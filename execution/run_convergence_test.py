import numpy as np
import matplotlib.pyplot as plt
import os
import json

# Import run_simulation from run_meep_simulation.py and get_force_density_lifshitz from run_pfa_model.py
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from execution.run_meep_simulation import run_simulation
from execution.run_pfa_model import get_force_density_lifshitz

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
    parser = argparse.ArgumentParser(description="Sweep MEEP resolution and plot convergence.")
    parser.add_argument("--cores", type=int, default=12, help="Number of MPI cores to use for running simulations.")
    args = parser.parse_args()
    
    import datetime
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = f"results_convergence_{now_str}"
    os.makedirs(outdir, exist_ok=True)
    
    resolutions = [20, 40, 60, 80, 100, 120]
    d = 0.1
    N = 2
    material = "Gold"
    nmax = 3
    
    # Save parameters.txt
    with open(os.path.join(outdir, "parameters.txt"), "w") as f:
        f.write(f"--cores {args.cores}\n")
        f.write(f"--d {d}\n")
        f.write(f"--N {N}\n")
        f.write(f"--material {material}\n")
        f.write(f"--resolutions {','.join(map(str, resolutions))}\n")
        
    print("==================================================")
    print("Yee Grid Resolution Convergence Test Sweep (Gold)")
    print("==================================================")
    L = 0.3
    # Effective area A_2 = (8/9) * L^2
    area = (8.0 / 9.0) * (L**2)
    
    # Calculate PFA baseline force
    f_pfa_dens = get_force_density_lifshitz(d, material, T=0)
    f_pfa = f_pfa_dens * area
    print(f"PFA Baseline Force Density: {f_pfa_dens:.6e}")
    print(f"PFA Baseline Force (N=2, L=0.3): {f_pfa:.6e}")
    
    results = []
    
    import subprocess
    in_slurm = "SLURM_JOB_ID" in os.environ
    
    # 1. Run or Load simulations
    for res in resolutions:
        json_file = f".tmp/meep_d_{d:.4f}_N_{N}_{material}_res_{res}_theta_0.0.json"
        
        if os.path.exists(json_file):
            print(f"Found cached results for resolution = {res} px/um in {json_file}")
            with open(json_file, "r") as f:
                data = json.load(f)
                f_sub = data["force_subtracted"]
        else:
            print(f"Running parallel FDTD simulation for resolution = {res} px/um...")
            sim_cmd = [
                sys.executable,
                "execution/run_meep_simulation.py",
                "--d", f"{d:.4f}",
                "--N", str(N),
                "--material", material,
                "--res", str(res),
                "--nmax", str(nmax)
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
                
        # Fractional PFA deviation: eta = (F_FDTD - F_PFA) / F_PFA
        eta = (f_sub - f_pfa) / f_pfa
        results.append({
            "resolution": res,
            "force_subtracted": f_sub,
            "eta": eta
        })
        print(f"Resolution: {res} px/um -> Force: {f_sub:.6e}, Deviation (eta): {eta*100:.4f}%")
        
    # Save the consolidated convergence results
    consolidated_file = os.path.join(outdir, "convergence_results.json")
    with open(consolidated_file, "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Extract arrays
    res_arr = np.array([r["resolution"] for r in results])
    eta_arr = np.array([r["eta"] for r in results])
    
    # 3. Verify Convergence Tolerance (< 0.1% change between 100 and 120 px/um)
    eta_100 = eta_arr[res_arr == 100][0]
    eta_120 = eta_arr[res_arr == 120][0]
    deviation_diff = abs(eta_120 - eta_100)
    print(f"\nDeviation at R=100: {eta_100*100:.6f}%")
    print(f"Deviation at R=120: {eta_120*100:.6f}%")
    print(f"Absolute change: {deviation_diff*100:.6f}%")
    
    if deviation_diff < 0.001:
        print(">>> CONVERGENCE VERIFIED: Grid discretization change is < 0.1%! <<<")
    else:
        print("WARNING: Grid discretization change is >= 0.1%. Higher resolution may be needed.")
        
    # 4. Generate Plot
    fig, ax = plt.subplots(figsize=(3.5, 3.0))
    
    # Plot convergence curve
    ax.plot(res_arr, eta_arr * 100.0, color='#2980b9', linestyle='-', marker='s', markersize=4, linewidth=1.2, label='FDTD Sweep')
    
    # Add labels and styling
    ax.set_xlabel(r'Resolution R (px/$\mu$m)')
    ax.set_ylabel('Fractional PFA Deviation (%)')
    ax.set_title('Grid Resolution Convergence Sweep (Gold)', fontsize=9, fontweight='bold')
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    
    # Text box with convergence status
    status_text = f"Change (100 -> 120):\n{deviation_diff*100:.4f}%"
    box_props = dict(boxstyle='round', facecolor='white', edgecolor='none', alpha=0.8)
    ax.text(0.05, 0.15, status_text, transform=ax.transAxes, fontsize=7, verticalalignment='bottom', bbox=box_props)
    
    plt.tight_layout()
    pdf_path = os.path.join(outdir, 'figure_convergence_test.pdf')
    svg_path = os.path.join(outdir, 'figure_convergence_test.svg')
    plt.savefig(pdf_path, format='pdf', dpi=300)
    plt.savefig(svg_path, format='svg', dpi=300)
    print(f"Plot saved to {pdf_path} / {svg_path}")
    plt.close()

if __name__ == "__main__":
    main()
