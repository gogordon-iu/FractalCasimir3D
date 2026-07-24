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
    parser = argparse.ArgumentParser(description="Consolidate partial moment files for Frontier 1: 3D Stepped Fractal Sieve Casimir Repulsion.")
    parser.add_argument("--L", type=float, default=2.0, help="Plate length in microns.")
    parser.add_argument("--d", type=float, default=0.12, help="Gap separation in microns.")
    parser.add_argument("--N-top", type=int, default=3, help="Prefractal generation of top plate.")
    parser.add_argument("--N-bottom", type=int, default=3, help="Prefractal generation of bottom plate.")
    parser.add_argument("--resolution", type=int, default=40, help="Resolution (pixels/um).")
    parser.add_argument("--theta", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument("--eps-bg", type=float, default=2.1, help="Background dielectric constant.")
    parser.add_argument("--material", type=str, default="Phosphorene_tuned", help="Material name.")
    parser.add_argument("--cores", type=int, default=128, help="Number of cores used.")
    parser.add_argument("--plot-only", action="store_true", help="Only generate plot and summary without throwing error on missing files.")
    args = parser.parse_args()

    L = args.L
    d = args.d
    N_top = args.N_top
    N_bot = args.N_bottom
    resolution = args.resolution
    theta = args.theta
    eps_bg = args.eps_bg
    mat = args.material

    print("==================================================")
    print("FRONTIER 1: 3D STEPPED FRACTAL SIEVE CASIMIR SWEEP ANALYSIS")
    print(f"Parameters: L = {L:.2f} um, d = {d:.2f} um ({d*1000:.0f} nm), N_top = {N_top}, N_bottom = {N_bot}")
    print(f"Resolution = {resolution}, theta = {theta} deg, eps_bg = {eps_bg}")
    print("==================================================")

    nbot_str = f"_sieve_Nbot_{N_bot}"
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
            
            if files:
                with open(files[0], "r") as f:
                    data = json.load(f)
                    forces[cfg][(m_start, m_end)] = data["force"]
            else:
                missing_segments.append((cfg, m_start, m_end))

    if missing_segments:
        print(f"STATUS: INCOMPLETE ({len(missing_segments)} segments missing)")
        for cfg, m_start, m_end in missing_segments:
            print(f"  Missing: config_{cfg} moments_{m_start}_{m_end}")
        if not args.plot_only:
            sys.exit(1)
        return

    print("STATUS: COMPLETE! All 36 simulation segment files found.")

    f_both = sum(forces["both"].values())
    f_self = sum(forces["self"].values())
    f_subtracted = f_both - f_self
    
    A_eff = get_effective_area(N_top, L)
    pressure = f_subtracted / A_eff
    is_repulsive = bool(pressure > 0.0)

    regime_str = "REPULSIVE (POSITIVE PRESSURE - CASIMIR LEVITATION!)" if is_repulsive else "ATTRACTIVE (NEGATIVE PRESSURE)"

    print("==================================================")
    print(f"Force (Both Plates):       {f_both:.8e}")
    print(f"Force (Self Plate):        {f_self:.8e}")
    print(f"Force (Subtracted Net):    {f_subtracted:.8e}")
    print(f"Effective Area (A_eff):    {A_eff:.6f} um^2")
    print(f"Consolidated Pressure:     {pressure:.8e}")
    print(f"CASIMIR REGIME:            {regime_str}")
    print("==================================================")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_sieve_L_{L:.2f}_d_{d:.2f}_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    summary_data = {
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
        "pressure": pressure,
        "is_repulsive": is_repulsive,
        "regime": regime_str
    }

    with open(os.path.join(out_dir, "sieve_sweep_results.json"), "w") as f:
        json.dump(summary_data, f, indent=4)

    with open(os.path.join(out_dir, "parameters.txt"), "w") as f:
        for k, v in summary_data.items():
            f.write(f"{k}: {v}\n")

    print(f"Saved 3D Stepped Sieve sweep analysis to {out_dir}/")

    # Auto-push results to GitHub
    try:
        import subprocess
        print("Staging, committing, and pushing 3D Stepped Sieve results to GitHub...")
        subprocess.run(["git", "add", out_dir], check=False)
        diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff_res.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"Auto-sync 3D Stepped Sieve results (L={L:.2f}um, d={d:.2f}um) from BigRed200"], check=False)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            subprocess.run(["git", "push", "origin", "main"], check=False)
            print("Git sync complete!")
        else:
            print("No new changes to push.")
    except Exception as e:
        print(f"Git push warning: {e}")

if __name__ == "__main__":
    main()
