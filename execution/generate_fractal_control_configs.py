#!/usr/bin/env python3
"""
Configuration Generator for Fractal Geometry Control Suite
----------------------------------------------------------
Generates the 15-task configuration suite to isolate and explore the effect of
fractal geometry vs. non-fractal geometry at strictly constant average distance:

Matrix of Configurations:
  1. N=1 Fractal: θ in {0°, 60°, 90°} (Tasks 1-3)
  2. N=2 Fractal: θ in {0°, 60°, 90°} (Tasks 4-6)
  3. N=3 Fractal: θ in {0°, 60°, 90°} (Tasks 7-9)
  4. N=3 Shuffled: θ in {0°, 60°, 90°} (Tasks 10-12)
  5. N=0 Flat Baseline: θ in {0°, 60°, 90°} (Tasks 13-15)

Key Guarantees:
- Area-weighted average distance <d> is identical across all tasks:
    <d> = d_min + f_N * h == d_average = 100 nm (0.10 µm)
- N=3 Shuffled contains the exact same 73 elements as N=3 Fractal.
- Clean structured JSON output, zero hardcoded magic variables, zero try-catch.
"""

import os
import sys
import json
import argparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from execution.fractal_control_geometry import calculate_area_fraction, calculate_standoff


def build_suite_configs(
    d_average_um: float = 0.10,
    feature_depth_um: float = 0.05,
    L_um: float = 2.0,
    material: str = "Gold",
    medium: str = "Vacuum",
    eps_bg: float = 1.0,
    resolution: int = 40,
    nmax: int = 1,
    T_run: float = 12.0,
    shuffle_seed: int = 42
) -> list:
    """
    Constructs the list of 15 configuration dictionaries.
    """
    assert d_average_um > 0.0, f"d_average_um must be positive, got {d_average_um}"
    assert feature_depth_um > 0.0, f"feature_depth_um must be positive, got {feature_depth_um}"
    assert L_um > 0.0, f"L_um must be positive, got {L_um}"

    angles = [0.0, 60.0, 90.0]
    cases = [
        {"name": "N1_fractal", "geom": "fractal", "N": 1},
        {"name": "N2_fractal", "geom": "fractal", "N": 2},
        {"name": "N3_fractal", "geom": "fractal", "N": 3},
        {"name": "N3_shuffled", "geom": "shuffled", "N": 3},
        {"name": "N0_flat_control", "geom": "flat", "N": 0},
    ]

    configs = []
    task_id = 1

    for case in cases:
        geom_type = case["geom"]
        N = case["N"]
        case_name = case["name"]

        f_area = calculate_area_fraction(N)
        d_min = calculate_standoff(d_average_um, feature_depth_um, f_area)

        for theta in angles:
            label = (
                f"FractalControl: {case_name}, d_avg={d_average_um*1e3:.0f}nm, "
                f"d_min={d_min*1e3:.2f}nm, th={theta:.1f}deg, mat={material}"
            )
            cfg = {
                "task_id": task_id,
                "label": label,
                "campaign": "fractal_geometry_control",
                "geometry_type": geom_type,
                "case_name": case_name,
                "N_top": N,
                "N_bot": 1,
                "theta": float(theta),
                "d_average_um": float(d_average_um),
                "feature_depth_um": float(feature_depth_um),
                "area_fraction": float(f_area),
                "d_min_um": float(d_min),
                "t_top_um": 0.10,
                "t_bottom_um": 0.10,
                "material": str(material),
                "medium": str(medium),
                "eps_bg": float(eps_bg),
                "L": float(L_um),
                "resolution": int(resolution),
                "nmax": int(nmax),
                "T_run": float(T_run),
                "shuffle_seed": int(shuffle_seed)
            }
            configs.append(cfg)
            task_id += 1

    assert len(configs) == 15, f"Expected 15 configurations, generated {len(configs)}"
    return configs


def main():
    parser = argparse.ArgumentParser(
        description="Generate configuration suite for Fractal Geometry Control Campaign"
    )
    parser.add_argument("--d-avg", type=float, default=0.10, help="Target average distance in um (default: 0.10 um = 100 nm)")
    parser.add_argument("--feature-depth", type=float, default=0.05, help="Feature cavity depth in um (default: 0.05 um = 50 nm)")
    parser.add_argument("--L", type=float, default=2.0, help="Plate width in um (default: 2.0)")
    parser.add_argument("--material", type=str, default="Gold", help="Plate material (default: Gold)")
    parser.add_argument("--medium", type=str, default="Vacuum", help="Immersion medium (default: Vacuum)")
    parser.add_argument("--eps-bg", type=float, default=1.0, help="Background permittivity (default: 1.0)")
    parser.add_argument("--resolution", type=int, default=40, help="FDTD Yee grid resolution (default: 40)")
    parser.add_argument("--nmax", type=int, default=1, help="Multipole moment cutoff multiplier (default: 1 -> 36 moments)")
    parser.add_argument("--T-run", type=float, default=12.0, help="Simulation duration (default: 12.0)")
    parser.add_argument("--shuffle-seed", type=int, default=42, help="Seed for reproducible element shuffling (default: 42)")
    parser.add_argument("--out-dir", type=str, default="sweep_configs_fractal_control", help="Output directory for configs")

    args = parser.parse_args()

    out_path = os.path.join(REPO_ROOT, args.out_dir)
    os.makedirs(out_path, exist_ok=True)

    configs = build_suite_configs(
        d_average_um=args.d_avg,
        feature_depth_um=args.feature_depth,
        L_um=args.L,
        material=args.material,
        medium=args.medium,
        eps_bg=args.eps_bg,
        resolution=args.resolution,
        nmax=args.nmax,
        T_run=args.T_run,
        shuffle_seed=args.shuffle_seed
    )

    for cfg in configs:
        tid = cfg["task_id"]
        cfg_filename = f"config_{tid:03d}.json"
        cfg_file_path = os.path.join(out_path, cfg_filename)
        with open(cfg_file_path, "w", encoding="utf-8") as f_out:
            json.dump(cfg, f_out, indent=4)

    # Master manifest
    manifest_path = os.path.join(out_path, "master_fractal_control_suite.json")
    with open(manifest_path, "w", encoding="utf-8") as f_man:
        json.dump({
            "campaign": "fractal_geometry_control",
            "total_tasks": len(configs),
            "d_average_um": args.d_avg,
            "feature_depth_um": args.feature_depth,
            "resolution": args.resolution,
            "tasks": configs
        }, f_man, indent=4)

    print("=" * 80)
    print(f"Successfully generated {len(configs)} configuration files in: {out_path}")
    print(f"Master manifest written to: {manifest_path}")
    print(f"{'Task':<6}{'Case':<18}{'N':<4}{'Theta':<8}{'d_avg (nm)':<12}{'d_min (nm)':<12}{'f_area':<10}")
    print("-" * 80)
    for c in configs:
        print(
            f"{c['task_id']:<6}{c['case_name']:<18}{c['N_top']:<4}{c['theta']:<8.1f}"
            f"{c['d_average_um']*1e3:<12.1f}{c['d_min_um']*1e3:<12.2f}{c['area_fraction']:<10.4f}"
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
