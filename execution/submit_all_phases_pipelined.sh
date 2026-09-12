#!/bin/bash
# Pipelined Master Launcher for All 3 Phases with Sequential Dependencies & Notifications

echo "================================================================================"
echo "ENQUEUING ALL 3 PHASES WITH SLURM CHAINING & INDIVIDUAL NOTIFICATIONS"
echo "================================================================================"

mkdir -p .tmp

# 1. Enqueue Phase 1 (Baselines)
P1_OUT=$(sbatch execution/submit_phase1_baselines.sbatch)
echo "$P1_OUT"
P1_ID=$(echo "$P1_OUT" | awk '{print $4}')
if [ -z "$P1_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 1!"
    exit 1
fi
echo "Phase 1 Array Enqueued: $P1_ID"

# 2. Enqueue Phase 2 (Pyramids & Defenses, dependent on Phase 1)
P2_OUT=$(sbatch --dependency=afterok:$P1_ID execution/submit_phase2_corrugations.sbatch)
echo "$P2_OUT"
P2_ID=$(echo "$P2_OUT" | awk '{print $4}')
if [ -z "$P2_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 2!"
    exit 1
fi
echo "Phase 2 Array Enqueued (afterok:$P1_ID): $P2_ID"

# 3. Enqueue Phase 3 (Sweet Spot Sweep, dependent on Phase 2)
P3_OUT=$(sbatch --dependency=afterok:$P2_ID execution/submit_phase3_sweet_spot.sbatch)
echo "$P3_OUT"
P3_ID=$(echo "$P3_OUT" | awk '{print $4}')
if [ -z "$P3_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 3!"
    exit 1
fi
echo "Phase 3 Array Enqueued (afterok:$P2_ID): $P3_ID"

# 4. Enqueue Master Analyzer (dependent on Phase 3)
ANALYZER_OUT=$(sbatch --dependency=afterok:$P3_ID execution/submit_unified_nature_analyzer.sbatch)
echo "$ANALYZER_OUT"
ANALYZER_ID=$(echo "$ANALYZER_OUT" | awk '{print $4}')
echo "Master Analyzer Enqueued (afterok:$P3_ID): $ANALYZER_ID"

echo "================================================================================"
echo "SUCCESS: All 3 Phases Chained and Active!"
echo "Notifications: Slurm will email gogordon@iu.edu when Phase 1 finishes,"
echo "               allowing you to inspect Phase 1 while Phase 2 runs,"
echo "               and again when Phase 2 finishes while Phase 3 runs."
echo "Check queue with: squeue -u $USER"
echo "================================================================================"
