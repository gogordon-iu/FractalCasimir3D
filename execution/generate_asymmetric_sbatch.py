import os

def generate_asymmetric_sbatch():
    os.makedirs("execution", exist_ok=True)
    
    L = 2.0
    d = 0.25
    N_top = 3
    N_bot = 2
    res = 40
    theta = 90.0
    eps_bg = 2.1
    mat = "Phosphorene_tuned"
    time_limit = "06:00:00"
    
    # 18 segments of 6 moments each (total 108 moments)
    segments = [(i * 6, (i + 1) * 6) for i in range(18)]
    
    for config in ["both", "self"]:
        suffix = f"asym_L_{L:.2f}_d_{d:.2f}_Ntop_{N_top}_Nbot_{N_bot}_{config}"
        for seg_idx, (m_start, m_end) in enumerate(segments):
            sbatch_file = f"execution/submit_{suffix}_seg_{seg_idx}.sbatch"
            
            content = f"""#!/bin/bash
#SBATCH -J {suffix}_seg_{seg_idx}
#SBATCH -A r01540
#SBATCH -o logs/{suffix}_seg_{seg_idx}_%j.out
#SBATCH -e logs/{suffix}_seg_{seg_idx}_%j.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time={time_limit}
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

echo "Starting Asymmetric Dual-Fractal Casimir Sweep ({config}) Segment {seg_idx}: moments {m_start} to {m_end}..."
srun -n 128 $CONDA_PREFIX/bin/python execution/run_meep_simulation.py \\
    --d {d} \\
    --N {N_top} \\
    --N-bottom {N_bot} \\
    --material {mat} \\
    --res {res} \\
    --nmax 3 \\
    --theta {theta} \\
    --eps-bg {eps_bg} \\
    --L {L} \\
    --config {config} \\
    --moment-start {m_start} \\
    --moment-end {m_end}

echo "Segment {seg_idx} complete."
"""
            with open(sbatch_file, "w") as f:
                f.write(content)
                
    # Also generate plot/compilation sbatch file
    plot_sbatch = f"execution/submit_asym_L_{L:.2f}_d_{d:.2f}_plot.sbatch"
    plot_content = f"""#!/bin/bash
#SBATCH -J asym_L_{L:.2f}_plot
#SBATCH -A r01540
#SBATCH -o logs/asym_L_{L:.2f}_plot_%j.out
#SBATCH -e logs/asym_L_{L:.2f}_plot_%j.err
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

echo "Starting Asymmetric Dual-Fractal compilation and analysis..."
$CONDA_PREFIX/bin/python execution/run_asymmetric_sweep.py --cores 128 --L {L} --d {d} --N-top {N_top} --N-bottom {N_bot}
echo "Compilation and analysis complete."
"""
    with open(plot_sbatch, "w") as f:
        f.write(plot_content)

    print(f"Generated asymmetric sbatch files for L={L} um, d={d} um (Ntop={N_top}, Nbot={N_bot})")

if __name__ == "__main__":
    generate_asymmetric_sbatch()
