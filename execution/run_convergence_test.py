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
    parser.add_argument("--run-missing", action="store_true", help="Run simulations for missing resolutions instead of skipping them.")
    args = parser.parse_args()
    
    import datetime
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = f"results_convergence_{now_str}"
    os.makedirs(outdir, exist_ok=True)
    
    resolutions = [20, 40, 60, 80, 100, 120]
    d = 0.1
    N = 2
    material = "Gold"
    nmax = 1
    
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
            # Auto-consolidate individual task files if the config file doesn't exist
            for cfg in ["both", "self"]:
                cfg_file = f".tmp/meep_d_{d:.4f}_N_{N}_{material}_res_{res}_theta_0.0_config_{cfg}.json"
                if not os.path.exists(cfg_file):
                    task_files = [
                        f".tmp/meep_d_{d:.4f}_N_{N}_{material}_res_{res}_theta_0.0_config_{cfg}_task_{i}.json"
                        for i in range(36 * nmax)
                    ]
                    if all(os.path.exists(tf) for tf in task_files):
                        print(f"Consolidating 36 task files for resolution = {res} px/um (config {cfg})...")
                        total_f = 0.0
                        for tf in task_files:
                            try:
                                with open(tf, "r") as f:
                                    tf_data = json.load(f)
                                total_f += tf_data["force"]
                            except Exception as e:
                                print(f"Error reading {tf}: {e}")
                                total_f = None
                                break
                        
                        if total_f is not None:
                            consolidated_config_data = {
                                "d_um": d,
                                "N": N,
                                "material": material,
                                "resolution": res,
                                "theta_deg": 0.0,
                                "eps_bg": 1.0,
                                f"force_{cfg}": total_f
                            }
                            with open(cfg_file, "w") as f:
                                json.dump(consolidated_config_data, f, indent=4)

            # Check if separate config_both and config_self files exist, and compile them
            both_file = f".tmp/meep_d_{d:.4f}_N_{N}_{material}_res_{res}_theta_0.0_config_both.json"
            self_file = f".tmp/meep_d_{d:.4f}_N_{N}_{material}_res_{res}_theta_0.0_config_self.json"
            if os.path.exists(both_file) and os.path.exists(self_file):
                print(f"Found separate both/self files for resolution = {res} px/um. Consolidating...")
                with open(both_file, "r") as f:
                    both_data = json.load(f)
                with open(self_file, "r") as f:
                    self_data = json.load(f)
                f_both = both_data["force_both"]
                f_self = self_data["force_self"]
                f_sub = f_both - f_self
                
                # Save the consolidated JSON file
                consolidated_data = {
                    "d_um": d,
                    "N": N,
                    "material": material,
                    "resolution": res,
                    "theta_deg": 0.0,
                    "eps_bg": both_data.get("eps_bg", 1.0),
                    "force_both": f_both,
                    "force_self": f_self,
                    "force_subtracted": f_sub
                }
                with open(json_file, "w") as f:
                    json.dump(consolidated_data, f, indent=4)
            else:
                if args.run_missing:
                    print(f"Running parallel FDTD simulation for resolution = {res} px/um...")
                    sim_cmd = [
                        sys.executable,
                        "execution/run_meep_simulation.py",
                        "--d", f"{d:.4f}",
                        "--N", str(N),
                        "--material", material,
                        "--res", str(res),
                        "--nmax", str(nmax),
                        "--T-run", "20.0"
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
                    
                    if os.path.exists(json_file):
                        with open(json_file, "r") as f:
                            data = json.load(f)
                            f_sub = data["force_subtracted"]
                    else:
                        print(f"ERROR: Simulation failed to generate {json_file}")
                        continue
                else:
                    print(f"WARNING: Cached result file not found: {json_file}. Skipping resolution {res}.")
                    continue
                
        # Fractional PFA deviation: eta = (F_FDTD - F_PFA) / F_PFA
        eta = (f_sub - f_pfa) / f_pfa
        results.append({
            "resolution": res,
            "force_subtracted": f_sub,
            "eta": eta
        })
        print(f"Resolution: {res} px/um -> Force: {f_sub:.6e}, Deviation (eta): {eta*100:.4f}%")
        
    if not results:
        print("ERROR: No valid simulation results found in .tmp! Exiting.")
        sys.exit(1)
        
    # Save the consolidated convergence results
    consolidated_file = os.path.join(outdir, "convergence_results.json")
    with open(consolidated_file, "w") as f:
        json.dump(results, f, indent=4)
        
    # 2. Extract arrays
    res_arr = np.array([r["resolution"] for r in results])
    eta_arr = np.array([r["eta"] for r in results])
    
    # 3. Verify Convergence Tolerance (change between two highest available resolutions)
    if len(res_arr) >= 2:
        # Sort by resolution
        sort_idx = np.argsort(res_arr)
        res_sorted = res_arr[sort_idx]
        eta_sorted = eta_arr[sort_idx]
        
        res_max_1 = res_sorted[-2]
        res_max_2 = res_sorted[-1]
        eta_max_1 = eta_sorted[-2]
        eta_max_2 = eta_sorted[-1]
        
        deviation_diff = abs(eta_max_2 - eta_max_1)
        print(f"\nDeviation at R={res_max_1}: {eta_max_1*100:.6f}%")
        print(f"Deviation at R={res_max_2}: {eta_max_2*100:.6f}%")
        print(f"Absolute change: {deviation_diff*100:.6f}%")
        
        if deviation_diff < 0.001:
            print(f">>> CONVERGENCE VERIFIED: Grid discretization change between {res_max_1} and {res_max_2} is < 0.1%! <<<")
        else:
            print(f"WARNING: Grid discretization change between {res_max_1} and {res_max_2} is >= 0.1%. Higher resolution may be needed.")
        status_text = f"Change ({res_max_1} -> {res_max_2}):\n{deviation_diff*100:.4f}%"
    else:
        deviation_diff = 0.0
        print("\nWARNING: Only one resolution data point available. Cannot compute convergence change.")
        status_text = "Insufficient Data"
        
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
