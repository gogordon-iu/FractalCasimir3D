#!/usr/bin/env python3
"""
execution/run_real_world_nems_clutch.py

Prepare and audit the specified NEMS clutch geometry, run repository BEM
solvers, and compare their results with zero-temperature dispersive
Lifshitz-PFA calculations.

Important:
    Surviving Cantor ring ribs extend through the landing-pad sector to
    connect to the pedestals. Rotor tooth radial slots remain open.
    Connectivity and collisions are measured rather than assumed.

    The hybrid material calculation is an explicitly labelled, component-
    weighted BEM approximation, not a claim that a homogeneous-material BEM
    solver implements an exact heterogeneous scattering calculation.

    Full 360-degree meshes are used for geometry audits. The repository BEM
    solver receives a single 90-degree sector and applies its own four-fold
    symmetry multiplier.

    Solves run in-process unless a solver subprocess deadline is requested.
    A timeout is recorded as unavailable data, never as a fabricated force.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import inspect
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray


SCRIPT_START = time.monotonic()
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DESIGN_NAMES = (
    "Rot_C4_TightSlot_N2",
    "Rot_C8_Compact_N2",
    "Rot_C10_Fractal_N3",
)
FLOAT = np.float64
EPS = 1.0e-11
HBAR = 1.054571817e-34
LIGHT_SPEED = 299_792_458.0
UM_TO_M = 1.0e-6
HBAR_C_EV_UM = 0.1973269804
GOLD_OMEGA_P_INV_UM = 9.03 / HBAR_C_EV_UM
GOLD_GAMMA_INV_UM = 0.053 / HBAR_C_EV_UM
SUPPORT_CLEARANCE_UM = 0.002
DATASET = "real_world_nems_clutch"
EXECUTED_AT = datetime.now(timezone.utc).isoformat()
Array = NDArray[np.float64]


@dataclass(frozen=True)
class Design:
    name: str
    r_min: float
    r_max: float
    rings: tuple[tuple[float, float], ...]
    teeth: tuple[tuple[float, float], ...]
    tooth_arc_deg: float
    aperture_arc_deg: float
    raw_spec: Any
    raw_context: Any


@dataclass
class Surface:
    centers_um: Array
    normals: Array
    areas_um2: Array
    tags: tuple[str, ...]
    components: tuple[str, ...]
    vertices_um: Array
    triangles: NDArray[np.int64]
    occupied_cells: int
    connected_components: int
    watertight: bool
    orientation_consistent: bool
    volume_um3: float
    repository_faces: list[Any]
    panel_phi_bounds_deg: tuple[tuple[float, float], ...] = ()

    def summary(self) -> dict[str, Any]:
        return {
            "panels": len(self.tags),
            "vertices": len(self.vertices_um),
            "triangles": len(self.triangles),
            "occupied_cells": self.occupied_cells,
            "connected_components": self.connected_components,
            "watertight": self.watertight,
            "orientation_consistent": self.orientation_consistent,
            "volume_um3": self.volume_um3,
            "component_panel_counts": {
                component: self.components.count(component)
                for component in sorted(set(self.components))
            },
        }


@dataclass
class MeshPair:
    rotor: Surface
    stator: Surface


@dataclass(frozen=True)
class Job:
    design_name: str
    theta_deg: float
    variant: str
    kernel: str
    subdivisions: int
    n_xi: int
    device: str
    convergence: bool = False


class RepositoryAPIError(RuntimeError):
    """The installed repository API cannot represent the requested operation."""


class GeometryError(ValueError):
    """The geometry or its serialization is invalid."""


_REPO: dict[str, Any] | None = None


def repository() -> dict[str, Any]:
    global _REPO
    if _REPO is None:
        from execution.run_rotational_z_eff_clutch import (
            DEFAULT_DESIGNS,
            Z_TIP_FIXED_UM,
            H_TEETH_UM,
            Z_ROTOR_TOP_UM,
            Z_PAD_TOP_UM,
            SECTOR_DEG,
            SYMMETRY_ORDER,
            resolve_design,
            geometry_context,
            tooth_segments,
            repository_face,
            build_rotational_stepped_clutch_mesh,
            collision_certificate,
            angular_state,
            extract_fz,
        )
        from execution.casimir_bem_solver import (
            ClutchSurfaceMesh,
            Geometry,
            MaterialModel,
            run_bem_casimir_solver,
            MEEP_FORCE_TO_SI,
        )
        from utils.metrics_logger import (
            set_solver_provenance,
            log_step,
            log_metric,
            export_macros,
            save_plot_provenance,
        )

        _REPO = dict(locals())
        expected = {
            "Z_TIP_FIXED_UM": -0.100,
            "H_TEETH_UM": 0.100,
            "Z_ROTOR_TOP_UM": 0.000,
            "Z_PAD_TOP_UM": -0.115,
            "SECTOR_DEG": 90.0,
            "SYMMETRY_ORDER": 4.0,
        }
        for name, value in expected.items():
            actual = float(_REPO[name])
            if not math.isfinite(actual) or not math.isclose(
                actual, value, abs_tol=1.0e-12, rel_tol=0.0
            ):
                raise RepositoryAPIError(
                    f"Repository constant {name}={actual!r}; required {value!r}."
                )
    return _REPO


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return plain(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return repr(value)


def output_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    """Separate artifact completion from scientific measurement availability."""
    result = dict(value)
    original_status = result.get("status")
    if original_status is not None and original_status != "completed":
        result.setdefault("measurement_status", original_status)
    result.setdefault("model", "BEM and continuum dispersive Lifshitz-PFA")
    result["dataset"] = DATASET
    result["status"] = "completed"
    result.setdefault("executed_at", EXECUTED_AT)
    return result


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value: Any) -> None:
    if isinstance(value, Mapping):
        value = output_metadata(value)
    atomic_text(path, json.dumps(plain(value), indent=2, allow_nan=False) + "\n")


def fields_of(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: getattr(value, field.name)
            for field in dataclasses.fields(value)
        }
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def invoke(
    function: Callable[..., Any],
    values: Mapping[str, Any],
    *,
    extra_kwargs: Mapping[str, Any] | None = None,
) -> Any:
    """
    Bind by inspected parameter names; do not retry calls after solver errors.

    Unsupported required parameters cause an actionable API error, rather than
    guessed positional arguments or silently ignored physical parameters.
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError) as exc:
        raise RepositoryAPIError(
            f"Cannot inspect {getattr(function, '__qualname__', repr(function))}"
        ) from exc

    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    has_varkw = False
    for name, parameter in signature.parameters.items():
        if name in ("self", "cls"):
            continue
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            has_varkw = True
            continue
        if name in values:
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                positional.append(values[name])
            else:
                keywords[name] = values[name]
        elif parameter.default is inspect.Parameter.empty:
            raise RepositoryAPIError(
                f"Unsupported required argument {name!r} in "
                f"{getattr(function, '__qualname__', function)!s}{signature}. "
                "Extend the explicit repository adapter for this API."
            )
    if has_varkw and extra_kwargs:
        for name, value in extra_kwargs.items():
            keywords.setdefault(name, value)
    return function(*positional, **keywords)


def lookup(
    sources: Sequence[Any], names: Sequence[str], *, default: Any = None
) -> Any:
    for source in sources:
        data = fields_of(source)
        for name in names:
            if name in data:
                return data[name]
    return default


def finite_number(value: Any, name: str) -> float:
    if isinstance(value, (bool, str, bytes)) or not np.isscalar(value):
        raise GeometryError(f"{name} must be a finite real scalar.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise GeometryError(f"{name} must be a finite real scalar.") from exc
    if not math.isfinite(number):
        raise GeometryError(f"{name} is non-finite.")
    return number


def intervals(value: Any, name: str) -> tuple[tuple[float, float], ...]:
    if value is None:
        raise RepositoryAPIError(f"Repository did not expose {name}.")
    result: list[tuple[float, float]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            low = lookup([item], ("r_inner", "r_in", "inner", "start", "lo"))
            high = lookup([item], ("r_outer", "r_out", "outer", "end", "hi"))
        else:
            if len(item) != 2:
                raise GeometryError(f"{name}[{index}] must contain two endpoints.")
            low, high = item
        a = finite_number(low, f"{name}[{index}].lo")
        b = finite_number(high, f"{name}[{index}].hi")
        if a < 0.0 or b <= a:
            raise GeometryError(f"Invalid {name} interval {(a, b)}.")
        result.append((a, b))
    result.sort()
    if not result:
        raise GeometryError(f"{name} must not be empty.")
    for left, right in zip(result, result[1:]):
        if right[0] < left[1] - EPS:
            raise GeometryError(f"{name} contains overlapping intervals.")
    return tuple(result)


def get_design(name: str) -> Design:
    repo = repository()
    defaults = repo["DEFAULT_DESIGNS"]
    if isinstance(defaults, Mapping):
        if name not in defaults:
            raise RepositoryAPIError(f"Missing repository design {name}.")
        raw = defaults[name]
    else:
        candidates = [
            item
            for item in defaults
            if lookup([item], ("name", "design", "design_name", "id")) == name
        ]
        if len(candidates) != 1:
            raise RepositoryAPIError(f"Cannot uniquely locate design {name}.")
        raw = candidates[0]

    if not isinstance(raw, Mapping):
        raise RepositoryAPIError(f"Repository design {name} must be a mapping.")
    spec = repo["resolve_design"](raw, str(raw.get("family", "concentric_cantor")))
    context = invoke(
        repo["geometry_context"],
        {
            "spec": spec,
            "design": spec,
            "theta_deg": 0.0,
            "theta": 0.0,
            "z_tip_um": -0.100,
            "z_tip": -0.100,
        },
    )
    sources = [context, spec, raw]
    r_min = finite_number(
        lookup(sources, ("R_min", "R_min_um", "r_min", "r_min_um")), "R_min"
    )
    r_max = finite_number(
        lookup(sources, ("R_max", "R_max_um", "r_max", "r_max_um")), "R_max"
    )
    rings = intervals(spec.ring_intervals, "ring_intervals")
    teeth = intervals(
        [(float(e.r_tooth_in), float(e.r_tooth_out)) for e in spec.elements],
        "tooth_intervals",
    )
    tooth_arc = finite_number(
        lookup(sources, ("tooth_arc_deg", "tooth_arc")), "tooth_arc_deg"
    )
    aperture = finite_number(
        lookup(sources, ("aperture_arc_deg", "aperture_arc"), default=36.0),
        "aperture_arc_deg",
    )
    if not 0.0 < r_min < r_max:
        raise GeometryError("Require 0 < R_min < R_max.")
    if not 0.0 < tooth_arc < 90.0 or not math.isclose(aperture, 36.0):
        raise GeometryError("Invalid tooth arc or non-36-degree aperture.")
    for a, b in (*rings, *teeth):
        if a < r_min - EPS or b > r_max + EPS:
            raise GeometryError("An active radial interval leaves [R_min, R_max].")
    if r_min - 0.03 <= max(0.08, r_min - 0.12):
        raise GeometryError("The specified inner rotor collar has no radial width.")
    return Design(name, r_min, r_max, rings, teeth, tooth_arc, aperture, spec, context)


def segments(design: Design, theta_deg: float) -> tuple[tuple[float, float], ...]:
    raw = invoke(
        repository()["tooth_segments"],
        {
            "theta_deg": theta_deg,
            "theta": theta_deg,
            "tooth_arc_deg": design.tooth_arc_deg,
            "tooth_arc": design.tooth_arc_deg,
            "arc_deg": design.tooth_arc_deg,
            "sector_deg": 90.0,
        },
    )
    result: list[tuple[float, float]] = []
    for item in raw:
        a, b = float(item[0]), float(item[1])
        if not math.isfinite(a + b) or a < -EPS or b > 90.0 + EPS or b <= a:
            raise GeometryError(f"Invalid repository tooth segment {(a, b)}.")
        result.append((max(0.0, a), min(90.0, b)))
    if not result:
        raise GeometryError("Repository tooth_segments returned an empty set.")
    return tuple(result)


def in_intervals(value: float, ranges: Sequence[tuple[float, float]]) -> bool:
    return any(a - EPS < value < b + EPS for a, b in ranges)


def grid_nodes(values: Sequence[float], subdivisions: int) -> Array:
    if subdivisions < 1:
        raise ValueError("subdivisions must be positive.")
    original = sorted(set(round(float(value), 12) for value in values))
    if len(original) < 2 or not np.all(np.isfinite(original)):
        raise GeometryError("A grid requires at least two finite nodes.")
    refined = [
        a + (b - a) * j / subdivisions
        for a, b in zip(original, original[1:])
        for j in range(subdivisions)
    ]
    refined.append(original[-1])
    return np.asarray(refined, dtype=FLOAT)


def configuration(designs: Sequence[Design]) -> dict[str, Any]:
    items: dict[str, Any] = {}
    for design in designs:
        rotor_hub = max(0.08, design.r_min - 0.12)
        stator_hub = max(0.10, design.r_min - 0.10)
        items[design.name] = {
            "repository_spec": plain(design.raw_spec),
            "R_min_um": design.r_min,
            "R_max_um": design.r_max,
            "ring_intervals_um": design.rings,
            "tooth_intervals_um": design.teeth,
            "sector_deg": 90.0,
            "symmetry_order": 4,
            "aperture_arc_deg": design.aperture_arc_deg,
            "bridge_arc_deg": 90.0 - design.aperture_arc_deg,
            "tooth_arc_deg": design.tooth_arc_deg,
            "rotor": {
                "teeth": {
                    "radial_intervals_um": design.teeth,
                    "angular_rule": "repository tooth_segments(theta_deg, tooth_arc_deg)",
                    "z_um": [-0.100, 0.350],
                    "active_shoe_z_um": [-0.100, 0.0],
                    "recessed_hanger_stem_z_um": [0.0, 0.350],
                    "continuous_shank_height_um": 0.450,
                },
                "spider": {
                    "radial_um": [rotor_hub, design.r_max + 0.12],
                    "angular_rule": "same as rotor teeth, replicated four times",
                    "z_um": [0.350, 0.470],
                },
                "inner_hub_collar_requested": {
                    "radial_um": [rotor_hub, design.r_min - 0.03],
                    "phi_deg": [0.0, 360.0],
                    "z_um": [0.350, 0.470],
                },
                "outer_actuator_ring_requested": {
                    "radial_um": [design.r_max + 0.03, design.r_max + 0.12],
                    "phi_deg": [0.0, 360.0],
                    "z_um": [0.350, 0.470],
                },
                "mesh_occupancy_collar_radial_um": [rotor_hub, design.r_min],
                "mesh_occupancy_actuator_radial_um": [
                    design.r_max, design.r_max + 0.12,
                ],
            },
            "stator": {
                "elevated_cantor_ribs": {
                    "radial_intervals_um": design.rings,
                    "phi_per_sector_deg": [0.0, design.aperture_arc_deg],
                    "z_um": [-0.025, 0.0],
                    "requested_support": "doubly-clamped; connectivity audited",
                },
                "landing_sector_rib_clamps": {
                    "radial_intervals_um": design.rings,
                    "phi_per_sector_deg": [design.aperture_arc_deg, 90.0],
                    "z_um": [-0.550, 0.0],
                    "note": "Surviving ring ribs join the pad pedestals; tooth slots stay open.",
                },
                "landing_pad_pedestals": {
                    "radial_um": [design.r_min, design.r_max],
                    "phi_per_sector_deg": [design.aperture_arc_deg, 90.0],
                    "z_um": [-0.550, -0.115],
                },
                "inner_anchor_hub": {
                    "radial_um": [stator_hub, design.r_min],
                    "phi_deg": [0.0, 360.0],
                    "z_um": [-0.550, 0.0],
                },
                "outer_anchor_frame": {
                    "radial_um": [design.r_max, design.r_max + 0.10],
                    "phi_deg": [0.0, 360.0],
                    "z_um": [-0.550, 0.0],
                },
                "release_trench_floor": {
                    "radial_um": [stator_hub, design.r_max + 0.10],
                    "phi_deg": [0.0, 360.0],
                    "z_um": [-0.650, -0.550],
                },
            },
            "nominal_gaps_um": {
                "tooth_to_pad": 0.015,
                "spider_to_rib": 0.350,
                "tooth_to_floor": 0.450,
                "rib_bottom_to_recessed_pad_top": 0.090,
            },
        }
    return {
        "schema_version": 1,
        "length_unit": "um",
        "force_unit": "N",
        "temperature_K": 0.0,
        "designs": items,
        "materials": {
            "gold": {
                "model": "Drude",
                "eps_inf": 1.0,
                "omega_p_inv_um": GOLD_OMEGA_P_INV_UM,
                "gamma_inv_um": GOLD_GAMMA_INV_UM,
                "hbar_c_eV_um": HBAR_C_EV_UM,
                "frequency_convention": "angular wavenumber, rad/um",
                "note": "The specified Drude-Lorentz stack has no Lorentz poles for Au.",
            },
            "silicon_nitride": {
                "model": "Lorentz",
                "eps_inf": 1.0,
                "omega_0_inv_um": 5.85,
                "strength_inv_um2": 2.89 * 5.85**2,
                "gamma_inv_um": 0.10,
                "eps_static": 3.89,
            },
            "silica": {
                "model": "constant dielectric",
                "eps_static": 2.10,
                "note": "No optical oscillator was specified; no dispersion is invented.",
            },
        },
        "metallization": {
            "all_gold": "homogeneous Au on all surfaces",
            "selective_gold": {
                "active_teeth_ribs_pads": "Au",
                "upper_spider_hubs_floor": "Si3N4",
                "calculation": "component-weighted homogeneous BEM approximation",
                "coating_thickness_um": None,
                "exact_multilayer_optics_available": False,
            },
        },
        "solver_support_clearance_um": SUPPORT_CLEARANCE_UM,
        "specification_conflicts": [
            "Part 2 specifies collars ending at R_min-0.03 and starting at "
            "R_max+0.03; part 3 explicitly occupies collars through R_min and "
            "from R_max. The mesh follows the explicit part-3 occupancy.",
            "Surviving Cantor ring ribs extend to z=0 in the landing-pad sector "
            "to provide pedestal clamps. Connectivity and rotor clearance are "
            "audited on the full geometry.",
            "An actuator ring is specified, but comb fingers, suspension, shaft "
            "bearings, drive electrodes, and electrical routing are not. "
            "Their mechanics and actuation are not verified by this script.",
            "Solver support macro-boxes use 2 nm clearances at adjoining "
            "boundaries to avoid overlapping or coincident interface panels. "
            "They approximate, rather than exactly reproduce, the connected "
            "full-geometry audit mesh.",
        ],
    }


def cell_label(
    body: Literal["rotor", "stator"],
    design: Design,
    tooth_angles: Sequence[tuple[float, float]],
    r: float,
    phi: float,
    z: float,
    variant: str,
) -> str | None:
    angular = phi % 90.0
    tooth = in_intervals(r, design.teeth) and in_intervals(angular, tooth_angles)
    if body == "rotor":
        if variant == "isolated":
            return "active" if tooth and -0.100 < z < 0.0 else None
        if tooth and -0.100 < z < 0.0:
            return "active"
        if tooth and 0.0 < z < 0.350:
            return None if variant == "without_spider" else "spider"
        hub = max(0.08, design.r_min - 0.12)
        rim = design.r_max + 0.12
        if 0.350 < z < 0.470 and hub < r < rim:
            collar = r < design.r_min or r > design.r_max
            spoke = in_intervals(angular, tooth_angles)
            if collar:
                return None if variant == "without_foundation" else "foundation"
            if spoke:
                return None if variant == "without_spider" else "spider"
        return None

    if variant == "isolated":
        if (
            angular < design.aperture_arc_deg
            and in_intervals(r, design.rings)
            and -0.025 < z < 0.0
        ):
            return "active"
        if (
            angular > design.aperture_arc_deg
            and design.r_min < r < design.r_max
            and -0.265 < z < -0.115
        ):
            return "active"
        return None

    if -0.650 < z < -0.550:
        return None if variant == "without_foundation" else "foundation"
    if (r < design.r_min or r > design.r_max) and -0.550 < z < 0.0:
        return None if variant == "without_foundation" else "foundation"
    if (
        angular > design.aperture_arc_deg
        and in_intervals(r, design.rings)
        and -0.550 < z < 0.0
    ):
        return "active"
    if (
        angular > design.aperture_arc_deg
        and design.r_min < r < design.r_max
        and -0.550 < z < -0.115
    ):
        return "active"
    if (
        angular < design.aperture_arc_deg
        and in_intervals(r, design.rings)
        and -0.025 < z < 0.0
    ):
        return "active"
    return None


def occupancy_components(occupied: NDArray[np.bool_]) -> int:
    remaining = set(map(tuple, np.argwhere(occupied).tolist()))
    nr, na, nz = occupied.shape
    count = 0
    while remaining:
        count += 1
        queue = deque([remaining.pop()])
        while queue:
            i, j, k = queue.popleft()
            neighbors = (
                (i - 1, j, k),
                (i + 1, j, k),
                (i, (j - 1) % na, k),
                (i, (j + 1) % na, k),
                (i, j, k - 1),
                (i, j, k + 1),
            )
            for neighbor in neighbors:
                a, b, c = neighbor
                if 0 <= a < nr and 0 <= b < na and 0 <= c < nz:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
    return count


def cylindrical_vertex(r: float, phi_deg: float, z: float) -> tuple[float, float, float]:
    phi = math.radians(phi_deg)
    return (r * math.cos(phi), r * math.sin(phi), z)


def face_record(
    body: str,
    kind: str,
    sign: int,
    r0: float,
    r1: float,
    p0: float,
    p1: float,
    z0: float,
    z1: float,
    corners: Sequence[tuple[float, float, float]],
    center: Array,
    normal: Array,
    area: float,
    component: str,
) -> Any:
    if kind == "horizontal":
        tag = f"{body}_{'top' if sign > 0 else 'bottom'}"
    else:
        tag = f"{body}_{kind}_wall"
    p0_rad, p1_rad = math.radians(p0), math.radians(p1)
    if kind == "horizontal":
        z_face = z1 if sign > 0 else z0
        return repository()["repository_face"](
            kind,
            r0=r0,
            r1=r1,
            phi0=p0_rad,
            phi1=p1_rad,
            z0=z_face,
            z1=z_face,
            sign=sign,
            panel_type=tag,
        )
    if kind == "radial":
        r_face = r1 if sign > 0 else r0
        return repository()["repository_face"](
            kind,
            r0=r_face,
            r1=r_face,
            phi0=p0_rad,
            phi1=p1_rad,
            z0=z0,
            z1=z1,
            sign=sign,
            panel_type=tag,
        )
    if kind == "azimuthal":
        phi_face = p1_rad if sign > 0 else p0_rad
        return repository()["repository_face"](
            kind,
            r0=r0,
            r1=r1,
            phi0=phi_face,
            phi1=phi_face,
            z0=z0,
            z1=z1,
            sign=sign,
            panel_type=tag,
        )
    raise GeometryError(f"Unsupported face kind {kind!r}.")


def build_surface(
    design: Design,
    theta_deg: float,
    body: Literal["rotor", "stator"],
    subdivisions: int,
    variant: str,
) -> Surface:
    tooth_angles = segments(design, theta_deg)
    hub = (
        max(0.08, design.r_min - 0.12)
        if body == "rotor"
        else max(0.10, design.r_min - 0.10)
    )
    rim = design.r_max + (0.12 if body == "rotor" else 0.10)
    radial_values = [hub, design.r_min, design.r_max, rim]
    for a, b in (*design.rings, *design.teeth):
        radial_values.extend((a, b))
    radii = grid_nodes(radial_values, subdivisions)
    sector_nodes = {0.0, 90.0, design.aperture_arc_deg}
    for a, b in tooth_angles:
        sector_nodes.update((a, b))
    angles = grid_nodes(
        [90.0 * sector + node for sector in range(4) for node in sector_nodes],
        subdivisions,
    )
    heights = grid_nodes(
        [-0.100, 0.0, 0.350, 0.470]
        if body == "rotor"
        else [-0.650, -0.550, -0.265, -0.115, -0.025, 0.0],
        subdivisions,
    )
    shape = (len(radii) - 1, len(angles) - 1, len(heights) - 1)
    if math.prod(shape) > 2_000_000:
        raise GeometryError("Requested mesh exceeds the two-million-cell safety limit.")
    labels = np.empty(shape, dtype=object)
    labels.fill(None)
    volume = 0.0
    for i, j, k in np.ndindex(shape):
        label = cell_label(
            body,
            design,
            tooth_angles,
            float((radii[i] + radii[i + 1]) / 2.0),
            float((angles[j] + angles[j + 1]) / 2.0),
            float((heights[k] + heights[k + 1]) / 2.0),
            variant,
        )
        labels[i, j, k] = label
        if label is not None:
            volume += (
                0.5
                * (radii[i + 1] ** 2 - radii[i] ** 2)
                * math.radians(float(angles[j + 1] - angles[j]))
                * (heights[k + 1] - heights[k])
            )
    occupied = labels != None  # noqa: E711
    if not np.any(occupied):
        raise GeometryError(f"Empty {body} mesh for variant {variant}.")

    vertices: list[tuple[float, float, float]] = []
    vertex_ids: dict[tuple[int, int, int], int] = {}
    triangles: list[tuple[int, int, int]] = []
    centers: list[Array] = []
    normals: list[Array] = []
    areas: list[float] = []
    tags: list[str] = []
    components: list[str] = []
    records: list[Any] = []
    phi_bounds: list[tuple[float, float]] = []
    nr, na, nz = shape

    def vertex(index: tuple[int, int, int]) -> int:
        i, j, k = index
        key = (i, j % na, k)
        if key not in vertex_ids:
            vertex_ids[key] = len(vertices)
            vertices.append(
                cylindrical_vertex(
                    float(radii[i]), float(angles[j % na]), float(heights[k])
                )
            )
        return vertex_ids[key]

    directions = (
        (0, -1, "radial"),
        (0, 1, "radial"),
        (1, -1, "azimuthal"),
        (1, 1, "azimuthal"),
        (2, -1, "horizontal"),
        (2, 1, "horizontal"),
    )
    for i, j, k in map(tuple, np.argwhere(occupied).tolist()):
        r0, r1 = map(float, radii[i : i + 2])
        p0, p1 = map(float, angles[j : j + 2])
        z0, z1 = map(float, heights[k : k + 2])
        mid_phi = math.radians((p0 + p1) / 2.0)
        for axis, sign, kind in directions:
            neighbor = [i, j, k]
            neighbor[axis] += sign
            neighbor[1] %= na
            a, b, c = neighbor
            if 0 <= a < nr and 0 <= c < nz and occupied[a, b, c]:
                continue

            if axis == 2:
                kk = k + (sign > 0)
                nodes = [
                    (i, j, kk),
                    (i + 1, j, kk),
                    (i + 1, j + 1, kk),
                    (i, j + 1, kk),
                ]
                normal = np.array([0.0, 0.0, float(sign)])
                area = 0.5 * (r1**2 - r0**2) * math.radians(p1 - p0)
            elif axis == 0:
                ii = i + (sign > 0)
                nodes = [
                    (ii, j, k),
                    (ii, j + 1, k),
                    (ii, j + 1, k + 1),
                    (ii, j, k + 1),
                ]
                normal = sign * np.array(
                    [math.cos(mid_phi), math.sin(mid_phi), 0.0]
                )
                area = (r1 if sign > 0 else r0) * math.radians(p1 - p0) * (z1 - z0)
            else:
                jj = j + (sign > 0)
                angle = math.radians(p1 if sign > 0 else p0)
                nodes = [
                    (i, jj, k),
                    (i + 1, jj, k),
                    (i + 1, jj, k + 1),
                    (i, jj, k + 1),
                ]
                normal = sign * np.array([-math.sin(angle), math.cos(angle), 0.0])
                area = (r1 - r0) * (z1 - z0)

            ids = [vertex(tuple(node)) for node in nodes]
            coordinates = np.asarray([vertices[index] for index in ids], dtype=FLOAT)
            cross = np.cross(
                coordinates[1] - coordinates[0],
                coordinates[2] - coordinates[0],
            )
            if float(np.dot(cross, normal)) < 0.0:
                ids.reverse()
                coordinates = coordinates[::-1]
            center = np.mean(coordinates, axis=0)
            if area <= 0.0 or not np.isfinite(area):
                raise GeometryError("Non-positive or non-finite boundary panel area.")
            tag = (
                f"{body}_{'top' if sign > 0 else 'bottom'}"
                if kind == "horizontal"
                else f"{body}_{kind}_wall"
            )
            component = str(labels[i, j, k])
            record = face_record(
                body, kind, sign, r0, r1, p0, p1, z0, z1,
                [vertices[index] for index in ids], center, normal, area, component,
            )
            records.append(record)
            centers.append(center)
            normals.append(normal)
            areas.append(area)
            tags.append(tag)
            components.append(component)
            # Use the owning cell's bounds to assign seam faces unambiguously.
            phi_bounds.append((p0, p1))
            triangles.extend(
                ((ids[0], ids[1], ids[2]), (ids[0], ids[2], ids[3]))
            )

    edge_counts: dict[tuple[int, int], int] = {}
    edge_orientation: dict[tuple[int, int], int] = {}
    for triangle in triangles:
        for a, b in zip(triangle, (triangle[1], triangle[2], triangle[0])):
            key = (min(a, b), max(a, b))
            edge_counts[key] = edge_counts.get(key, 0) + 1
            edge_orientation[key] = edge_orientation.get(key, 0) + (1 if a < b else -1)
    watertight = bool(edge_counts) and all(count == 2 for count in edge_counts.values())
    oriented = all(value == 0 for value in edge_orientation.values())
    return Surface(
        np.asarray(centers, dtype=FLOAT),
        np.asarray(normals, dtype=FLOAT),
        np.asarray(areas, dtype=FLOAT),
        tuple(tags),
        tuple(components),
        np.asarray(vertices, dtype=FLOAT),
        np.asarray(triangles, dtype=np.int64),
        int(np.count_nonzero(occupied)),
        occupancy_components(occupied),
        watertight,
        oriented,
        float(volume),
        records,
        tuple(phi_bounds),
    )


def build_monolithic_nems_clutch_mesh(
    design: Design,
    theta_deg: float,
    *,
    subdivisions: int = 1,
    variant: str = "full",
) -> MeshPair:
    """Build full 360-degree conforming external-boundary meshes in micrometres."""
    if variant not in ("full", "isolated", "without_spider", "without_foundation"):
        raise ValueError(f"Unsupported geometry variant {variant!r}.")
    theta = finite_number(theta_deg, "theta_deg")
    if subdivisions < 1:
        raise ValueError("subdivisions must be positive.")
    pair = MeshPair(
        build_surface(design, theta, "rotor", subdivisions, variant),
        build_surface(design, theta, "stator", subdivisions, variant),
    )
    for name, surface in (("rotor", pair.rotor), ("stator", pair.stator)):
        if not surface.watertight or not surface.orientation_consistent:
            raise GeometryError(f"{name} boundary is non-manifold or inconsistently oriented.")
    return pair


def repository_mesh(
    pair: MeshPair | None,
    design: Design,
    theta_deg: float,
    variant: str = "full",
    subdivisions: int = 1,
) -> Any:
    """Use the exact active-zone sector plus structural-support macro-panels."""
    if variant not in ("full", "isolated", "without_spider", "without_foundation"):
        raise ValueError(f"Unsupported geometry variant {variant!r}.")
    if (
        isinstance(subdivisions, (bool, np.bool_))
        or not isinstance(subdivisions, (int, np.integer))
        or subdivisions < 1
    ):
        raise ValueError("subdivisions must be a positive integer.")
    theta_deg = finite_number(theta_deg, "theta_deg")
    repo = repository()
    panel_resolution = {
        "n_r": 2 * subdivisions,
        "n_phi_tooth": 3 * subdivisions,
        "n_phi_bridge": 3 * subdivisions,
        "n_z": 2 * subdivisions,
    }
    # The audit pair remains a full 360-degree occupancy mesh. Do not replace
    # the active solver panels with its coarser, single-centroid tooth walls.
    base_mesh = repo["build_rotational_stepped_clutch_mesh"](
        design.raw_spec, theta_deg, **panel_resolution
    )
    if variant == "isolated":
        return base_mesh

    rotor_faces = list(base_mesh.rotor)
    stator_faces = list(base_mesh.stator)

    def append_support(
        faces: list[Any],
        body: str,
        r0: float,
        r1: float,
        p0: float,
        p1: float,
        z0: float,
        z1: float,
    ) -> None:
        if not (0.0 <= p0 < p1 <= 90.0 and 0.0 < r0 < r1 and z0 < z1):
            raise GeometryError("Invalid structural-support macro-panel bounds.")
        phi0, phi1 = math.radians(p0), math.radians(p1)
        for sign in (-1, 1):
            z_face = z1 if sign > 0 else z0
            faces.append(
                repo["repository_face"](
                    "horizontal",
                    r0=r0,
                    r1=r1,
                    phi0=phi0,
                    phi1=phi1,
                    z0=z_face,
                    z1=z_face,
                    sign=sign,
                    panel_type=f"{body}_{'top' if sign > 0 else 'bottom'}",
                )
            )
            r_face = r1 if sign > 0 else r0
            faces.append(
                repo["repository_face"](
                    "radial",
                    r0=r_face,
                    r1=r_face,
                    phi0=phi0,
                    phi1=phi1,
                    z0=z0,
                    z1=z1,
                    sign=sign,
                    panel_type=f"{body}_radial_wall",
                )
            )
            phi_face = phi1 if sign > 0 else phi0
            faces.append(
                repo["repository_face"](
                    "azimuthal",
                    r0=r0,
                    r1=r1,
                    phi0=phi_face,
                    phi1=phi_face,
                    z0=z0,
                    z1=z1,
                    sign=sign,
                    panel_type=f"{body}_azimuthal_wall",
                )
            )

    clearance = SUPPORT_CLEARANCE_UM
    tooth_angles = segments(design, theta_deg)
    if variant != "without_spider":
        for r0, r1 in design.teeth:
            for p0, p1 in tooth_angles:
                r_mid = 0.5 * (r0 + r1)
                stem_half_w = min(0.015, 0.20 * (r1 - r0))
                # Keep support panels above the tooth top and below the spider
                # bottom: neither interface may contain coincident panels.
                append_support(
                    rotor_faces, "rotor", r_mid - stem_half_w,
                    r_mid + stem_half_w, p0, p1,
                    clearance, 0.350 - clearance,
                )
        for p0, p1 in tooth_angles:
            append_support(
                rotor_faces, "rotor", design.r_min, design.r_max,
                p0, p1, 0.350, 0.470,
            )
    if variant != "without_foundation":
        for r0, r1 in (
            (max(0.08, design.r_min - 0.12), design.r_min - clearance),
            (design.r_max + clearance, design.r_max + 0.12),
        ):
            append_support(
                rotor_faces, "rotor", r0, r1, 0.0, 90.0, 0.350, 0.470
            )

    for r0, r1 in design.rings:
        append_support(
            stator_faces, "stator", r0, r1,
            design.aperture_arc_deg + math.degrees(clearance / design.r_min),
            90.0, -0.115 + clearance, 0.0,
        )
    append_support(
        stator_faces, "stator", design.r_min, design.r_max,
        design.aperture_arc_deg, 90.0, -0.550, -0.265 - clearance,
    )
    if variant != "without_foundation":
        stator_hub = max(0.10, design.r_min - 0.10)
        for r0, r1 in (
            (stator_hub, design.r_min - clearance),
            (design.r_max + clearance, design.r_max + 0.10),
        ):
            append_support(
                stator_faces, "stator", r0, r1, 0.0, 90.0, -0.550, 0.0
            )
        append_support(
            stator_faces, "stator", stator_hub, design.r_max + 0.10,
            0.0, 90.0, -0.650, -0.550 - clearance,
        )

    geom = repo["Geometry"](
        R_min=design.r_min,
        R_max=design.r_max,
        z_tip=-0.100,
        h_teeth=0.450,
        t_membrane=0.025,
        t_landing_pad=0.435,
        theta_deg=theta_deg,
        tooth_arc_deg=design.tooth_arc_deg,
        aperture_arc_deg=design.aperture_arc_deg,
        elements=design.raw_spec.native_elements,
    )
    elements = [dataclasses.asdict(e) for e in design.raw_spec.native_elements]
    parameters = {
        **design.raw_context,
        "theta_deg": theta_deg,
        "theta": theta_deg,
        "material": "Gold",
        "elements": elements,
        "track_elements": elements,
        "clutch_elements": elements,
    }
    config = dict(parameters)
    return repo["ClutchSurfaceMesh"](
        tuple(rotor_faces),
        tuple(stator_faces),
        geom,
        parameters,
        config,
        panel_resolution,
    )


def geometry_object(design: Design, theta: float, mesh: Any) -> Any:
    values = {**fields_of(design.raw_spec), **fields_of(design.raw_context)}
    values.update(
        {
            "name": design.name,
            "design_name": design.name,
            "spec": design.raw_spec,
            "mesh": mesh,
            "surface_mesh": mesh,
            "theta_deg": theta,
            "theta": theta,
            "R_min": design.r_min,
            "R_max": design.r_max,
            "r_min": design.r_min,
            "r_max": design.r_max,
            "ring_intervals": design.rings,
            "tooth_intervals": design.teeth,
            "tooth_arc_deg": design.tooth_arc_deg,
            "aperture_arc_deg": design.aperture_arc_deg,
            "z_tip_um": -0.100,
            "z_tip": -0.100,
            "z_rotor_top_um": 0.470,
            "z_pad_top_um": -0.115,
            "gap_um": 0.015,
            "gap": 0.015,
            "symmetry_order": 4,
            "sector_deg": 90.0,
        }
    )
    return invoke(repository()["Geometry"], values, extra_kwargs=values)


def gold_material() -> Any:
    parameters = {
        "eps_inf": 1.0,
        "omega_p": GOLD_OMEGA_P_INV_UM,
        "gamma": GOLD_GAMMA_INV_UM,
        "omega_p_um_inv": GOLD_OMEGA_P_INV_UM,
        "gamma_um_inv": GOLD_GAMMA_INV_UM,
        "lorentz_oscillators": [],
    }
    values = {
        **parameters,
        "name": "gold",
        "material_name": "gold",
        "material": "gold",
        "model": "drude",
        "kind": "drude",
        "model_type": "drude",
        "dispersion": parameters,
        "parameters": parameters,
        "params": parameters,
        "epsilon_inf": 1.0,
        "plasma_frequency": GOLD_OMEGA_P_INV_UM,
        "damping": GOLD_GAMMA_INV_UM,
    }
    return invoke(
        repository()["MaterialModel"],
        values,
        extra_kwargs={"name": "gold", **parameters},
    )


def force_si(raw_result: Any) -> float:
    if isinstance(raw_result, Mapping) and "f_net_N" in raw_result:
        return finite_number(raw_result["f_net_N"], "f_net_N")
    repo = repository()
    raw = invoke(
        repo["extract_fz"],
        {
            "result": raw_result,
            "results": raw_result,
            "data": raw_result,
            "payload": raw_result,
            "out": raw_result,
        },
    )
    force = finite_number(raw, "extract_fz result")
    data = fields_of(raw_result)
    unit = lookup([data], ("force_unit", "force_units", "units"))
    if isinstance(unit, Mapping):
        unit = unit.get("force")
    if unit is not None:
        normalized = str(unit).strip().lower()
        if normalized in ("n", "newton", "newtons", "si"):
            return force
        if normalized in ("pn", "piconewton", "piconewtons"):
            return force * 1.0e-12
        if normalized in ("nn", "nanonewton", "nanonewtons"):
            return force * 1.0e-9
        if normalized not in ("meep", "meep_units", "dimensionless", "natural"):
            raise RepositoryAPIError(f"Unknown repository force unit {unit!r}.")
    # Legacy unlabelled extract_fz results use the repository's native convention.
    factor = finite_number(repo["MEEP_FORCE_TO_SI"], "MEEP_FORCE_TO_SI")
    if factor <= 0.0:
        raise RepositoryAPIError("MEEP_FORCE_TO_SI must be positive.")
    converted = force * factor
    if not math.isfinite(converted):
        raise ArithmeticError("Force conversion overflowed.")
    return converted


def solve_job(job: Job) -> dict[str, Any]:
    started = time.monotonic()
    design = get_design(job.design_name)
    # Full 360-degree connectivity/collision audits are performed once in main.
    mesh = repository_mesh(
        None, design, job.theta_deg,
        variant=job.variant, subdivisions=job.subdivisions,
    )
    solver_sector_panels = {
        "rotor": len(mesh.rotor),
        "stator": len(mesh.stator),
    }
    solver = repository()["run_bem_casimir_solver"]
    result = solver(
        mesh.parameters,
        n_r=2 * job.subdivisions,
        n_phi_tooth=3 * job.subdivisions,
        n_phi_bridge=3 * job.subdivisions,
        n_z=2 * job.subdivisions,
        n_xi=job.n_xi,
        max_steps=0,
        device=job.device,
        task_id=f"{job.design_name}_{job.variant}_{job.kernel}_{job.theta_deg:g}",
        mesh=mesh,
        record_metrics=False,
        formulation=job.kernel,
    )
    already_si = isinstance(result, Mapping) and "f_net_N" in result
    fz = finite_number(result["f_net_N"], "f_net_N") if already_si else force_si(result)
    return {
        **dataclasses.asdict(job),
        "status": "ok",
        "fz_N": fz,
        "elapsed_s": time.monotonic() - started,
        "solver_sector_panels": solver_sector_panels,
        "solver_sector_deg": 90.0,
        "solver_symmetry_multiplier": 4,
        "force_conversion": (
            "f_net_N already in SI Newtons; no conversion"
            if already_si
            else "extract_fz; explicit result units if supplied, otherwise "
            "repository MEEP_FORCE_TO_SI"
        ),
    }


def solver_worker(jobs: list[Job], output: str, threads: int) -> None:
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["OPENBLAS_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    try:
        import torch

        torch.set_num_threads(threads)
    except ImportError:
        torch = None  # type: ignore[assignment]
    with open(output, "a", encoding="utf-8", buffering=1) as handle:
        for idx, job in enumerate(jobs, start=1):
            started = time.monotonic()
            try:
                result = solve_job(job)
            except Exception as exc:
                result = {
                    **dataclasses.asdict(job),
                    "status": "error",
                    "fz_N": None,
                    "elapsed_s": time.monotonic() - started,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
            handle.write(
                json.dumps(plain(output_metadata(result)), allow_nan=False) + "\n"
            )
            handle.flush()
            print(
                f"[{idx}/{len(jobs)}] {job.design_name} {job.theta_deg:g} "
                f"{job.variant} {job.kernel} {result['status']} "
                f"fz_N={result['fz_N']} elapsed_s={result['elapsed_s']:.3f}",
                flush=True,
            )


def execute_jobs(
    jobs: list[Job], output_dir: Path, timeout_s: float | None, threads: int
) -> list[dict[str, Any]]:
    stream = output_dir / "solver_results.jsonl"
    atomic_text(stream, "")
    if timeout_s is not None and timeout_s <= 0.0:
        return [
            {**dataclasses.asdict(job), "status": "timeout", "fz_N": None}
            for job in jobs
        ]
    timed_out = False
    exitcode = 0
    if timeout_s is None:
        # Avoid spawn/import overhead when no subprocess deadline is requested.
        solver_worker(jobs, str(stream), threads)
    else:
        context = mp.get_context("spawn")
        process = context.Process(
            target=solver_worker, args=(jobs, str(stream), threads), daemon=False
        )
        process.start()
        process.join(timeout_s)
        timed_out = process.is_alive()
        if timed_out:
            process.terminate()
            process.join(1.0)
            if process.is_alive():
                process.kill()
                process.join()
        exitcode = process.exitcode
    completed: list[dict[str, Any]] = []
    for line in stream.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Internal consumers still use measurement status, not artifact status.
        if "measurement_status" in record:
            record["status"] = record["measurement_status"]
        completed.append(record)
    keys = {
        (
            item["design_name"], item["theta_deg"], item["variant"],
            item["kernel"], item["subdivisions"], item["n_xi"],
        )
        for item in completed
    }
    for job in jobs:
        key = (
            job.design_name, job.theta_deg, job.variant, job.kernel,
            job.subdivisions, job.n_xi,
        )
        if key not in keys:
            completed.append(
                {
                    **dataclasses.asdict(job),
                    "status": "timeout" if timed_out else "worker_failed",
                    "fz_N": None,
                    "error": (
                        "Solver subprocess deadline exceeded."
                        if timed_out
                        else f"Solver worker exited with code {exitcode}."
                    ),
                }
            )
    return completed


def epsilon_imaginary(material: str, frequency_inv_um: Array) -> Array:
    u = np.maximum(np.asarray(frequency_inv_um, dtype=FLOAT), np.finfo(FLOAT).tiny)
    if not np.all(np.isfinite(u)):
        raise ValueError("Imaginary frequencies must be finite.")
    if material == "gold":
        # u is an angular wavenumber: convert eV using hbar*c, not h*c.
        result = 1.0 + GOLD_OMEGA_P_INV_UM**2 / (u * (u + GOLD_GAMMA_INV_UM))
    elif material == "silicon_nitride":
        result = 1.0 + 2.89 * 5.85**2 / (u**2 + 0.10 * u + 5.85**2)
    elif material == "silica":
        result = np.full_like(u, 2.10)
    else:
        raise ValueError(f"Unknown material {material!r}.")
    if not np.all(np.isfinite(result)) or np.any(result < 1.0):
        raise ArithmeticError("Invalid imaginary-axis dielectric response.")
    return result


def lifshitz_pressure(
    gap_um: float,
    material_a: str,
    material_b: str,
    *,
    n_legendre: int = 128,
    n_laguerre: int = 96,
) -> float:
    """Zero-temperature planar pressure, negative for attraction, in pascals."""
    gap = finite_number(gap_um, "gap_um")
    if gap <= 0.0 or n_legendre < 2 or n_laguerre < 2:
        raise ValueError("A positive gap and quadrature orders >= 2 are required.")
    t_nodes, t_weights = np.polynomial.legendre.leggauss(n_legendre)
    t = ((t_nodes + 1.0) / 2.0)[None, :]
    wt = (t_weights / 2.0)[None, :]
    x_nodes, x_weights = np.polynomial.laguerre.laggauss(n_laguerre)
    x = x_nodes[:, None]
    wx = x_weights[:, None]
    u = x * t / (2.0 * gap)
    ea = epsilon_imaginary(material_a, u)
    eb = epsilon_imaginary(material_b, u)

    def reflection(epsilon: Array) -> tuple[Array, Array]:
        q = np.sqrt(1.0 + (epsilon - 1.0) * t**2)
        te = (1.0 - q) / (1.0 + q)
        tm = (epsilon - q) / (epsilon + q)
        return te, tm

    tea, tma = reflection(ea)
    teb, tmb = reflection(eb)
    exp_minus_x = np.exp(-x)
    integral = 0.0
    for product in (tea * teb, tma * tmb):
        denominator = 1.0 - product * exp_minus_x
        if np.any(denominator <= 0.0):
            raise ArithmeticError("Invalid Lifshitz reflection denominator.")
        # Laguerre weights already contain exp(-x).
        integral += float(np.sum(wx * wt * x**3 * product / denominator))
    result = -HBAR * LIGHT_SPEED * integral / (
        32.0 * math.pi**2 * (gap * UM_TO_M) ** 4
    )
    if not math.isfinite(result):
        raise ArithmeticError("Non-finite Lifshitz pressure.")
    return result


def angular_overlap(
    first: Sequence[tuple[float, float]], second: Sequence[tuple[float, float]]
) -> float:
    return sum(max(0.0, min(b, d) - max(a, c)) for a, b in first for c, d in second)


def radial_area(ranges: Sequence[tuple[float, float]]) -> float:
    return sum((b * b - a * a) / 2.0 for a, b in ranges)


def pfa_results(design: Design, theta: float) -> dict[str, Any]:
    teeth_angles = segments(design, theta)
    pad_angle = angular_overlap(teeth_angles, [(design.aperture_arc_deg, 90.0)])
    rib_angle = angular_overlap(teeth_angles, [(0.0, design.aperture_arc_deg)])
    tooth_area_um2 = 4.0 * radial_area(design.teeth) * math.radians(design.tooth_arc_deg)
    pad_area_um2 = 4.0 * radial_area(design.teeth) * math.radians(pad_angle)
    spider_rib_area_um2 = 4.0 * radial_area(design.rings) * math.radians(rib_angle)
    areas = {
        "landing_pad": pad_area_um2,
        "spider_to_rib": spider_rib_area_um2,
        "tooth_to_floor": max(0.0, tooth_area_um2 - pad_area_um2),
    }
    gaps = {"landing_pad": 0.015, "spider_to_rib": 0.350, "tooth_to_floor": 0.450}
    results: dict[str, Any] = {
        "design_name": design.name,
        "theta_deg": theta,
        "quadrature": {"gauss_legendre": 128, "gauss_laguerre": 96},
        "areas_um2": areas,
        "gaps_um": gaps,
        "limitations": [
            "Pairwise projected planar areas; not an exact many-body solution.",
            "Only unshielded aperture tooth area is assigned to the trench floor.",
            "No positive-force stepped-edge contribution is invented.",
            "Hub sidewalls and corner diffraction are not planar PFA terms.",
        ],
    }
    for stack, support in (
        ("all_gold", "gold"),
        ("hybrid_silicon_nitride", "silicon_nitride"),
        ("hybrid_silica", "silica"),
    ):
        contributions = {}
        for component, area in areas.items():
            second = "gold" if component == "landing_pad" else support
            pressure = lifshitz_pressure(gaps[component], "gold", second)
            contributions[component] = pressure * area * UM_TO_M**2
        results[stack] = {
            "fz_N": sum(contributions.values()),
            "components_N": contributions,
        }
    results["contrast_weights"] = {}
    for support in ("silicon_nitride", "silica"):
        weights = {}
        for component, gap in (("spider", 0.350), ("foundation", 0.450)):
            au = lifshitz_pressure(gap, "gold", "gold")
            mixed = lifshitz_pressure(gap, "gold", support)
            if abs(au) <= np.finfo(FLOAT).tiny:
                raise ArithmeticError("Gold reference pressure is zero.")
            weights[component] = mixed / au
        results["contrast_weights"][support] = weights
    return results


def exact_collision_audit(design: Design, theta: float) -> dict[str, Any]:
    angle_ranges = segments(design, theta)
    overlaps: list[dict[str, Any]] = []
    aperture_overlap = angular_overlap(
        angle_ranges, [(0.0, design.aperture_arc_deg)]
    )
    landing_overlap = angular_overlap(
        angle_ranges, [(design.aperture_arc_deg, 90.0)]
    )
    for tooth in design.teeth:
        for ring in design.rings:
            width = min(tooth[1], ring[1]) - max(tooth[0], ring[0])
            if width <= EPS:
                continue
            for angular_width, vertical_width, component in (
                (aperture_overlap, 0.025, "aperture_rib"),
                (landing_overlap, 0.100, "landing_sector_rib_clamp"),
            ):
                if angular_width > EPS:
                    overlaps.append(
                        {
                            "rotor_radial_um": tooth,
                            "stator_radial_um": ring,
                            "radial_overlap_um": width,
                            "angular_overlap_deg_per_sector": angular_width,
                            "vertical_overlap_um": vertical_width,
                            "stator_component": component,
                        }
                    )
    audit: dict[str, Any] = {
        "full_geometry_collision_free": not overlaps,
        "intersections": overlaps,
        "minimum_named_vertical_gap_um": 0.015,
    }
    values = {
        **fields_of(design.raw_spec),
        **fields_of(design.raw_context),
        "spec": design.raw_spec,
        "design": design.raw_spec,
        "context": design.raw_context,
        "ctx": design.raw_context,
        "theta_deg": theta,
        "theta": theta,
        "z_tip_um": -0.100,
        "z_tip": -0.100,
        "tooth_segments": angle_ranges,
        "segments": angle_ranges,
    }
    for name in ("angular_state", "collision_certificate"):
        try:
            audit[f"repository_{name}"] = plain(invoke(repository()[name], values))
        except Exception as exc:
            audit[f"repository_{name}_error"] = f"{type(exc).__name__}: {exc}"
    audit["repository_certificate_scope"] = (
        "Repository active-zone certificate is supplementary; the full "
        "occupancy intersection audit is authoritative for extended shanks "
        "and landing-sector rib clamps."
    )
    return audit


def derived_comparison(
    solver_records: Sequence[dict[str, Any]], pfa: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    index = {
        (
            record["design_name"], record["theta_deg"], record["variant"],
            record["kernel"],
        ): record
        for record in solver_records
        if record.get("status") == "ok" and not record.get("convergence")
    }
    output: list[dict[str, Any]] = []
    for reference in pfa:
        name, theta = reference["design_name"], reference["theta_deg"]
        for kernel in ("vector_dyadic", "scalar_yukawa"):
            base = {
                "design_name": name,
                "theta_deg": theta,
                "solver": kernel,
                "model": "homogeneous BEM",
            }
            full = index.get((name, theta, "full", kernel))
            isolated = index.get((name, theta, "isolated", kernel))
            no_spider = index.get((name, theta, "without_spider", kernel))
            no_foundation = index.get((name, theta, "without_foundation", kernel))
            for label, record in (("all_gold_full", full), ("all_gold_isolated", isolated)):
                output.append(
                    {
                        **base,
                        "stack": label,
                        "fz_N": record["fz_N"] if record else None,
                        "status": "ok" if record else "unavailable",
                    }
                )
            if full and isolated and no_spider and no_foundation:
                f = float(full["fz_N"])
                active = float(isolated["fz_N"])
                spider = f - float(no_spider["fz_N"])
                foundation = f - float(no_foundation["fz_N"])
                interaction = f - active - spider - foundation
                for material in ("silicon_nitride", "silica"):
                    weights = reference["contrast_weights"][material]
                    weighted_spider = weights["spider"] * spider
                    weighted_foundation = weights["foundation"] * foundation
                    # Cross-component scattering has no unique local allocation.
                    cross_weight = math.sqrt(weights["spider"] * weights["foundation"])
                    weighted_interaction = cross_weight * interaction
                    output.append(
                        {
                            **base,
                            "stack": f"hybrid_{material}",
                            "model": "component-weighted BEM approximation",
                            "status": "ok",
                            "fz_N": (
                                active + weighted_spider
                                + weighted_foundation + weighted_interaction
                            ),
                            "active_N": active,
                            "spider_N": weighted_spider,
                            "foundation_N": weighted_foundation,
                            "nonadditive_residual_N": weighted_interaction,
                            "gold_active_N": active,
                            "gold_spider_N": spider,
                            "gold_foundation_N": foundation,
                            "gold_nonadditive_residual_N": interaction,
                            "weighting": weights,
                        }
                    )
            else:
                for material in ("silicon_nitride", "silica"):
                    output.append(
                        {
                            **base,
                            "stack": f"hybrid_{material}",
                            "model": "component-weighted BEM approximation",
                            "status": "unavailable",
                            "fz_N": None,
                        }
                    )
        for stack in ("all_gold", "hybrid_silicon_nitride", "hybrid_silica"):
            output.append(
                {
                    "design_name": name,
                    "theta_deg": theta,
                    "solver": "continuum_lifshitz_pfa",
                    "model": "zero-temperature projected-area Lifshitz-PFA",
                    "stack": stack,
                    "status": "ok",
                    "fz_N": reference[stack]["fz_N"],
                    **reference[stack]["components_N"],
                }
            )
    return output


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    columns = (
        "design_name", "theta_deg", "solver", "model", "dataset", "stack",
        "status", "measurement_status", "executed_at",
        "fz_N", "active_N", "spider_N", "foundation_N",
        "nonadditive_residual_N", "landing_pad", "spider_to_rib", "tooth_to_floor",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".forces.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                serialized = output_metadata(row)
                writer.writerow(
                    {
                        key: "" if serialized.get(key) is None else serialized.get(key, "")
                        for key in columns
                    }
                )
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def metrics_call(
    name: str,
    values: Mapping[str, Any],
    warnings: list[str],
    *,
    extra_kwargs: Mapping[str, Any] | None = None,
) -> None:
    try:
        invoke(repository()[name], values, extra_kwargs=extra_kwargs)
    except Exception as exc:
        warnings.append(f"{name}: {type(exc).__name__}: {exc}")


def provenance_values(provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provenance": dict(provenance),
        "metadata": dict(provenance),
        "data": dict(provenance),
        "solver": "real_world_nems_clutch",
        "solver_name": "real_world_nems_clutch",
        "name": "real_world_nems_clutch",
        "method": "BEM and continuum dispersive Lifshitz-PFA",
        "device": provenance["device"],
        "script": str(Path(__file__).resolve()),
        "script_path": str(Path(__file__).resolve()),
        "source": str(Path(__file__).resolve()),
        "run_id": provenance["run_id"],
    }


def plot_report(
    rows: Sequence[dict[str, Any]],
    solver_records: Sequence[dict[str, Any]],
    report: Mapping[str, Any],
    figure_dir: Path,
    warnings: list[str],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 9.0), constrained_layout=True)
    ax_a, ax_b, ax_c, ax_d = axes.flat
    colors = dict(zip(DESIGN_NAMES, ("tab:blue", "tab:orange", "tab:green")))

    def curve(
        ax: Any, selected: Sequence[dict[str, Any]], label: str, **kwargs: Any
    ) -> None:
        valid = [
            row for row in selected
            if row.get("status") == "ok" and row.get("fz_N") is not None
        ]
        valid.sort(key=lambda row: float(row["theta_deg"]))
        if valid:
            ax.plot(
                [row["theta_deg"] for row in valid],
                [float(row["fz_N"]) * 1.0e12 for row in valid],
                marker="o", label=label, **kwargs,
            )

    for name in DESIGN_NAMES:
        for stack, style in (("all_gold_full", "-"), ("all_gold_isolated", "--")):
            curve(
                ax_a,
                [
                    row for row in rows
                    if row["design_name"] == name
                    and row["solver"] == "vector_dyadic" and row["stack"] == stack
                ],
                f"{name.replace('Rot_', '')}: {stack.replace('all_gold_', '')}",
                color=colors[name], linestyle=style,
            )
    first_name = next(
        iter(report["provenance"]["sampled_angles"]), DESIGN_NAMES[0]
    )
    for solver, stack, label in (
        ("vector_dyadic", "all_gold_full", "Vector dyadic BEM"),
        ("scalar_yukawa", "all_gold_full", "Scalar Yukawa BEM"),
        ("continuum_lifshitz_pfa", "all_gold", "Dispersive Lifshitz-PFA"),
    ):
        curve(
            ax_b,
            [
                row for row in rows
                if row["design_name"] == first_name
                and row["solver"] == solver and row["stack"] == stack
            ],
            label,
        )

    hybrid_rows = [
        row for row in rows
        if row["design_name"] == first_name
        and row["solver"] == "vector_dyadic"
        and row["stack"] == "hybrid_silicon_nitride"
        and row.get("status") == "ok"
    ]
    if hybrid_rows:
        for key, label in (
            ("active_N", "Isolated active zone"),
            ("spider_N", "Weighted upper spider"),
            ("foundation_N", "Weighted floor and hubs"),
            ("nonadditive_residual_N", "Weighted nonadditive residual"),
        ):
            ordered = sorted(hybrid_rows, key=lambda row: row["theta_deg"])
            ax_c.plot(
                [row["theta_deg"] for row in ordered],
                [float(row[key]) * 1.0e12 for row in ordered],
                marker="o", label=label,
            )
    else:
        ax_c.text(
            0.5, 0.5, "Hybrid BEM breakdown unavailable\n"
            "(failed, timed-out, or unrequested ablation solves)",
            ha="center", va="center", transform=ax_c.transAxes,
        )

    convergence = [
        row for row in solver_records
        if row.get("status") == "ok" and row.get("convergence")
    ]
    for theta in (0.0, 48.0):
        for kernel, style in (("vector_dyadic", "-"), ("scalar_yukawa", "--")):
            baseline = [
                row for row in solver_records
                if row.get("status") == "ok"
                and not row.get("convergence")
                and row["design_name"] == DESIGN_NAMES[0]
                and row["theta_deg"] == theta
                and row["variant"] == "full" and row["kernel"] == kernel
            ]
            selected = baseline + [
                row for row in convergence
                if row["design_name"] == DESIGN_NAMES[0]
                and row["theta_deg"] == theta
                and row["variant"] == "full" and row["kernel"] == kernel
                and any(
                    row["n_xi"] == max(12, 2 * base["n_xi"])
                    for base in baseline
                )
            ]
            if selected:
                selected.sort(key=lambda row: row["n_xi"])
                ax_d.plot(
                    [row["n_xi"] for row in selected],
                    [float(row["fz_N"]) * 1.0e12 for row in selected],
                    marker="o", linestyle=style,
                    label=f"{theta:g}°, {kernel}",
                )
    if not convergence:
        ax_d.text(
            0.5, 0.5, "Refined quadrature convergence not available",
            ha="center", va="center", transform=ax_d.transAxes,
        )

    titles = (
        "A  Full monolithic vs isolated active zone",
        f"B  Three solver models: {first_name}",
        "C  Selective Au / Si₃N₄ component-weighted approximation",
        "D  Quadrature convergence (refined nξ = max(12, 2 × baseline nξ))",
    )
    for index, (ax, title) in enumerate(zip(axes.flat, titles)):
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Quadrature order nξ" if index == 3 else "Rotor angle (deg)")
        ax.set_ylabel("Rotor Fz (pN); +z upward")
        ax.axhline(0.0, color="0.5", linewidth=0.7)
        ax.grid(alpha=0.25)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, fontsize=7)
        elif index in (0, 1):
            ax.text(
                0.5, 0.5, "No successful BEM measurements",
                ha="center", va="center", transform=ax.transAxes,
            )
    fig.suptitle(
        f"Real-world NEMS clutch — {report['verification_status']}\n"
        "Geometry/material approximations and failed measurements are disclosed in the report",
        fontsize=11,
    )
    base = figure_dir / "fig_real_world_nems_clutch_verification"
    for suffix in (".png", ".pdf"):
        path = base.with_suffix(suffix)
        fig.savefig(path, dpi=180)
        provenance = dict(report["provenance"])
        provenance.update(
            {
                "figure": str(path),
                "verification_status": report["verification_status"],
                "hybrid_model": "component-weighted BEM approximation",
                "report": str(ROOT / "results/real_world_nems_clutch_report.json"),
            }
        )
        metrics_call(
            "save_plot_provenance",
            {
                **provenance_values(provenance),
                "path": str(path),
                "plot_path": str(path),
                "figure_path": str(path),
                "filename": str(path),
                "fig_path": str(path),
            },
            warnings,
            extra_kwargs={"provenance": provenance},
        )
        write_json(Path(str(path) + ".provenance.json"), provenance)
    write_json(base.with_suffix(".provenance.json"), report["provenance"])
    plt.close(fig)


def markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        "# Real-world monolithic NEMS clutch verification",
        "",
        f"**Status: {report['verification_status']}**",
        "",
        "Forces are in SI newtons; positive force is upward on the rotor. "
        "Unavailable values are not zero forces.",
        "",
        "Artifact status `completed` indicates output generation only; "
        "`measurement_status` retains failed or unavailable measurement states.",
        "",
        "## Scope and limitations",
        "",
    ]
    for issue in report["limitations"]:
        lines.append(f"- {issue}")
    lines.extend(
        [
            "",
            "## Mechanical and mesh audit",
            "",
            "| Design | Angle (deg) | Rotor components | Stator components | "
            "Watertight | Collision-free |",
            "|---|---:|---:|---:|:---:|:---:|",
        ]
    )
    for item in report["geometry_audits"]:
        if item.get("status") != "ok":
            lines.append(
                f"| {item['design_name']} | {item['theta_deg']:g} | — | — | "
                f"ERROR | — |"
            )
            continue
        rotor, stator = item["mesh"]["rotor"], item["mesh"]["stator"]
        lines.append(
            f"| {item['design_name']} | {item['theta_deg']:g} | "
            f"{rotor['connected_components']} | {stator['connected_components']} | "
            f"{rotor['watertight'] and stator['watertight']} | "
            f"{item['collision']['full_geometry_collision_free']} |"
        )
    lines.extend(
        [
            "",
            "## Solver execution",
            "",
            f"- Requested BEM measurements: {len(report['solver_results'])}",
            f"- Successful BEM measurements: {report['successful_bem_measurements']}",
            "- BEM receives one 90-degree sector with face angles in radians; "
            "the repository solver applies four-fold cyclic symmetry.",
            "- Repository `f_net_N` results are already SI newtons.",
            "- Continuum PFA: 128-point Gauss-Legendre × "
            "96-point Gauss-Laguerre, zero temperature.",
            "- Hybrid weighting: mixed Au/dielectric planar pressure divided by "
            "Au/Au pressure at 350 nm for spider and 450 nm for foundation.",
            "- Component ablations are nonadditive scattering differences. "
            "The residual is retained and disclosed.",
            "",
            "## Convergence",
            "",
            "| Angle | Kernel | Relative refined/baseline change | Sign |",
            "|---:|---|---:|---|",
        ]
    )
    for item in report["convergence"]:
        relative = item.get("relative_change")
        rendered = "unavailable" if relative is None else f"{relative:.6g}"
        lines.append(
            f"| {item['theta_deg']:g} | {item['kernel']} | "
            f"{rendered} | {item.get('observed_sign', 'unavailable')} |"
        )
    errors = [
        item for item in report["solver_results"] if item.get("status") != "ok"
    ]
    if errors:
        lines.extend(["", "## Failed or unavailable measurements", ""])
        for item in errors:
            message = str(item.get("error", item["status"])).replace("\n", " ")
            lines.append(
                f"- {item['design_name']}, {item['theta_deg']:g}°, "
                f"{item['variant']}, {item['kernel']}: {message}"
            )
    if report["warnings"]:
        lines.extend(["", "## Provenance/output warnings", ""])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `results/real_world_nems_clutch_config.json`",
            "- `results/real_world_nems_clutch_report.json`",
            "- `results/real_world_nems_clutch/forces_comparison.csv`",
            "- `figures/fig_real_world_nems_clutch_verification.png` and `.pdf` "
            "(unless plotting was disabled)",
            "",
            "A mechanically disconnected geometry is not certified as a "
            "complete zero-floating-parts device, even if its field solve succeeds.",
            "",
        ]
    )
    return "\n".join(lines)


def convergence_summary(
    records: Sequence[dict[str, Any]], tolerance: float
) -> list[dict[str, Any]]:
    output = []
    for theta in (0.0, 48.0):
        for kernel in ("vector_dyadic", "scalar_yukawa"):
            selected = [
                item for item in records
                if item.get("status") == "ok"
                and item["design_name"] == DESIGN_NAMES[0]
                and item["theta_deg"] == theta
                and item["variant"] == "full" and item["kernel"] == kernel
            ]
            baseline = next(
                (item for item in selected if not item.get("convergence")), None
            )
            refined = next(
                (
                    item for item in selected
                    if item.get("convergence")
                    and baseline is not None
                    and item["n_xi"] == max(12, 2 * baseline["n_xi"])
                ),
                None,
            )
            item: dict[str, Any] = {
                "theta_deg": theta,
                "kernel": kernel,
                "expected_sign": "repulsive" if theta == 0.0 else "attractive",
                "relative_change": None,
                "within_tolerance": False,
                "expected_sign_verified": False,
            }
            if baseline and refined:
                f0, f1 = float(baseline["fz_N"]), float(refined["fz_N"])
                scale = max(abs(f0), abs(f1))
                change = abs(f1 - f0) / scale if scale > 0.0 else 0.0
                sign = "repulsive" if f1 > 0.0 else "attractive" if f1 < 0.0 else "zero"
                item.update(
                    {
                        "baseline_fz_N": f0,
                        "refined_fz_N": f1,
                        "baseline_n_xi": baseline["n_xi"],
                        "refined_n_xi": refined["n_xi"],
                        "relative_change": change,
                        "within_tolerance": change <= tolerance,
                        "observed_sign": sign,
                        "expected_sign_verified": sign == item["expected_sign"],
                        "baseline_panels": sum(
                            baseline["solver_sector_panels"][body]
                            for body in ("rotor", "stator")
                        ),
                        "refined_panels": sum(
                            refined["solver_sector_panels"][body]
                            for body in ("rotor", "stator")
                        ),
                    }
                )
            output.append(item)
    return output


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps", type=int, default=0,
        help="0 runs all angles; 1..5 performs one micro-probe; "
        ">5 limits design-angle samples.",
    )
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--plot", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--n-xi", type=int, default=6)
    parser.add_argument("--subdivisions", type=int, default=1)
    parser.add_argument("--convergence-subdivisions", type=int, default=1)
    parser.add_argument("--convergence-tolerance", type=float, default=0.05)
    parser.add_argument(
        "--solver-timeout", type=float, default=0.0,
        help="Total BEM subprocess deadline in seconds; 0 runs in-process "
        "without a deadline.",
    )
    parser.add_argument("--threads", type=int, default=min(8, os.cpu_count() or 4))
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 2 if complete verification fails (micro-probes still exit 0).",
    )
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative.")
    if args.n_xi < 2 or args.subdivisions < 1 or args.threads < 1:
        parser.error("--n-xi >= 2, --subdivisions >= 1, and --threads >= 1 required.")
    if args.convergence_subdivisions < args.subdivisions:
        parser.error("--convergence-subdivisions must be >= --subdivisions.")
    if not math.isfinite(args.solver_timeout) or args.solver_timeout < 0.0:
        parser.error("--solver-timeout must be finite and nonnegative.")
    if (
        not math.isfinite(args.convergence_tolerance)
        or not 0.0 < args.convergence_tolerance < 1.0
    ):
        parser.error("--convergence-tolerance must be between 0 and 1.")
    return args


def detect_device(requested: str) -> str:
    try:
        import torch
    except ImportError:
        if requested == "cuda":
            raise RuntimeError("--device cuda requires PyTorch and CUDA.")
        return "cpu"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and device != "cuda":
        raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is false.")
    return device if requested == "auto" else requested


def main() -> int:
    args = parse_arguments()
    micro = 0 < args.max_steps <= 5
    results_dir = ROOT / "results"
    output_dir = results_dir / "real_world_nems_clutch"
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    device = detect_device(args.device)
    designs = [get_design(name) for name in DESIGN_NAMES]
    config = configuration(designs)
    write_json(results_dir / "real_world_nems_clutch_config.json", config)

    provenance: dict[str, Any] = {
        "run_id": f"real_world_nems_clutch_{time.time_ns()}",
        "script": str(Path(__file__).resolve()),
        "device": device,
        "python": sys.version,
        "numpy": np.__version__,
        "arguments": vars(args),
        "micro_probe": micro,
        "force_units": "N",
        "length_units": "um",
        "full_360_degree_mesh": True,
        "solver_sector_deg": 90.0,
        "solver_face_angular_unit": "rad",
        "solver_symmetry_multiplier": 4,
        "temperature_K": 0.0,
        "gold_model": config["materials"]["gold"],
        "hybrid_model": "component-weighted BEM approximation",
        "no_fabricated_solver_results": True,
        "model": "BEM and continuum dispersive Lifshitz-PFA",
        "dataset": DATASET,
        "executed_at": EXECUTED_AT,
    }
    all_samples = [
        (design, float(theta))
        for design in designs
        for theta in (
            (0.0, 3.0, 21.0, 30.0, 48.0)
            if design.name == DESIGN_NAMES[2]
            else (0.0, 18.0, 36.0, 48.0)
        )
    ]
    samples = (
        all_samples[:1] if micro
        else all_samples[: args.max_steps] if args.max_steps > 0
        else all_samples
    )
    provenance["sampled_angles"] = {
        design.name: sorted(
            theta for sampled_design, theta in samples
            if sampled_design.name == design.name
        )
        for design in designs
        if any(sampled_design.name == design.name for sampled_design, _ in samples)
    }
    metrics_call(
        "set_solver_provenance",
        provenance_values(provenance),
        warnings,
        extra_kwargs=provenance,
    )
    n_xi = 4 if micro else args.n_xi
    subdivisions = 1 if micro else args.subdivisions
    audits: list[dict[str, Any]] = []
    pfa: list[dict[str, Any]] = []
    jobs: list[Job] = []
    for step, (design, theta) in enumerate(samples):
        try:
            pair = build_monolithic_nems_clutch_mesh(
                design, theta, subdivisions=subdivisions
            )
            audit = {
                "design_name": design.name,
                "theta_deg": theta,
                "status": "ok",
                "mesh": {"rotor": pair.rotor.summary(), "stator": pair.stator.summary()},
                "collision": exact_collision_audit(design, theta),
                "zero_floating_parts": (
                    pair.rotor.connected_components == 1
                    and pair.stator.connected_components == 1
                ),
            }
        except Exception as exc:
            audit = {
                "design_name": design.name,
                "theta_deg": theta,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "zero_floating_parts": False,
            }
        audits.append(audit)
        pfa.append(pfa_results(design, theta))
        metrics_call(
            "log_step",
            {
                "step": step,
                "iteration": step,
                "data": audit,
                "metrics": audit,
                "payload": audit,
                "record": audit,
                "name": "geometry_audit",
            },
            warnings,
            extra_kwargs={"design": design.name, "theta_deg": theta},
        )
        if audit["status"] == "ok" and audit["collision"]["full_geometry_collision_free"]:
            variants = (
                ("full", "isolated")
                if micro
                else ("full", "isolated", "without_spider", "without_foundation")
            )
            kernels = (
                ("vector_dyadic",)
                if micro
                else ("vector_dyadic", "scalar_yukawa")
            )
            for variant in variants:
                for kernel in kernels:
                    jobs.append(
                        Job(
                            design.name, theta, variant, kernel,
                            subdivisions, n_xi, device,
                        )
                    )
    if not micro:
        for theta in (0.0, 48.0):
            if any(
                design.name == DESIGN_NAMES[0] and sample_theta == theta
                for design, sample_theta in samples
            ):
                for kernel in ("vector_dyadic", "scalar_yukawa"):
                    jobs.append(
                        Job(
                            DESIGN_NAMES[0], theta, "full", kernel,
                            args.convergence_subdivisions,
                            max(12, 2 * n_xi), device, True,
                        )
                    )
    timeout: float | None = args.solver_timeout or None
    records = execute_jobs(jobs, output_dir, timeout, args.threads) if jobs else []
    for step, record in enumerate(records):
        if record.get("status") == "ok":
            metrics_call(
                "log_metric",
                {
                    "name": "nems_rotor_fz_N",
                    "metric": "nems_rotor_fz_N",
                    "key": "nems_rotor_fz_N",
                    "value": record["fz_N"],
                    "step": step,
                    "iteration": step,
                    "metadata": {
                        key: record[key]
                        for key in ("design_name", "theta_deg", "variant", "kernel")
                    },
                },
                warnings,
                extra_kwargs={"step": step},
            )
    rows = derived_comparison(records, pfa)
    write_csv(output_dir / "forces_comparison.csv", rows)
    convergence = convergence_summary(records, args.convergence_tolerance)
    successful = sum(record.get("status") == "ok" for record in records)
    connected = bool(audits) and all(
        audit.get("status") == "ok" and audit.get("zero_floating_parts")
        and audit["collision"]["full_geometry_collision_free"]
        for audit in audits
    )
    complete_sampling = len(samples) == len(all_samples)
    numerical_ok = (
        bool(records) and successful == len(records)
        and all(
            item["within_tolerance"] and item["expected_sign_verified"]
            for item in convergence
        )
    )
    # Exact multilayer/heterogeneous optics and actual comb actuation are not
    # specified or solved, so complete real-world certification is withheld.
    status = (
        "MICRO-PROBE: NOT A COMPLETE VERIFICATION"
        if micro
        else "NOT VERIFIED: SPECIFICATION OR MODEL LIMITATIONS"
    )
    limitations = list(config["specification_conflicts"]) + [
        "Selective metallization is a component-weighted homogeneous-BEM "
        "approximation, not an exact heterogeneous or finite-thickness coating solve.",
        "The silica comparison uses the specified static dielectric constant; "
        "a silica dispersion curve was not supplied.",
        "PFA is a zero-temperature planar projected-area comparison and "
        "cannot verify stepped-edge repulsion.",
        "The convergence check increases n_xi to max(12, 2 * baseline n_xi); "
        "panel subdivisions may also increase. Separate mesh and quadrature "
        "error contributions are not independently established.",
        "No load-bearing stress, buckling, release fabrication, stiction, "
        "electrical actuation, shaft bearing, or finite-temperature verification "
        "is claimed.",
        "Solves run in-process without a deadline by default. An explicitly "
        "requested deadline bounds the solver subprocess, not arbitrary "
        "third-party import, plotting, or filesystem latency.",
    ]

    comparison_index = {
        (row["design_name"], row["theta_deg"], row["solver"], row["stack"]):
        row["fz_N"]
        for row in rows
        if row.get("status") == "ok"
    }
    report_designs: dict[str, Any] = {}
    for design in designs:
        angles = provenance["sampled_angles"].get(design.name, [])
        report_designs[design.name] = {
            "R_min_um": design.r_min,
            "R_max_um": design.r_max,
            "ring_intervals_um": design.rings,
            "tooth_intervals_um": design.teeth,
            "aperture_arc_deg": design.aperture_arc_deg,
            "tooth_arc_deg": design.tooth_arc_deg,
            "theta_deg": list(angles),
            "full_monolithic_fz_N": [
                comparison_index.get(
                    (design.name, theta, "vector_dyadic", "all_gold_full")
                )
                for theta in angles
            ],
            "isolated_active_zone_fz_N": [
                comparison_index.get(
                    (design.name, theta, "vector_dyadic", "all_gold_isolated")
                )
                for theta in angles
            ],
            "continuum_lifshitz_pfa_fz_N": [
                comparison_index.get(
                    (design.name, theta, "continuum_lifshitz_pfa", "all_gold")
                )
                for theta in angles
            ],
        }

    report: dict[str, Any] = {
        "schema_version": 1,
        "model": "BEM and continuum dispersive Lifshitz-PFA",
        "dataset": DATASET,
        "status": "completed",
        "executed_at": EXECUTED_AT,
        "verification_status": status,
        "complete_device_verified": False,
        "mechanical_connectivity_verified": connected,
        "full_angle_sampling_completed": complete_sampling,
        "numerical_checks_passed": numerical_ok,
        "successful_bem_measurements": successful,
        "designs": report_designs,
        "geometry_audits": audits,
        "solver_results": records,
        "lifshitz_pfa": pfa,
        "comparison": [output_metadata(row) for row in rows],
        "convergence": convergence,
        "convergence_relative_tolerance": args.convergence_tolerance,
        "limitations": limitations,
        "warnings": warnings,
        "provenance": provenance,
    }
    metrics_call(
        "export_macros",
        {
            "path": str(output_dir / "verification_macros.tex"),
            "output_path": str(output_dir / "verification_macros.tex"),
            "filename": str(output_dir / "verification_macros.tex"),
            "macros": {
                "NEMSMeasurementsSuccessful": successful,
                "NEMSMeasurementsRequested": len(records),
                "NEMSMechanicalConnectivityVerified": int(connected),
            },
            "metrics": {
                "successful_bem_measurements": successful,
                "requested_bem_measurements": len(records),
            },
        },
        warnings,
    )
    if args.plot:
        try:
            plot_report(rows, records, report, ROOT / "figures", warnings)
        except Exception as exc:
            warnings.append(f"Plot generation: {type(exc).__name__}: {exc}")
    report["elapsed_s"] = time.monotonic() - SCRIPT_START
    report["micro_probe_under_15s"] = (
        report["elapsed_s"] < 15.0 if micro else None
    )
    write_json(results_dir / "real_world_nems_clutch_report.json", report)
    atomic_text(
        results_dir / "real_world_nems_clutch_report.md", markdown_report(report)
    )
    print(
        f"{status}\n"
        f"BEM: {successful}/{len(records)} successful; "
        f"mechanically connected: {connected}; "
        f"elapsed: {report['elapsed_s']:.3f} s\n"
        f"Report: {results_dir / 'real_world_nems_clutch_report.json'}",
        flush=True,
    )
    return 0 if micro or not args.strict else 2


if __name__ == "__main__":
    mp.freeze_support()
    try:
        raise SystemExit(main())
    except (RepositoryAPIError, GeometryError, RuntimeError, OSError) as error:
        fatal_path = ROOT / "results/real_world_nems_clutch_report.json"
        fatal_report = {
            "schema_version": 1,
            "verification_status": "PREPARATION FAILED",
            "complete_device_verified": False,
            "measurement_status": "error",
            "error": f"{type(error).__name__}: {error}",
            "traceback": traceback.format_exc(),
            "elapsed_s": time.monotonic() - SCRIPT_START,
        }
        try:
            write_json(fatal_path, fatal_report)
            atomic_text(
                fatal_path.with_suffix(".md"),
                "# Real-world NEMS clutch\n\n"
                "**Preparation failed; no verification is claimed.**\n\n"
                f"```text\n{fatal_report['error']}\n```\n",
            )
        except OSError as output_error:
            print(f"Could not write failure report: {output_error}", file=sys.stderr)
        print(fatal_report["error"], file=sys.stderr)
        raise SystemExit(1) from error
