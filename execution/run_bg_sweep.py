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
    parser = argparse.ArgumentParser(description="Consolidate and plot dielectric background sweep results.")
    parser.add_argument("--cores", type=int, default=12, help="Number of MPI cores to use for running simulations.")
    args = parser.parse_args()
    
    import datetime
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = f"results_bg_sweep_{now_str}"
    os.makedirs(outdir, exist_ok=True)
    
    # Background sweep parameters
    eps_bg_list = [1.5, 1.8, 2.1, 2.4, 2.7, 3.0, 3.3, 3.6]
    d = 0.1
    N = 3
    resolution = 40
    nmax = 3
    theta = 90.0
    
    # Save parameters.txt
    with open(os.path.join(outdir, "parameters.txt"), "w") as f:
        f.write(f"--cores {args.cores}\n")
        f.write(f"--res {resolution}\n")
        f.write(f"--d {d}\n")
        f.write(f"--N {N}\n")
        f.write(f"--theta {theta}\n")
        f.write(f"--eps_bg_list {','.join(map(str, eps_bg_list))}\n")
        
    print("==================================================")
    print("Phosphorene Casimir Background Sweep at Theta = 90 deg")
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
        for eps in eps_bg_list:
            json_file = f".tmp/meep_d_{d:.4f}_N_{N}_{mat}_res_{resolution}_theta_{theta:.1f}_eps_{eps:.1f}.json"
            
            if os.path.exists(json_file):
                print(f"Found cached results for eps_bg = {eps:.1f} in {json_file}")
                with open(json_file, "r") as f:
                    data = json.load(f)
                    f_sub = data["force_subtracted"]
            else:
                print(f"Running parallel FDTD simulation for eps_bg = {eps:.1f}...")
                sim_cmd = [
                    sys.executable,
                    "execution/run_meep_simulation.py",
                    "--d", f"{d:.4f}",
                    "--N", str(N),
                    "--material", mat,
                    "--res", str(resolution),
                    "--nmax", str(nmax),
                    "--theta", f"{theta:.1f}",
                    "--eps-bg", f"{eps:.1f}"
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
                "eps_bg": eps,
                "force_subtracted": f_sub,
                "pressure": pressure
            })
            print(f"eps_bg: {eps:.1f} -> Force: {f_sub:.6e}, Pressure: {pressure:.6e}")
        
    # Save the consolidated background sweep results
    consolidated_file = os.path.join(outdir, "bg_sweep_results.json")
    with open(consolidated_file, "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Extract arrays
    eps_vals = np.array([r["eps_bg"] for r in results["Phosphorene_tuned"]])
    pressures_tuned = np.array([r["pressure"] for r in results["Phosphorene_tuned"]])
    
    # 3. Find the zero-crossover background permittivity
    spline_tuned = UnivariateSpline(eps_vals, pressures_tuned, s=0)
    roots = spline_tuned.roots()
    
    magic_eps = None
    if len(roots) > 0:
        magic_eps = roots[0]
        print(f"\n>>> Detected Repulsive Background Permittivity: {magic_eps:.3f} <<<")
    else:
        # Fallback: linear interpolation
        for i in range(len(eps_vals) - 1):
            if pressures_tuned[i] * pressures_tuned[i+1] < 0:
                p1, p2 = pressures_tuned[i], pressures_tuned[i+1]
                e1, e2 = eps_vals[i], eps_vals[i+1]
                magic_eps = e1 - p1 * (e2 - e1) / (p2 - p1)
                print(f"\n>>> Detected Repulsive Background Permittivity (linear interp): {magic_eps:.3f} <<<")
                break
                
    if magic_eps is None:
        print("\nWARNING: No zero-crossing found in the background permittivity sweep.")
        
    # 4. Generate Plot
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    
    eps_dense = np.linspace(eps_bg_list[0], eps_bg_list[-1], 200)
    
    # Plot original Phosphorene curve
    pressures_orig = np.array([r["pressure"] for r in results["Phosphorene"]])
    spline_orig = UnivariateSpline(eps_vals, pressures_orig, s=0)
    ax.plot(eps_dense, spline_orig(eps_dense), color='#c0392b', linestyle='--', linewidth=1.2, label=r'Original Phosphorene ($\epsilon_z = 1.2$, Untuned)')
    ax.scatter(eps_vals, pressures_orig, color='#c0392b', marker='o', s=20, zorder=3)
    
    # Plot tuned Phosphorene curve
    ax.plot(eps_dense, spline_tuned(eps_dense), color='#27ae60', linestyle='-', linewidth=1.5, label=r'Tuned Phosphorene ($\epsilon_z = \epsilon_{\mathrm{bg}}$, Tuned)')
    ax.scatter(eps_vals, pressures_tuned, color='#27ae60', marker='s', s=20, zorder=3)
    
    # Draw horizontal line at zero
    ax.axhline(0, color='black', linestyle='-', linewidth=0.8, alpha=0.7)
    
    # Draw vertical line at zero crossing
    if magic_eps is not None:
        ax.axvline(magic_eps, color='#2980b9', linestyle='--', linewidth=1.2, label=r'Crossover $\epsilon_{\mathrm{bg}} \approx ' + f'{magic_eps:.2f}$')
    
    ax.set_xlabel(r'Background Permittivity $\epsilon_{\mathrm{bg}}$')
    ax.set_ylabel('Normal Casimir Pressure P (dimensionless)')
    ax.set_title('Casimir Pressure vs. Background Permittivity (Theta=90)', fontsize=8, fontweight='bold')
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    ax.legend(loc='lower left', frameon=True, edgecolor='none', facecolor='#f5f5f5')
    
    plt.tight_layout()
    
    pdf_path = os.path.join(outdir, 'figure_bg_sweep.pdf')
    svg_path = os.path.join(outdir, 'figure_bg_sweep.svg')
    plt.savefig(pdf_path, format='pdf', dpi=300)
    plt.savefig(svg_path, format='svg', dpi=300)
    print(f"Plot saved to {pdf_path} / {svg_path}")
    plt.close()
    
if __name__ == "__main__":
    main()
