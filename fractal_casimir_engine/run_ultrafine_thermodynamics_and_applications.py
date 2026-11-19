#!/usr/bin/env python3
"""Suite 7 (eng_uf7): Stochastic Thermodynamics, Multi-Tier Efficiency, & Practical Applications.

Grounded strictly on the post-bugfix Ultra-Fine 3D BEM landscapes cached in ``uf1`` and ``uf3``
plus the exact 3D ``CurvilinearPrism`` / panel meshes in ``geometries.py``:

  1. Part A (Loaded Motor Curves & Steady-State First-Law Shaft Efficiency):
     2-DOF underdamped BAOAB Langevin integration under opposing external shaft load torque
     tau_load >= 0 across unloaded (tau_load = 0) through stall (tau_load >= tau_stall),
     verifying discrete BAOAB kick energy conservation and O(dt^2) symplectic First-Law
     balance on the limit cycle while extracting stall torque tau_stall, no-load speed omega_0,
     maximum shaft power P_max, and loaded thermodynamic shaft efficiency eta_shaft(tau_load*).
  2. Part B (Finite-Temperature Stochastic Thermodynamics & TUR Audit):
     Steady-state medium entropy production rate dS_tot/dt = <dQ_bath/dt> / T and
     Thermodynamic Uncertainty Relation (TUR) product
       Q_TUR = [Var(Delta theta) / <Delta theta>^2] * [<Delta S_tot> / (2 k_B)] >= 1
     across T in {4, 77, 300} K and unloaded vs optimal-load operating points.
  3. Part C (Three-Tier Physical Wall-Plug Efficiency Budget):
     Exact geometric stator modulation volume/capacitance energy accounting comparing:
       (i) VO2 thin-film thermal Mott switching (latent + sensible enthalpy vs Carnot ceiling),
       (ii) Photodoped SOI Si optical carrier injection (from BEM Drude wp = 2.15 eV & threshold),
       (iii) Capacitive / 2D-Dirac graphene gate modulation (unrecovered vs resonant tank Q = 50).
  4. Part D (Quantitative Practical NEMS Application Benchmarks):
       (i) Zero-field cryogenic (4 K / 77 K) all-optical discrete 90-deg stepper & passive
           non-volatile Casimir detent latch (jitter, torsional stiffness, Kramers retention),
       (ii) Self-calibrated Knudsen spinning-rotor vacuum gauge (exact Epstein 1924 diffuse
           molecular drag integrated over the 3D BEM rotor mesh) & biomolecular torque benchmark,
       (iii) Wafer-scale chiral metasurface array scaling (areal torque/power density, kHz
           modulation bandwidth, and optical thermal budget).
"""

from __future__ import annotations

import argparse
import datetime
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

from fractal_casimir_engine.bem_cycle_solver import (
    DISPERSIVE_ENGINE_MATERIALS,
    detect_compute_device,
)
from fractal_casimir_engine.geometries import (
    ENGINE_R_MAX_UM,
    ENGINE_R_MIN_UM,
    ENGINE_Z_TIP_MAX_UM,
    ENGINE_Z_TIP_MIN_UM,
    SECTOR_DEG,
    build_engine_surface_mesh,
    canonical_cantor_n2_tracks,
)
from fractal_casimir_engine.run_engine_cycle_mapping import (
    PeriodicHermitePotential2D,
    rotor_inertia_properties,
)
from fractal_casimir_engine.run_ultrafine_langevin_and_tolerances import (
    _gate_scale_batch,
    _release_window_mask,
    eval_hermite_batch,
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

# CODATA 2018 physical constants (exact SI)
KB_J_PER_K: float = 1.380649e-23
ELEMENTARY_CHARGE_C: float = 1.602176634e-19
HBAR_J_S: float = 1.054571817e-34
ELECTRON_MASS_KG: float = 9.1093837015e-31
EPSILON_0_F_PER_M: float = 8.8541878128e-12
AVOGADRO_PER_MOL: float = 6.02214076e23
N2_MOLECULAR_MASS_KG: float = 0.0280134 / AVOGADRO_PER_MOL  # 4.65173e-26 kg

# Physical switching & bearing parameters matching uf1 / uf3 / uf6
Z_EQ_UM: float = -0.084
K_FLEX_N_PER_M: float = 4.0e-5
GAMMA_Z_N_S_PER_M: float = 2.5e-12
GAMMA_TH_NM_S_PER_RAD: float = 6.0e-25
K_STOP_PN_PER_UM: float = 180.0 / 0.010
RELEASE_HALF_WIDTH_DEG: float = 11.5

KNUDSEN_PRESSURES_PA: tuple[float, ...] = (1.0e-3, 1.0e-1, 1.0, 10.0, 30.0, 100.0, 300.0, 1000.0)


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


def load_json_required(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Required upstream BEM report missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def check_walltime(started_mono: float, max_walltime_hours: float) -> None:
    if max_walltime_hours > 0.0 and (time.monotonic() - started_mono) >= max_walltime_hours * 3600.0:
        raise TimeoutError("Approaching walltime limit; stopping cleanly.")


def _aux_potential_and_force_batch(z_u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (U_aux_aJ, F_aux_pN) for axial suspension spring + soft clearance stops."""
    dz_m = (z_u - Z_EQ_UM) * 1.0e-6
    u_spring_aj = 0.5 * K_FLEX_N_PER_M * (dz_m * dz_m) * 1.0e18
    f_spring_pn = -K_FLEX_N_PER_M * dz_m * 1.0e12

    u_stop_aj = np.where(
        z_u < ENGINE_Z_TIP_MIN_UM,
        0.5 * K_STOP_PN_PER_UM * ((ENGINE_Z_TIP_MIN_UM - z_u) ** 2),
        np.where(z_u > ENGINE_Z_TIP_MAX_UM, 0.5 * K_STOP_PN_PER_UM * ((z_u - ENGINE_Z_TIP_MAX_UM) ** 2), 0.0),
    )
    f_stop_pn = np.where(
        z_u < ENGINE_Z_TIP_MIN_UM,
        K_STOP_PN_PER_UM * (ENGINE_Z_TIP_MIN_UM - z_u),
        np.where(z_u > ENGINE_Z_TIP_MAX_UM, -K_STOP_PN_PER_UM * (z_u - ENGINE_Z_TIP_MAX_UM), 0.0),
    )
    return (u_spring_aj + u_stop_aj), (f_spring_pn + f_stop_pn)


def build_potential_from_grid(surf: Mapping[str, Any], z_grid: np.ndarray, th_grid: np.ndarray) -> PeriodicHermitePotential2D:
    return PeriodicHermitePotential2D(
        np.asarray(z_grid, dtype=np.float64),
        np.asarray(th_grid, dtype=np.float64),
        np.asarray(surf["energy_grid_aJ"], dtype=np.float64),
        np.asarray(surf["fz_grid_pN"], dtype=np.float64),
        np.asarray(surf["tau_grid_pN_um"], dtype=np.float64),
    )


def simulate_loaded_thermodynamic_ensemble(
    design_name: str,
    pot_on: PeriodicHermitePotential2D,
    *,
    pot_off: PeriodicHermitePotential2D | None = None,
    mode: str,
    temperature_K: float,
    tau_load_pN_um: float = 0.0,
    gamma_th_override: float | None = None,
    n_traj: int = 128,
    n_steps: int = 12000,
    dt_us: float = 0.04,
    warmup_frac: float = 0.25,
    pre_equilibrate: bool = True,
    seed: int = 20261118,
) -> dict[str, Any]:
    """Run 2-DOF underdamped BAOAB Langevin with discrete kick energy & Second-Law accounting.

    Over the steady-state window [step_ss, n_steps], tracks per trajectory:
      - Exact discrete BAOAB B1+B2 kick work against external shaft load:
          W_shaft = sum (half_dt * omega_mid_B * tau_load)
      - Exact BAOAB O-step heat dissipated into thermal bath:
          Q_bath = sum [ K(v^-) - K(v^+) ]
      - Electromagnetic Casimir input work:
          * ``two_state_switching``: free-energy jumps Delta E_switch = E_new - E_old at seam
            crossings (net W_em_net = sum Delta E_switch and unrecuperated W_pump_pos = sum max(0, Delta E)).
          * ``pad_release_gated``: exact discrete B1+B2 kick work injected by gated Casimir forces
            W_em_net = sum (half_dt * vz_mid_B * 1e6 * F_z_cas + half_dt * omega_mid_B * tau_cas).
      - Symplectic O(dt^2) First-Law splitting residual:
          R_1st = | <Delta E_sys_ss + W_shaft_ss + Q_bath_ss - W_em_net_ss> |
        plus exact discrete BAOAB kinetic-work identity residual (< 1e-12 aJ).
      - Medium entropy production <Delta S_tot> = <Q_bath_ss> / T and TUR product:
          Q_TUR = [Var(Delta theta_ss) / <Delta theta_ss>^2] * [<Delta S_tot> / (2 k_B)]
    """
    if mode not in ("two_state_switching", "pad_release_gated"):
        raise ValueError(f"Unsupported mode: {mode}")
    if mode == "two_state_switching" and pot_off is None:
        raise ValueError("pot_off is required for two_state_switching.")
    if temperature_K < 0.0 or not math.isfinite(temperature_K):
        raise ValueError("temperature_K must be finite and nonnegative.")
    if tau_load_pN_um < 0.0 or not math.isfinite(tau_load_pN_um):
        raise ValueError("tau_load_pN_um must be finite and nonnegative.")
    if dt_us <= 0.0 or not math.isfinite(dt_us):
        raise ValueError("dt_us must be finite and strictly positive.")
    if n_traj < 1 or n_steps < 10:
        raise ValueError("n_traj >= 1 and n_steps >= 10 required.")
    if not (0.05 <= warmup_frac <= 0.80):
        raise ValueError("warmup_frac must lie in [0.05, 0.80].")

    props = rotor_inertia_properties(design_name)
    mass_kg = float(props["mass_kg"])
    iz_kg_m2 = float(props["iz_kg_m2"])
    gamma_th = float(GAMMA_TH_NM_S_PER_RAD if gamma_th_override is None else gamma_th_override)
    if gamma_th <= 0.0 or not math.isfinite(gamma_th):
        raise ValueError("gamma_th must be finite and positive.")

    dt_s = float(dt_us) * 1.0e-6
    half_dt = 0.5 * dt_s
    kbt_J = KB_J_PER_K * float(temperature_K)
    kbt_aJ = kbt_J * 1.0e18

    cz = math.exp(-(GAMMA_Z_N_S_PER_M / mass_kg) * dt_s)
    cth = math.exp(-(gamma_th / iz_kg_m2) * dt_s)
    sig_vz = math.sqrt((kbt_J / mass_kg) * max(0.0, 1.0 - cz * cz)) if kbt_J > 0.0 else 0.0
    sig_om = math.sqrt((kbt_J / iz_kg_m2) * max(0.0, 1.0 - cth * cth)) if kbt_J > 0.0 else 0.0

    rng = np.random.default_rng(seed)
    inv_m_pN = 1.0e-12 / mass_kg
    inv_iz_pNum = 1.0e-18 / iz_kg_m2

    def eval_casimir(z_u: np.ndarray, th_r: np.ndarray, off_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if mode == "two_state_switching":
            assert pot_off is not None
            e_on, fz_on, tau_on = eval_hermite_batch(pot_on, z_u, th_r)
            e_off, fz_off, tau_off = eval_hermite_batch(pot_off, z_u, th_r)
            return (
                np.where(off_mask, e_off, e_on),
                np.where(off_mask, fz_off, fz_on),
                np.where(off_mask, tau_off, tau_on),
            )
        e_on, fz_on, tau_on = eval_hermite_batch(pot_on, z_u, th_r)
        sc = _gate_scale_batch(th_r)
        return e_on, fz_on * sc, tau_on * sc

    z_init_val = -0.097
    th_init_val = math.radians(9.0)
    vz_init_mean = 0.0
    om_init_mean = 0.0

    if pre_equilibrate and n_steps >= 400:
        # Single-trajectory pilot relaxation (dt_pilot <= 0.08 us, symplectic-safe) over >= 2.0 * (I_z / gamma_th)
        tau_relax_s = iz_kg_m2 / gamma_th
        dt_p = min(0.08e-6, max(dt_s, 2.0 * dt_s))
        half_dt_p = 0.5 * dt_p
        cz_p = math.exp(-(GAMMA_Z_N_S_PER_M / mass_kg) * dt_p)
        cth_p = math.exp(-(gamma_th / iz_kg_m2) * dt_p)
        n_pilot_steps = min(22000, max(2000, int(round(2.2 * tau_relax_s / dt_p))))
        zp = np.array([z_init_val], dtype=np.float64)
        thp = np.array([th_init_val], dtype=np.float64)
        vzp = np.zeros(1, dtype=np.float64)
        omp = np.zeros(1, dtype=np.float64)
        off_p = _release_window_mask(thp, half_width_deg=RELEASE_HALF_WIDTH_DEG)
        _, fz_cp, tau_cp = eval_casimir(zp, thp, off_p)
        _, f_auxp = _aux_potential_and_force_batch(zp)
        fzt_p = fz_cp + f_auxp
        taut_p = tau_cp - tau_load_pN_um
        om_tail_acc = 0.0
        vz_tail_acc = 0.0
        n_tail = max(1, n_pilot_steps // 5)
        for pstep in range(1, n_pilot_steps + 1):
            vzp += half_dt_p * fzt_p * inv_m_pN
            omp += half_dt_p * taut_p * inv_iz_pNum
            zp += half_dt_p * vzp * 1.0e6
            thp += half_dt_p * omp
            vzp *= cz_p
            omp *= cth_p
            zp += half_dt_p * vzp * 1.0e6
            thp += half_dt_p * omp
            if mode == "two_state_switching":
                off_p = _release_window_mask(thp, half_width_deg=RELEASE_HALF_WIDTH_DEG)
            _, fz_cp, tau_cp = eval_casimir(zp, thp, off_p)
            _, f_auxp = _aux_potential_and_force_batch(zp)
            fzt_p = fz_cp + f_auxp
            taut_p = tau_cp - tau_load_pN_um
            vzp += half_dt_p * fzt_p * inv_m_pN
            omp += half_dt_p * taut_p * inv_iz_pNum
            if pstep > n_pilot_steps - n_tail:
                om_tail_acc += float(omp[0])
                vz_tail_acc += float(vzp[0])
        z_init_val = float(zp[0])
        th_init_val = float(np.mod(thp[0], math.radians(SECTOR_DEG)))
        vz_init_mean = vz_tail_acc / n_tail
        om_init_mean = om_tail_acc / n_tail

    z_um = np.full(n_traj, z_init_val, dtype=np.float64)
    th_rad = np.full(n_traj, th_init_val, dtype=np.float64)
    if kbt_J > 0.0:
        vz = rng.normal(vz_init_mean, math.sqrt(kbt_J / mass_kg), size=n_traj)
        om = rng.normal(om_init_mean, math.sqrt(kbt_J / iz_kg_m2), size=n_traj)
    else:
        vz = np.full(n_traj, vz_init_mean, dtype=np.float64)
        om = np.full(n_traj, om_init_mean, dtype=np.float64)

    is_off = _release_window_mask(th_rad, half_width_deg=RELEASE_HALF_WIDTH_DEG)

    def sys_energy_aj(z_u: np.ndarray, vz_v: np.ndarray, om_v: np.ndarray, e_cas: np.ndarray) -> np.ndarray:
        ke_aj = (0.5 * mass_kg * vz_v * vz_v + 0.5 * iz_kg_m2 * om_v * om_v) * 1.0e18
        u_aux_aj, _ = _aux_potential_and_force_batch(z_u)
        if mode == "two_state_switching":
            return ke_aj + u_aux_aj + e_cas
        # For non-potential gated forces, system mechanical energy is K + U_aux
        return ke_aj + u_aux_aj

    e_cas_cur, fz_cas, tau_cas = eval_casimir(z_um, th_rad, is_off)
    _, f_aux = _aux_potential_and_force_batch(z_um)
    fz_tot = fz_cas + f_aux
    tau_tot = tau_cas - tau_load_pN_um

    step_ss = int(round(n_steps * warmup_frac))
    th_ss_start = th_rad.copy()
    e_sys_ss_start = sys_energy_aj(z_um, vz, om, e_cas_cur)
    ke_ss_start = (0.5 * mass_kg * vz * vz + 0.5 * iz_kg_m2 * om * om) * 1.0e18

    q_bath_ss_aj = np.zeros(n_traj, dtype=np.float64)
    w_shaft_ss_aj = np.zeros(n_traj, dtype=np.float64)
    w_cas_kick_ss_aj = np.zeros(n_traj, dtype=np.float64)
    w_aux_kick_ss_aj = np.zeros(n_traj, dtype=np.float64)
    w_em_net_ss_aj = np.zeros(n_traj, dtype=np.float64)
    w_pump_pos_ss_aj = np.zeros(n_traj, dtype=np.float64)
    n_switches_ss = np.zeros(n_traj, dtype=np.int64)

    for step in range(1, n_steps + 1):
        in_ss = step > step_ss
        fz_cas_prev = fz_cas
        tau_cas_prev = tau_cas
        f_aux_prev = f_aux

        # B1 (exact discrete kick work = m * v_mid * dv = half_dt * v_mid * F)
        vz0, om0 = vz.copy(), om.copy()
        vz += half_dt * fz_tot * inv_m_pN
        om += half_dt * tau_tot * inv_iz_pNum
        if in_ss:
            vz_mid1 = 0.5 * (vz0 + vz) * 1.0e6  # um/s
            om_mid1 = 0.5 * (om0 + om)
            w_cas_kick_ss_aj += half_dt * (vz_mid1 * fz_cas_prev + om_mid1 * tau_cas_prev)
            w_aux_kick_ss_aj += half_dt * (vz_mid1 * f_aux_prev)
            w_shaft_ss_aj += half_dt * (om_mid1 * tau_load_pN_um)

        # A1
        z_um += half_dt * vz * 1.0e6
        th_rad += half_dt * om
        # O (exact heat into bath dQ_bath = K(v^-) - K(v^+))
        ke_pre_aj = (0.5 * mass_kg * vz * vz + 0.5 * iz_kg_m2 * om * om) * 1.0e18
        if sig_vz > 0.0:
            vz = cz * vz + sig_vz * rng.standard_normal(n_traj)
            om = cth * om + sig_om * rng.standard_normal(n_traj)
        else:
            vz *= cz
            om *= cth
        if in_ss:
            ke_post_aj = (0.5 * mass_kg * vz * vz + 0.5 * iz_kg_m2 * om * om) * 1.0e18
            q_bath_ss_aj += ke_pre_aj - ke_post_aj

        # A2
        z_um += half_dt * vz * 1.0e6
        th_rad += half_dt * om

        # Evaluate Casimir forces at new configuration on CURRENT surface before checking switch
        e_cas_new_same, fz_cas, tau_cas = eval_casimir(z_um, th_rad, is_off)
        _, f_aux = _aux_potential_and_force_batch(z_um)
        fz_tot = fz_cas + f_aux
        tau_tot = tau_cas - tau_load_pN_um

        # B2 (exact discrete second half-kick work)
        vz2, om2 = vz.copy(), om.copy()
        vz += half_dt * fz_tot * inv_m_pN
        om += half_dt * tau_tot * inv_iz_pNum
        if in_ss:
            vz_mid2 = 0.5 * (vz2 + vz) * 1.0e6
            om_mid2 = 0.5 * (om2 + om)
            w_cas_kick_ss_aj += half_dt * (vz_mid2 * fz_cas + om_mid2 * tau_cas)
            w_aux_kick_ss_aj += half_dt * (vz_mid2 * f_aux)
            w_shaft_ss_aj += half_dt * (om_mid2 * tau_load_pN_um)

        # Check discrete state switch at end of Verlet step (instantaneous potential jump at fixed q)
        if mode == "two_state_switching":
            now_off = _release_window_mask(th_rad, half_width_deg=RELEASE_HALF_WIDTH_DEG)
            switched = now_off != is_off
            if np.any(switched):
                assert pot_off is not None
                is_off = now_off
                e_cas_after, fz_cas, tau_cas = eval_casimir(z_um, th_rad, is_off)
                if in_ss:
                    de_sw = np.where(switched, e_cas_after - e_cas_new_same, 0.0)
                    w_em_net_ss_aj += de_sw
                    w_pump_pos_ss_aj += np.maximum(0.0, de_sw)
                    n_switches_ss += switched.astype(np.int64)
                e_cas_cur = e_cas_after
                fz_tot = fz_cas + f_aux
                tau_tot = tau_cas - tau_load_pN_um
            else:
                e_cas_cur = e_cas_new_same
        else:
            e_cas_cur = e_cas_new_same

        if step == step_ss:
            th_ss_start = th_rad.copy()
            e_sys_ss_start = sys_energy_aj(z_um, vz, om, e_cas_cur)
            ke_ss_start = (0.5 * mass_kg * vz * vz + 0.5 * iz_kg_m2 * om * om) * 1.0e18

    dt_ss_s = (n_steps - step_ss) * dt_s
    dth_ss_rad = th_rad - th_ss_start
    dth_ss_deg = np.rad2deg(dth_ss_rad)
    e_sys_ss_end = sys_energy_aj(z_um, vz, om, e_cas_cur)
    ke_ss_end = (0.5 * mass_kg * vz * vz + 0.5 * iz_kg_m2 * om * om) * 1.0e18
    de_sys_ss_aj = e_sys_ss_end - e_sys_ss_start

    if mode == "pad_release_gated":
        w_em_net_ss_aj = w_cas_kick_ss_aj.copy()
        w_pump_pos_ss_aj = np.maximum(0.0, w_em_net_ss_aj)

    # Exact discrete BAOAB kinetic-work identity: (K_end - K_start) + W_shaft + Q_bath == W_cas_kick + W_aux_kick
    discrete_kick_res_aj = abs(
        float(np.mean((ke_ss_end - ke_ss_start) + w_shaft_ss_aj + q_bath_ss_aj - w_cas_kick_ss_aj - w_aux_kick_ss_aj))
    )

    mean_de_sys = float(np.mean(de_sys_ss_aj))
    mean_w_shaft = float(np.mean(w_shaft_ss_aj))
    mean_q_bath = float(np.mean(q_bath_ss_aj))
    mean_w_em_net = float(np.mean(w_em_net_ss_aj))
    mean_w_pump_pos = float(np.mean(w_pump_pos_ss_aj))
    # O(dt^2) symplectic potential-splitting First-Law residual
    first_law_res_aj = abs(mean_de_sys + mean_w_shaft + mean_q_bath - mean_w_em_net)

    mean_dth_rad = float(np.mean(dth_ss_rad))
    var_dth_rad2 = float(np.var(dth_ss_rad, ddof=1)) if n_traj > 1 else 0.0
    omega_ss_rad_s = mean_dth_rad / dt_ss_s
    se_omega_rad_s = (float(np.std(dth_ss_rad, ddof=1)) / math.sqrt(n_traj) / dt_ss_s) if n_traj > 1 else 0.0

    # 1 aJ / s = 1e-18 W = 1 aW = 1e-3 fW = 1000 zW
    p_shaft_aw = mean_w_shaft / dt_ss_s
    p_shaft_fw = p_shaft_aw * 1.0e-3
    p_shaft_zw = p_shaft_aw * 1.0e3
    p_em_net_zw = (mean_w_em_net / dt_ss_s) * 1.0e3
    p_pump_pos_zw = (mean_w_pump_pos / dt_ss_s) * 1.0e3
    p_bath_zw = (mean_q_bath / dt_ss_s) * 1.0e3

    # True steady-state limit-cycle input consumed (mean_w_em_net - mean_de_sys == mean_w_shaft + mean_q_bath)
    w_in_consumed_aj = mean_w_shaft + mean_q_bath
    eta_shaft_rev = (
        min(1.0, max(0.0, mean_w_shaft / w_in_consumed_aj))
        if (w_in_consumed_aj > 1.0e-6 and mean_w_shaft > 0.0)
        else 0.0
    )
    w_pump_consumed_aj = max(w_in_consumed_aj, mean_w_pump_pos - min(0.0, mean_de_sys))
    eta_shaft_irrev = (
        min(1.0, max(0.0, mean_w_shaft / w_pump_consumed_aj))
        if (w_pump_consumed_aj > 1.0e-6 and mean_w_shaft > 0.0)
        else 0.0
    )

    if kbt_aJ > 0.0:
        delta_s_kb = mean_q_bath / kbt_aJ
        sigma_dot_kb_per_ms = (delta_s_kb / dt_ss_s) * 1.0e-3
    else:
        delta_s_kb = 0.0
        sigma_dot_kb_per_ms = 0.0

    rel_var_th = (var_dth_rad2 / (mean_dth_rad * mean_dth_rad)) if abs(mean_dth_rad) > 1.0e-6 else None
    q_tur = (rel_var_th * 0.5 * delta_s_kb) if (rel_var_th is not None and delta_s_kb > 0.0 and n_traj > 1) else None
    eta_tur = (1.0 / q_tur) if (q_tur is not None and q_tur > 0.0) else None

    return {
        "design_name": design_name,
        "mode": mode,
        "actuation_regime": "autonomous_limit_cycle_motor" if pre_equilibrate else "pulsed_self_latching_stepper",
        "temperature_K": float(temperature_K),
        "tau_load_pN_um": float(tau_load_pN_um),
        "tau_load_pN_nm": float(tau_load_pN_um * 1.0e3),
        "n_trajectories": int(n_traj),
        "window_ss_us": round(dt_ss_s * 1.0e6, 2),
        "omega_ss_krad_s": omega_ss_rad_s * 1.0e-3,
        "se_omega_krad_s": se_omega_rad_s * 1.0e-3,
        "rpm_ss": omega_ss_rad_s * 60.0 / (2.0 * math.pi),
        "mean_advance_ss_deg": float(np.mean(dth_ss_deg)),
        "mean_switches_ss": float(np.mean(n_switches_ss)),
        "w_shaft_ss_aJ": mean_w_shaft,
        "w_em_net_ss_aJ": mean_w_em_net,
        "w_pump_pos_ss_aJ": mean_w_pump_pos,
        "q_bath_ss_aJ": mean_q_bath,
        "de_sys_ss_aJ": mean_de_sys,
        "discrete_kick_balance_residual_aJ": discrete_kick_res_aj,
        "first_law_residual_aJ": first_law_res_aj,
        "p_shaft_fW": p_shaft_fw,
        "p_shaft_aW": p_shaft_aw,
        "p_shaft_zW": p_shaft_zw,
        "p_em_net_zW": p_em_net_zw,
        "p_pump_pos_zW": p_pump_pos_zw,
        "p_bath_zW": p_bath_zw,
        "eta_shaft_rev_pct": 100.0 * eta_shaft_rev,
        "eta_shaft_irrev_pct": 100.0 * eta_shaft_irrev,
        "delta_s_tot_kB": delta_s_kb,
        "entropy_rate_kB_per_ms": sigma_dot_kb_per_ms,
        "rel_variance_theta": rel_var_th,
        "q_tur": q_tur,
        "eta_tur_pct": (100.0 * eta_tur) if eta_tur is not None else None,
    }


def sweep_loaded_motor_curve(
    label: str,
    design_name: str,
    pot_on: PeriodicHermitePotential2D,
    *,
    pot_off: PeriodicHermitePotential2D | None,
    mode: str,
    temperature_K: float,
    pre_equilibrate: bool = True,
    n_traj: int = 96,
    n_steps: int = 12000,
    n_load_points: int = 9,
    seed_base: int = 20261118,
    started_mono: float = 0.0,
    max_walltime_hours: float = 0.0,
) -> dict[str, Any]:
    """Bracket stall torque adaptively from unloaded omega_0 and map the full motor curve."""
    unloaded = simulate_loaded_thermodynamic_ensemble(
        design_name,
        pot_on,
        pot_off=pot_off,
        mode=mode,
        temperature_K=temperature_K,
        tau_load_pN_um=0.0,
        pre_equilibrate=pre_equilibrate,
        n_traj=n_traj,
        n_steps=n_steps,
        seed=seed_base,
    )
    if unloaded["omega_ss_krad_s"] <= 0.0:
        raise RuntimeError(
            f"Unloaded motor speed is non-positive ({unloaded['omega_ss_krad_s']:.3f} krad/s) for {label}; "
            "cannot measure forward stall torque."
        )
    omega0_rad_s = unloaded["omega_ss_krad_s"] * 1.0e3
    # Characteristic viscous stall estimate tau_visc = gamma_th * omega_0 (in pN*um = 1e18 N*m)
    tau_visc_pN_um = GAMMA_TH_NM_S_PER_RAD * omega0_rad_s * 1.0e18
    tau_max = max(0.012, 1.30 * tau_visc_pN_um)

    # Probe upper bracket and expand until non-positive speed (true stall bracket) is observed
    probe_step = 0
    probe_hi = simulate_loaded_thermodynamic_ensemble(
        design_name,
        pot_on,
        pot_off=pot_off,
        mode=mode,
        temperature_K=temperature_K,
        tau_load_pN_um=tau_max,
        pre_equilibrate=pre_equilibrate,
        n_traj=max(32, n_traj // 2),
        n_steps=n_steps,
        seed=seed_base + 99,
    )
    while probe_hi["omega_ss_krad_s"] > 0.0 and tau_max < 10.0:
        probe_step += 1
        tau_max *= 1.45
        probe_hi = simulate_loaded_thermodynamic_ensemble(
            design_name,
            pot_on,
            pot_off=pot_off,
            mode=mode,
            temperature_K=temperature_K,
            tau_load_pN_um=tau_max,
            pre_equilibrate=pre_equilibrate,
            n_traj=max(32, n_traj // 2),
            n_steps=n_steps,
            seed=seed_base + 101 + probe_step,
        )

    tau_grid = np.linspace(0.0, tau_max, n_load_points, dtype=np.float64)
    points: list[dict[str, Any]] = [unloaded]
    for idx, tau_val in enumerate(tau_grid[1:], start=1):
        check_walltime(started_mono, max_walltime_hours)
        pt = simulate_loaded_thermodynamic_ensemble(
            design_name,
            pot_on,
            pot_off=pot_off,
            mode=mode,
            temperature_K=temperature_K,
            tau_load_pN_um=float(tau_val),
            pre_equilibrate=pre_equilibrate,
            n_traj=n_traj,
            n_steps=n_steps,
            seed=seed_base + idx * 7,
        )
        points.append(pt)

    # Ensure full ensemble also crosses <= 0.0 (in case full n_traj has slightly higher mean than half-n_traj probe)
    extra_idx = 0
    while points[-1]["omega_ss_krad_s"] > 0.0 and tau_max < 10.0 and extra_idx < 5:
        extra_idx += 1
        tau_max *= 1.25
        check_walltime(started_mono, max_walltime_hours)
        points.append(
            simulate_loaded_thermodynamic_ensemble(
                design_name,
                pot_on,
                pot_off=pot_off,
                mode=mode,
                temperature_K=temperature_K,
                tau_load_pN_um=float(tau_max),
                pre_equilibrate=pre_equilibrate,
                n_traj=n_traj,
                n_steps=n_steps,
                seed=seed_base + 200 + extra_idx * 7,
            )
        )

    taus = np.array([p["tau_load_pN_um"] for p in points], dtype=np.float64)
    omegas = np.array([p["omega_ss_krad_s"] for p in points], dtype=np.float64)
    p_shaft = np.array([p["p_shaft_zW"] for p in points], dtype=np.float64)

    # Strictly bracketed zero-crossing interpolation for stall torque tau_stall where omega(tau_stall) == 0
    neg_indices = np.where(omegas <= 0.0)[0]
    if len(neg_indices) == 0:
        raise RuntimeError(f"Failed to bracket stall torque up to tau_max={tau_max:.4f} pN*um for {label}.")
    i1 = int(neg_indices[0])
    i0 = max(0, i1 - 1)
    w0, w1 = float(omegas[i0]), float(omegas[i1])
    t0, t1 = float(taus[i0]), float(taus[i1])
    tau_stall = t0 + (0.0 - w0) * (t1 - t0) / (w1 - w0) if w1 != w0 else t1

    best_idx = int(np.argmax(p_shaft))
    opt_pt = points[best_idx]
    kbt_300_pN_nm = KB_J_PER_K * 300.0 * 1.0e21  # 4.141947 pN*nm

    return {
        "label": label,
        "design_name": design_name,
        "mode": mode,
        "actuation_regime": "autonomous_limit_cycle_motor" if pre_equilibrate else "pulsed_self_latching_stepper",
        "temperature_K": float(temperature_K),
        "omega_no_load_krad_s": float(unloaded["omega_ss_krad_s"]),
        "rpm_no_load": float(unloaded["rpm_ss"]),
        "tau_stall_pN_um": float(tau_stall),
        "tau_stall_pN_nm": float(tau_stall * 1.0e3),
        "tau_stall_kBT300_per_rad": float((tau_stall * 1.0e3) / kbt_300_pN_nm),
        "tau_opt_pN_um": float(opt_pt["tau_load_pN_um"]),
        "p_shaft_max_fW": float(opt_pt["p_shaft_fW"]),
        "p_shaft_max_aW": float(opt_pt["p_shaft_aW"]),
        "p_shaft_max_zW": float(opt_pt["p_shaft_zW"]),
        "eta_shaft_rev_at_max_power_pct": float(opt_pt["eta_shaft_rev_pct"]),
        "eta_shaft_irrev_at_max_power_pct": float(opt_pt["eta_shaft_irrev_pct"]),
        "eta_shaft_rev_peak_pct": float(max(p["eta_shaft_rev_pct"] for p in points)),
        "eta_shaft_irrev_peak_pct": float(max(p["eta_shaft_irrev_pct"] for p in points)),
        "max_first_law_residual_aJ": float(max(p["first_law_residual_aJ"] for p in points)),
        "q_tur_unloaded": unloaded["q_tur"],
        "q_tur_at_max_power": opt_pt["q_tur"],
        "points": points,
    }


def compute_wall_plug_efficiency_budget(
    motor_curves: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute exact 3-tier physical wall-plug efficiency budget from Cantor_N2 stator pad geometry."""
    tracks = canonical_cantor_n2_tracks(vernier=True)
    # Full 4-sector annular slot area across all 3 Cantor tracks (um^2)
    area_tracks_full_um2 = sum(math.pi * (t.r_slot_out**2 - t.r_slot_in**2) for t in tracks)
    # Active release-seam angular fraction: two 23-deg release windows per 90-deg sector
    seam_fraction = (2.0 * (2.0 * RELEASE_HALF_WIDTH_DEG)) / SECTOR_DEG  # 46 / 90 = 0.5111
    area_single_stator_um2 = area_tracks_full_um2 * seam_fraction
    area_dual_stator_um2 = 2.0 * area_single_stator_um2

    # Work delivered per 90-deg sector at maximum shaft power: W_sector_aJ = tau_opt * (pi / 2)
    sector_rad = math.radians(SECTOR_DEG)
    b_vo2_curve = motor_curves["Config_B_VO2_300K"]
    d_si_curve = motor_curves["Config_D_Si_300K"]
    d_gated_curve = motor_curves["Config_D_Gated_300K"]

    w_shaft_sector_vo2_aj = float(b_vo2_curve["tau_opt_pN_um"]) * sector_rad
    w_shaft_sector_si_aj = float(d_si_curve["tau_opt_pN_um"]) * sector_rad
    w_shaft_sector_gated_aj = float(d_gated_curve["tau_opt_pN_um"]) * sector_rad

    # 1. Thermal VO2 Mott phase-change thin-film stator (Berglund & Guggenheim PR 185, 1022 (1969)):
    #    t_vo2 = 25 nm, T_bath = 300 K -> T_high = 345 K across T_c = 341 K,
    #    C_v = 3.0 J/(cm^3 K), Delta H_latent = 51.4 J/cm^3; 2 switching cycles per 90-deg sector.
    t_vo2_um = 0.025
    vol_vo2_cm3 = (area_single_stator_um2 * t_vo2_um) * 1.0e-12  # 1 um^3 = 1e-12 cm^3
    t_bath_k, t_vo2_high_k = 300.0, 345.0
    enthalpy_per_cm3_J = 3.0 * (t_vo2_high_k - t_bath_k) + 51.4  # 186.4 J/cm^3
    # Two ON->OFF->ON thermal pulses per 90-deg sector
    q_in_vo2_sector_aj = 2.0 * vol_vo2_cm3 * enthalpy_per_cm3_J * 1.0e18
    carnot_vo2_pct = 100.0 * (1.0 - t_bath_k / t_vo2_high_k)
    eta_wall_vo2 = w_shaft_sector_vo2_aj / q_in_vo2_sector_aj

    # 2. All-optical photodoped SOI Si stator (exact Drude wp_eV = 2.15 eV from bem_cycle_solver.py):
    #    wp^2 = n_eh * e^2 / (eps_0 * m_opt^*), m_opt^* = 0.15 m_e in Si, pump photon 1.55 eV (800 nm), t_soi = 20 nm.
    wp_si_ev = float(DISPERSIVE_ENGINE_MATERIALS["silicon_photodoped"]["wp_eV"])
    wp_rad_s = (wp_si_ev * ELEMENTARY_CHARGE_C) / HBAR_J_S
    m_opt_si_kg = 0.15 * ELECTRON_MASS_KG
    n_eh_m3 = EPSILON_0_F_PER_M * m_opt_si_kg * (wp_rad_s**2) / (ELEMENTARY_CHARGE_C**2)
    n_eh_cm3 = n_eh_m3 * 1.0e-6
    t_soi_um = 0.020
    vol_soi_m3 = (area_dual_stator_um2 * t_soi_um) * 1.0e-18
    e_photon_J = 1.55 * ELEMENTARY_CHARGE_C
    # Two optical carrier pulses per 90-deg sector
    e_opt_si_bem_sector_aj = 2.0 * vol_soi_m3 * n_eh_m3 * e_photon_J * 1.0e18
    eta_wall_si_bem = w_shaft_sector_si_aj / e_opt_si_bem_sector_aj

    # Moderate carrier-modulation SOI regime (Delta n_eh = 1e19 cm^-3)
    e_opt_si_mod_sector_aj = e_opt_si_bem_sector_aj * (1.0e19 / n_eh_cm3)
    eta_wall_si_mod = w_shaft_sector_si_aj / e_opt_si_mod_sector_aj

    # 3. Capacitive / 2D-Dirac graphene gate on 20 nm SiO2 (eps_ox = 3.9, V_g = 0.5 V, 2 pulses/sector):
    eps_ox = 3.9
    t_ox_m = 20.0e-9
    c_gate_F = EPSILON_0_F_PER_M * eps_ox * (area_dual_stator_um2 * 1.0e-12) / t_ox_m
    v_gate_V = 0.50
    e_cap_stored_per_switch_aj = 0.5 * c_gate_F * (v_gate_V**2) * 1.0e18
    e_cap_unrecovered_sector_aj = 2.0 * (2.0 * e_cap_stored_per_switch_aj)  # CV^2 per charge-discharge cycle
    q_tank = 50.0
    e_cap_resonant_sector_aj = 2.0 * ((math.pi / q_tank) * e_cap_stored_per_switch_aj) + w_shaft_sector_gated_aj
    eta_wall_cap_unrec = w_shaft_sector_gated_aj / e_cap_unrecovered_sector_aj
    eta_wall_cap_resonant = w_shaft_sector_gated_aj / e_cap_resonant_sector_aj

    return {
        "active_geometry": {
            "tracks_annular_area_um2": round(area_tracks_full_um2, 4),
            "release_seam_duty_fraction": round(seam_fraction, 4),
            "single_stator_active_area_um2": round(area_single_stator_um2, 4),
            "dual_stator_active_area_um2": round(area_dual_stator_um2, 4),
        },
        "modalities": {
            "VO2_Thermal_Mott_25nm": {
                "film_thickness_nm": 25.0,
                "t_low_K": t_bath_k,
                "t_high_K": t_vo2_high_k,
                "carnot_ceiling_pct": round(carnot_vo2_pct, 2),
                "input_energy_per_sector_fJ": round(q_in_vo2_sector_aj * 1.0e-3, 3),
                "shaft_work_per_sector_aJ": round(w_shaft_sector_vo2_aj, 5),
                "internal_shaft_efficiency_pct": round(float(b_vo2_curve["eta_shaft_rev_at_max_power_pct"]), 2),
                "wall_plug_efficiency": eta_wall_vo2,
            },
            "Silicon_PhotoDoped_BEM_wp2p15eV_20nm": {
                "soi_thickness_nm": 20.0,
                "wp_eV": wp_si_ev,
                "carrier_density_cm3": n_eh_cm3,
                "photon_energy_eV": 1.55,
                "input_energy_per_sector_fJ": round(e_opt_si_bem_sector_aj * 1.0e-3, 3),
                "threshold_1e19_input_per_sector_fJ": round(e_opt_si_mod_sector_aj * 1.0e-3, 3),
                "shaft_work_per_sector_aJ": round(w_shaft_sector_si_aj, 5),
                "internal_shaft_efficiency_pct": round(float(d_si_curve["eta_shaft_rev_at_max_power_pct"]), 2),
                "wall_plug_efficiency_bem_density": eta_wall_si_bem,
                "wall_plug_efficiency_1e19_density": eta_wall_si_mod,
            },
            "Graphene_2D_Capacitive_Gate_0p5V": {
                "gate_capacitance_fF": round(c_gate_F * 1.0e15, 3),
                "gate_voltage_V": v_gate_V,
                "resonant_tank_Q": q_tank,
                "unrecovered_input_per_sector_aJ": round(e_cap_unrecovered_sector_aj, 3),
                "resonant_input_per_sector_aJ": round(e_cap_resonant_sector_aj, 3),
                "shaft_work_per_sector_aJ": round(w_shaft_sector_gated_aj, 5),
                "internal_shaft_efficiency_pct": round(float(d_gated_curve["eta_shaft_rev_at_max_power_pct"]), 2),
                "wall_plug_efficiency_unrecovered_pct": 100.0 * eta_wall_cap_unrec,
                "wall_plug_efficiency_resonant_pct": 100.0 * eta_wall_cap_resonant,
                "resonant_vs_vo2_efficiency_gain": eta_wall_cap_resonant / max(1.0e-30, eta_wall_vo2),
            },
        },
    }


def evaluate_cryogenic_stepper_and_passive_latch(
    design_name: str,
    pot_on: PeriodicHermitePotential2D,
    pot_off: PeriodicHermitePotential2D,
    *,
    n_traj: int = 128,
    hold_steps: int = 4000,
) -> dict[str, Any]:
    """Benchmark Application 1: Zero-field cryogenic optical stepper & passive non-volatile Casimir detent."""
    props = rotor_inertia_properties(design_name)
    iz_kg_m2 = float(props["iz_kg_m2"])
    mass_kg = float(props["mass_kg"])

    # Map equilibrium axial relaxation z_eq*(theta) and effective 1D azimuthal pinning profile U_eff(theta)
    th_deg_dense = np.linspace(0.0, SECTOR_DEG, 1800, endpoint=False, dtype=np.float64)
    th_rad_dense = np.deg2rad(th_deg_dense)
    z_scan = np.linspace(ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MAX_UM, 65, dtype=np.float64)
    zz, tt = np.meshgrid(z_scan, th_rad_dense, indexing="ij")
    e_grid, _, _ = eval_hermite_batch(pot_on, zz.ravel(), tt.ravel())
    u_aux, _ = _aux_potential_and_force_batch(zz.ravel())
    u_tot_2d = (e_grid + u_aux).reshape(z_scan.size, th_deg_dense.size)
    iz_min = np.argmin(u_tot_2d, axis=0)
    u_1d_aj = u_tot_2d[iz_min, np.arange(th_deg_dense.size)]
    z_min_path_um = z_scan[iz_min]

    idx_well = int(np.argmin(u_1d_aj))
    idx_bar = int(np.argmax(u_1d_aj))
    theta_lock_deg = float(th_deg_dense[idx_well])
    z_lock_um = float(z_min_path_um[idx_well])
    barrier_pin_aj = float(u_1d_aj[idx_bar] - u_1d_aj[idx_well])
    barrier_pin_mev = barrier_pin_aj / (ELEMENTARY_CHARGE_C * 1.0e-3 * 1.0e18)

    # Local torsional stiffness kappa_theta = d^2 U / dtheta^2 at passive detent minimum (pN*um / rad)
    dth_r = float(th_rad_dense[1] - th_rad_dense[0])
    im1 = (idx_well - 1) % th_deg_dense.size
    ip1 = (idx_well + 1) % th_deg_dense.size
    kappa_th_pN_um_per_rad = max(1.0e-6, float(u_1d_aj[ip1] - 2.0 * u_1d_aj[idx_well] + u_1d_aj[im1]) / (dth_r * dth_r))
    omega_libration_rad_s = math.sqrt((kappa_th_pN_um_per_rad * 1.0e-18) / iz_kg_m2)

    temp_rows: dict[str, Any] = {}
    dt_s = 0.025e-6
    half_dt = 0.5 * dt_s
    cz = math.exp(-(GAMMA_Z_N_S_PER_M / mass_kg) * dt_s)
    cth = math.exp(-(GAMMA_TH_NM_S_PER_RAD / iz_kg_m2) * dt_s)
    inv_m_pN = 1.0e-12 / mass_kg
    inv_iz_pNum = 1.0e-18 / iz_kg_m2

    for temp_K in (4.0, 77.0, 300.0):
        kbt_J = KB_J_PER_K * temp_K
        kbt_aj = kbt_J * 1.0e18
        barrier_kbt = barrier_pin_aj / kbt_aj
        # Kramers escape lifetime tau_esc = (2*pi / omega_0) * exp(Delta U / k_B T) (capped at 1e30 s for JSON safety)
        log_tau = math.log(2.0 * math.pi / omega_libration_rad_s) + min(70.0, barrier_kbt)
        tau_retention_s = min(1.0e30, math.exp(log_tau))

        # Direct BAOAB hold test inside the passive zero-power detent well (zero switching power!)
        rng = np.random.default_rng(int(9100 + temp_K))
        sig_vz = math.sqrt((kbt_J / mass_kg) * max(0.0, 1.0 - cz * cz))
        sig_om = math.sqrt((kbt_J / iz_kg_m2) * max(0.0, 1.0 - cth * cth))
        z_u = np.full(n_traj, z_lock_um, dtype=np.float64)
        th_r = np.full(n_traj, math.radians(theta_lock_deg), dtype=np.float64)
        vz = rng.normal(0.0, math.sqrt(kbt_J / mass_kg), size=n_traj)
        om = rng.normal(0.0, math.sqrt(kbt_J / iz_kg_m2), size=n_traj)
        _, fz_c, tau_c = eval_hermite_batch(pot_on, z_u, th_r)
        _, f_aux = _aux_potential_and_force_batch(z_u)
        fz_tot = fz_c + f_aux
        for _ in range(hold_steps):
            vz += half_dt * fz_tot * inv_m_pN
            om += half_dt * tau_c * inv_iz_pNum
            z_u += half_dt * vz * 1.0e6
            th_r += half_dt * om
            vz = cz * vz + sig_vz * rng.standard_normal(n_traj)
            om = cth * om + sig_om * rng.standard_normal(n_traj)
            z_u += half_dt * vz * 1.0e6
            th_r += half_dt * om
            _, fz_c, tau_c = eval_hermite_batch(pot_on, z_u, th_r)
            _, f_aux = _aux_potential_and_force_batch(z_u)
            fz_tot = fz_c + f_aux
            vz += half_dt * fz_tot * inv_m_pN
            om += half_dt * tau_c * inv_iz_pNum

        disp_deg = np.rad2deg(th_r) - theta_lock_deg
        rms_jitter_deg = float(np.std(disp_deg, ddof=1)) if n_traj > 1 else 0.0
        escaped_frac = float(np.mean(np.abs(disp_deg) > 45.0))

        # Active pulsed step-and-latch simulation: 500 us optical actuation burst from axial preload
        step_sim = simulate_loaded_thermodynamic_ensemble(
            design_name,
            pot_on,
            pot_off=pot_off,
            mode="two_state_switching",
            temperature_K=temp_K,
            tau_load_pN_um=0.0,
            pre_equilibrate=False,
            n_traj=n_traj,
            n_steps=12500,
            dt_us=0.04,
            warmup_frac=0.20,
            seed=int(9500 + temp_K),
        )
        t_90deg_step_us = (
            math.radians(SECTOR_DEG) / (step_sim["omega_ss_krad_s"] * 1.0e3) * 1.0e6
            if step_sim["omega_ss_krad_s"] > 0.1
            else None
        )

        temp_rows[f"{int(temp_K)}K"] = {
            "temperature_K": temp_K,
            "barrier_kBT": round(barrier_kbt, 2),
            "rms_pointing_jitter_deg": round(rms_jitter_deg, 4),
            "rms_pointing_jitter_mrad": round(math.radians(rms_jitter_deg) * 1.0e3, 3),
            "hold_escape_fraction": escaped_frac,
            "kramers_retention_s": tau_retention_s,
            "optical_90deg_step_time_us": round(t_90deg_step_us, 2) if t_90deg_step_us is not None else None,
        }

    return {
        "design_name": design_name,
        "passive_lock_angle_deg": round(theta_lock_deg, 2),
        "passive_lock_z_tip_um": round(z_lock_um, 4),
        "pinning_barrier_aJ": round(barrier_pin_aj, 4),
        "pinning_barrier_meV": round(barrier_pin_mev, 1),
        "torsional_stiffness_pN_um_per_rad": round(kappa_th_pN_um_per_rad, 4),
        "libration_freq_MHz": round(omega_libration_rad_s / (2.0 * math.pi) * 1.0e-6, 3),
        "standby_power_W": 0.0,
        "stray_electric_field_V_per_m": 0.0,
        "stray_magnetic_field_T": 0.0,
        "temperatures": temp_rows,
    }


def compute_epstein_knudsen_rotor_drag_coeff(design_name: str, temperature_K: float = 300.0) -> dict[str, float]:
    """Integrate exact free-molecular Epstein (1924) diffuse gas rotational drag over the 3D BEM rotor mesh.

    For a surface panel i with area A_i, centroid (x_i, y_i, z_i), lever arm r_i = hypot(x_i, y_i),
    and azimuthal unit vector e_theta = (-y_i/r_i, x_i/r_i, 0):
      gamma_gas(P) = P * sqrt(m_N2 / (2 * pi * k_B * T)) * sum_i A_i * r_i^2 * [1 + (1 + pi/4) * (n_i . e_theta)^2]
    """
    mesh = build_engine_surface_mesh(
        design_name,
        z_tip_um=-0.084,
        theta_deg=0.0,
        n_r=2,
        n_phi_tooth=4,
        n_phi_bridge=4,
        n_z=2,
    )
    # 1. Active 4-sector 3D BEM Cantor rotor teeth (normal + shear momentum transfer)
    geom_moment_m4 = 0.0
    total_rotor_area_um2 = 0.0
    for panel in mesh.rotor:
        verts = np.asarray(panel.vertices, dtype=np.float64)
        cent = np.mean(verts, axis=0)  # in um
        r_um = math.hypot(float(cent[0]), float(cent[1]))
        area_um2 = float(panel.area)
        total_rotor_area_um2 += 4.0 * area_um2
        if r_um < 1.0e-9:
            continue
        eth_x = -float(cent[1]) / r_um
        eth_y = float(cent[0]) / r_um
        n_vec = panel.normal
        n_dot_eth = float(n_vec[0]) * eth_x + float(n_vec[1]) * eth_y
        weight = 1.0 + (1.0 + 0.25 * math.pi) * (n_dot_eth * n_dot_eth)
        # 4 sectors; area_um2 * r_um^2 -> (1e-12 m^2) * (1e-12 m^2) = 1e-24 m^4
        geom_moment_m4 += 4.0 * area_um2 * (r_um * r_um) * weight * 1.0e-24

    # 2. Supporting 25%-fill annular spider carrier frame (matching rotor_inertia_properties: hub_thick = 35 nm)
    hub_thick_um = 0.035
    area_spider_top_bot_um2 = 2.0 * 0.25 * math.pi * (ENGINE_R_MAX_UM**2 - ENGINE_R_MIN_UM**2)
    moment_spider_top_bot_m4 = 2.0 * 0.25 * 0.5 * math.pi * (ENGINE_R_MAX_UM**4 - ENGINE_R_MIN_UM**4) * 1.0e-24
    area_spider_rims_um2 = 2.0 * math.pi * (ENGINE_R_MAX_UM + ENGINE_R_MIN_UM) * hub_thick_um
    moment_spider_rims_m4 = 2.0 * math.pi * (ENGINE_R_MAX_UM**3 + ENGINE_R_MIN_UM**3) * hub_thick_um * 1.0e-24

    total_rotor_area_um2 += area_spider_top_bot_um2 + area_spider_rims_um2
    geom_moment_m4 += moment_spider_top_bot_m4 + moment_spider_rims_m4

    kinetic_prefactor_s_per_m = math.sqrt(N2_MOLECULAR_MASS_KG / (2.0 * math.pi * KB_J_PER_K * temperature_K))
    # gamma_gas per Pascal in N*m*s/rad
    c_drag_per_Pa = kinetic_prefactor_s_per_m * geom_moment_m4
    p_half_Pa = GAMMA_TH_NM_S_PER_RAD / c_drag_per_Pa
    return {
        "rotor_surface_area_um2": round(total_rotor_area_um2, 4),
        "epstein_geom_moment_m4": geom_moment_m4,
        "gamma_gas_per_Pa_Nm_s_rad": c_drag_per_Pa,
        "half_speed_crossover_pressure_Pa": p_half_Pa,
        "half_speed_crossover_mTorr": p_half_Pa * 7.50062,
    }


def evaluate_knudsen_gauge_and_rheometer(
    design_name: str,
    pot_on: PeriodicHermitePotential2D,
    motor_curve_300k: Mapping[str, Any],
    *,
    n_traj: int = 64,
    n_steps: int = 16000,
    started_mono: float = 0.0,
    max_walltime_hours: float = 0.0,
) -> dict[str, Any]:
    """Benchmark Application 2: Knudsen rarefied-gas vacuum manometer & biomolecular torsional rheometer."""
    epstein = compute_epstein_knudsen_rotor_drag_coeff(design_name, temperature_K=300.0)
    c_drag = float(epstein["gamma_gas_per_Pa_Nm_s_rad"])

    pressure_rows: list[dict[str, float]] = []
    omega_uhv: float | None = None
    for idx, p_pa in enumerate(KNUDSEN_PRESSURES_PA):
        check_walltime(started_mono, max_walltime_hours)
        gamma_tot = GAMMA_TH_NM_S_PER_RAD + c_drag * float(p_pa)
        sim = simulate_loaded_thermodynamic_ensemble(
            design_name,
            pot_on,
            mode="pad_release_gated",
            temperature_K=300.0,
            tau_load_pN_um=0.0,
            gamma_th_override=gamma_tot,
            n_traj=n_traj,
            n_steps=n_steps,
            seed=20261200 + idx * 13,
        )
        if omega_uhv is None:
            omega_uhv = max(1.0e-6, float(sim["omega_ss_krad_s"]))
        # N2 mean free path at 300 K: lambda_mfp ~ (6.6e-3 Pa*m) / P; Kn = lambda / R_outer (1.0 um)
        knudsen_number = (6.6e-3 / float(p_pa)) / 1.0e-6
        pressure_rows.append(
            {
                "pressure_Pa": float(p_pa),
                "pressure_mTorr": round(float(p_pa) * 7.50062, 4),
                "knudsen_number": knudsen_number,
                "gamma_tot_Nm_s_rad": gamma_tot,
                "omega_ss_krad_s": round(float(sim["omega_ss_krad_s"]), 3),
                "se_omega_krad_s": round(float(sim["se_omega_krad_s"]), 3),
                "normalized_speed": round(float(sim["omega_ss_krad_s"]) / omega_uhv, 4),
            }
        )

    tau_stall_pN_nm = float(motor_curve_300k["tau_stall_pN_nm"])
    # Reference single-molecule biological torques (Bryant et al. Nature 424, 338 (2003); Yasuda et al. Cell 93, 1117 (1998))
    dna_overstretch_pN_nm = 34.0
    f1_atpase_stall_pN_nm = 41.0
    bacterial_flagellar_pN_nm = 1260.0

    return {
        "epstein_kinetic_model": epstein,
        "pressure_calibration_curve": pressure_rows,
        "biomolecular_rheometry_comparison": {
            "engine_stall_torque_pN_nm": round(tau_stall_pN_nm, 2),
            "ratio_vs_DNA_supercoiling_34pNnm": round(tau_stall_pN_nm / dna_overstretch_pN_nm, 2),
            "ratio_vs_F1_ATPase_41pNnm": round(tau_stall_pN_nm / f1_atpase_stall_pN_nm, 2),
            "fraction_of_flagellar_motor_1260pNnm": round(tau_stall_pN_nm / bacterial_flagellar_pN_nm, 3),
        },
    }


def compute_metasurface_array_scaling(
    motor_curves: Mapping[str, Mapping[str, Any]],
    wall_plug: Mapping[str, Any],
    cryo_stepper: Mapping[str, Any],
) -> dict[str, Any]:
    """Benchmark Application 3: Wafer-scale 2D chiral nanophotonic metasurface array scaling."""
    # Outer stator radius R_max = 1.10 um -> diameter 2.20 um; 2.50 um pitch leaves 300 nm isolation moat (>> gap)
    pitch_um = 2.50
    cell_area_cm2 = (pitch_um * 1.0e-4) ** 2  # 6.25e-8 cm^2
    rotors_per_cm2 = 1.0 / cell_area_cm2  # 1.60e7 rotors / cm^2

    d_gated = motor_curves["Config_D_Gated_300K"]
    d_si = motor_curves["Config_D_Si_300K"]

    # Collective areal stall torque density (pN*um * rotors/cm^2 -> 1e-18 N*m * rotors/cm^2 -> nN*m / cm^2)
    areal_stall_torque_nNm_cm2 = float(d_gated["tau_stall_pN_um"]) * 1.0e-18 * rotors_per_cm2 * 1.0e9
    areal_shaft_power_gated_pW_cm2 = float(d_gated["p_shaft_max_zW"]) * 1.0e-21 * rotors_per_cm2 * 1.0e12
    areal_shaft_power_si_pW_cm2 = float(d_si["p_shaft_max_zW"]) * 1.0e-21 * rotors_per_cm2 * 1.0e12

    step_time_300k_us = cryo_stepper["temperatures"]["300K"]["optical_90deg_step_time_us"]
    step_time_4k_us = cryo_stepper["temperatures"]["4K"]["optical_90deg_step_time_us"]
    max_mech_bw_khz = (1.0e3 / (2.0 * float(step_time_300k_us))) if step_time_300k_us else 0.0

    # Thermal budget limit under 1.0 W/cm^2 passive Si wafer cooling for threshold SOI optical switching
    e_si_1e19_J_per_step = (
        float(wall_plug["modalities"]["Silicon_PhotoDoped_BEM_wp2p15eV_20nm"]["threshold_1e19_input_per_sector_fJ"])
        * 1.0e-15
    )
    areal_energy_per_step_mJ_cm2 = e_si_1e19_J_per_step * rotors_per_cm2 * 1.0e3
    thermal_limited_rep_rate_Hz_at_1W_cm2 = 1.0 / (e_si_1e19_J_per_step * rotors_per_cm2)

    cap_input_J_per_step = (
        float(wall_plug["modalities"]["Graphene_2D_Capacitive_Gate_0p5V"]["resonant_input_per_sector_aJ"]) * 1.0e-18
    )
    areal_power_2d_gate_at_10kHz_uW_cm2 = cap_input_J_per_step * rotors_per_cm2 * 1.0e4 * 1.0e6

    return {
        "cell_pitch_um": pitch_um,
        "isolation_moat_nm": 300.0,
        "rotors_per_cm2": rotors_per_cm2,
        "areal_stall_torque_nNm_per_cm2": round(areal_stall_torque_nNm_cm2, 4),
        "areal_shaft_power_gated_pW_per_cm2": round(areal_shaft_power_gated_pW_cm2, 3),
        "areal_shaft_power_photo_si_pW_per_cm2": round(areal_shaft_power_si_pW_cm2, 3),
        "optical_90deg_switch_time_300K_us": step_time_300k_us,
        "optical_90deg_switch_time_4K_us": step_time_4k_us,
        "mechanical_modulation_bandwidth_kHz": round(max_mech_bw_khz, 2),
        "soi_1e19_areal_step_fluence_mJ_per_cm2": round(areal_energy_per_step_mJ_cm2, 4),
        "soi_cw_rep_rate_at_1W_cm2_Hz": round(thermal_limited_rep_rate_Hz_at_1W_cm2, 1),
        "graphene_gate_areal_power_at_10kHz_uW_per_cm2": round(areal_power_2d_gate_at_10kHz_uW_cm2, 3),
    }


def generate_uf7_figure(
    report: Mapping[str, Any],
    png_path: Path,
    pdf_path: Path,
    report_path: Path,
) -> None:
    """Render 4-panel publication figure for Thermodynamics, Efficiency, & Practical Applications."""
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 7.5,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 8.2), dpi=300)
    ax_a, ax_b, ax_c, ax_d = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

    # Panel A: Loaded Motor Torque-Speed & Shaft Power Curves (Config D Gated 300K & 4K)
    mc_300 = report["loaded_motor_curves"]["Config_D_Gated_300K"]
    mc_4 = report["loaded_motor_curves"]["Config_D_Gated_4K"]
    tau_300 = [p["tau_load_pN_nm"] for p in mc_300["points"]]
    om_300 = [p["omega_ss_krad_s"] for p in mc_300["points"]]
    pwr_300_fw = [p.get("p_shaft_fW", p["p_shaft_zW"] * 1.0e-6) for p in mc_300["points"]]
    tau_4 = [p["tau_load_pN_nm"] for p in mc_4["points"]]
    om_4 = [p["omega_ss_krad_s"] for p in mc_4["points"]]

    ax_a_r = ax_a.twinx()
    l1 = ax_a.plot(tau_300, om_300, "o-", color="#1f77b4", lw=1.8, ms=4.5, label=r"$\langle\omega\rangle$ (300 K)")
    l2 = ax_a.plot(tau_4, om_4, "s--", color="#4c9be8", lw=1.3, ms=3.8, label=r"$\langle\omega\rangle$ (4 K)")
    l3 = ax_a_r.plot(tau_300, pwr_300_fw, "^-", color="#d62728", lw=1.8, ms=4.8, label=r"$P_{\mathrm{shaft}}$ (300 K)")
    ax_a.axhline(0.0, color="0.5", ls=":", lw=0.9)
    ax_a.set_xlabel(r"External Load Torque $\tau_{\mathrm{load}}$ (pN$\cdot$nm)")
    ax_a.set_ylabel(r"Steady Speed $\langle\omega_{\mathrm{ss}}\rangle$ (krad/s)", color="#1f77b4")
    ax_a_r.set_ylabel(r"Delivered Shaft Power $P_{\mathrm{shaft}}$ (fW)", color="#d62728")
    ax_a.set_title("(a) Loaded Motor Curve & Peak Shaft Power (Config D)")
    lines = l1 + l2 + l3
    ax_a.legend(lines, [ln.get_label() for ln in lines], loc="upper right", frameon=True)
    ax_a.grid(True, alpha=0.25)

    # Panel B: Loaded Thermodynamic Shaft Efficiency & EMP Benchmark
    mc_vo2 = report["loaded_motor_curves"]["Config_B_VO2_300K"]
    mc_si = report["loaded_motor_curves"]["Config_D_Si_300K"]
    for curve, col, mk, lbl in (
        (mc_300, "#1f77b4", "o", "Config D Gated (300 K)"),
        (mc_vo2, "#ff7f0e", "s", r"Config B Au–VO$_2$ (300 K)"),
        (mc_si, "#2ca02c", "^", "Config D Au–photo-Si (300 K)"),
    ):
        ts = max(1.0e-9, float(curve["tau_stall_pN_um"]))
        pts_pos = [p for p in curve["points"] if p["omega_ss_krad_s"] > 0.0]
        x_norm = [p["tau_load_pN_um"] / ts for p in pts_pos]
        y_eta = [p["eta_shaft_rev_pct"] for p in pts_pos]
        ax_b.plot(x_norm, y_eta, marker=mk, ls="-", color=col, lw=1.7, ms=4.5, label=lbl)
    ax_b.axhline(50.0, color="0.35", ls="--", lw=1.0, label="Linear-response EMP bound (50% at 0.5)")
    ax_b.plot([0.5], [50.0], marker="*", color="#d62728", ms=9.0, zorder=5)
    ax_b.set_xlim(0.0, 1.12)
    ax_b.set_ylim(0.0, 96.0)
    ax_b.set_xlabel(r"Normalized Load $\tau_{\mathrm{load}} / \tau_{\mathrm{stall}}$")
    ax_b.set_ylabel(r"Shaft Transduction Efficiency $\eta_{\mathrm{shaft}}$ (%)")
    ax_b.set_title("(b) Thermodynamic Shaft Efficiency vs. Load")
    ax_b.legend(loc="upper left", frameon=True)
    ax_b.grid(True, alpha=0.25)

    # Panel C: Multi-Tier Efficiency Hierarchy & TUR Product Across Temperature
    wp = report["wall_plug_efficiency_budget"]["modalities"]
    tiers = [
        "Internal EMP\nCasimir→Shaft\n(Config D)",
        "TUR Precision\n1 / Q_TUR\n(300 K)",
        "2D Graphene\nGate (Q=50)",
        "Photo-Si SOI\n(1e19 cm^-3)",
        "VO2 Mott\nThermal (25 nm)",
    ]
    vals_pct = [
        max(1.0e-9, float(mc_300["eta_shaft_rev_at_max_power_pct"])),
        max(1.0e-9, float(report["summary"]["cfg_d_gated_300K_tur_eff_pct"])),
        max(1.0e-9, float(wp["Graphene_2D_Capacitive_Gate_0p5V"]["wall_plug_efficiency_resonant_pct"])),
        max(1.0e-9, 100.0 * float(wp["Silicon_PhotoDoped_BEM_wp2p15eV_20nm"]["wall_plug_efficiency_1e19_density"])),
        max(1.0e-9, 100.0 * float(wp["VO2_Thermal_Mott_25nm"]["wall_plug_efficiency"])),
    ]
    colors_c = ["#1f77b4", "#17becf", "#2ca02c", "#9467bd", "#ff7f0e"]
    bars = ax_c.bar(np.arange(len(tiers)), vals_pct, color=colors_c, width=0.58, edgecolor="0.2", lw=0.7)
    ax_c.set_yscale("log")
    ax_c.set_ylim(1.0e-8, 250.0)
    ax_c.set_xticks(np.arange(len(tiers)))
    ax_c.set_xticklabels(tiers, fontsize=7.5)
    ax_c.set_ylabel("Efficiency (%) [log scale]")
    ax_c.set_title("(c) Multi-Tier Transduction vs. Wall-Plug Efficiency")
    for rect, v in zip(bars, vals_pct):
        txt = f"{v:.1f}%" if v >= 0.1 else f"{v:.1e}%"
        ax_c.text(
            rect.get_x() + 0.5 * rect.get_width(),
            v * 1.6,
            txt,
            ha="center",
            va="bottom",
            fontsize=7.2,
        )
    ax_c.grid(True, axis="y", alpha=0.25)

    # Panel D: Practical Application — Knudsen Rarefied-Gas Manometer & Cryo Stepper Inset Text
    kn = report["practical_applications"]["knudsen_vacuum_gauge_and_rheometer"]
    p_pa = [r["pressure_Pa"] for r in kn["pressure_calibration_curve"]]
    w_kn = [r["omega_ss_krad_s"] for r in kn["pressure_calibration_curve"]]
    w_se = [r["se_omega_krad_s"] for r in kn["pressure_calibration_curve"]]
    p_half = float(kn["epstein_kinetic_model"]["half_speed_crossover_pressure_Pa"])

    ax_d.errorbar(p_pa, w_kn, yerr=w_se, fmt="o-", color="#8c564b", lw=1.8, ms=4.8, capsize=2.5, label="3D BEM + Epstein BAOAB (300 K)")
    p_smooth = np.logspace(-3, 3, 200)
    w0 = w_kn[0]
    ax_d.plot(p_smooth, w0 / (1.0 + p_smooth / p_half), "--", color="0.3", lw=1.2, label=rf"Analytical $1/(1 + P/P_{{1/2}})$, $P_{{1/2}}={p_half:.1f}$ Pa")
    ax_d.axvline(p_half, color="#d62728", ls=":", lw=1.1)
    ax_d.set_xscale("log")
    ax_d.set_xlabel(r"Ambient $\mathrm{N}_2$ Pressure $P$ (Pa)")
    ax_d.set_ylabel(r"Steady Rotor Speed $\langle\omega_{\mathrm{ss}}\rangle$ (krad/s)")
    ax_d.set_title("(d) Knudsen Vacuum Manometer & Cryogenic Latch")

    cryo = report["practical_applications"]["cryogenic_optical_stepper_and_latch"]
    j4 = cryo["temperatures"]["4K"]["rms_pointing_jitter_deg"]
    b_mev = cryo["pinning_barrier_meV"]
    stall_atp = kn["biomolecular_rheometry_comparison"]["ratio_vs_F1_ATPase_41pNnm"]
    note = (
        f"4 K Optical Latch:\n"
        f"  $\\Delta U_{{\\mathrm{{pin}}}} = {b_mev:.0f}$ meV\n"
        f"  $\\sigma_\\theta(4\\,\\mathrm{{K}}) = {j4:.3f}^\\circ$\n"
        f"  $\\tau_{{\\mathrm{{stall}}}} = {stall_atp:.1f}\\times$ F$_1$-ATPase"
    )
    ax_d.text(
        0.04,
        0.10,
        note,
        transform=ax_d.transAxes,
        fontsize=7.6,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f8f9fa", "edgecolor": "0.65"},
    )
    ax_d.legend(loc="upper right", frameon=True)
    ax_d.grid(True, alpha=0.25)

    fig.tight_layout()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=300)
    fig.savefig(pdf_path)
    plt.close(fig)

    solver_params = {"suite": "eng_uf7", "dataset": "fractal_casimir_engine_cycle"}
    for fpath in (png_path, pdf_path):
        save_plot_provenance(
            str(fpath),
            str(report_path),
            columns_used=[
                "summary",
                "loaded_motor_curves",
                "stochastic_thermodynamics_tur",
                "wall_plug_efficiency_budget",
                "practical_applications",
            ],
            solver_name="BEM_StochasticThermodynamics_Applications_Suite7",
            solver_parameters=solver_params,
        )
    # Also write stem-level sidecar matching uf1..uf6 convention
    stem_sidecar = png_path.with_suffix(".provenance.json")
    png_sidecar = Path(f"{png_path}.provenance.json")
    if png_sidecar.is_file():
        stem_sidecar.write_bytes(png_sidecar.read_bytes())


def export_uf7_provenance_and_figure(
    report: Mapping[str, Any],
    report_path: Path,
    *,
    results_dir: Path | None = None,
    figures_dir: Path | None = None,
) -> None:
    res_dir = UF_RESULTS_DIR if results_dir is None else results_dir
    fig_dir = ENGINE_FIGURES_DIR if figures_dir is None else figures_dir
    res_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    prov_path = str(res_dir / "uf7_provenance_metrics.json")
    macros_path = str(res_dir / "uf7_macros_results.tex")
    solver_name = "BEM_StochasticThermodynamics_Applications_Suite7"
    solver_params = {
        "dataset": "fractal_casimir_engine_cycle",
        "suite": "eng_uf7",
        "upstream_reports": ["uf1_mesh_convergence_report.json", "uf3_active_switching_report.json"],
    }
    set_solver_provenance(
        solver_name,
        solver_params,
        metrics_path=prov_path,
    )

    s = report["summary"]
    step_id = "uf7_thermodynamics_and_applications"
    log_step(
        step_id,
        {
            "max_first_law_residual_aJ": s["max_first_law_residual_aJ"],
            "min_q_tur": s["min_q_tur_observed"],
            "cfg_d_stall_tau_pN_nm": s["cfg_d_gated_300K_stall_tau_pN_nm"],
            "cfg_d_max_power_zW": s["cfg_d_gated_300K_max_power_zW"],
        },
        metrics_path=prov_path,
    )

    step_4k_val = s.get("cryo_4K_90deg_step_us")
    if step_4k_val is None:
        raise ValueError("cryo_4K_90deg_step_us must be non-null for macro export.")
    metrics_map = {
        "engine_uf7_cfg_d_stall_tau_pnnm": round(float(s["cfg_d_gated_300K_stall_tau_pN_nm"]), 1),
        "engine_uf7_cfg_d_stall_kbt": round(float(s["cfg_d_gated_300K_stall_kBT300"]), 1),
        "engine_uf7_cfg_d_max_power_fw": round(float(s.get("cfg_d_gated_300K_max_power_fW", s["cfg_d_gated_300K_max_power_zW"] * 1.0e-6)), 2),
        "engine_uf7_cfg_b_vo2_max_power_aw": round(float(s.get("cfg_b_vo2_300K_max_power_aW", s["cfg_b_vo2_300K_max_power_zW"] * 1.0e-3)), 1),
        "engine_uf7_cfg_d_si_max_power_aw": round(float(s.get("cfg_d_si_300K_max_power_aW", s["cfg_d_si_300K_max_power_zW"] * 1.0e-3)), 1),
        "engine_uf7_cfg_d_emp_pct": round(float(s["cfg_d_gated_300K_emp_pct"]), 1),
        "engine_uf7_cfg_b_vo2_stall_pnnm": round(float(s["cfg_b_vo2_300K_stall_tau_pN_nm"]), 1),
        "engine_uf7_cfg_b_vo2_emp_pct": round(float(s["cfg_b_vo2_300K_emp_pct"]), 1),
        "engine_uf7_cfg_d_si_stall_pnnm": round(float(s["cfg_d_si_300K_stall_tau_pN_nm"]), 1),
        "engine_uf7_cfg_d_si_emp_pct": round(float(s["cfg_d_si_300K_emp_pct"]), 1),
        "engine_uf7_cfg_d_q_tur_300k": round(float(s["cfg_d_gated_300K_q_tur"]), 2),
        "engine_uf7_cfg_d_tur_eff_pct": round(float(s["cfg_d_gated_300K_tur_eff_pct"]), 1),
        "engine_uf7_max_first_law_res_aj": float(s["max_first_law_residual_aJ"]),
        "engine_uf7_vo2_wall_eff": float(s["vo2_wall_plug_efficiency"]),
        "engine_uf7_si_1e19_wall_eff": float(s["si_1e19_wall_plug_efficiency"]),
        "engine_uf7_graphene_wall_eff_pct": round(float(s["graphene_resonant_wall_plug_pct"]), 2),
        "engine_uf7_cryo_barrier_mev": round(float(s["cryo_pinning_barrier_meV"]), 1),
        "engine_uf7_cryo_4k_jitter_deg": round(float(s["cryo_4K_jitter_deg"]), 3),
        "engine_uf7_cryo_4k_step_us": round(float(step_4k_val), 1),
        "engine_uf7_knudsen_p_half_pa": round(float(s["knudsen_p_half_Pa"]), 1),
        "engine_uf7_atpase_torque_ratio": round(float(s["stall_vs_f1_atpase_ratio"]), 1),
        "engine_uf7_array_rotors_cm2": float(s["array_rotors_per_cm2"]),
        "engine_uf7_array_torque_nnm_cm2": round(float(s["array_stall_torque_nNm_cm2"]), 2),
        "engine_uf7_array_power_pw_cm2": round(float(s["array_gated_power_pW_cm2"]), 1),
        "engine_uf7_array_bw_khz": round(float(s["array_mech_bandwidth_kHz"]), 1),
    }
    for m_key, m_val in metrics_map.items():
        log_metric(m_key, m_val, step_id=step_id, metrics_path=prov_path)

    export_macros(metrics_path=prov_path, output_path=macros_path)

    generate_uf7_figure(
        report,
        fig_dir / "fig_uf7_thermodynamics_and_applications.png",
        fig_dir / "fig_uf7_thermodynamics_and_applications.pdf",
        report_path,
    )


def run_micro_probe(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    device = detect_compute_device(args.device)
    uf1 = load_json_required(args.results_dir / "uf1_mesh_convergence_report.json")
    surf_d = uf1["ultrafine_landscapes"]["Config_D_DualStator_PushPull"]
    pot_d = build_potential_from_grid(surf_d, surf_d["z_grid_um"], surf_d["theta_grid_deg"])

    n_steps_probe = max(20, int(args.max_steps) * 40)
    pt = simulate_loaded_thermodynamic_ensemble(
        "Config_D_DualStator_PushPull",
        pot_d,
        mode="pad_release_gated",
        temperature_K=300.0,
        tau_load_pN_um=0.05,
        n_traj=16,
        n_steps=n_steps_probe,
        seed=20261118,
    )
    epstein = compute_epstein_knudsen_rotor_drag_coeff("Config_D_DualStator_PushPull")
    probe_out = args.results_dir / "probe_uf7_thermodynamics_and_applications_report.json"
    payload = {
        "suite": "eng_uf7",
        "status": "micro_probe_completed",
        "time_truncated": True,
        "max_steps": int(args.max_steps),
        "device": device,
        "elapsed_seconds": time.perf_counter() - started,
        "sample_loaded_point": pt,
        "sample_epstein": epstein,
    }
    atomic_write_json(probe_out, payload)
    print(f"[UF7 MICRO-PROBE] Completed in {payload['elapsed_seconds']:.2f}s -> {probe_out}", flush=True)
    return 0


def run_full_campaign(args: argparse.Namespace) -> int:
    started_mono = time.monotonic()
    started_wall = time.perf_counter()
    device = detect_compute_device(args.device)

    uf1 = load_json_required(args.results_dir / "uf1_mesh_convergence_report.json")
    uf3 = load_json_required(args.results_dir / "uf3_active_switching_report.json")

    surf_d_au = uf1["ultrafine_landscapes"]["Config_D_DualStator_PushPull"]
    pot_d_au = build_potential_from_grid(surf_d_au, surf_d_au["z_grid_um"], surf_d_au["theta_grid_deg"])

    d3_b = uf3["designs"]["Config_B_Manhattan_Vernier"]
    pot_b_vo2_on = build_potential_from_grid(d3_b["surfaces"]["Au_VO2_ON"], d3_b["z_grid_um"], d3_b["theta_grid_deg"])
    pot_b_vo2_off = build_potential_from_grid(
        d3_b["surfaces"]["Au_VO2_OFF"], d3_b["z_grid_um"], d3_b["theta_grid_deg"]
    )

    d3_d = uf3["designs"]["Config_D_DualStator_PushPull"]
    pot_d_si_on = build_potential_from_grid(d3_d["surfaces"]["Au_Si_ON"], d3_d["z_grid_um"], d3_d["theta_grid_deg"])
    pot_d_si_off = build_potential_from_grid(d3_d["surfaces"]["Au_Si_OFF"], d3_d["z_grid_um"], d3_d["theta_grid_deg"])

    print("[UF7 1/4] Sweeping loaded motor curves & steady-state First-Law shaft efficiency...", flush=True)
    motor_curves: dict[str, dict[str, Any]] = {}
    # Config_D_Gated & Config_B_VO2 operate as autonomous limit-cycle motors (pre_equilibrate=True);
    # Config_D_Si operates as a pulsed 500-us optical stepper that self-latches once axial preload relaxes.
    curve_specs = (
        ("Config_D_Gated_300K", "Config_D_DualStator_PushPull", pot_d_au, None, "pad_release_gated", 300.0, True, 7100),
        ("Config_D_Gated_4K", "Config_D_DualStator_PushPull", pot_d_au, None, "pad_release_gated", 4.0, True, 7200),
        ("Config_B_VO2_300K", "Config_B_Manhattan_Vernier", pot_b_vo2_on, pot_b_vo2_off, "two_state_switching", 300.0, True, 7300),
        ("Config_D_Si_300K", "Config_D_DualStator_PushPull", pot_d_si_on, pot_d_si_off, "two_state_switching", 300.0, False, 7400),
        ("Config_D_Si_4K", "Config_D_DualStator_PushPull", pot_d_si_on, pot_d_si_off, "two_state_switching", 4.0, False, 7500),
    )
    for label, dname, p_on, p_off, mode, temp_k, pre_eq, s_base in curve_specs:
        check_walltime(started_mono, args.max_walltime_hours)
        motor_curves[label] = sweep_loaded_motor_curve(
            label,
            dname,
            p_on,
            pot_off=p_off,
            mode=mode,
            temperature_K=temp_k,
            pre_equilibrate=pre_eq,
            n_traj=args.n_traj,
            n_steps=args.n_steps,
            n_load_points=9,
            seed_base=s_base,
            started_mono=started_mono,
            max_walltime_hours=args.max_walltime_hours,
        )

    print("[UF7 2/4] Auditing finite-T stochastic thermodynamics & TUR bounds...", flush=True)
    tur_audit: dict[str, Any] = {}
    tau_opt_d = float(motor_curves["Config_D_Gated_300K"]["tau_opt_pN_um"])
    tau_opt_si = float(motor_curves["Config_D_Si_300K"]["tau_opt_pN_um"])
    for temp_k in (4.0, 77.0, 300.0):
        check_walltime(started_mono, args.max_walltime_hours)
        tur_audit[f"Config_D_Gated_{int(temp_k)}K_opt_load"] = simulate_loaded_thermodynamic_ensemble(
            "Config_D_DualStator_PushPull",
            pot_d_au,
            mode="pad_release_gated",
            temperature_K=temp_k,
            tau_load_pN_um=tau_opt_d,
            pre_equilibrate=True,
            n_traj=max(128, args.n_traj),
            n_steps=args.n_steps,
            seed=int(8100 + temp_k),
        )
        tur_audit[f"Config_D_Si_{int(temp_k)}K_opt_load"] = simulate_loaded_thermodynamic_ensemble(
            "Config_D_DualStator_PushPull",
            pot_d_si_on,
            pot_off=pot_d_si_off,
            mode="two_state_switching",
            temperature_K=temp_k,
            tau_load_pN_um=tau_opt_si,
            pre_equilibrate=False,
            n_traj=max(128, args.n_traj),
            n_steps=args.n_steps,
            seed=int(8400 + temp_k),
        )

    print("[UF7 3/4] Computing 3-tier physical wall-plug efficiency budget...", flush=True)
    wall_plug = compute_wall_plug_efficiency_budget(motor_curves)

    print("[UF7 4/4] Benchmarking cryogenic stepper/latch, Knudsen manometer, & metasurface array...", flush=True)
    cryo_stepper = evaluate_cryogenic_stepper_and_passive_latch(
        "Config_D_DualStator_PushPull",
        pot_d_si_on,
        pot_d_si_off,
        n_traj=args.n_traj,
    )
    knudsen = evaluate_knudsen_gauge_and_rheometer(
        "Config_D_DualStator_PushPull",
        pot_d_au,
        motor_curves["Config_D_Gated_300K"],
        n_traj=max(64, args.n_traj // 2),
        n_steps=max(12000, int(0.8 * args.n_steps)),
        started_mono=started_mono,
        max_walltime_hours=args.max_walltime_hours,
    )
    array_scaling = compute_metasurface_array_scaling(motor_curves, wall_plug, cryo_stepper)

    all_q_tur = [
        float(v["q_tur"])
        for v in tur_audit.values()
        if v.get("q_tur") is not None
    ] + [
        float(c["q_tur_at_max_power"])
        for c in motor_curves.values()
        if c.get("q_tur_at_max_power") is not None
    ]
    max_first_law = max(float(c["max_first_law_residual_aJ"]) for c in motor_curves.values())

    mc_d300 = motor_curves["Config_D_Gated_300K"]
    mc_bvo2 = motor_curves["Config_B_VO2_300K"]
    mc_dsi = motor_curves["Config_D_Si_300K"]
    q_tur_d300 = float(tur_audit["Config_D_Gated_300K_opt_load"]["q_tur"])

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    summary = {
        "cfg_d_gated_300K_stall_tau_pN_nm": mc_d300["tau_stall_pN_nm"],
        "cfg_d_gated_300K_stall_kBT300": mc_d300["tau_stall_kBT300_per_rad"],
        "cfg_d_gated_300K_max_power_fW": mc_d300["p_shaft_max_fW"],
        "cfg_d_gated_300K_max_power_zW": mc_d300["p_shaft_max_zW"],
        "cfg_d_gated_300K_emp_pct": mc_d300["eta_shaft_rev_at_max_power_pct"],
        "cfg_b_vo2_300K_stall_tau_pN_nm": mc_bvo2["tau_stall_pN_nm"],
        "cfg_b_vo2_300K_max_power_aW": mc_bvo2["p_shaft_max_aW"],
        "cfg_b_vo2_300K_max_power_zW": mc_bvo2["p_shaft_max_zW"],
        "cfg_b_vo2_300K_emp_pct": mc_bvo2["eta_shaft_rev_at_max_power_pct"],
        "cfg_d_si_300K_stall_tau_pN_nm": mc_dsi["tau_stall_pN_nm"],
        "cfg_d_si_300K_max_power_aW": mc_dsi["p_shaft_max_aW"],
        "cfg_d_si_300K_max_power_zW": mc_dsi["p_shaft_max_zW"],
        "cfg_d_si_300K_emp_pct": mc_dsi["eta_shaft_rev_at_max_power_pct"],
        "cfg_d_gated_300K_q_tur": q_tur_d300,
        "cfg_d_gated_300K_tur_eff_pct": 100.0 / q_tur_d300,
        "min_q_tur_observed": min(all_q_tur),
        "max_first_law_residual_aJ": max_first_law,
        "vo2_wall_plug_efficiency": wall_plug["modalities"]["VO2_Thermal_Mott_25nm"]["wall_plug_efficiency"],
        "si_1e19_wall_plug_efficiency": wall_plug["modalities"]["Silicon_PhotoDoped_BEM_wp2p15eV_20nm"][
            "wall_plug_efficiency_1e19_density"
        ],
        "graphene_resonant_wall_plug_pct": wall_plug["modalities"]["Graphene_2D_Capacitive_Gate_0p5V"][
            "wall_plug_efficiency_resonant_pct"
        ],
        "cryo_pinning_barrier_meV": cryo_stepper["pinning_barrier_meV"],
        "cryo_4K_jitter_deg": cryo_stepper["temperatures"]["4K"]["rms_pointing_jitter_deg"],
        "cryo_4K_90deg_step_us": cryo_stepper["temperatures"]["4K"]["optical_90deg_step_time_us"],
        "knudsen_p_half_Pa": knudsen["epstein_kinetic_model"]["half_speed_crossover_pressure_Pa"],
        "stall_vs_f1_atpase_ratio": knudsen["biomolecular_rheometry_comparison"]["ratio_vs_F1_ATPase_41pNnm"],
        "array_rotors_per_cm2": array_scaling["rotors_per_cm2"],
        "array_stall_torque_nNm_cm2": array_scaling["areal_stall_torque_nNm_per_cm2"],
        "array_gated_power_pW_cm2": array_scaling["areal_shaft_power_gated_pW_per_cm2"],
        "array_mech_bandwidth_kHz": array_scaling["mechanical_modulation_bandwidth_kHz"],
    }

    report = {
        "suite": "eng_uf7",
        "model": "BEM_StochasticThermodynamics_Applications_Suite7",
        "dataset": "fractal_casimir_engine_cycle",
        "status": "completed",
        "executed_at": now_iso,
        "time_truncated": False,
        "device": device,
        "elapsed_seconds": round(time.perf_counter() - started_wall, 3),
        "summary": summary,
        "loaded_motor_curves": motor_curves,
        "stochastic_thermodynamics_tur": tur_audit,
        "wall_plug_efficiency_budget": wall_plug,
        "practical_applications": {
            "cryogenic_optical_stepper_and_latch": cryo_stepper,
            "knudsen_vacuum_gauge_and_rheometer": knudsen,
            "wafer_metasurface_array_scaling": array_scaling,
        },
    }

    report_path = args.results_dir / "uf7_thermodynamics_and_applications_report.json"
    atomic_write_json(report_path, report)
    export_uf7_provenance_and_figure(
        report,
        report_path,
        results_dir=args.results_dir,
        figures_dir=args.figures_dir,
    )
    print(f"[UF7 COMPLETED] Saved {report_path} in {report['elapsed_seconds']:.2f}s", flush=True)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Run fast micro-probe when > 0; run full UF7 campaign when 0.",
    )
    parser.add_argument("--device", type=str, default="auto", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--n-traj", type=int, default=96, help="Ensemble trajectories per loaded point.")
    parser.add_argument("--n-steps", type=int, default=12000, help="BAOAB time steps per trajectory (dt=0.04 us).")
    parser.add_argument("--max-walltime-hours", type=float, default=0.0)
    parser.add_argument("--results-dir", type=Path, default=UF_RESULTS_DIR)
    parser.add_argument("--figures-dir", type=Path, default=ENGINE_FIGURES_DIR)
    parser.add_argument(
        "--from-report",
        type=Path,
        default=None,
        help="Regenerate provenance metrics, macros, and figure from an existing uf7 report JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.from_report is not None:
        rep = load_json_required(args.from_report)
        export_uf7_provenance_and_figure(
            rep,
            args.from_report,
            results_dir=args.results_dir,
            figures_dir=args.figures_dir,
        )
        return 0
    if args.max_steps < 0:
        raise ValueError("--max-steps must be >= 0.")
    if args.max_steps > 0:
        return run_micro_probe(args)
    try:
        return run_full_campaign(args)
    except TimeoutError as exc:
        print(f"[UF7 WALLTIME] {exc}", file=sys.stderr, flush=True)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
