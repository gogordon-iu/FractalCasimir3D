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

from execution.casimir_bem_solver import BEM_TIER_STANDARD
from execution.clutch_geometry_redesign import (
    DEFAULT_H_TEETH_ROTATIONAL_UM,
    DEFAULT_HYBRID_L2_H_TEETH_UM,
    DEFAULT_HYBRID_L2_Z_TIP_UM,
    DEFAULT_NUM_SECTORS,
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    DEFAULT_SECTOR_DEG,
    DEFAULT_TOOTH_ARC_DEG,
    DEFAULT_TOOTH_CENTER_OFFSET_DEG,
    DEFAULT_T_LANDING_PAD_UM,
    DEFAULT_T_MEMBRANE_UM,
    DEFAULT_Z_PAD_TOP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
    ROTATIONAL_C8_COMPACT_N2_SPEC,
    disengaged_angle_deg,
    engaged_angle_deg,
)
from execution.materials_database_dispersive import (
    EPSILON_0_F_PER_M,
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
THETA_ENGAGED_DEG = engaged_angle_deg(
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    sector_deg=DEFAULT_SECTOR_DEG,
    tooth_center_offset_deg=DEFAULT_TOOTH_CENTER_OFFSET_DEG,
)
SWITCHING_ANGLES_DEG: tuple[float, float] = (
    THETA_DISENGAGED_DEG,
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
    """Compute mechanical stiffness, safety factors, and linear/basin-equilibrium strokes."""
    kz = (
        float(spoke_count)
        * SILICON_YOUNGS_MODULUS_GPA
        * width_um
        * thickness_um**3
        / length_um**3
        * GPA_UM_TO_PN_PER_NM
    )
    kr = (
        float(spoke_count)
        * SILICON_YOUNGS_MODULUS_GPA
        * thickness_um
        * width_um**3
        / length_um**3
        * GPA_UM_TO_PN_PER_NM
    )
    if kz <= 0.0 or kr <= 0.0:
        raise ValueError("Mechanical suspension stiffness must be positive.")
    kz_casimir_rep = max(force_rep_pN, 0.0) / basin_width_nm
    lift_linear_nm = force_rep_pN / kz
    lift_basin_eq_nm = force_rep_pN / (kz + kz_casimir_rep)
    engaged_linear_shift_nm = force_engaged_pN / kz
    pull_in_factor = ((alpha + 1.0) ** (alpha + 1.0)) / (alpha**alpha)
    kz_crit_pull_in = pull_in_factor * abs(force_engaged_pN) / pad_gap_nm
    pull_in_safety_factor = kz / max(kz_crit_pull_in, 1e-12)
    lateral_sf = kr / max(abs(k_r_casimir_pN_per_nm), 1e-9)
    return {
        "spoke_count": spoke_count,
        "L_spoke_um": length_um,
        "w_spoke_um": width_um,
        "t_spoke_um": thickness_um,
        "k_z_mech_pN_per_nm": kz,
        "k_r_mech_pN_per_nm": kr,
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
    study["execution_status"] = "complete"


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
                if isinstance(previous, Mapping) and previous.get("mode") != "micro_probe":
                    rows = previous.get("evaluations", ())
                    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                        existing_evaluations = rows
        evaluator = Evaluator(settings, report, existing_evaluations)

        load_backend()
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
                    "### 2. Electrostatic residual-voltage bound",
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
            "patch_potential", "lateral_stability", "cd_tolerance"
        ):
            for field, value in study.get(section, {}).items():
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    if math.isfinite(float(value)):
                        metrics.append((f"nature_{name}_{section}_{field}", float(value), step))
    return metrics


def make_figure(report: Mapping[str, Any], figures_dir: Path) -> tuple[Path, Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 2, figsize=(12.0, 8.5), constrained_layout=True)
    a, b, c, d = axes.reshape(-1)
    colors = ("tab:blue", "tab:orange")

    for (name, study), color in zip(report["designs"].items(), colors):
        material_rows = study.get("material_dispersion", {}).get("rows", [])
        for theta, style in (
            (THETA_DISENGAGED_DEG, "-o"),
            (THETA_ENGAGED_DEG, "--s"),
        ):
            selected = [row for row in material_rows if row["theta_deg"] == theta]
            if selected:
                a.plot(
                    [row["regime"] for row in selected],
                    [row["force_z_pN"] for row in selected],
                    style, color=color, label=f"{name}, {theta:g}°",
                )
        patch = study.get("patch_potential", {})
        voltage_rows = patch.get("voltage_rows", [])
        if voltage_rows:
            b.plot(
                [row["V_patch_mV"] for row in voltage_rows],
                [row["F_net_pN"] for row in voltage_rows],
                "-o", color=color, label=name,
            )
        lateral = study.get("lateral_stability", {})
        if "k_r_Casimir_pN_per_nm" in lateral:
            x = float(list(report["designs"]).index(name))
            casimir = lateral["k_r_Casimir_pN_per_nm"]
            mechanical = lateral["k_r_mech_pN_per_nm"]
            c.bar(x - 0.18, casimir, width=0.34, color=color, label=f"{name}: Casimir")
            c.bar(
                x + 0.18, mechanical, width=0.34, color=color, alpha=0.4,
                hatch="//", label=f"{name}: suspension",
            )
        tolerance_rows = study.get("cd_tolerance", {}).get("rows", [])
        if tolerance_rows:
            x_values = [row["delta_w_tooth_nm"] for row in tolerance_rows]
            d.plot(
                x_values, [row["F_rep_pN"] for row in tolerance_rows],
                "-o", color=color, label=f"{name}: repulsion",
            )
            d.plot(
                x_values, [row["Delta_F_pN"] for row in tolerance_rows],
                "--s", color=color, label=f"{name}: swing",
            )

    a.set(title="1. Material dispersion / temperature", ylabel="Vertical force (pN)")
    b.set(title="2. Residual-voltage bound", xlabel="Voltage (mV)", ylabel="Net force (pN)")
    c.set(title="3. Sampled radial stiffness vs. suspension", ylabel="Stiffness (pN/nm)")
    d.set(
        title="4. Tooth CD tolerance", xlabel="Tooth width error (nm)", ylabel="Force (pN)"
    )
    if c.has_data():
        c.set_xticks(range(len(report["designs"])), list(report["designs"]), fontsize=8)
    for axis in (a, b, c, d):
        axis.axhline(0.0, color="0.4", linewidth=0.7)
        axis.grid(alpha=0.2)
        handles, labels = axis.get_legend_handles_labels()
        if handles:
            axis.legend(handles, labels, fontsize=7)
        else:
            axis.text(
                0.5, 0.5,
                "Not evaluated\n" + str(report["execution_status"]).replace("_", " "),
                transform=axis.transAxes, ha="center", va="center", color="0.4",
            )
    figure.suptitle(
        f"Nature feasibility / stability — {report['execution_status']}", fontsize=13
    )
    pdf = figures_dir / "fig_nature_feasibility_stability.pdf"
    png = figures_dir / "fig_nature_feasibility_stability.png"
    try:
        figure.savefig(pdf, metadata={"Title": "Nature feasibility and stability: real 3D BEM"})
        figure.savefig(png, dpi=180)
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
