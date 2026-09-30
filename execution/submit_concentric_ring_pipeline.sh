#!/bin/bash
# ==============================================================================
# Master Pipeline for Concentric Cantor-Ring Casimir Clutch: "The One Ring"
# ==============================================================================
# Usage:
#   bash execution/submit_concentric_ring_pipeline.sh
# ==============================================================================

set -e

cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "================================================================================"
echo "DISPATCHING CONCENTRIC CANTOR-RING CASIMIR CLUTCH CAMPAIGN ('THE ONE RING')"
echo "Target Cluster: BigRed 200 (Indiana University Bloomington)"
echo "Started: $(date)"
echo "================================================================================"

mkdir -p .tmp results_concentric_ring cluster_diagnostics/raw_logs

# 1. Regenerate configs if needed
if [ ! -f "sweep_configs_concentric_ring/config_017.json" ]; then
    echo "[PIPELINE] Generating 17-task Concentric Cantor-Ring configuration suite..."
    python execution/generate_concentric_ring_configs.py --res 60
fi

# 2. Submit Array Job (Tasks 1-17, max 3 concurrent on 128 cores each)
echo "[PIPELINE] Submitting Slurm array job: execution/submit_concentric_ring.sbatch..."
ARRAY_JOB_ID=$(sbatch --parsable execution/submit_concentric_ring.sbatch)
echo "  ==> Submitted Array Job ID: ${ARRAY_JOB_ID}"

# 3. Submit Postprocessing Plot Job chained after all concentric_ring jobs complete
echo "[PIPELINE] Submitting chained analysis job (dependency singleton on concentric_ring)..."
PLOT_JOB_ID=$(sbatch --dependency=singleton --job-name=concentric_ring --parsable execution/submit_concentric_ring_plot.sbatch)
echo "  ==> Submitted Postprocessing Job ID: ${PLOT_JOB_ID}"

echo "================================================================================"
echo "CAMPAIGN SUCCESSFULLY LAUNCHED ON BIGRED 200"
echo "Array Job ID:          ${ARRAY_JOB_ID} (Tasks 1-17)"
echo "Postprocessing Job ID: ${PLOT_JOB_ID} (Chained singleton: concentric_ring)"
echo "Monitor status with:   bash execution/status.sh"
echo "================================================================================"
