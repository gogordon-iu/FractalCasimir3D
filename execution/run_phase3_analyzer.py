#!/usr/bin/env python3
"""
Phase 3 Analyzer: Sweet Spot High-Resolution 3D Parameter Sweep (224 Tasks)
--------------------------------------------------------------------------
Inspects Phase 3 simulation results:
- 8 twist angles theta in [80, 94] deg
- 4 corrugation wall slopes alpha in [70, 85] deg
- 7 separation distances d in [50, 350] nm
- All corrugated runs with realistic physical rounded tips (r_tip = 5.0 nm)
- Extracts stable passive levitation equilibria d_eq and normal stiffness
- Updates Publication Tables 1 & 2 and Figures 2 & 3
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import argparse
import glob
import json
import math
import warnings
from datetime import datetime, timezone

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


MEEP_TO_PA = 0.0316152649


def finite_float(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def nonnegative_int(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if result < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return result


def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)


def get_expected_output_path(cfg):
    d = float(cfg["d"])
    N = int(cfg.get("N_top", 3))
    N_bot = int(cfg.get("N_bot", 3))
    corr = bool(cfg.get("corrugated", True))
    alpha = float(cfg.get("corrugation_angle", 45.0))
    rtip = float(cfg.get("r_tip_nm", 5.0))
    med = cfg.get("medium", "Vacuum")
    sieve = bool(cfg.get("stepped_sieve", False))
    mat = cfg.get("material", "Phosphorene_tuned")
    res = int(cfg.get("resolution", 40))
    theta = float(cfg["theta"])
    eps_bg = float(cfg.get("eps_bg", 2.1))
    L = float(cfg.get("L", 2.0))

    rtip_str = f"_rtip_{rtip:.1f}" if (corr and rtip > 0.0) else ""
    med_str = f"_med_{med}" if med and med not in ["Vacuum", "None"] else ""
    nbot_str = f"_corrugated_al_{alpha:.1f}{rtip_str}{med_str}_Nbot_{N_bot}" if corr else (f"_sieve_Nbot_{N_bot}" if sieve else (f"_Nbot_{N_bot}" if N_bot > 1 else ""))
    return f".tmp/meep_d_{d:.4f}_N_{N}{nbot_str}_{mat}_res_{res}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}.json"


def read_result_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        warnings.warn(f"Unable to read simulation result '{path}': {exc}")
        return None


def is_partial_record(record):
    task_idx = record.get("task_idx")
    if task_idx is None:
        return False
    task_idx = finite_float(task_idx)
    return task_idx is None or task_idx >= 0


def extract_pressure(record, cfg):
    f_both = record.get("force_both")
    f_self = record.get("force_self")
    if f_both is not None and f_self is not None:
        f_both = finite_float(f_both)
        f_self = finite_float(f_self)
        N = finite_float(cfg.get("N_top", 3))
        L = finite_float(cfg.get("L", 2.0))
        if (
            f_both is None or f_self is None or N is None or L is None
            or N < 1 or not N.is_integer() or L <= 0
        ):
            return None
        try:
            area = get_effective_area(int(N), L)
        except OverflowError:
            return None
        if not math.isfinite(area) or area <= 0:
            return None
        p_val = ((f_both - f_self) / area) * MEEP_TO_PA
    else:
        # pressure_Pa is already in SI units; do not convert it again.
        p_val = finite_float(record.get("pressure_Pa"))

    if p_val is None or not math.isfinite(p_val) or abs(p_val) < 1e-15:
        return None
    return p_val


def save_plot_provenance(path, metadata):
    """Persist the inputs, execution timestamp and conversion used by a plot."""
    with open(path + ".provenance.json", "w") as f:
        json.dump(metadata, f, indent=4, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=nonnegative_int,
        default=None,
        help="Maximum number of target configurations to analyze (default: all)."
    )
    args = parser.parse_args()
    executed_at = datetime.now(timezone.utc).isoformat()

    print("================================================================================")
    print("PHASE 3 RESULTS ANALYZER: SWEET SPOT 3D GRID & PASSIVE LEVITATION")
    print("================================================================================")

    config_files = sorted(glob.glob("sweep_configs_phase3/config_*.json"))
    if args.max_steps is not None:
        config_files = config_files[:args.max_steps]
    print(f"Loaded {len(config_files)} Phase 3 target task configurations.")
    if not config_files:
        raise RuntimeError("[ERROR: RUN_DATA_MISSING] No Phase 3 target configurations selected.")

    summary_files = sorted(glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json"))
    raw_records = []
    source_files = set()
    for fp in summary_files:
        data = read_result_json(fp)
        if isinstance(data, list):
            records = [r for r in data if isinstance(r, dict)]
            if len(records) != len(data):
                warnings.warn(f"Ignoring non-object records in '{fp}'.")
            raw_records.extend(records)
            source_files.add(fp)
        elif isinstance(data, dict) and "d_um" in data:
            raw_records.append(data)
            source_files.add(fp)
        elif data is not None:
            warnings.warn(f"Unrecognized simulation summary format in '{fp}'.")

    matched = []
    for cfg_path in config_files:
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                raise ValueError("configuration must be a JSON object")
            d_tgt = finite_float(cfg["d"])
            th_tgt = finite_float(cfg["theta"])
            al_tgt = finite_float(cfg["corrugation_angle"])
            r_tip_tgt = finite_float(cfg["r_tip_nm"])
            if any(v is None for v in (d_tgt, th_tgt, al_tgt, r_tip_tgt)):
                raise ValueError("target parameters must be finite numbers")
            if d_tgt <= 0:
                raise ValueError("separation must be positive")
            expected_fp = get_expected_output_path(cfg)
            task_id = cfg["task_id"]
            label = cfg["label"]
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise RuntimeError(f"Invalid Phase 3 configuration '{cfg_path}': {exc}") from exc

        best_match = None
        p_val = None
        if os.path.exists(expected_fp):
            r = read_result_json(expected_fp)
            if isinstance(r, dict) and not is_partial_record(r):
                candidate_pressure = extract_pressure(r, cfg)
                if candidate_pressure is not None:
                    best_match = r
                    p_val = candidate_pressure
                    source_files.add(expected_fp)
            elif r is not None:
                warnings.warn(f"Ignoring incomplete or invalid result '{expected_fp}'.")

        if best_match is None:
            best_score = -1
            for r in raw_records:
                # Reject partial single-moment runs.
                if is_partial_record(r):
                    continue

                alpha_r = finite_float(r.get("corrugation_angle", r.get("alpha_deg", 0.0)))
                is_corr = bool(r.get("corrugated", True)) or (alpha_r is not None and alpha_r > 0.0)
                if not is_corr:
                    continue

                res_r = finite_float(r.get("resolution", 40))
                if res_r != 40:
                    continue

                d_r = finite_float(r.get("d_um", r.get("d", -1)))
                theta_r = finite_float(r.get("theta_deg", r.get("theta", -1)))
                alpha_r = finite_float(r.get("corrugation_angle", r.get("alpha_deg", -1)))
                r_tip_r = finite_float(r.get("r_tip_nm", r.get("r_tip", 5.0)))
                if any(v is None for v in (d_r, theta_r, alpha_r, r_tip_r)):
                    continue

                if (
                    round(d_r, 4) == round(d_tgt, 4)
                    and round(theta_r, 1) == round(th_tgt, 1)
                    and round(alpha_r, 1) == round(al_tgt, 1)
                    and round(r_tip_r, 1) == round(r_tip_tgt, 1)
                ):
                    candidate_pressure = extract_pressure(r, cfg)
                    if candidate_pressure is None:
                        continue
                    score = res_r
                    if score > best_score:
                        best_score = score
                        best_match = r
                        p_val = candidate_pressure

        matched.append({
            "task_id": task_id,
            "label": label,
            "model": cfg.get("material", "Phosphorene_tuned"),
            "dataset": "phase3",
            "executed_at": executed_at,
            "alpha_deg": al_tgt,
            "theta_deg": th_tgt,
            "d_um": d_tgt,
            "r_tip_nm": r_tip_tgt,
            "pressure_Pa": p_val,
            "is_repulsive": bool(p_val is not None and p_val > 0.0),
            "status": "completed" if p_val is not None else "pending"
        })

    completed = [m for m in matched if m["status"] == "completed"]
    if not completed:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No valid, complete Phase 3 simulation results "
            "matched the selected configurations."
        )

    repulsive = [m for m in completed if m["is_repulsive"]]
    repulsive.sort(key=lambda x: x["pressure_Pa"], reverse=True)

    print(f"Phase 3 Status: {len(completed)} / {len(matched)} tasks completed.")
    print(f"Verified Repulsive Points: {len(repulsive)} / {len(completed)} ({len(repulsive)/len(completed)*100:.1f}%)")

    print("\nTop 15 Verified Repulsive Points (r_tip = 5 nm):")
    for p in repulsive[:15]:
        print(f"  alpha = {p['alpha_deg']:4.1f}° | theta = {p['theta_deg']:4.1f}° | d = {p['d_um']*1000:5.1f} nm | P = {p['pressure_Pa']:+9.6f} Pa")

    # Detect Passive Levitation Equilibria.
    curves = {}
    for r in completed:
        k = (r["alpha_deg"], r["theta_deg"])
        curves.setdefault(k, []).append(r)

    eq_points = []
    for (a, th), pts in curves.items():
        pts.sort(key=lambda x: x["d_um"])
        d_arr = [p["d_um"] for p in pts]
        p_arr = [p["pressure_Pa"] for p in pts]
        for i in range(len(p_arr) - 1):
            if p_arr[i] > 0 and p_arr[i+1] < 0:
                d1, d2 = d_arr[i], d_arr[i+1]
                p1, p2 = p_arr[i], p_arr[i+1]
                delta_d_m = (d2 - d1) * 1e-6
                delta_p = p2 - p1
                if delta_d_m <= 0 or not math.isfinite(delta_p):
                    continue
                d_eq = d1 + (0.0 - p1) * (d2 - d1) / delta_p
                stiffness = -delta_p / delta_d_m
                if not math.isfinite(d_eq) or not math.isfinite(stiffness):
                    continue
                eq_points.append({
                    "alpha": a,
                    "theta": th,
                    "d_eq_nm": d_eq * 1000.0,
                    "p_max": max(p_arr),
                    "stiffness_Pa_per_m": stiffness
                })

    eq_points.sort(key=lambda x: x["p_max"], reverse=True)
    print(f"\nStable Passive Levitation Equilibria Found: {len(eq_points)}")
    for eq in eq_points[:15]:
        print(f"  alpha = {eq['alpha']:4.1f}° | theta = {eq['theta']:4.1f}° | d_eq = {eq['d_eq_nm']:6.2f} nm | P_max = {eq['p_max']:+9.4f} Pa | K_z = {eq['stiffness_Pa_per_m']:9.2e} Pa/m")

    # Update Table 1: Sweet Spot Repulsion Table.
    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)
    tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_sweet_spot_repulsion.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated Phase 3 Sweet Spot Repulsion Table (r_tip = 5.0 nm)\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write("\\caption{Phase 3: Verified Repulsive Casimir Pressures across $(\\alpha, \\theta, d)$ with Realistic Rounded Tips ($r_{\\rm tip} = 5.0\\text{ nm}$).}\n")
        f.write("\\label{tab:sweet_spot_repulsion}\n")
        f.write("\\begin{tabular}{ccccc}\n\\toprule\n")
        f.write("\\textbf{Corrugation $\\alpha$} & \\textbf{Twist $\\theta$} & \\textbf{Separation $d$ (nm)} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Regime} \\\\\n\\midrule\n")
        for p in repulsive[:20]:
            f.write(f"${p['alpha_deg']:.1f}^\\circ$ & ${p['theta_deg']:.1f}^\\circ$ & ${p['d_um']*1000:.1f}$ nm & $\\mathbf{{{p['pressure_Pa']:+9.6f}}}$ & \\textbf{{REPULSIVE}} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"\nUpdated Table 1: '{tex_path}'.")

    # Update Table 2: Levitation Equilibria Table.
    lev_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_levitation_equilibria.tex"
    with open(lev_path, "w") as f:
        f.write("% Auto-generated Phase 3 Levitation Equilibria Table (r_tip = 5.0 nm)\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write("\\caption{Phase 3: Passive Levitation Equilibrium Gaps ($d_{\\rm eq}$ where $P=0, \\partial P/\\partial d < 0$) with Realistic Rounded Tips ($r_{\\rm tip} = 5.0\\text{ nm}$).}\n")
        f.write("\\label{tab:levitation_equilibria}\n")
        f.write("\\begin{tabular}{ccccc}\n\\toprule\n")
        f.write("\\textbf{Corrugation $\\alpha$} & \\textbf{Twist $\\theta$} & \\textbf{Peak Pressure $P_{\\max}$ (Pa)} & \\textbf{Equilibrium Gap $d_{\\rm eq}$ (nm)} & \\textbf{Stability} \\\\\n\\midrule\n")
        for eq in eq_points[:22]:
            f.write(f"${eq['alpha']:.1f}^\\circ$ & ${eq['theta']:.1f}^\\circ$ & ${eq['p_max']:+9.4f}$ Pa & $\\mathbf{{{eq['d_eq_nm']:.2f}\\text{{ nm}}}}$ & \\textbf{{Stable Levitation}} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"Updated Table 2: '{lev_path}'.")

    provenance = {
        "script": os.path.relpath(__file__, REPO_ROOT),
        "model": sorted(set(m["model"] for m in completed)),
        "dataset": "phase3",
        "status": "completed",
        "executed_at": executed_at,
        "config_files": config_files,
        "source_files": sorted(source_files),
        "max_steps": args.max_steps,
        "meep_to_pa": MEEP_TO_PA,
        "pressure_units": "Pa",
        "stiffness_units": "Pa/m"
    }

    # Generate Figures 2 & 3.
    os.makedirs("Papers/Fractal_Casimir_Nature_EM/figures", exist_ok=True)
    plt.figure(figsize=(7, 5))
    colors = ["#1f77b4", "#2ca02c", "#d62728", "#9467bd"]
    sample_curves = [((75.0, 82.0), colors[0]), ((70.0, 80.0), colors[1]), ((75.0, 94.0), colors[2]), ((70.0, 88.0), colors[3])]
    for (key, col) in sample_curves:
        if key in curves:
            c_pts = sorted(curves[key], key=lambda x: x["d_um"])
            ds_nm = [p["d_um"] * 1000.0 for p in c_pts]
            ps = [p["pressure_Pa"] for p in c_pts]
            plt.plot(ds_nm, ps, "o-", color=col, lw=2, ms=6, label=f"$\\alpha={key[0]}^\\circ, \\theta={key[1]}^\\circ$ ($r_{{\\rm tip}}=5$ nm)")
    plt.axhline(0, color="black", ls="--", lw=1.2, label="Zero-Pressure Bound ($P=0$)")
    plt.xlabel("Plate Separation $d$ (nm)", fontsize=12)
    plt.ylabel("Casimir Normal Pressure $P$ (Pa)", fontsize=12)
    plt.title("Figure 2: Nanomechanical Passive Levitation Traps ($r_{\\rm tip} = 5.0$ nm)", fontsize=13, pad=12)
    plt.grid(True, alpha=0.3)
    plt.legend(frameon=True)
    plt.tight_layout()
    fig2_path = "Papers/Fractal_Casimir_Nature_EM/figures/fig2_levitation_curves.png"
    plt.savefig(fig2_path, dpi=300)
    plt.close()
    save_plot_provenance(fig2_path, provenance)
    print(f"Generated Figure 2: '{fig2_path}'.")

    # Figure 3: 2D Phase Diagram. Missing points must not appear as zero pressure.
    plt.figure(figsize=(7, 5))
    d100_pts = [p for p in completed if round(p["d_um"], 2) == 0.10]
    if d100_pts:
        th_list = sorted(set(p["theta_deg"] for p in d100_pts))
        al_list = sorted(set(p["alpha_deg"] for p in d100_pts))
        P_grid = np.full((len(al_list), len(th_list)), np.nan)
        for i, a in enumerate(al_list):
            for j, th in enumerate(th_list):
                match = [p for p in d100_pts if p["alpha_deg"] == a and p["theta_deg"] == th]
                if match:
                    P_grid[i, j] = match[0]["pressure_Pa"]
        masked_grid = np.ma.masked_invalid(P_grid)
        c = plt.pcolormesh(th_list, al_list, masked_grid, shading="auto", cmap="RdBu_r", vmin=-0.5, vmax=0.5)
        plt.colorbar(c, label="Pressure $P$ (Pa)")
        finite_pressures = P_grid[np.isfinite(P_grid)]
        if (
            len(al_list) >= 2 and len(th_list) >= 2
            and finite_pressures.size
            and finite_pressures.min() < 0 < finite_pressures.max()
        ):
            plt.contour(th_list, al_list, masked_grid, levels=[0.0], colors="black", linewidths=2)
    plt.xlabel(r"Twist Angle $\theta$ (deg)", fontsize=12)
    plt.ylabel(r"Corrugation Angle $\alpha$ (deg)", fontsize=12)
    plt.title(r"Figure 3: 2D Casimir Repulsion Phase Diagram ($d=100$ nm, $r_{\rm tip}=5$ nm)", fontsize=13, pad=12)
    plt.tight_layout()
    fig3_path = "Papers/Fractal_Casimir_Nature_EM/figures/fig3_phase_diagram.png"
    plt.savefig(fig3_path, dpi=300)
    plt.close()
    save_plot_provenance(fig3_path, provenance)
    print(f"Generated Figure 3: '{fig3_path}'.")

    # Preserve the per-task summary list while adding freshness metadata.
    os.makedirs("results_phase3", exist_ok=True)
    summary_path = "results_phase3/phase3_summary.json"
    with open(summary_path, "w") as f:
        json.dump(matched, f, indent=4, allow_nan=False)
    print(f"Saved Phase 3 summary to '{summary_path}'.")

    from utils.metrics_logger import log_metrics

    log_metrics(
        model="Phosphorene_tuned",
        dataset="phase3",
        metrics={
            "status": "completed",
            "executed_at": executed_at,
            "tasks_completed": len(completed),
            "tasks_total": len(matched),
            "repulsive_points": len(repulsive),
            "repulsive_fraction": len(repulsive) / len(completed),
            "stable_equilibria": len(eq_points)
        }
    )

    # Auto-sync the artifacts actually generated by this analyzer.
    from execution.git_sync import git_sync_results
    git_sync_results(
        "phase3",
        [
            summary_path,
            tex_path,
            lev_path,
            fig2_path,
            fig2_path + ".provenance.json",
            fig3_path,
            fig3_path + ".provenance.json"
        ],
        len(completed),
        len(matched)
    )
    print("================================================================================")


if __name__ == "__main__":
    main()
