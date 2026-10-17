#!/usr/bin/env python3
"""Evaluate fixed-height, purely rotational stepped Cantor-ring clutches.

All repository SurfacePanel coordinates and areas are in um and um^2.
Forces are obtained exclusively from execution.casimir_bem_solver.

A small positive --max-steps (1 through 10) runs only the first task, with
that solver step budget and without plotting. --max-steps 0 runs the full
21-task campaign with n_xi=24 and produces JSON, Markdown, PNG and PDF reports.
"""

from __future__ import annotations

import argparse
import dataclasses
import inspect
import json
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution.casimir_bem_solver import (  # noqa: E402
    ClutchSurfaceMesh,
    Geometry,
    TrackElement,
    _azimuthal,
    _horizontal,
    _radial,
    run_bem_casimir_solver,
)
from execution.clutch_geometry_redesign import get_scoped_clutch_elements  # noqa: E402
from utils.metrics_logger import (  # noqa: E402
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)


Z_TIP_FIXED_UM = -0.100
H_TEETH_UM = 0.100
Z_ROTOR_TOP_UM = Z_TIP_FIXED_UM + H_TEETH_UM
Z_PAD_TOP_UM = -0.115
SECTOR_DEG = 90.0
SYMMETRY_ORDER = 4

OUTPUT_MODEL = "BEM_Meep_RotationalZEff"
OUTPUT_DATASET = "rotational_z_eff_clutch"
STALE_MEEP_LABEL = "STALE_PRE_BUGFIX_EXCLUDED"
MIN_MEEP_CACHE_VERSION = 6
MAX_MEEP_FORCE_PN = 1e6
MAX_MEEP_COUR = 0.35

DEFAULT_DESIGNS = (
    {
        "name": "Rot_C4_TightSlot_N2",
        "N": 2,
        "R_min": 0.30,
        "R_max": 1.35,
        "w1_ratio": 0.65,
        "min_tooth_w": 0.020,
        "h_teeth": 0.100,
        "t_membrane": 0.025,
        "t_landing_pad": 0.150,
        "tooth_arc_deg": 15.0,
        "aperture_arc_deg": 36.0,
        "angles": (0.0, 6.0, 12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 48.0),
    },
    {
        "name": "Rot_C8_Compact_N2",
        "N": 2,
        "R_min": 0.20,
        "R_max": 0.90,
        "w1_ratio": 0.45,
        "min_tooth_w": 0.020,
        "h_teeth": 0.100,
        "t_membrane": 0.025,
        "t_landing_pad": 0.150,
        "tooth_arc_deg": 15.0,
        "aperture_arc_deg": 36.0,
        "angles": (0.0, 6.0, 12.0, 18.0, 24.0, 30.0, 36.0, 42.0, 48.0),
    },
    {
        "name": "Rot_C10_Fractal_N3",
        "N": 3,
        "R_min": 0.30,
        "R_max": 1.65,
        "w1_ratio": 0.40,
        "min_tooth_w": 0.015,
        "h_teeth": 0.100,
        "t_membrane": 0.025,
        "t_landing_pad": 0.150,
        "tooth_arc_deg": 12.0,
        "aperture_arc_deg": 36.0,
        "angles": (3.0, 21.0, 48.0),
    },
)


class ConfigurationError(ValueError):
    """Invalid or unsupported geometry/API configuration."""


class EvaluationError(RuntimeError):
    """A solver result fails numerical validation."""


def output_metadata() -> dict[str, str]:
    """Fields required by freshness_filter.py for each emitted record."""
    return {
        "model": OUTPUT_MODEL,
        "dataset": OUTPUT_DATASET,
        "status": "completed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def normalized_name(name: str) -> str:
    return "".join(character.lower() for character in name if character.isalnum())


def object_fields(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {item.name: getattr(value, item.name) for item in dataclasses.fields(value)}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def lookup(source: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    indexed = {normalized_name(key): value for key, value in source.items()}
    for name in names:
        if normalized_name(name) in indexed:
            return indexed[normalized_name(name)]
    return default


def finite_float(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_, str, bytes, complex, np.complexfloating)):
        raise ConfigurationError(f"{name} must be a real numeric scalar.")
    if not np.isscalar(value):
        raise ConfigurationError(f"{name} must be a real numeric scalar.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ConfigurationError(f"{name} must be a real number.") from exc
    if not math.isfinite(result):
        raise ConfigurationError(f"{name} must be finite.")
    return result


def positive_int(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ConfigurationError(f"{name} must be an integer.")
    if int(value) < 1:
        raise ConfigurationError(f"{name} must be at least 1.")
    return int(value)


def meep_freshness_reasons(value: object) -> list[str]:
    """Reject legacy/unstable files before any Meep data can be reported.

    Check all occurrences, including parameters and records nested in reports.
    No unvalidated numeric values are copied into the freshness audit.
    """
    if not isinstance(value, Mapping):
        return ["invalid_json_record"]

    fields: dict[str, list[Any]] = {
        "cacheversion": [],
        "fnetpn": [],
        "cour": [],
    }

    def collect(node: object) -> None:
        if isinstance(node, Mapping):
            for key, item in node.items():
                normalized = normalized_name(str(key))
                if normalized in fields:
                    fields[normalized].append(item)
                collect(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                collect(item)

    collect(value)
    reasons = []
    if not fields["cacheversion"]:
        reasons.append("missing_cache_version")
    checks = (
        ("cacheversion", "cache_version", lambda number: number >= MIN_MEEP_CACHE_VERSION,
         "cache_version_below_6"),
        ("fnetpn", "f_net_pN", lambda number: abs(number) <= MAX_MEEP_FORCE_PN,
         "force_exceeds_stability_limit"),
        ("cour", "cour", lambda number: number <= MAX_MEEP_COUR,
         "cour_exceeds_stability_limit"),
    )
    for key, name, predicate, reason in checks:
        for item in fields[key]:
            try:
                number = finite_float(item, name)
            except ConfigurationError:
                invalid_reason = f"invalid_{name}"
                if invalid_reason not in reasons:
                    reasons.append(invalid_reason)
                continue
            if not predicate(number) and reason not in reasons:
                reasons.append(reason)
    return reasons


def scan_meep_results(directory: Path) -> list[dict[str, Any]]:
    """Audit Meep files without ingesting or rewriting stale solver results."""
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ConfigurationError(f"Meep results path is not a directory: {directory}.")

    audit = []
    for path in sorted(directory.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                contents = json.load(handle)
            reasons = meep_freshness_reasons(contents)
        except (OSError, UnicodeError, ValueError, RecursionError):
            reasons = ["unreadable_or_invalid_json"]
        excluded = bool(reasons)
        entry = {
            **output_metadata(),
            "path": str(path),
            "excluded": excluded,
            "freshness_status": STALE_MEEP_LABEL if excluded else "CACHE_V6_FRESH",
            "reasons": reasons,
        }
        audit.append(entry)
        if excluded:
            print(f"{STALE_MEEP_LABEL}: {path} ({', '.join(reasons)})",
                  file=sys.stderr)
    return audit


def invoke(function: Callable[..., Any], context: Mapping[str, Any]) -> Any:
    """Bind repository APIs by parameter name, never by guessed ordering."""
    signature = inspect.signature(function)
    indexed = {normalized_name(key): value for key, value in context.items()}
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    missing: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        key = normalized_name(parameter.name)
        if key in indexed:
            value = indexed[key]
        elif parameter.default is not inspect.Parameter.empty:
            if parameter.kind is not inspect.Parameter.POSITIONAL_ONLY:
                continue
            value = parameter.default
        else:
            missing.append(parameter.name)
            continue
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[parameter.name] = value
    if missing:
        raise ConfigurationError(
            f"Unsupported required parameters for "
            f"{getattr(function, '__qualname__', repr(function))}{signature}: "
            f"{', '.join(missing)}."
        )
    signature.bind(*positional, **keywords)
    return function(*positional, **keywords)


def constructor_defaults(constructor: Callable[..., Any]) -> dict[str, Any]:
    return {
        parameter.name: parameter.default
        for parameter in inspect.signature(constructor).parameters.values()
        if parameter.default is not inspect.Parameter.empty
        and parameter.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }


@dataclass(frozen=True, slots=True)
class ToothInterval:
    r_inner: float
    r_outer: float
    r_tooth_in: float
    r_tooth_out: float
    source: object


@dataclass(frozen=True, slots=True)
class ClutchSpec:
    R_min: float
    R_max: float
    aperture_arc_deg: float
    tooth_arc_deg: float
    t_membrane: float
    t_landing_pad: float
    elements: tuple[ToothInterval, ...]
    native_elements: tuple[TrackElement, ...]
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def z_pad_bot(self) -> float:
        return Z_PAD_TOP_UM - self.t_landing_pad

    @property
    def ring_intervals(self) -> tuple[tuple[float, float], ...]:
        rings = []
        left = self.R_min
        for element in self.elements:
            rings.append((left, element.r_inner))
            left = element.r_outer
        rings.append((left, self.R_max))
        return tuple(rings)


def validate_spec(spec: ClutchSpec) -> None:
    for name in (
        "R_min", "R_max", "aperture_arc_deg", "tooth_arc_deg",
        "t_membrane", "t_landing_pad",
    ):
        finite_float(getattr(spec, name), name)
    if not 0.0 < spec.R_min < spec.R_max:
        raise ConfigurationError("Require 0 < R_min < R_max.")
    if not 0.0 < spec.aperture_arc_deg < SECTOR_DEG:
        raise ConfigurationError("aperture_arc_deg must lie strictly in (0, 90).")
    if not 0.0 < spec.tooth_arc_deg < min(
        spec.aperture_arc_deg, SECTOR_DEG - spec.aperture_arc_deg
    ):
        raise ConfigurationError("The tooth must fit strictly inside both sectors.")
    if spec.t_membrane <= 0.0 or spec.t_landing_pad <= 0.0:
        raise ConfigurationError("Stator thicknesses must be positive.")
    if -spec.t_membrane <= Z_PAD_TOP_UM:
        raise ConfigurationError("The elevated membrane must lie above the pad.")
    if not spec.elements or len(spec.elements) != len(spec.native_elements):
        raise ConfigurationError("A nonempty matching slot collection is required.")
    left = spec.R_min
    for index, element in enumerate(spec.elements):
        for name in ("r_inner", "r_outer", "r_tooth_in", "r_tooth_out"):
            finite_float(getattr(element, name), f"elements[{index}].{name}")
        if not (
            left < element.r_inner < element.r_tooth_in
            < element.r_tooth_out < element.r_outer
        ):
            raise ConfigurationError(f"Invalid or overlapping slot {index}.")
        left = element.r_outer
    if not left < spec.R_max:
        raise ConfigurationError("The outer surviving ring must have positive width.")


def coerce_spec(value: object) -> ClutchSpec:
    if isinstance(value, ClutchSpec):
        validate_spec(value)
        return value
    supplied = object_fields(value)
    if not supplied:
        raise ConfigurationError("spec must be a mapping or geometry object.")
    merged = {**constructor_defaults(Geometry), **supplied}
    raw = lookup(merged, "elements", "track_elements", "clutch_elements")
    if raw is None or isinstance(raw, (str, bytes, Mapping)):
        raise ConfigurationError("elements must be a nonempty sequence.")
    try:
        raw = list(raw)
    except TypeError as exc:
        raise ConfigurationError("elements must be iterable.") from exc
    if not raw:
        raise ConfigurationError("A Cantor clutch requires at least one slot.")
    pairs = []
    for index, element in enumerate(raw):
        fields = object_fields(element)
        numbers = {}
        for name in ("r_inner", "r_outer", "r_tooth_in", "r_tooth_out"):
            numbers[name] = finite_float(
                lookup(fields, name, f"{name}_um"), f"elements[{index}].{name}"
            )
        native = element if isinstance(element, TrackElement) else invoke(
            TrackElement, {**merged, **fields, **numbers}
        )
        pairs.append((ToothInterval(**numbers, source=element), native))
    pairs.sort(key=lambda pair: pair[0].r_inner)
    spec = ClutchSpec(
        R_min=finite_float(lookup(merged, "R_min", "R_min_um"), "R_min"),
        R_max=finite_float(lookup(merged, "R_max", "R_max_um"), "R_max"),
        aperture_arc_deg=finite_float(
            lookup(merged, "aperture_arc_deg", default=36.0), "aperture_arc_deg"
        ),
        tooth_arc_deg=finite_float(
            lookup(merged, "tooth_arc_deg", default=15.0), "tooth_arc_deg"
        ),
        t_membrane=finite_float(
            lookup(merged, "t_membrane", "t_membrane_um", default=0.025),
            "t_membrane",
        ),
        t_landing_pad=finite_float(
            lookup(merged, "t_landing_pad", "t_landing_pad_um", default=0.150),
            "t_landing_pad",
        ),
        elements=tuple(pair[0] for pair in pairs),
        native_elements=tuple(pair[1] for pair in pairs),
        extra=merged,
    )
    validate_spec(spec)
    return spec


def geometry_context(spec: ClutchSpec, theta_deg: float) -> dict[str, Any]:
    return {
        **spec.extra,
        "R_min": spec.R_min,
        "R_max": spec.R_max,
        "elements": list(spec.native_elements),
        "track_elements": list(spec.native_elements),
        "clutch_elements": list(spec.native_elements),
        "N_rings": len(spec.elements) + 1,
        "n_teeth": len(spec.elements),
        "aperture_arc_deg": spec.aperture_arc_deg,
        "tooth_arc_deg": spec.tooth_arc_deg,
        "t_membrane": spec.t_membrane,
        "t_landing_pad": spec.t_landing_pad,
        "h_teeth": H_TEETH_UM,
        "z_tip": Z_TIP_FIXED_UM,
        "z_tip_um": Z_TIP_FIXED_UM,
        "z_recess": Z_PAD_TOP_UM,
        "z_pad_top": Z_PAD_TOP_UM,
        "z_pad_bot": spec.z_pad_bot,
        "theta_deg": theta_deg,
        "theta": theta_deg,
        "symmetry_order": SYMMETRY_ORDER,
        "n_sectors": SYMMETRY_ORDER,
    }


def tooth_segments(
    theta_deg: float, tooth_arc_deg: float
) -> tuple[tuple[float, float, bool, bool], ...]:
    theta = finite_float(theta_deg, "theta_deg")
    width = finite_float(tooth_arc_deg, "tooth_arc_deg")
    if not 0.0 < width < SECTOR_DEG:
        raise ConfigurationError("Invalid tooth angular width.")
    center = (15.0 + theta % SECTOR_DEG) % SECTOR_DEG
    low, high = center - width / 2.0, center + width / 2.0
    if low < 0.0:
        return ((0.0, high, False, True),
                (low + SECTOR_DEG, SECTOR_DEG, True, False))
    if high > SECTOR_DEG:
        return ((low, SECTOR_DEG, True, False),
                (0.0, high - SECTOR_DEG, False, True))
    return ((low, high, True, True),)


def repository_face(
    kind: str,
    *,
    r0: float,
    r1: float,
    phi0: float,
    phi1: float,
    z0: float,
    z1: float,
    sign: int,
    panel_type: str,
) -> Any:
    """Use native um-valued face constructors with angles in radians."""
    body = panel_type.split("_", 1)[0]
    context = {
        "r0": r0, "r1": r1, "r_inner": r0, "r_outer": r1,
        "r_min": r0, "r_max": r1,
        "p0": phi0, "p1": phi1, "phi0": phi0, "phi1": phi1,
        "phi_min": phi0, "phi_max": phi1,
        "z0": z0, "z1": z1, "z_bottom": z0, "z_top": z1,
        "sign": sign, "normal_sign": sign, "normal_direction": sign,
        "normal_z": sign, "normal_r": sign, "normal_phi": sign,
        "nz": sign, "nr": sign, "nphi": sign,
        "up": sign > 0, "outward": sign > 0,
        "body": body, "owner": body,
        "panel_type": panel_type, "kind": panel_type,
    }
    if kind == "horizontal":
        context["z"] = z0
        helper = _horizontal
    elif kind == "radial":
        context.update({"r": r0, "radius": r0})
        helper = _radial
    elif kind == "azimuthal":
        context.update({"phi": phi0, "p": phi0})
        helper = _azimuthal
    else:
        raise ConfigurationError(f"Unknown face kind: {kind}.")
    panel = invoke(helper, context)
    if getattr(panel, "panel_type", None) != panel_type:
        raise ConfigurationError(f"{helper.__name__} did not retain {panel_type}.")
    return panel


def build_rotational_stepped_clutch_mesh(
    spec: object,
    theta_deg: float,
    n_r: int = 2,
    n_phi_tooth: int = 3,
    n_phi_bridge: int = 3,
    n_z: int = 2,
) -> ClutchSurfaceMesh:
    """Build native rotor faces and a conforming occupied-cell stator boundary."""
    resolved = coerce_spec(spec)
    theta = finite_float(theta_deg, "theta_deg")
    nr = positive_int(n_r, "n_r")
    nt = positive_int(n_phi_tooth, "n_phi_tooth")
    nb = positive_int(n_phi_bridge, "n_phi_bridge")
    nz = positive_int(n_z, "n_z")
    context = geometry_context(resolved, theta)
    geometry = invoke(Geometry, context)
    for name, expected in (("z_tip", Z_TIP_FIXED_UM), ("h_teeth", H_TEETH_UM)):
        actual = lookup(object_fields(geometry), name, f"{name}_um")
        if actual is None or not math.isclose(
            finite_float(actual, f"Geometry.{name}"), expected,
            rel_tol=0.0, abs_tol=1e-14,
        ):
            raise ConfigurationError(f"Geometry must retain {name}={expected} um.")

    rotor: list[Any] = []
    stator: list[Any] = []

    def emit(target: list[Any], kind: str, bounds: tuple, sign: int, label: str) -> None:
        a, b, p, q, low, high = bounds
        target.append(repository_face(
            kind, r0=float(a), r1=float(b), phi0=float(p), phi1=float(q),
            z0=float(low), z1=float(high), sign=sign, panel_type=label,
        ))

    rotor_z = np.linspace(geometry.z_tip, geometry.z_tip + geometry.h_teeth, nz + 1)
    for element in resolved.elements:
        radii = np.linspace(element.r_tooth_in, element.r_tooth_out, nr + 1)
        for low_phi, high_phi, cap_low, cap_high in tooth_segments(
            theta, resolved.tooth_arc_deg
        ):
            low_phi = math.radians(low_phi)
            high_phi = math.radians(high_phi)
            angles = np.linspace(low_phi, high_phi, nt + 1)
            for i in range(nr):
                a, b = radii[i:i + 2]
                for j in range(nt):
                    p, q = angles[j:j + 2]
                    emit(rotor, "horizontal",
                         (a, b, p, q, rotor_z[0], rotor_z[0]), -1, "rotor_bottom")
                    emit(rotor, "horizontal",
                         (a, b, p, q, rotor_z[-1], rotor_z[-1]), 1, "rotor_top")
                for k in range(nz):
                    low, high = rotor_z[k:k + 2]
                    if cap_low:
                        emit(rotor, "azimuthal",
                             (a, b, low_phi, low_phi, low, high),
                             -1, "rotor_azimuthal_wall")
                    if cap_high:
                        emit(rotor, "azimuthal",
                             (a, b, high_phi, high_phi, low, high),
                             1, "rotor_azimuthal_wall")
            for j in range(nt):
                p, q = angles[j:j + 2]
                for k in range(nz):
                    low, high = rotor_z[k:k + 2]
                    emit(rotor, "radial",
                         (radii[0], radii[0], p, q, low, high),
                         -1, "rotor_radial_wall")
                    emit(rotor, "radial",
                         (radii[-1], radii[-1], p, q, low, high),
                         1, "rotor_radial_wall")

    # All surviving rings and slots share radial, angular and height nodes.
    boundaries = [resolved.R_min]
    for element in resolved.elements:
        boundaries.extend((element.r_inner, element.r_outer))
    boundaries.append(resolved.R_max)
    radial_nodes = [boundaries[0]]
    slot_flags = []
    for index, (a, b) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        radial_nodes.extend(np.linspace(a, b, nr + 1)[1:])
        slot_flags.extend([index % 2 == 1] * nr)
    radii = np.asarray(radial_nodes, dtype=float)
    angles = np.deg2rad(np.concatenate((
        np.linspace(0.0, resolved.aperture_arc_deg, nt + 1),
        np.linspace(resolved.aperture_arc_deg, SECTOR_DEG, nb + 1)[1:],
    )))
    pad_z = np.linspace(resolved.z_pad_bot, Z_PAD_TOP_UM, nz + 1)
    membrane_z = np.linspace(-resolved.t_membrane, 0.0, nz + 1)
    heights = np.concatenate((pad_z, membrane_z))
    ni, nj, nk = len(radii) - 1, len(angles) - 1, len(heights) - 1
    occupied = np.zeros((ni, nj, nk), dtype=bool)
    for i in range(ni):
        for j in range(nj):
            in_bridge = j >= nt
            for k in range(nk):
                z_mid = 0.5 * (heights[k] + heights[k + 1])
                in_elevated_membrane = -resolved.t_membrane <= z_mid <= 0.0
                in_recessed_pad = resolved.z_pad_bot <= z_mid <= Z_PAD_TOP_UM
                occupied[i, j, k] = (
                    in_recessed_pad if in_bridge
                    else ((not slot_flags[i]) and in_elevated_membrane)
                )

    def filled(i: int, j: int, k: int) -> bool:
        return (
            0 <= i < ni and 0 <= k < nk
            and bool(occupied[i, j % nj, k])
        )

    for i, j, k in np.argwhere(occupied):
        a, b = radii[i:i + 2]
        p, q = angles[j:j + 2]
        low, high = heights[k:k + 2]
        if not filled(i, j, k - 1):
            emit(stator, "horizontal", (a, b, p, q, low, low),
                 -1, "stator_bottom")
        if not filled(i, j, k + 1):
            emit(stator, "horizontal", (a, b, p, q, high, high),
                 1, "stator_top")
        if not filled(i - 1, j, k):
            emit(stator, "radial", (a, a, p, q, low, high),
                 -1, "stator_radial_wall")
        if not filled(i + 1, j, k):
            emit(stator, "radial", (b, b, p, q, low, high),
                 1, "stator_radial_wall")
        if not filled(i, j - 1, k):
            emit(stator, "azimuthal", (a, b, p, p, low, high),
                 -1, "stator_azimuthal_wall")
        if not filled(i, j + 1, k):
            emit(stator, "azimuthal", (a, b, q, q, low, high),
                 1, "stator_azimuthal_wall")

    supplied_parameters = lookup(resolved.extra, "parameters", default={})
    supplied_config = lookup(resolved.extra, "config", default={})
    if not isinstance(supplied_parameters, Mapping):
        raise ConfigurationError("parameters must be a mapping.")
    if not isinstance(supplied_config, Mapping):
        raise ConfigurationError("config must be a mapping.")
    elements = [dataclasses.asdict(e) for e in resolved.native_elements]
    parameters = {
        **supplied_parameters,
        **context,
        "material": lookup(
            resolved.extra, "material",
            default=lookup(supplied_parameters, "material", default="Gold"),
        ),
        "elements": elements,
        "track_elements": elements,
        "clutch_elements": elements,
    }
    config = {**supplied_config, **parameters}
    panel_resolution = {
        "n_r": nr, "n_phi_tooth": nt, "n_phi_bridge": nb, "n_z": nz,
    }
    return ClutchSurfaceMesh(
        tuple(rotor), tuple(stator), geometry, parameters, config, panel_resolution
    )


def collision_certificate(spec: ClutchSpec) -> dict[str, Any]:
    validate_spec(spec)
    radial = min(
        min(e.r_tooth_in - e.r_inner, e.r_outer - e.r_tooth_out)
        for e in spec.elements
    )
    return {
        "collision_free_for_all_angles": True,
        "minimum_elevated_rib_radial_clearance_um": radial,
        "landing_pad_vertical_clearance_um": Z_TIP_FIXED_UM - Z_PAD_TOP_UM,
        "z_tip_fixed_um": Z_TIP_FIXED_UM,
        "z_rotor_top_um": Z_ROTOR_TOP_UM,
        "z_pad_top_um": Z_PAD_TOP_UM,
        "z_pad_bottom_um": spec.z_pad_bot,
        "qualification": "Analytical curved-geometry clearance, not mesh convergence.",
    }


def angular_state(spec: ClutchSpec, theta_deg: float) -> dict[str, Any]:
    validate_spec(spec)
    width = sum(
        max(0.0, min(high, spec.aperture_arc_deg) - max(low, 0.0))
        for low, high, _, _ in tooth_segments(theta_deg, spec.tooth_arc_deg)
    )
    fraction = min(1.0, max(0.0, width / spec.tooth_arc_deg))
    if math.isclose(fraction, 1.0, rel_tol=0.0, abs_tol=1e-12):
        state, effective = "aperture", Z_TIP_FIXED_UM
    elif math.isclose(fraction, 0.0, rel_tol=0.0, abs_tol=1e-12):
        state, effective = "landing_pad", Z_TIP_FIXED_UM - Z_PAD_TOP_UM
    else:
        state, effective = "straddling", None
    return {
        "state": state,
        "aperture_fraction": fraction,
        "landing_pad_fraction": 1.0 - fraction,
        "delta_z_eff_um": effective,
        "z_tip_fixed_um": Z_TIP_FIXED_UM,
    }


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        result = float(value)
        if not math.isfinite(result):
            raise EvaluationError("A solver/provenance value is non-finite.")
        return result
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    fields = object_fields(value)
    return json_safe(fields) if fields else repr(value)


def extract_fz(result: object) -> float:
    fields = object_fields(result)
    force = lookup(
        fields, "f_net_N", "F_z_N", "Fz_N", "F_z", "Fz", "force_z_N", "force_z",
        "rotor_force_z_N", "rotor_Fz_N", "F_total_N", "F_total",
    )
    if force is None:
        vector = lookup(fields, "force_N", "force", "rotor_force_N")
        if vector is not None:
            try:
                array = np.asarray(vector, dtype=np.float64)
            except (TypeError, ValueError, OverflowError) as exc:
                raise EvaluationError("Invalid solver force vector.") from exc
            if array.shape == (3,) and np.isfinite(array).all():
                force = array[2]
            else:
                raise EvaluationError("Expected three finite force components.")
    if force is None:
        nested = lookup(fields, "metrics", "result", "results")
        if nested is not None and nested is not result:
            return extract_fz(nested)
        raise EvaluationError("Cannot identify signed rotor F_z in the BEM result.")
    try:
        return finite_float(force, "solver F_z")
    except ConfigurationError as exc:
        raise EvaluationError(str(exc)) from exc


def resolve_design(explicit: Mapping[str, Any], scope: str) -> ClutchSpec:
    data = dict(explicit)
    if lookup(data, "elements", "track_elements", "clutch_elements") is None:
        data["elements"] = get_scoped_clutch_elements(
            N=int(data["N"]),
            R_min=float(data["R_min"]),
            R_max=float(data["R_max"]),
            w1_ratio=float(data["w1_ratio"]),
            min_tooth_w=float(data["min_tooth_w"]),
        )
    return coerce_spec(data)


def load_spec(args: argparse.Namespace) -> ClutchSpec:
    if args.spec_json is None:
        return resolve_design(DEFAULT_DESIGNS[0], args.scope)
    with args.spec_json.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ConfigurationError("--spec-json must contain a JSON object.")
    return resolve_design(loaded, args.scope)


def choose_device(requested: str) -> str:
    try:
        import torch
    except ImportError:
        if requested == "cuda":
            raise ConfigurationError("CUDA was requested, but PyTorch is absent.")
        return "cpu"
    available = torch.cuda.is_available()
    if requested == "cuda" and not available:
        raise ConfigurationError("CUDA was requested but is unavailable.")
    return ("cuda" if available else "cpu") if requested == "auto" else requested


def atomic_json_write(path: Path, contents: object) -> None:
    if not isinstance(contents, Mapping):
        raise ConfigurationError("Output JSON must be a record mapping.")
    payload = {**contents, **output_metadata()}
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(json_safe(payload), handle, indent=2, allow_nan=False)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def logger_context(output_dir: Path, provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **output_metadata(),
        "solver": "execution.casimir_bem_solver.run_bem_casimir_solver",
        "solver_name": "run_bem_casimir_solver",
        "name": "rotational_stepped_cantor_clutch",
        "run_name": "rotational_stepped_cantor_clutch",
        "provenance": dict(provenance), "metadata": dict(provenance),
        "details": dict(provenance),
        "output_dir": output_dir, "out_dir": output_dir,
        "path": output_dir / "metrics.json",
        "source": str(Path(__file__).resolve()),
        "script": str(Path(__file__).resolve()),
        "method": "BEM",
        "description": "Fixed-height purely rotational stepped Cantor clutch",
    }


def make_plot(
    records: Sequence[Mapping[str, Any]],
    output_dir: Path,
    logging_context: Mapping[str, Any],
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    metric_keys_list = [record["metric_key"] for record in records]
    figure, axes = plt.subplots(2, 1, sharex=True, figsize=(8, 6))
    try:
        for name in dict.fromkeys(record["design"] for record in records):
            ordered = sorted(
                (record for record in records if record["design"] == name),
                key=lambda record: record["theta_deg"],
            )
            angles = [record["theta_deg"] for record in ordered]
            axes[0].plot(angles, [r["F_z_N"] for r in ordered], "o-", label=name)
            axes[1].plot(
                angles, [r["landing_pad_fraction"] for r in ordered], "o-",
                label=name,
            )
        axes[0].axhline(0.0, color="black", linewidth=0.8)
        axes[0].set_ylabel("Rotor $F_z$ (N)")
        axes[0].legend(fontsize="small")
        axes[1].set_ylabel("Landing-pad overlap")
        axes[1].set_xlabel(r"Rotation $\theta$ (degrees)")
        axes[1].set_ylim(-0.05, 1.05)
        for axis in axes:
            axis.grid(alpha=0.25)
        figure.suptitle("Pure rotation; rotor tip fixed at −100 nm")
        figure.tight_layout()
        for suffix in ("png", "pdf"):
            path = output_dir / f"fig_rotational_z_eff_clutch.{suffix}"
            figure.savefig(path, dpi=180)
            save_plot_provenance(
                str(path),
                str(PROJECT_ROOT / "results" / "provenance_metrics.json"),
                metric_keys_list,
                solver_name="bem",
                solver_parameters={
                    "formulation": "vector_dyadic",
                    **output_metadata(),
                },
            )
    finally:
        plt.close(figure)


def write_markdown(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# Rotational stepped Cantor clutch",
        "",
        "Rotor tip: −0.100 um; rotor top: 0.000 um; pad top: −0.115 um.",
        "Panel coordinates and areas use um and um². Forces are signed BEM results.",
        "",
        "Legacy or unstable Meep files are marked "
        f"`{STALE_MEEP_LABEL}` in the JSON freshness audit and excluded; "
        "their force values are not reported.",
        "",
        "| Design | Angle (deg) | State | F_z (N) |",
        "|---|---:|---|---:|",
    ]
    for record in records:
        lines.append(
            f"| {record['design']} | {record['theta_deg']:.6g} | "
            f"{record['state']} | {record['F_z_N']:+.9e} |"
        )
    lines.extend((
        "",
        "Force signs are sampled numerical results, not an all-angle or "
        "mesh/frequency-convergence proof.",
        "",
    ))
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text("\n".join(lines), encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-json", type=Path)
    parser.add_argument("--scope", default="concentric_cantor")
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--theta-deg", type=float, nargs="+")
    parser.add_argument("--n-r", type=int, default=2)
    parser.add_argument("--n-phi-tooth", type=int, default=3)
    parser.add_argument("--n-phi-bridge", type=int, default=3)
    parser.add_argument("--n-z", type=int, default=2)
    parser.add_argument("--n-kappa", type=int)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--require-force-switch", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_steps < 0:
        raise ConfigurationError("max_steps must be nonnegative.")
    for name in ("n_r", "n_phi_tooth", "n_phi_bridge", "n_z"):
        positive_int(getattr(args, name), name)
    if args.n_kappa is not None:
        positive_int(args.n_kappa, "n_kappa")
    explicit_angles = None
    if args.theta_deg is not None:
        explicit_angles = tuple(finite_float(v, "theta_deg") for v in args.theta_deg)
        if not explicit_angles:
            raise ConfigurationError("At least one angle is required.")

    quick = 0 < args.max_steps <= 10
    if args.spec_json is not None:
        spec = load_spec(args)
        designs = [(
            str(lookup(spec.extra, "name", default="custom")),
            spec,
            explicit_angles if explicit_angles is not None else DEFAULT_DESIGNS[0]["angles"],
        )]
    else:
        selected = DEFAULT_DESIGNS[:1] if quick else DEFAULT_DESIGNS
        designs = [
            (
                design["name"],
                resolve_design(design, args.scope),
                explicit_angles if explicit_angles is not None else design["angles"],
            )
            for design in selected
        ]
    tasks = [(name, spec, theta) for name, spec, angles in designs for theta in angles]
    if quick:
        tasks = tasks[:1]
    if not tasks:
        raise ConfigurationError("At least one evaluation task is required.")

    device = choose_device(args.device)
    n_xi = args.n_kappa if args.n_kappa is not None else 24
    args.output_dir.mkdir(parents=True, exist_ok=True)
    meep_audit = scan_meep_results(PROJECT_ROOT / "results_rotational_z_eff_meep")
    provenance = {
        **output_metadata(),
        "script": str(Path(__file__).resolve()),
        "solver": "execution.casimir_bem_solver.run_bem_casimir_solver",
        "formulation": "vector_dyadic",
        "device": device,
        "geometry_units": "um", "panel_units": "um", "panel_area_units": "um^2",
        "force_units": "N",
        "physical_rotor_tip_um": Z_TIP_FIXED_UM,
        "physical_rotor_top_um": Z_ROTOR_TOP_UM,
        "vertical_motion_um": 0.0,
        "symmetry_order": SYMMETRY_ORDER,
        "force_signs_prescribed": False,
        "solver_max_steps": args.max_steps,
        "n_xi": n_xi,
        "meep_freshness_audit": meep_audit,
        "meep_freshness_policy": {
            "minimum_cache_version": MIN_MEEP_CACHE_VERSION,
            "maximum_abs_f_net_pN": MAX_MEEP_FORCE_PN,
            "maximum_cour": MAX_MEEP_COUR,
            "excluded_label": STALE_MEEP_LABEL,
            "meep_forces_used_in_bem_evaluation": False,
        },
        "collision_certificates": {
            name: collision_certificate(spec) for name, spec, _ in designs
        },
        "arguments": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
    }
    logging = logger_context(args.output_dir, provenance)
    set_solver_provenance("bem", {
        "formulation": "vector_dyadic", "n_xi": n_xi, **output_metadata(),
    })
    records = []
    report_path = args.output_dir / "rotational_z_eff_clutch_report.json"
    for step, (name, spec, theta) in enumerate(tasks):
        mesh = build_rotational_stepped_clutch_mesh(
            spec, theta, args.n_r, args.n_phi_tooth, args.n_phi_bridge, args.n_z
        )
        # Carry schema fields into solver-generated metric/CSV provenance too.
        mesh.parameters.update(output_metadata())
        task_id = f"{name}_theta_{theta:.9g}_step_{step}"
        step_id = task_id
        metric_key = f"{task_id}_f_net_pN"
        result = run_bem_casimir_solver(
            mesh.parameters,
            n_r=args.n_r,
            n_phi_tooth=args.n_phi_tooth,
            n_phi_bridge=args.n_phi_bridge,
            n_z=args.n_z,
            n_xi=n_xi,
            max_steps=args.max_steps,
            device=device,
            task_id=task_id,
            mesh=mesh,
            record_metrics=True,
            formulation="vector_dyadic",
        )
        force = extract_fz(result)
        if not isinstance(result, Mapping):
            raise EvaluationError("Expected a BEM result mapping.")
        try:
            force_pn = finite_float(result["f_net_pN"], "solver f_net_pN")
            force_fn = finite_float(result["f_net_fN"], "solver f_net_fN")
            diagnostics = result["diagnostics"]
            if not isinstance(diagnostics, Mapping):
                raise EvaluationError("Expected a BEM diagnostics mapping.")
            metadata = output_metadata()
            solver_parameters = result["solver_parameters"]
            if not isinstance(solver_parameters, Mapping):
                raise EvaluationError("Expected a BEM solver_parameters mapping.")
            solver_parameters = {**solver_parameters, **metadata}
            record = {
                **metadata,
                "step": step,
                "step_id": step_id,
                "task_id": task_id,
                "metric_key": metric_key,
                "design": name,
                "theta_deg": theta,
                "F_z_N": force,
                "f_net_N": finite_float(result["f_net_N"], "solver f_net_N"),
                "f_net_pN": force_pn,
                "f_net_fN": force_fn,
                "F_net": json_safe(result["F_net"]),
                "F_bottom": json_safe(diagnostics["F_bottom"]),
                "F_lateral_top_edge": json_safe(diagnostics["F_lateral_top_edge"]),
                "elapsed_seconds": finite_float(
                    result["elapsed_seconds"], "solver elapsed_seconds"
                ),
                "solver_parameters": json_safe(solver_parameters),
                **angular_state(spec, theta),
                "solver_result": json_safe({**result, **metadata}),
            }
        except KeyError as exc:
            raise EvaluationError(f"Missing BEM result field: {exc.args[0]}.") from exc
        except ConfigurationError as exc:
            raise EvaluationError(str(exc)) from exc
        records.append(record)
        log_step(
            step_id,
            record,
            solver_name="bem",
            solver_parameters=solver_parameters,
        )
        log_metric(
            metric_key,
            result["f_net_pN"],
            step_id=step_id,
            solver_name="bem",
            solver_parameters=solver_parameters,
        )
        atomic_json_write(report_path, {"provenance": provenance, "evaluations": records})
        print(
            f"[{step + 1}/{len(tasks)}] {name} theta={theta:.6f} deg "
            f"state={record['state']} F_z={force:+.9e} N",
            flush=True,
        )

    aperture = [r for r in records if r["state"] == "aperture"]
    pad = [r for r in records if r["state"] == "landing_pad"]
    repulsive = bool(aperture) and all(r["F_z_N"] > 0.0 for r in aperture)
    attractive = bool(pad) and all(r["F_z_N"] < 0.0 for r in pad)
    evaluation = {
        **output_metadata(),
        "pure_aperture_sample_count": len(aperture),
        "pure_landing_pad_sample_count": len(pad),
        "all_sampled_pure_aperture_forces_repulsive": repulsive,
        "all_sampled_pure_landing_pad_forces_attractive": attractive,
        "requested_force_switch_verified_on_samples": repulsive and attractive,
        "physical_vertical_motion_um": 0.0,
        "qualification": "Sampled forces do not establish mesh/frequency convergence.",
    }
    atomic_json_write(report_path, {
        "provenance": provenance, "evaluation": evaluation, "evaluations": records,
    })
    write_markdown(args.output_dir / "rotational_z_eff_clutch_report.md", records)
    export_macros()
    if not quick and (args.max_steps == 0 or args.plot):
        make_plot(records, PROJECT_ROOT / "figures", logging)
    print(json.dumps(evaluation, indent=2, allow_nan=False))
    print(f"Report: {report_path}")
    if args.require_force_switch and not (repulsive and attractive):
        print("Requested force switch was not established by the BEM results.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConfigurationError, EvaluationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
