import os
import sys
import glob
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import TwoSlopeNorm

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def main():
    print("==================================================")
    print("PAIRWISE PARAMETER SWEEP ANALYSIS & VISUALIZATION GENERATOR")
    print("==================================================")

    # 1. Load all records from results directories and .tmp
    summary_files = glob.glob("results_hybrid_parameter_sweep_*/hybrid_sweep_summary.json") + glob.glob("results_corrugated_*/corrugated_sweep_results.json")
    tmp_files = glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")

    records = []
    for fp in summary_files + tmp_files:
        try:
            with open(fp, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict) and "d_um" in data:
                    records.append(data)
        except Exception as e:
            pass

    print(f"Loaded {len(records)} total simulation JSON records.")

    # 2. Extract and organize unique (alpha, theta, d) points
    results_map = {}
    for rec in records:
        d = float(rec.get("d_um", 0.1))
        theta = float(rec.get("theta_deg", 90.0))
        alpha = float(rec.get("corrugation_angle", 60.0))
        
        f_both = rec.get("force_both", None)
        f_self = rec.get("force_self", None)
        p_direct = rec.get("pressure_Pa", rec.get("pressure", None))
        
        if p_direct is not None:
            p = float(p_direct)
            key = (round(alpha, 1), round(theta, 1), round(d, 4))
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }
        elif f_both is not None and f_self is not None:
            f_net = float(f_both) - float(f_self)
            A_eff = get_effective_area(3, float(rec.get("L", 2.0)))
            p = f_net / A_eff
            key = (round(alpha, 1), round(theta, 1), round(d, 4))
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }

    data_list = list(results_map.values())
    print(f"Extracted {len(data_list)} unique physical parameter points.")

    out_fig_dir = "Papers/Fractal_Casimir_Version_02/figures"
    os.makedirs(out_fig_dir, exist_ok=True)
    os.makedirs("scratch", exist_ok=True)

    # Styling for publication-quality plots
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    plt.rcParams.update({
        'font.size': 12,
        'font.family': 'sans-serif',
        'axes.labelsize': 14,
        'axes.titlesize': 14,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
        'legend.fontsize': 11,
        'figure.titlesize': 16
    })

    # ==================================================
    # PAIR 1: (theta, alpha) at fixed d = 0.10 um (100 nm)
    # ==================================================
    print("\nProcessing Pair 1: (theta, alpha) Phase Space...")
    p1_data = [r for r in data_list if abs(r["d_um"] - 0.10) < 0.01]
    
    # 1D Line Graph for Pair 1: P(theta) for various alpha
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    alphas = sorted(list(set(r["alpha_deg"] for r in p1_data)))
    colors = plt.cm.plasma(np.linspace(0.1, 0.9, max(1, len(alphas))))
    
    for idx, a in enumerate(alphas):
        pts = sorted([r for r in p1_data if abs(r["alpha_deg"] - a) < 0.5], key=lambda x: x["theta_deg"])
        if pts:
            th_vals = [r["theta_deg"] for r in pts]
            p_vals = [r["pressure_Pa"] for r in pts]
            ax.plot(th_vals, p_vals, 'o-', label=f"Wall Slope $\\alpha = {a}^\\circ$", color=colors[idx], linewidth=2, markersize=6)
            
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5, label='Zero-Pressure Boundary ($P=0$)')
    ax.set_xlabel("Twist Angle $\\theta$ (degrees)")
    ax.set_ylabel("Consolidated Casimir Pressure $P$ (Pa)")
    ax.set_title("Pair 1: Casimir Pressure vs. Twist Angle $\\theta$ ($d = 100$ nm)")
    ax.legend(loc='best', frameon=True)
    plt.tight_layout()
    fig1_path = os.path.join(out_fig_dir, "pair1_theta_alpha_1d.png")
    fig.savefig(fig1_path, dpi=300)
    plt.close(fig)
    print(f"Saved 1D plot: {fig1_path}")

    # 2D Contour Heatmap for Pair 1: (theta, alpha) Phase Diagram
    if len(p1_data) >= 4:
        fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
        th_arr = np.array([r["theta_deg"] for r in p1_data])
        al_arr = np.array([r["alpha_deg"] for r in p1_data])
        pr_arr = np.array([r["pressure_Pa"] for r in p1_data])
        
        # Grid interpolation
        ti = np.linspace(min(th_arr), max(th_arr), 100)
        ai = np.linspace(min(al_arr), max(al_arr), 100)
        TT, AA = np.meshgrid(ti, ai)
        
        from scipy.interpolate import griddata
        try:
            PP = griddata((th_arr, al_arr), pr_arr, (TT, AA), method='cubic', fill_value=0.0)
        except Exception:
            PP = griddata((th_arr, al_arr), pr_arr, (TT, AA), method='nearest', fill_value=0.0)
        
        vmin, vmax = min(pr_arr), max(pr_arr)
        norm = TwoSlopeNorm(vmin=min(vmin, -0.01), vcenter=0.0, vmax=max(vmax, 0.01))
        
        contour = ax.contourf(TT, AA, PP, levels=50, cmap='RdBu_r', norm=norm)
        cbar = fig.colorbar(contour, ax=ax)
        cbar.set_label("Casimir Pressure $P$ (Pa)")
        
        # Contour line for zero boundary
        ax.contour(TT, AA, PP, levels=[0.0], colors='black', linewidths=2.5, linestyles='--')
        ax.scatter(th_arr, al_arr, c='black', s=20, alpha=0.6, label='3D FDTD Grid Points')
        
        ax.set_xlabel("Twist Angle $\\theta$ (degrees)")
        ax.set_ylabel("Corrugation Wall Slope $\\alpha$ (degrees)")
        ax.set_title("Pair 1: 2D Phase Diagram $P(\\theta, \\alpha)$ ($d = 100$ nm)")
        ax.legend(loc='lower left', frameon=True)
        plt.tight_layout()
        fig1_2d_path = os.path.join(out_fig_dir, "pair1_theta_alpha_2d.png")
        fig.savefig(fig1_2d_path, dpi=300)
        plt.close(fig)
        print(f"Saved 2D heatmap: {fig1_2d_path}")

    # ==================================================
    # PAIR 2: (theta, d) at fixed alpha = 60.0 deg
    # ==================================================
    print("\nProcessing Pair 2: (theta, d) Phase Space...")
    p2_data = [r for r in data_list if abs(r["alpha_deg"] - 60.0) < 0.5]
    
    # 1D Line Graph for Pair 2: P(d) force-distance curves for various theta
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    thetas = sorted(list(set(r["theta_deg"] for r in p2_data)))
    colors = plt.cm.viridis(np.linspace(0.1, 0.9, max(1, len(thetas))))
    
    for idx, th in enumerate(thetas):
        pts = sorted([r for r in p2_data if abs(r["theta_deg"] - th) < 0.5], key=lambda x: x["d_um"])
        if pts:
            d_vals = [r["d_um"] * 1000.0 for r in pts] # convert to nm
            p_vals = [r["pressure_Pa"] for r in pts]
            ax.plot(d_vals, p_vals, 's-', label=f"$\\theta = {th}^\\circ$", color=colors[idx], linewidth=2, markersize=6)
            
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5, label='Zero-Pressure Boundary ($P=0$)')
    ax.set_xlabel("Separation Distance $d$ (nm)")
    ax.set_ylabel("Consolidated Casimir Pressure $P$ (Pa)")
    ax.set_title("Pair 2: Force-Distance Curves $P(d)$ vs. Twist Angle $\\theta$ ($\\alpha = 60^\\circ$)")
    ax.legend(loc='best', frameon=True)
    plt.tight_layout()
    fig2_path = os.path.join(out_fig_dir, "pair2_theta_d_1d.png")
    fig.savefig(fig2_path, dpi=300)
    plt.close(fig)
    print(f"Saved 1D plot: {fig2_path}")

    # 2D Contour Heatmap for Pair 2: (theta, d) Phase Diagram
    if len(p2_data) >= 4:
        fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
        th_arr = np.array([r["theta_deg"] for r in p2_data])
        d_arr = np.array([r["d_um"] * 1000.0 for r in p2_data])
        pr_arr = np.array([r["pressure_Pa"] for r in p2_data])
        
        ti = np.linspace(min(th_arr), max(th_arr), 100)
        di = np.linspace(min(d_arr), max(d_arr), 100)
        TT, DD = np.meshgrid(ti, di)
        
        from scipy.interpolate import griddata
        try:
            PP = griddata((th_arr, d_arr), pr_arr, (TT, DD), method='cubic', fill_value=0.0)
        except Exception:
            PP = griddata((th_arr, d_arr), pr_arr, (TT, DD), method='nearest', fill_value=0.0)
        
        vmin, vmax = min(pr_arr), max(pr_arr)
        norm = TwoSlopeNorm(vmin=min(vmin, -0.01), vcenter=0.0, vmax=max(vmax, 0.01))
        
        contour = ax.contourf(TT, DD, PP, levels=50, cmap='RdBu_r', norm=norm)
        cbar = fig.colorbar(contour, ax=ax)
        cbar.set_label("Casimir Pressure $P$ (Pa)")
        
        ax.contour(TT, DD, PP, levels=[0.0], colors='black', linewidths=2.5, linestyles='--')
        ax.scatter(th_arr, d_arr, c='black', s=20, alpha=0.6, label='3D FDTD Grid Points')
        
        ax.set_xlabel("Twist Angle $\\theta$ (degrees)")
        ax.set_ylabel("Separation Distance $d$ (nm)")
        ax.set_title("Pair 2: 2D Phase Diagram $P(\\theta, d)$ ($\\alpha = 60^\\circ$)")
        ax.legend(loc='lower left', frameon=True)
        plt.tight_layout()
        fig2_2d_path = os.path.join(out_fig_dir, "pair2_theta_d_2d.png")
        fig.savefig(fig2_2d_path, dpi=300)
        plt.close(fig)
        print(f"Saved 2D heatmap: {fig2_2d_path}")

    # ==================================================
    # PAIR 3: (alpha, d) at fixed theta = 91.1 deg
    # ==================================================
    print("\nProcessing Pair 3: (alpha, d) Phase Space...")
    p3_data = [r for r in data_list if abs(r["theta_deg"] - 91.1) < 1.0 or abs(r["theta_deg"] - 90.0) < 0.5]
    
    # 1D Line Graph for Pair 3: P(d) for various alpha
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    alphas = sorted(list(set(r["alpha_deg"] for r in p3_data)))
    colors = plt.cm.magma(np.linspace(0.1, 0.9, max(1, len(alphas))))
    
    for idx, a in enumerate(alphas):
        pts = sorted([r for r in p3_data if abs(r["alpha_deg"] - a) < 0.5], key=lambda x: x["d_um"])
        if pts:
            d_vals = [r["d_um"] * 1000.0 for r in pts] # convert to nm
            p_vals = [r["pressure_Pa"] for r in pts]
            ax.plot(d_vals, p_vals, '^--', label=f"Wall Slope $\\alpha = {a}^\\circ$", color=colors[idx], linewidth=2, markersize=6)
            
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5, label='Zero-Pressure Boundary ($P=0$)')
    ax.set_xlabel("Separation Distance $d$ (nm)")
    ax.set_ylabel("Consolidated Casimir Pressure $P$ (Pa)")
    ax.set_title("Pair 3: Force-Distance Curves $P(d)$ vs. Wall Slope $\\alpha$ ($\\theta \\approx 91.1^\\circ$)")
    ax.legend(loc='best', frameon=True)
    plt.tight_layout()
    fig3_path = os.path.join(out_fig_dir, "pair3_alpha_d_1d.png")
    fig.savefig(fig3_path, dpi=300)
    plt.close(fig)
    print(f"Saved 1D plot: {fig3_path}")

    # 2D Contour Heatmap for Pair 3: (alpha, d) Phase Diagram
    if len(p3_data) >= 4:
        fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
        al_arr = np.array([r["alpha_deg"] for r in p3_data])
        d_arr = np.array([r["d_um"] * 1000.0 for r in p3_data])
        pr_arr = np.array([r["pressure_Pa"] for r in p3_data])
        
        ai = np.linspace(min(al_arr), max(al_arr), 100)
        di = np.linspace(min(d_arr), max(d_arr), 100)
        AA, DD = np.meshgrid(ai, di)
        
        from scipy.interpolate import griddata
        try:
            PP = griddata((al_arr, d_arr), pr_arr, (AA, DD), method='cubic', fill_value=0.0)
        except Exception:
            PP = griddata((al_arr, d_arr), pr_arr, (AA, DD), method='nearest', fill_value=0.0)
        
        vmin, vmax = min(pr_arr), max(pr_arr)
        norm = TwoSlopeNorm(vmin=min(vmin, -0.01), vcenter=0.0, vmax=max(vmax, 0.01))
        
        contour = ax.contourf(AA, DD, PP, levels=50, cmap='RdBu_r', norm=norm)
        cbar = fig.colorbar(contour, ax=ax)
        cbar.set_label("Casimir Pressure $P$ (Pa)")
        
        ax.contour(AA, DD, PP, levels=[0.0], colors='black', linewidths=2.5, linestyles='--')
        ax.scatter(al_arr, d_arr, c='black', s=20, alpha=0.6, label='3D FDTD Grid Points')
        
        ax.set_xlabel("Corrugation Wall Slope $\\alpha$ (degrees)")
        ax.set_ylabel("Separation Distance $d$ (nm)")
        ax.set_title("Pair 3: 2D Phase Diagram $P(\\alpha, d)$ ($\\theta \\approx 91.1^\\circ$)")
        ax.legend(loc='lower left', frameon=True)
        plt.tight_layout()
        fig3_2d_path = os.path.join(out_fig_dir, "pair3_alpha_d_2d.png")
        fig.savefig(fig3_2d_path, dpi=300)
        plt.close(fig)
        print(f"Saved 2D heatmap: {fig3_2d_path}")

    # ==================================================
    # Generate Formatted LaTeX Tables for all 3 Pairs
    # ==================================================
    print("\nGenerating formatted LaTeX data tables for master report...")
    
    # Table 1: Pair 1 (theta, alpha) Data Table
    t1_tex = """\\begin{table}[h!]
\\centering
\\caption{Pair 1 Pairwise Analysis: Consolidated Casimir Pressure $P(\\theta, \\alpha)$ across Twist Angle $\\theta$ and Corrugation Wall Slope $\\alpha$ at fixed separation $d = 100$ nm ($L=2.0\\ \\mu\\text{m}$, $N=3$).}
\\begin{tabular}{cccc}
\\hline
\\textbf{Twist Angle $\\theta$} & \\textbf{Wall Slope $\\alpha$} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Physical Regime} \\\\
\\hline
"""
    for r in sorted(p1_data, key=lambda x: (x["alpha_deg"], x["theta_deg"])):
        reg = "\\textbf{REPULSIVE ($P>0$)}" if r["is_repulsive"] else "Attractive ($P<0$)"
        t1_tex += f"${r['theta_deg']:.1f}^\\circ$ & ${r['alpha_deg']:.1f}^\\circ$ & ${r['pressure_Pa']:+.6f}$ & {reg} \\\\\n"
    t1_tex += """\\hline
\\end{tabular}
\\end{table}
"""

    # Table 2: Pair 2 (theta, d) Data Table
    t2_tex = """\\begin{table}[h!]
\\centering
\\caption{Pair 2 Pairwise Analysis: Consolidated Casimir Pressure $P(\\theta, d)$ across Twist Angle $\\theta$ and Separation Distance $d$ at fixed wall slope $\\alpha = 60^\\circ$ ($L=2.0\\ \\mu\\text{m}$, $N=3$).}
\\begin{tabular}{cccc}
\\hline
\\textbf{Twist Angle $\\theta$} & \\textbf{Separation $d$ (nm)} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Physical Regime} \\\\
\\hline
"""
    for r in sorted(p2_data, key=lambda x: (x["theta_deg"], x["d_um"])):
        reg = "\\textbf{REPULSIVE ($P>0$)}" if r["is_repulsive"] else "Attractive ($P<0$)"
        t2_tex += f"${r['theta_deg']:.1f}^\\circ$ & ${r['d_um']*1000.0:.0f}$ nm & ${r['pressure_Pa']:+.6f}$ & {reg} \\\\\n"
    t2_tex += """\\hline
\\end{tabular}
\\end{table}
"""

    # Table 3: Pair 3 (alpha, d) Data Table
    t3_tex = """\\begin{table}[h!]
\\centering
\\caption{Pair 3 Pairwise Analysis: Consolidated Casimir Pressure $P(\\alpha, d)$ across Corrugation Wall Slope $\\alpha$ and Separation Distance $d$ at fixed twist angle $\\theta = 91.1^\\circ$ ($L=2.0\\ \\mu\\text{m}$, $N=3$).}
\\begin{tabular}{cccc}
\\hline
\\textbf{Wall Slope $\\alpha$} & \\textbf{Separation $d$ (nm)} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Physical Regime} \\\\
\\hline
"""
    for r in sorted(p3_data, key=lambda x: (x["alpha_deg"], x["d_um"])):
        reg = "\\textbf{REPULSIVE ($P>0$)}" if r["is_repulsive"] else "Attractive ($P<0$)"
        t3_tex += f"${r['alpha_deg']:.1f}^\\circ$ & ${r['d_um']*1000.0:.0f}$ nm & ${r['pressure_Pa']:+.6f}$ & {reg} \\\\\n"
    t3_tex += """\\hline
\\end{tabular}
\\end{table}
"""

    # Save latex tables snippet to scratch
    with open("scratch/pairwise_tables.tex", "w") as f:
        f.write(t1_tex + "\n\n" + t2_tex + "\n\n" + t3_tex)

    print("Saved scratch/pairwise_tables.tex cleanly!")
    print("Done generating all pairwise 1D graphs, 2D heatmaps, and LaTeX tables!")

if __name__ == "__main__":
    main()
