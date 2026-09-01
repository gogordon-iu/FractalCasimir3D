"""
Master Orchestrator & BigRed 200 Slurm Suite Generator for Nature Refutation
----------------------------------------------------------------------------
Generates all configuration JSONs in sweep_configs_nature_refutation/ and creates
production Slurm sbatch array submission scripts tailored for Indiana University's
BigRed 200 Cray EX supercomputer (AMD EPYC 7742, 128 cores/node, account r01540).
"""

import os
import json


def generate_all_nature_configs():
    print("==================================================")
    print("GENERATING NATURE REFUTATION SUITE (TASKS 1 - 4)")
    print("==================================================")

    config_dir = "sweep_configs_nature_refutation"
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs("execution", exist_ok=True)
    os.makedirs("results_nature_validation", exist_ok=True)

    # -------------------------------------------------------------------------
    # Task 1 Configurations: Grid Convergence & Edge Rounding
    # -------------------------------------------------------------------------
    resolutions = [40, 60, 80, 100, 120, 160]
    r_tips_nm = [0.0, 2.0, 5.0, 10.0, 20.0]
    standoffs_nm = [10.0, 20.0, 30.0, 50.0]

    t1_configs = []
    t1_id = 1
    for res in resolutions:
        for r_tip in r_tips_nm:
            for ds in [30.0]:  # Primary standoff
                cfg = {
                    "task_type": "task1_convergence",
                    "task_id": t1_id,
                    "resolution": res,
                    "r_tip_nm": r_tip,
                    "delta_s_nm": ds,
                    "d_um": 0.15,
                    "alpha_deg": 75.0,
                    "theta_deg": 90.0,
                    "L_um": 2.0,
                    "material": "Phosphorene_tuned"
                }
                cpath = os.path.join(config_dir, f"task1_config_{t1_id:03d}.json")
                with open(cpath, "w") as f:
                    json.dump(cfg, f, indent=4)
                t1_configs.append(cfg)
                t1_id += 1

    # Standoff distance invariance sweep (res=80, r_tip=5nm)
    for ds in standoffs_nm:
        cfg = {
            "task_type": "task1_convergence",
            "task_id": t1_id,
            "resolution": 80,
            "r_tip_nm": 5.0,
            "delta_s_nm": ds,
            "d_um": 0.15,
            "alpha_deg": 75.0,
            "theta_deg": 90.0,
            "L_um": 2.0,
            "material": "Phosphorene_tuned"
        }
        cpath = os.path.join(config_dir, f"task1_config_{t1_id:03d}.json")
        with open(cpath, "w") as f:
            json.dump(cfg, f, indent=4)
        t1_configs.append(cfg)
        t1_id += 1

    print(f"Task 1: Generated {len(t1_configs)} grid convergence & edge rounding configs.")

    # -------------------------------------------------------------------------
    # Task 2 Configurations: Anisotropic Dispersive Kramers-Kronig Loss
    # -------------------------------------------------------------------------
    materials = ["BlackPhosphorus", "ReS2", "Phosphorene_tuned", "Gold", "Silicon"]
    media = ["Vacuum", "Teflon_AF", "Ethanol", "Bromobenzene", "Glycerol"]
    thetas_t2 = [0.0, 30.0, 45.0, 60.0, 75.0, 90.0]
    ds_t2 = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]

    t2_configs = []
    t2_id = 1
    for mat in ["BlackPhosphorus", "ReS2"]:
        for med in ["Teflon_AF", "Ethanol", "Bromobenzene"]:
            for th in thetas_t2:
                for d in ds_t2:
                    cfg = {
                        "task_type": "task2_dispersion",
                        "task_id": t2_id,
                        "material_top": mat,
                        "material_bot": mat,
                        "medium": med,
                        "theta_deg": th,
                        "alpha_deg": 75.0,
                        "d_um": d,
                        "T_K": 0.0
                    }
                    cpath = os.path.join(config_dir, f"task2_config_{t2_id:03d}.json")
                    with open(cpath, "w") as f:
                        json.dump(cfg, f, indent=4)
                    t2_configs.append(cfg)
                    t2_id += 1

    print(f"Task 2: Generated {len(t2_configs)} dispersive loss & immersion configs.")

    # -------------------------------------------------------------------------
    # Task 3 Configurations: 6-DOF Mechanical Stability Matrix
    # -------------------------------------------------------------------------
    t3_configs = []
    t3_id = 1
    for d_eq in [0.10, 0.12, 0.15, 0.18, 0.20]:
        for alpha in [60.0, 70.0, 75.0, 80.0]:
            cfg = {
                "task_type": "task3_stability_6dof",
                "task_id": t3_id,
                "d_eq_um": d_eq,
                "alpha_deg": alpha,
                "theta_z_eq": 90.0,
                "L_um": 2.0
            }
            cpath = os.path.join(config_dir, f"task3_config_{t3_id:03d}.json")
            with open(cpath, "w") as f:
                json.dump(cfg, f, indent=4)
            t3_configs.append(cfg)
            t3_id += 1

    print(f"Task 3: Generated {len(t3_configs)} 6-DOF mechanical stability configs.")

    # -------------------------------------------------------------------------
    # Task 4 Configurations: Finite-Temperature Matsubara Summation & DSI
    # -------------------------------------------------------------------------
    temperatures = [4.0, 77.0, 150.0, 300.0, 400.0]
    ds_t4 = [0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00]

    t4_configs = []
    t4_id = 1
    for temp in temperatures:
        for d in ds_t4:
            cfg = {
                "task_type": "task4_thermal_matsubara",
                "task_id": t4_id,
                "d_um": d,
                "T_K": temp,
                "material_top": "BlackPhosphorus",
                "material_bot": "BlackPhosphorus",
                "medium": "Teflon_AF",
                "theta_deg": 90.0,
                "alpha_deg": 75.0
            }
            cpath = os.path.join(config_dir, f"task4_config_{t4_id:03d}.json")
            with open(cpath, "w") as f:
                json.dump(cfg, f, indent=4)
            t4_configs.append(cfg)
            t4_id += 1

    print(f"Task 4: Generated {len(t4_configs)} finite-temperature Matsubara DSI configs.")

    # -------------------------------------------------------------------------
    # Generate Slurm Batch Scripts for BigRed 200
    # -------------------------------------------------------------------------
    generate_slurm_scripts(len(t1_configs), len(t2_configs), len(t3_configs), len(t4_configs))


def generate_slurm_scripts(num_t1, num_t2, num_t3, num_t4):
    # Common SBATCH header
    header_template = """#!/bin/bash
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
"""

    # Task 1 SBATCH
    t1_sbatch = f"""{header_template}#SBATCH -J nature_t1_conv
#SBATCH --array=1-{num_t1}%8
#SBATCH -o .tmp/nature_t1_%A_%a.out
#SBATCH -e .tmp/nature_t1_%A_%a.err

echo "=================================================="
echo "NATURE TASK 1: GRID CONVERGENCE & EDGE ROUNDING"
echo "Array Task: $SLURM_ARRAY_TASK_ID / {num_t1} on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task1_config_%03d.json" $SLURM_ARRAY_TASK_ID)
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['resolution'])")
RTIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['r_tip_nm'])")
DS=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['delta_s_nm'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_um'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['alpha_deg'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['theta_deg'])")

srun -n 128 $PYTHON_EXEC execution/run_rounded_convergence.py \\
    --res $RES --r-tip $RTIP --delta-s $DS --d $D_UM --alpha $ALPHA --theta $THETA --outdir results_nature_validation

echo "Completed Task 1 at $(date)"
"""

    # Task 2 SBATCH
    t2_sbatch = f"""{header_template}#SBATCH -J nature_t2_disp
#SBATCH --array=1-{num_t2}%12
#SBATCH -o .tmp/nature_t2_%A_%a.out
#SBATCH -e .tmp/nature_t2_%A_%a.err

echo "=================================================="
echo "NATURE TASK 2: ANISOTROPIC DISPERSIVE LOSS"
echo "Array Task: $SLURM_ARRAY_TASK_ID / {num_t2} on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task2_config_%03d.json" $SLURM_ARRAY_TASK_ID)
MAT_TOP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['material_top'])")
MAT_BOT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['material_bot'])")
MED=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['medium'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['theta_deg'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['alpha_deg'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_um'])")

$PYTHON_EXEC execution/run_anisotropic_dispersive_lifshitz.py \\
    --material-top $MAT_TOP --material-bot $MAT_BOT --medium $MED --theta $THETA --alpha $ALPHA --d $D_UM --outdir results_nature_validation

echo "Completed Task 2 at $(date)"
"""

    # Task 3 SBATCH
    t3_sbatch = f"""{header_template}#SBATCH -J nature_t3_stab
#SBATCH --array=1-{num_t3}%8
#SBATCH -o .tmp/nature_t3_%A_%a.out
#SBATCH -e .tmp/nature_t3_%A_%a.err

echo "=================================================="
echo "NATURE TASK 3: 6-DOF MECHANICAL STIFFNESS MATRIX"
echo "Array Task: $SLURM_ARRAY_TASK_ID / {num_t3} on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task3_config_%03d.json" $SLURM_ARRAY_TASK_ID)
D_EQ=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_eq_um'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['alpha_deg'])")
THETA_Z=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['theta_z_eq'])")
L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['L_um'])")

$PYTHON_EXEC execution/run_6dof_stability_analyzer.py \\
    --d-eq $D_EQ --alpha $ALPHA --theta-z $THETA_Z --L $L_UM --outdir results_nature_validation

echo "Completed Task 3 at $(date)"
"""

    # Task 4 SBATCH
    t4_sbatch = f"""{header_template}#SBATCH -J nature_t4_temp
#SBATCH --array=1-{num_t4}%12
#SBATCH -o .tmp/nature_t4_%A_%a.out
#SBATCH -e .tmp/nature_t4_%A_%a.err

echo "=================================================="
echo "NATURE TASK 4: FINITE-T MATSUBARA SUMMATION & DSI"
echo "Array Task: $SLURM_ARRAY_TASK_ID / {num_t4} on $(hostname)"
echo "Start: $(date)"
echo "=================================================="

source ~/miniconda3/etc/profile.d/conda.sh
module unload xalt
export XALT_EXECUTABLE_TRACKING=no
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

PYTHON_EXEC="$CONDA_PREFIX/bin/python"
[ ! -f "$PYTHON_EXEC" ] && PYTHON_EXEC="python"

CFG_FILE=$(printf "sweep_configs_nature_refutation/task4_config_%03d.json" $SLURM_ARRAY_TASK_ID)
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['d_um'])")
TEMP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CFG_FILE'))['T_K'])")

$PYTHON_EXEC execution/run_thermal_matsubara_dsi.py \\
    --d $D_UM --T $TEMP --outdir results_nature_validation

echo "Completed Task 4 at $(date)"
"""

    # Master submission launcher script
    master_sh = """#!/bin/bash
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
"""

    with open("execution/submit_nature_task1_convergence.sbatch", "w", newline="\n") as f:
        f.write(t1_sbatch)
    with open("execution/submit_nature_task2_dispersion.sbatch", "w", newline="\n") as f:
        f.write(t2_sbatch)
    with open("execution/submit_nature_task3_stability_6dof.sbatch", "w", newline="\n") as f:
        f.write(t3_sbatch)
    with open("execution/submit_nature_task4_thermal_matsubara.sbatch", "w", newline="\n") as f:
        f.write(t4_sbatch)
    with open("execution/submit_nature_master_all.sh", "w", newline="\n") as f:
        f.write(master_sh)

    print("Successfully created all Slurm sbatch and master launch scripts in execution/.")


if __name__ == "__main__":
    generate_all_nature_configs()
