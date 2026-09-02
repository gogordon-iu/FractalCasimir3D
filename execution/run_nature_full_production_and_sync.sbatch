#!/bin/bash
#SBATCH -J nature_full_production
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=24:00:00
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o logs/nature_full_production_%j.out
#SBATCH -e logs/nature_full_production_%j.err

echo "=================================================="
echo "BIGRED 200: NATURE FULL PRODUCTION & AUTO-SYNC PIPELINE"
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

# 2. Navigate to Project Root and Pull Latest Code
cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p logs .tmp results_nature_validation sweep_configs_nature_refutation

echo "Pulling latest code from Git..."
git pull

# 3. Regenerate all sweep configurations (R=40, 60, 80, 100)
echo "Generating production configurations..."
$PYTHON_EXEC execution/generate_nature_refutation_suite.py

# 4. TASK 1: Grid Convergence & Corner Rounding Sweep (R = 40, 60, 80, 100)
echo "=================================================="
echo "STARTING TASK 1: FDTD GRID & TIP ROUNDING CONVERGENCE"
echo "=================================================="
RESOLUTIONS=(40 60 80 100)
TIPS=(0.0 2.0 5.0 10.0 20.0)

for RES in "${RESOLUTIONS[@]}"; do
    for RTIP in "${TIPS[@]}"; do
        echo "[Task 1] Running Res=$RES px/um, r_tip=$RTIP nm..."
        srun -n 128 $PYTHON_EXEC execution/run_rounded_convergence.py \
            --res $RES \
            --r-tip $RTIP \
            --delta-s 30.0 \
            --d 0.15 \
            --alpha 75.0 \
            --theta 90.0 \
            --outdir results_nature_validation
    done
done

# Standoff distance invariance sweep (res=80, r_tip=5nm)
for DS in 10.0 20.0 30.0 50.0; do
    echo "[Task 1] Standoff Invariance: delta_s=$DS nm (Res=80, r_tip=5nm)..."
    srun -n 128 $PYTHON_EXEC execution/run_rounded_convergence.py \
        --res 80 \
        --r-tip 5.0 \
        --delta-s $DS \
        --d 0.15 \
        --alpha 75.0 \
        --theta 90.0 \
        --outdir results_nature_validation
done

# 5. TASK 2: Anisotropic Dispersive Drude-Lorentz Optical Losses
echo "=================================================="
echo "STARTING TASK 2: ANISOTROPIC DISPERSIVE LOSSES (BP & ReS2)"
echo "=================================================="
for CFG in sweep_configs_nature_refutation/task2_config_*.json; do
    MAT_TOP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['material_top'])")
    MAT_BOT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['material_bot'])")
    MED=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['medium'])")
    THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['theta_deg'])")
    ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['alpha_deg'])")
    D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['d_um'])")

    $PYTHON_EXEC execution/run_anisotropic_dispersive_lifshitz.py \
        --material-top "$MAT_TOP" \
        --material-bot "$MAT_BOT" \
        --medium "$MED" \
        --theta "$THETA" \
        --alpha "$ALPHA" \
        --d "$D_UM" \
        --outdir results_nature_validation
done

# 6. TASK 3: 6-DOF Mechanical Stability Matrix & Earnshaw Eigenspectrum
echo "=================================================="
echo "STARTING TASK 3: 6-DOF STIFFNESS MATRIX & EIGENSPECTRUM"
echo "=================================================="
for CFG in sweep_configs_nature_refutation/task3_config_*.json; do
    D_EQ=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['d_eq_um'])")
    ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['alpha_deg'])")
    THETA_Z=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['theta_z_eq'])")
    L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['L_um'])")

    $PYTHON_EXEC execution/run_6dof_stability_analyzer.py \
        --d-eq "$D_EQ" \
        --alpha "$ALPHA" \
        --theta-z "$THETA_Z" \
        --L "$L_UM" \
        --outdir results_nature_validation
done

# 7. TASK 4: Finite-Temperature Matsubara Summation & DSI at 300 K
echo "=================================================="
echo "STARTING TASK 4: FINITE-T MATSUBARA DSI OBSERVABILITY"
echo "=================================================="
$PYTHON_EXEC execution/run_thermal_matsubara_dsi.py \
    --d 0.15 \
    --T 300.0 \
    --sweep-all \
    --outdir results_nature_validation

for CFG in sweep_configs_nature_refutation/task4_config_*.json; do
    D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['d_um'])")
    TEMP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG'))['T_K'])")

    $PYTHON_EXEC execution/run_thermal_matsubara_dsi.py \
        --d "$D_UM" \
        --T "$TEMP" \
        --outdir results_nature_validation
done

# 8. Post-Processing & Rendering Nature Publication Figures (PDF & SVG)
echo "=================================================="
echo "RENDERING NATURE PUBLICATION FIGURES..."
echo "=================================================="
$PYTHON_EXEC execution/postprocess_nature_validation.py

echo "Generated Figures:"
ls -lh nature_fig*.pdf nature_fig*.svg

# 9. Automated Git Commit and Push of All Results and Figures
echo "=================================================="
echo "SYNCING ALL RESULTS, LOGS, AND FIGURES TO GITHUB..."
echo "=================================================="
git add results_nature_validation/ logs/ nature_fig*.pdf nature_fig*.svg sweep_configs_nature_refutation/
git commit -m "Complete Nature refutation production runs (R=40-100, Tasks 1-4) from BigRed 200 Job $SLURM_JOB_ID"
git pull --rebase origin main
git push origin main

echo "=================================================="
echo "ALL NATURE TASKS EXECUTED, POST-PROCESSED, AND PUSHED TO GIT!"
echo "End Time: $(date)"
echo "=================================================="
