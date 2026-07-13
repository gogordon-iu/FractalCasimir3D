#!/bin/bash
#SBATCH -J twist_L_1.6_plot
#SBATCH -A r01540
#SBATCH -o logs/twist_L_1.6_plot_%j.out
#SBATCH -e logs/twist_L_1.6_plot_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1
export OMP_NUM_THREADS=1

echo "Starting twist sweep L = 1.6 plotting..."
$CONDA_PREFIX/bin/python execution/run_twist_sweep.py --cores 128 --L 1.6
echo "Plotting complete."
