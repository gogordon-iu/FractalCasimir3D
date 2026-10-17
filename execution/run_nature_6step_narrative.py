#!/usr/bin/env python3
"""Execute the grounded six-step Fractal Casimir Rotary Clutch campaign.

Run from any directory:
    python execution/run_nature_6step_narrative.py
    python execution/run_nature_6step_narrative.py --max-steps 1

The repository's active-sector builder is reused directly, rather than
duplicated. All reported forces and energies come from the repository solver.
A micro-probe produces explicitly incomplete reports, never synthetic results.

Freshness metadata describes completed report/table-record generation.
campaign_status and source_status retain computation and measurement status.
"""

from __future__ import annotations

import argparse
import copy
import csv
import dataclasses
import hashlib
import importlib
import inspect
import json
import math
import os
import sys
import tempfile
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from execution.casimir_bem_solver import (
    ClutchSurfaceMesh,
    Geometry,
    TrackElement,
    _azimuthal,
    _horizontal,
    _radial,
    run_bem_casimir_solver,
)
from execution.clutch_geometry_redesign import get_scoped_clutch_elements
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

Body = Literal["rotor", "stator"]
Formulation = Literal["scalar_yukawa", "vector_dyadic"]

SECTOR_ANGLE = math.pi / 2.0
HBAR_C_PN_UM2 = 0.031615267735
# Meep force units are hbar*c/um^2, converted here to newtons.
MEEP_FORCE_TO_SI_N = HBAR_C_PN_UM2 * 1e-12
MEEP_CACHE_VERSION = 6
SOLVER_NAME = "execution.casimir_bem_solver.run_bem_casimir_solver"
REPORT_MODEL = "BEM_Meep_Nature6Step"
REPORT_DATASET = "nature_6step_narrative"
STEP_NAMES = (
    "step1_single_tooth_ztip",
    "step2_n0_angular_sweep",
    "step3_fractal_hierarchy",
    "step4_fractal_advantage",
    "step5_best_active_configuration",
    "step6_monolithic_ultrahigh_validation",
)
_MISSING = object()


@dataclass(frozen=True, slots=True)
class TrackSpec3D:
    r_inner: float
    r_outer: float
    r_tooth_in: float
    r_tooth_out: float
    z_tip: float
    h_teeth: float
    level: int

    def __post_init__(self) -> None:
        values = (
            self.r_inner,
            self.r_outer,
            self.r_tooth_in,
            self.r_tooth_out,
            self.z_tip,
            self.h_teeth,
        )
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Track dimensions must be finite.")
        if not (
            0.0 < self.r_inner < self.r_tooth_in
            < self.r_tooth_out < self.r_outer
        ):
            raise ValueError(f"Invalid tooth/slot radial bounds: {self!r}")
        if (
            self.h_teeth <= 0.0
            or isinstance(self.level, bool)
            or not isinstance(self.level, int)
            or self.level < 1
        ):
            raise ValueError("Tooth height must be positive; level a positive integer.")

    @property
    def z_top(self) -> float:
        return self.z_tip + self.h_teeth


@dataclass(frozen=True, slots=True)
class StudyDesign:
    name: str
    tracks: tuple[TrackSpec3D, ...]
    R_min: float
    R_max: float
    aperture_arc_deg: float = 36.0
    tooth_arc_deg: float = 15.0
    t_membrane: float = 0.025
    t_landing_pad: float = 0.150
    z_pad_top: float = -0.115
    generation: int = 2
    w1_ratio: float = 0.65
    min_tooth_w: float = 0.020

    def __post_init__(self) -> None:
        if not self.name or not self.tracks:
            raise ValueError("A design needs a name and at least one track.")
        dimensions = (
            self.R_min,
            self.R_max,
            self.aperture_arc_deg,
            self.tooth_arc_deg,
            self.t_membrane,
            self.t_landing_pad,
            self.z_pad_top,
            self.w1_ratio,
            self.min_tooth_w,
        )
        if not all(math.isfinite(v) for v in dimensions):
            raise ValueError("Design dimensions must be finite.")
        if not 0.0 < self.R_min < self.R_max:
            raise ValueError("Invalid annulus.")
        if not 0.0 < self.tooth_arc_deg < self.aperture_arc_deg < 90.0:
            raise ValueError("Require 0 < tooth arc < aperture arc < 90 degrees.")
        if self.t_membrane <= 0.0 or self.t_landing_pad <= 0.0:
            raise ValueError("Stator thicknesses must be positive.")
        previous = self.R_min
        for track in sorted(self.tracks, key=lambda item: item.r_inner):
            if track.r_inner < previous - 1e-9:
                raise ValueError("Overlapping or out-of-annulus tracks.")
            if track.r_outer > self.R_max + 1e-9:
                raise ValueError("Track exceeds outer radius.")
            previous = track.r_outer

    @property
    def footprint_um2(self) -> float:
        """Full-device annular footprint; symmetry is not counted twice."""
        return math.pi * (self.R_max**2 - self.R_min**2)


@dataclass(frozen=True, slots=True)
class Resolution:
    name: str
    n_r: int
    n_phi_tooth: int
    n_phi_bridge: int
    n_z: int
    n_xi: int

    def __post_init__(self) -> None:
        for value in (
            self.n_r,
            self.n_phi_tooth,
            self.n_phi_bridge,
            self.n_z,
            self.n_xi,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("Resolution counts must be positive integers.")


STANDARD = Resolution("Standard", 1, 2, 2, 2, 10)
HIGH = Resolution("High", 1, 3, 3, 2, 12)
ULTRA_HIGH = Resolution("Ultra_High", 2, 3, 3, 2, 14)


@dataclass(frozen=True, slots=True)
class Task:
    step: str
    design: StudyDesign
    theta_deg: float
    formulation: Formulation
    resolution: Resolution = STANDARD
    boundary: Literal["Active-Only", "Full-Monolithic"] = "Active-Only"
    purpose: str = ""

    @property
    def cache_key(self) -> str:
        content = {
            "design": dataclasses.asdict(self.design),
            "theta_deg": self.theta_deg,
            "formulation": self.formulation,
            "resolution": dataclasses.asdict(self.resolution),
            "boundary": self.boundary,
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, allow_nan=False).encode("utf-8")
        ).hexdigest()


def finite_float(value: Any, label: str) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise TypeError(f"{label} must be a real number, not {type(value).__name__}.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"{label} must be a real scalar.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite.")
    return result


def json_safe(value: Any) -> Any:
    """Serialize solver diagnostics without admitting NaN/Infinity into JSON."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if hasattr(value, "detach"):
        return json_safe(value.detach().cpu().tolist())
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return json_safe(value.item())
    return repr(value)


def freshness_metadata(executed_at: str | None = None) -> dict[str, str]:
    return {
        "model": REPORT_MODEL,
        "dataset": REPORT_DATASET,
        "status": "completed",
        "executed_at": (
            executed_at
            if executed_at is not None
            else datetime.now(timezone.utc).isoformat()
        ),
    }


def freshness_record(
    row: Mapping[str, Any], executed_at: str
) -> dict[str, Any]:
    """Stamp an emitted record without disguising unavailable measurements."""
    result = dict(row)
    if "status" in result and result["status"] != "completed":
        result["source_status"] = result["status"]
    result.update(freshness_metadata(executed_at))
    return result


def freshness_tables(value: Any, executed_at: str) -> Any:
    """Stamp JSON table rows after computation, leaving solver inputs untouched."""
    if isinstance(value, Mapping):
        return {
            key: freshness_tables(item, executed_at)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            freshness_record(freshness_tables(item, executed_at), executed_at)
            if isinstance(item, Mapping)
            else freshness_tables(item, executed_at)
            for item in value
        ]
    return value


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def callable_source_hash(function: Callable[..., Any]) -> str:
    try:
        source = inspect.getsource(function)
    except (OSError, TypeError):
        source = f"{function.__module__}.{function.__qualname__}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def invoke_signature(
    function: Callable[..., Any],
    context: Mapping[str, Any],
    *,
    label: str,
    required_keywords: Sequence[str] = (),
) -> Any:
    """Bind real repository signatures; never discard required controls."""
    signature = inspect.signature(function)
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    has_var_keywords = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if parameter.name in context:
            value = context[parameter.name]
        elif parameter.default is not inspect.Parameter.empty:
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                positional.append(parameter.default)
            continue
        else:
            raise TypeError(
                f"Unsupported required parameter {parameter.name!r} in "
                f"{label}{signature}. Available bindings: {sorted(context)}"
            )
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[parameter.name] = value

    for name in required_keywords:
        if name not in context:
            raise RuntimeError(f"Internal error: no binding for {name!r}.")
        if name not in signature.parameters:
            if not has_var_keywords:
                raise TypeError(f"{label}{signature} does not support {name!r}.")
            keywords[name] = context[name]
    signature.bind(*positional, **keywords)
    return function(*positional, **keywords)


class ReferenceMeshAdapter:
    """Reuse the repository's exact one-sector active mesh implementation."""

    def __init__(self) -> None:
        self.module = importlib.import_module("execution.run_fractal_advantage_study")
        self.track_type = getattr(self.module, "TrackSpec3D", None)
        self.design_type = getattr(self.module, "StudyDesign", None)
        if not callable(self.track_type) or not callable(self.design_type):
            raise ImportError(
                "run_fractal_advantage_study must expose TrackSpec3D and StudyDesign."
            )

        preferred = (
            "build_active_sector_mesh",
            "build_active_zone_sector_mesh",
            "build_active_zone_mesh",
            "build_sector_mesh",
            "build_surface_mesh",
            "build_mesh",
        )
        candidates: list[tuple[int, str, Callable[..., Any]]] = []
        for name, function in vars(self.module).items():
            if not inspect.isfunction(function) or function.__module__ != self.module.__name__:
                continue
            lower = name.lower()
            if "mesh" not in lower or not any(word in lower for word in ("build", "make")):
                continue
            if any(word in lower for word in ("monolithic", "full", "plot")):
                continue
            parameters = inspect.signature(function).parameters
            if not any(name in parameters for name in ("design", "study_design")):
                continue
            if not any(name in parameters for name in ("theta_deg", "theta", "angle_deg")):
                continue
            rank = preferred.index(name) if name in preferred else len(preferred)
            candidates.append((rank, name, function))
        if not candidates:
            raise ImportError("Cannot identify the reference active-sector mesh builder.")
        candidates.sort(key=lambda item: (item[0], item[1]))
        if (
            len(candidates) > 1
            and candidates[0][0] == candidates[1][0] == len(preferred)
        ):
            raise ImportError(
                "Ambiguous reference mesh builders: "
                + ", ".join(item[1] for item in candidates)
            )
        self.builder_name = candidates[0][1]
        self.builder = candidates[0][2]
        self._designs: dict[str, Any] = {}

    @staticmethod
    def design_context(design: StudyDesign, tracks: Sequence[Any]) -> dict[str, Any]:
        return {
            **dataclasses.asdict(design),
            "name": design.name,
            "label": design.name,
            "design_name": design.name,
            "category": f"gen_{design.generation}",
            "description": design.name,
            "tracks": tuple(tracks),
            "track_specs": list(tracks),
            "tracks_3d": list(tracks),
            "N": design.generation,
            "n": design.generation,
            "fractal_generation": design.generation,
            "r_min": design.R_min,
            "r_max": design.R_max,
            "aperture_deg": design.aperture_arc_deg,
            "tooth_deg": design.tooth_arc_deg,
            "z_tip": design.tracks[0].z_tip,
            "h_teeth": design.tracks[0].h_teeth,
            "z_top": design.tracks[0].z_top,
            "n_tracks": len(tracks),
            "M": len(tracks),
        }

    def reference_design(self, design: StudyDesign) -> Any:
        key = json.dumps(dataclasses.asdict(design), sort_keys=True)
        if key in self._designs:
            return self._designs[key]
        reference_tracks = [
            invoke_signature(
                self.track_type,
                {
                    **dataclasses.asdict(track),
                    "r_in": track.r_inner,
                    "r_out": track.r_outer,
                    "tooth_r_inner": track.r_tooth_in,
                    "tooth_r_outer": track.r_tooth_out,
                    "z_top": track.z_top,
                },
                label="reference TrackSpec3D",
            )
            for track in design.tracks
        ]
        context = self.design_context(design, reference_tracks)
        signature = inspect.signature(self.design_type)
        element_names = {"elements", "track_elements", "clutch_elements"}
        needed = element_names.intersection(signature.parameters)
        if needed:
            scoped_context = {
                **context,
                "scope": "active",
                "scope_name": "active",
                "configuration": design.name,
                "configuration_name": design.name,
            }
            scoped = invoke_signature(
                get_scoped_clutch_elements,
                scoped_context,
                label="get_scoped_clutch_elements",
            )
            if isinstance(scoped, Geometry):
                elements = getattr(scoped, "elements", _MISSING)
                if elements is _MISSING:
                    raise TypeError("Scoped Geometry does not expose elements.")
            elif isinstance(scoped, Mapping):
                elements = scoped.get("elements", scoped.get("track_elements", _MISSING))
                if elements is _MISSING:
                    raise TypeError("Scoped element mapping has no elements.")
            else:
                elements = scoped
            if not isinstance(elements, Sequence) or not elements:
                raise TypeError("Scoped clutch elements must be a nonempty sequence.")
            if not all(isinstance(item, TrackElement) for item in elements):
                raise TypeError("Scoped clutch elements are not TrackElement objects.")
            context.update({name: elements for name in element_names})
        result = invoke_signature(
            self.design_type, context, label="reference StudyDesign"
        )
        self._designs[key] = result
        return result

    def build(
        self,
        design: StudyDesign,
        theta_deg: float,
        n_r: int,
        n_phi_tooth: int,
        n_phi_bridge: int,
        n_z: int,
    ) -> ClutchSurfaceMesh:
        reference = self.reference_design(design)
        context = {
            "design": reference,
            "study_design": reference,
            "theta_deg": theta_deg,
            "angle_deg": theta_deg,
            "theta": math.radians(theta_deg),
            "n_r": n_r,
            "n_phi_tooth": n_phi_tooth,
            "n_phi_bridge": n_phi_bridge,
            "n_z": n_z,
        }
        result = invoke_signature(self.builder, context, label=self.builder_name)
        if not isinstance(result, ClutchSurfaceMesh):
            raise TypeError(
                f"{self.builder_name} returned {type(result).__name__}, "
                "not ClutchSurfaceMesh."
            )
        return result

    @property
    def provenance(self) -> dict[str, Any]:
        return {
            "module": self.module.__name__,
            "builder": self.builder_name,
            "builder_sha256": callable_source_hash(self.builder),
            "scoped_elements_sha256": callable_source_hash(get_scoped_clutch_elements),
            "sector_angle_rad": SECTOR_ANGLE,
            "cyclic_symmetry_applied_by": SOLVER_NAME,
        }


_ADAPTER: ReferenceMeshAdapter | None = None


def mesh_adapter() -> ReferenceMeshAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = ReferenceMeshAdapter()
    return _ADAPTER


def build_active_sector_mesh(
    design: StudyDesign,
    theta_deg: float,
    n_r: int,
    n_phi_tooth: int,
    n_phi_bridge: int,
    n_z: int,
) -> ClutchSurfaceMesh:
    return mesh_adapter().build(
        design, theta_deg, n_r, n_phi_tooth, n_phi_bridge, n_z
    )


def subdivisions(start: float, stop: float, count: int) -> list[float]:
    if count < 1 or not math.isfinite(start) or not math.isfinite(stop) or stop <= start:
        raise ValueError("Invalid subdivision interval or count.")
    return [start + (stop - start) * index / count for index in range(count + 1)]


def tooth_intervals(theta_deg: float, arc_deg: float) -> list[tuple[float, float]]:
    center = math.radians((15.0 + theta_deg % 90.0) % 90.0)
    half_width = math.radians(arc_deg) / 2.0
    intervals: list[tuple[float, float]] = []
    for offset in (-SECTOR_ANGLE, 0.0, SECTOR_ANGLE):
        low = max(0.0, center + offset - half_width)
        high = min(SECTOR_ANGLE, center + offset + half_width)
        if high - low > 1e-14:
            intervals.append((low, high))
    return sorted(intervals)


def sector_solid_panels(
    r0: float,
    r1: float,
    p0: float,
    p1: float,
    z0: float,
    z1: float,
    body: Body,
    n_r: int,
    n_phi: int,
    n_z: int,
    *,
    cyclic_cut: bool,
) -> list[Any]:
    """Outward-oriented boundary of an annular prism, in radians.

    Artificial azimuthal faces at the cyclic sector cuts are omitted when the
    solid continues across those cuts. No internal subdivision faces are added.
    """
    radii = subdivisions(r0, r1, n_r)
    angles = subdivisions(p0, p1, n_phi)
    heights = subdivisions(z0, z1, n_z)
    panels: list[Any] = []
    bottom_kind = f"{body}_bottom"
    top_kind = f"{body}_top"
    radial_kind = f"{body}_radial_wall"
    azimuthal_kind = f"{body}_azimuthal_wall"

    for ra, rb in zip(radii[:-1], radii[1:], strict=True):
        for pa, pb in zip(angles[:-1], angles[1:], strict=True):
            panels.append(_horizontal(ra, rb, pa, pb, z0, -1.0, bottom_kind, body))
            panels.append(_horizontal(ra, rb, pa, pb, z1, +1.0, top_kind, body))
    for pa, pb in zip(angles[:-1], angles[1:], strict=True):
        for za, zb in zip(heights[:-1], heights[1:], strict=True):
            panels.append(_radial(r0, pa, pb, za, zb, -1.0, radial_kind, body))
            panels.append(_radial(r1, pa, pb, za, zb, +1.0, radial_kind, body))
    for phi, sign in ((p0, -1.0), (p1, +1.0)):
        is_cut = math.isclose(phi, 0.0, abs_tol=1e-13) or math.isclose(
            phi, SECTOR_ANGLE, abs_tol=1e-13
        )
        if cyclic_cut and is_cut:
            continue
        for ra, rb in zip(radii[:-1], radii[1:], strict=True):
            for za, zb in zip(heights[:-1], heights[1:], strict=True):
                panels.append(
                    _azimuthal(ra, rb, phi, za, zb, sign, azimuthal_kind, body)
                )
    return panels


def mesh_fields(mesh: ClutchSurfaceMesh) -> dict[str, Any]:
    if dataclasses.is_dataclass(mesh):
        return {item.name: getattr(mesh, item.name) for item in dataclasses.fields(mesh)}
    names: set[str] = set(vars(mesh)) if hasattr(mesh, "__dict__") else set()
    for cls in type(mesh).__mro__:
        slots = getattr(cls, "__slots__", ())
        names.update((slots,) if isinstance(slots, str) else slots)
    return {
        name: getattr(mesh, name)
        for name in names
        if name not in {"__dict__", "__weakref__"} and hasattr(mesh, name)
    }


def panel_body(panel: Any) -> str | None:
    body = getattr(panel, "body", None)
    if body in ("rotor", "stator"):
        return cast(str, body)
    kind = getattr(panel, "kind", getattr(panel, "panel_type", ""))
    if isinstance(kind, str):
        for candidate in ("rotor", "stator"):
            if kind.startswith(f"{candidate}_"):
                return candidate
    return None


def append_mesh_panels(
    mesh: ClutchSurfaceMesh, rotor: Sequence[Any], stator: Sequence[Any]
) -> ClutchSurfaceMesh:
    """Preserve the repository mesh type and all non-panel metadata."""
    fields = mesh_fields(mesh)
    updates: dict[str, Any] = {}
    assigned: set[str] = set()
    for name, existing in fields.items():
        if not isinstance(existing, (list, tuple)) or not existing:
            continue
        bodies = {panel_body(panel) for panel in existing}
        if None in bodies:
            continue
        lower = name.lower()
        if bodies == {"rotor", "stator"}:
            if assigned:
                raise TypeError("Ambiguous redundant panel containers in mesh.")
            additions = list(rotor) + list(stator)
            assigned.update(("rotor", "stator"))
        elif bodies == {"rotor"} and (
            "rotor" in lower or lower in {"panels", "surface_panels"}
        ):
            additions = list(rotor)
            assigned.add("rotor")
        elif bodies == {"stator"} and (
            "stator" in lower or lower in {"panels", "surface_panels"}
        ):
            additions = list(stator)
            assigned.add("stator")
        else:
            continue
        combined = list(existing) + additions
        updates[name] = tuple(combined) if isinstance(existing, tuple) else combined

    if assigned != {"rotor", "stator"}:
        raise TypeError(
            "Cannot safely identify both panel containers in ClutchSurfaceMesh; "
            f"fields are {sorted(fields)}."
        )
    if dataclasses.is_dataclass(mesh):
        result = dataclasses.replace(mesh, **updates)
    else:
        result = copy.copy(mesh)
        for name, value in updates.items():
            setattr(result, name, value)
    if not isinstance(result, ClutchSurfaceMesh):
        raise TypeError("Mesh replacement changed its type.")
    return result


def build_monolithic_sector_mesh(
    design: StudyDesign,
    theta_deg: float,
    n_r: int,
    n_phi_tooth: int,
    n_phi_bridge: int,
    n_z: int,
) -> ClutchSurfaceMesh:
    """Active sector plus the specified passive monolithic support boundary."""
    active = build_active_sector_mesh(
        design, theta_deg, n_r, n_phi_tooth, n_phi_bridge, n_z
    )
    intervals = tooth_intervals(theta_deg, design.tooth_arc_deg)
    rotor: list[Any] = []

    # Spokes and collars share radial boundaries. Their interface faces are
    # removed below so that only the boundary of the support union survives.
    for p0, p1 in intervals:
        rotor.extend(
            sector_solid_panels(
                design.R_min, design.R_max, p0, p1, 0.350, 0.470,
                "rotor", n_r, n_phi_tooth, n_z, cyclic_cut=True,
            )
        )

    inner = max(0.08, design.R_min - 0.12)
    outer = design.R_max + 0.12
    cuts = sorted({0.0, SECTOR_ANGLE, *(v for interval in intervals for v in interval)})
    for p0, p1 in zip(cuts[:-1], cuts[1:], strict=True):
        if p1 - p0 <= 1e-14:
            continue
        covered = any(a <= (p0 + p1) / 2.0 <= b for a, b in intervals)
        for r0, r1, shared_radius, shared_sign in (
            (inner, design.R_min, design.R_min, +1.0),
            (design.R_max, outer, design.R_max, -1.0),
        ):
            radii = subdivisions(r0, r1, n_r)
            angles = subdivisions(p0, p1, n_phi_tooth)
            heights = subdivisions(0.350, 0.470, n_z)
            for ra, rb in zip(radii[:-1], radii[1:], strict=True):
                for pa, pb in zip(angles[:-1], angles[1:], strict=True):
                    rotor.append(_horizontal(
                        ra, rb, pa, pb, 0.350, -1.0, "rotor_bottom", "rotor"
                    ))
                    rotor.append(_horizontal(
                        ra, rb, pa, pb, 0.470, +1.0, "rotor_top", "rotor"
                    ))
            for radius, sign in ((r0, -1.0), (r1, +1.0)):
                if covered and radius == shared_radius and sign == shared_sign:
                    continue
                for pa, pb in zip(angles[:-1], angles[1:], strict=True):
                    for za, zb in zip(heights[:-1], heights[1:], strict=True):
                        rotor.append(_radial(
                            radius, pa, pb, za, zb, sign,
                            "rotor_radial_wall", "rotor"
                        ))

    # Regenerate spokes without their collar-contact radial faces.
    spoke_horizontal_and_azimuthal: list[Any] = []
    for p0, p1 in intervals:
        radii = subdivisions(design.R_min, design.R_max, n_r)
        angles = subdivisions(p0, p1, n_phi_tooth)
        heights = subdivisions(0.350, 0.470, n_z)
        for ra, rb in zip(radii[:-1], radii[1:], strict=True):
            for pa, pb in zip(angles[:-1], angles[1:], strict=True):
                spoke_horizontal_and_azimuthal.append(_horizontal(
                    ra, rb, pa, pb, 0.350, -1.0, "rotor_bottom", "rotor"
                ))
                spoke_horizontal_and_azimuthal.append(_horizontal(
                    ra, rb, pa, pb, 0.470, +1.0, "rotor_top", "rotor"
                ))
        for phi, sign in ((p0, -1.0), (p1, +1.0)):
            if math.isclose(phi, 0.0, abs_tol=1e-13) or math.isclose(
                phi, SECTOR_ANGLE, abs_tol=1e-13
            ):
                continue
            for ra, rb in zip(radii[:-1], radii[1:], strict=True):
                for za, zb in zip(heights[:-1], heights[1:], strict=True):
                    spoke_horizontal_and_azimuthal.append(_azimuthal(
                        ra, rb, phi, za, zb, sign,
                        "rotor_azimuthal_wall", "rotor"
                    ))
    original_spoke_count = sum(
        len(sector_solid_panels(
            design.R_min, design.R_max, p0, p1, 0.350, 0.470,
            "rotor", n_r, n_phi_tooth, n_z, cyclic_cut=True,
        ))
        for p0, p1 in intervals
    )
    rotor = spoke_horizontal_and_azimuthal + rotor[original_spoke_count:]

    stator = sector_solid_panels(
        design.R_min, design.R_max, 0.0, SECTOR_ANGLE, -0.650, -0.550,
        "stator", n_r, n_phi_bridge, n_z, cyclic_cut=True,
    )
    return append_mesh_panels(active, rotor, stator)


def cantor_tracks(
    r_min: float,
    r_max: float,
    generation: int,
    ratio: float,
    minimum_width: float,
) -> tuple[TrackSpec3D, ...]:
    if generation < 1 or not 0.0 < ratio < 1.0:
        raise ValueError("Invalid Cantor generation or tooth ratio.")
    retained = [(r_min, r_max)]
    removed: list[tuple[float, float, int]] = []
    for level in range(1, generation + 1):
        next_retained: list[tuple[float, float]] = []
        for low, high in retained:
            third = (high - low) / 3.0
            removed.append((low + third, high - third, level))
            next_retained.extend(((low, low + third), (high - third, high)))
        retained = next_retained
    tracks: list[TrackSpec3D] = []
    for low, high, level in sorted(removed):
        width = (high - low) * ratio
        if width < minimum_width - 1e-12:
            raise ValueError(
                f"Requested minimum tooth width {minimum_width} exceeds "
                f"the Cantor tooth width {width}; clipping would break matching."
            )
        center = (low + high) / 2.0
        tracks.append(TrackSpec3D(
            low, high, center - width / 2.0, center + width / 2.0,
            -0.100, 0.100, level,
        ))
    return tuple(tracks)


def build_designs() -> dict[str, StudyDesign]:
    single_track = TrackSpec3D(
        0.4166667, 0.5333333, 0.4370833, 0.5129167,
        -0.100, 0.100, 2,
    )
    n0 = StudyDesign(
        "Fractal_N0_SingleTrack", (single_track,), 0.30, 0.65,
        generation=0, min_tooth_w=0.0,
    )
    n1 = StudyDesign(
        "Fractal_N1_FundRing",
        cantor_tracks(0.30, 1.35, 1, 0.82, 0.020),
        0.30, 1.35, generation=1, w1_ratio=0.82,
    )
    n2 = StudyDesign(
        "Fractal_N2_Cantor3Track",
        cantor_tracks(0.30, 1.35, 2, 0.65, 0.020),
        0.30, 1.35,
    )
    n3 = StudyDesign(
        "Fractal_N3_Cantor7Track",
        cantor_tracks(0.30, 1.65, 3, 0.40, 0.015),
        0.30, 1.65, generation=3, w1_ratio=0.40,
        min_tooth_w=0.015, tooth_arc_deg=12.0,
    )
    flat = dataclasses.replace(n2, name="Cantor_N2_FlatZ")
    hybrid = dataclasses.replace(
        flat,
        name="Cantor_N2_HybridRZ",
        tracks=tuple(
            dataclasses.replace(track, z_tip=-0.090, h_teeth=0.090)
            if track.level == 2
            else dataclasses.replace(track, z_tip=-0.100, h_teeth=0.100)
            for track in flat.tracks
        ),
    )
    compact = StudyDesign(
        "Rot_C8_Compact_N2",
        cantor_tracks(0.30, 0.65, 2, 0.65, 0.015),
        0.30, 0.65, min_tooth_w=0.015,
    )

    total_slot = sum(track.r_outer - track.r_inner for track in flat.tracks)
    total_tooth = sum(track.r_tooth_out - track.r_tooth_in for track in flat.tracks)
    center = (flat.R_min + flat.R_max) / 2.0
    wide_track = TrackSpec3D(
        center - total_slot / 2.0, center + total_slot / 2.0,
        center - total_tooth / 2.0, center + total_tooth / 2.0,
        -0.100, 0.100, 1,
    )
    single = dataclasses.replace(flat, name="Ctrl_SingleWide", tracks=(wide_track,))

    slot_width = total_slot / 3.0
    tooth_width = total_tooth / 3.0
    rib_w = ((flat.R_max - flat.R_min) - total_slot) / 4.0
    periodic_tracks = tuple(
        TrackSpec3D(
            cursor, cursor + slot_width,
            cursor + (slot_width - tooth_width) / 2.0,
            cursor + (slot_width + tooth_width) / 2.0,
            -0.100, 0.100, 1,
        )
        for cursor in (
            flat.R_min + rib_w + index * (slot_width + rib_w)
            for index in range(3)
        )
    )
    periodic = dataclasses.replace(
        flat, name="Ctrl_UniformPeriodic", tracks=periodic_tracks
    )
    # Retain the existing control name and expose the requested baseline name.
    uniform = dataclasses.replace(periodic, name="Uniform_3Track_Control")
    sorted_original = sorted(flat.tracks, key=lambda track: track.r_inner)
    ribs = [sorted_original[0].r_inner - flat.R_min]
    ribs.extend(
        right.r_inner - left.r_outer
        for left, right in zip(sorted_original[:-1], sorted_original[1:], strict=True)
    )
    ribs.append(flat.R_max - sorted_original[-1].r_outer)
    ordered = sorted(
        sorted_original,
        key=lambda track: (
            track.r_tooth_out - track.r_tooth_in,
            track.r_outer - track.r_inner,
        ),
    )
    cursor = flat.R_min + ribs[0]
    monotonic_tracks: list[TrackSpec3D] = []
    for index, track in enumerate(ordered):
        slot = track.r_outer - track.r_inner
        tooth = track.r_tooth_out - track.r_tooth_in
        middle = cursor + slot / 2.0
        monotonic_tracks.append(TrackSpec3D(
            cursor, cursor + slot, middle - tooth / 2.0, middle + tooth / 2.0,
            -0.100, 0.100, track.level,
        ))
        cursor += slot + ribs[index + 1]
    monotonic = dataclasses.replace(
        flat, name="Ctrl_SizeMatched_Monotonic", tracks=tuple(monotonic_tracks)
    )
    designs = (
        n0, n1, n2, n3, flat, hybrid, compact, single, periodic, uniform, monotonic
    )
    return {design.name: design for design in designs}


def tooth_geometry_metrics(design: StudyDesign) -> dict[str, Any]:
    angle = math.radians(design.tooth_arc_deg)
    slot_widths = [track.r_outer - track.r_inner for track in design.tracks]
    tooth_widths = [
        track.r_tooth_out - track.r_tooth_in for track in design.tracks
    ]
    area_sector = sum(
        0.5 * angle * (track.r_tooth_out**2 - track.r_tooth_in**2)
        for track in design.tracks
    )
    perimeter_sector = sum(
        2.0 * (track.r_tooth_out - track.r_tooth_in)
        + angle * (track.r_tooth_in + track.r_tooth_out)
        for track in design.tracks
    )
    slot_area_sector = sum(
        0.5 * math.radians(design.aperture_arc_deg)
        * (track.r_outer**2 - track.r_inner**2)
        for track in design.tracks
    )
    ordered = sorted(design.tracks, key=lambda track: track.r_inner)
    ribs = [ordered[0].r_inner - design.R_min]
    ribs.extend(
        right.r_inner - left.r_outer
        for left, right in zip(ordered[:-1], ordered[1:], strict=True)
    )
    ribs.append(design.R_max - ordered[-1].r_outer)
    return {
        "track_count": len(design.tracks),
        "total_slot_width_um": sum(slot_widths),
        "total_tooth_width_um": sum(tooth_widths),
        "slot_widths_um": slot_widths,
        "tooth_widths_um": tooth_widths,
        "rib_widths_um": ribs,
        "full_tooth_planform_area_um2": 4.0 * area_sector,
        "full_tooth_planform_perimeter_um": 4.0 * perimeter_sector,
        "full_slot_planform_area_um2": 4.0 * slot_area_sector,
        "full_annular_footprint_um2": design.footprint_um2,
    }


def validate_controls(designs: Mapping[str, StudyDesign]) -> dict[str, Any]:
    names = (
        "Cantor_N2_FlatZ",
        "Cantor_N2_HybridRZ",
        "Ctrl_SingleWide",
        "Ctrl_UniformPeriodic",
        "Uniform_3Track_Control",
        "Ctrl_SizeMatched_Monotonic",
    )
    metrics = {name: tooth_geometry_metrics(designs[name]) for name in names}
    reference = metrics[names[0]]
    for name in names[1:]:
        for key in ("total_slot_width_um", "total_tooth_width_um"):
            if not math.isclose(metrics[name][key], reference[key], abs_tol=1e-10):
                raise ValueError(f"{name} does not match {key}.")
    for name in ("Ctrl_UniformPeriodic", "Uniform_3Track_Control"):
        for key in (
            "full_tooth_planform_area_um2",
            "full_tooth_planform_perimeter_um",
            "full_slot_planform_area_um2",
        ):
            if not math.isclose(
                metrics[name][key], reference[key],
                rel_tol=1e-10, abs_tol=1e-12,
            ):
                raise ValueError(f"{name} does not match {key}.")
    for key in ("slot_widths_um", "tooth_widths_um", "rib_widths_um"):
        left = sorted(reference[key])
        right = sorted(metrics["Ctrl_SizeMatched_Monotonic"][key])
        if len(left) != len(right) or any(
            not math.isclose(a, b, abs_tol=1e-10)
            for a, b in zip(left, right, strict=True)
        ):
            raise ValueError(f"Monotonic control does not match the {key} multiset.")
    return metrics


def landing_overlap(design: StudyDesign, theta_deg: float) -> float:
    """Analytic projected tooth-area fraction over pads in the active slots."""
    pad_low = math.radians(design.aperture_arc_deg)
    pad_high = SECTOR_ANGLE
    overlap_angle = sum(
        max(0.0, min(high, pad_high) - max(low, pad_low))
        for low, high in tooth_intervals(theta_deg, design.tooth_arc_deg)
    )
    fraction = overlap_angle / math.radians(design.tooth_arc_deg)
    return min(1.0, max(0.0, fraction))


def extract_scalar(
    result: Mapping[str, Any], names: Sequence[str], *, required: bool
) -> float | None:
    for name in names:
        if name in result and result[name] is not None:
            return finite_float(result[name], f"solver result {name}")
    if required:
        raise KeyError(f"Solver result is missing all of {tuple(names)}.")
    return None


def resume_lookup_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    resolution = row.get("resolution", {})
    tier = row.get("tier")
    if tier is None and isinstance(resolution, Mapping):
        tier = resolution.get("tier", resolution.get("name"))
    if not isinstance(tier, str):
        raise TypeError("Cached row has no resolution tier.")
    return (
        row["step"], row["design"],
        finite_float(row["theta_deg"], "cached angle"),
        row["formulation"], row["boundary"], tier, row.get("purpose", ""),
    )


@dataclass
class Campaign:
    max_steps: int
    formulation: Formulation
    device: str
    convergence_tolerance: float
    agreement_tolerance: float
    rows: list[dict[str, Any]] = field(default_factory=list)
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    started: float = field(default_factory=time.perf_counter)
    resume_cache: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    resumed_cache_keys: set[str] = field(default_factory=set)
    solver_evaluations: int = 0

    def load_resume(self, path: Path) -> int:
        """Load valid full-run measurements, including rows from partial reports."""
        if self.max_steps != 0 or not path.is_file():
            return 0
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(previous, Mapping):
                return 0
            configuration = previous.get("configuration", {})
            if not isinstance(configuration, Mapping) or (
                configuration.get("solver_sha256")
                != callable_source_hash(run_bem_casimir_solver)
                or configuration.get("formulation") != self.formulation
                or configuration.get("max_steps") != 0
            ):
                return 0
            saved_rows = previous.get("tasks", [])
            if not isinstance(saved_rows, list):
                return 0
        except (OSError, ValueError, TypeError):
            return 0

        loaded = 0
        for saved in saved_rows:
            if not isinstance(saved, Mapping):
                continue
            source_status = saved.get("source_status", saved.get("status"))
            if source_status not in ("ok", "complete", "completed"):
                continue
            try:
                key = resume_lookup_key(saved)
                cache_key = saved["cache_key"]
                if not isinstance(cache_key, str) or not cache_key:
                    continue
                parameters = saved.get("solver_parameters", {})
                if (
                    not isinstance(parameters, Mapping)
                    or parameters.get("max_steps") != 0
                    or not isinstance(saved.get("solver_result"), Mapping)
                    or not isinstance(saved.get("task_id"), str)
                ):
                    continue
                force = finite_float(saved["F_z_pN"], "cached force")
                result_force = extract_scalar(
                    saved["solver_result"],
                    ("f_net_pN", "F_z_pN", "force_z_pN", "Fz_pN"),
                    required=True,
                )
                if result_force != force:
                    continue
                energy = saved.get("energy_hbar_c_per_um")
                if energy is not None:
                    finite_float(energy, "cached energy")
                elapsed = finite_float(saved["solver_elapsed_s"], "cached elapsed time")
                if elapsed < 0.0:
                    continue
                # Verify the content hash, not just the coarse narrative key.
                # Strip table-generation metadata from serialized track records.
                saved_design = copy.deepcopy(parameters["design"])
                if isinstance(saved_design, Mapping):
                    saved_design = dict(saved_design)
                    tracks = saved_design.get("tracks")
                    if isinstance(tracks, list):
                        track_fields = {item.name for item in dataclasses.fields(TrackSpec3D)}
                        saved_design["tracks"] = [
                            {name: value for name, value in track.items() if name in track_fields}
                            if isinstance(track, Mapping) else track
                            for track in tracks
                        ]
                content = {
                    "design": saved_design,
                    "theta_deg": saved["theta_deg"],
                    "formulation": saved["formulation"],
                    "resolution": saved["resolution"],
                    "boundary": saved["boundary"],
                }
                computed_key = hashlib.sha256(
                    json.dumps(content, sort_keys=True, allow_nan=False).encode("utf-8")
                ).hexdigest()
                if computed_key != cache_key:
                    continue
                row = copy.deepcopy(dict(saved))
                row["force_sign"] = (
                    "repulsive" if force > 0.0
                    else "attractive" if force < 0.0 else "zero"
                )
                self.resume_cache[key] = row
                self.cache[cache_key] = row
                self.resumed_cache_keys.add(cache_key)
                loaded += 1
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        return loaded

    def run(self, task: Task) -> dict[str, Any]:
        sequence = len(self.rows) + 1
        task_id = f"{task.step}_{sequence:04d}"
        parameters = {
            "task_id": task_id,
            "design": dataclasses.asdict(task.design),
            "theta_deg": task.theta_deg,
            "formulation": task.formulation,
            "boundary": task.boundary,
            **dataclasses.asdict(task.resolution),
            "device": self.device,
            "max_steps": self.max_steps,
            "record_metrics": False,
            "sector_angle_rad": SECTOR_ANGLE,
            "force_symmetry_multiplier": "applied internally by solver only",
            "mesh_builder": mesh_adapter().provenance,
        }
        geometry_metrics = tooth_geometry_metrics(task.design)
        base = {
            "task_id": task_id,
            "step": task.step,
            "design": task.design.name,
            "theta_deg": task.theta_deg,
            "z_tip_um": task.design.tracks[0].z_tip,
            "max_z_top_um": max(track.z_top for track in task.design.tracks),
            "formulation": task.formulation,
            "boundary": task.boundary,
            "tier": task.resolution.name,
            "resolution": dataclasses.asdict(task.resolution),
            "purpose": task.purpose,
            "landing_pad_overlap_fraction": landing_overlap(task.design, task.theta_deg),
            "footprint_um2": task.design.footprint_um2,
            "track_count": len(task.design.tracks),
            "full_tooth_count": 4 * len(task.design.tracks),
            "full_tooth_planform_area_um2": geometry_metrics["full_tooth_planform_area_um2"],
            "cache_key": task.cache_key,
            "solver_parameters": parameters,
        }
        original = self.resume_cache.get(resume_lookup_key(base))
        if original is None or original.get("cache_key") != task.cache_key:
            original = self.cache.get(task.cache_key)
        if original is not None:
            row = {
                **base,
                **{
                    key: copy.deepcopy(original[key])
                    for key in (
                        "F_z_pN", "energy_hbar_c_per_um", "force_sign",
                        "solver_result", "solver_elapsed_s",
                    )
                },
                "reused_from_task_id": original["task_id"],
                "resumed_from_report": task.cache_key in self.resumed_cache_keys,
                "status": "ok",
            }
        else:
            start = time.perf_counter()
            builder = (
                build_monolithic_sector_mesh
                if task.boundary == "Full-Monolithic"
                else build_active_sector_mesh
            )
            mesh = builder(
                task.design, task.theta_deg, task.resolution.n_r,
                task.resolution.n_phi_tooth, task.resolution.n_phi_bridge,
                task.resolution.n_z,
            )
            signature = inspect.signature(run_bem_casimir_solver)
            mesh_aliases = ("mesh", "surface_mesh", "clutch_mesh", "clutch_surface_mesh")
            separate_mesh = next(
                (name for name in mesh_aliases if name in signature.parameters), None
            )
            context: dict[str, Any] = {
                **{name: mesh for name in mesh_aliases},
                "parameters": mesh.parameters,
                "task_id": task_id,
                "theta_deg": task.theta_deg,
                "angle_deg": task.theta_deg,
                "theta": math.radians(task.theta_deg),
                "formulation": task.formulation,
                "n_xi": task.resolution.n_xi,
                "n_r": task.resolution.n_r,
                "n_phi_tooth": task.resolution.n_phi_tooth,
                "n_phi_bridge": task.resolution.n_phi_bridge,
                "n_z": task.resolution.n_z,
                "device": self.device,
                "record_metrics": False,
            }
            if separate_mesh is None:
                geometry_parameter = signature.parameters.get("geometry")
                if geometry_parameter is None:
                    raise TypeError(
                        "Solver exposes neither a custom mesh parameter nor geometry."
                    )
                context["geometry"] = mesh
            elif "geometry" in signature.parameters:
                parameter = signature.parameters["geometry"]
                if parameter.default is inspect.Parameter.empty:
                    geometry = getattr(mesh, "geometry", None)
                    if not isinstance(geometry, Geometry):
                        raise TypeError(
                            "Solver requires Geometry in addition to a mesh, "
                            "but the reference mesh does not expose one."
                        )
                    context["geometry"] = geometry

            required = ["record_metrics", "formulation", "n_xi"]
            if self.max_steps > 0:
                context["max_steps"] = self.max_steps
                required.append("max_steps")
            result = invoke_signature(
                run_bem_casimir_solver, context,
                label=SOLVER_NAME, required_keywords=required,
            )
            self.solver_evaluations += 1
            if not isinstance(result, Mapping):
                raise TypeError("BEM solver must return a result mapping.")
            force = extract_scalar(
                result, ("f_net_pN", "F_z_pN", "force_z_pN", "Fz_pN"), required=True
            )
            energy = extract_scalar(
                result, ("energy_hbar_c_per_um",), required=False
            )
            assert force is not None
            row = {
                **base,
                "status": "ok",
                "F_z_pN": force,
                "energy_hbar_c_per_um": energy,
                "force_sign": (
                    "repulsive" if force > 0.0
                    else "attractive" if force < 0.0 else "zero"
                ),
                "solver_result": json_safe(result),
                "solver_elapsed_s": time.perf_counter() - start,
                "reused_from_task_id": None,
                "resumed_from_report": False,
            }
            self.cache[task.cache_key] = row

        for denominator, label in (
            (row["full_tooth_count"], "full tooth count"),
            (row["footprint_um2"], "footprint"),
            (row["full_tooth_planform_area_um2"], "tooth planform area"),
        ):
            if finite_float(denominator, label) <= 0.0:
                raise ValueError(f"Nonpositive {label} normalization denominator.")
        row["F_z_pN_per_tooth"] = finite_float(
            row["F_z_pN"] / row["full_tooth_count"], "per-tooth force"
        )
        row["F_z_pN_per_um2"] = finite_float(
            row["F_z_pN"] / row["footprint_um2"], "footprint-normalized force"
        )
        row["F_z_pN_per_tooth_area_um2"] = finite_float(
            row["F_z_pN"] / row["full_tooth_planform_area_um2"],
            "tooth-area-normalized force",
        )
        self.rows.append(row)
        logged_id = log_step(
            task_id, json_safe(row),
            solver_name=SOLVER_NAME, solver_parameters=parameters,
        )
        step_id = logged_id if isinstance(logged_id, str) else task_id
        for key in (
            "F_z_pN", "energy_hbar_c_per_um", "landing_pad_overlap_fraction",
        ):
            if row[key] is not None:
                log_metric(
                    f"{task_id}_{key}", row[key], step_id=step_id,
                    solver_name=SOLVER_NAME, solver_parameters=parameters,
                )
        print(
            f"[{sequence:03d}] {task.step}: {task.design.name}, "
            f"theta={task.theta_deg:g}, {task.boundary}, "
            f"{task.resolution.name}, {task.formulation}: "
            f"Fz={row['F_z_pN']:.8g} pN"
            + (" (cached)" if original is not None else ""),
            flush=True,
        )
        return row


def tasks_steps_1_to_5(
    designs: Mapping[str, StudyDesign], formulation: Formulation
) -> list[Task]:
    tasks: list[Task] = []
    single = designs["Fractal_N0_SingleTrack"]
    for z_tip in (-0.110, -0.105, -0.100, -0.090, -0.075, -0.055):
        design = dataclasses.replace(
            single, name="SingleTooth_Track0",
            tracks=(dataclasses.replace(single.tracks[0], z_tip=z_tip),),
        )
        for angle in (3.0, 48.0):
            tasks.append(Task(STEP_NAMES[0], design, angle, formulation))
    for angle in (0.0, 3.0, 6.0, 12.0, 18.0, 24.0, 30.0, 39.0, 48.0):
        tasks.append(Task(STEP_NAMES[1], single, angle, formulation))
    for name in (
        "Fractal_N0_SingleTrack", "Fractal_N1_FundRing",
        "Fractal_N2_Cantor3Track", "Fractal_N3_Cantor7Track",
    ):
        for angle in (3.0, 21.0, 48.0):
            tasks.append(Task(STEP_NAMES[2], designs[name], angle, formulation))
    for name in (
        "Cantor_N2_FlatZ", "Cantor_N2_HybridRZ", "Ctrl_SingleWide",
        "Ctrl_UniformPeriodic", "Ctrl_SizeMatched_Monotonic",
        "Uniform_3Track_Control",
    ):
        for angle in (3.0, 48.0):
            tasks.append(Task(STEP_NAMES[3], designs[name], angle, formulation))
    step5_names = (
        "Rot_C8_Compact_N2", "Cantor_N2_FlatZ",
        "Cantor_N2_HybridRZ", "Fractal_N3_Cantor7Track",
        "Ctrl_SingleWide", "Ctrl_UniformPeriodic",
        "Ctrl_SizeMatched_Monotonic", "Uniform_3Track_Control",
    )
    for name in step5_names:
        for angle in (3.0, 48.0):
            tasks.append(Task(STEP_NAMES[4], designs[name], angle, formulation))
    return tasks


def step5_scores(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[str, dict[float, Mapping[str, Any]]] = {}
    for row in rows:
        if row["step"] == STEP_NAMES[4] and row["status"] in ("ok", "completed"):
            candidates.setdefault(str(row["design"]), {})[float(row["theta_deg"])] = row
    scores: list[dict[str, Any]] = []
    for name, angles in candidates.items():
        if 3.0 not in angles or 48.0 not in angles:
            continue
        repulsive = finite_float(angles[3.0]["F_z_pN"], "repulsive force")
        attractive = finite_float(angles[48.0]["F_z_pN"], "attractive force")
        footprint = finite_float(angles[3.0]["footprint_um2"], "footprint")
        track_count = finite_float(angles[3.0]["track_count"], "track count")
        tooth_count = 4.0 * track_count
        parameters = angles[3.0].get("solver_parameters", {})
        tooth_area_value = angles[3.0].get("full_tooth_planform_area_um2")
        if tooth_area_value is None and isinstance(parameters, Mapping):
            design = parameters.get("design")
            if isinstance(design, Mapping):
                tooth_area_value = 4.0 * sum(
                    0.5 * math.radians(finite_float(design["tooth_arc_deg"], "tooth arc"))
                    * (
                        finite_float(track["r_tooth_out"], "outer tooth radius") ** 2
                        - finite_float(track["r_tooth_in"], "inner tooth radius") ** 2
                    )
                    for track in design["tracks"]
                )
        tooth_area = (
            finite_float(tooth_area_value, "tooth planform area")
            if tooth_area_value is not None else None
        )
        if footprint <= 0.0 or tooth_count <= 0.0:
            raise ValueError("Nonpositive force-efficiency denominator.")
        if tooth_area is not None and tooth_area <= 0.0:
            raise ValueError("Nonpositive tooth-area denominator.")
        swing = finite_float(repulsive - attractive, "force swing")
        score = {
            "design": name,
            "candidate_kind": (
                "control" if name.startswith("Ctrl_") or name == "Uniform_3Track_Control"
                else "fractal"
            ),
            "F_rep_pN": repulsive,
            "F_att_pN": attractive,
            "Delta_F_pN": swing,
            "F_rep_pN_per_um2": finite_float(repulsive / footprint, "repulsion density"),
            "F_att_pN_per_um2": finite_float(attractive / footprint, "attraction density"),
            "Delta_F_pN_per_um2": finite_float(swing / footprint, "swing density"),
            "F_rep_pN_per_tooth": finite_float(repulsive / tooth_count, "per-tooth repulsion"),
            "F_att_pN_per_tooth": finite_float(attractive / tooth_count, "per-tooth attraction"),
            "Delta_F_pN_per_tooth": finite_float(swing / tooth_count, "per-tooth swing"),
            "F_rep_pN_per_tooth_area_um2": (
                finite_float(repulsive / tooth_area, "tooth-area repulsion")
                if tooth_area is not None else None
            ),
            "F_att_pN_per_tooth_area_um2": (
                finite_float(attractive / tooth_area, "tooth-area attraction")
                if tooth_area is not None else None
            ),
            "Delta_F_pN_per_tooth_area_um2": (
                finite_float(swing / tooth_area, "tooth-area swing")
                if tooth_area is not None else None
            ),
            "footprint_um2": footprint,
            "track_count": track_count,
            "full_tooth_count": tooth_count,
            "full_tooth_planform_area_um2": tooth_area,
            "repulsive_state_verified": repulsive > 0.0,
            "attractive_state_verified": attractive < 0.0,
            "sampling_note": "Specified theta=3 and 48 deg states; not global extrema.",
        }
        scores.append(score)
    return scores


def step6_tasks(
    designs: Mapping[str, StudyDesign],
    selected: Formulation,
    active_champion: str,
) -> list[Task]:
    tasks: list[Task] = []
    for name in ("Cantor_N2_HybridRZ", "Fractal_N3_Cantor7Track"):
        for angle in (3.0, 48.0):
            for boundary in ("Active-Only", "Full-Monolithic"):
                tasks.append(Task(
                    STEP_NAMES[5], designs[name], angle, selected,
                    boundary=cast(Literal["Active-Only", "Full-Monolithic"], boundary),
                    purpose="active-only approximation validation",
                ))
    validation_design = designs["Cantor_N2_HybridRZ"]
    for resolution in (STANDARD, HIGH, ULTRA_HIGH):
        for angle in (3.0, 48.0):
            tasks.append(Task(
                STEP_NAMES[5], validation_design, angle, selected,
                resolution=resolution,
                purpose="resolution convergence and formulation cross-check",
            ))
    cross_check: Formulation = (
        "vector_dyadic" if selected == "scalar_yukawa" else "scalar_yukawa"
    )
    for angle in (3.0, 48.0):
        tasks.append(Task(
            STEP_NAMES[5], validation_design, angle, cross_check,
            resolution=STANDARD,
            purpose="resolution convergence and formulation cross-check",
        ))
    return tasks


def relative_difference(new: float, reference: float) -> float | None:
    if reference == 0.0:
        return 0.0 if new == 0.0 else None
    return abs(new - reference) / abs(reference)


def convergence_record(
    newer: Mapping[str, Any], older: Mapping[str, Any], tolerance: float
) -> dict[str, Any]:
    new_force = finite_float(newer["F_z_pN"], "new force")
    old_force = finite_float(older["F_z_pN"], "reference force")
    relative = relative_difference(new_force, old_force)
    return {
        "new_task_id": newer["task_id"],
        "reference_task_id": older["task_id"],
        "new_F_z_pN": new_force,
        "reference_F_z_pN": old_force,
        "absolute_difference_pN": abs(new_force - old_force),
        "relative_difference": relative,
        "relative_tolerance": tolerance,
        "within_tolerance": relative is not None and relative <= tolerance,
        "zero_reference": old_force == 0.0,
    }


def meep_value(
    document: Mapping[str, Any], names: Sequence[str], default: Any = _MISSING
) -> Any:
    """Accept flat reports and reports with nested result/config containers."""
    for name in names:
        if name in document and document[name] is not None:
            return document[name]
    for value in document.values():
        if isinstance(value, Mapping):
            found = meep_value(value, names, _MISSING)
            if found is not _MISSING:
                return found
    return default


def load_meep_verification() -> dict[str, Any]:
    """Read measured Meep data; invalid or absent files never become measurements."""
    tasks: list[dict[str, Any]] = []
    for task_id in range(1, 13):
        result_path = (
            REPOSITORY_ROOT / "results_nature_meep_verification"
            / f"task_{task_id}_meep.json"
        )
        config_path = (
            REPOSITORY_ROOT / "sweep_configs_nature_meep_verification"
            / f"config_{task_id:03d}.json"
        )
        row: dict[str, Any] = {
            "task_id": task_id,
            "status": "unavailable",
            "design": None,
            "theta_deg": None,
            "R": None,
            "dt": None,
            "cache_version": None,
            "F_2pass_pN": None,
            "F_stator_only_pN": None,
            "f_net_pN": None,
            "result_path": str(result_path.relative_to(REPOSITORY_ROOT)),
            "config_path": str(config_path.relative_to(REPOSITORY_ROOT)),
        }
        try:
            result_bytes = result_path.read_bytes()
            config_bytes = config_path.read_bytes()
            result = json.loads(result_bytes)
            config = json.loads(config_bytes)
            if not isinstance(result, Mapping) or not isinstance(config, Mapping):
                raise TypeError("Meep result and configuration must be JSON objects.")
            row["result_sha256"] = hashlib.sha256(result_bytes).hexdigest()
            row["config_sha256"] = hashlib.sha256(config_bytes).hexdigest()
            row["configuration"] = config
            row["solver_result"] = result
            if result.get("status") != "complete":
                raise ValueError("Meep task status is not complete.")

            versions = [
                meep_value(document, ("cache_version", "CACHE_VERSION"))
                for document in (result, config)
            ]
            for version in versions:
                if version is not _MISSING and (
                    isinstance(version, bool)
                    or not isinstance(version, int)
                    or version != MEEP_CACHE_VERSION
                ):
                    raise ValueError("Meep task is not CACHE_VERSION=6.")
            row["cache_version"] = (
                MEEP_CACHE_VERSION if any(v is not _MISSING for v in versions) else None
            )
            row["cache_version_note"] = (
                "verified" if row["cache_version"] is not None
                else "not recorded; post-bugfix dt guard verified"
            )
            dt_values = [
                meep_value(document, ("dt",))
                for document in (result, config)
            ]
            recorded_dt = [
                finite_float(value, "Meep dt")
                for value in dt_values if value is not _MISSING
            ]
            if not recorded_dt or any(not 0.0 < dt <= 0.0075 for dt in recorded_dt):
                raise ValueError("Meep task requires 0 < dt <= 0.0075.")
            row["dt"] = max(recorded_dt)

            design = meep_value(
                config,
                ("geometry_scope", "design_name", "design", "configuration_name", "name"),
            )
            if isinstance(design, Mapping):
                design = meep_value(design, ("name", "design_name"))
            if not isinstance(design, str) or not design:
                design = meep_value(result, ("design_name", "design"))
            if not isinstance(design, str) or not design:
                raise TypeError("Meep configuration has no design name.")
            row["design"] = design
            row["name"] = meep_value(config, ("name",), default=design)
            theta = meep_value(config, ("theta_deg", "angle_deg"))
            if theta is _MISSING:
                theta = meep_value(result, ("theta_deg", "angle_deg"))
            row["theta_deg"] = finite_float(theta, "Meep angle")
            resolution = meep_value(config, ("resolution", "R"))
            if isinstance(resolution, Mapping):
                resolution = meep_value(resolution, ("R", "resolution", "value"))
            if resolution is _MISSING:
                resolution = meep_value(result, ("resolution", "R"))
            row["R"] = finite_float(resolution, "Meep resolution")
            if row["R"] <= 0.0:
                raise ValueError("Meep resolution must be positive.")

            conversion = MEEP_FORCE_TO_SI_N
            supplied_conversion = meep_value(
                result, ("MEEP_FORCE_TO_SI_N", "meep_force_to_si_n"),
                meep_value(config, ("MEEP_FORCE_TO_SI_N", "meep_force_to_si_n")),
            )
            if supplied_conversion is not _MISSING:
                conversion = finite_float(supplied_conversion, "Meep force conversion")
                if conversion <= 0.0:
                    raise ValueError("Meep force conversion must be positive.")
            row["MEEP_FORCE_TO_SI_N"] = conversion
            # Build locally so a partially invalid task cannot expose valid-looking metrics.
            forces = {
                "F_2pass_pN": finite_float(
                    finite_float(meep_value(result, ("F_2pass",)), "Meep F_2pass")
                    * conversion * 1e12,
                    "Meep F_2pass_pN",
                ),
                "F_stator_only_pN": finite_float(
                    finite_float(
                        meep_value(result, ("F_stator_only",)), "Meep F_stator_only"
                    ) * conversion * 1e12,
                    "Meep F_stator_only_pN",
                ),
                "f_net_pN": finite_float(
                    meep_value(result, ("f_net_pN",)), "Meep f_net_pN"
                ),
            }
            row.update(forces)
            row["status"] = "complete"
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            row["error"] = str(exc)
        tasks.append(row)

    richardson: dict[str, Any] = {
        "status": "unavailable",
        "task_ids": [11, 8, 12],
        "design": "Cantor_N2_HybridRZ",
        "theta_deg": 3.0,
        "resolutions": [40, 50, 60],
        "order": 4,
        "method": "Three-point least-squares Richardson fit F(R)=F_inf+C*(1/R)^4.",
        "F_inf_4pass_pN": None,
        "r2_4pass": None,
        "points": [],
    }
    try:
        by_id = {row["task_id"]: row for row in tasks}
        points = []
        for task_id, resolution in zip((11, 8, 12), (40, 50, 60), strict=True):
            row = by_id[task_id]
            if (
                row["status"] != "complete"
                or row["design"] != "Cantor_N2_HybridRZ"
                or not math.isclose(row["theta_deg"], 3.0, rel_tol=0.0, abs_tol=1e-12)
                or row["R"] != resolution
            ):
                raise ValueError(f"Task {task_id} is not a valid Richardson input.")
            points.append({
                "task_id": task_id,
                "R": resolution,
                "dx": 1.0 / resolution,
                "f_net_pN": row["f_net_pN"],
            })
        # Scale dx^4 to avoid an ill-conditioned intercept fit.
        x = [(40.0 / point["R"]) ** 4 for point in points]
        y = [point["f_net_pN"] for point in points]
        x_mean = math.fsum(x) / 3.0
        y_mean = math.fsum(y) / 3.0
        denominator = math.fsum((value - x_mean) ** 2 for value in x)
        if denominator <= 0.0:
            raise ValueError("Degenerate Richardson grid.")
        slope = math.fsum(
            (xx - x_mean) * (yy - y_mean)
            for xx, yy in zip(x, y, strict=True)
        ) / denominator
        asymptote = finite_float(y_mean - slope * x_mean, "Richardson asymptote")
        predictions = [asymptote + slope * value for value in x]
        residual = math.fsum(
            (actual - predicted) ** 2
            for actual, predicted in zip(y, predictions, strict=True)
        )
        total = math.fsum((value - y_mean) ** 2 for value in y)
        r2 = finite_float(1.0 - residual / total, "Richardson R squared") if total else None
        richardson.update({
            "status": "complete",
            "points": points,
            "F_inf_4pass_pN": asymptote,
            "r2_4pass": r2,
            "coefficient_pN_um_minus4": finite_float(
                slope * 40.0**4, "Richardson coefficient"
            ),
            "residual_sum_squares_pN2": finite_float(residual, "Richardson residual"),
        })
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        richardson["error"] = str(exc)

    complete_count = sum(row["status"] == "complete" for row in tasks)
    return {
        "status": "complete" if complete_count == 12 else "partial" if complete_count else "unavailable",
        "completed_tasks": complete_count,
        "planned_tasks": 12,
        "cache_version": MEEP_CACHE_VERSION,
        "dt_max": 0.0075,
        "MEEP_FORCE_TO_SI_N": MEEP_FORCE_TO_SI_N,
        "tasks": tasks,
        "richardson": richardson,
        "force_note": "f_net_pN is the reported four-pass net force; no extra symmetry multiplier.",
    }


def derive_analysis(campaign: Campaign) -> dict[str, Any]:
    rows = campaign.rows
    analysis: dict[str, Any] = {}

    step1 = [row for row in rows if row["step"] == STEP_NAMES[0]]
    open_reference = next(
        (
            row for row in step1
            if row["theta_deg"] == 3.0
            and math.isclose(row["z_tip_um"], -0.100, abs_tol=1e-12)
        ),
        None,
    )
    pad_reference = next(
        (
            row for row in step1
            if row["theta_deg"] == 48.0
            and math.isclose(row["z_tip_um"], -0.100, abs_tol=1e-12)
        ),
        None,
    )
    analysis[STEP_NAMES[0]] = {
        "aperture_repulsive_z_tip_um": [
            row["z_tip_um"] for row in step1
            if row["theta_deg"] == 3.0 and row["F_z_pN"] > 0.0
        ],
        "aperture_attractive_overhanging_z_tip_um": [
            row["z_tip_um"] for row in step1
            if row["theta_deg"] == 3.0
            and row["max_z_top_um"] > 0.0 and row["F_z_pN"] < 0.0
        ],
        "flush_tip_aperture_repulsive": (
            open_reference["F_z_pN"] > 0.0 if open_reference else None
        ),
        "flush_tip_pad_attractive": (
            pad_reference["F_z_pN"] < 0.0 if pad_reference else None
        ),
        "flush_tip_abs_pad_to_aperture_force_ratio": (
            abs(pad_reference["F_z_pN"]) / abs(open_reference["F_z_pN"])
            if open_reference and pad_reference and open_reference["F_z_pN"] != 0.0
            else None
        ),
        "interpretation": (
            "Signs and force ratio are measured. 'Strongly attractive' has "
            "no imposed numerical threshold."
        ),
    }

    angular = sorted(
        (row for row in rows if row["step"] == STEP_NAMES[1]),
        key=lambda row: row["theta_deg"],
    )
    torque: list[dict[str, Any]] = []
    if len(angular) >= 3 and all(
        row["energy_hbar_c_per_um"] is not None for row in angular
    ):
        import numpy as np

        angles = np.array([math.radians(row["theta_deg"]) for row in angular], dtype=float)
        energies = np.array(
            [row["energy_hbar_c_per_um"] for row in angular], dtype=float
        )
        if not np.all(np.isfinite(energies)) or not np.all(np.diff(angles) > 0.0):
            raise ValueError("Invalid energy/angle array for restoring torque.")
        derivative = np.gradient(energies, angles, edge_order=2)
        torques = -HBAR_C_PN_UM2 * derivative
        for row, value in zip(angular, torques.tolist(), strict=True):
            torque.append({
                "task_id": row["task_id"],
                "theta_deg": row["theta_deg"],
                "tau_z_pN_um": finite_float(value, "restoring torque"),
            })
    analysis[STEP_NAMES[1]] = {
        "torque": torque,
        "torque_method": (
            "-hbar*c*d(energy_hbar_c_per_um)/d(theta_rad); "
            "nonuniform second-order finite differences"
        ),
        "hbar_c_pN_um2": HBAR_C_PN_UM2,
        "torque_status": (
            "computed" if torque
            else "unavailable: fewer than three energy samples or missing solver energies"
        ),
        "warning": "A vertical-force angular derivative is not an azimuthal torque.",
    }

    scores = step5_scores(rows)
    swing_champion = max(scores, key=lambda item: item["Delta_F_pN"]) if scores else None
    rep_champion = max(scores, key=lambda item: item["F_rep_pN"]) if scores else None
    compact = [
        score for score in scores
        if score["design"] in ("Cantor_N2_HybridRZ", "Cantor_N2_FlatZ")
    ]
    compact_champion = (
        max(compact, key=lambda item: item["Delta_F_pN"]) if compact else None
    )
    analysis[STEP_NAMES[4]] = {
        "scores": scores,
        "maximum_swing_champion": swing_champion,
        "maximum_repulsion_champion": rep_champion,
        "compact_N2_swing_champion": compact_champion,
        "maximum_per_tooth_swing_champion": (
            max(scores, key=lambda item: item["Delta_F_pN_per_tooth"])
            if scores else None
        ),
        "maximum_footprint_normalized_swing_champion": (
            max(scores, key=lambda item: item["Delta_F_pN_per_um2"])
            if scores else None
        ),
        "normalization_conventions": {
            "raw_force": "F_rep_pN, F_att_pN and Delta_F_pN are full-device forces in pN.",
            "per_tooth": "Full-device force divided by 4 * track_count; pN/tooth.",
            "per_area": "Fields ending _per_um2 use the full annular footprint; pN/um^2.",
            "per_tooth_area": (
                "Fields ending _per_tooth_area_um2 use full-device tooth planform area; pN/um^2."
            ),
            "control_alias": "Uniform_3Track_Control has the same geometry as Ctrl_UniformPeriodic.",
        },
        "nominated_N3_champion_confirmed_for_both": (
            swing_champion["design"] == "Fractal_N3_Cantor7Track"
            and rep_champion["design"] == "Fractal_N3_Cantor7Track"
            if swing_champion and rep_champion else None
        ),
        "policy": (
            "Raw-force champions include evaluated controls and are inferred from "
            "computed results, not stipulated. Normalized efficiencies are reported separately."
        ),
    }

    validation = [row for row in rows if row["step"] == STEP_NAMES[5]]
    monolithic: list[dict[str, Any]] = []
    ladder: list[dict[str, Any]] = []
    agreement: list[dict[str, Any]] = []
    for row in validation:
        if row["boundary"] == "Full-Monolithic":
            reference = next(
                (
                    candidate for candidate in validation
                    if candidate["design"] == row["design"]
                    and candidate["theta_deg"] == row["theta_deg"]
                    and candidate["formulation"] == row["formulation"]
                    and candidate["tier"] == row["tier"]
                    and candidate["boundary"] == "Active-Only"
                ),
                None,
            )
            if reference:
                monolithic.append({
                    "design": row["design"],
                    "theta_deg": row["theta_deg"],
                    **convergence_record(row, reference, campaign.agreement_tolerance),
                })
        if row["purpose"] != "resolution convergence and formulation cross-check":
            continue
        previous_tier = {"High": "Standard", "Ultra_High": "High"}.get(row["tier"])
        if previous_tier:
            previous = next(
                (
                    candidate for candidate in validation
                    if candidate["purpose"] == row["purpose"]
                    and candidate["design"] == row["design"]
                    and candidate["theta_deg"] == row["theta_deg"]
                    and candidate["formulation"] == row["formulation"]
                    and candidate["tier"] == previous_tier
                ),
                None,
            )
            if previous:
                ladder.append({
                    "design": row["design"],
                    "theta_deg": row["theta_deg"],
                    "formulation": row["formulation"],
                    "comparison": f"{previous_tier} -> {row['tier']}",
                    **convergence_record(row, previous, campaign.convergence_tolerance),
                })
        if row["formulation"] == "vector_dyadic":
            scalar = next(
                (
                    candidate for candidate in validation
                    if candidate["purpose"] == row["purpose"]
                    and candidate["design"] == row["design"]
                    and candidate["theta_deg"] == row["theta_deg"]
                    and candidate["tier"] == row["tier"]
                    and candidate["formulation"] == "scalar_yukawa"
                ),
                None,
            )
            if scalar:
                agreement.append({
                    "design": row["design"],
                    "theta_deg": row["theta_deg"],
                    "tier": row["tier"],
                    **convergence_record(row, scalar, campaign.agreement_tolerance),
                })
    analysis[STEP_NAMES[5]] = {
        "active_vs_full": monolithic,
        "resolution_ladder": ladder,
        "vector_vs_scalar": agreement,
        "convergence_tolerance": campaign.convergence_tolerance,
        "agreement_tolerance": campaign.agreement_tolerance,
        "all_observed_ultra_high_changes_within_tolerance": (
            all(item["within_tolerance"] for item in ladder if "Ultra_High" in item["comparison"])
            if any("Ultra_High" in item["comparison"] for item in ladder) else None
        ),
        "all_observed_formulations_within_tolerance": (
            all(item["within_tolerance"] for item in agreement) if agreement else None
        ),
        "interpretation": (
            "Agreement is tested, not assumed. Scalar Yukawa and vector dyadic "
            "models can differ physically; a failed cross-check is retained."
        ),
    }
    analysis["meep_verification"] = load_meep_verification()
    analysis["meep_verification"]["bem_comparison"] = [
        {
            key: row[key]
            for key in (
                "task_id", "design", "theta_deg", "formulation",
                "boundary", "tier", "F_z_pN",
            )
        }
        for row in validation
        if row["status"] == "ok"
        and row["design"] == "Cantor_N2_HybridRZ"
        and row["theta_deg"] == 3.0
    ]
    return analysis


CSV_COLUMNS = (
    "model", "dataset", "status", "executed_at", "source_status",
    "task_id", "step", "design", "theta_deg", "z_tip_um", "max_z_top_um",
    "formulation", "boundary", "tier", "track_count", "full_tooth_count",
    "F_z_pN", "F_z_pN_per_tooth", "F_z_pN_per_um2",
    "F_z_pN_per_tooth_area_um2", "full_tooth_planform_area_um2",
    "energy_hbar_c_per_um", "tau_z_pN_um", "landing_pad_overlap_fraction",
    "footprint_um2", "solver_elapsed_s", "reused_from_task_id",
)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], analysis: Mapping[str, Any]) -> None:
    import io

    torque = {
        item["task_id"]: item["tau_z_pN_um"]
        for item in analysis[STEP_NAMES[1]]["torque"]
    }
    executed_at = datetime.now(timezone.utc).isoformat()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(freshness_record(
            {**row, "tau_z_pN_um": torque.get(row["task_id"])}, executed_at
        ))
    atomic_text(path, buffer.getvalue())


def plot_campaign(
    campaign: Campaign, analysis: Mapping[str, Any], output_directory: Path
) -> tuple[Path, Path]:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 9,
        "legend.fontsize": 6,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    figure, axes = plt.subplots(2, 3, figsize=(13.0, 7.6), constrained_layout=True)
    titles = (
        "A  Single-tooth vertical-position sweep",
        "B  N=0 angular response",
        "C  Fractal hierarchy",
        "D  Fractal and matched controls",
        "E  Active-configuration raw force swing",
        "F  Monolithic and convergence validation",
    )
    colors = plt.get_cmap("tab10")
    for axis, title in zip(axes.flat, titles, strict=True):
        axis.set_title(title, loc="left")
        axis.axhline(0.0, color="0.65", linewidth=0.6)
        axis.grid(alpha=0.18)

    rows = campaign.rows
    axis = axes[0, 0]
    for index, angle in enumerate((3.0, 48.0)):
        selected = sorted(
            (
                row for row in rows
                if row["step"] == STEP_NAMES[0] and row["theta_deg"] == angle
            ),
            key=lambda row: row["z_tip_um"],
        )
        if selected:
            axis.plot(
                [row["z_tip_um"] for row in selected],
                [row["F_z_pN"] for row in selected], "o-",
                color=colors(index), label=f"{angle:g}°",
            )
    axis.set_xlabel(r"$z_{\mathrm{tip}}$ ($\mu$m)")
    axis.set_ylabel(r"$F_z$ (pN)")

    axis = axes[0, 1]
    angular = sorted(
        (row for row in rows if row["step"] == STEP_NAMES[1]),
        key=lambda row: row["theta_deg"],
    )
    if angular:
        axis.plot(
            [row["theta_deg"] for row in angular],
            [row["F_z_pN"] for row in angular], "o-", label=r"$F_z$",
        )
        secondary = axis.twinx()
        secondary.plot(
            [row["theta_deg"] for row in angular],
            [row["landing_pad_overlap_fraction"] for row in angular],
            "--", color="0.5",
        )
        secondary.set_ylabel("Pad overlap fraction", color="0.4")
        secondary.set_ylim(-0.03, 1.03)
    axis.set_xlabel(r"$\theta$ (deg)")
    axis.set_ylabel(r"$F_z$ (pN)")

    axis = axes[0, 2]
    hierarchy_names = (
        "Fractal_N0_SingleTrack", "Fractal_N1_FundRing",
        "Fractal_N2_Cantor3Track", "Fractal_N3_Cantor7Track",
    )
    for index, angle in enumerate((3.0, 21.0, 48.0)):
        selected = {
            row["design"]: row for row in rows
            if row["step"] == STEP_NAMES[2] and row["theta_deg"] == angle
        }
        x = [level for level, name in enumerate(hierarchy_names) if name in selected]
        if x:
            axis.plot(
                x, [selected[hierarchy_names[level]]["F_z_pN"] for level in x],
                "o-", color=colors(index), label=f"{angle:g}°",
            )
    axis.set_xticks(range(4), ("N0 / 1", "N1 / 1", "N2 / 3", "N3 / 7"))
    axis.set_xlabel("Generation / track count")
    axis.set_ylabel(r"$F_z$ (pN)")

    axis = axes[1, 0]
    control_names = (
        "Cantor_N2_FlatZ", "Cantor_N2_HybridRZ", "Ctrl_SingleWide",
        "Ctrl_UniformPeriodic", "Ctrl_SizeMatched_Monotonic",
        "Uniform_3Track_Control",
    )
    control_labels = ("Flat Z", "Hybrid RZ", "Wide", "Periodic", "Monotonic", "Uniform 3")
    for index, angle in enumerate((3.0, 48.0)):
        selected = {
            row["design"]: row for row in rows
            if row["step"] == STEP_NAMES[3] and row["theta_deg"] == angle
        }
        x = [number for number, name in enumerate(control_names) if name in selected]
        if x:
            axis.bar(
                [number + (index - 0.5) * 0.36 for number in x],
                [selected[control_names[number]]["F_z_pN"] for number in x],
                width=0.36, color=colors(index), label=f"{angle:g}°",
            )
    axis.set_xticks(range(len(control_names)), control_labels, rotation=30, ha="right")
    axis.set_ylabel(r"$F_z$ (pN)")

    axis = axes[1, 1]
    scores = analysis[STEP_NAMES[4]]["scores"]
    if scores:
        labels = [
            score["design"].replace("Cantor_N2_", "N2 ").replace(
                "Fractal_N3_Cantor7Track", "N3 / 7"
            ).replace("Rot_C8_Compact_N2", "Compact N2").replace(
                "Ctrl_SizeMatched_Monotonic", "Monotonic"
            ).replace("Ctrl_UniformPeriodic", "Periodic").replace(
                "Uniform_3Track_Control", "Uniform 3"
            ).replace("Ctrl_SingleWide", "Wide")
            for score in scores
        ]
        for index, (key, label) in enumerate((
            ("F_rep_pN", "Repulsion"),
            ("F_att_pN", "Attraction (signed)"),
            ("Delta_F_pN", "Swing"),
        )):
            axis.bar(
                [number + (index - 1) * 0.25 for number in range(len(scores))],
                [score[key] for score in scores],
                width=0.25, color=colors(index), label=label,
            )
        axis.set_xticks(range(len(scores)), labels, rotation=30, ha="right")
    axis.set_ylabel("Raw force / force swing (pN)")

    axis = axes[1, 2]
    validation = [row for row in rows if row["step"] == STEP_NAMES[5]]
    ladder = [
        row for row in validation
        if row["purpose"] == "resolution convergence and formulation cross-check"
    ]
    for index, (angle, formulation) in enumerate((
        (3.0, "scalar_yukawa"), (48.0, "scalar_yukawa"),
        (3.0, "vector_dyadic"), (48.0, "vector_dyadic"),
    )):
        selected = {
            row["tier"]: row for row in ladder
            if row["theta_deg"] == angle and row["formulation"] == formulation
        }
        x = [level for level, name in enumerate(
            ("Standard", "High", "Ultra_High")
        ) if name in selected]
        if x:
            names = ("Standard", "High", "Ultra_High")
            axis.plot(
                x, [selected[names[level]]["F_z_pN"] for level in x],
                "o-" if formulation == "scalar_yukawa" else "s--",
                color=colors(index),
                label=f"{angle:g}° {'scalar' if formulation == 'scalar_yukawa' else 'vector'}",
            )
    for index, name in enumerate(("Cantor_N2_HybridRZ", "Fractal_N3_Cantor7Track")):
        for angle_index, angle in enumerate((3.0, 48.0)):
            selected = [
                row for row in validation
                if row["design"] == name and row["theta_deg"] == angle
                and row["tier"] == "Standard"
                and row["formulation"] == campaign.formulation
                and row["purpose"] == "active-only approximation validation"
            ]
            center = 3.2 + index * 0.9 + angle_index * 0.30
            for row in selected:
                full = row["boundary"] == "Full-Monolithic"
                axis.scatter(
                    center + (0.05 if full else -0.05), row["F_z_pN"],
                    marker="D" if full else "x", color=colors(4 + index),
                    s=25,
                    label=(
                        "Full" if full else "Active"
                    ) if index == 0 and angle_index == 0 else None,
                )
    ticks = [0, 1, 2, 3.35, 4.25]
    tick_labels = ["Std", "High", "Ultra", "N2 A/F", "N3 A/F"]
    richardson = analysis.get("meep_verification", {}).get("richardson", {})
    if richardson.get("status") == "complete":
        points = richardson["points"]
        positions = [5.2 + index * 0.6 for index in range(len(points))]
        axis.plot(
            positions, [point["f_net_pN"] for point in points],
            "^:", color=colors(6), label="Meep 3° R=40,50,60",
        )
        axis.axhline(
            richardson["F_inf_4pass_pN"], color=colors(7), linestyle="--",
            linewidth=1.0, label="Meep Rich. asymptote",
        )
        ticks.extend(positions)
        tick_labels.extend(f"R{point['R']}" for point in points)
    axis.set_xticks(ticks, tick_labels, rotation=30, ha="right")
    axis.set_ylabel(r"$F_z$ (pN)")

    for index, axis in enumerate(axes.flat):
        step_rows = [row for row in rows if row["step"] == STEP_NAMES[index]]
        has_meep = index == 5 and richardson.get("status") == "complete"
        if not step_rows and not has_meep:
            axis.text(
                0.5, 0.5, "Not executed", transform=axis.transAxes,
                ha="center", va="center", color="0.4",
            )
        handles, labels = axis.get_legend_handles_labels()
        if handles:
            axis.legend(handles, labels, loc="best", frameon=False)

    figure.suptitle(
        "Fractal Casimir Rotary Clutch — six-step BEM narrative"
        + (" (INCOMPLETE MICRO-PROBE)" if 0 < campaign.max_steps <= 10 else ""),
        fontsize=12,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    pdf = output_directory / "fig_nature_6step_narrative.pdf"
    png = output_directory / "fig_nature_6step_narrative.png"
    try:
        figure.savefig(pdf, bbox_inches="tight")
        figure.savefig(png, dpi=220, bbox_inches="tight")
    finally:
        plt.close(figure)
    return pdf, png


def format_number(value: Any) -> str:
    return "unavailable" if value is None else f"{finite_float(value, 'report value'):.8g}"


def markdown_report(report: Mapping[str, Any]) -> str:
    analysis = report["analysis"]
    lines = [
        "# Fractal Casimir Rotary Clutch: six-step narrative",
        "",
        f"- Status: **{report.get('campaign_status', report['status'])}**",
        f"- Solver: `{SOLVER_NAME}`",
        f"- Formulation for steps 1–5: `{report['configuration']['formulation']}`",
        f"- Device: `{report['configuration']['device']}`",
        f"- Executed task records: {len(report['tasks'])}",
        f"- Unique solver evaluations represented: {report['unique_solver_evaluations']}",
        f"- New BEM evaluations this run: {report.get('new_solver_evaluations', report['unique_solver_evaluations'])}",
        f"- Elapsed time before report generation: {report['elapsed_s']:.3f} s",
        "",
        "## Numerical and provenance conventions",
        "",
        "- All forces and energies below are solver outputs, not fitted or stipulated.",
        "- Meshes contain one 90-degree sector; the solver supplies fourfold symmetry.",
        "- Positive vertical force denotes repulsion; negative denotes attraction.",
        "- Raw force is full-device force in pN; per-tooth efficiency divides by",
        "  four times the track count (the full-device tooth count).",
        "- Footprint-normalized efficiency uses the full annular active footprint;",
        "  tooth-area-normalized efficiency instead uses full tooth planform area.",
        "- Raw-force rankings are distinct from normalized-efficiency rankings.",
        "- Uniform_3Track_Control is the named alias of Ctrl_UniformPeriodic;",
        "  both are reported transparently and are not independent geometries.",
        "- Pad overlap is an analytic projected-area fraction, not a solver observable.",
        "- Missing measurements are unavailable, never filled with zeros.",
        "- Freshness status `completed` denotes report/table-record generation;",
        "  `campaign_status` and row `source_status` retain actual solver availability",
        "  and incomplete/failed campaign states.",
        "- Scalar/vector agreement and convergence are tested rather than assumed.",
        "- Passive support validation includes union-boundary spider spokes and collars",
        "  at z = 0.350–0.470 µm and the trench slab at z = −0.650–−0.550 µm.",
        "",
    ]
    if report.get("error"):
        lines.extend(("## Execution error", "", "```text", report["error"], "```", ""))
    for step in STEP_NAMES:
        state = report["steps"][step]
        lines.extend((
            f"## {step}",
            "",
            f"Status: {state['status']}; records: {state['completed_tasks']}.",
            "",
        ))
        selected = [row for row in report["tasks"] if row["step"] == step]
        if selected:
            lines.extend((
                "| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |",
                "|---|---:|---:|---|---|---|---:|---:|",
            ))
            for row in selected:
                lines.append(
                    f"| {row['design']} | {row['theta_deg']:g} | {row['z_tip_um']:g} "
                    f"| {row['boundary']} | {row['tier']} | {row['formulation']} "
                    f"| {format_number(row['F_z_pN'])} "
                    f"| {format_number(row['energy_hbar_c_per_um'])} |"
                )
            lines.append("")
        if step == STEP_NAMES[0]:
            observation = analysis[step]
            lines.extend((
                "At z_tip = −0.100 µm:",
                f"- Aperture repulsion verified: {observation['flush_tip_aperture_repulsive']}",
                f"- Pad attraction verified: {observation['flush_tip_pad_attractive']}",
                "- |pad force| / |aperture force|: "
                + format_number(observation["flush_tip_abs_pad_to_aperture_force_ratio"]),
                "",
            ))
        elif step == STEP_NAMES[1]:
            lines.extend((
                analysis[step]["torque_status"],
                "",
                analysis[step]["torque_method"] + ".",
                "",
            ))
            if analysis[step]["torque"]:
                lines.extend(("| θ (deg) | τz (pN µm) |", "|---:|---:|"))
                for item in analysis[step]["torque"]:
                    lines.append(
                        f"| {item['theta_deg']:g} | {item['tau_z_pN_um']:.8g} |"
                    )
                lines.append("")
        elif step == STEP_NAMES[4]:
            scores = analysis[step]["scores"]
            if scores:
                lines.extend((
                    "### Raw full-device force",
                    "",
                    "| Candidate | Kind | Repulsion (pN) | Attraction (pN) | Swing (pN) |",
                    "|---|---|---:|---:|---:|",
                ))
                for score in scores:
                    lines.append(
                        f"| {score['design']} | {score['candidate_kind']} "
                        f"| {score['F_rep_pN']:.8g} | {score['F_att_pN']:.8g} "
                        f"| {score['Delta_F_pN']:.8g} |"
                    )
                lines.extend((
                    "",
                    "### Normalized efficiency",
                    "",
                    "| Candidate | Full tooth count | Repulsion (pN/tooth) | Swing (pN/tooth) | Repulsion / footprint (pN/µm²) | Swing / footprint (pN/µm²) | Repulsion / tooth area (pN/µm²) |",
                    "|---|---:|---:|---:|---:|---:|---:|",
                ))
                for score in scores:
                    lines.append(
                        f"| {score['design']} | {score['full_tooth_count']:g} "
                        f"| {score['F_rep_pN_per_tooth']:.8g} "
                        f"| {score['Delta_F_pN_per_tooth']:.8g} "
                        f"| {score['F_rep_pN_per_um2']:.8g} "
                        f"| {score['Delta_F_pN_per_um2']:.8g} "
                        f"| {format_number(score['F_rep_pN_per_tooth_area_um2'])} |"
                    )
                lines.append("")
                for key, label in (
                    ("maximum_swing_champion", "Maximum raw-swing champion"),
                    ("maximum_repulsion_champion", "Maximum raw-repulsion champion"),
                    ("compact_N2_swing_champion", "Compact N=2 raw-swing champion"),
                    ("maximum_per_tooth_swing_champion", "Maximum per-tooth-swing champion"),
                    (
                        "maximum_footprint_normalized_swing_champion",
                        "Maximum footprint-normalized-swing champion",
                    ),
                ):
                    champion = analysis[step][key]
                    lines.append(
                        f"- {label}: **{champion['design'] if champion else 'unavailable'}**"
                    )
                lines.extend((
                    "",
                    "These are the specified 3° and 48° operating states, not a "
                    "proof of globally maximal force over all angles.",
                    "",
                ))
        elif step == STEP_NAMES[5]:
            for key, label in (
                ("active_vs_full", "Active-only versus full monolithic"),
                ("resolution_ladder", "Resolution convergence"),
                ("vector_vs_scalar", "Vector-dyadic versus scalar-Yukawa"),
            ):
                lines.extend((f"### {label}", ""))
                comparisons = analysis[step][key]
                if not comparisons:
                    lines.extend(("Not measured.", ""))
                    continue
                lines.extend((
                    "| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |",
                    "|---|---:|---|---:|---:|---|",
                ))
                for item in comparisons:
                    comparison = item.get("comparison", item.get("tier", label))
                    lines.append(
                        f"| {item['design']} | {item['theta_deg']:g} | {comparison} "
                        f"| {item['absolute_difference_pN']:.8g} "
                        f"| {format_number(item['relative_difference'])} "
                        f"| {item['within_tolerance']} |"
                    )
                lines.append("")
            lines.extend((analysis[step]["interpretation"], ""))

    meep = analysis.get("meep_verification", {})
    lines.extend((
        "## 3D FDTD Meep Cross-Solver Verification & Yee-Grid Convergence (BigRed 200)",
        "",
        f"Suite status: **{meep.get('status', 'unavailable')}**; "
        f"validated tasks: {meep.get('completed_tasks', 0)}/12.",
        "",
        "Only complete tasks with 0 < dt ≤ 0.0075 are admitted. Recorded cache "
        "versions must equal 6; missing version metadata is identified below.",
        "Two-pass and stator-only forces are converted using "
        "`F * MEEP_FORCE_TO_SI_N * 1e12`; the four-pass `f_net_pN` is already in pN.",
        "",
        "| Task | Design | θ (deg) | R | dt | Cache version | Status | F₂pass (pN) | Fstator-only (pN) | F₄pass net (pN) |",
        "|---:|---|---:|---:|---:|---|---|---:|---:|---:|",
    ))
    for item in meep.get("tasks", []):
        lines.append(
            f"| {item['task_id']} | {item.get('design') or 'unavailable'} "
            f"| {format_number(item.get('theta_deg'))} "
            f"| {format_number(item.get('R'))} | {format_number(item.get('dt'))} "
            f"| {item.get('cache_version') if item.get('cache_version') is not None else 'not recorded'} "
            f"| {item.get('source_status', item['status'])} | {format_number(item.get('F_2pass_pN'))} "
            f"| {format_number(item.get('F_stator_only_pN'))} "
            f"| {format_number(item.get('f_net_pN'))} |"
        )
    lines.append("")
    for item in meep.get("tasks", []):
        if item.get("error"):
            lines.append(f"- Task {item['task_id']}: {item['error']}")
    richardson = meep.get("richardson", {})
    if richardson.get("status") == "complete":
        asymptote = finite_float(richardson["F_inf_4pass_pN"], "Meep asymptote")
        r2 = richardson.get("r2_4pass")
        r2_text = "unavailable (constant force samples)" if r2 is None else f"{r2:.4f}"
        lines.extend((
            "",
            "### Richardson continuum extrapolation",
            "",
            "Cantor_N2_HybridRZ at θ = 3°: Tasks 11, 8, 12, "
            "R = 40, 50, 60; dx = 1/R.",
            "A three-point fixed-order p = 4 fit uses `F(R) = F_inf + C dx^4`.",
            f"**R = 40, 50, 60 → F_inf = {asymptote:+.4f} pN "
            f"(R² = {r2_text})**.",
            "",
            "| Task | R | Four-pass force (pN) |",
            "|---:|---:|---:|",
        ))
        for point in richardson["points"]:
            lines.append(
                f"| {point['task_id']} | {point['R']} | {point['f_net_pN']:+.8g} |"
            )
        lines.extend((
            "",
            "The asymptote and R² are recomputed from the supplied measurements, "
            "not imposed constants. R² describes this fixed-order fit, not an "
            "independent proof of fourth-order convergence.",
            "",
        ))
    else:
        lines.extend((
            "",
            "Richardson continuum extrapolation unavailable: "
            + richardson.get("error", "missing validated convergence data"),
            "",
        ))
    bem = meep.get("bem_comparison", [])
    lines.extend(("### Corresponding 3D BEM results (Cantor_N2_HybridRZ, θ = 3°)", ""))
    if bem:
        lines.extend((
            "| BEM task | Model | Boundary | Tier | Fz (pN) |",
            "|---|---|---|---|---:|",
        ))
        for item in bem:
            lines.append(
                f"| {item['task_id']} | {item['formulation']} "
                f"| {item['boundary']} | {item['tier']} | {item['F_z_pN']:+.8g} |"
            )
        lines.append("")
    else:
        lines.extend(("Not measured in this campaign.", ""))
    lines.extend((
        "Meep and BEM are independent solver results. Differences in discretization "
        "and physical formulation are retained rather than forced into agreement.",
        "",
        "## Artifacts",
        "",
        "- `results/nature_6step_narrative_report.json`",
        "- `results/nature_6step_narrative_data.csv`",
        "- `results/macros_results.tex`",
        "- `figures/fig_nature_6step_narrative.pdf`",
        "- `figures/fig_nature_6step_narrative.png`",
        "",
    ))
    return "\n".join(lines)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps", type=int, default=0,
        help="0 uses solver defaults; 1–10 executes only the first campaign task.",
    )
    parser.add_argument(
        "--formulation", choices=("scalar_yukawa", "vector_dyadic"),
        default="vector_dyadic",
    )
    parser.add_argument(
        "--convergence-tolerance", type=float, default=0.15,
        help="Relative force-change threshold for adjacent resolution tiers.",
    )
    parser.add_argument(
        "--agreement-tolerance", type=float, default=0.15,
        help="Relative threshold for active/full and scalar/vector comparisons.",
    )
    arguments = parser.parse_args()
    if arguments.max_steps < 0:
        parser.error("--max-steps must be nonnegative.")
    for name in ("convergence_tolerance", "agreement_tolerance"):
        value = getattr(arguments, name)
        if not math.isfinite(value) or value < 0.0:
            parser.error(f"--{name.replace('_', '-')} must be finite and nonnegative.")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    os.chdir(REPOSITORY_ROOT)
    results_directory = REPOSITORY_ROOT / "results"
    figures_directory = REPOSITORY_ROOT / "figures"
    results_directory.mkdir(parents=True, exist_ok=True)

    try:
        import torch
    except ImportError:
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    campaign = Campaign(
        max_steps=arguments.max_steps,
        formulation=cast(Formulation, arguments.formulation),
        device=device,
        convergence_tolerance=arguments.convergence_tolerance,
        agreement_tolerance=arguments.agreement_tolerance,
    )
    resumed_rows = campaign.load_resume(
        results_directory / "nature_6step_narrative_report.json"
    )
    if resumed_rows:
        print(f"Loaded {resumed_rows} validated BEM task records for resume.", flush=True)
    micro_probe = 0 < arguments.max_steps <= 10
    configuration = {
        "python_version": sys.version,
        "repository_root": str(REPOSITORY_ROOT),
        "formulation": arguments.formulation,
        "device": device,
        "max_steps": arguments.max_steps,
        "micro_probe": micro_probe,
        "convergence_tolerance": arguments.convergence_tolerance,
        "agreement_tolerance": arguments.agreement_tolerance,
        "solver_sha256": callable_source_hash(run_bem_casimir_solver),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "energy_conversion_hbar_c_pN_um2": HBAR_C_PN_UM2,
        "resume_loaded_rows": resumed_rows,
    }
    set_solver_provenance(SOLVER_NAME, solver_parameters=configuration)

    error: str | None = None
    designs: dict[str, StudyDesign] = {}
    controls: dict[str, Any] = {}
    expected = {step: 0 for step in STEP_NAMES}
    completed_campaign = False
    champion_name: str | None = None

    try:
        designs = build_designs()
        controls = validate_controls(designs)
        configuration["active_mesh_reference"] = mesh_adapter().provenance
        initial_tasks = tasks_steps_1_to_5(designs, campaign.formulation)
        for task in initial_tasks:
            expected[task.step] += 1
        expected[STEP_NAMES[5]] = 16
        if micro_probe:
            campaign.run(initial_tasks[0])
        else:
            for task in initial_tasks:
                campaign.run(task)
            scores = step5_scores(campaign.rows)
            if not scores:
                raise RuntimeError("Step 5 produced no complete candidate comparisons.")
            champion_name = str(max(scores, key=lambda score: score["Delta_F_pN"])["design"])
            validation_tasks = step6_tasks(designs, campaign.formulation, champion_name)
            expected[STEP_NAMES[5]] = len(validation_tasks)
            for task in validation_tasks:
                campaign.run(task)
            completed_campaign = True
    except Exception:
        error = traceback.format_exc()
        print(error, file=sys.stderr, flush=True)

    analysis = derive_analysis(campaign)
    steps: dict[str, dict[str, Any]] = {}
    for step in STEP_NAMES:
        count = sum(row["step"] == step for row in campaign.rows)
        planned = expected[step]
        steps[step] = {
            "completed_tasks": count,
            "planned_tasks": planned,
            "status": (
                "complete" if planned > 0 and count == planned
                else "partial" if count else "not_executed"
            ),
        }
    status = (
        "failed" if error
        else "micro_probe_incomplete" if micro_probe
        else "complete" if completed_campaign else "incomplete"
    )
    unique_evaluations = len({row["cache_key"] for row in campaign.rows})
    report: dict[str, Any] = {
        **freshness_metadata(),
        "schema_version": 1,
        "campaign_status": status,
        "freshness_status_scope": "report and table-record generation, not solver success",
        "configuration": configuration,
        "elapsed_s": time.perf_counter() - campaign.started,
        "micro_probe_runtime_target_s": 20.0 if micro_probe else None,
        "micro_probe_runtime_note": (
            "Target is hardware-dependent; measured runtime is reported, not guaranteed."
            if micro_probe else None
        ),
        "unique_solver_evaluations": unique_evaluations,
        "new_solver_evaluations": campaign.solver_evaluations,
        "resumed_task_records": sum(
            bool(row.get("resumed_from_report")) for row in campaign.rows
        ),
        "steps": steps,
        "designs": {
            name: {
                **dataclasses.asdict(design),
                "geometry_metrics": tooth_geometry_metrics(design),
            }
            for name, design in designs.items()
        },
        "matched_control_validation": controls,
        "step6_active_champion": champion_name,
        "tasks": campaign.rows,
        "analysis": analysis,
        "error": error,
        "units": {
            "length": "um",
            "force": "pN",
            "force_per_tooth": "pN/tooth",
            "force_per_area": "pN/um^2",
            "energy_hbar_c_per_um": "hbar*c/um",
            "torque": "pN*um",
            "mesh_face_angles": "radians",
            "reported_rotation_angles": "degrees",
        },
    }

    csv_path = results_directory / "nature_6step_narrative_data.csv"
    json_path = results_directory / "nature_6step_narrative_report.json"
    markdown_path = results_directory / "nature_6step_narrative_report.md"
    artifact_error: str | None = None
    try:
        write_csv(csv_path, campaign.rows, analysis)
        pdf, png = plot_campaign(campaign, analysis, figures_directory)
        meep = analysis["meep_verification"]
        for figure_path in (pdf, png):
            save_plot_provenance(
                str(figure_path.relative_to(REPOSITORY_ROOT)),
                data_source=str(csv_path.relative_to(REPOSITORY_ROOT)),
                columns_used=[
                    "step", "design", "theta_deg", "z_tip_um",
                    "F_z_pN", "landing_pad_overlap_fraction",
                    "boundary", "tier", "formulation", "footprint_um2",
                ],
                solver_name=SOLVER_NAME,
                solver_parameters={
                    **configuration,
                    "campaign_status": status,
                    "derived_quantities": {
                        "Delta_F_pN": "F_z_pN(theta=3) - F_z_pN(theta=48)",
                        "F_rep_pN_per_um2": "F_z_pN(theta=3) / footprint_um2",
                        "F_rep_pN_per_tooth": "F_z_pN(theta=3) / (4 * track_count)",
                        "F_rep_pN_per_tooth_area_um2": (
                            "F_z_pN(theta=3) / full_tooth_planform_area_um2"
                        ),
                    },
                    "meep_sources": [
                        {
                            key: row.get(key)
                            for key in (
                                "task_id", "result_path", "config_path",
                                "result_sha256", "config_sha256", "status",
                            )
                        }
                        for row in meep["tasks"]
                    ],
                    "meep_richardson": meep["richardson"],
                },
            )
        log_step(
            "nature_6step_narrative_summary",
            json_safe({
                "status": status,
                "steps": steps,
                "analysis": analysis,
                "matched_control_validation": controls,
                "report_path": str(json_path.relative_to(REPOSITORY_ROOT)),
            }),
            solver_name=SOLVER_NAME,
            solver_parameters=configuration,
        )
        for score in analysis[STEP_NAMES[4]]["scores"]:
            for key in (
                "F_rep_pN", "F_att_pN", "Delta_F_pN", "F_rep_pN_per_um2",
                "F_att_pN_per_um2", "Delta_F_pN_per_um2",
                "F_rep_pN_per_tooth", "F_att_pN_per_tooth", "Delta_F_pN_per_tooth",
                "F_rep_pN_per_tooth_area_um2", "F_att_pN_per_tooth_area_um2",
                "Delta_F_pN_per_tooth_area_um2",
            ):
                if score[key] is None:
                    continue
                log_metric(
                    f"nature_{score['design']}_{key}", score[key],
                    solver_name=SOLVER_NAME,
                    solver_parameters={
                        **configuration,
                        "design": score["design"],
                        "derived_from_step": STEP_NAMES[4],
                        "sample_angles_deg": [3.0, 48.0],
                        "full_tooth_count": score["full_tooth_count"],
                        "footprint_um2": score["footprint_um2"],
                        "full_tooth_planform_area_um2": score["full_tooth_planform_area_um2"],
                    },
                )
    except Exception:
        artifact_error = traceback.format_exc()
        print(artifact_error, file=sys.stderr, flush=True)
    finally:
        # Meep logging is independent of plotting failures and precedes macro export.
        try:
            meep = analysis["meep_verification"]
            for row in meep["tasks"]:
                task_id = row["task_id"]
                meep_parameters = {
                    "configuration": row.get("configuration"),
                    "result_path": row["result_path"],
                    "config_path": row["config_path"],
                    "result_sha256": row.get("result_sha256"),
                    "config_sha256": row.get("config_sha256"),
                    "cache_version": row.get("cache_version"),
                    "dt": row.get("dt"),
                    "MEEP_FORCE_TO_SI_N": row.get(
                        "MEEP_FORCE_TO_SI_N", MEEP_FORCE_TO_SI_N
                    ),
                }
                name = f"nature_meep_task_{task_id}"
                logged_id = log_step(
                    name, json_safe(row),
                    solver_name="Meep 3D FDTD",
                    solver_parameters=json_safe(meep_parameters),
                )
                if row["status"] != "complete":
                    continue
                for key in ("f_net_pN", "F_2pass_pN"):
                    log_metric(
                        f"{name}_{key}", row[key],
                        step_id=logged_id if isinstance(logged_id, str) else name,
                        solver_name="Meep 3D FDTD",
                        solver_parameters=json_safe(meep_parameters),
                    )
            richardson = meep["richardson"]
            name = "nature_meep_richardson"
            richardson_parameters = {
                "task_ids": richardson["task_ids"],
                "resolutions": richardson["resolutions"],
                "order": richardson["order"],
                "method": richardson["method"],
                "design": richardson["design"],
                "theta_deg": richardson["theta_deg"],
                "source_files": [
                    {
                        key: row.get(key)
                        for key in (
                            "task_id", "result_path", "config_path",
                            "result_sha256", "config_sha256",
                        )
                    }
                    for row in meep["tasks"]
                    if row["task_id"] in richardson["task_ids"]
                ],
            }
            logged_id = log_step(
                name, json_safe(richardson),
                solver_name="Meep 3D FDTD Richardson extrapolation",
                solver_parameters=richardson_parameters,
            )
            if richardson["status"] == "complete":
                for key in ("F_inf_4pass_pN", "r2_4pass"):
                    if richardson[key] is not None:
                        log_metric(
                            f"{name}_{key}", richardson[key],
                            step_id=logged_id if isinstance(logged_id, str) else name,
                            solver_name="Meep 3D FDTD Richardson extrapolation",
                            solver_parameters=richardson_parameters,
                        )
        except Exception:
            meep_log_error = traceback.format_exc()
            print(meep_log_error, file=sys.stderr, flush=True)
            artifact_error = (
                f"{artifact_error}\n{meep_log_error}" if artifact_error else meep_log_error
            )

        # This is the campaign's single macro-export call.
        try:
            export_macros(output_path="results/macros_results.tex")
        except Exception:
            macro_error = traceback.format_exc()
            print(macro_error, file=sys.stderr, flush=True)
            artifact_error = (
                f"{artifact_error}\n{macro_error}" if artifact_error else macro_error
            )

        report["artifact_error"] = artifact_error
        report["total_elapsed_s"] = time.perf_counter() - campaign.started
        if micro_probe:
            report["micro_probe_runtime_target_met"] = report["total_elapsed_s"] < 20.0
        if artifact_error:
            report["campaign_status"] = "failed"
        report["executed_at"] = datetime.now(timezone.utc).isoformat()
        serialized_report = freshness_tables(json_safe(report), report["executed_at"])
        # Named mappings are also tabular records, even without a list container.
        for container_name in ("designs", "matched_control_validation"):
            serialized_report[container_name] = {
                name: freshness_record(row, report["executed_at"])
                for name, row in serialized_report[container_name].items()
            }
        atomic_text(
            json_path,
            json.dumps(serialized_report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        atomic_text(markdown_path, markdown_report(report))

    print(
        f"Campaign {report['campaign_status']}; "
        f"{len(campaign.rows)} records, {unique_evaluations} unique evaluations "
        f"represented, {campaign.solver_evaluations} new BEM evaluations, "
        f"{report['total_elapsed_s']:.3f} s.\n"
        f"Report: {json_path}",
        flush=True,
    )
    return 1 if error or artifact_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
