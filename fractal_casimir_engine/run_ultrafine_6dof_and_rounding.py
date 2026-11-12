#!/usr/bin/env python3
"""Suite 4 (eng_uf4): Ultra-Fine 6-DOF Lateral/Tilt Stability Hessian & EBL Corner-Rounding Audit.

Two-part referee robustness campaign on BigRed 200 A100 GPUs:
  1. Full 4-sector non-Bloch 3D BEM 6-DOF rigid-body Hessian across the cycle,
     certifying C_4 cancellation of net lateral forces (F_x = F_y = 0) and tilt
     torques (tau_x = tau_y = 0), quantifying peak destabilizing lateral/tilt
     Casimir stiffnesses, and computing nanobearing pull-in safety factors.
  2. Multi-facet 2D EBL planform vertical-corner fillet sweep (r_edge_nm in {0, 5, 10, 15} nm)
     on the Ultra-Fine mesh, proving that (+F_z, +tau_theta) and (-F_z, +tau_theta)
     arise from volumetric chiral Cantor slot/pad geometry rather than sharp planform corners.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fractal_casimir_engine import ENGINE_DESIGN_NAMES
from fractal_casimir_engine.bem_cycle_solver import (
    Full4Sector6DofBemEvaluator,
    PreparedEngineBemModel,
    detect_compute_device,
)
from fractal_casimir_engine.run_engine_cycle_mapping import cycle_z_profile_um
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

ENGINE_DIR = PROJECT_ROOT / "fractal_casimir_engine"
UF_RESULTS_DIR = ENGINE_DIR / "results" / "ultrafine"
ENGINE_FIGURES_DIR = ENGINE_DIR / "figures"

CYCLE_SAMPLE_ANGLES_DEG: tuple[float, ...] = (12.0, 22.0, 34.0, 42.0, 52.0, 64.0, 78.0, 86.0)
ROUNDING_RADII_NM: tuple[float, ...] = (0.0, 5.0, 10.0, 15.0)
BENCHMARK_STATES: tuple[tuple[str, float, float], ...] = (
    ("Stroke_I_Repulsive", -0.092, 22.0),
    ("Stroke_III_Attractive", -0.084, 64.0),
)

# Reference NEMS radial/tilt hub bearing stiffnesses for pull-in safety margin
REF_BEARING_K_LAT_UN_M: float = 250000.0        # 0.25 N/m = 2.5e5 uN/m radial hub bearing
REF_BEARING_K_TILT_PN_UM_RAD: float = 25000.0   # 2.5e4 pN*um/rad rotational-plane tilt stiffness


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        d = json.load(handle)
    return d if isinstance(d, dict) else None


def check_walltime(started_mono: float, max_walltime_hours: float) -> None:
    if max_walltime_hours > 0.0 and (time.monotonic() - started_mono) >= max_walltime_hours * 3600.0:
        raise TimeoutError("Approaching Slurm walltime limit; checkpoint saved cleanly for auto-resubmit.")


def run_micro_probe(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    device = detect_compute_device(args.device)

    base = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=3,
        n_z=1,
        n_xi=4,
        quad_order=2,
        device=device,
        lazy_self_cache=True,
    )
    eval6 = Full4Sector6DofBemEvaluator(base)
    hess = eval6.evaluate_6dof_hessian(-0.092, 22.0, max_steps=args.max_steps)

    rounded_model = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        n_r=2,
        n_phi_tooth=3,
        n_phi_bridge=3,
        n_z=1,
        n_xi=4,
        quad_order=2,
        r_edge_nm=10.0,
        device=device,
        lazy_self_cache=True,
    )
    rounded_eval = rounded_model.evaluate_states_batch([(-0.092, 22.0)], max_steps=args.max_steps)[0]

    out_path = UF_RESULTS_DIR / "probe_uf4_6dof_and_rounding_report.json"
    payload = {
        "suite": "eng_uf4",
        "status": "micro_probe_completed",
        "time_truncated": True,
        "max_steps": int(args.max_steps),
        "device": device,
        "elapsed_seconds": time.perf_counter() - started,
        "sample_6dof_hessian": hess,
        "sample_rounded_10nm": rounded_eval,
    }
    atomic_write_json(out_path, payload)
    print(f"[UF4 MICRO-PROBE] Completed in {payload['elapsed_seconds']:.2f}s -> {out_path}", flush=True)
    return 0


def run_full_campaign(args: argparse.Namespace) -> int:
    started_mono = time.monotonic()
    started_wall = time.perf_counter()
    device = detect_compute_device(args.device)
    chk_dir = args.checkpoint_dir
    chk_dir.mkdir(parents=True, exist_ok=True)

    # 1. Full 4-sector 6-DOF Hessian sweep across cycle angles on Ultra-Fine mesh
    hessian_by_design: dict[str, list[dict[str, Any]]] = {d: [] for d in ENGINE_DESIGN_NAMES}
    for dname in ENGINE_DESIGN_NAMES:
        base_model: PreparedEngineBemModel | None = None
        eval6: Full4Sector6DofBemEvaluator | None = None
        for th_deg in CYCLE_SAMPLE_ANGLES_DEG:
            check_walltime(started_mono, args.max_walltime_hours)
            chk_file = chk_dir / f"hess6dof_{dname}_th{int(round(th_deg)):03d}.json"
            cached = load_json_if_exists(chk_file)
            if cached is not None and not args.no_cache:
                hessian_by_design[dname].append(cached)
                continue

            if eval6 is None:
                base_model = PreparedEngineBemModel(
                    dname,
                    n_r=3,
                    n_phi_tooth=6,
                    n_phi_bridge=6,
                    n_phi_arc_override=18,
                    n_z=3,
                    n_xi=24,
                    quad_order=3,
                    device=device,
                    lazy_self_cache=True,
                    max_memory_gib=args.max_memory_gib,
                )
                eval6 = Full4Sector6DofBemEvaluator(base_model)

            z_u, _ = cycle_z_profile_um(th_deg)
            rec = eval6.evaluate_6dof_hessian(z_u, th_deg)
            atomic_write_json(chk_file, rec)
            hessian_by_design[dname].append(rec)
            print(
                f"[UF4 6DOF] {dname} theta={th_deg:.0f} deg: "
                f"|Fx|={abs(rec['f_x_pN']):.2e} pN, K_lat_destab={rec['k_destab_lat_max_uN_m']:.2f} uN/m",
                flush=True,
            )

    # 2. EBL corner-rounding sweep r_edge_nm in {0, 5, 10, 15} nm across all 4 designs
    rounding_by_design: dict[str, list[dict[str, Any]]] = {d: [] for d in ENGINE_DESIGN_NAMES}
    for dname in ENGINE_DESIGN_NAMES:
        for r_nm in ROUNDING_RADII_NM:
            check_walltime(started_mono, args.max_walltime_hours)
            chk_file = chk_dir / f"rounding_{dname}_r{int(round(r_nm)):02d}nm.json"
            cached = load_json_if_exists(chk_file)
            if cached is not None and not args.no_cache:
                rounding_by_design[dname].append(cached)
                continue

            rmodel = PreparedEngineBemModel(
                dname,
                n_r=4,
                n_phi_tooth=6,
                n_phi_bridge=6,
                n_phi_arc_override=18,
                n_z=3,
                n_xi=24,
                quad_order=3,
                r_edge_nm=r_nm,
                device=device,
                lazy_self_cache=True,
                max_memory_gib=args.max_memory_gib,
            )
            pts = [(z_u, th_d) for _, z_u, th_d in BENCHMARK_STATES]
            evals = rmodel.evaluate_states_batch(pts)
            row = {
                "design_name": dname,
                "r_edge_nm": float(r_nm),
                "n_dofs_total": 4 * (rmodel.nr_dof + rmodel.ns_dof),
                "Stroke_I_Repulsive": evals[0],
                "Stroke_III_Attractive": evals[1],
            }
            atomic_write_json(chk_file, row)
            rounding_by_design[dname].append(row)
            print(f"[UF4 ROUNDING] {dname} r_edge={r_nm:.0f} nm done.", flush=True)

    max_c4_lat_force_residual_pN = max(
        max(abs(r["f_x_pN"]), abs(r["f_y_pN"]))
        for d in ENGINE_DESIGN_NAMES
        for r in hessian_by_design[d]
    )
    max_k_lat_destab_uN_m = max(
        r["k_destab_lat_max_uN_m"] for d in ENGINE_DESIGN_NAMES for r in hessian_by_design[d]
    )
    max_k_tilt_destab = max(
        r["k_destab_tilt_max_pN_um_rad"] for d in ENGINE_DESIGN_NAMES for r in hessian_by_design[d]
    )
    lat_safety_factor = REF_BEARING_K_LAT_UN_M / max(1.0e-6, max_k_lat_destab_uN_m)
    tilt_safety_factor = REF_BEARING_K_TILT_PN_UM_RAD / max(1.0e-6, max_k_tilt_destab)

    # Torque retention at r_edge = 15 nm vs 0 nm for Config D
    d_r0 = rounding_by_design["Config_D_DualStator_PushPull"][0]
    d_r15 = rounding_by_design["Config_D_DualStator_PushPull"][-1]
    retention_s1_pct = (
        100.0
        * d_r15["Stroke_I_Repulsive"]["tau_theta_pN_um"]
        / max(1.0e-9, d_r0["Stroke_I_Repulsive"]["tau_theta_pN_um"])
    )
    retention_s3_pct = (
        100.0
        * d_r15["Stroke_III_Attractive"]["tau_theta_pN_um"]
        / max(1.0e-9, d_r0["Stroke_III_Attractive"]["tau_theta_pN_um"])
    )

    report = {
        "suite": "eng_uf4",
        "status": "completed",
        "time_truncated": False,
        "device": device,
        "elapsed_seconds": time.perf_counter() - started_wall,
        "summary": {
            "max_c4_lateral_force_residual_pN": float(max_c4_lat_force_residual_pN),
            "max_k_lat_destab_uN_m": float(max_k_lat_destab_uN_m),
            "max_k_tilt_destab_pN_um_rad": float(max_k_tilt_destab),
            "lateral_bearing_safety_factor": float(lat_safety_factor),
            "tilt_bearing_safety_factor": float(tilt_safety_factor),
            "config_d_15nm_tau_retention_stroke1_pct": float(retention_s1_pct),
            "config_d_15nm_tau_retention_stroke3_pct": float(retention_s3_pct),
        },
        "hessian_6dof": hessian_by_design,
        "rounding_model": "2d_ebl_planform_vertical_corner_fillet",
        "corner_rounding": rounding_by_design,
    }
    report_path = UF_RESULTS_DIR / "uf4_6dof_and_rounding_report.json"
    atomic_write_json(report_path, report)

    metrics_path = UF_RESULTS_DIR / "uf4_provenance_metrics.json"
    macros_path = UF_RESULTS_DIR / "uf4_macros_results.tex"
    solver_params = {
        "n_r": 4,
        "n_phi_tooth": 6,
        "n_phi_arc": 18,
        "n_z": 3,
        "n_xi": 24,
        "quad_order": 3,
        "rounding_model": "2d_ebl_planform_vertical_corner_fillet",
    }
    set_solver_provenance(
        "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding",
        solver_params,
        metrics_path=str(metrics_path),
    )
    log_step("uf4_6dof_and_ebl_rounding", report["summary"], metrics_path=str(metrics_path))
    log_metric(
        "engine_uf4_max_k_lat_un_m",
        round(max_k_lat_destab_uN_m, 2),
        step_id="uf4_6dof_and_ebl_rounding",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf4_lat_safety_factor",
        round(lat_safety_factor, 1),
        step_id="uf4_6dof_and_ebl_rounding",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf4_tilt_safety_factor",
        round(tilt_safety_factor, 1),
        step_id="uf4_6dof_and_ebl_rounding",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf4_retain_stroke1_pct",
        round(retention_s1_pct, 1),
        step_id="uf4_6dof_and_ebl_rounding",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf4_retain_stroke3_pct",
        round(retention_s3_pct, 1),
        step_id="uf4_6dof_and_ebl_rounding",
        metrics_path=str(metrics_path),
    )
    export_macros(metrics_path=str(metrics_path), output_path=str(macros_path))

    # Plot Suite 4 figure
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=300)
    palette = {
        "Sym_Baseline_CantorN2": "#5f6368",
        "Config_B_Manhattan_Vernier": "#1a73e8",
        "Config_C_Helical_Turbine": "#0d9488",
        "Config_D_DualStator_PushPull": "#d93025",
    }
    for dname in ENGINE_DESIGN_NAMES:
        short = dname.split("_")[1]
        h_rows = hessian_by_design[dname]
        axes[0].plot(
            [r["theta_deg"] for r in h_rows],
            [r["k_destab_lat_max_uN_m"] for r in h_rows],
            "-o",
            lw=1.9,
            color=palette[dname],
            label=short,
        )
        r_rows = rounding_by_design[dname]
        axes[1].plot(
            [r["r_edge_nm"] for r in r_rows],
            [r["Stroke_I_Repulsive"]["tau_theta_pN_um"] for r in r_rows],
            "-o",
            lw=1.9,
            color=palette[dname],
            label=f"{short} (Stroke I)",
        )
        axes[1].plot(
            [r["r_edge_nm"] for r in r_rows],
            [r["Stroke_III_Attractive"]["tau_theta_pN_um"] for r in r_rows],
            "--s",
            lw=1.4,
            color=palette[dname],
            alpha=0.8,
        )

    axes[0].set_xlabel("Cycle Rotor Angle $\\theta$ (deg)")
    axes[0].set_ylabel("Destabilizing Lateral Stiffness $K_{\\mathrm{lat}}^{\\mathrm{Cas}}$ ($\\mu$N/m)")
    axes[0].set_title("A. Full 4-Sector 6-DOF Lateral Pull-In Stiffness")
    axes[0].legend(fontsize=8.5)
    axes[0].grid(True, alpha=0.25)

    axes[1].axhline(0.0, color="#222222", lw=0.8, ls=":")
    axes[1].set_xlabel("2D EBL Planform Corner Fillet Radius $r_{\\mathrm{edge}}$ (nm)")
    axes[1].set_ylabel("Azimuthal Torque $\\tau_\\theta$ (pN$\\cdot\\mu$m)")
    axes[1].set_title("B. 2D EBL Planform Corner-Rounding ($r_{\\mathrm{edge}} \\in [0, 15]$ nm)")
    axes[1].legend(fontsize=8.0, loc="best")
    axes[1].grid(True, alpha=0.25)

    fig.tight_layout()
    out_png = ENGINE_FIGURES_DIR / "fig_uf4_6dof_and_rounding.png"
    out_pdf = ENGINE_FIGURES_DIR / "fig_uf4_6dof_and_rounding.pdf"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)

    for fp in (out_png, out_pdf):
        save_plot_provenance(
            str(fp),
            str(report_path),
            columns_used=["hessian_6dof", "corner_rounding"],
            solver_name="BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding",
            solver_parameters=solver_params,
        )
    print(f"[UF4 COMPLETE] Saved {report_path} and figures.", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-steps", type=int, default=0)
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--max-walltime-hours", type=float, default=5.5)
    p.add_argument("--max-memory-gib", type=float, default=36.0)
    p.add_argument("--checkpoint-dir", type=Path, default=UF_RESULTS_DIR / "checkpoints_uf4")
    p.add_argument("--no-cache", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.max_steps > 0:
            return run_micro_probe(args)
        return run_full_campaign(args)
    except TimeoutError as exc:
        print(f"[UF4 WALLTIME] {exc}", file=sys.stderr, flush=True)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
