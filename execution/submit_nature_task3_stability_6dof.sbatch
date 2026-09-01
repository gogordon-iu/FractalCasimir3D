#!/bin/bash
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH -J nature_t3_stab
#SBATCH --array=1-20%8
#SBATCH -o .tmp/nature_t3_%A_%a.out
#SBATCH -e .tmp/nature_t3_%A_%a.err

echo "=================================================="
echo "NATURE TASK 3: 6-DOF MECHANICAL STIFFNESS MATRIX"
echo "Array Task: $SLURM_ARRAY_TASK_ID / 20 on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task3_config_%03d.json" $SLURM_ARRAY_TASK_ID)
D_EQ=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_eq_um'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['alpha_deg'])")
THETA_Z=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['theta_z_eq'])")
L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['L_um'])")

$PYTHON_EXEC execution/run_6dof_stability_analyzer.py \
    --d-eq $D_EQ --alpha $ALPHA --theta-z $THETA_Z --L $L_UM --outdir results_nature_validation

echo "Completed Task 3 at $(date)"
