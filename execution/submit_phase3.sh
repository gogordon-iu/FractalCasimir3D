#!/bin/bash
# Standalone Launcher for Phase 3 on BigRed 200

echo "================================================================================"
echo "LAUNCHING PHASE 3 ON BIGRED 200"
echo "================================================================================"

mkdir -p .tmp

SUBMIT_OUT=$(sbatch execution/submit_phase3_sweet_spot.sbatch)
echo "$SUBMIT_OUT"

JOB_ID=$(echo "$SUBMIT_OUT" | awk '{print $4}')
if [ -z "$JOB_ID" ]; then
    echo "ERROR: Failed to launch Phase 3!"
    exit 1
fi

echo "Phase 3 Job Array Enqueued: $JOB_ID"
echo "Slurm will email gogordon@iu.edu when Phase 3 finishes."
echo "Check queue with: squeue -u $USER"
echo "================================================================================"
