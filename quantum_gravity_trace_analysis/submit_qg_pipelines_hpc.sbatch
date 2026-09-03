#!/bin/bash
#SBATCH -J qg_casimir_pipelines
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=04:00:00
#SBATCH -o .tmp/qg_pipelines_%j.out
#SBATCH -e .tmp/qg_pipelines_%j.err

echo "=================================================="
echo "RUNNING QUANTUM GRAVITY & STRESS TRACE PIPELINES ON BIGRED 200"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on node: $(hostname)"
echo "Start time: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p .tmp quantum_gravity_trace_analysis/figures

python quantum_gravity_trace_analysis/run_all_quantum_gravity_pipelines.py

echo "=================================================="
echo "All Quantum Gravity Pipelines completed at $(date)."
echo "=================================================="
