#!/bin/bash
#SBATCH -J casimir_p1_baselines
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=04:00:00
#SBATCH --array=1-28%14
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/casimir_p1_baselines_%A_%a.out
#SBATCH -e .tmp/casimir_p1_baselines_%A_%a.err

echo "================================================================================"
echo "CASIMIR_P1_BASELINES TASK: $SLURM_ARRAY_TASK_ID / 28"
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

module unload xalt 2>/dev/null || true
export XALT_EXECUTABLE_TRACKING=no
export PYTHONUNBUFFERED=1

cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p .tmp

CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_phase1/config_${CFG_INDEX}.json"

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
CORR=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['corrugated'])")
RTIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['r_tip_nm'])")
MED=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['medium'])")
SIEVE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['stepped_sieve'])")

echo "Executing: $LABEL"
echo "Params: d=$D_UM um, N=($NTOP,$NBOT), mat=$MAT, res=$RES, theta=$THETA deg, alpha=$ALPHA deg, r_tip=$RTIP nm, med=$MED"

EXTRA_ARGS=""
if [ "$CORR" = "True" ] || [ "$CORR" = "true" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --corrugated --corrugation-angle $ALPHA --r-tip $RTIP"
fi
if [ "$SIEVE" = "True" ] || [ "$SIEVE" = "true" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --stepped-sieve"
fi
if [ "$MED" != "None" ] && [ "$MED" != "Vacuum" ] && [ -n "$MED" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --medium $MED"
fi

bash execution/run_meep_wrapper.sh $PYTHON_EXEC execution/run_meep_simulation.py \
    --L $L_UM \
    --d $D_UM \
    --N $NTOP \
    --N-bottom $NBOT \
    --theta $THETA \
    --material $MAT \
    --res $RES \
    --eps-bg $EPS \
    --config all \
    $EXTRA_ARGS

EXIT_CODE=$?
echo "Task $SLURM_ARRAY_TASK_ID completed with exit code $EXIT_CODE at $(date)."
exit $EXIT_CODE
