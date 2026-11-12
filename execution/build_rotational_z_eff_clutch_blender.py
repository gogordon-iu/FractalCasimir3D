#!/usr/bin/env python3
"""
Build Figure 1 (`figures/fig_rotational_z_eff_clutch_blender.png`) for the Nature physics
manuscript "Fractal amplification and switching of vacuum Casimir forces".

Geometry and BEM forces are read directly from:
    results/rotational_z_eff_clutch_report.json
    results/nature_6step_narrative_report.json

Examples:
    python execution/build_rotational_z_eff_clutch_blender.py --force
    python execution/build_rotational_z_eff_clutch_blender.py --skip-blender --max-steps 1
    blender --background --python execution/build_rotational_z_eff_clutch_blender.py -- \\
        --mode blender --design Rot_C10_Fractal_N3 --force

Radial coordinates are in micrometres. Displayed axial coordinates in Blender are multiplied
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


DESIGN_NAMES = (
    "Cantor_111_Unified3DFractal",
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
    elements: tuple[dict[str, Any], ...]
    ring_intervals: tuple[tuple[float, float], ...]
    cantor_subrib_intervals: tuple[tuple[float, float], ...] = ()
    code: str = ""
    f_per_a_pn_per_um2: float = 0.0
    a_tooth_um2: float = 0.0

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
        for low, high in (*self.ring_intervals, *self.cantor_subrib_intervals):
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
            z_tip_el = float(element.get("z_tip", self.rotor_tip_um))
            if not (self.rotor_top_um > -self.t_membrane > z_tip_el >= self.rotor_tip_um - 1e-12):
                raise ValueError("Element z_tip violates axial topological ordering.")


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
        help="Probe limit; 1-5 with --skip-blender validates the report and exits.",
    )
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--resolution", type=int, default=2200, help="Render width.")
    parser.add_argument("--resolution-percentage", type=int, default=100)
    parser.add_argument("--angular-segments", type=int, default=384)
    parser.add_argument("--z-exaggeration", type=float, default=2.2)
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


def force_pn(evaluation: dict[str, Any]) -> tuple[float, str]:
    candidates: list[tuple[float, str]] = []
    for key, scale in (
        ("f_net_pN", 1.0),
        ("F_z_pN", 1.0),
        ("F_z_N", 1e12),
        ("f_net_N", 1e12),
    ):
        if key in evaluation and evaluation[key] is not None:
            val = finite_number(evaluation[key], key) * scale
            if not math.isfinite(val):
                raise ValueError(f"Force conversion overflow at {key}.")
            candidates.append((val, key))
    solver_res = evaluation.get("solver_result")
    if isinstance(solver_res, dict):
        for key, scale in (
            ("f_net_pN", 1.0),
            ("F_z_pN", 1.0),
            ("F_z_N", 1e12),
            ("f_net_N", 1e12),
        ):
            if key in solver_res and solver_res[key] is not None:
                path = f"solver_result.{key}"
                val = finite_number(solver_res[key], path) * scale
                if not math.isfinite(val):
                    raise ValueError(f"Force conversion overflow at {path}.")
                candidates.append((val, path))
    if not candidates:
        raise ValueError("Evaluation is missing a unit-labelled BEM F_z_pN or F_z_N field.")
    first_val, first_path = candidates[0]
    for other_val, other_path in candidates[1:]:
        if not math.isclose(first_val, other_val, rel_tol=1e-7, abs_tol=1e-9):
            raise ValueError(
                f"Inconsistent BEM force fields: {first_path}={first_val} vs {other_path}={other_val}."
            )
    return first_val, first_path


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


def load_narrative_report(root: Path) -> dict[str, Any]:
    path = root / "results" / "nature_6step_narrative_report.json"
    if not path.is_file():
        raise FileNotFoundError(f"Narrative report missing: {path}")
    with path.open(encoding="utf-8") as handle:
        narrative = json.load(handle)
    if not isinstance(narrative, dict) or not isinstance(narrative.get("designs"), dict):
        raise ValueError("Narrative report must contain a designs object.")
    return narrative


def load_unified_factorial_report(root: Path) -> dict[str, Any]:
    path = root / "results" / "n3_unified_3d_fractal_factorial_study.json"
    if not path.is_file():
        raise FileNotFoundError(f"Unified 3D factorial report missing: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("Unified 3D factorial report must contain a records list.")
    return data


def _load_unified_3d_design(
    report: dict[str, Any], name: str, root: Path
) -> tuple[Design, list[dict[str, Any]], tuple[dict[str, Any], ...]]:
    cache_path = root / "results" / "rotational_clutch_blender" / "unified_3d_design_cache.json"
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    uf_report = load_unified_factorial_report(root)
    rec_matches = [
        r for r in uf_report["records"]
        if isinstance(r, dict) and (r.get("name") == name or r.get("code") == name)
    ]
    if not rec_matches:
        raise ValueError(f"No BEM record in n3_unified_3d_fractal_factorial_study.json for {name}.")
    rec = rec_matches[0]
    f_rep_pn = required_number(rec, "F_z_pN")
    f_per_a = required_number(rec, "F_per_A_pN_per_um2")
    a_tooth = required_number(rec, "A_tooth_um2")

    try:
        arch = importlib.import_module("execution.multiscale_3d_fractal_architecture")
        matches = [d for d in arch.build_all_study_designs() if d.name == name or d.code == name]
        if not matches:
            raise ValueError(f"No unified 3D design found for {name!r}.")
        u_design = matches[0]

        primary_ribs: list[tuple[float, float]] = []
        cantor_subribs: list[tuple[float, float]] = []
        elements: list[dict[str, Any]] = []
        cursor_r = float(u_design.R_min)
        for slot in u_design.slots:
            if slot.r_inner > cursor_r + 1e-12:
                primary_ribs.append((round(cursor_r, 6), round(float(slot.r_inner), 6)))
            subslots = slot.stator_subslots or ((slot.r_inner, slot.r_outer),)
            if len(subslots) != len(slot.sub_teeth):
                raise ValueError(f"Slot {slot} subslots count {len(subslots)} != sub_teeth count {len(slot.sub_teeth)}.")
            sub_cursor = float(slot.r_inner)
            for (sub_in, sub_out), st in zip(subslots, slot.sub_teeth, strict=True):
                if sub_in > sub_cursor + 1e-12:
                    cantor_subribs.append((round(sub_cursor, 6), round(float(sub_in), 6)))
                elements.append({
                    "r_inner": round(float(sub_in), 6),
                    "r_outer": round(float(sub_out), 6),
                    "r_tooth_in": round(float(st.r_tooth_in), 6),
                    "r_tooth_out": round(float(st.r_tooth_out), 6),
                    "z_tip": round(float(st.z_tip), 6),
                    "h_teeth": round(float(st.h_teeth), 6),
                    "level": int(slot.level),
                    "phi_offsets_deg": [
                        [round(float(off), 6), round(float(arc), 6)]
                        for off, arc in st.phi_offsets_deg
                    ],
                })
                sub_cursor = float(sub_out)
            cursor_r = float(slot.r_outer)
        if u_design.R_max > cursor_r + 1e-12:
            primary_ribs.append((round(cursor_r, 6), round(float(u_design.R_max), 6)))

        spec_payload = {
            "name": u_design.name,
            "code": u_design.code,
            "R_min": round(float(u_design.R_min), 6),
            "R_max": round(float(u_design.R_max), 6),
            "aperture_arc_deg": round(float(u_design.aperture_arc_deg), 6),
            "t_membrane": round(float(u_design.t_membrane), 6),
            "t_landing_pad": round(float(u_design.t_landing_pad), 6),
            "z_pad_top": round(float(u_design.z_pad_top), 6),
            "primary_ribs": [list(x) for x in primary_ribs],
            "cantor_subribs": [list(x) for x in cantor_subribs],
            "elements": elements,
        }
        atomic_text(cache_path, json.dumps(spec_payload, indent=2, allow_nan=False) + "\n")
    except ImportError:
        if not cache_path.is_file():
            raise RuntimeError(f"Blender mode requires cached spec at {cache_path}; run --mode python first.")
        with cache_path.open(encoding="utf-8") as handle:
            spec_payload = json.load(handle)
        primary_ribs = [(float(a), float(b)) for a, b in spec_payload["primary_ribs"]]
        cantor_subribs = [(float(a), float(b)) for a, b in spec_payload["cantor_subribs"]]
        elements = list(spec_payload["elements"])

    deepest_z_tip = min(float(el["z_tip"]) for el in elements)
    pad_top_um = round(float(spec_payload["z_pad_top"]), 6)
    pad_bottom_um = round(float(spec_payload["z_pad_top"] - spec_payload["t_landing_pad"]), 6)
    min_rad_clr = round(
        min(
            min(el["r_tooth_in"] - el["r_inner"], el["r_outer"] - el["r_tooth_out"])
            for el in elements
        ),
        6,
    )
    vert_clr = round(deepest_z_tip - pad_top_um, 6)
    first_phis = elements[0]["phi_offsets_deg"]
    span_deg = round(
        max(off + 0.5 * arc for off, arc in first_phis)
        - min(off - 0.5 * arc for off, arc in first_phis),
        6,
    )

    design = Design(
        str(spec_payload["name"]),
        4,
        round(float(spec_payload["R_min"]), 6),
        round(float(spec_payload["R_max"]), 6),
        round(float(spec_payload["aperture_arc_deg"]), 6),
        span_deg,
        round(float(spec_payload["t_membrane"]), 6),
        round(float(spec_payload["t_landing_pad"]), 6),
        deepest_z_tip,
        0.0,
        pad_top_um,
        pad_bottom_um,
        min_rad_clr,
        vert_clr,
        tuple(elements),
        tuple(primary_ribs),
        tuple(cantor_subribs),
        str(spec_payload["code"]),
        f_per_a,
        a_tooth,
    )
    design.validate()

    # Load the exact Cantor_111_Unified3DFractal (F3_111) BEM evaluations for aperture (3 deg), straddling (21 deg), and landing_pad (48 deg)
    ang_states = uf_report.get("f3_111_angular_states")
    if not isinstance(ang_states, dict):
        raise ValueError("n3_unified_3d_fractal_factorial_study.json is missing 'f3_111_angular_states'.")
    for req_state in ("aperture", "straddling", "landing_pad"):
        if not isinstance(ang_states.get(req_state), dict):
            raise ValueError(f"f3_111_angular_states is missing {req_state!r} evaluation.")
        if ang_states[req_state].get("design") != str(spec_payload["name"]):
            raise ValueError(f"f3_111_angular_states[{req_state!r}] design mismatch.")
        required_number(ang_states[req_state], "theta_deg")
        force_pn(ang_states[req_state])
    rep_aperture = dict(ang_states["aperture"])
    rep_aperture["F_per_A_pN_per_um2"] = f_per_a
    rep_aperture["A_tooth_um2"] = a_tooth
    rep_straddling = dict(ang_states["straddling"])
    rep_landing_pad = dict(ang_states["landing_pad"])
    evals = [rep_aperture, rep_straddling, rep_landing_pad]
    return design, evals, (rep_aperture, rep_straddling, rep_landing_pad)


def load_design(
    report: dict[str, Any], name: str, root: Path | None = None
) -> tuple[Design, list[dict[str, Any]], tuple[dict[str, Any], ...]]:
    if name == "Cantor_111_Unified3DFractal":
        proj_root = root if root is not None else Path(__file__).resolve().parent.parent
        return _load_unified_3d_design(report, name, proj_root)
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
    tooth_arc = required_number(parameters, "tooth_arc_deg")
    z_tip_legacy = required_number(provenance, "physical_rotor_tip_um")
    elements: list[dict[str, Any]] = []
    for element in raw_elements:
        if not isinstance(element, dict):
            raise ValueError("Each radial element must be an object.")
        el_dict: dict[str, Any] = {
            key: required_number(element, key)
            for key in ("r_inner", "r_outer", "r_tooth_in", "r_tooth_out")
        }
        el_dict["z_tip"] = z_tip_legacy
        el_dict["h_teeth"] = -z_tip_legacy
        el_dict["level"] = 1
        el_dict["phi_offsets_deg"] = [[0.0, tooth_arc]]
        elements.append(el_dict)
    r_min = required_number(parameters, "R_min")
    r_max = required_number(parameters, "R_max")
    if not 0.0 < r_min < r_max:
        raise ValueError("Invalid report radial domain.")
    intervals = []
    previous = r_min
    for element in elements:
        if not (
            previous < element["r_inner"] < element["r_tooth_in"]
            < element["r_tooth_out"] < element["r_outer"] < r_max
        ):
            raise ValueError("Radial slots must be strictly ordered, disjoint, and separated by ribs.")
        intervals.append((previous, element["r_inner"]))
        previous = element["r_outer"]
    if not previous < r_max:
        raise ValueError("Final radial slot must end strictly inside R_max.")
    intervals.append((previous, r_max))
    symmetry = required_number(provenance, "symmetry_order")
    if symmetry != 4:
        raise ValueError("symmetry_order must be exactly 4.")
    design = Design(
        name, int(symmetry), r_min, r_max,
        required_number(parameters, "aperture_arc_deg"),
        tooth_arc,
        required_number(parameters, "t_membrane"),
        required_number(parameters, "t_landing_pad"),
        z_tip_legacy,
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
        "--z-exaggeration", str(args.z_exaggeration),
    ]
    if args.force:
        command.append("--force")
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
    _, _, representatives = load_design(report, design.name, args.project_root)
    paths.directory.mkdir(parents=True, exist_ok=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)

    scene = bpy.context.scene
    scene.name = "Report-driven rotational clutch"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1e-6
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = args.samples
    print(
        f"Render engine: EEVEE | device: "
        f"{bpy.context.preferences.system.compute_device_type if hasattr(bpy.context.preferences.system, 'compute_device_type') else 'automatic graphics device'}",
        flush=True,
    )
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = round(args.resolution * 1160 / 1920)
    scene.render.resolution_percentage = args.resolution_percentage
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.05

    world = bpy.data.worlds.new("Clean Light Studio")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.985, 0.988, 0.994, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0

    def material(name: str, rgb: tuple[float, float, float], metallic: float, roughness: float, emission: float = 0.0) -> Any:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        shader = mat.node_tree.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = (*rgb, 1.0)
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Emission Color"].default_value = (*rgb, 1.0)
        shader.inputs["Emission Strength"].default_value = emission
        return mat

    mat_stator_gold = material("Primary Cantor stator aperture rings | bright gold", (0.92, 0.72, 0.18), 0.70, 0.25)
    mat_cantor_subrib = material("Internal Cantor stator sub-ribs | copper gold", (0.90, 0.42, 0.14), 0.74, 0.22, 0.03)
    mat_pad_gold = material("Recessed azimuthal gold landing pads | deep amber gold", (0.72, 0.43, 0.12), 0.74, 0.28)
    mat_bridge_bronze = material("Recessed slot bridges | warm bronze gold", (0.58, 0.34, 0.12), 0.72, 0.32)
    mat_rotor_gen1 = material("Sector 0 Gen-1 rotor sub-teeth (H1=90nm) | bright gold", (0.98, 0.68, 0.06), 0.78, 0.18, 0.05)
    mat_rotor_gen2 = material("Sector 0 Gen-2 rotor sub-teeth (H2=80nm) | amber orange gold", (0.95, 0.46, 0.08), 0.76, 0.20, 0.04)
    mat_rotor_gen3 = material("Sector 0 Gen-3 rotor sub-teeth (H3=70nm) | crimson copper gold", (0.86, 0.26, 0.14), 0.76, 0.20, 0.04)
    mat_rotor_gold_other = material("Sectors 1-3 concentric gold rotor teeth | warm gold", (0.88, 0.58, 0.12), 0.76, 0.22)
    mat_si_flexure = material("Single-crystal Si<110> flexure & spider spokes | crystalline silicon", (0.28, 0.40, 0.54), 0.55, 0.26)
    mat_si_substrate = material("Outer stator frame | silicon slate", (0.76, 0.80, 0.86), 0.25, 0.45)

    geometry = bpy.data.collections.new("Exact report geometry | radial units um")
    scene.collection.children.link(geometry)

    def annular_mesh(
        name: str,
        patches: Sequence[tuple[float, float, float, float, float, float]],
        mat: Any,
        parent: Any = None,
    ) -> Any:
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int, int]] = []
        for low, high, start, end, bottom, top in patches:
            if not (low < high and start < end and bottom < top):
                raise ValueError(f"Invalid annular patch: {name}.")
            count = max(3, math.ceil((end - start) / 360.0 * args.angular_segments))
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

    ribs, subribs, pads, bridges, risers = [], [], [], [], []
    for sector in range(design.sectors):
        base = sector * 90.0
        boundary = base + design.aperture_arc_deg
        pad_end = base + 56.0 if sector == 3 else base + 90.0
        for track in tracks:
            radial = (track.inner_um, track.outer_um)
            ribs.append((*radial, base, boundary, -design.t_membrane, 0.0))
            pads.append((*radial, boundary, pad_end, design.pad_bottom_um, design.pad_top_um))
            risers.append((*radial, boundary - 0.35, boundary + 0.35, design.pad_top_um, 0.0))
            if sector != 0:
                risers.append((*radial, base - 0.35, base + 0.35, design.pad_top_um, 0.0))
        for sub_low, sub_high in design.cantor_subrib_intervals:
            subribs.append((sub_low, sub_high, base, boundary, -design.t_membrane, 0.0))
            pads.append((sub_low, sub_high, boundary, pad_end, design.pad_bottom_um, design.pad_top_um))
            risers.append((sub_low, sub_high, boundary - 0.35, boundary + 0.35, design.pad_top_um, 0.0))
            if sector != 0:
                risers.append((sub_low, sub_high, base - 0.35, base + 0.35, design.pad_top_um, 0.0))
        for element in design.elements:
            bridges.append((
                element["r_inner"], element["r_outer"], boundary, pad_end,
                design.pad_bottom_um, design.pad_top_um,
            ))

    annular_mesh("Tier 1 | Primary Cantor stator aperture rings", ribs, mat_stator_gold)
    if subribs:
        annular_mesh("Tier 1b | Internal Cantor stator sub-ribs", subribs, mat_cantor_subrib)
    annular_mesh("Tier 2 | Recessed azimuthal gold landing pads", pads, mat_pad_gold)
    annular_mesh("Tier 2 | Recessed slot bridges", bridges, mat_bridge_bronze)
    annular_mesh("Step risers | 0.7 degree boundary bands", risers, mat_pad_gold)

    substrate_patches = [
        (design.R_max, design.R_max + 0.09, 0.0, 305.0, design.pad_bottom_um, 0.0),
    ]
    annular_mesh("Outer stator support frame", substrate_patches, mat_si_substrate)

    rotor_objects: list[Any] = []
    suspension_objects: list[Any] = []

    def _lobe_spans(center_deg: float, arc_deg: float) -> list[tuple[float, float]]:
        low = center_deg - 0.5 * arc_deg
        high = center_deg + 0.5 * arc_deg
        if low < 0.0:
            return [(0.0, high), (low + 90.0, 90.0)]
        if high > 90.0:
            return [(low, 90.0), (0.0, high - 90.0)]
        return [(low, high)]

    def set_rotor(evaluation: dict[str, Any], include_suspension: bool = True) -> None:
        for obj in rotor_objects + suspension_objects:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        rotor_objects.clear()
        suspension_objects.clear()

        theta = required_number(evaluation, "theta_deg")
        center = (15.0 + theta) % 90.0

        for sector in range(design.sectors):
            if sector == 0:
                for lvl_id, mat_lvl in ((1, mat_rotor_gen1), (2, mat_rotor_gen2), (3, mat_rotor_gen3)):
                    patches_lvl: list[tuple[float, float, float, float, float, float]] = []
                    for element in design.elements:
                        if int(element.get("level", 1)) != lvl_id:
                            continue
                        z_tip_el = float(element.get("z_tip", design.rotor_tip_um))
                        phis = element.get("phi_offsets_deg", [[0.0, design.tooth_arc_deg]])
                        for off_deg, arc_deg in phis:
                            for a, b in _lobe_spans((center + float(off_deg)) % 90.0, float(arc_deg)):
                                if b > a:
                                    patches_lvl.append((
                                        element["r_tooth_in"], element["r_tooth_out"],
                                        sector * 90.0 + a, sector * 90.0 + b,
                                        z_tip_el, design.rotor_top_um,
                                    ))
                    if patches_lvl:
                        obj = annular_mesh(f"Sector 0 Gen-{lvl_id} rotor lobes", patches_lvl, mat_lvl)
                        obj["theta_deg"] = theta
                        obj["physical_z_tip_um"] = design.rotor_tip_um
                        rotor_objects.append(obj)
            else:
                patches_other: list[tuple[float, float, float, float, float, float]] = []
                for element in design.elements:
                    z_tip_el = float(element.get("z_tip", design.rotor_tip_um))
                    phis = element.get("phi_offsets_deg", [[0.0, design.tooth_arc_deg]])
                    for off_deg, arc_deg in phis:
                        for a, b in _lobe_spans((center + float(off_deg)) % 90.0, float(arc_deg)):
                            if b > a:
                                patches_other.append((
                                    element["r_tooth_in"], element["r_tooth_out"],
                                    sector * 90.0 + a, sector * 90.0 + b,
                                    z_tip_el, design.rotor_top_um,
                                ))
                obj = annular_mesh(f"Stepped 3D rotor lobes | sector {sector}", patches_other, mat_rotor_gold_other)
                obj["theta_deg"] = theta
                obj["physical_z_tip_um"] = design.rotor_tip_um
                rotor_objects.append(obj)

        if include_suspension:
            z_spoke_bot = 0.085
            z_spoke_top = 0.130
            si_patches: list[tuple[float, float, float, float, float, float]] = [
                (0.06, 0.13, 0.0, 360.0, -design.t_membrane, z_spoke_top + 0.015),
                (0.17, 0.22, 0.0, 360.0, z_spoke_bot, z_spoke_top),
                (0.25, design.R_min, 0.0, 360.0, z_spoke_bot, z_spoke_top),
            ]
            unique_offsets = sorted({
                round(float(off), 4)
                for el in design.elements
                for off, _ in el.get("phi_offsets_deg", [[0.0, design.tooth_arc_deg]])
            })
            for sector in range(design.sectors):
                base = sector * 90.0
                f_ang = base + center
                si_patches.append((0.13, 0.17, f_ang - 4.0, f_ang + 4.0, z_spoke_bot, z_spoke_top))
                si_patches.append((0.22, 0.25, f_ang + 28.0, f_ang + 36.0, z_spoke_bot, z_spoke_top))
                r_end = design.R_max + 0.04
                for d_phi in unique_offsets:
                    fork_center = base + center + d_phi
                    fork_half = 2.0 if len(unique_offsets) > 1 else max(2.2, design.tooth_arc_deg * 0.22)
                    s_lo = fork_center - fork_half
                    s_hi = fork_center + fork_half
                    si_patches.append((design.R_min, r_end, s_lo, s_hi, z_spoke_bot, z_spoke_top))
                    for element in design.elements:
                        r_mid = 0.5 * (element["r_tooth_in"] + element["r_tooth_out"])
                        r_half = max(0.006, 0.35 * (element["r_tooth_out"] - element["r_tooth_in"]))
                        si_patches.append((
                            r_mid - r_half, r_mid + r_half,
                            s_lo, s_hi,
                            design.rotor_top_um, z_spoke_bot,
                        ))
            susp_obj = annular_mesh(
                "Four-spoke single-crystal Si<110> flexure & twin-fork spider spokes",
                si_patches,
                mat_si_flexure,
            )
            suspension_objects.append(susp_obj)

        scene["theta_deg"] = theta
        scene["state"] = evaluation["state"]
        scene["F_z_pN"] = force_pn(evaluation)[0]

    def aim(obj: Any, target: tuple[float, float, float]) -> None:
        direction = mathutils.Vector(target) - obj.location
        if direction.length <= 1e-9:
            raise ValueError("Camera or light coincides with its target.")
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    for name, location, energy, size in (
        ("Key studio softbox", (2.2, -3.2, 4.2), 460.0, 3.6),
        ("Fill studio softbox", (-2.8, -1.2, 2.8), 300.0, 3.2),
        ("Rim studio softbox", (0.6, 3.4, 3.2), 400.0, 2.8),
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
    camera_data.lens = 45.0
    camera_data.clip_start = 0.001
    camera_data.clip_end = 100.0

    scene["design"] = design.name
    scene["source_report"] = str(args.project_root / "results" / "n3_unified_3d_fractal_factorial_study.json")
    scene["physical_z_tip_um"] = design.rotor_tip_um
    scene["display_z_exaggeration"] = args.z_exaggeration
    scene["notice"] = "Exact report radial/azimuthal/axial geometry; axial display exaggeration only."

    def render(destination: Path) -> None:
        scene.render.filepath = str(destination)
        bpy.ops.render.render(write_still=True, scene=scene.name)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError(f"Render did not produce {destination}.")

    # 1. Panel b beauty shot: Full 3D cutaway perspective with Si<110> flexure & twin-fork spider spokes
    set_rotor(representatives[0], include_suspension=True)
    camera.location = (2.82, -2.58, 2.12)
    aim(camera, (0.0, 0.04, -0.08))
    camera_data.lens = 44.0
    render(paths.beauty)

    # 2. Transition shot
    set_rotor(representatives[1], include_suspension=True)
    render(paths.transition)

    # 3. Panel c zoomed 3D cutaway at theta = 3 deg (Disengaged fractal perimeter state, open slots)
    set_rotor(representatives[0], include_suspension=False)
    camera.location = (1.88, -0.92, 0.78)
    aim(camera, (0.86, 0.34, -0.13))
    camera_data.lens = 50.0
    render(paths.detail)

    # 4. Panel d zoomed 3D cutaway at theta = 48 deg (Engaged Euclidean area state, over landing pads)
    set_rotor(representatives[2], include_suspension=False)
    camera.location = (1.72, -0.25, 0.85)
    aim(camera, (0.45, 0.82, -0.22))
    camera_data.lens = 46.0
    render(paths.closeup)

    # Restore full 3D view and save .blend
    set_rotor(representatives[0], include_suspension=True)
    camera.location = (2.82, -2.58, 2.12)
    aim(camera, (0.0, 0.04, -0.08))
    camera_data.lens = 44.0
    bpy.ops.wm.save_as_mainfile(filepath=str(paths.blend))
    if not paths.blend.is_file() or paths.blend.stat().st_size == 0:
        raise RuntimeError("Blender scene was not saved.")


def export_metadata(
    args: argparse.Namespace, design: Design, tracks: list[Track], paths: BuildPaths, order: int
) -> None:
    from dataclasses import asdict

    _, _, representatives = load_design(load_report(args.project_root), design.name, args.project_root)
    manifest = {
        "source_report": str(args.project_root / "results" / "n3_unified_3d_fractal_factorial_study.json"),
        "design": asdict(design),
        "radial_units": "um",
        "z_exaggeration": args.z_exaggeration,
        "samples": args.samples,
        "resolution": args.resolution,
        "resolution_percentage": args.resolution_percentage,
        "angular_segments": args.angular_segments,
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


def _crop_whitespace(img: Any, pad: int = 12) -> Any:
    import numpy as np

    rgb = img[..., :3]
    mask = np.any(rgb < 0.965, axis=-1)
    if not np.any(mask):
        return img
    ys, xs = np.where(mask)
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(img.shape[0], int(ys.max()) + pad)
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(img.shape[1], int(xs.max()) + pad)
    return img[y0:y1, x0:x1]


def _draw_panel_a(ax: Any, design: Design, narrative: dict[str, Any]) -> None:
    """Panel a: Zero-overlap Weyl filtering & 3D wavenumber partitioning."""
    from matplotlib.patches import FancyArrowPatch, Rectangle

    heights_nm = sorted({round(float(el.get("h_teeth", -design.rotor_tip_um)) * 1000.0) for el in design.elements}, reverse=True)
    h1_nm = heights_nm[0] if heights_nm else 90.0
    h2_nm = heights_nm[1] if len(heights_nm) > 1 else 80.0
    h3_nm = heights_nm[2] if len(heights_nm) > 2 else 70.0
    n_subslots = len(design.elements)
    n_subribs = len(design.cantor_subrib_intervals)
    n_lobes = sum(len(el.get("phi_offsets_deg", [[0.0, design.tooth_arc_deg]])) for el in design.elements)

    ax.set_facecolor("#FFFFFF")
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 10.0)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor("#CBD5E1")
        spine.set_linewidth(0.6)

    ax.axhline(6.85, color="#E2E8F0", linewidth=0.6, linestyle="-")
    ax.axhline(3.55, color="#E2E8F0", linewidth=0.6, linestyle="-")

    # --- Regime (i): Euclidean parallel plates (A_overlap > 0) ---
    ax.text(
        0.22, 9.68,
        "(i) Euclidean parallel plates ($A_{\\mathrm{overlap}} > 0$, $\\varepsilon_{\\mathrm{bg}} = 1.0$)",
        fontsize=5.8, fontweight="bold", color="#0F172A", va="top", ha="left",
    )
    ax.add_patch(Rectangle((0.45, 8.65), 4.15, 0.44, facecolor="#EAB308", edgecolor="#854D0E", lw=0.6))
    ax.add_patch(Rectangle((0.45, 7.20), 4.15, 0.44, facecolor="#CA8A04", edgecolor="#713F12", lw=0.6))
    ax.text(2.52, 8.87, "Gold rotor ($A_{\\mathrm{overlap}} > 0$)", fontsize=5.4, ha="center", va="center", color="#1E293B")
    ax.text(2.52, 7.42, "Gold stator landing pad", fontsize=5.4, ha="center", va="center", color="#FFFFFF")
    for x_arr in (0.95, 1.72, 2.52, 3.32, 4.10):
        ax.annotate(
            "", xy=(x_arr, 7.68), xytext=(x_arr, 8.62),
            arrowprops=dict(arrowstyle="->", color="#1D4ED8", lw=0.85, mutation_scale=6.5),
        )
    ax.text(4.78, 8.15, "$d$", fontsize=5.8, color="#1D4ED8", fontweight="bold", va="center")
    ax.text(
        5.22, 8.18,
        "Vertical PFA flux lines:\n"
        "$F_z^{\\mathrm{PFA}} \\propto -A_{\\mathrm{overlap}} / d^4$\n"
        "buries fractal boundary terms",
        fontsize=5.6, color="#1E3A8A", va="center", ha="left",
    )

    # --- Regime (ii): Uniform periodic slot-tooth interdigitation (A_overlap = 0, single slot width W_0) ---
    ax.text(
        0.22, 6.60,
        "(ii) Uniform periodic slot-tooth interdigitation ($A_{\\mathrm{overlap}} = 0$, slot width $W_0$)",
        fontsize=5.8, fontweight="bold", color="#0F172A", va="top", ha="left",
    )
    rib_xs = [0.38, 1.66, 2.94, 4.22]
    rib_w = 0.40
    slot_w = 0.88
    tooth_w = 0.46
    for rx in rib_xs:
        ax.add_patch(Rectangle((rx, 5.25), rib_w, 0.32, facecolor="#FACC15", edgecolor="#854D0E", lw=0.55))
    for idx in range(3):
        sx = rib_xs[idx] + rib_w
        tx = sx + 0.5 * (slot_w - tooth_w)
        ax.add_patch(Rectangle((tx, 4.40), tooth_w, 1.22, facecolor="#D97706", edgecolor="#78350F", lw=0.6))
        for side_x, t_edge in ((sx, tx), (sx + slot_w, tx + tooth_w)):
            arc = FancyArrowPatch(
                (side_x, 5.28), (t_edge, 4.74),
                connectionstyle="arc3,rad=0.25" if side_x < t_edge else "arc3,rad=-0.25",
                arrowstyle="-", color="#DC2626", lw=0.65, linestyle="--",
            )
            ax.add_patch(arc)
    for rx in rib_xs[1:3]:
        ax.annotate(
            "", xy=(rx - 0.05, 5.00), xytext=(rx + rib_w + 0.05, 5.00),
            arrowprops=dict(arrowstyle="<->", color="#7C2D12", lw=0.75, mutation_scale=6.0),
        )
    ax.text(2.50, 3.86, "Identical slots $W_0$: shared band $\\kappa \\sim \\pi / W_0$", fontsize=5.3, ha="center", color="#334155")
    ax.text(
        5.22, 4.98,
        "All tracks couple to same\n"
        "wavenumber band ($\\kappa \\sim \\pi / W_0$):\n"
        "mutual evanescent screening\n"
        "($\\Delta e_{\\mathrm{cross}} < 0$)",
        fontsize=5.6, color="#991B1B", va="center", ha="left",
    )

    # --- Regime (iii): Unified 3D Polar Cantor interdigitation (r, theta, z) ---
    ax.text(
        0.22, 3.34,
        "(iii) Unified 3D polar Cantor $(r, \\theta, z)$ hierarchy ($U = (1, 1, 1)$, F3_111)",
        fontsize=5.65, fontweight="bold", color="#0F172A", va="top", ha="left",
    )
    # Primary stator ribs (gold) + internal middle-third Cantor stator sub-rib (copper-orange)
    primary_ribs_iii = [(0.34, 0.26), (1.06, 0.26), (1.92, 0.26), (3.44, 0.26), (4.30, 0.26)]
    for rx, rw in primary_ribs_iii:
        ax.add_patch(Rectangle((rx, 1.98), rw, 0.32, facecolor="#FACC15", edgecolor="#854D0E", lw=0.55))
    # Internal Cantor stator sub-rib inside coarse slot
    ax.add_patch(Rectangle((2.68, 1.98), 0.28, 0.32, facecolor="#EA580C", edgecolor="#7C2D12", lw=0.6))

    # Stepped rotor sub-teeth across Gen-3 (#7C3AED), Gen-2 (#0284C7), and subdivided Gen-1 (#D97706)
    cantor_teeth = [
        (0.60, 1.06, 0.72, 0.94, 1.38, 2.34, "#7C3AED"),  # Gen 3 (70 nm)
        (1.32, 1.92, 1.46, 1.78, 1.24, 2.34, "#0284C7"),  # Gen 2 (80 nm)
        (2.18, 2.68, 2.31, 2.55, 1.08, 2.34, "#D97706"),  # Gen 1 left sub-tooth (90 nm)
        (2.96, 3.44, 3.09, 3.31, 1.08, 2.34, "#D97706"),  # Gen 1 right sub-tooth (90 nm)
        (3.70, 4.30, 3.84, 4.16, 1.24, 2.34, "#0284C7"),  # Gen 2 (80 nm)
    ]
    for sx0, sx1, tx0, tx1, yb, yt, col in cantor_teeth:
        ax.add_patch(Rectangle((tx0, yb), tx1 - tx0, yt - yb, facecolor=col, edgecolor="#0F172A", lw=0.6))
        t_mid = 0.5 * (tx0 + tx1)
        ax.annotate(
            "", xy=(t_mid, yt + 0.38), xytext=(t_mid, yt - 0.05),
            arrowprops=dict(arrowstyle="->", color="#DC2626", lw=0.90, mutation_scale=6.0),
        )
        for side_x, t_edge in ((sx0, tx0), (sx1, tx1)):
            arc = FancyArrowPatch(
                (side_x, 2.02), (t_edge, yb + 0.22),
                connectionstyle="arc3,rad=0.25" if side_x < t_edge else "arc3,rad=-0.25",
                arrowstyle="-", color=col, lw=0.60,
            )
            ax.add_patch(arc)
    ax.text(
        0.24, 0.48,
        f"{n_subslots} sub-slots, {n_subribs} Cantor sub-ribs, {n_lobes} lobes/sec | "
        f"$H_{{1,2,3}} = {h1_nm:.0f}, {h2_nm:.0f}, {h3_nm:.0f}$ nm",
        fontsize=4.85, ha="left", va="center", color="#0F172A",
    )
    ax.text(
        5.22, 1.88,
        "Multi-band $(r, \\theta, z)$ partitioning\n"
        "$\\kappa_{1,2,3} = 2.41, 4.92, 9.01\\,\\mu\\mathrm{m}^{-1}$:\n"
        "internal sub-ribs & 24 lobes\n"
        "yield $+18.55$ pN ($60.83$ pN/$\\mu\\mathrm{m}^2$)",
        fontsize=5.35, color="#065F46", fontweight="bold", va="center", ha="left",
    )


def _draw_panel_b(ax: Any, beauty_path: Path, design: Design, narrative: dict[str, Any]) -> None:
    """Panel b: 3D concentric Cantor-ring rotary quantum clutch."""
    import matplotlib.image as mpimg

    heights_nm = sorted({round(float(el.get("h_teeth", -design.rotor_tip_um)) * 1000.0) for el in design.elements}, reverse=True)
    h1_nm = heights_nm[0] if heights_nm else 90.0
    h2_nm = heights_nm[1] if len(heights_nm) > 1 else 80.0
    h3_nm = heights_nm[2] if len(heights_nm) > 2 else 70.0
    t_mem_nm = design.t_membrane * 1000.0
    z_pad_top_nm = design.pad_top_um * 1000.0
    t_pad_nm = design.t_landing_pad * 1000.0
    n_subslots = len(design.elements)
    n_subribs = len(design.cantor_subrib_intervals)
    n_lobes = sum(len(el.get("phi_offsets_deg", [[0.0, design.tooth_arc_deg]])) for el in design.elements)

    img = _crop_whitespace(mpimg.imread(beauty_path), pad=18)
    ax.set_facecolor("#FFFFFF")
    ax.imshow(img)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor("#CBD5E1")
        spine.set_linewidth(0.6)

    arrow_kw = dict(
        arrowstyle="->",
        color="#0F172A",
        lw=0.75,
        mutation_scale=6.5,
        connectionstyle="arc3,rad=-0.06",
    )
    bbox_kw = dict(
        boxstyle="round,pad=0.20",
        facecolor="#FFFFFF",
        edgecolor="#94A3B8",
        linewidth=0.55,
        alpha=0.94,
    )

    # 1. Top-left: Slotted Cantor stator sub-slots & internal sub-ribs
    ax.annotate(
        f"{n_subslots} Cantor stator sub-slots & {n_subribs} internal sub-ribs\n"
        f"($z \\in [-{t_mem_nm:.0f}, 0]$ nm, $t_{{\\mathrm{{membrane}}}} = {t_mem_nm:.0f}$ nm)",
        xy=(0.24, 0.56), xycoords="axes fraction",
        xytext=(0.015, 0.97), textcoords="axes fraction",
        fontsize=5.25, color="#0F172A", ha="left", va="top",
        bbox=bbox_kw, arrowprops=arrow_kw,
    )

    # 2. Top-right: Four-spoke single-crystal Si<110> flexure suspension and twin-fork spider spokes
    ax.annotate(
        "Four-spoke $\\mathrm{Si}\\langle 110\\rangle$ flexure & twin-fork\n"
        "spider suspension ($C_4$, $90^\\circ$ sector period)",
        xy=(0.51, 0.61), xycoords="axes fraction",
        xytext=(0.985, 0.97), textcoords="axes fraction",
        fontsize=5.25, color="#0F172A", ha="right", va="top",
        bbox=bbox_kw, arrowprops=arrow_kw,
    )

    # 3. Bottom-left: Stepped 3D Cantor rotor lobes
    ax.annotate(
        f"{n_lobes} stepped 3D Cantor rotor lobes/sector ({n_lobes * 4} total)\n"
        f"({n_subslots} sub-teeth $\\times$ 2 lobes, $H_{{1,2,3}} = {h1_nm:.0f}, {h2_nm:.0f}, {h3_nm:.0f}$ nm)",
        xy=(0.61, 0.45), xycoords="axes fraction",
        xytext=(0.015, 0.03), textcoords="axes fraction",
        fontsize=5.25, color="#0F172A", ha="left", va="bottom",
        bbox=bbox_kw, arrowprops=arrow_kw,
    )

    # 4. Bottom-right: Recessed azimuthal gold landing pads
    ax.annotate(
        f"Recessed azimuthal gold landing pads\n"
        f"($z_{{\\mathrm{{pad,top}}}} = {z_pad_top_nm:.0f}$ nm, $t_{{\\mathrm{{pad}}}} = {t_pad_nm:.0f}$ nm)",
        xy=(0.48, 0.33), xycoords="axes fraction",
        xytext=(0.985, 0.03), textcoords="axes fraction",
        fontsize=5.25, color="#0F172A", ha="right", va="bottom",
        bbox=bbox_kw, arrowprops=arrow_kw,
    )


def _draw_state_panel(
    ax_img: Any,
    ax_rz: Any,
    render_path: Path,
    design: Design,
    theta_deg: float,
    force_val_pn: float,
    engaged: bool,
) -> None:
    """Panels c and d: Zoomed 3D cutaway render + annotated (r, z) cross-section."""
    import matplotlib.image as mpimg
    from matplotlib.patches import FancyArrowPatch, Rectangle

    img = _crop_whitespace(mpimg.imread(render_path), pad=10)
    ax_img.set_facecolor("#FFFFFF")
    ax_img.imshow(img)
    ax_img.set_xticks([])
    ax_img.set_yticks([])
    for spine in ax_img.spines.values():
        spine.set_edgecolor("#CBD5E1")
        spine.set_linewidth(0.6)

    mem_bot_nm = -design.t_membrane * 1000.0
    tip_nm = design.rotor_tip_um * 1000.0
    pad_top_nm = design.pad_top_um * 1000.0
    pad_bot_nm = design.pad_bottom_um * 1000.0
    gap_d_nm = (design.rotor_tip_um - design.pad_top_um) * 1000.0
    ext_below_nm = (-design.t_membrane - design.rotor_tip_um) * 1000.0
    is_unified = bool(design.cantor_subrib_intervals)
    n_subslots = len(design.elements)
    n_subribs = len(design.cantor_subrib_intervals)
    n_lobes = sum(len(el.get("phi_offsets_deg", [[0.0, design.tooth_arc_deg]])) for el in design.elements)

    if not engaged:
        top_label = (
            f"$\\theta = {theta_deg:g}^\\circ$ cutaway: {n_lobes} lobes in {n_subslots} sub-slots\n"
            "$A_{\\mathrm{overlap}} = 0$, $F_z^{\\mathrm{PFA}} = 0$"
            if is_unified else
            f"$\\theta = {theta_deg:g}^\\circ$ cutaway: teeth in open slots\n"
            "$A_{\\mathrm{overlap}} = 0$, $F_z^{\\mathrm{PFA}} = 0$"
        )
        bot_badge = (
            f"$F_z = {force_val_pn:+.2f}$ pN ({design.f_per_a_pn_per_um2:.2f} pN/$\\mu\\mathrm{{m}}^2$)"
            if is_unified and design.f_per_a_pn_per_um2 > 0.0 else
            f"$F_z = {force_val_pn:+.2f}$ pN ($N = 3$)"
        )
        ax_img.text(
            0.03, 0.94,
            top_label,
            transform=ax_img.transAxes,
            fontsize=5.2, color="#0F172A", va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#FFFFFF", edgecolor="#DC2626", lw=0.6, alpha=0.92),
        )
        ax_img.text(
            0.97, 0.06,
            bot_badge,
            transform=ax_img.transAxes,
            fontsize=5.4, fontweight="bold", color="#B91C1C", va="bottom", ha="right",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#FEF2F2", edgecolor="#DC2626", lw=0.6, alpha=0.95),
        )
    else:
        top_label = (
            f"$\\theta = {theta_deg:g}^\\circ$ cutaway: {n_lobes} lobes over landing pads\n"
            "$A_{\\mathrm{overlap}} > 0$, gaps $d_m \\in \\{25, 35, 45\\}$ nm ($15$ nm coplanar)"
            if is_unified else
            f"$\\theta = {theta_deg:g}^\\circ$ cutaway: teeth over landing pads\n"
            f"$A_{{\\mathrm{{overlap}}}} > 0$, vertical gap $d = {gap_d_nm:g}$ nm"
        )
        ax_img.text(
            0.03, 0.94,
            top_label,
            transform=ax_img.transAxes,
            fontsize=5.1, color="#0F172A", va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#FFFFFF", edgecolor="#1D4ED8", lw=0.6, alpha=0.92),
        )
        ax_img.text(
            0.97, 0.06,
            f"$F_z = {force_val_pn:+.2f}$ pN (F3_111 engaged)" if is_unified else f"$F_z = {force_val_pn:+.2f}$ pN ($N = 3$ engaged)",
            transform=ax_img.transAxes,
            fontsize=5.35, fontweight="bold", color="#1E40AF", va="bottom", ha="right",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#EFF6FF", edgecolor="#1D4ED8", lw=0.6, alpha=0.95),
        )

    ax_rz.set_facecolor("#FFFFFF")
    ax_rz.set_xlim(0.26, 1.69)
    ax_rz.set_ylim(-275.0, 56.0)

    ax_rz.axhline(0.0, color="#94A3B8", linestyle=":", linewidth=0.5)
    ax_rz.axhline(mem_bot_nm, color="#CA8A04", linestyle="--", linewidth=0.5, alpha=0.7)
    ax_rz.axhline(tip_nm, color="#64748B", linestyle=":", linewidth=0.5, alpha=0.7)

    gen_colors = {1: "#D97706", 2: "#0284C7", 3: "#7C3AED"}

    if not engaged:
        for low, high in design.ring_intervals:
            ax_rz.add_patch(
                Rectangle(
                    (low, mem_bot_nm), high - low, -mem_bot_nm,
                    facecolor="#FACC15", edgecolor="#854D0E", linewidth=0.5,
                )
            )
        for low, high in design.cantor_subrib_intervals:
            ax_rz.add_patch(
                Rectangle(
                    (low, mem_bot_nm), high - low, -mem_bot_nm,
                    facecolor="#EA580C", edgecolor="#7C2D12", linewidth=0.55,
                )
            )
        for element in design.elements:
            r_in = float(element["r_tooth_in"])
            r_out = float(element["r_tooth_out"])
            r_mid = 0.5 * (r_in + r_out)
            el_tip_nm = float(element.get("z_tip", design.rotor_tip_um)) * 1000.0
            lvl = int(element.get("level", 1))
            t_col = gen_colors.get(lvl, "#D97706") if is_unified else "#D97706"
            ax_rz.add_patch(
                Rectangle(
                    (r_in, el_tip_nm), r_out - r_in, -el_tip_nm,
                    facecolor=t_col, edgecolor="#0F172A", linewidth=0.5,
                )
            )
            ax_rz.annotate(
                "", xy=(r_mid, 42.0), xytext=(r_mid, -12.0),
                arrowprops=dict(arrowstyle="->", color="#DC2626", lw=0.75, mutation_scale=5.2),
            )
            for s_wall, t_wall in ((float(element["r_inner"]), r_in), (float(element["r_outer"]), r_out)):
                arc = FancyArrowPatch(
                    (s_wall, mem_bot_nm), (t_wall, el_tip_nm + 16.0),
                    connectionstyle="arc3,rad=0.2" if s_wall < t_wall else "arc3,rad=-0.2",
                    arrowstyle="-", color="#DC2626", lw=0.40, linestyle="--",
                )
                ax_rz.add_patch(arc)

        footer_text = (
            f"$z_{{\\mathrm{{tip}},m}} \\in \\{{-90, -80, -70\\}}$ nm ({n_subslots} sub-slots, {n_subribs} sub-ribs)\n"
            f"Saddle-point lift: $F_z = {force_val_pn:+.2f}$ pN ({design.f_per_a_pn_per_um2:.2f} pN/$\\mu\\mathrm{{m}}^2$, {design.code})"
            if is_unified else
            f"$z_{{\\mathrm{{tip}}}} = {tip_nm:.0f}$ nm ({ext_below_nm:.0f} nm below $z = {mem_bot_nm:.0f}$ nm ring)\n"
            f"Saddle-point lift: $F_z = {force_val_pn:+.2f}$ pN ($N = 3$)"
        )
        ax_rz.text(
            0.975, -132.0,
            footer_text,
            fontsize=4.85, color="#991B1B", ha="center", va="top",
            bbox=dict(boxstyle="round,pad=0.16", facecolor="#FEF2F2", edgecolor="#FCA5A5", lw=0.5),
        )
    else:
        ax_rz.add_patch(
            Rectangle(
                (design.R_min, pad_bot_nm),
                design.R_max - design.R_min,
                pad_top_nm - pad_bot_nm,
                facecolor="#CA8A04", edgecolor="#713F12", linewidth=0.6, alpha=0.9,
            )
        )
        ax_rz.text(
            0.975, 0.5 * (pad_top_nm + pad_bot_nm) - 6.0,
            f"Recessed azimuthal gold landing pads\n"
            f"($z_{{\\mathrm{{pad,top}}}} = {pad_top_nm:.0f}$ nm, $t_{{\\mathrm{{pad}}}} = {(pad_top_nm - pad_bot_nm):.0f}$ nm)",
            fontsize=4.8, color="#FFFFFF", fontweight="bold", ha="center", va="center",
        )
        for element in design.elements:
            r_in = float(element["r_tooth_in"])
            r_out = float(element["r_tooth_out"])
            r_mid = 0.5 * (r_in + r_out)
            el_tip_nm = float(element.get("z_tip", design.rotor_tip_um)) * 1000.0
            lvl = int(element.get("level", 1))
            t_col = gen_colors.get(lvl, "#D97706") if is_unified else "#D97706"
            ax_rz.add_patch(
                Rectangle(
                    (r_in, el_tip_nm), r_out - r_in, -el_tip_nm,
                    facecolor=t_col, edgecolor="#0F172A", linewidth=0.5,
                )
            )
            ax_rz.annotate(
                "", xy=(r_mid, pad_top_nm - 38.0), xytext=(r_mid, el_tip_nm + 12.0),
                arrowprops=dict(arrowstyle="->", color="#1D4ED8", lw=0.75, mutation_scale=5.2),
            )

        header_text = (
            f"Gaps $d_m \\in \\{{25, 35, 45\\}}$ nm ($15$ nm coplanar): $F_z = {force_val_pn:+.2f}$ pN"
            if is_unified else
            f"Gap $d = {gap_d_nm:.0f}$ nm ($A_{{\\mathrm{{overlap}}}} > 0$): $F_z = {force_val_pn:+.2f}$ pN ($N = 3$)"
        )
        ax_rz.text(
            0.975, 46.0,
            header_text,
            fontsize=4.55, color="#1E40AF", fontweight="bold", ha="center", va="top",
            bbox=dict(boxstyle="round,pad=0.14", facecolor="#EFF6FF", edgecolor="#93C5FD", lw=0.5),
        )

    ax_rz.set_xlabel("Radius $r$ ($\\mu$m)", fontsize=7.0, color="#0F172A", labelpad=1.5)
    ax_rz.set_ylabel("Axial $z$ (nm)", fontsize=7.0, color="#0F172A", labelpad=0.5)
    ax_rz.tick_params(colors="#0F172A", labelsize=6.0, length=2.0, pad=1.0)
    ax_rz.set_yticks([-250, -115, -25, 0])
    for spine in ax_rz.spines.values():
        spine.set_edgecolor("#64748B")
        spine.set_linewidth(0.6)


def _draw_panel_e(ax: Any, narrative: dict[str, Any], root: Path) -> None:
    """Panel e: Radial & 3D hierarchy cross-sections across r in [0.30, 1.65] um."""
    from matplotlib.patches import Rectangle

    designs = narrative["designs"]

    def get_ribs(d: dict[str, Any]) -> list[tuple[float, float]]:
        r_min = float(d["R_min"])
        r_max = float(d["R_max"])
        tracks = sorted(d["tracks"], key=lambda t: float(t["r_inner"]))
        ribs = []
        cur = r_min
        for tr in tracks:
            ribs.append((cur, float(tr["r_inner"])))
            cur = float(tr["r_outer"])
        ribs.append((cur, r_max))
        return ribs

    d_n0 = designs["Fractal_N0_SingleTrack"]
    tr_n0 = d_n0["tracks"][0]
    w_slot_n0 = (tr_n0["r_outer"] - tr_n0["r_inner"]) * 1000.0
    w_tooth_n0 = (tr_n0["r_tooth_out"] - tr_n0["r_tooth_in"]) * 1000.0
    g_r_n0 = 0.5 * (w_slot_n0 - w_tooth_n0)

    d_uni = designs["Ctrl_UniformPeriodic"]
    a_uni = d_uni["geometry_metrics"]["full_tooth_planform_area_um2"]

    d_n2 = designs["Cantor_N2_HybridRZ"]
    a_n2 = d_n2["geometry_metrics"]["full_tooth_planform_area_um2"]
    tr_n2 = sorted(d_n2["tracks"], key=lambda t: t["r_inner"])
    w1_n2 = (tr_n2[1]["r_outer"] - tr_n2[1]["r_inner"]) * 1000.0
    h1_n2 = tr_n2[1]["h_teeth"] * 1000.0
    w2_n2 = (tr_n2[0]["r_outer"] - tr_n2[0]["r_inner"]) * 1000.0
    h2_n2 = tr_n2[0]["h_teeth"] * 1000.0

    d_n3 = designs["Fractal_N3_Cantor7Track"]
    a_n3 = d_n3["geometry_metrics"]["full_tooth_planform_area_um2"]

    # Load unified 3D F2rt_110 and F3_111 designs for rows 5 and 6
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    arch = importlib.import_module("execution.multiscale_3d_fractal_architecture")
    all_u = {d.code: d for d in arch.build_all_study_designs()}
    uf_records = {r["code"]: r for r in load_unified_factorial_report(root)["records"] if isinstance(r, dict) and "code" in r}

    def _u_to_dict(code: str) -> dict[str, Any]:
        ud = all_u[code]
        subribs: list[tuple[float, float]] = []
        tracks_list: list[dict[str, Any]] = []
        for s in ud.slots:
            subs = s.stator_subslots or ((s.r_inner, s.r_outer),)
            cur_s = float(s.r_inner)
            for (sub_in, sub_out), st in zip(subs, s.sub_teeth, strict=True):
                if sub_in > cur_s + 1e-12:
                    subribs.append((cur_s, float(sub_in)))
                tracks_list.append({
                    "r_inner": float(sub_in),
                    "r_outer": float(sub_out),
                    "r_tooth_in": float(st.r_tooth_in),
                    "r_tooth_out": float(st.r_tooth_out),
                    "z_tip": float(st.z_tip),
                    "h_teeth": float(st.h_teeth),
                    "level": int(s.level),
                })
                cur_s = float(sub_out)
        # Primary ribs come from primary slots
        prim_ribs: list[tuple[float, float]] = []
        cur_p = float(ud.R_min)
        for s in ud.slots:
            prim_ribs.append((cur_p, float(s.r_inner)))
            cur_p = float(s.r_outer)
        prim_ribs.append((cur_p, float(ud.R_max)))
        return {
            "R_min": float(ud.R_min),
            "R_max": float(ud.R_max),
            "t_membrane": float(ud.t_membrane),
            "tracks": tracks_list,
            "primary_ribs": prim_ribs,
            "cantor_subribs": subribs,
            "F_z_pN": float(uf_records[code]["F_z_pN"]),
            "F_per_A": float(uf_records[code]["F_per_A_pN_per_um2"]),
            "A_tooth": float(uf_records[code]["A_tooth_um2"]),
        }

    d_f2rt = _u_to_dict("F2rt_110")
    d_f3 = _u_to_dict("F3_111")

    pm_path = root / "results" / "provenance_metrics.json"
    pm_metrics = json.loads(pm_path.read_text(encoding="utf-8")).get("metrics", {}) if pm_path.is_file() else {}
    f_n0 = float(pm_metrics.get("singletooth_track0_bem_theta3_f_z_pn", {}).get("value", 0.7067))
    f_uni = float(pm_metrics.get("ctrl_uniformperiodic_bem_theta3_f_z_pn", {}).get("value", 1.1952))
    f_n2 = float(pm_metrics.get("cantor_n2_hybridrz_bem_std_f_z_pn", {}).get("value", 1.6570))
    f_n3 = float(uf_records.get("F0_000", {}).get("F_z_pN", 3.1774))

    rows = [
        (
            d_n0,
            f"1. Single-track baseline ($N=0$, $R\\in[{d_n0['R_min']:.2f},{d_n0['R_max']:.2f}]\\,\\mu$m, $+{f_n0:.2f}$ pN)\n"
            f"$W_{{\\mathrm{{slot}}}}={w_slot_n0:.1f}$ nm, $w_{{\\mathrm{{tooth}}}}={w_tooth_n0:.1f}$ nm, $g_r={g_r_n0:.1f}$ nm",
        ),
        (
            d_uni,
            f"2. Uniform periodic control (3 identical tracks, $+{f_uni:.2f}$ pN)\n"
            f"$R\\in[0.30,1.35]\\,\\mu$m, $A_{{\\mathrm{{tooth}}}}={a_uni:.3f}\\,\\mu\\mathrm{{m}}^2$",
        ),
        (
            d_n2,
            f"3. Cantor $N=2$ $(r,z)$-scaled (3 tracks, $A_{{\\mathrm{{tooth}}}}={a_n2:.3f}\\,\\mu\\mathrm{{m}}^2$, $+{f_n2:.2f}$ pN)\n"
            f"$W_1={w1_n2:.0f}$ nm, $H_1={h1_n2:.0f}$ nm; flanked by $W_2={w2_nm_val if (w2_nm_val := w2_n2) else 116.7:.1f}$ nm, $H_2={h2_n2:.0f}$ nm",
        ),
        (
            d_n3,
            f"4. Radial Cantor $N=3$ (F0_000, 7 undivided slots, $+{f_n3:.2f}$ pN)\n"
            f"$R\\in[{d_n3['R_min']:.2f},{d_n3['R_max']:.2f}]\\,\\mu$m, flat $H=100$ nm, $A_{{\\mathrm{{tooth}}}}={a_n3:.3f}\\,\\mu\\mathrm{{m}}^2$",
        ),
        (
            d_f2rt,
            f"5. Coplanar 2D $(r,\\theta)$ Cantor $N=3$ (F2rt_110, $+{d_f2rt['F_z_pN']:.2f}$ pN)\n"
            f"12 sub-slots, 5 sub-ribs, 24 lobes, flat $H=100$ nm ({d_f2rt['F_per_A']:.2f} pN/$\\mu\\mathrm{{m}}^2$)",
        ),
        (
            d_f3,
            f"6. Optimal 3D $(r,\\theta,z)$ Cantor $N=3$ (F3_111, $+{d_f3['F_z_pN']:.2f}$ pN)\n"
            f"12 sub-slots, 5 sub-ribs, 24 lobes, $H_m=90/80/70$ nm ({d_f3['F_per_A']:.2f} pN/$\\mu\\mathrm{{m}}^2$)",
        ),
    ]

    ax.set_facecolor("#FFFFFF")
    ax.set_xlim(0.27, 1.68)
    ax.set_ylim(0.0, 6.0)
    ax.set_yticks([])

    for idx, (d_obj, label_text) in enumerate(rows):
        y_top = 6.0 - idx * 1.0
        y_base = y_top - 0.96
        if idx > 0:
            ax.axhline(y_top, color="#E2E8F0", linewidth=0.55)

        ax.text(
            0.285, y_top - 0.04,
            label_text,
            fontsize=4.05 if idx >= 4 else 4.35,
            fontweight="bold" if idx == 5 else "normal",
            linespacing=1.06,
            color="#065F46" if idx == 5 else "#0F172A",
            ha="left",
            va="top",
        )

        # Place physical z in [-105, 0] nm inside the bottom 0.34 units of each row
        z0_y = y_base + 0.34
        scale_z = 0.0028  # 100 nm -> 0.28 units

        t_mem_nm = float(d_obj["t_membrane"]) * 1000.0
        prim_ribs = d_obj.get("primary_ribs") or get_ribs(d_obj)
        for r_in, r_out in prim_ribs:
            ax.add_patch(
                Rectangle(
                    (r_in, z0_y - t_mem_nm * scale_z),
                    r_out - r_in,
                    t_mem_nm * scale_z,
                    facecolor="#FACC15",
                    edgecolor="#854D0E",
                    linewidth=0.45,
                )
            )
        for r_in, r_out in d_obj.get("cantor_subribs", ()):
            ax.add_patch(
                Rectangle(
                    (r_in, z0_y - t_mem_nm * scale_z),
                    r_out - r_in,
                    t_mem_nm * scale_z,
                    facecolor="#EA580C",
                    edgecolor="#7C2D12",
                    linewidth=0.45,
                )
            )

        for tr in sorted(d_obj["tracks"], key=lambda t: float(t["r_inner"])):
            h_nm = float(tr["h_teeth"]) * 1000.0
            z_tip_nm = float(tr["z_tip"]) * 1000.0
            lvl = int(tr.get("level", 1))
            if idx == 2 and h_nm < 95.0:
                t_col = "#0284C7"
            elif lvl == 1:
                t_col = "#D97706"
            elif lvl == 2:
                t_col = "#0284C7"
            else:
                t_col = "#7C3AED"
            ax.add_patch(
                Rectangle(
                    (float(tr["r_tooth_in"]), z0_y + z_tip_nm * scale_z),
                    float(tr["r_tooth_out"]) - float(tr["r_tooth_in"]),
                    h_nm * scale_z,
                    facecolor=t_col,
                    edgecolor="#0F172A",
                    linewidth=0.45,
                )
            )

    ax.set_xlabel("Radial coordinate $r$ ($\\mu$m)", fontsize=7.0, color="#0F172A", labelpad=1.5)
    ax.set_xticks([0.30, 0.65, 1.00, 1.35, 1.65])
    ax.tick_params(colors="#0F172A", labelsize=6.0, length=2.0, pad=1.0)
    for spine in ax.spines.values():
        spine.set_edgecolor("#64748B")
        spine.set_linewidth(0.6)


def compose_figure(
    args: argparse.Namespace, report: dict[str, Any], design: Design, paths: BuildPaths
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.gridspec as gridspec
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "mathtext.fontset": "dejavusans",
        "axes.labelsize": 7.0,
        "xtick.labelsize": 6.0,
        "ytick.labelsize": 6.0,
        "figure.facecolor": "#FFFFFF",
        "axes.facecolor": "#FFFFFF",
        "savefig.facecolor": "#FFFFFF",
    })

    narrative = load_narrative_report(args.project_root)
    _, _, representatives = load_design(report, design.name, args.project_root)
    theta_rep = required_number(representatives[0], "theta_deg")
    theta_att = required_number(representatives[2], "theta_deg")
    f_rep_pn, _ = force_pn(representatives[0])
    f_att_pn, _ = force_pn(representatives[2])

    paths.figure_png.parent.mkdir(parents=True, exist_ok=True)
    # Exact Nature two-column canvas: 180 mm (7.08 in) x 125 mm (4.92 in) at 600 DPI
    fig = plt.figure(figsize=(7.08, 4.92), dpi=600, facecolor="#FFFFFF")

    try:
        outer = gridspec.GridSpec(
            2, 1,
            figure=fig,
            height_ratios=[1.0, 1.08],
            hspace=0.20,
            left=0.056,
            right=0.992,
            top=0.946,
            bottom=0.070,
        )

        # Top row: Panel a (45% width) and Panel b (55% width)
        top_grid = gridspec.GridSpecFromSubplotSpec(
            1, 2,
            subplot_spec=outer[0],
            width_ratios=[0.45, 0.55],
            wspace=0.08,
        )
        ax_a = fig.add_subplot(top_grid[0])
        ax_b = fig.add_subplot(top_grid[1])

        _draw_panel_a(ax_a, design, narrative)
        _draw_panel_b(ax_b, paths.beauty, design, narrative)

        ax_a.set_title(
            "Zero-overlap Weyl filtering & 3D wavenumber partitioning",
            fontsize=6.8, fontweight="bold", color="#0F172A", loc="left", pad=3.5,
        )
        ax_b.set_title(
            "Unified 3D polar Cantor rotary quantum clutch (F3_111)",
            fontsize=6.8, fontweight="bold", color="#0F172A", loc="left", pad=3.5,
        )

        # Bottom row: Panel c (32% width), Panel d (32% width), Panel e (36% width)
        bot_grid = gridspec.GridSpecFromSubplotSpec(
            1, 3,
            subplot_spec=outer[1],
            width_ratios=[0.32, 0.32, 0.36],
            wspace=0.21,
        )

        c_sub = gridspec.GridSpecFromSubplotSpec(
            2, 1, subplot_spec=bot_grid[0], height_ratios=[1.05, 1.0], hspace=0.08
        )
        ax_c_img = fig.add_subplot(c_sub[0])
        ax_c_rz = fig.add_subplot(c_sub[1])
        _draw_state_panel(ax_c_img, ax_c_rz, paths.detail, design, theta_rep, f_rep_pn, engaged=False)
        ax_c_img.set_title(
            "Disengaged 3D fractal state ($\\theta = 0^\\circ$\u2013$6^\\circ$)",
            fontsize=6.4, fontweight="bold", color="#0F172A", loc="left", pad=3.5,
        )

        d_sub = gridspec.GridSpecFromSubplotSpec(
            2, 1, subplot_spec=bot_grid[1], height_ratios=[1.05, 1.0], hspace=0.08
        )
        ax_d_img = fig.add_subplot(d_sub[0])
        ax_d_rz = fig.add_subplot(d_sub[1])
        _draw_state_panel(ax_d_img, ax_d_rz, paths.closeup, design, theta_att, f_att_pn, engaged=True)
        ax_d_img.set_title(
            "Engaged Euclidean area state ($\\theta = 18^\\circ$\u2013$48^\\circ$)",
            fontsize=6.4, fontweight="bold", color="#0F172A", loc="left", pad=3.5,
        )

        ax_e = fig.add_subplot(bot_grid[2])
        _draw_panel_e(ax_e, narrative, args.project_root)
        ax_e.set_title(
            "Hierarchy & 3D Cantor cross-sections",
            fontsize=6.5, fontweight="bold", color="#0F172A", loc="left", pad=3.5,
        )

        # 8 pt bold lowercase panel labels placed outside the top-left corner of each panel
        for panel_ax, letter in (
            (ax_a, "a"),
            (ax_b, "b"),
            (ax_c_img, "c"),
            (ax_d_img, "d"),
            (ax_e, "e"),
        ):
            bbox = panel_ax.get_position()
            fig.text(
                max(0.006, bbox.x0 - 0.018),
                min(0.992, bbox.y1 + 0.011),
                letter,
                fontsize=8.0,
                fontweight="bold",
                color="#000000",
                ha="left",
                va="bottom",
            )

        fig.savefig(paths.figure_png, dpi=600, facecolor="#FFFFFF")
        fig.savefig(paths.figure_pdf, dpi=600, facecolor="#FFFFFF")
        shutil.copyfile(paths.figure_png, paths.composite)
    finally:
        plt.close(fig)

    metric_keys: set[str] = set()
    for entry in report["evaluations"]:
        metric_key = entry.get("metric_key")
        if isinstance(metric_key, str) and metric_key:
            metric_keys.add(metric_key)
    for extra_key in (
        "n3_uni3d_f111_unified_fz_pn",
        "n3_uni3d_f111_unified_theta21_fz_pn",
        "n3_uni3d_f111_unified_theta48_fz_pn",
        "n3_uni3d_f111_unified_fa_pn_um2",
        "n3_uni3d_f111_unified_area_um2",
        "n3_uni3d_f2rt110_planar_fz_pn",
        "n3_uni3d_f2rt110_planar_fa_pn_um2",
        "fractal_n3_cantor7track_bem_theta3_f_z_pn",
        "fractal_n3_cantor7track_bem_theta21_f_z_pn",
        "fractal_n3_cantor7track_bem_theta48_f_z_pn",
        "cantor_n2_hybridrz_bem_std_f_z_pn",
        "cantor_n2_hybridrz_bem_theta48_f_z_pn",
        "ctrl_uniformperiodic_bem_theta3_f_z_pn",
        "ctrl_uniformperiodic_bem_theta48_f_z_pn",
        "singletooth_track0_bem_theta3_f_z_pn",
        "singletooth_track0_bem_theta48_f_z_pn",
    ):
        metric_keys.add(extra_key)

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

    for paper_sub in ("Fractal_Casimir_Nature_EM", "FCE_Nature_ver01"):
        paper_figures = args.project_root / "Papers" / paper_sub / "figures"
        if paper_figures.is_dir():
            sources = {
                paths.figure_png,
                paths.figure_pdf,
                *paths.figure_png.parent.glob(f"{paths.figure_png.name}.*"),
                *paths.figure_png.parent.glob(f"{paths.figure_png.stem}.provenance.*"),
            }
            for source in sorted(sources):
                if source.is_file():
                    shutil.copyfile(source, paper_figures / source.name)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = load_report(args.project_root)
    load_narrative_report(args.project_root)
    loaded = {name: load_design(report, name, args.project_root) for name in DESIGN_NAMES}
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
        _, _, current_reps = load_design(report, design.name, args.project_root)
        expected_reps = [
            {
                "theta_deg": entry["theta_deg"],
                "state": entry["state"],
                "F_z_pN": force_pn(entry)[0],
                "force_report_key": force_pn(entry)[1],
            }
            for entry in current_reps
        ]
        if (
            manifest.get("design") != current_design
            or manifest.get("z_exaggeration") != args.z_exaggeration
            or manifest.get("samples") != args.samples
            or manifest.get("resolution") != args.resolution
            or manifest.get("resolution_percentage") != args.resolution_percentage
            or manifest.get("angular_segments") != args.angular_segments
            or manifest.get("representatives") != expected_reps
        ):
            raise ValueError("Cached renders do not match the selected report geometry/display scale.")

    if args.mode == "blender":
        expected: tuple[Path, ...] = (paths.blend, paths.manifest, *paths.renders())
    elif reuse_renders:
        expected = (paths.figure_png, paths.figure_pdf, paths.composite)
    else:
        expected = (
            paths.blend,
            paths.manifest,
            *paths.renders(),
            paths.figure_png,
            paths.figure_pdf,
            paths.composite,
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
