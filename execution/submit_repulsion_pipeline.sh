#!/bin/bash
# ==============================================================================
# Vacuum Casimir Repulsion Pipeline Launcher
# ==============================================================================
set -e

cd /N/project/gorengor_werewolf/FractalCasimir3D

# Auto-detect Python executable
if [ -f "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python"
elif [ -f "$HOME/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="$HOME/.conda/envs/meep/bin/python"
else
    PYTHON_EXEC="python"
fi

echo "================================================================================"
echo "LAUNCHING VACUUM CASIMIR REPULSION CAMPAIGN (PHASE 1)"
echo "Target: Discovering Genuine Casimir Repulsion in Pure Vacuum (P > 0)"
echo "Python: $PYTHON_EXEC"
echo "================================================================================"

# 1. Generate/verify the 36 Phase 1 configurations
$PYTHON_EXEC execution/generate_repulsion_campaign.py

# 2. Submit the Slurm array job
JOB_OUTPUT=$(sbatch execution/submit_repulsion_campaign.sbatch)
echo "$JOB_OUTPUT"

JOB_ID=$(echo "$JOB_OUTPUT" | awk '{print $4}')
echo ""
echo "================================================================================"
echo "SUCCESS: Repulsion Phase 1 submitted under Slurm Job ID: $JOB_ID"
echo "================================================================================"
echo "To monitor cluster progress, run:"
echo "    squeue -u \$USER"
echo ""
echo "To analyze results and auto-push to GitHub at any time, run:"
echo "    $PYTHON_EXEC execution/run_repulsion_analyzer.py"
echo "================================================================================"
