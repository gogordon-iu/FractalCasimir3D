"""Simulation III: Discrete-Scale-Invariant Log-Periodic Spacetime Metric Comb.

Implements Section VI of the manuscript:
  - Sweeps probe/vane vertical elevation |tilde_z| logarithmically across the homothetically
    (r, z)-staged prefractal CPSC (scale b = 3.0, plus b = 2.5 and 4.0) vs single-scale periodic control.
  - Solves the 3D isolated-boundary linearized Einstein equation nabla^2 h_bar_{mu nu} = -16 pi T_{mu nu}^{tot}
    and extracts the scale-compensated Newtonian potential |z|^2 tilde_h_{00} and axial tidal
    Riemann curvature |z|^4 tilde_R_{0z0z}.
  - Recovers the fundamental DSI log-frequency omega_1 = 2*pi / ln(b) and scale factor b_hat,
    and quantifies rotary comb suppression upon switching from theta_open to theta_face.
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

from fractal_casimir_gravity.solvers.bem_scattering import (  # noqa: E402
    compute_four_pass_stress_tensor,
    get_torch_device,
)
from fractal_casimir_gravity.solvers.cpsc_geometry import CPSCSpec  # noqa: E402
from fractal_casimir_gravity.solvers.linearized_gravity import (  # noqa: E402
    fit_log_periodic_metric_comb,
    solve_linearized_einstein_static,
)
from fractal_casimir_gravity.utils.metrics_logger import log_metric, log_step  # noqa: E402


def _eval_homothetic_metric_point(
    spec: CPSCSpec,
    theta_rad: float,
    z_abs: float,
    nx: int,
    nz: int,
    device,
) -> tuple[float, float]:
    """Evaluate local 3D linearized Einstein metric h_00 and tidal Riemann R_{0z0z}
    at scale-covariant cavity probe coordinate x_probe(z_abs) for homothetic elevation z_abs.
    """
    # Scale-covariant box tracking z_abs so grid resolution stays uniform across Cantor decades
    half_xy = 1.15
    z_bot = -0.35 * max(z_abs / 0.27, 0.12)
    z_top = z_abs + 0.20 * max(z_abs, 0.03)
    xs = np.linspace(-half_xy, half_xy, nx)
    ys = np.linspace(-half_xy, half_xy, nx)
    zs = np.linspace(z_bot, z_top, nz)
    spacings = (float(xs[1] - xs[0]), float(ys[1] - ys[0]), float(zs[1] - zs[0]))
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    pts = np.stack([gx, gy, gz], axis=-1).reshape(-1, 3)

    vox = compute_four_pass_stress_tensor(
        spec,
        theta_rad=theta_rad,
        eval_points=pts,
        field_model="em_pec",
        z_vane_override=+z_abs,
        n_kappa=8,
        n_rad=1,
        n_phi=2,
        n_z=1,
        min_wall_dist=0.003 * max(z_abs / 0.10, 0.25),
        device=device,
    )["t_mutual"].reshape((nx, nx, nz, 4, 4))

    grav = solve_linearized_einstein_static(vox, spacings, device=device)
    # Sample along central cavity annulus mid-radius (x = 0.625, y = 0, z = 0.5 * z_abs)
    ix = int(np.argmin(np.abs(xs - 0.625)))
    iy = nx // 2
    iz = int(np.argmin(np.abs(zs - 0.35 * z_abs)))
    h00_val = float(grav["h_00"][ix, iy, iz])
    r0z0z_val = float(grav["r_0z0z"][ix, iy, iz])
    return h00_val, r0z0z_val


def run_simulation(
    max_steps: int | None = None,
    planned_steps: int = 36,
    results_dir: str = "fractal_casimir_gravity/results",
) -> Dict[str, object]:
    """Execute Phenomenon III logarithmic stroke sweep and Mellin/harmonic comb analysis."""
    device = get_torch_device()
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = str(out_dir / "provenance_metrics.json")

    n_steps = min(max_steps, planned_steps) if max_steps is not None else planned_steps
    n_steps = max(n_steps, 5)

    # Use N=4 homothetic stages across 3 Cantor decades z_abs in [0.012, 0.32] so > 3 log-periods are sampled
    spec_cantor_b3 = CPSCSpec(
        name="CPSC_Homothetic_b3_N4",
        constellation="breathing_4_4",
        staging="homothetic",
        geometry_kind="prefractal",
        generation_n=4,
        scale_b=3.0,
    )
    spec_periodic = CPSCSpec(
        name="Ctrl_Homothetic_Periodic",
        constellation="breathing_4_4",
        staging="coplanar",
        geometry_kind="periodic_grating",
        generation_n=3,
        scale_b=3.0,
    )

    z_sweep = np.geomspace(0.012, 0.32, n_steps)
    ln_z_over_ell = np.log(z_sweep / spec_cantor_b3.ell_star)

    nx_grid = 12
    nz_grid = 10

    log_step(
        "sim3_init_homothetic_sweep",
        {
            "device": str(device),
            "n_steps": n_steps,
            "scale_b": spec_cantor_b3.scale_b,
            "theoretical_omega_1": 2.0 * math.pi / math.log(spec_cantor_b3.scale_b),
        },
        metrics_path=metrics_path,
    )

    h00_open_cantor = np.zeros(n_steps, dtype=np.float64)
    r0z0z_open_cantor = np.zeros(n_steps, dtype=np.float64)
    h00_face_cantor = np.zeros(n_steps, dtype=np.float64)
    h00_open_periodic = np.zeros(n_steps, dtype=np.float64)

    theta_face = math.pi / spec_cantor_b3.m_low
    for idx, z_val in enumerate(z_sweep):
        zf = float(z_val)
        h_o, r_o = _eval_homothetic_metric_point(spec_cantor_b3, 0.0, zf, nx_grid, nz_grid, device)
        h_f, _ = _eval_homothetic_metric_point(spec_cantor_b3, theta_face, zf, nx_grid, nz_grid, device)
        h_p, _ = _eval_homothetic_metric_point(spec_periodic, 0.0, zf, nx_grid, nz_grid, device)
        h00_open_cantor[idx] = h_o
        r0z0z_open_cantor[idx] = r_o
        h00_face_cantor[idx] = h_f
        h00_open_periodic[idx] = h_p

    scaled_open_cantor = (z_sweep**2) * h00_open_cantor
    scaled_face_cantor = (z_sweep**2) * h00_face_cantor
    scaled_open_periodic = (z_sweep**2) * h00_open_periodic
    scaled_tidal_open = (z_sweep**4) * r0z0z_open_cantor

    fit_cantor = fit_log_periodic_metric_comb(ln_z_over_ell, scaled_open_cantor, omega_min=3.5, omega_max=9.0)
    fit_face = fit_log_periodic_metric_comb(ln_z_over_ell, scaled_face_cantor, omega_min=3.5, omega_max=9.0)
    fit_periodic = fit_log_periodic_metric_comb(ln_z_over_ell, scaled_open_periodic, omega_min=3.5, omega_max=9.0)

    omega_hat = float(fit_cantor["omega_hat"])
    b_hat = float(fit_cantor["b_hat"])
    r2_cantor = float(fit_cantor["r_squared"])
    r2_periodic = float(fit_periodic["r_squared"])
    tidal_peak = float(np.max(np.abs(scaled_tidal_open)))
    suppression = float(fit_cantor["amp_1"]) / max(float(fit_face["amp_1"]), 1.0e-30)

    log_metric("fcg_dsi_recovered_omega_one_b_three", omega_hat, step_id="sim3_dsi", metrics_path=metrics_path)
    log_metric("fcg_dsi_recovered_scale_factor_b_hat", b_hat, step_id="sim3_dsi", metrics_path=metrics_path)
    log_metric("fcg_dsi_metric_comb_r_squared_cantor", r2_cantor, step_id="sim3_dsi", metrics_path=metrics_path)
    log_metric("fcg_dsi_metric_comb_r_squared_periodic", r2_periodic, step_id="sim3_dsi", metrics_path=metrics_path)
    log_metric("fcg_dsi_tidal_riemann_peak_open", tidal_peak, step_id="sim3_dsi", metrics_path=metrics_path)
    log_metric("fcg_dsi_open_to_face_harmonic_suppression", suppression, step_id="sim3_dsi", metrics_path=metrics_path)

    payload = {
        "z_sweep": z_sweep.tolist(),
        "ln_z_over_ell": ln_z_over_ell.tolist(),
        "scaled_h00_open_cantor": scaled_open_cantor.tolist(),
        "scaled_h00_face_cantor": scaled_face_cantor.tolist(),
        "scaled_h00_open_periodic": scaled_open_periodic.tolist(),
        "scaled_r0z0z_open_cantor": scaled_tidal_open.tolist(),
        "detrended_cantor": fit_cantor["detrended"].tolist(),  # type: ignore[union-attr]
        "omega_grid": fit_cantor["omega_grid"].tolist(),  # type: ignore[union-attr]
        "r2_spectrum_cantor": fit_cantor["r2_spectrum"].tolist(),  # type: ignore[union-attr]
        "r2_spectrum_periodic": fit_periodic["r2_spectrum"].tolist(),  # type: ignore[union-attr]
        "omega_hat": omega_hat,
        "b_hat": b_hat,
        "r2_cantor": r2_cantor,
        "r2_periodic": r2_periodic,
    }
    out_json = out_dir / "sim3_log_periodic_metric_comb.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[SIM3] Completed {n_steps} steps (omega_1={omega_hat:.3f}, b_hat={b_hat:.3f}) -> {out_json}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Phenomenon III: DSI Log-Periodic Spacetime Metric Comb")
    parser.add_argument("--max-steps", type=int, default=None, help="Limit step count for profiling/testing")
    parser.add_argument("--planned-steps", type=int, default=36, help="Full logarithmic stroke sweep steps")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Output directory for JSON and provenance")
    args = parser.parse_args()
    run_simulation(max_steps=args.max_steps, planned_steps=args.planned_steps, results_dir=args.results_dir)


if __name__ == "__main__":
    main()
