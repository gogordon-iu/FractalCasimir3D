#!/bin/bash
#SBATCH -J cantor_forest
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=08:00:00
#SBATCH --array=1-8%2
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/cantor_forest_%A_%a.out
#SBATCH -e .tmp/cantor_forest_%A_%a.err

echo "================================================================================"
echo "SIERPINSKI-CANTOR FOREST CASIMIR REPULSION: TASK $SLURM_ARRAY_TASK_ID / 8"
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
mkdir -p .tmp cluster_diagnostics/raw_logs results_cantor_forest

CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_cantor_forest/config_${CFG_INDEX}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file $CONFIG_FILE not found!"
    exit 1
fi

N_FRACTAL=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N_fractal'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['theta_deg'])")
L_CELL=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['L_fractal_um'])")
W1_APERTURE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['W1_aperture_um'])")
W1_PILLAR=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['w1_pillar_um'])")
H_PILLAR=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['H_pillar_um'])")
T_PLATE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['t_plate_um'])")
Z_TIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['z_tip_um'])")
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['resolution'])")
NMAX=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['nmax'])")
T_RUN=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['T_run'])")

echo "Configuration $CONFIG_FILE loaded:"
echo "  Generation N: ${N_FRACTAL}, Rotation theta: ${THETA} deg"
echo "  Cell span L: ${L_CELL} um, W1 aperture: ${W1_APERTURE} um, w1 pillar: ${W1_PILLAR} um, H: ${H_PILLAR} um"
echo "  Stator thickness t: ${T_PLATE} um, Tip clearance z_tip: ${Z_TIP} um"
echo "  Material: $MAT, Resolution: $RES, T_run: $T_RUN"
echo "================================================================================"

bash execution/run_meep_wrapper.sh srun -n 128 $PYTHON_EXEC execution/run_cantor_forest_meep.py \
    --task-id $SLURM_ARRAY_TASK_ID \
    --N-fractal $N_FRACTAL \
    --theta $THETA \
    --L-cell $L_CELL \
    --W1-aperture $W1_APERTURE \
    --w1-pillar $W1_PILLAR \
    --H-pillar $H_PILLAR \
    --t-plate $T_PLATE \
    --z-tip $Z_TIP \
    --material $MAT \
    --res $RES \
    --nmax $NMAX \
    --config all \
    --T-run $T_RUN \
    --max-walltime-hours 7.5

EXIT_CODE=$?
echo "Task $SLURM_ARRAY_TASK_ID finished with exit code $EXIT_CODE at $(date)."

# Auto-sync results to GitHub on Rank 0
if [ $EXIT_CODE -eq 0 ]; then
    mkdir -p cluster_diagnostics/raw_logs
    cp -f .tmp/cantor_forest_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.* cluster_diagnostics/raw_logs/ 2>/dev/null || true
    
    rm -f .git/index.lock 2>/dev/null || true
    git add results_cantor_forest/ cluster_diagnostics/raw_logs/
    git commit -m "progress(cantor_forest): Task $SLURM_ARRAY_TASK_ID (N=$N_FRACTAL, theta=${THETA}deg) COMPLETE" || true
    git pull origin main --no-edit -X ours 2>/dev/null || true
    git push origin main 2>/dev/null || true
fi

exit $EXIT_CODE
