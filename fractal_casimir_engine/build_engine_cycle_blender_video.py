#!/usr/bin/env python3
"""Build 3D Blender animation video (.mp4) and keyframe composite for the Fractal Casimir Engine.

Architecture (honoring BUG-261107-01):
  - ``--mode python`` (host Python): Reads empirical BEM data from
    ``fractal_casimir_engine/results/engine_cycle_report.json``, exports a pure-JSON
    scene bundle (zero torch/scipy required inside Blender), invokes Blender 4.5 in
    background mode to render 3D frames with dynamic F_z and tau_theta 3D force/torque
    vectors, composites synchronized live (E_C, F_z, tau_theta) telemetry HUD panels,
    encodes ``fractal_casimir_engine_cycle.mp4`` via ffmpeg, and emits provenance sidecars.
  - ``--mode blender`` (Blender embedded Python): Uses ONLY ``bpy``, ``mathutils``, and
    Python stdlib (``json``, ``math``, ``pathlib``).
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("python", "blender"), default="python")
    parser.add_argument("--design", default="Config_D_DualStator_PushPull")
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "fractal_casimir_engine" / "results" / "engine_cycle_report.json",
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        default=PROJECT_ROOT
        / "fractal_casimir_engine"
        / "results"
        / "blender_video"
        / "scene_bundle.json",
    )
    parser.add_argument(
        "--blender",
        default=os.environ.get(
            "BLENDER_BIN",
            r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
        ),
    )
    parser.add_argument("--frames", type=int, default=72, help="Total animation frames per 90-deg cycle.")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--z-exaggeration", type=float, default=3.2)
    parser.add_argument("--skip-blender", action="store_true")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Positive integer runs a fast 2-frame verification probe.",
    )
    return parser.parse_args(argv)


# ==============================================================================
# BLENDER EMBEDDED PYTHON MODE (stdlib + bpy + mathutils ONLY — no torch/scipy!)
# ==============================================================================
def run_blender_mode(args: argparse.Namespace) -> int:
    import bpy  # type: ignore[import-not-found]
    import mathutils  # type: ignore[import-not-found]

    with args.bundle.open("r", encoding="utf-8") as handle:
        bundle = json.load(handle)

    out_dir = Path(bundle["raw_frames_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    z_exag = float(bundle["z_exaggeration"])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # Configure fast, crisp raytraced / EEVEE-Next or Cycles render
    available_engines = {
        item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items
    }
    if "CYCLES" in available_engines:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(bundle["samples"])
        scene.cycles.use_denoising = True
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.get_devices()
            for dev_type in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
                try:
                    prefs.compute_device_type = dev_type
                    for d in prefs.devices:
                        d.use = True
                    scene.cycles.device = "GPU"
                    break
                except Exception:
                    continue
        except Exception:
            scene.cycles.device = "CPU"
    elif "BLENDER_EEVEE_NEXT" in available_engines:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    else:
        scene.render.engine = "BLENDER_EEVEE"

    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    # Dark studio world background
    world = bpy.data.worlds.new("EngineWorld")
    scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node is not None:
        bg_node.inputs[0].default_value = (0.018, 0.022, 0.035, 1.0)
        bg_node.inputs[1].default_value = 0.9

    def make_metallic_material(
        name: str, rgba: tuple[float, float, float, float], roughness: float = 0.22, emission: float = 0.0
    ) -> Any:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Metallic"].default_value = 0.92 if emission == 0.0 else 0.15
            bsdf.inputs["Roughness"].default_value = roughness
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = rgba
                bsdf.inputs["Emission Strength"].default_value = emission
        return mat

    mat_rotor_gold = make_metallic_material("RotorGold", (1.00, 0.78, 0.22, 1.0), roughness=0.18)
    mat_stator_rep = make_metallic_material("StatorRepulsive", (0.28, 0.68, 0.95, 1.0), roughness=0.26)
    mat_stator_attr = make_metallic_material("StatorAttractive", (0.88, 0.42, 0.24, 1.0), roughness=0.28)
    mat_substrate = make_metallic_material("SOISubstrate", (0.07, 0.09, 0.13, 1.0), roughness=0.45)
    mat_fz_arrow = make_metallic_material("FzArrowMat", (0.10, 0.92, 1.00, 1.0), roughness=0.15, emission=2.6)
    mat_tau_arrow = make_metallic_material("TauArrowMat", (0.15, 0.98, 0.48, 1.0), roughness=0.15, emission=2.6)

    def prism_point_xyz(p: dict[str, Any], u: float, v: float, w: float, sector_deg: float) -> tuple[float, float, float]:
        r0 = (1.0 - v) * p["r0_v0"] + v * p["r0_v1"]
        r1 = (1.0 - v) * p["r1_v0"] + v * p["r1_v1"]
        r = (1.0 - u) * r0 + u * r1
        phi0 = (1.0 - w) * p["phi0_w0_deg"] + w * p["phi0_w1_deg"]
        phi1 = (1.0 - w) * p["phi1_w0_deg"] + w * p["phi1_w1_deg"]
        phi_rad = math.radians((1.0 - v) * phi0 + v * phi1 + sector_deg)
        z0 = (1.0 - v) * p["z0_v0"] + v * p["z0_v1"]
        z1 = (1.0 - v) * p["z1_v0"] + v * p["z1_v1"]
        z = ((1.0 - w) * z0 + w * z1) * z_exag
        return (r * math.cos(phi_rad), r * math.sin(phi_rad), z)

    def add_prism_mesh(
        name: str, p: dict[str, Any], sector_deg: float, material: Any, parent_obj: Any = None, nu: int = 3, nv: int = 12, nw: int = 3
    ) -> Any:
        verts: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int, int]] = []

        def idx(i: int, j: int, k: int) -> int:
            return (i * (nv + 1) + j) * (nw + 1) + k

        for i in range(nu + 1):
            u = i / nu
            for j in range(nv + 1):
                v = j / nv
                for k in range(nw + 1):
                    w = k / nw
                    verts.append(prism_point_xyz(p, u, v, w, sector_deg))

        for i in range(nu):
            for j in range(nv):
                faces.append((idx(i, j, 0), idx(i, j + 1, 0), idx(i + 1, j + 1, 0), idx(i + 1, j, 0)))
                faces.append((idx(i, j, nw), idx(i + 1, j, nw), idx(i + 1, j + 1, nw), idx(i, j + 1, nw)))
        for j in range(nv):
            for k in range(nw):
                faces.append((idx(0, j, k), idx(0, j, k + 1), idx(0, j + 1, k + 1), idx(0, j + 1, k)))
                faces.append((idx(nu, j, k), idx(nu, j + 1, k), idx(nu, j + 1, k + 1), idx(nu, j, k + 1)))
        for i in range(nu):
            for k in range(nw):
                faces.append((idx(i, 0, k), idx(i + 1, 0, k), idx(i + 1, 0, k + 1), idx(i, 0, k + 1)))
                faces.append((idx(i, nv, k), idx(i, nv, k + 1), idx(i + 1, nv, k + 1), idx(i + 1, nv, k)))

        mesh_data = bpy.data.meshes.new(name + "_mesh")
        mesh_data.from_pydata(verts, [], faces)
        mesh_data.update()
        obj = bpy.data.objects.new(name, mesh_data)
        obj.data.materials.append(material)
        scene.collection.objects.link(obj)
        if parent_obj is not None:
            obj.parent = parent_obj
        return obj

    # Base SOI wafer disk
    bpy.ops.mesh.primitive_cylinder_add(radius=1.28, depth=0.12, vertices=96, location=(0.0, 0.0, -0.28 * z_exag))
    wafer = bpy.context.active_object
    wafer.name = "SOI_Wafer_Base"
    wafer.data.materials.append(mat_substrate)

    # Build all 4 stator sectors
    for s_idx in range(4):
        s_deg = 90.0 * s_idx
        for p_idx, p in enumerate(bundle["stator_sector0"]):
            role = p["role"]
            is_rep = ("rep" in role) or ("slot" in role) or ("up_collar" in role)
            mat = mat_stator_rep if is_rep else mat_stator_attr
            add_prism_mesh(f"Stator_S{s_idx}_{p_idx}_{role}", p, s_deg, mat)

    # Parent Empty for rigid rotor motion (z translation + theta rotation)
    rotor_root = bpy.data.objects.new("RotorRoot", None)
    scene.collection.objects.link(rotor_root)

    z_ref_um = float(bundle["rotor_ref_z_tip_um"])
    h_teeth_um = float(bundle["h_teeth_um"])
    for s_idx in range(4):
        s_deg = 90.0 * s_idx
        for p_idx, p in enumerate(bundle["rotor_ref_theta0"]):
            add_prism_mesh(f"RotorTooth_S{s_idx}_{p_idx}", p, s_deg, mat_rotor_gold, parent_obj=rotor_root, nv=8)

        # Lightweight radial spider spoke connecting the 3 Cantor rotor tracks above the teeth
        spoke_prism = {
            "r0_v0": 0.16,
            "r1_v0": 1.00,
            "r0_v1": 0.16,
            "r1_v1": 1.00,
            "phi0_w0_deg": -2.2,
            "phi1_w0_deg": 2.2,
            "phi0_w1_deg": -2.2,
            "phi1_w1_deg": 2.2,
            "z0_v0": z_ref_um + h_teeth_um,
            "z1_v0": z_ref_um + h_teeth_um + 0.022,
            "z0_v1": z_ref_um + h_teeth_um,
            "z1_v1": z_ref_um + h_teeth_um + 0.022,
        }
        add_prism_mesh(f"RotorSpoke_S{s_idx}", spoke_prism, s_deg, mat_rotor_gold, parent_obj=rotor_root, nu=4, nv=3, nw=2)

    # Central rotor hub ring attached to RotorRoot
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.18,
        depth=0.08 * z_exag,
        vertices=64,
        location=(0.0, 0.0, (z_ref_um + h_teeth_um + 0.01) * z_exag),
    )
    hub = bpy.context.active_object
    hub.name = "RotorHub"
    hub.data.materials.append(mat_rotor_gold)
    hub.parent = rotor_root

    def make_arrow_object(name: str, mat: Any) -> Any:
        root = bpy.data.objects.new(name, None)
        scene.collection.objects.link(root)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.024, depth=0.22, vertices=24, location=(0.0, 0.0, 0.11))
        shaft = bpy.context.active_object
        shaft.data.materials.append(mat)
        shaft.parent = root
        bpy.ops.mesh.primitive_cone_add(radius1=0.058, radius2=0.0, depth=0.11, vertices=24, location=(0.0, 0.0, 0.275))
        head = bpy.context.active_object
        head.data.materials.append(mat)
        head.parent = root
        return root

    fz_arrow = make_arrow_object("AxialForceArrow", mat_fz_arrow)
    tau_arrows = [make_arrow_object(f"TorqueArrow_{k}", mat_tau_arrow) for k in range(4)]

    # Three-point studio lighting + isometric-elevated camera
    def add_area_light(name: str, loc: tuple[float, float, float], energy: float, color: tuple[float, float, float]) -> None:
        light_data = bpy.data.lights.new(name=name, type="AREA")
        light_data.energy = energy
        light_data.size = 2.8
        light_data.color = color
        light_obj = bpy.data.objects.new(name=name, object_data=light_data)
        light_obj.location = loc
        direction = mathutils.Vector((0.0, 0.0, 0.0)) - mathutils.Vector(loc)
        light_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(light_obj)

    add_area_light("KeyLight", (2.6, -2.4, 2.9), 420.0, (1.0, 0.97, 0.92))
    add_area_light("FillLight", (-2.8, -1.6, 2.0), 230.0, (0.75, 0.88, 1.0))
    add_area_light("RimLight", (0.2, 3.0, 2.2), 260.0, (1.0, 0.85, 0.68))

    cam_data = bpy.data.cameras.new("EngineCam")
    cam_data.lens = 42.0
    cam_obj = bpy.data.objects.new("EngineCam", cam_data)
    cam_obj.location = (2.32, -2.42, 1.86)
    look_vec = mathutils.Vector((0.0, 0.0, 0.04)) - cam_obj.location
    cam_obj.rotation_euler = look_vec.to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    fz_bsdf = mat_fz_arrow.node_tree.nodes.get("Principled BSDF")
    tau_bsdf = mat_tau_arrow.node_tree.nodes.get("Principled BSDF")
    fz_max = max(float(bundle["max_abs_fz_pN"]), 0.05)
    tau_max = max(float(bundle["max_abs_tau_pN_um"]), 0.01)

    for frame_info in bundle["frames"]:
        f_idx = int(frame_info["frame_index"])
        th_deg = float(frame_info["theta_deg"])
        z_tip = float(frame_info["z_tip_um"])
        fz = float(frame_info["f_z_pN"])
        tau = float(frame_info["tau_theta_pN_um"])

        dz_vis = (z_tip - z_ref_um) * z_exag
        rotor_root.location = (0.0, 0.0, dz_vis)
        rotor_root.rotation_euler = (0.0, 0.0, math.radians(th_deg))

        # Update dynamic 3D Axial Force arrow clearly above rotor hub
        fz_mag = min(1.35, max(0.24, 1.15 * abs(fz) / fz_max))
        z_arrow_base = (0.48 if fz >= 0.0 else 0.86) + dz_vis
        fz_arrow.location = (0.0, 0.0, z_arrow_base)
        fz_arrow.rotation_euler = (0.0 if fz >= 0.0 else math.pi, 0.0, 0.0)
        fz_arrow.scale = (1.15, 1.15, fz_mag)
        fz_col = (0.08, 0.92, 1.00, 1.0) if fz >= 0.0 else (1.00, 0.30, 0.22, 1.0)
        if fz_bsdf is not None:
            fz_bsdf.inputs["Base Color"].default_value = fz_col
            if "Emission Color" in fz_bsdf.inputs:
                fz_bsdf.inputs["Emission Color"].default_value = fz_col

        # Update 4 tangential Torque arrows around outer rotor perimeter
        tau_mag = min(1.35, max(0.18, 1.15 * abs(tau) / tau_max))
        tau_col = (0.15, 0.98, 0.48, 1.0) if tau >= 0.0 else (0.98, 0.22, 0.72, 1.0)
        if tau_bsdf is not None:
            tau_bsdf.inputs["Base Color"].default_value = tau_col
            if "Emission Color" in tau_bsdf.inputs:
                tau_bsdf.inputs["Emission Color"].default_value = tau_col

        r_arrow = 1.06
        for k_sec, t_obj in enumerate(tau_arrows):
            ang = math.radians(th_deg + 90.0 * k_sec)
            t_obj.location = (r_arrow * math.cos(ang), r_arrow * math.sin(ang), 0.06 + dz_vis)
            tang_dir = mathutils.Vector((-math.sin(ang), math.cos(ang), 0.0))
            if tau < 0.0:
                tang_dir = -tang_dir
            t_obj.rotation_euler = tang_dir.to_track_quat("Z", "Y").to_euler()
            t_obj.scale = (0.85, 0.85, tau_mag)

        scene.render.filepath = str(out_dir / f"raw_{f_idx:04d}.png")
        bpy.ops.render.render(write_still=True)

    blend_out = Path(bundle["blend_file"])
    blend_out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_out))
    return 0


# ==============================================================================
# HOST PYTHON DRIVER MODE (prepares JSON bundle, renders HUD frames & MP4 video)
# ==============================================================================
def run_python_mode(args: argparse.Namespace) -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image
    from scipy.interpolate import interp1d

    from utils.metrics_logger import (
        export_macros,
        generate_manuscript_map,
        log_metric,
        save_plot_provenance,
    )

    if not args.report.is_file():
        raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Missing BEM report: {args.report}")

    with args.report.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    if args.design not in report["designs"]:
        raise ValueError(f"Design {args.design!r} not found in {args.report}.")

    d_data = report["designs"][args.design]
    cyc_pts = d_data["closed_cycle"]["points"]

    base_th = np.array([p["theta_deg"] for p in cyc_pts], dtype=np.float64)
    base_z = np.array([p["z_tip_um"] for p in cyc_pts], dtype=np.float64)
    base_e = np.array([p["energy_aJ"] for p in cyc_pts], dtype=np.float64)
    base_fz = np.array([p["f_z_pN"] for p in cyc_pts], dtype=np.float64)
    base_tau = np.array([p["tau_theta_pN_um"] for p in cyc_pts], dtype=np.float64)

    n_frames = 2 if int(args.max_steps) > 0 else int(args.frames)
    th_anim = np.linspace(0.0, 90.0, n_frames, endpoint=False)

    f_z_fn = interp1d(base_th, base_z, kind="linear")
    f_e_fn = interp1d(base_th, base_e, kind="linear")
    f_fz_fn = interp1d(base_th, base_fz, kind="linear")
    f_tau_fn = interp1d(base_th, base_tau, kind="linear")

    video_dir = args.bundle.parent
    raw_dir = video_dir / "raw_frames"
    comp_dir = video_dir / "composited_frames"
    raw_dir.mkdir(parents=True, exist_ok=True)
    comp_dir.mkdir(parents=True, exist_ok=True)

    frames_payload: list[dict[str, Any]] = []
    for idx, th_val in enumerate(th_anim):
        frames_payload.append(
            {
                "frame_index": idx,
                "theta_deg": float(th_val),
                "z_tip_um": float(f_z_fn(th_val)),
                "energy_aJ": float(f_e_fn(th_val)),
                "f_z_pN": float(f_fz_fn(th_val)),
                "tau_theta_pN_um": float(f_tau_fn(th_val)),
            }
        )

    bundle = {
        "design_name": args.design,
        "z_exaggeration": float(args.z_exaggeration),
        "samples": 12 if int(args.max_steps) > 0 else int(args.samples),
        "rotor_ref_z_tip_um": float(d_data["geometry_prisms"]["rotor_ref_theta0"][0]["z0_v0"]),
        "h_teeth_um": float(d_data["h_teeth_um"]),
        "rotor_ref_theta0": d_data["geometry_prisms"]["rotor_ref_theta0"],
        "stator_sector0": d_data["geometry_prisms"]["stator_sector0"],
        "max_abs_fz_pN": float(np.max(np.abs(base_fz))),
        "max_abs_tau_pN_um": float(np.max(np.abs(base_tau))),
        "raw_frames_dir": str(raw_dir),
        "blend_file": str(video_dir / f"{args.design}_engine_cycle.blend"),
        "frames": frames_payload,
    }
    args.bundle.parent.mkdir(parents=True, exist_ok=True)
    with args.bundle.open("w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2)

    if not args.skip_blender:
        blender_exe = Path(args.blender)
        if not blender_exe.is_file():
            raise FileNotFoundError(f"Blender binary not found at {blender_exe}")
        cmd = [
            str(blender_exe),
            "--background",
            "--python",
            str(Path(__file__).resolve()),
            "--",
            "--mode",
            "blender",
            "--bundle",
            str(args.bundle),
        ]
        subprocess.run(cmd, check=True)
    else:
        # Fallback placeholder 3D view only if --skip-blender was explicitly requested
        for fr in frames_payload:
            img = Image.new("RGB", (1080, 1080), (14, 18, 28))
            img.save(raw_dir / f"raw_{fr['frame_index']:04d}.png")

    # Composite each 1080x1080 3D Blender render with a 840x1080 live telemetry HUD -> 1920x1080 HD
    land = d_data["landscape_2d"]
    z_grid_nm = np.asarray(land["z_grid_um"]) * 1e3
    th_grid_raw = np.asarray(land["theta_grid_deg"])
    th_grid_deg = np.append(th_grid_raw, 90.0)
    e_raw = np.asarray(land["energy_aJ"])
    tau_raw = np.asarray(land["tau_theta_pN_um"])
    fz_raw = np.asarray(land["f_z_pN"])
    e_mat = np.concatenate([e_raw, e_raw[:, :1]], axis=1)
    tau_mat = np.concatenate([tau_raw, tau_raw[:, :1]], axis=1)
    fz_mat = np.concatenate([fz_raw, fz_raw[:, :1]], axis=1)

    plt.style.use("dark_background")
    for fr in frames_payload:
        idx = int(fr["frame_index"])
        th_now = fr["theta_deg"]
        z_now_nm = fr["z_tip_um"] * 1e3
        e_now = fr["energy_aJ"]
        fz_now = fr["f_z_pN"]
        tau_now = fr["tau_theta_pN_um"]

        hud_fig, (ax_map, ax_curves) = plt.subplots(
            2, 1, figsize=(8.4, 10.8), dpi=100, gridspec_kw={"height_ratios": [1.05, 1.0]}
        )
        hud_fig.patch.set_facecolor("#0b0e17")

        # Top HUD: 2D Casimir Energy E_C(z, theta) + Force/Torque flow + live rotor marker
        ax_map.set_facecolor("#101522")
        im = ax_map.pcolormesh(th_grid_deg, z_grid_nm, e_mat, shading="auto", cmap="magma")
        th_m, z_m = np.meshgrid(th_grid_deg, z_grid_nm)
        f_scale = max(float(np.max(np.abs(fz_mat))), 0.05)
        t_scale = max(float(np.max(np.abs(tau_mat))), 0.01)
        ax_map.quiver(
            th_m, z_m, tau_mat / t_scale, fz_mat / f_scale, color="white", alpha=0.45, scale=18.0
        )
        ax_map.plot(base_th, base_z * 1e3, color="#00e5ff", lw=2.0, ls="--", label="Cycle Path")
        ax_map.scatter([th_now], [z_now_nm], s=150, color="#00ff88", edgecolors="white", zorder=6)
        cbar = hud_fig.colorbar(im, ax=ax_map, fraction=0.046, pad=0.03)
        cbar.set_label("$E_C$ (aJ)", color="white")
        ax_map.set_title(
            f"Fractal Casimir Engine ({args.design})\n"
            f"$\\theta = {th_now:5.1f}^\\circ$ | $z_{{\\rm tip}} = {z_now_nm:6.1f}$ nm",
            fontsize=12,
            fontweight="bold",
            color="white",
        )
        ax_map.set_xlabel("Sector Angle $\\theta$ (deg)")
        ax_map.set_ylabel("Rotor Tip $z_{\\rm tip}$ (nm)")

        # Bottom HUD: Live synchronized F_z(theta), tau_theta(theta), and E_C(theta)
        ax_curves.set_facecolor("#101522")
        ax_curves.plot(base_th, base_fz, color="#00e5ff", lw=2.3, label="$F_z$ (pN)")
        ax_curves.plot(
            base_th, base_tau * 5.0, color="#22ff77", lw=2.3, label="$5 \\times \\tau_\\theta$ (pN$\\cdot\\mu$m)"
        )
        ax_curves.plot(
            base_th,
            (base_e - np.mean(base_e)) * 10.0,
            color="#ffb703",
            lw=1.8,
            ls="-.",
            label="$10 \\times \\Delta E_C$ (aJ)",
        )
        ax_curves.axhline(0.0, color="#888888", lw=0.9, ls=":")
        ax_curves.axvline(th_now, color="white", lw=1.8)
        regime = (
            "REPULSIVE UP-STROKE (+Fz, +tau)"
            if fz_now >= 0.0 and tau_now >= 0.0
            else "ATTRACTIVE DOWN-STROKE (-Fz, +tau)"
            if fz_now < 0.0 and tau_now >= 0.0
            else "PAD-EXIT TRANSITION"
        )
        ax_curves.set_title(
            f"{regime}\n$F_z = {fz_now:+.3f}$ pN | $\\tau_\\theta = {tau_now:+.3f}$ pN$\\cdot\\mu$m | $E_C = {e_now:+.4f}$ aJ",
            fontsize=10.5,
            fontweight="bold",
            color="#72efdd" if tau_now >= 0.0 else "#ff99c8",
        )
        ax_curves.set_xlabel("Sector Angle $\\theta$ (deg)")
        ax_curves.set_ylabel("Force / Scaled Torque & Energy")
        ax_curves.legend(loc="lower left", fontsize=8.5, facecolor="#0b0e17")
        ax_curves.grid(True, alpha=0.22)

        hud_fig.tight_layout(pad=1.6)
        hud_png = comp_dir / f"_hud_{idx:04d}.png"
        hud_fig.savefig(hud_png, dpi=100, facecolor=hud_fig.get_facecolor())
        plt.close(hud_fig)

        img_3d = Image.open(raw_dir / f"raw_{idx:04d}.png").convert("RGB").resize((1080, 1080))
        img_hud = Image.open(hud_png).convert("RGB").resize((840, 1080))
        canvas = Image.new("RGB", (1920, 1080), (11, 14, 23))
        canvas.paste(img_3d, (0, 0))
        canvas.paste(img_hud, (1080, 0))
        canvas.save(comp_dir / f"frame_{idx:04d}.png")
        hud_png.unlink(missing_ok=True)

    plt.style.use("default")

    video_mp4 = video_dir / "fractal_casimir_engine_cycle.mp4"
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        fallback = Path(r"C:\Users\gorengor\.gemini\ffmpeg_shared\ffmpeg-n6.1.3-win64-gpl-shared-6.1\bin\ffmpeg.exe")
        if fallback.is_file():
            ffmpeg_bin = str(fallback)

    if ffmpeg_bin is None and int(args.max_steps) == 0:
        raise FileNotFoundError("ffmpeg binary not found in PATH or fallback location; cannot encode MP4 video.")

    if ffmpeg_bin is not None and n_frames >= 2:
        single_mp4 = video_dir / "_single_sector_cycle.mp4"
        cmd_single = [
            ffmpeg_bin,
            "-y",
            "-framerate",
            str(args.fps),
            "-i",
            str(comp_dir / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            str(single_mp4),
        ]
        subprocess.run(cmd_single, check=True)
        # Stitch 4 consecutive C_4 sector cycles (= 360-degree full revolution) into final MP4
        cmd_loop360 = [
            ffmpeg_bin,
            "-y",
            "-stream_loop",
            "3",
            "-i",
            str(single_mp4),
            "-c",
            "copy",
            str(video_mp4),
        ]
        subprocess.run(cmd_loop360, check=True)
        single_mp4.unlink(missing_ok=True)

    # Assemble 4-keyframe composite figure for manuscript + provenance sidecar
    if int(args.max_steps) == 0 and n_frames >= 4:
        pick_indices = [
            min(n_frames - 1, int(round(frac * (n_frames - 1))))
            for frac in (0.18, 0.38, 0.66, 0.88)
        ]
        fig_kf, axes_kf = plt.subplots(2, 2, figsize=(15.5, 8.8), constrained_layout=True)
        labels_kf = (
            "A. Stroke I: Repulsive Lift + Forward Spin",
            "B. Top-Dead-Center Slot-to-Pad Crossover",
            "C. Stroke III: Attractive Pull + Same-Direction Spin",
            "D. Bottom-Dead-Center Pad-Exit Reset / Gate",
        )
        for ax_k, f_i, lbl in zip(axes_kf.flat, pick_indices, labels_kf):
            arr = np.asarray(Image.open(comp_dir / f"frame_{f_i:04d}.png"))
            ax_k.imshow(arr)
            ax_k.set_title(lbl, fontsize=11, fontweight="bold")
            ax_k.axis("off")

        fig_dir = PROJECT_ROOT / "fractal_casimir_engine" / "figures"
        paper_dir = PROJECT_ROOT / "Papers" / "Fractal_Casimir_Engine"
        paper_fig_dir = paper_dir / "figures"
        metrics_path = PROJECT_ROOT / "fractal_casimir_engine" / "results" / "provenance_metrics.json"
        macros_path = PROJECT_ROOT / "fractal_casimir_engine" / "results" / "macros_results.tex"
        fig_dir.mkdir(parents=True, exist_ok=True)
        paper_fig_dir.mkdir(parents=True, exist_ok=True)

        sidecar_meta = {
            "campaign": "fractal_casimir_engine_cycle",
            "dataset": "fractal_casimir_engine_cycle",
            "formulation": "vector_dyadic_and_scalar_yukawa",
            "material": "Gold",
            "eps_bg": 1.0,
        }
        if int(report.get("blender_frames", -1)) != int(n_frames) or not macros_path.is_file():
            log_metric(
                "engine_blender_video_frames",
                int(n_frames),
                step_id="engine_cycle_campaign_summary",
                metrics_path=str(metrics_path),
                solver_name="BEM_EngineCycle_3D",
                solver_parameters=sidecar_meta,
            )
            export_macros(metrics_path=str(metrics_path), output_path=str(macros_path))
            shutil.copy2(macros_path, paper_dir / "macros_results.tex")

        for ext in ("png", "pdf"):
            out_kf = fig_dir / f"fig4_engine_blender_keyframes.{ext}"
            fig_kf.savefig(out_kf, dpi=220)
            save_plot_provenance(
                str(out_kf),
                str(args.report),
                ["engine_blender_video_frames", "engine_cfg_d_peak_fz_rep_pn", "engine_cfg_d_peak_tau_pos_pn_um"],
                solver_name="BEM_EngineCycle_3D",
                solver_parameters=sidecar_meta,
            )
            shutil.copy2(out_kf, paper_fig_dir / out_kf.name)
            for sc in fig_dir.glob(f"{out_kf.stem}*.provenance.json"):
                shutil.copy2(sc, paper_fig_dir / sc.name)
        plt.close(fig_kf)

        if video_mp4.is_file():
            shutil.copy2(video_mp4, paper_fig_dir / video_mp4.name)

        tex_path = paper_dir / "fractal_casimir_engine.tex"
        if tex_path.is_file() and metrics_path.is_file():
            ledger = generate_manuscript_map(
                str(tex_path),
                metrics_path=str(metrics_path),
                figures_dir=str(paper_fig_dir),
                output_map_path=str(paper_dir / "manuscript_provenance_map.json"),
            )
            if ledger.get("audit_status") != "PASS":
                raise RuntimeError(f"Manuscript provenance audit FAILED: {ledger}")

    print(f"[BLENDER-VIDEO] Rendered {n_frames} frames -> {video_mp4}")
    return 0


def main() -> int:
    args = parse_args()
    if args.mode == "blender":
        return run_blender_mode(args)
    return run_python_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
