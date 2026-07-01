import os

def main():
    L_vals = [0.3, 0.4, 0.5, 0.6]
    time_limits = {
        0.3: "06:00:00",
        0.4: "08:00:00",
        0.5: "10:00:00",
        0.6: "12:00:00"
    }
    
    # Define combinations
    runs = [
        {"suffix": "std_both", "material": "Phosphorene", "config": "both", "eps": "2.4"},
        {"suffix": "std_self", "material": "Phosphorene", "config": "self", "eps": "2.4"},
        {"suffix": "tuned_both", "material": "Phosphorene_tuned", "config": "both", "eps": "2.1"},
        {"suffix": "tuned_self", "material": "Phosphorene_tuned", "config": "self", "eps": "2.1"},
    ]
    
    os.makedirs("execution", exist_ok=True)
    
    for L in L_vals:
        L_str = f"{L:.1f}"
        
        # Write array scripts for each combination
        for run in runs:
            suffix = run["suffix"]
            mat = run["material"]
            cfg = run["config"]
            eps = run["eps"]
            
            sweep_file = f"execution/submit_twist_L_{L_str}_{suffix}.sbatch"
            with open(sweep_file, "w", newline='\n') as f:
                f.write(f"""#!/bin/bash
#SBATCH -J twist_L_{L_str}_{suffix}
#SBATCH -A r01540
#SBATCH -o logs/twist_L_{L_str}_{suffix}_%A_%a.out
#SBATCH -e logs/twist_L_{L_str}_{suffix}_%A_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time={time_limits[L]}
#SBATCH --array=0-6
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Twist angle list
THETAS=(0.0 15.0 30.0 45.0 60.0 75.0 90.0)
THETA=${{THETAS[$SLURM_ARRAY_TASK_ID]}}

# Create logs and cache directories
mkdir -p logs
mkdir -p .tmp

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1 for parallel MPI execution
export OMP_NUM_THREADS=1

echo "Running Twist Sweep L = {L_str} ({suffix}) task ID: $SLURM_ARRAY_TASK_ID (theta = $THETA deg)"

srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \\
    --d 0.1 \\
    --N 3 \\
    --material {mat} \\
    --res 40 \\
    --nmax 3 \\
    --theta "$THETA" \\
    --eps-bg {eps} \\
    --L {L_str} \\
    --config {cfg}
""")
                
        # Write the plot sbatch script
        plot_file = f"execution/submit_twist_L_{L_str}_plot.sbatch"
        with open(plot_file, "w", newline='\n') as f:
            f.write(f"""#!/bin/bash
#SBATCH -J twist_L_{L_str}_plot
#SBATCH -A r01540
#SBATCH -o logs/twist_L_{L_str}_plot_%j.out
#SBATCH -e logs/twist_L_{L_str}_plot_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1
export OMP_NUM_THREADS=1

echo "Starting twist sweep L = {L_str} plotting..."
$CONDA_PREFIX/bin/python execution/run_twist_sweep.py --cores 128 --L {L_str}
echo "Plotting complete."
""")
            
    print(f"Generated parallel sbatch files for L values: {L_vals}")

if __name__ == "__main__":
    main()
