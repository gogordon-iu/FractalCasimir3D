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
    ]

    manifest_rows: list[dict[str, Any]] = []
    for spec in specs:
        task_id = int(spec["task_id"])
        cfg = {
            "task_id": task_id,
            "design_name": (
                "Rectilinear_Cantor_N2_HybridXZ"
                if spec["geometry_mode"] == "rectilinear_xz"
                else "Cantor_N2_HybridRZ"
            ),
            "control_label": spec["label"],
            "N_fractal": 2,
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
            "L_domain_um": 3.2,
            "pml_thickness_um": 0.25,
            "courant": 0.5,
            "T_run": t_run,
            "d_eff_um": d_eff,
            "resolution": int(spec["resolution"]),
            "nmax": int(spec["nmax"]),
            "material": str(spec["material"]),
            "stress_box_mode": "per_tooth_rotor_frame",
            "fixed_stress_box_margin_um": FIXED_STRESS_BOX_MARGIN_UM,
            "eps_averaging": False,
            "geometry_mode": str(spec["geometry_mode"]),
            "force_complex_fields": True,
            "geometry": {
                "elements": elements,
            },
        }
        cfg_path = config_dir / f"config_{task_id:03d}.json"
        atomic_write_json(cfg_path, cfg)
        manifest_rows.append(
            {
                "task_id": task_id,
                "config_file": str(cfg_path.relative_to(ROOT)).replace("\\", "/"),
                "label": spec["label"],
                "resolution": spec["resolution"],
                "nmax": spec["nmax"],
                "material": spec["material"],
                "geometry_mode": spec["geometry_mode"],
                "fixed_stress_box_margin_um": FIXED_STRESS_BOX_MARGIN_UM,
                "moments_per_pass": 18 * 6 * (int(spec["nmax"]) ** 2),
                "moments_total_4pass": 4 * 18 * 6 * (int(spec["nmax"]) ** 2),
            }
        )
    return manifest_rows


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

    is_micro = 0 < args.max_steps <= 10
    n_xi_sweep_rows: list[dict[str, Any]] = []
    spatial_sweep_rows: list[dict[str, Any]] = []

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
        # 1. Decouple n_xi quadrature at fixed Standard spatial mesh (1,504 panels)
        for n_xi in (16, 24, 32, 40, 64):
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
        # 2. Directional spatial mesh refinement ablation at fixed n_xi=32 + rectangular self-term test
        directional_configs = (
            ("Standard_2_2_2_2_diskSelf", 2, 2, 2, 2, False),
            ("RadialOnly_3_2_2_2_diskSelf", 3, 2, 2, 2, False),
            ("AzimuthalToothOnly_2_3_2_2_diskSelf", 2, 3, 2, 2, False),
            ("VerticalZOnly_2_2_2_3_diskSelf", 2, 2, 2, 3, False),
            ("High_3_3_2_3_diskSelf", 3, 3, 2, 3, False),
            ("Standard_2_2_2_2_rectSelf", 2, 2, 2, 2, True),
        )
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

    now_iso = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "model": "BEM_FDTD_Convergence_Resolution",
        "dataset": "cantor_n2_hybridrz_convergence_controls",
        "status": "completed",
        "execution_status": "micro_probe_complete" if is_micro else "complete",
        "executed_at": now_iso,
        "device": device,
        "n_xi_decoupled_sweep": n_xi_sweep_rows,
        "spatial_and_self_term_sweep": spatial_sweep_rows,
        "bigred200_meep_control_configs": meep_configs,
        "elapsed_seconds": time.monotonic() - started,
    }
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

    out_path = ROOT / "results" / "bem_fdtd_convergence_resolution.json"
    atomic_write_json(out_path, report)

    from utils.metrics_logger import log_step, log_metric, set_solver_provenance

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

    print(
        f"Completed {report['execution_status']} in {report['elapsed_seconds']:.2f}s -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
