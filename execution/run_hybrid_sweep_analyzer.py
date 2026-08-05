import os
import sys
import glob
import json
import argparse
import datetime
import numpy as np

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def main():
    print("==================================================")
    print("HYBRID CASIMIR LEVITATION PARAMETER SWEEP ANALYZER")
    print("==================================================")

    # Search for all completed simulation json result files in .tmp/
    tmp_files = glob.glob(".tmp/meep_d_*.json")
    print(f"Found {len(tmp_files)} result files in .tmp/")

    records = []
    for fp in tmp_files:
        try:
            with open(fp, "r") as f:
                data = json.load(f)
                records.append(data)
        except Exception as e:
            print(f"Warning reading {fp}: {e}")

    if not records:
        print("No completed parameter sweep records found.")
        sys.exit(0)

    print(f"Successfully loaded {len(records)} parameter result records.")

    # Organize data by (alpha, theta, d)
    results_map = {}
    for rec in records:
        d = rec.get("d_um", 0.1)
        theta = rec.get("theta_deg", 90.0)
        # Extract corrugation angle if saved, default 60.0
        alpha = rec.get("corrugation_angle", 60.0)
        
        f_both = rec.get("force_both", None)
        f_self = rec.get("force_self", None)
        
        if f_both is not None and f_self is not None:
            f_net = f_both - f_self
            A_eff = get_effective_area(3, rec.get("L", 2.0))
            p = f_net / A_eff
            key = (alpha, theta, d)
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "force_both": f_both,
                "force_self": f_self,
                "force_net": f_net,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }

    print(f"Consolidated {len(results_map)} unique (alpha, theta, d) parameter points.")

    # Summary directory output
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_hybrid_parameter_sweep_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    summary_file = os.path.join(out_dir, "hybrid_sweep_summary.json")
    with open(summary_file, "w") as f:
        json.dump(list(results_map.values()), f, indent=4)

    # Print Key Phase Space Highlights
    repulsive_points = [v for v in results_map.values() if v["is_repulsive"]]
    print("==================================================")
    print(f"Total Evaluated Points:  {len(results_map)}")
    print(f"Repulsive Points (P>0):  {len(repulsive_points)} / {len(results_map)}")
    if repulsive_points:
        max_repulsion = max(repulsive_points, key=lambda x: x["pressure_Pa"])
        print(f"Maximum Repulsive Pressure: +{max_repulsion['pressure_Pa']:.6f} Pa")
        print(f"  at alpha = {max_repulsion['alpha_deg']} deg, theta = {max_repulsion['theta_deg']} deg, d = {max_repulsion['d_um']} um")
    print("==================================================")

    # Auto-sync results to GitHub
    try:
        import subprocess
        print("Staging, committing, and pushing Hybrid Parameter Sweep results to GitHub...")
        subprocess.run(["git", "add", out_dir], check=False)
        diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff_res.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"Auto-sync Hybrid Casimir Parameter Sweep analysis from BigRed200"], check=False)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            subprocess.run(["git", "push", "origin", "main"], check=False)
            print("Git sync complete!")
        else:
            print("No new changes to push.")
    except Exception as e:
        print(f"Git push warning: {e}")

if __name__ == "__main__":
    main()
