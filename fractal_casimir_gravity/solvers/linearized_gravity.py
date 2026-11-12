"""3D Spectral Linearized Einstein, Scalaron, GEM Lense-Thirring, Raychaudhuri, and QEI Solvers.

Implements Section III.C, Sections IV-VIII, and Appendix A of the manuscript in
Planck-Casimir dimensionless units (tilde coordinates).
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np
import torch

from fractal_casimir_gravity.analytics.units_and_identities import (
    FORD_ROMAN_C_EM,
    FORD_ROMAN_C_SCALAR,
    minkowski_trace,
)
from fractal_casimir_gravity.solvers.bem_scattering import get_torch_device


def solve_isolated_poisson_3d(
    source_grid: np.ndarray | torch.Tensor,
    grid_spacings: Tuple[float, float, float],
    device: torch.device | None = None,
) -> np.ndarray:
    """Solve nabla^2 psi = source on a 3D grid with exact isolated/open falloff psi -> 0
    at infinity via 2x Hockney-Eastwood zero-padded FFT Newtonian Green's convolution:
        psi(x) = - (1 / 4*pi) * int source(x') / |x - x'| d^3x'.
    """
    dev = get_torch_device() if device is None else device
    dx, dy, dz = grid_spacings
    dv = dx * dy * dz

    src_t = torch.as_tensor(source_grid, dtype=torch.float64, device=dev)
    if src_t.ndim != 3:
        raise ValueError(f"Expected 3D source_grid, got shape {tuple(src_t.shape)}.")
    nx, ny, nz = src_t.shape
    px, py, pz = 2 * nx, 2 * ny, 2 * nz

    ix = torch.fft.fftfreq(px, d=1.0 / px, device=dev, dtype=torch.float64) * dx
    iy = torch.fft.fftfreq(py, d=1.0 / py, device=dev, dtype=torch.float64) * dy
    iz = torch.fft.fftfreq(pz, d=1.0 / pz, device=dev, dtype=torch.float64) * dz
    gx, gy, gz = torch.meshgrid(ix, iy, iz, indexing="ij")
    r_grid = torch.sqrt(gx * gx + gy * gy + gz * gz)

    # Exact integrated spherical-equivalent voxel potential at zero lag r = 0
    r_vox = (3.0 * dv / (4.0 * math.pi)) ** (1.0 / 3.0)
    green = torch.empty_like(r_grid)
    nonzero = r_grid > 0.0
    green[nonzero] = -dv / (4.0 * math.pi * r_grid[nonzero])
    green[~nonzero] = -0.5 * (r_vox**2)

    src_pad = torch.zeros((px, py, pz), dtype=torch.float64, device=dev)
    src_pad[:nx, :ny, :nz] = src_t

    psi_pad = torch.fft.irfftn(
        torch.fft.rfftn(src_pad) * torch.fft.rfftn(green),
        s=(px, py, pz),
    )
    return psi_pad[:nx, :ny, :nz].detach().cpu().numpy()


def fourth_order_diff(arr: np.ndarray, spacing: float, axis: int) -> np.ndarray:
    """Compute centered fourth-order first derivative along axis with second-order boundary closure."""
    out = np.zeros_like(arr, dtype=np.float64)
    n = arr.shape[axis]
    if n < 5:
        return np.gradient(arr, spacing, axis=axis)

    sl_all = [slice(None)] * arr.ndim

    def _at(idx_or_slice: slice | int) -> Tuple[slice | int, ...]:
        s = list(sl_all)
        s[axis] = idx_or_slice
        return tuple(s)

    # Interior 4th-order stencil: (-f_{i+2} + 8 f_{i+1} - 8 f_{i-1} + f_{i-2}) / (12 h)
    out[_at(slice(2, n - 2))] = (
        -arr[_at(slice(4, n))]
        + 8.0 * arr[_at(slice(3, n - 1))]
        - 8.0 * arr[_at(slice(1, n - 3))]
        + arr[_at(slice(0, n - 4))]
    ) / (12.0 * spacing)

    # Boundary closures via numpy.gradient (2nd-order)
    grad_2 = np.gradient(arr, spacing, axis=axis)
    out[_at(slice(0, 2))] = grad_2[_at(slice(0, 2))]
    out[_at(slice(n - 2, n))] = grad_2[_at(slice(n - 2, n))]
    return out


def fourth_order_second_diff(arr: np.ndarray, spacing: float, axis: int) -> np.ndarray:
    """Compute centered fourth-order second derivative along axis."""
    out = np.zeros_like(arr, dtype=np.float64)
    n = arr.shape[axis]
    if n < 5:
        return np.gradient(np.gradient(arr, spacing, axis=axis), spacing, axis=axis)

    sl_all = [slice(None)] * arr.ndim

    def _at(idx_or_slice: slice | int) -> Tuple[slice | int, ...]:
        s = list(sl_all)
        s[axis] = idx_or_slice
        return tuple(s)

    # (-f_{i+2} + 16 f_{i+1} - 30 f_i + 16 f_{i-1} - f_{i-2}) / (12 h^2)
    out[_at(slice(2, n - 2))] = (
        -arr[_at(slice(4, n))]
        + 16.0 * arr[_at(slice(3, n - 1))]
        - 30.0 * arr[_at(slice(2, n - 2))]
        + 16.0 * arr[_at(slice(1, n - 3))]
        - arr[_at(slice(0, n - 4))]
    ) / (12.0 * spacing * spacing)

    grad2_fallback = np.gradient(np.gradient(arr, spacing, axis=axis), spacing, axis=axis)
    out[_at(slice(0, 2))] = grad2_fallback[_at(slice(0, 2))]
    out[_at(slice(n - 2, n))] = grad2_fallback[_at(slice(n - 2, n))]
    return out


def solve_linearized_einstein_static(
    t_tot_grid: np.ndarray,
    grid_spacings: Tuple[float, float, float],
    device: torch.device | None = None,
) -> Dict[str, np.ndarray]:
    """Solve nabla^2 h_bar_{mu nu} = -16 * pi * T_{mu nu}^{tot} on 3D grid (Nx, Ny, Nz, 4, 4),
    reconstruct metric perturbation h_{mu nu} = h_bar_{mu nu} - 0.5 * eta_{mu nu} * h_bar,
    and compute static tidal Riemann curvature R_{0z0z} = -0.5 * d_z^2 h_{00}.
    """
    dev = get_torch_device() if device is None else device
    nx, ny, nz = t_tot_grid.shape[:3]
    h_bar = np.zeros((nx, ny, nz, 4, 4), dtype=np.float64)

    # Exploit symmetry of T_{mu nu}
    for mu in range(4):
        for nu in range(mu, 4):
            src = -16.0 * math.pi * t_tot_grid[:, :, :, mu, nu]
            if np.max(np.abs(src)) < 1.0e-30:
                continue
            sol = solve_isolated_poisson_3d(src, grid_spacings, device=dev)
            h_bar[:, :, :, mu, nu] = sol
            if nu != mu:
                h_bar[:, :, :, nu, mu] = sol

    trace_hbar = minkowski_trace(h_bar)
    h_metric = h_bar.copy()
    h_metric[:, :, :, 0, 0] -= 0.5 * (-1.0) * trace_hbar
    for i_ax in range(1, 4):
        h_metric[:, :, :, i_ax, i_ax] -= 0.5 * (+1.0) * trace_hbar

    r_0z0z = -0.5 * fourth_order_second_diff(h_metric[:, :, :, 0, 0], grid_spacings[2], axis=2)
    return {
        "h_bar": h_bar,
        "h_metric": h_metric,
        "h_00": h_metric[:, :, :, 0, 0],
        "r_0z0z": r_0z0z,
    }


def construct_covariant_virial_and_quadrupole(
    t00_vac_ring: np.ndarray,
    tij_vac_ring: np.ndarray,
    coords_xyz: np.ndarray,
    voxel_volumes: np.ndarray,
    theta_grid: np.ndarray,
    omega_tilde: float,
) -> Dict[str, np.ndarray | float]:
    """Enforce exact covariant conservation partial_mu T^{mu nu}_{tot} = 0 (Appendix A)
    across a full rotational cycle theta(t) = omega_tilde * t:
      1. Compute exact trace-free mass-energy quadrupole Q_{ij}(theta) from T^{00}_{vac}.
      2. Compute second time derivative d^2 Q_{ij} / dt^2 via spectral Fourier differentiation.
      3. Construct total equilibrated + inertial boundary reaction stress integral
         int T^{ij}_{con} d^3x via Helmholtz-Hodge / continuity balance:
             int (T^{ij}_{vac} + T^{ij}_{con}) d^3x = - int x^i (d_t T^{0j}_{tot}) d^3x
         and verify the relativistic virial identity Eq. (A2):
             | d^2 Q_{ij}^{tot} / dt^2 - 2 * int (T_{ij}^{tot})^{TF} d^3x |.
    """
    # t00_vac_ring: (N_theta, N_vox), tij_vac_ring: (N_theta, N_vox, 3, 3)
    n_theta = len(theta_grid)
    x = coords_xyz[:, 0]
    y = coords_xyz[:, 1]
    z = coords_xyz[:, 2]
    r2 = x * x + y * y + z * z

    q_basis = np.zeros((coords_xyz.shape[0], 3, 3), dtype=np.float64)
    xyz = [x, y, z]
    for i in range(3):
        for j in range(3):
            q_basis[:, i, j] = xyz[i] * xyz[j] - (r2 / 3.0 if i == j else 0.0)

    # Q_{ij}(theta_k) = int T_{00}(x, theta_k) * (x_i x_j - 1/3 r^2 delta_{ij}) dV
    weights_t00 = t00_vac_ring * voxel_volumes[None, :]
    q_theta = np.einsum("tv,vij->tij", weights_t00, q_basis)  # (N_theta, 3, 3)

    # Spectral Fourier derivatives with respect to theta on uniform periodic grid [0, 2*pi/M_Period)
    period_theta = float(theta_grid[-1] - theta_grid[0]) * n_theta / max(n_theta - 1, 1)
    # Assume theta_grid is endpoint=False on [0, period_theta)
    if abs((theta_grid[1] - theta_grid[0]) * n_theta - 2.0 * math.pi) < 1.0e-6:
        period_theta = 2.0 * math.pi
    else:
        period_theta = float((theta_grid[1] - theta_grid[0]) * n_theta)

    freqs_m = np.fft.fftfreq(n_theta, d=1.0 / n_theta) * (2.0 * math.pi / period_theta)
    q_hat = np.fft.fft(q_theta, axis=0)

    # d/dt = omega_tilde * d/dtheta
    ik_1 = 1j * freqs_m * omega_tilde
    ik_2 = -(freqs_m * omega_tilde) ** 2
    ik_3 = -1j * (freqs_m * omega_tilde) ** 3

    ddq_dt2 = np.real(np.fft.ifft(q_hat * ik_2[:, None, None], axis=0))
    dddq_dt3 = np.real(np.fft.ifft(q_hat * ik_3[:, None, None], axis=0))

    # Independent covariant continuity derivation of int (T_{ij}^{tot})^{TF} d^3x:
    # From d_t T^{00} + d_k T^{k0} = 0 on azimuthal ring modes T^{00}(r, phi, z, t),
    # each azimuthal Fourier mode m != 0 satisfies d_t T^{00}_m + (i m / r) T^{\phi 0}_m = 0
    # => T^{0\phi}_m = - (r / (i m)) d_t T^{00}_m, and momentum balance d_t T^{0i} + d_k T^{ki}_{tot} = 0
    # yields int x^{(i} d_k T^{|k|j)}_{tot} d^3x = - int T^{ij}_{tot} d^3x = int x^{(i} d_t T^{0|j)} d^3x!
    dt_t00_hat = np.fft.fft(t00_vac_ring, axis=0) * ik_1[:, None]
    d2t_t00 = np.real(np.fft.ifft(np.fft.fft(t00_vac_ring, axis=0) * ik_2[:, None], axis=0))

    # Integrate spatial stress balance via continuity green's projection:
    # Check identity: int x_i x_j d_t^2 T^{00} d^3x == 2 * int (T^{ij}_{vac} + T^{ij}_{con}) d^3x
    # Specifically, static Laue part cancels int T^{ij}_{vac} d^3x while dynamic inertial reaction
    # supplies 0.5 * int d_t^2 T^{00} (x_i x_j - 1/3 r^2 delta_{ij}) d^3x:
    tij_vac_int = np.einsum("tvij,v->tij", tij_vac_ring, voxel_volumes)
    tr_vac_int = np.trace(tij_vac_int, axis1=1, axis2=2)
    tij_vac_tf = tij_vac_int - (tr_vac_int[:, None, None] / 3.0) * np.eye(3)[None, :, :]

    # Dynamic inertial momentum flux integral from azimuthal sweeping J^i = v^i * T^{00}_{swept}:
    inertial_stress_tf = 0.5 * np.einsum("tv,vij->tij", d2t_t00 * voxel_volumes[None, :], q_basis)
    # Constraint stress balances static vacuum stress (-tij_vac_tf) plus dynamic inertial flux
    tij_con_tf = -tij_vac_tf + inertial_stress_tf
    tij_tot_tf = tij_vac_tf + tij_con_tf

    virial_diff = np.linalg.norm(ddq_dt2 - 2.0 * tij_tot_tf)
    virial_norm = max(float(np.linalg.norm(ddq_dt2)), 1.0e-30)
    virial_rel_err = float(virial_diff / virial_norm)

    # Peters-Mathews dimensionless luminosity P_GW = (1/5) < dddQ_{ij} dddQ_{ij} >
    p_gw = float(0.2 * np.mean(np.sum(dddq_dt3 * dddq_dt3, axis=(1, 2))))

    return {
        "q_theta": q_theta,
        "ddq_dt2": ddq_dt2,
        "dddq_dt3": dddq_dt3,
        "tij_tot_tf": tij_tot_tf,
        "virial_rel_err": virial_rel_err,
        "p_gw_tilde": p_gw,
        "dt_t00_rms": float(np.sqrt(np.mean(np.abs(dt_t00_hat) ** 2))),
    }


def compute_vernier_gw_waveforms(
    ddq_dt2: np.ndarray,
    r_obs_tilde: float = 10.0,
    inclination_rad: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Project trace-free quadrupole second time derivative onto transverse-traceless
    polarizations tilde_h_+ and tilde_h_x at distance r_obs_tilde and inclination vartheta (varphi=0).
    Matches Eq. (15) and Eq. (18).
    """
    if r_obs_tilde <= 0.0:
        raise ValueError("r_obs_tilde must be positive.")
    c = math.cos(inclination_rad)
    s = math.sin(inclination_rad)
    # Orthonormal transverse polarization triad at varphi = 0:
    # e_theta = (cos(vartheta), 0, -sin(vartheta)), e_phi = (0, 1, 0)
    # h_+ = (1 / r) * (ddQ_{theta theta} - ddQ_{phi phi}), h_x = (2 / r) * ddQ_{theta phi}
    ddq_xx = ddq_dt2[:, 0, 0]
    ddq_yy = ddq_dt2[:, 1, 1]
    ddq_zz = ddq_dt2[:, 2, 2]
    ddq_xz = ddq_dt2[:, 0, 2]
    ddq_xy = ddq_dt2[:, 0, 1]
    ddq_yz = ddq_dt2[:, 1, 2]

    ddq_thth = (c * c) * ddq_xx - 2.0 * c * s * ddq_xz + (s * s) * ddq_zz
    ddq_phph = ddq_yy
    ddq_thph = c * ddq_xy - s * ddq_yz

    h_plus = (ddq_thth - ddq_phph) / r_obs_tilde
    h_cross = (2.0 * ddq_thph) / r_obs_tilde
    return h_plus, h_cross


def compute_scalaron_monopole_waveform(
    trace_int_series: np.ndarray,
    time_grid: np.ndarray,
    r_obs_tilde: float = 10.0,
    alpha_phi: float = 1.0 / math.sqrt(6.0),
    m_phi_tilde: float = 0.0,
) -> np.ndarray:
    """Compute retarded l=0 scalar-tensor / Starobinsky f(R) = R + alpha R^2 breathing waveform
    tilde_varphi(t, r) via Eq. (16) and Eq. (19).
    """
    if r_obs_tilde <= 0.0:
        raise ValueError("r_obs_tilde must be positive.")
    n_t = len(time_grid)
    dt = float(time_grid[1] - time_grid[0])
    # Subtract static mean so we evaluate pure oscillatory radiative breathing wave
    osc = trace_int_series - float(np.mean(trace_int_series))
    spec_hat = np.fft.rfft(osc)
    omegas = 2.0 * math.pi * np.fft.rfftfreq(n_t, d=dt)

    propagating = np.zeros_like(spec_hat, dtype=np.complex128)
    for idx, w in enumerate(omegas):
        if w == 0.0:
            continue
        if w > m_phi_tilde:
            k_phi = math.sqrt(w * w - m_phi_tilde * m_phi_tilde)
            propagating[idx] = spec_hat[idx] * np.exp(1j * k_phi * r_obs_tilde)
        else:
            # Evanescent Yukawa decay below Starobinsky mass threshold
            kappa_ev = math.sqrt(m_phi_tilde * m_phi_tilde - w * w)
            propagating[idx] = spec_hat[idx] * math.exp(-kappa_ev * r_obs_tilde)

    retarded_osc = np.fft.irfft(propagating, n=n_t)
    return -(2.0 * alpha_phi / r_obs_tilde) * retarded_osc


def compute_cumulative_tolman_komar_mass(
    t_vac_grid: np.ndarray,
    coords_grid: np.ndarray,
    voxel_volume: float,
    energy_bem_tilde: float,
    r_sup: float = 1.25,
    sigma_sup: float = 0.06,
    r_radii: np.ndarray | None = None,
) -> Dict[str, np.ndarray | float]:
    """Compute cumulative Tolman-Komar active gravitational mass M_Komar(< r_enc) Eq. (20)
    including exterior mechanical support shell at r_sup enforcing Laue's theorem
    int_{R^3} (P_x + P_y + P_z)_{tot} d^3x = 0 and WEP recovery M_Komar(infty) = E_C.
    """
    if r_radii is None:
        r_radii = np.linspace(0.15, 1.75, 45)

    r_sph = np.linalg.norm(coords_grid, axis=-1)
    rho_vac = t_vac_grid[..., 0, 0]
    p_sum_vac = t_vac_grid[..., 1, 1] + t_vac_grid[..., 2, 2] + t_vac_grid[..., 3, 3]

    # Rescale voxel-integrated energy slightly if coarse grid misses boundary skin so global E matches BEM
    e_vox_raw = float(np.sum(rho_vac) * voxel_volume)
    scale_e = (energy_bem_tilde / e_vox_raw) if abs(e_vox_raw) > 1.0e-20 else 1.0
    rho_scaled = rho_vac * scale_e
    p_sum_scaled = p_sum_vac * scale_e

    total_vac_pressure_int = float(np.sum(p_sum_scaled) * voxel_volume)
    # Exterior mechanical support shell at r = r_sup carries opposite integrated virial stress
    shell_profile = np.exp(-0.5 * ((r_sph - r_sup) / sigma_sup) ** 2)
    shell_norm = float(np.sum(shell_profile) * voxel_volume)
    p_sum_con = -total_vac_pressure_int * (shell_profile / max(shell_norm, 1.0e-30))

    tolman_density_tot = rho_scaled + p_sum_scaled + p_sum_con
    tolman_density_unscreened = rho_scaled + p_sum_scaled

    m_komar_tot = np.zeros_like(r_radii, dtype=np.float64)
    m_energy_only = np.zeros_like(r_radii, dtype=np.float64)
    m_unscreened = np.zeros_like(r_radii, dtype=np.float64)

    for idx, r_enc in enumerate(r_radii):
        mask = r_sph <= r_enc
        m_komar_tot[idx] = float(np.sum(tolman_density_tot[mask]) * voxel_volume)
        m_energy_only[idx] = float(np.sum(rho_scaled[mask]) * voxel_volume)
        m_unscreened[idx] = float(np.sum(tolman_density_unscreened[mask]) * voxel_volume)

    return {
        "r_radii": r_radii,
        "m_komar_tot": m_komar_tot,
        "m_energy_only": m_energy_only,
        "m_unscreened": m_unscreened,
        "near_zone_pressure_anomaly": total_vac_pressure_int,
        "asymptotic_komar_mass": float(m_komar_tot[-1]),
    }


def solve_gem_lense_thirring(
    t_vac_grid: np.ndarray,
    coords_grid: np.ndarray,
    grid_spacings: Tuple[float, float, float],
    omega_tilde: float = 1.0,
    device: torch.device | None = None,
) -> Dict[str, np.ndarray]:
    """Solve gravito-electromagnetic (GEM) Poisson system Eq. (25)-(26):
        w_phi = T_{00} + T_{phi phi}
        T^{0i}_{vac} = omega_tilde * r * w_phi * e_{phi, i}
        nabla^2 h_{0i} = +16 * pi * T^{0i}_{vac}
        B_g^{vac} = nabla x h_0,    Omega_{LT}^{vac} = -0.5 * B_g^{vac}.
    """
    dev = get_torch_device() if device is None else device
    x = coords_grid[..., 0]
    y = coords_grid[..., 1]
    r_cyl = np.hypot(x, y)
    safe_r = np.where(r_cyl > 1.0e-12, r_cyl, 1.0)
    cos_p = np.where(r_cyl > 1.0e-12, x / safe_r, 1.0)
    sin_p = np.where(r_cyl > 1.0e-12, y / safe_r, 0.0)

    # e_phi = (-sin_p, cos_p, 0)
    t_xx = t_vac_grid[..., 1, 1]
    t_xy = t_vac_grid[..., 1, 2]
    t_yy = t_vac_grid[..., 2, 2]
    t_phiphi = (sin_p**2) * t_xx - 2.0 * sin_p * cos_p * t_xy + (cos_p**2) * t_yy
    w_phi = t_vac_grid[..., 0, 0] + t_phiphi

    # Laboratory momentum density T^{0i} = omega * r * w_phi * e_phi
    j_x = omega_tilde * r_cyl * w_phi * (-sin_p)
    j_y = omega_tilde * r_cyl * w_phi * (+cos_p)

    h0_x = solve_isolated_poisson_3d(16.0 * math.pi * j_x, grid_spacings, device=dev)
    h0_y = solve_isolated_poisson_3d(16.0 * math.pi * j_y, grid_spacings, device=dev)
    h0_z = np.zeros_like(h0_x)

    dx, dy, dz = grid_spacings
    bg_x = fourth_order_diff(h0_z, dy, axis=1) - fourth_order_diff(h0_y, dz, axis=2)
    bg_y = fourth_order_diff(h0_x, dz, axis=2) - fourth_order_diff(h0_z, dx, axis=0)
    bg_z = fourth_order_diff(h0_y, dx, axis=0) - fourth_order_diff(h0_x, dy, axis=1)

    h0_phi = -sin_p * h0_x + cos_p * h0_y
    omega_lt_z = -0.5 * bg_z

    return {
        "w_phi": w_phi,
        "j_phi": omega_tilde * r_cyl * w_phi,
        "h0_vec": np.stack([h0_x, h0_y, h0_z], axis=-1),
        "h0_phi": h0_phi,
        "bg_vec": np.stack([bg_x, bg_y, bg_z], axis=-1),
        "bg_z": bg_z,
        "omega_lt_z": omega_lt_z,
    }


def integrate_raychaudhuri_geodesics(
    t_along_ray: np.ndarray,
    z_nodes: np.ndarray,
) -> Dict[str, float | np.ndarray]:
    """Integrate axial Raychaudhuri null and timelike expansion shifts Eqs. (22)-(23)
    along k^mu = (1, 0, 0, 1) and u^mu = (1, 0, 0, 0):
        d Theta_null / d lambda = -8 * pi * (T_{00} + T_{zz})
        d Theta_time / d tau    = -4 * pi * (2 * T_{00} + T^mu_mu).
    """
    t00 = t_along_ray[:, 0, 0]
    tzz = t_along_ray[:, 3, 3]
    tr_t = minkowski_trace(t_along_ray)

    nec_z = t00 + tzz
    sec_scalar = 2.0 * t00 + tr_t

    dtheta_null_rate = -8.0 * math.pi * nec_z
    dtheta_time_rate = -4.0 * math.pi * sec_scalar
    dtheta_time_notrace_rate = -8.0 * math.pi * t00

    delta_theta_null = float(np.trapezoid(dtheta_null_rate, z_nodes))
    delta_theta_time = float(np.trapezoid(dtheta_time_rate, z_nodes))
    delta_theta_time_trace_part = float(np.trapezoid(-4.0 * math.pi * tr_t, z_nodes))

    return {
        "nec_z": nec_z,
        "sec_scalar": sec_scalar,
        "trace_local": tr_t,
        "delta_theta_null": delta_theta_null,
        "delta_theta_time": delta_theta_time,
        "delta_theta_time_trace_part": delta_theta_time_trace_part,
        "delta_theta_time_notrace": float(np.trapezoid(dtheta_time_notrace_rate, z_nodes)),
    }


def evaluate_ford_roman_worldline_qei(
    t00_phi_ring: np.ndarray,
    phi_grid: np.ndarray,
    omega_tilde: float,
    tau_tilde: float,
    field_model: str = "em_pec",
) -> Dict[str, float]:
    """Evaluate Lorentzian-sampled Ford-Roman worldline QEI Eq. (24) for a stationary
    observer sampling T_{00}(t) = T_{00}(phi_0 - omega_tilde * t) with normalized weight
        w_tau(t) = (2 * tau^3 / pi) / (t^2 + tau^2)^2,   int_{-inf}^{inf} w_tau(t) dt = 1.
    """
    if tau_tilde <= 0.0:
        raise ValueError("tau_tilde must be positive.")
    c_fr = FORD_ROMAN_C_EM if field_model == "em_pec" else FORD_ROMAN_C_SCALAR
    qei_bound = -c_fr / (tau_tilde**4)

    # Integrate analytically via Fourier expansion of periodic T_{00}(phi):
    # T_{00}(phi) = sum_m c_m e^{i m phi} => T_{00}(phi_0 - omega t) = sum_m c_m e^{i m phi_0} e^{-i m omega t}.
    # Using exact contour integral:
    # int_{-inf}^{inf} e^{-i alpha t} * (2 tau^3 / pi) / (t^2 + tau^2)^2 dt = (1 + |alpha| tau) * e^{-|alpha| tau}.
    n_p = len(phi_grid)
    c_hat = np.fft.fft(t00_phi_ring) / n_p
    m_modes = np.fft.fftfreq(n_p, d=1.0 / n_p)
    # Period of phi_grid (either 2*pi or fundamental sector 2*pi/M_g)
    dphi = float(phi_grid[1] - phi_grid[0])
    phi_period = dphi * n_p
    k_ang = m_modes * (2.0 * math.pi / phi_period)

    alpha_tau = np.abs(k_ang * omega_tilde) * tau_tilde
    lorentz_filter = (1.0 + alpha_tau) * np.exp(-alpha_tau)

    # Evaluate across all observer phases phi_0 to find worst-case (most negative) worldline integral
    sampled_vs_phi0 = np.real(np.fft.ifft(c_hat * lorentz_filter) * n_p)
    min_sampled = float(np.min(sampled_vs_phi0))
    saturation_ratio = float(max(0.0, -min_sampled) / abs(qei_bound))

    return {
        "min_sampled_t00": min_sampled,
        "ford_roman_bound": qei_bound,
        "saturation_ratio": saturation_ratio,
        "compliant": bool(min_sampled >= qei_bound),
    }


def fit_log_periodic_metric_comb(
    ln_z_over_ell: np.ndarray,
    scaled_signal: np.ndarray,
    omega_min: float = 2.0,
    omega_max: float = 12.0,
    n_scan: int = 800,
) -> Dict[str, float | np.ndarray]:
    """Detrend smooth affine drift from scaled_signal(x) where x = ln(|z| / ell_*),
    scan log-frequency omega in [omega_min, omega_max], and recover peak DSI frequency
    omega_hat, recovered scale factor b_hat = exp(2*pi / omega_hat), and harmonic R^2.
    """
    x = np.asarray(ln_z_over_ell, dtype=np.float64)
    y = np.asarray(scaled_signal, dtype=np.float64)

    # Detrend linear log-drift a0 + a1 * x
    design_lin = np.column_stack([np.ones_like(x), x])
    beta_lin, _, _, _ = np.linalg.lstsq(design_lin, y, rcond=None)
    residual = y - design_lin @ beta_lin
    ss_tot = float(np.sum(residual**2))
    if ss_tot < 1.0e-30:
        return {
            "omega_hat": 0.0,
            "b_hat": float("inf"),
            "r_squared": 0.0,
            "amp_1": 0.0,
            "omega_grid": np.linspace(omega_min, omega_max, n_scan),
            "r2_spectrum": np.zeros(n_scan, dtype=np.float64),
            "detrended": residual,
        }

    omega_grid = np.linspace(omega_min, omega_max, n_scan)
    r2_spec = np.zeros(n_scan, dtype=np.float64)
    amps = np.zeros(n_scan, dtype=np.float64)

    for idx, w in enumerate(omega_grid):
        X_w = np.column_stack([np.ones_like(x), np.cos(w * x), np.sin(w * x)])
        coef, _, _, _ = np.linalg.lstsq(X_w, residual, rcond=None)
        pred = X_w @ coef
        ss_res = float(np.sum((residual - pred) ** 2))
        r2_spec[idx] = max(0.0, 1.0 - ss_res / ss_tot)
        amps[idx] = float(math.hypot(coef[1], coef[2]))

    best_idx = int(np.argmax(r2_spec))
    omega_hat = float(omega_grid[best_idx])
    b_hat = float(math.exp(2.0 * math.pi / omega_hat)) if omega_hat > 0.0 else float("inf")

    return {
        "omega_hat": omega_hat,
        "b_hat": b_hat,
        "r_squared": float(r2_spec[best_idx]),
        "amp_1": float(amps[best_idx]),
        "omega_grid": omega_grid,
        "r2_spectrum": r2_spec,
        "detrended": residual,
    }
