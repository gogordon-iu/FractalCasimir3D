#!/usr/bin/env python3
"""
Unified Nature Publication Campaign Generator (292 Tasks)
-------------------------------------------------------
Generates the comprehensive parameter space required for the Nature paper:
- Tier 1: General Parameters & Fundamental Casimir Baselines (28 tasks)
  * Planar uncorrugated baselines (Gold, Silicon, Phosphorene)
  * 1/d^4 Lifshitz distance scaling
  * (8/9)^(N-1) Sierpinski fractal area law
  * Optical anisotropy twist angle theta baseline
- Tier 2: Pyramid Corrugation & Corner Singularity Refutation (40 tasks)
  * Wall slope alpha in [45, 54.7, 60, 70, 75, 80, 85] deg
  * Tip rounding r_tip in [0, 2, 5, 10, 20] nm (proves repulsion is not a corner singularity)
  * Full multi-oscillator dispersion & optical loss (BlackPhosphorus, ReS2)
  * Immersion dielectric screening (Teflon_AF, Ethanol, Bromobenzene, Glycerol, Cyclohexane)
- Tier 3: Sweet Spot High-Resolution 3D Parameter Sweep (224 tasks)
  * 8 thetas in [80, 94] deg x 4 alphas in [70, 85] deg x 7 gaps in [50, 350] nm
  * Maps 3D P=0 phase boundary and passive levitation equilibrium heights d_eq
"""

import os
import json

def generate_unified_campaign():
    print("================================================================================")
    print("GENERATING UNIFIED NATURE CAMPAIGN PARAMETER RUN (292 TASKS)")
    print("================================================================================")

    config_dir = "sweep_configs_unified"
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs("execution", exist_ok=True)

    tasks = []
    task_id = 1

    # ==========================================================================
    # TIER 1: GENERAL PARAMETERS & FUNDAMENTAL BASELINES (28 tasks)
    # ==========================================================================
    print("Generating Tier 1: General Parameters & Fundamental Casimir Baselines...")
    
    # 1.1 Conventional Materials Planar Baselines (Au, cSi) at d=100nm, N=1,2,3
    for mat in ["Gold", "Silicon"]:
        for N in [1, 2, 3]:
            tasks.append({
                "task_id": task_id,
                "tier": "tier1_general_materials",
                "label": f"Planar {mat} N={N} d=100nm baseline",
                "d": 0.10,
                "N_top": N,
                "N_bot": 1,
                "material": mat,
                "resolution": 40,
                "theta": 0.0,
                "eps_bg": 1.0,
                "L": 2.0,
                "corrugated": False,
                "corrugation_angle": 0.0,
                "r_tip_nm": 0.0,
                "medium": "Vacuum",
                "stepped_sieve": False
            })
            task_id += 1

    # 1.2 Untuned Phosphorene in Vacuum (eps_bg=1.0) - Lifshitz 1/d^4 Scaling (N=1)
    for d_val in [0.05, 0.10, 0.20, 0.35]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier1_lifshitz_scaling",
            "label": f"Phosphorene planar Lifshitz scaling d={int(d_val*1000)}nm N=1",
            "d": float(d_val),
            "N_top": 1,
            "N_bot": 1,
            "material": "Phosphorene",
            "resolution": 40,
            "theta": 0.0,
            "eps_bg": 1.0,
            "L": 2.0,
            "corrugated": False,
            "corrugation_angle": 0.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 1.3 Untuned Phosphorene in Vacuum - Sierpinski Fractal Area Law (8/9)^(N-1) at d=100nm
    for N in [1, 2, 3, 4]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier1_fractal_area_law",
            "label": f"Phosphorene planar fractal area law N={N} d=100nm",
            "d": 0.10,
            "N_top": N,
            "N_bot": 1,
            "material": "Phosphorene",
            "resolution": 40,
            "theta": 0.0,
            "eps_bg": 1.0,
            "L": 2.0,
            "corrugated": False,
            "corrugation_angle": 0.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 1.4 Untuned Phosphorene in Vacuum - Twist Angle Theta Baseline (Planar uncorrugated)
    for th in [0.0, 30.0, 60.0, 90.0]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier1_theta_baseline",
            "label": f"Phosphorene planar twist baseline theta={int(th)}deg N=3 d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 1,
            "material": "Phosphorene",
            "resolution": 40,
            "theta": float(th),
            "eps_bg": 1.0,
            "L": 2.0,
            "corrugated": False,
            "corrugation_angle": 0.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 1.5 Tuned Phosphorene (eps_bg=2.1) - Planar Uncorrugated Twist Series
    for th in [0.0, 30.0, 60.0, 90.0]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier1_tuned_twist_series",
            "label": f"Tuned Phosphorene planar twist theta={int(th)}deg eps=2.1 d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 1,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": float(th),
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": False,
            "corrugation_angle": 0.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 1.6 Tuned Phosphorene (eps_bg=2.1) - Planar Uncorrugated Distance Series
    for d_val in [0.05, 0.10, 0.20, 0.35]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier1_tuned_distance_series",
            "label": f"Tuned Phosphorene planar distance d={int(d_val*1000)}nm theta=90deg",
            "d": float(d_val),
            "N_top": 3,
            "N_bot": 1,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": False,
            "corrugation_angle": 0.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 1.7 Tuned Phosphorene (eps_bg=2.1) - Size Scaling (L=0.3um, 1.0um)
    for L_val in [0.30, 1.00]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier1_size_scaling",
            "label": f"Tuned Phosphorene planar size scaling L={L_val}um d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 1,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": float(L_val),
            "corrugated": False,
            "corrugation_angle": 0.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    print(f"  -> Tier 1 generated: {task_id - 1} tasks.")

    # ==========================================================================
    # TIER 2: PYRAMID CORRUGATION & CORNER SINGULARITY REFUTATION (40 tasks)
    # ==========================================================================
    print("Generating Tier 2: Pyramid Corrugation & Corner Singularity Refutation...")
    tier2_start = task_id

    # 2.1 Wall Slope Alpha Dependence at theta=90deg, d=100nm
    for alpha_val in [45.0, 54.7, 60.0, 70.0, 75.0, 80.0, 85.0]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_alpha_dependence",
            "label": f"Corrugated pyramid alpha={alpha_val}deg theta=90deg d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 3,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": float(alpha_val),
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.2 Corrugated Distance Series for alpha=45deg
    for d_val in [0.05, 0.15, 0.25, 0.35]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_corrugated_d_series_45",
            "label": f"Corrugated pyramid alpha=45deg d={int(d_val*1000)}nm",
            "d": float(d_val),
            "N_top": 3,
            "N_bot": 3,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 45.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.3 Corrugated Distance Series for alpha=60deg
    for d_val in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_corrugated_d_series_60",
            "label": f"Corrugated pyramid alpha=60deg d={int(d_val*1000)}nm",
            "d": float(d_val),
            "N_top": 3,
            "N_bot": 3,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 60.0,
            "r_tip_nm": 0.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.4 Tip Rounding Singularity Refutation (r_tip sweep at alpha=75deg, d=100nm)
    for r_val in [0.0, 2.0, 5.0, 10.0, 20.0]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_tip_rounding_75",
            "label": f"Tip rounding r_tip={int(r_val)}nm alpha=75deg d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 3,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 75.0,
            "r_tip_nm": float(r_val),
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.5 Tip Rounding at alpha=80deg, d=100nm
    for r_val in [2.0, 5.0, 10.0, 20.0]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_tip_rounding_80",
            "label": f"Tip rounding r_tip={int(r_val)}nm alpha=80deg d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 3,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 80.0,
            "r_tip_nm": float(r_val),
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.6 Tip Rounding at alpha=75deg, d=150nm
    for r_val in [5.0, 10.0]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_tip_rounding_gap150",
            "label": f"Tip rounding r_tip={int(r_val)}nm alpha=75deg d=150nm",
            "d": 0.15,
            "N_top": 3,
            "N_bot": 3,
            "material": "Phosphorene_tuned",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 75.0,
            "r_tip_nm": float(r_val),
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.7 Material Multi-Oscillator Dispersion with Optical Loss (BlackPhosphorus)
    for d_val in [0.05, 0.10, 0.15, 0.20]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_dispersive_loss_bp",
            "label": f"Authentic dispersive BP with loss d={int(d_val*1000)}nm alpha=75deg",
            "d": float(d_val),
            "N_top": 3,
            "N_bot": 3,
            "material": "BlackPhosphorus",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 75.0,
            "r_tip_nm": 5.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.8 Material Dispersion: Rhenium Disulfide (ReS2)
    for d_val in [0.05, 0.10]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_dispersive_res2",
            "label": f"Authentic dispersive ReS2 d={int(d_val*1000)}nm alpha=75deg",
            "d": float(d_val),
            "N_top": 3,
            "N_bot": 3,
            "material": "ReS2",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 2.1,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 75.0,
            "r_tip_nm": 5.0,
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        task_id += 1

    # 2.9 Liquid Immersion Screening (Nature Reviewer 2)
    for med in ["Teflon_AF", "Ethanol", "Bromobenzene", "Glycerol", "Cyclohexane"]:
        tasks.append({
            "task_id": task_id,
            "tier": "tier2_liquid_immersion",
            "label": f"Liquid immersion screening medium={med} alpha=75deg d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 3,
            "material": "BlackPhosphorus",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 1.0,  # Will be dynamically set to liquid eps_static
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 75.0,
            "r_tip_nm": 5.0,
            "medium": med,
            "stepped_sieve": False
        })
        task_id += 1

    print(f"  -> Tier 2 generated: {task_id - tier2_start} tasks.")

    # ==========================================================================
    # TIER 3: SWEET SPOT HIGH-RESOLUTION 3D PARAMETER SWEEP (224 tasks)
    # ==========================================================================
    print("Generating Tier 3: Sweet Spot High-Resolution 3D Parameter Sweep...")
    tier3_start = task_id

    thetas = [80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0, 94.0]
    alphas = [70.0, 75.0, 80.0, 85.0]
    ds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]

    for a in alphas:
        for th in thetas:
            for d in ds:
                tasks.append({
                    "task_id": task_id,
                    "tier": "tier3_sweet_spot_grid",
                    "label": f"Sweet spot alpha={a:.1f}deg theta={th:.1f}deg d={int(d*1000)}nm",
                    "d": float(d),
                    "N_top": 3,
                    "N_bot": 3,
                    "material": "Phosphorene_tuned",
                    "resolution": 40,
                    "theta": float(th),
                    "eps_bg": 2.1,
                    "L": 2.0,
                    "corrugated": True,
                    "corrugation_angle": float(a),
                    "r_tip_nm": 5.0,  # Realistic nanofabricated tip rounding
                    "medium": "Vacuum",
                    "stepped_sieve": False
                })
                task_id += 1

    total_tasks = len(tasks)
    print(f"  -> Tier 3 generated: {task_id - tier3_start} tasks.")
    print(f"Total unified campaign tasks: {total_tasks}")

    # Write all JSON config files
    for t in tasks:
        cfg_path = os.path.join(config_dir, f"config_{t['task_id']:03d}.json")
        with open(cfg_path, "w") as f:
            json.dump(t, f, indent=4)

    print(f"Successfully serialized {total_tasks} configuration files in '{config_dir}/'.")

    # ==========================================================================
    # SLURM JOB ARRAY SCRIPT (execution/submit_unified_nature_array.sbatch)
    # ==========================================================================
    sbatch_content = f"""#!/bin/bash
#SBATCH -J casimir_nature_unified
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time=12:00:00
#SBATCH --array=1-{total_tasks}%16
#SBATCH -o .tmp/nature_unified_%A_%a.out
#SBATCH -e .tmp/nature_unified_%A_%a.err

echo "================================================================================"
echo "UNIFIED NATURE CAMPAIGN TASK: $SLURM_ARRAY_TASK_ID / {total_tasks}"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

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

# Load Task Configuration
CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="sweep_configs_unified/config_${{CFG_INDEX}}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file $CONFIG_FILE not found!"
    exit 1
fi

echo "Reading task parameters from $CONFIG_FILE..."
TIER=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['tier'])")
LABEL=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['label'])")
ALPHA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['corrugation_angle'])")
THETA=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['theta'])")
D_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['d'])")
L_UM=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['L'])")
RES=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['resolution'])")
EPS=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['eps_bg'])")
MAT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['material'])")
NTOP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N_top'])")
NBOT=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['N_bot'])")
CORR=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['corrugated'])")
RTIP=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['r_tip_nm'])")
MED=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['medium'])")
SIEVE=$($PYTHON_EXEC -c "import json; print(json.load(open('$CONFIG_FILE'))['stepped_sieve'])")

echo "Executing [$TIER]: $LABEL"
echo "Params: d=$D_UM um, N=($NTOP,$NBOT), mat=$MAT, res=$RES, theta=$THETA deg, alpha=$ALPHA deg, r_tip=$RTIP nm, med=$MED"

EXTRA_ARGS=""
if [ "$CORR" = "True" ] || [ "$CORR" = "true" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --corrugated --corrugation-angle $ALPHA --r-tip $RTIP"
fi
if [ "$SIEVE" = "True" ] || [ "$SIEVE" = "true" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --stepped-sieve"
fi
if [ "$MED" != "None" ] && [ "$MED" != "Vacuum" ] && [ -n "$MED" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --medium $MED"
fi

bash execution/run_meep_wrapper.sh $PYTHON_EXEC execution/run_meep_simulation.py \\
    --L $L_UM \\
    --d $D_UM \\
    --N $NTOP \\
    --N-bottom $NBOT \\
    --theta $THETA \\
    --material $MAT \\
    --res $RES \\
    --eps-bg $EPS \\
    --config all \\
    --task-idx $SLURM_ARRAY_TASK_ID \\
    $EXTRA_ARGS

EXIT_CODE=$?
echo "Task $SLURM_ARRAY_TASK_ID completed with exit code $EXIT_CODE at $(date)."
exit $EXIT_CODE
"""

    sbatch_file = os.path.join("execution", "submit_unified_nature_array.sbatch")
    with open(sbatch_file, "w", newline="\n") as f:
        f.write(sbatch_content)
    print(f"Generated Slurm job array script: '{sbatch_file}'.")

    # ==========================================================================
    # SLURM ANALYZER SBATCH SCRIPT (execution/submit_unified_nature_analyzer.sbatch)
    # ==========================================================================
    analyzer_sbatch = """#!/bin/bash
#SBATCH -J casimir_nature_analyzer
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --time=02:00:00
#SBATCH -o .tmp/nature_analyzer_%j.out
#SBATCH -e .tmp/nature_analyzer_%j.err

echo "================================================================================"
echo "UNIFIED NATURE CAMPAIGN POST-SIMULATION ANALYZER"
echo "Host: $(hostname)"
echo "Started: $(date)"
echo "================================================================================"

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

echo "Executing Unified Nature Analyzer..."
$PYTHON_EXEC execution/run_unified_nature_analyzer.py

echo "Analysis complete at $(date)."
"""

    analyzer_sbatch_file = os.path.join("execution", "submit_unified_nature_analyzer.sbatch")
    with open(analyzer_sbatch_file, "w", newline="\n") as f:
        f.write(analyzer_sbatch)
    print(f"Generated Slurm analyzer script: '{analyzer_sbatch_file}'.")

    # ==========================================================================
    # MASTER LAUNCHER SCRIPT (execution/submit_unified_nature_master.sh)
    # ==========================================================================
    master_sh = f"""#!/bin/bash
# Master Launcher Script for Unified Nature Campaign (292 Tasks) & Automated Analyzer

echo "================================================================================"
echo "LAUNCHING UNIFIED NATURE PUBLICATION RUN (292 TASKS) ON BIGRED 200"
echo "================================================================================"

mkdir -p .tmp

# Submit Job Array
ARRAY_SUBMIT=$(sbatch execution/submit_unified_nature_array.sbatch)
echo "$ARRAY_SUBMIT"

ARRAY_ID=$(echo "$ARRAY_SUBMIT" | awk '{{print $4}}')
if [ -z "$ARRAY_ID" ]; then
    echo "ERROR: Failed to obtain Slurm Job Array ID!"
    exit 1
fi

echo "Submitted Job Array ID: $ARRAY_ID"

# Submit Dependent Analyzer Job (afterok)
echo "Submitting Dependent Analyzer (afterok:$ARRAY_ID)..."
ANALYZER_SUBMIT=$(sbatch --dependency=afterok:$ARRAY_ID execution/submit_unified_nature_analyzer.sbatch)
echo "$ANALYZER_SUBMIT"

echo "================================================================================"
echo "SUCCESS: Entire Unified Nature Campaign Enqueued on BigRed 200!"
echo "Array ID: $ARRAY_ID"
echo "Monitor status with: squeue -u $USER"
echo "================================================================================"
"""

    master_file = os.path.join("execution", "submit_unified_nature_master.sh")
    with open(master_file, "w", newline="\n") as f:
        f.write(master_sh)
    print(f"Generated Master Launcher script: '{master_file}'.")
    print("================================================================================")
    print("ALL 292 CONFIGS AND SCRIPTS SUCCESSFULLY GENERATED!")
    print("================================================================================")

if __name__ == "__main__":
    generate_unified_campaign()
