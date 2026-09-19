#!/bin/bash
#SBATCH -J casimir_clutch
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=24:00:00
#SBATCH --array=1-10%5
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/casimir_clutch_%A_%a.out
#SBATCH -e .tmp/casimir_clutch_%A_%a.err

echo "================================================================================"
echo "CASIMIR_CLUTCH TASK: $SLURM_ARRAY_TASK_ID / 10"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

# Environment Activation (Detect BigRed 200 conda installation)
if [ -f "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python"
    export PATH="/N/u/gogordon/BigRed200/.conda/envs/meep/bin:$PATH"
    export LD_LIBRARY_PATH="/N/u/gogordon/BigRed200/.conda/envs/meep/lib:$LD_LIBRARY_PATH"
elif [ -f "$HOME/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="$HOME/.conda/envs/meep/bin/python"
    export PATH="$HOME/.conda/envs/meep/bin:$PATH"
    export LD_LIBRARY_PATH="$HOME/.conda/envs/meep/lib:$LD_LIBRARY_PATH"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source ~/miniconda3/etc/profile.d/conda.sh
    conda activate meep
    PYTHON_EXEC="$CONDA_PREFIX/bin/python"
else
    PYTHON_EXEC="python"
fi
export PYTHON_EXEC

module unload xalt 2>/dev/null || true
export XALT_EXECUTABLE_TRACKING=no
export PYTHONUNBUFFERED=1
export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH}"

cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p .tmp

CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_clutch/config_${CFG_INDEX}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file $CONFIG_FILE not found!"
    exit 1
fi

echo "Reading task parameters from $CONFIG_FILE..."
LABEL=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['label'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['corrugation_angle'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['theta'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['d'])")
L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['L'])")
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['resolution'])")
EPS=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['eps_bg'])")
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")
NTOP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N_top'])")
NBOT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N_bot'])")
RTIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['r_tip_nm'])")
NMAX=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE')).get('nmax', 3))")
CLUTCH=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE')).get('clutch', True))")

echo "Executing Quantum Clutch Simulation"
echo "Label: $LABEL"
echo "Params: d=$D_UM um, N_top=$NTOP, N_bot=$NBOT, mat=$MAT, res=$RES, nmax=$NMAX, theta=$THETA deg, alpha=$ALPHA deg, r_tip=$RTIP nm, eps=$EPS"

EXTRA_ARGS=""
if [ "$CLUTCH" = "True" ] || [ "$CLUTCH" = "true" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --clutch --corrugation-angle $ALPHA --r-tip $RTIP"
fi

bash execution/run_meep_wrapper.sh srun -n 128 $PYTHON_EXEC execution/run_meep_simulation.py \
    --L $L_UM \
    --d $D_UM \
    --N $NTOP \
    --N-bottom $NBOT \
    --theta $THETA \
    --material $MAT \
    --res $RES \
    --nmax $NMAX \
    --eps-bg $EPS \
    --config all \
    --no-subgroups \
    $EXTRA_ARGS

EXIT_CODE=$?
echo "Clutch Task $SLURM_ARRAY_TASK_ID ($LABEL) completed with exit code $EXIT_CODE at $(date)."

mkdir -p cluster_diagnostics/raw_logs
cp -f .tmp/casimir_clutch_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true

exit $EXIT_CODE
