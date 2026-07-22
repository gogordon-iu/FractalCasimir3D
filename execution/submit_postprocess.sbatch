#!/bin/bash
#SBATCH -J casimir_postprocess
#SBATCH -A r01540
#SBATCH -o logs/postprocess_%j.out
#SBATCH -e logs/postprocess_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
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

echo "Starting post-processing with parameters: nsteps=$1, res=$2, nmax=$3"
# Run the PFA analytical model baseline calculations first
python execution/run_pfa_model.py
# Run the post-processing and plotting script
python execution/postprocess_and_plot.py --nsteps "$1" --res "$2" --nmax "$3"
echo "Post-processing complete. Figures and dataset generated."
