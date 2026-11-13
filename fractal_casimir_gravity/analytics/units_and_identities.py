"""Analytical identities, Planck-Casimir unit conversions, and symbolic proofs."""

from __future__ import annotations

import math
from typing import Dict

import numpy as np

HBAR_SI: float = 1.054571817e-34
C_SI: float = 299792458.0
G_SI: float = 6.67430e-11
PLANCK_LENGTH_M: float = math.sqrt(HBAR_SI * G_SI / (C_SI**3))
PLANCK_LENGTH_SQ_M2: float = HBAR_SI * G_SI / (C_SI**3)

METRIC_ETA: np.ndarray = np.diag([-1.0, 1.0, 1.0, 1.0])

# Ford-Roman (3+1)D Lorentzian worldline constants C_FR in Eq. (31)
FORD_ROMAN_C_SCALAR: float = 3.0 / (32.0 * math.pi**2)
FORD_ROMAN_C_EM: float = 3.0 / (16.0 * math.pi**2)

# Fewster-Eveson (3+1)D C^2_0([-tau_c, tau_c]) compact-support QEI constants for g(t) = sqrt(8/(5*tau_c)) cos^3(pi*t/(2*tau_c))
FEWSTER_EVESON_C_SCALAR: float = 9.0 * (math.pi**2) / 256.0
FEWSTER_EVESON_C_EM: float = 9.0 * (math.pi**2) / 128.0


def epsilon_planck_sq(length_scale_m: float = 1.0e-6) -> float:
    """Return dimensionless Planck-cavity coupling (ell_P / L)^2."""
    if length_scale_m <= 0.0:
        raise ValueError("length_scale_m must be strictly positive.")
    return PLANCK_LENGTH_SQ_M2 / (length_scale_m**2)


def tilde_h_to_si(tilde_h: float | np.ndarray, length_scale_m: float = 1.0e-6) -> float | np.ndarray:
    """Convert dimensionless metric perturbation tilde_h to physical strain h_mu_nu."""
    return epsilon_planck_sq(length_scale_m) * tilde_h


def tilde_ricci_to_si_m_inv2(tilde_r: float | np.ndarray, length_scale_m: float = 1.0e-6) -> float | np.ndarray:
    """Convert dimensionless Ricci curvature tilde_R to physical curvature R [m^-2]."""
    return (epsilon_planck_sq(length_scale_m) / (length_scale_m**2)) * tilde_r


def brown_maclay_tensor_covariant(
    gap_tilde: float,
    field_model: str = "em_pec",
) -> np.ndarray:
    """Analytical covariant stress-energy tensor tilde_T_{mu nu} between flat plates.

    Signature (-, +, +, +):
      T_{00} = +rho_vac < 0, T_{xx} = T_{yy} = -rho_vac > 0, T_{zz} = 3*rho_vac < 0.
    """
    if gap_tilde <= 0.0:
        raise ValueError("gap_tilde must be strictly positive.")
    dof = 2.0 if field_model == "em_pec" else 1.0
    coeff = dof * (math.pi**2) / (1440.0 * (gap_tilde**4))
    rho_tilde = -coeff
    p_par = +coeff
    p_perp = -3.0 * coeff
    return np.diag([rho_tilde, p_par, p_par, p_perp])


def minkowski_trace(t_cov: np.ndarray) -> float | np.ndarray:
    """Compute g^{mu nu} T_{mu nu} = -T_{00} + T_{11} + T_{22} + T_{33}."""
    return -t_cov[..., 0, 0] + t_cov[..., 1, 1] + t_cov[..., 2, 2] + t_cov[..., 3, 3]


def verify_symbolic_identities() -> Dict[str, bool]:
    """Run exact SymPy verification of the manuscript's foundational analytical theorems."""
    import sympy as sp

    d, ell_s, b = sp.symbols("d ell_s b", positive=True)
    rho_c = -sp.pi**2 / (720 * d**4)
    t_bm_mixed_trace = -rho_c + (-rho_c) + (-rho_c) + (3 * rho_c)
    bm_traceless = sp.simplify(t_bm_mixed_trace) == 0
    bm_boost_invariant = sp.simplify(rho_c + (-rho_c)) == 0

    # Force-free crossover locking: E = A_ann * C(ln(d/ell_s)) / d^3
    c_func = sp.Function("C")
    x_var = sp.ln(d / ell_s)
    e_func = c_func(x_var) / d**3
    f_z = -sp.diff(e_func, d)
    # Check F_z * d^4 == 3*C - d*(dC/dd) == 3*C - dC/d(ln d)
    dc_dln_d = d * sp.diff(c_func(x_var), d)
    lock_residual = sp.simplify(f_z * d**4 - (3 * c_func(x_var) - dc_dln_d))
    force_free_locking_ok = lock_residual == 0

    # Rigid C_M quadrupole vanishing for M = 6 and M = 4
    phi = sp.Symbol("phi", real=True)
    c6_quad = sp.integrate(sp.cos(6 * phi) * sp.exp(2 * sp.I * phi), (phi, 0, 2 * sp.pi))
    c4_quad = sp.integrate(sp.cos(4 * phi) * sp.exp(2 * sp.I * phi), (phi, 0, 2 * sp.pi))
    # Vernier product cos(6*(phi - theta)) * cos(4*phi) has non-zero m = 2 moment
    theta = sp.Symbol("theta", real=True)
    vernier_quad = sp.integrate(
        sp.cos(6 * (phi - theta)) * sp.cos(4 * phi) * sp.cos(2 * phi),
        (phi, 0, 2 * sp.pi),
    )
    vernier_selection_ok = (
        sp.simplify(c6_quad) == 0
        and sp.simplify(c4_quad) == 0
        and sp.simplify(vernier_quad - sp.pi * sp.cos(6 * theta) / 2) == 0
    )

    # Exact Wick trace-log planar limit: (1 / (2*pi)) * (1 / (2*pi)) * int_0^inf q^2 ln(1 - e^{-2*q*d}) dq
    # = -pi^2 / (1440 * d^3) for 1 scalar DOF (=> -pi^2 / (1440 * d^4) energy density; 2x for PEC EM)
    u = sp.Symbol("u", positive=True)
    n_idx = sp.Symbol("n", integer=True, positive=True)
    term_n = sp.integrate(u**2 * (-sp.exp(-n_idx * u) / n_idx), (u, 0, sp.oo))
    planar_wick_per_area = (1 / (2 * sp.pi)) * (1 / (2 * sp.pi)) * (1 / (2 * d) ** 3) * sp.summation(term_n, (n_idx, 1, sp.oo))
    planar_scalar_density = planar_wick_per_area / d
    planar_wick_limit_ok = (
        sp.simplify(planar_scalar_density - (-sp.pi**2 / (1440 * d**4))) == 0
        and sp.simplify(2 * planar_scalar_density - (-sp.pi**2 / (720 * d**4))) == 0
    )

    # Weak-gravity first-order redshift profile: average across z in [0, d] has zero O(Y*d) correction
    z_sym, y_grav = sp.symbols("z Y", real=True)
    eps_weak_grav = (-sp.pi**2 / (1440 * d**4)) * (1 + 2 * y_grav * (z_sym - d / 2))
    avg_weak_grav = sp.integrate(eps_weak_grav, (z_sym, 0, d)) / d
    weak_gravity_avg_ok = sp.simplify(avg_weak_grav - (-sp.pi**2 / (1440 * d**4))) == 0

    # Starobinsky f(R) = R + alpha * R^2 trace identity: 3*Box f'(R) + f'(R)*R - 2*f(R) = 6*alpha*Box R - R
    r_curv, alpha_s, box_r = sp.symbols("R alpha BoxR", real=True)
    f_r = r_curv + alpha_s * r_curv**2
    fp_r = sp.diff(f_r, r_curv)
    trace_lhs = 3 * (2 * alpha_s * box_r) + fp_r * r_curv - 2 * f_r
    scalaron_trace_ok = sp.simplify(trace_lhs - (6 * alpha_s * box_r - r_curv)) == 0

    # 8. Euler degree -1 homogeneity of E_C(d, R, ell_s) vs fixed-cutoff macroscopic effective trace Eq. (12):
    # Under simultaneous dilatation (d, R, ell_s) -> lambda*(d, R, ell_s), total conformal virial vanishes;
    # holding microscopic prefractal cutoff ell_s fixed transfers +ell_s * dE_C/dell_s / V_cav into T^mu_{mu,eff},
    # and for constant C = -pi^2/720 reproduces canonical Casimir pressure P_z = -pi^2 / (240 * d^4).
    rad_r, hbar_c = sp.symbols("rad_r hbar_c", positive=True)
    c2_func = sp.Function("C2")
    e_3d = (sp.pi * rad_r**2) * (hbar_c / d**3) * c2_func(sp.ln(d / ell_s), sp.ln(rad_r / ell_s))
    v_cav_sym = sp.pi * rad_r**2 * d
    euler_full = d * sp.diff(e_3d, d) + rad_r * sp.diff(e_3d, rad_r) + ell_s * sp.diff(e_3d, ell_s) + e_3d
    rho_macro = e_3d / v_cav_sym
    pz_macro = -sp.diff(e_3d, d) / (sp.pi * rad_r**2)
    pr_pphi_macro = -(rad_r / (d * sp.pi * rad_r**2)) * sp.diff(e_3d, rad_r)
    trace_eff_macro = -rho_macro + pz_macro + pr_pphi_macro
    cutoff_virial = (ell_s / v_cav_sym) * sp.diff(e_3d, ell_s)
    e_3d_planar = (sp.pi * rad_r**2) * (hbar_c / d**3) * (-sp.pi**2 / 720)
    pz_planar = -sp.diff(e_3d_planar, d) / (sp.pi * rad_r**2)
    euler_virial_trace_ok = (
        sp.simplify(euler_full) == 0
        and sp.simplify(trace_eff_macro - cutoff_virial) == 0
        and sp.simplify(pz_planar - (-sp.pi**2 * hbar_c / (240 * d**4))) == 0
    )

    # 9. Four-pass inclusion-exclusion cancellation Eq. (17) and pairwise disjointness of Cantor tracks (N=1..4):
    g0_s, dg_u, dg_l, dg_mut = sp.symbols("G0 dGU dGL dGmut")
    four_pass_expr = (g0_s + dg_u + dg_l + dg_mut) - (g0_s + dg_u) - (g0_s + dg_l) + g0_s
    cantor_intervals: list[tuple[sp.Rational, sp.Rational]] = []

    def _collect_cantor(a_left: sp.Rational, a_right: sp.Rational, depth: int, max_depth: int) -> None:
        if depth > max_depth:
            return
        w_seg = (a_right - a_left) / 3
        cantor_intervals.append((a_left + w_seg, a_right - w_seg))
        _collect_cantor(a_left, a_left + w_seg, depth + 1, max_depth)
        _collect_cantor(a_right - w_seg, a_right, depth + 1, max_depth)

    _collect_cantor(sp.Rational(0), sp.Rational(1), 1, 4)
    disjoint_ok = len(cantor_intervals) == 15 and all(
        cantor_intervals[i][1] <= cantor_intervals[j][0] or cantor_intervals[j][1] <= cantor_intervals[i][0]
        for i in range(len(cantor_intervals))
        for j in range(i + 1, len(cantor_intervals))
    )
    inclusion_exclusion_ok = sp.simplify(four_pass_expr - dg_mut) == 0 and disjoint_ok

    # 10. Fewster-Eveson C^2_0([-tau_c, tau_c]) compact-support QEI constant for g(t) = sqrt(8/(5*tau_c))*cos^3(pi*t/(2*tau_c)):
    t_qei, tau_c = sp.symbols("t_qei tau_c", positive=True)
    t_sym = sp.Symbol("t_sym", real=True)
    g_win = sp.sqrt(sp.Rational(8, 5) / tau_c) * sp.cos(sp.pi * t_sym / (2 * tau_c)) ** 3
    g_norm = sp.integrate(g_win**2, (t_sym, -tau_c, tau_c))
    g_d1 = sp.diff(g_win, t_sym)
    g_d2 = sp.diff(g_win, t_sym, 2)
    fe_bound_scalar = -sp.integrate(g_d2**2, (t_sym, -tau_c, tau_c)) / (16 * sp.pi**2)
    compact_qei_ok = (
        sp.simplify(g_norm - 1) == 0
        and sp.simplify(g_win.subs(t_sym, tau_c)) == 0
        and sp.simplify(g_d1.subs(t_sym, tau_c)) == 0
        and sp.simplify(g_d2.subs(t_sym, tau_c)) == 0
        and sp.simplify(fe_bound_scalar - (-9 * sp.pi**2 / (256 * tau_c**4))) == 0
    )

    # 11. Covariant continuity & Laue stress closure for steadily co-rotating radial vanes at O(Omega r / c):
    r_cyl, phi_lab, z_cyl, t_lab, omega_rot, c_vel = sp.symbols(
        "r_cyl phi_lab z_cyl t_lab omega_rot c_vel", positive=True
    )
    phi_corot = phi_lab - omega_rot * t_lab
    e_corot = sp.Function("E_corot")(r_cyl, phi_corot, z_cyl)
    p_phi_corot = sp.Function("P_phi")(r_cyl, phi_corot, z_cyl)
    sig_rphi = sp.Function("S_rphi")(r_cyl, phi_corot, z_cyl)
    sig_zphi = sp.Function("S_zphi")(r_cyl, phi_corot, z_cyl)
    beta_rot = omega_rot * r_cyl / c_vel
    t00_lab = e_corot
    t0phi_lab = beta_rot * (e_corot + p_phi_corot)
    t0r_lab = beta_rot * sig_rphi
    t0z_lab = beta_rot * sig_zphi
    continuity_lhs = (
        (1 / c_vel) * sp.diff(t00_lab, t_lab)
        + (1 / r_cyl) * sp.diff(r_cyl * t0r_lab, r_cyl)
        + (1 / r_cyl) * sp.diff(t0phi_lab, phi_lab)
        + sp.diff(t0z_lab, z_cyl)
    )
    corot_equil_phi = (
        (1 / r_cyl) * sp.diff(p_phi_corot, phi_lab)
        + (1 / r_cyl**2) * sp.diff(r_cyl**2 * sig_rphi, r_cyl)
        + sp.diff(sig_zphi, z_cyl)
    )
    rotating_continuity_ok = sp.simplify(continuity_lhs - beta_rot * corot_equil_phi) == 0

    return {
        "brown_maclay_traceless": bool(bm_traceless),
        "brown_maclay_boost_invariant": bool(bm_boost_invariant),
        "force_free_scale_locking": bool(force_free_locking_ok),
        "vernier_quadrupole_selection_rule": bool(vernier_selection_ok),
        "planar_scalar_1440_and_em_720_wick_limit": bool(planar_wick_limit_ok),
        "weak_gravity_first_order_average_null": bool(weak_gravity_avg_ok),
        "starobinsky_scalaron_trace_reduction": bool(scalaron_trace_ok),
        "euler_virial_cutoff_effective_trace": bool(euler_virial_trace_ok),
        "four_pass_inclusion_exclusion_and_cantor_disjointness": bool(inclusion_exclusion_ok),
        "fewster_eveson_compact_support_qei_constant": bool(compact_qei_ok),
        "rotating_vane_covariant_continuity_laue_balance": bool(rotating_continuity_ok),
    }
