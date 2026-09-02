#!/bin/bash
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH -J nature_t1_conv
#SBATCH --array=1-24%8
#SBATCH -o .tmp/nature_t1_%A_%a.out
#SBATCH -e .tmp/nature_t1_%A_%a.err

echo "=================================================="
echo "NATURE TASK 1: GRID CONVERGENCE & EDGE ROUNDING"
echo "Array Task: $SLURM_ARRAY_TASK_ID / 24 on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task1_config_%03d.json" $SLURM_ARRAY_TASK_ID)
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['resolution'])")
RTIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['r_tip_nm'])")
DS=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['delta_s_nm'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_um'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['alpha_deg'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['theta_deg'])")

srun -n 128 $PYTHON_EXEC execution/run_rounded_convergence.py \
    --res $RES --r-tip $RTIP --delta-s $DS --d $D_UM --alpha $ALPHA --theta $THETA --outdir results_nature_validation

echo "Completed Task 1 at $(date)"
