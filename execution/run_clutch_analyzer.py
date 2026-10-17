#!/usr/bin/env python3
"""
Fractal Quantum Clutch: Results Analyzer
----------------------------------------
Analyzes the Quantum Clutch screening suite (Menger Spire vs Sierpinski Sieve)
demonstrating the rotation-driven force inversion from Casimir Repulsion (P > 0)
to Attraction (P < 0) in pure vacuum.
"""

import argparse
import glob
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

MEEP_TO_PA = 0.0316152649
MODEL = "quantum_clutch"
DATASET = "sweep_configs_clutch"


def finite_float(value):
    """Return a finite numeric value, or None for invalid/missing data."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def get_effective_area(N, L):
    n = finite_float(N)
    length = finite_float(L)
    if n is None or not n.is_integer() or n < 1:
        raise ValueError("N must be a positive integer")
    if length is None or length <= 0:
        raise ValueError("L must be finite and positive")
    area = ((8.0 / 9.0) ** (int(n) - 1)) * (length ** 2)
    if not math.isfinite(area) or area <= 0:
        raise ValueError("Effective area must be finite and positive")
    return area


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
    return (
        f".tmp/meep_d_{d:.4f}_N_{N}{nbot_str}_{mat}_res_{res}"
        f"_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}.json"
    )


def read_json_object(path):
    with open(path, "r") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def nonnegative_int(value):
    try:
        number = int(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from err
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=nonnegative_int,
        default=None,
        help="Maximum number of configurations to analyze (default: all).",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("FRACTAL QUANTUM CLUTCH ANALYZER (MENGER SPIRE VS SIERPINSKI SIEVE)")
    print("=" * 80)

    config_files = sorted(glob.glob("sweep_configs_clutch/config_*.json"))
    if not config_files:
        config_files = sorted(
            glob.glob(os.path.join(REPO_ROOT, DATASET, "config_*.json"))
        )
    if not config_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No configuration records found in "
            "sweep_configs_clutch (working directory or repository root)."
        )

    if args.max_steps is not None:
        config_files = config_files[:args.max_steps]
    if not config_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No records selected for analysis "
            "(--max-steps is zero)."
        )

    print(f"Loaded {len(config_files)} target Quantum Clutch configurations.")
    executed_at = datetime.now(timezone.utc).isoformat()

    matched = []
    for fp in config_files:
        try:
            cfg = read_json_object(fp)
            d_val = finite_float(cfg["d"])
            th_val = finite_float(cfg["theta"])
            tid_value = finite_float(cfg["task_id"])
            if d_val is None or th_val is None:
                raise ValueError("Gap and angle must be finite numbers")
            if tid_value is None or not tid_value.is_integer():
                raise ValueError("task_id must be an integer")
            tid = int(tid_value)
            expected_fp = get_expected_output_path(cfg)
            area = get_effective_area(cfg["N_top"], cfg.get("L", 2.0))
        except (json.JSONDecodeError, OSError, KeyError, TypeError,
                ValueError, OverflowError) as err:
            raise RuntimeError(
                f"[ERROR: RUN_DATA_MISSING] Invalid configuration {fp}: {err}"
            ) from err

        p_val = None
        f_sub = None
        f_both = None
        f_self = None

        # Prefer exact filenames before the legacy gap/angle search.
        patterns = [
            os.path.join(
                REPO_ROOT, "results_clutch", "results_json",
                os.path.basename(expected_fp),
            ),
            os.path.join(REPO_ROOT, expected_fp),
            expected_fp,
            os.path.join(
                REPO_ROOT, "results_clutch", "results_json",
                f"meep_d_{d_val:.4f}_*theta_{th_val:.1f}_*.json",
            ),
            os.path.join(
                REPO_ROOT, ".tmp",
                f"meep_d_{d_val:.4f}_*theta_{th_val:.1f}_*.json",
            ),
        ]
        seen = set()
        for pat in patterns:
            for found_f in sorted(glob.glob(pat)):
                if (
                    "moments_" in os.path.basename(found_f)
                    or "config_" in os.path.basename(found_f)
                    or os.path.abspath(found_f) in seen
                ):
                    continue
                seen.add(os.path.abspath(found_f))
                try:
                    data = read_json_object(found_f)
                    pressure = finite_float(data.get("pressure_Pa"))
                    if pressure is None:
                        raise ValueError("Missing or non-finite pressure_Pa")
                    p_val = pressure
                    f_sub = finite_float(data.get("force_subtracted"))
                    f_both = finite_float(data.get("force_both"))
                    f_self = finite_float(data.get("force_self"))
                    break
                except (json.JSONDecodeError, OSError, ValueError) as err:
                    print(f"Warning: Corrupted result file {found_f} ({err}).")
            if p_val is not None:
                break

        if p_val is None:
            status_f = os.path.join(
                REPO_ROOT, "results_clutch", "progress",
                f"task_{tid:03d}_status.json",
            )
            if os.path.exists(status_f):
                try:
                    s_data = read_json_object(status_f)
                    if s_data.get("status") == "COMPLETE":
                        p_val = finite_float(s_data.get("pressure_Pa"))
                        if p_val is not None:
                            f_sub = finite_float(s_data.get("net_force"))
                except (json.JSONDecodeError, OSError, ValueError) as err:
                    print(f"Warning: Corrupted status file {status_f} ({err}).")

        if p_val is None:
            # Strictly require v4 verified geometry checkpoints.
            rtip = float(cfg.get("r_tip_nm", 5.0))
            rtip_str = f"_rtip_{rtip:.1f}" if rtip > 0 else ""
            geom_tag = (
                f"_clutch_al_{float(cfg.get('corrugation_angle', 75.0)):.1f}"
                f"{rtip_str}"
            )
            chk_tag = (
                f"v4_d_{d_val:.4f}_Ntop_{int(cfg['N_top'])}"
                f"_Nbot_{int(cfg.get('N_bot', 3))}_mat_{cfg['material']}"
                f"_res_{int(cfg.get('resolution', 40))}_th_{th_val:.1f}"
                f"{geom_tag}_L_{float(cfg.get('L', 2.0)):.2f}"
            )
            checkpoint_dirs = list(dict.fromkeys([
                os.path.join(REPO_ROOT, ".tmp"), ".tmp"
            ]))
            for checkpoint_dir in checkpoint_dirs:
                chk_b = os.path.join(checkpoint_dir, f"chk_{chk_tag}_both.json")
                chk_s = os.path.join(checkpoint_dir, f"chk_{chk_tag}_self.json")
                if not (os.path.exists(chk_b) and os.path.exists(chk_s)):
                    continue
                try:
                    fb_val = finite_float(read_json_object(chk_b)["force"])
                    fs_val = finite_float(read_json_object(chk_s)["force"])
                    if fb_val is None or fs_val is None:
                        raise ValueError("Checkpoint forces must be finite numbers")
                    net_force = finite_float(fb_val - fs_val)
                    if net_force is None:
                        raise ValueError("Non-finite subtracted force")
                    pressure = finite_float((net_force / area) * MEEP_TO_PA)
                    if pressure is None:
                        raise ValueError("Non-finite checkpoint pressure")
                    f_both = fb_val
                    f_self = fs_val
                    f_sub = net_force
                    p_val = pressure
                    break
                except (json.JSONDecodeError, OSError, KeyError, TypeError,
                        ValueError, OverflowError, ZeroDivisionError) as err:
                    print(
                        f"Warning: Corrupted checkpoint pair "
                        f"{chk_b} / {chk_s} ({err})."
                    )

        matched.append({
            "model": MODEL,
            "dataset": DATASET,
            "executed_at": executed_at,
            "task_id": tid,
            "label": cfg.get("label", f"Task {tid}"),
            "d_um": d_val,
            "N_top": int(cfg["N_top"]),
            "N_bot": int(cfg.get("N_bot", 3)),
            "theta_deg": th_val,
            "pressure_Pa": p_val,
            "force_subtracted": f_sub,
            "force_both": f_both,
            "force_self": f_self,
            "status": "completed" if p_val is not None else "pending",
        })

    completed = [m for m in matched if m["status"] == "completed"]
    if not completed:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No valid pressure records found in "
            "result files, completed progress records, or v4 checkpoint pairs."
        )

    repulsive = [m for m in completed if m["pressure_Pa"] > 0]
    attractive = [m for m in completed if m["pressure_Pa"] < 0]

    print(f"\nClutch Status: {len(completed)} / {len(matched)} tasks completed.")
    print(f"Repulsive States (Disengaged, P > 0): {len(repulsive)}")
    print(f"Attractive States (Engaged, P < 0):    {len(attractive)}")

    gaps = sorted({m["d_um"] for m in matched})
    for d_val in gaps:
        items = [m for m in matched if abs(m["d_um"] - d_val) < 1e-4]
        print(f"\n--- Gap d = {int(d_val * 1000)} nm ({len(items)} Tasks) ---")
        for it in items:
            p = it["pressure_Pa"]
            if p is not None:
                p_str = f"{p:+12.6f} Pa"
                if p > 0:
                    flag = "*** REPULSIVE (P > 0) [DISENGAGED] ***"
                elif p < 0:
                    flag = "Attractive [ENGAGED]"
                else:
                    flag = "Zero Force (P = 0)"
            else:
                p_str = "    Pending"
                flag = "---"
            print(
                f"  Task {it['task_id']:2d} | th={it['theta_deg']:5.1f}deg "
                f"| P = {p_str} | {flag}"
            )

    clutch_verified = False
    for d_val in gaps:
        d_items = [m for m in completed if abs(m["d_um"] - d_val) < 1e-4]
        p_0 = next(
            (m["pressure_Pa"] for m in d_items
             if abs(m["theta_deg"]) < 1e-2), None
        )
        p_90 = next(
            (m["pressure_Pa"] for m in d_items
             if abs(m["theta_deg"] - 90.0) < 1e-2), None
        )
        if p_0 is not None and p_90 is not None and p_0 > 0 and p_90 < 0:
            print(
                f"\n>>> SUCCESS! QUANTUM CLUTCH CONFIRMED "
                f"AT d={int(d_val * 1000)}nm! <<<"
            )
            print(f"    theta =  0.0 deg: P = {p_0:+10.6f} Pa (Repulsive Levitation)")
            print(f"    theta = 90.0 deg: P = {p_90:+10.6f} Pa (Attractive Clamping)")
            print(f"    Dynamic Switch Amplitude: Delta_P = {p_0 - p_90:10.6f} Pa")
            clutch_verified = True

    os.makedirs("results_clutch", exist_ok=True)
    summary_path = "results_clutch/clutch_summary.json"
    with open(summary_path, "w") as f:
        json.dump(matched, f, indent=4, allow_nan=False)
    print(f"\nSaved summary dataset to '{summary_path}'.")

    metrics = {
        "model": MODEL,
        "dataset": DATASET,
        "status": "completed",
        "executed_at": executed_at,
        "completed_tasks": len(completed),
        "total_tasks": len(matched),
        "repulsive_states": len(repulsive),
        "attractive_states": len(attractive),
        "clutch_verified": clutch_verified,
    }
    try:
        from utils.metrics_logger import log_metrics
    except ImportError as err:
        print(f"[Metrics Note] Metrics logger unavailable: {err}")
    else:
        log_metrics(metrics)

    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)
    tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_quantum_clutch.tex"
    with open(tex_path, "w") as f:
        f.write("% Auto-generated Fractal Quantum Clutch Verification Table\n")
        f.write("\\begin{table}[htbp]\n\\centering\n")
        f.write(
            "\\caption{Fractal Quantum Clutch: Rotation-Driven Casimir Force "
            "Inversion ($\\epsilon_{\\rm bg}=1.0$).}\n"
        )
        f.write("\\label{tab:quantum_clutch}\n")
        f.write("\\begin{tabular}{cccccc}\n\\toprule\n")
        f.write(
            "\\textbf{Task} & \\textbf{Gap $d$} & \\textbf{Twist $\\theta$} & "
            "\\textbf{Pressure $P$ (Pa)} & \\textbf{Clutch State} & "
            "\\textbf{Regime} \\\\\n\\midrule\n"
        )
        for m in matched:
            p = m["pressure_Pa"]
            p_str = f"${p:+9.6f}$ Pa" if p is not None else "Pending"
            if p is None:
                state_str, reg_str = "---", "Pending"
            elif p > 0:
                state_str, reg_str = "Disengaged", "\\textbf{Repulsive ($P>0$)}"
            elif p < 0:
                state_str, reg_str = "Engaged", "Attractive ($P<0$)"
            else:
                state_str, reg_str = "---", "Zero force ($P=0$)"
            f.write(
                f"{m['task_id']:2d} & ${m['d_um'] * 1000:.0f}\\text{{ nm}}$ & "
                f"${m['theta_deg']:.1f}^\\circ$ & {p_str} & "
                f"{state_str} & {reg_str} \\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    print(f"Generated Publication Table: '{tex_path}'.")

    sync_paths = [summary_path, tex_path]
    plt = None
    fig = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        os.makedirs("Papers/Fractal_Casimir_Nature_EM/figures", exist_ok=True)
        fig_path = (
            "Papers/Fractal_Casimir_Nature_EM/figures/"
            "fig_quantum_clutch_characteristic.png"
        )
        fig = plt.figure(figsize=(8.5, 5.0))
        colors = {0.04: "#2ca02c", 0.08: "#1f77b4"}
        markers = {0.04: "o", 0.08: "s"}
        for d_val in gaps:
            sub_d = sorted(
                [m for m in completed if abs(m["d_um"] - d_val) < 1e-4],
                key=lambda m: m["theta_deg"],
            )
            if sub_d:
                plt.plot(
                    [m["theta_deg"] for m in sub_d],
                    [m["pressure_Pa"] for m in sub_d],
                    marker=markers.get(d_val, "o"),
                    color=colors.get(d_val, "black"),
                    linewidth=2.0, markersize=8,
                    label=f"Gap d = {int(d_val * 1000)} nm",
                )
        plt.axhline(
            0, color="red", linestyle="--", linewidth=1.5,
            label="Zero-Force Gateway (P = 0)",
        )
        plt.xlabel(r"Twist Angle $\theta$ (degrees)", fontsize=12)
        plt.ylabel(r"Casimir Pressure $P$ (Pa)", fontsize=12)
        plt.title(
            r"Fractal Quantum Clutch: Rotational Switching "
            r"($P>0 \leftrightarrow P<0$)",
            fontsize=13, pad=12,
        )
        plt.legend(frameon=True, fontsize=10)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(fig_path, dpi=300)
        sync_paths.append(fig_path)

        provenance = dict(metrics, source=summary_path)
        try:
            from utils.plot_provenance import save_plot_provenance
        except ImportError as err:
            # Preserve provenance even on lightweight cluster installations.
            provenance_path = fig_path + ".provenance.json"
            with open(provenance_path, "w") as f:
                json.dump(provenance, f, indent=4, allow_nan=False)
            sync_paths.append(provenance_path)
            print(f"[Provenance Note] Provenance helper unavailable: {err}")
        else:
            save_plot_provenance(fig_path, provenance)

        print(f"Generated Clutch Characteristic Figure: '{fig_path}'.")
    except (ImportError, RuntimeError, OSError) as err:
        print(f"[Note] Skipping matplotlib figure generation on cluster: {err}")
    finally:
        if plt is not None and fig is not None:
            plt.close(fig)

    try:
        from execution.git_sync import git_sync_results
        git_sync_results(
            MODEL, sync_paths, len(completed), len(matched)
        )
    except (ImportError, subprocess.SubprocessError, OSError) as err:
        print(f"[Git Auto-Sync Note] {err}")

    print("=" * 80)


if __name__ == "__main__":
    main()
