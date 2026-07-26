import os
import sys
import json
import itertools

def main():
    print("==================================================")
    print("SLURM GENERATOR: Hybrid Casimir Levitation Parameter Sweep Project")
    print("==================================================")

    # 1. Parameter Grid Definition
    # Slope Angles (deg)
    angles = [30.0, 45.0, 54.7, 60.0, 65.0]
    
    # Twist Angles (deg) - 90 deg anisotropic + Moire twist delta
    thetas = [0.0, 90.0, 90.5, 91.1, 92.5, 95.0]
    
    # Separations (um)
    distances = [0.08, 0.10, 0.12, 0.15, 0.20, 0.30]

    # Shared parameters
    L = 2.0
    N_top = 3
    N_bot = 3
    resolution = 40
    eps_bg = 2.1
    material = "Phosphorene_tuned"

    output_dir = "execution"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("sweep_configs", exist_ok=True)

    param_list = []
    param_id = 0

    for alpha, th, d in itertools.product(angles, thetas, distances):
        param_id += 1
        config = {
            "param_id": param_id,
            "alpha": float(alpha),
            "theta": float(th),
            "d": float(d),
            "L": L,
            "N_top": N_top,
            "N_bot": N_bot,
            "resolution": resolution,
            "eps_bg": eps_bg,
            "material": material
        }
        param_list.append(config)
        
        # Save config JSON
        cfg_path = os.path.join("sweep_configs", f"config_{param_id:03d}.json")
        with open(cfg_path, "w") as f:
            json.dump(config, f, indent=4)

    print(f"Generated {len(param_list)} parameter configurations in sweep_configs/")

    # Generate Slurm Job Array Script (use forward slashes for Linux compatibility)
    sbatch_array_path = "execution/submit_hybrid_sweep_array.sbatch"
    
    array_content = f"""#!/bin/bash
#SBATCH -J hybrid_casimir_sweep
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=08:00:00
#SBATCH --array=1-{len(param_list)}%10
#SBATCH -o logs/sweep_task_%A_%a.out
#SBATCH -e logs/sweep_task_%A_%a.err

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Get parameter ID from Slurm array index
PARAM_ID=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs/config_${{PARAM_ID}}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file $CONFIG_FILE not found."
    exit 1
fi

echo "=================================================="
echo "Running Hybrid Casimir Sweep Task ID: $PARAM_ID"
echo "Config File: $CONFIG_FILE"
echo "=================================================="

# Parse parameters from JSON
ALPHA=$($CONDA_PREFIX/bin/python -c "import json; print(json.load(open('$CONFIG_FILE'))['alpha'])")
THETA=$($CONDA_PREFIX/bin/python -c "import json; print(json.load(open('$CONFIG_FILE'))['theta'])")
D_UM=$($CONDA_PREFIX/bin/python -c "import json; print(json.load(open('$CONFIG_FILE'))['d'])")

echo "Parameters: alpha=${{ALPHA}} deg, theta=${{THETA}} deg, d=${{D_UM}} um"

# Execute simulation for both and self configurations
$CONDA_PREFIX/bin/python execution/run_meep_simulation.py \\
    --d $D_UM \\
    --N 3 \\
    --N-bottom 3 \\
    --L 2.0 \\
    --material Phosphorene_tuned \\
    --res 40 \\
    --theta $THETA \\
    --eps-bg 2.1 \\
    --corrugated \\
    --corrugation-angle $ALPHA \\
    --config all

echo "Task $PARAM_ID complete!"
"""
    with open(sbatch_array_path, "w") as f:
        f.write(array_content)

    print(f"Generated Slurm Job Array script: {sbatch_array_path}")

    # Generate Master Launcher
    master_sh_path = "execution/submit_hybrid_sweep_master.sh"
    master_content = f"""#!/bin/bash
# Master Submission Script for Hybrid Casimir Levitation Parameter Sweep

mkdir -p logs .tmp sweep_configs

echo "Submitting Slurm Job Array for 180 Parameter Sweep Tasks..."
JOB_ID=$(sbatch execution/submit_hybrid_sweep_array.sbatch | awk '{{print $4}}')
echo "Submitted Slurm Job Array ID: $JOB_ID"

# Submit Analysis Plot Job with dependency on array completion
sbatch -A r01540 --dependency=afterok:$JOB_ID --job-name=hybrid_sweep_analysis --partition=general --nodes=1 --ntasks-per-node=128 --time=02:00:00 --output=logs/sweep_analysis_%j.log --wrap="cd /N/project/gorengor_werewolf/FractalCasimir3D && source ~/miniconda3/etc/profile.d/conda.sh && conda activate meep && $CONDA_PREFIX/bin/python execution/run_hybrid_sweep_analyzer.py"

echo "All jobs submitted cleanly! Dependencies set for automated analysis."
"""
    with open(master_sh_path, "w") as f:
        f.write(master_content)

    print(f"Generated Master Launcher: {master_sh_path}")
    print("Done!")

if __name__ == "__main__":
    main()
