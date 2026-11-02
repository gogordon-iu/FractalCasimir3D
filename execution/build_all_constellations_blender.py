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
        slug="01_N0_Overhang",
        title="1. N=0 Overhang Control",
        subtitle="SingleTooth_Track0 (z_tip = -55 nm, +45 nm protrusion)",
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
        slug="02_Fractal_N0_SingleTrack",
        title="2. N=0 Deep-Insertion Baseline",
        subtitle="SingleTooth_Track0 (1 track, z_tip = -100 nm flush)",
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
        slug="03_Fractal_N1_FundRing",
        title="3. N=1 Fundamental Cantor Ring",
        subtitle="Fractal_N1_FundRing (1 middle-third slot, w/W = 0.82)",
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
        slug="04_Cantor_N2_FlatZ",
        title="4. N=2 Cantor 3-Track (Flat-Z)",
        subtitle="Cantor_N2_FlatZ / Fractal_N2 (3 Cantor slots, z_tip = -100 nm)",
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
        index=5,
        slug="05_Ctrl_SingleWide",
        title="5. Control A: Single Wide Tooth",
        subtitle="Ctrl_SingleWide (matched total slot & tooth width, 1 track)",
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
        index=6,
        slug="06_Ctrl_UniformPeriodic",
        title="6. Control B: Uniform 3-Track Grating",
        subtitle="Ctrl_UniformPeriodic / Uniform_3Track (3 equal slots & teeth)",
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
        index=7,
        slug="07_Ctrl_SizeMatched_Monotonic",
        title="7. Control C: Size-Matched Monotonic",
        subtitle="Ctrl_SizeMatched_Monotonic (N=2 widths ordered narrow->wide)",
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
        index=8,
        slug="08_Cantor_N2_HybridRZ",
        title="8. N=2 Anisotropic (r, z) Cantor",
        subtitle="Cantor_N2_HybridRZ (Gen-1 z_tip=-100 nm, Gen-2 z_tip=-90 nm)",
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
        slug="09_Rot_C8_Compact_N2",
        title="9. N=2 Compact Footprint Champion",
        subtitle="Rot_C8_Compact_N2 (R in [0.20, 0.90] um, w1/W1 = 0.45)",
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
        slug="10_Fractal_N3_Cantor7Track",
        title="10. N=3 Cantor 7-Track Hierarchy",
        subtitle="Fractal_N3_Cantor7Track (7 tracks, 28 teeth, R in [0.30, 1.65] um)",
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
        index=11,
        slug="11_Cantor_N2_HybridRZ_Monolithic",
        title="11. N=2 Hybrid (r, z) Full-Monolithic",
        subtitle="Cantor_N2_HybridRZ + 4 spider spokes, hub collars & trench slab",
        step_label="Step 6: Monolithic NEMS Validation",
        report_design="Cantor_N2_HybridRZ",
        boundary="Full-Monolithic",
        z_tip_override_um=None,
        h_teeth_override_um=None,
        theta_rep_deg=3.0,
        theta_att_deg=48.0,
        meep_rep_task_id=None,
        meep_att_task_id=None,
        category="monolithic",
    ),
    ConstellationSpec(
        index=12,
        slug="12_Fractal_N3_Cantor7Track_Monolithic",
        title="12. N=3 7-Track Full-Monolithic",
        subtitle="Fractal_N3_Cantor7Track + 4 spider spokes, collars & trench slab",
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


def load_constellations(report: dict[str, Any]) -> tuple[LoadedConstellation, ...]:
    designs = report["designs"]
    tasks = report["tasks"]
    meep_tasks = {
        int(row["task_id"]): row
        for row in report.get("analysis", {}).get("meep_verification", {}).get("tasks", [])
        if isinstance(row, dict) and "task_id" in row
    }

    loaded: list[LoadedConstellation] = []
    for spec in CONSTELLATIONS:
        if spec.report_design not in designs:
            raise ValueError(f"Design {spec.report_design!r} missing from report.")
        raw_design = designs[spec.report_design]
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
        elif spec.report_design == "Cantor_N2_FlatZ":
            alias_names.append("Fractal_N2_Cantor3Track")
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
        if rep_task is None or att_task is None:
            raise ValueError(
                f"Missing Standard BEM task for {spec.slug} "
                f"(found rep={rep_task is not None}, att={att_task is not None})."
            )

        f_rep_bem = required_number(rep_task, "F_z_pN")
        f_att_bem = required_number(att_task, "F_z_pN")
        delta_f_bem = f_rep_bem - f_att_bem

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
            if m_row.get("status") in ("complete", "completed") or (
                m_row.get("source_status") == "complete"
            ):
                f_rep_meep = required_number(m_row, "f_net_pN")

        f_att_meep = None
        if spec.meep_att_task_id is not None and spec.meep_att_task_id in meep_tasks:
            m_row = meep_tasks[spec.meep_att_task_id]
            if m_row.get("status") in ("complete", "completed") or (
                m_row.get("source_status") == "complete"
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
                full_tooth_count=DEFAULT_NUM_SECTORS * len(tracks),
                f_rep_bem_pn=f_rep_bem,
                f_att_bem_pn=f_att_bem,
                delta_f_bem_pn=delta_f_bem,
                rep_task_id=str(rep_task["task_id"]),
                att_task_id=str(att_task["task_id"]),
                f_rep_high_pn=f_rep_high,
                f_rep_ultra_pn=f_rep_ultra,
                f_rep_meep_pn=f_rep_meep,
                f_att_meep_pn=f_att_meep,
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
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"

    world = bpy.data.worlds.new("Constellation Studio World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.08, 0.10, 0.14, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.95

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

    mat_gold = material("Stator Elevated Ribs | Polished Gold", (0.96, 0.77, 0.22), 0.92, 0.17)
    mat_copper = material("Stator Recessed Pads | Copper Gold", (0.76, 0.45, 0.18), 0.88, 0.25)
    mat_bronze = material("Stator Slot Bridges | Rose Bronze", (0.52, 0.31, 0.15), 0.85, 0.30)
    mat_teal_gen1 = material(
        "Sector 0 Gen-1 Rotor Teeth | Emerald Teal", (0.06, 0.92, 0.56), 0.80, 0.16, 0.22
    )
    mat_cyan_gen2 = material(
        "Sector 0 Gen-2 Rotor Teeth | Electric Cyan", (0.08, 0.68, 0.98), 0.80, 0.16, 0.22
    )
    mat_violet_gen3 = material(
        "Sector 0 Gen-3 Rotor Teeth | Vibrant Violet", (0.76, 0.34, 0.98), 0.80, 0.16, 0.24
    )
    mat_overhang = material(
        "Sector 0 Overhang Tooth | Coral Red", (0.98, 0.28, 0.24), 0.78, 0.18, 0.28
    )
    mat_sapphire = material(
        "Sectors 1-3 Rotor Teeth | Platinum Sapphire", (0.34, 0.52, 0.76), 0.88, 0.22
    )
    mat_titanium = material(
        "Monolithic Spider & Hub Collars | Brushed Titanium", (0.74, 0.78, 0.84), 0.90, 0.24
    )
    mat_slate = material(
        "Monolithic Trench Slab | Silicon Slate", (0.22, 0.26, 0.33), 0.65, 0.35
    )
    mat_ref_ring = material(
        "Standard R=1.35um Reference Ring", (0.35, 0.42, 0.54), 0.40, 0.45, 0.15
    )
    mat_pedestal = material(
        "Studio Pedestal Base", (0.11, 0.13, 0.18), 0.30, 0.55
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

        # Reference scale ring at standard R_max = 1.35 um + pedestal disc
        ref_z = item.z_pad_bottom * z_scale - 0.06
        create_annular_mesh(
            f"{item.spec.slug}_ref_ring_1p35um",
            [(1.345, 1.365, 0.0, 360.0, ref_z - 0.012, ref_z)],
            mat_ref_ring,
            collection,
            anchor,
            1.0,
        )
        ped_r = max(1.52, item.R_max + 0.18)
        create_annular_mesh(
            f"{item.spec.slug}_pedestal",
            [(0.04, ped_r, 0.0, 360.0, -0.74, -0.68)],
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
        ("Key studio softbox", (2.2, -3.4, 4.5), 520.0, 3.5),
        ("Fill studio softbox", (-3.0, -1.2, 2.6), 280.0, 3.0),
        ("Rim studio softbox", (1.0, 3.6, 3.2), 600.0, 2.5),
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
    camera_data.lens = 44.0
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
    panel_h = round(args.resolution * 760 / 1200)

    # 1. Render each constellation individually at the origin and save its individual .blend
    for item, col, anchor in built:
        for _, other_col, other_anchor in built:
            is_current = other_col == col
            other_col.hide_render = not is_current
            other_col.hide_viewport = not is_current
            other_anchor.location = (0.0, 0.0, 0.0)

        r_focus = max(1.05, item.R_max)
        if item.spec.boundary == "Full-Monolithic":
            dist = r_focus * 2.55
            camera.location = (dist * 0.92, -dist * 0.96, dist * 0.72)
            aim(camera, (0.0, 0.0, -0.05))
        else:
            dist = r_focus * 2.15
            camera.location = (dist * 0.88, -dist * 0.92, dist * 0.70)
            aim(camera, (0.0, 0.0, -0.12))

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
                "f_rep_bem_pN": item.f_rep_bem_pn,
                "f_att_bem_pN": item.f_att_bem_pn,
                "delta_f_bem_pN": item.delta_f_bem_pn,
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


def draw_rz_profile(ax: Any, item: LoadedConstellation) -> None:
    from matplotlib.patches import Rectangle

    ax.set_facecolor("#0f141d")
    r_limit = 1.72
    ax.set_xlim(0.0, r_limit)
    ax.set_ylim(-290.0, 95.0)

    # Stator landing-pad level dashed line
    pad_top_nm = item.z_pad_top * 1000.0
    pad_bot_nm = item.z_pad_bottom * 1000.0
    ax.axhspan(
        pad_bot_nm,
        pad_top_nm,
        xmin=item.R_min / r_limit,
        xmax=item.R_max / r_limit,
        color="#8a5229",
        alpha=0.28,
    )
    ax.plot(
        [item.R_min, item.R_max],
        [pad_top_nm, pad_top_nm],
        "--",
        color="#d98a4e",
        linewidth=0.9,
    )

    # Elevated stator ribs (gold, z in [-25, 0] nm)
    mem_bot_nm = -item.t_membrane * 1000.0
    for r_in, r_out in item.rib_intervals:
        ax.add_patch(
            Rectangle(
                (r_in, mem_bot_nm),
                r_out - r_in,
                -mem_bot_nm,
                facecolor="#f5c238",
                edgecolor="#ffe380",
                linewidth=0.6,
            )
        )

    # Rotor teeth colored by Cantor generation / overhang status
    is_overhang = item.spec.z_tip_override_um is not None and item.spec.z_tip_override_um > -0.08
    level_colors = {
        1: "#10eb8f",
        2: "#14aeff",
        3: "#c257fa",
    }
    for tr in item.tracks:
        color = "#fa473e" if is_overhang else level_colors.get(tr.level, "#10eb8f")
        z_tip_nm = tr.z_tip * 1000.0
        h_nm = tr.h_teeth * 1000.0
        ax.add_patch(
            Rectangle(
                (tr.r_tooth_in, z_tip_nm),
                tr.r_tooth_out - tr.r_tooth_in,
                h_nm,
                facecolor=color,
                edgecolor="white",
                linewidth=0.55,
            )
        )

    if item.spec.boundary == "Full-Monolithic":
        ax.axhspan(
            48.0,
            82.0,
            xmin=max(0.0, (item.R_min - 0.12) / r_limit),
            xmax=min(1.0, (item.R_max + 0.12) / r_limit),
            color="#b8c4d4",
            alpha=0.85,
        )
        ax.text(
            (item.R_min + item.R_max) / 2.0,
            64.0,
            "Monolithic Spider & Collars (+350..+470 nm) + Trench (-650..-550 nm)",
            color="#0b0f17",
            fontsize=6.3,
            fontweight="bold",
            ha="center",
            va="center",
        )

    ax.axhline(0.0, color="#ffffff", linestyle=":", linewidth=0.6, alpha=0.55)
    ax.set_xlabel("Radius r (µm)", fontsize=7.5, color="#cbd5e1", labelpad=1.5)
    ax.set_ylabel("z (nm)", fontsize=7.5, color="#cbd5e1", labelpad=1.5)
    ax.tick_params(colors="#cbd5e1", labelsize=6.8, length=2.5, pad=1.5)
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")
        spine.set_linewidth(0.6)


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

    paths.figure_png.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(24.0, 26.2), facecolor="#090d14")

    outer = gridspec.GridSpec(
        5,
        4,
        figure=fig,
        height_ratios=[1.28, 1.02, 1.02, 1.02, 0.90],
        hspace=0.28,
        wspace=0.17,
        left=0.035,
        right=0.985,
        top=0.936,
        bottom=0.068,
    )

    short_names = (
        "#1 N=0 Overhang",
        "#2 N=0 Baseline",
        "#3 N=1 Ring",
        "#4 N=2 Flat-Z",
        "#5 Ctrl Wide",
        "#6 Ctrl Uniform",
        "#7 Ctrl Monotonic",
        "#8 N=2 Hybrid(r,z)",
        "#9 C8 Compact",
        "#10 N=3 7-Track",
        "#11 N=2 Monolithic",
        "#12 N=3 Monolithic",
    )

    # Top row: Panoramic 3D Side-by-Side Lineup Render across all 4 columns
    ax_lineup = fig.add_subplot(outer[0, :])
    ax_lineup.imshow(mpimg.imread(paths.lineup_render))
    ax_lineup.set_axis_off()
    ax_lineup.set_title(
        "A  3D Side-by-Side Exhibition Lineup of All 12 Evaluated Constellations "
        "(Exact 1:1 Radial Scale in Blender; Top Row #1–#6, Bottom Row #7–#12)",
        fontsize=12.5,
        fontweight="bold",
        color="#f8fafc",
        loc="left",
        pad=6,
    )
    for idx, label in enumerate(short_names):
        row = idx // 6
        col_idx = idx % 6
        x_frac = 0.095 + col_idx * 0.162
        y_frac = 0.535 if row == 0 else 0.035
        ax_lineup.text(
            x_frac,
            y_frac,
            f"{label}  ({constellations[idx].f_rep_bem_pn:+.2f} pN)",
            transform=ax_lineup.transAxes,
            fontsize=8.2,
            fontweight="bold",
            color="#f8fafc",
            ha="center",
            va="bottom",
            bbox={
                "boxstyle": "round,pad=0.22",
                "facecolor": "#0f172a",
                "edgecolor": "#475569",
                "alpha": 0.85,
            },
        )

    category_border = {
        "hierarchy": "#38bdf8",
        "control": "#f59e0b",
        "fractal_rz": "#10b981",
        "champion": "#a855f7",
        "monolithic": "#e2e8f0",
    }

    # Rows 1..3: 12 Individual Constellations (each cell has 3D render + (r, z) radial profile)
    for idx, item in enumerate(constellations):
        grid_row = 1 + idx // 4
        grid_col = idx % 4
        sub = gridspec.GridSpecFromSubplotSpec(
            2,
            1,
            subplot_spec=outer[grid_row, grid_col],
            height_ratios=[2.35, 1.0],
            hspace=0.06,
        )
        ax_img = fig.add_subplot(sub[0])
        ax_rz = fig.add_subplot(sub[1])

        ax_img.imshow(mpimg.imread(paths.panel_renders[item.spec.slug]))
        ax_img.set_xticks([])
        ax_img.set_yticks([])
        border_col = category_border.get(item.spec.category, "#64748b")
        for spine in ax_img.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor(border_col)
            spine.set_linewidth(1.5)

        ax_img.set_title(
            f"{item.spec.title}  [{item.spec.step_label}]\n"
            f"{item.spec.subtitle}\n"
            f"R ∈ [{item.R_min:.2f}, {item.R_max:.2f}] µm  |  {len(item.tracks)} tracks "
            f"({item.full_tooth_count} teeth)  |  A = {item.footprint_um2:.2f} µm²",
            fontsize=8.0,
            fontweight="bold",
            color="#f1f5f9",
            loc="left",
            pad=3.5,
        )

        # Bottom-left badge inside image: BEM repulsive, attractive, and switching swing
        sign_col = "#10b981" if item.f_rep_bem_pn > 0 else "#ef4444"
        ax_img.text(
            0.02,
            0.055,
            f"F(3°) = {item.f_rep_bem_pn:+.3f} pN | F(48°) = {item.f_att_bem_pn:+.2f} pN | "
            f"ΔF = {item.delta_f_bem_pn:.2f} pN",
            transform=ax_img.transAxes,
            fontsize=7.3,
            fontweight="bold",
            color="#ffffff",
            bbox={
                "boxstyle": "round,pad=0.23",
                "facecolor": sign_col,
                "edgecolor": "white",
                "alpha": 0.88,
            },
        )

        # Top-right badge inside image: High/Ultra BEM and/or Meep 4-pass verification when present
        extra_badges: list[str] = []
        if item.f_rep_ultra_pn is not None:
            extra_badges.append(f"BEM Ultra: {item.f_rep_ultra_pn:+.2f} pN")
        elif item.f_rep_high_pn is not None:
            extra_badges.append(f"BEM High: {item.f_rep_high_pn:+.2f} pN")
        if item.f_rep_meep_pn is not None:
            extra_badges.append(f"Meep 4-pass: {item.f_rep_meep_pn:+.3f} pN")
        if extra_badges:
            ax_img.text(
                0.98,
                0.93,
                " | ".join(extra_badges),
                transform=ax_img.transAxes,
                fontsize=7.2,
                fontweight="bold",
                color="#e2e8f0",
                ha="right",
                va="top",
                bbox={
                    "boxstyle": "round,pad=0.22",
                    "facecolor": "#0f172a",
                    "edgecolor": border_col,
                    "alpha": 0.86,
                },
            )

        draw_rz_profile(ax_rz, item)

    # Bottom row: Side-by-side quantitative comparison charts across all 12 constellations
    bottom_sub = gridspec.GridSpecFromSubplotSpec(
        1, 2, subplot_spec=outer[4, :], width_ratios=[1.12, 1.0], wspace=0.16
    )
    ax_rep = fig.add_subplot(bottom_sub[0])
    ax_swing = fig.add_subplot(bottom_sub[1])

    x_positions = list(range(len(constellations)))
    rep_vals = [c.f_rep_bem_pn for c in constellations]
    bar_colors = [
        "#ef4444" if c.f_rep_bem_pn < 0 else category_border.get(c.spec.category, "#38bdf8")
        for c in constellations
    ]

    ax_rep.set_facecolor("#0f141d")
    bars = ax_rep.bar(x_positions, rep_vals, color=bar_colors, edgecolor="white", linewidth=0.7)
    ax_rep.axhline(0.0, color="#ffffff", linewidth=0.9)
    ax_rep.set_xticks(x_positions)
    ax_rep.set_xticklabels(short_names, rotation=22, ha="right", fontsize=8.3, color="#e2e8f0")
    ax_rep.set_ylabel("Open-Slot Vertical Force F_z(θ = 3°) [pN]", fontsize=9.5, color="#f8fafc")
    ax_rep.set_title(
        "B  Disengaged Open-Slot Repulsion F_z(θ = 3°) Across All 12 Constellations (Standard 3D BEM)",
        fontsize=10.8,
        fontweight="bold",
        color="#f8fafc",
        loc="left",
    )
    ax_rep.tick_params(colors="#cbd5e1", labelsize=8.0)
    ax_rep.grid(axis="y", alpha=0.22, color="#64748b")
    ax_rep.set_ylim(min(rep_vals) - 0.55, max(rep_vals) + 0.65)
    for bar, val in zip(bars, rep_vals):
        y_text = val + 0.08 if val >= 0 else val - 0.24
        ax_rep.text(
            bar.get_x() + bar.get_width() / 2.0,
            y_text,
            f"{val:+.2f}",
            ha="center",
            va="bottom" if val >= 0 else "top",
            fontsize=7.5,
            fontweight="bold",
            color="#f8fafc",
        )
    for spine in ax_rep.spines.values():
        spine.set_edgecolor("#334155")

    swing_vals = [c.delta_f_bem_pn for c in constellations]
    density_vals = [c.delta_f_bem_pn / c.footprint_um2 for c in constellations]
    ax_swing.set_facecolor("#0f141d")
    width = 0.38
    b1 = ax_swing.bar(
        [x - width / 2.0 for x in x_positions],
        swing_vals,
        width=width,
        color="#38bdf8",
        edgecolor="white",
        linewidth=0.6,
        label="Total Switching Swing ΔF_z = F(3°) − F(48°) [pN]",
    )
    b2 = ax_swing.bar(
        [x + width / 2.0 for x in x_positions],
        density_vals,
        width=width,
        color="#10b981",
        edgecolor="white",
        linewidth=0.6,
        label="Footprint-Normalized Swing ΔF_z / A_annulus [pN/µm²]",
    )
    ax_swing.set_xticks(x_positions)
    ax_swing.set_xticklabels(short_names, rotation=22, ha="right", fontsize=8.3, color="#e2e8f0")
    ax_swing.set_ylabel("Force Swing [pN] / Density [pN/µm²]", fontsize=9.5, color="#f8fafc")
    ax_swing.set_title(
        "C  Bipolar Switching Swing ΔF_z & Footprint Efficiency Across All 12 Constellations",
        fontsize=10.8,
        fontweight="bold",
        color="#f8fafc",
        loc="left",
    )
    ax_swing.tick_params(colors="#cbd5e1", labelsize=8.0)
    ax_swing.grid(axis="y", alpha=0.22, color="#64748b")
    ax_swing.legend(fontsize=8.2, facecolor="#1e293b", edgecolor="#475569", labelcolor="#f8fafc")
    ax_swing.set_ylim(0.0, max(swing_vals) + 2.5)
    for bar, val in zip(b1, swing_vals):
        ax_swing.text(
            bar.get_x() + bar.get_width() / 2.0,
            val + 0.25,
            f"{val:.1f}",
            ha="center",
            va="bottom",
            fontsize=6.8,
            color="#bae6fd",
        )
    for bar, val in zip(b2, density_vals):
        ax_swing.text(
            bar.get_x() + bar.get_width() / 2.0,
            val + 0.25,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=6.8,
            color="#a7f3d0",
        )
    for spine in ax_swing.spines.values():
        spine.set_edgecolor("#334155")

    fig.suptitle(
        TITLE,
        fontsize=16.5,
        fontweight="bold",
        color="#f8fafc",
        y=0.972,
    )
    fig.text(
        0.5,
        0.948,
        "Color Key — Gold: Elevated Stator Ribs (z ∈ [−25, 0] nm) | Copper/Bronze: Recessed Landing Pads "
        "(z ∈ [−265, −115] nm) | Sector-0 Rotor Teeth: Emerald (Gen-1), Cyan (Gen-2), Violet (Gen-3), "
        "Coral (Overhang +45 nm) | Sapphire: Sectors 1–3 Teeth | Titanium/Slate: Monolithic Spider & Trench",
        ha="center",
        fontsize=9.5,
        color="#cbd5e1",
    )
    fig.text(
        0.5,
        0.008,
        "Grounded Source: results/nature_6step_narrative_report.json | "
        "Master 3D Scene: results/all_constellations_blender/all_constellations_scene.blend "
        "(+ 12 individual .blend models in results/all_constellations_blender/models/) | "
        f"Active-layer axial display exaggeration ×{args.z_exaggeration:g}",
        ha="center",
        fontsize=8.8,
        color="#94a3b8",
    )

    try:
        fig.savefig(paths.figure_png, dpi=220, facecolor=fig.get_facecolor())
        fig.savefig(paths.figure_pdf, facecolor=fig.get_facecolor())
        shutil.copyfile(paths.figure_png, paths.composite_png)
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
                "constellation_count": len(constellations),
                "display_z_exaggeration": args.z_exaggeration,
            },
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = load_narrative_report(args.project_root)
    constellations = load_constellations(report)
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
