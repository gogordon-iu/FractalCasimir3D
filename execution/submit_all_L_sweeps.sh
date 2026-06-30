#!/bin/bash

# Force execution from repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "Submitting all L-scaling twist sweep jobs to Slurm..."

sbatch execution/submit_twist_L_0.3.sbatch
sbatch execution/submit_twist_L_0.4.sbatch
sbatch execution/submit_twist_L_0.5.sbatch
sbatch execution/submit_twist_L_0.6.sbatch

echo "All jobs submitted. You can check queue status with: squeue -u gogordon"
