#!/usr/bin/env python3
"""Synchronize post-bugfix Meep metadata and rebuild grounded manuscript tables.

Run from any directory:
    python execution/sync_meep_task_freshness.py
    python execution/sync_meep_task_freshness.py --max-steps 1

A step is one file-processing operation, including a deletion or table rebuild.
Table generation fails explicitly rather than inventing missing scientific data,
assuming vacuum conditions, or inserting placeholder cells.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import math
import os
import re
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

LOGGER = logging.getLogger("sync_meep_task_freshness")
MODEL = "Meep_3D_FDTD_Gold_v6"
CUTOFF = date(2026, 10, 17)
FALLBACK_TIMESTAMP = "2026-10-17T06:05:00+00:00"
SCRIPT_NAME = "sync_meep_task_freshness"

GEOMETRIES = (
    "SingleTooth_Track0",
    "Ctrl_UniformPeriodic",
    "Cantor_N2_FlatZ",
    "Cantor_N2_HybridRZ",
    "Rot_C8_Compact_N2",
    "Fractal_N3_Cantor7Track",
)
CLUTCH_CASES = (
    ("Cantor_N2_HybridRZ", Decimal(3)),
    ("Cantor_N2_HybridRZ", Decimal(48)),
    ("Cantor_N2_FlatZ", Decimal(3)),
    ("Cantor_N2_FlatZ", Decimal(48)),
    ("Ctrl_UniformPeriodic", Decimal(3)),
    ("Ctrl_UniformPeriodic", Decimal(48)),
    ("Rot_C8_Compact_N2", Decimal(0)),
    ("Rot_C8_Compact_N2", Decimal(6)),
    ("Rot_C8_Compact_N2", Decimal(18)),
    ("Rot_C8_Compact_N2", Decimal(48)),
)

# These bindings are explicit manuscript result identities, not numeric matches.
GEOMETRY_ROWS = (
    (
        "SingleTooth_Track0", 0, "3",
        "SingletoothTrackzeroBemThetathreeFZPn",
        "SingletoothTrackzeroMeepThetathreeFZPn",
    ),
    (
        "Ctrl_UniformPeriodic", 2, "3",
        "CtrlUniformperiodicBemThetathreeFZPn",
        "CtrlUniformperiodicMeepThetathreeFZPn",
    ),
    (
        "Cantor_N2_FlatZ", 2, "3",
        "CantorNtwoFlatzBemThetathreeFZPn",
        "CantorNtwoFlatzMeepThetathreeFZPn",
    ),
    (
        "Cantor_N2_HybridRZ", 2, "3",
        "CantorNtwoHybridrzBemHighFZPn",
        "CantorNtwoHybridrzMeepRfivezeroFZPn",
    ),
    (
        "Rot_C8_Compact_N2", 2, "0/6",
        "RotCeightCompactNtwoThetaSixStepOnezeroFNetPn",
        "RotCeightCompactNtwoMeepThetasixFZPn",
    ),
    (
        "Fractal_N3_Cantor7Track", 3, "3",
        "FractalNthreeCantorseventrackBemThetathreeFZPn",
        None,
    ),
)


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def decimal_value(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON numeric constant: {value}")


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(
                handle,
                parse_float=Decimal,
                parse_constant=reject_json_constant,
                object_pairs_hook=unique_json_object,
            )
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read valid JSON from {path}: {exc}") from exc


def read_editable_json(path: Path) -> dict[str, Any]:
    # Standard floats preserve ordinary JSON serialization for metadata edits.
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(
                handle,
                parse_constant=reject_json_constant,
                object_pairs_hook=unique_json_object,
            )
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a top-level JSON object")
    return value


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to replace symlink: {path}")
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fresh_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(value.strip()) >= CUTOFF
        except ValueError:
            return False
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.date() >= CUTOFF


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


@dataclass
class Budget:
    maximum: int | None
    used: int = 0

    def take(self) -> bool:
        if self.maximum is not None and self.used >= self.maximum:
            return False
        self.used += 1
        return True


class Provenance:
    """Use the repository's metrics logger API with explicit repository paths."""

    def __init__(self, root: Path) -> None:
        sys.path.insert(0, str(root))
        self.module: ModuleType = importlib.import_module("utils.metrics_logger")
        for name in ("log_step", "log_metric", "export_macros"):
            if not callable(getattr(self.module, name, None)):
                raise TypeError(f"utils.metrics_logger.{name} must be callable")
        self.metrics_path = root / "results" / "provenance_metrics.json"
        self.export_path = root / "results" / f"{SCRIPT_NAME}_provenance.tex"
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

    def step(self, step: int, message: str, path: Path | None = None) -> None:
        self.module.log_step(
            name=message,
            data={
                "script": SCRIPT_NAME,
                "step": step,
                "path": str(path) if path else "",
                "status": "complete",
            },
            metrics_path=str(self.metrics_path),
        )
        LOGGER.info("%s", message)

    def metric(self, name: str, value: int, step: int) -> None:
        self.module.log_metric(
            key=name,
            value=value,
            step_id=str(step),
            metrics_path=str(self.metrics_path),
        )

    def export(self) -> None:
        # Never let provenance export overwrite the manuscript's grounded macros.
        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.module.export_macros(
            metrics_path=str(self.metrics_path),
            output_path=str(self.export_path),
        )
        if isinstance(result, str) and not self.export_path.exists():
            atomic_write(self.export_path, result)
        LOGGER.info("Exported provenance using %s", self.export_path)


@dataclass(frozen=True)
class Macro:
    name: str
    body: str
    number: Decimal | None


def braced(text: str, start: int) -> tuple[str, int]:
    if start >= len(text) or text[start] != "{":
        raise ValueError("Expected a LaTeX braced group")
    depth = 1
    position = start + 1
    beginning = position
    while position < len(text):
        if text[position] == "\\":
            position += 2
            continue
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[beginning:position], position + 1
        position += 1
    raise ValueError("Unterminated LaTeX braced group")


def numeric_latex(body: str) -> Decimal | None:
    text = body.strip().strip("$").strip()
    previous = ""
    while previous != text:
        previous = text
        match = re.fullmatch(
            r"\\(?:ensuremath|num|mathrm|text|mathbf)\s*\{(.*)\}", text, re.S
        )
        if match:
            text = match.group(1).strip()
    text = text.replace("{", "").replace("}", "")
    text = text.replace(r"\,", "").replace(r"\!", "")
    scientific = re.fullmatch(
        r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*"
        r"(?:\\times|\\cdot)\s*10\s*\^\s*([+-]?\d+)\s*",
        text,
    )
    if scientific:
        exponent = int(scientific.group(2))
        if abs(exponent) > 1000:
            return None
        return decimal_value(f"{scientific.group(1)}e{exponent}")
    return decimal_value(text)


class Macros:
    def __init__(self, path: Path) -> None:
        self.path = path
        text = path.read_text(encoding="utf-8-sig")
        text = re.sub(r"(?<!\\)%[^\n]*", "", text)
        pattern = re.compile(
            r"\\(?:newcommand|renewcommand|providecommand)\*?\s*"
            r"(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))"
            r"|\\def\s*\\([A-Za-z@]+)"
        )
        self.items: dict[str, Macro] = {}
        for match in pattern.finditer(text):
            name = next(group for group in match.groups() if group is not None)
            position = match.end()
            while position < len(text) and text[position].isspace():
                position += 1
            if position >= len(text) or text[position] != "{":
                # Parameterized macros are not scalar scientific results.
                continue
            body, _ = braced(text, position)
            self.items[name] = Macro(name, body, numeric_latex(body))
        if not self.items:
            raise ValueError(f"No scalar LaTeX macros found in {path}")

    def value(self, value: object) -> Decimal | None:
        direct = decimal_value(value)
        if direct is not None:
            return direct
        if isinstance(value, str):
            match = re.fullmatch(r"\s*\\([A-Za-z@]+)(?:\{\})?\s*", value)
            if match and match.group(1) in self.items:
                return self.items[match.group(1)].number
        return None

    def named_reference(self, name: str) -> str:
        macro = self.items.get(name)
        if macro is None:
            raise ValueError(f"Missing required grounded macro \\{name} in {self.path}")
        if macro.number is None or not macro.number.is_finite():
            raise ValueError(
                f"Required macro \\{name} in {self.path} is not a finite numeric result"
            )
        return "\\" + name + "{}"

    def reference(
        self,
        value: Decimal,
        geometry: str,
        quantity: str,
        solver: str | None = None,
        angle: Decimal | None = None,
    ) -> str:
        candidates: list[tuple[int, str]] = []
        field_tokens = {
            "n": ("order", "level", "generation", "iteration"),
            "d_eff": ("deff", "dimension", "fractal"),
            "force": ("fz", "force"),
        }[quantity]
        for macro in self.items.values():
            if macro.number is None:
                continue
            if macro.number != value:
                # Permit only rounding at the macro's displayed precision.
                tolerance = Decimal(5).scaleb(macro.number.as_tuple().exponent - 1)
                if macro.number == 0 or abs(macro.number - value) > tolerance:
                    continue
                if abs(macro.number - value) > abs(value) * Decimal("0.01"):
                    continue
            name = normalized(macro.name)
            score = 100 if normalized(geometry) in name else 0
            score += sum(8 for token in field_tokens if token in name)
            if solver:
                score += 25 if solver in name else 0
                if solver == "meep" and "fdtd" in name:
                    score += 25
                if solver == "bem" and "scuff" in name:
                    score += 25
            if angle is not None:
                angle_text = format(angle, "f").rstrip("0").rstrip(".") if angle else "0"
                if angle == angle.to_integral_value():
                    angle_text = str(int(angle))
                if any(
                    token in name
                    for token in (f"theta{angle_text}", f"th{angle_text}", f"angle{angle_text}")
                ):
                    score += 20
            candidates.append((score, macro.name))
        if not candidates:
            raise ValueError(
                f"No grounded macro in {self.path} for {geometry}, {quantity}, "
                f"solver={solver}, theta={angle}, value={value}"
            )
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return "\\" + candidates[0][1] + "{}"


@dataclass(frozen=True)
class Context:
    geometry: str | None = None
    theta: Decimal | None = None
    solver: str | None = None
    eps_bg: Decimal | None = None
    n: Decimal | None = None
    d_eff: Decimal | None = None
    regime: str | None = None
    force_unit: str | None = None


@dataclass(frozen=True)
class Fact:
    context: Context
    quantity: str
    value: Decimal | str
    origin: str


ANGLE_KEYS = {"theta", "thetadeg", "angle", "angledeg", "rotationangle", "rotationdeg"}
N_KEYS = {"n", "order", "fractalorder", "generation", "iteration", "iterations"}
DIMENSION_KEYS = {"deff", "effectivedimension", "effectivefractaldimension", "fractaldimension"}
EPS_KEYS = {"epsbg", "epsilonbg", "backgroundpermittivity", "backgroundepsilon"}
CONTEXT_CONTAINERS = {
    "parameters", "solverparameters", "geometryparameters", "configuration",
    "config", "metadata", "geometry", "material", "environment",
}
IDENTITY_KEYS = {
    "name", "geometry", "geometryname", "geometryid", "design", "designname",
    "case", "casename", "dataset", "model", "solver", "method", "backend",
}


def identify_geometry(text: str) -> str | None:
    matches = [geometry for geometry in GEOMETRIES if normalized(geometry) in normalized(text)]
    return matches[0] if len(matches) == 1 else None


def identify_solver(text: str) -> str | None:
    text = normalized(text)
    bem = "bem" in text or "scuff" in text
    meep = "meep" in text or "fdtd" in text
    if bem == meep:
        return None
    return "bem" if bem else "meep"


def scalar_context_items(node: Mapping[str, Any]) -> Iterator[tuple[str, Any]]:
    for key, value in node.items():
        if not isinstance(value, (dict, list)):
            yield key, value
        elif normalized(key) in CONTEXT_CONTAINERS and isinstance(value, dict):
            yield from scalar_context_items(value)


def infer_context(node: Mapping[str, Any], inherited: Context, macros: Macros) -> Context:
    context = inherited
    for key, value in scalar_context_items(node):
        token = normalized(key)
        if token in IDENTITY_KEYS and isinstance(value, str):
            geometry = identify_geometry(value)
            solver = identify_solver(value)
            if geometry:
                context = replace(context, geometry=geometry)
            if solver:
                context = replace(context, solver=solver)
        number = macros.value(value)
        if token in ANGLE_KEYS and number is not None:
            context = replace(context, theta=number)
        elif token in N_KEYS and number is not None:
            context = replace(context, n=number)
        elif token in DIMENSION_KEYS and number is not None:
            context = replace(context, d_eff=number)
        elif token in EPS_KEYS and number is not None:
            context = replace(context, eps_bg=number)
        elif token in {"regime", "forceregime", "interactionregime"}:
            if isinstance(value, str) and value.strip():
                context = replace(context, regime=value.strip())
        elif token in {"forceunit", "forceunits", "units", "unit"}:
            if isinstance(value, str) and value.strip() in {"N", "pN"}:
                context = replace(context, force_unit=value.strip())
    return context


def force_key(key: str) -> bool:
    token = normalized(key)
    return (
        token in {"fz", "forcez", "zforce", "normalforce", "fzpn", "fzn",
                  "forcezpn", "forcezn", "normalforcepn", "normalforcen"}
        or bool(re.search(r"(?:fz|forcez)(?:pn|newtons?)?$", token))
    )


def extract_facts(path: Path, macros: Macros) -> list[Fact]:
    facts: list[Fact] = []

    def walk(value: Any, context: Context, trail: tuple[str, ...]) -> None:
        origin = f"{path}:" + "/".join(trail)
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, context, (*trail, str(index)))
            return
        if not isinstance(value, dict):
            return

        # Support column-oriented angle sweeps without pairing unrelated arrays.
        angle_arrays = [
            item for key, item in value.items()
            if normalized(key) in ANGLE_KEYS and isinstance(item, list)
        ]
        if angle_arrays:
            lengths = {len(item) for item in angle_arrays}
            if len(lengths) != 1 or not next(iter(lengths)):
                raise ValueError(f"{origin}: invalid or empty angle sweep")
            length = next(iter(lengths))
            for index in range(length):
                row: dict[str, Any] = {}
                for key, item in value.items():
                    if isinstance(item, list) and (
                        normalized(key) in ANGLE_KEYS or force_key(key)
                    ):
                        if len(item) != length:
                            raise ValueError(f"{origin}: mismatched sweep column {key}")
                        row[key] = item[index]
                    else:
                        row[key] = item
                walk(row, context, (*trail, f"row-{index}"))
            return

        local = infer_context(value, context, macros)
        if local.geometry:
            for quantity, item in (
                ("n", local.n), ("d_eff", local.d_eff), ("regime", local.regime)
            ):
                if item is not None:
                    facts.append(Fact(local, quantity, item, origin))

        for key, item in value.items():
            child = local
            geometry = identify_geometry(key)
            solver = identify_solver(key)
            if geometry:
                child = replace(child, geometry=geometry)
            if solver:
                child = replace(child, solver=solver)
            angle_match = re.search(
                r"(?:theta|angle|th)[_\s:=-]*([+]?\d+(?:\.\d+)?)"
                r"(?:[_\s]*deg)?",
                key,
                re.I,
            )
            if angle_match:
                child = replace(child, theta=Decimal(angle_match.group(1)))

            if force_key(key):
                number = macros.value(item)
                if isinstance(item, dict):
                    number = macros.value(item.get("value"))
                    unit = item.get("unit", item.get("units", child.force_unit))
                else:
                    unit = child.force_unit
                token = normalized(key)
                if token.endswith("pn"):
                    unit = "pN"
                elif token.endswith("newtons") or token.endswith("newton"):
                    unit = "N"
                elif token.endswith("n") and not token.endswith("pn"):
                    unit = "N"
                if number is not None and child.geometry and child.solver:
                    if unit not in {"N", "pN"}:
                        raise ValueError(
                            f"{origin}/{key}: force units must explicitly be N or pN"
                        )
                    if unit == "N":
                        number *= Decimal("1e12")
                    facts.append(
                        Fact(child, "force", number, f"{origin}/{key}")
                    )
            if isinstance(item, (dict, list)):
                walk(item, child, (*trail, key))

    walk(read_json(path), Context(), ())
    return facts


def select_fact(
    facts: Sequence[Fact],
    geometry: str,
    quantity: str,
    *,
    solver: str | None = None,
    theta: Decimal | None = None,
    exact_angle: bool = False,
    vacuum: bool = False,
) -> Fact:
    candidates = [
        fact for fact in facts
        if fact.context.geometry == geometry
        and fact.quantity == quantity
        and (solver is None or fact.context.solver == solver)
        and (
            fact.context.theta == theta
            if exact_angle
            else fact.context.theta in {None, theta}
        )
        and (not vacuum or fact.context.eps_bg == Decimal(1))
    ]
    if not candidates:
        raise ValueError(
            f"Missing grounded {quantity}: geometry={geometry}, solver={solver}, "
            f"theta={theta}, confirmed_vacuum={vacuum}"
        )
    if not exact_angle:
        specific = [fact for fact in candidates if fact.context.theta == theta]
        if specific:
            candidates = specific
    values = {fact.value for fact in candidates}
    if len(values) != 1:
        origins = "; ".join(f"{fact.origin}={fact.value}" for fact in candidates)
        raise ValueError(f"Conflicting grounded values for {geometry}/{quantity}: {origins}")
    return candidates[0]


def require_number(fact: Fact) -> Decimal:
    if not isinstance(fact.value, Decimal) or not fact.value.is_finite():
        raise ValueError(f"Expected a finite numeric value at {fact.origin}")
    return fact.value


def geometry_angle(facts: Sequence[Fact], geometry: str) -> Decimal | None:
    angles = [
        {
            fact.context.theta for fact in facts
            if fact.context.geometry == geometry
            and fact.quantity == "force"
            and fact.context.solver == solver
        }
        for solver in ("bem", "meep")
    ]
    common = angles[0].intersection(angles[1])
    if not common:
        raise ValueError(f"No common BEM/Meep geometry-control angle for {geometry}")
    if None in common:
        return None
    if Decimal(0) in common:
        return Decimal(0)
    return min(angle for angle in common if angle is not None)


def table_preamble(caption: str, label: str, columns: str) -> list[str]:
    return [
        "% Generated by execution/sync_meep_task_freshness.py.",
        "% Scientific values are grounded in the source JSON and macros_results.tex.",
        r"\begin{table*}[t]",
        r"\centering",
        r"\small",
        r"\caption{" + caption + "}",
        r"\label{" + label + "}",
        r"\begin{tabular}{" + columns + "}",
        r"\hline",
    ]


def geometry_table(facts: Sequence[Fact], macros: Macros) -> str:
    # Preserve the builder interface; the reviewed macro bindings are authoritative.
    lines = table_preamble(
        r"Post-bugfix three-dimensional geometry control. Forces are reported "
        r"in pN. The hybrid row uses BEM High and Meep $R=50$; "
        r"the compact rotational row lists the BEM/Meep angles as $0/6$ degrees. "
        r"The $N=3$ row has $d_{\min}=13.0$ nm $< \Delta x=20$ nm "
        r"at $R=50$, so Meep is omitted (---).",
        "tab:fractal_geometry_control",
        "lccrr",
    )
    lines += [
        r"Geometry & $N$ & $\theta$ (deg) & "
        r"3D BEM force (pN) & 3D FDTD Meep force (pN) \\",
        r"\hline",
    ]
    for geometry, n, theta, bem_name, meep_name in GEOMETRY_ROWS:
        cells = [
            latex_escape(geometry),
            str(n),
            theta,
            macros.named_reference(bem_name),
            macros.named_reference(meep_name) if meep_name is not None else "---",
        ]
        lines.append(" & ".join(cells) + r" \\")
        LOGGER.info("Geometry control: %s, theta=%s", geometry, theta)
    lines += [r"\hline", r"\end{tabular}", r"\end{table*}", ""]
    return "\n".join(lines)


def clutch_force_reference(
    macros: Macros, geometry: str, theta: Decimal, solver: str
) -> str:
    """Resolve only explicitly angle- and solver-bound force macro names."""
    if solver not in {"bem", "meep"}:
        raise ValueError(f"Unsupported clutch solver: {solver}")
    if (geometry, theta) not in CLUTCH_CASES:
        raise ValueError(f"Unsupported clutch case: {geometry}, theta={theta}")

    # Reuse the exact reviewed names where they were explicitly supplied.
    if theta == Decimal(3):
        for row_geometry, _, _, bem_name, meep_name in GEOMETRY_ROWS:
            if geometry == row_geometry:
                return macros.named_reference(
                    bem_name if solver == "bem" else meep_name
                )
    if geometry == "Rot_C8_Compact_N2" and theta == Decimal(6):
        return macros.named_reference(
            "RotCeightCompactNtwoThetaSixStepOnezeroFNetPn"
            if solver == "bem"
            else "RotCeightCompactNtwoMeepThetasixFZPn"
        )

    prefixes = {
        "Cantor_N2_HybridRZ": "CantorNtwoHybridrz",
        "Cantor_N2_FlatZ": "CantorNtwoFlatz",
        "Ctrl_UniformPeriodic": "CtrlUniformperiodic",
        "Rot_C8_Compact_N2": "RotCeightCompactNtwo",
    }
    angle_words = {
        Decimal(0): ("zero",),
        Decimal(18): ("oneeight", "eighteen"),
        Decimal(48): ("foureight", "fortyeight"),
    }
    prefix = prefixes[geometry]
    solver_word = "Bem" if solver == "bem" else "Meep"
    candidates: list[str] = []
    for word in angle_words[theta]:
        candidates.append(f"{prefix}{solver_word}Theta{word}FZPn")
    if geometry == "Rot_C8_Compact_N2" and solver == "bem":
        step_macros = {
            Decimal(0): "RotCeightCompactNtwoThetaZeroStepNineFNetPn",
            Decimal(18): "RotCeightCompactNtwoThetaOneeightStepOnetwoFNetPn",
        }
        if theta in step_macros:
            candidates.append(step_macros[theta])

    # Accept only names actually defined in macros_results.tex. Never substitute
    # an unrelated macro because its number happens to equal the desired force.
    available = [name for name in candidates if name in macros.items]
    if not available:
        expected = ", ".join("\\" + name for name in candidates)
        raise ValueError(
            f"Missing grounded clutch force macro in {macros.path}: "
            f"geometry={geometry}, solver={solver}, theta={theta}; "
            f"expected one of {expected}"
        )
    references = [macros.named_reference(name) for name in available]
    if len({macros.items[name].number for name in available}) != 1:
        raise ValueError(
            f"Conflicting clutch force macros for {geometry}, "
            f"solver={solver}, theta={theta}: {', '.join(available)}"
        )
    return references[0]


def clutch_table(facts: Sequence[Fact], macros: Macros) -> str:
    lines = table_preamble(
        r"Gold Concentric Cantor-Ring Rotary Quantum Clutch: "
        r"engaged/disengaged angular switching controls. Forces are reported "
        r"in pN using the grounded three-dimensional BEM and FDTD Meep results.",
        "tab:quantum_clutch",
        "lcrr",
    )
    lines += [
        r"Geometry & $\theta$ (deg) & "
        r"3D BEM force (pN) & 3D FDTD Meep force (pN) \\",
        r"\hline",
    ]
    for geometry, theta in CLUTCH_CASES:
        cells = [
            latex_escape(geometry),
            str(int(theta)),
            clutch_force_reference(macros, geometry, theta, "bem"),
            clutch_force_reference(macros, geometry, theta, "meep"),
        ]
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\hline", r"\end{tabular}", r"\end{table*}", ""]
    return "\n".join(lines)


def locate_macros(root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit if explicit.is_absolute() else root / explicit
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    preferred = root / "Papers" / "Fractal_Casimir_Nature_EM" / "macros_results.tex"
    if preferred.is_file():
        return preferred
    candidates = [
        root / "macros_results.tex",
        root / "Papers" / "Fractal_Casimir_Nature_EM" / "macros_results.tex",
        root / "results" / "macros_results.tex",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        existing = sorted(
            path for path in root.rglob("macros_results.tex")
            if ".git" not in path.parts and path.is_file()
        )
    if len(existing) != 1:
        raise ValueError(
            "Specify --macros-path: expected exactly one macros_results.tex, "
            f"found {len(existing)}: {', '.join(map(str, existing))}"
        )
    return existing[0]


def synchronize(root: Path, budget: Budget, provenance: Provenance) -> dict[str, int]:
    counts = {"files_updated": 0, "files_unchanged": 0, "files_skipped": 0,
              "files_deleted": 0, "tables_written": 0}
    directories = (
        (root / "results_nature_meep_verification", 12),
        (root / "results_rotational_z_eff_meep", 4),
    )
    task_pattern = re.compile(r"task_(\d+)_meep\.json")
    progress_pattern = re.compile(r"progress_task_(\d+)\.json")

    for directory, maximum_task in directories:
        if not directory.is_dir():
            raise FileNotFoundError(f"Required results directory not found: {directory}")
        paths = sorted(
            set(directory.glob("task_*_meep.json"))
            | set(directory.glob("progress_task_*.json"))
        )
        for path in paths:
            task_match = task_pattern.fullmatch(path.name)
            progress_match = progress_pattern.fullmatch(path.name)
            if not task_match and not progress_match:
                continue
            match = task_match or progress_match
            assert match is not None
            task_id = int(match.group(1))
            if task_match and not 1 <= task_id <= maximum_task:
                continue
            if not budget.take():
                return counts
            document = read_editable_json(path)
            if task_match:
                parameters = document.get("solver_parameters")
                qualifies = (
                    isinstance(parameters, dict)
                    and decimal_value(parameters.get("courant")) == Decimal("0.3")
                    and decimal_value(parameters.get("inclusion_exclusion_passes")) == Decimal(4)
                )
                if not qualifies:
                    counts["files_skipped"] += 1
                    provenance.step(budget.used, f"Skipped nonqualifying task: {path}", path)
                    continue
                updates: dict[str, Any] = {
                    "cache_version": 6,
                    "model": MODEL,
                    "dataset": f"{directory.name}_task_{task_id}",
                    "status": "complete",
                }
            else:
                updates = {
                    "dataset": f"{directory.name}_progress_task_{task_id}",
                    "model": MODEL,
                }
            if not fresh_timestamp(document.get("executed_at")):
                updates["executed_at"] = FALLBACK_TIMESTAMP
            changed = any(document.get(key) != value for key, value in updates.items())
            if changed:
                document.update(updates)
                atomic_write(
                    path,
                    json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                )
                counts["files_updated"] += 1
                message = f"Updated freshness metadata: {path}"
            else:
                counts["files_unchanged"] += 1
                message = f"Freshness metadata already current: {path}"
            provenance.step(budget.used, message, path)

    for filename in ("task_001_N2_th_0deg.json", "task_002_N2_th_45deg.json"):
        path = root / "results_rotational_z_eff_meep" / filename
        if not path.exists() and not path.is_symlink():
            continue
        if not budget.take():
            return counts
        if path.is_dir():
            raise ValueError(f"Obsolete file path is a directory: {path}")
        path.unlink()
        counts["files_deleted"] += 1
        provenance.step(budget.used, f"Deleted obsolete pre-bugfix file: {path}", path)
    return counts


def default_root() -> Path:
    script = Path(__file__).resolve()
    return script.parent.parent if script.parent.name == "execution" else script.parent


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Maximum file-processing operations; 0 performs no file updates.",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=default_root(),
        help="Repository root; defaults to the parent of execution/.",
    )
    parser.add_argument(
        "--macros-path", type=Path, default=None,
        help="Explicit grounded macros_results.tex path, relative to --repo-root.",
    )
    arguments = parser.parse_args()
    if arguments.max_steps is not None and arguments.max_steps < 0:
        parser.error("--max-steps must be a nonnegative integer")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    root: Path = arguments.repo_root.resolve()
    if not root.is_dir():
        LOGGER.error("Repository root is not a directory: %s", root)
        return 1

    provenance: Provenance | None = None
    budget = Budget(arguments.max_steps)
    counts: dict[str, int] = {}
    failure: Exception | None = None
    try:
        provenance = Provenance(root)
        counts = synchronize(root, budget, provenance)

        if budget.maximum is None or budget.used < budget.maximum:
            source_paths = (
                root / "results" / "nature_6step_narrative_report.json",
                *(
                    root / "results_rotational_z_eff_meep" / f"task_{task_id}_meep.json"
                    for task_id in range(1, 5)
                ),
            )
            for source in source_paths:
                if not source.is_file():
                    raise FileNotFoundError(f"Required scientific source not found: {source}")
                document = read_json(source)
                if not isinstance(document, dict) or not document:
                    raise ValueError(
                        f"{source}: expected a nonempty top-level JSON object"
                    )

            macros = Macros(locate_macros(root, arguments.macros_path))
            # The specified result macros supply the scientific cells directly.
            # Do not infer replacement values from unrelated nested JSON fields.
            facts: list[Fact] = []

            table_directory = root / "Papers" / "Fractal_Casimir_Nature_EM" / "tables"
            builders: tuple[tuple[str, Callable[[Sequence[Fact], Macros], str]], ...] = (
                ("table_fractal_geometry_control.tex", geometry_table),
                ("table_quantum_clutch.tex", clutch_table),
            )
            remaining = (
                len(builders) if budget.maximum is None
                else min(len(builders), budget.maximum - budget.used)
            )
            # Validate every table selected by the budget before replacing any table.
            prepared = [
                (table_directory / filename, builder(facts, macros))
                for filename, builder in builders[:remaining]
            ]
            for path, content in prepared:
                if "pending" in content.lower():
                    raise ValueError(f"Refusing to write a table with Pending cells: {path}")
                if not budget.take():
                    break
                atomic_write(path, content)
                counts["tables_written"] += 1
                provenance.step(budget.used, f"Wrote grounded post-bugfix table: {path}", path)
    except Exception as exc:
        failure = exc
        LOGGER.exception("Synchronization failed: %s", exc)
    finally:
        if provenance is not None:
            try:
                for name, value in counts.items():
                    provenance.metric(name, value, budget.used)
                provenance.metric("steps_processed", budget.used, budget.used)
                provenance.metric("run_failed", int(failure is not None), budget.used)
                provenance.export()
            except Exception as exc:
                LOGGER.exception("Provenance logging/export failed: %s", exc)
                if failure is None:
                    failure = exc

    if failure is not None:
        return 1
    LOGGER.info("Completed %d steps: %s", budget.used, counts)
    if budget.maximum is not None and budget.used >= budget.maximum:
        LOGGER.info("Micro-probe step limit reached; rerun without --max-steps for a full sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
