#!/usr/bin/env python3
"""
Results Analyzer for Dual-Fractal Rotary Vacuum Casimir Clutch (N=1 vs N=3)
--------------------------------------------------------------------------------
Processes simulation JSON outputs from results_fractal_rotary_clutch/ and evaluates:
1. Normal Casimir force F_z(theta) and pressure P(theta) across rotation angles
   theta in {0 deg, 30 deg, 45 deg, 90 deg} for prefractal generations N = 1 and N = 3.
2. Demonstrates the Casimir clutch transition from Levin-Johnson vacuum repulsion (F_z > 0)
   to Kenneth-Klich vacuum attraction (F_z < 0) purely via in-plane plate rotation theta.
3. Quantifies fractal geometric scaling at strictly invariant area-weighted
   average plate distance <d> = 20.00 nm.
4. Identifies the critical clutch neutral angle theta_clutch where F_z = 0.
5. Generates summary JSON, publication LaTeX tables, and a multi-curve figure.
"""

import os
import sys
import glob
import json
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find_zero_crossing(th_vals, f_vals):
    """Computes linear interpolation zero-crossing angle theta_clutch where F_z = 0."""
    for i in range(len(f_vals) - 1):
        if (f_vals[i] > 0 and f_vals[i+1] < 0) or (f_vals[i] < 0 and f_vals[i+1] > 0):
            th1, th2 = th_vals[i], th_vals[i+1]
            f1, f2 = f_vals[i], f_vals[i+1]
            return float(th1 - f1 * (th2 - th1) / (f2 - f1))
    return None


def main():
    res_dir = os.path.join(REPO_ROOT, "results_fractal_rotary_clutch")
    files = sorted(glob.glob(os.path.join(res_dir, "task_*.json")))

    if not files:
        print(f"No result files found in {res_dir}. Run the simulation on Big Red 200 first.")
        return

    data = []
    for f in files:
        with open(f, "r") as f_in:
            d = json.load(f_in)
        data.append(d)

    if not data:
        print("No valid result JSON files loaded.")
        return

    # Separate into N=1 and N=3 groups
    data_n1 = sorted([d for d in data if d.get("N_fractal") == 1], key=lambda x: x.get("theta_deg", 0.0))
    data_n3 = sorted([d for d in data if d.get("N_fractal") == 3], key=lambda x: x.get("theta_deg", 0.0))

    print("=" * 110)
    print("DUAL-FRACTAL ROTARY VACUUM CASIMIR CLUTCH: N=1 vs N=3 AT INVARIANT <d> = 20.0 nm")
    print("=" * 110)
    print(f"{'Task':<6}{'Gen N':<8}{'theta':<10}{'z_tip (nm)':<14}{'<d> (nm)':<12}{'F_total (fN)':<18}{'Pressure (Pa)':<18}{'Regime':<24}")
    print("-" * 110)

    for d in sorted(data, key=lambda x: (x.get("N_fractal", 1), x.get("theta_deg", 0.0))):
        tid = d.get("task_id", 0)
        n_gen = d.get("N_fractal", 1)
        th = d.get("theta_deg", 0.0)
        ztip = d.get("z_tip_nm", 0.0)
        davg = d.get("d_average_nm", 20.0)
        f_net_fN = d.get("force_total_fN", d.get("force_total_meep", 0.0) * 31.615)
        p = d.get("pressure_Pa", 0.0)
        regime_str = "++ FRACTAL REPULSION ++" if f_net_fN > 0 else "-- FRACTAL ATTRACTION --"
        print(f"{tid:<6}{n_gen:<8}{th:<10.1f}{ztip:<14.2f}{davg:<12.1f}{f_net_fN:<+18.4f}{p:<+18.4e}{regime_str:<24}")

    print("=" * 110)

    # Analyze N=1 series
    th_n1 = [d.get("theta_deg", 0.0) for d in data_n1]
    f_n1 = [d.get("force_total_fN", d.get("force_total_meep", 0.0) * 31.615) for d in data_n1]
    p_n1 = [d.get("pressure_Pa", 0.0) for d in data_n1]
    th_clutch_n1 = find_zero_crossing(th_n1, f_n1) if len(th_n1) > 1 else None

    # Analyze N=3 series
    th_n3 = [d.get("theta_deg", 0.0) for d in data_n3]
    f_n3 = [d.get("force_total_fN", d.get("force_total_meep", 0.0) * 31.615) for d in data_n3]
    p_n3 = [d.get("pressure_Pa", 0.0) for d in data_n3]
    th_clutch_n3 = find_zero_crossing(th_n3, f_n3) if len(th_n3) > 1 else None

    print("\n--- CLUTCH TRANSITION SUMMARY ---")
    if th_clutch_n1 is not None:
        print(f"  Generation N=1: Neutral Clutch Angle theta_clutch = {th_clutch_n1:.2f} deg (z_tip = 17.22 nm, <d> = 20.0 nm)")
    else:
        print("  Generation N=1: No zero crossing captured within completed angles.")

    if th_clutch_n3 is not None:
        print(f"  Generation N=3: Neutral Clutch Angle theta_clutch = {th_clutch_n3:.2f} deg (z_tip = 12.56 nm, <d> = 20.0 nm)")
    else:
        print("  Generation N=3: No zero crossing captured within completed angles.")

    # 1. Summary JSON
    summary_data = {
        "architecture": "dual_fractal_rotary_casimir_clutch_constant_d_avg",
        "d_average_nm": 20.0,
        "N_1": {
            "z_tip_nm": 17.22,
            "theta_clutch_deg": th_clutch_n1,
            "tasks": data_n1
        },
        "N_3": {
            "z_tip_nm": 12.56,
            "theta_clutch_deg": th_clutch_n3,
            "tasks": data_n3
        }
    }
    summary_path = os.path.join(res_dir, "fractal_clutch_summary.json")
    with open(summary_path, "w", newline="\n") as f_sum:
        json.dump(summary_data, f_sum, indent=4)
    print(f"\nSummary JSON saved: {summary_path}")

    # 2. LaTeX Table
    table_path = os.path.join(res_dir, "table_fractal_clutch.tex")
    with open(table_path, "w", newline="\n") as f_tex:
        f_tex.write(r"\begin{table}[htbp]" + "\n")
        f_tex.write(r"\centering" + "\n")
        f_tex.write(r"\caption{Dual-Fractal Rotary Vacuum Casimir Clutch Force and Pressure vs Rotation Angle $\theta$ at Invariant Average Distance $\langle d \rangle = 20.00\,\text{nm}$ ($L = 1.05\,\mu\text{m}$, $W_1 = 250\,\text{nm}$, $w_1 = 35\,\text{nm}$, Gold in Vacuum).}" + "\n")
        f_tex.write(r"\label{tab:fractal_rotary_clutch}" + "\n")
        f_tex.write(r"\begin{tabular}{cccccccc}" + "\n")
        f_tex.write(r"\hline\hline" + "\n")
        f_tex.write(r"Task & Gen $N$ & $\theta$ (deg) & $z_{\text{tip}}$ (nm) & $\langle d \rangle$ (nm) & $F_{\text{total}}$ (fN) & Pressure (Pa) & Clutch State \\" + "\n")
        f_tex.write(r"\hline" + "\n")
        for d in sorted(data, key=lambda x: (x.get("N_fractal", 1), x.get("theta_deg", 0.0))):
            tid = d.get("task_id", 0)
            n_gen = d.get("N_fractal", 1)
            th = d.get("theta_deg", 0.0)
            ztip = d.get("z_tip_nm", 0.0)
            davg = d.get("d_average_nm", 20.0)
            f_net_fN = d.get("force_total_fN", d.get("force_total_meep", 0.0) * 31.615)
            p = d.get("pressure_Pa", 0.0)
            state = "Levitating (Repulsive)" if f_net_fN > 0 else "Clamping (Attractive)"
            f_tex.write(f"{tid} & {n_gen} & {th:.1f} & {ztip:.2f} & {davg:.1f} & {f_net_fN:+.2f} & {p:+.2e} & {state} \\\\\n")
        f_tex.write(r"\hline\hline" + "\n")
        f_tex.write(r"\end{tabular}" + "\n")
        f_tex.write(r"\end{table}" + "\n")
    print(f"LaTeX Table saved: {table_path}")

    # 3. Publication 3-panel figure: N=1 vs N=3 comparison
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Helvetica", "Arial", "DejaVu Sans"]
    plt.rcParams["font.size"] = 8
    plt.rcParams["axes.labelsize"] = 8
    plt.rcParams["axes.titlesize"] = 9
    plt.rcParams["legend.fontsize"] = 7
    plt.rcParams["xtick.labelsize"] = 7
    plt.rcParams["ytick.labelsize"] = 7

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(11.0, 3.4), dpi=300)

    # (a) Normal Force F_z(theta): N=1 vs N=3
    ax1.axhline(0, color="k", linestyle="--", linewidth=0.8, alpha=0.7)
    if th_n1 and f_n1:
        ax1.plot(th_n1, f_n1, "o-", color="#1f77b4", linewidth=1.6, markersize=5,
                 label=r"$N=1$ ($z_{\mathrm{tip}}=17.2\,\mathrm{nm}$)")
    if th_n3 and f_n3:
        ax1.plot(th_n3, f_n3, "s--", color="#d62728", linewidth=1.6, markersize=5,
                 label=r"$N=3$ ($z_{\mathrm{tip}}=12.6\,\mathrm{nm}$)")

    if th_clutch_n1 is not None:
        ax1.axvline(th_clutch_n1, color="#1f77b4", linestyle=":", linewidth=0.9, alpha=0.8)
    if th_clutch_n3 is not None:
        ax1.axvline(th_clutch_n3, color="#d62728", linestyle=":", linewidth=0.9, alpha=0.8)

    ax1.set_xlabel(r"Rotation Angle $\theta$ (deg)")
    ax1.set_ylabel(r"Total Rotor Force $F_z$ (fN)")
    ax1.set_title(r"(a) Rotor Normal Force $F_z(\theta)$")
    ax1.set_xlim(-5, 95)
    ax1.set_xticks([0, 30, 45, 90])
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="lower left", frameon=True)

    # (b) Normal Pressure P(theta): N=1 vs N=3
    ax2.axhline(0, color="k", linestyle="--", linewidth=0.8, alpha=0.7)
    if th_n1 and p_n1:
        ax2.plot(th_n1, p_n1, "o-", color="#1f77b4", linewidth=1.6, markersize=5,
                 label=r"$N=1$ Pressure")
    if th_n3 and p_n3:
        ax2.plot(th_n3, p_n3, "s--", color="#d62728", linewidth=1.6, markersize=5,
                 label=r"$N=3$ Pressure")

    ax2.set_xlabel(r"Rotation Angle $\theta$ (deg)")
    ax2.set_ylabel(r"Normal Pressure $P$ (Pa)")
    ax2.set_title(r"(b) Primary Needle Pressure $P(\theta)$")
    ax2.set_xlim(-5, 95)
    ax2.set_xticks([0, 30, 45, 90])
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(loc="lower left", frameon=True)

    # (c) Geometric Invariance & Fractal Ratio
    # Compare ratio F_z(N=3) / F_z(N=1) across matching angles
    common_angles = sorted(list(set(th_n1).intersection(set(th_n3))))
    if common_angles:
        ratios = []
        for ang in common_angles:
            idx1 = th_n1.index(ang)
            idx3 = th_n3.index(ang)
            if abs(f_n1[idx1]) > 1e-12:
                ratios.append(f_n3[idx3] / f_n1[idx1])
            else:
                ratios.append(np.nan)
        ax3.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6, label="No Scaling (1.0)")
        ax3.plot(common_angles, ratios, "D-", color="#2ca02c", linewidth=1.6, markersize=5,
                 label=r"$F_z(N=3) / F_z(N=1)$")
        ax3.set_xlabel(r"Rotation Angle $\theta$ (deg)")
        ax3.set_ylabel(r"Fractal Force Ratio $F_3 / F_1$")
        ax3.set_title(r"(c) Fractal Scaling at Invariant $\langle d \rangle = 20\,\mathrm{nm}$")
        ax3.set_xlim(-5, 95)
        ax3.set_xticks([0, 30, 45, 90])
        ax3.grid(True, linestyle=":", alpha=0.5)
        ax3.legend(loc="best", frameon=True)
    else:
        # Fallback layout showing invariant average distance formulation
        ax3.text(0.5, 0.6, r"$\langle d \rangle = z_{\mathrm{tip}} + f_N \cdot h = 20.00\,\mathrm{nm}$",
                 ha="center", va="center", fontsize=9, transform=ax3.transAxes)
        ax3.text(0.5, 0.4, r"$N=1: z_{\mathrm{tip}} = 17.22\,\mathrm{nm}$" + "\n" + r"$N=3: z_{\mathrm{tip}} = 12.56\,\mathrm{nm}$",
                 ha="center", va="center", fontsize=8, transform=ax3.transAxes)
        ax3.set_title(r"(c) Invariant Average Distance Setup")
        ax3.axis("off")

    plt.tight_layout()
    fig_path = os.path.join(res_dir, "fig_fractal_clutch_N1_vs_N3.png")
    fig_compat_path = os.path.join(res_dir, "fig_fractal_rotary_clutch.png")
    plt.savefig(fig_path, dpi=300)
    plt.savefig(fig_compat_path, dpi=300)
    plt.close()
    print(f"Publication Figure saved: {fig_path}")


if __name__ == "__main__":
    main()
