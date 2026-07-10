#!/bin/bash
#SBATCH -J twist_L_1.2_std_both
#SBATCH -A r01540
#SBATCH -o logs/twist_L_1.2_std_both_%A_%a.out
#SBATCH -e logs/twist_L_1.2_std_both_%A_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=03:00:00
#SBATCH --array=0-6
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Twist angle list
THETAS=(0.0 15.0 30.0 45.0 60.0 75.0 90.0)
THETA=${THETAS[$SLURM_ARRAY_TASK_ID]}

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

echo "Running Twist Sweep L = 1.2 (std_both) task ID: $SLURM_ARRAY_TASK_ID (theta = $THETA deg)"

srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 3 \
    --material Phosphorene \
    --res 40 \
    --nmax 3 \
    --theta "$THETA" \
    --eps-bg 2.4 \
    --L 1.2 \
    --config both \\
    --no-subgroups
