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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import argparse
import glob
import json
import math
from datetime import datetime, timezone

# Auto-detect and switch to meep conda environment if available
try:
    import numpy as np
except ImportError:
    candidates = [
        os.path.expanduser("~/.conda/envs/meep/bin/python"),
        "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python",
        os.path.expanduser("~/miniconda3/envs/meep/bin/python"),
        os.path.expanduser("~/anaconda3/envs/meep/bin/python"),
        "/N/soft/rhel8/miniconda3/envs/meep/bin/python",
    ]
    for candidate in candidates:
        if os.path.exists(candidate) and sys.executable != candidate:
            print(f"[Auto-Env] Switching to MEEP environment: {candidate}")
            os.execv(candidate, [candidate] + sys.argv)
    np = None

MEEP_TO_PA = 0.0316152649


def get_effective_area(N, L):
    return ((8.0 / 9.0) ** (N - 1)) * (L ** 2)


def linear_fit(x_arr, y_arr):
    if len(x_arr) != len(y_arr):
        raise ValueError("linear_fit requires equally sized inputs.")

    x_arr = [float(x) for x in x_arr]
    y_arr = [float(y) for y in y_arr]
    if not all(math.isfinite(v) for v in x_arr + y_arr):
        raise ValueError("linear_fit requires finite inputs.")

    n = len(x_arr)
    if n < 2:
        return 0.0, 0.0
    mean_x = sum(x_arr) / n
    mean_y = sum(y_arr) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_arr, y_arr))
    var = sum((x - mean_x) ** 2 for x in x_arr)
    slope = cov / var if var != 0 else 0.0
    intercept = mean_y - slope * mean_x
    return slope, intercept


def get_expected_output_path(cfg):
    d = float(cfg["d"])
    N = int(cfg["N_top"])
    N_bot = int(cfg.get("N_bot", 1))
    corr = bool(cfg.get("corrugated", False))
    alpha = float(cfg.get("corrugation_angle", 0.0))
    rtip = float(cfg.get("r_tip_nm", 0.0))
    med = cfg.get("medium", "Vacuum")
    sieve = bool(cfg.get("stepped_sieve", False))
    mat = cfg["material"]
    res = int(cfg.get("resolution", 40))
    theta = float(cfg["theta"])
    eps_bg = float(cfg["eps_bg"])
    L = float(cfg["L"])

    rtip_str = f"_rtip_{rtip:.1f}" if (corr and rtip > 0.0) else ""
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


def nonnegative_int(value):
    try:
        number = int(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=nonnegative_int,
        default=None,
        help="Maximum number of task configurations to analyze (default: all).",
    )
    args = parser.parse_args()
    executed_at = datetime.now(timezone.utc).isoformat()

    print("================================================================================")
    print("PHASE 1 RESULTS ANALYZER: GENERAL PARAMETERS & FUNDAMENTAL BASELINES")
    print("================================================================================")

    config_files = sorted(glob.glob("sweep_configs_phase1/config_*.json"))
    if args.max_steps is not None:
        config_files = config_files[:args.max_steps]
    print(f"Loaded {len(config_files)} Phase 1 target task configurations.")

    if not config_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No Phase 1 task configurations "
            "are available within the requested --max-steps limit."
        )

    # Match each Phase 1 config to available results using fast direct lookup.
    matched = []
    for cfg_path in config_files:
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                raise ValueError("configuration must be a JSON object")

            d_tgt = float(cfg["d"])
            N_tgt = int(cfg["N_top"])
            mat_tgt = cfg["material"]
            th_tgt = float(cfg["theta"])
            eps_tgt = float(cfg["eps_bg"])
            L_tgt = float(cfg["L"])
            if not all(math.isfinite(v) for v in (d_tgt, th_tgt, eps_tgt, L_tgt)):
                raise ValueError("configuration parameters must be finite")
            if N_tgt < 1:
                raise ValueError("N_top must be at least 1")

            expected_fp = get_expected_output_path(cfg)
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise RuntimeError(
                f"[ERROR: RUN_DATA_INVALID] Invalid configuration '{cfg_path}': {exc}"
            ) from exc

        best_match = None
        if os.path.exists(expected_fp):
            try:
                with open(expected_fp, "r") as f:
                    result = json.load(f)
                if not isinstance(result, dict):
                    raise ValueError("result must be a JSON object")
                if "task_idx" not in result:
                    best_match = result
                else:
                    print(
                        f"[WARNING] Ignoring task metadata rather than simulation "
                        f"results in '{expected_fp}'.",
                        file=sys.stderr,
                    )
            except (OSError, ValueError, TypeError) as exc:
                print(
                    f"[WARNING] Cannot read results '{expected_fp}': {exc}",
                    file=sys.stderr,
                )

        p_val = None
        if best_match is not None:
            try:
                f_both = best_match.get("force_both")
                f_self = best_match.get("force_self")
                p_dir = best_match.get("pressure_Pa")
                if f_both is not None and f_self is not None:
                    A_eff = get_effective_area(N_tgt, L_tgt)
                    if not math.isfinite(A_eff) or A_eff <= 0.0:
                        raise ValueError("effective area must be finite and positive")
                    p_val = (
                        (float(f_both) - float(f_self)) / float(A_eff)
                    ) * MEEP_TO_PA
                elif p_dir is not None:
                    # pressure_Pa is already expressed in SI units.
                    p_val = float(p_dir)

                if p_val is not None and (
                    not math.isfinite(p_val) or abs(p_val) < 1e-15
                ):
                    raise ValueError("pressure must be finite and non-zero")
            except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
                print(
                    f"[WARNING] Invalid pressure in '{expected_fp}': {exc}",
                    file=sys.stderr,
                )
                p_val = None

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
            "model": "meep",
            "dataset": "phase1",
            "status": "completed" if p_val is not None else "pending",
            "executed_at": executed_at,
        })

    completed = [m for m in matched if m["status"] == "completed"]
    print(f"Phase 1 Status: {len(completed)} / {len(matched)} tasks completed.")

    for m in matched:
        p_str = (
            f"{m['pressure_Pa']:+9.6f} Pa"
            if m["pressure_Pa"] is not None
            else "Pending / Running"
        )
        regime = (
            ("REPULSIVE" if m["pressure_Pa"] > 0 else "Attractive")
            if m["pressure_Pa"] is not None
            else "---"
        )
        print(
            f"  Task {m['task_id']:02d}: {m['label']:<60} "
            f"| P = {p_str} | {regime}"
        )

    if not completed:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No valid, completed Phase 1 simulation "
            "results were found for the selected configurations."
        )

    # 1. Lifshitz Distance Power Law Check
    lifshitz = [m for m in completed if m["tier"] == "tier1_lifshitz_scaling"]
    valid_lifshitz = [
        m for m in lifshitz
        if abs(m["pressure_Pa"]) > 1e-12 and m["d_um"] > 0
    ]
    lifshitz_slope = None
    if (
        len(valid_lifshitz) >= 2
        and len({m["d_um"] for m in valid_lifshitz}) >= 2
    ):
        log_d = [math.log(m["d_um"]) for m in valid_lifshitz]
        log_p = [math.log(abs(m["pressure_Pa"])) for m in valid_lifshitz]
        lifshitz_slope, intercept = linear_fit(log_d, log_p)
        print(
            f"\n* Lifshitz Distance Scaling: Fitted |P(d)| ~ "
            f"d^({lifshitz_slope:.2f}) [Theory: d^-4.00, points: "
            f"{len(valid_lifshitz)}/{len(lifshitz)}]"
        )
    else:
        print(
            "\n* Lifshitz Distance Scaling: Awaiting completed non-zero "
            "datapoints at distinct distances."
        )

    # 2. Fractal Area Law Check
    area_tasks = [m for m in completed if m["tier"] == "tier1_fractal_area_law"]
    valid_area = [m for m in area_tasks if abs(m["pressure_Pa"]) > 1e-12]
    area_ratio = None
    if len(valid_area) >= 2:
        valid_area.sort(key=lambda x: x["N"])
        p_first = abs(valid_area[0]["pressure_Pa"])
        p_last = abs(valid_area[-1]["pressure_Pa"])
        area_ratio = p_last / p_first
        print(
            f"* Fractal Area Law Scaling: N={valid_area[0]['N']} to "
            f"{valid_area[-1]['N']} Ratio = {area_ratio:.4f} "
            "[Theory: (8/9)^(N-1)]"
        )
    else:
        print(
            "* Fractal Area Law Scaling: Awaiting completed non-zero "
            "fractal generation datapoints."
        )

    # Write LaTeX Table. No figures are saved by this analyzer, so there are
    # no saved figures requiring a save_plot_provenance call.
    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)
    tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_phase1_baselines.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated Phase 1 Casimir Baselines Table\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write("\\caption{Phase 1: Fundamental Casimir Baselines and Scaling Laws "
                "($d=100\\text{ nm}$, uncorrugated).}\n")
        f.write("\\label{tab:phase1_baselines}\n")
        f.write("\\begin{tabular}{ccccc}\n\\toprule\n")
        f.write("\\textbf{Material} & \\textbf{Prefractal $N$} & "
                "\\textbf{Twist $\\theta$} & \\textbf{Pressure $P$ (Pa)} & "
                "\\textbf{Physical Regime} \\\\\n\\midrule\n")
        for m in matched[:15]:
            p_str = (
                f"${m['pressure_Pa']:+9.6f}$ Pa"
                if m["pressure_Pa"] is not None
                else "Pending"
            )
            reg_str = (
                ("\\textbf{REPULSIVE}" if m["pressure_Pa"] > 0 else "Attractive")
                if m["pressure_Pa"] is not None
                else "Pending"
            )
            f.write(
                f"{m['material']} & $N={m['N']}$ & "
                f"${m['theta_deg']:.1f}^\\circ$ & {p_str} & {reg_str} \\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"\nGenerated Phase 1 Table: '{tex_path}'.")

    # Preserve the summary's list-of-task-records interface.
    os.makedirs("results_phase1", exist_ok=True)
    with open("results_phase1/phase1_summary.json", "w") as f:
        json.dump(matched, f, indent=4, allow_nan=False)
    print("Saved Phase 1 summary to 'results_phase1/phase1_summary.json'.")

    # Keep standalone analysis usable when the repository logging utility
    # is not installed; do not hide import failures inside that utility.
    try:
        import utils.metrics_logger as metrics_logger
    except ModuleNotFoundError as exc:
        if exc.name not in ("utils", "utils.metrics_logger"):
            raise
        print(
            "[WARNING] utils.metrics_logger is unavailable; metrics logging skipped.",
            file=sys.stderr,
        )
    else:
        metrics_logger.log_metrics({
            "model": "meep",
            "dataset": "phase1",
            "status": "completed",
            "executed_at": executed_at,
            "completed_tasks": len(completed),
            "total_tasks": len(matched),
            "max_steps": args.max_steps,
            "lifshitz_slope": lifshitz_slope,
            "fractal_area_ratio": area_ratio,
        })

    # Auto-sync results to GitHub
    from execution.git_sync import git_sync_results
    git_sync_results(
        "phase1",
        [
            "results_phase1/phase1_summary.json",
            "Papers/Fractal_Casimir_Nature_EM/tables/table_phase1_baselines.tex",
        ],
        len(completed),
        len(matched),
    )
    print("================================================================================")


if __name__ == "__main__":
    main()
