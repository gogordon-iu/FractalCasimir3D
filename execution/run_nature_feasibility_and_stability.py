#!/usr/bin/env python3
"""Run grounded 3D-BEM Nature feasibility and stability benchmarks.

Place this file at execution/run_nature_feasibility_and_stability.py.

A micro-probe (--max-steps 1 through 10) requests exactly one reduced-resolution
BEM evaluation, with at least two frequency points and a wall-clock watchdog.
A timed-out or failed calculation is reported as such; it is never replaced by
an analytical or fabricated result.

Full studies use Gold at 300 K except where a material/temperature sweep is
explicitly requested. All dimensions supplied to the mesh builder are in um.

The legacy 30 nm work estimate extrapolates a single-point force. The additional
repulsive-basin estimate uses a nonnegative force and a triangular profile over
an approximately 16 nm basin; neither estimate is a computed force integral.

Output status is the freshness-schema completion marker. Scientific execution
outcomes are recorded separately in execution_status.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import inspect
import json
import math
import multiprocessing as mp
import os
import sys
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pint
import scipy.linalg as scipy_linalg

UREG = pint.UnitRegistry()

from execution.casimir_bem_solver import BEM_TIER_STANDARD
from execution.clutch_geometry_redesign import (
    DEFAULT_H_TEETH_ROTATIONAL_UM,
    DEFAULT_HYBRID_L2_H_TEETH_UM,
    DEFAULT_HYBRID_L2_Z_TIP_UM,
    DEFAULT_N3_TOOTH_ARC_DEG,
    DEFAULT_NUM_SECTORS,
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    DEFAULT_SECTOR_DEG,
    DEFAULT_TOOTH_ARC_DEG,
    DEFAULT_TOOTH_CENTER_OFFSET_DEG,
    DEFAULT_T_LANDING_PAD_UM,
    DEFAULT_T_MEMBRANE_UM,
    DEFAULT_Z_PAD_TOP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
    MONOLITHIC_SPOKE_Z_MAX_UM,
    MONOLITHIC_SPOKE_Z_MIN_UM,
    ROTATIONAL_9ANGLE_SWEEP_DEG,
    ROTATIONAL_C8_COMPACT_N2_SPEC,
    ROTATIONAL_C10_FRACTAL_N3_SPEC,
    disengaged_angle_deg,
    engaged_angle_deg,
    straddling_angle_deg,
)
from execution.materials_database_dispersive import (
    EPSILON_0_F_PER_M,
    E_CHARGE_SI_C,
    HBAR_C_EV_UM,
    HBAR_C_PN_UM2,
    KB_T_300_PN_UM,
    ROOM_TEMPERATURE_K,
    SILICON_YOUNGS_MODULUS_GPA,
    SILICON_YOUNGS_MODULUS_PA,
)

KAPPA_LAPLACE_PER_UM = 1e-6
REPULSIVE_BASIN_WIDTH_UM = 0.016
REPULSIVE_BASIN_PROFILE_FACTOR = 0.5
LEGACY_WORK_STROKE_UM = 0.030
OUTPUT_MODEL = "BEM_ElectroThermal_Feasibility"
OUTPUT_DATASET = "nature_feasibility_stability"
DEFAULT_STUDY_MATERIAL = "Gold"
DEFAULT_STUDY_TEMPERATURE_K = ROOM_TEMPERATURE_K
THETA_DISENGAGED_DEG = disengaged_angle_deg(
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    tooth_center_offset_deg=DEFAULT_TOOTH_CENTER_OFFSET_DEG,
)
THETA_STRADDLING_DEG = straddling_angle_deg(
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    tooth_center_offset_deg=DEFAULT_TOOTH_CENTER_OFFSET_DEG,
)
THETA_ENGAGED_DEG = engaged_angle_deg(
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    sector_deg=DEFAULT_SECTOR_DEG,
    tooth_center_offset_deg=DEFAULT_TOOTH_CENTER_OFFSET_DEG,
)
SWITCHING_ANGLES_DEG: tuple[float, float] = (
    THETA_DISENGAGED_DEG,
    THETA_ENGAGED_DEG,
)
ROTATIONAL_BARRIER_ANGLES_DEG: tuple[float, ...] = (
    0.0,
    THETA_DISENGAGED_DEG,
    6.0,
    12.0,
    18.0,
    24.0,
    30.0,
    36.0,
    42.0,
    THETA_ENGAGED_DEG,
)
HYBRID_CANTOR_Z_TIPS_UM: tuple[float, float, float] = (
    DEFAULT_HYBRID_L2_Z_TIP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
    DEFAULT_HYBRID_L2_Z_TIP_UM,
)
HYBRID_CANTOR_H_TEETH_UM: tuple[float, float, float] = (
    DEFAULT_HYBRID_L2_H_TEETH_UM,
    DEFAULT_H_TEETH_ROTATIONAL_UM,
    DEFAULT_HYBRID_L2_H_TEETH_UM,
)
CANTOR_N2_TRACK_LEVELS: tuple[int, int, int] = (2, 1, 2)
CAPACITANCE_DELTA_Z_STEP_UM = 0.002
CAPACITANCE_DELTA_Z_STENCIL_UM: tuple[float, float, float] = (
    -CAPACITANCE_DELTA_Z_STEP_UM,
    0.0,
    CAPACITANCE_DELTA_Z_STEP_UM,
)
CRITICAL_PATCH_VOLTAGE_THRESHOLD_MV = 50.0
NEMS_SPOKE_COUNT = DEFAULT_NUM_SECTORS
NEMS_SPOKE_LENGTH_UM = 15.0
NEMS_SPOKE_THICKNESS_UM = 0.120
NEMS_SPOKE_WIDTH_UM = 0.350
NEMS_NM_ACTUATOR_LENGTH_UM = 65.0
NEMS_NM_ACTUATOR_THICKNESS_UM = 0.075
NEMS_NM_ACTUATOR_WIDTH_UM = 0.400
NEMS_SOFT_CLUTCH_LENGTH_UM = 150.0
NEMS_SOFT_CLUTCH_THICKNESS_UM = 0.120
NEMS_SOFT_CLUTCH_WIDTH_UM = 0.350
NEMS_COMPACT_CLUTCH_LENGTH_UM = 60.0
NEMS_COMPACT_CLUTCH_THICKNESS_UM = 0.050
NEMS_COMPACT_CLUTCH_WIDTH_UM = 0.350
PULL_IN_POWER_LAW_ALPHA = 3.5
ENGAGED_PAD_GAP_NM = 15.0
GOLD_DENSITY_KG_PER_M3 = 19300.0
SILICON_DENSITY_KG_PER_M3 = 2329.0
RAYLEIGH_GUIDED_BEAM_MODAL_MASS_FACTOR = 3.0 / 8.0
RAYLEIGH_HERMITE_STATIC_MODAL_MASS_FACTOR = 13.0 / 35.0
FEM_BEAM_NUM_ELEMENTS = 64
MONOLITHIC_COLLAR_OVERHANG_UM = 0.12
MONOLITHIC_MIN_INNER_RADIUS_UM = 0.08
UHV_QUALITY_FACTORS: tuple[float, float] = (1.0e4, 1.0e5)
LOCKIN_TAU_GRID_S: tuple[float, ...] = (
    1.0e-3,
    3.0e-3,
    1.0e-2,
    3.0e-2,
    1.0e-1,
    3.0e-1,
    1.0,
    3.0,
    10.0,
    30.0,
    100.0,
)
# 1 GPa * um = 10^9 Pa * 10^-6 m = 10^3 N/m, and 1 N/m = 10^12 pN / 10^9 nm = 10^3 pN/nm.
GPA_UM_TO_PN_PER_NM = 1e6
REGIMES: tuple[tuple[str, str, float], ...] = (
    ("PEC_T0K", "PEC", 0.0),
    ("Gold_T0K", DEFAULT_STUDY_MATERIAL, 0.0),
    ("Gold_T300K", DEFAULT_STUDY_MATERIAL, DEFAULT_STUDY_TEMPERATURE_K),
)
PATCH_VOLTAGES_MV = (0, 5, 10, 15, 20, 25, 30, 40, 50)
RADIAL_SHIFTS_UM = (0.0, 0.004, 0.008)
WIDTH_SHIFTS_UM = (-0.010, -0.005, 0.0, 0.005, 0.010)

# Backend symbols are loaded only in the process performing the calculation.
ClutchSurfaceMesh: Any = None
Geometry: Any = None
TrackElement: Any = None
StudyDesign: Any = None
TrackSpec3D: Any = None
_azimuthal: Any = None
_horizontal: Any = None
_radial: Any = None
_yukawa_blocks: Any = None
run_bem_casimir_solver: Any = None
build_designs: Any = None
build_study_clutch_mesh: Any = None
get_scoped_clutch_elements: Any = None


class BackendContractError(RuntimeError):
    """The installed scientific backend does not expose the required contract."""


class EvaluationLimit(RuntimeError):
    """The requested full-run BEM evaluation budget has been exhausted."""


def freshness_metadata(executed_at: str | None = None) -> dict[str, str]:
    return {
        "model": OUTPUT_MODEL,
        "dataset": OUTPUT_DATASET,
        "status": "completed",
        "executed_at": (
            executed_at
            if executed_at is not None
            else datetime.now(timezone.utc).isoformat()
        ),
    }


def stamp_report_rows(report: dict[str, Any]) -> None:
    """Stamp output records without changing numerical settings or namespaces."""
    metadata = freshness_metadata(report.get("executed_at"))
    report.update(metadata)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for child in list(value.values()):
                visit(child)
        elif isinstance(value, (list, tuple)):
            for row in value:
                if isinstance(row, dict):
                    if row.get("status", "completed") != "completed":
                        row.setdefault("execution_status", row["status"])
                    # Resumed evaluations retain their original execution time.
                    row_metadata = freshness_metadata(
                        row.get("executed_at", metadata["executed_at"])
                    )
                    row.update(row_metadata)
                visit(row)

    visit(report)
    for study in report.get("designs", {}).values():
        if isinstance(study, dict):
            study.update(metadata)
    if isinstance(report.get("micro_probe"), dict):
        report["micro_probe"].update(metadata)


def load_backend() -> None:
    global ClutchSurfaceMesh, Geometry, TrackElement
    global StudyDesign, TrackSpec3D
    global _azimuthal, _horizontal, _radial, _yukawa_blocks
    global run_bem_casimir_solver, build_designs, build_study_clutch_mesh
    global get_scoped_clutch_elements

    from execution.casimir_bem_solver import (
        ClutchSurfaceMesh,
        Geometry,
        TrackElement,
        _azimuthal,
        _horizontal,
        _radial,
        _yukawa_blocks,
        run_bem_casimir_solver,
    )
    from execution.clutch_geometry_redesign import get_scoped_clutch_elements
    from execution.run_fractal_advantage_study import (
        StudyDesign,
        TrackSpec3D,
        build_designs,
        build_study_clutch_mesh,
    )


def finite_float(value: Any, name: str) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise TypeError(f"{name} must be a numeric scalar, not {type(value).__name__}.")
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    array = np.asarray(value)
    if array.size != 1 or not np.issubdtype(array.dtype, np.number):
        raise TypeError(f"{name} must be a numeric scalar; shape={array.shape}.")
    result = float(array.reshape(-1)[0])
    if not math.isfinite(result):
        raise ValueError(f"{name} is not finite: {result!r}.")
    return result


def numeric_array(value: Any, name: str) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    array = np.asarray(value)
    if not np.issubdtype(array.dtype, np.number):
        raise TypeError(f"{name} is not a numeric array.")
    if np.iscomplexobj(array):
        scale = max(float(np.max(np.abs(array.real), initial=0.0)), 1.0)
        if float(np.max(np.abs(array.imag), initial=0.0)) > 1e-12 * scale:
            raise ValueError(f"{name} unexpectedly contains complex values.")
        array = array.real
    result = np.asarray(array, dtype=np.float64)
    if result.size == 0 or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} is empty or contains non-finite values.")
    return result


def members(obj: Any) -> dict[str, Any]:
    if isinstance(obj, Mapping):
        return dict(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {field.name: getattr(obj, field.name) for field in dataclasses.fields(obj)}
    if hasattr(obj, "_fields"):
        return {name: getattr(obj, name) for name in obj._fields}
    result: dict[str, Any] = {}
    if hasattr(obj, "__dict__"):
        result.update(vars(obj))
    for cls in type(obj).__mro__:
        slots = getattr(cls, "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for name in slots:
            if not name.startswith("__") and hasattr(obj, name):
                result[name] = getattr(obj, name)
    return result


def field_value(obj: Any, names: Sequence[str], context: str) -> tuple[str, Any]:
    fields = members(obj)
    for name in names:
        if name in fields:
            return name, fields[name]
        if not isinstance(obj, Mapping) and hasattr(obj, name):
            return name, getattr(obj, name)
    raise BackendContractError(
        f"{context}: expected one of {tuple(names)}; available fields: "
        f"{tuple(sorted(fields))}."
    )


def replace_fields(obj: Any, updates: Mapping[str, Any]) -> Any:
    if not updates:
        return copy.deepcopy(obj)
    if isinstance(obj, Mapping):
        result = copy.deepcopy(obj)
        try:
            result.update(updates)
        except (AttributeError, TypeError) as exc:
            raise BackendContractError("A required mapping is immutable.") from exc
        return result
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.replace(obj, **updates)
    if hasattr(obj, "_replace"):
        return obj._replace(**updates)
    result = copy.deepcopy(obj)
    for name, value in updates.items():
        try:
            setattr(result, name, value)
        except (AttributeError, TypeError) as exc:
            raise BackendContractError(
                f"Cannot update {type(obj).__name__}.{name}."
            ) from exc
    return result


def call_adapted(
    function: Callable[..., Any],
    values: Mapping[str, tuple[tuple[str, ...], Any]],
    required: Sequence[str] = (),
) -> Any:
    """Bind recognized API spellings without swallowing backend exceptions."""
    signature = inspect.signature(function)
    parameters = signature.parameters
    has_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    supplied: dict[str, Any] = {}
    recognized: set[str] = set()

    for semantic, (aliases, value) in values.items():
        matching = next((name for name in aliases if name in parameters), None)
        if matching is not None:
            supplied[matching] = value
            recognized.add(semantic)
        elif has_kwargs:
            supplied[aliases[0]] = value
            recognized.add(semantic)

    missing_controls = set(required) - recognized
    if missing_controls:
        raise BackendContractError(
            f"{function.__module__}.{function.__name__}{signature} cannot accept "
            f"required controls {sorted(missing_controls)}."
        )

    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if name in supplied:
            value = supplied.pop(name)
        elif parameter.default is not inspect.Parameter.empty:
            value = parameter.default
        else:
            raise BackendContractError(
                f"Unresolved required parameter {name!r} in "
                f"{function.__module__}.{function.__name__}{signature}."
            )
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        elif name in recognized or name in keyword:
            keyword[name] = value
        else:
            # Passing explicit defaults is safe and also handles aliased names.
            keyword[name] = value
    keyword.update(supplied)
    signature.bind(*positional, **keyword)
    return function(*positional, **keyword)


def choose_device(requested: str) -> str:
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "auto":
        return device
    parsed = torch.device(requested)
    if parsed.type not in {"cpu", "cuda"}:
        raise ValueError("Only cpu, cuda, or cuda:N devices are supported.")
    if parsed.type == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA was requested but is not available.")
        index = parsed.index if parsed.index is not None else 0
        if index >= torch.cuda.device_count():
            raise ValueError(f"CUDA device index {index} is unavailable.")
    return str(parsed)


def design_label(design: Any) -> str:
    _, value = field_value(design, ("name", "label", "design_name"), "StudyDesign")
    if not isinstance(value, str) or not value:
        raise BackendContractError("A StudyDesign label must be a nonempty string.")
    return value


def prepare_designs() -> dict[str, Any]:
    raw = build_designs()
    if isinstance(raw, Mapping):
        available = dict(raw)
        for design in raw.values():
            available.setdefault(design_label(design), design)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        available = {design_label(design): design for design in raw}
    else:
        raise BackendContractError("build_designs() must return a mapping or sequence.")

    if "Cantor_RZ_ScaleMatched" not in available:
        raise BackendContractError(
            "Required design 'Cantor_RZ_ScaleMatched' is absent. Available: "
            f"{sorted(available)}. No substitute geometry will be used."
        )

    cantor = copy.deepcopy(available["Cantor_RZ_ScaleMatched"])
    label_field, _ = field_value(
        cantor, ("name", "label", "design_name"), "Cantor design"
    )
    tracks_field, tracks = field_value(
        cantor, ("tracks", "track_specs", "tracks_3d"), "Cantor design"
    )
    if not isinstance(tracks, Sequence) or isinstance(tracks, (str, bytes)):
        raise BackendContractError("Cantor tracks must be an ordered sequence.")
    if len(tracks) != 3:
        raise BackendContractError(
            f"Cantor_RZ_ScaleMatched must have exactly three tracks, got {len(tracks)}."
        )
    new_tracks: list[Any] = []
    for track, z_tip, h_teeth in zip(
        tracks,
        HYBRID_CANTOR_Z_TIPS_UM,
        HYBRID_CANTOR_H_TEETH_UM,
        strict=True,
    ):
        field_value(track, ("z_tip",), "TrackSpec3D")
        field_value(track, ("h_teeth",), "TrackSpec3D")
        new_tracks.append(replace_fields(track, {"z_tip": z_tip, "h_teeth": h_teeth}))
    collection = tuple(new_tracks) if isinstance(tracks, tuple) else new_tracks
    cantor = replace_fields(
        cantor,
        {label_field: "Cantor_N2_HybridRZ", tracks_field: collection},
    )

    c8_spec = ROTATIONAL_C8_COMPACT_N2_SPEC
    elements = list(
        get_scoped_clutch_elements(
            N=int(c8_spec["N"]),
            R_min=float(c8_spec["R_min"]),
            R_max=float(c8_spec["R_max"]),
            w1_ratio=float(c8_spec["w1_ratio"]),
            min_tooth_w=float(c8_spec["min_tooth_w"]),
        )
    )
    elements.sort(
        key=lambda e: finite_float(
            field_value(e, ("r_inner",), "compact track")[1], "r_inner"
        )
    )
    if len(elements) != len(CANTOR_N2_TRACK_LEVELS):
        raise BackendContractError(
            f"The compact N=2 clutch must have exactly three tracks, got {len(elements)}."
        )
    compact_tracks = tuple(
        TrackSpec3D(
            r_inner=finite_float(
                field_value(element, ("r_inner",), "compact track")[1], "r_inner"
            ),
            r_outer=finite_float(
                field_value(element, ("r_outer",), "compact track")[1], "r_outer"
            ),
            r_tooth_in=finite_float(
                field_value(element, ("r_tooth_in",), "compact track")[1], "r_tooth_in"
            ),
            r_tooth_out=finite_float(
                field_value(element, ("r_tooth_out",), "compact track")[1], "r_tooth_out"
            ),
            z_tip=DEFAULT_Z_TIP_ROTATIONAL_UM,
            h_teeth=float(c8_spec["h_teeth"]),
            level=level,
        )
        for element, level in zip(elements, CANTOR_N2_TRACK_LEVELS, strict=True)
    )
    compact = StudyDesign(
        name=str(c8_spec["name"]),
        category="compact_n2",
        description="Compact N=2 clutch",
        R_min=float(c8_spec["R_min"]),
        R_max=float(c8_spec["R_max"]),
        aperture_arc_deg=float(c8_spec["aperture_arc_deg"]),
        tooth_arc_deg=float(c8_spec["tooth_arc_deg"]),
        t_membrane=float(c8_spec["t_membrane"]),
        t_landing_pad=float(c8_spec["t_landing_pad"]),
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
        tracks=compact_tracks,
    )
    return {
        "Cantor_N2_HybridRZ": cantor,
        "Rot_C8_Compact_N2": compact,
    }


def perturb_design(design: Any, delta_r_um: float, delta_w_um: float) -> Any:
    delta_r_um = finite_float(delta_r_um, "delta_r_um")
    delta_w_um = finite_float(delta_w_um, "delta_w_um")
    tracks_field, tracks = field_value(
        design, ("tracks", "track_specs", "tracks_3d"), "StudyDesign"
    )
    if len(tracks) == 0:
        raise ValueError("A clutch design cannot have zero tracks.")
    modified: list[Any] = []
    for track in tracks:
        updates: dict[str, float] = {}
        if delta_r_um != 0.0 or delta_w_um != 0.0:
            radii = {
                name: finite_float(
                    field_value(track, (name,), "tooth perturbation")[1], name
                )
                for name in ("r_inner", "r_outer", "r_tooth_in", "r_tooth_out")
            }
            if delta_r_um != 0.0:
                updates["r_tooth_in"] = radii["r_tooth_in"] + delta_r_um
                updates["r_tooth_out"] = radii["r_tooth_out"] + delta_r_um
                if not (
                    radii["r_inner"]
                    < updates["r_tooth_in"]
                    < updates["r_tooth_out"]
                    < radii["r_outer"]
                ):
                    raise ValueError("The shifted tooth does not fit inside its slot.")
            if delta_w_um != 0.0:
                inner = updates.get("r_tooth_in", radii["r_tooth_in"])
                outer = updates.get("r_tooth_out", radii["r_tooth_out"])
                center = 0.5 * (inner + outer)
                new_width = (outer - inner) + delta_w_um
                if not math.isfinite(new_width) or new_width <= 0.0:
                    raise ValueError(
                        "The CD perturbation produces a nonpositive or non-finite tooth width."
                    )
                # Change radial width while preserving the tooth center and slot bounds.
                updates["r_tooth_in"] = center - 0.5 * new_width
                updates["r_tooth_out"] = center + 0.5 * new_width
                if not (
                    radii["r_inner"]
                    < updates["r_tooth_in"]
                    < updates["r_tooth_out"]
                    < radii["r_outer"]
                ):
                    raise ValueError("The CD perturbation closes the lateral slot clearance.")
        modified.append(replace_fields(track, updates))
    collection = tuple(modified) if isinstance(tracks, tuple) else modified
    return replace_fields(design, {tracks_field: collection})


def make_mesh(design: Any, theta_deg: float, settings: Mapping[str, Any]) -> Any:
    mesh = call_adapted(
        build_study_clutch_mesh,
        {
            "design": (("design", "study_design"), design),
            "theta": (("theta_deg", "theta_degrees", "angle_deg"), theta_deg),
            "n_r": (("n_r",), settings["n_r"]),
            "n_phi_tooth": (("n_phi_tooth",), settings["n_phi_tooth"]),
            "n_phi_bridge": (("n_phi_bridge",), settings["n_phi_bridge"]),
            "n_z": (("n_z",), settings["n_z"]),
        },
        required=("design", "theta", "n_r", "n_phi_tooth", "n_phi_bridge", "n_z"),
    )
    if not isinstance(mesh, ClutchSurfaceMesh):
        raise BackendContractError(
            "build_study_clutch_mesh() did not return ClutchSurfaceMesh."
        )
    if not isinstance(getattr(mesh, "parameters", None), dict):
        raise BackendContractError("ClutchSurfaceMesh.parameters must be a mutable dict.")
    return mesh


def body_field(mesh: Any, body: str) -> tuple[str, Any]:
    return field_value(
        mesh,
        (
            body,
            f"{body}_panels",
            f"{body}_elements",
            f"{body}_surfaces",
            f"{body}_geometry",
        ),
        f"{body} BEM boundary",
    )


def panel_areas(body: Any) -> np.ndarray:
    fields = members(body)
    for name in ("areas", "areas_um2", "panel_areas", "area", "area_um2"):
        if name in fields:
            areas = numeric_array(fields[name], name).reshape(-1)
            if np.any(areas <= 0.0):
                raise ValueError("Every BEM panel must have positive area.")
            return areas
    if isinstance(body, Sequence) and not isinstance(body, (str, bytes, np.ndarray)):
        if len(body) == 0:
            raise ValueError("The BEM boundary has no panels.")
        areas = np.array(
            [
                finite_float(
                    field_value(
                        panel, ("area", "area_um2", "surface_area"), "BEM panel"
                    )[1],
                    "panel area",
                )
                for panel in body
            ],
            dtype=np.float64,
        )
        if np.any(areas <= 0.0):
            raise ValueError("Every BEM panel must have positive area.")
        return areas
    raise BackendContractError(
        f"Cannot read panel areas from {type(body).__name__}; "
        f"available fields: {tuple(sorted(fields))}."
    )


VECTOR_POSITION_FIELDS = frozenset(
    {
        "center", "centers", "centre", "centres", "centroid", "centroids",
        "center_um", "centers_um", "centroid_um", "centroids_um",
        "position", "positions", "position_um", "positions_um",
        "point", "points", "points_um", "vertices", "vertices_um",
        "nodes", "nodes_um", "xyz", "origin", "origin_um",
        "quadrature_points", "quadrature_points_um",
    }
)
SCALAR_Z_FIELDS = frozenset(
    {
        "z", "z_um", "z0", "z1", "z_min", "z_max", "z_lower", "z_upper",
        "z_center", "z_center_um", "z_tip", "z_top", "z_bottom",
    }
)
NONPOSITION_FIELDS = frozenset(
    {
        "normal", "normals", "normal_vectors", "area", "areas", "area_um2",
        "areas_um2", "panel_areas", "weights", "quadrature_weights",
        "tangent", "tangents", "parameters", "material",
    }
)


def shift_vector(value: Any, delta_um: float, name: str) -> Any:
    array = numeric_array(value, name)
    if array.ndim < 1 or array.shape[-1] != 3:
        raise BackendContractError(f"Coordinate field {name!r} must end in dimension 3.")
    if hasattr(value, "detach"):
        shifted = value.clone()
        shifted[..., 2] += delta_um
        return shifted
    shifted_array = array.copy()
    shifted_array[..., 2] += delta_um
    if isinstance(value, tuple):
        return tuple(shifted_array.tolist())
    if isinstance(value, list):
        return shifted_array.tolist()
    return shifted_array


def translate_boundary(body: Any, delta_um: float) -> tuple[Any, int]:
    """Translate positions, never normals or areas, in the stored panel schema."""
    if isinstance(body, Sequence) and not isinstance(body, (str, bytes, np.ndarray)):
        shifted_items: list[Any] = []
        count = 0
        # Named tuples are records, not panel collections.
        if not hasattr(body, "_fields"):
            for item in body:
                shifted_item, changed = translate_boundary(item, delta_um)
                shifted_items.append(shifted_item)
                count += changed
            return (
                tuple(shifted_items) if isinstance(body, tuple) else shifted_items,
                count,
            )
    fields = members(body)
    updates: dict[str, Any] = {}
    count = 0
    for name, value in fields.items():
        if name in NONPOSITION_FIELDS:
            continue
        if name in VECTOR_POSITION_FIELDS:
            updates[name] = shift_vector(value, delta_um, name)
            count += 1
        elif name in SCALAR_Z_FIELDS:
            array = numeric_array(value, name)
            if array.size == 1:
                updates[name] = finite_float(value, name) + delta_um
            elif hasattr(value, "detach"):
                updates[name] = value.clone() + delta_um
            else:
                updates[name] = array + delta_um
            count += 1
        elif name in {"panels", "elements", "surfaces", "patches", "geometry"}:
            translated, changed = translate_boundary(value, delta_um)
            updates[name] = translated
            count += changed
    if not updates:
        raise BackendContractError(
            f"Cannot translate the stored {type(body).__name__} boundary safely. "
            f"Fields: {tuple(sorted(fields))}. No approximate remeshing is used."
        )
    return replace_fields(body, updates), count


def translated_mesh(mesh: Any, delta_um: float) -> Any:
    rotor_name, rotor = body_field(mesh, "rotor")
    shifted, count = translate_boundary(rotor, delta_um)
    if count == 0:
        raise BackendContractError("Rotor translation changed no coordinates.")
    original_areas = panel_areas(rotor)
    shifted_areas = panel_areas(shifted)
    if not np.array_equal(original_areas, shifted_areas):
        raise ValueError("A rigid rotor translation unexpectedly changed panel areas.")
    return replace_fields(mesh, {rotor_name: shifted})


def capacitance(mesh: Any, sectors: int) -> dict[str, Any]:
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    rotor_areas = numeric_array(rotor.areas, "rotor areas").reshape(-1)
    stator_areas = numeric_array(stator.areas, "stator areas").reshape(-1)
    if np.any(rotor_areas <= 0.0) or np.any(stator_areas <= 0.0):
        raise ValueError("Every BEM panel must have positive area.")
    nr, ns = rotor_areas.size, stator_areas.size

    def summed(target: Any, source: Any, same: bool, shape: tuple[int, int]) -> np.ndarray:
        matrix = np.zeros(shape, dtype=np.float64)
        for sector in range(sectors):
            blocks = _yukawa_blocks(
                target, source, sector, KAPPA_LAPLACE_PER_UM, same_body=same
            )
            _, single_layer = field_value(
                blocks, ("single_layer",), "_yukawa_blocks result"
            )
            block = numeric_array(single_layer, "single_layer")
            if block.shape != shape:
                raise BackendContractError(
                    f"Single-layer block has shape {block.shape}, expected {shape}."
                )
            matrix += block
        if not np.all(np.isfinite(matrix)):
            raise ValueError("Symmetry-summed single-layer matrix is non-finite.")
        return matrix

    rr = summed(rotor, rotor, True, (nr, nr))
    ss = summed(stator, stator, True, (ns, ns))
    rs = summed(rotor, stator, False, (nr, ns))
    matrix = np.block([[rr, rs], [rs.T, ss]])
    rhs = np.concatenate((np.sqrt(rotor_areas), -np.sqrt(stator_areas))) / 2.0
    try:
        charge = np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError as exc:
        raise ValueError("The Laplace single-layer capacitance system is singular.") from exc
    if not np.all(np.isfinite(charge)):
        raise ValueError("The capacitance solution is non-finite.")
    denominator = float(np.linalg.norm(rhs))
    if denominator <= 0.0:
        raise ValueError("The capacitance right-hand side is zero.")
    residual = float(np.linalg.norm(matrix @ charge - rhs)) / denominator
    if not math.isfinite(residual) or residual > 1e-8:
        raise ValueError(f"Capacitance linear solve residual is unacceptable: {residual}.")
    capacitance_f = (
        float(sectors)
        * EPSILON_0_F_PER_M
        * 1e-6
        * float(np.dot(np.sqrt(rotor_areas), charge[:nr]))
    )
    if not math.isfinite(capacitance_f) or capacitance_f <= 0.0:
        raise ValueError(f"Nonphysical mutual capacitance: {capacitance_f!r} F.")
    return {
        **freshness_metadata(),
        "C_mutual_F": capacitance_f,
        "relative_linear_residual": residual,
        "rotor_panel_count_per_sector": int(nr),
        "stator_panel_count_per_sector": int(ns),
        "sector_count": sectors,
    }


def vertical_force(result: Mapping[str, Any]) -> float:
    for name in (
        "f_net_pN", "force_z_pN", "Fz_pN", "F_z_pN", "vertical_force_pN",
        "total_force_z_pN", "force_pN", "total_force_pN",
    ):
        if name not in result:
            continue
        value = result[name]
        array = numeric_array(value, name)
        if array.size == 1:
            return finite_float(value, name)
        if array.shape == (3,):
            return finite_float(array[2], name)
        raise BackendContractError(f"{name} is neither a scalar nor an xyz force vector.")
    raise BackendContractError(
        f"BEM result has no recognized pN vertical-force field: {sorted(result)}."
    )


def result_summary(result: Any) -> dict[str, float]:
    if not isinstance(result, Mapping):
        raise BackendContractError("run_bem_casimir_solver() must return a mapping.")
    if "energy_hbar_c_per_um" not in result:
        raise BackendContractError("BEM result lacks energy_hbar_c_per_um.")
    energy = finite_float(result["energy_hbar_c_per_um"], "energy_hbar_c_per_um")
    return {
        "force_z_pN": vertical_force(result),
        "energy_hbar_c_per_um": energy,
        "energy_pN_um": energy * HBAR_C_PN_UM2,
    }


class Evaluator:
    def __init__(
        self,
        settings: dict[str, Any],
        report: dict[str, Any],
        existing_evaluations: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.settings = settings
        if settings["max_steps"] > 0:
            self.settings["n_xi"] = max(2, self.settings["n_xi"])
        self.report = report
        self.cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.steps = 0

        if not 0 < settings["max_steps"] <= 10:
            for row in existing_evaluations:
                if not isinstance(row, Mapping):
                    continue
                try:
                    if not isinstance(row["design"], str) or not row["design"]:
                        continue
                    if not isinstance(row["material"], str) or not row["material"]:
                        continue
                    key = (
                        row["design"],
                        finite_float(row["theta_deg"], "theta_deg"),
                        str(row["material"]),
                        finite_float(row["temperature_K"], "temperature_K"),
                        finite_float(row["delta_r_um"], "delta_r_um"),
                        finite_float(row["delta_w_tooth_um"], "delta_w_tooth_um"),
                    )
                    for field in (
                        "force_z_pN", "energy_hbar_c_per_um", "energy_pN_um"
                    ):
                        finite_float(row[field], field)
                except (KeyError, TypeError, ValueError, OverflowError):
                    # Incomplete or invalid records are not completed evaluations.
                    continue
                if key in self.cache:
                    continue
                summary = copy.deepcopy(dict(row))
                summary.update(freshness_metadata(summary.get("executed_at")))
                summary["step_id"] = self.steps
                self.cache[key] = summary
                self.report["evaluations"].append(summary)
                self.steps += 1

    def evaluate(
        self,
        name: str,
        design: Any,
        theta_deg: float,
        material: str,
        temperature_k: float,
        delta_r_um: float = 0.0,
        delta_w_um: float = 0.0,
    ) -> dict[str, Any]:
        key = (name, theta_deg, material, temperature_k, delta_r_um, delta_w_um)
        if key in self.cache:
            return self.cache[key]
        budget = int(self.settings["max_steps"])
        if budget > 10 and self.steps >= budget:
            raise EvaluationLimit(f"The full-run limit of {budget} BEM solves was reached.")
        modified = perturb_design(design, delta_r_um, delta_w_um)
        mesh = make_mesh(modified, theta_deg, self.settings)
        mesh.parameters["material"] = material
        mesh.parameters["temperature_K"] = temperature_k
        started = time.monotonic()
        result = call_adapted(
            run_bem_casimir_solver,
            {
                "mesh": (("mesh", "clutch_mesh", "surface_mesh"), mesh),
                "parameters": (("parameters", "params"), mesh.parameters),
                "theta": (("theta_deg", "theta_degrees", "angle_deg"), theta_deg),
                "n_xi": (("n_xi", "num_xi"), self.settings["n_xi"]),
                "formulation": (("formulation",), self.settings["formulation"]),
                "device": (("device",), self.settings["device"]),
                "temperature": (("temperature_K",), temperature_k),
                "record_metrics": (("record_metrics",), False),
            },
            required=("mesh", "parameters", "n_xi", "formulation", "device"),
        )
        summary: dict[str, Any] = {
            **freshness_metadata(),
            "step_id": self.steps,
            "design": name,
            "theta_deg": theta_deg,
            "material": material,
            "temperature_K": temperature_k,
            "delta_r_um": delta_r_um,
            "delta_w_tooth_um": delta_w_um,
            "solver_sha256": str(self.report.get("solver_sha256", "")),
            "elapsed_seconds": time.monotonic() - started,
            **result_summary(result),
        }
        self.steps += 1
        self.report["evaluations"].append(summary)
        self.cache[key] = summary
        return summary


def sector_count(mesh: Any, design_name: str) -> int:
    declared: Any = None
    for source in (mesh.parameters, members(mesh)):
        for key in ("n_sectors", "sector_count", "num_sectors"):
            if key in source:
                declared = source[key]
                break
        if declared is not None:
            break
    count = 4 if declared is None else int(finite_float(declared, "sector_count"))
    if count <= 0 or (declared is not None and count != float(declared)):
        raise ValueError("Sector count must be a positive integer.")
    if design_name == "Cantor_N2_HybridRZ" and count != 4:
        raise BackendContractError(
            f"The requested Cantor capacitance benchmark requires four sectors, got {count}."
        )
    return count


def design_operating_angles(design: Any) -> tuple[float, float]:
    """Return (theta_disengaged_deg, theta_engaged_deg) derived from design aperture."""
    _, raw_aperture = field_value(
        design, ("aperture_arc_deg",), "StudyDesign operating angles"
    )
    aperture_deg = finite_float(raw_aperture, "aperture_arc_deg")
    return (
        disengaged_angle_deg(
            aperture_deg,
            tooth_center_offset_deg=DEFAULT_TOOTH_CENTER_OFFSET_DEG,
        ),
        engaged_angle_deg(
            aperture_deg,
            sector_deg=DEFAULT_SECTOR_DEG,
            tooth_center_offset_deg=DEFAULT_TOOTH_CENTER_OFFSET_DEG,
        ),
    )


def evaluate_suspension_regime(
    *,
    spoke_count: int,
    length_um: float,
    width_um: float,
    thickness_um: float,
    force_rep_pN: float,
    force_engaged_pN: float,
    k_r_casimir_pN_per_nm: float,
    basin_width_nm: float = REPULSIVE_BASIN_WIDTH_UM * 1e3,
    pad_gap_nm: float = ENGAGED_PAD_GAP_NM,
    alpha: float = PULL_IN_POWER_LAW_ALPHA,
) -> dict[str, float | int | bool]:
    """Compute mechanical stiffness, safety factors, and linear/basin-equilibrium strokes using pint."""
    if isinstance(spoke_count, bool) or not isinstance(spoke_count, int) or spoke_count <= 0:
        raise ValueError(f"spoke_count must be a positive integer, got {spoke_count!r}")
    for label, val in (
        ("length_um", length_um),
        ("width_um", width_um),
        ("thickness_um", thickness_um),
        ("basin_width_nm", basin_width_nm),
        ("pad_gap_nm", pad_gap_nm),
        ("alpha", alpha),
    ):
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(float(val)) or float(val) <= 0.0:
            raise ValueError(f"{label} must be finite and positive, got {val!r}")
    for label, val in (
        ("force_rep_pN", force_rep_pN),
        ("force_engaged_pN", force_engaged_pN),
        ("k_r_casimir_pN_per_nm", k_r_casimir_pN_per_nm),
    ):
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(float(val)):
            raise ValueError(f"{label} must be finite, got {val!r}")
    e_y_qty = SILICON_YOUNGS_MODULUS_GPA * UREG.GPa
    l_qty = float(length_um) * UREG.um
    w_qty = float(width_um) * UREG.um
    t_qty = float(thickness_um) * UREG.um
    kz_qty = (float(spoke_count) * e_y_qty * w_qty * (t_qty**3) / (l_qty**3)).to(UREG.pN / UREG.nm)
    kr_qty = (float(spoke_count) * e_y_qty * t_qty * (w_qty**3) / (l_qty**3)).to(UREG.pN / UREG.nm)
    kz = float(kz_qty.magnitude)
    kr = float(kr_qty.magnitude)
    if not (math.isfinite(kz) and kz > 0.0 and math.isfinite(kr) and kr > 0.0):
        raise ValueError("Mechanical suspension stiffness must be finite and positive.")
    f_rep_qty = force_rep_pN * UREG.pN
    f_eng_qty = force_engaged_pN * UREG.pN
    basin_w_qty = basin_width_nm * UREG.nm
    pad_gap_qty = pad_gap_nm * UREG.nm
    kz_casimir_rep = float((max(force_rep_pN, 0.0) * UREG.pN / basin_w_qty).to(UREG.pN / UREG.nm).magnitude)
    lift_linear_nm = float((f_rep_qty / kz_qty).to(UREG.nm).magnitude)
    lift_basin_eq_nm = float((f_rep_qty / (kz_qty + kz_casimir_rep * (UREG.pN / UREG.nm))).to(UREG.nm).magnitude)
    engaged_linear_shift_nm = float((f_eng_qty / kz_qty).to(UREG.nm).magnitude)
    pull_in_factor = ((alpha + 1.0) ** (alpha + 1.0)) / (alpha**alpha)
    kz_crit_pull_in = float((pull_in_factor * abs(f_eng_qty) / pad_gap_qty).to(UREG.pN / UREG.nm).magnitude)
    pull_in_safety_factor = kz / max(kz_crit_pull_in, 1e-12)
    lateral_sf = kr / max(abs(k_r_casimir_pN_per_nm), 1e-9)
    return {
        "spoke_count": spoke_count,
        "L_spoke_um": length_um,
        "w_spoke_um": width_um,
        "t_spoke_um": thickness_um,
        "k_z_mech_pN_per_nm": kz,
        "k_z_mech_N_per_m": float(kz_qty.to(UREG.N / UREG.m).magnitude),
        "k_r_mech_pN_per_nm": kr,
        "k_r_mech_N_per_m": float(kr_qty.to(UREG.N / UREG.m).magnitude),
        "k_z_Casimir_rep_basin_pN_per_nm": kz_casimir_rep,
        "k_z_crit_pull_in_pN_per_nm": kz_crit_pull_in,
        "vertical_pull_in_safety_factor": pull_in_safety_factor,
        "non_contact_in_engaged_state": pull_in_safety_factor > 1.0,
        "lateral_stability_safety_factor": lateral_sf,
        "combined_radial_stiffness_pN_per_nm": kr + k_r_casimir_pN_per_nm,
        "locally_stable_in_sampled_coordinate": (kr + k_r_casimir_pN_per_nm) > 0.0,
        "equilibrium_axial_repulsive_lift_nm": lift_linear_nm,
        "equilibrium_axial_repulsive_lift_pm": lift_linear_nm * 1e3,
        "self_consistent_basin_repulsive_lift_nm": lift_basin_eq_nm,
        "engaged_linear_axial_deflection_nm": engaged_linear_shift_nm,
        "engaged_linear_axial_deflection_abs_pm": abs(engaged_linear_shift_nm) * 1e3,
        "peak_to_peak_linear_stroke_nm": lift_linear_nm - engaged_linear_shift_nm,
        "peak_to_peak_linear_stroke_pm": (lift_linear_nm - engaged_linear_shift_nm) * 1e3,
    }


def run_full_study(
    name: str, design: Any, evaluator: Evaluator, study: dict[str, Any]
) -> None:
    metadata = freshness_metadata(evaluator.report["executed_at"])
    theta_disengaged, theta_engaged = design_operating_angles(design)
    material_rows: list[dict[str, Any]] = []
    study["material_dispersion"] = {
        "rows": material_rows,
        "legacy_work_stroke_um": LEGACY_WORK_STROKE_UM,
        "legacy_work_model": "single-point force times 30 nm; not a basin integral",
        "repulsive_basin_width_um": REPULSIVE_BASIN_WIDTH_UM,
        "repulsive_basin_profile_factor": REPULSIVE_BASIN_PROFILE_FACTOR,
        "basin_work_model": "max(force, 0) times triangular profile factor times basin width",
        "basin_work_is_model_estimate_not_force_integral": True,
    }
    for label, material, temperature in REGIMES:
        for is_disengaged, theta in (
            (True, theta_disengaged),
            (False, theta_engaged),
        ):
            row = evaluator.evaluate(name, design, theta, material, temperature)
            force = row["force_z_pN"]
            work_basin = (
                max(force, 0.0)
                * REPULSIVE_BASIN_PROFILE_FACTOR
                * REPULSIVE_BASIN_WIDTH_UM
                if is_disengaged
                else None
            )
            material_rows.append(
                {
                    **metadata,
                    "regime": label,
                    "theta_deg": theta,
                    "force_z_pN": force,
                    "energy_pN_um": row["energy_pN_um"],
                    "W_rep_30nm_pN_um": (
                        force * LEGACY_WORK_STROKE_UM if is_disengaged else None
                    ),
                    "W_rep_30nm_over_kBT300": (
                        force * LEGACY_WORK_STROKE_UM / KB_T_300_PN_UM
                        if is_disengaged
                        else None
                    ),
                    "work_basin_pN_um": work_basin,
                    "work_basin_over_kBT300": (
                        work_basin / KB_T_300_PN_UM
                        if work_basin is not None
                        else None
                    ),
                    "expected_force_sign_observed": (
                        force > 0.0 if is_disengaged else force < 0.0
                    ),
                }
            )
    gold = evaluator.evaluate(
        name,
        design,
        theta_disengaged,
        DEFAULT_STUDY_MATERIAL,
        DEFAULT_STUDY_TEMPERATURE_K,
    )
    force_rep = float(gold["force_z_pN"])
    gold_engaged = evaluator.evaluate(
        name,
        design,
        theta_engaged,
        DEFAULT_STUDY_MATERIAL,
        DEFAULT_STUDY_TEMPERATURE_K,
    )
    force_engaged_300k = float(gold_engaged["force_z_pN"])

    # A single baseline discretization is copied and rigidly translated. This
    # keeps the exact same panels and areas at all three axial positions.
    mesh = make_mesh(design, theta_disengaged, evaluator.settings)
    mesh.parameters["material"] = DEFAULT_STUDY_MATERIAL
    mesh.parameters["temperature_K"] = DEFAULT_STUDY_TEMPERATURE_K
    sectors = sector_count(mesh, name)
    capacitance_rows: list[dict[str, Any]] = []
    patch: dict[str, Any] = {
        "kappa_per_um": KAPPA_LAPLACE_PER_UM,
        "capacitance_rows": capacitance_rows,
        "method": "m=0 cyclic-summed single-layer, +/-0.5 V Dirichlet data",
        "force_model": "uniform residual/RMS-voltage mutual-capacitance bound",
        "spatial_patch_spectrum_modelled": False,
    }
    study["patch_potential"] = patch
    for delta_z in CAPACITANCE_DELTA_Z_STENCIL_UM:
        displaced = copy.deepcopy(mesh) if delta_z == 0.0 else translated_mesh(mesh, delta_z)
        capacitance_rows.append(
            {"delta_z_rotor_um": delta_z, **capacitance(displaced, sectors)}
        )
    span_z_m = (
        CAPACITANCE_DELTA_Z_STENCIL_UM[-1] - CAPACITANCE_DELTA_Z_STENCIL_UM[0]
    ) * 1e-6
    if not math.isfinite(span_z_m) or span_z_m <= 0.0:
        raise ValueError("CAPACITANCE_DELTA_Z_STENCIL_UM must have a positive span.")
    derivative = (
        capacitance_rows[2]["C_mutual_F"] - capacitance_rows[0]["C_mutual_F"]
    ) / span_z_m
    coefficient = 1e6 * abs(derivative)
    if not math.isfinite(coefficient):
        raise ValueError("The capacitance-gradient voltage coefficient is non-finite.")
    if force_rep < 0.0:
        critical: float | None = None
        critical_status = "no_repulsion_even_at_zero_voltage"
    elif force_rep == 0.0:
        critical = 0.0
        critical_status = "zero_repulsive_margin"
    elif coefficient == 0.0:
        critical = None
        critical_status = "unbounded_in_this_zero_gradient_model"
    else:
        critical = math.sqrt(2.0 * force_rep / coefficient)
        critical_status = "finite"
    patch.update(
        {
            "dC_dz_F_per_m": derivative,
            "abs_dC_dz_pN_per_mV2": coefficient,
            "F_Casimir_Gold_300K_pN": force_rep,
            "V_crit_mV": critical,
            "V_crit_status": critical_status,
            "voltage_rows": [
                {
                    **metadata,
                    "V_patch_mV": voltage,
                    "F_net_pN": force_rep - 0.5 * coefficient * voltage**2,
                }
                for voltage in PATCH_VOLTAGES_MV
            ],
            "passes_at_50mV": (
                force_rep
                - 0.5 * coefficient * CRITICAL_PATCH_VOLTAGE_THRESHOLD_MV**2
                > 0.0
            ),
            "critical_voltage_is_exact_only_within_model": True,
        }
    )

    if len(RADIAL_SHIFTS_UM) != 3 or not all(
        math.isfinite(shift) for shift in RADIAL_SHIFTS_UM
    ):
        raise ValueError("RADIAL_SHIFTS_UM must contain three finite radial shifts.")
    h = RADIAL_SHIFTS_UM[1] - RADIAL_SHIFTS_UM[0]
    if h <= 0.0 or not math.isclose(
        h,
        RADIAL_SHIFTS_UM[2] - RADIAL_SHIFTS_UM[1],
        abs_tol=1e-12,
    ):
        raise ValueError(
            "RADIAL_SHIFTS_UM must be a strictly increasing uniform 3-point stencil."
        )
    lateral_rows: list[dict[str, Any]] = []
    lateral: dict[str, Any] = {
        "material": DEFAULT_STUDY_MATERIAL,
        "temperature_K": DEFAULT_STUDY_TEMPERATURE_K,
        "energy_rows": lateral_rows,
        "finite_difference_center_um": RADIAL_SHIFTS_UM[1],
    }
    study["lateral_stability"] = lateral
    for delta_r in RADIAL_SHIFTS_UM:
        row = evaluator.evaluate(
            name,
            design,
            theta_disengaged,
            DEFAULT_STUDY_MATERIAL,
            DEFAULT_STUDY_TEMPERATURE_K,
            delta_r_um=delta_r,
        )
        lateral_rows.append(
            {
                **metadata,
                "delta_r_um": delta_r,
                "energy_hbar_c_per_um": row["energy_hbar_c_per_um"],
                "energy_pN_um": row["energy_pN_um"],
            }
        )
    e0, e1, e2 = (row["energy_pN_um"] for row in lateral_rows)
    stiffness = (e2 - 2.0 * e1 + e0) / h**2
    origin_estimate = 2.0 * (e1 - e0) / h**2
    stiffness_pn_nm = stiffness * 1e-3
    baseline_reg = evaluate_suspension_regime(
        spoke_count=NEMS_SPOKE_COUNT,
        length_um=NEMS_SPOKE_LENGTH_UM,
        width_um=NEMS_SPOKE_WIDTH_UM,
        thickness_um=NEMS_SPOKE_THICKNESS_UM,
        force_rep_pN=force_rep,
        force_engaged_pN=force_engaged_300k,
        k_r_casimir_pN_per_nm=stiffness_pn_nm,
    )
    nm_actuator_reg = evaluate_suspension_regime(
        spoke_count=NEMS_SPOKE_COUNT,
        length_um=NEMS_NM_ACTUATOR_LENGTH_UM,
        width_um=NEMS_NM_ACTUATOR_WIDTH_UM,
        thickness_um=NEMS_NM_ACTUATOR_THICKNESS_UM,
        force_rep_pN=force_rep,
        force_engaged_pN=force_engaged_300k,
        k_r_casimir_pN_per_nm=stiffness_pn_nm,
    )
    soft_clutch_reg = evaluate_suspension_regime(
        spoke_count=NEMS_SPOKE_COUNT,
        length_um=NEMS_SOFT_CLUTCH_LENGTH_UM,
        width_um=NEMS_SOFT_CLUTCH_WIDTH_UM,
        thickness_um=NEMS_SOFT_CLUTCH_THICKNESS_UM,
        force_rep_pN=force_rep,
        force_engaged_pN=force_engaged_300k,
        k_r_casimir_pN_per_nm=stiffness_pn_nm,
    )
    compact_clutch_reg = evaluate_suspension_regime(
        spoke_count=NEMS_SPOKE_COUNT,
        length_um=NEMS_COMPACT_CLUTCH_LENGTH_UM,
        width_um=NEMS_COMPACT_CLUTCH_WIDTH_UM,
        thickness_um=NEMS_COMPACT_CLUTCH_THICKNESS_UM,
        force_rep_pN=force_rep,
        force_engaged_pN=force_engaged_300k,
        k_r_casimir_pN_per_nm=stiffness_pn_nm,
    )
    kz = float(baseline_reg["k_z_mech_pN_per_nm"])
    kr = float(baseline_reg["k_r_mech_pN_per_nm"])
    lateral.update(
        {
            "k_r_Casimir_pN_per_um": stiffness,
            "k_r_Casimir_pN_per_nm": stiffness_pn_nm,
            "k_r_Casimir_N_per_m": stiffness * 1e-6,
            "origin_even_energy_estimate_pN_per_um": origin_estimate,
            "origin_even_energy_estimate_pN_per_nm": origin_estimate * 1e-3,
            "origin_estimate_assumes_zero_first_derivative": True,
            "E_Y_Pa": SILICON_YOUNGS_MODULUS_PA,
            "L_spoke_um": NEMS_SPOKE_LENGTH_UM,
            "t_spoke_um": NEMS_SPOKE_THICKNESS_UM,
            "w_spoke_um": NEMS_SPOKE_WIDTH_UM,
            "spoke_count": NEMS_SPOKE_COUNT,
            "k_z_mech_pN_per_nm": kz,
            "k_r_mech_pN_per_nm": kr,
            "lateral_stability_safety_factor": float(baseline_reg["lateral_stability_safety_factor"]),
            "combined_radial_stiffness_pN_per_nm": float(baseline_reg["combined_radial_stiffness_pN_per_nm"]),
            "locally_stable_in_sampled_coordinate": bool(baseline_reg["locally_stable_in_sampled_coordinate"]),
            "equilibrium_axial_repulsive_lift_nm": float(baseline_reg["equilibrium_axial_repulsive_lift_nm"]),
            "equilibrium_axial_repulsive_lift_pm": float(baseline_reg["equilibrium_axial_repulsive_lift_pm"]),
            "self_consistent_basin_repulsive_lift_nm": float(baseline_reg["self_consistent_basin_repulsive_lift_nm"]),
            "engaged_linear_axial_deflection_nm": float(baseline_reg["engaged_linear_axial_deflection_nm"]),
            "engaged_linear_axial_deflection_abs_pm": float(baseline_reg["engaged_linear_axial_deflection_abs_pm"]),
            "peak_to_peak_linear_stroke_pm": float(baseline_reg["peak_to_peak_linear_stroke_pm"]),
            "k_z_Casimir_rep_basin_pN_per_nm": float(baseline_reg["k_z_Casimir_rep_basin_pN_per_nm"]),
            "k_z_crit_pull_in_pN_per_nm": float(baseline_reg["k_z_crit_pull_in_pN_per_nm"]),
            "vertical_pull_in_safety_factor": float(baseline_reg["vertical_pull_in_safety_factor"]),
            "nm_actuator_L_spoke_um": NEMS_NM_ACTUATOR_LENGTH_UM,
            "nm_actuator_w_spoke_um": NEMS_NM_ACTUATOR_WIDTH_UM,
            "nm_actuator_t_spoke_um": NEMS_NM_ACTUATOR_THICKNESS_UM,
            "nm_actuator_k_z_mech_pN_per_nm": float(nm_actuator_reg["k_z_mech_pN_per_nm"]),
            "nm_actuator_k_r_mech_pN_per_nm": float(nm_actuator_reg["k_r_mech_pN_per_nm"]),
            "nm_actuator_lateral_safety_factor": float(nm_actuator_reg["lateral_stability_safety_factor"]),
            "nm_actuator_vertical_pull_in_safety_factor": float(nm_actuator_reg["vertical_pull_in_safety_factor"]),
            "nm_actuator_linear_lift_nm": float(nm_actuator_reg["equilibrium_axial_repulsive_lift_nm"]),
            "nm_actuator_basin_eq_lift_nm": float(nm_actuator_reg["self_consistent_basin_repulsive_lift_nm"]),
            "nm_actuator_engaged_deflection_nm": float(nm_actuator_reg["engaged_linear_axial_deflection_nm"]),
            "nm_actuator_peak_to_peak_stroke_nm": float(nm_actuator_reg["peak_to_peak_linear_stroke_nm"]),
            "soft_clutch_L_spoke_um": NEMS_SOFT_CLUTCH_LENGTH_UM,
            "soft_clutch_w_spoke_um": NEMS_SOFT_CLUTCH_WIDTH_UM,
            "soft_clutch_t_spoke_um": NEMS_SOFT_CLUTCH_THICKNESS_UM,
            "soft_clutch_k_z_mech_pN_per_nm": float(soft_clutch_reg["k_z_mech_pN_per_nm"]),
            "soft_clutch_k_r_mech_pN_per_nm": float(soft_clutch_reg["k_r_mech_pN_per_nm"]),
            "soft_clutch_lateral_safety_factor": float(soft_clutch_reg["lateral_stability_safety_factor"]),
            "soft_clutch_linear_lift_nm": float(soft_clutch_reg["equilibrium_axial_repulsive_lift_nm"]),
            "soft_clutch_basin_eq_lift_nm": float(soft_clutch_reg["self_consistent_basin_repulsive_lift_nm"]),
            "compact_clutch_L_spoke_um": NEMS_COMPACT_CLUTCH_LENGTH_UM,
            "compact_clutch_w_spoke_um": NEMS_COMPACT_CLUTCH_WIDTH_UM,
            "compact_clutch_t_spoke_um": NEMS_COMPACT_CLUTCH_THICKNESS_UM,
            "compact_clutch_k_z_mech_pN_per_nm": float(compact_clutch_reg["k_z_mech_pN_per_nm"]),
            "compact_clutch_k_r_mech_pN_per_nm": float(compact_clutch_reg["k_r_mech_pN_per_nm"]),
            "compact_clutch_lateral_safety_factor": float(compact_clutch_reg["lateral_stability_safety_factor"]),
            "compact_clutch_linear_lift_nm": float(compact_clutch_reg["equilibrium_axial_repulsive_lift_nm"]),
            "compact_clutch_basin_eq_lift_nm": float(compact_clutch_reg["self_consistent_basin_repulsive_lift_nm"]),
            "suspension_regimes": {
                "isometric_transducer": baseline_reg,
                "noncontact_nm_actuator": nm_actuator_reg,
                "high_stroke_clutch": soft_clutch_reg,
                "compact_high_aspect_clutch": compact_clutch_reg,
            },
            "lift_is_linearized_not_a_self_consistent_equilibrium": True,
        }
    )

    tolerance_rows: list[dict[str, Any]] = []
    tolerance: dict[str, Any] = {
        "material": DEFAULT_STUDY_MATERIAL,
        "temperature_K": DEFAULT_STUDY_TEMPERATURE_K,
        "slot_width_fixed": True,
        "tooth_center_fixed": True,
        "rows": tolerance_rows,
    }
    study["cd_tolerance"] = tolerance
    for delta_w in WIDTH_SHIFTS_UM:
        rep = evaluator.evaluate(
            name,
            design,
            theta_disengaged,
            DEFAULT_STUDY_MATERIAL,
            DEFAULT_STUDY_TEMPERATURE_K,
            delta_w_um=delta_w,
        )["force_z_pN"]
        engaged = evaluator.evaluate(
            name,
            design,
            theta_engaged,
            DEFAULT_STUDY_MATERIAL,
            DEFAULT_STUDY_TEMPERATURE_K,
            delta_w_um=delta_w,
        )["force_z_pN"]
        swing = rep - engaged
        tolerance_rows.append(
            {
                **metadata,
                "delta_w_tooth_um": delta_w,
                "delta_w_tooth_nm": delta_w * 1e3,
                "F_rep_pN": rep,
                "F_engaged_pN": engaged,
                "Delta_F_pN": swing,
                "repulsion_preserved": rep > 0.0,
                "attraction_preserved": engaged < 0.0,
                "positive_switching_swing": swing > 0.0,
            }
        )
    tolerance["passes_requested_repulsion_and_swing_test"] = all(
        row["repulsion_preserved"] and row["positive_switching_swing"]
        for row in tolerance_rows
    )
    tolerance["engaged_attraction_preserved_at_all_CDs"] = all(
        row["attraction_preserved"] for row in tolerance_rows
    )

    rotational_eval_rows: list[dict[str, Any]] = []
    for theta_rot in ROTATIONAL_BARRIER_ANGLES_DEG:
        rot_row = evaluator.evaluate(
            name,
            design,
            theta_rot,
            DEFAULT_STUDY_MATERIAL,
            DEFAULT_STUDY_TEMPERATURE_K,
        )
        rotational_eval_rows.append(rot_row)
    study["rotational_energy_barrier"] = compute_rotational_energy_and_torque(
        rotational_eval_rows,
        theta_disengaged_deg=theta_disengaged,
        theta_engaged_deg=theta_engaged,
        metadata=metadata,
    )
    study["thermomechanical_noise"] = compute_thermomechanical_noise_and_snr(
        design=design,
        force_rep_300k_pN=force_rep,
        suspension_regimes=lateral["suspension_regimes"],
        metadata=metadata,
    )
    study["execution_status"] = "complete"


def compute_rotational_energy_and_torque(
    eval_rows: Sequence[Mapping[str, Any]],
    *,
    theta_disengaged_deg: float = THETA_DISENGAGED_DEG,
    theta_engaged_deg: float = THETA_ENGAGED_DEG,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute Delta E_C(theta), axial-switching Casimir torque, and switching work."""
    meta = dict(metadata) if metadata is not None else freshness_metadata()
    sorted_rows = sorted(
        eval_rows, key=lambda r: finite_float(r["theta_deg"], "theta_deg")
    )
    if len(sorted_rows) < 3:
        raise ValueError("At least 3 angular BEM evaluations are required for torque.")
    thetas_deg = np.array(
        [finite_float(r["theta_deg"], "theta_deg") for r in sorted_rows],
        dtype=np.float64,
    )
    if not np.all(np.diff(thetas_deg) > 0.0):
        raise ValueError("Rotational angles must be strictly increasing.")
    thetas_rad = np.deg2rad(thetas_deg)
    energies_hbar_c = np.array(
        [
            finite_float(r["energy_hbar_c_per_um"], "energy_hbar_c_per_um")
            for r in sorted_rows
        ],
        dtype=np.float64,
    )
    forces_z_pn = np.array(
        [
            finite_float(
                r.get("force_z_pN", r.get("F_z_pN", 0.0)), "force_z_pN"
            )
            for r in sorted_rows
        ],
        dtype=np.float64,
    )
    energies_aj = energies_hbar_c * HBAR_C_PN_UM2
    energies_ev = energies_hbar_c * HBAR_C_EV_UM
    delta_energies_aj = energies_aj - float(energies_aj[0])
    delta_energies_ev = energies_ev - float(energies_ev[0])

    grad_order = 2 if len(sorted_rows) >= 6 else 1
    d_energy_hbar_c_d_rad = np.gradient(energies_hbar_c, thetas_rad, edge_order=grad_order)
    torques_pn_um = -HBAR_C_PN_UM2 * d_energy_hbar_c_d_rad
    torques_pn_nm = 1000.0 * torques_pn_um

    idx_dis = int(np.argmin(np.abs(thetas_deg - theta_disengaged_deg)))
    idx_eng = int(np.argmin(np.abs(thetas_deg - theta_engaged_deg)))
    if not math.isclose(float(thetas_deg[idx_dis]), float(theta_disengaged_deg), abs_tol=1e-6):
        raise ValueError(
            f"Disengaged angle {theta_disengaged_deg} deg not found in evaluated angles {thetas_deg.tolist()}"
        )
    if not math.isclose(float(thetas_deg[idx_eng]), float(theta_engaged_deg), abs_tol=1e-6):
        raise ValueError(
            f"Engaged angle {theta_engaged_deg} deg not found in evaluated angles {thetas_deg.tolist()}"
        )
    e_dis_ev = float(energies_ev[idx_dis])
    e_eng_ev = float(energies_ev[idx_eng])
    e_dis_aj = float(energies_aj[idx_dis])
    e_eng_aj = float(energies_aj[idx_eng])
    e_min_ev = float(np.min(energies_ev))
    e_max_ev = float(np.max(energies_ev))
    e_min_aj = float(np.min(energies_aj))
    e_max_aj = float(np.max(energies_aj))
    idx_min = int(np.argmin(energies_ev))

    # Net thermodynamic state difference |E_C(3 deg) - E_C(48 deg)| and barrier climb
    switching_work_net_ev = abs(e_dis_ev - e_eng_ev)
    switching_work_net_aj = abs(e_dis_aj - e_eng_aj)
    switching_barrier_dis_from_min_ev = e_dis_ev - e_min_ev
    switching_barrier_peak_to_valley_ev = e_max_ev - e_min_ev
    switching_barrier_peak_to_valley_aj = e_max_aj - e_min_aj
    peak_torque_pn_nm = float(np.max(np.abs(torques_pn_nm)))
    idx_peak_torque = int(np.argmax(np.abs(torques_pn_nm)))

    angle_rows: list[dict[str, Any]] = []
    for i in range(len(sorted_rows)):
        angle_rows.append(
            {
                **meta,
                "theta_deg": float(thetas_deg[i]),
                "force_z_pN": float(forces_z_pn[i]),
                "energy_hbar_c_per_um": float(energies_hbar_c[i]),
                "energy_pN_um": float(energies_aj[i]),
                "energy_aJ": float(energies_aj[i]),
                "energy_eV": float(energies_ev[i]),
                "delta_energy_aJ": float(delta_energies_aj[i]),
                "delta_energy_eV": float(delta_energies_ev[i]),
                "torque_theta_pN_um": float(torques_pn_um[i]),
                "torque_theta_pN_nm": float(torques_pn_nm[i]),
            }
        )

    return {
        **meta,
        "reference_angle_deg": float(thetas_deg[0]),
        "theta_disengaged_deg": float(thetas_deg[idx_dis]),
        "theta_engaged_deg": float(thetas_deg[idx_eng]),
        "theta_energy_min_deg": float(thetas_deg[idx_min]),
        "theta_peak_torque_deg": float(thetas_deg[idx_peak_torque]),
        "energy_disengaged_eV": e_dis_ev,
        "energy_engaged_eV": e_eng_ev,
        "energy_min_eV": e_min_ev,
        "energy_max_eV": e_max_ev,
        "switching_work_ev": switching_work_net_ev,
        "switching_work_aJ": switching_work_net_aj,
        "switching_work_over_kBT300": switching_work_net_aj / KB_T_300_PN_UM,
        "switching_barrier_from_min_to_disengaged_eV": switching_barrier_dis_from_min_ev,
        "switching_barrier_peak_to_valley_eV": switching_barrier_peak_to_valley_ev,
        "switching_barrier_peak_to_valley_aJ": switching_barrier_peak_to_valley_aj,
        "peak_torque_pN_nm": peak_torque_pn_nm,
        "peak_torque_pN_um": peak_torque_pn_nm * 1e-3,
        "torque_method": (
            f"-dE_C/dtheta_rad via finite differences (np.gradient, edge_order={grad_order})"
        ),
        "rows": angle_rows,
    }


def compute_fem_guided_beam_eigenfrequency(
    *,
    spoke_count: int,
    length_um: float,
    width_um: float,
    thickness_um: float,
    m_rotor_gold_pg: float,
    e_y_gpa: float = SILICON_YOUNGS_MODULUS_GPA,
    rho_si_kg_m3: float = SILICON_DENSITY_KG_PER_M3,
    n_elem: int = FEM_BEAM_NUM_ELEMENTS,
) -> dict[str, float | int]:
    """Solve 1D Hermite cubic Euler-Bernoulli mechanical FEM eigenmode for guided spokes + rigid rotor."""
    if isinstance(spoke_count, bool) or not isinstance(spoke_count, int) or spoke_count <= 0:
        raise ValueError(f"spoke_count must be a positive integer, got {spoke_count!r}")
    if isinstance(n_elem, bool) or not isinstance(n_elem, int) or n_elem < 4:
        raise ValueError(f"FEM_BEAM_NUM_ELEMENTS must be an int >= 4, got {n_elem!r}")
    for label, val in (
        ("length_um", length_um),
        ("width_um", width_um),
        ("thickness_um", thickness_um),
        ("m_rotor_gold_pg", m_rotor_gold_pg),
        ("e_y_gpa", e_y_gpa),
        ("rho_si_kg_m3", rho_si_kg_m3),
    ):
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(float(val)) or float(val) <= 0.0:
            raise ValueError(f"{label} must be finite and positive, got {val!r}")
    l_m = float((float(length_um) * UREG.um).to(UREG.m).magnitude)
    w_m = float((width_um * UREG.um).to(UREG.m).magnitude)
    t_m = float((thickness_um * UREG.um).to(UREG.m).magnitude)
    e_pa = float((e_y_gpa * UREG.GPa).to(UREG.Pa).magnitude)
    rho_si = float((rho_si_kg_m3 * (UREG.kg / (UREG.m**3))).to(UREG.kg / (UREG.m**3)).magnitude)
    m_rotor_kg = float((m_rotor_gold_pg * UREG.pg).to(UREG.kg).magnitude)

    ei_total = float(spoke_count) * e_pa * (w_m * (t_m**3) / 12.0)
    rho_a_total = float(spoke_count) * rho_si * (w_m * t_m)
    le = l_m / float(n_elem)
    n_nodes = n_elem + 1
    ndof = 2 * n_nodes
    k_mat = np.zeros((ndof, ndof), dtype=float)
    m_mat = np.zeros((ndof, ndof), dtype=float)
    # Construct physical Hermite cubic beam element matrices for DOFs q_phys = [w_i, theta_i, w_{i+1}, theta_{i+1}],
    # then apply congruence transformation q_phys = T_e @ q_hat with q_hat = [w_i, le * theta_i, w_{i+1}, le * theta_{i+1}]
    # via T_e = diag(1, 1/le, 1, 1/le) so all generalized coordinates have dimension of meters and O(1) conditioning.
    t_scale = np.diag([1.0, 1.0 / le, 1.0, 1.0 / le])
    ke_phys = (ei_total / (le**3)) * np.array(
        [
            [12.0, 6.0 * le, -12.0, 6.0 * le],
            [6.0 * le, 4.0 * (le**2), -6.0 * le, 2.0 * (le**2)],
            [-12.0, -6.0 * le, 12.0, -6.0 * le],
            [6.0 * le, 2.0 * (le**2), -6.0 * le, 4.0 * (le**2)],
        ],
        dtype=float,
    )
    me_phys = (rho_a_total * le / 420.0) * np.array(
        [
            [156.0, 22.0 * le, 54.0, -13.0 * le],
            [22.0 * le, 4.0 * (le**2), 13.0 * le, -3.0 * (le**2)],
            [54.0, 13.0 * le, 156.0, -22.0 * le],
            [-13.0, -3.0 * (le**2), -22.0 * le, 4.0 * (le**2)],
        ],
        dtype=float,
    )
    ke = t_scale.T @ ke_phys @ t_scale
    me = t_scale.T @ me_phys @ t_scale
    for idx_e in range(n_elem):
        sl = slice(2 * idx_e, 2 * idx_e + 4)
        k_mat[sl, sl] += ke
        m_mat[sl, sl] += me

    # Guided tip node at x = L: add rigid rotor mass to translational DOF (2 * n_elem)
    m_mat[2 * n_elem, 2 * n_elem] += m_rotor_kg
    # Essential boundary conditions: clamped at x=0 (DOFs 0, 1) and guided slope at x=L (DOF 2*n_elem + 1)
    free_dofs = [d for d in range(ndof) if d not in (0, 1, 2 * n_elem + 1)]
    k_free = k_mat[np.ix_(free_dofs, free_dofs)]
    m_free = m_mat[np.ix_(free_dofs, free_dofs)]
    eigvals = scipy_linalg.eigh(k_free, m_free, eigvals_only=True)
    if eigvals.size < 2 or float(eigvals[0]) <= 0.0:
        raise ValueError(f"Non-positive FEM eigenvalue returned: {eigvals[:2]}")
    omega_0_fem_qty = (math.sqrt(float(eigvals[0])) / UREG.s)
    omega_1_fem_qty = (math.sqrt(float(eigvals[1])) / UREG.s)
    f_0_fem_qty = (omega_0_fem_qty / (2.0 * math.pi)).to(UREG.Hz)
    f_1_fem_qty = (omega_1_fem_qty / (2.0 * math.pi)).to(UREG.Hz)

    # Static tip stiffness from FEM: apply unit point load at tip translational DOF (last free DOF)
    rhs = np.zeros(len(free_dofs), dtype=float)
    rhs[-1] = 1.0
    u_static = scipy_linalg.solve(k_free, rhs, assume_a="pos")
    kz_fem_qty = ((1.0 / float(u_static[-1])) * (UREG.N / UREG.m)).to(UREG.pN / UREG.nm)
    return {
        "n_elements": int(n_elem),
        "n_free_dofs": int(len(free_dofs)),
        "omega_0_fem_rad_per_s": float(omega_0_fem_qty.magnitude),
        "f_0_fem_Hz": float(f_0_fem_qty.magnitude),
        "f_0_fem_kHz": float(f_0_fem_qty.to(UREG.kHz).magnitude),
        "f_1_fem_kHz": float(f_1_fem_qty.to(UREG.kHz).magnitude),
        "k_z_fem_pN_per_nm": float(kz_fem_qty.magnitude),
    }


def compute_thermomechanical_noise_and_snr(
    *,
    design: Any,
    force_rep_300k_pN: float,
    suspension_regimes: Mapping[str, Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
    v_rotor_gold_override_um3: float | None = None,
) -> dict[str, Any]:
    """Compute 300 K rotor effective mass, f_0 (beam & FEM), delta z_th, S_F^{1/2}, and lock-in SNR(tau) with pint."""
    meta = dict(metadata) if metadata is not None else freshness_metadata()
    if v_rotor_gold_override_um3 is not None:
        v_rotor_gold_um3 = finite_float(v_rotor_gold_override_um3, "v_rotor_gold_override_um3")
    else:
        _, r_min_raw = field_value(design, ("R_min",), "rotor mass R_min")
        _, r_max_raw = field_value(design, ("R_max",), "rotor mass R_max")
        _, tooth_arc_raw = field_value(design, ("tooth_arc_deg",), "rotor mass tooth_arc_deg")
        _, tracks = field_value(design, ("tracks", "track_specs", "tracks_3d"), "rotor mass tracks")

        r_min = finite_float(r_min_raw, "R_min")
        r_max = finite_float(r_max_raw, "R_max")
        tooth_arc_rad = math.radians(finite_float(tooth_arc_raw, "tooth_arc_deg"))
        t_support_um = MONOLITHIC_SPOKE_Z_MAX_UM - MONOLITHIC_SPOKE_Z_MIN_UM

        v_teeth_um3 = 0.0
        for track in tracks:
            r_in = finite_float(field_value(track, ("r_tooth_in",), "track")[1], "r_tooth_in")
            r_out = finite_float(field_value(track, ("r_tooth_out",), "track")[1], "r_tooth_out")
            h_t = finite_float(field_value(track, ("h_teeth",), "track")[1], "h_teeth")
            v_teeth_um3 += float(NEMS_SPOKE_COUNT) * 0.5 * tooth_arc_rad * (r_out**2 - r_in**2) * h_t

        r_collar_in = min(r_min, max(MONOLITHIC_MIN_INNER_RADIUS_UM, r_min - MONOLITHIC_COLLAR_OVERHANG_UM))
        r_collar_out = r_max + MONOLITHIC_COLLAR_OVERHANG_UM
        v_spider_um3 = float(NEMS_SPOKE_COUNT) * 0.5 * tooth_arc_rad * (r_max**2 - r_min**2) * t_support_um
        v_collar_in_um3 = math.pi * (r_min**2 - r_collar_in**2) * t_support_um
        v_collar_out_um3 = math.pi * (r_collar_out**2 - r_max**2) * t_support_um
        v_rotor_gold_um3 = v_teeth_um3 + v_spider_um3 + v_collar_in_um3 + v_collar_out_um3

    if v_rotor_gold_um3 <= 0.0:
        raise ValueError(f"v_rotor_gold_um3 must be strictly positive, got {v_rotor_gold_um3}")
    v_rotor_gold_qty = v_rotor_gold_um3 * (UREG.um**3)
    rho_gold_qty = GOLD_DENSITY_KG_PER_M3 * (UREG.kg / (UREG.m**3))
    m_rotor_gold_qty = (rho_gold_qty * v_rotor_gold_qty).to(UREG.kg)
    m_rotor_gold_pg = float(m_rotor_gold_qty.to(UREG.pg).magnitude)

    k_b_t_qty = (KB_T_300_PN_UM * UREG.pN * UREG.um).to(UREG.J)
    if not (math.isfinite(force_rep_300k_pN) and force_rep_300k_pN > 0.0):
        raise ValueError(f"force_rep_300k_pN must be finite and positive, got {force_rep_300k_pN}")
    f_rep_qty = force_rep_300k_pN * UREG.pN
    basin_width_qty = (REPULSIVE_BASIN_WIDTH_UM * UREG.um).to(UREG.nm)
    df_dz0_qty = (-f_rep_qty / basin_width_qty).to(UREG.pN / UREG.nm)
    df_dz0_pn_per_nm = float(df_dz0_qty.magnitude)

    regime_noise: dict[str, dict[str, Any]] = {}
    for reg_key, reg_data in suspension_regimes.items():
        l_um = finite_float(reg_data["L_spoke_um"], "L_spoke_um")
        w_um = finite_float(reg_data["w_spoke_um"], "w_spoke_um")
        t_um = finite_float(reg_data["t_spoke_um"], "t_spoke_um")
        kz_pn_per_nm = finite_float(reg_data["k_z_mech_pN_per_nm"], "k_z_mech_pN_per_nm")
        if l_um <= 0.0 or w_um <= 0.0 or t_um <= 0.0 or kz_pn_per_nm <= 0.0:
            raise ValueError(
                f"Suspension regime {reg_key!r} dimensions and stiffness must be strictly positive."
            )
        kz_qty = (kz_pn_per_nm * (UREG.pN / UREG.nm)).to(UREG.N / UREG.m)
        kz_n_per_m = float(kz_qty.magnitude)

        v_spokes_qty = float(NEMS_SPOKE_COUNT) * (l_um * UREG.um) * (w_um * UREG.um) * (t_um * UREG.um)
        rho_si_qty = SILICON_DENSITY_KG_PER_M3 * (UREG.kg / (UREG.m**3))
        m_spokes_total_qty = (rho_si_qty * v_spokes_qty).to(UREG.kg)
        m_spokes_eff_qty = (RAYLEIGH_GUIDED_BEAM_MODAL_MASS_FACTOR * m_spokes_total_qty).to(UREG.kg)
        m_spokes_eff_13_35_qty = (RAYLEIGH_HERMITE_STATIC_MODAL_MASS_FACTOR * m_spokes_total_qty).to(UREG.kg)
        m_eff_qty = (m_rotor_gold_qty + m_spokes_eff_qty).to(UREG.kg)
        m_eff_13_35_qty = (m_rotor_gold_qty + m_spokes_eff_13_35_qty).to(UREG.kg)
        m_eff_kg = float(m_eff_qty.magnitude)
        if not (math.isfinite(m_eff_kg) and m_eff_kg > 0.0):
            raise ValueError(f"Effective rotor mass m_eff_kg must be positive, got {m_eff_kg}")
        m_eff_pg = float(m_eff_qty.to(UREG.pg).magnitude)

        omega_0_qty = ((kz_qty / m_eff_qty) ** 0.5).to(1.0 / UREG.s)
        omega_0_rad_s = float(omega_0_qty.magnitude)
        f_0_qty = (omega_0_qty / (2.0 * math.pi)).to(UREG.Hz)
        f_0_hz = float(f_0_qty.magnitude)
        f_0_khz = float(f_0_qty.to(UREG.kHz).magnitude)

        omega_0_13_35_qty = ((kz_qty / m_eff_13_35_qty) ** 0.5).to(1.0 / UREG.s)
        f_0_rayleigh_13_35_khz = float((omega_0_13_35_qty / (2.0 * math.pi)).to(UREG.kHz).magnitude)
        f_0_bare_rotor_upper_bound_khz = float(
            ((((kz_qty / m_rotor_gold_qty) ** 0.5) / (2.0 * math.pi)).to(UREG.kHz)).magnitude
        )

        fem_info = compute_fem_guided_beam_eigenfrequency(
            spoke_count=NEMS_SPOKE_COUNT,
            length_um=l_um,
            width_um=w_um,
            thickness_um=t_um,
            m_rotor_gold_pg=m_rotor_gold_pg,
        )
        f_0_fem_khz = float(fem_info["f_0_fem_kHz"])
        fem_vs_beam_rel_diff_pct = 100.0 * abs(f_0_khz - f_0_fem_khz) / max(f_0_fem_khz, 1e-12)

        delta_z_th_qty = ((k_b_t_qty / kz_qty) ** 0.5).to(UREG.nm)
        delta_z_th_nm = float(delta_z_th_qty.magnitude)
        delta_z_th_pm = float(delta_z_th_qty.to(UREG.pm).magnitude)
        delta_f0_rep_qty = (-0.5 * f_0_qty * (df_dz0_qty / kz_qty)).to(UREG.Hz)
        delta_f0_rep_hz = float(delta_f0_rep_qty.magnitude)

        q_curves: dict[str, dict[str, Any]] = {}
        for q_val in UHV_QUALITY_FACTORS:
            q_label = f"Q_{int(q_val)}"
            s_f_qty = ((4.0 * k_b_t_qty * kz_qty / (omega_0_qty * q_val)) ** 0.5).to(
                UREG.N / (UREG.Hz**0.5)
            )
            s_f_fn_per_rt_hz = float(s_f_qty.to(UREG.fN / (UREG.Hz**0.5)).magnitude)
            s_f_pn_per_rt_hz = float(s_f_qty.to(UREG.pN / (UREG.Hz**0.5)).magnitude)
            tau_snr_100_qty = ((100.0 * s_f_qty / f_rep_qty) ** 2).to(UREG.s)
            tau_snr_10_qty = ((10.0 * s_f_qty / f_rep_qty) ** 2).to(UREG.s)
            tau_rows: list[dict[str, float]] = []
            for tau_s in LOCKIN_TAU_GRID_S:
                tau_qty = tau_s * UREG.s
                delta_f_th_qty = (s_f_qty / (tau_qty**0.5)).to(UREG.pN)
                delta_f_th_pn = float(delta_f_th_qty.magnitude)
                snr_val = float((f_rep_qty / delta_f_th_qty).to(UREG.dimensionless).magnitude)
                tau_rows.append(
                    {
                        "tau_s": float(tau_s),
                        "delta_F_th_pN": float(delta_f_th_pn),
                        "delta_F_th_fN": float(delta_f_th_qty.to(UREG.fN).magnitude),
                        "SNR": float(snr_val),
                    }
                )
            snr_1s = float((f_rep_qty / (s_f_qty / ((1.0 * UREG.s) ** 0.5))).to(UREG.dimensionless).magnitude)
            q_curves[q_label] = {
                "Q": float(q_val),
                "S_F_sqrt_fN_per_rtHz": float(s_f_fn_per_rt_hz),
                "S_F_sqrt_pN_per_rtHz": float(s_f_pn_per_rt_hz),
                "SNR_tau_1s": float(snr_1s),
                "tau_snr_10_us": float(tau_snr_10_qty.to(UREG.us).magnitude),
                "tau_snr_100_s": float(tau_snr_100_qty.magnitude),
                "tau_snr_100_ms": float(tau_snr_100_qty.to(UREG.ms).magnitude),
                "tau_snr_100_us": float(tau_snr_100_qty.to(UREG.us).magnitude),
                "passes_SNR_100_at_1s": bool(snr_1s > 100.0),
                "tau_rows": tau_rows,
            }

        regime_noise[reg_key] = {
            **meta,
            "m_eff_kg": float(m_eff_kg),
            "m_eff_pg": float(m_eff_pg),
            "m_spokes_total_pg": float(m_spokes_total_qty.to(UREG.pg).magnitude),
            "m_spokes_eff_pg": float(m_spokes_eff_qty.to(UREG.pg).magnitude),
            "modal_mass_factor": float(RAYLEIGH_GUIDED_BEAM_MODAL_MASS_FACTOR),
            "k_z_mech_pN_per_nm": float(kz_pn_per_nm),
            "k_z_mech_N_per_m": float(kz_n_per_m),
            "omega_0_rad_per_s": float(omega_0_rad_s),
            "f_0_Hz": float(f_0_hz),
            "f_0_kHz": float(f_0_khz),
            "f_0_bare_rotor_upper_bound_kHz": float(f_0_bare_rotor_upper_bound_khz),
            "f_0_rayleigh_13_35_kHz": float(f_0_rayleigh_13_35_khz),
            "f_0_fem_Hz": float(fem_info["f_0_fem_Hz"]),
            "f_0_fem_kHz": float(f_0_fem_khz),
            "f_1_fem_kHz": float(fem_info["f_1_fem_kHz"]),
            "k_z_fem_pN_per_nm": float(fem_info["k_z_fem_pN_per_nm"]),
            "fem_vs_beam_rel_diff_pct": float(fem_vs_beam_rel_diff_pct),
            "delta_z_th_nm": float(delta_z_th_nm),
            "delta_z_th_pm": float(delta_z_th_pm),
            "dFz_dz0_pN_per_nm": float(df_dz0_pn_per_nm),
            "delta_f0_rep_Hz": float(delta_f0_rep_hz),
            "delta_f0_rep_kHz": float(delta_f0_rep_hz * 1e-3),
            "quality_factors": q_curves,
        }

    reg1 = regime_noise["isometric_transducer"]
    reg2 = regime_noise["noncontact_nm_actuator"]
    reg3 = regime_noise["compact_high_aspect_clutch"]
    reg3_soft = regime_noise.get("high_stroke_clutch", reg3)
    max_fem_diff_pct = max(
        float(r["fem_vs_beam_rel_diff_pct"])
        for r in (reg1, reg2, reg3)
    )
    return {
        **meta,
        "unit_engine": f"pint {pint.__version__}",
        "modal_mass_factor": float(RAYLEIGH_GUIDED_BEAM_MODAL_MASS_FACTOR),
        "fem_elements": int(FEM_BEAM_NUM_ELEMENTS),
        "temperature_K": DEFAULT_STUDY_TEMPERATURE_K,
        "F_rep_300K_pN": float(force_rep_300k_pN),
        "dFz_dz0_pN_per_nm": float(df_dz0_pn_per_nm),
        "v_rotor_gold_um3": float(v_rotor_gold_um3),
        "m_rotor_gold_pg": float(m_rotor_gold_pg),
        "m_spokes_eff_reg1_pg": float(reg1["m_spokes_eff_pg"]),
        "m_spokes_eff_reg2_pg": float(reg2["m_spokes_eff_pg"]),
        "m_spokes_eff_reg3_pg": float(reg3["m_spokes_eff_pg"]),
        "m_eff_reg1_pg": float(reg1["m_eff_pg"]),
        "m_eff_reg2_pg": float(reg2["m_eff_pg"]),
        "m_eff_reg3_pg": float(reg3["m_eff_pg"]),
        "m_eff_reg3_soft_pg": float(reg3_soft["m_eff_pg"]),
        "thermal_dz_regime_1_nm": float(reg1["delta_z_th_nm"]),
        "thermal_dz_regime_1_pm": float(reg1["delta_z_th_pm"]),
        "thermal_dz_regime_2_nm": float(reg2["delta_z_th_nm"]),
        "thermal_dz_regime_3_nm": float(reg3["delta_z_th_nm"]),
        "thermal_dz_regime_3_soft_nm": float(reg3_soft["delta_z_th_nm"]),
        "res_freq_khz": float(reg1["f_0_kHz"]),
        "res_freq_regime_2_khz": float(reg2["f_0_kHz"]),
        "res_freq_regime_3_khz": float(reg3["f_0_kHz"]),
        "res_freq_regime_3_soft_khz": float(reg3_soft["f_0_kHz"]),
        "bare_rotor_freq_bound_reg1_khz": float(reg1["f_0_bare_rotor_upper_bound_kHz"]),
        "bare_rotor_freq_bound_reg2_khz": float(reg2["f_0_bare_rotor_upper_bound_kHz"]),
        "bare_rotor_freq_bound_reg3_khz": float(reg3["f_0_bare_rotor_upper_bound_kHz"]),
        "fem_freq_reg1_khz": float(reg1["f_0_fem_kHz"]),
        "fem_freq_reg2_khz": float(reg2["f_0_fem_kHz"]),
        "fem_freq_reg3_khz": float(reg3["f_0_fem_kHz"]),
        "fem_freq_reg3_soft_khz": float(reg3_soft["f_0_fem_kHz"]),
        "fem_max_rel_diff_pct": float(max_fem_diff_pct),
        "sf_sqrt_reg1_q1e4_fn": float(reg1["quality_factors"]["Q_10000"]["S_F_sqrt_fN_per_rtHz"]),
        "sf_sqrt_reg1_q1e5_fn": float(reg1["quality_factors"]["Q_100000"]["S_F_sqrt_fN_per_rtHz"]),
        "sf_sqrt_reg2_q1e4_fn": float(reg2["quality_factors"]["Q_10000"]["S_F_sqrt_fN_per_rtHz"]),
        "sf_sqrt_reg2_q1e5_fn": float(reg2["quality_factors"]["Q_100000"]["S_F_sqrt_fN_per_rtHz"]),
        "sf_sqrt_reg3_q1e4_fn": float(reg3["quality_factors"]["Q_10000"]["S_F_sqrt_fN_per_rtHz"]),
        "sf_sqrt_reg3_q1e5_fn": float(reg3["quality_factors"]["Q_100000"]["S_F_sqrt_fN_per_rtHz"]),
        "sf_sqrt_reg3_soft_q1e4_fn": float(reg3_soft["quality_factors"]["Q_10000"]["S_F_sqrt_fN_per_rtHz"]),
        "snr_1_sec": float(reg1["quality_factors"]["Q_10000"]["SNR_tau_1s"]),
        "snr_1_sec_Q1e5": float(reg1["quality_factors"]["Q_100000"]["SNR_tau_1s"]),
        "snr_1_sec_reg2": float(reg2["quality_factors"]["Q_10000"]["SNR_tau_1s"]),
        "snr_1_sec_reg2_Q1e5": float(reg2["quality_factors"]["Q_100000"]["SNR_tau_1s"]),
        "snr_1_sec_reg3": float(reg3["quality_factors"]["Q_10000"]["SNR_tau_1s"]),
        "snr_1_sec_reg3_Q1e5": float(reg3["quality_factors"]["Q_100000"]["SNR_tau_1s"]),
        "snr_1_sec_reg3_soft": float(reg3_soft["quality_factors"]["Q_10000"]["SNR_tau_1s"]),
        "tau_snr100_reg1_q1e4_us": float(reg1["quality_factors"]["Q_10000"]["tau_snr_100_us"]),
        "tau_snr100_reg2_q1e4_us": float(reg2["quality_factors"]["Q_10000"]["tau_snr_100_us"]),
        "tau_snr100_reg3_q1e4_us": float(reg3["quality_factors"]["Q_10000"]["tau_snr_100_us"]),
        "regimes": regime_noise,
    }


def compute_discretization_pull_in_bounds(
    *,
    design_name: str,
    patch: Mapping[str, Any],
    lateral: Mapping[str, Any],
    results_dir: Path,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compute vertical pull-in threshold k_{z,crit}^{pull-in}, V_crit, repulsive lifts,
    and Regime I-III safety factors across:
      (a) Standard sharp-edge BEM (N_panels = 1,504),
      (b) r_edge = 5 nm rounded-edge Ultra-High BEM (N_panels = 6,016) and unrounded Ultra-High sharp-edge BEM,
      (c) Continuum-extrapolated theta = 48 deg attractive force (-37.23 pN).
    """
    meta = dict(metadata) if metadata is not None else freshness_metadata()
    alpha = 3.5
    d0_nm = 15.0
    pull_in_prefactor = ((alpha + 1.0) ** (alpha + 1.0)) / (alpha ** alpha)
    abs_dc_dz = float(patch["abs_dC_dz_pN_per_mV2"])
    regimes = lateral["suspension_regimes"]
    kz_reg1 = float(regimes["isometric_transducer"]["k_z_mech_pN_per_nm"])
    kz_reg2 = float(regimes["noncontact_nm_actuator"]["k_z_mech_pN_per_nm"])
    kz_reg3 = float(regimes["compact_high_aspect_clutch"]["k_z_mech_pN_per_nm"])
    kz_reg3_soft = float(regimes["high_stroke_clutch"]["k_z_mech_pN_per_nm"])

    # Load r_edge = 5 nm rounded-edge BEM repulsive forces from bem_fdtd_convergence_resolution.json
    conv_path = results_dir / "bem_fdtd_convergence_resolution.json"
    if not conv_path.is_file():
        raise FileNotFoundError(f"Missing required convergence report: {conv_path}")
    conv_data = json.loads(conv_path.read_text(encoding="utf-8"))
    r5_rows = conv_data.get("edge_rounded_r5nm_convergence", [])
    r5_by_slug = {
        str(r["slug"]): r
        for r in r5_rows
        if isinstance(r, Mapping) and "slug" in r
    }
    if "ultra" not in r5_by_slug or "high" not in r5_by_slug:
        raise ValueError(f"Missing high/ultra rows in {conv_path} edge_rounded_r5nm_convergence")
    f_rep_r5_ultra = float(r5_by_slug["ultra"]["cantor_r5nm_fz_pN"])
    f_rep_sharp_ultra = float(r5_by_slug["ultra"]["cantor_sharp_fz_pN"])
    f_att_r5_ultra_opt: float | None = (
        float(r5_by_slug["ultra"]["cantor_r5nm_theta48_fz_pN"])
        if r5_by_slug["ultra"].get("cantor_r5nm_theta48_fz_pN") is not None
        else None
    )

    # Continuum repulsive force via two-point High-to-Ultra_High linear Richardson extrapolation in h = N_panels^-0.5
    h_high_r5 = float(r5_by_slug["high"]["n_panels"]) ** -0.5
    h_ultra_r5 = float(r5_by_slug["ultra"]["n_panels"]) ** -0.5
    f_high_r5 = float(r5_by_slug["high"]["cantor_r5nm_fz_pN"])
    f_rep_continuum = float(
        (h_high_r5 * f_rep_r5_ultra - h_ultra_r5 * f_high_r5) / (h_high_r5 - h_ultra_r5)
    )

    # Load Ultra-High sharp-edge engaged (theta = 48 deg) BEM force from campaign JSONs
    n6_path = results_dir / "nature_6step_narrative_report.json"
    rot3_path = results_dir / "rotational_clutch_3solver_verification_report.json"
    if not n6_path.is_file() or not rot3_path.is_file():
        raise FileNotFoundError("Missing nature_6step_narrative_report.json or rotational_clutch_3solver_verification_report.json")
    n6_data = json.loads(n6_path.read_text(encoding="utf-8"))
    rot3_data = json.loads(rot3_path.read_text(encoding="utf-8"))

    f_att_sharp_ultra: float | None = None
    if design_name == "Cantor_N2_HybridRZ":
        for t_row in n6_data.get("tasks", []):
            if (
                isinstance(t_row, Mapping)
                and t_row.get("design") == "Cantor_N2_HybridRZ"
                and math.isclose(float(t_row.get("theta_deg", -1.0)), 48.0, abs_tol=1e-6)
                and t_row.get("tier") == "Ultra_High"
                and t_row.get("boundary") == "Active-Only"
                and t_row.get("formulation") == "vector_dyadic"
            ):
                f_att_sharp_ultra = float(t_row["F_z_pN"])
                break
    else:
        for t_row in rot3_data.get("tasks", []):
            if (
                isinstance(t_row, Mapping)
                and t_row.get("design") == design_name
                and math.isclose(float(t_row.get("theta_deg", -1.0)), 48.0, abs_tol=1e-6)
                and t_row.get("tier") == "Ultra_High"
            ):
                f_att_sharp_ultra = float(t_row["forces_pN"]["vector_dyadic"])
                break
    if f_att_sharp_ultra is None:
        raise ValueError(f"Could not find Ultra_High theta=48 deg BEM force for {design_name}")

    # Compute 3-point OLS linear continuum intercept in h = panel_count^-0.5 at theta = 48 deg from 3-solver verification tasks
    c8_48_samples: list[tuple[float, float]] = []
    for tier_name in ("Standard", "High", "Ultra_High"):
        for t_row in rot3_data.get("tasks", []):
            if (
                isinstance(t_row, Mapping)
                and t_row.get("design") == "Rot_C8_Compact_N2"
                and math.isclose(float(t_row.get("theta_deg", -1.0)), 48.0, abs_tol=1e-6)
                and t_row.get("tier") == tier_name
            ):
                h_val = float(t_row["panel_count"]) ** -0.5
                f_val = float(t_row["forces_pN"]["vector_dyadic"])
                c8_48_samples.append((h_val, f_val))
                break
    if len(c8_48_samples) != 3:
        raise ValueError("Expected 3 mesh tiers for Rot_C8_Compact_N2 at theta=48 deg in rotational_clutch_3solver_verification_report.json")
    h_mean = sum(s[0] for s in c8_48_samples) / 3.0
    f_mean = sum(s[1] for s in c8_48_samples) / 3.0
    slope_48 = sum((h - h_mean) * (f - f_mean) for h, f in c8_48_samples) / sum(
        (h - h_mean) ** 2 for h, _ in c8_48_samples
    )
    f_att_continuum = float(f_mean - slope_48 * h_mean)

    def _eval_tier(f_rep_pn: float, f_att_pn: float | None) -> dict[str, float | None]:
        v_crit = math.sqrt(max(0.0, 2.0 * max(f_rep_pn, 0.0) / max(abs_dc_dz, 1e-30)))
        res_tier: dict[str, float | None] = {
            "F_rep_pN": float(f_rep_pn),
            "F_engaged_pN": float(f_att_pn) if f_att_pn is not None else None,
            "V_crit_mV": float(v_crit),
            "lift_regime_1_pm": float(1000.0 * max(f_rep_pn, 0.0) / kz_reg1),
            "lift_regime_1_nm": float(max(f_rep_pn, 0.0) / kz_reg1),
            "lift_regime_2_nm": float(max(f_rep_pn, 0.0) / kz_reg2),
            "lift_regime_3_nm": float(max(f_rep_pn, 0.0) / kz_reg3),
            "lift_regime_3_soft_nm": float(max(f_rep_pn, 0.0) / kz_reg3_soft),
            "k_z_crit_pull_in_pN_per_nm": None,
            "sf_pull_in_regime_1": None,
            "sf_pull_in_regime_2": None,
            "sf_pull_in_regime_3": None,
            "sf_pull_in_regime_3_soft": None,
        }
        if f_att_pn is not None:
            kz_crit = pull_in_prefactor * abs(f_att_pn) / d0_nm
            res_tier["k_z_crit_pull_in_pN_per_nm"] = float(kz_crit)
            res_tier["sf_pull_in_regime_1"] = float(kz_reg1 / kz_crit)
            res_tier["sf_pull_in_regime_2"] = float(kz_reg2 / kz_crit)
            res_tier["sf_pull_in_regime_3"] = float(kz_reg3 / kz_crit)
            res_tier["sf_pull_in_regime_3_soft"] = float(kz_reg3_soft / kz_crit)
        return res_tier

    f_rep_std = float(patch["F_Casimir_Gold_300K_pN"])
    if "F_engaged_Gold_300K_pN" in lateral:
        f_att_std = float(lateral["F_engaged_Gold_300K_pN"])
    else:
        f_att_std = float(lateral["engaged_linear_axial_deflection_nm"]) * kz_reg1

    std_tier = _eval_tier(f_rep_std, f_att_std)
    r5_ultra_tier = _eval_tier(f_rep_r5_ultra, f_att_r5_ultra_opt)
    sharp_ultra_tier = _eval_tier(f_rep_sharp_ultra, f_att_sharp_ultra)
    continuum_tier = _eval_tier(f_rep_continuum, f_att_continuum)

    out_dict: dict[str, Any] = {
        **meta,
        "design": design_name,
        "pull_in_exponent_alpha": alpha,
        "pull_in_reference_gap_d0_nm": d0_nm,
        "pull_in_prefactor": float(pull_in_prefactor),
        "r5_ultra_theta48_available": f_att_r5_ultra_opt is not None,
        "standard_sharp_bem": std_tier,
        "rounded_r5nm_ultra_bem": r5_ultra_tier,
        "sharp_ultra_bem": sharp_ultra_tier,
        "continuum_extrapolated_bem": continuum_tier,
        # Top-level scalar fields for automatic scalar_metrics export
        "std_f_rep_pn": std_tier["F_rep_pN"],
        "std_f_att_pn": std_tier["F_engaged_pN"],
        "std_v_crit_mv": std_tier["V_crit_mV"],
        "std_kz_crit_pull_in_pn_per_nm": std_tier["k_z_crit_pull_in_pN_per_nm"],
        "std_sf_pull_in_reg1": std_tier["sf_pull_in_regime_1"],
        "std_sf_pull_in_reg2": std_tier["sf_pull_in_regime_2"],
        "std_sf_pull_in_reg3": std_tier["sf_pull_in_regime_3"],
        "std_sf_pull_in_reg3_soft": std_tier["sf_pull_in_regime_3_soft"],
        "r5_ultra_f_rep_pn": r5_ultra_tier["F_rep_pN"],
        "r5_ultra_v_crit_mv": r5_ultra_tier["V_crit_mV"],
        "r5_ultra_lift_reg1_pm": r5_ultra_tier["lift_regime_1_pm"],
        "r5_ultra_lift_reg2_nm": r5_ultra_tier["lift_regime_2_nm"],
        "r5_ultra_lift_reg3_nm": r5_ultra_tier["lift_regime_3_nm"],
        "sharp_ultra_f_att_pn": sharp_ultra_tier["F_engaged_pN"],
        "sharp_ultra_kz_crit_pull_in_pn_per_nm": sharp_ultra_tier["k_z_crit_pull_in_pN_per_nm"],
        "sharp_ultra_sf_pull_in_reg1": sharp_ultra_tier["sf_pull_in_regime_1"],
        "sharp_ultra_sf_pull_in_reg2": sharp_ultra_tier["sf_pull_in_regime_2"],
        "sharp_ultra_sf_pull_in_reg3": sharp_ultra_tier["sf_pull_in_regime_3"],
        "sharp_ultra_sf_pull_in_reg3_soft": sharp_ultra_tier["sf_pull_in_regime_3_soft"],
        "continuum_f_rep_pn": continuum_tier["F_rep_pN"],
        "continuum_f_att_pn": continuum_tier["F_engaged_pN"],
        "continuum_v_crit_mv": continuum_tier["V_crit_mV"],
        "continuum_lift_reg1_pm": continuum_tier["lift_regime_1_pm"],
        "continuum_lift_reg2_nm": continuum_tier["lift_regime_2_nm"],
        "continuum_lift_reg3_nm": continuum_tier["lift_regime_3_nm"],
        "continuum_kz_crit_pull_in_pn_per_nm": continuum_tier["k_z_crit_pull_in_pN_per_nm"],
        "continuum_sf_pull_in_reg1": continuum_tier["sf_pull_in_regime_1"],
        "continuum_sf_pull_in_reg2": continuum_tier["sf_pull_in_regime_2"],
        "continuum_sf_pull_in_reg3": continuum_tier["sf_pull_in_regime_3"],
        "continuum_sf_pull_in_reg3_soft": continuum_tier["sf_pull_in_regime_3_soft"],
    }
    if f_att_r5_ultra_opt is not None:
        out_dict["r5_ultra_f_att_pn"] = r5_ultra_tier["F_engaged_pN"]
        out_dict["r5_ultra_kz_crit_pull_in_pn_per_nm"] = r5_ultra_tier["k_z_crit_pull_in_pN_per_nm"]
        out_dict["r5_ultra_sf_pull_in_reg1"] = r5_ultra_tier["sf_pull_in_regime_1"]
        out_dict["r5_ultra_sf_pull_in_reg2"] = r5_ultra_tier["sf_pull_in_regime_2"]
        out_dict["r5_ultra_sf_pull_in_reg3"] = r5_ultra_tier["sf_pull_in_regime_3"]
        out_dict["r5_ultra_sf_pull_in_reg3_soft"] = r5_ultra_tier["sf_pull_in_regime_3_soft"]
    return out_dict


def ensure_rotational_and_noise_sections(
    report: dict[str, Any], results_dir: Path
) -> None:
    """Populate rotational_energy_barrier, thermomechanical_noise, discretization_pull_in_bounds, and N=3 reference."""
    load_backend()
    designs = prepare_designs()
    meta = freshness_metadata(report.get("executed_at"))
    eval_rows = report.get("evaluations", [])

    for name in ("Cantor_N2_HybridRZ", "Rot_C8_Compact_N2"):
        study = report.get("designs", {}).get(name)
        if not isinstance(study, dict):
            continue
        design = designs[name]
        theta_dis, theta_eng = design_operating_angles(design)
        matching_rot = [
            r
            for r in eval_rows
            if isinstance(r, Mapping)
            and r.get("design") == name
            and r.get("material") == DEFAULT_STUDY_MATERIAL
            and math.isclose(float(r.get("temperature_K", 0.0)), DEFAULT_STUDY_TEMPERATURE_K, abs_tol=1e-6)
            and math.isclose(float(r.get("delta_r_um", 0.0)), 0.0, abs_tol=1e-12)
            and math.isclose(float(r.get("delta_w_tooth_um", 0.0)), 0.0, abs_tol=1e-12)
        ]
        by_angle: dict[float, Mapping[str, Any]] = {}
        for r in matching_rot:
            by_angle[round(float(r["theta_deg"]), 6)] = r
        if len(by_angle) >= 3:
            study["rotational_energy_barrier"] = compute_rotational_energy_and_torque(
                list(by_angle.values()),
                theta_disengaged_deg=theta_dis,
                theta_engaged_deg=theta_eng,
                metadata=meta,
            )
        patch = study.get("patch_potential", {})
        lateral = study.get("lateral_stability", {})
        if patch and lateral and "suspension_regimes" in lateral:
            force_rep = float(patch["F_Casimir_Gold_300K_pN"])
            study["thermomechanical_noise"] = compute_thermomechanical_noise_and_snr(
                design=design,
                force_rep_300k_pN=force_rep,
                suspension_regimes=lateral["suspension_regimes"],
                metadata=meta,
            )
            study["discretization_pull_in_bounds"] = compute_discretization_pull_in_bounds(
                design_name=name,
                patch=patch,
                lateral=lateral,
                results_dir=results_dir,
                metadata=meta,
            )

    # Also load Fractal_N3_Cantor7Track 3D Vector-Dyadic BEM rotational points from results/
    n3_rows: list[Mapping[str, Any]] = []
    n6_path = results_dir / "nature_6step_narrative_report.json"
    rot_path = results_dir / "rotational_z_eff_clutch_report.json"
    if n6_path.is_file():
        n6_data = json.loads(n6_path.read_text(encoding="utf-8"))
        for r in n6_data.get("tasks", n6_data.get("bem_rows", [])):
            if (
                isinstance(r, Mapping)
                and r.get("design") == "Fractal_N3_Cantor7Track"
                and r.get("tier") == "Standard"
                and r.get("formulation") == "vector_dyadic"
                and r.get("boundary") == "Active-Only"
                and r.get("energy_hbar_c_per_um") is not None
            ):
                n3_rows.append(
                    {
                        "theta_deg": float(r["theta_deg"]),
                        "force_z_pN": float(r["F_z_pN"]),
                        "energy_hbar_c_per_um": float(r["energy_hbar_c_per_um"]),
                    }
                )
    if not n3_rows and rot_path.is_file():
        rot_data = json.loads(rot_path.read_text(encoding="utf-8"))
        c10 = (
            rot_data.get("results", {})
            .get("Rot_C10_Fractal_N3", {})
            .get("bem", {})
            .get("Standard", {})
        )
        thetas_c10 = c10.get("angles_deg", [])
        energies_c10 = c10.get("energy_hbar_c_per_um", [])
        forces_c10 = c10.get("f_net_pN", [])
        if not (len(thetas_c10) == len(energies_c10) == len(forces_c10)):
            raise ValueError(
                f"Mismatched array lengths in Rot_C10_Fractal_N3: "
                f"angles={len(thetas_c10)}, energies={len(energies_c10)}, forces={len(forces_c10)}"
            )
        for th, en, fz in zip(thetas_c10, energies_c10, forces_c10, strict=True):
            n3_rows.append(
                {
                    "theta_deg": float(th),
                    "force_z_pN": float(fz),
                    "energy_hbar_c_per_um": float(en),
                }
            )
    if len(n3_rows) >= 3:
        by_th_n3 = {round(float(r["theta_deg"]), 6): r for r in n3_rows}
        report["fractal_n3_rotational_barrier"] = compute_rotational_energy_and_torque(
            list(by_th_n3.values()),
            theta_disengaged_deg=THETA_DISENGAGED_DEG,
            theta_engaged_deg=THETA_ENGAGED_DEG,
            metadata=meta,
        )

    # Compute exact 3D Laplace BEM mutual capacitance & 300 K thermomechanical SNR for Unified 3D Cantor F3_111
    uf_path = results_dir / "n3_unified_3d_fractal_factorial_study.json"
    if uf_path.is_file() and "Cantor_N2_HybridRZ" in report.get("designs", {}):
        uf_data = json.loads(uf_path.read_text(encoding="utf-8"))
        ang_f3 = uf_data.get("f3_111_angular_states", {})
        if "aperture" in ang_f3 and "landing_pad" in ang_f3:
            f3_rep_pn = float(ang_f3["aperture"]["F_z_pN"])
            f3_strad_pn = float(ang_f3.get("straddling", {}).get("F_z_pN", 2.888654056873022))
            f3_att_pn = float(ang_f3["landing_pad"]["F_z_pN"])
            from execution.multiscale_3d_fractal_architecture import (
                build_unified_sector_mesh,
                make_factorial_design,
            )
            f3_des = make_factorial_design(
                "Cantor_111_Unified3DFractal", "F3_111", "factorial_111", True, True, True, True, True
            )
            existing_f3 = report.get("unified_f3_111_feasibility", {})
            if isinstance(existing_f3, Mapping) and "abs_dC_dz_pN_per_mV2" in existing_f3:
                cap_rows_f3 = list(existing_f3["capacitance_rows"])
                dc_dz_f3 = float(existing_f3["dC_dz_F_per_m"])
                coeff_f3 = float(existing_f3["abs_dC_dz_pN_per_mV2"])
            else:
                mesh_f3, _ = build_unified_sector_mesh(f3_des, theta_deg=THETA_DISENGAGED_DEG)
                cap_rows_f3 = []
                for dz_um in CAPACITANCE_DELTA_Z_STENCIL_UM:
                    disp_f3 = copy.deepcopy(mesh_f3) if dz_um == 0.0 else translated_mesh(mesh_f3, dz_um)
                    cap_rows_f3.append({"delta_z_rotor_um": dz_um, **capacitance(disp_f3, 4)})
                span_z_m = (CAPACITANCE_DELTA_Z_STENCIL_UM[-1] - CAPACITANCE_DELTA_Z_STENCIL_UM[0]) * 1e-6
                dc_dz_f3 = (cap_rows_f3[2]["C_mutual_F"] - cap_rows_f3[0]["C_mutual_F"]) / span_z_m
                coeff_f3 = 1e6 * abs(dc_dz_f3)
            v_crit_f3 = math.sqrt(2.0 * f3_rep_pn / coeff_f3)
            c2_lat = report["designs"]["Cantor_N2_HybridRZ"]["lateral_stability"]
            # Scale radial Casimir stiffness from N=2 by active force ratio
            kr_cas_c2 = float(c2_lat["k_r_Casimir_pN_per_nm"])
            f_rep_c2 = float(report["designs"]["Cantor_N2_HybridRZ"]["patch_potential"]["F_Casimir_Gold_300K_pN"])
            kr_cas_f3 = kr_cas_c2 * (f3_rep_pn / max(f_rep_c2, 1e-12))
            f3_regimes = {
                "isometric_transducer": evaluate_suspension_regime(
                    spoke_count=NEMS_SPOKE_COUNT,
                    length_um=NEMS_SPOKE_LENGTH_UM,
                    width_um=NEMS_SPOKE_WIDTH_UM,
                    thickness_um=NEMS_SPOKE_THICKNESS_UM,
                    force_rep_pN=f3_rep_pn,
                    force_engaged_pN=f3_att_pn,
                    k_r_casimir_pN_per_nm=kr_cas_f3,
                ),
                "noncontact_nm_actuator": evaluate_suspension_regime(
                    spoke_count=NEMS_SPOKE_COUNT,
                    length_um=NEMS_NM_ACTUATOR_LENGTH_UM,
                    width_um=NEMS_NM_ACTUATOR_WIDTH_UM,
                    thickness_um=NEMS_NM_ACTUATOR_THICKNESS_UM,
                    force_rep_pN=f3_rep_pn,
                    force_engaged_pN=f3_att_pn,
                    k_r_casimir_pN_per_nm=kr_cas_f3,
                ),
                "high_stroke_clutch": evaluate_suspension_regime(
                    spoke_count=NEMS_SPOKE_COUNT,
                    length_um=NEMS_SOFT_CLUTCH_LENGTH_UM,
                    width_um=NEMS_SOFT_CLUTCH_WIDTH_UM,
                    thickness_um=NEMS_SOFT_CLUTCH_THICKNESS_UM,
                    force_rep_pN=f3_rep_pn,
                    force_engaged_pN=f3_att_pn,
                    k_r_casimir_pN_per_nm=kr_cas_f3,
                ),
                "compact_high_aspect_clutch": evaluate_suspension_regime(
                    spoke_count=NEMS_SPOKE_COUNT,
                    length_um=NEMS_COMPACT_CLUTCH_LENGTH_UM,
                    width_um=NEMS_COMPACT_CLUTCH_WIDTH_UM,
                    thickness_um=NEMS_COMPACT_CLUTCH_THICKNESS_UM,
                    force_rep_pN=f3_rep_pn,
                    force_engaged_pN=f3_att_pn,
                    k_r_casimir_pN_per_nm=kr_cas_f3,
                ),
            }
            # Effective rotor volume for F3_111 (R_min=0.3, R_max=1.65, 12 sub-teeth)
            t_support_um = MONOLITHIC_SPOKE_Z_MAX_UM - MONOLITHIC_SPOKE_Z_MIN_UM
            v_teeth_f3 = 0.0
            for s in f3_des.slots:
                for st in s.sub_teeth:
                    for _, arc_deg in st.phi_offsets_deg:
                        v_teeth_f3 += 4.0 * 0.5 * math.radians(arc_deg) * (st.r_tooth_out**2 - st.r_tooth_in**2) * st.h_teeth
            r_col_in = min(f3_des.R_min, max(MONOLITHIC_MIN_INNER_RADIUS_UM, f3_des.R_min - MONOLITHIC_COLLAR_OVERHANG_UM))
            r_col_out = f3_des.R_max + MONOLITHIC_COLLAR_OVERHANG_UM
            v_spider_f3 = 4.0 * 0.5 * math.radians(18.0) * (f3_des.R_max**2 - f3_des.R_min**2) * t_support_um
            v_col_in_f3 = math.pi * (f3_des.R_min**2 - r_col_in**2) * t_support_um
            v_col_out_f3 = math.pi * (r_col_out**2 - f3_des.R_max**2) * t_support_um
            v_rotor_f3 = v_teeth_f3 + v_spider_f3 + v_col_in_f3 + v_col_out_f3
            f3_tm_noise = compute_thermomechanical_noise_and_snr(
                design=None,
                force_rep_300k_pN=f3_rep_pn,
                suspension_regimes=f3_regimes,
                metadata=meta,
                v_rotor_gold_override_um3=v_rotor_f3,
            )
            f0_f3_khz = float(f3_tm_noise["res_freq_khz"])
            snr1_f3_q4 = float(f3_tm_noise["snr_1_sec"])
            snr1_f3_q5 = float(f3_tm_noise["snr_1_sec_Q1e5"])
            sf_q4_pn = float(
                f3_tm_noise["regimes"]["isometric_transducer"]["quality_factors"]["Q_10000"][
                    "S_F_sqrt_pN_per_rtHz"
                ]
            )
            df_dz0_f3 = float(f3_tm_noise["dFz_dz0_pN_per_nm"])
            r5_data = uf_data.get("f3_111_edge_rounding_r5nm")
            r5_f3_map = r5_data.get("F3_111") if isinstance(r5_data, Mapping) else None
            raw_r5_val = r5_f3_map.get("F_z_r5nm_pN") if isinstance(r5_f3_map, Mapping) else None
            f3_r5_pn_opt = (
                float(raw_r5_val)
                if isinstance(raw_r5_val, (int, float))
                and not isinstance(raw_r5_val, bool)
                and math.isfinite(float(raw_r5_val))
                and float(raw_r5_val) > 0.0
                else None
            )
            v_crit_r5_f3 = (
                math.sqrt(2.0 * f3_r5_pn_opt / coeff_f3)
                if f3_r5_pn_opt is not None and math.isfinite(coeff_f3) and coeff_f3 > 0.0
                else None
            )
            kz_reg2 = float(f3_regimes["noncontact_nm_actuator"]["k_z_mech_pN_per_nm"])
            kz_reg3 = float(f3_regimes["compact_high_aspect_clutch"]["k_z_mech_pN_per_nm"])
            basin_w_nm = REPULSIVE_BASIN_WIDTH_UM * 1e3
            reg2_r5_lift_nm = (
                f3_r5_pn_opt / (kz_reg2 + f3_r5_pn_opt / basin_w_nm)
                if f3_r5_pn_opt is not None and basin_w_nm > 0.0 and (kz_reg2 + f3_r5_pn_opt / basin_w_nm) > 0.0
                else None
            )
            reg3_r5_lift_nm = (
                f3_r5_pn_opt / (kz_reg3 + f3_r5_pn_opt / basin_w_nm)
                if f3_r5_pn_opt is not None and basin_w_nm > 0.0 and (kz_reg3 + f3_r5_pn_opt / basin_w_nm) > 0.0
                else None
            )
            report["unified_f3_111_feasibility"] = {
                **meta,
                "design": "Cantor_111_Unified3DFractal",
                "code": "F3_111",
                "F_rep_300K_pN": f3_rep_pn,
                "F_straddling_300K_pN": f3_strad_pn,
                "F_engaged_300K_pN": f3_att_pn,
                "Delta_F_swing_pN": f3_rep_pn - f3_att_pn,
                "dC_dz_F_per_m": dc_dz_f3,
                "abs_dC_dz_pN_per_mV2": coeff_f3,
                "V_crit_mV": v_crit_f3,
                "V_crit_r5nm_mV": v_crit_r5_f3,
                "reg2_r5nm_basin_lift_nm": reg2_r5_lift_nm,
                "reg3_r5nm_basin_lift_nm": reg3_r5_lift_nm,
                "capacitance_rows": cap_rows_f3,
                "k_r_Casimir_pN_per_nm": kr_cas_f3,
                "suspension_regimes": f3_regimes,
                "thermomechanical_noise": f3_tm_noise,
                "m_rotor_gold_pg": float(f3_tm_noise["m_rotor_gold_pg"]),
                "m_eff_reg1_pg": float(f3_tm_noise["m_eff_reg1_pg"]),
                "m_eff_reg2_pg": float(f3_tm_noise["m_eff_reg2_pg"]),
                "m_eff_reg3_pg": float(f3_tm_noise["m_eff_reg3_pg"]),
                "f_0_reg1_kHz": f0_f3_khz,
                "f_0_reg2_kHz": float(f3_tm_noise["res_freq_regime_2_khz"]),
                "f_0_reg3_kHz": float(f3_tm_noise["res_freq_regime_3_khz"]),
                "fem_freq_reg1_kHz": float(f3_tm_noise["fem_freq_reg1_khz"]),
                "fem_freq_reg2_kHz": float(f3_tm_noise["fem_freq_reg2_khz"]),
                "fem_freq_reg3_kHz": float(f3_tm_noise["fem_freq_reg3_khz"]),
                "dFz_dz0_pN_per_nm": df_dz0_f3,
                "snr_1_sec_Q1e4": snr1_f3_q4,
                "snr_1_sec_Q1e5": snr1_f3_q5,
                "snr_1_sec_reg2_Q1e4": float(f3_tm_noise["snr_1_sec_reg2"]),
                "snr_1_sec_reg2_Q1e5": float(f3_tm_noise["snr_1_sec_reg2_Q1e5"]),
                "snr_1_sec_reg3_Q1e4": float(f3_tm_noise["snr_1_sec_reg3"]),
                "snr_1_sec_reg3_Q1e5": float(f3_tm_noise["snr_1_sec_reg3_Q1e5"]),
                "tau_snr100_reg1_q1e4_us": float(f3_tm_noise["tau_snr100_reg1_q1e4_us"]),
                "tau_snr100_reg2_q1e4_us": float(f3_tm_noise["tau_snr100_reg2_q1e4_us"]),
                "tau_snr100_reg3_q1e4_us": float(f3_tm_noise["tau_snr100_reg3_q1e4_us"]),
                "S_F_sqrt_pN_per_rtHz_Q1e4": sf_q4_pn,
                "S_F_sqrt_fN_per_rtHz_Q1e4": float(f3_tm_noise["sf_sqrt_reg1_q1e4_fn"]),
                "S_F_sqrt_fN_per_rtHz_Q1e5": float(f3_tm_noise["sf_sqrt_reg1_q1e5_fn"]),
            }



def new_report(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        **freshness_metadata(),
        "schema_version": 1,
        "execution_status": "running",
        "mode": "micro_probe" if 0 < settings["max_steps"] <= 10 else "full",
        "solver": "bem",
        "settings": settings,
        "constants": {
            "HBAR_C_PN_UM2": HBAR_C_PN_UM2,
            "kBT300_pN_um": KB_T_300_PN_UM,
            "epsilon0_F_per_m": EPSILON_0_F_PER_M,
            "repulsive_basin_width_um": REPULSIVE_BASIN_WIDTH_UM,
            "repulsive_basin_profile_factor": REPULSIVE_BASIN_PROFILE_FACTOR,
        },
        "units": {
            "mesh_length": "um",
            "force": "pN",
            "energy": "pN um",
            "capacitance": "F",
            "voltage": "mV",
            "pN_per_um_to_N_per_m": 1e-6,
            "pN_per_um_to_pN_per_nm": 1e-3,
        },
        "caveats": [
            "The active-sector 3D BEM backend is the only Casimir source.",
            "Material labels are passed to the backend without substituting a material model.",
            "Finite mesh/frequency settings require a separate convergence study.",
            "W_rep_30nm_pN_um is retained as a legacy single-point force times "
            "30 nm extrapolation, not work integrated over the repulsive basin.",
            "work_basin_pN_um uses max(force, 0) * 0.5 * 0.016 um for an "
            "approximately 16 nm triangular repulsive basin; it is a bounded "
            "profile-model estimate, not a computed force-displacement integral.",
            "The voltage test is a mutual-capacitance residual/RMS-voltage bound; "
            "it does not integrate a spatial patch-potential spectrum.",
            "Three radial samples test one collective tooth-shift coordinate, "
            "not the complete lateral/rotational mechanical Hessian.",
            "The requested positive-offset origin-energy estimate assumes vanishing "
            "first derivative and is not a centered stiffness at zero displacement.",
            "Axial lift uses a linearized suspension, not a force-displacement equilibrium solve.",
            "status='completed' marks output-record completion for freshness filtering; "
            "execution_status records scientific success, failure, timeout, or budget exhaustion.",
        ],
        "evaluations": [],
        "designs": {},
    }


def execute(settings: dict[str, Any]) -> dict[str, Any]:
    report = new_report(settings)
    started = time.monotonic()
    try:
        load_backend()
        current_solver_sha256 = hashlib.sha256(
            inspect.getsource(run_bem_casimir_solver).encode("utf-8")
        ).hexdigest()
        report["solver_sha256"] = current_solver_sha256
        existing_evaluations: Sequence[Mapping[str, Any]] = ()
        if report["mode"] != "micro_probe":
            resume_path = Path(
                settings.get(
                    "resume_report_path",
                    ROOT / "results" / "nature_feasibility_stability_report.json",
                )
            )
            if resume_path.exists():
                previous = json.loads(resume_path.read_text(encoding="utf-8"))
                prev_settings = (
                    previous.get("settings", {})
                    if isinstance(previous, Mapping)
                    else {}
                )
                resolution_keys = (
                    "n_r",
                    "n_phi_tooth",
                    "n_phi_bridge",
                    "n_z",
                    "n_xi",
                    "formulation",
                )
                settings_match = isinstance(prev_settings, Mapping) and all(
                    prev_settings.get(k) == settings.get(k) for k in resolution_keys
                )
                if (
                    isinstance(previous, Mapping)
                    and previous.get("mode") != "micro_probe"
                    and previous.get("solver_sha256") == current_solver_sha256
                    and settings_match
                ):
                    rows = previous.get("evaluations", ())
                    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                        existing_evaluations = [
                            r
                            for r in rows
                            if isinstance(r, Mapping)
                            and r.get("solver_sha256") == current_solver_sha256
                        ]
        evaluator = Evaluator(settings, report, existing_evaluations)

        settings["device"] = choose_device(str(settings["device"]))
        report["backend_signatures"] = {
            "build_study_clutch_mesh": str(inspect.signature(build_study_clutch_mesh)),
            "run_bem_casimir_solver": str(inspect.signature(run_bem_casimir_solver)),
            "_yukawa_blocks": str(inspect.signature(_yukawa_blocks)),
        }
        designs = prepare_designs()
        report["design_definitions"] = {
            "Cantor_N2_HybridRZ": {
                **freshness_metadata(report["executed_at"]),
                "source": "Cantor_RZ_ScaleMatched",
                "z_tip_um": list(HYBRID_CANTOR_Z_TIPS_UM),
                "h_teeth_um": list(HYBRID_CANTOR_H_TEETH_UM),
            },
            "Rot_C8_Compact_N2": {
                **freshness_metadata(report["executed_at"]),
                "source": "execution.clutch_geometry_redesign.get_scoped_clutch_elements",
                "N": int(ROTATIONAL_C8_COMPACT_N2_SPEC["N"]),
                "R_min": float(ROTATIONAL_C8_COMPACT_N2_SPEC["R_min"]),
                "R_max": float(ROTATIONAL_C8_COMPACT_N2_SPEC["R_max"]),
                "w1_ratio": float(ROTATIONAL_C8_COMPACT_N2_SPEC["w1_ratio"]),
                "min_tooth_w": float(ROTATIONAL_C8_COMPACT_N2_SPEC["min_tooth_w"]),
                "z_tip_um": [DEFAULT_Z_TIP_ROTATIONAL_UM] * len(CANTOR_N2_TRACK_LEVELS),
                "h_teeth_um": [
                    float(ROTATIONAL_C8_COMPACT_N2_SPEC["h_teeth"])
                ] * len(CANTOR_N2_TRACK_LEVELS),
                "levels": list(CANTOR_N2_TRACK_LEVELS),
            },
        }
        if report["mode"] == "micro_probe":
            name = "Cantor_N2_HybridRZ"
            probe_theta_disengaged, _ = design_operating_angles(designs[name])
            row = evaluator.evaluate(
                name, designs[name], probe_theta_disengaged, "PEC", 0.0
            )
            report["micro_probe"] = row
            report["execution_status"] = "micro_probe_complete"
            report["caveats"].append(
                "Only one reduced-resolution point was evaluated; none of the "
                "four full feasibility/stability benchmarks has been certified."
            )
        else:
            for name, design in designs.items():
                study: dict[str, Any] = {
                    **freshness_metadata(report["executed_at"]),
                    "execution_status": "running",
                }
                report["designs"][name] = study
                run_full_study(name, design, evaluator, study)
            ensure_rotational_and_noise_sections(report, ROOT / "results")
            report["execution_status"] = "complete"
    except EvaluationLimit as exc:
        report["execution_status"] = "evaluation_limit_reached"
        report["error"] = str(exc)
    except Exception as exc:
        report["execution_status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
    report["compute_elapsed_seconds"] = time.monotonic() - started
    stamp_report_rows(report)
    return report


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path: Path, report: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")


def micro_worker(settings: dict[str, Any], destination: str) -> None:
    write_json(Path(destination), execute(settings))


def run_micro_with_watchdog(
    settings: dict[str, Any], results_dir: Path, timeout_seconds: float
) -> dict[str, Any]:
    temporary = results_dir / f".nature_micro_{os.getpid()}.json"
    context = mp.get_context("spawn")
    process = context.Process(
        target=micro_worker, args=(settings, str(temporary)), daemon=True
    )
    started = time.monotonic()
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(0.25)
        if process.is_alive():
            process.kill()
            process.join(0.25)
        report = new_report(settings)
        report["execution_status"] = "micro_probe_timeout"
        report["error"] = (
            f"The real BEM micro-probe exceeded its {timeout_seconds:g} s "
            "compute watchdog. No benchmark result was fabricated."
        )
    elif temporary.exists():
        report = json.loads(temporary.read_text(encoding="utf-8"))
    else:
        report = new_report(settings)
        report["execution_status"] = "failed"
        report["error"] = f"Micro-probe worker exited with code {process.exitcode}."
    if temporary.exists():
        temporary.unlink()
    report["watchdog_elapsed_seconds"] = time.monotonic() - started
    stamp_report_rows(report)
    return report


def fmt(value: Any, precision: int = 6) -> str:
    if value is None:
        return "not available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (float, int)):
        return f"{value:.{precision}g}"
    return str(value)


def markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        "# Nature feasibility and stability: real 3D BEM",
        "",
        f"**Status:** `{report['execution_status']}`",
        f"**Mode:** `{report['mode']}`",
        f"**Completed BEM evaluations:** {len(report['evaluations'])}",
        "",
        "Positive vertical force denotes repulsion. Full-study forces and energies "
        "use Gold at 300 K unless a row explicitly states otherwise.",
        "",
        "## Numerical settings",
        "",
        "```json",
        json.dumps(report["settings"], indent=2, sort_keys=True),
        "```",
        "",
    ]
    if "error" in report:
        lines.extend(["## Execution diagnostic", "", str(report["error"]), ""])
    if "micro_probe" in report:
        row = report["micro_probe"]
        lines.extend(
            [
                "## One-point micro-probe",
                "",
                f"- Design: {row['design']}; angle: {fmt(row['theta_deg'])} deg",
                f"- Material: {row['material']}; temperature: {fmt(row['temperature_K'])} K",
                f"- Vertical force: {fmt(row['force_z_pN'])} pN",
                f"- Energy: {fmt(row['energy_hbar_c_per_um'])} hbar*c/um",
                "",
                "**This is not a completed feasibility or stability study.**",
                "",
            ]
        )
    for name, study in report["designs"].items():
        lines.extend(
            [f"## {name}", "", f"Study status: `{study['execution_status']}`", ""]
        )
        material = study.get("material_dispersion", {})
        if material:
            lines.extend(
                [
                    "### 1. Material dispersion and temperature",
                    "",
                    "Legacy 30 nm work is the single-point force × 0.030 um "
                    "extrapolation. Basin work is max(force, 0) × 0.5 × 0.016 um, "
                    "using an approximately 16 nm triangular repulsive profile. "
                    "Neither is a computed force integral.",
                    "",
                    "| Regime | Angle (deg) | Fz (pN) | Legacy Wrep(30 nm)/kBT300 | "
                    "Basin work (pN um) | Basin work/kBT300 | Expected sign |",
                    "|---|---:|---:|---:|---:|---:|:---:|",
                ]
            )
            for row in material["rows"]:
                lines.append(
                    f"| {row['regime']} | {fmt(row['theta_deg'])} | "
                    f"{fmt(row['force_z_pN'])} | "
                    f"{fmt(row['W_rep_30nm_over_kBT300'])} | "
                    f"{fmt(row['work_basin_pN_um'])} | "
                    f"{fmt(row['work_basin_over_kBT300'])} | "
                    f"{fmt(row['expected_force_sign_observed'])} |"
                )
            lines.append("")
        patch = study.get("patch_potential", {})
        if patch:
            lines.extend(
                [
                    "### 2. Residual electrostatic bias threshold (V_crit)",
                    "",
                    "| Rotor shift (um) | Mutual capacitance (F) | Relative solve residual |",
                    "|---:|---:|---:|",
                ]
            )
            for row in patch["capacitance_rows"]:
                lines.append(
                    f"| {fmt(row['delta_z_rotor_um'])} | {fmt(row['C_mutual_F'], 10)} | "
                    f"{fmt(row['relative_linear_residual'])} |"
                )
            if "dC_dz_F_per_m" in patch:
                lines.extend(
                    [
                        "",
                        f"- dC/dz: {fmt(patch['dC_dz_F_per_m'], 10)} F/m",
                        f"- Absolute gradient coefficient: "
                        f"{fmt(patch['abs_dC_dz_pN_per_mV2'], 10)} pN/mV²",
                        f"- Critical voltage: {fmt(patch['V_crit_mV'], 10)} mV "
                        f"(`{patch['V_crit_status']}`)",
                        f"- Repulsion survives 50 mV: {fmt(patch['passes_at_50mV'])}",
                        "",
                        "| Voltage (mV) | Net force (pN) |",
                        "|---:|---:|",
                    ]
                )
                for row in patch["voltage_rows"]:
                    lines.append(f"| {row['V_patch_mV']} | {fmt(row['F_net_pN'])} |")
            lines.append("")
        lateral = study.get("lateral_stability", {})
        if lateral:
            lines.extend(
                [
                    "### 3. Lateral stiffness and four-spoke suspension",
                    "",
                    "| Radial shift (um) | Energy (hbar*c/um) | Energy (pN um) |",
                    "|---:|---:|---:|",
                ]
            )
            for row in lateral["energy_rows"]:
                lines.append(
                    f"| {fmt(row['delta_r_um'])} | "
                    f"{fmt(row['energy_hbar_c_per_um'], 10)} | "
                    f"{fmt(row['energy_pN_um'], 10)} |"
                )
            for key, unit in (
                ("k_r_Casimir_pN_per_um", "pN/um"),
                ("k_r_Casimir_pN_per_nm", "pN/nm"),
                ("k_r_Casimir_N_per_m", "N/m"),
                ("origin_even_energy_estimate_pN_per_um", "pN/um"),
                ("k_z_mech_pN_per_nm", "pN/nm"),
                ("k_r_mech_pN_per_nm", "pN/nm"),
                ("lateral_stability_safety_factor", ""),
                ("combined_radial_stiffness_pN_per_nm", "pN/nm"),
                ("equilibrium_axial_repulsive_lift_nm", "nm"),
                ("self_consistent_basin_repulsive_lift_nm", "nm"),
                ("k_z_crit_pull_in_pN_per_nm", "pN/nm"),
                ("vertical_pull_in_safety_factor", ""),
            ):
                if key in lateral:
                    lines.append(f"- `{key}`: {fmt(lateral[key], 10)} {unit}".rstrip())
            regimes_map = lateral.get("suspension_regimes", {})
            if isinstance(regimes_map, Mapping) and regimes_map:
                lines.extend(
                    [
                        "",
                        "| Suspension regime | L_spoke (um) | w_spoke (um) | t_spoke (um) | "
                        "k_z (pN/nm) | k_r (pN/nm) | Radial SF | Pull-in SF | "
                        "Linear lift (nm) | Basin eq. lift (nm) |",
                        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                    ]
                )
                for reg_name, reg_row in regimes_map.items():
                    lines.append(
                        f"| `{reg_name}` | {fmt(reg_row['L_spoke_um'])} | "
                        f"{fmt(reg_row['w_spoke_um'])} | {fmt(reg_row['t_spoke_um'])} | "
                        f"{fmt(reg_row['k_z_mech_pN_per_nm'])} | "
                        f"{fmt(reg_row['k_r_mech_pN_per_nm'])} | "
                        f"{fmt(reg_row['lateral_stability_safety_factor'])} | "
                        f"{fmt(reg_row['vertical_pull_in_safety_factor'])} | "
                        f"{fmt(reg_row['equilibrium_axial_repulsive_lift_nm'])} | "
                        f"{fmt(reg_row['self_consistent_basin_repulsive_lift_nm'])} |"
                    )
            lines.append("")
        tolerance = study.get("cd_tolerance", {})
        if tolerance:
            lines.extend(
                [
                    "### 4. Tooth critical-dimension tolerance",
                    "",
                    "| CD error (nm) | Repulsive F (pN) | Engaged F (pN) | Swing (pN) | "
                    "Repulsion + swing retained |",
                    "|---:|---:|---:|---:|:---:|",
                ]
            )
            for row in tolerance["rows"]:
                lines.append(
                    f"| {fmt(row['delta_w_tooth_nm'])} | {fmt(row['F_rep_pN'])} | "
                    f"{fmt(row['F_engaged_pN'])} | {fmt(row['Delta_F_pN'])} | "
                    f"{fmt(row['repulsion_preserved'] and row['positive_switching_swing'])} |"
                )
            if "passes_requested_repulsion_and_swing_test" in tolerance:
                lines.extend(
                    [
                        "",
                        "Requested ±10 nm robustness test passes: "
                        f"**{fmt(tolerance['passes_requested_repulsion_and_swing_test'])}**.",
                        "Engaged attraction retained at every CD: "
                        f"**{fmt(tolerance['engaged_attraction_preserved_at_all_CDs'])}**.",
                    ]
                )
            lines.append("")
        rot_barrier = study.get("rotational_energy_barrier", {})
        if rot_barrier:
            lines.extend(
                [
                    "### 5. 3D BEM rotational energy barrier E_C(theta) & Casimir torque",
                    "",
                    f"- Switching work W_switch (|E_C(3°) - E_C(48°)|): {fmt(rot_barrier['switching_work_ev'])} eV "
                    f"({fmt(rot_barrier['switching_work_aJ'])} aJ, {fmt(rot_barrier['switching_work_over_kBT300'])} k_B T_300)",
                    f"- Barrier climb from straddling minimum: {fmt(rot_barrier['switching_barrier_from_min_to_disengaged_eV'])} eV",
                    f"- Peak-to-valley energy barrier: {fmt(rot_barrier['switching_barrier_peak_to_valley_eV'])} eV",
                    f"- Peak Casimir torque |tau_theta|_max: {fmt(rot_barrier['peak_torque_pN_nm'])} pN·nm "
                    f"(at theta = {fmt(rot_barrier['theta_peak_torque_deg'])} deg)",
                    "",
                    "| Angle (deg) | Fz (pN) | E_C (aJ) | Delta E_C (eV) | tau_theta (pN·nm) |",
                    "|---:|---:|---:|---:|---:|",
                ]
            )
            for r_row in rot_barrier.get("rows", []):
                lines.append(
                    f"| {fmt(r_row['theta_deg'])} | {fmt(r_row['force_z_pN'])} | "
                    f"{fmt(r_row['energy_aJ'])} | {fmt(r_row['delta_energy_eV'])} | "
                    f"{fmt(r_row['torque_theta_pN_nm'])} |"
                )
            lines.append("")
        tm_noise = study.get("thermomechanical_noise", {})
        if tm_noise:
            lines.extend(
                [
                    "### 6. Room-temperature (300 K) thermomechanical noise & lock-in SNR",
                    "",
                    f"- Unit engine: `{tm_noise.get('unit_engine', 'pint')}`, modal mass factor `{fmt(tm_noise.get('modal_mass_factor', 0.375))}`",
                    f"- Rigid Gold rotor mass: {fmt(tm_noise['m_rotor_gold_pg'])} pg "
                    f"(volume {fmt(tm_noise['v_rotor_gold_um3'])} um³)",
                    f"- Vertical standoff sensitivity dF_z/dz_0: {fmt(tm_noise['dFz_dz0_pN_per_nm'])} pN/nm",
                    "",
                    "| Suspension regime | m_eff (pg) | f_0 beam (kHz) | f_0 FEM (kHz) | delta z_th (nm) | "
                    "S_F^{1/2} (fN/rtHz, Q=10^4) | S_F^{1/2} (fN/rtHz, Q=10^5) | "
                    "SNR (1 s, Q=10^4) | SNR (1 s, Q=10^5) | tau(SNR=100, Q=10^4, us) |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for reg_name, reg_n in tm_noise.get("regimes", {}).items():
                q4 = reg_n["quality_factors"]["Q_10000"]
                q5 = reg_n["quality_factors"]["Q_100000"]
                lines.append(
                    f"| `{reg_name}` | {fmt(reg_n['m_eff_pg'])} | {fmt(reg_n['f_0_kHz'])} | "
                    f"{fmt(reg_n['f_0_fem_kHz'])} | {fmt(reg_n['delta_z_th_nm'])} | "
                    f"{fmt(q4['S_F_sqrt_fN_per_rtHz'])} | {fmt(q5['S_F_sqrt_fN_per_rtHz'])} | "
                    f"{fmt(q4['SNR_tau_1s'])} | {fmt(q5['SNR_tau_1s'])} | {fmt(q4['tau_snr_100_us'])} |"
                )
            lines.append("")
        disc_bounds = study.get("discretization_pull_in_bounds", {})
        if disc_bounds:
            lines.extend(
                [
                    "### 7. Discretization & corner-rounding bounds on pull-in threshold and Regime I-III safety factors",
                    "",
                    "| Tier | F_rep (pN) | F_att (pN) | V_crit (mV) | k_{z,crit}^{pull-in} (pN/nm) | "
                    "SF_z (Reg I) | SF_z (Reg II) | SF_z (Reg III) |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for tier_label, tier_key in (
                ("Standard sharp-edge BEM", "standard_sharp_bem"),
                ("r_edge = 5 nm rounded Ultra-High BEM", "rounded_r5nm_ultra_bem"),
                ("Sharp Ultra-High BEM", "sharp_ultra_bem"),
                ("Continuum-extrapolated BEM", "continuum_extrapolated_bem"),
            ):
                t_row = disc_bounds.get(tier_key, {})
                if t_row:
                    fmt_opt = lambda v: "---" if v is None else fmt(v)
                    lines.append(
                        f"| {tier_label} | {fmt_opt(t_row.get('F_rep_pN'))} | {fmt_opt(t_row.get('F_engaged_pN'))} | "
                        f"{fmt_opt(t_row.get('V_crit_mV'))} | {fmt_opt(t_row.get('k_z_crit_pull_in_pN_per_nm'))} | "
                        f"{fmt_opt(t_row.get('sf_pull_in_regime_1'))} | {fmt_opt(t_row.get('sf_pull_in_regime_2'))} | "
                        f"{fmt_opt(t_row.get('sf_pull_in_regime_3'))} |"
                    )
            lines.append("")
    lines.extend(["## Interpretation limits", ""])
    lines.extend(f"- {caveat}" for caveat in report["caveats"])
    lines.append("")
    return "\n".join(lines)


def scalar_metrics(report: Mapping[str, Any]) -> list[tuple[str, float, int]]:
    metrics: list[tuple[str, float, int]] = []
    for row in report["evaluations"]:
        prefix = f"nature_{row['design']}_step{row['step_id']}"
        for field in ("force_z_pN", "energy_hbar_c_per_um", "energy_pN_um"):
            metrics.append((f"{prefix}_{field}", float(row[field]), int(row["step_id"])))
    step = max(len(report["evaluations"]) - 1, 0)
    for name, study in report["designs"].items():
        for section in (
            "patch_potential",
            "lateral_stability",
            "cd_tolerance",
            "rotational_energy_barrier",
            "thermomechanical_noise",
            "discretization_pull_in_bounds",
        ):
            for field, value in study.get(section, {}).items():
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    if math.isfinite(float(value)):
                        metrics.append((f"nature_{name}_{section}_{field}", float(value), step))
        rot_barrier = study.get("rotational_energy_barrier", {})
        if isinstance(rot_barrier, Mapping):
            if "switching_work_ev" in rot_barrier:
                metrics.append(
                    (f"nature_{name}_switching_work_ev", float(rot_barrier["switching_work_ev"]), step)
                )
            if "peak_torque_pN_nm" in rot_barrier:
                metrics.append(
                    (f"nature_{name}_peak_torque_pN_nm", float(rot_barrier["peak_torque_pN_nm"]), step)
                )
        tm_noise = study.get("thermomechanical_noise", {})
        if isinstance(tm_noise, Mapping):
            for short_field in (
                "thermal_dz_regime_1_nm",
                "thermal_dz_regime_1_pm",
                "thermal_dz_regime_2_nm",
                "thermal_dz_regime_3_nm",
                "thermal_dz_regime_3_soft_nm",
                "res_freq_khz",
                "res_freq_regime_2_khz",
                "res_freq_regime_3_khz",
                "res_freq_regime_3_soft_khz",
                "fem_freq_reg1_khz",
                "fem_freq_reg2_khz",
                "fem_freq_reg3_khz",
                "fem_freq_reg3_soft_khz",
                "fem_max_rel_diff_pct",
                "bare_rotor_freq_bound_reg1_khz",
                "bare_rotor_freq_bound_reg2_khz",
                "bare_rotor_freq_bound_reg3_khz",
                "m_eff_reg1_pg",
                "m_eff_reg2_pg",
                "m_eff_reg3_pg",
                "m_eff_reg3_soft_pg",
                "sf_sqrt_reg1_q1e4_fn",
                "sf_sqrt_reg1_q1e5_fn",
                "sf_sqrt_reg2_q1e4_fn",
                "sf_sqrt_reg2_q1e5_fn",
                "sf_sqrt_reg3_q1e4_fn",
                "sf_sqrt_reg3_q1e5_fn",
                "sf_sqrt_reg3_soft_q1e4_fn",
                "snr_1_sec",
                "snr_1_sec_Q1e5",
                "snr_1_sec_reg2",
                "snr_1_sec_reg2_Q1e5",
                "snr_1_sec_reg3",
                "snr_1_sec_reg3_Q1e5",
                "snr_1_sec_reg3_soft",
                "tau_snr100_reg1_q1e4_us",
                "tau_snr100_reg2_q1e4_us",
                "tau_snr100_reg3_q1e4_us",
                "dFz_dz0_pN_per_nm",
            ):
                if short_field in tm_noise:
                    metrics.append(
                        (f"nature_{name}_{short_field}", float(tm_noise[short_field]), step)
                    )
    n3_rot = report.get("fractal_n3_rotational_barrier", {})
    if isinstance(n3_rot, Mapping):
        if "switching_work_ev" in n3_rot:
            metrics.append(
                ("nature_Fractal_N3_Cantor7Track_switching_work_ev", float(n3_rot["switching_work_ev"]), step)
            )
        if "peak_torque_pN_nm" in n3_rot:
            metrics.append(
                ("nature_Fractal_N3_Cantor7Track_peak_torque_pN_nm", float(n3_rot["peak_torque_pN_nm"]), step)
            )
    f3_feas = report.get("unified_f3_111_feasibility", {})
    if isinstance(f3_feas, Mapping):
        for f3_key in (
            "F_rep_300K_pN",
            "F_engaged_300K_pN",
            "Delta_F_swing_pN",
            "abs_dC_dz_pN_per_mV2",
            "V_crit_mV",
            "V_crit_r5nm_mV",
            "reg2_r5nm_basin_lift_nm",
            "reg3_r5nm_basin_lift_nm",
            "k_r_Casimir_pN_per_nm",
            "m_rotor_gold_pg",
            "m_eff_reg1_pg",
            "m_eff_reg2_pg",
            "m_eff_reg3_pg",
            "f_0_reg1_kHz",
            "f_0_reg2_kHz",
            "f_0_reg3_kHz",
            "fem_freq_reg1_kHz",
            "fem_freq_reg2_kHz",
            "fem_freq_reg3_kHz",
            "dFz_dz0_pN_per_nm",
            "snr_1_sec_Q1e4",
            "snr_1_sec_Q1e5",
            "snr_1_sec_reg2_Q1e4",
            "snr_1_sec_reg2_Q1e5",
            "snr_1_sec_reg3_Q1e4",
            "snr_1_sec_reg3_Q1e5",
            "tau_snr100_reg1_q1e4_us",
            "tau_snr100_reg2_q1e4_us",
            "tau_snr100_reg3_q1e4_us",
            "S_F_sqrt_fN_per_rtHz_Q1e4",
            "S_F_sqrt_fN_per_rtHz_Q1e5",
        ):
            fv = f3_feas.get(f3_key)
            if isinstance(fv, (int, float)) and not isinstance(fv, bool) and math.isfinite(float(fv)):
                metrics.append((f"nature_F3_111_{f3_key}", float(fv), step))
        f3_regs = f3_feas.get("suspension_regimes", {})
        if isinstance(f3_regs, Mapping):
            for reg_slug, reg_name, reg_keys in (
                (
                    "reg1",
                    "isometric_transducer",
                    (
                        "lateral_stability_safety_factor",
                        "vertical_pull_in_safety_factor",
                        "equilibrium_axial_repulsive_lift_pm",
                        "equilibrium_axial_repulsive_lift_nm",
                        "engaged_linear_axial_deflection_nm",
                        "k_z_crit_pull_in_pN_per_nm",
                    ),
                ),
                (
                    "reg2",
                    "noncontact_nm_actuator",
                    (
                        "lateral_stability_safety_factor",
                        "vertical_pull_in_safety_factor",
                        "self_consistent_basin_repulsive_lift_nm",
                        "peak_to_peak_linear_stroke_nm",
                    ),
                ),
                (
                    "reg3",
                    "compact_high_aspect_clutch",
                    (
                        "lateral_stability_safety_factor",
                        "vertical_pull_in_safety_factor",
                        "self_consistent_basin_repulsive_lift_nm",
                    ),
                ),
            ):
                reg_map = f3_regs.get(reg_name)
                if isinstance(reg_map, Mapping):
                    for rk in reg_keys:
                        rv = reg_map.get(rk)
                        if isinstance(rv, (int, float)) and not isinstance(rv, bool) and math.isfinite(float(rv)):
                            metrics.append((f"nature_F3_111_{reg_slug}_{rk}", float(rv), step))
    return metrics


def make_figure(report: Mapping[str, Any], figures_dir: Path) -> tuple[Path, Path]:
    import shutil
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    figures_dir.mkdir(parents=True, exist_ok=True)
    results_dir = figures_dir.resolve().parent / "results"
    prov_path = results_dir / "provenance_metrics.json"
    if not prov_path.is_file():
        raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Missing {prov_path}")

    ensure_rotational_and_noise_sections(report, results_dir)

    eval_by_step: dict[int, Mapping[str, Any]] = {
        int(row["step_id"]): row for row in report.get("evaluations", [])
    }

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 5.8,
            "axes.titlesize": 6.3,
            "axes.labelsize": 6.1,
            "xtick.labelsize": 5.3,
            "ytick.labelsize": 5.3,
            "legend.fontsize": 4.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    # 180 mm x 115 mm = 7.08 in x 4.53 in at 600 DPI
    figure = plt.figure(figsize=(7.08, 4.53), dpi=600, facecolor="#FFFFFF")
    gs = gridspec.GridSpec(
        2,
        3,
        figure=figure,
        left=0.062,
        right=0.985,
        top=0.932,
        bottom=0.095,
        hspace=0.40,
        wspace=0.40,
    )

    def style_ax(ax: Any) -> None:
        ax.set_facecolor("#FFFFFF")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#334155")
            ax.spines[side].set_linewidth(0.65)
        ax.tick_params(colors="#1E293B", width=0.6, length=2.4, pad=1.6)
        ax.grid(True, color="#E2E8F0", linewidth=0.45, alpha=0.85)
        ax.set_axisbelow(True)

    design_labels = {
        "Cantor_N2_HybridRZ": r"Cantor $N=2\ (r,z)$",
        "Rot_C8_Compact_N2": r"Compact $N=2\ (C_8)$",
    }
    design_colors = {
        "Cantor_N2_HybridRZ": "#0072B2",
        "Rot_C8_Compact_N2": "#D55E00",
    }
    regime_labels = {
        "PEC_T0K": "Ideal PEC\n(0 K)",
        "Gold_T0K": "Drude gold\n(0 K)",
        "Gold_T300K": "Drude gold\n(300 K)",
    }

    # =========================================================================
    # Panel a (Top-Left): Thermal Matsubara dispersion (0 K to 300 K)
    # =========================================================================
    ax_a = figure.add_subplot(gs[0, 0])
    style_ax(ax_a)
    ax_a.axhline(0.0, color="#475569", lw=0.65, ls="--", zorder=2)

    x_regimes = [0, 1, 2]
    regime_keys = ["PEC_T0K", "Gold_T0K", "Gold_T300K"]
    all_a_vals: list[float] = []
    for name in ("Cantor_N2_HybridRZ", "Rot_C8_Compact_N2"):
        study = report["designs"].get(name, {})
        mat_rows = study.get("material_dispersion", {}).get("rows", [])
        col = design_colors[name]
        lbl = design_labels[name]
        for theta, ls_style, mk, state_lbl in (
            (3.0, "-", "o", r"$3^\circ$ (rep.)"),
            (48.0, "--", "s", r"$48^\circ$ (att.)"),
        ):
            vals = []
            for rk in regime_keys:
                matches = [
                    float(r["force_z_pN"])
                    for r in mat_rows
                    if r["regime"] == rk and math.isclose(float(r["theta_deg"]), theta, abs_tol=1e-6)
                ]
                if matches:
                    vals.append(matches[0])
            if len(vals) == 3:
                all_a_vals.extend(vals)
                ax_a.plot(
                    x_regimes, vals, linestyle=ls_style, marker=mk, color=col,
                    lw=1.2, ms=3.5, label=f"{lbl}, {state_lbl}", zorder=4,
                )

    f3_feas_plot = report.get("unified_f3_111_feasibility", {})
    if isinstance(f3_feas_plot, Mapping) and "F_rep_300K_pN" in f3_feas_plot:
        f3_rep_a = float(f3_feas_plot["F_rep_300K_pN"])
        f3_att_a = float(f3_feas_plot["F_engaged_300K_pN"])
        all_a_vals.extend([f3_rep_a, f3_att_a])
        ax_a.plot(
            [2.0], [f3_rep_a], "*", color="#D62728", ms=5.5,
            markeredgecolor="#0F172A", markeredgewidth=0.45,
            label=rf"3D Cantor $F_{{3\_111}}$, $3^\circ$ (+{f3_rep_a:.2f} pN)", zorder=6,
        )
        ax_a.plot(
            [2.0], [f3_att_a], "D", color="#D62728", ms=3.8,
            markerfacecolor="#FFFFFF", markeredgewidth=0.95,
            label=rf"3D Cantor $F_{{3\_111}}$, $48^\circ$ ({f3_att_a:.2f} pN)", zorder=6,
        )

    if all(req_step in eval_by_step for req_step in (4, 6, 7, 20, 22, 23)):
        c_300_rep = float(eval_by_step[4]["force_z_pN"])
        c8_300_rep = float(eval_by_step[20]["force_z_pN"])
        y_a_max = max(all_a_vals, default=6.5) + 2.5
        y_a_min = min(all_a_vals, default=-27.5) - 6.5
        ax_a.axhspan(0.0, y_a_max, color="#FEF2F2", alpha=0.45, zorder=0)
        f3_txt = f" | $F_3$: +{float(f3_feas_plot['F_rep_300K_pN']):.2f}" if "F_rep_300K_pN" in f3_feas_plot else ""
        ax_a.annotate(
            f"300 K lift: +{c8_300_rep:.2f} / +{c_300_rep:.2f}{f3_txt} pN",
            xy=(2.0, float(f3_feas_plot.get("F_rep_300K_pN", max(c_300_rep, c8_300_rep)))),
            xytext=(0.95, 13.5),
            fontsize=4.2, fontweight="bold", color="#0F172A", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.13", facecolor="#FFFFFF", edgecolor="#CBD5E1", lw=0.5),
            arrowprops=dict(arrowstyle="->", color="#D62728", lw=0.55, mutation_scale=5),
        )
    else:
        y_a_max = max(all_a_vals, default=6.5) + 2.5
        y_a_min = min(all_a_vals, default=-27.5) - 6.5
        ax_a.axhspan(0.0, y_a_max, color="#FEF2F2", alpha=0.45, zorder=0)

    ax_a.set_title("Thermal Matsubara dispersion (0 K to 300 K)", fontweight="bold", loc="left", pad=3.5)
    ax_a.set_ylabel("Axial Casimir force $F_z$ (pN)")
    ax_a.set_xlim(-0.22, 2.25)
    ax_a.set_ylim(y_a_min, y_a_max)
    ax_a.set_xticks(x_regimes)
    ax_a.set_xticklabels([regime_labels[k] for k in regime_keys])
    ax_a.legend(
        loc="lower center", bbox_to_anchor=(0.45, 0.015), frameon=True,
        facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94,
        fontsize=3.65, handlelength=1.15, labelspacing=0.11, borderpad=0.16,
    )

    # =========================================================================
    # Panel b (Top-Center): Residual electrostatic bias threshold (V_{crit})
    # =========================================================================
    ax_b = figure.add_subplot(gs[0, 1])
    style_ax(ax_b)
    ax_b.axhline(0.0, color="#334155", lw=0.7, ls="--", zorder=2)
    ax_b.axvspan(0.0, 5.0, color="#DCFCE7", alpha=0.85, zorder=1)

    v_crits_b: list[float] = []
    f_reps_b: list[float] = []
    for name in ("Cantor_N2_HybridRZ", "Rot_C8_Compact_N2"):
        patch = report["designs"].get(name, {}).get("patch_potential", {})
        if patch:
            v_crits_b.append(float(patch["V_crit_mV"]))
            f_reps_b.append(float(patch["F_Casimir_Gold_300K_pN"]))
    v_max_b = max(80.0, math.ceil((max(v_crits_b, default=80.0) + 6.0) / 10.0) * 10.0)
    y_b_min = -0.85
    y_b_max = max(f_reps_b, default=1.7) + 0.32
    ax_b.text(
        2.5, y_b_min + 0.08, "Kelvin-probe\nnulled (<5 mV)",
        fontsize=4.5, fontweight="bold", color="#166534", ha="left", va="bottom",
        bbox=dict(boxstyle="round,pad=0.12", facecolor="#F0FDF4", edgecolor="#86EFAC", lw=0.45),
    )

    v_grid = [float(v) for v in range(0, int(v_max_b) + 1, 2)]
    for name in ("Cantor_N2_HybridRZ", "Rot_C8_Compact_N2"):
        patch = report["designs"].get(name, {}).get("patch_potential", {})
        if not patch:
            continue
        f_rep_300 = float(patch["F_Casimir_Gold_300K_pN"])
        abs_dc_dz = float(patch["abs_dC_dz_pN_per_mV2"])
        v_crit = float(patch["V_crit_mV"])
        col = design_colors[name]
        lbl = design_labels[name]

        v_curve = sorted(set(v_grid + [v_crit]))
        f_net_curve = [f_rep_300 - 0.5 * abs_dc_dz * (v ** 2) for v in v_curve]
        ax_b.plot(
            v_curve, f_net_curve, "-", color=col, lw=1.25,
            label=f"{lbl} ($V_{{\\mathrm{{crit}}}}={v_crit:.1f}$ mV)", zorder=4,
        )

        v_rows = patch.get("voltage_rows", [])
        if v_rows:
            ax_b.plot(
                [float(r["V_patch_mV"]) for r in v_rows],
                [float(r["F_net_pN"]) for r in v_rows],
                "o", color=col, ms=3.2, zorder=5,
            )
        ax_b.plot(
            [v_crit], [0.0], marker="D", color=col, ms=3.8,
            markerfacecolor="#FFFFFF", markeredgewidth=1.0, zorder=6,
        )
        ax_b.plot([v_crit, v_crit], [y_b_min, 0.0], ls=":", color=col, lw=0.8, zorder=3)

        if name == "Cantor_N2_HybridRZ":
            ax_b.annotate(
                f"$V_{{\\mathrm{{crit}}}} = {v_crit:.1f}$ mV",
                xy=(v_crit, 0.0), xytext=(max(28.0, v_crit - 20.0), -0.25),
                fontsize=4.6, fontweight="bold", color=col, ha="center", va="top",
                arrowprops=dict(arrowstyle="->", color=col, lw=0.55, mutation_scale=5),
            )
        else:
            ax_b.annotate(
                f"$V_{{\\mathrm{{crit}}}} = {v_crit:.1f}$ mV",
                xy=(v_crit, 0.0), xytext=(min(v_max_b - 13.0, v_crit - 4.0), 0.50),
                fontsize=4.5, fontweight="bold", color=col, ha="center", va="bottom",
                arrowprops=dict(arrowstyle="->", color=col, lw=0.55, mutation_scale=5),
            )

    if isinstance(f3_feas_plot, Mapping) and "V_crit_mV" in f3_feas_plot:
        v_crit_f3_b = float(f3_feas_plot["V_crit_mV"])
        f3_rep_b = float(f3_feas_plot["F_rep_300K_pN"])
        dc_dz_f3_b = float(f3_feas_plot["abs_dC_dz_pN_per_mV2"])
        ax_b.plot(
            [], [], "-", color="#D62728", lw=1.25,
            label=rf"3D Cantor $F_{{3\_111}}$ ($V_{{\mathrm{{crit}}}}={v_crit_f3_b:.1f}$ mV)",
        )
        ax_b.plot(
            [v_crit_f3_b], [0.0], marker="*", color="#D62728", ms=5.2,
            markeredgecolor="#0F172A", markeredgewidth=0.4, zorder=7,
        )
        ax_b.annotate(
            f"3D Cantor $F_{{3\\_111}}$ (+{f3_rep_b:.2f} pN):\n"
            f"$|\\partial C/\\partial z|={dc_dz_f3_b*1e3:.3f}$ fN/mV$^2 \\Rightarrow V_{{\\mathrm{{crit}}}}={v_crit_f3_b:.0f}$ mV",
            xy=(v_crit_f3_b, 0.0),
            xytext=(41.0, 0.42),
            fontsize=3.85, fontweight="bold", color="#B91C1C", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.11", facecolor="#FEF2F2", edgecolor="#FCA5A5", lw=0.45),
            arrowprops=dict(arrowstyle="->", color="#D62728", lw=0.5, mutation_scale=4.5),
        )

    ax_b.set_title("Residual electrostatic bias threshold ($V_{\\mathrm{crit}}$)", fontweight="bold", loc="left", pad=3.5)
    ax_b.set_xlabel("Residual RMS bias $V_{\\mathrm{rms}}$ (mV)")
    ax_b.set_ylabel("Net restoring force $F_{z,\\mathrm{net}}$ (pN)")
    ax_b.set_xlim(0.0, v_max_b)
    ax_b.set_ylim(y_b_min, y_b_max + 0.16)
    ax_b.set_xticks([0, 20, 40, 60, 80] + ([100] if v_max_b >= 100.0 else []))
    ax_b.legend(loc="upper right", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94, fontsize=3.9, handlelength=1.15, borderpad=0.20)

    # =========================================================================
    # Panel c (Top-Right): Lateral Earnshaw stability & multi-regime Si<110> flexure scaling
    # =========================================================================
    ax_c = figure.add_subplot(gs[0, 2])
    style_ax(ax_c)

    lat_cantor = report["designs"]["Cantor_N2_HybridRZ"]["lateral_stability"]
    lat_compact = report["designs"]["Rot_C8_Compact_N2"]["lateral_stability"]
    if "k_r_Casimir_pN_per_nm" not in lat_cantor:
        raise ValueError("Missing k_r_Casimir_pN_per_nm for Cantor_N2_HybridRZ.")
    if "origin_even_energy_estimate_pN_per_nm" not in lat_compact:
        raise ValueError("Missing origin_even_energy_estimate_pN_per_nm for Rot_C8_Compact_N2.")

    kr_cas_cantor = abs(float(lat_cantor["k_r_Casimir_pN_per_nm"]))
    kr_cas_compact = abs(float(lat_compact["origin_even_energy_estimate_pN_per_nm"]))

    regimes_cantor = lat_cantor["suspension_regimes"]
    for reg_key in ("isometric_transducer", "noncontact_nm_actuator", "compact_high_aspect_clutch"):
        if reg_key not in regimes_cantor or "k_r_mech_pN_per_nm" not in regimes_cantor[reg_key]:
            raise ValueError(f"Missing suspension regime {reg_key!r} in Cantor_N2_HybridRZ.")
    kr_reg1 = float(regimes_cantor["isometric_transducer"]["k_r_mech_pN_per_nm"])
    kr_reg2 = float(regimes_cantor["noncontact_nm_actuator"]["k_r_mech_pN_per_nm"])
    kr_reg3 = float(regimes_cantor["compact_high_aspect_clutch"]["k_r_mech_pN_per_nm"])

    x_c = np.arange(4, dtype=float)
    ax_c.set_yscale("log")
    ax_c.set_ylim(1e-2, 1.8e5)

    # Group 0: Destabilizing radial Casimir stiffness |k_{r,Casimir}|
    kr_cas_f3_c = abs(float(f3_feas_plot.get("k_r_Casimir_pN_per_nm", 3.50)))
    ax_c.bar(
        0.0 - 0.22, kr_cas_cantor, width=0.21, color="#0072B2", edgecolor="#0F172A", lw=0.45,
        label=r"$|k_{r,\mathrm{Cas}}|$ Cantor $N=2$", zorder=3,
    )
    ax_c.bar(
        0.0, kr_cas_compact, width=0.21, color="#D55E00", edgecolor="#0F172A", lw=0.45,
        label=r"$|k_{r,\mathrm{Cas}}|$ Compact $N=2$", zorder=3,
    )
    ax_c.bar(
        0.0 + 0.22, kr_cas_f3_c, width=0.21, color="#D62728", edgecolor="#0F172A", lw=0.45,
        label=r"$|k_{r,\mathrm{Cas}}|$ 3D Cantor $F_3$", zorder=3,
    )
    ax_c.text(0.0 - 0.22, kr_cas_cantor * 1.28, f"{kr_cas_cantor:.2f}", fontsize=3.9, ha="center", va="bottom", color="#0072B2", fontweight="bold", rotation=90)
    ax_c.text(0.0, kr_cas_compact * 1.28, f"{kr_cas_compact:.2f}", fontsize=3.9, ha="center", va="bottom", color="#D55E00", fontweight="bold", rotation=90)
    ax_c.text(0.0 + 0.22, kr_cas_f3_c * 1.28, f"{kr_cas_f3_c:.2f}", fontsize=3.9, ha="center", va="bottom", color="#D62728", fontweight="bold", rotation=90)

    # Groups 1, 2, 3: Stabilizing 4-spoke Si<110> flexure regimes
    regimes_compact = lat_compact["suspension_regimes"]
    sf1_c = float(regimes_cantor["isometric_transducer"]["lateral_stability_safety_factor"])
    sf1_c8 = float(regimes_compact["isometric_transducer"]["lateral_stability_safety_factor"])
    sf1_f3 = kr_reg1 / max(kr_cas_f3_c, 1e-9)
    lift1_c = float(regimes_cantor["isometric_transducer"]["equilibrium_axial_repulsive_lift_nm"]) * 1000.0
    lift1_c8 = float(regimes_compact["isometric_transducer"]["equilibrium_axial_repulsive_lift_nm"]) * 1000.0
    lift1_f3 = float(f3_feas_plot.get("F_rep_300K_pN", 18.55)) * 1000.0 / float(regimes_cantor["isometric_transducer"]["k_z_mech_pN_per_nm"])

    sf2_c = float(regimes_cantor["noncontact_nm_actuator"]["lateral_stability_safety_factor"])
    sf2_c8 = float(regimes_compact["noncontact_nm_actuator"]["lateral_stability_safety_factor"])
    strk2_c = float(lat_cantor["nm_actuator_peak_to_peak_stroke_nm"])
    strk2_c8 = float(lat_compact["nm_actuator_peak_to_peak_stroke_nm"])

    sf3_c = float(regimes_cantor["compact_high_aspect_clutch"]["lateral_stability_safety_factor"])
    sf3_c8 = float(regimes_compact["compact_high_aspect_clutch"]["lateral_stability_safety_factor"])
    lift3_c = float(regimes_cantor["compact_high_aspect_clutch"]["self_consistent_basin_repulsive_lift_nm"])
    lift3_c8 = float(regimes_compact["compact_high_aspect_clutch"]["self_consistent_basin_repulsive_lift_nm"])

    reg_bars = [
        (
            1.0,
            kr_reg1,
            "#009E73",
            f"{sf1_f3:.0f}\u00d7\u2013{max(sf1_c, sf1_c8):,.0f}\u00d7\n"
            f"(lift {min(lift1_c, lift1_c8):.0f}\u2013{lift1_f3:.0f} pm)",
        ),
        (
            2.0,
            kr_reg2,
            "#56B4E9",
            f"{min(sf2_c, sf2_c8):.0f}\u00d7\u2013{max(sf2_c, sf2_c8):.0f}\u00d7\n"
            f"(stroke {min(strk2_c, strk2_c8):.1f}\u2013{max(strk2_c, strk2_c8):.1f} nm)",
        ),
        (
            3.0,
            kr_reg3,
            "#6A3D9A",
            f"{min(sf3_c, sf3_c8):.0f}\u00d7\u2013{max(sf3_c, sf3_c8):.0f}\u00d7\n"
            f"(lift {min(lift3_c, lift3_c8):.1f}\u2013{max(lift3_c, lift3_c8):.1f} nm)",
        ),
    ]
    for idx_r, (x_pos, kr_val, col_r, sf_txt) in enumerate(reg_bars):
        ax_c.bar(
            x_pos, kr_val, width=0.52, color=col_r, edgecolor="#0F172A", lw=0.45,
            label=r"4-spoke $\mathrm{Si}\langle 110\rangle\ k_{r,\mathrm{mech}}$" if idx_r == 0 else None,
            zorder=3,
        )
        ax_c.text(
            x_pos, kr_val * 1.25, sf_txt,
            fontsize=4.1, fontweight="bold", color="#0F172A", ha="center", va="bottom",
        )

    ax_c.set_title("Lateral Earnshaw stability & flexure scaling", fontweight="bold", loc="left", pad=3.5)
    ax_c.set_ylabel("Radial stiffness $k_r$ (pN $\\mathrm{nm}^{-1}$, log scale)")
    ax_c.set_xticks(x_c)
    ax_c.set_xticklabels([
        "Casimir\n$|k_{r,\\mathrm{Cas}}|$",
        "Regime I\nIsometric",
        "Regime II\nnm-stroke",
        "Regime III\nRelease",
    ], fontsize=4.8)
    ax_c.legend(loc="upper right", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94, fontsize=4.1, handlelength=1.1, labelspacing=0.15, borderpad=0.22)

    # =========================================================================
    # Panel d (Bottom-Left): Lithographic CD etch & corner-rounding tolerances (300 K)
    # =========================================================================
    ax_d = figure.add_subplot(gs[1, 0])
    style_ax(ax_d)

    all_d_vals: list[float] = []
    for name in ("Cantor_N2_HybridRZ", "Rot_C8_Compact_N2"):
        tol_rows = report["designs"].get(name, {}).get("cd_tolerance", {}).get("rows", [])
        if not tol_rows:
            continue
        col = design_colors[name]
        lbl = design_labels[name]
        dw = [float(r["delta_w_tooth_nm"]) for r in tol_rows]
        f_rep_cd = [float(r["F_rep_pN"]) for r in tol_rows]
        df_swing = [float(r["Delta_F_pN"]) for r in tol_rows]
        all_d_vals.extend(f_rep_cd)
        all_d_vals.extend(df_swing)

        ax_d.plot(dw, f_rep_cd, "-o", color=col, lw=1.2, ms=3.2, label=f"{lbl} $F_z(3^\\circ)$", zorder=4)
        ax_d.plot(dw, df_swing, "--s", color=col, lw=1.1, ms=3.0, label=f"{lbl} $\\Delta F_z$", zorder=4)

    # EBL corner-rounding markers at r_edge = 5 nm and 10 nm (steps 6, 7 for Cantor_N2; steps 22, 23 for Compact_N2)
    if all(k in eval_by_step for k in (6, 7, 22, 23)):
        ax_d.plot(
            [-0.7, 0.7],
            [float(eval_by_step[6]["force_z_pN"]), float(eval_by_step[7]["force_z_pN"])],
            "D", color="#0072B2", ms=3.8, markerfacecolor="#FFFFFF", markeredgewidth=1.0,
            linestyle="none", zorder=6,
        )
        ax_d.plot(
            [-0.7, 0.7],
            [float(eval_by_step[22]["force_z_pN"]), float(eval_by_step[23]["force_z_pN"])],
            "D", color="#D55E00", ms=3.8, markerfacecolor="#FFFFFF", markeredgewidth=1.0,
            linestyle="none", label=r"EBL rounding ($r_{\mathrm{edge}}=5,10$ nm)", zorder=6,
        )

        ebl_forces = [float(eval_by_step[k]["force_z_pN"]) for k in (6, 7, 22, 23)]
        all_d_vals.extend(ebl_forces)
        y_d_max = max(all_d_vals, default=6.5) + 0.9
        ax_d.annotate(
            f"EBL rounding $r_{{\\mathrm{{edge}}}}=5,10$ nm:\n+{min(ebl_forces):.2f} to +{max(ebl_forces):.2f} pN retained",
            xy=(0.7, float(eval_by_step[23]["force_z_pN"])),
            xytext=(0.0, max(ebl_forces) + 1.05),
            fontsize=4.35, fontweight="bold", color="#0F172A", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.13", facecolor="#FFFBEB", edgecolor="#FCD34D", lw=0.45),
            arrowprops=dict(arrowstyle="->", color="#B45309", lw=0.5, mutation_scale=4.5),
        )
    else:
        y_d_max = max(all_d_vals, default=6.5) + 0.9

    if isinstance(f3_feas_plot, Mapping) and "F_rep_300K_pN" in f3_feas_plot:
        f3_rep_d = float(f3_feas_plot["F_rep_300K_pN"])
        f3_sw_d = float(f3_feas_plot["Delta_F_swing_pN"])
        ax_d.plot(
            [], [], "*", color="#D62728", ms=5.0, ls="none",
            label=rf"3D $F_{{3\_111}}$ nominal: +{f3_rep_d:.2f} / $\Delta F={f3_sw_d:.1f}$ pN",
        )

    ax_d.set_title("Lithographic CD & corner tolerances (300 K)", fontweight="bold", loc="left", pad=3.5)
    ax_d.set_xlabel("Tooth-width etch error $\\Delta w_{\\mathrm{tooth}}$ (nm)")
    ax_d.set_ylabel("Force $F_z(3^\\circ)$ or swing $\\Delta F_z$ (pN)")
    ax_d.set_xlim(-11.5, 11.5)
    ax_d.set_ylim(0.45, y_d_max + 2.05)
    ax_d.set_xticks([-10, -5, 0, 5, 10])
    ax_d.legend(loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94, fontsize=3.7, handlelength=1.15, labelspacing=0.12, borderpad=0.16)

    # =========================================================================
    # Panel e (Bottom-Center): 3D BEM rotational energy barrier E_C(theta) & Casimir torque tau_theta(theta)
    # =========================================================================
    ax_e = figure.add_subplot(gs[1, 1])
    style_ax(ax_e)
    ax_e_r = ax_e.twinx()
    ax_e_r.spines["top"].set_visible(False)
    ax_e_r.spines["left"].set_visible(False)
    ax_e_r.spines["right"].set_visible(True)
    ax_e_r.spines["right"].set_color("#475569")
    ax_e_r.spines["right"].set_linewidth(0.65)
    ax_e_r.tick_params(colors="#334155", width=0.6, length=2.0, pad=1.2, labelsize=4.9)

    ax_e.axhline(0.0, color="#64748B", lw=0.6, ls=":", zorder=2)
    ax_e.axvline(3.0, color="#009E73", lw=0.65, ls="--", alpha=0.65, zorder=1)
    ax_e.axvline(48.0, color="#64748B", lw=0.65, ls="--", alpha=0.65, zorder=1)

    rot_cantor = report["designs"]["Cantor_N2_HybridRZ"]["rotational_energy_barrier"]
    rot_compact = report["designs"]["Rot_C8_Compact_N2"]["rotational_energy_barrier"]
    fractal_n3_ref = report.get("fractal_n3_rotational_barrier", {})

    for name, rot_data, col, mk in (
        ("Cantor_N2_HybridRZ", rot_cantor, "#0072B2", "o"),
        ("Rot_C8_Compact_N2", rot_compact, "#D55E00", "s"),
    ):
        rows = rot_data.get("rows", [])
        if not rows:
            continue
        thetas = [float(r["theta_deg"]) for r in rows]
        de_ev = [float(r["delta_energy_eV"]) for r in rows]
        tau_pnnm = [float(r["torque_theta_pN_nm"]) for r in rows]
        lbl = design_labels[name]
        ax_e.plot(
            thetas, de_ev, "-", marker=mk, color=col, lw=1.2, ms=2.8,
            label=f"{lbl} $\\Delta E_C$", zorder=4,
        )
        ax_e_r.plot(
            thetas, tau_pnnm, "--", color=col, lw=0.95, alpha=0.88,
            label=f"{lbl} $\\tau_\\theta$", zorder=3,
        )

    if fractal_n3_ref and fractal_n3_ref.get("rows"):
        f_rows = fractal_n3_ref["rows"]
        f_thetas = [float(r["theta_deg"]) for r in f_rows]
        f_de_ev = [float(r["delta_energy_eV"]) for r in f_rows]
        f_tau = [float(r["torque_theta_pN_nm"]) for r in f_rows]
        ax_e.plot(
            f_thetas, f_de_ev, "-.^", color="#6A3D9A", lw=1.1, ms=3.0,
            label=r"1D Cantor $N=3$ $\Delta E_C$", zorder=4,
        )
        ax_e_r.plot(
            f_thetas, f_tau, ":", color="#6A3D9A", lw=0.9, alpha=0.85, zorder=3,
        )

    if isinstance(f3_feas_plot, Mapping) and "Delta_F_swing_pN" in f3_feas_plot:
        ax_e.plot(
            [], [], "*", color="#D62728", ms=4.8, ls="none",
            label=rf"3D $F_{{3\_111}}$ ($\Delta F={float(f3_feas_plot['Delta_F_swing_pN']):.1f}$ pN)",
        )

    w_sw_c_ev = float(rot_cantor["switching_work_ev"])
    w_sw_c_aj = float(rot_cantor["switching_work_aJ"])
    tau_pk_c = float(rot_cantor["peak_torque_pN_nm"])
    tau_pk_c8 = float(rot_compact["peak_torque_pN_nm"])
    c_rows_e = rot_cantor.get("rows", [])
    min_de_c_ev = min((float(r["delta_energy_eV"]) for r in c_rows_e), default=-0.35)

    ax_e.annotate(
        f"$W_{{\\mathrm{{switch}}}}(48^\\circ\\!\\to\\!3^\\circ) = {w_sw_c_ev:.2f}$ eV\n"
        f"(${w_sw_c_aj:.3f}$ aJ; $|\\tau_\\theta|_{{\\max}} = {tau_pk_c:.1f}/{tau_pk_c8:.1f}$ pN$\\cdot$nm)",
        xy=(18.0, min_de_c_ev),
        xytext=(24.5, -0.86),
        fontsize=3.85, fontweight="bold", color="#0F172A", ha="center", va="center",
        bbox=dict(boxstyle="round,pad=0.11", facecolor="#F8FAFC", edgecolor="#CBD5E1", lw=0.45),
        arrowprops=dict(arrowstyle="->", color="#0072B2", lw=0.5, mutation_scale=4.5),
    )

    ax_e.set_title("3D BEM energy $\\Delta E_C(\\theta)$ & torque $\\tau_\\theta(\\theta)$", fontweight="bold", loc="left", pad=3.5)
    ax_e.set_xlabel("Rotor rotation angle $\\theta$ (deg)")
    ax_e.set_ylabel("Energy $\\Delta E_C(\\theta)$ (eV; $1\\,\\mathrm{eV}=0.160\\,\\mathrm{aJ}$)")
    ax_e_r.set_ylabel("Torque $\\tau_\\theta$ (pN$\\cdot$nm)", fontsize=5.3, color="#334155", labelpad=1.5)
    ax_e.set_xlim(-1.5, 50.0)
    ax_e.set_ylim(-1.05, 0.72)
    ax_e_r.set_ylim(-380.0, 540.0)
    ax_e_r.set_yticks([-300, -150, 0, 150, 300, 450])
    ax_e.set_xticks([0, 12, 24, 36, 48])

    lines_l, labels_l = ax_e.get_legend_handles_labels()
    lines_r, labels_r = ax_e_r.get_legend_handles_labels()
    ax_e.legend(
        lines_l + lines_r[:1],
        labels_l + [r"Dashed: torque $\tau_\theta(\theta)$"],
        loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1",
        framealpha=0.94, fontsize=3.6, handlelength=1.15, labelspacing=0.11, borderpad=0.16,
    )

    # =========================================================================
    # Panel f (Bottom-Right): 300 K thermomechanical noise & lock-in SNR(tau)
    # =========================================================================
    ax_f = figure.add_subplot(gs[1, 2])
    style_ax(ax_f)
    ax_f.set_xscale("log")
    ax_f.set_yscale("log")

    tm_cantor = report["designs"]["Cantor_N2_HybridRZ"]["thermomechanical_noise"]
    tm_compact = report["designs"]["Rot_C8_Compact_N2"]["thermomechanical_noise"]
    tm_regimes_c = tm_cantor["regimes"]

    ax_f.axhline(100.0, color="#DC2626", lw=0.75, ls="--", zorder=2)
    ax_f.axhspan(100.0, 1.5e8, color="#F0FDF4", alpha=0.45, zorder=0)
    ax_f.text(
        1.3e-3, 125.0, r"Lock-in threshold $\mathrm{SNR} = 10^2$",
        fontsize=4.0, fontweight="bold", color="#B91C1C", ha="left", va="bottom",
    )

    reg_plot_specs = [
        ("isometric_transducer", "Regime I (Isometric)", "#009E73"),
        ("noncontact_nm_actuator", "Regime II (nm-stroke)", "#0072B2"),
        ("compact_high_aspect_clutch", "Regime III (Release)", "#6A3D9A"),
    ]
    for reg_key, reg_short, reg_col in reg_plot_specs:
        rc = tm_regimes_c[reg_key]
        f0_khz = float(rc["f_0_kHz"])
        dz_pm = float(rc["delta_z_th_pm"])
        q4_curve = rc["quality_factors"]["Q_10000"]["tau_rows"]
        q5_curve = rc["quality_factors"]["Q_100000"]["tau_rows"]
        taus_4 = [float(p["tau_s"]) for p in q4_curve]
        snrs_4 = [float(p["SNR"]) for p in q4_curve]
        taus_5 = [float(p["tau_s"]) for p in q5_curve]
        snrs_5 = [float(p["SNR"]) for p in q5_curve]
        dz_str = f"{dz_pm:.0f} pm" if dz_pm < 500.0 else f"{dz_pm/1000.0:.2f} nm"
        ax_f.plot(
            taus_4, snrs_4, "-", color=reg_col, lw=1.2,
            label=f"{reg_short} ($f_0\\!={f0_khz:.1f}$ kHz, $\\delta z_{{\\mathrm{{th}}}}\\!={dz_str}$, $Q\\!=\\!10^4$)",
            zorder=4,
        )
        ax_f.plot(
            taus_5, snrs_5, "--", color=reg_col, lw=0.95, alpha=0.85, zorder=3,
        )

    # Also plot Unified 3D F3_111 Regime I (Q=10^4) curve and marker at tau = 1 s
    snr1_c = float(tm_cantor["snr_1_sec"])
    snr1_c8 = float(tm_compact["snr_1_sec"])
    df_dz_c = abs(float(tm_cantor["dFz_dz0_pN_per_nm"]))
    if isinstance(f3_feas_plot, Mapping) and "snr_1_sec_Q1e4" in f3_feas_plot:
        snr1_f3 = float(f3_feas_plot["snr_1_sec_Q1e4"])
        f0_f3_k = float(f3_feas_plot["f_0_reg1_kHz"])
        taus_f3 = [float(p["tau_s"]) for p in tm_regimes_c["isometric_transducer"]["quality_factors"]["Q_10000"]["tau_rows"]]
        snrs_f3 = [snr1_f3 * math.sqrt(t_s) for t_s in taus_f3]
        ax_f.plot(
            taus_f3, snrs_f3, "-.", color="#D62728", lw=1.35,
            label=rf"3D $F_{{3\_111}}$ Reg. I ($f_0\!={f0_f3_k:.1f}$ kHz, $\mathrm{{SNR}}(1\,\mathrm{{s}})\!=\!{snr1_f3:,.0f}$)",
            zorder=5,
        )
        ax_f.plot([1.0], [snr1_f3], "*", color="#D62728", ms=5.2, markeredgecolor="#0F172A", markeredgewidth=0.4, zorder=7)
    else:
        snr1_f3 = 0.0
    ax_f.plot([1.0], [snr1_c], "o", color="#009E73", ms=3.8, markerfacecolor="#FFFFFF", markeredgewidth=1.1, zorder=6)
    ax_f.plot([1.0], [snr1_c8], "D", color="#D55E00", ms=3.6, markerfacecolor="#FFFFFF", markeredgewidth=1.0, zorder=6)

    f3_snr_txt = f" / ${snr1_f3:,.0f}$ ($F_3$)" if snr1_f3 > 0 else ""
    ax_f.annotate(
        f"$\\tau=1$ s ($Q=10^4$):\n"
        f"$\\mathrm{{SNR}} = {snr1_c:,.0f}$ ($N=2$) / ${snr1_c8:,.0f}$ ($C_8$){f3_snr_txt}\n"
        f"$|\\partial F_z/\\partial z_0| = {df_dz_c:.2f}\\to 1.16$ pN/nm",
        xy=(1.0, snr1_c8),
        xytext=(2.2, 48.0),
        fontsize=3.7, fontweight="bold", color="#0F172A", ha="center", va="center",
        bbox=dict(boxstyle="round,pad=0.11", facecolor="#FFFFFF", edgecolor="#CBD5E1", lw=0.45),
        arrowprops=dict(arrowstyle="->", color="#D62728", lw=0.5, mutation_scale=4.5),
    )

    ax_f.set_title("300 K thermomechanical noise & $\\mathrm{SNR}(\\tau)$", fontweight="bold", loc="left", pad=3.5)
    ax_f.set_xlabel("Lock-in integration time $\\tau$ (s)")
    ax_f.set_ylabel("Force SNR $F_{z,300\\mathrm{K}}^{\\mathrm{rep}} / \\delta F_{\\mathrm{th}}(\\tau)$")
    ax_f.set_xlim(1.0e-3, 1.0e2)
    ax_f.set_ylim(2.0e1, 1.5e8)
    ax_f.legend(
        loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1",
        framealpha=0.94, fontsize=3.45, handlelength=1.1, labelspacing=0.11, borderpad=0.16,
    )

    # Panel labels (8 pt bold lowercase a-f outside top-left)
    for label_char, ax_item in (
        ("a", ax_a),
        ("b", ax_b),
        ("c", ax_c),
        ("d", ax_d),
        ("e", ax_e),
        ("f", ax_f),
    ):
        pos = ax_item.get_position()
        figure.text(
            pos.x0 - 0.038,
            pos.y1 + 0.014,
            label_char,
            fontsize=8.0,
            fontweight="bold",
            va="bottom",
            ha="left",
            color="#0F172A",
        )

    pdf = figures_dir / "fig_nature_feasibility_stability.pdf"
    png = figures_dir / "fig_nature_feasibility_stability.png"
    try:
        figure.savefig(pdf, dpi=600, facecolor="#FFFFFF", metadata={"Title": "Nature feasibility and stability: real 3D BEM"})
        figure.savefig(png, dpi=600, facecolor="#FFFFFF")
        for paper_dir in (
            figures_dir.resolve().parent / "Papers" / "Fractal_Casimir_Nature_EM" / "figures",
            figures_dir.resolve().parent / "Papers" / "FCE_Nature_ver01" / "figures",
        ):
            if paper_dir.is_dir():
                shutil.copy2(pdf, paper_dir / pdf.name)
                shutil.copy2(png, paper_dir / png.name)
    finally:
        plt.close(figure)
    return pdf, png


def persist_artifacts(report: dict[str, Any], output_root: Path) -> None:
    results_dir = output_root / "results"
    figures_dir = output_root / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "nature_feasibility_stability_report.json"
    md_path = results_dir / "nature_feasibility_stability_report.md"

    # Save scientific results before ancillary plotting/logging, so diagnostics
    # survive failures in optional presentation infrastructure.
    stamp_report_rows(report)
    write_json(json_path, report)
    atomic_text(md_path, markdown_report(report))

    from utils.metrics_logger import (
        set_solver_provenance,
        log_step,
        log_metric,
        export_macros,
        save_plot_provenance,
    )

    metadata = freshness_metadata(report["executed_at"])
    solver_params: dict[str, Any] = {
        **report["settings"],
        **metadata,
        "benchmark": "nature_feasibility_and_stability",
        "execution_status": report["execution_status"],
        "backend_signatures": report.get("backend_signatures", {}),
        "materials_and_temperatures": [
            {
                **metadata,
                "regime": label,
                "material": material,
                "temperature_K": temperature,
            }
            for label, material, temperature in REGIMES
        ],
        "laplace_kappa_per_um": KAPPA_LAPLACE_PER_UM,
        "full_study_material": "Gold",
        "full_study_temperature_K": 300.0,
    }

    # The logger's required relative paths are rooted at output_root.
    original_directory = Path.cwd()
    try:
        os.chdir(output_root)
        set_solver_provenance("bem", solver_params)
        for row in report["evaluations"]:
            step_id = int(row["step_id"])
            summary_dict = dict(row)
            log_step(
                step_id, summary_dict,
                solver_name="bem", solver_parameters=solver_params,
            )
        metrics = scalar_metrics(report)
        for metric_name, value, step_id in metrics:
            log_metric(
                metric_name, value, step_id=step_id,
                solver_name="bem", solver_parameters=solver_params,
            )
        export_macros(output_path="results/macros_results.tex")
        paper_macros = Path("Papers/FCE_Nature_ver01/macros_results.tex")
        if paper_macros.parent.is_dir():
            import shutil as _shutil
            _shutil.copy2("results/macros_results.tex", paper_macros)
        if report.get("mode") != "micro_probe" and report.get("execution_status") == "complete":
            pdf, png = make_figure(report, Path("figures"))
            metric_keys_list = [name for name, _, _ in metrics]
            for figure_path in (pdf, png):
                save_plot_provenance(
                    str(figure_path),
                    "results/provenance_metrics.json",
                    metric_keys_list,
                    solver_name="bem",
                    solver_parameters=solver_params,
                )
    finally:
        os.chdir(original_directory)

    report["artifacts"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "figure_pdf": str(figures_dir / "fig_nature_feasibility_stability.pdf"),
        "figure_png": str(figures_dir / "fig_nature_feasibility_stability.png"),
        "macros": str(results_dir / "macros_results.tex"),
        "provenance": str(results_dir / "provenance_metrics.json"),
    }
    write_json(json_path, report)
    atomic_text(md_path, markdown_report(report))


def positive_integer(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("Value must be a positive integer.")
    return value


def nonnegative_integer(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("Value must be a nonnegative integer.")
    return value


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps", type=nonnegative_integer, default=0,
        help="0: both complete studies; 1..10: one micro-probe; >10: cap BEM solves.",
    )
    parser.add_argument("--formulation", default="vector_dyadic")
    parser.add_argument("--n-r", type=positive_integer, default=BEM_TIER_STANDARD.n_r)
    parser.add_argument("--n-phi-tooth", type=positive_integer, default=BEM_TIER_STANDARD.n_phi_tooth)
    parser.add_argument("--n-phi-bridge", type=positive_integer, default=BEM_TIER_STANDARD.n_phi_bridge)
    parser.add_argument("--n-z", type=positive_integer, default=BEM_TIER_STANDARD.n_z)
    parser.add_argument("--n-xi", type=positive_integer, default=BEM_TIER_STANDARD.n_xi)
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--output-root", type=Path, default=ROOT,
        help="Directory under which results/ and figures/ are written.",
    )
    parser.add_argument(
        "--micro-timeout-seconds", type=float, default=13.0,
        help="Micro-probe worker watchdog; leaves time for artifact generation.",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="Regenerate Figure 5 directly from cached JSON reports, update derived sections/macros, without re-running BEM.",
    )
    arguments = parser.parse_args(argv)
    if not arguments.formulation.strip():
        parser.error("--formulation cannot be empty.")
    if (
        not math.isfinite(arguments.micro_timeout_seconds)
        or not 0.0 < arguments.micro_timeout_seconds <= 15.0
    ):
        parser.error("--micro-timeout-seconds must be finite and in (0, 15].")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    output_root = arguments.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    results_dir = output_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    if arguments.plot_only:
        report_path = results_dir / "nature_feasibility_stability_report.json"
        md_path = results_dir / "nature_feasibility_stability_report.md"
        for req_name in (
            "nature_feasibility_stability_report.json",
            "provenance_metrics.json",
        ):
            req_file = results_dir / req_name
            if not req_file.is_file():
                raise FileNotFoundError(
                    f"[ERROR: RUN_DATA_MISSING] --plot-only requires {req_file}"
                )
        cached_report = json.loads(report_path.read_text(encoding="utf-8"))
        ensure_rotational_and_noise_sections(cached_report, results_dir)
        write_json(report_path, cached_report)
        atomic_text(md_path, markdown_report(cached_report))
        from utils.metrics_logger import (
            log_step,
            log_metric,
            export_macros,
            save_plot_provenance,
        )
        solver_params_cached = dict(cached_report.get("settings", {}))
        original_directory = Path.cwd()
        try:
            os.chdir(output_root)
            prov_file = Path("results/provenance_metrics.json")
            prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
            existing_steps = {int(s.get("step", -1)) for s in prov_data.get("steps", []) if isinstance(s, Mapping)}
            existing_metrics = prov_data.get("metrics", {})
            logged_any = False
            for row in cached_report.get("evaluations", []):
                step_id = int(row["step_id"])
                if step_id >= 32 and step_id not in existing_steps:
                    log_step(
                        step_id,
                        dict(row),
                        solver_name="bem",
                        solver_parameters=solver_params_cached,
                    )
                    logged_any = True
            metrics = scalar_metrics(cached_report)
            for metric_name, value, step_id in metrics:
                prev_entry = existing_metrics.get(metric_name)
                prev_val = prev_entry.get("value") if isinstance(prev_entry, Mapping) else None
                if prev_val is None or not math.isclose(float(prev_val), float(value), rel_tol=1e-12, abs_tol=1e-15):
                    log_metric(
                        metric_name,
                        value,
                        step_id=step_id,
                        solver_name="bem",
                        solver_parameters=solver_params_cached,
                    )
                    logged_any = True
            if logged_any or not Path("results/macros_results.tex").is_file():
                export_macros(output_path="results/macros_results.tex")
                paper_macros = Path("Papers/FCE_Nature_ver01/macros_results.tex")
                if paper_macros.parent.is_dir():
                    import shutil as _shutil
                    _shutil.copy2("results/macros_results.tex", paper_macros)
            pdf, png = make_figure(cached_report, Path("figures"))
            metric_keys_list = [name for name, _, _ in metrics]
            import shutil as _shutil
            for figure_path in (pdf, png):
                save_plot_provenance(
                    str(figure_path),
                    "results/provenance_metrics.json",
                    metric_keys_list,
                    solver_name="bem",
                    solver_parameters=solver_params_cached,
                )
                prov_sidecar = Path(str(figure_path) + ".provenance.json")
                if prov_sidecar.is_file():
                    for p_dir in (
                        Path("Papers/Fractal_Casimir_Nature_EM/figures"),
                        Path("Papers/FCE_Nature_ver01/figures"),
                    ):
                        if p_dir.is_dir():
                            _shutil.copy2(prov_sidecar, p_dir / prov_sidecar.name)
        finally:
            os.chdir(original_directory)
        print(f"Plot-only regeneration complete: {png}", flush=True)
        return 0
    micro = 0 < arguments.max_steps <= 10
    requested_resolution = {
        "n_r": arguments.n_r,
        "n_phi_tooth": arguments.n_phi_tooth,
        "n_phi_bridge": arguments.n_phi_bridge,
        "n_z": arguments.n_z,
        "n_xi": arguments.n_xi,
    }
    effective_resolution = (
        {key: 1 for key in requested_resolution} if micro else requested_resolution.copy()
    )
    if arguments.max_steps > 0:
        effective_resolution["n_xi"] = max(2, effective_resolution["n_xi"])
    settings: dict[str, Any] = {
        "max_steps": arguments.max_steps,
        "formulation": arguments.formulation,
        "device": arguments.device,
        **effective_resolution,
        "requested_resolution": requested_resolution,
        "micro_resolution_override": micro,
    }
    if not micro:
        settings["resume_report_path"] = str(
            results_dir / "nature_feasibility_stability_report.json"
        )
    started = time.monotonic()
    report = (
        run_micro_with_watchdog(settings, results_dir, arguments.micro_timeout_seconds)
        if micro
        else execute(settings)
    )
    try:
        persist_artifacts(report, output_root)
    except Exception as exc:
        report["artifact_error"] = f"{type(exc).__name__}: {exc}"
        report["artifact_traceback"] = traceback.format_exc()
        report["total_elapsed_seconds"] = time.monotonic() - started
        write_json(results_dir / "nature_feasibility_stability_report.json", report)
        atomic_text(
            results_dir / "nature_feasibility_stability_report.md",
            markdown_report(report)
            + f"\n## Artifact-generation error\n\n{report['artifact_error']}\n",
        )
        print(report["artifact_error"], file=sys.stderr)
        return 1

    report["total_elapsed_seconds"] = time.monotonic() - started
    write_json(results_dir / "nature_feasibility_stability_report.json", report)
    print(
        f"{report['execution_status']}: {len(report['evaluations'])} BEM evaluation(s), "
        f"{report['total_elapsed_seconds']:.2f} s\n"
        f"Report: {results_dir / 'nature_feasibility_stability_report.json'}"
    )
    if report["execution_status"] in {"complete", "micro_probe_complete"}:
        return 0
    if report["execution_status"] in {"evaluation_limit_reached", "micro_probe_timeout"}:
        return 2
    return 1


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
