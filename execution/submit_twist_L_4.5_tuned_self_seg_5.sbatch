#!/bin/bash
#SBATCH -J twist_L_4.5_tuned_self_seg_5
#SBATCH -A r01540
#SBATCH -o logs/twist_L_4.5_tuned_self_seg_5_%A_%a.out
#SBATCH -e logs/twist_L_4.5_tuned_self_seg_5_%A_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=17:00:00
#SBATCH --array=6-6
#SBATCH --mail-type=FAIL,END
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

echo "Running Segmented Twist Sweep L = 4.5 (tuned_self) segment 5 task ID: $SLURM_ARRAY_TASK_ID (theta = $THETA deg)"

srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --d 0.1 \
    --N 3 \
    --material Phosphorene_tuned \
    --res 40 \
    --nmax 3 \
    --theta "$THETA" \
    --eps-bg 2.1 \
    --L 4.5 \
    --config self \
    --no-subgroups \
    --moment-start 20 \
    --moment-end 24
