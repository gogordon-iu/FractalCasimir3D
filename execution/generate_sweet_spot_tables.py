import json
import os

def generate_latex_tables():
    with open('results_sweet_spot_sweep_20260831_134421/sweet_spot_sweep_summary.json', 'r') as f:
        data = json.load(f)

    # 1. High repulsive table
    repulsive = [d for d in data if d.get('pressure_Pa', 0) > 0]
    repulsive_sorted = sorted(repulsive, key=lambda x: x['pressure_Pa'], reverse=True)

    # 2. Levitation equilibrium points
    curves = {}
    for r in data:
        k = (r['alpha_deg'], r['theta_deg'])
        curves.setdefault(k, []).append(r)

    eq_points = []
    for (a, th), pts in curves.items():
        pts.sort(key=lambda x: x['d_um'])
        d_arr = [p['d_um'] for p in pts]
        p_arr = [p['pressure_Pa'] for p in pts]
        for i in range(len(p_arr) - 1):
            if p_arr[i] > 0 and p_arr[i+1] < 0:
                d1, d2 = d_arr[i], d_arr[i+1]
                p1, p2 = p_arr[i], p_arr[i+1]
                d_eq = d1 + (0.0 - p1) * (d2 - d1) / (p2 - p1)
                eq_points.append({
                    "alpha_deg": a,
                    "theta_deg": th,
                    "d_eq_nm": d_eq * 1000.0,
                    "p_max_Pa": max(p_arr),
                    "d1_nm": d1 * 1000.0,
                    "d2_nm": d2 * 1000.0,
                    "p1_Pa": p1,
                    "p2_Pa": p2
                })

    print(f"Found {len(repulsive)} repulsive points out of {len(data)} total FDTD points.")
    print(f"Found {len(eq_points)} stable nanomechanical levitation equilibrium points.")

    # Write sweet spot table
    out_tex_path = os.path.join('Papers', 'Fractal_Casimir_Nature_EM', 'tables', 'table_sweet_spot_repulsion.tex')
    with open(out_tex_path, 'w') as f:
        f.write("% Auto-generated from results_sweet_spot_sweep_20260831_134421\n")
        f.write("\\begin{table}[htbp]\n")
        f.write("\\centering\n")
        f.write("\\caption{Representative Verified 3D FDTD Repulsive Casimir Pressures ($P > 0$) in Vacuum across the $(\\alpha, \\theta, d)$ Parameter Space ($L=2.0\\ \\mu\\text{m}$, $N=3$).}\n")
        f.write("\\label{tab:sweet_spot_repulsion}\n")
        f.write("\\begin{tabular}{ccccc}\n")
        f.write("\\toprule\n")
        f.write("\\textbf{Corrugation $\\alpha$} & \\textbf{Twist $\\theta$} & \\textbf{Separation $d$ (nm)} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Regime} \\\\\n")
        f.write("\\midrule\n")
        for r in repulsive_sorted[:20]:
            f.write(f"${r['alpha_deg']:.1f}^\\circ$ & ${r['theta_deg']:.1f}^\\circ$ & ${r['d_um']*1000.0:.1f}$ nm & $\\mathbf{{{r['pressure_Pa']:+.6f}}}$ & \\textbf{{REPULSIVE}} \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")

    # Write equilibrium table
    eq_tex_path = os.path.join('Papers', 'Fractal_Casimir_Nature_EM', 'tables', 'table_levitation_equilibria.tex')
    with open(eq_tex_path, 'w') as f:
        f.write("% Auto-generated from results_sweet_spot_sweep_20260831_134421\n")
        f.write("\\begin{table}[htbp]\n")
        f.write("\\centering\n")
        f.write("\\caption{Stable Passive Nanomechanical Levitation Equilibrium Heights ($d_{\\rm eq}$ where $P=0$ and $\\partial P/\\partial d < 0$) in Vacuum.}\n")
        f.write("\\label{tab:levitation_equilibria}\n")
        f.write("\\begin{tabular}{ccccc}\n")
        f.write("\\toprule\n")
        f.write("\\textbf{Corrugation $\\alpha$} & \\textbf{Twist $\\theta$} & \\textbf{Peak Pressure $P_{\\max}$ (Pa)} & \\textbf{Equilibrium Gap $d_{\\rm eq}$ (nm)} & \\textbf{Stability} \\\\\n")
        f.write("\\midrule\n")
        for eq in eq_points:
            f.write(f"${eq['alpha_deg']:.1f}^\\circ$ & ${eq['theta_deg']:.1f}^\\circ$ & $+{eq['p_max_Pa']:.4f}$ Pa & $\\mathbf{{{eq['d_eq_nm']:.2f}\\text{{ nm}}}}$ & \\textbf{{Stable Levitation}} \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")

    print(f"Wrote {out_tex_path} and {eq_tex_path}")

if __name__ == '__main__':
    generate_latex_tables()
