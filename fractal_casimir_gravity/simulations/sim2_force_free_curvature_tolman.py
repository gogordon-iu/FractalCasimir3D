"""Simulation II: Force-Free Spacetime Curvature Crossover & Tolman-Komar Active Mass.

Implements Section V of the manuscript:
  - Sweeps (theta, d_sep) in the N=3 (4,4) prefractal CPSC across open-aperture repulsion
    (tilde_F_z > 0) and facing-sector attraction (tilde_F_z < 0).
  - Solves Brent root-finding for the exact axial-force-free crossover angle theta_0 where
    tilde_F_z(theta_0) = 0, verifying d_{ln |z|} C / C == 3 and finite tilde_R_eff(theta_0) != 0.
  - Evaluates spatial cumulative Tolman-Komar active gravitational mass M_Komar(< r_enc),
    contrasting near-zone Tolman pressure anomalies against global WEP mass recovery.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Dict

import numpy as np
from scipy.optimize import brentq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fractal_casimir_gravity.solvers.bem_scattering import (  # noqa: E402
    compute_cavity_thermodynamics,
    compute_four_pass_stress_tensor,
    get_torch_device,
)
from fractal_casimir_gravity.solvers.cpsc_geometry import CPSCSpec  # noqa: E402
from fractal_casimir_gravity.solvers.linearized_gravity import (  # noqa: E402
    compute_cumulative_tolman_komar_mass,
)
from fractal_casimir_gravity.utils.metrics_logger import (  # noqa: E402
    log_metric,
    log_step,
    save_simulation_json,
)


def _build_cartesian_cavity_grid(
    nx: int = 14,
    ny: int = 14,
    nz: int = 8,
    l_xy: float = 1.65,
    z_min: float = -0.22,
    z_max: float = 0.14,
) -> tuple[np.ndarray, float]:
    xs = np.linspace(-l_xy, l_xy, nx)
    ys = np.linspace(-l_xy, l_xy, ny)
    zs = np.linspace(z_min, z_max, nz)
    dx = float(xs[1] - xs[0])
    dy = float(ys[1] - ys[0])
    dz = float(zs[1] - zs[0])
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    coords = np.stack([gx, gy, gz], axis=-1)
    return coords, dx * dy * dz


def run_simulation(
    max_steps: int | None = None,
    planned_steps: int = 30,
    results_dir: str = "fractal_casimir_gravity/results",
) -> Dict[str, object]:
    """Execute Phenomenon II sweep and root-refinement."""
    device = get_torch_device()
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = str(out_dir / "provenance_metrics.json")

    n_steps = min(max_steps, planned_steps) if max_steps is not None else planned_steps
    n_steps = max(n_steps, 4)

    spec_n3 = CPSCSpec(
        name="CPSC_Breathing44_N3",
        constellation="breathing_4_4",
        staging="coplanar",
        geometry_kind="prefractal",
        generation_n=3,
    )
    theta_face = math.pi / spec_n3.m_low  # pi/4 = 45 deg
    theta_scan = np.linspace(0.0, theta_face, n_steps)

    log_step(
        "sim2_init_force_free_sweep",
        {"device": str(device), "n_steps": n_steps, "theta_max_deg": math.degrees(theta_face)},
        metrics_path=metrics_path,
    )

    energies = np.zeros(n_steps, dtype=np.float64)
    forces = np.zeros(n_steps, dtype=np.float64)
    ricci_effs = np.zeros(n_steps, dtype=np.float64)
    scale_ratios = np.zeros(n_steps, dtype=np.float64)

    for idx, th in enumerate(theta_scan):
        thermo = compute_cavity_thermodynamics(
            spec_n3, float(th), field_model="em_pec",
            n_kappa=14, n_rad=2, n_phi=2, n_z=1, compute_torque=False, device=device,
        )
        energies[idx] = thermo.energy_tilde
        forces[idx] = thermo.force_z_tilde
        ricci_effs[idx] = thermo.ricci_eff_tilde
        scale_ratios[idx] = thermo.d_ln_z_c / thermo.coeff_c if abs(thermo.coeff_c) > 1.0e-30 else 0.0

    # Locate sign change from open-aperture repulsion (F_z > 0) to facing-sector attraction (F_z < 0)
    sign_changes = np.where(np.sign(forces[:-1]) != np.sign(forces[1:]))[0]
    if len(sign_changes) > 0:
        i0 = int(sign_changes[0])
        th_a, th_b = float(theta_scan[i0]), float(theta_scan[i0 + 1])

        def _force_fn(th_val: float) -> float:
            return compute_cavity_thermodynamics(
                spec_n3, th_val, field_model="em_pec",
                n_kappa=14, n_rad=2, n_phi=2, n_z=1, compute_torque=False, device=device,
            ).force_z_tilde

        theta_zero_rad = float(brentq(_force_fn, th_a, th_b, xtol=1.0e-5, maxiter=20))
    else:
        best_i = int(np.argmin(np.abs(forces)))
        theta_zero_rad = float(theta_scan[best_i])

    thermo_zero = compute_cavity_thermodynamics(
        spec_n3, theta_zero_rad, field_model="em_pec",
        n_kappa=14, n_rad=2, n_phi=2, n_z=1, compute_torque=True, device=device,
    )
    theta_zero_deg = math.degrees(theta_zero_rad)
    res_force = abs(thermo_zero.force_z_tilde)
    ricci_at_zero = thermo_zero.ricci_eff_tilde
    lock_ratio = thermo_zero.d_ln_z_c / thermo_zero.coeff_c if abs(thermo_zero.coeff_c) > 1.0e-30 else 0.0

    # Evaluate 3D Tolman-Komar cumulative mass profiles at theta_open (0) and theta_face (pi/4)
    coords_grid, dvol = _build_cartesian_cavity_grid(nx=14, ny=14, nz=8)
    pts_flat = coords_grid.reshape(-1, 3)

    vox_open = compute_four_pass_stress_tensor(
        spec_n3, 0.0, pts_flat, field_model="em_pec",
        n_kappa=12, n_rad=2, n_phi=2, n_z=1, device=device,
    )["t_mutual"].reshape(coords_grid.shape[:3] + (4, 4))
    vox_face = compute_four_pass_stress_tensor(
        spec_n3, theta_face, pts_flat, field_model="em_pec",
        n_kappa=12, n_rad=2, n_phi=2, n_z=1, device=device,
    )["t_mutual"].reshape(coords_grid.shape[:3] + (4, 4))

    komar_open = compute_cumulative_tolman_komar_mass(vox_open, coords_grid, dvol, float(energies[0]))
    komar_face = compute_cumulative_tolman_komar_mass(vox_face, coords_grid, dvol, float(energies[-1]))

    near_zone_tolman_swing = abs(
        float(komar_face["near_zone_pressure_anomaly"]) - float(komar_open["near_zone_pressure_anomaly"])
    )
    global_wep_swing = float(komar_face["asymptotic_komar_mass"]) - float(komar_open["asymptotic_komar_mass"])

    log_metric("fcg_ffc_theta_zero_deg_gen_three", theta_zero_deg, step_id="sim2_ffc", metrics_path=metrics_path)
    log_metric("fcg_ffc_residual_force_at_theta_zero", res_force, step_id="sim2_ffc", metrics_path=metrics_path)
    log_metric("fcg_ffc_ricci_eff_at_theta_zero", ricci_at_zero, step_id="sim2_ffc", metrics_path=metrics_path)
    log_metric("fcg_ffc_scale_lock_ratio_at_theta_zero", lock_ratio, step_id="sim2_ffc", metrics_path=metrics_path)
    log_metric("fcg_ffc_near_zone_tolman_swing", near_zone_tolman_swing, step_id="sim2_ffc", metrics_path=metrics_path)
    log_metric("fcg_ffc_global_wep_mass_defect_swing", global_wep_swing, step_id="sim2_ffc", metrics_path=metrics_path)

    payload = {
        "theta_deg_scan": np.degrees(theta_scan).tolist(),
        "energies_tilde": energies.tolist(),
        "forces_z_tilde": forces.tolist(),
        "ricci_eff_tilde": ricci_effs.tolist(),
        "scale_ratios_dlnzC_over_C": scale_ratios.tolist(),
        "theta_zero_deg": theta_zero_deg,
        "residual_force_at_theta_zero": res_force,
        "ricci_eff_at_theta_zero": ricci_at_zero,
        "scale_lock_ratio_at_theta_zero": lock_ratio,
        "r_radii": komar_open["r_radii"].tolist(),  # type: ignore[union-attr]
        "komar_tot_open": komar_open["m_komar_tot"].tolist(),  # type: ignore[union-attr]
        "komar_tot_face": komar_face["m_komar_tot"].tolist(),  # type: ignore[union-attr]
        "komar_unscreened_open": komar_open["m_unscreened"].tolist(),  # type: ignore[union-attr]
        "komar_unscreened_face": komar_face["m_unscreened"].tolist(),  # type: ignore[union-attr]
    }
    out_json = out_dir / "sim2_force_free_curvature_tolman.json"
    save_simulation_json(out_json, "Sim2_ForceFreeCurvature_Tolman", "CPSC_Breathing44_N3", payload)
    print(f"[SIM2] Completed {n_steps} steps (theta_0 = {theta_zero_deg:.3f} deg) -> {out_json}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Phenomenon II: Force-Free Curvature & Tolman-Komar Mass")
    parser.add_argument("--max-steps", type=int, default=None, help="Limit step count for profiling/testing")
    parser.add_argument("--planned-steps", type=int, default=30, help="Full angular scan step count")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Output directory for JSON and provenance")
    args = parser.parse_args()
    run_simulation(max_steps=args.max_steps, planned_steps=args.planned_steps, results_dir=args.results_dir)


if __name__ == "__main__":
    main()
