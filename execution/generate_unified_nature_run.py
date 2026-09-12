#!/usr/bin/env python3
"""
Unified Nature Publication Campaign Generator (Phases 1, 2, 3 & Master Unified)
-----------------------------------------------------------------------------
Generates the comprehensive parameter space required for the Nature paper:
- Phase 1: General Parameters & Fundamental Casimir Baselines (28 tasks)
  * Planar uncorrugated baselines (Gold, Silicon, Phosphorene)
  * 1/d^4 Lifshitz distance scaling
  * (8/9)^(N-1) Sierpinski fractal area law
  * Optical anisotropy twist angle theta baseline
- Phase 2: Pyramid Corrugation & Reviewer Defenses (40 tasks)
  * Integrated physical rounded tips (r_tip = 5.0 nm) across all corrugated runs!
  * Wall slope alpha in [45, 54.7, 60, 70, 75, 80, 85] deg
  * Tip rounding singularity refutation sweep r_tip in [0, 2, 5, 10, 20] nm
  * Full multi-oscillator dispersion & optical loss (BlackPhosphorus, ReS2)
  * Immersion dielectric screening (Teflon_AF, Ethanol, Bromobenzene, Glycerol, Cyclohexane)
- Phase 3: Sweet Spot High-Resolution 3D Parameter Sweep (224 tasks)
  * 8 thetas in [80, 94] deg x 4 alphas in [70, 85] deg x 7 gaps in [50, 350] nm
  * All corrugated runs integrated with realistic nanofabricated tip rounding r_tip = 5.0 nm
  * Maps 3D P=0 phase boundary and passive levitation equilibrium heights d_eq

Separates into 3 dedicated Slurm jobs with user email notifications (END, FAIL)
so the user gets notified immediately as each phase concludes.
"""

import os
import json

def generate_campaign():
    print("================================================================================")
    print("GENERATING NATURE PUBLICATION CAMPAIGN: PHASES 1, 2, AND 3")
    print("================================================================================")

    p1_dir = "sweep_configs_phase1"
    p2_dir = "sweep_configs_phase2"
    p3_dir = "sweep_configs_phase3"
    unified_dir = "sweep_configs_unified"

    for d in [p1_dir, p2_dir, p3_dir, unified_dir, "execution"]:
        os.makedirs(d, exist_ok=True)

    # ==========================================================================
    # PHASE 1: GENERAL PARAMETERS & FUNDAMENTAL BASELINES (28 tasks)
    # ==========================================================================
    print("Generating Phase 1: General Parameters & Fundamental Casimir Baselines (28 tasks)...")
    p1_tasks = []
    t_id = 1

    # 1.1 Conventional Materials Planar Baselines (Au, cSi) at d=100nm, N=1,2,3
    for mat in ["Gold", "Silicon"]:
        for N in [1, 2, 3]:
            p1_tasks.append({
                "task_id": t_id,
                "tier": "tier1_general_materials",
                "phase": 1,
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
            t_id += 1

    # 1.2 Untuned Phosphorene in Vacuum (eps_bg=1.0) - Lifshitz 1/d^4 Scaling (N=1)
    for d_val in [0.05, 0.10, 0.20, 0.35]:
        p1_tasks.append({
            "task_id": t_id,
            "tier": "tier1_lifshitz_scaling",
            "phase": 1,
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
        t_id += 1

    # 1.3 Untuned Phosphorene in Vacuum - Sierpinski Fractal Area Law (8/9)^(N-1) at d=100nm
    for N in [1, 2, 3, 4]:
        p1_tasks.append({
            "task_id": t_id,
            "tier": "tier1_fractal_area_law",
            "phase": 1,
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
        t_id += 1

    # 1.4 Untuned Phosphorene in Vacuum - Twist Angle Theta Baseline
    for th in [0.0, 30.0, 60.0, 90.0]:
        p1_tasks.append({
            "task_id": t_id,
            "tier": "tier1_theta_baseline",
            "phase": 1,
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
        t_id += 1

    # 1.5 Tuned Phosphorene (eps_bg=2.1) - Planar Uncorrugated Twist Series
    for th in [0.0, 30.0, 60.0, 90.0]:
        p1_tasks.append({
            "task_id": t_id,
            "tier": "tier1_tuned_twist_series",
            "phase": 1,
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
        t_id += 1

    # 1.6 Tuned Phosphorene (eps_bg=2.1) - Planar Uncorrugated Distance Series
    for d_val in [0.05, 0.10, 0.20, 0.35]:
        p1_tasks.append({
            "task_id": t_id,
            "tier": "tier1_tuned_distance_series",
            "phase": 1,
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
        t_id += 1

    # 1.7 Tuned Phosphorene (eps_bg=2.1) - Size Scaling (L=0.3um, 1.0um)
    for L_val in [0.30, 1.00]:
        p1_tasks.append({
            "task_id": t_id,
            "tier": "tier1_size_scaling",
            "phase": 1,
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
        t_id += 1

    for i, t in enumerate(p1_tasks, 1):
        cfg_path = os.path.join(p1_dir, f"config_{i:03d}.json")
        with open(cfg_path, "w") as f:
            json.dump(t, f, indent=4)
    print(f"  -> Phase 1 serialized: {len(p1_tasks)} configs in '{p1_dir}/'.")

    # ==========================================================================
    # PHASE 2: PYRAMID CORRUGATIONS & REVIEWER DEFENSES (40 tasks)
    # Physical rounded tips (r_tip = 5.0 nm) integrated into ALL corrugated runs!
    # ==========================================================================
    print("Generating Phase 2: Pyramid Corrugation & Reviewer Defenses (40 tasks)...")
    p2_tasks = []
    p2_id = 1

    # 2.1 Wall Slope Alpha Dependence with physical rounded tips r_tip = 5.0 nm
    for alpha_val in [45.0, 54.7, 60.0, 70.0, 75.0, 80.0, 85.0]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_alpha_dependence",
            "phase": 2,
            "label": f"Corrugated pyramid alpha={alpha_val}deg r_tip=5nm theta=90deg d=100nm",
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
            "r_tip_nm": 5.0,  # Physical rounded tips integrated
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        p2_id += 1

    # 2.2 Corrugated Distance Series for alpha=45deg with r_tip = 5.0 nm
    for d_val in [0.05, 0.15, 0.25, 0.35]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_corrugated_d_series_45",
            "phase": 2,
            "label": f"Corrugated pyramid alpha=45deg r_tip=5nm d={int(d_val*1000)}nm",
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
            "r_tip_nm": 5.0,  # Physical rounded tips integrated
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        p2_id += 1

    # 2.3 Corrugated Distance Series for alpha=60deg with r_tip = 5.0 nm
    for d_val in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_corrugated_d_series_60",
            "phase": 2,
            "label": f"Corrugated pyramid alpha=60deg r_tip=5nm d={int(d_val*1000)}nm",
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
            "r_tip_nm": 5.0,  # Physical rounded tips integrated
            "medium": "Vacuum",
            "stepped_sieve": False
        })
        p2_id += 1

    # 2.4 Explicit Tip Rounding Singularity Refutation (r_tip in [0, 2, 5, 10, 20] nm)
    for r_val in [0.0, 2.0, 5.0, 10.0, 20.0]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_tip_rounding_75",
            "phase": 2,
            "label": f"Tip rounding singularity test r_tip={int(r_val)}nm alpha=75deg d=100nm",
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
        p2_id += 1

    # 2.5 Tip Rounding at alpha=80deg, d=100nm
    for r_val in [2.0, 5.0, 10.0, 20.0]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_tip_rounding_80",
            "phase": 2,
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
        p2_id += 1

    # 2.6 Tip Rounding at alpha=75deg, d=150nm
    for r_val in [5.0, 10.0]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_tip_rounding_gap150",
            "phase": 2,
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
        p2_id += 1

    # 2.7 Multi-Oscillator Dispersion with Optical Loss (BlackPhosphorus, r_tip = 5.0 nm)
    for d_val in [0.05, 0.10, 0.15, 0.20]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_dispersive_loss_bp",
            "phase": 2,
            "label": f"Authentic dispersive BP with loss r_tip=5nm d={int(d_val*1000)}nm",
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
        p2_id += 1

    # 2.8 Material Dispersion: Rhenium Disulfide (ReS2, r_tip = 5.0 nm)
    for d_val in [0.05, 0.10]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_dispersive_res2",
            "phase": 2,
            "label": f"Authentic dispersive ReS2 r_tip=5nm d={int(d_val*1000)}nm",
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
        p2_id += 1

    # 2.9 Liquid Immersion Screening (Nature Reviewer 2, r_tip = 5.0 nm)
    for med in ["Teflon_AF", "Ethanol", "Bromobenzene", "Glycerol", "Cyclohexane"]:
        p2_tasks.append({
            "task_id": p2_id,
            "tier": "tier2_liquid_immersion",
            "phase": 2,
            "label": f"Liquid immersion medium={med} r_tip=5nm d=100nm",
            "d": 0.10,
            "N_top": 3,
            "N_bot": 3,
            "material": "BlackPhosphorus",
            "resolution": 40,
            "theta": 90.0,
            "eps_bg": 1.0,
            "L": 2.0,
            "corrugated": True,
            "corrugation_angle": 75.0,
            "r_tip_nm": 5.0,
            "medium": med,
            "stepped_sieve": False
        })
        p2_id += 1

    for i, t in enumerate(p2_tasks, 1):
        cfg_path = os.path.join(p2_dir, f"config_{i:03d}.json")
        with open(cfg_path, "w") as f:
            json.dump(t, f, indent=4)
    print(f"  -> Phase 2 serialized: {len(p2_tasks)} configs in '{p2_dir}/'.")

    # ==========================================================================
    # PHASE 3: SWEET SPOT HIGH-RESOLUTION 3D PARAMETER SWEEP (224 tasks)
    # All corrugated runs with r_tip = 5.0 nm
    # ==========================================================================
    print("Generating Phase 3: Sweet Spot High-Resolution 3D Sweep (224 tasks)...")
    p3_tasks = []
    p3_id = 1

    thetas = [80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0, 94.0]
    alphas = [70.0, 75.0, 80.0, 85.0]
    ds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]

    for a in alphas:
        for th in thetas:
            for d in ds:
                p3_tasks.append({
                    "task_id": p3_id,
                    "tier": "tier3_sweet_spot_grid",
                    "phase": 3,
                    "label": f"Sweet spot alpha={a:.1f}deg theta={th:.1f}deg r_tip=5nm d={int(d*1000)}nm",
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
                    "r_tip_nm": 5.0,  # Physical rounded tips integrated into all sweet spot runs
                    "medium": "Vacuum",
                    "stepped_sieve": False
                })
                p3_id += 1

    for i, t in enumerate(p3_tasks, 1):
        cfg_path = os.path.join(p3_dir, f"config_{i:03d}.json")
        with open(cfg_path, "w") as f:
            json.dump(t, f, indent=4)
    print(f"  -> Phase 3 serialized: {len(p3_tasks)} configs in '{p3_dir}/'.")

    # Serialize Unified Master Index (292 tasks)
    all_tasks = p1_tasks + p2_tasks + p3_tasks
    for i, t in enumerate(all_tasks, 1):
        t_master = dict(t)
        t_master["master_task_id"] = i
        cfg_path = os.path.join(unified_dir, f"config_{i:03d}.json")
        with open(cfg_path, "w") as f:
            json.dump(t_master, f, indent=4)
    print(f"  -> Master Unified serialized: {len(all_tasks)} configs in '{unified_dir}/'.")

    # ==========================================================================
    # SLURM ARRAY GENERATOR HELPER
    # ==========================================================================
    def build_sbatch(job_name, total, cfg_folder, time_limit, throttle=16):
        return f"""#!/bin/bash
#SBATCH -J {job_name}
#SBATCH -p general
#SBATCH -A r01540
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128
#SBATCH --time={time_limit}
#SBATCH --array=1-{total}%{throttle}
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=gogordon@iu.edu
#SBATCH -o .tmp/{job_name}_%A_%a.out
#SBATCH -e .tmp/{job_name}_%A_%a.err

echo "================================================================================"
echo "{job_name.upper()} TASK: $SLURM_ARRAY_TASK_ID / {total}"
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
mkdir -p .tmp

CFG_INDEX=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
CONFIG_FILE="{cfg_folder}/config_${{CFG_INDEX}}.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file $CONFIG_FILE not found!"
    exit 1
fi

echo "Reading task parameters from $CONFIG_FILE..."
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

echo "Executing: $LABEL"
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

    # Generate Phase 1 sbatch
    with open("execution/submit_phase1_baselines.sbatch", "w", newline="\n") as f:
        f.write(build_sbatch("casimir_p1_baselines", len(p1_tasks), p1_dir, "04:00:00", throttle=14))
    print("Generated 'execution/submit_phase1_baselines.sbatch'.")

    # Generate Phase 2 sbatch
    with open("execution/submit_phase2_corrugations.sbatch", "w", newline="\n") as f:
        f.write(build_sbatch("casimir_p2_pyramids", len(p2_tasks), p2_dir, "08:00:00", throttle=10))
    print("Generated 'execution/submit_phase2_corrugations.sbatch'.")

    # Generate Phase 3 sbatch
    with open("execution/submit_phase3_sweet_spot.sbatch", "w", newline="\n") as f:
        f.write(build_sbatch("casimir_p3_sweetspot", len(p3_tasks), p3_dir, "12:00:00", throttle=16))
    print("Generated 'execution/submit_phase3_sweet_spot.sbatch'.")

    # Generate Unified Array sbatch
    with open("execution/submit_unified_nature_array.sbatch", "w", newline="\n") as f:
        f.write(build_sbatch("casimir_nature_unified", len(all_tasks), unified_dir, "12:00:00", throttle=16))
    print("Generated 'execution/submit_unified_nature_array.sbatch'.")

    # ==========================================================================
    # LAUNCHER SHELL SCRIPTS FOR INDIVIDUAL PHASES
    # ==========================================================================
    for p_num, sbatch_name in [(1, "submit_phase1_baselines.sbatch"), (2, "submit_phase2_corrugations.sbatch"), (3, "submit_phase3_sweet_spot.sbatch")]:
        launcher_content = f"""#!/bin/bash
# Standalone Launcher for Phase {p_num} on BigRed 200

echo "================================================================================"
echo "LAUNCHING PHASE {p_num} ON BIGRED 200"
echo "================================================================================"

mkdir -p .tmp

SUBMIT_OUT=$(sbatch execution/{sbatch_name})
echo "$SUBMIT_OUT"

JOB_ID=$(echo "$SUBMIT_OUT" | awk '{{print $4}}')
if [ -z "$JOB_ID" ]; then
    echo "ERROR: Failed to launch Phase {p_num}!"
    exit 1
fi

echo "Phase {p_num} Job Array Enqueued: $JOB_ID"
echo "Slurm will email gogordon@iu.edu when Phase {p_num} finishes."
echo "Check queue with: squeue -u $USER"
echo "================================================================================"
"""
        with open(f"execution/submit_phase{p_num}.sh", "w", newline="\n") as f:
            f.write(launcher_content)
        print(f"Generated 'execution/submit_phase{p_num}.sh'.")

    # ==========================================================================
    # PIPELINED MASTER LAUNCHER (Chained with notifications upon each completion)
    # ==========================================================================
    pipelined_sh = """#!/bin/bash
# Pipelined Master Launcher for All 3 Phases with Sequential Dependencies & Notifications

echo "================================================================================"
echo "ENQUEUING ALL 3 PHASES WITH SLURM CHAINING & INDIVIDUAL NOTIFICATIONS"
echo "================================================================================"

mkdir -p .tmp

# 1. Enqueue Phase 1 (Baselines)
P1_OUT=$(sbatch execution/submit_phase1_baselines.sbatch)
echo "$P1_OUT"
P1_ID=$(echo "$P1_OUT" | awk '{print $4}')
if [ -z "$P1_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 1!"
    exit 1
fi
echo "Phase 1 Array Enqueued: $P1_ID"

# 2. Enqueue Phase 2 (Pyramids & Defenses, dependent on Phase 1)
P2_OUT=$(sbatch --dependency=afterok:$P1_ID execution/submit_phase2_corrugations.sbatch)
echo "$P2_OUT"
P2_ID=$(echo "$P2_OUT" | awk '{print $4}')
if [ -z "$P2_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 2!"
    exit 1
fi
echo "Phase 2 Array Enqueued (afterok:$P1_ID): $P2_ID"

# 3. Enqueue Phase 3 (Sweet Spot Sweep, dependent on Phase 2)
P3_OUT=$(sbatch --dependency=afterok:$P2_ID execution/submit_phase3_sweet_spot.sbatch)
echo "$P3_OUT"
P3_ID=$(echo "$P3_OUT" | awk '{print $4}')
if [ -z "$P3_ID" ]; then
    echo "ERROR: Failed to enqueue Phase 3!"
    exit 1
fi
echo "Phase 3 Array Enqueued (afterok:$P2_ID): $P3_ID"

# 4. Enqueue Master Analyzer (dependent on Phase 3)
ANALYZER_OUT=$(sbatch --dependency=afterok:$P3_ID execution/submit_unified_nature_analyzer.sbatch)
echo "$ANALYZER_OUT"
ANALYZER_ID=$(echo "$ANALYZER_OUT" | awk '{print $4}')
echo "Master Analyzer Enqueued (afterok:$P3_ID): $ANALYZER_ID"

echo "================================================================================"
echo "SUCCESS: All 3 Phases Chained and Active!"
echo "Notifications: Slurm will email gogordon@iu.edu when Phase 1 finishes,"
echo "               allowing you to inspect Phase 1 while Phase 2 runs,"
echo "               and again when Phase 2 finishes while Phase 3 runs."
echo "Check queue with: squeue -u $USER"
echo "================================================================================"
"""

    with open("execution/submit_all_phases_pipelined.sh", "w", newline="\n") as f:
        f.write(pipelined_sh)
    print("Generated 'execution/submit_all_phases_pipelined.sh'.")
    print("================================================================================")
    print("CAMPAIGN GENERATION COMPLETE!")
    print("================================================================================")

if __name__ == "__main__":
    generate_campaign()
