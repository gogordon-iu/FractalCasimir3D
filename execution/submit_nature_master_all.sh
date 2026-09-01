#!/bin/bash
# Master Submission Script for Nature Refutation Suite on BigRed 200

echo "=================================================="
echo "SUBMITTING ALL 4 NATURE REFUTATION SLURM ARRAYS"
echo "=================================================="

mkdir -p .tmp results_nature_validation

JOB1=$(sbatch execution/submit_nature_task1_convergence.sbatch | awk '{print $NF}')
echo "Submitted Task 1 (Grid Convergence & Rounding): Job ID $JOB1"

JOB2=$(sbatch execution/submit_nature_task2_dispersion.sbatch | awk '{print $NF}')
echo "Submitted Task 2 (Dispersive Kramers-Kronig Loss): Job ID $JOB2"

JOB3=$(sbatch execution/submit_nature_task3_stability_6dof.sbatch | awk '{print $NF}')
echo "Submitted Task 3 (6-DOF Stability Matrix): Job ID $JOB3"

JOB4=$(sbatch execution/submit_nature_task4_thermal_matsubara.sbatch | awk '{print $NF}')
echo "Submitted Task 4 (Finite-T Matsubara DSI): Job ID $JOB4"

echo "=================================================="
echo "All Nature validation jobs submitted successfully!"
echo "Monitor with: squeue -u $USER"
echo "=================================================="
