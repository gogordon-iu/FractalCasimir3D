#!/usr/bin/env python3
"""Scan ten disengaged Cantor-ring clutch configurations for F_net > 0.

Geometry lengths are in micrometres. Positive force denotes the solver's
positive-z convention. Positive results are numerical candidates, not a
substitute for mesh, frequency-quadrature, and formulation convergence checks.

Examples:
    python execution/run_repulsion_10configs_scan.py
    python execution/run_repulsion_10configs_scan.py --configs 1 2 --max-steps 2
    python execution/run_repulsion_10configs_scan.py --formulation vector_dyadic
    python execution/run_repulsion_10configs_scan.py --max-steps 2 --all-configs
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import numbers
import os
import sys
import tempfile
import time
import traceback
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    import torch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

Formulation = Literal["vector_dyadic", "scalar_yukawa"]

FORCE_KEYS = (
    "F_net",
    "f_net_N",
    "f_net_fN",
    "f_net_pN",
    "F_bottom",
    "F_lateral_top_edge",
)
FAILURE_STATUSES = {
    "failed", "failure", "error", "invalid", "diverged", "nonconverged",
    "not_converged", "not converged", "cancelled", "canceled",
}


@dataclass(frozen=True, slots=True)
class ConfigSpec:
    config_num: int
    slug: str
    label: str
    N: int
    R_min: float
    R_max: float
    w1_ratio: float
    min_tooth_w: float
    z_tip: float
    h_teeth: float
    t_membrane: float
    t_landing_pad: float
    tooth_arc_deg: float
    aperture_arc_deg: float
    rationale: str

    @property
    def theta_deg(self) -> float:
        return (self.aperture_arc_deg / 2.0) - 15.0

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{self.slug}: {name} must be finite")
        if self.config_num < 1 or self.N < 1:
            raise ValueError(f"{self.slug}: configuration number and N must be positive")
        if not 0.0 < self.R_min < self.R_max:
            raise ValueError(f"{self.slug}: invalid radial bounds")
        if not 0.0 < self.w1_ratio < 1.0:
            raise ValueError(f"{self.slug}: w1_ratio must be between zero and one")
        if min(self.min_tooth_w, self.h_teeth, self.t_membrane) <= 0.0:
            raise ValueError(f"{self.slug}: tooth width, height, and membrane must be positive")
        if self.t_landing_pad < 0.0:
            raise ValueError(f"{self.slug}: landing-pad thickness cannot be negative")
        if not 0.0 < self.tooth_arc_deg < self.aperture_arc_deg < 90.0:
            raise ValueError(f"{self.slug}: invalid disengaged angular geometry")
        center = (15.0 + self.theta_deg) % 90.0
        if not math.isclose(center, self.aperture_arc_deg / 2.0, abs_tol=1e-12):
            raise ValueError(f"{self.slug}: tooth is not centered in its aperture")


CONFIGURATIONS: tuple[ConfigSpec, ...] = (
    ConfigSpec(
        1, "cfg01_full_window_pass_through",
        "C1: Full-Window Pass-Through (z=-100nm)",
        2, 0.30, 1.35, 0.23, 0.020, -0.100, 0.250, 0.025, 0.150, 15.0, 30.0,
        "Baseline 250nm tooth spanning z=[-100,+150]nm with a 25nm membrane and 150nm landing pad.",
    ),
    ConfigSpec(
        2, "cfg02_deep_below_membrane_peak",
        "C2: Deep Below-Membrane Peak (z=-250nm)",
        2, 0.30, 1.35, 0.23, 0.020, -0.250, 0.250, 0.025, 0.150, 15.0, 30.0,
        "250nm tooth spanning z=[-250,0]nm to probe below-membrane upward force.",
    ),
    ConfigSpec(
        3, "cfg03_ultra_thin_membrane_levin",
        "C3: Ultra-Thin Membrane Levin (t=20nm, z=-45nm)",
        2, 0.30, 1.35, 0.20, 0.020, -0.045, 0.060, 0.020, 0.020, 15.0, 30.0,
        "20nm thin stator membrane with a 60nm compact tooth spanning z=[-45,+15]nm.",
    ),
    ConfigSpec(
        4, "cfg04_high_radial_fill_tight_slot",
        "C4: High Radial Fill Tight Slot (w1=0.65)",
        2, 0.30, 1.35, 0.65, 0.020, -0.100, 0.250, 0.025, 0.150, 15.0, 30.0,
        "High radial tooth-to-slot width ratio (0.65) narrowing radial slot clearance by 2.2x.",
    ),
    ConfigSpec(
        5, "cfg05_wide_angular_aperture",
        "C5: Wide Angular Aperture (50deg slot, 10deg tooth)",
        2, 0.30, 1.35, 0.23, 0.020, -0.100, 0.250, 0.025, 0.150, 10.0, 50.0,
        "50-deg open angular slot with 10-deg tooth to decouple azimuthal landing-pad pull-down.",
    ),
    ConfigSpec(
        6, "cfg06_tall_slot_submerged_tooth",
        "C6: Tall Slot / Short Submerged Tooth (t=100nm, h=80nm)",
        2, 0.30, 1.35, 0.35, 0.020, -0.180, 0.080, 0.100, 0.100, 15.0, 30.0,
        "80nm short tooth spanning z=[-180,-100]nm beneath a 100nm membrane.",
    ),
    ConfigSpec(
        7, "cfg07_zero_landing_pad_backing",
        "C7: Zero Landing-Pad Backing (t_pad=0, z=-100nm)",
        2, 0.30, 1.35, 0.30, 0.020, -0.100, 0.250, 0.025, 0.000, 15.0, 35.0,
        "Eliminates extra landing-pad backing thickness (t_landing_pad=0) with a 25nm membrane.",
    ),
    ConfigSpec(
        8, "cfg08_compact_submicron_ring",
        "C8: Compact Sub-Micron Ring (R=0.2..0.9um)",
        2, 0.20, 0.90, 0.45, 0.020, -0.100, 0.250, 0.025, 0.150, 15.0, 36.0,
        "Sub-micron radial footprint R in [0.20, 0.90]um with tight sub-40nm radial slot clearances.",
    ),
    ConfigSpec(
        9, "cfg09_single_track_N1_fundamental",
        "C9: Single-Track Fundamental Ring (N=1, w1=0.55)",
        1, 0.30, 1.35, 0.55, 0.020, -0.100, 0.250, 0.025, 0.150, 12.0, 40.0,
        "Single fundamental middle-third slot (N=1) without inter-track cross-talk.",
    ),
    ConfigSpec(
        10, "cfg10_high_density_N3_fractal",
        "C10: High-Density 3-Level Fractal Ring (N=3, 7 tracks)",
        3, 0.30, 1.65, 0.40, 0.015, -0.100, 0.250, 0.025, 0.150, 12.0, 36.0,
        "3-level Cantor ring with 7 concentric slots/teeth multiplying radial perimeter edges by 2.33x.",
    ),
)


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("expected an integer greater than zero")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--formulation",
        choices=("vector_dyadic", "scalar_yukawa", "both"),
        default="both",
    )
    parser.add_argument(
        "--max-steps", type=int, default=0,
        help="solver iteration cap per configuration/formulation (default: 0)",
    )
    parser.add_argument("--n-r", type=positive_int, default=2)
    parser.add_argument("--n-phi-tooth", type=positive_int, default=3)
    parser.add_argument("--n-phi-bridge", type=positive_int, default=3)
    parser.add_argument("--n-z", type=positive_int, default=2)
    parser.add_argument("--n-xi", type=positive_int, default=24)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--configs", type=int, nargs="+", choices=range(1, 11),
        default=list(range(1, 11)), metavar="1..10",
        help="configuration subset; default: all ten",
    )
    parser.add_argument(
        "--all-configs", action="store_true",
        help="disable the one-configuration, one-formulation micro-probe for max-steps 1..5",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=REPOSITORY_ROOT / "results" / "repulsion_10configs_scan",
    )
    parser.add_argument(
        "--skip-plot", action="store_true",
        help="do not generate the force comparison plot",
    )
    return parser.parse_args()


def finite_scalar(value: object, name: str) -> float:
    import torch

    if isinstance(value, torch.Tensor):
        if value.numel() != 1 or value.is_complex() or value.dtype == torch.bool:
            raise TypeError(f"{name} must be a real scalar")
        value = value.detach().cpu().item()
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a real numeric scalar, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} is not finite")
    return result


def json_ready(value: Any) -> Any:
    """Normalize metadata without silently emitting non-standard NaN/Infinity."""
    import torch

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return finite_scalar(value, "JSON numeric value")
    if isinstance(value, torch.Tensor):
        return json_ready(value.detach().cpu().tolist())
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    # Solver metadata may contain descriptive objects such as torch.dtype.
    return str(value)


def record_metadata(status: str = "completed") -> dict[str, str]:
    """Metadata required by freshness_filter.py."""
    return {
        "model": "casimir_bem_10configs",
        "dataset": "repulsion_10configs_scan",
        "status": status,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="",
            dir=path.parent, prefix=f".{path.name}.", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, payload: Any) -> None:
    if isinstance(payload, Mapping):
        payload = {**record_metadata(), **payload}
    atomic_write(
        path,
        json.dumps(json_ready(payload), indent=2, allow_nan=False, ensure_ascii=False) + "\n",
    )


def build_config(spec: ConfigSpec) -> dict[str, Any]:
    from execution.clutch_geometry_redesign import get_scoped_clutch_elements

    spec.validate()
    elements = get_scoped_clutch_elements(
        N=spec.N,
        R_min=spec.R_min,
        R_max=spec.R_max,
        w1_ratio=spec.w1_ratio,
        min_tooth_w=spec.min_tooth_w,
    )
    if not isinstance(elements, list) or not elements:
        raise ValueError(f"{spec.slug}: geometry returned no elements")
    if any(not isinstance(element, dict) for element in elements):
        raise TypeError(f"{spec.slug}: geometry elements must be dictionaries")
    return {
        "task_id": spec.config_num,
        "task_name": spec.slug,
        "description": spec.rationale,
        "material": "Gold",
        "N_fractal": spec.N,
        "R_min": spec.R_min,
        "R_max": spec.R_max,
        "w1_ratio": spec.w1_ratio,
        "min_tooth_w": spec.min_tooth_w,
        "z_tip": spec.z_tip,
        "h_teeth": spec.h_teeth,
        "t_membrane": spec.t_membrane,
        "t_landing_pad": spec.t_landing_pad,
        "theta_deg": spec.theta_deg,
        "tooth_arc_deg": spec.tooth_arc_deg,
        "aperture_arc_deg": spec.aperture_arc_deg,
        "elements": elements,
    }


def validate_result(result: object) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise TypeError("run_bem_casimir_solver must return a dictionary")
    required = (
        *FORCE_KEYS[:4], "elapsed_seconds", "solver", "solver_parameters",
        "status", "diagnostics",
    )
    missing = [key for key in required if key not in result]
    if missing:
        raise ValueError(f"solver result is missing keys: {', '.join(missing)}")

    diagnostics = result["diagnostics"]
    if not isinstance(diagnostics, Mapping):
        raise TypeError("solver diagnostics must be a mapping")
    diagnostic_keys = ("F_bottom", "F_lateral_top_edge", "n_panels_total")
    missing = [key for key in diagnostic_keys if key not in diagnostics]
    if missing:
        raise ValueError(f"solver diagnostics is missing keys: {', '.join(missing)}")

    normalized = {key: finite_scalar(result[key], key) for key in FORCE_KEYS[:4]}
    normalized["F_bottom"] = finite_scalar(diagnostics["F_bottom"], "F_bottom")
    normalized["F_lateral_top_edge"] = finite_scalar(
        diagnostics["F_lateral_top_edge"], "F_lateral_top_edge",
    )
    panel_count = finite_scalar(diagnostics["n_panels_total"], "n_panels_total")
    if panel_count < 0.0 or not panel_count.is_integer():
        raise ValueError("n_panels_total must be a nonnegative integer")
    normalized["n_panels_total"] = int(panel_count)

    normalized["elapsed_seconds"] = finite_scalar(result["elapsed_seconds"], "elapsed_seconds")
    if normalized["elapsed_seconds"] < 0.0:
        raise ValueError("solver elapsed_seconds cannot be negative")
    if not isinstance(result["solver"], str) or not result["solver"].strip():
        raise TypeError("solver name must be a nonempty string")
    if not isinstance(result["solver_parameters"], dict):
        raise TypeError("solver_parameters must be a dictionary")
    if not isinstance(result["status"], str) or not result["status"].strip():
        raise TypeError("solver status must be a nonempty string")
    normalized.update(
        solver=result["solver"],
        solver_parameters=json_ready(result["solver_parameters"]),
        status=result["status"],
    )
    status = result["status"].strip().lower()
    if status in FAILURE_STATUSES or status.startswith(("error:", "failed:")):
        raise RuntimeError(f"solver reported unsuccessful status: {result['status']}")
    # All three unit-labelled net forces must agree; F_net's unit is not assumed.
    net_n = normalized["f_net_N"]
    for key, scale in (("f_net_fN", 1e15), ("f_net_pN", 1e12)):
        expected = net_n * scale
        if not math.isfinite(expected):
            raise ValueError(f"{key}: unit conversion overflow")
        if not math.isclose(normalized[key], expected, rel_tol=1e-7, abs_tol=1e-12):
            raise ValueError(f"inconsistent net-force units: {key} versus f_net_N")
    if (normalized["F_net"] > 0.0) != (net_n > 0.0):
        raise ValueError("F_net and f_net_N disagree on repulsive classification")
    if (normalized["F_net"] < 0.0) != (net_n < 0.0):
        raise ValueError("F_net and f_net_N disagree on force sign")
    return normalized


def solver_parameters(args: argparse.Namespace, formulation: Formulation) -> dict[str, Any]:
    return {
        "n_r": args.n_r,
        "n_phi_tooth": args.n_phi_tooth,
        "n_phi_bridge": args.n_phi_bridge,
        "n_z": args.n_z,
        "n_xi": args.n_xi,
        "max_steps": args.max_steps,
        "device": args.device,
        "formulation": formulation,
    }


def evaluate(
    spec: ConfigSpec,
    formulation: Formulation,
    args: argparse.Namespace,
    output_dir: Path,
) -> dict[str, Any]:
    from execution.casimir_bem_solver import run_bem_casimir_solver
    from utils.metrics_logger import log_metric, log_step, set_solver_provenance

    step_id = f"repulsion_scan_{spec.slug}_{formulation}"
    parameters = solver_parameters(args, formulation)
    row: dict[str, Any] = {
        **record_metadata("failed"),
        "config_num": spec.config_num,
        "slug": spec.slug,
        "label": spec.label,
        "formulation": formulation,
        "theta_deg": spec.theta_deg,
        "step_id": step_id,
        "success": False,
        "repulsive": None,
        "error": None,
        "provenance_error": None,
        "solver": "run_bem_casimir_solver",
        "solver_parameters": parameters,
    }
    started = time.perf_counter()
    provenance_errors: list[str] = []
    try:
        set_solver_provenance(
            solver_name="run_bem_casimir_solver", solver_parameters=parameters,
        )
        log_step(
            step_id,
            {
                "configuration": asdict(spec),
                "theta_deg": spec.theta_deg,
                "state": "disengaged_slot",
                "phase": "started",
            },
            solver_name="run_bem_casimir_solver",
            solver_parameters=parameters,
        )
    except Exception as exc:
        provenance_errors.append(f"start logging: {type(exc).__name__}: {exc}")

    try:
        config_dict = build_config(spec)
        config_path = str(output_dir / "configs" / f"{spec.slug}_{formulation}.json")
        write_json(Path(config_path), config_dict)
        row["config_file"] = config_path
        task_id = spec.config_num
        solver_max_steps = args.max_steps
        result = run_bem_casimir_solver(
            config_dict,
            n_r=args.n_r,
            n_phi_tooth=args.n_phi_tooth,
            n_phi_bridge=args.n_phi_bridge,
            n_z=args.n_z,
            n_xi=args.n_xi,
            max_steps=solver_max_steps,
            device=args.device,
            config_file=config_path,
            task_id=task_id,
            record_metrics=True,
            formulation=formulation,
        )
        normalized = validate_result(result)
        # Preserve the solver's status separately from the freshness status.
        normalized["solver_status"] = normalized.pop("status")
        row.update(normalized)
        row["success"] = True
        row["repulsive"] = row["F_net"] > 0.0
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc()
    row["wall_seconds"] = time.perf_counter() - started
    row.update(record_metadata("completed" if row["success"] else "failed"))

    try:
        set_solver_provenance(
            solver_name=row["solver"], solver_parameters=row["solver_parameters"],
        )
        log_step(
            step_id,
            {
                "phase": "completed" if row["success"] else "failed",
                "success": row["success"],
                "error": row["error"],
                "wall_seconds": row["wall_seconds"],
            },
            solver_name=row["solver"],
            solver_parameters=row["solver_parameters"],
        )
        keys = (
            "success", "repulsive", *FORCE_KEYS, "n_panels_total",
            "elapsed_seconds", "status", "solver_status",
        )
        for key in keys:
            if key in row:
                log_metric(
                    f"{step_id}_{key}",
                    row[key],
                    step_id=step_id,
                    solver_name=row["solver"],
                    solver_parameters=row["solver_parameters"],
                )
    except Exception as exc:
        provenance_errors.append(f"result logging: {type(exc).__name__}: {exc}")
    if provenance_errors:
        row["provenance_error"] = "; ".join(provenance_errors)
        print(f"WARNING: {row['provenance_error']}", file=sys.stderr)
    write_json(output_dir / "runs" / f"{spec.slug}_{formulation}.json", row)
    return row


def save_summary(
    output_dir: Path,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    expected_runs: int,
) -> None:
    selected = set(args.configs)
    summary: list[dict[str, Any]] = []
    for spec in CONFIGURATIONS:
        if spec.config_num not in selected:
            continue
        entries = [row for row in rows if row["config_num"] == spec.config_num]
        successful = [row for row in entries if row["success"]]
        expected_per_config = 2 if args.formulation == "both" else 1
        complete = len(successful) == expected_per_config
        summary.append({
            "config_num": spec.config_num,
            "slug": spec.slug,
            "complete": complete,
            "repulsive_formulations": [
                row["formulation"] for row in successful if row["repulsive"]
            ],
            "repulsive_in_all_requested_formulations": (
                all(row["repulsive"] for row in successful) if complete else None
            ),
            "sign_disagreement": (
                len({row["repulsive"] for row in successful}) > 1
                if len(successful) > 1 else None
            ),
        })
    scan_successful = (
        expected_runs > 0
        and len(rows) == expected_runs
        and all(row["success"] for row in rows)
    )
    payload = {
        **record_metadata("completed" if scan_successful else "incomplete"),
        "description": "Disengaged slot scan; repulsive iff validated F_net > 0.",
        "caution": (
            "Finite positive forces are numerical candidates. This scan alone "
            "does not establish convergence or agreement with physical experiment."
        ),
        "arguments": vars(args),
        "expected_runs": expected_runs,
        "completed_runs": len(rows),
        "successful_runs": sum(bool(row["success"]) for row in rows),
        "configurations": summary,
        "runs": rows,
    }
    write_json(output_dir / "scan_results.json", payload)
    columns = (
        "model", "dataset", "executed_at",
        "config_num", "slug", "label", "formulation", "theta_deg", "success",
        "repulsive", *FORCE_KEYS, "n_panels_total", "elapsed_seconds",
        "wall_seconds", "solver", "status", "solver_status", "config_file", "error",
        "provenance_error",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(output_dir / "scan_results.csv", buffer.getvalue())

    ranked: list[dict[str, Any]] = []
    for spec in CONFIGURATIONS:
        entry: dict[str, Any] = {
            "config_num": spec.config_num,
            "slug": spec.slug,
            "label": spec.label,
            "configuration": asdict(spec),
        }
        forces: list[float] = []
        for formulation in ("vector_dyadic", "scalar_yukawa"):
            matches = [
                row for row in rows
                if row["config_num"] == spec.config_num
                and row["formulation"] == formulation
            ]
            run = matches[-1] if matches else None
            valid = run is not None and run["success"]
            entry[formulation] = {
                "status": (
                    run["status"] if valid else "failed" if run is not None else "not run"
                ),
                "f_net_fN": run["f_net_fN"] if valid else None,
                "f_net_pN": run["f_net_pN"] if valid else None,
                "error": run["error"] if run is not None else None,
            }
            if valid:
                forces.append(run["f_net_pN"])
        entry["ranking_force_pN"] = max(forces) if forces else None
        ranked.append(entry)
    ranked.sort(key=lambda entry: (
        entry["ranking_force_pN"] is None,
        -entry["ranking_force_pN"] if entry["ranking_force_pN"] is not None else 0.0,
        entry["config_num"],
    ))
    for rank, entry in enumerate(ranked, 1):
        entry["rank"] = rank if entry["ranking_force_pN"] is not None else None

    report_path = REPOSITORY_ROOT / "results" / "repulsion_10configs_scan_report"
    write_json(report_path.with_suffix(".json"), {
        **payload,
        "ranking_basis": "Descending maximum validated net force (pN) across formulations.",
        "ranked_configurations": ranked,
    })
    lines = [
        "# Disengaged Cantor-ring clutch scan",
        "",
        payload["caution"],
        "",
        f"Completed runs: {len(rows)} / {expected_runs}; "
        f"successful runs: {payload['successful_runs']}.",
        "",
        "Ranked by descending maximum validated net force across formulations. "
        "Unrun or failed configurations are unranked and listed last.",
        "",
        "| Rank | Configuration | vector_dyadic (fN) | vector_dyadic (pN) | "
        "scalar_yukawa (fN) | scalar_yukawa (pN) |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for entry in ranked:
        cells = [
            str(entry["rank"]) if entry["rank"] is not None else "—",
            entry["label"].replace("|", r"\|"),
        ]
        for formulation in ("vector_dyadic", "scalar_yukawa"):
            force = entry[formulation]
            for key in ("f_net_fN", "f_net_pN"):
                cells.append(
                    f"{force[key]:.9g}" if force[key] is not None else force["status"]
                )
        lines.append("| " + " | ".join(cells) + " |")
    atomic_write(report_path.with_suffix(".md"), "\n".join(lines) + "\n")


def make_plot(
    output_dir: Path,
    rows: list[dict[str, Any]],
    metrics_path: Path,
) -> bool:
    from utils.metrics_logger import save_plot_provenance

    successful = [row for row in rows if row["success"]]
    if not successful:
        print("No valid forces to plot.", file=sys.stderr)
        return True
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        print(f"Plot unavailable: {exc}; use --skip-plot if intentional.", file=sys.stderr)
        return False

    figure = None
    try:
        figure, axis = plt.subplots(figsize=(12, max(4.5, 0.35 * len(successful))))
        forces = [row["f_net_pN"] for row in successful]
        positions = list(range(len(successful)))
        axis.barh(
            positions, forces,
            color=["#248a3d" if row["repulsive"] else "#b74242" for row in successful],
        )
        axis.set_yticks(
            positions,
            [f"C{row['config_num']} / {row['formulation']}" for row in successful],
        )
        axis.invert_yaxis()
        axis.axvline(0.0, color="black", linewidth=0.8)
        axis.set_xlabel("Net force (pN); positive = +z")
        axis.set_title("Disengaged Cantor-ring clutch: numerical repulsion candidates")
        axis.grid(axis="x", alpha=0.25)
        figure.tight_layout()
        columns_list = [f"{row['step_id']}_f_net_pN" for row in successful]
        parameters = {
            "runs": [
                {
                    "step_id": row["step_id"],
                    "solver": row["solver"],
                    "solver_parameters": row["solver_parameters"],
                }
                for row in successful
            ],
        }
        paths = (
            output_dir / "repulsion_scan.png",
            REPOSITORY_ROOT / "figures" / "fig_repulsion_10configs_scan.png",
            REPOSITORY_ROOT / "figures" / "fig_repulsion_10configs_scan.pdf",
        )
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(path, dpi=180)
            save_plot_provenance(
                str(path),
                str(metrics_path),
                columns_list,
                solver_name="run_bem_casimir_solver",
                solver_parameters=parameters,
            )
        return True
    except Exception as exc:
        print(f"Plot/provenance failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False
    finally:
        if figure is not None:
            plt.close(figure)


def main() -> int:
    args = parse_args()
    # Resolve user-relative output paths before establishing repository-relative
    # paths for the repository logger and material-data loading.
    output_dir = args.output_dir.expanduser().resolve()
    args.output_dir = output_dir
    os.chdir(REPOSITORY_ROOT)

    import torch
    from utils.metrics_logger import export_macros

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.device == "auto":
        args.device = device
    elif args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda requested, but CUDA is unavailable")

    output_dir.mkdir(parents=True, exist_ok=True)
    args.configs = sorted(set(args.configs))
    selected = [spec for spec in CONFIGURATIONS if spec.config_num in args.configs]
    if not selected:
        raise ValueError("no configurations selected")
    formulations: tuple[Formulation, ...]
    if args.formulation == "both":
        formulations = ("vector_dyadic", "scalar_yukawa")
    elif args.formulation == "vector_dyadic":
        formulations = ("vector_dyadic",)
    else:
        formulations = ("scalar_yukawa",)
    if 0 < args.max_steps <= 5 and not args.all_configs:
        selected = [CONFIGURATIONS[0]]
        formulations = (formulations[0],)
        # Summaries describe the effective micro-probe selection.
        args.configs = [selected[0].config_num]
        args.formulation = formulations[0]
    expected_runs = len(selected) * len(formulations)
    rows: list[dict[str, Any]] = []
    interrupted = False
    print(
        f"Scanning {len(selected)} configurations / {expected_runs} solver runs "
        f"on {args.device}; max_steps={args.max_steps}",
        flush=True,
    )
    save_summary(output_dir, args, rows, expected_runs)
    try:
        for spec in selected:
            for formulation in formulations:
                print(f"[{len(rows) + 1}/{expected_runs}] {spec.label} / {formulation}", flush=True)
                row = evaluate(spec, formulation, args, output_dir)
                rows.append(row)
                save_summary(output_dir, args, rows, expected_runs)
                if row["success"]:
                    classification = "REPULSIVE" if row["repulsive"] else "NON-REPULSIVE"
                    print(
                        f"  {classification}: F_net={row['F_net']:.9g}, "
                        f"force={row['f_net_pN']:.9g} pN, status={row['status']}",
                        flush=True,
                    )
                else:
                    print(f"  FAILED: {row['error']}", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted; completed runs have been preserved.", file=sys.stderr)
    finally:
        save_summary(output_dir, args, rows, expected_runs)

    metrics_path = REPOSITORY_ROOT / "results" / "provenance_metrics.json"
    ancillary_ok = True
    try:
        export_macros()
    except Exception as exc:
        ancillary_ok = False
        print(f"Default macro export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    try:
        export_macros(
            metrics_path=str(metrics_path),
            output_path=str(output_dir / "macros_results.tex"),
        )
    except Exception as exc:
        ancillary_ok = False
        print(f"Macro export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    if not args.skip_plot:
        ancillary_ok = make_plot(output_dir, rows, metrics_path) and ancillary_ok

    candidates = [row for row in rows if row["success"] and row["repulsive"]]
    print(f"\nPositive-force candidates: {len(candidates)} / {len(rows)} attempted runs.")
    for row in sorted(candidates, key=lambda item: item["f_net_pN"], reverse=True):
        print(f"  {row['slug']} / {row['formulation']}: {row['f_net_pN']:.9g} pN")
    print(f"Results: {output_dir}")
    print("Positive forces require independent convergence checks before physical interpretation.")
    if interrupted:
        return 130
    failed = (
        len(rows) != expected_runs
        or any(not row["success"] or row["provenance_error"] for row in rows)
        or not ancillary_ok
    )
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except KeyboardInterrupt:
        exit_code = 130
    except Exception:
        traceback.print_exc()
        exit_code = 1
    raise SystemExit(exit_code)
