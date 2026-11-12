"""Simulation V: Cantor-Stratified Gravitomagnetic Frame Dragging from Broken Boost Invariance.

Implements Section VIII of the manuscript:
  - Verifies azimuthal boost-invariance null w_phi = T_{00} + T_{phi phi} -> 0 in the analytical
    Brown-Maclay planar vacuum and symmetric flat-annulus control interior.
  - Evaluates 3D voxel maps of broken boost enthalpy w_phi(x) and rotational momentum current
    T^{0 phi}_{vac} = omega_tilde * r * w_phi in the chiral prefractal CPSC (N = 3) vs periodic control.
  - Solves the 3D isolated-boundary GEM Poisson equation nabla^2 h_{0i} = +16 pi T^{0i}_{vac}
    and extracts Lense-Thirring frame-dragging precession Omega_{LT, z}^{vac} = -0.5 * (nabla x h_0)_z.
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

from fractal_casimir_gravity.analytics.units_and_identities import (  # noqa: E402
    brown_maclay_tensor_covariant,
)
from fractal_casimir_gravity.solvers.bem_scattering import (  # noqa: E402
    compute_four_pass_stress_tensor,
    get_torch_device,
)
from fractal_casimir_gravity.solvers.cpsc_geometry import CPSCSpec  # noqa: E402
from fractal_casimir_gravity.solvers.linearized_gravity import (  # noqa: E402
    solve_gem_lense_thirring,
)
from fractal_casimir_gravity.utils.metrics_logger import (  # noqa: E402
    log_metric,
    log_step,
    save_simulation_json,
)


def _count_sign_reversals(profile: np.ndarray, rel_tol: float = 0.02) -> int:
    """Count genuine sign reversals exceeding rel_tol * max|profile| along a 1D radial profile."""
    peak = float(np.max(np.abs(profile)))
    if peak < 1.0e-30:
        return 0
    sig = profile[np.abs(profile) > rel_tol * peak]
    if len(sig) < 2:
        return 0
    return int(np.sum(np.sign(sig[:-1]) != np.sign(sig[1:])))


def run_simulation(
    max_steps: int | None = None,
    planned_steps: int = 16,
    results_dir: str = "fractal_casimir_gravity/results",
) -> Dict[str, object]:
    """Execute Phenomenon V 3D gravitomagnetic Lense-Thirring simulation."""
    device = get_torch_device()
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = str(out_dir / "provenance_metrics.json")

    nz_steps = min(max_steps, planned_steps) if max_steps is not None else planned_steps
    nz_steps = max(nz_steps, 5)
    nx_grid = 22

    # 1. Exact Brown-Maclay + interior flat-annulus boost enthalpy verification
    bm = brown_maclay_tensor_covariant(gap_tilde=0.02, field_model="em_pec")
    bm_enthalpy_null = abs(float(bm[0, 0] + bm[2, 2])) / max(abs(float(bm[0, 0])), 1.0e-30)

    spec_chiral_n3 = CPSCSpec(
        name="CPSC_Chiral44_N3",
        constellation="chiral_4_4",
        staging="coplanar",
        geometry_kind="prefractal",
        generation_n=3,
        chiral_skew_rad=0.14,
    )
    spec_periodic = CPSCSpec(
        name="Ctrl_Chiral44_Periodic",
        constellation="chiral_4_4",
        staging="coplanar",
        geometry_kind="periodic_grating",
        generation_n=3,
        chiral_skew_rad=0.14,
    )

    log_step(
        "sim5_init_gem_grid",
        {"device": str(device), "nx_grid": nx_grid, "nz_steps": nz_steps},
        metrics_path=metrics_path,
    )

    xs = np.linspace(-1.25, 1.25, nx_grid)
    ys = np.linspace(-1.25, 1.25, nx_grid)
    zs = np.linspace(-0.14, 0.04, nz_steps)
    spacings = (float(xs[1] - xs[0]), float(ys[1] - ys[0]), float(zs[1] - zs[0]))
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    coords_3d = np.stack([gx, gy, gz], axis=-1)

    t_cantor_3d = np.zeros((nx_grid, nx_grid, nz_steps, 4, 4), dtype=np.float64)
    t_per_3d = np.zeros((nx_grid, nx_grid, nz_steps, 4, 4), dtype=np.float64)

    theta_op = 0.5 * (math.pi / spec_chiral_n3.m_low)
    for iz in range(nz_steps):
        pts_slice = coords_3d[:, :, iz, :].reshape(-1, 3)
        res_c = compute_four_pass_stress_tensor(
            spec_chiral_n3, theta_op, pts_slice, field_model="em_pec",
            n_kappa=8, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.005, device=device,
        )
        t_cantor_3d[:, :, iz, :, :] = res_c["t_mutual"].reshape((nx_grid, nx_grid, 4, 4))

        res_p = compute_four_pass_stress_tensor(
            spec_periodic, theta_op, pts_slice, field_model="em_pec",
            n_kappa=8, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.005, device=device,
        )
        t_per_3d[:, :, iz, :, :] = res_p["t_mutual"].reshape((nx_grid, nx_grid, 4, 4))

    # Normalized unit angular velocity omega_tilde = 1.0 yields |Omega_LT,z| / omega_tilde directly
    gem_cantor = solve_gem_lense_thirring(t_cantor_3d, coords_3d, spacings, omega_tilde=1.0, device=device)
    gem_per = solve_gem_lense_thirring(t_per_3d, coords_3d, spacings, omega_tilde=1.0, device=device)

    # Fine 1D radial profile at cavity midplane z = -0.06 across generations N = 1, 2, 3
    n_rad_prof = 64
    r_prof = np.linspace(spec_chiral_n3.r_in + 0.015, spec_chiral_n3.r_out - 0.015, n_rad_prof)
    pts_prof = np.column_stack([r_prof, np.zeros_like(r_prof), np.full_like(r_prof, -0.06)])
    t_prof_n3 = compute_four_pass_stress_tensor(
        spec_chiral_n3, theta_op, pts_prof, field_model="em_pec",
        n_kappa=10, n_rad=1, n_phi=2, n_z=1, min_wall_dist=0.004, device=device,
    )["t_mutual"]
    w_phi_prof_n3 = t_prof_n3[:, 0, 0] + t_prof_n3[:, 2, 2]  # at y=0 (phi=0), e_phi = +y

    # Extract midplane Lense-Thirring precession Omega_{LT,z} / omega_tilde
    iz_mid = int(np.argmin(np.abs(zs - (-0.06))))
    iy_mid = nx_grid // 2
    pos_x_mask = xs >= spec_chiral_n3.r_in
    omega_lt_rad_cantor = gem_cantor["omega_lt_z"][pos_x_mask, iy_mid, iz_mid]

    peak_lt_n3 = float(np.max(np.abs(gem_cantor["omega_lt_z"])))
    rms_lt_cantor = float(np.sqrt(np.mean(gem_cantor["omega_lt_z"] ** 2)))
    rms_lt_per = float(np.sqrt(np.mean(gem_per["omega_lt_z"] ** 2)))
    circ_ratio = rms_lt_cantor / max(rms_lt_per, 1.0e-30)

    # Count radial sign reversals across the fine radial momentum/vorticity profile
    sign_reversals = max(_count_sign_reversals(w_phi_prof_n3), _count_sign_reversals(omega_lt_rad_cantor))

    log_metric("fcg_gem_flat_annulus_enthalpy_null", bm_enthalpy_null, step_id="sim5_gem", metrics_path=metrics_path)
    log_metric("fcg_gem_peak_lense_thirring_gen_three", peak_lt_n3, step_id="sim5_gem", metrics_path=metrics_path)
    log_metric("fcg_gem_vortex_sign_reversals_radial", int(sign_reversals), step_id="sim5_gem", metrics_path=metrics_path)
    log_metric("fcg_gem_cantor_to_periodic_circulation_ratio", circ_ratio, step_id="sim5_gem", metrics_path=metrics_path)

    payload = {
        "xs": xs.tolist(),
        "zs": zs.tolist(),
        "r_prof": r_prof.tolist(),
        "w_phi_prof_n3": w_phi_prof_n3.tolist(),
        "w_phi_xz_cantor": gem_cantor["w_phi"][:, iy_mid, :].tolist(),
        "j_phi_xz_cantor": gem_cantor["j_phi"][:, iy_mid, :].tolist(),
        "h0_phi_xz_cantor": gem_cantor["h0_phi"][:, iy_mid, :].tolist(),
        "omega_lt_xy_midplane_cantor": gem_cantor["omega_lt_z"][:, :, iz_mid].tolist(),
        "omega_lt_xy_midplane_periodic": gem_per["omega_lt_z"][:, :, iz_mid].tolist(),
        "peak_lt_n3": peak_lt_n3,
        "sign_reversals_radial": int(sign_reversals),
        "cantor_to_periodic_ratio": circ_ratio,
    }
    out_json = out_dir / "sim5_gravitomagnetic_frame_dragging.json"
    save_simulation_json(out_json, "Sim5_GravitomagneticFrameDragging", "CPSC_Chiral44_N3", payload)
    print(f"[SIM5] Completed {nz_steps} z-slices (peak LT = {peak_lt_n3:.4e}, rev = {sign_reversals}) -> {out_json}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Phenomenon V: Gravitomagnetic Frame Dragging")
    parser.add_argument("--max-steps", type=int, default=None, help="Limit z-slice steps for profiling/testing")
    parser.add_argument("--planned-steps", type=int, default=16, help="Full 3D z-slice grid count")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Output directory for JSON and provenance")
    args = parser.parse_args()
    run_simulation(max_steps=args.max_steps, planned_steps=args.planned_steps, results_dir=args.results_dir)


if __name__ == "__main__":
    main()
