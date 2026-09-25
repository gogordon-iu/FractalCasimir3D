#!/bin/bash
#SBATCH -J casimir_fractal_ctrl
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH --array=1-15%5
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/casimir_fractal_ctrl_%A_%a.out
#SBATCH -e .tmp/casimir_fractal_ctrl_%A_%a.err

echo "================================================================================"
echo "FRACTAL GEOMETRY CONTROL CAMPAIGN - TASK: $SLURM_ARRAY_TASK_ID / 15"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

# Environment Activation (Detect BigRed 200 conda environment)
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
export PYTHONPATH="/N/project/gorengor_werewolf/FractalCasimir3D:${PYTHONPATH}"

cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p .tmp results_fractal_control/results_json results_fractal_control/progress

CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_fractal_control/config_${CFG_INDEX}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file $CONFIG_FILE not found!"
    exit 1
fi

echo "Reading task parameters from $CONFIG_FILE..."
LABEL=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['label'])")
CASE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['case_name'])")
GEOM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['geometry_type'])")
N=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N_top'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['theta'])")
D_AVG=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['d_average_um'])")
D_MIN=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['d_min_um'])")
H_CAV=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['feature_depth_um'])")
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['resolution'])")
L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['L'])")

echo "Task Details:"
echo "  Label:       $LABEL"
echo "  Case:        $CASE (type: $GEOM, N=$N)"
echo "  Twist Angle: $THETA deg"
echo "  Avg Gap:     $D_AVG um"
echo "  Standoff:    $D_MIN um"
echo "  Depth:       $H_CAV um"
echo "  Material:    $MAT (L=$L_UM um, Res=$RES)"

# Execution via srun across 128 ranks
echo "Launching 3D FDTD Maxwell stress tensor integration with srun (128 ranks)..."
srun -n 128 $PYTHON_EXEC execution/run_fractal_control_simulation.py --config-file "$CONFIG_FILE"
SIM_STATUS=$?

echo "Simulation finished with exit code: $SIM_STATUS at $(date)."

if [ $SIM_STATUS -eq 0 ]; then
    echo "Task $SLURM_ARRAY_TASK_ID completed cleanly. Updating master analysis..."
    $PYTHON_EXEC execution/analyze_fractal_control.py || true
else
    echo "ERROR: Task $SLURM_ARRAY_TASK_ID failed with code $SIM_STATUS."
fi

exit $SIM_STATUS
