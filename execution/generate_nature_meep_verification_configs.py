#!/usr/bin/env python3
"""Generate the Nature six-step Meep verification and convergence configurations.

Run from the repository root, for example:

    python execution/generate_nature_meep_verification_configs.py
    python execution/generate_nature_meep_verification_configs.py --max-steps 1

A micro-probe writes only the requested prefix of the twelve-task campaign.
The manifests explicitly distinguish planned tasks from generated tasks.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import inspect
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import textwrap
from collections.abc import Callable, Mapping, Sequence
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from execution.clutch_geometry_redesign import (  # noqa: E402
    compute_dynamic_Trun,
    get_scoped_clutch_elements,
)
from utils.metrics_logger import (  # noqa: E402
    export_macros,
    log_metric,
    log_step,
    set_solver_provenance,
)


JSONDict = dict[str, Any]
TOTAL_TASKS = 12
REL_TOL = 1.0e-10
ABS_TOL = 1.0e-12

COMMON: JSONDict = {
    "solver": "meep",
    "dimensions": 3,
    "z_pad_top_um": -0.115,
    "t_membrane_um": 0.025,
    "t_landing_pad_um": 0.150,
    "aperture_arc_deg": 30.0,
    "bridge_arc_deg": 60.0,
    "tooth_arc_deg": 15.0,
    "num_sectors": 4,
    "nmax": 1,
    "pml_thickness_um": 0.25,
    "courant": 0.3,
    "material": "Gold",
    "force_complex_fields": True,
    "stress_box_mode": "per_tooth_rotor_frame",
}

TASK_SPECS: tuple[JSONDict, ...] = (
    {
        "name": "Step1_SingleTooth_Repulsive_z100_th3",
        "geometry": "SingleTooth_Track0",
        "steps": [1, 2],
        "theta_deg": 3.0,
        "purpose": "Single-tooth open-slot repulsion.",
    },
    {
        "name": "Step1_SingleTooth_AttractivePad_z100_th48",
        "geometry": "SingleTooth_Track0",
        "steps": [1, 2],
        "theta_deg": 48.0,
        "purpose": "Single-tooth landing-pad attraction.",
    },
    {
        "name": "Step1_SingleTooth_OverhangFlip_z055_th3",
        "geometry": "SingleTooth_Track0",
        "steps": [1],
        "theta_deg": 3.0,
        "z_tip_um": -0.055,
        "purpose": "Overhang sign reversal: tooth top is +45 nm above z=0.",
    },
    {
        "name": "Step4_Ctrl_UniformPeriodic_th3_R50",
        "geometry": "Ctrl_UniformPeriodic",
        "steps": [4],
        "theta_deg": 3.0,
        "purpose": "Equal-area/equal-perimeter non-fractal control, disengaged.",
    },
    {
        "name": "Step4_Ctrl_UniformPeriodic_th48_R50",
        "geometry": "Ctrl_UniformPeriodic",
        "steps": [4],
        "theta_deg": 48.0,
        "purpose": "Equal-area/equal-perimeter non-fractal control, engaged.",
    },
    {
        "name": "Step3_4_Cantor_N2_FlatZ_th3_R50",
        "geometry": "Cantor_N2_FlatZ",
        "steps": [3, 4],
        "theta_deg": 3.0,
        "purpose": "Fractal N=2 disengaged repulsion.",
    },
    {
        "name": "Step3_4_Cantor_N2_FlatZ_th48_R50",
        "geometry": "Cantor_N2_FlatZ",
        "steps": [3, 4],
        "theta_deg": 48.0,
        "purpose": "Fractal N=2 engaged clamping.",
    },
    {
        "name": "Step4_5_Cantor_N2_HybridRZ_th3_R50",
        "geometry": "Cantor_N2_HybridRZ",
        "steps": [4, 5],
        "theta_deg": 3.0,
        "purpose": "Optimal coupled (r,z) fractal, disengaged, standard grid.",
    },
    {
        "name": "Step4_5_Cantor_N2_HybridRZ_th48_R50",
        "geometry": "Cantor_N2_HybridRZ",
        "steps": [4, 5],
        "theta_deg": 48.0,
        "purpose": "Optimal coupled (r,z) fractal, engaged, standard grid.",
    },
    {
        "name": "Step5_Rot_C8_Compact_N2_th3_R50",
        "geometry": "Rot_C8_Compact_N2",
        "steps": [5],
        "theta_deg": 3.0,
        "L_domain_um": 2.0,
        "purpose": "Compact peak-force design, disengaged.",
    },
    {
        "name": "Step6_Conv_Cantor_N2_HybridRZ_th3_R40",
        "geometry": "Cantor_N2_HybridRZ",
        "steps": [6],
        "theta_deg": 3.0,
        "resolution": 40,
        "purpose": "Yee-grid convergence coarse tier: dx=25 nm.",
    },
    {
        "name": "Step6_Conv_Cantor_N2_HybridRZ_th3_R60",
        "geometry": "Cantor_N2_HybridRZ",
        "steps": [6],
        "theta_deg": 3.0,
        "resolution": 60,
        "purpose": "Yee-grid convergence fine tier: dx=16.6666667 nm.",
    },
)


def finite_float(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise TypeError(f"{label} must be a real number, not {type(value).__name__}.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"{label} must be a finite real number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} is not finite: {number!r}.")
    if positive and number <= 0.0:
        raise ValueError(f"{label} must be positive; received {number!r}.")
    return number


def normalized_name(name: str) -> str:
    return "".join(character.lower() for character in name if character.isalnum())


def invoke(
    function: Callable[..., Any],
    context: Mapping[str, Any],
    *,
    extra_kwargs: Mapping[str, Any] | None = None,
) -> Any:
    """Bind repository APIs by parameter name without swallowing their errors."""
    signature = inspect.signature(function)
    lookup = {normalized_name(key): value for key, value in context.items()}
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    has_var_kwargs = False
    missing: list[str] = []

    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            has_var_kwargs = True
            continue
        key = normalized_name(parameter.name)
        if key in lookup:
            value = lookup[key]
        elif parameter.default is not inspect.Parameter.empty:
            value = parameter.default
        else:
            missing.append(parameter.name)
            continue

        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[parameter.name] = value

    if missing:
        raise TypeError(
            f"Cannot bind {function.__module__}.{function.__name__}{signature}: "
            f"unsupported required parameters {missing}. "
            "Update the explicit repository API context for this installation."
        )
    if has_var_kwargs and extra_kwargs:
        kwargs.update({key: value for key, value in extra_kwargs.items() if key not in kwargs})
    signature.bind(*args, **kwargs)
    return function(*args, **kwargs)


def make_element(
    r_inner: float,
    r_outer: float,
    level: int,
    ratio: float,
    z_tip: float,
    height: float,
) -> JSONDict:
    width = finite_float(r_outer - r_inner, "slot width", positive=True)
    r_center = 0.5 * (r_inner + r_outer)
    w_tooth = ratio * width
    r_tooth_in = r_center - 0.5 * w_tooth
    r_tooth_out = r_center + 0.5 * w_tooth
    return {
        "r_inner": r_inner,
        "r_outer": r_outer,
        "r_center": r_center,
        "r_tooth_in": r_tooth_in,
        "r_tooth_out": r_tooth_out,
        "W_slot": width,
        "w_tooth": w_tooth,
        "w1_ratio": ratio,
        "level": max(1, level),
        "z_tip": z_tip,
        "h_teeth": height,
        "z_tip_um": z_tip,
        "H_teeth_um": height,
    }


def cantor_elements(
    lower: float,
    upper: float,
    depth: int,
    ratio: float,
    z_tip: float,
    height: float,
) -> list[JSONDict]:
    intervals = [(lower, upper)]
    elements: list[JSONDict] = []
    for level in range(1, depth + 1):
        remaining: list[tuple[float, float]] = []
        for start, stop in intervals:
            third = (stop - start) / 3.0
            left, right = start + third, stop - third
            elements.append(make_element(left, right, level, ratio, z_tip, height))
            remaining.extend(((start, left), (right, stop)))
        intervals = remaining
    return sorted(elements, key=lambda element: element["r_inner"])


def repository_context(config: JSONDict) -> JSONDict:
    context = dict(config)
    context.update(
        {
            "config": config,
            "cfg": config,
            "params": config,
            "parameters": config,
            "settings": config,
            "scope": config["geometry_scope"],
            "geometry": config["geometry_scope"],
            "geometry_name": config["geometry_scope"],
            "geometry_type": config["geometry_scope"],
            "r_min": config["R_min_um"],
            "r_max": config["R_max_um"],
            "r_min_um": config["R_min_um"],
            "r_max_um": config["R_max_um"],
            "R_inner": config["R_min_um"],
            "R_outer": config["R_max_um"],
            "R": (config["R_min_um"], config["R_max_um"]),
            "depth": config["N"],
            "cantor_order": config["N"],
            "z_tip": config["z_tip_um"],
            "h_teeth": config["H_teeth_um"],
            "z_pad_top": config["z_pad_top_um"],
            "L_domain": config["L_domain_um"],
            "pml_thickness": config["pml_thickness_um"],
            "tooth_ratio": config["w1_ratio"],
            "clutch_elements": config["elements"],
            "tracks": config["elements"],
        }
    )
    return context


def extract_elements(result: Any) -> list[Mapping[str, Any]]:
    if isinstance(result, Mapping):
        for key in ("elements", "clutch_elements", "tracks"):
            if key in result:
                result = result[key]
                break
        else:
            if result and all(isinstance(value, Mapping) for value in result.values()):
                result = list(result.values())
    if not isinstance(result, Sequence) or isinstance(result, (str, bytes)):
        raise TypeError("get_scoped_clutch_elements must return a sequence of elements.")
    if not result:
        raise ValueError("get_scoped_clutch_elements returned no elements.")
    elements: list[Mapping[str, Any]] = []
    for element in result:
        if dataclasses.is_dataclass(element) and not isinstance(element, type):
            element = dataclasses.asdict(element)
        if not isinstance(element, Mapping):
            raise TypeError("Each scoped clutch element must be a mapping or dataclass.")
        elements.append(element)
    return elements


def element_value(element: Mapping[str, Any], *names: str) -> float:
    lookup = {normalized_name(key): value for key, value in element.items()}
    for name in names:
        key = normalized_name(name)
        if key in lookup:
            return finite_float(lookup[key], name)
    raise ValueError(f"Scoped element is missing {names[0]!r}: {dict(element)!r}")


def verify_scoped_elements(config: JSONDict) -> None:
    """Verify the imported generator agrees with the requested Cantor construction."""
    result = get_scoped_clutch_elements(
        N=int(config["N"]),
        R_min=float(config["R_min_um"]),
        R_max=float(config["R_max_um"]),
        w1_ratio=float(config["w1_ratio"]),
        min_tooth_w=0.020,
    )
    scoped = extract_elements(result)
    scoped.sort(key=lambda element: element_value(element, "r_inner", "r_inner_um"))
    expected = config["elements"]
    if len(scoped) != len(expected):
        raise ValueError(
            f"{config['name']}: expected {len(expected)} tracks, "
            f"but get_scoped_clutch_elements returned {len(scoped)}."
        )
    for index, (actual, target) in enumerate(zip(scoped, expected, strict=True)):
        for field, aliases in (
            ("r_inner", ("r_inner", "r_inner_um")),
            ("r_outer", ("r_outer", "r_outer_um")),
            ("w_tooth", ("w_tooth", "w_tooth_um")),
        ):
            actual_value = element_value(actual, *aliases)
            if not math.isclose(
                actual_value, target[field], rel_tol=REL_TOL, abs_tol=ABS_TOL
            ):
                raise ValueError(
                    f"{config['name']}, track {index}: repository {field}="
                    f"{actual_value} differs from required {target[field]}."
                )


def build_config(task_id: int, spec: JSONDict) -> JSONDict:
    geometry = str(spec["geometry"])
    compact = geometry == "Rot_C8_Compact_N2"
    single = geometry == "SingleTooth_Track0"
    control = geometry == "Ctrl_UniformPeriodic"
    lower, upper = (0.20, 0.90) if compact else (0.30, 1.35)
    ratio = 0.45 if compact else 0.65
    z_tip = float(spec.get("z_tip_um", -0.100))
    height = 0.100
    depth = 1 if single else 2

    config: JSONDict = {
        **COMMON,
        "task_id": task_id,
        "name": spec["name"],
        "geometry_scope": geometry,
        "narrative_steps": spec["steps"],
        "purpose": spec["purpose"],
        "N": depth,
        "w1_ratio": ratio,
        "R_min_um": lower,
        "R_max_um": upper,
        "theta_deg": spec["theta_deg"],
        "z_tip_um": z_tip,
        "H_teeth_um": height,
        "L_domain_um": spec.get("L_domain_um", 3.0),
        "resolution": spec.get("resolution", 50),
    }

    if control:
        slot_width = 0.19444444444444445
        wall_width = 0.11666666666666665
        elements = [
            make_element(
                lower + wall_width + index * (slot_width + wall_width),
                lower + wall_width + index * (slot_width + wall_width) + slot_width,
                2,
                ratio,
                z_tip,
                height,
            )
            for index in range(3)
        ]
        config.update(
            {
                "N": 0,
                "M": 3,
                "slot_distribution": "uniform_periodic",
                "total_slot_width_um": 0.5833333333333334,
                "metal_wall_width_um": wall_width,
                "W_slot_um": slot_width,
                "w_tooth_um": 0.1263888888888889,
            }
        )
    else:
        elements = cantor_elements(lower, upper, depth, ratio, z_tip, height)
        config["slot_distribution"] = "cantor"
        if single:
            elements = [make_element(0.65, 1.00, 1, ratio, z_tip, height)]
            elements[0]["W_slot"] = 0.35
            elements[0]["w_tooth"] = 0.2275

    for track_id, element in enumerate(elements):
        element["track_id"] = track_id
    config["geometry"] = elements
    config["elements"] = elements
    config["N_fractal"] = max(1, int(config["N"]))

    if not control:
        verify_scoped_elements(config)

    if geometry == "Cantor_N2_HybridRZ":
        for element in elements:
            if element["level"] == 1:
                element.update(
                    {
                        "z_tip": -0.110,
                        "z_tip_um": -0.110,
                        "h_teeth": 0.110,
                        "H_teeth_um": 0.110,
                    }
                )

    config["moments_per_config"] = 36 * len(elements)
    config["total_moments"] = 144 * len(elements)
    config["dx_nm"] = 1000.0 / config["resolution"]
    config["total_slot_width_um"] = math.fsum(element["W_slot"] for element in elements)
    return config


def return_tuple_names(function: Callable[..., Any], length: int) -> list[str] | None:
    """Recover named tuple-return expressions, avoiding assumed numerical ordering."""
    try:
        source = textwrap.dedent(inspect.getsource(function))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError, IndentationError):
        return None

    candidates: set[tuple[str, ...]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, (ast.Tuple, ast.List)):
            items = node.value.elts
            if len(items) == length and all(isinstance(item, ast.Name) for item in items):
                candidates.add(tuple(item.id for item in items if isinstance(item, ast.Name)))
    if len(candidates) == 1:
        return list(next(iter(candidates)))
    return None


def dynamic_results(result: Any) -> JSONDict:
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        result = dataclasses.asdict(result)
    if hasattr(result, "_asdict") and callable(result._asdict):
        result = result._asdict()
    if isinstance(result, Mapping):
        return dict(result)
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        if len(result) == 2 and isinstance(result[1], Mapping):
            return {**dict(result[1]), "T_run": result[0]}
        names = return_tuple_names(compute_dynamic_Trun, len(result))
        if names is not None:
            return dict(zip(names, result, strict=True))
        if len(result) == 2:
            return {"T_run": result[0], "Sigma": result[1]}
        raise TypeError(
            "compute_dynamic_Trun returned an ambiguous sequence. Return a mapping "
            "with d_eff_um, T_run, and Sigma, or a tuple of named local variables."
        )
    return {"T_run": finite_float(result, "compute_dynamic_Trun result", positive=True)}


def compute_run_parameters(config: JSONDict) -> None:
    elements = config["elements"]
    if not elements:
        raise ValueError(f"{config['name']}: empty geometry.")

    clearances: list[float] = []
    for element in elements:
        clearances.extend(
            (
                finite_float(
                    element["z_tip"] - config["z_pad_top_um"],
                    "tooth/landing-pad clearance",
                    positive=True,
                ),
                finite_float(
                    (element["W_slot"] - element["w_tooth"]) / 2.0,
                    "radial side clearance",
                    positive=True,
                ),
            )
        )
    config["d_eff_um"] = min(clearances)
    config["d_eff_definition"] = (
        "Minimum tooth-tip/landing-pad and centered radial side clearance."
    )

    run_time, diagnostics = compute_dynamic_Trun(float(config["d_eff_um"]))
    if not isinstance(diagnostics, Mapping):
        raise TypeError("compute_dynamic_Trun diagnostics must be a mapping.")
    if "Sigma" not in diagnostics:
        raise ValueError(
            f"compute_dynamic_Trun did not return Sigma for {config['name']}; "
            f"returned keys: {list(diagnostics)}."
        )
    config["T_run"] = finite_float(run_time, "T_run", positive=True)
    config["Sigma"] = finite_float(diagnostics["Sigma"], "Sigma", positive=True)
    config["dynamic_run_parameter_source"] = (
        "execution.clutch_geometry_redesign.compute_dynamic_Trun"
    )


def log_configuration(
    config: JSONDict, provenance: JSONDict | None = None
) -> None:
    prefix = f"NatureMeepTask{config['task_id']:03d}"
    for field, unit in (
        ("d_eff_um", "um"),
        ("T_run", "Meep time units"),
        ("Sigma", "Meep units"),
        ("resolution", "pixels/um"),
        ("dx_nm", "nm"),
        ("moments_per_config", "moments"),
        ("total_moments", "moments"),
    ):
        name = f"{prefix}_{field}"
        log_metric(
            name,
            config[field],
            step_id="nature_meep_verification",
            solver_name="meep",
            solver_parameters=provenance,
        )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def markdown_manifest(manifest: JSONDict) -> str:
    lines = [
        "# Nature six-step Meep verification campaign",
        "",
        "- Target: BigRed 200; 3D Meep FDTD.",
        f"- Configuration directory: `{manifest['output_dir']}`.",
        f"- Generated: {manifest['generated_count']} / {TOTAL_TASKS} planned tasks.",
        f"- Complete campaign: {'yes' if manifest['complete_campaign'] else 'no (micro-probe)'}.",
        f"- Sum of moments_per_config: {manifest['sum_moments_per_config']}.",
        f"- Sum of total_moments: {manifest['sum_total_moments']}.",
        "",
        "All lengths are in micrometers unless otherwise indicated. "
        "Track elements are sorted by increasing r_inner.",
        "",
        "| Task | Configuration | Steps | Tracks | θ (deg) | R (px/µm) | "
        "dx (nm) | d_eff (µm) | T_run | Sigma | Moments/config | Total moments |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for config in manifest["configurations"]:
        steps = ", ".join(str(step) for step in config["narrative_steps"])
        lines.append(
            f"| {config['task_id']} | `{config['name']}` | {steps} | "
            f"{len(config['elements'])} | {config['theta_deg']:g} | "
            f"{config['resolution']} | {config['dx_nm']:.6g} | "
            f"{config['d_eff_um']:.9g} | {config['T_run']:.9g} | "
            f"{config['Sigma']:.9g} | {config['moments_per_config']} | "
            f"{config['total_moments']} |"
        )
    lines.extend(
        [
            "",
            "## Verification comparisons",
            "",
            "- Tasks 1–2: open-slot repulsion versus landing-pad attraction.",
            "- Tasks 1 and 3: overhang-induced force-sign reversal.",
            "- Tasks 4–7: equal-total-slot-width uniform control versus N=2 Cantor.",
            "- Tasks 6–9: flat-z versus coupled (r,z) geometry.",
            "- Task 10: compact-envelope peak-force design.",
            "- Tasks 11, 8, and 12: identical disengaged hybrid geometry at "
            "R=40, 50, and 60.",
            "",
            "No FDTD simulations are executed by this generator.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("sweep_configs_nature_meep_verification"),
        help="Directory for config_001.json through config_012.json.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory for JSON/Markdown manifests and exported metric macros.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=TOTAL_TASKS,
        help="Generate the first N tasks for a micro-probe (1 through 12).",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.max_steps <= TOTAL_TASKS:
        parser.error("--max-steps must be an integer from 1 through 12.")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    output_dir = args.output_dir.expanduser().resolve()
    results_dir = args.results_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    provenance: JSONDict = {
        "solver": "meep",
        "solver_name": "Meep",
        "backend": "meep",
        "method": "3D FDTD",
        "dimensions": 3,
        "platform": "BigRed 200",
        "hardware": "BigRed 200",
        "generator": "execution/generate_nature_meep_verification_configs.py",
        "simulation_executed": False,
    }
    set_solver_provenance("meep", provenance)

    message = f"Generate Nature Meep verification configurations ({args.max_steps}/12)"
    log_step(
        "nature_meep_verification",
        {
            "message": message,
            "max_steps": args.max_steps,
            "planned_tasks": TOTAL_TASKS,
        },
        solver_name="meep",
        solver_parameters=provenance,
    )

    configurations: list[JSONDict] = []
    # Validate and compute the entire requested prefix before publishing configs.
    for task_id, spec in enumerate(TASK_SPECS[: args.max_steps], start=1):
        config = build_config(task_id, spec)
        compute_run_parameters(config)
        json_text(config)
        configurations.append(config)

    for config in configurations:
        filename = f"config_{config['task_id']:03d}.json"
        config["config_file"] = filename
        atomic_write(output_dir / filename, json_text(config))
        log_configuration(config, provenance)

    # Prevent stale suffix files from making a micro-probe look like a full run.
    for task_id in range(args.max_steps + 1, TOTAL_TASKS + 1):
        (output_dir / f"config_{task_id:03d}.json").unlink(missing_ok=True)

    manifest: JSONDict = {
        "schema_version": 1,
        "campaign": "nature_meep_verification",
        "provenance": provenance,
        "output_dir": str(output_dir),
        "planned_count": TOTAL_TASKS,
        "generated_count": len(configurations),
        "complete_campaign": len(configurations) == TOTAL_TASKS,
        "planned_tasks": [
            {"task_id": task_id, "name": spec["name"]}
            for task_id, spec in enumerate(TASK_SPECS, start=1)
        ],
        "common_parameters": COMMON,
        "sum_moments_per_config": sum(
            config["moments_per_config"] for config in configurations
        ),
        "sum_total_moments": sum(config["total_moments"] for config in configurations),
        "configurations": configurations,
    }
    atomic_write(
        results_dir / "nature_meep_verification_manifest.json",
        json_text(manifest),
    )
    atomic_write(
        results_dir / "nature_meep_verification_manifest.md",
        markdown_manifest(manifest),
    )

    macro_path = results_dir / "nature_meep_verification_macros.tex"
    export_macros(output_path=str(macro_path))
    export_macros()
    print(
        f"Generated {len(configurations)}/{TOTAL_TASKS} configurations in "
        f"{output_dir}; manifests written to {results_dir}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
