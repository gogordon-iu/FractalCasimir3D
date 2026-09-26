#!/bin/bash
# ==============================================================================
# Master Submission Pipeline for Sierpinski-Cantor Forest Casimir Repulsion
# ==============================================================================
# Usage:
#   bash execution/submit_cantor_forest_pipeline.sh
# ==============================================================================

set -e

cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "================================================================================"
echo "SIERPINSKI-CANTOR FOREST CASIMIR REPULSION CAMPAIGN SUBMISSION"
echo "Target Cluster: BigRed 200 (Indiana University Bloomington)"
echo "Started: $(date)"
echo "================================================================================"

mkdir -p .tmp logs results_cantor_forest cluster_diagnostics/raw_logs

# 1. Regenerate configurations if needed
if [ ! -f "sweep_configs_cantor_forest/config_008.json" ]; then
    echo "[PIPELINE] Generating 8-task Sierpinski-Cantor Forest configuration suite..."
    python execution/generate_cantor_forest_configs.py --res 60
fi

# 2. Submit Array Job (Tasks 1-8, max 2 concurrent on 128 cores each)
echo "[PIPELINE] Submitting Slurm array job: execution/submit_cantor_forest.sbatch..."
ARRAY_JOB_ID=$(sbatch --parsable execution/submit_cantor_forest.sbatch)
echo "  ==> Submitted Array Job ID: ${ARRAY_JOB_ID}"

# 3. Submit Postprocessing Plot Job chained after array completion
echo "[PIPELINE] Submitting chained analysis job (dependency afterany:${ARRAY_JOB_ID})..."
PLOT_JOB_ID=$(sbatch --dependency=afterany:${ARRAY_JOB_ID} --parsable execution/submit_cantor_forest_plot.sbatch)
echo "  ==> Submitted Postprocessing Job ID: ${PLOT_JOB_ID}"

echo "================================================================================"
echo "CAMPAIGN SUCCESSFULLY LAUNCHED ON BIGRED 200"
echo "Array Job ID:          ${ARRAY_JOB_ID} (Tasks 1-8)"
echo "Postprocessing Job ID: ${PLOT_JOB_ID} (Chained afterany)"
echo "Monitor status with:   squeue -u \$USER"
echo "================================================================================"
