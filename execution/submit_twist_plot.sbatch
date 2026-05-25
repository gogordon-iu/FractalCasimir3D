#!/bin/bash
#SBATCH -J casimir_twist_plot
#SBATCH -o logs/twist_plot.out
#SBATCH -e logs/twist_plot.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "Starting Phosphorene twist plotting..."
# Execute the consolidation and plotting script
python execution/run_twist_sweep.py
echo "Plotting complete."
