import os
import sys
import json
import glob
import math
import datetime
import argparse

MEEP_TO_PA = 0.0316152649


def get_effective_area(N, L):
    return ((8.0 / 9.0) ** (N - 1)) * (L ** 2)


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate and analyze Asymmetric Dual-Fractal Casimir simulations."
    )
    parser.add_argument("--L", type=float, default=2.0, help="Plate width in microns.")
    parser.add_argument("--d", type=float, default=0.25, help="Plate gap in microns.")
    parser.add_argument("--N-top", type=int, default=3, help="Top plate iteration level.")
    parser.add_argument("--N-bottom", type=int, default=2, help="Bottom plate iteration level.")
    parser.add_argument("--res", type=int, default=40, help="Resolution.")
    parser.add_argument("--theta", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument("--eps-bg", type=float, default=2.1, help="Background dielectric constant.")
    parser.add_argument("--material", type=str, default="Phosphorene_tuned", help="Material.")
    parser.add_argument("--cores", type=int, default=128, help="Number of cores.")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Simulation step limit recorded in the analysis metadata; does not truncate consolidation.",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="Only check file status without exiting with error if incomplete.",
    )
    args = parser.parse_args()

    for name in ("L", "d", "eps_bg"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    if not math.isfinite(args.theta):
        parser.error("--theta must be finite.")
    for name in ("N_top", "N_bottom", "res", "cores"):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be at least 1.")
    if args.max_steps is not None and args.max_steps < 1:
        parser.error("--max-steps must be at least 1.")
    if not args.material.strip():
        parser.error("--material must not be empty.")

    L = args.L
    d = args.d
    N_top = args.N_top
    N_bot = args.N_bottom
    resolution = args.res
    theta = args.theta
    eps_bg = args.eps_bg
    mat = args.material

    try:
        A_eff = get_effective_area(N_top, L)
    except OverflowError:
        parser.error("Effective area overflowed; check --L and --N-top.")
    if not math.isfinite(A_eff) or A_eff <= 0:
        parser.error("Effective area must be finite and positive.")

    segments = [(i * 6, (i + 1) * 6) for i in range(18)]

    results = {}
    missing_segments = []

    for config in ["both", "self"]:
        total_force = 0.0
        complete = True
        for m_start, m_end in segments:
            pattern = (
                f".tmp/meep_d_{d:.4f}_N_{N_top}_Nbot_{N_bot}_{mat}"
                f"_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}"
                f"_L_{L:.2f}_config_{config}_moments_{m_start}_{m_end}.json"
            )
            files = glob.glob(pattern)
            if files:
                try:
                    with open(files[0], "r") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        raise ValueError("Segment data must be a JSON object.")
                    force = data["force"]
                    if isinstance(force, bool) or not isinstance(force, (int, float)):
                        raise ValueError("Segment force must be a number.")
                    if not math.isfinite(force):
                        raise ValueError("Segment force must be finite.")
                    next_total = total_force + force
                    if not math.isfinite(next_total):
                        raise ValueError("Accumulated force must be finite.")
                    total_force = next_total
                except (OSError, ValueError, KeyError, TypeError, OverflowError) as e:
                    print(f"Invalid segment {files[0]}: {e}", file=sys.stderr)
                    complete = False
                    missing_segments.append((config, m_start, m_end))
            else:
                complete = False
                missing_segments.append((config, m_start, m_end))

        if complete:
            results[f"force_{config}"] = total_force

    print("==================================================")
    print("ASYMMETRIC DUAL-FRACTAL CASIMIR SWEEP SUMMARY")
    print(
        f"L = {L:.2f} um, d = {d:.2f} um ({d * 1000:.0f} nm), "
        f"N_top = {N_top}, N_bottom = {N_bot}"
    )
    print(f"Material: {mat}, Theta = {theta:.1f} deg, Resolution = {resolution}")
    print("==================================================")

    if missing_segments:
        print(f"STATUS: INCOMPLETE ({len(missing_segments)} segments missing or invalid)")
        for cfg, m_start, m_end in missing_segments:
            print(f"  Missing or invalid: config_{cfg} moments_{m_start}_{m_end}")
        if not args.plot_only:
            sys.exit(1)
        return

    f_both = results["force_both"]
    f_self = results["force_self"]
    f_subtracted = f_both - f_self
    pressure_meep = f_subtracted / A_eff
    pressure_Pa = pressure_meep * MEEP_TO_PA

    if not all(math.isfinite(value) for value in (f_subtracted, pressure_meep, pressure_Pa)):
        parser.error("Computed net force or pressure is not finite.")

    is_repulsive = pressure_Pa > 0
    if is_repulsive:
        regime_str = "REPULSIVE (POSITIVE PRESSURE!)"
    elif pressure_Pa < 0:
        regime_str = "ATTRACTIVE (NEGATIVE PRESSURE)"
    else:
        regime_str = "NEUTRAL (ZERO PRESSURE)"

    print(f"Force (Both Plates):       {f_both:.8e}")
    print(f"Force (Self Plate):        {f_self:.8e}")
    print(f"Force (Subtracted Net):    {f_subtracted:.8e}")
    print(f"Effective Area (A_eff):    {A_eff:.6f} um^2")
    print(f"Pressure (Meep units):     {pressure_meep:.8e}")
    print(f"Consolidated Pressure:     {pressure_Pa:.8e} Pa")
    print(f"CASIMIR REGIME:            {regime_str}")
    print("==================================================")

    executed_at = datetime.datetime.now(datetime.timezone.utc)
    timestamp = executed_at.strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_asym_L_{L:.2f}_d_{d:.2f}_{timestamp}"
    if args.max_steps is not None:
        out_dir = os.path.join(".tmp", "asym_probe", out_dir)
    os.makedirs(out_dir, exist_ok=True)

    summary_data = {
        "model": mat,
        "dataset": "asymmetric_dual_fractal_casimir",
        "status": "completed",
        "executed_at": executed_at.isoformat(),
        "max_steps": args.max_steps,
        "L_um": L,
        "d_um": d,
        "N_top": N_top,
        "N_bottom": N_bot,
        "resolution": resolution,
        "theta_deg": theta,
        "eps_bg": eps_bg,
        "material": mat,
        "force_both": f_both,
        "force_self": f_self,
        "force_subtracted": f_subtracted,
        "effective_area_um2": A_eff,
        "pressure": pressure_Pa,
        "pressure_Pa": pressure_Pa,
        "pressure_meep": pressure_meep,
        "is_repulsive": is_repulsive,
        "regime": regime_str,
    }

    with open(os.path.join(out_dir, "asymmetric_sweep_results.json"), "w") as f:
        json.dump(summary_data, f, indent=4, allow_nan=False)

    with open(os.path.join(out_dir, "parameters.txt"), "w") as f:
        for k, v in summary_data.items():
            f.write(f"{k}: {v}\n")

    print(f"Saved asymmetric sweep analysis to {out_dir}/")

    # Support direct execution from execution/ as well as module execution.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from utils import metrics_logger

        metrics_logger.log_metrics(summary_data)
    except Exception as e:
        print(f"Metrics logging warning: {e}", file=sys.stderr)

    # Auto-push results to GitHub only for unrestricted runs.
    if args.max_steps is None:
        try:
            import subprocess

            print("Staging, committing, and pushing asymmetric sweep results to GitHub...")
            subprocess.run(["git", "add", out_dir], check=False)
            diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
            if diff_res.returncode != 0:
                subprocess.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        f"Auto-sync asymmetric sweep results (L={L:.2f}um, d={d:.2f}um) from BigRed200",
                    ],
                    check=False,
                )
                subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
                subprocess.run(["git", "push", "origin", "main"], check=False)
                print("Git sync complete!")
            else:
                print("No new changes to push.")
        except Exception as e:
            print(f"Git push warning: {e}")


if __name__ == "__main__":
    main()
