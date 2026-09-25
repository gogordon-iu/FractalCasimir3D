#!/bin/bash
# Master Dispatcher for Fractal Geometry Control Campaign on BigRed 200

echo "================================================================================"
echo "DISPATCHING FRACTAL GEOMETRY CONTROL CAMPAIGN (15 TASKS)"
echo "Target: BigRed 200 (Partition: general, 128 cores/node)"
echo "================================================================================"

# Ensure directories exist
mkdir -p .tmp results_fractal_control/results_json results_fractal_control/progress results_fractal_control/figures

# Verify configs exist
if [ ! -d "sweep_configs_fractal_control" ] || [ $(ls -1 sweep_configs_fractal_control/config_*.json 2>/dev/null | wc -l) -ne 15 ]; then
    echo "Generating configuration files..."
    python execution/generate_fractal_control_configs.py
fi

# Submit Slurm job array
JOB_ID=$(sbatch --parsable execution/submit_fractal_control_campaign.sbatch)
echo "Submitted Slurm job array with Job ID: $JOB_ID"
echo "Monitor status with: squeue -u $USER"
echo "Track real-time progress with: python execution/analyze_fractal_control.py"
echo "View logs at: .tmp/casimir_fractal_ctrl_${JOB_ID}_*.out"
