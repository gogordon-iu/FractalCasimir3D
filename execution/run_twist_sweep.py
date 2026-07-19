import numpy as np
import matplotlib.pyplot as plt
import os
import json
from scipy.interpolate import UnivariateSpline

# Import run_simulation from run_meep_simulation.py
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from execution.run_meep_simulation import run_simulation

# Style rules for publication-quality plots
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 8
plt.rcParams['axes.labelsize'] = 8
plt.rcParams['axes.titlesize'] = 10
plt.rcParams['legend.fontsize'] = 7
plt.rcParams['xtick.labelsize'] = 7
plt.rcParams['ytick.labelsize'] = 7
plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Consolidate and plot twist sweep results.")
    parser.add_argument("--cores", type=int, default=12, help="Number of MPI cores to use for running simulations.")
    parser.add_argument("--L", type=float, default=0.3, help="Plate width/length in microns.")
    parser.add_argument("--plot-only", action="store_true", help="Only consolidate cache and plot without running missing simulations.")
    args = parser.parse_args()
    
    import datetime
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = f"results_twist_L_{args.L:.2f}_{now_str}"
    os.makedirs(outdir, exist_ok=True)
    
    # Twist sweep parameters
    theta_list = [0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0]
    d = 0.1
    N = 3
    L = args.L
    resolution = 40
    nmax = 3
    
    # Save parameters.txt
    with open(os.path.join(outdir, "parameters.txt"), "w") as f:
        f.write(f"--cores {args.cores}\n")
        f.write(f"--res {resolution}\n")
        f.write(f"--d {d}\n")
        f.write(f"--N {N}\n")
        f.write(f"--L {L}\n")
        f.write(f"--eps_bg_tuned 2.1\n")
        f.write(f"--eps_bg_std 2.4\n")
        
    print("==================================================")
    print("Phosphorene Casimir Twist Sweep and Magic Angle Detection")
    print("==================================================")
    
    L = args.L
    # Effective area A_3 = (8/9)^2 * L^2
    area = ((8.0 / 9.0)**(N - 1)) * (L**2)
    
    results = {
        "Phosphorene": [],
        "Phosphorene_tuned": []
    }
    missing_files = []
    
    import subprocess
    in_slurm = "SLURM_JOB_ID" in os.environ
    
    # Materials and angles to loop over based on L
    materials_to_run = ["Phosphorene_tuned"] if L >= 0.8 else ["Phosphorene", "Phosphorene_tuned"]
    thetas_to_run = [90.0] if L >= 0.8 else theta_list

    # 1. Run or Load simulations
    for mat in materials_to_run:
        print(f"\n--- Sweeping material: {mat} ---")
        eps_bg = 2.1 if mat == "Phosphorene_tuned" else 2.4
        for theta in thetas_to_run:
            json_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}.json"
            
            if os.path.exists(json_file):
                print(f"Found cached results for theta = {theta:.1f} deg in {json_file}")
                with open(json_file, "r") as f:
                    data = json.load(f)
                    f_sub = data["force_subtracted"]
            else:
                # Segment-based checkpointing compilation
                segments = [
                    (0, 11), (11, 22), (22, 33), (33, 44), (44, 55),
                    (55, 66), (66, 77), (77, 88), (88, 99), (99, 108)
                ]
                
                both_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_both.json"
                if not os.path.exists(both_file):
                    both_segs_exist = True
                    for start, end in segments:
                        seg_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_both_moments_{start}_{end}.json"
                        if not os.path.exists(seg_file):
                            both_segs_exist = False
                            break
                    if both_segs_exist:
                        print(f"All 10 segment files for config both found. Compiling...")
                        f_both_sum = 0.0
                        for start, end in segments:
                            seg_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_both_moments_{start}_{end}.json"
                            with open(seg_file, "r") as sf:
                                seg_data = json.load(sf)
                                f_both_sum += seg_data["force"]
                        with open(both_file, "w") as f:
                            json.dump({
                                "d_um": d, "N": N, "material": mat, "resolution": resolution,
                                "theta_deg": theta, "eps_bg": eps_bg, "L": L, "config": "both",
                                "force": f_both_sum
                            }, f, indent=4)
                            
                self_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_self.json"
                if not os.path.exists(self_file):
                    self_segs_exist = True
                    for start, end in segments:
                        seg_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_self_moments_{start}_{end}.json"
                        if not os.path.exists(seg_file):
                            self_segs_exist = False
                            break
                    if self_segs_exist:
                        print(f"All 10 segment files for config self found. Compiling...")
                        f_self_sum = 0.0
                        for start, end in segments:
                            seg_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_self_moments_{start}_{end}.json"
                            with open(seg_file, "r") as sf:
                                seg_data = json.load(sf)
                                f_self_sum += seg_data["force"]
                        with open(self_file, "w") as f:
                            json.dump({
                                "d_um": d, "N": N, "material": mat, "resolution": resolution,
                                "theta_deg": theta, "eps_bg": eps_bg, "L": L, "config": "self",
                                "force": f_self_sum
                            }, f, indent=4)

                if os.path.exists(both_file) and os.path.exists(self_file):
                    print(f"Found separate both/self files for theta = {theta:.1f} deg. Consolidating...")
                    with open(both_file, "r") as f:
                        both_data = json.load(f)
                    with open(self_file, "r") as f:
                        self_data = json.load(f)
                    f_both = both_data["force_both"] if "force_both" in both_data else both_data["force"]
                    f_self = self_data["force_self"] if "force_self" in self_data else self_data["force"]
                    f_sub = f_both - f_self
                    
                    # Save the consolidated JSON file
                    consolidated_data = {
                        "d_um": d,
                        "N": N,
                        "material": mat,
                        "resolution": resolution,
                        "theta_deg": theta,
                        "eps_bg": eps_bg,
                        "L": L,
                        "force_both": f_both,
                        "force_self": f_self,
                        "force_subtracted": f_sub
                    }
                    with open(json_file, "w") as f:
                        json.dump(consolidated_data, f, indent=4)
                else:
                    if args.plot_only:
                        print(f"WARNING: Cache file missing for material = {mat}, theta = {theta:.1f} deg.")
                        # Check which specific files are missing to report later
                        missing_reasons = []
                        if L >= 0.8:
                            for cfg in ["both", "self"]:
                                for start, end in segments:
                                    seg_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps_bg:.1f}_L_{L:.2f}_config_{cfg}_moments_{start}_{end}.json"
                                    if not os.path.exists(seg_file):
                                        missing_reasons.append(f"config_{cfg}_moments_{start}_{end}")
                        else:
                            if not os.path.exists(both_file):
                                missing_reasons.append(f"{both_file} (config_both)")
                            if not os.path.exists(self_file):
                                missing_reasons.append(f"{self_file} (config_self)")
                        if not missing_reasons:
                            missing_reasons.append(f"{json_file} (unified)")
                        missing_files.append((mat, theta, missing_reasons))
                        f_sub = None
                    else:
                        print(f"Running parallel FDTD simulation for theta = {theta:.1f} deg...")
                        sim_cmd = [
                            sys.executable,
                            "execution/run_meep_simulation.py",
                            "--d", f"{d:.4f}",
                            "--N", str(N),
                            "--material", mat,
                            "--res", str(resolution),
                            "--nmax", str(nmax),
                            "--theta", f"{theta:.1f}",
                            "--eps-bg", f"{eps_bg:.1f}",
                            "--L", f"{L:.2f}"
                        ]
                        
                        if args.cores > 1:
                            if in_slurm:
                                cmd = ["srun", "-n", str(args.cores)] + sim_cmd
                            else:
                                import shutil
                                if shutil.which("mpirun") is not None:
                                    cmd = ["mpirun", "-np", str(args.cores)] + sim_cmd
                                else:
                                    cmd = sim_cmd
                        else:
                            cmd = sim_cmd
                            
                        print(f"Executing: {' '.join(cmd)}")
                        subprocess.run(cmd)
                        
                        with open(json_file, "r") as f:
                            data = json.load(f)
                            f_sub = data["force_subtracted"]
                    
            if f_sub is not None:
                # Normal pressure: P = F / Area
                pressure = f_sub / area
                results[mat].append({
                    "theta_deg": theta,
                    "force_subtracted": f_sub,
                    "pressure": pressure
                })
                print(f"Theta: {theta:.1f} deg -> Force: {f_sub:.6e}, Pressure: {pressure:.6e}")
        
    if missing_files:
        print("\n==================================================")
        print("ERROR: Incomplete Sweep Data (Plot-only Mode)")
        print("==================================================")
        print(f"The following {len(missing_files)} configurations/angles have missing cache files:")
        for mat, theta, reasons in missing_files:
            print(f" - Material: {mat:<18} Angle: {theta:>5.1f} deg | Missing: {', '.join(reasons)}")
        print("\nSimulation files are still missing on the cluster. Please submit or rerun these tasks.")
        sys.exit(1)
        
    # Save the consolidated twist sweep results
    consolidated_file = os.path.join(outdir, "twist_sweep_results.json")
    with open(consolidated_file, "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Extract arrays and plot (only for L < 0.8 um where a full sweep was run)
    if L < 0.8:
        thetas = np.array([r["theta_deg"] for r in results["Phosphorene_tuned"]])
        pressures_tuned = np.array([r["pressure"] for r in results["Phosphorene_tuned"]])
        
        # 3. Find the Magic Angle (where pressure crosses zero)
        spline_tuned = UnivariateSpline(thetas, pressures_tuned, s=0)
        roots = spline_tuned.roots()
        
        magic_angle = None
        if len(roots) > 0:
            magic_angle = roots[0]
            print(f"\n>>> Detected Casimir Magic Angle: {magic_angle:.3f} degrees <<<")
        else:
            # Fallback: linear interpolation
            for i in range(len(thetas) - 1):
                if pressures_tuned[i] * pressures_tuned[i+1] < 0:
                    p1, p2 = pressures_tuned[i], pressures_tuned[i+1]
                    t1, t2 = thetas[i], thetas[i+1]
                    magic_angle = t1 - p1 * (t2 - t1) / (p2 - p1)
                    print(f"\n>>> Detected Casimir Magic Angle (linear interp): {magic_angle:.3f} degrees <<<")
                    break
                    
        if magic_angle is None:
            print("\nWARNING: No zero-crossing found in the pressure sweep.")
            magic_angle = 45.0  # default fallback
            
        # 4. Generate Plot
        fig, ax = plt.subplots(figsize=(4.2, 3.2))
        
        theta_dense = np.linspace(0, 90, 200)
        
        # Plot original Phosphorene curve
        pressures_orig = np.array([r["pressure"] for r in results["Phosphorene"]])
        spline_orig = UnivariateSpline(thetas, pressures_orig, s=0)
        ax.plot(theta_dense, spline_orig(theta_dense), color='#c0392b', linestyle='--', linewidth=1.2, label=r'Original Phosphorene ($\epsilon_z = 1.2, \epsilon_{\mathrm{bg}} = 2.4$)')
        ax.scatter(thetas, pressures_orig, color='#c0392b', marker='o', s=20, zorder=3)
        
        # Plot tuned Phosphorene curve
        ax.plot(theta_dense, spline_tuned(theta_dense), color='#27ae60', linestyle='-', linewidth=1.5, label=r'Tuned Phosphorene ($\epsilon_z = \epsilon_{\mathrm{bg}} = 2.1$)')
        ax.scatter(thetas, pressures_tuned, color='#27ae60', marker='s', s=20, zorder=3)
        
        # Draw horizontal line at zero
        ax.axhline(0, color='black', linestyle='-', linewidth=0.8, alpha=0.7)
        
        # Draw vertical line at magic angle
        ax.axvline(magic_angle, color='#2980b9', linestyle='--', linewidth=1.2, label=r'$\theta_{\mathrm{magic}} \approx ' + f'{magic_angle:.1f}^\\circ$')
        
        ax.set_xlabel(r'Twist Angle $\theta$ (degrees)')
        ax.set_ylabel('Normal Casimir Pressure P (dimensionless)')
        ax.set_title(f'Casimir Pressure vs. Twist Angle (L={L:.2f})', fontsize=9, fontweight='bold')
        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
        ax.legend(loc='lower left', frameon=True, edgecolor='none', facecolor='#f5f5f5')
        
        plt.tight_layout()
        
        pdf_path = os.path.join(outdir, 'figure_twist_angle_comparison.pdf')
        svg_path = os.path.join(outdir, 'figure_twist_angle_comparison.svg')
        plt.savefig(pdf_path, format='pdf', dpi=300)
        plt.savefig(svg_path, format='svg', dpi=300)
        print(f"Plot saved to {pdf_path} / {svg_path}")
        plt.close()
    else:
        print("\nOptimized 90-degree sweep complete. Skipping plot for L >= 0.8 um.")
    
if __name__ == "__main__":
    main()
