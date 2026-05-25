#!/bin/bash
#SBATCH -J casimir_sweep
#SBATCH -o logs/casimir_%a.out
#SBATCH -e logs/casimir_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --time=04:00:00
#SBATCH --array=0-599   # 3 materials * 4 generations * 50 separation steps = 600 tasks
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Create logs and cache directories
mkdir -p logs
mkdir -p .tmp

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads for MEEP's C++ solver
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

echo "Running task ID: $SLURM_ARRAY_TASK_ID"
echo "CPUs allocated: $SLURM_CPUS_PER_TASK"

# Run the task mapping script
# Customize resolution (--res) and separations (--nsteps) here
# - res=40 provides double the current resolution (grid volume size reduction of 8x)
# - nsteps=50 provides a fine-grained sweep of 50 steps along the separation axis
srun python execution/run_slurm_array_task.py \
    --task-id $SLURM_ARRAY_TASK_ID \
    --nsteps 50 \
    --res 40 \
    --nmax 5
