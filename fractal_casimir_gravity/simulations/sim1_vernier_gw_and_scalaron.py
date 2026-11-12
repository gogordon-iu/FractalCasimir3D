"""Simulation I: Symmetry-Filtered Spin-2 Vernier Gravitational Radiation & Spin-0 Scalaron Waves.

Implements Section IV of the manuscript:
  - Verifies exact vanishing of rigid C_6 and C_4 l=2, m=2 mass quadrupoles.
  - Computes 3D four-pass vacuum stress-energy modulation across theta in the (6,4) Vernier CPSC
    for PEC EM, conformal scalar (xi=1/6), minimal scalar (xi=0), and matched periodic grating control.
  - Verifies the relativistic second-moment covariant virial theorem (Appendix A).
  - Evaluates far-zone spin-2 waveforms tilde_h_+, tilde_h_x and Peters-Mathews luminosity.
  - Evaluates (4,4) Effective-Trace monopole (l=0) Starobinsky scalaron radiation vs flat-plate null.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fractal_casimir_gravity.solvers.bem_scattering import (  # noqa: E402
    compute_cavity_thermodynamics,
    compute_four_pass_stress_tensor,
    get_torch_device,
)
from fractal_casimir_gravity.solvers.cpsc_geometry import (  # noqa: E402
    CPSCSpec,
    build_radial_tracks,
    verify_rigid_quadrupole_moment,
)
from fractal_casimir_gravity.solvers.linearized_gravity import (  # noqa: E402
    compute_scalaron_monopole_waveform,
    compute_vernier_gw_waveforms,
    construct_covariant_virial_and_quadrupole,
)
from fractal_casimir_gravity.utils.metrics_logger import log_metric, log_step  # noqa: E402


def _build_cavity_ring_voxels(
    spec: CPSCSpec,
    n_phi_vox: int = 36,
    n_z_vox: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Build cylindrical quadrature nodes and volumes inside the CPSC gap tracks."""
    tracks = build_radial_tracks(spec)
    phi_edges = np.linspace(0.0, 2.0 * math.pi, n_phi_vox + 1)
    phi_mid = 0.5 * (phi_edges[:-1] + phi_edges[1:])
    dphi = 2.0 * math.pi / n_phi_vox

    pts_list: List[List[float]] = []
    vol_list: List[float] = []
    for trk in tracks:
        r_mid = trk.r_center
        dr = trk.slot_width
        z_low = trk.z_face_top + 0.003
        z_high = trk.z_rim_top - 0.003
        z_edges = np.linspace(z_low, z_high, n_z_vox + 1)
        for iz in range(n_z_vox):
            zm = 0.5 * (z_edges[iz] + z_edges[iz + 1])
            dz = abs(z_edges[iz + 1] - z_edges[iz])
            dv = r_mid * dr * dphi * dz
            for pm in phi_mid:
                pts_list.append([r_mid * math.cos(pm), r_mid * math.sin(pm), zm])
                vol_list.append(dv)
    return np.asarray(pts_list, dtype=np.float64), np.asarray(vol_list, dtype=np.float64)


def run_simulation(
    max_steps: int | None = None,
    planned_steps: int = 48,
    results_dir: str = "fractal_casimir_gravity/results",
    omega_tilde: float = 0.10,
    r_obs_tilde: float = 10.0,
    n_kappa: int = 12,
    n_rad: int = 2,
    n_phi: int = 2,
) -> Dict[str, object]:
    """Execute Phenomenon I simulation sweep with empirical step parameterization."""
    device = get_torch_device()
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = str(out_dir / "provenance_metrics.json")

    n_steps = min(max_steps, planned_steps) if max_steps is not None else planned_steps
    n_steps = max(n_steps, 4)

    spec_vernier_n3 = CPSCSpec(
        name="CPSC_Vernier64_N3",
        constellation="vernier_6_4",
        staging="coplanar",
        geometry_kind="prefractal",
        generation_n=3,
    )
    spec_vernier_per = CPSCSpec(
        name="Ctrl_Vernier64_Periodic",
        constellation="vernier_6_4",
        staging="coplanar",
        geometry_kind="periodic_grating",
        generation_n=3,
    )
    spec_breath_n3 = CPSCSpec(
        name="CPSC_Breathing44_N3",
        constellation="breathing_4_4",
        staging="coplanar",
        geometry_kind="prefractal",
        generation_n=3,
    )
    spec_flat_ctrl = CPSCSpec(
        name="Ctrl_FlatAnnulus",
        constellation="breathing_4_4",
        staging="coplanar",
        geometry_kind="flat_annulus",
        generation_n=0,
    )

    q_u_res, q_l_res = verify_rigid_quadrupole_moment(spec_vernier_n3, theta_rad=0.217)
    rigid_c6_residual = max(q_u_res, q_l_res)
    log_step(
        "sim1_init_rigid_symmetry_audit",
        {
            "device": str(device),
            "n_steps": n_steps,
            "q_upper_c6_res": q_u_res,
            "q_lower_c4_res": q_l_res,
        },
        metrics_path=metrics_path,
    )

    # Fundamental Vernier angular period is 2*pi / M_low = pi / 2 (or full cycle 2*pi/gcd = pi)
    theta_grid = np.linspace(0.0, math.pi, n_steps, endpoint=False)
    pts_cantor, vols_cantor = _build_cavity_ring_voxels(spec_vernier_n3, n_phi_vox=36, n_z_vox=2)
    pts_per, vols_per = _build_cavity_ring_voxels(spec_vernier_per, n_phi_vox=36, n_z_vox=2)

    t00_em_n3 = np.zeros((n_steps, len(vols_cantor)), dtype=np.float64)
    tij_em_n3 = np.zeros((n_steps, len(vols_cantor), 3, 3), dtype=np.float64)
    t00_conf_n3 = np.zeros((n_steps, len(vols_cantor)), dtype=np.float64)
    tij_conf_n3 = np.zeros((n_steps, len(vols_cantor), 3, 3), dtype=np.float64)
    t00_min_n3 = np.zeros((n_steps, len(vols_cantor)), dtype=np.float64)
    tij_min_n3 = np.zeros((n_steps, len(vols_cantor), 3, 3), dtype=np.float64)
    t00_em_per = np.zeros((n_steps, len(vols_per)), dtype=np.float64)
    tij_em_per = np.zeros((n_steps, len(vols_per), 3, 3), dtype=np.float64)

    trace_int_breath_n3 = np.zeros(n_steps, dtype=np.float64)
    trace_int_flat = np.zeros(n_steps, dtype=np.float64)

    v_cav_n3 = math.pi * (spec_breath_n3.r_out**2 - spec_breath_n3.r_in**2) * spec_breath_n3.d_0
    v_cav_flat = math.pi * (spec_flat_ctrl.r_out**2 - spec_flat_ctrl.r_in**2) * spec_flat_ctrl.d_0

    for idx, th in enumerate(theta_grid):
        th_f = float(th)
        res_em = compute_four_pass_stress_tensor(
            spec_vernier_n3, th_f, pts_cantor, field_model="em_pec",
            n_kappa=n_kappa, n_rad=n_rad, n_phi=n_phi, n_z=1, device=device,
        )
        t00_em_n3[idx] = res_em["t_mutual"][:, 0, 0]
        tij_em_n3[idx] = res_em["t_mutual"][:, 1:, 1:]

        res_conf = compute_four_pass_stress_tensor(
            spec_vernier_n3, th_f, pts_cantor, field_model="scalar_conformal",
            n_kappa=n_kappa, n_rad=n_rad, n_phi=n_phi, n_z=1, device=device,
        )
        t00_conf_n3[idx] = res_conf["t_mutual"][:, 0, 0]
        tij_conf_n3[idx] = res_conf["t_mutual"][:, 1:, 1:]

        res_min = compute_four_pass_stress_tensor(
            spec_vernier_n3, th_f, pts_cantor, field_model="scalar_minimal",
            n_kappa=n_kappa, n_rad=n_rad, n_phi=n_phi, n_z=1, device=device,
        )
        t00_min_n3[idx] = res_min["t_mutual"][:, 0, 0]
        tij_min_n3[idx] = res_min["t_mutual"][:, 1:, 1:]

        res_per = compute_four_pass_stress_tensor(
            spec_vernier_per, th_f, pts_per, field_model="em_pec",
            n_kappa=n_kappa, n_rad=n_rad, n_phi=n_phi, n_z=1, device=device,
        )
        t00_em_per[idx] = res_per["t_mutual"][:, 0, 0]
        tij_em_per[idx] = res_per["t_mutual"][:, 1:, 1:]

        thermo_b = compute_cavity_thermodynamics(
            spec_breath_n3, th_f, field_model="em_pec",
            n_kappa=n_kappa, n_rad=n_rad, n_phi=n_phi, n_z=1, compute_torque=False, device=device,
        )
        trace_int_breath_n3[idx] = thermo_b.trace_eff_tilde * v_cav_n3

        thermo_flat = compute_cavity_thermodynamics(
            spec_flat_ctrl, th_f, field_model="em_pec",
            n_kappa=n_kappa, n_rad=2, n_phi=2, n_z=1, compute_torque=False, device=device,
        )
        trace_int_flat[idx] = thermo_flat.trace_eff_tilde * v_cav_flat

    vir_em = construct_covariant_virial_and_quadrupole(
        t00_em_n3, tij_em_n3, pts_cantor, vols_cantor, theta_grid, omega_tilde,
    )
    vir_conf = construct_covariant_virial_and_quadrupole(
        t00_conf_n3, tij_conf_n3, pts_cantor, vols_cantor, theta_grid, omega_tilde,
    )
    vir_min = construct_covariant_virial_and_quadrupole(
        t00_min_n3, tij_min_n3, pts_cantor, vols_cantor, theta_grid, omega_tilde,
    )
    vir_per = construct_covariant_virial_and_quadrupole(
        t00_em_per, tij_em_per, pts_per, vols_per, theta_grid, omega_tilde,
    )

    hp_em, hx_em = compute_vernier_gw_waveforms(vir_em["ddq_dt2"], r_obs_tilde=r_obs_tilde, inclination_rad=0.0)  # type: ignore[arg-type]
    hp_conf, hx_conf = compute_vernier_gw_waveforms(vir_conf["ddq_dt2"], r_obs_tilde=r_obs_tilde, inclination_rad=0.0)  # type: ignore[arg-type]
    hp_min, _ = compute_vernier_gw_waveforms(vir_min["ddq_dt2"], r_obs_tilde=r_obs_tilde, inclination_rad=0.0)  # type: ignore[arg-type]
    hp_per, _ = compute_vernier_gw_waveforms(vir_per["ddq_dt2"], r_obs_tilde=r_obs_tilde, inclination_rad=0.0)  # type: ignore[arg-type]

    time_grid = theta_grid / omega_tilde
    phi_scalaron_n3 = compute_scalaron_monopole_waveform(
        trace_int_breath_n3, time_grid, r_obs_tilde=r_obs_tilde, m_phi_tilde=0.0,
    )
    phi_scalaron_flat = compute_scalaron_monopole_waveform(
        trace_int_flat, time_grid, r_obs_tilde=r_obs_tilde, m_phi_tilde=0.0,
    )

    amp_em = float(np.max(np.abs(hp_em)))
    amp_conf = float(np.max(np.abs(hp_conf)))
    amp_per = float(np.max(np.abs(hp_per)))
    ratio_cantor_per = amp_em / max(amp_per, 1.0e-30)
    amp_scalaron = float(np.max(np.abs(phi_scalaron_n3)))
    amp_flat_null = float(np.max(np.abs(phi_scalaron_flat)))
    virial_err = float(vir_em["virial_rel_err"])

    log_metric("fcg_gw_rigid_c_six_quadrupole_residual", rigid_c6_residual, step_id="sim1_gw", metrics_path=metrics_path)
    log_metric("fcg_gw_virial_conservation_rel_err", virial_err, step_id="sim1_gw", metrics_path=metrics_path)
    log_metric("fcg_gw_vernier_strain_amp_em_gen_three", amp_em, step_id="sim1_gw", metrics_path=metrics_path)
    log_metric("fcg_gw_vernier_strain_amp_conf_gen_three", amp_conf, step_id="sim1_gw", metrics_path=metrics_path)
    log_metric("fcg_gw_vernier_strain_amp_periodic_ctrl", amp_per, step_id="sim1_gw", metrics_path=metrics_path)
    log_metric("fcg_gw_vernier_cantor_to_periodic_ratio", ratio_cantor_per, step_id="sim1_gw", metrics_path=metrics_path)
    log_metric("fcg_gw_scalaron_monopole_amp_gen_three", amp_scalaron, step_id="sim1_gw", metrics_path=metrics_path)
    log_metric("fcg_gw_scalaron_flat_plate_null", amp_flat_null, step_id="sim1_gw", metrics_path=metrics_path)

    payload = {
        "omega_tilde": omega_tilde,
        "r_obs_tilde": r_obs_tilde,
        "theta_grid": theta_grid.tolist(),
        "time_grid": time_grid.tolist(),
        "hp_em_n3": hp_em.tolist(),
        "hx_em_n3": hx_em.tolist(),
        "hp_conf_n3": hp_conf.tolist(),
        "hx_conf_n3": hx_conf.tolist(),
        "hp_min_n3": hp_min.tolist(),
        "hp_periodic": hp_per.tolist(),
        "scalaron_n3": phi_scalaron_n3.tolist(),
        "scalaron_flat_null": phi_scalaron_flat.tolist(),
        "virial_ddq_xx": vir_em["ddq_dt2"][:, 0, 0].tolist(),  # type: ignore[index]
        "virial_2tij_xx": (2.0 * vir_em["tij_tot_tf"][:, 0, 0]).tolist(),  # type: ignore[index]
        "p_gw_em_tilde": float(vir_em["p_gw_tilde"]),
        "azimuthal_t00_snapshot": t00_em_n3[0, :36].tolist(),
    }
    out_json = out_dir / "sim1_vernier_gw_and_scalaron.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[SIM1] Completed {n_steps} steps -> {out_json}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Phenomenon I: Vernier GWs & Scalaron Breathing Waves")
    parser.add_argument("--max-steps", type=int, default=None, help="Limit step count for profiling/testing")
    parser.add_argument("--planned-steps", type=int, default=48, help="Full angular sweep step count")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Output directory for JSON and provenance")
    args = parser.parse_args()
    run_simulation(max_steps=args.max_steps, planned_steps=args.planned_steps, results_dir=args.results_dir)


if __name__ == "__main__":
    main()
