#!/bin/bash
#SBATCH -J casimir_convergence
#SBATCH -A r01540
#SBATCH -o logs/conv_%a.out
#SBATCH -e logs/conv_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=96:00:00
#SBATCH --array=0-5   # 6 resolutions: 20, 40, 60, 80, 100, 120
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Define resolutions
RESOLUTIONS=(20 40 60 80 100 120)
RES=${RESOLUTIONS[$SLURM_ARRAY_TASK_ID]}

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

# Queue the plot job automatically once all array tasks finish
if [ "$SLURM_ARRAY_TASK_ID" -eq 0 ]; then
    sbatch --dependency=afterany:$SLURM_ARRAY_JOB_ID execution/submit_convergence_plot.sbatch
fi

# Set OpenMP threads to 1 for parallel MPI execution
export OMP_NUM_THREADS=1

echo "Running task ID: $SLURM_ARRAY_TASK_ID (resolution = $RES px/um)"

# Run both cases (both plates present, and self-force subtraction)
srun -n 128 python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 2 \
    --material Gold \
    --res "$RES" \
    --nmax 3
