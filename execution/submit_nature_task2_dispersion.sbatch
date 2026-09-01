#!/bin/bash
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH -J nature_t2_disp
#SBATCH --array=1-216%12
#SBATCH -o .tmp/nature_t2_%A_%a.out
#SBATCH -e .tmp/nature_t2_%A_%a.err

echo "=================================================="
echo "NATURE TASK 2: ANISOTROPIC DISPERSIVE LOSS"
echo "Array Task: $SLURM_ARRAY_TASK_ID / 216 on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task2_config_%03d.json" $SLURM_ARRAY_TASK_ID)
MAT_TOP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['material_top'])")
MAT_BOT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['material_bot'])")
MED=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['medium'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['theta_deg'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['alpha_deg'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_um'])")

$PYTHON_EXEC execution/run_anisotropic_dispersive_lifshitz.py \
    --material-top $MAT_TOP --material-bot $MAT_BOT --medium $MED --theta $THETA --alpha $ALPHA --d $D_UM --outdir results_nature_validation

echo "Completed Task 2 at $(date)"
