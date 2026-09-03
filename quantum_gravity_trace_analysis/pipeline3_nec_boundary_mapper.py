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

HBAR = 1.054571817e-34
C_LIGHT = 299792458.0

def safe_norm(arr):
    vmin, vmax = np.min(arr), np.max(arr)
    if vmin < 0 and vmax > 0:
        return TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
    return None

def analyze_nec_boundaries(summary_path=None, out_dir="quantum_gravity_trace_analysis/figures", json_out="quantum_gravity_trace_analysis/pipeline3_nec_boundary_summary.json"):
    print('==================================================')
    print('PIPELINE 3: NULL ENERGY CONDITION (NEC) & ENERGY INVERSION MAPPER')
    print('==================================================')

    if summary_path and os.path.exists(summary_path):
        target_files = [summary_path]
    else:
        target_files = sorted(glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json"))
        if not target_files:
            target_files = sorted(glob.glob("results_*/sweet_spot_sweep_summary.json"))

    if not target_files:
        raise FileNotFoundError("No sweet spot sweep summary JSON file found.")

    latest_file = target_files[-1]
    print(f"Loading dataset from '{latest_file}'...")
    with open(latest_file, 'r') as f:
        data = json.load(f)

    # Group by (alpha, theta)
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
            'pressure_Pa': p_pa
        })

    # Evaluate Null Energy Condition along normal direction: NEC_z = rho_vac + P_z
    C_eff = 0.0108 # N=3 prefractal Lifshitz geometric scale
    nec_analysis = []
    print("\n--- Evaluating Null Energy Condition (NEC_z = rho_vac + P_z) ---")

    for (alpha, theta), pts in sorted(curves.items()):
        pts.sort(key=lambda x: x['d_um'])
        if len(pts) >= 2:
            d_nm_list = []
            p_list = []
            nec_list = []
            ratio_list = []

            for p in pts:
                d_m = p['d_m']
                d_nm = p['d_um'] * 1000.0
                p_z = p['pressure_Pa']

                # Local baseline vacuum energy density
                rho_vac_pa = -(HBAR * C_LIGHT / (d_m**4)) * C_eff
                
                # Null Energy Condition: NEC_z = rho_vac + P_z
                nec_val = rho_vac_pa + p_z

                # Restoration ratio: eta = P_z / |rho_vac|
                eta = p_z / abs(rho_vac_pa)

                d_nm_list.append(d_nm)
                p_list.append(p_z)
                nec_list.append(nec_val)
                ratio_list.append(eta)

            max_p = max(p_list)
            max_nec = max(nec_list)
            max_eta = max(ratio_list)
            is_nec_restored = bool(max_p > 0 and max_nec >= 0)

            rec = {
                'alpha_deg': alpha,
                'theta_deg': theta,
                'max_pressure_Pa': float(max_p),
                'max_nec_val_Pa': float(max_nec),
                'max_restoration_ratio_eta': float(max_eta),
                'is_repulsive': bool(max_p > 0),
                'is_nec_restored': is_nec_restored,
                'curve_points': [
                    {'d_nm': round(d_nm_list[i], 2), 'pressure_Pa': p_list[i], 'nec_z_Pa': nec_list[i], 'eta': ratio_list[i]}
                    for i in range(len(d_nm_list))
                ]
            }
            nec_analysis.append(rec)
            status = "RESTORED (NEC >= 0)" if is_nec_restored else "Violated (Standard QFT)"
            print(f"  Alpha={alpha:4.1f} deg, Theta={theta:4.1f} deg => P_max={max_p:+.4f} Pa | Status: {status}")

    # Save summary JSON
    summary_data = {
        'metadata': {
            'dataset_source': latest_file,
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_configurations': len(nec_analysis),
            'note': 'NEC_z = rho_vac + P_z. When P_z > |rho_vac|, NEC is locally restored in vacuum.'
        },
        'nec_configurations': nec_analysis
    }
    os.makedirs(os.path.dirname(json_out), exist_ok=True)
    with open(json_out, 'w') as f:
        json.dump(summary_data, f, indent=4)
    print(f"\nSaved Pipeline 3 summary dataset to '{json_out}'.")

    # Generate Publication Plots
    plot_nec_figures(curves, nec_analysis, out_dir)
    print("Pipeline 3 analysis completed successfully!")

def plot_nec_figures(curves, nec_results, out_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.4))
    fig.subplots_adjust(wspace=0.35)

    # ------------------ PANEL A: 1D NEC_z(d) Curves ------------------
    rep_thetas = [80.0, 82.0, 90.0, 92.0, 94.0]
    colors = ['#1e3799', '#0984e3', '#00b894', '#e17055', '#d63031']

    for idx, th in enumerate(rep_thetas):
        key = (75.0, th)
        if key in curves:
            pts = sorted(curves[key], key=lambda x: x['d_um'])
            d_nm = [p['d_um'] * 1000.0 for p in pts]
            p_vals = [p['pressure_Pa'] for p in pts]
            
            # Plot P_z as proxy for NEC_z normal stress cushion
            ax1.plot(d_nm, p_vals, 'o-', color=colors[idx], label=f'$\\theta = {th:.0f}^\\circ$', linewidth=1.2, markersize=3.5)

    ax1.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.7)
    ax1.fill_between([50, 350], 0, 1.0, color='green', alpha=0.08, label='NEC Restored (P > 0)')
    ax1.fill_between([50, 350], -1.0, 0, color='red', alpha=0.05, label='NEC Violated (P < 0)')

    ax1.set_xlabel(r'Cavity Gap $d$ (nm)')
    ax1.set_ylabel(r'Normal Stress / NEC Driver $P_z$ (Pa)')
    ax1.set_title(r'(a) Null Energy Driver $P_z(d)$ ($\alpha = 75^\circ$)', fontweight='bold')
    ax1.set_xlim(50, 350)
    ax1.set_ylim(-0.03, 0.03)
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.legend(loc='lower right', frameon=True, facecolor='#f5f5f5', edgecolor='none', fontsize=6.5)

    # ------------------ PANEL B: 2D Phase Diagram of Maximum Repulsive Stress ------------------
    if len(nec_results) >= 4:
        alphas = np.array([p['alpha_deg'] for p in nec_results])
        thetas = np.array([p['theta_deg'] for p in nec_results])
        p_maxs = np.array([p['max_pressure_Pa'] for p in nec_results])

        grid_a, grid_th = np.mgrid[70:75:50j, 80:94:50j]
        grid_p = griddata((alphas, thetas), p_maxs, (grid_a, grid_th), method='linear')

        norm = safe_norm(grid_p)
        im = ax2.imshow(grid_p, extent=[80, 94, 70, 75], origin='lower', aspect='auto', cmap='RdYlGn', norm=norm)
        cbar = plt.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
        cbar.set_label(r'Max Repulsive Pressure $P_{\mathrm{max}}$ (Pa)', fontsize=7)

        ax2.scatter(thetas, alphas, c='white', edgecolor='black', s=25, zorder=4)
        ax2.set_xlabel(r'Optical Axis Twist Angle $\theta$ (deg)')
        ax2.set_ylabel(r'Corrugation Wall Slope $\alpha$ (deg)')
        ax2.set_title(r'(b) NEC-Restored Operational State Space $(\alpha, \theta)$', fontweight='bold')

    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, 'figure_qg_pipeline3_nec_boundaries.png')
    out_pdf = os.path.join(out_dir, 'figure_qg_pipeline3_nec_boundaries.pdf')
    plt.savefig(out_png, dpi=300, bbox_inches='tight')
    plt.savefig(out_pdf, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved Pipeline 3 publication plots:")
    print(f"  - {out_png}")
    print(f"  - {out_pdf}")

def main():
    parser = argparse.ArgumentParser(description='Pipeline 3: Null Energy Condition (NEC) & Energy Inversion Mapper')
    parser.add_argument('--summary', type=str, default=None, help='Path to sweet_spot_sweep_summary.json')
    parser.add_argument('--out-dir', type=str, default='quantum_gravity_trace_analysis/figures', help='Output directory for plots')
    parser.add_argument('--json-out', type=str, default='quantum_gravity_trace_analysis/pipeline3_nec_boundary_summary.json', help='Output JSON summary path')
    args = parser.parse_args()

    analyze_nec_boundaries(summary_path=args.summary, out_dir=args.out_dir, json_out=args.json_out)

if __name__ == '__main__':
    main()
