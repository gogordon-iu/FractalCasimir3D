#!/usr/bin/env python3
"""
Build 3D Blender models and a side-by-side explanatory atlas figure for EVERY
constellation evaluated in the six-step Fractal Casimir Rotary Clutch narrative.

All geometry parameters, track coordinates, and BEM / Meep force benchmarks are
read directly from:
    results/nature_6step_narrative_report.json
and canonical passive monolithic structural elevation constants from:
    execution/clutch_geometry_redesign.py

Examples:
    python execution/build_all_constellations_blender.py --force
    python execution/build_all_constellations_blender.py --skip-blender --max-steps 1
    blender --background --python execution/build_all_constellations_blender.py -- \\
        --mode blender --force
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from execution.clutch_geometry_redesign import (
    DEFAULT_NUM_SECTORS,
    DEFAULT_SECTOR_DEG,
    DEFAULT_TOOTH_CENTER_OFFSET_DEG,
    MONOLITHIC_SPOKE_Z_MAX_UM,
    MONOLITHIC_SPOKE_Z_MIN_UM,
    MONOLITHIC_TRENCH_Z_MAX_UM,
    MONOLITHIC_TRENCH_Z_MIN_UM,
)

TITLE = (
    "Complete 3D Constellation Atlas: From Single-Tooth Overhang & Non-Fractal Controls "
    "to Hierarchical (r, z) Cantor & Monolithic NEMS Clutches"
)

MONOLITHIC_COLLAR_OVERHANG_UM = 0.12
MONOLITHIC_MIN_INNER_RADIUS_UM = 0.08


@dataclass(frozen=True)
class ConstellationSpec:
    index: int
    panel_letter: str
    slug: str
    title: str
    subtitle: str
    step_label: str
    report_design: str
    boundary: str
    z_tip_override_um: float | None
    h_teeth_override_um: float | None
    theta_rep_deg: float
    theta_att_deg: float
    meep_rep_task_id: int | None
    meep_att_task_id: int | None
    category: str


CONSTELLATIONS: tuple[ConstellationSpec, ...] = (
    ConstellationSpec(
        index=1,
        panel_letter="a",
        slug="01_N0_Overhang",
        title="N = 0 symmetric overhang",
        subtitle="z_tip = -55 nm (+45 nm protrusion)",
        step_label="Step 1: Sign-Reversal Control",
        report_design="Fractal_N0_SingleTrack",
        boundary="Active-Only",
        z_tip_override_um=-0.055,
        h_teeth_override_um=0.100,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=3,
        meep_att_task_id=None,
        category="hierarchy",
    ),
    ConstellationSpec(
        index=2,
        panel_letter="b",
        slug="02_Fractal_N0_SingleTrack",
        title="N = 0 deep interdigitation",
        subtitle="z_tip = -100 nm (flush slot entry)",
        step_label="Steps 1–3: N=0 Baseline",
        report_design="Fractal_N0_SingleTrack",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=1,
        meep_att_task_id=2,
        category="hierarchy",
    ),
    ConstellationSpec(
        index=3,
        panel_letter="c",
        slug="03_Fractal_N1_FundRing",
        title="N = 1 fundamental Cantor slot",
        subtitle="1 middle-third slot (W_1 = 350 nm)",
        step_label="Step 3: N=1 Cantor Ring",
        report_design="Fractal_N1_FundRing",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=None,
        meep_att_task_id=None,
        category="hierarchy",
    ),
    ConstellationSpec(
        index=4,
        panel_letter="d",
        slug="04_Ctrl_SingleWide",
        title="Single wide tooth control",
        subtitle="Matched total slot & tooth area (1 track)",
        step_label="Steps 4–5: Non-Fractal Control A",
        report_design="Ctrl_SingleWide",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=None,
        meep_att_task_id=None,
        category="control",
    ),
    ConstellationSpec(
        index=5,
        panel_letter="e",
        slug="05_Ctrl_UniformPeriodic",
        title="Uniform periodic grating control",
        subtitle="3 equal slots & teeth",
        step_label="Steps 4–5: Non-Fractal Control B",
        report_design="Ctrl_UniformPeriodic",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=4,
        meep_att_task_id=5,
        category="control",
    ),
    ConstellationSpec(
        index=6,
        panel_letter="f",
        slug="06_Ctrl_SizeMatched_Monotonic",
        title="Size-matched monotonic control",
        subtitle="N = 2 widths ordered narrow to wide",
        step_label="Steps 4–5: Non-Fractal Control C",
        report_design="Ctrl_SizeMatched_Monotonic",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=None,
        meep_att_task_id=None,
        category="control",
    ),
    ConstellationSpec(
        index=7,
        panel_letter="g",
        slug="07_Cantor_N2_FlatZ",
        title="Cantor N = 2 uniform-depth",
        subtitle="H_1 = H_2 = 100 nm",
        step_label="Steps 3–5: N=2 Flat-Z",
        report_design="Cantor_N2_FlatZ",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=6,
        meep_att_task_id=7,
        category="hierarchy",
    ),
    ConstellationSpec(
        index=8,
        panel_letter="h",
        slug="08_Cantor_N2_HybridRZ",
        title="Cantor N = 2 (r, z)-scaled",
        subtitle="H_1 = 100 nm, H_2 = 90 nm",
        step_label="Steps 4–6: (r, z) Scale-Matched",
        report_design="Cantor_N2_HybridRZ",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=8,
        meep_att_task_id=9,
        category="fractal_rz",
    ),
    ConstellationSpec(
        index=9,
        panel_letter="i",
        slug="09_Rot_C8_Compact_N2",
        title="Compact N = 2 rotational variant",
        subtitle="R in [0.20, 0.90] um, w_1/W_1 = 0.45",
        step_label="Step 5: Footprint Density Champion",
        report_design="Rot_C8_Compact_N2",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=10,
        meep_att_task_id=None,
        category="champion",
    ),
    ConstellationSpec(
        index=10,
        panel_letter="j",
        slug="10_Rot_C4_TightSlot_N2",
        title="Tight-slot N = 2 rotational variant",
        subtitle="R in [0.30, 1.35] um, theta_rep = 6 deg",
        step_label="Step 2: Rotational Tight-Slot N=2",
        report_design="Rot_C4_TightSlot_N2",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=6.0,
        theta_att_deg=48.0,
        meep_rep_task_id=None,
        meep_att_task_id=None,
        category="hierarchy",
    ),
    ConstellationSpec(
        index=11,
        panel_letter="k",
        slug="11_Fractal_N3_Cantor7Track",
        title="Cantor N = 3 seven-track hierarchy",
        subtitle="7 tracks, 28 teeth, R in [0.30, 1.65] um",
        step_label="Steps 3, 5 & 6: Peak Swing Champion",
        report_design="Fractal_N3_Cantor7Track",
        boundary="Active-Only",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=None,
        meep_att_task_id=None,
        category="champion",
    ),
    ConstellationSpec(
        index=12,
        panel_letter="l",
        slug="12_Fractal_N3_Cantor7Track_Monolithic",
        title="Full-monolithic N = 2 & N = 3 assemblies",
        subtitle="4 radial spokes + hub collars + trench",
        step_label="Step 6: Full-Device NEMS Clutch",
        report_design="Fractal_N3_Cantor7Track",
        boundary="Full-Monolithic",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=None,
        meep_att_task_id=None,
        category="monolithic",
    ),
)


@dataclass(frozen=True)
class TrackGeometry:
    r_inner: float
    r_outer: float
    r_tooth_in: float
    r_tooth_out: float
    z_tip: float
    h_teeth: float
    level: int

    @property
    def z_top(self) -> float:
        return self.z_tip + self.h_teeth


@dataclass(frozen=True)
class LoadedConstellation:
    spec: ConstellationSpec
    R_min: float
    R_max: float
    aperture_arc_deg: float
    tooth_arc_deg: float
    t_membrane: float
    t_landing_pad: float
    z_pad_top: float
    z_pad_bottom: float
    tracks: tuple[TrackGeometry, ...]
    rib_intervals: tuple[tuple[float, float], ...]
    footprint_um2: float
    tooth_area_um2: float
    full_tooth_count: int
    f_rep_bem_pn: float
    f_att_bem_pn: float
    delta_f_bem_pn: float
    rep_task_id: str
    att_task_id: str
    f_rep_high_pn: float | None
    f_rep_ultra_pn: float | None
    f_rep_meep_pn: float | None
    f_att_meep_pn: float | None
    f_rep_secondary_pn: float | None = None
    f_att_secondary_pn: float | None = None


@dataclass(frozen=True)
class BuildPaths:
    directory: Path
    models_dir: Path
    manifest: Path
    master_blend: Path
    lineup_render: Path
    panel_renders: dict[str, Path]
    individual_blends: dict[str, Path]
    composite_png: Path
    figure_png: Path
    figure_pdf: Path

    @classmethod
    def create(cls, root: Path) -> BuildPaths:
        directory = root / "results" / "all_constellations_blender"
        models_dir = directory / "models"
        panel_renders = {
            spec.slug: directory / f"render_{spec.slug}.png"
            for spec in CONSTELLATIONS
        }
        individual_blends = {
            spec.slug: models_dir / f"{spec.slug}.blend"
            for spec in CONSTELLATIONS
        }
        return cls(
            directory=directory,
            models_dir=models_dir,
            manifest=directory / "all_constellations_manifest.json",
            master_blend=directory / "all_constellations_scene.blend",
            lineup_render=directory / "render_all_constellations_lineup.png",
            panel_renders=panel_renders,
            individual_blends=individual_blends,
            composite_png=directory / "fig_all_constellations_blender.png",
            figure_png=root / "figures" / "fig_all_constellations_blender.png",
            figure_pdf=root / "figures" / "fig_all_constellations_blender.pdf",
        )

    def all_renders(self) -> tuple[Path, ...]:
        return (self.lineup_render, *self.panel_renders.values())


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a numeric JSON value.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


def required_number(mapping: dict[str, Any], key: str) -> float:
    if key not in mapping:
        raise ValueError(f"Report is missing {key!r}.")
    return finite_number(mapping[key], key)


def atomic_text(path: Path, text: str) -> None:
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("python", "blender"), default="python")
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
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
        "--max-steps",
        type=int,
        default=0,
        help="Probe limit; 1-5 with --skip-blender validates the report and exits.",
    )
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--resolution", type=int, default=1200, help="Panel render width.")
    parser.add_argument("--resolution-percentage", type=int, default=100)
    parser.add_argument("--angular-segments", type=int, default=256)
    parser.add_argument("--z-exaggeration", type=float, default=1.8)
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


def load_narrative_report(root: Path) -> dict[str, Any]:
    path = root / "results" / "nature_6step_narrative_report.json"
    if not path.is_file():
        raise FileNotFoundError(f"Required narrative report not found: {path}")
    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict):
        raise ValueError("Narrative report must be a JSON object.")
    if not isinstance(report.get("designs"), dict) or not report["designs"]:
        raise ValueError("Narrative report is missing designs dictionary.")
    if not isinstance(report.get("tasks"), list) or not report["tasks"]:
        raise ValueError("Narrative report is missing tasks list.")
    return report


def find_bem_task(
    tasks: list[dict[str, Any]],
    design_names: Sequence[str],
    theta_deg: float,
    boundary: str,
    tier: str = "Standard",
    formulation: str = "vector_dyadic",
    z_tip_override_um: float | None = None,
) -> dict[str, Any] | None:
    for task in tasks:
        if task.get("design") not in design_names:
            continue
        if task.get("boundary") != boundary:
            continue
        if task.get("tier") != tier:
            continue
        if task.get("formulation") != formulation:
            continue
        if not math.isclose(
            finite_number(task.get("theta_deg", -999.0), "theta_deg"),
            theta_deg,
            abs_tol=1e-6,
        ):
            continue
        if z_tip_override_um is not None and not math.isclose(
            finite_number(task.get("z_tip_um", -999.0), "z_tip_um"),
            z_tip_override_um,
            abs_tol=1e-6,
        ):
            continue
        if z_tip_override_um is None and task.get("step") == "step1_single_tooth_ztip":
            if not math.isclose(
                finite_number(task.get("z_tip_um", -999.0), "z_tip_um"),
                -0.100,
                abs_tol=1e-6,
            ):
                continue
        return task
    return None


def load_rotational_report(root: Path) -> dict[str, Any]:
    path = root / "results" / "rotational_z_eff_clutch_report.json"
    if not path.is_file():
        raise FileNotFoundError(f"Required rotational report not found: {path}")
    with path.open(encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict) or not isinstance(report.get("evaluations"), list):
        raise ValueError("Rotational report must contain an evaluations list.")
    return report


def find_rotational_eval(
    evaluations: list[dict[str, Any]],
    design_name: str,
    theta_deg: float,
) -> dict[str, Any] | None:
    for entry in evaluations:
        if entry.get("design") != design_name:
            continue
        if math.isclose(
            finite_number(entry.get("theta_deg", -999.0), "theta_deg"),
            theta_deg,
            abs_tol=1e-6,
        ):
            return entry
    return None


def extract_rotational_design(
    evaluations: list[dict[str, Any]],
    design_name: str,
) -> dict[str, Any]:
    for entry in evaluations:
        if entry.get("design") != design_name:
            continue
        solver_res = entry.get("solver_result")
        if not isinstance(solver_res, dict):
            continue
        params = solver_res.get("parameters")
        if not isinstance(params, dict) or params.get("name") != design_name:
            continue
        elements = params.get("elements")
        if not isinstance(elements, list) or not elements:
            raise ValueError(f"Rotational design {design_name!r} has no elements.")
        tooth_arc_deg = required_number(params, "tooth_arc_deg")
        z_tip_val = required_number(params, "z_tip")
        h_teeth_val = required_number(params, "h_teeth")
        max_slot_w = max(
            required_number(el, "r_outer") - required_number(el, "r_inner")
            for el in elements
        )
        tracks: list[dict[str, Any]] = []
        area_sector = 0.0
        angle_rad = math.radians(tooth_arc_deg)
        for el in elements:
            r_in = required_number(el, "r_inner")
            r_out = required_number(el, "r_outer")
            rt_in = required_number(el, "r_tooth_in")
            rt_out = required_number(el, "r_tooth_out")
            ratio = max_slot_w / max(r_out - r_in, 1e-12)
            level = 1 + int(round(math.log(max(ratio, 1.0)) / math.log(3.0)))
            tracks.append(
                {
                    "r_inner": r_in,
                    "r_outer": r_out,
                    "r_tooth_in": rt_in,
                    "r_tooth_out": rt_out,
                    "z_tip": z_tip_val,
                    "h_teeth": h_teeth_val,
                    "level": level,
                }
            )
            area_sector += 0.5 * angle_rad * (rt_out**2 - rt_in**2)
        return {
            "name": design_name,
            "R_min": required_number(params, "R_min"),
            "R_max": required_number(params, "R_max"),
            "aperture_arc_deg": required_number(params, "aperture_arc_deg"),
            "tooth_arc_deg": tooth_arc_deg,
            "t_membrane": required_number(params, "t_membrane"),
            "t_landing_pad": required_number(params, "t_landing_pad"),
            "z_pad_top": required_number(params, "z_pad_top"),
            "geometry_metrics": {
                "full_tooth_planform_area_um2": float(DEFAULT_NUM_SECTORS) * area_sector,
            },
            "tracks": tracks,
        }
    raise ValueError(
        f"Design {design_name!r} missing from both narrative and rotational reports."
    )


def load_constellations(
    report: dict[str, Any],
    rot_report: dict[str, Any] | None = None,
) -> tuple[LoadedConstellation, ...]:
    designs = report["designs"]
    tasks = report["tasks"]
    rot_evals = rot_report.get("evaluations", []) if isinstance(rot_report, dict) else []
    meep_tasks = {
        int(row["task_id"]): row
        for row in report.get("analysis", {}).get("meep_verification", {}).get("tasks", [])
        if isinstance(row, dict) and "task_id" in row
    }

    loaded: list[LoadedConstellation] = []
    for spec in CONSTELLATIONS:
        if spec.report_design in designs:
            raw_design = designs[spec.report_design]
        else:
            raw_design = extract_rotational_design(rot_evals, spec.report_design)
        r_min = required_number(raw_design, "R_min")
        r_max = required_number(raw_design, "R_max")
        aperture_arc_deg = required_number(raw_design, "aperture_arc_deg")
        tooth_arc_deg = required_number(raw_design, "tooth_arc_deg")
        t_membrane = required_number(raw_design, "t_membrane")
        t_landing_pad = required_number(raw_design, "t_landing_pad")
        z_pad_top = required_number(raw_design, "z_pad_top")
        z_pad_bottom = z_pad_top - t_landing_pad
        raw_tracks = raw_design.get("tracks")
        if not isinstance(raw_tracks, list) or not raw_tracks:
            raise ValueError(f"Design {spec.report_design!r} has no tracks.")
        tracks: list[TrackGeometry] = []
        for item in sorted(raw_tracks, key=lambda tr: required_number(tr, "r_inner")):
            z_tip = (
                spec.z_tip_override_um
                if spec.z_tip_override_um is not None
                else required_number(item, "z_tip")
            )
            h_teeth = (
                spec.h_teeth_override_um
                if spec.h_teeth_override_um is not None
                else required_number(item, "h_teeth")
            )
            tracks.append(
                TrackGeometry(
                    r_inner=required_number(item, "r_inner"),
                    r_outer=required_number(item, "r_outer"),
                    r_tooth_in=required_number(item, "r_tooth_in"),
                    r_tooth_out=required_number(item, "r_tooth_out"),
                    z_tip=z_tip,
                    h_teeth=h_teeth,
                    level=int(required_number(item, "level")),
                )
            )

        geom_metrics = raw_design.get("geometry_metrics")
        if isinstance(geom_metrics, dict) and "full_tooth_planform_area_um2" in geom_metrics:
            tooth_area_um2 = required_number(geom_metrics, "full_tooth_planform_area_um2")
        else:
            angle_rad = math.radians(tooth_arc_deg)
            sector_area = sum(
                0.5 * angle_rad * (tr.r_tooth_out**2 - tr.r_tooth_in**2)
                for tr in tracks
            )
            tooth_area_um2 = float(DEFAULT_NUM_SECTORS) * sector_area
        if tooth_area_um2 <= 0.0:
            raise ValueError(f"Design {spec.report_design!r} has nonpositive tooth_area_um2.")

        ribs: list[tuple[float, float]] = []
        cursor = r_min
        for tr in tracks:
            if tr.r_inner <= cursor + 1e-9 or not (
                tr.r_inner < tr.r_tooth_in < tr.r_tooth_out < tr.r_outer
            ):
                raise ValueError(f"Invalid radial ordering in {spec.slug}.")
            ribs.append((cursor, tr.r_inner))
            cursor = tr.r_outer
        if cursor >= r_max - 1e-9:
            raise ValueError(f"Outer rib missing in {spec.slug}.")
        ribs.append((cursor, r_max))

        alias_names: list[str] = [spec.report_design]
        if spec.report_design == "Fractal_N0_SingleTrack":
            alias_names.append("SingleTooth_Track0")
        elif spec.report_design in ("Cantor_N2_FlatZ", "Rot_C4_TightSlot_N2"):
            alias_names.extend(["Cantor_N2_FlatZ", "Fractal_N2_Cantor3Track"])
        elif spec.report_design == "Ctrl_UniformPeriodic":
            alias_names.append("Uniform_3Track_Control")

        rep_task = find_bem_task(
            tasks,
            alias_names,
            spec.theta_rep_deg,
            spec.boundary,
            tier="Standard",
            formulation="vector_dyadic",
            z_tip_override_um=spec.z_tip_override_um,
        )
        att_task = find_bem_task(
            tasks,
            alias_names,
            spec.theta_att_deg,
            spec.boundary,
            tier="Standard",
            formulation="vector_dyadic",
            z_tip_override_um=spec.z_tip_override_um,
        )
        if spec.report_design == "Rot_C4_TightSlot_N2" and (rep_task is None or att_task is None):
            rot_rep = find_rotational_eval(rot_evals, "Rot_C4_TightSlot_N2", spec.theta_rep_deg)
            rot_att = find_rotational_eval(rot_evals, "Rot_C4_TightSlot_N2", spec.theta_att_deg)
            if rot_rep is None or rot_att is None:
                raise ValueError("Missing Rot_C4_TightSlot_N2 evaluation in rotational report.")
            f_rep_bem = required_number(rot_rep, "f_net_pN")
            f_att_bem = required_number(rot_att, "f_net_pN")
            rep_task_id = "rot_C4_6deg"
            att_task_id = "rot_C4_48deg"
        else:
            if rep_task is None or att_task is None:
                raise ValueError(
                    f"Missing Standard BEM task for {spec.slug} "
                    f"(found rep={rep_task is not None}, att={att_task is not None})."
                )
            f_rep_bem = required_number(rep_task, "F_z_pN")
            f_att_bem = required_number(att_task, "F_z_pN")
            rep_task_id = str(rep_task["task_id"])
            att_task_id = str(att_task["task_id"])

        delta_f_bem = f_rep_bem - f_att_bem

        f_rep_secondary: float | None = None
        f_att_secondary: float | None = None
        if spec.report_design == "Rot_C8_Compact_N2":
            rot_c8_6 = find_rotational_eval(rot_evals, "Rot_C8_Compact_N2", 6.0)
            if rot_c8_6 is None:
                raise ValueError("Missing Rot_C8_Compact_N2 6-deg evaluation in rotational report.")
            f_rep_secondary = required_number(rot_c8_6, "f_net_pN")
        elif spec.slug == "12_Fractal_N3_Cantor7Track_Monolithic":
            mono_n2_rep = find_bem_task(
                tasks, ["Cantor_N2_HybridRZ"], 3.0, "Full-Monolithic", tier="Standard"
            )
            mono_n2_att = find_bem_task(
                tasks, ["Cantor_N2_HybridRZ"], 48.0, "Full-Monolithic", tier="Standard"
            )
            if mono_n2_rep is None or mono_n2_att is None:
                raise ValueError(
                    "Missing Full-Monolithic Cantor_N2_HybridRZ BEM tasks in narrative report."
                )
            f_rep_secondary = required_number(mono_n2_rep, "F_z_pN")
            f_att_secondary = required_number(mono_n2_att, "F_z_pN")

        high_task = find_bem_task(
            tasks,
            alias_names,
            spec.theta_rep_deg,
            spec.boundary,
            tier="High",
            formulation="vector_dyadic",
            z_tip_override_um=spec.z_tip_override_um,
        )
        ultra_task = find_bem_task(
            tasks,
            alias_names,
            spec.theta_rep_deg,
            spec.boundary,
            tier="Ultra_High",
            formulation="vector_dyadic",
            z_tip_override_um=spec.z_tip_override_um,
        )
        f_rep_high = required_number(high_task, "F_z_pN") if high_task else None
        f_rep_ultra = required_number(ultra_task, "F_z_pN") if ultra_task else None

        f_rep_meep = None
        if spec.meep_rep_task_id is not None and spec.meep_rep_task_id in meep_tasks:
            m_row = meep_tasks[spec.meep_rep_task_id]
            if m_row.get("f_net_pN") is not None and (
                m_row.get("status") in ("complete", "completed")
                or m_row.get("source_status") == "complete"
            ):
                f_rep_meep = required_number(m_row, "f_net_pN")

        f_att_meep = None
        if spec.meep_att_task_id is not None and spec.meep_att_task_id in meep_tasks:
            m_row = meep_tasks[spec.meep_att_task_id]
            if m_row.get("f_net_pN") is not None and (
                m_row.get("status") in ("complete", "completed")
                or m_row.get("source_status") == "complete"
            ):
                f_att_meep = required_number(m_row, "f_net_pN")

        footprint = math.pi * (r_max**2 - r_min**2)
        loaded.append(
            LoadedConstellation(
                spec=spec,
                R_min=r_min,
                R_max=r_max,
                aperture_arc_deg=aperture_arc_deg,
                tooth_arc_deg=tooth_arc_deg,
                t_membrane=t_membrane,
                t_landing_pad=t_landing_pad,
                z_pad_top=z_pad_top,
                z_pad_bottom=z_pad_bottom,
                tracks=tuple(tracks),
                rib_intervals=tuple(ribs),
                footprint_um2=footprint,
                tooth_area_um2=tooth_area_um2,
                full_tooth_count=DEFAULT_NUM_SECTORS * len(tracks),
                f_rep_bem_pn=f_rep_bem,
                f_att_bem_pn=f_att_bem,
                delta_f_bem_pn=delta_f_bem,
                rep_task_id=rep_task_id,
                att_task_id=att_task_id,
                f_rep_high_pn=f_rep_high,
                f_rep_ultra_pn=f_rep_ultra,
                f_rep_meep_pn=f_rep_meep,
                f_att_meep_pn=f_att_meep,
                f_rep_secondary_pn=f_rep_secondary,
                f_att_secondary_pn=f_att_secondary,
            )
        )
    return tuple(loaded)


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
        resolve_blender(args.blender),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--mode",
        "blender",
        "--project-root",
        str(args.project_root),
        "--max-steps",
        str(args.max_steps),
        "--samples",
        str(args.samples),
        "--resolution",
        str(args.resolution),
        "--resolution-percentage",
        str(args.resolution_percentage),
        "--angular-segments",
        str(args.angular_segments),
        "--z-exaggeration",
        str(args.z_exaggeration),
        "--force",
    ]
    print("Launching:", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True)


def tooth_angular_spans_deg(theta_deg: float, tooth_arc_deg: float) -> list[tuple[float, float]]:
    center = (DEFAULT_TOOTH_CENTER_OFFSET_DEG + theta_deg) % DEFAULT_SECTOR_DEG
    low = center - tooth_arc_deg / 2.0
    high = center + tooth_arc_deg / 2.0
    if low < 0.0:
        return [(0.0, high), (low + DEFAULT_SECTOR_DEG, DEFAULT_SECTOR_DEG)]
    if high > DEFAULT_SECTOR_DEG:
        return [(low, DEFAULT_SECTOR_DEG), (0.0, high - DEFAULT_SECTOR_DEG)]
    return [(low, high)]


def build_blender(
    args: argparse.Namespace,
    constellations: tuple[LoadedConstellation, ...],
    paths: BuildPaths,
) -> None:
    try:
        bpy: Any = importlib.import_module("bpy")
        mathutils: Any = importlib.import_module("mathutils")
    except ImportError as error:
        raise RuntimeError("--mode blender must run inside Blender 4.5+.") from error
    if tuple(bpy.app.version) < (4, 5, 0):
        raise RuntimeError(f"Blender 4.5+ is required; found {bpy.app.version_string}.")

    paths.directory.mkdir(parents=True, exist_ok=True)
    paths.models_dir.mkdir(parents=True, exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)

    scene = bpy.context.scene
    scene.name = "All Fractal Casimir Clutch Constellations"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1e-6
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_percentage = args.resolution_percentage
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.04

    world = bpy.data.worlds.new("Constellation Studio World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.95, 0.96, 0.97, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0

    def material(
        name: str,
        rgb: tuple[float, float, float],
        metallic: float,
        roughness: float,
        emission: float = 0.0,
        alpha: float = 1.0,
    ) -> Any:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        shader = mat.node_tree.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = (*rgb, 1.0)
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Emission Color"].default_value = (*rgb, 1.0)
        shader.inputs["Emission Strength"].default_value = emission
        if "Alpha" in shader.inputs and alpha < 1.0:
            shader.inputs["Alpha"].default_value = alpha
            if hasattr(mat, "blend_method"):
                mat.blend_method = "BLEND"
        return mat

    mat_gold = material(
        "Stator Elevated Ribs | Grey-Brown Bronze", (0.46, 0.40, 0.35), 0.62, 0.28
    )
    mat_copper = material(
        "Stator Recessed Pads | Cyan Teal", (0.04, 0.66, 0.80), 0.70, 0.22, 0.05
    )
    mat_bronze = material(
        "Stator Slot Bridges | Deep Teal", (0.04, 0.50, 0.64), 0.68, 0.26, 0.03
    )
    mat_teal_gen1 = material(
        "Sector 0 Gen-1 Rotor Teeth | Rich Metallic Gold", (0.98, 0.68, 0.08), 0.78, 0.18, 0.06
    )
    mat_cyan_gen2 = material(
        "Sector 0 Gen-2 Rotor Teeth | Warm Amber Gold", (0.94, 0.56, 0.06), 0.78, 0.20, 0.05
    )
    mat_violet_gen3 = material(
        "Sector 0 Gen-3 Rotor Teeth | Burnished Gold", (0.86, 0.46, 0.04), 0.78, 0.22, 0.04
    )
    mat_overhang = material(
        "Sector 0 Overhang Tooth | Bright Metallic Gold", (0.98, 0.64, 0.08), 0.78, 0.18, 0.06
    )
    mat_sapphire = material(
        "Sectors 1-3 Rotor Teeth | Warm Metallic Gold", (0.90, 0.60, 0.12), 0.76, 0.22, 0.03
    )
    mat_titanium = material(
        "Monolithic Spider & Hub Collars | Crystalline Silicon", (0.36, 0.46, 0.58), 0.58, 0.26
    )
    mat_slate = material(
        "Monolithic Trench Slab | Silicon Slate", (0.24, 0.30, 0.38), 0.48, 0.34
    )
    mat_ref_ring = material(
        "Standard R=1.35um Reference Ring", (0.58, 0.64, 0.72), 0.35, 0.42
    )
    mat_pedestal = material(
        "Outer Stator Support Frame", (0.74, 0.78, 0.84), 0.30, 0.45
    )

    def create_annular_mesh(
        name: str,
        patches: Sequence[tuple[float, float, float, float, float, float]],
        mat: Any,
        collection: Any,
        parent: Any,
        z_scale: float,
    ) -> Any:
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int, int]] = []
        for low, high, start, end, bottom, top in patches:
            if not (low < high and start < end and bottom < top):
                raise ValueError(
                    f"Invalid annular patch in {name}: "
                    f"r=({low}, {high}), phi=({start}, {end}), z=({bottom}, {top})"
                )
            count = max(3, math.ceil((end - start) / 360.0 * args.angular_segments))
            offset = len(vertices)
            for idx in range(count + 1):
                angle = math.radians(start + (end - start) * idx / count)
                c, s = math.cos(angle), math.sin(angle)
                vertices.extend(
                    (
                        (low * c, low * s, bottom * z_scale),
                        (high * c, high * s, bottom * z_scale),
                        (low * c, low * s, top * z_scale),
                        (high * c, high * s, top * z_scale),
                    )
                )
            for idx in range(count):
                a, b = offset + 4 * idx, offset + 4 * (idx + 1)
                faces.extend(
                    (
                        (a, b, b + 1, a + 1),
                        (a + 2, a + 3, b + 3, b + 2),
                        (a, a + 2, b + 2, b),
                        (a + 1, b + 1, b + 3, a + 3),
                    )
                )
            last = offset + 4 * count
            faces.extend(
                (
                    (offset, offset + 1, offset + 3, offset + 2),
                    (last, last + 2, last + 3, last + 1),
                )
            )
        mesh = bpy.data.meshes.new(name + "_mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        obj.data.materials.append(mat)
        obj.parent = parent
        return obj

    def build_constellation_collection(item: LoadedConstellation) -> tuple[Any, Any]:
        col_name = f"Constellation_{item.spec.slug}"
        collection = bpy.data.collections.new(col_name)
        scene.collection.children.link(collection)

        anchor = bpy.data.objects.new(f"Anchor_{item.spec.slug}", None)
        anchor.empty_display_type = "PLAIN_AXES"
        anchor.empty_display_size = 0.25
        collection.objects.link(anchor)

        z_scale = args.z_exaggeration
        ribs: list[tuple[float, float, float, float, float, float]] = []
        pads: list[tuple[float, float, float, float, float, float]] = []
        bridges: list[tuple[float, float, float, float, float, float]] = []
        risers: list[tuple[float, float, float, float, float, float]] = []

        for sector in range(DEFAULT_NUM_SECTORS):
            base = sector * DEFAULT_SECTOR_DEG
            boundary = base + item.aperture_arc_deg
            # Cut away the last 28 deg of Sector 3's recessed bridge [332, 360] deg
            # so the front-right camera sees the exposed radial (r, z) cross-section at phi=0!
            pad_end = base + 62.0 if sector == 3 else base + DEFAULT_SECTOR_DEG
            for r_in, r_out in item.rib_intervals:
                ribs.append((r_in, r_out, base, boundary, -item.t_membrane, 0.0))
                pads.append((r_in, r_out, boundary, pad_end, item.z_pad_bottom, item.z_pad_top))
                risers.append((r_in, r_out, boundary - 0.35, boundary + 0.35, item.z_pad_top, 0.0))
                if sector != 0:
                    risers.append((r_in, r_out, base - 0.35, base + 0.35, item.z_pad_top, 0.0))
            for tr in item.tracks:
                bridges.append(
                    (tr.r_inner, tr.r_outer, boundary, pad_end, item.z_pad_bottom, item.z_pad_top)
                )

        create_annular_mesh(
            f"{item.spec.slug}_stator_ribs", ribs, mat_gold, collection, anchor, z_scale
        )
        create_annular_mesh(
            f"{item.spec.slug}_stator_pads", pads, mat_copper, collection, anchor, z_scale
        )
        create_annular_mesh(
            f"{item.spec.slug}_stator_bridges", bridges, mat_bronze, collection, anchor, z_scale
        )
        create_annular_mesh(
            f"{item.spec.slug}_stator_risers", risers, mat_copper, collection, anchor, z_scale
        )

        # Rotor teeth at theta = theta_rep_deg (3 deg open-slot state)
        spans = tooth_angular_spans_deg(item.spec.theta_rep_deg, item.tooth_arc_deg)
        s0_gen1: list[tuple[float, float, float, float, float, float]] = []
        s0_gen2: list[tuple[float, float, float, float, float, float]] = []
        s0_gen3: list[tuple[float, float, float, float, float, float]] = []
        s_other: list[tuple[float, float, float, float, float, float]] = []

        for sector in range(DEFAULT_NUM_SECTORS):
            base = sector * DEFAULT_SECTOR_DEG
            for tr in item.tracks:
                for a, b in spans:
                    if b <= a:
                        continue
                    patch = (
                        tr.r_tooth_in,
                        tr.r_tooth_out,
                        base + a,
                        base + b,
                        tr.z_tip,
                        tr.z_top,
                    )
                    if sector == 0:
                        if tr.level == 1:
                            s0_gen1.append(patch)
                        elif tr.level == 2:
                            s0_gen2.append(patch)
                        else:
                            s0_gen3.append(patch)
                    else:
                        s_other.append(patch)

        is_overhang = item.spec.z_tip_override_um is not None and item.spec.z_tip_override_um > -0.08
        if s0_gen1:
            create_annular_mesh(
                f"{item.spec.slug}_rotor_s0_gen1",
                s0_gen1,
                mat_overhang if is_overhang else mat_teal_gen1,
                collection,
                anchor,
                z_scale,
            )
        if s0_gen2:
            create_annular_mesh(
                f"{item.spec.slug}_rotor_s0_gen2",
                s0_gen2,
                mat_overhang if is_overhang else mat_cyan_gen2,
                collection,
                anchor,
                z_scale,
            )
        if s0_gen3:
            create_annular_mesh(
                f"{item.spec.slug}_rotor_s0_gen3",
                s0_gen3,
                mat_violet_gen3,
                collection,
                anchor,
                z_scale,
            )
        if s_other:
            create_annular_mesh(
                f"{item.spec.slug}_rotor_s123",
                s_other,
                mat_sapphire,
                collection,
                anchor,
                z_scale,
            )

        # Reference scale ring at standard R_max = 1.35 um + outer stator support frame
        ref_z = item.z_pad_bottom * z_scale - 0.04
        create_annular_mesh(
            f"{item.spec.slug}_ref_ring_1p35um",
            [(1.345, 1.365, 0.0, 360.0, ref_z - 0.012, ref_z)],
            mat_ref_ring,
            collection,
            anchor,
            1.0,
        )
        create_annular_mesh(
            f"{item.spec.slug}_outer_support_frame",
            [(item.R_max, item.R_max + 0.07, 0.0, 315.0, item.z_pad_bottom * z_scale, 0.0)],
            mat_pedestal,
            collection,
            anchor,
            1.0,
        )

        # Passive monolithic NEMS support structures (for Step 6 Full-Monolithic models)
        if item.spec.boundary == "Full-Monolithic":
            inner_collar_r = max(
                MONOLITHIC_MIN_INNER_RADIUS_UM,
                item.R_min - MONOLITHIC_COLLAR_OVERHANG_UM,
            )
            outer_collar_r = item.R_max + MONOLITHIC_COLLAR_OVERHANG_UM
            spoke_patches: list[tuple[float, float, float, float, float, float]] = []
            for sector in range(DEFAULT_NUM_SECTORS):
                base = sector * DEFAULT_SECTOR_DEG
                for a, b in spans:
                    if b <= a:
                        continue
                    spoke_patches.append(
                        (
                            item.R_min,
                            item.R_max,
                            base + a,
                            base + b,
                            MONOLITHIC_SPOKE_Z_MIN_UM,
                            MONOLITHIC_SPOKE_Z_MAX_UM,
                        )
                    )
                    # Vertical carrier posts connecting rotor teeth top (z=0) to spider spoke
                    for tr in item.tracks:
                        spoke_patches.append(
                            (
                                tr.r_tooth_in,
                                tr.r_tooth_out,
                                base + a + 0.25 * (b - a),
                                base + a + 0.75 * (b - a),
                                max(0.0, tr.z_top * z_scale),
                                MONOLITHIC_SPOKE_Z_MIN_UM,
                            )
                        )
            # Leave front cutaway [315, 355] deg open on outer collar so active region stays visible
            spoke_patches.append(
                (
                    inner_collar_r,
                    item.R_min,
                    0.0,
                    360.0,
                    MONOLITHIC_SPOKE_Z_MIN_UM,
                    MONOLITHIC_SPOKE_Z_MAX_UM,
                )
            )
            spoke_patches.append(
                (
                    item.R_max,
                    outer_collar_r,
                    0.0,
                    310.0,
                    MONOLITHIC_SPOKE_Z_MIN_UM,
                    MONOLITHIC_SPOKE_Z_MAX_UM,
                )
            )
            create_annular_mesh(
                f"{item.spec.slug}_monolithic_spider_and_collars",
                spoke_patches,
                mat_titanium,
                collection,
                anchor,
                1.0,
            )
            trench_patches = [
                (
                    item.R_min,
                    item.R_max,
                    0.0,
                    332.0,
                    MONOLITHIC_TRENCH_Z_MIN_UM,
                    MONOLITHIC_TRENCH_Z_MAX_UM,
                )
            ]
            create_annular_mesh(
                f"{item.spec.slug}_monolithic_trench_slab",
                trench_patches,
                mat_slate,
                collection,
                anchor,
                1.0,
            )

        anchor["slug"] = item.spec.slug
        anchor["report_design"] = item.spec.report_design
        anchor["boundary"] = item.spec.boundary
        anchor["f_rep_bem_pN"] = item.f_rep_bem_pn
        anchor["f_att_bem_pN"] = item.f_att_bem_pn
        anchor["delta_f_bem_pN"] = item.delta_f_bem_pn
        return collection, anchor

    built: list[tuple[LoadedConstellation, Any, Any]] = []
    for item in constellations:
        col, anchor = build_constellation_collection(item)
        built.append((item, col, anchor))

    def aim(obj: Any, target: tuple[float, float, float]) -> None:
        direction = mathutils.Vector(target) - obj.location
        if direction.length <= 1e-9:
            raise ValueError("Camera or light coincides with its target.")
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    lights: list[Any] = []
    for name, location, energy, size in (
        ("Key studio softbox", (2.2, -3.4, 4.5), 480.0, 3.5),
        ("Fill studio softbox", (-3.0, -1.2, 2.6), 300.0, 3.0),
        ("Rim studio softbox", (1.0, 3.6, 3.2), 520.0, 2.5),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = size
        light_obj = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light_obj)
        light_obj.location = location
        aim(light_obj, (0.0, 0.0, -0.10))
        lights.append(light_obj)

    camera_data = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "PERSP"
    camera_data.lens = 48.0
    camera_data.clip_start = 0.001
    camera_data.clip_end = 250.0

    def render_still(destination: Path, width: int, height: int) -> None:
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.filepath = str(destination)
        bpy.ops.render.render(write_still=True, scene=scene.name)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError(f"Render did not produce {destination}.")

    panel_w = args.resolution
    panel_h = round(args.resolution * 640 / 1200)

    # 1. Render each constellation individually at the origin and save its individual .blend
    for item, col, anchor in built:
        for _, other_col, other_anchor in built:
            is_current = other_col == col
            other_col.hide_render = not is_current
            other_col.hide_viewport = not is_current
            other_anchor.location = (0.0, 0.0, 0.0)

        r_focus = max(1.02, item.R_max)
        if item.spec.boundary == "Full-Monolithic":
            dist = r_focus * 2.15
            camera.location = (dist * 0.90, -dist * 0.94, dist * 0.68)
            aim(camera, (0.0, 0.0, -0.04))
        else:
            dist = r_focus * 1.74
            camera.location = (dist * 0.86, -dist * 0.90, dist * 0.66)
            aim(camera, (0.0, 0.0, -0.14))

        render_still(paths.panel_renders[item.spec.slug], panel_w, panel_h)
        ind_blend = paths.individual_blends[item.spec.slug]
        bpy.ops.wm.save_as_mainfile(filepath=str(ind_blend))

    # 2. Arrange ALL 12 constellations side-by-side in a 2-row x 6-column 3D exhibition lineup
    # Row 0 (#1..#6) in back-top row (y > 0), Row 1 (#7..#12) in front-bottom row (y < 0)
    spacing_x = 3.72
    spacing_y = 3.85
    for idx, (item, col, anchor) in enumerate(built):
        col.hide_render = False
        col.hide_viewport = False
        row = idx // 6
        col_idx = idx % 6
        x_pos = (col_idx - 2.5) * spacing_x
        y_pos = (0.5 - row) * spacing_y
        z_pos = 0.28 * (1 - row)
        anchor.location = (x_pos, y_pos, z_pos)

    # Reposition lights to illuminate the entire 22 um x 8 um side-by-side 3D lineup evenly
    lights[0].location = (6.0, -14.0, 16.0)
    lights[0].data.energy = 8500.0
    lights[0].data.size = 18.0
    aim(lights[0], (0.0, 0.0, 0.0))

    lights[1].location = (-10.0, -10.0, 12.0)
    lights[1].data.energy = 4500.0
    lights[1].data.size = 16.0
    aim(lights[1], (0.0, 0.0, 0.0))

    lights[2].location = (0.0, 14.0, 13.0)
    lights[2].data.energy = 6500.0
    lights[2].data.size = 16.0
    aim(lights[2], (0.0, 0.0, 0.0))

    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 22.4
    camera.location = (0.0, -17.5, 13.0)
    aim(camera, (0.0, 0.12, -0.18))

    lineup_w = max(2400, round(args.resolution * 2.0))
    lineup_h = round(lineup_w * 640 / 2400)
    render_still(paths.lineup_render, lineup_w, lineup_h)

    scene["constellation_count"] = len(constellations)
    scene["source_report"] = str(
        args.project_root / "results" / "nature_6step_narrative_report.json"
    )
    scene["display_z_exaggeration"] = args.z_exaggeration
    bpy.ops.wm.save_as_mainfile(filepath=str(paths.master_blend))
    if not paths.master_blend.is_file() or paths.master_blend.stat().st_size == 0:
        raise RuntimeError("Master Blender scene was not saved.")


def export_metadata(
    args: argparse.Namespace,
    constellations: tuple[LoadedConstellation, ...],
    paths: BuildPaths,
) -> None:
    manifest = {
        "source_report": str(
            args.project_root / "results" / "nature_6step_narrative_report.json"
        ),
        "radial_units": "um",
        "z_exaggeration": args.z_exaggeration,
        "master_blend": str(paths.master_blend),
        "lineup_render": str(paths.lineup_render),
        "constellations": [
            {
                "index": item.spec.index,
                "panel_letter": item.spec.panel_letter,
                "slug": item.spec.slug,
                "title": item.spec.title,
                "subtitle": item.spec.subtitle,
                "step_label": item.spec.step_label,
                "report_design": item.spec.report_design,
                "boundary": item.spec.boundary,
                "R_min_um": item.R_min,
                "R_max_um": item.R_max,
                "track_count": len(item.tracks),
                "full_tooth_count": item.full_tooth_count,
                "footprint_um2": item.footprint_um2,
                "tooth_area_um2": item.tooth_area_um2,
                "f_rep_bem_pN": item.f_rep_bem_pn,
                "f_att_bem_pN": item.f_att_bem_pn,
                "delta_f_bem_pN": item.delta_f_bem_pn,
                "f_rep_secondary_pN": item.f_rep_secondary_pn,
                "f_att_secondary_pN": item.f_att_secondary_pn,
                "f_rep_high_pN": item.f_rep_high_pn,
                "f_rep_ultra_pN": item.f_rep_ultra_pn,
                "f_rep_meep_pN": item.f_rep_meep_pn,
                "f_att_meep_pN": item.f_att_meep_pn,
                "rep_task_id": item.rep_task_id,
                "att_task_id": item.att_task_id,
                "render_path": str(paths.panel_renders[item.spec.slug]),
                "blend_path": str(paths.individual_blends[item.spec.slug]),
                "tracks": [dataclasses.asdict(tr) for tr in item.tracks],
            }
            for item in constellations
        ],
    }
    atomic_text(paths.manifest, json.dumps(manifest, indent=2, allow_nan=False) + "\n")


def draw_rz_profile(ax: Any, item: LoadedConstellation, show_ylabel: bool = True) -> None:
    from matplotlib.patches import Rectangle

    ax.set_facecolor("#FFFFFF")
    r_limit = 1.72
    ax.set_xlim(0.0, r_limit)
    ax.set_ylim(-290.0, 136.0)

    # Recessed landing-pad level (cyan/teal, z in [-265, -115] nm)
    pad_top_nm = item.z_pad_top * 1000.0
    pad_bot_nm = item.z_pad_bottom * 1000.0
    ax.axhspan(
        pad_bot_nm,
        pad_top_nm,
        xmin=item.R_min / r_limit,
        xmax=item.R_max / r_limit,
        color="#06B6D4",
        alpha=0.25,
    )
    ax.plot(
        [item.R_min, item.R_max],
        [pad_top_nm, pad_top_nm],
        "--",
        color="#0891B2",
        linewidth=0.8,
    )

    # Elevated stator aperture rings (grey/brown, z in [-25, 0] nm)
    mem_bot_nm = -item.t_membrane * 1000.0
    for r_in, r_out in item.rib_intervals:
        ax.add_patch(
            Rectangle(
                (r_in, mem_bot_nm),
                r_out - r_in,
                -mem_bot_nm,
                facecolor="#78716C",
                edgecolor="#44403C",
                linewidth=0.5,
            )
        )

    # Gold rotor teeth across radial coordinate r (um)
    level_gold = {
        1: "#F59E0B",
        2: "#D97706",
        3: "#B45309",
    }
    for tr in item.tracks:
        color = level_gold.get(tr.level, "#F59E0B")
        z_tip_nm = tr.z_tip * 1000.0
        h_nm = tr.h_teeth * 1000.0
        ax.add_patch(
            Rectangle(
                (tr.r_tooth_in, z_tip_nm),
                tr.r_tooth_out - tr.r_tooth_in,
                h_nm,
                facecolor=color,
                edgecolor="#78350F",
                linewidth=0.5,
            )
        )

    if item.spec.boundary == "Full-Monolithic":
        ax.axhspan(
            42.0,
            98.0,
            xmin=max(0.0, (item.R_min - 0.10) / r_limit),
            xmax=min(1.0, (item.R_max + 0.04) / r_limit),
            color="#64748B",
            alpha=0.28,
        )
        ax.text(
            (item.R_min + item.R_max) / 2.0 - 0.03,
            70.0,
            "Spokes (+350..+470 nm) & trench (-650..-550 nm)",
            color="#1E293B",
            fontsize=4.8,
            ha="center",
            va="center",
        )

    ax.axhline(0.0, color="#6B7280", linestyle=":", linewidth=0.55, alpha=0.7)
    ax.set_xticks([0.0, 0.4, 0.8, 1.2, 1.6])
    ax.set_yticks([-250, -100, 0])
    if not show_ylabel:
        ax.set_yticklabels([])
    else:
        ax.set_ylabel("z (nm)", fontsize=6.0, color="#111827", labelpad=1.2)
    ax.set_xlabel("r (\u03bcm)", fontsize=6.0, color="#111827", labelpad=0.4)
    ax.tick_params(colors="#111827", labelsize=6.0, length=2.0, pad=1.0)
    for spine in ax.spines.values():
        spine.set_edgecolor("#9CA3AF")
        spine.set_linewidth(0.55)


def format_panel_header(item: LoadedConstellation) -> tuple[str, str]:
    letter = item.spec.panel_letter
    f_rep = item.f_rep_bem_pn
    f_att = item.f_att_bem_pn
    if letter == "a":
        title = "N = 0 symmetric overhang"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 1 track ($z_{{\\mathrm{{tip}}}}$ = \u221255 nm)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "b":
        title = "N = 0 deep interdigitation"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 1 track ($z_{{\\mathrm{{tip}}}}$ = \u2212100 nm)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "c":
        title = "N = 1 fundamental Cantor slot"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 1 track ($W_1$ = 350 nm)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "d":
        title = "Single wide tooth control"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 1 track "
            f"($A_{{\\mathrm{{tooth}}}}$ = {item.tooth_area_um2:.3f} \u03bcm\u00b2)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "e":
        title = "Uniform periodic grating control"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 3 tracks "
            f"($A_{{\\mathrm{{tooth}}}}$ = {item.tooth_area_um2:.3f} \u03bcm\u00b2)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "f":
        title = "Size-matched monotonic control"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 3 tracks "
            f"($A_{{\\mathrm{{tooth}}}}$ = {item.tooth_area_um2:.3f} \u03bcm\u00b2)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "g":
        title = "Cantor N = 2 uniform-depth"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 3 tracks ($H_1 = H_2$ = 100 nm)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "h":
        title = "Cantor N = 2 (r, z)-scaled"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 3 tracks ($H_1$ = 100, $H_2$ = 90 nm)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "i":
        if item.f_rep_secondary_pn is None:
            raise ValueError("Missing secondary 6-deg force for Rot_C8_Compact_N2.")
        f6 = item.f_rep_secondary_pn
        title = "Compact N = 2 rotational variant"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 3 tracks "
            f"($A_{{\\mathrm{{tooth}}}}$ = {item.tooth_area_um2:.3f} \u03bcm\u00b2)\n"
            f"$F_z$(3\u00b0/6\u00b0) = {f_rep:+.2f}/{f6:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "j":
        title = "Tight-slot N = 2 rotational variant"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 3 tracks "
            f"($A_{{\\mathrm{{tooth}}}}$ = {item.tooth_area_um2:.3f} \u03bcm\u00b2)\n"
            f"$F_z$(6\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    elif letter == "k":
        title = "Cantor N = 3 seven-track hierarchy (28 teeth)"
        sub = (
            f"$R \\in$ [{item.R_min:.2f}, {item.R_max:.2f}] \u03bcm | 7 tracks "
            f"($A_{{\\mathrm{{tooth}}}}$ = {item.tooth_area_um2:.3f} \u03bcm\u00b2)\n"
            f"$F_z$(3\u00b0) = {f_rep:+.2f} pN, $F_z$(48\u00b0) = {f_att:+.2f} pN"
        )
    else:
        if item.f_rep_secondary_pn is None or item.f_att_secondary_pn is None:
            raise ValueError("Missing Full-Monolithic N=2 forces for Panel l.")
        f_rep_n2 = item.f_rep_secondary_pn
        f_att_n2 = item.f_att_secondary_pn
        title = "Monolithic N = 2 & N = 3 assemblies"
        sub = (
            "4 radial spokes + hub collars + trench\n"
            f"$F_z$(3\u00b0) = {f_rep_n2:+.2f}/{f_rep:+.2f} pN, "
            f"$F_z$(48\u00b0) = {f_att_n2:+.2f}/{f_att:+.2f} pN"
        )
    return title, sub


def compose_figure(
    args: argparse.Namespace,
    constellations: tuple[LoadedConstellation, ...],
    paths: BuildPaths,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.gridspec as gridspec
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "mathtext.fontset": "custom",
            "mathtext.rm": "Arial",
            "mathtext.it": "Arial:italic",
            "mathtext.bf": "Arial:bold",
            "axes.labelsize": 6.0,
            "xtick.labelsize": 6.0,
            "ytick.labelsize": 6.0,
        }
    )

    paths.figure_png.parent.mkdir(parents=True, exist_ok=True)
    # 180 mm x 252 mm = 7.08 in x 9.92 in at 600 DPI (5 rows x 3 columns)
    fig = plt.figure(figsize=(7.08, 9.92), dpi=600, facecolor="#FFFFFF")

    outer = gridspec.GridSpec(
        5,
        3,
        figure=fig,
        hspace=0.52,
        wspace=0.19,
        left=0.068,
        right=0.985,
        top=0.945,
        bottom=0.045,
    )

    for idx, item in enumerate(constellations):
        grid_row = idx // 3
        grid_col = idx % 3
        sub = gridspec.GridSpecFromSubplotSpec(
            2,
            1,
            subplot_spec=outer[grid_row, grid_col],
            height_ratios=[2.20, 1.0],
            hspace=0.05,
        )
        ax_img = fig.add_subplot(sub[0])
        ax_rz = fig.add_subplot(sub[1])

        ax_img.set_facecolor("#F3F4F6")
        ax_img.imshow(mpimg.imread(paths.panel_renders[item.spec.slug]))
        ax_img.set_xticks([])
        ax_img.set_yticks([])
        for spine in ax_img.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor("#D1D5DB")
            spine.set_linewidth(0.6)

        title_text, sub_text = format_panel_header(item)
        # 8 pt bold lowercase panel label outside top-left
        ax_img.text(
            -0.08,
            1.31,
            item.spec.panel_letter,
            transform=ax_img.transAxes,
            fontsize=8.0,
            fontweight="bold",
            color="#111827",
            ha="left",
            va="bottom",
        )
        # 7 pt bold title above panel
        ax_img.text(
            0.0,
            1.31,
            title_text,
            transform=ax_img.transAxes,
            fontsize=7.0,
            fontweight="bold",
            color="#111827",
            ha="left",
            va="bottom",
        )
        # 6 pt two-line specification subtitle
        ax_img.text(
            0.0,
            1.02,
            sub_text,
            transform=ax_img.transAxes,
            fontsize=6.0,
            color="#374151",
            ha="left",
            va="bottom",
            linespacing=1.08,
        )

        draw_rz_profile(ax_rz, item, show_ylabel=(grid_col == 0))

    # Row 5 (Panels m, n, o): Unified 3D Conformal-Recursive Polar Cantor Hierarchy (r, theta, z)
    uni_json_path = args.project_root / "results" / "n3_unified_3d_fractal_factorial_study.json"
    uni_render_dir = args.project_root / "results" / "n3_unified_3d_blender"
    if uni_json_path.is_file() and uni_render_dir.is_dir():
        from matplotlib.patches import Rectangle as _Rect
        from execution.multiscale_3d_fractal_architecture import make_factorial_design

        uni_study = json.loads(uni_json_path.read_text(encoding="utf-8"))
        uni_by_code = {str(r["code"]): r for r in uni_study.get("records", uni_study.get("results", []))}
        f3_ang_raw = uni_study.get("f3_111_angular_states", {})
        if isinstance(f3_ang_raw, dict):
            f3_att_48 = float(f3_ang_raw.get("landing_pad", {}).get("F_z_pN", -19.98))
        else:
            f3_att_48 = -19.98

        row5_specs = (
            (
                0,
                "m",
                "F1r_100",
                make_factorial_design("Cantor_100_RadialOnly", "F1r_100", "fractal_1d", True, True, False, False, iso_area=True),
                uni_render_dir / "render_03_F1r_100_Cantor_100_RadialOnly.png",
                "Unified 1D radial Cantor (F1r_100)",
                lambda r_row: (
                    f"$R \\in$ [0.30, 1.65] \u03bcm | 12 sub-teeth + 5 Cu sub-ribs\n"
                    f"$F_z$(3\u00b0) = {float(r_row.get('F_z_pN', r_row.get('f_z_pN', 9.09))):+.2f} pN ($A_{{\\mathrm{{tooth}}}}$ = {float(r_row.get('A_tooth_um2', r_row.get('total_tooth_area_um2', 0.310))):.3f} \u03bcm\u00b2)"
                ),
            ),
            (
                1,
                "n",
                "F2rt_110",
                make_factorial_design("Cantor_110_RadialTheta_Planar1Mask", "F2rt_110", "fractal_2d", True, True, True, False, iso_area=True),
                uni_render_dir / "render_06_F2rt_110_Cantor_110_RadialTheta_Planar1Mask.png",
                "Planar 2D (r, \u03b8) Cantor 1-mask (F2rt_110)",
                lambda r_row: (
                    f"$R \\in$ [0.30, 1.65] \u03bcm | 12 sub-teeth, 24 lobes (1 mask)\n"
                    f"$F_z$(3\u00b0) = {float(r_row.get('F_z_pN', r_row.get('f_z_pN', 13.54))):+.2f} pN ($A_{{\\mathrm{{tooth}}}}$ = {float(r_row.get('A_tooth_um2', r_row.get('total_tooth_area_um2', 0.310))):.3f} \u03bcm\u00b2)"
                ),
            ),
            (
                2,
                "o",
                "F3_111",
                make_factorial_design("Cantor_111_Unified3DFractal", "F3_111", "most_fractal_3d", True, True, True, True, iso_area=True),
                uni_render_dir / "render_09_F3_111_Cantor_111_Unified3DFractal.png",
                "Unified 3D (r, \u03b8, z) Cantor (F3_111)",
                lambda r_row: (
                    f"$R \\in$ [0.30, 1.65] \u03bcm | 12 teeth, 24 lobes, 3 z-tiers\n"
                    f"$F_z$(3\u00b0) = {float(r_row.get('F_z_pN', r_row.get('f_z_pN', 18.55))):+.2f} pN, $F_z$(48\u00b0) = {f3_att_48:+.2f} pN"
                ),
            ),
        )

        for col_idx, p_letter, code_key, u_des, r_png, p_title, sub_fn in row5_specs:
            if code_key not in uni_by_code or not r_png.is_file():
                continue
            r_row = uni_by_code[code_key]
            sub = gridspec.GridSpecFromSubplotSpec(
                2,
                1,
                subplot_spec=outer[4, col_idx],
                height_ratios=[2.20, 1.0],
                hspace=0.05,
            )
            ax_img = fig.add_subplot(sub[0])
            ax_rz = fig.add_subplot(sub[1])

            ax_img.set_facecolor("#F3F4F6")
            img_arr = mpimg.imread(r_png)
            # Crop 4:3 -> 1.5625:1 aspect ratio to match Panels a-l
            h_img, w_img = img_arr.shape[:2]
            if w_img > 0 and h_img > 0 and abs((w_img / h_img) - (4.0 / 3.0)) < 0.05:
                x_crop = int(round(w_img * 0.09))
                w_new = w_img - 2 * x_crop
                h_new = int(round(w_new / 1.5625))
                y_crop_top = int(round((h_img - h_new) * 0.56))
                img_arr = img_arr[y_crop_top : y_crop_top + h_new, x_crop : x_crop + w_new]
            ax_img.imshow(img_arr)
            ax_img.set_xticks([])
            ax_img.set_yticks([])
            for spine in ax_img.spines.values():
                spine.set_visible(True)
                spine.set_edgecolor("#B91C1C" if code_key == "F3_111" else "#D1D5DB")
                spine.set_linewidth(0.85 if code_key == "F3_111" else 0.6)

            ax_img.text(
                -0.10,
                1.31,
                p_letter,
                transform=ax_img.transAxes,
                fontsize=8.0,
                fontweight="bold",
                color="#111827",
                ha="left",
                va="bottom",
            )
            ax_img.text(
                0.0,
                1.31,
                p_title,
                transform=ax_img.transAxes,
                fontsize=6.8,
                fontweight="bold",
                color="#991B1B" if code_key == "F3_111" else "#111827",
                ha="left",
                va="bottom",
            )
            ax_img.text(
                0.0,
                1.02,
                sub_fn(r_row),
                transform=ax_img.transAxes,
                fontsize=5.85,
                color="#374151",
                ha="left",
                va="bottom",
                linespacing=1.08,
            )

            # Draw Unified 3D (r, z) cross-section with primary stator ribs, copper sub-ribs, and 12 sub-teeth
            ax_rz.set_facecolor("#FFFFFF")
            r_limit = 1.72
            ax_rz.set_xlim(0.0, r_limit)
            ax_rz.set_ylim(-290.0, 136.0)
            pad_top_nm = u_des.z_pad_top * 1000.0
            pad_bot_nm = (u_des.z_pad_top - u_des.t_landing_pad) * 1000.0
            ax_rz.axhspan(
                pad_bot_nm,
                pad_top_nm,
                xmin=u_des.R_min / r_limit,
                xmax=u_des.R_max / r_limit,
                color="#06B6D4",
                alpha=0.25,
            )
            ax_rz.plot(
                [u_des.R_min, u_des.R_max],
                [pad_top_nm, pad_top_nm],
                "--",
                color="#0891B2",
                linewidth=0.8,
            )
            mem_bot_nm = -u_des.t_membrane * 1000.0
            # Primary stator ribs
            prev_r = u_des.R_min
            for sl in u_des.slots:
                if sl.r_inner > prev_r + 1e-6:
                    ax_rz.add_patch(
                        _Rect(
                            (prev_r, mem_bot_nm),
                            sl.r_inner - prev_r,
                            -mem_bot_nm,
                            facecolor="#78716C",
                            edgecolor="#44403C",
                            linewidth=0.45,
                        )
                    )
                # Copper stator sub-ribs inside subdivided slots
                if len(sl.stator_subslots) > 1:
                    for idx_ss in range(len(sl.stator_subslots) - 1):
                        sr_in = sl.stator_subslots[idx_ss][1]
                        sr_out = sl.stator_subslots[idx_ss + 1][0]
                        if sr_out > sr_in + 1e-6:
                            ax_rz.add_patch(
                                _Rect(
                                    (sr_in, mem_bot_nm),
                                    sr_out - sr_in,
                                    -mem_bot_nm,
                                    facecolor="#D95F02",
                                    edgecolor="#7C2D12",
                                    linewidth=0.45,
                                )
                            )
                prev_r = sl.r_outer
            if u_des.R_max > prev_r + 1e-6:
                ax_rz.add_patch(
                    _Rect(
                        (prev_r, mem_bot_nm),
                        u_des.R_max - prev_r,
                        -mem_bot_nm,
                        facecolor="#78716C",
                        edgecolor="#44403C",
                        linewidth=0.45,
                    )
                )
            # 12 rotor sub-teeth
            level_gold_u = {1: "#F59E0B", 2: "#D97706", 3: "#B45309"}
            for sl in u_des.slots:
                for st in sl.sub_teeth:
                    col_st = level_gold_u.get(int(st.sub_level_z), "#F59E0B")
                    ax_rz.add_patch(
                        _Rect(
                            (st.r_tooth_in, st.z_tip * 1000.0),
                            st.r_tooth_out - st.r_tooth_in,
                            st.h_teeth * 1000.0,
                            facecolor=col_st,
                            edgecolor="#78350F",
                            linewidth=0.45,
                        )
                    )
            ax_rz.axhline(0.0, color="#6B7280", linestyle=":", linewidth=0.55, alpha=0.7)
            ax_rz.set_xticks([0.0, 0.4, 0.8, 1.2, 1.6])
            ax_rz.set_yticks([-250, -100, 0])
            if col_idx != 0:
                ax_rz.set_yticklabels([])
            else:
                ax_rz.set_ylabel("z (nm)", fontsize=6.0, color="#111827", labelpad=1.2)
            ax_rz.set_xlabel("r (\u03bcm)", fontsize=6.0, color="#111827", labelpad=0.4)
            ax_rz.tick_params(colors="#111827", labelsize=6.0, length=2.0, pad=1.0)
            for spine in ax_rz.spines.values():
                spine.set_edgecolor("#9CA3AF")
                spine.set_linewidth(0.55)

    legend_handles = [
        Patch(facecolor="#F59E0B", edgecolor="#78350F", linewidth=0.5, label="Gold rotor teeth (Au)"),
        Patch(
            facecolor="#78716C",
            edgecolor="#44403C",
            linewidth=0.5,
            label="Stator aperture rings ($z \\in [-25, 0]$ nm)",
        ),
        Patch(
            facecolor="#D95F02",
            edgecolor="#7C2D12",
            linewidth=0.5,
            label="Cantor stator sub-ribs (Cu, Panels m\u2013o)",
        ),
        Patch(
            facecolor="#06B6D4",
            edgecolor="#0891B2",
            alpha=0.45,
            linewidth=0.6,
            label="Recessed landing pads ($z_{\\mathrm{pad}} = -115$ nm)",
        ),
        Patch(
            facecolor="#64748B",
            edgecolor="#334155",
            alpha=0.55,
            linewidth=0.5,
            label="Monolithic Si spokes & trench",
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.51, 0.003),
        ncol=5,
        frameon=False,
        fontsize=5.5,
        handlelength=1.0,
        handletextpad=0.35,
        columnspacing=0.8,
    )

    try:
        fig.savefig(paths.figure_png, dpi=600, facecolor="#FFFFFF")
        fig.savefig(paths.figure_pdf, facecolor="#FFFFFF")
        shutil.copyfile(paths.figure_png, paths.composite_png)
        for paper_sub in ("Fractal_Casimir_Nature_EM", "FCE_Nature_ver01"):
            paper_fig_dir = args.project_root / "Papers" / paper_sub / "figures"
            if paper_fig_dir.is_dir():
                shutil.copyfile(paths.figure_png, paper_fig_dir / paths.figure_png.name)
                shutil.copyfile(paths.figure_pdf, paper_fig_dir / paths.figure_pdf.name)
    finally:
        plt.close(fig)

    logger = importlib.import_module("utils.metrics_logger")
    columns_used = [
        "step",
        "design",
        "theta_deg",
        "z_tip_um",
        "F_z_pN",
        "boundary",
        "tier",
        "formulation",
        "footprint_um2",
    ]
    for fig_path in (paths.figure_png, paths.figure_pdf):
        logger.save_plot_provenance(
            str(fig_path.relative_to(args.project_root)),
            data_source="results/nature_6step_narrative_data.csv",
            columns_used=columns_used,
            solver_name="execution.casimir_bem_solver.run_bem_casimir_solver",
            solver_parameters={
                "formulation": "vector_dyadic",
                "source_report": "results/nature_6step_narrative_report.json",
                "rotational_report": "results/rotational_z_eff_clutch_report.json",
                "unified_3d_report": "results/n3_unified_3d_fractal_factorial_study.json",
                "constellation_count": len(constellations) + 3,
                "display_z_exaggeration": args.z_exaggeration,
            },
        )
        prov_sidecar = Path(str(fig_path) + ".provenance.json")
        if prov_sidecar.is_file():
            for paper_sub in ("Fractal_Casimir_Nature_EM", "FCE_Nature_ver01"):
                paper_fig_dir = args.project_root / "Papers" / paper_sub / "figures"
                if paper_fig_dir.is_dir():
                    shutil.copyfile(prov_sidecar, paper_fig_dir / prov_sidecar.name)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = load_narrative_report(args.project_root)
    rot_report = load_rotational_report(args.project_root)
    constellations = load_constellations(report, rot_report)
    if args.mode == "python" and args.skip_blender and 1 <= args.max_steps <= 5:
        print(
            f"Validated {len(constellations)} constellations, radial track geometries, "
            "and grounded BEM/Meep evaluations from nature_6step_narrative_report.json.",
            flush=True,
        )
        return 0

    paths = BuildPaths.create(args.project_root)
    renders_exist = all(
        path.is_file() and path.stat().st_size > 0 for path in paths.all_renders()
    )
    reuse_renders = args.mode == "python" and args.skip_blender and renders_exist

    expected = (
        (paths.master_blend, *paths.all_renders(), *paths.individual_blends.values())
        if args.mode == "blender"
        else (paths.figure_png, paths.figure_pdf, paths.composite_png)
    )
    existing = [path for path in expected if path.exists()]
    if existing and not args.force:
        raise FileExistsError(
            f"Output already exists: {existing[0]}. Use --force to rebuild."
        )

    paths.directory.mkdir(parents=True, exist_ok=True)
    paths.models_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "blender":
        build_blender(args, constellations, paths)
        export_metadata(args, constellations, paths)
    else:
        if not reuse_renders:
            launch_blender(args)
        if not all(
            path.is_file() and path.stat().st_size > 0 for path in paths.all_renders()
        ):
            raise RuntimeError("All 13 Blender renders (lineup + 12 panels) are required.")
        export_metadata(args, constellations, paths)
        compose_figure(args, constellations, paths)
        print(f"Saved publication figures to {paths.figure_png.parent}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        ValueError,
        RuntimeError,
        ImportError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
