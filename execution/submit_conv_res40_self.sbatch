#!/bin/bash
#SBATCH -J conv_R40_self
#SBATCH -A r01540
#SBATCH -o logs/conv_R40_self_%A_%a.out
#SBATCH -e logs/conv_R40_self_%A_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --array=0-35
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Create logs and cache directories
mkdir -p logs
mkdir -p .tmp

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1 for parallel MPI execution
export OMP_NUM_THREADS=1

echo "Running task ID: $SLURM_ARRAY_TASK_ID (resolution = 40 px/um, config = self)"

srun -n 128 python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 2 \
    --material Gold \
    --res 40 \
    --nmax 1 \
    --T-run 20.0 \
    --config self \
    --task-idx $SLURM_ARRAY_TASK_ID
