#!/usr/bin/env python3
"""
Build 3D Blender (.blend) models, individual studio renders (.png), and a
19-panel annotated atlas figure for all 19 configurations in the Unified 3D
Conformal-Recursive Polar Cantor Fractal 2^3 Factorial & Matched Controls Study.

All geometry parameters, recursive (r, theta, z) Cantor rules, and matched
7-tooth / 12-tooth control constructors are imported directly from:
    - execution/clutch_geometry_redesign.py
    - execution/multiscale_3d_fractal_architecture.py
with zero hardcoded magic numbers or conditional geometry hacks.
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("python", "blender"), default="python")
    parser.add_argument("--blender", default=DEFAULT_BLENDER_BIN, help="Path to Blender 4.5+ executable")
    parser.add_argument("--max-steps", type=int, default=0, help="Cap on number of configurations (0 = all 19)")
    parser.add_argument("--samples", type=int, default=48, help="Blender Eevee Next render samples")
    parser.add_argument("--resolution", type=int, default=1200, help="Individual render width in pixels")
    parser.add_argument("--angular-segments", type=int, default=256, help="Full-circle angular mesh subdivisions")
    parser.add_argument("--z-exaggeration", type=float, default=2.2, help="Vertical z exaggeration for visual clarity")
    parser.add_argument("--specs-json", default="", help="Path to serialized Blender scene specifications JSON")
    parser.add_argument(
        "--reuse-renders",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse existing individual Blender render PNGs when all expected panels exist",
    )
    args = parser.parse_args(argv)
    if args.max_steps < 0:
        parser.error("--max-steps must be >= 0")
    if args.samples < 1:
        parser.error("--samples must be >= 1")
    if args.resolution < 128:
        parser.error("--resolution must be >= 128")
    if args.angular_segments < 32:
        parser.error("--angular-segments must be >= 32")
    if not (math.isfinite(args.z_exaggeration) and args.z_exaggeration > 0.0):
        parser.error("--z-exaggeration must be finite and > 0")
    return args


def extract_solid_stator_rib_intervals(design: Any) -> tuple[tuple[float, float, bool], ...]:
    """Return tuple of (r_in, r_out, is_internal_subrib) for all solid stator ribs in `design`.
    Distinguishes primary inter-slot ribs from internal Cantor / equal sub-ribs."""
    ribs: list[tuple[float, float, bool]] = []
    cursor_r = float(design.R_min)
    for slot in design.slots:
        subslots = slot.stator_subslots or ((slot.r_inner, slot.r_outer),)
        for idx, (sub_in, sub_out) in enumerate(subslots):
            if sub_in > cursor_r + 1e-12:
                is_internal = idx > 0
                ribs.append((float(cursor_r), float(sub_in), bool(is_internal)))
            cursor_r = float(sub_out)
    if design.R_max > cursor_r + 1e-12:
        ribs.append((float(cursor_r), float(design.R_max), False))
    return tuple(ribs)


def serialize_design_blender_spec(idx_1based: int, des: Any) -> dict[str, Any]:
    """Precompute exact 3D annular patch lists in the host Python environment so Blender's
    embedded Python interpreter requires only standard-library JSON + bpy + mathutils."""
    from execution.clutch_geometry_redesign import (
        DEFAULT_N3_Z_TIPS_BY_GEN_UM,
        DEFAULT_NUM_SECTORS,
        DEFAULT_SECTOR_DEG,
        DEFAULT_Z_TIP_ROTATIONAL_UM,
    )
    from execution.multiscale_3d_fractal_architecture import DEFAULT_DISENGAGED_THETA_DEG
    from execution.run_fractal_advantage_study import tooth_segments

    slug = f"{idx_1based:02d}_{des.code}_{des.name}"
    z_pad_bot = float(des.z_pad_top - des.t_landing_pad)
    rib_intervals = extract_solid_stator_rib_intervals(des)

    primary_ribs: list[list[float]] = []
    internal_subribs: list[list[float]] = []
    pads: list[list[float]] = []
    bridges: list[list[float]] = []

    for sector in range(DEFAULT_NUM_SECTORS):
        base = float(sector * DEFAULT_SECTOR_DEG)
        boundary = float(base + des.aperture_arc_deg)
        pad_end = float(base + DEFAULT_SECTOR_DEG)
        for r_in, r_out, is_internal in rib_intervals:
            patch = [r_in, r_out, base, boundary, float(-des.t_membrane), 0.0]
            if is_internal:
                internal_subribs.append(patch)
            else:
                primary_ribs.append(patch)
            pads.append([r_in, r_out, boundary, pad_end, z_pad_bot, float(des.z_pad_top)])
        for slot in des.slots:
            subslots = slot.stator_subslots or ((slot.r_inner, slot.r_outer),)
            for sub_in, sub_out in subslots:
                bridges.append([float(sub_in), float(sub_out), boundary, pad_end, z_pad_bot, float(des.z_pad_top)])

    z_tiers_by_key: dict[str, float] = {
        "s0_flat": float(DEFAULT_Z_TIP_ROTATIONAL_UM),
        "s0_g1": float(DEFAULT_N3_Z_TIPS_BY_GEN_UM[1]),
        "s0_g2": float(DEFAULT_N3_Z_TIPS_BY_GEN_UM[2]),
        "s0_g3": float(DEFAULT_N3_Z_TIPS_BY_GEN_UM[3]),
    }
    s0_buckets: dict[str, list[list[float]]] = {k: [] for k in z_tiers_by_key}
    s_other: list[list[float]] = []

    for sector in range(DEFAULT_NUM_SECTORS):
        base = float(sector * DEFAULT_SECTOR_DEG)
        for slot in des.slots:
            for st in slot.sub_teeth:
                z_top = float(st.z_tip + st.h_teeth)
                bucket_key = min(z_tiers_by_key, key=lambda k: abs(float(st.z_tip) - z_tiers_by_key[k]))
                for d_phi_deg, arc_deg in st.phi_offsets_deg:
                    for low_deg, high_deg, _, _ in tooth_segments(DEFAULT_DISENGAGED_THETA_DEG + d_phi_deg, arc_deg):
                        patch = [
                            float(st.r_tooth_in),
                            float(st.r_tooth_out),
                            float(base + low_deg),
                            float(base + high_deg),
                            float(st.z_tip),
                            z_top,
                        ]
                        if sector == 0:
                            s0_buckets[bucket_key].append(patch)
                        else:
                            s_other.append(patch)

    return {
        "slug": slug,
        "code": des.code,
        "name": des.name,
        "R_max": float(des.R_max),
        "z_pad_bot": z_pad_bot,
        "full_circle_deg": float(DEFAULT_NUM_SECTORS * DEFAULT_SECTOR_DEG),
        "primary_ribs": primary_ribs,
        "internal_subribs": internal_subribs,
        "pads": pads,
        "bridges": bridges,
        "s0_flat": s0_buckets["s0_flat"],
        "s0_g1": s0_buckets["s0_g1"],
        "s0_g2": s0_buckets["s0_g2"],
        "s0_g3": s0_buckets["s0_g3"],
        "s_other": s_other,
    }


def audit_design_geometry_and_mesh(
    design: Any,
    theta_deg: float | None = None,
) -> dict[str, Any]:
    """Perform a rigorous mathematical and 3D mesh audit on `design` and its BEM surface mesh."""
    import numpy as np
    from execution.clutch_geometry_redesign import (
        DEFAULT_LAB_MIN_CLEARANCE_UM,
        DEFAULT_LAB_MIN_FEATURE_UM,
        DEFAULT_MIN_TOOTH_W_UM,
        DEFAULT_NUM_SECTORS,
    )
    from execution.multiscale_3d_fractal_architecture import (
        DEFAULT_DISENGAGED_THETA_DEG,
        active_area_unified,
        build_unified_sector_mesh,
    )
    from execution.run_fractal_advantage_study import tooth_segments

    if theta_deg is None:
        theta_deg = DEFAULT_DISENGAGED_THETA_DEG

    mesh, panel_slot_ids = build_unified_sector_mesh(design, theta_deg=theta_deg)
    rotor_arr = mesh.sector_arrays("rotor")
    stator_arr = mesh.sector_arrays("stator")

    issues: list[str] = []
    min_radial_clearance_nm = math.inf
    min_tooth_w_nm = math.inf
    min_subrib_w_nm = math.inf
    min_axial_pad_clearance_nm = math.inf
    min_aperture_margin_deg = math.inf
    n_subteeth_sector = 0
    n_lobes_sector = 0

    for slot in design.slots:
        subslots = slot.stator_subslots or ((slot.r_inner, slot.r_outer),)
        for idx in range(len(subslots) - 1):
            rib_w_nm = (subslots[idx + 1][0] - subslots[idx][1]) * 1000.0
            min_subrib_w_nm = min(min_subrib_w_nm, rib_w_nm)
            if rib_w_nm + 1e-6 < DEFAULT_LAB_MIN_FEATURE_UM * 1000.0:
                issues.append(f"Internal stator sub-rib width {rib_w_nm:.2f} nm < 15.0 nm")

        for st_idx, st in enumerate(slot.sub_teeth):
            n_subteeth_sector += 1
            w_nm = (st.r_tooth_out - st.r_tooth_in) * 1000.0
            min_tooth_w_nm = min(min_tooth_w_nm, w_nm)
            if w_nm + 1e-6 < DEFAULT_MIN_TOOTH_W_UM * 1000.0:
                issues.append(f"Sub-tooth width {w_nm:.2f} nm < 20.0 nm")

            if len(subslots) == len(slot.sub_teeth):
                s_in, s_out = subslots[st_idx]
            else:
                s_in, s_out = slot.r_inner, slot.r_outer
            clr_in_nm = (st.r_tooth_in - s_in) * 1000.0
            clr_out_nm = (s_out - st.r_tooth_out) * 1000.0
            min_radial_clearance_nm = min(min_radial_clearance_nm, clr_in_nm, clr_out_nm)
            if (
                clr_in_nm + 1e-6 < DEFAULT_LAB_MIN_CLEARANCE_UM * 1000.0
                or clr_out_nm + 1e-6 < DEFAULT_LAB_MIN_CLEARANCE_UM * 1000.0
            ):
                issues.append(f"Radial clearance ({clr_in_nm:.2f}, {clr_out_nm:.2f}) nm < 15.0 nm")

            ax_clr_nm = (st.z_tip - design.z_pad_top) * 1000.0
            min_axial_pad_clearance_nm = min(min_axial_pad_clearance_nm, ax_clr_nm)
            if ax_clr_nm <= 0.0:
                issues.append(f"Tooth z_tip={st.z_tip:.4f} collides with z_pad_top={design.z_pad_top:.4f}")

            lobe_edges: list[tuple[float, float]] = []
            for d_phi_deg, arc_deg in st.phi_offsets_deg:
                n_lobes_sector += 1
                segs = tooth_segments(theta_deg + d_phi_deg, arc_deg)
                for low_deg, high_deg, _, _ in segs:
                    lobe_edges.append((low_deg, high_deg))
                    margin = min(low_deg - 0.0, design.aperture_arc_deg - high_deg)
                    min_aperture_margin_deg = min(min_aperture_margin_deg, margin)
                    if low_deg < -1e-6 or high_deg > design.aperture_arc_deg + 1e-6:
                        issues.append(
                            f"Lobe [{low_deg:.2f}, {high_deg:.2f}] deg overhangs aperture [0, {design.aperture_arc_deg:.1f}] deg"
                        )
            lobe_edges.sort()
            for l_i in range(len(lobe_edges) - 1):
                if lobe_edges[l_i][1] > lobe_edges[l_i + 1][0] + 1e-6:
                    issues.append(f"Overlapping azimuthal lobes on tooth: {lobe_edges}")

    hz_top_mask = rotor_arr.normals[:, 2] > 0.9
    bem_active_area_um2 = float(DEFAULT_NUM_SECTORS * np.sum(rotor_arr.areas[hz_top_mask]))
    analytic_area_um2 = active_area_unified(design)
    area_diff_um2 = abs(bem_active_area_um2 - analytic_area_um2)
    if area_diff_um2 / max(analytic_area_um2, 1e-12) > 5e-3:
        issues.append(
            f"BEM top-face area {bem_active_area_um2:.6f} deviates >0.5% from analytical area {analytic_area_um2:.6f}"
        )

    expected_rotor_panels = 32 * n_lobes_sector
    if int(rotor_arr.count) != expected_rotor_panels:
        issues.append(f"Rotor panel count {rotor_arr.count} != expected {expected_rotor_panels}")
    if len(panel_slot_ids) != int(rotor_arr.count):
        issues.append("panel_slot_ids length mismatch")

    ribs = extract_solid_stator_rib_intervals(design)
    n_internal_subribs = sum(1 for _, _, is_int in ribs if is_int)

    return {
        "code": design.code,
        "name": design.name,
        "u_r": design.u_r,
        "u_theta": design.u_theta,
        "u_z": design.u_z,
        "family_role": design.family_role,
        "n_primary_slots": len(design.slots),
        "n_stator_subslots_sector": sum(len(s.stator_subslots or ((s.r_inner, s.r_outer),)) for s in design.slots),
        "n_internal_stator_subribs": n_internal_subribs,
        "n_rotor_subteeth_sector": n_subteeth_sector,
        "n_azimuthal_lobes_sector": n_lobes_sector,
        "n_lobes_full_device": DEFAULT_NUM_SECTORS * n_lobes_sector,
        "A_tooth_analytic_um2": round(analytic_area_um2, 6),
        "A_tooth_bem_mesh_um2": round(bem_active_area_um2, 6),
        "area_match_abs_err_um2": round(area_diff_um2, 9),
        "min_tooth_width_nm": round(float(min_tooth_w_nm), 3),
        "min_radial_clearance_nm": round(float(min_radial_clearance_nm), 3),
        "min_internal_subrib_nm": round(float(min_subrib_w_nm), 3) if math.isfinite(min_subrib_w_nm) else None,
        "min_axial_pad_clearance_nm": round(float(min_axial_pad_clearance_nm), 3),
        "min_aperture_margin_deg": round(float(min_aperture_margin_deg), 3),
        "n_rotor_panels_sector": int(rotor_arr.count),
        "n_stator_panels_sector": int(stator_arr.count),
        "audit_status": "PASS" if not issues else "FAIL",
        "issues": issues,
    }


def build_blender_scenes_and_renders(args: argparse.Namespace) -> None:
    """Run inside Blender 4.5+ using only standard-library json/math + bpy/mathutils."""
    bpy: Any = importlib.import_module("bpy")
    mathutils: Any = importlib.import_module("mathutils")

    specs_path = Path(args.specs_json)
    payload = json.loads(specs_path.read_text(encoding="utf-8"))
    out_dir = Path(payload["out_dir"])
    spec_list: Sequence[Mapping[str, Any]] = payload["specs"]

    models_dir = out_dir / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)

    scene = bpy.context.scene
    scene.name = "Unified 3D Fractal & Matched Controls Atlas"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1e-6
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = int(args.samples)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.04

    world = bpy.data.worlds.new("Unified3D Studio World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.95, 0.96, 0.98, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0

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

    mat_primary_rib = make_material("Stator Primary Ribs | Bronze", (0.44, 0.38, 0.33), 0.62, 0.28)
    mat_sub_rib = make_material("Stator Cantor/Equal Sub-Ribs | Bright Copper-Gold", (0.85, 0.42, 0.18), 0.72, 0.22, 0.05)
    mat_pad = make_material("Stator Recessed Pad | Cyan Teal", (0.04, 0.66, 0.80), 0.70, 0.22, 0.04)
    mat_bridge = make_material("Stator Slot Bridges | Deep Teal", (0.04, 0.48, 0.62), 0.68, 0.26, 0.02)
    mat_flat = make_material("Rotor Flat Teeth (z=-100nm) | Pale Champagne Gold", (0.94, 0.82, 0.42), 0.76, 0.22, 0.04)
    mat_gen1 = make_material("Rotor Gen-1 Teeth (z=-90nm) | Bright Gold", (0.98, 0.72, 0.10), 0.80, 0.18, 0.06)
    mat_gen2 = make_material("Rotor Gen-2 Teeth (z=-80nm) | Amber Orange", (0.95, 0.50, 0.06), 0.80, 0.20, 0.05)
    mat_gen3 = make_material("Rotor Gen-3 Teeth (z=-70nm) | Crimson Gold", (0.88, 0.24, 0.12), 0.80, 0.20, 0.05)
    mat_other_sec = make_material("Sectors 1-3 Rotor Teeth | Warm Gold", (0.88, 0.62, 0.16), 0.75, 0.24, 0.03)
    mat_frame = make_material("Outer Stator Frame", (0.74, 0.78, 0.84), 0.30, 0.45)

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

    def build_design_collection(spec: Mapping[str, Any]) -> tuple[str, Any, Any, float]:
        slug = str(spec["slug"])
        collection = bpy.data.collections.new(f"Design_{slug}")
        scene.collection.children.link(collection)

        anchor = bpy.data.objects.new(f"Anchor_{slug}", None)
        anchor.empty_display_type = "PLAIN_AXES"
        anchor.empty_display_size = 0.25
        collection.objects.link(anchor)

        z_scale = float(args.z_exaggeration)
        create_annular_mesh(f"{slug}_stator_primary_ribs", spec["primary_ribs"], mat_primary_rib, collection, anchor, z_scale)
        if spec["internal_subribs"]:
            create_annular_mesh(f"{slug}_stator_subribs", spec["internal_subribs"], mat_sub_rib, collection, anchor, z_scale)
        create_annular_mesh(f"{slug}_stator_pads", spec["pads"], mat_pad, collection, anchor, z_scale)
        create_annular_mesh(f"{slug}_stator_bridges", spec["bridges"], mat_bridge, collection, anchor, z_scale)

        if spec.get("s0_flat"):
            create_annular_mesh(f"{slug}_rotor_s0_flat", spec["s0_flat"], mat_flat, collection, anchor, z_scale)
        if spec["s0_g1"]:
            create_annular_mesh(f"{slug}_rotor_s0_gen1", spec["s0_g1"], mat_gen1, collection, anchor, z_scale)
        if spec["s0_g2"]:
            create_annular_mesh(f"{slug}_rotor_s0_gen2", spec["s0_g2"], mat_gen2, collection, anchor, z_scale)
        if spec["s0_g3"]:
            create_annular_mesh(f"{slug}_rotor_s0_gen3", spec["s0_g3"], mat_gen3, collection, anchor, z_scale)
        if spec["s_other"]:
            create_annular_mesh(f"{slug}_rotor_s123", spec["s_other"], mat_other_sec, collection, anchor, z_scale)

        r_max = float(spec["R_max"])
        z_pad_bot = float(spec["z_pad_bot"])
        full_circle_deg = float(spec["full_circle_deg"])
        create_annular_mesh(
            f"{slug}_outer_frame",
            [[r_max, r_max + 0.06, 0.0, full_circle_deg, z_pad_bot * z_scale, 0.0]],
            mat_frame,
            collection,
            anchor,
            1.0,
        )
        return slug, collection, anchor, r_max

    built = [build_design_collection(spec) for spec in spec_list]

    def aim(obj: Any, target: tuple[float, float, float]) -> None:
        direction = mathutils.Vector(target) - obj.location
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    for name, location, energy, size in (
        ("Key studio softbox", (2.4, -3.6, 4.8), 520.0, 3.8),
        ("Fill studio softbox", (-3.2, -1.4, 2.8), 320.0, 3.2),
        ("Rim studio softbox", (1.2, 3.8, 3.4), 540.0, 2.8),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = size
        light_obj = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light_obj)
        light_obj.location = location
        aim(light_obj, (0.0, 0.0, -0.10))

    camera_data = bpy.data.cameras.new("Studio camera")
    camera = bpy.data.objects.new("Studio camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "PERSP"
    camera_data.lens = 48.0
    camera_data.clip_start = 0.001
    camera_data.clip_end = 250.0

    panel_w = int(args.resolution)
    panel_h = round(panel_w * 740 / 1200)

    for slug, col, anchor, r_max in built:
        for _, other_col, other_anchor, _ in built:
            is_cur = other_col == col
            other_col.hide_render = not is_cur
            other_col.hide_viewport = not is_cur
            other_anchor.location = (0.0, 0.0, 0.0)

        dist = r_max * 2.22
        camera.location = (dist * 0.88, -dist * 0.92, dist * 0.64)
        aim(camera, (0.0, 0.0, -0.08))

        render_path = out_dir / f"render_{slug}.png"
        scene.render.resolution_x = panel_w
        scene.render.resolution_y = panel_h
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True, scene=scene.name)

        blend_path = models_dir / f"{slug}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    # Save master scene with all evaluated models arranged on a 4-column grid
    for idx, (_, col, anchor, _) in enumerate(built):
        col.hide_render = False
        col.hide_viewport = False
        row = idx // 4
        col_idx = idx % 4
        anchor.location = ((col_idx - 1.5) * 3.8, (2.0 - row) * 3.8, 0.0)
    master_blend = out_dir / f"n3_unified_3d_all_{len(spec_list)}_designs.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(master_blend))


def compose_atlas_figure(
    designs: Sequence[Any],
    audits: Sequence[Mapping[str, Any]],
    bem_by_code: Mapping[str, Mapping[str, Any]],
    out_dir: Path,
    out_png: Path,
    out_pdf: Path,
) -> None:
    """Compose a 5x4 annotated visual inspection atlas of all evaluated 3D Blender renders."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    n = len(designs)
    ncols = 4
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(18.0, 3.6 * nrows), dpi=200)
    axes_flat = np.atleast_1d(axes).ravel()

    for idx, (des, aud) in enumerate(zip(designs, audits, strict=True)):
        ax = axes_flat[idx]
        slug = f"{idx + 1:02d}_{des.code}_{des.name}"
        img_path = out_dir / f"render_{slug}.png"
        if img_path.is_file():
            img = plt.imread(str(img_path))
            ax.imshow(img)
        ax.axis("off")

        bem_rec = bem_by_code.get(des.code)
        if bem_rec is not None:
            fz_str = f"Fz(3°) = {float(bem_rec['F_z_pN']):+.3f} pN | F/A = {float(bem_rec['F_per_A_pN_per_um2']):+.1f}"
        else:
            fz_str = "Fz(3°): Pending HPC solve"

        panel_letter = chr(ord("a") + idx)
        code_clean = str(des.code).replace("_", "-")
        name_clean = str(des.name).replace("_", "-")
        title_line = f"({panel_letter}) {code_clean}: {name_clean}"
        sub_line = (
            f"u=({des.u_r},{des.u_theta},{des.u_z}) | "
            f"SubSlots={aud['n_stator_subslots_sector']} (SubRibs={aud['n_internal_stator_subribs']}) | "
            f"Teeth={aud['n_rotor_subteeth_sector']} | Lobes={aud['n_azimuthal_lobes_sector']}/sec\n"
            f"A={aud['A_tooth_analytic_um2']:.4f} um² | {fz_str} | Audit: {aud['audit_status']}"
        )
        ax.set_title(f"{title_line}\n{sub_line}", fontsize=7.6, fontweight="bold", pad=4)

    for idx in range(n, len(axes_flat)):
        axes_flat[idx].axis("off")

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    fig.savefig(out_pdf)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "blender":
        build_blender_scenes_and_renders(args)
        return 0

    from execution.multiscale_3d_fractal_architecture import build_all_study_designs
    from utils.metrics_logger import (
        export_macros,
        log_metric,
        log_step,
        save_plot_provenance,
        set_solver_provenance,
    )

    all_designs = build_all_study_designs()
    is_micro = 0 < args.max_steps < len(all_designs)
    selected = all_designs[: args.max_steps] if is_micro else all_designs

    suffix = "_micro" if is_micro else ""
    out_dir = ROOT / "results" / f"n3_unified_3d_blender{suffix}"
    out_png = ROOT / "figures" / f"fig_n3_unified_3d_blender_atlas{suffix}.png"
    out_pdf = ROOT / "figures" / f"fig_n3_unified_3d_blender_atlas{suffix}.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run mathematical & BEM mesh audit on each selected configuration:
    audits = [audit_design_geometry_and_mesh(d) for d in selected]
    failed = [a for a in audits if a["audit_status"] != "PASS"]
    if failed:
        raise RuntimeError(f"Geometry/mesh audit failed on designs: {failed}")

    expected_renders = [out_dir / f"render_{idx:02d}_{d.code}_{d.name}.png" for idx, d in enumerate(selected, 1)]
    need_blender = not (args.reuse_renders and all(p.is_file() for p in expected_renders))

    if need_blender:
        # 2. Serialize Blender patch specifications for Blender's embedded Python:
        specs_payload = {
            "out_dir": str(out_dir),
            "specs": [serialize_design_blender_spec(idx, d) for idx, d in enumerate(selected, 1)],
        }
        specs_json_path = out_dir / "blender_scene_specs.json"
        with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, encoding="utf-8") as tmp:
            json.dump(specs_payload, tmp, indent=2)
            tmp_specs = Path(tmp.name)
        tmp_specs.replace(specs_json_path)

        # 3. Launch headless Blender 4.5+ to build .blend models and render .png panels:
        blender_exe = shutil.which(args.blender) or (args.blender if Path(args.blender).is_file() else shutil.which("blender"))
        if not blender_exe:
            raise FileNotFoundError(f"Blender executable not found at {args.blender!r}")

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

    # 4. Load empirical BEM results where available and compose the 19-panel atlas:
    bem_json = ROOT / "results" / "n3_unified_3d_fractal_factorial_study.json"
    bem_by_code: dict[str, Mapping[str, Any]] = {}
    if bem_json.is_file():
        data = json.loads(bem_json.read_text(encoding="utf-8"))
        for r in data.get("records", []):
            bem_by_code[str(r["code"])] = r

    compose_atlas_figure(selected, audits, bem_by_code, out_dir, out_png, out_pdf)

    now_iso = datetime.now(timezone.utc).isoformat()
    manifest_payload = {
        "generated_at_utc": now_iso,
        "model": "Unified3DFractal_Blender_Audit",
        "dataset": "n3_unified_3d_fractal_factorial_study",
        "executed_at": now_iso,
        "n_configurations_built": len(selected),
        "all_audits_passed": len(failed) == 0,
        "master_blend": str(out_dir / f"n3_unified_3d_all_{len(selected)}_designs.blend"),
        "atlas_figure_png": str(out_png),
        "atlas_figure_pdf": str(out_pdf),
        "audits": audits,
    }
    manifest_path = out_dir / "n3_unified_3d_blender_manifest.json"
    with tempfile.NamedTemporaryFile("w", dir=out_dir, delete=False, encoding="utf-8") as tmp:
        json.dump(manifest_payload, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(manifest_path)

    if not is_micro:
        set_solver_provenance(
            "blender_audit",
            {
                "benchmark": "n3_unified_3d_blender_audit",
                "n_configurations": len(selected),
                "executed_at": now_iso,
            },
        )
        log_step(
            "n3_unified_3d_blender_audit",
            {"status": "complete", "n_configurations": len(selected)},
            solver_name="blender_audit",
        )
        metrics_to_log = {
            "n3_blender_audit_total_configs": float(len(selected)),
            "n3_blender_audit_passed_configs": float(sum(1 for a in audits if a["audit_status"] == "PASS")),
            "n3_blender_audit_max_area_err_um2": float(max(a["area_match_abs_err_um2"] for a in audits)),
            "n3_blender_audit_min_radial_clearance_nm": float(min(a["min_radial_clearance_nm"] for a in audits)),
            "n3_blender_audit_min_axial_clearance_nm": float(min(a["min_axial_pad_clearance_nm"] for a in audits)),
        }
        for k, v in metrics_to_log.items():
            log_metric(k, v, step_id="n3_unified_3d_blender_audit", solver_name="blender_audit", defer_save=True)
        first_k = next(iter(metrics_to_log))
        log_metric(first_k, metrics_to_log[first_k], step_id="n3_unified_3d_blender_audit", solver_name="blender_audit", defer_save=False)
        export_macros(str(ROOT / "results" / "provenance_metrics.json"), str(ROOT / "results" / "macros_results.tex"))
        save_plot_provenance(str(out_png), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        save_plot_provenance(str(out_pdf), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        for paper_dir in (
            ROOT / "Papers" / "Fractal_Casimir_Nature_EM" / "figures",
            ROOT / "Papers" / "FCE_Nature_ver01" / "figures",
        ):
            if paper_dir.is_dir():
                for src_f in (out_png, out_pdf, out_png.with_suffix(".provenance.json"), out_pdf.with_suffix(".provenance.json")):
                    if src_f.is_file():
                        shutil.copy2(src_f, paper_dir / src_f.name)

    print(
        f"[BLENDER-AUDIT] Built & audited {len(selected)} configurations -> {manifest_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
