#!/usr/bin/env python3
"""
Fractal Quantum Clutch: Results Analyzer
----------------------------------------
Analyzes the 10-task Quantum Clutch screening suite (Menger Spire vs Sierpinski Sieve)
demonstrating the rotation-driven force inversion from Casimir Repulsion (P > 0) to
Attraction (P < 0) in pure vacuum.

Lightweight, standard-library-only design for instantaneous cluster execution
without network filesystem / GPFS latency.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import glob
import json
import math

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def get_expected_output_path(cfg):
    d = float(cfg["d"])
    N = int(cfg["N_top"])
    N_bot = int(cfg.get("N_bot", 3))
    alpha = float(cfg.get("corrugation_angle", 75.0))
    rtip = float(cfg.get("r_tip_nm", 5.0))
    mat = cfg["material"]
    res = int(cfg.get("resolution", 40))
    theta = float(cfg["theta"])
    eps_bg = float(cfg.get("eps_bg", 1.0))
    L = float(cfg.get("L", 2.0))
    
    rtip_str = f"_rtip_{rtip:.1f}" if rtip > 0.0 else ""
    nbot_str = f"_clutch_al_{alpha:.1f}{rtip_str}_Nbot_{N_bot}"
    return f".tmp/meep_d_{d:.4f}_N_{N}{nbot_str}_{mat}_res_{res}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}.json"

def main():
    print("=" * 80)
    print("FRACTAL QUANTUM CLUTCH ANALYZER (MENGER SPIRE VS SIERPINSKI SIEVE)")
    print("=" * 80)

    config_files = sorted(glob.glob("sweep_configs_clutch/config_*.json"))
    if not config_files:
        config_files = sorted(glob.glob(os.path.join(REPO_ROOT, "sweep_configs_clutch/config_*.json")))

    print(f"Loaded {len(config_files)} target Quantum Clutch configurations.")

    matched = []
    for fp in config_files:
        with open(fp, "r") as f:
            cfg = json.load(f)

        expected_fp = get_expected_output_path(cfg)
        p_val = None
        f_sub = None
        f_both = None
        f_self = None

        d_val = float(cfg["d"])
        th_val = float(cfg["theta"])
        tid = cfg["task_id"]

        # Search candidates in results_clutch/results_json and .tmp
        patterns = [
            os.path.join(REPO_ROOT, "results_clutch", "results_json", f"meep_d_{d_val:.4f}_*theta_{th_val:.1f}_*.json"),
            os.path.join(REPO_ROOT, ".tmp", f"meep_d_{d_val:.4f}_*theta_{th_val:.1f}_*.json"),
            expected_fp
        ]
        found_f = None
        for pat in patterns:
            matches = [m for m in glob.glob(pat) if "moments_" not in os.path.basename(m) and "config_" not in os.path.basename(m)]
            if matches:
                found_f = matches[0]
                break

        if found_f and os.path.exists(found_f):
            try:
                with open(found_f, "r") as out_f:
                    data = json.load(out_f)
                    p_val = data.get("pressure_Pa")
                    f_sub = data.get("force_subtracted")
                    f_both = data.get("force_both")
                    f_self = data.get("force_self")
            except (json.JSONDecodeError, OSError, KeyError) as err:
                print(f"Warning: Corrupted result file {found_f} ({err}).")
        else:
            # Check progress status file
            status_f = os.path.join(REPO_ROOT, "results_clutch", "progress", f"task_{tid:03d}_status.json")
            if os.path.exists(status_f):
                try:
                    with open(status_f, "r") as sf:
                        s_data = json.load(sf)
                        if s_data.get("status") == "COMPLETE" and s_data.get("pressure_Pa") is not None:
                            p_val = s_data.get("pressure_Pa")
                            f_sub = s_data.get("net_force")
                except (json.JSONDecodeError, OSError) as err:
                    pass

            if p_val is None:
                # Checkpoint fallback check (strictly require v4 verified geometry checkpoints)
                rtip_str = f"_rtip_{float(cfg.get('r_tip_nm', 5.0)):.1f}" if float(cfg.get('r_tip_nm', 5.0)) > 0 else ""
                geom_tag = f"_clutch_al_{float(cfg.get('corrugation_angle', 75.0)):.1f}{rtip_str}"
                chk_tag = f"v4_d_{d_val:.4f}_Ntop_{cfg['N_top']}_Nbot_{cfg.get('N_bot', 3)}_mat_{cfg['material']}_res_{cfg['resolution']}_th_{th_val:.1f}{geom_tag}_L_{float(cfg.get('L', 2.0)):.2f}"
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
                    except (json.JSONDecodeError, OSError, KeyError) as err:
                        print(f"Warning: Corrupted checkpoint pair {chk_b} / {chk_s} ({err}).")

        matched.append({
            "task_id": cfg["task_id"],
            "label": cfg["label"],
            "d_um": cfg["d"],
            "N_top": cfg["N_top"],
            "N_bot": cfg["N_bot"],
            "theta_deg": cfg["theta"],
            "pressure_Pa": p_val,
            "force_subtracted": f_sub,
            "force_both": f_both,
            "force_self": f_self,
            "status": "COMPLETED" if p_val is not None else "PENDING"
        })

    completed = [m for m in matched if m["status"] == "COMPLETED"]
    repulsive = [m for m in completed if m["pressure_Pa"] is not None and m["pressure_Pa"] > 0]
    attractive = [m for m in completed if m["pressure_Pa"] is not None and m["pressure_Pa"] < 0]

    print(f"\nClutch Status: {len(completed)} / {len(matched)} tasks completed.")
    print(f"Repulsive States (Disengaged, P > 0): {len(repulsive)}")
    print(f"Attractive States (Engaged, P < 0):    {len(attractive)}")

    # Print summary grouped by Gap d
    gaps = sorted(list(set([m["d_um"] for m in matched])))
    for d_val in gaps:
        items = [m for m in matched if abs(m["d_um"] - d_val) < 1e-4]
        print(f"\n--- Gap d = {int(d_val*1000)} nm ({len(items)} Tasks) ---")
        for it in items:
            p = it["pressure_Pa"]
            if p is not None:
                p_str = f"{p:+12.6f} Pa"
                flag = "*** REPULSIVE (P > 0) [DISENGAGED] ***" if p > 0 else "Attractive [ENGAGED]"
            else:
                p_str = "    Pending"
                flag = "---"
            print(f"  Task {it['task_id']:2d} | th={it['theta_deg']:5.1f}deg | P = {p_str} | {flag}")

    # Check Quantum Clutch Inversion Verification
    clutch_verified = False
    for d_val in gaps:
        d_items = [m for m in completed if abs(m["d_um"] - d_val) < 1e-4]
        p_0 = next((m["pressure_Pa"] for m in d_items if abs(m["theta_deg"] - 0.0) < 1e-2), None)
        p_90 = next((m["pressure_Pa"] for m in d_items if abs(m["theta_deg"] - 90.0) < 1e-2), None)
        if p_0 is not None and p_90 is not None:
            if p_0 > 0 and p_90 < 0:
                print(f"\n>>> SUCCESS! QUANTUM CLUTCH CONFIRMED AT d={int(d_val*1000)}nm! <<<")
                print(f"    theta =  0.0 deg: P = {p_0:+10.6f} Pa (Repulsive Levitation)")
                print(f"    theta = 90.0 deg: P = {p_90:+10.6f} Pa (Attractive Clamping)")
                print(f"    Dynamic Switch Amplitude: Delta_P = {p_0 - p_90:10.6f} Pa")
                clutch_verified = True

    # Save summary JSON
    os.makedirs("results_clutch", exist_ok=True)
    summary_path = "results_clutch/clutch_summary.json"
    with open(summary_path, "w") as f:
        json.dump(matched, f, indent=4)
    print(f"\nSaved summary dataset to '{summary_path}'.")

    # Generate Publication LaTeX Table
    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)
    tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_quantum_clutch.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated Fractal Quantum Clutch Verification Table\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write("\\caption{Fractal Quantum Clutch: Rotation-Driven Casimir Force Inversion ($\\epsilon_{\\rm bg}=1.0$).}\n")
        f.write("\\label{tab:quantum_clutch}\n")
        f.write("\\begin{tabular}{cccccc}\n\\toprule\n")
        f.write("\\textbf{Task} & \\textbf{Gap $d$} & \\textbf{Twist $\\theta$} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Clutch State} & \\textbf{Regime} \\\\\n\\midrule\n")
        for m in matched:
            p_str = f"${m['pressure_Pa']:+9.6f}$ Pa" if m["pressure_Pa"] is not None else "Pending"
            if m["pressure_Pa"] is not None:
                if m["pressure_Pa"] > 0:
                    state_str = "Disengaged"
                    reg_str = "\\textbf{Repulsive ($P>0$)}"
                else:
                    state_str = "Engaged"
                    reg_str = "Attractive ($P<0$)"
            else:
                state_str = "---"
                reg_str = "Pending"
            f.write(f"{m['task_id']:2d} & ${m['d_um']*1000:.0f}\\text{{ nm}}$ & ${m['theta_deg']:.1f}^\\circ$ & {p_str} & {state_str} & {reg_str} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"Generated Publication Table: '{tex_path}'.")

    # Generate Characteristic Comparison Figure (optional, non-blocking)
    if completed:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            os.makedirs("Papers/Fractal_Casimir_Nature_EM/figures", exist_ok=True)
            fig_path = "Papers/Fractal_Casimir_Nature_EM/figures/fig_quantum_clutch_characteristic.png"
            plt.figure(figsize=(8.5, 5.0))
            colors = {0.04: "#2ca02c", 0.08: "#1f77b4"}
            markers = {0.04: "o", 0.08: "s"}

            for d_val in gaps:
                sub_d = [m for m in completed if abs(m["d_um"] - d_val) < 1e-4 and m["pressure_Pa"] is not None]
                if sub_d:
                    sub_d = sorted(sub_d, key=lambda x: x["theta_deg"])
                    xs = [m["theta_deg"] for m in sub_d]
                    ys = [m["pressure_Pa"] for m in sub_d]
                    plt.plot(xs, ys, marker=markers.get(d_val, "o"), color=colors.get(d_val, "black"),
                             linewidth=2.0, markersize=8, label=f"Gap d = {int(d_val*1000)} nm")

            plt.axhline(0, color="red", linestyle="--", linewidth=1.5, label="Zero-Force Gateway (P = 0)")
            plt.xlabel(r"Twist Angle $\theta$ (degrees)", fontsize=12)
            plt.ylabel(r"Casimir Pressure $P$ (Pa)", fontsize=12)
            plt.title(r"Fractal Quantum Clutch: Rotational Switching ($P>0 \leftrightarrow P<0$)", fontsize=13, pad=12)
            plt.legend(frameon=True, fontsize=10)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(fig_path, dpi=300)
            plt.close()
            print(f"Generated Clutch Characteristic Figure: '{fig_path}'.")
        except (ImportError, RuntimeError, OSError) as e:
            print(f"[Note] Skipping matplotlib figure generation on cluster: {e}")

    # Auto-sync to GitHub
    try:
        from execution.git_sync import git_sync_results
        git_sync_results(
            "quantum_clutch",
            [
                summary_path,
                tex_path,
                "Papers/Fractal_Casimir_Nature_EM/figures/fig_quantum_clutch_characteristic.png"
            ],
            len(completed),
            len(matched)
        )
    except (ImportError, subprocess.SubprocessError, OSError) as e:
        print(f"[Git Auto-Sync Note] {e}")

    print("=" * 80)

if __name__ == "__main__":
    main()
