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

# 1. Submit Cardinal Tasks (1, 5) to general partition (171-181 GB RAM fits in 240 GB node limit)
echo -e "\n[1/2] Submitting Cardinal Tasks (Task 1: th=0.0 deg, Task 5: th=90.0 deg) to 'general' partition..."
echo "  Note: Task 5 will automatically resume from its 17 checkpointed moments."
JOB_OUT_GEN=$(sbatch --array=1,5%2 execution/submit_clutch_campaign.sbatch)
echo "  $JOB_OUT_GEN"
JOB_ID_GEN=$(echo "$JOB_OUT_GEN" | awk '{print $NF}')

# 2. Submit Angled Tasks (2, 3, 4, 7, 8, 9) to largemem partition (285 GB RAM requires >240 GB node)
echo -e "\n[2/2] Submitting Angled Tasks (Tasks 2, 3, 4, 7, 8, 9: th=30, 45, 60 deg) to 'largemem' partition (350GB RAM requested)..."
JOB_OUT_MEM=$(sbatch --array=2-4,7-9%3 execution/submit_clutch_campaign_largemem.sbatch)
echo "  $JOB_OUT_MEM"
JOB_ID_MEM=$(echo "$JOB_OUT_MEM" | awk '{print $NF}')

echo ""
echo "Successfully enqueued:"
echo "  - General Partition (Tasks 1, 5): Job ID $JOB_ID_GEN"
echo "  - Largemem Partition (Tasks 2-4, 7-9): Job ID $JOB_ID_MEM"
echo "To monitor queue: squeue -u \$USER"
echo "================================================================================"
