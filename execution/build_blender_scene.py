#!/usr/bin/env python3
"""
Blender Scene Generator for MEEP 3D Voxel Models
------------------------------------------------
Imports the MEEP voxel-based physical configuration into Blender 4.5+,
assigns physically accurate Cycles/Eevee gold and dielectric shaders,
adds interactive Exploded View shape keys, sets up studio lighting,
cameras, measurement calipers, and renders publication-grade preview images.

Usage (Headless):
    blender --background --python execution/build_blender_scene.py -- [options]
"""

import os
import sys
import math
import argparse

try:
    import bpy
    import mathutils
except ImportError:
    print("ERROR: This script must be executed within Blender (blender --background --python ...)")
    sys.exit(1)


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Build Blender scene from MEEP voxel OBJ.")
    parser.add_argument("--obj", type=str, default="results_voxel_visualization/meep_latest_clutch_voxels_res60.obj")
    parser.add_argument("--out-blend", type=str, default="results_voxel_visualization/meep_latest_clutch_scene.blend")
    parser.add_argument("--out-glb", type=str, default="results_voxel_visualization/meep_latest_clutch_voxels.glb")
    parser.add_argument("--render-dir", type=str, default="results_voxel_visualization")
    return parser.parse_args(argv)


def reset_scene():
    """Removes all default objects from the scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def create_gold_material(name, color_rgb, roughness, metallic=1.0):
    """Creates a high-fidelity Principled BSDF gold shader."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    node_out = nodes.new(type="ShaderNodeOutputMaterial")
    node_out.location = (400, 0)

    node_bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    node_bsdf.location = (0, 0)
    node_bsdf.inputs["Base Color"].default_value = (*color_rgb, 1.0)
    node_bsdf.inputs["Metallic"].default_value = metallic
    node_bsdf.inputs["Roughness"].default_value = roughness
    node_bsdf.inputs["IOR"].default_value = 0.47  # Physical optical IOR of Gold

    links.new(node_bsdf.outputs["BSDF"], node_out.inputs["Surface"])
    return mat


def create_gap_material(name="Material_Casimir_Vacuum_Gap"):
    """Creates an emissive semi-transparent wireframe/bounding shader for the Casimir gap."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    node_out = nodes.new(type="ShaderNodeOutputMaterial")
    node_out.location = (400, 0)

    node_bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    node_bsdf.location = (0, 0)
    node_bsdf.inputs["Base Color"].default_value = (0.05, 0.85, 1.0, 1.0)  # Cyan
    node_bsdf.inputs["Roughness"].default_value = 0.1
    node_bsdf.inputs["Transmission Weight"].default_value = 0.90
    node_bsdf.inputs["Emission Color"].default_value = (0.0, 0.7, 1.0, 1.0)
    node_bsdf.inputs["Emission Strength"].default_value = 0.5
    node_bsdf.inputs["Alpha"].default_value = 0.35

    links.new(node_bsdf.outputs["BSDF"], node_out.inputs["Surface"])
    return mat


def setup_lighting():
    """Sets up studio lighting with sun, key, fill, and rim lights for metallic materials."""
    # 1. Main Sun Light for crisp metallic reflections
    sun_data = bpy.data.lights.new(name="Sun_Light", type="SUN")
    sun_data.energy = 5.0
    sun_data.color = (1.0, 0.98, 0.94)
    sun_obj = bpy.data.objects.new(name="Sun_Light", object_data=sun_data)
    sun_obj.rotation_euler = (math.radians(50), math.radians(25), math.radians(-40))
    bpy.context.scene.collection.objects.link(sun_obj)

    # 2. Key Light (Warm area light, front-right)
    key_data = bpy.data.lights.new(name="Key_Light", type="AREA")
    key_data.energy = 150.0
    key_data.size = 3.0
    key_data.color = (1.0, 0.95, 0.88)
    key_obj = bpy.data.objects.new(name="Key_Light", object_data=key_data)
    key_obj.location = (3.5, -3.0, 2.5)
    key_obj.rotation_euler = (math.radians(55), math.radians(15), math.radians(45))
    bpy.context.scene.collection.objects.link(key_obj)

    # 3. Fill Light (Cool area light, front-left)
    fill_data = bpy.data.lights.new(name="Fill_Light", type="AREA")
    fill_data.energy = 100.0
    fill_data.size = 4.0
    fill_data.color = (0.88, 0.94, 1.0)
    fill_obj = bpy.data.objects.new(name="Fill_Light", object_data=fill_data)
    fill_obj.location = (-3.0, -3.0, 1.5)
    fill_obj.rotation_euler = (math.radians(60), math.radians(-15), math.radians(-40))
    bpy.context.scene.collection.objects.link(fill_obj)

    # 4. Underside / Sieve Fill Light (Illuminates bottom sieve and through-slots)
    under_data = bpy.data.lights.new(name="Underside_Light", type="AREA")
    under_data.energy = 120.0
    under_data.size = 3.5
    under_data.color = (1.0, 0.96, 0.92)
    under_obj = bpy.data.objects.new(name="Underside_Light", object_data=under_data)
    under_obj.location = (0.0, 0.0, -2.5)
    under_obj.rotation_euler = (0, 0, 0)
    bpy.context.scene.collection.objects.link(under_obj)

    # 5. Rim Accent Light (Back-top)
    rim_data = bpy.data.lights.new(name="Rim_Light", type="AREA")
    rim_data.energy = 140.0
    rim_data.size = 2.5
    rim_data.color = (1.0, 1.0, 1.0)
    rim_obj = bpy.data.objects.new(name="Rim_Light", object_data=rim_data)
    rim_obj.location = (0.0, 3.5, 2.5)
    rim_obj.rotation_euler = (math.radians(-135), 0, 0)
    bpy.context.scene.collection.objects.link(rim_obj)


def add_scale_caliper(L=2.0, d=0.04):
    """Creates visual 3D scale bars and gap measurement markers in the scene."""
    caliper_col = bpy.data.collections.new("Measurement_Calipers")
    bpy.context.scene.collection.children.link(caliper_col)

    # Lateral scale bar (1 um = 1000 nm)
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.015, depth=1.0, location=(0.0, -L/2.0 - 0.25, -d/2.0)
    )
    bar = bpy.context.active_object
    bar.name = "Scale_Bar_1um"
    bar.rotation_euler = (0, math.radians(90), 0)
    caliper_col.objects.link(bar)
    bpy.context.scene.collection.objects.unlink(bar)

    mat_cal = bpy.data.materials.new(name="Material_Caliper_Marker")
    mat_cal.use_nodes = True
    bsdf = mat_cal.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 1.0, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.2
    bar.data.materials.append(mat_cal)


def setup_cameras():
    """Creates 4 dedicated cameras to capture all angles of the physical assembly."""
    cameras = {}

    # 1. Side Gap Profile Camera (Shows spires entering 40 nm gap above sieve)
    c1_data = bpy.data.cameras.new(name="Camera_Side_Gap_Profile")
    c1_data.lens = 45
    c1_obj = bpy.data.objects.new(name="Camera_Side_Gap_Profile", object_data=c1_data)
    c1_obj.location = (2.2, -0.6, 0.25)
    dir1 = mathutils.Vector((0.0, 0.0, 0.05)) - c1_obj.location
    c1_obj.rotation_euler = dir1.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(c1_obj)
    cameras["side_gap"] = c1_obj

    # 2. Exploded 3/4 Overview Camera (Angled from low-elevation to see under the top plate and into the sieve)
    c2_data = bpy.data.cameras.new(name="Camera_Exploded_Overview")
    c2_data.lens = 42
    c2_obj = bpy.data.objects.new(name="Camera_Exploded_Overview", object_data=c2_data)
    c2_obj.location = (2.6, -2.6, -0.4)
    dir2 = mathutils.Vector((0.0, 0.0, 0.25)) - c2_obj.location
    c2_obj.rotation_euler = dir2.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(c2_obj)
    cameras["exploded"] = c2_obj

    # 3. Fractal Spire Array Underside Camera (Looking directly up at Menger spires)
    c3_data = bpy.data.cameras.new(name="Camera_Spire_Array")
    c3_data.lens = 45
    c3_obj = bpy.data.objects.new(name="Camera_Spire_Array", object_data=c3_data)
    c3_obj.location = (0.0, 0.0, -2.8)
    c3_obj.rotation_euler = (math.radians(180), 0, 0)
    bpy.context.scene.collection.objects.link(c3_obj)
    cameras["spires"] = c3_obj

    # 4. Fractal Sieve Apertures Topdown Camera (Looking down at sieve slots)
    c4_data = bpy.data.cameras.new(name="Camera_Sieve_Apertures")
    c4_data.lens = 50
    c4_obj = bpy.data.objects.new(name="Camera_Sieve_Apertures", object_data=c4_data)
    c4_obj.location = (0.5, -1.8, 1.8)
    dir4 = mathutils.Vector((0.0, 0.0, -0.05)) - c4_obj.location
    c4_obj.rotation_euler = dir4.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(c4_obj)
    cameras["sieve"] = c4_obj

    # 5. Alignment Verification Profile Camera (Looking directly along the X-axis slot tunnels)
    c5_data = bpy.data.cameras.new(name="Camera_Alignment_Profile")
    c5_data.lens = 32
    c5_obj = bpy.data.objects.new(name="Camera_Alignment_Profile", object_data=c5_data)
    c5_obj.location = (3.0, 0.15, 0.12)
    dir5 = mathutils.Vector((0.0, 0.0, 0.08)) - c5_obj.location
    c5_obj.rotation_euler = dir5.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(c5_obj)
    cameras["alignment"] = c5_obj

    return cameras


def add_exploded_shape_key(obj, z_offset=0.65):
    """Adds an interactive shape key to smoothly lift top plate components in Blender."""
    if not obj or obj.type != "MESH":
        return None
    sk_basis = obj.shape_key_add(name="Actual_Physical_Gap", from_mix=False)
    sk_exp = obj.shape_key_add(name="Exploded_View", from_mix=False)
    for v in sk_exp.data:
        v.co.z += z_offset
    sk_exp.value = 0.0  # Default to exact physical position!
    return sk_exp


def main():
    args = parse_args()

    obj_path = os.path.abspath(args.obj)
    if not os.path.exists(obj_path):
        print(f"ERROR: OBJ file not found: {obj_path}")
        sys.exit(1)

    print("=" * 80)
    print("BUILDING BLENDER 3D SCENE FROM MEEP VOXEL MODEL")
    print("=" * 80)
    print(f"Input OBJ: {obj_path}")

    # 1. Reset scene
    reset_scene()

    # 2. Import OBJ
    print("Importing MEEP voxel mesh...")
    bpy.ops.wm.obj_import(filepath=obj_path)

    # 3. Create high-quality procedural PBR gold materials
    mat_spires = create_gold_material("Material_TopPlate_Spires", (1.000, 0.766, 0.336), roughness=0.20)
    mat_slab = create_gold_material("Material_TopPlate_Backing_Slab", (0.880, 0.680, 0.280), roughness=0.35)
    mat_sieve = create_gold_material("Material_Bottom_Plate_Sieve", (0.980, 0.820, 0.400), roughness=0.16)
    mat_gap = create_gap_material("Material_Casimir_Vacuum_Gap")

    mat_lookup = {
        "Top_Plate_Spires": mat_spires,
        "Top_Plate_Backing_Slab": mat_slab,
        "Bottom_Plate_Sieve": mat_sieve,
        "Casimir_Vacuum_Gap": mat_gap,
    }

    # Group objects into Collections and add Exploded View shape keys
    clutch_col = bpy.data.collections.new("Fractal_Quantum_Clutch")
    bpy.context.scene.collection.children.link(clutch_col)

    top_plate_objects = []
    bottom_plate_objects = []
    gap_object = None

    for obj in list(bpy.context.scene.collection.objects):
        for key, mat in mat_lookup.items():
            if key.lower() in obj.name.lower():
                obj.data.materials.clear()
                obj.data.materials.append(mat)
                print(f"  Assigned {mat.name} to {obj.name}")

                if key == "Casimir_Vacuum_Gap":
                    obj.display_type = "WIRE"
                    obj.show_wire = True
                    gap_object = obj

                if "Top_Plate" in key:
                    top_plate_objects.append(obj)
                    add_exploded_shape_key(obj, z_offset=0.65)
                    print(f"  Added 'Exploded_View' shape key to {obj.name}")

                if "Bottom_Plate" in key:
                    bottom_plate_objects.append(obj)

                clutch_col.objects.link(obj)
                bpy.context.scene.collection.objects.unlink(obj)
                break

    # 4. Setup Lighting and Calipers
    setup_lighting()
    add_scale_caliper()

    # 5. Setup Cameras
    cameras = setup_cameras()

    # 6. Render Settings (High-Quality Eevee Next)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    # World background: studio ambient light so gold shines brilliantly
    world = bpy.data.worlds.new(name="Studio_Environment")
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = (0.18, 0.20, 0.24, 1.0)
        bg_node.inputs["Strength"].default_value = 1.6
    scene.world = world

    # 7. Save .blend file (default state: Exploded_View = 0.0, the exact physical simulation)
    out_blend = os.path.abspath(args.out_blend)
    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print(f"Saved native Blender scene: {out_blend}")

    # 8. Export .glb
    out_glb = os.path.abspath(args.out_glb)
    bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB")
    print(f"Exported GLB asset: {out_glb}")

    # 9. Render Multi-View Previews
    render_dir = os.path.abspath(args.render_dir)
    os.makedirs(render_dir, exist_ok=True)

    # Render 1: Side Gap Profile View (Actual assembly, 40 nm gap)
    r1_path = os.path.join(render_dir, "meep_clutch_side_gap_actual.png")
    scene.camera = cameras["side_gap"]
    scene.render.filepath = r1_path
    print("Rendering Side Gap Profile...")
    bpy.ops.render.render(write_still=True)
    print(f"  Rendered: {r1_path}")

    # Render 2: Exploded Overview (Lifting top plate to clearly show fractal spires and sieve)
    r2_path = os.path.join(render_dir, "meep_clutch_exploded_overview.png")
    scene.camera = cameras["exploded"]
    scene.render.filepath = r2_path
    for obj in top_plate_objects:
        sk = obj.data.shape_keys.key_blocks.get("Exploded_View")
        if sk:
            sk.value = 1.0
    print("Rendering Exploded Overview...")
    bpy.ops.render.render(write_still=True)
    print(f"  Rendered: {r2_path}")

    # Render 3: Spire Array View (Hide bottom plate to showcase recursive Menger spires)
    r3_path = os.path.join(render_dir, "meep_clutch_spire_array_detail.png")
    scene.camera = cameras["spires"]
    scene.render.filepath = r3_path
    for obj in bottom_plate_objects:
        obj.hide_render = True
    if gap_object:
        gap_object.hide_render = True
    print("Rendering Spire Array Detail...")
    bpy.ops.render.render(write_still=True)
    print(f"  Rendered: {r3_path}")
    for obj in bottom_plate_objects:
        obj.hide_render = False

    # Render 4: Sieve Apertures View (Hide top plate to showcase Anisotropic Sierpinski sieve)
    r4_path = os.path.join(render_dir, "meep_clutch_sieve_apertures_detail.png")
    scene.camera = cameras["sieve"]
    scene.render.filepath = r4_path
    for obj in top_plate_objects:
        obj.hide_render = True
    print("Rendering Sieve Apertures Detail...")
    bpy.ops.render.render(write_still=True)
    print(f"  Rendered: {r4_path}")

    # Render 5: Alignment Verification View (Looking along X-axis to verify N=1, N=2, N=3 alignment)
    r5_path = os.path.join(render_dir, "meep_clutch_alignment_detail.png")
    scene.camera = cameras["alignment"]
    scene.render.filepath = r5_path
    for obj in top_plate_objects:
        obj.hide_render = False
        sk = obj.data.shape_keys.key_blocks.get("Exploded_View")
        if sk:
            sk.value = 0.22  # Lifted slightly to clearly see spire tips hovering right over sieve slots
    for obj in bottom_plate_objects:
        obj.hide_render = False
    if gap_object:
        gap_object.hide_render = True
    print("Rendering Alignment Verification Detail...")
    bpy.ops.render.render(write_still=True)
    print(f"  Rendered: {r5_path}")

    # Reset visibility and shape keys back to 0.0 (actual physical position) and re-save .blend
    for obj in top_plate_objects:
        obj.hide_render = False
        sk = obj.data.shape_keys.key_blocks.get("Exploded_View")
        if sk:
            sk.value = 0.0
    for obj in bottom_plate_objects:
        obj.hide_render = False
    if gap_object:
        gap_object.hide_render = False

    scene.camera = cameras["side_gap"]
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)

    print("=" * 80)
    print("BLENDER SCENE GENERATION COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    main()
