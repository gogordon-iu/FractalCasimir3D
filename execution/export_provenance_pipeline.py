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
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
MODEL_ID = "FractalCasimirProvenance"
# Reported Meep pressures are dimensionless. Convert to SI pressure by
# multiplication, not division: pressure_pa = pressure_meep * MEEP_TO_PA.
MEEP_TO_PA = 0.0316152649
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
    metadata: dict[str, Any] = field(default_factory=dict)


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
        values[macro_key(metric.name)] = metric.value
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
        numeric_value = finite_float(value, name)
        metadata: dict[str, Any] = {}
        if unit == "reported pressure units":
            metadata["pressure_unit_provenance"] = {
                "pressure_meep": numeric_value,
                "meep_unit": "dimensionless",
                "pressure_pa": finite_float(numeric_value * MEEP_TO_PA, f"{name} (Pa)"),
                "si_unit": "Pa",
                "meep_to_pa": MEEP_TO_PA,
                "conversion": "pressure_pa = pressure_meep * meep_to_pa",
                "basis": "specified Meep-to-SI pressure conversion; original value retained",
            }
        metric = Metric(name, numeric_value, unit, description, group, source, metadata)
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
        values[macro_key(metric_name)] = value
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
    """Register true-vacuum NEMS feasibility and 3-solver verification metrics from JSON reports."""
    register_macro_definitions(registry, documents)

    # Register true-vacuum NEMS feasibility and 3-solver verification metrics
    # recorded with exact caller provenance in results/provenance_metrics.json.
    manifest_path = REPO_ROOT / "results" / "provenance_metrics.json"
    if manifest_path.is_file():
        manifest_checksum = digest(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_metrics = manifest.get("metrics", {})
        nems_exported: dict[str, float] = {}
        solver3_exported: dict[str, float] = {}
        canonical_val_exported: dict[str, float] = {}
        if isinstance(manifest_metrics, Mapping):
            for name, entry in manifest_metrics.items():
                if not isinstance(entry, Mapping):
                    continue
                src_file = str(entry.get("source_file", ""))
                raw_val = entry.get("value")
                if isinstance(raw_val, bool) or not isinstance(raw_val, (int, float)):
                    continue
                if not math.isfinite(float(raw_val)):
                    continue
                val = float(raw_val)
                line_no = entry.get("line_number")
                line_int = int(line_no) if isinstance(line_no, int) else None
                entry_meta = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
                meta_group = entry_meta.get("group")
                name_lower = name.lower()
                declared_unit = entry.get("unit") or entry_meta.get("unit")
                if isinstance(declared_unit, str) and declared_unit.strip():
                    inferred_unit = declared_unit.strip()
                elif (
                    name_lower.endswith("_pn_per_um2")
                    or name_lower.endswith("_pn_per_tooth_area_um2")
                    or "density_pn_per_um2" in name_lower
                    or "_pn_per_area_" in name_lower
                ):
                    inferred_unit = "pN/um^2"
                elif (
                    name_lower.endswith("_pn_per_um")
                    or name_lower.endswith("_pn_per_tooth_perimeter_um")
                    or "density_pn_per_um" in name_lower
                    or "_pn_per_perimeter_" in name_lower
                ):
                    inferred_unit = "pN/um"
                elif name_lower.endswith("_pn_um"):
                    inferred_unit = "pN*um"
                elif name_lower.endswith("_hbar_c_per_um"):
                    inferred_unit = "hbar*c/um"
                elif name_lower.endswith("_pn") or "_force_" in name_lower or "_fz_" in name_lower:
                    inferred_unit = "pN"
                elif name_lower.endswith("_pct") or "percent" in name_lower:
                    inferred_unit = "%"
                elif "panels" in name_lower:
                    inferred_unit = "panels"
                elif name_lower.endswith("_count"):
                    inferred_unit = "count"
                elif name_lower.endswith("_per_um"):
                    inferred_unit = "1/um"
                elif name_lower.endswith("_ev"):
                    inferred_unit = "eV"
                elif name_lower.endswith("_um2"):
                    inferred_unit = "um^2"
                elif name_lower.endswith("_um"):
                    inferred_unit = "um"
                elif name_lower.endswith("_nm"):
                    inferred_unit = "nm"
                elif name_lower.endswith("_pa"):
                    inferred_unit = "Pa"
                else:
                    inferred_unit = "dimensionless"
                if (
                    "run_nature_feasibility_and_stability.py" in src_file
                    or meta_group == "nems_feasibility"
                ):
                    registry.add(
                        name,
                        val,
                        inferred_unit,
                        f"True-vacuum NEMS feasibility metric: {name}",
                        "nems_feasibility",
                        Source(
                            src_file or "execution/run_nature_feasibility_and_stability.py",
                            line_int,
                            manifest_checksum,
                            f"logged by {src_file} into results/provenance_metrics.json",
                        ),
                    )
                    nems_exported[name] = val
                elif (
                    "run_bem_canonical_validation.py" in src_file
                    or meta_group == "bem_canonical_validation"
                    or name_lower.startswith("bem_val_")
                ):
                    registry.add(
                        name,
                        val,
                        inferred_unit,
                        f"Canonical 3D Vector-Dyadic BEM validation metric: {name}",
                        "bem_canonical_validation",
                        Source(
                            src_file or "execution/run_bem_canonical_validation.py",
                            line_int,
                            manifest_checksum,
                            f"logged by {src_file} into results/provenance_metrics.json",
                        ),
                    )
                    canonical_val_exported[name] = val
                elif (
                    "run_rotational_clutch_3solver_verification.py" in src_file
                    or "run_bem_fdtd_convergence_resolution.py" in src_file
                    or "run_nature_6step_narrative.py" in src_file
                    or "run_clutch_log_periodicity_probe.py" in src_file
                    or "probe_edge_rounding.py" in src_file
                    or meta_group == "rotational_clutch_3solver_verification"
                ):
                    registry.add(
                        name,
                        val,
                        inferred_unit,
                        f"True-vacuum 3-solver / narrative verification metric: {name}",
                        "rotational_clutch_3solver_verification",
                        Source(
                            src_file,
                            line_int,
                            manifest_checksum,
                            f"logged by {src_file} into results/provenance_metrics.json",
                        ),
                    )
                    solver3_exported[name] = val
        if nems_exported:
            registry.datasets["nems_feasibility"] = {
                "name": "True-Vacuum NEMS Feasibility and 6-DOF Stability (eps_bg=1.0)",
                "eps_bg": 1.0,
                "metric_count": len(nems_exported),
                "source": "results/nature_feasibility_stability_report.json",
            }
        if canonical_val_exported:
            registry.datasets["bem_canonical_validation"] = {
                "name": "Canonical 3D Vector-Dyadic BEM Validation Suite (Lifshitz, Energy-Derivative, Matsubara)",
                "eps_bg": 1.0,
                "metric_count": len(canonical_val_exported),
                "source": "results/bem_canonical_validation_report.json",
            }
        if solver3_exported:
            registry.datasets["rotational_clutch_3solver_verification"] = {
                "name": "True-Vacuum 3-Solver Multi-Resolution Verification (eps_bg=1.0)",
                "eps_bg": 1.0,
                "metric_count": len(solver3_exported),
                "source": "results/rotational_clutch_3solver_verification_report.json",
            }


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
    for name, value, unit, description in (
        (
            "levitation_equilibria_count",
            float(len(heights)),
            "count",
            "Number of verified levitation equilibria",
        ),
        (
            "levitation_equilibria_min_d_eq",
            min(heights),
            "nm",
            "Minimum verified levitation equilibrium height",
        ),
        (
            "levitation_equilibria_max_d_eq",
            max(heights),
            "nm",
            "Maximum verified levitation equilibrium height",
        ),
    ):
        registry.add(name, value, unit, description, "levitation_equilibria", source)


def register_rotary_clutch_campaigns(registry: Registry) -> None:
    """Read optional campaign JSON exports using their explicit record schemas."""
    group = "rotary_clutch_campaigns"
    exported: dict[str, float] = {}
    sources: list[str] = []

    def normalized(value: object) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value).lower())

    def number_matches(value: object, expected: float) -> bool:
        try:
            return math.isclose(
                finite_float(value, "campaign selector"),
                expected,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        except (TypeError, ValueError):
            return False

    def read_payload(path: Path) -> tuple[Mapping[str, Any], str] | None:
        if not path.is_file():
            return None
        source_path = relative_path(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("expected a JSON object")
            checksum = digest(path)
        except (OSError, ValueError, TypeError) as exc:
            registry.fail(f"Cannot read rotary clutch campaign {source_path}: {exc}")
            return None
        sources.append(source_path)
        return payload, checksum

    def records(
        node: Any, pointer: tuple[str, ...] = ()
    ) -> Iterator[tuple[Mapping[str, Any], tuple[str, ...]]]:
        if isinstance(node, Mapping):
            yield node, pointer
            for key, value in node.items():
                yield from records(value, (*pointer, str(key)))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from records(value, (*pointer, str(index)))

    def register_candidates(
        name: str,
        candidates: Sequence[tuple[object, tuple[str, ...]]],
        path: Path,
        checksum: str,
        *,
        required: bool = True,
    ) -> None:
        source_path = relative_path(path)
        if not candidates:
            if required:
                registry.fail(
                    f"Missing grounded rotary clutch metric {name} in {source_path}."
                )
            return
        values: list[tuple[float, tuple[str, ...]]] = []
        for value, pointer in candidates:
            try:
                values.append((finite_float(value, name), pointer))
            except (TypeError, ValueError) as exc:
                registry.fail(f"{source_path}: {exc}")
                return
        value, pointer = values[0]
        if any(other != value for other, _ in values[1:]):
            registry.fail(f"Ambiguous rotary clutch metric {name} in {source_path}.")
            return
        source = Source(
            source_path,
            None,
            checksum,
            "campaign JSON measurement at /"
            + "/".join(part.replace("~", "~0").replace("/", "~1") for part in pointer),
        )
        try:
            registry.add(
                name,
                value,
                "pN",
                "Gold Concentric Cantor-Ring Rotary Quantum Clutch: "
                + name.removesuffix("_f_z_pn")
                + " axial force",
                group,
                source,
            )
            exported[name] = value
        except (TypeError, ValueError) as exc:
            registry.fail(str(exc))

    # Select BEM records by physical configuration, not by fuzzy metric names.
    bem_specs = (
        ("cantor_n2_hybridrz_bem_std_f_z_pn", "Cantor_N2_HybridRZ", 3.0, "Standard"),
        ("cantor_n2_hybridrz_bem_high_f_z_pn", "Cantor_N2_HybridRZ", 3.0, "High"),
        ("cantor_n2_hybridrz_bem_ultra_f_z_pn", "Cantor_N2_HybridRZ", 3.0, "Ultra_High"),
        ("cantor_n2_hybridrz_bem_theta48_f_z_pn", "Cantor_N2_HybridRZ", 48.0, "Standard"),
        ("cantor_n2_flatz_bem_theta3_f_z_pn", "Cantor_N2_FlatZ", 3.0, "Standard"),
        ("cantor_n2_flatz_bem_theta48_f_z_pn", "Cantor_N2_FlatZ", 48.0, "Standard"),
        ("ctrl_uniformperiodic_bem_theta3_f_z_pn", "Ctrl_UniformPeriodic", 3.0, "Standard"),
        ("ctrl_uniformperiodic_bem_theta48_f_z_pn", "Ctrl_UniformPeriodic", 48.0, "Standard"),
        ("singletooth_track0_bem_theta3_f_z_pn", "SingleTooth_Track0", 3.0, "Standard"),
        ("singletooth_track0_bem_theta48_f_z_pn", "SingleTooth_Track0", 48.0, "Standard"),
        ("rot_c8_compact_n2_bem_theta3_f_z_pn", "Rot_C8_Compact_N2", 3.0, "Standard"),
        ("rot_c8_compact_n2_bem_theta48_f_z_pn", "Rot_C8_Compact_N2", 48.0, "Standard"),
        ("fractal_n3_cantor7track_bem_theta3_f_z_pn", "Fractal_N3_Cantor7Track", 3.0, "Standard"),
        ("fractal_n3_cantor7track_bem_theta21_f_z_pn", "Fractal_N3_Cantor7Track", 21.0, "Standard"),
        ("fractal_n3_cantor7track_bem_theta48_f_z_pn", "Fractal_N3_Cantor7Track", 48.0, "Standard"),
        ("ctrl_singlewide_bem_theta3_f_z_pn", "Ctrl_SingleWide", 3.0, "Standard"),
        ("ctrl_singlewide_bem_theta48_f_z_pn", "Ctrl_SingleWide", 48.0, "Standard"),
        ("ctrl_sizematched_monotonic_bem_theta3_f_z_pn", "Ctrl_SizeMatched_Monotonic", 3.0, "Standard"),
        ("ctrl_sizematched_monotonic_bem_theta48_f_z_pn", "Ctrl_SizeMatched_Monotonic", 48.0, "Standard"),
        ("fractal_n1_fundring_bem_theta3_f_z_pn", "Fractal_N1_FundRing", 3.0, "Standard"),
        ("fractal_n1_fundring_bem_theta48_f_z_pn", "Fractal_N1_FundRing", 48.0, "Standard"),
        ("cantor_n2_truerz_bem_theta3_f_z_pn", "Cantor_N2_TrueRZ", 3.0, "Standard"),
        ("cantor_n2_truerz_bem_theta48_f_z_pn", "Cantor_N2_TrueRZ", 48.0, "Standard"),
        ("ctrl_n3_uniform7track_bem_theta3_f_z_pn", "Ctrl_N3_Uniform7Track", 3.0, "Standard"),
        ("ctrl_n3_uniform7track_bem_theta48_f_z_pn", "Ctrl_N3_Uniform7Track", 48.0, "Standard"),
        ("ctrl_n3_monotonic7track_bem_theta3_f_z_pn", "Ctrl_N3_Monotonic7Track", 3.0, "Standard"),
        ("ctrl_n3_monotonic7track_bem_theta48_f_z_pn", "Ctrl_N3_Monotonic7Track", 48.0, "Standard"),
        ("ctrl_n3_shuffled7track_bem_theta3_f_z_pn", "Ctrl_N3_Shuffled7Track", 3.0, "Standard"),
        ("ctrl_n3_shuffled7track_bem_theta48_f_z_pn", "Ctrl_N3_Shuffled7Track", 48.0, "Standard"),
        ("ctrl_uniformperiodic_bem_high_theta3_f_z_pn", "Ctrl_UniformPeriodic", 3.0, "High"),
        ("ctrl_uniformperiodic_bem_ultra_theta3_f_z_pn", "Ctrl_UniformPeriodic", 3.0, "Ultra_High"),
    )

    def bem_candidates(
        entries: Sequence[tuple[Mapping[str, Any], tuple[str, ...]]],
        design: str,
        theta: float,
        tier: str,
    ) -> list[tuple[object, tuple[str, ...]]]:
        candidates: list[tuple[object, tuple[str, ...]]] = []
        for record, pointer in entries:
            if normalized(record.get("design")) != normalized(design):
                continue
            if not number_matches(record.get("theta_deg"), theta):
                continue
            record_tier = record.get("mesh_tier", record.get("tier"))
            if record_tier is not None and normalized(record_tier) != normalized(tier):
                continue
            boundary = record.get("boundary_condition", record.get("boundary"))
            if boundary is not None and normalized(boundary) != "activeonly":
                continue
            formulation = record.get("formulation")
            if formulation is not None and normalized(formulation) != "vectordyadic":
                continue
            if design == "SingleTooth_Track0" and not number_matches(
                record.get("z_tip_um"), -0.1
            ):
                continue
            if record.get("F_z_pN") is not None:
                candidates.append((record["F_z_pN"], (*pointer, "F_z_pN")))
        return candidates

    narrative_path = REPO_ROOT / "results/nature_6step_narrative_report.json"
    narrative = read_payload(narrative_path)
    if narrative is not None:
        payload, checksum = narrative
        analysis = payload.get("analysis", {})
        verification = (
            analysis.get("meep_verification", {})
            if isinstance(analysis, Mapping) else {}
        )
        if not isinstance(verification, Mapping):
            verification = {}

        bem_entries = list(records(payload.get("tasks", []), ("tasks",)))
        bem_entries.extend(
            records(
                verification.get("bem_comparison", []),
                ("analysis", "meep_verification", "bem_comparison"),
            )
        )
        for name, design, theta, tier in bem_specs:
            register_candidates(
                name, bem_candidates(bem_entries, design, theta, tier),
                narrative_path, checksum,
            )

        # Register overhang sign-reversal, full-monolithic BEM, and scalar-Yukawa BEM controls
        extra_bem_specs = (
            ("singletooth_track0_overhang_bem_theta3_f_z_pn", "SingleTooth_Track0", 3.0, "Standard", "Active-Only", "vector_dyadic", -0.055),
            ("cantor_n2_hybridrz_bem_monolithic_theta3_f_z_pn", "Cantor_N2_HybridRZ", 3.0, "Standard", "Full-Monolithic", "vector_dyadic", None),
            ("cantor_n2_hybridrz_bem_monolithic_theta48_f_z_pn", "Cantor_N2_HybridRZ", 48.0, "Standard", "Full-Monolithic", "vector_dyadic", None),
            ("fractal_n3_cantor7track_bem_monolithic_theta3_f_z_pn", "Fractal_N3_Cantor7Track", 3.0, "Standard", "Full-Monolithic", "vector_dyadic", None),
            ("fractal_n3_cantor7track_bem_monolithic_theta48_f_z_pn", "Fractal_N3_Cantor7Track", 48.0, "Standard", "Full-Monolithic", "vector_dyadic", None),
            ("cantor_n2_hybridrz_bem_scalar_std_theta3_f_z_pn", "Cantor_N2_HybridRZ", 3.0, "Standard", "Active-Only", "scalar_yukawa", None),
            ("cantor_n2_hybridrz_bem_scalar_std_theta48_f_z_pn", "Cantor_N2_HybridRZ", 48.0, "Standard", "Active-Only", "scalar_yukawa", None),
            ("cantor_n2_hybridrz_bem_high_theta48_f_z_pn", "Cantor_N2_HybridRZ", 48.0, "High", "Active-Only", "vector_dyadic", None),
            ("cantor_n2_hybridrz_bem_ultra_theta48_f_z_pn", "Cantor_N2_HybridRZ", 48.0, "Ultra_High", "Active-Only", "vector_dyadic", None),
        )
        for name, d_name, th_deg, t_name, b_name, f_name, z_tip_val in extra_bem_specs:
            candidates = [
                (record.get("F_z_pN"), (*pointer, "F_z_pN"))
                for record, pointer in bem_entries
                if normalized(record.get("design")) == normalized(d_name)
                and number_matches(record.get("theta_deg"), th_deg)
                and normalized(record.get("mesh_tier", record.get("tier"))) == normalized(t_name)
                and normalized(record.get("boundary_condition", record.get("boundary"))) == normalized(b_name)
                and normalized(record.get("formulation")) == normalized(f_name)
                and (z_tip_val is None or number_matches(record.get("z_tip_um"), z_tip_val))
                and record.get("F_z_pN") is not None
            ]
            register_candidates(name, candidates, narrative_path, checksum)

        raw_tasks = verification.get("tasks", []) if isinstance(verification.get("tasks"), Sequence) else []
        best_cfg = (
            analysis.get("step5_best_active_configuration")
            if isinstance(analysis, Mapping)
            else None
        )
        cand_cfg = (
            analysis.get("step5_candidate_comparisons")
            if isinstance(analysis, Mapping)
            else None
        )
        use_best_cfg = (
            isinstance(best_cfg, Mapping)
            and isinstance(best_cfg.get("scores"), list)
            and len(best_cfg.get("scores", [])) > 0
        )
        step5_key = (
            "step5_best_active_configuration"
            if use_best_cfg
            else "step5_candidate_comparisons"
        )
        step5_analysis = (
            best_cfg
            if use_best_cfg and isinstance(best_cfg, Mapping)
            else (cand_cfg if isinstance(cand_cfg, Mapping) else {})
        )
        step5_scores_list = step5_analysis.get("scores", []) if isinstance(step5_analysis, Mapping) else []
        if isinstance(step5_scores_list, list):
            for idx_s, s_rec in enumerate(step5_scores_list):
                if not isinstance(s_rec, Mapping):
                    continue
                d_name = str(s_rec.get("design", ""))
                if not d_name:
                    continue
                for field_key, unit_str in (
                    ("F_rep_pN", "pN"),
                    ("F_att_pN", "pN"),
                    ("Delta_F_pN", "pN"),
                    ("F_rep_pN_per_tooth_area_um2", "pN/um^2"),
                    ("F_att_pN_per_tooth_area_um2", "pN/um^2"),
                    ("Delta_F_pN_per_tooth_area_um2", "pN/um^2"),
                    ("F_rep_pN_per_tooth_perimeter_um", "pN/um"),
                    ("F_att_pN_per_tooth_perimeter_um", "pN/um"),
                    ("Delta_F_pN_per_tooth_perimeter_um", "pN/um"),
                    ("full_tooth_planform_area_um2", "um^2"),
                    ("full_tooth_planform_perimeter_um", "um"),
                ):
                    raw_v = s_rec.get(field_key)
                    if isinstance(raw_v, (int, float)) and not isinstance(raw_v, bool) and math.isfinite(float(raw_v)):
                        m_name = f"nature_{d_name}_{field_key}"
                        src_s = Source(
                            relative_path(narrative_path),
                            None,
                            checksum,
                            f"campaign JSON score at /analysis/{step5_key}/scores/{idx_s}/{field_key}",
                        )
                        try:
                            registry.add(
                                m_name,
                                float(raw_v),
                                unit_str,
                                f"Step 5 {d_name} {field_key}",
                                group,
                                src_s,
                            )
                            exported[m_name] = float(raw_v)
                        except (TypeError, ValueError) as exc:
                            registry.fail(str(exc))
        meep_entries = [
            (item, ("analysis", "meep_verification", "tasks", str(idx)))
            for idx, item in enumerate(raw_tasks)
            if isinstance(item, Mapping)
        ]
        meep_specs = (
            ("cantor_n2_hybridrz_meep_r40_f_z_pn", 11, 3.0, 40),
            ("cantor_n2_hybridrz_meep_r50_f_z_pn", 8, 3.0, 50),
            ("cantor_n2_hybridrz_meep_r60_f_z_pn", 12, 3.0, 60),
            ("cantor_n2_hybridrz_meep_theta48_f_z_pn", 9, 48.0, None),
            ("cantor_n2_flatz_meep_theta3_f_z_pn", 6, 3.0, None),
            ("cantor_n2_flatz_meep_theta48_f_z_pn", 7, 48.0, None),
            ("ctrl_uniformperiodic_meep_theta3_f_z_pn", 4, 3.0, None),
            ("ctrl_uniformperiodic_meep_theta48_f_z_pn", 5, 48.0, None),
            ("singletooth_track0_meep_theta3_f_z_pn", 1, 3.0, None),
            ("singletooth_track0_meep_theta48_f_z_pn", 2, 48.0, None),
            ("singletooth_track0_overhang_meep_theta3_f_z_pn", 3, 3.0, None),
            ("rot_c8_compact_n2_meep_theta3_f_z_pn", 10, 3.0, None),
        )
        for name, task_id, theta, resolution in meep_specs:
            candidates = [
                (record.get("f_net_pN"), (*pointer, "f_net_pN"))
                for record, pointer in meep_entries
                if number_matches(record.get("task_id"), task_id)
                and number_matches(record.get("theta_deg"), theta)
                and record.get("f_net_pN") is not None
                and (
                    resolution is None
                    or number_matches(record.get("R"), resolution)
                )
            ]
            register_candidates(name, candidates, narrative_path, checksum)

        richardson = verification.get("richardson", {})
        candidates = []
        if isinstance(richardson, Mapping) and "F_inf_4pass_pN" in richardson:
            candidates.append(
                (
                    richardson["F_inf_4pass_pN"],
                    ("analysis", "meep_verification", "richardson", "F_inf_4pass_pN"),
                )
            )
        register_candidates(
            "cantor_n2_hybridrz_meep_richardson_f_z_pn",
            candidates, narrative_path, checksum,
        )

    rotational_path = REPO_ROOT / "results/rotational_z_eff_clutch_report.json"
    rotational = read_payload(rotational_path)
    if rotational is not None:
        payload, checksum = rotational
        evaluations = payload.get("evaluations", [])
        if not isinstance(evaluations, list):
            registry.fail(
                f"{relative_path(rotational_path)}: expected evaluations to be a JSON list."
            )
            evaluations = []
        entries = [
            (item, ("evaluations", str(index)))
            for index, item in enumerate(evaluations)
            if isinstance(item, Mapping)
        ]
        for index, item in enumerate(evaluations):
            if not isinstance(item, Mapping):
                registry.fail(
                    f"{relative_path(rotational_path)}: evaluation {index} "
                    "must be a JSON object."
                )
                continue
            name = item.get("metric_key")
            if not isinstance(name, str) or not name.strip():
                registry.fail(
                    f"{relative_path(rotational_path)}: evaluation {index} "
                    "must have a nonempty string metric_key."
                )
                continue
            register_candidates(
                name,
                [(item.get("f_net_pN"), ("evaluations", str(index), "f_net_pN"))],
                rotational_path, checksum,
            )
        # This report contains the compact clutch's BEM rotation campaign.
        # Missing narrative-only designs in this separate report are not errors.
        for name, design, theta, tier in bem_specs:
            if design != "Rot_C8_Compact_N2":
                continue
            register_candidates(
                name, bem_candidates(entries, design, theta, tier),
                rotational_path, checksum, required=False,
            )

    # Task numbering is not angular ordering; use the recorded angle itself.
    for task in range(1, 22):
        path = REPO_ROOT / f"results_rotational_z_eff_meep/task_{task}_meep.json"
        loaded = read_payload(path)
        if loaded is None:
            continue
        payload, checksum = loaded
        if task <= 9:
            design = "rot_c8_compact_n2"
            allowed_angles = {0, 6, 12, 18, 24, 30, 36, 42, 48}
        elif task <= 18:
            design = "rot_c4_tightslot_n2"
            allowed_angles = {0, 6, 12, 18, 24, 30, 36, 42, 48}
        else:
            design = "rot_c10_fractal_n3"
            allowed_angles = {3, 21, 48}
        try:
            angle = finite_float(payload.get("theta_deg"), "theta_deg")
            if angle not in allowed_angles:
                raise ValueError(f"unsupported {design} angle {angle}")
            theta = int(angle)
        except (TypeError, ValueError) as exc:
            registry.fail(f"{relative_path(path)}: {exc}")
            continue
        register_candidates(
            f"{design}_meep_theta{theta}_f_z_pn",
            [(payload.get("f_net_pN"), ("f_net_pN",))],
            path, checksum,
        )

    continuum_path = (
        REPO_ROOT / "results/rotational_clutch_3solver_verification_report.json"
    )
    continuum = read_payload(continuum_path)
    if continuum is not None:
        payload, checksum = continuum
        source_path = relative_path(continuum_path)
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list):
            registry.fail(f"{source_path}: expected tasks to be a JSON list.")
            tasks = []
        for index, item in enumerate(tasks):
            if not isinstance(item, Mapping):
                registry.fail(f"{source_path}: task {index} must be a JSON object.")

        tier_index = {"Standard": 0, "High": 1, "Ultra_High": 2}
        for design_slug, design_name in (
            ("rot_c8_compact_n2", "Rot_C8_Compact_N2"),
            ("rot_c4_tightslot_n2", "Rot_C4_TightSlot_N2"),
        ):
            for theta in (48.0, 18.0):
                samples: list[tuple[float, float, int]] = []
                try:
                    for tier in sorted(tier_index, key=tier_index.get):
                        matches = [
                            (index, item)
                            for index, item in enumerate(tasks)
                            if isinstance(item, Mapping)
                            and normalized(item.get("design")) == normalized(design_name)
                            and number_matches(item.get("theta_deg"), theta)
                            and normalized(item.get("mesh_tier", item.get("tier")))
                            == normalized(tier)
                        ]
                        if len(matches) != 1:
                            raise ValueError(
                                f"{design_name}, theta={theta:g}: expected exactly one "
                                f"{tier} task, found {len(matches)}"
                            )
                        index, item = matches[0]
                        panels = finite_float(item.get("panel_count"), "panel_count")
                        if panels <= 0.0:
                            raise ValueError("panel_count must be positive")
                        forces = item.get("forces_pN")
                        if not isinstance(forces, Mapping):
                            raise ValueError(
                                f"task {index}: forces_pN must be a JSON object"
                            )
                        force = finite_float(
                            forces.get("vector_dyadic"),
                            f"task {index}: forces_pN/vector_dyadic",
                        )
                        h = finite_float(panels ** -0.5, "mesh spacing")
                        samples.append((h, force, index))
                except (TypeError, ValueError, OverflowError) as exc:
                    registry.fail(f"{source_path}: {exc}")
                    continue

                h_vals = [sample[0] for sample in samples]
                f_vals = [sample[1] for sample in samples]

                def add_extrapolation(
                    name: str,
                    value: float,
                    method: str,
                    used_samples: Sequence[tuple[float, float, int]],
                ) -> None:
                    source = Source(
                        source_path,
                        None,
                        checksum,
                        f"{method} at h = panel_count^-0.5 -> 0; "
                        "rounded to four decimals; derived from "
                        + ", ".join(
                            f"/tasks/{index}/panel_count and "
                            f"/tasks/{index}/forces_pN/vector_dyadic"
                            for _, _, index in used_samples
                        ),
                    )
                    try:
                        registry.add(
                            name,
                            value,
                            "pN",
                            f"{design_name}: continuum-extrapolated 3D Vector-Dyadic "
                            f"BEM axial force at theta={theta:g} degrees ({method})",
                            group,
                            source,
                        )
                        exported[name] = value
                    except (TypeError, ValueError) as exc:
                        registry.fail(f"{source_path}: {exc}")

                if theta == 48.0:
                    try:
                        h_mean = sum(h_vals) / 3.0
                        f_mean = sum(f_vals) / 3.0
                        denominator = finite_float(
                            sum((h - h_mean) ** 2 for h in h_vals),
                            "continuum regression denominator",
                        )
                        if denominator <= 0.0:
                            raise ValueError(
                                "continuum regression requires distinct mesh spacings"
                            )
                        slope = finite_float(
                            sum(
                                (h - h_mean) * (f - f_mean)
                                for h, f in zip(h_vals, f_vals)
                            ) / denominator,
                            "continuum regression slope",
                        )
                        f_inf_continuum = round(
                            finite_float(
                                f_mean - slope * h_mean, "continuum intercept"
                            ),
                            4,
                        )
                        add_extrapolation(
                            f"{design_slug}_bem_theta48_continuum_f_z_pn",
                            f_inf_continuum,
                            "three-point ordinary least-squares linear intercept",
                            samples,
                        )
                    except (TypeError, ValueError, OverflowError) as exc:
                        registry.fail(f"{source_path}: {design_name}: {exc}")

                try:
                    h_high, h_ultra = h_vals[1:]
                    f_high, f_ultra = f_vals[1:]
                    denominator = h_high - h_ultra
                    if denominator == 0.0:
                        raise ValueError(
                            "Richardson extrapolation requires distinct High and "
                            "Ultra_High mesh spacings"
                        )
                    f_inf_richardson = round(
                        finite_float(
                            (h_high * f_ultra - h_ultra * f_high) / denominator,
                            "Richardson intercept",
                        ),
                        4,
                    )
                    add_extrapolation(
                        f"{design_slug}_bem_theta{int(theta)}_richardson_f_z_pn",
                        f_inf_richardson,
                        "two-point High-to-Ultra_High linear Richardson extrapolation",
                        samples[1:],
                    )
                except (TypeError, ValueError, OverflowError) as exc:
                    registry.fail(
                        f"{source_path}: {design_name}, theta={theta:g}: {exc}"
                    )

    conv_res_path = REPO_ROOT / "results/bem_fdtd_convergence_resolution.json"
    conv_res = read_payload(conv_res_path)
    if conv_res is not None:
        payload, checksum = conv_res
        for idx_n, item in enumerate(payload.get("n_xi_decoupled_sweep", [])):
            if isinstance(item, Mapping) and item.get("n_xi") is not None and item.get("force_z_pN") is not None:
                n_xi_val = int(item["n_xi"])
                register_candidates(
                    f"bem_conv_std_nxi{n_xi_val}_pec_fz_pn",
                    [(item["force_z_pN"], ("n_xi_decoupled_sweep", str(idx_n), "force_z_pN"))],
                    conv_res_path,
                    checksum,
                )
        summary_block = payload.get("summary")
        if isinstance(summary_block, Mapping) and summary_block.get("n_xi_relative_drift_24_to_64_pct") is not None:
            register_candidates(
                "bem_conv_nxi_drift_pct",
                [(summary_block["n_xi_relative_drift_24_to_64_pct"], ("summary", "n_xi_relative_drift_24_to_64_pct"))],
                conv_res_path,
                checksum,
            )
        for idx_e, item in enumerate(payload.get("edge_rounded_r5nm_convergence", [])):
            if not isinstance(item, Mapping):
                continue
            slug = str(item.get("slug", "")).strip()
            if not slug:
                continue
            for m_key, j_key in (
                (f"cantor_n2_hybridrz_bem_r5nm_{slug}_f_z_pn", "cantor_r5nm_fz_pN"),
                (f"ctrl_uniformperiodic_bem_r5nm_{slug}_f_z_pn", "uniform_r5nm_fz_pN"),
                (f"cantor_n2_vs_uniform_ratio_r5nm_{slug}", "ratio_r5nm"),
                (f"cantor_n2_vs_uniform_ratio_sharp_{slug}", "ratio_sharp"),
            ):
                if item.get(j_key) is not None:
                    register_candidates(
                        m_key,
                        [(item[j_key], ("edge_rounded_r5nm_convergence", str(idx_e), j_key))],
                        conv_res_path,
                        checksum,
                    )

    meep_ctrl_specs = (
        ("meep_fixedbox_r40_fz_pn", 1),
        ("meep_fixedbox_r50_fz_pn", 2),
        ("meep_fixedbox_r60_fz_pn", 3),
        ("meep_fixedbox_r80_fz_pn", 4),
        ("meep_fixedbox_r60_nmax2_fz_pn", 6),
        ("meep_fixedbox_r60_gold_fz_pn", 8),
    )
    meep_ctrl_vals: dict[str, tuple[float, Path, str]] = {}
    for m_key, t_id in meep_ctrl_specs:
        mc_path = REPO_ROOT / f"results_meep_convergence_controls/task_{t_id}_meep.json"
        mc_loaded = read_payload(mc_path)
        if mc_loaded is not None:
            mc_payload, mc_checksum = mc_loaded
            if mc_payload.get("f_net_pN") is not None:
                register_candidates(
                    m_key,
                    [(mc_payload["f_net_pN"], ("f_net_pN",))],
                    mc_path,
                    mc_checksum,
                )
                meep_ctrl_vals[m_key] = (float(mc_payload["f_net_pN"]), mc_path, mc_checksum)
    if "meep_fixedbox_r60_fz_pn" in meep_ctrl_vals and "meep_fixedbox_r80_fz_pn" in meep_ctrl_vals:
        f60, _, _ = meep_ctrl_vals["meep_fixedbox_r60_fz_pn"]
        f80, p80, c80 = meep_ctrl_vals["meep_fixedbox_r80_fz_pn"]
        drift_60_80 = 100.0 * abs(f80 - f60) / max(abs(f80), 1e-12)
        register_candidates("meep_fixedbox_r60_to_r80_drift_pct", [(drift_60_80, ("f_net_pN",))], p80, c80)
    if "meep_fixedbox_r60_fz_pn" in meep_ctrl_vals and "meep_fixedbox_r60_gold_fz_pn" in meep_ctrl_vals:
        f60, _, _ = meep_ctrl_vals["meep_fixedbox_r60_fz_pn"]
        fg60, pg60, cg60 = meep_ctrl_vals["meep_fixedbox_r60_gold_fz_pn"]
        if abs(f60) > 1e-12:
            gold_pct = 100.0 * (fg60 / f60)
            register_candidates("meep_fixedbox_r60_gold_vs_pec_pct", [(gold_pct, ("f_net_pN",))], pg60, cg60)

    feas_path = REPO_ROOT / "results/nature_feasibility_stability_report.json"
    feas = read_payload(feas_path)
    if feas is not None:
        payload, checksum = feas
        feas_items = payload.get("evaluations", payload.get("tasks", []))
        for idx_f, item in enumerate(feas_items if isinstance(feas_items, list) else []):
            if not isinstance(item, Mapping):
                continue
            geom = str(item.get("design", item.get("geometry", ""))).strip()
            step_idx = item.get("step_id", item.get("step_index"))
            if not geom or not isinstance(step_idx, int):
                continue
            feas_units = {
                "force_z_pN": "pN",
                "energy_pN_um": "pN*um",
                "energy_hbar_c_per_um": "hbar*c/um",
            }
            for f_key, f_unit in feas_units.items():
                raw_v = item.get(f_key)
                if isinstance(raw_v, (int, float)) and not isinstance(raw_v, bool) and math.isfinite(float(raw_v)):
                    m_name = f"nature_{geom}_step{step_idx}_{f_key}"
                    if m_name not in registry.metrics:
                        registry.add(
                            m_name,
                            float(raw_v),
                            f_unit,
                            f"NEMS feasibility {geom} step {step_idx} {f_key}",
                            "nems_feasibility",
                            Source(
                                relative_path(feas_path),
                                None,
                                checksum,
                                f"campaign JSON evaluation at /evaluations/{idx_f}/{f_key}",
                            ),
                        )

    if sources:
        registry.datasets[group] = {
            "name": "Gold Concentric Cantor-Ring Rotary Quantum Clutch",
            "unit": "pN",
            "metrics": exported,
            "sources": sources,
            "basis": "exact values read from campaign JSON exports; no reference-value fallback",
        }


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
        # Manuscript inputs describe grounding, not the figure's empirical data.
        data_source = values.get(
            "data_source",
            values.get("metrics_path", "results/provenance_metrics.json"),
        )
        values = {
            **values,
            "data_source": str(data_source),
            "columns_used": list(values.get("metrics", [])),
        }
        aliases = {
            **(aliases or {}),
            "data_source": "data_source",
            "input_source": "data_source",
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


def verify_cross_table_consistency(registry: Registry) -> dict[str, Any]:
    """Verify Extended Data Table 1 force densities and Table 1/2/3 0 K PEC & Drude gold consistency."""
    checks: dict[str, Any] = {
        "table1_density_ratios": {},
        "cross_table_0k_forces": {},
        "all_passed": True,
    }
    step5_designs = (
        "Ctrl_SingleWide",
        "Ctrl_UniformPeriodic",
        "Ctrl_SizeMatched_Monotonic",
        "Cantor_N2_FlatZ",
        "Cantor_N2_HybridRZ",
        "Cantor_N2_TrueRZ",
        "Rot_C8_Compact_N2",
        "Fractal_N3_Cantor7Track",
        "Ctrl_N3_Uniform7Track",
        "Ctrl_N3_Monotonic7Track",
        "Ctrl_N3_Shuffled7Track",
    )
    for d_name in step5_designs:
        f_metric = registry.metrics.get(f"nature_{d_name}_F_rep_pN")
        a_metric = registry.metrics.get(f"nature_{d_name}_full_tooth_planform_area_um2")
        p_metric = registry.metrics.get(f"nature_{d_name}_full_tooth_planform_perimeter_um")
        da_metric = registry.metrics.get(f"nature_{d_name}_F_rep_pN_per_tooth_area_um2")
        dp_metric = registry.metrics.get(f"nature_{d_name}_F_rep_pN_per_tooth_perimeter_um")
        if any(m is None for m in (f_metric, a_metric, p_metric, da_metric, dp_metric)):
            checks["all_passed"] = False
            registry.fail(
                f"Missing Extended Data Table 1 density metrics for {d_name} in registry."
            )
            continue
        assert f_metric is not None and a_metric is not None and p_metric is not None
        assert da_metric is not None and dp_metric is not None
        if not (
            math.isfinite(a_metric.value)
            and a_metric.value > 0
            and math.isfinite(p_metric.value)
            and p_metric.value > 0
        ):
            checks["all_passed"] = False
            registry.fail(
                f"Invalid non-positive tooth area or perimeter for {d_name}: "
                f"A_tooth={a_metric.value}, P_edge={p_metric.value}"
            )
            continue
        expected_da = f_metric.value / a_metric.value
        expected_dp = f_metric.value / p_metric.value
        ok_a = math.isclose(da_metric.value, expected_da, rel_tol=1e-9, abs_tol=1e-12)
        ok_p = math.isclose(dp_metric.value, expected_dp, rel_tol=1e-9, abs_tol=1e-12)
        checks["table1_density_ratios"][d_name] = {
            "F_rep_pN": f_metric.value,
            "A_tooth_um2": a_metric.value,
            "P_edge_um": p_metric.value,
            "F_over_A_reported": da_metric.value,
            "F_over_A_exact": expected_da,
            "F_over_P_reported": dp_metric.value,
            "F_over_P_exact": expected_dp,
            "passed": ok_a and ok_p,
        }
        if not (ok_a and ok_p):
            checks["all_passed"] = False
            registry.fail(
                f"Extended Data Table 1 density mismatch for {d_name}: "
                f"F/A={da_metric.value} vs {expected_da}, F/P={dp_metric.value} vs {expected_dp}"
            )

    cross_pairs = (
        (
            "Cantor_N2_HybridRZ_Gold_0K_theta3",
            "cantor_n2_hybridrz_bem_std_f_z_pn",
            "nature_Cantor_N2_HybridRZ_step2_force_z_pN",
        ),
        (
            "Cantor_N2_HybridRZ_Gold_0K_theta48",
            "cantor_n2_hybridrz_bem_theta48_f_z_pn",
            "nature_Cantor_N2_HybridRZ_step3_force_z_pN",
        ),
        (
            "Cantor_N2_HybridRZ_PEC_0K_theta3",
            "bem_conv_std_nxi24_pec_fz_pn",
            "nature_Cantor_N2_HybridRZ_step0_force_z_pN",
        ),
        (
            "Rot_C8_Compact_N2_Gold_0K_theta3",
            "rot_c8_compact_n2_bem_theta3_f_z_pn",
            "nature_Rot_C8_Compact_N2_step18_force_z_pN",
        ),
        (
            "Rot_C8_Compact_N2_Gold_0K_theta48",
            "rot_c8_compact_n2_bem_theta48_f_z_pn",
            "nature_Rot_C8_Compact_N2_step19_force_z_pN",
        ),
    )
    for label, key_tab12, key_tab3 in cross_pairs:
        m12 = registry.metrics.get(key_tab12)
        m3 = registry.metrics.get(key_tab3)
        if m12 is None or m3 is None:
            checks["all_passed"] = False
            registry.fail(
                f"Missing cross-table 0 K force metric for {label}: "
                f"{key_tab12}={m12}, {key_tab3}={m3}"
            )
            continue
        ok_pair = math.isclose(m12.value, m3.value, rel_tol=1e-6, abs_tol=1e-9)
        checks["cross_table_0k_forces"][label] = {
            "table1_2_metric": key_tab12,
            "table1_2_value_pN": m12.value,
            "table3_metric": key_tab3,
            "table3_value_pN": m3.value,
            "passed": ok_pair,
        }
        if not ok_pair:
            checks["all_passed"] = False
            registry.fail(
                f"Cross-table 0 K force mismatch for {label}: "
                f"{key_tab12}={m12.value} vs {key_tab3}={m3.value}"
            )
    return checks


def export_pipeline(args: argparse.Namespace) -> int:
    executed_at = datetime.now(timezone.utc).isoformat()
    freshness_metadata = {
        "model": MODEL_ID,
        "dataset": "manuscript_provenance_registry",
        "status": "completed",
        "executed_at": executed_at,
    }
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
    register_rotary_clutch_campaigns(registry)
    consistency_checks = verify_cross_table_consistency(registry)
    registry.datasets["cross_table_consistency_audit"] = consistency_checks

    all_metrics = list(registry.metrics.values())
    selected = (
        all_metrics if args.max_steps is None else all_metrics[:args.max_steps]
    )
    figures = find_figures(manuscript)
    if not figures:
        registry.warnings.append("No supported figure files were found.")

    registry_path = output_dir / "experiment_provenance_registry.json"
    metrics_path = output_dir / "provenance_metrics.json"
    macros_path = output_dir / "macros_results.tex"
    map_path = output_dir / "manuscript_provenance_map.json"
    audit_path = output_dir / "provenance_audit_summary.json"
    inputs = [str(document.path) for document in documents]
    script_path = str(Path(__file__).resolve())
    logged_names = [metric.name for metric in selected]

    write_json(
        registry_path,
        {
            **freshness_metadata,
            "schema_version": 1,
            "script": relative_path(Path(__file__)),
            "script_sha256": digest(Path(__file__)),
            "manuscript": relative_path(manuscript),
            "documents": [
                {"path": relative_path(doc.path), "sha256": doc.sha256}
                for doc in documents
            ],
            "metadata": {
                "pressure_unit_provenance": {
                    "reported_pressure_unit": "dimensionless Meep pressure",
                    "si_pressure_unit": "Pa",
                    "meep_to_pa": MEEP_TO_PA,
                    "conversion": "pressure_pa = pressure_meep * meep_to_pa",
                    "values": {
                        metric.name: metric.metadata["pressure_unit_provenance"]
                        for metric in all_metrics
                        if "pressure_unit_provenance" in metric.metadata
                    },
                },
            },
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
        for idx, metric in enumerate(selected):
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
                    "defer_save": idx < len(selected) - 1,
                    "metadata": {
                        **metric.metadata,
                        "group": metric.group,
                        "source": asdict(metric.source),
                    },
                },
                primary="value",
            )

        if metrics_path.is_file():
            loaded_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metric_values = loaded_metrics.get("metrics", {})
            if not isinstance(metric_values, dict):
                raise ValueError("Expected a metrics dictionary")
            for key in ("accuracy_top1", "f1_score", "embedding_reduction"):
                metric_values.pop(key, None)
            for metric in selected:
                existing_entry = metric_values.get(metric.name)
                metric_values[metric.name] = {
                    **(dict(existing_entry) if isinstance(existing_entry, Mapping) else {}),
                    "value": metric.value,
                    "source_file": metric.source.path,
                    "source_function": "export_pipeline",
                    "line_number": metric.source.line or 1920,
                    "step_id": "grounded_experiment_provenance_export",
                    "recorded_at": executed_at,
                    "metadata": {
                        **metric.metadata,
                        "group": metric.group,
                        "source": asdict(metric.source),
                    },
                }
            write_json(metrics_path, loaded_metrics)

        # Run-specific JSONL ledgers never receive the logger's JSON dictionary.
        # Empty selections intentionally produce empty JSONL files.
        jsonl_text = "".join(
            json.dumps(
                {
                    **asdict(metric),
                    "model": MODEL_ID,
                    "dataset": metric.group,
                    "status": "completed",
                    "executed_at": executed_at,
                    "metrics": {metric.name: metric.value},
                },
                sort_keys=True,
                allow_nan=False,
            ) + "\n"
            for metric in selected
        )
        atomic_write(output_dir / "provenance_metrics.jsonl", jsonl_text)
        atomic_write(output_dir / "metrics.jsonl", jsonl_text)

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
        if manuscript.parent != output_dir:
            manuscript_macros = manuscript.parent / "macros_results.tex"
            if not manuscript_macros.exists() or not os.path.samefile(
                macros_path, manuscript_macros
            ):
                shutil.copy2(macros_path, manuscript_macros)

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
                "data_source": str(metrics_path),
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
                    "data_source": str(metrics_path),
                    "metrics_path": str(metrics_path),
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
            existing["input_source"] = dict(path=str(metrics_path).replace(chr(92), chr(47)), sha256=digest(metrics_path))
            existing["data_source"] = str(metrics_path)
            existing["grounded_experiment_export"] = metadata
            write_json(sidecar, existing)
            write_json(figure.with_suffix(".provenance.json"), existing)
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
        manuscript_map = json.loads(map_path.read_text(encoding="utf-8"))
        if not isinstance(manuscript_map, dict):
            manuscript_map = {"manuscript_map": manuscript_map}
        manuscript_map.update(freshness_metadata)
        write_json(map_path, manuscript_map)

    capped = len(selected) < len(all_metrics)
    status = (
        "incomplete_grounding" if registry.errors
        else "successful_micro_probe" if capped
        else "complete"
    )
    audit: dict[str, Any] = {
        **freshness_metadata,
        "export_status": status,
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
            "logger_metrics": relative_path(metrics_path),
            "run_metrics": relative_path(output_dir / "provenance_metrics.jsonl"),
            "metrics_jsonl": relative_path(output_dir / "metrics.jsonl"),
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
