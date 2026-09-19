#!/bin/bash
# ==============================================================================
# FRACTAL QUANTUM CLUTCH PIPELINE LAUNCHER
# ==============================================================================
# Submits the 10-task Quantum Clutch screening array on BigRed 200:
# Demonstrating rotation-driven switching from Casimir Repulsion (P > 0) to
# Attraction (P < 0) in pure vacuum between dual 3D fractals.
# ==============================================================================

set -e

REPO_ROOT="/N/project/gorengor_werewolf/FractalCasimir3D"
cd "$REPO_ROOT"

echo "================================================================================"
echo "LAUNCHING FRACTAL QUANTUM CLUTCH CAMPAIGN (10 TASKS)"
echo "================================================================================"

# Clear any stale Git locks and prepare directories
rm -f .git/index.lock .git/refs/remotes/origin/main.lock
mkdir -p .tmp cluster_diagnostics/raw_logs

# Verify task configuration files exist
python execution/generate_clutch_campaign.py

# Submit Slurm array
echo -e "\nSubmitting Slurm Array 'submit_clutch_campaign.sbatch'..."
JOB_OUTPUT=$(sbatch execution/submit_clutch_campaign.sbatch)
echo "$JOB_OUTPUT"

JOB_ID=$(echo "$JOB_OUTPUT" | awk '{print $NF}')
echo -e "\nSuccessfully queued Quantum Clutch Array with Job ID: $JOB_ID"
echo "To monitor execution:"
echo "  squeue -u \$USER"
echo ""
echo "To harvest logs, error traces, and push diagnostics to GitHub at any time:"
echo "  bash execution/push_all_cluster_logs.sh"
echo ""
echo "To analyze results and auto-push to GitHub at any time:"
echo "  python execution/run_clutch_analyzer.py"
echo "================================================================================"
