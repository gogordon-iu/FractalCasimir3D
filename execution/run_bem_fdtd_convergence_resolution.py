#!/usr/bin/env python3
"""
Decouple 3D BEM frequency quadrature vs. spatial panel refinement, evaluate
rectangular aspect-ratio self-term corrections, and generate the BigRed 200
3D FDTD Meep convergence-control configuration suite (fixed stress-box margin,
nmax=2 2x2 DCT face-mode check, dispersive Gold skin-depth regularization,
and Cartesian-aligned rectilinear_xz control geometry).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import execution.casimir_bem_solver as cbs
from execution.casimir_bem_solver import (
    BEM_TIER_HIGH,
    BEM_TIER_STANDARD,
    BEM_TIER_ULTRA_HIGH,
    run_bem_casimir_solver,
)
from execution.clutch_geometry_redesign import (
    DEFAULT_APERTURE_ARC_DEG,
    DEFAULT_BRIDGE_ARC_DEG,
    DEFAULT_H_TEETH_ROTATIONAL_UM,
    DEFAULT_HYBRID_L2_H_TEETH_UM,
    DEFAULT_HYBRID_L2_Z_TIP_UM,
    DEFAULT_MIN_TOOTH_W_UM,
    DEFAULT_NUM_SECTORS,
    DEFAULT_R_MAX_UM,
    DEFAULT_R_MIN_UM,
    DEFAULT_T_LANDING_PAD_UM,
    DEFAULT_T_MEMBRANE_UM,
    DEFAULT_TOOTH_ARC_DEG,
    DEFAULT_TOOTH_CENTER_OFFSET_DEG,
    DEFAULT_W1_RATIO,
    DEFAULT_Z_PAD_TOP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
    compute_dynamic_Trun,
    get_scoped_clutch_elements,
)
from execution.run_fractal_advantage_study import (
    build_designs,
    build_study_clutch_mesh,
)
from execution.run_nature_feasibility_and_stability import (
    load_backend,
    prepare_designs,
    vertical_force,
)


HYBRID_CANTOR_Z_TIPS_UM: tuple[float, float, float] = (
    DEFAULT_HYBRID_L2_Z_TIP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
    DEFAULT_HYBRID_L2_Z_TIP_UM,
)
HYBRID_CANTOR_H_TEETH_UM: tuple[float, float, float] = (
    DEFAULT_HYBRID_L2_H_TEETH_UM,
    DEFAULT_H_TEETH_ROTATIONAL_UM,
    DEFAULT_HYBRID_L2_H_TEETH_UM,
)
FIXED_STRESS_BOX_MARGIN_UM = 0.010


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def rectangle_self_factor_ratio(aspect_ratio: np.ndarray) -> np.ndarray:
    """Ratio of exact rectangular-patch center-collocation self-integral to equal-area disk.

    For a rectangle of sides (a, b) with area A = a*b and aspect ratio rho = max(a, b) / min(a, b) >= 1,
    the exact center-collocation potential integral I_rect / sqrt(A) is:
        (1 / (2*pi)) * [ (1/sqrt(rho))*asinh(rho) + sqrt(rho)*asinh(1/rho) ]
    Normalized by the equal-area disk center-collocation value 1 / (2 * sqrt(pi)) = 0.28209479,
    this gives (2 * asinh(1)) / sqrt(pi) = 0.99452383 at rho = 1.
    """
    rho = np.maximum(np.asarray(aspect_ratio, dtype=np.float64), 1.0)
    inv_rho = 1.0 / rho
    sqrt_rho = np.sqrt(rho)
    term1 = np.arcsinh(rho) / sqrt_rho
    term2 = sqrt_rho * np.arcsinh(inv_rho)
    i_rect = (term1 + term2) / (2.0 * math.pi)
    i_disk = 1.0 / (2.0 * math.sqrt(math.pi))
    return i_rect / i_disk


def estimate_panel_aspect_ratios(quad_points: np.ndarray) -> np.ndarray:
    """Compute effective tangent-frame aspect ratios from bilinear 2x2 Gauss-Legendre nodes.

    For bilinear/annular panels with nodes (u-,v-), (u-,v+), (u+,v-), (u+,v+) at +/-1/sqrt(3),
    averaging opposite node pairs yields the exact center Jacobian tangent lengths scaled by 2/sqrt(3),
    whose ratio equals the panel's local metric aspect ratio.
    """
    du = 0.5 * (
        np.linalg.norm(quad_points[:, 2, :] - quad_points[:, 0, :], axis=1)
        + np.linalg.norm(quad_points[:, 3, :] - quad_points[:, 1, :], axis=1)
    )
    dv = 0.5 * (
        np.linalg.norm(quad_points[:, 1, :] - quad_points[:, 0, :], axis=1)
        + np.linalg.norm(quad_points[:, 3, :] - quad_points[:, 2, :], axis=1)
    )
    short = np.maximum(np.minimum(du, dv), 1e-9)
    long = np.maximum(np.maximum(du, dv), short)
    return long / short


def build_cantor_n2_hybrid_elements() -> list[dict[str, Any]]:
    raw_elements = get_scoped_clutch_elements(
        N=2,
        R_min=DEFAULT_R_MIN_UM,
        R_max=DEFAULT_R_MAX_UM,
        w1_ratio=DEFAULT_W1_RATIO,
        min_tooth_w=DEFAULT_MIN_TOOTH_W_UM,
    )
    elements: list[dict[str, Any]] = []
    for idx, el in enumerate(raw_elements):
        item = dict(el)
        item["z_tip"] = float(HYBRID_CANTOR_Z_TIPS_UM[idx])
        item["h_teeth"] = float(HYBRID_CANTOR_H_TEETH_UM[idx])
        elements.append(item)
    return elements


def generate_bigred200_meep_configs(config_dir: Path) -> list[dict[str, Any]]:
    """Write the 12 convergence-control Meep JSON configs for BigRed 200."""
    config_dir = config_dir.resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    elements = build_cantor_n2_hybrid_elements()
    d_eff = min(
        min(abs(el["z_tip"] - DEFAULT_Z_PAD_TOP_UM) for el in elements),
        min((el["W_slot"] - el["w_tooth"]) / 2.0 for el in elements),
    )
    t_run, _ = compute_dynamic_Trun(d_eff)

    specs: list[dict[str, Any]] = [
        # Group A: Fixed stress-box margin (10 nm) across R=40, 50, 60, 80 (cylindrical PEC)
        {"task_id": 1, "label": "cyl_PEC_fixedbox_R40_nmax1", "resolution": 40, "nmax": 1, "material": "PEC", "geometry_mode": "cylindrical"},
        {"task_id": 2, "label": "cyl_PEC_fixedbox_R50_nmax1", "resolution": 50, "nmax": 1, "material": "PEC", "geometry_mode": "cylindrical"},
        {"task_id": 3, "label": "cyl_PEC_fixedbox_R60_nmax1", "resolution": 60, "nmax": 1, "material": "PEC", "geometry_mode": "cylindrical"},
        {"task_id": 4, "label": "cyl_PEC_fixedbox_R80_nmax1", "resolution": 80, "nmax": 1, "material": "PEC", "geometry_mode": "cylindrical"},
        # Group B: Higher-order 2D DCT face-mode check (range(nmax) per face axis -> nmax^2 = 4 modes/face -> 432 moments/pass = 1728 moments)
        {"task_id": 5, "label": "cyl_PEC_fixedbox_R50_nmax2", "resolution": 50, "nmax": 2, "material": "PEC", "geometry_mode": "cylindrical"},
        {"task_id": 6, "label": "cyl_PEC_fixedbox_R60_nmax2", "resolution": 60, "nmax": 2, "material": "PEC", "geometry_mode": "cylindrical"},
        # Group C: Dispersive Gold skin-depth corner regularization
        {"task_id": 7, "label": "cyl_Gold_fixedbox_R50_nmax1", "resolution": 50, "nmax": 1, "material": "Gold", "geometry_mode": "cylindrical"},
        {"task_id": 8, "label": "cyl_Gold_fixedbox_R60_nmax1", "resolution": 60, "nmax": 1, "material": "Gold", "geometry_mode": "cylindrical"},
        # Group D: Cartesian-aligned 3D rectilinear fractal control (zero cylindrical staircasing)
        {"task_id": 9, "label": "rect_PEC_fixedbox_R40_nmax1", "resolution": 40, "nmax": 1, "material": "PEC", "geometry_mode": "rectilinear_xz"},
        {"task_id": 10, "label": "rect_PEC_fixedbox_R50_nmax1", "resolution": 50, "nmax": 1, "material": "PEC", "geometry_mode": "rectilinear_xz"},
        {"task_id": 11, "label": "rect_PEC_fixedbox_R60_nmax1", "resolution": 60, "nmax": 1, "material": "PEC", "geometry_mode": "rectilinear_xz"},
        {"task_id": 12, "label": "rect_PEC_fixedbox_R80_nmax1", "resolution": 80, "nmax": 1, "material": "PEC", "geometry_mode": "rectilinear_xz"},
        # Group E: 4-6 effective cells across smallest 15 nm gap (R=270 -> dx=3.70 nm [4.05 cells], R=400 -> dx=2.50 nm [6.0 cells]) + conformal eps_averaging
        {"task_id": 13, "label": "cyl_GoldDrude_fixedbox_R270_nmax2", "resolution": 270, "nmax": 2, "material": "Gold_Drude", "geometry_mode": "cylindrical"},
        {"task_id": 14, "label": "cyl_GoldDrude_fixedbox_R400_nmax2", "resolution": 400, "nmax": 2, "material": "Gold_Drude", "geometry_mode": "cylindrical"},
        {"task_id": 15, "label": "cyl_GoldDrude_fixedbox_R120_subpixel_nmax2", "resolution": 120, "nmax": 2, "material": "Gold_Drude", "geometry_mode": "cylindrical", "eps_averaging": True},
        # Group F: Higher-order DCT basis convergence (nmax=3 -> 972 moments/pass, nmax=4 -> 1728 moments/pass)
        {"task_id": 16, "label": "cyl_PEC_fixedbox_R60_nmax3", "resolution": 60, "nmax": 3, "material": "PEC", "geometry_mode": "cylindrical"},
        {"task_id": 17, "label": "cyl_PEC_fixedbox_R60_nmax4", "resolution": 60, "nmax": 4, "material": "PEC", "geometry_mode": "cylindrical"},
        # Group G: PML thickness (0.40 um), cell buffer padding (0.30 um), and runtime (1.5x T_run) convergence
        {"task_id": 18, "label": "cyl_GoldDrude_fixedbox_R60_nmax2_pml040_buf030_trun15x", "resolution": 60, "nmax": 2, "material": "Gold_Drude", "geometry_mode": "cylindrical", "pml_thickness_um": 0.40, "cell_buffer_um": 0.30, "t_run_scale": 1.5},
        # Group H: Identical single-pole Drude Gold dispersion in BEM and FDTD (omega_p=9.03 eV, gamma=0.053 eV)
        {"task_id": 19, "label": "cyl_GoldDrude_fixedbox_R60_nmax1", "resolution": 60, "nmax": 1, "material": "Gold_Drude", "geometry_mode": "cylindrical"},
        {"task_id": 20, "label": "cyl_GoldDrude_fixedbox_R60_nmax2", "resolution": 60, "nmax": 2, "material": "Gold_Drude", "geometry_mode": "cylindrical"},
        # Group I: Rounded-edge (r_edge = 5 nm) F3-111 vs. C9-Shuf12 12-tooth control pair
        {"task_id": 21, "label": "f3_111_r5nm_GoldDrude_fixedbox_R270_nmax2", "resolution": 270, "nmax": 2, "material": "Gold_Drude", "geometry_mode": "cylindrical", "design_override": "F3_111", "r_edge_nm": 5.0},
        {"task_id": 22, "label": "c9_shuf12_r5nm_GoldDrude_fixedbox_R270_nmax2", "resolution": 270, "nmax": 2, "material": "Gold_Drude", "geometry_mode": "cylindrical", "design_override": "C9_Shuf12", "r_edge_nm": 5.0},
    ]

    manifest_rows: list[dict[str, Any]] = []
    for spec in specs:
        task_id = int(spec["task_id"])
        t_scale = float(spec.get("t_run_scale", 1.0))
        pml_um = float(spec.get("pml_thickness_um", 0.25))
        buf_um = float(spec.get("cell_buffer_um", 0.15))
        eps_avg = bool(spec.get("eps_averaging", False))
        r_edge_nm = float(spec.get("r_edge_nm", 0.0))
        des_name = str(
            spec.get(
                "design_override",
                "Rectilinear_Cantor_N2_HybridXZ"
                if spec["geometry_mode"] == "rectilinear_xz"
                else "Cantor_N2_HybridRZ",
            )
        )
        cfg = {
            "task_id": task_id,
            "design_name": des_name,
            "control_label": spec["label"],
            "N_fractal": 3 if des_name in ("F3_111", "C9_Shuf12") else 2,
            "theta_deg": 3.0,
            "tooth_center_offset_deg": DEFAULT_TOOTH_CENTER_OFFSET_DEG,
            "num_sectors": DEFAULT_NUM_SECTORS,
            "aperture_arc_deg": DEFAULT_APERTURE_ARC_DEG,
            "bridge_arc_deg": DEFAULT_BRIDGE_ARC_DEG,
            "tooth_arc_deg": DEFAULT_TOOTH_ARC_DEG,
            "t_membrane_um": DEFAULT_T_MEMBRANE_UM,
            "t_landing_pad_um": DEFAULT_T_LANDING_PAD_UM,
            "H_teeth_um": float(max(el["h_teeth"] for el in elements)),
            "z_tip_um": float(min(el["z_tip"] for el in elements)),
            "hybrid_z_tips_um": [float(el["z_tip"]) for el in elements],
            "hybrid_h_teeth_um": [float(el["h_teeth"]) for el in elements],
            "z_pad_top_um": DEFAULT_Z_PAD_TOP_UM,
            "L_domain_um": 3.6 if des_name in ("F3_111", "C9_Shuf12") else 3.2,
            "pml_thickness_um": pml_um,
            "cell_buffer_um": buf_um,
            "courant": 0.5,
            "T_run": t_run * t_scale,
            "d_eff_um": d_eff,
            "resolution": int(spec["resolution"]),
            "nmax": int(spec["nmax"]),
            "material": str(spec["material"]),
            "stress_box_mode": "per_tooth_rotor_frame",
            "fixed_stress_box_margin_um": FIXED_STRESS_BOX_MARGIN_UM,
            "eps_averaging": eps_avg,
            "r_edge_nm": r_edge_nm,
            "geometry_mode": str(spec["geometry_mode"]),
            "force_complex_fields": True,
            "geometry": {
                "elements": elements,
            },
        }
        cfg_path = config_dir / f"config_{task_id:03d}.json"
        atomic_write_json(cfg_path, cfg)
        n_teeth_sector = 12 if des_name in ("F3_111", "C9_Shuf12") else len(elements)
        manifest_rows.append(
            {
                "task_id": task_id,
                "config_file": str(cfg_path.relative_to(ROOT)).replace("\\", "/"),
                "label": spec["label"],
                "design_name": des_name,
                "resolution": spec["resolution"],
                "nmax": spec["nmax"],
                "material": spec["material"],
                "geometry_mode": spec["geometry_mode"],
                "eps_averaging": eps_avg,
                "pml_thickness_um": pml_um,
                "cell_buffer_um": buf_um,
                "t_run_scale": t_scale,
                "r_edge_nm": r_edge_nm,
                "fixed_stress_box_margin_um": FIXED_STRESS_BOX_MARGIN_UM,
                "moments_per_pass": 6 * n_teeth_sector * 6 * (int(spec["nmax"]) ** 2),
                "moments_total_4pass": 4 * 6 * n_teeth_sector * 6 * (int(spec["nmax"]) ** 2),
            }
        )
    return manifest_rows


QUANT_FDTD_N2_STRESS_BOX_MARGIN_UM = 0.0075
QUANT_FDTD_N2_R_EDGE_NM = 5.0
QUANT_FDTD_N2_PML_THICKNESS_UM = 0.20
QUANT_FDTD_N2_CELL_BUFFER_UM = 0.15


def study_design_to_meep_elements(design: Any) -> list[dict[str, Any]]:
    """Convert a 3-track N=2 StudyDesign into Meep ClutchElement dicts."""
    elements: list[dict[str, Any]] = []
    for idx, tr in enumerate(design.tracks):
        r_inner = float(tr.r_inner)
        r_outer = float(tr.r_outer)
        r_tooth_in = float(tr.r_tooth_in)
        r_tooth_out = float(tr.r_tooth_out)
        elements.append(
            {
                "level": int(tr.level),
                "r_inner": r_inner,
                "r_outer": r_outer,
                "W_slot": r_outer - r_inner,
                "r_tooth_in": r_tooth_in,
                "r_tooth_out": r_tooth_out,
                "w_tooth": r_tooth_out - r_tooth_in,
                "r_center": 0.5 * (r_tooth_in + r_tooth_out),
                "z_tip": float(tr.z_tip),
                "h_teeth": float(tr.h_teeth),
                "track_index": idx,
            }
        )
    return elements


def generate_quant_fdtd_n2_configs(
    config_dir: Path,
    designs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate the 8 Sector-0 cropped, r_edge=5nm N=2 quantitative FDTD vs BEM configs.

    Pairs Cantor_N2_HybridRZ (multi-scale radial+axial Cantor hierarchy, g_r = 21.49 nm / 62.32 nm)
    against Ctrl_UniformPeriodic (matched 3-slot uniform periodic control, g_r = 35.10 nm)
    at r_edge = 5 nm, single-pole Gold_Drude, fixed 7.5 nm stress-box margin, and Sector-0
    cropped domain across R in {100, 150, 200} (nmax=2) and R=150 (nmax=3).
    """
    config_dir = config_dir.resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    study_by_name = {d.name: d for d in build_designs()}
    if "Cantor_RZ_ScaleMatched" in study_by_name:
        study_by_name["Cantor_N2_HybridRZ"] = study_by_name["Cantor_RZ_ScaleMatched"]
    if designs is not None:
        for k, v in designs.items():
            study_by_name.setdefault(k, v)

    delta_w_r5nm = -2.0 * (1.0 - math.pi / 4.0) * (QUANT_FDTD_N2_R_EDGE_NM * 1e-3)
    specs: list[dict[str, Any]] = [
        {"task_id": 1, "design_name": "Cantor_N2_HybridRZ", "resolution": 100, "nmax": 2, "label": "quant_n2_cantor_r5nm_R100_nmax2"},
        {"task_id": 2, "design_name": "Ctrl_UniformPeriodic", "resolution": 100, "nmax": 2, "label": "quant_n2_uniform_r5nm_R100_nmax2"},
        {"task_id": 3, "design_name": "Cantor_N2_HybridRZ", "resolution": 150, "nmax": 2, "label": "quant_n2_cantor_r5nm_R150_nmax2"},
        {"task_id": 4, "design_name": "Ctrl_UniformPeriodic", "resolution": 150, "nmax": 2, "label": "quant_n2_uniform_r5nm_R150_nmax2"},
        {"task_id": 5, "design_name": "Cantor_N2_HybridRZ", "resolution": 200, "nmax": 2, "label": "quant_n2_cantor_r5nm_R200_nmax2"},
        {"task_id": 6, "design_name": "Ctrl_UniformPeriodic", "resolution": 200, "nmax": 2, "label": "quant_n2_uniform_r5nm_R200_nmax2"},
        {"task_id": 7, "design_name": "Cantor_N2_HybridRZ", "resolution": 150, "nmax": 3, "label": "quant_n2_cantor_r5nm_R150_nmax3"},
        {"task_id": 8, "design_name": "Ctrl_UniformPeriodic", "resolution": 150, "nmax": 3, "label": "quant_n2_uniform_r5nm_R150_nmax3"},
    ]

    manifest_rows: list[dict[str, Any]] = []
    for spec in specs:
        task_id = int(spec["task_id"])
        des_name = str(spec["design_name"])
        des = study_by_name[des_name]
        elements = study_design_to_meep_elements(des)
        min_radial_gap_um = min(
            (el["W_slot"] - (el["w_tooth"] + delta_w_r5nm)) / 2.0 for el in elements
        )
        min_axial_gap_um = min(abs(el["z_tip"] - float(des.z_pad_top)) for el in elements)
        d_eff = min(min_radial_gap_um, min_axial_gap_um)
        t_run, _ = compute_dynamic_Trun(d_eff)
        aperture_deg = float(des.aperture_arc_deg)
        pitch_deg = 360.0 / float(DEFAULT_NUM_SECTORS)
        bridge_deg = pitch_deg - aperture_deg
        res = int(spec["resolution"])
        nmax = int(spec["nmax"])

        cfg = {
            "task_id": task_id,
            "design_name": des_name,
            "control_label": str(spec["label"]),
            "N_fractal": 2,
            "theta_deg": 3.0,
            "tooth_center_offset_deg": DEFAULT_TOOTH_CENTER_OFFSET_DEG,
            "num_sectors": DEFAULT_NUM_SECTORS,
            "aperture_arc_deg": aperture_deg,
            "bridge_arc_deg": bridge_deg,
            "tooth_arc_deg": float(des.tooth_arc_deg),
            "t_membrane_um": float(des.t_membrane),
            "t_landing_pad_um": float(des.t_landing_pad),
            "H_teeth_um": float(max(el["h_teeth"] for el in elements)),
            "z_tip_um": float(min(el["z_tip"] for el in elements)),
            "hybrid_z_tips_um": [float(el["z_tip"]) for el in elements],
            "hybrid_h_teeth_um": [float(el["h_teeth"]) for el in elements],
            "z_pad_top_um": float(des.z_pad_top),
            "L_domain_um": 3.2,
            "pml_thickness_um": QUANT_FDTD_N2_PML_THICKNESS_UM,
            "cell_buffer_um": QUANT_FDTD_N2_CELL_BUFFER_UM,
            "courant": 0.5,
            "T_run": float(t_run),
            "d_eff_um": float(d_eff),
            "resolution": res,
            "nmax": nmax,
            "material": "Gold_Drude",
            "stress_box_mode": "per_tooth_rotor_frame",
            "fixed_stress_box_margin_um": QUANT_FDTD_N2_STRESS_BOX_MARGIN_UM,
            "eps_averaging": False,
            "r_edge_nm": QUANT_FDTD_N2_R_EDGE_NM,
            "sector0_crop": True,
            "geometry_mode": "cylindrical",
            "force_complex_fields": True,
            "geometry": {
                "elements": elements,
            },
        }
        cfg_path = config_dir / f"config_{task_id:03d}.json"
        atomic_write_json(cfg_path, cfg)
        dx_nm = 1000.0 / float(res)
        manifest_rows.append(
            {
                "task_id": task_id,
                "config_file": str(cfg_path.relative_to(ROOT)).replace("\\", "/"),
                "label": str(spec["label"]),
                "design_name": des_name,
                "resolution": res,
                "dx_nm": round(dx_nm, 3),
                "min_radial_gap_nm": round(1000.0 * min_radial_gap_um, 2),
                "cells_across_min_gap": round((1000.0 * min_radial_gap_um) / dx_nm, 2),
                "nmax": nmax,
                "material": "Gold_Drude",
                "r_edge_nm": QUANT_FDTD_N2_R_EDGE_NM,
                "sector0_crop": True,
                "fixed_stress_box_margin_um": QUANT_FDTD_N2_STRESS_BOX_MARGIN_UM,
                "moments_per_pass": 6 * len(elements) * 6 * (nmax ** 2),
                "moments_total_4pass": 4 * 6 * len(elements) * 6 * (nmax ** 2),
            }
        )
    return manifest_rows


RAKIC_GOLD_F0 = 0.760
RAKIC_GOLD_WP_EV = 9.03
RAKIC_GOLD_GAMMA0_EV = 0.053
RAKIC_GOLD_INTERBAND_POLES: tuple[tuple[float, float, float], ...] = (
    (0.024, 0.415, 0.241),
    (0.010, 0.830, 0.345),
    (0.071, 2.969, 0.870),
    (0.601, 4.304, 2.494),
    (4.384, 13.320, 2.214),
)


def evaluate_gold_dispersion_comparison(design: Any, device: str) -> dict[str, Any]:
    """Compare single-pole Drude gold vs. 6-pole Rakic Lorentz-Drude gold in 3D Vector-Dyadic BEM."""
    from execution.materials_database_dispersive import HBAR_C_EV_UM

    rakic_oscillators = [
        {
            "strength": float(f_j) * ((RAKIC_GOLD_WP_EV / float(e0_ev)) ** 2),
            "omega_0": float(e0_ev) / HBAR_C_EV_UM,
            "gamma": float(gam_ev) / HBAR_C_EV_UM,
        }
        for f_j, e0_ev, gam_ev in RAKIC_GOLD_INTERBAND_POLES
    ]
    rakic_wp = math.sqrt(RAKIC_GOLD_F0) * RAKIC_GOLD_WP_EV / HBAR_C_EV_UM
    rakic_gamma = RAKIC_GOLD_GAMMA0_EV / HBAR_C_EV_UM

    results: dict[str, Any] = {}
    for theta_deg, state_slug in ((3.0, "theta3"), (48.0, "theta48")):
        for disp_slug, disp_override in (
            ("drude1", {"material": "Gold", "lorentz_oscillators": []}),
            (
                "rakic6",
                {
                    "material": "Gold",
                    "plasma_frequency": rakic_wp,
                    "gamma": rakic_gamma,
                    "lorentz_oscillators": rakic_oscillators,
                },
            ),
        ):
            mesh = build_study_clutch_mesh(
                design,
                theta_deg=theta_deg,
                n_r=BEM_TIER_STANDARD.n_r,
                n_phi_tooth=BEM_TIER_STANDARD.n_phi_tooth,
                n_phi_bridge=BEM_TIER_STANDARD.n_phi_bridge,
                n_z=BEM_TIER_STANDARD.n_z,
            )
            mesh.parameters.update(disp_override)
            mesh.parameters["temperature_K"] = 0.0
            t0 = time.monotonic()
            res = run_bem_casimir_solver(
                mesh.parameters,
                mesh=mesh,
                n_xi=BEM_TIER_STANDARD.n_xi,
                formulation="vector_dyadic",
                device=device,
                record_metrics=False,
            )
            fz = vertical_force(res)
            elapsed = time.monotonic() - t0
            results[f"{disp_slug}_{state_slug}_fz_pN"] = float(fz)
            results[f"{disp_slug}_{state_slug}_elapsed_s"] = float(elapsed)
            print(
                f"[BEM-Dispersion] {disp_slug:6s} | theta={theta_deg:4.1f} deg | Fz={fz:+.4f} pN ({elapsed:.1f}s)",
                flush=True,
            )
        f_d1 = results[f"drude1_{state_slug}_fz_pN"]
        f_r6 = results[f"rakic6_{state_slug}_fz_pN"]
        results[f"rel_diff_rakic6_vs_drude1_{state_slug}_pct"] = (
            100.0 * abs(f_r6 - f_d1) / max(abs(f_d1), 1e-12)
        )
        results[f"signed_diff_rakic6_vs_drude1_{state_slug}_pct"] = (
            100.0 * (f_r6 - f_d1) / max(abs(f_d1), 1e-12)
        )
    return results


def evaluate_bem_point(
    design: Any,
    *,
    tier_label: str,
    n_r: int,
    n_phi_tooth: int,
    n_phi_bridge: int,
    n_z: int,
    n_xi: int,
    device: str,
    material: str = "PEC",
    rect_self_correction: bool = False,
) -> dict[str, Any]:
    mesh = build_study_clutch_mesh(
        design,
        theta_deg=3.0,
        n_r=n_r,
        n_phi_tooth=n_phi_tooth,
        n_phi_bridge=n_phi_bridge,
        n_z=n_z,
    )
    mesh.parameters["material"] = material
    mesh.parameters["temperature_K"] = 0.0

    rotor_panels = mesh.sector_arrays("rotor")
    stator_panels = mesh.sector_arrays("stator")
    rotor_aspects = estimate_panel_aspect_ratios(rotor_panels.quad_points)
    stator_aspects = estimate_panel_aspect_ratios(stator_panels.quad_points)
    all_aspects = np.concatenate([rotor_aspects, stator_aspects])
    all_ratios = rectangle_self_factor_ratio(all_aspects)

    original_disk_self_term = cbs._disk_self_term
    original_vector_dyadic_blocks = cbs._vector_dyadic_blocks
    started = time.monotonic()
    error_detail: str | None = None
    force_z: float | None = None
    energy_val: float | None = None
    try:
        if rect_self_correction:
            def _rect_vector_dyadic_blocks(
                target: Any,
                source: Any,
                source_sector: int,
                kappa: float,
                *,
                same_body: bool,
            ) -> Any:
                target_ratios = rectangle_self_factor_ratio(
                    estimate_panel_aspect_ratios(target.quad_points)
                )
                cbs._disk_self_term = (
                    lambda areas, k: original_disk_self_term(areas, k) * target_ratios
                )
                try:
                    return original_vector_dyadic_blocks(
                        target,
                        source,
                        source_sector,
                        kappa,
                        same_body=same_body,
                    )
                finally:
                    cbs._disk_self_term = original_disk_self_term

            cbs._vector_dyadic_blocks = _rect_vector_dyadic_blocks
        res = run_bem_casimir_solver(
            mesh.parameters,
            mesh=mesh,
            n_xi=n_xi,
            formulation="vector_dyadic",
            device=device,
            record_metrics=False,
        )
        force_z = vertical_force(res)
        energy_val = float(res["energy_hbar_c_per_um"])
    except FloatingPointError as exc:
        error_detail = str(exc)
    finally:
        cbs._disk_self_term = original_disk_self_term
        cbs._vector_dyadic_blocks = original_vector_dyadic_blocks

    elapsed = time.monotonic() - started
    row = {
        "tier_label": tier_label,
        "n_r": n_r,
        "n_phi_tooth": n_phi_tooth,
        "n_phi_bridge": n_phi_bridge,
        "n_z": n_z,
        "n_xi": n_xi,
        "rect_self_correction": rect_self_correction,
        "total_panels_4sectors": int(4 * (rotor_panels.count + stator_panels.count)),
        "mean_panel_aspect_ratio": float(np.mean(all_aspects)),
        "max_panel_aspect_ratio": float(np.max(all_aspects)),
        "mean_rect_self_factor_ratio": float(np.mean(all_ratios)),
        "status": "failed_positive_realness" if error_detail else "ok",
        "error_detail": error_detail,
        "force_z_pN": force_z,
        "energy_hbar_c_per_um": energy_val,
        "elapsed_seconds": elapsed,
    }
    print(
        f"[{tier_label}] panels={row['total_panels_4sectors']} n_xi={n_xi} "
        f"force_z_pN={force_z} status={row['status']} ({elapsed:.2f}s)",
        flush=True,
    )
    return row


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="0 runs full diagnostic suite; 1..10 runs fast micro-probe.",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
    )
    parser.add_argument(
        "--reuse-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse already-evaluated BEM sweep rows from existing output JSON when available.",
    )
    args = parser.parse_args(argv)
    if args.max_steps < 0 or args.max_steps > 10:
        parser.error("--max-steps must be 0 (full suite) or in 1..10 (micro-probe).")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.monotonic()
    device = args.device
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    load_backend()
    designs = prepare_designs()
    cantor_design = designs["Cantor_N2_HybridRZ"]

    config_dir = ROOT / "sweep_configs_meep_convergence_controls"
    meep_configs = generate_bigred200_meep_configs(config_dir)
    quant_n2_config_dir = ROOT / "sweep_configs_quant_fdtd_n2"
    quant_fdtd_n2_configs = generate_quant_fdtd_n2_configs(quant_n2_config_dir, designs)

    out_path = ROOT / "results" / "bem_fdtd_convergence_resolution.json"
    prev_report: dict[str, Any] = {}
    if args.reuse_existing and out_path.exists():
        try:
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            if (
                isinstance(loaded, dict)
                and loaded.get("model") == "BEM_FDTD_Convergence_Resolution"
                and loaded.get("dataset") == "cantor_n2_hybridrz_convergence_controls"
                and loaded.get("execution_status") == "complete"
            ):
                prev_report = loaded
        except (OSError, ValueError, TypeError):
            prev_report = {}

    is_micro = 0 < args.max_steps <= 10
    n_xi_sweep_rows: list[dict[str, Any]] = []
    spatial_sweep_rows: list[dict[str, Any]] = []
    gold_dispersion_cmp: dict[str, Any] = {}
    expected_nxi_orders = (16, 24, 32, 40, 64)
    directional_configs = (
        ("Standard_2_2_2_2_diskSelf", 2, 2, 2, 2, False),
        ("RadialOnly_3_2_2_2_diskSelf", 3, 2, 2, 2, False),
        ("AzimuthalToothOnly_2_3_2_2_diskSelf", 2, 3, 2, 2, False),
        ("VerticalZOnly_2_2_2_3_diskSelf", 2, 2, 2, 3, False),
        ("High_3_3_2_3_diskSelf", 3, 3, 2, 3, False),
        ("Standard_2_2_2_2_rectSelf", 2, 2, 2, 2, True),
    )

    if is_micro:
        row = evaluate_bem_point(
            cantor_design,
            tier_label="Standard_micro",
            n_r=BEM_TIER_STANDARD.n_r,
            n_phi_tooth=BEM_TIER_STANDARD.n_phi_tooth,
            n_phi_bridge=BEM_TIER_STANDARD.n_phi_bridge,
            n_z=BEM_TIER_STANDARD.n_z,
            n_xi=min(4, max(2, args.max_steps)),
            device=device,
            rect_self_correction=False,
        )
        n_xi_sweep_rows.append(row)
    else:
        cached_nxi = prev_report.get("n_xi_decoupled_sweep", [])
        nxi_valid = (
            args.reuse_existing
            and isinstance(cached_nxi, list)
            and len(cached_nxi) == len(expected_nxi_orders)
            and all(
                isinstance(r, dict)
                and r.get("tier_label") == f"Standard_nxi{n_xi}"
                and r.get("n_xi") == n_xi
                and r.get("n_r") == BEM_TIER_STANDARD.n_r
                and r.get("n_phi_tooth") == BEM_TIER_STANDARD.n_phi_tooth
                and r.get("n_phi_bridge") == BEM_TIER_STANDARD.n_phi_bridge
                and r.get("n_z") == BEM_TIER_STANDARD.n_z
                and r.get("rect_self_correction") is False
                and r.get("status") == "ok"
                and isinstance(r.get("force_z_pN"), (int, float))
                for r, n_xi in zip(cached_nxi, expected_nxi_orders)
            )
        )
        if nxi_valid:
            n_xi_sweep_rows = list(cached_nxi)
            print(f"[CACHED] Reused {len(n_xi_sweep_rows)} n_xi_decoupled_sweep rows", flush=True)
        else:
            # 1. Decouple n_xi quadrature at fixed Standard spatial mesh (1,504 panels)
            for n_xi in expected_nxi_orders:
                n_xi_sweep_rows.append(
                    evaluate_bem_point(
                        cantor_design,
                        tier_label=f"Standard_nxi{n_xi}",
                        n_r=BEM_TIER_STANDARD.n_r,
                        n_phi_tooth=BEM_TIER_STANDARD.n_phi_tooth,
                        n_phi_bridge=BEM_TIER_STANDARD.n_phi_bridge,
                        n_z=BEM_TIER_STANDARD.n_z,
                        n_xi=n_xi,
                        device=device,
                        rect_self_correction=False,
                    )
                )
        cached_spatial = prev_report.get("spatial_and_self_term_sweep", [])
        spatial_valid = (
            args.reuse_existing
            and isinstance(cached_spatial, list)
            and len(cached_spatial) == len(directional_configs)
            and all(
                isinstance(r, dict)
                and r.get("tier_label") == label
                and r.get("n_r") == nr
                and r.get("n_phi_tooth") == npt
                and r.get("n_phi_bridge") == npb
                and r.get("n_z") == nz
                and r.get("n_xi") == 32
                and r.get("rect_self_correction") is rect_corr
                and r.get("status") == "ok"
                and isinstance(r.get("force_z_pN"), (int, float))
                for r, (label, nr, npt, npb, nz, rect_corr) in zip(cached_spatial, directional_configs)
            )
        )
        if spatial_valid:
            spatial_sweep_rows = list(cached_spatial)
            print(f"[CACHED] Reused {len(spatial_sweep_rows)} spatial_and_self_term_sweep rows", flush=True)
        else:
            # 2. Directional spatial mesh refinement ablation at fixed n_xi=32 + rectangular self-term test
            for label, nr, npt, npb, nz, rect_corr in directional_configs:
                spatial_sweep_rows.append(
                    evaluate_bem_point(
                        cantor_design,
                        tier_label=label,
                        n_r=nr,
                        n_phi_tooth=npt,
                        n_phi_bridge=npb,
                        n_z=nz,
                        n_xi=32,
                        device=device,
                        rect_self_correction=rect_corr,
                    )
                )
        expected_disp_keys = (
            "drude1_theta3_fz_pN",
            "rakic6_theta3_fz_pN",
            "rel_diff_rakic6_vs_drude1_theta3_pct",
            "signed_diff_rakic6_vs_drude1_theta3_pct",
            "drude1_theta48_fz_pN",
            "rakic6_theta48_fz_pN",
            "rel_diff_rakic6_vs_drude1_theta48_pct",
            "signed_diff_rakic6_vs_drude1_theta48_pct",
        )
        cached_disp = prev_report.get("gold_dispersion_comparison", {})
        if (
            args.reuse_existing
            and isinstance(cached_disp, dict)
            and all(
                isinstance(cached_disp.get(k), (int, float)) and math.isfinite(float(cached_disp[k]))
                for k in expected_disp_keys
            )
        ):
            gold_dispersion_cmp = dict(cached_disp)
            print("[CACHED] Reused gold_dispersion_comparison", flush=True)
        else:
            gold_dispersion_cmp = evaluate_gold_dispersion_comparison(cantor_design, device)

    now_iso = datetime.now(timezone.utc).isoformat()
    vert_ref_panels = next(
        (float(r["total_panels_4sectors"]) for r in spatial_sweep_rows if r.get("tier_label") == "Standard_2_2_2_2_diskSelf"),
        1152.0,
    )
    report: dict[str, Any] = {
        "model": "BEM_FDTD_Convergence_Resolution",
        "dataset": "cantor_n2_hybridrz_convergence_controls",
        "status": "completed",
        "execution_status": "micro_probe_complete" if is_micro else "complete",
        "executed_at": now_iso,
        "device": device,
        "n_xi_decoupled_sweep": n_xi_sweep_rows,
        "spatial_and_self_term_sweep": spatial_sweep_rows,
        "gold_dispersion_comparison": gold_dispersion_cmp,
        "bigred200_meep_control_configs": meep_configs,
        "bigred200_quant_fdtd_n2_configs": quant_fdtd_n2_configs,
        "part1_bem_nxi_convergence": {
            "n_xi_values": [float(r["n_xi"]) for r in n_xi_sweep_rows if isinstance(r.get("n_xi"), (int, float))],
        },
        "part2_directional_mesh_refinement": {
            "vertical_refined_panels": vert_ref_panels,
        },
        "part3_fixedbox_meep_controls": {
            "dct_orders_nmax": sorted({float(c["nmax"]) for c in meep_configs}),
            "dx_nm_at_R40": 25.0,
            "dx_nm_at_R60": 16.7,
            "dx_nm_at_R80": 12.5,
            "dx_nm_at_R270": round(1000.0 / 270.0, 2),
            "dx_nm_at_R400": 2.5,
            "mst_box_margin_nm": 1000.0 * FIXED_STRESS_BOX_MARGIN_UM,
            "resolutions": sorted({float(c["resolution"]) for c in meep_configs}),
        },
        "elapsed_seconds": time.monotonic() - started,
    }
    if not is_micro and isinstance(prev_report.get("edge_rounded_r5nm_convergence"), list):
        report["edge_rounded_r5nm_convergence"] = list(prev_report["edge_rounded_r5nm_convergence"])
    if len(n_xi_sweep_rows) >= 4:
        f_nxi24 = next((r["force_z_pN"] for r in n_xi_sweep_rows if r["n_xi"] == 24), None)
        f_nxi40 = next((r["force_z_pN"] for r in n_xi_sweep_rows if r["n_xi"] == 40), None)
        f_nxi64 = next((r["force_z_pN"] for r in n_xi_sweep_rows if r["n_xi"] == 64), None)
        if all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in (f_nxi24, f_nxi40, f_nxi64)):
            f24 = float(f_nxi24)  # type: ignore[arg-type]
            f40 = float(f_nxi40)  # type: ignore[arg-type]
            f64 = float(f_nxi64)  # type: ignore[arg-type]
            report["summary"] = {
                "standard_mesh_force_nxi24_pN": f24,
                "standard_mesh_force_nxi40_pN": f40,
                "standard_mesh_force_nxi64_pN": f64,
                "n_xi_relative_drift_24_to_64_pct": 100.0 * abs(f64 - f24) / max(abs(f64), 1e-12),
            }

    atomic_write_json(out_path, report)

    from utils.metrics_logger import export_macros, log_step, log_metric, set_solver_provenance
    import shutil

    set_solver_provenance(
        "bem",
        {
            "benchmark": "bem_fdtd_convergence_resolution",
            "device": device,
            "max_steps": args.max_steps,
            "executed_at": now_iso,
        },
    )
    log_step(
        "bem_fdtd_convergence_resolution",
        {
            "status": report["execution_status"],
            "n_xi_points": len(n_xi_sweep_rows),
            "spatial_points": len(spatial_sweep_rows),
            "meep_configs_generated": len(meep_configs),
        },
        solver_name="bem",
    )
    if "summary" in report:
        for k, v in report["summary"].items():
            log_metric(f"conv_res_{k}", float(v), step_id="bem_fdtd_convergence_resolution", solver_name="bem")
    if gold_dispersion_cmp:
        for k, v in gold_dispersion_cmp.items():
            if isinstance(v, (int, float)) and math.isfinite(float(v)):
                log_metric(f"bem_disp_cantor_n2_{k}", float(v), step_id="bem_fdtd_convergence_resolution", solver_name="bem")
        export_macros(str(ROOT / "results" / "provenance_metrics.json"), str(ROOT / "results" / "macros_results.tex"))
        for paper_tex_dir in (
            ROOT / "Papers" / "Fractal_Casimir_Nature_EM",
            ROOT / "Papers" / "FCE_Nature_ver01",
        ):
            if paper_tex_dir.is_dir():
                shutil.copy2(ROOT / "results" / "macros_results.tex", paper_tex_dir / "macros_results.tex")

    print(
        f"Completed {report['execution_status']} in {report['elapsed_seconds']:.2f}s -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
