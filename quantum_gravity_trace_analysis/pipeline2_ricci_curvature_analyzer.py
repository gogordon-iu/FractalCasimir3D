import os
import sys
import glob
import json
import argparse
import datetime
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from scipy.interpolate import griddata

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 8
plt.rcParams['axes.labelsize'] = 8
plt.rcParams['axes.titlesize'] = 9
plt.rcParams['legend.fontsize'] = 7
plt.rcParams['xtick.labelsize'] = 7
plt.rcParams['ytick.labelsize'] = 7
plt.rcParams['pdf.fonttype'] = 42

# Physical Constants (SI)
HBAR = 1.054571817e-34 # J*s
C_LIGHT = 299792458.0  # m/s
G_NEWTON = 6.67430e-11 # m^3 / (kg * s^2)
L_PLANCK = np.sqrt(HBAR * G_NEWTON / (C_LIGHT**3)) # 1.616e-35 m

def safe_norm(arr):
    vmin, vmax = np.min(arr), np.max(arr)
    if vmin < 0 and vmax > 0:
        return TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
    return None

def analyze_ricci_curvature(summary_path=None, out_dir="quantum_gravity_trace_analysis/figures", json_out="quantum_gravity_trace_analysis/pipeline2_ricci_curvature_summary.json"):
    print('==================================================')
    print('PIPELINE 2: PARAMETER-SPACE RICCI CURVATURE & QUANTUM GRAVITY ANALYZER')
    print('==================================================')

    # 1. Locate summary files
    if summary_path and os.path.exists(summary_path):
        target_files = [summary_path]
    else:
        target_files = sorted(glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json"))
        if not target_files:
            target_files = sorted(glob.glob("results_*/sweet_spot_sweep_summary.json"))
    
    if not target_files:
        raise FileNotFoundError("No sweet spot sweep summary JSON file found.")
        
    latest_file = target_files[-1]
    print(f"Loading empirical dataset from '{latest_file}'...")
    with open(latest_file, 'r') as f:
        data = json.load(f)

    print(f"Loaded {len(data)} total parameter points.")

    # 2. Group by (alpha, theta) to extract curves P(d)
    curves = {}
    for r in data:
        alpha = float(r.get('alpha_deg', r.get('alpha', 75.0)))
        theta = float(r.get('theta_deg', r.get('theta', 90.0)))
        d_um = float(r.get('d_um', r.get('d', 0.1)))
        p_pa = float(r.get('pressure_Pa', r.get('pressure', 0.0)))

        key = (round(alpha, 1), round(theta, 1))
        if key not in curves:
            curves[key] = []
        curves[key].append({
            'd_um': d_um,
            'd_m': d_um * 1e-6,
            'pressure_Pa': p_pa,
            'is_repulsive': p_pa > 0
        })

    # 3. Find Levitation Equilibrium Points (P = 0, dP/dd < 0) & Evaluate Curvature Invariant
    equilibrium_results = []
    print("\n--- Identifying Levitation Equilibrium Points & Levitation-Locked Curvatures ---")

    for (alpha, theta), pts in sorted(curves.items()):
        pts.sort(key=lambda x: x['d_um'])
        if len(pts) >= 2:
            d_arr = [p['d_um'] for p in pts]
            p_arr = [p['pressure_Pa'] for p in pts]

            for i in range(len(p_arr) - 1):
                # Zero crossing from positive (repulsive) to negative (attractive)
                if p_arr[i] > 0 and p_arr[i+1] < 0:
                    d1, d2 = d_arr[i], d_arr[i+1]
                    p1, p2 = p_arr[i], p_arr[i+1]
                    d_eq_um = d1 + (0.0 - p1) * (d2 - d1) / (p2 - p1)
                    d_eq_nm = d_eq_um * 1000.0
                    d_eq_m = d_eq_um * 1e-6

                    # Levitation Restoring Spring Stiffness: kappa = -dP/dd (Pa/m)
                    dP_dd = (p2 - p1) / ((d2 - d1) * 1e-6)
                    stiffness_kappa = -dP_dd

                    # Physical Vacuum Energy Density at d_eq (estimated via Lifshitz/PFA scaling)
                    # For N=3, C_0 ~ (8/9)^2 * (pi^2 / 720) ~ 0.0108
                    C_eff = 0.0108
                    rho_vac_J_m3 = -(HBAR * C_LIGHT / (d_eq_m**4)) * C_eff

                    # 1. Levitation-Locked Trace Invariant: T^mu_mu(d_eq) = -3 * rho_vac(d_eq)
                    T_trace_d_eq = -3.0 * rho_vac_J_m3 # in J/m^3 = Pa

                    # 2. Semiclassical Ricci Scalar Curvature: R(d_eq) = -8*pi*G/c^4 * T^mu_mu
                    # R = +24 * pi * G / c^4 * rho_vac
                    Ricci_R_m2 = (24.0 * np.pi * G_NEWTON / (C_LIGHT**4)) * rho_vac_J_m3
                    Ricci_Planck_dimless = Ricci_R_m2 * (d_eq_m**2)

                    rec = {
                        'alpha_deg': alpha,
                        'theta_deg': theta,
                        'd_eq_nm': round(d_eq_nm, 2),
                        'd_eq_um': round(d_eq_um, 4),
                        'stiffness_kappa_Pa_per_m': float(stiffness_kappa),
                        'p_max_repulsive_Pa': max(p_arr),
                        'rho_vac_J_m3': float(rho_vac_J_m3),
                        'T_trace_J_m3': float(T_trace_d_eq),
                        'Ricci_scalar_R_m2': float(Ricci_R_m2),
                        'Ricci_Planck_scaled': float(Ricci_Planck_dimless)
                    }
                    equilibrium_results.append(rec)
                    print(f"  Alpha={alpha:4.1f} deg, Theta={theta:4.1f} deg => d_eq={d_eq_nm:6.2f} nm | P_max={max(p_arr):+.4f} Pa | R={Ricci_R_m2:+.4e} m^-2")

    # 4. Save analysis JSON
    summary_data = {
        'metadata': {
            'dataset_source': latest_file,
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'num_equilibrium_points': len(equilibrium_results),
            'note': 'At levitation equilibrium P_z=0, R(d_eq) = +24*pi*G*rho_vac/c^4 (pure force-free spacetime curvature)'
        },
        'equilibrium_curvature_points': equilibrium_results
    }
    os.makedirs(os.path.dirname(json_out), exist_ok=True)
    with open(json_out, 'w') as f:
        json.dump(summary_data, f, indent=4)
    print(f"\nSaved Pipeline 2 summary dataset to '{json_out}'.")

    # 5. Generate Publication Plots
    plot_ricci_curvature_figures(curves, equilibrium_results, out_dir)
    print("Pipeline 2 analysis completed successfully!")

def plot_ricci_curvature_figures(curves, eq_points, out_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.4))
    fig.subplots_adjust(wspace=0.35)

    # ------------------ PANEL A: 1D Pressure & Ricci Curvature Curves ------------------
    # Select representative curves for alpha=75 deg
    rep_thetas = [80.0, 82.0, 90.0, 92.0, 94.0]
    colors = ['#1e3799', '#0984e3', '#00b894', '#e17055', '#d63031']

    for idx, th in enumerate(rep_thetas):
        key = (75.0, th)
        if key in curves:
            pts = sorted(curves[key], key=lambda x: x['d_um'])
            d_nm = [p['d_um'] * 1000.0 for p in pts]
            p_vals = [p['pressure_Pa'] for p in pts]
            ax1.plot(d_nm, p_vals, 'o-', color=colors[idx], label=f'$\\theta = {th:.0f}^\\circ$', linewidth=1.2, markersize=3.5)

    ax1.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.7)
    
    # Highlight stable equilibrium points
    for eq in eq_points:
        if eq['alpha_deg'] == 75.0 and eq['theta_deg'] in rep_thetas:
            ax1.scatter([eq['d_eq_nm']], [0.0], color='gold', edgecolor='black', s=50, zorder=5, marker='*')

    ax1.set_xlabel(r'Cavity Gap $d$ (nm)')
    ax1.set_ylabel(r'Casimir Normal Pressure $P_\perp$ (Pa)')
    ax1.set_title(r'(a) Casimir Pressure & Zero-Force Levitation ($\alpha = 75^\circ$)', fontweight='bold')
    ax1.set_ylim(-0.04, 0.04)
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.legend(loc='lower right', frameon=True, facecolor='#f5f5f5', edgecolor='none')

    # ------------------ PANEL B: 2D Phase Diagram of Levitation-Locked Ricci Curvature R(alpha, theta) ------------------
    if len(eq_points) >= 4:
        alphas = np.array([p['alpha_deg'] for p in eq_points])
        thetas = np.array([p['theta_deg'] for p in eq_points])
        d_eqs = np.array([p['d_eq_nm'] for p in eq_points])

        grid_a, grid_th = np.mgrid[70:75:50j, 80:94:50j]
        grid_d = griddata((alphas, thetas), d_eqs, (grid_a, grid_th), method='linear')

        im = ax2.imshow(grid_d, extent=[80, 94, 70, 75], origin='lower', aspect='auto', cmap='plasma')
        cbar = plt.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
        cbar.set_label(r'Stable Levitation Height $d_{\mathrm{eq}}$ (nm)', fontsize=7)

        # Plot empirical points
        ax2.scatter(thetas, alphas, c='white', edgecolor='black', s=25, zorder=4)
        for p in eq_points:
            ax2.annotate(f"{p['d_eq_nm']:.0f}nm", (p['theta_deg'], p['alpha_deg']), textcoords="offset points", xytext=(0,4), ha='center', fontsize=6, color='black', weight='bold')

        ax2.set_xlabel(r'Optical Axis Twist Angle $\theta$ (deg)')
        ax2.set_ylabel(r'Corrugation Wall Slope $\alpha$ (deg)')
        ax2.set_title(r'(b) Levitation-Locked Metric State Space $d_{\mathrm{eq}}(\alpha, \theta)$', fontweight='bold')

    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, 'figure_qg_pipeline2_ricci_curvature.png')
    out_pdf = os.path.join(out_dir, 'figure_qg_pipeline2_ricci_curvature.pdf')
    plt.savefig(out_png, dpi=300, bbox_inches='tight')
    plt.savefig(out_pdf, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved Pipeline 2 publication plots:")
    print(f"  - {out_png}")
    print(f"  - {out_pdf}")

def main():
    parser = argparse.ArgumentParser(description='Pipeline 2: Parameter-Space Ricci Curvature & Quantum Gravity Analyzer')
    parser.add_argument('--summary', type=str, default=None, help='Path to sweet_spot_sweep_summary.json')
    parser.add_argument('--out-dir', type=str, default='quantum_gravity_trace_analysis/figures', help='Output directory for plots')
    parser.add_argument('--json-out', type=str, default='quantum_gravity_trace_analysis/pipeline2_ricci_curvature_summary.json', help='Output JSON summary path')
    args = parser.parse_args()

    analyze_ricci_curvature(summary_path=args.summary, out_dir=args.out_dir, json_out=args.json_out)

if __name__ == '__main__':
    main()
