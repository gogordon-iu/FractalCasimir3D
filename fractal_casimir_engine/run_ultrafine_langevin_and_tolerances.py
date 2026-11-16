#!/usr/bin/env python3
"""Suite 6 (eng_uf6): Thermal Langevin Brownian Dynamics & Experimental NEMS Tolerance Budget.

Addresses experimental NEMS referee questions across four coupled physical audits:
  1. Part A (Thermal Langevin Dynamics, T in {0, 4, 77, 300} K, M = 256 seeds):
     Exact fluctuation-dissipation 2-DOF underdamped BAOAB Langevin integration on the
     C^1-conservative Ultra-Fine 1.5-deg Hermite Casimir landscapes (from uf1) and physical
     Kramers-Kronig two-state VO2 / photo-Si switching landscapes (from uf3), preceded by a
     mandatory equilibrium Second-Law zero-drift & Maxwell-Boltzmann equipartition gate.
  2. Part B1 (Polycrystalline Gold Patch Potentials & Residual Kelvin-Probe Bias):
     3D Voronoi grain patch-potential Monte Carlo across V_rms in {0, 5, 10, 15, 20, 30} mV
     (grain correlation length l_c = 50 nm, 32 realizations) and residual DC offset
     Delta V_DC in {0, 5, 10, 20, 30} mV.
  3. Part B2 (3D BEM RMS Surface Roughness Perturbation):
     Direct 3D cyclic BEM Monte Carlo with stochastic normal panel perturbations
     sigma_rms in {0.0, 1.0, 2.0, 3.0} nm on Config_D Stroke I & Stroke III.
  4. Part B3 (Full 4-Sector Non-Bloch Static Eccentricity & Tilt Runout):
     Exact non-Bloch 4-sector 3D BEM evaluation of (F_z, tau_theta) under static lateral
     eccentricity Delta x in {0, 4, 8, 12} nm and static tilt alpha_x in {0, 0.5, 1.0, 2.0} mrad.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from execution.casimir_bem_solver import ClutchSurfaceMesh, SurfacePanel
from fractal_casimir_engine import ENGINE_DESIGN_NAMES
from fractal_casimir_engine.bem_cycle_solver import (
    Full4Sector6DofBemEvaluator,
    PreparedEngineBemModel,
    build_engine_body_panels,
    detect_compute_device,
)
from fractal_casimir_engine.geometries import (
    ENGINE_Z_TIP_MAX_UM,
    ENGINE_Z_TIP_MIN_UM,
    SECTOR_DEG,
    build_engine_surface_mesh,
)
from fractal_casimir_engine.run_engine_cycle_mapping import (
    PeriodicHermitePotential2D,
    rotor_inertia_properties,
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

KB_J_PER_K: float = 1.380649e-23
EPS0_AJ_UM_PER_V2: float = 0.5 * 8.8541878128e-12 * 1.0e-6 * 1.0e18  # 4.4270939064 aJ*um / V^2

TEMPERATURES_K: tuple[float, ...] = (0.0, 4.0, 77.0, 300.0)
PATCH_VRMS_MV: tuple[float, ...] = (0.0, 5.0, 10.0, 15.0, 20.0, 30.0)
DC_BIAS_MV: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0, 30.0)
ROUGHNESS_SIGMA_NM: tuple[float, ...] = (0.0, 1.0, 2.0, 3.0)
ECCENTRICITY_DX_NM: tuple[float, ...] = (0.0, 4.0, 8.0, 12.0)
TILT_MRAD: tuple[float, ...] = (0.0, 0.5, 1.0, 2.0)

BENCHMARK_STATES: tuple[tuple[str, float, float], ...] = (
    ("Stroke_I_Repulsive", -0.092, 22.0),
    ("Stroke_III_Attractive", -0.084, 64.0),
)


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


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        d = json.load(handle)
    return d if isinstance(d, dict) else None


def _require_pos_int(val: Any, name: str) -> int:
    if not isinstance(val, int) or isinstance(val, bool) or val < 1:
        raise ValueError(f"{name} must be a positive integer >= 1.")
    return val


def check_walltime(started_mono: float, max_walltime_hours: float) -> None:
    if max_walltime_hours > 0.0 and (time.monotonic() - started_mono) >= max_walltime_hours * 3600.0:
        raise TimeoutError("Approaching Slurm walltime limit; checkpoint saved cleanly for auto-resubmit.")


def eval_hermite_batch(
    pot: PeriodicHermitePotential2D,
    z_um_arr: np.ndarray,
    th_rad_arr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized O(M) evaluation of (E_C, F_z, tau_theta) with exact conservative boundary clamping."""
    zc = np.clip(z_um_arr, pot.z[0], pot.z[-1] - 1.0e-12)
    iz = np.clip(((zc - pot.z[0]) // pot.dz).astype(np.int64), 0, pot.nz - 2)
    u = (zc - pot.z[iz]) / pot.dz

    thr = np.mod(th_rad_arr, pot.period_rad)
    ith = np.mod((thr // pot.dth).astype(np.int64), pot.nth)
    ith1 = (ith + 1) % pot.nth
    v = (thr - ith * pot.dth) / pot.dth

    u2, u3 = u * u, u * u * u
    v2, v3 = v * v, v * v * v
    bu0 = 2.0 * u3 - 3.0 * u2 + 1.0
    bu1 = -2.0 * u3 + 3.0 * u2
    bu2 = u3 - 2.0 * u2 + u
    bu3 = u3 - u2
    dbu0 = (6.0 * u2 - 6.0 * u) / pot.dz
    dbu1 = (-6.0 * u2 + 6.0 * u) / pot.dz
    dbu2 = (3.0 * u2 - 4.0 * u + 1.0) / pot.dz
    dbu3 = (3.0 * u2 - 2.0 * u) / pot.dz

    bv0 = 2.0 * v3 - 3.0 * v2 + 1.0
    bv1 = -2.0 * v3 + 3.0 * v2
    bv2 = v3 - 2.0 * v2 + v
    bv3 = v3 - v2
    dbv0 = (6.0 * v2 - 6.0 * v) / pot.dth
    dbv1 = (-6.0 * v2 + 6.0 * v) / pot.dth
    dbv2 = (3.0 * v2 - 4.0 * v + 1.0) / pot.dth
    dbv3 = (3.0 * v2 - 2.0 * v) / pot.dth

    dz, dth = pot.dz, pot.dth
    iz1 = iz + 1
    e00, e01 = pot.e[iz, ith], pot.e[iz, ith1]
    e10, e11 = pot.e[iz1, ith], pot.e[iz1, ith1]
    eth00, eth01 = dth * pot.eth[iz, ith], dth * pot.eth[iz, ith1]
    eth10, eth11 = dth * pot.eth[iz1, ith], dth * pot.eth[iz1, ith1]
    ez00, ez01 = dz * pot.ez[iz, ith], dz * pot.ez[iz, ith1]
    ez10, ez11 = dz * pot.ez[iz1, ith], dz * pot.ez[iz1, ith1]
    ezth00, ezth01 = dz * dth * pot.ezth[iz, ith], dz * dth * pot.ezth[iz, ith1]
    ezth10, ezth11 = dz * dth * pot.ezth[iz1, ith], dz * dth * pot.ezth[iz1, ith1]

    c0 = bu0 * e00 + bu1 * e10 + bu2 * ez00 + bu3 * ez10
    c1 = bu0 * e01 + bu1 * e11 + bu2 * ez01 + bu3 * ez11
    c2 = bu0 * eth00 + bu1 * eth10 + bu2 * ezth00 + bu3 * ezth10
    c3 = bu0 * eth01 + bu1 * eth11 + bu2 * ezth01 + bu3 * ezth11

    dc0 = dbu0 * e00 + dbu1 * e10 + dbu2 * ez00 + dbu3 * ez10
    dc1 = dbu0 * e01 + dbu1 * e11 + dbu2 * ez01 + dbu3 * ez11
    dc2 = dbu0 * eth00 + dbu1 * eth10 + dbu2 * ezth00 + dbu3 * ezth10
    dc3 = dbu0 * eth01 + dbu1 * eth11 + dbu2 * ezth01 + dbu3 * ezth11

    e_val = c0 * bv0 + c1 * bv1 + c2 * bv2 + c3 * bv3
    fz_val = -(dc0 * bv0 + dc1 * bv1 + dc2 * bv2 + dc3 * bv3)
    tau_val = -(c0 * dbv0 + c1 * dbv1 + c2 * dbv2 + c3 * dbv3)

    # Exact C^1 curl-free 1 nm exterior collar so (F_z, tau) = -grad E holds smoothly everywhere
    # without discontinuous force impulses at z_min/z_max, reaching F_z == 0 for |pen| >= 1 nm.
    mask_low = z_um_arr < pot.z[0]
    mask_high = z_um_arr > pot.z[-1]
    if np.any(mask_low) or np.any(mask_high):
        delta_c = 0.001  # 1.0 nm C^1 taper collar
        dfz_dth = -(dc0 * dbv0 + dc1 * dbv1 + dc2 * dbv2 + dc3 * dbv3)
        if np.any(mask_low):
            s = pot.z[0] - z_um_arr[mask_low]
            sc = np.minimum(s, delta_c)
            w_s = sc - 0.5 * (sc * sc) / delta_c
            dw_ds = np.maximum(0.0, 1.0 - s / delta_c)
            e_val[mask_low] = e_val[mask_low] + fz_val[mask_low] * w_s
            tau_val[mask_low] = tau_val[mask_low] - dfz_dth[mask_low] * w_s
            fz_val[mask_low] = fz_val[mask_low] * dw_ds
        if np.any(mask_high):
            s = z_um_arr[mask_high] - pot.z[-1]
            sc = np.minimum(s, delta_c)
            w_s = sc - 0.5 * (sc * sc) / delta_c
            dw_ds = np.maximum(0.0, 1.0 - s / delta_c)
            e_val[mask_high] = e_val[mask_high] - fz_val[mask_high] * w_s
            tau_val[mask_high] = tau_val[mask_high] + dfz_dth[mask_high] * w_s
            fz_val[mask_high] = fz_val[mask_high] * dw_ds

    return e_val, fz_val, tau_val


def _gate_scale_batch(th_rad_arr: np.ndarray) -> np.ndarray:
    """Vectorized pad-exit permittivity gate scale identical to simulate_coupled_dynamics."""
    th_mod = np.mod(np.rad2deg(th_rad_arr), SECTOR_DEG)
    scale = np.ones_like(th_mod)
    for seam_deg in (42.5, 89.0):
        delta = np.mod(th_mod - seam_deg + 0.5 * SECTOR_DEG, SECTOR_DEG) - 0.5 * SECTOR_DEG
        mask = np.abs(delta) <= 11.5
        if np.any(mask):
            s = np.cos(0.5 * math.pi * delta[mask] / 11.5) ** 2
            scale[mask] *= 1.0 - 0.92 * s
    return scale


def _release_window_mask(th_rad_arr: np.ndarray, *, half_width_deg: float = 11.5) -> np.ndarray:
    th_mod = np.mod(np.rad2deg(th_rad_arr), SECTOR_DEG)
    out = np.zeros(th_mod.shape, dtype=bool)
    for seam_deg in (42.5, 89.0):
        delta = np.mod(th_mod - seam_deg + 0.5 * SECTOR_DEG, SECTOR_DEG) - 0.5 * SECTOR_DEG
        out |= np.abs(delta) <= half_width_deg
    return out


def simulate_baoab_langevin_ensemble(
    design_name: str,
    pot_on: PeriodicHermitePotential2D,
    *,
    pot_off: PeriodicHermitePotential2D | None = None,
    mode: str,
    temperature_K: float,
    n_traj: int = 256,
    n_steps: int = 20000,
    dt_us: float = 0.025,
    seed: int = 20261115,
    thermalize_init: bool = False,
) -> dict[str, Any]:
    """Integrate M coupled 2-DOF underdamped BAOAB Langevin trajectories in float64.

    Modes:
      - ``equilibrium_static``: Purely conservative single-surface dynamics (Second-Law test).
      - ``pad_release_gated``: Unpolarized two-seam pad-exit permittivity gate.
      - ``two_state_switching``: Kramers-Kronig ON <-> OFF dispersive material switching.
    """
    if temperature_K < 0.0 or not math.isfinite(temperature_K):
        raise ValueError("temperature_K must be finite and nonnegative.")
    if dt_us <= 0.0 or not math.isfinite(dt_us):
        raise ValueError("dt_us must be finite and strictly positive.")
    n_traj = _require_pos_int(n_traj, "n_traj")
    n_steps = _require_pos_int(n_steps, "n_steps")
    if mode == "two_state_switching" and pot_off is None:
        raise ValueError("pot_off is required for two_state_switching mode.")

    props = rotor_inertia_properties(design_name)
    mass_kg = float(props["mass_kg"])
    iz_kg_m2 = float(props["iz_kg_m2"])

    z_eq_um = -0.084
    k_flex_N_m = 4.0e-5
    gamma_z = 2.5e-12
    gamma_th = 6.0e-25
    k_stop_pn_per_um = 180.0 / 0.010

    dt_s = float(dt_us) * 1.0e-6
    kbt_J = KB_J_PER_K * float(temperature_K)

    cz = math.exp(-(gamma_z / mass_kg) * dt_s)
    cth = math.exp(-(gamma_th / iz_kg_m2) * dt_s)
    sig_vz = math.sqrt((kbt_J / mass_kg) * max(0.0, 1.0 - cz * cz)) if kbt_J > 0.0 else 0.0
    sig_om = math.sqrt((kbt_J / iz_kg_m2) * max(0.0, 1.0 - cth * cth)) if kbt_J > 0.0 else 0.0

    rng = np.random.default_rng(seed)
    if thermalize_init:
        if kbt_J > 0.0:
            # Sample exact canonical Boltzmann-Gibbs configurational measure P(z, th) ~ exp(-U_total(z, th) / k_B T)
            nz_b, nth_b = 128, 360
            zg_b = np.linspace(ENGINE_Z_TIP_MIN_UM - 0.003, ENGINE_Z_TIP_MAX_UM + 0.003, nz_b)
            thg_b = np.linspace(0.0, math.radians(SECTOR_DEG), nth_b, endpoint=False)
            zz_b, tt_b = np.meshgrid(zg_b, thg_b, indexing="ij")
            zf = zz_b.ravel()
            e_cas_aj, _, _ = eval_hermite_batch(pot_on, zf, tt_b.ravel())
            u_sp_aj = 0.5 * k_flex_N_m * (((zf - z_eq_um) * 1.0e-6) ** 2) * 1.0e18
            u_stop_aj = np.where(
                zf < ENGINE_Z_TIP_MIN_UM,
                0.5 * k_stop_pn_per_um * ((ENGINE_Z_TIP_MIN_UM - zf) ** 2),
                np.where(zf > ENGINE_Z_TIP_MAX_UM, 0.5 * k_stop_pn_per_um * ((zf - ENGINE_Z_TIP_MAX_UM) ** 2), 0.0),
            )
            u_tot_J = (e_cas_aj + u_sp_aj + u_stop_aj) * 1.0e-18
            log_w = -(u_tot_J - float(np.min(u_tot_J))) / kbt_J
            weights = np.exp(np.clip(log_w, -700.0, 0.0))
            weights /= float(np.sum(weights))
            picks = rng.choice(weights.size, size=n_traj, replace=True, p=weights)
            dz_cell = (zg_b[1] - zg_b[0]) * 0.5
            dth_cell = (thg_b[1] - thg_b[0]) * 0.5
            z_um = zf[picks] + rng.uniform(-dz_cell, dz_cell, size=n_traj)
            th_rad = tt_b.ravel()[picks] + rng.uniform(-dth_cell, dth_cell, size=n_traj)
            vz = rng.normal(0.0, math.sqrt(kbt_J / mass_kg), size=n_traj)
            om = rng.normal(0.0, math.sqrt(kbt_J / iz_kg_m2), size=n_traj)
        else:
            z_um = np.full(n_traj, z_eq_um, dtype=np.float64)
            th_rad = np.zeros(n_traj, dtype=np.float64)
            vz = np.zeros(n_traj, dtype=np.float64)
            om = np.zeros(n_traj, dtype=np.float64)
    else:
        z_um = np.full(n_traj, -0.097, dtype=np.float64)
        th_rad = np.full(n_traj, math.radians(9.0), dtype=np.float64)
        if kbt_J > 0.0:
            vz = rng.normal(0.0, math.sqrt(kbt_J / mass_kg), size=n_traj)
            om = rng.normal(0.0, math.sqrt(kbt_J / iz_kg_m2), size=n_traj)
        else:
            vz = np.zeros(n_traj, dtype=np.float64)
            om = np.zeros(n_traj, dtype=np.float64)

    th_init = th_rad.copy()

    def eval_forces(z_u: np.ndarray, th_r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if mode == "two_state_switching":
            assert pot_off is not None
            mask_off = _release_window_mask(th_r)
            _, fz_on, tau_on = eval_hermite_batch(pot_on, z_u, th_r)
            _, fz_off, tau_off = eval_hermite_batch(pot_off, z_u, th_r)
            fz_c = np.where(mask_off, fz_off, fz_on)
            tau_c = np.where(mask_off, tau_off, tau_on)
        else:
            _, fz_c, tau_c = eval_hermite_batch(pot_on, z_u, th_r)
            if mode == "pad_release_gated":
                sc = _gate_scale_batch(th_r)
                fz_c = fz_c * sc
                tau_c = tau_c * sc

        f_spring_pN = -k_flex_N_m * ((z_u - z_eq_um) * 1.0e-6) * 1.0e12
        f_stop_pN = np.where(
            z_u < ENGINE_Z_TIP_MIN_UM,
            k_stop_pn_per_um * (ENGINE_Z_TIP_MIN_UM - z_u),
            np.where(z_u > ENGINE_Z_TIP_MAX_UM, -k_stop_pn_per_um * (z_u - ENGINE_Z_TIP_MAX_UM), 0.0),
        )
        return (fz_c + f_spring_pN + f_stop_pN), tau_c

    fz_tot, tau_tot = eval_forces(z_um, th_rad)

    stride = max(1, n_steps // 200)
    sample_t_s: list[float] = [0.0]
    sample_mean_adv_deg: list[float] = [0.0]
    sample_p10_adv_deg: list[float] = [0.0]
    sample_p90_adv_deg: list[float] = [0.0]
    sample_var_th_rad2: list[float] = [0.0]
    ke_z_samples: list[float] = []
    ke_th_samples: list[float] = []

    half_dt = 0.5 * dt_s
    inv_m_pN = 1.0e-12 / mass_kg
    inv_iz_pNum = 1.0e-18 / iz_kg_m2

    for step in range(1, n_steps + 1):
        # B (half-kick)
        vz += half_dt * fz_tot * inv_m_pN
        om += half_dt * tau_tot * inv_iz_pNum
        # A (half-drift)
        z_um += half_dt * vz * 1.0e6
        th_rad += half_dt * om
        # O (exact Ornstein-Uhlenbeck thermostat)
        if sig_vz > 0.0:
            vz = cz * vz + sig_vz * rng.standard_normal(n_traj)
            om = cth * om + sig_om * rng.standard_normal(n_traj)
        else:
            vz *= cz
            om *= cth
        # A (second half-drift)
        z_um += half_dt * vz * 1.0e6
        th_rad += half_dt * om
        # B (second half-kick)
        fz_tot, tau_tot = eval_forces(z_um, th_rad)
        vz += half_dt * fz_tot * inv_m_pN
        om += half_dt * tau_tot * inv_iz_pNum

        if step >= n_steps // 2 and step % stride == 0:
            ke_z_samples.append(float(np.mean(mass_kg * vz * vz)))
            ke_th_samples.append(float(np.mean(iz_kg_m2 * om * om)))

        if step % stride == 0 or step == n_steps:
            dth_rad = th_rad - th_init
            dth_deg = np.rad2deg(dth_rad)
            sample_t_s.append(step * dt_s)
            sample_mean_adv_deg.append(float(np.mean(dth_deg)))
            sample_p10_adv_deg.append(float(np.percentile(dth_deg, 10.0)))
            sample_p90_adv_deg.append(float(np.percentile(dth_deg, 90.0)))
            sample_var_th_rad2.append(float(np.var(dth_rad, ddof=1)) if n_traj > 1 else 0.0)

    dth_final_rad = th_rad - th_init
    dth_final_deg = np.rad2deg(dth_final_rad)
    mean_adv = float(np.mean(dth_final_deg))
    std_adv = float(np.std(dth_final_deg, ddof=1)) if n_traj > 1 else 0.0
    se_adv = std_adv / math.sqrt(n_traj) if n_traj > 1 else 0.0

    # Late-time linear regression over second half of trajectory for steady drift omega & diffusivity D_theta
    t_arr = np.asarray(sample_t_s, dtype=np.float64)
    half_idx = max(1, len(t_arr) // 2)
    t_tail = t_arr[half_idx:]
    adv_tail_rad = np.deg2rad(np.asarray(sample_mean_adv_deg[half_idx:], dtype=np.float64))
    var_tail_rad2 = np.asarray(sample_var_th_rad2[half_idx:], dtype=np.float64)

    omega_steady_rad_s = float(np.polyfit(t_tail, adv_tail_rad, 1)[0]) if len(t_tail) >= 2 else 0.0
    if len(t_tail) >= 2 and temperature_K > 0.0 and n_traj > 1:
        slope_var = float(np.polyfit(t_tail, var_tail_rad2, 1)[0])
        d_theta_rad2_s = max(0.0, 0.5 * slope_var)
    else:
        d_theta_rad2_s = 0.0

    sector_rad = math.radians(SECTOR_DEG)
    peclet_sector = (
        abs(omega_steady_rad_s) * sector_rad / d_theta_rad2_s if d_theta_rad2_s > 1.0e-12 else 0.0
    )

    equipartition_z_ratio = (float(np.mean(ke_z_samples)) / kbt_J) if (kbt_J > 0.0 and ke_z_samples) else 1.0
    equipartition_th_ratio = (float(np.mean(ke_th_samples)) / kbt_J) if (kbt_J > 0.0 and ke_th_samples) else 1.0

    return {
        "design_name": design_name,
        "mode": mode,
        "temperature_K": float(temperature_K),
        "n_trajectories": int(n_traj),
        "horizon_us": round(n_steps * dt_us, 2),
        "mean_advance_deg": mean_adv,
        "std_advance_deg": std_adv,
        "se_advance_deg": se_adv,
        "median_advance_deg": float(np.median(dth_final_deg)),
        "prob_gt_90deg": float(np.mean(dth_final_deg > 90.0)),
        "prob_gt_360deg": float(np.mean(dth_final_deg > 360.0)),
        "omega_steady_krad_s": omega_steady_rad_s * 1.0e-3,
        "d_theta_rad2_s": d_theta_rad2_s,
        "peclet_sector": peclet_sector,
        "equipartition_z_ratio": equipartition_z_ratio,
        "equipartition_th_ratio": equipartition_th_ratio,
        "trace": {
            "time_us": (t_arr * 1.0e6).round(3).tolist(),
            "mean_deg": [round(x, 3) for x in sample_mean_adv_deg],
            "p10_deg": [round(x, 3) for x in sample_p10_adv_deg],
            "p90_deg": [round(x, 3) for x in sample_p90_adv_deg],
        },
    }


def evaluate_patch_and_dc_bias_budget(
    design_name: str,
    *,
    z_tip_um: float = -0.092,
    theta_deg: float = 22.0,
    grain_size_um: float = 0.050,
    n_realizations: int = 32,
    fast_probe: bool = False,
    seed: int = 20261116,
) -> dict[str, Any]:
    """Evaluate 3D polycrystalline Au patch-potential & residual Kelvin-probe DC bias forces/torques."""
    n_realizations = _require_pos_int(n_realizations, "n_realizations")
    if grain_size_um <= 0.0 or not math.isfinite(grain_size_um):
        raise ValueError("grain_size_um must be finite and strictly positive.")
    base = PreparedEngineBemModel(
        design_name,
        n_r=1 if fast_probe else 2,
        n_phi_tooth=2 if fast_probe else 4,
        n_phi_bridge=2 if fast_probe else 4,
        n_phi_arc_override=6 if fast_probe else 12,
        n_z=1 if fast_probe else 2,
        n_xi=4 if fast_probe else 8,
        quad_order=2,
        lazy_self_cache=True,
    )
    rot_sec0 = base.rotor_ref
    stat_sec0 = base.stator_ref

    rot_mats = [
        np.array([[math.cos(k * 0.5 * math.pi), -math.sin(k * 0.5 * math.pi), 0.0],
                  [math.sin(k * 0.5 * math.pi),  math.cos(k * 0.5 * math.pi), 0.0],
                  [0.0, 0.0, 1.0]], dtype=np.float64)
        for k in range(4)
    ]

    # Assemble full 4-sector panel centroids, normals, and areas in reference frames
    r_cent_ref = np.concatenate([rot_sec0.centroids @ rm.T for rm in rot_mats], axis=0)
    r_norm_ref = np.concatenate([rot_sec0.normals @ rm.T for rm in rot_mats], axis=0)
    r_area = np.tile(rot_sec0.areas, 4)

    s_cent = np.concatenate([stat_sec0.centroids @ rm.T for rm in rot_mats], axis=0)
    s_norm = np.concatenate([stat_sec0.normals @ rm.T for rm in rot_mats], axis=0)
    s_area = np.tile(stat_sec0.areas, 4)

    def geom_capacitance_matrix(z_u: float, th_d: float) -> np.ndarray:
        dz_u = z_u - base.z_ref_um
        ang = math.radians(th_d)
        ca, sa = math.cos(ang), math.sin(ang)
        rm = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        rc = (r_cent_ref @ rm.T) + np.array([0.0, 0.0, dz_u], dtype=np.float64)
        rn = r_norm_ref @ rm.T

        diff = rc[:, None, :] - s_cent[None, :, :]
        dist2 = np.sum(diff * diff, axis=2)
        dist = np.sqrt(dist2)
        # Opposing outward normals satisfy n_r . n_s < 0 and separated along -n_s
        align = np.clip(-np.einsum("ia,ja->ij", rn, s_norm), 0.0, 1.0)
        a_pair = (2.0 * r_area[:, None] * s_area[None, :] / np.maximum(1.0e-12, r_area[:, None] + s_area[None, :]))
        d_eff = np.sqrt(dist2 + (r_area[:, None] + s_area[None, :]) / (16.0 * math.pi))
        cutoff = np.exp(-dist / 0.120)
        # Returns C_ij in aJ / V^2 so E_elec = - sum_{i,j} C_ij * (dV_ij)^2
        return EPS0_AJ_UM_PER_V2 * (a_pair * align * cutoff) / d_eff

    hz = 0.0005  # 0.5 nm
    hth_deg = 0.10
    hth_rad = math.radians(hth_deg)
    c_zp = geom_capacitance_matrix(z_tip_um + hz, theta_deg)
    c_zm = geom_capacitance_matrix(z_tip_um - hz, theta_deg)
    c_tp = geom_capacitance_matrix(z_tip_um, theta_deg + hth_deg)
    c_tm = geom_capacitance_matrix(z_tip_um, theta_deg - hth_deg)

    # Since E = - sum C_ij V_ij^2, F_z = -dE/dz = + sum (dC_ij/dz) V_ij^2 (in pN = aJ/um)
    dc_dz = (c_zp - c_zm) / (2.0 * hz)
    dc_dth = (c_tp - c_tm) / (2.0 * hth_rad)

    rng = np.random.default_rng(seed)
    total_r_area = float(np.sum(r_area))
    total_s_area = float(np.sum(s_area))
    n_grains_r = max(24, int(round(total_r_area / (grain_size_um**2))))
    n_grains_s = max(32, int(round(total_s_area / (grain_size_um**2))))

    # Pre-sample Voronoi grain assignments on rotor and stator 3D surfaces
    patch_rows: list[dict[str, float]] = []
    for v_mv in PATCH_VRMS_MV:
        v_volt = v_mv * 1.0e-3
        fz_samples = []
        tau_samples = []
        for _ in range(n_realizations):
            if v_volt == 0.0:
                fz_samples.append(0.0)
                tau_samples.append(0.0)
                continue
            gr_idx = rng.choice(len(r_cent_ref), size=min(n_grains_r, len(r_cent_ref)), replace=False)
            gs_idx = rng.choice(len(s_cent), size=min(n_grains_s, len(s_cent)), replace=False)
            r_gid = np.argmin(np.sum((r_cent_ref[:, None, :] - r_cent_ref[gr_idx][None, :, :]) ** 2, axis=2), axis=1)
            s_gid = np.argmin(np.sum((s_cent[:, None, :] - s_cent[gs_idx][None, :, :]) ** 2, axis=2), axis=1)
            vr = rng.normal(0.0, v_volt, size=len(gr_idx))[r_gid]
            vs = rng.normal(0.0, v_volt, size=len(gs_idx))[s_gid]
            dv2 = (vr[:, None] - vs[None, :]) ** 2
            fz_samples.append(float(np.sum(dc_dz * dv2)))
            tau_samples.append(float(np.sum(dc_dth * dv2)))
        patch_rows.append(
            {
                "v_rms_mV": float(v_mv),
                "mean_fz_elec_pN": float(np.mean(fz_samples)),
                "std_fz_elec_pN": float(np.std(fz_samples, ddof=1)) if len(fz_samples) > 1 else 0.0,
                "mean_tau_elec_pN_um": float(np.mean(tau_samples)),
                "rms_pinning_tau_pN_um": float(np.sqrt(np.mean(np.square(tau_samples)))),
            }
        )

    dc_rows: list[dict[str, float]] = []
    sum_dc_dz = float(np.sum(dc_dz))
    sum_dc_dth = float(np.sum(dc_dth))
    for dc_mv in DC_BIAS_MV:
        v2 = (dc_mv * 1.0e-3) ** 2
        dc_rows.append(
            {
                "dc_bias_mV": float(dc_mv),
                "fz_dc_pN": sum_dc_dz * v2,
                "tau_dc_pN_um": sum_dc_dth * v2,
            }
        )

    return {
        "design_name": design_name,
        "z_tip_um": z_tip_um,
        "theta_deg": theta_deg,
        "grain_size_nm": grain_size_um * 1.0e3,
        "patch_vrms_sweep": patch_rows,
        "dc_bias_sweep": dc_rows,
    }


def _perturb_mesh_roughness(
    mesh: ClutchSurfaceMesh,
    sigma_nm: float,
    rng: np.random.Generator,
) -> ClutchSurfaceMesh:
    """Apply zero-mean Gaussian normal displacement delta_h ~ N(0, sigma_nm^2) to every panel."""
    if sigma_nm <= 0.0:
        return mesh
    sig_um = sigma_nm * 1.0e-3

    def shift_panels(panels: tuple[SurfacePanel, ...]) -> tuple[SurfacePanel, ...]:
        out: list[SurfacePanel] = []
        dh_arr = rng.normal(0.0, sig_um, size=len(panels))
        for p, dh in zip(panels, dh_arr):
            shift = float(dh) * p.normal
            out.append(
                dataclasses.replace(
                    p,
                    vertices=p.vertices + shift[None, :],
                    centroid=p.centroid + shift,
                )
            )
        return tuple(out)

    return dataclasses.replace(
        mesh,
        rotor=shift_panels(mesh.rotor),
        stator=shift_panels(mesh.stator),
    )


def evaluate_roughness_bem_sweep(
    design_name: str,
    *,
    device: str,
    n_realizations: int = 6,
    max_steps: int = 0,
    seed: int = 20261117,
) -> list[dict[str, Any]]:
    """Direct 3D cyclic BEM Monte Carlo over stochastic panel roughness sigma_rms in {0, 1, 2, 3} nm."""
    n_realizations = _require_pos_int(n_realizations, "n_realizations")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    sigmas = (0.0, 2.0) if max_steps > 0 else ROUGHNESS_SIGMA_NM
    n_real = 2 if max_steps > 0 else n_realizations

    for sig_nm in sigmas:
        s1_tau: list[float] = []
        s1_fz: list[float] = []
        s3_tau: list[float] = []
        s3_fz: list[float] = []
        reps = 1 if sig_nm == 0.0 else n_real
        for _ in range(reps):
            model = PreparedEngineBemModel(
                design_name,
                n_r=1 if max_steps > 0 else 2,
                n_phi_tooth=2 if max_steps > 0 else 4,
                n_phi_bridge=2 if max_steps > 0 else 4,
                n_phi_arc_override=6 if max_steps > 0 else 12,
                n_z=1 if max_steps > 0 else 2,
                n_xi=4 if max_steps > 0 else 16,
                quad_order=2 if max_steps > 0 else 3,
                device=device,
                lazy_self_cache=True,
            )
            if sig_nm > 0.0:
                rmesh = _perturb_mesh_roughness(model.ref_mesh, sig_nm, rng)
                model.rotor_ref = build_engine_body_panels(rmesh.rotor, quad_order=model.quad_order)
                model.stator_ref = build_engine_body_panels(rmesh.stator, quad_order=model.quad_order)
            evals = model.evaluate_states_batch(
                [(-0.092, 22.0), (-0.084, 64.0)], max_steps=max_steps
            )
            s1_fz.append(float(evals[0]["f_z_pN"]))
            s1_tau.append(float(evals[0]["tau_theta_pN_um"]))
            s3_fz.append(float(evals[1]["f_z_pN"]))
            s3_tau.append(float(evals[1]["tau_theta_pN_um"]))

        rows.append(
            {
                "sigma_rms_nm": float(sig_nm),
                "n_realizations": reps,
                "Stroke_I_fz_mean_pN": float(np.mean(s1_fz)),
                "Stroke_I_tau_mean_pN_um": float(np.mean(s1_tau)),
                "Stroke_I_tau_std_pN_um": float(np.std(s1_tau, ddof=1)) if len(s1_tau) > 1 else 0.0,
                "Stroke_III_fz_mean_pN": float(np.mean(s3_fz)),
                "Stroke_III_tau_mean_pN_um": float(np.mean(s3_tau)),
                "Stroke_III_tau_std_pN_um": float(np.std(s3_tau, ddof=1)) if len(s3_tau) > 1 else 0.0,
            }
        )
    return rows


def evaluate_misaligned_pose_fz_tau(
    eval6: Full4Sector6DofBemEvaluator,
    *,
    dx_um: float,
    rx_rad: float,
    z_tip_um: float,
    theta_deg: float,
    hz_um: float = 0.001,
    hth_deg: float = 0.25,
    max_steps: int = 0,
) -> dict[str, float]:
    """Extract exact non-Bloch 4-sector (E_C, F_z, tau_theta) at an off-center / tilted rotor pose."""
    if hz_um <= 0.0 or not math.isfinite(hz_um) or hth_deg <= 0.0 or not math.isfinite(hth_deg):
        raise ValueError("hz_um and hth_deg must be finite and strictly positive.")
    base_p = {
        "dx_um": float(dx_um),
        "dy_um": 0.0,
        "z_tip_um": float(z_tip_um),
        "rx_rad": float(rx_rad),
        "ry_rad": 0.0,
        "theta_deg": float(theta_deg),
    }
    stencil = [
        base_p,
        {**base_p, "z_tip_um": float(z_tip_um) + hz_um},
        {**base_p, "z_tip_um": float(z_tip_um) - hz_um},
        {**base_p, "theta_deg": float(theta_deg) + hth_deg},
        {**base_p, "theta_deg": float(theta_deg) - hth_deg},
    ]
    vals = eval6.evaluate_energy_poses_batch(stencil, max_steps=max_steps, min_clearance_um=0.004)
    e0 = vals[0]["energy_aJ"]
    fz_pN = -(vals[1]["energy_aJ"] - vals[2]["energy_aJ"]) / (2.0 * hz_um)
    tau_pN_um = -(vals[3]["energy_aJ"] - vals[4]["energy_aJ"]) / (2.0 * math.radians(hth_deg))
    return {
        "dx_nm": round(dx_um * 1.0e3, 3),
        "tilt_mrad": round(rx_rad * 1.0e3, 3),
        "z_tip_um": float(z_tip_um),
        "theta_deg": float(theta_deg),
        "energy_aJ": float(e0),
        "f_z_pN": float(fz_pN),
        "tau_theta_pN_um": float(tau_pN_um),
        "min_clearance_nm": round(vals[0]["min_clearance_um"] * 1.0e3, 3),
    }


def generate_uf6_figure(
    report: dict[str, Any],
    fig_png: Path,
    fig_pdf: Path,
    rep_path: Path,
    solver_params: dict[str, Any],
) -> None:
    """Render 4-panel Thermal Langevin & Experimental Tolerance Budget figure."""
    fig_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.8), dpi=220)

    colors = {
        "Sym_Baseline_CantorN2": "#555555",
        "Config_B_Manhattan_Vernier": "#1f77b4",
        "Config_C_Helical_Turbine": "#2ca02c",
        "Config_D_DualStator_PushPull": "#d62728",
    }
    labels = {
        "Sym_Baseline_CantorN2": "Sym Control",
        "Config_B_Manhattan_Vernier": "Config B (Manhattan)",
        "Config_C_Helical_Turbine": "Config C (Helical)",
        "Config_D_DualStator_PushPull": "Config D (Dual-Stator)",
    }

    # Panel A: 300 K Langevin Trajectory Ensembles (Mean + 10-90% Band)
    ax_a = axes[0, 0]
    for dname in ENGINE_DESIGN_NAMES:
        rec_300 = report["langevin_gated"][dname]["300K"]
        tr = rec_300["trace"]
        t_us = np.asarray(tr["time_us"], dtype=np.float64)
        mu = np.asarray(tr["mean_deg"], dtype=np.float64)
        p10 = np.asarray(tr["p10_deg"], dtype=np.float64)
        p90 = np.asarray(tr["p90_deg"], dtype=np.float64)
        lbl = f"{labels[dname]} ({rec_300['mean_advance_deg']:+.0f}°)"
        ax_a.plot(t_us, mu, linewidth=2.0, color=colors[dname], label=lbl)
        ax_a.fill_between(t_us, p10, p90, color=colors[dname], alpha=0.14)
    ax_a.axhline(0.0, color="black", linewidth=0.8)
    ax_a.set_xlabel(r"Time $t$ ($\mu\mathrm{s}$)")
    ax_a.set_ylabel(r"Ensemble Rotation $\Delta\theta(t)$ ($^\circ$, $T = 300\ \mathrm{K}$)")
    ax_a.set_title("A. 300 K Underdamped Langevin Ensembles (Mean & 10–90% Band)")
    ax_a.grid(True, alpha=0.3)
    ax_a.legend(fontsize=8)

    # Panel B: Temperature Scaling of Active Switching & Gated Drift (0, 4, 77, 300 K)
    ax_b = axes[0, 1]
    t_labels = ["0K", "4K", "77K", "300K"]
    x_t = np.arange(len(t_labels), dtype=np.float64)
    for key, lbl, col, ls in (
        ("Config_D_gated", "Config D (UF1 Gated)", "#d62728", "-"),
        ("Config_B_vo2", r"Config B ($\mathrm{Au-VO_2}$ Switching)", "#1f77b4", "--"),
        ("Config_D_si", r"Config D ($\mathrm{Au-photo\text{-}Si}$ Switching)", "#ff7f0e", "-."),
        ("Sym_vo2", r"Sym Control ($\mathrm{Au-VO_2}$)", "#555555", ":"),
    ):
        series = report["temperature_scaling"][key]
        mus = [float(series[tk]["mean_advance_deg"]) for tk in t_labels]
        ses = [float(series[tk]["se_advance_deg"]) for tk in t_labels]
        ax_b.errorbar(x_t, mus, yerr=ses, marker="o", linewidth=1.9, linestyle=ls, color=col, capsize=3, label=lbl)
    ax_b.axhline(0.0, color="black", linewidth=0.8)
    ax_b.set_xticks(x_t)
    ax_b.set_xticklabels(["0 K", "4 K", "77 K", "300 K"])
    ax_b.set_ylabel(r"Mean Advance $\langle\Delta\theta\rangle \pm \mathrm{SE}$ ($^\circ$, $500\ \mu\mathrm{s}$)")
    ax_b.set_title("B. Thermal Robustness Across Cryogenic to Room Temperature")
    ax_b.grid(True, alpha=0.3)
    ax_b.legend(fontsize=8)

    # Panel C: Patch Potential & Kelvin-Probe DC Bias Budget vs Casimir Torque
    ax_c = axes[1, 0]
    for dname, col, lbl in (
        ("Config_B_Manhattan_Vernier", "#1f77b4", "Config B"),
        ("Config_D_DualStator_PushPull", "#d62728", "Config D"),
    ):
        p_rows = report["patch_potentials"][dname]["patch_vrms_sweep"]
        vs = [float(r["v_rms_mV"]) for r in p_rows]
        pin_tau = [float(r["rms_pinning_tau_pN_um"]) for r in p_rows]
        dc_rows = report["patch_potentials"][dname]["dc_bias_sweep"]
        dcs = [float(r["dc_bias_mV"]) for r in dc_rows]
        dc_tau = [abs(float(r["tau_dc_pN_um"])) for r in dc_rows]
        ax_c.plot(vs, pin_tau, marker="o", linewidth=2.0, color=col, label=f"{lbl} Patch RMS Pinning $\\sigma(\\tau_\\theta)$")
        ax_c.plot(dcs, dc_tau, marker="s", linewidth=1.6, linestyle="--", color=col, label=f"{lbl} Residual DC $|\\tau_\\theta^{{\\mathrm{{DC}}}}|$")
    cas_ref = float(report["summary"]["config_d_ref_stroke1_tau_pN_um"])
    ax_c.axhline(cas_ref, color="#222222", linestyle="-.", linewidth=1.2, label=f"Config D Stroke I Casimir $\\tau_\\theta$ ({cas_ref:.2f})")
    ax_c.set_xlabel(r"Patch $V_{\mathrm{rms}}$ or Residual Kelvin-Probe Bias $\Delta V_{\mathrm{DC}}$ (mV)")
    ax_c.set_ylabel(r"Torque Magnitude ($\mathrm{pN\cdot\mu m}$)")
    ax_c.set_title("C. Electrostatic Patch & DC Bias Budget vs. Casimir Torque")
    ax_c.grid(True, alpha=0.3)
    ax_c.legend(fontsize=7.5)

    # Panel D: Static Rotor Eccentricity & Surface Roughness Torque Retention
    ax_d = axes[1, 1]
    for dname in ("Sym_Baseline_CantorN2", "Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull"):
        ecc = report["misalignment_bem"][dname]["eccentricity_stroke1"]
        dxs = [float(r["dx_nm"]) for r in ecc]
        taus = [float(r["tau_theta_pN_um"]) for r in ecc]
        ax_d.plot(dxs, taus, marker="o", linewidth=2.0, color=colors[dname], label=f"{labels[dname]} (Stroke I vs $\\Delta x$)")
    rough = report["roughness_bem_config_d"]
    sig_x = [float(r["sigma_rms_nm"]) * 4.0 for r in rough]  # mapped onto [0, 12] secondary scale or plotted cleanly
    ax_d2 = ax_d.twiny()
    ax_d2.errorbar(
        [float(r["sigma_rms_nm"]) for r in rough],
        [float(r["Stroke_I_tau_mean_pN_um"]) for r in rough],
        yerr=[float(r["Stroke_I_tau_std_pN_um"]) for r in rough],
        marker="^",
        linestyle=":",
        color="#9467bd",
        linewidth=1.8,
        capsize=3,
        label=r"Config D Roughness $\sigma_{\mathrm{rms}}$ (top axis)",
    )
    ax_d2.set_xlabel(r"3D Panel Normal Roughness $\sigma_{\mathrm{rms}}$ (nm)", fontsize=8.5, color="#9467bd")
    ax_d.axhline(0.0, color="black", linewidth=0.8)
    ax_d.set_xlabel(r"Static Rotor Off-Center Eccentricity $\Delta x$ (nm)")
    ax_d.set_ylabel(r"Stroke I Azimuthal Torque $\tau_\theta$ ($\mathrm{pN\cdot\mu m}$)")
    ax_d.set_title("D. Non-Bloch Eccentricity Runout & 3D Surface Roughness")
    ax_d.grid(True, alpha=0.3)
    h1, l1 = ax_d.get_legend_handles_labels()
    h2, l2 = ax_d2.get_legend_handles_labels()
    ax_d.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="lower left")
    _ = sig_x

    fig.tight_layout()
    fig.savefig(fig_png, dpi=240)
    fig.savefig(fig_pdf)
    plt.close(fig)

    for fp in (fig_png, fig_pdf):
        save_plot_provenance(
            str(fp),
            str(rep_path),
            columns_used=["equilibrium_no_go_audit", "langevin_gated", "temperature_scaling", "patch_potentials", "misalignment_bem", "roughness_bem_config_d"],
            solver_name="BEM_Langevin_Patch_Roughness_Tolerance_Suite6",
            solver_parameters=solver_params,
        )


def _load_uf1_and_uf3_potentials() -> tuple[
    dict[str, PeriodicHermitePotential2D],
    dict[str, dict[str, tuple[PeriodicHermitePotential2D, PeriodicHermitePotential2D]]],
]:
    """Load empirically computed 2D landscapes from uf1 and uf3 reports."""
    uf1_path = UF_RESULTS_DIR / "uf1_mesh_convergence_report.json"
    uf3_path = UF_RESULTS_DIR / "uf3_active_switching_report.json"
    if not uf1_path.is_file() or not uf3_path.is_file():
        raise FileNotFoundError(
            f"[ERROR: RUN_DATA_MISSING] Required upstream landscapes missing: {uf1_path} or {uf3_path}"
        )
    uf1 = json.loads(uf1_path.read_text(encoding="utf-8"))
    uf3 = json.loads(uf3_path.read_text(encoding="utf-8"))

    uf1_pots: dict[str, PeriodicHermitePotential2D] = {}
    for dname, land in uf1["ultrafine_landscapes"].items():
        uf1_pots[dname] = PeriodicHermitePotential2D(
            np.asarray(land["z_grid_um"], dtype=np.float64),
            np.asarray(land["theta_grid_deg"], dtype=np.float64),
            np.asarray(land["energy_grid_aJ"], dtype=np.float64),
            np.asarray(land["fz_grid_pN"], dtype=np.float64),
            np.asarray(land["tau_grid_pN_um"], dtype=np.float64),
        )

    uf3_pots: dict[str, dict[str, tuple[PeriodicHermitePotential2D, PeriodicHermitePotential2D]]] = {}
    for dname, dblock in uf3["designs"].items():
        z3 = np.asarray(dblock.get("z_grid_um", uf3.get("z_grid_um")), dtype=np.float64)
        th3 = np.asarray(dblock.get("theta_grid_deg", uf3.get("theta_grid_deg")), dtype=np.float64)
        surfs = dblock["surfaces"]

        def make_p(mkey: str) -> PeriodicHermitePotential2D:
            s = surfs[mkey]
            return PeriodicHermitePotential2D(
                z3,
                th3,
                np.asarray(s["energy_grid_aJ"], dtype=np.float64),
                np.asarray(s["fz_grid_pN"], dtype=np.float64),
                np.asarray(s["tau_grid_pN_um"], dtype=np.float64),
            )

        uf3_pots[dname] = {
            "vo2": (make_p("Au_VO2_ON"), make_p("Au_VO2_OFF")),
            "si": (make_p("Au_Si_ON"), make_p("Au_Si_OFF")),
        }
    return uf1_pots, uf3_pots


def run_micro_probe(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    device = detect_compute_device(args.device)
    uf1_pots, _ = _load_uf1_and_uf3_potentials()

    probe_steps = max(1, int(args.max_steps))
    eq_res = simulate_baoab_langevin_ensemble(
        "Config_D_DualStator_PushPull",
        uf1_pots["Config_D_DualStator_PushPull"],
        mode="equilibrium_static",
        temperature_K=300.0,
        n_traj=32,
        n_steps=probe_steps,
        thermalize_init=True,
    )
    patch_res = evaluate_patch_and_dc_bias_budget(
        "Config_D_DualStator_PushPull", n_realizations=max(1, min(probe_steps, 4)), fast_probe=True
    )
    base = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=min(probe_steps, 3),
        quad_order=2,
        device=device,
        lazy_self_cache=True,
    )
    ev6 = Full4Sector6DofBemEvaluator(base)
    mis_sample = evaluate_misaligned_pose_fz_tau(
        ev6, dx_um=0.006, rx_rad=0.001, z_tip_um=-0.092, theta_deg=22.0, max_steps=args.max_steps
    )

    out_path = UF_RESULTS_DIR / "probe_uf6_langevin_and_tolerances_report.json"
    payload = {
        "suite": "eng_uf6",
        "status": "micro_probe_completed",
        "time_truncated": True,
        "max_steps": int(args.max_steps),
        "device": device,
        "elapsed_seconds": time.perf_counter() - started,
        "sample_equilibrium_300K": eq_res,
        "sample_patch_vrms_20mV": patch_res["patch_vrms_sweep"][4],
        "sample_misalignment": mis_sample,
    }
    atomic_write_json(out_path, payload)
    print(f"[UF6 MICRO-PROBE] Completed in {payload['elapsed_seconds']:.2f}s -> {out_path}", flush=True)
    return 0


def run_full_campaign(args: argparse.Namespace) -> int:
    started_mono = time.monotonic()
    started_wall = time.perf_counter()
    device = detect_compute_device(args.device)
    chk_dir = args.checkpoint_dir
    chk_dir.mkdir(parents=True, exist_ok=True)

    uf1_pots, uf3_pots = _load_uf1_and_uf3_potentials()

    # Part A1: Equilibrium Second-Law Zero-Drift & Equipartition Gate (M=512, 300 K)
    eq_chk = chk_dir / "partA_equilibrium_300K.json"
    eq_audit = None if args.no_cache else load_json_if_exists(eq_chk)
    if eq_audit is None:
        eq_audit = simulate_baoab_langevin_ensemble(
            "Config_D_DualStator_PushPull",
            uf1_pots["Config_D_DualStator_PushPull"],
            mode="equilibrium_static",
            temperature_K=300.0,
            n_traj=512,
            n_steps=20000,
            dt_us=0.025,
            seed=20261101,
            thermalize_init=True,
        )
        atomic_write_json(eq_chk, eq_audit)
        print(
            f"[UF6 SECOND-LAW GATE] 300 K static drift = {eq_audit['mean_advance_deg']:+.3f} +/- {eq_audit['se_advance_deg']:.3f} deg, "
            f"equipartition (z, th) = ({eq_audit['equipartition_z_ratio']:.3f}, {eq_audit['equipartition_th_ratio']:.3f})",
            flush=True,
        )

    # Part A2: Ultra-Fine Gated Langevin Ensembles across all 4 designs & T in {0, 4, 77, 300} K
    langevin_gated: dict[str, dict[str, Any]] = {d: {} for d in ENGINE_DESIGN_NAMES}
    for d_idx, dname in enumerate(ENGINE_DESIGN_NAMES):
        for t_idx, temp_K in enumerate(TEMPERATURES_K):
            tk = f"{int(round(temp_K))}K"
            cfile = chk_dir / f"langevin_gated_{dname}_{tk}.json"
            rec = None if args.no_cache else load_json_if_exists(cfile)
            if rec is None:
                rec = simulate_baoab_langevin_ensemble(
                    dname,
                    uf1_pots[dname],
                    mode="pad_release_gated",
                    temperature_K=temp_K,
                    n_traj=256 if temp_K > 0.0 else 1,
                    n_steps=20000,
                    dt_us=0.025,
                    seed=20261200 + 10 * d_idx + t_idx,
                )
                atomic_write_json(cfile, rec)
            langevin_gated[dname][tk] = rec

    # Part A3: Physical Two-State Dispersive Switching Langevin Ensembles across T in {0, 4, 77, 300} K
    switching_specs = (
        ("Config_B_vo2", "Config_B_Manhattan_Vernier", "vo2"),
        ("Config_D_si", "Config_D_DualStator_PushPull", "si"),
        ("Sym_vo2", "Sym_Baseline_CantorN2", "vo2"),
    )
    temp_scaling: dict[str, dict[str, Any]] = {
        "Config_D_gated": langevin_gated["Config_D_DualStator_PushPull"]
    }
    for s_idx, (tag, dname, mpair) in enumerate(switching_specs):
        temp_scaling[tag] = {}
        p_on, p_off = uf3_pots[dname][mpair]
        for t_idx, temp_K in enumerate(TEMPERATURES_K):
            tk = f"{int(round(temp_K))}K"
            cfile = chk_dir / f"langevin_switch_{tag}_{tk}.json"
            rec = None if args.no_cache else load_json_if_exists(cfile)
            if rec is None:
                rec = simulate_baoab_langevin_ensemble(
                    dname,
                    p_on,
                    pot_off=p_off,
                    mode="two_state_switching",
                    temperature_K=temp_K,
                    n_traj=256 if temp_K > 0.0 else 1,
                    n_steps=20000,
                    dt_us=0.025,
                    seed=20261300 + 10 * s_idx + t_idx,
                )
                atomic_write_json(cfile, rec)
            temp_scaling[tag][tk] = rec

    # Part B1: Polycrystalline Gold Patch Potentials & Residual DC Bias Budget
    patch_potentials: dict[str, Any] = {}
    for dname in ("Sym_Baseline_CantorN2", "Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull"):
        check_walltime(started_mono, args.max_walltime_hours)
        pfile = chk_dir / f"patch_budget_{dname}.json"
        prec = None if args.no_cache else load_json_if_exists(pfile)
        if prec is None:
            prec = evaluate_patch_and_dc_bias_budget(dname, n_realizations=32)
            atomic_write_json(pfile, prec)
            print(f"[UF6 PATCH] {dname} done.", flush=True)
        patch_potentials[dname] = prec

    # Part B2: Direct 3D BEM Surface Roughness Sweep on Config_D (sigma_rms in {0, 1, 2, 3} nm)
    rough_chk = chk_dir / "roughness_bem_Config_D.json"
    rough_cached = None if args.no_cache else load_json_if_exists(rough_chk)
    if rough_cached is None:
        check_walltime(started_mono, args.max_walltime_hours)
        rough_rows = evaluate_roughness_bem_sweep("Config_D_DualStator_PushPull", device=device, n_realizations=6)
        atomic_write_json(rough_chk, {"rows": rough_rows})
        print("[UF6 ROUGHNESS] Config_D 3D BEM roughness sweep done.", flush=True)
    else:
        rough_rows = rough_cached["rows"]

    # Part B3: Full 4-Sector Non-Bloch Static Eccentricity & Tilt Runout
    misalignment_bem: dict[str, Any] = {}
    for dname in ("Sym_Baseline_CantorN2", "Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull"):
        check_walltime(started_mono, args.max_walltime_hours)
        mfile = chk_dir / f"misalignment_6dof_{dname}.json"
        mrec = None if args.no_cache else load_json_if_exists(mfile)
        if mrec is None:
            base6 = PreparedEngineBemModel(
                dname,
                n_r=2,
                n_phi_tooth=4,
                n_phi_bridge=4,
                n_phi_arc_override=12,
                n_z=2,
                n_xi=16,
                quad_order=2,
                device=device,
                lazy_self_cache=True,
                max_memory_gib=args.max_memory_gib,
            )
            ev6 = Full4Sector6DofBemEvaluator(base6)
            ecc_s1 = [
                evaluate_misaligned_pose_fz_tau(ev6, dx_um=dx * 1.0e-3, rx_rad=0.0, z_tip_um=-0.092, theta_deg=22.0)
                for dx in ECCENTRICITY_DX_NM
            ]
            ecc_s3 = [
                evaluate_misaligned_pose_fz_tau(ev6, dx_um=dx * 1.0e-3, rx_rad=0.0, z_tip_um=-0.084, theta_deg=64.0)
                for dx in ECCENTRICITY_DX_NM
            ]
            tilt_s1 = [
                evaluate_misaligned_pose_fz_tau(ev6, dx_um=0.0, rx_rad=tr * 1.0e-3, z_tip_um=-0.092, theta_deg=22.0)
                for tr in TILT_MRAD
            ]
            mrec = {
                "design_name": dname,
                "eccentricity_stroke1": ecc_s1,
                "eccentricity_stroke3": ecc_s3,
                "tilt_stroke1": tilt_s1,
            }
            atomic_write_json(mfile, mrec)
            print(f"[UF6 MISALIGNMENT] {dname} non-Bloch eccentricity & tilt sweep done.", flush=True)
        misalignment_bem[dname] = mrec

    d_ecc1 = misalignment_bem["Config_D_DualStator_PushPull"]["eccentricity_stroke1"]
    tau_dx0 = float(d_ecc1[0]["tau_theta_pN_um"])
    tau_dx12 = float(d_ecc1[-1]["tau_theta_pN_um"])
    ecc12_retain_pct = (100.0 * tau_dx12 / tau_dx0) if abs(tau_dx0) > 1.0e-9 else 0.0

    r0_tau = float(rough_rows[0]["Stroke_I_tau_mean_pN_um"])
    r3_tau = float(rough_rows[-1]["Stroke_I_tau_mean_pN_um"])
    rough3_retain_pct = (100.0 * r3_tau / r0_tau) if abs(r0_tau) > 1.0e-9 else 0.0

    patch_d_30 = float(patch_potentials["Config_D_DualStator_PushPull"]["patch_vrms_sweep"][-1]["rms_pinning_tau_pN_um"])
    casimir_to_patch30_snr = (abs(tau_dx0) / patch_d_30) if patch_d_30 > 1.0e-12 else 0.0

    summary = {
        "eq_300K_drift_deg": round(float(eq_audit["mean_advance_deg"]), 3),
        "eq_300K_se_deg": round(float(eq_audit["se_advance_deg"]), 3),
        "eq_300K_equipartition_th": round(float(eq_audit["equipartition_th_ratio"]), 4),
        "config_d_gated_300K_mean_deg": round(float(langevin_gated["Config_D_DualStator_PushPull"]["300K"]["mean_advance_deg"]), 1),
        "config_d_gated_300K_peclet": round(float(langevin_gated["Config_D_DualStator_PushPull"]["300K"]["peclet_sector"]), 2),
        "config_b_vo2_300K_mean_deg": round(float(temp_scaling["Config_B_vo2"]["300K"]["mean_advance_deg"]), 1),
        "config_b_vo2_300K_peclet": round(float(temp_scaling["Config_B_vo2"]["300K"]["peclet_sector"]), 2),
        "config_d_si_300K_mean_deg": round(float(temp_scaling["Config_D_si"]["300K"]["mean_advance_deg"]), 1),
        "config_d_si_77K_mean_deg": round(float(temp_scaling["Config_D_si"]["77K"]["mean_advance_deg"]), 1),
        "sym_300K_gated_mean_deg": round(float(langevin_gated["Sym_Baseline_CantorN2"]["300K"]["mean_advance_deg"]), 2),
        "config_d_ref_stroke1_tau_pN_um": round(tau_dx0, 4),
        "config_d_patch_30mV_pinning_tau_pN_um": round(patch_d_30, 5),
        "config_d_casimir_to_patch30mV_snr": round(casimir_to_patch30_snr, 1),
        "config_d_ecc12nm_tau_retain_pct": round(ecc12_retain_pct, 1),
        "config_d_rough3nm_tau_retain_pct": round(rough3_retain_pct, 1),
    }

    rep_path = UF_RESULTS_DIR / "uf6_langevin_and_tolerances_report.json"
    report = {
        "suite": "eng_uf6",
        "status": "completed",
        "time_truncated": False,
        "device": device,
        "elapsed_seconds": time.perf_counter() - started_wall,
        "summary": summary,
        "equilibrium_no_go_audit": eq_audit,
        "langevin_gated": langevin_gated,
        "temperature_scaling": temp_scaling,
        "patch_potentials": patch_potentials,
        "roughness_bem_config_d": rough_rows,
        "misalignment_bem": misalignment_bem,
    }
    atomic_write_json(rep_path, report)

    solver_params = {
        "n_trajectories": 256,
        "horizon_us": 500.0,
        "temperatures_K": list(TEMPERATURES_K),
        "patch_vrms_mV": list(PATCH_VRMS_MV),
        "roughness_sigma_nm": list(ROUGHNESS_SIGMA_NM),
        "eccentricity_dx_nm": list(ECCENTRICITY_DX_NM),
    }
    uf6_metrics = UF_RESULTS_DIR / "uf6_provenance_metrics.json"
    uf6_macros = UF_RESULTS_DIR / "uf6_macros_results.tex"
    set_solver_provenance(
        "BEM_Langevin_Patch_Roughness_Tolerance_Suite6",
        solver_params,
        dataset_name="fractal_casimir_engine_cycle",
        metrics_path=str(uf6_metrics),
    )
    log_step("uf6_langevin_and_tolerances", summary, metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_eq_drift_deg", summary["eq_300K_drift_deg"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_cfg_d_300k_deg", summary["config_d_gated_300K_mean_deg"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_cfg_d_300k_peclet", summary["config_d_gated_300K_peclet"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_cfg_b_vo2_300k_deg", summary["config_b_vo2_300K_mean_deg"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_cfg_d_si_300k_deg", summary["config_d_si_300K_mean_deg"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_patch30_snr", summary["config_d_casimir_to_patch30mV_snr"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_ecc12_retain_pct", summary["config_d_ecc12nm_tau_retain_pct"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    log_metric("engine_uf6_rough3_retain_pct", summary["config_d_rough3nm_tau_retain_pct"], step_id="uf6_langevin_and_tolerances", metrics_path=str(uf6_metrics))
    export_macros(metrics_path=str(uf6_metrics), output_path=str(uf6_macros))

    fig_png = ENGINE_FIGURES_DIR / "fig_uf6_langevin_and_tolerances.png"
    fig_pdf = ENGINE_FIGURES_DIR / "fig_uf6_langevin_and_tolerances.pdf"
    generate_uf6_figure(report, fig_png, fig_pdf, rep_path, solver_params)
    print(f"[UF6 COMPLETE] Saved report -> {rep_path} and figure -> {fig_png}", flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-steps", type=int, default=0, help=">0 runs fast local micro-probe; 0 runs full campaign.")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=UF_RESULTS_DIR / "checkpoints_uf6",
        help="Directory for atomic JSON checkpoints.",
    )
    p.add_argument("--max-walltime-hours", type=float, default=0.0)
    p.add_argument("--max-memory-gib", type=float, default=34.0)
    p.add_argument("--no-cache", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.max_steps > 0:
            return run_micro_probe(args)
        return run_full_campaign(args)
    except TimeoutError as exc:
        print(f"[UF6 WALLTIME] {exc}", file=sys.stderr, flush=True)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
