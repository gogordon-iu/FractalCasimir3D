#!/usr/bin/env python3
"""
Phase 1 Analyzer: Fundamental Casimir Baselines & Scaling Laws (28 Tasks)
------------------------------------------------------------------------
Inspects Phase 1 simulation results:
- Planar Gold and Silicon baselines (N=1,2,3)
- Lifshitz 1/d^4 distance scaling
- Sierpinski (8/9)^(N-1) fractal area law
- Anisotropic twist angle theta on flat plates

Works in pure Python without requiring numpy or external dependencies!
"""

import os
import sys
import glob
import json
import math

# Auto-detect and switch to meep conda environment if available
try:
    import numpy as np
except ImportError:
    candidates = [
        os.path.expanduser("~/.conda/envs/meep/bin/python"),
        "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python",
        os.path.expanduser("~/miniconda3/envs/meep/bin/python"),
        os.path.expanduser("~/anaconda3/envs/meep/bin/python"),
        "/N/soft/rhel8/miniconda3/envs/meep/bin/python"
    ]
    for candidate in candidates:
        if os.path.exists(candidate) and sys.executable != candidate:
            print(f"[Auto-Env] Switching to MEEP environment: {candidate}")
            os.execv(candidate, [candidate] + sys.argv)
    np = None

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def linear_fit(x_arr, y_arr):
    n = len(x_arr)
    if n < 2:
        return 0.0, 0.0
    mean_x = sum(x_arr) / n
    mean_y = sum(y_arr) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_arr, y_arr))
    var = sum((x - mean_x)**2 for x in x_arr)
    slope = cov / var if var != 0 else 0.0
    intercept = mean_y - slope * mean_x
    return slope, intercept

def main():
    print("================================================================================")
    print("PHASE 1 RESULTS ANALYZER: GENERAL PARAMETERS & FUNDAMENTAL BASELINES")
    print("================================================================================")

    config_files = sorted(glob.glob("sweep_configs_phase1/config_*.json"))
    print(f"Loaded {len(config_files)} Phase 1 target task configurations.")

    target_files = sorted(set(glob.glob(".tmp/meep_*.json")))
    print(f"Scanning {len(target_files)} simulation result files...")
    raw_records = []
    for fp in target_files:
        try:
            with open(fp, "r") as f:
                d = json.load(f)
                if isinstance(d, dict) and "d_um" in d:
                    raw_records.append(d)
        except Exception:
            pass

    # Match each Phase 1 config to available results
    matched = []
    for cfg_path in config_files:
        with open(cfg_path) as f:
            cfg = json.load(f)
        d_tgt = cfg["d"]
        N_tgt = cfg["N_top"]
        mat_tgt = cfg["material"]
        th_tgt = cfg["theta"]
        eps_tgt = cfg["eps_bg"]
        L_tgt = cfg["L"]
        corr_tgt = cfg["corrugated"]

        best_match = None
        best_score = -1
        for r in raw_records:
            # Verify corrugation flag
            is_corr = bool(r.get("corrugated", False)) or float(r.get("corrugation_angle", r.get("alpha_deg", 0.0))) > 0.0
            if is_corr != corr_tgt:
                continue

            # Verify bottom plate generation
            n_bot_r = int(r.get("N_bottom", r.get("N_bot", 1)))
            if n_bot_r != int(cfg.get("N_bot", 1)):
                continue

            if (round(float(r.get("d_um", r.get("d", -1))), 4) == round(d_tgt, 4) and
                int(r.get("N", r.get("N_top", -1))) == N_tgt and
                r.get("material") == mat_tgt and
                round(float(r.get("theta_deg", r.get("theta", -1))), 1) == round(th_tgt, 1) and
                round(float(r.get("eps_bg", -1)), 1) == round(eps_tgt, 1) and
                round(float(r.get("L", -1)), 2) == round(L_tgt, 2)):
                
                # Scoring: prioritize exact task_idx match and highest resolution
                score = 0
                if r.get("task_idx") == cfg["task_id"]:
                    score += 1000
                res_r = int(r.get("resolution", 0))
                if res_r == cfg.get("resolution", 40):
                    score += 200
                else:
                    score += res_r
                
                if score > best_score:
                    best_score = score
                    best_match = r

        p_val = None
        if best_match:
            f_both = best_match.get("force_both")
            f_self = best_match.get("force_self")
            p_dir = best_match.get("pressure_Pa")
            if f_both is not None and f_self is not None:
                A_eff = get_effective_area(N_tgt, L_tgt)
                p_val = (float(f_both) - float(f_self)) / A_eff
            elif p_dir is not None:
                p_val = float(p_dir)

        matched.append({
            "task_id": cfg["task_id"],
            "label": cfg["label"],
            "tier": cfg["tier"],
            "material": mat_tgt,
            "N": N_tgt,
            "d_um": d_tgt,
            "theta_deg": th_tgt,
            "eps_bg": eps_tgt,
            "L": L_tgt,
            "pressure_Pa": p_val,
            "status": "COMPLETED" if p_val is not None else "PENDING"
        })

    completed = [m for m in matched if m["status"] == "COMPLETED"]
    print(f"Phase 1 Status: {len(completed)} / {len(matched)} tasks completed.")

    for m in matched:
        p_str = f"{m['pressure_Pa']:+9.6f} Pa" if m["pressure_Pa"] is not None else "Pending / Running"
        regime = ("REPULSIVE" if m["pressure_Pa"] > 0 else "Attractive") if m["pressure_Pa"] is not None else "---"
        print(f"  Task {m['task_id']:02d}: {m['label']:<60} | P = {p_str} | {regime}")

    # 1. Lifshitz Distance Power Law Check
    lifshitz = [m for m in completed if m["tier"] == "tier1_lifshitz_scaling"]
    valid_lifshitz = [m for m in lifshitz if m["pressure_Pa"] is not None and abs(m["pressure_Pa"]) > 1e-12 and m["d_um"] > 0]
    if len(valid_lifshitz) >= 2:
        d_vals = [m["d_um"] for m in valid_lifshitz]
        p_vals = [abs(m["pressure_Pa"]) for m in valid_lifshitz]
        log_d = [math.log(x) for x in d_vals]
        log_p = [math.log(x) for x in p_vals]
        slope, intercept = linear_fit(log_d, log_p)
        print(f"\n* Lifshitz Distance Scaling: Fitted |P(d)| ~ d^({slope:.2f}) [Theory: d^-4.00, points: {len(valid_lifshitz)}/{len(lifshitz)}]")
    else:
        print("\n* Lifshitz Distance Scaling: Awaiting completed non-zero distance datapoints.")

    # 2. Fractal Area Law Check
    area_tasks = [m for m in completed if m["tier"] == "tier1_fractal_area_law"]
    valid_area = [m for m in area_tasks if m["pressure_Pa"] is not None and abs(m["pressure_Pa"]) > 1e-12]
    if len(valid_area) >= 2:
        valid_area.sort(key=lambda x: x["N"])
        p_first = abs(valid_area[0]["pressure_Pa"])
        p_last = abs(valid_area[-1]["pressure_Pa"])
        ratio = p_last / p_first if p_first > 1e-12 else 0.0
        print(f"* Fractal Area Law Scaling: N={valid_area[0]['N']} to {valid_area[-1]['N']} Ratio = {ratio:.4f} [Theory: (8/9)^(N-1)]")
    else:
        print("* Fractal Area Law Scaling: Awaiting completed non-zero fractal generation datapoints.")

    # Write LaTeX Table
    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)
    tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_phase1_baselines.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated Phase 1 Casimir Baselines Table\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write("\\caption{Phase 1: Fundamental Casimir Baselines and Scaling Laws ($d=100\\text{ nm}$, uncorrugated).}\n")
        f.write("\\label{tab:phase1_baselines}\n")
        f.write("\\begin{tabular}{ccccc}\n\\toprule\n")
        f.write("\\textbf{Material} & \\textbf{Prefractal $N$} & \\textbf{Twist $\\theta$} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Physical Regime} \\\\\n\\midrule\n")
        for m in matched[:15]:
            p_str = f"${m['pressure_Pa']:+9.6f}$ Pa" if m["pressure_Pa"] is not None else "Pending"
            reg_str = ("\\textbf{REPULSIVE}" if m["pressure_Pa"] > 0 else "Attractive") if m["pressure_Pa"] is not None else "Pending"
            f.write(f"{m['material']} & $N={m['N']}$ & ${m['theta_deg']:.1f}^\\circ$ & {p_str} & {reg_str} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"\nGenerated Phase 1 Table: '{tex_path}'.")

    # Save summary JSON
    os.makedirs("results_phase1", exist_ok=True)
    with open("results_phase1/phase1_summary.json", "w") as f:
        json.dump(matched, f, indent=4)
    print("Saved Phase 1 summary to 'results_phase1/phase1_summary.json'.")
    print("================================================================================")

if __name__ == "__main__":
    main()
