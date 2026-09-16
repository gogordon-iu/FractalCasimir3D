#!/usr/bin/env python3
"""
Fractal Quantum Clutch Campaign Generator
-----------------------------------------
Generates the minimal 10-task configuration suite to demonstrate the complete
Quantum Clutch: rotation-driven switching from Casimir Repulsion (P > 0) to
Attraction (P < 0) in pure vacuum (eps_bg = 1.0).

Parameter Grid:
- Gaps: d in [40 nm, 80 nm]
- Twist angles: theta in [0.0, 30.0, 45.0, 60.0, 90.0] deg
- Total Tasks: 2 * 5 = 10 Tasks
"""

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "sweep_configs_clutch")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    gaps = [0.04, 0.08]  # um (40 nm, 80 nm)
    thetas = [0.0, 30.0, 45.0, 60.0, 90.0]  # deg

    task_list = []
    task_id = 1

    for d in gaps:
        for th in thetas:
            task = {
                "task_id": task_id,
                "label": f"Clutch: Menger Spire (N=3) vs Sierpinski Sieve (N=3), d={int(d*1000)}nm, th={th:.1f}deg",
                "campaign": "quantum_clutch",
                "d": d,
                "N_top": 3,
                "N_bot": 3,
                "corrugated": False,
                "clutch": True,
                "stepped_sieve": False,
                "corrugation_angle": 75.0,
                "r_tip_nm": 5.0,
                "theta": th,
                "material": "Gold",
                "medium": "Vacuum",
                "eps_bg": 1.0,
                "L": 2.0,
                "resolution": 80,
                "nmax": 5
            }
            task_list.append(task)
            
            cfg_path = os.path.join(OUTPUT_DIR, f"config_{task_id:03d}.json")
            with open(cfg_path, "w") as f:
                json.dump(task, f, indent=4)
            task_id += 1

    master_path = os.path.join(OUTPUT_DIR, "master_clutch_tasks.json")
    with open(master_path, "w") as f:
        json.dump(task_list, f, indent=4)

    print("=" * 80)
    print("FRACTAL QUANTUM CLUTCH CAMPAIGN GENERATOR")
    print("=" * 80)
    print(f"Generated {len(task_list)} task configurations in '{OUTPUT_DIR}'.")
    for t in task_list:
        print(f"  Task {t['task_id']:2d} | gap={int(t['d']*1000):2d}nm | th={t['theta']:4.1f}deg | {t['label']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
