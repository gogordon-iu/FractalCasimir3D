#!/bin/bash
#SBATCH -J casimir_clutch_analyzer
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --time=01:00:00
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/clutch_analyzer_%j.out
#SBATCH -e .tmp/clutch_analyzer_%j.err

echo "================================================================================"
echo "FRACTAL QUANTUM CLUTCH POST-SIMULATION ANALYZER"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

# Environment Activation (Detect BigRed 200 conda installation)
if [ -f "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python"
    export PATH="/N/u/gogordon/BigRed200/.conda/envs/meep/bin:$PATH"
    export LD_LIBRARY_PATH="/N/u/gogordon/BigRed200/.conda/envs/meep/lib:$LD_LIBRARY_PATH"
elif [ -f "$HOME/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="$HOME/.conda/envs/meep/bin/python"
    export PATH="$HOME/.conda/envs/meep/bin:$PATH"
    export LD_LIBRARY_PATH="$HOME/.conda/envs/meep/lib:$LD_LIBRARY_PATH"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source ~/miniconda3/etc/profile.d/conda.sh
    conda activate meep
    PYTHON_EXEC="$CONDA_PREFIX/bin/python"
else
    PYTHON_EXEC="python"
fi

module unload xalt 2>/dev/null || true
export XALT_EXECUTABLE_TRACKING=no
export PYTHONUNBUFFERED=1
export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH}"

cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "Executing Quantum Clutch Analyzer & Generating Verification Tables/Figures..."
$PYTHON_EXEC execution/run_clutch_analyzer.py

echo "Harvesting logs and pushing final diagnostics to GitHub..."
$PYTHON_EXEC execution/harvest_cluster_diagnostics.py 2>/dev/null || true

echo "Quantum Clutch Analysis complete at $(date)."
