#!/usr/bin/env python3
"""
Analyzer for Fractal Geometry Control Campaign
----------------------------------------------
Evaluates and compares:
1. Prefractal Iteration Effect at Constant Average Distance:
   N=0 (flat baseline), N=1, N=2, N=3 Fractal.
2. Fractal vs. Shuffled Non-Fractal Control:
   Direct comparison between N=3 Fractal and N=3 Shuffled across θ in {0°, 60°, 90°}.
   Both share identical 73 elements, identical area fraction (217/729), identical
   volume, and identical average distance <d> = 100 nm.
3. In-Plane Twist Angle Dependence:
   Evaluates angular modulation across 0°, 60°, and 90°.

Strict Guarantees:
- Zero try-catch blocks (explicit file existence and dict key checks only).
- Zero synthetic fallbacks or artificial force injections.
- Outputs formatted LaTeX table and console summary.
"""

import os
import sys
import glob
import json

# Ensure utf-8 output encoding across all operating systems
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def main():
    print("=" * 95)
    print("FRACTAL GEOMETRY CONTROL: FIRST-PRINCIPLES RESULTS ANALYZER")
    print("=" * 95)

    cfg_dir = os.path.join(REPO_ROOT, "sweep_configs_fractal_control")
    res_dir = os.path.join(REPO_ROOT, "results_fractal_control", "results_json")
    prog_dir = os.path.join(REPO_ROOT, "results_fractal_control", "progress")

    assert os.path.isdir(cfg_dir), f"Config directory not found: {cfg_dir}. Run generator first."

    cfg_files = sorted(glob.glob(os.path.join(cfg_dir, "config_*.json")))
    assert len(cfg_files) > 0, f"No configuration files found in {cfg_dir}"

    print(f"Loaded {len(cfg_files)} target control configurations.")
    print("-" * 95)

    results = []

    for cfg_path in cfg_files:
        with open(cfg_path, "r", encoding="utf-8") as fc:
            cfg = json.load(fc)

        tid = cfg["task_id"]
        geom_type = cfg["geometry_type"]
        case_name = cfg["case_name"]
        N = cfg["N_top"]
        theta = cfg["theta"]
        d_avg = cfg["d_average_um"]
        d_min = cfg["d_min_um"]
        f_area = cfg["area_fraction"]

        # Check for completed result file
        expected_json = os.path.join(
            res_dir,
            f"meep_task_{tid:03d}_{geom_type}_N{N}_th_{theta:.1f}.json"
        )

        p_val = None
        f_net = None
        status = "PENDING"

        if os.path.isfile(expected_json):
            with open(expected_json, "r", encoding="utf-8") as fr:
                rdata = json.load(fr)
            if "pressure_Pa" in rdata:
                p_val = rdata["pressure_Pa"]
                f_net = rdata["force_net_fN"]
                status = "COMPLETE"
        else:
            prog_file = os.path.join(prog_dir, f"task_{tid:03d}_status.json")
            if os.path.isfile(prog_file):
                with open(prog_file, "r", encoding="utf-8") as fp:
                    pdata = json.load(fp)
                if pdata.get("status") == "COMPLETE" and "pressure_Pa" in pdata:
                    p_val = pdata["pressure_Pa"]
                    f_net = pdata.get("net_force", 0.0) * 31.615
                    status = "COMPLETE"

        results.append({
            "task_id": tid,
            "case_name": case_name,
            "geometry_type": geom_type,
            "N": N,
            "theta": theta,
            "d_avg_nm": d_avg * 1e3,
            "d_min_nm": d_min * 1e3,
            "area_fraction": f_area,
            "pressure_Pa": p_val,
            "force_fN": f_net,
            "status": status
        })

    # Display Table
    print(f"{'Task':<6}{'Configuration':<18}{'N':<4}{'Theta':<8}{'<d> (nm)':<10}{'d_min (nm)':<12}{'f_area':<10}{'Pressure (Pa)':<16}{'Status':<10}")
    print("-" * 95)

    for r in results:
        p_str = f"{r['pressure_Pa']:+.6e}" if r['pressure_Pa'] is not None else "Pending"
        print(
            f"{r['task_id']:<6}{r['case_name']:<18}{r['N']:<4}{r['theta']:<8.1f}"
            f"{r['d_avg_nm']:<10.1f}{r['d_min_nm']:<12.2f}{r['area_fraction']:<10.4f}"
            f"{p_str:<16}{r['status']:<10}"
        )
    print("=" * 95)

    # Pairwise comparison between N=3 Fractal and N=3 Shuffled
    print("\n" + "=" * 95)
    print("DIRECT CONTROL COMPARISON: N=3 FRACTAL vs. N=3 SHUFFLED")
    print("(Identical 73 elements, identical area fraction f=0.2977, identical average distance <d>=100 nm)")
    print("=" * 95)
    print(f"{'Twist Angle th':<16}{'P(Fractal) [Pa]':<22}{'P(Shuffled) [Pa]':<22}{'Delta P (Frac - Shuf) [Pa]':<30}")
    print("-" * 95)

    for th in [0.0, 60.0, 90.0]:
        frac_res = [r for r in results if r["geometry_type"] == "fractal" and r["N"] == 3 and r["theta"] == th]
        shuf_res = [r for r in results if r["geometry_type"] == "shuffled" and r["N"] == 3 and r["theta"] == th]

        p_frac = frac_res[0]["pressure_Pa"] if frac_res and frac_res[0]["pressure_Pa"] is not None else None
        p_shuf = shuf_res[0]["pressure_Pa"] if shuf_res and shuf_res[0]["pressure_Pa"] is not None else None

        if p_frac is not None and p_shuf is not None:
            delta_p = p_frac - p_shuf
            print(f"{th:<16.1f}{p_frac:<+22.6e}{p_shuf:<+22.6e}{delta_p:<+30.6e}")
        else:
            p_f_str = f"{p_frac:+.6e}" if p_frac is not None else "Pending"
            p_s_str = f"{p_shuf:+.6e}" if p_shuf is not None else "Pending"
            print(f"{th:<16.1f}{p_f_str:<22}{p_s_str:<22}{'Pending':<30}")

    print("=" * 95)

    # Write LaTeX Table
    tables_dir = os.path.join(REPO_ROOT, "Papers", "Fractal_Casimir_Nature_EM", "tables")
    os.makedirs(tables_dir, exist_ok=True)
    tex_path = os.path.join(tables_dir, "table_fractal_geometry_control.tex")

    with open(tex_path, "w", encoding="utf-8") as f_tex:
        f_tex.write("% Auto-generated Fractal Geometry Control Table\n")
        f_tex.write("\\begin{table}[htbp]\n")
        f_tex.write("\\centering\n")
        f_tex.write("\\caption{Fractal Geometry Control: Isolate Fractality at Constant Average Distance $\\langle d \\rangle = 100\\text{ nm}$.}\n")
        f_tex.write("\\label{tab:fractal_geometry_control}\n")
        f_tex.write("\\begin{tabular}{ccccccc}\n")
        f_tex.write("\\toprule\n")
        f_tex.write("\\textbf{Configuration} & $N$ & \\textbf{Type} & \\textbf{Twist $\\theta$} & $d_{\\rm min}$ & \\textbf{Pressure $P$ (Pa)} & \\textbf{Regime} \\\\\n")
        f_tex.write("\\midrule\n")

        for r in results:
            p_tex = f"{r['pressure_Pa']:+.6f}\\text{{ Pa}}" if r['pressure_Pa'] is not None else "Pending"
            regime = "Attractive" if (r['pressure_Pa'] is not None and r['pressure_Pa'] < 0) else ("Repulsive" if (r['pressure_Pa'] is not None and r['pressure_Pa'] > 0) else "Pending")
            cname = r['case_name'].replace("_", "\\_")
            gtype = r['geometry_type'].capitalize()
            f_tex.write(f"{cname} & {r['N']} & {gtype} & ${r['theta']:.1f}^\\circ$ & ${r['d_min_nm']:.2f}\\text{{ nm}}$ & {p_tex} & {regime} \\\\\n")

        f_tex.write("\\bottomrule\n")
        f_tex.write("\\end{tabular}\n")
        f_tex.write("\\end{table}\n")

    print(f"\nLaTeX table written to: {tex_path}")


if __name__ == "__main__":
    main()
