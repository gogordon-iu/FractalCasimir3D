#!/usr/bin/env python3
"""Aggregate and audit quantitative N=2 3D FDTD BigRed 200 results vs. 3D BEM.

Reads completed 4-pass 3D FDTD MEEP outputs (`results/quant_fdtd_n2/task_*_meep.json`
or `results_quant_fdtd_n2/task_*_meep.json`) for the N=2 corner-rounded
(`r_edge = 5 nm`, single-pole Drude gold, fixed 8 nm stress-box standoff, Sector-0
cropped) `Cantor_N2_HybridRZ` vs. `Ctrl_UniformPeriodic` validation suite, compares
them against the 3D Vector-Dyadic BEM `r_edge = 5 nm` benchmarks, performs
resolution/DCT/PML convergence analysis, and exports auditable provenance metrics
and LaTeX macros via `utils.metrics_logger`.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.metrics_logger import export_macros, log_metric, log_step

BEM_R5NM_REF: dict[str, dict[str, float]] = {
    "Cantor_N2_HybridRZ": {
        "Standard": 1.2671722931523986,
        "High": 1.4847000592684327,
        "Ultra-High": 1.4040651153746458,
    },
    "Ctrl_UniformPeriodic": {
        "Standard": 0.9553978271609033,
        "High": 1.089401389533491,
        "Ultra-High": 1.0063075077522994,
    },
}


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _finite_float_or_default(value: Any, default: float) -> float:
    parsed = _finite_float(value)
    return parsed if parsed is not None else default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _richardson_two_point(r1: float, f1: float, r2: float, f2: float, order: float = 2.0) -> float:
    if r1 <= 0.0 or r2 <= 0.0 or math.isclose(r1, r2):
        raise ValueError(f"Invalid resolutions for Richardson extrapolation: r1={r1}, r2={r2}")
    h1 = 1.0 / r1
    h2 = 1.0 / r2
    ratio = (h1 / h2) ** order
    return float((ratio * f2 - f1) / (ratio - 1.0))


def aggregate_quant_fdtd_n2(
    *,
    configs_dir: Path,
    results_dirs: list[Path],
    bem_ref_path: Path,
    output_path: Path,
    max_steps: int = 0,
) -> dict[str, Any]:
    bem_ref: dict[str, dict[str, float]] = {
        design: dict(tiers) for design, tiers in BEM_R5NM_REF.items()
    }
    bem_payload = _load_json(bem_ref_path)
    if bem_payload and isinstance(bem_payload.get("bem_edge_rounding_convergence"), dict):
        edge_conv = bem_payload["bem_edge_rounding_convergence"]
        for design in ("Cantor_N2_HybridRZ", "Ctrl_UniformPeriodic"):
            design_block = edge_conv.get(design)
            if not isinstance(design_block, dict):
                continue
            rows = design_block.get("r_edge_5nm", [])
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and "tier" in row and "f_z_pN" in row:
                        tier_name = str(row["tier"])
                        fz_val = _finite_float(row["f_z_pN"])
                        if tier_name in ("Standard", "High", "Ultra-High") and fz_val is not None and fz_val > 0.0:
                            bem_ref[design][tier_name] = fz_val

    bem_ratios = {
        tier: float(bem_ref["Cantor_N2_HybridRZ"][tier] / bem_ref["Ctrl_UniformPeriodic"][tier])
        for tier in ("Standard", "High", "Ultra-High")
    }

    config_files = sorted(configs_dir.glob("config_*.json"))
    if max_steps > 0:
        config_files = config_files[:max_steps]

    tasks_summary: list[dict[str, Any]] = []
    completed_by_task: dict[int, dict[str, Any]] = {}

    for cfg_path in config_files:
        cfg = _load_json(cfg_path)
        if cfg is None:
            continue
        task_id = _safe_int(cfg.get("task_id"), 0)
        if task_id <= 0:
            stem_digits = "".join(ch for ch in cfg_path.stem if ch.isdigit())
            task_id = _safe_int(stem_digits, 0)
        design_id = str(cfg.get("design_id", "unknown"))
        resolution = _safe_int(cfg.get("resolution"), 0)
        n_max = _safe_int(cfg.get("casimir_Order_N", cfg.get("n_max", 1)), 1)
        r_edge_nm = _finite_float_or_default(cfg.get("r_edge_nm"), 5.0)
        dx_nm = (1000.0 / float(resolution)) if resolution > 0 else None

        task_result: dict[str, Any] | None = None
        result_source: str | None = None
        for rdir in results_dirs:
            candidate = rdir / f"task_{task_id}_meep.json"
            loaded = _load_json(candidate)
            if loaded is not None:
                task_result = loaded
                result_source = str(candidate)
                break

        status = "missing"
        f_net_pN: float | None = None
        f_2pass_pN: float | None = None
        f_stator_only_pN: float | None = None
        elapsed_s: float | None = None
        completed_moments = 0
        moments_per_config = _safe_int(cfg.get("moments_per_pass"), 0)

        if task_result is not None:
            status = str(task_result.get("status", "unknown"))
            completed_moments = _safe_int(task_result.get("completed_moments"), 0)
            moments_per_config = _safe_int(
                task_result.get("num_tasks_per_config"), moments_per_config
            )
            elapsed_s = _finite_float(task_result.get("elapsed_seconds"))
            scale_si = _finite_float_or_default(task_result.get("MEEP_FORCE_TO_SI_N"), 3.16152677e-14)
            scale_pN = scale_si * 1e12
            f_net_pN = _finite_float(task_result.get("f_net_pN"))
            raw_2pass = _finite_float(task_result.get("F_2pass"))
            if raw_2pass is not None:
                f_2pass_pN = _finite_float(raw_2pass * scale_pN)
            raw_stator = _finite_float(task_result.get("F_stator_only"))
            if raw_stator is not None:
                f_stator_only_pN = _finite_float(raw_stator * scale_pN)
            if status == "complete":
                if f_net_pN is None:
                    status = "invalid_nonfinite_force"
                elif moments_per_config <= 0 or completed_moments != 4 * moments_per_config:
                    status = "incomplete_moments"

        bem_ultra = bem_ref.get(design_id, {}).get("Ultra-High")
        bem_std = bem_ref.get(design_id, {}).get("Standard")
        rel_diff_vs_bem_ultra_pct = (
            100.0 * (f_net_pN - bem_ultra) / bem_ultra
            if (f_net_pN is not None and bem_ultra)
            else None
        )
        rel_diff_vs_bem_std_pct = (
            100.0 * (f_net_pN - bem_std) / bem_std
            if (f_net_pN is not None and bem_std)
            else None
        )

        entry = {
            "task_id": task_id,
            "config_id": str(cfg.get("config_id", cfg_path.stem)),
            "design_id": design_id,
            "study_role": str(cfg.get("study_role", "")),
            "resolution": resolution,
            "dx_nm": round(dx_nm, 4) if dx_nm is not None else None,
            "cells_across_20p4nm_radial_gap": round(20.4167 / dx_nm, 3) if (dx_nm is not None and dx_nm > 0.0) else None,
            "cells_across_15nm_vertical_gap": round(15.0 / dx_nm, 3) if (dx_nm is not None and dx_nm > 0.0) else None,
            "n_max": n_max,
            "r_edge_nm": r_edge_nm,
            "material": str(cfg.get("material", "gold_drude1")),
            "stress_box_margin_nm": round(_finite_float_or_default(cfg.get("stress_box_margin_um"), 0.008) * 1000.0, 2),
            "pml_thickness_um": _finite_float_or_default(cfg.get("pml_thickness"), 0.18),
            "cell_buffer_um": _finite_float_or_default(cfg.get("cell_buffer_um"), 0.10),
            "T_run": _finite_float_or_default(cfg.get("T_run"), 3.0),
            "status": status,
            "result_file": result_source,
            "completed_moments": completed_moments,
            "total_4pass_moments": 4 * moments_per_config,
            "elapsed_seconds": elapsed_s,
            "f_net_pN": f_net_pN,
            "f_2pass_pN": f_2pass_pN,
            "f_stator_only_pN": f_stator_only_pN,
            "bem_r5nm_std_pN": bem_std,
            "bem_r5nm_ultra_pN": bem_ultra,
            "rel_diff_vs_bem_std_pct": rel_diff_vs_bem_std_pct,
            "rel_diff_vs_bem_ultra_pct": rel_diff_vs_bem_ultra_pct,
        }
        tasks_summary.append(entry)
        if status == "complete" and f_net_pN is not None and moments_per_config > 0 and completed_moments == 4 * moments_per_config:
            completed_by_task[task_id] = entry

    pair_comparisons: dict[str, dict[str, Any]] = {}
    for label, t_cantor, t_unif in (
        ("R120_nmax1", 1, 2),
        ("R160_nmax1", 3, 4),
        ("R200_nmax2", 5, 6),
    ):
        c_row = completed_by_task.get(t_cantor)
        u_row = completed_by_task.get(t_unif)
        if c_row and u_row and c_row["f_net_pN"] is not None and u_row["f_net_pN"] is not None:
            fc = float(c_row["f_net_pN"])
            fu = float(u_row["f_net_pN"])
            if not math.isclose(fu, 0.0, abs_tol=1e-15):
                fdtd_ratio = fc / fu
                if math.isfinite(fdtd_ratio):
                    pair_comparisons[label] = {
                        "cantor_f_z_pN": fc,
                        "uniform_f_z_pN": fu,
                        "fdtd_cantor_to_uniform_ratio": fdtd_ratio,
                        "bem_ultra_cantor_to_uniform_ratio": bem_ratios["Ultra-High"],
                        "ratio_rel_diff_vs_bem_ultra_pct": 100.0
                        * (fdtd_ratio - bem_ratios["Ultra-High"])
                        / bem_ratios["Ultra-High"],
                    }

    convergence_checks: dict[str, Any] = {}
    if 1 in completed_by_task and 3 in completed_by_task:
        f120 = float(completed_by_task[1]["f_net_pN"])
        f160 = float(completed_by_task[3]["f_net_pN"])
        convergence_checks["cantor_R120_to_R160_nmax1"] = {
            "f_R120_pN": f120,
            "f_R160_pN": f160,
            "rel_drift_pct": 100.0 * abs(f160 - f120) / max(abs(f160), 1e-12),
            "richardson_extrap_pN": _richardson_two_point(120.0, f120, 160.0, f160),
        }
    if 2 in completed_by_task and 4 in completed_by_task:
        u120 = float(completed_by_task[2]["f_net_pN"])
        u160 = float(completed_by_task[4]["f_net_pN"])
        convergence_checks["uniform_R120_to_R160_nmax1"] = {
            "f_R120_pN": u120,
            "f_R160_pN": u160,
            "rel_drift_pct": 100.0 * abs(u160 - u120) / max(abs(u160), 1e-12),
            "richardson_extrap_pN": _richardson_two_point(120.0, u120, 160.0, u160),
        }
    if 3 in completed_by_task and 7 in completed_by_task:
        fn1 = float(completed_by_task[3]["f_net_pN"])
        fn3 = float(completed_by_task[7]["f_net_pN"])
        convergence_checks["cantor_R160_nmax1_to_nmax3"] = {
            "f_nmax1_pN": fn1,
            "f_nmax3_pN": fn3,
            "rel_drift_pct": 100.0 * (fn3 - fn1) / max(abs(fn1), 1e-12),
        }
    if 3 in completed_by_task and 8 in completed_by_task:
        f_std = float(completed_by_task[3]["f_net_pN"])
        f_pml = float(completed_by_task[8]["f_net_pN"])
        convergence_checks["cantor_R160_pml_pad_trun_check"] = {
            "f_base_pN": f_std,
            "f_extended_pml_trun_pN": f_pml,
            "rel_drift_pct": 100.0 * (f_pml - f_std) / max(abs(f_std), 1e-12),
        }

    summary_payload = {
        "study": "quant_fdtd_n2_bigred200_validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_configured_tasks": len(tasks_summary),
        "completed_tasks_count": len(completed_by_task),
        "completed_task_ids": sorted(completed_by_task.keys()),
        "bem_r5nm_reference_pN": bem_ref,
        "bem_r5nm_cantor_to_uniform_ratios": bem_ratios,
        "tasks": tasks_summary,
        "pair_comparisons": pair_comparisons,
        "convergence_checks": convergence_checks,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2, allow_nan=False)

    log_step(
        "quant_fdtd_n2_aggregation",
        {
            "configured_tasks": len(tasks_summary),
            "completed_tasks": len(completed_by_task),
            "output_path": str(output_path),
        },
    )
    log_metric(
        "quant_fdtd_n2_configured_tasks",
        len(tasks_summary),
        step_id="quant_fdtd_n2_aggregation",
    )
    log_metric(
        "quant_fdtd_n2_completed_tasks",
        len(completed_by_task),
        step_id="quant_fdtd_n2_aggregation",
    )

    for task_id, row in sorted(completed_by_task.items()):
        log_metric(
            f"quant_fdtd_n2_task{task_id}_fz_pn",
            float(row["f_net_pN"]),
            step_id="quant_fdtd_n2_aggregation",
        )
        if row["rel_diff_vs_bem_ultra_pct"] is not None:
            log_metric(
                f"quant_fdtd_n2_task{task_id}_rel_diff_bem_ultra_pct",
                float(row["rel_diff_vs_bem_ultra_pct"]),
                step_id="quant_fdtd_n2_aggregation",
            )

    for label, comp in pair_comparisons.items():
        log_metric(
            f"quant_fdtd_n2_{label.lower()}_cantor_to_uniform_ratio",
            float(comp["fdtd_cantor_to_uniform_ratio"]),
            step_id="quant_fdtd_n2_aggregation",
        )

    export_macros()
    paper_macros = PROJECT_ROOT / "Papers" / "FCE_Nature_ver01" / "macros_results.tex"
    results_macros = PROJECT_ROOT / "results" / "macros_results.tex"
    if results_macros.is_file() and paper_macros.parent.is_dir():
        shutil.copyfile(results_macros, paper_macros)

    return summary_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=PROJECT_ROOT / "sweep_configs_quant_fdtd_n2",
        help="Directory containing config_001.json .. config_008.json.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "quant_fdtd_n2",
        help="Primary directory containing task_<ID>_meep.json files.",
    )
    parser.add_argument(
        "--legacy-results-dir",
        type=Path,
        default=PROJECT_ROOT / "results_quant_fdtd_n2",
        help="Fallback directory containing task_<ID>_meep.json files.",
    )
    parser.add_argument(
        "--bem-ref-file",
        type=Path,
        default=PROJECT_ROOT / "results" / "bem_fdtd_convergence_resolution.json",
        help="Path to BEM/FDTD convergence reference JSON.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=PROJECT_ROOT / "results" / "quant_fdtd_n2_summary.json",
        help="Output summary JSON path inside results/.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Optional cap on number of config files processed (for micro-probing).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_steps < 0:
        raise ValueError("--max-steps must be >= 0")
    summary = aggregate_quant_fdtd_n2(
        configs_dir=args.configs_dir,
        results_dirs=[args.results_dir, args.legacy_results_dir],
        bem_ref_path=args.bem_ref_file,
        output_path=args.output_file,
        max_steps=args.max_steps,
    )
    print(
        f"[quant_fdtd_n2] Aggregated {summary['completed_tasks_count']}/"
        f"{summary['total_configured_tasks']} completed tasks -> {args.output_file}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
