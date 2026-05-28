#!/bin/bash
#SBATCH -J casimir_twist_sweep
#SBATCH -A r01540
#SBATCH -o logs/twist_%a.out
#SBATCH -e logs/twist_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=12
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --array=0-6   # 7 angles: 0, 15, 30, 45, 60, 75, 90
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Define angles
THETAS=(0.0 15.0 30.0 45.0 60.0 75.0 90.0)
THETA=${THETAS[$SLURM_ARRAY_TASK_ID]}

# Create logs and cache directories
mkdir -p logs
mkdir -p .tmp

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Queue the plot job automatically once all array tasks finish
if [ "$SLURM_ARRAY_TASK_ID" -eq 0 ]; then
    sbatch --dependency=afterany:$SLURM_ARRAY_JOB_ID execution/submit_twist_plot.sbatch
fi

# Set OpenMP threads to 1 for parallel MPI execution
export OMP_NUM_THREADS=1

echo "Running task ID: $SLURM_ARRAY_TASK_ID (theta = $THETA deg)"

# Run both cases (both plates present, and self-force subtraction)
srun -n 12 python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 3 \
    --material Phosphorene \
    --res 40 \
    --nmax 3 \
    --theta "$THETA" \
    --eps-bg 1.6
