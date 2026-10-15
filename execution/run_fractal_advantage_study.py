#!/usr/bin/env python3
"""Matched BEM study of radial/vertical fractal Casimir clutch designs.

All geometric dimensions are in micrometres. Forces reported by the study
are in pN. Run from any directory; output paths are relative to the repository.
"""

from __future__ import annotations

import argparse
import dataclasses
import inspect
import json
import math
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import numpy as np
import torch

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

RESULTS = REPOSITORY_ROOT / "results"
FIGURES = REPOSITORY_ROOT / "figures"
REPORT_JSON = RESULTS / "fractal_advantage_study_report.json"
REPORT_MD = RESULTS / "fractal_advantage_study_report.md"
FIGURE_STEM = FIGURES / "fig_fractal_advantage_study"
SOLVER_PROVENANCE: dict[str, Any] = {}

DZ_VALUES = (-0.060, -0.030, 0.000, 0.020, 0.040)
WINDOW_DESIGNS = (
    "Ctrl_UniformPeriodic",
    "Cantor_FlatZ",
    "Cantor_RZ_ScaleMatched",
    "Cantor_Z_Staircase",
)


@dataclass(frozen=True)
class TrackSpec3D:
    r_inner: float
    r_outer: float
    r_tooth_in: float
    r_tooth_out: float
    z_tip: float
    h_teeth: float
    level: int = 1


@dataclass(frozen=True)
class StudyDesign:
    name: str
    category: str
    description: str
    R_min: float
    R_max: float
    aperture_arc_deg: float
    tooth_arc_deg: float
    t_membrane: float
    t_landing_pad: float
    z_pad_top: float
    tracks: tuple[TrackSpec3D, ...]


@dataclass(frozen=True)
class Task:
    design: StudyDesign
    theta_deg: float
    delta_z_rotor: float
    experiment: str


def finite(value: Any, label: str) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise TypeError(f"{label} must be a real number, not {type(value).__name__}")
    if isinstance(value, torch.Tensor):
        if value.numel() != 1:
            raise ValueError(f"{label} must be scalar")
        value = value.detach().cpu().item()
    array = np.asarray(value)
    if array.size != 1:
        raise ValueError(f"{label} must be scalar")
    result = float(array.reshape(-1)[0])
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite: {result}")
    return result


def normalized_name(name: str) -> str:
    return "".join(c.lower() for c in name if c.isalnum())


def invoke(
    function: Callable[..., Any],
    values: Mapping[str, Any],
    *,
    extras: Mapping[str, Any] | None = None,
) -> Any:
    """Bind supported repository API spellings without retrying failed calls.

    Signature adaptation is deliberately conservative: an unrecognized required
    parameter is an error, rather than silently substituting an incorrect value.
    """
    signature = inspect.signature(function)
    normalized = {normalized_name(k): v for k, v in values.items()}
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    accepts_kwargs = False
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_kwargs = True
            continue
        key = normalized_name(parameter.name)
        if key in normalized:
            value = normalized[key]
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            raise TypeError(
                f"Unsupported repository API: {function.__module__}."
                f"{function.__qualname__}{signature}; missing binding for "
                f"{parameter.name!r}"
            )
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[parameter.name] = value
    if accepts_kwargs and extras:
        for key, value in extras.items():
            keywords.setdefault(key, value)
    return function(*positional, **keywords)


def aliases(value: Any, *names: str) -> dict[str, Any]:
    return dict.fromkeys(names, value)


def field_value(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    raise TypeError(f"{type(obj).__name__} lacks required field {names!r}")


def tooth_segments(
    theta_deg: float, tooth_arc_deg: float,
) -> tuple[tuple[float, float, bool, bool], ...]:
    """Tooth intervals and physical end caps in one periodic 90-degree sector."""
    theta_deg = finite(theta_deg, "theta_deg")
    width = finite(tooth_arc_deg, "tooth_arc_deg")
    if not 0.0 < width < 90.0:
        raise ValueError("tooth_arc_deg must lie strictly between 0 and 90")
    center = (15.0 + theta_deg % 90.0) % 90.0
    low, high = center - width / 2.0, center + width / 2.0
    if low < 0.0:
        return ((0.0, high, False, True), (low + 90.0, 90.0, True, False))
    if high > 90.0:
        return ((0.0, high - 90.0, False, True), (low, 90.0, True, False))
    return ((low, high, True, True),)


def repository_face(
    kind: str,
    r0: float,
    r1: float,
    phi0: float,
    phi1: float,
    z0: float,
    z1: float,
    sign: int,
    body: str,
) -> Any:
    """Create one repository-native surface panel; input angles are degrees."""
    if kind not in ("horizontal", "radial", "azimuthal"):
        raise ValueError(f"Unknown face kind: {kind}")
    if sign not in (-1, 1) or body not in ("rotor", "stator"):
        raise ValueError("Invalid face normal or body")
    p0, p1 = math.radians(phi0), math.radians(phi1)
    if kind == "horizontal":
        panel_kind = f"{body}_{'bottom' if sign < 0 else 'top'}"
        return _horizontal(r0, r1, p0, p1, z0, sign, panel_kind, body)
    if kind == "radial":
        return _radial(r0, p0, p1, z0, z1, sign, f"{body}_radial_wall", body)
    return _azimuthal(
        r0, r1, p0, z0, z1, sign, f"{body}_azimuthal_wall", body,
    )


def validate_design(design: StudyDesign) -> None:
    for item in dataclasses.fields(design):
        value = getattr(design, item.name)
        if isinstance(value, float):
            finite(value, item.name)
    if not design.tracks:
        raise ValueError("A design must contain at least one track")
    if not 0.0 < design.R_min < design.R_max:
        raise ValueError("Invalid radial envelope")
    if not 0.0 < design.aperture_arc_deg < 90.0:
        raise ValueError("Invalid aperture angle")
    if not 0.0 < design.tooth_arc_deg < design.aperture_arc_deg:
        raise ValueError("Tooth must fit inside the aperture sector")
    if design.t_membrane <= 0.0 or design.t_landing_pad <= 0.0:
        raise ValueError("Stator thicknesses must be positive")
    previous = design.R_min
    for track in design.tracks:
        for item in dataclasses.fields(track):
            finite(getattr(track, item.name), item.name)
        if not (
            previous <= track.r_inner < track.r_tooth_in
            < track.r_tooth_out < track.r_outer <= design.R_max
        ):
            raise ValueError(f"Overlapping or invalid track in {design.name}")
        if track.h_teeth <= 0.0 or track.level < 1:
            raise ValueError("Invalid tooth height or fractal level")
        previous = track.r_outer


def subdivisions(low: float, high: float, count: int) -> np.ndarray:
    if high <= low:
        raise ValueError("Subdivision interval must have positive length")
    return np.linspace(low, high, count + 1, dtype=float)


def make_track_element(track: TrackSpec3D) -> TrackElement:
    values = dataclasses.asdict(track)
    values.update(aliases(track.level, "generation", "depth"))
    values.update(aliases(track.r_tooth_out - track.r_tooth_in, "tooth_width", "w_tooth"))
    values.update(aliases(track.r_outer - track.r_inner, "slot_width", "width"))
    return invoke(TrackElement, values)


def panel_components(panel: Any) -> tuple[Any, Any, Any]:
    if isinstance(panel, (tuple, list)) and len(panel) in (3, 4):
        return panel[0], panel[1], panel[2]
    return (
        field_value(panel, "center", "centroid", "center_um", "centroid_um"),
        field_value(panel, "normal", "unit_normal"),
        field_value(panel, "area", "area_um2"),
    )


def make_mesh(
    geometry: Geometry,
    panels: list[Any],
    bodies: list[str],
    theta_deg: float,
    delta_z_rotor: float,
    *,
    panel_resolution: Mapping[str, int] | None = None,
) -> ClutchSurfaceMesh:
    if len(panels) != len(bodies):
        raise ValueError("Panel and body counts must match")
    if not panels or any(body not in ("rotor", "stator") for body in bodies):
        raise ValueError("Mesh requires panels with valid body labels")
    parameters = {
        "material": "Gold",
        "R_min": geometry.R_min,
        "R_max": geometry.R_max,
        "z_tip": geometry.z_tip,
        "h_teeth": geometry.h_teeth,
        "t_membrane": geometry.t_membrane,
        "t_landing_pad": geometry.t_landing_pad,
        "theta_deg": theta_deg,
        "tooth_arc_deg": geometry.tooth_arc_deg,
        "aperture_arc_deg": geometry.aperture_arc_deg,
        "elements": [dataclasses.asdict(e) for e in geometry.elements],
    }
    return ClutchSurfaceMesh(
        rotor=tuple(p for p, body in zip(panels, bodies) if body == "rotor"),
        stator=tuple(p for p, body in zip(panels, bodies) if body == "stator"),
        geometry=geometry,
        parameters=parameters,
        config=dict(parameters),
        panel_resolution=dict(panel_resolution) if panel_resolution is not None else {
            "n_r": 1, "n_phi_tooth": 2, "n_phi_bridge": 2, "n_z": 2,
        },
    )


def build_study_clutch_mesh(
    design: StudyDesign,
    theta_deg: float,
    delta_z_rotor: float = 0.0,
    n_r: int = 1,
    n_phi_tooth: int = 2,
    n_phi_bridge: int = 2,
    n_z: int = 2,
) -> ClutchSurfaceMesh:
    """Build one periodic 90-degree sector, with no artificial seam caps."""
    validate_design(design)
    theta_deg = finite(theta_deg, "theta_deg")
    delta_z_rotor = finite(delta_z_rotor, "delta_z_rotor")
    for name, count in (
        ("n_r", n_r), ("n_phi_tooth", n_phi_tooth),
        ("n_phi_bridge", n_phi_bridge), ("n_z", n_z),
    ):
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError(f"{name} must be a positive integer")

    rotor: list[Any] = []
    stator: list[Any] = []

    def emit(
        kind: str, r0: float, r1: float, p0: float, p1: float,
        z0: float, z1: float, sign: int, body: str,
    ) -> None:
        # The meshing grids use radians; repository_face retains its degree API.
        panel = repository_face(
            kind, r0, r1, math.degrees(p0), math.degrees(p1),
            z0, z1, sign, body,
        )
        (rotor if body == "rotor" else stator).append(panel)

    for track in design.tracks:
        re = subdivisions(track.r_tooth_in, track.r_tooth_out, n_r)
        ze = subdivisions(
            track.z_tip + delta_z_rotor,
            track.z_tip + track.h_teeth + delta_z_rotor,
            n_z,
        )
        for low_deg, high_deg, cap_low, cap_high in tooth_segments(
            theta_deg, design.tooth_arc_deg,
        ):
            low_phi, high_phi = math.radians(low_deg), math.radians(high_deg)
            pe = subdivisions(low_phi, high_phi, n_phi_tooth)
            for i in range(n_r):
                for j in range(n_phi_tooth):
                    emit("horizontal", re[i], re[i + 1], pe[j], pe[j + 1],
                         ze[0], ze[0], -1, "rotor")
                    emit("horizontal", re[i], re[i + 1], pe[j], pe[j + 1],
                         ze[-1], ze[-1], 1, "rotor")
            for j in range(n_phi_tooth):
                for k in range(n_z):
                    emit("radial", re[0], re[0], pe[j], pe[j + 1],
                         ze[k], ze[k + 1], -1, "rotor")
                    emit("radial", re[-1], re[-1], pe[j], pe[j + 1],
                         ze[k], ze[k + 1], 1, "rotor")
            for i in range(n_r):
                for k in range(n_z):
                    if cap_low:
                        emit("azimuthal", re[i], re[i + 1], pe[0], pe[0],
                             ze[k], ze[k + 1], -1, "rotor")
                    if cap_high:
                        emit("azimuthal", re[i], re[i + 1], pe[-1], pe[-1],
                             ze[k], ze[k + 1], 1, "rotor")

    radial_boundaries = [design.R_min]
    for track in design.tracks:
        radial_boundaries.extend((track.r_inner, track.r_outer))
    radial_boundaries.append(design.R_max)
    if np.any(np.diff(radial_boundaries) <= 0.0):
        raise ValueError("Stator requires strictly increasing radial boundaries")

    radial_edges: list[float] = [radial_boundaries[0]]
    interval_ids: list[int] = []
    for interval, (low, high) in enumerate(zip(radial_boundaries, radial_boundaries[1:])):
        radial_edges.extend(subdivisions(low, high, n_r)[1:].tolist())
        interval_ids.extend([interval] * n_r)

    angles = np.deg2rad(np.concatenate((
        np.linspace(0.0, design.aperture_arc_deg, n_phi_tooth + 1),
        np.linspace(design.aperture_arc_deg, 90.0, n_phi_bridge + 1)[1:],
    )))
    heights = np.concatenate((
        np.linspace(
            design.z_pad_top - design.t_landing_pad, design.z_pad_top, n_z + 1,
        ),
        np.linspace(-design.t_membrane, 0.0, n_z + 1),
    ))
    # A shared, sorted grid avoids duplicate interior faces and also handles
    # touching or overlapping membrane and landing-pad height ranges.
    heights = np.unique(heights)
    ni, nj, nk = len(interval_ids), len(angles) - 1, len(heights) - 1

    def filled(i: int, j: int, k: int) -> bool:
        if i < 0 or i >= ni or k < 0 or k >= nk:
            return False
        j %= nj
        midpoint = (heights[k] + heights[k + 1]) / 2.0
        if j < n_phi_tooth:
            return (
                interval_ids[i] % 2 == 0
                and -design.t_membrane < midpoint < 0.0
            )
        return (
            design.z_pad_top - design.t_landing_pad
            < midpoint < design.z_pad_top
        )

    for i in range(ni):
        for j in range(nj):
            for k in range(nk):
                if not filled(i, j, k):
                    continue
                r0, r1 = radial_edges[i:i + 2]
                p0, p1 = angles[j:j + 2]
                z0, z1 = heights[k:k + 2]
                if not filled(i, j, k - 1):
                    emit("horizontal", r0, r1, p0, p1, z0, z0, -1, "stator")
                if not filled(i, j, k + 1):
                    emit("horizontal", r0, r1, p0, p1, z1, z1, 1, "stator")
                if not filled(i - 1, j, k):
                    emit("radial", r0, r0, p0, p1, z0, z1, -1, "stator")
                if not filled(i + 1, j, k):
                    emit("radial", r1, r1, p0, p1, z0, z1, 1, "stator")
                if not filled(i, j - 1, k):
                    emit("azimuthal", r0, r1, p0, p0, z0, z1, -1, "stator")
                if not filled(i, j + 1, k):
                    emit("azimuthal", r0, r1, p1, p1, z0, z1, 1, "stator")

    track_elements = tuple(make_track_element(t) for t in design.tracks)
    geometry = Geometry(
        R_min=design.R_min,
        R_max=design.R_max,
        z_tip=min(t.z_tip + delta_z_rotor for t in design.tracks),
        h_teeth=max(t.h_teeth for t in design.tracks),
        t_membrane=design.t_membrane,
        t_landing_pad=design.t_landing_pad,
        theta_deg=theta_deg,
        tooth_arc_deg=design.tooth_arc_deg,
        aperture_arc_deg=design.aperture_arc_deg,
        elements=track_elements,
    )
    return make_mesh(
        geometry, rotor + stator,
        ["rotor"] * len(rotor) + ["stator"] * len(stator),
        theta_deg, delta_z_rotor,
        panel_resolution={
            "n_r": n_r,
            "n_phi_tooth": n_phi_tooth,
            "n_phi_bridge": n_phi_bridge,
            "n_z": n_z,
        },
    )


def build_designs() -> tuple[StudyDesign, ...]:
    raw = get_scoped_clutch_elements(
        N=2, R_min=0.30, R_max=1.35, w1_ratio=0.65, min_tooth_w=0.020,
    )
    if isinstance(raw, Mapping):
        raw = field_value(raw, "tracks", "elements", "clutch_elements")
    elif hasattr(raw, "tracks"):
        raw = raw.tracks
    elements = sorted(tuple(raw), key=lambda t: finite(field_value(t, "r_inner"), "r_inner"))
    if len(elements) != 3:
        raise ValueError("Scoped N=2 geometry must return exactly three Cantor tracks")
    base = tuple(
        TrackSpec3D(
            r_inner=finite(field_value(t, "r_inner"), "r_inner"),
            r_outer=finite(field_value(t, "r_outer"), "r_outer"),
            r_tooth_in=finite(field_value(t, "r_tooth_in"), "r_tooth_in"),
            r_tooth_out=finite(field_value(t, "r_tooth_out"), "r_tooth_out"),
            z_tip=-0.100,
            h_teeth=0.100,
            level=(2, 1, 2)[i],
        )
        for i, t in enumerate(elements)
    )
    slot_widths = [t.r_outer - t.r_inner for t in base]
    tooth_widths = [t.r_tooth_out - t.r_tooth_in for t in base]
    ribs = [
        base[0].r_inner - 0.30,
        base[1].r_inner - base[0].r_outer,
        base[2].r_inner - base[1].r_outer,
        1.35 - base[2].r_outer,
    ]
    total_slot, total_tooth = math.fsum(slot_widths), math.fsum(tooth_widths)
    midpoint = (0.30 + 1.35) / 2.0
    single = (
        TrackSpec3D(
            midpoint - total_slot / 2.0, midpoint + total_slot / 2.0,
            midpoint - total_tooth / 2.0, midpoint + total_tooth / 2.0,
            -0.100, 0.100,
        ),
    )

    def arrange(
        slots: Sequence[tuple[float, float, int]], rib_widths: Sequence[float],
    ) -> tuple[TrackSpec3D, ...]:
        if len(rib_widths) != len(slots) + 1:
            raise ValueError("Incorrect number of stator ribs")
        cursor = 0.30 + rib_widths[0]
        output: list[TrackSpec3D] = []
        for i, (slot_width, tooth_width, level) in enumerate(slots):
            center = cursor + slot_width / 2.0
            output.append(TrackSpec3D(
                cursor, cursor + slot_width,
                center - tooth_width / 2.0, center + tooth_width / 2.0,
                -0.100, 0.100, level,
            ))
            cursor += slot_width + rib_widths[i + 1]
        if not math.isclose(cursor, 1.35, abs_tol=1e-12):
            raise ValueError("Control construction failed to preserve radial envelope")
        return tuple(output)

    periodic = arrange(
        [(total_slot / 3.0, total_tooth / 3.0, 1)] * 3,
        [(1.05 - total_slot) / 4.0] * 4,
    )
    order = sorted(range(3), key=lambda i: (slot_widths[i], i))
    monotonic = arrange(
        [(slot_widths[i], tooth_widths[i], base[i].level) for i in order],
        sorted(ribs),
    )

    def design(name: str, category: str, description: str,
               tracks: tuple[TrackSpec3D, ...]) -> StudyDesign:
        result = StudyDesign(
            name, category, description, 0.30, 1.35, 36.0, 15.0,
            0.025, 0.150, -0.115, tracks,
        )
        validate_design(result)
        return result

    designs = (
        design("Cantor_FlatZ", "fractal_radial", "Cantor N=2, uniform vertical geometry.", base),
        design(
            "Cantor_RZ_ScaleMatched", "mechanism_2",
            "Coupled radial/vertical scales; all tooth tops flush at z=0.",
            tuple(dataclasses.replace(
                t, z_tip=(-0.085, -0.110, -0.085)[i],
                h_teeth=(0.085, 0.110, 0.085)[i],
            ) for i, t in enumerate(base)),
        ),
        design(
            "Cantor_Z_Staircase", "mechanism_1",
            "Staggered tips and tops for a potentially broader repulsion window.",
            tuple(dataclasses.replace(
                t, z_tip=(-0.075, -0.112, -0.100)[i],
                h_teeth=(0.075, 0.082, 0.085)[i],
            ) for i, t in enumerate(base)),
        ),
        design("Ctrl_SingleWide", "control_A", "Single equal-total-width slot and tooth.", single),
        design("Ctrl_UniformPeriodic", "control_B", "Three uniform slots with four equal ribs.", periodic),
        design(
            "Ctrl_SizeMatched_Monotonic", "control_C",
            "Exact width multisets, slots and ribs ordered narrow-to-wide.", monotonic,
        ),
    )
    for d in designs:
        if not math.isclose(
            math.fsum(t.r_outer - t.r_inner for t in d.tracks), total_slot, abs_tol=1e-12,
        ) or not math.isclose(
            math.fsum(t.r_tooth_out - t.r_tooth_in for t in d.tracks),
            total_tooth, abs_tol=1e-12,
        ):
            raise ValueError("Matched-width invariant failed")
        if any(t.z_tip <= d.z_pad_top for t in d.tracks):
            raise ValueError("Nominal rotor tip intersects the landing pad")
    return designs


def active_geometry(design: StudyDesign) -> tuple[float, float]:
    """Fourfold total horizontal tooth area and plan-view edge perimeter."""
    angle = math.radians(design.tooth_arc_deg)
    area = 4.0 * math.fsum(
        0.5 * angle * (t.r_tooth_out**2 - t.r_tooth_in**2) for t in design.tracks
    )
    perimeter = 4.0 * math.fsum(
        angle * (t.r_tooth_out + t.r_tooth_in)
        + 2.0 * (t.r_tooth_out - t.r_tooth_in)
        for t in design.tracks
    )
    if area <= 0.0 or perimeter <= 0.0:
        raise ValueError("Nonpositive active area or edge perimeter")
    return area, perimeter


def extract_force_pN(result: Any) -> float:
    """Require a labelled force; never infer units from numerical magnitude."""
    for names, multiplier in (
        (("f_net_pN", "F_z_pN", "Fz_pN", "force_z_pN", "vertical_force_pN"), 1.0),
        (("f_net_N", "F_z_N", "Fz_N", "force_z_N", "vertical_force_N"), 1e12),
    ):
        for name in names:
            if (isinstance(result, Mapping) and name in result) or hasattr(result, name):
                return finite(finite(field_value(result, name), name) * multiplier, name)
    for name, multiplier in (("force_pN", 1.0), ("force_N", 1e12), ("forces_N", 1e12)):
        if (isinstance(result, Mapping) and name in result) or hasattr(result, name):
            value = field_value(result, name)
            if isinstance(value, torch.Tensor):
                value = value.detach().cpu().numpy()
            array = np.asarray(value)
            if array.shape == (3,):
                return finite(finite(array[2], name) * multiplier, name)
    if isinstance(result, Mapping):
        for key in ("metrics", "results", "observables", "forces"):
            if key in result and isinstance(result[key], Mapping):
                try:
                    return extract_force_pN(result[key])
                except KeyError:
                    continue
    raise KeyError(
        "BEM result contains no recognized unit-labelled vertical force; "
        "expected f_net_pN, f_net_N, F_z_pN, F_z_N, "
        "or a three-component force_N/force_pN."
    )


def record_step(step: int, name: str, data: Mapping[str, Any]) -> None:
    log_step(
        f"{name}_{step}",
        data=dict(data),
        solver_name="bem",
        solver_parameters=SOLVER_PROVENANCE,
    )


def record_metric(name: str, value: float, unit: str, context: Mapping[str, Any]) -> None:
    value = finite(value, name)
    step_id = context.get("step_id", name)
    log_metric(
        str(name),
        value=float(value),
        step_id=str(step_id),
        solver_name="bem",
        solver_parameters=SOLVER_PROVENANCE,
    )


def positive_window(points: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """Integrate the positive part of the piecewise-linear force interpolant."""
    if len(points) < 2:
        raise ValueError("At least two sweep samples are required")
    ordered = sorted((finite(x, "delta_z"), finite(y, "force")) for x, y in points)
    if any(b[0] <= a[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Sweep coordinates must be distinct")
    width = 0.0
    work_pN_um = 0.0
    intervals: list[list[float]] = []
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if y0 <= 0.0 and y1 <= 0.0:
            continue
        left, right = x0, x1
        fleft, fright = max(y0, 0.0), max(y1, 0.0)
        if y0 < 0.0 < y1:
            left = x0 + (x1 - x0) * (-y0) / (y1 - y0)
        elif y1 < 0.0 < y0:
            right = x0 + (x1 - x0) * y0 / (y0 - y1)
        length = right - left
        if length <= 0.0:
            continue
        width += length
        work_pN_um += 0.5 * (fleft + fright) * length
        if intervals and math.isclose(intervals[-1][1], left, abs_tol=1e-12):
            intervals[-1][1] = right
        else:
            intervals.append([left, right])
    return {
        "peak_repulsive_force_pN": max(y for _, y in ordered),
        "repulsive_window_width_um": width,
        "repulsive_work_fN_um": work_pN_um * 1000.0,
        "positive_intervals_um": intervals,
        "window_left_censored": ordered[0][1] > 0.0,
        "window_right_censored": ordered[-1][1] > 0.0,
    }


def summaries(
    designs: Sequence[StudyDesign], records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    switching: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    for design in designs:
        a = [r for r in records if r["design"] == design.name and r["experiment"] == "A"]
        forces = {r["theta_deg"]: r["F_z_pN"] for r in a}
        if 3.0 in forces and 48.0 in forces:
            rep, att = forces[3.0], forces[48.0]
            area, perimeter = active_geometry(design)
            entry: dict[str, Any] = {
                "design": design.name,
                "F_rep_pN": rep,
                "F_att_pN": att,
                "Delta_F_pN": rep - att,
                "switching_ratio": abs(att) / max(rep, 1e-9),
                "active_tooth_area_um2": area,
                "edge_perimeter_um": perimeter,
                "repulsive_at_disengagement": rep > 0.0,
                "attractive_at_engagement": att < 0.0,
            }
            for key, force in (("F_rep", rep), ("F_att", att), ("Delta_F", rep - att)):
                entry[f"{key}_pN_per_um2"] = force / area
                entry[f"{key}_pN_per_um"] = force / perimeter
            switching.append(entry)
        b = [
            (r["delta_z_rotor_um"], r["F_z_pN"]) for r in records
            if r["design"] == design.name and r["experiment"] == "B"
        ]
        if len(b) == len(DZ_VALUES):
            windows.append({"design": design.name, **positive_window(b)})
    return switching, windows


def export_report(report: Mapping[str, Any]) -> None:
    temporary = REPORT_JSON.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    temporary.replace(REPORT_JSON)
    lines = [
        "# Optimal Fractal Advantage: grounded BEM study",
        "",
        f"- Status: **{report['status']}**",
        f"- Formulation: `{report['configuration']['formulation']}`",
        f"- Device: `{report['configuration']['resolved_device']}`",
        f"- Completed tasks: {len(report['samples'])}/{report['planned_tasks']}",
        "- Positive vertical force denotes repulsion.",
        "- Window widths and work are restricted to the sampled displacement interval.",
        "- Work integrates the positive piecewise-linear force, inserting zero crossings.",
        "- These finite-resolution results do not establish mathematical optimality.",
        "- Area means horizontal tooth footprint; perimeter means its plan-view boundary.",
        "",
        "## Experiment A",
        "",
        "| Design | Disengaged (pN) | Engaged (pN) | Swing (pN) | Ratio |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in report["switching"]:
        lines.append(
            f"| {item['design']} | {item['F_rep_pN']:.6g} | "
            f"{item['F_att_pN']:.6g} | {item['Delta_F_pN']:.6g} | "
            f"{item['switching_ratio']:.6g} |"
        )
    if not report["switching"]:
        lines.append("\nNot completed: micro-probe results are not a switching comparison.")
    lines.extend([
        "", "## Experiment B", "",
        "| Design | Peak (pN) | Window (um) | Work (fN um = aJ) | Censored |",
        "|---|---:|---:|---:|---|",
    ])
    for item in report["windows"]:
        censored = item["window_left_censored"] or item["window_right_censored"]
        lines.append(
            f"| {item['design']} | {item['peak_repulsive_force_pN']:.6g} | "
            f"{item['repulsive_window_width_um']:.6g} | "
            f"{item['repulsive_work_fN_um']:.6g} | {censored} |"
        )
    if not report["windows"]:
        lines.append("\nNot completed: no broadband-window claim can be made.")
    if report.get("error"):
        lines.extend(["", "## Failure", "", str(report["error"])])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_report(report: Mapping[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    switching = report["switching"]
    if switching:
        x = np.arange(len(switching))
        axes[0].bar(x - 0.18, [s["F_rep_pN"] for s in switching], 0.36,
                    label="Disengaged, 3°")
        axes[0].bar(x + 0.18, [s["F_att_pN"] for s in switching], 0.36,
                    label="Engaged, 48°")
        axes[0].set_xticks(x, [s["design"] for s in switching], rotation=40, ha="right")
        axes[0].legend()
    else:
        samples = [s for s in report["samples"] if s["experiment"] == "A"]
        if samples:
            axes[0].bar([0], [samples[0]["F_z_pN"]])
            axes[0].set_xticks([0], [f"{samples[0]['design']}\n3° micro-probe"])
        axes[0].text(0.5, 0.95, "Incomplete comparison", transform=axes[0].transAxes,
                     ha="center", va="top")
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set_ylabel("Vertical force (pN)")
    axes[0].set_title("A · Switching and matched controls")

    plotted = False
    for name in WINDOW_DESIGNS:
        samples = sorted(
            (s for s in report["samples"] if s["experiment"] == "B" and s["design"] == name),
            key=lambda s: s["delta_z_rotor_um"],
        )
        if samples:
            axes[1].plot(
                [s["delta_z_rotor_um"] for s in samples],
                [s["F_z_pN"] for s in samples],
                marker="o", label=name,
            )
            plotted = True
    if plotted:
        axes[1].legend(fontsize=8)
    else:
        axes[1].text(0.5, 0.5, "Sweep not executed", transform=axes[1].transAxes,
                     ha="center", va="center")
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_xlabel("Rotor vertical displacement (um)")
    axes[1].set_ylabel("Vertical force at 3° (pN)")
    axes[1].set_title("B · Sampled vertical repulsion window")
    metric_keys_list = [
        f"fractal_{sample['design']}_{sample['experiment']}_{index}_F_z_pN"
        for index, sample in enumerate(report["samples"], start=1)
    ]
    metric_keys_list.extend(
        f"fractal_{entry['design']}_Delta_F_pN" for entry in report["switching"]
    )
    metric_keys_list.extend(
        f"fractal_{entry['design']}_repulsive_window_width_um"
        for entry in report["windows"]
    )
    try:
        for suffix in (".png", ".pdf"):
            path = FIGURE_STEM.with_suffix(suffix)
            fig.savefig(path, dpi=180)
            save_plot_provenance(
                str(path),
                str(RESULTS / "provenance_metrics.json"),
                metric_keys_list,
                solver_name="bem",
                solver_parameters=SOLVER_PROVENANCE,
            )
    finally:
        plt.close(fig)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--max-steps", type=int, default=0)
    result.add_argument(
        "--formulation", choices=("vector_dyadic", "scalar_yukawa"),
        default="vector_dyadic",
    )
    result.add_argument("--n-r", type=int, default=1)
    result.add_argument("--n-phi-tooth", type=int, default=2)
    result.add_argument("--n-phi-bridge", type=int, default=2)
    result.add_argument("--n-z", type=int, default=2)
    result.add_argument("--n-xi", type=int, default=16)
    result.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return result


def main() -> int:
    argument_parser = parser()
    args = argument_parser.parse_args()
    if args.max_steps < 0:
        argument_parser.error("--max-steps cannot be negative")
    for name in ("n_r", "n_phi_tooth", "n_phi_bridge", "n_z", "n_xi"):
        if getattr(args, name) < 1:
            argument_parser.error(f"--{name.replace('_', '-')} must be positive")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.device != "auto":
        device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        argument_parser.error("--device cuda requested but CUDA is unavailable")

    os.chdir(REPOSITORY_ROOT)
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    micro = 0 < args.max_steps <= 10
    configuration = {**vars(args), "resolved_device": device, "micro_probe": micro}
    provenance = {
        "solver": "execution.casimir_bem_solver.run_bem_casimir_solver",
        "formulation": args.formulation,
        "device": device,
        "n_r": args.n_r,
        "n_phi_tooth": args.n_phi_tooth,
        "n_phi_bridge": args.n_phi_bridge,
        "n_z": args.n_z,
        "n_xi": args.n_xi,
        "max_steps": args.max_steps,
        "geometry_units": "um",
        "force_units": "pN",
    }
    SOLVER_PROVENANCE.clear()
    SOLVER_PROVENANCE.update(provenance)
    set_solver_provenance(
        "bem", {"formulation": args.formulation, "n_xi": args.n_xi},
    )

    designs = build_designs()
    by_name = {d.name: d for d in designs}
    tasks = [
        Task(d, angle, 0.0, "A") for d in designs for angle in (3.0, 48.0)
    ] + [
        Task(by_name[name], 3.0, dz, "B") for name in WINDOW_DESIGNS for dz in DZ_VALUES
    ]
    selected = tasks[:1] if micro else tasks
    records: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "configuration": configuration,
        "designs": [dataclasses.asdict(d) for d in designs],
        "planned_tasks": len(tasks),
        "selected_tasks": len(selected),
        "samples": records,
        "switching": [],
        "windows": [],
        "limitations": [
            "No mesh or imaginary-frequency convergence claim is made.",
            "Window and work are restricted to [-0.060, 0.040] um.",
            "Positive endpoint forces imply a censored repulsion window.",
            "Micro-probes are pipeline checks, not physical evidence of advantage.",
            "A wall-clock bound depends on repository solver and available hardware.",
        ],
    }
    record_step(0, "study_configuration", configuration)

    for index, task in enumerate(selected, start=1):
        mesh = build_study_clutch_mesh(
            task.design, task.theta_deg, task.delta_z_rotor,
            args.n_r, args.n_phi_tooth, args.n_phi_bridge, args.n_z,
        )
        task_id = f"fractal_{task.design.name}_{task.experiment}_{index}"
        context = {
            "design": task.design.name,
            "experiment": task.experiment,
            "theta_deg": task.theta_deg,
            "delta_z_rotor_um": task.delta_z_rotor,
            "formulation": args.formulation,
            "micro_probe": micro,
            "step_id": task_id,
        }
        task_start = time.monotonic()
        result = run_bem_casimir_solver(
            mesh.parameters,
            n_r=args.n_r,
            n_phi_tooth=args.n_phi_tooth,
            n_phi_bridge=args.n_phi_bridge,
            n_z=args.n_z,
            n_xi=args.n_xi,
            max_steps=args.max_steps,
            device=device,
            task_id=task_id,
            mesh=mesh,
            record_metrics=True,
            formulation=args.formulation,
        )
        force = finite(extract_force_pN(result), "F_z_pN")
        area, perimeter = active_geometry(task.design)
        record = {
            **context,
            "F_z_pN": force,
            "F_z_pN_per_um2": force / area,
            "F_z_pN_per_um": force / perimeter,
            "active_tooth_area_um2": area,
            "edge_perimeter_um": perimeter,
            "elapsed_seconds": time.monotonic() - task_start,
        }
        records.append(record)
        prefix = task_id
        for key, unit in (
            ("F_z_pN", "pN"), ("F_z_pN_per_um2", "pN/um^2"),
            ("F_z_pN_per_um", "pN/um"), ("active_tooth_area_um2", "um^2"),
            ("edge_perimeter_um", "um"), ("elapsed_seconds", "s"),
        ):
            record_metric(f"{prefix}_{key}", record[key], unit, context)
        record_step(index, "bem_task_completed", record)
        report["switching"], report["windows"] = summaries(designs, records)
        export_report(report)

    report["status"] = "micro_probe_complete" if micro else "complete"
    report["elapsed_seconds"] = time.monotonic() - start
    for group in ("switching", "windows"):
        for entry in report[group]:
            for key, value in entry.items():
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    unit = (
                        "fN um" if key.endswith("fN_um") else
                        "pN/um^2" if key.endswith("pN_per_um2") else
                        "pN/um" if key.endswith("pN_per_um") else
                        "pN" if key.endswith("pN") else
                        "um^2" if key.endswith("um2") else
                        "um" if key.endswith("um") else "1"
                    )
                    record_metric(
                        f"fractal_{entry['design']}_{key}", float(value), unit,
                        {
                            "experiment": group,
                            "design": entry["design"],
                            "step_id": f"fractal_{entry['design']}_{group}",
                        },
                    )
    record_step(len(selected) + 1, "study_completed", {
        "status": report["status"],
        "completed_tasks": len(records),
        "elapsed_seconds": report["elapsed_seconds"],
    })
    export_report(report)
    export_macros(output_path=str(RESULTS / "macros_results.tex"))
    for required in (
        RESULTS / "provenance_metrics.json", RESULTS / "macros_results.tex",
    ):
        if not required.is_file() or required.stat().st_size == 0:
            raise RuntimeError("[ERROR: RUN_DATA_MISSING]")
    plot_report(report)
    report["elapsed_seconds"] = time.monotonic() - start
    export_report(report)
    print(
        f"{report['status']}: {len(records)} BEM task(s), "
        f"{report['elapsed_seconds']:.2f} s; report: {REPORT_JSON}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
