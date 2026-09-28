#!/usr/bin/env python3
"""
Dual-Fractal Rotary Vacuum Casimir Clutch Configuration Suite Generator
--------------------------------------------------------------------------------
Generates the 8-task configuration suite to explore the rotary Casimir clutch
at strictly constant area-weighted average distance <d> between the plates:

Matrix of Configurations:
  1. N = 1 Fractal: theta in {0 deg, 30 deg, 45 deg, 90 deg} (Tasks 1-4)
  2. N = 3 Fractal: theta in {0 deg, 30 deg, 45 deg, 90 deg} (Tasks 5-8)

Constant Average Distance Invariance:
  For a fractal sieve membrane with aperture area fraction f_N = 1 - (8/9)^N and
  membrane feature thickness h = t_plate:
    <d> = (1 - f_N) * z_tip + f_N * (z_tip + h) = z_tip + f_N * h == d_average
    => z_tip(N) = d_average - f_N * h

Guarantees:
  - Average plate distance <d> = 20.00 nm is strictly identical across all N=1 and N=3 tasks.
  - Tip clearances z_tip(1) = 17.22 nm and z_tip(3) = 12.56 nm reside within the
    Levin-Johnson repulsive near-field regime (z_tip < W1 / 4 = 62.5 nm) while
    guaranteeing z_tip > 0 for frictionless, non-contact rotation.
  - Zero hardcoded magic variables, zero try-catch.
"""

import os
import sys
import json
import math

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


from execution.run_fractal_rotary_clutch_meep import (
    get_fractal_clutch_elements,
    compute_plate_area_fraction
)


def calculate_standoff(d_average: float, feature_depth: float, area_fraction: float) -> float:
    """Calculates tip standoff z_tip such that average distance <d> == d_average."""
    assert d_average > 0.0, f"d_average must be positive, got {d_average}"
    assert feature_depth >= 0.0, f"feature_depth must be non-negative, got {feature_depth}"
    z_tip = d_average - area_fraction * feature_depth
    assert z_tip > 0.0, f"Calculated z_tip={z_tip} must be positive!"
    # Verify reconstructed average distance to machine precision
    reconstructed_d_avg = (1.0 - area_fraction) * z_tip + area_fraction * (z_tip + feature_depth)
    assert math.isclose(reconstructed_d_avg, d_average, rel_tol=1e-12, abs_tol=1e-12)
    return z_tip


def build_fractal_clutch_suite(
    d_average_um: float = 0.020,     # Target invariant average distance: 20 nm
    t_plate_um: float = 0.025,       # Stator membrane thickness: 25 nm
    L_fractal_um: float = 1.05,      # Fractal base span: 1.05 um
    W1_aperture_um: float = 0.25,    # Primary aperture diameter: 250 nm
    w1_needle_um: float = 0.035,     # Primary needle width: 35 nm
    H_needle_um: float = 0.25,       # Needle height: 250 nm
    material: str = "Gold",
    medium: str = "Vacuum",
    resolution: int = 60,            # Cluster-proven resolution: dx = 16.67 nm (~1.2h/task on 128 cores)
    nmax: int = 1,
    T_run: float = 3.0
) -> list:
    """Constructs the list of 8 configuration dictionaries."""
    angles = [0.0, 30.0, 45.0, 90.0]
    generations = [1, 3]

    configs = []
    task_id = 1

    for N in generations:
        elements = get_fractal_clutch_elements(N, L_fractal_um, W1=W1_aperture_um, w1=w1_needle_um)
        f_area = compute_plate_area_fraction(elements, L_fractal_um)
        z_tip = calculate_standoff(d_average_um, t_plate_um, f_area)

        for theta in angles:
            if abs(theta) < 1e-3 or abs(theta - 90.0) < 1e-3:
                expected_regime = "REPULSIVE"
            elif abs(theta - 45.0) < 1e-3:
                expected_regime = "ATTRACTIVE"
            else:
                expected_regime = "TRANSITION"

            label = (
                f"DualFractalClutch: N={N}, th={theta:.1f}deg, "
                f"<d>={d_average_um*1e3:.1f}nm, z_tip={z_tip*1e3:.2f}nm, mat={material}"
            )

            cfg = {
                "task_id": task_id,
                "label": label,
                "campaign": "dual_fractal_rotary_clutch_constant_d_avg",
                "N_fractal": N,
                "theta_deg": float(theta),
                "d_average_um": float(d_average_um),
                "feature_depth_um": float(t_plate_um),
                "area_fraction": float(f_area),
                "z_tip_um": float(z_tip),
                "L_fractal_um": float(L_fractal_um),
                "W1_aperture_um": float(W1_aperture_um),
                "w1_needle_um": float(w1_needle_um),
                "H_needle_um": float(H_needle_um),
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

    return configs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Dual-Fractal Casimir Clutch Configuration Suite")
    parser.add_argument("--res", type=int, default=60, help="Yee grid resolution (default: 60 px/um, dx=16.67 nm, ~1.2h/task)")
    parser.add_argument("--d-avg", type=float, default=0.020, help="Target invariant average distance in um (default: 0.020)")
    parser.add_argument("--t-plate", type=float, default=0.025, help="Stator plate thickness in um (default: 0.025)")
    parser.add_argument("--T-run", type=float, default=3.0, help="FDTD run duration in Meep time units (default: 3.0)")
    args = parser.parse_args()

    configs = build_fractal_clutch_suite(
        d_average_um=args.d_avg,
        t_plate_um=args.t_plate,
        resolution=args.res,
        T_run=args.T_run
    )
    out_dir = os.path.join(REPO_ROOT, "sweep_configs_fractal_clutch")
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
        print(f"Generated {fname}: N={cfg['N_fractal']}, theta={cfg['theta_deg']:.1f} deg, z_tip={cfg['z_tip_um']*1e3:.2f} nm, <d>={cfg['d_average_um']*1e3:.1f} nm, res={cfg['resolution']}")

    master_path = os.path.join(out_dir, "master_fractal_clutch_suite.json")
    with open(master_path, "w", newline="\n") as f_m:
        json.dump(configs, f_m, indent=4)
    print(f"\nSuccessfully generated {len(configs)} configurations in {out_dir}")
    print(f"Master suite saved to {master_path}")


if __name__ == "__main__":
    main()
