#!/bin/bash
#SBATCH -J hybrid_casimir_sweep
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=08:00:00
#SBATCH --array=1-576%10
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
CONFIG_FILE="sweep_configs/config_${PARAM_ID}.json"

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

echo "Parameters: alpha=${ALPHA} deg, theta=${THETA} deg, d=${D_UM} um"

# Execute simulation for both and self configurations
$CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --d $D_UM \
    --N 3 \
    --N-bottom 3 \
    --L 2.0 \
    --material Phosphorene_tuned \
    --res 40 \
    --theta $THETA \
    --eps-bg 2.1 \
    --corrugated \
    --corrugation-angle $ALPHA \
    --config all

echo "Task $PARAM_ID complete!"
