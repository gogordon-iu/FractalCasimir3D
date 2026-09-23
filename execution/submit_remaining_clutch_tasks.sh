#!/bin/bash
# ==============================================================================
# SUBMIT & RESUME ALL QUANTUM CLUTCH SCREENING TASKS (TASKS 1-10)
# ==============================================================================
# Dispatches all 10 screening tasks with automatic checkpoint resumption:
#   - Task 1: 0/72 moments (Clean start)
#   - Task 5: 17/72 moments (Resumes from moment 18)
#   - Task 6: 38/72 moments (Resumes from moment 39)
#   - Task 10: 36/72 moments (Resumes from moment 37)
#   - Tasks 2, 3, 4, 7, 8, 9: Angled tasks on 2-node distributed general partition
#
# Does not disturb Task 999 (nmax=3 convergence) which is actively running.
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
echo "LAUNCHING / RESUMING ALL 10 CLUTCH SCREENING TASKS (TASKS 1-10)"
echo "================================================================================"
echo "Working Directory: $(pwd)"
echo "Timestamp:         $(date)"

# Sync latest Git commits
rm -f .git/index.lock .git/refs/remotes/origin/main.lock 2>/dev/null || true
git fetch origin main 2>/dev/null || true
git pull origin main 2>/dev/null || true

# 1. Submit Cardinal Tasks (1, 5, 6, 10) to general partition (1 node, 128 cores per task)
echo -e "\n[1/2] Submitting Cardinal Tasks (Tasks 1, 5, 6, 10: th=0.0, 90.0 deg) to 'general' partition (1 node each)..."
echo "  Note: Tasks 5, 6, 10 will automatically resume from their checkpointed moments."
JOB_OUT_GEN=$(sbatch --array=1,5,6,10%2 execution/submit_clutch_campaign.sbatch)
echo "  $JOB_OUT_GEN"
JOB_ID_GEN=$(echo "$JOB_OUT_GEN" | awk '{print $NF}')

# 2. Submit Angled Tasks (2, 3, 4, 7, 8, 9) across 2 nodes (256 cores, 512 GB RAM distributed)
echo -e "\n[2/2] Submitting Angled Tasks (Tasks 2, 3, 4, 7, 8, 9: th=30, 45, 60 deg) across 2 nodes (512 GB distributed RAM)..."
JOB_OUT_MULTI=$(sbatch --array=2-4,7-9%2 execution/submit_clutch_campaign_multinode.sbatch)
echo "  $JOB_OUT_MULTI"
JOB_ID_MULTI=$(echo "$JOB_OUT_MULTI" | awk '{print $NF}')

echo ""
echo "Successfully enqueued:"
echo "  - Cardinal Tasks (Tasks 1, 5, 6, 10) [1 Node, 128 cores]:  Job ID $JOB_ID_GEN"
echo "  - Angled Tasks   (Tasks 2-4, 7-9)    [2 Nodes, 256 cores]: Job ID $JOB_ID_MULTI"
echo "To monitor queue: squeue -u \$USER"
echo "================================================================================"
