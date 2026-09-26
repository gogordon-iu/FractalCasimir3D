#!/bin/bash
#SBATCH -J cantor_plot
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/cantor_plot_%j.out
#SBATCH -e .tmp/cantor_plot_%j.err

echo "================================================================================"
echo "SIERPINSKI-CANTOR FOREST POSTPROCESSING & PUBLICATION PLOT"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

# Environment Activation (Detect BigRed 200 conda installation)
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

cd /N/project/gorengor_werewolf/FractalCasimir3D
export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH}"

$PYTHON_EXEC execution/analyze_cantor_forest.py

EXIT_CODE=$?
echo "Analysis completed with exit code $EXIT_CODE at $(date)."

if [ $EXIT_CODE -eq 0 ]; then
    rm -f .git/index.lock 2>/dev/null || true
    git add results_cantor_forest/
    git commit -m "results(cantor_forest): finalize summary JSON, LaTeX tables, and publication figure" || true
    git pull origin main --no-edit -X ours 2>/dev/null || true
    git push origin main 2>/dev/null || true
fi

exit $EXIT_CODE
