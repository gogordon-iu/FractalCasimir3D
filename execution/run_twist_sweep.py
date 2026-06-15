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
    args = parser.parse_args()
    
    import datetime
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = f"results_twist_{now_str}"
    os.makedirs(outdir, exist_ok=True)
    
    # Twist sweep parameters
    theta_list = [0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0]
    d = 0.1
    N = 3
    resolution = 40
    nmax = 3
    eps_bg = 1.6
    
    # Save parameters.txt
    with open(os.path.join(outdir, "parameters.txt"), "w") as f:
        f.write(f"--cores {args.cores}\n")
        f.write(f"--res {resolution}\n")
        f.write(f"--d {d}\n")
        f.write(f"--N {N}\n")
        f.write(f"--eps_bg {eps_bg}\n")
        
    print("==================================================")
    print("Phosphorene Casimir Twist Sweep and Magic Angle Detection")
    print("==================================================")
    
    L = 0.3
    # Effective area A_3 = (8/9)^2 * L^2
    area = ((8.0 / 9.0)**(N - 1)) * (L**2)
    
    results = {
        "Phosphorene": [],
        "Phosphorene_tuned": []
    }
    
    import subprocess
    in_slurm = "SLURM_JOB_ID" in os.environ
    
    # 1. Run or Load simulations
    for mat in ["Phosphorene", "Phosphorene_tuned"]:
        print(f"\n--- Sweeping material: {mat} ---")
        for theta in theta_list:
            json_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}.json"
            
            if os.path.exists(json_file):
                print(f"Found cached results for theta = {theta:.1f} deg in {json_file}")
                with open(json_file, "r") as f:
                    data = json.load(f)
                    f_sub = data["force_subtracted"]
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
                    "--eps-bg", f"{eps_bg:.1f}"
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
                    
            # Normal pressure: P = F / Area
            pressure = f_sub / area
            results[mat].append({
                "theta_deg": theta,
                "force_subtracted": f_sub,
                "pressure": pressure
            })
            print(f"Theta: {theta:.1f} deg -> Force: {f_sub:.6e}, Pressure: {pressure:.6e}")
        
    # Save the consolidated twist sweep results
    consolidated_file = os.path.join(outdir, "twist_sweep_results.json")
    with open(consolidated_file, "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Extract arrays
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
    ax.plot(theta_dense, spline_orig(theta_dense), color='#c0392b', linestyle='--', linewidth=1.2, label=r'Original Phosphorene ($\epsilon_z = 1.2$, Untuned)')
    ax.scatter(thetas, pressures_orig, color='#c0392b', marker='o', s=20, zorder=3)
    
    # Plot tuned Phosphorene curve
    ax.plot(theta_dense, spline_tuned(theta_dense), color='#27ae60', linestyle='-', linewidth=1.5, label=r'Tuned Phosphorene ($\epsilon_z = 1.6$, Magic Angle)')
    ax.scatter(thetas, pressures_tuned, color='#27ae60', marker='s', s=20, zorder=3)
    
    # Draw horizontal line at zero
    ax.axhline(0, color='black', linestyle='-', linewidth=0.8, alpha=0.7)
    
    # Draw vertical line at magic angle
    ax.axvline(magic_angle, color='#2980b9', linestyle='--', linewidth=1.2, label=r'$\theta_{\mathrm{magic}} \approx ' + f'{magic_angle:.1f}^\\circ$')
    
    ax.set_xlabel(r'Twist Angle $\theta$ (degrees)')
    ax.set_ylabel('Normal Casimir Pressure P (dimensionless)')
    ax.set_title('Casimir Pressure vs. Twist Angle Comparison', fontsize=9, fontweight='bold')
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.legend(loc='lower left', frameon=True, edgecolor='none', facecolor='#f5f5f5')
    
    plt.tight_layout()
    
    pdf_path = os.path.join(outdir, 'figure_twist_angle_comparison.pdf')
    svg_path = os.path.join(outdir, 'figure_twist_angle_comparison.svg')
    plt.savefig(pdf_path, format='pdf', dpi=300)
    plt.savefig(svg_path, format='svg', dpi=300)
    print(f"Plot saved to {pdf_path} / {svg_path}")
    plt.close()
    
if __name__ == "__main__":
    main()
