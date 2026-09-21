#!/bin/bash
#SBATCH -J clutch_conv_nmax3
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/clutch_conv_nmax3_%j.out
#SBATCH -e .tmp/clutch_conv_nmax3_%j.err

echo "================================================================================"
echo "QUANTUM CLUTCH: MOMENT MULTIPOLE CONVERGENCE VERIFICATION (n_max = 3)"
echo "Target: Task 1 (d = 40 nm, theta = 0.0 deg, R = 60, N = 3, Gold, L = 2.0 um)"
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
mkdir -p .tmp cluster_diagnostics/raw_logs results_clutch

SYNCED=false
sync_and_push() {
    if [ "$SYNCED" = "true" ]; then
        return
    fi
    SYNCED=true
    local code=${1:-$?}
    echo "Synchronizing progress and pushing reports for Convergence Task 999 (exit code $code)..."
    mkdir -p cluster_diagnostics/raw_logs
    cp -f .tmp/clutch_conv_nmax3_${SLURM_JOB_ID}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true

    $PYTHON_EXEC execution/sync_task_progress.py \
        --task-id 999 \
        --label "Clutch_Conv_nmax3_th_0.0" \
        --exit-code $code || true
}
trap 'sync_and_push $?' EXIT TERM INT

echo "Executing Quantum Clutch n_max=3 Convergence Simulation (216 FDTD moments)..."
bash execution/run_meep_wrapper.sh srun -n 128 $PYTHON_EXEC execution/run_meep_simulation.py \
    --L 2.0 \
    --d 0.04 \
    --N 3 \
    --N-bottom 3 \
    --theta 0.0 \
    --material Gold \
    --res 60 \
    --nmax 3 \
    --eps-bg 1.0 \
    --config all \
    --no-subgroups \
    --T-run 12.0 \
    --max-walltime-hours 11.0 \
    --campaign-task-id 999 \
    --clutch \
    --corrugation-angle 75.0 \
    --r-tip 5.0

EXIT_CODE=$?
echo "Convergence test finished with exit code $EXIT_CODE at $(date)."

sync_and_push $EXIT_CODE

COMPLETE_FLAG=".tmp/task_999_complete.flag"
PENDING_FLAG=".tmp/task_999_pending.flag"

if [ -f "$COMPLETE_FLAG" ]; then
    echo "================================================================================"
    echo "[CONVERGENCE COMPLETE] Task 1 with n_max=3 (216 moments) is 100% completed!"
    echo "Running Moment Convergence Analyzer: execution/analyze_moment_convergence.py"
    echo "================================================================================"
    $PYTHON_EXEC execution/analyze_moment_convergence.py || true
elif [ -f "$PENDING_FLAG" ]; then
    echo "================================================================================"
    echo "[AUTO-RESUBMIT] Convergence run reached 12-hour limit with pending moments."
    echo "Checkpoints safely preserved. Launching continuation job for n_max=3 test..."
    echo "================================================================================"
    RESUBMIT_OUT=$(sbatch execution/submit_clutch_convergence_nmax3.sbatch)
    echo "  Continuity Job Queued: $RESUBMIT_OUT"
else
    echo "Notice: Simulation exited with code $EXIT_CODE."
fi

exit 0
