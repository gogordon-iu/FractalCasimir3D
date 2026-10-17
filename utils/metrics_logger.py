"""
Provenance Logger Utility for Grounded Experiment Pipelines.
Enforces empirical tracking across experiment execution, plot generation,
LaTeX macro synchronization, and manuscript mapping.
"""

import os
import sys
import json
import inspect
import hashlib
import datetime
import re
import shutil
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, Optional

import platform

RESULTS_DIR = Path("results")
DEFAULT_METRICS_PATH = RESULTS_DIR / "provenance_metrics.json"
DEFAULT_MACROS_PATH = RESULTS_DIR / "macros_results.tex"
DEFAULT_MAP_PATH = Path("manuscript_provenance_map.json")

_ACTIVE_SOLVER_NAME: Optional[str] = None
_ACTIVE_SOLVER_PARAMS: Optional[Dict[str, Any]] = None

DIGIT_WORDS = {
    "0": "Zero",
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
}


def _resolve_manifest_paths(metrics_path: str) -> tuple[Path, Path]:
    path = Path(metrics_path)
    if path.suffix.lower() == ".jsonl":
        return path.with_suffix(".json"), path
    return path, path.with_suffix(".jsonl")


def _replace_with_retry(tmp_path: Path, path: Path) -> None:
    for attempt in range(20):
        try:
            os.replace(tmp_path, path)
            return
        except OSError:
            if attempt == 19:
                raise
            time.sleep(0.02)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as f:
            tmp_path = Path(f.name)
            json.dump(payload, f, indent=2)
        _replace_with_retry(tmp_path, path)
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as f:
            tmp_path = Path(f.name)
            f.write(text)
        _replace_with_retry(tmp_path, path)
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _read_json_with_retry(path: Path) -> Any:
    for attempt in range(20):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            if attempt == 19:
                raise
            time.sleep(0.02)


def _get_caller_info(skip_frames: int = 2) -> Dict[str, Any]:
    stack = inspect.stack()
    if not stack:
        return {"source_file": "UNKNOWN", "source_function": "UNKNOWN", "line_number": -1}
    frame = stack[skip_frames] if len(stack) > skip_frames else stack[-1]
    module_path = os.path.relpath(frame.filename, os.getcwd()) if os.path.isabs(frame.filename) else frame.filename
    return {
        "source_file": str(module_path).replace("\\", "/"),
        "source_function": frame.function,
        "line_number": frame.lineno,
    }


def _compute_sha256(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return "UNKNOWN_OR_MISSING"
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _ensure_manifest_fields(
    manifest: Dict[str, Any],
    solver_name: Optional[str] = None,
    solver_parameters: Optional[Dict[str, Any]] = None,
) -> None:
    metadata = manifest.setdefault("run_metadata", {})
    parameters = solver_parameters
    if not isinstance(parameters, Mapping):
        parameters = metadata.get("solver_parameters", {})
    if not isinstance(parameters, Mapping):
        parameters = {}

    manifest["model"] = next(
        (
            candidate
            for candidate in (solver_name, metadata.get("solver"))
            if isinstance(candidate, str)
            and candidate.strip()
            and candidate != "unspecified"
        ),
        "FractalCasimirSolver",
    )
    manifest["dataset"] = next(
        (
            candidate
            for candidate in (parameters.get("dataset"), metadata.get("dataset"))
            if isinstance(candidate, str) and candidate.strip()
        ),
        "fractal_casimir_3d",
    )
    manifest["status"] = "completed"
    manifest["executed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()


def _save_manifest(metrics_path: str, manifest: Dict[str, Any]) -> None:
    manifest_path, jsonl_path = _resolve_manifest_paths(metrics_path)
    _ensure_manifest_fields(manifest)

    lines = []
    for key, record in manifest.get("metrics", {}).items():
        value = record.get("value")
        lines.append(json.dumps({
            "model": manifest["model"],
            "dataset": manifest["dataset"],
            "status": "completed",
            "executed_at": manifest["executed_at"],
            "metric_key": key,
            "value": value,
            "step_id": record.get("step_id"),
            "source_file": record.get("source_file"),
            "solver": record.get("solver", manifest["model"]),
            "metrics": {key: value},
        }, sort_keys=True))

    _atomic_write_json(manifest_path, manifest)
    _atomic_write_text(jsonl_path, "\n".join(lines) + ("\n" if lines else ""))


def _load_or_init_manifest(path: Path) -> Dict[str, Any]:
    path, _ = _resolve_manifest_paths(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        manifest = _read_json_with_retry(path)
    else:
        manifest = {
            "run_metadata": {
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "environment": platform.system(),
                "entry_point": _get_caller_info(skip_frames=3)["source_file"],
            },
            "intermediate_steps": {},
            "metrics": {},
        }
    _ensure_manifest_fields(manifest)
    return manifest


def _resolve_solver_provenance(
    solver_name: Optional[str] = None,
    solver_parameters: Optional[Dict[str, Any]] = None,
    data: Any = None,
    existing_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve solver provenance in explicit, data, active, environment, manifest order."""
    data_mapping = data if isinstance(data, Mapping) else {}
    metadata = {}
    if isinstance(existing_manifest, Mapping):
        candidate = existing_manifest.get("run_metadata", {})
        if isinstance(candidate, Mapping):
            metadata = candidate

    name = next(
        (
            candidate
            for candidate in (
                solver_name,
                data_mapping.get("solver"),
                data_mapping.get("solver_name"),
                _ACTIVE_SOLVER_NAME,
                os.environ.get("CASIMIR_SOLVER"),
                metadata.get("solver"),
            )
            if isinstance(candidate, str) and candidate.strip()
        ),
        "unspecified",
    )

    parameters = next(
        (
            dict(candidate)
            for candidate in (
                solver_parameters,
                data_mapping.get("solver_parameters"),
                data_mapping.get("parameters"),
                _ACTIVE_SOLVER_PARAMS,
            )
            if isinstance(candidate, Mapping)
        ),
        None,
    )
    if parameters is None:
        env_parameters = os.environ.get("CASIMIR_SOLVER_PARAMS")
        if env_parameters:
            try:
                parsed_parameters = json.loads(env_parameters)
            except (ValueError, TypeError):
                parsed_parameters = None
            if isinstance(parsed_parameters, Mapping):
                parameters = dict(parsed_parameters)

    if parameters is None:
        existing_parameters = metadata.get("solver_parameters")
        parameters = dict(existing_parameters) if isinstance(existing_parameters, Mapping) else {}

    return {"solver": name, "solver_parameters": parameters}


def set_solver_provenance(
    solver_name: str,
    solver_parameters: Optional[Dict[str, Any]] = None,
    metrics_path: str = str(DEFAULT_METRICS_PATH),
) -> Dict[str, Any]:
    """Activate a solver and record its configuration and run in the manifest."""
    global _ACTIVE_SOLVER_NAME, _ACTIVE_SOLVER_PARAMS

    if not isinstance(solver_name, str) or not solver_name.strip():
        raise ValueError("solver_name must be a non-empty string")
    if solver_parameters is not None and not isinstance(solver_parameters, Mapping):
        raise TypeError("solver_parameters must be a mapping or None")

    parameters = dict(solver_parameters) if solver_parameters is not None else {}
    path = Path(metrics_path)
    manifest = _load_or_init_manifest(path)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata = manifest["run_metadata"]
    metadata["solver"] = solver_name
    metadata["solver_parameters"] = parameters
    metadata.setdefault("solver_runs", []).append({
        "solver": solver_name,
        "solver_parameters": dict(parameters),
        "timestamp": timestamp,
    })
    metadata["updated_at"] = timestamp

    _save_manifest(metrics_path, manifest)

    _ACTIVE_SOLVER_NAME = solver_name
    _ACTIVE_SOLVER_PARAMS = dict(parameters)
    return manifest


def log_step(
    name: str,
    data: Any,
    metrics_path: str = str(DEFAULT_METRICS_PATH),
    solver_name: Optional[str] = None,
    solver_parameters: Optional[Dict[str, Any]] = None,
) -> None:
    """Records intermediate pipeline state transitions, splits, or matrix reductions."""
    path = Path(metrics_path)
    manifest = _load_or_init_manifest(path)
    caller = _get_caller_info(skip_frames=1)
    solver = _resolve_solver_provenance(
        solver_name, solver_parameters, data=data, existing_manifest=manifest
    )

    manifest["intermediate_steps"][name] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_file": caller["source_file"],
        "source_function": caller["source_function"],
        "line_number": caller["line_number"],
        "data_summary": data,
        **solver,
    }
    if solver["solver"] != "unspecified":
        manifest["run_metadata"].update(solver)
    else:
        manifest["run_metadata"]["solver_parameters"] = solver["solver_parameters"]
    manifest["run_metadata"]["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _save_manifest(metrics_path, manifest)


def log_metric(
    key: str,
    value: Any,
    step_id: Optional[str] = None,
    metrics_path: str = str(DEFAULT_METRICS_PATH),
    solver_name: Optional[str] = None,
    solver_parameters: Optional[Dict[str, Any]] = None,
) -> None:
    """Records final metric with rigorous caller lineage."""
    path = Path(metrics_path)
    manifest = _load_or_init_manifest(path)
    caller = _get_caller_info(skip_frames=1)
    resolved_step_id = step_id or "final_evaluation"
    step = manifest.get("intermediate_steps", {}).get(resolved_step_id)
    solver = _resolve_solver_provenance(
        solver_name, solver_parameters, data=step, existing_manifest=manifest
    )

    manifest["metrics"][key] = {
        "value": value,
        "source_file": caller["source_file"],
        "source_function": caller["source_function"],
        "line_number": caller["line_number"],
        "step_id": resolved_step_id,
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **solver,
    }
    if solver["solver"] != "unspecified":
        manifest["run_metadata"].update(solver)
    else:
        manifest["run_metadata"]["solver_parameters"] = solver["solver_parameters"]
    manifest["run_metadata"]["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _save_manifest(metrics_path, manifest)


def log_metrics(
    metrics=None,
    *,
    step_id=None,
    metrics_path=str(DEFAULT_METRICS_PATH),
    solver_name=None,
    solver_parameters=None,
    **kwargs,
) -> None:
    """Log scalar metrics, flattening nested mappings into dot-separated keys."""
    if metrics is not None and not isinstance(metrics, Mapping):
        raise TypeError("metrics must be a mapping or None")

    entries = dict(metrics) if metrics is not None else {}
    entries.update(kwargs)

    def record_entries(mapping, prefix=""):
        for key, value in mapping.items():
            metric_key = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, Mapping):
                record_entries(value, metric_key)
            elif isinstance(value, (int, float, str)):
                log_metric(
                    metric_key,
                    value,
                    step_id=step_id,
                    metrics_path=metrics_path,
                    solver_name=solver_name,
                    solver_parameters=solver_parameters,
                )

    record_entries(entries)
    # Empty or non-scalar inputs still produce a valid manifest for export.
    manifest_path, _ = _resolve_manifest_paths(metrics_path)
    if not manifest_path.exists():
        _save_manifest(metrics_path, _load_or_init_manifest(manifest_path))
    export_macros(metrics_path=metrics_path)


log_experiment_metrics = log_metrics
log = log_metrics
record = log_metrics


def _sanitize_macro_name(key: str) -> str:
    """
    Sanitizes arbitrary string into a standard LaTeX macro name.
    Standard LaTeX requires command names to consist solely of alphabet letters [a-zA-Z].
    Digits are converted into words (e.g. 1 -> One) to prevent LaTeX syntax errors.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", key)
    words = cleaned.split()
    sanitized_words = []
    for word in words:
        word_chars = []
        for char in word:
            if char.isdigit():
                word_chars.append(DIGIT_WORDS[char])
            else:
                word_chars.append(char)
        sanitized_words.append("".join(word_chars).capitalize())
    result = "".join(sanitized_words)
    # Strictly enforce pure alphabetic characters for valid LaTeX \\newcommand
    result = re.sub(r"[^a-zA-Z]", "", result)
    return result or "MacroValue"


def export_macros(
    metrics_path: str = str(DEFAULT_METRICS_PATH),
    output_path: str = str(DEFAULT_MACROS_PATH),
) -> None:
    """Exports scalar values in provenance_metrics.json into LaTeX macros."""
    in_path, _ = _resolve_manifest_paths(metrics_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Cannot find metrics manifest at {in_path}")

    manifest = _read_json_with_retry(in_path)

    metrics = manifest.get("metrics", {})
    lines = [
        "% Auto-generated by utils.metrics_logger. DO NOT EDIT DIRECTLY.",
        f"% Generated at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        "",
    ]

    for key, data in sorted(metrics.items()):
        val = data.get("value")
        if isinstance(val, (int, float, str)):
            macro_name = _sanitize_macro_name(key)
            if isinstance(val, float):
                if val != 0 and (abs(val) < 1e-4 or abs(val) >= 1e5):
                    formatted_val = f"{val:.2e}"
                else:
                    formatted_val = f"{val:.6g}"
                    if "." in formatted_val:
                        formatted_val = formatted_val.rstrip("0").rstrip(".")
            else:
                formatted_val = str(val)
            lines.append(f"\\newcommand{{\\{macro_name}}}{{{formatted_val}}}")

    _atomic_write_text(out_path, "\n".join(lines) + "\n")


def save_plot_provenance(
    figure_path: str,
    data_source: str,
    columns_used: List[str],
    sidecar_suffix: str = ".provenance.json",
    solver_name: Optional[str] = None,
    solver_parameters: Optional[Dict[str, Any]] = None,
) -> str:
    """Generates full-filename and legacy stem-based sidecars for a figure."""
    fig = Path(figure_path)
    sidecar_path = fig.parent / f"{fig.stem}{sidecar_suffix}"
    full_sidecar_path = fig.parent / f"{fig.name}{sidecar_suffix}"
    caller = _get_caller_info(skip_frames=1)

    source_data = {}
    try:
        source_path = Path(data_source)
        if source_path.suffix.lower() == ".jsonl":
            source_path, _ = _resolve_manifest_paths(str(source_path))
        with open(source_path, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        if isinstance(loaded_data, Mapping):
            source_data = loaded_data
    except (OSError, ValueError, UnicodeError):
        pass

    source_solver_data = dict(source_data)
    source_metadata = source_data.get("run_metadata")
    if isinstance(source_metadata, Mapping):
        for field in ("solver", "solver_name", "solver_parameters", "parameters"):
            if field not in source_solver_data and field in source_metadata:
                source_solver_data[field] = source_metadata[field]

    solver = _resolve_solver_provenance(
        solver_name,
        solver_parameters,
        data=source_solver_data,
        existing_manifest=source_data,
    )
    sidecar_data = {
        "figure_file": str(fig).replace("\\", "/"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_source": {
            "path": str(data_source).replace("\\", "/"),
            "sha256": _compute_sha256(data_source),
        },
        "data_slices_columns": columns_used,
        "generating_code": {
            "source_file": caller["source_file"],
            "source_function": caller["source_function"],
            "line_number": caller["line_number"],
        },
        **solver,
    }

    _atomic_write_json(full_sidecar_path, sidecar_data)
    if sidecar_path != full_sidecar_path:
        _atomic_write_json(sidecar_path, sidecar_data)

    return str(sidecar_path)


class MetricsLogger:
    """Lightweight instance wrapper around the module-level logging functions."""

    def __init__(
        self,
        metrics_path=str(DEFAULT_METRICS_PATH),
        solver_name=None,
        solver_parameters=None,
        **_kwargs,
    ):
        self.metrics_path = metrics_path
        self.solver_name = solver_name
        self.solver_parameters = solver_parameters

    def log_metric(self, key, value, step_id=None, **kwargs):
        kwargs.setdefault("metrics_path", self.metrics_path)
        kwargs.setdefault("solver_name", self.solver_name)
        kwargs.setdefault("solver_parameters", self.solver_parameters)
        return log_metric(key, value, step_id=step_id, **kwargs)

    def log_metrics(self, metrics=None, *, step_id=None, **kwargs):
        kwargs.setdefault("metrics_path", self.metrics_path)
        kwargs.setdefault("solver_name", self.solver_name)
        kwargs.setdefault("solver_parameters", self.solver_parameters)
        return log_metrics(metrics, step_id=step_id, **kwargs)

    def log(self, *args, **kwargs):
        return self.log_metrics(*args, **kwargs)

    def record(self, *args, **kwargs):
        return self.log_metrics(*args, **kwargs)

    def log_step(self, name, data, **kwargs):
        kwargs.setdefault("metrics_path", self.metrics_path)
        kwargs.setdefault("solver_name", self.solver_name)
        kwargs.setdefault("solver_parameters", self.solver_parameters)
        return log_step(name, data, **kwargs)

    def set_solver_provenance(
        self, solver_name=None, solver_parameters=None, **kwargs
    ):
        name = self.solver_name if solver_name is None else solver_name
        parameters = (
            self.solver_parameters
            if solver_parameters is None
            else solver_parameters
        )
        kwargs.setdefault("metrics_path", self.metrics_path)
        manifest = set_solver_provenance(name, parameters, **kwargs)
        self.solver_name = name
        self.solver_parameters = dict(parameters) if parameters is not None else {}
        return manifest

    def export_macros(self, output_path=str(DEFAULT_MACROS_PATH), **kwargs):
        kwargs.setdefault("metrics_path", self.metrics_path)
        return export_macros(output_path=output_path, **kwargs)

    def save_plot_provenance(
        self,
        figure_path,
        data_source,
        columns_used,
        sidecar_suffix=".provenance.json",
        **kwargs,
    ):
        kwargs.setdefault("solver_name", self.solver_name)
        kwargs.setdefault("solver_parameters", self.solver_parameters)
        return save_plot_provenance(
            figure_path,
            data_source,
            columns_used,
            sidecar_suffix=sidecar_suffix,
            **kwargs,
        )


def generate_manuscript_map(
    manuscript_path: str,
    output_map_path: str = str(DEFAULT_MAP_PATH),
    metrics_path: str = str(DEFAULT_METRICS_PATH),
    figures_dir: str = "figures",
    **_ignored_kwargs: Any,
) -> Dict[str, Any]:
    """Scans manuscript for macro/figure citations and builds manuscript_provenance_map.json."""
    if _ignored_kwargs.get("output_path") is not None:
        output_map_path = _ignored_kwargs["output_path"]
    if _ignored_kwargs.get("figure_dir") is not None:
        figures_dir = _ignored_kwargs["figure_dir"]

    ms_path = Path(manuscript_path)
    if not ms_path.exists():
        raise FileNotFoundError(f"Manuscript not found at {manuscript_path}")

    with open(ms_path, "r", encoding="utf-8") as f:
        text = f.read()

    metrics_manifest_path, _ = _resolve_manifest_paths(metrics_path)
    metrics_data = {}
    if metrics_manifest_path.exists():
        metrics_data = _read_json_with_retry(metrics_manifest_path).get("metrics", {})

    ledger: Dict[str, Any] = {"macros": {}, "figures": {}, "audit_status": "PASS"}

    metric_macro_to_key = {_sanitize_macro_name(k): k for k in metrics_data.keys()}
    macro_matches = set(re.findall(r"\\([a-zA-Z]+)", text))
    results_metric_prefixes = (
        "Model",
        "SweetSpot",
        "Levitation",
        "Asymmetric",
        "Frontier",
        "Scaling",
        "AtomicCqed",
        "ClutchPilot",
        "SolverComparison",
    )

    for macro_name, metric_key in sorted(metric_macro_to_key.items()):
        record = metrics_data[metric_key]
        ledger["macros"][f"\\{macro_name}"] = {
            "status": "RESOLVED" if macro_name in macro_matches else "UNUSED_MACRO",
            "value": record.get("value"),
            "source_metric_key": metric_key,
            "source_file": record.get("source_file"),
            "source_function": record.get("source_function"),
            "intermediate_step_id": record.get("step_id"),
            "provenance_artifact": str(metrics_manifest_path).replace("\\", "/"),
        }

    for macro_name in sorted(macro_matches):
        if (
            macro_name not in metric_macro_to_key
            and macro_name.startswith(results_metric_prefixes)
        ):
            ledger["macros"][f"\\{macro_name}"] = {
                "status": "UNRESOLVED_MACRO",
                "note": "Macro referenced in text but not found in provenance_metrics.json",
            }
            ledger["audit_status"] = "FAIL"

    fig_dir = Path(figures_dir)
    if fig_dir.exists():
        for sidecar in fig_dir.glob("*.provenance.json"):
            base_fig_name = sidecar.name.removesuffix(".provenance.json")
            if base_fig_name in text:
                try:
                    with open(sidecar, "r", encoding="utf-8") as sf:
                        s_data = json.load(sf)
                    ledger["figures"][base_fig_name] = {
                        "figure_file": s_data.get("figure_file"),
                        "sidecar_artifact": str(sidecar).replace("\\", "/"),
                        "source_data": s_data.get("input_source", {}).get("path"),
                        "source_sha256": s_data.get("input_source", {}).get("sha256"),
                        "generating_function": s_data.get("generating_code", {}).get("source_function"),
                    }
                except Exception:
                    ledger["figures"][base_fig_name] = {"status": "INVALID_SIDECAR"}
                    ledger["audit_status"] = "FAIL"

    out_path = Path(output_map_path)
    _atomic_write_json(out_path, ledger)

    return ledger


def init_workspace(target_dir: str = "utils") -> str:
    """Scaffolds metrics_logger.py into the specified target directory of the active project."""
    target_path = Path(target_dir) / "metrics_logger.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    this_file = Path(__file__).resolve()
    shutil.copy2(this_file, target_path)
    print(f"[METRICS-LOGGER] Installed local copy to {target_path}")
    return str(target_path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        target = sys.argv[2] if len(sys.argv) > 2 else "utils"
        init_workspace(target)
    else:
        print("Testing metrics_logger provenance harness...")
        log_step("test_reduction", {"dim": 128, "norm": 1.042})
        log_metric("accuracy_top1", 94.25, step_id="eval_test_split")
        log_metric("f1_score", 0.912, step_id="eval_test_split")
        export_macros()
        save_plot_provenance("figures/demo_loss.png", "results/provenance_metrics.json", ["accuracy_top1"])
        print("Verification complete. LaTeX macros and provenance sidecar generated successfully.")
