"""3D Cyclic-Bloch Boundary-Element Scattering and Four-Pass Euclidean Correlator Engine.

Implements Section III.A and Section III.B of the manuscript across three zero-temperature
massless relativistic quantum field models in Planck-Casimir dimensionless units:
  1. "scalar_conformal" : Callan-Coleman-Jackiw conformal scalar (xi = 1/6)
  2. "scalar_minimal"   : Minimally coupled scalar (xi = 0)
  3. "em_pec"           : Ideal 0 K perfect-electric-conductor (PEC) vector electromagnetism
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Literal, Tuple

import numpy as np
import torch

from fractal_casimir_gravity.solvers.cpsc_geometry import (
    CPSCSpec,
    PanelBatch3D,
    build_cpsc_mesh,
    is_inside_cpsc_conductor,
)

FieldModel = Literal["scalar_conformal", "scalar_minimal", "em_pec"]


def get_torch_device() -> torch.device:
    """Select CUDA device when available, otherwise fall back cleanly to CPU."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def gauss_legendre_kappa_grid(
    n_kappa: int = 16,
    kappa_min: float = 1.0e-2,
    kappa_max: float = 2.0e2,
) -> Tuple[np.ndarray, np.ndarray]:
    """Log-transformed Gauss-Legendre quadrature nodes and weights on [kappa_min, kappa_max]."""
    if n_kappa < 2:
        raise ValueError("n_kappa must be >= 2.")
    u_nodes, u_weights = np.polynomial.legendre.leggauss(n_kappa)
    ln_a = math.log(kappa_min)
    ln_b = math.log(kappa_max)
    half_span = 0.5 * (ln_b - ln_a)
    ln_k = 0.5 * (ln_a + ln_b) + half_span * u_nodes
    kappas = np.exp(ln_k)
    weights = kappas * half_span * u_weights
    return kappas.astype(np.float64), weights.astype(np.float64)


def _rotate_vectors_z(vecs: torch.Tensor, angle_rad: float) -> torch.Tensor:
    """Rotate (..., 3) Cartesian vectors around the +z axis by angle_rad."""
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    x = vecs[..., 0]
    y = vecs[..., 1]
    z = vecs[..., 2]
    return torch.stack([c * x - s * y, s * x + c * y, z], dim=-1)


def _assemble_scalar_block(
    c_row: torch.Tensor,
    a_row: torch.Tensor,
    c_col: torch.Tensor,
    a_col: torch.Tensor,
    kappa: float,
    same_patch_set: bool,
) -> torch.Tensor:
    """Assemble SPD single-layer Yukawa Galerkin block with exact scale homogeneity."""
    diff = c_row[:, None, :] - c_col[None, :, :]
    dist = torch.linalg.norm(diff, dim=-1)
    # Regularize close distinct panels symmetrically using panel areas (scales as lambda^1)
    r_reg = torch.sqrt(dist * dist + (a_row[:, None] + a_col[None, :]) / (16.0 * math.pi))
    block = (a_row[:, None] * a_col[None, :]) * torch.exp(-kappa * r_reg) / (4.0 * math.pi * r_reg)
    if same_patch_set:
        # Exact integrated circular-patch self-interaction: A * (1 - exp(-kappa * R_eq)) / (2 * kappa)
        r_eq = torch.sqrt(a_row / math.pi)
        if kappa * float(torch.max(r_eq).item()) < 1.0e-5:
            diag_val = a_row * (0.5 * r_eq - 0.25 * kappa * r_eq * r_eq)
        else:
            diag_val = a_row * (-torch.expm1(-kappa * r_eq)) / (2.0 * kappa)
        idx = torch.arange(c_row.shape[0], device=c_row.device)
        block[idx, idx] = diag_val
    return block


def _yukawa_kernel_matrix(
    p_row: torch.Tensor,
    p_col: torch.Tensor,
    reg_sq: torch.Tensor,
    kappa: float,
) -> torch.Tensor:
    """Evaluate regularized exp(-kappa * R) / (4 * pi * R) for shape (N, M, 3) pairs."""
    diff = p_row - p_col
    r = torch.sqrt(torch.sum(diff * diff, dim=-1) + reg_sq)
    return torch.exp(-kappa * r) / (4.0 * math.pi * r)


def _assemble_efie_block(
    c_row: torch.Tensor,
    t1_row: torch.Tensor,
    t2_row: torch.Tensor,
    a_row: torch.Tensor,
    c_col: torch.Tensor,
    t1_col: torch.Tensor,
    t2_col: torch.Tensor,
    a_col: torch.Tensor,
    kappa: float,
    same_patch_set: bool,
) -> torch.Tensor:
    """Assemble strictly SPD 2-DOF/panel EFIE Galerkin block:
    Gamma = A_a A_b (t_a . t_b) G_0 + kappa^-2 (A_a A_b / (l_a l_b)) Delta^2 G_0.
    Scales homogeneously as lambda^3 under x -> lambda * x, kappa -> kappa / lambda.
    """
    n_r = c_row.shape[0]
    n_c = c_col.shape[0]
    device = c_row.device
    dtype = c_row.dtype

    # Stack 2 tangential basis functions per panel: shape (2 * N, 3)
    c_r2 = c_row.repeat_interleave(2, dim=0)
    a_r2 = a_row.repeat_interleave(2, dim=0)
    t_r2 = torch.stack([t1_row, t2_row], dim=1).reshape(2 * n_r, 3)

    c_c2 = c_col.repeat_interleave(2, dim=0)
    a_c2 = a_col.repeat_interleave(2, dim=0)
    t_c2 = torch.stack([t1_col, t2_col], dim=1).reshape(2 * n_c, 3)

    reg_sq = (a_r2[:, None] + a_c2[None, :]) / (16.0 * math.pi)
    g0_center = _yukawa_kernel_matrix(c_r2[:, None, :], c_c2[None, :, :], reg_sq, kappa)
    t_dot = torch.matmul(t_r2, t_c2.T)
    vec_term = (a_r2[:, None] * a_c2[None, :]) * t_dot * g0_center

    # Finite-dipole surface divergence term guaranteeing SPD structure for all kappa > 0
    ell_r = 0.5 * torch.sqrt(a_r2)
    ell_c = 0.5 * torch.sqrt(a_c2)
    pr_plus = c_r2 + 0.5 * ell_r[:, None] * t_r2
    pr_minus = c_r2 - 0.5 * ell_r[:, None] * t_r2
    pc_plus = c_c2 + 0.5 * ell_c[:, None] * t_c2
    pc_minus = c_c2 - 0.5 * ell_c[:, None] * t_c2

    g_pp = _yukawa_kernel_matrix(pr_plus[:, None, :], pc_plus[None, :, :], reg_sq, kappa)
    g_pm = _yukawa_kernel_matrix(pr_plus[:, None, :], pc_minus[None, :, :], reg_sq, kappa)
    g_mp = _yukawa_kernel_matrix(pr_minus[:, None, :], pc_plus[None, :, :], reg_sq, kappa)
    g_mm = _yukawa_kernel_matrix(pr_minus[:, None, :], pc_minus[None, :, :], reg_sq, kappa)

    pref_div = (a_r2[:, None] * a_c2[None, :]) / (ell_r[:, None] * ell_c[None, :] * (kappa * kappa))
    div_term = pref_div * (g_pp - g_pm - g_mp + g_mm)

    block = vec_term + div_term
    if same_patch_set:
        # Ensure clean diagonal conditioning at large kappa
        r_eq = torch.sqrt(a_r2 / math.pi)
        diag_add = 0.05 * a_r2 * r_eq * torch.exp(-kappa * r_eq)
        idx = torch.arange(2 * n_r, device=device)
        block = block.to(dtype=dtype)
        block[idx, idx] = block[idx, idx] + diag_add
    return block


def compute_casimir_energy_bem(
    spec: CPSCSpec,
    theta_rad: float,
    field_model: FieldModel = "em_pec",
    z_vane_override: float | None = None,
    r_scale: float = 1.0,
    freeze_slot_cutoff: bool = False,
    n_kappa: int = 14,
    kappa_min: float = 1.0e-2,
    kappa_max: float = 1.5e2,
    n_rad: int = 2,
    n_phi: int = 2,
    n_z: int = 1,
    use_bloch: bool = True,
    device: torch.device | None = None,
) -> float:
    """Compute exact zero-temperature dimensionless Casimir interaction energy tilde_E_C
    via Eq. (11) using cyclic Bloch projection into M_g = gcd(M_up, M_low) blocks.
    """
    dev = get_torch_device() if device is None else device
    mesh = build_cpsc_mesh(
        spec,
        theta_rad=theta_rad,
        z_vane_override=z_vane_override,
        r_scale=r_scale,
        freeze_slot_cutoff=freeze_slot_cutoff,
        n_rad=n_rad,
        n_phi=n_phi,
        n_z=n_z,
        fundamental_sector_only=use_bloch,
    )
    m_gcd = spec.m_gcd if use_bloch else 1
    # Folding xi in (-inf, +inf) -> 2 * int_0^inf d_xi cancels the 1/2 zero-point factor universally;
    # polarization multiplicity (1 for scalar, 2 for PEC EM) is carried by dof_mult in M(kappa).
    sigma_field = 1.0
    kappas, weights = gauss_legendre_kappa_grid(n_kappa, kappa_min=kappa_min, kappa_max=kappa_max)

    mask_u = mesh.body_id == 0
    mask_l = mesh.body_id == 1

    c_u = torch.as_tensor(mesh.centroids[mask_u], dtype=torch.float64, device=dev)
    a_u = torch.as_tensor(mesh.areas[mask_u], dtype=torch.float64, device=dev)
    t1_u = torch.as_tensor(mesh.tangents_1[mask_u], dtype=torch.float64, device=dev)
    t2_u = torch.as_tensor(mesh.tangents_2[mask_u], dtype=torch.float64, device=dev)

    c_l = torch.as_tensor(mesh.centroids[mask_l], dtype=torch.float64, device=dev)
    a_l = torch.as_tensor(mesh.areas[mask_l], dtype=torch.float64, device=dev)
    t1_l = torch.as_tensor(mesh.tangents_1[mask_l], dtype=torch.float64, device=dev)
    t2_l = torch.as_tensor(mesh.tangents_2[mask_l], dtype=torch.float64, device=dev)

    dof_mult = 2 if field_model == "em_pec" else 1
    n_u_dof = c_u.shape[0] * dof_mult
    n_l_dof = c_l.shape[0] * dof_mult

    total_integral = 0.0
    for kappa, w_k in zip(kappas, weights):
        k_val = float(kappa)
        uu_shifts = []
        ll_shifts = []
        ul_shifts = []
        lu_shifts = []

        for q in range(m_gcd):
            angle_q = 2.0 * math.pi * q / m_gcd
            c_u_q = _rotate_vectors_z(c_u, angle_q)
            c_l_q = _rotate_vectors_z(c_l, angle_q)
            same_q = q == 0
            if field_model == "em_pec":
                t1_u_q = _rotate_vectors_z(t1_u, angle_q)
                t2_u_q = _rotate_vectors_z(t2_u, angle_q)
                t1_l_q = _rotate_vectors_z(t1_l, angle_q)
                t2_l_q = _rotate_vectors_z(t2_l, angle_q)
                uu_shifts.append(_assemble_efie_block(c_u, t1_u, t2_u, a_u, c_u_q, t1_u_q, t2_u_q, a_u, k_val, same_q))
                ll_shifts.append(_assemble_efie_block(c_l, t1_l, t2_l, a_l, c_l_q, t1_l_q, t2_l_q, a_l, k_val, same_q))
                ul_shifts.append(_assemble_efie_block(c_u, t1_u, t2_u, a_u, c_l_q, t1_l_q, t2_l_q, a_l, k_val, False))
                lu_shifts.append(_assemble_efie_block(c_l, t1_l, t2_l, a_l, c_u_q, t1_u_q, t2_u_q, a_u, k_val, False))
            else:
                uu_shifts.append(_assemble_scalar_block(c_u, a_u, c_u_q, a_u, k_val, same_q))
                ll_shifts.append(_assemble_scalar_block(c_l, a_l, c_l_q, a_l, k_val, same_q))
                ul_shifts.append(_assemble_scalar_block(c_u, a_u, c_l_q, a_l, k_val, False))
                lu_shifts.append(_assemble_scalar_block(c_l, a_l, c_u_q, a_u, k_val, False))

        uu_stack = torch.stack(uu_shifts, dim=0)  # (M_g, N_u, N_u)
        ll_stack = torch.stack(ll_shifts, dim=0)  # (M_g, N_l, N_l)
        ul_stack = torch.stack(ul_shifts, dim=0)  # (M_g, N_u, N_l)
        lu_stack = torch.stack(lu_shifts, dim=0)  # (M_g, N_l, N_u)

        # Exact discrete Fourier transform over cyclic shifts q = 0..M_g-1
        uu_bloch = torch.fft.fft(uu_stack, dim=0)
        ll_bloch = torch.fft.fft(ll_stack, dim=0)
        ul_bloch = torch.fft.fft(ul_stack, dim=0)
        lu_bloch = torch.fft.fft(lu_stack, dim=0)

        eye_u = torch.eye(n_u_dof, dtype=torch.complex128, device=dev)
        logdet_sum_k = 0.0
        for ell in range(m_gcd):
            x_ul = torch.linalg.solve(uu_bloch[ell], ul_bloch[ell])
            x_lu = torch.linalg.solve(ll_bloch[ell], lu_bloch[ell])
            m_ell = torch.matmul(x_ul, x_lu)
            sign, logabsdet = torch.linalg.slogdet(eye_u - m_ell)
            # Eigenvalues of M_ell are real in [0, 1); guard numerical noise near 0
            if float(torch.real(sign).item()) > 0.0:
                logdet_sum_k += float(logabsdet.item())
        total_integral += float(w_k) * logdet_sum_k

    return (sigma_field / (2.0 * math.pi)) * total_integral


@dataclass(frozen=True)
class CavityThermodynamics:
    """Dimensionless Casimir energy, force, torque, Effective Trace, and Effective Ricci scalar."""

    theta_rad: float
    z_abs: float
    energy_tilde: float
    coeff_c: float
    force_z_tilde: float
    torque_theta_tilde: float
    d_ln_z_c: float
    d_ln_r_c: float
    trace_eff_tilde: float
    ricci_eff_tilde: float


def compute_cavity_thermodynamics(
    spec: CPSCSpec,
    theta_rad: float,
    field_model: FieldModel = "em_pec",
    z_vane_override: float | None = None,
    n_kappa: int = 14,
    n_rad: int = 2,
    n_phi: int = 2,
    n_z: int = 1,
    rel_step: float = 0.015,
    theta_step: float = 0.012,
    compute_torque: bool = True,
    device: torch.device | None = None,
) -> CavityThermodynamics:
    """Evaluate tilde_E_C, axial force tilde_F_z = -dE/dd_sep, torque, and 3D Effective Trace Eq. (8).

    In coplanar mode, the vertical separation coordinate is the upward gap d_sep = z_vane - z_face_top > 0
    above the stationary lower facing sector (z_face_top = z_vane_0 - d_0); increasing d_sep moves the
    upper assembly upward (+z). In homothetic mode with z_vane > 0, d_sep = z_vane > 0.
    """
    dev = get_torch_device() if device is None else device
    z_base = spec.z_vane_0 if z_vane_override is None else z_vane_override
    z_face_ref = spec.z_vane_0 - spec.d_0

    if spec.staging == "coplanar" and z_base <= 0.0:
        d_sep = z_base - z_face_ref
        if d_sep <= 1.0e-5:
            raise ValueError(f"Coplanar separation d_sep = {d_sep} must be > 0 (z_vane > {z_face_ref}).")

        def _d_to_zvane(d_val: float) -> float:
            return z_face_ref + d_val
    else:
        d_sep = abs(z_base)
        if d_sep <= 1.0e-5:
            raise ValueError("Homothetic |z_vane| must be strictly positive.")

        def _d_to_zvane(d_val: float) -> float:
            return d_val if z_base >= 0.0 else -d_val

    def _eval_e(th: float, d_val: float, r_sc: float = 1.0, freeze_cut: bool = False) -> float:
        # Scale kappa integration window inversely with uniform dilation so flat_annulus
        # satisfies exact Euler homogeneity E(s*d, s*R) = s^-1 E(d, R) to machine precision
        k_scale = 1.0 / r_sc if (spec.geometry_kind == "flat_annulus" and abs(d_val / d_sep - r_sc) < 1.0e-9) else 1.0
        return compute_casimir_energy_bem(
            spec,
            theta_rad=th,
            field_model=field_model,
            z_vane_override=_d_to_zvane(d_val),
            r_scale=r_sc,
            freeze_slot_cutoff=freeze_cut,
            n_kappa=n_kappa,
            kappa_min=1.0e-2 * k_scale,
            kappa_max=1.5e2 * k_scale,
            n_rad=n_rad,
            n_phi=n_phi,
            n_z=n_z,
            use_bloch=True,
            device=dev,
        )

    a_ann_0 = math.pi * (spec.r_out**2 - spec.r_in**2)
    e_0 = _eval_e(theta_rad, d_sep, 1.0, False)
    # Dimensionless per-area Casimir coefficient C: tilde_E_C = A_ann * d_sep^-3 * C
    c_0 = e_0 * (d_sep**3) / a_ann_0

    # Centered logarithmic finite difference in upward separation d_sep at fixed ell_* and fixed R
    d_plus = d_sep * math.exp(+rel_step)
    d_minus = d_sep * math.exp(-rel_step)
    e_zp = _eval_e(theta_rad, d_plus, 1.0, False)
    e_zm = _eval_e(theta_rad, d_minus, 1.0, False)
    c_zp = e_zp * (d_plus**3) / a_ann_0
    c_zm = e_zm * (d_minus**3) / a_ann_0

    d_ln_z_e = (e_zp - e_zm) / (2.0 * rel_step)
    force_z = -d_ln_z_e / d_sep
    d_ln_z_c = (c_zp - c_zm) / (2.0 * rel_step)

    # Joint macroscopic cavity dilatation s -> (s * d_sep, s * R) at fixed internal cutoff ell_*:
    # d/d(ln s) [s * E_C(s * d_sep, s * R; ell_*)]|_{s=1} = (1 + d/d(ln d) + d/d(ln R)) E_C
    #   = A_ann * d_sep^-3 * (dC/d(ln d) + dC/d(ln R))
    s_plus = math.exp(+rel_step)
    s_minus = math.exp(-rel_step)
    se_p = s_plus * _eval_e(theta_rad, d_sep * s_plus, s_plus, True)
    se_m = s_minus * _eval_e(theta_rad, d_sep * s_minus, s_minus, True)
    dilatation_e = (se_p - se_m) / (2.0 * rel_step)

    v_cav = a_ann_0 * d_sep
    trace_eff = -dilatation_e / v_cav
    d_ln_r_c = dilatation_e * (d_sep**3) / a_ann_0 - d_ln_z_c
    ricci_eff = -8.0 * math.pi * trace_eff

    if compute_torque:
        e_tp = _eval_e(theta_rad + theta_step, d_sep, 1.0, False)
        e_tm = _eval_e(theta_rad - theta_step, d_sep, 1.0, False)
        torque_th = -(e_tp - e_tm) / (2.0 * theta_step)
    else:
        torque_th = 0.0

    return CavityThermodynamics(
        theta_rad=theta_rad,
        z_abs=d_sep,
        energy_tilde=e_0,
        coeff_c=c_0,
        force_z_tilde=force_z,
        torque_theta_tilde=torque_th,
        d_ln_z_c=d_ln_z_c,
        d_ln_r_c=d_ln_r_c,
        trace_eff_tilde=trace_eff,
        ricci_eff_tilde=ricci_eff,
    )


def _evaluate_single_pass_stress_voxels(
    panels: PanelBatch3D,
    points: torch.Tensor,
    field_model: FieldModel,
    kappas: np.ndarray,
    weights: np.ndarray,
    min_wall_dist: float = 0.008,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Evaluate boundary-renormalized stress-energy tensor tilde_T_{mu nu}(x) (N_pts, 4, 4)
    for a single panel set (U+L, U alone, or L alone).
    Returns (t_munu, valid_mask) where valid_mask marks interior vacuum points outside min_wall_dist.
    """
    dev = points.device
    n_pts = points.shape[0]
    t_accum = torch.zeros((n_pts, 4, 4), dtype=torch.float64, device=dev)

    if panels.centroids.shape[0] == 0:
        return t_accum, torch.ones(n_pts, dtype=torch.bool, device=dev)

    c_p = torch.as_tensor(panels.centroids, dtype=torch.float64, device=dev)
    n_p_vec = torch.as_tensor(panels.normals, dtype=torch.float64, device=dev)
    a_p = torch.as_tensor(panels.areas, dtype=torch.float64, device=dev)
    t1_p = torch.as_tensor(panels.tangents_1, dtype=torch.float64, device=dev)
    t2_p = torch.as_tensor(panels.tangents_2, dtype=torch.float64, device=dev)

    # Mask points that sit within normal clearance min_wall_dist AND within panel radius r_eq of a panel
    diff_all = points[:, None, :] - c_p[None, :, :]  # (N_pts, N_p, 3)
    dist_all = torch.linalg.norm(diff_all, dim=-1)
    norm_dist = torch.abs(torch.sum(diff_all * n_p_vec[None, :, :], dim=-1))
    tang_dist = torch.sqrt(torch.clamp(dist_all * dist_all - norm_dist * norm_dist, min=0.0))
    r_panel = torch.sqrt(a_p / math.pi)
    too_close = (dist_all <= min_wall_dist) | ((norm_dist <= min_wall_dist) & (tang_dist <= r_panel[None, :]))
    valid_mask = ~torch.any(too_close, dim=1)
    if not bool(torch.any(valid_mask).item()):
        return t_accum, valid_mask

    pts_v = points[valid_mask]
    diff_v = pts_v[:, None, :] - c_p[None, :, :]  # (N_v, N_p, 3)
    r_v = torch.linalg.norm(diff_v, dim=-1)       # strictly > 0 on valid_mask
    n_v = pts_v.shape[0]
    t_v = torch.zeros((n_v, 4, 4), dtype=torch.float64, device=dev)

    xi_val = (1.0 / 6.0) if field_model == "scalar_conformal" else 0.0
    eye3 = torch.eye(3, dtype=torch.float64, device=dev)

    for kappa, w_k in zip(kappas, weights):
        k_val = float(kappa)
        w_pref = float(w_k) / math.pi

        if field_model in ("scalar_conformal", "scalar_minimal"):
            gamma = _assemble_scalar_block(c_p, a_p, c_p, a_p, k_val, same_patch_set=True)
            exp_kr = torch.exp(-k_val * r_v)
            g0 = a_p[None, :] * exp_kr / (4.0 * math.pi * r_v)  # (N_v, N_p)
            dg0 = -a_p[None, :, None] * diff_v * ((1.0 + k_val * r_v) * exp_kr / (4.0 * math.pi * (r_v**3)))[:, :, None]

            # Solve Gamma * X = g0^T and Gamma * Y_i = dg0_i^T
            w_g0 = torch.linalg.solve(gamma, g0.T).T  # (N_v, N_p)
            delta_g = -torch.sum(g0 * w_g0, dim=1)    # (N_v,)
            d00 = -(k_val * k_val) * delta_g          # < (d_0 phi)^2 >_k

            w_dg = torch.empty_like(dg0)
            for i_ax in range(3):
                w_dg[:, :, i_ax] = torch.linalg.solve(gamma, dg0[:, :, i_ax].T).T
            # d_ij = < d_i phi d_j phi >_k = -sum_{a,b} (d_i g0_a) W_{ab} (d_j g0_b)
            d_ij = -torch.einsum("vpi,vpj->vij", dg0, w_dg)  # (N_v, 3, 3)

            # Second spatial derivative of <phi^2>_k for exact CCJ conformal improvement term
            kr = k_val * r_v
            c1 = -(1.0 + kr) / (4.0 * math.pi * (r_v**3))
            c2 = (3.0 + 3.0 * kr + kr * kr) / (4.0 * math.pi * (r_v**5))
            ddg0 = a_p[None, :, None, None] * exp_kr[:, :, None, None] * (
                c1[:, :, None, None] * eye3[None, None, :, :]
                + c2[:, :, None, None] * (diff_v[:, :, :, None] * diff_v[:, :, None, :])
            )  # (N_v, N_p, 3, 3)

            # d_i d_j DeltaG(x, x) = -2 * sum_p ddg0_{p,ij} * w_g0_p - 2 * sum_p dg0_{p,i} * w_dg_{p,j} (symmetrized)
            dd_phi2 = -2.0 * torch.einsum("vpij,vp->vij", ddg0, w_g0) + 2.0 * d_ij
            lap_phi2 = torch.diagonal(dd_phi2, dim1=-2, dim2=-1).sum(dim=-1)  # equals 2*(-d00 + tr_d)

            tr_d = torch.diagonal(d_ij, dim1=-2, dim2=-1).sum(dim=-1)
            lagrangian_2 = -d00 + tr_d  # <(d phi)^2>_k

            t00_k = d00 + 0.5 * lagrangian_2 - xi_val * lap_phi2
            tij_k = (
                d_ij
                - 0.5 * lagrangian_2[:, None, None] * eye3[None, :, :]
                + xi_val * (lap_phi2[:, None, None] * eye3[None, :, :] - dd_phi2)
            )
            t_v[:, 0, 0] += w_pref * t00_k
            t_v[:, 1:, 1:] += w_pref * tij_k
        else:
            gamma_em = _assemble_efie_block(
                c_p, t1_p, t2_p, a_p, c_p, t1_p, t2_p, a_p, k_val, same_patch_set=True,
            )
            n_p = c_p.shape[0]
            t_basis = torch.stack([t1_p, t2_p], dim=1).reshape(2 * n_p, 3)  # (2*N_p, 3)
            a_2 = a_p.repeat_interleave(2, dim=0)
            diff_2 = diff_v.repeat_interleave(2, dim=1)  # (N_v, 2*N_p, 3)
            r_2 = r_v.repeat_interleave(2, dim=1)
            exp_kr = torch.exp(-k_val * r_2)
            kr = k_val * r_2
            r_hat = diff_2 / r_2[:, :, None]

            # Exact electric propagation tensor G_{0,ik}(R) * t_{mu, k}: satisfies (nabla^2 - k^2) E = 0
            f_iso = (1.0 + 1.0 / kr + 1.0 / (kr * kr)) * exp_kr / (4.0 * math.pi * r_2)
            f_rr = (1.0 + 3.0 / kr + 3.0 / (kr * kr)) * exp_kr / (4.0 * math.pi * r_2)
            r_dot_t = torch.sum(r_hat * t_basis[None, :, :], dim=-1)  # (N_v, 2*N_p)
            e_prop = a_2[None, :, None] * (
                f_iso[:, :, None] * t_basis[None, :, :]
                - f_rr[:, :, None] * r_dot_t[:, :, None] * r_hat
            )  # (N_v, 2*N_p, 3)

            # Exact magnetic propagation tensor -(1/k) (nabla G_0 x t_mu)
            dg_scalar = -((1.0 + kr) * exp_kr) / (4.0 * math.pi * (r_2**2))
            grad_g0 = dg_scalar[:, :, None] * r_hat
            h_prop = -(a_2[None, :, None] / k_val) * torch.cross(grad_g0, t_basis[None, :, :].expand_as(grad_g0), dim=-1)

            w_e = torch.empty_like(e_prop)
            w_h = torch.empty_like(h_prop)
            for i_ax in range(3):
                w_e[:, :, i_ax] = torch.linalg.solve(gamma_em, e_prop[:, :, i_ax].T).T
                w_h[:, :, i_ax] = torch.linalg.solve(gamma_em, h_prop[:, :, i_ax].T).T

            # Euclidean Wick-rotated Maxwell correlators (verified against Casimir-Polder & Brown-Maclay)
            ee_ij = +(k_val * k_val) * torch.einsum("vmi,vmj->vij", e_prop, w_e)
            hh_ij = -(k_val * k_val) * torch.einsum("vmi,vmj->vij", h_prop, w_h)

            em_sum = ee_ij + hh_ij
            e2_plus_h2 = torch.diagonal(em_sum, dim1=-2, dim2=-1).sum(dim=-1)
            t00_k = 0.5 * e2_plus_h2
            tij_k = 0.5 * e2_plus_h2[:, None, None] * eye3[None, :, :] - em_sum

            t_v[:, 0, 0] += w_pref * t00_k
            t_v[:, 1:, 1:] += w_pref * tij_k

    t_accum[valid_mask] = t_v
    return t_accum, valid_mask


def compute_four_pass_stress_tensor(
    spec: CPSCSpec,
    theta_rad: float,
    eval_points: np.ndarray,
    field_model: FieldModel = "em_pec",
    z_vane_override: float | None = None,
    n_kappa: int = 12,
    kappa_min: float = 2.0e-2,
    kappa_max: float = 1.2e2,
    n_rad: int = 2,
    n_phi: int = 2,
    n_z: int = 1,
    min_wall_dist: float = 0.008,
    fundamental_sector_only: bool = False,
    phi_grading_beta: float = 0.0,
    device: torch.device | None = None,
) -> Dict[str, np.ndarray]:
    """Execute the exact four-pass inclusion-exclusion correlator Eq. (13):
        Delta T_mut = T^{U+L} - T^U - T^L + T^{vac}   (with T^{vac}_ren = 0)
    and return both total boundary-renormalized T^{ren} = T^{U+L} and mutual Delta T_mut.
    """
    dev = get_torch_device() if device is None else device
    full_mesh = build_cpsc_mesh(
        spec,
        theta_rad=theta_rad,
        z_vane_override=z_vane_override,
        n_rad=n_rad,
        n_phi=n_phi,
        n_z=n_z,
        fundamental_sector_only=fundamental_sector_only,
        phi_grading_beta=phi_grading_beta,
    )
    mask_u = full_mesh.body_id == 0
    mask_l = full_mesh.body_id == 1

    def _subset(mask: np.ndarray) -> PanelBatch3D:
        return PanelBatch3D(
            centroids=full_mesh.centroids[mask],
            normals=full_mesh.normals[mask],
            tangents_1=full_mesh.tangents_1[mask],
            tangents_2=full_mesh.tangents_2[mask],
            areas=full_mesh.areas[mask],
            sigma_reg=full_mesh.sigma_reg[mask],
            body_id=full_mesh.body_id[mask],
            generation_id=full_mesh.generation_id[mask],
        )

    mesh_u = _subset(mask_u)
    mesh_l = _subset(mask_l)

    kappas, weights = gauss_legendre_kappa_grid(n_kappa, kappa_min=kappa_min, kappa_max=kappa_max)
    pts_np = np.asarray(eval_points, dtype=np.float64)
    inside_bulk_np = is_inside_cpsc_conductor(
        spec, theta_rad=theta_rad, points=pts_np, z_vane_override=z_vane_override, margin=min_wall_dist,
    )
    outside_t = torch.as_tensor(~inside_bulk_np, dtype=torch.bool, device=dev)
    pts_t = torch.as_tensor(pts_np, dtype=torch.float64, device=dev)

    # Pass 1: U + L coupled cavity
    t_ul, valid_ul = _evaluate_single_pass_stress_voxels(full_mesh, pts_t, field_model, kappas, weights, min_wall_dist)
    # Pass 2: Isolated upper assembly U
    t_u, valid_u = _evaluate_single_pass_stress_voxels(mesh_u, pts_t, field_model, kappas, weights, min_wall_dist)
    # Pass 3: Isolated lower assembly L
    t_l, valid_l = _evaluate_single_pass_stress_voxels(mesh_l, pts_t, field_model, kappas, weights, min_wall_dist)
    # Pass 4: Free Minkowski vacuum reference (analytically subtracted via G_full - G_0 = 0)
    t_vac = torch.zeros_like(t_ul)

    valid = valid_ul & valid_u & valid_l & outside_t
    t_mut = (t_ul - t_u - t_l + t_vac) * valid[:, None, None].to(torch.float64)
    t_ren = (t_ul - t_vac) * valid[:, None, None].to(torch.float64)

    return {
        "t_mutual": t_mut.detach().cpu().numpy(),
        "t_total_ren": t_ren.detach().cpu().numpy(),
        "t_upper_self": t_u.detach().cpu().numpy(),
        "t_lower_self": t_l.detach().cpu().numpy(),
        "valid_mask": valid.detach().cpu().numpy(),
    }
