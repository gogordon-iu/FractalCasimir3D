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

# Ensure sweep_configs_sweet_spot exist, or generate them dynamically if missing
if [ ! -d "sweep_configs_sweet_spot" ] || [ ! -f "sweep_configs_sweet_spot/config_001.json" ]; then
    echo "Sweep configs missing, pulling from git..."
    git pull
    if [ ! -d "sweep_configs_sweet_spot" ]; then
        echo "Generating sweep configs dynamically..."
        $PYTHON_EXEC execution/generate_sweet_spot_configs.py
    fi
fi

# Determine Config File Index
CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_sweet_spot/config_${CFG_INDEX}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config file $CONFIG_FILE not found! Generating configs..."
    $PYTHON_EXEC execution/generate_sweet_spot_configs.py
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

srun -n 128 $PYTHON_EXEC execution/run_meep_simulation.py \
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
    --config all

echo "Task $SLURM_ARRAY_TASK_ID complete at $(date)."
