#!/bin/bash
#SBATCH -J sieve_L_2.00_d_0.12_plot
#SBATCH -A r01540
#SBATCH -o logs/sieve_L_2.00_d_0.12_plot_%j.out
#SBATCH -e logs/sieve_L_2.00_d_0.12_plot_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
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

echo "Starting Frontier 1 3D Stepped Sieve compilation and analysis..."
$CONDA_PREFIX/bin/python execution/run_sieve_sweep.py --cores 128 --L 2.00 --d 0.12 --N-top 3 --N-bottom 3
echo "Compilation and analysis complete."
