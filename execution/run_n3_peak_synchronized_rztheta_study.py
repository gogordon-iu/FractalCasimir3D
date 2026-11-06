#!/usr/bin/env python3
"""
Peak-Synchronized 3D (r, z, theta) N=3 Cantor Clutch & Area-Angle-Height Control Study.

Evaluates whether synchronizing each track's radial fill ratio (w_k / W_k), vertical tooth
height / tip depth (h_teeth_k, z_tip_k), and azimuthal tooth angle (Delta_theta_k) to the
log-periodic wavenumber peaks (kappa_peak,m in {2.41, 4.92, 9.01} um^-1, lambda_m in
{415, 203, 111} nm) and local radial chord-length peaks of the 3rd-generation (N=3, 7-track)
Cantor hierarchy unlocks the dormant Generation-1 (450 nm) and Generation-2 (150 nm) slots
and outer-radius Generation-3 (50 nm) tracks, and tests those designs head-to-head against
matched Area-Angle-Height Controls:

  1. Fractal_N3_Cantor7Track_FlatZ (Baseline flat-height, uniform-angle N=3 Cantor, A = 0.3104 um^2)
  2. Ctrl_Uniform7Track_FlatZ (Baseline flat-height, uniform-angle 7-track grating, A = 0.3104 um^2)
  3. Ctrl_Monotonic7Track_FlatZ (Baseline flat-height, uniform-angle monotonic 7-track, A = 0.3356 um^2)
  4. Cantor_N3_PeakSync_IsoArea (Peak-synchronized (r,z,theta) N=3 Cantor at exact matched A = 0.3104 um^2)
  5. Cantor_N3_PeakSync_HighForce (Peak-synchronized (r,z,theta) N=3 Cantor with unconstrained inner-slot angle)
  6. Ctrl_Uniform_IsoAreaAngleHeight (Uniform 7-track grating with exact matched A = 0.3104 um^2,
     radial angle profile Delta_theta_k, and stepped tooth height profile H_k)
  7. Ctrl_OutOfPhase_IsoAreaAngleHeight (Cantor 7-track slots with exact matched A = 0.3104 um^2,
     tooth widths, angles, and stepped heights assigned out-of-phase with the Cantor generations)
  8. Ctrl_Monotonic_SameRadialProf_IsoArea (Monotonic 7-track [50,50,50,50,150,150,450] nm given the
     exact same radial-slot (w_k, H_k, Delta_theta_k) profile scaled to A = 0.3104 um^2)
  9. Ctrl_Monotonic_SameGenRule_IsoArea (Monotonic 7-track [50,50,50,50,150,150,450] nm given the
     same generation-indexed (w_m, H_m) rules and inverse-radius chord-locked angle law at A = 0.3104 um^2)
"""

from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse
import dataclasses
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.casimir_bem_solver import (
    ClutchSurfaceMesh,
    Geometry,
    MEEP_FORCE_TO_SI,
    MaterialModel,
    _disk_self_term,
    _quadrature,
    _rotation,
)
from execution.run_fractal_advantage_study import (
    TrackSpec3D,
    make_track_element,
    repository_face,
    subdivisions,
    tooth_segments,
)
from execution.clutch_geometry_redesign import (
    DEFAULT_H_TEETH_ROTATIONAL_UM,
    DEFAULT_N3_ANGLES_BY_GEN_DEG,
    DEFAULT_N3_CANTOR_GENERATIONS,
    DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM as CANTOR_WIDTHS_NM,
    DEFAULT_N3_H_TEETH_BY_GEN_UM,
    DEFAULT_N3_ISO_AREA_TARGET_UM2 as ISO_AREA_TARGET_UM2,
    DEFAULT_N3_MAX_TOOTH_ARC_DEG,
    DEFAULT_N3_MONOTONIC_GENERATIONS,
    DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM as MONOTONIC_WIDTHS_NM,
    DEFAULT_N3_OUT_OF_PHASE_SLOT_ORDER,
    DEFAULT_N3_R_MAX_UM,
    DEFAULT_N3_TOOTH_ARC_DEG,
    DEFAULT_N3_UNIFORM_SLOT_WIDTHS_NM as UNIFORM_WIDTHS_NM,
    DEFAULT_N3_W1_RATIO,
    DEFAULT_N3_Z_TIPS_BY_GEN_UM,
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    DEFAULT_R_MIN_UM,
    DEFAULT_T_LANDING_PAD_UM,
    DEFAULT_T_MEMBRANE_UM,
    DEFAULT_Z_PAD_TOP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
)
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)


@dataclass(frozen=True, slots=True)
class TrackSpecRZTheta:
    """Per-track 3D (r, z, theta) geometric specification."""
    r_inner: float
    r_outer: float
    r_tooth_in: float
    r_tooth_out: float
    z_tip: float
    h_teeth: float
    tooth_arc_deg: float
    level: int


@dataclass(frozen=True, slots=True)
class PeakSyncDesign:
    """Multi-track 3D (r, z, theta) clutch design specification."""
    name: str
    family_role: str
    tracks: tuple[TrackSpecRZTheta, ...]
    R_min: float = DEFAULT_R_MIN_UM
    R_max: float = DEFAULT_N3_R_MAX_UM
    aperture_arc_deg: float = DEFAULT_ROTATIONAL_APERTURE_ARC_DEG
    t_membrane: float = DEFAULT_T_MEMBRANE_UM
    t_landing_pad: float = DEFAULT_T_LANDING_PAD_UM
    z_pad_top: float = DEFAULT_Z_PAD_TOP_UM


def build_rztheta_design(
    name: str,
    family_role: str,
    slot_widths_nm: Sequence[float],
    w_ratios: Sequence[float],
    z_tips_um: Sequence[float],
    h_teeths_um: Sequence[float],
    thetas_deg: Sequence[float],
    z_pad_top: float = DEFAULT_Z_PAD_TOP_UM,
    R_min: float = DEFAULT_R_MIN_UM,
    R_max: float = DEFAULT_N3_R_MAX_UM,
) -> PeakSyncDesign:
    """Construct a 7-track 3D (r, z, theta) design with equal inter-slot stator ribs."""
    rib_um = ((R_max - R_min) - sum(w * 1e-3 for w in slot_widths_nm)) / (len(slot_widths_nm) + 1)
    cur = R_min + rib_um
    tracks: list[TrackSpecRZTheta] = []
    lvl_map = {450: 1, 150: 2, 50: 3}
    for idx, w_nm in enumerate(slot_widths_nm):
        s_um = float(w_nm) * 1e-3
        t_um = float(w_ratios[idx]) * s_um
        mid = cur + 0.5 * s_um
        tracks.append(
            TrackSpecRZTheta(
                r_inner=cur,
                r_outer=cur + s_um,
                r_tooth_in=mid - 0.5 * t_um,
                r_tooth_out=mid + 0.5 * t_um,
                z_tip=float(z_tips_um[idx]),
                h_teeth=float(h_teeths_um[idx]),
                tooth_arc_deg=float(thetas_deg[idx]),
                level=lvl_map.get(int(round(w_nm)), 1),
            )
        )
        cur += s_um + rib_um
    return PeakSyncDesign(
        name=name,
        family_role=family_role,
        tracks=tuple(tracks),
        R_min=R_min,
        R_max=R_max,
        z_pad_top=z_pad_top,
    )


def active_tooth_area_um2(tracks: Sequence[TrackSpecRZTheta]) -> float:
    """Return total C4 active rotor tooth footprint area in um^2."""
    return float(
        sum(
            4.0 * math.radians(t.tooth_arc_deg) * 0.5 * (t.r_inner + t.r_outer) * (t.r_tooth_out - t.r_tooth_in)
            for t in tracks
        )
    )


def scale_thetas_to_area(
    slot_widths_nm: Sequence[float],
    w_ratios: Sequence[float],
    z_tips_um: Sequence[float],
    h_teeths_um: Sequence[float],
    thetas_raw_deg: Sequence[float],
    target_area_um2: float = ISO_AREA_TARGET_UM2,
    max_theta_deg: float = DEFAULT_N3_MAX_TOOTH_ARC_DEG,
    R_min: float = DEFAULT_R_MIN_UM,
    R_max: float = DEFAULT_N3_R_MAX_UM,
) -> list[float]:
    """Scale per-track azimuthal angles so total active tooth area matches target_area_um2
    while clamping every tooth angle <= max_theta_deg to prevent aperture overhang."""
    cur_thetas = [min(float(th), max_theta_deg) for th in thetas_raw_deg]
    for _ in range(30):
        tmp = build_rztheta_design(
            "tmp", "tmp", slot_widths_nm, w_ratios, z_tips_um, h_teeths_um, cur_thetas, R_min=R_min, R_max=R_max
        )
        cur_area = active_tooth_area_um2(tmp.tracks)
        if abs(cur_area - target_area_um2) <= 1e-9:
            break
        uncapped_area = sum(
            4.0 * math.radians(t.tooth_arc_deg) * 0.5 * (t.r_inner + t.r_outer) * (t.r_tooth_out - t.r_tooth_in)
            for t in tmp.tracks
            if t.tooth_arc_deg < max_theta_deg - 1e-7
        )
        capped_area = cur_area - uncapped_area
        if uncapped_area <= 1e-12:
            break
        factor = (target_area_um2 - capped_area) / uncapped_area
        cur_thetas = [
            min(max_theta_deg, th * factor) if th < max_theta_deg - 1e-7 else max_theta_deg
            for th in cur_thetas
        ]
    return cur_thetas


def build_rztheta_sector_mesh(
    design: PeakSyncDesign,
    theta_deg: float = 3.0,
    n_r: int = 2,
    n_phi_tooth: int = 3,
    n_phi_bridge: int = 3,
    n_z: int = 2,
) -> ClutchSurfaceMesh:
    """Build exact 3D C4-sector boundary element surface mesh with per-track (r, z, theta) parameters."""
    rotor: list[Any] = []
    stator: list[Any] = []

    def emit(kind: str, r0: float, r1: float, p0: float, p1: float, z0: float, z1: float, sign: int, body: str) -> None:
        panel = repository_face(kind, r0, r1, math.degrees(p0), math.degrees(p1), z0, z1, sign, body)
        (rotor if body == "rotor" else stator).append(panel)

    for track in design.tracks:
        re = subdivisions(track.r_tooth_in, track.r_tooth_out, n_r)
        ze = subdivisions(track.z_tip, track.z_tip + track.h_teeth, n_z)
        for low_deg, high_deg, cap_low, cap_high in tooth_segments(theta_deg, track.tooth_arc_deg):
            low_phi, high_phi = math.radians(low_deg), math.radians(high_deg)
            pe = subdivisions(low_phi, high_phi, n_phi_tooth)
            for i in range(n_r):
                for j in range(n_phi_tooth):
                    emit("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[0], ze[0], -1, "rotor")
                    emit("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[-1], ze[-1], 1, "rotor")
            for j in range(n_phi_tooth):
                for k in range(n_z):
                    emit("radial", re[0], re[0], pe[j], pe[j + 1], ze[k], ze[k + 1], -1, "rotor")
                    emit("radial", re[-1], re[-1], pe[j], pe[j + 1], ze[k], ze[k + 1], 1, "rotor")
            for i in range(n_r):
                for k in range(n_z):
                    if cap_low:
                        emit("azimuthal", re[i], re[i + 1], pe[0], pe[0], ze[k], ze[k + 1], -1, "rotor")
                    if cap_high:
                        emit("azimuthal", re[i], re[i + 1], pe[-1], pe[-1], ze[k], ze[k + 1], 1, "rotor")

    radial_boundaries = [design.R_min]
    for track in design.tracks:
        radial_boundaries.extend((track.r_inner, track.r_outer))
    radial_boundaries.append(design.R_max)
    radial_edges: list[float] = [radial_boundaries[0]]
    interval_ids: list[int] = []
    for interval, (low, high) in enumerate(zip(radial_boundaries, radial_boundaries[1:])):
        radial_edges.extend(subdivisions(low, high, n_r)[1:].tolist())
        interval_ids.extend([interval] * n_r)

    angles = np.deg2rad(
        np.concatenate(
            (
                np.linspace(0.0, design.aperture_arc_deg, n_phi_tooth + 1),
                np.linspace(design.aperture_arc_deg, 90.0, n_phi_bridge + 1)[1:],
            )
        )
    )
    heights = np.unique(
        np.concatenate(
            (
                np.linspace(design.z_pad_top - design.t_landing_pad, design.z_pad_top, n_z + 1),
                np.linspace(-design.t_membrane, 0.0, n_z + 1),
            )
        )
    )
    ni, nj, nk = len(interval_ids), len(angles) - 1, len(heights) - 1

    def filled(i: int, j: int, k: int) -> bool:
        if i < 0 or i >= ni or k < 0 or k >= nk:
            return False
        j %= nj
        midpoint = (heights[k] + heights[k + 1]) / 2.0
        if j < n_phi_tooth:
            return interval_ids[i] % 2 == 0 and -design.t_membrane < midpoint < 0.0
        return design.z_pad_top - design.t_landing_pad < midpoint < design.z_pad_top

    for i in range(ni):
        for j in range(nj):
            for k in range(nk):
                if not filled(i, j, k):
                    continue
                r0, r1 = radial_edges[i], radial_edges[i + 1]
                p0, p1 = angles[j], angles[j + 1]
                z0, z1 = heights[k], heights[k + 1]
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

    base_tracks = [
        TrackSpec3D(t.r_inner, t.r_outer, t.r_tooth_in, t.r_tooth_out, t.z_tip, t.h_teeth, t.level)
        for t in design.tracks
    ]
    elements = tuple(make_track_element(t) for t in base_tracks)
    geometry = Geometry(
        R_min=design.R_min,
        R_max=design.R_max,
        t_membrane=design.t_membrane,
        t_landing_pad=design.t_landing_pad,
        z_tip=min(t.z_tip for t in design.tracks),
        h_teeth=max(t.h_teeth for t in design.tracks),
        theta_deg=theta_deg,
        tooth_arc_deg=design.tracks[0].tooth_arc_deg,
        aperture_arc_deg=design.aperture_arc_deg,
        elements=elements,
    )
    parameters = {
        "material": "Gold",
        "R_min": design.R_min,
        "R_max": design.R_max,
        "z_tip": geometry.z_tip,
        "h_teeth": geometry.h_teeth,
        "t_membrane": geometry.t_membrane,
        "t_landing_pad": geometry.t_landing_pad,
        "theta_deg": theta_deg,
        "tooth_arc_deg": geometry.tooth_arc_deg,
        "aperture_arc_deg": geometry.aperture_arc_deg,
        "elements": [dataclasses.asdict(e) for e in elements],
    }
    return ClutchSurfaceMesh(
        rotor=tuple(rotor),
        stator=tuple(stator),
        geometry=geometry,
        parameters=parameters,
        config=dict(parameters),
        panel_resolution={"n_r": n_r, "n_phi_tooth": n_phi_tooth, "n_phi_bridge": n_phi_bridge, "n_z": n_z},
    )


def evaluate_design_3d_bem(
    design: PeakSyncDesign,
    theta_deg: float = 3.0,
    n_r: int = 2,
    n_phi_tooth: int = 3,
    n_phi_bridge: int = 3,
    n_z: int = 2,
    n_xi: int = 24,
    num_threads: int = 8,
) -> dict[str, Any]:
    """Evaluate a 7-track 3D (r,z,theta) design in 3D Vector-Dyadic BEM with exact per-track force decomposition."""
    torch.set_num_threads(max(1, int(num_threads)))
    t0 = time.perf_counter()
    mesh = build_rztheta_sector_mesh(
        design,
        theta_deg=theta_deg,
        n_r=n_r,
        n_phi_tooth=n_phi_tooth,
        n_phi_bridge=n_phi_bridge,
        n_z=n_z,
    )
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    material = MaterialModel.from_parameters(mesh.parameters)

    track_ids = np.full(len(mesh.rotor), -1, dtype=int)
    for i, p in enumerate(mesh.rotor):
        v = np.asarray(p.vertices)
        vr = np.hypot(v[:, 0], v[:, 1])
        rmin, rmax = float(np.min(vr)), float(np.max(vr))
        for k, trk in enumerate(design.tracks):
            if rmin >= trk.r_tooth_in - 1e-7 and rmax <= trk.r_tooth_out + 1e-7:
                track_ids[i] = k
                break
    if np.any(track_ids < 0):
        raise RuntimeError(f"Unassigned rotor panels in {design.name}")
    dof_track_ids = np.repeat(track_ids, 2)

    char_gap_um = math.inf
    for sector in range(4):
        sp = stator.centroids @ _rotation(sector).T
        for c in rotor.centroids:
            char_gap_um = min(char_gap_um, float(np.min(np.linalg.norm(sp - c, axis=1))))
    k_eff = 1.0 / max(char_gap_um, 0.020)
    kappa_0 = 1.0 / 0.100
    kappas, weights, _ = _quadrature(n_xi, kappa_0)
    K = len(kappas)
    phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)

    def same_modes_torch(body: Any) -> np.ndarray:
        N = body.count
        sub_var = torch.from_numpy((body.areas[:, None] + body.areas[None, :]) / (32.0 * math.pi))
        area_scale = torch.from_numpy(np.sqrt(body.areas[:, None]) * np.sqrt(body.areas[None, :]) / (4.0 * math.pi))
        kap_t = torch.from_numpy(kappas)
        sec_blocks = np.zeros((4, K, 2 * N, 2 * N), dtype=np.float64)
        for sec in range(4):
            rot = _rotation(sec)
            src_pts = body.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, body.tangents)
            t_dot_t = torch.from_numpy(np.einsum("ima,jna->ijmn", body.tangents, src_tan))
            ker_sum = torch.zeros((K, N, N), dtype=torch.float64)
            for qt in range(4):
                for qs in range(4):
                    w = float(body.quad_weights[qt] * body.quad_weights[qs])
                    delta = torch.from_numpy(body.quad_points[:, qt, None, :] - src_pts[None, :, qs, :])
                    eff_d = torch.sqrt(torch.sum(delta**2, dim=2) + sub_var)
                    scale = (area_scale * w) / eff_d
                    ker_sum += torch.exp(-kap_t[:, None, None] * eff_d[None, :, :]) * scale[None, :, :]
            single = ker_sum[:, :, :, None, None] * t_dot_t[None, :, :, :, :]
            if sec == 0:
                idx = np.arange(N)
                for q, kap in enumerate(kappas):
                    diag = torch.from_numpy(_disk_self_term(body.areas, float(kap)))
                    single[q, idx, idx] = diag[:, None, None] * torch.eye(2, dtype=torch.float64)
            sec_blocks[sec] = single.permute(0, 1, 3, 2, 4).reshape(K, 2 * N, 2 * N).numpy()
        return np.einsum("ms,skij->kmij", phases, sec_blocks)

    def cross_modes_torch(target: Any, source: Any) -> tuple[np.ndarray, np.ndarray]:
        Nt, Ns = target.count, source.count
        M = Nt * Ns
        sub_var = torch.from_numpy((target.areas[:, None] + source.areas[None, :]) / (32.0 * math.pi))
        area_scale = torch.from_numpy(np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :]) / (4.0 * math.pi))
        qw = torch.from_numpy(target.quad_weights[:, None] * source.quad_weights[None, :]).reshape(16)
        rs_sec = np.zeros((4, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        dz_sec = np.zeros((4, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        u_z = torch.from_numpy(target.tangents[:, :, 2][:, None, :, None])
        tgt_q = torch.from_numpy(target.quad_points.transpose(1, 0, 2)[:, :, None, :])
        for sec in range(4):
            rot = _rotation(sec)
            src_pts = source.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, source.tangents)
            t_dot_t = torch.from_numpy(np.einsum("ima,jna->ijmn", target.tangents, src_tan))
            v_z = torch.from_numpy(src_tan[:, :, 2][None, :, None, :])
            src_q = torch.from_numpy(src_pts.transpose(1, 0, 2)[None, :, :, :])
            delta = (tgt_q[:, None, :, :, :] - src_q[:, :, None, :, :]).reshape(16, Nt, Ns, 3)
            eff_d = torch.sqrt(torch.sum(delta**2, dim=3) + sub_var[None, :, :])
            inv_d = 1.0 / eff_d
            scale = (area_scale[None, :, :] * qw[:, None, None]) * inv_d
            dz_over_d = delta[:, :, :, 2] * inv_d
            u_R = torch.einsum("ima,qija->qijm", torch.from_numpy(target.tangents), delta)
            v_R = torch.einsum("jna,qija->qijn", torch.from_numpy(src_tan), delta)
            R_inv2 = (inv_d**2)[:, :, :, None, None]
            Z = delta[:, :, :, 2][:, :, :, None, None]
            D = u_R[:, :, :, :, None] * v_R[:, :, :, None, :] * R_inv2
            dD_dz = (
                (u_z[None] * v_R[:, :, :, None, :] + u_R[:, :, :, :, None] * v_z[None]) * R_inv2
                - 2.0 * Z * D * R_inv2
            )
            D_c = D.reshape(16, M, 4).permute(1, 2, 0).reshape(M, 4, 16)
            dD_c = dD_dz.reshape(16, M, 4).permute(1, 2, 0).reshape(M, 4, 16)
            eff_d_f = eff_d.reshape(16, M)
            inv_d_f = inv_d.reshape(16, M)
            scale_f = scale.reshape(16, M)
            dz_d_f = dz_over_d.reshape(16, M)
            for qk, kap_val in enumerate(kappas):
                kap = float(kap_val)
                x = kap * eff_d_f
                ker = torch.exp(-x) * scale_f
                rad_deriv = -ker * (kap + inv_d_f)
                sc_dz = rad_deriv * dz_d_f
                inv = 1.0 / (1.0 + x)
                denom = 1.0 - inv + inv**2
                c_dir = (1.0 + inv + inv**2) / denom
                dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denom**2
                s_t = (0.5 * torch.sum(ker, dim=0)).reshape(Nt, Ns, 1, 1)
                dz_t = (0.5 * torch.sum(sc_dz, dim=0)).reshape(Nt, Ns, 1, 1)
                w_D = (-0.25 * ker * c_dir).T.reshape(M, 1, 16)
                w_dz_D = (-0.25 * sc_dz * c_dir - 0.25 * ker * dc_dir_dx * kap * dz_d_f).T.reshape(M, 1, 16)
                s_D = torch.sum(D_c * w_D, dim=2).reshape(Nt, Ns, 2, 2)
                dz_D = (torch.sum(D_c * w_dz_D, dim=2) + torch.sum(dD_c * w_D, dim=2)).reshape(Nt, Ns, 2, 2)
                single = s_t * t_dot_t + s_D
                dz = dz_t * t_dot_t + dz_D
                rs_sec[sec, qk] = single.permute(0, 2, 1, 3).reshape(2 * Nt, 2 * Ns).numpy()
                dz_sec[sec, qk] = dz.permute(0, 2, 1, 3).reshape(2 * Nt, 2 * Ns).numpy()
        return np.einsum("ms,skij->kmij", phases, rs_sec), np.einsum("ms,skij->kmij", phases, dz_sec)

    rr_modes = same_modes_torch(rotor)
    ss_modes = same_modes_torch(stator)
    rs_modes, dz_modes = cross_modes_torch(rotor, stator)

    dof_forces = np.zeros(2 * rotor.count, dtype=np.float64)
    total_energy = 0.0
    for q in range(K):
        kap = float(kappas[q])
        w_q = float(weights[q])
        tm, te, _ = material.channel_weights(kap, k_eff=k_eff)
        q_dof = np.zeros(2 * rotor.count, dtype=np.float64)
        q_e = 0.0
        for mode, mult in ((0, 1.0), (2, 1.0), (1, 2.0)):
            if mode in (0, 2):
                mr = torch.from_numpy(rr_modes[q, mode].real.copy())
                ms = torch.from_numpy(ss_modes[q, mode].real.copy())
                g = torch.from_numpy(rs_modes[q, mode].real.copy())
                dg = torch.from_numpy(dz_modes[q, mode].real.copy())
                sr, dsr = g.T.contiguous(), dg.T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.float64)
            else:
                mr = torch.from_numpy(rr_modes[q, mode].copy())
                ms = torch.from_numpy(ss_modes[q, mode].copy())
                g = torch.from_numpy(rs_modes[q, mode].copy())
                dg = torch.from_numpy(dz_modes[q, mode].copy())
                sr, dsr = g.conj().T.contiguous(), dg.conj().T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.complex128)
            lu_r, piv_r = torch.linalg.lu_factor(mr)
            lu_s, piv_s = torch.linalg.lu_factor(ms)
            x = torch.linalg.lu_solve(lu_r, piv_r, g)
            ns_col = sr.shape[1]
            z_all = torch.linalg.lu_solve(lu_s, piv_s, torch.cat((sr, dsr), dim=1))
            z, dz = z_all[:, :ns_col], z_all[:, ns_col:]
            coupling = x @ z
            B, C = dg @ z, x @ dz
            for ch_w in (tm, te):
                pw = ch_w**2
                y = eye - pw * coupling
                sign, logabsdet = torch.linalg.slogdet(y)
                if float(sign.real) <= 0.0:
                    raise RuntimeError(f"Non-positive slogdet in {design.name}")
                lu_y, piv_y = torch.linalg.lu_factor(y)
                U = torch.linalg.lu_solve(lu_y, piv_y, C)
                V = torch.linalg.lu_solve(lu_r, piv_r, torch.linalg.lu_solve(lu_y, piv_y, B, left=False), left=False)
                per_dof = -pw * (torch.diagonal(V).real + torch.diagonal(U).real).numpy()
                q_e += mult * float(logabsdet.item()) / (2.0 * math.pi)
                q_dof += mult * (-per_dof / (2.0 * math.pi))
        total_energy += w_q * q_e
        dof_forces += w_q * q_dof

    f_tracks_pN = [
        float(np.sum(dof_forces[dof_track_ids == k]) * MEEP_FORCE_TO_SI * 1e12)
        for k in range(len(design.tracks))
    ]
    r_centers_um = [0.5 * (t.r_inner + t.r_outer) for t in design.tracks]
    f_circ_tracks = [
        float(fk / (2.0 * math.pi * rk)) for fk, rk in zip(f_tracks_pN, r_centers_um)
    ]
    f_z_pN = float(np.sum(dof_forces) * MEEP_FORCE_TO_SI * 1e12)
    a_tooth = active_tooth_area_um2(design.tracks)
    return {
        "name": design.name,
        "family_role": design.family_role,
        "theta_deg": float(theta_deg),
        "F_z_pN": f_z_pN,
        "F_circ_sum_pN_per_um": float(sum(f_circ_tracks)),
        "A_tooth_um2": a_tooth,
        "F_per_A_pN_per_um2": float(f_z_pN / a_tooth),
        "f_tracks_pN": f_tracks_pN,
        "f_circ_tracks_pN_per_um": f_circ_tracks,
        "r_centers_um": r_centers_um,
        "slot_widths_nm": [round((t.r_outer - t.r_inner) * 1e3, 3) for t in design.tracks],
        "tooth_widths_nm": [round((t.r_tooth_out - t.r_tooth_in) * 1e3, 3) for t in design.tracks],
        "w_ratios": [round((t.r_tooth_out - t.r_tooth_in) / (t.r_outer - t.r_inner), 4) for t in design.tracks],
        "z_tips_nm": [round(t.z_tip * 1e3, 2) for t in design.tracks],
        "h_teeths_nm": [round(t.h_teeth * 1e3, 2) for t in design.tracks],
        "thetas_deg": [round(t.tooth_arc_deg, 4) for t in design.tracks],
        "z_pad_top_nm": round(design.z_pad_top * 1e3, 2),
        "energy": float(total_energy),
        "elapsed_s": float(time.perf_counter() - t0),
    }


def build_study_designs() -> list[PeakSyncDesign]:
    """Build the 9-design Peak-Synchronized (r, z, theta) & Area-Angle-Height Control suite
    with strictly invariant DEFAULT_Z_PAD_TOP_UM and canonical parameters from clutch_geometry_redesign."""
    n_tracks = len(CANTOR_WIDTHS_NM)
    base_w = [DEFAULT_N3_W1_RATIO] * n_tracks
    base_zt = [DEFAULT_Z_TIP_ROTATIONAL_UM] * n_tracks
    base_ht = [DEFAULT_H_TEETH_ROTATIONAL_UM] * n_tracks
    base_th = [DEFAULT_N3_TOOTH_ARC_DEG] * n_tracks

    d1 = build_rztheta_design(
        "Fractal_N3_Cantor7Track_FlatZ",
        "baseline_cantor_flatz",
        CANTOR_WIDTHS_NM,
        base_w,
        base_zt,
        base_ht,
        base_th,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )
    d2 = build_rztheta_design(
        "Ctrl_Uniform7Track_FlatZ",
        "ctrl_uniform_flatz",
        UNIFORM_WIDTHS_NM,
        base_w,
        base_zt,
        base_ht,
        base_th,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )
    d3 = build_rztheta_design(
        "Ctrl_Monotonic7Track_FlatZ",
        "ctrl_monotonic_flatz",
        MONOTONIC_WIDTHS_NM,
        base_w,
        base_zt,
        base_ht,
        base_th,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )

    w_by_gen = {1: 0.82, 2: 0.68, 3: DEFAULT_N3_W1_RATIO}
    w_cantor_sync = [w_by_gen[g] for g in DEFAULT_N3_CANTOR_GENERATIONS]
    zt_cantor_sync = [DEFAULT_N3_Z_TIPS_BY_GEN_UM[g] for g in DEFAULT_N3_CANTOR_GENERATIONS]
    ht_cantor_sync = [DEFAULT_N3_H_TEETH_BY_GEN_UM[g] for g in DEFAULT_N3_CANTOR_GENERATIONS]
    th_cantor_iso_raw = [DEFAULT_N3_ANGLES_BY_GEN_DEG[g] for g in DEFAULT_N3_CANTOR_GENERATIONS]
    th_cantor_iso = scale_thetas_to_area(
        CANTOR_WIDTHS_NM, w_cantor_sync, zt_cantor_sync, ht_cantor_sync, th_cantor_iso_raw, ISO_AREA_TARGET_UM2
    )
    d4 = build_rztheta_design(
        "Cantor_N3_PeakSync_IsoArea",
        "cantor_peaksync_isoarea",
        CANTOR_WIDTHS_NM,
        w_cantor_sync,
        zt_cantor_sync,
        ht_cantor_sync,
        th_cantor_iso,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )

    th_cantor_hf = [min(th * 1.15, DEFAULT_N3_MAX_TOOTH_ARC_DEG) for th in th_cantor_iso]
    d5 = build_rztheta_design(
        "Cantor_N3_PeakSync_HighForce",
        "cantor_peaksync_highforce",
        CANTOR_WIDTHS_NM,
        w_cantor_sync,
        zt_cantor_sync,
        ht_cantor_sync,
        th_cantor_hf,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )

    th_uni_iso = scale_thetas_to_area(
        UNIFORM_WIDTHS_NM, base_w, zt_cantor_sync, ht_cantor_sync, th_cantor_iso, ISO_AREA_TARGET_UM2
    )
    d6 = build_rztheta_design(
        "Ctrl_Uniform_IsoAreaAngleHeight",
        "ctrl_uniform_iso_aah",
        UNIFORM_WIDTHS_NM,
        base_w,
        zt_cantor_sync,
        ht_cantor_sync,
        th_uni_iso,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )

    anti_gens = [DEFAULT_N3_CANTOR_GENERATIONS[i] for i in DEFAULT_N3_OUT_OF_PHASE_SLOT_ORDER]
    w_anti = [w_by_gen[g] for g in anti_gens]
    zt_anti = [DEFAULT_N3_Z_TIPS_BY_GEN_UM[g] for g in anti_gens]
    ht_anti = [DEFAULT_N3_H_TEETH_BY_GEN_UM[g] for g in anti_gens]
    th_anti_raw = [DEFAULT_N3_ANGLES_BY_GEN_DEG[g] for g in anti_gens]
    th_anti_iso = scale_thetas_to_area(
        CANTOR_WIDTHS_NM, w_anti, zt_anti, ht_anti, th_anti_raw, ISO_AREA_TARGET_UM2
    )
    d7 = build_rztheta_design(
        "Ctrl_OutOfPhase_IsoAreaAngleHeight",
        "ctrl_outofphase_iso_aah",
        CANTOR_WIDTHS_NM,
        w_anti,
        zt_anti,
        ht_anti,
        th_anti_iso,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )

    th_mono_rad_iso = scale_thetas_to_area(
        MONOTONIC_WIDTHS_NM, w_cantor_sync, zt_cantor_sync, ht_cantor_sync, th_cantor_iso, ISO_AREA_TARGET_UM2
    )
    d8 = build_rztheta_design(
        "Ctrl_Monotonic_SameRadialProf_IsoArea",
        "ctrl_monotonic_sameradial_iso",
        MONOTONIC_WIDTHS_NM,
        w_cantor_sync,
        zt_cantor_sync,
        ht_cantor_sync,
        th_mono_rad_iso,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )

    w_mono_gen = [w_by_gen[g] for g in DEFAULT_N3_MONOTONIC_GENERATIONS]
    zt_mono_gen = [DEFAULT_N3_Z_TIPS_BY_GEN_UM[g] for g in DEFAULT_N3_MONOTONIC_GENERATIONS]
    ht_mono_gen = [DEFAULT_N3_H_TEETH_BY_GEN_UM[g] for g in DEFAULT_N3_MONOTONIC_GENERATIONS]
    th_mono_gen_raw = [DEFAULT_N3_ANGLES_BY_GEN_DEG[g] for g in DEFAULT_N3_MONOTONIC_GENERATIONS]
    th_mono_gen_iso = scale_thetas_to_area(
        MONOTONIC_WIDTHS_NM, w_mono_gen, zt_mono_gen, ht_mono_gen, th_mono_gen_raw, ISO_AREA_TARGET_UM2
    )
    d9 = build_rztheta_design(
        "Ctrl_Monotonic_SameGenRule_IsoArea",
        "ctrl_monotonic_samegen_iso",
        MONOTONIC_WIDTHS_NM,
        w_mono_gen,
        zt_mono_gen,
        ht_mono_gen,
        th_mono_gen_iso,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )

    return [d1, d2, d3, d4, d5, d6, d7, d8, d9]


def render_figure(
    records: Sequence[Mapping[str, Any]],
    out_png: Path,
    out_pdf: Path,
) -> None:
    """Render 4-panel comparative diagnostic figure for Peak-Synchronized (r, z, theta) Cantor vs Controls."""
    by_name = {r["name"]: r for r in records}
    fig, axes = plt.subplots(2, 2, figsize=(14.5, 10.2), dpi=220)
    ax_bar, ax_trk = axes[0]
    ax_dens, ax_prof = axes[1]

    order = [
        ("Fractal_N3_Cantor7Track_FlatZ", "Cantor Flat-Z\n(Baseline)", "#1f77b4"),
        ("Cantor_N3_PeakSync_IsoArea", "Cantor Peak-Sync\n(Iso-Area)", "#d62728"),
        ("Cantor_N3_PeakSync_HighForce", "Cantor Peak-Sync\n(High-Force)", "#8c1d40"),
        ("Ctrl_Uniform7Track_FlatZ", "Uniform Flat-Z\n(Control)", "#7f7f7f"),
        ("Ctrl_Uniform_IsoAreaAngleHeight", "Uniform Peak-Sync\n(Iso-AAH Ctrl)", "#9edae5"),
        ("Ctrl_OutOfPhase_IsoAreaAngleHeight", "Out-of-Phase\n(Iso-AAH Ctrl)", "#bcbd22"),
        ("Ctrl_Monotonic_SameRadialProf_IsoArea", "Monotonic\n(Same Radial Prof)", "#ff9896"),
        ("Ctrl_Monotonic_SameGenRule_IsoArea", "Monotonic\n(Same Gen Rule)", "#ff7f0e"),
        ("Ctrl_Monotonic7Track_FlatZ", "Monotonic Flat-Z\n(A=0.336 um²)", "#2ca02c"),
    ]
    present = [(k, lbl, c) for k, lbl, c in order if k in by_name]
    x = np.arange(len(present))
    fz_vals = [float(by_name[k]["F_z_pN"]) for k, _, _ in present]
    colors = [c for _, _, c in present]
    bars = ax_bar.bar(x, fz_vals, color=colors, edgecolor="black", linewidth=0.8)
    ax_bar.axhline(0.0, color="black", linewidth=0.8)
    if "Fractal_N3_Cantor7Track_FlatZ" in by_name:
        ax_bar.axhline(
            float(by_name["Fractal_N3_Cantor7Track_FlatZ"]["F_z_pN"]),
            color="#1f77b4",
            linestyle="--",
            linewidth=1.1,
            label="Baseline Cantor Flat-Z",
        )
    for b, v in zip(bars, fz_vals):
        va = "bottom" if v >= 0 else "top"
        offset = 0.08 if v >= 0 else -0.22
        ax_bar.text(b.get_x() + b.get_width() / 2.0, v + offset, f"{v:+.2f}", ha="center", va=va, fontsize=8.5, fontweight="bold")
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels([lbl for _, lbl, _ in present], fontsize=8.0, rotation=22, ha="right")
    ax_bar.set_ylabel(r"Disengaged Repulsive Force $F_z(3^\circ)$ [pN]", fontsize=10)
    ax_bar.set_title("(a) 3D BEM Repulsion: Peak-Synchronized Cantor vs. Area-Angle-Height Controls", fontsize=10.5, fontweight="bold")
    ax_bar.set_ylim(min(-0.6, min(fz_vals) - 0.5), max(fz_vals) + 0.65)
    ax_bar.grid(axis="y", alpha=0.25)

    # Panel (b): Per-track force comparison across the 7 Cantor tracks
    trk_idx = np.arange(1, 8)
    w_bar = 0.20
    trk_series = [
        ("Fractal_N3_Cantor7Track_FlatZ", "Cantor Flat-Z (Baseline)", "#1f77b4", -1.5 * w_bar),
        ("Cantor_N3_PeakSync_IsoArea", "Cantor Peak-Sync (Iso-Area)", "#d62728", -0.5 * w_bar),
        ("Cantor_N3_PeakSync_HighForce", "Cantor Peak-Sync (High-Force)", "#8c1d40", 0.5 * w_bar),
        ("Ctrl_OutOfPhase_IsoAreaAngleHeight", "Out-of-Phase Ctrl (Iso-AAH)", "#bcbd22", 1.5 * w_bar),
    ]
    for k, lbl, c, dx in trk_series:
        if k in by_name:
            ax_trk.bar(trk_idx + dx, by_name[k]["f_tracks_pN"], width=w_bar, color=c, edgecolor="black", linewidth=0.6, label=lbl)
    ax_trk.axhline(0.0, color="black", linewidth=0.8)
    ax_trk.set_xticks(trk_idx)
    ax_trk.set_xticklabels([f"T{i}\n({int(w)}nm)" for i, w in enumerate(CANTOR_WIDTHS_NM, 1)], fontsize=8.5)
    ax_trk.set_ylabel(r"Per-Track Axial Force $F_{z,k}$ [pN]", fontsize=10)
    ax_trk.set_title("(b) Per-Track Unlocking of Gen-1 (450 nm), Gen-2 (150 nm) & Outer Gen-3 (50 nm)", fontsize=10.5, fontweight="bold")
    ax_trk.legend(fontsize=8.0, loc="upper right")
    ax_trk.grid(axis="y", alpha=0.25)

    # Panel (c): Force per unit active tooth area F_z / A_tooth and Circumference-Normalized sum F_{z,k}/(2 pi R_k)
    fa_vals = [float(by_name[k]["F_per_A_pN_per_um2"]) for k, _, _ in present]
    fc_vals = [float(by_name[k]["F_circ_sum_pN_per_um"]) * 10.0 for k, _, _ in present]
    ax_dens.bar(x - 0.18, fa_vals, width=0.35, color=colors, edgecolor="black", linewidth=0.7, label=r"$F_z / A_{\mathrm{tooth}}$ [pN/$\mu$m$^2$]")
    ax_dens.bar(x + 0.18, fc_vals, width=0.35, color=colors, edgecolor="black", linewidth=0.7, hatch="//", alpha=0.78, label=r"$10 \times \sum_k F_{z,k}/(2\pi R_k)$ [0.1 pN/$\mu$m]")
    ax_dens.axhline(0.0, color="black", linewidth=0.8)
    ax_dens.set_xticks(x)
    ax_dens.set_xticklabels([lbl for _, lbl, _ in present], fontsize=8.0, rotation=22, ha="right")
    ax_dens.set_ylabel("Normalized Force Efficiency", fontsize=10)
    ax_dens.set_title("(c) Active-Area Efficiency & Circumference-Normalized Track Force", fontsize=10.5, fontweight="bold")
    ax_dens.legend(fontsize=8.5, loc="upper right")
    ax_dens.grid(axis="y", alpha=0.25)

    # Panel (d): Synchronized (r, z, theta) geometric profile across the 7 Cantor tracks
    if "Cantor_N3_PeakSync_IsoArea" in by_name:
        rec_iso = by_name["Cantor_N3_PeakSync_IsoArea"]
        ax_prof2 = ax_prof.twinx()
        l1 = ax_prof.plot(trk_idx, rec_iso["h_teeths_nm"], "o-", color="#d62728", linewidth=2.0, label=r"Stepped Tooth Height $H_k$ [nm]")
        l2 = ax_prof.plot(trk_idx, rec_iso["tooth_widths_nm"], "s--", color="#1f77b4", linewidth=1.8, label=r"Peak-Matched Tooth Width $w_k$ [nm]")
        l3 = ax_prof2.plot(trk_idx, rec_iso["thetas_deg"], "^-", color="#2ca02c", linewidth=2.0, label=r"Chord-Locked Tooth Angle $\Delta\theta_k$ [deg]")
        ax_prof.set_xticks(trk_idx)
        ax_prof.set_xticklabels([f"T{i}\n({int(w)}nm)" for i, w in enumerate(CANTOR_WIDTHS_NM, 1)], fontsize=8.5)
        ax_prof.set_ylabel("Height $H_k$ / Tooth Width $w_k$ [nm]", fontsize=10, color="#1f77b4")
        ax_prof2.set_ylabel(r"Azimuthal Tooth Angle $\Delta\theta_k$ [deg]", fontsize=10, color="#2ca02c")
        ax_prof.set_title(r"(d) Peak-Synchronized $(r, z, \theta)$ Cantor Profile ($A_{\mathrm{tooth}} = 0.3104\ \mu\mathrm{m}^2$)", fontsize=10.5, fontweight="bold")
        lines = l1 + l2 + l3
        ax_prof.legend(lines, [ln.get_label() for ln in lines], fontsize=8.0, loc="upper right")
        ax_prof.grid(alpha=0.25)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
    fig.savefig(out_pdf)
    plt.close(fig)


def write_markdown_summary(out_md: Path, payload: Mapping[str, Any]) -> None:
    """Write human-readable Markdown report summarizing the Peak-Synchronized (r, z, theta) study."""
    recs = payload["records"]
    lines = [
        "# Peak-Synchronized 3D $(r, z, \\theta)$ $N=3$ Cantor Clutch & Area-Angle-Height Control Study",
        "",
        f"- **Generated (UTC)**: `{payload['generated_at_utc']}`",
        f"- **Quadrature**: `n_xi = {payload['solver_config']['n_xi']}`, `n_r = {payload['solver_config']['n_r']}`, "
        f"`n_phi_tooth = {payload['solver_config']['n_phi_tooth']}`, `n_z = {payload['solver_config']['n_z']}`",
        "",
        "## 1. Comparative Summary Table ($\\theta = 3^\\circ$ Disengaged Open-Slot Repulsion)",
        "",
        "| Design Name | Role | $A_{\\text{tooth}}$ [$\\mu\\text{m}^2$] | $F_z(3^\\circ)$ [pN] | $F_z / A_{\\text{tooth}}$ [pN/$\\mu\\text{m}^2$] | $\\sum_k F_{z,k}/(2\\pi R_k)$ [pN/$\\mu\\text{m}$] | Track Forces $[F_1,\\dots,F_7]$ [pN] |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for r in recs:
        trks_str = ", ".join(f"{x:+.3f}" for x in r["f_tracks_pN"])
        lines.append(
            f"| `{r['name']}` | `{r['family_role']}` | {r['A_tooth_um2']:.4f} | **{r['F_z_pN']:+.4f}** | "
            f"{r['F_per_A_pN_per_um2']:+.2f} | {r['F_circ_sum_pN_per_um']:+.4f} | `[{trks_str}]` |"
        )
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-xi", type=int, default=24, help="Imaginary-frequency quadrature order (default: 24)")
    parser.add_argument("--num-threads", type=int, default=8, help="PyTorch CPU threads (default: 8)")
    parser.add_argument("--max-steps", type=int, default=0, help="Optional cap on evaluated designs (0 = all 9)")
    args = parser.parse_args(argv)

    designs = build_study_designs()
    if args.max_steps < 0:
        raise ValueError("--max-steps must be >= 0")
    is_micro = 0 < args.max_steps < len(designs)
    selected_designs = designs[: args.max_steps] if is_micro else designs

    src_text = inspect.getsource(sys.modules[__name__])
    code_hash = hashlib.sha256(src_text.encode("utf-8")).hexdigest()[:16]
    now_iso = datetime.now(timezone.utc).isoformat()

    records: list[dict[str, Any]] = []
    for idx, des in enumerate(selected_designs, 1):
        rec = evaluate_design_3d_bem(des, theta_deg=3.0, n_xi=int(args.n_xi), num_threads=int(args.num_threads))
        records.append(rec)
        print(
            f"[{idx}/{len(selected_designs)}] {rec['name']:38s} | Fz={rec['F_z_pN']:+.4f} pN | "
            f"A={rec['A_tooth_um2']:.4f} um^2 | F/A={rec['F_per_A_pN_per_um2']:+.2f} | "
            f"F_circ={rec['F_circ_sum_pN_per_um']:+.4f} | trks={[round(x, 3) for x in rec['f_tracks_pN']]}",
            flush=True,
        )

    by_name = {r["name"]: r for r in records}
    summary: dict[str, Any] = {}
    if not is_micro:
        base_cantor = by_name["Fractal_N3_Cantor7Track_FlatZ"]
        iso_cantor = by_name["Cantor_N3_PeakSync_IsoArea"]
        hf_cantor = by_name["Cantor_N3_PeakSync_HighForce"]
        uni_flatz = by_name["Ctrl_Uniform7Track_FlatZ"]
        uni_aah = by_name["Ctrl_Uniform_IsoAreaAngleHeight"]
        anti_aah = by_name["Ctrl_OutOfPhase_IsoAreaAngleHeight"]
        mono_rad = by_name["Ctrl_Monotonic_SameRadialProf_IsoArea"]
        mono_gen = by_name["Ctrl_Monotonic_SameGenRule_IsoArea"]
        mono_flatz = by_name["Ctrl_Monotonic7Track_FlatZ"]

        gain_iso_vs_flatz_pct = 100.0 * (iso_cantor["F_z_pN"] - base_cantor["F_z_pN"]) / base_cantor["F_z_pN"]
        gain_hf_vs_flatz_pct = 100.0 * (hf_cantor["F_z_pN"] - base_cantor["F_z_pN"]) / base_cantor["F_z_pN"]
        ratio_iso_vs_uni_aah = iso_cantor["F_z_pN"] / uni_aah["F_z_pN"]
        gain_iso_vs_mono_rad_pct = 100.0 * (iso_cantor["F_z_pN"] - mono_rad["F_z_pN"]) / mono_rad["F_z_pN"]
        summary = {
            "gain_iso_vs_flatz_pct": gain_iso_vs_flatz_pct,
            "gain_hf_vs_flatz_pct": gain_hf_vs_flatz_pct,
            "ratio_iso_vs_uni_aah": ratio_iso_vs_uni_aah,
            "gain_iso_vs_mono_samerad_pct": gain_iso_vs_mono_rad_pct,
        }

    payload = {
        "generated_at_utc": now_iso,
        "execution_status": "micro_probe_complete" if is_micro else "complete",
        "solver_config": {
            "n_r": 2,
            "n_phi_tooth": 3,
            "n_phi_bridge": 3,
            "n_z": 2,
            "n_xi": int(args.n_xi),
            "code_version_hash": code_hash,
        },
        "summary": summary,
        "records": records,
    }

    suffix = "_micro" if is_micro else ""
    out_json = ROOT / "results" / f"n3_peak_synchronized_rztheta_study{suffix}.json"
    out_md = ROOT / "results" / f"n3_peak_synchronized_rztheta_study{suffix}.md"
    out_png = ROOT / "figures" / f"fig_n3_peak_synchronized_rztheta{suffix}.png"
    out_pdf = ROOT / "figures" / f"fig_n3_peak_synchronized_rztheta{suffix}.pdf"

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=out_json.parent, delete=False, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out_json)

    write_markdown_summary(out_md, payload)
    render_figure(records, out_png, out_pdf)

    if not is_micro:
        set_solver_provenance(
            "bem",
            {
                "benchmark": "n3_peak_synchronized_rztheta_study",
                "n_xi": int(args.n_xi),
                "n_designs": len(records),
                "code_version_hash": code_hash,
                "executed_at": now_iso,
            },
        )
        log_step(
            "n3_peak_synchronized_rztheta_study",
            {
                "status": "complete",
                "n_designs": len(records),
                "n_xi": int(args.n_xi),
            },
            solver_name="bem",
        )
        metrics_to_log: dict[str, float] = {
            "n3_peaksync_cantor_flatz_fz_pn": float(base_cantor["F_z_pN"]),
            "n3_peaksync_cantor_isoarea_fz_pn": float(iso_cantor["F_z_pN"]),
            "n3_peaksync_cantor_isoarea_fa": float(iso_cantor["F_per_A_pN_per_um2"]),
            "n3_peaksync_cantor_isoarea_fcirc": float(iso_cantor["F_circ_sum_pN_per_um"]),
            "n3_peaksync_cantor_highforce_fz_pn": float(hf_cantor["F_z_pN"]),
            "n3_peaksync_cantor_highforce_area_um2": float(hf_cantor["A_tooth_um2"]),
            "n3_peaksync_cantor_highforce_fcirc": float(hf_cantor["F_circ_sum_pN_per_um"]),
            "n3_peaksync_ctrl_uni_flatz_fz_pn": float(uni_flatz["F_z_pN"]),
            "n3_peaksync_ctrl_uni_aah_fz_pn": float(uni_aah["F_z_pN"]),
            "n3_peaksync_ctrl_outofphase_aah_fz_pn": float(anti_aah["F_z_pN"]),
            "n3_peaksync_ctrl_mono_samerad_fz_pn": float(mono_rad["F_z_pN"]),
            "n3_peaksync_ctrl_mono_samegen_fz_pn": float(mono_gen["F_z_pN"]),
            "n3_peaksync_ctrl_mono_flatz_fz_pn": float(mono_flatz["F_z_pN"]),
            "n3_peaksync_gain_iso_vs_flatz_pct": float(gain_iso_vs_flatz_pct),
            "n3_peaksync_gain_hf_vs_flatz_pct": float(gain_hf_vs_flatz_pct),
            "n3_peaksync_ratio_iso_vs_uni_aah": float(ratio_iso_vs_uni_aah),
            "n3_peaksync_gain_iso_vs_mono_samerad_pct": float(gain_iso_vs_mono_rad_pct),
        }
        for m_key, m_val in metrics_to_log.items():
            log_metric(m_key, m_val, step_id="n3_peak_synchronized_rztheta_study", solver_name="bem", defer_save=True)
        first_k = next(iter(metrics_to_log))
        log_metric(first_k, metrics_to_log[first_k], step_id="n3_peak_synchronized_rztheta_study", solver_name="bem", defer_save=False)
        export_macros(str(ROOT / "results" / "provenance_metrics.json"), str(ROOT / "results" / "macros_results.tex"))
        save_plot_provenance(str(out_png), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        save_plot_provenance(str(out_pdf), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
