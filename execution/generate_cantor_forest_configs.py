#!/usr/bin/env python3
"""
Sierpinski-Cantor Forest Configuration Suite Generator
-------------------------------------------------------
Generates the EXACT 8-task configuration suite for BigRed 200, matching
the currently running needle architecture (Dual-Fractal Rotary Casimir Clutch):
- EXACT same angles: theta in {0.0 deg, 30.0 deg, 45.0 deg, 90.0 deg}
- EXACT same distances: <d> = 20.0 nm, z_tip(1) = 15.55 nm, z_tip(3) = 14.94 nm
- EXACT same dimensions: L = 1.05 um, W1 = 250 nm, w1 = 35 nm, H = 250 nm, t = 25 nm
- EXACT same number of tasks: 8 tasks (Tasks 1-4: N=1, Tasks 5-8: N=3)
- EXACT same materials & solver: Gold in Vacuum, R = 60 px/um, nmax = 1, T_run = 12.0
"""

import os
import sys
import json
import math

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from execution.cantor_forest_geometry import (
    get_sierpinski_cantor_elements,
    compute_sieve_area_fractions
)


def calculate_standoff(d_average: float, feature_depth: float, area_fraction: float) -> float:
    """Calculates tip standoff z_tip such that average distance <d> == d_average."""
    assert d_average > 0.0, f"d_average must be positive, got {d_average}"
    assert feature_depth >= 0.0, f"feature_depth must be non-negative, got {feature_depth}"
    z_tip = d_average - area_fraction * feature_depth
    assert z_tip > 0.0, f"Calculated z_tip={z_tip} must be positive!"
    reconstructed_d_avg = (1.0 - area_fraction) * z_tip + area_fraction * (z_tip + feature_depth)
    assert math.isclose(reconstructed_d_avg, d_average, rel_tol=1e-12, abs_tol=1e-12)
    return z_tip


def build_cantor_forest_suite(
    d_average_um: float = 0.020,     # Target invariant average distance: 20 nm
    t_plate_um: float = 0.025,       # Stator membrane thickness: 25 nm
    L_fractal_um: float = 1.05,      # Base domain span: 1.05 um
    W1_aperture_um: float = 0.250,   # Primary aperture width: 250 nm
    w1_pillar_um: float = 0.035,     # Primary pillar width: 35 nm
    H_pillar_um: float = 0.250,      # Pillar height: 250 nm
    material: str = "Gold",
    medium: str = "Vacuum",
    resolution: int = 60,            # R = 60 px/um (dx = 16.67 nm)
    nmax: int = 1,
    T_run: float = 12.0,
    match_needle_ztip: bool = True   # Exactly match needle z_tip values (15.548 nm and 14.943 nm)
) -> list:
    """
    Constructs the list of exactly 8 configuration dictionaries matching the needle clutch suite.
    """
    angles = [0.0, 30.0, 45.0, 90.0]
    generations = [1, 3]

    # Stored needle z_tip values for exact 1:1 distance pairing
    needle_ztips = {
        1: 0.015547629459198138,  # 15.55 nm
        3: 0.014942986546249738   # 14.94 nm
    }

    configs = []
    task_id = 1

    for N in generations:
        elements = get_sierpinski_cantor_elements(N, L_fractal_um, W1_aperture_um, w1_pillar_um)
        af = compute_sieve_area_fractions(elements, L_fractal_um)
        f_area = af["aperture_area_fraction"]

        if match_needle_ztip:
            z_tip = needle_ztips[N]
        else:
            z_tip = calculate_standoff(d_average_um, t_plate_um, f_area)

        num_pillars = len(elements)  # 1 for N=1, 73 for N=3

        for theta in angles:
            if abs(theta) < 1e-3 or abs(theta - 90.0) < 1e-3:
                expected_regime = "REPULSIVE"
            elif abs(theta - 45.0) < 1e-3:
                expected_regime = "ATTRACTIVE"
            else:
                expected_regime = "TRANSITION"

            label = (
                f"CantorForest: N={N} ({num_pillars} pillars), th={theta:.1f}deg, "
                f"<d>={d_average_um*1e3:.1f}nm, z_tip={z_tip*1e3:.2f}nm, mat={material}"
            )

            cfg = {
                "task_id": task_id,
                "label": label,
                "campaign": "sierpinski_cantor_forest_constant_d_avg",
                "N_fractal": N,
                "num_pillars": num_pillars,
                "theta_deg": float(theta),
                "d_average_um": float(d_average_um),
                "feature_depth_um": float(t_plate_um),
                "area_fraction": float(f_area),
                "z_tip_um": float(z_tip),
                "L_fractal_um": float(L_fractal_um),
                "W1_aperture_um": float(W1_aperture_um),
                "w1_pillar_um": float(w1_pillar_um),
                "H_pillar_um": float(H_pillar_um),
                "t_plate_um": float(t_plate_um),
                "expected_regime": expected_regime,
                "material": str(material),
                "medium": str(medium),
                "resolution": int(resolution),
                "nmax": int(nmax),
                "T_run": float(T_run)
            }
            configs.append(cfg)
            task_id += 1

    assert len(configs) == 8, f"Expected exactly 8 tasks, got {len(configs)}"
    return configs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Sierpinski-Cantor Forest 8-Task Configuration Suite")
    parser.add_argument("--res", type=int, default=60, help="Grid resolution (default: 60 px/um)")
    parser.add_argument("--d-avg", type=float, default=0.020, help="Average distance in um (default: 0.020)")
    parser.add_argument("--t-plate", type=float, default=0.025, help="Stator plate thickness in um (default: 0.025)")
    args = parser.parse_args()

    configs = build_cantor_forest_suite(
        d_average_um=args.d_avg,
        t_plate_um=args.t_plate,
        resolution=args.res
    )

    out_dir = os.path.join(REPO_ROOT, "sweep_configs_cantor_forest")
    os.makedirs(out_dir, exist_ok=True)

    # Clean old configs
    for old_f in os.listdir(out_dir):
        if old_f.endswith(".json"):
            os.remove(os.path.join(out_dir, old_f))

    for cfg in configs:
        tid = cfg["task_id"]
        fname = os.path.join(out_dir, f"config_{tid:03d}.json")
        with open(fname, "w", newline="\n") as f_out:
            json.dump(cfg, f_out, indent=4)
        print(f"Task {tid:02d}: N={cfg['N_fractal']} ({cfg['num_pillars']:2d} pillars), theta={cfg['theta_deg']:4.1f} deg, z_tip={cfg['z_tip_um']*1e3:.2f} nm, <d>={cfg['d_average_um']*1e3:.1f} nm, res={cfg['resolution']}")

    master_path = os.path.join(out_dir, "master_cantor_forest_suite.json")
    with open(master_path, "w", newline="\n") as f_m:
        json.dump(configs, f_m, indent=4)

    print(f"\nSuccessfully generated EXACT {len(configs)} configurations in {out_dir}")
    print(f"Master suite saved to {master_path}")


if __name__ == "__main__":
    main()
