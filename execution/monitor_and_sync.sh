#!/bin/bash
# One-line Monitor & Git Sync Script for BigRed 200

cd /N/project/gorengor_werewolf/FractalCasimir3D

# Activate environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python"
fi

$PYTHON_EXEC execution/monitor_and_sync_report.py
