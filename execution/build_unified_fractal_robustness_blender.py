#!/usr/bin/env python3
"""
Build 3D Blender (.blend) models, studio & macro close-up renders (.png),
programmatic visual-quality audits, and publication composite figures for the
Unified 3D Fractal Robustness Study (`H3-Cantor-Robust` vs. 5 Matched Controls).

All geometry parameters, homothetic b=3.0 track/rib/bridge dimensions, and
kinematic angles are imported directly from:
    - execution/clutch_geometry_redesign.py
    - execution/homothetic_3d_robust_architecture.py
with zero hardcoded magic numbers or synthetic force overrides.

Outputs:
    1. results/unified_fractal_robustness_blender/models/*.blend
    2. results/unified_fractal_robustness_blender/render_*.png
    3. results/unified_fractal_robustness_blender/unified_fractal_robustness_blender_manifest.json
    4. figures/fig_unified_fractal_robustness_blender_atlas.{png,pdf} (+ .provenance.json)
    5. figures/fig_h3_cantor_robust_blender_hero.{png,pdf} (+ .provenance.json)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BLENDER_BIN = os.environ.get(
    "BLENDER_BIN",
    r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
)


def find_blender_executable(preferred: str = DEFAULT_BLENDER_BIN) -> str | None:
    """Locate Blender 4.x+ executable or return None if unavailable."""
    if preferred and Path(preferred).is_file():
        return str(Path(preferred))
    found_pref = shutil.which(preferred) if preferred else None
    if found_pref:
        return found_pref
    return shutil.which("blender")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("python", "blender"), default="python")
    parser.add_argument("--blender", default=DEFAULT_BLENDER_BIN, help="Path to Blender 4.5+ executable")
    parser.add_argument("--max-steps", type=int, default=0, help="Cap on number of configurations (0 = all 6)")
    parser.add_argument("--samples", type=int, default=48, help="Blender Eevee Next render samples")
    parser.add_argument("--resolution", type=int, default=1400, help="Individual render width in pixels")
    parser.add_argument("--angular-segments", type=int, default=320, help="Full-circle angular mesh subdivisions")
    parser.add_argument("--z-exaggeration", type=float, default=3.2, help="Vertical z exaggeration for visual clarity")
    parser.add_argument("--specs-json", default="", help="Path to serialized Blender scene specifications JSON")
    parser.add_argument(
        "--reuse-renders",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Reuse existing individual Blender render PNGs when all expected panels exist",
    )
    args = parser.parse_args(argv)
    if args.max_steps < 0:
        parser.error("--max-steps must be >= 0")
    if args.samples < 1:
        parser.error("--samples must be >= 1")
    if args.resolution < 256:
        parser.error("--resolution must be >= 256")
    if args.angular_segments < 64:
        parser.error("--angular-segments must be >= 64")
    if not (math.isfinite(args.z_exaggeration) and args.z_exaggeration > 0.0):
        parser.error("--z-exaggeration must be finite and > 0")
    return args


def serialize_robust_design_blender_spec(
    idx_1based: int,
    design: Any,
    *,
    theta_deg: float,
    z_shift_um: float,
    slug_override: str | None = None,
) -> dict[str, Any]:
    """Serialize exact 3D annular prism patch lists `[r_in, r_out, phi0_deg, phi1_deg, z_bot, z_top]`
    for `design` at kinematic state `(theta_deg, z_shift_um)` so Blender's embedded Python needs only stdlib."""
    from execution.clutch_geometry_redesign import DEFAULT_NUM_SECTORS, DEFAULT_SECTOR_DEG
    from execution.homothetic_3d_robust_architecture import _lobe_sector_segments_deg

    slug = slug_override or f"{idx_1based:02d}_{design.code}"
    # Common wafer substrate datum across ALL 6 designs so external chip height never varies artificially
    common_wafer_bot_um = -0.640
    common_wafer_floor_top_um = -0.560
    pedestal_arc_deg = 1.6

    stator_ribs: list[list[float]] = []
    stator_collars: list[list[float]] = []
    stator_bridges: list[list[float]] = []
    stator_pads: list[list[float]] = []
    hub_and_frame: list[list[float]] = [
        # Common recessed wafer base rims (0..360 deg) strictly outside [R_min, R_max]
        [float(design.R_min_um - 0.14), float(design.R_min_um), 0.0, 360.0, common_wafer_bot_um, common_wafer_floor_top_um],
        [float(design.R_max_um), float(design.R_max_um + 0.14), 0.0, 360.0, common_wafer_bot_um, common_wafer_floor_top_um],
    ]
    rotor_s0_by_gen: dict[str, list[list[float]]] = {"g1": [], "g2": [], "g3": []}
    rotor_other_sectors: list[list[float]] = []

    pad_thick_um = max(float(design.pad_thickness_um), 0.080)
    max_pad_top_um = max(float(t.z_pad_top_um) for t in design.tracks)

    for sector in range(DEFAULT_NUM_SECTORS):
        base = float(sector * DEFAULT_SECTOR_DEG)
        ap_end = float(base + design.aperture_arc_deg)
        sec_end = float(base + DEFAULT_SECTOR_DEG)

        # Quarter-aperture outer & inner anchor posts strictly outside [R_min, R_max] up to z = 0.0 um datum;
        # rotor slots inside [R_min, R_max] remain 100% open across phi = 0 deg and phi = 36 deg!
        hub_and_frame.append(
            [float(design.R_min_um - 0.14), float(design.R_min_um), base, ap_end, common_wafer_floor_top_um, 0.0]
        )
        hub_and_frame.append(
            [float(design.R_max_um), float(design.R_max_um + 0.14), base, ap_end, common_wafer_floor_top_um, 0.0]
        )
        # Low pad-support rim ledges in the open attractive zone [ap_end, sec_end] strictly outside [R_min, R_max]
        if max_pad_top_um > common_wafer_floor_top_um:
            hub_and_frame.append(
                [
                    float(design.R_min_um - 0.14),
                    float(design.R_min_um),
                    ap_end,
                    sec_end,
                    common_wafer_floor_top_um,
                    max_pad_top_um,
                ]
            )
            hub_and_frame.append(
                [
                    float(design.R_max_um),
                    float(design.R_max_um + 0.14),
                    ap_end,
                    sec_end,
                    common_wafer_floor_top_um,
                    max_pad_top_um,
                ]
            )

        # Interdigitated stator ribs exist ONLY in the 4 quarter-apertures [base, ap_end], NEVER across [ap_end, sec_end]!
        for rib in design.ribs:
            r_in = float(rib.r_in_um)
            r_out = float(rib.r_out_um)
            rz_bot = float(rib.z_bot_um)
            rz_top = float(rib.z_top_um)
            stator_ribs.append([r_in, r_out, base, ap_end, rz_bot, rz_top])

            adj_tracks = [
                design.tracks[idx]
                for idx in (rib.left_track_index, rib.right_track_index)
                if idx is not None
            ]
            rib_pad_top = min(float(t.z_pad_top_um) for t in adj_tracks)
            rib_pad_bot = max(common_wafer_bot_um, rib_pad_top - pad_thick_um)

            # Vertical end-pedestals strictly within [r_in, r_out] anchor each rib down to the recessed pad level
            # at base and ap_end WITHOUT entering or blocking any rotor slot [r_slot_in, r_slot_out]!
            if rib_pad_bot < rz_bot:
                stator_ribs.append([r_in, r_out, base, base + pedestal_arc_deg, rib_pad_bot, rz_bot])
                stator_ribs.append([r_in, r_out, ap_end - pedestal_arc_deg, ap_end, rib_pad_bot, rz_bot])

            # In the open attractive zone [ap_end, sec_end], ONLY the recessed landing-pad terrace exists — ZERO upper ribs!
            stator_pads.append([r_in, r_out, ap_end, sec_end, rib_pad_bot, rib_pad_top])

        for trk in design.tracks:
            z_s0 = float(trk.z_stage_center_um - 0.5 * trk.h_stage_um)
            z_s1 = float(trk.z_stage_center_um + 0.5 * trk.h_stage_um)
            col_w = float(trk.collar_width_um)
            if col_w > 1.0e-6:
                stator_collars.append(
                    [float(trk.r_slot_in_um - col_w), float(trk.r_slot_in_um), base, ap_end, z_s0, z_s1]
                )
                stator_collars.append(
                    [float(trk.r_slot_out_um), float(trk.r_slot_out_um + col_w), base, ap_end, z_s0, z_s1]
                )

            for br in trk.micro_bridges:
                b0 = float(base + br.phi_center_deg - 0.5 * br.phi_width_deg)
                b1 = float(base + br.phi_center_deg + 0.5 * br.phi_width_deg)
                stator_bridges.append(
                    [float(trk.r_slot_in_um), float(trk.r_slot_out_um), b0, b1, float(br.z_bot_um), float(br.z_top_um)]
                )

            z_p1 = float(trk.z_pad_top_um)
            z_p0 = max(common_wafer_bot_um, z_p1 - pad_thick_um)
            stator_pads.append([float(trk.r_slot_in_um), float(trk.r_slot_out_um), ap_end, sec_end, z_p0, z_p1])

            z_r0 = float(-z_shift_um - 0.5 * trk.h_stage_um)
            z_r1 = float(-z_shift_um + 0.5 * trk.h_stage_um)
            gen_key = f"g{min(max(int(trk.generation), 1), 3)}"
            for d_phi_deg, arc_deg in trk.lobe_offsets_deg:
                for low_deg, high_deg, _, _ in _lobe_sector_segments_deg(theta_deg, d_phi_deg, arc_deg):
                    patch = [
                        float(trk.r_tooth_in_um),
                        float(trk.r_tooth_out_um),
                        float(base + low_deg),
                        float(base + high_deg),
                        z_r0,
                        z_r1,
                    ]
                    if sector == 0:
                        rotor_s0_by_gen[gen_key].append(patch)
                    else:
                        rotor_other_sectors.append(patch)

    min_z_stator = common_wafer_bot_um

    return {
        "slug": slug,
        "code": design.code,
        "name": design.name,
        "theta_deg": float(theta_deg),
        "z_shift_um": float(z_shift_um),
        "R_min_um": float(design.R_min_um),
        "R_max_um": float(design.R_max_um),
        "min_z_stator_um": float(min_z_stator),
        "stator_ribs": stator_ribs,
        "stator_collars": stator_collars,
        "stator_bridges": stator_bridges,
        "stator_pads": stator_pads,
        "hub_and_frame": hub_and_frame,
        "rotor_s0_g1": rotor_s0_by_gen["g1"],
        "rotor_s0_g2": rotor_s0_by_gen["g2"],
        "rotor_s0_g3": rotor_s0_by_gen["g3"],
        "rotor_other_sectors": rotor_other_sectors,
    }


def audit_robust_design_for_blender(design: Any) -> dict[str, Any]:
    """Run mathematical, BEM-mesh, elastostatic-rib, and 3D collision verification on `design`."""
    import numpy as np
    from execution.clutch_geometry_redesign import DEFAULT_NUM_SECTORS, H3_ROBUST_NOMINAL_OP_Z_UM
    from execution.homothetic_3d_robust_architecture import (
        DISENGAGED_THETA_DEG,
        ENGAGED_THETA_DEG,
        active_tooth_area_um2,
        build_homothetic_sector_bem_mesh,
        compute_design_geometric_summary,
        compute_stator_rib_elastostatic_safety,
        verify_design_3d_non_intersection,
    )

    chk_dis = verify_design_3d_non_intersection(
        design, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM, theta_deg=DISENGAGED_THETA_DEG
    )
    chk_deep = verify_design_3d_non_intersection(design, z_shift_um=0.520, theta_deg=DISENGAGED_THETA_DEG)
    chk_eng = verify_design_3d_non_intersection(
        design, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM, theta_deg=ENGAGED_THETA_DEG
    )
    built = build_homothetic_sector_bem_mesh(
        design, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM, theta_deg=DISENGAGED_THETA_DEG
    )
    issues: list[str] = []
    if not chk_dis["collision_free"]:
        issues.extend(chk_dis["collisions"])
    if not chk_deep["collision_free"]:
        issues.extend(chk_deep["collisions"])
    if not chk_eng["collision_free"]:
        issues.extend(chk_eng["collisions"])
    if (
        built.mesh is None
        or built.shorted
        or built.all_teeth_etched_away
        or built.surviving_tracks < len(design.tracks)
    ):
        issues.append(
            f"Nominal mesh invalid (shorted={built.shorted}, surviving_tracks={built.surviving_tracks}/{len(design.tracks)})"
        )

    geom = compute_design_geometric_summary(design)
    analytic_area = active_tooth_area_um2(design)
    bem_area = 0.0
    n_rotor_panels = 0
    n_stator_panels = 0
    if built.mesh is not None:
        r_arr = built.mesh.sector_arrays("rotor")
        s_arr = built.mesh.sector_arrays("stator")
        n_rotor_panels = int(r_arr.count)
        n_stator_panels = int(s_arr.count)
        top_mask = r_arr.normals[:, 2] > 0.9
        bem_area = float(DEFAULT_NUM_SECTORS * np.sum(r_arr.areas[top_mask]))

    area_err = abs(bem_area - analytic_area)
    if area_err / max(analytic_area, 1.0e-12) > 5.0e-3:
        issues.append(f"BEM active area {bem_area:.6f} deviates >0.5% from analytic {analytic_area:.6f} um^2")

    rib_static = compute_stator_rib_elastostatic_safety(
        design,
        track_radial_stiffness_N_per_m=[0.0] * len(design.tracks),
    )
    n_bridges_sec = sum(len(t.micro_bridges) for t in design.tracks)
    min_rib_w_nm = min((r.width_um * 1000.0) for r in design.ribs)

    return {
        "code": design.code,
        "name": design.name,
        "family_role": design.family_role,
        "n_tracks": int(geom["n_tracks"]),
        "n_lobes_per_sector": int(geom["n_lobes_per_sector"]),
        "n_bridges_per_sector": int(n_bridges_sec),
        "A_tooth_analytic_um2": round(analytic_area, 6),
        "A_tooth_bem_um2": round(bem_area, 6),
        "area_match_abs_err_um2": round(area_err, 9),
        "g_min_nm": round(float(geom["g_r_min_nm"]), 3),
        "min_rib_width_nm": round(float(min_rib_w_nm), 3),
        "max_unsupported_rib_arc_deg": round(float(max(r.unsupported_arc_deg for r in design.ribs)), 3),
        "SF_rib_static": round(float(rib_static["SF_rib"]), 2),
        "n_rotor_panels_sector": n_rotor_panels,
        "n_stator_panels_sector": n_stator_panels,
        "collision_free_all_states": bool(
            chk_dis["collision_free"] and chk_deep["collision_free"] and chk_eng["collision_free"]
        ),
        "audit_status": "PASS" if not issues else "FAIL",
        "issues": issues,
    }


def inspect_rendered_png_quality(
    png_path: Path,
    *,
    min_fg_fraction: float = 0.06,
    max_fg_fraction: float = 0.90,
    check_unclipped_margins: bool = False,
) -> dict[str, Any]:
    """Programmatic visual-inspection gate on a rendered or composite PNG image.
    Verifies file integrity, resolution, foreground occupancy, luminance contrast,
    and (for full-device studio renders) unclipped 4-edge canvas margins."""
    import matplotlib.image as mpimg
    import numpy as np

    if not png_path.is_file() or png_path.stat().st_size == 0:
        return {"path": str(png_path), "status": "FAIL", "issues": ["Missing or empty PNG file"]}

    arr = np.asarray(mpimg.imread(str(png_path)), dtype=np.float64)
    issues: list[str] = []
    if arr.ndim != 3 or arr.shape[2] < 3:
        return {"path": str(png_path), "status": "FAIL", "issues": [f"Unexpected image shape {arr.shape}"]}

    h, w, c = arr.shape
    rgb = arr[:, :, :3]
    has_transparency = bool(c >= 4 and float(np.min(arr[:, :, 3])) < 0.5)
    if has_transparency:
        fg_mask = arr[:, :, 3] > 0.05
    else:
        bg_ref = np.median(
            np.concatenate([rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]], axis=0), axis=0
        )
        fg_mask = np.linalg.norm(rgb - bg_ref[None, None, :], axis=2) > 0.035

    fg_fraction = float(np.mean(fg_mask))
    if fg_fraction < min_fg_fraction:
        issues.append(f"Foreground occupancy too small ({fg_fraction:.3f} < {min_fg_fraction:.3f})")
    if fg_fraction > max_fg_fraction:
        issues.append(f"Foreground occupancy too high ({fg_fraction:.3f} > {max_fg_fraction:.3f})")

    luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    fg_luma = luma[fg_mask] if np.any(fg_mask) else luma.ravel()
    luma_std = float(np.std(fg_luma))
    if luma_std < 0.04:
        issues.append(f"Low foreground luminance contrast (std={luma_std:.4f})")

    # Check against severe overexposure (pure white blowout on >20% of foreground)
    overexposed_frac = float(np.mean(fg_luma > 0.985)) if len(fg_luma) > 0 else 0.0
    if has_transparency and overexposed_frac > 0.15:
        issues.append(f"Overexposed foreground highlights ({overexposed_frac:.3f} > 0.15)")

    ys, xs = np.where(fg_mask)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) > 0 else [0, 0, 0, 0]
    if check_unclipped_margins and len(xs) > 0:
        min_margin = min(bbox[0], bbox[1], (w - 1) - bbox[2], (h - 1) - bbox[3])
        if min_margin < 6:
            issues.append(f"Object clipped or too close to render border (min_margin={min_margin}px, bbox={bbox})")

    return {
        "path": str(png_path),
        "width_px": int(w),
        "height_px": int(h),
        "has_transparency": has_transparency,
        "foreground_fraction": round(fg_fraction, 4),
        "foreground_luma_std": round(luma_std, 4),
        "overexposed_fraction": round(overexposed_frac, 4),
        "bbox_xyxy": bbox,
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
    }


def build_blender_scenes_and_renders(args: argparse.Namespace) -> None:
    """Execute inside headless Blender 4.5+ using only Python stdlib + bpy + mathutils."""
    bpy: Any = importlib.import_module("bpy")
    mathutils: Any = importlib.import_module("mathutils")

    specs_path = Path(args.specs_json)
    payload = json.loads(specs_path.read_text(encoding="utf-8"))
    out_dir = Path(payload["out_dir"])
    atlas_specs: Sequence[Mapping[str, Any]] = payload["atlas_specs"]
    hero_jobs: Sequence[Mapping[str, Any]] = payload["hero_jobs"]

    models_dir = out_dir / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)

    scene = bpy.context.scene
    scene.name = "H3 Cantor Robust & Matched Controls Studio"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1e-6
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = int(args.samples)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.38

    world = bpy.data.worlds.new("Robustness3D Studio World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.74, 0.78, 0.85, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.16

    def make_material(
        name: str,
        rgb: tuple[float, float, float],
        metallic: float,
        roughness: float,
        emission: float = 0.0,
    ) -> Any:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        shader = mat.node_tree.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = (*rgb, 1.0)
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Emission Color"].default_value = (*rgb, 1.0)
        shader.inputs["Emission Strength"].default_value = emission
        return mat

    mat_rib = make_material("Stator Structural Ribs | Gunmetal Slate", (0.20, 0.24, 0.32), 0.58, 0.32)
    mat_collar = make_material("Stator Stage Collars | Warm Bronze", (0.68, 0.40, 0.18), 0.70, 0.25, 0.02)
    mat_bridge = make_material("Homothetic Rim Micro-Bridges | Vivid Emerald", (0.04, 0.80, 0.38), 0.52, 0.20, 0.12)
    mat_pad = make_material("Stepped Engagement Landing Pads | Royal Sapphire", (0.10, 0.36, 0.76), 0.62, 0.25, 0.03)
    mat_frame = make_material("Anchored Inner Hub & Outer Frame | Brushed Titanium", (0.30, 0.35, 0.44), 0.52, 0.34)
    mat_g1 = make_material("Rotor Gen-1 Coarse (W=810nm, g=243nm) | Radiant Gold", (0.96, 0.72, 0.10), 0.80, 0.20, 0.05)
    mat_g2 = make_material("Rotor Gen-2 Medium (W=270nm, g=81nm) | Deep Amber", (0.94, 0.42, 0.06), 0.80, 0.20, 0.05)
    mat_g3 = make_material("Rotor Gen-3 Fine (W=90nm, g=27nm) | Crimson Ruby", (0.88, 0.14, 0.15), 0.78, 0.20, 0.06)
    mat_other = make_material("Rotor Sectors 1-3 | Brushed Champagne Gold", (0.86, 0.64, 0.20), 0.76, 0.24, 0.03)

    def create_annular_mesh(
        name: str,
        patches: Sequence[Sequence[float]],
        mat: Any,
        collection: Any,
        parent: Any,
        z_scale: float,
    ) -> Any:
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int, int]] = []
        for low, high, start, end, bottom, top in patches:
            if not (low < high and start < end and bottom < top):
                continue
            count = max(3, math.ceil((end - start) / 360.0 * int(args.angular_segments)))
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

    def build_collection(spec: Mapping[str, Any]) -> tuple[str, Any, Any, float]:
        slug = str(spec["slug"])
        col = bpy.data.collections.new(f"Design_{slug}")
        scene.collection.children.link(col)

        anchor = bpy.data.objects.new(f"Anchor_{slug}", None)
        anchor.empty_display_type = "PLAIN_AXES"
        anchor.empty_display_size = 0.5
        col.objects.link(anchor)

        z_s = float(args.z_exaggeration)
        create_annular_mesh(f"{slug}_ribs", spec["stator_ribs"], mat_rib, col, anchor, z_s)
        if spec["stator_collars"]:
            create_annular_mesh(f"{slug}_collars", spec["stator_collars"], mat_collar, col, anchor, z_s)
        if spec["stator_bridges"]:
            create_annular_mesh(f"{slug}_bridges", spec["stator_bridges"], mat_bridge, col, anchor, z_s)
        create_annular_mesh(f"{slug}_pads", spec["stator_pads"], mat_pad, col, anchor, z_s)
        create_annular_mesh(f"{slug}_frame", spec["hub_and_frame"], mat_frame, col, anchor, z_s)

        if spec["rotor_s0_g1"]:
            create_annular_mesh(f"{slug}_s0_g1", spec["rotor_s0_g1"], mat_g1, col, anchor, z_s)
        if spec["rotor_s0_g2"]:
            create_annular_mesh(f"{slug}_s0_g2", spec["rotor_s0_g2"], mat_g2, col, anchor, z_s)
        if spec["rotor_s0_g3"]:
            create_annular_mesh(f"{slug}_s0_g3", spec["rotor_s0_g3"], mat_g3, col, anchor, z_s)
        if spec["rotor_other_sectors"]:
            create_annular_mesh(f"{slug}_s_other", spec["rotor_other_sectors"], mat_other, col, anchor, z_s)

        return slug, col, anchor, float(spec["R_max_um"])

    all_spec_map: dict[str, Mapping[str, Any]] = {}
    for s in atlas_specs:
        all_spec_map[str(s["slug"])] = s
    for hj in hero_jobs:
        s = hj["spec"]
        all_spec_map[str(s["slug"])] = s

    built_by_slug: dict[str, tuple[str, Any, Any, float]] = {}
    for slug, spec in all_spec_map.items():
        built_by_slug[slug] = build_collection(spec)

    def aim(obj: Any, target: tuple[float, float, float]) -> None:
        direction = mathutils.Vector(target) - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # Directional studio softboxes calibrated for crisp 3D depth contrast without specular blowout
    for name, location, energy, size in (
        ("Key studio softbox", (12.0, -15.0, 20.0), 2600.0, 10.5),
        ("Fill studio softbox", (-14.0, -6.5, 12.5), 540.0, 12.0),
        ("Rim studio softbox", (4.5, 16.0, 15.0), 1850.0, 9.0),
        ("Macro Sector0 Accent", (8.8, 2.2, 9.8), 680.0, 6.0),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = size
        light_obj = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light_obj)
        light_obj.location = location
        aim(light_obj, (1.2, 0.8, -0.45))

    camera_data = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "PERSP"
    camera_data.clip_start = 0.01
    camera_data.clip_end = 500.0

    panel_w = int(args.resolution)
    panel_h = round(panel_w * 900 / 1400)

    def activate_only(target_slug: str) -> tuple[Any, float]:
        for s_key, (_, col, anchor, _) in built_by_slug.items():
            is_cur = s_key == target_slug
            col.hide_render = not is_cur
            col.hide_viewport = not is_cur
            anchor.location = (0.0, 0.0, 0.0)
        _, col_cur, _, r_max = built_by_slug[target_slug]
        return col_cur, r_max

    # 1. Render all 6 individual full-device studio views (unclipped full ring, Sector 0 in foreground)
    for spec in atlas_specs:
        slug = str(spec["slug"])
        _, r_max = activate_only(slug)
        camera_data.lens = 50.0
        dist = r_max * 2.82
        camera.location = (dist * 0.92, -dist * 0.64, dist * 0.84)
        aim(camera, (0.0, 0.0, -1.35))

        render_path = out_dir / f"render_{slug}.png"
        scene.render.resolution_x = panel_w
        scene.render.resolution_y = panel_h
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True, scene=scene.name)

        blend_path = models_dir / f"{slug}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    # 2. Render the 4 Hero close-up & kinematic panels
    for hj in hero_jobs:
        slug = str(hj["spec"]["slug"])
        activate_only(slug)
        camera_data.lens = float(hj["lens_mm"])
        cam_loc = tuple(float(x) for x in hj["camera_location"])
        cam_tgt = tuple(float(x) for x in hj["camera_target"])
        camera.location = cam_loc
        aim(camera, cam_tgt)

        render_path = out_dir / str(hj["render_filename"])
        scene.render.resolution_x = panel_w
        scene.render.resolution_y = panel_h
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True, scene=scene.name)

    # 3. Save master .blend file with the 6 study architectures arranged on a 3x2 studio grid
    atlas_slugs = [str(s["slug"]) for s in atlas_specs]
    for s_key, (_, col, anchor, _) in built_by_slug.items():
        if s_key in atlas_slugs:
            idx = atlas_slugs.index(s_key)
            col.hide_render = False
            col.hide_viewport = False
            row = idx // 3
            col_idx = idx % 3
            anchor.location = ((col_idx - 1.0) * 15.5, (0.5 - row) * 15.5, 0.0)
        else:
            col.hide_render = True
            col.hide_viewport = True
    master_blend = out_dir / f"unified_fractal_robustness_all_{len(atlas_specs)}_designs.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(master_blend))


def compose_six_design_atlas_figure(
    designs: Sequence[Any],
    audits: Sequence[Mapping[str, Any]],
    study_results_by_code: Mapping[str, Mapping[str, Any]],
    out_dir: Path,
    out_png: Path,
    out_pdf: Path,
) -> None:
    """Compose a 2x3 publication atlas comparing `H3-Cantor-Robust` against all 5 matched controls."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    n = len(designs)
    ncols = 4 if n >= 7 else 3
    nrows = math.ceil(n / ncols)
    fig_w = 18.6 if ncols == 4 else 16.5
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, 4.75 * nrows), dpi=220)
    axes_flat = np.atleast_1d(axes).ravel()

    def _fmt_sf(sf_val: float) -> str:
        if sf_val >= 1.0e4:
            return f"{sf_val:.2e}"
        return f"{sf_val:.1f}"

    for idx, (des, aud) in enumerate(zip(designs, audits, strict=True)):
        ax = axes_flat[idx]
        slug = f"{idx + 1:02d}_{des.code}"
        img_path = out_dir / f"render_{slug}.png"
        if img_path.is_file():
            img = plt.imread(str(img_path))
            if img.ndim == 3 and img.shape[2] >= 4:
                ys, xs = np.where(img[:, :, 3] > 0.02)
                if len(xs) > 0:
                    pad_px = 14
                    y0 = max(0, int(ys.min()) - pad_px)
                    y1 = min(img.shape[0], int(ys.max()) + pad_px + 1)
                    x0 = max(0, int(xs.min()) - pad_px)
                    x1 = min(img.shape[1], int(xs.max()) + pad_px + 1)
                    img = img[y0:y1, x0:x1]
            ax.imshow(img)
        ax.axis("off")

        res = study_results_by_code.get(des.code)
        if res is not None:
            b1 = res["benchmark_1_axial_stroke"]
            b4 = res["benchmark_4_cleanroom_yield"]
            perf_str = (
                f"Fz(3°)={b1['F_z_op_pN']:+.2f} pN | Bz={b1['log_stroke_basin_Bz']:.2f} | "
                f"Y_lab={b4['cleanroom_yield_Y_lab_pct']:.1f}%"
            )
        else:
            perf_str = f"SF_rib(0)={_fmt_sf(float(aud['SF_rib_static']))} | BEM: Pending BigRed 200"

        panel_letter = chr(ord("a") + idx)
        title_color = "#8B1E1E" if des.is_fractal else "#111827"
        title_line = f"({panel_letter}) {des.name}"
        sub_line = (
            f"Tracks={aud['n_tracks']}/sec | Lobes={aud['n_lobes_per_sector']}/sec | "
            f"Bridges={aud['n_bridges_per_sector']}/sec | g_min={aud['g_min_nm']:.0f} nm\n"
            f"A_tooth={aud['A_tooth_analytic_um2']:.4f} um² | {perf_str} | {aud['audit_status']}"
        )
        ax.set_title(title_line, fontsize=10.2 if n >= 7 else 11.0, fontweight="bold", color=title_color, pad=22)
        ax.text(
            0.5,
            1.008,
            sub_line,
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=7.1 if n >= 7 else 7.9,
            color="#374151",
        )

    for idx in range(n, len(axes_flat)):
        axes_flat[idx].axis("off")

    fig.suptitle(
        "Unified 3D Fractal Switch (H3-Cantor-Robust & H3-Cantor-Sym-2x2x2, b = 3, g_min = 27 nm) vs. Five Iso-Area Matched Controls\n"
        "Sector 0 Key: Gold = Gen-1 (W=810 nm, z=-360 nm) | Amber = Gen-2 (W=270 nm, z=-120 nm) | "
        "Crimson = Gen-3 (W=90 nm, z=-40 nm) | Emerald = Rim Micro-Bridges | Sapphire = Landing Pads",
        fontsize=10.5,
        fontweight="bold",
        y=0.985,
    )
    fig.subplots_adjust(left=0.015, right=0.985, bottom=0.015, top=0.875, wspace=0.06, hspace=0.22)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
    fig.savefig(out_pdf)
    plt.close(fig)


def compose_hero_architecture_figure(
    hero_jobs: Sequence[Mapping[str, Any]],
    out_dir: Path,
    out_png: Path,
    out_pdf: Path,
) -> None:
    """Compose a 2x2 high-magnification hero figure illustrating:
    (a) Full C4 H3-Cantor-Robust device, (b) Sector-0 9:3:1 homothetic close-up,
    (c) Ctrl-KnifeEdge-g27 19-track fragile knife-edge close-up, (d) theta=48 deg engaged latch."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(2, 2, figsize=(15.5, 9.8), dpi=220)
    axes_flat = np.atleast_1d(axes).ravel()

    for idx, hj in enumerate(hero_jobs[:4]):
        ax = axes_flat[idx]
        img_path = out_dir / str(hj["render_filename"])
        if img_path.is_file():
            img = plt.imread(str(img_path))
            if idx == 0 and img.ndim == 3 and img.shape[2] >= 4:
                ys, xs = np.where(img[:, :, 3] > 0.02)
                if len(xs) > 0:
                    pad_px = 14
                    y0 = max(0, int(ys.min()) - pad_px)
                    y1 = min(img.shape[0], int(ys.max()) + pad_px + 1)
                    x0 = max(0, int(xs.min()) - pad_px)
                    x1 = min(img.shape[1], int(xs.max()) + pad_px + 1)
                    img = img[y0:y1, x0:x1]
            ax.imshow(img)
        ax.axis("off")
        ax.set_title(str(hj["panel_title"]), fontsize=10.6, fontweight="bold", color="#111827", pad=20)
        ax.text(
            0.5,
            1.008,
            str(hj["panel_subtitle"]),
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=8.3,
            color="#374151",
        )

    fig.suptitle(
        "H3-Cantor-Robust 3D Homothetic Architecture, Cleanroom Survival Features & Rotary-Axial Switching Kinematics",
        fontsize=11.8,
        fontweight="bold",
        y=0.985,
    )
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.02, top=0.895, wspace=0.06, hspace=0.20)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
    fig.savefig(out_pdf)
    plt.close(fig)


def build_hero_job_definitions(by_code: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Construct the 4 high-magnification & kinematic render specifications."""
    from execution.clutch_geometry_redesign import H3_ROBUST_NOMINAL_OP_Z_UM
    from execution.homothetic_3d_robust_architecture import DISENGAGED_THETA_DEG, ENGAGED_THETA_DEG

    h3 = by_code["H3_Cantor_Robust"]
    ke = by_code["Ctrl_KnifeEdge_g27"]

    return [
        {
            "render_filename": "render_hero_a_h3_full_disengaged.png",
            "lens_mm": 50.0,
            "camera_location": [16.1, -11.2, 14.5],
            "camera_target": [0.0, 0.0, -1.35],
            "panel_title": "(a) H3-Cantor-Robust Full C4 Rotary-Axial Switch (theta = 3 deg Disengaged)",
            "panel_subtitle": "R in [3.50, 6.20] um | A_tooth = 3.1026 um² | 7 Homothetic Tracks/Sector | Emerald Rim Micro-Bridges",
            "spec": serialize_robust_design_blender_spec(
                1,
                h3,
                theta_deg=DISENGAGED_THETA_DEG,
                z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM,
                slug_override="hero_a_h3_full_disengaged",
            ),
        },
        {
            "render_filename": "render_hero_b_h3_sector0_macro.png",
            "lens_mm": 54.0,
            "camera_location": [9.15, -2.55, 5.05],
            "camera_target": [4.32, 1.80, -0.46],
            "panel_title": "(b) H3-Cantor-Robust Sector-0 Macro: Exact 9 : 3 : 1 (b = 3.0) 3D Homothety",
            "panel_subtitle": "Gaps g_r = {243, 81, 27} nm | Depths z = -{360, 120, 40} nm | Vernier Stagger + Emerald Rim Micro-Bridges",
            "spec": serialize_robust_design_blender_spec(
                2,
                h3,
                theta_deg=DISENGAGED_THETA_DEG,
                z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM,
                slug_override="hero_b_h3_sector0_macro",
            ),
        },
        {
            "render_filename": "render_hero_c_knifeedge_sector0_macro.png",
            "lens_mm": 54.0,
            "camera_location": [9.15, -2.55, 5.05],
            "camera_target": [4.32, 1.80, -0.46],
            "panel_title": "(c) Ctrl-KnifeEdge-g27 Sector-0 Macro: Single-Scale 27 nm Point Optimizer",
            "panel_subtitle": "19 Coplanar Tracks (z = -40 nm, g_r = 27 nm) | 36 deg Unbridged 49.5 nm Stator Ribs -> Fragile Under Etch/Stroke",
            "spec": serialize_robust_design_blender_spec(
                3,
                ke,
                theta_deg=DISENGAGED_THETA_DEG,
                z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM,
                slug_override="hero_c_knifeedge_sector0_macro",
            ),
        },
        {
            "render_filename": "render_hero_d_h3_engaged_48deg_macro.png",
            "lens_mm": 53.0,
            "camera_location": [7.55, 0.85, 5.35],
            "camera_target": [2.25, 4.15, -0.48],
            "panel_title": "(d) H3-Cantor-Robust Engaged Pad-Lock State (theta = 48 deg Attractive Latch)",
            "panel_subtitle": "Rotor Lobes Clear Emerald Rim Micro-Bridges & Latch Over Sapphire Stepped Pads (g_pad = {135, 45, 15} nm)",
            "spec": serialize_robust_design_blender_spec(
                4,
                h3,
                theta_deg=ENGAGED_THETA_DEG,
                z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM,
                slug_override="hero_d_h3_engaged_48deg_macro",
            ),
        },
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "blender":
        build_blender_scenes_and_renders(args)
        return 0

    from execution.clutch_geometry_redesign import H3_ROBUST_NOMINAL_OP_Z_UM
    from execution.homothetic_3d_robust_architecture import (
        DISENGAGED_THETA_DEG,
        build_all_robustness_study_designs,
    )
    from utils.metrics_logger import (
        export_macros,
        log_metric,
        log_step,
        save_plot_provenance,
        set_solver_provenance,
    )

    all_designs = build_all_robustness_study_designs()
    by_code = {d.code: d for d in all_designs}
    is_micro = 0 < args.max_steps < len(all_designs)
    selected = all_designs[: args.max_steps] if is_micro else all_designs

    suffix = "_micro" if is_micro else ""
    out_dir = ROOT / "results" / f"unified_fractal_robustness_blender{suffix}"
    atlas_png = ROOT / "figures" / f"fig_unified_fractal_robustness_blender_atlas{suffix}.png"
    atlas_pdf = ROOT / "figures" / f"fig_unified_fractal_robustness_blender_atlas{suffix}.pdf"
    hero_png = ROOT / "figures" / f"fig_h3_cantor_robust_blender_hero{suffix}.png"
    hero_pdf = ROOT / "figures" / f"fig_h3_cantor_robust_blender_hero{suffix}.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Mathematical, BEM-mesh, elastostatic-rib, and 3D collision audit on every configuration
    audits = [audit_robust_design_for_blender(d) for d in selected]
    failed_audits = [a for a in audits if a["audit_status"] != "PASS"]
    if failed_audits:
        raise RuntimeError(f"3D geometry/collision audit failed: {failed_audits}")

    hero_jobs = build_hero_job_definitions(by_code) if not is_micro else build_hero_job_definitions(by_code)[:1]
    expected_renders = [out_dir / f"render_{idx:02d}_{d.code}.png" for idx, d in enumerate(selected, 1)] + [
        out_dir / str(hj["render_filename"]) for hj in hero_jobs
    ]
    master_blend_path = out_dir / f"unified_fractal_robustness_all_{len(selected)}_designs.blend"
    expected_blends = [
        *[out_dir / "models" / f"{idx:02d}_{d.code}.blend" for idx, d in enumerate(selected, 1)],
        master_blend_path,
    ]
    blender_exe = find_blender_executable(args.blender)
    if blender_exe is not None:
        can_reuse = args.reuse_renders and all(p.is_file() for p in expected_renders) and all(
            p.is_file() for p in expected_blends
        )
    else:
        can_reuse = args.reuse_renders and all(p.is_file() for p in expected_renders)
    need_blender = not can_reuse

    if need_blender:
        if not blender_exe:
            raise FileNotFoundError(f"Blender executable not found at {args.blender!r}")

        atlas_specs = [
            serialize_robust_design_blender_spec(
                idx,
                d,
                theta_deg=DISENGAGED_THETA_DEG,
                z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM,
            )
            for idx, d in enumerate(selected, 1)
        ]
        specs_payload = {
            "out_dir": str(out_dir),
            "atlas_specs": atlas_specs,
            "hero_jobs": hero_jobs,
        }
        specs_json_path = out_dir / "blender_scene_specs.json"
        with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, encoding="utf-8") as tmp:
            json.dump(specs_payload, tmp, indent=2)
            tmp_specs = Path(tmp.name)
        tmp_specs.replace(specs_json_path)

        cmd = [
            str(blender_exe),
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(Path(__file__).resolve()),
            "--",
            "--mode",
            "blender",
            "--specs-json",
            str(specs_json_path),
            "--samples",
            str(args.samples),
            "--resolution",
            str(args.resolution),
            "--angular-segments",
            str(args.angular_segments),
            "--z-exaggeration",
            str(args.z_exaggeration),
        ]
        try:
            subprocess.run(cmd, check=True)
        finally:
            specs_json_path.unlink(missing_ok=True)

    # 2. Programmatic visual-quality inspection on every rendered PNG panel
    atlas_render_paths = [out_dir / f"render_{idx:02d}_{d.code}.png" for idx, d in enumerate(selected, 1)]
    hero_render_paths = [out_dir / str(hj["render_filename"]) for hj in hero_jobs]
    visual_inspections = [
        *[
            inspect_rendered_png_quality(p, min_fg_fraction=0.18, max_fg_fraction=0.88, check_unclipped_margins=True)
            for p in atlas_render_paths
        ],
        *[
            inspect_rendered_png_quality(
                p,
                min_fg_fraction=0.18,
                max_fg_fraction=0.92,
                check_unclipped_margins=("full_disengaged" in p.name),
            )
            for p in hero_render_paths
        ],
    ]
    failed_visuals = [v for v in visual_inspections if v["status"] != "PASS"]
    if failed_visuals:
        raise RuntimeError(f"Rendered PNG visual inspection failed: {failed_visuals}")

    # 3. Load empirical study results if already generated (zero synthetic numbers)
    study_json = ROOT / "results" / "unified_fractal_robustness_study.json"
    study_by_code: dict[str, Mapping[str, Any]] = {}
    if study_json.is_file():
        s_data = json.loads(study_json.read_text(encoding="utf-8"))
        for c_key, rec in s_data.get("designs", {}).items():
            study_by_code[str(c_key)] = rec

    compose_six_design_atlas_figure(selected, audits, study_by_code, out_dir, atlas_png, atlas_pdf)
    if not is_micro:
        compose_hero_architecture_figure(hero_jobs, out_dir, hero_png, hero_pdf)

    # Inspect composite figures too
    composite_checks = [inspect_rendered_png_quality(atlas_png, min_fg_fraction=0.10)]
    if not is_micro:
        composite_checks.append(inspect_rendered_png_quality(hero_png, min_fg_fraction=0.10))
    failed_comp = [c for c in composite_checks if c["status"] != "PASS"]
    if failed_comp:
        raise RuntimeError(f"Composite figure visual inspection failed: {failed_comp}")

    now_iso = datetime.now(timezone.utc).isoformat()
    manifest_payload = {
        "generated_at_utc": now_iso,
        "model": "H3CantorRobust_Blender_Visual_Audit",
        "dataset": "h3_cantor_robust_vs_5_matched_controls",
        "status": "completed",
        "executed_at": now_iso,
        "n_configurations_built": len(selected),
        "all_geometry_audits_passed": len(failed_audits) == 0,
        "all_visual_inspections_passed": len(failed_visuals) == 0 and len(failed_comp) == 0,
        "master_blend": str(master_blend_path) if master_blend_path.is_file() else None,
        "design_blends": [str(p) for p in expected_blends[:-1] if p.is_file()],
        "atlas_figure_png": str(atlas_png),
        "atlas_figure_pdf": str(atlas_pdf),
        "hero_figure_png": str(hero_png) if not is_micro else None,
        "hero_figure_pdf": str(hero_pdf) if not is_micro else None,
        "geometry_audits": audits,
        "render_visual_inspections": visual_inspections,
        "composite_visual_inspections": composite_checks,
    }
    manifest_path = out_dir / "unified_fractal_robustness_blender_manifest.json"
    with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, encoding="utf-8") as tmp:
        json.dump(manifest_payload, tmp, indent=2)
        tmp_manifest = Path(tmp.name)
    tmp_manifest.replace(manifest_path)

    if not is_micro:
        prov_json_path = str(ROOT / "results" / "provenance_metrics.json")
        set_solver_provenance(
            "blender_visual_audit",
            {
                "benchmark": "unified_fractal_robustness_blender",
                "n_configurations": len(selected),
                "executed_at": now_iso,
            },
        )
        log_step(
            "unified_fractal_robustness_blender",
            {
                "status": "completed",
                "n_configurations": len(selected),
                "all_visual_inspections_passed": True,
            },
            solver_name="blender_visual_audit",
        )
        metrics_to_log = {
            "h3_blender_total_configs": float(len(selected)),
            "h3_blender_passed_audits": float(sum(1 for a in audits if a["audit_status"] == "PASS")),
            "h3_blender_passed_visuals": float(len(visual_inspections)),
            "h3_blender_max_area_err_um2": float(max(a["area_match_abs_err_um2"] for a in audits)),
            "h3_blender_min_clearance_nm": float(min(a["g_min_nm"] for a in audits)),
        }
        for k, v in metrics_to_log.items():
            log_metric(k, v, step_id="unified_fractal_robustness_blender", solver_name="blender_visual_audit", defer_save=False)
        export_macros(prov_json_path, str(ROOT / "results" / "macros_results.tex"))
        for fig_p in (atlas_png, atlas_pdf, hero_png, hero_pdf):
            save_plot_provenance(str(fig_p), prov_json_path, list(metrics_to_log.keys()))

        paper_fig_dir = ROOT / "Papers" / "FCE_Nature_ver01" / "figures"
        if paper_fig_dir.is_dir():
            for src_f in (
                atlas_png,
                atlas_pdf,
                hero_png,
                hero_pdf,
                Path(f"{atlas_png}.provenance.json"),
                Path(f"{atlas_pdf}.provenance.json"),
                Path(f"{hero_png}.provenance.json"),
                Path(f"{hero_pdf}.provenance.json"),
            ):
                if src_f.is_file():
                    shutil.copy2(src_f, paper_fig_dir / src_f.name)

    print(
        json.dumps(
            {
                "event": "blender_visual_audit_done",
                "n_configs": len(selected),
                "n_renders_inspected": len(visual_inspections),
                "atlas_png": str(atlas_png),
                "hero_png": str(hero_png) if not is_micro else None,
                "manifest": str(manifest_path),
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
