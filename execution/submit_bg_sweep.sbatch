#!/bin/bash
#SBATCH -J casimir_bg_sweep
#SBATCH -A r01540
#SBATCH -o logs/bg_%A_%a.out
#SBATCH -e logs/bg_%A_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --array=0-15  # 2 materials * 8 background values = 16 tasks
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Background permittivity list (matches run_bg_sweep.py)
BG_VALS=(1.5 1.8 2.1 2.4 2.7 3.0 3.3 3.6)

# Calculate material index and background value index from array task ID
MAT_IDX=$((SLURM_ARRAY_TASK_ID / 8))
BG_IDX=$((SLURM_ARRAY_TASK_ID % 8))

# Map indices to parameter values
if [ $MAT_IDX -eq 0 ]; then
    MAT="Phosphorene"
else
    MAT="Phosphorene_tuned"
fi

BG=${BG_VALS[$BG_IDX]}

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
    sbatch --dependency=afterany:$SLURM_ARRAY_JOB_ID execution/submit_bg_plot.sbatch
fi

# Set OpenMP threads to 1 for parallel MPI execution
export OMP_NUM_THREADS=1

echo "Running task ID: $SLURM_ARRAY_TASK_ID (material = $MAT, eps_bg = $BG, theta = 90.0 deg)"

srun -n 128 python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 3 \
    --material "$MAT" \
    --res 40 \
    --nmax 3 \
    --theta 90.0 \
    --eps-bg "$BG"
