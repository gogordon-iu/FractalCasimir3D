#!/usr/bin/env python3
"""Generate the stepped-elevation rotational-clutch Meep sweep configurations."""

from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.clutch_geometry_redesign import (  # noqa: E402
    compute_dynamic_Trun,
    get_scoped_clutch_elements,
)
from utils.metrics_logger import export_macros, log_metric, log_step  # noqa: E402


DEFAULT_OUTPUT_DIR = REPO_ROOT / "sweep_configs_rotational_z_eff_meep"
COMMON_ANGLES = (6.0, 18.0, 48.0, 0.0, 12.0, 24.0, 30.0, 36.0, 42.0)

Z_TIP_UM = -0.100
Z_PAD_TOP_UM = -0.115
RESOLUTION = 50


@dataclass(frozen=True)
class Candidate:
    name: str
    n: int
    r_min_um: float
    r_max_um: float
    w1_ratio: float
    min_tooth_w_um: float
    tooth_arc_deg: float
    domain_um: float
    angles_deg: tuple[float, ...]


CANDIDATES = (
    Candidate(
        "Rot_C8_Compact_N2",
        2,
        0.20,
        0.90,
        0.45,
        0.020,
        15.0,
        2.0,
        COMMON_ANGLES,
    ),
    Candidate(
        "Rot_C4_TightSlot_N2",
        2,
        0.30,
        1.35,
        0.65,
        0.020,
        15.0,
        3.0,
        COMMON_ANGLES,
    ),
    Candidate(
        "Rot_C10_Fractal_N3",
        3,
        0.30,
        1.65,
        0.40,
        0.015,
        12.0,
        3.5,
        (3.0, 21.0, 48.0),
    ),
)


def finite_number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise TypeError(f"{label} must be numeric, not {type(value).__name__}.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"{label} must be a finite real number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite; received {number!r}.")
    if positive and number <= 0.0:
        raise ValueError(f"{label} must be positive; received {number!r}.")
    return number


def json_value(value: Any, label: str) -> Any:
    """Convert geometry scalars/arrays to JSON without silently losing data."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return finite_number(value, label)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{label} contains a non-string dictionary key.")
            result[key] = json_value(item, f"{label}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [json_value(item, f"{label}[{i}]") for i, item in enumerate(value)]

    # NumPy scalars and arrays, without requiring NumPy in this generator.
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar = item_method()
        except ValueError:
            scalar = value
        if scalar is not value:
            return json_value(scalar, label)
    tolist_method = getattr(value, "tolist", None)
    if callable(tolist_method):
        return json_value(tolist_method(), label)
    raise TypeError(f"{label} contains unsupported type {type(value).__name__}.")


def invoke_by_signature(
    function: Callable[..., Any],
    values: Mapping[str, Any],
    *,
    variadic_values: Mapping[str, Any] | None = None,
) -> Any:
    """Bind existing repository APIs by name, preserving their default values."""
    signature = inspect.signature(function)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    has_var_kwargs = False

    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_kwargs = True
            continue

        if name in values:
            value = values[name]
        elif parameter.default is not inspect.Parameter.empty:
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                args.append(parameter.default)
            continue
        else:
            raise TypeError(
                f"Cannot bind required parameter {name!r} of "
                f"{function.__module__}.{function.__name__}{signature}."
            )

        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[name] = value

    if has_var_kwargs and variadic_values:
        for name, value in variadic_values.items():
            if name not in signature.parameters:
                kwargs[name] = value

    signature.bind(*args, **kwargs)
    return function(*args, **kwargs)


def compute_run_parameters(domain_um: float, d_eff_um: float) -> tuple[float, float]:
    """Obtain T_run and Sigma from the repository's authoritative helper."""
    result = invoke_by_signature(
        compute_dynamic_Trun,
        {
            "L_domain_um": domain_um,
            "L_domain": domain_um,
            "L_um": domain_um,
            "L": domain_um,
            "d_eff_um": d_eff_um,
            "d_eff": d_eff_um,
            "resolution": RESOLUTION,
            "res": RESOLUTION,
            "nmax": 1,
            "pml_thickness_um": 0.25,
            "pml_thickness": 0.25,
            "courant": 0.5,
        },
        variadic_values={
            "L_domain_um": domain_um,
            "d_eff_um": d_eff_um,
            "resolution": RESOLUTION,
        },
    )

    if isinstance(result, Mapping):
        if "T_run" not in result:
            raise ValueError("compute_dynamic_Trun did not return T_run.")
        sigma_key = "Sigma" if "Sigma" in result else "sigma"
        if sigma_key not in result:
            raise ValueError("compute_dynamic_Trun did not return Sigma.")
        run_time, sigma = result["T_run"], result[sigma_key]
    elif hasattr(result, "T_run") and (
        hasattr(result, "Sigma") or hasattr(result, "sigma")
    ):
        run_time = result.T_run
        sigma = getattr(result, "Sigma", getattr(result, "sigma", None))
    elif isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        if len(result) != 2:
            raise ValueError("compute_dynamic_Trun must return (T_run, Sigma).")
        run_time, sigma = result
        if isinstance(sigma, Mapping):
            if "Sigma" not in sigma and "sigma" not in sigma:
                raise ValueError("compute_dynamic_Trun did not return Sigma.")
            sigma = sigma.get("Sigma", sigma.get("sigma"))
    else:
        raise TypeError(
            "compute_dynamic_Trun must return (T_run, Sigma), or a mapping "
            "containing T_run and Sigma; refusing to invent Sigma."
        )

    return (
        finite_number(run_time, "T_run", positive=True),
        finite_number(sigma, "Sigma", positive=True),
    )


def make_candidate_configs(candidate: Candidate) -> list[dict[str, Any]]:
    raw_elements = get_scoped_clutch_elements(
        candidate.n,
        candidate.r_min_um,
        candidate.r_max_um,
        candidate.w1_ratio,
        candidate.min_tooth_w_um,
    )
    if raw_elements is None or isinstance(raw_elements, (str, bytes, Mapping)):
        raise TypeError(f"{candidate.name}: geometry must be an iterable of dicts.")

    elements: list[dict[str, Any]] = []
    clearances: list[float] = []
    for index, raw_element in enumerate(raw_elements):
        if not isinstance(raw_element, Mapping):
            raise TypeError(f"{candidate.name}: element {index} is not a mapping.")
        element = json_value(raw_element, f"{candidate.name}.geometry[{index}]")
        if not isinstance(element, dict):
            raise TypeError("Geometry serialization did not produce a dictionary.")
        if "W_slot" not in element or "w_tooth" not in element:
            raise KeyError(
                f"{candidate.name}: element {index} needs W_slot and w_tooth."
            )
        slot = finite_number(element["W_slot"], "W_slot", positive=True)
        tooth = finite_number(element["w_tooth"], "w_tooth", positive=True)
        clearance = finite_number(
            (slot - tooth) / 2.0,
            f"{candidate.name}.geometry[{index}].half_slot_clearance",
            positive=True,
        )
        elements.append(element)
        clearances.append(clearance)

    if not elements:
        raise ValueError(f"{candidate.name}: generated geometry is empty.")

    d_eff_um = finite_number(
        min(abs(Z_TIP_UM - Z_PAD_TOP_UM), min(clearances)),
        "d_eff_um",
        positive=True,
    )
    run_time, sigma = compute_run_parameters(candidate.domain_um, d_eff_um)

    base: dict[str, Any] = {
        "candidate_name": candidate.name,
        "N_fractal": candidate.n,
        "R_min_um": candidate.r_min_um,
        "R_max_um": candidate.r_max_um,
        "w1_ratio": candidate.w1_ratio,
        "min_tooth_w_um": candidate.min_tooth_w_um,
        "z_tip_um": Z_TIP_UM,
        "z_pad_top_um": Z_PAD_TOP_UM,
        "t_membrane_um": 0.025,
        "t_landing_pad_um": 0.150,
        "H_teeth_um": 0.250,
        "num_sectors": 4,
        "aperture_arc_deg": 36.0,
        "bridge_arc_deg": 54.0,
        "tooth_arc_deg": candidate.tooth_arc_deg,
        "L_domain_um": candidate.domain_um,
        "resolution": RESOLUTION,
        "nmax": 1,
        "pml_thickness_um": 0.25,
        "courant": 0.5,
        "T_run": run_time,
        "d_eff_um": d_eff_um,
        "Sigma": sigma,
        "material": "Gold",
        "stress_box_mode": "per_tooth_rotor_frame",
        "geometry": elements,
    }
    return [{**base, "theta_deg": angle} for angle in candidate.angles_deg]


def atomic_write_json(path: Path, data: Any) -> None:
    payload = json.dumps(data, indent=2, allow_nan=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def record_step(message: str, details: Mapping[str, Any]) -> None:
    invoke_by_signature(
        log_step,
        {
            "step": "generate_rotational_z_eff_meep_configs",
            "step_name": "generate_rotational_z_eff_meep_configs",
            "name": "generate_rotational_z_eff_meep_configs",
            "message": message,
            "description": message,
            "details": dict(details),
            "metadata": dict(details),
            "data": dict(details),
            "status": "completed",
        },
        variadic_values={"message": message, "details": dict(details)},
    )


def record_metric(name: str, value: float, unit: str) -> None:
    invoke_by_signature(
        log_metric,
        {
            "name": name,
            "metric": name,
            "metric_name": name,
            "key": name,
            "value": value,
            "metric_value": value,
            "unit": unit,
            "units": unit,
            "step": "generate_rotational_z_eff_meep_configs",
            "description": name,
        },
        variadic_values={"unit": unit},
    )


def export_provenance(path: Path) -> None:
    invoke_by_signature(
        export_macros,
        {
            "path": str(path),
            "output_path": str(path),
            "output_file": str(path),
            "output_filename": str(path),
            "filename": str(path),
            "filepath": str(path),
            "file_path": str(path),
            "tex_path": str(path),
            "output_dir": str(path.parent),
        },
    )
    export_macros()


def positive_task_limit(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--max-steps must be an integer.") from exc
    if not 1 <= value <= 21:
        raise argparse.ArgumentTypeError("--max-steps must be between 1 and 21.")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination directory (default: repository sweep directory).",
    )
    parser.add_argument(
        "--max-steps",
        type=positive_task_limit,
        default=21,
        help="Generate the first 1–21 tasks; defaults to the complete sweep.",
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()

    configs: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        if len(configs) >= args.max_steps:
            break
        for config in make_candidate_configs(candidate):
            if len(configs) >= args.max_steps:
                break
            configs.append({"task_id": len(configs) + 1, **config})

    if len(configs) != args.max_steps:
        raise RuntimeError("Generated task count does not match the requested limit.")

    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for config in configs:
        task_id = config["task_id"]
        filename = f"config_{task_id:03d}.json"
        atomic_write_json(output_dir / filename, config)
        entries.append(
            {
                "task_id": task_id,
                "filename": filename,
                "candidate_name": config["candidate_name"],
                "theta_deg": config["theta_deg"],
                "d_eff_um": config["d_eff_um"],
                "T_run": config["T_run"],
                "Sigma": config["Sigma"],
                "geometry_element_count": len(config["geometry"]),
            }
        )

    manifest = {
        "schema_version": 1,
        "generator": "execution/generate_rotational_z_eff_meep_configs.py",
        "sweep_name": "Stepped-Elevation Rotational Clutch",
        "task_count": len(configs),
        "total_planned_tasks": 21,
        "complete": len(configs) == 21,
        "geometry_provider": (
            "execution.clutch_geometry_redesign.get_scoped_clutch_elements"
        ),
        "run_time_provider": "execution.clutch_geometry_redesign.compute_dynamic_Trun",
        "d_eff_definition": (
            "min(abs(z_tip_um-z_pad_top_um), "
            "min((el['W_slot']-el['w_tooth'])/2 for el in geometry))"
        ),
        "tasks": entries,
    }
    atomic_write_json(output_dir / "manifest.json", manifest)

    record_step(
        "Generated rotational z-effective Meep sweep configurations.",
        {
            "output_dir": str(output_dir),
            "manifest": str(output_dir / "manifest.json"),
            "task_count": len(configs),
            "complete": len(configs) == 21,
        },
    )
    record_metric("rotational_z_eff_meep_config_count", float(len(configs)), "configs")
    for name in dict.fromkeys(config["candidate_name"] for config in configs):
        representative = next(c for c in configs if c["candidate_name"] == name)
        record_metric(f"{name}_d_eff_um", representative["d_eff_um"], "um")
        record_metric(f"{name}_T_run", representative["T_run"], "Meep time units")
        record_metric(f"{name}_Sigma", representative["Sigma"], "Meep units")
    export_provenance(output_dir / "provenance_macros.tex")

    print(f"Wrote {len(configs)} configurations and manifest.json to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
