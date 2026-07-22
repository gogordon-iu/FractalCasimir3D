#!/bin/bash
#SBATCH -J twist_sweep_sync
#SBATCH -A r01540
#SBATCH -o logs/sync_%j.out
#SBATCH -e logs/sync_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:15:00
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


# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "=================================================="
echo "Starting final sweep compilation and git sync..."
echo "=================================================="

# Run the git sync script to consolidate, plot, and push to GitHub
$CONDA_PREFIX/bin/python execution/sync_results_to_github.py

echo "Sync complete."
