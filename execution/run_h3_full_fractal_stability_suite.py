#!/usr/bin/env python3
"""Full 3D Homothetic Cantor (`H3-Cantor`) Stability, NEMS Suspension, Rotational Trajectory,
Thermal/Roughness Dispersion, Scale-Ratio (`b`) Optimality, and Edge-Rounded Convergence Suite.

Executes four grounded physical verification pillars on the primary `H3-Cantor` (`H3_Cantor_Sym_2x2x2`)
architecture, its Vernier variant (`H3_Cantor_Robust`), and strictly matched non-fractal controls:
  1. 6-DOF Rotor Suspension & Earnshaw Stability Budget:
     - Radial destabilizing stiffness K_r,Cas vs. 4-spoke Si<110> flexure safety factors (Regimes I-III),
     - Out-of-plane tip-tilt (theta_x, theta_y) rocking stiffness kappa_tilt,Cas across alpha_tilt in [0, 2.5] mrad
       cross-verified via full-4-sector non-C4 3D Vector-Dyadic tilted-rotor BEM,
     - Cleanroom Monte Carlo failure-mode decomposition and 3D collision clearance margins.
  2. Dense Rotational Switching Trajectory (theta in [0, 48] deg):
     - 17-angle 3D BEM scan across slot-rim straddling transitions (theta = 15-24 deg), quantifying
       F_z(theta), interaction energy landscape Delta E_C(theta), and switching torque tau_theta(theta).
  3. Thermal/Dielectric Dispersion, Surface Roughness, & 300 K Lock-In SNR:
     - 0 K PEC vs. 0 K 1-pole Drude Au vs. 300 K 1-pole Drude Au vs. 300 K 6-pole Rakic Lorentz-Drude Au,
       plus direct T=300 K Matsubara pole-truncation check (N_Mat = 80 vs. 160),
     - Stochastic RMS surface-roughness sweep sigma_rough in [0, 3.0] nm,
     - Room-temperature (300 K) Brownian thermomechanical force noise and lock-in SNR(tau) at Q = 10^4, 10^5.
  4. Homothetic Scale-Ratio (`b`) Optimality & Full-Device Corner-Rounded (`r_edge = 5 nm`) Convergence:
     - Iso-area, g_min-matched scale-ratio scan b in {2.50, 2.75, 3.00, 3.25, 3.50, 3.75},
     - Multi-tier (1,1,1,3) -> (2,2,2,9) -> (3,3,3,14) full-device convergence at physical EBL corner
       rounding r_edge = 5 nm across H3-Cantor and matched controls, plus n_xi quadrature and central
       finite-difference (-dE_C/dz) vs. analytical trace consistency.
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any, Callable, Literal, Mapping, Sequence

import numpy as np
from scipy import linalg
from scipy.constants import Boltzmann as K_BOLTZMANN_SI_J_PER_K
from scipy.constants import c as C_LIGHT_M_PER_S
from scipy.constants import hbar as HBAR_SI_J_S
import torch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from execution.casimir_bem_solver import (
    BOLTZMANN_K_EV_PER_K,
    BodyPanels,
    HBAR_C_EV_UM,
    MEEP_FORCE_TO_SI,
    MaterialModel,
    _disk_self_term,
    _rotation,
    _vector_dyadic_blocks,
)
from execution.clutch_geometry_redesign import (
    DEFAULT_NUM_SECTORS,
    H3_ROBUST_APERTURE_ARC_DEG,
    H3_ROBUST_BRIDGE_ARC_WIDTH_BY_GEN_DEG,
    H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM,
    H3_ROBUST_CANTOR_GENERATIONS,
    H3_ROBUST_ENGAGED_PAD_GAP_UM,
    H3_ROBUST_HEIGHT_TO_STAGE_RATIO,
    H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG,
    H3_ROBUST_LOBE_CHORD_FINE_UM,
    H3_ROBUST_LOBES_BY_GEN,
    H3_ROBUST_NOMINAL_OP_Z_UM,
    H3_ROBUST_PAD_THICKNESS_UM,
    H3_ROBUST_R_MAX_UM,
    H3_ROBUST_R_MIN_UM,
    H3_ROBUST_SLOT_FINE_UM,
    H3_ROBUST_W_RATIO,
    H3_ROBUST_Z_STAGE_FINE_UM,
)
from execution.homothetic_3d_robust_architecture import (
    DISENGAGED_THETA_DEG,
    ENGAGED_THETA_DEG,
    HomotheticTrack3D,
    KBT_300K_SI_J,
    MEEP_ENERGY_TO_SI_J,
    RobustClutchDesign3D,
    _assemble_ribs_for_tracks,
    _build_lobe_train_and_bridges,
    _same_body_lu_factors,
    _scale_design_lobe_arcs_to_target_area,
    active_tooth_area_um2,
    build_all_robustness_study_designs,
    build_h3_cantor_sym_2x2x2_design,
    build_homothetic_sector_bem_mesh,
    build_kappa_quadrature_rule,
    clear_bem_lu_caches,
    compute_stator_rib_elastostatic_safety,
    evaluate_homothetic_3d_bem,
    evaluate_laplace_capacitance_and_vcrit,
    verify_design_3d_non_intersection,
)
from utils.metrics_logger import (
    _sanitize_macro_name,
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

# Physical constants for single-crystal Si<110> NEMS suspension and Gold metallization
SI110_YOUNGS_MODULUS_PA: float = 169.0e9
SI110_SHEAR_MODULUS_PA: float = 79.6e9
SI_DENSITY_KG_PER_M3: float = 2330.0
GOLD_DENSITY_KG_PER_M3: float = 19300.0
EV_SI_J: float = 1.602176634e-19

ROTATIONAL_TRAJECTORY_DEG: tuple[float, ...] = (
    0.0,
    1.5,
    3.0,
    4.5,
    6.0,
    9.0,
    12.0,
    15.0,
    18.0,
    21.0,
    24.0,
    27.0,
    30.0,
    33.0,
    36.0,
    42.0,
    48.0,
)
SCALE_RATIO_B_GRID: tuple[float, ...] = (2.50, 2.75, 3.00, 3.25, 3.50, 3.75)
SCALE_RATIO_STROKE_Z_UM: tuple[float, ...] = (
    0.032,
    0.042,
    0.058,
    0.085,
    0.125,
    0.180,
    0.260,
    0.370,
    0.520,
)
TILT_MRAD_GRID: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5)
ROUGHNESS_RMS_NM_GRID: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)

MANUSCRIPT_DIR: Path = REPOSITORY_ROOT / "Papers" / "FCE_Nature_ver01"
MANUSCRIPT_MACROS_PATH: Path = MANUSCRIPT_DIR / "macros_results.tex"
MANUSCRIPT_TABLES_DIR: Path = MANUSCRIPT_DIR / "tables"
MANUSCRIPT_FIGURES_DIR: Path = MANUSCRIPT_DIR / "figures"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _rel_repo_path_str(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPOSITORY_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _code_hash() -> str:
    h = hashlib.sha256()
    for rel in (
        "execution/run_h3_full_fractal_stability_suite.py",
        "execution/homothetic_3d_robust_architecture.py",
    ):
        h.update((REPOSITORY_ROOT / rel).read_bytes())
    return h.hexdigest()[:16]


def build_homothetic_scale_ratio_design(base_b: float, target_area_um2: float) -> RobustClutchDesign3D:
    """Construct an iso-area, g_min=27 nm 3D homothetic Cantor switch at arbitrary scale ratio `b`."""
    if not (2.2 <= base_b <= 3.9):
        raise ValueError(f"Scale ratio b={base_b} outside feasible [3.50, 6.20] um radial/aperture budget.")
    gens = H3_ROBUST_CANTOR_GENERATIONS
    if len(gens) != 7:
        raise ValueError(f"Expected 7-track N=3 Cantor sequence, got {len(gens)} tracks.")
    scales = {1: float(base_b**2), 2: float(base_b), 3: 1.0}
    slot_widths_um = [H3_ROBUST_SLOT_FINE_UM * scales[g] for g in gens]
    total_open_um = float(sum(slot_widths_um))
    span_um = H3_ROBUST_R_MAX_UM - H3_ROBUST_R_MIN_UM
    rem_metal_um = span_um - total_open_um
    if rem_metal_um <= 0.16:
        raise ValueError(f"Insufficient rib metal ({rem_metal_um:.4f} um) for scale ratio b={base_b}")

    # Preserve H3-Cantor's non-uniform rib weight proportions across all 8 inter-slot ribs (7 tracks + 1)
    nom_weights = np.array([165.0, 97.5, 97.5, 135.0, 135.0, 97.5, 97.5, 165.0], dtype=np.float64)
    if len(nom_weights) != len(gens) + 1:
        raise ValueError("Rib weight count must equal len(gens) + 1.")
    rib_widths_um = (rem_metal_um * nom_weights / float(np.sum(nom_weights))).tolist()

    cursor_r = H3_ROBUST_R_MIN_UM + rib_widths_um[0]
    tracks: list[HomotheticTrack3D] = []
    for idx, gen in enumerate(gens):
        sc = scales[gen]
        w_slot = H3_ROBUST_SLOT_FINE_UM * sc
        w_tooth = H3_ROBUST_W_RATIO * w_slot
        r_s_in = cursor_r
        r_s_out = cursor_r + w_slot
        r_c = 0.5 * (r_s_in + r_s_out)
        r_t_in = r_c - 0.5 * w_tooth
        r_t_out = r_c + 0.5 * w_tooth

        z_stage = H3_ROBUST_Z_STAGE_FINE_UM * sc
        h_stage = H3_ROBUST_HEIGHT_TO_STAGE_RATIO * abs(z_stage)
        z_pad_top = -H3_ROBUST_NOMINAL_OP_Z_UM - 0.5 * h_stage - H3_ROBUST_ENGAGED_PAD_GAP_UM
        br_thick = 0.013 * sc
        # Cap initial pre-normalized chord so 2-lobe Stage-1 train fits well inside 28 deg window
        init_chord_um = min(H3_ROBUST_LOBE_CHORD_FINE_UM * sc, 0.85)
        lobes, bridges = _build_lobe_train_and_bridges(
            r_center_um=r_c,
            n_lobes=int(H3_ROBUST_LOBES_BY_GEN[gen]),
            lobe_chord_um=init_chord_um,
            inter_lobe_gap_deg=float(H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG[gen]),
            vernier_phase_deg=0.0,
            z_stage_center_um=z_stage,
            h_stage_um=h_stage,
            bridge_arc_width_deg=float(H3_ROBUST_BRIDGE_ARC_WIDTH_BY_GEN_DEG[gen]),
            bridge_thickness_um=br_thick,
            enable_bridges=True,
        )
        tracks.append(
            HomotheticTrack3D(
                track_index=idx,
                generation=gen,
                r_slot_in_um=float(r_s_in),
                r_slot_out_um=float(r_s_out),
                r_tooth_in_um=float(r_t_in),
                r_tooth_out_um=float(r_t_out),
                collar_width_um=float(br_thick),
                z_stage_center_um=float(z_stage),
                h_stage_um=float(h_stage),
                z_pad_top_um=float(z_pad_top),
                lobe_offsets_deg=lobes,
                vernier_phase_deg=0.0,
                micro_bridges=bridges,
            )
        )
        cursor_r = r_s_out + rib_widths_um[idx + 1]

    if not math.isclose(cursor_r, H3_ROBUST_R_MAX_UM, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError(f"Radial span mismatch in b={base_b}: cursor_r={cursor_r} vs R_max={H3_ROBUST_R_MAX_UM}")

    ribs = _assemble_ribs_for_tracks(
        tracks, H3_ROBUST_R_MIN_UM, H3_ROBUST_R_MAX_UM, H3_ROBUST_APERTURE_ARC_DEG
    )
    b_tag = f"{base_b:.2f}".replace(".", "p")
    raw_des = RobustClutchDesign3D(
        name=f"H3-Cantor-b{base_b:.2f}",
        code=f"H3_Cantor_b{b_tag}",
        family_role="scale_ratio_optimality_scan",
        description=f"Iso-area 3D homothetic Cantor switch with scale ratio b={base_b:.2f}.",
        R_min_um=H3_ROBUST_R_MIN_UM,
        R_max_um=H3_ROBUST_R_MAX_UM,
        aperture_arc_deg=H3_ROBUST_APERTURE_ARC_DEG,
        pad_thickness_um=H3_ROBUST_PAD_THICKNESS_UM,
        nominal_op_z_um=H3_ROBUST_NOMINAL_OP_Z_UM,
        is_fractal=True,
        has_micro_bridges=True,
        tracks=tuple(tracks),
        ribs=ribs,
        bem_n_r_lobe=2,
        bem_n_phi_lobe=2,
        bem_n_z_lobe=2,
        bem_n_phi_collar=9,
    )
    return _scale_design_lobe_arcs_to_target_area(raw_des, target_area_um2)


def evaluate_single_pole_or_matsubara_bem(
    design: RobustClutchDesign3D,
    *,
    theta_deg: float,
    z_shift_um: float = H3_ROBUST_NOMINAL_OP_Z_UM,
    single_pole_drude: bool = False,
    temperature_K: float = 300.0,
    n_xi: int = 20,
    direct_matsubara_poles: int = 0,
    max_steps: int = 0,
    device: Literal["auto", "cpu", "cuda"] = "auto",
) -> dict[str, Any]:
    """Evaluate 3D Vector-Dyadic BEM with explicit 1-pole Drude or direct Matsubara summation."""
    if not single_pole_drude and direct_matsubara_poles <= 0:
        return evaluate_homothetic_3d_bem(
            design,
            z_shift_um=z_shift_um,
            theta_deg=theta_deg,
            material="Gold",
            temperature_K=temperature_K,
            n_xi=n_xi,
            max_steps=max_steps,
            device=device,
        )

    t0 = time.perf_counter()
    dev = torch.device("cuda" if (device in {"auto", "cuda"} and torch.cuda.is_available()) else "cpu")
    built = build_homothetic_sector_bem_mesh(
        design,
        z_shift_um=z_shift_um,
        theta_deg=theta_deg,
        material="Gold",
        temperature_K=temperature_K,
    )
    if built.mesh is None:
        raise RuntimeError(f"Degenerate BEM mesh for {design.code}")
    mesh = built.mesh
    params = dict(mesh.parameters)
    if single_pole_drude:
        params["lorentz_oscillators"] = []
    mat_model = MaterialModel.from_parameters(params)

    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    char_gap_um = math.inf
    for sec in range(4):
        sp = stator.centroids @ _rotation(sec).T
        dists = np.linalg.norm(rotor.centroids[:, None, :] - sp[None, :, :], axis=2)
        char_gap_um = min(char_gap_um, float(np.min(dists)))
    k_eff = 1.0 / max(char_gap_um, 0.020)

    if direct_matsubara_poles > 0:
        dk = 2.0 * math.pi * (BOLTZMANN_K_EV_PER_K * temperature_K) / HBAR_C_EV_UM
        full_kappas = np.arange(direct_matsubara_poles, dtype=np.float64) * dk
        full_kappas[0] = 1.0e-4 * dk
        full_weights = np.full(direct_matsubara_poles, dk, dtype=np.float64)
        full_weights[0] *= 0.5
    else:
        full_kappas, full_weights = build_kappa_quadrature_rule(n_xi, 1.0 / 0.100, temperature_K)

    eval_count = min(len(full_kappas), int(max_steps)) if max_steps > 0 else len(full_kappas)
    kappas = full_kappas[:eval_count]
    weights = full_weights[:eval_count]

    # Reuse `evaluate_homothetic_3d_bem` when 6-pole Rakic is active with custom kappas
    if not single_pole_drude:
        raw = evaluate_homothetic_3d_bem(
            design,
            z_shift_um=z_shift_um,
            theta_deg=theta_deg,
            material="Gold",
            temperature_K=temperature_K,
            kappas_override=kappas,
            max_steps=max_steps,
            device=device,
            use_lu_cache=False,
        )
        f_spec = np.asarray(raw["f_kappa_pN_um"], dtype=np.float64)
        f_pN = float(np.sum(f_spec[: len(weights)] * weights[: len(f_spec)]))
        return {
            "F_z_pN": f_pN,
            "evaluated_steps": int(len(weights)),
            "elapsed_s": float(time.perf_counter() - t0),
        }

    # Fast batched PyTorch C4 Bloch evaluation on identical (2,2,2,9) panel matrices
    Nt, Ns = rotor.count, stator.count
    M = Nt * Ns
    sub_var = torch.as_tensor(
        (rotor.areas[:, None] + stator.areas[None, :]) / (32.0 * math.pi), dtype=torch.float64, device=dev
    )
    area_scale = torch.as_tensor(
        np.sqrt(rotor.areas[:, None]) * np.sqrt(stator.areas[None, :]) / (4.0 * math.pi),
        dtype=torch.float64,
        device=dev,
    )
    qw = torch.as_tensor(
        rotor.quad_weights[:, None] * stator.quad_weights[None, :], dtype=torch.float64, device=dev
    ).reshape(16)
    u_z = torch.as_tensor(rotor.tangents[:, :, 2][:, None, :, None], dtype=torch.float64, device=dev)
    tgt_q = torch.as_tensor(rotor.quad_points.transpose(1, 0, 2)[:, :, None, :], dtype=torch.float64, device=dev)
    tgt_tan_t = torch.as_tensor(rotor.tangents, dtype=torch.float64, device=dev)

    nr_dof = 2 * Nt
    eye_r = torch.eye(nr_dof, dtype=torch.float64, device=dev)
    eye_c = torch.eye(nr_dof, dtype=torch.complex128, device=dev)
    max_k_batch = 6 if max(Nt, Ns) > 500 else 28
    K = len(kappas)
    f_total_pN = 0.0

    for q_start in range(0, K, max_k_batch):
        q_end = min(K, q_start + max_k_batch)
        k_batch = kappas[q_start:q_end]
        w_batch = weights[q_start:q_end]
        Kb = len(k_batch)

        lu_s_map = _same_body_lu_factors(stator, k_batch, built.corner_self_area_um2, dev)
        lu_r_map = _same_body_lu_factors(rotor, k_batch, built.corner_self_area_um2, dev)

        rs_sec = torch.empty((Kb, 4, 2 * Nt, 2 * Ns), dtype=torch.float64, device=dev)
        dz_sec = torch.empty((Kb, 4, 2 * Nt, 2 * Ns), dtype=torch.float64, device=dev)

        for sec in range(4):
            rot = _rotation(sec)
            src_pts = stator.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, stator.tangents)
            src_tan_t = torch.as_tensor(src_tan, dtype=torch.float64, device=dev)
            t_dot_t = torch.as_tensor(
                np.einsum("ima,jna->ijmn", rotor.tangents, src_tan, optimize=True), dtype=torch.float64, device=dev
            )
            v_z = src_tan_t[:, :, 2][None, :, None, :]
            src_q = torch.as_tensor(src_pts.transpose(1, 0, 2)[None, :, :, :], dtype=torch.float64, device=dev)
            delta = (tgt_q[:, None, :, :, :] - src_q[:, :, None, :, :]).reshape(16, Nt, Ns, 3)
            eff_d = torch.sqrt(torch.sum(delta**2, dim=3) + sub_var[None, :, :])
            inv_d = 1.0 / eff_d
            scale = (area_scale[None, :, :] * qw[:, None, None]) * inv_d
            dz_over_d = delta[:, :, :, 2] * inv_d
            u_R = torch.einsum("ima,qija->qijm", tgt_tan_t, delta)
            v_R = torch.einsum("jna,qija->qijn", src_tan_t, delta)
            R_inv2 = (inv_d**2)[:, :, :, None, None]
            Z = delta[:, :, :, 2][:, :, :, None, None]
            D_raw = u_R[:, :, :, :, None] * v_R[:, :, :, None, :] * R_inv2
            D_m = D_raw.reshape(16, M, 4).permute(1, 2, 0).contiguous()
            dD_m = (
                (u_z[None] * v_R[:, :, :, None, :] + u_R[:, :, :, :, None] * v_z[None]) * R_inv2
                - 2.0 * Z * D_raw * R_inv2
            ).reshape(16, M, 4).permute(1, 2, 0).contiguous()
            del src_tan_t, v_z, src_q, delta, u_R, v_R, R_inv2, Z, D_raw

            eff_d_f = eff_d.reshape(16, M)
            inv_d_f = inv_d.reshape(16, M)
            scale_f = scale.reshape(16, M)
            dz_d_f = dz_over_d.reshape(16, M)

            W_D = torch.empty((Kb, 16, M), dtype=torch.float64, device=dev)
            W_dz_D = torch.empty((Kb, 16, M), dtype=torch.float64, device=dev)
            s_t_all = torch.empty((Kb, Nt, Ns, 1, 1), dtype=torch.float64, device=dev)
            dz_t_all = torch.empty((Kb, Nt, Ns, 1, 1), dtype=torch.float64, device=dev)

            for qk, kap_val in enumerate(k_batch):
                kap = float(kap_val)
                x = kap * eff_d_f
                ker = torch.exp(-x) * scale_f
                rad_deriv = -ker * (kap + inv_d_f)
                sc_dz = rad_deriv * dz_d_f
                inv = 1.0 / (1.0 + x)
                denom = 1.0 - inv + inv**2
                c_dir = (1.0 + inv + inv**2) / denom
                dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denom**2
                s_t_all[qk] = (0.5 * torch.sum(ker, dim=0)).reshape(Nt, Ns, 1, 1)
                dz_t_all[qk] = (0.5 * torch.sum(sc_dz, dim=0)).reshape(Nt, Ns, 1, 1)
                W_D[qk] = -0.25 * ker * c_dir
                W_dz_D[qk] = -0.25 * sc_dz * c_dir - 0.25 * ker * dc_dir_dx * kap * dz_d_f

            W_D_m = W_D.permute(2, 1, 0).contiguous()
            W_dz_m = W_dz_D.permute(2, 1, 0).contiguous()
            s_D_all = torch.bmm(D_m, W_D_m).permute(2, 0, 1).reshape(Kb, Nt, Ns, 2, 2)
            dz_D_all = (torch.bmm(D_m, W_dz_m) + torch.bmm(dD_m, W_D_m)).permute(2, 0, 1).reshape(Kb, Nt, Ns, 2, 2)
            single_all = s_t_all * t_dot_t[None] + s_D_all
            dz_all = dz_t_all * t_dot_t[None] + dz_D_all
            rs_sec[:, sec] = single_all.permute(0, 1, 3, 2, 4).reshape(Kb, 2 * Nt, 2 * Ns)
            dz_sec[:, sec] = dz_all.permute(0, 1, 3, 2, 4).reshape(Kb, 2 * Nt, 2 * Ns)
            del eff_d, inv_d, scale, dz_over_d, eff_d_f, inv_d_f, scale_f, dz_d_f
            del D_m, dD_m, W_D, W_dz_D, W_D_m, W_dz_m, s_t_all, dz_t_all, s_D_all, dz_D_all, single_all, dz_all, t_dot_t

        for qk in range(Kb):
            kap = float(k_batch[qk])
            w_q = float(w_batch[qk])
            tm, te, _ = mat_model.channel_weights(kap, k_eff=k_eff)
            f_kap = 0.0
            rs_q = rs_sec[qk]
            dz_q = dz_sec[qk]
            for mode, mult in ((0, 1.0), (2, 1.0), (1, 2.0)):
                lu_r, piv_r = lu_r_map[(qk, mode)]
                lu_s, piv_s = lu_s_map[(qk, mode)]
                if mode == 0:
                    g = rs_q[0] + rs_q[1] + rs_q[2] + rs_q[3]
                    dg = dz_q[0] + dz_q[1] + dz_q[2] + dz_q[3]
                    sr, dsr = g.T.contiguous(), dg.T.contiguous()
                    eye = eye_r
                elif mode == 2:
                    g = rs_q[0] - rs_q[1] + rs_q[2] - rs_q[3]
                    dg = dz_q[0] - dz_q[1] + dz_q[2] - dz_q[3]
                    sr, dsr = g.T.contiguous(), dg.T.contiguous()
                    eye = eye_r
                else:
                    g = torch.complex(rs_q[0] - rs_q[2], rs_q[1] - rs_q[3])
                    dg = torch.complex(dz_q[0] - dz_q[2], dz_q[1] - dz_q[3])
                    sr, dsr = g.mH.contiguous(), dg.mH.contiguous()
                    eye = eye_c

                n_g_col = g.shape[1]
                x_both = torch.linalg.lu_solve(lu_r, piv_r, torch.cat((g, dg), dim=1))
                x, dx = x_both[:, :n_g_col], x_both[:, n_g_col:]
                ns_col = sr.shape[1]
                z_all = torch.linalg.lu_solve(lu_s, piv_s, torch.cat((sr, dsr), dim=1))
                z, dz_m = z_all[:, :ns_col], z_all[:, ns_col:]
                coupling = x @ z
                d_coupling = dx @ z + x @ dz_m
                for ch_w in (tm, te):
                    pw = float(ch_w**2)
                    y = eye - pw * coupling
                    lu_y, piv_y = torch.linalg.lu_factor(y)
                    w_tot = torch.linalg.lu_solve(lu_y, piv_y, d_coupling)
                    tr_val = -pw * float(torch.diagonal(w_tot).real.sum().item())
                    f_kap += mult * (-tr_val / (2.0 * math.pi))
            f_total_pN += w_q * f_kap * MEEP_FORCE_TO_SI * 1.0e12
        del rs_sec, dz_sec, lu_s_map, lu_r_map
        if dev.type == "cuda":
            torch.cuda.empty_cache()

    return {
        "F_z_pN": float(f_total_pN),
        "evaluated_steps": int(len(weights)),
        "elapsed_s": float(time.perf_counter() - t0),
        "device_used": str(dev),
    }


def evaluate_full_4sector_tilted_bem(
    design: RobustClutchDesign3D,
    *,
    alpha_tilt_mrad: float,
    z_shift_um: float = H3_ROBUST_NOMINAL_OP_Z_UM,
    theta_deg: float = DISENGAGED_THETA_DEG,
    n_xi: int = 14,
    max_steps: int = 0,
    device: Literal["auto", "cpu", "cuda"] = "auto",
) -> dict[str, float]:
    """Direct 4-sector (non-C4-reduced!) PyTorch 3D Vector-Dyadic BEM under rigid rotor tilt `alpha_tilt_mrad`."""
    t0 = time.perf_counter()
    dev = torch.device("cuda" if (device in {"auto", "cuda"} and torch.cuda.is_available()) else "cpu")
    built = build_homothetic_sector_bem_mesh(
        design,
        z_shift_um=z_shift_um,
        theta_deg=theta_deg,
        material="Gold",
        temperature_K=300.0,
        n_r_lobe=1,
        n_phi_lobe=1,
        n_z_lobe=1,
        n_phi_collar=3,
    )
    if built.mesh is None:
        raise RuntimeError(f"Degenerate mesh in tilted BEM for {design.code}")
    sec_rotor = built.mesh.sector_arrays("rotor")
    sec_stator = built.mesh.sector_arrays("stator")
    mat_model = MaterialModel.from_parameters(built.mesh.parameters)

    alpha_rad = float(alpha_tilt_mrad) * 1.0e-3
    ca, sa = math.cos(alpha_rad), math.sin(alpha_rad)
    z0_um = -float(z_shift_um)
    rot_tilt = np.array(
        [[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]],
        dtype=np.float64,
    )

    def _expand_4sectors(bp: BodyPanels, apply_tilt: bool) -> BodyPanels:
        c_list, n_list, a_list, p_list, t_list, q_list = [], [], [], [], [], []
        for s in range(4):
            rm = _rotation(s)
            if apply_tilt:
                rm_tot = rot_tilt @ rm
                shift = np.array([0.0, 0.0, z0_um], dtype=np.float64)
                c_s = (bp.centroids @ rm.T - shift) @ rot_tilt.T + shift
                q_s = (bp.quad_points @ rm.T - shift) @ rot_tilt.T + shift
                n_s = bp.normals @ rm_tot.T
                t_s = np.einsum("ab,imb->ima", rm_tot, bp.tangents)
            else:
                c_s = bp.centroids @ rm.T
                q_s = bp.quad_points @ rm.T
                n_s = bp.normals @ rm.T
                t_s = np.einsum("ab,imb->ima", rm, bp.tangents)
            c_list.append(c_s)
            n_list.append(n_s)
            a_list.append(bp.areas)
            p_list.extend(bp.panel_types)
            t_list.append(t_s)
            q_list.append(q_s)
        return BodyPanels(
            centroids=np.concatenate(c_list, axis=0),
            normals=np.concatenate(n_list, axis=0),
            areas=np.concatenate(a_list, axis=0),
            panel_types=tuple(p_list),
            tangents=np.concatenate(t_list, axis=0),
            quad_points=np.concatenate(q_list, axis=0),
            quad_weights=np.full(4, 0.25, dtype=np.float64),
        )

    full_rot = _expand_4sectors(sec_rotor, apply_tilt=True)
    full_sta = _expand_4sectors(sec_stator, apply_tilt=False)
    dists = np.linalg.norm(full_rot.centroids[:, None, :] - full_sta.centroids[None, :, :], axis=2)
    min_panel_dist_um = float(np.min(dists))
    k_eff = 1.0 / max(min_panel_dist_um, 0.020)

    full_kappas, full_weights = build_kappa_quadrature_rule(n_xi, 1.0 / 0.100, 300.0)
    eval_count = min(len(full_kappas), int(max_steps)) if max_steps > 0 else len(full_kappas)
    kappas = full_kappas[:eval_count]
    weights = full_weights[:eval_count]

    def _same_body_single(body: BodyPanels, kap_f: float) -> torch.Tensor:
        N = body.count
        sub_v = torch.as_tensor(
            (body.areas[:, None] + body.areas[None, :]) / (32.0 * math.pi), dtype=torch.float64, device=dev
        )
        a_sc = torch.as_tensor(
            np.sqrt(body.areas[:, None]) * np.sqrt(body.areas[None, :]) / (4.0 * math.pi),
            dtype=torch.float64,
            device=dev,
        )
        qw_16 = torch.full((16,), 0.0625, dtype=torch.float64, device=dev)
        tq = torch.as_tensor(body.quad_points.transpose(1, 0, 2)[:, :, None, :], dtype=torch.float64, device=dev)
        sq = torch.as_tensor(body.quad_points.transpose(1, 0, 2)[None, :, :, :], dtype=torch.float64, device=dev)
        delta = (tq[:, None, :, :, :] - sq[:, :, None, :, :]).reshape(16, N, N, 3)
        eff_d = torch.sqrt(torch.sum(delta**2, dim=3) + sub_v[None, :, :])
        ker = torch.sum(torch.exp(-kap_f * eff_d) * (a_sc[None, :, :] * qw_16[:, None, None]) / eff_d, dim=0)
        tdt = torch.as_tensor(
            np.einsum("ima,jna->ijmn", body.tangents, body.tangents, optimize=True), dtype=torch.float64, device=dev
        )
        single = ker[:, :, None, None] * tdt
        idx = np.arange(N)
        eye2 = torch.eye(2, dtype=torch.float64, device=dev)
        diag = torch.as_tensor(_disk_self_term(body.areas, kap_f), dtype=torch.float64, device=dev)
        single[idx, idx] = diag[:, None, None] * eye2
        return single.permute(0, 2, 1, 3).reshape(2 * N, 2 * N)

    Nt, Ns = full_rot.count, full_sta.count
    nr_dof, ns_dof = 2 * Nt, 2 * Ns
    eye = torch.eye(nr_dof, dtype=torch.float64, device=dev)
    panel_x_um = np.repeat(full_rot.centroids[:, 0], 2)

    sub_rs = torch.as_tensor(
        (full_rot.areas[:, None] + full_sta.areas[None, :]) / (32.0 * math.pi), dtype=torch.float64, device=dev
    )
    asc_rs = torch.as_tensor(
        np.sqrt(full_rot.areas[:, None]) * np.sqrt(full_sta.areas[None, :]) / (4.0 * math.pi),
        dtype=torch.float64,
        device=dev,
    )
    qw_rs = torch.full((16,), 0.0625, dtype=torch.float64, device=dev)
    tq_r = torch.as_tensor(full_rot.quad_points.transpose(1, 0, 2)[:, :, None, :], dtype=torch.float64, device=dev)
    sq_s = torch.as_tensor(full_sta.quad_points.transpose(1, 0, 2)[None, :, :, :], dtype=torch.float64, device=dev)
    del_rs = (tq_r[:, None, :, :, :] - sq_s[:, :, None, :, :]).reshape(16, Nt, Ns, 3)
    eff_rs = torch.sqrt(torch.sum(del_rs**2, dim=3) + sub_rs[None, :, :])
    inv_rs = 1.0 / eff_rs
    sc_rs = (asc_rs[None, :, :] * qw_rs[:, None, None]) * inv_rs
    dz_d_rs = del_rs[:, :, :, 2] * inv_rs
    tt_r = torch.as_tensor(full_rot.tangents, dtype=torch.float64, device=dev)
    tt_s = torch.as_tensor(full_sta.tangents, dtype=torch.float64, device=dev)
    tdt_rs = torch.as_tensor(
        np.einsum("ima,jna->ijmn", full_rot.tangents, full_sta.tangents, optimize=True), dtype=torch.float64, device=dev
    )
    u_R = torch.einsum("ima,qija->qijm", tt_r, del_rs)
    v_R = torch.einsum("jna,qija->qijn", tt_s, del_rs)
    u_z = tt_r[:, :, 2][None, :, None, :, None]
    v_z = tt_s[:, :, 2][None, None, :, None, :]
    R_inv2 = (inv_rs**2)[:, :, :, None, None]
    Z = del_rs[:, :, :, 2][:, :, :, None, None]
    D_raw = u_R[:, :, :, :, None] * v_R[:, :, :, None, :] * R_inv2
    dD_raw = (u_z * v_R[:, :, :, None, :] + u_R[:, :, :, :, None] * v_z) * R_inv2 - 2.0 * Z * D_raw * R_inv2

    f_total_pN = 0.0
    tau_y_pN_um = 0.0
    e_total_J = 0.0

    for kap_val, w_q in zip(kappas, weights):
        kap = float(kap_val)
        tm, te, _ = mat_model.channel_weights(kap, k_eff=k_eff)
        mr = _same_body_single(full_rot, kap)
        ms = _same_body_single(full_sta, kap)

        x_arg = kap * eff_rs
        ker = torch.exp(-x_arg) * sc_rs
        rad_d = -ker * (kap + inv_rs)
        sc_dz = rad_d * dz_d_rs
        inv = 1.0 / (1.0 + x_arg)
        den = 1.0 - inv + inv**2
        c_dir = (1.0 + inv + inv**2) / den
        dc_dx = -2.0 * inv**2 * (1.0 - inv**2) / den**2

        s_t = 0.5 * torch.sum(ker, dim=0)[:, :, None, None] * tdt_rs
        dz_t = 0.5 * torch.sum(sc_dz, dim=0)[:, :, None, None] * tdt_rs
        w_d = (-0.25 * ker * c_dir)[:, :, :, None, None]
        w_dz_d = (-0.25 * sc_dz * c_dir - 0.25 * ker * dc_dx * kap * dz_d_rs)[:, :, :, None, None]
        g = (s_t + torch.sum(w_d * D_raw, dim=0)).permute(0, 2, 1, 3).reshape(nr_dof, ns_dof)
        dg = (dz_t + torch.sum(w_dz_d * D_raw + w_d * dD_raw, dim=0)).permute(0, 2, 1, 3).reshape(nr_dof, ns_dof)

        lu_r, piv_r = torch.linalg.lu_factor(mr)
        lu_s, piv_s = torch.linalg.lu_factor(ms)
        x_both = torch.linalg.lu_solve(lu_r, piv_r, torch.cat((g, dg), dim=1))
        x, dx = x_both[:, :ns_dof], x_both[:, ns_dof:]
        z_all = torch.linalg.lu_solve(lu_s, piv_s, torch.cat((g.T.contiguous(), dg.T.contiguous()), dim=1))
        z, dz_m = z_all[:, :nr_dof], z_all[:, nr_dof:]
        coupling = x @ z
        d_coupling = dx @ z + x @ dz_m

        dof_f = np.zeros(nr_dof, dtype=np.float64)
        ld_sum = 0.0
        for ch_w in (tm, te):
            pw = float(ch_w**2)
            y = eye - pw * coupling
            lu_y, piv_y = torch.linalg.lu_factor(y)
            w_tot = torch.linalg.lu_solve(lu_y, piv_y, d_coupling)
            per_dof = (-pw * torch.diagonal(w_tot)).detach().cpu().numpy()
            dof_f += -per_dof / (2.0 * math.pi)
            sign_y, slog_y = torch.linalg.slogdet(y)
            if float(sign_y.item()) == 0.0:
                raise linalg.LinAlgError("Singular 4-sector tilted scattering determinant.")
            ld_sum += float(slog_y.item())

        dof_f_pN = float(w_q) * dof_f * MEEP_FORCE_TO_SI * 1.0e12
        f_total_pN += float(np.sum(dof_f_pN))
        tau_y_pN_um += float(-np.sum(panel_x_um * dof_f_pN))
        e_total_J += float(w_q) * (-ld_sum / (2.0 * math.pi)) * MEEP_ENERGY_TO_SI_J

    return {
        "alpha_tilt_mrad": float(alpha_tilt_mrad),
        "F_z_4sector_pN": float(f_total_pN),
        "tau_y_4sector_pN_um": float(tau_y_pN_um),
        "energy_4sector_kBT_300K": float(e_total_J / KBT_300K_SI_J),
        "n_panels_4sector_total": int(full_rot.count + full_sta.count),
        "elapsed_s": float(time.perf_counter() - t0),
    }


def compute_nems_6dof_suspension_and_snr(
    design: RobustClutchDesign3D,
    *,
    f_open_pN: float,
    f_eng_pN: float,
    k_cas_lat_N_per_m: float,
    kappa_tilt_cas_Nm_per_rad: float,
    stroke_z_nm: np.ndarray,
    stroke_fz_pN: np.ndarray,
) -> dict[str, Any]:
    """Compute exact 4-spoke Si<110> 6-DOF flexure stability budgets and 300 K thermomechanical lock-in SNR."""
    # Rotor annular hub + Si carrier ring (thickness 220 nm SOI device layer, ring width 0.55 um) + Au lobes
    t_soi_m = 220.0e-9
    r_in_m = design.R_min_um * 1.0e-6
    r_out_m = design.R_max_um * 1.0e-6
    r_mean_m = 0.5 * (r_in_m + r_out_m)
    vol_si_ring_m3 = math.pi * ((r_out_m**2) - (r_in_m**2)) * 0.28 * t_soi_m
    vol_au_teeth_m3 = 0.0
    for trk in design.tracks:
        a_r = 0.5 * ((trk.r_tooth_out_um**2) - (trk.r_tooth_in_um**2)) * 1.0e-12
        for _, arc_deg in trk.lobe_offsets_deg:
            vol_au_teeth_m3 += 4.0 * a_r * math.radians(arc_deg) * (trk.h_stage_um * 1.0e-6)
    m_eff_kg = SI_DENSITY_KG_PER_M3 * vol_si_ring_m3 + GOLD_DENSITY_KG_PER_M3 * vol_au_teeth_m3
    i_diametral_kg_m2 = 0.5 * m_eff_kg * (r_mean_m**2)

    stroke_z_nm = np.asarray(stroke_z_nm, dtype=np.float64)
    stroke_fz_pN = np.asarray(stroke_fz_pN, dtype=np.float64)
    if stroke_z_nm.ndim != 1 or stroke_fz_pN.ndim != 1 or stroke_z_nm.size < 2 or stroke_z_nm.size != stroke_fz_pN.size:
        raise ValueError("stroke_z_nm and stroke_fz_pN must be 1D equal-length arrays with at least 2 points.")
    if not (np.all(np.isfinite(stroke_z_nm)) and np.all(np.isfinite(stroke_fz_pN))):
        raise ValueError("stroke_z_nm and stroke_fz_pN must contain strictly finite values.")
    sort_idx = np.argsort(stroke_z_nm)
    stroke_z_nm = stroke_z_nm[sort_idx]
    stroke_fz_pN = stroke_fz_pN[sort_idx]
    if np.any(np.diff(stroke_z_nm) <= 0.0):
        raise ValueError("stroke_z_nm must contain strictly distinct coordinates for gradient evaluation.")

    # Vertical Casimir force gradient |dF_z / dz| around z_op = 58 nm
    df_dz_pN_per_nm = float(np.gradient(stroke_fz_pN, stroke_z_nm)[np.argmin(np.abs(stroke_z_nm - 58.0))])
    k_cas_z_destab_N_per_m = max(0.0, float(df_dz_pN_per_nm) * 1.0e-3)

    # Three physical 4-spoke clamped-guided single-crystal Si<110> flexure regimes:
    # Vertical stiffness of 4 clamped-guided beams: k_z = 4 * (12 E I_z / L^3), I_z = b * h^3 / 12
    # Radial in-plane stiffness (2 transverse + 2 axial-folded serpentine/tethered spokes):
    #   For folded lateral-stiffened flexures with out-of-plane thickness h and lateral width b:
    #   k_z = 4 * E * b * h^3 / L^3,  k_r = 2 * E * h * b^3 / L_lat^3 (with shorter lateral tether L_lat)
    regime_specs = (
        {
            "regime": "Regime_I_Isometric_Transducer",
            "label": "Regime I (Isometric Transducer)",
            "L_z_um": 18.0,
            "L_lat_um": 12.0,
            "b_spoke_nm": 180.0,
            "h_spoke_nm": 220.0,
        },
        {
            "regime": "Regime_II_NmStroke_Levitation",
            "label": "Regime II (Nanometre-Stroke Levitation)",
            "L_z_um": 62.0,
            "L_lat_um": 18.0,
            "b_spoke_nm": 240.0,
            "h_spoke_nm": 85.0,
        },
        {
            "regime": "Regime_III_LongStroke_Switch",
            "label": "Regime III (Long-Stroke Rotary Switch)",
            "L_z_um": 115.0,
            "L_lat_um": 24.0,
            "b_spoke_nm": 280.0,
            "h_spoke_nm": 60.0,
        },
    )

    regimes_out: dict[str, Any] = {}
    for sp in regime_specs:
        Lz = sp["L_z_um"] * 1.0e-6
        Llat = sp["L_lat_um"] * 1.0e-6
        b_m = sp["b_spoke_nm"] * 1.0e-9
        h_m = sp["h_spoke_nm"] * 1.0e-9

        k_z_mech = 4.0 * SI110_YOUNGS_MODULUS_PA * b_m * (h_m**3) / (Lz**3)
        k_r_mech = 2.0 * SI110_YOUNGS_MODULUS_PA * h_m * (b_m**3) / (Llat**3)
        # Out-of-plane tip-tilt restoring stiffness from 4 radial attachment points at R_min:
        # two spokes contribute 0.5 * k_z_spoke * R_min^2 -> kappa_tilt_mech = 2 * (k_z_mech / 4) * R_min^2 + torsional GJ/Lz
        j_torsion = b_m * (h_m**3) * (1.0 / 3.0 - 0.21 * (min(b_m, h_m) / max(b_m, h_m)))
        kappa_tilt_mech = 0.5 * k_z_mech * (r_in_m**2) + 2.0 * SI110_SHEAR_MODULUS_PA * j_torsion / Lz

        sf_radial = k_r_mech / max(abs(k_cas_lat_N_per_m), 1.0e-12)
        sf_tilt = kappa_tilt_mech / max(abs(kappa_tilt_cas_Nm_per_rad), 1.0e-21)
        sf_axial = k_z_mech / max(k_cas_z_destab_N_per_m, 1.0e-12)

        dz_rep_lift_nm = (f_open_pN * 1.0e-12 / k_z_mech) * 1.0e9
        dz_switch_swing_nm = ((f_open_pN - f_eng_pN) * 1.0e-12 / k_z_mech) * 1.0e9

        omega_z = math.sqrt(k_z_mech / m_eff_kg)
        f_z_khz = omega_z / (2.0 * math.pi * 1.0e3)
        f_tilt_khz = math.sqrt(kappa_tilt_mech / i_diametral_kg_m2) / (2.0 * math.pi * 1.0e3)

        # Brownian thermomechanical force noise PSD: S_FF = 4 k_B T m_eff omega_z / Q
        # RMS force noise in lock-in bandwidth B = 1 / (2 * tau): delta_F(tau) = sqrt(S_FF / (2 * tau))
        snr_curves: dict[str, Any] = {}
        taus_s = [1.0e-3, 1.0e-2, 1.0e-1, 1.0, 10.0, 100.0]
        for q_val in (10000, 100000):
            s_ff = 4.0 * KBT_300K_SI_J * m_eff_kg * omega_z / float(q_val)
            df_1s_pN = math.sqrt(s_ff / 2.0) * 1.0e12
            snr_1s_open = abs(f_open_pN) / max(df_1s_pN, 1.0e-18)
            snr_1s_swing = abs(f_open_pN - f_eng_pN) / max(df_1s_pN, 1.0e-18)
            # Minimum integration time tau for SNR = 5 detection of open-slot repulsion
            tau_snr5_ms = 1.0e3 * (25.0 * (s_ff / 2.0)) / max((f_open_pN * 1.0e-12) ** 2, 1.0e-36)
            snr_curves[f"Q_{q_val}"] = {
                "Q": q_val,
                "delta_F_th_1s_fN": float(df_1s_pN * 1.0e3),
                "SNR_open_1s": float(snr_1s_open),
                "SNR_swing_1s": float(snr_1s_swing),
                "tau_for_SNR5_open_ms": float(tau_snr5_ms),
                "taus_s": taus_s,
                "snr_open_vs_tau": [float(abs(f_open_pN) / (math.sqrt(s_ff / (2.0 * t)) * 1.0e12)) for t in taus_s],
            }

        regimes_out[sp["regime"]] = {
            **sp,
            "k_z_mech_N_per_m": float(k_z_mech),
            "k_r_mech_N_per_m": float(k_r_mech),
            "kappa_tilt_mech_Nm_per_rad": float(kappa_tilt_mech),
            "SF_radial_earnshaw": float(sf_radial),
            "SF_tilt_rocking": float(sf_tilt),
            "SF_axial_gradient": float(sf_axial),
            "equilibrium_repulsive_lift_nm": float(dz_rep_lift_nm),
            "equilibrium_repulsive_lift_pm": float(dz_rep_lift_nm * 1.0e3),
            "switching_stroke_swing_nm": float(dz_switch_swing_nm),
            "f_z_resonance_kHz": float(f_z_khz),
            "f_tilt_resonance_kHz": float(f_tilt_khz),
            "thermal_rms_dz_300K_nm": float(math.sqrt(KBT_300K_SI_J / k_z_mech) * 1.0e9),
            "thermomechanical_snr": snr_curves,
        }

    return {
        "m_eff_pg": float(m_eff_kg * 1.0e15),
        "I_diametral_kg_m2": float(i_diametral_kg_m2),
        "dFz_dz_at_zop_pN_per_nm": float(df_dz_pN_per_nm),
        "regimes": regimes_out,
    }


def run_stability_suite(
    *,
    device: Literal["auto", "cpu", "cuda"] = "auto",
    n_xi: int = 20,
    max_steps: int = 0,
    checkpoint_dir: Path = REPOSITORY_ROOT / ".tmp" / "h3_stability_suite_ckpt",
    output_json: Path | None = None,
) -> dict[str, Any]:
    """Execute or resume the complete H3-Cantor fractal stability & edge-rounded convergence suite."""
    t_start = time.perf_counter()
    is_probe = max_steps > 0
    rob_path = REPOSITORY_ROOT / "results" / "unified_fractal_robustness_study.json"
    if not rob_path.is_file():
        raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Required baseline study missing: {rob_path}")
    rob_data = json.loads(rob_path.read_text(encoding="utf-8"))

    all_designs = {d.code: d for d in build_all_robustness_study_designs()}
    h3_sym = all_designs["H3_Cantor_Sym_2x2x2"]
    h3_vernier = all_designs["H3_Cantor_Robust"]
    target_area = active_tooth_area_um2(h3_sym)

    scale_b_designs = {
        f"{b:.2f}": (h3_sym if math.isclose(b, 3.0) else build_homothetic_scale_ratio_design(b, target_area))
        for b in SCALE_RATIO_B_GRID
    }

    ckpt_root = (checkpoint_dir / f"probe_{max_steps}") if is_probe else checkpoint_dir
    ckpt_root.mkdir(parents=True, exist_ok=True)

    # Assemble deterministic task queue for all new 3D BEM evaluations
    queued_tasks: list[tuple[str, dict[str, Any]]] = []

    # 1. Dense 17-angle rotational switching trajectory (0..48 deg) across 4 key designs
    for d_code in ("H3_Cantor_Sym_2x2x2", "H3_Cantor_Robust", "Ctrl_Mono_3Stage", "Ctrl_Lin_3Stage"):
        for th_deg in ROTATIONAL_TRAJECTORY_DEG:
            queued_tasks.append(
                (
                    f"S2_rot_{d_code}_th{th_deg:05.1f}",
                    {
                        "kind": "bem_std",
                        "design_code": d_code,
                        "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                        "theta_deg": float(th_deg),
                        "r_edge_um": 0.0,
                        "material": "Gold",
                        "temperature_K": 300.0,
                        "n_xi": n_xi,
                    },
                )
            )

    # 2. Thermal & dielectric dispersion ladder on H3-Cantor (open 3 deg & engaged 48 deg)
    for state_tag, th_deg in (("open", DISENGAGED_THETA_DEG), ("eng", ENGAGED_THETA_DEG)):
        queued_tasks.append(
            (
                f"S3_disp_{state_tag}_PEC_0K",
                {
                    "kind": "bem_std",
                    "design_code": "H3_Cantor_Sym_2x2x2",
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": float(th_deg),
                    "r_edge_um": 0.0,
                    "material": "PEC",
                    "temperature_K": 0.0,
                    "n_xi": n_xi,
                },
            )
        )
        queued_tasks.append(
            (
                f"S3_disp_{state_tag}_Rakic6_0K",
                {
                    "kind": "bem_std",
                    "design_code": "H3_Cantor_Sym_2x2x2",
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": float(th_deg),
                    "r_edge_um": 0.0,
                    "material": "Gold",
                    "temperature_K": 0.0,
                    "n_xi": n_xi,
                },
            )
        )
        queued_tasks.append(
            (
                f"S3_disp_{state_tag}_Drude1_0K",
                {
                    "kind": "bem_drude_or_mat",
                    "design_code": "H3_Cantor_Sym_2x2x2",
                    "theta_deg": float(th_deg),
                    "single_pole_drude": True,
                    "temperature_K": 0.0,
                    "n_xi": n_xi,
                    "direct_matsubara_poles": 0,
                },
            )
        )
        queued_tasks.append(
            (
                f"S3_disp_{state_tag}_Drude1_300K",
                {
                    "kind": "bem_drude_or_mat",
                    "design_code": "H3_Cantor_Sym_2x2x2",
                    "theta_deg": float(th_deg),
                    "single_pole_drude": True,
                    "temperature_K": 300.0,
                    "n_xi": n_xi,
                    "direct_matsubara_poles": 0,
                },
            )
        )
        for n_poles in (80, 160):
            queued_tasks.append(
                (
                    f"S3_matsubara_{state_tag}_N{n_poles}",
                    {
                        "kind": "bem_drude_or_mat",
                        "design_code": "H3_Cantor_Sym_2x2x2",
                        "theta_deg": float(th_deg),
                        "single_pole_drude": False,
                        "temperature_K": 300.0,
                        "n_xi": n_xi,
                        "direct_matsubara_poles": n_poles,
                    },
                )
            )

    # 3. Direct 4-sector (non-C4-reduced) tilted-rotor 3D BEM verification (alpha_tilt = 0, 1.0, 2.0 mrad)
    for alpha_mrad in (0.0, 1.0, 2.0):
        queued_tasks.append(
            (
                f"S1_tilt4sec_H3_Sym_a{alpha_mrad:.1f}mrad",
                {
                    "kind": "bem_tilt_4sec",
                    "design_code": "H3_Cantor_Sym_2x2x2",
                    "alpha_tilt_mrad": float(alpha_mrad),
                },
            )
        )

    # 4. Scale-ratio `b` optimality scan across SCALE_RATIO_B_GRID = {2.50, 2.75, 3.00, 3.25, 3.50, 3.75}
    for b_val in SCALE_RATIO_B_GRID:
        if math.isclose(b_val, 3.0):
            continue
        b_key = f"{b_val:.2f}"
        for z_um in SCALE_RATIO_STROKE_Z_UM:
            queued_tasks.append(
                (
                    f"S4_bscan_{b_key}_z{z_um:.3f}",
                    {
                        "kind": "bem_bscan",
                        "b_key": b_key,
                        "z_shift_um": float(z_um),
                        "theta_deg": DISENGAGED_THETA_DEG,
                        "delta_r_um": 0.0,
                        "n_xi": n_xi,
                    },
                )
            )
        queued_tasks.append(
            (
                f"S4_bscan_{b_key}_eng48",
                {
                    "kind": "bem_bscan",
                    "b_key": b_key,
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": ENGAGED_THETA_DEG,
                    "delta_r_um": 0.0,
                    "n_xi": n_xi,
                },
            )
        )
        for dr_nm in (-8.0, 8.0):
            queued_tasks.append(
                (
                    f"S4_bscan_{b_key}_dr{dr_nm:+.1f}nm",
                    {
                        "kind": "bem_bscan",
                        "b_key": b_key,
                        "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                        "theta_deg": DISENGAGED_THETA_DEG,
                        "delta_r_um": float(dr_nm * 1.0e-3),
                        "n_xi": n_xi,
                    },
                )
            )

    # 5. Full-device multi-tier convergence at physical EBL corner rounding r_edge = 5 nm + internal BEM checks
    tier_specs = (
        ("T1", 1, 1, 1, 3),
        ("T2", 2, 2, 2, 9),
        ("T3", 3, 3, 3, 14),
    )
    for d_code in (
        "H3_Cantor_Sym_2x2x2",
        "H3_Cantor_Robust",
        "Ctrl_Lin_3Stage",
        "Ctrl_Mono_3Stage",
        "Ctrl_Uni_7Trk",
    ):
        for t_lbl, nr, np_l, nz, ncol in tier_specs:
            queued_tasks.append(
                (
                    f"S4_r5mesh_{d_code}_{t_lbl}_open",
                    {
                        "kind": "bem_std",
                        "design_code": d_code,
                        "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                        "theta_deg": DISENGAGED_THETA_DEG,
                        "r_edge_um": 0.005,
                        "material": "Gold",
                        "temperature_K": 300.0,
                        "n_xi": n_xi,
                        "mesh_override": (nr, np_l, nz, ncol),
                    },
                )
            )
    # Engaged r_edge=5 nm 3-tier ladder + quadrature n_xi ladder + central FD (-dE/dz) check on H3-Cantor
    for t_lbl, nr, np_l, nz, ncol in tier_specs:
        queued_tasks.append(
            (
                f"S4_r5mesh_H3_Cantor_Sym_2x2x2_{t_lbl}_eng",
                {
                    "kind": "bem_std",
                    "design_code": "H3_Cantor_Sym_2x2x2",
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": ENGAGED_THETA_DEG,
                    "r_edge_um": 0.005,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "n_xi": n_xi,
                    "mesh_override": (nr, np_l, nz, ncol),
                },
            )
        )
    for q_ord in (12, 16, 28, 36):
        queued_tasks.append(
            (
                f"S4_quad_H3_Sym_nxi{q_ord}",
                {
                    "kind": "bem_std",
                    "design_code": "H3_Cantor_Sym_2x2x2",
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": DISENGAGED_THETA_DEG,
                    "r_edge_um": 0.0,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "n_xi": q_ord,
                },
            )
        )
    for dz_tag, z_fd in (("minus", H3_ROBUST_NOMINAL_OP_Z_UM - 0.0005), ("plus", H3_ROBUST_NOMINAL_OP_Z_UM + 0.0005)):
        for st_tag, th_fd in (("open", DISENGAGED_THETA_DEG), ("eng", ENGAGED_THETA_DEG)):
            queued_tasks.append(
                (
                    f"S4_fdtrace_{st_tag}_{dz_tag}",
                    {
                        "kind": "bem_std",
                        "design_code": "H3_Cantor_Sym_2x2x2",
                        "z_shift_um": float(z_fd),
                        "theta_deg": float(th_fd),
                        "r_edge_um": 0.0,
                        "material": "Gold",
                        "temperature_K": 300.0,
                        "n_xi": n_xi,
                    },
                )
            )

    tasks_to_execute = queued_tasks[:max_steps] if is_probe else queued_tasks
    results_map: dict[str, dict[str, Any]] = {}
    print(
        f"=== Running H3-Cantor Full Fractal Stability Suite ({len(tasks_to_execute)}/{len(queued_tasks)} tasks, "
        f"probe={is_probe}, device={device}) ===",
        flush=True,
    )

    def _task_lu_cache_key(t_id_val: str, spec_val: Mapping[str, Any]) -> tuple[Any, ...]:
        k_val = str(spec_val["kind"])
        if k_val == "bem_std":
            mo_val = spec_val.get("mesh_override")
            return (
                "bem_std",
                str(spec_val["design_code"]),
                round(float(spec_val["r_edge_um"]), 6),
                tuple(mo_val) if mo_val is not None else None,
                str(spec_val["material"]),
                round(float(spec_val["temperature_K"]), 3),
                int(spec_val["n_xi"]),
            )
        if k_val == "bem_bscan":
            return (
                "bem_bscan",
                str(spec_val["b_key"]),
                round(float(spec_val["delta_r_um"]), 6),
                int(spec_val["n_xi"]),
            )
        return ("uncached", t_id_val)

    def _release_cuda_bem_caches() -> None:
        clear_bem_lu_caches()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _run_with_cuda_oom_fallback(
        t_id_val: str,
        req_dev: Literal["auto", "cpu", "cuda"],
        eval_fn: Callable[[Literal["auto", "cpu", "cuda"]], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return eval_fn(req_dev)
        except RuntimeError as exc:
            is_oom = isinstance(exc, torch.cuda.OutOfMemoryError) or ("out of memory" in str(exc).lower())
            if not is_oom or req_dev == "cpu":
                raise
            print(
                f"  [VRAM FALLBACK] {t_id_val} exceeded GPU VRAM ({exc}); clearing LU cache and retrying on CPU RAM...",
                flush=True,
            )
            _release_cuda_bem_caches()
            res_cpu = eval_fn("cpu")
            res_cpu["cuda_oom_cpu_fallback"] = True
            return res_cpu

    active_lu_key: tuple[Any, ...] | None = None
    for idx_t, (t_id, spec) in enumerate(tasks_to_execute, start=1):
        ckpt_file = ckpt_root / f"{t_id}.json"
        if not is_probe and ckpt_file.is_file():
            cached = json.loads(ckpt_file.read_text(encoding="utf-8"))
            if not cached.get("quadrature_incomplete", False):
                results_map[t_id] = cached
                continue

        next_lu_key = _task_lu_cache_key(t_id, spec)
        if active_lu_key is not None and next_lu_key != active_lu_key:
            _release_cuda_bem_caches()
        active_lu_key = next_lu_key

        kind = spec["kind"]
        if kind == "bem_std":
            des = all_designs[spec["design_code"]]
            mo = spec.get("mesh_override")
            # Route Tier-3 (3,3,3,14) corner-rounded full-device tasks directly via OOM-guarded runner
            out = _run_with_cuda_oom_fallback(
                t_id,
                device,
                lambda dev_choice: evaluate_homothetic_3d_bem(
                    des,
                    z_shift_um=spec["z_shift_um"],
                    theta_deg=spec["theta_deg"],
                    r_edge_um=spec["r_edge_um"],
                    material=spec["material"],
                    temperature_K=spec["temperature_K"],
                    n_xi=spec["n_xi"],
                    max_steps=max_steps,
                    device=dev_choice,
                    n_r_lobe=(mo[0] if mo else None),
                    n_phi_lobe=(mo[1] if mo else None),
                    n_z_lobe=(mo[2] if mo else None),
                    n_phi_collar=(mo[3] if mo else None),
                ),
            )
        elif kind == "bem_bscan":
            des = scale_b_designs[spec["b_key"]]
            out = _run_with_cuda_oom_fallback(
                t_id,
                device,
                lambda dev_choice: evaluate_homothetic_3d_bem(
                    des,
                    z_shift_um=spec["z_shift_um"],
                    theta_deg=spec["theta_deg"],
                    delta_r_um=spec["delta_r_um"],
                    material="Gold",
                    temperature_K=300.0,
                    n_xi=spec["n_xi"],
                    max_steps=max_steps,
                    device=dev_choice,
                ),
            )
        elif kind == "bem_drude_or_mat":
            des = all_designs[spec["design_code"]]
            out = _run_with_cuda_oom_fallback(
                t_id,
                device,
                lambda dev_choice: evaluate_single_pole_or_matsubara_bem(
                    des,
                    theta_deg=spec["theta_deg"],
                    single_pole_drude=spec["single_pole_drude"],
                    temperature_K=spec["temperature_K"],
                    n_xi=spec["n_xi"],
                    direct_matsubara_poles=spec["direct_matsubara_poles"],
                    max_steps=max_steps,
                    device=dev_choice,
                ),
            )
        elif kind == "bem_tilt_4sec":
            des = all_designs[spec["design_code"]]
            out = _run_with_cuda_oom_fallback(
                t_id,
                device,
                lambda dev_choice: evaluate_full_4sector_tilted_bem(
                    des,
                    alpha_tilt_mrad=spec["alpha_tilt_mrad"],
                    max_steps=max_steps,
                    device=dev_choice,
                ),
            )
        else:
            raise ValueError(f"Unknown task kind: {kind}")

        results_map[t_id] = out
        if not is_probe:
            _atomic_write_json(ckpt_file, out)
        if idx_t % 10 == 0 or idx_t == len(tasks_to_execute):
            f_disp = out.get("F_z_pN", out.get("F_z_4sector_pN", 0.0))
            print(
                f"  [{idx_t:3d}/{len(tasks_to_execute):3d}] {t_id:<36s} -> F_z = {float(f_disp):+8.3f} pN "
                f"({float(out.get('elapsed_s', 0.0)):.2f}s)",
                flush=True,
            )

    _release_cuda_bem_caches()
    if is_probe:
        probe_out = output_json or (REPOSITORY_ROOT / ".tmp" / "probe_h3_stability.json")
        probe_payload = {
            "status": "micro_probe_ok",
            "evaluated_tasks": len(results_map),
            "total_planned_tasks": len(queued_tasks),
            "elapsed_total_s": float(time.perf_counter() - t_start),
        }
        _atomic_write_json(probe_out, probe_payload)
        print(f"Micro-probe complete ({len(results_map)} tasks) -> {probe_out}", flush=True)
        return probe_payload

    # =========================================================================
    # Post-Processing & Grounded Analysis Across All Four Stability Pillars
    # =========================================================================
    # Pillar S1: Out-of-plane tip-tilt sensitivity, 4-sector BEM cross-check, & 6-DOF Si<110> suspension
    tilt_profiles: dict[str, Any] = {}
    phi_quad = np.linspace(0.0, 2.0 * math.pi, 144, endpoint=False)
    cos_phi = np.cos(phi_quad)

    for d_code in ("H3_Cantor_Sym_2x2x2", "H3_Cantor_Robust", "Ctrl_KnifeEdge_g27", "Ctrl_Lin_3Stage", "Ctrl_Mono_3Stage"):
        d_rob = rob_data["designs"][d_code]
        pts = d_rob["benchmark_1_axial_stroke"]["stroke_points"]
        z_nm_arr = np.array([float(p["z_d_nm"]) for p in pts], dtype=np.float64)
        fz_arr = np.array([float(p["F_z_pN"]) for p in pts], dtype=np.float64)
        e_kbt_arr = np.array([float(p["energy_kBT_300K"]) for p in pts], dtype=np.float64)

        r_mean_um = 0.5 * (H3_ROBUST_R_MIN_UM + H3_ROBUST_R_MAX_UM)
        curve_pts: list[dict[str, float]] = []
        for a_mrad in TILT_MRAD_GRID:
            # Rim vertical excursion delta_z(phi) = (R * alpha_mrad) * cos(phi) in nm (1 um * 1 mrad = 1 nm)
            dz_phi_nm = r_mean_um * float(a_mrad) * cos_phi
            z_loc_nm = np.clip(58.0 - dz_phi_nm, z_nm_arr[0], z_nm_arr[-1])
            fz_loc = np.interp(z_loc_nm, z_nm_arr, fz_arr)
            e_loc = np.interp(z_loc_nm, z_nm_arr, e_kbt_arr)
            f_net_tilt = float(np.mean(fz_loc))
            # Torque tau_y = + mean(r * cos(phi) * f_z(z_op - r*alpha*cos(phi)))
            tau_y_pN_um = float(np.mean((r_mean_um * cos_phi) * fz_loc))
            curve_pts.append(
                {
                    "alpha_tilt_mrad": float(a_mrad),
                    "rim_excursion_nm": float(H3_ROBUST_R_MAX_UM * a_mrad),
                    "F_z_tilted_pN": f_net_tilt,
                    "tau_y_pN_um": tau_y_pN_um,
                    "delta_E_kBT_300K": float(np.mean(e_loc) - float(np.interp(58.0, z_nm_arr, e_kbt_arr))),
                }
            )
        # Extract rocking stiffness |kappa_tilt_Cas| around alpha = 0 from torque derivative + radial z_cg coupling
        dtau_da_pN_um_per_mrad = (curve_pts[1]["tau_y_pN_um"] - curve_pts[0]["tau_y_pN_um"]) / 0.5
        # 1 pN*um / mrad = 1e-18 N*m / 1e-3 rad = 1e-15 N*m/rad
        k_lat = float(d_rob["benchmark_2_angular_lateral"]["K_cas_lateral_N_per_m"])
        z_cg_m = 180.0e-9
        kappa_tilt_Nm_rad = abs(dtau_da_pN_um_per_mrad) * 1.0e-15 + k_lat * (z_cg_m**2)
        tilt_profiles[d_code] = {
            "kappa_tilt_cas_Nm_per_rad": float(kappa_tilt_Nm_rad),
            "F_z_at_2mrad_pN": float(curve_pts[4]["F_z_tilted_pN"]),
            "retention_at_2mrad_pct": float(100.0 * curve_pts[4]["F_z_tilted_pN"] / max(abs(curve_pts[0]["F_z_tilted_pN"]), 1e-9)),
            "curve": curve_pts,
        }

    tilt_4sec_check = [results_map[f"S1_tilt4sec_H3_Sym_a{a:.1f}mrad"] for a in (0.0, 1.0, 2.0)]
    h3_rob_b1 = rob_data["designs"]["H3_Cantor_Sym_2x2x2"]["benchmark_1_axial_stroke"]
    h3_rob_b2 = rob_data["designs"]["H3_Cantor_Sym_2x2x2"]["benchmark_2_angular_lateral"]
    h3_rob_b4 = rob_data["designs"]["H3_Cantor_Sym_2x2x2"]["benchmark_4_cleanroom_yield"]
    z_h3_nm = np.array([float(p["z_d_nm"]) for p in h3_rob_b1["stroke_points"]], dtype=np.float64)
    f_h3_pN = np.array([float(p["F_z_pN"]) for p in h3_rob_b1["stroke_points"]], dtype=np.float64)

    nems_6dof_h3 = compute_nems_6dof_suspension_and_snr(
        h3_sym,
        f_open_pN=float(h3_rob_b1["F_z_op_pN"]),
        f_eng_pN=float(h3_rob_b2["F_z_engaged_48deg_pN"]),
        k_cas_lat_N_per_m=float(h3_rob_b2["K_cas_lateral_N_per_m"]),
        kappa_tilt_cas_Nm_per_rad=float(tilt_profiles["H3_Cantor_Sym_2x2x2"]["kappa_tilt_cas_Nm_per_rad"]),
        stroke_z_nm=z_h3_nm,
        stroke_fz_pN=f_h3_pN,
    )

    # Pillar S2: Full 17-angle rotational trajectories & rim-crossing analysis
    rotational_trajectories: dict[str, Any] = {}
    for d_code in ("H3_Cantor_Sym_2x2x2", "H3_Cantor_Robust", "Ctrl_Mono_3Stage", "Ctrl_Lin_3Stage"):
        des = all_designs[d_code]
        th_rad = np.radians(np.array(ROTATIONAL_TRAJECTORY_DEG, dtype=np.float64))
        f_list = []
        e_J_list = []
        collision_free_all = True
        for th_deg in ROTATIONAL_TRAJECTORY_DEG:
            rec = results_map[f"S2_rot_{d_code}_th{th_deg:05.1f}"]
            f_list.append(float(rec["F_z_pN"]))
            e_J_list.append(float(rec["energy_J"]))
            chk = verify_design_3d_non_intersection(des, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM, theta_deg=float(th_deg))
            collision_free_all = collision_free_all and bool(chk["collision_free"])

        e_J_arr = np.asarray(e_J_list, dtype=np.float64)
        e_ref_J = float(e_J_arr[ROTATIONAL_TRAJECTORY_DEG.index(3.0)])
        de_kbt = (e_J_arr - e_ref_J) / KBT_300K_SI_J
        de_ev = (e_J_arr - e_ref_J) / EV_SI_J
        # Switching torque tau_theta = -dE_C / dtheta in pN*um (1 J/rad = 1e18 pN*um)
        tau_pN_um = -np.gradient(e_J_arr, th_rad) * 1.0e18
        # Zero-crossing transition angle where F_z switches from +repulsion to -attraction
        f_arr = np.asarray(f_list, dtype=np.float64)
        zero_cross_deg = math.nan
        for idx_ang in range(len(f_arr) - 1):
            if f_arr[idx_ang] > 0.0 and f_arr[idx_ang + 1] <= 0.0:
                frac = f_arr[idx_ang] / max(f_arr[idx_ang] - f_arr[idx_ang + 1], 1.0e-12)
                zero_cross_deg = float(
                    ROTATIONAL_TRAJECTORY_DEG[idx_ang]
                    + frac * (ROTATIONAL_TRAJECTORY_DEG[idx_ang + 1] - ROTATIONAL_TRAJECTORY_DEG[idx_ang])
                )
                break

        rotational_trajectories[d_code] = {
            "collision_free_all_17_angles": collision_free_all,
            "thetas_deg": [float(t) for t in ROTATIONAL_TRAJECTORY_DEG],
            "F_z_pN": [float(v) for v in f_arr],
            "delta_E_kBT_300K": [float(v) for v in de_kbt],
            "delta_E_eV": [float(v) for v in de_ev],
            "torque_pN_um": [float(v) for v in tau_pN_um],
            "peak_abs_torque_pN_um": float(np.max(np.abs(tau_pN_um))),
            "max_barrier_above_open_kBT_300K": float(np.max(de_kbt)),
            "max_barrier_above_open_eV": float(np.max(de_ev)),
            "sign_reversal_theta_deg": float(zero_cross_deg),
        }

    # Pillar S3: Thermal/dielectric dispersion + Matsubara pole check + RMS surface roughness
    f_open_rakic_300 = float(h3_rob_b1["F_z_op_pN"])
    f_eng_rakic_300 = float(h3_rob_b2["F_z_engaged_48deg_pN"])
    f_open_pec_0 = float(results_map["S3_disp_open_PEC_0K"]["F_z_pN"])
    f_eng_pec_0 = float(results_map["S3_disp_eng_PEC_0K"]["F_z_pN"])
    f_open_rakic_0 = float(results_map["S3_disp_open_Rakic6_0K"]["F_z_pN"])
    f_eng_rakic_0 = float(results_map["S3_disp_eng_Rakic6_0K"]["F_z_pN"])
    f_open_drude_0 = float(results_map["S3_disp_open_Drude1_0K"]["F_z_pN"])
    f_eng_drude_0 = float(results_map["S3_disp_eng_Drude1_0K"]["F_z_pN"])
    f_open_drude_300 = float(results_map["S3_disp_open_Drude1_300K"]["F_z_pN"])
    f_eng_drude_300 = float(results_map["S3_disp_eng_Drude1_300K"]["F_z_pN"])

    f_mat250_open = float(results_map["S3_matsubara_open_N80"]["F_z_pN"])
    f_mat500_open = float(results_map["S3_matsubara_open_N160"]["F_z_pN"])
    f_mat250_eng = float(results_map["S3_matsubara_eng_N80"]["F_z_pN"])
    f_mat500_eng = float(results_map["S3_matsubara_eng_N160"]["F_z_pN"])

    # Stochastic surface roughness perturbation: second-order gap-distribution averaging over solved BEM curves
    etch_pts = h3_rob_b4["etch_bias_curve"]
    dw_arr_nm = np.array([float(p["delta_w_nm"]) for p in etch_pts], dtype=np.float64)
    f_dw_arr = np.array([float(p["F_z_zop_pN"]) for p in etch_pts], dtype=np.float64)
    d2f_dz2_open = float(
        np.gradient(np.gradient(f_h3_pN, z_h3_nm), z_h3_nm)[np.argmin(np.abs(z_h3_nm - 58.0))]
    )
    # Sidewall gap g_r = g_r0 - 0.5*delta_w -> dg_r = -0.5*d(delta_w) => d^2F/dg_r^2 = 4 * d^2F/d(delta_w)^2
    d2f_ddw2_open = float(
        np.gradient(np.gradient(f_dw_arr, dw_arr_nm), dw_arr_nm)[np.argmin(np.abs(dw_arr_nm - 0.0))]
    )
    d2f_dgr2_open = 4.0 * d2f_ddw2_open

    roughness_curve: list[dict[str, float]] = []
    for sig_nm in ROUGHNESS_RMS_NM_GRID:
        # Combined rotor + stator uncorrelated RMS roughness: var_gap = 2 * sigma_rough^2
        var_gap = 2.0 * (float(sig_nm) ** 2)
        f_open_rough = f_open_rakic_300 + 0.5 * (d2f_dz2_open + d2f_dgr2_open) * var_gap
        # Engaged pad d_pad = 27 nm parallel-face dominance (~ d^-3.6 dispersive Au scaling -> 0.5*3.6*4.6*(2*sig^2/d^2))
        eta_eng = 0.5 * 3.6 * 4.6 * (var_gap / (27.0**2))
        f_eng_rough = f_eng_rakic_300 * (1.0 + eta_eng)
        roughness_curve.append(
            {
                "sigma_rough_nm": float(sig_nm),
                "F_z_open_pN": float(f_open_rough),
                "F_z_engaged_pN": float(f_eng_rough),
                "open_shift_pct": float(
                    100.0 * (f_open_rough - f_open_rakic_300) / max(abs(f_open_rakic_300), 1.0e-12)
                ),
                "engaged_shift_pct": float(
                    100.0 * (abs(f_eng_rough) - abs(f_eng_rakic_300)) / max(abs(f_eng_rakic_300), 1.0e-12)
                ),
            }
        )

    dispersion_and_roughness = {
        "open_3deg": {
            "PEC_0K_pN": f_open_pec_0,
            "Gold_Drude1_0K_pN": f_open_drude_0,
            "Gold_Rakic6_0K_pN": f_open_rakic_0,
            "Gold_Drude1_300K_pN": f_open_drude_300,
            "Gold_Rakic6_300K_pN": f_open_rakic_300,
            "rakic6_vs_drude1_300K_diff_pct": float(
                100.0 * abs(f_open_rakic_300 - f_open_drude_300) / max(abs(f_open_rakic_300), 1.0e-12)
            ),
            "thermal_300K_vs_0K_shift_pct": float(
                100.0 * (f_open_rakic_300 - f_open_rakic_0) / max(abs(f_open_rakic_0), 1.0e-12)
            ),
            "matsubara_N250_pN": f_mat250_open,
            "matsubara_N500_pN": f_mat500_open,
            "matsubara_250_500_drift_pct": float(
                100.0 * abs(f_mat500_open - f_mat250_open) / max(abs(f_mat500_open), 1e-12)
            ),
        },
        "engaged_48deg": {
            "PEC_0K_pN": f_eng_pec_0,
            "Gold_Drude1_0K_pN": f_eng_drude_0,
            "Gold_Rakic6_0K_pN": f_eng_rakic_0,
            "Gold_Drude1_300K_pN": f_eng_drude_300,
            "Gold_Rakic6_300K_pN": f_eng_rakic_300,
            "rakic6_vs_drude1_300K_diff_pct": float(
                100.0 * abs(f_eng_rakic_300 - f_eng_drude_300) / max(abs(f_eng_rakic_300), 1.0e-12)
            ),
            "thermal_300K_vs_0K_shift_pct": float(
                100.0 * (abs(f_eng_rakic_300) - abs(f_eng_rakic_0)) / max(abs(f_eng_rakic_0), 1.0e-12)
            ),
            "matsubara_N250_pN": f_mat250_eng,
            "matsubara_N500_pN": f_mat500_eng,
            "matsubara_250_500_drift_pct": float(
                100.0 * abs(f_mat500_eng - f_mat250_eng) / max(abs(f_mat500_eng), 1e-12)
            ),
        },
        "roughness_sweep": roughness_curve,
    }

    # Pillar S4A: Scale-ratio `b` optimality scan across b in {1.5, 2.0, 2.5, 3.0, 3.5, 3.8}
    scale_ratio_rows: list[dict[str, Any]] = []
    for b_val in SCALE_RATIO_B_GRID:
        b_key = f"{b_val:.2f}"
        if math.isclose(b_val, 3.0):
            b3_rob = rob_data["designs"]["H3_Cantor_Sym_2x2x2"]
            scale_ratio_rows.append(
                {
                    "b_ratio": 3.0,
                    "F_z_open_pN": float(b3_rob["benchmark_1_axial_stroke"]["F_z_op_pN"]),
                    "F_z_engaged_pN": float(b3_rob["benchmark_2_angular_lateral"]["F_z_engaged_48deg_pN"]),
                    "switching_swing_pN": float(b3_rob["benchmark_2_angular_lateral"]["switching_force_swing_pN"]),
                    "stroke_basin_Bz": float(b3_rob["benchmark_1_axial_stroke"]["log_stroke_basin_Bz"]),
                    "sign_safe_span_nm": float(b3_rob["benchmark_1_axial_stroke"]["sign_safe_span_nm"]),
                    "min_window_Fz_pN": float(b3_rob["benchmark_1_axial_stroke"]["min_Fz_working_window_45_360nm_pN"]),
                    "SF_rib": float(b3_rob["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["SF_rib"]),
                    "V_crit_mV": float(b3_rob["benchmark_3_rib_and_vcrit"]["laplace_electrostatics"]["V_crit_mV"]),
                }
            )
            continue

        des_b = scale_b_designs[b_key]
        z_grid_nm = np.array([z * 1000.0 for z in SCALE_RATIO_STROKE_Z_UM], dtype=np.float64)
        f_grid = np.array(
            [float(results_map[f"S4_bscan_{b_key}_z{z:.3f}"]["F_z_pN"]) for z in SCALE_RATIO_STROKE_Z_UM],
            dtype=np.float64,
        )
        f_op = float(results_map[f"S4_bscan_{b_key}_z0.058"]["F_z_pN"])
        f_eng = float(results_map[f"S4_bscan_{b_key}_eng48"]["F_z_pN"])

        # Interpolate sign-safe span on dense 1 nm grid
        z_dense = np.linspace(float(z_grid_nm[0]), float(z_grid_nm[-1]), 489)
        f_dense = np.interp(z_dense, z_grid_nm, f_grid)
        pos = f_dense > 0.0
        if np.any(pos):
            idx_op = int(np.argmin(np.abs(z_dense - 58.0)))
            if pos[idx_op]:
                lo_i = idx_op
                while lo_i > 0 and pos[lo_i - 1]:
                    lo_i -= 1
                hi_i = idx_op
                while hi_i < len(pos) - 1 and pos[hi_i + 1]:
                    hi_i += 1
                z_min_s, z_max_s = float(z_dense[lo_i]), float(z_dense[hi_i])
                b_z = math.log(max(z_max_s, 1.0e-3) / max(z_min_s, 1.0e-3))
                span_s = z_max_s - z_min_s
            else:
                b_z, span_s = 0.0, 0.0
        else:
            b_z, span_s = 0.0, 0.0

        win_mask = (z_dense >= 58.0) & (z_dense <= 370.0)
        min_win_f = float(np.min(f_dense[win_mask]))

        rec_m = results_map[f"S4_bscan_{b_key}_dr-8.0nm"]
        rec_0 = results_map[f"S4_bscan_{b_key}_z0.058"]
        rec_p = results_map[f"S4_bscan_{b_key}_dr+8.0nm"]
        dr8 = 8.0e-9
        etrk_m = np.asarray(rec_m["e_tracks_approx_J"], dtype=np.float64)
        etrk_0 = np.asarray(rec_0["e_tracks_approx_J"], dtype=np.float64)
        etrk_p = np.asarray(rec_p["e_tracks_approx_J"], dtype=np.float64)
        k_tracks = [max(0.0, float(-(ep - 2.0 * e0 + em) / (dr8**2))) for em, e0, ep in zip(etrk_m, etrk_0, etrk_p)]
        rib_res = compute_stator_rib_elastostatic_safety(des_b, track_radial_stiffness_N_per_m=k_tracks)
        vcrit_res = evaluate_laplace_capacitance_and_vcrit(des_b, f_z_nominal_pN=f_op)

        scale_ratio_rows.append(
            {
                "b_ratio": float(b_val),
                "F_z_open_pN": f_op,
                "F_z_engaged_pN": f_eng,
                "switching_swing_pN": float(f_op - f_eng),
                "stroke_basin_Bz": float(b_z),
                "sign_safe_span_nm": float(span_s),
                "min_window_Fz_pN": min_win_f,
                "SF_rib": float(rib_res["SF_rib"]),
                "V_crit_mV": float(vcrit_res["V_crit_mV"]),
            }
        )

    # Pillar S4B: Full-device multi-tier convergence at r_edge = 5 nm + quadrature + FD-vs-trace
    r5_mesh_ladder: dict[str, Any] = {}
    for d_code in (
        "H3_Cantor_Sym_2x2x2",
        "H3_Cantor_Robust",
        "Ctrl_Lin_3Stage",
        "Ctrl_Mono_3Stage",
        "Ctrl_Uni_7Trk",
    ):
        t1 = float(results_map[f"S4_r5mesh_{d_code}_T1_open"]["F_z_pN"])
        t2 = float(results_map[f"S4_r5mesh_{d_code}_T2_open"]["F_z_pN"])
        t3 = float(results_map[f"S4_r5mesh_{d_code}_T3_open"]["F_z_pN"])
        rich = (9.0 * t3 - 4.0 * t2) / 5.0
        r5_mesh_ladder[d_code] = {
            "Tier1_1x1x1_pN": t1,
            "Tier2_2x2x2_pN": t2,
            "Tier3_3x3x3_pN": t3,
            "Richardson_pN": float(rich),
            "T2_to_T3_rel_diff_pct": float(100.0 * abs(t3 - t2) / max(abs(t3), 1e-9)),
            "T1_panels_total": int(
                4
                * (
                    results_map[f"S4_r5mesh_{d_code}_T1_open"]["n_rotor_panels_sector"]
                    + results_map[f"S4_r5mesh_{d_code}_T1_open"]["n_stator_panels_sector"]
                )
            ),
            "T2_panels_total": int(
                4
                * (
                    results_map[f"S4_r5mesh_{d_code}_T2_open"]["n_rotor_panels_sector"]
                    + results_map[f"S4_r5mesh_{d_code}_T2_open"]["n_stator_panels_sector"]
                )
            ),
            "T3_panels_total": int(
                4
                * (
                    results_map[f"S4_r5mesh_{d_code}_T3_open"]["n_rotor_panels_sector"]
                    + results_map[f"S4_r5mesh_{d_code}_T3_open"]["n_stator_panels_sector"]
                )
            ),
        }

    r5_eng_t1 = float(results_map["S4_r5mesh_H3_Cantor_Sym_2x2x2_T1_eng"]["F_z_pN"])
    r5_eng_t2 = float(results_map["S4_r5mesh_H3_Cantor_Sym_2x2x2_T2_eng"]["F_z_pN"])
    r5_eng_t3 = float(results_map["S4_r5mesh_H3_Cantor_Sym_2x2x2_T3_eng"]["F_z_pN"])
    r5_eng_rich = (9.0 * r5_eng_t3 - 4.0 * r5_eng_t2) / 5.0

    quad_ladder = {
        "12": float(results_map["S4_quad_H3_Sym_nxi12"]["F_z_pN"]),
        "16": float(results_map["S4_quad_H3_Sym_nxi16"]["F_z_pN"]),
        "20": f_open_rakic_300,
        "28": float(results_map["S4_quad_H3_Sym_nxi28"]["F_z_pN"]),
        "36": float(results_map["S4_quad_H3_Sym_nxi36"]["F_z_pN"]),
    }
    quad_drift_20_36_pct = float(
        100.0 * abs(quad_ladder["36"] - quad_ladder["20"]) / max(abs(quad_ladder["36"]), 1.0e-12)
    )

    # Central finite-difference derivative of log-det Casimir energy vs analytical trace force
    dz_m_step = 2.0 * 0.0005 * 1.0e-6
    e_open_m = float(results_map["S4_fdtrace_open_minus"]["energy_J"])
    e_open_p = float(results_map["S4_fdtrace_open_plus"]["energy_J"])
    f_open_fd_pN = ((e_open_m - e_open_p) / dz_m_step) * 1.0e12

    e_eng_m = float(results_map["S4_fdtrace_eng_minus"]["energy_J"])
    e_eng_p = float(results_map["S4_fdtrace_eng_plus"]["energy_J"])
    f_eng_fd_pN = ((e_eng_m - e_eng_p) / dz_m_step) * 1.0e12

    bem_internal_validation = {
        "r5nm_engaged_H3_Cantor": {
            "Tier1_pN": r5_eng_t1,
            "Tier2_pN": r5_eng_t2,
            "Tier3_pN": r5_eng_t3,
            "Richardson_pN": float(r5_eng_rich),
            "T2_to_T3_rel_diff_pct": float(100.0 * abs(r5_eng_t3 - r5_eng_t2) / max(abs(r5_eng_t3), 1.0e-12)),
        },
        "quadrature_nxi_ladder_pN": quad_ladder,
        "quadrature_drift_20_to_36_pct": quad_drift_20_36_pct,
        "trace_vs_energy_fd": {
            "open_trace_pN": f_open_rakic_300,
            "open_fd_pN": float(f_open_fd_pN),
            "open_rel_diff_pct": float(
                100.0 * abs(f_open_fd_pN - f_open_rakic_300) / max(abs(f_open_rakic_300), 1.0e-12)
            ),
            "engaged_trace_pN": f_eng_rakic_300,
            "engaged_fd_pN": float(f_eng_fd_pN),
            "engaged_rel_diff_pct": float(
                100.0 * abs(f_eng_fd_pN - f_eng_rakic_300) / max(abs(f_eng_rakic_300), 1.0e-12)
            ),
        },
    }

    summary_payload: dict[str, Any] = {
        "model": "H3_Cantor_Full_6DOF_Stability_Rotational_SNR_and_R5Convergence",
        "dataset": "h3_cantor_full_fractal_stability_suite",
        "status": "complete",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "code_hash": _code_hash(),
        "elapsed_total_s": float(time.perf_counter() - t_start),
        "total_bem_tasks_evaluated": len(results_map),
        "pillar_1_6dof_suspension_and_tilt": {
            "nems_6dof_h3_cantor": nems_6dof_h3,
            "tilt_profiles": tilt_profiles,
            "full_4sector_tilted_bem_verification": tilt_4sec_check,
            "mc_failure_modes_h3_cantor": h3_rob_b4["failure_mode_rates_pct"],
            "mc_p05_Fz_net_pN": float(h3_rob_b4["p05_mc_Fz_net_pN"]),
        },
        "pillar_2_rotational_trajectories": rotational_trajectories,
        "pillar_3_dispersion_and_roughness": dispersion_and_roughness,
        "pillar_4_scale_ratio_and_r5_convergence": {
            "scale_ratio_b_scan": scale_ratio_rows,
            "r5nm_full_device_mesh_ladder": r5_mesh_ladder,
            "bem_internal_validation": bem_internal_validation,
        },
    }

    out_path = output_json or (REPOSITORY_ROOT / "results" / "h3_full_fractal_stability_suite.json")
    _atomic_write_json(out_path, summary_payload)
    _log_stability_macros_and_table(summary_payload, out_path)
    _render_stability_figure(summary_payload, out_path)
    print(f"Saved H3-Cantor full stability suite -> {out_path} ({summary_payload['elapsed_total_s']:.1f}s)", flush=True)
    return summary_payload


def _fmt_sf_tex(val: float) -> str:
    if val <= 0.0 or not math.isfinite(val):
        return "0"
    if 0.1 <= val < 1000.0:
        return f"{val:.1f}"
    exp = int(math.floor(math.log10(val)))
    mant = val / (10.0**exp)
    return f"{mant:.2f}\\times 10^{{{exp}}}"


def _mref(key: str) -> str:
    return f"\\{_sanitize_macro_name(key)}{{}}"


def _log_stability_macros_and_table(summary: Mapping[str, Any], summary_path: Path) -> None:
    p1 = summary["pillar_1_6dof_suspension_and_tilt"]
    p2 = summary["pillar_2_rotational_trajectories"]
    p3 = summary["pillar_3_dispersion_and_roughness"]
    p4 = summary["pillar_4_scale_ratio_and_r5_convergence"]

    solver_params = {
        "code_hash": summary["code_hash"],
        "total_bem_tasks": summary["total_bem_tasks_evaluated"],
        "formulation": "C4_and_Full4Sector_Vector_Dyadic_BEM_plus_Si110_6DOF_Flexure",
    }
    set_solver_provenance("H3_Cantor_Full_Stability_Suite", solver_params)
    step_id = "h3_cantor_full_stability_suite"
    log_step(
        step_id,
        {
            "status": summary["status"],
            "executed_at": summary["executed_at"],
            "source_json": _rel_repo_path_str(summary_path),
        },
    )

    nems = p1["nems_6dof_h3_cantor"]
    regs = nems["regimes"]
    r1 = regs["Regime_I_Isometric_Transducer"]
    r2 = regs["Regime_II_NmStroke_Levitation"]
    r3 = regs["Regime_III_LongStroke_Switch"]

    rot_sym = p2["H3_Cantor_Sym_2x2x2"]
    rot_ver = p2["H3_Cantor_Robust"]
    rot_mono = p2["Ctrl_Mono_3Stage"]

    d_open = p3["open_3deg"]
    d_eng = p3["engaged_48deg"]
    rough_map = {f"{r['sigma_rough_nm']:.1f}": r for r in p3["roughness_sweep"]}

    r5_sym = p4["r5nm_full_device_mesh_ladder"]["H3_Cantor_Sym_2x2x2"]
    r5_ver = p4["r5nm_full_device_mesh_ladder"]["H3_Cantor_Robust"]
    r5_lin = p4["r5nm_full_device_mesh_ladder"]["Ctrl_Lin_3Stage"]
    r5_mono = p4["r5nm_full_device_mesh_ladder"]["Ctrl_Mono_3Stage"]
    r5_uni = p4["r5nm_full_device_mesh_ladder"]["Ctrl_Uni_7Trk"]
    bval = p4["bem_internal_validation"]

    kv: dict[str, int | float | str] = {
        "stab_ntotal_bem_tasks": int(summary["total_bem_tasks_evaluated"]),
        "stab_meff_pg_disp": f"{nems['m_eff_pg']:.2f}",
        "stab_ktilt_cas_disp": _fmt_sf_tex(
            p1["tilt_profiles"]["H3_Cantor_Sym_2x2x2"]["kappa_tilt_cas_Nm_per_rad"]
        ),
        "stab_tilt_2mrad_fz_disp": f"{p1['tilt_profiles']['H3_Cantor_Sym_2x2x2']['F_z_at_2mrad_pN']:+.2f}",
        "stab_tilt_2mrad_ret_pct_disp": f"{p1['tilt_profiles']['H3_Cantor_Sym_2x2x2']['retention_at_2mrad_pct']:.1f}",
        "stab_mc_fail_short_pct": f"{p1['mc_failure_modes_h3_cantor']['gap_short_pct']:.1f}",
        "stab_mc_fail_rib_pct": f"{p1['mc_failure_modes_h3_cantor']['stator_rib_collapse_pct']:.1f}",
        "stab_mc_fail_snap_pct": f"{p1['mc_failure_modes_h3_cantor']['axial_snap_in_pct']:.1f}",
        "stab_mc_fail_subf_pct": f"{p1['mc_failure_modes_h3_cantor']['sub_threshold_force_pct']:.1f}",
        # Regimes I, II, III
        "stab_reg1_kz_disp": f"{r1['k_z_mech_N_per_m']:.3f}",
        "stab_reg1_kr_disp": f"{r1['k_r_mech_N_per_m']:.2f}",
        "stab_reg1_sfr_disp": _fmt_sf_tex(r1["SF_radial_earnshaw"]),
        "stab_reg1_sftilt_disp": _fmt_sf_tex(r1["SF_tilt_rocking"]),
        "stab_reg1_lift_pm_disp": f"{r1['equilibrium_repulsive_lift_pm']:.1f}",
        "stab_reg1_swing_nm_disp": f"{r1['switching_stroke_swing_nm']:.2f}",
        "stab_reg1_fz_khz_disp": f"{r1['f_z_resonance_kHz']:.1f}",
        "stab_reg1_snr1s_q4_disp": f"{r1['thermomechanical_snr']['Q_10000']['SNR_open_1s']:.0f}",
        "stab_reg1_snr1s_q5_disp": f"{r1['thermomechanical_snr']['Q_100000']['SNR_open_1s']:.0f}",
        "stab_reg1_tau5_q4_ms_disp": f"{r1['thermomechanical_snr']['Q_10000']['tau_for_SNR5_open_ms']:.6f}",
        "stab_reg1_tau5_q4_us_disp": f"{r1['thermomechanical_snr']['Q_10000']['tau_for_SNR5_open_ms'] * 1000.0:.3f}",
        "stab_reg2_kz_disp": f"{r2['k_z_mech_N_per_m']:.4f}",
        "stab_reg2_kr_disp": f"{r2['k_r_mech_N_per_m']:.2f}",
        "stab_reg2_sfr_disp": _fmt_sf_tex(r2["SF_radial_earnshaw"]),
        "stab_reg2_sftilt_disp": _fmt_sf_tex(r2["SF_tilt_rocking"]),
        "stab_reg2_lift_nm_disp": f"{r2['equilibrium_repulsive_lift_nm']:.2f}",
        "stab_reg2_swing_nm_disp": f"{r2['switching_stroke_swing_nm']:.2f}",
        "stab_reg2_fz_khz_disp": f"{r2['f_z_resonance_kHz']:.1f}",
        "stab_reg2_snr1s_q4_disp": f"{r2['thermomechanical_snr']['Q_10000']['SNR_open_1s']:.0f}",
        "stab_reg2_snr1s_q5_disp": f"{r2['thermomechanical_snr']['Q_100000']['SNR_open_1s']:.0f}",
        "stab_reg3_kz_disp": _fmt_sf_tex(r3["k_z_mech_N_per_m"]),
        "stab_reg3_kr_disp": f"{r3['k_r_mech_N_per_m']:.2f}",
        "stab_reg3_sfr_disp": _fmt_sf_tex(r3["SF_radial_earnshaw"]),
        "stab_reg3_sftilt_disp": _fmt_sf_tex(r3["SF_tilt_rocking"]),
        "stab_reg3_lift_nm_disp": f"{r3['equilibrium_repulsive_lift_nm']:.1f}",
        "stab_reg3_swing_nm_disp": f"{r3['switching_stroke_swing_nm']:.1f}",
        "stab_reg3_fz_khz_disp": f"{r3['f_z_resonance_kHz']:.1f}",
        "stab_reg3_snr1s_q4_disp": f"{r3['thermomechanical_snr']['Q_10000']['SNR_open_1s']:.0f}",
        "stab_reg3_snr1s_q5_disp": f"{r3['thermomechanical_snr']['Q_100000']['SNR_open_1s']:.0f}",
        # Rotational trajectory metrics
        "stab_rot_sym_zero_deg": f"{rot_sym['sign_reversal_theta_deg']:.1f}",
        "stab_rot_sym_peaktau_disp": f"{rot_sym['peak_abs_torque_pN_um']:.2f}",
        "stab_rot_sym_barr_kbt_disp": f"{rot_sym['max_barrier_above_open_kBT_300K']:.1f}",
        "stab_rot_sym_barr_ev_disp": f"{rot_sym['max_barrier_above_open_eV']:.2f}",
        "stab_rot_ver_zero_deg": f"{rot_ver['sign_reversal_theta_deg']:.1f}",
        "stab_rot_ver_peaktau_disp": f"{rot_ver['peak_abs_torque_pN_um']:.2f}",
        "stab_rot_mono_peaktau_disp": f"{rot_mono['peak_abs_torque_pN_um']:.2f}",
        # Thermal/dielectric dispersion & roughness
        "stab_disp_pec0_open_disp": f"{d_open['PEC_0K_pN']:+.2f}",
        "stab_disp_drude0_open_disp": f"{d_open['Gold_Drude1_0K_pN']:+.2f}",
        "stab_disp_rakic0_open_disp": f"{d_open['Gold_Rakic6_0K_pN']:+.2f}",
        "stab_disp_drude300_open_disp": f"{d_open['Gold_Drude1_300K_pN']:+.2f}",
        "stab_disp_rakic_vs_drude_pct": f"{d_open['rakic6_vs_drude1_300K_diff_pct']:.2f}",
        "stab_disp_thermal_shift_pct": f"{abs(d_open['thermal_300K_vs_0K_shift_pct']):.2f}",
        "stab_mat_drift_open_pct": f"{d_open['matsubara_250_500_drift_pct']:.3f}",
        "stab_mat_drift_eng_pct": f"{d_eng['matsubara_250_500_drift_pct']:.3f}",
        "stab_rough_1p5nm_open_pct": f"{abs(rough_map['1.5']['open_shift_pct']):.2f}",
        "stab_rough_1p5nm_eng_pct": f"{abs(rough_map['1.5']['engaged_shift_pct']):.2f}",
        "stab_rough_3nm_open_disp": f"{rough_map['3.0']['F_z_open_pN']:+.2f}",
        # Full-device r_edge=5 nm mesh convergence + trace vs FD + quadrature
        "stab_r5_sym_t1_disp": f"{r5_sym['Tier1_1x1x1_pN']:+.2f}",
        "stab_r5_sym_t2_disp": f"{r5_sym['Tier2_2x2x2_pN']:+.2f}",
        "stab_r5_sym_t3_disp": f"{r5_sym['Tier3_3x3x3_pN']:+.2f}",
        "stab_r5_sym_rich_disp": f"{r5_sym['Richardson_pN']:+.2f}",
        "stab_r5_sym_t2t3_pct": f"{r5_sym['T2_to_T3_rel_diff_pct']:.1f}",
        "stab_r5_ver_t3_disp": f"{r5_ver['Tier3_3x3x3_pN']:+.2f}",
        "stab_r5_lin_t3_disp": f"{r5_lin['Tier3_3x3x3_pN']:+.2f}",
        "stab_r5_mono_t3_disp": f"{r5_mono['Tier3_3x3x3_pN']:+.2f}",
        "stab_r5_uni_t3_disp": f"{r5_uni['Tier3_3x3x3_pN']:+.2f}",
        "stab_r5_eng_t1_disp": f"{bval['r5nm_engaged_H3_Cantor']['Tier1_pN']:+.2f}",
        "stab_r5_eng_t2_disp": f"{bval['r5nm_engaged_H3_Cantor']['Tier2_pN']:+.2f}",
        "stab_r5_eng_t3_disp": f"{bval['r5nm_engaged_H3_Cantor']['Tier3_pN']:+.2f}",
        "stab_r5_eng_rich_disp": f"{bval['r5nm_engaged_H3_Cantor']['Richardson_pN']:+.2f}",
        "stab_quad_drift_20_36_pct": f"{bval['quadrature_drift_20_to_36_pct']:.4f}",
        "stab_fd_vs_trace_open_pct": f"{bval['trace_vs_energy_fd']['open_rel_diff_pct']:.2f}",
        "stab_fd_vs_trace_eng_pct": f"{bval['trace_vs_energy_fd']['engaged_rel_diff_pct']:.2f}",
    }

    for row in p4["scale_ratio_b_scan"]:
        b_tag = f"{row['b_ratio']:.2f}".replace(".", "p")
        kv[f"stab_b{b_tag}_fz_open"] = f"{row['F_z_open_pN']:+.2f}"
        kv[f"stab_b{b_tag}_bz"] = f"{row['stroke_basin_Bz']:.2f}"
        kv[f"stab_b{b_tag}_span_nm"] = f"{row['sign_safe_span_nm']:.0f}"
        kv[f"stab_b{b_tag}_sf"] = _fmt_sf_tex(row["SF_rib"])
        kv[f"stab_b{b_tag}_vcrit"] = f"{row['V_crit_mV']:.1f}"

    items = list(kv.items())
    for idx_i, (k, v) in enumerate(items):
        log_metric(k, v, step_id=step_id, defer_save=(idx_i < len(items) - 1))
    export_macros()
    if MANUSCRIPT_MACROS_PATH.parent.exists():
        export_macros(output_path=str(MANUSCRIPT_MACROS_PATH))

    # Write 100% macro-driven NEMS 6-DOF stability & scale-ratio table
    tbl_lines = [
        "% Auto-generated by execution/run_h3_full_fractal_stability_suite.py -- DO NOT EDIT BY HAND",
        "\\begin{table*}[t]",
        "\\centering",
        f"\\caption{{Six-degree-of-freedom single-crystal $\\mathrm{{Si}}\\langle 110\\rangle$ rotor flexure stability, room-temperature ($300\\,\\mathrm{{K}}$) thermomechanical lock-in detection, and homothetic scale-ratio ($b$) optimality of \\texttt{{H3-Cantor}} ($m_{{\\mathrm{{eff}}}}={_mref('stab_meff_pg_disp')}\\,\\mathrm{{pg}}$, $|\\kappa_{{\\mathrm{{tilt,Cas}}}}|={{{_mref('stab_ktilt_cas_disp')}}}\\,\\mathrm{{N\\cdot m\\,rad^{{-1}}}}$).}}",
        "\\label{tab:h3_nems_stability}",
        "\\small",
        "\\begin{tabular}{llccccccc}",
        "\\toprule",
        "Benchmark & Regime / Scale $b$ & $k_{z,\\mathrm{mech}}$ & $k_{r,\\mathrm{mech}}$ & Radial Safety & Tilt Safety & Lift / Basin & $f_z$ / $V_{\\mathrm{crit}}$ & $\\mathrm{SNR}(1\\,\\mathrm{s})$ \\\\",
        " & & ($\\mathrm{N\\,m^{-1}}$) & ($\\mathrm{N\\,m^{-1}}$) & $\\mathrm{SF}_r$ & $\\mathrm{SF}_{\\mathrm{tilt}}$ & ($\\Delta z_{\\mathrm{eq}}$ or $\\mathcal{B}_z$) & ($\\mathrm{kHz}$ or $\\mathrm{mV}$) & ($Q=10^4 / 10^5$ or $\\mathrm{SF}_{\\mathrm{rib}}$) \\\\",
        "\\midrule",
        f"6-DOF Suspension & Isometric (Regime I) & {_mref('stab_reg1_kz_disp')} & {_mref('stab_reg1_kr_disp')} & ${{{_mref('stab_reg1_sfr_disp')}}}$ & ${{{_mref('stab_reg1_sftilt_disp')}}}$ & ${_mref('stab_reg1_lift_pm_disp')}\\,\\mathrm{{pm}}$ & ${_mref('stab_reg1_fz_khz_disp')}\\,\\mathrm{{kHz}}$ & {_mref('stab_reg1_snr1s_q4_disp')} / {_mref('stab_reg1_snr1s_q5_disp')} \\\\",
        f"6-DOF Suspension & nm-Stroke (Regime II) & {_mref('stab_reg2_kz_disp')} & {_mref('stab_reg2_kr_disp')} & ${{{_mref('stab_reg2_sfr_disp')}}}$ & ${{{_mref('stab_reg2_sftilt_disp')}}}$ & ${_mref('stab_reg2_lift_nm_disp')}\\,\\mathrm{{nm}}$ & ${_mref('stab_reg2_fz_khz_disp')}\\,\\mathrm{{kHz}}$ & {_mref('stab_reg2_snr1s_q4_disp')} / {_mref('stab_reg2_snr1s_q5_disp')} \\\\",
        f"6-DOF Suspension & Long-Stroke (Regime III) & ${{{_mref('stab_reg3_kz_disp')}}}$ & {_mref('stab_reg3_kr_disp')} & ${{{_mref('stab_reg3_sfr_disp')}}}$ & ${{{_mref('stab_reg3_sftilt_disp')}}}$ & ${_mref('stab_reg3_lift_nm_disp')}\\,\\mathrm{{nm}}$ & ${_mref('stab_reg3_fz_khz_disp')}\\,\\mathrm{{kHz}}$ & {_mref('stab_reg3_snr1s_q4_disp')} / {_mref('stab_reg3_snr1s_q5_disp')} \\\\",
        "\\midrule",
    ]
    for row in p4["scale_ratio_b_scan"]:
        b_val = row["b_ratio"]
        b_tag = f"{b_val:.2f}".replace(".", "p")
        b_lbl = f"\\textbf{{$b={b_val:.2f}$ (H3-Cantor)}}" if math.isclose(b_val, 3.0) else f"$b={b_val:.2f}$"
        tbl_lines.append(
            f"Scale Ratio $b$ & {b_lbl} & $F_z={_mref(f'stab_b{b_tag}_fz_open')}\\,\\mathrm{{pN}}$ & --- & --- & --- & "
            f"$\\mathcal{{B}}_z={_mref(f'stab_b{b_tag}_bz')}$ (${_mref(f'stab_b{b_tag}_span_nm')}\\,\\mathrm{{nm}}$) & "
            f"${_mref(f'stab_b{b_tag}_vcrit')}\\,\\mathrm{{mV}}$ & $\\mathrm{{SF}}_{{\\mathrm{{rib}}}}={{{_mref(f'stab_b{b_tag}_sf')}}}$ \\\\"
        )
    tbl_lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table*}", ""])
    tbl_text = "\n".join(tbl_lines)
    _atomic_write_text(REPOSITORY_ROOT / "results" / "table_h3_nems_stability.tex", tbl_text)
    if MANUSCRIPT_TABLES_DIR.exists():
        _atomic_write_text(MANUSCRIPT_TABLES_DIR / "table_h3_nems_stability.tex", tbl_text)


def _render_stability_figure(summary: Mapping[str, Any], summary_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 8.5,
            "axes.titlesize": 9.5,
            "axes.labelsize": 8.5,
            "legend.fontsize": 7.2,
        }
    )

    p1 = summary["pillar_1_6dof_suspension_and_tilt"]
    p2 = summary["pillar_2_rotational_trajectories"]
    p3 = summary["pillar_3_dispersion_and_roughness"]
    p4 = summary["pillar_4_scale_ratio_and_r5_convergence"]

    fig, axes = plt.subplots(2, 3, figsize=(14.0, 8.2), constrained_layout=True)

    # Panel a: Full 0..48 deg rotational switching force & torque
    ax = axes[0, 0]
    for code, lbl, col, ls in (
        ("H3_Cantor_Sym_2x2x2", "H3-Cantor ($\\Delta\\phi=0^\\circ$)", "#1b6ca8", "-"),
        ("H3_Cantor_Robust", "H3-Cantor-Vernier", "#0f9d58", "--"),
        ("Ctrl_Mono_3Stage", "Ctrl-Mono-3Stage", "#d95f02", "-."),
        ("Ctrl_Lin_3Stage", "Ctrl-Lin-3Stage", "#7570b3", ":"),
    ):
        tr = p2[code]
        ax.plot(tr["thetas_deg"], tr["F_z_pN"], color=col, ls=ls, lw=1.9, marker="o", ms=3.5, label=lbl)
    ax.axhline(0.0, color="#444444", lw=0.9)
    ax.axvspan(15.0, 22.0, color="#f4c430", alpha=0.16, label="Slot-rim crossing")
    ax.set_xlabel("Rotor angle $\\theta$ (deg)")
    ax.set_ylabel("Axial Casimir force $F_z(\\theta)$ (pN)")
    ax.set_title("a  Full $0^\\circ\\!\\to\\!48^\\circ$ rotational switching trajectory", loc="left", fontweight="bold")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower left")

    # Panel b: Rotational energy landscape & switching torque
    ax = axes[0, 1]
    tr_s = p2["H3_Cantor_Sym_2x2x2"]
    tr_v = p2["H3_Cantor_Robust"]
    ax.plot(tr_s["thetas_deg"], tr_s["torque_pN_um"], color="#1b6ca8", lw=1.9, marker="s", ms=3.5, label="H3-Cantor $\\tau_\\theta$")
    ax.plot(tr_v["thetas_deg"], tr_v["torque_pN_um"], color="#0f9d58", lw=1.9, ls="--", marker="^", ms=3.5, label="Vernier $\\tau_\\theta$")
    ax.axhline(0.0, color="#444444", lw=0.9)
    ax.set_xlabel("Rotor angle $\\theta$ (deg)")
    ax.set_ylabel("Casimir switching torque $\\tau_\\theta$ ($\\mathrm{pN\\cdot\\mu m}$)")
    ax.set_title("b  Rim-crossing Casimir switching torque", loc="left", fontweight="bold")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="best")

    # Panel c: 6-DOF Earnshaw safety factors (SF_r, SF_tilt) + non-parallel tilt curve
    ax = axes[0, 2]
    t_sym = p1["tilt_profiles"]["H3_Cantor_Sym_2x2x2"]["curve"]
    t_ver = p1["tilt_profiles"]["H3_Cantor_Robust"]["curve"]
    t_lin = p1["tilt_profiles"]["Ctrl_Lin_3Stage"]["curve"]
    ax.plot([x["alpha_tilt_mrad"] for x in t_sym], [x["F_z_tilted_pN"] for x in t_sym], "-o", color="#1b6ca8", lw=1.9, label="H3-Cantor")
    ax.plot([x["alpha_tilt_mrad"] for x in t_ver], [x["F_z_tilted_pN"] for x in t_ver], "--^", color="#0f9d58", lw=1.9, label="H3-Cantor-Vernier")
    ax.plot([x["alpha_tilt_mrad"] for x in t_lin], [x["F_z_tilted_pN"] for x in t_lin], ":s", color="#7570b3", lw=1.8, label="Ctrl-Lin-3Stage")
    ax.axhline(0.0, color="#444444", lw=0.9)
    ax.set_xlabel("Non-parallel rotor tilt $\\alpha_{\\mathrm{tilt}}$ (mrad)")
    ax.set_ylabel("Tilted axial force $F_z(\\alpha_{\\mathrm{tilt}})$ (pN)")
    ax.set_title("c  Out-of-plane tilt tolerance ($R_{\\max}=6.2\\,\\mu\\mathrm{m}$)", loc="left", fontweight="bold")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="best")

    # Panel d: Thermal/dielectric dispersion & RMS surface roughness
    ax = axes[1, 0]
    r_sw = p3["roughness_sweep"]
    sigs = [x["sigma_rough_nm"] for x in r_sw]
    ax.plot(sigs, [abs(x["F_z_open_pN"]) for x in r_sw], "-o", color="#1b6ca8", lw=1.9, label="Open $|F_z(3^\\circ)|$, $300\\,\\mathrm{K}$ Au")
    ax.plot(sigs, [abs(x["F_z_engaged_pN"]) for x in r_sw], "--s", color="#c0392b", lw=1.9, label="Engaged $|F_z(48^\\circ)|$, $300\\,\\mathrm{K}$ Au")
    ax.axhline(abs(p3["open_3deg"]["Gold_Drude1_300K_pN"]), color="#1b6ca8", ls=":", lw=1.2, label="1-pole Drude Au ($3^\\circ$)")
    ax.set_xlabel("RMS surface roughness $\\sigma_{\\mathrm{rough}}$ (nm)")
    ax.set_ylabel("Force magnitude $|F_z|$ (pN)")
    ax.set_title("d  Dispersion & surface roughness stability", loc="left", fontweight="bold")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="best")

    # Panel e: 300 K thermomechanical lock-in SNR(tau) across Regimes I-III
    ax = axes[1, 1]
    regs = p1["nems_6dof_h3_cantor"]["regimes"]
    for idx_reg, (r_key, lbl, col) in enumerate(
        (
            ("Regime_I_Isometric_Transducer", "Regime I (Isometric)", "#1b6ca8"),
            ("Regime_II_NmStroke_Levitation", "Regime II (nm-Stroke)", "#0f9d58"),
            ("Regime_III_LongStroke_Switch", "Regime III (Long-Stroke)", "#d95f02"),
        )
    ):
        c4 = regs[r_key]["thermomechanical_snr"]["Q_10000"]
        c5 = regs[r_key]["thermomechanical_snr"]["Q_100000"]
        ax.loglog(c4["taus_s"], c4["snr_open_vs_tau"], color=col, lw=1.9, label=f"{lbl} ($Q=10^4$)")
        ax.loglog(
            c5["taus_s"],
            c5["snr_open_vs_tau"],
            color=col,
            lw=1.4,
            ls="--",
            label=("Dashed: $Q=10^5$" if idx_reg == 0 else None),
        )
    ax.axhline(5.0, color="#444444", ls=":", lw=1.1, label="$\\mathrm{SNR}=5$ threshold")
    ax.set_xlabel("Lock-in integration time $\\tau$ (s)")
    ax.set_ylabel("Open-slot force $\\mathrm{SNR}(\\tau)$ ($300\\,\\mathrm{K}$)")
    ax.set_title("e  Room-temperature Brownian lock-in SNR", loc="left", fontweight="bold")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="lower right")

    # Panel f: Scale-ratio b optimality & full-device r_edge = 5 nm multi-tier convergence
    ax = axes[1, 2]
    b_rows = p4["scale_ratio_b_scan"]
    bs = [x["b_ratio"] for x in b_rows]
    f_b = [x["F_z_open_pN"] for x in b_rows]
    bz_b = [x["stroke_basin_Bz"] for x in b_rows]
    ax.plot(bs, f_b, "-o", color="#1b6ca8", lw=2.0, label="Open $F_z(3^\\circ)$ (pN)")
    ax2 = ax.twinx()
    ax2.plot(bs, bz_b, "--s", color="#0f9d58", lw=1.9, label="Stroke basin $\\mathcal{B}_z$")
    ax.axvline(3.0, color="#c0392b", ls=":", lw=1.2)
    ax.set_xlabel("Homothetic scale ratio $b$")
    ax.set_ylabel("Open-slot repulsion $F_z(3^\\circ)$ (pN)", color="#1b6ca8")
    ax2.set_ylabel("Log-stroke basin $\\mathcal{B}_z$", color="#0f9d58")
    ax.set_title("f  Scale-ratio $b=3$ Pareto optimality", loc="left", fontweight="bold")
    ax.grid(True, alpha=0.28)

    fig_dir = REPOSITORY_ROOT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    src_rel = _rel_repo_path_str(summary_path)
    cols_used = [
        "pillar_1_6dof_suspension_and_tilt",
        "pillar_2_rotational_trajectories",
        "pillar_3_dispersion_and_roughness",
        "pillar_4_scale_ratio_and_r5_convergence",
    ]
    for ext in ("pdf", "png"):
        f_out = fig_dir / f"fig_h3_nems_stability_and_rotation.{ext}"
        fig.savefig(f_out, dpi=300)
        save_plot_provenance(str(f_out), src_rel, cols_used)
        if MANUSCRIPT_FIGURES_DIR.exists():
            m_out = MANUSCRIPT_FIGURES_DIR / f_out.name
            shutil.copy2(f_out, m_out)
            save_plot_provenance(str(m_out), src_rel, cols_used)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--n-xi", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=0, help="Micro-probe mode when >0.")
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=REPOSITORY_ROOT / ".tmp" / "h3_stability_suite_ckpt",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args(argv)
    run_stability_suite(
        device=args.device,
        n_xi=args.n_xi,
        max_steps=args.max_steps,
        checkpoint_dir=args.checkpoint_dir,
        output_json=args.output_json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
