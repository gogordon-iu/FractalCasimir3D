#!/bin/bash
#SBATCH -J concentric_ring
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=08:00:00
#SBATCH --array=1-17%3
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/concentric_ring_%A_%a.out
#SBATCH -e .tmp/concentric_ring_%A_%a.err

echo "================================================================================"
echo "CONCENTRIC CANTOR-RING CASIMIR CLUTCH: TASK $SLURM_ARRAY_TASK_ID / 17"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

# Environment Activation (Detect BigRed 200 conda environment)
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
export OMP_NUM_THREADS=1

cd /N/project/gorengor_werewolf/FractalCasimir3D
export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH}"
mkdir -p .tmp cluster_diagnostics/raw_logs results_concentric_ring

CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_concentric_ring/config_${CFG_INDEX}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file $CONFIG_FILE not found! Generating suite..."
    $PYTHON_EXEC execution/generate_concentric_ring_configs.py --res 60
fi

echo "Task details for config $CONFIG_FILE:"
$PYTHON_EXEC -c "import json; d=json.load(open('$CONFIG_FILE')); print(f\"  Arch: {d.get('architecture')}, N={d.get('N_fractal')}, Tracks: {d.get('num_tracks')}, theta={d.get('theta_deg')} deg, z_tip={d.get('z_tip_nm'):.2f} nm, <d>={d.get('d_average_nm')} nm\")"
echo "================================================================================"

# Clear any stale flags before launching
rm -f .tmp/concentric_ring_task_${CFG_INDEX}_complete.flag .tmp/concentric_ring_task_${CFG_INDEX}_pending.flag 2>/dev/null || true

bash execution/run_meep_wrapper.sh srun -n 128 $PYTHON_EXEC execution/run_concentric_ring_meep.py \
    --config-file "$CONFIG_FILE" \
    --task-id $SLURM_ARRAY_TASK_ID \
    --config all \
    --max-walltime-hours 7.2

EXIT_CODE=$?
echo "Task $SLURM_ARRAY_TASK_ID finished with exit code $EXIT_CODE at $(date)."

COMPLETE_FLAG=".tmp/concentric_ring_task_${CFG_INDEX}_complete.flag"
PENDING_FLAG=".tmp/concentric_ring_task_${CFG_INDEX}_pending.flag"

# Auto-sync results to GitHub on Rank 0
if [ $EXIT_CODE -eq 0 ]; then
    mkdir -p cluster_diagnostics/raw_logs
    cp -f .tmp/concentric_ring_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true
    
    if [ -f "$COMPLETE_FLAG" ]; then
        rm -f .git/index.lock 2>/dev/null || true
        git add results_concentric_ring/ cluster_diagnostics/raw_logs/
        git commit -m "progress(concentric_ring): Task $SLURM_ARRAY_TASK_ID COMPLETE" || true
        git pull origin main --no-edit -X ours 2>/dev/null || true
        git push origin main 2>/dev/null || true
    elif [ -f "$PENDING_FLAG" ]; then
        echo "Task $SLURM_ARRAY_TASK_ID paused at walltime guard. Resubmitting follow-up segment..."
        sbatch --array=${SLURM_ARRAY_TASK_ID} execution/submit_concentric_ring.sbatch
    fi
fi

exit $EXIT_CODE
