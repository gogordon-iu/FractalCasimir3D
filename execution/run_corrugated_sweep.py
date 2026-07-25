import os
import sys
import glob
import json
import argparse
import subprocess
import numpy as np

def main():
    parser = argparse.ArgumentParser(description="Aggregate Frontier 2 (3D Interlocking Fractal Corrugations) FDTD results.")
    parser.add_argument("--L", type=float, default=2.0, help="Plate width in um.")
    parser.add_argument("--d", type=float, default=0.10, help="Gap in um.")
    parser.add_argument("--N", type=int, default=3, help="Top pre-fractal level N.")
    parser.add_argument("--N-bottom", type=int, default=3, help="Bottom corrugated level N.")
    parser.add_argument("--material", type=str, default="Phosphorene_tuned", help="Material name.")
    parser.add_argument("--res", type=int, default=40, help="Resolution in pixels/um.")
    parser.add_argument("--theta", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument("--eps-bg", type=float, default=2.1, help="Background dielectric constant.")
    args = parser.parse_args()

    tmp_dir = ".tmp"
    num_tasks = 108

    print("==================================================")
    print("Aggregating Frontier 2 (3D Fractal Corrugations) Results")
    print(f"L={args.L:.2f} um, d={args.d:.2f} um ({args.d*1000:.0f} nm), N_top={args.N}, N_bottom={args.N_bottom}")
    print(f"Material={args.material}, R={args.res}, theta={args.theta} deg, eps_bg={args.eps_bg}")
    print("==================================================")

    def load_config_force(config_name):
        pattern = os.path.join(tmp_dir, f"meep_corrugated_d_{args.d:.4f}_N_{args.N}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_config_{config_name}_seg_*.dat")
        seg_files = glob.glob(pattern)
        print(f"Found {len(seg_files)} segment files for config={config_name}.")

        collected_moments = {}
        for fpath in seg_files:
            try:
                with open(fpath, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            t_idx = int(parts[0])
                            val = float(parts[1])
                            collected_moments[t_idx] = val
            except Exception as e:
                print(f"Warning: Could not read {fpath}: {e}")

        missing = [i for i in range(num_tasks) if i not in collected_moments]
        if missing:
            print(f"STATUS: INCOMPLETE ({len(missing)} moments missing for {config_name}).")
            return None, missing

        total_force = sum(collected_moments.values())
        return total_force, []

    f_both, missing_both = load_config_force("both")
    f_self, missing_self = load_config_force("self")

    if f_both is None or f_self is None:
        print("Not all segments are complete yet. Plot job exiting safely.")
        sys.exit(0)

    f_subtracted = f_both - f_self
    area_eff = (args.L ** 2) * ((8.0 / 9.0) ** args.N) # effective solid plate area
    pressure = f_subtracted / area_eff
    is_repulsive = bool(pressure > 0.0)

    timestamp = subprocess.check_output(["date", "+%Y%m%d_%H%M%S"]).decode().strip()
    out_dir = f"results_corrugated_L_{args.L:.2f}_d_{args.d:.2f}_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    results = {
        "L_um": args.L,
        "d_um": args.d,
        "N_top": args.N,
        "N_bottom": args.N_bottom,
        "resolution": args.res,
        "theta_deg": args.theta,
        "eps_bg": args.eps_bg,
        "material": args.material,
        "force_both": f_both,
        "force_self": f_self,
        "force_subtracted": f_subtracted,
        "effective_area_um2": area_eff,
        "pressure": pressure,
        "is_repulsive": is_repulsive,
        "regime": "REPULSIVE (POSITIVE PRESSURE)" if is_repulsive else "ATTRACTIVE (NEGATIVE PRESSURE)"
    }

    json_path = os.path.join(out_dir, "corrugated_sweep_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=4)

    param_path = os.path.join(out_dir, "parameters.txt")
    with open(param_path, "w") as f:
        for k, v in results.items():
            f.write(f"{k}: {v}\n")

    print("\n==================================================")
    print("FRONTIER 2 SIMULATION SWEEP RESULTS COMPLETE")
    print(f"Force Both: {f_both:.6f}")
    print(f"Force Self: {f_self:.6f}")
    print(f"Net Force:  {f_subtracted:.6f}")
    print(f"Effective Area: {area_eff:.6f} um^2")
    print(f"Pressure:   {pressure:.6f} Pa")
    print(f"Regime:     {results['regime']}")
    print("==================================================")

    # Auto-commit and push results to GitHub
    try:
        subprocess.run(["git", "add", out_dir], check=True)
        commit_msg = f"Auto-sync Frontier 2 3D Corrugated results (L={args.L:.2f}um, d={args.d:.2f}um, P={pressure:.4f})"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("Successfully auto-committed and pushed Frontier 2 results to GitHub!")
    except Exception as e:
        print(f"Warning: Git auto-push encountered an issue: {e}")

if __name__ == "__main__":
    main()
