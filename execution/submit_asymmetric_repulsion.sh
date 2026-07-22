#!/bin/bash

# Force execution from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Ensure execution logs directory exists
mkdir -p logs
mkdir -p .tmp

echo "=================================================="
echo "Submitting Asymmetric Dual-Fractal Casimir Repulsion Sweep"
echo "Parameters: L = 2.0 um, d = 0.25 um (250 nm), N_top = 3, N_bottom = 2"
echo "=================================================="

# Initialize job dependency string
JOBS=""

L="2.00"
d="0.25"
Ntop="3"
Nbot="2"

for config in "both" "self"; do
    for seg in {0..17}; do
        sbatch_file="execution/submit_asym_L_${L}_d_${d}_Ntop_${Ntop}_Nbot_${Nbot}_${config}_seg_${seg}.sbatch"
        if [ -f "$sbatch_file" ]; then
            JOB_ID=$(sbatch --parsable "$sbatch_file")
            echo "Submitted ${sbatch_file} -> Job ID: ${JOB_ID}"
            if [ -z "$JOBS" ]; then
                JOBS="$JOB_ID"
            else
                JOBS="$JOBS:$JOB_ID"
            fi
        else
            echo "Warning: ${sbatch_file} not found!"
        fi
    done
done

echo "--------------------------------------------------"
echo "Submitting final compilation/analysis job with dependency --dependency=afterany:${JOBS}"
plot_sbatch="execution/submit_asym_L_${L}_d_${d}_plot.sbatch"
if [ -f "$plot_sbatch" ]; then
    PLOT_JOB_ID=$(sbatch --dependency=afterany:${JOBS} --parsable "$plot_sbatch")
    echo "Submitted plot job ${plot_sbatch} -> Job ID: ${PLOT_JOB_ID}"
fi
echo "=================================================="
echo "Submission complete. Monitor status with: squeue -u gogordon"
echo "=================================================="
