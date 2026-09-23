#!/bin/bash
#SBATCH -J clutch_largemem
#SBATCH -p largemem
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH --mem=350G
#SBATCH --array=2-4,7-9%3
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/clutch_largemem_%A_%a.out
#SBATCH -e .tmp/clutch_largemem_%A_%a.err

echo "================================================================================"
echo "CASIMIR_CLUTCH LARGEMEM TASK: $SLURM_ARRAY_TASK_ID / 10"
echo "Target: Angled Tasks (theta = 30, 45, 60 deg, R = 60, N = 3, RAM > 240 GB)"
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
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")
NMAX=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['nmax'])")
RTIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['r_tip'])")
NTOP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N'])")
NBOT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N_bottom'])")
EPS=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['eps_bg'])")
CLUTCH=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE')).get('clutch', True))")

echo "Executing Quantum Clutch Simulation on High-Memory Node (largemem, 350GB RAM requested)"
echo "Label: $LABEL"
echo "Params: d=$D_UM um, N_top=$NTOP, N_bot=$NBOT, mat=$MAT, res=$RES, nmax=$NMAX, theta=$THETA deg, alpha=$ALPHA deg, r_tip=$RTIP nm, eps=$EPS"

SYNCED=false
sync_and_push() {
    if [ "$SYNCED" = "true" ]; then
        return
    fi
    SYNCED=true
    local code=${1:-$?}
    echo "Synchronizing progress and pushing reports for Task $SLURM_ARRAY_TASK_ID (exit code $code)..."
    mkdir -p cluster_diagnostics/raw_logs
    cp -f .tmp/clutch_largemem_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true

    $PYTHON_EXEC execution/sync_task_progress.py \
        --task-id $SLURM_ARRAY_TASK_ID \
        --label "$LABEL" \
        --exit-code $code || true
}
trap 'sync_and_push $?' EXIT TERM INT

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
    --T-run 12.0 \
    --max-walltime-hours 11.0 \
    --campaign-task-id $SLURM_ARRAY_TASK_ID \
    $EXTRA_ARGS

EXIT_CODE=$?
echo "Clutch Largemem Task $SLURM_ARRAY_TASK_ID ($LABEL) finished with exit code $EXIT_CODE at $(date)."

COMPLETE_FLAG=".tmp/task_${CFG_INDEX}_complete.flag"
PENDING_FLAG=".tmp/task_${CFG_INDEX}_pending.flag"

if [ -f "$COMPLETE_FLAG" ]; then
    echo "================================================================================"
    echo "[TASK COMPLETE] Task $SLURM_ARRAY_TASK_ID ($LABEL) is 100% completed!"
    echo "================================================================================"

    # Check if all 10 tasks in the campaign are complete
    ALL_TASKS_COMPLETE=true
    for tid in {1..10}; do
        t_idx=$(printf "%03d" $tid)
        if [ ! -f ".tmp/task_${t_idx}_complete.flag" ]; then
            ALL_TASKS_COMPLETE=false
            break
        fi
    done

    if [ "$ALL_TASKS_COMPLETE" = "true" ]; then
        echo "================================================================================"
        echo "ALL 10 QUANTUM CLUTCH TASKS ARE 100% COMPLETE!"
        echo "Triggering post-simulation analyzer: sbatch execution/submit_clutch_analyzer.sbatch"
        echo "================================================================================"
        sbatch execution/submit_clutch_analyzer.sbatch || true
    else
        echo "Remaining tasks in progress. Awaiting full campaign completion."
    fi

elif [ -f "$PENDING_FLAG" ]; then
    echo "================================================================================"
    echo "[AUTO-RESUBMIT] Task $SLURM_ARRAY_TASK_ID reached 12-hour limit with pending moments."
    echo "Checkpoints safely preserved. Launching continuation job for Task $SLURM_ARRAY_TASK_ID..."
    echo "================================================================================"
    RESUBMIT_OUT=$(sbatch --array=${SLURM_ARRAY_TASK_ID} execution/submit_clutch_campaign_largemem.sbatch 2>&1) || true
    echo "  Continuity Job Queued: $RESUBMIT_OUT"
else
    echo "Notice: Simulation exited with code $EXIT_CODE. Checking checkpoint status."
fi

sync_and_push $EXIT_CODE

exit 0
