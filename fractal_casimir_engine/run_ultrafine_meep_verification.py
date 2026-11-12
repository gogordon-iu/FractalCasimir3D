#!/usr/bin/env python3
"""Suite 2 (eng_uf2): Independent Full-Wave 3D Meep FDTD Casimir Stress Tensor Verification.

Zero-BEM-assumption volumetric 3D FDTD verification of BOTH axial Casimir force F_z
and azimuthal Casimir torque tau_theta across all 8 canonical benchmark states
(4 engine architectures x {Stroke I repulsive, Stroke III attractive}) on BigRed 200.

Key physics & numerical guarantees:
  1. 4-pass Casimir inclusion-exclusion (both - rotor - stator + vac) using Meep's
     exact time-domain Casimir kernel ``make_casimir_gfunc`` and cosine-mode stress
     projections ``casimir_stress_dct_integral``.
  2. Co-rotating per-tooth coordinate frames (global rotation -(theta + vernier_k))
     so each Cantor tooth k sits symmetrically on the +x axis at R_k, maximizing
     Cartesian Yee-grid vacuum clearance and aligning +y identically with +theta_hat_k.
  3. Simultaneous extraction of mp.Z (F_{z,k}) and mp.Y (F_{theta,k} -> tau_k = R_k * F_{y,k})
     in a single FDTD pass with native C++ ``mp.Prism`` sub-wedges.
  4. Resumable per-moment/per-shard checkpoints + walltime exit code 75 for Slurm
     ``--auto-resubmit``.
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from execution.materials_database_dispersive import (
    EV_TO_MEEP_FREQ,
    GOLD_EPS_INF,
    GOLD_GAMMA_EV,
    GOLD_WP_EV,
    MEEP_FORCE_TO_SI,
)
from fractal_casimir_engine import ENGINE_DESIGN_NAMES
from fractal_casimir_engine.bem_cycle_solver import PreparedEngineBemModel
from fractal_casimir_engine.geometries import (
    CurvilinearPrism,
    SECTOR_DEG,
    build_engine_prisms,
    prism_to_meep_subwedges,
)
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

ENGINE_DIR = PROJECT_ROOT / "fractal_casimir_engine"
UF_RESULTS_DIR = ENGINE_DIR / "results" / "ultrafine"
ENGINE_FIGURES_DIR = ENGINE_DIR / "figures"

ALL_CONFIGS: tuple[str, ...] = ("both", "rotor", "stator", "vac")
DIMLESS_TO_PN: float = float(MEEP_FORCE_TO_SI) * 1.0e12

# Canonical 8-task matrix (1-indexed for Slurm --array=1-8)
MEEP_BENCHMARK_TASKS: tuple[dict[str, Any], ...] = (
    {"task_id": 1, "design_name": "Sym_Baseline_CantorN2", "stroke": "Stroke_I_Repulsive", "z_tip_um": -0.092, "theta_deg": 22.0},
    {"task_id": 2, "design_name": "Sym_Baseline_CantorN2", "stroke": "Stroke_III_Attractive", "z_tip_um": -0.084, "theta_deg": 64.0},
    {"task_id": 3, "design_name": "Config_B_Manhattan_Vernier", "stroke": "Stroke_I_Repulsive", "z_tip_um": -0.092, "theta_deg": 22.0},
    {"task_id": 4, "design_name": "Config_B_Manhattan_Vernier", "stroke": "Stroke_III_Attractive", "z_tip_um": -0.084, "theta_deg": 64.0},
    {"task_id": 5, "design_name": "Config_C_Helical_Turbine", "stroke": "Stroke_I_Repulsive", "z_tip_um": -0.092, "theta_deg": 22.0},
    {"task_id": 6, "design_name": "Config_C_Helical_Turbine", "stroke": "Stroke_III_Attractive", "z_tip_um": -0.084, "theta_deg": 64.0},
    {"task_id": 7, "design_name": "Config_D_DualStator_PushPull", "stroke": "Stroke_I_Repulsive", "z_tip_um": -0.092, "theta_deg": 22.0},
    {"task_id": 8, "design_name": "Config_D_DualStator_PushPull", "stroke": "Stroke_III_Attractive", "z_tip_um": -0.084, "theta_deg": 64.0},
)


@dataclasses.dataclass(frozen=True)
class ToothStressFace:
    """Single planar Cartesian face of a co-rotating per-tooth Maxwell stress box."""

    name: str
    tooth_index: int
    r_lever_um: float
    rot_deg: float
    axis: int  # 0 -> x, 1 -> y, 2 -> z
    orientation: float  # +1.0 outward along +axis, -1.0 outward along -axis
    center: tuple[float, float, float]
    size: tuple[float, float, float]

    @property
    def tangent_axes(self) -> tuple[int, int]:
        axes = tuple(a for a in range(3) if a != self.axis)
        return axes[0], axes[1]


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _sample_prism_volume_points(
    prism: CurvilinearPrism,
    *,
    rot_deg: float,
    nu: int = 7,
    nv: int = 19,
    nw: int = 7,
) -> np.ndarray:
    us = np.linspace(0.0, 1.0, nu)
    vs = np.linspace(0.0, 1.0, nv)
    ws = np.linspace(0.0, 1.0, nw)
    pts = np.array(
        [prism.point(float(u), float(v), float(w)) for u in us for v in vs for w in ws],
        dtype=np.float64,
    )
    rad = math.radians(rot_deg)
    c, s = math.cos(rad), math.sin(rad)
    rmat = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return pts @ rmat.T


def build_and_certify_stress_faces(
    design_name: str,
    z_tip_um: float,
    theta_deg: float,
    *,
    min_box_clearance_um: float = 0.0045,
) -> tuple[list[ToothStressFace], dict[str, Any]]:
    """Construct certified vacuum-isolated co-rotating 6-face stress boxes for all 3 Cantor teeth."""
    rotor_s0, stator_s0, tracks, _ = build_engine_prisms(
        design_name, z_tip_um=z_tip_um, theta_deg=theta_deg
    )

    faces: list[ToothStressFace] = []
    box_diagnostics: list[dict[str, Any]] = []

    for k, tr in enumerate(tracks):
        rot_deg = -(float(theta_deg) + float(tr.vernier_deg))
        r_lever = 0.5 * (tr.r_tooth_in + tr.r_tooth_out)
        tooth_prism = rotor_s0[k]
        tooth_pts = _sample_prism_volume_points(tooth_prism, rot_deg=rot_deg, nu=9, nv=25, nw=9)

        tx0, ty0, tz0 = (float(x) for x in np.min(tooth_pts, axis=0))
        tx1, ty1, tz1 = (float(x) for x in np.max(tooth_pts, axis=0))

        # Collect dense points from ALL other bodies (all 4 stator sectors + other rotor teeth)
        ext_chunks: list[np.ndarray] = []
        for sec in range(4):
            sec_rot = rot_deg + sec * SECTOR_DEG
            for sp in stator_s0:
                ext_chunks.append(_sample_prism_volume_points(sp, rot_deg=sec_rot, nu=7, nv=25, nw=7))
            for r_idx, rp in enumerate(rotor_s0):
                if sec == 0 and r_idx == k:
                    continue
                ext_chunks.append(_sample_prism_volume_points(rp, rot_deg=sec_rot, nu=5, nv=13, nw=5))
        ext_pts = np.concatenate(ext_chunks, axis=0)

        # Azimuthal and axial margins (strictly between tooth and recessed/ceiling pads)
        by0 = ty0 - 0.012
        by1 = ty1 + 0.012
        # Find nearest axial obstacles overlapping expanded radial/azimuthal footprint
        in_xy_band = (
            (ext_pts[:, 0] >= tx0 - 0.004)
            & (ext_pts[:, 0] <= tx1 + 0.004)
            & (ext_pts[:, 1] >= by0 - 0.002)
            & (ext_pts[:, 1] <= by1 + 0.002)
        )
        below_z = ext_pts[in_xy_band & (ext_pts[:, 2] < tz0), 2]
        above_z = ext_pts[in_xy_band & (ext_pts[:, 2] > tz1), 2]
        z_floor_max = float(np.max(below_z)) if below_z.size else (tz0 - 0.026)
        z_ceil_min = float(np.min(above_z)) if above_z.size else (tz1 + 0.026)
        bz0 = 0.5 * (z_floor_max + tz0) if (tz0 - z_floor_max) < 0.028 else (tz0 - 0.012)
        bz1 = 0.5 * (tz1 + z_ceil_min) if (z_ceil_min - tz1) < 0.028 else (tz1 + 0.012)

        # Find nearest inner (-x) and outer (+x) obstacles inside [by0, by1] x [bz0, bz1]
        in_yz_slab = (
            (ext_pts[:, 1] >= by0 - 0.002)
            & (ext_pts[:, 1] <= by1 + 0.002)
            & (ext_pts[:, 2] >= bz0 - 0.002)
            & (ext_pts[:, 2] <= bz1 + 0.002)
        )
        inner_x = ext_pts[in_yz_slab & (ext_pts[:, 0] < tx0), 0]
        outer_x = ext_pts[in_yz_slab & (ext_pts[:, 0] > tx1), 0]
        x_in_obs = float(np.max(inner_x)) if inner_x.size else (tx0 - 0.024)
        x_out_obs = float(np.min(outer_x)) if outer_x.size else (tx1 + 0.024)

        bx0 = 0.5 * (x_in_obs + tx0) if (tx0 - x_in_obs) < 0.028 else (tx0 - 0.012)
        bx1 = 0.5 * (tx1 + x_out_obs) if (x_out_obs - tx1) < 0.028 else (tx1 + 0.012)

        # Certify strictly positive distance from the 6 box surfaces to BOTH tooth_pts AND ext_pts
        inner_clearances = [
            tx0 - bx0,
            bx1 - tx1,
            ty0 - by0,
            by1 - ty1,
            tz0 - bz0,
            bz1 - tz1,
        ]
        min_inner = min(inner_clearances)
        if min_inner < min_box_clearance_um:
            raise ValueError(
                f"Stress box inner clearance {min_inner * 1e3:.2f} nm < {min_box_clearance_um * 1e3:.2f} nm "
                f"on {design_name} track {k} (theta={theta_deg})."
            )

        # Verify zero external body points lie inside or within min_box_clearance_um of [bx0, bx1]x[by0, by1]x[bz0, bz1]
        dx_ext = np.maximum(np.maximum(bx0 - ext_pts[:, 0], ext_pts[:, 0] - bx1), 0.0)
        dy_ext = np.maximum(np.maximum(by0 - ext_pts[:, 1], ext_pts[:, 1] - by1), 0.0)
        dz_ext = np.maximum(np.maximum(bz0 - ext_pts[:, 2], ext_pts[:, 2] - bz1), 0.0)
        dist_ext = np.sqrt(dx_ext**2 + dy_ext**2 + dz_ext**2)
        min_ext = float(np.min(dist_ext))
        if min_ext < min_box_clearance_um:
            raise ValueError(
                f"Stress box external stator/rotor clearance {min_ext * 1e3:.2f} nm < "
                f"{min_box_clearance_um * 1e3:.2f} nm on {design_name} track {k} (theta={theta_deg})."
            )

        cx, cy, cz = 0.5 * (bx0 + bx1), 0.5 * (by0 + by1), 0.5 * (bz0 + bz1)
        sx, sy, sz = (bx1 - bx0), (by1 - by0), (bz1 - bz0)

        faces.extend(
            (
                ToothStressFace(f"t{k}_xm", k, r_lever, rot_deg, 0, -1.0, (bx0, cy, cz), (0.0, sy, sz)),
                ToothStressFace(f"t{k}_xp", k, r_lever, rot_deg, 0, +1.0, (bx1, cy, cz), (0.0, sy, sz)),
                ToothStressFace(f"t{k}_ym", k, r_lever, rot_deg, 1, -1.0, (cx, by0, cz), (sx, 0.0, sz)),
                ToothStressFace(f"t{k}_yp", k, r_lever, rot_deg, 1, +1.0, (cx, by1, cz), (sx, 0.0, sz)),
                ToothStressFace(f"t{k}_zm", k, r_lever, rot_deg, 2, -1.0, (cx, cy, bz0), (sx, sy, 0.0)),
                ToothStressFace(f"t{k}_zp", k, r_lever, rot_deg, 2, +1.0, (cx, cy, bz1), (sx, sy, 0.0)),
            )
        )
        box_diagnostics.append(
            {
                "tooth_index": k,
                "r_lever_um": r_lever,
                "rot_deg": rot_deg,
                "box_bounds_um": {"x": [bx0, bx1], "y": [by0, by1], "z": [bz0, bz1]},
                "min_inner_clearance_nm": min_inner * 1.0e3,
                "min_external_clearance_nm": min_ext * 1.0e3,
            }
        )

    # Sector-0 cropped physical window enclosing all 3 co-rotating tooth boxes + active stator corridor
    phys_bounds = {
        "x_range_um": [0.18, 1.12],
        "y_range_um": [-0.42, 0.42],
        "z_range_um": [-0.25, 0.19],
        "cell_buffer_um": 0.08,
        "pml_thickness_um": 0.16,
    }
    meta = {
        "design_name": design_name,
        "z_tip_um": z_tip_um,
        "theta_deg": theta_deg,
        "boxes": box_diagnostics,
        "min_certified_clearance_nm": float(
            min(min(b["min_inner_clearance_nm"], b["min_external_clearance_nm"]) for b in box_diagnostics)
        ),
        "domain": phys_bounds,
    }
    return faces, meta


def _cell_spec(domain: Mapping[str, Any]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    xr, yr, zr = domain["x_range_um"], domain["y_range_um"], domain["z_range_um"]
    pad = 2.0 * (float(domain["cell_buffer_um"]) + float(domain["pml_thickness_um"]))
    dims = (float(xr[1] - xr[0]) + pad, float(yr[1] - yr[0]) + pad, float(zr[1] - zr[0]) + pad)
    centers = (0.5 * float(xr[0] + xr[1]), 0.5 * float(yr[0] + yr[1]), 0.5 * float(zr[0] + zr[1]))
    return dims, centers


def _cosine_amplitude(face: ToothStressFace, modes: tuple[int, int]) -> Callable[[Any], float]:
    axes = face.tangent_axes
    lengths = (face.size[axes[0]], face.size[axes[1]])
    norm = math.sqrt(
        (1.0 if modes[0] == 0 else 2.0) * (1.0 if modes[1] == 0 else 2.0) / (lengths[0] * lengths[1])
    )

    def amp(rel_pos: Any) -> float:
        coords = (float(rel_pos.x), float(rel_pos.y), float(rel_pos.z))
        val = norm
        for ax, length, m in zip(axes, lengths, modes):
            val *= math.cos(math.pi * m * (coords[ax] / length + 0.5))
        return val

    return amp


def _kernel_array(
    mp: Any,
    t_run: float,
    dt: float,
    sigma: float,
    field_type: Any,
    count: int,
) -> tuple[Any, np.ndarray]:
    owner = mp.make_casimir_gfunc(t_run, dt, sigma, field_type)
    if owner is None:
        raise RuntimeError("mp.make_casimir_gfunc returned null.")
    if isinstance(owner, np.ndarray):
        arr = np.asarray(owner)
        if np.iscomplexobj(arr):
            arr = arr[:count]
        else:
            interleaved = arr[: count * 2]
            arr = interleaved[0::2] + 1j * interleaved[1::2]
    else:
        try:
            ptr = ctypes.cast(owner, ctypes.POINTER(ctypes.c_double))
        except (TypeError, ctypes.ArgumentError):
            ptr = ctypes.cast(int(owner), ctypes.POINTER(ctypes.c_double))
        interleaved = np.ctypeslib.as_array(ptr, shape=(count * 2,))
        arr = interleaved[0::2] + 1j * interleaved[1::2]
    if not bool(np.isfinite(arr).all()):
        raise FloatingPointError("Casimir time kernel g(t) contains non-finite entries.")
    return owner, arr


def _build_meep_geometry_for_face(
    mp: Any,
    design_name: str,
    z_tip_um: float,
    theta_deg: float,
    rot_deg: float,
    configuration: str,
    material: Any,
    background: Any,
    domain: Mapping[str, Any],
) -> list[Any]:
    if configuration == "vac":
        return []
    rotor_s0, stator_s0, _, _ = build_engine_prisms(
        design_name, z_tip_um=z_tip_um, theta_deg=theta_deg
    )
    xr, yr, zr = domain["x_range_um"], domain["y_range_um"], domain["z_range_um"]
    x_min, x_max = float(xr[0]), float(xr[1])
    y_min, y_max = float(yr[0]), float(yr[1])

    geom: list[Any] = []
    source_prisms: list[tuple[CurvilinearPrism, int]] = []
    if configuration in ("both", "stator"):
        for sec in range(4):
            for sp in stator_s0:
                source_prisms.append((sp, sec))
    if configuration in ("both", "rotor"):
        for sec in range(4):
            for rp in rotor_s0:
                source_prisms.append((rp, sec))

    for prism, sec in source_prisms:
        wedges = prism_to_meep_subwedges(prism, rot_deg=rot_deg + sec * SECTOR_DEG, n_v=20, n_w_helical=8)
        for w in wedges:
            xs = [v[0] for v in w["vertices_xy"]]
            ys = [v[1] for v in w["vertices_xy"]]
            if max(xs) < x_min or min(xs) > x_max or max(ys) < y_min or min(ys) > y_max:
                continue
            verts = [mp.Vector3(vx, vy, float(w["z_min"])) for vx, vy in w["vertices_xy"]]
            geom.append(
                mp.Prism(
                    vertices=verts,
                    height=float(w["z_max"] - w["z_min"]),
                    axis=mp.Vector3(0.0, 0.0, 1.0),
                    material=material,
                )
            )

    # Mask outside physical crop window so zero metal ever enters buffer/PML
    dims, centers = _cell_spec(domain)
    cx0, cx1 = centers[0] - 0.5 * dims[0] - 0.05, centers[0] + 0.5 * dims[0] + 0.05
    cy0, cy1 = centers[1] - 0.5 * dims[1] - 0.05, centers[1] + 0.5 * dims[1] + 0.05
    mz = dims[2] + 0.10
    if x_min > cx0:
        geom.append(
            mp.Block(
                size=mp.Vector3(x_min - cx0, cy1 - cy0, mz),
                center=mp.Vector3(0.5 * (cx0 + x_min), centers[1], centers[2]),
                material=background,
            )
        )
    if cx1 > x_max:
        geom.append(
            mp.Block(
                size=mp.Vector3(cx1 - x_max, cy1 - cy0, mz),
                center=mp.Vector3(0.5 * (x_max + cx1), centers[1], centers[2]),
                material=background,
            )
        )
    if y_min > cy0:
        geom.append(
            mp.Block(
                size=mp.Vector3(cx1 - cx0, y_min - cy0, mz),
                center=mp.Vector3(centers[0], 0.5 * (cy0 + y_min), centers[2]),
                material=background,
            )
        )
    if cy1 > y_max:
        geom.append(
            mp.Block(
                size=mp.Vector3(cx1 - cx0, cy1 - y_max, mz),
                center=mp.Vector3(centers[0], 0.5 * (y_max + cy1), centers[2]),
                material=background,
            )
        )
    return geom


def run_numpy_yee_micro_probe(
    args: argparse.Namespace,
    task_spec: Mapping[str, Any],
    faces: Sequence[ToothStressFace],
    meta: Mapping[str, Any],
) -> int:
    """Deterministic float64 3D Yee-grid curl + dual (Fz, Fy) stress projection micro-probe."""
    started = time.perf_counter()
    dims, centers = _cell_spec(meta["domain"])
    req_shape = tuple(max(4, math.ceil(L * args.resolution)) for L in dims)
    shape = tuple(min(64, n) for n in req_shape)
    spacing = tuple(L / n for L, n in zip(dims, shape))
    dt = 0.5 * min(spacing)

    coords = tuple(
        (np.arange(n, dtype=np.float64) + 0.5) * dx - 0.5 * L + c0
        for n, dx, L, c0 in zip(shape, spacing, dims, centers)
    )
    e_field = np.zeros((3, *shape), dtype=np.float64)
    h_field = np.zeros_like(e_field)

    # Project onto first 3 faces (one per tooth) for fast diagnostic validation
    probe_faces = faces[::6]
    proj_specs = []
    for face in probe_faces:
        sel: list[Any] = [slice(None), slice(None), slice(None)]
        sel[face.axis] = int(np.argmin(np.abs(coords[face.axis] - face.center[face.axis])))
        bases = []
        for ax in face.tangent_axes:
            rel = coords[ax] - face.center[ax]
            idx = np.flatnonzero(np.abs(rel) <= 0.5 * face.size[ax])
            if idx.size == 0:
                idx = np.array([int(np.argmin(np.abs(rel)))])
            sel[ax] = slice(int(idx[0]), int(idx[-1]) + 1)
            pos = np.clip(rel[idx] / face.size[ax] + 0.5, 0.0, 1.0)
            modes = np.arange(args.nmax, dtype=np.float64)
            b = np.cos(math.pi * modes[:, None] * pos[None, :]) * np.sqrt(
                np.where(modes == 0, 1.0, 2.0) / face.size[ax]
            )[:, None]
            bases.append(b)
        area = spacing[face.tangent_axes[0]] * spacing[face.tangent_axes[1]]
        proj_specs.append((face, tuple(sel), bases[0], bases[1], area))
        e_field[(2, *sel)] += np.outer(bases[0][0], bases[1][0])

    def diff_ax(f: np.ndarray, ax: int, fwd: bool) -> np.ndarray:
        return (np.roll(f, -1, axis=ax) - f) / spacing[ax] if fwd else (f - np.roll(f, 1, axis=ax)) / spacing[ax]

    def step_curl(tgt: np.ndarray, src: np.ndarray, scale: float, fwd: bool) -> None:
        tgt[0] += scale * (diff_ax(src[2], 1, fwd) - diff_ax(src[1], 2, fwd))
        tgt[1] += scale * (diff_ax(src[0], 2, fwd) - diff_ax(src[2], 0, fwd))
        tgt[2] += scale * (diff_ax(src[1], 0, fwd) - diff_ax(src[0], 1, fwd))

    chk_z = 0.0
    chk_tau = 0.0
    for _ in range(args.max_steps):
        step_curl(h_field, e_field, -dt, True)
        step_curl(e_field, h_field, dt, False)
        for face, sel, b0, b1, area in proj_specs:
            ef = e_field[(slice(None), *sel)]
            hf = h_field[(slice(None), *sel)]
            tz = ef[2] * ef[face.axis] + hf[2] * hf[face.axis]
            ty = ef[1] * ef[face.axis] + hf[1] * hf[face.axis]
            if face.axis == 2:
                tz -= 0.5 * (np.sum(ef * ef, axis=0) + np.sum(hf * hf, axis=0))
            if face.axis == 1:
                ty -= 0.5 * (np.sum(ef * ef, axis=0) + np.sum(hf * hf, axis=0))
            chk_z += dt * face.orientation * area * float(np.sum(b0 @ tz @ b1.T))
            chk_tau += dt * face.r_lever_um * face.orientation * area * float(np.sum(b0 @ ty @ b1.T))

    out_path = UF_RESULTS_DIR / f"probe_uf2_task_{int(task_spec['task_id']):02d}.json"
    payload = {
        "suite": "eng_uf2",
        "status": "micro_probe_completed",
        "solver": "numpy_yee_probe",
        "time_truncated": True,
        "casimir_force_computed": False,
        "task_id": int(task_spec["task_id"]),
        "design_name": task_spec["design_name"],
        "stroke": task_spec["stroke"],
        "resolution": int(args.resolution),
        "nmax": int(args.nmax),
        "max_steps": int(args.max_steps),
        "stress_box_certification": meta,
        "yee_grid_shape": shape,
        "dct_checksum_z": chk_z,
        "dct_checksum_tau": chk_tau,
        "elapsed_seconds": time.perf_counter() - started,
    }
    atomic_write_json(out_path, payload)
    print(
        f"[UF2 MICRO-PROBE] Task {task_spec['task_id']} ({task_spec['design_name']}) "
        f"min_clearance={meta['min_certified_clearance_nm']:.2f} nm -> {out_path}",
        flush=True,
    )
    return 0


def run_meep_task(args: argparse.Namespace, task_spec: Mapping[str, Any]) -> int:
    faces, meta = build_and_certify_stress_faces(
        task_spec["design_name"],
        float(task_spec["z_tip_um"]),
        float(task_spec["theta_deg"]),
    )

    try:
        mp = importlib.import_module("meep")
    except ImportError as exc:
        if args.max_steps > 0:
            return run_numpy_yee_micro_probe(args, task_spec, faces, meta)
        raise RuntimeError(
            "Meep is required for --max-steps 0 full FDTD verification; load BigRed 200 meep env."
        ) from exc

    started_mono = time.monotonic()
    walltime_sec = args.max_walltime_hours * 3600.0

    # Parallel shard detection (MPI lockstep vs Slurm serial multi-task sharding)
    processors = int(mp.count_processors())
    mpi_comm: Any = None
    shard_count = 1
    shard_rank = 0
    is_master = bool(mp.am_master())
    if processors > 1:
        try:
            from mpi4py import MPI  # type: ignore[import-not-found]

            mpi_comm = MPI.COMM_WORLD
            is_master = mpi_comm.Get_rank() == 0
        except ImportError as exc:
            raise RuntimeError(
                "MPI-enabled pymeep (mp.count_processors() > 1) requires mpi4py for lockstep rank sync."
            ) from exc
    elif processors == 1:
        ntasks = int(os.environ.get("SLURM_NTASKS", "1"))
        if ntasks > 1:
            shard_count = ntasks
            shard_rank = int(os.environ.get("SLURM_PROCID", "0"))
            is_master = shard_rank == 0
            if not is_master:
                mp.verbosity(0)

    sigma = 0.5 / 0.050  # d_eff = 50 nm -> sigma = 10.0 um^-1
    t_run = float(args.t_run)
    courant = 0.5
    dims, centers = _cell_spec(meta["domain"])
    pml_thick = float(meta["domain"]["pml_thickness_um"])

    polarizations = (
        ("Ex", mp.Ex, True),
        ("Ey", mp.Ey, True),
        ("Ez", mp.Ez, True),
        ("Hx", mp.Hx, False),
        ("Hy", mp.Hy, False),
        ("Hz", mp.Hz, False),
    )
    comp_dir = {
        mp.Ex: mp.X,
        mp.Ey: mp.Y,
        mp.Ez: mp.Z,
        mp.Hx: mp.X,
        mp.Hy: mp.Y,
        mp.Hz: mp.Z,
    }

    chk_dir = args.checkpoint_dir / f"task_{int(task_spec['task_id']):02d}"
    if is_master or shard_count > 1:
        chk_dir.mkdir(parents=True, exist_ok=True)
    if mpi_comm is not None:
        mpi_comm.Barrier()

    fp_payload = {
        "task": dict(task_spec),
        "resolution": args.resolution,
        "nmax": args.nmax,
        "t_run": t_run,
        "material": args.material,
        "max_steps": args.max_steps,
    }
    fingerprint = hashlib.sha256(json.dumps(fp_payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]

    # Load all existing shard checkpoints matching fingerprint (broadcast in MPI mode for lockstep worklist)
    merged: dict[str, dict[str, tuple[float, float]]] = {cfg: {} for cfg in ALL_CONFIGS}
    if not args.no_cache and (is_master or shard_count > 1):
        for p in sorted(chk_dir.glob(f"moments_{fingerprint}_*.json")):
            try:
                with p.open("r", encoding="utf-8") as fh:
                    d = json.load(fh)
                if d.get("fingerprint") == fingerprint:
                    for cfg in ALL_CONFIGS:
                        for k_str, pair in d.get("moments", {}).get(cfg, {}).items():
                            merged[cfg][k_str] = (float(pair[0]), float(pair[1]))
            except (OSError, ValueError, KeyError):
                continue
    if mpi_comm is not None:
        merged = mpi_comm.bcast(merged if is_master else None, root=0)

    all_work: list[tuple[str, str, Any, bool, ToothStressFace, int]] = [
        (cfg, pol_label, comp, is_elec, face, mode)
        for cfg in ALL_CONFIGS
        for pol_label, comp, is_elec in polarizations
        for face in faces
        for mode in range(args.nmax**2)
        if f"{pol_label}:{face.name}:{mode}" not in merged[cfg]
    ]

    shard_file = chk_dir / f"moments_{fingerprint}_shard_{shard_rank:03d}.json"
    local_moments: dict[str, dict[str, list[float]]] = {
        cfg: {k: [v[0], v[1]] for k, v in merged[cfg].items()} if shard_rank == 0 else {}
        for cfg in ALL_CONFIGS
    }

    wp_meep = GOLD_WP_EV * EV_TO_MEEP_FREQ
    gam_meep = GOLD_GAMMA_EV * EV_TO_MEEP_FREQ

    walltime_hit = False
    for idx, (cfg, pol_label, comp, is_elec, face, mode) in enumerate(all_work):
        if idx % shard_count != shard_rank:
            continue
        stop_now = (time.monotonic() - started_mono) >= walltime_sec if (is_master or shard_count > 1) else False
        if mpi_comm is not None:
            stop_now = bool(mpi_comm.bcast(stop_now, root=0))
        if stop_now:
            walltime_hit = True
            break

        cond = {"D_conductivity": sigma} if is_elec else {"B_conductivity": sigma}
        background = mp.Medium(epsilon=1.0, **cond)
        if args.material.lower() == "pec":
            mat = mp.metal
        else:
            drude = mp.DrudeSusceptibility(frequency=1.0, gamma=gam_meep, sigma=wp_meep**2)
            mat = mp.Medium(epsilon=GOLD_EPS_INF, E_susceptibilities=[drude], **cond)

        geom = _build_meep_geometry_for_face(
            mp,
            task_spec["design_name"],
            float(task_spec["z_tip_um"]),
            float(task_spec["theta_deg"]),
            face.rot_deg,
            cfg,
            mat,
            background,
            meta["domain"],
        )

        dt_holder = [courant / args.resolution]

        def impulse(t: float) -> float:
            dt_v = dt_holder[0]
            return 1.0 / dt_v if -0.25 * dt_v <= t < 0.75 * dt_v else 0.0

        m1, m2 = mode % args.nmax, mode // args.nmax
        if face.axis == 0:
            mx, my, mz = 0, m1, m2
        elif face.axis == 1:
            mx, my, mz = m1, 0, m2
        else:
            mx, my, mz = m1, m2, 0

        sim = mp.Simulation(
            cell_size=mp.Vector3(*dims),
            geometry_center=mp.Vector3(*centers),
            dimensions=3,
            resolution=args.resolution,
            Courant=courant,
            boundary_layers=[mp.PML(pml_thick)],
            default_material=background,
            geometry=geom,
            eps_averaging=False,
            sources=[
                mp.Source(
                    src=mp.CustomSource(
                        src_func=impulse,
                        start_time=-0.25 * dt_holder[0],
                        end_time=0.75 * dt_holder[0],
                    ),
                    component=comp,
                    center=mp.Vector3(*face.center),
                    size=mp.Vector3(*face.size),
                    amp_func=_cosine_amplitude(face, (m1, m2)),
                )
            ],
            force_complex_fields=True,
        )
        try:
            sim.init_sim()
            dt_raw = sim.fields.dt
            dt = float(dt_raw() if callable(dt_raw) else dt_raw)
            dt_holder[0] = dt
            full_steps = max(1, int(t_run / dt))
            steps = min(full_steps, args.max_steps) if args.max_steps > 0 else full_steps
            ftype = mp.E_stuff if is_elec else mp.H_stuff
            k_owner, gt_arr = _kernel_array(mp, t_run, dt, sigma, ftype, steps)
            vol = mp.Volume(center=mp.Vector3(*face.center), size=mp.Vector3(*face.size), dims=3)

            int_z = 0.0
            int_y = 0.0
            aborted_mid_moment = False
            for step in range(steps):
                if step > 0 and step % 25 == 0:
                    mid_stop = (
                        (time.monotonic() - started_mono) >= walltime_sec
                        if (is_master or shard_count > 1)
                        else False
                    )
                    if mpi_comm is not None:
                        mid_stop = bool(mpi_comm.bcast(mid_stop, root=0))
                    if mid_stop:
                        aborted_mid_moment = True
                        walltime_hit = True
                        break
                sim.fields.step()
                fz_t = sim.fields.casimir_stress_dct_integral(
                    mp.Z, comp_dir[comp], float(mx), float(my), float(mz), ftype, vol.swigobj
                )
                fy_t = sim.fields.casimir_stress_dct_integral(
                    mp.Y, comp_dir[comp], float(mx), float(my), float(mz), ftype, vol.swigobj
                )
                int_z += float(np.imag(gt_arr[step] * dt * face.orientation * fz_t))
                int_y += float(np.imag(gt_arr[step] * dt * face.orientation * fy_t))
            del gt_arr, k_owner
        finally:
            sim.reset_meep()

        if aborted_mid_moment:
            break

        m_key = f"{pol_label}:{face.name}:{mode}"
        tau_contrib = face.r_lever_um * int_y
        if is_master or shard_count > 1:
            local_moments[cfg][m_key] = [int_z, tau_contrib]
            atomic_write_json(
                shard_file,
                {"fingerprint": fingerprint, "shard_rank": shard_rank, "moments": local_moments},
            )

    # Barrier / merge on rank 0
    if shard_count > 1:
        job_tag = os.environ.get("SLURM_JOB_ID", "local")
        done_marker = chk_dir / f"done_{fingerprint}_job_{job_tag}_shard_{shard_rank:03d}.json"
        atomic_write_json(done_marker, {"walltime_hit": walltime_hit, "ts": time.time()})
        if not is_master:
            return 75 if walltime_hit else 0
        # Wait for peer shards in this Slurm step (bounded by remaining walltime + 600s grace)
        wait_deadline = max(time.monotonic() + 900.0, started_mono + walltime_sec + 300.0)
        while time.monotonic() < wait_deadline:
            markers = list(chk_dir.glob(f"done_{fingerprint}_job_{job_tag}_shard_*.json"))
            if len(markers) >= shard_count:
                break
            time.sleep(0.5)

    if not is_master:
        rc_worker = 75 if walltime_hit else 0
        if mpi_comm is not None:
            rc_worker = int(mpi_comm.bcast(0, root=0))
        return rc_worker

    # Reload all shards
    final_merged: dict[str, dict[str, tuple[float, float]]] = {cfg: {} for cfg in ALL_CONFIGS}
    for p in sorted(chk_dir.glob(f"moments_{fingerprint}_*.json")):
        with p.open("r", encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("fingerprint") == fingerprint:
            for cfg in ALL_CONFIGS:
                for k_str, pair in d.get("moments", {}).get(cfg, {}).items():
                    final_merged[cfg][k_str] = (float(pair[0]), float(pair[1]))

    expected_per_cfg = 6 * len(faces) * (args.nmax**2)
    complete = all(len(final_merged[cfg]) == expected_per_cfg for cfg in ALL_CONFIGS)
    if not complete:
        print(
            f"[UF2 PARTIAL] Task {task_spec['task_id']}: "
            f"{sum(len(final_merged[c]) for c in ALL_CONFIGS)}/{4 * expected_per_cfg} moments cached.",
            file=sys.stderr,
            flush=True,
        )
        if mpi_comm is not None:
            mpi_comm.bcast(75, root=0)
        return 75

    fz_by_cfg = {
        cfg: 4.0 * math.fsum(v[0] for v in final_merged[cfg].values()) for cfg in ALL_CONFIGS
    }
    tau_by_cfg = {
        cfg: 4.0 * math.fsum(v[1] for v in final_merged[cfg].values()) for cfg in ALL_CONFIGS
    }
    fz_net_dimless = (fz_by_cfg["both"] - fz_by_cfg["rotor"]) - (fz_by_cfg["stator"] - fz_by_cfg["vac"])
    tau_net_dimless = (tau_by_cfg["both"] - tau_by_cfg["rotor"]) - (tau_by_cfg["stator"] - tau_by_cfg["vac"])

    out_file = (
        UF_RESULTS_DIR / f"probe_uf2_task_{int(task_spec['task_id']):02d}.json"
        if args.max_steps > 0
        else UF_RESULTS_DIR / f"uf2_task_{int(task_spec['task_id']):02d}.json"
    )
    task_result = {
        "suite": "eng_uf2",
        "status": "micro_probe_completed" if args.max_steps > 0 else "completed",
        "solver": "Meep_3D_FDTD_Casimir_MST",
        "time_truncated": args.max_steps > 0,
        "task_id": int(task_spec["task_id"]),
        "design_name": task_spec["design_name"],
        "stroke": task_spec["stroke"],
        "z_tip_um": float(task_spec["z_tip_um"]),
        "theta_deg": float(task_spec["theta_deg"]),
        "resolution": int(args.resolution),
        "dx_nm": 1000.0 / float(args.resolution),
        "nmax": int(args.nmax),
        "t_run": t_run,
        "material": args.material,
        "moments_per_config": expected_per_cfg,
        "stress_box_certification": meta,
        "fz_by_config_dimless": fz_by_cfg,
        "tau_by_config_dimless": tau_by_cfg,
        "f_z_pN": fz_net_dimless * DIMLESS_TO_PN,
        "tau_theta_pN_um": tau_net_dimless * DIMLESS_TO_PN,
        "lever_arm_approximation_max_rel_bound": 0.083,
    }
    atomic_write_json(out_file, task_result)
    print(f"[UF2 TASK {task_spec['task_id']} COMPLETE] Saved {out_file}", flush=True)
    if mpi_comm is not None:
        mpi_comm.bcast(0, root=0)
    return 0


def aggregate_uf2_results(args: argparse.Namespace) -> int:
    """Aggregate all 8 completed Meep FDTD task JSONs against Ultra-Fine 3D BEM."""
    tasks_data: list[dict[str, Any]] = []
    for t_spec in MEEP_BENCHMARK_TASKS:
        tid = int(t_spec["task_id"])
        p = UF_RESULTS_DIR / f"uf2_task_{tid:02d}.json"
        if not p.is_file():
            raise FileNotFoundError(
                f"[ERROR: RUN_DATA_MISSING] Missing completed Meep FDTD output {p}."
            )
        with p.open("r", encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("time_truncated", False) or d.get("status") != "completed":
            raise RuntimeError(f"Refusing to aggregate time-truncated or incomplete task file {p}.")
        tasks_data.append(d)

    # Evaluate matching L4_UltraFine BEM reference at the 8 states
    bem_ref: dict[int, dict[str, Any]] = {}
    for dname in ENGINE_DESIGN_NAMES:
        model = PreparedEngineBemModel(
            dname,
            material=args.material,
            n_r=3,
            n_phi_tooth=6,
            n_phi_bridge=6,
            n_phi_arc_override=18,
            n_z=3,
            n_xi=24,
            quad_order=3,
            device=args.device,
            lazy_self_cache=True,
        )
        evals = model.evaluate_states_batch([(-0.092, 22.0), (-0.084, 64.0)])
        for t_spec in MEEP_BENCHMARK_TASKS:
            if t_spec["design_name"] == dname:
                bem_ref[int(t_spec["task_id"])] = (
                    evals[0] if t_spec["stroke"] == "Stroke_I_Repulsive" else evals[1]
                )

    comparisons: list[dict[str, Any]] = []
    fz_sign_matches = 0
    chiral_tau_sign_matches = 0
    chiral_count = 0
    for td in tasks_data:
        tid = int(td["task_id"])
        b = bem_ref[tid]
        fz_m, fz_b = float(td["f_z_pN"]), float(b["f_z_pN"])
        tau_m, tau_b = float(td["tau_theta_pN_um"]), float(b["tau_theta_pN_um"])
        if fz_m * fz_b > 0.0:
            fz_sign_matches += 1
        is_chiral = td["design_name"] != "Sym_Baseline_CantorN2"
        if is_chiral:
            chiral_count += 1
            if tau_m > 0.0 and tau_b > 0.0:
                chiral_tau_sign_matches += 1
        comparisons.append(
            {
                "task_id": tid,
                "design_name": td["design_name"],
                "stroke": td["stroke"],
                "meep_f_z_pN": fz_m,
                "bem_f_z_pN": fz_b,
                "meep_tau_theta_pN_um": tau_m,
                "bem_tau_theta_pN_um": tau_b,
                "fz_sign_match": bool(fz_m * fz_b > 0.0),
                "tau_positive_concordance": bool((not is_chiral) or (tau_m > 0.0 and tau_b > 0.0)),
            }
        )

    report = {
        "suite": "eng_uf2",
        "status": "completed",
        "time_truncated": False,
        "resolution": int(tasks_data[0]["resolution"]),
        "dx_nm": float(tasks_data[0]["dx_nm"]),
        "nmax": int(tasks_data[0]["nmax"]),
        "summary": {
            "fz_sign_matches": fz_sign_matches,
            "total_states": len(comparisons),
            "chiral_forward_torque_matches": chiral_tau_sign_matches,
            "chiral_states": chiral_count,
            "config_d_stroke1_meep_tau_pN_um": comparisons[6]["meep_tau_theta_pN_um"],
            "config_d_stroke3_meep_tau_pN_um": comparisons[7]["meep_tau_theta_pN_um"],
            "config_d_stroke1_meep_fz_pN": comparisons[6]["meep_f_z_pN"],
            "config_d_stroke3_meep_fz_pN": comparisons[7]["meep_f_z_pN"],
        },
        "comparisons": comparisons,
    }
    report_path = UF_RESULTS_DIR / "uf2_meep_verification_report.json"
    atomic_write_json(report_path, report)

    metrics_path = UF_RESULTS_DIR / "uf2_provenance_metrics.json"
    macros_path = UF_RESULTS_DIR / "uf2_macros_results.tex"
    solver_params = {"resolution": report["resolution"], "dx_nm": report["dx_nm"], "nmax": report["nmax"]}
    set_solver_provenance(
        "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM",
        solver_params,
        metrics_path=str(metrics_path),
    )
    log_step("uf2_meep_fdtd_verification", report["summary"], metrics_path=str(metrics_path))
    log_metric(
        "engine_uf2_resolution",
        report["resolution"],
        step_id="uf2_meep_fdtd_verification",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf2_fz_sign_matches",
        fz_sign_matches,
        step_id="uf2_meep_fdtd_verification",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf2_chiral_tau_matches",
        chiral_tau_sign_matches,
        step_id="uf2_meep_fdtd_verification",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf2_config_d_stroke1_tau",
        round(report["summary"]["config_d_stroke1_meep_tau_pN_um"], 3),
        step_id="uf2_meep_fdtd_verification",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf2_config_d_stroke3_tau",
        round(report["summary"]["config_d_stroke3_meep_tau_pN_um"], 3),
        step_id="uf2_meep_fdtd_verification",
        metrics_path=str(metrics_path),
    )
    export_macros(metrics_path=str(metrics_path), output_path=str(macros_path))

    # Plot Meep FDTD vs Ultra-Fine BEM bar comparison
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=300)
    x = np.arange(len(comparisons))
    w = 0.36
    short_lbls = [
        f"{c['design_name'].split('_')[1]}\n({'I' if 'Stroke_I_' in c['stroke'] else 'III'})"
        for c in comparisons
    ]
    axes[0].bar(x - 0.5 * w, [c["meep_f_z_pN"] for c in comparisons], w, label="3D Meep FDTD (MST)", color="#1a73e8")
    axes[0].bar(x + 0.5 * w, [c["bem_f_z_pN"] for c in comparisons], w, label="Ultra-Fine 3D BEM", color="#fbbc04")
    axes[0].axhline(0.0, color="#222222", lw=0.8)
    axes[0].set_xticks(x, short_lbls, fontsize=8)
    axes[0].set_ylabel("Axial Force $F_z$ (pN)")
    axes[0].set_title("A. Full-Wave 3D Meep FDTD vs. BEM: $F_z$")
    axes[0].legend(fontsize=8.5)
    axes[0].grid(True, axis="y", alpha=0.25)

    axes[1].bar(
        x - 0.5 * w,
        [c["meep_tau_theta_pN_um"] for c in comparisons],
        w,
        label="3D Meep FDTD (MST)",
        color="#d93025",
    )
    axes[1].bar(
        x + 0.5 * w,
        [c["bem_tau_theta_pN_um"] for c in comparisons],
        w,
        label="Ultra-Fine 3D BEM",
        color="#0d9488",
    )
    axes[1].axhline(0.0, color="#222222", lw=0.8)
    axes[1].set_xticks(x, short_lbls, fontsize=8)
    axes[1].set_ylabel("Azimuthal Torque $\\tau_\\theta$ (pN$\\cdot\\mu$m)")
    axes[1].set_title("B. Full-Wave 3D Meep FDTD vs. BEM: $\\tau_\\theta$")
    axes[1].legend(fontsize=8.5)
    axes[1].grid(True, axis="y", alpha=0.25)

    fig.tight_layout()
    out_png = ENGINE_FIGURES_DIR / "fig_uf2_meep_vs_bem.png"
    out_pdf = ENGINE_FIGURES_DIR / "fig_uf2_meep_vs_bem.pdf"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)

    for fp in (out_png, out_pdf):
        save_plot_provenance(
            str(fp),
            str(report_path),
            columns_used=["comparisons", "summary"],
            solver_name="Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM",
            solver_parameters=solver_params,
        )
    print(f"[UF2 AGGREGATE COMPLETE] Saved {report_path} and figures.", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task-id", type=int, default=7, help="Task ID in 1..8 (or Slurm array index).")
    p.add_argument("--aggregate", action="store_true", help="Aggregate all 8 completed Meep tasks.")
    p.add_argument("--resolution", type=int, default=100, help="FDTD pixels/um (100 -> dx = 10 nm).")
    p.add_argument("--nmax", type=int, default=2, help="Tangential cosine modes per direction.")
    p.add_argument("--t-run", type=float, default=2.5, help="Casimir integration horizon (um/c).")
    p.add_argument("--material", choices=("Gold", "PEC"), default="Gold")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--max-steps", type=int, default=0)
    p.add_argument("--max-walltime-hours", type=float, default=11.3)
    p.add_argument("--checkpoint-dir", type=Path, default=UF_RESULTS_DIR / "checkpoints_uf2")
    p.add_argument("--no-cache", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.aggregate:
        return aggregate_uf2_results(args)
    if not 1 <= args.task_id <= len(MEEP_BENCHMARK_TASKS):
        raise ValueError(f"--task-id must be in 1..{len(MEEP_BENCHMARK_TASKS)}.")
    return run_meep_task(args, MEEP_BENCHMARK_TASKS[args.task_id - 1])


if __name__ == "__main__":
    raise SystemExit(main())
