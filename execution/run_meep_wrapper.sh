#!/bin/bash
# Crash-Proof Execution Wrapper for 3D FDTD Casimir Simulations

echo "=================================================="
echo "RUNNING CRASH-PROOF MEEP SIMULATION WRAPPER"
echo "=================================================="

SLURM_TASK=${SLURM_ARRAY_TASK_ID:-0}
PYTHON_EXEC=${PYTHON_EXEC:-python}

# Function to handle crash exit
on_exit_failure() {
    EXIT_CODE=$?
    if [ $EXIT_CODE -ne 0 ]; then
        echo "=================================================="
        echo "[CRASH DETECTED] Task $SLURM_TASK exited with status code $EXIT_CODE"
        echo "=================================================="
        
        # Invoke crash_handler.py to log details and push to GitHub
        $PYTHON_EXEC execution/crash_handler.py "$SLURM_TASK" "ExitCode_$EXIT_CODE" "Simulation task failed with exit code $EXIT_CODE. Check .tmp/sweet_spot_${SLURM_ARRAY_JOB_ID:-0}_${SLURM_TASK}.err for details."
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
