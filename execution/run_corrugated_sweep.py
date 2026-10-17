import os
import sys
import glob
import json
import argparse
import datetime
import math
import numpy as np

MEEP_TO_PA = 0.0316152649


def get_effective_area(N, L):
    return ((8.0 / 9.0) ** (N - 1)) * (L ** 2)


def main():
    parser = argparse.ArgumentParser(description="Consolidate partial moment files for Frontier 2: 3D Interlocking Fractal Corrugations.")
    parser.add_argument("--L", type=float, default=2.0, help="Plate length in microns.")
    parser.add_argument("--d", type=float, default=0.10, help="Gap separation in microns.")
    parser.add_argument("--N", type=int, default=3, help="Prefractal generation of top plate.")
    parser.add_argument("--N-bottom", type=int, default=3, help="Prefractal generation of bottom plate.")
    parser.add_argument("--res", type=int, default=40, help="Resolution (pixels/um).")
    parser.add_argument("--theta", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument("--eps-bg", type=float, default=2.1, help="Background dielectric constant.")
    parser.add_argument("--material", type=str, default="Phosphorene_tuned", help="Material name.")
    parser.add_argument("--corrugation-angle", type=float, default=60.0, help="Wall slope angle in degrees.")
    parser.add_argument("--cores", type=int, default=128, help="Number of cores used.")
    parser.add_argument("--max-steps", type=int, default=None,
                        help="Optional simulation step limit recorded as metadata; this script only consolidates existing files.")
    parser.add_argument("--plot-only", action="store_true", help="Only generate plot and summary without throwing error on missing files.")
    args = parser.parse_args()

    for name in ("L", "d", "eps_bg"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive.")
    for name in ("theta", "corrugation_angle"):
        if not math.isfinite(getattr(args, name)):
            parser.error(f"--{name.replace('_', '-')} must be finite.")
    for name in ("N", "N_bottom", "res", "cores"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive.")
    if args.max_steps is not None and args.max_steps <= 0:
        parser.error("--max-steps must be positive.")

    L = args.L
    d = args.d
    N_top = args.N
    N_bot = args.N_bottom
    resolution = args.res
    theta = args.theta
    eps_bg = args.eps_bg
    mat = args.material
    alpha = args.corrugation_angle

    try:
        A_eff = get_effective_area(N_top, L)
    except (OverflowError, ValueError):
        parser.error("Parameters produce an invalid effective area.")
    if not math.isfinite(A_eff) or A_eff <= 0:
        parser.error("Effective area must be finite and positive.")

    print("==================================================")
    print("FRONTIER 2: 3D INTERLOCKING FRACTAL CORRUGATIONS SWEEP ANALYSIS")
    print(f"Parameters: L = {L:.2f} um, d = {d:.2f} um ({d*1000:.0f} nm), N_top = {N_top}, N_bottom = {N_bot}")
    print(f"Corrugation Angle = {alpha} deg, Resolution = {resolution}, theta = {theta} deg, eps_bg = {eps_bg}")
    print("==================================================")

    nbot_str = f"_corrugated_al_{alpha:.1f}_Nbot_{N_bot}"
    nbot_str_legacy = f"_corrugated_Nbot_{N_bot}"
    num_segments = 18
    moments_per_seg = 6

    missing_segments = []
    forces = {"both": {}, "self": {}}

    for cfg in ["both", "self"]:
        for seg in range(num_segments):
            m_start = seg * moments_per_seg
            m_end = (seg + 1) * moments_per_seg

            pattern = f".tmp/meep_d_{d:.4f}_N_{N_top}{nbot_str}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_{cfg}_moments_{m_start}_{m_end}.json"
            files = glob.glob(pattern)
            if not files:
                pattern_legacy = f".tmp/meep_d_{d:.4f}_N_{N_top}{nbot_str_legacy}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_{cfg}_moments_{m_start}_{m_end}.json"
                files = glob.glob(pattern_legacy)

            if files:
                try:
                    with open(files[0], "r") as f:
                        data = json.load(f)
                    force = data["force"]
                    if isinstance(force, bool) or not isinstance(force, (int, float)):
                        raise ValueError("force must be a numeric scalar")
                    force = float(force)
                    if not math.isfinite(force):
                        raise ValueError("force must be finite")
                    forces[cfg][(m_start, m_end)] = force
                except (OSError, ValueError, TypeError, KeyError, OverflowError) as e:
                    print(f"Invalid segment file {files[0]}: {e}")
                    missing_segments.append((cfg, m_start, m_end))
            else:
                missing_segments.append((cfg, m_start, m_end))

    if missing_segments:
        print(f"STATUS: INCOMPLETE ({len(missing_segments)} segments missing or invalid)")
        for cfg, m_start, m_end in missing_segments:
            print(f"  Missing or invalid: config_{cfg} moments_{m_start}_{m_end}")
        if args.max_steps is not None:
            executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join(
                ".tmp", "corrugated_probe",
                f"results_corrugated_L_{L:.2f}_d_{d:.2f}_{timestamp}"
            )
            os.makedirs(out_dir, exist_ok=True)
            summary_data = {
                "model": mat,
                "dataset": "corrugated_sweep",
                "status": "incomplete_segments",
                "executed_at": executed_at,
                "max_steps": args.max_steps,
                "L_um": L,
                "d_um": d,
                "N_top": N_top,
                "N_bottom": N_bot,
                "resolution": resolution,
                "theta_deg": theta,
                "eps_bg": eps_bg,
                "material": mat,
                "corrugation_angle_deg": alpha,
                "effective_area_um2": A_eff,
                "missing_segments": [
                    {"config": cfg, "moment_start": m_start, "moment_end": m_end}
                    for cfg, m_start, m_end in missing_segments
                ]
            }
            with open(os.path.join(out_dir, "corrugated_sweep_results.json"), "w") as f:
                json.dump(summary_data, f, indent=4, allow_nan=False)
            print(f"Saved Frontier 2 probe status to {out_dir}/")
            try:
                from utils.metrics_logger import log_metrics
                log_metrics(summary_data)
            except Exception as e:
                print(f"Metrics logging warning: {e}")
            return
        if not args.plot_only:
            sys.exit(1)
        return

    print("STATUS: COMPLETE! All 36 simulation segment files found.")

    f_both = sum(forces["both"].values())
    f_self = sum(forces["self"].values())
    f_subtracted = f_both - f_self

    pressure_meep = f_subtracted / A_eff
    pressure_Pa = pressure_meep * MEEP_TO_PA
    if not all(math.isfinite(value) for value in
               (f_both, f_self, f_subtracted, pressure_meep, pressure_Pa)):
        parser.error("Aggregated forces and pressures must be finite.")
    is_repulsive = bool(pressure_Pa > 0.0)

    if is_repulsive:
        regime_str = "REPULSIVE (POSITIVE PRESSURE - CASIMIR LEVITATION!)"
    elif pressure_Pa < 0.0:
        regime_str = "ATTRACTIVE (NEGATIVE PRESSURE)"
    else:
        regime_str = "NEUTRAL (ZERO PRESSURE)"

    print("==================================================")
    print(f"Force (Both Plates):       {f_both:.8e}")
    print(f"Force (Self Plate):        {f_self:.8e}")
    print(f"Force (Subtracted Net):    {f_subtracted:.8e}")
    print(f"Effective Area (A_eff):    {A_eff:.6f} um^2")
    print(f"Pressure (Meep units):     {pressure_meep:.8e}")
    print(f"Consolidated Pressure:     {pressure_Pa:.8e} Pa")
    print(f"CASIMIR REGIME:            {regime_str}")
    print("==================================================")

    executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_corrugated_L_{L:.2f}_d_{d:.2f}_{timestamp}"
    if args.max_steps is not None:
        out_dir = os.path.join(".tmp", "corrugated_probe", out_dir)
    os.makedirs(out_dir, exist_ok=True)

    summary_data = {
        "model": mat,
        "dataset": "corrugated_sweep",
        "status": "completed",
        "executed_at": executed_at,
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
        "regime": regime_str
    }

    with open(os.path.join(out_dir, "corrugated_sweep_results.json"), "w") as f:
        json.dump(summary_data, f, indent=4, allow_nan=False)

    with open(os.path.join(out_dir, "parameters.txt"), "w") as f:
        for k, v in summary_data.items():
            f.write(f"{k}: {v}\n")

    print(f"Saved Frontier 2 3D Corrugated sweep analysis to {out_dir}/")

    try:
        from utils.metrics_logger import log_metrics
        log_metrics(summary_data)
    except Exception as e:
        print(f"Metrics logging warning: {e}")

    # Auto-push only full-run results to GitHub.
    if args.max_steps is None:
        try:
            import subprocess
            print("Staging, committing, and pushing Frontier 2 results to GitHub...")
            subprocess.run(["git", "add", out_dir], check=False)
            diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
            if diff_res.returncode != 0:
                subprocess.run(["git", "commit", "-m", f"Auto-sync Frontier 2 3D Corrugated results (L={L:.2f}um, d={d:.2f}um) from BigRed200"], check=False)
                subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
                subprocess.run(["git", "push", "origin", "main"], check=False)
                print("Git sync complete!")
            else:
                print("No new changes to push.")
        except Exception as e:
            print(f"Git push warning: {e}")


if __name__ == "__main__":
    main()
