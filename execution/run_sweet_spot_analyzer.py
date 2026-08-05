import os
import sys
import glob
import json
import datetime
import subprocess
import numpy as np

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def main():
    print("==================================================")
    print("SWEET SPOT PARAMETER SWEEP RESULTS ANALYZER")
    print("==================================================")

    # 1. Search for all output JSONs across historical sweeps and new sweet spot sweep
    summary_files = glob.glob("results_*/sweet_spot_sweep_summary.json") + glob.glob("results_*/hybrid_sweep_summary.json")
    tmp_files = glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")

    records = []
    for fp in summary_files + tmp_files:
        try:
            with open(fp, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict) and ("d_um" in data or "d" in data):
                    records.append(data)
        except Exception:
            pass

    print(f"Loaded {len(records)} total JSON result records across all sweeps.")

    # 2. Extract and organize unique physical points
    results_map = {}
    for rec in records:
        d = float(rec.get("d_um", rec.get("d", 0.1)))
        theta = float(rec.get("theta_deg", rec.get("theta", 90.0)))
        alpha = float(rec.get("corrugation_angle", rec.get("alpha_deg", rec.get("alpha", 60.0))))
        
        f_both = rec.get("force_both", None)
        f_self = rec.get("force_self", None)
        p_direct = rec.get("pressure_Pa", rec.get("pressure", None))
        
        if p_direct is not None:
            p = float(p_direct)
            key = (round(alpha, 1), round(theta, 1), round(d, 4))
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }
        elif f_both is not None and f_self is not None:
            f_net = float(f_both) - float(f_self)
            A_eff = get_effective_area(3, float(rec.get("L", 2.0)))
            p = f_net / A_eff
            key = (round(alpha, 1), round(theta, 1), round(d, 4))
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }

    data_list = list(results_map.values())
    print(f"Extracted {len(data_list)} unique physical parameter points.")

    # Sort data points logically
    data_list.sort(key=lambda x: (x["alpha_deg"], x["theta_deg"], x["d_um"]))

    # Save timestamped summary directory
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_sweet_spot_sweep_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    summary_file = os.path.join(out_dir, "sweet_spot_sweep_summary.json")
    with open(summary_file, "w") as f:
        json.dump(data_list, f, indent=4)

    print(f"Saved consolidated sweet spot summary to '{summary_file}'.")

    # 3. Find Nanomechanical Levitation Equilibrium Heights (P=0 with dP/dd < 0)
    print("
--------------------------------------------------")
    print("NANOMECHANICAL LEVITATION EQUILIBRIUM HEIGHT ANALYSIS (P = 0, dP/dd < 0)")
    print("--------------------------------------------------")
    
    # Group by (alpha, theta)
    curves = {}
    for r in data_list:
        key = (r["alpha_deg"], r["theta_deg"])
        if key not in curves:
            curves[key] = []
        curves[key].append(r)

    eq_points = []
    for (a, th), pts in curves.items():
        pts.sort(key=lambda x: x["d_um"])
        if len(pts) >= 2:
            d_arr = [p["d_um"] for p in pts]
            p_arr = [p["pressure_Pa"] for p in pts]
            
            # Check for zero crossings from positive to negative as d increases (stable levitation point!)
            for i in range(len(p_arr) - 1):
                if p_arr[i] > 0 and p_arr[i+1] < 0:
                    # Linear interpolation for zero crossing
                    d1, d2 = d_arr[i], d_arr[i+1]
                    p1, p2 = p_arr[i], p_arr[i+1]
                    d_eq = d1 + (0.0 - p1) * (d2 - d1) / (p2 - p1)
                    eq_points.append({
                        "alpha_deg": a,
                        "theta_deg": th,
                        "d_eq_nm": round(d_eq * 1000.0, 2),
                        "d_eq_um": round(d_eq, 4),
                        "p_max_Pa": max(p_arr)
                    })
                    print(f"FOUND STABLE EQUILIBRIUM: Alpha={a} deg, Theta={th} deg => d_eq = {d_eq*1000.0:.2f} nm (P_max = {max(p_arr):+.4f} Pa)")

    # 4. Auto-commit and push results to GitHub
    try:
        print("
Auto-syncing sweet spot sweep results to GitHub...")
        subprocess.run(["git", "add", summary_file], check=True)
        subprocess.run(["git", "commit", "-m", f"Add sweet spot parameter sweep results ({timestamp})"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Successfully synced sweet spot results to GitHub!")
    except Exception as e:
        print(f"Git auto-sync notice: {e}")

if __name__ == "__main__":
    main()
