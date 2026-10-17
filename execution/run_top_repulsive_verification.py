#!/usr/bin/env python3
"""Verify the top three repulsive Cantor-ring configurations.

Run from any directory:
    python execution/run_top_repulsive_verification.py
    python execution/run_top_repulsive_verification.py \
        --tasks C4_disengaged_base --max-steps 1

Distances in configuration dictionaries are in micrometers; angles are degrees.
--max-steps is forwarded unchanged to the repository solver. Its default, zero,
preserves the solver's own zero-step-limit semantics. With no explicit --tasks,
limits from 1 through 10 run only the first task for micro-profiling, without
cache reuse, plotting, or macro export.

Matching successful scan results may be reused for unlimited baseline runs.
Convergence comparisons are available for C4, C8, and C10.
Positive normal force is classified as repulsive, negative as attractive.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sys
import tempfile
import time
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from numbers import Integral, Real
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FORMULATION = "vector_dyadic"
MODEL = "casimir_bem_top_repulsive"
DATASET = "top_repulsive_verification"


@dataclass(frozen=True, slots=True)
class Winner:
    code: str
    name: str
    rank: int
    N: int
    R_min: float
    R_max: float
    w1_ratio: float
    min_tooth_w: float
    h_teeth: float
    t_membrane: float
    t_landing_pad: float
    tooth_arc_deg: float
    aperture_arc_deg: float

    def angle(self, state: str) -> float:
        if state == "disengaged":
            return self.aperture_arc_deg / 2.0 - 15.0
        if state == "slot_offset":
            return self.aperture_arc_deg / 2.0 - 15.0 + 4.0
        if state == "engaged":
            return (self.aperture_arc_deg + 90.0) / 2.0 - 15.0
        raise ValueError(f"Unknown clutch state: {state!r}")


WINNERS: dict[str, Winner] = {
    "C10": Winner(
        "C10", "cfg10_high_density_N3_fractal", 1,
        3, 0.30, 1.65, 0.40, 0.015, 0.250, 0.025, 0.150, 12.0, 36.0,
    ),
    "C4": Winner(
        "C4", "cfg04_high_radial_fill_tight_slot", 2,
        2, 0.30, 1.35, 0.65, 0.020, 0.250, 0.025, 0.150, 15.0, 30.0,
    ),
    "C8": Winner(
        "C8", "cfg08_compact_submicron_ring", 3,
        2, 0.20, 0.90, 0.45, 0.020, 0.250, 0.025, 0.150, 15.0, 36.0,
    ),
}


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    winner: str
    state: str
    z_tip: float
    n_r: int
    n_phi_tooth: int
    n_phi_bridge: int
    n_z: int
    n_xi: int

    def mesh_parameters(self) -> dict[str, int]:
        return {
            "n_r": self.n_r,
            "n_phi_tooth": self.n_phi_tooth,
            "n_phi_bridge": self.n_phi_bridge,
            "n_z": self.n_z,
            "n_xi": self.n_xi,
        }


TASKS: tuple[Task, ...] = (
    Task("C4_disengaged_base", "C4", "disengaged", -0.100, 2, 3, 3, 2, 24),
    Task("C4_disengaged_highres", "C4", "disengaged", -0.100, 2, 4, 4, 2, 32),
    Task("C4_slot_offset_4deg", "C4", "slot_offset", -0.100, 2, 3, 3, 2, 24),
    Task("C4_engaged_pad_z15nm", "C4", "engaged", 0.015, 2, 3, 3, 2, 24),
    Task("C8_disengaged_base", "C8", "disengaged", -0.100, 2, 3, 3, 2, 24),
    Task("C8_disengaged_highres", "C8", "disengaged", -0.100, 2, 4, 4, 2, 32),
    Task("C8_slot_offset_4deg", "C8", "slot_offset", -0.100, 2, 3, 3, 2, 24),
    Task("C8_engaged_pad_z15nm", "C8", "engaged", 0.015, 2, 3, 3, 2, 24),
    Task("C10_disengaged_base", "C10", "disengaged", -0.100, 2, 3, 3, 2, 24),
    Task("C10_disengaged_highxi", "C10", "disengaged", -0.100, 2, 3, 3, 2, 32),
    Task("C10_slot_offset_4deg", "C10", "slot_offset", -0.100, 2, 3, 3, 2, 24),
    Task("C10_engaged_pad_z15nm", "C10", "engaged", 0.015, 2, 3, 3, 2, 24),
)


def finite_float(value: Any, name: str) -> float:
    """Accept real scalar numbers, including scalar NumPy/Torch values."""
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if not isinstance(value, Real) and hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, RuntimeError) as exc:
            raise ValueError(f"{name} must be scalar") from exc
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, got {result!r}")
    return result


def json_safe(value: Any) -> Any:
    """Convert scientific values without silently emitting NaN or Infinity."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return finite_float(value, "serialized value")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON dictionary keys must be strings")
        return {key: json_safe(item) for key, item in value.items()}
    if hasattr(value, "detach"):
        return json_safe(value.detach().cpu().tolist())
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [json_safe(item) for item in value]
    raise TypeError(f"Unsupported serialized value: {type(value).__name__}")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value: Any) -> None:
    atomic_text(
        path,
        json.dumps(json_safe(value), indent=2, allow_nan=False) + "\n",
    )


def positive_panel_count(value: Any) -> int:
    numeric = finite_float(value, "diagnostics.n_panels_total")
    if numeric < 1.0 or not numeric.is_integer():
        raise ValueError("diagnostics.n_panels_total must be a positive integer")
    return int(numeric)


def classify(force: float) -> str:
    return "repulsive" if force > 0.0 else "attractive" if force < 0.0 else "zero"


def validate_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise TypeError("Solver result must be a mapping")
    required = {
        "F_net", "f_net_N", "f_net_fN", "f_net_pN", "elapsed_seconds",
        "solver", "solver_parameters", "status", "diagnostics",
    }
    missing = required.difference(result)
    if missing:
        raise ValueError(f"Solver result is missing fields: {sorted(missing)}")
    diagnostics = result["diagnostics"]
    if not isinstance(diagnostics, Mapping):
        raise TypeError("Solver diagnostics must be a mapping")
    for key in ("F_bottom", "F_lateral_top_edge", "n_panels_total"):
        if key not in diagnostics:
            raise ValueError(f"Solver diagnostics are missing {key!r}")

    clean = json_safe(dict(result))
    for key in ("f_net_N", "f_net_fN", "f_net_pN", "elapsed_seconds"):
        clean[key] = finite_float(result[key], key)
    if clean["elapsed_seconds"] < 0.0:
        raise ValueError("elapsed_seconds cannot be negative")
    clean["diagnostics"]["n_panels_total"] = positive_panel_count(
        diagnostics["n_panels_total"]
    )
    if not isinstance(clean["solver"], str) or not clean["solver"]:
        raise ValueError("Solver name must be a nonempty string")
    if not isinstance(clean["solver_parameters"], dict):
        raise TypeError("solver_parameters must be a mapping")
    if not isinstance(clean["status"], str) or not clean["status"]:
        raise ValueError("Solver status must be a nonempty string")

    status = clean["status"].strip().lower()
    if any(token in status for token in ("fail", "error", "diverg", "abort")):
        raise ValueError(f"Solver reported unsuccessful status: {clean['status']}")
    for key, scale in (("f_net_fN", 1e15), ("f_net_pN", 1e12)):
        expected = clean["f_net_N"] * scale
        if not math.isfinite(expected):
            raise ValueError(f"Force conversion overflows for {key}")
        if not math.isclose(clean[key], expected, rel_tol=1e-5, abs_tol=1e-12):
            raise ValueError(f"Inconsistent force units: f_net_N versus {key}")
    return clean


def config_for(task: Task) -> dict[str, Any]:
    winner = WINNERS[task.winner]
    config = asdict(winner)
    for key in ("code", "name", "rank"):
        del config[key]
    config["material"] = "Gold"
    config["theta_deg"] = winner.angle(task.state)
    config["z_tip"] = task.z_tip

    center = (15.0 + config["theta_deg"] % 90.0) % 90.0
    half_width = winner.tooth_arc_deg / 2.0
    lower, upper = center - half_width, center + half_width
    if task.state in {"disengaged", "slot_offset"}:
        if not (0.0 < lower < upper < winner.aperture_arc_deg):
            raise ValueError(f"{task.task_id}: tooth is not strictly inside slot")
    elif not (winner.aperture_arc_deg < lower < upper < 90.0):
        raise ValueError(f"{task.task_id}: tooth is not strictly above landing pad")
    return config


def load_cached_baseline(
    task: Task, config: dict[str, Any], parameters: dict[str, Any],
) -> tuple[dict[str, Any], Path] | None:
    """Reuse only a validated, successful scan with explicitly matching inputs."""
    if parameters["max_steps"] != 0 or task.task_id != f"{task.winner}_disengaged_base":
        return None
    path = (
        REPOSITORY_ROOT / "results" / "repulsion_10configs_scan" / "runs"
        / f"{WINNERS[task.winner].name}_{FORMULATION}.json"
    )
    try:
        with path.open(encoding="utf-8") as stream:
            cached = json.load(stream)
        if not isinstance(cached, Mapping):
            return None
        if "success" in cached and cached["success"] is not True:
            return None

        result = validate_result(cached.get("result", cached))
        if result["status"].strip().lower() not in {
            "success", "successful", "ok", "complete", "completed", "converged",
        }:
            return None
        cached_parameters = result["solver_parameters"]
        for key, expected in parameters.items():
            actual = cached_parameters.get(key)
            if isinstance(expected, Real) and not isinstance(expected, bool):
                if finite_float(actual, key) != expected:
                    return None
            elif actual != expected:
                return None

        cached_config = None
        for source in (cached, result, cached_parameters):
            for key in ("configuration", "config"):
                if isinstance(source.get(key), Mapping):
                    cached_config = source[key]
                    break
            if cached_config is not None:
                break

        if cached_config is None:
            # Some scan files store the configuration via solver provenance.
            config_file = None
            for source in (cached, result, cached_parameters):
                if isinstance(source.get("config_file"), str):
                    config_file = source["config_file"]
                    break
            if not config_file:
                return None
            source_path = Path(config_file).expanduser()
            if not source_path.is_absolute():
                source_path = REPOSITORY_ROOT / source_path
            with source_path.open(encoding="utf-8") as stream:
                cached_config = json.load(stream)

        if not isinstance(cached_config, Mapping):
            return None
        for key, expected in config.items():
            if key == "elements":
                continue
            actual = cached_config.get(key)
            if isinstance(expected, Real) and not isinstance(expected, bool):
                if not math.isclose(
                    finite_float(actual, key), float(expected),
                    rel_tol=1e-12, abs_tol=1e-15,
                ):
                    return None
            elif actual != expected:
                return None
        return result, path
    except (OSError, ValueError, TypeError, OverflowError):
        # Missing, malformed, or incompatible caches must not fail a fresh run.
        return None


def comparisons(
    records: list[dict[str, Any]], tolerance: float, limited: bool,
) -> dict[str, Any]:
    successful = {
        record["task_id"]: record for record in records if record["success"]
    }
    convergence: dict[str, Any] = {}
    characterization: dict[str, Any] = {}

    for code in ("C4", "C8", "C10"):
        base_id = f"{code}_disengaged_base"
        disengaged = successful.get(base_id)
        engaged = successful.get(f"{code}_engaged_pad_z15nm")
        offset = successful.get(f"{code}_slot_offset_4deg")
        entry: dict[str, Any] = {
            "disengaged_task": base_id,
            "disengaged_force_N": None,
            "off_center_force_N": None,
            "engaged_force_N": None,
            "bipolar_observed": None,
            "bipolar_contrast_ratio": None,
            "bipolar_contrast_ratio_definition": (
                "F_disengaged / abs(F_engaged), only for repulsive disengaged "
                "and attractive engaged forces; null if unavailable or nonfinite."
            ),
            "step_limited_run": limited,
        }
        for record, key in (
            (disengaged, "disengaged_force_N"),
            (offset, "off_center_force_N"),
            (engaged, "engaged_force_N"),
        ):
            if record is not None:
                entry[key] = record["result"]["f_net_N"]
        if disengaged is not None and engaged is not None:
            entry["bipolar_observed"] = (
                entry["disengaged_force_N"] > 0.0
                and entry["engaged_force_N"] < 0.0
            )
            if entry["bipolar_observed"]:
                ratio = (
                    entry["disengaged_force_N"] / abs(entry["engaged_force_N"])
                )
                if math.isfinite(ratio):
                    entry["bipolar_contrast_ratio"] = ratio
        if disengaged is not None and offset is not None:
            entry["offset_delta_force_N"] = (
                entry["off_center_force_N"] - entry["disengaged_force_N"]
            )
        characterization[code] = entry

        high_id = (
            f"{code}_disengaged_highxi"
            if code == "C10" else f"{code}_disengaged_highres"
        )
        high = successful.get(high_id)
        if disengaged is None or high is None:
            convergence[code] = {
                "available": False,
                "reason": "Both baseline and high-resolution results are required.",
            }
            continue
        base_force = disengaged["result"]["f_net_N"]
        high_force = high["result"]["f_net_N"]
        difference = abs(high_force - base_force)
        scale = max(abs(base_force), abs(high_force))
        relative = difference / scale if scale > 0.0 else 0.0
        convergence[code] = {
            "available": True,
            "baseline_force_N": base_force,
            "high_resolution_force_N": high_force,
            "absolute_difference_N": difference,
            "relative_difference_max_normalized": relative,
            "relative_tolerance": tolerance,
            "within_tolerance": relative <= tolerance,
            "sign_preserved": classify(base_force) == classify(high_force),
            "high_resolution_repulsive": high_force > 0.0,
            "step_limited_run": limited,
            "interpretation": (
                "Quadrature-only comparison at fixed mesh."
                if code == "C10"
                else "Joint azimuthal mesh/quadrature comparison; "
                "does not isolate their errors."
            ),
        }
    return {"convergence": convergence, "characterization": characterization}


def write_markdown_report(
    path: Path, records: list[dict[str, Any]], summary: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    def cell(value: Any) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, float):
            return f"{value:.8g}"
        return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", " ")

    lines = [
        "# Top repulsive Cantor-ring verification",
        "",
        f"- Started (UTC): {metadata['started_utc']}",
        f"- Device: {metadata['device']}; formulation: {metadata['formulation']}",
        f"- Solver max steps: {metadata['max_steps']} (forwarded unchanged)",
        f"- Successful tasks: {summary['successful_tasks']}; "
        f"failed tasks: {summary['failed_tasks']}",
        "- Force convention: positive repulsive; negative attractive.",
        "",
    ]
    if metadata["step_limited_run"]:
        lines.extend([
            "**Step-limited probe: these results are not evidence of solver convergence.**",
            "",
        ])
    lines.extend([
        "## All tasks",
        "",
        "Tasks not selected for this run are marked not run.",
        "",
        "| Task | State | θ (deg) | z tip (µm) | Mesh (r/tooth/bridge/z) | "
        "n ξ | Status | Force (pN) | Class | Panels | Solver seconds | "
        "Wall seconds | Error |",
        "|---|---|---:|---:|---|---:|---|---:|---|---:|---:|---:|---|",
    ])
    by_id = {record["task_id"]: record for record in records}
    for task in TASKS:
        record = by_id.get(task.task_id)
        result = record["result"] if record and record["success"] else None
        values = [
            task.task_id,
            task.state,
            WINNERS[task.winner].angle(task.state),
            task.z_tip,
            f"{task.n_r}/{task.n_phi_tooth}/{task.n_phi_bridge}/{task.n_z}",
            task.n_xi,
            result["status"] if result else (
                "verification_failed" if record else "not run"
            ),
            result["f_net_pN"] if result else None,
            classify(result["f_net_N"]) if result else None,
            result["diagnostics"]["n_panels_total"] if result else None,
            result["elapsed_seconds"] if result else None,
            record["wall_seconds"] if record else None,
            record["error"] if record else "",
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")

    reused = [record for record in records if record.get("cache_source")]
    if reused:
        lines.extend(["", "### Reused baseline provenance", ""])
        lines.extend(
            f"- {cell(record['task_id'])}: {cell(record['cache_source'])}. "
            "Solver seconds refer to the original scan run."
            for record in reused
        )

    lines.extend([
        "",
        "## 24-point vs 32-point convergence",
        "",
        "Relative difference = |F32 − F24| / max(|F24|, |F32|); "
        "defined as zero when both forces are zero.",
        "C4/C8 also refine the azimuthal mesh; C10 keeps the mesh fixed.",
        "",
        "| Winner | F24 (N) | F32 (N) | Relative difference | Tolerance | "
        "Within tolerance | Sign preserved | Note |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ])
    for code in ("C4", "C8", "C10"):
        entry = summary["convergence"][code]
        values = [
            code,
            entry.get("baseline_force_N"),
            entry.get("high_resolution_force_N"),
            entry.get("relative_difference_max_normalized"),
            entry.get("relative_tolerance"),
            entry.get("within_tolerance"),
            entry.get("sign_preserved"),
            entry.get("interpretation", entry.get("reason", "")),
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")

    lines.extend([
        "",
        "## Bipolar Disengaged-Repulsive vs Engaged-Attractive contrast",
        "",
        "Contrast ratio = F_disengaged / |F_engaged|, using the 24-point "
        "disengaged baseline. It is reported only when the disengaged force "
        "is positive and the engaged force is negative. Missing, zero-divisor, "
        "non-bipolar, or nonfinite ratios are N/A.",
        "",
        "| Winner | Disengaged force (N) | Engaged force (N) | "
        "Bipolar observed | Contrast ratio | Off-center force (N) |",
        "|---|---:|---:|---|---:|---:|",
    ])
    for code in ("C4", "C8", "C10"):
        entry = summary["characterization"][code]
        values = [
            code,
            entry["disengaged_force_N"],
            entry["engaged_force_N"],
            entry["bipolar_observed"],
            entry["bipolar_contrast_ratio"],
            entry["off_center_force_N"],
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    if metadata["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {cell(warning)}" for warning in metadata["warnings"])
    atomic_text(path, "\n".join(lines) + "\n")


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "model", "dataset", "executed_at",
        "task_id", "winner", "state", "theta_deg", "z_tip",
        "n_r", "n_phi_tooth", "n_phi_bridge", "n_z", "n_xi",
        "success", "status", "solver_status", "force_class",
        "f_net_N", "f_net_fN", "f_net_pN",
        "F_net", "F_bottom", "F_lateral_top_edge", "n_panels_total",
        "elapsed_seconds", "wall_seconds", "solver", "error",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for record in records:
        row = {key: record.get(key, "") for key in fields}
        if record["success"]:
            result = record["result"]
            row["status"] = "completed"
            row["solver_status"] = result["status"]
            for key in (
                "f_net_N", "f_net_fN", "f_net_pN",
                "elapsed_seconds", "solver",
            ):
                row[key] = result[key]
            row["force_class"] = classify(result["f_net_N"])
            for key, value in (
                ("F_net", result["F_net"]),
                ("F_bottom", result["diagnostics"]["F_bottom"]),
                ("F_lateral_top_edge", result["diagnostics"]["F_lateral_top_edge"]),
            ):
                row[key] = json.dumps(value, allow_nan=False)
            row["n_panels_total"] = result["diagnostics"]["n_panels_total"]
        else:
            row["status"] = "verification_failed"
        writer.writerow(row)
    atomic_text(path, buffer.getvalue())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps", type=int, default=0,
        help="Nonnegative solver step limit, forwarded unchanged (default: 0).",
    )
    parser.add_argument(
        "--tasks", nargs="+", choices=[task.task_id for task in TASKS],
        help="Run only these tasks, in the canonical task order.",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=REPOSITORY_ROOT / "results" / "top_repulsive_verification",
    )
    parser.add_argument(
        "--convergence-rtol", type=float, default=0.05,
        help="Maximum relative force difference for the comparison flag.",
    )
    parser.add_argument(
        "--no-plot", action="store_true", help="Do not create the force plot.",
    )
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    if not math.isfinite(args.convergence_rtol) or args.convergence_rtol < 0.0:
        parser.error("--convergence-rtol must be finite and nonnegative")
    return args


def main() -> int:
    args = parse_args()
    sys.path.insert(0, str(REPOSITORY_ROOT))
    # Repository metrics utilities use repository-relative output paths.
    os.chdir(REPOSITORY_ROOT)

    import torch
    from execution.clutch_geometry_redesign import get_scoped_clutch_elements
    from execution.casimir_bem_solver import run_bem_casimir_solver
    from utils.metrics_logger import (
        export_macros,
        log_metric,
        log_step,
        save_plot_provenance,
        set_solver_provenance,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    selected = set(args.tasks) if args.tasks else {task.task_id for task in TASKS}
    tasks = tuple(task for task in TASKS if task.task_id in selected)
    micro_probe = 0 < args.max_steps <= 10 and not args.tasks
    if micro_probe:
        tasks = (TASKS[0],)
    if not tasks:
        raise ValueError("At least one verification task is required")

    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "torch_version": torch.__version__,
        "device": device,
        "formulation": FORMULATION,
        "max_steps": args.max_steps,
        "step_limited_run": args.max_steps > 0,
        "micro_probe": micro_probe,
        "length_unit": "micrometer",
        "angle_unit": "degree",
        "force_sign_convention": "positive repulsive; negative attractive",
        "tasks": [asdict(task) for task in tasks],
        "winners": {key: asdict(value) for key, value in WINNERS.items()},
        "warnings": [],
    }
    if args.max_steps > 0:
        metadata["warnings"].append(
            "Step-limited results are probes, not evidence of solver convergence."
        )
    records: list[dict[str, Any]] = []
    write_json(output / "run_metadata.json", metadata)

    for index, task in enumerate(tasks, start=1):
        started = time.perf_counter()
        config = config_for(task)
        parameters: dict[str, Any] = {
            **task.mesh_parameters(),
            "max_steps": args.max_steps,
            "device": device,
            "formulation": FORMULATION,
        }
        record: dict[str, Any] = {
            **asdict(task),
            "model": MODEL,
            "dataset": DATASET,
            "theta_deg": config["theta_deg"],
            "success": False,
            "error": "",
        }
        config_path = output / "configs" / f"{task.task_id}.json"
        print(
            f"[{index}/{len(tasks)}] {task.task_id} "
            f"theta={config['theta_deg']:.3f} deg "
            f"z_tip={task.z_tip:+.3f} um device={device}",
            flush=True,
        )
        try:
            winner = WINNERS[task.winner]
            # The solver's element projection requires the geometry API's
            # returned elements in the configuration itself.
            elements = get_scoped_clutch_elements(
                N=winner.N,
                R_min=winner.R_min,
                R_max=winner.R_max,
                w1_ratio=winner.w1_ratio,
                min_tooth_w=winner.min_tooth_w,
            )
            if elements is None:
                raise ValueError("Geometry API returned None")
            if hasattr(elements, "__len__") and len(elements) == 0:
                raise ValueError("Geometry API returned an empty collection")
            config["elements"] = elements
            write_json(
                output / "geometry" / f"{task.task_id}.json",
                {"configuration": config, "scoped_clutch_elements": elements},
            )
            write_json(config_path, config)
            set_solver_provenance(
                solver_name=FORMULATION, solver_parameters=parameters,
            )
            cached = (
                load_cached_baseline(task, config, parameters)
                if args.max_steps == 0 else None
            )
            if cached is not None:
                record["result"], source_path = cached
                record["cache_source"] = str(source_path)
                print(f"  Reusing validated baseline: {source_path}", flush=True)
            else:
                result = run_bem_casimir_solver(
                    config,
                    n_r=task.n_r,
                    n_phi_tooth=task.n_phi_tooth,
                    n_phi_bridge=task.n_phi_bridge,
                    n_z=task.n_z,
                    n_xi=task.n_xi,
                    max_steps=args.max_steps,
                    device=device,
                    config_file=str(config_path),
                    task_id=task.task_id,
                    record_metrics=True,
                    formulation=FORMULATION,
                )
                record["result"] = validate_result(result)
            record["success"] = True
            print(
                f"  F={record['result']['f_net_pN']:+.8g} pN; "
                f"panels={record['result']['diagnostics']['n_panels_total']}; "
                f"status={record['result']['status']}",
                flush=True,
            )
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["traceback"] = traceback.format_exc()
            print(f"  FAILED: {record['error']}", file=sys.stderr, flush=True)

        record["wall_seconds"] = time.perf_counter() - started
        record["status"] = (
            "completed" if record["success"] else "verification_failed"
        )
        record["executed_at"] = datetime.now(timezone.utc).isoformat()
        records.append(record)
        write_json(output / "tasks" / f"{task.task_id}.json", record)
        write_json(output / "results.json", records)
        write_csv(output / "forces.csv", records)
        write_json(
            REPOSITORY_ROOT / "results" / "top_repulsive_verification.json",
            records,
        )
        write_csv(
            REPOSITORY_ROOT / "results" / "top_repulsive_verification.csv",
            records,
        )

        try:
            result = record.get("result")
            solver_name = result["solver"] if result is not None else FORMULATION
            solver_parameters = (
                result["solver_parameters"] if result is not None else parameters
            )
            log_step(
                task.task_id,
                {
                    "success": record["success"],
                    "configuration": config,
                    "wall_seconds": record["wall_seconds"],
                    "error": record["error"],
                    "cache_source": record.get("cache_source"),
                },
                solver_name=solver_name,
                solver_parameters=solver_parameters,
            )
            if record["success"]:
                for key in ("f_net_N", "f_net_fN", "f_net_pN", "elapsed_seconds"):
                    log_metric(
                        f"{task.task_id}_{key}",
                        record["result"][key],
                        step_id=task.task_id,
                        solver_name=solver_name,
                        solver_parameters=solver_parameters,
                    )
                log_metric(
                    f"{task.task_id}_n_panels_total",
                    record["result"]["diagnostics"]["n_panels_total"],
                    step_id=task.task_id,
                    solver_name=solver_name,
                    solver_parameters=solver_parameters,
                )
        except Exception as exc:
            metadata["warnings"].append(
                f"Metrics logging failed for {task.task_id}: {exc}"
            )

    summary = comparisons(records, args.convergence_rtol, args.max_steps > 0)
    summary["successful_tasks"] = sum(record["success"] for record in records)
    summary["failed_tasks"] = len(records) - summary["successful_tasks"]
    write_json(output / "summary.json", summary)
    write_json(
        REPOSITORY_ROOT / "results" / "top_repulsive_verification_report.json",
        summary,
    )

    if (
        not micro_probe
        and not args.no_plot
        and any(record["success"] for record in records)
    ):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            successful = [record for record in records if record["success"]]
            labels = [record["task_id"] for record in successful]
            forces = [record["result"]["f_net_pN"] for record in successful]
            figure, axis = plt.subplots(figsize=(12, 6), layout="constrained")
            try:
                axis.bar(
                    range(len(forces)), forces,
                    color=["tab:red" if force > 0.0 else "tab:blue" for force in forces],
                )
                axis.axhline(0.0, color="black", linewidth=0.8)
                axis.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
                axis.set_ylabel("Normal force (pN): + repulsive / − attractive")
                axis.set_title(
                    "Top Cantor-ring bipolar clutch verification"
                    + (" — step-limited probe" if args.max_steps > 0 else "")
                )
                axis.grid(axis="y", alpha=0.25)
                figure.savefig(output / "bipolar_forces.png", dpi=200)
                figures_dir = REPOSITORY_ROOT / "figures"
                figures_dir.mkdir(parents=True, exist_ok=True)
                metric_keys = [
                    f"{record['task_id']}_f_net_pN" for record in successful
                ]
                plot_parameters = {
                    "max_steps": args.max_steps,
                    "device": device,
                    "formulation": FORMULATION,
                    "tasks": [asdict(task) for task in tasks],
                }
                for suffix in (".png", ".pdf"):
                    fig_path = figures_dir / f"fig_top_repulsive_verification{suffix}"
                    figure.savefig(fig_path, dpi=200)
                    try:
                        save_plot_provenance(
                            str(fig_path),
                            str(REPOSITORY_ROOT / "results" / "provenance_metrics.json"),
                            metric_keys,
                            solver_name="bem",
                            solver_parameters=plot_parameters,
                        )
                    except Exception as exc:
                        metadata["warnings"].append(
                            f"Plot provenance failed for {fig_path.name}: {exc}"
                        )
            finally:
                plt.close(figure)
        except Exception as exc:
            metadata["warnings"].append(f"Plot/provenance generation failed: {exc}")

    if not micro_probe:
        try:
            export_macros()
        except Exception as exc:
            metadata["warnings"].append(f"Macro export failed: {exc}")

    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "run_metadata.json", metadata)
    write_markdown_report(
        REPOSITORY_ROOT / "results" / "top_repulsive_verification_report.md",
        records,
        summary,
        metadata,
    )
    for warning in metadata["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(
        f"Completed: {summary['successful_tasks']}/{len(tasks)} tasks succeeded. "
        f"Artifacts: {output}",
        flush=True,
    )
    return 1 if summary["failed_tasks"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Verification interrupted.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception:
        traceback.print_exc()
        raise SystemExit(1) from None
