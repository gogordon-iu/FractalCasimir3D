import os
import sys
import json
import glob
import datetime
import argparse
import numpy as np

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def main():
    parser = argparse.ArgumentParser(description="Consolidate and analyze Asymmetric Dual-Fractal Casimir simulations.")
    parser.add_argument("--L", type=float, default=2.0, help="Plate width in microns.")
    parser.add_argument("--d", type=float, default=0.25, help="Plate gap in microns.")
    parser.add_argument("--N-top", type=int, default=3, help="Top plate iteration level.")
    parser.add_argument("--N-bottom", type=int, default=2, help="Bottom plate iteration level.")
    parser.add_argument("--res", type=int, default=40, help="Resolution.")
    parser.add_argument("--theta", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument("--eps-bg", type=float, default=2.1, help="Background dielectric constant.")
    parser.add_argument("--material", type=str, default="Phosphorene_tuned", help="Material.")
    parser.add_argument("--cores", type=int, default=128, help="Number of cores.")
    parser.add_argument("--plot-only", action="store_true", help="Only check file status without exiting with error if incomplete.")
    args = parser.parse_args()

    L = args.L
    d = args.d
    N_top = args.N_top
    N_bot = args.N_bottom
    resolution = args.res
    theta = args.theta
    eps_bg = args.eps_bg
    mat = args.material

    segments = [(i * 6, (i + 1) * 6) for i in range(18)]

    results = {}
    missing_segments = []

    for config in ["both", "self"]:
        total_force = 0.0
        complete = True
        for m_start, m_end in segments:
            pattern = f".tmp/meep_d_{d:.4f}_N_{N_top}_Nbot_{N_bot}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_{config}_moments_{m_start}_{m_end}.json"
            files = glob.glob(pattern)
            if files:
                with open(files[0], "r") as f:
                    data = json.load(f)
                    total_force += data["force"]
            else:
                complete = False
                missing_segments.append((config, m_start, m_end))

        if complete:
            results[f"force_{config}"] = total_force

    print("==================================================")
    print(f"ASYMMETRIC DUAL-FRACTAL CASIMIR SWEEP SUMMARY")
    print(f"L = {L:.2f} um, d = {d:.2f} um ({d*1000:.0f} nm), N_top = {N_top}, N_bottom = {N_bot}")
    print(f"Material: {mat}, Theta = {theta:.1f} deg, Resolution = {resolution}")
    print("==================================================")

    if missing_segments:
        print(f"STATUS: INCOMPLETE ({len(missing_segments)} segments missing)")
        for cfg, m_start, m_end in missing_segments:
            print(f"  Missing: config_{cfg} moments_{m_start}_{m_end}")
        if not args.plot_only:
            sys.exit(1)
        return

    f_both = results["force_both"]
    f_self = results["force_self"]
    f_subtracted = f_both - f_self
    A_eff = get_effective_area(N_top, L)
    pressure = f_subtracted / A_eff

    is_repulsive = pressure > 0
    regime_str = "REPULSIVE (POSITIVE PRESSURE!)" if is_repulsive else "ATTRACTIVE (NEGATIVE PRESSURE)"

    print(f"Force (Both Plates):       {f_both:.8e}")
    print(f"Force (Self Plate):        {f_self:.8e}")
    print(f"Force (Subtracted Net):    {f_subtracted:.8e}")
    print(f"Effective Area (A_eff):    {A_eff:.6f} um^2")
    print(f"Consolidated Pressure:     {pressure:.8e}")
    print(f"CASIMIR REGIME:            {regime_str}")
    print("==================================================")

    # Save results directory
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_asym_L_{L:.2f}_d_{d:.2f}_{timestamp}"
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

    with open(os.path.join(out_dir, "asymmetric_sweep_results.json"), "w") as f:
        json.dump(summary_data, f, indent=4)

    with open(os.path.join(out_dir, "parameters.txt"), "w") as f:
        for k, v in summary_data.items():
            f.write(f"{k}: {v}\n")

    print(f"Saved asymmetric sweep analysis to {out_dir}/")

if __name__ == "__main__":
    main()
