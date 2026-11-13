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
    build_h3_mechanistic_ablation_designs,
    build_homothetic_sector_bem_mesh,
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
    _sanitize_macro_name,
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
DEFAULT_ABLATION_FIG_PDF = REPOSITORY_ROOT / "figures" / "fig_h3_mechanistic_ablations.pdf"
DEFAULT_ABLATION_FIG_PNG = REPOSITORY_ROOT / "figures" / "fig_h3_mechanistic_ablations.png"
DEFAULT_LATEX_TABLE = (
    REPOSITORY_ROOT / "Papers" / "FCE_Nature_ver01" / "tables" / "table_unified_fractal_robustness.tex"
)
DEFAULT_ABLATION_LATEX_TABLE = (
    REPOSITORY_ROOT / "Papers" / "FCE_Nature_ver01" / "tables" / "table_h3_mechanistic_ablations.tex"
)
MANUSCRIPT_MACROS_PATH = REPOSITORY_ROOT / "Papers" / "FCE_Nature_ver01" / "macros_results.tex"

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


def _build_bem_task_list(
    designs: Sequence[RobustClutchDesign3D],
    ablation_designs: Sequence[RobustClutchDesign3D] = (),
) -> list[dict[str, Any]]:
    """Construct the deterministic ordered list of all 3D BEM evaluations across Benchmarks 1-6."""
    by_code = {d.code: d for d in (*designs, *ablation_designs)}
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
        ("H3_Cantor_Sym_2x2x2", "PEC", 0.0),
        ("H3_Cantor_Sym_2x2x2", "Gold", 300.0),
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

    # 8. Benchmark 5B: 36-point ideal PEC (0 K) stroke sweep on Cantor architectures
    for pec_code in ("H3_Cantor_Robust", "H3_Cantor_Sym_2x2x2"):
        if pec_code not in by_code:
            continue
        for z_um in STROKE_Z_GRID_UM:
            tasks.append(
                {
                    "task_key": f"B5_pec_stroke_{pec_code}_z{z_um:.6f}",
                    "benchmark": "B5_pec_stroke",
                    "design_code": pec_code,
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

    # 9. Benchmark 5C: 3-tier balanced mesh-refinement ladder (n_phi_collar scaled proportionally!)
    mesh_ladder_specs = [
        ("B5_mesh_tier1_H3_Cantor_Sym", "H3_Cantor_Sym_2x2x2", DISENGAGED_THETA_DEG, (1, 1, 1, 3), 0),
        ("B5_mesh_tier3_H3_Cantor_Sym", "H3_Cantor_Sym_2x2x2", DISENGAGED_THETA_DEG, (3, 3, 3, 14), 6),
        ("B5_mesh_tier1_eng_H3_Cantor_Sym", "H3_Cantor_Sym_2x2x2", ENGAGED_THETA_DEG, (1, 1, 1, 3), 0),
        ("B5_mesh_tier3_eng_H3_Cantor_Sym", "H3_Cantor_Sym_2x2x2", ENGAGED_THETA_DEG, (3, 3, 3, 14), 6),
        ("B5_mesh_tier1_H3_Cantor_Robust", "H3_Cantor_Robust", DISENGAGED_THETA_DEG, (1, 1, 1, 3), 0),
    ]
    for t_key, d_code, th_deg, mesh_ov, extra_xi in mesh_ladder_specs:
        if d_code in by_code:
            tasks.append(
                {
                    "task_key": t_key,
                    "benchmark": "B5_mesh_convergence",
                    "design_code": d_code,
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": th_deg,
                    "delta_w_um": 0.0,
                    "delta_r_um": 0.0,
                    "r_edge_um": 0.0,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "spectral_91": False,
                    "refined_mesh": extra_xi > 0,
                    "mesh_override": list(mesh_ov),
                    "extra_n_xi": int(extra_xi),
                }
            )

    # 10. Benchmark 6: Mechanistic Ablations (2^3 orthogonal factorial + N=1,2,3 depth + micro-bridge isolation)
    for abl in ablation_designs:
        for suffix, th_deg, dr_nm in (
            ("dis3deg", DISENGAGED_THETA_DEG, 0.0),
            ("eng48deg", ENGAGED_THETA_DEG, 0.0),
            ("th2.5deg", 2.5, 0.0),
            ("th3.5deg", 3.5, 0.0),
            ("dr-8.0nm", DISENGAGED_THETA_DEG, -8.0),
            ("dr+8.0nm", DISENGAGED_THETA_DEG, +8.0),
        ):
            tasks.append(
                {
                    "task_key": f"B6_abl_{abl.code}_{suffix}",
                    "benchmark": "B6_mechanistic_ablations",
                    "design_code": abl.code,
                    "z_shift_um": H3_ROBUST_NOMINAL_OP_Z_UM,
                    "theta_deg": th_deg,
                    "delta_w_um": 0.0,
                    "delta_r_um": dr_nm * 1.0e-3,
                    "r_edge_um": 0.0,
                    "material": "Gold",
                    "temperature_K": 300.0,
                    "spectral_91": False,
                    "refined_mesh": False,
                }
            )
    return tasks


VERIFIED_V1_6DESIGN_CODE_HASH = "9c65828d1361e664"
VERIFIED_V2_SYM_CODE_HASH = "df6a5fee001a9823"


def _resolve_task_mesh_override(task: Mapping[str, Any]) -> tuple[int | None, int | None, int | None, int | None]:
    raw_ov = task.get("mesh_override")
    if isinstance(raw_ov, (list, tuple)) and len(raw_ov) == 4:
        return (int(raw_ov[0]), int(raw_ov[1]), int(raw_ov[2]), int(raw_ov[3]))
    if bool(task.get("refined_mesh", False)):
        return (2, 2, 2, 9)
    return (None, None, None, None)


def _checkpoint_matches_task(
    cached: Mapping[str, Any],
    task: Mapping[str, Any],
    *,
    by_code: Mapping[str, RobustClutchDesign3D] | None = None,
) -> bool:
    """Verify a cached BEM task record matches all task physical & mesh panel counts before reuse."""
    try:
        d_code = str(task["design_code"])
        if str(cached.get("design_code")) != d_code:
            return False
        if str(cached.get("material")) != str(task["material"]):
            return False
        for key in ("z_shift_um", "theta_deg", "delta_w_um", "delta_r_um", "r_edge_um", "temperature_K"):
            if not math.isclose(float(cached[key]), float(task[key]), rel_tol=1e-9, abs_tol=1e-12):
                return False
        if not bool(cached.get("shorted", False)) and not bool(cached.get("all_teeth_etched_away", False)):
            if bool(task.get("spectral_91", False)) and len(cached.get("kappas_um_inv", ())) != len(SPECTRAL_KAPPA_GRID_UM_INV):
                return False
            if by_code is not None and d_code in by_code:
                des = by_code[d_code]
                nr_ov, nphi_ov, nz_ov, ncol_ov = _resolve_task_mesh_override(task)
                built = build_homothetic_sector_bem_mesh(
                    des,
                    z_shift_um=float(task["z_shift_um"]),
                    theta_deg=float(task["theta_deg"]),
                    delta_w_um=float(task["delta_w_um"]),
                    delta_r_um=float(task["delta_r_um"]),
                    r_edge_um=float(task["r_edge_um"]),
                    n_r_lobe=nr_ov,
                    n_phi_lobe=nphi_ov,
                    n_z_lobe=nz_ov,
                    n_phi_collar=ncol_ov,
                )
                if built.mesh is not None:
                    if int(cached.get("n_rotor_panels_sector", -1)) != built.mesh.sector_arrays("rotor").count:
                        return False
                    if int(cached.get("n_stator_panels_sector", -1)) != built.mesh.sector_arrays("stator").count:
                        return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _execute_single_task(
    task: Mapping[str, Any],
    by_code: Mapping[str, RobustClutchDesign3D],
    *,
    n_xi: int,
    device: Literal["auto", "cpu", "cuda"],
) -> dict[str, Any]:
    des = by_code[str(task["design_code"])]
    is_spec = bool(task.get("spectral_91", False))
    extra_xi = int(task.get("extra_n_xi", 6 if task.get("refined_mesh", False) else 0))
    nr_ov, nphi_ov, nz_ov, ncol_ov = _resolve_task_mesh_override(task)
    has_explicit_ov = task.get("mesh_override") is not None or bool(task.get("refined_mesh", False))
    return evaluate_homothetic_3d_bem(
        des,
        z_shift_um=float(task["z_shift_um"]),
        theta_deg=float(task["theta_deg"]),
        delta_w_um=float(task["delta_w_um"]),
        delta_r_um=float(task["delta_r_um"]),
        r_edge_um=float(task["r_edge_um"]),
        material=str(task["material"]),
        temperature_K=float(task["temperature_K"]),
        n_xi=n_xi + extra_xi,
        kappas_override=SPECTRAL_KAPPA_GRID_UM_INV if is_spec else None,
        device=device,
        use_lu_cache=not has_explicit_ov,
        n_r_lobe=nr_ov,
        n_phi_lobe=nphi_ov,
        n_z_lobe=nz_ov,
        n_phi_collar=ncol_ov,
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
        ("H3_Cantor_Sym_2x2x2_PEC", "B5_spec91_H3_Cantor_Sym_2x2x2_PEC"),
        ("H3_Cantor_Sym_2x2x2_Gold300K", "B5_spec91_H3_Cantor_Sym_2x2x2_Gold"),
        ("Ctrl_Lin_3Stage_PEC", "B5_spec91_Ctrl_Lin_3Stage_PEC"),
        ("Ctrl_Lin_3Stage_Gold300K", "B5_spec91_Ctrl_Lin_3Stage_Gold"),
    ):
        if task_key not in task_results:
            continue
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
        ("H3_Cantor_Sym_2x2x2_PEC", "B5_pec_stroke_H3_Cantor_Sym_2x2x2"),
        ("H3_Cantor_Sym_2x2x2_Gold300K", "B1_stroke_H3_Cantor_Sym_2x2x2"),
        ("Ctrl_Lin_3Stage_Gold300K", "B1_stroke_Ctrl_Lin_3Stage"),
        ("Ctrl_KnifeEdge_g27_Gold300K", "B1_stroke_Ctrl_KnifeEdge_g27"),
    ):
        first_key = f"{prefix}_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"
        if first_key not in task_results:
            continue
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

    # 3-tier balanced mesh convergence ladder (1x1x1 col=3 -> 2x2x2 col=9 -> 3x3x3 col=14)
    f_sym_t1 = float(task_results["B5_mesh_tier1_H3_Cantor_Sym"]["F_z_pN"])
    f_sym_t2 = float(task_results[f"B1_stroke_H3_Cantor_Sym_2x2x2_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"]["F_z_pN"])
    f_sym_t3 = float(task_results["B5_mesh_tier3_H3_Cantor_Sym"]["F_z_pN"])
    f_sym_rich = (9.0 * f_sym_t3 - 4.0 * f_sym_t2) / 5.0

    f_eng_t1 = float(task_results["B5_mesh_tier1_eng_H3_Cantor_Sym"]["F_z_pN"])
    f_eng_t2 = float(task_results[f"B2_theta_H3_Cantor_Sym_2x2x2_th{ENGAGED_THETA_DEG:.3f}"]["F_z_pN"])
    f_eng_t3 = float(task_results["B5_mesh_tier3_eng_H3_Cantor_Sym"]["F_z_pN"])
    f_eng_rich = (9.0 * f_eng_t3 - 4.0 * f_eng_t2) / 5.0

    f_rob_t1 = float(task_results["B5_mesh_tier1_H3_Cantor_Robust"]["F_z_pN"])
    f_rob_t2 = float(task_results[f"B1_stroke_H3_Cantor_Robust_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"]["F_z_pN"])
    rel_diff_t2_t3_pct = 100.0 * abs(f_sym_t3 - f_sym_t2) / max(abs(f_sym_t3), 1e-9)
    rel_diff_t3_rich_pct = 100.0 * abs(f_sym_rich - f_sym_t3) / max(abs(f_sym_rich), 1e-9)

    return {
        "wavenumber_subbands": spectral_out,
        "stroke_log_periodicity": stroke_lomb_out,
        "mesh_convergence": {
            "F_z_sym_tier1_1x1x1_pN": f_sym_t1,
            "F_z_sym_tier2_2x2x2_pN": f_sym_t2,
            "F_z_sym_tier3_3x3x3_pN": f_sym_t3,
            "F_z_sym_richardson_pN": f_sym_rich,
            "F_z_sym_eng_tier1_pN": f_eng_t1,
            "F_z_sym_eng_tier2_pN": f_eng_t2,
            "F_z_sym_eng_tier3_pN": f_eng_t3,
            "F_z_sym_eng_richardson_pN": f_eng_rich,
            "F_z_rob_tier1_1x1x1_pN": f_rob_t1,
            "F_z_rob_tier2_2x2x2_pN": f_rob_t2,
            "F_z_standard_mesh_pN": f_sym_t2,
            "F_z_refined_2x2x2_mesh_pN": f_sym_t3,
            "relative_difference_pct": float(rel_diff_t2_t3_pct),
            "tier3_vs_richardson_pct": float(rel_diff_t3_rich_pct),
            "tier2_rotor_panels_sector": int(
                task_results[f"B1_stroke_H3_Cantor_Sym_2x2x2_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"]["n_rotor_panels_sector"]
            ),
            "tier2_stator_panels_sector": int(
                task_results[f"B1_stroke_H3_Cantor_Sym_2x2x2_z{H3_ROBUST_NOMINAL_OP_Z_UM:.6f}"]["n_stator_panels_sector"]
            ),
            "refined_rotor_panels_sector": int(
                task_results["B5_mesh_tier3_H3_Cantor_Sym"]["n_rotor_panels_sector"]
            ),
            "refined_stator_panels_sector": int(
                task_results["B5_mesh_tier3_H3_Cantor_Sym"]["n_stator_panels_sector"]
            ),
        },
    }


def _analyze_mechanistic_ablations(
    ablation_designs: Sequence[RobustClutchDesign3D],
    designs_summary: Mapping[str, Any],
    task_results: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate 2^3 (r, theta, z) factorial contrasts, N=1..3 depth ladder, and bridge/Vernier ablations."""
    abl_records: dict[str, dict[str, Any]] = {}
    for abl in ablation_designs:
        rec_dis = task_results[f"B6_abl_{abl.code}_dis3deg"]
        rec_eng = task_results[f"B6_abl_{abl.code}_eng48deg"]
        rec_th_m = task_results[f"B6_abl_{abl.code}_th2.5deg"]
        rec_th_p = task_results[f"B6_abl_{abl.code}_th3.5deg"]
        rec_dr_m = task_results[f"B6_abl_{abl.code}_dr-8.0nm"]
        rec_dr_p = task_results[f"B6_abl_{abl.code}_dr+8.0nm"]

        e0 = float(rec_dis["energy_J"])
        dth_rad = math.radians(0.5)
        d2E_dth2_Jm = (float(rec_th_p["energy_J"]) - 2.0 * e0 + float(rec_th_m["energy_J"])) / (dth_rad**2)
        tau_3deg_pN_um = -(float(rec_th_p["energy_J"]) - float(rec_th_m["energy_J"])) / (2.0 * dth_rad) * 1.0e18

        dr8_m = 8.0e-9
        d2E_dr2_N_per_m = (float(rec_dr_p["energy_J"]) - 2.0 * e0 + float(rec_dr_m["energy_J"])) / (dr8_m**2)
        r_mean_um = 0.5 * (abl.R_min_um + abl.R_max_um)
        k_cas_lat = max(0.0, -0.5 * d2E_dr2_N_per_m - 0.5 * d2E_dth2_Jm / ((r_mean_um * 1.0e-6) ** 2))

        etrk_m = np.asarray(rec_dr_m["e_tracks_approx_J"], dtype=np.float64)
        etrk_0 = np.asarray(rec_dis["e_tracks_approx_J"], dtype=np.float64)
        etrk_p = np.asarray(rec_dr_p["e_tracks_approx_J"], dtype=np.float64)
        k_tracks = [
            float(max(0.0, -(ep - 2.0 * ec + em) / (dr8_m**2)))
            for em, ec, ep in zip(etrk_m, etrk_0, etrk_p)
        ]
        rib_res = compute_stator_rib_elastostatic_safety(
            abl,
            track_radial_stiffness_N_per_m=k_tracks,
            v_patch_rms_mv=20.0,
            overlay_eccentricity_nm=5.0,
        )
        f_dis = float(rec_dis["F_z_pN"])
        f_eng = float(rec_eng["F_z_pN"])
        cap_res = evaluate_laplace_capacitance_and_vcrit(
            abl,
            f_z_nominal_pN=f_dis,
            z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM,
            theta_deg=DISENGAGED_THETA_DEG,
        )
        abl_records[abl.code] = {
            "code": abl.code,
            "name": abl.name,
            "family_role": abl.family_role,
            "description": abl.description,
            "n_tracks": len(abl.tracks),
            "A_tooth_um2": float(active_tooth_area_um2(abl)),
            "n_rotor_panels_sector": int(rec_dis["n_rotor_panels_sector"]),
            "n_stator_panels_sector": int(rec_dis["n_stator_panels_sector"]),
            "F_z_disengaged_3deg_pN": f_dis,
            "F_z_engaged_48deg_pN": f_eng,
            "switching_force_swing_pN": float(f_dis - f_eng),
            "reversible_sign_switch": bool(f_dis > 0.0 and f_eng < 0.0),
            "local_torque_3deg_pN_um": float(abs(tau_3deg_pN_um)),
            "K_cas_lateral_mN_per_m": float(k_cas_lat * 1.0e3),
            "SF_rib": float(rib_res["SF_rib"]),
            "max_rib_deflection_nm": float(rib_res["max_rib_deflection_nm"]),
            "V_crit_mV": float(cap_res["V_crit_mV"]),
        }

    sym = designs_summary["H3_Cantor_Sym_2x2x2"]
    rob = designs_summary["H3_Cantor_Robust"]
    f111_entry = {
        "code": "H3_Cantor_Sym_2x2x2",
        "name": sym["name"],
        "bits": "111",
        "I_r": 1,
        "I_theta": 1,
        "I_z": 1,
        "F_z_disengaged_3deg_pN": float(sym["benchmark_1_axial_stroke"]["F_z_op_pN"]),
        "F_z_engaged_48deg_pN": float(sym["benchmark_2_angular_lateral"]["F_z_engaged_48deg_pN"]),
        "switching_force_swing_pN": float(sym["benchmark_2_angular_lateral"]["switching_force_swing_pN"]),
        "SF_rib": float(sym["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["SF_rib"]),
        "V_crit_mV": float(sym["benchmark_3_rib_and_vcrit"]["laplace_electrostatics"]["V_crit_mV"]),
    }

    cells_by_bits: dict[str, dict[str, Any]] = {"111": f111_entry}
    for bits in ("000", "001", "010", "011", "100", "101", "110"):
        rec = abl_records[f"Abl_F{bits}"]
        cells_by_bits[bits] = {
            "code": rec["code"],
            "name": rec["name"],
            "bits": bits,
            "I_r": int(bits[0]),
            "I_theta": int(bits[1]),
            "I_z": int(bits[2]),
            "F_z_disengaged_3deg_pN": rec["F_z_disengaged_3deg_pN"],
            "F_z_engaged_48deg_pN": rec["F_z_engaged_48deg_pN"],
            "switching_force_swing_pN": rec["switching_force_swing_pN"],
            "SF_rib": rec["SF_rib"],
            "V_crit_mV": rec["V_crit_mV"],
        }

    def _yates_effects(metric_key: str) -> dict[str, float]:
        y = {(int(b[0]), int(b[1]), int(b[2])): float(cells_by_bits[b][metric_key]) for b in cells_by_bits}
        d_r = 0.25 * sum(y[(1, j, k)] - y[(0, j, k)] for j in (0, 1) for k in (0, 1))
        d_th = 0.25 * sum(y[(i, 1, k)] - y[(i, 0, k)] for i in (0, 1) for k in (0, 1))
        d_z = 0.25 * sum(y[(i, j, 1)] - y[(i, j, 0)] for i in (0, 1) for j in (0, 1))
        i_rth = 0.25 * sum((y[(1, 1, k)] - y[(0, 1, k)]) - (y[(1, 0, k)] - y[(0, 0, k)]) for k in (0, 1))
        i_rz = 0.25 * sum((y[(1, j, 1)] - y[(0, j, 1)]) - (y[(1, j, 0)] - y[(0, j, 0)]) for j in (0, 1))
        i_thz = 0.25 * sum((y[(i, 1, 1)] - y[(i, 0, 1)]) - (y[(i, 1, 0)] - y[(i, 0, 0)]) for i in (0, 1))
        i_rthz = 0.25 * (
            ((y[(1, 1, 1)] - y[(0, 1, 1)]) - (y[(1, 0, 1)] - y[(0, 0, 1)]))
            - ((y[(1, 1, 0)] - y[(0, 1, 0)]) - (y[(1, 0, 0)] - y[(0, 0, 0)]))
        )
        return {
            "baseline_000": y[(0, 0, 0)],
            "full_111": y[(1, 1, 1)],
            "net_gain_111_minus_000": y[(1, 1, 1)] - y[(0, 0, 0)],
            "main_effect_r": d_r,
            "main_effect_theta": d_th,
            "main_effect_z": d_z,
            "interaction_r_theta": i_rth,
            "interaction_r_z": i_rz,
            "interaction_theta_z": i_thz,
            "synergy_3way_r_theta_z": i_rthz,
        }

    depth_ladder = [
        {
            "N_depth": 1,
            "code": "Abl_Depth_N1",
            "n_tracks": abl_records["Abl_Depth_N1"]["n_tracks"],
            "F_z_disengaged_3deg_pN": abl_records["Abl_Depth_N1"]["F_z_disengaged_3deg_pN"],
            "F_z_engaged_48deg_pN": abl_records["Abl_Depth_N1"]["F_z_engaged_48deg_pN"],
            "switching_force_swing_pN": abl_records["Abl_Depth_N1"]["switching_force_swing_pN"],
            "SF_rib": abl_records["Abl_Depth_N1"]["SF_rib"],
            "V_crit_mV": abl_records["Abl_Depth_N1"]["V_crit_mV"],
        },
        {
            "N_depth": 2,
            "code": "Abl_Depth_N2",
            "n_tracks": abl_records["Abl_Depth_N2"]["n_tracks"],
            "F_z_disengaged_3deg_pN": abl_records["Abl_Depth_N2"]["F_z_disengaged_3deg_pN"],
            "F_z_engaged_48deg_pN": abl_records["Abl_Depth_N2"]["F_z_engaged_48deg_pN"],
            "switching_force_swing_pN": abl_records["Abl_Depth_N2"]["switching_force_swing_pN"],
            "SF_rib": abl_records["Abl_Depth_N2"]["SF_rib"],
            "V_crit_mV": abl_records["Abl_Depth_N2"]["V_crit_mV"],
        },
        {
            "N_depth": 3,
            "code": "H3_Cantor_Sym_2x2x2",
            "n_tracks": 7,
            "F_z_disengaged_3deg_pN": f111_entry["F_z_disengaged_3deg_pN"],
            "F_z_engaged_48deg_pN": f111_entry["F_z_engaged_48deg_pN"],
            "switching_force_swing_pN": f111_entry["switching_force_swing_pN"],
            "SF_rib": f111_entry["SF_rib"],
            "V_crit_mV": f111_entry["V_crit_mV"],
        },
    ]

    no_br = abl_records["Abl_NoBridges"]
    sym_defl = float(sym["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["max_rib_deflection_nm"])
    bridge_isolation = {
        "bridged_code": "H3_Cantor_Sym_2x2x2",
        "unbridged_code": "Abl_NoBridges",
        "bridged_Fz_3deg_pN": f111_entry["F_z_disengaged_3deg_pN"],
        "unbridged_Fz_3deg_pN": no_br["F_z_disengaged_3deg_pN"],
        "bridged_SF_rib": f111_entry["SF_rib"],
        "unbridged_SF_rib": no_br["SF_rib"],
        "SF_rib_gain_ratio": f111_entry["SF_rib"] / max(no_br["SF_rib"], 1e-9),
        "bridged_max_deflection_nm": sym_defl,
        "unbridged_max_deflection_nm": no_br["max_rib_deflection_nm"],
    }

    vernier_isolation = {
        "in_phase_code": "H3_Cantor_Sym_2x2x2",
        "vernier_code": "H3_Cantor_Robust",
        "in_phase_Fz_3deg_pN": f111_entry["F_z_disengaged_3deg_pN"],
        "vernier_Fz_3deg_pN": float(rob["benchmark_1_axial_stroke"]["F_z_op_pN"]),
        "in_phase_R_tau": float(sym["benchmark_2_angular_lateral"]["torque_ripple_R_tau"]),
        "vernier_R_tau": float(rob["benchmark_2_angular_lateral"]["torque_ripple_R_tau"]),
        "in_phase_Y_lab_pct": float(sym["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"]),
        "vernier_Y_lab_pct": float(rob["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"]),
    }

    return {
        "ablation_designs": abl_records,
        "factorial_2x2x2_cells": [cells_by_bits[b] for b in ("000", "001", "010", "011", "100", "101", "110", "111")],
        "yates_effects_open_Fz_pN": _yates_effects("F_z_disengaged_3deg_pN"),
        "yates_effects_switching_swing_pN": _yates_effects("switching_force_swing_pN"),
        "recursion_depth_ladder": depth_ladder,
        "micro_bridge_isolation": bridge_isolation,
        "vernier_phase_isolation": vernier_isolation,
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
    all_order = [
        "H3_Cantor_Sym_2x2x2",
        "H3_Cantor_Robust",
        "Ctrl_KnifeEdge_g27",
        "Ctrl_Uni_7Trk",
        "Ctrl_Lin_3Stage",
        "Ctrl_Mono_3Stage",
        "Ctrl_Shuf_OutPhase",
    ]
    order = [c for c in all_order if c in designs_data]
    labels = {
        "H3_Cantor_Sym_2x2x2": "H3-Cantor-Sym (2x2x2)",
        "H3_Cantor_Robust": "H3-Cantor-Robust (b=3)",
        "Ctrl_KnifeEdge_g27": "Ctrl-KnifeEdge-g27",
        "Ctrl_Uni_7Trk": "Ctrl-Uni-7Trk",
        "Ctrl_Lin_3Stage": "Ctrl-Lin-3Stage",
        "Ctrl_Mono_3Stage": "Ctrl-Mono-3Stage",
        "Ctrl_Shuf_OutPhase": "Ctrl-Shuf-OutPhase",
    }
    colors = {
        "H3_Cantor_Sym_2x2x2": "#B22222",
        "H3_Cantor_Robust": "#0072B2",
        "Ctrl_KnifeEdge_g27": "#D55E00",
        "Ctrl_Uni_7Trk": "#009E73",
        "Ctrl_Lin_3Stage": "#CC79A7",
        "Ctrl_Mono_3Stage": "#E69F00",
        "Ctrl_Shuf_OutPhase": "#56B4E9",
    }
    lstyles = {
        "H3_Cantor_Sym_2x2x2": "-",
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
        lw = 2.4 if code in ("H3_Cantor_Sym_2x2x2", "H3_Cantor_Robust") else 1.5
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
        lw = 2.4 if code in ("H3_Cantor_Sym_2x2x2", "H3_Cantor_Robust") else 1.5
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
        ("H3_Cantor_Sym_2x2x2_Gold300K", "H3-Cantor-Sym 2x2x2 (Gold)", "#B22222", "-"),
        ("H3_Cantor_Robust_PEC", "H3-Cantor (PEC 0K)", "#003f5c", "-"),
        ("H3_Cantor_Robust_Gold300K", "H3-Cantor (Gold 300K)", "#0072B2", "--"),
        ("Ctrl_Lin_3Stage_Gold300K", "Ctrl-Lin-3Stage", "#CC79A7", ":"),
        ("Ctrl_KnifeEdge_g27_Gold300K", "Ctrl-KnifeEdge-g27", "#D55E00", "-."),
    ):
        if key_s not in st_lomb:
            continue
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

    columns_used = [
        "designs.*.benchmark_1_axial_stroke.stroke_points",
        "designs.*.benchmark_2_angular_lateral.torque_ripple_R_tau",
        "designs.*.benchmark_3_rib_and_vcrit.rib_elastostatics.SF_rib",
        "designs.*.benchmark_4_cleanroom_yield.etch_bias_curve",
        "designs.*.benchmark_4_cleanroom_yield.cleanroom_yield_Y_lab_pct",
        "benchmark_5_ln3_scale_covering.wavenumber_subbands.H3_Cantor_Robust_Gold300K",
        "benchmark_5_ln3_scale_covering.stroke_log_periodicity",
    ]
    prov_solver_params = {"code_hash": code_hash}
    save_plot_provenance(
        str(pdf_path),
        str(DEFAULT_OUTPUT_JSON),
        columns_used,
        solver_name="vector_dyadic_bem_3d_plus_hermite_fem",
        solver_parameters=prov_solver_params,
    )
    save_plot_provenance(
        str(png_path),
        str(DEFAULT_OUTPUT_JSON),
        columns_used,
        solver_name="vector_dyadic_bem_3d_plus_hermite_fem",
        solver_parameters=prov_solver_params,
    )


def _mref(metric_key: str) -> str:
    """Return a clean LaTeX macro invocation `\\MacroName{}` for `metric_key`."""
    return f"\\{_sanitize_macro_name(metric_key)}{{}}"


def _fmt_sf_tex(sf_val: float) -> str:
    val = float(sf_val)
    if val < 999.0:
        return f"{val:.1f}"
    exp = int(math.floor(math.log10(abs(val))))
    mant = val / (10.0**exp)
    return f"{mant:.2f}\\times 10^{{{exp}}}"


def _render_ablation_figure(
    summary: Mapping[str, Any],
    pdf_path: Path,
    png_path: Path,
    code_hash: str,
) -> None:
    """Render 4-panel mechanistic ablation figure (2^3 factorial, Yates contrasts, depth N=1..3, bridges/Vernier)."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    b6 = summary["benchmark_6_mechanistic_ablations"]
    cells = b6["factorial_2x2x2_cells"]
    yates = b6["yates_effects_open_Fz_pN"]
    depth = b6["recursion_depth_ladder"]
    br = b6["micro_bridge_isolation"]
    vn = b6["vernier_phase_isolation"]

    plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9})
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.6), constrained_layout=True)

    # Panel (a): 2^3 (I_r, I_theta, I_z) Factorial Open Repulsion & Engaged Latch
    ax = axes[0, 0]
    x_idx = np.arange(len(cells))
    w_bar = 0.37
    f_open = [c["F_z_disengaged_3deg_pN"] for c in cells]
    f_eng_abs = [abs(c["F_z_engaged_48deg_pN"]) for c in cells]
    ax.bar(x_idx - 0.5 * w_bar, f_open, width=w_bar, color="#B22222", edgecolor="#222222", lw=0.7, label="Open repulsion $F_z(3^\\circ)$")
    ax.bar(x_idx + 0.5 * w_bar, f_eng_abs, width=w_bar, color="#0072B2", edgecolor="#222222", lw=0.7, label="Engaged latch $|F_z(48^\\circ)|$")
    ax.axhline(0.0, color="#333333", lw=0.9, ls="--")
    ax.set_xticks(x_idx)
    ax.set_xticklabels([f"$({c['I_r']},{c['I_theta']},{c['I_z']})$" for c in cells], fontsize=8.3)
    ax.set_xlabel("Factorial cell $(I_r, I_\\theta, I_z)$")
    ax.set_ylabel("Axial Casimir force magnitude (pN)")
    ax.set_title("a  $2^3$ Homothetic $(r,\\theta,z)$ Factorial Switching")
    ax.legend(fontsize=8.0, loc="upper left")
    ax.grid(True, axis="y", alpha=0.25)

    # Panel (b): Orthogonal Yates Main Effects & Multi-Axis Synergy on F_z(3 deg)
    ax = axes[0, 1]
    eff_labels = [
        "$\\Delta_r$",
        "$\\Delta_\\theta$",
        "$\\Delta_z$",
        "$\\mathcal{I}_{r\\theta}$",
        "$\\mathcal{I}_{rz}$",
        "$\\mathcal{I}_{\\theta z}$",
        "$\\mathcal{I}_{r\\theta z}$",
    ]
    eff_vals = [
        yates["main_effect_r"],
        yates["main_effect_theta"],
        yates["main_effect_z"],
        yates["interaction_r_theta"],
        yates["interaction_r_z"],
        yates["interaction_theta_z"],
        yates["synergy_3way_r_theta_z"],
    ]
    eff_cols = ["#B22222" if v >= 0.0 else "#D55E00" for v in eff_vals]
    bars = ax.bar(np.arange(len(eff_vals)), eff_vals, color=eff_cols, width=0.58, edgecolor="#222222", lw=0.7)
    ax.axhline(0.0, color="#333333", lw=0.9, ls="--")
    ax.set_xticks(np.arange(len(eff_vals)))
    ax.set_xticklabels(eff_labels, fontsize=9.0)
    ax.set_ylabel("Orthogonal Yates contrast on $F_z(3^\\circ)$ (pN)")
    ax.set_title("b  Exact Yates Main-Effect & Synergy Decomposition")
    for b_rect, v in zip(bars, eff_vals):
        va = "bottom" if v >= 0.0 else "top"
        off = 0.02 if v >= 0.0 else -0.02
        ax.text(b_rect.get_x() + 0.5 * b_rect.get_width(), v + off, f"{v:+.2f}", ha="center", va=va, fontsize=7.6)
    ax.grid(True, axis="y", alpha=0.25)

    # Panel (c): Recursion-Depth Ladder N = 1 -> 2 -> 3 at Constant Active Tooth Area
    ax = axes[1, 0]
    ns = [row["N_depth"] for row in depth]
    fz_n = [row["F_z_disengaged_3deg_pN"] for row in depth]
    sw_n = [row["switching_force_swing_pN"] for row in depth]
    ax.plot(ns, fz_n, marker="o", ms=6.5, lw=2.3, color="#B22222", label="Open levitation $F_z(3^\\circ)$")
    ax.plot(ns, sw_n, marker="s", ms=6.0, lw=2.1, ls="--", color="#0072B2", label="Switching swing $\\Delta F_z$")
    ax.set_xticks(ns)
    ax.set_xticklabels([f"$N={n}$ ({row['n_tracks']} trk)" for n, row in zip(ns, depth)])
    ax.set_ylabel("Force (pN)")
    ax.set_title("c  Area-Matched Cantor Recursion Ladder ($N=1,2,3$)")
    ax.legend(fontsize=8.0, loc="upper left")
    ax.grid(True, alpha=0.25)

    # Panel (d): Stator Micro-Bridge & Vernier Phase Isolations
    ax = axes[1, 1]
    cat_labels = [
        "No Bridges\n($\\mathrm{SF}_{\\mathrm{rib}}$)",
        "Bridged H3\n($\\mathrm{SF}_{\\mathrm{rib}}$)",
        "Vernier\n($10^2\\mathcal{R}_\\tau$)",
        "Symmetric $\\Delta\\phi=0$\n($10^2\\mathcal{R}_\\tau$)",
    ]
    cat_vals = [
        max(br["unbridged_SF_rib"], 1.0e-3),
        max(br["bridged_SF_rib"], 1.0e-3),
        max(100.0 * vn["vernier_R_tau"], 1.0e-3),
        max(100.0 * vn["in_phase_R_tau"], 1.0e-3),
    ]
    cat_cols = ["#D55E00", "#009E73", "#0072B2", "#B22222"]
    ax.bar(np.arange(4), cat_vals, color=cat_cols, width=0.56, edgecolor="#222222", lw=0.7)
    ax.axhline(1.0, color="#333333", lw=1.1, ls="--", label="Collapse threshold $\\mathrm{SF}_{\\mathrm{rib}}=1$")
    ax.set_yscale("log")
    ax.set_xticks(np.arange(4))
    ax.set_xticklabels(cat_labels, fontsize=8.2)
    ax.set_ylabel("Dimensionless metric (log scale)")
    ax.set_title("d  Stator Micro-Bridge & Angular Phase Ablations")
    ax.legend(fontsize=8.0, loc="best")
    ax.grid(True, axis="y", alpha=0.25)

    fig.savefig(pdf_path, dpi=300)
    fig.savefig(png_path, dpi=220)
    plt.close(fig)

    cols = [
        "benchmark_6_mechanistic_ablations.factorial_2x2x2_cells",
        "benchmark_6_mechanistic_ablations.yates_effects_open_Fz_pN",
        "benchmark_6_mechanistic_ablations.recursion_depth_ladder",
        "benchmark_6_mechanistic_ablations.micro_bridge_isolation",
        "benchmark_6_mechanistic_ablations.vernier_phase_isolation",
    ]
    for p in (pdf_path, png_path):
        save_plot_provenance(
            str(p),
            str(DEFAULT_OUTPUT_JSON),
            cols,
            solver_name="vector_dyadic_bem_3d_plus_hermite_fem",
            solver_parameters={"code_hash": code_hash},
        )


def _write_latex_summary_table(summary: Mapping[str, Any], out_tex: Path) -> None:
    """Write 100% macro-driven LaTeX benchmark table from solved 2x2x2 BEM/FEM metrics."""
    out_tex.parent.mkdir(parents=True, exist_ok=True)
    designs_data = summary["designs"]
    all_order = [
        ("H3_Cantor_Sym_2x2x2", "\\textbf{H3-Cantor ($\\Delta\\phi=0^\\circ$)}"),
        ("H3_Cantor_Robust", "H3-Cantor-Vernier ($\\Delta\\phi_k\\neq 0$)"),
        ("Ctrl_KnifeEdge_g27", "Ctrl-KnifeEdge-g27"),
        ("Ctrl_Uni_7Trk", "Ctrl-Uni-7Trk"),
        ("Ctrl_Lin_3Stage", "Ctrl-Lin-3Stage"),
        ("Ctrl_Mono_3Stage", "Ctrl-Mono-3Stage"),
        ("Ctrl_Shuf_OutPhase", "Ctrl-Shuf-OutPhase"),
    ]
    order = [(c, n) for c, n in all_order if c in designs_data]
    lines = [
        "% Auto-generated by execution/run_unified_fractal_robustness_study.py -- DO NOT EDIT BY HAND",
        "\\begin{table*}[t]",
        "\\centering",
        f"\\caption{{Multi-perturbation nanomechanical and cleanroom fabrication benchmark comparing the primary \\texttt{{H3-Cantor}} architecture ($b=3$, $N=3$, $g_{{\\min}}={_mref('rob_gmin_nm_disp')}\\,\\mathrm{{nm}}$, $A_{{\\mathrm{{tooth}}}}={_mref('rob_atooth_um2_disp')}\\,\\mu\\mathrm{{m}}^2$), its Vernier phase variant, and five strictly area- and $g_{{\\min}}$-matched non-fractal controls on the unified $2\\times 2\\times 2$ 3D BEM mesh ($300\\,\\mathrm{{K}}$ Drude--Lorentz Gold) and 32-element Hermite curved-beam FEM.}}",
        "\\label{tab:unified_fractal_robustness}",
        "\\small",
        "\\begin{tabular}{lcccccccc}",
        "\\hline\\hline",
        "Design & $F_z(\\theta_{\\mathrm{open}})$ & $F_z(\\theta_{\\mathrm{eng}})$ & Stroke Basin $\\mathcal{B}_z$ & Min Stroke $F_z$ & Torque Ripple & Rib Safety & $V_{\\mathrm{crit}}$ & Lab Yield \\\\",
        " & (pN) & (pN) & $\\ln(z_{\\max}/z_{\\min})$ & (pN) & $\\mathcal{R}_\\tau$ & $\\mathrm{SF}_{\\mathrm{rib}}$ & (mV) & $Y_{\\mathrm{lab}}$ (\\%) \\\\",
        "\\hline",
    ]
    for code, tex_name in order:
        p = f"rob_tbl_{code}"
        lines.append(
            f"{tex_name} & {_mref(p + '_fz_open')} & {_mref(p + '_fz_eng')} & "
            f"{_mref(p + '_bz')} & {_mref(p + '_min_fz')} & "
            f"{_mref(p + '_rtau')} & ${{{_mref(p + '_sf')}}}$ & {_mref(p + '_vcrit')} & {_mref(p + '_ylab')} \\\\"
        )
    lines.extend(["\\hline\\hline", "\\end{tabular}", "\\end{table*}", ""])
    out_tex.write_text("\n".join(lines), encoding="utf-8")


def _write_ablation_latex_table(summary: Mapping[str, Any], out_tex: Path) -> None:
    """Write 100% macro-driven LaTeX table for the 2^3 factorial, recursion-depth ladder, and structural ablations."""
    out_tex.parent.mkdir(parents=True, exist_ok=True)
    b6 = summary["benchmark_6_mechanistic_ablations"]
    lines = [
        "% Auto-generated by execution/run_unified_fractal_robustness_study.py -- DO NOT EDIT BY HAND",
        "\\begin{table*}[t]",
        "\\centering",
        f"\\caption{{Mechanistic decomposition of \\texttt{{H3-Cantor}} on the matched $2\\times 2\\times 2$ 3D BEM mesh: orthogonal $2^3$ $(I_r, I_\\theta, I_z)$ homothetic staging factorial, area-matched Cantor recursion-depth ladder ($N=1,2,3$ at $A_{{\\mathrm{{tooth}}}}={_mref('rob_atooth_um2_disp')}\\,\\mu\\mathrm{{m}}^2$), and suspended stator micro-bridge isolation.}}",
        "\\label{tab:h3_mechanistic_ablations}",
        "\\small",
        "\\begin{tabular}{llccccc}",
        "\\hline\\hline",
        "Group & Configuration & $F_z(\\theta_{\\mathrm{open}})$ (pN) & $F_z(\\theta_{\\mathrm{eng}})$ (pN) & Swing $\\Delta F_z$ (pN) & $\\mathrm{SF}_{\\mathrm{rib}}$ & $V_{\\mathrm{crit}}$ (mV) \\\\",
        "\\hline",
    ]
    cell_desc = {
        "000": "Uniform baseline $(0,0,0)$",
        "001": "$z$-staging only $(0,0,1)$",
        "010": "$\\theta$-subdivision only $(0,1,0)$",
        "011": "$(\\theta,z)$ staging $(0,1,1)$",
        "100": "$r$-Cantor only $(1,0,0)$",
        "101": "$(r,z)$ staging $(1,0,1)$",
        "110": "$(r,\\theta)$ staging $(1,1,0)$",
        "111": "\\textbf{Full H3-Cantor $(1,1,1)$}",
    }
    for c in b6["factorial_2x2x2_cells"]:
        bits = c["bits"]
        p = f"abl_f{bits}"
        lines.append(
            f"$2^3$ Factorial & {cell_desc[bits]} & {_mref(p + '_fz_open')} & {_mref(p + '_fz_eng')} & "
            f"{_mref(p + '_swing')} & ${{{_mref(p + '_sf')}}}$ & {_mref(p + '_vcrit')} \\\\"
        )
    lines.append("\\hline")
    for row in b6["recursion_depth_ladder"]:
        n_d = int(row["N_depth"])
        p = f"abl_depth_n{n_d}"
        lines.append(
            f"Depth Ladder & Generation $N={n_d}$ ({_mref(p + '_ntrk')} tracks) & {_mref(p + '_fz_open')} & "
            f"{_mref(p + '_fz_eng')} & {_mref(p + '_swing')} & ${{{_mref(p + '_sf')}}}$ & {_mref(p + '_vcrit')} \\\\"
        )
    lines.append("\\hline")
    lines.append(
        f"Bridge Ablation & Unbridged stator (\\texttt{{Abl-NoBridges}}) & {_mref('abl_nobr_fz_open')} & "
        f"{_mref('abl_nobr_fz_eng')} & {_mref('abl_nobr_swing')} & ${{{_mref('abl_nobr_sf')}}}$ & {_mref('abl_nobr_vcrit')} \\\\"
    )
    lines.extend(["\\hline\\hline", "\\end{tabular}", "\\end{table*}", ""])
    out_tex.write_text("\n".join(lines), encoding="utf-8")


def _log_grounded_provenance_metrics(summary: Mapping[str, Any], solver_params: Mapping[str, Any]) -> None:
    """Export all robustness, ln(3), mesh-convergence, and mechanistic ablation macros to provenance_metrics.json."""
    set_solver_provenance("vector_dyadic_bem_3d_plus_hermite_fem", dict(solver_params))
    step_id = "unified_fractal_robustness_3d_study"
    h3 = summary["designs"]["H3_Cantor_Robust"]
    h3_sym = summary["designs"]["H3_Cantor_Sym_2x2x2"]
    ke = summary["designs"]["Ctrl_KnifeEdge_g27"]
    sp_pec = summary["benchmark_5_ln3_scale_covering"]["wavenumber_subbands"]["H3_Cantor_Robust_PEC"]
    sp_gold = summary["benchmark_5_ln3_scale_covering"]["wavenumber_subbands"]["H3_Cantor_Robust_Gold300K"]
    sp_sym_pec = summary["benchmark_5_ln3_scale_covering"]["wavenumber_subbands"]["H3_Cantor_Sym_2x2x2_PEC"]
    sp_sym_gold = summary["benchmark_5_ln3_scale_covering"]["wavenumber_subbands"]["H3_Cantor_Sym_2x2x2_Gold300K"]
    mc_mesh = summary["benchmark_5_ln3_scale_covering"]["mesh_convergence"]
    b6 = summary["benchmark_6_mechanistic_ablations"]

    step_summary: dict[str, Any] = {
        "status": "completed",
        "executed_at": summary["executed_at"],
        "h3_sym_2x2x2_Fz_op_pN": h3_sym["benchmark_1_axial_stroke"]["F_z_op_pN"],
        "h3_sym_2x2x2_R_tau": h3_sym["benchmark_2_angular_lateral"]["torque_ripple_R_tau"],
        "h3_sym_2x2x2_Y_lab_pct": h3_sym["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
        "h3_Fz_op_pN": h3["benchmark_1_axial_stroke"]["F_z_op_pN"],
        "h3_Y_lab_pct": h3["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
        "knife_edge_Y_lab_pct": ke["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
    }
    log_step(step_id, step_summary)

    scalar_entries: dict[str, int | float | str] = {
        "rob_gmin_nm_disp": f"{h3_sym['geometry_descriptors']['g_r_min_nm']:.0f}",
        "rob_atooth_um2_disp": f"{h3_sym['geometry_descriptors']['A_tooth_um2']:.3f}",
        "rob_ntotal_bem_tasks": int(summary["total_bem_tasks_evaluated"]),
        "rob_mc_chips_per_design": int(h3_sym["benchmark_4_cleanroom_yield"]["monte_carlo_n_chips"]),
        # Raw floats
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
        "h3_sym_Fz_op_pN": h3_sym["benchmark_1_axial_stroke"]["F_z_op_pN"],
        "h3_sym_Fz_engaged_pN": h3_sym["benchmark_2_angular_lateral"]["F_z_engaged_48deg_pN"],
        "h3_sym_stroke_span_nm": h3_sym["benchmark_1_axial_stroke"]["sign_safe_span_nm"],
        "h3_sym_stroke_basin_Bz": h3_sym["benchmark_1_axial_stroke"]["log_stroke_basin_Bz"],
        "h3_sym_min_stroke_Fz_pN": h3_sym["benchmark_1_axial_stroke"]["min_Fz_working_window_45_360nm_pN"],
        "h3_sym_escape_work_kBT": h3_sym["benchmark_1_axial_stroke"]["escape_work_kBT_300K"],
        "h3_sym_torque_ripple": h3_sym["benchmark_2_angular_lateral"]["torque_ripple_R_tau"],
        "h3_sym_SF_rib": h3_sym["benchmark_3_rib_and_vcrit"]["rib_elastostatics"]["SF_rib"],
        "h3_sym_V_crit_mV": h3_sym["benchmark_3_rib_and_vcrit"]["laplace_electrostatics"]["V_crit_mV"],
        "h3_sym_yield_pct": h3_sym["benchmark_4_cleanroom_yield"]["cleanroom_yield_Y_lab_pct"],
        "h3_sym_median_mc_Fz_pN": h3_sym["benchmark_4_cleanroom_yield"]["median_mc_Fz_net_pN"],
        #Formatted prose macros for H3-Cantor (Sym 2x2x2) & controls
        "h3_sym_fz_peak_disp": f"{h3_sym['benchmark_1_axial_stroke']['F_z_peak_pN']:+.2f}",
        "h3_sym_z_peak_nm_disp": f"{h3_sym['benchmark_1_axial_stroke']['z_peak_nm']:.0f}",
        "h3_sym_z_safe_min_nm_disp": f"{h3_sym['benchmark_1_axial_stroke']['sign_safe_z_min_nm']:.1f}",
        "h3_sym_z_safe_max_nm_disp": f"{h3_sym['benchmark_1_axial_stroke']['sign_safe_z_max_nm']:.0f}",
        "h3_sym_span_nm_disp": f"{h3_sym['benchmark_1_axial_stroke']['sign_safe_span_nm']:.1f}",
        "h3_sym_escape_kbt_disp": f"{h3_sym['benchmark_1_axial_stroke']['escape_work_kBT_300K']:.2f}",
        "h3_sym_swing_pn_disp": f"{h3_sym['benchmark_2_angular_lateral']['switching_force_swing_pN']:.2f}",
        "h3_sym_switch_ratio_disp": f"{h3_sym['benchmark_2_angular_lateral']['switching_ratio_abs']:.2f}",
        "h3_sym_klat_mn_disp": f"{h3_sym['benchmark_2_angular_lateral']['K_cas_lateral_mN_per_m']:.3f}",
        "h3_sym_rib_defl_nm_disp": f"{h3_sym['benchmark_3_rib_and_vcrit']['rib_elastostatics']['max_rib_deflection_nm']:.3f}",
        "h3_sym_r5_ret_pct_disp": f"{h3_sym['benchmark_4_cleanroom_yield']['r5nm_retention_pct']:.1f}",
        "h3_sym_r10_ret_pct_disp": f"{h3_sym['benchmark_4_cleanroom_yield']['r10nm_retention_pct']:.1f}",
        "h3_sym_overetch_z160_disp": f"{h3_sym['benchmark_4_cleanroom_yield']['severe_overetch_m40nm_stage2_z160nm_Fz_pN']:+.2f}",
        "h3_sym_ci_lo_disp": f"{h3_sym['benchmark_4_cleanroom_yield']['cleanroom_yield_95ci_pct'][0]:.1f}",
        "h3_sym_ci_hi_disp": f"{h3_sym['benchmark_4_cleanroom_yield']['cleanroom_yield_95ci_pct'][1]:.1f}",
        # Spectral sub-band spacing & Lomb-Scargle
        "h3_pec_dlnk_21": sp_pec["spacing_comparison"]["delta_ln_kappa_21"],
        "h3_pec_dlnk_32": sp_pec["spacing_comparison"]["delta_ln_kappa_32"],
        "h3_gold_dlnk_21": sp_gold["spacing_comparison"]["delta_ln_kappa_21"],
        "h3_gold_dlnk_32": sp_gold["spacing_comparison"]["delta_ln_kappa_32"],
        "h3_sym_pec_dlnk_21_disp": f"{sp_sym_pec['spacing_comparison']['delta_ln_kappa_21']:.2f}",
        "h3_sym_pec_dlnk_32_disp": f"{sp_sym_pec['spacing_comparison']['delta_ln_kappa_32']:.2f}",
        "h3_sym_gold_dlnk_21_disp": f"{sp_sym_gold['spacing_comparison']['delta_ln_kappa_21']:.2f}",
        "h3_sym_gold_dlnk_32_disp": f"{sp_sym_gold['spacing_comparison']['delta_ln_kappa_32']:.2f}",
        "h3_sym_gold_k1_disp": f"{sp_sym_gold['peaks_by_generation']['1']['kappa_peak_um_inv']:.2f}",
        "h3_sym_gold_k2_disp": f"{sp_sym_gold['peaks_by_generation']['2']['kappa_peak_um_inv']:.2f}",
        "h3_sym_gold_k3_disp": f"{sp_sym_gold['peaks_by_generation']['3']['kappa_peak_um_inv']:.2f}",
        # 3-tier panel-mesh ladder
        "h3_mesh_t1_open_disp": f"{mc_mesh['F_z_sym_tier1_1x1x1_pN']:+.2f}",
        "h3_mesh_t2_open_disp": f"{mc_mesh['F_z_sym_tier2_2x2x2_pN']:+.2f}",
        "h3_mesh_t3_open_disp": f"{mc_mesh['F_z_sym_tier3_3x3x3_pN']:+.2f}",
        "h3_mesh_rich_open_disp": f"{mc_mesh['F_z_sym_richardson_pN']:+.2f}",
        "h3_mesh_t1_eng_disp": f"{mc_mesh['F_z_sym_eng_tier1_pN']:+.2f}",
        "h3_mesh_t2_eng_disp": f"{mc_mesh['F_z_sym_eng_tier2_pN']:+.2f}",
        "h3_mesh_t3_eng_disp": f"{mc_mesh['F_z_sym_eng_tier3_pN']:+.2f}",
        "h3_mesh_rich_eng_disp": f"{mc_mesh['F_z_sym_eng_richardson_pN']:+.2f}",
        "h3_mesh_t2_t3_diff_pct_disp": f"{mc_mesh['relative_difference_pct']:.1f}",
        "h3_mesh_t3_rich_diff_pct_disp": f"{mc_mesh['tier3_vs_richardson_pct']:.1f}",
        "h3_mesh_t2_nr": int(mc_mesh["tier2_rotor_panels_sector"]),
        "h3_mesh_t2_ns": int(mc_mesh["tier2_stator_panels_sector"]),
        "h3_mesh_t3_nr": int(mc_mesh["refined_rotor_panels_sector"]),
        "h3_mesh_t3_ns": int(mc_mesh["refined_stator_panels_sector"]),
    }

    st_lomb_sym = summary["benchmark_5_ln3_scale_covering"]["stroke_log_periodicity"].get(
        "H3_Cantor_Sym_2x2x2_Gold300K", {}
    )
    ls_sym = st_lomb_sym.get("free_frequency_lomb_scargle", {})
    if not ls_sym.get("underdetermined", True):
        scalar_entries["h3_sym_lomb_omega_peak_disp"] = f"{ls_sym['omega_hat_1h']:.2f}"
        scalar_entries["h3_sym_lomb_r2_peak_disp"] = f"{ls_sym['r2_peak_1h']:.3f}"
        scalar_entries["h3_sym_lomb_b_hat_disp"] = f"{ls_sym['b_hat_1h']:.2f}"

    # All 7 main-table rows
    for code, d in summary["designs"].items():
        p = f"rob_tbl_{code}"
        b1 = d["benchmark_1_axial_stroke"]
        b2 = d["benchmark_2_angular_lateral"]
        b3 = d["benchmark_3_rib_and_vcrit"]
        b4 = d["benchmark_4_cleanroom_yield"]
        scalar_entries[p + "_fz_open"] = f"{b1['F_z_op_pN']:+.2f}"
        scalar_entries[p + "_fz_eng"] = f"{b2['F_z_engaged_48deg_pN']:+.2f}"
        scalar_entries[p + "_bz"] = f"{b1['log_stroke_basin_Bz']:.2f}"
        scalar_entries[p + "_min_fz"] = f"{b1['min_Fz_working_window_45_360nm_pN']:+.2f}"
        scalar_entries[p + "_rtau"] = f"{b2['torque_ripple_R_tau']:.4f}"
        scalar_entries[p + "_sf"] = _fmt_sf_tex(b3["rib_elastostatics"]["SF_rib"])
        scalar_entries[p + "_vcrit"] = f"{b3['laplace_electrostatics']['V_crit_mV']:.1f}"
        scalar_entries[p + "_ylab"] = f"{b4['cleanroom_yield_Y_lab_pct']:.1f}"
        scalar_entries[p + "_span_nm"] = f"{b1['sign_safe_span_nm']:.1f}"

    # All 8 factorial cells + Yates effects + Depth ladder + Bridge isolation
    for c in b6["factorial_2x2x2_cells"]:
        p = f"abl_f{c['bits']}"
        scalar_entries[p + "_fz_open"] = f"{c['F_z_disengaged_3deg_pN']:+.2f}"
        scalar_entries[p + "_fz_eng"] = f"{c['F_z_engaged_48deg_pN']:+.2f}"
        scalar_entries[p + "_swing"] = f"{c['switching_force_swing_pN']:.2f}"
        scalar_entries[p + "_sf"] = _fmt_sf_tex(c["SF_rib"])
        scalar_entries[p + "_vcrit"] = f"{c['V_crit_mV']:.1f}"

    y_open = b6["yates_effects_open_Fz_pN"]
    y_sw = b6["yates_effects_switching_swing_pN"]
    for short_k, dict_k in (
        ("dr", "main_effect_r"),
        ("dth", "main_effect_theta"),
        ("dz", "main_effect_z"),
        ("irth", "interaction_r_theta"),
        ("irz", "interaction_r_z"),
        ("ithz", "interaction_theta_z"),
        ("irthz", "synergy_3way_r_theta_z"),
        ("net", "net_gain_111_minus_000"),
    ):
        scalar_entries[f"abl_yates_open_{short_k}"] = f"{y_open[dict_k]:+.2f}"
        scalar_entries[f"abl_yates_swing_{short_k}"] = f"{y_sw[dict_k]:+.2f}"

    for row in b6["recursion_depth_ladder"]:
        n_d = int(row["N_depth"])
        p = f"abl_depth_n{n_d}"
        scalar_entries[p + "_ntrk"] = int(row["n_tracks"])
        scalar_entries[p + "_fz_open"] = f"{row['F_z_disengaged_3deg_pN']:+.2f}"
        scalar_entries[p + "_fz_eng"] = f"{row['F_z_engaged_48deg_pN']:+.2f}"
        scalar_entries[p + "_swing"] = f"{row['switching_force_swing_pN']:.2f}"
        scalar_entries[p + "_sf"] = _fmt_sf_tex(row["SF_rib"])
        scalar_entries[p + "_vcrit"] = f"{row['V_crit_mV']:.1f}"

    no_br = b6["ablation_designs"]["Abl_NoBridges"]
    scalar_entries["abl_nobr_fz_open"] = f"{no_br['F_z_disengaged_3deg_pN']:+.2f}"
    scalar_entries["abl_nobr_fz_eng"] = f"{no_br['F_z_engaged_48deg_pN']:+.2f}"
    scalar_entries["abl_nobr_swing"] = f"{no_br['switching_force_swing_pN']:.2f}"
    scalar_entries["abl_nobr_sf"] = _fmt_sf_tex(no_br["SF_rib"])
    scalar_entries["abl_nobr_vcrit"] = f"{no_br['V_crit_mV']:.1f}"
    scalar_entries["abl_nobr_defl_nm"] = f"{no_br['max_rib_deflection_nm']:.1f}"
    scalar_entries["abl_bridge_sf_gain_ratio"] = _fmt_sf_tex(b6["micro_bridge_isolation"]["SF_rib_gain_ratio"])

    keys_list = list(scalar_entries.items())
    for i_k, (key, val) in enumerate(keys_list):
        log_metric(key, val, step_id=step_id, defer_save=(i_k < len(keys_list) - 1))
    export_macros()
    export_macros(output_path=str(MANUSCRIPT_MACROS_PATH))


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
    ablation_designs = build_h3_mechanistic_ablation_designs()
    by_code = {d.code: d for d in (*designs, *ablation_designs)}
    code_hash = _compute_combined_code_hash()

    # Pre-flight geometric & 3D collision verification across stroke and rotational switching
    collision_audit: dict[str, Any] = {}
    for des in (*designs, *ablation_designs):
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

    all_tasks = _build_bem_task_list(designs, ablation_designs)

    # Micro-probe mode (`--max-steps > 0`) for hpc-workload-gate empirical profiling
    if args.max_steps > 0:
        clear_bem_lu_caches()
        n_run = min(int(args.max_steps), len(all_tasks))
        # Representative cold-LU (~30%) + cached-sweep (~70%) task mix across 2x2x2 designs & ablations
        n_stroke_per_design = len(STROKE_Z_GRID_UM)
        if n_run == 5 and len(all_tasks) >= 3 * n_stroke_per_design:
            probe_tasks = [
                all_tasks[0],                          # H3_Cantor_Robust (2x2x2, cold LU)
                all_tasks[1],                          # H3_Cantor_Robust (2x2x2, cached LU)
                all_tasks[2],                          # H3_Cantor_Robust (2x2x2, cached LU)
                all_tasks[2 * n_stroke_per_design],    # Ctrl_Uni_7Trk (2x2x2, cold LU)
                all_tasks[-1],                         # Abl_Depth_N2 (2x2x2 ablation)
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
            "model": "BEM_vector_dyadic_Gold_300K_2x2x2_probe",
            "dataset": "h3_cantor_2x2x2_controls_and_ablations",
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
    verified_v2_ckpt_dir = args.checkpoint_dir / f"hash_{VERIFIED_V2_SYM_CODE_HASH}_nxi{args.n_xi}"

    task_results: dict[str, dict[str, Any]] = {}
    n_total = len(all_tasks)
    print(f"[UNIFIED-ROBUSTNESS] Executing {n_total} grounded 3D BEM tasks (n_xi={args.n_xi}, code_hash={code_hash})...")

    for idx, tsk in enumerate(all_tasks, start=1):
        t_key = str(tsk["task_key"])
        d_code = str(tsk["design_code"])
        ckpt_file = ckpt_dir / f"{t_key}.json"
        loaded_ckpt: dict[str, Any] | None = None
        if not args.no_cache_ckpt and ckpt_file.is_file():
            candidate_ckpt = json.loads(ckpt_file.read_text(encoding="utf-8"))
            if _checkpoint_matches_task(candidate_ckpt, tsk, by_code=by_code):
                loaded_ckpt = candidate_ckpt
        if (
            loaded_ckpt is None
            and not args.no_cache_ckpt
            and d_code == "H3_Cantor_Sym_2x2x2"
            and tsk.get("mesh_override") is None
            and verified_v2_ckpt_dir.is_dir()
            and verified_v2_ckpt_dir.resolve() != ckpt_dir.resolve()
        ):
            prev_file = verified_v2_ckpt_dir / f"{t_key}.json"
            if prev_file.is_file():
                candidate_ckpt = json.loads(prev_file.read_text(encoding="utf-8"))
                if _checkpoint_matches_task(candidate_ckpt, tsk, by_code=by_code):
                    loaded_ckpt = candidate_ckpt
                    ckpt_file.write_text(json.dumps(loaded_ckpt), encoding="utf-8")
        if loaded_ckpt is not None:
            task_results[t_key] = loaded_ckpt
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
    b6_res = _analyze_mechanistic_ablations(ablation_designs, designs_summary, task_results)

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
        "by_electrostatic_V_crit_mV": sorted(
            ((c, designs_summary[c]["benchmark_3_rib_and_vcrit"]["laplace_electrostatics"]["V_crit_mV"]) for c in designs_summary),
            key=lambda kv: kv[1],
            reverse=True,
        ),
        "by_min_working_stroke_Fz_pN": sorted(
            ((c, designs_summary[c]["benchmark_1_axial_stroke"]["min_Fz_working_window_45_360nm_pN"]) for c in designs_summary),
            key=lambda kv: kv[1],
            reverse=True,
        ),
        "by_median_mc_Fz_net_pN": sorted(
            ((c, designs_summary[c]["benchmark_4_cleanroom_yield"]["median_mc_Fz_net_pN"]) for c in designs_summary),
            key=lambda kv: kv[1],
            reverse=True,
        ),
    }

    solver_params = {
        "formulation": "vector_dyadic",
        "symmetry": "C4_Bloch_4_sectors",
        "bem_mesh_parity": "2x2x2_lobe_9_collar_all_designs",
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
        "model": "BEM_vector_dyadic_3D_2x2x2_Gold300K_and_Hermite_FEM",
        "dataset": "h3_cantor_2x2x2_unified_robustness_and_ablations",
        "status": "completed",
        "executed_at": executed_iso,
        "code_hash": code_hash,
        "elapsed_total_s": float(time.perf_counter() - t_start),
        "total_bem_tasks_evaluated": n_total,
        "solver_parameters": solver_params,
        "rankings": rankings,
        "designs": designs_summary,
        "benchmark_5_ln3_scale_covering": b5_res,
        "benchmark_6_mechanistic_ablations": b6_res,
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
        _render_ablation_figure(full_summary, DEFAULT_ABLATION_FIG_PDF, DEFAULT_ABLATION_FIG_PNG, code_hash)
        for fig_png in (DEFAULT_FIGURE_PNG, DEFAULT_ABLATION_FIG_PNG):
            fig_audit = inspect_rendered_png_quality(
                fig_png, min_fg_fraction=0.04, max_fg_fraction=0.96
            )
            if fig_audit["status"] != "PASS":
                raise RuntimeError(f"Figure visual inspection failed ({fig_png.name}): {fig_audit}")
        _write_latex_summary_table(full_summary, DEFAULT_LATEX_TABLE)
        _write_ablation_latex_table(full_summary, DEFAULT_ABLATION_LATEX_TABLE)
        print(f"[UNIFIED-ROBUSTNESS] Saved summary JSON   -> {out_json}")
        print(f"[UNIFIED-ROBUSTNESS] Saved figures        -> {DEFAULT_FIGURE_PDF}, {DEFAULT_ABLATION_FIG_PDF}")
        print(f"[UNIFIED-ROBUSTNESS] Saved LaTeX tables   -> {DEFAULT_LATEX_TABLE}, {DEFAULT_ABLATION_LATEX_TABLE}")

        if not args.skip_blender:
            blender_render_dir = REPOSITORY_ROOT / "results" / "unified_fractal_robustness_blender"
            expected_render_count = len(designs) + 4
            has_cached_renders = (
                blender_render_dir.is_dir()
                and len(list(blender_render_dir.glob("render_*.png"))) >= expected_render_count
            )
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
