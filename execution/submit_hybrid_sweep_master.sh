#!/bin/bash
# Master Submission Script for 24-Hour Hybrid Casimir Levitation Parameter Sweep

mkdir -p logs .tmp sweep_configs

echo "Submitting Slurm Job Array for 240 Parameter Sweep Tasks..."
JOB_ID=$(sbatch execution/submit_hybrid_sweep_array.sbatch | awk '{print $4}')
echo "Submitted Slurm Job Array ID: $JOB_ID"

# Submit Analysis Plot Job with dependency on array completion
sbatch -A r01540 --dependency=afterok:$JOB_ID --job-name=hybrid_sweep_analysis --partition=general --nodes=1 --ntasks-per-node=128 --time=02:00:00 --output=logs/sweep_analysis_%j.log --wrap="cd /N/project/gorengor_werewolf/FractalCasimir3D && source ~/miniconda3/etc/profile.d/conda.sh && conda activate meep && $CONDA_PREFIX/bin/python execution/run_hybrid_sweep_analyzer.py"

echo "All jobs submitted cleanly! Dependencies set for automated analysis."
