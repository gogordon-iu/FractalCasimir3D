#!/usr/bin/env python3
"""
Concentric Cantor-Ring Configuration Generator: "The One Ring to Rule Them All"
-------------------------------------------------------------------------------
Generates complete simulation configuration JSONs for the Concentric Cantor-Ring
rotary Casimir clutch suite across:
1. Prefractal generations N in {1, 2, 3}.
2. Rotation angles theta in {0.0 deg, 22.5 deg, 45.0 deg, 90.0 deg}.
   - 0.0 deg:   Full tooth-in-aperture alignment (Repulsion / Levitation)
   - 22.5 deg:  Crossover transition
   - 45.0 deg:  Tooth-over-bridge alignment (Attraction / Clamping)
   - 90.0 deg:  Symmetry recovery
3. Non-fractal controls:
   - Uniform periodic concentric ring control (equal pitch, no fractal hierarchy)
   - Solid flat plate control (pure Lifshitz attractive reference)
4. Strict analytical distance invariance: <d> = 20.00 nm across all tasks.
"""

import os
import sys
import json
import argparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from execution.concentric_ring_geometry import (
    get_cantor_ring_elements,
    get_uniform_ring_elements,
    compute_concentric_aperture_area_fraction,
    compute_invariant_z_tip
)


def generate_all_configs(
    out_dir: str = "sweep_configs_concentric_ring",
    d_avg_nm: float = 20.0,
    t_plate_nm: float = 25.0,
    H_teeth_nm: float = 250.0,
    L_domain_um: float = 3.0,
    R_min_um: float = 0.30,
    R_max_um: float = 1.35,
    resolution: int = 60,
    T_run: float = 12.0,
    nmax: int = 1,
    material: str = "Gold"
):
    os.makedirs(out_dir, exist_ok=True)

    d_avg_um = d_avg_nm * 1e-3
    t_plate_um = t_plate_nm * 1e-3
    H_teeth_um = H_teeth_nm * 1e-3

    angles = [0.0, 22.5, 45.0, 90.0]
    task_id = 1
    master_manifest = []

    # 1. Fractal Generations N = 1, 2, 3
    for N in [1, 2, 3]:
        elements = get_cantor_ring_elements(N=N, R_min=R_min_um, R_max=R_max_um)
        f_ap = compute_concentric_aperture_area_fraction(elements, R_min_um, R_max_um)
        z_tip_um = compute_invariant_z_tip(d_avg_um, f_ap, t_plate_um)

        for th in angles:
            exp_regime = "REPULSIVE" if th in [0.0, 90.0] else "ATTRACTIVE" if th == 45.0 else "TRANSITION"
            cfg = {
                "task_id": task_id,
                "label": f"CantorRing_N{N}_th_{th:.1f}deg",
                "campaign": "concentric_cantor_ring_clutch",
                "architecture": "Concentric_Cantor_Ring",
                "N_fractal": N,
                "is_control": False,
                "is_flat_control": False,
                "control_type": "none",
                "num_tracks": len(elements),
                "theta_deg": float(th),
                "d_average_nm": float(d_avg_nm),
                "d_average_um": float(d_avg_um),
                "area_fraction": float(f_ap),
                "z_tip_nm": float(z_tip_um * 1e3),
                "z_tip_um": float(z_tip_um),
                "L_domain_um": float(L_domain_um),
                "R_min_um": float(R_min_um),
                "R_max_um": float(R_max_um),
                "H_teeth_nm": float(H_teeth_nm),
                "H_teeth_um": float(H_teeth_um),
                "t_plate_nm": float(t_plate_nm),
                "t_plate_um": float(t_plate_um),
                "expected_regime": exp_regime,
                "material": material,
                "resolution": int(resolution),
                "nmax": int(nmax),
                "T_run": float(T_run),
                "num_sectors": 4,
                "sector_duty_cycle": 0.50,
                "tooth_duty_cycle": 0.38,
                "elements": elements
            }

            fname = os.path.join(out_dir, f"config_{task_id:03d}.json")
            with open(fname, "w") as f:
                json.dump(cfg, f, indent=4)
            master_manifest.append(cfg)
            task_id += 1

    # 2. Non-Fractal Uniform Periodic Control (N=0, 3 Rings)
    ctrl_elements = get_uniform_ring_elements(num_rings=3, R_min=R_min_um, R_max=R_max_um)
    ctrl_f_ap = compute_concentric_aperture_area_fraction(ctrl_elements, R_min_um, R_max_um)
    ctrl_z_tip_um = compute_invariant_z_tip(d_avg_um, ctrl_f_ap, t_plate_um)

    for th in angles:
        exp_regime = "REPULSIVE" if th in [0.0, 90.0] else "ATTRACTIVE" if th == 45.0 else "TRANSITION"
        cfg = {
            "task_id": task_id,
            "label": f"UniformRing_Ctrl_th_{th:.1f}deg",
            "campaign": "concentric_cantor_ring_clutch",
            "architecture": "Concentric_Cantor_Ring",
            "N_fractal": 0,
            "is_control": True,
            "is_flat_control": False,
            "control_type": "uniform_periodic",
            "num_tracks": len(ctrl_elements),
            "theta_deg": float(th),
            "d_average_nm": float(d_avg_nm),
            "d_average_um": float(d_avg_um),
            "area_fraction": float(ctrl_f_ap),
            "z_tip_nm": float(ctrl_z_tip_um * 1e3),
            "z_tip_um": float(ctrl_z_tip_um),
            "L_domain_um": float(L_domain_um),
            "R_min_um": float(R_min_um),
            "R_max_um": float(R_max_um),
            "H_teeth_nm": float(H_teeth_nm),
            "H_teeth_um": float(H_teeth_um),
            "t_plate_nm": float(t_plate_nm),
            "t_plate_um": float(t_plate_um),
            "expected_regime": exp_regime,
            "material": material,
            "resolution": int(resolution),
            "nmax": int(nmax),
            "T_run": float(T_run),
            "num_sectors": 4,
            "sector_duty_cycle": 0.50,
            "tooth_duty_cycle": 0.38,
            "elements": ctrl_elements
        }

        fname = os.path.join(out_dir, f"config_{task_id:03d}.json")
        with open(fname, "w") as f:
            json.dump(cfg, f, indent=4)
        master_manifest.append(cfg)
        task_id += 1

    # 3. Solid Flat Plate Control (f_ap = 0, z_tip = d_avg)
    flat_cfg = {
        "task_id": task_id,
        "label": "SolidFlat_Plate_Ctrl",
        "campaign": "concentric_cantor_ring_clutch",
        "architecture": "Concentric_Cantor_Ring",
        "N_fractal": 0,
        "is_control": True,
        "is_flat_control": True,
        "control_type": "solid_flat_slab",
        "num_tracks": 0,
        "theta_deg": 0.0,
        "d_average_nm": float(d_avg_nm),
        "d_average_um": float(d_avg_um),
        "area_fraction": 0.0,
        "z_tip_nm": float(d_avg_nm),
        "z_tip_um": float(d_avg_um),
        "L_domain_um": float(L_domain_um),
        "R_min_um": float(R_min_um),
        "R_max_um": float(R_max_um),
        "H_teeth_nm": float(H_teeth_nm),
        "H_teeth_um": float(H_teeth_um),
        "t_plate_nm": float(t_plate_nm),
        "t_plate_um": float(t_plate_um),
        "expected_regime": "ATTRACTIVE",
        "material": material,
        "resolution": int(resolution),
        "nmax": int(nmax),
        "T_run": float(T_run),
        "num_sectors": 4,
        "sector_duty_cycle": 0.0,
        "tooth_duty_cycle": 0.0,
        "elements": []
    }
    fname = os.path.join(out_dir, f"config_{task_id:03d}.json")
    with open(fname, "w") as f:
        json.dump(flat_cfg, f, indent=4)
    master_manifest.append(flat_cfg)

    # Master manifest
    manifest_path = os.path.join(out_dir, "master_concentric_ring_suite.json")
    with open(manifest_path, "w") as f:
        json.dump(master_manifest, f, indent=4)

    print("=" * 80)
    print(f"CONCENTRIC CANTOR-RING CONFIGURATION SUITE GENERATED")
    print(f"Directory: {out_dir}")
    print(f"Total Tasks: {len(master_manifest)}")
    print(f"  Tasks 001-004: Generation N=1 (1 Ring) across theta in [0, 22.5, 45, 90] deg")
    print(f"  Tasks 005-008: Generation N=2 (3 Rings) across theta in [0, 22.5, 45, 90] deg")
    print(f"  Tasks 009-012: Generation N=3 (7 Rings) across theta in [0, 22.5, 45, 90] deg")
    print(f"  Tasks 013-016: Non-Fractal Uniform Periodic Control (3 Rings)")
    print(f"  Task  017:     Solid Flat Plate Reference Control")
    print("=" * 80)
    return master_manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Concentric Cantor-Ring configs.")
    parser.add_argument("--res", type=int, default=60, help="Grid resolution R (pixels/um)")
    parser.add_argument("--out-dir", type=str, default="sweep_configs_concentric_ring")
    args = parser.parse_args()

    generate_all_configs(out_dir=args.out_dir, resolution=args.res)
