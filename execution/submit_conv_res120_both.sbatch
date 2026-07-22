#!/bin/bash
#SBATCH -J conv_R120_both
#SBATCH -A r01540
#SBATCH -o logs/conv_R120_both_%A_%a.out
#SBATCH -e logs/conv_R120_both_%A_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --array=0-35
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Exit trap for staging and pushing error logs on failure
_curr_dir=$(dirname "$0")
_exit_handler=""
for i in {1..4}; do
    if [ -f "$_curr_dir/hpc_exit_handler.py" ]; then
        _exit_handler="$_curr_dir/hpc_exit_handler.py"
        break
    fi
    _curr_dir="$_curr_dir/.."
done
if [ -n "$_exit_handler" ]; then
    trap 'if [ $? -ne 0 ]; then python "$_exit_handler" $? "$0"; fi' EXIT
fi


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

echo "Running task ID: $SLURM_ARRAY_TASK_ID (resolution = 120 px/um, config = both)"

srun -n 128 python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 2 \
    --material Gold \
    --res 120 \
    --nmax 1 \
    --T-run 20.0 \
    --config both \
    --task-idx $SLURM_ARRAY_TASK_ID
