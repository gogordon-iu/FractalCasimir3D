import os
import json

def generate_sweet_spot_sweep():
    print("==================================================")
    print("GENERATING SWEET SPOT MASTER PARAMETER SWEEP (224 TASKS)")
    print("==================================================")

    config_dir = "sweep_configs_sweet_spot"
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs("execution", exist_ok=True)

    # 1. Parameter Ranges as requested by the User:
    # Theta: [80, 82, 84, 86, 88, 90, 92, 94] (8 values)
    # Alpha: [70, 75, 80, 85] (4 values)
    # d: [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35] (7 values in um)
    thetas = [80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0, 94.0]
    alphas = [70.0, 75.0, 80.0, 85.0]
    ds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]

    total_tasks = len(thetas) * len(alphas) * len(ds)
    print(f"Total parameter combinations to generate: {total_tasks} tasks ({len(thetas)} thetas x {len(alphas)} alphas x {len(ds)} ds)")

    task_configs = []
    task_id = 1
    for a in alphas:
        for th in thetas:
            for d in ds:
                cfg = {
                    "param_id": task_id,
                    "alpha": float(a),
                    "theta": float(th),
                    "d": float(d),
                    "L": 2.0,
                    "N_top": 3,
                    "N_bot": 3,
                    "resolution": 40,
                    "eps_bg": 2.1,
                    "material": "Phosphorene_tuned"
                }
                config_path = os.path.join(config_dir, f"config_{task_id:03d}.json")
                with open(config_path, "w") as f:
                    json.dump(cfg, f, indent=4)
                task_configs.append(cfg)
                task_id += 1

    print(f"Successfully generated {total_tasks} JSON configuration files in '{config_dir}/'.")

    # 2. Generate Slurm Array SBATCH script
    sbatch_content = f"""#!/bin/bash
#SBATCH -J casimir_sweet_spot
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH --array=1-{total_tasks}%8
#SBATCH -o .tmp/sweet_spot_%A_%a.out
#SBATCH -e .tmp/sweet_spot_%A_%a.err

echo "=================================================="
echo "SLURM ARRAY TASK ID: $SLURM_ARRAY_TASK_ID / {total_tasks}"
echo "Running on node: $(hostname)"
echo "Start time: $(date)"
echo "=================================================="

# Environment Activation
source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python"
fi

cd /N/project/gorengor_werewolf/FractalCasimir3D
mkdir -p .tmp

# Determine Config File Index
CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_sweet_spot/config_${{CFG_INDEX}}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Config file $CONFIG_FILE not found!"
    exit 1
fi

echo "Reading parameters from $CONFIG_FILE..."
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['alpha'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['theta'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['d'])")
L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['L'])")
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['resolution'])")
EPS=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['eps_bg'])")
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")

echo "Executing 3D FDTD Simulation: Alpha=$ALPHA deg, Theta=$THETA deg, d=$D_UM um, L=$L_UM um, Res=$RES..."

$PYTHON_EXEC execution/run_meep_simulation.py \
    --L $L_UM \
    --d $D_UM \
    --N 3 \
    --N-bottom 3 \
    --corrugated \
    --corrugation-angle $ALPHA \
    --theta $THETA \
    --material $MAT \
    --res $RES \
    --eps-bg $EPS \
    --config all \
    --task-idx $SLURM_ARRAY_TASK_ID

echo "Task $SLURM_ARRAY_TASK_ID complete at $(date)."
"""

    sbatch_path = os.path.join("execution", "submit_sweet_spot_array.sbatch")
    with open(sbatch_path, "w", newline="\n") as f:
        f.write(sbatch_content)
    print(f"Generated Slurm job array script '{sbatch_path}'.")

    # 3. Generate Master Launcher Script
    master_sh = f"""#!/bin/bash
# Master Launcher Script for Sweet Spot Parameter Sweep Array & Automatic Analyzer

echo "=================================================="
echo "LAUNCHING SWEET SPOT 3D FDTD PARAMETER SWEEP ARRAY ({total_tasks} TASKS)"
echo "=================================================="

mkdir -p .tmp

# Submit Job Array
ARRAY_JOB_OUTPUT=$(sbatch execution/submit_sweet_spot_array.sbatch)
echo "$ARRAY_JOB_OUTPUT"

# Extract Job ID
ARRAY_JOB_ID=$(echo "$ARRAY_JOB_OUTPUT" | awk '{{print $4}}')

if [ -z "$ARRAY_JOB_ID" ]; then
    echo "ERROR: Failed to submit Slurm job array!"
    exit 1
fi

echo "Submitted Job Array ID: $ARRAY_JOB_ID"

# Submit Dependent Analysis Job
echo "Submitting Dependent Analysis Job (afterok:$ARRAY_JOB_ID)..."
sbatch --dependency=afterok:$ARRAY_JOB_ID execution/submit_sweet_spot_analyzer.sbatch

echo "=================================================="
echo "SUCCESS: Sweet Spot Parameter Sweep Array and Analysis Pipeline Enqueued!"
echo "Check progress using: squeue -u $USER"
echo "=================================================="
"""

    master_path = os.path.join("execution", "submit_sweet_spot_master.sh")
    with open(master_path, "w", newline="\n") as f:
        f.write(master_sh)
    os.chmod(master_path, 0o755)
    print(f"Generated Master Launcher script '{master_path}'.")

    # 4. Generate Analysis Slurm script
    analyzer_sbatch = """#!/bin/bash
#SBATCH -J sweet_spot_analysis
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=02:00:00
#SBATCH -o .tmp/sweet_spot_analysis_%j.out
#SBATCH -e .tmp/sweet_spot_analysis_%j.err

echo "=================================================="
echo "RUNNING SWEET SPOT PARAMETER SWEEP ANALYZER"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep

python execution/run_sweet_spot_analyzer.py

echo "Analysis complete."
"""

    analyzer_sbatch_path = os.path.join("execution", "submit_sweet_spot_analyzer.sbatch")
    with open(analyzer_sbatch_path, "w", newline="\n") as f:
        f.write(analyzer_sbatch)
    print(f"Generated Analysis Slurm script '{analyzer_sbatch_path}'.")

    # 5. Generate `run_sweet_spot_analyzer.py`
    analyzer_py = """import os
import sys
import glob
import json
import datetime
import subprocess
import numpy as np

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def main():
    print("==================================================")
    print("SWEET SPOT PARAMETER SWEEP RESULTS ANALYZER")
    print("==================================================")

    # 1. Search for all output JSONs across historical sweeps and new sweet spot sweep
    summary_files = glob.glob("results_*/sweet_spot_sweep_summary.json") + glob.glob("results_*/hybrid_sweep_summary.json")
    tmp_files = glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")

    records = []
    for fp in summary_files + tmp_files:
        try:
            with open(fp, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict) and ("d_um" in data or "d" in data):
                    records.append(data)
        except Exception:
            pass

    print(f"Loaded {len(records)} total JSON result records across all sweeps.")

    # 2. Extract and organize unique physical points
    results_map = {}
    for rec in records:
        d = float(rec.get("d_um", rec.get("d", 0.1)))
        theta = float(rec.get("theta_deg", rec.get("theta", 90.0)))
        alpha = float(rec.get("corrugation_angle", rec.get("alpha_deg", rec.get("alpha", 60.0))))
        
        f_both = rec.get("force_both", None)
        f_self = rec.get("force_self", None)
        p_direct = rec.get("pressure_Pa", rec.get("pressure", None))
        
        if p_direct is not None:
            p = float(p_direct)
            key = (round(alpha, 1), round(theta, 1), round(d, 4))
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }
        elif f_both is not None and f_self is not None:
            f_net = float(f_both) - float(f_self)
            A_eff = get_effective_area(3, float(rec.get("L", 2.0)))
            p = f_net / A_eff
            key = (round(alpha, 1), round(theta, 1), round(d, 4))
            results_map[key] = {
                "alpha_deg": alpha,
                "theta_deg": theta,
                "d_um": d,
                "pressure_Pa": p,
                "is_repulsive": bool(p > 0.0)
            }

    data_list = list(results_map.values())
    print(f"Extracted {len(data_list)} unique physical parameter points.")

    # Sort data points logically
    data_list.sort(key=lambda x: (x["alpha_deg"], x["theta_deg"], x["d_um"]))

    # Save timestamped summary directory
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results_sweet_spot_sweep_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    summary_file = os.path.join(out_dir, "sweet_spot_sweep_summary.json")
    with open(summary_file, "w") as f:
        json.dump(data_list, f, indent=4)

    print(f"Saved consolidated sweet spot summary to '{summary_file}'.")

    # 3. Find Nanomechanical Levitation Equilibrium Heights (P=0 with dP/dd < 0)
    print("\n--------------------------------------------------")
    print("NANOMECHANICAL LEVITATION EQUILIBRIUM HEIGHT ANALYSIS (P = 0, dP/dd < 0)")
    print("--------------------------------------------------")
    
    # Group by (alpha, theta)
    curves = {}
    for r in data_list:
        key = (r["alpha_deg"], r["theta_deg"])
        if key not in curves:
            curves[key] = []
        curves[key].append(r)

    eq_points = []
    for (a, th), pts in curves.items():
        pts.sort(key=lambda x: x["d_um"])
        if len(pts) >= 2:
            d_arr = [p["d_um"] for p in pts]
            p_arr = [p["pressure_Pa"] for p in pts]
            
            # Check for zero crossings from positive to negative as d increases (stable levitation point!)
            for i in range(len(p_arr) - 1):
                if p_arr[i] > 0 and p_arr[i+1] < 0:
                    # Linear interpolation for zero crossing
                    d1, d2 = d_arr[i], d_arr[i+1]
                    p1, p2 = p_arr[i], p_arr[i+1]
                    d_eq = d1 + (0.0 - p1) * (d2 - d1) / (p2 - p1)
                    eq_points.append({
                        "alpha_deg": a,
                        "theta_deg": th,
                        "d_eq_nm": round(d_eq * 1000.0, 2),
                        "d_eq_um": round(d_eq, 4),
                        "p_max_Pa": max(p_arr)
                    })
                    print(f"FOUND STABLE EQUILIBRIUM: Alpha={a} deg, Theta={th} deg => d_eq = {d_eq*1000.0:.2f} nm (P_max = {max(p_arr):+.4f} Pa)")

    # 4. Auto-commit and push results to GitHub
    try:
        print("\nAuto-syncing sweet spot sweep results to GitHub...")
        subprocess.run(["git", "add", summary_file], check=True)
        subprocess.run(["git", "commit", "-m", f"Add sweet spot parameter sweep results ({timestamp})"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Successfully synced sweet spot results to GitHub!")
    except Exception as e:
        print(f"Git auto-sync notice: {e}")

if __name__ == "__main__":
    main()
"""

    analyzer_py_path = os.path.join("execution", "run_sweet_spot_analyzer.py")
    with open(analyzer_py_path, "w") as f:
        f.write(analyzer_py)
    print(f"Generated Analyzer script '{analyzer_py_path}'.")

    print("\n==================================================")
    print("ALL SWEET SPOT SWEEP CODE GENERATED CLEANLY!")
    print("==================================================")

if __name__ == "__main__":
    generate_sweet_spot_sweep()
