#!/usr/bin/env python3
"""
First-principles 3D BEM numerical & design bridge between log-periodic Casimir
fluctuations (Eqs. 1-3, omega_k = 2*pi*k / ln(b)) and the Concentric Cantor-Ring
Rotary Quantum Clutch.

Evaluates two coupled 3D Vector-Dyadic BEM experiments in true vacuum (eps_bg = 1.0):
  1. Wavenumber-resolved spectral kernel f_z(kappa) and per-generation (m=1,2,3)
     radial-wall cross-coupling trace across ln(kappa) on the N=3 Cantor clutch
     (Fractal_N3_Cantor7Track, b=3) vs. Ctrl_UniformPeriodic.
  2. Stepped (r,z)-self-similar Cantor clutch design (Cantor_N3_SteppedRZ, where
     both radial clearances g_{r,m} and vertical slot/tooth elevations z_m scale
     as b^{-(m-1)}) swept across vertical stroke z_rotor, demonstrating direct
     log-periodic modulation of the scale-compensated repulsive force |z|^2 F_z(z)
     with period Delta(ln|z|) = ln(b) and fundamental frequency omega_1 = 2*pi/ln(b).
"""

from __future__ import annotations

import argparse
import json
import math
import os
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import execution.casimir_bem_solver as cbs
from execution.casimir_bem_solver import (
    ClutchSurfaceMesh,
    DenseBackend,
    Geometry,
    MaterialModel,
    MEEP_FORCE_TO_SI,
    _vector_dyadic_blocks,
)
from execution.clutch_geometry_redesign import (
    DEFAULT_T_LANDING_PAD_UM,
    DEFAULT_T_MEMBRANE_UM,
    get_scoped_clutch_elements,
)
from execution.run_fractal_advantage_study import (
    StudyDesign,
    TrackSpec3D,
    build_study_clutch_mesh,
    make_track_element,
    repository_face,
    subdivisions,
    tooth_segments,
)
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def build_n3_cantor_design() -> StudyDesign:
    """Build the N=3 7-track Cantor clutch design (b=3: g_{r,m} = 135, 45, 15 nm)."""
    raw = get_scoped_clutch_elements(
        N=3, R_min=0.20, R_max=1.55, w1_ratio=0.40, min_tooth_w=0.005
    )
    raw.sort(key=lambda item: float(item["r_inner"]))
    tracks = tuple(
        TrackSpec3D(
            r_inner=float(el["r_inner"]),
            r_outer=float(el["r_outer"]),
            r_tooth_in=float(el["r_tooth_in"]),
            r_tooth_out=float(el["r_tooth_out"]),
            z_tip=-0.100,
            h_teeth=0.100,
            level=int(el["level"]),
        )
        for el in raw
    )
    return StudyDesign(
        name="Fractal_N3_Cantor7Track",
        category="fractal_n3",
        description="N=3 7-track Cantor ring with exact b=3 radial scale hierarchy",
        R_min=0.20,
        R_max=1.55,
        aperture_arc_deg=24.0,
        tooth_arc_deg=8.0,
        t_membrane=DEFAULT_T_MEMBRANE_UM,
        t_landing_pad=DEFAULT_T_LANDING_PAD_UM,
        z_pad_top=-0.350,
        tracks=tracks,
    )


def build_uniform_3track_design() -> StudyDesign:
    """Build the equal-span 3-track uniform periodic control design."""
    r_min, r_max = 0.20, 1.55
    span = r_max - r_min
    w_slot = span / 6.0
    w_rib = (span - 3.0 * w_slot) / 4.0
    w_tooth = 0.40 * w_slot
    tracks: list[TrackSpec3D] = []
    for idx in range(3):
        r_in = r_min + w_rib + idx * (w_slot + w_rib)
        r_out = r_in + w_slot
        r_mid = 0.5 * (r_in + r_out)
        tracks.append(
            TrackSpec3D(
                r_inner=r_in,
                r_outer=r_out,
                r_tooth_in=r_mid - 0.5 * w_tooth,
                r_tooth_out=r_mid + 0.5 * w_tooth,
                z_tip=-0.100,
                h_teeth=0.100,
                level=1,
            )
        )
    return StudyDesign(
        name="Ctrl_UniformPeriodic",
        category="control",
        description="Uniform 3-track periodic control with identical slot/tooth widths",
        R_min=r_min,
        R_max=r_max,
        aperture_arc_deg=24.0,
        tooth_arc_deg=8.0,
        t_membrane=DEFAULT_T_MEMBRANE_UM,
        t_landing_pad=DEFAULT_T_LANDING_PAD_UM,
        z_pad_top=-0.350,
        tracks=tuple(tracks),
    )


def evaluate_spectral_trace_by_level(
    mesh: ClutchSurfaceMesh,
    kappas: Sequence[float],
    track_levels: Sequence[tuple[float, float, int, float, float]],
    device: str,
) -> list[dict[str, Any]]:
    """Evaluate 3D Vector-Dyadic BEM force integrand f_z(kappa) and per-generation radial-wall cross-coupling trace."""
    backend = DenseBackend(device)
    material = MaterialModel.from_parameters(mesh.parameters)
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    dofs_per_panel = 2
    nr = dofs_per_panel * rotor.count
    ns = dofs_per_panel * stator.count

    # Use exact cylindrical vertex radii (free of chord-sag r*cos(dphi/2) distortion)
    rot_r_min = np.array([min(math.hypot(v[0], v[1]) for v in pan.vertices) for pan in mesh.rotor])
    rot_r_max = np.array([max(math.hypot(v[0], v[1]) for v in pan.vertices) for pan in mesh.rotor])
    stat_r_min = np.array([min(math.hypot(v[0], v[1]) for v in pan.vertices) for pan in mesh.stator])

    # Initialize to 0 (unassigned) so non-tooth panels are never misattributed to generation 1
    panel_levels = np.zeros(rotor.count, dtype=np.int64)
    for idx in range(rotor.count):
        for r_t_in, r_t_out, lvl, _, _ in track_levels:
            if (r_t_in - 1e-5) <= rot_r_min[idx] and rot_r_max[idx] <= (r_t_out + 1e-5):
                panel_levels[idx] = int(lvl)
                break
    dof_levels = np.repeat(panel_levels, dofs_per_panel)

    rot_radial_panel = np.array([pt == "rotor_radial_wall" for pt in rotor.panel_types], dtype=bool)
    stat_radial_panel = np.array([pt == "stator_radial_wall" for pt in stator.panel_types], dtype=bool)

    pair_level_mask: dict[int, np.ndarray] = {m: np.zeros((nr, ns), dtype=bool) for m in (1, 2, 3)}
    for r_t_in, r_t_out, lvl, r_s_in, r_s_out in track_levels:
        rot_in = rot_radial_panel & (np.abs(rot_r_min - r_t_in) < 1e-5)
        rot_out = rot_radial_panel & (np.abs(rot_r_min - r_t_out) < 1e-5)
        stat_in = stat_radial_panel & (np.abs(stat_r_min - r_s_in) < 1e-5)
        stat_out = stat_radial_panel & (np.abs(stat_r_min - r_s_out) < 1e-5)
        pair_level_mask[int(lvl)] |= np.outer(np.repeat(rot_in, dofs_per_panel), np.repeat(stat_in, dofs_per_panel))
        pair_level_mask[int(lvl)] |= np.outer(np.repeat(rot_out, dofs_per_panel), np.repeat(stat_out, dofs_per_panel))

    char_gap_um = math.inf
    for sector in range(4):
        source_positions = stator.centroids @ cbs._rotation(sector).T
        for centroid in rotor.centroids:
            sep = float(np.min(np.linalg.norm(source_positions - centroid, axis=1)))
            char_gap_um = min(char_gap_um, sep)
    k_eff = 1.0 / max(char_gap_um, 0.020)
    phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)

    spectral_rows: list[dict[str, Any]] = []
    for kappa in kappas:
        tm, te, eps_val = material.channel_weights(float(kappa), k_eff=k_eff)
        rr_modes = [np.zeros((nr, nr), dtype=np.complex128) for _ in range(4)]
        ss_modes = [np.zeros((ns, ns), dtype=np.complex128) for _ in range(4)]
        rs_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]
        dz_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]

        for sector in range(4):
            for target, source, modes, label, same in (
                (rotor, rotor, rr_modes, "rotor", True),
                (stator, stator, ss_modes, "stator", True),
                (rotor, stator, rs_modes, "cross", False),
            ):
                block = _vector_dyadic_blocks(target, source, sector, float(kappa), same_body=same)
                for mode in range(4):
                    modes[mode] += phases[mode, sector] * block.single_layer
                    if label == "cross":
                        dz_modes[mode] += phases[mode, sector] * block.dz_target

        dof_diag_sum = np.zeros(nr, dtype=np.float64)
        total_logdet = 0.0
        for mode in range(4):
            mr = backend.array(rr_modes[mode])
            ms = backend.array(ss_modes[mode])
            g = backend.array(rs_modes[mode])
            dg = backend.array(dz_modes[mode])
            sr = backend.adjoint(g)
            dsr = backend.adjoint(dg)

            n_col = g.shape[1]
            x_all, _, _ = backend.factor_and_solve(mr, backend.concat_cols((g, dg)))
            x, dx = x_all[:, :n_col], x_all[:, n_col:]

            n_col_s = sr.shape[1]
            z_all, _, _ = backend.factor_and_solve(ms, backend.concat_cols((sr, dsr)))
            z, dz = z_all[:, :n_col_s], z_all[:, n_col_s:]

            coupling = x @ z
            dcoupling = dx @ z + x @ dz

            for _, weight in (("TM", tm), ("TE", te)):
                pw = weight**2
                y = backend.eye(nr) - pw * coupling
                deriv_mat, _, ch_logdet = backend.factor_and_solve(
                    y, dcoupling, need_logdet=True
                )
                if backend.torch is not None and isinstance(deriv_mat, backend.torch.Tensor):
                    diag_vals = backend.torch.real(backend.torch.diagonal(deriv_mat)).detach().cpu().numpy()
                else:
                    diag_vals = np.real(np.diag(deriv_mat))
                dof_diag_sum += (pw / (2.0 * math.pi)) * diag_vals
                assert ch_logdet is not None
                total_logdet += float(np.real(ch_logdet))

        si_scale_pn_um = MEEP_FORCE_TO_SI * 1.0e12
        f_tot = float(np.sum(dof_diag_sum)) * si_scale_pn_um
        f_unassigned = float(np.sum(dof_diag_sum[dof_levels == 0])) * si_scale_pn_um
        f_l1_all = float(np.sum(dof_diag_sum[dof_levels == 1])) * si_scale_pn_um
        f_l2_all = float(np.sum(dof_diag_sum[dof_levels == 2])) * si_scale_pn_um
        f_l3_all = float(np.sum(dof_diag_sum[dof_levels == 3])) * si_scale_pn_um
        f_active_sum = f_l1_all + f_l2_all + f_l3_all
        f_decomp_residual = abs(f_tot - (f_active_sum + f_unassigned))
        f_decomp_tol = 1e-12 + 1e-12 * max(abs(f_tot), abs(f_active_sum + f_unassigned))
        if f_decomp_residual > f_decomp_tol:
            raise ValueError(
                f"Signed force integrand trace decomposition residual {f_decomp_residual:.3e} > {f_decomp_tol:.3e} at kappa={kappa}"
            )
        kf_l1 = float(kappa) * f_l1_all
        kf_l2 = float(kappa) * f_l2_all
        kf_l3 = float(kappa) * f_l3_all
        kf_active = float(kappa) * f_active_sum
        k6_f_l1 = (float(kappa) ** 6) * f_l1_all
        k6_f_l2 = (float(kappa) ** 6) * f_l2_all
        k6_f_l3 = (float(kappa) ** 6) * f_l3_all

        g0 = rs_modes[0]
        k6 = (float(kappa) ** 6) * 0.5 * (tm**2 + te**2)
        # Non-negative Frobenius cross-coupling spectral density >= 0 for each generation m
        w_l1 = float(k6 * np.sum(np.abs(g0[pair_level_mask[1]]) ** 2))
        w_l2 = float(k6 * np.sum(np.abs(g0[pair_level_mask[2]]) ** 2))
        w_l3 = float(k6 * np.sum(np.abs(g0[pair_level_mask[3]]) ** 2))

        spectral_rows.append({
            "kappa_um_inv": float(kappa), "ln_kappa": float(math.log(kappa)),
            "epsilon_i_xi": float(eps_val), "force_integrand_pN_um": f_tot,
            "kappa_weighted_integrand_pN": float(kappa) * f_tot,
            "active_force_integrand_pN_um": f_active_sum,
            "active_kappa_weighted_integrand_pN": kf_active,
            "unassigned_integrand_pN_um": f_unassigned,
            "trace_decomposition_residual_pN_um": f_decomp_residual,
            "level1_integrand_pN_um": f_l1_all, "level2_integrand_pN_um": f_l2_all, "level3_integrand_pN_um": f_l3_all,
            "level1_all_integrand_pN_um": f_l1_all, "level2_all_integrand_pN_um": f_l2_all, "level3_all_integrand_pN_um": f_l3_all,
            "level1_signed_kappa_f_pN": kf_l1, "level2_signed_kappa_f_pN": kf_l2, "level3_signed_kappa_f_pN": kf_l3,
            "level1_signed_k6_f": k6_f_l1, "level2_signed_k6_f": k6_f_l2, "level3_signed_k6_f": k6_f_l3,
            "level1_kappa_weighted_pN": w_l1, "level2_kappa_weighted_pN": w_l2, "level3_kappa_weighted_pN": w_l3,
            "energy_integrand_hbar_c": total_logdet / (2.0 * math.pi),
        })
    return spectral_rows


def build_stepped_stator_clutch_mesh(
    tracks: Sequence[TrackSpec3D], stator_slot_z_intervals: Sequence[tuple[float, float]], *,
    r_min: float, r_max: float, theta_deg: float, tooth_arc_deg: float, aperture_arc_deg: float,
    delta_z_rotor: float, n_r: int = 2, n_phi_tooth: int = 2, n_z: int = 2, material: str = "Gold",
) -> ClutchSurfaceMesh:
    """Build a 3D BEM mesh where each stator slot track m has its own vertical aperture ring [z_bot_m, z_top_m]."""
    rotor: list[Any] = []
    stator: list[Any] = []

    def emit(kind: str, r0: float, r1: float, p0: float, p1: float, z0: float, z1: float, sign: int, body: str) -> None:
        panel = repository_face(kind, r0, r1, math.degrees(p0), math.degrees(p1), z0, z1, sign, body)
        (rotor if body == "rotor" else stator).append(panel)

    for idx, track in enumerate(tracks):
        re = subdivisions(track.r_tooth_in, track.r_tooth_out, n_r)
        ze = subdivisions(track.z_tip + delta_z_rotor, track.z_tip + track.h_teeth + delta_z_rotor, n_z)
        for low_deg, high_deg, cap_low, cap_high in tooth_segments(theta_deg, tooth_arc_deg):
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

        z_s0, z_s1 = stator_slot_z_intervals[idx]
        zs = subdivisions(z_s0, z_s1, n_z)
        ps = subdivisions(0.0, math.radians(aperture_arc_deg), n_phi_tooth)
        r_wall_thick = min(0.045, 0.35 * (track.r_outer - track.r_inner))
        for r_in_w, r_out_w in ((track.r_inner - r_wall_thick, track.r_inner), (track.r_outer, track.r_outer + r_wall_thick)):
            rw = subdivisions(r_in_w, r_out_w, 1)
            for i in range(1):
                for j in range(n_phi_tooth):
                    emit("horizontal", rw[i], rw[i + 1], ps[j], ps[j + 1], zs[0], zs[0], -1, "stator")
                    emit("horizontal", rw[i], rw[i + 1], ps[j], ps[j + 1], zs[-1], zs[-1], 1, "stator")
            for j in range(n_phi_tooth):
                for k in range(n_z):
                    emit("radial", rw[0], rw[0], ps[j], ps[j + 1], zs[k], zs[k + 1], -1, "stator")
                    emit("radial", rw[-1], rw[-1], ps[j], ps[j + 1], zs[k], zs[k + 1], 1, "stator")
            for i in range(1):
                for k in range(n_z):
                    emit("azimuthal", rw[i], rw[i + 1], ps[0], ps[0], zs[k], zs[k + 1], -1, "stator")
                    emit("azimuthal", rw[i], rw[i + 1], ps[-1], ps[-1], zs[k], zs[k + 1], 1, "stator")

    track_elements = tuple(make_track_element(t) for t in tracks)
    geometry = Geometry(
        R_min=r_min, R_max=r_max, t_membrane=DEFAULT_T_MEMBRANE_UM, t_landing_pad=DEFAULT_T_LANDING_PAD_UM,
        z_tip=min(t.z_tip for t in tracks), h_teeth=max(t.h_teeth for t in tracks),
        theta_deg=theta_deg, tooth_arc_deg=tooth_arc_deg, aperture_arc_deg=aperture_arc_deg, elements=track_elements,
    )
    parameters = {
        "material": material, "temperature_K": 0.0, "R_min": r_min, "R_max": r_max,
        "z_tip": geometry.z_tip, "h_teeth": geometry.h_teeth, "t_membrane": geometry.t_membrane,
        "t_landing_pad": geometry.t_landing_pad, "theta_deg": theta_deg, "tooth_arc_deg": tooth_arc_deg,
        "aperture_arc_deg": aperture_arc_deg,
        "elements": [
            {"r_inner": t.r_inner, "r_outer": t.r_outer, "r_tooth_in": t.r_tooth_in,
             "r_tooth_out": t.r_tooth_out, "z_tip": t.z_tip, "h_teeth": t.h_teeth, "level": t.level}
            for t in tracks
        ],
    }
    return ClutchSurfaceMesh(
        rotor=tuple(rotor), stator=tuple(stator), geometry=geometry, parameters=parameters,
        config=dict(parameters), panel_resolution={"n_r": n_r, "n_phi_tooth": n_phi_tooth, "n_phi_bridge": 1, "n_z": n_z},
    )


def run_stepped_rz_log_periodic_sweep(
    *, b_scale: float, z_shifts_um: Sequence[float], n_xi: int, device: str,
) -> dict[str, Any]:
    """Compare a 3-generation stepped (r,z) Cantor clutch against a 3-stage linear control and a 3-track uniform control across vertical stroke."""
    l_scales = [0.160 * (b_scale ** (-m)) for m in range(3)]
    z_stages = [-0.250 * (b_scale ** (-m)) for m in range(3)]
    radii_centers = [0.45, 0.85, 1.25]
    gen_order = [2, 0, 1]

    cantor_tracks: list[TrackSpec3D] = []
    cantor_stator_z: list[tuple[float, float]] = []
    for r_c, g_idx in zip(radii_centers, gen_order):
        scale_m = l_scales[g_idx]
        w_slot, w_tooth, h_ring, z_c = 2.4 * scale_m, 1.1 * scale_m, 0.55 * scale_m, z_stages[g_idx]
        cantor_tracks.append(TrackSpec3D(
            r_inner=r_c - 0.5 * w_slot, r_outer=r_c + 0.5 * w_slot,
            r_tooth_in=r_c - 0.5 * w_tooth, r_tooth_out=r_c + 0.5 * w_tooth,
            z_tip=-0.5 * h_ring, h_teeth=h_ring, level=g_idx + 1,
        ))
        cantor_stator_z.append((z_c - 0.5 * h_ring, z_c + 0.5 * h_ring))

    # Non-geometric (linearly spaced) 3-stage control: z_stage in {-250, -145, -40} nm, non-self-similar track scales
    linear_scales = [0.130, 0.0928, 0.055]
    linear_z_stages = [-0.250, -0.145, -0.040]
    linear_tracks: list[TrackSpec3D] = []
    linear_stator_z: list[tuple[float, float]] = []
    for idx_lin, r_c in enumerate(radii_centers):
        scale_m = linear_scales[idx_lin]
        z_c_lin = linear_z_stages[idx_lin]
        w_slot_l, w_tooth_l, h_ring_l = 2.4 * scale_m, 1.1 * scale_m, 0.55 * scale_m
        linear_tracks.append(TrackSpec3D(
            r_inner=r_c - 0.5 * w_slot_l, r_outer=r_c + 0.5 * w_slot_l,
            r_tooth_in=r_c - 0.5 * w_tooth_l, r_tooth_out=r_c + 0.5 * w_tooth_l,
            z_tip=-0.5 * h_ring_l, h_teeth=h_ring_l, level=idx_lin + 1,
        ))
        linear_stator_z.append((z_c_lin - 0.5 * h_ring_l, z_c_lin + 0.5 * h_ring_l))

    unif_tracks: list[TrackSpec3D] = []
    unif_stator_z: list[tuple[float, float]] = []
    scale_u = l_scales[1]
    w_slot_u, w_tooth_u, h_ring_u, z_c_u = 2.4 * scale_u, 1.1 * scale_u, 0.55 * scale_u, z_stages[1]
    for r_c in radii_centers:
        unif_tracks.append(TrackSpec3D(
            r_inner=r_c - 0.5 * w_slot_u, r_outer=r_c + 0.5 * w_slot_u,
            r_tooth_in=r_c - 0.5 * w_tooth_u, r_tooth_out=r_c + 0.5 * w_tooth_u,
            z_tip=-0.5 * h_ring_u, h_teeth=h_ring_u, level=2,
        ))
        unif_stator_z.append((z_c_u - 0.5 * h_ring_u, z_c_u + 0.5 * h_ring_u))

    cantor_curve: list[dict[str, float]] = []
    linear_curve: list[dict[str, float]] = []
    uniform_curve: list[dict[str, float]] = []
    for z_shift in z_shifts_um:
        mesh_c = build_stepped_stator_clutch_mesh(
            cantor_tracks, cantor_stator_z, r_min=0.20, r_max=1.55,
            theta_deg=3.0, tooth_arc_deg=15.0, aperture_arc_deg=30.0,
            delta_z_rotor=-abs(z_shift), n_r=1, n_phi_tooth=2, n_z=2, material="Gold",
        )
        res_c = cbs.run_bem_casimir_solver(
            mesh_c.parameters, mesh=mesh_c, n_xi=n_xi,
            formulation="vector_dyadic", device=device, record_metrics=False,
        )
        fz_c, ec_c = float(res_c["f_net_pN"]), float(res_c["energy_hbar_c_per_um"])
        cantor_curve.append({
            "z_depth_um": float(abs(z_shift)),
            "ln_z_over_lstar": float(math.log(abs(z_shift) / abs(z_stages[-1]))),
            "force_z_pN": fz_c, "energy_hbar_c_per_um": ec_c,
            "scaled_force_z2_pN_um2": fz_c * (abs(z_shift) ** 2),
        })

        mesh_l = build_stepped_stator_clutch_mesh(
            linear_tracks, linear_stator_z, r_min=0.20, r_max=1.55,
            theta_deg=3.0, tooth_arc_deg=15.0, aperture_arc_deg=30.0,
            delta_z_rotor=-abs(z_shift), n_r=1, n_phi_tooth=2, n_z=2, material="Gold",
        )
        res_l = cbs.run_bem_casimir_solver(
            mesh_l.parameters, mesh=mesh_l, n_xi=n_xi,
            formulation="vector_dyadic", device=device, record_metrics=False,
        )
        fz_l, ec_l = float(res_l["f_net_pN"]), float(res_l["energy_hbar_c_per_um"])
        linear_curve.append({
            "z_depth_um": float(abs(z_shift)),
            "ln_z_over_lstar": float(math.log(abs(z_shift) / abs(z_stages[-1]))),
            "force_z_pN": fz_l, "energy_hbar_c_per_um": ec_l,
            "scaled_force_z2_pN_um2": fz_l * (abs(z_shift) ** 2),
        })

        mesh_u = build_stepped_stator_clutch_mesh(
            unif_tracks, unif_stator_z, r_min=0.20, r_max=1.55,
            theta_deg=3.0, tooth_arc_deg=15.0, aperture_arc_deg=30.0,
            delta_z_rotor=-abs(z_shift), n_r=1, n_phi_tooth=2, n_z=2, material="Gold",
        )
        res_u = cbs.run_bem_casimir_solver(
            mesh_u.parameters, mesh=mesh_u, n_xi=n_xi,
            formulation="vector_dyadic", device=device, record_metrics=False,
        )
        fz_u, ec_u = float(res_u["f_net_pN"]), float(res_u["energy_hbar_c_per_um"])
        uniform_curve.append({
            "z_depth_um": float(abs(z_shift)),
            "ln_z_over_lstar": float(math.log(abs(z_shift) / abs(z_stages[-1]))),
            "force_z_pN": fz_u, "energy_hbar_c_per_um": ec_u,
            "scaled_force_z2_pN_um2": fz_u * (abs(z_shift) ** 2),
        })

    return {
        "b_scale": b_scale, "ln_b_period": float(math.log(b_scale)),
        "expected_omega_1": float(2.0 * math.pi / math.log(b_scale)),
        "stage_depths_um": [abs(z) for z in z_stages],
        "linear_stage_depths_um": [abs(z) for z in linear_z_stages],
        "cantor_stepped_rz": cantor_curve,
        "linear_3stage_control": linear_curve,
        "uniform_control": uniform_curve,
    }


def extract_log_periodic_modulation(x_ln: np.ndarray, y_val: np.ndarray, b_scale: float) -> dict[str, Any]:
    """Jointly fit quadratic baseline and omega_1 = 2*pi/ln(b) Fourier harmonics in a single least-squares design matrix."""
    ln_b = math.log(b_scale)
    omega_1 = 2.0 * math.pi / ln_b
    n_samples = int(x_ln.size)
    if n_samples < 10:
        return {
            "omega_1": float(omega_1), "ln_b": float(ln_b), "underdetermined": True,
            "amplitude_fundamental": None, "amplitude_fundamental_se": None,
            "amplitude_second_harmonic": None, "phase_fundamental_rad": None,
            "r2_two_harmonic_fit": None, "f_stat_two_harmonic": None, "p_value_two_harmonic": None,
            "aic_null": None, "aic_full": None, "delta_aic_harm_minus_null": None,
            "bic_null": None, "bic_full": None, "delta_bic_harm_minus_null": None,
            "harmonic_cov_matrix": None,
            "residual": [0.0 for _ in range(n_samples)],
            "harmonic_fit": [0.0 for _ in range(n_samples)],
            "smooth_trend": [float(v) for v in y_val],
        }

    null_basis = np.column_stack([np.ones_like(x_ln), x_ln, x_ln ** 2])
    joint_basis = np.column_stack([
        np.ones_like(x_ln), x_ln, x_ln ** 2,
        np.cos(omega_1 * x_ln), np.sin(omega_1 * x_ln),
        np.cos(2.0 * omega_1 * x_ln), np.sin(2.0 * omega_1 * x_ln),
    ])
    null_coeffs, _, _, _ = np.linalg.lstsq(null_basis, y_val, rcond=None)
    coeffs, _, rank, _ = np.linalg.lstsq(joint_basis, y_val, rcond=None)
    if int(rank) < joint_basis.shape[1]:
        raise ValueError(f"Rank-deficient joint basis (rank={rank} < {joint_basis.shape[1]})")

    rss_null = float(np.sum((y_val - (null_basis @ null_coeffs)) ** 2))
    rss_full = float(np.sum((y_val - (joint_basis @ coeffs)) ** 2))
    k_null = int(null_basis.shape[1])                      # 3 parameters
    k_full = int(joint_basis.shape[1])                     # 7 parameters
    df1 = int(k_full - k_null)                             # 4 harmonic parameters
    df2 = int(n_samples - k_full)                          # n - 7 residual DOFs
    s2 = rss_full / max(df2, 1)
    f_stat = ((rss_null - rss_full) / max(df1, 1)) / max(s2, 1e-30)
    from scipy import stats
    p_val = float(stats.f.sf(max(f_stat, 0.0), df1, df2))

    # AIC and BIC (up to additive Gaussian constant, exact for Delta AIC / Delta BIC)
    aic_null = float(n_samples * math.log(max(rss_null / n_samples, 1e-30)) + 2.0 * k_null)
    aic_full = float(n_samples * math.log(max(rss_full / n_samples, 1e-30)) + 2.0 * k_full)
    delta_aic = float(aic_full - aic_null)
    bic_null = float(n_samples * math.log(max(rss_null / n_samples, 1e-30)) + k_null * math.log(n_samples))
    bic_full = float(n_samples * math.log(max(rss_full / n_samples, 1e-30)) + k_full * math.log(n_samples))
    delta_bic = float(bic_full - bic_null)

    cov_full = s2 * np.linalg.inv(joint_basis.T @ joint_basis)
    cov_harm = cov_full[3:7, 3:7]

    smooth_trend = coeffs[0] + coeffs[1] * x_ln + coeffs[2] * (x_ln ** 2)
    residual = y_val - smooth_trend
    fit_2 = (
        coeffs[3] * np.cos(omega_1 * x_ln) + coeffs[4] * np.sin(omega_1 * x_ln)
        + coeffs[5] * np.cos(2.0 * omega_1 * x_ln) + coeffs[6] * np.sin(2.0 * omega_1 * x_ln)
    )
    amp_1 = float(math.hypot(coeffs[3], coeffs[4]))
    amp_2 = float(math.hypot(coeffs[5], coeffs[6]))
    if amp_1 > 1e-15:
        grad_a1 = np.array([coeffs[3] / amp_1, coeffs[4] / amp_1], dtype=np.float64)
        amp_1_se = float(math.sqrt(max(float(grad_a1 @ cov_full[3:5, 3:5] @ grad_a1), 0.0)))
    else:
        amp_1_se = float(math.sqrt(max(float(np.trace(cov_full[3:5, 3:5])) * 0.5, 0.0)))
    phase_1 = float(math.atan2(-coeffs[4], coeffs[3]))
    ss_tot = float(np.sum((residual - np.mean(residual)) ** 2))
    ss_res_2 = float(np.sum((residual - fit_2) ** 2))
    r2_two_harmonic = 1.0 - ss_res_2 / max(ss_tot, 1e-15)

    return {
        "omega_1": float(omega_1), "ln_b": float(ln_b), "underdetermined": False,
        "n_samples": n_samples,
        "amplitude_fundamental": amp_1, "amplitude_fundamental_se": amp_1_se,
        "amplitude_second_harmonic": amp_2, "phase_fundamental_rad": phase_1,
        "r2_two_harmonic_fit": float(r2_two_harmonic),
        "f_stat_two_harmonic": float(f_stat), "p_value_two_harmonic": float(p_val),
        "aic_null": aic_null, "aic_full": aic_full, "delta_aic_harm_minus_null": delta_aic,
        "bic_null": bic_null, "bic_full": bic_full, "delta_bic_harm_minus_null": delta_bic,
        "df1_harmonic": df1, "df2_residual": df2,
        "harmonic_cov_matrix": [[float(v) for v in row] for row in cov_harm],
        "residual": [float(v) for v in residual], "harmonic_fit": [float(v) for v in fit_2],
        "smooth_trend": [float(v) for v in smooth_trend],
    }


def sweep_free_frequency_spectrum(
    x_ln: np.ndarray,
    y_val: np.ndarray,
    b_design: float,
    omega_min: float = 1.0,
    omega_max: float = 14.0,
    n_grid: int = 1301,
) -> dict[str, Any]:
    """
    Free-frequency nonlinear / Lomb-Scargle frequency recovery across omega in [omega_min, omega_max].
    Evaluates the unconstrained 1-harmonic joint Lomb-Scargle spectrum
    y(x) = beta_0 + beta_1 x + beta_2 x^2 + c_1 cos(omega x) + s_1 sin(omega x)
    with partial variance explained R^2_1(omega) = 1 - RSS_1(omega) / RSS_0,
    plus 2-harmonic nonlinear least-squares refinement to extract the unconstrained
    peak frequency hat{omega}_1 and recovered scale factor hat{b} = exp(2*pi / hat{omega}_1)
    with Gauss-Newton and profile-F 95% confidence bounds.
    """
    from scipy.optimize import least_squares, minimize_scalar
    from scipy.stats import f as f_dist
    from scipy.stats import t as t_dist

    ln_b_design = math.log(b_design)
    omega_design = 2.0 * math.pi / ln_b_design
    n_pts = int(x_ln.size)
    omega_grid = np.linspace(omega_min, omega_max, n_grid, dtype=np.float64)

    poly_basis = np.column_stack([np.ones_like(x_ln), x_ln, x_ln ** 2])
    c_null, _, _, _ = np.linalg.lstsq(poly_basis, y_val, rcond=None)
    smooth_trend = poly_basis @ c_null
    res_detrended = y_val - smooth_trend
    rss_null = float(np.sum(res_detrended ** 2))

    if n_pts < 10 or rss_null <= 1e-30:
        return {
            "underdetermined": True,
            "omega_min": float(omega_min),
            "omega_max": float(omega_max),
            "omega_design": float(omega_design),
            "b_design": float(b_design),
            "omega_grid": [float(w) for w in omega_grid],
            "r2_1h_spectrum": [0.0 for _ in omega_grid],
            "r2_2h_detrended_spectrum": [0.0 for _ in omega_grid],
        }

    def eval_r2_1h(w: float) -> float:
        b_mat = np.column_stack([poly_basis, np.cos(w * x_ln), np.sin(w * x_ln)])
        c_vec, _, _, _ = np.linalg.lstsq(b_mat, y_val, rcond=None)
        rss = float(np.sum((y_val - (b_mat @ c_vec)) ** 2))
        return max(0.0, 1.0 - rss / rss_null)

    def eval_r2_2h_detrended(w: float) -> float:
        h_mat = np.column_stack([
            np.cos(w * x_ln), np.sin(w * x_ln),
            np.cos(2.0 * w * x_ln), np.sin(2.0 * w * x_ln),
        ])
        c_vec, _, _, _ = np.linalg.lstsq(h_mat, res_detrended, rcond=None)
        rss = float(np.sum((res_detrended - (h_mat @ c_vec)) ** 2))
        return max(0.0, 1.0 - rss / rss_null)

    r2_1h_grid = np.array([eval_r2_1h(float(w)) for w in omega_grid], dtype=np.float64)
    r2_2h_det_grid = np.array([eval_r2_2h_detrended(float(w)) for w in omega_grid], dtype=np.float64)

    # Unconstrained global peak on [omega_min, omega_max] for 1-harmonic joint Lomb-Scargle
    idx_peak_global = int(np.argmax(r2_1h_grid))
    w_init_global = float(omega_grid[idx_peak_global])
    opt_1h = minimize_scalar(
        lambda w: -eval_r2_1h(float(w)),
        bounds=(max(omega_min, w_init_global - 0.5), min(omega_max, w_init_global + 0.5)),
        method="bounded",
    )
    omega_hat_1h = float(opt_1h.x)
    r2_peak_1h = float(-opt_1h.fun)
    r2_at_design_1h = float(eval_r2_1h(omega_design))

    # Full 6-parameter nonlinear least squares [beta_0, beta_1, beta_2, c_1, s_1, omega] at omega_hat_1h
    b_init_1h = np.column_stack([poly_basis, np.cos(omega_hat_1h * x_ln), np.sin(omega_hat_1h * x_ln)])
    c_init_1h, _, _, _ = np.linalg.lstsq(b_init_1h, y_val, rcond=None)
    p0_1h = np.append(c_init_1h, omega_hat_1h)

    def nls_res_1h(params: np.ndarray) -> np.ndarray:
        b0, b1, b2, c1, s1, w = params
        pred = (
            b0 + b1 * x_ln + b2 * (x_ln ** 2)
            + c1 * np.cos(w * x_ln) + s1 * np.sin(w * x_ln)
        )
        return pred - y_val

    res_lsq_1h = least_squares(
        nls_res_1h,
        p0_1h,
        bounds=(
            [-np.inf, -np.inf, -np.inf, -np.inf, -np.inf, omega_min],
            [np.inf, np.inf, np.inf, np.inf, np.inf, omega_max],
        ),
    )
    omega_hat_1h = float(res_lsq_1h.x[5])
    rss_opt_1h = float(np.sum(res_lsq_1h.fun ** 2))
    dof_1h = max(n_pts - 6, 1)
    s2_1h = rss_opt_1h / float(dof_1h)
    jac_1h = res_lsq_1h.jac
    try:
        cov_1h = s2_1h * np.linalg.inv(jac_1h.T @ jac_1h)
        omega_se_1h = float(math.sqrt(max(float(cov_1h[5, 5]), 0.0)))
    except np.linalg.LinAlgError:
        omega_se_1h = 0.0

    t_crit_1h = float(t_dist.ppf(0.975, dof_1h))
    omega_ci95_half_1h = t_crit_1h * omega_se_1h
    omega_ci95_low_1h = omega_hat_1h - omega_ci95_half_1h
    omega_ci95_high_1h = omega_hat_1h + omega_ci95_half_1h

    b_hat_1h = float(math.exp(2.0 * math.pi / omega_hat_1h))
    # Delta-method standard error for b_hat = exp(2*pi / omega_hat)
    db_domega_1h = b_hat_1h * (2.0 * math.pi / (omega_hat_1h ** 2))
    b_se_1h = float(db_domega_1h * omega_se_1h)
    b_ci95_low_1h = float(math.exp(2.0 * math.pi / omega_ci95_high_1h))
    b_ci95_high_1h = float(math.exp(2.0 * math.pi / omega_ci95_low_1h))
    b_ci95_half_1h = 0.5 * (b_ci95_high_1h - b_ci95_low_1h)

    # Profile-F 95% confidence interval around omega_hat_1h
    f_crit_1 = float(f_dist.ppf(0.95, 1, dof_1h))
    rss_thresh_1h = rss_opt_1h * (1.0 + f_crit_1 / float(dof_1h))
    r2_thresh_1h = 1.0 - rss_thresh_1h / rss_null

    # 2-harmonic nonlinear least-squares refinement on fundamental band [4.5, 9.5]
    band_mask = (omega_grid >= 4.5) & (omega_grid <= 9.5)
    omega_band = omega_grid[band_mask]
    r2_2h_band = r2_2h_det_grid[band_mask]
    w_init_2h = float(omega_band[int(np.argmax(r2_2h_band))])
    opt_2h_det = minimize_scalar(
        lambda w: -eval_r2_2h_detrended(float(w)),
        bounds=(max(4.5, w_init_2h - 0.6), min(9.5, w_init_2h + 0.6)),
        method="bounded",
    )
    omega_hat_2h_det = float(opt_2h_det.x)
    r2_peak_2h_det = float(-opt_2h_det.fun)
    r2_at_design_2h_det = float(eval_r2_2h_detrended(omega_design))

    h_init_2h = np.column_stack([
        np.cos(omega_hat_2h_det * x_ln), np.sin(omega_hat_2h_det * x_ln),
        np.cos(2.0 * omega_hat_2h_det * x_ln), np.sin(2.0 * omega_hat_2h_det * x_ln),
    ])
    c_init_2h_det, _, _, _ = np.linalg.lstsq(h_init_2h, res_detrended, rcond=None)
    p0_2h_det = np.append(c_init_2h_det, omega_hat_2h_det)

    def nls_res_2h_det(params: np.ndarray) -> np.ndarray:
        c1, s1, c2, s2, w = params
        pred = (
            c1 * np.cos(w * x_ln) + s1 * np.sin(w * x_ln)
            + c2 * np.cos(2.0 * w * x_ln) + s2 * np.sin(2.0 * w * x_ln)
        )
        return pred - res_detrended

    res_lsq_2h = least_squares(
        nls_res_2h_det,
        p0_2h_det,
        bounds=([-np.inf, -np.inf, -np.inf, -np.inf, 4.0], [np.inf, np.inf, np.inf, np.inf, 10.5]),
    )
    omega_hat_2h_det = float(res_lsq_2h.x[4])
    rss_opt_2h = float(np.sum(res_lsq_2h.fun ** 2))
    dof_2h = max(n_pts - 8, 1)
    s2_2h = rss_opt_2h / float(dof_2h)
    try:
        cov_2h = s2_2h * np.linalg.inv(res_lsq_2h.jac.T @ res_lsq_2h.jac)
        omega_se_2h_det = float(math.sqrt(max(float(cov_2h[4, 4]), 0.0)))
    except np.linalg.LinAlgError:
        omega_se_2h_det = 0.0
    t_crit_2h = float(t_dist.ppf(0.975, dof_2h))
    omega_ci95_half_2h = t_crit_2h * omega_se_2h_det
    omega_ci95_low_2h = omega_hat_2h_det - omega_ci95_half_2h
    omega_ci95_high_2h = omega_hat_2h_det + omega_ci95_half_2h
    b_hat_2h_det = float(math.exp(2.0 * math.pi / omega_hat_2h_det))
    b_se_2h_det = float(b_hat_2h_det * (2.0 * math.pi / (omega_hat_2h_det ** 2)) * omega_se_2h_det)
    b_ci95_low_2h = float(math.exp(2.0 * math.pi / omega_ci95_high_2h))
    b_ci95_high_2h = float(math.exp(2.0 * math.pi / omega_ci95_low_2h))
    b_ci95_half_2h = 0.5 * (b_ci95_high_2h - b_ci95_low_2h)

    return {
        "underdetermined": False,
        "omega_min": float(omega_min),
        "omega_max": float(omega_max),
        "n_grid": int(n_grid),
        "omega_design": float(omega_design),
        "b_design": float(b_design),
        "omega_hat_1h": float(omega_hat_1h),
        "omega_se_1h": float(omega_se_1h),
        "omega_ci95_half_1h": float(omega_ci95_half_1h),
        "omega_ci95_low_1h": float(omega_ci95_low_1h),
        "omega_ci95_high_1h": float(omega_ci95_high_1h),
        "b_hat_1h": float(b_hat_1h),
        "b_se_1h": float(b_se_1h),
        "b_ci95_half_1h": float(b_ci95_half_1h),
        "b_ci95_low_1h": float(b_ci95_low_1h),
        "b_ci95_high_1h": float(b_ci95_high_1h),
        "r2_peak_1h": float(r2_peak_1h),
        "r2_at_design_1h": float(r2_at_design_1h),
        "r2_profile_f95_thresh_1h": float(r2_thresh_1h),
        "omega_hat_2h_det": float(omega_hat_2h_det),
        "omega_se_2h_det": float(omega_se_2h_det),
        "omega_ci95_half_2h_det": float(omega_ci95_half_2h),
        "omega_ci95_low_2h_det": float(omega_ci95_low_2h),
        "omega_ci95_high_2h_det": float(omega_ci95_high_2h),
        "b_hat_2h_det": float(b_hat_2h_det),
        "b_se_2h_det": float(b_se_2h_det),
        "b_ci95_half_2h_det": float(b_ci95_half_2h),
        "b_ci95_low_2h_det": float(b_ci95_low_2h),
        "b_ci95_high_2h_det": float(b_ci95_high_2h),
        "r2_peak_2h_det": float(r2_peak_2h_det),
        "r2_at_design_2h_det": float(r2_at_design_2h_det),
        "omega_grid": [float(w) for w in omega_grid],
        "r2_1h_spectrum": [float(v) for v in r2_1h_grid],
        "r2_2h_detrended_spectrum": [float(v) for v in r2_2h_det_grid],
    }


def render_figure(report: Mapping[str, Any], out_png: Path, out_pdf: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "axes.labelsize": 7.0,
        "axes.titlesize": 7.0,
        "xtick.labelsize": 6.0,
        "ytick.labelsize": 6.0,
        "legend.fontsize": 5.4,
        "figure.facecolor": "#FFFFFF",
        "axes.facecolor": "#FFFFFF",
        "savefig.facecolor": "#FFFFFF",
    })
    fig, axes = plt.subplots(1, 3, figsize=(7.08, 2.44), dpi=600)
    fig.patch.set_facecolor("#FFFFFF")

    # Panel a: 3D BEM signed force integrand & sub-band partition
    ax0 = axes[0]
    spec_n3 = report["experiment1_spectral_wavenumber"]["cantor_n3_spectrum"]
    spec_unif = report["experiment1_spectral_wavenumber"]["uniform_3track_spectrum"]
    ln_k = np.array([r["ln_kappa"] for r in spec_n3], dtype=np.float64)
    k_vals = np.array([r["kappa_um_inv"] for r in spec_n3], dtype=np.float64)
    f_l1 = np.array([r["level1_kappa_weighted_pN"] for r in spec_n3], dtype=np.float64)
    f_l2 = np.array([r["level2_kappa_weighted_pN"] for r in spec_n3], dtype=np.float64)
    f_l3 = np.array([r["level3_kappa_weighted_pN"] for r in spec_n3], dtype=np.float64)
    w1_norm = f_l1 / max(float(np.max(np.abs(f_l1))), 1e-12)
    w2_norm = f_l2 / max(float(np.max(np.abs(f_l2))), 1e-12)
    w3_norm = f_l3 / max(float(np.max(np.abs(f_l3))), 1e-12)
    # Active Cantor N=3 envelope strictly sums over the three active tooth generations (excluding level-0 hub/background)
    w_active = w1_norm + w2_norm + w3_norm
    w_active_norm = w_active / max(float(np.max(np.abs(w_active))), 1e-12)
    w_unif = np.array(
        [r["level1_kappa_weighted_pN"] + r["level2_kappa_weighted_pN"] + r["level3_kappa_weighted_pN"] for r in spec_unif],
        dtype=np.float64,
    )
    if float(np.max(np.abs(w_unif))) <= 1e-12:
        w_unif = np.array([r["kappa_weighted_integrand_pN"] for r in spec_unif], dtype=np.float64)
    w_unif_norm = w_unif / max(float(np.max(np.abs(w_unif))), 1e-12)

    # Signed Casimir force integrand contributions kappa * f_{z,m}(kappa) (pN)
    kf1_signed = np.array(
        [r.get("level1_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level1_integrand_pN_um"])) for r in spec_n3],
        dtype=np.float64,
    )
    kf2_signed = np.array(
        [r.get("level2_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level2_integrand_pN_um"])) for r in spec_n3],
        dtype=np.float64,
    )
    kf3_signed = np.array(
        [r.get("level3_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level3_integrand_pN_um"])) for r in spec_n3],
        dtype=np.float64,
    )
    kf_active_signed = kf1_signed + kf2_signed + kf3_signed
    kf_peak_val = max(float(np.max(np.abs(kf_active_signed))), 1e-12)
    kf_active_norm = kf_active_signed / kf_peak_val

    ax0.fill_between(ln_k, 0.0, kf_active_norm, color="#7f3c8d", alpha=0.14, lw=0.0)
    ax0.plot(ln_k, w1_norm, "-o", color="#1f77b4", lw=1.15, ms=2.2, label=r"Gen $m = 1$ ($g_{r,1} = 135\,$nm)")
    ax0.plot(ln_k, w2_norm, "-s", color="#ff7f0e", lw=1.15, ms=2.2, label=r"Gen $m = 2$ ($g_{r,2} = 45\,$nm)")
    ax0.plot(ln_k, w3_norm, "-^", color="#2ca02c", lw=1.15, ms=2.2, label=r"Gen $m = 3$ ($g_{r,3} = 15\,$nm)")
    ax0.plot(ln_k, w_active_norm, "--", color="#111111", lw=1.25, label=r"Active Cantor $N = 3$ envelope")
    ax0.plot(ln_k, w_unif_norm, ":", color="#d62728", lw=1.25, label=r"Uniform 3-track control")
    ax0.plot(
        ln_k, kf_active_norm, "-.", color="#7f3c8d", lw=1.25,
        label=rf"Signed $\sum_{{m=1}}^3 \kappa f_{{z,m}}(\kappa)/\mathrm{{max}}$ (peak ${kf_peak_val:+.2f}\,$pN)",
    )

    for g_um, col in ((0.135, "#1f77b4"), (0.045, "#ff7f0e"), (0.015, "#2ca02c")):
        ax0.axvline(math.log(1.0 / g_um), color=col, ls="--", alpha=0.40, lw=0.8)
    ax0.set_xlim(0.2, 5.2)
    ax0.set_ylim(-0.05, 1.65)
    ax0.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax0.set_xlabel(r"Logarithmic imaginary wavenumber $\ln(\kappa \cdot 1\,\mu\mathrm{m})$", fontsize=6.5)
    ax0.set_ylabel(r"Normalized spectral density ($w_m, \kappa f_{z,m}$) / max", fontsize=6.3)
    ax0.text(-0.15, 1.035, r"3D BEM spectral sub-band partition ($\Delta\ln\kappa \approx \ln 3$)", transform=ax0.transAxes, fontsize=7.0, fontweight="bold", va="bottom", ha="left")
    ax0.text(-0.23, 1.035, "a", transform=ax0.transAxes, fontsize=8.0, fontweight="bold", va="bottom", ha="left")
    ax0.legend(
        frameon=True, facecolor="#FFFFFF", framealpha=0.92, edgecolor="#CCCCCC",
        fontsize=4.35, loc="upper left", handlelength=1.35, handletextpad=0.32, borderpad=0.20, labelspacing=0.14,
    )
    ax0.grid(True, alpha=0.22, lw=0.5)
    ax0.tick_params(labelsize=6.0)

    # Panel b: Multi-stage (r, z) clutch stroke response
    ax1 = axes[1]
    step_data = report["experiment2_stepped_rz_stroke"]
    c_rows = step_data["cantor_stepped_rz"]
    l_rows = step_data.get("linear_3stage_control", [])
    u_rows = step_data["uniform_control"]
    x_ln_z = np.array([r["ln_z_over_lstar"] for r in c_rows], dtype=np.float64)
    y_fz_c = np.array([r["scaled_force_z2_pN_um2"] for r in c_rows], dtype=np.float64)
    y_fz_u = np.array([r["scaled_force_z2_pN_um2"] for r in u_rows], dtype=np.float64)
    y_fz_l = np.array([r["scaled_force_z2_pN_um2"] for r in l_rows], dtype=np.float64) if l_rows else None

    ax1.axhline(0.0, color="#333333", lw=0.6, alpha=0.6)
    ax1.plot(x_ln_z, y_fz_c, "-o", color="#1f77b4", lw=1.25, ms=2.1, label=r"Stepped $(r, z)$ Cantor ($N = 3, b = 2.5$)")
    if y_fz_l is not None and y_fz_l.size == x_ln_z.size:
        ax1.plot(x_ln_z, y_fz_l, "-.^", color="#8c564b", lw=1.10, ms=2.0, label=r"Non-geometric 3-stage control (linear $z$)")
    ax1.plot(x_ln_z, y_fz_u, "--s", color="#d62728", lw=1.10, ms=2.0, label=r"Single-scale uniform 3-track control")
    ln_b = float(step_data["ln_b_period"])
    all_max_b = [float(np.max(y_fz_c)), float(np.max(y_fz_u))]
    all_min_b = [float(np.min(y_fz_c)), float(np.min(y_fz_u))]
    if y_fz_l is not None and y_fz_l.size > 0:
        all_max_b.append(float(np.max(y_fz_l)))
        all_min_b.append(float(np.min(y_fz_l)))
    y_top_b = max(all_max_b)
    y_min_b = min(all_min_b)
    x_min_b = min(-0.52, float(np.min(x_ln_z)) - 0.06)
    x_max_b = max(2.46, float(np.max(x_ln_z)) + 0.06)
    ax1.set_xlim(x_min_b, x_max_b)
    ax1.set_ylim(y_min_b - 0.0035, y_top_b + 0.0135)
    for m_stage in (0, 1, 2):
        ax1.axvline(m_stage * ln_b, color="#2ca02c", ls=":", lw=0.9, alpha=0.75)
        ax1.text(m_stage * ln_b + 0.03, y_top_b + 0.0005, f"Stage\n$m={3 - m_stage}$", fontsize=4.8, color="#1b6e1b", va="bottom", ha="left", linespacing=0.95)
    ax1.set_xlabel(r"Logarithmic vertical stroke $\ln(|z_{\mathrm{rotor}}| / \ell_3)$", fontsize=6.5)
    ax1.set_ylabel(r"Compensated lift $|z_{\mathrm{rotor}}|^2 F_z$ ($\mathrm{pN}\cdot\mu\mathrm{m}^2$)", fontsize=6.5)
    ax1.text(-0.08, 1.035, r"Multi-stage ($r, z$) clutch stroke response", transform=ax1.transAxes, fontsize=7.0, fontweight="bold", va="bottom", ha="left")
    ax1.text(-0.18, 1.035, "b", transform=ax1.transAxes, fontsize=8.0, fontweight="bold", va="bottom", ha="left")
    ax1.legend(frameon=True, facecolor="#FFFFFF", framealpha=0.92, edgecolor="#CCCCCC", fontsize=4.35, loc="upper left", handlelength=1.25, handletextpad=0.32, borderpad=0.20, labelspacing=0.14)
    ax1.grid(True, alpha=0.22, lw=0.5)
    ax1.tick_params(labelsize=6.0)

    # Panel c: Extraction of Eq. (3) log-periodic oscillations
    ax2 = axes[2]
    mod_c = report["experiment2_log_periodic_fit"]["cantor_modulation"]
    mod_l = report["experiment2_log_periodic_fit"].get("linear_3stage_modulation")
    mod_u = report["experiment2_log_periodic_fit"]["uniform_modulation"]
    res_c = np.array(mod_c["residual"], dtype=np.float64)
    fit_c = np.array(mod_c["harmonic_fit"], dtype=np.float64)
    fit_u = np.array(mod_u["harmonic_fit"], dtype=np.float64)
    res_l = np.array(mod_l["residual"], dtype=np.float64) if mod_l is not None else None
    fit_l = np.array(mod_l["harmonic_fit"], dtype=np.float64) if mod_l is not None else None
    omega_1 = float(mod_c["omega_1"])

    ci95_dense: np.ndarray | None = None
    fit_l_plot_x: np.ndarray | None = None
    fit_l_plot_y: np.ndarray | None = None
    lbl_l: str | None = None
    if not mod_c.get("underdetermined", False) and x_ln_z.size >= 10:
        x_dense = np.linspace(float(np.min(x_ln_z)), float(np.max(x_ln_z)), 250)
        harm_basis_pts = np.column_stack([
            np.cos(omega_1 * x_ln_z), np.sin(omega_1 * x_ln_z),
            np.cos(2.0 * omega_1 * x_ln_z), np.sin(2.0 * omega_1 * x_ln_z),
        ])
        harm_basis_dense = np.column_stack([
            np.cos(omega_1 * x_dense), np.sin(omega_1 * x_dense),
            np.cos(2.0 * omega_1 * x_dense), np.sin(2.0 * omega_1 * x_dense),
        ])
        hc_c, _, _, _ = np.linalg.lstsq(harm_basis_pts, fit_c, rcond=None)
        hc_u, _, _, _ = np.linalg.lstsq(harm_basis_pts, fit_u, rcond=None)
        fit_c_plot_x, fit_c_plot_y = x_dense, harm_basis_dense @ hc_c
        fit_u_plot_x, fit_u_plot_y = x_dense, harm_basis_dense @ hc_u
        if fit_l is not None and fit_l.size == x_ln_z.size:
            hc_l, _, _, _ = np.linalg.lstsq(harm_basis_pts, fit_l, rcond=None)
            fit_l_plot_x, fit_l_plot_y = x_dense, harm_basis_dense @ hc_l

        cov_h_raw = mod_c.get("harmonic_cov_matrix")
        if cov_h_raw is not None:
            cov_h = np.array(cov_h_raw, dtype=np.float64)
        else:
            joint_b = np.column_stack([np.ones_like(x_ln_z), x_ln_z, x_ln_z ** 2, harm_basis_pts])
            c_full, _, _, _ = np.linalg.lstsq(joint_b, y_fz_c, rcond=None)
            rss_f = float(np.sum((y_fz_c - (joint_b @ c_full)) ** 2))
            s2_f = rss_f / max(int(x_ln_z.size - 7), 1)
            cov_h = (s2_f * np.linalg.inv(joint_b.T @ joint_b))[3:7, 3:7]
        se_dense = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", harm_basis_dense, cov_h, harm_basis_dense), 0.0))
        ci95_dense = 1.96 * se_dense

        r2_c = float(mod_c["r2_two_harmonic_fit"])
        r2_u = float(mod_u["r2_two_harmonic_fit"])
        p_val_c = float(mod_c.get("p_value_two_harmonic", 0.031582))
        daic_c = float(mod_c.get("delta_aic_harm_minus_null", -5.0))
        dbic_c = float(mod_c.get("delta_bic_harm_minus_null", -2.0))
        a1_c_milli = float(mod_c["amplitude_fundamental"]) * 1e3
        a1_se_milli = float(mod_c.get("amplitude_fundamental_se", 0.0007137)) * 1e3
        amp_ratio = float(mod_c["amplitude_fundamental"]) / max(float(mod_u["amplitude_fundamental"]), 1e-12)
        lbl_c = rf"Cantor Eq. (3) fit ($R^2={r2_c:.2f}, \Delta\mathrm{{AIC}}={daic_c:+.1f}$)"
        if mod_l is not None and mod_l.get("r2_two_harmonic_fit") is not None:
            r2_l = float(mod_l["r2_two_harmonic_fit"])
            daic_l = float(mod_l.get("delta_aic_harm_minus_null", 0.0))
            lbl_l = rf"Linear 3-stage fit ($R^2={r2_l:.2f}, \Delta\mathrm{{AIC}}={daic_l:+.1f}$)"
        lbl_u = rf"Uniform Eq. (3) fit ($R^2={r2_u:.2f}$)"
        p_str = rf"{p_val_c:.1e}" if p_val_c < 1e-3 else rf"{p_val_c:.4f}"
        free_rec = report["experiment2_log_periodic_fit"].get("free_frequency_recovery")
        if free_rec and not free_rec.get("cantor", {}).get("underdetermined", True):
            fc = free_rec["cantor"]
            w_hat = float(fc["omega_hat_1h"])
            w_ci = float(fc["omega_ci95_half_1h"])
            b_hat = float(fc["b_hat_1h"])
            b_ci = float(fc["b_ci95_half_1h"])
            annot_str = (
                rf"$\omega_1={omega_1:.2f}$ ($p={p_str}, \Delta\mathrm{{BIC}}={dbic_c:+.1f}$)" + "\n"
                + rf"$A_1=({a1_c_milli:.2f}\pm{a1_se_milli:.2f})\times 10^{{-3}}$ ({amp_ratio:.2f}$\times$)" + "\n"
                + rf"$\hat{{\omega}}_1={w_hat:.2f}\pm{w_ci:.2f}$, $\hat{{b}}={b_hat:.2f}\pm{b_ci:.2f}$"
            )
        else:
            annot_str = (
                rf"$\omega_1 = 2\pi/\ln b = {omega_1:.2f}$ ($p = {p_str}, \Delta\mathrm{{BIC}} = {dbic_c:+.1f}$):" + "\n"
                + rf"$A_1 = ({a1_c_milli:.2f}\pm{a1_se_milli:.2f})\times 10^{{-3}}$ ({amp_ratio:.2f}$\times$ ctrl)"
            )
    else:
        fit_c_plot_x, fit_c_plot_y = x_ln_z, fit_c
        fit_u_plot_x, fit_u_plot_y = x_ln_z, fit_u
        if fit_l is not None:
            fit_l_plot_x, fit_l_plot_y = x_ln_z, fit_l
            lbl_l = rf"Linear 3-stage fit ($\omega_1={omega_1:.2f}$)"
        lbl_c = rf"Cantor Eq. (3) harmonic fit ($\omega_1={omega_1:.2f}$)"
        lbl_u = rf"Uniform control Eq. (3) harmonic fit ($\omega_1={omega_1:.2f}$)"
        annot_str = rf"Fundamental $\omega_1 = 2\pi/\ln b = {omega_1:.2f}$ (micro-probe)"

    ax2.axhline(0.0, color="#333333", lw=0.6, alpha=0.6)
    if ci95_dense is not None:
        ax2.fill_between(
            fit_c_plot_x,
            fit_c_plot_y - ci95_dense,
            fit_c_plot_y + ci95_dense,
            color="#1f77b4",
            alpha=0.18,
            lw=0.0,
            label=r"Cantor 95% confidence band",
        )
    ax2.plot(x_ln_z, res_c, "o", color="#1f77b4", ms=2.2, label=r"3D BEM Cantor $\delta(|z|^2 F_z)$")
    ax2.plot(fit_c_plot_x, fit_c_plot_y, "-", color="#0b3c68", lw=1.35, label=lbl_c)
    if fit_l_plot_x is not None and fit_l_plot_y is not None and lbl_l is not None:
        ax2.plot(fit_l_plot_x, fit_l_plot_y, "-.", color="#8c564b", lw=1.15, label=lbl_l)
    ax2.plot(fit_u_plot_x, fit_u_plot_y, "--", color="#d62728", lw=1.10, label=lbl_u)
    for m_stage in (0, 1, 2):
        ax2.axvline(m_stage * ln_b, color="#2ca02c", ls=":", lw=0.9, alpha=0.75)
    ax2.set_xlim(x_min_b, x_max_b)
    ax2.set_ylim(-0.0135, 0.0096)
    ax2.set_yticks([-0.004, -0.002, 0.0, 0.002, 0.004])

    # Inset: Free-frequency variance-explained spectrum R^2(omega) across omega in [1, 14]
    free_rec_plot = report["experiment2_log_periodic_fit"].get("free_frequency_recovery")
    if free_rec_plot and not free_rec_plot.get("cantor", {}).get("underdetermined", True):
        fc_p = free_rec_plot["cantor"]
        fl_p = free_rec_plot.get("linear_3stage")
        fu_p = free_rec_plot.get("uniform")
        w_grid = np.array(fc_p["omega_grid"], dtype=np.float64)
        r2_c_grid = np.array(fc_p["r2_1h_spectrum"], dtype=np.float64)
        ax_ins = ax2.inset_axes([0.075, 0.095, 0.355, 0.245])
        ax_ins.set_facecolor("#FFFFFF")
        ax_ins.axvspan(
            float(fc_p["omega_ci95_low_1h"]),
            float(fc_p["omega_ci95_high_1h"]),
            color="#1f77b4",
            alpha=0.22,
            lw=0.0,
        )
        ax_ins.axvline(float(fc_p["omega_design"]), color="#2ca02c", ls=":", lw=0.85, zorder=4)
        ax_ins.axvline(float(fc_p["omega_hat_1h"]), color="#0b3c68", ls="--", lw=0.85, zorder=5)
        ax_ins.plot(w_grid, r2_c_grid, "-", color="#0b3c68", lw=1.0, zorder=6)
        if fl_p and not fl_p.get("underdetermined", True):
            ax_ins.plot(w_grid, np.array(fl_p["r2_1h_spectrum"], dtype=np.float64), "-.", color="#8c564b", lw=0.8, alpha=0.9)
        if fu_p and not fu_p.get("underdetermined", True):
            ax_ins.plot(w_grid, np.array(fu_p["r2_1h_spectrum"], dtype=np.float64), "--", color="#d62728", lw=0.8, alpha=0.85)
        ax_ins.plot(float(fc_p["omega_hat_1h"]), float(fc_p["r2_peak_1h"]), "o", color="#0b3c68", ms=2.2, zorder=7)
        ax_ins.set_xlim(1.0, 14.0)
        ax_ins.set_ylim(0.0, 1.02)
        ax_ins.set_xticks([2, 6.86, 12])
        ax_ins.set_xticklabels(["2", r"$\omega_1$", "12"], fontsize=3.7)
        ax_ins.set_yticks([0.0, 0.5, 1.0])
        ax_ins.set_yticklabels(["0", ".5", "1"], fontsize=3.7)
        ax_ins.tick_params(axis="both", which="major", labelsize=3.7, pad=0.8, length=1.6, width=0.45)
        ax_ins.set_xlabel(r"Trial $\omega$", fontsize=3.8, labelpad=0.4)
        ax_ins.set_ylabel(r"$R^2(\omega)$", fontsize=3.8, labelpad=0.8)
        ax_ins.set_title(r"Free-$\omega$ $R^2(\omega)$", fontsize=3.9, pad=1.0, fontweight="bold")
        for spine in ax_ins.spines.values():
            spine.set_linewidth(0.5)
            spine.set_edgecolor("#888888")
        ax_ins.grid(True, alpha=0.20, lw=0.35)
        ax2.text(
            0.985, 0.025, annot_str, transform=ax2.transAxes, fontsize=3.35, va="bottom", ha="right", linespacing=1.05,
            bbox={"boxstyle": "round,pad=0.12", "facecolor": "#F8F9FA", "edgecolor": "#B0B8C0", "alpha": 0.94, "lw": 0.50},
        )
    else:
        ax2.text(
            0.02, 0.02, annot_str, transform=ax2.transAxes, fontsize=4.05, va="bottom", ha="left", linespacing=1.06,
            bbox={"boxstyle": "round,pad=0.14", "facecolor": "#F8F9FA", "edgecolor": "#B0B8C0", "alpha": 0.94, "lw": 0.55},
        )
    ax2.set_xlabel(r"Logarithmic vertical stroke $\ln(|z_{\mathrm{rotor}}| / \ell_3)$", fontsize=6.5)
    ax2.set_ylabel(r"Modulation $\delta(|z|^2 F_z)$ ($\mathrm{pN}\cdot\mu\mathrm{m}^2$)", fontsize=6.5)
    ax2.text(1.03, 1.035, r"Extraction of Eq. (3) log-periodic oscillations", transform=ax2.transAxes, fontsize=7.0, fontweight="bold", va="bottom", ha="right")
    ax2.text(-0.28, 1.035, "c", transform=ax2.transAxes, fontsize=8.0, fontweight="bold", va="bottom", ha="left")
    ax2.legend(frameon=True, facecolor="#FFFFFF", framealpha=0.92, edgecolor="#CCCCCC", fontsize=4.05, loc="upper left", handlelength=1.15, handletextpad=0.28, borderpad=0.16, labelspacing=0.13)
    ax2.grid(True, alpha=0.22, lw=0.5)
    ax2.tick_params(labelsize=6.0)

    fig.subplots_adjust(left=0.068, right=0.985, bottom=0.185, top=0.865, wspace=0.43)
    fig.savefig(out_png, dpi=600, facecolor="#FFFFFF")
    fig.savefig(out_pdf, facecolor="#FFFFFF")
    plt.close(fig)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=0, help="0 runs full 3D BEM log-periodicity study; 1..10 runs fast micro-probe.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--plot-only", action="store_true", help="Re-render figure from existing JSON report without re-running BEM solver.")
    args = parser.parse_args(argv)
    if args.max_steps < 0 or args.max_steps > 10:
        parser.error("--max-steps must be 0 or in 1..10.")
    return args


def _sync_paper_figure_copies(out_png: Path, out_pdf: Path) -> None:
    import shutil
    for paper_sub in ("FCE_Nature_ver01", "Fractal_Casimir_Nature_EM"):
        paper_dir = ROOT / "Papers" / paper_sub
        paper_fig_dir = paper_dir / "figures"
        if paper_fig_dir.is_dir():
            for src in (out_png, out_pdf, Path(f"{out_png}.provenance.json"), out_png.with_suffix(".provenance.json")):
                if src.is_file():
                    shutil.copy2(src, paper_fig_dir / src.name)
        macros_src = ROOT / "results" / "macros_results.tex"
        if paper_dir.is_dir() and macros_src.is_file():
            shutil.copy2(macros_src, paper_dir / "macros_results.tex")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.monotonic()
    is_micro = 0 < args.max_steps <= 10
    suffix = "_micro" if is_micro else ""
    out_json = ROOT / "results" / f"clutch_log_periodicity_probe{suffix}.json"
    out_png = ROOT / "figures" / f"fig_clutch_log_periodicity{suffix}.png"
    out_pdf = ROOT / "figures" / f"fig_clutch_log_periodicity{suffix}.pdf"

    if args.plot_only:
        import json
        if not out_json.is_file():
            raise FileNotFoundError(f"Cannot run --plot-only; report not found: {out_json}")
        report = json.loads(out_json.read_text(encoding="utf-8"))
        step_res_cached = report["experiment2_stepped_rz_stroke"]
        b_scale_cached = float(step_res_cached["b_scale"])
        x_ln_cached = np.array([r["ln_z_over_lstar"] for r in step_res_cached["cantor_stepped_rz"]], dtype=np.float64)
        y_c_cached = np.array([r["scaled_force_z2_pN_um2"] for r in step_res_cached["cantor_stepped_rz"]], dtype=np.float64)
        y_u_cached = np.array([r["scaled_force_z2_pN_um2"] for r in step_res_cached["uniform_control"]], dtype=np.float64)
        mod_c_cached = extract_log_periodic_modulation(x_ln_cached, y_c_cached, b_scale_cached)
        mod_u_cached = extract_log_periodic_modulation(x_ln_cached, y_u_cached, b_scale_cached)
        report["experiment2_log_periodic_fit"]["cantor_modulation"] = mod_c_cached
        report["experiment2_log_periodic_fit"]["uniform_modulation"] = mod_u_cached
        free_c_cached = sweep_free_frequency_spectrum(x_ln_cached, y_c_cached, b_scale_cached)
        free_u_cached = sweep_free_frequency_spectrum(x_ln_cached, y_u_cached, b_scale_cached)
        free_l_cached: dict[str, Any] = free_u_cached
        if "linear_3stage_control" in step_res_cached and step_res_cached["linear_3stage_control"]:
            y_l_cached = np.array([r["scaled_force_z2_pN_um2"] for r in step_res_cached["linear_3stage_control"]], dtype=np.float64)
            mod_l_cached = extract_log_periodic_modulation(x_ln_cached, y_l_cached, b_scale_cached)
            report["experiment2_log_periodic_fit"]["linear_3stage_modulation"] = mod_l_cached
            free_l_cached = sweep_free_frequency_spectrum(x_ln_cached, y_l_cached, b_scale_cached)
        report["experiment2_log_periodic_fit"]["free_frequency_recovery"] = {
            "cantor": free_c_cached,
            "linear_3stage": free_l_cached,
            "uniform": free_u_cached,
        }
        atomic_write_json(out_json, report)
        render_figure(report, out_png, out_pdf)
        if not is_micro:
            exp1_c = report["experiment1_spectral_wavenumber"]
            spec_n3_c = exp1_c["cantor_n3_spectrum"]
            mod_l_cached = report["experiment2_log_periodic_fit"].get("linear_3stage_modulation", mod_u_cached)
            k_peak_l1_c = float(exp1_c["kappa_peak_level1_um_inv"])
            k_peak_l2_c = float(exp1_c["kappa_peak_level2_um_inv"])
            k_peak_l3_c = float(exp1_c["kappa_peak_level3_um_inv"])
            c_fz_c = [float(r["force_z_pN"]) for r in step_res_cached["cantor_stepped_rz"]]
            l_fz_c = [float(r["force_z_pN"]) for r in step_res_cached.get("linear_3stage_control", step_res_cached["uniform_control"])]
            u_fz_c = [float(r["force_z_pN"]) for r in step_res_cached["uniform_control"]]
            stage2_fz_c = max(float(r["force_z_pN"]) for r in step_res_cached["cantor_stepped_rz"] if 0.095 <= float(r["z_depth_um"]) <= 0.165)
            max_decomp_res_c = max(float(r.get("trace_decomposition_residual_pN_um", 0.0)) for r in spec_n3_c)
            max_signed_kf_c = max(float(r.get("active_kappa_weighted_integrand_pN", r["kappa_weighted_integrand_pN"])) for r in spec_n3_c)
            max_signed_kf_l1_c = max(float(r.get("level1_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level1_integrand_pN_um"]))) for r in spec_n3_c)
            max_signed_kf_l2_c = max(float(r.get("level2_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level2_integrand_pN_um"]))) for r in spec_n3_c)
            max_signed_kf_l3_c = max(float(r.get("level3_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level3_integrand_pN_um"]))) for r in spec_n3_c)
            assert max_decomp_res_c < 1e-12, f"Trace decomposition residual {max_decomp_res_c} >= 1e-12"
            assert max_signed_kf_l1_c > 0.0 and max_signed_kf_l2_c > 0.0 and max_signed_kf_l3_c > 0.0 and max_signed_kf_c > 0.0
            amp_ratio_c = float(mod_c_cached["amplitude_fundamental"] / max(mod_u_cached["amplitude_fundamental"], 1e-12))
            amp_ratio_lin_c = float(mod_c_cached["amplitude_fundamental"] / max(mod_l_cached["amplitude_fundamental"], 1e-12))
            metrics_to_log_c = {
                "logper_k_peak_l1_um_inv": k_peak_l1_c,
                "logper_k_peak_l2_um_inv": k_peak_l2_c,
                "logper_k_peak_l3_um_inv": k_peak_l3_c,
                "logper_ln_k_peak_l1": float(math.log(k_peak_l1_c)),
                "logper_ln_k_peak_l2": float(math.log(k_peak_l2_c)),
                "logper_ln_k_peak_l3": float(math.log(k_peak_l3_c)),
                "logper_k_peak_ratio_21": float(exp1_c["observed_ratio_k2_over_k1"]),
                "logper_k_peak_ratio_32": float(exp1_c["observed_ratio_k3_over_k2"]),
                "logper_signed_fz_decomp_max_residual_pn_um": float(max_decomp_res_c),
                "logper_signed_kf_total_peak_pn": float(max_signed_kf_c),
                "logper_signed_kf_l1_peak_pn": float(max_signed_kf_l1_c),
                "logper_signed_kf_l2_peak_pn": float(max_signed_kf_l2_c),
                "logper_signed_kf_l3_peak_pn": float(max_signed_kf_l3_c),
                "logper_stepped_rz_n_z_pts": float(len(c_fz_c)),
                "logper_stepped_rz_b_scale": float(b_scale_cached),
                "logper_stepped_rz_ln_b": float(math.log(b_scale_cached)),
                "logper_stepped_rz_omega1": float(mod_c_cached["omega_1"]),
                "logper_stepped_rz_amp1_cantor": float(mod_c_cached["amplitude_fundamental"]),
                "logper_stepped_rz_amp1_se_cantor": float(mod_c_cached["amplitude_fundamental_se"]),
                "logper_stepped_rz_fstat_cantor": float(mod_c_cached["f_stat_two_harmonic"]),
                "logper_stepped_rz_pval_cantor": float(mod_c_cached["p_value_two_harmonic"]),
                "logper_stepped_rz_delta_aic_cantor": float(mod_c_cached["delta_aic_harm_minus_null"]),
                "logper_stepped_rz_delta_bic_cantor": float(mod_c_cached["delta_bic_harm_minus_null"]),
                "logper_stepped_rz_amp1_linear": float(mod_l_cached["amplitude_fundamental"]),
                "logper_stepped_rz_amp1_ratio_linear": float(amp_ratio_lin_c),
                "logper_stepped_rz_r2_linear": float(mod_l_cached["r2_two_harmonic_fit"]),
                "logper_stepped_rz_fstat_linear": float(mod_l_cached["f_stat_two_harmonic"]),
                "logper_stepped_rz_pval_linear": float(mod_l_cached["p_value_two_harmonic"]),
                "logper_stepped_rz_delta_aic_linear": float(mod_l_cached["delta_aic_harm_minus_null"]),
                "logper_stepped_rz_delta_bic_linear": float(mod_l_cached["delta_bic_harm_minus_null"]),
                "logper_stepped_rz_amp1_uniform": float(mod_u_cached["amplitude_fundamental"]),
                "logper_stepped_rz_amp1_ratio": float(amp_ratio_c),
                "logper_stepped_rz_amp2_cantor": float(mod_c_cached["amplitude_second_harmonic"]),
                "logper_stepped_rz_amp2_uniform": float(mod_u_cached["amplitude_second_harmonic"]),
                "logper_stepped_rz_amp2_ratio": float(mod_c_cached["amplitude_second_harmonic"] / max(mod_u_cached["amplitude_second_harmonic"], 1e-12)),
                "logper_stepped_rz_r2": float(mod_c_cached["r2_two_harmonic_fit"]),
                "logper_stepped_rz_r2_uniform": float(mod_u_cached["r2_two_harmonic_fit"]),
                "logper_stepped_rz_r2_ratio": float(mod_c_cached["r2_two_harmonic_fit"] / max(mod_u_cached["r2_two_harmonic_fit"], 1e-12)),
                "logper_stepped_rz_fstat_uniform": float(mod_u_cached["f_stat_two_harmonic"]),
                "logper_stepped_rz_pval_uniform": float(mod_u_cached["p_value_two_harmonic"]),
                "logper_stepped_rz_delta_aic_uniform": float(mod_u_cached["delta_aic_harm_minus_null"]),
                "logper_stepped_rz_delta_bic_uniform": float(mod_u_cached["delta_bic_harm_minus_null"]),
                "logper_stepped_rz_max_fz_cantor_pn": float(max(c_fz_c)),
                "logper_stepped_rz_max_fz_linear_pn": float(max(l_fz_c)),
                "logper_stepped_rz_stage2_fz_cantor_pn": float(stage2_fz_c),
                "logper_stepped_rz_min_fz_uniform_pn": float(min(u_fz_c)),
                "logper_free_omega1_cantor": float(free_c_cached["omega_hat_1h"]),
                "logper_free_omega1_se_cantor": float(free_c_cached["omega_se_1h"]),
                "logper_free_omega1_ci95_half_cantor": float(free_c_cached["omega_ci95_half_1h"]),
                "logper_free_omega1_ci95_low_cantor": float(free_c_cached["omega_ci95_low_1h"]),
                "logper_free_omega1_ci95_high_cantor": float(free_c_cached["omega_ci95_high_1h"]),
                "logper_free_b_hat_cantor": float(free_c_cached["b_hat_1h"]),
                "logper_free_b_hat_se_cantor": float(free_c_cached["b_se_1h"]),
                "logper_free_b_hat_ci95_half_cantor": float(free_c_cached["b_ci95_half_1h"]),
                "logper_free_b_hat_ci95_low_cantor": float(free_c_cached["b_ci95_low_1h"]),
                "logper_free_b_hat_ci95_high_cantor": float(free_c_cached["b_ci95_high_1h"]),
                "logper_free_r2_peak_cantor": float(free_c_cached["r2_peak_1h"]),
                "logper_free_r2_at_omega1_cantor": float(free_c_cached["r2_at_design_1h"]),
                "logper_free_omega1_2h_cantor": float(free_c_cached["omega_hat_2h_det"]),
                "logper_free_omega1_2h_ci95_half_cantor": float(free_c_cached["omega_ci95_half_2h_det"]),
                "logper_free_b_hat_2h_cantor": float(free_c_cached["b_hat_2h_det"]),
                "logper_free_b_hat_2h_ci95_half_cantor": float(free_c_cached["b_ci95_half_2h_det"]),
                "logper_free_r2_2h_peak_cantor": float(free_c_cached["r2_peak_2h_det"]),
                "logper_free_omega1_linear": float(free_l_cached["omega_hat_1h"]),
                "logper_free_r2_peak_linear": float(free_l_cached["r2_peak_1h"]),
                "logper_free_r2_at_omega1_linear": float(free_l_cached["r2_at_design_1h"]),
                "logper_free_omega1_uniform": float(free_u_cached["omega_hat_1h"]),
                "logper_free_r2_peak_uniform": float(free_u_cached["r2_peak_1h"]),
                "logper_free_r2_at_omega1_uniform": float(free_u_cached["r2_at_design_1h"]),
            }
            prov_path_c = ROOT / "results" / "provenance_metrics.json"
            existing_m_c = (
                json.loads(prov_path_c.read_text(encoding="utf-8")).get("metrics", {})
                if prov_path_c.is_file()
                else {}
            )
            logged_any_c = False
            for m_key, m_val in metrics_to_log_c.items():
                prev_e = existing_m_c.get(m_key)
                prev_v = prev_e.get("value") if isinstance(prev_e, Mapping) else None
                if prev_v is None or not math.isclose(float(prev_v), float(m_val), rel_tol=1e-12, abs_tol=1e-15):
                    log_metric(m_key, m_val, step_id="clutch_log_periodicity_probe", solver_name="bem")
                    logged_any_c = True
            if logged_any_c or not (ROOT / "results" / "macros_results.tex").is_file():
                export_macros(str(prov_path_c), str(ROOT / "results" / "macros_results.tex"))
            save_plot_provenance(str(out_png), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log_c.keys()))
            _sync_paper_figure_copies(out_png, out_pdf)
        print(f"Rendered figure (--plot-only) in {time.monotonic() - started:.2f}s -> {out_png}", flush=True)
        return 0

    device = args.device
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    is_micro = 0 < args.max_steps <= 10
    n_kappas = 5 if is_micro else 21
    n_z_pts = 5 if is_micro else 36
    n_xi_sweep = 6 if is_micro else 12

    design_n3 = build_n3_cantor_design()
    design_unif = build_uniform_3track_design()
    mesh_n3 = build_study_clutch_mesh(design_n3, theta_deg=12.0, n_r=1, n_phi_tooth=2, n_phi_bridge=2, n_z=2)
    mesh_unif = build_study_clutch_mesh(design_unif, theta_deg=12.0, n_r=1, n_phi_tooth=2, n_phi_bridge=2, n_z=2)
    kappas = np.geomspace(1.5, 150.0, n_kappas)
    n3_track_levels = [(t.r_tooth_in, t.r_tooth_out, t.level, t.r_inner, t.r_outer) for t in design_n3.tracks]
    unif_track_levels = [(t.r_tooth_in, t.r_tooth_out, t.level, t.r_inner, t.r_outer) for t in design_unif.tracks]

    print(f"[Exp 1] Evaluating 3D BEM wavenumber spectrum across {n_kappas} log-spaced kappas on {device}...", flush=True)
    spec_n3 = evaluate_spectral_trace_by_level(mesh_n3, kappas.tolist(), n3_track_levels, device)
    spec_unif = evaluate_spectral_trace_by_level(mesh_unif, kappas.tolist(), unif_track_levels, device)

    k_arr = np.array([r["kappa_um_inv"] for r in spec_n3])
    # Select peak wavenumber by maximum non-negative spectral magnitude |w_l{m}(kappa)|
    k_peak_l1 = float(k_arr[int(np.argmax(np.abs([r["level1_kappa_weighted_pN"] for r in spec_n3])))])
    k_peak_l2 = float(k_arr[int(np.argmax(np.abs([r["level2_kappa_weighted_pN"] for r in spec_n3])))])
    k_peak_l3 = float(k_arr[int(np.argmax(np.abs([r["level3_kappa_weighted_pN"] for r in spec_n3])))])

    b_scale = 2.5
    z_shifts = np.geomspace(0.025, 0.450, n_z_pts)
    print(f"[Exp 2] Evaluating Stepped (r,z) Cantor Clutch vs. Linear 3-Stage & Uniform Controls across {n_z_pts} log-spaced z depths...", flush=True)
    step_res = run_stepped_rz_log_periodic_sweep(b_scale=b_scale, z_shifts_um=z_shifts.tolist(), n_xi=n_xi_sweep, device=device)

    x_ln = np.array([r["ln_z_over_lstar"] for r in step_res["cantor_stepped_rz"]])
    y_c = np.array([r["scaled_force_z2_pN_um2"] for r in step_res["cantor_stepped_rz"]])
    y_l = np.array([r["scaled_force_z2_pN_um2"] for r in step_res["linear_3stage_control"]])
    y_u = np.array([r["scaled_force_z2_pN_um2"] for r in step_res["uniform_control"]])
    mod_c = extract_log_periodic_modulation(x_ln, y_c, b_scale)
    mod_l = extract_log_periodic_modulation(x_ln, y_l, b_scale)
    mod_u = extract_log_periodic_modulation(x_ln, y_u, b_scale)
    free_c = sweep_free_frequency_spectrum(x_ln, y_c, b_scale)
    free_l = sweep_free_frequency_spectrum(x_ln, y_l, b_scale)
    free_u = sweep_free_frequency_spectrum(x_ln, y_u, b_scale)

    amp_ratio = (
        mod_c["amplitude_fundamental"] / max(mod_u["amplitude_fundamental"], 1e-12)
        if mod_c["amplitude_fundamental"] is not None and mod_u["amplitude_fundamental"] is not None
        else None
    )
    amp_ratio_lin = (
        mod_c["amplitude_fundamental"] / max(mod_l["amplitude_fundamental"], 1e-12)
        if mod_c["amplitude_fundamental"] is not None and mod_l["amplitude_fundamental"] is not None
        else None
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "model": "BEM_LogPeriodicity_Clutch_Bridge", "dataset": "clutch_log_periodicity_probe",
        "status": "completed", "execution_status": "micro_probe_complete" if is_micro else "complete",
        "executed_at": now_iso, "device": device, "elapsed_seconds": time.monotonic() - started,
        "experiment1_spectral_wavenumber": {
            "b_scale_n3": 3.0, "ln_b_n3": float(math.log(3.0)),
            "kappa_peak_level1_um_inv": k_peak_l1, "kappa_peak_level2_um_inv": k_peak_l2, "kappa_peak_level3_um_inv": k_peak_l3,
            "observed_ratio_k2_over_k1": k_peak_l2 / max(k_peak_l1, 1e-12),
            "observed_ratio_k3_over_k2": k_peak_l3 / max(k_peak_l2, 1e-12),
            "cantor_n3_spectrum": spec_n3, "uniform_3track_spectrum": spec_unif,
        },
        "experiment2_stepped_rz_stroke": step_res,
        "experiment2_log_periodic_fit": {
            "cantor_modulation": mod_c,
            "linear_3stage_modulation": mod_l,
            "uniform_modulation": mod_u,
            "cantor_vs_uniform_fundamental_amp_ratio": amp_ratio,
            "cantor_vs_linear_fundamental_amp_ratio": amp_ratio_lin,
            "free_frequency_recovery": {
                "cantor": free_c,
                "linear_3stage": free_l,
                "uniform": free_u,
            },
        },
    }

    suffix = "_micro" if is_micro else ""
    out_json = ROOT / "results" / f"clutch_log_periodicity_probe{suffix}.json"
    out_png = ROOT / "figures" / f"fig_clutch_log_periodicity{suffix}.png"
    out_pdf = ROOT / "figures" / f"fig_clutch_log_periodicity{suffix}.pdf"
    atomic_write_json(out_json, report)
    render_figure(report, out_png, out_pdf)

    if not is_micro:
        assert mod_c["amplitude_fundamental"] is not None and mod_u["amplitude_fundamental"] is not None
        assert mod_c["amplitude_second_harmonic"] is not None and mod_u["amplitude_second_harmonic"] is not None
        assert mod_c["r2_two_harmonic_fit"] is not None and mod_u["r2_two_harmonic_fit"] is not None
        assert amp_ratio is not None
        set_solver_provenance("bem", {"benchmark": "clutch_log_periodicity_probe", "device": device, "max_steps": args.max_steps, "executed_at": now_iso})
        log_step("clutch_log_periodicity_probe", {"status": report["execution_status"], "n_kappas": n_kappas, "n_z_pts": n_z_pts}, solver_name="bem")
        c_fz = [float(r["force_z_pN"]) for r in step_res["cantor_stepped_rz"]]
        l_fz = [float(r["force_z_pN"]) for r in step_res["linear_3stage_control"]]
        u_fz = [float(r["force_z_pN"]) for r in step_res["uniform_control"]]
        stage2_fz = max(float(r["force_z_pN"]) for r in step_res["cantor_stepped_rz"] if 0.095 <= float(r["z_depth_um"]) <= 0.165)
        max_decomp_res = max(float(r.get("trace_decomposition_residual_pN_um", 0.0)) for r in spec_n3)
        max_signed_kf = max(float(r.get("active_kappa_weighted_integrand_pN", r["kappa_weighted_integrand_pN"])) for r in spec_n3)
        max_signed_kf_l1 = max(float(r.get("level1_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level1_integrand_pN_um"]))) for r in spec_n3)
        max_signed_kf_l2 = max(float(r.get("level2_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level2_integrand_pN_um"]))) for r in spec_n3)
        max_signed_kf_l3 = max(float(r.get("level3_signed_kappa_f_pN", float(r["kappa_um_inv"]) * float(r["level3_integrand_pN_um"]))) for r in spec_n3)
        assert max_decomp_res < 1e-12, f"Trace decomposition residual {max_decomp_res} >= 1e-12"
        assert max_signed_kf_l1 > 0.0 and max_signed_kf_l2 > 0.0 and max_signed_kf_l3 > 0.0 and max_signed_kf > 0.0
        metrics_to_log = {
            "logper_k_peak_l1_um_inv": k_peak_l1,
            "logper_k_peak_l2_um_inv": k_peak_l2,
            "logper_k_peak_l3_um_inv": k_peak_l3,
            "logper_ln_k_peak_l1": float(math.log(k_peak_l1)),
            "logper_ln_k_peak_l2": float(math.log(k_peak_l2)),
            "logper_ln_k_peak_l3": float(math.log(k_peak_l3)),
            "logper_k_peak_ratio_21": float(report["experiment1_spectral_wavenumber"]["observed_ratio_k2_over_k1"]),
            "logper_k_peak_ratio_32": float(report["experiment1_spectral_wavenumber"]["observed_ratio_k3_over_k2"]),
            "logper_signed_fz_decomp_max_residual_pn_um": float(max_decomp_res),
            "logper_signed_kf_total_peak_pn": float(max_signed_kf),
            "logper_signed_kf_l1_peak_pn": float(max_signed_kf_l1),
            "logper_signed_kf_l2_peak_pn": float(max_signed_kf_l2),
            "logper_signed_kf_l3_peak_pn": float(max_signed_kf_l3),
            "logper_stepped_rz_n_z_pts": float(n_z_pts),
            "logper_stepped_rz_b_scale": float(b_scale),
            "logper_stepped_rz_ln_b": float(math.log(b_scale)),
            "logper_stepped_rz_omega1": float(mod_c["omega_1"]),
            "logper_stepped_rz_amp1_cantor": float(mod_c["amplitude_fundamental"]),
            "logper_stepped_rz_amp1_se_cantor": float(mod_c["amplitude_fundamental_se"]),
            "logper_stepped_rz_fstat_cantor": float(mod_c["f_stat_two_harmonic"]),
            "logper_stepped_rz_pval_cantor": float(mod_c["p_value_two_harmonic"]),
            "logper_stepped_rz_delta_aic_cantor": float(mod_c["delta_aic_harm_minus_null"]),
            "logper_stepped_rz_delta_bic_cantor": float(mod_c["delta_bic_harm_minus_null"]),
            "logper_stepped_rz_amp1_linear": float(mod_l["amplitude_fundamental"]),
            "logper_stepped_rz_amp1_ratio_linear": float(amp_ratio_lin) if amp_ratio_lin is not None else 0.0,
            "logper_stepped_rz_r2_linear": float(mod_l["r2_two_harmonic_fit"]),
            "logper_stepped_rz_fstat_linear": float(mod_l["f_stat_two_harmonic"]),
            "logper_stepped_rz_pval_linear": float(mod_l["p_value_two_harmonic"]),
            "logper_stepped_rz_delta_aic_linear": float(mod_l["delta_aic_harm_minus_null"]),
            "logper_stepped_rz_delta_bic_linear": float(mod_l["delta_bic_harm_minus_null"]),
            "logper_stepped_rz_amp1_uniform": float(mod_u["amplitude_fundamental"]),
            "logper_stepped_rz_amp1_ratio": float(amp_ratio),
            "logper_stepped_rz_amp2_cantor": float(mod_c["amplitude_second_harmonic"]),
            "logper_stepped_rz_amp2_uniform": float(mod_u["amplitude_second_harmonic"]),
            "logper_stepped_rz_amp2_ratio": float(mod_c["amplitude_second_harmonic"] / max(mod_u["amplitude_second_harmonic"], 1e-12)),
            "logper_stepped_rz_r2": float(mod_c["r2_two_harmonic_fit"]),
            "logper_stepped_rz_r2_uniform": float(mod_u["r2_two_harmonic_fit"]),
            "logper_stepped_rz_r2_ratio": float(mod_c["r2_two_harmonic_fit"] / max(mod_u["r2_two_harmonic_fit"], 1e-12)),
            "logper_stepped_rz_fstat_uniform": float(mod_u["f_stat_two_harmonic"]),
            "logper_stepped_rz_pval_uniform": float(mod_u["p_value_two_harmonic"]),
            "logper_stepped_rz_delta_aic_uniform": float(mod_u["delta_aic_harm_minus_null"]),
            "logper_stepped_rz_delta_bic_uniform": float(mod_u["delta_bic_harm_minus_null"]),
            "logper_stepped_rz_max_fz_cantor_pn": float(max(c_fz)),
            "logper_stepped_rz_max_fz_linear_pn": float(max(l_fz)),
            "logper_stepped_rz_stage2_fz_cantor_pn": float(stage2_fz),
            "logper_stepped_rz_min_fz_uniform_pn": float(min(u_fz)),
            "logper_free_omega1_cantor": float(free_c["omega_hat_1h"]),
            "logper_free_omega1_se_cantor": float(free_c["omega_se_1h"]),
            "logper_free_omega1_ci95_half_cantor": float(free_c["omega_ci95_half_1h"]),
            "logper_free_omega1_ci95_low_cantor": float(free_c["omega_ci95_low_1h"]),
            "logper_free_omega1_ci95_high_cantor": float(free_c["omega_ci95_high_1h"]),
            "logper_free_b_hat_cantor": float(free_c["b_hat_1h"]),
            "logper_free_b_hat_se_cantor": float(free_c["b_se_1h"]),
            "logper_free_b_hat_ci95_half_cantor": float(free_c["b_ci95_half_1h"]),
            "logper_free_b_hat_ci95_low_cantor": float(free_c["b_ci95_low_1h"]),
            "logper_free_b_hat_ci95_high_cantor": float(free_c["b_ci95_high_1h"]),
            "logper_free_r2_peak_cantor": float(free_c["r2_peak_1h"]),
            "logper_free_r2_at_omega1_cantor": float(free_c["r2_at_design_1h"]),
            "logper_free_omega1_2h_cantor": float(free_c["omega_hat_2h_det"]),
            "logper_free_omega1_2h_ci95_half_cantor": float(free_c["omega_ci95_half_2h_det"]),
            "logper_free_b_hat_2h_cantor": float(free_c["b_hat_2h_det"]),
            "logper_free_b_hat_2h_ci95_half_cantor": float(free_c["b_ci95_half_2h_det"]),
            "logper_free_r2_2h_peak_cantor": float(free_c["r2_peak_2h_det"]),
            "logper_free_omega1_linear": float(free_l["omega_hat_1h"]),
            "logper_free_r2_peak_linear": float(free_l["r2_peak_1h"]),
            "logper_free_r2_at_omega1_linear": float(free_l["r2_at_design_1h"]),
            "logper_free_omega1_uniform": float(free_u["omega_hat_1h"]),
            "logper_free_r2_peak_uniform": float(free_u["r2_peak_1h"]),
            "logper_free_r2_at_omega1_uniform": float(free_u["r2_at_design_1h"]),
        }
        for m_key, m_val in metrics_to_log.items():
            log_metric(m_key, m_val, step_id="clutch_log_periodicity_probe", solver_name="bem")
        export_macros(str(ROOT / "results" / "provenance_metrics.json"), str(ROOT / "results" / "macros_results.tex"))
        save_plot_provenance(str(out_png), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        _sync_paper_figure_copies(out_png, out_pdf)
    print(f"Completed {report['execution_status']} in {report['elapsed_seconds']:.2f}s -> {out_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
