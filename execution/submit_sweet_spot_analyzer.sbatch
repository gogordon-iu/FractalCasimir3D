#!/bin/bash
#SBATCH -J sweet_spot_analysis
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=02:00:00
#SBATCH -o .tmp/sweet_spot_analysis_%j.out
#SBATCH -e .tmp/sweet_spot_analysis_%j.err

echo "=================================================="
echo "RUNNING SWEET SPOT PARAMETER SWEEP ANALYZER"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep

python execution/run_sweet_spot_analyzer.py

echo "Analysis complete."
