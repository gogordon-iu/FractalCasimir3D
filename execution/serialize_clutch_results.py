#!/usr/bin/env python3
"""
Serialize Completed Checkpoints for Dual-Fractal Rotary Vacuum Casimir Clutch
--------------------------------------------------------------------------------
Zero-dependency post-processor (does NOT require Meep).
Reads .tmp/chk_fractal_clutch_task_*_{both,self}.json checkpoints, computes net
Casimir force F_z and normal pressure P, and writes the standardized result JSONs to:
    results_fractal_rotary_clutch/task_{task_id:03d}_N_{N}_th_{int(theta)}deg.json
Also archives raw logs from .tmp/ to cluster_diagnostics/raw_logs/.
"""

import os
import sys
import glob
import json
import time
import shutil

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from execution.fractal_rotary_clutch_geometry import (
    get_fractal_clutch_elements,
    compute_plate_area_fraction
)

MEEP_TO_PA = 0.031615
MEEP_FORCE_TO_SI = 3.1615e-14


def serialize_task(cfg_path):
    with open(cfg_path, "r") as f:
        cfg = json.load(f)

    task_id = int(cfg["task_id"])
    N_fractal = int(cfg["N_fractal"])
    theta = float(cfg["theta_deg"])
    L_fractal = float(cfg["L_fractal_um"])
    W1 = float(cfg["W1_aperture_um"])
    w1 = float(cfg["w1_needle_um"])
    H = float(cfg["H_needle_um"])
    t_plate = float(cfg["t_plate_um"])
    z_tip = float(cfg["z_tip_um"])
    mat = cfg["material"]
    res = int(cfg["resolution"])

    out_dir = os.path.join(REPO_ROOT, "results_fractal_rotary_clutch")
    os.makedirs(out_dir, exist_ok=True)
    out_dest = os.path.join(out_dir, f"task_{task_id:03d}_N_{N_fractal}_th_{int(theta)}deg.json")

    # Pattern for checkpoint files in .tmp/
    chk_pattern_both = f".tmp/chk_fractal_clutch_task_{task_id:03d}_N_{N_fractal}_th_{theta:.1f}_*both.json"
    chk_pattern_self = f".tmp/chk_fractal_clutch_task_{task_id:03d}_N_{N_fractal}_th_{theta:.1f}_*self.json"

    both_matches = glob.glob(chk_pattern_both)
    self_matches = glob.glob(chk_pattern_self)

    if not both_matches or not self_matches:
        if os.path.exists(out_dest):
            print(f"[ALREADY EXISTS] Task {task_id:03d} (N={N_fractal}, th={theta:.1f} deg): {out_dest}")
            with open(out_dest, "r") as f:
                return json.load(f)
        print(f"[SKIP] Task {task_id:03d} (N={N_fractal}, th={theta:.1f} deg): Checkpoint files not found in .tmp/")
        return None

    both_file = both_matches[0]
    self_file = self_matches[0]

    with open(both_file, "r") as f:
        f_both = float(json.load(f)["force"])
    with open(self_file, "r") as f:
        f_self = float(json.load(f)["force"])

    f_net = f_both - f_self
    f_net_N = f_net * MEEP_FORCE_TO_SI
    f_net_fN = f_net_N * 1e15

    elements = get_fractal_clutch_elements(N_fractal, L_fractal, W1=W1, w1=w1)
    A_rotor = sum(elem["w_needle"] ** 2 for elem in elements)
    pressure_Pa = (f_net / A_rotor) * MEEP_TO_PA

    f_area = compute_plate_area_fraction(elements, L_fractal)
    d_avg_um = (1.0 - f_area) * z_tip + f_area * (z_tip + t_plate)

    result_data = {
        "task_id": task_id,
        "architecture": "dual_fractal_rotary_casimir_clutch",
        "actual_distance_nm": float(cfg.get("actual_distance_nm", 20.0 if task_id <= 8 else 30.0)),
        "N_fractal": N_fractal,
        "theta_deg": float(theta),
        "d_average_nm": float(d_avg_um * 1e3),
        "L_fractal_nm": float(L_fractal * 1e3),
        "W1_aperture_nm": float(W1 * 1e3),
        "w1_needle_nm": float(w1 * 1e3),
        "H_needle_nm": float(H * 1e3),
        "t_plate_nm": float(t_plate * 1e3),
        "z_tip_nm": float(z_tip * 1e3),
        "material": mat,
        "resolution": res,
        "num_needles": len(elements),
        "A_rotor_um2": float(A_rotor),
        "force_total_meep": float(f_net),
        "force_total_fN": float(f_net_fN),
        "pressure_Pa": float(pressure_Pa),
        "regime": "REPULSIVE" if f_net > 0 else "ATTRACTIVE",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(out_dest, "w") as f:
        json.dump(result_data, f, indent=4)

    # Archive raw log files if present
    log_dir = os.path.join(REPO_ROOT, "cluster_diagnostics", "raw_logs")
    os.makedirs(log_dir, exist_ok=True)
    for log_match in glob.glob(f".tmp/fractal_clutch_*_{task_id}.*"):
        dst = os.path.join(log_dir, os.path.basename(log_match))
        try:
            shutil.copy2(log_match, dst)
        except Exception:
            pass

    print(f"[SERIALIZED] Task {task_id:03d} (N={N_fractal}, th={theta:.1f} deg):")
    print(f"  F_both = {f_both:+.6e}, F_self = {f_self:+.6e}")
    print(f"  F_net  = {f_net:+.6e} ({f_net_fN:+.4f} fN) | P = {pressure_Pa:+.4f} Pa ({result_data['regime']})")
    print(f"  Saved -> {out_dest}\n")
    return result_data


def main():
    cfg_files = sorted(glob.glob(os.path.join(REPO_ROOT, "sweep_configs_fractal_clutch", "config_*.json")))
    if not cfg_files:
        print("No sweep configs found.")
        return

    print("=" * 85)
    print("SERIALIZING COMPLETED DUAL-FRACTAL CASIMIR CLUTCH TASKS FROM .tmp/ CHECKPOINTS")
    print("=" * 85)

    processed = 0
    for cfg_path in cfg_files:
        res = serialize_task(cfg_path)
        if res is not None:
            processed += 1

    print("=" * 85)
    print(f"Done. Successfully verified/serialized {processed} of {len(cfg_files)} tasks.")
    print("=" * 85)


if __name__ == "__main__":
    main()
