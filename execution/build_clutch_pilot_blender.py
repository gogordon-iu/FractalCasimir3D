#!/usr/bin/env python3
"""Build Blender clutch visualizations and assemble their audited diagnostic figure.

Blender:
    blender --background --python execution/build_clutch_pilot_blender.py -- \
        --mode blender

Python:
    python execution/build_clutch_pilot_blender.py
    python execution/build_clutch_pilot_blender.py --max-steps 5 --skip-blender

OBJ coordinates are preserved; no scientific geometry or gap dimensions are changed.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

LOGGER = logging.getLogger("clutch_pilot")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

OVERVIEW_RENDERS = (
    "render_th0_topdown_voxels.png",
    "render_th0_isometric_voxels.png",
    "render_th45_topdown_voxels.png",
    "render_th45_isometric_voxels.png",
)
GAP_RENDER = "render_gap_cross_section_voxels.png"
ALL_RENDERS = (*OVERVIEW_RENDERS, GAP_RENDER)

PANEL_TITLES = (
    "A  |  θ = 0° — Sector 0 / top-down",
    "B  |  θ = 0° — three-quarter overview",
    "C  |  θ = 45° — Sector 0 / top-down",
    "D  |  θ = 45° — three-quarter overview",
)
PANEL_CAPTIONS = (
    "Emerald Sector 0 teeth; magenta stress envelope; gold stator bands.",
    "Studio-lit overview of the unrotated voxel geometry.",
    "Rotated Sector 0 teeth and stress envelope over the bronze landing pad.",
    "Studio-lit overview of the rotated voxel geometry.",
)


def positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def nonnegative_int(value: str) -> int:
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return result


def parse_arguments() -> argparse.Namespace:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("python", "blender"), default="python")
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--blender", default=os.environ.get("BLENDER_BIN", "blender"))
    parser.add_argument("--skip-blender", action="store_true")
    parser.add_argument("--force", action="store_true", help="Regenerate all renders.")
    parser.add_argument("--max-steps", type=nonnegative_int, default=0)
    parser.add_argument("--samples", type=positive_int, default=96)
    parser.add_argument("--resolution-percentage", type=positive_int, default=100)
    parser.add_argument("--dpi", type=positive_int, default=240)
    parser.add_argument("--blender-timeout", type=positive_int, default=3600)
    # Blender's arguments precede "--"; only parse this script's arguments.
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    if args.resolution_percentage > 100:
        parser.error("--resolution-percentage must be between 1 and 100")
    args.project_root = args.project_root.expanduser().resolve()
    return args


def load_json_object(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> Any:
        raise ValueError(f"Non-finite JSON number: {value}")

    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, parse_constant=reject_constant)
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{path} must contain a nonempty JSON object")
    return value


def flatten_audit(value: Mapping[str, Any]) -> dict[str, Any]:
    """Use JSON-pointer keys so nested keys remain exact and unambiguous."""
    leaves: dict[str, Any] = {}

    def escape(key: str) -> str:
        return key.replace("~", "~0").replace("/", "~1")

    def walk(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            if not node:
                leaves[pointer] = {}
            for key, child in node.items():
                if not isinstance(key, str):
                    raise TypeError("JSON object keys must be strings")
                walk(child, f"{pointer}/{escape(key)}")
        elif isinstance(node, list):
            if not node:
                leaves[pointer] = []
            for index, child in enumerate(node):
                walk(child, f"{pointer}/{index}")
        elif node is None or isinstance(node, (str, bool, int, float)):
            if isinstance(node, float) and not math.isfinite(node):
                raise ValueError(f"Non-finite audit value at {pointer}")
            leaves[pointer] = node
        else:
            raise TypeError(f"Unsupported audit value at {pointer}: {type(node)!r}")

    walk(dict(value), "")
    if not leaves:
        raise ValueError("The audit contains no values")
    return leaves


def valid_png(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        return handle.read(8) == PNG_SIGNATURE


def atomic_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".json", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def invoke_provenance_helper(
    helper: Callable[..., Any],
    plot: Path,
    root: Path,
    audit: Mapping[str, Any],
    leaves: Mapping[str, Any],
) -> None:
    """Adapt common metrics_logger signatures without silently dropping linkage."""
    audit_path = root / "results_voxel_visualization/clutch_pilot_voxel_audit.json"
    metrics_path = root / "results/provenance_metrics.json"
    metadata = {
        "script": "execution/build_clutch_pilot_blender.py",
        "audit_path": str(audit_path),
        "metrics_path": str(metrics_path),
        "metric_key_format": "RFC 6901 JSON Pointer into the voxel audit",
        "metric_keys": list(leaves),
        "audit_values": dict(leaves),
        "artifact_exists": plot.is_file(),
    }
    aliases: dict[str, Any] = {}
    for name in (
        "plot_path", "figure_path", "fig_path", "image_path", "output_path",
        "plot_file", "figure_file", "plot_filename", "filename",
    ):
        aliases[name] = str(plot)
    for name in (
        "metrics_path", "metrics_file", "metrics_json_path", "metrics_json",
        "provenance_path", "provenance_file", "provenance_json_path", "data_source",
    ):
        aliases[name] = str(metrics_path)
    for name in ("metric_keys", "metrics_keys", "metric_names", "keys", "columns_used"):
        aliases[name] = list(leaves)
    for name in ("metrics", "metrics_dict", "metric_values", "audit_metrics"):
        aliases[name] = dict(leaves)
    for name in ("metadata", "extra", "extra_metadata", "provenance", "details"):
        aliases[name] = metadata
    for name in ("script", "script_name", "source_script", "script_path"):
        aliases[name] = "execution/build_clutch_pilot_blender.py"
    for name in ("audit_path", "audit_file", "source_path", "source_file"):
        aliases[name] = str(audit_path)
    aliases["audit"] = dict(audit)

    signature = inspect.signature(helper)
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    has_var_keyword = False
    has_concrete_parameter = False
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
            continue
        has_concrete_parameter = True
        if parameter.name in aliases:
            value = aliases[parameter.name]
        elif parameter.default is not inspect.Parameter.empty:
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                positional.append(parameter.default)
            continue
        else:
            raise TypeError(
                "Unsupported required save_plot_provenance parameter "
                f"{parameter.name!r}; signature is {signature}"
            )
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keyword[parameter.name] = value

    if has_var_keyword:
        for name, value in {
            "plot_path": str(plot),
            "metrics_path": str(metrics_path),
            "metric_keys": list(leaves),
            "metadata": metadata,
        }.items():
            if name not in signature.parameters:
                keyword[name] = value
    if not has_concrete_parameter and not has_var_keyword:
        positional = [str(plot), list(leaves), str(metrics_path)]
    helper(*positional, **keyword)


def log_provenance(
    root: Path, audit: Mapping[str, Any], plots: Sequence[Path]
) -> None:
    leaves = flatten_audit(audit)
    root_string = str(root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)
    module = importlib.import_module("utils.metrics_logger")
    helper = getattr(module, "save_plot_provenance", None)
    if not callable(helper):
        raise TypeError("utils.metrics_logger.save_plot_provenance must be callable")

    manifest_path = (
        root / "results_voxel_visualization/clutch_pilot_plot_provenance.json"
    )
    manifest = load_json_object(manifest_path) if manifest_path.exists() else {}
    records = manifest.setdefault("artifacts", {})
    if not isinstance(records, dict):
        raise ValueError(f"Invalid artifacts mapping in {manifest_path}")
    for plot in dict.fromkeys(plots):
        invoke_provenance_helper(helper, plot, root, audit, leaves)
        try:
            artifact = plot.relative_to(root).as_posix()
        except ValueError:
            artifact = str(plot)
        records[artifact] = {
            "exists": plot.is_file(),
            "audit": "results_voxel_visualization/clutch_pilot_voxel_audit.json",
            "metrics": "results/provenance_metrics.json",
            "metric_key_format": "RFC 6901 JSON Pointer into the voxel audit",
            "metric_keys": list(leaves),
            "audit_values": dict(leaves),
        }
        LOGGER.info("Logged provenance: %s", artifact)
    atomic_json(manifest_path, manifest)


def self_check(root: Path, max_steps: int) -> None:
    directory = root / "results_voxel_visualization"
    for filename in ("clutch_pilot_th0_voxels.obj", "clutch_pilot_th45_voxels.obj"):
        path = directory / filename
        if not path.exists():
            LOGGER.warning("Self-check: optional input not yet present: %s", path)
            continue
        checked = 0
        with path.open("r", encoding="utf-8", errors="strict") as handle:
            for line in handle:
                parts = line.split()
                if not parts or parts[0] != "v":
                    continue
                if len(parts) < 4:
                    raise ValueError(f"Malformed OBJ vertex in {path}")
                coordinates = [float(component) for component in parts[1:4]]
                if not all(math.isfinite(component) for component in coordinates):
                    raise ValueError(f"Non-finite OBJ vertex in {path}")
                checked += 1
                if checked >= max(1, max_steps):
                    break
        if checked == 0:
            raise ValueError(f"No OBJ vertices found in {path}")
        LOGGER.info("Self-check: validated %d vertices from %s", checked, filename)
    for filename in ALL_RENDERS:
        path = directory / filename
        if path.exists() and not valid_png(path):
            raise ValueError(f"Invalid PNG signature: {path}")
    LOGGER.info("Fast self-check passed")


def build_blender(args: argparse.Namespace) -> None:
    try:
        import bpy
        from mathutils import Vector
    except ImportError as exc:
        raise RuntimeError("--mode blender must run inside Blender") from exc

    if bpy.app.version < (4, 5, 0):
        raise RuntimeError(f"Blender 4.5+ required; found {bpy.app.version_string}")

    directory = args.project_root / "results_voxel_visualization"
    directory.mkdir(parents=True, exist_ok=True)
    for angle in ("0", "45"):
        source = directory / f"clutch_pilot_th{angle}_voxels.obj"
        if not source.is_file() or source.stat().st_size == 0:
            raise FileNotFoundError(f"Missing or empty OBJ: {source}")

    def material(
        name: str,
        color: tuple[float, float, float],
        metallic: float,
        roughness: float,
        alpha: float = 1.0,
        emission: float = 0.0,
    ) -> Any:
        result = bpy.data.materials.new(name)
        result.use_nodes = True
        result.diffuse_color = (*color, alpha)
        nodes = result.node_tree.nodes
        shader = nodes.get("Principled BSDF")
        if shader is None:
            raise RuntimeError("Blender did not create a Principled BSDF node")
        shader.inputs["Base Color"].default_value = (*color, 1.0)
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Alpha"].default_value = alpha
        shader.inputs["Emission Color"].default_value = (*color, 1.0)
        shader.inputs["Emission Strength"].default_value = emission
        if alpha < 1.0:
            result.surface_render_method = "DITHERED"
            result.use_transparency_overlap = False
        return result

    def aim(obj: Any, target: tuple[float, float, float]) -> None:
        delta = Vector(target) - obj.location
        if delta.length <= 1e-12:
            raise ValueError(f"Degenerate camera/light direction for {obj.name}")
        obj.rotation_euler = delta.to_track_quat("-Z", "Y").to_euler()

    def light(
        name: str,
        kind: str,
        location: tuple[float, float, float],
        energy: float,
        color: tuple[float, float, float],
        size: float = 3.0,
    ) -> None:
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = color
        if kind == "AREA":
            data.shape = "DISK"
            data.size = size
        elif kind == "SUN":
            data.angle = math.radians(12.0)
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = location
        aim(obj, (0.2, 0.2, 0.02))

    def camera(
        name: str,
        location: tuple[float, float, float],
        target: tuple[float, float, float],
        ortho_scale: float | None = None,
    ) -> Any:
        data = bpy.data.cameras.new(name)
        data.clip_start = 0.00001
        data.clip_end = 1000.0
        data.lens = 48.0
        if ortho_scale is not None:
            data.type = "ORTHO"
            data.ortho_scale = ortho_scale
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = location
        aim(obj, target)
        return obj

    for angle in ("0", "45"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = args.resolution_percentage
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.image_settings.color_depth = "8"
        scene.render.film_transparent = False
        scene.render.use_file_extension = True
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = args.samples
        if hasattr(scene.render, "engine"):
            scene["requested_render_samples"] = args.samples
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.exposure = -0.25
        scene.view_settings.gamma = 1.0
        scene.unit_settings.system = "NONE"
        scene["geometry_policy"] = "Original OBJ coordinates preserved without scaling"
        scene["gap_annotation_policy"] = "Gap dimensions must come from voxel audit"

        world = bpy.data.worlds.new("Clutch_Studio_World")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs["Color"].default_value = (
            0.14, 0.16, 0.20, 1.0
        )
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.2
        scene.world = world

        bpy.ops.wm.obj_import(
            filepath=str(directory / f"clutch_pilot_th{angle}_voxels.obj"),
            forward_axis="NEGATIVE_Y",
            up_axis="Z",
            use_split_objects=True,
            use_split_groups=True,
            validate_meshes=True,
        )
        meshes = [obj for obj in scene.objects if obj.type == "MESH"]
        if not meshes:
            raise ValueError(f"No meshes imported for θ={angle}")

        specifications = (
            ("Stator_Membrane", (0.88, 0.68, 0.22), 0.35, 0.35, 1.0, 0.0),
            ("Stator_Landing_Pad", (0.55, 0.40, 0.14), 0.35, 0.45, 1.0, 0.0),
            ("Rotor_Teeth_Sector0", (0.10, 0.92, 0.55), 0.8, 0.15, 1.0, 0.35),
            ("Rotor_Teeth_Other", (0.35, 0.48, 0.68), 1.0, 0.25, 1.0, 0.0),
            ("Stress_Box_Envelope", (1.0, 0.18, 0.55), 0.0, 0.3, 1.0, 3.0),
            ("Zmin_Integration_Sheet", (0.15, 0.85, 1.0), 0.0, 0.3, 0.45, 0.85),
        )
        materials = {
            name: material(name, color, metallic, roughness, alpha, emission)
            for name, color, metallic, roughness, alpha, emission in specifications
        }
        fallback = material("Unclassified_Voxel", (0.45, 0.49, 0.55), 0.4, 0.35)
        counts = dict.fromkeys(materials, 0)
        for obj in meshes:
            matched = next(
                (name for name in materials if name.lower() in obj.name.lower()),
                None,
            )
            obj.data.materials.clear()
            obj.data.materials.append(materials[matched] if matched else fallback)
            for polygon in obj.data.polygons:
                polygon.material_index = 0
                polygon.use_smooth = False
            if matched is not None:
                counts[matched] += 1
            else:
                LOGGER.warning("Unclassified OBJ group: %s", obj.name)
            if matched == "Stress_Box_Envelope":
                obj.display_type = "WIRE"
                obj.show_wire = True
                obj.show_all_edges = True
                # Viewport wire display alone does not render wire geometry.
                wire = obj.modifiers.new("Render_Stress_Envelope_Wire", "WIREFRAME")
                wire.thickness = 0.018
                wire.use_replace = True
                wire.use_even_offset = True
                wire.show_viewport = False
                wire.show_render = True

        for name, count in counts.items():
            if count == 0:
                raise ValueError(
                    f"OBJ θ={angle} lacks required name substring {name!r}"
                )

        light("Sun", "SUN", (1.0, -2.0, 4.0), 2.2, (1.0, 0.93, 0.80))
        light("Key", "AREA", (1.5, -1.7, 3.0), 12.0, (1.0, 0.90, 0.75))
        light("Fill", "AREA", (-2.0, 1.0, 2.0), 8.0, (0.65, 0.82, 1.0))
        light("Underside", "AREA", (0.4, 0.2, -1.5), 6.0, (0.45, 0.80, 1.0), 2.0)
        light("Rim", "AREA", (1.0, 2.0, 2.5), 10.0, (1.0, 0.65, 0.40), 2.0)

        top = camera(
            "Camera_Topdown", (0.65, 0.55, 2.5), (0.65, 0.55, 0.0), 1.9
        )
        # Explicitly fix roll to keep world +Y at the top of the image.
        top.rotation_euler = (0.0, 0.0, 0.0)
        iso = camera(
            "Camera_Isometric", (2.4, -2.2, 1.6), (0.2, 0.2, 0.05)
        )
        jobs = [
            (top, f"render_th{angle}_topdown_voxels.png"),
            (iso, f"render_th{angle}_isometric_voxels.png"),
        ]
        if angle == "0":
            gap = camera(
                "Camera_Gap_Cross_Section",
                (0.82, -0.35, 0.06),
                (0.82, 0.21, 0.06),
                0.95,
            )
            gap.data.clip_start = 0.53
            jobs.append((gap, GAP_RENDER))

        scene.camera = top
        blend_path = directory / f"clutch_pilot_th{angle}_scene.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        for active_camera, filename in jobs:
            scene.camera = active_camera
            scene.render.filepath = str(directory / filename)
            LOGGER.info("Rendering θ=%s: %s", angle, filename)
            bpy.ops.render.render(write_still=True)
            if not valid_png(directory / filename):
                raise RuntimeError(f"Blender failed to produce a valid PNG: {filename}")
        scene.camera = top
        scene.render.filepath = str(directory / f"render_th{angle}_topdown_voxels.png")
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))


def run_blender(args: argparse.Namespace) -> None:
    executable = shutil.which(args.blender)
    if executable is None:
        candidate = Path(args.blender).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            executable = str(candidate.resolve())
    if executable is None:
        raise FileNotFoundError(
            "Blender executable not found. Supply --blender /path/to/blender "
            "or set BLENDER_BIN."
        )
    samples = args.samples
    if args.max_steps > 0:
        samples = min(samples, args.max_steps)
    command = [
        executable,
        "--background",
        "--python-exit-code", "1",
        "--python", str(Path(__file__).resolve()),
        "--",
        "--mode", "blender",
        "--project-root", str(args.project_root),
        "--samples", str(samples),
        "--resolution-percentage", str(args.resolution_percentage),
    ]
    LOGGER.info("Invoking Blender: %s", " ".join(command))
    subprocess.run(
        command,
        cwd=args.project_root,
        check=True,
        timeout=args.blender_timeout,
    )


def compose_figure(
    root: Path, audit: Mapping[str, Any], dpi: int
) -> tuple[Path, Path]:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    directory = root / "results_voxel_visualization"
    leaves = flatten_audit(audit)
    configs = audit.get("configs")
    if not isinstance(configs, list) or len(configs) < 2:
        raise ValueError("The voxel audit must contain at least two configs")
    metrics: list[Mapping[str, Any]] = []
    for index in range(2):
        config = configs[index]
        if not isinstance(config, Mapping) or not isinstance(
            config.get("metrics"), Mapping
        ):
            raise ValueError(f"Audit configs[{index}].metrics must be an object")
        metrics.append(config["metrics"])

    summary_fields = (
        ("dx_nm", "Voxel pitch (nm)"),
        ("z_tip_nm", "Tooth tip z (nm)"),
        ("gap_in_voxels", "Gap (voxels)"),
        ("zmin_in_voxels", "Integration zmin (voxels)"),
        (
            "pure_vacuum_z_planes_with_clear_1_voxel_buffer_from_both",
            "Vacuum planes (1-voxel buffers)",
        ),
        ("sector0_teeth_exact_area_um2", "Sector 0 tooth area (µm²)"),
        ("stress_box_zmin_area_um2", "Stress box zmin area (µm²)"),
        ("box_to_tooth_area_ratio", "Box / tooth area ratio"),
        ("box_empty_area_fraction", "Box empty area fraction"),
        ("stator_metal_fraction_under_box", "Metal fraction under box"),
        ("stator_metal_area_under_box_um2", "Metal area under box (µm²)"),
        ("Rotor_Teeth_Sector0_voxel_count", "Sector 0 tooth voxel count"),
    )
    summary_rows: list[tuple[str, str, str]] = []
    for key, label in summary_fields:
        values: list[str] = []
        for index, config_metrics in enumerate(metrics):
            if key not in config_metrics:
                raise ValueError(f"Missing audit metric: configs[{index}].metrics.{key}")
            value = config_metrics[key]
            if value is None or isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                raise ValueError(
                    f"Audit configs[{index}].metrics.{key} must be a finite number"
                )
            values.append(json.dumps(value, ensure_ascii=False, allow_nan=False))
        summary_rows.append((label, values[0], values[1]))

    label_width = max(len(row[0]) for row in summary_rows)
    value_widths = [
        max(len(header), *(len(row[column]) for row in summary_rows))
        for column, header in ((1, "θ = 0°"), (2, "θ = 45°"))
    ]

    def summary_line(label: str, first: str, second: str) -> str:
        return (
            f"{label:<{label_width}}  "
            f"{first:>{value_widths[0]}}  {second:>{value_widths[1]}}"
        )

    header = summary_line("Metric", "θ = 0°", "θ = 45°")
    # Exactly 18 lines; full audit values remain in PNG metadata and provenance.
    summary_lines = [
        "Exact voxel audit",
        "Source: clutch_pilot_voxel_audit.json",
        "",
        header,
        "─" * len(header),
        *(summary_line(*row) for row in summary_rows),
        "Values copied from configs[0/1].metrics; no rounding.",
    ]

    width, height = 16.0, 14.0
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi <= 0:
        raise ValueError("dpi must be a positive integer")
    if max(width, height) * dpi > 65000:
        raise ValueError("Figure exceeds PNG renderer limits; reduce --dpi.")

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "figure.facecolor": "#f7f8fb",
            "savefig.facecolor": "#f7f8fb",
        }
    ):
        figure = plt.figure(figsize=(width, height))
        try:
            grid = figure.add_gridspec(
                3, 2,
                height_ratios=(1.0, 1.0, 1.0),
                left=0.035, right=0.965, bottom=0.055, top=0.925,
                wspace=0.09, hspace=0.30,
            )
            figure.suptitle(
                "Clutch pilot — voxel geometry and exact audit",
                fontsize=20, fontweight="bold", y=0.975,
            )
            for index, filename in enumerate(ALL_RENDERS):
                path = directory / filename
                if not valid_png(path):
                    raise FileNotFoundError(f"Missing or invalid render: {path}")
                with Image.open(path) as image:
                    image.load()
                    pixels = np.asarray(image.convert("RGB"))
                if pixels.size == 0:
                    raise ValueError(f"Empty render: {path}")
                axis = figure.add_subplot(grid[index // 2, index % 2])
                axis.imshow(pixels)
                axis.set_axis_off()
                if index < len(OVERVIEW_RENDERS):
                    title = PANEL_TITLES[index]
                    caption = PANEL_CAPTIONS[index]
                else:
                    title = (
                        "E  |  Sub-Voxel Gap Cross-Section\n"
                        "(z_tip = 15 nm = 0.90 voxels)"
                    )
                    caption = (
                        "Sector 0 teeth above the stator; cyan integration sheet "
                        "inside the gap."
                    )
                axis.set_title(
                    title, loc="left", fontsize=12,
                    fontweight="bold", pad=9,
                )
                axis.text(
                    0.0, -0.055, caption,
                    transform=axis.transAxes,
                    fontsize=8.5, color="#253044", va="top",
                )

            summary_axis = figure.add_subplot(grid[2, 1])
            summary_axis.set_axis_off()
            summary_axis.set_title(
                "F  |  Key exact metrics", loc="left",
                fontsize=12, fontweight="bold", pad=9,
            )
            summary_text = summary_axis.text(
                0.0, 0.98, "\n".join(summary_lines),
                transform=summary_axis.transAxes,
                va="top", ha="left",
                fontsize=9.0, family="DejaVu Sans Mono",
                color="#172033", linespacing=1.4,
            )
            # Fit exact numeric strings without truncation or extra figure rows.
            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            text_box = summary_text.get_window_extent(renderer)
            axis_box = summary_axis.get_window_extent(renderer)
            fit = min(
                1.0,
                axis_box.width / max(text_box.width, 1.0),
                0.96 * axis_box.height / max(text_box.height, 1.0),
            )
            summary_text.set_fontsize(summary_text.get_fontsize() * fit)

            primary = root / "figures/fig_clutch_pilot_voxel_audit.png"
            secondary = directory / "fig_clutch_pilot_voxel_audit.png"
            primary.parent.mkdir(parents=True, exist_ok=True)
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=primary.parent, suffix=".png", delete=False
                ) as handle:
                    temporary = Path(handle.name)
                figure.savefig(
                    temporary, format="png", dpi=dpi,
                    metadata={
                        "Title": "Clutch pilot voxel audit",
                        "Description": json.dumps(
                            {
                                "audit": "clutch_pilot_voxel_audit.json",
                                "exact_audit_values": leaves,
                            },
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    },
                )
                os.replace(temporary, primary)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            shutil.copy2(primary, secondary)
            LOGGER.info("Saved composite: %s", primary)
            return primary, secondary
        finally:
            plt.close(figure)


def run_python(args: argparse.Namespace) -> None:
    root = args.project_root
    directory = root / "results_voxel_visualization"
    audit_path = directory / "clutch_pilot_voxel_audit.json"
    audit = load_json_object(audit_path) if audit_path.is_file() else None
    if audit is not None:
        flatten_audit(audit)

    render_paths = [directory / filename for filename in ALL_RENDERS]
    provenance_paths = [
        root / "figures/fig_clutch_pilot_voxel_audit.png",
        *render_paths,
    ]
    try:
        missing = [path for path in render_paths if not valid_png(path)]
        if args.max_steps > 0:
            self_check(root, args.max_steps)
        if (
            missing
            and args.skip_blender
            and 0 < args.max_steps <= 5
        ):
            LOGGER.info(
                "Micro-probe complete; Blender skipped and %d renders pending.",
                len(missing),
            )
            return

        if missing or args.force:
            if args.skip_blender:
                raise FileNotFoundError(
                    "Blender was skipped, but required renders are unavailable "
                    "or --force was requested: "
                    + ", ".join(path.name for path in missing)
                )
            run_blender(args)

        if audit is None:
            raise FileNotFoundError(f"Required voxel audit not found: {audit_path}")
        compose_figure(root, audit, args.dpi)
    finally:
        # Audit-present probes also register planned artifacts, with existence
        # flags, so a successful fast exit never silently omits provenance.
        if audit is not None:
            log_provenance(root, audit, provenance_paths)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_arguments()
    try:
        if args.mode == "blender":
            build_blender(args)
        else:
            run_python(args)
    except Exception:
        LOGGER.exception("Clutch pilot visualization failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
