#!/bin/bash
# Master Slurm Submission Script for Frontier 2: 3D Interlocking Fractal Corrugations

cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p logs .tmp

job_ids=()

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_0.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 0: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_1.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 1: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_2.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 2: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_3.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 3: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_4.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 4: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_5.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 5: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_6.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 6: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_7.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 7: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_8.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 8: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_9.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 9: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_10.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 10: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_11.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 11: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_12.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 12: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_13.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 13: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_14.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 14: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_15.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 15: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_16.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 16: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_17.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted both seg 17: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_0.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 0: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_1.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 1: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_2.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 2: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_3.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 3: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_4.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 4: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_5.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 5: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_6.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 6: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_7.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 7: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_8.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 8: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_9.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 9: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_10.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 10: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_11.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 11: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_12.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 12: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_13.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 13: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_14.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 14: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_15.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 15: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_16.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 16: Job ID $job_id"

res=$(sbatch execution/submit_corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_self_seg_17.sbatch)
job_id=$(echo $res | awk '{print $4}')
job_ids+=($job_id)
echo "Submitted self seg 17: Job ID $job_id"

# Build dependency string: afterany:job1:job2:...
dep_str=$(IFS=:; echo "${job_ids[*]}")

echo "Submitting compilation plot job dependent on ${#job_ids[@]} segment jobs..."
sbatch --dependency=afterany:$dep_str execution/submit_corrugated_L_2.00_d_0.10_plot.sbatch

echo "All Frontier 2 simulation segment jobs and plot job successfully queued on BigRed200."
