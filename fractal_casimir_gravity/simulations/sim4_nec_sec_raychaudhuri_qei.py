"""Simulation IV: Rotary NEC/SEC Switching, Raychaudhuri Geodesic Lensing, and Worldline QEIs.

Implements Section VII of the manuscript:
  - Maps 2D (r, z) cross-sections of NEC_z = T_{00} + T_{zz} and SEC = 2 T_{00} + T^mu_mu
    at open-aperture (theta_open = 0) vs facing-sector (theta_face = pi/4) states.
  - Sweeps rotor angle theta across [0, pi/4] to integrate axial Raychaudhuri null and timelike
    geodesic expansion shifts across PEC EM, conformal scalar (xi=1/6), and minimal scalar (xi=0).
  - Evaluates Lorentzian-sampled Ford-Roman worldline QEI across rotation rates omega_tilde.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Dict

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fractal_casimir_gravity.analytics.units_and_identities import minkowski_trace  # noqa: E402
from fractal_casimir_gravity.solvers.bem_scattering import (  # noqa: E402
    compute_four_pass_stress_tensor,
    get_torch_device,
)
from fractal_casimir_gravity.solvers.cpsc_geometry import CPSCSpec, build_radial_tracks  # noqa: E402
from fractal_casimir_gravity.solvers.linearized_gravity import (  # noqa: E402
    evaluate_ford_roman_worldline_qei,
    integrate_raychaudhuri_geodesics,
)
from fractal_casimir_gravity.utils.metrics_logger import (  # noqa: E402
    log_metric,
    log_step,
    save_simulation_json,
)


def run_simulation(
    max_steps: int | None = None,
    planned_steps: int = 24,
    results_dir: str = "fractal_casimir_gravity/results",
) -> Dict[str, object]:
    """Execute Phenomenon IV energy-condition, Raychaudhuri, and Ford-Roman QEI sweep."""
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
    tracks = build_radial_tracks(spec_n3)
    # Central generation-1 facing-sector gap channel at phi = pi / M_low = pi / 4
    central_trk = next((t for t in tracks if t.generation == 1), tracks[len(tracks) // 2])
    phi_face_meridian = math.pi / spec_n3.m_low
    r_ray = central_trk.r_center
    z_ray = np.linspace(-0.116, -0.104, 16)
    pts_ray = np.column_stack([
        np.full_like(z_ray, r_ray * math.cos(phi_face_meridian)),
        np.full_like(z_ray, r_ray * math.sin(phi_face_meridian)),
        z_ray,
    ])

    theta_face = math.pi / spec_n3.m_low
    theta_scan = np.linspace(0.0, theta_face, n_steps)

    log_step(
        "sim4_init_raychaudhuri_qei",
        {"device": str(device), "n_steps": n_steps, "r_ray": r_ray, "phi_meridian": phi_face_meridian},
        metrics_path=metrics_path,
    )

    null_em = np.zeros(n_steps, dtype=np.float64)
    time_em = np.zeros(n_steps, dtype=np.float64)
    null_conf = np.zeros(n_steps, dtype=np.float64)
    time_conf = np.zeros(n_steps, dtype=np.float64)
    null_min = np.zeros(n_steps, dtype=np.float64)
    time_min = np.zeros(n_steps, dtype=np.float64)
    time_min_trace_part = np.zeros(n_steps, dtype=np.float64)

    for idx, th in enumerate(theta_scan):
        th_f = float(th)
        t_em = compute_four_pass_stress_tensor(
            spec_n3, th_f, pts_ray, field_model="em_pec",
            n_kappa=10, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.005, device=device,
        )["t_mutual"]
        ray_em = integrate_raychaudhuri_geodesics(t_em, z_ray)
        null_em[idx] = float(ray_em["delta_theta_null"])
        time_em[idx] = float(ray_em["delta_theta_time"])

        t_cf = compute_four_pass_stress_tensor(
            spec_n3, th_f, pts_ray, field_model="scalar_conformal",
            n_kappa=10, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.005, device=device,
        )["t_mutual"]
        ray_cf = integrate_raychaudhuri_geodesics(t_cf, z_ray)
        null_conf[idx] = float(ray_cf["delta_theta_null"])
        time_conf[idx] = float(ray_cf["delta_theta_time"])

        t_mn = compute_four_pass_stress_tensor(
            spec_n3, th_f, pts_ray, field_model="scalar_minimal",
            n_kappa=10, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.005, device=device,
        )["t_mutual"]
        ray_mn = integrate_raychaudhuri_geodesics(t_mn, z_ray)
        null_min[idx] = float(ray_mn["delta_theta_null"])
        time_min[idx] = float(ray_mn["delta_theta_time"])
        time_min_trace_part[idx] = float(ray_mn["delta_theta_time_trace_part"])

    # 2D (r, z) cross-section maps:
    #   - Open-aperture meridian (phi = 0) at theta_open = 0
    #   - Facing-sector meridian (phi = pi/4) at theta_face = pi/4
    nr_map = 24
    nz_map = 18
    r_vals = np.linspace(spec_n3.r_in + 0.02, spec_n3.r_out - 0.02, nr_map)
    z_vals = np.linspace(-0.114, -0.006, nz_map)
    gr, gz = np.meshgrid(r_vals, z_vals, indexing="ij")
    pts_rz_open = np.column_stack([gr.ravel(), np.zeros(gr.size), gz.ravel()])
    pts_rz_face = np.column_stack([
        gr.ravel() * math.cos(phi_face_meridian),
        gr.ravel() * math.sin(phi_face_meridian),
        gz.ravel(),
    ])

    res_rz_open = compute_four_pass_stress_tensor(
        spec_n3, 0.0, pts_rz_open, field_model="em_pec",
        n_kappa=10, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.006, device=device,
    )
    res_rz_face = compute_four_pass_stress_tensor(
        spec_n3, theta_face, pts_rz_face, field_model="em_pec",
        n_kappa=10, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.006, device=device,
    )

    t_open = res_rz_open["t_mutual"].reshape((nr_map, nz_map, 4, 4))
    t_face = res_rz_face["t_mutual"].reshape((nr_map, nz_map, 4, 4))
    valid_open = res_rz_open["valid_mask"].reshape((nr_map, nz_map))
    valid_face = res_rz_face["valid_mask"].reshape((nr_map, nz_map))

    nec_z_open = t_open[:, :, 0, 0] + t_open[:, :, 3, 3]
    nec_z_face = t_face[:, :, 0, 0] + t_face[:, :, 3, 3]
    sec_open = 2.0 * t_open[:, :, 0, 0] + minkowski_trace(t_open)
    sec_face = 2.0 * t_face[:, :, 0, 0] + minkowski_trace(t_face)

    nec_min_face = float(np.min(nec_z_face[valid_face])) if np.any(valid_face) else float(np.min(nec_z_face))
    nec_max_open = float(np.max(nec_z_open[valid_open])) if np.any(valid_open) else float(np.max(nec_z_open))
    if np.any(valid_open):
        r_weights = gr[valid_open]
        pos_mask = sec_open[valid_open] > 0.0
        sec_pos_vol_frac = float(np.sum(r_weights[pos_mask]) / max(float(np.sum(r_weights)), 1.0e-30))
    else:
        sec_pos_vol_frac = 0.0

    null_switch_delta = float(null_em[-1] - null_em[0])
    trace_share_min = float(
        np.max(np.abs(time_min_trace_part)) / max(float(np.max(np.abs(time_min))), 1.0e-30)
    )

    # Worldline Ford-Roman QEI along azimuthal ring inside facing gap (z_0 = -0.110, r_0 = central_trk.r_center)
    # Within a static boundary gap of wall clearance d_wall = d_0 / 2, causal sub-reflection worldline
    # sampling holds for effective width tau_eff = (tau_Omega^{-2} + d_wall^{-2})^{-1/2}.
    n_phi_qei = 48
    phi_ring = np.linspace(0.0, 2.0 * math.pi / spec_n3.m_gcd, n_phi_qei, endpoint=False)
    pts_qei = np.column_stack([
        central_trk.r_center * np.cos(phi_ring),
        central_trk.r_center * np.sin(phi_ring),
        np.full_like(phi_ring, -0.110),
    ])
    t_qei_ring = compute_four_pass_stress_tensor(
        spec_n3, theta_face, pts_qei, field_model="em_pec",
        n_kappa=10, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.006, device=device,
    )["t_mutual"][:, 0, 0]

    omega_list = np.geomspace(0.05, 8.0, 18)
    dphi_vane = 0.28 * (2.0 * math.pi / spec_n3.m_up)
    tau_causal = 0.5 * spec_n3.d_0
    qei_saturations = []
    for om in omega_list:
        tau_pass = dphi_vane / (spec_n3.m_up * float(om))
        tau_eff = 1.0 / math.hypot(1.0 / tau_pass, 1.0 / tau_causal)
        qei_res = evaluate_ford_roman_worldline_qei(t_qei_ring, phi_ring, float(om), tau_eff, field_model="em_pec")
        qei_saturations.append(float(qei_res["saturation_ratio"]))
    max_qei_sat = float(np.max(qei_saturations))

    log_metric("fcg_ec_nec_z_min_facing_phase", nec_min_face, step_id="sim4_ec", metrics_path=metrics_path)
    log_metric("fcg_ec_nec_z_max_open_phase", nec_max_open, step_id="sim4_ec", metrics_path=metrics_path)
    log_metric("fcg_ec_sec_positive_volume_frac_open", sec_pos_vol_frac, step_id="sim4_ec", metrics_path=metrics_path)
    log_metric("fcg_ec_raychaudhuri_null_switch_delta", null_switch_delta, step_id="sim4_ec", metrics_path=metrics_path)
    log_metric("fcg_ec_raychaudhuri_time_trace_share", trace_share_min, step_id="sim4_ec", metrics_path=metrics_path)
    log_metric("fcg_ec_ford_roman_qei_saturation_ratio", max_qei_sat, step_id="sim4_ec", metrics_path=metrics_path)

    payload = {
        "theta_deg_scan": np.degrees(theta_scan).tolist(),
        "delta_theta_null_em": null_em.tolist(),
        "delta_theta_time_em": time_em.tolist(),
        "delta_theta_null_conf": null_conf.tolist(),
        "delta_theta_time_conf": time_conf.tolist(),
        "delta_theta_null_min": null_min.tolist(),
        "delta_theta_time_min": time_min.tolist(),
        "r_vals": r_vals.tolist(),
        "z_vals": z_vals.tolist(),
        "nec_z_open": nec_z_open.tolist(),
        "nec_z_face": nec_z_face.tolist(),
        "sec_open": sec_open.tolist(),
        "sec_face": sec_face.tolist(),
        "omega_qei_list": omega_list.tolist(),
        "qei_saturation_ratios": qei_saturations,
    }
    out_json = out_dir / "sim4_nec_sec_raychaudhuri_qei.json"
    save_simulation_json(out_json, "Sim4_NEC_SEC_Raychaudhuri_QEI", "CPSC_Breathing44_N3", payload)
    print(f"[SIM4] Completed {n_steps} steps (QEI max sat = {max_qei_sat:.4e}) -> {out_json}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Phenomenon IV: NEC/SEC Switching, Raychaudhuri & QEI")
    parser.add_argument("--max-steps", type=int, default=None, help="Limit step count for profiling/testing")
    parser.add_argument("--planned-steps", type=int, default=24, help="Full angular lensing sweep steps")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Output directory for JSON and provenance")
    args = parser.parse_args()
    run_simulation(max_steps=args.max_steps, planned_steps=args.planned_steps, results_dir=args.results_dir)


if __name__ == "__main__":
    main()
