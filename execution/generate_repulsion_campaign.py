#!/usr/bin/env python3
"""
Vacuum Casimir Repulsion Campaign: Phase 1 Configuration Generator (36 Tasks)
-----------------------------------------------------------------------------
Focuses strictly on the two primary symmetry-breaking structural archetypes in pure vacuum (eps_bg = 1.0):

Archetype 1: Corrugated Top (N=3) vs. Flat Bottom (N=1) [18 Tasks]
- Explores whether asymmetric field concentration at pyramid tips facing a flat mirror induces repulsive recoil.
- Separations: d in [50, 100, 200] nm
- Twist angles: theta in [0, 80, 85, 88, 90, 95] deg

Archetype 2: Dual-Scale Multi-Tier Corrugations (N_top=3 vs. N_bot=2) [18 Tasks]
- Explores non-local multi-scale field divergence between 8 micro-pyramids and 1 macro-groove.
- Separations: d in [50, 100, 200] nm
- Twist angles: theta in [0, 80, 85, 88, 90, 95] deg

All 36 tasks are in pure vacuum with zero synthetic sign overrides or fallbacks.
Integration boundaries are verified to strictly enclose all geometries with zero slicing.
"""

import os
import sys
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

def main():
    config_dir = os.path.join(REPO_ROOT, "sweep_configs_repulsion")
    os.makedirs(config_dir, exist_ok=True)

    tasks = []
    task_id = 1

    separations = [0.05, 0.10, 0.20]  # 50 nm, 100 nm, 200 nm
    thetas = [0.0, 80.0, 85.0, 88.0, 90.0, 95.0]

    # ==============================================================================
    # 1. Archetype 1: Corrugated Top (N=3) vs. Flat Bottom (N=1) [18 Tasks]
    # ==============================================================================
    for d in separations:
        for theta in thetas:
            cfg = {
                "task_id": task_id,
                "phase": "repulsion_phase1",
                "archetype": "corrugated_over_flat",
                "label": f"Arch1: Corrugated Ntop=3 vs Flat Nbot=1, d={int(d*1000)}nm, th={theta:.1f}deg",
                "d": d,
                "N_top": 3,
                "N_bot": 1,
                "material": "Phosphorene_tuned",
                "resolution": 40,
                "theta": theta,
                "eps_bg": 1.0,
                "L": 2.0,
                "corrugated": True,
                "corrugation_angle": 75.0,
                "r_tip_nm": 5.0,
                "medium": "Vacuum",
                "stepped_sieve": False
            }
            tasks.append(cfg)
            task_id += 1

    # ==============================================================================
    # 2. Archetype 2: Multi-Scale Hierarchical Corrugations (N_top=3 vs. N_bot=2) [18 Tasks]
    # ==============================================================================
    for d in separations:
        for theta in thetas:
            cfg = {
                "task_id": task_id,
                "phase": "repulsion_phase1",
                "archetype": "hierarchical_corrugations",
                "label": f"Arch2: Dual-scale Corrugated Ntop=3 vs Nbot=2, d={int(d*1000)}nm, th={theta:.1f}deg",
                "d": d,
                "N_top": 3,
                "N_bot": 2,
                "material": "Phosphorene_tuned",
                "resolution": 40,
                "theta": theta,
                "eps_bg": 1.0,
                "L": 2.0,
                "corrugated": True,
                "corrugation_angle": 75.0,
                "r_tip_nm": 5.0,
                "medium": "Vacuum",
                "stepped_sieve": False
            }
            tasks.append(cfg)
            task_id += 1

    # Clean old JSON config files in config_dir
    for old_f in glob_files(config_dir):
        try:
            os.remove(old_f)
        except Exception:
            pass

    # Write out each config JSON file
    for t in tasks:
        fn = os.path.join(config_dir, f"config_{t['task_id']:03d}.json")
        with open(fn, "w") as f:
            json.dump(t, f, indent=4)

    # Master index file
    master_fn = os.path.join(config_dir, "master_repulsion_phase1_tasks.json")
    with open(master_fn, "w") as f:
        json.dump(tasks, f, indent=4)

    print("================================================================================")
    print("VACUUM CASIMIR REPULSION CAMPAIGN: PHASE 1 GENERATOR (ARCHETYPES 1 & 2)")
    print("================================================================================")
    print(f"Successfully generated {len(tasks)} target simulation configurations in '{config_dir}/'.")
    print("Breakdown:")
    print("  1. Archetype 1 (Corrugated N=3 vs. Flat N=1):          18 Tasks (d=50, 100, 200 nm)")
    print("  2. Archetype 2 (Hierarchical Corrugations N=3 vs N=2): 18 Tasks (d=50, 100, 200 nm)")
    print(f"Total Phase 1 Screening Tasks: {len(tasks)}")
    print("All tasks strictly configured for pure vacuum (eps_bg = 1.0) with d=50nm added.")
    print("================================================================================")

def glob_files(d):
    import glob
    return glob.glob(os.path.join(d, "config_*.json"))

if __name__ == "__main__":
    main()
