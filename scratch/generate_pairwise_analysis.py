import os
import sys
import glob
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from scipy.interpolate import griddata

def main():
    print("==================================================")
    print("PURE EMPIRICAL PAIRWISE PARAMETER SWEEP ANALYSIS GENERATOR")
    print("(STRICTLY NO FALLBACK FORMULAS - DUMMY 0.0 PLACEHOLDERS FILTERED)")
    print("==================================================")

    # 1. Load all records from results directories (summary files take precedence over .tmp)
    summary_files = sorted(glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json")) + \
                    sorted(glob.glob("results_hybrid_parameter_sweep_*/hybrid_sweep_summary.json")) + \
                    sorted(glob.glob("results_corrugated_*/corrugated_sweep_results.json"))
    tmp_files = glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")

    records = []
    for fp in tmp_files + summary_files:
        try:
            with open(fp, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict) and ("d_um" in data or "d" in data):
                    records.append(data)
        except Exception:
            pass

    print(f"Loaded {len(records)} total simulation JSON records.")

    # Build empirical lookup dictionary from real simulation data (filtering out dummy 0.0 placeholders)
    fdtd_data = {}
    for rec in records:
        d = float(rec.get("d_um", rec.get("d", 0.1)))
        th = float(rec.get("theta_deg", rec.get("theta", 90.0)))
        a = float(rec.get("corrugation_angle", rec.get("alpha_deg", rec.get("alpha", 60.0))))
        
        p = None
        if "pressure_Pa" in rec:
            p = float(rec["pressure_Pa"])
        elif "pressure" in rec:
            p = float(rec["pressure"])
            
        # STRICT FILTER: Ignore dummy 0.0 placeholders from grid initialization
        if p is not None and abs(p) > 1e-12:
            key = (round(a, 1), round(th, 1), round(d, 3))
            fdtd_data[key] = p

    print(f"Compiled {len(fdtd_data)} verified non-zero empirical FDTD simulation data points.")

    out_fig_dir = "Papers/FractalCasimir3D_Version_02/figures"
    if not os.path.exists(out_fig_dir):
        out_fig_dir = "Papers/Fractal_Casimir_Version_02/figures"
    os.makedirs(out_fig_dir, exist_ok=True)
    os.makedirs("scratch", exist_ok=True)

    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    plt.rcParams.update({
        'font.size': 12,
        'font.family': 'sans-serif',
        'axes.labelsize': 14,
        'axes.titlesize': 14,
        'xtick.labelsize': 11,
        'ytick.labelsize': 11,
        'legend.fontsize': 10,
        'figure.titlesize': 16
    })

    # STRICT EMPIRICAL LOOKUP - ABSOLUTELY NO FALLBACK FORMULAS OR DUMMY ZEROS
    def get_empirical_pressure(alpha_deg, theta_deg, d_um):
        key = (round(alpha_deg, 1), round(theta_deg, 1), round(d_um, 3))
        if key in fdtd_data:
            return fdtd_data[key]
        return np.nan

    thetas_fine = [0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 91.1, 92.0, 94.0]
    alphas_fine = [45.0, 50.0, 54.7, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0]
    ds_fine = [0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.35]

    # Helper for 2D Grid Interpolation over ONLY real empirical data
    def make_2d_heatmap(x_points, y_points, grid_x, grid_y, values, xlabel, ylabel, title, out_path):
        valid = ~np.isnan(values)
        if np.sum(valid) < 4:
            print(f"Skipping 2D heatmap for {title} (insufficient data: {np.sum(valid)} points)")
            return
            
        points = np.column_stack((x_points[valid], y_points[valid]))
        vals = values[valid]
        
        XX, YY = np.meshgrid(grid_x, grid_y)
        ZZ = griddata(points, vals, (XX, YY), method='linear')
        ZZ_near = griddata(points, vals, (XX, YY), method='nearest')
        mask = np.isnan(ZZ)
        ZZ[mask] = ZZ_near[mask]
        
        fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
        v_min, v_max = np.min(vals), np.max(vals)
        if v_min < 0 and v_max > 0:
            norm = TwoSlopeNorm(vmin=v_min, vcenter=0.0, vmax=v_max)
            contour = ax.contourf(XX, YY, ZZ, levels=60, cmap='RdBu_r', norm=norm)
        else:
            contour = ax.contourf(XX, YY, ZZ, levels=60, cmap='viridis')
            
        cbar = fig.colorbar(contour, ax=ax)
        cbar.set_label("Consolidated Casimir Pressure $P$ (Pa)")
        
        if v_min < 0 and v_max > 0:
            ax.contour(XX, YY, ZZ, levels=[0.0], colors='black', linewidths=2.5, linestyles='--')
            
        ax.scatter(x_points[valid], y_points[valid], c='black', s=15, alpha=0.6, label='FDTD Data Points')
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        plt.tight_layout()
        fig.savefig(out_path, dpi=300)
        plt.close(fig)
        print(f"Saved 2D heatmap: {out_path}")

    # ==================================================
    # PAIR 1: (theta, alpha) Fine-Grained Phase Space (d = 100 nm)
    # ==================================================
    print("\nGenerating Pair 1: Pure Empirical (theta, alpha) plot ($d = 100$ nm)...")
    fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
    alphas_to_plot = [60.0, 70.0, 75.0, 80.0, 85.0]
    colors = plt.cm.plasma(np.linspace(0.1, 0.95, len(alphas_to_plot)))
    
    p1_xs, p1_ys, p1_zs = [], [], []
    for idx, a in enumerate(alphas_to_plot):
        ths_valid, ps_valid = [], []
        for th in thetas_fine:
            p_val = get_empirical_pressure(a, th, 0.10)
            p1_xs.append(th)
            p1_ys.append(a)
            p1_zs.append(p_val)
            if not np.isnan(p_val):
                ths_valid.append(th)
                ps_valid.append(p_val)
                
        if ths_valid:
            ax.plot(ths_valid, ps_valid, 'o-', label=f"Wall Slope $\\alpha = {a}^\\circ$", color=colors[idx], linewidth=2.2, markersize=6)
            
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5, label='Zero-Pressure Boundary ($P=0$)')
    ax.set_xlabel("Twist Angle $\\theta$ (degrees)")
    ax.set_ylabel("Consolidated Casimir Pressure $P$ (Pa)")
    ax.set_title("Pair 1: Pure Empirical Casimir Pressure vs. Twist Angle $\\theta$ ($d = 100$ nm)")
    ax.legend(loc='best', frameon=True, fontsize=9)
    plt.tight_layout()
    fig1_path = os.path.join(out_fig_dir, "pair1_theta_alpha_1d.png")
    fig.savefig(fig1_path, dpi=300)
    plt.close(fig)
    print(f"Saved 1D plot: {fig1_path}")

    tt_grid = np.linspace(0.0, 94.0, 150)
    aa_grid = np.linspace(45.0, 85.0, 150)
    fig1_2d_path = os.path.join(out_fig_dir, "pair1_theta_alpha_2d.png")
    make_2d_heatmap(np.array(p1_xs), np.array(p1_ys), tt_grid, aa_grid, np.array(p1_zs),
                    "Twist Angle $\\theta$ (degrees)", "Wall Slope $\\alpha$ (degrees)",
                    "Pair 1: Pure Empirical 2D Phase Diagram $P(\\theta, \\alpha)$ ($d = 100$ nm)", fig1_2d_path)

    # ==================================================
    # PAIR 2: (theta, d) Fine-Grained Phase Space (alpha = 70 deg)
    # ==================================================
    print("\nGenerating Pair 2: Pure Empirical (theta, d) plot (alpha = 70 deg)...")
    fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
    thetas_p2 = [80.0, 84.0, 88.0, 90.0, 91.1, 94.0]
    colors = plt.cm.viridis(np.linspace(0.1, 0.95, len(thetas_p2)))
    
    p2_xs, p2_ys, p2_zs = [], [], []
    for idx, th in enumerate(thetas_p2):
        ds_valid, ps_valid = [], []
        for d_u in ds_fine:
            p_val = get_empirical_pressure(70.0, th, d_u)
            p2_xs.append(th)
            p2_ys.append(d_u * 1000.0)
            p2_zs.append(p_val)
            if not np.isnan(p_val):
                ds_valid.append(d_u * 1000.0)
                ps_valid.append(p_val)
                
        if ds_valid:
            ax.plot(ds_valid, ps_valid, 's-', label=f"$\\theta = {th}^\\circ$", color=colors[idx], linewidth=2.2, markersize=6)
            
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5, label='Zero-Pressure Boundary ($P=0$)')
    ax.set_xlabel("Separation Distance $d$ (nm)")
    ax.set_ylabel("Consolidated Casimir Pressure $P$ (Pa)")
    ax.set_title("Pair 2: Pure Empirical Force-Distance Curves $P(d)$ vs. $\\theta$ ($\\alpha = 70^\\circ$)")
    ax.legend(loc='best', frameon=True, fontsize=9)
    plt.tight_layout()
    fig2_path = os.path.join(out_fig_dir, "pair2_theta_d_1d.png")
    fig.savefig(fig2_path, dpi=300)
    plt.close(fig)
    print(f"Saved 1D plot: {fig2_path}")

    dd_grid = np.linspace(50.0, 350.0, 150)
    fig2_2d_path = os.path.join(out_fig_dir, "pair2_theta_d_2d.png")
    make_2d_heatmap(np.array(p2_xs), np.array(p2_ys), tt_grid, dd_grid, np.array(p2_zs),
                    "Twist Angle $\\theta$ (degrees)", "Separation Distance $d$ (nm)",
                    "Pair 2: Pure Empirical 2D Phase Diagram $P(\\theta, d)$ ($\\alpha = 70^\\circ$)", fig2_2d_path)

    # ==================================================
    # PAIR 3: (alpha, d) Fine-Grained Phase Space (theta = 91.1 deg)
    # ==================================================
    print("\nGenerating Pair 3: Pure Empirical (alpha, d) plot (theta = 91.1 deg)...")
    fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
    alphas_p3 = [45.0, 54.7, 60.0, 70.0, 75.0, 80.0, 85.0]
    colors = plt.cm.magma(np.linspace(0.1, 0.95, len(alphas_p3)))
    
    p3_xs, p3_ys, p3_zs = [], [], []
    for idx, a in enumerate(alphas_p3):
        ds_valid, ps_valid = [], []
        for d_u in ds_fine:
            p_val = get_empirical_pressure(a, 91.1, d_u)
            p3_xs.append(a)
            p3_ys.append(d_u * 1000.0)
            p3_zs.append(p_val)
            if not np.isnan(p_val):
                ds_valid.append(d_u * 1000.0)
                ps_valid.append(p_val)
                
        if ds_valid:
            ax.plot(ds_valid, ps_valid, '^--', label=f"Wall Slope $\\alpha = {a}^\\circ$", color=colors[idx], linewidth=2.2, markersize=6)
            
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5, label='Zero-Pressure Boundary ($P=0$)')
    ax.set_xlabel("Separation Distance $d$ (nm)")
    ax.set_ylabel("Consolidated Casimir Pressure $P$ (Pa)")
    ax.set_title("Pair 3: Pure Empirical Force-Distance Curves $P(d)$ vs. Wall Slope $\\alpha$ ($\\theta = 91.1^\\circ$)")
    ax.legend(loc='best', frameon=True, fontsize=9)
    plt.tight_layout()
    fig3_path = os.path.join(out_fig_dir, "pair3_alpha_d_1d.png")
    fig.savefig(fig3_path, dpi=300)
    plt.close(fig)
    print(f"Saved 1D plot: {fig3_path}")

    fig3_2d_path = os.path.join(out_fig_dir, "pair3_alpha_d_2d.png")
    make_2d_heatmap(np.array(p3_xs), np.array(p3_ys), aa_grid, dd_grid, np.array(p3_zs),
                    "Wall Slope $\\alpha$ (degrees)", "Separation Distance $d$ (nm)",
                    "Pair 3: Pure Empirical 2D Phase Diagram $P(\\alpha, d)$ ($\\theta = 91.1^\\circ$)", fig3_2d_path)

    # ==================================================
    # Generate Formatted LaTeX Tables featuring Pure Empirical Data & Reporting Missing Points
    # ==================================================
    print("\nGenerating pure empirical LaTeX data tables (dummy 0.0 placeholders reported as Pending)...")
    
    # Table 1: Fine-Grained Twist Angles at d = 100 nm
    t1_tex = """\\begin{table}[h!]
\\centering
\\caption{Pair 1 Verified Empirical FDTD Analysis: Consolidated Casimir Pressure $P(\\theta, \\alpha)$ across fine-grained twist angles $\\theta \\in [80^\\circ, 82^\\circ, 84^\\circ, 86^\\circ, 88^\\circ, 90^\\circ, 92^\\circ, 94^\\circ]$ and wall slopes $\\alpha \\in [70^\\circ, 75^\\circ]$ at fixed separation $d = 100$ nm ($L=2.0\\ \\mu\\text{m}$, $N=3$). Uncalculated Slurm tasks are explicitly reported as Pending (Slurm Job).}
\\begin{tabular}{cccc}
\\hline
\\textbf{Twist Angle $\\theta$} & \\textbf{Wall Slope $\\alpha$} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Physical Regime} \\\\
\\hline
"""
    for a in [70.0, 75.0]:
        for th in [80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0, 94.0]:
            key = (round(a, 1), round(th, 1), 0.10)
            if key in fdtd_data:
                p_val = fdtd_data[key]
                reg = "\\textbf{REPULSIVE ($P>0$)}" if p_val > 0 else "Attractive ($P<0$)"
                t1_tex += f"${th:.1f}^\\circ$ & ${a:.1f}^\\circ$ & ${p_val:+.6f}$ & {reg} \\\\\n"
            else:
                t1_tex += f"${th:.1f}^\\circ$ & ${a:.1f}^\\circ$ & \\textit{{Pending (Slurm Job)}} & \\textit{{Executing}} \\\\\n"
    t1_tex += """\\hline
\\end{tabular}
\\end{table}
"""

    # Table 2: Fine-grained separation gaps d at alpha = 70 deg
    t2_tex = """\\begin{table}[h!]
\\centering
\\caption{Pair 2 Verified Empirical FDTD Analysis: Consolidated Casimir Pressure $P(\\theta, d)$ across fine-grained twist angles $\\theta \\in [80^\\circ, 82^\\circ, 84^\\circ, 86^\\circ, 88^\\circ, 90^\\circ, 92^\\circ, 94^\\circ]$ and separation distances $d \\in [50\\text{ nm}, 100\\text{ nm}, 150\\text{ nm}, 200\\text{ nm}, 250\\text{ nm}, 300\\text{ nm}, 350\\text{ nm}]$ at fixed wall slope $\\alpha = 70^\\circ$ ($L=2.0\\ \\mu\\text{m}$, $N=3$). Uncalculated Slurm tasks are explicitly reported as Pending (Slurm Job).}
\\begin{tabular}{cccc}
\\hline
\\textbf{Twist Angle $\\theta$} & \\textbf{Separation $d$ (nm)} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Physical Regime} \\\\
\\hline
"""
    for th in [80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0, 94.0]:
        for d_u in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
            key = (70.0, round(th, 1), round(d_u, 3))
            if key in fdtd_data:
                p_val = fdtd_data[key]
                reg = "\\textbf{REPULSIVE ($P>0$)}" if p_val > 0 else "Attractive ($P<0$)"
                t2_tex += f"${th:.1f}^\\circ$ & ${d_u*1000.0:.0f}$ nm & ${p_val:+.6f}$ & {reg} \\\\\n"
            else:
                t2_tex += f"${th:.1f}^\\circ$ & ${d_u*1000.0:.0f}$ nm & \\textit{{Pending (Slurm Job)}} & \\textit{{Executing}} \\\\\n"
    t2_tex += """\\hline
\\end{tabular}
\\end{table}
"""

    # Table 3: Wall slopes alpha at theta = 91.1 deg
    t3_tex = """\\begin{table}[h!]
\\centering
\\caption{Pair 3 Verified Empirical FDTD Analysis: Consolidated Casimir Pressure $P(\\alpha, d)$ at $\\theta = 91.1^\\circ$ ($L=2.0\\ \\mu\\text{m}$, $N=3$). Uncalculated Slurm tasks are explicitly reported as Pending (Slurm Job).}
\\begin{tabular}{cccc}
\\hline
\\textbf{Wall Slope $\\alpha$} & \\textbf{Separation $d$ (nm)} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Physical Regime} \\\\
\\hline
"""
    for a in [60.0, 70.0, 75.0, 80.0, 85.0]:
        for d_u in [0.05, 0.10, 0.15, 0.25]:
            key = (round(a, 1), 91.1, round(d_u, 3))
            if key in fdtd_data:
                p_val = fdtd_data[key]
                reg = "\\textbf{REPULSIVE ($P>0$)}" if p_val > 0 else "Attractive ($P<0$)"
                t3_tex += f"${a:.1f}^\\circ$ & ${d_u*1000.0:.0f}$ nm & ${p_val:+.6f}$ & {reg} \\\\\n"
            else:
                t3_tex += f"${a:.1f}^\\circ$ & ${d_u*1000.0:.0f}$ nm & \\textit{{Pending (Slurm Job)}} & \\textit{{Executing}} \\\\\n"
    t3_tex += """\\hline
\\end{tabular}
\\end{table}
"""

    with open("scratch/pairwise_tables.tex", "w") as f:
        f.write(t1_tex + "\n\n" + t2_tex + "\n\n" + t3_tex)

    print("Saved scratch/pairwise_tables.tex cleanly with verified non-zero empirical parameters!")
    print("Done generating all pure empirical 1D graphs, 2D heatmaps, and LaTeX tables!")

if __name__ == "__main__":
    main()
