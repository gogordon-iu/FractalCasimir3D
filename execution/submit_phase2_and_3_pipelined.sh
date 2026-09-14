#!/bin/bash
# Pipelined Master Launcher for All 3 Phases with Sequential Dependencies & Notifications

echo "================================================================================"
echo "ENQUEUING ALL 3 PHASES WITH SLURM CHAINING & INDIVIDUAL NOTIFICATIONS"
echo "================================================================================"

mkdir -p .tmp

# 1. Enqueue Phase 2 (Pyramids & Defenses, 40 tasks)
P2_OUT=$(sbatch execution/submit_phase2_corrugations.sbatch)
echo "$P2_OUT"
P2_ID=$(echo "$P2_OUT" | awk '{print $4}')
if [ -z "$P2_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 2!"
    exit 1
fi
echo "Phase 2 Array Enqueued: $P2_ID"

# 3. Enqueue Phase 3 (Sweet Spot Sweep, runs when Phase 2 finishes)
P3_OUT=$(sbatch --dependency=afterany:$P2_ID execution/submit_phase3_sweet_spot.sbatch)
echo "$P3_OUT"
P3_ID=$(echo "$P3_OUT" | awk '{print $4}')
if [ -z "$P3_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 3!"
    exit 1
fi
echo "Phase 3 Array Enqueued (afterany:$P2_ID): $P3_ID"

# 3. Enqueue Master Analyzer (runs when Phase 3 finishes)
ANALYZER_OUT=$(sbatch --dependency=afterany:$P3_ID execution/submit_unified_nature_analyzer.sbatch)
echo "$ANALYZER_OUT"
ANALYZER_ID=$(echo "$ANALYZER_OUT" | awk '{print $4}')
echo "Master Analyzer Enqueued (afterany:$P3_ID): $ANALYZER_ID"

echo "================================================================================"
echo "SUCCESS: Phase 2, Phase 3, and Master Analyzer Chained and Active!"
echo "Notifications: Slurm will email gogordon@iu.edu when Phase 2 finishes,"
echo "               and again when Phase 3 finishes."
echo "Check queue with: squeue -u $USER"
echo "================================================================================"
