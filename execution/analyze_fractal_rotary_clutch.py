#!/usr/bin/env python3
"""
Results Analyzer for Dual-Fractal Rotary Vacuum Casimir Clutch
--------------------------------------------------------------------------------
Processes simulation JSON outputs from results_fractal_rotary_clutch/ and evaluates:
1. Normal Casimir force F_z(theta) and pressure P(theta) across rotation angles
   for prefractal generation N.
2. Identifies the critical clutch disengagement/engagement angle theta_clutch
   where the force switches from fractal repulsion (F_z > 0) to attraction (F_z < 0).
3. Produces summary JSON, LaTeX tables, and a 3-panel publication figure.
"""

import os
import sys
import glob
import json
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

def main():
    res_dir = os.path.join(REPO_ROOT, "results_fractal_rotary_clutch")
    files = sorted(glob.glob(os.path.join(res_dir, "task_*.json")))

    if not files:
        print(f"No result files found in {res_dir}. Run the simulation on Big Red 200 first.")
        return

    data = []
    for f in files:
        try:
            with open(f, "r") as f_in:
                d = json.load(f_in)
            data.append(d)
        except (json.JSONDecodeError, OSError) as err:
            print(f"Warning: Could not read {f}: {err}")

    if not data:
        print("No valid result JSON files loaded.")
        return

    data = sorted(data, key=lambda x: x.get("theta_deg", 0.0))

    print("=" * 100)
    print("DUAL-FRACTAL ROTARY VACUUM CASIMIR CLUTCH ANALYSIS (Menger-Sierpinski Architecture)")
    print("=" * 100)
    print(f"{'Task ID':<10}{'Gen N':<8}{'theta (deg)':<14}{'F_total (fN)':<18}{'Pressure (Pa)':<18}{'Regime':<24}")
    print("-" * 100)

    has_repulsive = False
    has_attractive = False
    th_vals = []
    f_vals = []
    p_vals = []

    for d in data:
        tid = d.get("task_id", 0)
        n_gen = d.get("N_fractal", 1)
        th = d.get("theta_deg", 0.0)
        f_net_fN = d.get("force_total_fN", d.get("force_total_meep", 0.0) * 31.615)
        p = d.get("pressure_Pa", 0.0)

        th_vals.append(th)
        f_vals.append(f_net_fN)
        p_vals.append(p)

        if f_net_fN > 0:
            has_repulsive = True
            regime_str = "++ FRACTAL REPULSION ++"
        else:
            has_attractive = True
            regime_str = "-- FRACTAL ATTRACTION --"

        print(f"{tid:<10}{n_gen:<8}{th:<14.1f}{f_net_fN:<+18.4f}{p:<+18.4e}{regime_str:<24}")

    print("=" * 100)

    # Check for clutch zero-crossing angle theta_clutch
    th_clutch = None
    for i in range(len(f_vals) - 1):
        if (f_vals[i] > 0 and f_vals[i+1] < 0) or (f_vals[i] < 0 and f_vals[i+1] > 0):
            th1, th2 = th_vals[i], th_vals[i+1]
            f1, f2 = f_vals[i], f_vals[i+1]
            th_clutch = th1 - f1 * (th2 - th1) / (f2 - f1)
            break

    if has_repulsive and has_attractive:
        print(">>> SUCCESS: Full Dual-Fractal Casimir Clutch verified! Transitions between Repulsion and Attraction.")
        if th_clutch is not None:
            print(f">>> FRACTAL CLUTCH THRESHOLD: theta_clutch = {th_clutch:.2f} deg")
    elif has_repulsive:
        print("Notice: Repulsive forces detected; run intermediate angles (e.g. 45 deg) to capture attractive engagement.")
    else:
        print("Notice: Attractive forces detected; verify theta = 0 deg for aperture repulsion.")
    print("=" * 100)

    # 1. Save summary JSON
    summary_data = {
        "architecture": "dual_fractal_rotary_casimir_clutch",
        "theta_clutch_deg": float(th_clutch) if th_clutch is not None else None,
        "has_repulsive": bool(has_repulsive),
        "has_attractive": bool(has_attractive),
        "data_points": data
    }
    summary_path = os.path.join(res_dir, "fractal_clutch_summary.json")
    with open(summary_path, "w") as f_sum:
        json.dump(summary_data, f_sum, indent=4)
    print(f"Summary JSON saved: {summary_path}")

    # 2. Save LaTeX Table
    table_path = os.path.join(res_dir, "table_fractal_clutch.tex")
    with open(table_path, "w") as f_tex:
        f_tex.write(r"\begin{table}[htbp]" + "\n")
        f_tex.write(r"\centering" + "\n")
        f_tex.write(r"\caption{Dual-Fractal Rotary Vacuum Casimir Clutch Force and Pressure vs Rotation Angle $\theta$ ($z_{\text{tip}} = 15\,\text{nm}$, $N = 2$, $L = 1.05\,\mu\text{m}$, $W_1 = 350\,\text{nm}$).}" + "\n")
        f_tex.write(r"\label{tab:fractal_rotary_clutch}" + "\n")
        f_tex.write(r"\begin{tabular}{cccccc}" + "\n")
        f_tex.write(r"\hline" + "\n")
        f_tex.write(r"Task & Gen $N$ & $\theta$ (deg) & $F_{\text{total}}$ (fN) & Pressure (Pa) & Clutch State \\" + "\n")
        f_tex.write(r"\hline" + "\n")
        for d in data:
            tid = d.get("task_id", 0)
            n_gen = d.get("N_fractal", 1)
            th = d.get("theta_deg", 0.0)
            f_net_fN = d.get("force_total_fN", d.get("force_total_meep", 0.0) * 31.615)
            p = d.get("pressure_Pa", 0.0)
            state = "Levitating (Repulsive)" if f_net_fN > 0 else "Clamping (Attractive)"
            f_tex.write(f"{tid} & {n_gen} & {th:.1f} & {f_net_fN:+.2f} & {p:+.2e} & {state} \\\\\n")
        f_tex.write(r"\hline" + "\n")
        f_tex.write(r"\end{tabular}" + "\n")
        f_tex.write(r"\end{table}" + "\n")
    print(f"LaTeX Table saved: {table_path}")

    # 3. Generate publication-quality 3-panel figure
    try:
        import matplotlib.pyplot as plt
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
        plt.rcParams['font.size'] = 8
        plt.rcParams['axes.labelsize'] = 8
        plt.rcParams['axes.titlesize'] = 9
        plt.rcParams['legend.fontsize'] = 7
        plt.rcParams['xtick.labelsize'] = 7
        plt.rcParams['ytick.labelsize'] = 7

        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(10.5, 3.2), dpi=300)

        th_arr = np.array(th_vals)
        f_arr = np.array(f_vals)
        p_arr = np.array(p_vals)

        # (a) Full C4 Angular Range: theta in [0, 90] deg
        ax1.axhline(0, color="k", linestyle="--", linewidth=0.8, alpha=0.7)
        if th_clutch is not None:
            ax1.axvline(th_clutch, color="crimson", linestyle="-.", linewidth=0.8, label=f"$\\theta_{{c1}} = {th_clutch:.1f}^\\circ$")
            ax1.axvline(90.0 - th_clutch, color="crimson", linestyle="-.", linewidth=0.8, label=f"$\\theta_{{c2}} = {90.0-th_clutch:.1f}^\\circ$")
        ax1.plot(th_arr, f_arr, "o-", color="#1f77b4", linewidth=1.5, markersize=5, label=r"$F_z(\theta)$ (Fractal)")
        ax1.fill_between(th_arr, 0, f_arr, where=(f_arr > 0), color="green", alpha=0.18, label="Fractal Repulsion")
        ax1.fill_between(th_arr, 0, f_arr, where=(f_arr < 0), color="blue", alpha=0.10, label="Fractal Attraction")
        ax1.set_xlabel(r"Rotation Angle $\theta$ (deg)")
        ax1.set_ylabel(r"Fractal Rotor Force $F_z$ (fN)")
        ax1.set_title(r"(a) Full $C_4$ Clutch Characteristic")
        ax1.grid(True, linestyle=":", alpha=0.5)
        ax1.legend(loc="lower left", frameon=True)

        # (b) Transition Zoom around theta_clutch
        near_mask = th_arr <= 45.0
        ax2.axhline(0, color="k", linestyle="--", linewidth=0.8, alpha=0.7)
        if th_clutch is not None:
            ax2.axvline(th_clutch, color="crimson", linestyle="-.", linewidth=1.0, label=f"$\\theta_c = {th_clutch:.1f}^\\circ$ (Neutral)")
        ax2.plot(th_arr[near_mask], f_arr[near_mask], "o-", color="#2ca02c", linewidth=1.8, markersize=6, label=r"$F_z$ (Transition)")
        ax2.fill_between(th_arr[near_mask], 0, f_arr[near_mask], where=(f_arr[near_mask] > 0), color="green", alpha=0.25, label="REPULSION")
        ax2.fill_between(th_arr[near_mask], 0, f_arr[near_mask], where=(f_arr[near_mask] < 0), color="blue", alpha=0.15, label="ATTRACTION")
        ax2.set_xlabel(r"Rotation Angle $\theta$ (deg)")
        ax2.set_ylabel(r"Fractal Rotor Force $F_z$ (fN)")
        ax2.set_title(r"(b) Near-Zero Transition Zoom")
        ax2.grid(True, linestyle=":", alpha=0.5)
        ax2.legend(loc="upper right", frameon=True)

        # (c) Normal Pressure P(theta)
        ax3.axhline(0, color="k", linestyle="--", linewidth=0.8, alpha=0.7)
        if th_clutch is not None:
            ax3.axvline(th_clutch, color="crimson", linestyle="-.", linewidth=0.8, label=f"$\\theta_c = {th_clutch:.1f}^\\circ$")
        ax3.plot(th_arr, p_arr, "s-", color="#d62728", linewidth=1.5, markersize=5, label=r"Pressure (Pa)")
        ax3.fill_between(th_arr, 0, p_arr, where=(p_arr > 0), color="green", alpha=0.18)
        ax3.fill_between(th_arr, 0, p_arr, where=(p_arr < 0), color="blue", alpha=0.10)
        ax3.set_xlabel(r"Rotation Angle $\theta$ (deg)")
        ax3.set_ylabel(r"Normal Pressure $P$ (Pa)")
        ax3.set_title(r"(c) Primary Needle Pressure $P(\theta)$")
        ax3.grid(True, linestyle=":", alpha=0.5)
        ax3.legend(loc="lower left", frameon=True)

        plt.tight_layout()
        fig_path = os.path.join(res_dir, "fig_fractal_rotary_clutch.png")
        plt.savefig(fig_path, dpi=300)
        plt.close()
        print(f"Publication Figure saved: {fig_path}")
    except Exception as fig_err:
        print(f"Notice: Could not render figure ({fig_err}).")

if __name__ == "__main__":
    main()
