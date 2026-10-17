#!/usr/bin/env python3
"""
Sierpinski-Cantor Forest Configuration Suite Generator
-------------------------------------------------------
Generates the 8-task configuration suite for BigRed 200:
- Angles: theta in {0.0 deg, 30.0 deg, 45.0 deg, 90.0 deg}
- Constant average distance: <d> = 20.0 nm by default
- Dimensions: L = 1.05 um, W1 = 250 nm, w1 = 35 nm, H = 250 nm, t = 25 nm
- 8 tasks (Tasks 1-4: N=1, Tasks 5-8: N=3)
- Materials & solver: Gold in Vacuum, R = 60 px/um, nmax = 1, T_run = 12.0

Tip standoffs are calculated from the Cantor forest aperture area fractions.
Exact needle standoffs remain available through match_needle_ztip=True.
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
    if not math.isclose(reconstructed_d_avg, d_average, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Calculated standoff does not preserve the average distance.")
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
    resolution: int = 60,           # R = 60 px/um (dx = 16.67 nm)
    nmax: int = 1,
    T_run: float = 12.0,
    match_needle_ztip: bool = False
) -> list:
    """
    Constructs exactly 8 configuration dictionaries.

    By default, each generation uses its own aperture area fraction to
    preserve d_average_um. Needle standoffs are an explicit opt-in override.
    """
    angles = [0.0, 30.0, 45.0, 90.0]
    generations = [1, 3]

    # Stored needle z_tip values for optional exact 1:1 distance pairing.
    needle_ztips = {
        1: 0.015547629459198138,
        3: 0.014942986546249738
    }

    configs = []
    task_id = 1

    for N in generations:
        elements = get_sierpinski_cantor_elements(
            N, L_fractal_um, W1_aperture_um, w1_pillar_um
        )
        af = compute_sieve_area_fractions(elements, L_fractal_um)
        f_area = af["aperture_area_fraction"]

        if match_needle_ztip:
            z_tip = needle_ztips[N]
        else:
            z_tip = calculate_standoff(d_average_um, t_plate_um, f_area)

        num_pillars = len(elements)

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
    from utils.metrics_logger import MetricsLogger

    parser = argparse.ArgumentParser(
        description="Generate Sierpinski-Cantor Forest 8-Task Configuration Suite"
    )
    parser.add_argument(
        "--res", type=int, default=60,
        help="Grid resolution (default: 60 px/um)"
    )
    parser.add_argument(
        "--d-avg", type=float, default=0.020,
        help="Average distance in um (default: 0.020)"
    )
    parser.add_argument(
        "--t-plate", type=float, default=0.025,
        help="Stator plate thickness in um (default: 0.025)"
    )
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Maximum number of configurations to write in the probe directory "
             "(default: write all 8 configurations in the production directory)"
    )
    args = parser.parse_args()

    if args.max_steps is not None and args.max_steps < 0:
        parser.error("--max-steps must be non-negative")
    if args.res <= 0:
        parser.error("--res must be positive")

    configs = build_cantor_forest_suite(
        d_average_um=args.d_avg,
        t_plate_um=args.t_plate,
        resolution=args.res
    )

    if args.max_steps is not None:
        configs = configs[:args.max_steps]
        out_dir = os.path.join(
            REPO_ROOT, ".tmp", "sweep_configs_cantor_forest_probe"
        )
    else:
        out_dir = os.path.join(REPO_ROOT, "sweep_configs_cantor_forest")
    os.makedirs(out_dir, exist_ok=True)

    # Clean old configs.
    for old_f in os.listdir(out_dir):
        if old_f.endswith(".json"):
            os.remove(os.path.join(out_dir, old_f))

    metrics_logger = MetricsLogger(os.path.join(out_dir, "metrics.jsonl"))
    try:
        for cfg in configs:
            tid = cfg["task_id"]
            fname = os.path.join(out_dir, f"config_{tid:03d}.json")
            with open(fname, "w", newline="\n") as f_out:
                json.dump(cfg, f_out, indent=4, allow_nan=False)

            metrics_logger.log({
                "step": tid,
                "task_id": tid,
                "N_fractal": cfg["N_fractal"],
                "num_pillars": cfg["num_pillars"],
                "theta_deg": cfg["theta_deg"],
                "d_average_um": cfg["d_average_um"],
                "z_tip_um": cfg["z_tip_um"],
                "area_fraction": cfg["area_fraction"],
                "resolution": cfg["resolution"]
            })

            print(
                f"Task {tid:02d}: N={cfg['N_fractal']} "
                f"({cfg['num_pillars']:2d} pillars), "
                f"theta={cfg['theta_deg']:4.1f} deg, "
                f"z_tip={cfg['z_tip_um']*1e3:.2f} nm, "
                f"<d>={cfg['d_average_um']*1e3:.1f} nm, "
                f"res={cfg['resolution']}"
            )

        master_path = os.path.join(out_dir, "master_cantor_forest_suite.json")
        with open(master_path, "w", newline="\n") as f_m:
            json.dump(configs, f_m, indent=4, allow_nan=False)
    finally:
        close = getattr(metrics_logger, "close", None)
        if callable(close):
            close()

    print(f"\nSuccessfully generated {len(configs)} configurations in {out_dir}")
    print(f"Master suite saved to {master_path}")


if __name__ == "__main__":
    main()
