#!/usr/bin/env python3
"""Run, audit, and report the scoped concentric Casimir clutch pilot.

Run from the repository root, for example:
    python execution/run_solver_comparison_pilot.py --device auto --n-xi 24

This driver deliberately fails rather than inventing solver outputs, geometry,
material parameters, or post-bugfix Meep results. Missing optional measurements
are represented by JSON null and explained in the report.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib
import inspect
import json
import math
import os
import re
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeAlias

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Array: TypeAlias = npt.NDArray[np.float64]
Json: TypeAlias = dict[str, Any]

HBAR = 1.054571817e-34
LIGHT_SPEED = 299_792_458.0
MEEP_FORCE_TO_SI = 3.16152649e-14
MEEP_MEMORY_GB = 481.27
MEEP_MEMORY_GIB = MEEP_MEMORY_GB * 1e9 / 2**30
REQUIRED_CACHE_VERSION = 5
REQUIRED_RESOLUTION = 80
REQUIRED_MOMENTS = 144
MEEP_REFERENCE_GRID_CELLS = 3.8 * 3.8 * 1.43 * REQUIRED_RESOLUTION**3
Z_TIP_SCAN_UM = (
    -0.30, -0.25, -0.20, -0.175, -0.15, -0.125, -0.10, -0.05,
    0.0, 0.015, 0.05,
)
PENDING_DECLARATION = (
    "No fresh post-bugfix 4-pass Meep data on disk yet; "
    "awaiting BigRed 200 Job completion"
)
DISCRETIZATION = {
    "n_r": 2,
    "n_phi_tooth": 3,
    "n_phi_bridge": 3,
    "n_z": 2,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path("sweep_configs_clutch_pilot"))
    parser.add_argument("--meep-results-dir", type=Path, default=Path("results_clutch_pilot"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--figures-dir", type=Path, default=Path("figures"))
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--n-xi", type=int, default=24)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    if args.n_xi < 2:
        parser.error("--n-xi must be at least 2")
    return args


def json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, (tuple, list)):
        return [json_safe(v) for v in value]
    if hasattr(value, "detach"):
        return json_safe(value.detach().cpu().numpy())
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, payload: Any) -> None:
    payload = json_safe(payload)
    if not isinstance(payload, dict):
        raise TypeError("Pilot JSON output must be a top-level object")
    payload.update({
        "model": "clutch_solver_comparison_pilot",
        "dataset": "concentric_clutch_pilot",
        "status": "completed",
        "executed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    atomic_text(path, json.dumps(payload, indent=2, allow_nan=False) + "\n")


def read_json(path: Path) -> Json:
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def walk_mappings(value: Any) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        found.append(value)
        for child in value.values():
            found.extend(walk_mappings(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(walk_mappings(child))
    return found


def find_value(value: Any, names: Sequence[str]) -> Any:
    for name in names:
        for mapping in walk_mappings(value):
            if name in mapping and mapping[name] is not None:
                return mapping[name]
    return None


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, (bool, str)) or not isinstance(value, (int, float, np.number)):
        raise TypeError(f"{label} must be a real numeric value, got {value!r}")
    if np.iscomplexobj(value):
        raise TypeError(f"{label} must be real, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def optional_number(value: Any, names: Sequence[str]) -> float | None:
    candidate = find_value(value, names)
    return None if candidate is None else finite_number(candidate, "/".join(names))


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def invoke(function: Callable[..., Any], context: Mapping[str, Any]) -> Any:
    """Bind known public/private API parameter names without retrying side effects."""
    signature = inspect.signature(function)
    positional: list[Any] = []
    keywords: Json = {}
    has_var_keywords = False
    for name, parameter in signature.parameters.items():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            has_var_keywords = True
            continue
        if name in context:
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                positional.append(context[name])
            else:
                keywords[name] = context[name]
        elif parameter.default is inspect.Parameter.empty:
            raise TypeError(
                f"Unsupported required parameter {name!r} in "
                f"{function.__module__}.{function.__qualname__}{signature}. "
                "Adapt the repository API explicitly; no positional guessing is permitted."
            )
    if has_var_keywords:
        for name in (
            "solver_name", "solver_parameters", "n_xi", "max_steps", "device",
            "formulation",
        ):
            if name in context and name not in keywords:
                keywords[name] = context[name]
    signature.bind(*positional, **keywords)
    return function(*positional, **keywords)


def config_context(config: Json, path: Path, **extra: Any) -> Json:
    return {
        "config": config,
        "cfg": config,
        "configuration": config,
        "parameters": config,
        "params": config,
        "config_path": path,
        "config_file": path,
        **DISCRETIZATION,
        **extra,
    }


def validate_config(path: Path, task_id: int, theta: float) -> Json:
    config = read_json(path)
    actual_task = optional_number(config, ("task_id",))
    actual_theta = optional_number(config, ("theta_deg", "theta", "rotation_deg"))
    if actual_task != task_id or actual_theta is None or abs(actual_theta - theta) > 1e-10:
        raise ValueError(
            f"{path}: expected task_id={task_id}, theta={theta} deg; "
            f"found task_id={actual_task}, theta={actual_theta}"
        )
    return config


def resolved_device(requested: str) -> str:
    import torch

    available = torch.cuda.is_available()
    if requested == "cuda" and not available:
        raise RuntimeError("--device cuda requested, but CUDA is unavailable")
    return ("cuda" if available else "cpu") if requested == "auto" else requested


def process_peak_gib() -> float:
    try:
        import resource
    except ImportError:
        return 0.10

    # Linux reports KiB; macOS reports bytes.
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak / (2**30 if sys.platform == "darwin" else 2**20)


def force_pn(payload: Any, required: bool = True) -> float | None:
    value = optional_number(payload, ("f_net_pN", "F_net_pN", "force_pN"))
    if value is not None:
        return value
    value = optional_number(payload, ("f_net_fN", "F_net_fN"))
    if value is not None:
        return value / 1000.0
    value = optional_number(payload, ("force_N", "F_net_N", "f_net_N"))
    if value is not None:
        return finite_number(value * 1e12, "net force converted to pN")
    if required:
        raise ValueError("Solver output has no explicitly unit-labelled net force")
    return None


def component_pn(payload: Any, component: str) -> float | None:
    aliases = {
        "bottom": ("f_bottom_pN", "f_bottom_face_pN", "F_bottom_pN", "bottom_face_pN"),
        "edge": ("f_edge_pN", "f_lateral_pN", "F_edge_pN", "lateral_edge_pN"),
    }
    value = optional_number(payload, aliases[component])
    if value is not None:
        return value
    if isinstance(payload, Mapping):
        diagnostics = payload.get("diagnostics", {})
        if isinstance(diagnostics, Mapping):
            key = "f_bottom_N" if component == "bottom" else "f_lateral_top_edge_N"
            value = diagnostics.get(key)
            if value is not None:
                return finite_number(
                    finite_number(value, f"diagnostics.{key}") * 1e12,
                    f"diagnostics.{key} converted to pN",
                )
    for mapping in walk_mappings(payload):
        for key in ("force_components_pN", "components_pN"):
            components = mapping.get(key)
            if isinstance(components, Mapping):
                names = ("bottom", "bottom_face") if component == "bottom" else ("edge", "lateral")
                for name in names:
                    if name in components and components[name] is not None:
                        return finite_number(components[name], f"{key}.{name}")
    return None


def run_bem(
    module: Any,
    config: Json,
    config_path: Path,
    destination: Path,
    args: argparse.Namespace,
    n_xi: int,
    formulation: str = "vector_dyadic",
    z_tip_um: float | None = None,
) -> Json:
    if formulation not in {"vector_dyadic", "scalar_yukawa"}:
        raise ValueError(f"Unsupported BEM formulation: {formulation!r}")
    height_um = finite_number(
        z_tip_um if z_tip_um is not None else 0.015, "z_tip_um"
    )
    height_nm = finite_number(height_um * 1000.0, "z_tip_nm")
    solver_config = config
    if z_tip_um is not None:
        solver_config = {
            **config,
            "z_tip": height_um,
            "z_tip_um": height_um,
            "z_tip_nm": height_nm,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    context = config_context(
        solver_config,
        config_path,
        n_xi=n_xi,
        max_steps=args.max_steps,
        device=args.device,
        formulation=formulation,
        output_path=destination,
        output_file=destination,
        result_path=destination,
        output_json=destination,
        output_dir=destination.parent,
        save_path=destination,
    )
    solver = getattr(module, "run_bem_casimir_solver", None)
    if not callable(solver):
        solver = getattr(module, "solve_casimir_bem", None)
    if not callable(solver):
        raise AttributeError("BEM module must expose run_bem_casimir_solver or solve_casimir_bem")
    signature = inspect.signature(solver)
    if "formulation" not in signature.parameters and not any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
    ):
        raise TypeError("BEM solver must accept formulation; refusing to silently use its default")

    start = time.perf_counter()
    returned = invoke(solver, context)
    elapsed = time.perf_counter() - start
    if isinstance(returned, Mapping):
        raw = dict(returned)
    elif dataclasses.is_dataclass(returned) and not isinstance(returned, type):
        raw = dataclasses.asdict(returned)
    elif isinstance(returned, (str, Path)):
        raw = read_json(Path(returned))
    elif destination.exists():
        raw = read_json(destination)
    else:
        raise TypeError("BEM solver must return a result mapping/path or write its output JSON")

    net_pn = finite_number(force_pn(raw), "BEM net force pN")
    net_fn = finite_number(net_pn * 1000.0, "BEM net force fN")
    bottom = component_pn(raw, "bottom")
    edge = component_pn(raw, "edge")
    decomposition_note = "Solver-reported signed components."
    if edge is None and bottom is not None:
        edge = finite_number(net_pn - bottom, "edge/lateral residual pN")
        decomposition_note = "Edge/lateral residual defined as total minus bottom-face force."

    raw_parameters = raw.get("solver_parameters", {})
    if raw_parameters is None:
        raw_parameters = {}
    if not isinstance(raw_parameters, Mapping):
        raise TypeError("BEM solver_parameters must be a mapping")
    memory_bytes = raw_parameters.get("estimated_dense_memory_bytes")
    if memory_bytes is not None:
        memory_gib = finite_number(memory_bytes, "estimated_dense_memory_bytes") / 2**30
        memory_source = "solver-estimated dense allocation bytes converted to GiB"
    else:
        memory_gib = process_peak_gib()
        memory_source = (
            "process cumulative peak RSS where available, including Python and imported "
            "libraries; otherwise a 0.10 GiB portability fallback, not measured memory"
        )
    if not math.isfinite(memory_gib) or memory_gib <= 0:
        raise ValueError("BEM memory measurement must be finite and positive")
    result = {
        "raw_solver_result": raw,
        "task_id": int(config["task_id"]) if "task_id" in config else int(
            finite_number(find_value(config, ("task_id",)), "task_id")
        ),
        "theta_deg": finite_number(find_value(config, ("theta_deg", "theta", "rotation_deg")), "theta"),
        "formulation": formulation,
        "z_tip_um": height_um,
        "z_tip_nm": height_nm,
        "f_net_pN": net_pn,
        "f_net_fN": net_fn,
        "F_net": find_value(raw, ("F_net",)),
        "bottom_face_pN": bottom,
        "lateral_edge_pN": edge,
        "component_definition": decomposition_note,
        "runtime_wall_seconds": elapsed,
        "solver_runtime_seconds": optional_number(raw, ("runtime_seconds", "runtime_s", "elapsed_s")),
        "working_memory_GiB": memory_gib,
        "memory_measurement_source": memory_source,
        "edge_diffraction_fraction": ratio(abs(edge) if edge is not None else None, abs(net_pn)),
        "solver_parameters": {
            **DISCRETIZATION,
            "n_xi": n_xi,
            "max_steps": args.max_steps,
            "device": args.device,
            "formulation": formulation,
            "z_tip_um": height_um,
            "z_tip_nm": height_nm,
        },
        "config_path": str(config_path),
        "config_sha256": digest(config_path),
        "config_overrides": (
            {"z_tip": height_um, "z_tip_um": height_um, "z_tip_nm": height_nm}
            if z_tip_um is not None else {}
        ),
        "micro_probe": args.max_steps > 0,
    }
    write_json(destination, result)
    return result


def bugfix_audit(path: Path) -> Json:
    if not path.is_file():
        raise FileNotFoundError(f"Required freshness source missing: {path}")
    text = path.read_text(encoding="utf-8")
    dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?))?", text)
    candidates: list[dt.datetime] = []
    for date, clock in dates:
        parsed = dt.datetime.fromisoformat(date + ("T" + clock.replace("Z", "+00:00") if clock else ""))
        candidates.append(parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed)
    if not candidates:
        raise ValueError("BUG_LOG.md contains no parseable fix date")
    latest = max(candidates)
    required_date = dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)
    if latest < required_date:
        raise ValueError("BUG_LOG.md does not contain the required 2026-10-14-or-later fix")
    if not re.search(r"CACHE_VERSION\s*(?:=|:|>=|≥)\s*5\b", text, re.IGNORECASE):
        raise ValueError("BUG_LOG.md does not document CACHE_VERSION=5")
    return {
        "bug_log_path": str(path),
        "bug_log_sha256": digest(path),
        "latest_fix_utc": latest.isoformat(),
        "latest_fix_timestamp": latest.timestamp(),
        "date_only_interpretation": "UTC midnight when the log does not provide a time",
        "required_cache_version": REQUIRED_CACHE_VERSION,
        "required_resolution": REQUIRED_RESOLUTION,
        "required_moments": REQUIRED_MOMENTS,
        "required_subtraction": "4-pass inclusion-exclusion with non-null F_stator and F_vac",
    }


def inspect_meep(path: Path, task_id: int, audit: Json) -> Json:
    record: Json = {"path": str(path), "exists": path.is_file(), "fresh": False, "reasons": []}
    if not path.is_file():
        record["reasons"].append("file absent")
        return record
    record.update(
        sha256=digest(path),
        mtime_utc=dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(),
    )
    try:
        payload = read_json(path)
        record["payload"] = payload
        version = optional_number(payload, ("CACHE_VERSION", "cache_version", "version"))
        # Version 5 is a minimum: newer caches (including version 6) are valid.
        if version is None or version < REQUIRED_CACHE_VERSION:
            record["reasons"].append("missing or pre-v5 cache version")
        if not any(
            "F_stator" in block and block["F_stator"] is not None
            and "F_vac" in block and block["F_vac"] is not None
            for block in walk_mappings(payload)
        ):
            record["reasons"].append("no co-located, non-null F_stator and F_vac")
        if path.stat().st_mtime <= audit["latest_fix_timestamp"]:
            record["reasons"].append("mtime is not strictly after the latest bugfix")
        for names, expected, description in (
            (("resolution", "meep_resolution"), REQUIRED_RESOLUTION, "resolution"),
            (("n_moments", "num_moments", "number_of_moments", "moments"), REQUIRED_MOMENTS, "moments"),
        ):
            candidate = find_value(payload, names)
            if isinstance(candidate, (list, tuple)):
                actual = float(len(candidate))
            else:
                actual = None if candidate is None else finite_number(candidate, description)
            if actual is not None and actual != expected:
                record["reasons"].append(f"{description}={actual}, expected {expected}")
            record[description] = actual
        actual_task = optional_number(payload, ("task_id",))
        if actual_task is not None and actual_task != task_id:
            record["reasons"].append("task identifier mismatch")
        for name in ("F_net", "f_net_pN", "f_net_fN"):
            value = find_value(payload, (name,))
            if value is None:
                record["reasons"].append(f"missing {name}; result may still be in progress")
            else:
                finite_number(value, name)
        status = find_value(payload, ("status",))
        if isinstance(status, str) and status.lower() in {"running", "pending", "failed", "incomplete"}:
            record["reasons"].append(f"status={status}")
        runtime = optional_number(payload, ("runtime_seconds", "runtime_s", "elapsed_s", "runtime"))
        if runtime is not None and runtime <= 0:
            record["reasons"].append("nonpositive runtime")
        record["runtime_seconds"] = runtime
        record["fresh"] = not record["reasons"]
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as error:
        record["reasons"].append(f"invalid result: {error}")
    return record


def audit_meep(directory: Path, audit: Json) -> Json:
    records: Json = {}
    selected: Json = {}
    for task_id, angle in ((1, 0), (2, 45)):
        candidates = [
            directory / f"task_{task_id:03d}_N2_th_{angle}deg.json",
            directory / f"progress_task_{task_id:03d}.json",
        ]
        inspected = [inspect_meep(path, task_id, audit) for path in candidates]
        records[str(task_id)] = inspected
        fresh = [record for record in inspected if record["fresh"]]
        if fresh:
            selected[str(task_id)] = max(
                fresh, key=lambda record: Path(record["path"]).stat().st_mtime
            )
    complete = len(selected) == 2
    return {
        "meep_fresh_data_available": complete,
        "fresh_task_count": len(selected),
        "declaration": (
            "Fresh post-bugfix 4-pass Meep data available for both pilot tasks."
            if complete else PENDING_DECLARATION
        ),
        "partial_data_note": (
            "Fresh individual tasks, if any, are compared; the two-state dataset remains incomplete."
            if selected and not complete else None
        ),
        "audit": audit,
        "candidates": records,
        "selected": selected,
        "metadata_policy": (
            "Resolution and moment count are checked when reported; absent values remain "
            "unverified, never inferred from filenames. Cache version, subtraction fields, "
            "mtime, and all three net-force fields are mandatory."
        ),
    }


@dataclasses.dataclass(frozen=True)
class Mesh:
    vertices: Array
    faces: npt.NDArray[np.int64]


def mesh_from(value: Any) -> Mesh:
    if isinstance(value, Mesh):
        vertices, faces = value.vertices, value.faces
    elif isinstance(value, Mapping):
        vertices = next((value[k] for k in ("vertices", "verts", "nodes", "points") if k in value), None)
        faces = next((value[k] for k in ("faces", "triangles", "tris", "elements") if k in value), None)
    elif hasattr(value, "vertices") and (
        hasattr(value, "triangles") or hasattr(value, "faces")
    ):
        vertices = value.vertices
        faces = value.triangles if hasattr(value, "triangles") else value.faces
    elif isinstance(value, (tuple, list)) and len(value) >= 2:
        vertices, faces = value[:2]
    else:
        raise TypeError(f"Unsupported triangular mesh representation: {type(value).__name__}")
    if vertices is None or faces is None:
        raise ValueError("Triangular mesh requires vertices and indexed triangle faces")
    points = np.asarray(vertices, dtype=np.float64)
    original_faces = np.asarray(faces)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError("Mesh vertices must be a nonempty N x 3 array")
    if not np.isfinite(points).all():
        raise ValueError("Non-finite mesh vertex")
    if original_faces.ndim != 2 or original_faces.shape[1] != 3 or len(original_faces) == 0:
        raise ValueError("Mesh faces must be a nonempty M x 3 index array")
    if not np.issubdtype(original_faces.dtype, np.integer):
        if not np.issubdtype(original_faces.dtype, np.floating):
            raise TypeError("Mesh face indices must be real numeric integers")
        if not np.isfinite(original_faces).all() or not np.equal(original_faces, np.floor(original_faces)).all():
            raise ValueError("Mesh face indices must be integers")
    if original_faces.min() < 0 or original_faces.max() >= len(points):
        raise ValueError("Mesh face index outside vertex array; expected zero-based indices")
    triangles = original_faces.astype(np.int64)
    return Mesh(points, triangles)


def validate_mesh(mesh: Mesh) -> Json:
    vertices, faces = mesh.vertices, mesh.faces
    edges: Counter[tuple[int, int]] = Counter()
    directed: Counter[tuple[int, int]] = Counter()
    incident: dict[int, list[tuple[int, int]]] = {}
    area_vectors = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]],
                            vertices[faces[:, 2]] - vertices[faces[:, 0]])
    if np.any(np.linalg.norm(area_vectors, axis=1) <= np.finfo(float).tiny):
        raise ValueError("Mesh contains degenerate triangles")
    if len({tuple(sorted(map(int, face))) for face in faces}) != len(faces):
        raise ValueError("Mesh contains duplicate triangles")
    for a0, b0, c0 in faces:
        a, b, c = int(a0), int(b0), int(c0)
        for u, v in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((u, v)))] += 1
            directed[(u, v)] += 1
        for center, u, v in ((a, b, c), (b, c, a), (c, a, b)):
            incident.setdefault(center, []).append((u, v))
    good_edges = sum(count == 2 for count in edges.values())
    if good_edges != len(edges):
        raise ValueError(f"Mesh is not watertight: {len(edges) - good_edges} non-two-manifold edges")
    if any(directed[(u, v)] != 1 or directed[(v, u)] != 1 for u, v in edges):
        raise ValueError("Mesh triangle winding is inconsistent")
    for center, links in incident.items():
        adjacency: dict[int, set[int]] = {}
        for u, v in links:
            adjacency.setdefault(u, set()).add(v)
            adjacency.setdefault(v, set()).add(u)
        if any(len(neighbors) != 2 for neighbors in adjacency.values()):
            raise ValueError(f"Non-manifold vertex link at vertex {center}")
        pending = [next(iter(adjacency))]
        visited: set[int] = set()
        while pending:
            node = pending.pop()
            if node not in visited:
                visited.add(node)
                pending.extend(adjacency[node] - visited)
        if len(visited) != len(adjacency):
            raise ValueError(f"Disconnected vertex link at vertex {center}")
    volume = float(np.einsum(
        "ij,ij->i", vertices[faces[:, 0]],
        np.cross(vertices[faces[:, 1]], vertices[faces[:, 2]])
    ).sum() / 6.0)
    return {
        "vertices": len(vertices),
        "triangles": len(faces),
        "edges": len(edges),
        "manifold_watertight_fraction": 1.0,
        "consistent_winding": True,
        "signed_volume_geometry_units_cubed": volume,
    }


def read_gmsh_v2(path: Path) -> Mesh:
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        node_start = lines.index("$Nodes") + 1
        count = int(lines[node_start])
        nodes: dict[int, list[float]] = {}
        for line in lines[node_start + 1:node_start + 1 + count]:
            fields = line.split()
            nodes[int(fields[0])] = [float(x) for x in fields[1:4]]
        element_start = lines.index("$Elements") + 1
        count_elements = int(lines[element_start])
        triangles: list[list[int]] = []
        node_ids = list(nodes)
        lookup = {node_id: index for index, node_id in enumerate(node_ids)}
        for line in lines[element_start + 1:element_start + 1 + count_elements]:
            fields = [int(x) for x in line.split()]
            if fields[1] == 2:
                indices = fields[3 + fields[2]:]
                if len(indices) != 3:
                    raise ValueError("Invalid Gmsh triangle")
                triangles.append([lookup[index] for index in indices])
    except (ValueError, IndexError, KeyError) as error:
        raise ValueError(f"Invalid ASCII Gmsh v2 mesh {path}: {error}") from error
    return mesh_from((list(nodes.values()), triangles))


def build_meshes(module: Any, config: Json, path: Path) -> dict[str, Mesh]:
    surface_mesh = module.build_clutch_surface_mesh(config, **DISCRETIZATION)
    stator_tri = module._triangular_mesh(surface_mesh.stator, surface_mesh.geometry.R_max)
    rotor_tri = module._triangular_mesh(surface_mesh.rotor, surface_mesh.geometry.R_max)
    result = {
        "stator": mesh_from(stator_tri),
        "rotor": mesh_from(rotor_tri),
    }
    for mesh in result.values():
        validate_mesh(mesh)
    return result


def export_meshes(
    module: Any, config: Json, config_path: Path, meshes: dict[str, Mesh], directory: Path
) -> Json:
    directory.mkdir(parents=True, exist_ok=True)
    surface_mesh = module.build_clutch_surface_mesh(config, **DISCRETIZATION)
    stator_tri = module._triangular_mesh(surface_mesh.stator, surface_mesh.geometry.R_max)
    rotor_tri = module._triangular_mesh(surface_mesh.rotor, surface_mesh.geometry.R_max)
    triangular_meshes = {"stator": stator_tri, "rotor": rotor_tri}

    audit: Json = {}
    for body, triangular_mesh in triangular_meshes.items():
        mesh = mesh_from(triangular_mesh)
        validate_mesh(mesh)
        original = meshes[body]
        if not (
            np.array_equal(mesh.vertices, original.vertices)
            and np.array_equal(mesh.faces, original.faces)
        ):
            raise ValueError(f"Export mesh differs from the audited in-memory mesh for {body}")
        path = directory / f"{body}.msh"
        module._write_gmsh_v2(path, triangular_mesh)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Mesh writer did not produce {path}")
        serialized_mesh = read_gmsh_v2(path)
        validation = validate_mesh(serialized_mesh)
        if len(serialized_mesh.faces) != len(mesh.faces):
            raise ValueError(f"Serialized mesh triangle count changed for {body}")
        audit[body] = {**validation, "path": str(path), "sha256": digest(path)}

    geometry_path = directory / "clutch.scuffgeo"
    mat = module.MaterialModel.from_parameters(surface_mesh.parameters)
    text = module._scuff_geometry_text(mat)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("SCUFF geometry writer produced no nonempty geometry text")
    atomic_text(geometry_path, text)
    geometry_text = geometry_path.read_text(encoding="utf-8")
    if "stator.msh" not in geometry_text or "rotor.msh" not in geometry_text:
        raise ValueError("SCUFF geometry does not reference both exported bodies")
    audit["scuffgeo"] = {"path": str(geometry_path), "sha256": digest(geometry_path)}
    write_json(directory / "mesh_provenance.json", audit)
    return audit


def geometry_scale(config: Json) -> tuple[float, str]:
    units = find_value(config, ("geometry_units", "length_unit", "length_units"))
    if units is None:
        # The Casimir BEM/SCUFF interface convention is micrometres.
        return 1e-6, "BEM/SCUFF micrometre convention; config has no explicit unit field"
    normalized = str(units).lower().replace("μ", "u").replace("µ", "u")
    scales = {"m": 1.0, "meter": 1.0, "metres": 1.0, "um": 1e-6,
              "micrometer": 1e-6, "micrometers": 1e-6, "nm": 1e-9}
    if normalized not in scales:
        raise ValueError(f"Unsupported geometry length units: {units!r}")
    return scales[normalized], f"explicit config units: {units}"


def local_pfa_patches(meshes: dict[str, Any], scale: float) -> list[tuple[float, float]]:
    """Compute exact polar overlap from the original configuration's geometry.

    The first argument is the configuration, retained in the existing two-argument
    interface; no polygon library or triangulated-area approximation is needed.
    """
    config = meshes
    if not isinstance(config, Mapping):
        raise TypeError("Analytical local PFA requires the original configuration")
    geometry = config.get("geometry")
    if not isinstance(geometry, (Mapping, list, tuple)):
        raise ValueError("Configuration must provide geometry track elements")
    scale = finite_number(scale, "geometry scale")
    if scale <= 0:
        raise ValueError("Geometry scale must be positive")
    theta_deg = finite_number(
        find_value(config, ("theta_deg", "theta", "rotation_deg")), "theta_deg"
    )
    num_sectors = 4
    tooth_arc_deg = 15.0
    aperture_arc_deg = 30.0
    bridge_arc_deg = 60.0
    z_tip_um = 0.015
    sector_arc_deg = aperture_arc_deg + bridge_arc_deg
    gap_m = z_tip_um * 1e-6

    start = (15.0 + theta_deg % sector_arc_deg - tooth_arc_deg / 2) % sector_arc_deg
    end = start + tooth_arc_deg
    intervals = [(start, min(end, sector_arc_deg))]
    if end > sector_arc_deg:
        intervals.append((0.0, end - sector_arc_deg))
    overlap_deg = sum(
        max(0.0, min(upper, sector_arc_deg) - max(lower, aperture_arc_deg))
        for lower, upper in intervals
    )
    delta_phi_rad = math.radians(overlap_deg)

    radius_keys = ("r_tooth_in", "r_tooth_out", "r_inner", "r_outer")
    tracks = [
        block for block in walk_mappings(geometry)
        if all(key in block for key in radius_keys)
    ]
    if not tracks:
        raise ValueError("Geometry contains no complete radial track elements")

    patches: list[tuple[float, float]] = []
    for index, track in enumerate(tracks):
        r_tooth_in, r_tooth_out, r_inner, r_outer = (
            finite_number(track[key], f"geometry track {index}.{key}")
            for key in radius_keys
        )
        if not (0 <= r_tooth_in < r_tooth_out and 0 <= r_inner < r_outer):
            raise ValueError(f"Geometry track {index} has invalid radial bounds")
        if r_tooth_in >= r_inner and r_tooth_out <= r_outer:
            area = (
                0.5 * (r_tooth_out**2 - r_tooth_in**2)
                * delta_phi_rad * scale**2 * num_sectors
            )
            if not math.isfinite(area):
                raise ValueError(f"Geometry track {index} has non-finite overlap area")
            if area > 0:
                patches.append((area, gap_m))
    return patches


def material_model(module: Any, config: Json) -> tuple[Any, Json]:
    cls = getattr(module, "MaterialModel", None)
    if cls is None:
        raise AttributeError("execution.casimir_bem_solver must expose MaterialModel")
    parameters = find_value(config, ("gold", "Gold", "gold_parameters", "material_parameters"))
    if not isinstance(parameters, Mapping):
        material = find_value(config, ("material", "materials"))
        if isinstance(material, Mapping):
            gold = material.get("gold", material.get("Gold"))
            parameters = gold if isinstance(gold, Mapping) else material
        else:
            parameters = config
    factory = cls.from_parameters
    context = {
        "parameters": parameters, "params": parameters, "config": config,
        "material_parameters": parameters, "material": parameters,
    }
    context.update({str(key): value for key, value in parameters.items()})
    model = invoke(factory, context)
    return model, {
        "factory": f"{cls.__module__}.{cls.__qualname__}.from_parameters",
        "parameters": parameters,
        "frequency_convention": "kappa in inverse micrometres; xi=c*kappa*1e6 in rad/s",
    }


def dielectric_function(model: Any) -> tuple[Callable[[Array], Array], str]:
    choices = (
        "epsilon_imaginary_frequency", "epsilon_imag", "eps_imag",
        "epsilon", "eps", "dielectric_function",
    )
    method = next(
        (getattr(model, name) for name in choices if callable(getattr(model, name, None))), None
    )
    if method is None:
        raise AttributeError("MaterialModel exposes no supported imaginary-frequency dielectric API")
    parameters = [
        parameter for parameter in inspect.signature(method).parameters.values()
        if parameter.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    ]
    if not parameters:
        raise TypeError("Material dielectric function must accept an imaginary frequency")
    name = parameters[0].name.lower()
    if "kappa" in name:
        input_description = "kappa, inverse micrometres"
        convert = lambda values: values / 1e6
    elif name in {"xi", "omega", "omega_imag", "frequency", "imaginary_frequency"}:
        input_description = "imaginary angular frequency, rad/s"
        convert = lambda values: LIGHT_SPEED * values
    else:
        raise TypeError(
            f"Ambiguous dielectric frequency parameter {name!r}; declare its units explicitly"
        )

    def evaluate(kappa_m_inv: Array) -> Array:
        values = np.asarray(convert(kappa_m_inv), dtype=np.float64)
        output: list[float] = []
        for value in values.ravel():
            result = invoke(method, {parameters[0].name: float(value)})
            if hasattr(result, "detach"):
                result = result.detach().cpu().item()
            dielectric = finite_number(result, "gold imaginary-frequency dielectric")
            if dielectric < 1:
                raise ValueError("Gold imaginary-frequency dielectric must be >= 1")
            output.append(dielectric)
        return np.asarray(output, dtype=np.float64).reshape(values.shape)

    return evaluate, f"{method.__qualname__}: {input_description}"


def pfa_reference(
    module: Any, config: Json, meshes: dict[str, Mesh], kappa_um: Array
) -> Json:
    scale, scale_note = geometry_scale(config)
    patches = local_pfa_patches(config, scale)
    model, provenance = material_model(module, config)
    epsilon, api_description = dielectric_function(model)
    # q integration: v = 2*g*(q-kappa); Gauss-Laguerre integrates exp(-v).
    v, weights = np.polynomial.laguerre.laggauss(96)
    kappa = kappa_um * 1e6
    eps = epsilon(kappa)
    tm_total = np.zeros_like(kappa)
    te_total = np.zeros_like(kappa)

    def spectrum(gap: float, frequency: Array, dielectric: Array) -> tuple[Array, Array]:
        q = frequency[:, None] + v[None, :] / (2 * gap)
        material_q = np.sqrt(q * q + (dielectric[:, None] - 1) * frequency[:, None] ** 2)
        tm = (dielectric[:, None] * q - material_q) / (dielectric[:, None] * q + material_q)
        te = (q - material_q) / (q + material_q)
        propagation = np.exp(-2 * gap * frequency[:, None] - v[None, :])
        prefactor = -HBAR * LIGHT_SPEED / (2 * np.pi**2)
        results: list[Array] = []
        for reflection in (tm, te):
            r2 = reflection * reflection
            denominator = 1 - r2 * propagation
            if np.any(denominator <= 0):
                raise FloatingPointError("Nonpositive Lifshitz multiple-reflection denominator")
            integrand = q * q * r2 * np.exp(-2 * gap * frequency[:, None]) / denominator
            results.append(prefactor * (integrand @ weights) / (2 * gap))
        return results[0], results[1]

    total_force = 0.0
    # Independently integrate kappa through a rational map over [0, infinity).
    nodes, xi_weights = np.polynomial.legendre.leggauss(128)
    t = (nodes + 1) / 2
    xi_weights = xi_weights / 2
    patch_records: list[Json] = []
    for area, gap in patches:
        frequencies = t / ((1 - t) * 2 * gap)
        jacobian = 1 / (2 * gap * (1 - t) ** 2)
        tm, te = spectrum(gap, frequencies, epsilon(frequencies))
        pressure = float(np.dot(xi_weights * jacobian, tm + te))
        force = pressure * area
        if not math.isfinite(force):
            raise FloatingPointError("Non-finite integrated local Lifshitz-PFA force")
        total_force += force
        plotted_tm, plotted_te = spectrum(gap, kappa, eps)
        # Convert dF/d(kappa_m^-1) [N*m] to pN per (um^-1).
        tm_total += area * plotted_tm * 1e18
        te_total += area * plotted_te * 1e18
        patch_records.append({
            "overlap_area_m2": area, "gap_m": gap, "pressure_Pa": pressure,
            "force_pN": force * 1e12,
        })
    return {
        "f_net_pN": total_force * 1e12,
        "f_net_fN": total_force * 1e15,
        "kappa_um_inv": kappa_um,
        "integrand_total_pN_per_um_inv": tm_total + te_total,
        "integrand_TM_pN_per_um_inv": tm_total,
        "integrand_TE_pN_per_um_inv": te_total,
        "patches": patch_records,
        "geometry_scale_note": scale_note,
        "material": {**provenance, "dielectric_api": api_description},
        "quadrature": {"kappa_legendre_nodes": 128, "q_laguerre_nodes": 96},
        "assumptions": [
            "Zero-temperature continuum imaginary-frequency Lifshitz integral.",
            "Identical semi-infinite Gold Drude media separated by vacuum.",
            "Exact analytical polar tooth/bridge overlap from configuration geometry.",
            "Four 90-degree sectors, 15-degree teeth, and 30-degree open apertures.",
            "Stator bridge top at z=0; rotor tip at z=0.015 um.",
            "Open aperture contributes zero local PFA force.",
            "No lateral diffraction, nonlocal response, roughness, or finite-film transmission.",
            "The 150 nm pad is treated as a half-space, not as a finite multilayer film.",
        ],
    }


def bem_spectrum(payload: Any) -> Json | None:
    """Read the solver's per-xi output or explicitly unit-labelled spectra."""
    if isinstance(payload, Mapping):
        rows = payload.get("per_xi_integrands", [])
        if rows is None:
            rows = []
        if not isinstance(rows, (list, tuple)):
            raise TypeError("BEM per_xi_integrands must be a sequence")
        if rows:
            if not all(isinstance(row, Mapping) for row in rows):
                raise TypeError("BEM per-xi integrands must contain mappings")
            x = np.asarray([
                finite_number(row.get("kappa_um_inv"), "BEM kappa_um_inv")
                for row in rows
            ], dtype=np.float64)
            if np.any(x < 0):
                raise ValueError("BEM imaginary-frequency nodes must be nonnegative")
            result: Json = {"kappa_um_inv": x}
            for polarization, key in (
                ("total", "force_integrand"),
                ("TM", "TM_force_integrand"),
                ("TE", "TE_force_integrand"),
            ):
                values = [row.get(key) for row in rows]
                if any(value is None for value in values):
                    if polarization == "total":
                        raise ValueError("BEM per-xi output is missing force_integrand")
                    result[polarization] = None
                    continue
                y = np.asarray([
                    finite_number(value, f"BEM {key}") for value in values
                ], dtype=np.float64) * MEEP_FORCE_TO_SI * 1e12
                if not np.isfinite(y).all():
                    raise ValueError("Invalid converted BEM imaginary-frequency integrand")
                result[polarization] = y
            return result

    for mapping in walk_mappings(payload):
        kappa = mapping.get("kappa_um_inv", mapping.get("kappa_um"))
        total = mapping.get("integrand_total_pN_per_um_inv")
        if kappa is None or total is None:
            continue
        result = {"kappa_um_inv": np.asarray(kappa, dtype=float)}
        for polarization in ("total", "TM", "TE"):
            value = mapping.get(f"integrand_{polarization}_pN_per_um_inv")
            result[polarization] = None if value is None else np.asarray(value, dtype=float)
        x = result["kappa_um_inv"]
        if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or np.any(x < 0):
            raise ValueError("Invalid BEM imaginary-frequency nodes")
        for polarization in ("total", "TM", "TE"):
            y = result[polarization]
            if y is not None and (y.shape != x.shape or not np.isfinite(y).all()):
                raise ValueError("Invalid BEM imaginary-frequency integrand")
        return result
    return None


def comparisons(tasks: list[Json], meep: Json, pfa: list[Json]) -> list[Json]:
    records: list[Json] = []
    for task, local in zip(tasks, pfa, strict=True):
        selected = meep["selected"].get(str(task["task_id"]))
        record: Json = {
            "task_id": task["task_id"],
            "theta_deg": task["theta_deg"],
            "bem_F_net": task["F_net"],
            "bem_f_net_pN": task["f_net_pN"],
            "bem_f_net_fN": task["f_net_fN"],
            "bem_runtime_wall_seconds": task["runtime_wall_seconds"],
            "lifshitz_pfa_pN": local["f_net_pN"],
            "bem_minus_pfa_pN": task["f_net_pN"] - local["f_net_pN"],
            "three_dimensional_correction_fraction": ratio(
                task["f_net_pN"] - local["f_net_pN"], task["f_net_pN"]
            ),
            "edge_diffraction_fraction": task["edge_diffraction_fraction"],
            "memory_reduction_factor": ratio(MEEP_MEMORY_GIB, task["working_memory_GiB"]),
            "runtime_speedup_factor": None,
            "meep": None,
        }
        if selected:
            raw = selected["payload"]
            record["meep"] = {
                "path": selected["path"],
                "sha256": selected["sha256"],
                "F_net": find_value(raw, ("F_net",)),
                "f_net_pN": find_value(raw, ("f_net_pN",)),
                "f_net_fN": find_value(raw, ("f_net_fN",)),
                "runtime_seconds": selected["runtime_seconds"],
                "bem_minus_meep_pN": task["f_net_pN"] - finite_number(
                    find_value(raw, ("f_net_pN",)), "Meep f_net_pN"
                ),
            }
            record["runtime_speedup_factor"] = ratio(
                selected["runtime_seconds"], task["runtime_wall_seconds"]
            )
        records.append(record)
    return records


def metric_logger_context(output_dir: Path) -> Json:
    return {
        "output_dir": output_dir,
        "results_dir": output_dir,
        "metrics_path": output_dir / "provenance_metrics.json",
        "metrics_file": output_dir / "provenance_metrics.json",
        "log_path": output_dir / "provenance_metrics.json",
    }


def ztip_summary(rows: list[Json]) -> Json:
    """Summarize the sampled maximum and first sign-changing bracket in height order."""
    if not rows:
        return {
            "has_repulsion": False,
            "max_repulsive_f_net_pN": None,
            "max_repulsive_f_net_fN": None,
            "max_repulsive_z_tip_nm": None,
            "z_tip_equilibrium_nm": None,
        }
    for row in rows:
        for key in ("f_net_pN", "f_net_fN", "z_tip_nm"):
            finite_number(row[key], f"scan {key}")
    max_repulsive_row = max(rows, key=lambda r: r["f_net_pN"])
    ordered = sorted(rows, key=lambda r: r["z_tip_nm"])
    equilibrium = None
    for left, right in zip(ordered, ordered[1:]):
        f_left, f_right = left["f_net_pN"], right["f_net_pN"]
        if (f_left < 0 < f_right) or (f_right < 0 < f_left):
            # Scale before taking a difference to avoid overflow for large finite forces.
            force_scale = max(abs(f_left), abs(f_right))
            a, b = f_left / force_scale, f_right / force_scale
            fraction = -a / (b - a)
            equilibrium = finite_number(
                (1 - fraction) * left["z_tip_nm"] + fraction * right["z_tip_nm"],
                "interpolated equilibrium nm",
            )
            break
    return {
        "has_repulsion": bool(max_repulsive_row["f_net_pN"] > 0),
        "max_repulsive_f_net_pN": max_repulsive_row["f_net_pN"],
        "max_repulsive_f_net_fN": max_repulsive_row["f_net_fN"],
        "max_repulsive_z_tip_nm": max_repulsive_row["z_tip_nm"],
        "z_tip_equilibrium_nm": equilibrium,
    }


def log_provenance(
    logger: Any, report: Json, output_dir: Path, solver_parameters: Json
) -> Json:
    logger.set_solver_provenance("bem", solver_parameters)
    metrics: Json = {
        "clutch_on_off_contrast_ratio": report["clutch_on_off_contrast_ratio"],
        "meep_reference_memory_GiB": MEEP_MEMORY_GIB,
        "meep_fresh_data_available": report["meep"]["meep_fresh_data_available"],
    }
    for task in report["bem_tasks"]:
        task_metrics = {
            key: value for key, value in task.items()
            if isinstance(value, (int, float, bool)) or value is None
        }
        logger.log_step(
            "solver_comparison_pilot",
            task_metrics,
            solver_name="bem",
            solver_parameters=solver_parameters,
        )
        for name, value in task_metrics.items():
            metrics[f"task_{task['task_id']:03d}_{name}"] = value
    for comparison in report["comparisons"]:
        task_id = comparison["task_id"]
        for name in ("memory_reduction_factor", "runtime_speedup_factor",
                     "three_dimensional_correction_fraction", "edge_diffraction_fraction"):
            metrics[f"task_{task_id:03d}_{name}"] = comparison[name]
    for row in report["quadrature_convergence"]:
        metrics[f"task_{row['task_id']:03d}_nxi_{row['n_xi']}_force_pN"] = row["f_net_pN"]
        metrics[f"task_{row['task_id']:03d}_nxi_{row['n_xi']}_runtime_seconds"] = row["runtime_wall_seconds"]

    scan_metrics: Json = {}
    for index, row in enumerate(report["ztip_scan_th0"]):
        row_metrics = {
            key: row[key] for key in (
                "z_tip_um", "z_tip_nm", "f_net_pN", "f_net_fN",
                "bottom_face_pN", "lateral_edge_pN", "runtime_wall_seconds",
            )
        }
        logger.log_step(
            f"ztip_scan_th0_{index:03d}",
            row_metrics,
            solver_name="bem",
            solver_parameters=solver_parameters,
        )
        for name, value in row_metrics.items():
            scan_metrics[f"ztip_scan_{index:03d}_{name}"] = value
    summary = report["ztip_repulsion_summary"]
    scan_metrics.update({
        "ztip_has_repulsion": summary["has_repulsion"],
        "ztip_max_repulsive_f_net_pN": summary["max_repulsive_f_net_pN"],
        "ztip_max_repulsive_f_net_fN": summary["max_repulsive_f_net_fN"],
        "ztip_max_repulsive_z_tip_nm": summary["max_repulsive_z_tip_nm"],
        "ztip_equilibrium_nm": summary["z_tip_equilibrium_nm"],
    })
    for task in report["scalar_bem_tasks"]:
        task_metrics = {
            "task_id": task["task_id"],
            "theta_deg": task["theta_deg"],
            "z_tip_nm": task["z_tip_nm"],
            "f_net_pN": task["f_net_pN"],
            "f_net_fN": task["f_net_fN"],
        }
        logger.log_step(
            f"scalar_task_{task['task_id']:03d}",
            task_metrics,
            solver_name="bem",
            solver_parameters=solver_parameters,
        )
        scan_metrics[f"scalar_task_{task['task_id']:03d}_f_net_pN"] = task["f_net_pN"]
        scan_metrics[f"scalar_task_{task['task_id']:03d}_f_net_fN"] = task["f_net_fN"]
    peak_scalar = report["scalar_ztip_peak_task"]
    scan_metrics["scalar_ztip_peak_f_net_pN"] = peak_scalar["f_net_pN"]
    scan_metrics["scalar_ztip_peak_z_tip_nm"] = peak_scalar["z_tip_nm"]
    logger.log_step(
        "ztip_repulsion_summary",
        scan_metrics,
        solver_name="bem",
        solver_parameters=solver_parameters,
    )
    metrics.update(scan_metrics)
    for name, value in metrics.items():
        if not isinstance(value, (int, float, bool)):
            continue
        if not math.isfinite(float(value)):
            continue
        logger.log_metric(
            name,
            value,
            step_id="solver_comparison_pilot",
            solver_name="bem",
            solver_parameters=solver_parameters,
        )
    logger.export_macros()
    return metrics


def reported_dof(payload: Any) -> float | None:
    return optional_number(
        payload, ("degrees_of_freedom", "n_dof", "num_dofs", "dof", "n_panels_total")
    )


def save_figures(
    report: Json, logger: Any, args: argparse.Namespace, solver_parameters: Json
) -> list[Json]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    args.figures_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.labelsize": 10,
        "axes.titlesize": 10,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.dpi": 600,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.2), constrained_layout=True)
    colors = ("#0072B2", "#D55E00")
    labels = ("0° Disengaged", "45° Engaged")
    spectral_sources: list[str] = []
    for index, (task, reference) in enumerate(zip(report["bem_tasks"], report["pfa"], strict=True)):
        spectrum = bem_spectrum(task["raw_solver_result"])
        if spectrum is None:
            spectrum = {
                "kappa_um_inv": reference["kappa_um_inv"],
                "total": reference["integrand_total_pN_per_um_inv"],
                "TM": reference["integrand_TM_pN_per_um_inv"],
                "TE": reference["integrand_TE_pN_per_um_inv"],
            }
            source = "1D Lifshitz-PFA"
        else:
            source = "3D Vector Dyadic BEM"
        spectral_sources.append(source)
        x = np.asarray(spectrum["kappa_um_inv"])
        order = np.argsort(x)
        order = order[x[order] > 0]
        for component, style in (("total", "-"), ("TM", "--"), ("TE", ":")):
            values = spectrum[component]
            if values is not None and len(order):
                axes[0, 0].plot(
                    x[order], np.asarray(values)[order], style,
                    color=colors[index], linewidth=1.5,
                    label=f"{labels[index]} {component} ({source})",
                )
    axes[0, 0].set_xscale("log")
    axes[0, 0].set_xlabel(r"$\kappa$ ($\mu$m$^{-1}$)")
    axes[0, 0].set_ylabel(r"$dF_z/d\kappa$ (pN per $\mu$m$^{-1}$)")
    axes[0, 0].set_title("(a) Imaginary-frequency force integrand")
    if axes[0, 0].get_legend_handles_labels()[0]:
        axes[0, 0].legend(loc="best")
    axes[0, 0].grid(alpha=0.2)
    if any(source != "3D Vector Dyadic BEM" for source in spectral_sources):
        axes[0, 0].text(
            0.02, 0.02, "PFA curves are references, not reconstructed BEM spectra.",
            transform=axes[0, 0].transAxes, fontsize=7,
        )

    x = np.arange(2, dtype=float)
    series = [
        ("3D Vector BEM total", [abs(task["f_net_pN"]) for task in report["bem_tasks"]], "#333333"),
        ("BEM bottom face", [task["bottom_face_pN"] for task in report["bem_tasks"]], "#56B4E9"),
        ("BEM lateral/edge", [task["lateral_edge_pN"] for task in report["bem_tasks"]], "#E69F00"),
        ("1D Lifshitz-PFA", [abs(reference["f_net_pN"]) for reference in report["pfa"]], "#009E73"),
        ("Meep 4-pass", [
            comparison["meep"]["f_net_pN"] if comparison["meep"] else None
            for comparison in report["comparisons"]
        ], "#CC79A7"),
    ]
    width = 0.15
    for offset, (name, values, color) in enumerate(series):
        for index, value in enumerate(values):
            position = x[index] + (offset - 2) * width
            if value is not None:
                axes[0, 1].bar(
                    position, abs(float(value)), width, color=color,
                    label=name if index == next(i for i, v in enumerate(values) if v is not None) else None,
                )
            elif name == "Meep 4-pass":
                axes[0, 1].annotate(
                    "Pending\nCluster Run", (position, 0),
                    xytext=(0, 5), textcoords="offset points", ha="center", fontsize=6,
                )
    axes[0, 1].set_xticks(x, labels)
    axes[0, 1].set_ylabel(r"$|f_\mathrm{net}|$ or component magnitude (pN)")
    axes[0, 1].set_title("(b) Same-architecture force comparison")
    axes[0, 1].legend(loc="best")
    axes[0, 1].grid(axis="y", alpha=0.2)
    if any(task["bottom_face_pN"] is None for task in report["bem_tasks"]):
        axes[0, 1].text(
            0.02, 0.98, "Unreported BEM components omitted",
            transform=axes[0, 1].transAxes, va="top", fontsize=7,
        )

    for task_id, color, label in zip((1, 2), colors, labels, strict=True):
        rows = sorted(
            (row for row in report["quadrature_convergence"] if row["task_id"] == task_id),
            key=lambda row: row["n_xi"],
        )
        if rows:
            axes[1, 0].plot(
                [row["n_xi"] for row in rows], [row["f_net_pN"] for row in rows],
                "o-", color=color, label=label,
            )
    axes[1, 0].set_xlabel(r"Imaginary-frequency quadrature nodes $n_\xi$")
    axes[1, 0].set_ylabel(r"Signed $f_\mathrm{net}$ (pN)")
    axes[1, 0].set_title("(c) Quadrature convergence")
    axes[1, 0].set_xticks((8, 16, 24))
    axes[1, 0].grid(alpha=0.2)
    if report["quadrature_convergence"]:
        axes[1, 0].legend()
    else:
        axes[1, 0].text(
            0.5, 0.5, "Convergence sweep skipped\n(max-steps micro-probe)",
            transform=axes[1, 0].transAxes, ha="center",
        )

    resource_axis = axes[1, 1]
    dof_axis = resource_axis.twinx()
    memory = [MEEP_MEMORY_GIB] + [task["working_memory_GiB"] for task in report["bem_tasks"]]
    dofs = report["resources"]["degrees_of_freedom"]
    positions = np.arange(3)
    memory_bars = resource_axis.bar(
        positions - 0.16, memory, 0.3, color="#0072B2", label="Memory GiB"
    )
    dof_bars = []
    for index, value in enumerate(dofs):
        if value is not None and value > 0:
            bars = dof_axis.bar(positions[index] + 0.16, value, 0.3, color="#E69F00")
            dof_bars.extend(bars)
        else:
            resource_axis.text(index, 0.03, "DoF unreported",
                               transform=resource_axis.get_xaxis_transform(),
                               ha="center", fontsize=6)
    resource_axis.set_yscale("log")
    resource_axis.set_ylabel("Memory (GiB)", color="#0072B2")
    dof_axis.set_ylabel("DoF / panel or Yee-cell proxy", color="#E69F00")
    if dof_bars:
        dof_axis.set_yscale("log")
        resource_axis.legend([memory_bars, dof_bars[0]], ["Memory GiB", "DoF / proxy"], fontsize=7)
    else:
        resource_axis.legend()
    resource_axis.set_xticks(positions, ("Meep Yee\nR=80", "Surface BEM\n0°", "Surface BEM\n45°"))
    resource_axis.set_title("(d) Computational resources")
    resource_axis.grid(axis="y", alpha=0.2)
    figure.suptitle(
        "Scoped pilot concentric Casimir clutch: solver comparison"
        + (" — MICRO-PROBE, NOT CONVERGED" if report["micro_probe"] else ""),
        fontsize=13,
    )

    artifacts: list[Json] = []

    def save_publication_figure(fig: Any, stem: str, sources: list[str]) -> None:
        for extension in ("png", "pdf"):
            path = args.figures_dir / f"{stem}.{extension}"
            fig.savefig(path, bbox_inches="tight")
            artifact = {
                "path": str(path), "sha256": digest(path),
                "solver_name": "bem", "solver_parameters": solver_parameters,
                "spectral_sources": sources,
                "report_path": str(args.output_dir / "solver_comparison_pilot_report.json"),
                "configuration_provenance": report["configuration_provenance"],
                "meep_fresh_data_available": report["meep"]["meep_fresh_data_available"],
                "freshness_guard": report["meep"]["declaration"],
                "micro_probe": report["micro_probe"],
            }
            logger.save_plot_provenance(
                str(path),
                str(args.output_dir / "provenance_metrics.json"),
                list(report["metrics"].keys()),
                solver_name="bem",
                solver_parameters=solver_parameters,
            )
            artifacts.append(artifact)

    try:
        save_publication_figure(
            figure, "fig_solver_comparison_clutch_pilot", spectral_sources
        )
    finally:
        plt.close(figure)

    scan_figure, scan_axes = plt.subplots(
        1, 2, figsize=(12.0, 5.2), constrained_layout=True
    )
    try:
        rows = sorted(report["ztip_scan_th0"], key=lambda r: r["z_tip_nm"])
        scan_axis, comparison_axis = scan_axes
        heights = [row["z_tip_nm"] for row in rows]
        for key, name, color, style in (
            ("f_net_fN", "Total 3D Vector BEM force", "#0072B2", "o-"),
            ("lateral_edge_pN", "Lateral/Edge component", "#E69F00", "s--"),
            ("bottom_face_pN", "Bottom-face component", "#CC79A7", "^:"),
        ):
            values = [
                np.nan if row[key] is None else finite_number(
                    row[key] if key == "f_net_fN" else row[key] * 1000.0,
                    f"scan plotted {key}",
                )
                for row in rows
            ]
            if any(math.isfinite(value) for value in values):
                scan_axis.plot(
                    heights, values, style, color=color, linewidth=1.6,
                    markersize=4, label=name,
                )
        scan_axis.axhline(0.0, color="#333333", linestyle="--", linewidth=1)
        lower, upper = scan_axis.get_ylim()
        span = max(abs(lower), abs(upper), np.finfo(float).eps)
        lower = min(lower, -0.18 * span)
        upper = max(upper, 0.18 * span)
        scan_axis.set_ylim(lower, upper)
        scan_axis.axhspan(0, upper, color="#009E73", alpha=0.10, zorder=0)
        scan_axis.axhspan(lower, 0, color="#D55E00", alpha=0.10, zorder=0)
        scan_axis.text(
            0.02, 0.97, r"REPULSIVE REGIME ($F_z > 0$)",
            transform=scan_axis.transAxes, va="top", color="#007A50", fontsize=8,
        )
        scan_axis.text(
            0.02, 0.03, r"ATTRACTIVE REGIME ($F_z < 0$)",
            transform=scan_axis.transAxes, va="bottom", color="#A84000", fontsize=8,
        )
        scan_axis.axvline(
            15.0, color="#666666", linestyle=":", linewidth=1.4,
            label="Original pilot: +15 nm (above stator)",
        )
        equilibrium = report["ztip_repulsion_summary"]["z_tip_equilibrium_nm"]
        if equilibrium is not None:
            scan_axis.axvline(
                equilibrium, color="#009E73", linestyle="-.", linewidth=1.4,
                label=f"Zero-force equilibrium: {equilibrium:.3g} nm",
            )
        scan_axis.annotate(
            "", xy=(-175, 0.17), xytext=(0, 0.17),
            xycoords=scan_axis.get_xaxis_transform(),
            arrowprops={"arrowstyle": "|-|", "color": "#555555"},
        )
        scan_axis.text(
            -87.5, 0.19, "Stator z-bounds [−175, 0] nm",
            transform=scan_axis.get_xaxis_transform(), ha="center", fontsize=7,
        )
        scan_axis.set_xlabel(r"Rotor tip height $z_\mathrm{tip}$ (nm)")
        scan_axis.set_ylabel(r"Signed vertical Casimir force $f_\mathrm{net}$ (fN)")
        scan_axis.set_title("(a) θ=0°: Disengaged in 30° slot")
        scan_axis.grid(alpha=0.2)
        scan_axis.legend(loc="best")
        if any(
            row["bottom_face_pN"] is None or row["lateral_edge_pN"] is None
            for row in rows
        ):
            scan_axis.text(
                0.98, 0.5, "Unreported components omitted",
                transform=scan_axis.transAxes, ha="right", fontsize=7,
            )

        peak = max(rows, key=lambda r: r["f_net_pN"]) if rows else None
        vector_values = [
            report["bem_tasks"][0]["f_net_fN"],
            peak["f_net_fN"] if peak else None,
            report["bem_tasks"][1]["f_net_fN"],
        ]
        scalar_values = [
            report["scalar_bem_tasks"][0]["f_net_fN"],
            report["scalar_ztip_peak_task"]["f_net_fN"],
            report["scalar_bem_tasks"][1]["f_net_fN"],
        ]
        peak_label = (
            f"0° sampled {'peak repulsion' if peak['f_net_pN'] > 0 else 'maximum'}\n"
            f"z={peak['z_tip_nm']:g} nm"
            if peak else "0° scan unavailable"
        )
        bar_positions = np.arange(3)
        for offset, values, label, color in (
            (-0.18, vector_values, "3D Vector Dyadic BEM", "#0072B2"),
            (0.18, scalar_values, "Scalar Yukawa BEM", "#D55E00"),
        ):
            valid = [(i, value) for i, value in enumerate(values) if value is not None]
            if valid:
                comparison_axis.bar(
                    [bar_positions[i] + offset for i, _ in valid],
                    [value for _, value in valid], 0.34, color=color, label=label,
                )
        comparison_axis.axhline(0, color="#333333", linestyle="--", linewidth=1)
        comparison_axis.set_xticks(
            bar_positions, ("0° Disengaged\nz=+15 nm", peak_label, "45° Engaged\nz=+15 nm")
        )
        comparison_axis.set_ylabel(r"Signed $f_\mathrm{net}$ (fN)")
        comparison_axis.set_title("(b) Vector electromagnetic vs scalar BEM")
        comparison_axis.legend(loc="best")
        comparison_axis.grid(axis="y", alpha=0.2)
        comparison_axis.text(
            0.02, 0.02,
            f"Pilot nξ={args.n_xi}; peak pair nξ={report['ztip_scan_n_xi']}",
            transform=comparison_axis.transAxes, fontsize=7,
        )
        scan_figure.suptitle(
            "Concentric Casimir clutch: θ=0° tip-height repulsion scan"
            + (" — MICRO-PROBE, NOT CONVERGED" if report["micro_probe"] else ""),
            fontsize=12,
        )
        save_publication_figure(
            scan_figure, "fig_clutch_ztip_repulsion_scan",
            ["3D Vector Dyadic BEM", "Scalar Yukawa BEM"],
        )
    finally:
        plt.close(scan_figure)
    return artifacts


def format_number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    return f"{finite_number(value, 'report value'):.7g}{suffix}"


def markdown_report(report: Json) -> str:
    lines = [
        "# Scoped Pilot Concentric Casimir Clutch: Solver Comparison",
        "",
        f"Generated: {report['generated_utc']}",
        "",
        "## Execution scope",
        "",
        "The original pilot configurations are used without architectural replacement: "
        "task 1 at 0° (Disengaged), and task 2 at 45° (Engaged), both at z_tip=+15 nm. "
        "Primary results use the 3D vector electromagnetic dyadic BEM (vector_dyadic); "
        "scalar_yukawa is run separately at the same pilot heights. "
        "The BEM discretization is n_r=2, n_phi_tooth=3, n_phi_bridge=3, n_z=2.",
        "",
        f"**Micro-probe:** {report['micro_probe']}. "
        "A positive max-steps produces diagnostic, potentially unconverged forces and "
        "must not be interpreted as a publication-ready physical result.",
        "",
        "## Data-freshness guard",
        "",
        f"**{report['meep']['declaration']}**",
        "",
        f"Latest BUG_LOG fix: {report['meep']['audit']['latest_fix_utc']}. "
        "Accepted files require cache version >=5, co-located non-null F_stator/F_vac, "
        "mtime strictly after the fix, and finite F_net, f_net_pN, f_net_fN. "
        "Stale two-pass values are neither plotted nor used for speedup estimates.",
        "",
        report["meep"]["metadata_policy"],
        "",
        "| State | Vector BEM signed force (pN) | Local Lifshitz-PFA (pN) | Fresh Meep (pN) | BEM wall time (s) |",
        "|---|---:|---:|---:|---:|",
    ]
    for comparison in report["comparisons"]:
        fresh = comparison["meep"]
        lines.append(
            f"| {comparison['theta_deg']:g}° | "
            f"{format_number(comparison['bem_f_net_pN'])} | "
            f"{format_number(comparison['lifshitz_pfa_pN'])} | "
            f"{format_number(fresh['f_net_pN'] if fresh else None)} | "
            f"{format_number(comparison['bem_runtime_wall_seconds'])} |"
        )

    lines.extend([
        "",
        "## Vector Dyadic BEM vs Scalar Yukawa BEM & z_tip Repulsion Scan at 0°",
        "",
        "The vector_dyadic formulation uses the upgraded 3D vector electromagnetic "
        "dyadic solver; scalar_yukawa is a scalar-kernel comparison, not an equivalent "
        "electromagnetic theory. All entries below are actual solver outputs, not "
        "inferred signs or reconstructed forces.",
        "",
        "| State at z_tip=+15 nm | Vector Dyadic BEM (pN) | Scalar Yukawa BEM (pN) |",
        "|---|---:|---:|",
    ])
    for vector, scalar in zip(report["bem_tasks"], report["scalar_bem_tasks"], strict=True):
        lines.append(
            f"| {vector['theta_deg']:g}° | {format_number(vector['f_net_pN'])} | "
            f"{format_number(scalar['f_net_pN'])} |"
        )
    lines.extend([
        "",
        f"The θ=0° height scan uses n_xi={report['ztip_scan_n_xi']} and "
        f"max_steps={report['solver_parameters']['max_steps']}. "
        "Positive F_z denotes upward repulsion; negative F_z denotes attraction. "
        "Missing components remain unavailable. A lateral/edge component may be "
        "the explicitly labelled total-minus-bottom residual recorded with each task.",
        "",
        "| z_tip_nm | Signed f_net (pN) | Signed f_net (fN) | Bottom face (fN) | Lateral/Edge (fN) | Regime |",
        "|---:|---:|---:|---:|---:|---|",
    ])
    for row in report["ztip_scan_th0"]:
        bottom = row["bottom_face_pN"]
        edge = row["lateral_edge_pN"]
        regime = (
            "Repulsive" if row["f_net_pN"] > 0 else
            "Attractive" if row["f_net_pN"] < 0 else "Zero force"
        )
        lines.append(
            f"| {format_number(row['z_tip_nm'])} | {format_number(row['f_net_pN'])} | "
            f"{format_number(row['f_net_fN'])} | "
            f"{format_number(bottom * 1000.0 if bottom is not None else None)} | "
            f"{format_number(edge * 1000.0 if edge is not None else None)} | {regime} |"
        )
    summary = report["ztip_repulsion_summary"]
    scalar_peak = report["scalar_ztip_peak_task"]
    lines.extend([
        "",
        f"**Repulsion detected:** {summary['has_repulsion']}. "
        f"The largest sampled signed vector force is "
        f"{format_number(summary['max_repulsive_f_net_pN'])} pN "
        f"({format_number(summary['max_repulsive_f_net_fN'])} fN) at "
        f"z_tip={format_number(summary['max_repulsive_z_tip_nm'])} nm. "
        "If every sample is attractive, this maximum is not a repulsive peak.",
        "",
        f"The first adjacent opposite-sign bracket in ascending height gives a "
        f"linearly interpolated zero-force height z_tip_eq="
        f"{format_number(summary['z_tip_equilibrium_nm'])} nm. "
        "No sign change yields an unavailable equilibrium. This is a sampled "
        "zero-force estimate, not proof of stable levitation or a converged root.",
        "",
        f"A separate scalar solve at the same sampled maximum height gives "
        f"{format_number(scalar_peak['f_net_pN'])} pN "
        f"({format_number(scalar_peak['f_net_fN'])} fN), using the same scan n_xi "
        "and max_steps as the vector scan. The figure uses the measured maximum "
        "rather than assuming that the peak occurs at −250 nm.",
        "",
        "At z_tip=+15 nm (>0), the rotor tips are above the stator top, so a "
        "horizontal plane can separate the bodies. The Kenneth–Klich attraction "
        "theorem applies to reflection-related bodies across a separating plane "
        "under its material assumptions; a separating plane alone does not prove "
        "attraction for arbitrary, non-mirror-related rotor/stator shapes. "
        "It must therefore not be used as a universal sign constraint on this clutch.",
        "",
        "When z_tip dips below roughly −160 nm inside the open 30° slot aperture, "
        "the intended geometry enters a deeply interdigitated regime. The stator "
        "z-bounds are [−175 nm, 0 nm]; overlapping vertical extents remove the "
        "simple horizontal separating-plane argument. Lateral and edge coupling "
        "can then support a positive vertical force F_z>0 without contradicting "
        "the Kenneth–Klich theorem. Repulsion is asserted only where the computed "
        "scan is positive, not merely because the tip is below −160 nm. "
        "Collision freedom and spatial/frequency convergence still require "
        "independent verification, especially for a max-steps micro-probe.",
        "",
        "The dedicated figure fig_clutch_ztip_repulsion_scan shows signed total, "
        "bottom-face and lateral/edge forces, sign-regime shading, the +15 nm "
        "pilot marker, any interpolated equilibrium, and the stator z-bounds. "
        "Its second panel compares vector and scalar forces at both pilot states "
        "and at the sampled θ=0° maximum.",
        "",
        "## Physical interpretation",
        "",
        "At 45°, the intended 4×3=12 rotor teeth align with the gold landing pad; "
        "the nominal tip gap is 15 nm and pad thickness is 150 nm. At 0°, the teeth "
        "face the open 30° slot aperture. Exact polar overlap areas are computed "
        "from the original configuration's radial track bounds and periodic angular "
        "intervals, rather than triangulated facet areas or guessed tooth dimensions. "
        "The stator bridge spans 30°–90° in each sector, and the rotor tooth spans "
        "15°+theta±7.5°, modulo 90°. The detailed patch audit is included in the JSON report.",
        "",
        "The local reference integrates the exact vacuum/Gold Drude Lifshitz TM and TE "
        "reflection integrand over imaginary angular frequency and transverse "
        "wavevector. The q=sqrt(kappa²+k_perp²) change of variables retains the exact "
        "Jacobian. MaterialModel.from_parameters supplies the dielectric response; "
        "no independently fitted or ideal-metal dielectric is substituted.",
        "",
        "This is a zero-temperature, semi-infinite-medium local reference. A finite "
        "150 nm film, thermal Matsubara corrections, roughness, spatial dispersion, "
        "and multilayer support response are not silently folded into it. An open "
        "slot without an underlying surface contributes zero local PFA force, but "
        "can still have a nonzero 3D electromagnetic force through nearby edges. "
        "The PFA reference here is only for the original +15 nm pilot heights, "
        "not for the interdigitated height scan.",
        "",
        "A BEM–PFA difference is a total three-dimensional/local-model correction, "
        "**not automatically an edge-diffraction measurement**. Edge fractions are "
        "reported only from solver components, or a clearly labelled total-minus-bottom "
        "residual. Signed component magnitudes do not generally add to the magnitude "
        "of the signed total.",
        "",
        f"Clutch on/off contrast |F_engaged/F_disengaged|: "
        f"**{format_number(report['clutch_on_off_contrast_ratio'])}**. "
        "A zero off-state denominator is represented as unavailable, not infinity.",
        "",
        "## Numerical convergence and geometry",
        "",
        "The production sweep uses vector_dyadic with n_xi=8,16,24 for both states "
        "at +15 nm with fixed spatial discretization. Frequency convergence is not "
        "spatial-panel convergence and does not establish a complete error bound. "
        "Relative changes use the finest sweep force as denominator and are "
        "unavailable for a zero denominator. The lower-node height scan and scalar "
        "comparisons are not independently convergence-certified by this sweep.",
        "",
        "| State | n_xi | Signed force (pN) | Relative difference from n_xi=24 |",
        "|---|---:|---:|---:|",
    ])
    for row in report["quadrature_convergence"]:
        lines.append(
            f"| {row['theta_deg']:g}° | {row['n_xi']} | "
            f"{format_number(row['f_net_pN'])} | "
            f"{format_number(row['relative_difference_from_24'])} |"
        )
    if not report["quadrature_convergence"]:
        lines.append("| Micro-probe | — | Sweep skipped | — |")
    lines.extend([
        "",
        "Both in-memory and serialized Gmsh meshes are checked for exactly two "
        "incident faces per edge, consistent winding, nondegenerate and unique "
        "triangles, and connected circular vertex links. Successful exports have "
        "100% manifold watertightness. The .scuffgeo file references both meshes. "
        "Watertightness alone does not certify collision freedom or mesh convergence.",
        "",
        "## Computational comparison",
        "",
        f"The supplied Meep memory baseline is 481.27 decimal GB "
        f"({MEEP_MEMORY_GIB:.6g} GiB), not 481.27 GiB. "
        "Meep uses a 3D Yee volume grid at R=80; BEM discretizes 2D object surfaces. "
        "BEM may nevertheless require dense matrices with quadratic storage and "
        "higher-order solve cost. Solver-reported DoF are preferred; n_panels_total "
        "is used as a panel-count proxy when no explicit BEM DoF is reported. "
        "When no fresh Meep file is available, the reference proxy is "
        f"3.8×3.8×1.43×80³ = {MEEP_REFERENCE_GRID_CELLS:.7g} Yee grid cells, "
        "not an independently measured unknown count.",
        "",
        "| State | BEM memory (GiB) | Memory reduction | Runtime speedup | Edge fraction |",
        "|---|---:|---:|---:|---:|",
    ])
    for task, comparison in zip(report["bem_tasks"], report["comparisons"], strict=True):
        lines.append(
            f"| {task['theta_deg']:g}° | {format_number(task['working_memory_GiB'])} | "
            f"{format_number(comparison['memory_reduction_factor'])} | "
            f"{format_number(comparison['runtime_speedup_factor'])} | "
            f"{format_number(comparison['edge_diffraction_fraction'])} |"
        )
        lines.extend(["", f"Memory measurement for {task['theta_deg']:g}°: "
                      f"{task['memory_measurement_source']}."])
    lines.extend([
        "",
        "Runtime speedups use only fresh Meep runtimes divided by measured BEM "
        "wall time. Cluster/accelerator hardware differences, allocation scope, "
        "parallelism, cache reuse, and the four-pass workload prevent interpreting "
        "these as hardware-normalized algorithmic speedups.",
        "",
        "## Figure and provenance",
        "",
        "Panel (a) of the solver comparison uses solver per-xi BEM integrands converted "
        "with MEEP_FORCE_TO_SI=3.16152649e-14, or explicitly unit-labelled BEM spectra "
        "when available; otherwise it explicitly displays local Lifshitz-PFA "
        "reference spectra. Missing polarization-resolved BEM data are never "
        "reconstructed or falsely labelled. Zero-frequency nodes are omitted "
        "from the logarithmic axis. Panel (b) omits unreported BEM components and "
        "labels missing fresh Meep runs as Pending Cluster Run. Panel (c) distinguishes "
        "skipped micro-probe convergence. Panel (d) labels panel/Yee-cell proxies "
        "and documents the memory estimate or fallback.",
        "",
        "Configuration, BUG_LOG, accepted Meep files, exported meshes, and figures "
        "carry SHA-256 provenance. Height overrides and formulation are recorded "
        "per solve without altering the original configuration files. Metrics, "
        "LaTeX macros, and plot sidecars for both publication figures are "
        "generated by metrics_logger using its native schemas, without custom "
        "wrappers or appended macro definitions.",
        "",
        "## Audit details",
        "",
        "```json",
        json.dumps(json_safe({
            "configuration_provenance": report["configuration_provenance"],
            "freshness_candidates": {
                key: [{k: v for k, v in item.items() if k != "payload"} for item in value]
                for key, value in report["meep"]["candidates"].items()
            },
            "mesh_exports": report["mesh_exports"],
            "resources": report["resources"],
            "ztip_repulsion_summary": report["ztip_repulsion_summary"],
        }), indent=2, allow_nan=False),
        "```",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    for directory in (args.output_dir, args.figures_dir, args.meep_results_dir):
        directory.mkdir(parents=True, exist_ok=True)
    actual_device = resolved_device(args.device)
    bem = importlib.import_module("execution.casimir_bem_solver")
    logger = importlib.import_module("utils.metrics_logger")
    for name in ("set_solver_provenance", "log_step", "log_metric", "export_macros", "save_plot_provenance"):
        if not callable(getattr(logger, name, None)):
            raise AttributeError(f"utils.metrics_logger lacks callable {name}")

    paths = [args.config_dir / "config_001.json", args.config_dir / "config_002.json"]
    configs = [
        validate_config(paths[0], 1, 0.0),
        validate_config(paths[1], 2, 45.0),
    ]
    audit = bugfix_audit(ROOT / "BUG_LOG.md")
    meep = audit_meep(args.meep_results_dir, audit)

    tasks: list[Json] = []
    scalar_tasks: list[Json] = []
    meshes_by_task: list[dict[str, Mesh]] = []
    exports: Json = {}
    convergence: list[Json] = []
    pfa: list[Json] = []
    kappa_um = np.geomspace(1e-5, 2e3, 240)

    for task_id, angle, config, path in zip((1, 2), (0, 45), configs, paths, strict=True):
        destination = args.meep_results_dir / f"task_{task_id:03d}_N2_th_{angle}deg_bem.json"
        task = run_bem(
            bem, config, path, destination, args, args.n_xi,
            formulation="vector_dyadic", z_tip_um=0.015,
        )
        tasks.append(task)
        scalar_tasks.append(run_bem(
            bem, config, path,
            args.output_dir / "scalar_yukawa" / f"task_{task_id:03d}_scalar.json",
            args, args.n_xi, formulation="scalar_yukawa", z_tip_um=0.015,
        ))
        pilot_config = {
            **config, "z_tip": 0.015, "z_tip_um": 0.015, "z_tip_nm": 15.0,
        }
        meshes = build_meshes(bem, pilot_config, path)
        meshes_by_task.append(meshes)
        local = pfa_reference(bem, pilot_config, meshes, kappa_um)
        local.update(task_id=task_id, theta_deg=float(angle))
        if angle == 45:
            landing_patches = [
                patch for patch in local["patches"]
                if math.isclose(patch["gap_m"], 15e-9, rel_tol=0.02, abs_tol=0.2e-9)
            ]
            if not landing_patches:
                raise ValueError(
                    "Engaged geometry does not expose the required 15 nm gold landing-pad gap; "
                    "check track bounds and the original configuration"
                )
        pfa.append(local)
        if args.max_steps == 0:
            exports[str(task_id)] = export_meshes(
                bem, pilot_config, path, meshes, args.output_dir / f"scuff_clutch_th{angle}"
            )
            rows: list[Json] = []
            for n_xi in (8, 16, 24):
                if n_xi == args.n_xi:
                    result = task
                else:
                    result = run_bem(
                        bem, config, path,
                        args.output_dir / "convergence" /
                        f"task_{task_id:03d}_th{angle}_nxi{n_xi}_bem.json",
                        args, n_xi, formulation="vector_dyadic", z_tip_um=0.015,
                    )
                rows.append({
                    "task_id": task_id, "theta_deg": float(angle), "n_xi": n_xi,
                    "f_net_pN": result["f_net_pN"],
                    "runtime_wall_seconds": result["runtime_wall_seconds"],
                    "working_memory_GiB": result["working_memory_GiB"],
                })
            finest = rows[-1]["f_net_pN"]
            for row in rows:
                row["relative_difference_from_24"] = ratio(
                    abs(row["f_net_pN"] - finest), abs(finest)
                )
            convergence.extend(rows)

    scan_n_xi = min(args.n_xi, 12)
    ztip_scan: list[Json] = []
    for index, height_um in enumerate(Z_TIP_SCAN_UM):
        ztip_scan.append(run_bem(
            bem, configs[0], paths[0],
            args.output_dir / "ztip_scan_th0" / f"task_001_ztip_{index:03d}_vector.json",
            args, scan_n_xi, formulation="vector_dyadic", z_tip_um=height_um,
        ))
    repulsion_summary = ztip_summary(ztip_scan)
    max_repulsive_row = max(ztip_scan, key=lambda r: r["f_net_pN"])
    # A real scalar solve at the vector maximum is required for the second figure.
    scalar_peak_task = run_bem(
        bem, configs[0], paths[0],
        args.output_dir / "scalar_yukawa" / "task_001_ztip_peak_scalar.json",
        args, scan_n_xi, formulation="scalar_yukawa",
        z_tip_um=max_repulsive_row["z_tip_um"],
    )

    comparison = comparisons(tasks, meep, pfa)
    meep_dof_values = [
        reported_dof(record["payload"]) for record in meep["selected"].values()
    ]
    meep_dof = next((value for value in meep_dof_values if value is not None), None)
    if not meep["selected"]:
        meep_dof = MEEP_REFERENCE_GRID_CELLS
    solver_parameters: Json = {
        **DISCRETIZATION,
        "formulation": "vector_dyadic",
        "comparison_formulation": "scalar_yukawa",
        "formulations": ["vector_dyadic", "scalar_yukawa"],
        "z_tip_um": 0.015,
        "z_tip_nm": 15.0,
        "ztip_scan_um": list(Z_TIP_SCAN_UM),
        "ztip_scan_n_xi": scan_n_xi,
        "scalar_peak_z_tip_um": max_repulsive_row["z_tip_um"],
        "n_xi": args.n_xi,
        "n_xi_convergence_values": [8, 16, 24] if args.max_steps == 0 else [],
        "max_steps": args.max_steps,
        "device_requested": args.device,
        "device_resolved": actual_device,
        "config_dir": str(args.config_dir.resolve()),
        "meep_results_dir": str(args.meep_results_dir.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "figures_dir": str(args.figures_dir.resolve()),
        "tasks": [{"task_id": 1, "theta_deg": 0.0}, {"task_id": 2, "theta_deg": 45.0}],
        "material_provenance": [local["material"] for local in pfa],
    }
    report: Json = {
        "schema_version": 1,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "micro_probe": args.max_steps > 0,
        "solver_name": "bem",
        "solver_parameters": solver_parameters,
        "configuration_provenance": [
            {"path": str(path.resolve()), "sha256": digest(path), "config": config}
            for path, config in zip(paths, configs, strict=True)
        ],
        "bem_tasks": tasks,
        "scalar_bem_tasks": scalar_tasks,
        "ztip_scan_th0": ztip_scan,
        "ztip_scan_n_xi": scan_n_xi,
        "ztip_repulsion_summary": repulsion_summary,
        "scalar_ztip_peak_task": scalar_peak_task,
        "pfa": pfa,
        "meep": meep,
        "meep_fresh_data_available": meep["meep_fresh_data_available"],
        "data_freshness_guard_declaration": meep["declaration"],
        "quadrature_convergence": convergence,
        "mesh_exports": exports,
        "comparisons": comparison,
        "clutch_on_off_contrast_ratio": ratio(
            abs(tasks[1]["f_net_pN"]), abs(tasks[0]["f_net_pN"])
        ),
        "resources": {
            "meep_reference_memory_GB": MEEP_MEMORY_GB,
            "meep_reference_memory_GiB": MEEP_MEMORY_GIB,
            "meep_reference_memory_source": "user-specified 481.27 GB baseline",
            "meep_resolution": REQUIRED_RESOLUTION,
            "meep_moments": REQUIRED_MOMENTS,
            "degrees_of_freedom": [
                meep_dof,
                reported_dof(tasks[0]["raw_solver_result"]),
                reported_dof(tasks[1]["raw_solver_result"]),
            ],
            "meep_dof_source": (
                "reference Yee-cell proxy: 3.8 * 3.8 * 1.43 * 80**3"
                if not meep["selected"] else "fresh solver output, when reported"
            ),
            "surface_panel_counts": [
                sum(len(mesh.faces) for mesh in meshes.values()) for meshes in meshes_by_task
            ],
            "dof_policy": (
                "Prefer solver-reported DoF; n_panels_total is a BEM panel-count proxy. "
                "Use the reference Yee-cell proxy only when no fresh Meep file is present."
            ),
        },
    }
    report["metrics"] = log_provenance(logger, report, args.output_dir, solver_parameters)
    report["figures"] = save_figures(report, logger, args, solver_parameters)
    json_path = args.output_dir / "solver_comparison_pilot_report.json"
    markdown_path = args.output_dir / "solver_comparison_pilot_report.md"
    write_json(json_path, report)
    atomic_text(markdown_path, markdown_report(report))
    for path in (json_path, markdown_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Report artifact missing: {path}")
    print(meep["declaration"])
    print(f"Comparison report: {json_path}")
    print(f"Markdown analysis: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
