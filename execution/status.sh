#!/bin/bash
# ==============================================================================
# Quick Status & Real-Time Dashboard for BigRed 200 Casimir Runs
# ==============================================================================
# Usage:
#   bash execution/status.sh          # One-shot dashboard
#   bash execution/status.sh -w       # Live refreshing watch mode
#   bash execution/status.sh --tail 3 # View live log of Task 3
# ==============================================================================

cd /N/project/gorengor_werewolf/FractalCasimir3D

# Detect Python interpreter
if [ -f "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python"
elif [ -f "$HOME/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="$HOME/.conda/envs/meep/bin/python"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source ~/miniconda3/etc/profile.d/conda.sh
    conda activate meep
    PYTHON_EXEC="$CONDA_PREFIX/bin/python"
else
    PYTHON_EXEC="python"
fi

$PYTHON_EXEC execution/monitor_all_casimir_runs.py "$@"
