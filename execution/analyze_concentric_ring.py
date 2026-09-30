#!/usr/bin/env python3
"""
Concentric Cantor-Ring Rotary Casimir Clutch Analyzer: "The One Ring to Rule Them All"
--------------------------------------------------------------------------------------
Processes simulation outputs from results_concentric_ring/ across:
1. Prefractal generations N in {1, 2, 3}.
2. Non-fractal uniform periodic concentric ring control.
3. Solid flat plate reference control.
4. Identifies critical neutral clutch angles theta_clutch where F_z = 0.
5. Demonstrates the physical scale truncation boundary: N=1 -> N=2 -> N=3.
6. Generates summary JSON, publication LaTeX table, and 3-panel publication figure.
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
    res_dir = os.path.join(REPO_ROOT, "results_concentric_ring")
    files = sorted(glob.glob(os.path.join(res_dir, "task_*.json")))

    if not files:
        print(f"No result files found in {res_dir}. Run the simulation on BigRed 200 first.")
        print("Note: Submit execution/submit_concentric_ring.sbatch via Slurm.")
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

    data_by_id = {d["task_id"]: d for d in data}

    print("=" * 115)
    print("CONCENTRIC CANTOR-RING ROTARY CASIMIR CLUTCH ANALYSIS: 'THE ONE RING'")
    print("=" * 115)
    print(f"{'Task':<6}{'Type':<12}{'N':<4}{'Tracks':<8}{'theta (deg)':<13}{'z_tip (nm)':<13}{'F_net (fN)':<16}{'Pressure (Pa)':<16}{'Regime':<15}")
    print("-" * 115)

    for tid in sorted(data_by_id.keys()):
        d = data_by_id[tid]
        arch = "Control" if d.get("is_control") else f"Cantor N={d.get('N_fractal')}"
        n_frac = d.get("N_fractal", 0)
        n_t = d.get("num_tracks", 0)
        th = d.get("theta_deg", 0.0)
        z = d.get("z_tip_nm", 0.0)
        f_net_fN = d.get("force_net_fN", 0.0)
        p = d.get("pressure_Pa", 0.0)
        reg_str = "++ REPULSIVE ++" if f_net_fN > 0 else "-- ATTRACTIVE --"
        print(f"{tid:<6}{arch:<12}{n_frac:<4}{n_t:<8}{th:<13.1f}{z:<13.2f}{f_net_fN:<+16.2f}{p:<+16.4e}{reg_str:<15}")

    print("=" * 115)

    # Separate datasets
    groups = {
        "N1": sorted([d for d in data if not d.get("is_control") and d.get("N_fractal") == 1], key=lambda x: x["theta_deg"]),
        "N2": sorted([d for d in data if not d.get("is_control") and d.get("N_fractal") == 2], key=lambda x: x["theta_deg"]),
        "N3": sorted([d for d in data if not d.get("is_control") and d.get("N_fractal") == 3], key=lambda x: x["theta_deg"]),
        "Uniform": sorted([d for d in data if d.get("is_control") and not d.get("is_flat_control")], key=lambda x: x["theta_deg"]),
        "Flat": [d for d in data if d.get("is_flat_control")]
    }

    crossover_angles = {}
    for gname in ["N1", "N2", "N3", "Uniform"]:
        g_data = groups[gname]
        if len(g_data) >= 2:
            th_vals = [d["theta_deg"] for d in g_data]
            f_vals = [d["force_net_fN"] for d in g_data]
            x_angle = find_zero_crossing(th_vals, f_vals)
            crossover_angles[gname] = x_angle
            if x_angle is not None:
                print(f">>> Critical Clutch Neutral Angle ({gname}): theta_clutch = {x_angle:.2f} deg")

    # Save Summary JSON
    summary_data = {
        "campaign": "concentric_cantor_ring_rotary_clutch",
        "crossover_angles_deg": crossover_angles,
        "tasks": data_by_id
    }
    sum_path = os.path.join(res_dir, "concentric_ring_clutch_summary.json")
    with open(sum_path, "w") as f_s:
        json.dump(summary_data, f_s, indent=4)
    print(f"\nSummary JSON saved to {sum_path}")

    # Generate Publication LaTeX Table
    tex_path = os.path.join(res_dir, "table_concentric_ring_clutch.tex")
    with open(tex_path, "w") as f_tex:
        f_tex.write(r"\begin{table*}[t]" + "\n")
        f_tex.write(r"\centering" + "\n")
        f_tex.write(r"\caption{Rotary Casimir Clutch in the Concentric Cantor-Ring Architecture at Invariant $\langle d \rangle = 20.0\,\text{nm}$.}" + "\n")
        f_tex.write(r"\label{tab:concentric_ring_clutch}" + "\n")
        f_tex.write(r"\begin{tabular}{cccccccc}" + "\n")
        f_tex.write(r"\hline\hline" + "\n")
        f_tex.write(r"Task & Configuration & Level $N$ & Tracks & Angle $\theta$ & $z_{\text{tip}}$ (nm) & $F_{\text{net}}$ (fN) & Pressure (Pa) \\" + "\n")
        f_tex.write(r"\hline" + "\n")
        for tid in sorted(data_by_id.keys()):
            d = data_by_id[tid]
            arch_str = "Solid Flat" if d.get("is_flat_control") else "Uniform Ring" if d.get("is_control") else f"Cantor Ring"
            f_tex.write(
                f"{tid} & {arch_str} & {d.get('N_fractal', 0)} & {d.get('num_tracks', 0)} & "
                f"{d.get('theta_deg', 0.0):.1f}$^\\circ$ & {d.get('z_tip_nm', 0.0):.2f} & "
                f"{d.get('force_net_fN', 0.0):+.2f} & {d.get('pressure_Pa', 0.0):+.2e} \\\\\n"
            )
        f_tex.write(r"\hline\hline" + "\n")
        f_tex.write(r"\end{tabular}" + "\n")
        f_tex.write(r"\end{table*}" + "\n")
    print(f"LaTeX table saved to {tex_path}")

    # 3-Panel Publication Figure
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Panel (a): F_net(theta) across N=1, N=2, N=3, and Uniform Control
    ax1 = axes[0]
    colors = {"N1": "#1f77b4", "N2": "#ff7f0e", "N3": "#2ca02c", "Uniform": "#9467bd"}
    labels = {
        "N1": r"Cantor $N=1$ (1 Track)",
        "N2": r"Cantor $N=2$ (3 Tracks)",
        "N3": r"Cantor $N=3$ (7 Tracks)",
        "Uniform": r"Uniform Control (3 Tracks)"
    }
    markers = {"N1": "o--", "N2": "^-", "N3": "s-", "Uniform": "d-."}

    for gname in ["N1", "N2", "N3", "Uniform"]:
        g_data = groups[gname]
        if g_data:
            th = [d["theta_deg"] for d in g_data]
            f_val = [d["force_net_fN"] for d in g_data]
            ax1.plot(th, f_val, markers[gname], color=colors[gname], linewidth=2.0, markersize=7, label=labels[gname])

    ax1.axhline(0, color="gray", linestyle="--", alpha=0.7)
    ax1.set_xlabel(r"Rotation Angle $\theta$ (deg)", fontsize=11)
    ax1.set_ylabel(r"Net Casimir Force $F_z$ (fN)", fontsize=11)
    ax1.set_title(r"(a) Concentric Ring Clutch $F_z(\theta)$ at $\langle d \rangle = 20\,$nm", fontsize=12, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(fontsize=9, loc="upper right")

    # Panel (b): Scale Truncation Boundary (P_max vs N)
    ax2 = axes[1]
    n_levels = [1, 2, 3]
    p_max_vals = []
    for gname in ["N1", "N2", "N3"]:
        g_data = groups[gname]
        if g_data:
            p_max = max(d["pressure_Pa"] for d in g_data)
            p_max_vals.append(p_max)
        else:
            p_max_vals.append(0.0)

    if any(p > 0 for p in p_max_vals):
        ax2.plot(n_levels, p_max_vals, "bo-", linewidth=2.2, markersize=8, label="Cantor Ring Hierarchy")
        if groups["Uniform"]:
            p_ctrl_max = max(d["pressure_Pa"] for d in groups["Uniform"])
            ax2.axhline(p_ctrl_max, color="purple", linestyle="--", linewidth=1.8, label="Uniform Grating Control")

    ax2.set_xlabel(r"Prefractal Generation $N$", fontsize=11)
    ax2.set_ylabel(r"Peak Repulsive Pressure $P_{\max}$ (Pa)", fontsize=11)
    ax2.set_title(r"(b) Electrodynamic Scale Truncation ($N=1 \to 3$)", fontsize=12, fontweight="bold")
    ax2.set_xticks([1, 2, 3])
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(fontsize=9, loc="lower right")

    # Panel (c): Chip-Scale Force on 100 um Disk vs. Thermal Noise Floor
    ax3 = axes[2]
    for gname in ["N2", "N3"]:
        g_data = groups[gname]
        if g_data:
            th = [d["theta_deg"] for d in g_data]
            f_chip = [d.get("chip_scale_100um", {}).get("force_net_nN", 0.0) for d in g_data]
            ax3.plot(th, f_chip, markers[gname], color=colors[gname], linewidth=2.2, markersize=7, label=f"Cantor {gname} ($100\,\mu$m disk)")

    ax3.axhspan(-0.001, 0.001, color="yellow", alpha=0.4, label=r"AFM Thermal Noise $\pm 1\,$pN")
    ax3.axhline(0, color="gray", linestyle="--", alpha=0.7)
    ax3.set_xlabel(r"Rotation Angle $\theta$ (deg)", fontsize=11)
    ax3.set_ylabel(r"Macroscopic Chip Force (nN)", fontsize=11)
    ax3.set_title(r"(c) Concentric Disk Force vs. Thermal Noise Floor", fontsize=12, fontweight="bold")
    ax3.grid(True, linestyle=":", alpha=0.6)
    ax3.legend(fontsize=9, loc="upper right")

    plt.tight_layout()
    fig_path = os.path.join(res_dir, "fig_concentric_ring_clutch.png")
    plt.savefig(fig_path, dpi=300)
    plt.close()
    print(f"Publication figure saved to {fig_path}")


if __name__ == "__main__":
    main()
