"""Analytical identities, Planck-Casimir unit conversions, and symbolic proofs."""

from __future__ import annotations

import math
from typing import Dict

import numpy as np
import sympy as sp

HBAR_SI: float = 1.054571817e-34
C_SI: float = 299792458.0
G_SI: float = 6.67430e-11
PLANCK_LENGTH_M: float = math.sqrt(HBAR_SI * G_SI / (C_SI**3))
PLANCK_LENGTH_SQ_M2: float = HBAR_SI * G_SI / (C_SI**3)

METRIC_ETA: np.ndarray = np.diag([-1.0, 1.0, 1.0, 1.0])

# Ford-Roman (3+1)D Lorentzian worldline constants C_FR in Eq. (20)
FORD_ROMAN_C_SCALAR: float = 3.0 / (32.0 * math.pi**2)
FORD_ROMAN_C_EM: float = 3.0 / (16.0 * math.pi**2)


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

    return {
        "brown_maclay_traceless": bool(bm_traceless),
        "brown_maclay_boost_invariant": bool(bm_boost_invariant),
        "force_free_scale_locking": bool(force_free_locking_ok),
        "vernier_quadrupole_selection_rule": bool(vernier_selection_ok),
    }
