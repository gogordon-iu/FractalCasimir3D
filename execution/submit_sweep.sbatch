#!/bin/bash
#SBATCH -J casimir_sweep
#SBATCH -o logs/casimir_%a.out
#SBATCH -e logs/casimir_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=12
#SBATCH --time=48:00:00
#SBATCH --array=0-599   # 3 materials * 4 generations * 50 separation steps = 600 tasks
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Define sweep parameters
NSTEPS=50
RESOLUTION=80
NMAX=5

# Create logs and cache directories
mkdir -p logs
mkdir -p .tmp

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Queue the post-processing job automatically once all array tasks finish (success or failure)
if [ "$SLURM_ARRAY_TASK_ID" -eq 0 ]; then
    sbatch --dependency=afterany:$SLURM_ARRAY_JOB_ID execution/submit_postprocess.sbatch $NSTEPS $RESOLUTION $NMAX
fi

# Set OpenMP threads for MEEP's C++ solver
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

echo "Running task ID: $SLURM_ARRAY_TASK_ID"
echo "CPUs allocated: $SLURM_CPUS_PER_TASK"

# Run the task mapping script
python execution/run_slurm_array_task.py \
    --task-id $SLURM_ARRAY_TASK_ID \
    --nsteps $NSTEPS \
    --res $RESOLUTION \
    --nmax $NMAX \
    --cores $SLURM_CPUS_PER_TASK
