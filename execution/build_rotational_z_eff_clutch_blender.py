#!/usr/bin/env python3
"""
Build a report-driven visualization of the rotational stepped-elevation clutch.

Geometry and BEM forces are read from:
    results/rotational_z_eff_clutch_report.json

Examples:
    python execution/build_rotational_z_eff_clutch_blender.py --force
    python execution/build_rotational_z_eff_clutch_blender.py --skip-blender --max-steps 1
    blender --background --python execution/build_rotational_z_eff_clutch_blender.py -- \
        --mode blender --design Rot_C10_Fractal_N3 --force

Radial coordinates are in micrometres. Displayed axial coordinates are multiplied
by --z-exaggeration; this never changes the report geometry or force data.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


TITLE = "Purely Rotational Stepped-Elevation Concentric Cantor Casimir Clutch"
DESIGN_NAMES = (
    "Rot_C10_Fractal_N3",
    "Rot_C4_TightSlot_N2",
    "Rot_C8_Compact_N2",
)


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a numeric JSON value.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{label} must be finite.") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


def required_number(mapping: dict[str, Any], key: str) -> float:
    if key not in mapping:
        raise ValueError(f"Report is missing {key!r}.")
    return finite_number(mapping[key], key)


@dataclass(frozen=True)
class Track:
    index: int
    inner_um: float
    outer_um: float


@dataclass(frozen=True)
class Design:
    name: str
    sectors: int
    R_min: float
    R_max: float
    aperture_arc_deg: float
    tooth_arc_deg: float
    t_membrane: float
    t_landing_pad: float
    rotor_tip_um: float
    rotor_top_um: float
    pad_top_um: float
    pad_bottom_um: float
    radial_clearance_um: float
    vertical_clearance_um: float
    elements: tuple[dict[str, float], ...]
    ring_intervals: tuple[tuple[float, float], ...]

    def validate(self) -> None:
        if self.sectors != 4:
            raise ValueError("The report must describe the specified four-sector geometry.")
        if not 0.0 < self.R_min < self.R_max:
            raise ValueError("Invalid report radial domain.")
        if not 0.0 < self.aperture_arc_deg < 90.0:
            raise ValueError("Invalid aperture angle.")
        if not 0.0 < self.tooth_arc_deg < 90.0:
            raise ValueError("Invalid tooth angle.")
        if self.t_membrane <= 0.0 or self.t_landing_pad <= 0.0:
            raise ValueError("Membrane and landing-pad thicknesses must be positive.")
        if not (
            self.rotor_top_um >= 0.0 > -self.t_membrane
            > self.rotor_tip_um > self.pad_top_um > self.pad_bottom_um
        ):
            raise ValueError("Report violates the required axial topological ordering.")
        if self.radial_clearance_um <= 0.0 or self.vertical_clearance_um <= 0.0:
            raise ValueError("Collision certificates must certify positive clearances.")
        if not math.isclose(
            self.pad_top_um - self.pad_bottom_um,
            self.t_landing_pad,
            rel_tol=1e-8,
            abs_tol=1e-10,
        ):
            raise ValueError("Landing-pad thickness disagrees with its certified elevations.")
        if not math.isclose(
            self.rotor_tip_um - self.pad_top_um,
            self.vertical_clearance_um,
            rel_tol=1e-8,
            abs_tol=1e-10,
        ):
            raise ValueError("Landing-pad clearance disagrees with the fixed rotor tip.")
        if not self.elements or not self.ring_intervals:
            raise ValueError("Report geometry is empty.")
        for low, high in self.ring_intervals:
            if not self.R_min <= low < high <= self.R_max:
                raise ValueError("Invalid surviving Cantor ring interval.")
        for element in self.elements:
            if not (
                self.R_min < element["r_inner"] < element["r_tooth_in"]
                < element["r_tooth_out"] < element["r_outer"] < self.R_max
            ):
                raise ValueError("A rotor tooth does not fit strictly inside its radial slot.")
            clearance = min(
                element["r_tooth_in"] - element["r_inner"],
                element["r_outer"] - element["r_tooth_out"],
            )
            if clearance + 1e-10 < self.radial_clearance_um:
                raise ValueError("Element geometry contradicts the radial collision certificate.")


@dataclass(frozen=True)
class BuildPaths:
    directory: Path
    manifest: Path
    blend: Path
    beauty: Path
    transition: Path
    detail: Path
    closeup: Path
    composite: Path
    figure_png: Path
    figure_pdf: Path

    @classmethod
    def create(cls, root: Path, name: str) -> BuildPaths:
        directory = root / "results" / "rotational_clutch_blender"
        return cls(
            directory,
            directory / "visualization_manifest.json",
            directory / "rotational_z_eff_clutch_scene.blend",
            directory / "render_rot_clutch_repulsive_iso.png",
            directory / "render_rot_clutch_straddling_iso.png",
            directory / "render_rot_clutch_attractive_iso.png",
            directory / "render_rot_clutch_step_closeup.png",
            directory / "fig_rotational_z_eff_clutch_blender.png",
            root / "figures" / "fig_rotational_z_eff_clutch_blender.png",
            root / "figures" / "fig_rotational_z_eff_clutch_blender.pdf",
        )

    def renders(self) -> tuple[Path, ...]:
        return self.beauty, self.transition, self.detail, self.closeup


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("python", "blender"), default="python")
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--design", choices=DESIGN_NAMES, default=DESIGN_NAMES[0])
    parser.add_argument(
        "--blender",
        default=os.environ.get(
            "BLENDER_BIN",
            r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
        ),
    )
    parser.add_argument("--skip-blender", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--max-steps", type=int, default=0,
        help="Probe limit; 1–5 with --skip-blender validates the report and exits.",
    )
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--resolution", type=int, default=1920, help="Render width.")
    parser.add_argument("--resolution-percentage", type=int, default=100)
    parser.add_argument("--angular-segments", type=int, default=384)
    parser.add_argument("--z-exaggeration", type=float, default=2.5)
    args = parser.parse_args(argv)
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative.")
    if not 1 <= args.samples <= 16384:
        parser.error("--samples must be between 1 and 16384.")
    if not 256 <= args.resolution <= 8192:
        parser.error("--resolution must be between 256 and 8192.")
    if not 1 <= args.resolution_percentage <= 100:
        parser.error("--resolution-percentage must be between 1 and 100.")
    if not 48 <= args.angular_segments <= 8192:
        parser.error("--angular-segments must be between 48 and 8192.")
    if not math.isfinite(args.z_exaggeration) or args.z_exaggeration <= 0.0:
        parser.error("--z-exaggeration must be finite and positive.")
    if args.mode == "blender" and args.skip_blender:
        parser.error("--skip-blender is only applicable to --mode python.")
    args.project_root = args.project_root.expanduser().resolve()
    return args


def atomic_text(path: Path, text: str) -> None:
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def numeric_fields(mapping: dict[str, Any], prefix: str = ""):
    """Search result fields, not geometry parameters, retaining their report paths."""
    for key, value in mapping.items():
        if value is None:
            continue
        path = f"{prefix}.{key}" if prefix else key
        if key in ("parameters", "provenance"):
            continue
        if isinstance(value, dict):
            yield from numeric_fields(value, path)
        else:
            yield key, value, path


def force_pn(evaluation: dict[str, Any]) -> tuple[float, str]:
    aliases = {
        "fzpn": 1.0,
        "forcezpn": 1.0,
        "zforcepn": 1.0,
        "totalfzpn": 1.0,
        "fztotalpn": 1.0,
        "fzn": 1e12,
        "forcezn": 1e12,
        "zforcen": 1e12,
        "totalfzn": 1e12,
        "fztotaln": 1e12,
    }
    fields = list(numeric_fields(evaluation))
    # Prefer explicitly labelled pN fields over converted SI fields.
    for scale in (1.0, 1e12):
        for key, value, path in fields:
            if value is None:
                continue
            normalized = "".join(c for c in key.lower() if c.isalnum())
            if aliases.get(normalized) == scale:
                result = finite_number(value, path) * scale
                if not math.isfinite(result):
                    raise ValueError(f"Force conversion overflow at {path}.")
                return result, path
    raise ValueError("Evaluation is missing a unit-labelled BEM F_z_pN or F_z_N field.")


def delta_z_nm(evaluation: dict[str, Any], design: Design) -> str:
    aliases = {
        "deltazeffnm": 1.0, "zeffnm": 1.0,
        "deltazeffum": 1000.0, "zeffum": 1000.0,
        "deltazeffm": 1e9, "zeffm": 1e9,
    }
    for key, value, path in numeric_fields(evaluation):
        if value is None:
            continue
        normalized = "".join(c for c in key.lower() if c.isalnum())
        if normalized in aliases:
            nm = finite_number(value, path) * aliases[normalized]
            if not math.isfinite(nm):
                raise ValueError(f"Effective-separation conversion overflow at {path}.")
            return f"{nm:+.8g} nm"
    if evaluation["state"] == "aperture":
        return f"{design.rotor_tip_um * 1000:+.8g} nm"
    if evaluation["state"] == "landing_pad":
        return f"{design.vertical_clearance_um * 1000:+.8g} nm"
    # A straddling state spans both tiers; do not invent a scalar effective gap.
    return (
        f"{design.rotor_tip_um * 1000:+.8g} / "
        f"{design.vertical_clearance_um * 1000:+.8g} nm (two tiers)"
    )


def load_report(root: Path) -> dict[str, Any]:
    path = root / "results" / "rotational_z_eff_clutch_report.json"
    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict):
        raise ValueError("Report must be a JSON object.")
    if not isinstance(report.get("provenance"), dict):
        raise ValueError("Report provenance must be an object.")
    evaluations = report.get("evaluations")
    if not isinstance(evaluations, list) or not evaluations:
        raise ValueError("Report evaluations must be a nonempty list.")
    for entry in evaluations:
        if not isinstance(entry, dict):
            raise ValueError("Each evaluation must be an object.")
        if entry.get("design") in DESIGN_NAMES:
            required_number(entry, "theta_deg")
            force_pn(entry)
            if not isinstance(entry.get("state"), str):
                raise ValueError("Each supported evaluation must have a state.")
    return report


def load_design(
    report: dict[str, Any], name: str
) -> tuple[Design, list[dict[str, Any]], tuple[dict[str, Any], ...]]:
    evaluations = [entry for entry in report["evaluations"] if entry.get("design") == name]
    if not evaluations:
        raise ValueError(f"No evaluations found for {name}.")
    solver = evaluations[0].get("solver_result")
    if not isinstance(solver, dict) or not isinstance(solver.get("parameters"), dict):
        raise ValueError(f"{name} is missing solver_result.parameters.")
    parameters = solver["parameters"]
    provenance = report["provenance"]
    certificates = provenance.get("collision_certificates")
    if not isinstance(certificates, dict) or not isinstance(certificates.get(name), dict):
        raise ValueError(f"No collision certificate found for {name}.")
    certificate = certificates[name]
    raw_elements = parameters.get("elements")
    if not isinstance(raw_elements, list) or not raw_elements:
        raise ValueError(f"{name} has no radial slot elements.")
    elements = []
    for element in raw_elements:
        if not isinstance(element, dict):
            raise ValueError("Each radial element must be an object.")
        elements.append({
            key: required_number(element, key)
            for key in ("r_inner", "r_outer", "r_tooth_in", "r_tooth_out")
        })
    r_min = required_number(parameters, "R_min")
    r_max = required_number(parameters, "R_max")
    intervals = []
    previous = r_min
    for element in elements:
        if element["r_inner"] <= previous:
            raise ValueError("Radial slots must be ordered, disjoint, and separated by ribs.")
        intervals.append((previous, element["r_inner"]))
        previous = element["r_outer"]
    intervals.append((previous, r_max))
    symmetry = required_number(provenance, "symmetry_order")
    if symmetry != 4:
        raise ValueError("symmetry_order must be exactly 4.")
    design = Design(
        name, int(symmetry), r_min, r_max,
        required_number(parameters, "aperture_arc_deg"),
        required_number(parameters, "tooth_arc_deg"),
        required_number(parameters, "t_membrane"),
        required_number(parameters, "t_landing_pad"),
        required_number(provenance, "physical_rotor_tip_um"),
        required_number(provenance, "physical_rotor_top_um"),
        required_number(certificate, "z_pad_top_um"),
        required_number(certificate, "z_pad_bottom_um"),
        required_number(certificate, "minimum_elevated_rib_radial_clearance_um"),
        required_number(certificate, "landing_pad_vertical_clearance_um"),
        tuple(elements), tuple(intervals),
    )
    design.validate()
    representatives = []
    for state, last in (("aperture", False), ("straddling", False), ("landing_pad", True)):
        matches = [entry for entry in evaluations if entry["state"] == state]
        if not matches:
            raise ValueError(f"{name} has no {state!r} evaluation.")
        representatives.append(matches[-1] if last else matches[0])
    return design, evaluations, tuple(representatives)


def cantor_tracks(design: Design, order: int) -> list[Track]:
    """Use the exact report intervals; never procedurally refine or truncate them."""
    return [Track(index, low, high) for index, (low, high) in enumerate(design.ring_intervals)]


def effective_order(design: Design, max_steps: int) -> int:
    # The loaded geometry is authoritative, regardless of the probe limit.
    return len(design.elements)


def resolve_blender(requested: str) -> str:
    candidate = Path(requested).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    executable = shutil.which(requested) or shutil.which("blender")
    if executable:
        return executable
    raise FileNotFoundError("Blender was not found. Supply --blender or set BLENDER_BIN.")


def launch_blender(args: argparse.Namespace) -> None:
    command = [
        resolve_blender(args.blender), "--background", "--factory-startup",
        "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--",
        "--mode", "blender", "--project-root", str(args.project_root),
        "--design", args.design, "--max-steps", str(args.max_steps),
        "--samples", str(args.samples), "--resolution", str(args.resolution),
        "--resolution-percentage", str(args.resolution_percentage),
        "--angular-segments", str(args.angular_segments),
        "--z-exaggeration", str(args.z_exaggeration), "--force",
    ]
    print("Launching:", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True)


def build_blender(
    args: argparse.Namespace, design: Design, tracks: list[Track], paths: BuildPaths, order: int
) -> None:
    try:
        bpy: Any = importlib.import_module("bpy")
        mathutils: Any = importlib.import_module("mathutils")
    except ImportError as error:
        raise RuntimeError("--mode blender must run inside Blender 4.5+.") from error
    if tuple(bpy.app.version) < (4, 5, 0):
        raise RuntimeError(f"Blender 4.5+ is required; found {bpy.app.version_string}.")
    report = load_report(args.project_root)
    _, _, representatives = load_design(report, design.name)
    paths.directory.mkdir(parents=True, exist_ok=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene.name = "Report-driven rotational clutch"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1e-6
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = args.samples
    print(f"Render engine: EEVEE | device: {bpy.context.preferences.system.compute_device_type if hasattr(bpy.context.preferences.system, 'compute_device_type') else 'automatic graphics device'}",
          flush=True)
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = round(args.resolution * 1080 / 1920)
    scene.render.resolution_percentage = args.resolution_percentage
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("Neutral studio")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.11, 0.13, 0.18, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9

    def material(name, rgb, metallic, roughness, emission=0.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        shader = mat.node_tree.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = (*rgb, 1)
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Emission Color"].default_value = (*rgb, 1)
        shader.inputs["Emission Strength"].default_value = emission
        return mat

    gold = material("Elevated ribs | polished bright gold", (0.96, 0.76, 0.22), 0.92, 0.18)
    copper = material("Recessed rings and risers | copper gold", (0.74, 0.46, 0.18), 0.88, 0.25)
    bronze = material("Recessed slot bridges | rose bronze", (0.54, 0.32, 0.14), 0.85, 0.30)
    teal = material("Sector 0 teeth | emerald teal", (0.08, 0.92, 0.58), 0.82, 0.15, 0.20)
    sapphire = material("Sectors 1–3 teeth | platinum sapphire", (0.36, 0.52, 0.74), 0.90, 0.22)
    cyan = material("Reference | fixed tip", (0.0, 0.85, 1.0), 0.0, 0.3, 2.0)
    magenta = material("Reference | landing pad", (1.0, 0.24, 0.55), 0.0, 0.3, 2.0)
    geometry = bpy.data.collections.new("Exact report geometry | radial units um")
    scene.collection.children.link(geometry)

    def annular_mesh(name, patches, mat, parent=None, bevel=0.0):
        vertices, faces = [], []
        for low, high, start, end, bottom, top in patches:
            if not (low < high and start < end and bottom < top):
                raise ValueError(f"Invalid annular patch: {name}.")
            count = max(3, math.ceil((end - start) / 360 * args.angular_segments))
            offset = len(vertices)
            for index in range(count + 1):
                angle = math.radians(start + (end - start) * index / count)
                c, s = math.cos(angle), math.sin(angle)
                vertices.extend((
                    (low * c, low * s, bottom * args.z_exaggeration),
                    (high * c, high * s, bottom * args.z_exaggeration),
                    (low * c, low * s, top * args.z_exaggeration),
                    (high * c, high * s, top * args.z_exaggeration),
                ))
            for index in range(count):
                a, b = offset + 4 * index, offset + 4 * (index + 1)
                faces.extend((
                    (a, b, b + 1, a + 1),
                    (a + 2, a + 3, b + 3, b + 2),
                    (a, a + 2, b + 2, b),
                    (a + 1, b + 1, b + 3, a + 3),
                ))
            last = offset + 4 * count
            faces.extend((
                (offset, offset + 1, offset + 3, offset + 2),
                (last, last + 2, last + 3, last + 1),
            ))
        mesh = bpy.data.meshes.new(name + " mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        geometry.objects.link(obj)
        obj.data.materials.append(mat)
        obj.parent = parent
        obj["radial_units"] = "um"
        obj["z_exaggeration"] = args.z_exaggeration
        return obj

    ribs, pads, bridges, risers = [], [], [], []
    for sector in range(design.sectors):
        base = sector * 90.0
        boundary = base + design.aperture_arc_deg
        for track in tracks:
            radial = (track.inner_um, track.outer_um)
            ribs.append((*radial, base, boundary, -design.t_membrane, 0.0))
            pads.append((*radial, boundary, base + 90.0, design.pad_bottom_um, design.pad_top_um))
            for edge in (base, boundary):
                risers.append((*radial, edge - 0.4, edge + 0.4, design.pad_top_um, 0.0))
        for element in design.elements:
            bridges.append((
                element["r_inner"], element["r_outer"], boundary, base + 90.0,
                design.pad_bottom_um, design.pad_top_um,
            ))
    annular_mesh("Tier 1 | elevated Cantor ribs; open radial slots", ribs, gold)
    annular_mesh("Tier 2 | recessed landing-pad rings", pads, copper)
    annular_mesh("Tier 2 | recessed slot bridges", bridges, bronze)
    annular_mesh("Step risers | 0.8 degree boundary bands", risers, copper)
    for label, z, mat in (
        ("Fixed rotor tip", design.rotor_tip_um, cyan),
        ("Recessed pad top", design.pad_top_um, magenta),
        ("Elevated rib top", 0.0, gold),
    ):
        annular_mesh(
            "Elevation reference | " + label,
            [(design.R_max + 0.02, design.R_max + 0.04, 0.0, 65.0, z, z + 0.0005)],
            mat,
        )

    rotor_objects = []

    def set_rotor(evaluation):
        for obj in rotor_objects:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        rotor_objects.clear()
        theta = required_number(evaluation, "theta_deg")
        center = (15.0 + theta) % 90.0
        low = center - design.tooth_arc_deg / 2
        high = center + design.tooth_arc_deg / 2
        if low < 0:
            spans = [(0.0, high), (low + 90.0, 90.0)]
        elif high > 90:
            spans = [(low, 90.0), (0.0, high - 90.0)]
        else:
            spans = [(low, high)]
        for sector in range(design.sectors):
            patches = [
                (
                    element["r_tooth_in"], element["r_tooth_out"],
                    sector * 90.0 + a, sector * 90.0 + b,
                    design.rotor_tip_um, design.rotor_top_um,
                )
                for element in design.elements for a, b in spans if b > a
            ]
            obj = annular_mesh(
                f"Fixed-z rotor teeth | sector {sector}", patches,
                teal if sector == 0 else sapphire,
            )
            obj["theta_deg"] = theta
            obj["physical_z_tip_um"] = design.rotor_tip_um
            rotor_objects.append(obj)
        scene["theta_deg"] = theta
        scene["state"] = evaluation["state"]
        scene["F_z_pN"] = force_pn(evaluation)[0]

    def aim(obj, target):
        direction = mathutils.Vector(target) - obj.location
        if direction.length <= 1e-9:
            raise ValueError("Camera or light coincides with its target.")
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    for name, location, energy, size in (
        ("Key studio softbox", (1.5, -2.8, 4.0), 450, 3.0),
        ("Fill studio softbox", (-2.5, -0.5, 2.0), 250, 2.5),
        ("Rim studio softbox", (0.8, 3.0, 2.8), 550, 2.0),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.size = energy, size
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = location
        aim(obj, (0.0, 0.0, -0.08))

    camera_data = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "PERSP"
    camera_data.lens = 42
    camera_data.clip_start = 0.001
    camera_data.clip_end = 100
    camera.location = (3.55, -3.25, 2.65)
    aim(camera, (0.0, 0.0, -0.12))
    scene["design"] = design.name
    scene["source_report"] = str(args.project_root / "results" / "rotational_z_eff_clutch_report.json")
    scene["physical_z_tip_um"] = design.rotor_tip_um
    scene["display_z_exaggeration"] = args.z_exaggeration
    scene["notice"] = "Exact report radial geometry; axial display exaggeration only."

    def render(destination):
        scene.render.filepath = str(destination)
        bpy.ops.render.render(write_still=True, scene=scene.name)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError(f"Render did not produce {destination}.")

    for evaluation, destination in zip(representatives, paths.renders()[:3]):
        set_rotor(evaluation)
        render(destination)
    set_rotor(representatives[1])
    camera.location = (2.15, 0.15, 0.52)
    aim(camera, (0.75, 0.52, -0.22))
    camera_data.lens = 45
    render(paths.closeup)
    camera.location = (3.55, -3.25, 2.65)
    aim(camera, (0.0, 0.0, -0.12))
    camera_data.lens = 42
    bpy.ops.wm.save_as_mainfile(filepath=str(paths.blend))
    if not paths.blend.is_file() or paths.blend.stat().st_size == 0:
        raise RuntimeError("Blender scene was not saved.")


def export_metadata(
    args: argparse.Namespace, design: Design, tracks: list[Track], paths: BuildPaths, order: int
) -> None:
    from dataclasses import asdict

    _, _, representatives = load_design(load_report(args.project_root), design.name)
    manifest = {
        "source_report": str(args.project_root / "results" / "rotational_z_eff_clutch_report.json"),
        "design": asdict(design),
        "radial_units": "um",
        "z_exaggeration": args.z_exaggeration,
        "physical_z_tip_is_fixed": True,
        "representatives": [
            {
                "theta_deg": entry["theta_deg"],
                "state": entry["state"],
                "F_z_pN": force_pn(entry)[0],
                "force_report_key": force_pn(entry)[1],
            }
            for entry in representatives
        ],
        "renders": [str(path) for path in paths.renders()],
    }
    atomic_text(paths.manifest, json.dumps(manifest, indent=2, allow_nan=False) + "\n")


def compose_figure(
    args: argparse.Namespace, report: dict[str, Any], design: Design, paths: BuildPaths
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    _, _, representatives = load_design(report, design.name)
    paths.figure_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(3, 2, figsize=(18, 14.5))
    metric_keys = set()
    for entry in report["evaluations"]:
        metric_key = entry.get("metric_key")
        if isinstance(metric_key, str) and metric_key:
            metric_keys.add(metric_key)
    try:
        titles = ("A  Repulsive State", "B  Straddling Transition", "C  Attractive State")
        for ax, title, path, evaluation in zip(
            axes.flat, titles, paths.renders()[:3], representatives
        ):
            ax.imshow(mpimg.imread(path))
            ax.set_axis_off()
            force, _ = force_pn(evaluation)
            ax.set_title(
                f"{title}\n"
                f"θ = {evaluation['theta_deg']:g}° | {evaluation['state']} | "
                f"Δz_eff = {delta_z_nm(evaluation, design)}\n"
                f"BEM F_z = {force:+.4f} pN",
                fontsize=11, loc="left",
            )
        ax = axes.flat[3]
        ax.imshow(mpimg.imread(paths.closeup))
        ax.set_axis_off()
        ax.set_title(
            "D  Step-Boundary Macro Close-Up\n"
            f"Fixed z_tip = {design.rotor_tip_um * 1000:g} nm | "
            f"ribs = 0 nm | pad = {design.pad_top_um * 1000:g} nm\n"
            f"Landing-pad clearance = {design.vertical_clearance_um * 1000:g} nm; "
            f"display axial scale ×{args.z_exaggeration:g}",
            fontsize=11, loc="left",
        )
        ax = axes.flat[4]
        colors = ("#986020", "#287ea5", "#159866")
        for name, color in zip(
            ("Rot_C4_TightSlot_N2", "Rot_C8_Compact_N2", "Rot_C10_Fractal_N3"), colors
        ):
            _, evaluations, _ = load_design(report, name)
            evaluations = sorted(evaluations, key=lambda entry: entry["theta_deg"])
            angles, forces = [], []
            for evaluation in evaluations:
                force, _ = force_pn(evaluation)
                angles.append(evaluation["theta_deg"])
                forces.append(force)
            ax.plot(angles, forces, "o-", color=color, markersize=4, label=name)
        ax.axhline(0, color="black", linewidth=0.9)
        bottom, top = ax.get_ylim()
        if top > 0:
            ax.axhspan(max(0, bottom), top, color="#7bd4b0", alpha=0.15)
        if bottom < 0:
            ax.axhspan(bottom, min(0, top), color="#f1bd7d", alpha=0.18)
        ax.set_ylim(bottom, top)
        ax.set_title("E  Exact BEM force versus rotation", loc="left")
        ax.set_xlabel("Rotation angle θ (deg)")
        ax.set_ylabel("F_z (pN): positive repulsive / negative attractive")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9)

        rows = [
            ("Selected design", design.name),
            ("Symmetry order", str(design.sectors)),
            ("Radial domain (µm)", f"{design.R_min:.12g} – {design.R_max:.12g}"),
            ("Slots / surviving rings", f"{len(design.elements)} / {len(design.ring_intervals)}"),
            ("Aperture / tooth arc (deg)", f"{design.aperture_arc_deg:g} / {design.tooth_arc_deg:g}"),
            ("Membrane / landing pad (nm)", f"{design.t_membrane * 1000:g} / {design.t_landing_pad * 1000:g}"),
            ("Rotor tip / top (nm)", f"{design.rotor_tip_um * 1000:g} / {design.rotor_top_um * 1000:g}"),
            ("Pad top / bottom (nm)", f"{design.pad_top_um * 1000:g} / {design.pad_bottom_um * 1000:g}"),
            ("Certified radial clearance (nm)", f"{design.radial_clearance_um * 1000:.12g}"),
            ("Certified pad clearance (nm)", f"{design.vertical_clearance_um * 1000:.12g}"),
        ]
        for evaluation in representatives:
            force, _ = force_pn(evaluation)
            rows.append((
                f"{evaluation['state']} F_z (pN), θ={evaluation['theta_deg']:g}°",
                f"{force:+.4f}",
            ))
        ax = axes.flat[5]
        ax.set_axis_off()
        ax.set_title("F  Exact geometry & force audit", loc="left")
        table = ax.table(
            cellText=rows, colLabels=("Report quantity", "Report value"),
            colWidths=(0.52, 0.48), cellLoc="left", bbox=(0.0, 0.0, 1.0, 0.90),
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8.5)
        fig.suptitle(TITLE, fontsize=18)
        fig.text(
            0.5, 0.012,
            "Source: results/rotational_z_eff_clutch_report.json | "
            "Forces are report BEM results, not inferred from renders. "
            "Axial exaggeration is display-only.",
            ha="center", fontsize=9,
        )
        fig.tight_layout(rect=(0.01, 0.035, 0.99, 0.96))
        fig.savefig(paths.figure_png, dpi=200)
        fig.savefig(paths.figure_pdf)
        shutil.copyfile(paths.figure_png, paths.composite)
    finally:
        plt.close(fig)

    root_string = str(args.project_root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)
    logger = importlib.import_module("utils.metrics_logger")
    for fig_path in (paths.figure_png, paths.figure_pdf):
        logger.save_plot_provenance(
            str(fig_path),
            str(args.project_root / "results" / "provenance_metrics.json"),
            sorted(metric_keys),
            solver_name="bem",
            solver_parameters={"formulation": "vector_dyadic"},
        )

    paper_figures = (
        args.project_root / "Papers" / "Fractal_Casimir_Nature_EM" / "figures"
    )
    if paper_figures.is_dir():
        # Include sidecars that append to the PNG name or replace its suffix.
        sources = {
            paths.figure_png,
            *paths.figure_png.parent.glob(f"{paths.figure_png.name}.*"),
            *paths.figure_png.parent.glob(f"{paths.figure_png.stem}.provenance.*"),
        }
        for source in sorted(sources):
            if source.is_file():
                shutil.copyfile(source, paper_figures / source.name)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = load_report(args.project_root)
    loaded = {name: load_design(report, name) for name in DESIGN_NAMES}
    design = loaded[args.design][0]
    if args.mode == "python" and args.skip_blender and 1 <= args.max_steps <= 5:
        print("Validated report geometry, collision certificates, and BEM evaluations.", flush=True)
        return 0

    paths = BuildPaths.create(args.project_root, design.name)
    order = effective_order(design, args.max_steps)
    tracks = cantor_tracks(design, order)
    renders_exist = all(path.is_file() and path.stat().st_size > 0 for path in paths.renders())
    reuse_renders = args.mode == "python" and args.skip_blender and renders_exist
    if reuse_renders:
        if not paths.manifest.is_file():
            raise ValueError("Cannot verify cached renders: visualization manifest is missing.")
        with paths.manifest.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        from dataclasses import asdict

        current_design = json.loads(json.dumps(asdict(design), allow_nan=False))
        if (
            manifest.get("design") != current_design
            or manifest.get("z_exaggeration") != args.z_exaggeration
        ):
            raise ValueError("Cached renders do not match the selected report geometry/display scale.")

    expected = (
        (paths.blend, *paths.renders())
        if args.mode == "blender"
        else (paths.figure_png, paths.figure_pdf, paths.composite)
    )
    existing = [path for path in expected if path.exists()]
    if existing and not args.force:
        raise FileExistsError(f"Output already exists: {existing[0]}. Use --force to rebuild.")
    paths.directory.mkdir(parents=True, exist_ok=True)
    if args.mode == "blender":
        build_blender(args, design, tracks, paths, order)
        export_metadata(args, design, tracks, paths, order)
    else:
        if not reuse_renders:
            launch_blender(args)
        if not all(path.is_file() and path.stat().st_size > 0 for path in paths.renders()):
            raise RuntimeError("All four Blender renders are required for the publication figure.")
        compose_figure(args, report, design, paths)
        print(f"Saved publication figures to {paths.figure_png.parent}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError, ValueError, RuntimeError, ImportError, subprocess.CalledProcessError
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
