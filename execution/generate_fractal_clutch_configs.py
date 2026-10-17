#!/usr/bin/env python3
"""
Dual-Fractal Rotary Vacuum Casimir Clutch Configuration Suite Generator
--------------------------------------------------------------------------------
Generates configurations for N in {1, 3} and theta in {0, 30, 45, 90} degrees.

Each requested distance is the invariant area-weighted average plate distance:
    <d> = (1 - f_N) * z_tip + f_N * (z_tip + h)
        = z_tip + f_N * h
    => z_tip(N) = d_target - f_N * h

The default suite contains 16 tasks: eight at <d> = 20.00 nm and eight at
<d> = 30.00 nm. Every configuration must have a strictly positive tip clearance.
"""

import os
import sys
import json
import math
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from execution.fractal_rotary_clutch_geometry import (
    get_fractal_clutch_elements,
    compute_plate_area_fraction,
)
from utils.metrics_logger import log_metrics


def calculate_standoff(d_average: float, feature_depth: float, area_fraction: float) -> float:
    """Calculates positive tip standoff such that average distance equals d_average."""
    if not math.isfinite(d_average) or d_average <= 0.0:
        raise ValueError(f"d_average must be finite and positive, got {d_average}")
    if not math.isfinite(feature_depth) or feature_depth < 0.0:
        raise ValueError(
            f"feature_depth must be finite and non-negative, got {feature_depth}"
        )
    if not math.isfinite(area_fraction) or not 0.0 <= area_fraction <= 1.0:
        raise ValueError(
            f"area_fraction must be finite and in [0, 1], got {area_fraction}"
        )

    z_tip = d_average - area_fraction * feature_depth
    if not math.isfinite(z_tip) or z_tip <= 0.0:
        raise ValueError(f"Calculated z_tip={z_tip} must be finite and positive!")

    reconstructed_d_avg = (
        (1.0 - area_fraction) * z_tip
        + area_fraction * (z_tip + feature_depth)
    )
    if not math.isclose(
        reconstructed_d_avg, d_average, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise ValueError(
            f"Reconstructed average distance {reconstructed_d_avg} "
            f"does not match target {d_average}"
        )
    return z_tip


def build_fractal_clutch_suite(
    actual_distances_nm: list = [20.0, 30.0],
    t_plate_um: float = 0.025,       # Stator membrane thickness: 25 nm
    L_fractal_um: float = 1.05,      # Fractal base span: 1.05 um
    W1_aperture_um: float = 0.25,    # Primary aperture diameter: 250 nm
    w1_needle_um: float = 0.035,     # Primary needle width: 35 nm
    H_needle_um: float = 0.25,       # Needle height: 250 nm
    material: str = "Gold",
    medium: str = "Vacuum",
    resolution: int = 60,           # Cluster-proven resolution: dx = 16.67 nm
    nmax: int = 1,
    T_run: float = 3.0,
) -> list:
    """
    Constructs eight configurations per requested average distance.

    The existing actual_distances_nm parameter and actual_distance_nm output
    field are retained for compatibility; their values specify the target
    area-weighted average distance, not the N=1 tip clearance.
    """
    angles = [0.0, 30.0, 45.0, 90.0]
    generations = [1, 3]

    if not math.isfinite(t_plate_um) or t_plate_um < 0.0:
        raise ValueError(
            f"t_plate_um must be finite and non-negative, got {t_plate_um}"
        )

    elements_dict = {
        N: get_fractal_clutch_elements(
            N, L_fractal_um, W1=W1_aperture_um, w1=w1_needle_um
        )
        for N in generations
    }
    area_fraction_dict = {
        N: compute_plate_area_fraction(elements_dict[N], L_fractal_um)
        for N in generations
    }

    configs = []
    task_id = 1

    for d_act_nm in actual_distances_nm:
        if not math.isfinite(d_act_nm) or d_act_nm <= 0.0:
            raise ValueError(
                f"Target distance must be finite and positive, got {d_act_nm}"
            )
        d_average_um = d_act_nm * 1e-3

        ztip_dict = {
            N: calculate_standoff(
                d_average_um, t_plate_um, area_fraction_dict[N]
            )
            for N in generations
        }

        for N in generations:
            f_area = area_fraction_dict[N]
            z_tip = ztip_dict[N]

            for theta in angles:
                if abs(theta) < 1e-3 or abs(theta - 90.0) < 1e-3:
                    expected_regime = "REPULSIVE"
                elif abs(theta - 45.0) < 1e-3:
                    expected_regime = "ATTRACTIVE"
                else:
                    expected_regime = "TRANSITION"

                label = (
                    f"DualFractalClutch: d_act={d_act_nm:.0f}nm, N={N}, "
                    f"th={theta:.1f}deg, <d>={d_average_um*1e3:.2f}nm, "
                    f"z_tip={z_tip*1e3:.2f}nm, mat={material}"
                )

                cfg = {
                    "task_id": task_id,
                    "label": label,
                    "campaign": "dual_fractal_rotary_clutch_constant_d_avg",
                    "actual_distance_nm": float(d_act_nm),
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
                    "T_run": float(T_run),
                }
                configs.append(cfg)
                task_id += 1

    return configs


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Dual-Fractal Casimir Clutch Configuration Suite"
    )
    parser.add_argument(
        "--res",
        type=int,
        default=60,
        help="Yee grid resolution (default: 60 px/um, dx=16.67 nm)",
    )
    parser.add_argument(
        "--t-plate",
        type=float,
        default=0.025,
        help="Stator plate thickness in um (default: 0.025)",
    )
    parser.add_argument(
        "--T-run",
        type=float,
        default=3.0,
        help="FDTD run duration in Meep time units (default: 3.0)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Maximum number of configurations to write (default: full suite)",
    )
    args = parser.parse_args()

    if args.max_steps is not None and args.max_steps < 0:
        parser.error("--max-steps must be non-negative")
    if args.res <= 0:
        parser.error("--res must be positive")
    if not math.isfinite(args.t_plate) or args.t_plate < 0.0:
        parser.error("--t-plate must be finite and non-negative")
    if not math.isfinite(args.T_run) or args.T_run <= 0.0:
        parser.error("--T-run must be finite and positive")

    started_at = time.perf_counter()
    configs = build_fractal_clutch_suite(
        actual_distances_nm=[20.0, 30.0],
        t_plate_um=args.t_plate,
        resolution=args.res,
        T_run=args.T_run,
    )
    if args.max_steps is not None:
        configs = configs[:args.max_steps]

    out_dir = os.path.join(REPO_ROOT, "sweep_configs_fractal_clutch")
    os.makedirs(out_dir, exist_ok=True)

    # Clean old configs.
    for old_f in os.listdir(out_dir):
        if old_f.endswith(".json"):
            os.remove(os.path.join(out_dir, old_f))

    for cfg in configs:
        tid = cfg["task_id"]
        fname = os.path.join(out_dir, f"config_{tid:03d}.json")
        with open(fname, "w", newline="\n") as f_out:
            json.dump(cfg, f_out, indent=4, allow_nan=False)
        print(
            f"Generated {fname}: Task {tid:02d} | "
            f"d_act={cfg['actual_distance_nm']:.0f} nm, "
            f"N={cfg['N_fractal']}, theta={cfg['theta_deg']:.1f} deg, "
            f"z_tip={cfg['z_tip_um']*1e3:.2f} nm, "
            f"<d>={cfg['d_average_um']*1e3:.2f} nm"
        )

    master_path = os.path.join(out_dir, "master_fractal_clutch_suite.json")
    with open(master_path, "w", newline="\n") as f_m:
        json.dump(configs, f_m, indent=4, allow_nan=False)

    log_metrics({
        "script": "generate_fractal_clutch_configs",
        "configurations_generated": len(configs),
        "elapsed_seconds": time.perf_counter() - started_at,
        "max_steps": args.max_steps,
        "resolution": args.res,
    })

    print(f"\nSuccessfully generated {len(configs)} configurations in {out_dir}")
    print(f"Master suite saved to {master_path}")


if __name__ == "__main__":
    main()
