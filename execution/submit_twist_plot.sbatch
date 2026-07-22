#!/bin/bash
#SBATCH -J casimir_twist_plot
#SBATCH -A r01540
#SBATCH -o logs/twist_plot_%j.out
#SBATCH -e logs/twist_plot_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=96:00:00
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


# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1
export OMP_NUM_THREADS=1

echo "Starting Phosphorene twist plotting..."
# Execute the consolidation and plotting script
python execution/run_twist_sweep.py --cores 128
echo "Plotting complete."
