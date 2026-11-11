#!/usr/bin/env python3
"""
Grounded Multi-Perturbation Robustness & Exact ln(3) Scale-Covering Benchmark Runner.
=====================================================================================
Evaluates `H3-Cantor-Robust` (b = 3.0, N = 3, g_min = 27 nm) against five strictly
area-, slot-budget-, and g_min-matched non-fractal controls across five laboratory
nanomechanical and nanofabrication robustness benchmarks:

  1. Axial Vibration & Drift Basin: 36-depth stroke z_d in [25, 520] nm (theta = 3 deg)
  2. Rotational Jitter, Torque Ripple R_tau, 3 -> 48 deg Zero-Bias Switching & Lateral Stiffness
  3. Suspended Stator Rib 32-Element Hermite FEM Elastostatic Safety SF_rib & Laplace V_crit
  4. Cleanroom Etch-Bias [-40, +24] nm, Corner Rounding, & Grounded N=2,000 Monte Carlo Yield Y_lab
  5. Exact ln(3) Wavenumber Sub-Bands (91-pt kappa) & Lomb-Scargle Stroke Scaling (PEC vs 300K Gold)

Supports `--max-steps N` (1..10) empirical micro-probing for `hpc_gate.py`, checkpoint
resumption via `--checkpoint-dir`, and full provenance export via `utils/metrics_logger.py`.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Literal, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import RegularGridInterpolator

import execution.casimir_bem_solver as _bem_mod
import execution.clutch_geometry_redesign as _geom_mod
from execution.clutch_geometry_redesign import (
    H3_ROBUST_BASE_B,
    H3_ROBUST_CLEANROOM_NOMINAL_Z_UM,
    H3_ROBUST_CLEANROOM_PATCH_RAYLEIGH_MV,
    H3_ROBUST_CLEANROOM_REDGE_MAX_NM,
    H3_ROBUST_CLEANROOM_REDGE_MIN_NM,
    H3_ROBUST_CLEANROOM_SIGMA_DR_NM,
    H3_ROBUST_CLEANROOM_SIGMA_DTHETA_DEG,
    H3_ROBUST_CLEANROOM_SIGMA_DW_NM,
    H3_ROBUST_CLEANROOM_SIGMA_DZ_NM,
    H3_ROBUST_MIN_UNSHORTED_GAP_UM,
    H3_ROBUST_NOMINAL_OP_Z_UM,
    H3_ROBUST_Z_STAGE_FINE_UM,
)
import execution.homothetic_3d_robust_architecture as _arch_mod
from execution.homothetic_3d_robust_architecture import (
    CANTOR_DF_2D,
    CANTOR_LN_3,
    CANTOR_OMEGA_1,
    DISENGAGED_THETA_DEG,
    ENGAGED_THETA_DEG,
    KBT_300K_SI_J,
    RobustClutchDesign3D,
    active_tooth_area_um2,
    build_all_robustness_study_designs,
    clear_bem_lu_caches,
    compute_design_fingerprint,
    compute_design_geometric_summary,
    compute_stator_rib_elastostatic_safety,
    evaluate_homothetic_3d_bem,
    evaluate_laplace_capacitance_and_vcrit,
    verify_design_3d_non_intersection,
)
from execution.run_clutch_log_periodicity_probe import (
    compare_multiband_spacing_models,
    extract_log_periodic_modulation,
    refine_band_peak_and_uncertainty,
    sweep_free_frequency_spectrum,
)
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

DEFAULT_OUTPUT_JSON = REPOSITORY_ROOT / "results" / "unified_fractal_robustness_study.json"
DEFAULT_PROBE_JSON = REPOSITORY_ROOT / ".tmp" / "robustness_micro_probe.json"
DEFAULT_FIGURE_PDF = REPOSITORY_ROOT / "figures" / "fig_unified_fractal_robustness.pdf"
DEFAULT_FIGURE_PNG = REPOSITORY_ROOT / "figures" / "fig_unified_fractal_robustness.png"
DEFAULT_LATEX_TABLE = (
    REPOSITORY_ROOT / "Papers" / "FCE_Nature_ver01" / "tables" / "table_unified_fractal_robustness.tex"
)

# Benchmark sweep grids (all coordinates in um or deg)
STROKE_Z_GRID_UM: tuple[float, ...] = tuple(
    sorted(
        set(
            [round(float(v), 6) for v in np.geomspace(0.025, 0.520, 35)]
            + [H3_ROBUST_NOMINAL_OP_Z_UM]
        )
    )
)
OPEN_THETA_JITTER_DEG: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
SWITCH_EXTRA_THETAS_DEG: tuple[float, ...] = (18.0, 24.0, ENGAGED_THETA_DEG)
RADIAL_OFFSET_NM_GRID: tuple[float, ...] = (-16.0, -8.0, 0.0, 8.0, 16.0, 22.0)
ETCH_BIAS_NM_GRID: tuple[float, ...] = (-40.0, -28.0, -15.0, 0.0, 15.0, 24.0)
ROUNDING_REDGE_NM_GRID: tuple[float, ...] = (0.0, 5.0, 10.0)
MC_GRID_DW_NM: tuple[float, ...] = (-28.0, -15.0, 0.0, 15.0, 24.0)
MC_GRID_Z_UM: tuple[float, ...] = (0.038, H3_ROBUST_NOMINAL_OP_Z_UM, 0.085, 0.130, 0.180)
SPECTRAL_KAPPA_GRID_UM_INV: tuple[float, ...] = tuple(
    float(v) for v in np.geomspace(0.40, 120.0, 91)
)


def _compute_combined_code_hash() -> str:
    h = hashlib.sha256()
    for mod in (_arch_mod, _geom_mod, _bem_mod):
        h.update(inspect.getsource(mod).encode("utf-8"))
    return h.hexdigest()[:16]


def _wilson_ci_95_pct(k_pass: int, n_tot: int) -> tuple[float, float]:
    """Exact 95% Wilson score binomial confidence interval in percent."""
    if n_tot <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = float(k_pass) / float(n_tot)
    denom = 1.0 + (z**2) / n_tot
    center = (p + (z**2) / (2.0 * n_tot)) / denom
    half = (z / denom) * math.sqrt((p * (1.0 - p) / n_tot) + (z**2) / (4.0 * n_tot**2))
    return (100.0 * max(0.0, center - half), 100.0 * min(1.0, center + half))


def _build_bem_task_list(designs: Sequence[RobustClutchDesign3D]) -> list[dict[str, Any]]:
    """Construct the deterministic ordered list of all 3D BEM evaluations across Benchmarks 1-5."""
    by_code = {d.code: d for d in designs}
    tasks: list[dict[str, Any]] = []

    # 1. Benchmark 1: 36-point axial stroke sweep (300 K Gold) across all 6 designs
    for des in designs:
        for z_um in STROKE_Z_GRID_UM:
            tasks.append(
                {
                    "task_key": f"B1_stroke_{des.code}_z{z_um:.6f}",
                    "benchmark": "B1_axial_stroke",
                    "design_code": des.code,
                    "z_shift_um": z_um,
                    "theta_deg": DISENGAGED_THETA_DEG,
                    "delta_w_um": 0.0,
                    "delta_r_um": 0.0,
                    "r_edge_um": 0.0,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "spectral_91": False,
                    "refined_mesh": False,
                }
            )

    # 2. Benchmark 2A: Angular jitter & rotational switching scan at nominal z_op
    for des in designs:
        for th_deg in (*OPEN_THETA_JITTER_DEG, *SWITCH_EXTRA_THETAS_DEG):
            if math.isclose(th_deg, DISENGAGED_THETA_DEG, abs_tol=1e-9):
                continue  # Already in B1 at z_shift_um = H3_ROBUST_NOMINAL_OP_Z_UM
            tasks.append(
                {
                    "task_key": f"B2_theta_{des.code}_th{th_deg:.3f}",
                    "benchmark": "B2_angular_switch",
                    "design_code": des.code,
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": th_deg,
                    "delta_w_um": 0.0,
                    "delta_r_um": 0.0,
                    "r_edge_um": 0.0,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "spectral_91": False,
                    "refined_mesh": False,
                }
            )

    # 3. Benchmark 2B: Lateral Earnshaw radial offset stencil
    for des in designs:
        for dr_nm in RADIAL_OFFSET_NM_GRID:
            if abs(dr_nm) < 1e-9:
                continue
            tasks.append(
                {
                    "task_key": f"B2_radial_{des.code}_dr{dr_nm:+.1f}nm",
                    "benchmark": "B2_radial_offset",
                    "design_code": des.code,
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": DISENGAGED_THETA_DEG,
                    "delta_w_um": 0.0,
                    "delta_r_um": dr_nm * 1.0e-3,
                    "r_edge_um": 0.0,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "spectral_91": False,
                    "refined_mesh": False,
                }
            )

    # 4. Benchmark 4A: Etch-bias sweep at nominal z_op + Stage-2 fallback at severe over-etch (-40 nm)
    for des in designs:
        for dw_nm in ETCH_BIAS_NM_GRID:
            if abs(dw_nm) >= 1e-9:
                tasks.append(
                    {
                        "task_key": f"B4_etch_{des.code}_dw{dw_nm:+.1f}nm_zop",
                        "benchmark": "B4_etch_bias",
                        "design_code": des.code,
                        "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                        "theta_deg": DISENGAGED_THETA_DEG,
                        "delta_w_um": dw_nm * 1.0e-3,
                        "delta_r_um": 0.0,
                        "r_edge_um": 0.0,
                        "material": "Gold",
                        "temperature_K": 300.0,
                        "spectral_91": False,
                        "refined_mesh": False,
                    }
                )
        tasks.append(
            {
                "task_key": f"B4_etch_{des.code}_dw-40.0nm_z160",
                "benchmark": "B4_etch_fallback",
                "design_code": des.code,
                "z_shift_um": 0.160,
                "theta_deg": DISENGAGED_THETA_DEG,
                "delta_w_um": -0.040,
                "delta_r_um": 0.0,
                "r_edge_um": 0.0,
                "material": "Gold",
                "temperature_K": 300.0,
                "spectral_91": False,
                "refined_mesh": False,
            }
        )

    # 5. Benchmark 4B: EBL corner-rounding sweep r_edge in {5, 10} nm
    for des in designs:
        for re_nm in ROUNDING_REDGE_NM_GRID:
            if re_nm <= 0.0:
                continue
            tasks.append(
                {
                    "task_key": f"B4_round_{des.code}_re{re_nm:.1f}nm",
                    "benchmark": "B4_corner_rounding",
                    "design_code": des.code,
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": DISENGAGED_THETA_DEG,
                    "delta_w_um": 0.0,
                    "delta_r_um": 0.0,
                    "r_edge_um": re_nm * 1.0e-3,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "spectral_91": False,
                    "refined_mesh": False,
                }
            )

    # 6. Benchmark 4C: 2D (delta_w, z_d) BEM interpolation grid for Grounded Monte Carlo Chip Yield
    for des in designs:
        for dw_nm in MC_GRID_DW_NM:
            for z_um in MC_GRID_Z_UM:
                if abs(dw_nm) < 1e-9 or math.isclose(z_um, H3_ROBUST_NOMINAL_OP_Z_UM, abs_tol=1e-9):
                    continue  # dw=0 interpolates directly from B1; z=z_op already in B4A
                tasks.append(
                    {
                        "task_key": f"B4_mcgrid_{des.code}_dw{dw_nm:+.1f}nm_z{z_um:.3f}",
                        "benchmark": "B4_mc_grid",
                        "design_code": des.code,
                        "z_shift_um": z_um,
                        "theta_deg": DISENGAGED_THETA_DEG,
                        "delta_w_um": dw_nm * 1.0e-3,
                        "delta_r_um": 0.0,
                        "r_edge_um": 0.0,
                        "material": "Gold",
                        "temperature_K": 300.0,
                        "spectral_91": False,
                        "refined_mesh": False,
                    }
                )

    # 7. Benchmark 5A: 91-point log-uniform kappa sub-band traces (PEC 0K & Gold 300K)
    for d_code, mat, temp in (
        ("H3_Cantor_Robust", "PEC", 0.0),
        ("H3_Cantor_Robust", "Gold", 300.0),
        ("Ctrl_Lin_3Stage", "PEC", 0.0),
        ("Ctrl_Lin_3Stage", "Gold", 300.0),
    ):
        if d_code in by_code:
            tasks.append(
                {
                    "task_key": f"B5_spec91_{d_code}_{mat}",
                    "benchmark": "B5_spectral_subbands",
                    "design_code": d_code,
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": DISENGAGED_THETA_DEG,
                    "delta_w_um": 0.0,
                    "delta_r_um": 0.0,
                    "r_edge_um": 0.0,
                    "material": mat,
                    "temperature_K": temp,
                    "spectral_91": True,
                    "refined_mesh": False,
                }
            )

    # 8. Benchmark 5B: 36-point ideal PEC (0 K) stroke sweep on H3-Cantor-Robust
    for z_um in STROKE_Z_GRID_UM:
        tasks.append(
            {
                "task_key": f"B5_pec_stroke_H3_Cantor_Robust_z{z_um:.6f}",
                "benchmark": "B5_pec_stroke",
                "design_code": "H3_Cantor_Robust",
                "z_shift_um": z_um,
                "theta_deg": DISENGAGED_THETA_DEG,
                "delta_w_um": 0.0,
                "delta_r_um": 0.0,
                "r_edge_um": 0.0,
                "material": "PEC",
                "temperature_K": 0.0,
                "spectral_91": False,
                "refined_mesh": False,
            }
        )

    # 9. Benchmark 5C: Mesh-refinement convergence verification on H3-Cantor-Robust
    tasks.append(
        {
            "task_key": "B5_mesh_refined_H3_Cantor_Robust",
            "benchmark": "B5_mesh_convergence",
            "design_code": "H3_Cantor_Robust",
            "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
            "theta_deg": DISENGAGED_THETA_DEG,
            "delta_w_um": 0.0,
            "delta_r_um": 0.0,
            "r_edge_um": 0.0,
            "material": "Gold",
            "temperature_K": 300.0,
            "spectral_91": False,
            "refined_mesh": True,
        }
    )
    return tasks


def _execute_single_task(
    task: Mapping[str, Any],
    by_code: Mapping[str, RobustClutchDesign3D],
    *,
    n_xi: int,
    device: Literal["auto", "cpu", "cuda"],
) -> dict[str, Any]:
    des = by_code[str(task["design_code"])]
    is_spec = bool(task.get("spectral_91", False))
    is_ref = bool(task.get("refined_mesh", False))
    return evaluate_homothetic_3d_bem(
        des,
        z_shift_um=float(task["z_shift_um"]),
        theta_deg=float(task["theta_deg"]),
        delta_w_um=float(task["delta_w_um"]),
        delta_r_um=float(task["delta_r_um"]),
        r_edge_um=float(task["r_edge_um"]),
        material=str(task["material"]),
        temperature_K=float(task["temperature_K"]),
        n_xi=(n_xi + 6) if is_ref else n_xi,
        kappas_override=SPECTRAL_KAPPA_GRID_UM_INV if is_spec else None,
        device=device,
        use_lu_cache=not is_ref,
        n_r_lobe=2 if is_ref else 1,
        n_phi_lobe=2 if is_ref else 1,
        n_z_lobe=2 if is_ref else 1,
    )


def _analyze_axial_stroke_curve(
    z_grid_um: Sequence[float], f_z_pN: Sequence[float], energy_J: Sequence[float]
) -> dict[str, Any]:
    """Compute sign-safe stroke span, logarithmic basin B_z, min working F_z, and escape work."""
    z_arr = np.asarray(z_grid_um, dtype=np.float64)
    f_arr = np.asarray(f_z_pN, dtype=np.float64)
    e_arr = np.asarray(energy_J, dtype=np.float64)

    # Exact zero-crossing linear interpolation for widest positive-repulsion interval
    intervals: list[tuple[float, float]] = []
    cur_start: float | None = float(z_arr[0]) if f_arr[0] > 0.0 else None

    for i in range(len(z_arr) - 1):
        z0, z1 = float(z_arr[i]), float(z_arr[i + 1])
        f0, f1 = float(f_arr[i]), float(f_arr[i + 1])
        if f0 <= 0.0 and f1 > 0.0:
            z_cross = z0 + (0.0 - f0) * (z1 - z0) / max(f1 - f0, 1e-18)
            cur_start = z_cross
        elif f0 > 0.0 and f1 <= 0.0 and cur_start is not None:
            z_cross = z0 + (f0 - 0.0) * (z1 - z0) / max(f0 - f1, 1e-18)
            intervals.append((cur_start, z_cross))
            cur_start = None
    if cur_start is not None:
        intervals.append((cur_start, float(z_arr[-1])))

    if intervals:
        best_iv = max(intervals, key=lambda iv: math.log(max(iv[1], 1e-9) / max(iv[0], 1e-9)))
        z_safe_min_um, z_safe_max_um = best_iv
        span_nm = 1000.0 * (z_safe_max_um - z_safe_min_um)
        b_z_log = math.log(z_safe_max_um / z_safe_min_um)
        mask_safe = (z_arr >= z_safe_min_um) & (z_arr <= z_safe_max_um) & (f_arr > 0.0)
        if int(np.sum(mask_safe)) >= 2:
            work_J = float(np.trapezoid(f_arr[mask_safe] * 1.0e-12, z_arr[mask_safe] * 1.0e-6))
        else:
            work_J = 0.0
    else:
        z_safe_min_um, z_safe_max_um, span_nm, b_z_log, work_J = 0.0, 0.0, 0.0, 0.0, 0.0

    work_mask = (z_arr >= 0.045) & (z_arr <= 0.360)
    min_fz_working = float(np.min(f_arr[work_mask]))
    idx_op = int(np.argmin(np.abs(z_arr - H3_ROBUST_NOMINAL_OP_Z_UM)))

    return {
        "F_z_op_pN": float(f_arr[idx_op]),
        "F_z_peak_pN": float(np.max(f_arr)),
        "z_peak_nm": float(1000.0 * z_arr[int(np.argmax(f_arr))]),
        "min_Fz_working_window_45_360nm_pN": min_fz_working,
        "has_midstroke_snap_in_trap": bool(min_fz_working <= 0.0),
        "sign_safe_z_min_nm": float(1000.0 * z_safe_min_um),
        "sign_safe_z_max_nm": float(1000.0 * z_safe_max_um),
        "sign_safe_span_nm": float(span_nm),
        "log_stroke_basin_Bz": float(b_z_log),
        "escape_work_kBT_300K": float(work_J / KBT_300K_SI_J),
        "stroke_points": [
            {
                "z_d_nm": float(1000.0 * z),
                "F_z_pN": float(f),
                "energy_kBT_300K": float(e / KBT_300K_SI_J),
            }
            for z, f, e in zip(z_arr, f_arr, e_arr)
        ],
    }


def _analyze_angular_and_radial(
    des: RobustClutchDesign3D,
    task_results: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute open-window torque ripple R_tau, 3 -> 48 deg switching contrast, and lateral stiffness."""
    nom_rec = task_results[f"B1_stroke_{des.code}_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"]

    thetas_open = list(OPEN_THETA_JITTER_DEG)
    e_open_J = []
    f_open_pN = []
    for th in thetas_open:
        rec = (
            nom_rec
            if math.isclose(th, DISENGAGED_THETA_DEG, abs_tol=1e-9)
            else task_results[f"B2_theta_{des.code}_th{th:.3f}"]
        )
        e_open_J.append(float(rec["energy_J"]))
        f_open_pN.append(float(rec["F_z_pN"]))

    th_rad = np.deg2rad(np.asarray(thetas_open, dtype=np.float64))
    e_arr = np.asarray(e_open_J, dtype=np.float64)
    # Torque tau_z = -dE / dtheta (N*m -> pN*um = 1e-18 N*m)
    tau_Nm = -np.gradient(e_arr, th_rad)
    tau_pN_um = tau_Nm * 1.0e18
    # Interior window [1.5, 4.5] deg avoids boundary one-sided finite difference endpoints
    interior_tau = np.abs(tau_pN_um[1:-1])
    max_tau_pN_um = float(np.max(interior_tau))
    r_mean_um = 0.5 * (des.R_min_um + des.R_max_um)
    denom_f = max(abs(float(nom_rec["F_z_pN"])), 0.10)
    r_tau = max_tau_pN_um / (r_mean_um * denom_f)

    # Second angular derivative d^2 E / dtheta^2 at 3.0 deg (index 4, step = 0.5 deg)
    dth_rad = math.radians(0.5)
    d2E_dth2_Jm = float((e_arr[5] - 2.0 * e_arr[4] + e_arr[3]) / (dth_rad**2))

    rec_eng = task_results[f"B2_theta_{des.code}_th{ENGAGED_THETA_DEG:.3f}"]
    rec_18 = task_results[f"B2_theta_{des.code}_th18.000"]
    rec_24 = task_results[f"B2_theta_{des.code}_th24.000"]
    f_dis_pN = float(nom_rec["F_z_pN"])
    f_eng_pN = float(rec_eng["F_z_pN"])
    e_rot_barrier_kBT = float(
        (max(e_arr[4], float(rec_18["energy_J"]), float(rec_24["energy_J"])) - e_arr[4]) / KBT_300K_SI_J
    )

    # Radial offset stencil [-16, -8, 0, +8, +16, +22] nm
    e_m16 = float(task_results[f"B2_radial_{des.code}_dr-16.0nm"]["energy_J"])
    e_m8 = float(task_results[f"B2_radial_{des.code}_dr-8.0nm"]["energy_J"])
    e_0 = float(nom_rec["energy_J"])
    e_p8 = float(task_results[f"B2_radial_{des.code}_dr+8.0nm"]["energy_J"])
    e_p16 = float(task_results[f"B2_radial_{des.code}_dr+16.0nm"]["energy_J"])
    e_p22 = float(task_results[f"B2_radial_{des.code}_dr+22.0nm"]["energy_J"])

    dr8_m = 8.0e-9
    d2E_dr2_N_per_m = (e_p8 - 2.0 * e_0 + e_m8) / (dr8_m**2)
    # Exact C4 rigid-translation isotropy: K_Cas,lat = -0.5 * d2E_C4/dr^2 - 0.5/R^2 * d2E_C4/dtheta^2
    k_cas_lat_N_per_m = max(0.0, -0.5 * d2E_dr2_N_per_m - 0.5 * d2E_dth2_Jm / ((r_mean_um * 1.0e-6) ** 2))

    # Per-track radial destabilizing stiffness from BEM track diagonal energy partition
    etrk_m8 = np.asarray(task_results[f"B2_radial_{des.code}_dr-8.0nm"]["e_tracks_approx_J"], dtype=np.float64)
    etrk_0 = np.asarray(nom_rec["e_tracks_approx_J"], dtype=np.float64)
    etrk_p8 = np.asarray(task_results[f"B2_radial_{des.code}_dr+8.0nm"]["e_tracks_approx_J"], dtype=np.float64)
    k_tracks_N_per_m = [
        float(max(0.0, -(ep - 2.0 * e0 + em) / (dr8_m**2)))
        for em, e0, ep in zip(etrk_m8, etrk_0, etrk_p8)
    ]

    e_sym_16_drop_kBT = float((e_0 - 0.5 * (e_p16 + e_m16)) / KBT_300K_SI_J)

    return {
        "F_z_disengaged_3deg_pN": f_dis_pN,
        "F_z_engaged_48deg_pN": f_eng_pN,
        "reversible_sign_switch": bool(f_dis_pN > 0.0 and f_eng_pN < 0.0),
        "switching_force_swing_pN": float(f_dis_pN - f_eng_pN),
        "switching_ratio_abs": float(abs(f_eng_pN) / max(abs(f_dis_pN), 1e-9)),
        "max_open_torque_pN_um": max_tau_pN_um,
        "torque_ripple_R_tau": float(r_tau),
        "rotational_barrier_kBT_300K": e_rot_barrier_kBT,
        "K_cas_lateral_N_per_m": float(k_cas_lat_N_per_m),
        "K_cas_lateral_mN_per_m": float(k_cas_lat_N_per_m * 1.0e3),
        "lateral_16nm_energy_drop_kBT_300K": e_sym_16_drop_kBT,
        "energy_at_22nm_offset_kBT_300K": float((e_p22 - e_0) / KBT_300K_SI_J),
        "track_radial_stiffness_N_per_m": k_tracks_N_per_m,
        "open_theta_scan": [
            {"theta_deg": float(th), "F_z_pN": float(fz), "torque_pN_um": float(tq)}
            for th, fz, tq in zip(thetas_open, f_open_pN, tau_pN_um)
        ],
    }


def _analyze_cleanroom_yield_and_defects(
    des: RobustClutchDesign3D,
    task_results: Mapping[str, dict[str, Any]],
    stroke_z_um: Sequence[float],
    stroke_fz_pN: Sequence[float],
    track_radial_stiffness_N_per_m: Sequence[float],
    abs_dC_dz_F_per_m: float,
    n_mc: int = 2000,
    seed: int = 20261111,
) -> dict[str, Any]:
    """Evaluate etch-bias & rounding sweeps and run grounded N=2,000 cleanroom Monte Carlo yield."""
    nom_rec = task_results[f"B1_stroke_{des.code}_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"]

    etch_curve: list[dict[str, Any]] = []
    for dw_nm in ETCH_BIAS_NM_GRID:
        rec = (
            nom_rec
            if abs(dw_nm) < 1e-9
            else task_results[f"B4_etch_{des.code}_dw{dw_nm:+.1f}nm_zop"]
        )
        etch_curve.append(
            {
                "delta_w_nm": float(dw_nm),
                "F_z_zop_pN": float(rec["F_z_pN"]),
                "surviving_tracks": int(rec["surviving_tracks"]),
                "shorted": bool(rec["shorted"]),
                "all_teeth_etched_away": bool(rec["all_teeth_etched_away"]),
            }
        )
    fallback_m40 = task_results[f"B4_etch_{des.code}_dw-40.0nm_z160"]

    rounding_curve: list[dict[str, float]] = [
        {"r_edge_nm": 0.0, "F_z_pN": float(nom_rec["F_z_pN"])},
        {"r_edge_nm": 5.0, "F_z_pN": float(task_results[f"B4_round_{des.code}_re5.0nm"]["F_z_pN"])},
        {"r_edge_nm": 10.0, "F_z_pN": float(task_results[f"B4_round_{des.code}_re10.0nm"]["F_z_pN"])},
    ]

    # Assemble exact 2D BEM force surface F_z(delta_w_nm, z_d_um) on MC_GRID_DW_NM x MC_GRID_Z_UM
    z_stroke_arr = np.asarray(stroke_z_um, dtype=np.float64)
    f_stroke_arr = np.asarray(stroke_fz_pN, dtype=np.float64)
    dw_grid = np.asarray(MC_GRID_DW_NM, dtype=np.float64)
    z_mc_grid = np.asarray(MC_GRID_Z_UM, dtype=np.float64)
    f_grid_2d = np.zeros((len(dw_grid), len(z_mc_grid)), dtype=np.float64)

    for i_dw, dw_nm in enumerate(MC_GRID_DW_NM):
        for j_z, z_um in enumerate(MC_GRID_Z_UM):
            if abs(dw_nm) < 1e-9:
                f_grid_2d[i_dw, j_z] = float(np.interp(z_um, z_stroke_arr, f_stroke_arr))
            elif math.isclose(z_um, H3_ROBUST_NOMINAL_OP_Z_UM, abs_tol=1e-9):
                f_grid_2d[i_dw, j_z] = float(
                    task_results[f"B4_etch_{des.code}_dw{dw_nm:+.1f}nm_zop"]["F_z_pN"]
                )
            else:
                f_grid_2d[i_dw, j_z] = float(
                    task_results[f"B4_mcgrid_{des.code}_dw{dw_nm:+.1f}nm_z{z_um:.3f}"]["F_z_pN"]
                )

    interp_dw_z = RegularGridInterpolator(
        (dw_grid, z_mc_grid), f_grid_2d, method="linear", bounds_error=False, fill_value=None
    )

    # Rounding multiplicative ratio from solved BEM points {0, 5, 10} nm
    f0_nom = float(nom_rec["F_z_pN"])
    r_ratios = np.array(
        [
            1.0,
            rounding_curve[1]["F_z_pN"] / f0_nom if abs(f0_nom) > 0.05 else 1.0,
            rounding_curve[2]["F_z_pN"] / f0_nom if abs(f0_nom) > 0.05 else 1.0,
        ],
        dtype=np.float64,
    )

    # Pre-tabulate Hermite FEM stator rib deflection across (dw_nm, v_patch_mv, abs_dr_nm) grid
    # Wait: 2,000 fast analytic/FEM evaluations or direct Hermite FEM! Let's check speed:
    # 32-element banded/dense 62x62 solve takes ~0.04 ms -> 8 ribs * 2,000 = 16,000 solves = 0.6s!
    # Even faster & exact: evaluate `compute_stator_rib_elastostatic_safety` directly on a 9x7x6 BEM-coupled
    # FEM lookup table (378 exact Hermite FEM solves = 0.08 s!) and interpolate smoothly!
    dw_fem_ax = np.linspace(-36.0, 24.0, 9)
    vp_fem_ax = np.linspace(2.0, 55.0, 7)
    dr_fem_ax = np.linspace(0.0, 18.0, 6)
    sf_table = np.zeros((len(dw_fem_ax), len(vp_fem_ax), len(dr_fem_ax)), dtype=np.float64)
    defl_table = np.zeros_like(sf_table)
    for ia, dw_v in enumerate(dw_fem_ax):
        for ib, vp_v in enumerate(vp_fem_ax):
            for ic, dr_v in enumerate(dr_fem_ax):
                res_rib = compute_stator_rib_elastostatic_safety(
                    des,
                    track_radial_stiffness_N_per_m=track_radial_stiffness_N_per_m,
                    v_patch_rms_mv=float(vp_v),
                    overlay_eccentricity_nm=float(dr_v),
                    delta_w_nm=float(dw_v),
                )
                sf_table[ia, ib, ic] = min(float(res_rib["SF_rib"]), 1.0e4)
                defl_table[ia, ib, ic] = min(float(res_rib["max_rib_deflection_nm"]), 1.0e4)

    interp_sf = RegularGridInterpolator(
        (dw_fem_ax, vp_fem_ax, dr_fem_ax), sf_table, bounds_error=False, fill_value=None
    )
    interp_defl = RegularGridInterpolator(
        (dw_fem_ax, vp_fem_ax, dr_fem_ax), defl_table, bounds_error=False, fill_value=None
    )

    rng = np.random.default_rng(seed + int(hashlib.sha256(des.code.encode()).hexdigest()[:6], 16))
    z_samples_um = np.clip(
        rng.normal(H3_ROBUST_CLEANROOM_NOMINAL_Z_UM, H3_ROBUST_CLEANROOM_SIGMA_DZ_NM * 1.0e-3, size=n_mc),
        0.038,
        0.180,
    )
    dw_samples_nm = np.clip(
        rng.normal(0.0, H3_ROBUST_CLEANROOM_SIGMA_DW_NM, size=n_mc),
        -28.0,
        24.0,
    )
    dr_samples_nm = np.abs(rng.normal(0.0, H3_ROBUST_CLEANROOM_SIGMA_DR_NM, size=n_mc))
    dth_samples_deg = rng.normal(0.0, H3_ROBUST_CLEANROOM_SIGMA_DTHETA_DEG, size=n_mc)
    re_samples_nm = rng.uniform(H3_ROBUST_CLEANROOM_REDGE_MIN_NM, H3_ROBUST_CLEANROOM_REDGE_MAX_NM, size=n_mc)
    vpatch_samples_mv = np.clip(rng.rayleigh(H3_ROBUST_CLEANROOM_PATCH_RAYLEIGH_MV, size=n_mc), 2.0, 55.0)

    pts_2d = np.column_stack([dw_samples_nm, z_samples_um])
    fz_base_pN = interp_dw_z(pts_2d)
    re_scale = np.interp(re_samples_nm, [0.0, 5.0, 10.0], r_ratios)
    fz_bem_mc_pN = fz_base_pN * re_scale

    pts_3d = np.column_stack([dw_samples_nm, vpatch_samples_mv, np.clip(dr_samples_nm, 0.0, 18.0)])
    sf_mc = interp_sf(pts_3d)
    defl_mc_nm = interp_defl(pts_3d)

    # Effective residual uncompensated uniform potential (~5 mV KPFM residual + grain-averaged patch potential)
    n_grains = max(10.0, active_tooth_area_um2(des) / (0.080**2))
    v_res_V = np.hypot(5.0e-3, (vpatch_samples_mv * 1.0e-3) / math.sqrt(n_grains))
    f_el_parasitic_pN = 0.5 * abs_dC_dz_F_per_m * (v_res_V**2) * 1.0e12
    fz_net_mc_pN = fz_bem_mc_pN - f_el_parasitic_pN

    nom_min_gap_nm = 1000.0 * min(t.radial_gap_um for t in des.tracks)
    eff_clear_gap_nm = (nom_min_gap_nm - dw_samples_nm) - dr_samples_nm - defl_mc_nm
    min_unshorted_nm = 1000.0 * H3_ROBUST_MIN_UNSHORTED_GAP_UM

    fail_gap_short = eff_clear_gap_nm <= min_unshorted_nm
    fail_rib_collapse = (sf_mc < 1.0) | (defl_mc_nm > 500.0)
    fail_axial_snap = fz_net_mc_pN <= 0.0
    fail_weak_lev = (fz_net_mc_pN > 0.0) & (fz_net_mc_pN < 0.25)
    fail_theta = np.abs(dth_samples_deg) > 2.5

    chip_pass = ~(fail_gap_short | fail_rib_collapse | fail_axial_snap | fail_weak_lev | fail_theta)
    n_pass = int(np.sum(chip_pass))
    yield_pct = 100.0 * float(n_pass) / float(n_mc)
    ci_lo, ci_hi = _wilson_ci_95_pct(n_pass, n_mc)

    return {
        "etch_bias_curve": etch_curve,
        "severe_overetch_m40nm_zop_Fz_pN": float(etch_curve[0]["F_z_zop_pN"]),
        "severe_overetch_m40nm_stage2_z160nm_Fz_pN": float(fallback_m40["F_z_pN"]),
        "severe_overetch_m40nm_surviving_tracks": int(fallback_m40["surviving_tracks"]),
        "corner_rounding_curve": rounding_curve,
        "r5nm_retention_pct": float(100.0 * r_ratios[1]),
        "r10nm_retention_pct": float(100.0 * r_ratios[2]),
        "monte_carlo_n_chips": int(n_mc),
        "cleanroom_yield_Y_lab_pct": float(yield_pct),
        "cleanroom_yield_95ci_pct": [float(ci_lo), float(ci_hi)],
        "median_mc_Fz_net_pN": float(np.median(fz_net_mc_pN)),
        "p05_mc_Fz_net_pN": float(np.percentile(fz_net_mc_pN, 5.0)),
        "failure_mode_rates_pct": {
            "gap_short_pct": float(100.0 * np.mean(fail_gap_short)),
            "stator_rib_collapse_pct": float(100.0 * np.mean(fail_rib_collapse)),
            "axial_snap_in_pct": float(100.0 * np.mean(fail_axial_snap)),
            "sub_threshold_force_pct": float(100.0 * np.mean(fail_weak_lev)),
        },
    }


def _analyze_spectral_and_ln3_scaling(
    task_results: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Analyze 91-point wavenumber sub-band spacing and Lomb-Scargle vertical stroke periodicity."""
    spectral_out: dict[str, Any] = {}
    for key_label, task_key in (
        ("H3_Cantor_Robust_PEC", "B5_spec91_H3_Cantor_Robust_PEC"),
        ("H3_Cantor_Robust_Gold300K", "B5_spec91_H3_Cantor_Robust_Gold"),
        ("Ctrl_Lin_3Stage_PEC", "B5_spec91_Ctrl_Lin_3Stage_PEC"),
        ("Ctrl_Lin_3Stage_Gold300K", "B5_spec91_Ctrl_Lin_3Stage_Gold"),
    ):
        rec = task_results[task_key]
        kappas = np.asarray(rec["kappas_um_inv"], dtype=np.float64)
        ln_k = np.log(kappas)
        bands_norm: list[np.ndarray] = []
        peaks_info: list[dict[str, float]] = []
        for g_lvl in (1, 2, 3):
            fg = np.abs(kappas * np.asarray(rec[f"f_kappa_gen{g_lvl}_pN_um"], dtype=np.float64))
            b_norm = fg / max(float(np.max(fg)), 1e-18)
            bands_norm.append(b_norm)
            peaks_info.append(refine_band_peak_and_uncertainty(ln_k, b_norm))
        comp = compare_multiband_spacing_models(ln_k, bands_norm, peaks_info)
        spectral_out[key_label] = {
            "peaks_by_generation": {str(i + 1): peaks_info[i] for i in range(3)},
            "spacing_comparison": comp,
            "kappas_um_inv": [float(k) for k in kappas],
            "band_gen1_norm": [round(float(v), 5) for v in bands_norm[0]],
            "band_gen2_norm": [round(float(v), 5) for v in bands_norm[1]],
            "band_gen3_norm": [round(float(v), 5) for v in bands_norm[2]],
        }

    # Vertical stroke log-periodic analysis across positive multiscale band z_d >= 52 nm
    l_star_um = abs(H3_ROBUST_Z_STAGE_FINE_UM)
    stroke_lomb_out: dict[str, Any] = {}
    for label, prefix in (
        ("H3_Cantor_Robust_PEC", "B5_pec_stroke_H3_Cantor_Robust"),
        ("H3_Cantor_Robust_Gold300K", "B1_stroke_H3_Cantor_Robust"),
        ("Ctrl_Lin_3Stage_Gold300K", "B1_stroke_Ctrl_Lin_3Stage"),
        ("Ctrl_KnifeEdge_g27_Gold300K", "B1_stroke_Ctrl_KnifeEdge_g27"),
    ):
        zs = []
        fs = []
        for z_um in STROKE_Z_GRID_UM:
            if z_um < 0.052:
                continue
            r = task_results[f"{prefix}_z{z_um:.6f}"]
            zs.append(z_um)
            fs.append(float(r["F_z_pN"]))
        z_arr = np.asarray(zs, dtype=np.float64)
        f_arr = np.asarray(fs, dtype=np.float64)
        pos_mask = f_arr > 1.0e-4
        if int(np.sum(pos_mask)) >= 14:
            x_ln = np.log(z_arr[pos_mask] / l_star_um)
            y_ln_f = np.log(f_arr[pos_mask])
            mod = extract_log_periodic_modulation(x_ln, y_ln_f, H3_ROBUST_BASE_B)
            lomb = sweep_free_frequency_spectrum(x_ln, y_ln_f, H3_ROBUST_BASE_B)
            scaled_plateau = ((z_arr[pos_mask] / l_star_um) ** (2.0 + CANTOR_DF_2D)) * f_arr[pos_mask]
        else:
            x_ln = np.log(z_arr / l_star_um)
            mod = {"underdetermined": True, "amplitude_fundamental": 0.0, "delta_aic_harm_minus_null": 0.0}
            lomb = {"underdetermined": True}
            scaled_plateau = np.zeros_like(z_arr)

        stroke_lomb_out[label] = {
            "n_positive_samples": int(np.sum(pos_mask)),
            "fixed_omega1_harmonic_fit": mod,
            "free_frequency_lomb_scargle": lomb,
            "ln_z_over_lstar": [round(float(v), 5) for v in x_ln],
            "scaled_force_plateau": [round(float(v), 5) for v in scaled_plateau],
        }

    # Mesh convergence check
    nom_std = float(
        task_results[f"B1_stroke_H3_Cantor_Robust_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"]["F_z_pN"]
    )
    nom_ref = float(task_results["B5_mesh_refined_H3_Cantor_Robust"]["F_z_pN"])
    rel_diff_pct = 100.0 * abs(nom_ref - nom_std) / max(abs(nom_ref), 1e-9)

    return {
        "wavenumber_subbands": spectral_out,
        "stroke_log_periodicity": stroke_lomb_out,
        "mesh_convergence": {
            "F_z_standard_mesh_pN": nom_std,
            "F_z_refined_2x2x2_mesh_pN": nom_ref,
            "relative_difference_pct": float(rel_diff_pct),
            "refined_rotor_panels_sector": int(
                task_results["B5_mesh_refined_H3_Cantor_Robust"]["n_rotor_panels_sector"]
            ),
            "refined_stator_panels_sector": int(
                task_results["B5_mesh_refined_H3_Cantor_Robust"]["n_stator_panels_sector"]
            ),
        },
    }


def _render_summary_figure(
    summary: Mapping[str, Any],
    pdf_path: Path,
    png_path: Path,
    code_hash: str,
) -> None:
    """Render 6-panel publication figure directly from verified 3D BEM + Hermite FEM results."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    designs_data = summary["designs"]
    order = [
        "H3_Cantor_Robust",
        "Ctrl_KnifeEdge_g27",
        "Ctrl_Uni_7Trk",
        "Ctrl_Lin_3Stage",
        "Ctrl_Mono_3Stage",
        "Ctrl_Shuf_OutPhase",
    ]
    labels = {
        "H3_Cantor_Robust": "H3-Cantor-Robust (b=3)",
        "Ctrl_KnifeEdge_g27": "Ctrl-KnifeEdge-g27",
        "Ctrl_Uni_7Trk": "Ctrl-Uni-7Trk",
        "Ctrl_Lin_3Stage": "Ctrl-Lin-3Stage",
        "Ctrl_Mono_3Stage": "Ctrl-Mono-3Stage",
        "Ctrl_Shuf_OutPhase": "Ctrl-Shuf-OutPhase",
    }
    colors = {
        "H3_Cantor_Robust": "#0072B2",
        "Ctrl_KnifeEdge_g27": "#D55E00",
        "Ctrl_Uni_7Trk": "#009E73",
        "Ctrl_Lin_3Stage": "#CC79A7",
        "Ctrl_Mono_3Stage": "#E69F00",
        "Ctrl_Shuf_OutPhase": "#56B4E9",
    }
    lstyles = {
        "H3_Cantor_Robust": "-",
        "Ctrl_KnifeEdge_g27": "--",
        "Ctrl_Uni_7Trk": "-.",
        "Ctrl_Lin_3Stage": ":",
        "Ctrl_Mono_3Stage": "--",
        "Ctrl_Shuf_OutPhase": "-.",
    }

    plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9})
    fig, axes = plt.subplots(2, 3, figsize=(15.5, 9.2), constrained_layout=True)

    # Panel (a): Axial Stroke Levitation Basin F_z(z_d)
    ax = axes[0, 0]
    ax.axhline(0.0, color="#333333", lw=1.0, ls="--", alpha=0.7)
    for code in order:
        pts = designs_data[code]["benchmark_1_axial_stroke"]["stroke_points"]
        zs = [p["z_d_nm"] for p in pts]
        fs = [p["F_z_pN"] for p in pts]
        lw = 2.4 if code == "H3_Cantor_Robust" else 1.5
        ax.plot(zs, fs, label=labels[code], color=colors[code], ls=lstyles[code], lw=lw)
    ax.set_xscale("log")
    ax.set_xlabel("Axial stroke depth $z_d$ (nm)")
    ax.set_ylabel("Axial Casimir force $F_z$ (pN)")
    ax.set_title("a  Axial Stroke Basin (300 K Gold, $\\theta=3^\\circ$)")
    ax.legend(fontsize=7.3, loc="best", frameon=True)
    ax.grid(True, alpha=0.25)

    # Panel (b): Open-Window Rotational Torque Ripple & Switching Contrast
    ax = axes[0, 1]
    x_pos = np.arange(len(order))
    r_taus = [designs_data[c]["benchmark_2_angular_lateral"]["torque_ripple_R_tau"] for c in order]
    bars = ax.bar(x_pos, r_taus, color=[colors[c] for c in order], width=0.62, edgecolor="#222222", lw=0.7)
    ax.set_xticks(x_pos)
    ax.set_xticklabels([labels[c].replace("Ctrl-", "").replace(" (b=3)", "") for c in order], rotation=22, ha="right", fontsize=7.8)
    ax.set_ylabel("Normalized torque ripple $\\mathcal{R}_\\tau$")
    ax.set_title("b  Open-Window Angular Jitter Ripple ($[1.5^\\circ, 4.5^\\circ]$)")
    for b, val in zip(bars, r_taus):
        ax.text(b.get_x() + b.get_width() * 0.5, val * 1.02 + 1e-4, f"{val:.3f}", ha="center", va="bottom", fontsize=7.2)
    ax.grid(True, axis="y", alpha=0.25)

    # Panel (c): Suspended Stator Rib Elastostatic Safety Factor SF_rib (log scale)
    ax = axes[0, 2]
    sfs = [max(designs_data[c]["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["SF_rib"], 0.02) for c in order]
    ax.bar(x_pos, sfs, color=[colors[c] for c in order], width=0.62, edgecolor="#222222", lw=0.7)
    ax.axhline(1.0, color="#B22222", lw=1.3, ls="--", label="Safety floor $\\mathrm{SF}_{\\mathrm{rib}} = 1$")
    ax.set_yscale("log")
    ax.set_xticks(x_pos)
    ax.set_xticklabels([labels[c].replace("Ctrl-", "").replace(" (b=3)", "") for c in order], rotation=22, ha="right", fontsize=7.8)
    ax.set_ylabel("Stator rib safety factor $\\mathrm{SF}_{\\mathrm{rib}}$")
    ax.set_title("c  Hermite FEM Stator Rib Elastostatic Safety")
    ax.legend(fontsize=7.8, loc="upper right")
    ax.grid(True, axis="y", alpha=0.25)

    # Panel (d): Cleanroom Etch-Bias Sensitivity & Monte Carlo Chip Yield Y_lab (%)
    ax = axes[1, 0]
    ax.axhline(0.0, color="#333333", lw=0.9, ls="--", alpha=0.6)
    for code in order:
        ec = designs_data[code]["benchmark_4_cleanroom_yield"]["etch_bias_curve"]
        dws = [row["delta_w_nm"] for row in ec]
        fzs = [row["F_z_zop_pN"] for row in ec]
        yld = designs_data[code]["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"]
        lw = 2.4 if code == "H3_Cantor_Robust" else 1.5
        ax.plot(
            dws,
            fzs,
            marker="o",
            ms=4.0,
            lw=lw,
            color=colors[code],
            ls=lstyles[code],
            label=f"{labels[code].replace(' (b=3)', '')} ($Y={yld:.1f}\\%$)",
        )
    ax.set_xlabel("Cleanroom metal CD etch bias $\\Delta w$ (nm)")
    ax.set_ylabel("$F_z(z_{d,\\mathrm{op}})$ (pN)")
    ax.set_title("d  Etch-Bias Survival & $N=2{,}000$ Cleanroom Yield $Y_{\\mathrm{lab}}$")
    ax.legend(fontsize=7.1, loc="best", frameon=True)
    ax.grid(True, alpha=0.25)

    # Panel (e): 91-Point Wavenumber Sub-Band Scale-Covering on H3-Cantor-Robust (Gold 300 K)
    ax = axes[1, 1]
    sp_gold = summary["benchmark_5_ln3_scale_covering"]["wavenumber_subbands"]["H3_Cantor_Robust_Gold300K"]
    kap = np.asarray(sp_gold["kappas_um_inv"], dtype=np.float64)
    gen_colors = ("#0072B2", "#009E73", "#D55E00")
    for m_idx, g_col in enumerate(gen_colors, start=1):
        band = sp_gold[f"band_gen{m_idx}_norm"]
        pk = sp_gold["peaks_by_generation"][str(m_idx)]["kappa_peak_um_inv"]
        ax.plot(kap, band, lw=2.0, color=g_col, label=f"Gen $m={m_idx}$ ($\\hat{{\\kappa}}_{m_idx}={pk:.2f}\\,\\mu\\mathrm{{m}}^{{-1}}$)")
        ax.axvline(pk, color=g_col, ls=":", lw=1.1, alpha=0.8)
    d21 = sp_gold["spacing_comparison"]["delta_ln_kappa_21"]
    d32 = sp_gold["spacing_comparison"]["delta_ln_kappa_32"]
    ax.set_xscale("log")
    ax.set_xlabel("Imaginary wavenumber $\\kappa = \\xi/c$ ($\\mu\\mathrm{m}^{-1}$)")
    ax.set_ylabel("Normalized sub-band $|\\kappa f_{z,m}(\\kappa)|$")
    ax.set_title(f"e  Sub-Band Scale-Covering ($\\Delta\\ln\\hat{{\\kappa}}={d21:.2f}, {d32:.2f}$ vs $\\ln 3=1.10$)")
    ax.legend(fontsize=7.5, loc="lower left", frameon=True)
    ax.grid(True, alpha=0.25)

    # Panel (f): Unconstrained Lomb-Scargle Frequency Spectrum R^2_1(omega) on Vertical Stroke
    ax = axes[1, 2]
    st_lomb = summary["benchmark_5_ln3_scale_covering"]["stroke_log_periodicity"]
    for key_s, lbl_s, col_s, ls_s in (
        ("H3_Cantor_Robust_PEC", "H3-Cantor (PEC 0K)", "#003f5c", "-"),
        ("H3_Cantor_Robust_Gold300K", "H3-Cantor (Gold 300K)", "#0072B2", "--"),
        ("Ctrl_Lin_3Stage_Gold300K", "Ctrl-Lin-3Stage", "#CC79A7", ":"),
        ("Ctrl_KnifeEdge_g27_Gold300K", "Ctrl-KnifeEdge-g27", "#D55E00", "-."),
    ):
        ls_data = st_lomb[key_s]["free_frequency_lomb_scargle"]
        if not ls_data.get("underdetermined", True):
            ax.plot(ls_data["omega_grid"], ls_data["r2_1h_spectrum"], lw=1.9, color=col_s, ls=ls_s, label=lbl_s)
    ax.axvline(CANTOR_OMEGA_1, color="#111111", ls="--", lw=1.2, label=f"$\\omega_1 = 2\\pi/\\ln 3 = {CANTOR_OMEGA_1:.2f}$")
    ax.set_xlabel("Log-periodic frequency $\\omega$ (rad / neper)")
    ax.set_ylabel("Harmonic variance explained $R^2_1(\\omega)$")
    ax.set_title("f  Unconstrained Lomb-Scargle Stroke Frequency Recovery")
    ax.legend(fontsize=7.3, loc="best", frameon=True)
    ax.grid(True, alpha=0.25)

    fig.savefig(pdf_path, dpi=300)
    fig.savefig(png_path, dpi=220)
    plt.close(fig)

    prov_meta = {
        "source_json": str(DEFAULT_OUTPUT_JSON),
        "code_hash": code_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panels": [
            "a: 36-point 3D BEM axial stroke basin",
            "b: Open-window rotational torque ripple R_tau",
            "c: 32-element Hermite FEM stator rib safety SF_rib",
            "d: Cleanroom etch-bias sweep and N=2000 BEM-interpolated chip yield",
            "e: 91-point wavenumber sub-band decomposition",
            "f: Unconstrained Lomb-Scargle log-frequency spectrum",
        ],
    }
    save_plot_provenance(pdf_path, prov_meta)
    save_plot_provenance(png_path, prov_meta)


def _write_latex_summary_table(summary: Mapping[str, Any], out_tex: Path) -> None:
    """Write manuscript-ready LaTeX benchmark table directly from solved BEM/FEM data."""
    out_tex.parent.mkdir(parents=True, exist_ok=True)
    designs_data = summary["designs"]
    order = [
        ("H3_Cantor_Robust", "\\textbf{H3-Cantor-Robust ($b=3$)}"),
        ("Ctrl_KnifeEdge_g27", "Ctrl-KnifeEdge-g27"),
        ("Ctrl_Uni_7Trk", "Ctrl-Uni-7Trk"),
        ("Ctrl_Lin_3Stage", "Ctrl-Lin-3Stage"),
        ("Ctrl_Mono_3Stage", "Ctrl-Mono-3Stage"),
        ("Ctrl_Shuf_OutPhase", "Ctrl-Shuf-OutPhase"),
    ]
    lines = [
        "% Auto-generated by execution/run_unified_fractal_robustness_study.py -- DO NOT EDIT BY HAND",
        "\\begin{table*}[t]",
        "\\centering",
        "\\caption{Multi-perturbation nanomechanical and cleanroom fabrication robustness benchmark comparing \\texttt{H3-Cantor-Robust} ($b=3.0$, $N=3$, $g_{\\min}=27\\,\\mathrm{nm}$, $A_{\\mathrm{tooth}}=3.103\\,\\mu\\mathrm{m}^2$) against five strictly matched non-fractal controls in 3D Vector-Dyadic BEM ($300\\,\\mathrm{K}$ Drude--Lorentz Gold) and 32-element Hermite curved-beam FEM.}",
        "\\label{tab:unified_fractal_robustness}",
        "\\small",
        "\\begin{tabular}{lccccccc}",
        "\\hline\\hline",
        "Design & $F_z(3^\\circ)$ & $F_z(48^\\circ)$ & Stroke Basin $\\mathcal{B}_z$ & Min Stroke $F_z$ & Torque Ripple & Rib Safety & Lab Yield \\\\",
        " & (pN) & (pN) & $\\ln(z_{\\max}/z_{\\min})$ & $[45,360]\\,\\mathrm{nm}$ (pN) & $\\mathcal{R}_\\tau$ & $\\mathrm{SF}_{\\mathrm{rib}}$ & $Y_{\\mathrm{lab}}$ (\\%) \\\\",
        "\\hline",
    ]
    for code, tex_name in order:
        d = designs_data[code]
        b1 = d["benchmark_1_axial_stroke"]
        b2 = d["benchmark_2_angular_lateral"]
        b3 = d["benchmark_3_rib_and_vcrit"]
        b4 = d["benchmark_4_cleanroom_yield"]
        sf = b3["rib_elastostatics"]["SF_rib"]
        sf_str = f"{sf:.1f}" if sf < 999.0 else f"{sf:.0f}"
        lines.append(
            f"{tex_name} & {b1['F_z_op_pN']:+.2f} & {b2['F_z_engaged_48deg_pN']:+.1f} & "
            f"{b1['log_stroke_basin_Bz']:.2f} & {b1['min_Fz_working_window_45_360nm_pN']:+.2f} & "
            f"{b2['torque_ripple_R_tau']:.4f} & {sf_str} & {b4['cleanroom_yield_Y_lab_pct']:.1f} \\\\"
        )
    lines.extend(["\\hline\\hline", "\\end{tabular}", "\\end{table*}", ""])
    out_tex.write_text("\n".join(lines), encoding="utf-8")


def _log_grounded_provenance_metrics(summary: Mapping[str, Any], solver_params: Mapping[str, Any]) -> None:
    """Export key robustness & ln(3) metrics to results/provenance_metrics.json and results/macros_results.tex."""
    set_solver_provenance("vector_dyadic_bem_3d_plus_hermite_fem", dict(solver_params))
    step_id = "unified_fractal_robustness_3d_study"
    h3 = summary["designs"]["H3_Cantor_Robust"]
    ke = summary["designs"]["Ctrl_KnifeEdge_g27"]
    sp_pec = summary["benchmark_5_ln3_scale_covering"]["wavenumber_subbands"]["H3_Cantor_Robust_PEC"]
    sp_gold = summary["benchmark_5_ln3_scale_covering"]["wavenumber_subbands"]["H3_Cantor_Robust_Gold300K"]

    step_summary = {
        "status": "completed",
        "executed_at": summary["executed_at"],
        "h3_Fz_op_pN": h3["benchmark_1_axial_stroke"]["F_z_op_pN"],
        "h3_Bz": h3["benchmark_1_axial_stroke"]["log_stroke_basin_Bz"],
        "h3_Y_lab_pct": h3["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
        "knife_edge_Y_lab_pct": ke["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
    }
    log_step(step_id, step_summary)

    metrics_map = {
        "h3_robust_Fz_op_pN": h3["benchmark_1_axial_stroke"]["F_z_op_pN"],
        "h3_robust_Fz_engaged_pN": h3["benchmark_2_angular_lateral"]["F_z_engaged_48deg_pN"],
        "h3_robust_stroke_span_nm": h3["benchmark_1_axial_stroke"]["sign_safe_span_nm"],
        "h3_robust_stroke_basin_Bz": h3["benchmark_1_axial_stroke"]["log_stroke_basin_Bz"],
        "h3_robust_min_stroke_Fz_pN": h3["benchmark_1_axial_stroke"]["min_Fz_working_window_45_360nm_pN"],
        "h3_robust_escape_work_kBT": h3["benchmark_1_axial_stroke"]["escape_work_kBT_300K"],
        "h3_robust_torque_ripple": h3["benchmark_2_angular_lateral"]["torque_ripple_R_tau"],
        "h3_robust_SF_rib": h3["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["SF_rib"],
        "h3_robust_V_crit_mV": h3["benchmark_3_rib_and_vcrit"]["laplace_electrostatics"]["V_crit_mV"],
        "h3_robust_yield_pct": h3["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
        "ctrl_knife_Fz_op_pN": ke["benchmark_1_axial_stroke"]["F_z_op_pN"],
        "ctrl_knife_SF_rib": ke["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["SF_rib"],
        "ctrl_knife_V_crit_mV": ke["benchmark_3_rib_and_vcrit"]["laplace_electrostatics"]["V_crit_mV"],
        "ctrl_knife_yield_pct": ke["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
        "h3_pec_dlnk_21": sp_pec["spacing_comparison"]["delta_ln_kappa_21"],
        "h3_pec_dlnk_32": sp_pec["spacing_comparison"]["delta_ln_kappa_32"],
        "h3_gold_dlnk_21": sp_gold["spacing_comparison"]["delta_ln_kappa_21"],
        "h3_gold_dlnk_32": sp_gold["spacing_comparison"]["delta_ln_kappa_32"],
    }
    for key, val in metrics_map.items():
        log_metric(key, float(val), step_id=step_id, defer_save=True)
    export_macros()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Micro-probe mode when >0: execute exact full-physics BEM on first N queued tasks and exit.",
    )
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--n-xi", type=int, default=20, help="Gauss-Legendre imaginary-frequency tail order.")
    parser.add_argument(
        "--n-mc", type=int, default=2000, help="Number of cleanroom Monte Carlo chip realizations per design."
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=REPOSITORY_ROOT / ".tmp" / "unified_robustness_ckpt",
        help="Directory for per-task JSON checkpoints.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Output JSON path (defaults to results/unified_fractal_robustness_study.json for full run).",
    )
    parser.add_argument("--no-cache-ckpt", action="store_true", help="Ignore existing task checkpoints.")
    parser.add_argument(
        "--skip-blender",
        action="store_true",
        help="Skip automatic 3D Blender atlas/hero rendering & visual inspection upon full run completion.",
    )
    args = parser.parse_args(argv)
    if args.max_steps < 0:
        parser.error("--max-steps must be >= 0.")
    if args.n_xi <= 0:
        parser.error("--n-xi must be > 0.")
    if args.n_mc <= 0:
        parser.error("--n-mc must be > 0.")

    t_start = time.perf_counter()
    designs = build_all_robustness_study_designs()
    by_code = {d.code: d for d in designs}
    code_hash = _compute_combined_code_hash()

    # Pre-flight geometric & 3D collision verification across stroke and rotational switching
    collision_audit: dict[str, Any] = {}
    for des in designs:
        chk_dis = verify_design_3d_non_intersection(
            des, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM, theta_deg=DISENGAGED_THETA_DEG
        )
        chk_deep = verify_design_3d_non_intersection(des, z_shift_um=0.520, theta_deg=DISENGAGED_THETA_DEG)
        chk_eng = verify_design_3d_non_intersection(
            des, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM, theta_deg=ENGAGED_THETA_DEG
        )
        if not (chk_dis["collision_free"] and chk_deep["collision_free"] and chk_eng["collision_free"]):
            raise RuntimeError(
                f"3D solid intersection detected in {des.code}: dis={chk_dis['collisions']}, "
                f"deep={chk_deep['collisions']}, eng={chk_eng['collisions']}"
            )
        collision_audit[des.code] = {
            "disengaged_3deg_zop": chk_dis["collision_free"],
            "deep_stroke_520nm_3deg": chk_deep["collision_free"],
            "engaged_48deg_zop": chk_eng["collision_free"],
        }

    all_tasks = _build_bem_task_list(designs)

    # Micro-probe mode (`--max-steps > 0`) for hpc-workload-gate empirical profiling
    if args.max_steps > 0:
        clear_bem_lu_caches()
        n_run = min(int(args.max_steps), len(all_tasks))
        # Representative cold-LU (~30%) + cached-sweep (~70%) task mix matching the 487-task queue across 7-trk & 19-trk designs
        n_stroke_per_design = len(STROKE_Z_GRID_UM)
        if n_run == 5 and len(all_tasks) >= 2 * n_stroke_per_design:
            probe_tasks = [
                all_tasks[0],                      # H3_Cantor_Robust (7-trk, cold LU)
                all_tasks[1],                      # H3_Cantor_Robust (7-trk, cached LU)
                all_tasks[2],                      # H3_Cantor_Robust (7-trk, cached LU)
                all_tasks[n_stroke_per_design],    # Ctrl_KnifeEdge_g27 (19-trk, cold LU)
                all_tasks[n_stroke_per_design + 1],  # Ctrl_KnifeEdge_g27 (19-trk, cached LU)
            ]
        else:
            probe_tasks = all_tasks[:n_run]
        probe_records = []
        for idx, tsk in enumerate(probe_tasks):
            rec = _execute_single_task(tsk, by_code, n_xi=args.n_xi, device=args.device)
            probe_records.append(
                {
                    "probe_step": idx + 1,
                    "task_key": tsk["task_key"],
                    "design_code": tsk["design_code"],
                    "F_z_pN": rec["F_z_pN"],
                    "elapsed_s": rec["elapsed_s"],
                }
            )
        elapsed_tot = time.perf_counter() - t_start
        out_probe = args.output_json if args.output_json is not None else DEFAULT_PROBE_JSON
        out_probe.parent.mkdir(parents=True, exist_ok=True)
        probe_payload = {
            "model": "BEM_vector_dyadic_Gold_300K_probe",
            "dataset": "h3_cantor_robust_vs_5_matched_controls",
            "status": "probe_completed",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "code_hash": code_hash,
            "max_steps": n_run,
            "total_planned_tasks": len(all_tasks),
            "elapsed_s": float(elapsed_tot),
            "sec_per_step": float(elapsed_tot / max(n_run, 1)),
            "records": probe_records,
        }
        out_probe.write_text(json.dumps(probe_payload, indent=2), encoding="utf-8")
        print(json.dumps({"event": "micro_probe_done", "steps": n_run, "total_planned": len(all_tasks), "elapsed_s": round(elapsed_tot, 4)}))
        return 0

    # Full production benchmark execution
    out_json = args.output_json if args.output_json is not None else DEFAULT_OUTPUT_JSON
    ckpt_dir = args.checkpoint_dir / f"hash_{code_hash}_nxi{args.n_xi}"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    task_results: dict[str, dict[str, Any]] = {}
    n_total = len(all_tasks)
    print(f"[UNIFIED-ROBUSTNESS] Executing {n_total} grounded 3D BEM tasks (n_xi={args.n_xi}, code_hash={code_hash})...")

    for idx, tsk in enumerate(all_tasks, start=1):
        t_key = str(tsk["task_key"])
        ckpt_file = ckpt_dir / f"{t_key}.json"
        if not args.no_cache_ckpt and ckpt_file.is_file():
            task_results[t_key] = json.loads(ckpt_file.read_text(encoding="utf-8"))
        else:
            res = _execute_single_task(tsk, by_code, n_xi=args.n_xi, device=args.device)
            task_results[t_key] = res
            ckpt_file.write_text(json.dumps(res), encoding="utf-8")
        if idx % 50 == 0 or idx == n_total:
            el = time.perf_counter() - t_start
            print(f"  [{idx:3d}/{n_total}] elapsed={el:.1f}s | last={t_key} -> F_z={task_results[t_key]['F_z_pN']:+.3f} pN")

    # Assemble per-design 4-pillar benchmark analyses
    designs_summary: dict[str, Any] = {}
    for des in designs:
        geom_desc = compute_design_geometric_summary(des)
        stroke_fz = [
            float(task_results[f"B1_stroke_{des.code}_z{z_um:.6f}"]["F_z_pN"])
            for z_um in STROKE_Z_GRID_UM
        ]
        stroke_ej = [
            float(task_results[f"B1_stroke_{des.code}_z{z_um:.6f}"]["energy_J"])
            for z_um in STROKE_Z_GRID_UM
        ]
        b1_res = _analyze_axial_stroke_curve(STROKE_Z_GRID_UM, stroke_fz, stroke_ej)
        b2_res = _analyze_angular_and_radial(des, task_results)

        rib_res = compute_stator_rib_elastostatic_safety(
            des,
            track_radial_stiffness_N_per_m=b2_res["track_radial_stiffness_N_per_m"],
            v_patch_rms_mv=20.0,
            overlay_eccentricity_nm=5.0,
        )
        cap_res = evaluate_laplace_capacitance_and_vcrit(
            des,
            f_z_nominal_pN=b1_res["F_z_op_pN"],
            z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM,
            theta_deg=DISENGAGED_THETA_DEG,
        )
        b3_res = {
            "rib_elastostatics": rib_res,
            "laplace_electrostatics": cap_res,
        }
        b4_res = _analyze_cleanroom_yield_and_defects(
            des,
            task_results,
            STROKE_Z_GRID_UM,
            stroke_fz,
            b2_res["track_radial_stiffness_N_per_m"],
            abs_dC_dz_F_per_m=cap_res["abs_dC_dz_nF_per_m"] * 1.0e-9,
            n_mc=args.n_mc,
        )
        designs_summary[des.code] = {
            "name": des.name,
            "code": des.code,
            "family_role": des.family_role,
            "description": des.description,
            "design_fingerprint": compute_design_fingerprint(des),
            "geometry_descriptors": geom_desc,
            "collision_audit": collision_audit[des.code],
            "benchmark_1_axial_stroke": b1_res,
            "benchmark_2_angular_lateral": b2_res,
            "benchmark_3_rib_and_vcrit": b3_res,
            "benchmark_4_cleanroom_yield": b4_res,
        }

    b5_res = _analyze_spectral_and_ln3_scaling(task_results)

    # Ranking & head-to-head comparison summary
    rankings = {
        "by_cleanroom_yield_Y_lab_pct": sorted(
            ((c, designs_summary[c]["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"]) for c in designs_summary),
            key=lambda kv: kv[1],
            reverse=True,
        ),
        "by_log_stroke_basin_Bz": sorted(
            ((c, designs_summary[c]["benchmark_1_axial_stroke"]["log_stroke_basin_Bz"]) for c in designs_summary),
            key=lambda kv: kv[1],
            reverse=True,
        ),
        "by_lowest_torque_ripple_R_tau": sorted(
            ((c, designs_summary[c]["benchmark_2_angular_lateral"]["torque_ripple_R_tau"]) for c in designs_summary),
            key=lambda kv: kv[1],
        ),
        "by_stator_rib_safety_SF_rib": sorted(
            ((c, designs_summary[c]["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["SF_rib"]) for c in designs_summary),
            key=lambda kv: kv[1],
            reverse=True,
        ),
        "by_single_point_nominal_Fz_pN": sorted(
            ((c, designs_summary[c]["benchmark_1_axial_stroke"]["F_z_op_pN"]) for c in designs_summary),
            key=lambda kv: kv[1],
            reverse=True,
        ),
    }

    solver_params = {
        "formulation": "vector_dyadic",
        "symmetry": "C4_Bloch_4_sectors",
        "material_primary": "Gold_Drude_Lorentz_300K",
        "material_reference": "PEC_0K",
        "n_xi_tail": int(args.n_xi),
        "fem_beam_elements": 32,
        "fem_element_type": "Hermite_cubic_Euler_Bernoulli_clamped_clamped",
        "monte_carlo_samples_per_design": int(args.n_mc),
        "code_hash": code_hash,
    }

    executed_iso = datetime.now(timezone.utc).isoformat()
    full_summary: dict[str, Any] = {
        "model": "BEM_vector_dyadic_3D_Gold300K_and_Hermite_FEM",
        "dataset": "h3_cantor_robust_unified_5pillar_benchmark",
        "status": "completed",
        "executed_at": executed_iso,
        "code_hash": code_hash,
        "elapsed_total_s": float(time.perf_counter() - t_start),
        "total_bem_tasks_evaluated": n_total,
        "solver_parameters": solver_params,
        "rankings": rankings,
        "designs": designs_summary,
        "benchmark_5_ln3_scale_covering": b5_res,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(full_summary, indent=2), encoding="utf-8")

    # Only update global manuscript/provenance artifacts on full default/production runs
    if out_json.resolve() == DEFAULT_OUTPUT_JSON.resolve():
        from execution.build_unified_fractal_robustness_blender import (
            find_blender_executable,
            inspect_rendered_png_quality,
            main as build_blender_main,
        )

        _log_grounded_provenance_metrics(full_summary, solver_params)
        _render_summary_figure(full_summary, DEFAULT_FIGURE_PDF, DEFAULT_FIGURE_PNG, code_hash)
        summary_fig_audit = inspect_rendered_png_quality(
            DEFAULT_FIGURE_PNG, min_fg_fraction=0.04, max_fg_fraction=0.96
        )
        if summary_fig_audit["status"] != "PASS":
            raise RuntimeError(f"Summary benchmark figure visual inspection failed: {summary_fig_audit}")
        _write_latex_summary_table(full_summary, DEFAULT_LATEX_TABLE)
        print(f"[UNIFIED-ROBUSTNESS] Saved summary JSON -> {out_json}")
        print(f"[UNIFIED-ROBUSTNESS] Saved figure       -> {DEFAULT_FIGURE_PDF}")
        print(f"[UNIFIED-ROBUSTNESS] Saved LaTeX table  -> {DEFAULT_LATEX_TABLE}")

        if not args.skip_blender:
            blender_render_dir = REPOSITORY_ROOT / "results" / "unified_fractal_robustness_blender"
            has_cached_renders = blender_render_dir.is_dir() and len(list(blender_render_dir.glob("render_*.png"))) >= 10
            if find_blender_executable() is not None or has_cached_renders:
                build_blender_main(["--reuse-renders"])
                print("[UNIFIED-ROBUSTNESS] Built & visually verified 3D Blender atlas and hero figures.")
            else:
                print(
                    "[UNIFIED-ROBUSTNESS] Blender executable not found and no cached renders present; "
                    "skipping 3D Blender render on headless compute node."
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
