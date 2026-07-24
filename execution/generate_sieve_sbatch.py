import os
import sys

def main():
    # Target Parameters for Frontier 1: 3D Stepped Fractal Sieve Casimir Repulsion
    L = 2.0         # plate width 2.0 um
    d = 0.12        # close-range gap 120 nm (0.12 um)
    N_top = 3       # top plate pre-fractal N=3 (27x27 grid)
    N_bot = 3       # bottom plate 3D Stepped Fractal Sieve N=3
    resolution = 40 # 40 pixels per um
    theta = 90.0    # 90 deg twist angle
    eps_bg = 2.1    # background dielectric
    material = "Phosphorene_tuned"
    nmax = 3        # 3 moments per polarization * 6 pols = 18 moments (total 108)
    T_run = 30.0
    
    # 3D Stepped Sieve Depths for levels 2, 3, 4 (macro=300nm, medium=150nm, micro=50nm)
    sieve_depths = [0.30, 0.15, 0.05]
    
    # 18 segments of 6 moments each (total 108 moments)
    moments_per_seg = 6
    num_segments = 18

    output_dir = "execution"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    print("==================================================")
    print("Generating Slurm .sbatch files for Frontier 1: 3D Stepped Fractal Sieve")
    print(f"Parameters: L={L:.2f} um, d={d:.2f} um ({d*1000:.0f} nm), N_top={N_top}, N_bottom={N_bot}")
    print(f"Sieve Depths: {sieve_depths} um, theta={theta} deg, eps_bg={eps_bg}, R={resolution}")
    print("==================================================")

    generated_files = []

    for config in ["both", "self"]:
        for seg in range(num_segments):
            m_start = seg * moments_per_seg
            m_end = (seg + 1) * moments_per_seg
            
            job_name = f"sieve_L_{L:.2f}_d_{d:.2f}_{config}_seg_{seg}"
            sbatch_filename = os.path.join(output_dir, f"submit_sieve_L_{L:.2f}_d_{d:.2f}_Ntop_{N_top}_Nbot_{N_bot}_{config}_seg_{seg}.sbatch")
            
            depths_str = " ".join(str(x) for x in sieve_depths)
            
            content = f"""#!/bin/bash
#SBATCH -J {job_name}
#SBATCH -A r01540
#SBATCH -o logs/{job_name}_%j.out
#SBATCH -e logs/{job_name}_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1
export OMP_NUM_THREADS=1

echo "Starting Frontier 1 3D Stepped Sieve segment: config={config}, moments {m_start} to {m_end}..."
mpirun -np 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \\
    --L {L:.2f} \\
    --d {d:.2f} \\
    --N {N_top} \\
    --N-bottom {N_bot} \\
    --material {material} \\
    --res {resolution} \\
    --nmax {nmax} \\
    --theta {theta} \\
    --eps-bg {eps_bg} \\
    --T-run {T_run} \\
    --config {config} \\
    --moment-start {m_start} \\
    --moment-end {m_end} \\
    --stepped-sieve \\
    --sieve-depths {depths_str}

echo "Segment {seg} ({config}) complete."
"""
            with open(sbatch_filename, "w") as f:
                f.write(content)
            generated_files.append(sbatch_filename)

    # Generate compilation plot sbatch
    plot_job_name = f"sieve_L_{L:.2f}_d_{d:.2f}_plot"
    plot_sbatch_filename = os.path.join(output_dir, f"submit_sieve_L_{L:.2f}_d_{d:.2f}_plot.sbatch")
    
    plot_content = f"""#!/bin/bash
#SBATCH -J {plot_job_name}
#SBATCH -A r01540
#SBATCH -o logs/{plot_job_name}_%j.out
#SBATCH -e logs/{plot_job_name}_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1
export OMP_NUM_THREADS=1

echo "Starting Frontier 1 3D Stepped Sieve compilation and analysis..."
$CONDA_PREFIX/bin/python execution/run_sieve_sweep.py --cores 128 --L {L:.2f} --d {d:.2f} --N-top {N_top} --N-bottom {N_bot}
echo "Compilation and analysis complete."
"""
    with open(plot_sbatch_filename, "w") as f:
        f.write(plot_content)
    generated_files.append(plot_sbatch_filename)

    # Generate submit_sieve_repulsion.sh
    submit_script = os.path.join(output_dir, "submit_sieve_repulsion.sh")
    submit_content = f"""#!/bin/bash

# Force execution from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Ensure execution logs directory exists
mkdir -p logs
mkdir -p .tmp

echo "=================================================="
echo "Submitting Frontier 1: 3D Stepped Fractal Sieve Casimir Repulsion Sweep"
echo "Parameters: L = {L:.2f} um, d = {d:.2f} um ({d*1000:.0f} nm), N_top = {N_top}, N_bottom = {N_bot}"
echo "Sieve Depths: {sieve_depths} um, theta = {theta} deg, R = {resolution}"
echo "=================================================="

JOBS=""

for config in "both" "self"; do
    for seg in {{0..17}}; do
        sbatch_file="execution/submit_sieve_L_{L:.2f}_d_{d:.2f}_Ntop_{N_top}_Nbot_{N_bot}_${{config}}_seg_${{seg}}.sbatch"
        if [ -f "$sbatch_file" ]; then
            JOB_ID=$(sbatch --parsable "$sbatch_file")
            echo "Submitted ${{sbatch_file}} -> Job ID: ${{JOB_ID}}"
            if [ -z "$JOBS" ]; then
                JOBS="$JOB_ID"
            else
                JOBS="$JOBS:$JOB_ID"
            fi
        else
            echo "Warning: ${{sbatch_file}} not found!"
        fi
    done
done

echo "--------------------------------------------------"
echo "Submitting final compilation/analysis job with dependency --dependency=afterany:${{JOBS}}"
plot_sbatch="execution/submit_sieve_L_{L:.2f}_d_{d:.2f}_plot.sbatch"
if [ -f "$plot_sbatch" ]; then
    PLOT_JOB_ID=$(sbatch --dependency=afterany:${{JOBS}} --parsable "$plot_sbatch")
    echo "Submitted plot job ${{plot_sbatch}} -> Job ID: ${{PLOT_JOB_ID}}"
fi
echo "=================================================="
echo "Submission complete. Monitor status with: squeue -u gogordon"
echo "=================================================="
"""
    with open(submit_script, "w") as f:
        f.write(submit_content)
    os.chmod(submit_script, 0o755)

    print(f"Generated {len(generated_files)} sbatch files and submission script {submit_script}")

if __name__ == "__main__":
    main()
