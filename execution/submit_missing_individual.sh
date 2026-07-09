#!/bin/bash

# Force execution from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "=================================================="
echo "Submitting 3 missing FDTD array tasks individually..."
echo "=================================================="

# 1. Submit L=0.5 Standard Self, task index 6 (theta = 90)
JOB_1=$(sbatch --array=6-6 --parsable execution/submit_twist_L_0.5_std_self.sbatch)
echo "Submitted L=0.5 Phosphorene standard self (theta=90.0): Job ID $JOB_1"

# 2. Submit L=0.6 Tuned Both, task index 3 (theta = 45)
JOB_2=$(sbatch --array=3-3 --parsable execution/submit_twist_L_0.6_tuned_both.sbatch)
echo "Submitted L=0.6 Phosphorene_tuned config_both (theta=45.0): Job ID $JOB_2"

# 3. Submit L=0.6 Tuned Self, task index 6 (theta = 90)
JOB_3=$(sbatch --array=6-6 --parsable execution/submit_twist_L_0.6_tuned_self.sbatch)
echo "Submitted L=0.6 Phosphorene_tuned config_self (theta=90.0): Job ID $JOB_3"

echo "=================================================="
echo "Submitting final sync job with dependencies..."
echo "=================================================="

# Submit the sync job as a dependency on afterany of all three simulation jobs
JOB_SYNC=$(sbatch --dependency=afterany:$JOB_1:$JOB_2:$JOB_3 --parsable execution/submit_sync.sbatch)
echo "Submitted sync job (dependency: afterany:$JOB_1:$JOB_2:$JOB_3): Job ID $JOB_SYNC"
echo "=================================================="
echo "Submission complete. Monitor status with: squeue -u gogordon"
echo "=================================================="
