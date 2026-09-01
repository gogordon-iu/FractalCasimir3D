#!/bin/bash
#SBATCH -J nature_refutation_master
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=24:00:00
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o logs/nature_refutation_%j.out
#SBATCH -e logs/nature_refutation_%j.err

echo "=================================================="
echo "BIGRED 200: NATURE REFUTATION MASTER PIPELINE"
echo "Job ID: $SLURM_JOB_ID"
echo "Compute Node: $(hostname)"
echo "Start Time: $(date)"
echo "=================================================="

# 1. Environment Setup & Lmod Modules
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python"
fi

# 2. Navigate to Project Root and Pull Latest Updates
cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p logs .tmp results_nature_validation sweep_configs_nature_refutation

echo "Pulling latest code and configurations from Git..."
git pull

# 3. Generate All Parameter Configurations
echo "=================================================="
echo "STEP 1: Generating Nature Refutation Configs..."
echo "=================================================="
$PYTHON_EXEC execution/generate_nature_refutation_suite.py

# 4. Task 1: Maxwell Stress Tensor Corner Rounding & Grid Convergence
echo "=================================================="
echo "STEP 2: Running Task 1 (Grid Convergence & Rounding)..."
echo "=================================================="
srun -n 128 $PYTHON_EXEC execution/run_rounded_convergence.py \
    --res 120 \
    --r-tip 5.0 \
    --delta-s 30.0 \
    --d 0.15 \
    --alpha 75.0 \
    --theta 90.0 \
    --outdir results_nature_validation

# 5. Task 2: Anisotropic Dispersive Drude-Lorentz Loss (BP & ReS2)
echo "=================================================="
echo "STEP 3: Running Task 2 (Anisotropic Dispersive Losses)..."
echo "=================================================="
$PYTHON_EXEC execution/run_anisotropic_dispersive_lifshitz.py \
    --material-top BlackPhosphorus \
    --material-bot BlackPhosphorus \
    --medium Teflon_AF \
    --theta 90.0 \
    --alpha 75.0 \
    --d 0.15 \
    --outdir results_nature_validation

$PYTHON_EXEC execution/run_anisotropic_dispersive_lifshitz.py \
    --material-top ReS2 \
    --material-bot ReS2 \
    --medium Teflon_AF \
    --theta 90.0 \
    --alpha 75.0 \
    --d 0.15 \
    --outdir results_nature_validation

# 6. Task 3: Complete 6-DOF Mechanical Stability Matrix & Earnshaw Eigenspectrum
echo "=================================================="
echo "STEP 4: Running Task 3 (6-DOF Mechanical Stiffness Matrix)..."
echo "=================================================="
$PYTHON_EXEC execution/run_6dof_stability_analyzer.py \
    --d-eq 0.15 \
    --alpha 75.0 \
    --theta-z 90.0 \
    --L 2.0 \
    --outdir results_nature_validation

# 7. Task 4: Finite-Temperature Matsubara Summation & DSI at 300 K
echo "=================================================="
echo "STEP 5: Running Task 4 (Finite-T Matsubara Summation & DSI)..."
echo "=================================================="
$PYTHON_EXEC execution/run_thermal_matsubara_dsi.py \
    --d 0.15 \
    --T 300.0 \
    --sweep-all \
    --outdir results_nature_validation

# 8. Post-Processing & Rendering Nature Publication Figures
echo "=================================================="
echo "STEP 6: Rendering 4 Publication Figures (PDF & SVG)..."
echo "=================================================="
$PYTHON_EXEC execution/postprocess_nature_validation.py

echo "=================================================="
echo "ALL NATURE REFUTATION TASKS COMPLETED SUCCESSFULLY!"
echo "End Time: $(date)"
echo "Generated Figures:"
ls -lh nature_fig*.pdf nature_fig*.svg
echo "=================================================="
