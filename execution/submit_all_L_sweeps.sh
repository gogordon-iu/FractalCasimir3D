#!/bin/bash

# Force execution from repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Clear old cached twist files to prevent any carry-over from failed jobs
rm -f .tmp/meep_*_theta_*.json

echo "Submitting all parallel L-scaling twist sweep jobs to Slurm..."

for L in 0.3 0.4 0.5 0.6; do
    job_ids=()
    echo "----------------------------------------"
    echo "Submitting jobs for L = ${L} um"
    
    for suffix in std_both std_self tuned_both tuned_self; do
        out=$(sbatch execution/submit_twist_L_${L}_${suffix}.sbatch)
        job_id=$(echo "$out" | awk '{print $4}')
        job_ids+=("$job_id")
        echo "Submitted L=${L} config=${suffix} -> Job ID: ${job_id}"
    done
    
    dependency_string=$(IFS=:; echo "${job_ids[*]}")
    echo "Scheduling plot job with dependency --dependency=afterany:${dependency_string}"
    sbatch --dependency=afterany:${dependency_string} execution/submit_twist_L_${L}_plot.sbatch
done

echo "----------------------------------------"
echo "All jobs submitted. Monitor using: squeue -u gogordon"
