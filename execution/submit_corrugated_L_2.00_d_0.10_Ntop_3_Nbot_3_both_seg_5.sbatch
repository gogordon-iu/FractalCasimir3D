#!/bin/bash
#SBATCH -J corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_5
#SBATCH -A r01540
#SBATCH -o logs/corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_5_%j.out
#SBATCH -e logs/corrugated_L_2.00_d_0.10_Ntop_3_Nbot_3_both_seg_5_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=08:00:00
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=gogordon@iu.edu

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

echo "Starting Frontier 2 3D Corrugated segment: config=both, moments 30 to 36..."
$CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --L 2.00 \
    --d 0.10 \
    --N 3 \
    --N-bottom 3 \
    --material Phosphorene_tuned \
    --res 40 \
    --nmax 3 \
    --theta 91.1 \
    --eps-bg 2.1 \
    --T-run 30.0 \
    --config both \
    --moment-start 30 \
    --moment-end 36 \
    --corrugated \
    --corrugation-angle 60.0

echo "Completed Frontier 2 segment: config=both, moments 30 to 36."
