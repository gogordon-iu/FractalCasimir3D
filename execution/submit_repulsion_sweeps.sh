#!/bin/bash

# Force execution from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "=================================================="
echo "Submitting all FDTD sweeps for L = 0.8, 1.0, 1.2, 1.4 um..."
echo "=================================================="

# Initialize job dependency string
JOBS=""

for L in "0.8" "1.0" "1.2" "1.4" "1.6" "1.8" "2.0"; do
    echo "Submitting jobs for L = $L um:"
    for suffix in "tuned_both" "tuned_self"; do
        sbatch_file="execution/submit_twist_L_${L}_${suffix}.sbatch"
        if [ -f "$sbatch_file" ]; then
            JOB_ID=$(sbatch --parsable "$sbatch_file")
            echo "  -> Sbatch: $sbatch_file | Job ID: $JOB_ID"
            if [ -z "$JOBS" ]; then
                JOBS="$JOB_ID"
            else
                JOBS="$JOBS:$JOB_ID"
            fi
        else
            echo "  -> INFO: File not found (skipping): $sbatch_file"
        fi
    done
done

echo "=================================================="
echo "Submitting final sync job with dependency link..."
echo "=================================================="

# Submit the sync job as a dependency on afterany of all 16 simulation array jobs
if [ -n "$JOBS" ]; then
    JOB_SYNC=$(sbatch --dependency=afterany:$JOBS --parsable execution/submit_sync.sbatch)
    echo "Submitted sync job (dependency: afterany:$JOBS): Job ID $JOB_SYNC"
else
    echo "ERROR: No jobs were submitted. Sync job not queued."
fi

echo "=================================================="
echo "Submission complete. Monitor status with: squeue -u gogordon"
echo "=================================================="
