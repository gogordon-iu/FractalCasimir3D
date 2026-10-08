#!/usr/bin/env python3
"""Export grounded experimental metrics and manuscript/figure provenance.

Values not supplied explicitly in the experiment specification are read from
the manuscript and its local TeX inputs. Missing or ambiguous measurements are
reported as audit failures; they are never replaced with invented values.

Exit codes:
    0: Successful export, including an intentionally capped --max-steps probe.
    1: Execution/export failure.
    2: Export completed, but required manuscript data could not be grounded.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import re
import shutil
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.metrics_logger import (  # noqa: E402
    export_macros,
    generate_manuscript_map,
    log_metric,
    log_step,
    save_plot_provenance,
)

T = TypeVar("T")
SCALING_LENGTHS = (
    0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.20, 1.40, 2.00, 3.00, 4.00, 4.50
)
SCALING_RESOLUTIONS = {
    length: (30, 40) if length <= 0.60 else (30,) if length < 2.00 else (40,)
    for length in SCALING_LENGTHS
}
FIGURE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".svg", ".eps", ".tif", ".tiff"}
NUMBER_PATTERN = (
    r"[-+]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][-+]?\d+)?"
)
NUMBER_RE = re.compile(NUMBER_PATTERN)
ASSIGNMENT_RE = re.compile(
    rf"(?P<name>[A-Za-z][A-Za-z0-9_]*(?:\([^)]*\))?)"
    rf"\s*(?:=|:)\s*(?P<value>{NUMBER_PATTERN})"
)
MACRO_RE = re.compile(r"\\([A-Za-z]+)\b")
DIGIT_WORDS = (
    "zero", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine",
)
MODEL_NAMES = {
    1: "Offset",
    2: "Pure Power Law",
    3: "Dual Power Law",
    4: "Screened Power Law",
}


@dataclass(frozen=True)
class Source:
    path: str
    line: int | None
    sha256: str | None
    basis: str


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    unit: str
    description: str
    group: str
    source: Source


@dataclass(frozen=True)
class TexDocument:
    path: Path
    text: str
    sha256: str


@dataclass(frozen=True)
class Table:
    document: TexDocument
    offset: int
    context: str
    rows: tuple[tuple[str, ...], ...]

    @property
    def source(self) -> Source:
        return Source(
            relative_path(self.document.path),
            self.document.text.count("\n", 0, self.offset) + 1,
            self.document.sha256,
            "manuscript table",
        )


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError(f"{label}: expected a real numeric value, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label}: non-finite value {value!r}")
    return result


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path: Path, value: object) -> None:
    atomic_write(
        path,
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%[^\n]*", "", text)


def plain_tex(text: str) -> str:
    """Normalize common numeric/table TeX without evaluating TeX commands."""
    result = strip_comments(text).replace("−", "-").replace("–", "-")
    result = re.sub(
        rf"({NUMBER_PATTERN})\s*\\(?:times|cdot)\s*10\s*\^\s*"
        r"\{\s*([-+]?\d+)\s*\}",
        lambda match: f"{match.group(1)}e{match.group(2)}",
        result,
    )
    result = re.sub(r"\\(?:SI|qty)\{([^{}]*)\}\{[^{}]*\}", r"\1", result)
    result = re.sub(r"\\(?:num|text|mathrm|mathbf|mathit|textrm|textbf)\{([^{}]*)\}", r"\1", result)
    result = re.sub(r"\\(?:pm|mp)\b", " +/- ", result)
    for symbol in ("alpha", "beta", "gamma", "lambda", "theta", "delta", "nu", "rho"):
        result = re.sub(rf"\\{symbol}\b", symbol, result)
    result = re.sub(r"_\s*\{([^{}]*)\}", r"_\1", result)
    result = re.sub(r"\\(?:hline|toprule|midrule|bottomrule|addlinespace)\b", " ", result)
    result = re.sub(r"\\(?:cline|cmidrule)(?:\([^)]*\))?\{[^{}]*\}", " ", result)
    result = re.sub(r"\\multicolumn\{\d+\}\{[^{}]*\}\{([^{}]*)\}", r"\1", result)
    result = result.replace(r"\%", "%").replace(r"\,", " ").replace(r"\!", "")
    result = result.replace(r"\(", "").replace(r"\)", "")
    result = result.replace(r"\[", "").replace(r"\]", "")
    result = result.replace("$", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", result).strip()


def macro_key(name: str) -> str:
    """Match metric names to TeX-safe names, including spelled-out digits."""
    expanded = re.sub(r"\d", lambda match: DIGIT_WORDS[int(match.group())], name)
    return re.sub(r"[^a-z]", "", expanded.lower())


def known_macro_values(registry: Registry) -> dict[str, float]:
    values = dict(registry.macro_values)
    for metric in registry.metrics.values():
        key = macro_key(metric.name)
        previous = values.get(key)
        if previous is not None and not math.isclose(
            previous, metric.value, rel_tol=1e-4, abs_tol=1e-4
        ):
            raise ValueError(f"Conflicting grounded macro value for {metric.name}.")
        values[key] = metric.value
    return values


def resolve_macro_tokens(text: str, registry: Registry | None) -> str:
    if registry is None:
        return text
    values = known_macro_values(registry)

    def replace(match: re.Match[str]) -> str:
        value = values.get(macro_key(match.group(1)))
        return match.group() if value is None else repr(value)

    return MACRO_RE.sub(replace, text)


def numeric_cell(cell: str, registry: Registry | None = None) -> float | None:
    text = plain_tex(resolve_macro_tokens(cell, registry))
    # Unknown value macros must not disappear and leave an unrelated number.
    if any(
        macro_key(match.group(1)) in {"", "nan", "inf", "infinity"}
        or match.group(1)[:1].isupper()
        for match in MACRO_RE.finditer(text)
    ):
        return None
    # Nested formatting can leave command names after braces are normalized.
    text = re.sub(r"\\[A-Za-z]+", "", text).strip()
    if "+/-" in text:
        text = text.split("+/-", 1)[0].strip()
    text = text.replace("^", "").strip()
    match = re.fullmatch(
        rf"\s*({NUMBER_PATTERN})\s*(?:%|nm|um|µm|μm|kHz|eV|deg|°)?\s*", text
    )
    if match is None:
        return None
    return finite_float(match.group(1), "manuscript numeric cell")


def read_manuscript_tree(manuscript: Path) -> list[TexDocument]:
    documents: list[TexDocument] = []
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.resolve()
        if resolved in visited:
            return
        if not resolved.is_file():
            raise FileNotFoundError(f"Missing manuscript input: {resolved}")
        visited.add(resolved)
        text = resolved.read_text(encoding="utf-8")
        documents.append(TexDocument(resolved, text, digest(resolved)))
        for match in re.finditer(
            r"\\(?:input|include)\s*\{([^{}]+)\}", strip_comments(text)
        ):
            name = match.group(1).strip()
            if "\\" in name or "#" in name:
                raise ValueError(f"Cannot resolve dynamic TeX input {name!r} in {resolved}")
            supplied = Path(name)
            if not supplied.suffix:
                supplied = supplied.with_suffix(".tex")
            candidates = (
                resolved.parent / supplied,
                manuscript.parent / supplied,
                REPO_ROOT / supplied,
            )
            target = next((candidate for candidate in candidates if candidate.is_file()), None)
            if target is None:
                raise FileNotFoundError(f"Cannot resolve TeX input {name!r} in {resolved}")
            visit(target)

    visit(manuscript)
    return documents


def extract_tables(documents: Sequence[TexDocument]) -> list[Table]:
    tables: list[Table] = []
    pattern = re.compile(
        r"\\begin\{(tabular\*?|tabularx|longtable)\}(.*?)\\end\{\1\}",
        re.DOTALL,
    )
    for document in documents:
        for match in pattern.finditer(document.text):
            body = strip_comments(match.group(2))
            rows: list[tuple[str, ...]] = []
            for row in re.split(r"\\\\(?:\[[^\]]*\])?|\\tabularnewline", body):
                if "&" not in row:
                    continue
                cells = tuple(plain_tex(cell) for cell in re.split(r"(?<!\\)&", row))
                rows.append(cells)
            if rows:
                tables.append(
                    Table(
                        document,
                        match.start(),
                        plain_tex(document.text[max(0, match.start() - 900):match.end() + 500]),
                        tuple(rows),
                    )
                )
    return tables


def slug(text: str) -> str:
    cleaned = re.sub(r"\\[A-Za-z]+", "", plain_tex(text))
    return re.sub(r"[^a-z0-9]+", "_", cleaned.lower()).strip("_")


class Registry:
    def __init__(self) -> None:
        self.metrics: dict[str, Metric] = {}
        self.macro_values: dict[str, float] = {}
        self.datasets: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add(
        self,
        name: str,
        value: object,
        unit: str,
        description: str,
        group: str,
        source: Source,
    ) -> None:
        metric = Metric(name, finite_float(value, name), unit, description, group, source)
        previous = self.metrics.get(name)
        if previous is not None and not math.isclose(
            previous.value, metric.value, rel_tol=1e-10, abs_tol=1e-12
        ):
            raise ValueError(
                f"Conflicting grounded values for {name}: {previous.value} and {metric.value}"
            )
        if previous is None:
            self.metrics[name] = metric

    def fail(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)


def register_macro_definitions(
    registry: Registry, documents: Sequence[TexDocument]
) -> None:
    """Read only explicit, argument-free numeric macros; never execute TeX."""
    pattern = re.compile(
        r"\\(?:newcommand|renewcommand|providecommand)\*?\s*"
        r"(?:\{\\(?P<braced>[A-Za-z]+)\}|\\(?P<bare>[A-Za-z]+))"
        r"\s*(?:\[0\]\s*)?\{(?P<body>[^{}]*)\}"
        r"|\\def\s*\\(?P<defined>[A-Za-z]+)\s*\{(?P<definition>[^{}]*)\}"
    )
    pending: list[tuple[str, str]] = []
    for document in documents:
        for match in pattern.finditer(strip_comments(document.text)):
            name = match.group("braced") or match.group("bare") or match.group("defined")
            body = match.group("body")
            if body is None:
                body = match.group("definition")
            pending.append((name, body))

    # Repeated passes allow simple aliases without evaluating recursive macros.
    while pending:
        unresolved: list[tuple[str, str]] = []
        progress = False
        for name, body in pending:
            value = numeric_cell(body, registry)
            if value is None:
                unresolved.append((name, body))
                continue
            key = macro_key(name)
            previous = registry.macro_values.get(key)
            if previous is not None and not math.isclose(
                previous, value, rel_tol=1e-10, abs_tol=1e-12
            ):
                raise ValueError(f"Conflicting manuscript definitions for \\{name}.")
            registry.macro_values[key] = value
            progress = True
        if not progress:
            break
        pending = unresolved


def specification_source(
    value: float,
    documents: Sequence[TexDocument],
    registry: Registry | None = None,
    metric_name: str | None = None,
) -> Source:
    # Preserve offsets when removing comments so source line attribution is exact.
    texts = [
        re.sub(r"(?<!\\)%[^\n]*", lambda match: " " * len(match.group()), document.text)
        for document in documents
    ]
    for document, text in zip(documents, texts, strict=True):
        for match in NUMBER_RE.finditer(text):
            candidate = finite_float(match.group(), "manuscript numeric token")
            if math.isclose(candidate, value, rel_tol=1e-9, abs_tol=1e-12):
                return Source(
                    relative_path(document.path),
                    document.text.count("\n", 0, match.start()) + 1,
                    document.sha256,
                    "experiment specification; numeric occurrence in manuscript "
                    "(occurrence alone is not semantic verification)",
                )

    values = known_macro_values(registry) if registry is not None else {}
    if metric_name is not None:
        key = macro_key(metric_name)
        previous = values.get(key)
        if previous is not None and not math.isclose(
            previous, value, rel_tol=1e-4, abs_tol=1e-4
        ):
            raise ValueError(f"Conflicting grounded macro value for {metric_name}.")
        values[key] = value
    for document, text in zip(documents, texts, strict=True):
        for match in MACRO_RE.finditer(text):
            # A declaration is not a manuscript use of the macro.
            prefix = text[max(0, match.start() - 100):match.start()]
            if re.search(
                r"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{?\s*$"
                r"|\\def\s*$",
                prefix,
            ):
                continue
            candidate = values.get(macro_key(match.group(1)))
            if candidate is not None and math.isclose(
                candidate, value, rel_tol=1e-4, abs_tol=1e-4
            ):
                return Source(
                    relative_path(document.path),
                    document.text.count("\n", 0, match.start()) + 1,
                    document.sha256,
                    f"experiment specification; matching metric macro {match.group()} "
                    "used in manuscript (occurrence alone is not semantic verification)",
                )
    return Source(
        "grounded-experiment-pipeline/user-specification",
        None,
        None,
        "explicit experiment specification; no matching manuscript numeric token or macro found",
    )


def register_supplied_metrics(
    registry: Registry, documents: Sequence[TexDocument]
) -> None:
    register_macro_definitions(registry, documents)
    # Force and pressure units are not guessed where the specification omits them.
    groups: dict[str, list[tuple[str, float, str, str]]] = {
        "model_1": [
            ("model_1_ssr", 0.00928379, "reported units", "Offset sum of squared residuals"),
        ],
        "model_2": [
            ("model_2_ssr", 0.03148498, "reported units", "Pure power-law sum of squared residuals"),
        ],
        "model_3": [
            ("model_3_ssr", 0.03148498, "reported units", "Dual power-law sum of squared residuals"),
        ],
        "model_4": [
            ("model_4_lambda", 1.223087, "um", "Screened power-law screening length"),
            ("model_4_ssr", 0.00440022, "reported units", "Screened power-law sum of squared residuals"),
        ],
        "lifshitz": [
            (
                f"lifshitz_d_{distance}_pressure",
                pressure,
                "reported pressure units",
                f"Table 3 semi-analytical Lifshitz pressure at d={distance} nm",
            )
            for distance, pressure in (
                (100, -0.00395),
                (150, 0.00340),
                (200, 0.00376),
                (250, 0.00305),
                (300, 0.00231),
                (400, 0.00129),
                (500, 0.000748),
            )
        ],
        "asymmetric_cavity": [
            ("asymmetric_cavity_F_both", -0.583529, "reported force units", "Combined force"),
            ("asymmetric_cavity_F_self", -0.538354, "reported force units", "Self-force"),
            ("asymmetric_cavity_F_net", -0.045175, "reported force units", "Net force"),
            ("asymmetric_cavity_A_eff", 3.160494, "reported area units", "Effective area"),
            ("asymmetric_cavity_pressure", -0.014294, "reported pressure units", "Net pressure"),
            ("asymmetric_cavity_suppression_factor", 8.25, "dimensionless", "Suppression factor"),
        ],
        "frontier_1": [
            ("frontier_1_pressure", -0.218758, "reported pressure units", "Stepped-sieve pressure"),
        ],
        "frontier_2": [
            ("frontier_2_F_both", 4838.044314, "reported force units", "Combined force"),
            ("frontier_2_F_self", 4838.065605, "reported force units", "Self-force"),
            ("frontier_2_F_net", -0.021290, "reported force units", "Reported net force"),
            ("frontier_2_pressure", -0.006736, "reported pressure units", "Net pressure"),
            ("frontier_2_cancellation_percent", 94.3, "%", "Reported cancellation percentage"),
            ("frontier_2_reduction_ratio", 17.52, "dimensionless", "Reported reduction ratio"),
        ],
        "atomic_cqed": [
            ("atomic_cqed_lamb_shift_delta_nu", 2.4, "kHz", "Lamb frequency shift"),
            ("atomic_cqed_lamb_shift_delta_E", 1.0e-11, "eV", "Lamb energy shift"),
            ("atomic_cqed_purcell_lifetime_variation_min", 10.0, "%", "Minimum lifetime variation"),
            ("atomic_cqed_purcell_lifetime_variation_max", 50.0, "%", "Maximum lifetime variation"),
            ("atomic_cqed_cp_shift", 1.0e-6, "eV", "Casimir-Polder energy shift"),
            ("atomic_cqed_scattering_deviation", 3.0e-19, "reported units", "Scattering deviation"),
        ],
    }
    for group, entries in groups.items():
        for name, value, unit, description in entries:
            registry.add(
                name, value, unit, description, group,
                specification_source(value, documents, registry, name),
            )

    registry.datasets["lifshitz"] = {
        "columns": ["d_nm", "pressure"],
        "rows": [
            [distance, entry[1]]
            for distance, entry in zip(
                (100, 150, 200, 250, 300, 400, 500), groups["lifshitz"], strict=True
            )
        ],
        "basis": "explicit experiment specification; Table 3 semi-analytical pressures",
    }

    sweet_spots = (
        (75.0, 82.0, 50.0, 3.610842),
        (75.0, 90.0, 150.0, 3.575480),
        (75.0, 94.0, 50.0, 0.901610),
        (60.0, 91.1, 100.0, 0.049422),
    )
    registry.datasets["repulsive_sweet_spots"] = {
        "columns": ["alpha_deg", "theta_deg", "d_nm", "pressure"],
        "rows": [list(row) for row in sweet_spots],
        "basis": "explicit experiment specification",
    }
    for index, row in enumerate(sweet_spots, start=1):
        for field, value, unit in zip(
            ("alpha", "theta", "d", "pressure"),
            row,
            ("deg", "deg", "nm", "reported pressure units"),
            strict=True,
        ):
            name = f"sweet_spot_{index}_{field}"
            registry.add(
                name,
                value,
                unit,
                f"Repulsive sweet spot {index}: {field}",
                "repulsive_sweet_spots",
                specification_source(value, documents, registry, name),
            )


def resolution_column(cell: str, resolution: int) -> bool:
    normalized = plain_tex(cell).lower()
    return bool(
        re.search(rf"\br\s*(?:=|_)?\s*{resolution}\b", normalized)
        or re.fullmatch(rf"(?:pressure|p)\s*[_([]?\s*{resolution}\s*[\])]?", normalized)
    )


def length_column(cell: str) -> bool:
    normalized = plain_tex(cell).lower()
    return bool(
        re.search(r"(?:\bplate\b(?:\s*size)?|\bl\b|length|separation|gap)", normalized)
    )


def register_scaling(registry: Registry, tables: Sequence[Table]) -> None:
    found: dict[tuple[float, int], tuple[float, Source]] = {}

    def record(length: float, resolution: int, pressure: float, source: Source) -> None:
        target = next(
            (item for item in SCALING_LENGTHS if math.isclose(item, length, abs_tol=1e-8)),
            None,
        )
        if target is None:
            return
        key = (target, resolution)
        previous = found.get(key)
        if previous is not None and not math.isclose(
            previous[0], pressure, rel_tol=1e-9, abs_tol=1e-12
        ):
            registry.fail(f"Ambiguous scaling pressure for L={target:.2f}, R={resolution}.")
            return
        found[key] = (pressure, source)

    for table in tables:
        for header_index, header in enumerate(table.rows):
            l_indices = [index for index, cell in enumerate(header) if length_column(cell)]
            columns = {
                resolution: [
                    index for index, cell in enumerate(header)
                    if resolution_column(cell, resolution)
                ]
                for resolution in (30, 40)
            }
            if len(l_indices) != 1:
                continue
            for row in table.rows[header_index + 1:]:
                if l_indices[0] >= len(row):
                    continue
                length = numeric_cell(row[l_indices[0]], registry)
                if length is None:
                    continue
                for resolution, indices in columns.items():
                    if len(indices) == 1 and indices[0] < len(row):
                        pressure = numeric_cell(row[indices[0]], registry)
                        if pressure is not None:
                            record(length, resolution, pressure, table.source)

    rows: list[dict[str, Any]] = []
    expected = {
        (length, resolution)
        for length, resolutions in SCALING_RESOLUTIONS.items()
        for resolution in resolutions
    }
    for length in SCALING_LENGTHS:
        row: dict[str, Any] = {"L": length}
        tag = f"{length:.2f}".replace(".", "p")
        for resolution in (30, 40):
            entry = found.get((length, resolution))
            if entry is None:
                # Table 1 intentionally omits the other resolution at larger L.
                if (length, resolution) in expected:
                    registry.fail(
                        f"Missing grounded scaling pressure: L={length:.2f}, R={resolution}. "
                        "Expected a manuscript table with plate size/L and "
                        "R=30/R=40 column headers."
                    )
                continue
            value, source = entry
            row[f"pressure_R{resolution}"] = value
            registry.add(
                f"scaling_L_{tag}_R_{resolution}_pressure",
                value,
                "reported pressure units",
                f"Scaling pressure at L={length:.2f}, R={resolution}",
                "scaling",
                source,
            )
        rows.append(row)
    registry.datasets["scaling"] = {
        "L_values": list(SCALING_LENGTHS),
        "resolutions": [30, 40],
        "available_resolutions_by_L": {
            f"{length:.2f}": list(resolutions)
            for length, resolutions in SCALING_RESOLUTIONS.items()
        },
        "rows": rows,
        "complete": expected.issubset(found)
        and not any("Ambiguous scaling" in error for error in registry.errors),
    }


def model_number(text: str) -> int | None:
    normalized = plain_tex(text).lower()
    explicit = re.search(r"\bmodel\s*([1-4])\b", normalized)
    if explicit:
        return int(explicit.group(1))
    if "screened" in normalized and "power" in normalized:
        return 4
    if "dual" in normalized and "power" in normalized:
        return 3
    if "pure" in normalized and "power" in normalized:
        return 2
    if "offset" in normalized:
        return 1
    return None


def parameter_name(text: str) -> str | None:
    label = slug(text)
    aliases = {
        "sum_of_squared_residuals": "ssr",
        "sum_squared_residuals": "ssr",
        "screening_length": "lambda",
        "a_1": "a1",
        "a_2": "a2",
        "alpha_1": "alpha1",
        "alpha_2": "alpha2",
    }
    label = aliases.get(label, label)
    if not label or label in {
        "model", "model_name", "fit", "best_fit", "parameters", "best_fit_parameters",
        "equation", "functional_form", "formula", "name", "description",
    }:
        return None
    return label


def register_models(
    registry: Registry, tables: Sequence[Table], documents: Sequence[TexDocument]
) -> None:
    extracted: dict[int, set[str]] = {index: set() for index in MODEL_NAMES}

    def add_parameter(index: int, parameter: str, value: float, source: Source) -> None:
        if parameter in {"r", "l", "model", "n", "number"}:
            return
        name = f"model_{index}_{parameter}"
        try:
            registry.add(
                name,
                value,
                "um" if parameter == "lambda" else "reported fit units",
                f"Model {index} ({MODEL_NAMES[index]}): {parameter}",
                f"model_{index}",
                source,
            )
            extracted[index].add(parameter)
        except ValueError as exc:
            registry.fail(str(exc))

    for table in tables:
        last_header: tuple[str, ...] | None = None
        for row in table.rows:
            index = model_number(" ".join(row[:2]))
            if index is None:
                if any(
                    "model" in cell.lower() or "parameter" in cell.lower()
                    or "ssr" in cell.lower()
                    for cell in row
                ):
                    last_header = row
                continue
            for cell in row:
                normalized = plain_tex(resolve_macro_tokens(cell, registry))
                for assignment in ASSIGNMENT_RE.finditer(normalized):
                    parameter = parameter_name(assignment.group("name"))
                    if parameter:
                        add_parameter(
                            index, parameter,
                            finite_float(assignment.group("value"), parameter), table.source,
                        )
            if last_header is not None and len(last_header) == len(row):
                for heading, cell in zip(last_header, row, strict=True):
                    parameter = parameter_name(heading)
                    value = numeric_cell(cell, registry)
                    if parameter and value is not None:
                        add_parameter(index, parameter, value, table.source)

    # Each itemize entry is a separate semantic unit even when all four items
    # occur in one paragraph. Read assignments even if a table already gave SSR.
    for document in documents:
        boundaries = [0]
        boundaries.extend(
            match.end()
            for match in re.finditer(
                r"\n\s*\n|\\item\b(?:\s*\[[^\]]*\])?|\\end\{itemize\}",
                document.text,
            )
        )
        boundaries.append(len(document.text))
        for start, end in zip(boundaries, boundaries[1:]):
            paragraph = document.text[start:end]
            normalized = plain_tex(resolve_macro_tokens(paragraph, registry))
            references = re.findall(r"\b[Mm]odel\s*([1-4])\b", normalized)
            if len(set(references)) != 1:
                continue
            index = int(references[0])
            source = Source(
                relative_path(document.path),
                document.text.count("\n", 0, start) + 1,
                document.sha256,
                "explicit parameter assignment in model paragraph or item",
            )
            for assignment in ASSIGNMENT_RE.finditer(normalized):
                parameter = parameter_name(assignment.group("name"))
                if parameter:
                    add_parameter(
                        index, parameter,
                        finite_float(assignment.group("value"), parameter), source,
                    )

    required_parameters = {
        1: {"a", "alpha", "b"},
        2: {"a", "alpha"},
        3: {"a1", "alpha1", "a2", "alpha2"},
        4: {"a", "alpha", "lambda"},
    }
    for index, model_name in MODEL_NAMES.items():
        missing = required_parameters[index] - extracted[index]
        if missing:
            registry.fail(
                f"Missing manuscript best-fit parameters for Model {index} "
                f"({model_name}): {', '.join(sorted(missing))}."
            )
        registry.datasets[f"model_{index}"] = {
            "name": model_name,
            "parameters": {
                name.removeprefix(f"model_{index}_"): metric.value
                for name, metric in registry.metrics.items()
                if metric.group == f"model_{index}"
            },
            "manuscript_parameters_extracted": sorted(extracted[index]),
        }


def equilibrium_header(text: str) -> bool:
    normalized = plain_tex(text).lower()
    return bool(
        re.search(r"\bd_?eq\b", normalized)
        or re.search(r"\bgap\b", normalized)
        or "equilibrium" in normalized
    )


def register_equilibria(registry: Registry, tables: Sequence[Table]) -> None:
    candidates: list[tuple[list[float], Source]] = []
    for table in tables:
        for index, header in enumerate(table.rows):
            columns = [column for column, cell in enumerate(header) if equilibrium_header(cell)]
            if len(columns) != 1:
                continue
            column = columns[0]
            if "nm" not in header[column].lower() and "nm" not in table.context.lower():
                continue
            alpha_columns = [
                i for i, cell in enumerate(header)
                if re.search(r"\balpha\b", plain_tex(cell).lower())
            ]
            theta_columns = [
                i for i, cell in enumerate(header)
                if re.search(r"\btheta\b", plain_tex(cell).lower())
            ]
            has_angles = len(alpha_columns) == 1 and len(theta_columns) == 1
            seen: set[tuple[float, float, float]] = set()
            values: list[float] = []
            for row in table.rows[index + 1:]:
                if column >= len(row):
                    continue
                value = numeric_cell(row[column], registry)
                if value is None:
                    continue
                if has_angles:
                    alpha_column = alpha_columns[0]
                    theta_column = theta_columns[0]
                    if max(alpha_column, theta_column) >= len(row):
                        continue
                    alpha = numeric_cell(row[alpha_column], registry)
                    theta = numeric_cell(row[theta_column], registry)
                    if alpha is None or theta is None:
                        continue
                    key = (alpha, theta, round(value, 1))
                    if key in seen:
                        continue
                    seen.add(key)
                values.append(value)
            if len(values) >= 13:
                candidates.append((values, table.source))

    if not candidates:
        registry.fail(
            "Missing at least 13 verified levitation equilibrium heights. Expected a "
            "manuscript table with a d_eq/equilibrium-height column explicitly in nm."
        )
        registry.datasets["levitation_equilibria"] = {
            "d_eq_nm": [], "expected_count": 13, "actual_count": 0, "complete": False
        }
        return

    heights, source = candidates[0]
    if any(
        len(heights) != len(other)
        or any(not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
               for a, b in zip(heights, other, strict=True))
        for other, _ in candidates[1:]
    ):
        registry.fail("Conflicting manuscript tables of equilibrium heights.")
        return
    if any(height <= 0.0 for height in heights):
        registry.fail("Equilibrium heights must all be positive finite values.")
        return

    registry.datasets["levitation_equilibria"] = {
        "d_eq_nm": heights,
        "expected_count": 13,
        "actual_count": len(heights),
        "complete": True,
        "source": asdict(source),
        "verification_basis": "reported manuscript equilibria; stability not recomputed",
        "deduplication_basis": "(alpha, theta, round(d_eq_nm, 1)) where available",
    }
    for index, height in enumerate(heights, start=1):
        registry.add(
            f"levitation_equilibrium_{index:02d}_d_eq",
            height, "nm", f"Verified equilibrium {index}: height",
            "levitation_equilibria", source,
        )


def validate_benchmarks(registry: Registry) -> None:
    for prefix in ("asymmetric_cavity", "frontier_2"):
        combined = registry.metrics[f"{prefix}_F_both"].value
        self_force = registry.metrics[f"{prefix}_F_self"].value
        reported = registry.metrics[f"{prefix}_F_net"].value
        residual = abs((combined - self_force) - reported)
        if residual > 1.6e-6:
            registry.fail(f"{prefix}: reported net force is inconsistent beyond rounding.")
        elif residual > 1e-9:
            registry.warnings.append(
                f"{prefix}: force subtraction differs from reported F_net by "
                f"{residual:.3g}; retained the reported value (rounding-level difference)."
            )
    area = registry.metrics["asymmetric_cavity_A_eff"].value
    if area <= 0.0:
        registry.fail("Asymmetric cavity effective area must be positive.")
    else:
        implied = registry.metrics["asymmetric_cavity_F_net"].value / area
        reported_pressure = registry.metrics["asymmetric_cavity_pressure"].value
        if not math.isclose(implied, reported_pressure, abs_tol=1e-6, rel_tol=0.0):
            registry.fail("Asymmetric cavity pressure is inconsistent with F_net / A_eff.")


def invoke_logger(
    function: Callable[..., Any],
    values: Mapping[str, Any],
    aliases: Mapping[str, str],
    primary: str | None = None,
) -> Any:
    """Bind known logger API spellings; reject unsupported required arguments."""
    signature = inspect.signature(function)
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    consumed: set[str] = set()
    accepts_kwargs = False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            accepts_kwargs = True
            continue
        key = aliases.get(parameter.name, parameter.name)
        if key not in values:
            if parameter.default is inspect.Parameter.empty:
                raise TypeError(
                    f"{function.__name__}{signature}: unsupported required parameter "
                    f"{parameter.name!r}; available semantic fields: {sorted(values)}"
                )
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                positional.append(parameter.default)
            continue
        consumed.add(key)
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(values[key])
        else:
            keywords[parameter.name] = values[key]
    if accepts_kwargs:
        for key, value in values.items():
            if key not in consumed:
                keywords[key] = value
    if primary is not None and primary not in consumed and not accepts_kwargs:
        raise TypeError(
            f"{function.__name__}{signature} cannot accept required {primary!r} data."
        )
    signature.bind(*positional, **keywords)
    return function(*positional, **keywords)


LOGGER_ALIASES: dict[str, str] = {
    "key": "name",
    "metric": "name",
    "metric_name": "name",
    "metric_value": "value",
    "units": "unit",
    "step": "step_name",
    "name_step": "step_name",
    "step_id": "step_name",
    "parameters": "params",
    "input_files": "inputs",
    "data_source": "inputs",
    "columns_used": "metrics",
    "output_files": "outputs",
    "source_file": "source",
    "source_path": "source",
    "file_path": "output_path",
    "output_file": "output_path",
    "filename": "output_path",
    "path": "output_path",
    "out_path": "output_path",
    "out_dir": "output_dir",
    "results_dir": "output_dir",
    "plot_path": "figure_path",
    "plot_file": "figure_path",
    "figure_file": "figure_path",
    "fig_path": "figure_path",
    "plot": "figure_path",
    "script_path": "script",
    "script_name": "script",
    "manuscript": "manuscript_path",
    "tex_path": "manuscript_path",
    "tex_file": "manuscript_path",
    "manuscript_file": "manuscript_path",
    "figures_dir": "figure_dir",
    "provenance": "metadata",
}


def logger_call(
    function: Callable[..., Any],
    values: Mapping[str, Any],
    aliases: Mapping[str, str] | None = None,
    primary: str | None = None,
) -> Any:
    if function is log_step and "data" not in values:
        # log_step(name, data, metrics_path) stores the complete step payload.
        values = {**values, "data": dict(values)}
    if function is save_plot_provenance:
        inputs_val = values.get("inputs", "results/provenance_metrics.json")
        data_source_str = (
            str(inputs_val[0])
            if isinstance(inputs_val, (list, tuple)) and inputs_val
            else str(inputs_val)
        )
        values = {
            **values,
            "data_source": data_source_str,
            "columns_used": list(values.get("metrics", [])),
        }
        # Bind the adapted fields rather than the original inputs/metrics.
        aliases = {
            **(aliases or {}),
            "data_source": "data_source",
            "columns_used": "columns_used",
        }
    return invoke_logger(
        function, values, {**LOGGER_ALIASES, **(aliases or {})}, primary
    )


def ensure_logger_artifact(
    target: Path, result: Any, default_path: Path, *, json_output: bool
) -> None:
    if target.is_file() and target.stat().st_size > 0:
        return
    if isinstance(result, Mapping) or (
        json_output and isinstance(result, (list, tuple))
    ):
        write_json(target, result)
        return
    if isinstance(result, (str, Path)):
        candidate: Path | None = None
        try:
            proposed = Path(result)
            if proposed.is_file():
                candidate = proposed
        except (OSError, ValueError):
            candidate = None
        if candidate is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
            return
        if isinstance(result, str) and (
            (json_output and result.lstrip().startswith(("{", "[")))
            or (not json_output and "\\" in result)
        ):
            if json_output:
                json.loads(result)
            atomic_write(target, result.rstrip() + "\n")
            return
    if default_path.is_file() and default_path.stat().st_size > 0:
        if default_path.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(default_path, target)
        return
    raise RuntimeError(f"Logger did not produce the required artifact: {target}")


def find_figures(manuscript: Path) -> list[Path]:
    roots = {
        REPO_ROOT / "Papers/Fractal_Casimir_Nature_EM/figures",
        manuscript.parent / "figures",
        REPO_ROOT / "figures",
    }
    figures: set[Path] = set()
    for root in roots:
        if root.is_dir():
            figures.update(
                path.resolve() for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in FIGURE_EXTENSIONS
            )
    figures.update(
        path.resolve() for path in REPO_ROOT.iterdir()
        if path.is_file() and path.suffix.lower() in FIGURE_EXTENSIONS
    )
    return sorted(figures, key=str)


def export_pipeline(args: argparse.Namespace) -> int:
    manuscript = Path(args.manuscript).expanduser()
    if not manuscript.is_absolute():
        manuscript = REPO_ROOT / manuscript
    manuscript = manuscript.resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    documents = read_manuscript_tree(manuscript)
    tables = extract_tables(documents)
    registry = Registry()
    register_supplied_metrics(registry, documents)
    register_scaling(registry, tables)
    register_models(registry, tables, documents)
    register_equilibria(registry, tables)
    validate_benchmarks(registry)

    all_metrics = list(registry.metrics.values())
    selected = (
        all_metrics if args.max_steps is None else all_metrics[:args.max_steps]
    )
    figures = find_figures(manuscript)
    if not figures:
        registry.warnings.append("No supported figure files were found.")

    registry_path = output_dir / "experiment_provenance_registry.json"
    metrics_path = output_dir / "metrics.jsonl"
    macros_path = output_dir / "macros_results.tex"
    map_path = output_dir / "manuscript_provenance_map.json"
    audit_path = output_dir / "provenance_audit_summary.json"
    inputs = [str(document.path) for document in documents]
    script_path = str(Path(__file__).resolve())
    logged_names = [metric.name for metric in selected]

    write_json(
        registry_path,
        {
            "schema_version": 1,
            "script": relative_path(Path(__file__)),
            "script_sha256": digest(Path(__file__)),
            "manuscript": relative_path(manuscript),
            "documents": [
                {"path": relative_path(doc.path), "sha256": doc.sha256}
                for doc in documents
            ],
            "datasets": registry.datasets,
            "metrics": [asdict(metric) for metric in all_metrics],
            "selected_metric_names": logged_names,
            "errors": registry.errors,
            "warnings": registry.warnings,
        },
    )

    with working_directory(REPO_ROOT):
        logger_call(
            log_step,
            {
                "step_name": "grounded_experiment_provenance_export",
                "description": "Register manuscript-grounded empirical experiment data.",
                "script": script_path,
                "params": {
                    "max_steps": args.max_steps,
                    "output_dir": str(output_dir),
                    "manuscript": str(manuscript),
                    "registry": str(registry_path),
                },
                "inputs": inputs,
                "outputs": [str(registry_path), str(macros_path), str(map_path)],
                "output_dir": str(output_dir),
                "metrics_path": str(metrics_path),
                "metadata": {"errors": registry.errors, "warnings": registry.warnings},
            },
            aliases={"name": "step_name"},
            primary="step_name",
        )
        for metric in selected:
            logger_call(
                log_metric,
                {
                    "name": metric.name,
                    "value": metric.value,
                    "unit": metric.unit,
                    "description": metric.description,
                    "source": metric.source.path,
                    "step_name": "grounded_experiment_provenance_export",
                    "script": script_path,
                    "output_dir": str(output_dir),
                    "output_path": str(metrics_path),
                    "metrics_path": str(metrics_path),
                    "metadata": {
                        "group": metric.group,
                        "source": asdict(metric.source),
                    },
                },
                primary="value",
            )

        # This run-specific ledger is independent of any logger append history.
        atomic_write(
            output_dir / "provenance_metrics.jsonl",
            "".join(
                json.dumps(asdict(metric), sort_keys=True, allow_nan=False) + "\n"
                for metric in selected
            ),
        )

        macros_result = logger_call(
            export_macros,
            {
                "output_path": str(macros_path),
                "output_dir": str(output_dir),
                "metrics_path": str(metrics_path),
            },
            aliases={"macros_path": "output_path"},
        )
        ensure_logger_artifact(
            macros_path, macros_result,
            REPO_ROOT / "results/macros_results.tex", json_output=False,
        )

        sidecars: list[str] = []
        for figure in figures:
            # The canonical full-filename sidecar avoids collisions between
            # figures such as plot.pdf and plot.png.
            sidecar = Path(f"{figure}.provenance.json")
            metadata: dict[str, Any] = {
                "schema_version": 1,
                "figure": relative_path(figure),
                "figure_sha256": digest(figure),
                "script": relative_path(Path(__file__)),
                "manuscript": relative_path(manuscript),
                "registry": relative_path(registry_path),
                "inputs": inputs,
                "exported_metric_names": logged_names,
                "lineage_status": "inventory association, not reconstructed generation lineage",
                "note": (
                    "The export script discovered this existing figure. It does not "
                    "claim to be the script that generated the figure or infer which "
                    "measurements were plotted."
                ),
            }
            provenance_result = logger_call(
                save_plot_provenance,
                {
                    "figure_path": str(figure),
                    "output_path": str(sidecar),
                    "output_dir": str(output_dir),
                    "script": script_path,
                    "params": {"manuscript": str(manuscript)},
                    "inputs": inputs + [str(registry_path)],
                    "metrics": logged_names,
                    "description": metadata["note"],
                    "metadata": metadata,
                },
                aliases={"path": "figure_path", "file_path": "figure_path"},
                primary="figure_path",
            )
            existing: dict[str, Any] = {}
            if sidecar.is_file():
                loaded = json.loads(sidecar.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError(f"Figure sidecar must contain a JSON object: {sidecar}")
                existing = loaded
            elif isinstance(provenance_result, Mapping):
                existing = dict(provenance_result)
            else:
                conventional = figure.with_suffix(".provenance.json")
                if conventional.is_file():
                    loaded = json.loads(conventional.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        existing = loaded
            existing["grounded_experiment_export"] = metadata
            write_json(sidecar, existing)
            sidecars.append(relative_path(sidecar))

        map_result = logger_call(
            generate_manuscript_map,
            {
                "manuscript_path": str(manuscript),
                "output_path": str(map_path),
                "output_dir": str(output_dir),
                "figure_dir": str(manuscript.parent / "figures"),
                "figures": [str(figure) for figure in figures],
                "metrics_path": str(metrics_path),
                "macros_path": str(macros_path),
                "registry_path": str(registry_path),
            },
            aliases={"map_path": "output_path"},
        )
        ensure_logger_artifact(
            map_path, map_result,
            REPO_ROOT / "results/manuscript_provenance_map.json",
            json_output=True,
        )
        json.loads(map_path.read_text(encoding="utf-8"))

    capped = len(selected) < len(all_metrics)
    status = (
        "incomplete_grounding" if registry.errors
        else "successful_micro_probe" if capped
        else "complete"
    )
    audit: dict[str, Any] = {
        "status": status,
        "audit_status": "FAIL" if registry.errors else "PASS",
        "manuscript": relative_path(manuscript),
        "output_dir": str(output_dir),
        "manuscript_source_files": len(documents),
        "manuscript_tables_examined": len(tables),
        "datasets_registered": sorted(registry.datasets),
        "metrics_registered": len(all_metrics),
        "metrics_exported": len(selected),
        "metrics_skipped_by_max_steps": len(all_metrics) - len(selected),
        "max_steps": args.max_steps,
        "figures_found": len(figures),
        "figure_sidecars": sidecars,
        "artifacts": {
            "registry": relative_path(registry_path),
            "run_metrics": relative_path(output_dir / "provenance_metrics.jsonl"),
            "macros": relative_path(macros_path),
            "manuscript_map": relative_path(map_path),
            "audit": relative_path(audit_path),
        },
        "errors": registry.errors,
        "warnings": registry.warnings,
        "grounding_policy": (
            "Unspecified pressures, fit parameters, and equilibrium heights must "
            "be extracted from manuscript tables or explicit model assignments. "
            "Reported stability and existing-figure lineage are not recomputed."
        ),
    }
    write_json(audit_path, audit)

    print("\nFractal Casimir Effect — provenance audit")
    print("=" * 56)
    print(f"Status:                 {status}")
    print(f"Audit status:           {audit['audit_status']}")
    print(f"Manuscript:             {relative_path(manuscript)}")
    print(f"Output directory:       {output_dir}")
    print(f"TeX source files:       {len(documents)}")
    print(f"Tables examined:        {len(tables)}")
    print(f"Datasets registered:    {len(registry.datasets)}")
    print(f"Metrics registered:     {len(all_metrics)}")
    print(f"Metrics exported:       {len(selected)}")
    print(f"Metrics probe-skipped:  {len(all_metrics) - len(selected)}")
    print(f"Figures / sidecars:     {len(figures)} / {len(sidecars)}")
    print("\nDatasets:")
    for name in sorted(registry.datasets):
        print(f"  - {name}")
    print("\nArtifacts:")
    for name, artifact in audit["artifacts"].items():
        print(f"  {name}: {artifact}")
    if registry.warnings:
        print("\nWarnings:")
        for warning in registry.warnings:
            print(f"  - {warning}")
    if registry.errors:
        print("\nGrounding failures:")
        for error in registry.errors:
            print(f"  - {error}")
        print("\nExport is incomplete; no missing experimental values were fabricated.")
    elif capped:
        print("\nIntentional micro-probe: only the selected metrics were sent to the logger.")
    else:
        print("\nAll required data categories were registered and exported.")
    return 2 if registry.errors else 0


def nonnegative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export grounded Fractal Casimir experiment provenance."
    )
    parser.add_argument(
        "--max-steps",
        type=nonnegative_int,
        default=None,
        help="Limit log_metric calls for a micro-probe; discovery still examines all data.",
    )
    parser.add_argument(
        "--output-dir", type=str, default="results",
        help="Output directory, relative to the repository root unless absolute.",
    )
    parser.add_argument(
        "--manuscript",
        type=str,
        default="Papers/Fractal_Casimir_Nature_EM/nature_fractal_casimir_em.tex",
        help="Manuscript path, relative to the repository root unless absolute.",
    )
    args = parser.parse_args(argv)
    if not args.output_dir.strip():
        parser.error("--output-dir must not be empty")
    if not args.manuscript.strip():
        parser.error("--manuscript must not be empty")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return export_pipeline(args)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(f"Provenance pipeline failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
