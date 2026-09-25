#!/usr/bin/env python3
"""
Generates Parameter Sweep Configs for Geometric Vacuum Casimir Repulsion (Proposition 2)
-----------------------------------------------------------------------------------------
Sweeps tip-to-aperture separation z_tip across the critical Levin-Johnson threshold W/4.
Material: Pure Gold in Vacuum (no fluids, no metamaterials).
"""

import os
import sys
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

def main():
    cfg_dir = os.path.join(REPO_ROOT, "sweep_configs_geometric_repulsion")
    os.makedirs(cfg_dir, exist_ok=True)

    # Core Parameters from Levin et al. (PRL 2010):
    W_aperture = 0.350   # 350 nm aperture
    t_plate = 0.025      # 25 nm thin membrane (t <= 0.1 W)
    H_needle = 0.250     # 250 nm elongated needle
    w_needle = 0.040     # 40 nm needle base width (aspect ratio 6.25:1)
    W_over_4 = W_aperture / 4.0  # 0.0875 um = 87.5 nm threshold

    # 4 Characteristic Separation Distances:
    z_tips = [
        0.120,   # Task 1: z > W/4 (120 nm) -> Classical Attraction (F_z < 0)
        0.060,   # Task 2: z < W/4 (60 nm)  -> Repulsive Onset (F_z > 0)
        0.030,   # Task 3: z << W/4 (30 nm) -> Peak Repulsion (F_z > 0)
        0.010    # Task 4: z near 0 (10 nm) -> Near-mouth Repulsion (F_z > 0)
    ]

    for i, z_val in enumerate(z_tips, start=1):
        is_repulsive_expected = (z_val < W_over_4)
        cfg = {
            "task_id": i,
            "label": f"Levin_Repulsion_W_{int(W_aperture*1e3)}nm_ztip_{int(z_val*1e3)}nm",
            "campaign": "geometric_vacuum_repulsion",
            "W_aperture_um": W_aperture,
            "t_plate_um": t_plate,
            "H_needle_um": H_needle,
            "w_needle_um": w_needle,
            "z_tip_um": z_val,
            "W_over_4_um": W_over_4,
            "expected_regime": "REPULSIVE" if is_repulsive_expected else "ATTRACTIVE",
            "material": "Gold",
            "medium": "Vacuum",
            "resolution": 80,
            "nmax": 1,
            "T_run": 12.0
        }
        out_f = os.path.join(cfg_dir, f"config_{i:03d}.json")
        with open(out_f, "w") as f:
            json.dump(cfg, f, indent=4)
        print(f"Created config: {out_f} [z_tip={int(z_val*1e3)} nm, Expected: {cfg['expected_regime']}]")

if __name__ == "__main__":
    main()
