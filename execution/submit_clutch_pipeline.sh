#!/bin/bash
# ==============================================================================
# FRACTAL QUANTUM CLUTCH PIPELINE LAUNCHER
# ==============================================================================
# Submits the 10-task Quantum Clutch screening array on BigRed 200:
# Demonstrating rotation-driven switching from Casimir Repulsion (P > 0) to
# Attraction (P < 0) in pure vacuum between dual 3D fractals.
#
# Features:
# - Clears stale Git index locks and syncs latest verified N=3 geometry
# - Purges obsolete clutch checkpoints and cache files from .tmp/
# - Autodetects BigRed 200 conda environment
# - Automatically chains post-simulation analysis and git sync via Slurm dependency
# ==============================================================================

set -euo pipefail

REPO_ROOT="/N/project/gorengor_werewolf/FractalCasimir3D"
if [ -d "$REPO_ROOT" ]; then
    cd "$REPO_ROOT"
else
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    cd "$REPO_ROOT"
fi

echo "================================================================================"
echo "LAUNCHING FRACTAL QUANTUM CLUTCH CAMPAIGN (10 TASKS, VERIFIED N=3 ALIGNMENT)"
echo "================================================================================"
echo "Working Directory: $(pwd)"
echo "Timestamp:         $(date)"

# 1. Clear any stale Git locks that block pull/commit/push
echo -e "\n[Step 1/6] Clearing stale Git locks and synchronizing repository..."
rm -f .git/index.lock .git/refs/remotes/origin/main.lock

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "  Pulling latest verified geometry from origin/main..."
    git fetch origin main 2>/dev/null || true
    git pull origin main 2>/dev/null || true
fi

# 2. Cancel any running or pending previous clutch jobs
echo -e "\n[Step 2/6] Checking for and canceling any previous Quantum Clutch jobs..."
USER_NAME="${USER:-$(whoami)}"
PREV_JOBS=$(squeue -u "$USER_NAME" -n casimir_clutch,casimir_clutch_analyzer -h -o "%i %j %T" 2>/dev/null || true)
if [ -n "$PREV_JOBS" ]; then
    echo "  Found active/pending clutch jobs in Slurm queue:"
    echo "$PREV_JOBS" | sed 's/^/    /'
    echo "  Canceling previous clutch jobs (scancel -u $USER_NAME -n casimir_clutch,casimir_clutch_analyzer)..."
    scancel -u "$USER_NAME" -n casimir_clutch,casimir_clutch_analyzer 2>/dev/null || true
    sleep 2
    echo "  Previous clutch jobs canceled successfully."
else
    echo "  No previous clutch jobs active in queue."
fi

# 3. Prepare required directories and purge stale clutch cache/checkpoints
echo -e "\n[Step 3/6] Purging stale clutch cache and previous task outputs..."
mkdir -p .tmp cluster_diagnostics/raw_logs results_clutch Papers/Fractal_Casimir_Nature_EM/tables Papers/Fractal_Casimir_Nature_EM/figures

# Purge previous clutch cache and checkpoints to guarantee clean first-principles execution
rm -f .tmp/chk_*clutch*.json
rm -f .tmp/meep_*clutch*.json
rm -f .tmp/casimir_clutch_*.out .tmp/casimir_clutch_*.err .tmp/clutch_analyzer_*.out .tmp/clutch_analyzer_*.err

# 4. Detect Python executable in BigRed 200 conda environment
echo -e "\n[Step 4/6] Detecting Python environment..."
PYTHON_EXEC="python"
if [ -f "/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="/N/u/gogordon/BigRed200/.conda/envs/meep/bin/python"
elif [ -f "${HOME:-}/.conda/envs/meep/bin/python" ]; then
    PYTHON_EXEC="${HOME}/.conda/envs/meep/bin/python"
elif [ -f "${HOME:-}/miniconda3/etc/profile.d/conda.sh" ]; then
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    conda activate meep 2>/dev/null || true
    PYTHON_EXEC="${CONDA_PREFIX:-${HOME}/miniconda3/envs/meep}/bin/python"
fi
echo "  Using Python: $PYTHON_EXEC"

# 5. Generate/verify task configuration files
echo -e "\n[Step 5/6] Generating 10-task Quantum Clutch configuration suite..."
"$PYTHON_EXEC" execution/generate_clutch_campaign.py

# 6. Submit Slurm array and chain automated post-processing analyzer
echo -e "\n[Step 6/6] Submitting Slurm Array 'submit_clutch_campaign.sbatch'..."
JOB_OUTPUT=$(sbatch execution/submit_clutch_campaign.sbatch)
echo "  $JOB_OUTPUT"

JOB_ID=$(echo "$JOB_OUTPUT" | awk '{print $NF}')
if [ -z "$JOB_ID" ]; then
    echo "ERROR: Failed to enqueue Quantum Clutch campaign array!"
    exit 1
fi
echo "  Successfully queued Quantum Clutch Array Job ID: $JOB_ID"

echo -e "\nChaining automated post-simulation analyzer 'submit_clutch_analyzer.sbatch'..."
ANALYZER_OUTPUT=$(sbatch --dependency="afterany:$JOB_ID" execution/submit_clutch_analyzer.sbatch)
echo "  $ANALYZER_OUTPUT"
ANALYZER_ID=$(echo "$ANALYZER_OUTPUT" | awk '{print $NF}')

echo "================================================================================"
echo "QUANTUM CLUTCH PIPELINE ENQUEUED SUCCESSFULLY"
echo "================================================================================"
echo "Campaign Array Job ID: $JOB_ID (10 tasks, concurrency 5)"
echo "Chained Analyzer ID:   $ANALYZER_ID (triggers automatically upon array completion)"
echo ""
echo "To monitor cluster queue:"
echo "  squeue -u \$USER"
echo ""
echo "To inspect live task logs:"
echo "  tail -f .tmp/casimir_clutch_${JOB_ID}_1.out"
echo ""
echo "To manually harvest diagnostics and push to GitHub at any time:"
echo "  bash execution/push_all_cluster_logs.sh"
echo ""
echo "To manually run the results analyzer at any time:"
echo "  \"$PYTHON_EXEC\" execution/run_clutch_analyzer.py"
echo "================================================================================"
