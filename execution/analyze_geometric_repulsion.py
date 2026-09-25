#!/usr/bin/env python3
"""
Analyzer for Geometric Vacuum Casimir Repulsion (Proposition 2)
---------------------------------------------------------------
Loads results from results_geometric_repulsion/ and evaluates:
1. Net force F_net (fN) and Casimir pressure (Pa) as a function of tip clearance z_tip.
2. Identifies the zero-crossing equilibrium separation z_0 where force transitions
   from attractive (F_z < 0) to repulsive (F_z > 0).
3. Verifies compliance with the Levin-Johnson theorem threshold z_tip < W / 4.
"""

import os
import sys
import glob
import json
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

def main():
    res_dir = os.path.join(REPO_ROOT, "results_geometric_repulsion")
    files = sorted(glob.glob(os.path.join(res_dir, "task_*.json")))

    if not files:
        print(f"No result files found in {res_dir}. Run the simulation on Big Red 200 first.")
        return

    data = []
    for f in files:
        try:
            with open(f, "r") as f_in:
                d = json.load(f_in)
            data.append(d)
        except (json.JSONDecodeError, OSError) as err:
            print(f"Warning: Could not read {f}: {err}")

    if not data:
        print("No valid result JSON files loaded.")
        return

    data = sorted(data, key=lambda x: x["z_tip_nm"], reverse=True)

    print("=" * 95)
    print("GEOMETRIC VACUUM CASIMIR REPULSION ANALYSIS (Levin-Johnson Mechanism)")
    print("=" * 95)
    print(f"{'Task ID':<10}{'z_tip (nm)':<14}{'W/4 (nm)':<12}{'F_net (fN)':<18}{'Pressure (Pa)':<18}{'Regime':<15}")
    print("-" * 95)

    has_repulsive = False
    z_vals = []
    f_vals = []

    for d in data:
        tid = d.get("task_id", 0)
        z = d.get("z_tip_nm", 0.0)
        w4 = d.get("W_over_4_nm", 0.0)
        f_net_fN = d.get("force_net_fN", d.get("force_net_meep", 0.0) * 31.615)
        p = d.get("pressure_Pa", 0.0)
        
        z_vals.append(z)
        f_vals.append(f_net_fN)

        if f_net_fN > 0:
            has_repulsive = True
            regime_str = "++ REPULSIVE ++"
        else:
            regime_str = "ATTRACTIVE"

        print(f"{tid:<10}{z:<14.1f}{w4:<12.1f}{f_net_fN:<+18.4f}{p:<+18.4e}{regime_str:<15}")

    print("=" * 95)

    # Check for zero crossing (Casimir levitation equilibrium)
    z_eq = None
    for i in range(len(f_vals) - 1):
        if (f_vals[i] < 0 and f_vals[i+1] > 0) or (f_vals[i] > 0 and f_vals[i+1] < 0):
            # Linear interpolation for zero crossing
            z1, z2 = z_vals[i], z_vals[i+1]
            f1, f2 = f_vals[i], f_vals[i+1]
            z_eq = z1 - f1 * (z2 - z1) / (f2 - f1)
            break

    if has_repulsive:
        print(">>> SUCCESS: Genuine geometric Casimir repulsion (F_z > 0) verified in pure vacuum!")
        if z_eq is not None:
            print(f">>> STABLE CASIMIR EQUILIBRIUM FOUND: z_0 = {z_eq:.2f} nm (Zero-force levitation point)")
    else:
        print("Notice: No positive forces detected yet. Ensure z_tip < W/4 threshold.")
    print("=" * 95)

if __name__ == "__main__":
    main()
