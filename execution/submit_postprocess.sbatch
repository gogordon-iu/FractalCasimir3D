#!/bin/bash
#SBATCH -J casimir_postprocess
#SBATCH -o logs/postprocess.out
#SBATCH -e logs/postprocess.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "Starting post-processing with parameters: nsteps=$1, res=$2, nmax=$3"
# Run the PFA analytical model baseline calculations first
python execution/run_pfa_model.py
# Run the post-processing and plotting script
python execution/postprocess_and_plot.py --nsteps "$1" --res "$2" --nmax "$3"
echo "Post-processing complete. Figures and dataset generated."
