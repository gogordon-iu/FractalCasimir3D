"""Simulation VI: Prefractal Generation Convergence (N=1..4), Discretization Error Analysis,
Interior Local Trace Null Verification, and Massive f(R) Scalaron Dispersion.

Directly addresses numerical verification, truncation error quantification, local-trace vs.
macroscopic-effective-trace separation, and Starobinsky f(R) = R + alpha R^2 stability (alpha > 0):
  1. Prefractal generation convergence N = 1, 2, 3, 4 in CPSC_Breathing44 (b = 3):
     evaluates E_C(N), F_z(N), force-free crossover theta_0(N), R_eff(theta_0(N)), and
     Cauchy step increments |E_C(N) - E_C(N-1)| / |E_C(N)| demonstrating N -> infty plateauing.
  2. Wick quadrature convergence N_kappa in {6, 10, 14, 20, 28} and BEM surface-panel
     subdivision convergence (n_rad, n_phi, n_z) in {(1,1,1), (2,2,2), (3,3,2), (4,4,2), (5,5,3)}
     in the resolved separation regime, alongside interior vacuum Maxwell trace residual
     |eta^{mu nu} T_{mu nu}^{EM}| / |T_{00}^{EM}| ~ 10^-16.
  3. 3D Hockney-Eastwood FFT Poisson voxel-grid convergence across (16x16x12, 22x22x16,
     28x28x20, 36x36x26, 48x48x32) for multi-slot chiral (4,4) Cantor gravitomagnetic vorticity.
  4. Starobinsky f(R) = R + alpha R^2 (alpha > 0, m_phi = L / sqrt(6 alpha)) scalaron
     dispersion and short-range Yukawa suppression for both the fundamental 4*Omega breathing
     harmonic and the full multi-harmonic sector-edge trace comb.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import brentq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fractal_casimir_gravity.analytics.units_and_identities import minkowski_trace  # noqa: E402
from fractal_casimir_gravity.solvers.bem_scattering import (  # noqa: E402
    compute_casimir_energy_bem,
    compute_cavity_thermodynamics,
    compute_four_pass_stress_tensor,
    gauss_legendre_kappa_grid,
    get_torch_device,
)
from fractal_casimir_gravity.solvers.cpsc_geometry import (  # noqa: E402
    CPSCSpec,
    build_cpsc_mesh,
    build_radial_tracks,
)
from fractal_casimir_gravity.solvers.linearized_gravity import (  # noqa: E402
    compute_scalaron_monopole_waveform,
    solve_gem_lense_thirring,
)
from fractal_casimir_gravity.utils.metrics_logger import (  # noqa: E402
    log_metric,
    log_step,
    save_simulation_json,
)


def _eval_axial_force_only(
    spec: CPSCSpec,
    theta_rad: float,
    n_kappa: int,
    device,
    rel_step: float = 0.015,
) -> float:
    """Fast 2-point centered logarithmic derivative for axial force F_z = -dE/dd_sep."""
    z_face_ref = spec.z_vane_0 - spec.d_0
    d_sep = spec.z_vane_0 - z_face_ref
    d_plus = d_sep * math.exp(+rel_step)
    d_minus = d_sep * math.exp(-rel_step)
    e_zp = compute_casimir_energy_bem(
        spec,
        theta_rad=theta_rad,
        field_model="em_pec",
        z_vane_override=z_face_ref + d_plus,
        n_kappa=n_kappa,
        n_rad=2,
        n_phi=2,
        n_z=1,
        use_bloch=True,
        device=device,
    )
    e_zm = compute_casimir_energy_bem(
        spec,
        theta_rad=theta_rad,
        field_model="em_pec",
        z_vane_override=z_face_ref + d_minus,
        n_kappa=n_kappa,
        n_rad=2,
        n_phi=2,
        n_z=1,
        use_bloch=True,
        device=device,
    )
    d_ln_z_e = (e_zp - e_zm) / (2.0 * rel_step)
    return float(-d_ln_z_e / d_sep)


def _find_theta_zero_for_generation(spec: CPSCSpec, n_kappa: int, device) -> Tuple[float, float, float]:
    """Bracket and solve the primary open-to-facing crossover F_z(theta_0) = 0 for generation N."""
    # Fine 1.5-deg bracket scan across [15 deg, 30 deg] matching Sim 2's angular resolution
    scan_thetas = np.radians(np.linspace(15.0, 30.0, 11))
    scan_forces = [
        _eval_axial_force_only(spec, float(th), n_kappa=n_kappa, device=device)
        for th in scan_thetas
    ]
    forces_arr = np.asarray(scan_forces, dtype=np.float64)
    sign_idx = np.where(np.sign(forces_arr[:-1]) != np.sign(forces_arr[1:]))[0]
    if len(sign_idx) > 0:
        i0 = int(sign_idx[0])
        th_a, th_b = float(scan_thetas[i0]), float(scan_thetas[i0 + 1])

        def _f_root(th_val: float) -> float:
            return _eval_axial_force_only(spec, th_val, n_kappa=n_kappa, device=device)

        th_zero = float(brentq(_f_root, th_a, th_b, xtol=1.0e-5, maxiter=20))
    else:
        i_min = int(np.argmin(np.abs(forces_arr)))
        th_zero = float(scan_thetas[i_min])

    thermo_zero = compute_cavity_thermodynamics(
        spec,
        th_zero,
        field_model="em_pec",
        n_kappa=n_kappa,
        n_rad=2,
        n_phi=2,
        n_z=1,
        compute_torque=False,
        device=device,
    )
    return math.degrees(th_zero), float(thermo_zero.ricci_eff_tilde), float(thermo_zero.force_z_tilde)


def _build_smooth_cantor_chiral_enthalpy_grid(
    spec_chiral: CPSCSpec,
    nx: int,
    ny: int,
    nz: int,
    l_xy: float = 1.25,
) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float, float]]:
    """Construct a spatially smooth, multi-slot chiral (4,4) Cantor azimuthal enthalpy source
    on a 3D grid (nx, ny, nz, 4, 4) to isolate pure Hockney-Eastwood 3D FFT Poisson + 4th-order
    curl discretization error without moving binary conductor-mask jumps.
    """
    xs = np.linspace(-l_xy, l_xy, nx)
    ys = np.linspace(-l_xy, l_xy, ny)
    zs = np.linspace(-0.14, 0.04, nz)
    dx = float(xs[1] - xs[0])
    dy = float(ys[1] - ys[0])
    dz = float(zs[1] - zs[0])
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    coords = np.stack([gx, gy, gz], axis=-1)

    rr = np.sqrt(gx * gx + gy * gy)
    phi = np.arctan2(gy, gx)
    z_env = np.exp(-(((gz + 0.06) / 0.035) ** 2))

    tracks = build_radial_tracks(spec_chiral)
    w_phi = np.zeros((nx, ny, nz), dtype=np.float64)
    for trk in tracks:
        r_c = 0.5 * (trk.r_slot_in + trk.r_slot_out)
        sigma_r = max(0.45 * trk.slot_width, 0.035)
        sign_gen = (-1.0) ** trk.generation
        skew = spec_chiral.chiral_skew_rad * sign_gen
        w_phi += (
            sign_gen
            * np.exp(-(((rr - r_c) / sigma_r) ** 2))
            * z_env
            * np.cos(spec_chiral.m_low * (phi - skew))
        )

    # Map rest-frame azimuthal enthalpy w_phi = T_00 + T_{phi phi} onto Cartesian components
    t_grid = np.zeros((nx, ny, nz, 4, 4), dtype=np.float64)
    t_grid[..., 0, 0] = -w_phi
    sp = np.sin(phi)
    cp = np.cos(phi)
    t_grid[..., 1, 1] = 2.0 * w_phi * (sp * sp)
    t_grid[..., 1, 2] = -2.0 * w_phi * (sp * cp)
    t_grid[..., 2, 1] = -2.0 * w_phi * (sp * cp)
    t_grid[..., 2, 2] = 2.0 * w_phi * (cp * cp)
    return t_grid, coords, (dx, dy, dz)


def run_simulation(
    max_steps: int | None = None,
    results_dir: str = "fractal_casimir_gravity/results",
) -> Dict[str, object]:
    """Execute prefractal N-convergence, discretization error, local-trace, and scalaron mass sweeps."""
    device = get_torch_device()
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = str(out_dir / "provenance_metrics.json")

    fast_mode = max_steps is not None and max_steps <= 6
    n_kappa_base = 8 if fast_mode else 14

    log_step(
        "sim6_init_convergence_suite",
        {"device": str(device), "fast_mode": fast_mode, "n_kappa_base": n_kappa_base},
        metrics_path=metrics_path,
    )

    # -------------------------------------------------------------------------
    # 1. Prefractal Generation Convergence Sweep: N = 1, 2, 3, 4 (b = 3)
    # -------------------------------------------------------------------------
    generations = [1, 2, 3] if fast_mode else [1, 2, 3, 4]
    gen_panel_counts: List[int] = []
    gen_e_open: List[float] = []
    gen_e_face: List[float] = []
    gen_c_open: List[float] = []
    gen_c_face: List[float] = []
    gen_cprime_open: List[float] = []
    gen_cprime_face: List[float] = []
    gen_trace_eff_face: List[float] = []
    gen_fz_open: List[float] = []
    gen_fz_face: List[float] = []
    gen_theta_zero_deg: List[float] = []
    gen_ricci_zero: List[float] = []

    for gen_n in generations:
        spec_g = CPSCSpec(
            name=f"CPSC_Breathing44_N{gen_n}",
            constellation="breathing_4_4",
            staging="coplanar",
            geometry_kind="prefractal",
            generation_n=gen_n,
        )
        mesh_g = build_cpsc_mesh(spec_g, theta_rad=0.0, n_rad=2, n_phi=2, n_z=1)
        gen_panel_counts.append(int(len(mesh_g.areas)))

        th_open = compute_cavity_thermodynamics(
            spec_g,
            0.0,
            field_model="em_pec",
            n_kappa=n_kappa_base,
            n_rad=2,
            n_phi=2,
            n_z=1,
            compute_torque=False,
            device=device,
        )
        th_face = compute_cavity_thermodynamics(
            spec_g,
            math.pi / 4.0,
            field_model="em_pec",
            n_kappa=n_kappa_base,
            n_rad=2,
            n_phi=2,
            n_z=1,
            compute_torque=False,
            device=device,
        )
        th0_deg, ricci0, _ = _find_theta_zero_for_generation(spec_g, n_kappa=n_kappa_base, device=device)

        gen_e_open.append(float(th_open.energy_tilde))
        gen_e_face.append(float(th_face.energy_tilde))
        gen_c_open.append(float(th_open.coeff_c))
        gen_c_face.append(float(th_face.coeff_c))
        gen_cprime_open.append(float(th_open.d_ln_z_c))
        gen_cprime_face.append(float(th_face.d_ln_z_c))
        gen_trace_eff_face.append(float(th_face.trace_eff_tilde))
        gen_fz_open.append(float(th_open.force_z_tilde))
        gen_fz_face.append(float(th_face.force_z_tilde))
        gen_theta_zero_deg.append(float(th0_deg))
        gen_ricci_zero.append(float(ricci0))
        print(
            f"[SIM6] Gen N={gen_n}: C_face={th_face.coeff_c:.5e}, C'_face={th_face.d_ln_z_c:.5e}, "
            f"th0={th0_deg:.3f} deg",
            flush=True,
        )

    gen_cauchy_rel_e_face = [
        abs(gen_e_face[i] - gen_e_face[i - 1]) / max(abs(gen_e_face[i]), 1.0e-30)
        for i in range(1, len(generations))
    ]
    gen_cauchy_rel_e_open = [
        abs(gen_e_open[i] - gen_e_open[i - 1]) / max(abs(gen_e_open[i]), 1.0e-30)
        for i in range(1, len(generations))
    ]
    gen_cauchy_rel_cprime_face = [
        abs(gen_cprime_face[i] - gen_cprime_face[i - 1]) / max(abs(gen_cprime_face[i]), 1.0e-30)
        for i in range(1, len(generations))
    ]
    gen_cauchy_rel_trace_eff_face = [
        abs(gen_trace_eff_face[i] - gen_trace_eff_face[i - 1]) / max(abs(gen_trace_eff_face[i]), 1.0e-30)
        for i in range(1, len(generations))
    ]
    rel_delta_3_to_4 = float(gen_cauchy_rel_e_face[-1])
    rel_cprime_delta_3_to_4 = float(gen_cauchy_rel_cprime_face[-1])
    rel_trace_eff_delta_3_to_4 = float(gen_cauchy_rel_trace_eff_face[-1])
    theta_zero_n4 = float(gen_theta_zero_deg[-1])
    theta_zero_shift_3_4 = float(abs(gen_theta_zero_deg[-1] - gen_theta_zero_deg[-2]))

    # -------------------------------------------------------------------------
    # 1b. Homothetic C_N(ln|z|) Emergence Sweep Across Generations N = 1..4
    # -------------------------------------------------------------------------
    n_hom_pts = 9 if fast_mode else 21
    z_hom_sweep = np.geomspace(0.0085, 0.30, n_hom_pts)
    z_stage_1_ref = 0.27
    ln_z_over_z1 = np.log(z_hom_sweep / z_stage_1_ref)
    homothetic_c_loc_by_gen: Dict[str, List[float]] = {}
    analytic_recursion_c_by_gen: Dict[str, List[float]] = {}

    for gen_n in generations:
        spec_hom = CPSCSpec(
            name=f"CPSC_Homothetic_b3_N{gen_n}",
            constellation="breathing_4_4",
            staging="homothetic",
            geometry_kind="prefractal",
            generation_n=gen_n,
            scale_b=3.0,
        )
        c_loc_vals: List[float] = []
        for z_val in z_hom_sweep:
            zf = float(z_val)
            scale = zf / spec_hom.z_stage_1
            x_c = spec_hom.r_in + 0.375 * scale
            z_c = -1.044 * zf
            z_vane = -0.956 * zf
            pt = np.array([[x_c, 0.0, z_c]], dtype=np.float64)
            vox_h = compute_four_pass_stress_tensor(
                spec_hom,
                theta_rad=0.0,
                eval_points=pt,
                field_model="scalar_conformal",
                z_vane_override=z_vane,
                n_kappa=6,
                kappa_min=0.5 / scale,
                kappa_max=80.0 / scale,
                n_rad=1,
                n_phi=3,
                n_z=1,
                min_wall_dist=0.006 * scale,
                fundamental_sector_only=True,
                phi_grading_beta=2.6,
                device=device,
            )["t_mutual"]
            c_loc_vals.append(float((zf**4) * abs(vox_h[0, 0, 0])))
        homothetic_c_loc_by_gen[str(gen_n)] = c_loc_vals
        print(f"[SIM6] Homothetic C_N(ln|z|) sweep completed for N={gen_n}", flush=True)

        # Exact self-similar recursion sum C_N^{rec}(X_0) = sum_{m=1}^N Phi(X_0 + (m-1)*ln b)
        # with localized single-stage Euclidean Yukawa window Phi(xi) = A_0 * sech^2(xi / sigma_0)
        c_rec = np.zeros_like(ln_z_over_z1)
        for m_idx in range(1, gen_n + 1):
            xi_m = ln_z_over_z1 + (m_idx - 1) * math.log(3.0)
            c_rec += 1.0 / (np.cosh(xi_m / 0.42) ** 2)
        analytic_recursion_c_by_gen[str(gen_n)] = c_rec.tolist()

    # -------------------------------------------------------------------------
    # 2. Wick Quadrature (N_kappa) & BEM Panel Refinement + Local Trace Residual
    # -------------------------------------------------------------------------
    spec_n3 = CPSCSpec(
        name="CPSC_Breathing44_N3",
        constellation="breathing_4_4",
        staging="coplanar",
        geometry_kind="prefractal",
        generation_n=3,
    )
    kappa_orders = [6, 10, 14, 20] if fast_mode else [6, 10, 14, 20, 28]
    kappa_energies: List[float] = []
    for nk in kappa_orders:
        ek = compute_casimir_energy_bem(
            spec_n3,
            theta_rad=math.pi / 4.0,
            field_model="em_pec",
            n_kappa=nk,
            n_rad=2,
            n_phi=2,
            n_z=1,
            use_bloch=True,
            device=device,
        )
        kappa_energies.append(float(ek))

    e_kappa_ref = kappa_energies[-1]
    kappa_rel_errors = [
        abs(val - e_kappa_ref) / max(abs(e_kappa_ref), 1.0e-30)
        for val in kappa_energies
    ]
    idx_k14 = kappa_orders.index(14) if 14 in kappa_orders else 0
    kappa_rel_err_14 = float(kappa_rel_errors[idx_k14])

    # Asymptotic BEM surface-panel convergence in the resolved separation regime (d_sep = 0.16 > h_panel)
    panel_configs = (
        [(1, 1, 1), (2, 2, 2), (3, 3, 2)]
        if fast_mode
        else [(1, 1, 1), (2, 2, 2), (3, 3, 2), (4, 4, 2), (5, 5, 3)]
    )
    panel_dofs: List[int] = []
    panel_energies: List[float] = []
    for nr, nph, nz_p in panel_configs:
        m_sub = build_cpsc_mesh(spec_n3, theta_rad=0.0, n_rad=nr, n_phi=nph, n_z=nz_p, fundamental_sector_only=False)
        panel_dofs.append(int(len(m_sub.areas)))
        e_sub = compute_casimir_energy_bem(
            spec_n3,
            theta_rad=math.pi / 4.0,
            field_model="scalar_conformal",
            z_vane_override=0.04,
            n_kappa=n_kappa_base,
            n_rad=nr,
            n_phi=nph,
            n_z=nz_p,
            use_bloch=True,
            device=device,
        )
        panel_energies.append(float(e_sub))

    e_panel_ref = panel_energies[-1]
    panel_rel_errors = [
        abs(val - e_panel_ref) / max(abs(e_panel_ref), 1.0e-30)
        for val in panel_energies
    ]
    bem_panel_rel_unc = float(panel_rel_errors[-2])

    # Pointwise interior local trace vs. macroscopic coarse-grained cavity trace across all 3 QFT models
    probe_pts = np.array(
        [
            [0.50, 0.00, -0.11],
            [0.625, 0.00, -0.05],
            [0.75, 0.12, -0.11],
            [0.42, 0.08, -0.06],
        ],
        dtype=np.float64,
    )
    field_models_check = ["scalar_conformal", "em_pec", "scalar_minimal"]
    interior_local_trace_ratios: Dict[str, float] = {}
    macroscopic_eff_trace_ratios: Dict[str, float] = {}
    v_cav_n3 = math.pi * (spec_n3.r_out**2 - spec_n3.r_in**2) * spec_n3.d_0
    for fm in field_models_check:
        vox_fm = compute_four_pass_stress_tensor(
            spec_n3,
            theta_rad=0.0,
            eval_points=probe_pts,
            field_model=fm,  # type: ignore[arg-type]
            n_kappa=n_kappa_base,
            n_rad=2,
            n_phi=2,
            n_z=1,
            min_wall_dist=0.005,
            fundamental_sector_only=True,
            device=device,
        )
        t_int_fm = vox_fm["t_total_ren"]
        tr_loc_fm = minkowski_trace(t_int_fm)
        t00_sc_fm = max(float(np.max(np.abs(t_int_fm[:, 0, 0]))), 1.0e-30)
        interior_local_trace_ratios[fm] = float(np.max(np.abs(tr_loc_fm)) / t00_sc_fm)

        th_fm = compute_cavity_thermodynamics(
            spec_n3,
            0.0,
            field_model=fm,  # type: ignore[arg-type]
            n_kappa=n_kappa_base,
            n_rad=2,
            n_phi=2,
            n_z=1,
            compute_torque=False,
            device=device,
        )
        rho_bar_fm = max(abs(th_fm.energy_tilde) / v_cav_n3, 1.0e-30)
        macroscopic_eff_trace_ratios[fm] = float(abs(th_fm.trace_eff_tilde) / rho_bar_fm)

    interior_em_trace_residual = float(interior_local_trace_ratios["em_pec"])
    interior_scalar_min_trace_ratio = float(interior_local_trace_ratios["scalar_minimal"])

    # Non-fractal planar parallel-plate scalar limit (-pi^2 / (1440 * d^4)) & 3D BEM flat annulus check
    d_planar = 0.05
    ks_pl, ws_pl = gauss_legendre_kappa_grid(28, 1.0e-3, 5.0e2)
    qp_pl, wp_pl = gauss_legendre_kappa_grid(44, 1.0e-3, 6.0e2)
    wick_planar_per_area = 0.0
    for k_v, w_kv in zip(ks_pl, ws_pl):
        q_rad = np.sqrt(k_v * k_v + qp_pl * qp_pl)
        integrand_pl = (qp_pl / (2.0 * math.pi)) * np.log1p(-np.exp(-2.0 * q_rad * d_planar))
        wick_planar_per_area += (w_kv / (2.0 * math.pi)) * float(np.sum(wp_pl * integrand_pl))
    wick_planar_density = wick_planar_per_area / d_planar
    exact_planar_scalar_density = -(math.pi**2) / (1440.0 * (d_planar**4))
    planar_scalar_limit_rel_err = abs(wick_planar_density - exact_planar_scalar_density) / abs(exact_planar_scalar_density)

    spec_flat_full = CPSCSpec(
        name="Ctrl_FlatAnnulus_FullWidth",
        constellation="breathing_4_4",
        staging="coplanar",
        geometry_kind="flat_annulus",
        generation_n=1,
        fill_chi=1.0,
        d_0=0.12,
        z_vane_0=-0.04,
    )
    a_ann_full = math.pi * (spec_flat_full.r_out**2 - spec_flat_full.r_in**2)
    e_flat_bem_scalar = compute_casimir_energy_bem(
        spec_flat_full,
        theta_rad=0.0,
        field_model="scalar_conformal",
        z_vane_override=-0.04,
        n_kappa=n_kappa_base,
        n_rad=3 if fast_mode else 5,
        n_phi=3 if fast_mode else 5,
        n_z=1,
        use_bloch=True,
        device=device,
    )
    e_flat_exact_scalar = -a_ann_full * (math.pi**2) / (1440.0 * (0.12**3))
    bem_flat_annulus_to_planar_ratio = float(e_flat_bem_scalar / e_flat_exact_scalar)

    # Interior flat-space stress-energy conservation check: d_j T^{ji}_{vac} = 0 across all 3 QFT models
    h_fd = 1.0e-4
    x0_div, y0_div, z0_div = 0.50, 0.02, -0.11
    div_stencil = np.array(
        [
            [x0_div, y0_div, z0_div],
            [x0_div + h_fd, y0_div, z0_div],
            [x0_div - h_fd, y0_div, z0_div],
            [x0_div + 2.0 * h_fd, y0_div, z0_div],
            [x0_div - 2.0 * h_fd, y0_div, z0_div],
            [x0_div, y0_div + h_fd, z0_div],
            [x0_div, y0_div - h_fd, z0_div],
            [x0_div, y0_div + 2.0 * h_fd, z0_div],
            [x0_div, y0_div - 2.0 * h_fd, z0_div],
            [x0_div, y0_div, z0_div + h_fd],
            [x0_div, y0_div, z0_div - h_fd],
            [x0_div, y0_div, z0_div + 2.0 * h_fd],
            [x0_div, y0_div, z0_div - 2.0 * h_fd],
        ],
        dtype=np.float64,
    )
    interior_div_ratios: Dict[str, float] = {}
    for fm in field_models_check:
        t_st = compute_four_pass_stress_tensor(
            spec_n3,
            theta_rad=0.0,
            eval_points=div_stencil,
            field_model=fm,  # type: ignore[arg-type]
            n_kappa=n_kappa_base,
            n_rad=2,
            n_phi=2,
            n_z=1,
            min_wall_dist=0.003,
            fundamental_sector_only=True,
            device=device,
        )["t_total_ren"]
        dx_t4 = (-t_st[3, 1:, 1:] + 8.0 * t_st[1, 1:, 1:] - 8.0 * t_st[2, 1:, 1:] + t_st[4, 1:, 1:]) / (12.0 * h_fd)
        dy_t4 = (-t_st[7, 1:, 1:] + 8.0 * t_st[5, 1:, 1:] - 8.0 * t_st[6, 1:, 1:] + t_st[8, 1:, 1:]) / (12.0 * h_fd)
        dz_t4 = (-t_st[11, 1:, 1:] + 8.0 * t_st[9, 1:, 1:] - 8.0 * t_st[10, 1:, 1:] + t_st[12, 1:, 1:]) / (12.0 * h_fd)
        div_v = dx_t4[0, :] + dy_t4[1, :] + dz_t4[2, :]
        grad_norm = float(np.linalg.norm(dx_t4) + np.linalg.norm(dy_t4) + np.linalg.norm(dz_t4))
        interior_div_ratios[fm] = float(np.linalg.norm(div_v) / max(grad_norm, 1.0e-30))
    interior_div_rel_residual = float(max(interior_div_ratios.values()))

    # -------------------------------------------------------------------------
    # 3. 3D Spectral FFT Poisson Voxel Grid Refinement (Chiral GEM Vorticity)
    # -------------------------------------------------------------------------
    spec_chiral = CPSCSpec(
        name="CPSC_Chiral44_N3",
        constellation="chiral_4_4",
        staging="coplanar",
        geometry_kind="prefractal",
        generation_n=3,
        chiral_skew_rad=0.14,
    )
    voxel_grids = (
        [(16, 16, 12), (22, 22, 16), (28, 28, 20)]
        if fast_mode
        else [(16, 16, 12), (22, 22, 16), (28, 28, 20), (36, 36, 26), (48, 48, 32)]
    )
    voxel_counts: List[int] = []
    voxel_rms_lt: List[float] = []
    for nx_g, ny_g, nz_g in voxel_grids:
        t_chiral_g, coords_g, spacings_g = _build_smooth_cantor_chiral_enthalpy_grid(
            spec_chiral, nx=nx_g, ny=ny_g, nz=nz_g,
        )
        gem_g = solve_gem_lense_thirring(t_chiral_g, coords_g, spacings_g, omega_tilde=1.0, device=device)
        voxel_counts.append(int(nx_g * ny_g * nz_g))
        voxel_rms_lt.append(float(np.sqrt(np.mean(gem_g["omega_lt_z"] ** 2))))

    rms_ref = voxel_rms_lt[-1]
    voxel_rel_errors = [
        abs(val - rms_ref) / max(abs(rms_ref), 1.0e-30)
        for val in voxel_rms_lt
    ]
    poisson_voxel_rel_unc = float(voxel_rel_errors[-2])

    # -------------------------------------------------------------------------
    # 4. Starobinsky f(R) = R + alpha R^2 (alpha > 0) Scalaron Mass Sweep
    # -------------------------------------------------------------------------
    omega_tilde = 0.10
    r_obs_tilde = 10.0
    period_44 = 2.0 * math.pi / 4.0  # fundamental azimuthal period pi/2 -> omega_B = 4 * Omega = 0.4
    v_cav = math.pi * (spec_n3.r_out**2 - spec_n3.r_in**2) * spec_n3.d_0

    sim2_path = out_dir / "sim2_force_free_curvature_tolman.json"
    if sim2_path.exists() and not fast_mode:
        sim2_data = json.loads(sim2_path.read_text(encoding="utf-8"))
        ricci_half = np.asarray(sim2_data["ricci_eff_tilde"], dtype=np.float64)
        # Reconstruct full [0, pi/2) period by mirror symmetry around theta_face = pi/4
        ricci_full = np.concatenate([ricci_half, ricci_half[-2:0:-1]])
        trace_series = (-ricci_full / (8.0 * math.pi)) * v_cav
        t_cycle = np.linspace(0.0, period_44, len(trace_series), endpoint=False) / omega_tilde
    else:
        n_t = 16 if fast_mode else 32
        th_cycle = np.linspace(0.0, period_44, n_t, endpoint=False)
        t_cycle = th_cycle / omega_tilde
        trace_series = np.zeros(n_t, dtype=np.float64)
        for idx_t, th_val in enumerate(th_cycle):
            th_c = compute_cavity_thermodynamics(
                spec_n3,
                float(th_val),
                field_model="em_pec",
                n_kappa=n_kappa_base,
                n_rad=2,
                n_phi=2,
                n_z=1,
                compute_torque=False,
                device=device,
            )
            trace_series[idx_t] = th_c.trace_eff_tilde * v_cav

    # Isolate fundamental n = 1 (4 * Omega) breathing harmonic alongside full multi-harmonic comb
    osc_trace = trace_series - float(np.mean(trace_series))
    hat_full = np.fft.rfft(osc_trace)
    hat_fund = np.zeros_like(hat_full)
    if len(hat_fund) > 1:
        hat_fund[1] = hat_full[1]
    trace_fund_series = np.fft.irfft(hat_fund, n=len(osc_trace))

    m_phi_grid = np.linspace(0.0, 5.6, 29)  # m_phi / (4 * Omega) in [0, 14]
    scalaron_amps_total: List[float] = []
    scalaron_amps_fund: List[float] = []
    for m_phi in m_phi_grid:
        wf_tot = compute_scalaron_monopole_waveform(
            osc_trace, t_cycle, r_obs_tilde=r_obs_tilde, m_phi_tilde=float(m_phi),
        )
        wf_fnd = compute_scalaron_monopole_waveform(
            trace_fund_series, t_cycle, r_obs_tilde=r_obs_tilde, m_phi_tilde=float(m_phi),
        )
        scalaron_amps_total.append(float(np.max(np.abs(wf_tot))))
        scalaron_amps_fund.append(float(np.max(np.abs(wf_fnd))))

    amp_fund_massless = max(scalaron_amps_fund[0], 1.0e-30)
    idx_heavy_2wb = int(np.argmin(np.abs(m_phi_grid - 0.80)))  # m_phi = 2 * (4 * Omega)
    yukawa_heavy_ratio = float(scalaron_amps_fund[idx_heavy_2wb] / amp_fund_massless)

    # -------------------------------------------------------------------------
    # Log all 11 convergence, error-analysis, trace-locality, and stability metrics
    # -------------------------------------------------------------------------
    log_metric("fcg_conv_gen_rel_delta_n_three_to_four", rel_delta_3_to_4, step_id="sim6_gen_convergence", metrics_path=metrics_path)
    log_metric("fcg_conv_cprime_rel_delta_n_three_to_four", rel_cprime_delta_3_to_4, step_id="sim6_gen_convergence", metrics_path=metrics_path)
    log_metric("fcg_conv_trace_eff_rel_delta_n_three_to_four", rel_trace_eff_delta_3_to_4, step_id="sim6_gen_convergence", metrics_path=metrics_path)
    log_metric("fcg_conv_theta_zero_deg_gen_four", theta_zero_n4, step_id="sim6_gen_convergence", metrics_path=metrics_path)
    log_metric("fcg_conv_theta_zero_shift_deg_three_to_four", theta_zero_shift_3_4, step_id="sim6_gen_convergence", metrics_path=metrics_path)
    log_metric("fcg_conv_kappa_quad_rel_err_n_fourteen", kappa_rel_err_14, step_id="sim6_bem_discretization", metrics_path=metrics_path)
    log_metric("fcg_conv_bem_panel_rel_uncertainty", bem_panel_rel_unc, step_id="sim6_bem_discretization", metrics_path=metrics_path)
    log_metric("fcg_conv_interior_em_trace_null_residual", interior_em_trace_residual, step_id="sim6_local_trace_check", metrics_path=metrics_path)
    log_metric("fcg_conv_interior_scalar_min_trace_ratio", interior_scalar_min_trace_ratio, step_id="sim6_local_trace_check", metrics_path=metrics_path)
    log_metric("fcg_conv_planar_scalar_limit_rel_err", planar_scalar_limit_rel_err, step_id="sim6_consistency_limits", metrics_path=metrics_path)
    log_metric("fcg_conv_interior_div_rel_residual", interior_div_rel_residual, step_id="sim6_consistency_limits", metrics_path=metrics_path)
    log_metric("fcg_conv_poisson_voxel_rel_uncertainty", poisson_voxel_rel_unc, step_id="sim6_voxel_convergence", metrics_path=metrics_path)
    log_metric("fcg_conv_scalaron_yukawa_suppression_heavy", yukawa_heavy_ratio, step_id="sim6_scalaron_dispersion", metrics_path=metrics_path)

    payload: Dict[str, object] = {
        "generations": generations,
        "gen_panel_counts": gen_panel_counts,
        "gen_e_open": gen_e_open,
        "gen_e_face": gen_e_face,
        "gen_c_open": gen_c_open,
        "gen_c_face": gen_c_face,
        "gen_cprime_open": gen_cprime_open,
        "gen_cprime_face": gen_cprime_face,
        "gen_trace_eff_face": gen_trace_eff_face,
        "gen_fz_open": gen_fz_open,
        "gen_fz_face": gen_fz_face,
        "gen_theta_zero_deg": gen_theta_zero_deg,
        "gen_ricci_zero": gen_ricci_zero,
        "gen_cauchy_rel_e_face": gen_cauchy_rel_e_face,
        "gen_cauchy_rel_e_open": gen_cauchy_rel_e_open,
        "gen_cauchy_rel_cprime_face": gen_cauchy_rel_cprime_face,
        "gen_cauchy_rel_trace_eff_face": gen_cauchy_rel_trace_eff_face,
        "homothetic_ln_z_over_z1": ln_z_over_z1.tolist(),
        "homothetic_c_loc_by_gen": homothetic_c_loc_by_gen,
        "analytic_recursion_c_by_gen": analytic_recursion_c_by_gen,
        "kappa_orders": kappa_orders,
        "kappa_energies": kappa_energies,
        "kappa_rel_errors": kappa_rel_errors,
        "panel_configs": [list(cfg) for cfg in panel_configs],
        "panel_dofs": panel_dofs,
        "panel_energies": panel_energies,
        "panel_rel_errors": panel_rel_errors,
        "field_models_check": field_models_check,
        "interior_local_trace_ratios": interior_local_trace_ratios,
        "macroscopic_eff_trace_ratios": macroscopic_eff_trace_ratios,
        "interior_em_trace_residual": interior_em_trace_residual,
        "interior_scalar_min_trace_ratio": interior_scalar_min_trace_ratio,
        "planar_scalar_limit_rel_err": planar_scalar_limit_rel_err,
        "bem_flat_annulus_to_planar_ratio": bem_flat_annulus_to_planar_ratio,
        "interior_div_ratios": interior_div_ratios,
        "interior_div_rel_residual": interior_div_rel_residual,
        "voxel_grids": [list(vg) for vg in voxel_grids],
        "voxel_counts": voxel_counts,
        "voxel_rms_lt": voxel_rms_lt,
        "voxel_rel_errors": voxel_rel_errors,
        "omega_b_fundamental": 4.0 * omega_tilde,
        "m_phi_grid": m_phi_grid.tolist(),
        "scalaron_amps": scalaron_amps_total,
        "scalaron_amps_fundamental": scalaron_amps_fund,
        "yukawa_heavy_ratio": yukawa_heavy_ratio,
    }
    out_json = out_dir / "sim6_convergence_and_error_bounds.json"
    save_simulation_json(out_json, "Sim6_Convergence_ErrorBounds", "CPSC_Convergence_N1_to_N4", payload)
    print(
        f"[SIM6] Completed convergence & error suite "
        f"(dE_34={rel_delta_3_to_4:.4f}, dCp_34={rel_cprime_delta_3_to_4:.4f}, "
        f"dTr_34={rel_trace_eff_delta_3_to_4:.4f}, th0_N4={theta_zero_n4:.3f} deg, "
        f"bem_unc={bem_panel_rel_unc:.4f}, vox_unc={poisson_voxel_rel_unc:.4f}) -> {out_json}"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Simulation VI: Prefractal & Discretization Convergence")
    parser.add_argument("--max-steps", type=int, default=None, help="Cap steps (<=6 triggers fast smoke mode)")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Output directory")
    args = parser.parse_args()
    run_simulation(max_steps=args.max_steps, results_dir=args.results_dir)


if __name__ == "__main__":
    main()
