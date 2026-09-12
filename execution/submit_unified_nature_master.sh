#!/bin/bash
# Master Launcher Script for Unified Nature Campaign (292 Tasks) & Automated Analyzer

echo "================================================================================"
echo "LAUNCHING UNIFIED NATURE PUBLICATION RUN (292 TASKS) ON BIGRED 200"
echo "================================================================================"

mkdir -p .tmp

# Submit Job Array
ARRAY_SUBMIT=$(sbatch execution/submit_unified_nature_array.sbatch)
echo "$ARRAY_SUBMIT"

ARRAY_ID=$(echo "$ARRAY_SUBMIT" | awk '{print $4}')
if [ -z "$ARRAY_ID" ]; then
    echo "ERROR: Failed to obtain Slurm Job Array ID!"
    exit 1
fi

echo "Submitted Job Array ID: $ARRAY_ID"

# Submit Dependent Analyzer Job (afterok)
echo "Submitting Dependent Analyzer (afterok:$ARRAY_ID)..."
ANALYZER_SUBMIT=$(sbatch --dependency=afterok:$ARRAY_ID execution/submit_unified_nature_analyzer.sbatch)
echo "$ANALYZER_SUBMIT"

echo "================================================================================"
echo "SUCCESS: Entire Unified Nature Campaign Enqueued on BigRed 200!"
echo "Array ID: $ARRAY_ID"
echo "Monitor status with: squeue -u $USER"
echo "================================================================================"
