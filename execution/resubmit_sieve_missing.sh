#!/bin/bash

# Force execution from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

L="2.00"
d="0.12"
Ntop="3"
Nbot="3"

JOBS=""
echo "Checking for missing segment cache files for Frontier 1: 3D Stepped Sieve..."

for config in "both" "self"; do
    for seg in {0..17}; do
        m_start=$((seg * 6))
        m_end=$(((seg + 1) * 6))
        cache_file=".tmp/meep_d_0.1200_N_3_sieve_Nbot_3_Phosphorene_tuned_res_40_theta_90.0_eps_2.1_L_2.00_config_${config}_moments_${m_start}_${m_end}.json"
        
        if [ ! -f "$cache_file" ]; then
            sbatch_file="execution/submit_sieve_L_${L}_d_${d}_Ntop_${Ntop}_Nbot_${Nbot}_${config}_seg_${seg}.sbatch"
            if [ -f "$sbatch_file" ]; then
                JOB_ID=$(sbatch --parsable "$sbatch_file")
                echo "Resubmitting missing segment ${seg} (${config}): ${sbatch_file} -> Job ID: ${JOB_ID}"
                if [ -z "$JOBS" ]; then
                    JOBS="$JOB_ID"
                else
                    JOBS="$JOBS:$JOB_ID"
                fi
            fi
        fi
    done
done

if [ -n "$JOBS" ]; then
    echo "--------------------------------------------------"
    echo "Submitting compilation plot job with dependency: --dependency=afterany:${JOBS}"
    PLOT_JOB_ID=$(sbatch --dependency=afterany:${JOBS} --parsable "execution/submit_sieve_L_${L}_d_${d}_plot.sbatch")
    echo "Submitted plot job -> Job ID: ${PLOT_JOB_ID}"
else
    echo "--------------------------------------------------"
    echo "All 36 segment files are present! Running plot compilation directly..."
    sbatch "execution/submit_sieve_L_${L}_d_${d}_plot.sbatch"
fi
echo "=================================================="
