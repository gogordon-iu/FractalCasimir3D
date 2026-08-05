#!/bin/bash
# Master Launcher Script for Sweet Spot Parameter Sweep Array & Automatic Analyzer

echo "=================================================="
echo "LAUNCHING SWEET SPOT 3D FDTD PARAMETER SWEEP ARRAY (224 TASKS)"
echo "=================================================="

mkdir -p .tmp

# Submit Job Array
ARRAY_JOB_OUTPUT=$(sbatch execution/submit_sweet_spot_array.sbatch)
echo "$ARRAY_JOB_OUTPUT"

# Extract Job ID
ARRAY_JOB_ID=$(echo "$ARRAY_JOB_OUTPUT" | awk '{print $4}')

if [ -z "$ARRAY_JOB_ID" ]; then
    echo "ERROR: Failed to submit Slurm job array!"
    exit 1
fi

echo "Submitted Job Array ID: $ARRAY_JOB_ID"

# Submit Dependent Analysis Job
echo "Submitting Dependent Analysis Job (afterok:$ARRAY_JOB_ID)..."
sbatch --dependency=afterok:$ARRAY_JOB_ID execution/submit_sweet_spot_analyzer.sbatch

echo "=================================================="
echo "SUCCESS: Sweet Spot Parameter Sweep Array and Analysis Pipeline Enqueued!"
echo "Check progress using: squeue -u $USER"
echo "=================================================="
