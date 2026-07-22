#!/bin/bash
#SBATCH -J asym_L_2.00_d_0.25_Ntop_3_Nbot_2_self_seg_7
#SBATCH -A r01540
#SBATCH -o logs/asym_L_2.00_d_0.25_Ntop_3_Nbot_2_self_seg_7_%j.out
#SBATCH -e logs/asym_L_2.00_d_0.25_Ntop_3_Nbot_2_self_seg_7_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
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

echo "Starting Asymmetric Dual-Fractal Casimir Sweep (self) Segment 7: moments 42 to 48..."
srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \
    --d 0.25 \
    --N 3 \
    --N-bottom 2 \
    --material Phosphorene_tuned \
    --res 40 \
    --nmax 3 \
    --theta 90.0 \
    --eps-bg 2.1 \
    --L 2.0 \
    --config self \
    --moment-start 42 \
    --moment-end 48

echo "Segment 7 complete."
