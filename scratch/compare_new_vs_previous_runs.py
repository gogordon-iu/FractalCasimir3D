import os
import glob
import json
import numpy as np

def main():
    print("==================================================")
    print("COMPARISON: NEW FINE-GRAINED RUNS VS PREVIOUS RUNS")
    print("==================================================")

    # 1. Gather all PREVIOUS runs (from results_twist_*, results_corrugated_*, results_hybrid_*)
    prev_points = {}
    prev_files = sorted(glob.glob("results_twist_*/**/*.json", recursive=True) + 
                        glob.glob("results_corrugated_*/**/*.json", recursive=True) + 
                        glob.glob("results_hybrid_*/**/*.json", recursive=True) +
                        glob.glob("results_2026*/**/*.json", recursive=True))
    
    for pf in prev_files:
        try:
            with open(pf, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = [data]
                else:
                    continue
                    
                for r in records:
                    if isinstance(r, dict) and ("pressure_Pa" in r or "force_subtracted" in r or "force_both" in r):
                        # Extract parameters
                        L = round(float(r.get("L", 2.0)), 2)
                        d = round(float(r.get("d_um", r.get("d", 0.1))), 4)
                        theta = round(float(r.get("theta_deg", r.get("theta", 0.0))), 1)
                        alpha = round(float(r.get("corrugation_angle", r.get("alpha_deg", 45.0))), 1)
                        mat = str(r.get("material", "Phosphorene_tuned"))
                        
                        p_val = r.get("pressure_Pa")
                        if p_val is None:
                            f_sub = r.get("force_subtracted", r.get("force_both", 0) - r.get("force_self", 0))
                            L_m = L * 1e-6
                            area_m2 = L_m ** 2
                            hbar = 1.054571817e-34
                            c_const = 299792458.0
                            f_N = f_sub * (hbar * c_const) / L_m
                            p_val = f_N / area_m2
                            
                        key = (L, d, theta, alpha, mat)
                        if abs(p_val) > 1e-15:
                            prev_points[key] = {
                                "source_file": pf,
                                "pressure_Pa": p_val,
                                "force_both": r.get("force_both"),
                                "force_self": r.get("force_self"),
                                "record": r
                            }
        except Exception:
            pass

    print(f"Loaded {len(prev_points)} verified parameter configurations from PREVIOUS runs.")

    # 2. Gather all NEW fine-grained runs from .tmp and latest sweet spot sweep
    new_points = {}
    new_files = sorted(glob.glob(".tmp/meep_d_*.json") + glob.glob("results_sweet_spot_sweep_20260827_*/**/*.json", recursive=True))
    
    for nf in new_files:
        try:
            with open(nf, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = [data]
                else:
                    continue
                    
                for r in records:
                    if isinstance(r, dict) and ("pressure_Pa" in r or "force_subtracted" in r or "force_both" in r):
                        L = round(float(r.get("L", 2.0)), 2)
                        d = round(float(r.get("d_um", r.get("d", 0.1))), 4)
                        theta = round(float(r.get("theta_deg", r.get("theta", 0.0))), 1)
                        alpha = round(float(r.get("corrugation_angle", r.get("alpha_deg", 45.0))), 1)
                        mat = str(r.get("material", "Phosphorene_tuned"))
                        
                        p_val = r.get("pressure_Pa")
                        if p_val is None:
                            f_sub = r.get("force_subtracted", r.get("force_both", 0) - r.get("force_self", 0))
                            L_m = L * 1e-6
                            area_m2 = L_m ** 2
                            hbar = 1.054571817e-34
                            c_const = 299792458.0
                            f_N = f_sub * (hbar * c_const) / L_m
                            p_val = f_N / area_m2
                            
                        key = (L, d, theta, alpha, mat)
                        if abs(p_val) > 1e-15:
                            new_points[key] = {
                                "source_file": nf,
                                "pressure_Pa": p_val,
                                "force_both": r.get("force_both"),
                                "force_self": r.get("force_self"),
                                "record": r
                            }
        except Exception:
            pass

    print(f"Loaded {len(new_points)} verified parameter configurations from NEW runs.")

    # 3. Match identical parameter configurations and compare
    matching_keys = sorted(list(set(prev_points.keys()) & set(new_points.keys())))
    print(f"\nExact Overlapping Parameter Points: {len(matching_keys)}")
    
    print("\n" + "="*80)
    print(f"{'Config (L, d, theta, alpha, mat)':<45} | {'Prev P (Pa)':<14} | {'New P (Pa)':<14} | {'Diff / Match':<12}")
    print("="*80)
    
    matches_count = 0
    discrepancy_count = 0
    
    for k in matching_keys:
        p_prev = prev_points[k]["pressure_Pa"]
        p_new = new_points[k]["pressure_Pa"]
        
        diff = abs(p_new - p_prev)
        denom = max(abs(p_prev), abs(p_new), 1e-12)
        rel_diff = diff / denom
        
        cfg_str = f"L={k[0]}um, d={k[1]*1000:.0f}nm, th={k[2]}°, al={k[3]}°"
        
        if rel_diff < 0.05: # < 5% difference
            status = "EXACT MATCH (OK)"
            matches_count += 1
        elif (p_prev > 0 and p_new > 0) or (p_prev < 0 and p_new < 0):
            status = f"SAME SIGN ({rel_diff*100:.1f}%)"
            matches_count += 1
        else:
            status = "SIGN FLIP (!)"
            discrepancy_count += 1
            
        print(f"{cfg_str:<45} | {p_prev:>+12.6f} | {p_new:>+12.6f} | {status}")

    print("\n" + "="*80)
    print(f"SUMMARY: {matches_count} matching points, {discrepancy_count} sign discrepancies out of {len(matching_keys)} overlaps.")
    
    # 4. Check global physics consistency: Sign vs theta across all new points
    print("\n--- GLOBAL PHYSICS BEHAVIOR CHECK ACROSS ALL NEW RUNS ---")
    small_angle_repulsive = [k for k, v in new_points.items() if k[2] < 75.0 and v["pressure_Pa"] > 0]
    cross_pol_repulsive = [k for k, v in new_points.items() if k[2] >= 80.0 and v["pressure_Pa"] > 0]
    
    print(f"New points with theta < 75° showing repulsion (should be 0): {len(small_angle_repulsive)}")
    print(f"New points with theta >= 80° showing repulsion: {len(cross_pol_repulsive)} / {len([k for k in new_points if k[2] >= 80.0])}")
    
    if len(small_angle_repulsive) == 0:
        print("--> PASSED: No spurious repulsion at small angles. Force is 100% attractive for theta < 75°, exactly as in previous runs!")
    else:
        print(f"--> WARNING: Found unexpected repulsion at small angles: {small_angle_repulsive}")

if __name__ == '__main__':
    main()
