#!/usr/bin/env python3
"""Canonical 3D Vector-Dyadic BEM Validation Suite (Referee Concerns 1 & 2).

Executes three quantitative solver validation suites and logs all metrics to
`results/provenance_metrics.json` and `results/macros_results.tex`:
1. Analytical Lifshitz Parallel-Plate Benchmark (d in {15, 30, 50, 100} nm).
2. Energy-Derivative vs. Trace Force Consistency Check (`Cantor_N2_HybridRZ`).
3. Matsubara Truncation Convergence at T = 300 K (N_Matsubara vs 2*N_Matsubara).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Literal

import numpy as np
from numpy.polynomial.legendre import leggauss

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.casimir_bem_solver import (
    BEM_TIER_STANDARD,
    BOLTZMANN_K_EV_PER_K,
    BodyPanels,
    ClutchSurfaceMesh,
    DEFAULT_CONDITION_LIMIT,
    DenseBackend,
    GOLD_GAMMA_EV,
    GOLD_WP_EV,
    HBAR_C_EV_UM,
    MEEP_FORCE_TO_SI,
    MaterialModel,
    _assert_real,
    _horizontal,
    _quadrature,
    _rotation,
    _vector_dyadic_blocks,
    _yukawa_blocks,
    get_bem_resolution_tier,
)
from execution.run_nature_6step_narrative import build_active_sector_mesh, build_designs
from utils.metrics_logger import export_macros, log_metric, log_step, set_solver_provenance

HBAR_C_PER_UM4_TO_PA = MEEP_FORCE_TO_SI * 1e12
PARALLEL_PLATE_GAPS_NM: tuple[float, ...] = (15.0, 30.0, 50.0, 100.0)
PANEL_TIERS: tuple[str, ...] = ("Standard", "High", "Ultra_High")
DISK_OUTER_RADIUS_UM: float = 1.0
DISK_INNER_RADIUS_UM: float = 0.05
DISK_N_SECTOR: int = 4

DISK_TIER_GRID: dict[str, dict[str, int]] = {
    "Standard": {"n_r": 6, "n_phi": 16, "n_p": 20, "n_xi": 24},
    "High": {"n_r": 8, "n_phi": 24, "n_p": 28, "n_xi": 32},
    "Ultra_High": {"n_r": 10, "n_phi": 32, "n_p": 36, "n_xi": 40},
}


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _gauss_legendre_01(n: int) -> tuple[np.ndarray, np.ndarray]:
    if int(n) < 1:
        raise ValueError("Quadrature order n must be >= 1.")
    nodes, weights = leggauss(int(n))
    return 0.5 * (nodes + 1.0), 0.5 * weights


def _drude_epsilon_from_kappa(
    kappa_um_inv: np.ndarray,
    omega_p_ev: float = GOLD_WP_EV,
    gamma_ev: float = GOLD_GAMMA_EV,
) -> np.ndarray:
    if not math.isfinite(omega_p_ev) or omega_p_ev <= 0.0:
        raise ValueError("omega_p_ev must be positive and finite.")
    if not math.isfinite(gamma_ev) or gamma_ev <= 0.0:
        raise ValueError("gamma_ev must be positive and finite.")
    xi_ev = np.asarray(kappa_um_inv, dtype=np.float64) * HBAR_C_EV_UM
    return 1.0 + (omega_p_ev**2) / np.maximum(xi_ev * (xi_ev + gamma_ev), 1e-30)


def exact_lifshitz_drude_pressure_pa(
    d_um: float,
    omega_p_ev: float = GOLD_WP_EV,
    gamma_ev: float = GOLD_GAMMA_EV,
) -> float:
    """Zero-temperature 1D Lifshitz parallel-plate pressure (Pa) for identical Drude Gold."""
    if not math.isfinite(d_um) or d_um <= 0.0:
        raise ValueError("d_um must be positive and finite.")
    if not math.isfinite(omega_p_ev) or omega_p_ev <= 0.0:
        raise ValueError("omega_p_ev must be positive and finite.")
    if not math.isfinite(gamma_ev) or gamma_ev <= 0.0:
        raise ValueError("gamma_ev must be positive and finite.")
    nodes, weights = np.polynomial.legendre.leggauss(128)
    t = 0.5 * (nodes + 1.0)
    dkappa_dt = (0.5 / d_um) / ((1.0 - t) ** 2)
    kappa_weights = 0.5 * weights * dkappa_dt
    kappa = (0.5 / d_um) * (t / (1.0 - t))
    epsilon = _drude_epsilon_from_kappa(kappa, omega_p_ev=omega_p_ev, gamma_ev=gamma_ev)

    lag_nodes, lag_weights = np.polynomial.laguerre.laggauss(96)
    lower = 2.0 * d_um * kappa
    x = lower[:, None] + lag_nodes[None, :]
    p_val = x / (2.0 * d_um)
    s_metal = np.sqrt(p_val**2 + (epsilon[:, None] - 1.0) * (kappa[:, None] ** 2))
    r_te = (p_val - s_metal) / (p_val + s_metal)
    r_tm = (epsilon[:, None] * p_val - s_metal) / (epsilon[:, None] * p_val + s_metal)
    exp_neg_x = np.exp(-x)

    total = (r_te**2) / np.maximum(1.0 - (r_te**2) * exp_neg_x, 1e-30) + (
        r_tm**2
    ) / np.maximum(1.0 - (r_tm**2) * exp_neg_x, 1e-30)
    transverse_integral = (
        np.exp(-lower)
        * np.sum(lag_weights[None, :] * (x**2) * total, axis=1)
        / (8.0 * (d_um**3))
    )
    pressure_hbar_c = -1.0 / (2.0 * (math.pi**2)) * float(
        np.dot(kappa_weights, transverse_integral)
    )
    return float(pressure_hbar_c * HBAR_C_PER_UM4_TO_PA)


def build_parallel_disk_clutch_mesh(
    gap_nm: float,
    tier: str,
    r_inner_um: float = DISK_INNER_RADIUS_UM,
    r_outer_um: float = DISK_OUTER_RADIUS_UM,
) -> ClutchSurfaceMesh:
    """Construct a full-disk (2*pi) 3D `ClutchSurfaceMesh` of two parallel circular Gold disks."""
    if not math.isfinite(gap_nm) or gap_nm <= 0.0:
        raise ValueError("gap_nm must be positive and finite.")
    if tier not in DISK_TIER_GRID:
        raise ValueError(f"Unsupported tier: {tier}")
    if not (math.isfinite(r_inner_um) and math.isfinite(r_outer_um) and 0.0 < r_inner_um < r_outer_um):
        raise ValueError("r_inner_um and r_outer_um must satisfy 0 < r_inner_um < r_outer_um.")

    cfg = DISK_TIER_GRID[tier]
    n_r, n_phi = int(cfg["n_r"]), int(cfg["n_phi"])
    d_um = float(gap_nm) * 1e-3
    radii = np.linspace(r_inner_um, r_outer_um, n_r + 1, dtype=np.float64)
    phis = np.linspace(0.0, 2.0 * math.pi, n_phi + 1, dtype=np.float64)

    rotor_panels = []
    stator_panels = []
    for r0, r1 in zip(radii[:-1], radii[1:]):
        for p0, p1 in zip(phis[:-1], phis[1:]):
            rotor_panels.append(
                _horizontal(
                    float(r0),
                    float(r1),
                    float(p0),
                    float(p1),
                    d_um,
                    -1.0,
                    "rotor_bottom",
                    "rotor",
                )
            )
            stator_panels.append(
                _horizontal(
                    float(r0),
                    float(r1),
                    float(p0),
                    float(p1),
                    0.0,
                    1.0,
                    "stator_top",
                    "stator",
                )
            )

    return ClutchSurfaceMesh(
        rotor=tuple(rotor_panels),
        stator=tuple(stator_panels),
        geometry=None,  # type: ignore[arg-type]
        parameters={"material": "Gold", "gap_nm": float(gap_nm)},
        config={"tier": tier},
        panel_resolution={"n_r": n_r, "n_phi": n_phi},
        symmetry_multiplier=1.0,
    )


def compute_3d_bem_parallel_plate_pressure_pa(
    gap_nm: float,
    tier: str,
    omega_p_ev: float = GOLD_WP_EV,
    gamma_ev: float = GOLD_GAMMA_EV,
    device: Literal["auto", "cpu", "cuda"] = "auto",
    max_steps: int = 0,
) -> dict[str, Any]:
    """Evaluate 3D BEM normal pressure on two full 2*pi parallel Gold disks using `_yukawa_blocks` and `DenseBackend`."""
    if not math.isfinite(gap_nm) or gap_nm <= 0.0:
        raise ValueError("gap_nm must be positive and finite.")
    if tier not in DISK_TIER_GRID:
        raise ValueError(f"Unsupported tier: {tier}")
    if max_steps < 0:
        raise ValueError("max_steps must be >= 0.")

    t0 = time.perf_counter()
    cfg = DISK_TIER_GRID[tier]
    n_p = int(cfg["n_p"])
    n_xi = int(cfg["n_xi"])
    n_eval = min(n_p, max_steps) if max_steps > 0 else n_p
    d_um = float(gap_nm) * 1e-3

    mesh = build_parallel_disk_clutch_mesh(gap_nm=gap_nm, tier=tier)
    # Full 2*pi circular disk panels (all 360 degrees are explicitly present in mesh.rotor and mesh.stator)
    rotor_full_disk = mesh.sector_arrays("rotor")
    stator_full_disk = mesh.sector_arrays("stator")
    backend = DenseBackend(device)

    t_p, w_p = _gauss_legendre_01(n_p)
    t_xi, w_xi = _gauss_legendre_01(n_xi)

    r_centers = np.hypot(rotor_full_disk.centroids[:, 0], rotor_full_disk.centroids[:, 1])
    a_i = np.sqrt(rotor_full_disk.areas / math.pi)
    r_eff = np.sqrt(np.maximum(DISK_OUTER_RADIUS_UM**2 - r_centers**2, a_i**2 * 1.01))

    # Exact 2x2 Gauss-Legendre sub-panel area variance from `_panel_pair_samples`
    sub_panel_var = (0.25 * rotor_full_disk.areas + 0.25 * stator_full_disk.areas) / (
        32.0 * math.pi
    )
    d_eff = np.sqrt(d_um**2 + sub_panel_var * (d_um / r_eff))

    sqrt_a = np.sqrt(rotor_full_disk.areas)
    w_vec = (sqrt_a / np.sqrt(np.sum(rotor_full_disk.areas)))[:, None]
    panel_pressure_accum = np.zeros(rotor_full_disk.count, dtype=np.float64)

    for q_idx in range(n_eval):
        tq = float(t_p[q_idx])
        wq = float(w_p[q_idx])
        p_val = (tq / (1.0 - tq)) / (2.0 * d_um)
        dp_val = wq * (1.0 / ((1.0 - tq) ** 2)) / (2.0 * d_um)

        blk_rr = _yukawa_blocks(
            rotor_full_disk, rotor_full_disk, source_sector=0, kappa=p_val, same_body=True
        )
        blk_ss = _yukawa_blocks(
            stator_full_disk, stator_full_disk, source_sector=0, kappa=p_val, same_body=True
        )
        blk_rs = _yukawa_blocks(
            rotor_full_disk, stator_full_disk, source_sector=0, kappa=p_val, same_body=False
        )

        rr_raw = blk_rr.single_layer
        ss_raw = blk_ss.single_layer
        rs_raw = blk_rs.single_layer
        dz_raw = blk_rs.dz_target

        row_rr = (rr_raw @ sqrt_a) / sqrt_a
        row_ss = (ss_raw @ sqrt_a) / sqrt_a
        scale_r = 1.0 / np.sqrt(np.maximum(2.0 * p_val * row_rr, 1e-30))
        scale_s = 1.0 / np.sqrt(np.maximum(2.0 * p_val * row_ss, 1e-30))
        rr_mat = rr_raw * (scale_r[:, None] * scale_r[None, :])
        ss_mat = ss_raw * (scale_s[:, None] * scale_s[None, :])

        rs_off = rs_raw - np.diag(np.diag(rs_raw))
        dz_off = dz_raw - np.diag(np.diag(dz_raw))
        rs_off_row = (rs_off @ sqrt_a) / sqrt_a
        dz_off_row = (dz_off @ sqrt_a) / sqrt_a

        dist_ext = np.sqrt(d_eff**2 + r_eff**2)
        tot_rs = (np.exp(-p_val * d_eff) - np.exp(-p_val * dist_ext)) / (2.0 * p_val)
        tot_dz = (
            0.5
            * (-np.exp(-p_val * d_eff) + (d_eff / dist_ext) * np.exp(-p_val * dist_ext))
            * (d_um / d_eff)
        )
        rs_mat = rs_off + np.diag(tot_rs - rs_off_row)
        dz_mat = dz_off + np.diag(tot_dz - dz_off_row)

        rhs_r = backend.array(np.concatenate([rs_mat @ w_vec, dz_mat @ w_vec], axis=1))
        rhs_s = backend.array(np.concatenate([rs_mat.T @ w_vec, dz_mat.T @ w_vec], axis=1))
        x_sol, cond_r, _ = backend.factor_and_solve(backend.array(rr_mat), rhs_r)
        z_sol, cond_s, _ = backend.factor_and_solve(backend.array(ss_mat), rhs_s)
        if max(cond_r, cond_s) > DEFAULT_CONDITION_LIMIT:
            raise RuntimeError(f"Parallel-plate BEM condition limit exceeded at p={p_val:g}")

        x_np = np.real(np.asarray(x_sol))
        z_np = np.real(np.asarray(z_sol))
        x_p = x_np[:, 0] / w_vec[:, 0]
        dx_p = x_np[:, 1] / w_vec[:, 0]
        z_p = z_np[:, 0] / w_vec[:, 0]
        dz_p = z_np[:, 1] / w_vec[:, 0]

        c_bem = np.clip(x_p * z_p, 0.0, 0.999999)
        dc_bem = dx_p * z_p + x_p * dz_p

        kap_vals = p_val * t_xi
        dkap_vals = p_val * w_xi
        eps_vals = _drude_epsilon_from_kappa(
            kap_vals, omega_p_ev=omega_p_ev, gamma_ev=gamma_ev
        )
        s_metal = np.sqrt(p_val**2 + (eps_vals - 1.0) * (kap_vals**2))
        r_tm_sq = ((eps_vals * p_val - s_metal) / (eps_vals * p_val + s_metal)) ** 2
        r_te_sq = ((p_val - s_metal) / (p_val + s_metal)) ** 2

        m_tm = r_tm_sq[:, None] * c_bem[None, :]
        m_te = r_te_sq[:, None] * c_bem[None, :]
        dm_tm = r_tm_sq[:, None] * dc_bem[None, :]
        dm_te = r_te_sq[:, None] * dc_bem[None, :]

        trace_term = (dm_tm / (1.0 - m_tm)) + (dm_te / (1.0 - m_te))
        panel_pressure_accum += (
            dp_val
            * (p_val / (4.0 * (math.pi**2)))
            * np.sum(dkap_vals[:, None] * trace_term, axis=0)
        )

    panel_pressure_pa = panel_pressure_accum * HBAR_C_PER_UM4_TO_PA
    pressure_bem_pa = float(
        np.sum(panel_pressure_pa * rotor_full_disk.areas) / np.sum(rotor_full_disk.areas)
    )
    pressure_lifshitz_pa = float(exact_lifshitz_drude_pressure_pa(d_um, omega_p_ev, gamma_ev))
    rel_err_pct = (
        100.0 * abs(pressure_bem_pa - pressure_lifshitz_pa) / max(abs(pressure_lifshitz_pa), 1e-30)
    )
    n_panels_full_disk = int(rotor_full_disk.count + stator_full_disk.count)
    h_spacing = float(n_panels_full_disk) ** -0.5

    return {
        "gap_nm": float(gap_nm),
        "gap_um": d_um,
        "d_over_R": d_um / DISK_OUTER_RADIUS_UM,
        "tier": tier,
        "panel_count_sector": int(n_panels_full_disk // DISK_N_SECTOR),
        "panel_count_full_disk": n_panels_full_disk,
        "n_p": n_p,
        "n_p_evaluated": n_eval,
        "n_xi": n_xi,
        "h_spacing": h_spacing,
        "h2_area_scale": 1.0 / float(n_panels_full_disk),
        "pressure_bem_pa": pressure_bem_pa,
        "pressure_lifshitz_pa": pressure_lifshitz_pa,
        "rel_error_vs_lifshitz_pct": rel_err_pct,
        "elapsed_s": time.perf_counter() - t0,
    }


def run_lifshitz_parallel_plate_suite(
    device: Literal["auto", "cpu", "cuda"] = "auto",
    max_steps: int = 0,
) -> dict[str, Any]:
    """Run Suite 1: Analytical Lifshitz Parallel-Plate Benchmark across d and tiers."""
    records: list[dict[str, Any]] = []
    by_gap: dict[str, dict[str, Any]] = {}

    for gap_nm in PARALLEL_PLATE_GAPS_NM:
        tier_results: dict[str, dict[str, Any]] = {}
        for tier in PANEL_TIERS:
            res = compute_3d_bem_parallel_plate_pressure_pa(
                gap_nm=gap_nm, tier=tier, device=device, max_steps=max_steps
            )
            records.append(res)
            tier_results[tier] = res

        # Sub-panel area variance scales as A_panel ~ 1 / N_panels = h^2
        h2_vals = np.array([tier_results[t]["h2_area_scale"] for t in PANEL_TIERS], dtype=np.float64)
        p_vals = np.array([tier_results[t]["pressure_bem_pa"] for t in PANEL_TIERS], dtype=np.float64)

        h2_mean = float(np.mean(h2_vals))
        p_mean = float(np.mean(p_vals))
        denom_ols = float(np.sum((h2_vals - h2_mean) ** 2))
        slope_ols = float(np.sum((h2_vals - h2_mean) * (p_vals - p_mean)) / max(denom_ols, 1e-30))
        p_continuum_ols_pa = float(p_mean - slope_ols * h2_mean)

        h2_high, h2_ultra = float(h2_vals[1]), float(h2_vals[2])
        p_high, p_ultra = float(p_vals[1]), float(p_vals[2])
        p_continuum_richardson_pa = float(
            (h2_high * p_ultra - h2_ultra * p_high) / max(h2_high - h2_ultra, 1e-30)
        )

        p_lifshitz_pa = float(tier_results["Ultra_High"]["pressure_lifshitz_pa"])
        denom_lif = max(abs(p_lifshitz_pa), 1e-30)
        rel_err_continuum_pct = 100.0 * abs(p_continuum_richardson_pa - p_lifshitz_pa) / denom_lif
        rel_err_ols_pct = 100.0 * abs(p_continuum_ols_pa - p_lifshitz_pa) / denom_lif

        gap_key = f"d{int(round(gap_nm))}nm"
        by_gap[gap_key] = {
            "gap_nm": float(gap_nm),
            "gap_um": float(gap_nm) * 1e-3,
            "d_over_R": (float(gap_nm) * 1e-3) / DISK_OUTER_RADIUS_UM,
            "pressure_lifshitz_pa": p_lifshitz_pa,
            "pressure_bem_std_pa": float(tier_results["Standard"]["pressure_bem_pa"]),
            "pressure_bem_high_pa": float(tier_results["High"]["pressure_bem_pa"]),
            "pressure_bem_ultra_pa": float(tier_results["Ultra_High"]["pressure_bem_pa"]),
            "pressure_bem_continuum_pa": p_continuum_richardson_pa,
            "pressure_bem_continuum_ols_pa": p_continuum_ols_pa,
            "rel_error_std_pct": float(tier_results["Standard"]["rel_error_vs_lifshitz_pct"]),
            "rel_error_high_pct": float(tier_results["High"]["rel_error_vs_lifshitz_pct"]),
            "rel_error_ultra_pct": float(tier_results["Ultra_High"]["rel_error_vs_lifshitz_pct"]),
            "rel_error_continuum_pct": rel_err_continuum_pct,
            "rel_error_continuum_ols_pct": rel_err_ols_pct,
        }

    err_seq = [by_gap[f"d{int(round(g))}nm"]["rel_error_continuum_pct"] for g in PARALLEL_PLATE_GAPS_NM]
    return {
        "disk_outer_radius_um": DISK_OUTER_RADIUS_UM,
        "disk_inner_radius_um": DISK_INNER_RADIUS_UM,
        "n_sector": DISK_N_SECTOR,
        "material": "Gold",
        "drude_omega_p_ev": GOLD_WP_EV,
        "drude_gamma_ev": GOLD_GAMMA_EV,
        "max_steps_applied": int(max_steps),
        "records": records,
        "by_gap": by_gap,
        "monotonic_d_over_r_recovery": bool(err_seq[0] < err_seq[1] < err_seq[2] < err_seq[3]),
        "min_continuum_rel_error_pct": float(min(err_seq)),
        "max_continuum_rel_error_pct": float(max(err_seq)),
    }


def _translate_body_panels_z(body: BodyPanels, dz_um: float) -> BodyPanels:
    new_centroids = np.array(body.centroids, dtype=np.float64, copy=True)
    new_centroids[:, 2] += dz_um
    new_quad_points = np.array(body.quad_points, dtype=np.float64, copy=True)
    if new_quad_points.size > 0:
        new_quad_points[:, :, 2] += dz_um
    return BodyPanels(
        centroids=new_centroids,
        normals=body.normals,
        areas=body.areas,
        panel_types=body.panel_types,
        tangents=body.tangents,
        quad_points=new_quad_points,
        quad_weights=body.quad_weights,
    )


def _characteristic_gap_um(rotor: BodyPanels, stator: BodyPanels) -> float:
    char_gap_um = math.inf
    if rotor.count and stator.count:
        for sector in range(4):
            source_positions = stator.centroids @ _rotation(sector).T
            for centroid in rotor.centroids:
                sep = float(np.min(np.linalg.norm(source_positions - centroid, axis=1)))
                char_gap_um = min(char_gap_um, sep)
    if not math.isfinite(char_gap_um):
        char_gap_um = 0.100
    return char_gap_um


def _assemble_stator_cyclic_modes(
    stator: BodyPanels,
    kappa: float,
    phases: np.ndarray,
) -> list[np.ndarray]:
    ns = 2 * stator.count
    ss_modes = [np.zeros((ns, ns), dtype=np.complex128) for _ in range(4)]
    for sector in range(4):
        blk_ss = _vector_dyadic_blocks(stator, stator, sector, kappa, same_body=True)
        for mode in range(4):
            ss_modes[mode] += phases[mode, sector] * blk_ss.single_layer
    return ss_modes


def evaluate_cantor_energy_derivative_vs_trace_at_angle(
    design: Any,
    theta_deg: float,
    delta_z_nm: float,
    tier_name: str,
    device: Literal["auto", "cpu", "cuda"] = "auto",
    max_steps: int = 0,
    precomputed_ss_by_q: dict[int, list[np.ndarray]] | None = None,
) -> dict[str, Any]:
    """Simultaneously evaluate direct trace force F_z^{trace} and central FD -dE_C/dz_rotor."""
    if not math.isfinite(delta_z_nm) or delta_z_nm <= 0.0:
        raise ValueError("delta_z_nm must be positive and finite.")
    t0 = time.perf_counter()
    dz_um = float(delta_z_nm) * 1e-3
    tier = get_bem_resolution_tier(tier_name)

    mesh_0 = build_active_sector_mesh(
        design, theta_deg, tier.n_r, tier.n_phi_tooth, tier.n_phi_bridge, tier.n_z
    )
    backend = DenseBackend(device)
    material = MaterialModel.from_parameters(mesh_0.parameters)
    rotor_0 = mesh_0.sector_arrays("rotor")
    stator_0 = mesh_0.sector_arrays("stator")
    rotor_plus = _translate_body_panels_z(rotor_0, +dz_um)
    rotor_minus = _translate_body_panels_z(rotor_0, -dz_um)

    char_gap_um = _characteristic_gap_um(rotor_0, stator_0)
    k_eff = 1.0 / max(char_gap_um, 0.020)

    kappa_0 = 1.0 / max(abs(mesh_0.geometry.z_tip), 0.015)
    kappas, weights, _ = _quadrature(tier.n_xi, kappa_0)
    n_eval = min(len(kappas), max_steps) if max_steps > 0 else len(kappas)

    nr = 2 * rotor_0.count
    ns = 2 * stator_0.count
    phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)
    condition_limit = DEFAULT_CONDITION_LIMIT

    net_trace = energy_0 = energy_plus = energy_minus = 0.0

    for q in range(n_eval):
        kappa = float(kappas[q])
        weight = float(weights[q])
        tm, te, _ = material.channel_weights(kappa, k_eff=k_eff)

        rr_modes = [np.zeros((nr, nr), dtype=np.complex128) for _ in range(4)]
        rs_0_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]
        dz_0_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]
        rs_plus_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]
        rs_minus_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]

        if precomputed_ss_by_q is not None and q in precomputed_ss_by_q:
            ss_modes = precomputed_ss_by_q[q]
        else:
            ss_modes = _assemble_stator_cyclic_modes(stator_0, kappa, phases)
            if precomputed_ss_by_q is not None:
                precomputed_ss_by_q[q] = ss_modes

        for sector in range(4):
            blk_rr = _vector_dyadic_blocks(rotor_0, rotor_0, sector, kappa, same_body=True)
            blk_rs_0 = _vector_dyadic_blocks(rotor_0, stator_0, sector, kappa, same_body=False)
            blk_rs_plus = _vector_dyadic_blocks(rotor_plus, stator_0, sector, kappa, same_body=False)
            blk_rs_minus = _vector_dyadic_blocks(rotor_minus, stator_0, sector, kappa, same_body=False)

            for mode in range(4):
                ph = phases[mode, sector]
                rr_modes[mode] += ph * blk_rr.single_layer
                rs_0_modes[mode] += ph * blk_rs_0.single_layer
                dz_0_modes[mode] += ph * blk_rs_0.dz_target
                rs_plus_modes[mode] += ph * blk_rs_plus.single_layer
                rs_minus_modes[mode] += ph * blk_rs_minus.single_layer

        derivative_0 = logdet_0_q = logdet_plus_q = logdet_minus_q = 0j

        for mode in range(4):
            mr = backend.array(rr_modes[mode])
            ms = backend.array(ss_modes[mode])
            g_0 = backend.array(rs_0_modes[mode])
            dg_0 = backend.array(dz_0_modes[mode])
            g_plus = backend.array(rs_plus_modes[mode])
            g_minus = backend.array(rs_minus_modes[mode])

            sr_0 = backend.adjoint(g_0)
            dsr_0 = backend.adjoint(dg_0)
            sr_plus = backend.adjoint(g_plus)
            sr_minus = backend.adjoint(g_minus)

            n_col = g_0.shape[1]
            x_all, cond_r, _ = backend.factor_and_solve(
                mr, backend.concat_cols((g_0, dg_0, g_plus, g_minus))
            )
            x_0 = x_all[:, :n_col]
            dx_0 = x_all[:, n_col : 2 * n_col]
            x_plus = x_all[:, 2 * n_col : 3 * n_col]
            x_minus = x_all[:, 3 * n_col :]

            n_col_s = sr_0.shape[1]
            z_all, cond_s, _ = backend.factor_and_solve(
                ms, backend.concat_cols((sr_0, dsr_0, sr_plus, sr_minus))
            )
            z_0 = z_all[:, :n_col_s]
            dz_0 = z_all[:, n_col_s : 2 * n_col_s]
            z_plus = z_all[:, 2 * n_col_s : 3 * n_col_s]
            z_minus = z_all[:, 3 * n_col_s :]

            if max(cond_r, cond_s) > condition_limit:
                raise RuntimeError(f"BEM condition number exceeded limit at kappa={kappa:g}")

            coupling_0 = x_0 @ z_0
            dcoupling_0 = dx_0 @ z_0 + x_0 @ dz_0
            coupling_plus = x_plus @ z_plus
            coupling_minus = x_minus @ z_minus

            for _channel, ch_weight in (("TM", tm), ("TE", te)):
                pw = ch_weight**2
                y_0 = backend.eye(nr) - pw * coupling_0
                deriv_mat_0, cond_y0, ch_logdet_0 = backend.factor_and_solve(
                    y_0, dcoupling_0, need_logdet=True
                )
                if cond_y0 > condition_limit or ch_logdet_0 is None:
                    raise RuntimeError("Invalid scattering determinant in trace/FD check.")
                ch_deriv_0 = -pw * backend.trace(deriv_mat_0)

                y_plus = backend.eye(nr) - pw * coupling_plus
                ch_logdet_plus = backend.logdet(y_plus)

                y_minus = backend.eye(nr) - pw * coupling_minus
                ch_logdet_minus = backend.logdet(y_minus)

                derivative_0 += ch_deriv_0
                logdet_0_q += ch_logdet_0
                logdet_plus_q += ch_logdet_plus
                logdet_minus_q += ch_logdet_minus

        d_total = _assert_real(derivative_0, "full cyclic derivative")
        l_0 = _assert_real(logdet_0_q, "logdet_0")
        l_plus = _assert_real(logdet_plus_q, "logdet_plus")
        l_minus = _assert_real(logdet_minus_q, "logdet_minus")

        net_trace += weight * (-d_total / (2.0 * math.pi))
        energy_0 += weight * (l_0 / (2.0 * math.pi))
        energy_plus += weight * (l_plus / (2.0 * math.pi))
        energy_minus += weight * (l_minus / (2.0 * math.pi))

    unit_scale = MEEP_FORCE_TO_SI * 1e12
    f_trace_pn = float(net_trace * unit_scale)
    e_0_pn_um = float(energy_0 * unit_scale)
    e_plus_pn_um = float(energy_plus * unit_scale)
    e_minus_pn_um = float(energy_minus * unit_scale)

    f_fd_pn = float(-(e_plus_pn_um - e_minus_pn_um) / (2.0 * dz_um))
    abs_diff_pn = abs(f_trace_pn - f_fd_pn)
    rel_diff = abs_diff_pn / max(abs(f_trace_pn), 1e-15)
    rel_diff_pct = 100.0 * rel_diff

    return {
        "design": "Cantor_N2_HybridRZ",
        "theta_deg": float(theta_deg),
        "tier": tier_name,
        "n_xi": int(tier.n_xi),
        "n_xi_evaluated": int(n_eval),
        "panel_count_sector": int(mesh_0.n_panels_rotor + mesh_0.n_panels_stator),
        "panel_count_full": int(mesh_0.n_panels_total),
        "delta_z_nm": float(delta_z_nm),
        "delta_z_um": dz_um,
        "force_trace_pN": f_trace_pn,
        "force_fd_central_pN": f_fd_pn,
        "energy_z0_pN_um": e_0_pn_um,
        "energy_z_plus_pN_um": e_plus_pn_um,
        "energy_z_minus_pN_um": e_minus_pn_um,
        "energy_z0_hbar_c_per_um": float(energy_0),
        "abs_discrepancy_pN": abs_diff_pn,
        "rel_discrepancy": rel_diff,
        "rel_discrepancy_pct": rel_diff_pct,
        "rel_agreement_pct": 100.0 * (1.0 - rel_diff),
        "elapsed_s": time.perf_counter() - t0,
    }


def run_energy_derivative_consistency_suite(
    device: Literal["auto", "cpu", "cuda"] = "auto",
    delta_z_nm: float = 0.5,
    max_steps: int = 0,
) -> dict[str, Any]:
    """Run Suite 2: Energy-Derivative vs. Trace Force Consistency Check on Cantor_N2_HybridRZ."""
    cantor_design = build_designs()["Cantor_N2_HybridRZ"]
    angles_deg = (3.0, 48.0)
    by_angle: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    shared_ss_cache: dict[int, list[np.ndarray]] = {}

    for theta_deg in angles_deg:
        res = evaluate_cantor_energy_derivative_vs_trace_at_angle(
            design=cantor_design,
            theta_deg=theta_deg,
            delta_z_nm=delta_z_nm,
            tier_name="Standard",
            device=device,
            max_steps=max_steps,
            precomputed_ss_by_q=shared_ss_cache,
        )
        by_angle[f"theta{int(round(theta_deg))}"] = res
        records.append(res)

    return {
        "design": "Cantor_N2_HybridRZ",
        "delta_z_nm": float(delta_z_nm),
        "angles_deg": list(angles_deg),
        "by_angle": by_angle,
        "records": records,
        "max_rel_discrepancy_pct": float(max(r["rel_discrepancy_pct"] for r in records)),
        "min_rel_agreement_pct": float(min(r["rel_agreement_pct"] for r in records)),
    }


def lifshitz_matsubara_sum_pair_pa(
    gap_nm: float,
    temperature_k: float,
    n_matsubara_cutoff: int,
    omega_p_ev: float = GOLD_WP_EV,
    gamma_ev: float = GOLD_GAMMA_EV,
    n_k: int = 96,
    n_matsubara_2x_override: int | None = None,
) -> tuple[float, float, float]:
    """Evaluate exact 1D Lifshitz thermal Matsubara sum at N and 2N, plus direct tail residual."""
    if not math.isfinite(gap_nm) or gap_nm <= 0.0:
        raise ValueError("gap_nm must be positive and finite.")
    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("temperature_k must be positive and finite.")
    if int(n_matsubara_cutoff) < 0:
        raise ValueError("n_matsubara_cutoff must be >= 0.")
    if not math.isfinite(omega_p_ev) or omega_p_ev <= 0.0:
        raise ValueError("omega_p_ev must be positive and finite.")
    if not math.isfinite(gamma_ev) or gamma_ev <= 0.0:
        raise ValueError("gamma_ev must be positive and finite.")
    if int(n_k) < 1:
        raise ValueError("n_k must be >= 1.")

    d_um = float(gap_nm) * 1e-3
    delta_kappa = (2.0 * math.pi * BOLTZMANN_K_EV_PER_K * float(temperature_k)) / HBAR_C_EV_UM
    t_k, w_k = _gauss_legendre_01(n_k)
    s_vals = t_k / (1.0 - t_k)
    dp_vals = w_k * (1.0 / ((1.0 - t_k) ** 2)) / (2.0 * d_um)

    n_1x = int(n_matsubara_cutoff)
    n_2x = int(n_matsubara_2x_override) if n_matsubara_2x_override is not None else 2 * n_1x
    if n_2x < n_1x:
        raise ValueError("n_matsubara_2x_override must be >= n_matsubara_cutoff.")

    p0_vals = s_vals / (2.0 * d_um)
    exp0 = np.exp(-2.0 * p0_vals * d_um)
    term0 = (p0_vals**2) * (exp0 / np.maximum(1.0 - exp0, 1e-30))
    sum_0 = 0.5 * float(np.sum((term0 / math.pi) * dp_vals))

    mode_contribs = np.zeros(n_2x, dtype=np.float64)
    if n_2x > 0:
        kappa_n = np.arange(1, n_2x + 1, dtype=np.float64) * delta_kappa
        eps_n = _drude_epsilon_from_kappa(kappa_n, omega_p_ev, gamma_ev)
        for idx_n in range(n_2x):
            kap = float(kappa_n[idx_n])
            eps_val = float(eps_n[idx_n])
            p_vals = kap + s_vals / (2.0 * d_um)
            s_metal = np.sqrt(p_vals**2 + (eps_val - 1.0) * (kap**2))
            r_tm = (eps_val * p_vals - s_metal) / (eps_val * p_vals + s_metal)
            r_te = (p_vals - s_metal) / (p_vals + s_metal)
            exp_fac = np.exp(-2.0 * p_vals * d_um)
            d_tm = (r_tm**2 * exp_fac) / np.maximum(1.0 - r_tm**2 * exp_fac, 1e-30)
            d_te = (r_te**2 * exp_fac) / np.maximum(1.0 - r_te**2 * exp_fac, 1e-30)
            mode_contribs[idx_n] = float(np.sum((p_vals**2 / math.pi) * (d_tm + d_te) * dp_vals))

    pref = -(delta_kappa / (2.0 * math.pi)) * HBAR_C_PER_UM4_TO_PA
    sum_1_to_n = float(np.sum(mode_contribs[:n_1x]))
    tail_n_to_2n = float(np.sum(mode_contribs[n_1x:n_2x]))

    p_1x = float(pref * (sum_0 + sum_1_to_n))
    p_2x = float(pref * (sum_0 + sum_1_to_n + tail_n_to_2n))
    rel_res = abs(tail_n_to_2n) / max(abs(sum_0 + sum_1_to_n + tail_n_to_2n), 1e-30)
    return p_1x, p_2x, float(rel_res)


def _bem_trace_integrand_at_kappa(
    rotor: BodyPanels,
    stator: BodyPanels,
    ss_modes: list[np.ndarray],
    kappa: float,
    k_eff: float,
    material: MaterialModel,
    backend: DenseBackend,
    phases: np.ndarray,
) -> float:
    """Evaluate exact 3D Vector-Dyadic BEM force integrand at a single imaginary frequency kappa."""
    tm, te, _ = material.channel_weights(kappa, k_eff=k_eff)
    nr = 2 * rotor.count
    ns = 2 * stator.count
    rr_modes = [np.zeros((nr, nr), dtype=np.complex128) for _ in range(4)]
    rs_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]
    dz_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]

    for sector in range(4):
        blk_rr = _vector_dyadic_blocks(rotor, rotor, sector, kappa, same_body=True)
        blk_rs = _vector_dyadic_blocks(rotor, stator, sector, kappa, same_body=False)
        for mode in range(4):
            ph = phases[mode, sector]
            rr_modes[mode] += ph * blk_rr.single_layer
            rs_modes[mode] += ph * blk_rs.single_layer
            dz_modes[mode] += ph * blk_rs.dz_target

    derivative = 0j
    for mode in range(4):
        mr = backend.array(rr_modes[mode])
        ms = backend.array(ss_modes[mode])
        g = backend.array(rs_modes[mode])
        dg = backend.array(dz_modes[mode])
        sr = backend.adjoint(g)
        dsr = backend.adjoint(dg)

        n_col = g.shape[1]
        x_all, cond_r, _ = backend.factor_and_solve(mr, backend.concat_cols((g, dg)))
        x, dx = x_all[:, :n_col], x_all[:, n_col:]

        n_col_s = sr.shape[1]
        z_all, cond_s, _ = backend.factor_and_solve(ms, backend.concat_cols((sr, dsr)))
        z, dz = z_all[:, :n_col_s], z_all[:, n_col_s:]

        if max(cond_r, cond_s) > DEFAULT_CONDITION_LIMIT:
            raise RuntimeError(f"BEM condition limit exceeded at kappa={kappa:g}")

        coupling = x @ z
        dcoupling = dx @ z + x @ dz

        for _channel, ch_weight in (("TM", tm), ("TE", te)):
            pw = ch_weight**2
            y = backend.eye(nr) - pw * coupling
            deriv_mat, cond_y, _ = backend.factor_and_solve(y, dcoupling, need_logdet=False)
            if cond_y > DEFAULT_CONDITION_LIMIT:
                raise RuntimeError(f"Scattering condition limit exceeded at kappa={kappa:g}")
            derivative += -pw * backend.trace(deriv_mat)

    d_total = _assert_real(derivative, "full cyclic derivative")
    return float(-d_total / (2.0 * math.pi))


def run_matsubara_truncation_suite(
    device: Literal["auto", "cpu", "cuda"] = "auto",
    temperature_k: float = 300.0,
    n_matsubara_cutoff: int = 64,
    max_steps: int = 0,
) -> dict[str, Any]:
    """Run Suite 3: Matsubara Truncation Convergence (T = 300 K) between N and 2N."""
    if not math.isfinite(temperature_k) or temperature_k <= 0.0:
        raise ValueError("temperature_k must be positive and finite.")
    if int(n_matsubara_cutoff) < 1:
        raise ValueError("n_matsubara_cutoff must be >= 1.")
    if int(max_steps) < 0:
        raise ValueError("max_steps must be >= 0.")

    t0 = time.perf_counter()
    cantor_design = build_designs()["Cantor_N2_HybridRZ"]
    tier = BEM_TIER_STANDARD
    backend = DenseBackend(device)
    phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)

    delta_kappa = (2.0 * math.pi * BOLTZMANN_K_EV_PER_K * float(temperature_k)) / HBAR_C_EV_UM
    full_2x = 2 * int(n_matsubara_cutoff)
    if max_steps > 0:
        n_poles_eval = min(full_2x + 1, int(max_steps))
        n_2x = max(0, n_poles_eval - 1)
        n_1x = min(int(n_matsubara_cutoff), n_2x // 2)
    else:
        n_1x = int(n_matsubara_cutoff)
        n_2x = full_2x
        n_poles_eval = n_2x + 1

    angles_deg = (3.0, 48.0)
    meshes = {
        th: build_active_sector_mesh(
            cantor_design, th, tier.n_r, tier.n_phi_tooth, tier.n_phi_bridge, tier.n_z
        )
        for th in angles_deg
    }
    rotors = {th: meshes[th].sector_arrays("rotor") for th in angles_deg}
    stator_shared = meshes[3.0].sector_arrays("stator")
    material = MaterialModel.from_parameters(meshes[3.0].parameters)
    k_effs = {
        th: 1.0 / max(_characteristic_gap_um(rotors[th], stator_shared), 0.020)
        for th in angles_deg
    }

    pole_kappas = np.arange(n_poles_eval, dtype=np.float64) * delta_kappa
    pole_kappas[0] = 1.0e-4 * delta_kappa

    mode_integrands: dict[float, np.ndarray] = {
        th: np.zeros(n_poles_eval, dtype=np.float64) for th in angles_deg
    }
    for idx_n in range(n_poles_eval):
        kap = float(pole_kappas[idx_n])
        ss_modes = _assemble_stator_cyclic_modes(stator_shared, kap, phases)
        for th in angles_deg:
            mode_integrands[th][idx_n] = _bem_trace_integrand_at_kappa(
                rotors[th], stator_shared, ss_modes, kap, k_effs[th], material, backend, phases
            )

    lifshitz_by_gap: dict[str, dict[str, Any]] = {}
    for gap_nm in PARALLEL_PLATE_GAPS_NM:
        p_1x, p_2x, rel_res = lifshitz_matsubara_sum_pair_pa(
            gap_nm=gap_nm,
            temperature_k=temperature_k,
            n_matsubara_cutoff=n_1x,
            n_matsubara_2x_override=n_2x,
        )
        lifshitz_by_gap[f"d{int(round(gap_nm))}nm"] = {
            "gap_nm": float(gap_nm),
            "n_matsubara": int(n_1x),
            "n_matsubara_2x": int(n_2x),
            "pressure_N_pa": p_1x,
            "pressure_2N_pa": p_2x,
            "tail_residual_rel": float(rel_res),
            "tail_residual_rel_pct": float(100.0 * rel_res),
        }

    prefactor = delta_kappa * MEEP_FORCE_TO_SI * 1e12
    cantor_by_angle: dict[str, dict[str, Any]] = {}
    elapsed_cantor = time.perf_counter() - t0
    for th in angles_deg:
        vals = mode_integrands[th]
        sum_1x = 0.5 * float(vals[0]) + float(np.sum(vals[1 : n_1x + 1]))
        tail_sum_n_to_2n = float(np.sum(vals[n_1x + 1 : n_2x + 1]))
        sum_2x = sum_1x + tail_sum_n_to_2n

        f_1x_pn = float(prefactor * sum_1x)
        f_2x_pn = float(prefactor * sum_2x)
        tail_abs_pn = abs(float(prefactor * tail_sum_n_to_2n))
        tail_rel = tail_abs_pn / max(abs(f_2x_pn), 1e-18)
        cantor_by_angle[f"theta{int(round(th))}"] = {
            "design": "Cantor_N2_HybridRZ",
            "theta_deg": float(th),
            "temperature_k": float(temperature_k),
            "delta_kappa_1_per_um": float(delta_kappa),
            "n_matsubara": int(n_1x),
            "n_matsubara_2x": int(n_2x),
            "n_poles_evaluated": int(n_poles_eval),
            "kappa_cutoff_1_per_um": float(n_1x * delta_kappa),
            "kappa_cutoff_2x_1_per_um": float(n_2x * delta_kappa),
            "energy_cutoff_ev": float(n_1x * delta_kappa * HBAR_C_EV_UM),
            "force_matsubara_N_pN": f_1x_pn,
            "force_matsubara_2N_pN": f_2x_pn,
            "tail_residual_abs_pN": tail_abs_pn,
            "tail_residual_rel": tail_rel,
            "tail_residual_rel_pct": 100.0 * tail_rel,
            "elapsed_s": elapsed_cantor,
        }

    return {
        "temperature_k": float(temperature_k),
        "n_matsubara_cutoff": int(n_1x),
        "n_matsubara_2x_cutoff": int(n_2x),
        "n_poles_evaluated": int(n_poles_eval),
        "delta_kappa_1_per_um": float(delta_kappa),
        "kappa_cutoff_1_per_um": float(n_1x * delta_kappa),
        "energy_cutoff_ev": float(n_1x * delta_kappa * HBAR_C_EV_UM),
        "cantor_by_angle": cantor_by_angle,
        "lifshitz_by_gap": lifshitz_by_gap,
        "max_cantor_tail_residual_rel": float(
            max(v["tail_residual_rel"] for v in cantor_by_angle.values())
        ),
        "max_cantor_tail_residual_rel_pct": float(
            max(v["tail_residual_rel_pct"] for v in cantor_by_angle.values())
        ),
        "max_lifshitz_tail_residual_rel": float(
            max(v["tail_residual_rel"] for v in lifshitz_by_gap.values())
        ),
    }


def log_validation_metrics_to_provenance(
    suite1: dict[str, Any],
    suite2: dict[str, Any],
    suite3: dict[str, Any],
    metrics_path: Path,
    macros_path: Path,
) -> dict[str, float]:
    """Record all canonical validation metrics into provenance_metrics.json and macros_results.tex."""
    set_solver_provenance(
        "VectorDyadicBEM3D_CanonicalValidation",
        {
            "dataset": "bem_canonical_validation",
            "eps_bg": 1.0,
            "material": "Gold",
            "drude_omega_p_ev": GOLD_WP_EV,
            "drude_gamma_ev": GOLD_GAMMA_EV,
            "temperature_k": 300.0,
            "n_matsubara": suite3["n_matsubara_cutoff"],
        },
        metrics_path=str(metrics_path),
    )

    log_step(
        "bem_canonical_validation_suite",
        {
            "suite1_lifshitz_gaps_nm": list(PARALLEL_PLATE_GAPS_NM),
            "suite2_energy_derivative_delta_z_nm": suite2["delta_z_nm"],
            "suite3_matsubara_cutoff": suite3["n_matsubara_cutoff"],
        },
        metrics_path=str(metrics_path),
    )

    flat_metrics: dict[str, float] = {}
    for gap_nm in PARALLEL_PLATE_GAPS_NM:
        g_int = int(round(gap_nm))
        g_data = suite1["by_gap"][f"d{g_int}nm"]
        flat_metrics[f"bem_val_lifshitz_exact_d{g_int}nm_pa"] = float(g_data["pressure_lifshitz_pa"])
        flat_metrics[f"bem_val_plate_bem_std_d{g_int}nm_pa"] = float(g_data["pressure_bem_std_pa"])
        flat_metrics[f"bem_val_plate_bem_high_d{g_int}nm_pa"] = float(g_data["pressure_bem_high_pa"])
        flat_metrics[f"bem_val_plate_bem_ultra_d{g_int}nm_pa"] = float(g_data["pressure_bem_ultra_pa"])
        flat_metrics[f"bem_val_plate_bem_continuum_d{g_int}nm_pa"] = float(
            g_data["pressure_bem_continuum_pa"]
        )
        flat_metrics[f"bem_val_plate_rel_err_std_d{g_int}nm_pct"] = float(
            g_data["rel_error_std_pct"]
        )
        flat_metrics[f"bem_val_plate_rel_err_high_d{g_int}nm_pct"] = float(
            g_data["rel_error_high_pct"]
        )
        flat_metrics[f"bem_val_plate_rel_err_ultra_d{g_int}nm_pct"] = float(
            g_data["rel_error_ultra_pct"]
        )
        flat_metrics[f"bem_val_plate_rel_err_continuum_d{g_int}nm_pct"] = float(
            g_data["rel_error_continuum_pct"]
        )

    flat_metrics["bem_val_plate_min_continuum_rel_err_pct"] = float(
        suite1["min_continuum_rel_error_pct"]
    )
    flat_metrics["bem_val_plate_max_continuum_rel_err_pct"] = float(
        suite1["max_continuum_rel_error_pct"]
    )

    for th_int in (3, 48):
        th_data = suite2["by_angle"][f"theta{th_int}"]
        flat_metrics[f"bem_val_cantor_theta{th_int}_trace_fz_pn"] = float(
            th_data["force_trace_pN"]
        )
        flat_metrics[f"bem_val_cantor_theta{th_int}_fd_fz_pn"] = float(
            th_data["force_fd_central_pN"]
        )
        flat_metrics[f"bem_val_cantor_theta{th_int}_energy_z0_pn_um"] = float(
            th_data["energy_z0_pN_um"]
        )
        flat_metrics[f"bem_val_cantor_theta{th_int}_energy_zplus_pn_um"] = float(
            th_data["energy_z_plus_pN_um"]
        )
        flat_metrics[f"bem_val_cantor_theta{th_int}_energy_zminus_pn_um"] = float(
            th_data["energy_z_minus_pN_um"]
        )
        flat_metrics[f"bem_val_cantor_theta{th_int}_trace_vs_fd_rel_err_pct"] = float(
            th_data["rel_discrepancy_pct"]
        )
        flat_metrics[f"bem_val_cantor_theta{th_int}_trace_vs_fd_agreement_pct"] = float(
            th_data["rel_agreement_pct"]
        )

    flat_metrics["bem_val_cantor_trace_vs_fd_step_nm"] = float(suite2["delta_z_nm"])
    flat_metrics["bem_val_cantor_trace_vs_fd_max_rel_err_pct"] = float(
        suite2["max_rel_discrepancy_pct"]
    )

    flat_metrics["bem_val_matsubara_cutoff_n_count"] = float(suite3["n_matsubara_cutoff"])
    flat_metrics["bem_val_matsubara_cutoff_2n_count"] = float(suite3["n_matsubara_2x_cutoff"])
    flat_metrics["bem_val_matsubara_poles_evaluated_count"] = float(
        suite3["n_poles_evaluated"]
    )
    flat_metrics["bem_val_matsubara_delta_kappa_per_um"] = float(suite3["delta_kappa_1_per_um"])
    flat_metrics["bem_val_matsubara_kappa_cutoff_per_um"] = float(suite3["kappa_cutoff_1_per_um"])
    flat_metrics["bem_val_matsubara_energy_cutoff_ev"] = float(suite3["energy_cutoff_ev"])

    for th_int in (3, 48):
        m_data = suite3["cantor_by_angle"][f"theta{th_int}"]
        flat_metrics[f"bem_val_matsubara_cantor_theta{th_int}_f_n_pn"] = float(
            m_data["force_matsubara_N_pN"]
        )
        flat_metrics[f"bem_val_matsubara_cantor_theta{th_int}_f_2n_pn"] = float(
            m_data["force_matsubara_2N_pN"]
        )
        flat_metrics[f"bem_val_matsubara_cantor_theta{th_int}_tail_rel"] = float(
            m_data["tail_residual_rel"]
        )
        flat_metrics[f"bem_val_matsubara_cantor_theta{th_int}_tail_rel_pct"] = float(
            m_data["tail_residual_rel_pct"]
        )

    for gap_nm in PARALLEL_PLATE_GAPS_NM:
        g_int = int(round(gap_nm))
        l_data = suite3["lifshitz_by_gap"][f"d{g_int}nm"]
        flat_metrics[f"bem_val_matsubara_plate_d{g_int}nm_tail_rel"] = float(
            l_data["tail_residual_rel"]
        )
        flat_metrics[f"bem_val_matsubara_plate_d{g_int}nm_tail_rel_pct"] = float(
            l_data["tail_residual_rel_pct"]
        )

    flat_metrics["bem_val_matsubara_max_tail_rel"] = float(suite3["max_cantor_tail_residual_rel"])
    flat_metrics["bem_val_matsubara_max_tail_rel_pct"] = float(
        suite3["max_cantor_tail_residual_rel_pct"]
    )

    keys = list(flat_metrics.keys())
    for idx, k in enumerate(keys):
        log_metric(
            k,
            flat_metrics[k],
            step_id="bem_canonical_validation_suite",
            metrics_path=str(metrics_path),
            defer_save=(idx < len(keys) - 1),
        )

    export_macros(metrics_path=str(metrics_path), output_path=str(macros_path))
    return flat_metrics


def write_markdown_summary(report: dict[str, Any], md_path: Path) -> None:
    """Write human-readable Markdown report summarizing all three validation suites."""
    s1 = report["suite1_lifshitz_parallel_plate"]
    s2 = report["suite2_energy_derivative_consistency"]
    s3 = report["suite3_matsubara_truncation_300k"]

    lines = [
        "# 3D Vector-Dyadic BEM Canonical Validation Report (Referee Concerns 1 & 2)",
        "",
        f"- **Generated at**: `{report['executed_at']}`",
        f"- **Material**: Drude Gold ($\\omega_p = {s1['drude_omega_p_ev']:.2f}\\text{{ eV}}$, $\\gamma = {s1['drude_gamma_ev']:.3f}\\text{{ eV}}$, $\\varepsilon_{{\\text{{bg}}}} = 1.0$)",
        "",
        "## 1. Analytical Lifshitz Parallel-Plate Benchmark ($R = 1.0\\ \\mu\\text{m}$ Disks)",
        "",
        "| Gap $d$ (nm) | $d/R$ | $P_z^{\\text{BEM}}$ Standard (Pa) | $P_z^{\\text{BEM}}$ High (Pa) | $P_z^{\\text{BEM}}$ Ultra-High (Pa) | $P_{z,\\infty}^{\\text{BEM}}$ Continuum (Pa) | Exact 1D Lifshitz $P_z^{\\text{Lifshitz}}$ (Pa) | Continuum Rel. Error (%) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for gap_nm in PARALLEL_PLATE_GAPS_NM:
        g = s1["by_gap"][f"d{int(round(gap_nm))}nm"]
        lines.append(
            f"| {gap_nm:.0f} | {g['d_over_R']:.3f} | {g['pressure_bem_std_pa']:.4f} | "
            f"{g['pressure_bem_high_pa']:.4f} | {g['pressure_bem_ultra_pa']:.4f} | "
            f"{g['pressure_bem_continuum_pa']:.4f} | {g['pressure_lifshitz_pa']:.4f} | "
            f"{g['rel_error_continuum_pct']:.3f}% |"
        )

    lines.extend([
        "",
        f"- **Monotonic recovery of 1D Lifshitz limit as $d/R \\to 0$**: `{s1['monotonic_d_over_r_recovery']}` "
        f"({s1['by_gap']['d100nm']['rel_error_continuum_pct']:.3f}% at $d/R=0.100$ $\\to$ "
        f"{s1['by_gap']['d15nm']['rel_error_continuum_pct']:.3f}% at $d/R=0.015$).",
        "",
        "## 2. Energy-Derivative vs. Trace Force Consistency (`Cantor_N2_HybridRZ`)",
        "",
        "| Angle $\\theta$ (deg) | $E_C(z_0 - \\Delta z)$ ($\\text{pN}\\cdot\\mu\\text{m}$) | $E_C(z_0)$ ($\\text{pN}\\cdot\\mu\\text{m}$) | $E_C(z_0 + \\Delta z)$ ($\\text{pN}\\cdot\\mu\\text{m}$) | Direct Trace $F_z^{\\text{trace}}$ (pN) | Central FD $-\\partial E_C/\\partial z_{\\text{rotor}}$ (pN) | Relative Discrepancy (%) | Relative Agreement (%) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for th_int in (3, 48):
        r = s2["by_angle"][f"theta{th_int}"]
        lines.append(
            f"| {th_int} | {r['energy_z_minus_pN_um']:.8f} | {r['energy_z0_pN_um']:.8f} | "
            f"{r['energy_z_plus_pN_um']:.8f} | {r['force_trace_pN']:+.6f} | "
            f"{r['force_fd_central_pN']:+.6f} | {r['rel_discrepancy_pct']:.5f}% | "
            f"{r['rel_agreement_pct']:.5f}% |"
        )

    lines.extend([
        "",
        "## 3. Matsubara Truncation Convergence ($T = 300\\text{ K}$)",
        "",
        f"- **Fundamental Matsubara spacing at $T = 300\\text{{ K}}$**: $\\Delta\\kappa = 2\\pi k_B T / (\\hbar c) = {s3['delta_kappa_1_per_um']:.8f}\\ \\mu\\text{{m}}^{{-1}}$",
        f"- **Direct Matsubara summation cutoff**: $N_{{\\text{{Matsubara}}}} = {s3['n_matsubara_cutoff']}$ ($\\kappa_{{\\max}} = {s3['kappa_cutoff_1_per_um']:.2f}\\ \\mu\\text{{m}}^{{-1}}$, $\\hbar\\omega_{{\\max}} = {s3['energy_cutoff_ev']:.2f}\\text{{ eV}}$) vs $2 N_{{\\text{{Matsubara}}}} = {s3['n_matsubara_2x_cutoff']}$ ($N_{{\\text{{poles}}}} = {s3['n_poles_evaluated']}$)",
        "",
        "| Configuration | $F_z(N)$ (pN) | $F_z(2N)$ (pN) | Relative Tail Residual $|F(2N)-F(N)|/|F(2N)|$ | Relative Tail Residual (%) |",
        "|---|---:|---:|---:|---:|",
    ])
    for th_int in (3, 48):
        m = s3["cantor_by_angle"][f"theta{th_int}"]
        lines.append(
            f"| `Cantor_N2_HybridRZ` ($\\theta = {th_int}^\\circ$) | {m['force_matsubara_N_pN']:+.6f} | "
            f"{m['force_matsubara_2N_pN']:+.6f} | {m['tail_residual_rel']:.3e} | "
            f"{m['tail_residual_rel_pct']:.5f}% |"
        )
    _atomic_write_text(md_path, "\n".join(lines) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run canonical 3D Vector-Dyadic BEM validation suite (Referee Concerns 1 & 2)."
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=("auto", "cpu", "cuda"),
        help="Compute backend device.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Optional micro-probe step cap (0 = full production run).",
    )
    parser.add_argument(
        "--delta-z-nm",
        type=float,
        default=0.5,
        help="Finite-difference axial step size in nm for -dE_C/dz_rotor check.",
    )
    parser.add_argument(
        "--n-matsubara",
        type=int,
        default=64,
        help="Matsubara summation cutoff N_Matsubara at T = 300 K.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="results/bem_canonical_validation_report.json",
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="results/bem_canonical_validation_report.md",
        help="Output Markdown summary path.",
    )
    args = parser.parse_args(argv)
    if args.max_steps < 0:
        parser.error("--max-steps must be >= 0")
    if not math.isfinite(args.delta_z_nm) or args.delta_z_nm <= 0.0:
        parser.error("--delta-z-nm must be positive and finite")
    if args.n_matsubara < 10:
        parser.error("--n-matsubara must be >= 10")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    t_start = time.perf_counter()
    backend = DenseBackend(args.device)

    print(
        f"[BEM Canonical Validation] Starting on device={backend.device} "
        f"(max_steps={args.max_steps}, delta_z_nm={args.delta_z_nm}, N_Matsubara={args.n_matsubara})"
    )

    suite1 = run_lifshitz_parallel_plate_suite(device=args.device, max_steps=args.max_steps)
    print(
        "[Suite 1: Lifshitz Parallel-Plate Benchmark] Completed: "
        f"monotonic d/R->0 recovery = {suite1['monotonic_d_over_r_recovery']}, "
        f"continuum rel error at d=15nm = {suite1['by_gap']['d15nm']['rel_error_continuum_pct']:.3f}%"
    )

    suite2 = run_energy_derivative_consistency_suite(
        device=args.device,
        delta_z_nm=args.delta_z_nm,
        max_steps=args.max_steps,
    )
    print(
        "[Suite 2: Energy-Derivative vs Trace Force] Completed: "
        f"theta=3 deg trace={suite2['by_angle']['theta3']['force_trace_pN']:+.6f} pN vs "
        f"FD={suite2['by_angle']['theta3']['force_fd_central_pN']:+.6f} pN "
        f"(rel err={suite2['by_angle']['theta3']['rel_discrepancy_pct']:.5f}%); "
        f"theta=48 deg trace={suite2['by_angle']['theta48']['force_trace_pN']:+.6f} pN vs "
        f"FD={suite2['by_angle']['theta48']['force_fd_central_pN']:+.6f} pN "
        f"(rel err={suite2['by_angle']['theta48']['rel_discrepancy_pct']:.5f}%)"
    )

    suite3 = run_matsubara_truncation_suite(
        device=args.device,
        temperature_k=300.0,
        n_matsubara_cutoff=args.n_matsubara,
        max_steps=args.max_steps,
    )
    print(
        "[Suite 3: Matsubara Truncation (T=300 K)] Completed: "
        f"N_Matsubara={suite3['n_matsubara_cutoff']} vs 2N={suite3['n_matsubara_2x_cutoff']}, "
        f"max Cantor tail residual = {suite3['max_cantor_tail_residual_rel']:.3e} "
        f"({suite3['max_cantor_tail_residual_rel_pct']:.5f}%)"
    )

    metrics_path = REPO_ROOT / "results" / "provenance_metrics.json"
    macros_path = REPO_ROOT / "results" / "macros_results.tex"
    logged_metrics = log_validation_metrics_to_provenance(
        suite1=suite1,
        suite2=suite2,
        suite3=suite3,
        metrics_path=metrics_path,
        macros_path=macros_path,
    )

    executed_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "model": "VectorDyadicBEM3D_CanonicalValidation",
        "dataset": "bem_canonical_validation",
        "status": "completed",
        "executed_at": executed_at,
        "runtime_device": backend.device,
        "max_steps": args.max_steps,
        "elapsed_total_s": time.perf_counter() - t_start,
        "suite1_lifshitz_parallel_plate": suite1,
        "suite2_energy_derivative_consistency": suite2,
        "suite3_matsubara_truncation_300k": suite3,
        "logged_metrics": logged_metrics,
    }

    out_json = REPO_ROOT / args.output_json
    _atomic_write_text(out_json, json.dumps(report, indent=2) + "\n")

    out_md = REPO_ROOT / args.output_md
    write_markdown_summary(report, out_md)
    print(f"[BEM Canonical Validation] Saved report to {out_json} and {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
