#!/bin/bash
# Resubmission Script for Frontier 2 (3D Interlocking Fractal Corrugations)
cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p logs .tmp

L="2.00"
d="0.10"
N_top="3"
N_bot="3"
material="Phosphorene_tuned"
res="40"
theta="90.0"
eps_bg="2.1"
plot_job_name="corrugated_L_${L}_d_${d}_plot"

job_ids=()

for config in "both" "self"; do
    for seg in {0..17}; do
        sbatch_file="execution/submit_corrugated_L_${L}_d_${d}_Ntop_${N_top}_Nbot_${N_bot}_${config}_seg_${seg}.sbatch"
        res=$(sbatch $sbatch_file)
        job_id=$(echo $res | awk '{print $4}')
        job_ids+=($job_id)
        echo "Submitted ${config} seg ${seg}: Job ID $job_id"
    done
done

dep_str=$(IFS=:; echo "${job_ids[*]}")
echo "Submitting compilation plot job dependent on ${#job_ids[@]} segment jobs..."
sbatch --dependency=afterany:$dep_str execution/submit_${plot_job_name}.sbatch

echo "All Frontier 2 simulation segment jobs and plot job successfully queued on BigRed200."
