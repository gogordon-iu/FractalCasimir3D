import argparse
import datetime
import glob
import json
import math
import os
import sys

MEEP_TO_PA = 0.0316152649


def get_effective_area(N, L):
    return ((8.0 / 9.0) ** (N - 1)) * (L ** 2)


def finite_float(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number, not a boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite.")
    return result


def positive_int(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--max-steps must be a positive integer.") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("--max-steps must be a positive integer.")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate and analyze sweet spot parameter sweep results."
    )
    parser.add_argument(
        "--max-steps",
        type=positive_int,
        default=None,
        help="Maximum number of input result records to process (default: all).",
    )
    args = parser.parse_args()

    print("==================================================")
    print("SWEET SPOT PARAMETER SWEEP RESULTS ANALYZER")
    print("==================================================")

    # Search for output JSONs across .tmp and historical summary files.
    input_dirs = [
        path for path in [".tmp"] + glob.glob("results_*")
        if os.path.isdir(path)
    ]
    if not input_dirs:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No .tmp or results_* input directory exists."
        )

    tmp_files = sorted(set(
        glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")
    ))
    summary_files = sorted(set(
        glob.glob("results_*/sweet_spot_sweep_summary.json")
        + glob.glob("results_*/hybrid_sweep_summary.json")
    ))
    input_files = list(dict.fromkeys(tmp_files + summary_files))
    if not input_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No sweep result JSON files were found."
        )

    records = []
    for fp in input_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"[ERROR: RUN_DATA_INVALID] Could not read result file '{fp}': {exc}"
            ) from exc

        candidates = data if isinstance(data, list) else [data]
        for rec in candidates:
            if isinstance(rec, dict) and ("d_um" in rec or "d" in rec):
                records.append(rec)

    if not records:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No physical sweep result records were found."
        )

    print(f"Loaded {len(records)} total JSON result records across all sweeps.")

    executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    results_map = {}
    selected_records = records if args.max_steps is None else records[:args.max_steps]

    for index, rec in enumerate(selected_records, start=1):
        try:
            d = finite_float(rec.get("d_um", rec.get("d")), "d_um")
            theta = finite_float(
                rec.get("theta_deg", rec.get("theta", 90.0)), "theta_deg"
            )
            alpha = finite_float(
                rec.get(
                    "corrugation_angle",
                    rec.get("alpha_deg", rec.get("alpha", 60.0)),
                ),
                "alpha_deg",
            )

            f_both = rec.get("force_both")
            f_self = rec.get("force_self")
            p_direct = rec.get("pressure_Pa", rec.get("pressure"))

            p = None
            pressure_meep = None
            if f_both is not None and f_self is not None:
                f_net = (
                    finite_float(f_both, "force_both")
                    - finite_float(f_self, "force_self")
                )
                L = finite_float(rec.get("L", 2.0), "L")
                if L <= 0:
                    raise ValueError("L must be positive.")
                area = get_effective_area(3, L)
                if not math.isfinite(area) or area <= 0:
                    raise ValueError("Effective area must be finite and positive.")
                pressure_meep = finite_float(f_net / area, "pressure_meep")
                p = finite_float(pressure_meep * MEEP_TO_PA, "pressure_Pa")
            elif p_direct is not None:
                val = finite_float(p_direct, "pressure_Pa")
                if abs(val) > 1e-12:  # Ignore dummy zero placeholders.
                    p = val
                    pressure_meep = finite_float(p / MEEP_TO_PA, "pressure_meep")
            elif rec.get("pressure_meep") is not None:
                val = finite_float(rec["pressure_meep"], "pressure_meep")
                converted = finite_float(val * MEEP_TO_PA, "pressure_Pa")
                if abs(converted) > 1e-12:
                    pressure_meep = val
                    p = converted

            if p is not None:
                key = (round(alpha, 1), round(theta, 1), round(d, 4))
                results_map[key] = {
                    "alpha_deg": alpha,
                    "theta_deg": theta,
                    "d_um": d,
                    "pressure_Pa": p,
                    "pressure_meep": pressure_meep,
                    "pressure_Pa_SI": p,
                    "pressure_meep_raw": pressure_meep,
                    "is_repulsive": bool(p > 0.0),
                    "model": rec.get("model") or "sweet_spot_sweep",
                    "dataset": rec.get("dataset") or "sweet_spot_parameter_sweep",
                    "status": "completed",
                    "executed_at": executed_at,
                }
        except (ValueError, OverflowError) as exc:
            raise RuntimeError(
                f"[ERROR: RUN_DATA_INVALID] Invalid result record {index}: {exc}"
            ) from exc

    data_list = list(results_map.values())
    if not data_list:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No usable pressure result records were found."
        )

    print(f"Extracted {len(data_list)} verified unique physical parameter points.")
    data_list.sort(key=lambda x: (x["alpha_deg"], x["theta_deg"], x["d_um"]))

    if args.max_steps is not None:
        # Keep partial probe output out of the historical sweep directories.
        out_dir = os.path.join(".tmp", "sweet_spot_probe")
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = f"results_sweet_spot_sweep_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    summary_file = os.path.join(out_dir, "sweet_spot_sweep_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(data_list, f, indent=4, allow_nan=False)

    if args.max_steps is None:
        os.makedirs("results", exist_ok=True)
        latest_summary_file = os.path.join("results", "sweet_spot_sweep_summary.json")
        with open(latest_summary_file, "w", encoding="utf-8") as f:
            json.dump(data_list, f, indent=4, allow_nan=False)

    print(f"Saved consolidated sweet spot summary to '{summary_file}'.")

    print("\n--------------------------------------------------")
    print("NANOMECHANICAL LEVITATION EQUILIBRIUM HEIGHT ANALYSIS (P = 0, dP/dd < 0)")
    print("--------------------------------------------------")

    curves = {}
    for r in data_list:
        key = (r["alpha_deg"], r["theta_deg"])
        curves.setdefault(key, []).append(r)

    eq_points = []
    for (a, th), pts in curves.items():
        pts.sort(key=lambda x: x["d_um"])
        if len(pts) < 2:
            continue

        d_arr = [p["d_um"] for p in pts]
        p_arr = [p["pressure_Pa"] for p in pts]
        p_max = max(p_arr)

        for i in range(len(p_arr) - 1):
            if p_arr[i] > 0 and p_arr[i + 1] < 0:
                d1, d2 = d_arr[i], d_arr[i + 1]
                p1, p2 = p_arr[i], p_arr[i + 1]
                if d2 <= d1:
                    continue

                # Scale pressures to avoid overflow in the interpolation ratio.
                scale = max(abs(p1), abs(p2))
                positive = p1 / scale
                negative = -p2 / scale
                fraction = positive / (positive + negative)
                d_eq = (1.0 - fraction) * d1 + fraction * d2
                d_eq_nm = d_eq * 1000.0
                if not math.isfinite(d_eq) or not math.isfinite(d_eq_nm):
                    raise RuntimeError(
                        "[ERROR: RUN_DATA_INVALID] Non-finite equilibrium height."
                    )

                eq_points.append({
                    "alpha_deg": a,
                    "theta_deg": th,
                    "d_eq_nm": round(d_eq_nm, 2),
                    "d_eq_um": round(d_eq, 4),
                    "p_max_Pa": p_max,
                })
                print(
                    f"FOUND STABLE EQUILIBRIUM: Alpha={a} deg, Theta={th} deg "
                    f"=> d_eq = {d_eq_nm:.2f} nm (P_max = {p_max:+.4f} Pa)"
                )

    # Permit direct execution from the execution/ directory.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from utils.metrics_logger import log_metrics

    log_metrics({
        "model": "sweet_spot_sweep",
        "dataset": "sweet_spot_parameter_sweep",
        "status": "completed",
        "executed_at": executed_at,
        "records_loaded": len(records),
        "records_processed": len(selected_records),
        "unique_points": len(data_list),
        "stable_equilibria": len(eq_points),
        "max_steps": args.max_steps,
        "summary_file": summary_file,
    })

    print("Sweet spot analysis complete!")


if __name__ == "__main__":
    main()
