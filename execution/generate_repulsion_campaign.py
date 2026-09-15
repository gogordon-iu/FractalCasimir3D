#!/usr/bin/env python3
"""
Vacuum Casimir Repulsion Campaign: Phase 1 Configuration Generator (36 Tasks)
-----------------------------------------------------------------------------
Generates 36 targeted simulation configurations to screen the 4 fundamental
symmetry-breaking topological archetypes in pure vacuum (eps_bg = 1.0):

1. Archetype 1: Corrugated Top (N=3) vs. Flat Bottom (N=1) [8 Tasks]
2. Archetype 2: Multi-Scale Hierarchical Corrugations (N_top=3 vs. N_bot=2) [8 Tasks]
3. Archetype 3: Perforated Carpet Waveguide Cutoff (N_top=3 vs. N_bot=1) [8 Tasks]
4. Archetype 4: Orthogonal Ridge Crossing (N_top=3, N_bot=3, theta around 90 deg) [12 Tasks]

All tasks are strictly in pure vacuum with zero synthetic sign overrides or fallbacks.
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

    # ==============================================================================
    # 1. Archetype 1: Corrugated Top (N=3) vs. Flat Bottom (N=1) [8 Tasks]
    # ==============================================================================
    d_vals_arch1 = [0.10, 0.20]  # 100 nm, 200 nm
    theta_vals_arch1 = [0.0, 85.0, 90.0, 95.0]
    for d in d_vals_arch1:
        for theta in theta_vals_arch1:
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
    # 2. Archetype 2: Multi-Scale Hierarchical Corrugations (N_top=3 vs. N_bot=2) [8 Tasks]
    # ==============================================================================
    d_vals_arch2 = [0.10, 0.20]  # 100 nm, 200 nm
    theta_vals_arch2 = [80.0, 85.0, 90.0, 95.0]
    for d in d_vals_arch2:
        for theta in theta_vals_arch2:
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

    # ==============================================================================
    # 3. Archetype 3: Perforated Carpet Waveguide Cutoff (N_top=3 vs. N_bot=1) [8 Tasks]
    # ==============================================================================
    d_vals_arch3 = [0.15, 0.30]  # 150 nm, 300 nm (cutoff range)
    theta_vals_arch3 = [0.0, 45.0, 85.0, 90.0]
    for d in d_vals_arch3:
        for theta in theta_vals_arch3:
            cfg = {
                "task_id": task_id,
                "phase": "repulsion_phase1",
                "archetype": "perforated_carpet_cutoff",
                "label": f"Arch3: Perforated Carpet Ntop=3 vs Solid Nbot=1, d={int(d*1000)}nm, th={theta:.1f}deg",
                "d": d,
                "N_top": 3,
                "N_bot": 1,
                "material": "Phosphorene_tuned",
                "resolution": 40,
                "theta": theta,
                "eps_bg": 1.0,
                "L": 2.0,
                "corrugated": False,
                "corrugation_angle": 0.0,
                "r_tip_nm": 0.0,
                "medium": "Vacuum",
                "stepped_sieve": False
            }
            tasks.append(cfg)
            task_id += 1

    # ==============================================================================
    # 4. Archetype 4: Orthogonal Ridge Crossing (N_top=3, N_bot=3) [12 Tasks]
    # ==============================================================================
    d_vals_arch4 = [0.05, 0.10]  # 50 nm, 100 nm
    theta_vals_arch4 = [80.0, 84.0, 88.0, 90.0, 92.0, 96.0]
    for d in d_vals_arch4:
        for theta in theta_vals_arch4:
            cfg = {
                "task_id": task_id,
                "phase": "repulsion_phase1",
                "archetype": "orthogonal_ridge_crossing",
                "label": f"Arch4: Cross-Corrugated Ntop=3, Nbot=3, d={int(d*1000)}nm, th={theta:.1f}deg",
                "d": d,
                "N_top": 3,
                "N_bot": 3,
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
    print("VACUUM CASIMIR REPULSION CAMPAIGN: PHASE 1 GENERATOR")
    print("================================================================================")
    print(f"Successfully generated {len(tasks)} target simulation configurations in '{config_dir}/'.")
    print("Breakdown by Archetype:")
    print("  1. Corrugated Top (N=3) vs. Flat Bottom (N=1):             8 Tasks")
    print("  2. Hierarchical Multi-Scale Corrugations (N=3 vs. N=2):    8 Tasks")
    print("  3. Perforated Carpet Waveguide Cutoff (N=3 vs. N=1):       8 Tasks")
    print("  4. Orthogonal Ridge Crossing (N=3 vs. N=3, theta ~ 90):   12 Tasks")
    print(f"Total Phase 1 Screening Tasks: {len(tasks)}")
    print("All tasks strictly configured for pure vacuum (eps_bg = 1.0).")
    print("================================================================================")

if __name__ == "__main__":
    main()
