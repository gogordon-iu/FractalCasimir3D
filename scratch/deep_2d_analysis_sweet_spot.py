import os
import glob
import json
import numpy as np

def main():
    print("==================================================")
    print("DEEP 2D PARAMETER SWEEP & ANOMALY ANALYSIS")
    print("==================================================")

    # 1. Gather all unique parameter points from raw .tmp JSONs and summary JSONs
    data_dict = {} # key: (alpha, theta, d) -> record
    
    # Check all summary files
    summary_files = sorted(glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json"))
    for sf in summary_files:
        try:
            with open(sf, "r") as f:
                records = json.load(f)
                for r in records:
                    if isinstance(r, dict) and "pressure_Pa" in r and abs(r["pressure_Pa"]) > 1e-15:
                        key = (round(float(r["alpha_deg"]), 1), round(float(r["theta_deg"]), 1), round(float(r["d_um"]), 4))
                        data_dict[key] = r
        except Exception:
            pass

    # Check raw .tmp JSON files
    tmp_files = glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")
    for f in tmp_files:
        try:
            with open(f, "r") as fp:
                d = json.load(fp)
                if isinstance(d, dict) and "force_both" in d and "force_self" in d:
                    f_sub = d.get("force_subtracted", d["force_both"] - d["force_self"])
                    L_val = d.get("L", 2.0)
                    area_m2 = (L_val * 1e-6) ** 2
                    c_const = 299792458.0
                    hbar = 1.054571817e-34
                    # P in Pa = F_meep * (hbar * c) / Area^2
                    force_N = f_sub * (hbar * c_const) / (L_val * 1e-6)
                    pressure_Pa = force_N / area_m2
                    
                    alpha_v = round(float(d.get("corrugation_angle", 45.0)), 1)
                    theta_v = round(float(d.get("theta_deg", d.get("theta", 0.0))), 1)
                    d_v = round(float(d.get("d_um", d.get("d", 0.1))), 4)
                    
                    key = (alpha_v, theta_v, d_v)
                    if key not in data_dict or abs(pressure_Pa) > abs(data_dict[key].get("pressure_Pa", 0)):
                        data_dict[key] = {
                            "alpha_deg": alpha_v,
                            "theta_deg": theta_v,
                            "d_um": d_v,
                            "force_both": d["force_both"],
                            "force_self": d["force_self"],
                            "force_subtracted": f_sub,
                            "pressure_Pa": pressure_Pa,
                            "is_repulsive": pressure_Pa > 0
                        }
        except Exception:
            pass

    all_records = list(data_dict.values())
    print(f"Total Unique Physical Parameter Points: {len(all_records)}")
    
    repulsive = [r for r in all_records if r["pressure_Pa"] > 0]
    print(f"Repulsive Levitation Points (P > 0): {len(repulsive)} / {len(all_records)} ({len(repulsive)/len(all_records)*100:.1f}%)")

    alphas = sorted(list(set(r["alpha_deg"] for r in all_records)))
    thetas = sorted(list(set(r["theta_deg"] for r in all_records)))
    ds = sorted(list(set(r["d_um"] for r in all_records)))
    print(f"Wall Slopes (alpha): {alphas}")
    print(f"Twist Angles (theta): {thetas}")
    print(f"Separations (d in um): {ds}")

    # -------------------------------------------------------------
    # 2D Parameter Grids & Phase Boundary Mapping
    # -------------------------------------------------------------
    print("\n" + "="*60)
    print("2D PARAMETER MATRICES: P(theta, alpha) at Fixed Gaps d")
    print("="*60)
    
    for d_target in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        grid_pts = [r for r in all_records if abs(r["d_um"] - d_target) < 1e-3]
        if not grid_pts:
            continue
        print(f"\n--- 2D Grid at d = {d_target*1000:.0f} nm ({d_target:.2f} um) [Total Points: {len(grid_pts)}] ---")
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

    # -------------------------------------------------------------
    # Anomaly Detection & Critical Phenomena
    # -------------------------------------------------------------
    print("\n" + "="*60)
    print("ANOMALY DETECTION & PHYSICAL SINGULARITY REPORT")
    print("="*60)

    # Anomaly 1: Super-Repulsion Resonance Peaks (P > 0.1 Pa)
    print("\n[ANOMALY 1] Giant Repulsive Levitation Resonance Peaks (P > 0.05 Pa):")
    peaks = sorted([r for r in all_records if r["pressure_Pa"] > 0.05], key=lambda x: -x["pressure_Pa"])
    for p in peaks:
        print(f"  --> GIANT LEVITATION: Alpha={p['alpha_deg']}°, Theta={p['theta_deg']}°, d={p['d_um']*1000:.1f} nm => P = {p['pressure_Pa']:+.6f} Pa")

    # Anomaly 2: Non-Monotonic Distance Dependence (dP/dd > 0 followed by dP/dd < 0)
    print("\n[ANOMALY 2] Non-Monotonic Distance Inversion & Levitation Traps:")
    # Group by (alpha, theta)
    curves = {}
    for r in all_records:
        key = (r["alpha_deg"], r["theta_deg"])
        if key not in curves:
            curves[key] = []
        curves[key].append(r)
        
    stable_wells = []
    for (al, th), pts in curves.items():
        pts.sort(key=lambda x: x["d_um"])
        if len(pts) >= 3:
            p_vals = [p["pressure_Pa"] for p in pts]
            d_vals = [p["d_um"] * 1000 for p in pts]
            # Check for zero-crossing from positive to negative (stable equilibrium trap)
            for i in range(len(p_vals) - 1):
                if p_vals[i] > 0 and p_vals[i+1] < 0:
                    d_eq = d_vals[i] + (0.0 - p_vals[i]) * (d_vals[i+1] - d_vals[i]) / (p_vals[i+1] - p_vals[i])
                    stable_wells.append((al, th, d_eq, max(p_vals)))
                    print(f"  --> STABLE LEVITATION TRAP: Alpha={al}°, Theta={th}° => Stable Gap d_eq = {d_eq:.2f} nm (P_max = {max(p_vals):+.4e} Pa)")

    # Anomaly 3: Angular Asymmetry around Theta = 90 deg
    print("\n[ANOMALY 3] Angular Asymmetry Across Cross-Polarization (Theta = 90 deg):")
    for al in alphas:
        pts_al = [r for r in all_records if abs(r["alpha_deg"] - al) < 1e-1]
        thetas_present = sorted(list(set(r["theta_deg"] for r in pts_al)))
        for th in [80.0, 82.0, 84.0, 86.0, 88.0]:
            th_mirror = 180.0 - th if th > 90 else (90.0 + (90.0 - th))
            match_left = [r for r in pts_al if abs(r["theta_deg"] - th) < 1e-1 and abs(r["d_um"] - 0.1) < 1e-3]
            match_right = [r for r in pts_al if abs(r["theta_deg"] - th_mirror) < 1e-1 and abs(r["d_um"] - 0.1) < 1e-3]
            if match_left and match_right:
                pl, pr = match_left[0]["pressure_Pa"], match_right[0]["pressure_Pa"]
                diff = abs(pl - pr)
                print(f"  --> Alpha={al}° at d=100nm: P({th}°) = {pl:+.6f} Pa vs P({th_mirror}°) = {pr:+.6f} Pa (Delta = {diff:.6f} Pa)")

if __name__ == '__main__':
    main()
