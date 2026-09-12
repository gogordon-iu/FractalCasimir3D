#!/bin/bash
# Standalone Launcher for Phase 1 on BigRed 200

echo "================================================================================"
echo "LAUNCHING PHASE 1 ON BIGRED 200"
echo "================================================================================"

mkdir -p .tmp

SUBMIT_OUT=$(sbatch execution/submit_phase1_baselines.sbatch)
echo "$SUBMIT_OUT"

JOB_ID=$(echo "$SUBMIT_OUT" | awk '{print $4}')
if [ -z "$JOB_ID" ]; then
    echo "ERROR: Failed to launch Phase 1!"
    exit 1
fi

echo "Phase 1 Job Array Enqueued: $JOB_ID"
echo "Slurm will email gogordon@iu.edu when Phase 1 finishes."
echo "Check queue with: squeue -u $USER"
echo "================================================================================"
