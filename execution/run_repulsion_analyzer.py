#!/usr/bin/env python3
"""
Vacuum Casimir Repulsion Campaign: Phase 1 Results Analyzer (Archetypes 1 & 2)
------------------------------------------------------------------------------
Evaluates first-principles Casimir pressure in SI Pascals, reports repulsive
results, and generates summary data, publication tables, and comparative figures.
"""

import argparse
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Auto-detect and switch to meep conda environment if dependencies are missing.
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
        "/N/soft/rhel8/miniconda3/envs/meep/bin/python",
    ]:
        if os.path.exists(candidate) and sys.executable != candidate:
            print(
                f"[Auto-Env] Switching from {sys.executable} "
                f"to MEEP conda environment: {candidate}"
            )
            os.execv(candidate, [candidate] + sys.argv)
    print("ERROR: 'numpy' or 'matplotlib' not found. Please activate the meep environment:")
    print("       conda activate meep")
    sys.exit(1)

MEEP_TO_PA = 0.0316152649
MODEL = "repulsion_phase1"
DATASET = "sweep_configs_repulsion"


def finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def get_effective_area(N, L):
    n = finite_number(N, "N")
    length = finite_number(L, "L")
    if n < 1 or not n.is_integer() or length <= 0:
        raise ValueError("N must be a positive integer and L must be positive")
    try:
        area = ((8.0 / 9.0) ** (n - 1)) * (length ** 2)
    except OverflowError as exc:
        raise ValueError("Effective area must be finite and positive") from exc
    if not math.isfinite(area) or area <= 0:
        raise ValueError("Effective area must be finite and positive")
    return area


def get_expected_output_path(cfg):
    d = float(cfg["d"])
    N = int(cfg["N_top"])
    N_bot = int(cfg.get("N_bot", 1))
    corr = bool(cfg.get("corrugated", True))
    alpha = float(cfg.get("corrugation_angle", 75.0))
    rtip = float(cfg.get("r_tip_nm", 0.0))
    med = cfg.get("medium", "Vacuum")
    sieve = bool(cfg.get("stepped_sieve", False))
    mat = cfg["material"]
    res = int(cfg.get("resolution", 40))
    theta = float(cfg["theta"])
    eps_bg = float(cfg.get("eps_bg", 1.0))
    L = float(cfg.get("L", 2.0))

    rtip_str = f"_rtip_{rtip:.1f}" if corr and rtip > 0.0 else ""
    med_str = f"_med_{med}" if med and med not in ["Vacuum", "None"] else ""
    nbot_str = (
        f"_corrugated_al_{alpha:.1f}{rtip_str}{med_str}_Nbot_{N_bot}"
        if corr
        else (
            f"_sieve_Nbot_{N_bot}"
            if sieve
            else (f"_Nbot_{N_bot}" if N_bot > 1 else "")
        )
    )
    return (
        f".tmp/meep_d_{d:.4f}_N_{N}{nbot_str}_{mat}_res_{res}"
        f"_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}.json"
    )


def find_record(path):
    if os.path.isfile(path):
        return path
    root_path = os.path.join(REPO_ROOT, path)
    if os.path.isfile(root_path):
        return root_path
    return None


def read_record(path):
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return data
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"[ERROR: RUN_DATA_MISSING] Cannot read valid record '{path}': {exc}"
        ) from exc


def optional_number(data, key):
    value = data.get(key)
    return None if value is None else finite_number(value, key)


def nonnegative_steps(value):
    try:
        steps = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--max-steps must be an integer") from exc
    if steps < 0:
        raise argparse.ArgumentTypeError("--max-steps must be nonnegative")
    return steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=nonnegative_steps,
        default=None,
        help="Maximum number of configurations to analyze (default: all).",
    )
    args = parser.parse_args()

    print("================================================================================")
    print("VACUUM CASIMIR REPULSION ANALYZER: ARCHETYPES 1 & 2 SCREENING")
    print("================================================================================")

    config_files = sorted(glob.glob("sweep_configs_repulsion/config_*.json"))
    if not config_files:
        config_files = sorted(
            glob.glob(os.path.join(REPO_ROOT, "sweep_configs_repulsion/config_*.json"))
        )
    if not config_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] Input directory or configuration records "
            "are missing: sweep_configs_repulsion/config_*.json"
        )
    if args.max_steps is not None:
        config_files = config_files[:args.max_steps]
    if not config_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No configurations selected for analysis."
        )

    print(f"Loaded {len(config_files)} target repulsion configurations.")

    executed_at = datetime.now(timezone.utc).isoformat()
    matched = []
    for fp in config_files:
        cfg = read_record(fp)
        try:
            # Normalize numeric configuration fields used in calculations and output.
            for key in ("d", "theta"):
                cfg[key] = finite_number(cfg[key], key)
            for key, default in (
                ("L", 2.0),
                ("corrugation_angle", 75.0),
                ("r_tip_nm", 0.0),
                ("eps_bg", 1.0),
            ):
                cfg[key] = finite_number(cfg.get(key, default), key)
            for key, default in (("N_top", None), ("N_bot", 1), ("resolution", 40)):
                number = finite_number(cfg.get(key, default), key)
                if not number.is_integer() or number < 1:
                    raise ValueError(f"{key} must be a positive integer")
                cfg[key] = int(number)
            get_effective_area(cfg["N_top"], cfg["L"])

            expected_fp = get_expected_output_path(cfg)
            final_fp = find_record(expected_fp)
            p_val = None
            f_sub = None
            f_both = None
            f_self = None

            if final_fp is not None:
                data = read_record(final_fp)
                p_val = optional_number(data, "pressure_Pa")
                f_sub = optional_number(data, "force_subtracted")
                f_both = optional_number(data, "force_both")
                f_self = optional_number(data, "force_self")
                if p_val is None:
                    raise ValueError(f"Missing pressure_Pa in '{final_fp}'")
            else:
                # Checkpoint fallback if the final subtracted file is not written.
                corr = bool(cfg.get("corrugated", True))
                rtip = cfg["r_tip_nm"]
                rtip_str = f"_rtip_{rtip:.1f}" if corr and rtip > 0 else ""
                geom_tag = (
                    f"_corr_al_{cfg['corrugation_angle']:.1f}{rtip_str}"
                    if corr
                    else "_planar"
                )
                chk_tag = (
                    f"v3_d_{cfg['d']:.4f}_Ntop_{cfg['N_top']}"
                    f"_Nbot_{cfg['N_bot']}_mat_{cfg['material']}"
                    f"_res_{cfg['resolution']}_th_{cfg['theta']:.1f}"
                    f"{geom_tag}_L_{cfg['L']:.2f}"
                )
                # Keep checkpoint pairs together; do not mix independent run roots.
                for base in (".tmp", os.path.join(REPO_ROOT, ".tmp")):
                    chk_b = os.path.join(base, f"chk_{chk_tag}_both.json")
                    chk_s = os.path.join(base, f"chk_{chk_tag}_self.json")
                    if os.path.isfile(chk_b) and os.path.isfile(chk_s):
                        f_both = finite_number(read_record(chk_b)["force"], "force_both")
                        f_self = finite_number(read_record(chk_s)["force"], "force_self")
                        f_sub = finite_number(f_both - f_self, "force_subtracted")
                        A_eff = get_effective_area(cfg["N_top"], cfg["L"])
                        p_val = finite_number(
                            (f_sub / A_eff) * MEEP_TO_PA, "pressure_Pa"
                        )
                        break

            matched.append({
                "task_id": int(finite_number(cfg["task_id"], "task_id")),
                "archetype": str(cfg.get("archetype", "unknown")),
                "label": cfg["label"],
                "d_um": cfg["d"],
                "N_top": cfg["N_top"],
                "N_bot": cfg["N_bot"],
                "corrugated": cfg.get("corrugated", False),
                "corrugation_angle": cfg["corrugation_angle"],
                "r_tip_nm": cfg["r_tip_nm"],
                "theta_deg": cfg["theta"],
                "pressure_Pa": p_val,
                "force_subtracted": f_sub,
                "force_both": f_both,
                "force_self": f_self,
                "status": "COMPLETED" if p_val is not None else "PENDING",
            })
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError(
                f"[ERROR: RUN_DATA_MISSING] Invalid configuration or run record "
                f"for '{fp}': {exc}"
            ) from exc

    completed = [m for m in matched if m["status"] == "COMPLETED"]
    if not completed:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No valid completed JSON records or "
            "both/self checkpoint pairs were found for the selected configurations."
        )
    repulsive = [m for m in completed if m["pressure_Pa"] > 0]

    print(f"Repulsion Screening Status: {len(completed)} / {len(matched)} tasks completed.")
    print(f"Repulsive States Discovered (P > 0): {len(repulsive)}")

    archetypes = [
        ("corrugated_over_flat", "1. Corrugated Top (N=3) vs. Flat Bottom (N=1)"),
        ("hierarchical_corrugations", "2. Hierarchical Corrugations (N=3 vs. N=2)"),
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
            print(
                f"  Task {it['task_id']:2d} | d={it['d_um'] * 1000:4.0f}nm "
                f"| th={it['theta_deg']:5.1f}deg | P = {p_str} | {flag}"
            )

    print("\n================================================================================")
    print("RANKING: TOP CANDIDATES CLOSEST TO OR EXCEEDING REPULSION (P > 0)")
    print("================================================================================")
    ranked = sorted(completed, key=lambda x: x["pressure_Pa"], reverse=True)
    for rank, it in enumerate(ranked[:10], 1):
        p = it["pressure_Pa"]
        status_tag = ">>> REPULSIVE <<<" if p > 0 else "Suppressed Attraction"
        print(
            f"  #{rank:2d}: Task {it['task_id']:2d} ({it['archetype']}) "
            f"| d={it['d_um'] * 1000:.0f}nm, th={it['theta_deg']:.1f}deg "
            f"-> P = {p:+10.6e} Pa [{status_tag}]"
        )

    metrics = {
        "completed_tasks": len(completed),
        "total_tasks": len(matched),
        "repulsive_states": len(repulsive),
    }
    summary = {
        "model": MODEL,
        "dataset": DATASET,
        "status": "completed",
        "executed_at": executed_at,
        "max_steps": args.max_steps,
        "metrics": metrics,
        "results": matched,
    }
    os.makedirs("results_repulsion", exist_ok=True)
    summary_path = "results_repulsion/repulsion_phase1_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=4, allow_nan=False)
    print(f"\nSaved summary dataset to '{summary_path}'.")

    from utils.metrics_logger import log_metrics

    log_metrics(model=MODEL, dataset=DATASET, metrics=metrics)

    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)
    tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_repulsion_screening.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated Vacuum Casimir Repulsion Screening Table (Archetypes 1 & 2)\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write("\\caption{Phase 1: Vacuum Casimir Repulsion Screening Across Archetypes 1 and 2 ($\\epsilon_{\\rm bg}=1.0$).}\n")
        f.write("\\label{tab:repulsion_screening}\n")
        f.write("\\begin{tabular}{ccccccc}\n\\toprule\n")
        f.write("\\textbf{Archetype} & $N_{\\rm top}$ & $N_{\\rm bot}$ & \\textbf{Gap $d$} & \\textbf{Twist $\\theta$} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Regime} \\\\\n\\midrule\n")
        for m in matched:
            p_str = (
                f"${m['pressure_Pa']:+9.6f}$ Pa"
                if m["pressure_Pa"] is not None
                else "Pending"
            )
            if m["pressure_Pa"] is not None:
                reg_str = (
                    "\\textbf{Repulsive ($P>0$)}"
                    if m["pressure_Pa"] > 0
                    else "Attractive"
                )
            else:
                reg_str = "Pending"
            f.write(
                f"{m['archetype'][:18]} & {m['N_top']} & {m['N_bot']} "
                f"& ${m['d_um'] * 1000:.0f}\\text{{ nm}}$ "
                f"& ${m['theta_deg']:.1f}^\\circ$ & {p_str} & {reg_str} \\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"Generated Publication Table: '{tex_path}'.")

    os.makedirs("Papers/Fractal_Casimir_Nature_EM/figures", exist_ok=True)
    fig_path = "Papers/Fractal_Casimir_Nature_EM/figures/fig_repulsion_screening.png"
    plt.figure(figsize=(9, 5.5))
    colors = {
        "corrugated_over_flat": "#1f77b4",
        "hierarchical_corrugations": "#ff7f0e",
    }
    markers = {0.05: "o", 0.10: "s", 0.20: "^"}

    for arch_key, arch_title in archetypes:
        sub = [m for m in completed if m["archetype"] == arch_key]
        for d_val, marker in markers.items():
            sub_d = [m for m in sub if abs(m["d_um"] - d_val) < 1e-4]
            if sub_d:
                xs = [m["theta_deg"] for m in sub_d]
                ys = [m["pressure_Pa"] for m in sub_d]
                plt.scatter(
                    xs,
                    ys,
                    s=70,
                    color=colors.get(arch_key, "black"),
                    marker=marker,
                    label=f"{arch_title[:28]} (d={int(d_val * 1000)}nm)",
                    alpha=0.85,
                )

    plt.axhline(
        0, color="red", linestyle="--", linewidth=1.5,
        label="Zero Pressure Boundary (P=0)",
    )
    plt.xlabel(r"Twist Angle $\theta$ (degrees)", fontsize=12)
    plt.ylabel(r"Casimir Pressure $P$ (Pa)", fontsize=12)
    plt.title(
        "Vacuum Casimir Repulsion Screening: Archetypes 1 & 2 ($P > 0$ Search)",
        fontsize=13,
        pad=12,
    )
    plt.legend(frameon=True, fontsize=9)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    try:
        plt.savefig(fig_path, dpi=300)
    finally:
        plt.close()

    from utils.plot_provenance import save_plot_provenance

    save_plot_provenance(
        fig_path,
        {
            "model": MODEL,
            "dataset": DATASET,
            "status": "completed",
            "executed_at": executed_at,
            "source": summary_path,
            "config_files": config_files,
            "max_steps": args.max_steps,
            "checkpoint_pressure_conversion": MEEP_TO_PA,
        },
    )
    print(f"Generated Comparative Figure: '{fig_path}'.")

    from execution.git_sync import git_sync_results

    git_sync_results(
        "repulsion_phase1",
        [summary_path, tex_path, fig_path],
        len(completed),
        len(matched),
    )
    print("================================================================================")


if __name__ == "__main__":
    main()
