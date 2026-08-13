import os
import glob
import json
import subprocess

def main():
    print("==================================================")
    print("CHECKING COMPLETED SWEET SPOT TASKS (1-224)")
    print("==================================================")

    # 1. Ensure config directory exists
    if not os.path.exists("sweep_configs_sweet_spot"):
        print("sweep_configs_sweet_spot missing. Generating...")
        subprocess.run(["python", "execution/generate_sweet_spot_configs.py"], check=True)

    # 2. Find all completed task_idx numbers from raw .tmp JSON files
    completed_task_ids = set()
    files = glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")
    for f in files:
        try:
            with open(f, "r") as fp:
                d = json.load(fp)
                if isinstance(d, dict) and "task_idx" in d and d["task_idx"] > 0:
                    completed_task_ids.add(d["task_idx"])
        except Exception:
            pass

    all_task_ids = set(range(1, 225))
    missing_task_ids = sorted(list(all_task_ids - completed_task_ids))

    print(f"Completed Tasks: {len(completed_task_ids)} / 224")
    print(f"Missing Tasks:   {len(missing_task_ids)} / 224")

    if not missing_task_ids:
        print("ALL 224 TASKS ARE 100% COMPLETE!")
        return

    print(f"Resubmitting {len(missing_task_ids)} missing tasks to Slurm...")

    # Create missing sbatch file
    sbatch_missing_path = "execution/submit_missing_sweet_spot.sbatch"
    with open("execution/submit_sweet_spot_array.sbatch", "r") as f:
        sbatch_content = f.read()

    lines = sbatch_content.splitlines()
    new_lines = []
    
    # Format array string safely (e.g. 1,2,3... or range)
    array_param = f"{missing_task_ids[0]}-{missing_task_ids[-1]}%8"
    
    for line in lines:
        if line.startswith("#SBATCH --array="):
            new_lines.append(f"#SBATCH --array={array_param}")
        else:
            new_lines.append(line)

    with open(sbatch_missing_path, "w", newline="\n") as f:
        f.write("\n".join(new_lines) + "\n")

    print(f"Generated missing tasks SBATCH file '{sbatch_missing_path}'.")

    # Submit to Slurm
    cmd = f"sbatch {sbatch_missing_path}"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr)

if __name__ == "__main__":
    main()
