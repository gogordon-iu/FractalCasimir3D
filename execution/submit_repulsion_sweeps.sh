#!/bin/bash

# Force execution from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "=================================================="
echo "Submitting segmented FDTD sweeps for L = 2.0 um at res = 40..."
echo "=================================================="

# Initialize job dependency string
JOBS=""

L="2.0"
echo "Submitting jobs for L = $L um (Tuned, 90 deg, segmented):"
for suffix in "tuned_both" "tuned_self"; do
    for seg in {0..9}; do
        sbatch_file="execution/submit_twist_L_${L}_${suffix}_seg_${seg}.sbatch"
        if [ -f "$sbatch_file" ]; then
            JOB_ID=$(sbatch --parsable "$sbatch_file")
            echo "  -> Sbatch: $sbatch_file | Job ID: $JOB_ID"
            if [ -z "$JOBS" ]; then
                JOBS="$JOB_ID"
            else
                JOBS="$JOBS:$JOB_ID"
            fi
        else
            echo "  -> ERROR: File not found: $sbatch_file"
        fi
    done
done

echo "=================================================="
echo "Submitting final sync job with dependency link..."
echo "=================================================="

# Submit the sync job as a dependency on afterany of all 20 simulation segment jobs
if [ -n "$JOBS" ]; then
    JOB_SYNC=$(sbatch --dependency=afterany:$JOBS --parsable execution/submit_sync.sbatch)
    echo "Submitted sync job (dependency: afterany:$JOBS): Job ID $JOB_SYNC"
else
    echo "ERROR: No jobs were submitted. Sync job not queued."
fi

echo "=================================================="
echo "Submission complete. Monitor status with: squeue -u gogordon"
echo "=================================================="
