#!/bin/bash
#SBATCH -J geom_repulse
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=04:00:00
#SBATCH --array=1-4%2
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/geom_repulse_%A_%a.out
#SBATCH -e .tmp/geom_repulse_%A_%a.err

echo "================================================================================"
echo "GEOMETRIC VACUUM CASIMIR REPULSION: TASK $SLURM_ARRAY_TASK_ID / 4"
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
export PYTHON_EXEC

module unload xalt 2>/dev/null || true
export XALT_EXECUTABLE_TRACKING=no
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1

cd /N/project/gorengor_werewolf/FractalCasimir3D
export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH}"
mkdir -p .tmp cluster_diagnostics/raw_logs results_geometric_repulsion

CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_geometric_repulsion/config_${CFG_INDEX}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file $CONFIG_FILE not found!"
    exit 1
fi

W_APERTURE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['W_aperture_um'])")
T_PLATE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['t_plate_um'])")
H_NEEDLE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['H_needle_um'])")
W_NEEDLE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['w_needle_um'])")
Z_TIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['z_tip_um'])")
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['resolution'])")
NMAX=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['nmax'])")

echo "Configuration $CONFIG_FILE loaded:"
echo "  W_aperture: ${W_APERTURE} um, t_plate: ${T_PLATE} um"
echo "  H_needle: ${H_NEEDLE} um, w_needle: ${W_NEEDLE} um"
echo "  z_tip: ${Z_TIP} um (W/4 threshold = $(echo "$W_APERTURE / 4.0" | bc -l) um)"
echo "  Material: $MAT, Resolution: $RES"
echo "================================================================================"

bash execution/run_meep_wrapper.sh srun -n 128 $PYTHON_EXEC execution/run_geometric_repulsion_meep.py \
    --task-id $SLURM_ARRAY_TASK_ID \
    --W-aperture $W_APERTURE \
    --t-plate $T_PLATE \
    --H-needle $H_NEEDLE \
    --w-needle $W_NEEDLE \
    --z-tip $Z_TIP \
    --material $MAT \
    --res $RES \
    --nmax $NMAX \
    --config all \
    --T-run 12.0

EXIT_CODE=$?
echo "Task $SLURM_ARRAY_TASK_ID finished with exit code $EXIT_CODE at $(date)."

# Auto-sync results to GitHub on Rank 0
if [ $EXIT_CODE -eq 0 ]; then
    mkdir -p cluster_diagnostics/raw_logs
    cp -f .tmp/geom_repulse_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true
    
    rm -f .git/index.lock 2>/dev/null || true
    git add results_geometric_repulsion/ cluster_diagnostics/raw_logs/
    git commit -m "progress(repulsion): Task $SLURM_ARRAY_TASK_ID (z_tip=${Z_TIP}um) COMPLETE" || true
    git pull origin main --no-edit -X ours 2>/dev/null || true
    git push origin main 2>/dev/null || true
fi

exit $EXIT_CODE
