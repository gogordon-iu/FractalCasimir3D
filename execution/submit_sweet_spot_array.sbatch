#!/bin/bash
#SBATCH -J casimir_sweet_spot
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH --array=1-224%8
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/sweet_spot_%A_%a.out
#SBATCH -e .tmp/sweet_spot_%A_%a.err

echo "=================================================="
echo "SLURM ARRAY TASK ID: $SLURM_ARRAY_TASK_ID / 224"
echo "Running on node: $(hostname)"
echo "Start time: $(date)"
echo "=================================================="

# Environment Activation
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python"
fi

cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p .tmp

# Determine Config File Index
CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_sweet_spot/config_${CFG_INDEX}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config file $CONFIG_FILE not found!"
    exit 1
fi

echo "Reading parameters from $CONFIG_FILE..."
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['alpha'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['theta'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['d'])")
L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['L'])")
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['resolution'])")
EPS=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['eps_bg'])")
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")

echo "Executing 3D FDTD Simulation: Alpha=$ALPHA deg, Theta=$THETA deg, d=$D_UM um, L=$L_UM um, Res=$RES..."

bash execution/run_meep_wrapper.sh $PYTHON_EXEC execution/run_meep_simulation.py \
    --L $L_UM \
    --d $D_UM \
    --N 3 \
    --N-bottom 3 \
    --corrugated \
    --corrugation-angle $ALPHA \
    --theta $THETA \
    --material $MAT \
    --res $RES \
    --eps-bg $EPS \
    --config all \
    --task-idx $SLURM_ARRAY_TASK_ID

echo "Task $SLURM_ARRAY_TASK_ID complete at $(date)."
