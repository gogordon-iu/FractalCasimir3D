#!/bin/bash
# ==============================================================================
# SUBMIT REMAINING QUANTUM CLUTCH TASKS (TASKS 1-5, 7-9)
# ==============================================================================
# Launches the remaining screening tasks without disturbing Tasks 6, 10, or 999
# which are already actively computing on the cluster.
#
# Task 5 automatically resumes from moment 18 (17 moments already checkpointed).
# All tasks self-resubmit every 12 hours until 100% complete.
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
echo "LAUNCHING REMAINING CLUTCH TASKS: 1, 2, 3, 4, 5, 7, 8, 9 (CONCURRENCY 3)"
echo "================================================================================"
echo "Working Directory: $(pwd)"
echo "Timestamp:         $(date)"

# Sync latest Git commits
rm -f .git/index.lock .git/refs/remotes/origin/main.lock 2>/dev/null || true
git fetch origin main 2>/dev/null || true
git pull origin main 2>/dev/null || true

# Submit remaining tasks with max concurrency 3 to balance cluster node allocation
echo -e "\nSubmitting Slurm array for tasks 1-5, 7-9..."
JOB_OUT=$(sbatch --array=1-5,7-9%3 execution/submit_clutch_campaign.sbatch)
echo "  $JOB_OUT"

JOB_ID=$(echo "$JOB_OUT" | awk '{print $NF}')
echo ""
echo "Successfully enqueued remaining tasks under Job ID: $JOB_ID"
echo "To monitor queue: squeue -u \$USER"
echo "================================================================================"
