#!/bin/bash
# ==============================================================================
# Dual-Fractal Rotary Vacuum Casimir Clutch: 16-Task Campaign Pipeline
# Actual Distances: 20 nm & 30 nm (with exact deduced invariant <d>)
# Generations: N=1 & N=3 | Angles: 0 deg, 30 deg, 45 deg, 90 deg
# ==============================================================================
set -e

cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "================================================================================"
echo "LAUNCHING DUAL-FRACTAL ROTARY CASIMIR CLUTCH 16-TASK CAMPAIGN (BigRed 200)"
echo "================================================================================"

# Clear any stale flags
rm -f .tmp/clutch_task_*.flag 2>/dev/null || true
mkdir -p .tmp cluster_diagnostics/raw_logs results_fractal_rotary_clutch

# Display campaign matrix
echo "Campaign Matrix:"
echo "  Suite 1: Actual Distance d_act = 20.0 nm --> Deduced Invariant <d> = 24.45 nm"
echo "    - Tasks 01-04: Generation N=1 (z_tip = 20.00 nm, 4 needles), theta in {0, 30, 45, 90} deg"
echo "    - Tasks 05-08: Generation N=3 (z_tip = 19.40 nm, 16 needles), theta in {0, 30, 45, 90} deg"
echo ""
echo "  Suite 2: Actual Distance d_act = 30.0 nm --> Deduced Invariant <d> = 34.45 nm"
echo "    - Tasks 09-12: Generation N=1 (z_tip = 30.00 nm, 4 needles), theta in {0, 30, 45, 90} deg"
echo "    - Tasks 13-16: Generation N=3 (z_tip = 29.40 nm, 16 needles), theta in {0, 30, 45, 90} deg"
echo "================================================================================"

JOB_ID=$(sbatch --parsable execution/submit_fractal_rotary_clutch.sbatch)

echo "Slurm Array Job Submitted Successfully!"
echo "Array Job ID: $JOB_ID (Tasks 1-16, concurrency limit: 2 concurrent tasks)"
echo ""
echo "To monitor execution:"
echo "  squeue -u \$USER"
echo "  tail -f .tmp/fractal_clutch_${JOB_ID}_*.out"
echo "================================================================================"
