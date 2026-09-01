#!/bin/bash
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH -J nature_t4_temp
#SBATCH --array=1-60%12
#SBATCH -o .tmp/nature_t4_%A_%a.out
#SBATCH -e .tmp/nature_t4_%A_%a.err

echo "=================================================="
echo "NATURE TASK 4: FINITE-T MATSUBARA SUMMATION & DSI"
echo "Array Task: $SLURM_ARRAY_TASK_ID / 60 on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task4_config_%03d.json" $SLURM_ARRAY_TASK_ID)
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_um'])")
TEMP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['T_K'])")

$PYTHON_EXEC execution/run_thermal_matsubara_dsi.py \
    --d $D_UM --T $TEMP --outdir results_nature_validation

echo "Completed Task 4 at $(date)"
