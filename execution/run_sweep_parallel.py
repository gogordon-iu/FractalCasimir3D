import argparse
import subprocess
import sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

def run_single_simulation(d, N, material, res, nmax):
    """Worker function to run a single MEEP simulation."""
    cmd = [
        sys.executable,
        "execution/run_meep_simulation.py",
        "--d", f"{d:.4f}",
        "--N", str(N),
        "--material", material,
        "--res", str(res),
        "--nmax", str(nmax)
    ]
    print(f"Starting: d={d:.4f} um, N={N}, material={material}, res={res}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: d={d:.4f} um, N={N}, material={material}, res={res}\nError:\n{result.stderr}")
    else:
        print(f"FINISHED: d={d:.4f} um, N={N}, material={material}, res={res}")
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description="Run 3D MEEP Casimir simulations in parallel.")
    parser.add_argument("--cores", type=int, default=32, help="Number of parallel processes to use.")
    parser.add_argument("--res", type=int, default=10, help="MEEP grid resolution.")
    parser.add_argument("--nmax", type=int, default=3, help="Max moments index limit.")
    parser.add_argument("--nsteps", type=int, default=10, help="Number of separations in sweep.")
    args = parser.parse_args()

    # Define sweep parameters
    # Match the log range in postprocess_and_plot.py (0.02 um to 1.0 um)
    separations = np.logspace(np.log10(0.02), np.log10(1.0), args.nsteps)
    generations = [1, 2, 3, 4]
    materials = ["PEC", "Gold", "Silicon"]

    # Build task list
    tasks = []
    for mat in materials:
        for N in generations:
            for d in separations:
                tasks.append((d, N, mat, args.res, args.nmax))

    print(f"Total simulations to run: {len(tasks)} using {args.cores} cores")

    # Run in parallel
    failures = 0
    with ProcessPoolExecutor(max_workers=args.cores) as executor:
        futures = {
            executor.submit(run_single_simulation, d, N, mat, res, nmax): (d, N, mat)
            for d, N, mat, res, nmax in tasks
        }
        
        for future in as_completed(futures):
            params = futures[future]
            try:
                ret = future.result()
                if ret != 0:
                    failures += 1
            except Exception as e:
                print(f"Exception for task {params}: {e}")
                failures += 1

    print(f"Sweep complete. Failed tasks: {failures}/{len(tasks)}")

if __name__ == "__main__":
    main()
