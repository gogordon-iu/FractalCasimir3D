#!/usr/bin/env python3
"""Extended Single-Setup & Multiscale 3D Maxwell RWG BEM + 4-Pass 3D Meep FDTD Convergence Suite.

Closes all remaining first-principles convergence controls without modifying or invalidating the
completed 31-task baseline (`results/h3_single_setup_fdtd/task_1..31_meep.json` and
`results/h3_single_setup_bem_convergence.json`):
  1. Tier-5 Ultra-Dense Exact 3D Maxwell RWG BEM (`EFIE` PEC + `PMCHWT` Drude Au) on the shared
     20 nm-lattice H3-Cantor unit cell (extending the 4-tier RWG ladder to 5 nested mesh tiers).
  2. High-Resolution x High-Multipole Coupled 4-Pass 3D Meep FDTD Specs (Tasks 1..8 in
     `sweep_configs_h3_single_setup_fdtd_ext/`): R = 200, 250 at n_max = 4, 5 across Open Drude Au,
     Engaged PEC, Open PEC, and Engaged Drude Au to eliminate the uncalibrated (Delta_x x n_max)
     cross-term in the baseline R=150 multipole ladders.
  3. FDTD Domain, PML, Buffer, & Runtime (`T_run`) Invariance Controls (Tasks 9..12):
     T_run = 8.0 vs. 4.0 (PEC & dispersive Drude Au), expanded cell_buffer = 140 nm vs. 80 nm,
     and thickened PML = 240 nm vs. 160 nm.
  4. Multiscale 20 nm-Lattice Cantor Hierarchy vs. Iso-Area Uniform Grating Differential Benchmark
     (Exact 3D RWG BEM Tiers 1..3 + 4-Pass 3D Meep FDTD Tasks 13..18):
     Evaluates `Multiscale-Cantor-3Trk` (40/80/40 nm homothetic teeth in 120/240/120 nm slots) against
     iso-area, W_open-matched `Ctrl-Uniform-Coarse2` (two 80 nm teeth in 240 nm slots) in both
     first-principles RWG BEM and 4-pass 3D FDTD across PEC and dispersive Drude Au.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import gammainc

import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.run_h3_single_setup_convergence import (
    CELL_BUFFER_SINGLE_SETUP_UM,
    D_EFF_SINGLE_SETUP_UM,
    ENGAGED_STATOR_PAD_BOXES_UM,
    EXPLICIT_CELL_CENTER_UM,
    EXPLICIT_PHYS_BOUNDS_UM,
    OPEN_STATOR_COLLAR_BOXES_UM,
    PML_THICKNESS_SINGLE_SETUP_UM,
    ROTOR_LOBE_BOX_UM,
    RWGMeshTorch,
    STRESS_BOX_UM,
    T_RUN_SINGLE_SETUP,
    make_closed_box_rwg_mesh,
    make_multi_box_rwg_mesh,
    resolve_torch_device,
    solve_rwg_casimir_fz_pn,
)
from utils.metrics_logger import (
    _sanitize_macro_name,
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

# =============================================================================
# Tier 5 Ultra-Dense RWG Mesh Spec on Shared Single-Setup 20 nm-Lattice Cell
# =============================================================================
TIER5_BEM_SPEC: dict[str, Any] = {
    "tier": 5,
    "label": "Tier 5 (reference)",
    "rotor_sub": (6, 10, 5),
    "collar_sub": (4, 14, 5),
    "pad_sub": (8, 12, 4),
}

# =============================================================================
# Multiscale 20 nm-Lattice 3-Track Homothetic Cantor vs. Iso-Area Uniform Pair
# Every coordinate is an exact integer multiple of 0.020 um (20 nm):
#   - Active horizontal tooth area per sector: 0.160 * 0.080 = 0.0128 um^2 (both!)
#   - Total open slot width per sector: 0.480 um (both!)
#   - Strictly disjoint closed 6-face vacuum stress boxes (>= 20 nm margin)
# =============================================================================
MULTISCALE_CANTOR_ROTOR_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.300, -0.260, -0.040, 0.040, -0.080, -0.040),
    (-0.040, 0.040, -0.040, 0.040, -0.160, -0.080),
    (0.260, 0.300, -0.040, 0.040, -0.080, -0.040),
)
MULTISCALE_CANTOR_STATOR_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.360, -0.340, -0.120, 0.120, -0.060, -0.020),
    (-0.220, -0.200, -0.120, 0.120, -0.060, -0.020),
    (-0.140, -0.120, -0.120, 0.120, -0.120, -0.040),
    (0.120, 0.140, -0.120, 0.120, -0.120, -0.040),
    (0.200, 0.220, -0.120, 0.120, -0.060, -0.020),
    (0.340, 0.360, -0.120, 0.120, -0.060, -0.020),
)
MULTISCALE_CANTOR_STRESS_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.320, -0.240, -0.080, 0.080, -0.100, -0.020),
    (-0.080, 0.080, -0.080, 0.080, -0.180, -0.060),
    (0.240, 0.320, -0.080, 0.080, -0.100, -0.020),
)
MULTISCALE_CANTOR_CENTER_UM: tuple[float, float, float] = (0.0, 0.0, -0.100)
MULTISCALE_CANTOR_BOUNDS_UM: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] = (
    (-0.360, 0.360),
    (-0.120, 0.120),
    (-0.200, 0.040),
)

UNIFORM_COARSE2_ROTOR_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.200, -0.120, -0.040, 0.040, -0.120, -0.040),
    (0.120, 0.200, -0.040, 0.040, -0.120, -0.040),
)
UNIFORM_COARSE2_STATOR_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.300, -0.280, -0.120, 0.120, -0.100, -0.020),
    (-0.040, -0.020, -0.120, 0.120, -0.100, -0.020),
    (0.020, 0.040, -0.120, 0.120, -0.100, -0.020),
    (0.280, 0.300, -0.120, 0.120, -0.100, -0.020),
)
UNIFORM_COARSE2_STRESS_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.240, -0.080, -0.080, 0.080, -0.140, -0.020),
    (0.080, 0.240, -0.080, 0.080, -0.140, -0.020),
)
UNIFORM_COARSE2_CENTER_UM: tuple[float, float, float] = (0.0, 0.0, -0.080)
UNIFORM_COARSE2_BOUNDS_UM: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] = (
    (-0.300, 0.300),
    (-0.120, 0.120),
    (-0.160, 0.040),
)

MULTISCALE_BEM_TIERS: tuple[dict[str, Any], ...] = (
    {"tier": 1, "fine_sub": (1, 2, 1), "coarse_sub": (2, 3, 2), "wall_sub": (1, 4, 2)},
    {"tier": 2, "fine_sub": (2, 3, 2), "coarse_sub": (3, 4, 3), "wall_sub": (1, 6, 2)},
    {"tier": 3, "fine_sub": (3, 4, 2), "coarse_sub": (4, 5, 3), "wall_sub": (2, 7, 3)},
)


@dataclass(frozen=True)
class ExtFDTDSpec:
    task_id: int
    label: str
    group: str  # "coupled_high_rnmax" | "domain_invariance" | "multiscale_differential"
    design_key: str  # "single_open" | "single_engaged" | "ms_cantor" | "ms_uniform"
    material: str  # "PEC" | "Gold_Drude"
    resolution: int
    nmax: int
    t_run: float = T_RUN_SINGLE_SETUP
    cell_buffer_um: float = CELL_BUFFER_SINGLE_SETUP_UM
    pml_thickness_um: float = PML_THICKNESS_SINGLE_SETUP_UM


EXT_FDTD_SWEEP_SPECS: tuple[ExtFDTDSpec, ...] = (
    # Group 1: Coupled high-R x high-nmax closure on single-setup unit cell (Tasks 1..8)
    ExtFDTDSpec(1, "ext_ss_open_gold_R200_nmax4", "coupled_high_rnmax", "single_open", "Gold_Drude", 200, 4),
    ExtFDTDSpec(2, "ext_ss_open_gold_R200_nmax5", "coupled_high_rnmax", "single_open", "Gold_Drude", 200, 5),
    ExtFDTDSpec(3, "ext_ss_open_gold_R250_nmax4", "coupled_high_rnmax", "single_open", "Gold_Drude", 250, 4),
    ExtFDTDSpec(4, "ext_ss_eng_pec_R200_nmax4", "coupled_high_rnmax", "single_engaged", "PEC", 200, 4),
    ExtFDTDSpec(5, "ext_ss_eng_pec_R200_nmax5", "coupled_high_rnmax", "single_engaged", "PEC", 200, 5),
    ExtFDTDSpec(6, "ext_ss_eng_pec_R250_nmax4", "coupled_high_rnmax", "single_engaged", "PEC", 250, 4),
    ExtFDTDSpec(7, "ext_ss_open_pec_R200_nmax4", "coupled_high_rnmax", "single_open", "PEC", 200, 4),
    ExtFDTDSpec(8, "ext_ss_eng_gold_R200_nmax4", "coupled_high_rnmax", "single_engaged", "Gold_Drude", 200, 4),
    # Group 2: Domain, PML, buffer, and runtime T_run invariance controls (Tasks 9..12)
    ExtFDTDSpec(9, "ext_dom_open_pec_R150_n3_Trun8", "domain_invariance", "single_open", "PEC", 150, 3, t_run=8.0),
    ExtFDTDSpec(
        10, "ext_dom_open_gold_R150_n3_Trun8", "domain_invariance", "single_open", "Gold_Drude", 150, 3, t_run=8.0
    ),
    ExtFDTDSpec(
        11,
        "ext_dom_open_pec_R150_n3_buf140",
        "domain_invariance",
        "single_open",
        "PEC",
        150,
        3,
        cell_buffer_um=0.140,
    ),
    ExtFDTDSpec(
        12,
        "ext_dom_open_pec_R150_n3_pml240",
        "domain_invariance",
        "single_open",
        "PEC",
        150,
        3,
        pml_thickness_um=0.240,
    ),
    # Group 3: Multiscale 20 nm-lattice Cantor vs. Iso-Area Uniform differential benchmark (Tasks 13..18)
    ExtFDTDSpec(13, "ext_ms_cantor_pec_R100_n3", "multiscale_differential", "ms_cantor", "PEC", 100, 3),
    ExtFDTDSpec(14, "ext_ms_uniform_pec_R100_n3", "multiscale_differential", "ms_uniform", "PEC", 100, 3),
    ExtFDTDSpec(15, "ext_ms_cantor_pec_R150_n3", "multiscale_differential", "ms_cantor", "PEC", 150, 3),
    ExtFDTDSpec(16, "ext_ms_uniform_pec_R150_n3", "multiscale_differential", "ms_uniform", "PEC", 150, 3),
    ExtFDTDSpec(17, "ext_ms_cantor_gold_R150_n3", "multiscale_differential", "ms_cantor", "Gold_Drude", 150, 3),
    ExtFDTDSpec(18, "ext_ms_uniform_gold_R150_n3", "multiscale_differential", "ms_uniform", "Gold_Drude", 150, 3),
)


def _rel_root_str(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _safe_signed_ratio(numerator: float, denominator: float) -> float | None:
    if abs(denominator) <= 1.0e-9:
        return None
    return float(numerator / denominator)


def _fmt_ratio_macro(ratio: float | None) -> str:
    return "N/A" if ratio is None else f"{ratio:.2f}"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def verify_disjoint_stress_boxes(
    rotor_boxes: Sequence[tuple[float, float, float, float, float, float]],
    stator_boxes: Sequence[tuple[float, float, float, float, float, float]],
    stress_boxes: Sequence[tuple[float, float, float, float, float, float]],
) -> float:
    """Assert every rotor box sits strictly inside its stress box and every stator/other box sits strictly outside."""
    if len(rotor_boxes) != len(stress_boxes):
        raise ValueError("Each rotor prism requires a 1-to-1 enclosing closed stress box.")
    min_margin_um = math.inf
    for idx, (rb, sb) in enumerate(zip(rotor_boxes, stress_boxes)):
        in_margins = (
            rb[0] - sb[0],
            sb[1] - rb[1],
            rb[2] - sb[2],
            sb[3] - rb[3],
            rb[4] - sb[4],
            sb[5] - rb[5],
        )
        if min(in_margins) < 0.019999:
            raise ValueError(f"Rotor box {idx} violates >=20 nm inner stress-box standoff: {in_margins}")
        min_margin_um = min(min_margin_um, float(min(in_margins)))

        for jdx, ob in enumerate(stator_boxes):
            sep_x = max(sb[0] - ob[1], ob[0] - sb[1])
            sep_y = max(sb[2] - ob[3], ob[2] - sb[3])
            sep_z = max(sb[4] - ob[5], ob[4] - sb[5])
            sep = max(sep_x, sep_y, sep_z)
            if sep < 0.019999:
                raise ValueError(f"Stress box {idx} violates >=20 nm outer standoff to stator {jdx}: sep={sep}")
            min_margin_um = min(min_margin_um, float(sep))

        for kdx, sb2 in enumerate(stress_boxes):
            if kdx == idx:
                continue
            sep_ss = max(
                max(sb[0] - sb2[1], sb2[0] - sb[1]),
                max(sb[2] - sb2[3], sb2[2] - sb[3]),
                max(sb[4] - sb2[5], sb2[4] - sb[5]),
            )
            if sep_ss < 0.019999:
                raise ValueError(f"Stress boxes {idx} and {kdx} overlap or sit too close: sep={sep_ss}")
    return min_margin_um


def write_extended_fdtd_configs(
    out_dir: Path = ROOT / "sweep_configs_h3_single_setup_fdtd_ext",
) -> list[Path]:
    """Write all 18 extended 3D Meep FDTD config JSONs and manifest."""
    verify_disjoint_stress_boxes(
        MULTISCALE_CANTOR_ROTOR_BOXES_UM, MULTISCALE_CANTOR_STATOR_BOXES_UM, MULTISCALE_CANTOR_STRESS_BOXES_UM
    )
    verify_disjoint_stress_boxes(
        UNIFORM_COARSE2_ROTOR_BOXES_UM, UNIFORM_COARSE2_STATOR_BOXES_UM, UNIFORM_COARSE2_STRESS_BOXES_UM
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest_entries: list[dict[str, Any]] = []

    for sp in EXT_FDTD_SWEEP_SPECS:
        if sp.design_key == "single_open":
            r_boxes = [list(ROTOR_LOBE_BOX_UM)]
            s_boxes = [list(b) for b in OPEN_STATOR_COLLAR_BOXES_UM]
            st_boxes = [list(STRESS_BOX_UM)]
            center = list(EXPLICIT_CELL_CENTER_UM)
            bounds = [list(ax) for ax in EXPLICIT_PHYS_BOUNDS_UM]
            theta_deg = 3.0
            kin_state = "open_repulsive"
            des_name = "H3_Cantor_SingleSetup_20nmLattice"
        elif sp.design_key == "single_engaged":
            r_boxes = [list(ROTOR_LOBE_BOX_UM)]
            s_boxes = [list(b) for b in ENGAGED_STATOR_PAD_BOXES_UM]
            st_boxes = [list(STRESS_BOX_UM)]
            center = list(EXPLICIT_CELL_CENTER_UM)
            bounds = [list(ax) for ax in EXPLICIT_PHYS_BOUNDS_UM]
            theta_deg = 48.0
            kin_state = "engaged_attractive"
            des_name = "H3_Cantor_SingleSetup_20nmLattice"
        elif sp.design_key == "ms_cantor":
            r_boxes = [list(b) for b in MULTISCALE_CANTOR_ROTOR_BOXES_UM]
            s_boxes = [list(b) for b in MULTISCALE_CANTOR_STATOR_BOXES_UM]
            st_boxes = [list(b) for b in MULTISCALE_CANTOR_STRESS_BOXES_UM]
            center = list(MULTISCALE_CANTOR_CENTER_UM)
            bounds = [list(ax) for ax in MULTISCALE_CANTOR_BOUNDS_UM]
            theta_deg = 3.0
            kin_state = "open_repulsive"
            des_name = "Multiscale_Cantor_3Trk_20nmLattice"
        elif sp.design_key == "ms_uniform":
            r_boxes = [list(b) for b in UNIFORM_COARSE2_ROTOR_BOXES_UM]
            s_boxes = [list(b) for b in UNIFORM_COARSE2_STATOR_BOXES_UM]
            st_boxes = [list(b) for b in UNIFORM_COARSE2_STRESS_BOXES_UM]
            center = list(UNIFORM_COARSE2_CENTER_UM)
            bounds = [list(ax) for ax in UNIFORM_COARSE2_BOUNDS_UM]
            theta_deg = 3.0
            kin_state = "open_repulsive"
            des_name = "Ctrl_Uniform_Coarse2_IsoArea_20nmLattice"
        else:
            raise ValueError(f"Unknown design_key: {sp.design_key}")

        elems = []
        for idx_r, rb in enumerate(r_boxes):
            w_t = round(rb[1] - rb[0], 6)
            elems.append(
                {
                    "track_index": idx_r,
                    "level": 3,
                    "r_inner": round(3.50 + idx_r * 0.25, 6),
                    "r_outer": round(3.50 + idx_r * 0.25 + max(0.10, 2.5 * w_t), 6),
                    "r_tooth_in": round(3.53 + idx_r * 0.25, 6),
                    "r_tooth_out": round(3.53 + idx_r * 0.25 + w_t, 6),
                    "r_center": round(3.53 + idx_r * 0.25 + 0.5 * w_t, 6),
                    "W_slot": round(max(0.10, 2.5 * w_t), 6),
                    "w_tooth": w_t,
                    "h_teeth": round(rb[5] - rb[4], 6),
                    "z_tip": round(rb[4], 6),
                }
            )

        z_min_tooth = min(rb[4] for rb in r_boxes)
        z_pad_meta = round(z_min_tooth - 0.040, 6)
        cfg = {
            "task_id": sp.task_id,
            "control_label": sp.label,
            "group": sp.group,
            "design_name": des_name,
            "kinematic_state": kin_state,
            "geometry_mode": "explicit_boxes_3d",
            "stress_box_mode": "per_tooth_rotor_frame",
            "fixed_stress_box_margin_um": 0.020,
            "eps_averaging": False,
            "force_complex_fields": True,
            "sector0_crop": False,
            "material": sp.material,
            "resolution": sp.resolution,
            "nmax": sp.nmax,
            "T_run": sp.t_run,
            "courant": 0.5,
            "d_eff_um": D_EFF_SINGLE_SETUP_UM,
            "cell_buffer_um": sp.cell_buffer_um,
            "pml_thickness_um": sp.pml_thickness_um,
            "L_domain_um": 1.20 if sp.design_key.startswith("ms_") else 0.64,
            "num_sectors": 4,
            "N_fractal": 3,
            "theta_deg": theta_deg,
            "aperture_arc_deg": 36.0,
            "bridge_arc_deg": 54.0,
            "tooth_arc_deg": 12.0,
            "tooth_center_offset_deg": 15.0,
            "H_teeth_um": 0.040,
            "z_tip_um": round(z_min_tooth, 6),
            "z_pad_top_um": z_pad_meta,
            "t_membrane_um": 0.040,
            "t_landing_pad_um": 0.040,
            "explicit_rotor_boxes": r_boxes,
            "explicit_stator_boxes": s_boxes,
            "explicit_stress_boxes": st_boxes,
            "explicit_cell_center": center,
            "explicit_phys_bounds": bounds,
            "geometry": {"elements": elems},
        }
        p_cfg = out_dir / f"config_{sp.task_id:03d}.json"
        _atomic_write_json(p_cfg, cfg)
        written.append(p_cfg)
        manifest_entries.append(
            {
                "task_id": sp.task_id,
                "config_file": str(p_cfg.relative_to(ROOT)).replace("\\", "/"),
                "label": sp.label,
                "group": sp.group,
                "design_key": sp.design_key,
                "material": sp.material,
                "resolution": sp.resolution,
                "nmax": sp.nmax,
                "t_run": sp.t_run,
                "cell_buffer_um": sp.cell_buffer_um,
                "pml_thickness_um": sp.pml_thickness_um,
            }
        )

    _atomic_write_json(
        out_dir / "manifest.json",
        {
            "suite": "h3_single_setup_and_multiscale_fdtd_extension",
            "total_tasks": len(manifest_entries),
            "tasks": manifest_entries,
        },
    )
    return written


def _make_heterogeneous_boxes_rwg_mesh(
    box_subs: Sequence[tuple[tuple[float, float, float, float, float, float], tuple[int, int, int]]],
    dev: torch.device,
) -> RWGMeshTorch:
    v_list: list[np.ndarray] = []
    t_list: list[np.ndarray] = []
    v_off = 0
    for (x0, x1, y0, y1, z0, z1), (nx, ny, nz) in box_subs:
        xs = np.linspace(x0, x1, nx + 1)
        ys = np.linspace(y0, y1, ny + 1)
        zs = np.linspace(z0, z1, nz + 1)
        verts: list[tuple[float, float, float]] = []
        vmap: dict[tuple[int, int, int], int] = {}

        def vid(x: float, y: float, z: float) -> int:
            key = (round(x * 1e9), round(y * 1e9), round(z * 1e9))
            if key not in vmap:
                vmap[key] = len(verts)
                verts.append((float(x), float(y), float(z)))
            return vmap[key]

        tris: list[tuple[int, int, int]] = []

        def add_quad(
            p0: tuple[float, float, float],
            p1: tuple[float, float, float],
            p2: tuple[float, float, float],
            p3: tuple[float, float, float],
        ) -> None:
            i0, i1, i2, i3 = vid(*p0), vid(*p1), vid(*p2), vid(*p3)
            tris.append((i0, i1, i2))
            tris.append((i0, i2, i3))

        for i in range(nx):
            for j in range(ny):
                add_quad((xs[i], ys[j], z0), (xs[i], ys[j + 1], z0), (xs[i + 1], ys[j + 1], z0), (xs[i + 1], ys[j], z0))
                add_quad((xs[i], ys[j], z1), (xs[i + 1], ys[j], z1), (xs[i + 1], ys[j + 1], z1), (xs[i], ys[j + 1], z1))
        for i in range(nx):
            for k in range(nz):
                add_quad((xs[i], y0, zs[k]), (xs[i + 1], y0, zs[k]), (xs[i + 1], y0, zs[k + 1]), (xs[i], y0, zs[k + 1]))
                add_quad((xs[i], y1, zs[k]), (xs[i], y1, zs[k + 1]), (xs[i + 1], y1, zs[k + 1]), (xs[i + 1], y1, zs[k]))
        for j in range(ny):
            for k in range(nz):
                add_quad((x0, ys[j], zs[k]), (x0, ys[j], zs[k + 1]), (x0, ys[j + 1], zs[k + 1]), (x0, ys[j + 1], zs[k]))
                add_quad((x1, ys[j], zs[k]), (x1, ys[j + 1], zs[k]), (x1, ys[j + 1], zs[k + 1]), (x1, ys[j], zs[k + 1]))

        v_arr = np.array(verts, dtype=np.float64)
        t_arr = np.array(tris, dtype=np.int64)
        v_list.append(v_arr)
        t_list.append(t_arr + v_off)
        v_off += int(v_arr.shape[0])
    return RWGMeshTorch(np.concatenate(v_list, axis=0), np.concatenate(t_list, axis=0), device=dev)


def _compute_h_eff_nm(rotor: RWGMeshTorch, stator: RWGMeshTorch) -> float:
    return round(
        1000.0 * math.sqrt(float(np.sum(rotor.areas) + np.sum(stator.areas)) / (rotor.n_tri + stator.n_tri)),
        4,
    )


def run_extended_bem_convergence(
    *,
    device: str = "auto",
    n_xi: int = 16,
    max_steps: int = 0,
    checkpoint_dir: Path = ROOT / ".tmp" / "h3_ext_bem_ckpt",
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Run Tier-5 single-setup RWG BEM + Tiers 1..3 multiscale Cantor-vs-Uniform RWG BEM."""
    t0 = time.perf_counter()
    dev = resolve_torch_device(device)
    is_probe = max_steps > 0
    ckpt_root = (checkpoint_dir / f"probe_{max_steps}") if is_probe else checkpoint_dir
    ckpt_root.mkdir(parents=True, exist_ok=True)

    # 1. Tier-5 single-setup RWG BEM across all 4 channels
    r_sub = TIER5_BEM_SPEC["rotor_sub"]
    c_sub = TIER5_BEM_SPEC["collar_sub"]
    p_sub = TIER5_BEM_SPEC["pad_sub"]
    rotor_t5 = make_closed_box_rwg_mesh(ROTOR_LOBE_BOX_UM, r_sub, device=dev)
    open_stator_t5 = make_multi_box_rwg_mesh(OPEN_STATOR_COLLAR_BOXES_UM, c_sub, device=dev)
    eng_stator_t5 = make_multi_box_rwg_mesh(ENGAGED_STATOR_PAD_BOXES_UM, p_sub, device=dev)
    h_open_t5 = _compute_h_eff_nm(rotor_t5, open_stator_t5)
    h_eng_t5 = _compute_h_eff_nm(rotor_t5, eng_stator_t5)

    tier5_results: dict[str, Any] = {}
    for ch_key, st_lbl, st_mesh, mat, h_nm in (
        ("open_pec", "open_repulsive", open_stator_t5, "PEC", h_open_t5),
        ("engaged_pec", "engaged_attractive", eng_stator_t5, "PEC", h_eng_t5),
        ("open_gold", "open_repulsive", open_stator_t5, "Gold_Drude", h_open_t5),
        ("engaged_gold", "engaged_attractive", eng_stator_t5, "Gold_Drude", h_eng_t5),
    ):
        ck_file = ckpt_root / f"tier5_{ch_key}.json"
        if not is_probe and ck_file.is_file():
            res = json.loads(ck_file.read_text(encoding="utf-8"))
        else:
            res = solve_rwg_casimir_fz_pn(
                rotor_t5,
                st_mesh,
                D_EFF_SINGLE_SETUP_UM,
                material=mat,
                n_xi=n_xi,
                max_steps=max_steps,
            )
            res.update({"tier": 5, "label": TIER5_BEM_SPEC["label"], "state": st_lbl, "h_eff_nm": h_nm})
            if not is_probe:
                _atomic_write_json(ck_file, res)
        tier5_results[ch_key] = res
        print(
            f"  [Tier 5 Single-Setup] {ch_key:<13s} | DOF={res['n_total_dof']:4d} (h={res['h_eff_nm']:5.2f} nm) "
            f"| F_z = {res['F_z_total_pN']:+8.4f} pN ({res['elapsed_s']:.2f}s)",
            flush=True,
        )
        if is_probe and len(tier5_results) >= 2:
            break

    # 2. Multiscale 20 nm-lattice Cantor (3-track) vs. Iso-Area Uniform (2-track) RWG BEM Tiers 1..3
    multiscale_bem: dict[str, list[dict[str, Any]]] = {
        "cantor_pec": [],
        "uniform_pec": [],
        "cantor_gold": [],
        "uniform_gold": [],
    }
    tiers_to_run = MULTISCALE_BEM_TIERS[:1] if is_probe else MULTISCALE_BEM_TIERS
    for ts in tiers_to_run:
        t_idx = int(ts["tier"])
        f_sub = ts["fine_sub"]
        k_sub = ts["coarse_sub"]
        w_sub = ts["wall_sub"]

        cantor_rot = _make_heterogeneous_boxes_rwg_mesh(
            [
                (MULTISCALE_CANTOR_ROTOR_BOXES_UM[0], f_sub),
                (MULTISCALE_CANTOR_ROTOR_BOXES_UM[1], k_sub),
                (MULTISCALE_CANTOR_ROTOR_BOXES_UM[2], f_sub),
            ],
            dev,
        )
        cantor_sta = make_multi_box_rwg_mesh(MULTISCALE_CANTOR_STATOR_BOXES_UM, w_sub, device=dev)
        h_cantor = _compute_h_eff_nm(cantor_rot, cantor_sta)

        uni_rot = make_multi_box_rwg_mesh(UNIFORM_COARSE2_ROTOR_BOXES_UM, k_sub, device=dev)
        uni_sta = make_multi_box_rwg_mesh(UNIFORM_COARSE2_STATOR_BOXES_UM, w_sub, device=dev)
        h_uni = _compute_h_eff_nm(uni_rot, uni_sta)

        for m_key, r_m, s_m, mat, d_ch, h_nm in (
            ("cantor_pec", cantor_rot, cantor_sta, "PEC", 0.040, h_cantor),
            ("uniform_pec", uni_rot, uni_sta, "PEC", 0.080, h_uni),
            ("cantor_gold", cantor_rot, cantor_sta, "Gold_Drude", 0.040, h_cantor),
            ("uniform_gold", uni_rot, uni_sta, "Gold_Drude", 0.080, h_uni),
        ):
            ck_file = ckpt_root / f"ms_tier{t_idx}_{m_key}.json"
            if not is_probe and ck_file.is_file():
                res = json.loads(ck_file.read_text(encoding="utf-8"))
            else:
                res = solve_rwg_casimir_fz_pn(
                    r_m,
                    s_m,
                    d_ch,
                    material=mat,
                    n_xi=n_xi,
                    max_steps=max_steps,
                )
                res.update({"tier": t_idx, "design_channel": m_key, "h_eff_nm": h_nm})
                if not is_probe:
                    _atomic_write_json(ck_file, res)
            multiscale_bem[m_key].append(res)
            print(
                f"  [Multiscale Tier {t_idx}] {m_key:<13s} | DOF={res['n_total_dof']:4d} (h={res['h_eff_nm']:5.2f} nm) "
                f"| F_z = {res['F_z_total_pN']:+8.4f} pN ({res['elapsed_s']:.2f}s)",
                flush=True,
            )
            if is_probe and m_key == "uniform_pec":
                break

    if is_probe:
        probe_out = out_path or (ROOT / ".tmp" / "probe_h3_ext_bem.json")
        probe_payload = {
            "status": "micro_probe_ok",
            "elapsed_s": float(time.perf_counter() - t0),
        }
        _atomic_write_json(probe_out, probe_payload)
        return probe_payload

    # Extrapolate multiscale Cantor vs. Uniform continuum limits from Tiers 2..3
    ms_continuum: dict[str, dict[str, float]] = {}
    for m_key, rows in multiscale_bem.items():
        h2, f2 = float(rows[1]["h_eff_nm"]), float(rows[1]["F_z_total_pN"])
        h3, f3 = float(rows[2]["h_eff_nm"]), float(rows[2]["F_z_total_pN"])
        slope = (f3 - f2) / (h3 - h2)
        f_inf = f3 - slope * h3
        ms_continuum[m_key] = {
            "tier3_pN": f3,
            "continuum_pN": float(f_inf),
            "tier2_to_tier3_diff_pct": float(100.0 * abs(f3 - f2) / max(abs(f3), 1e-12)),
        }

    ms_summary = {
        "pec_tier3_gain_ratio": _safe_signed_ratio(
            ms_continuum["cantor_pec"]["tier3_pN"], ms_continuum["uniform_pec"]["tier3_pN"]
        ),
        "pec_continuum_gain_ratio": _safe_signed_ratio(
            ms_continuum["cantor_pec"]["continuum_pN"], ms_continuum["uniform_pec"]["continuum_pN"]
        ),
        "pec_continuum_delta_pN": float(
            ms_continuum["cantor_pec"]["continuum_pN"] - ms_continuum["uniform_pec"]["continuum_pN"]
        ),
        "gold_tier3_gain_ratio": _safe_signed_ratio(
            ms_continuum["cantor_gold"]["tier3_pN"], ms_continuum["uniform_gold"]["tier3_pN"]
        ),
        "gold_continuum_gain_ratio": _safe_signed_ratio(
            ms_continuum["cantor_gold"]["continuum_pN"], ms_continuum["uniform_gold"]["continuum_pN"]
        ),
        "gold_continuum_delta_pN": float(
            ms_continuum["cantor_gold"]["continuum_pN"] - ms_continuum["uniform_gold"]["continuum_pN"]
        ),
        "channels": ms_continuum,
    }

    payload = {
        "model": "Maxwell_RWG_BEM_EFIE_PMCHWT_Tier5_and_Multiscale",
        "dataset": "H3_Cantor_Extended_BEM_Convergence_20nmLattice",
        "status": "complete",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_total_s": float(time.perf_counter() - t0),
        "single_setup_tier5": tier5_results,
        "multiscale_cantor_vs_uniform_bem": multiscale_bem,
        "multiscale_summary": ms_summary,
    }
    target = out_path or (ROOT / "results" / "h3_full_convergence_extension_bem.json")
    _atomic_write_json(target, payload)
    print(f"Saved extended RWG BEM convergence -> {target} ({payload['elapsed_total_s']:.1f}s)", flush=True)
    return payload


def aggregate_extended_convergence(
    *,
    base_bem_path: Path = ROOT / "results" / "h3_single_setup_bem_convergence.json",
    ext_bem_path: Path = ROOT / "results" / "h3_full_convergence_extension_bem.json",
    base_fdtd_dir: Path = ROOT / "results" / "h3_single_setup_fdtd",
    ext_fdtd_dir: Path = ROOT / "results" / "h3_single_setup_fdtd_ext",
    out_summary_path: Path = ROOT / "results" / "h3_full_convergence_complete_summary.json",
) -> dict[str, Any]:
    """Aggregate Tiers 1..5 RWG BEM + 31 base FDTD + up to 18 extended FDTD runs."""
    if not base_bem_path.is_file() or not ext_bem_path.is_file():
        raise FileNotFoundError("Both base and extended RWG BEM JSONs are required for aggregation.")

    base_bem = json.loads(base_bem_path.read_text(encoding="utf-8"))
    ext_bem = json.loads(ext_bem_path.read_text(encoding="utf-8"))

    # Combine Tiers 1..5 for single-setup RWG BEM continuum extrapolation (linear fit on Tiers 3, 4, 5)
    five_tier_bem: dict[str, Any] = {}
    for ch_key in ("open_pec", "engaged_pec", "open_gold", "engaged_gold"):
        ladder = list(base_bem["mesh_ladder"][ch_key]) + [ext_bem["single_setup_tier5"][ch_key]]
        hs = np.array([float(r["h_eff_nm"]) for r in ladder[-3:]], dtype=np.float64)
        fs = np.array([float(r["F_z_total_pN"]) for r in ladder[-3:]], dtype=np.float64)
        A = np.vstack([np.ones_like(hs), hs]).T
        coef, *_ = np.linalg.lstsq(A, fs, rcond=None)
        f_inf_3pt = float(coef[0])
        h4, f4 = float(ladder[3]["h_eff_nm"]), float(ladder[3]["F_z_total_pN"])
        h5, f5 = float(ladder[4]["h_eff_nm"]), float(ladder[4]["F_z_total_pN"])
        f_inf_2pt = float(f5 - ((f5 - f4) / (h5 - h4)) * h5)
        se = 0.5 * abs(f_inf_3pt - f_inf_2pt) + 0.15 * abs(f5 - f4)
        five_tier_bem[ch_key] = {
            "tier4_pN": f4,
            "tier5_pN": f5,
            "tier5_dof": int(ladder[4]["n_total_dof"]),
            "tier5_h_nm": h5,
            "continuum_pN": f_inf_3pt,
            "continuum_se_pN": float(se),
            "ladder": [
                {"tier": int(r["tier"]), "h_eff_nm": float(r["h_eff_nm"]), "dof": int(r["n_total_dof"]), "F_z_pN": float(r["F_z_total_pN"])}
                for r in ladder
            ],
        }

    # Load all completed extended FDTD tasks (0..18)
    ext_fdtd_records: dict[int, dict[str, Any]] = {}
    for sp in EXT_FDTD_SWEEP_SPECS:
        p = ext_fdtd_dir / f"task_{sp.task_id}_meep.json"
        if not p.is_file():
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        v = raw.get("f_net_pN")
        if raw.get("status") == "complete" and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
            ext_fdtd_records[sp.task_id] = {
                "task_id": sp.task_id,
                "label": sp.label,
                "group": sp.group,
                "design_key": sp.design_key,
                "material": sp.material,
                "resolution": sp.resolution,
                "nmax": sp.nmax,
                "f_net_pN": float(v),
                "f_vac_pN": float(raw.get("f_vac_pN", 0.0)),
                "f_rotor_self_pN": float(raw.get("f_rotor_self_pN", 0.0)),
                "elapsed_s": float(raw.get("elapsed_wall_seconds", 0.0)),
            }

    # Load baseline single-setup convergence summary
    base_conv_summary = json.loads((ROOT / "results" / "h3_single_setup_convergence_summary.json").read_text(encoding="utf-8"))

    # Upgrade single-setup continuum agreement whenever high-(R, nmax) tasks are present
    upgraded_agreement: dict[str, Any] = {}
    high_rn_map = {
        "open_gold": (1, 2, 3),   # R200 n4, R200 n5, R250 n4
        "engaged_pec": (4, 5, 6), # R200 n4, R200 n5, R250 n4
        "open_pec": (7,),         # R200 n4
        "engaged_gold": (8,),     # R200 n4
    }
    for ch_key, base_ag in base_conv_summary["solver_agreement"].items():
        b5 = five_tier_bem[ch_key]
        t_ids = high_rn_map[ch_key]
        avail = sorted(
            (ext_fdtd_records[i] for i in t_ids if i in ext_fdtd_records),
            key=lambda r_item: (int(r_item["resolution"]), int(r_item["nmax"])),
        )
        has_high_r = any(int(r_item["resolution"]) > 150 for r_item in avail)
        if len(avail) >= 2 and has_high_r and ch_key in ("open_gold", "engaged_pec"):
            # Direct high-nmax spatial Richardson extrapolation between R=150, 200, 250 at nmax=4/5!
            m_r150 = {int(x["nmax"]): float(x["f_net_pN"]) for x in base_conv_summary["fdtd_multipole_ladders"][ch_key]}
            # Fit P(3, alpha * nmax) completeness factor at R=150
            ns = np.array([2.0, 3.0, 4.0, 5.0])
            ys = np.array([m_r150[int(n)] for n in ns])
            popt, _ = curve_fit(
                lambda n, finf, a: finf * gammainc(3.0, a * n),
                ns,
                np.abs(ys),
                p0=[abs(ys[-1]) * 1.04, 1.15],
                bounds=([abs(ys[-1]) * 0.9, 0.2], [abs(ys[-1]) * 2.5, 5.0]),
                maxfev=10000,
            )
            alpha_fit = float(popt[1])
            # Correct each high-R point by its analytical 1 / P(3, alpha * nmax) tail factor
            by_r: dict[int, float] = {150: m_r150[5] / float(gammainc(3.0, 5.0 * alpha_fit))}
            for rec_a in avail:
                c_fac = max(float(gammainc(3.0, float(rec_a["nmax"]) * alpha_fit)), 1.0e-9)
                by_r[int(rec_a["resolution"])] = float(rec_a["f_net_pN"]) / c_fac
            r_sorted = sorted(by_r.keys())
            if len(r_sorted) < 2:
                raise RuntimeError(f"Expected >=2 distinct spatial resolutions for {ch_key}, got {r_sorted}")
            r1, r2 = r_sorted[-2], r_sorted[-1]
            f1, f2 = by_r[r1], by_r[r2]
            dx1_2, dx2_2 = (1.0 / r1) ** 2, (1.0 / r2) ** 2
            fdtd_inf = float(f2 + (f2 - f1) * dx2_2 / (dx1_2 - dx2_2))
            fdtd_se = float(0.5 * abs(fdtd_inf - f2) + 0.02 * abs(fdtd_inf))
            finest_rec = max(avail, key=lambda x: (x["resolution"], x["nmax"]))
            fdtd_finest = float(finest_rec["f_net_pN"])
            rel_diff = abs(fdtd_inf - b5["continuum_pN"]) / max(abs(b5["continuum_pN"]), 1e-12) * 100.0
            upgraded_agreement[ch_key] = {
                "bem_tier5_pN": b5["tier5_pN"],
                "bem_continuum_pN": b5["continuum_pN"],
                "bem_continuum_se_pN": b5["continuum_se_pN"],
                "fdtd_finest_direct_pN": fdtd_finest,
                "fdtd_finest_R": finest_rec["resolution"],
                "fdtd_finest_nmax": finest_rec["nmax"],
                "fdtd_continuum_pN": fdtd_inf,
                "fdtd_continuum_se_pN": fdtd_se,
                "continuum_rel_diff_pct": float(rel_diff),
                "mode": "coupled_high_R_high_nmax",
            }
        else:
            fdtd_inf = float(base_ag["fdtd_continuum_pN"])
            fdtd_se = float(base_ag["fdtd_continuum_se_pN"])
            rel_diff = abs(fdtd_inf - b5["continuum_pN"]) / max(abs(b5["continuum_pN"]), 1e-12) * 100.0
            upgraded_agreement[ch_key] = {
                "bem_tier5_pN": b5["tier5_pN"],
                "bem_continuum_pN": b5["continuum_pN"],
                "bem_continuum_se_pN": b5["continuum_se_pN"],
                "fdtd_finest_direct_pN": float(base_ag["fdtd_finest_pN"]),
                "fdtd_finest_R": int(base_ag["fdtd_spatial_finest_R"]),
                "fdtd_finest_nmax": int(base_ag["fdtd_finest_nmax"]),
                "fdtd_continuum_pN": fdtd_inf,
                "fdtd_continuum_se_pN": fdtd_se,
                "continuum_rel_diff_pct": float(rel_diff),
                "mode": "tier5_bem_plus_baseline_31_fdtd",
            }

    # Domain invariance checks (Tasks 9..12 vs baseline Tasks 6 and 25)
    base_pec_r150_n3 = float(base_conv_summary["nmax_source_convergence"]["h3_ss_open_pec_R150_nmax3"])
    base_gold_r150_n3 = float(base_conv_summary["nmax_source_convergence"]["h3_ss_open_gold_R150_nmax3"])
    domain_checks: dict[str, Any] = {}
    for tid, name, ref_val in (
        (9, "Trun_8_vs_4_open_pec", base_pec_r150_n3),
        (10, "Trun_8_vs_4_open_gold", base_gold_r150_n3),
        (11, "buffer_140nm_vs_80nm_open_pec", base_pec_r150_n3),
        (12, "pml_240nm_vs_160nm_open_pec", base_pec_r150_n3),
    ):
        if tid in ext_fdtd_records:
            val = ext_fdtd_records[tid]["f_net_pN"]
            domain_checks[name] = {
                "control_pN": val,
                "baseline_pN": ref_val,
                "rel_drift_pct": float(100.0 * abs(val - ref_val) / max(abs(ref_val), 1e-12)),
            }

    # Multiscale Cantor vs. Uniform FDTD comparison (Tasks 13..18)
    multiscale_fdtd: dict[str, Any] = {}
    if 15 in ext_fdtd_records and 16 in ext_fdtd_records:
        c_pec = ext_fdtd_records[15]["f_net_pN"]
        u_pec = ext_fdtd_records[16]["f_net_pN"]
        multiscale_fdtd["pec_R150_n3"] = {
            "cantor_pN": c_pec,
            "uniform_pN": u_pec,
            "delta_pN": float(c_pec - u_pec),
            "fdtd_gain_ratio": _safe_signed_ratio(c_pec, u_pec),
            "rwg_bem_tier3_gain_ratio": ext_bem["multiscale_summary"]["pec_tier3_gain_ratio"],
        }
    if 17 in ext_fdtd_records and 18 in ext_fdtd_records:
        c_au = ext_fdtd_records[17]["f_net_pN"]
        u_au = ext_fdtd_records[18]["f_net_pN"]
        multiscale_fdtd["gold_R150_n3"] = {
            "cantor_pN": c_au,
            "uniform_pN": u_au,
            "delta_pN": float(c_au - u_au),
            "fdtd_gain_ratio": _safe_signed_ratio(c_au, u_au),
            "rwg_bem_tier3_gain_ratio": ext_bem["multiscale_summary"]["gold_tier3_gain_ratio"],
        }

    complete_summary = {
        "model": "Complete_5Tier_RWG_BEM_and_49Task_Meep_FDTD_Convergence",
        "dataset": "H3_Cantor_SingleSetup_and_Multiscale_20nmLattice",
        "status": "complete" if len(ext_fdtd_records) == len(EXT_FDTD_SWEEP_SPECS) else "bem_complete_fdtd_partial",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "completed_base_fdtd_tasks": 31,
        "completed_ext_fdtd_tasks": len(ext_fdtd_records),
        "expected_ext_fdtd_tasks": len(EXT_FDTD_SWEEP_SPECS),
        "five_tier_single_setup_bem": five_tier_bem,
        "multiscale_rwg_bem": ext_bem["multiscale_summary"],
        "upgraded_solver_agreement": upgraded_agreement,
        "fdtd_domain_invariance_controls": domain_checks,
        "multiscale_fdtd_vs_bem": multiscale_fdtd,
        "ext_fdtd_tasks": [ext_fdtd_records[k] for k in sorted(ext_fdtd_records)],
    }
    _atomic_write_json(out_summary_path, complete_summary)
    _log_extended_convergence_macros(complete_summary, out_summary_path)
    print(
        f"Aggregated extended convergence ({len(ext_fdtd_records)}/{len(EXT_FDTD_SWEEP_SPECS)} ext FDTD tasks) -> {out_summary_path}",
        flush=True,
    )
    return complete_summary


def _log_extended_convergence_macros(summary: Mapping[str, Any], summary_path: Path) -> None:
    step_id = "h3_extended_bem_fdtd_convergence"
    set_solver_provenance(
        "Maxwell_RWG_5Tier_and_Multiscale_BEM_FDTD",
        {
            "completed_ext_fdtd_tasks": summary["completed_ext_fdtd_tasks"],
            "expected_ext_fdtd_tasks": summary["expected_ext_fdtd_tasks"],
        },
    )
    log_step(
        step_id,
        {
            "status": summary["status"],
            "completed_ext_fdtd_tasks": summary["completed_ext_fdtd_tasks"],
            "source_json": _rel_root_str(summary_path),
        },
    )

    kv: dict[str, str | int | float] = {}
    b5 = summary["five_tier_single_setup_bem"]
    for ch_key, pfx in (
        ("open_pec", "conv_ext_open_pec"),
        ("engaged_pec", "conv_ext_eng_pec"),
        ("open_gold", "conv_ext_open_gold"),
        ("engaged_gold", "conv_ext_eng_gold"),
    ):
        kv[f"{pfx}_bem_t5_pn"] = f"{b5[ch_key]['tier5_pN']:+.3f}"
        kv[f"{pfx}_bem_t5_dof"] = int(b5[ch_key]["tier5_dof"])
        kv[f"{pfx}_bem_inf5_pn"] = f"{b5[ch_key]['continuum_pN']:+.3f}"
        kv[f"{pfx}_bem_se5_pn"] = f"{b5[ch_key]['continuum_se_pN']:.3f}"
        ag = summary["upgraded_solver_agreement"][ch_key]
        kv[f"{pfx}_fdtd_inf_pn"] = f"{ag['fdtd_continuum_pN']:+.3f}"
        kv[f"{pfx}_rel_diff_pct"] = f"{ag['continuum_rel_diff_pct']:.1f}"

    ms = summary["multiscale_rwg_bem"]
    kv["conv_ms_cantor_pec_t3_pn"] = f"{ms['channels']['cantor_pec']['tier3_pN']:+.3f}"
    kv["conv_ms_uniform_pec_t3_pn"] = f"{ms['channels']['uniform_pec']['tier3_pN']:+.3f}"
    kv["conv_ms_pec_gain_ratio"] = _fmt_ratio_macro(ms["pec_continuum_gain_ratio"])
    kv["conv_ms_cantor_gold_t3_pn"] = f"{ms['channels']['cantor_gold']['tier3_pN']:+.3f}"
    kv["conv_ms_uniform_gold_t3_pn"] = f"{ms['channels']['uniform_gold']['tier3_pN']:+.3f}"
    kv["conv_ms_gold_gain_ratio"] = _fmt_ratio_macro(ms["gold_continuum_gain_ratio"])

    dom = summary["fdtd_domain_invariance_controls"]
    if "Trun_8_vs_4_open_pec" in dom:
        kv["conv_dom_trun_pec_drift_pct"] = f"{dom['Trun_8_vs_4_open_pec']['rel_drift_pct']:.2f}"
    if "Trun_8_vs_4_open_gold" in dom:
        kv["conv_dom_trun_gold_drift_pct"] = f"{dom['Trun_8_vs_4_open_gold']['rel_drift_pct']:.2f}"
    if "buffer_140nm_vs_80nm_open_pec" in dom:
        kv["conv_dom_buf_pec_drift_pct"] = f"{dom['buffer_140nm_vs_80nm_open_pec']['rel_drift_pct']:.2f}"
    if "pml_240nm_vs_160nm_open_pec" in dom:
        kv["conv_dom_pml_pec_drift_pct"] = f"{dom['pml_240nm_vs_160nm_open_pec']['rel_drift_pct']:.2f}"

    ms_f = summary["multiscale_fdtd_vs_bem"]
    if "pec_R150_n3" in ms_f:
        kv["conv_ms_fdtd_cantor_pec_pn"] = f"{ms_f['pec_R150_n3']['cantor_pN']:+.3f}"
        kv["conv_ms_fdtd_uniform_pec_pn"] = f"{ms_f['pec_R150_n3']['uniform_pN']:+.3f}"
        kv["conv_ms_fdtd_pec_gain_ratio"] = _fmt_ratio_macro(ms_f["pec_R150_n3"]["fdtd_gain_ratio"])
    if "gold_R150_n3" in ms_f:
        kv["conv_ms_fdtd_cantor_gold_pn"] = f"{ms_f['gold_R150_n3']['cantor_pN']:+.3f}"
        kv["conv_ms_fdtd_uniform_gold_pn"] = f"{ms_f['gold_R150_n3']['uniform_pN']:+.3f}"
        kv["conv_ms_fdtd_gold_gain_ratio"] = _fmt_ratio_macro(ms_f["gold_R150_n3"]["fdtd_gain_ratio"])

    items = list(kv.items())
    for idx_i, (k, v) in enumerate(items):
        log_metric(k, v, step_id=step_id, defer_save=(idx_i < len(items) - 1))
    export_macros()
    macros_paper = ROOT / "Papers" / "FCE_Nature_ver01" / "macros_results.tex"
    if macros_paper.parent.exists():
        export_macros(output_path=str(macros_paper))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-fdtd-configs", action="store_true")
    parser.add_argument("--run-bem", action="store_true")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--n-xi", type=int, default=16)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=ROOT / ".tmp" / "h3_ext_bem_ckpt",
    )
    args = parser.parse_args(argv)

    if args.aggregate and args.max_steps > 0:
        parser.error("--aggregate cannot be combined with --max-steps > 0 micro-probe mode.")
    if not (args.write_fdtd_configs or args.run_bem or args.aggregate):
        if args.max_steps > 0:
            args.run_bem = True
        else:
            parser.error("Specify at least one of --write-fdtd-configs, --run-bem, --aggregate, or --max-steps > 0.")

    if args.write_fdtd_configs:
        written = write_extended_fdtd_configs()
        print(f"Wrote {len(written)} extended FDTD configs -> sweep_configs_h3_single_setup_fdtd_ext/", flush=True)
    if args.run_bem:
        run_extended_bem_convergence(
            device=args.device,
            n_xi=args.n_xi,
            max_steps=args.max_steps,
            checkpoint_dir=args.checkpoint_dir,
        )
    if args.aggregate:
        aggregate_extended_convergence()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
