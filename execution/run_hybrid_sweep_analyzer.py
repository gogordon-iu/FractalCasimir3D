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

    # Search for all completed simulation json result files in .tmp/ recursively
    tmp_files = set(glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json"))
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
        print("No completed parameter sweep records found.")
        sys.exit(0)

    print(f"Successfully loaded {len(records)} parameter result records.")

    # Organize data by (alpha, theta, d)
    results_map = {}
    partial_moments = {}

    for fp, rec in records:
        d = float(rec.get("d_um", 0.1))
        theta = float(rec.get("theta_deg", 90.0))
        alpha = float(rec.get("corrugation_angle", 60.0))
        
        f_both = rec.get("force_both", None)
        f_self = rec.get("force_self", None)
        f_sub = rec.get("force_subtracted", None)
        
        if f_both is not None and f_self is not None:
            f_net = float(f_both) - float(f_self)
            A_eff = get_effective_area(3, float(rec.get("L", 2.0)))
            p = f_net / A_eff
            key = (round(alpha, 1), round(theta, 1), round(d, 4))
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "force_both": float(f_both),
                "force_self": float(f_self),
                "force_net": f_net,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }
        elif "config" in rec and "force" in rec:
            # Handle partial moment files if present
            cfg = rec["config"]
            m_start = rec.get("moment_start", 0)
            m_end = rec.get("moment_end", 6)
            key = (round(alpha, 1), round(theta, 1), round(d, 4), cfg)
            if key not in partial_moments:
                partial_moments[key] = {}
            partial_moments[key][(m_start, m_end)] = float(rec["force"])

    # Consolidate any partial moment tasks if present
    for (alpha, theta, d, cfg), moments in list(partial_moments.items()):
        total_force = sum(moments.values())
        main_key = (alpha, theta, d)
        if main_key not in results_map:
            results_map[main_key] = {"alpha_deg": alpha, "theta_deg": theta, "d_um": d}
        if cfg == "both":
            results_map[main_key]["force_both"] = total_force
        elif cfg == "self":
            results_map[main_key]["force_self"] = total_force

    # Finalize pressure calculation for consolidated partials
    final_list = []
    for key, data in results_map.items():
        if "force_both" in data and "force_self" in data:
            f_both = data["force_both"]
            f_self = data["force_self"]
            f_net = f_both - f_self
            A_eff = get_effective_area(3, data.get("L", 2.0))
            p = f_net / A_eff
            data["force_net"] = f_net
            data["pressure_Pa"] = p
            data["is_repulsive"] = bool(p > 0.0)
            final_list.append(data)

    print(f"Consolidated {len(final_list)} unique (alpha, theta, d) parameter points.")

    # Summary directory output
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_hybrid_parameter_sweep_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    summary_file = os.path.join(out_dir, "hybrid_sweep_summary.json")
    with open(summary_file, "w") as f:
        json.dump(final_list, f, indent=4)

    # Print Key Phase Space Highlights
    repulsive_points = [v for v in final_list if v.get("is_repulsive", False)]
    print("==================================================")
    print(f"Total Evaluated Points:  {len(final_list)}")
    print(f"Repulsive Points (P>0):  {len(repulsive_points)} / {len(final_list)}")
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
            subprocess.run(["git", "commit", "-m", f"Auto-sync Hybrid Casimir Parameter Sweep analysis ({len(final_list)} points) from BigRed200"], check=False)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            subprocess.run(["git", "push", "origin", "main"], check=False)
            print("Git sync complete!")
        else:
            print("No new changes to push.")
    except Exception as e:
        print(f"Git push warning: {e}")

if __name__ == "__main__":
    main()
