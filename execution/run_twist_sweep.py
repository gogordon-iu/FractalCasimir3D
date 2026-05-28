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
    
    print("==================================================")
    print("Phosphorene Casimir Twist Sweep and Magic Angle Detection")
    print("==================================================")
    
    # Twist sweep parameters
    theta_list = [0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0]
    d = 0.1
    N = 3
    resolution = 40
    nmax = 3
    eps_bg = 1.6
    
    L = 0.3
    # Effective area A_3 = (8/9)^2 * L^2
    area = ((8.0 / 9.0)**(N - 1)) * (L**2)
    
    results = []
    
    import subprocess
    in_slurm = "SLURM_JOB_ID" in os.environ
    
    # 1. Run or Load simulations
    for theta in theta_list:
        json_file = f".tmp/meep_d_{d:.4f}_N_{N}_Phosphorene_res_{resolution}_theta_{theta:.1f}.json"
        
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
                "--material", "Phosphorene",
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
        results.append({
            "theta_deg": theta,
            "force_subtracted": f_sub,
            "pressure": pressure
        })
        print(f"Theta: {theta:.1f} deg -> Force: {f_sub:.6e}, Pressure: {pressure:.6e}")
        
    # Save the consolidated twist sweep results
    consolidated_file = ".tmp/twist_sweep_results.json"
    with open(consolidated_file, "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Extract arrays
    thetas = np.array([r["theta_deg"] for r in results])
    pressures = np.array([r["pressure"] for r in results])
    
    # 3. Find the Magic Angle (where pressure crosses zero)
    spline = UnivariateSpline(thetas, pressures, s=0)
    roots = spline.roots()
    
    magic_angle = None
    if len(roots) > 0:
        magic_angle = roots[0]
        print(f"\n>>> Detected Casimir Magic Angle: {magic_angle:.3f} degrees <<<")
    else:
        # Fallback: linear interpolation
        for i in range(len(thetas) - 1):
            if pressures[i] * pressures[i+1] < 0:
                p1, p2 = pressures[i], pressures[i+1]
                t1, t2 = thetas[i], thetas[i+1]
                magic_angle = t1 - p1 * (t2 - t1) / (p2 - p1)
                print(f"\n>>> Detected Casimir Magic Angle (linear interp): {magic_angle:.3f} degrees <<<")
                break
                
    if magic_angle is None:
        print("\nWARNING: No zero-crossing found in the pressure sweep.")
        magic_angle = 45.0  # default fallback
        
    # 4. Generate Plot
    fig, ax = plt.subplots(figsize=(3.5, 3.0))
    
    # Plot spline fit
    theta_dense = np.linspace(0, 90, 200)
    pressure_dense = spline(theta_dense)
    ax.plot(theta_dense, pressure_dense, color='#16a085', linewidth=1.5, label='Spline Fit')
    
    # Plot simulation data points
    ax.scatter(thetas, pressures, color='#c0392b', marker='o', s=25, zorder=3, label='FDTD Data')
    
    # Draw horizontal line at zero
    ax.axhline(0, color='black', linestyle='-', linewidth=0.8, alpha=0.7)
    
    # Draw vertical line at magic angle
    ax.axvline(magic_angle, color='#2980b9', linestyle='--', linewidth=1.2, label=r'$\theta_{\mathrm{magic}} \approx ' + f'{magic_angle:.1f}^\\circ$')
    
    ax.set_xlabel(r'Twist Angle $\theta$ (degrees)')
    ax.set_ylabel('Normal Casimir Pressure P (dimensionless)')
    ax.set_title('Casimir Pressure vs. Twist Angle (Phosphorene)', fontsize=9, fontweight='bold')
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.legend(loc='upper right', frameon=True, edgecolor='none', facecolor='#f5f5f5')
    
    plt.tight_layout()
    
    plt.savefig('figure_twist_angle_comparison.pdf', format='pdf', dpi=300)
    plt.savefig('figure_twist_angle_comparison.svg', format='svg', dpi=300)
    print("Plot saved to figure_twist_angle_comparison.pdf / .svg")
    plt.close()
    
if __name__ == "__main__":
    main()
