#!/bin/bash
#SBATCH -J sieve_L_2.00_d_0.12_both_seg_15
#SBATCH -A r01540
#SBATCH -o logs/sieve_L_2.00_d_0.12_both_seg_15_%j.out
#SBATCH -e logs/sieve_L_2.00_d_0.12_both_seg_15_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --mail-type=FAIL
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

echo "Starting Frontier 1 3D Stepped Sieve segment: config=both, moments 90 to 96..."
mpirun -np 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --L 2.00 \
    --d 0.12 \
    --N 3 \
    --N-bottom 3 \
    --material Phosphorene_tuned \
    --res 40 \
    --nmax 3 \
    --theta 90.0 \
    --eps-bg 2.1 \
    --T-run 30.0 \
    --config both \
    --moment-start 90 \
    --moment-end 96 \
    --stepped-sieve \
    --sieve-depths 0.3 0.15 0.05

echo "Segment 15 (both) complete."
