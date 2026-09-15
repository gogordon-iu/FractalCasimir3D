#!/usr/bin/env python3
"""
Vacuum Casimir Repulsion Campaign: Phase 1 Results Analyzer
------------------------------------------------------------
Analyzes the 36 Phase 1 screening tasks across the 4 symmetry-breaking archetypes:
1. Corrugated Top (N=3) vs. Flat Bottom (N=1)
2. Dual-Scale Multi-Tier Corrugations (N=3 vs. N=2)
3. Perforated Carpet Waveguide Cutoff (N=3 vs. N=1)
4. Orthogonal Ridge Crossing (N=3 vs. N=3, theta ~ 90 deg)

Evaluates first-principles Casimir pressure:
    P = (F_both - F_self) / A_eff
Flags any positive repulsive results (P > 0) without any hardcoded signs or fallbacks.
Generates publication LaTeX tables, comparative figures, and auto-syncs to GitHub.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import glob
import json
import math

# Auto-detect and switch to meep conda environment if numpy or matplotlib is missing
try:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    for candidate in [
        os.path.expanduser("~/.conda/envs/meep/bin/python"),
        "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python",
        os.path.expanduser("~/miniconda3/envs/meep/bin/python"),
        os.path.expanduser("~/anaconda3/envs/meep/bin/python"),
        "/N/soft/rhel8/miniconda3/envs/meep/bin/python"
    ]:
        if os.path.exists(candidate) and sys.executable != candidate:
            print(f"[Auto-Env] Switching from {sys.executable} to MEEP conda environment: {candidate}")
            os.execv(candidate, [candidate] + sys.argv)
    print("ERROR: 'numpy' or 'matplotlib' not found. Please activate the meep environment:")
    print("       conda activate meep")
    sys.exit(1)

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def get_expected_output_path(cfg):
    d = float(cfg["d"])
    N = int(cfg["N_top"])
    N_bot = int(cfg.get("N_bot", 1))
    corr = bool(cfg.get("corrugated", False))
    alpha = float(cfg.get("corrugation_angle", 75.0))
    rtip = float(cfg.get("r_tip_nm", 0.0))
    med = cfg.get("medium", "Vacuum")
    sieve = bool(cfg.get("stepped_sieve", False))
    mat = cfg["material"]
    res = int(cfg.get("resolution", 40))
    theta = float(cfg["theta"])
    eps_bg = float(cfg.get("eps_bg", 1.0))
    L = float(cfg.get("L", 2.0))
    
    rtip_str = f"_rtip_{rtip:.1f}" if (corr and rtip > 0.0) else ""
    med_str = f"_med_{med}" if med and med not in ["Vacuum", "None"] else ""
    nbot_str = f"_corrugated_al_{alpha:.1f}{rtip_str}{med_str}_Nbot_{N_bot}" if corr else (f"_sieve_Nbot_{N_bot}" if sieve else (f"_Nbot_{N_bot}" if N_bot > 1 else ""))
    return f".tmp/meep_d_{d:.4f}_N_{N}{nbot_str}_{mat}_res_{res}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}.json"

def main():
    print("================================================================================")
    print("VACUUM CASIMIR REPULSION ANALYZER: ASYMMETRY & RIDGE CROSSING SCREENING")
    print("================================================================================")

    config_files = sorted(glob.glob("sweep_configs_repulsion/config_*.json"))
    if not config_files:
        config_files = sorted(glob.glob(os.path.join(REPO_ROOT, "sweep_configs_repulsion/config_*.json")))
        
    print(f"Loaded {len(config_files)} target repulsion configurations.")

    matched = []
    for fp in config_files:
        with open(fp, "r") as f:
            cfg = json.load(f)

        expected_fp = get_expected_output_path(cfg)
        p_val = None
        f_sub = None
        f_both = None
        f_self = None

        if os.path.exists(expected_fp):
            try:
                with open(expected_fp, "r") as out_f:
                    data = json.load(out_f)
                    p_val = data.get("pressure_Pa")
                    f_sub = data.get("force_subtracted")
                    f_both = data.get("force_both")
                    f_self = data.get("force_self")
            except Exception:
                pass
        else:
            # Fallback: check checkpoint files if final file not yet aggregated
            rtip_str = f"_rtip_{float(cfg.get('r_tip_nm', 0.0)):.1f}" if (cfg.get("corrugated") and float(cfg.get("r_tip_nm", 0.0)) > 0) else ""
            if cfg.get("corrugated"):
                geom_tag = f"_corr_al_{float(cfg.get('corrugation_angle', 75.0)):.1f}{rtip_str}"
            else:
                geom_tag = "_planar"
            chk_tag = f"v3_d_{float(cfg['d']):.4f}_Ntop_{cfg['N_top']}_Nbot_{cfg.get('N_bot', 1)}_mat_{cfg['material']}_res_{cfg['resolution']}_th_{float(cfg['theta']):.1f}{geom_tag}_L_{float(cfg.get('L', 2.0)):.2f}"
            chk_b = f".tmp/chk_{chk_tag}_both.json"
            chk_s = f".tmp/chk_{chk_tag}_self.json"
            if os.path.exists(chk_b) and os.path.exists(chk_s):
                try:
                    with open(chk_b) as fb, open(chk_s) as fs:
                        fb_val = json.load(fb)["force"]
                        fs_val = json.load(fs)["force"]
                        f_both = fb_val
                        f_self = fs_val
                        f_sub = fb_val - fs_val
                        A_eff = get_effective_area(cfg["N_top"], cfg.get("L", 2.0))
                        p_val = f_sub / A_eff
                except Exception:
                    pass

        matched.append({
            "task_id": cfg["task_id"],
            "archetype": cfg.get("archetype", "unknown"),
            "label": cfg["label"],
            "d_um": cfg["d"],
            "N_top": cfg["N_top"],
            "N_bot": cfg.get("N_bot", 1),
            "corrugated": cfg.get("corrugated", False),
            "corrugation_angle": cfg.get("corrugation_angle", 0.0),
            "r_tip_nm": cfg.get("r_tip_nm", 0.0),
            "theta_deg": cfg["theta"],
            "pressure_Pa": p_val,
            "force_subtracted": f_sub,
            "force_both": f_both,
            "force_self": f_self,
            "status": "COMPLETED" if p_val is not None else "PENDING"
        })

    completed = [m for m in matched if m["status"] == "COMPLETED"]
    repulsive = [m for m in completed if m["pressure_Pa"] is not None and m["pressure_Pa"] > 0]
    
    print(f"Repulsion Screening Status: {len(completed)} / {len(matched)} tasks completed.")
    print(f"Repulsive States Discovered (P > 0): {len(repulsive)}")

    # Print summary grouped by Archetype
    archetypes = [
        ("corrugated_over_flat", "1. Corrugated Top (N=3) vs. Flat Bottom (N=1)"),
        ("hierarchical_corrugations", "2. Hierarchical Corrugations (N=3 vs. N=2)"),
        ("perforated_carpet_cutoff", "3. Perforated Carpet Cutoff (N=3 vs. N=1)"),
        ("orthogonal_ridge_crossing", "4. Orthogonal Ridge Crossing (N=3 vs. N=3)")
    ]

    for arch_key, arch_title in archetypes:
        items = [m for m in matched if m["archetype"] == arch_key]
        print(f"\n--- {arch_title} ({len(items)} Tasks) ---")
        for it in items:
            p = it["pressure_Pa"]
            if p is not None:
                p_str = f"{p:+12.6f} Pa"
                flag = "*** REPULSIVE (P > 0) ***" if p > 0 else "Attractive"
            else:
                p_str = "    Pending"
                flag = "---"
            print(f"  Task {it['task_id']:2d} | d={it['d_um']*1000:4.0f}nm | th={it['theta_deg']:5.1f}deg | P = {p_str} | {flag}")

    # Ranking by pressure (from most repulsive to most attractive)
    if completed:
        print("\n================================================================================")
        print("RANKING: TOP CANDIDATES CLOSEST TO OR EXCEEDING REPULSION (P > 0)")
        print("================================================================================")
        ranked = sorted(completed, key=lambda x: x["pressure_Pa"], reverse=True)
        for rank, it in enumerate(ranked[:10], 1):
            p = it["pressure_Pa"]
            status_tag = ">>> REPULSIVE <<<" if p > 0 else "Suppressed Attraction"
            print(f"  #{rank:2d}: Task {it['task_id']:2d} ({it['archetype']}) | d={it['d_um']*1000:.0f}nm, th={it['theta_deg']:.1f}deg -> P = {p:+10.6e} Pa [{status_tag}]")

    # Save summary JSON
    os.makedirs("results_repulsion", exist_ok=True)
    summary_path = "results_repulsion/repulsion_phase1_summary.json"
    with open(summary_path, "w") as f:
        json.dump(matched, f, indent=4)
    print(f"\nSaved summary dataset to '{summary_path}'.")

    # Generate LaTeX Table
    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)
    tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_repulsion_screening.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated Vacuum Casimir Repulsion Screening Table\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write("\\caption{Phase 1: Vacuum Casimir Repulsion Screening Across 4 Symmetry-Breaking Archetypes ($\\epsilon_{\\rm bg}=1.0$).}\n")
        f.write("\\label{tab:repulsion_screening}\n")
        f.write("\\begin{tabular}{ccccccc}\n\\toprule\n")
        f.write("\\textbf{Archetype} & $N_{\\rm top}$ & $N_{\\rm bot}$ & \\textbf{Gap $d$} & \\textbf{Twist $\\theta$} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Regime} \\\\\n\\midrule\n")
        for m in matched:
            p_str = f"${m['pressure_Pa']:+9.6f}$ Pa" if m["pressure_Pa"] is not None else "Pending"
            if m["pressure_Pa"] is not None:
                reg_str = "\\textbf{Repulsive ($P>0$)}" if m["pressure_Pa"] > 0 else "Attractive"
            else:
                reg_str = "Pending"
            f.write(f"{m['archetype'][:15]} & {m['N_top']} & {m['N_bot']} & ${m['d_um']*1000:.0f}\\text{{ nm}}$ & ${m['theta_deg']:.1f}^\\circ$ & {p_str} & {reg_str} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"Generated Publication Table: '{tex_path}'.")

    # Generate Diagnostic Comparison Figure
    if completed:
        os.makedirs("Papers/Fractal_Casimir_Nature_EM/figures", exist_ok=True)
        fig_path = "Papers/Fractal_Casimir_Nature_EM/figures/fig_repulsion_screening.png"
        plt.figure(figsize=(9, 5.5))
        colors = {"corrugated_over_flat": "#1f77b4", "hierarchical_corrugations": "#ff7f0e", "perforated_carpet_cutoff": "#2ca02c", "orthogonal_ridge_crossing": "#d62728"}
        
        for arch_key, arch_title in archetypes:
            sub = [m for m in completed if m["archetype"] == arch_key and m["pressure_Pa"] is not None]
            if sub:
                xs = [m["theta_deg"] for m in sub]
                ys = [m["pressure_Pa"] for m in sub]
                plt.scatter(xs, ys, s=60, color=colors.get(arch_key, "black"), label=arch_title[:32], alpha=0.8)

        plt.axhline(0, color="red", linestyle="--", linewidth=1.5, label="Zero Pressure Boundary (P=0)")
        plt.xlabel(r"Twist Angle $\theta$ (degrees)", fontsize=12)
        plt.ylabel(r"Casimir Pressure $P$ (Pa)", fontsize=12)
        plt.title("Vacuum Casimir Screening: Identification of Repulsive Regime ($P > 0$)", fontsize=13, pad=12)
        plt.legend(frameon=True, fontsize=9)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(fig_path, dpi=300)
        plt.close()
        print(f"Generated Comparative Figure: '{fig_path}'.")

    # Auto-sync to GitHub
    from execution.git_sync import git_sync_results
    git_sync_results(
        "repulsion_phase1",
        [
            summary_path,
            tex_path,
            "Papers/Fractal_Casimir_Nature_EM/figures/fig_repulsion_screening.png"
        ],
        len(completed),
        len(matched)
    )
    print("================================================================================")

if __name__ == "__main__":
    main()
