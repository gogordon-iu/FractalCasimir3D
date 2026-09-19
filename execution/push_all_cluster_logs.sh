#!/bin/bash
# ==============================================================================
# BigRed 200 Cluster Diagnostics & Log Auto-Pusher
# ==============================================================================
# Cleans stale git locks, harvests all output/error logs from .tmp and Slurm,
# generates the executive forensic incident report, and pushes to GitHub.
# ==============================================================================

set -e

REPO_ROOT="/N/project/gorengor_werewolf/FractalCasimir3D"
if [ -d "$REPO_ROOT" ]; then
    cd "$REPO_ROOT"
fi

echo "================================================================================"
echo "COLLECTING & PUSHING ALL CLUSTER LOGS AND FORENSIC DIAGNOSTICS"
echo "================================================================================"

# 1. Clear any stale Git locks that block pull/commit/push
rm -f .git/index.lock .git/refs/remotes/origin/main.lock

# 2. Run the Python diagnostics harvester
PYTHON_EXEC="python"
if [ -f "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python"
elif [ -f "$HOME/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="$HOME/.conda/envs/meep/bin/python"
fi

$PYTHON_EXEC execution/harvest_cluster_diagnostics.py

echo "================================================================================"
echo "Diagnostics successfully harvested and pushed to GitHub."
echo "View report: cluster_diagnostics/FORENSIC_INCIDENT_REPORT.md"
echo "================================================================================"
