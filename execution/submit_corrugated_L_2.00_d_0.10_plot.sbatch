#!/bin/bash
#SBATCH -J corrugated_L_2.00_d_0.10_plot
#SBATCH -A r01540
#SBATCH -o logs/corrugated_L_2.00_d_0.10_plot_%j.out
#SBATCH -e logs/corrugated_L_2.00_d_0.10_plot_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1
export OMP_NUM_THREADS=1

echo "Aggregating Frontier 2 3D Corrugated simulation results for L=2.00 um, d=0.10 um..."
$CONDA_PREFIX/bin/python execution/run_corrugated_sweep.py \
    --L 2.00 \
    --d 0.10 \
    --N 3 \
    --N-bottom 3 \
    --material Phosphorene_tuned \
    --res 40 \
    --theta 91.1 \
    --eps-bg 2.1

echo "Frontier 2 Aggregation complete."
