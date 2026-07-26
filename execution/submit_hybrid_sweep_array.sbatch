#!/bin/bash
#SBATCH --job-name=hybrid_casimir_sweep
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=08:00:00
#SBATCH --array=1-180%10
#SBATCH --output=logs/sweep_task_%A_%a.log
#SBATCH --error=logs/sweep_task_%A_%a.err

module load meep/1.25.0
module load python/3.10.8

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
ALPHA=$(python -c "import json; print(json.load(open('$CONFIG_FILE'))['alpha'])")
THETA=$(python -c "import json; print(json.load(open('$CONFIG_FILE'))['theta'])")
D_UM=$(python -c "import json; print(json.load(open('$CONFIG_FILE'))['d'])")

echo "Parameters: alpha=${ALPHA} deg, theta=${THETA} deg, d=${D_UM} um"

# Execute simulation for both and self configurations
python execution/run_meep_simulation.py \
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
