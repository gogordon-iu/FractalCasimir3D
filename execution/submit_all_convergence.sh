#!/bin/bash

# Submit all 12 convergence jobs and capture their Job IDs
job_ids=()

for res in 20 40 60 80 100 120; do
    for config in both self; do
        out=$(sbatch execution/submit_conv_res${res}_${config}.sbatch)
        # Extract job ID: Submitted batch job 123456
        job_id=$(echo "$out" | awk '{print $4}')
        job_ids+=("$job_id")
        echo "Submitted res=${res} config=${config} -> Job ID: ${job_id}"
    done
done

# Build the dependency string (colon-separated list of job IDs)
dependency_string=$(IFS=:; echo "${job_ids[*]}")

echo "Submitting plot job with dependency on all convergence array tasks..."
sbatch --dependency=afterany:${dependency_string} execution/submit_convergence_plot.sbatch
