#!/bin/bash
#SBATCH -J submit_missing_tasks
#SBATCH -A r01540
#SBATCH -o logs/missing_tasks_%j.out
#SBATCH -e logs/missing_tasks_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
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

echo "=================================================="
echo "Starting execution of 3 missing FDTD configurations..."
echo "=================================================="

# 1. Run the single missing L=0.5 task
echo "Running L=0.5 Phosphorene config_self..."
srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 3 \
    --material Phosphorene \
    --res 40 \
    --nmax 3 \
    --theta 90.0 \
    --eps-bg 2.4 \
    --L 0.5 \
    --config self \
    --no-subgroups

# 2. Run the two missing L=0.6 tasks
echo "Running L=0.6 Phosphorene_tuned config_both..."
srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 3 \
    --material Phosphorene_tuned \
    --res 40 \
    --nmax 3 \
    --theta 45.0 \
    --eps-bg 2.1 \
    --L 0.6 \
    --config both \
    --no-subgroups

echo "Running L=0.6 Phosphorene_tuned config_self..."
srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 3 \
    --material Phosphorene_tuned \
    --res 40 \
    --nmax 3 \
    --theta 90.0 \
    --eps-bg 2.1 \
    --L 0.6 \
    --config self \
    --no-subgroups

echo "=================================================="
echo "All missing simulations complete. Running sync..."
echo "=================================================="

# Run the git sync script to consolidate, plot, and push to GitHub
$CONDA_PREFIX/bin/python execution/sync_results_to_github.py

echo "Sync complete."
