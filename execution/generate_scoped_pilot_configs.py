#!/usr/bin/env python3
"""Generate the two Scoped Pilot Concentric Casimir Clutch configurations.

Run from the repository root, or execute this file directly:

    python execution/generate_scoped_pilot_configs.py --verify
    python execution/generate_scoped_pilot_configs.py --output-dir /tmp/pilot --verify

Geometry and dynamic run-time calculations are delegated to
execution.clutch_geometry_redesign; no substitute physics is implemented here.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import logging
import math
import numbers
import os
from pathlib import Path
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from types import ModuleType
from typing import Any


# Support both direct execution and `python -m execution.generate_scoped_pilot_configs`.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from execution.clutch_geometry_redesign import (  # noqa: E402
    compute_dynamic_Trun,
    get_scoped_clutch_elements,
)


LOGGER = logging.getLogger("generate_scoped_pilot_configs")


def load_metrics_logger() -> ModuleType | None:
    """Load the optional grounded-experiment-pipeline logging integration."""
    try:
        return importlib.import_module("utils.metrics_logger")
    except ImportError as exc:
        LOGGER.debug("Optional metrics logger is unavailable: %s", exc)
        return None


PHYSICAL_PARAMETERS: dict[str, int | float | str | list[str]] = {
    "N_fractal": 2,
    "num_tracks": 3,
    "L_domain_um": 3.0,
    "R_min_um": 0.30,
    "R_max_um": 1.35,
    "H_teeth_um": 0.250,
    "z_tip_um": 0.015,
    "z_tip_nm": 15.0,
    "t_membrane_um": 0.025,
    "t_landing_pad_um": 0.150,
    "num_sectors": 4,
    "aperture_arc_deg": 30.0,
    "bridge_arc_deg": 60.0,
    "tooth_arc_deg": 15.0,
    "resolution": 80,
    "nmax": 1,
    "material": "Gold",
    "inclusion_exclusion_passes": 4,
    "configurations": ["both", "rotor", "stator", "vac"],
}

PILOT_TASKS: tuple[tuple[float, str, str, str], ...] = (
    (
        0.0,
        "Disengaged",
        "REPULSIVE",
        "Tooth centered in the 30 deg aperture.",
    ),
    (
        45.0,
        "Engaged",
        "ATTRACTIVE",
        "Tooth centered on the 60 deg reinforced 150 nm landing pad.",
    ),
)


def to_json_value(value: Any, path: str = "$", active: set[int] | None = None) -> Any:
    """Convert scientific data without silently dropping fields or invalid floats."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"Non-finite numeric value at {path}: {value!r}")
        return result
    if isinstance(value, numbers.Complex):
        return {
            "real": to_json_value(value.real, f"{path}.real", active),
            "imag": to_json_value(value.imag, f"{path}.imag", active),
        }
    if isinstance(value, Path):
        return str(value)

    if active is None:
        active = set()
    identity = id(value)
    if identity in active:
        raise ValueError(f"Cyclic data cannot be serialized at {path}")
    active.add(identity)
    try:
        if isinstance(value, Mapping):
            result_dict: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError(f"JSON object key at {path} must be a string: {key!r}")
                result_dict[key] = to_json_value(item, f"{path}.{key}", active)
            return result_dict
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: to_json_value(
                    getattr(value, field.name), f"{path}.{field.name}", active
                )
                for field in dataclasses.fields(value)
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [
                to_json_value(item, f"{path}[{index}]", active)
                for index, item in enumerate(value)
            ]

        # NumPy arrays/scalars and similar scientific containers.
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            return to_json_value(tolist(), path, active)

        # Explicit conversion contracts are safer than dumping arbitrary object state.
        for method_name in ("to_dict", "as_dict"):
            converter = getattr(value, method_name, None)
            if callable(converter):
                return to_json_value(converter(), path, active)

        raise TypeError(
            f"Unsupported value at {path}: {type(value).__module__}."
            f"{type(value).__qualname__}. Geometry must return JSON-compatible "
            "data, dataclasses, or objects exposing to_dict()/as_dict()."
        )
    finally:
        active.remove(identity)


def geometry_for_angle(theta_deg: float) -> Any:
    """Return radial elements, which depend on N rather than the rotation angle."""
    geometry = get_scoped_clutch_elements(N=int(PHYSICAL_PARAMETERS["N_fractal"]))
    serialized = to_json_value(geometry, "$.geometry")
    if serialized is None or serialized == [] or serialized == {}:
        raise ValueError(f"Geometry helper returned empty geometry for theta={theta_deg}")
    return serialized


def dynamic_run_time() -> tuple[float, dict[str, Any]]:
    """Require both a positive run time and the helper's complete diagnostics."""
    raw = compute_dynamic_Trun(d_eff_um=float(PHYSICAL_PARAMETERS["z_tip_um"]))
    diagnostic_data: Mapping[str, Any]
    time_value: Any

    if isinstance(raw, Mapping):
        diagnostic_data = raw
        candidates = ("T_run", "Trun", "T_run_fs", "T_run_meep", "t_run")
        matching = [key for key in candidates if key in raw]
        if not matching:
            raise ValueError(
                "compute_dynamic_Trun returned a dictionary without a recognized "
                f"run-time key; expected one of {candidates}"
            )
        time_value = raw[matching[0]]
    elif isinstance(raw, (tuple, list)) and len(raw) == 2:
        time_value, diagnostic_data = raw
        if not isinstance(diagnostic_data, Mapping):
            raise TypeError("The second compute_dynamic_Trun result must be diagnostics.")
    else:
        raise TypeError(
            "compute_dynamic_Trun must return (T_run, diagnostics_dict) or a "
            "dictionary containing T_run and its complete mathematical diagnostics."
        )

    if isinstance(time_value, bool) or not isinstance(time_value, numbers.Real):
        raise TypeError("T_run must be a real number, not a boolean or string.")
    run_time = float(time_value)
    if not math.isfinite(run_time) or run_time <= 0.0:
        raise ValueError(f"T_run must be finite and strictly positive, got {run_time!r}")
    if not diagnostic_data:
        raise ValueError("compute_dynamic_Trun returned an empty diagnostic dictionary.")

    diagnostics = to_json_value(diagnostic_data, "$.provenance.dynamic_Trun_diagnostics")
    return run_time, diagnostics


def validate_physical_parameters() -> None:
    to_json_value(PHYSICAL_PARAMETERS)
    p = PHYSICAL_PARAMETERS
    if not 0.0 < float(p["R_min_um"]) < float(p["R_max_um"]) < float(p["L_domain_um"]) / 2:
        raise ValueError("Radii must be positive, ordered, and fit inside the domain.")
    if not math.isclose(
        float(p["z_tip_nm"]), 1000.0 * float(p["z_tip_um"]), rel_tol=1e-12
    ):
        raise ValueError("z_tip_nm and z_tip_um are inconsistent.")
    if not math.isclose(
        int(p["num_sectors"]) * (float(p["aperture_arc_deg"]) + float(p["bridge_arc_deg"])),
        360.0,
        abs_tol=1e-12,
    ):
        raise ValueError("Sector apertures and bridges must span exactly 360 degrees.")
    if not 0.0 < float(p["tooth_arc_deg"]) <= float(p["aperture_arc_deg"]):
        raise ValueError("The tooth must fit within the aperture.")
    for key in ("H_teeth_um", "z_tip_um", "t_membrane_um", "t_landing_pad_um"):
        if float(p[key]) <= 0.0:
            raise ValueError(f"{key} must be positive.")
    for key in (
        "N_fractal", "num_tracks", "num_sectors", "resolution", "nmax",
        "inclusion_exclusion_passes",
    ):
        value = p[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{key} must be a positive integer.")


def encode_json(document: Mapping[str, Any]) -> str:
    return json.dumps(to_json_value(document), indent=2, sort_keys=True, allow_nan=False) + "\n"


def atomic_write(path: Path, text: str) -> None:
    """Replace each file atomically; publish the suite manifest last."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_outputs(output_dir: Path, expected: Mapping[str, Mapping[str, Any]]) -> None:
    for filename, document in expected.items():
        path = output_dir / filename
        with path.open("r", encoding="utf-8") as handle:
            actual = json.load(handle)
        if actual != to_json_value(document):
            raise ValueError(f"Written configuration differs from expected data: {path}")
    manifest = expected["master_clutch_pilot_suite.json"]
    if manifest["num_tasks"] != 2:
        raise ValueError("The pilot suite must contain exactly two tasks.")
    for entry in manifest["tasks"]:
        config = expected[entry["config_file"]]
        if config["theta_deg"] != entry["theta_deg"]:
            raise ValueError("Manifest/config angle mismatch.")
        if config["expected_regime"] != entry["expected_regime"]:
            raise ValueError("Manifest/config expected-regime mismatch.")
        for key, value in PHYSICAL_PARAMETERS.items():
            if config.get(key) != value:
                raise ValueError(f"Incorrect physical parameter {key!r}.")


def generate_configs(output_dir: Path, verify: bool) -> list[Path]:
    validate_physical_parameters()
    metrics_module = load_metrics_logger()
    pipeline_logger = getattr(metrics_module, "logger", None)
    if isinstance(pipeline_logger, logging.Logger):
        pipeline_logger.info("Generating Scoped Pilot Concentric Casimir Clutch suite")

    run_time, diagnostics = dynamic_run_time()
    timestamp = datetime.now(timezone.utc).isoformat()
    documents: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []

    provenance: dict[str, Any] = {
        "generated_at_utc": timestamp,
        "generator": "execution/generate_scoped_pilot_configs.py",
        "geometry_function": "execution.clutch_geometry_redesign.get_scoped_clutch_elements",
        "T_run_function": "execution.clutch_geometry_redesign.compute_dynamic_Trun",
        "T_run_inputs": {"z_tip_um": PHYSICAL_PARAMETERS["z_tip_um"]},
        "dynamic_Trun_diagnostics": diagnostics,
        "metrics_logger_available": metrics_module is not None,
        "T_run_units": "Native units returned by compute_dynamic_Trun; no conversion applied.",
        "regime_note": "Expected regimes are pilot hypotheses, not simulation results.",
    }

    for task_id, (theta_deg, state, regime, description) in enumerate(PILOT_TASKS, start=1):
        filename = f"config_{task_id:03d}.json"
        documents[filename] = {
            "schema_version": 1,
            "suite_name": "Scoped Pilot Concentric Casimir Clutch",
            "task_id": task_id,
            "task_name": state,
            "description": description,
            **PHYSICAL_PARAMETERS,
            "theta_deg": theta_deg,
            "expected_regime": regime,
            "T_run": run_time,
            "geometry": geometry_for_angle(theta_deg),
            "provenance": provenance,
        }
        entries.append({
            "task_id": task_id,
            "config_file": filename,
            "theta_deg": theta_deg,
            "task_name": state,
            "expected_regime": regime,
            "description": description,
        })

    documents["master_clutch_pilot_suite.json"] = {
        "schema_version": 1,
        "suite_name": "Scoped Pilot Concentric Casimir Clutch",
        "num_tasks": len(entries),
        "N_fractal": 2,
        "angles_deg": [task[0] for task in PILOT_TASKS],
        "physical_parameters": dict(PHYSICAL_PARAMETERS),
        "T_run": run_time,
        "tasks": entries,
        "provenance": provenance,
    }

    # Serialize everything before writing anything to avoid partial output caused
    # by malformed geometry or diagnostics.
    encoded = {name: encode_json(document) for name, document in documents.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, text in encoded.items():
        path = output_dir / filename
        atomic_write(path, text)
        paths.append(path)
        LOGGER.info("Wrote %s", path)

    (output_dir / "config_003.json").unlink(missing_ok=True)

    if verify:
        verify_outputs(output_dir, documents)
        LOGGER.info("Verified all two configurations and the master suite.")

    if metrics_module is not None:
        metrics_module.log_step(
            "generate_scoped_pilot_configs",
            {
                "num_tasks": 2,
                "N_fractal": 2,
                "resolution": 80,
                "angles_deg": [0.0, 45.0],
                "T_run": run_time,
            },
        )
        metrics_module.export_macros()

    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "sweep_configs_clutch_pilot",
        help="Destination directory (default: repository/sweep_configs_clutch_pilot).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read back and verify all generated JSON files.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        generate_configs(args.output_dir.expanduser().resolve(), args.verify)
    except Exception:
        LOGGER.exception("Failed to generate the Scoped Pilot configuration suite.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
