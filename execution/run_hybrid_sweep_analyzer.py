import os
import sys
import glob
import json
import argparse
import datetime
import math

MEEP_TO_PA = 0.0316152649
MODEL = "hybrid_casimir_levitation"
DATASET = ".tmp"


def get_effective_area(N, L):
    return ((8.0 / 9.0) ** (N - 1)) * (L ** 2)


def finite_float(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def positive_int(value):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("--max-steps must be a positive integer")
    if result <= 0:
        raise argparse.ArgumentTypeError("--max-steps must be a positive integer")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Analyze completed hybrid Casimir parameter sweep results."
    )
    parser.add_argument(
        "--max-steps",
        type=positive_int,
        default=None,
        help="Maximum number of result records to process (default: all).",
    )
    args = parser.parse_args()

    print("==================================================")
    print("HYBRID CASIMIR LEVITATION PARAMETER SWEEP ANALYZER")
    print("==================================================")

    if not os.path.isdir(DATASET):
        raise RuntimeError(
            f"[ERROR: RUN_DATA_MISSING] Input directory {DATASET!r} is missing."
        )

    tmp_files = sorted(
        set(
            glob.glob(".tmp/**/*.json", recursive=True)
            + glob.glob(".tmp/*.json")
        )
    )
    print(f"Found {len(tmp_files)} result files in .tmp/")

    records = []
    for fp in tmp_files:
        try:
            with open(fp, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and "d_um" in data:
                records.append((fp, data))
        except Exception as e:
            print(f"Warning reading {fp}: {e}")

    if not records:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No completed parameter sweep records found."
        )

    print(f"Successfully loaded {len(records)} parameter result records.")
    if args.max_steps is not None:
        records = records[:args.max_steps]

    results_map = {}
    partial_moments = {}
    partial_lengths = {}

    for fp, rec in records:
        try:
            d = finite_float(rec.get("d_um", 0.1), "d_um")
            theta = finite_float(rec.get("theta_deg", 90.0), "theta_deg")
            alpha = finite_float(
                rec.get("corrugation_angle", 60.0), "corrugation_angle"
            )
            L = finite_float(rec.get("L", 2.0), "L")
            if L <= 0.0:
                raise ValueError("L must be positive")
            A_eff = get_effective_area(3, L)
            if not math.isfinite(A_eff) or A_eff <= 0.0:
                raise ValueError("Effective area must be finite and positive")

            f_both = rec.get("force_both")
            f_self = rec.get("force_self")
            main_key = (round(alpha, 1), round(theta, 1), round(d, 4))

            if f_both is not None and f_self is not None:
                f_both = finite_float(f_both, "force_both")
                f_self = finite_float(f_self, "force_self")
                f_net = finite_float(f_both - f_self, "force_net")
                pressure_meep = finite_float(f_net / A_eff, "pressure_meep")
                pressure_pa = pressure_meep * MEEP_TO_PA
                results_map[main_key] = {
                    "alpha_deg": alpha,
                    "theta_deg": theta,
                    "d_um": d,
                    "L": L,
                    "force_both": f_both,
                    "force_self": f_self,
                    "force_net": f_net,
                    "pressure_meep": pressure_meep,
                    "pressure_Pa": pressure_pa,
                    "is_repulsive": bool(pressure_pa > 0.0),
                }
            elif "config" in rec and "force" in rec:
                cfg = rec["config"]
                if not isinstance(cfg, str) or cfg not in ("both", "self"):
                    raise ValueError("config must be 'both' or 'self'")

                m_start = rec.get("moment_start", 0)
                m_end = rec.get("moment_end", 6)
                if (
                    isinstance(m_start, bool)
                    or isinstance(m_end, bool)
                    or not isinstance(m_start, int)
                    or not isinstance(m_end, int)
                    or m_start < 0
                    or m_end < m_start
                ):
                    raise ValueError("Invalid moment range")

                force = finite_float(rec["force"], "force")
                if (
                    main_key in partial_lengths
                    and partial_lengths[main_key] != L
                ):
                    raise ValueError("Inconsistent L for partial moment records")

                partial_lengths[main_key] = L
                key = main_key + (cfg,)
                partial_moments.setdefault(key, {})[(m_start, m_end)] = force
        except (TypeError, ValueError, OverflowError) as e:
            print(f"Warning skipping {fp}: {e}")

    # Complete result records take precedence over partial checkpoints.
    complete_keys = set(results_map)
    for (alpha, theta, d, cfg), moments in partial_moments.items():
        main_key = (alpha, theta, d)
        if main_key in complete_keys:
            continue
        if main_key not in results_map:
            results_map[main_key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "L": partial_lengths[main_key],
            }
        results_map[main_key][f"force_{cfg}"] = sum(moments.values())

    executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    final_list = []
    for key, data in results_map.items():
        if "force_both" not in data or "force_self" not in data:
            continue
        try:
            f_both = finite_float(data["force_both"], "force_both")
            f_self = finite_float(data["force_self"], "force_self")
            f_net = finite_float(f_both - f_self, "force_net")
            A_eff = get_effective_area(3, data["L"])
            if not math.isfinite(A_eff) or A_eff <= 0.0:
                raise ValueError("Effective area must be finite and positive")
            pressure_meep = finite_float(f_net / A_eff, "pressure_meep")
            pressure_pa = pressure_meep * MEEP_TO_PA
        except (TypeError, ValueError, OverflowError) as e:
            print(f"Warning skipping parameter point {key}: {e}")
            continue

        data.update({
            "force_net": f_net,
            "pressure_meep": pressure_meep,
            "pressure_Pa": pressure_pa,
            "is_repulsive": bool(pressure_pa > 0.0),
            "model": MODEL,
            "dataset": DATASET,
            "status": "completed",
            "executed_at": executed_at,
        })
        final_list.append(data)

    if not final_list:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No valid completed parameter points "
            "found in the selected records."
        )

    print(f"Consolidated {len(final_list)} unique (alpha, theta, d) parameter points.")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_hybrid_parameter_sweep_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    summary_file = os.path.join(out_dir, "hybrid_sweep_summary.json")
    with open(summary_file, "w") as f:
        json.dump(final_list, f, indent=4, allow_nan=False)

    repulsive_points = [v for v in final_list if v["is_repulsive"]]
    print("==================================================")
    print(f"Total Evaluated Points:  {len(final_list)}")
    print(f"Repulsive Points (P>0):  {len(repulsive_points)} / {len(final_list)}")
    if repulsive_points:
        max_repulsion = max(repulsive_points, key=lambda x: x["pressure_Pa"])
        print(f"Maximum Repulsive Pressure: +{max_repulsion['pressure_Pa']:.6f} Pa")
        print(
            f"  at alpha = {max_repulsion['alpha_deg']} deg, "
            f"theta = {max_repulsion['theta_deg']} deg, "
            f"d = {max_repulsion['d_um']} um"
        )
    print("==================================================")

    try:
        from utils.metrics_logger import log_metrics

        log_metrics({
            "model": MODEL,
            "dataset": DATASET,
            "status": "completed",
            "executed_at": executed_at,
            "total_evaluated_points": len(final_list),
            "repulsive_points": len(repulsive_points),
            "max_pressure_Pa": max(v["pressure_Pa"] for v in final_list),
            "summary_file": summary_file,
        })
    except Exception as e:
        print(f"Metrics logging warning: {e}")

    try:
        import subprocess

        print("Staging, committing, and pushing Hybrid Parameter Sweep results to GitHub...")
        subprocess.run(["git", "add", out_dir], check=False)
        diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff_res.returncode == 1:
            subprocess.run(
                [
                    "git", "commit", "-m",
                    f"Auto-sync Hybrid Casimir Parameter Sweep analysis "
                    f"({len(final_list)} points) from BigRed200",
                ],
                check=True,
            )
            subprocess.run(
                ["git", "pull", "--rebase", "origin", "main"], check=True
            )
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("Git sync complete!")
        elif diff_res.returncode == 0:
            print("No new changes to push.")
        else:
            print(f"Git push warning: git diff exited with {diff_res.returncode}")
    except Exception as e:
        print(f"Git push warning: {e}")


if __name__ == "__main__":
    main()
