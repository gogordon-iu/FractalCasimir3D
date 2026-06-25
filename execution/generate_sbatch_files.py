import os

def main():
    resolutions = [20, 40, 60, 80, 100, 120]
    configs = ["both", "self"]
    
    os.makedirs("execution", exist_ok=True)
    
    template = """#!/bin/bash
#SBATCH -J conv_R{res}_{config}
#SBATCH -A r01540
#SBATCH -o logs/conv_R{res}_{config}_%A_%a.out
#SBATCH -e logs/conv_R{res}_{config}_%A_%a.err
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --array=0-35
#SBATCH --mail-type=BEGIN,FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Create logs and cache directories
mkdir -p logs
mkdir -p .tmp

# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

# Set OpenMP threads to 1 for parallel MPI execution
export OMP_NUM_THREADS=1

echo "Running task ID: $SLURM_ARRAY_TASK_ID (resolution = {res} px/um, config = {config})"

srun -n 128 python execution/run_meep_simulation.py \\
    --d 0.1 \\
    --N 2 \\
    --material Gold \\
    --res {res} \\
    --nmax 1 \\
    --T-run 20.0 \\
    --config {config} \\
    --task-idx $SLURM_ARRAY_TASK_ID
"""

    for res in resolutions:
        for config in configs:
            filename = f"execution/submit_conv_res{res}_{config}.sbatch"
            content = template.format(res=res, config=config)
            with open(filename, "w") as f:
                f.write(content)
            print(f"Generated: {filename}")

if __name__ == "__main__":
    main()
