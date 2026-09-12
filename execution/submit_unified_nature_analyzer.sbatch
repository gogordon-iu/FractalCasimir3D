#!/bin/bash
#SBATCH -J casimir_nature_analyzer
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --time=02:00:00
#SBATCH -o .tmp/nature_analyzer_%j.out
#SBATCH -e .tmp/nature_analyzer_%j.err

echo "================================================================================"
echo "UNIFIED NATURE CAMPAIGN POST-SIMULATION ANALYZER"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python"
fi

cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "Executing Unified Nature Analyzer..."
$PYTHON_EXEC execution/run_unified_nature_analyzer.py

echo "Analysis complete at $(date)."
