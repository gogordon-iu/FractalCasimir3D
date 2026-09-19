#!/bin/bash
# Crash-Proof Execution Wrapper for 3D FDTD Casimir Simulations

echo "=================================================="
echo "RUNNING CRASH-PROOF MEEP SIMULATION WRAPPER"
echo "=================================================="

SLURM_TASK=${SLURM_ARRAY_TASK_ID:-0}
PYTHON_EXEC=${PYTHON_EXEC:-python}
export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH}"

# Function to handle crash exit
on_exit_failure() {
    EXIT_CODE=$?
    if [ $EXIT_CODE -ne 0 ]; then
        echo "=================================================="
        echo "[CRASH DETECTED] Task $SLURM_TASK exited with status code $EXIT_CODE"
        echo "=================================================="
        
        mkdir -p cluster_diagnostics/raw_logs
        cp -f .tmp/*_${SLURM_ARRAY_JOB_ID:-0}_${SLURM_TASK}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true
        cp -f .tmp/casimir_clutch_*_${SLURM_TASK}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true
        
        # Invoke crash_handler.py to log details and push to GitHub
        $PYTHON_EXEC execution/crash_handler.py "$SLURM_TASK" "ExitCode_$EXIT_CODE" "Simulation task failed with exit code $EXIT_CODE. Check cluster_diagnostics/raw_logs/ for mirrored logs."
    fi
}

# Trap exit signals
trap on_exit_failure EXIT

# Execute main simulation command passed as arguments
echo "Executing: $@"
"$@"
CMD_STATUS=$?

if [ $CMD_STATUS -ne 0 ]; then
    echo "Command failed with exit status $CMD_STATUS."
    exit $CMD_STATUS
else
    echo "Command succeeded cleanly."
    trap - EXIT
    exit 0
fi
