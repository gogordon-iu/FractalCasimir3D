#!/usr/bin/env python3
"""
Build and render a mechanically connected NEMS Cantor clutch in Blender 4.5+.

Typical invocations:
    python execution/build_real_world_nems_clutch_blender.py
    python execution/build_real_world_nems_clutch_blender.py --skip-blender --max-steps 1
    blender --background --python execution/build_real_world_nems_clutch_blender.py \
        -- --mode blender --project-root /path/to/project

Geometry is expressed in micrometres. Blender coordinates use one scene unit
per micrometre; z exaggeration is a presentation transformation, not a change
to the physical dimensions reported in the audit.

Report force values are never synthesized. Missing force series are explicitly
identified in the publication figure and build manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

LOGGER = logging.getLogger("real_world_nems_clutch")
DESIGNS = (
    "Rot_C10_Fractal_N3",
    "Rot_C4_TightSlot_N2",
    "Rot_C8_Compact_N2",
)
BUILD_VERSION = "real-world-nems-connected-1.0"
EPS = 1.0e-6  # 0.001 nm structural overlap; never applied to active gaps.
OUTPUT_NAMES = (
    "render_nems_repulsive_iso.png",
    "render_nems_straddling_iso.png",
    "render_nems_attractive_iso.png",
    "render_nems_step_cutaway_closeup.png",
)
MATERIAL_SPECS: tuple[tuple[str, tuple[float, float, float], float, float, float], ...] = (
    ("Silicon_Si3N4_Slate", (0.16, 0.22, 0.30), 0.15, 0.35, 0.0),
    ("Copper_Gold_Anchor", (0.76, 0.48, 0.20), 0.88, 0.24, 0.0),
    ("Polished_Gold_Cantor_Ribs", (0.96, 0.76, 0.22), 0.92, 0.18, 0.0),
    ("Copper_Bronze_Landing_Pad", (0.74, 0.46, 0.18), 0.84, 0.25, 0.0),
    ("Rose_Bronze_Slot_Bridge", (0.54, 0.32, 0.14), 0.78, 0.28, 0.0),
    ("Emerald_Teal_Tooth", (0.08, 0.92, 0.58), 0.85, 0.15, 0.18),
    ("Platinum_Sapphire_Tooth", (0.36, 0.52, 0.74), 0.90, 0.22, 0.0),
    ("Titanium_Teal_Spider", (0.14, 0.78, 0.68), 0.75, 0.20, 0.0),
    ("Steel_Blue_Spider", (0.28, 0.44, 0.66), 0.82, 0.24, 0.0),
)
NUMBER_TYPES = (int, float)


@dataclass(frozen=True)
class ForceCurve:
    kind: str
    theta_deg: tuple[float, ...]
    force_n: tuple[float, ...]
    source: str


@dataclass(frozen=True)
class Geometry:
    r_min: float
    r_max: float
    rings: tuple[tuple[float, float], ...]
    teeth: tuple[tuple[float, float], ...]
    aperture_deg: float
    tooth_arc_deg: float
    cantor_order: int
    geometry_sources: tuple[str, ...]

    @property
    def stator_inner(self) -> float:
        return max(0.10, self.r_min - 0.12)

    @property
    def stator_outer(self) -> float:
        return self.r_max + 0.14

    @property
    def rotor_hub_inner(self) -> float:
        return max(0.06, self.r_min - 0.16)

    @property
    def rotor_hub_outer(self) -> float:
        return self.r_min - 0.03

    @property
    def rotor_rim_inner(self) -> float:
        return self.r_max + 0.03

    @property
    def rotor_rim_outer(self) -> float:
        return self.r_max + 0.14

    @property
    def slots(self) -> tuple[tuple[float, float], ...]:
        return tuple(
            (self.rings[i][1], self.rings[i + 1][0])
            for i in range(len(self.rings) - 1)
        )

    @property
    def straddling_theta(self) -> float:
        return self.aperture_deg - self.tooth_arc_deg / 2.0

    @property
    def repulsive_theta(self) -> float:
        return min(3.0, max(0.0, (self.aperture_deg - self.tooth_arc_deg) / 2.0))

    @property
    def radial_clearance_nm(self) -> float:
        return 1000.0 * min(
            min(t0 - s0, s1 - t1)
            for (t0, t1), (s0, s1) in zip(self.teeth, self.slots)
        )


@dataclass(frozen=True)
class Report:
    path: Path
    sha256: str
    design: str
    geometry: Geometry
    curves: tuple[ForceCurve, ...]
    fallback: bool


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, NUMBER_TYPES):
        raise ValueError(f"{label} must be a finite number, received {value!r}.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite, received {value!r}.")
    return result


def walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from walk(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, (*path, str(index)))


def find_design_document(document: Any, design: str) -> Any:
    candidates: list[tuple[int, Any]] = []
    identifiers = {"design", "designname", "name", "id", "designid"}
    for path, item in walk(document):
        if path and path[-1] == design and isinstance(item, (dict, list)):
            candidates.append((len(path), item))
        if isinstance(item, Mapping):
            if any(
                normalized(str(key)) in identifiers and value == design
                for key, value in item.items()
            ):
                candidates.append((len(path), item))
    if not candidates:
        raise ValueError(f"Design {design!r} is not present in the report.")
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def find_field(
    document: Any, aliases: Sequence[str]
) -> tuple[Any, str] | None:
    rank = {normalized(name): index for index, name in enumerate(aliases)}
    candidates: list[tuple[int, int, Any, str]] = []
    for path, value in walk(document):
        if path and normalized(path[-1]) in rank:
            candidates.append(
                (rank[normalized(path[-1])], len(path), value, ".".join(path))
            )
    if not candidates:
        return None
    candidates.sort(key=lambda entry: (entry[0], entry[1]))
    _, _, value, source = candidates[0]
    return value, source


def length_scale(source: str) -> float:
    key = normalized(source.split(".")[-1])
    if key.endswith("nm"):
        return 1.0e-3
    if key.endswith("mm"):
        return 1000.0
    if key.endswith("meters") or key.endswith("metres") or key.endswith("radiusm"):
        return 1.0e6
    return 1.0


def get_scalar(
    document: Any,
    aliases: Sequence[str],
    *,
    default: float | None = None,
    length: bool = False,
) -> tuple[float, str]:
    found = find_field(document, aliases)
    if found is None:
        if default is None:
            raise ValueError(f"Report lacks a required geometry field: {', '.join(aliases)}")
        return default, f"specified/default:{aliases[0]}"
    value, source = found
    result = finite_number(value, source)
    return result * (length_scale(source) if length else 1.0), source


def parse_intervals(value: Any, source: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{source} must contain a nonempty list of radial intervals.")
    scale = length_scale(source)
    intervals: list[tuple[float, float]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            first = find_field(
                item, ("r_in_um", "r_start_um", "r_inner_um", "r_in", "r_start", "lo", "start")
            )
            last = find_field(
                item, ("r_out_um", "r_end_um", "r_outer_um", "r_out", "r_end", "hi", "end")
            )
            if first is None or last is None:
                raise ValueError(f"Cannot read radial endpoints in {source}[{index}].")
            lo = finite_number(first[0], first[1]) * length_scale(first[1]) * scale
            hi = finite_number(last[0], last[1]) * length_scale(last[1]) * scale
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            lo = finite_number(item[0], source) * scale
            hi = finite_number(item[1], source) * scale
        else:
            raise ValueError(f"Invalid radial interval in {source}[{index}].")
        if not 0.0 < lo < hi:
            raise ValueError(f"Invalid positive radial interval {(lo, hi)} in {source}.")
        intervals.append((lo, hi))
    intervals.sort()
    if any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError(f"{source} contains overlapping or touching intervals.")
    return tuple(intervals)


def cantor_intervals(lo: float, hi: float, order: int) -> tuple[tuple[float, float], ...]:
    intervals = [(lo, hi)]
    for _ in range(order):
        refined: list[tuple[float, float]] = []
        for left, right in intervals:
            third = (right - left) / 3.0
            refined.extend(((left, left + third), (right - third, right)))
        intervals = refined
    return tuple(intervals)


def extract_geometry(document: Any, design: str) -> Geometry:
    sources: list[str] = []
    ring_field = find_field(
        document,
        (
            "ring_intervals_um", "surviving_ring_intervals_um", "cantor_ring_intervals_um",
            "ring_intervals", "surviving_ring_intervals", "cantor_intervals", "rings_um",
        ),
    )
    rings = parse_intervals(*ring_field) if ring_field else None
    r_min, source = get_scalar(
        document,
        ("R_min_um", "r_min", "R_inner_um", "radius_inner_um", "inner_radius_um", "r_min_nm"),
        default=rings[0][0] if rings else None,
        length=True,
    )
    sources.append(source)
    r_max, source = get_scalar(
        document,
        ("R_max_um", "r_max", "R_outer_um", "radius_outer_um", "outer_radius_um", "r_max_nm"),
        default=rings[-1][1] if rings else None,
        length=True,
    )
    sources.append(source)
    match = re.search(r"_N(\d+)$", design)
    default_order = int(match.group(1)) if match else 3
    order_value, source = get_scalar(
        document, ("cantor_order", "fractal_order", "cantor_depth", "N"), default=float(default_order)
    )
    if not order_value.is_integer() or not 1 <= order_value <= 6:
        raise ValueError("Cantor order must be an integer between 1 and 6.")
    order = int(order_value)
    sources.append(source)
    if rings is None:
        rings = cantor_intervals(r_min, r_max, order)
        sources.append("derived:middle-third Cantor construction")
    else:
        sources.append(ring_field[1])
    aperture, source = get_scalar(
        document, ("aperture_arc_deg", "aperture_deg", "aperture_angle_deg"), default=36.0
    )
    sources.append(source)
    tooth_arc, source = get_scalar(
        document, ("tooth_arc_deg", "tooth_angle_deg", "rotor_tooth_arc_deg"), default=30.0
    )
    sources.append(source)
    if not 0.0 < tooth_arc <= aperture < 90.0:
        raise ValueError("Require 0 < tooth_arc_deg <= aperture_arc_deg < 90.")
    slots = tuple((a[1], b[0]) for a, b in zip(rings, rings[1:]))
    if not slots:
        raise ValueError("At least two surviving rings and one rotor slot are required.")
    tooth_field = find_field(
        document,
        ("tooth_intervals_um", "rotor_tooth_intervals_um", "tooth_intervals", "rotor_tooth_intervals"),
    )
    if tooth_field:
        teeth = parse_intervals(*tooth_field)
        sources.append(tooth_field[1])
    else:
        records = find_field(document, ("rotor_teeth", "teeth", "tooth_geometry"))
        if records and isinstance(records[0], list) and records[0] and isinstance(records[0][0], Mapping):
            teeth = parse_intervals(records[0], records[1])
            sources.append(records[1])
        else:
            fill, source = get_scalar(
                document, ("tooth_fill_fraction", "slot_fill_fraction", "tooth_width_fraction"),
                default=0.70,
            )
            if not 0.0 < fill < 1.0:
                raise ValueError("Tooth slot fill fraction must lie strictly between zero and one.")
            clearance_field = find_field(
                document, ("radial_clearance_nm", "tooth_side_clearance_nm", "radial_clearance_um")
            )
            if clearance_field:
                clearance = finite_number(clearance_field[0], clearance_field[1])
                clearance *= length_scale(clearance_field[1])
                if clearance <= 0.0:
                    raise ValueError("Radial clearance must be positive.")
                teeth = tuple((a + clearance, b - clearance) for a, b in slots)
                sources.append(clearance_field[1])
            else:
                teeth = tuple(
                    (a + (b - a) * (1.0 - fill) / 2.0, b - (b - a) * (1.0 - fill) / 2.0)
                    for a, b in slots
                )
                sources.append(source)
    if not 0.22 < r_min < r_max:
        raise ValueError("The specified anchor/collar architecture requires 0.22 < R_min < R_max.")
    tolerance = 1.0e-7 * max(1.0, r_max)
    if abs(rings[0][0] - r_min) > tolerance or abs(rings[-1][1] - r_max) > tolerance:
        raise ValueError("Surviving ring intervals must span the reported R_min and R_max.")
    if len(teeth) != len(slots):
        raise ValueError("There must be exactly one radial tooth interval per Cantor slot.")
    for tooth, slot in zip(teeth, slots):
        if not slot[0] < tooth[0] < tooth[1] < slot[1]:
            raise ValueError(f"Tooth interval {tooth} does not fit strictly inside slot {slot}.")
    geometry = Geometry(
        r_min, r_max, rings, teeth, aperture, tooth_arc, order, tuple(sources)
    )
    if geometry.rotor_hub_inner >= geometry.rotor_hub_outer:
        raise ValueError("Rotor collar has zero or negative radial thickness.")
    if geometry.stator_inner >= r_min:
        raise ValueError("Inner stator anchor has zero or negative radial thickness.")
    return geometry


def numeric_array(value: Any) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or not value:
        return None
    if any(isinstance(item, bool) or not isinstance(item, NUMBER_TYPES) for item in value):
        return None
    result = tuple(float(item) for item in value)
    return result if all(math.isfinite(item) for item in result) else None


def is_angle_key(key: str) -> bool:
    name = normalized(key)
    return name in {
        "theta", "thetadeg", "thetadegrees", "angles", "anglesdeg",
        "angledeg", "rotationdeg", "rotationanglesdeg", "thetagriddeg",
    }


def force_kind(path: str, fallback: bool) -> str | None:
    name = normalized(path)
    if any(word in name for word in ("lifshitz", "continuum", "pfa")):
        return "continuum"
    if any(word in name for word in ("isolated", "activezone", "activeonly")):
        return "isolated"
    if any(word in name for word in ("monolithic", "connected", "full", "total", "realworld")):
        return "full"
    if any(word in name for word in ("fz", "forcez", "normalforce", "axialforce")):
        return "isolated" if fallback else "full"
    return None


def force_unit_scale(path: str) -> float:
    terminal = normalized(path.split(".")[-1])
    for suffix, factor in (("pn", 1.0e-12), ("nn", 1.0e-9), ("un", 1.0e-6), ("mn", 1.0e-3)):
        if terminal.endswith(suffix):
            return factor
    return 1.0  # Unqualified scientific F_z fields conventionally use SI newtons.


def make_curve(
    kind: str, angles: Sequence[float], forces: Sequence[float], source: str
) -> ForceCurve:
    if len(angles) != len(forces) or not angles:
        raise ValueError(f"Force/angle array lengths disagree at {source}.")
    samples: dict[float, float] = {}
    scale = force_unit_scale(source)
    for theta, force in zip(angles, forces):
        theta = finite_number(theta, source)
        force = finite_number(force, source) * scale
        if theta in samples and not math.isclose(samples[theta], force, rel_tol=1.0e-9, abs_tol=1.0e-24):
            raise ValueError(f"Conflicting force samples at theta={theta} in {source}.")
        samples[theta] = force
    ordered = sorted(samples.items())
    return ForceCurve(kind, tuple(x for x, _ in ordered), tuple(y for _, y in ordered), source)


def extract_curves(document: Any, fallback: bool) -> tuple[ForceCurve, ...]:
    candidates: list[ForceCurve] = []

    def visit(value: Any, path: tuple[str, ...], inherited: tuple[float, ...] | None) -> None:
        if isinstance(value, Mapping):
            local_angles = inherited
            for key, item in value.items():
                if is_angle_key(str(key)):
                    array = numeric_array(item)
                    if array is not None:
                        local_angles = array
                        break
            for key, item in value.items():
                child_path = (*path, str(key))
                source = ".".join(child_path)
                array = numeric_array(item)
                kind = force_kind(source, fallback)
                terminal = normalized(str(key))
                force_named = any(
                    token in terminal for token in ("fz", "forcez", "force", "pfa", "lifshitz")
                )
                if (
                    array is not None and local_angles is not None and kind is not None
                    and force_named and not is_angle_key(str(key))
                ):
                    candidates.append(make_curve(kind, local_angles, array, source))
                if isinstance(item, (Mapping, list)):
                    visit(item, child_path, local_angles)
        elif isinstance(value, list):
            records = [item for item in value if isinstance(item, Mapping)]
            if records and len(records) == len(value):
                collected: dict[str, list[tuple[float, float]]] = {}
                for record in records:
                    theta: float | None = None
                    for key, item in record.items():
                        if is_angle_key(str(key)) and isinstance(item, NUMBER_TYPES) and not isinstance(item, bool):
                            theta = finite_number(item, ".".join(path))
                            break
                    if theta is None:
                        continue
                    for key, item in record.items():
                        name = normalized(str(key))
                        if (
                            isinstance(item, NUMBER_TYPES) and not isinstance(item, bool)
                            and any(token in name for token in ("fz", "force", "pfa", "lifshitz"))
                        ):
                            collected.setdefault(str(key), []).append(
                                (theta, finite_number(item, str(key)))
                            )
                for key, pairs in collected.items():
                    source = ".".join((*path, key))
                    kind = force_kind(source, fallback)
                    if kind is not None:
                        candidates.append(
                            make_curve(kind, [a for a, _ in pairs], [b for _, b in pairs], source)
                        )
            for index, item in enumerate(value):
                if isinstance(item, (Mapping, list)):
                    visit(item, (*path, str(index)), inherited)

    visit(document, (), None)
    selected: dict[str, ForceCurve] = {}
    for curve in candidates:
        previous = selected.get(curve.kind)
        if previous is None or len(curve.theta_deg) > len(previous.theta_deg):
            selected[curve.kind] = curve
    return tuple(selected[key] for key in ("full", "isolated", "continuum") if key in selected)


def load_report(root: Path, design: str) -> Report:
    primary = root / "results" / "real_world_nems_clutch_report.json"
    fallback_path = root / "results" / "rotational_z_eff_clutch_report.json"
    path = primary if primary.is_file() else fallback_path
    if not path.is_file():
        raise FileNotFoundError(f"Neither {primary} nor {fallback_path} exists.")
    raw = path.read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(document, (dict, list)):
        raise ValueError("The report must be a JSON object or array.")
    selected = find_design_document(document, design)
    geometry = extract_geometry(selected, design)
    fallback = path == fallback_path
    curves = extract_curves(selected, fallback)
    if not curves:
        LOGGER.warning("No recognizable sampled force curves found; no forces will be invented.")
    return Report(path.resolve(), hashlib.sha256(raw).hexdigest(), design, geometry, curves, fallback)


def parse_arguments() -> argparse.Namespace:
    script = Path(__file__).resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("python", "blender"), default="python")
    parser.add_argument("--project-root", type=Path, default=script.parent.parent)
    parser.add_argument("--design", choices=DESIGNS, default=DESIGNS[0])
    parser.add_argument(
        "--blender",
        default=os.environ.get(
            "BLENDER_BIN", "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"
        ),
    )
    parser.add_argument("--skip-blender", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--resolution", type=int, default=1920)
    parser.add_argument("--resolution-percentage", type=int, default=100)
    parser.add_argument("--angular-segments", type=int, default=384)
    parser.add_argument("--z-exaggeration", type=float, default=2.2)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    args.project_root = args.project_root.expanduser().resolve()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative.")
    if args.samples < 1:
        parser.error("--samples must be positive.")
    if args.resolution < 64:
        parser.error("--resolution must be at least 64 pixels.")
    if not 1 <= args.resolution_percentage <= 100:
        parser.error("--resolution-percentage must be between 1 and 100.")
    if not 48 <= args.angular_segments <= 8192:
        parser.error("--angular-segments must be between 48 and 8192.")
    if not math.isfinite(args.z_exaggeration) or args.z_exaggeration <= 0.0:
        parser.error("--z-exaggeration must be finite and positive.")
    return args


def atomic_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def settings_document(args: argparse.Namespace, report: Report) -> dict[str, Any]:
    return {
        "build_version": BUILD_VERSION,
        "script_sha256": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
        "report": str(report.path),
        "report_sha256": report.sha256,
        "fallback_report": report.fallback,
        "design": report.design,
        "geometry": asdict(report.geometry),
        "force_curve_sources": {curve.kind: curve.source for curve in report.curves},
        "samples": args.samples,
        "resolution": [args.resolution, round(args.resolution * 9.0 / 16.0)],
        "resolution_percentage": args.resolution_percentage,
        "angular_segments": args.angular_segments,
        "z_exaggeration": args.z_exaggeration,
        "physical_dimensions_um": {
            "floor_bottom": -0.650,
            "floor_top": -0.550,
            "membrane_bottom": -0.025,
            "membrane_top": 0.0,
            "pad_top": -0.115,
            "tooth_tip": -0.100,
            "spider_bottom": 0.350,
            "spider_top": 0.460,
            "collar_top": 0.520,
        },
    }


def render_output_directory(args: argparse.Namespace) -> Path:
    return args.project_root / "results" / "real_world_nems_clutch_blender"


def resolve_blender(binary: str) -> str:
    candidate = Path(binary).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(binary)
    if found is None:
        raise FileNotFoundError(
            f"Blender executable not found: {binary!r}. Set BLENDER_BIN or use --blender."
        )
    return found


def run_blender(args: argparse.Namespace) -> None:
    command = [
        resolve_blender(args.blender), "--background",
        "--python", str(Path(__file__).resolve()), "--",
        "--mode", "blender", "--project-root", str(args.project_root),
        "--design", args.design, "--samples", str(args.samples),
        "--resolution", str(args.resolution),
        "--resolution-percentage", str(args.resolution_percentage),
        "--angular-segments", str(args.angular_segments),
        "--z-exaggeration", str(args.z_exaggeration),
        "--max-steps", str(args.max_steps),
    ]
    if args.force:
        command.append("--force")
    LOGGER.info("Launching Blender: %s", subprocess.list2cmdline(command))
    subprocess.run(command, cwd=args.project_root, check=True)


class BlenderBuilder:
    def __init__(self, args: argparse.Namespace, geometry: Geometry) -> None:
        import bpy
        self.bpy: Any = bpy
        self.args = args
        self.geometry = geometry
        self.materials: list[Any] = []
        self.scene: Any = bpy.context.scene

    def initialize(self) -> None:
        bpy = self.bpy
        if tuple(bpy.app.version) < (4, 5, 0):
            raise RuntimeError(f"Blender 4.5+ is required; found {bpy.app.version_string}.")
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        scene = self.scene
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.render.resolution_x = self.args.resolution
        scene.render.resolution_y = round(self.args.resolution * 9.0 / 16.0)
        scene.render.resolution_percentage = self.args.resolution_percentage
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.image_settings.color_depth = "8"
        scene.render.film_transparent = False
        if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = self.args.samples
        elif hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_samples"):
            scene.eevee.taa_samples = self.args.samples
        scene.render.fps = 24
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1.0e-6
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.exposure = 0.4
        scene.world = bpy.data.worlds.new("NEMS_Studio_World")
        scene.world.use_nodes = True
        background = scene.world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (0.045, 0.060, 0.090, 1.0)
        background.inputs["Strength"].default_value = 0.35
        for name, color, metallic, roughness, emission in MATERIAL_SPECS:
            material = bpy.data.materials.new(name)
            material.use_nodes = True
            material.diffuse_color = (*color, 1.0)
            shader = material.node_tree.nodes.get("Principled BSDF")
            shader.inputs["Base Color"].default_value = (*color, 1.0)
            shader.inputs["Metallic"].default_value = metallic
            shader.inputs["Roughness"].default_value = roughness
            shader.inputs["Emission Color"].default_value = (*color, 1.0)
            shader.inputs["Emission Strength"].default_value = emission
            self.materials.append(material)

    def collection(self, name: str) -> Any:
        collection = self.bpy.data.collections.new(name)
        self.scene.collection.children.link(collection)
        return collection

    def sector(
        self, name: str, r0: float, r1: float, a0: float, a1: float,
        z0: float, z1: float, material_index: int, collection: Any,
    ) -> Any:
        values = (r0, r1, a0, a1, z0, z1)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite geometry parameters for {name}.")
        if not 0.0 < r0 < r1 or not z0 < z1 or not 0.0 < a1 - a0 <= 360.0 + EPS:
            raise ValueError(f"Invalid annular prism for {name}: {values}.")
        full = abs((a1 - a0) - 360.0) < 1.0e-8
        count = max(2, math.ceil(self.args.angular_segments * (a1 - a0) / 360.0))
        samples = count if full else count + 1
        vertices: list[tuple[float, float, float]] = []
        for index in range(samples):
            angle = math.radians(a0 + (a1 - a0) * index / count)
            cosine, sine = math.cos(angle), math.sin(angle)
            vertices.extend(
                (
                    (r0 * cosine, r0 * sine, z0 * self.args.z_exaggeration),
                    (r1 * cosine, r1 * sine, z0 * self.args.z_exaggeration),
                    (r0 * cosine, r0 * sine, z1 * self.args.z_exaggeration),
                    (r1 * cosine, r1 * sine, z1 * self.args.z_exaggeration),
                )
            )
        faces: list[tuple[int, ...]] = []
        for index in range(count):
            current = 4 * index
            following = 4 * ((index + 1) % samples)
            faces.extend(
                (
                    (current, following, following + 1, current + 1),
                    (current + 2, current + 3, following + 3, following + 2),
                    (current, current + 2, following + 2, following),
                    (current + 1, following + 1, following + 3, current + 3),
                )
            )
        if not full:
            end = 4 * (samples - 1)
            faces.extend(((0, 1, 3, 2), (end, end + 2, end + 3, end + 1)))
        mesh = self.bpy.data.meshes.new(name + "_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        mesh.validate(verbose=False)
        obj = self.bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        for material in self.materials:
            mesh.materials.append(material)
        for polygon in mesh.polygons:
            polygon.material_index = material_index
            polygon.use_smooth = False
        return obj

    def union(self, seed: Any, operands: Any, name: str) -> Any:
        """Exact solid union, followed by a strict topology/connectivity audit."""
        bpy = self.bpy
        bpy.ops.object.select_all(action="DESELECT")
        seed.select_set(True)
        bpy.context.view_layer.objects.active = seed
        modifier = seed.modifiers.new("Exact_Monolithic_Solid_Union", "BOOLEAN")
        modifier.operation = "UNION"
        modifier.solver = "EXACT"
        modifier.operand_type = "COLLECTION"
        modifier.collection = operands
        if hasattr(modifier, "use_self"):
            modifier.use_self = True
        if hasattr(modifier, "use_hole_tolerant"):
            modifier.use_hole_tolerant = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        for obj in list(operands.objects):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.data.collections.remove(operands)
        seed.name = name
        self.audit_mesh(seed)
        seed["mechanically_connected"] = True
        seed["solid_component_count"] = 1
        seed["physical_unit"] = "micrometre"
        seed["presentation_z_exaggeration"] = self.args.z_exaggeration
        return seed

    def audit_mesh(self, obj: Any) -> None:
        import bmesh
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            if not bm.verts or not bm.faces:
                raise RuntimeError(f"{obj.name}: construction produced an empty mesh.")
            bad_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
            if bad_edges:
                raise RuntimeError(
                    f"{obj.name}: construction produced {bad_edges} nonmanifold edges; "
                    "refusing floating geometry."
                )
            unseen = set(bm.verts)
            components = 0
            while unseen:
                components += 1
                start = unseen.pop()
                stack = [start]
                while stack:
                    vertex = stack.pop()
                    for edge in vertex.link_edges:
                        neighbor = edge.other_vert(vertex)
                        if neighbor in unseen:
                            unseen.remove(neighbor)
                            stack.append(neighbor)
            if components != 1:
                raise RuntimeError(
                    f"{obj.name}: {components} disconnected mesh components; expected one solid assembly."
                )
            volume = bm.calc_volume(signed=False)
            if not math.isfinite(volume) or volume <= 0.0:
                raise RuntimeError(f"{obj.name}: invalid solid volume.")
        finally:
            bm.free()

    def lattice_mesh(
        self,
        name: str,
        radial_nodes: Sequence[float],
        angular_nodes: Sequence[float],
        height_nodes: Sequence[float],
        cell_material: Callable[[float, float, float], int | None],
        collection: Any,
    ) -> Any:
        """Emit only the boundary of occupied conforming cylindrical cells."""
        axes: list[tuple[float, ...]] = []
        for label, nodes in (
            ("radius", radial_nodes), ("angle", angular_nodes), ("height", height_nodes)
        ):
            axis = tuple(sorted({finite_number(value, label) for value in nodes}))
            if len(axis) < 2:
                raise ValueError(f"{name}: {label} lattice requires at least two nodes.")
            axes.append(axis)
        radii, angles, heights = axes
        if radii[0] <= 0.0:
            raise ValueError(f"{name}: lattice radii must be positive.")
        if angles[0] != 0.0 or angles[-1] != 360.0:
            raise ValueError(f"{name}: angular lattice must span exactly 0 to 360 degrees.")
        if any(right - left >= 180.0 for left, right in zip(angles, angles[1:])):
            raise ValueError(f"{name}: angular cells must span less than 180 degrees.")
        exaggeration = finite_number(self.args.z_exaggeration, "z exaggeration")
        if exaggeration <= 0.0:
            raise ValueError("z exaggeration must be positive.")

        nr, na, nz = len(radii) - 1, len(angles) - 1, len(heights) - 1
        occupied: dict[tuple[int, int, int], int] = {}
        for i in range(nr):
            radius = radii[i] + (radii[i + 1] - radii[i]) / 2.0
            for j in range(na):
                angle = angles[j] + (angles[j + 1] - angles[j]) / 2.0
                for k in range(nz):
                    height = heights[k] + (heights[k + 1] - heights[k]) / 2.0
                    material = cell_material(radius, angle, height)
                    if material is None:
                        continue
                    if (
                        isinstance(material, bool) or not isinstance(material, int)
                        or not 0 <= material < len(self.materials)
                    ):
                        raise ValueError(f"{name}: invalid cell material {material!r}.")
                    occupied[(i, j, k)] = material
        if not occupied:
            raise ValueError(f"{name}: lattice contains no occupied cells.")

        vertices: list[tuple[float, float, float]] = []
        vertex_ids: dict[tuple[int, int, int], int] = {}
        faces: list[tuple[int, ...]] = []
        face_materials: list[int] = []

        def vertex_id(node: tuple[int, int, int]) -> int:
            i, j, k = node
            key = (i, j % na, k)
            if key not in vertex_ids:
                phi = math.radians(angles[key[1]])
                vertex_ids[key] = len(vertices)
                vertices.append((
                    radii[i] * math.cos(phi),
                    radii[i] * math.sin(phi),
                    heights[k] * exaggeration,
                ))
            return vertex_ids[key]

        def emit(
            nodes: tuple[tuple[int, int, int], ...],
            normal: tuple[float, float, float],
            material: int,
        ) -> None:
            face = tuple(vertex_id(node) for node in nodes)
            p0, p1, p2 = (vertices[index] for index in face[:3])
            u = tuple(b - a for a, b in zip(p0, p1))
            v = tuple(b - a for a, b in zip(p0, p2))
            cross = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            dot = sum(a * b for a, b in zip(cross, normal))
            if not math.isfinite(dot) or dot == 0.0:
                raise ValueError(f"{name}: degenerate lattice boundary face.")
            if dot < 0.0:
                face = tuple(reversed(face))
            faces.append(face)
            face_materials.append(material)

        for (i, j, k), material in occupied.items():
            mid_phi = math.radians((angles[j] + angles[j + 1]) / 2.0)
            radial_normal = (math.cos(mid_phi), math.sin(mid_phi), 0.0)
            for step in (-1, 1):
                if (i + step, j, k) not in occupied:
                    boundary = i if step == -1 else i + 1
                    emit(
                        (
                            (boundary, j, k), (boundary, j + 1, k),
                            (boundary, j + 1, k + 1), (boundary, j, k + 1),
                        ),
                        tuple(step * value for value in radial_normal),
                        material,
                    )
                if (i, (j + step) % na, k) not in occupied:
                    boundary = j if step == -1 else j + 1
                    phi = math.radians(angles[boundary])
                    emit(
                        (
                            (i, boundary, k), (i + 1, boundary, k),
                            (i + 1, boundary, k + 1), (i, boundary, k + 1),
                        ),
                        (-step * math.sin(phi), step * math.cos(phi), 0.0),
                        material,
                    )
                if (i, j, k + step) not in occupied:
                    boundary = k if step == -1 else k + 1
                    emit(
                        (
                            (i, j, boundary), (i + 1, j, boundary),
                            (i + 1, j + 1, boundary), (i, j + 1, boundary),
                        ),
                        (0.0, 0.0, float(step)),
                        material,
                    )

        mesh = self.bpy.data.meshes.new(name + "_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        for material in self.materials:
            mesh.materials.append(material)
        for polygon, material in zip(mesh.polygons, face_materials):
            polygon.material_index = material
            polygon.use_smooth = False
        obj = self.bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        self.audit_mesh(obj)
        obj["mechanically_connected"] = True
        obj["solid_component_count"] = 1
        obj["physical_unit"] = "micrometre"
        obj["presentation_z_exaggeration"] = exaggeration
        obj["construction"] = "Conforming cylindrical lattice boundary"
        return obj

    def build_stator(self) -> Any:
        g = self.geometry
        main = self.collection("Monolithic_Stator")
        radial_nodes = {
            g.stator_inner, g.r_min, g.r_max, g.stator_outer,
            *(endpoint for interval in g.rings for endpoint in interval),
        }
        angular_nodes = {
            *(360.0 * index / self.args.angular_segments
              for index in range(self.args.angular_segments + 1)),
            0.0, 5.0, 55.0, 360.0,
            *(90.0 * index for index in range(4)),
            *(90.0 * index + g.aperture_deg for index in range(4)),
        }

        def material(radius: float, phi: float, height: float) -> int | None:
            if -0.650 <= height < -0.550:
                return 0
            if g.stator_inner <= radius < g.r_min and -0.550 <= height < 0.0:
                return 1
            if g.r_max <= radius < g.stator_outer:
                if -0.550 <= height < -0.115:
                    return 1
                if -0.115 <= height < 0.0 and not 5.0 <= phi <= 55.0:
                    return 1
            local_phi = phi % 90.0
            in_ring = any(left <= radius < right for left, right in g.rings)
            if local_phi < g.aperture_deg:
                if in_ring and -0.025 <= height < 0.0:
                    return 2
            else:
                if in_ring:
                    if -0.115 <= height < 0.0:
                        return 2
                    if -0.550 <= height < -0.115:
                        return 3
                if (
                    -0.550 <= height < -0.115
                    and any(left <= radius < right for left, right in g.slots)
                ):
                    return 4
            return None

        return self.lattice_mesh(
            "MONOLITHIC_STATOR_SOLID",
            sorted(radial_nodes), sorted(angular_nodes),
            (-0.650, -0.550, -0.115, -0.025, 0.0),
            material, main,
        )

    def build_rotor(self) -> tuple[Any, Any]:
        g = self.geometry
        main = self.collection("Monolithic_Rotor")
        fingers = tuple(
            (
                60.0 + (index + 0.5) * 300.0 / 24.0 - 1.0,
                60.0 + (index + 0.5) * 300.0 / 24.0 + 1.0,
            )
            for index in range(24)
        )
        radial_nodes = {
            g.rotor_hub_inner, g.rotor_hub_outer,
            g.rotor_rim_inner, g.rotor_rim_outer, g.r_max + 0.22,
            *(endpoint for interval in g.teeth for endpoint in interval),
        }
        angular_nodes = {
            *(360.0 * index / self.args.angular_segments
              for index in range(self.args.angular_segments + 1)),
            0.0, 60.0, 360.0,
            *(90.0 * index for index in range(4)),
            *(90.0 * index + g.tooth_arc_deg for index in range(4)),
            *(endpoint for interval in fingers for endpoint in interval),
        }

        def material(radius: float, phi: float, height: float) -> int | None:
            if (
                g.rotor_hub_inner <= radius < g.rotor_hub_outer
                and 0.350 <= height < 0.520
            ):
                return 8
            sector_index = int(phi // 90.0)
            in_spoke = phi % 90.0 < g.tooth_arc_deg
            if 0.350 <= height < 0.460:
                if (
                    g.rotor_rim_inner <= radius < g.rotor_rim_outer
                    and 60.0 <= phi < 360.0
                ):
                    return 8
                if (
                    g.rotor_rim_outer <= radius < g.r_max + 0.22
                    and any(left <= phi < right for left, right in fingers)
                ):
                    return 8
                if in_spoke and g.rotor_hub_outer <= radius < g.rotor_rim_outer:
                    return 7 if sector_index == 0 else 8
            if (
                -0.100 <= height < 0.350 and in_spoke
                and any(left <= radius < right for left, right in g.teeth)
            ):
                return 5 if sector_index == 0 else 6
            return None

        rotor = self.lattice_mesh(
            "MONOLITHIC_ROTOR_SOLID",
            sorted(radial_nodes), sorted(angular_nodes),
            (-0.100, 0.350, 0.460, 0.520),
            material, main,
        )
        root = self.bpy.data.objects.new("Rotor_Rigid_Rotation_Axis", None)
        main.objects.link(root)
        rotor.parent = root
        root["rotation_axis"] = "Z"
        root["fixed_physical_tooth_tip_um"] = -0.100
        rotor["teeth_per_sector"] = len(g.teeth)
        rotor["comb_finger_count"] = 24
        return rotor, root

    def add_studio(self) -> Any:
        from mathutils import Vector
        bpy = self.bpy
        studio = self.collection("Studio_Cameras_And_Lights")
        for name, location, power, size, color in (
            ("Key_Softbox", (1.8, -2.6, 4.5), 650.0, 3.0, (0.80, 0.90, 1.0)),
            ("Warm_Fill", (-3.0, -0.8, 2.0), 420.0, 3.0, (1.0, 0.78, 0.54)),
            ("Rim_Softbox", (1.0, 3.2, 3.0), 850.0, 2.4, (0.60, 0.80, 1.0)),
            ("Macro_Fill", (3.0, 0.4, 1.8), 180.0, 2.0, (1.0, 0.94, 0.80)),
        ):
            light = bpy.data.lights.new(name, "AREA")
            light.energy = power
            light.shape = "DISK"
            light.size = size
            light.color = color
            obj = bpy.data.objects.new(name, light)
            studio.objects.link(obj)
            obj.location = location
            obj.rotation_euler = (Vector((0.0, 0.0, 0.0)) - obj.location).to_track_quat("-Z", "Y").to_euler()
        camera_data = bpy.data.cameras.new("Publication_Camera")
        camera_data.clip_start = 0.001
        camera_data.clip_end = 100.0
        camera_data.sensor_width = 36.0
        camera_data.dof.use_dof = False
        camera = bpy.data.objects.new("Publication_Camera", camera_data)
        studio.objects.link(camera)
        self.scene.camera = camera
        return camera

    def position_camera(
        self, camera: Any, position: tuple[float, float, float],
        target: tuple[float, float, float], lens: float,
    ) -> None:
        from mathutils import Vector
        camera.location = position
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = lens

    def render(self, root: Any, camera: Any, path: Path, theta: float, macro: bool) -> None:
        root.rotation_euler.z = math.radians(theta)
        root["theta_deg"] = theta
        if macro:
            self.position_camera(camera, (2.35, 0.10, 0.58), (0.78, 0.50, -0.15), 44.0)
        else:
            self.position_camera(camera, (3.95, -3.65, 2.95), (0.0, 0.0, -0.05), 40.0)
        self.bpy.context.view_layer.update()
        temporary = path.with_name(path.stem + ".temporary.png")
        self.scene.render.filepath = str(temporary)
        self.bpy.ops.render.render(write_still=True)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError(f"Blender failed to write {temporary}.")
        temporary.replace(path)


def blender_mode(args: argparse.Namespace, report: Report) -> None:
    if args.skip_blender:
        raise ValueError("--skip-blender is only applicable in --mode python.")
    output = render_output_directory(args)
    output.mkdir(parents=True, exist_ok=True)
    builder = BlenderBuilder(args, report.geometry)
    builder.initialize()
    stator = builder.build_stator()
    rotor, root = builder.build_rotor()
    camera = builder.add_studio()
    scene = builder.scene
    scene["design"] = report.design
    scene["report_sha256"] = report.sha256
    scene["physical_landing_pad_clearance_nm"] = 15.0
    scene["stator_component_count"] = 1
    scene["rotor_component_count"] = 1
    scene["assembly_count"] = 2
    scene["z_exaggeration_is_visual_only"] = True
    g = report.geometry
    states = (
        (OUTPUT_NAMES[0], g.repulsive_theta, False),
        (OUTPUT_NAMES[1], g.straddling_theta, False),
        (OUTPUT_NAMES[2], 48.0, False),
        (OUTPUT_NAMES[3], g.straddling_theta, True),
    )
    limit = min(args.max_steps, len(states)) if args.max_steps else len(states)
    rendered: list[str] = []
    for filename, theta, macro in states[:limit]:
        LOGGER.info("Rendering %s at theta=%g degrees", filename, theta)
        builder.render(root, camera, output / filename, theta, macro)
        rendered.append(filename)
    root.rotation_euler.z = math.radians(g.straddling_theta)
    builder.position_camera(camera, (3.95, -3.65, 2.95), (0.0, 0.0, -0.05), 40.0)
    builder.bpy.context.view_layer.update()
    scene_path = output / "real_world_nems_clutch_scene.blend"
    temporary_scene = output / "real_world_nems_clutch_scene.temporary.blend"
    builder.bpy.ops.wm.save_as_mainfile(filepath=str(temporary_scene))
    temporary_scene.replace(scene_path)
    manifest = settings_document(args, report)
    manifest["rendered_files"] = rendered
    manifest["complete"] = limit == len(states)
    manifest["topology_audit"] = {
        "stator": {"components": 1, "vertices": len(stator.data.vertices), "nonmanifold_edges": 0},
        "rotor": {"components": 1, "vertices": len(rotor.data.vertices), "nonmanifold_edges": 0},
        "solver": "Conforming cylindrical lattice boundary with shared vertex IDs",
        "structural_overlap_nm": 0.0,
        "active_gap_modified": False,
    }
    atomic_json(output / "build_manifest.json", manifest)


def force_at(curve: ForceCurve, theta: float) -> float | None:
    import bisect
    x, y = curve.theta_deg, curve.force_n
    if not x or theta < x[0] or theta > x[-1]:
        return None
    index = bisect.bisect_left(x, theta)
    if index < len(x) and math.isclose(x[index], theta, abs_tol=1.0e-10):
        return y[index]
    if index == 0 or index == len(x):
        return None
    span = x[index] - x[index - 1]
    if span <= 0.0:
        raise ValueError("Non-increasing force grid.")
    fraction = (theta - x[index - 1]) / span
    return y[index - 1] + fraction * (y[index] - y[index - 1])


def force_label(curves: Mapping[str, ForceCurve], kind: str, theta: float) -> str:
    curve = curves.get(kind)
    if curve is None:
        return "not reported"
    value = force_at(curve, theta)
    return "outside report grid" if value is None else f"{value * 1.0e12:+.5g} pN"


def save_provenance(
    root: Path, plot: Path, report: Report, args: argparse.Namespace
) -> None:
    """Use the project's logger when available; always retain an exact sidecar."""
    metadata = settings_document(args, report)
    metadata["plot"] = str(plot)
    metadata["plot_sha256"] = hashlib.sha256(plot.read_bytes()).hexdigest()
    metadata["interpolation"] = "piecewise linear; no extrapolation"
    metadata["missing_force_policy"] = "explicitly marked; never synthesized"
    atomic_json(plot.with_suffix(plot.suffix + ".provenance.json"), metadata)
    root_string = str(root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)
    try:
        module = importlib.import_module("utils.metrics_logger")
    except ModuleNotFoundError as exc:
        if exc.name not in {"utils", "utils.metrics_logger"}:
            raise
        LOGGER.warning(
            "utils.metrics_logger is unavailable; wrote self-contained provenance for %s.", plot.name
        )
        return
    function: Callable[..., Any] = module.save_plot_provenance
    signature = inspect.signature(function)
    values: dict[str, Any] = {
        "plotpath": plot, "figurepath": plot, "figpath": plot, "outputpath": plot,
        "filepath": plot, "path": plot, "filename": str(plot), "plotfile": str(plot),
        "scriptpath": Path(__file__).resolve(), "script": str(Path(__file__).resolve()),
        "scriptname": Path(__file__).name, "source": str(Path(__file__).resolve()),
        "projectroot": root, "root": root,
        "datapaths": [report.path], "inputpaths": [report.path],
        "sourcefiles": [str(report.path)], "inputfiles": [str(report.path)],
        "datafiles": [str(report.path)], "reportpath": report.path,
        "datasource": str(report.path),
        "columnsused": [curve.kind for curve in report.curves] or ["geometry"],
        "solvername": "real_world_nems_clutch_blender",
        "solverparameters": metadata,
        "metadata": metadata, "provenance": metadata, "params": metadata,
        "parameters": metadata, "extra": metadata, "extrainfo": metadata,
        "metrics": metadata, "design": report.design,
        "description": "Mechanically connected real-world monolithic NEMS clutch",
    }
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for parameter in signature.parameters.values():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        key = normalized(parameter.name)
        if key not in values:
            if parameter.default is inspect.Parameter.empty:
                raise TypeError(
                    f"Unsupported required save_plot_provenance parameter {parameter.name!r}; "
                    "the exact provenance sidecar has already been saved."
                )
            continue
        value = values[key]
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[parameter.name] = value
    signature.bind(*positional, **keywords)
    function(*positional, **keywords)


def publication_figure(args: argparse.Namespace, report: Report) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    output = render_output_directory(args)
    figures = args.project_root / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    paths = [output / name for name in OUTPUT_NAMES]
    missing = [str(path) for path in paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("Publication requires all four renders:\n" + "\n".join(missing))
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.titlesize": 12, "axes.labelsize": 10,
        "pdf.fonttype": 42, "ps.fonttype": 42,
    })
    fig, axes = plt.subplots(3, 2, figsize=(18.0, 14.5))
    g = report.geometry
    curves = {curve.kind: curve for curve in report.curves}
    angles = (g.repulsive_theta, g.straddling_theta, 48.0, g.straddling_theta)
    titles = (
        "A  Repulsive aperture state",
        "B  Straddling the elevation step",
        "C  Attractive landing-pad state",
        "D  Sector 0: mechanically connected step cutaway",
    )
    for axis, path, theta, title in zip(axes.flat, paths, angles, titles):
        image = mpimg.imread(path)
        if image.size == 0 or image.ndim not in (2, 3):
            raise ValueError(f"Invalid rendered image: {path}.")
        axis.imshow(image)
        axis.set_axis_off()
        axis.set_title(title, loc="left", fontweight="bold", pad=9)
        axis.text(
            0.015, 0.025,
            f"$\\theta={theta:g}^\\circ$  |  Full $F_z$: {force_label(curves, 'full', theta)}\n"
            f"Pad gap: 15 nm  |  minimum radial side gap: {g.radial_clearance_nm:.5g} nm",
            transform=axis.transAxes, fontsize=9, color="white",
            va="bottom", bbox={"facecolor": "#102333", "alpha": 0.88, "edgecolor": "none", "pad": 6},
        )
        if path.name == OUTPUT_NAMES[3]:
            axis.text(
                0.015, 0.975,
                f"{len(g.teeth)} emerald shanks/spoke; tips −100 nm\n"
                "Spider underside +350 nm; ribs 0 nm\n"
                "Pad −115 nm; release floor top −550 nm",
                transform=axis.transAxes, va="top", color="white", fontsize=9,
                bbox={"facecolor": "#102333", "alpha": 0.88, "edgecolor": "none", "pad": 6},
            )

    force_axis = axes[2, 0]
    force_axis.set_title("E  Reported normal-force comparison", loc="left", fontweight="bold")
    styles = {
        "full": ("Full monolithic connected NEMS", "#008b73", "-", 2.4),
        "isolated": ("Isolated active-zone NEMS", "#275da8", "--", 2.0),
        "continuum": ("Continuum Lifshitz–PFA", "#ac6920", ":", 2.0),
    }
    for kind, curve in curves.items():
        label, color, linestyle, width = styles[kind]
        force_axis.plot(
            curve.theta_deg, [value * 1.0e12 for value in curve.force_n],
            label=label, color=color, linestyle=linestyle, linewidth=width,
            marker="o" if len(curve.theta_deg) < 12 else None,
        )
    force_axis.axhline(0.0, color="#77818a", linewidth=0.8)
    force_axis.axvline(g.aperture_deg, color="#999999", linestyle=":", linewidth=0.8)
    force_axis.set_xlabel(r"Rotor angle $\theta$ (degrees)")
    force_axis.set_ylabel(r"Normal force $F_z$ (pN; report sign convention)")
    force_axis.grid(alpha=0.20)
    force_axis.xaxis.set_major_locator(MaxNLocator(7))
    if curves:
        force_axis.legend(loc="best", fontsize=9, framealpha=0.95)
    else:
        force_axis.text(
            0.5, 0.5, "No sampled force series recognized in this report.\nNo forces synthesized.",
            ha="center", va="center", transform=force_axis.transAxes,
        )
    absent = [styles[kind][0] for kind in styles if kind not in curves]
    if absent:
        force_axis.text(
            0.02, -0.20, "Not reported: " + "; ".join(absent),
            transform=force_axis.transAxes, fontsize=8, color="#9a3428", wrap=True,
        )

    table_axis = axes[2, 1]
    table_axis.set_axis_off()
    table_axis.set_title(
        "F  Exact monolithic NEMS engineering & force audit",
        loc="left", fontweight="bold", pad=12,
    )
    rows: list[list[str]] = [
        ["Design / Cantor order", f"{report.design} / N={g.cantor_order}"],
        ["Radial active span", f"{g.r_min:.7g}–{g.r_max:.7g} µm"],
        ["Cantor ribs / teeth", f"{len(g.rings)} ribs; {len(g.teeth)} teeth × 4 sectors"],
        ["Aperture / tooth arc", f"{g.aperture_deg:g}° / {g.tooth_arc_deg:g}°"],
        ["Stator floor thickness", "100 nm; top −550 nm"],
        ["Elevated membrane", "25 nm; top 0 nm; doubly clamped"],
        ["Landing pedestal height", "435 nm; top −115 nm"],
        ["Rotor shank span", "−100 to +350 nm; height 450 nm"],
        ["Spider / collar top", "+460 nm / +520 nm"],
        ["Attractive tip–pad gap", "15 nm (physical; not exaggerated)"],
        ["Minimum radial tooth gap", f"{g.radial_clearance_nm:.7g} nm"],
        ["Connectivity audit", "1 conforming-lattice rotor + 1 stator"],
        ["Rotary comb fingers", "24; attached to rotor actuator rim"],
        ["Display z exaggeration", f"{args.z_exaggeration:g}× (geometry presentation only)"],
    ]
    for label, theta in (
        ("Aperture", g.repulsive_theta),
        ("Step", g.straddling_theta),
        ("Landing", 48.0),
    ):
        rows.append(
            [f"Full Fz, {label} ({theta:g}°)", force_label(curves, "full", theta)]
        )
    if "full" in curves and "isolated" in curves:
        full = force_at(curves["full"], g.straddling_theta)
        isolated = force_at(curves["isolated"], g.straddling_theta)
        if full is not None and isolated is not None:
            rows.append(["Full − isolated at step", f"{(full - isolated) * 1.0e12:+.7g} pN"])
    table = table_axis.table(
        cellText=rows, colLabels=["Engineering / force quantity", "Physical value / audit"],
        loc="upper center", cellLoc="left", colLoc="left", colWidths=[0.48, 0.52],
        bbox=[0.0, 0.04, 1.0, 0.91],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.2)
    for (row, _column), cell in table.get_celld().items():
        cell.set_edgecolor("#d4dde3")
        cell.set_linewidth(0.45)
        if row == 0:
            cell.set_facecolor("#18354a")
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")
        else:
            cell.set_facecolor("#edf3f6" if row % 2 == 0 else "white")
    table_axis.text(
        0.0, -0.025,
        "Force samples: report values; displayed intermediate angles use linear interpolation.\n"
        "Shared lattice vertices; no structural overlap; active clearances are unchanged.",
        transform=table_axis.transAxes, fontsize=8, va="top",
    )
    fig.suptitle(
        "Real-World Monolithic On-Chip NEMS\n"
        "Stepped-Elevation Concentric Cantor Casimir Clutch",
        fontsize=19, fontweight="bold", y=0.988,
    )
    fig.text(
        0.035, 0.014,
        f"Source: {report.path.name} | {report.design} | report SHA-256 {report.sha256[:16]}…"
        " | Conforming-lattice connected assemblies; physical dimensions in nm/µm.",
        fontsize=8, color="#435363",
    )
    fig.subplots_adjust(left=0.035, right=0.985, top=0.93, bottom=0.075, hspace=0.30, wspace=0.13)
    png = figures / "fig_real_world_nems_clutch_blender.png"
    pdf = figures / "fig_real_world_nems_clutch_blender.pdf"
    try:
        fig.savefig(png, dpi=200, facecolor="white")
        fig.savefig(pdf, facecolor="white")
    finally:
        plt.close(fig)
    copied_png = output / png.name
    shutil.copy2(png, copied_png)
    save_provenance(args.project_root, png, report, args)
    save_provenance(args.project_root, pdf, report, args)
    shutil.copy2(
        png.with_suffix(png.suffix + ".provenance.json"),
        copied_png.with_suffix(copied_png.suffix + ".provenance.json"),
    )
    LOGGER.info("Publication figure saved: %s and %s", png, pdf)


def python_mode(args: argparse.Namespace, report: Report) -> None:
    if args.skip_blender and 1 <= args.max_steps <= 5:
        LOGGER.info(
            "Report validation successful: %s; %s; %d rings, %d teeth/sector; "
            "radial clearance %.7g nm; %d force series.",
            report.path, report.design, len(report.geometry.rings),
            len(report.geometry.teeth), report.geometry.radial_clearance_nm, len(report.curves),
        )
        return
    output = render_output_directory(args)
    expected = settings_document(args, report)
    manifest_path = output / "build_manifest.json"
    cache_valid = False
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cache_valid = (
                isinstance(manifest, dict)
                and manifest.get("complete") is True
                and all(manifest.get(key) == value for key, value in expected.items())
                and all((output / name).is_file() for name in OUTPUT_NAMES)
                and (output / "real_world_nems_clutch_scene.blend").is_file()
            )
        except (ValueError, OSError):
            cache_valid = False
    if not args.skip_blender and (args.force or not cache_valid):
        run_blender(args)
        if args.max_steps and args.max_steps < len(OUTPUT_NAMES):
            LOGGER.info(
                "Bounded render probe finished (%d views); publication composition deferred.",
                args.max_steps,
            )
            return
    if args.skip_blender and not cache_valid:
        raise RuntimeError(
            "--skip-blender requires a complete matching build manifest and four renders. "
            "Run without --skip-blender, or use --skip-blender --max-steps 1 for validation only."
        )
    publication_figure(args, report)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_arguments()
    try:
        report = load_report(args.project_root, args.design)
        if args.mode == "blender":
            blender_mode(args, report)
        else:
            python_mode(args, report)
    except Exception:
        LOGGER.exception("NEMS clutch build failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
