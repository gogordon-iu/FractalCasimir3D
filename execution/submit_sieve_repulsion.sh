#!/bin/bash

# Force execution from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Ensure execution logs directory exists
mkdir -p logs
mkdir -p .tmp

echo "=================================================="
echo "Submitting Frontier 1: 3D Stepped Fractal Sieve Casimir Repulsion Sweep"
echo "Parameters: L = 2.00 um, d = 0.12 um (120 nm), N_top = 3, N_bottom = 3"
echo "Sieve Depths: [0.3, 0.15, 0.05] um, theta = 90.0 deg, R = 40"
echo "=================================================="

JOBS=""

for config in "both" "self"; do
    for seg in {0..17}; do
        sbatch_file="execution/submit_sieve_L_2.00_d_0.12_Ntop_3_Nbot_3_${config}_seg_${seg}.sbatch"
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
plot_sbatch="execution/submit_sieve_L_2.00_d_0.12_plot.sbatch"
if [ -f "$plot_sbatch" ]; then
    PLOT_JOB_ID=$(sbatch --dependency=afterany:${JOBS} --parsable "$plot_sbatch")
    echo "Submitted plot job ${plot_sbatch} -> Job ID: ${PLOT_JOB_ID}"
fi
echo "=================================================="
echo "Submission complete. Monitor status with: squeue -u gogordon"
echo "=================================================="
