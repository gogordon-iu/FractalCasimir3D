import argparse
import subprocess
import sys
import numpy as np

def main():
    parser = argparse.ArgumentParser(description="Map Slurm array task ID to Casimir simulation parameters and run it.")
    parser.add_argument("--task-id", type=int, default=0, help="Slurm array task ID.")
    parser.add_argument("--nsteps", type=int, default=50, help="Number of separations in sweep.")
    parser.add_argument("--res", type=int, default=40, help="MEEP grid resolution.")
    parser.add_argument("--nmax", type=int, default=5, help="Max moments index limit.")
    args = parser.parse_args()
    
    # Sweep parameters (matches the range of 20 nm to 1000 nm)
    separations = np.logspace(np.log10(0.02), np.log10(1.0), args.nsteps)
    generations = [1, 2, 3, 4]
    materials = ["PEC", "Gold", "Silicon"]
    
    # Flatten parameter grid
    tasks = []
    for mat in materials:
        for N in generations:
            for d in separations:
                tasks.append((d, N, mat))
                
    if args.task_id < 0 or args.task_id >= len(tasks):
        print(f"Error: task-id {args.task_id} is out of range [0, {len(tasks)-1}]")
        sys.exit(1)
        
    d, N, mat = tasks[args.task_id]
    print(f"Task ID {args.task_id} mapped to: d={d:.4f} um, N={N}, material={mat}, res={args.res}, nmax={args.nmax}")
    
    # Execute the simulation script
    cmd = [
        sys.executable,
        "execution/run_meep_simulation.py",
        "--d", f"{d:.4f}",
        "--N", str(N),
        "--material", mat,
        "--res", str(args.res),
        "--nmax", str(args.nmax)
    ]
    
    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
