import os
import glob
import json
import numpy as np

def main():
    print("==================================================")
    print("FINAL 224-POINT SWEET SPOT SWEEP ANALYSIS")
    print("==================================================")

    # 1. Load latest consolidated summary
    summary_file = 'results_sweet_spot_sweep_20260831_134421/sweet_spot_sweep_summary.json'
    if not os.path.exists(summary_file):
        print(f"Summary file {summary_file} not found!")
        return

    data = json.load(open(summary_file))
    print(f"Total Unique Physical Configurations in Summary: {len(data)}")

    # Extract all parameters
    alphas = sorted(list(set(r['alpha_deg'] for r in data)))
    thetas = sorted(list(set(r['theta_deg'] for r in data)))
    ds = sorted(list(set(r['d_um'] for r in data)))
    print(f"Wall Slopes (alpha): {alphas}")
    print(f"Twist Angles (theta): {thetas}")
    print(f"Separations (d in um): {ds}")

    repulsive = [r for r in data if r.get('pressure_Pa', 0) > 0]
    print(f"\nRepulsive Levitation Points (P > 0): {len(repulsive)} / {len(data)} ({len(repulsive)/len(data)*100:.1f}%)")

    # 2. Audit completed vs missing tasks from sweep_configs_sweet_spot (1-224)
    config_files = sorted(glob.glob("sweep_configs_sweet_spot/config_*.json"))
    configs_map = {}
    for cf in config_files:
        try:
            task_num = int(os.path.basename(cf).replace("config_", "").replace(".json", ""))
            with open(cf, "r") as fp:
                cdata = json.load(fp)
                key = (round(float(cdata["d"]), 4), round(float(cdata["theta"]), 1), round(float(cdata["alpha"]), 1))
                configs_map[key] = task_num
        except Exception:
            pass

    completed_tasks = set()
    for r in data:
        key = (round(float(r["d_um"]), 4), round(float(r["theta_deg"]), 1), round(float(r["alpha_deg"]), 1))
        if key in configs_map:
            completed_tasks.add(configs_map[key])

    all_task_ids = set(range(1, 225))
    missing_tasks = sorted(list(all_task_ids - completed_tasks))
    print(f"\nCompleted Sweep Tasks: {len(completed_tasks)} / 224 ({len(completed_tasks)/224*100:.1f}%)")
    print(f"Remaining / Missing Tasks: {len(missing_tasks)} / 224")
    if missing_tasks:
        print(f"Missing Task IDs: {missing_tasks[:20]} ...")

    # 3. 2D Parameter Grid Matrices P(theta, alpha) at all separations d
    print("\n" + "="*80)
    print("FULL 2D PARAMETER MATRICES: P(theta, alpha) [Pa]")
    print("="*80)

    for d_target in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        grid_pts = [r for r in data if abs(r["d_um"] - d_target) < 1e-3]
        if not grid_pts:
            continue
        print(f"\n--- 2D Grid at d = {d_target*1000:.0f} nm ({d_target:.2f} um) [Points: {len(grid_pts)}] ---")
        grid_alphas = sorted(list(set(r["alpha_deg"] for r in grid_pts)))
        grid_thetas = sorted(list(set(r["theta_deg"] for r in grid_pts)))
        
        header = f"{'alpha / theta':<14}" + "".join([f"{th:>10.1f}°" for th in grid_thetas])
        print(header)
        print("-" * len(header))
        for al in grid_alphas:
            row_str = f"{al:>5.1f}°        "
            for th in grid_thetas:
                match = [r for r in grid_pts if abs(r["alpha_deg"] - al) < 1e-1 and abs(r["theta_deg"] - th) < 1e-1]
                if match:
                    p_val = match[0]["pressure_Pa"]
                    if p_val > 0:
                        row_str += f"{p_val:>+10.4f} "
                    else:
                        row_str += f"{p_val:>10.4f} "
                else:
                    row_str += f"{'--':>10} "
            print(row_str)

    # 4. Top Repulsive Levitation Peaks
    print("\n" + "="*80)
    print("TOP REPULSIVE LEVITATION PEAKS (P > 0)")
    print("="*80)
    rep_sorted = sorted(repulsive, key=lambda x: -x['pressure_Pa'])
    for i, r in enumerate(rep_sorted[:20], 1):
        print(f"{i:2d}. alpha={r['alpha_deg']:4.1f}° | theta={r['theta_deg']:4.1f}° | d={r['d_um']*1000:5.1f} nm => P = {r['pressure_Pa']:+10.6f} Pa")

    # 5. Stable Nanomechanical Levitation Equilibrium Traps (P = 0, dP/dd < 0)
    print("\n" + "="*80)
    print("STABLE NANOMECHANICAL LEVITATION EQUILIBRIUM TRAPS (P = 0, dP/dd < 0)")
    print("="*80)
    curves = {}
    for r in data:
        key = (r["alpha_deg"], r["theta_deg"])
        if key not in curves:
            curves[key] = []
        curves[key].append(r)

    stable_traps = []
    for (al, th), pts in curves.items():
        pts.sort(key=lambda x: x["d_um"])
        if len(pts) >= 3:
            p_vals = [p["pressure_Pa"] for p in pts]
            d_vals = [p["d_um"] * 1000 for p in pts]
            for i in range(len(p_vals) - 1):
                if p_vals[i] > 0 and p_vals[i+1] < 0:
                    d_eq = d_vals[i] + (0.0 - p_vals[i]) * (d_vals[i+1] - d_vals[i]) / (p_vals[i+1] - p_vals[i])
                    stable_traps.append((al, th, d_eq, max(p_vals)))
                    print(f"  --> STABLE EQUILIBRIUM TRAP: Alpha={al:4.1f}°, Theta={th:4.1f}° => Stable Gap d_eq = {d_eq:6.2f} nm (P_max = {max(p_vals):+9.4e} Pa)")

if __name__ == '__main__':
    main()
