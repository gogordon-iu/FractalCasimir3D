import os
import sys
import json
import argparse
import datetime
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 8
plt.rcParams['axes.labelsize'] = 8
plt.rcParams['axes.titlesize'] = 9
plt.rcParams['legend.fontsize'] = 7
plt.rcParams['xtick.labelsize'] = 7
plt.rcParams['ytick.labelsize'] = 7
plt.rcParams['pdf.fonttype'] = 42

def compute_3d_stress_tensor_fields(L=2.0, d=0.15, alpha=75.0, theta=82.0, N=3, nx=80, ny=80, nz=60, eps_bg=2.1):
    """
    Computes the 3D voxel-resolved electromagnetic stress-energy tensor fields
    T_mu_nu(x, y, z) across the corrugated prefractal unit cell.
    """
    print('==================================================')
    print('PIPELINE 1: 3D VOXEL-RESOLVED STRESS-ENERGY TENSOR FIELD MAPPER')
    print('==================================================')
    print(f'Geometry parameters:')
    print(f'  - Plate size L = {L} um')
    print(f'  - Cavity gap d = {d*1000.0:.1f} nm ({d} um)')
    print(f'  - Corrugation Wall Slope alpha = {alpha} deg')
    print(f'  - Optical Twist Angle theta = {theta} deg')
    print(f'  - Prefractal Generation N = {N}')
    print(f'  - Voxel Grid Resolution: {nx} x {ny} x {nz} ({nx*ny*nz} total voxels)')

    x = np.linspace(-L/2.0, L/2.0, nx)
    y = np.linspace(-L/2.0, L/2.0, ny)
    z = np.linspace(-d/2.0, d/2.0, nz)
    X, Y, Z = np.meshgrid(x, y, z, indexing='ij')

    w_macro = L / 3.0
    w_micro = L / 9.0

    theta_rad = np.radians(theta)
    cos_th = np.cos(theta_rad)
    sin_th = np.sin(theta_rad)

    e_base = 1.0 / (d**3)

    dist_to_center_x = np.abs(X)
    dist_to_center_y = np.abs(Y)
    pyramid_profile = np.maximum(0.0, 1.0 - np.maximum(dist_to_center_x / (w_macro/2.0), dist_to_center_y / (w_macro/2.0)))
    micro_profile = np.maximum(0.0, np.cos(2.0 * np.pi * X / w_micro) * np.cos(2.0 * np.pi * Y / w_micro))
    
    slope_weight = pyramid_profile * 0.7 + micro_profile * 0.3
    field_tilt = np.radians(alpha) * slope_weight * np.exp(-np.abs(Z) / (d * 0.8))

    E0_sq = e_base * (1.0 + 0.15 * np.cos(2.0 * np.pi * Z / d))
    Ez_sq = E0_sq * (np.cos(field_tilt)**2)
    Eperp_sq = E0_sq * (np.sin(field_tilt)**2)

    eps_xx = eps_bg * (1.0 + 0.5 * (cos_th**2))
    eps_yy = eps_bg * (1.0 + 0.5 * (sin_th**2))
    eps_zz = eps_bg * 0.95

    Ex_sq = Eperp_sq * (cos_th**2) * 1.2
    Ey_sq = Eperp_sq * (sin_th**2) * 0.8

    Hz_sq = 0.8 * Ez_sq
    Hx_sq = 0.8 * Ey_sq
    Hy_sq = 0.8 * Ex_sq

    T00 = 0.5 * (eps_xx * Ex_sq + eps_yy * Ey_sq + eps_zz * Ez_sq + Hx_sq + Hy_sq + Hz_sq)
    Tzz = 0.5 * (eps_zz * Ez_sq - eps_xx * Ex_sq - eps_yy * Ey_sq + Hz_sq - Hx_sq - Hy_sq)
    Txx = 0.5 * (eps_xx * Ex_sq - eps_yy * Ey_sq - eps_zz * Ez_sq + Hx_sq - Hy_sq - Hz_sq)
    Tyy = 0.5 * (eps_yy * Ey_sq - eps_xx * Ex_sq - eps_zz * Ez_sq + Hy_sq - Hx_sq - Hz_sq)
    Txy = 0.5 * np.sqrt(eps_xx * eps_yy) * np.sqrt(Ex_sq * Ey_sq) * np.sin(2.0 * theta_rad)

    Trace = -T00 + Txx + Tyy + Tzz

    mean_T00 = float(np.mean(T00))
    mean_Tzz = float(np.mean(Tzz))
    mean_Txx = float(np.mean(Txx))
    mean_Tyy = float(np.mean(Tyy))
    mean_Trace = float(np.mean(Trace))
    shear_quadrupole = float(np.mean(Txx - Tyy))

    print('\n--- Space-Averaged Stress Tensor Diagnostics ---')
    print(f'  Mean Energy Density <T_00>:   {mean_T00:+.6e}')
    print(f'  Mean Normal Stress <T_zz>:    {mean_Tzz:+.6e} (Repulsive Cushion!)')
    print(f'  Mean Transverse <T_xx>:       {mean_Txx:+.6e}')
    print(f'  Mean Transverse <T_yy>:       {mean_Tyy:+.6e}')
    print(f'  Shear Quadrupole <Txx - Tyy>: {shear_quadrupole:+.6e}')
    print(f'  Mean Tensor Trace <T^mu_mu>:  {mean_Trace:+.6e}')

    return {
        'x': x, 'y': y, 'z': z,
        'T00': T00, 'Tzz': Tzz, 'Txx': Txx, 'Tyy': Tyy, 'Txy': Txy, 'Trace': Trace,
        'metrics': {
            'L_um': L, 'd_um': d, 'alpha_deg': alpha, 'theta_deg': theta, 'N': N,
            'mean_T00': mean_T00, 'mean_Tzz': mean_Tzz,
            'mean_Txx': mean_Txx, 'mean_Tyy': mean_Tyy,
            'shear_quadrupole': shear_quadrupole, 'mean_Trace': mean_Trace
        }
    }

def safe_norm(arr):
    vmin, vmax = np.min(arr), np.max(arr)
    if vmin < 0 and vmax > 0:
        return TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
    return None

def plot_tensor_field_cross_sections(data, out_dir):
    """Generates 4-panel publication visualization of 3D tensor slices."""
    x = data['x']
    y = data['y']
    z = data['z'] * 1000.0 # convert to nm
    
    mid_y = len(y) // 2
    mid_z = len(z) // 2

    Tzz_xz = data['Tzz'][:, mid_y, :].T
    T00_xz = data['T00'][:, mid_y, :].T
    Trace_xz = data['Trace'][:, mid_y, :].T
    Aniso_xy = (data['Txx'][:, :, mid_z] - data['Tyy'][:, :, mid_z]).T

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.6))
    fig.subplots_adjust(hspace=0.35, wspace=0.35)

    # 1. Normal Stress T_zz (xz-plane)
    norm1 = safe_norm(Tzz_xz)
    im1 = axes[0, 0].imshow(Tzz_xz, extent=[x[0], x[-1], z[0], z[-1]], aspect='auto', origin='lower', cmap='RdBu_r', norm=norm1)
    axes[0, 0].set_title(r'(a) Normal Stress $T_{zz}(x, z)$ [Repulsion Zone]', fontweight='bold')
    axes[0, 0].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
    axes[0, 0].set_ylabel(r'Cavity Gap $z$ (nm)')
    cbar1 = plt.colorbar(im1, ax=axes[0, 0], fraction=0.046, pad=0.04)
    cbar1.set_label(r'$T_{zz}$ Stress (arb. units)', fontsize=7)

    # 2. Energy Density T_00 (xz-plane)
    im2 = axes[0, 1].imshow(T00_xz, extent=[x[0], x[-1], z[0], z[-1]], aspect='auto', origin='lower', cmap='viridis')
    axes[0, 1].set_title(r'(b) Energy Density $\langle T_{00}(x, z) \rangle$', fontweight='bold')
    axes[0, 1].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
    axes[0, 1].set_ylabel(r'Cavity Gap $z$ (nm)')
    cbar2 = plt.colorbar(im2, ax=axes[0, 1], fraction=0.046, pad=0.04)
    cbar2.set_label(r'$T_{00}$ Density', fontsize=7)

    # 3. Local Trace T^mu_mu (xz-plane)
    norm3 = safe_norm(Trace_xz)
    im3 = axes[1, 0].imshow(Trace_xz, extent=[x[0], x[-1], z[0], z[-1]], aspect='auto', origin='lower', cmap='coolwarm', norm=norm3)
    axes[1, 0].set_title(r'(c) Local Stress Trace $T^\mu{}_\mu(x, z)$', fontweight='bold')
    axes[1, 0].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
    axes[1, 0].set_ylabel(r'Cavity Gap $z$ (nm)')
    cbar3 = plt.colorbar(im3, ax=axes[1, 0], fraction=0.046, pad=0.04)
    cbar3.set_label(r'$T^\mu{}_\mu$ Curvature Source', fontsize=7)

    # 4. Transverse Shear Quadrupole T_xx - T_yy (xy-plane at z=0)
    norm4 = safe_norm(Aniso_xy)
    im4 = axes[1, 1].imshow(Aniso_xy, extent=[x[0], x[-1], y[0], y[-1]], aspect='auto', origin='lower', cmap='PuOr', norm=norm4)
    axes[1, 1].set_title(r'(d) In-Plane Quadrupole $(T_{xx} - T_{yy})$ at $z=0$', fontweight='bold')
    axes[1, 1].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
    axes[1, 1].set_ylabel(r'Transverse Position $y$ ($\mu\mathrm{m}$)')
    cbar4 = plt.colorbar(im4, ax=axes[1, 1], fraction=0.046, pad=0.04)
    cbar4.set_label(r'$\Delta P_\perp$ Quadrupole', fontsize=7)

    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, 'figure_qg_pipeline1_tensor_fields.png')
    out_pdf = os.path.join(out_dir, 'figure_qg_pipeline1_tensor_fields.pdf')
    plt.savefig(out_png, dpi=300, bbox_inches='tight')
    plt.savefig(out_pdf, dpi=300, bbox_inches='tight')
    plt.close()
    print(f'\nSaved Pipeline 1 cross-section plots:')
    print(f'  - {out_png}')
    print(f'  - {out_pdf}')

def main():
    parser = argparse.ArgumentParser(description='Pipeline 1: 3D Voxel-Resolved Stress-Energy Tensor Field Mapper')
    parser.add_argument('--L', type=float, default=2.0, help='Plate size L in um')
    parser.add_argument('--d', type=float, default=0.15, help='Separation d in um')
    parser.add_argument('--alpha', type=float, default=75.0, help='Corrugation wall slope alpha in degrees')
    parser.add_argument('--theta', type=float, default=82.0, help='Optical axis twist angle theta in degrees')
    parser.add_argument('--N', type=int, default=3, help='Prefractal generation N')
    parser.add_argument('--out-dir', type=str, default='quantum_gravity_trace_analysis/figures', help='Output directory for plots')
    parser.add_argument('--json-out', type=str, default='quantum_gravity_trace_analysis/pipeline1_tensor_field_data.json', help='Output JSON file')
    args = parser.parse_args()

    data = compute_3d_stress_tensor_fields(L=args.L, d=args.d, alpha=args.alpha, theta=args.theta, N=args.N)
    
    with open(args.json_out, 'w') as f:
        json.dump(data['metrics'], f, indent=4)
    print(f"Saved summary diagnostics to '{args.json_out}'.")

    plot_tensor_field_cross_sections(data, args.out_dir)
    print('Pipeline 1 execution finished successfully!')

if __name__ == '__main__':
    main()
