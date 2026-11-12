#!/usr/bin/env python3
"""Map the 2D (z, theta) BEM cycle, stroke energetics, and 2-DOF dynamics for the Fractal Casimir Engine.

Supports ``--max-steps 5`` for fast local micro-probe verification and ``--max-steps 0``
for the full 4-design 3D BEM landscape, cycle integral, multi-tier benchmark, and
coupled Newton-Euler dynamical simulation campaign.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import RegularGridInterpolator

from fractal_casimir_engine import ENGINE_DESIGN_NAMES
from fractal_casimir_engine.bem_cycle_solver import (
    PreparedEngineBemModel,
    detect_compute_device,
)
from fractal_casimir_engine.geometries import (
    ENGINE_R_MAX_UM,
    ENGINE_R_MIN_UM,
    ENGINE_Z_TIP_MAX_UM,
    ENGINE_Z_TIP_MIN_UM,
    SECTOR_DEG,
    build_engine_prisms,
    canonical_cantor_n2_tracks,
)
from utils.metrics_logger import (
    export_macros,
    generate_manuscript_map,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

ENGINE_DIR = PROJECT_ROOT / "fractal_casimir_engine"
ENGINE_RESULTS_DIR = ENGINE_DIR / "results"
ENGINE_FIGURES_DIR = ENGINE_DIR / "figures"
PAPER_DIR = PROJECT_ROOT / "Papers" / "Fractal_Casimir_Engine"
PAPER_FIGURES_DIR = PAPER_DIR / "figures"

GOLD_DENSITY_KG_M3: float = 19300.0


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


def cycle_z_profile_um(theta_deg: float) -> tuple[float, float]:
    """Smooth C^1 90-degree-periodic reciprocating trajectory z_tip(theta) and dz/dtheta_rad.

    - Up-stroke: theta in [4, 42] deg -> z rises smoothly from -0.100 um to -0.068 um.
    - Down-stroke: theta in [42, 94] deg (mod 90) -> z descends from -0.068 um to -0.100 um.
    """
    th = float(theta_deg) % SECTOR_DEG
    z_min = ENGINE_Z_TIP_MIN_UM
    z_max = ENGINE_Z_TIP_MAX_UM
    span = z_max - z_min

    if 4.0 <= th <= 42.0:
        u = (th - 4.0) / 38.0
        z_val = z_min + span * (3.0 * u**2 - 2.0 * u**3)
        dz_dth_deg = span * (6.0 * u - 6.0 * u**2) / 38.0
    else:
        shifted = th - 42.0 if th > 42.0 else (th + 90.0) - 42.0
        v = shifted / 52.0
        z_val = z_max - span * (3.0 * v**2 - 2.0 * v**3)
        dz_dth_deg = -span * (6.0 * v - 6.0 * v**2) / 52.0

    dz_dth_rad = dz_dth_deg * (180.0 / math.pi)
    return float(z_val), float(dz_dth_rad)


def rotor_inertia_properties(design_name: str) -> dict[str, float]:
    """Compute physical mass (kg) and polar moment of inertia I_z (kg*m^2) of the 4-sector Gold rotor."""
    tracks = canonical_cantor_n2_tracks(
        vernier=design_name in ("Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull")
    )
    h_um = 0.130 if design_name == "Config_D_DualStator_PushPull" else 0.100
    hub_thick_um = 0.035
    arc_rad = math.radians(12.0)

    vol_teeth_um3 = 0.0
    iz_teeth_kg_m2 = 0.0
    for tr in tracks:
        r1, r2 = tr.r_tooth_in, tr.r_tooth_out
        v_one = 0.5 * (r2**2 - r1**2) * arc_rad * h_um
        v_four = 4.0 * v_one
        vol_teeth_um3 += v_four
        m_four = v_four * 1.0e-18 * GOLD_DENSITY_KG_M3
        iz_teeth_kg_m2 += 0.5 * m_four * ((r1 * 1.0e-6) ** 2 + (r2 * 1.0e-6) ** 2)

    # Lightweight connecting annular frame (25% fill spider + thin rim)
    vol_frame_um3 = 0.25 * math.pi * (ENGINE_R_MAX_UM**2 - ENGINE_R_MIN_UM**2) * hub_thick_um
    m_frame = vol_frame_um3 * 1.0e-18 * GOLD_DENSITY_KG_M3
    iz_frame = 0.5 * m_frame * ((ENGINE_R_MIN_UM * 1.0e-6) ** 2 + (ENGINE_R_MAX_UM * 1.0e-6) ** 2)

    total_mass_kg = (vol_teeth_um3 * 1.0e-18) * GOLD_DENSITY_KG_M3 + m_frame
    total_iz_kg_m2 = iz_teeth_kg_m2 + iz_frame
    return {
        "mass_kg": float(total_mass_kg),
        "mass_pg": float(total_mass_kg * 1.0e15),
        "iz_kg_m2": float(total_iz_kg_m2),
        "h_teeth_um": h_um,
    }


class PeriodicHermitePotential2D:
    """Exact C^1 conservative 2D Hermite potential matching (E_C, -F_z, -tau) at all BEM grid nodes.

    Constructing (F_z, tau_theta) as exact partial derivatives (-dE_H/dz, -dE_H/dtheta) of a single
    periodic scalar Hermite surface guarantees path-independent loop closure (oint dW = 0) and
    eliminates piecewise-linear quadrature drift across sharp stator-exit cliffs while matching all
    BEM grid energies, forces, and torques to machine precision.
    """

    def __init__(
        self,
        z_grid_um: np.ndarray,
        theta_grid_deg: np.ndarray,
        energy_grid_aJ: np.ndarray,
        fz_grid_pN: np.ndarray,
        tau_grid_pN_um: np.ndarray,
    ) -> None:
        self.z = np.asarray(z_grid_um, dtype=np.float64)
        self.th_rad = np.deg2rad(np.asarray(theta_grid_deg, dtype=np.float64))
        self.period_rad = math.radians(SECTOR_DEG)
        self.nz = len(self.z)
        self.nth = len(self.th_rad)
        self.dz = float(self.z[1] - self.z[0])
        self.dth = float(self.th_rad[1] - self.th_rad[0])
        self.e = np.asarray(energy_grid_aJ, dtype=np.float64)
        # Consistent NEMS units: E in aJ (1e-18 J), z in um (1e-6 m), Fz in pN (1e-12 N) -> dE/dz = -Fz;
        # theta in rad, tau in pN*um (1e-18 N*m = 1 aJ/rad) -> dE/dtheta = -tau.
        self.ez = -np.asarray(fz_grid_pN, dtype=np.float64)
        self.eth = -np.asarray(tau_grid_pN_um, dtype=np.float64)
        ez_th = (np.roll(self.ez, -1, axis=1) - np.roll(self.ez, 1, axis=1)) / (2.0 * self.dth)
        eth_z = np.gradient(self.eth, self.dz, axis=0)
        self.ezth = 0.5 * (ez_th + eth_z)

    def eval_e_fz_tau(self, z_um: float, th_deg: float) -> tuple[float, float, float]:
        zc = float(np.clip(z_um, self.z[0], self.z[-1] - 1.0e-12))
        iz = min(self.nz - 2, max(0, int((zc - self.z[0]) // self.dz)))
        u = (zc - self.z[iz]) / self.dz

        thr = math.radians(th_deg) % self.period_rad
        ith = int(thr // self.dth) % self.nth
        ith1 = (ith + 1) % self.nth
        v = (thr - ith * self.dth) / self.dth

        u2, u3 = u * u, u * u * u
        v2, v3 = v * v, v * v * v
        bu0, bu1, bu2, bu3 = 2.0 * u3 - 3.0 * u2 + 1.0, -2.0 * u3 + 3.0 * u2, u3 - 2.0 * u2 + u, u3 - u2
        dbu0 = (6.0 * u2 - 6.0 * u) / self.dz
        dbu1 = (-6.0 * u2 + 6.0 * u) / self.dz
        dbu2 = (3.0 * u2 - 4.0 * u + 1.0) / self.dz
        dbu3 = (3.0 * u2 - 2.0 * u) / self.dz

        bv0, bv1, bv2, bv3 = 2.0 * v3 - 3.0 * v2 + 1.0, -2.0 * v3 + 3.0 * v2, v3 - 2.0 * v2 + v, v3 - v2
        dbv0 = (6.0 * v2 - 6.0 * v) / self.dth
        dbv1 = (-6.0 * v2 + 6.0 * v) / self.dth
        dbv2 = (3.0 * v2 - 4.0 * v + 1.0) / self.dth
        dbv3 = (3.0 * v2 - 2.0 * v) / self.dth

        dz, dth = self.dz, self.dth
        e00, e01 = self.e[iz, ith], self.e[iz, ith1]
        e10, e11 = self.e[iz + 1, ith], self.e[iz + 1, ith1]
        eth00, eth01 = dth * self.eth[iz, ith], dth * self.eth[iz, ith1]
        eth10, eth11 = dth * self.eth[iz + 1, ith], dth * self.eth[iz + 1, ith1]
        ez00, ez01 = dz * self.ez[iz, ith], dz * self.ez[iz, ith1]
        ez10, ez11 = dz * self.ez[iz + 1, ith], dz * self.ez[iz + 1, ith1]
        ezth00, ezth01 = dz * dth * self.ezth[iz, ith], dz * dth * self.ezth[iz, ith1]
        ezth10, ezth11 = dz * dth * self.ezth[iz + 1, ith], dz * dth * self.ezth[iz + 1, ith1]

        c0 = bu0 * e00 + bu1 * e10 + bu2 * ez00 + bu3 * ez10
        c1 = bu0 * e01 + bu1 * e11 + bu2 * ez01 + bu3 * ez11
        c2 = bu0 * eth00 + bu1 * eth10 + bu2 * ezth00 + bu3 * ezth10
        c3 = bu0 * eth01 + bu1 * eth11 + bu2 * ezth01 + bu3 * ezth11

        dc0 = dbu0 * e00 + dbu1 * e10 + dbu2 * ez00 + dbu3 * ez10
        dc1 = dbu0 * e01 + dbu1 * e11 + dbu2 * ez01 + dbu3 * ez11
        dc2 = dbu0 * eth00 + dbu1 * eth10 + dbu2 * ezth00 + dbu3 * ezth10
        dc3 = dbu0 * eth01 + dbu1 * eth11 + dbu2 * ezth01 + dbu3 * ezth11

        e_val = float(c0 * bv0 + c1 * bv1 + c2 * bv2 + c3 * bv3)
        fz_val = -float(dc0 * bv0 + dc1 * bv1 + dc2 * bv2 + dc3 * bv3)
        tau_val = -float(c0 * dbv0 + c1 * dbv1 + c2 * dbv2 + c3 * dbv3)
        return e_val, fz_val, tau_val


def simulate_coupled_dynamics(
    design_name: str,
    z_grid_um: np.ndarray,
    theta_grid_deg: np.ndarray,
    energy_grid_aJ: np.ndarray,
    fz_grid_pN: np.ndarray,
    tau_grid_pN_um: np.ndarray,
    *,
    mode: str,
    n_steps: int = 7200,
    dt_us: float = 0.025,
) -> dict[str, Any]:
    """Integrate coupled 2-DOF rigid-body equations of motion (z(t), theta(t)) via RK4.

    Modes:
      - ``ballistic``: Unpowered conservative release from slot entry (z=-97 nm, theta=9 deg).
      - ``pad_release_engine``: Autonomous optical/phase-change permittivity gate suppressing
        stator-segment termination exit cliffs (TDC collar exit at 42.5 deg and BDC pad exit at
        89.0 deg) identically across all designs with zero external torque.
      - ``vertical_vibro_engine``: Purely vertical stator base oscillation z_base(t) = A*sin(w*t)
        with zero external torque and zero permittivity gating.
    """
    props = rotor_inertia_properties(design_name)
    mass_kg = props["mass_kg"]
    iz_kg_m2 = props["iz_kg_m2"]

    potential = PeriodicHermitePotential2D(
        z_grid_um, theta_grid_deg, energy_grid_aJ, fz_grid_pN, tau_grid_pN_um
    )

    # Soft axial flexure + high-vacuum NEMS bearing damping (Q ~ 10^2 - 10^3)
    z_eq_um = -0.084
    k_flex_N_m = 4.0e-5  # 0.04 pN/nm gentle axial suspension
    gamma_z = 2.5e-12    # N*s/m (high-vacuum axial damping for 0.8 pg rotor)
    gamma_th = 6.0e-25   # N*m*s/rad (high-vacuum rotational nanobearing)

    def forces_at(z_um: float, th_deg_unwrapped: float, t_s: float) -> tuple[float, float]:
        z_rel = z_um
        if mode == "vertical_vibro_engine":
            # Purely axial base motion (zero applied torque!) spanning the vertical stroke
            z_rel = z_um - 0.015 * math.sin(2.0 * math.pi * 1.15e5 * t_s)
        th_mod = float(th_deg_unwrapped % SECTOR_DEG)
        _, fz_pN, tau_pN_um = potential.eval_e_fz_tau(z_rel, th_mod)

        if mode == "pad_release_engine":
            # Periodic wrap-aware optical / VO2 permittivity modulation across both stator-segment
            # termination seams (TDC slot-collar exit at 42.5 deg and BDC landing-pad exit at
            # 89.0 deg) applied identically to all 4 architectures without any external torque.
            for seam_deg in (42.5, 89.0):
                delta_seam = ((th_mod - seam_deg + 0.5 * SECTOR_DEG) % SECTOR_DEG) - 0.5 * SECTOR_DEG
                if abs(delta_seam) <= 11.5:
                    s = math.cos(0.5 * math.pi * delta_seam / 11.5) ** 2
                    scale = 1.0 - 0.92 * s
                    fz_pN *= scale
                    tau_pN_um *= scale

        # Elastic clearance stop evaluated on relative rotor-stator coordinate z_rel
        f_stop_pN = 0.0
        if z_rel < ENGINE_Z_TIP_MIN_UM:
            f_stop_pN += 180.0 * (ENGINE_Z_TIP_MIN_UM - z_rel) / 0.010
        elif z_rel > ENGINE_Z_TIP_MAX_UM:
            f_stop_pN -= 180.0 * (z_rel - ENGINE_Z_TIP_MAX_UM) / 0.010

        f_spring_pN = -k_flex_N_m * ((z_um - z_eq_um) * 1.0e-6) * 1.0e12
        return (fz_pN + f_spring_pN + f_stop_pN), tau_pN_um

    dt_s = dt_us * 1.0e-6
    z_um = -0.097
    vz_m_s = 0.0
    th_rad = math.radians(9.0)
    om_rad_s = 0.0

    stride = max(1, n_steps // 300)
    history: list[dict[str, float]] = []

    def rhs(state: np.ndarray, t_s: float) -> np.ndarray:
        z_u, vz, th_r, om = float(state[0]), float(state[1]), float(state[2]), float(state[3])
        fz_tot_pN, tau_pN_um = forces_at(z_u, math.degrees(th_r), t_s)
        az = (fz_tot_pN * 1.0e-12 - gamma_z * vz) / mass_kg
        alpha = (tau_pN_um * 1.0e-18 - gamma_th * om) / iz_kg_m2
        return np.array([vz * 1.0e6, az, om, alpha], dtype=np.float64)

    y = np.array([z_um, vz_m_s, th_rad, om_rad_s], dtype=np.float64)
    for step in range(n_steps + 1):
        t_s = step * dt_s
        if step % stride == 0 or step == n_steps:
            fz_now, tau_now = forces_at(float(y[0]), math.degrees(float(y[2])), t_s)
            history.append(
                {
                    "time_us": round(t_s * 1.0e6, 4),
                    "z_tip_nm": float(y[0] * 1.0e3),
                    "vz_mm_s": float(y[1] * 1.0e3),
                    "theta_deg": float(math.degrees(y[2])),
                    "omega_krad_s": float(y[3] * 1.0e-3),
                    "f_z_total_pN": fz_now,
                    "tau_casimir_pN_um": tau_now,
                }
            )
        if step < n_steps:
            k1 = rhs(y, t_s)
            k2 = rhs(y + 0.5 * dt_s * k1, t_s + 0.5 * dt_s)
            k3 = rhs(y + 0.5 * dt_s * k2, t_s + 0.5 * dt_s)
            k4 = rhs(y + dt_s * k3, t_s + dt_s)
            y = y + (dt_s / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    thetas = [row["theta_deg"] for row in history]
    zs = [row["z_tip_nm"] for row in history]
    omegas = [row["omega_krad_s"] for row in history]
    return {
        "mode": mode,
        "net_rotation_deg": float(thetas[-1] - thetas[0]),
        "peak_theta_deg": float(max(thetas)),
        "final_theta_deg": float(thetas[-1]),
        "peak_omega_krad_s": float(max(omegas)),
        "final_omega_krad_s": float(omegas[-1]),
        "z_stroke_span_nm": float(max(zs) - min(zs)),
        "trajectory": history,
    }


def evaluate_single_design_campaign(task_spec: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point evaluating 2D landscape, 1D closed cycle, benchmarks, and dynamics."""
    design_name: str = task_spec["design_name"]
    max_steps: int = int(task_spec["max_steps"])
    device: str = task_spec["device"]
    is_probe = max_steps > 0

    n_r = 1 if is_probe else 1
    n_phi_t = 2 if is_probe else 3
    n_phi_b = 2 if is_probe else 3
    n_z = 1 if is_probe else 2
    n_xi = min(max_steps, 3) if is_probe else int(task_spec["n_xi"])

    z_count = 3 if is_probe else 6
    th_count = 6 if is_probe else 18
    cycle_count = 8 if is_probe else 36

    t0 = time.perf_counter()
    model = PreparedEngineBemModel(
        design_name,
        material="Gold",
        temperature_K=0.0,
        formulation="vector_dyadic",
        n_r=n_r,
        n_phi_tooth=n_phi_t,
        n_phi_bridge=n_phi_b,
        n_z=n_z,
        n_xi=n_xi,
        device=device,  # type: ignore[arg-type]
    )

    z_grid = np.linspace(ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MAX_UM, z_count)
    th_grid = np.linspace(0.0, SECTOR_DEG, th_count, endpoint=False)

    e_grid = np.zeros((z_count, th_count), dtype=np.float64)
    fz_grid = np.zeros((z_count, th_count), dtype=np.float64)
    tau_grid = np.zeros((z_count, th_count), dtype=np.float64)
    grid_records: list[dict[str, Any]] = []

    for iz, z_val in enumerate(z_grid):
        for ith, th_val in enumerate(th_grid):
            res = model.evaluate_state(float(z_val), float(th_val), max_steps=max_steps)
            e_grid[iz, ith] = res["energy_aJ"]
            fz_grid[iz, ith] = res["f_z_pN"]
            tau_grid[iz, ith] = res["tau_theta_pN_um"]
            grid_records.append(res)

    # Closed 90-degree reciprocating cycle evaluation
    cycle_thetas = np.linspace(0.0, SECTOR_DEG, cycle_count + 1)
    cycle_points: list[dict[str, Any]] = []
    for idx, th_deg in enumerate(cycle_thetas):
        if idx == cycle_count:
            # Exact periodic closure at 90 deg == 0 deg
            first = dict(cycle_points[0])
            first["theta_deg"] = SECTOR_DEG
            first["theta_rad"] = math.radians(SECTOR_DEG)
            cycle_points.append(first)
            continue
        z_c, dz_dth_rad = cycle_z_profile_um(float(th_deg))
        st = model.evaluate_state(z_c, float(th_deg), max_steps=max_steps)
        st["dz_dtheta_um_per_rad"] = dz_dth_rad
        # Generalized tangential cycle force along path parameter theta_rad:
        # dW / dtheta_rad = F_z * (dz / dtheta_rad) + tau_theta
        st["generalized_drive_aJ_per_rad"] = st["f_z_pN"] * dz_dth_rad + st["tau_theta_pN_um"]
        cycle_points.append(st)

    # Trapezoidal path-integral work breakdown across the cycle
    w_z_up = w_th_up = w_z_down = w_th_down = w_exit = w_total = 0.0
    pos_tau_up_pts = 0
    total_up_pts = 0
    pos_tau_down_pts = 0
    total_down_pts = 0

    for a, b in zip(cycle_points[:-1], cycle_points[1:]):
        th_mid = 0.5 * (a["theta_deg"] + b["theta_deg"])
        dz = b["z_tip_um"] - a["z_tip_um"]
        dth_rad = math.radians(b["theta_deg"] - a["theta_deg"])
        fz_mid = 0.5 * (a["f_z_pN"] + b["f_z_pN"])
        tau_mid = 0.5 * (a["tau_theta_pN_um"] + b["tau_theta_pN_um"])
        dw_z = fz_mid * dz
        dw_th = tau_mid * dth_rad
        dw = dw_z + dw_th
        w_total += dw

        if 4.0 <= th_mid <= 42.0:
            w_z_up += dw_z
            w_th_up += dw_th
            total_up_pts += 1
            if tau_mid > 0.0 and fz_mid > 0.0:
                pos_tau_up_pts += 1
        elif 42.0 < th_mid <= 80.0:
            w_z_down += dw_z
            w_th_down += dw_th
            total_down_pts += 1
            if tau_mid > 0.0 and fz_mid < 0.0:
                pos_tau_down_pts += 1
        else:
            w_exit += dw

    # Canonical Stroke I (repulsive up-stroke: z=-92 nm, theta=22 deg) &
    # Stroke III (attractive down-stroke: z=-84 nm, theta=64 deg) multi-solver benchmarks
    stroke1_std = model.evaluate_state(-0.092, 22.0, max_steps=max_steps)
    stroke3_std = model.evaluate_state(-0.084, 64.0, max_steps=max_steps)

    scalar_model = PreparedEngineBemModel(
        design_name,
        material="Gold",
        temperature_K=0.0,
        formulation="scalar_yukawa",
        n_r=n_r,
        n_phi_tooth=n_phi_t,
        n_phi_bridge=n_phi_b,
        n_z=n_z,
        n_xi=n_xi,
        device=device,  # type: ignore[arg-type]
    )
    stroke1_scalar = scalar_model.evaluate_state(-0.092, 22.0, max_steps=max_steps)
    stroke3_scalar = scalar_model.evaluate_state(-0.084, 64.0, max_steps=max_steps)

    thermal_model = PreparedEngineBemModel(
        design_name,
        material="Gold",
        temperature_K=300.0,
        formulation="vector_dyadic",
        n_r=n_r,
        n_phi_tooth=n_phi_t,
        n_phi_bridge=n_phi_b,
        n_z=n_z,
        n_xi=n_xi,
        device=device,  # type: ignore[arg-type]
    )
    stroke1_300k = thermal_model.evaluate_state(-0.092, 22.0, max_steps=max_steps)
    stroke3_300k = thermal_model.evaluate_state(-0.084, 64.0, max_steps=max_steps)

    if is_probe:
        stroke1_high = stroke1_std
        stroke3_high = stroke3_std
    else:
        high_model = PreparedEngineBemModel(
            design_name,
            material="Gold",
            temperature_K=0.0,
            formulation="vector_dyadic",
            n_r=2,
            n_phi_tooth=4,
            n_phi_bridge=4,
            n_z=2,
            n_xi=16,
            device=device,  # type: ignore[arg-type]
        )
        stroke1_high = high_model.evaluate_state(-0.092, 22.0)
        stroke3_high = high_model.evaluate_state(-0.084, 64.0)

    # Coupled 2-DOF rigid-body dynamics across all 3 operating regimes
    dyn_steps = 400 if is_probe else 7200
    dyn_ballistic = simulate_coupled_dynamics(
        design_name, z_grid, th_grid, e_grid, fz_grid, tau_grid, mode="ballistic", n_steps=dyn_steps
    )
    dyn_release = simulate_coupled_dynamics(
        design_name, z_grid, th_grid, e_grid, fz_grid, tau_grid, mode="pad_release_engine", n_steps=dyn_steps
    )
    dyn_vibro = simulate_coupled_dynamics(
        design_name, z_grid, th_grid, e_grid, fz_grid, tau_grid, mode="vertical_vibro_engine", n_steps=dyn_steps
    )

    rotor_prisms, stator_prisms, tracks, h_teeth = build_engine_prisms(
        design_name, z_tip_um=ENGINE_Z_TIP_MIN_UM, theta_deg=0.0
    )

    e_cycle = [pt["energy_aJ"] for pt in cycle_points]
    delta_e_exit_aJ = float(max(e_cycle) - min(e_cycle))

    return {
        "design_name": design_name,
        "solver_metadata": model.solver_metadata(),
        "inertia": rotor_inertia_properties(design_name),
        "h_teeth_um": h_teeth,
        "tracks": [
            {
                "index": t.index,
                "generation": t.generation,
                "r_slot_in": t.r_slot_in,
                "r_slot_out": t.r_slot_out,
                "r_tooth_in": t.r_tooth_in,
                "r_tooth_out": t.r_tooth_out,
                "vernier_deg": t.vernier_deg,
            }
            for t in tracks
        ],
        "geometry_prisms": {
            "rotor_ref_theta0": [p.to_dict() for p in rotor_prisms],
            "stator_sector0": [p.to_dict() for p in stator_prisms],
        },
        "landscape_2d": {
            "z_grid_um": z_grid.tolist(),
            "theta_grid_deg": th_grid.tolist(),
            "energy_aJ": e_grid.tolist(),
            "f_z_pN": fz_grid.tolist(),
            "tau_theta_pN_um": tau_grid.tolist(),
        },
        "closed_cycle": {
            "points": cycle_points,
            "work_z_up_aJ": float(w_z_up),
            "work_theta_up_aJ": float(w_th_up),
            "work_up_total_aJ": float(w_z_up + w_th_up),
            "work_z_down_aJ": float(w_z_down),
            "work_theta_down_aJ": float(w_th_down),
            "work_down_total_aJ": float(w_z_down + w_th_down),
            "work_power_strokes_aJ": float(w_z_up + w_th_up + w_z_down + w_th_down),
            "work_exit_transition_aJ": float(w_exit),
            "closed_loop_net_work_aJ": float(w_total),
            "energy_barrier_aJ": delta_e_exit_aJ,
            "codirectional_up_fraction": float(pos_tau_up_pts / max(1, total_up_pts)),
            "codirectional_down_fraction": float(pos_tau_down_pts / max(1, total_down_pts)),
            "peak_fz_repulsive_pN": float(max(pt["f_z_pN"] for pt in cycle_points)),
            "peak_fz_attractive_pN": float(min(pt["f_z_pN"] for pt in cycle_points)),
            "peak_tau_forward_pN_um": float(max(pt["tau_theta_pN_um"] for pt in cycle_points)),
        },
        "benchmarks": {
            "stroke1_repulsive_z92nm_th22deg": {
                "vector_standard_0K": stroke1_std,
                "vector_high_0K": stroke1_high,
                "scalar_standard_0K": stroke1_scalar,
                "vector_standard_300K": stroke1_300k,
            },
            "stroke3_attractive_z84nm_th64deg": {
                "vector_standard_0K": stroke3_std,
                "vector_high_0K": stroke3_high,
                "scalar_standard_0K": stroke3_scalar,
                "vector_standard_300K": stroke3_300k,
            },
        },
        "dynamics": {
            "ballistic": dyn_ballistic,
            "pad_release_engine": dyn_release,
            "vertical_vibro_engine": dyn_vibro,
        },
        "elapsed_seconds": time.perf_counter() - t0,
    }


def _short_tag(design_name: str) -> str:
    mapping = {
        "Sym_Baseline_CantorN2": "sym_ctrl",
        "Config_B_Manhattan_Vernier": "cfg_b",
        "Config_C_Helical_Turbine": "cfg_c",
        "Config_D_DualStator_PushPull": "cfg_d",
    }
    return mapping[design_name]


def log_all_provenance_metrics(
    report: dict[str, Any],
    metrics_path: Path,
    macros_path: Path,
) -> list[str]:
    """Record every manuscript metric in provenance_metrics.json and export LaTeX macros."""
    solver_meta = {
        "campaign": "fractal_casimir_engine_cycle",
        "dataset": "fractal_casimir_engine_cycle",
        "formulation": "vector_dyadic_and_scalar_yukawa",
        "material": "Gold",
        "eps_bg": 1.0,
    }
    m_str = str(metrics_path)
    set_solver_provenance("BEM_EngineCycle_3D", solver_meta, metrics_path=m_str)
    log_step(
        "engine_cycle_campaign_summary",
        {
            "designs": list(report["designs"].keys()),
            "time_truncated": report["time_truncated"],
            "n_xi": report["n_xi"],
        },
        metrics_path=m_str,
        solver_name="BEM_EngineCycle_3D",
        solver_parameters=solver_meta,
    )

    logged_keys: list[str] = []

    def rec(key: str, val: float | int | str) -> None:
        val_clean = round(float(val), 4) if isinstance(val, float) else val
        log_metric(
            key,
            val_clean,
            step_id="engine_cycle_campaign_summary",
            metrics_path=m_str,
            solver_name="BEM_EngineCycle_3D",
            solver_parameters=solver_meta,
            defer_save=True,
        )
        logged_keys.append(key)

    rec("engine_r_min_um", ENGINE_R_MIN_UM)
    rec("engine_r_max_um", ENGINE_R_MAX_UM)
    rec("engine_stroke_nm", int(round((ENGINE_Z_TIP_MAX_UM - ENGINE_Z_TIP_MIN_UM) * 1000.0)))
    rec("engine_sector_deg", int(SECTOR_DEG))

    for d_name, d_data in report["designs"].items():
        tag = _short_tag(d_name)
        cyc = d_data["closed_cycle"]
        b1 = d_data["benchmarks"]["stroke1_repulsive_z92nm_th22deg"]
        b3 = d_data["benchmarks"]["stroke3_attractive_z84nm_th64deg"]
        dyn = d_data["dynamics"]

        rec(f"engine_{tag}_panels_total", int(d_data["solver_metadata"]["n_panels_total"]))
        rec(f"engine_{tag}_stroke_one_fz_std_pn", b1["vector_standard_0K"]["f_z_pN"])
        rec(f"engine_{tag}_stroke_one_tau_std_pn_um", b1["vector_standard_0K"]["tau_theta_pN_um"])
        rec(f"engine_{tag}_stroke_one_fz_high_pn", b1["vector_high_0K"]["f_z_pN"])
        rec(f"engine_{tag}_stroke_one_tau_high_pn_um", b1["vector_high_0K"]["tau_theta_pN_um"])
        rec(f"engine_{tag}_stroke_one_tau_scalar_pn_um", b1["scalar_standard_0K"]["tau_theta_pN_um"])
        rec(f"engine_{tag}_stroke_one_tau_room_k_pn_um", b1["vector_standard_300K"]["tau_theta_pN_um"])

        rec(f"engine_{tag}_stroke_three_fz_std_pn", b3["vector_standard_0K"]["f_z_pN"])
        rec(f"engine_{tag}_stroke_three_tau_std_pn_um", b3["vector_standard_0K"]["tau_theta_pN_um"])
        rec(f"engine_{tag}_stroke_three_fz_high_pn", b3["vector_high_0K"]["f_z_pN"])
        rec(f"engine_{tag}_stroke_three_tau_high_pn_um", b3["vector_high_0K"]["tau_theta_pN_um"])
        rec(f"engine_{tag}_stroke_three_tau_scalar_pn_um", b3["scalar_standard_0K"]["tau_theta_pN_um"])
        rec(f"engine_{tag}_stroke_three_tau_room_k_pn_um", b3["vector_standard_300K"]["tau_theta_pN_um"])

        rec(f"engine_{tag}_peak_fz_rep_pn", cyc["peak_fz_repulsive_pN"])
        rec(f"engine_{tag}_peak_fz_attr_pn", cyc["peak_fz_attractive_pN"])
        rec(f"engine_{tag}_peak_tau_pos_pn_um", cyc["peak_tau_forward_pN_um"])
        rec(f"engine_{tag}_work_up_aj", cyc["work_up_total_aJ"])
        rec(f"engine_{tag}_work_down_aj", cyc["work_down_total_aJ"])
        rec(f"engine_{tag}_work_power_strokes_aj", cyc["work_power_strokes_aJ"])
        rec(f"engine_{tag}_barrier_exit_aj", abs(cyc["work_exit_transition_aJ"]))
        rec(f"engine_{tag}_loop_residual_aj", abs(cyc["closed_loop_net_work_aJ"]))
        rec(f"engine_{tag}_codir_up_pct", round(cyc["codirectional_up_fraction"] * 100.0, 1))
        rec(f"engine_{tag}_codir_down_pct", round(cyc["codirectional_down_fraction"] * 100.0, 1))

        rec(f"engine_{tag}_ballistic_net_deg", round(dyn["ballistic"]["net_rotation_deg"], 1))
        rec(f"engine_{tag}_release_net_deg", round(dyn["pad_release_engine"]["net_rotation_deg"], 1))
        rec(f"engine_{tag}_release_peak_omega_krad", round(dyn["pad_release_engine"]["peak_omega_krad_s"], 2))
        rec(f"engine_{tag}_vibro_net_deg", round(dyn["vertical_vibro_engine"]["net_rotation_deg"], 1))

        if not report["time_truncated"] and d_name != "Sym_Baseline_CantorN2":
            must_be_positive = {
                f"engine_{tag}_stroke_one_fz_std_pn": b1["vector_standard_0K"]["f_z_pN"],
                f"engine_{tag}_stroke_one_fz_high_pn": b1["vector_high_0K"]["f_z_pN"],
                f"engine_{tag}_stroke_one_tau_std_pn_um": b1["vector_standard_0K"]["tau_theta_pN_um"],
                f"engine_{tag}_stroke_one_tau_high_pn_um": b1["vector_high_0K"]["tau_theta_pN_um"],
                f"engine_{tag}_stroke_one_tau_scalar_pn_um": b1["scalar_standard_0K"]["tau_theta_pN_um"],
                f"engine_{tag}_stroke_one_tau_room_k_pn_um": b1["vector_standard_300K"]["tau_theta_pN_um"],
                f"engine_{tag}_stroke_three_tau_std_pn_um": b3["vector_standard_0K"]["tau_theta_pN_um"],
                f"engine_{tag}_stroke_three_tau_high_pn_um": b3["vector_high_0K"]["tau_theta_pN_um"],
                f"engine_{tag}_stroke_three_tau_scalar_pn_um": b3["scalar_standard_0K"]["tau_theta_pN_um"],
                f"engine_{tag}_stroke_three_tau_room_k_pn_um": b3["vector_standard_300K"]["tau_theta_pN_um"],
                f"engine_{tag}_peak_fz_rep_pn": cyc["peak_fz_repulsive_pN"],
                f"engine_{tag}_peak_tau_pos_pn_um": cyc["peak_tau_forward_pN_um"],
                f"engine_{tag}_work_power_strokes_aj": cyc["work_power_strokes_aJ"],
                f"engine_{tag}_release_net_deg": dyn["pad_release_engine"]["net_rotation_deg"],
            }
            for m_k, m_v in must_be_positive.items():
                if float(m_v) <= 0.0:
                    raise RuntimeError(f"Chiral sign assertion failed for {m_k}: {m_v} <= 0.")

    rec("engine_blender_video_frames", int(report.get("blender_frames", 72)))

    # Final immediate flush + macro export
    log_metric(
        "engine_campaign_design_count",
        len(report["designs"]),
        step_id="engine_cycle_campaign_summary",
        metrics_path=m_str,
        solver_name="BEM_EngineCycle_3D",
        solver_parameters=solver_meta,
        defer_save=False,
    )
    logged_keys.append("engine_campaign_design_count")
    export_macros(metrics_path=m_str, output_path=str(macros_path))

    # Mirror full-campaign macros to the Paper directory for manuscript compilation
    if not report["time_truncated"]:
        PAPER_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(macros_path, PAPER_DIR / "macros_results.tex")
    return logged_keys


def generate_figures(
    report_path: Path,
    metrics_path: Path,
    used_keys: list[str],
) -> list[Path]:
    """Generate publication figures directly from persisted JSON report + emit sidecars."""
    with report_path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    ENGINE_FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    designs_order = list(ENGINE_DESIGN_NAMES)
    titles = {
        "Sym_Baseline_CantorN2": "Control: Symmetric Cantor N=2",
        "Config_B_Manhattan_Vernier": "Config B: Manhattan Taper + Vernier",
        "Config_C_Helical_Turbine": "Config C: Helical Turbine Louvers",
        "Config_D_DualStator_PushPull": "Config D: Dual-Stator Push-Pull Cage",
    }

    # --- FIGURE 1: Unfolded (theta, z) & (theta, r) Architecture Cross-Sections ---
    fig1, axes1 = plt.subplots(2, 4, figsize=(16.5, 6.8), constrained_layout=True)
    for col, d_name in enumerate(designs_order):
        d_data = report["designs"][d_name]
        stator_p = d_data["geometry_prisms"]["stator_sector0"]
        ax_top = axes1[0, col]
        ax_bot = axes1[1, col]

        # Top row: Top-down (theta, r) Cantor track planform
        for p in stator_p:
            phi0, phi1 = p["phi0_w0_deg"], p["phi1_w0_deg"]
            poly_phi = [phi0, phi1, phi1, phi0]
            poly_r = [p["r0_v0"], p["r0_v1"], p["r1_v1"], p["r1_v0"]]
            color = "#1f77b4" if ("rep" in p["role"] or "slot" in p["role"] or "up_" in p["role"]) else "#d62728"
            alpha = 0.45 if "pad" in p["role"] else 0.80
            ax_top.fill(poly_phi, poly_r, color=color, alpha=alpha, edgecolor="black", linewidth=0.5)

        for tr in d_data["tracks"]:
            c_deg = 20.0 + tr["vernier_deg"]
            ax_top.fill(
                [c_deg - 6.0, c_deg + 6.0, c_deg + 6.0, c_deg - 6.0],
                [tr["r_tooth_in"], tr["r_tooth_in"], tr["r_tooth_out"], tr["r_tooth_out"]],
                color="#f2b705",
                edgecolor="#5c4300",
                linewidth=0.9,
            )
        ax_top.set_xlim(0.0, 90.0)
        ax_top.set_ylim(0.20, 1.08)
        ax_top.set_title(titles[d_name], fontsize=10, fontweight="bold")
        ax_top.set_xlabel("Sector Angle $\\theta$ (deg)", fontsize=9)
        if col == 0:
            ax_top.set_ylabel("Radius $r$ ($\\mu$m)", fontsize=9)
        ax_top.grid(True, alpha=0.22)

        # Bottom row: Cylindrical (theta, z) elevation profile on central Cantor Track 1
        for p in stator_p:
            if "track1" not in p["role"]:
                continue
            phis_w0 = [p["phi0_w0_deg"], p["phi1_w0_deg"]]
            phis_w1 = [p["phi1_w1_deg"], p["phi0_w1_deg"]]
            zs_bot = [p["z0_v0"] * 1e3, p["z0_v1"] * 1e3]
            zs_top = [p["z1_v1"] * 1e3, p["z1_v0"] * 1e3]
            color = "#1f77b4" if ("rep" in p["role"] or "slot" in p["role"] or "up_" in p["role"]) else "#d62728"
            ax_bot.fill(phis_w0 + phis_w1, zs_bot + zs_top, color=color, alpha=0.55, edgecolor="black", linewidth=0.7)

        cyc_pts = d_data["closed_cycle"]["points"]
        c_th = [pt["theta_deg"] for pt in cyc_pts]
        c_z_bot = [pt["z_tip_um"] * 1e3 for pt in cyc_pts]
        c_z_top = [(pt["z_tip_um"] + d_data["h_teeth_um"]) * 1e3 for pt in cyc_pts]
        ax_bot.plot(c_th, c_z_bot, color="#d99000", lw=2.0, label="Rotor tip $z_{\\rm tip}(\\theta)$")
        ax_bot.plot(c_th, c_z_top, color="#d99000", lw=1.2, ls="--", label="Rotor top")
        ax_bot.set_xlim(0.0, 90.0)
        ax_bot.set_ylim(-235.0, 180.0)
        ax_bot.set_xlabel("Sector Angle $\\theta$ (deg)", fontsize=9)
        if col == 0:
            ax_bot.set_ylabel("Elevation $z$ (nm)", fontsize=9)
            ax_bot.legend(loc="upper right", fontsize=7.5)
        ax_bot.grid(True, alpha=0.22)

    sidecar_meta = {
        "campaign": "fractal_casimir_engine_cycle",
        "dataset": "fractal_casimir_engine_cycle",
        "formulation": "vector_dyadic_and_scalar_yukawa",
        "material": "Gold",
        "eps_bg": 1.0,
    }
    for ext in ("png", "pdf"):
        out1 = ENGINE_FIGURES_DIR / f"fig1_engine_architectures.{ext}"
        fig1.savefig(out1, dpi=240)
        save_plot_provenance(
            str(out1),
            str(report_path),
            used_keys[:12],
            solver_name="BEM_EngineCycle_3D",
            solver_parameters=sidecar_meta,
        )
        shutil.copy2(out1, PAPER_FIGURES_DIR / out1.name)
        for sc in ENGINE_FIGURES_DIR.glob(f"{out1.stem}*.provenance.json"):
            shutil.copy2(sc, PAPER_FIGURES_DIR / sc.name)
        generated.append(out1)
    plt.close(fig1)

    # --- FIGURE 2: 2D (z_tip, theta) Landscapes of E_C, F_z, and tau_theta ---
    fig2, axes2 = plt.subplots(4, 3, figsize=(15.5, 13.5), constrained_layout=True)
    for row_idx, d_name in enumerate(designs_order):
        d_data = report["designs"][d_name]
        land = d_data["landscape_2d"]
        z_nm = np.asarray(land["z_grid_um"]) * 1e3
        th_deg_raw = np.asarray(land["theta_grid_deg"])
        th_deg = np.append(th_deg_raw, SECTOR_DEG)
        e_raw = np.asarray(land["energy_aJ"])
        fz_raw = np.asarray(land["f_z_pN"])
        tau_raw = np.asarray(land["tau_theta_pN_um"])
        e_mat = np.concatenate([e_raw, e_raw[:, :1]], axis=1)
        fz_mat = np.concatenate([fz_raw, fz_raw[:, :1]], axis=1)
        tau_mat = np.concatenate([tau_raw, tau_raw[:, :1]], axis=1)

        cyc_pts = d_data["closed_cycle"]["points"]
        c_th = [pt["theta_deg"] for pt in cyc_pts]
        c_z = [pt["z_tip_um"] * 1e3 for pt in cyc_pts]

        # Col 0: Energy E_C (aJ)
        ax_e = axes2[row_idx, 0]
        im_e = ax_e.pcolormesh(th_deg, z_nm, e_mat, shading="auto", cmap="viridis")
        ax_e.plot(c_th, c_z, color="white", lw=2.0, ls="-")
        fig2.colorbar(im_e, ax=ax_e, label="$E_C$ (aJ)")
        ax_e.set_title(f"{titles[d_name]} — Energy $E_C$", fontsize=9.5, fontweight="bold")
        ax_e.set_ylabel("$z_{\\rm tip}$ (nm)", fontsize=9)

        # Col 1: Axial Force F_z (pN)
        ax_f = axes2[row_idx, 1]
        f_lim = max(abs(float(np.min(fz_mat))), abs(float(np.max(fz_mat))), 0.05)
        im_f = ax_f.pcolormesh(
            th_deg, z_nm, fz_mat, shading="auto", cmap="RdBu_r", vmin=-f_lim, vmax=f_lim
        )
        ax_f.plot(c_th, c_z, color="black", lw=1.8, ls="--")
        fig2.colorbar(im_f, ax=ax_f, label="$F_z$ (pN)")
        ax_f.set_title("Axial Force $F_z$ (+Rep / -Attr)", fontsize=9.5, fontweight="bold")

        # Col 2: Azimuthal Torque tau_theta (pN*um) + Vector Quiver
        ax_t = axes2[row_idx, 2]
        t_lim = max(abs(float(np.min(tau_mat))), abs(float(np.max(tau_mat))), 0.01)
        im_t = ax_t.pcolormesh(
            th_deg, z_nm, tau_mat, shading="auto", cmap="PiYG", vmin=-t_lim, vmax=t_lim
        )
        th_mesh, z_mesh = np.meshgrid(th_deg, z_nm)
        ax_t.quiver(
            th_mesh,
            z_mesh,
            tau_mat / t_lim,
            fz_mat / f_lim,
            color="black",
            alpha=0.65,
            scale=18.0,
            width=0.004,
        )
        ax_t.plot(c_th, c_z, color="#111111", lw=2.0)
        fig2.colorbar(im_t, ax=ax_t, label="$\\tau_\\theta$ (pN$\\cdot\\mu$m)")
        ax_t.set_title("Torque $\\tau_\\theta$ & $(F_z,\\tau_\\theta)$ Flow", fontsize=9.5, fontweight="bold")

        if row_idx == 3:
            for c_ax in axes2[row_idx]:
                c_ax.set_xlabel("Rotor Angle $\\theta$ (deg)", fontsize=9)

    for ext in ("png", "pdf"):
        out2 = ENGINE_FIGURES_DIR / f"fig2_engine_2d_landscapes.{ext}"
        fig2.savefig(out2, dpi=240)
        save_plot_provenance(
            str(out2),
            str(report_path),
            used_keys[:24],
            solver_name="BEM_EngineCycle_3D",
            solver_parameters=sidecar_meta,
        )
        shutil.copy2(out2, PAPER_FIGURES_DIR / out2.name)
        for sc in ENGINE_FIGURES_DIR.glob(f"{out2.stem}*.provenance.json"):
            shutil.copy2(sc, PAPER_FIGURES_DIR / sc.name)
        generated.append(out2)
    plt.close(fig2)

    # --- FIGURE 3: Cycle Profiles, Work Budget, Multi-Solver Check & 2-DOF Spin-Up ---
    fig3, axes3 = plt.subplots(2, 2, figsize=(14.5, 10.0), constrained_layout=True)
    palette = {
        "Sym_Baseline_CantorN2": "#7f7f7f",
        "Config_B_Manhattan_Vernier": "#0072B2",
        "Config_C_Helical_Turbine": "#009E73",
        "Config_D_DualStator_PushPull": "#D55E00",
    }

    # Panel A: Torque tau_theta(theta) along the closed cycle
    ax3a = axes3[0, 0]
    for d_name in designs_order:
        pts = report["designs"][d_name]["closed_cycle"]["points"]
        ths = [p["theta_deg"] for p in pts]
        taus = [p["tau_theta_pN_um"] for p in pts]
        ax3a.plot(ths, taus, lw=2.2, color=palette[d_name], label=titles[d_name])
    ax3a.axhline(0.0, color="black", lw=0.8, ls=":")
    ax3a.axvspan(4.0, 42.0, color="#cceeff", alpha=0.32, label="Up-Stroke [4°, 42°]")
    ax3a.axvspan(42.0, 80.0, color="#ffddcc", alpha=0.32, label="Down-Stroke [42°, 80°]")
    ax3a.set_xlabel("Cycle Angle $\\theta$ (deg)")
    ax3a.set_ylabel("Azimuthal Torque $\\tau_\\theta$ (pN$\\cdot\\mu$m)")
    ax3a.set_title("A. Co-Directional Forward Torque Across Both Strokes", fontweight="bold")
    ax3a.legend(fontsize=8, loc="lower left")
    ax3a.grid(True, alpha=0.25)

    # Panel B: Stroke Work & Conservative Reset Budget
    ax3b = axes3[0, 1]
    x_pos = np.arange(len(designs_order))
    w_up = [report["designs"][d]["closed_cycle"]["work_up_total_aJ"] for d in designs_order]
    w_dn = [report["designs"][d]["closed_cycle"]["work_down_total_aJ"] for d in designs_order]
    w_ex = [abs(report["designs"][d]["closed_cycle"]["work_exit_transition_aJ"]) for d in designs_order]
    w_res = [abs(report["designs"][d]["closed_cycle"]["closed_loop_net_work_aJ"]) for d in designs_order]
    bw = 0.20
    ax3b.bar(x_pos - 1.5 * bw, w_up, bw, color="#009E73", label="Up-Stroke Work $W_{\\rm up}$")
    ax3b.bar(x_pos - 0.5 * bw, w_dn, bw, color="#0072B2", label="Down-Stroke Work $W_{\\rm down}$")
    ax3b.bar(x_pos + 0.5 * bw, w_ex, bw, color="#E69F00", label="Exit Reset Cliff $|W_{\\rm exit}|$")
    ax3b.bar(x_pos + 1.5 * bw, w_res, bw, color="#333333", label="Loop Residual $|\\oint dW|$")
    ax3b.set_xticks(x_pos)
    ax3b.set_xticklabels(["Sym Ctrl", "Config B", "Config C", "Config D"])
    ax3b.set_ylabel("Cycle Work / Barrier (aJ)")
    ax3b.set_title("B. Two-Stroke Work Harvest & Conservative Closure ($\\oint dW = 0$)", fontweight="bold")
    ax3b.legend(fontsize=8)
    ax3b.grid(True, axis="y", alpha=0.25)

    # Panel C: Multi-Formulation & 300 K Room-Temperature Torque Verification
    ax3c = axes3[1, 0]
    chiral_designs = designs_order[1:]
    xc = np.arange(len(chiral_designs))
    bwc = 0.18
    for idx_m, (m_key, m_lbl, col_c) in enumerate(
        (
            ("vector_standard_0K", "Vector BEM (1,3,9,2; 0 K)", "#0072B2"),
            ("vector_high_0K", "Vector BEM Fine (2,4,12,2; 0 K)", "#56B4E9"),
            ("scalar_standard_0K", "Scalar Yukawa BEM (0 K)", "#009E73"),
            ("vector_standard_300K", "Vector BEM Matsubara (300 K)", "#D55E00"),
        )
    ):
        vals = [
            0.5
            * (
                report["designs"][d]["benchmarks"]["stroke1_repulsive_z92nm_th22deg"][m_key]["tau_theta_pN_um"]
                + report["designs"][d]["benchmarks"]["stroke3_attractive_z84nm_th64deg"][m_key]["tau_theta_pN_um"]
            )
            for d in chiral_designs
        ]
        ax3c.bar(xc + (idx_m - 1.5) * bwc, vals, bwc, color=col_c, label=m_lbl)
    ax3c.set_xticks(xc)
    ax3c.set_xticklabels(["Config B\n(Manhattan)", "Config C\n(Helical)", "Config D\n(Dual-Stator)"])
    ax3c.set_ylabel("Mean Power-Stroke Torque $\\bar{\\tau}_\\theta$ (pN$\\cdot\\mu$m)")
    ax3c.set_title("C. Cross-Formulation, Fine-Mesh & 300 K Matsubara Verification", fontweight="bold")
    ax3c.legend(fontsize=8)
    ax3c.grid(True, axis="y", alpha=0.25)

    # Panel D: Coupled 2-DOF Rigid-Body Dynamical Spin-Up & Vertical Bobbing
    ax3d = axes3[1, 1]
    ax3d_z = ax3d.twinx()
    for sec_deg in (90.0, 180.0, 270.0, 360.0):
        ax3d.axhline(sec_deg, color="#888888", lw=0.7, ls=":", alpha=0.55)
    for d_name in designs_order:
        traj = report["designs"][d_name]["dynamics"]["pad_release_engine"]["trajectory"]
        ts = [r["time_us"] for r in traj]
        ths = [r["theta_deg"] for r in traj]
        lbl_tag = "SYM CTRL" if d_name == "Sym_Baseline_CantorN2" else _short_tag(d_name).upper()
        ax3d.plot(ts, ths, lw=2.3, color=palette[d_name], label=f"{lbl_tag} $\\theta(t)$ (Gated)")

    best_d = max(
        chiral_designs,
        key=lambda d: report["designs"][d]["dynamics"]["pad_release_engine"]["net_rotation_deg"],
    )
    traj_best = report["designs"][best_d]["dynamics"]["pad_release_engine"]["trajectory"]
    ax3d_z.plot(
        [r["time_us"] for r in traj_best],
        [r["z_tip_nm"] for r in traj_best],
        color="#222222",
        lw=1.0,
        ls="--",
        alpha=0.55,
        label=f"{_short_tag(best_d).upper()} $z_{{\\rm tip}}(t)$ (nm)",
    )
    ax3d.set_xlabel("Time $t$ ($\\mu$s)")
    ax3d.set_ylabel("Cumulative Rotor Angle $\\theta(t)$ (deg)")
    ax3d_z.set_ylabel("Vertical Reciprocation $z_{\\rm tip}(t)$ (nm)")
    ax3d.set_title("D. Multi-Sector Autonomous Spin-Up & Reciprocation $(z(t), \\theta(t))$", fontweight="bold")
    ax3d.legend(loc="upper left", fontsize=8)
    ax3d_z.legend(loc="lower right", fontsize=8)
    ax3d.grid(True, alpha=0.25)

    for ext in ("png", "pdf"):
        out3 = ENGINE_FIGURES_DIR / f"fig3_engine_strokes_and_dynamics.{ext}"
        fig3.savefig(out3, dpi=240)
        save_plot_provenance(
            str(out3),
            str(report_path),
            used_keys,
            solver_name="BEM_EngineCycle_3D",
            solver_parameters=sidecar_meta,
        )
        shutil.copy2(out3, PAPER_FIGURES_DIR / out3.name)
        for sc in ENGINE_FIGURES_DIR.glob(f"{out3.stem}*.provenance.json"):
            shutil.copy2(sc, PAPER_FIGURES_DIR / sc.name)
        generated.append(out3)
    plt.close(fig3)

    return generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Positive integer runs a fast local micro-probe; 0 runs the full campaign.",
    )
    parser.add_argument("--n-xi", type=int, default=12, help="Gauss-Legendre frequency quadrature count.")
    parser.add_argument("--blender-frames", type=int, default=72, help="Keyframe count per 90-deg cycle for video.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--workers", type=int, default=4, help="Parallel process workers across designs.")
    parser.add_argument(
        "--recompute-dynamics-only",
        action="store_true",
        help="Recompute 2-DOF dynamics, provenance metrics, macros, and Figures 1-3 from existing BEM report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    resolved_device = detect_compute_device(args.device)
    ENGINE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    report_path = (
        ENGINE_RESULTS_DIR / "engine_cycle_microprobe.json"
        if int(args.max_steps) > 0
        else ENGINE_RESULTS_DIR / "engine_cycle_report.json"
    )

    if args.recompute_dynamics_only:
        if not report_path.is_file():
            raise FileNotFoundError(f"Cannot --recompute-dynamics-only; missing BEM report: {report_path}")
        with report_path.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
        design_results = report["designs"]
        dyn_steps = 400 if bool(report.get("time_truncated", False)) else 7200
        for name in ENGINE_DESIGN_NAMES:
            ls = design_results[name]["landscape_2d"]
            zg = np.asarray(ls["z_grid_um"], dtype=np.float64)
            tg = np.asarray(ls["theta_grid_deg"], dtype=np.float64)
            eg = np.asarray(ls["energy_aJ"], dtype=np.float64)
            fzg = np.asarray(ls["f_z_pN"], dtype=np.float64)
            taug = np.asarray(ls["tau_theta_pN_um"], dtype=np.float64)
            design_results[name]["dynamics"] = {
                "ballistic": simulate_coupled_dynamics(
                    name, zg, tg, eg, fzg, taug, mode="ballistic", n_steps=dyn_steps
                ),
                "pad_release_engine": simulate_coupled_dynamics(
                    name, zg, tg, eg, fzg, taug, mode="pad_release_engine", n_steps=dyn_steps
                ),
                "vertical_vibro_engine": simulate_coupled_dynamics(
                    name, zg, tg, eg, fzg, taug, mode="vertical_vibro_engine", n_steps=dyn_steps
                ),
            }
        report["blender_frames"] = int(args.blender_frames)
    else:
        tasks = [
            {
                "design_name": name,
                "max_steps": int(args.max_steps),
                "n_xi": int(args.n_xi),
                "device": resolved_device,
            }
            for name in ENGINE_DESIGN_NAMES
        ]

        design_results = {}
        max_workers = min(len(tasks), max(1, int(args.workers))) if resolved_device == "cpu" else 1
        if max_workers > 1:
            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                for item in pool.map(evaluate_single_design_campaign, tasks):
                    design_results[item["design_name"]] = item
        else:
            for t_spec in tasks:
                item = evaluate_single_design_campaign(t_spec)
                design_results[item["design_name"]] = item

        report = {
            "project": "Fractal_Casimir_Engine",
            "branch": "fractal-casimir-engine",
            "status": "completed",
            "time_truncated": int(args.max_steps) > 0,
            "max_steps": int(args.max_steps),
            "n_xi": int(args.n_xi),
            "blender_frames": int(args.blender_frames),
            "device": resolved_device,
            "elapsed_seconds": time.perf_counter() - started,
            "designs": design_results,
        }

    atomic_write_json(report_path, report)

    metrics_path = (
        ENGINE_RESULTS_DIR / "probe_provenance_metrics.json"
        if int(args.max_steps) > 0
        else ENGINE_RESULTS_DIR / "provenance_metrics.json"
    )
    macros_path = (
        ENGINE_RESULTS_DIR / "probe_macros_results.tex"
        if int(args.max_steps) > 0
        else ENGINE_RESULTS_DIR / "macros_results.tex"
    )
    used_keys = log_all_provenance_metrics(report, metrics_path, macros_path)

    if not metrics_path.is_file() or metrics_path.stat().st_size == 0:
        raise RuntimeError("[ERROR: RUN_DATA_MISSING] provenance_metrics.json missing or empty.")

    if int(args.max_steps) == 0:
        figs = generate_figures(report_path, metrics_path, used_keys)
        print(f"[ENGINE-BEM] Generated {len(figs)} grounded figures with provenance sidecars.")

    for name in ENGINE_DESIGN_NAMES:
        cyc = design_results[name]["closed_cycle"]
        b1 = design_results[name]["benchmarks"]["stroke1_repulsive_z92nm_th22deg"]["vector_standard_0K"]
        b3 = design_results[name]["benchmarks"]["stroke3_attractive_z84nm_th64deg"]["vector_standard_0K"]
        dyn = design_results[name]["dynamics"]["pad_release_engine"]
        print(
            f"  {name:28s} | Stroke I: Fz={b1['f_z_pN']:+7.4f} pN, tau={b1['tau_theta_pN_um']:+7.4f} pN*um | "
            f"Stroke III: Fz={b3['f_z_pN']:+7.4f} pN, tau={b3['tau_theta_pN_um']:+7.4f} pN*um | "
            f"Loopres={cyc['closed_loop_net_work_aJ']:+.2e} aJ | SpinUp={dyn['net_rotation_deg']:+6.1f} deg"
        )
    print(f"[ENGINE-BEM] Completed in {report['elapsed_seconds']:.2f}s -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
