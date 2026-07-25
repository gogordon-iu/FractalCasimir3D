import os
import sys

def main():
    # Target Parameters for Frontier 2: 3D Interlocking Fractal Corrugations
    L = 2.0         # plate width 2.0 um
    d = 0.10        # close-range gap 100 nm (0.10 um)
    N_top = 3       # top plate pre-fractal N=3
    N_bot = 3       # bottom plate 3D Fractal Corrugation N=3
    resolution = 40 # 40 pixels per um
    theta = 91.1    # 90 deg anisotropic twist + 1.1 deg Moire twist angle
    eps_bg = 2.1    # background dielectric
    material = "Phosphorene_tuned"
    nmax = 3        # 3 moments per polarization * 6 pols = 18 moments (total 108)
    T_run = 30.0
    corrugation_angle = 60.0 # 60-degree sloped walls for strong transverse field bending
    
    # 18 segments of 6 moments each (total 108 moments)
    moments_per_seg = 6
    num_segments = 18

    output_dir = "execution"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    print("==================================================")
    print("Generating Slurm .sbatch files for Frontier 2: Interlocking 3D Fractal Corrugations")
    print(f"Parameters: L={L:.2f} um, d={d:.2f} um ({d*1000:.0f} nm), N_top={N_top}, N_bottom={N_bot}")
    print(f"Corrugation Angle: {corrugation_angle} deg, theta={theta} deg, eps_bg={eps_bg}, R={resolution}")
    print("==================================================")

    generated_files = []

    for config in ["both", "self"]:
        for seg in range(num_segments):
            m_start = seg * moments_per_seg
            m_end = (seg + 1) * moments_per_seg
            
            job_name = f"corrugated_L_{L:.2f}_d_{d:.2f}_Ntop_{N_top}_Nbot_{N_bot}_{config}_seg_{seg}"
            sbatch_filename = os.path.join(output_dir, f"submit_{job_name}.sbatch")
            
            content = f"""#!/bin/bash
#SBATCH -J {job_name}
#SBATCH -A r01540
#SBATCH -o logs/{job_name}_%j.out
#SBATCH -e logs/{job_name}_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=08:00:00
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

echo "Starting Frontier 2 3D Corrugated segment: config={config}, moments {m_start} to {m_end}..."
$CONDA_PREFIX/bin/python execution/run_meep_simulation.py \\
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
    --corrugated \\
    --corrugation-angle {corrugation_angle}

echo "Completed Frontier 2 segment: config={config}, moments {m_start} to {m_end}."
"""
            with open(sbatch_filename, "w") as f:
                f.write(content)
            generated_files.append(sbatch_filename)

    # Generate compilation/plot sbatch script
    plot_job_name = f"corrugated_L_{L:.2f}_d_{d:.2f}_plot"
    plot_sbatch_filename = os.path.join(output_dir, f"submit_{plot_job_name}.sbatch")
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
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1
export OMP_NUM_THREADS=1

echo "Aggregating Frontier 2 3D Corrugated simulation results for L={L:.2f} um, d={d:.2f} um..."
$CONDA_PREFIX/bin/python execution/run_corrugated_sweep.py \\
    --L {L:.2f} \\
    --d {d:.2f} \\
    --N {N_top} \\
    --N-bottom {N_bot} \\
    --material {material} \\
    --res {resolution} \\
    --theta {theta} \\
    --eps-bg {eps_bg}

echo "Frontier 2 Aggregation complete."
"""
    with open(plot_sbatch_filename, "w") as f:
        f.write(plot_content)

    # Master Slurm submission bash script
    master_submit_script = os.path.join(output_dir, "submit_corrugated_repulsion.sh")
    with open(master_submit_script, "w") as f:
        f.write("#!/bin/bash\n")
        f.write("# Master Slurm Submission Script for Frontier 2: 3D Interlocking Fractal Corrugations\n\n")
        f.write("cd /N/project/gorengor_werewolf/FractalCasimir3D\n")
        f.write("mkdir -p logs .tmp\n\n")
        f.write("job_ids=()\n\n")
        
        for config in ["both", "self"]:
            for seg in range(num_segments):
                sbatch_file = f"execution/submit_corrugated_L_{L:.2f}_d_{d:.2f}_Ntop_{N_top}_Nbot_{N_bot}_{config}_seg_{seg}.sbatch"
                f.write(f'res=$(sbatch {sbatch_file})\n')
                f.write('job_id=$(echo $res | awk \'{print $4}\')\n')
                f.write('job_ids+=($job_id)\n')
                f.write(f'echo "Submitted {config} seg {seg}: Job ID $job_id"\n\n')
                
        f.write('# Build dependency string: afterany:job1:job2:...\n')
        f.write('dep_str=$(IFS=:; echo "${job_ids[*]}")\n\n')
        f.write(f'echo "Submitting compilation plot job dependent on ${{#job_ids[@]}} segment jobs..."\n')
        f.write(f'sbatch --dependency=afterany:$dep_str execution/submit_{plot_job_name}.sbatch\n\n')
        f.write('echo "All Frontier 2 simulation segment jobs and plot job successfully queued on BigRed200."\n')
        
    os.chmod(master_submit_script, 0o755)

    print(f"Generated {len(generated_files) + 1} sbatch files and submission script {master_submit_script}")

if __name__ == "__main__":
    main()
