#!/usr/bin/env python3
"""
MEEP Physical Simulator Voxel Extractor
---------------------------------------
Extracts the EXACT cell-by-cell discretization from the MEEP FDTD Yee grid
for the latest simulation configuration (Dual-Fractal Quantum Clutch:
Menger-Weierstrass Spire Array vs Anisotropic Sierpinski Carpet Sieve).

Outputs:
- Wavefront OBJ (.obj) with material tags (.mtl) and separated objects for Blender.
- Metadata JSON with exact physical coordinates, resolution, and voxel counts.
"""

import os
import sys
import json
import argparse
import time
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import meep as mp
    mp.verbosity(0)
except ImportError:
    print("ERROR: meep module not available in this Python environment.")
    sys.exit(1)

from execution.run_meep_simulation import compute_plate_thicknesses, compute_domain_dimensions
from execution.fractal_clutch_geometry import generate_anisotropic_sieve_apertures, generate_menger_spire_array


def build_meep_simulation(cfg, res=None):
    """Initializes the MEEP simulation structure for the given configuration."""
    L = float(cfg.get("L", 2.0))
    d = float(cfg.get("d", 0.04))
    N_top = int(cfg.get("N_top", 3))
    N_bot = int(cfg.get("N_bot", 3))
    theta = float(cfg.get("theta", 0.0))
    alpha = float(cfg.get("corrugation_angle", 75.0))
    r_tip_nm = float(cfg.get("r_tip_nm", 5.0))
    r_tip_um = r_tip_nm / 1000.0
    clutch = bool(cfg.get("clutch", True))
    resolution = int(res if res is not None else cfg.get("resolution", 40))

    t_top, t_bottom, H_spire, t_top_slab = compute_plate_thicknesses(clutch=clutch)
    sx, sy, sz, delta_s_xy, delta_s_z, L_rot = compute_domain_dimensions(
        L, theta, d, t_top, t_bottom, clutch=clutch
    )

    # Distinct epsilon tags to distinguish components during MEEP cell-by-cell query
    mat_bottom = mp.Medium(epsilon=2.0)
    mat_top_slab = mp.Medium(epsilon=3.0)
    mat_top_spires = mp.Medium(epsilon=4.0)
    mat_bg = mp.Medium(epsilon=1.0)

    geometry = []

    # 1. Bottom substrate / sieve plate
    z_bot_center = -d / 2.0 - t_bottom / 2.0
    geometry.append(mp.Block(
        center=mp.Vector3(0.0, 0.0, z_bot_center),
        size=mp.Vector3(L, L, t_bottom),
        material=mat_bottom
    ))

    # 2. Bottom plate through-slots (carved with background vacuum)
    slots = generate_anisotropic_sieve_apertures(
        N_bot, L, d, t_bottom=t_bottom, material=mat_bg
    )
    geometry.extend(slots)

    # 3. Top plate backing substrate slab
    theta_rad = np.radians(theta)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)
    e1 = mp.Vector3(C, S, 0.0)
    e2 = mp.Vector3(-S, C, 0.0)
    e3 = mp.Vector3(0.0, 0.0, 1.0)

    z_top_slab_center = d / 2.0 + H_spire + t_top_slab / 2.0
    geometry.append(mp.Block(
        center=mp.Vector3(0.0, 0.0, z_top_slab_center),
        size=mp.Vector3(L, L, t_top_slab),
        e1=e1, e2=e2, e3=e3,
        material=mat_top_slab
    ))

    # 4. Top plate Menger-Weierstrass Spire Array
    spires = generate_menger_spire_array(
        N_top, L, d, H_spire=H_spire, alpha=alpha,
        r_tip=r_tip_um, theta=theta, material=mat_top_spires
    )
    geometry.extend(spires)

    sim = mp.Simulation(
        cell_size=mp.Vector3(sx, sy, sz),
        geometry=geometry,
        resolution=resolution,
        default_material=mat_bg,
        eps_averaging=False
    )

    return sim, {
        "L": L, "d": d, "N_top": N_top, "N_bot": N_bot,
        "theta": theta, "alpha": alpha, "r_tip_nm": r_tip_nm,
        "t_top": t_top, "t_bottom": t_bottom,
        "H_spire": H_spire, "t_top_slab": t_top_slab,
        "sx": sx, "sy": sy, "sz": sz, "resolution": resolution
    }


def extract_cell_grid(sim, params):
    """Queries MEEP Yee grid cell-by-cell and classifies each voxel."""
    print("  Initializing MEEP physical structure and Yee grid...")
    t0 = time.time()
    sim.init_sim()
    eps = sim.get_epsilon()
    x, y, z, _ = sim.get_array_metadata()
    t1 = time.time()
    print(f"  MEEP Yee grid evaluated in {t1 - t0:.2f}s. Domain shape: {eps.shape} ({eps.size:,} total cells)")

    x = np.array(x)
    y = np.array(y)
    z = np.array(z)
    d = params["d"]
    H_spire = params["H_spire"]

    # 0: Vacuum, 1: Bottom Sieve, 2: Top Spires, 3: Top Backing Slab
    grid = np.zeros_like(eps, dtype=np.int32)

    for k, zk in enumerate(z):
        if zk < -d / 2.0:
            # Bottom region: cells where epsilon is elevated above vacuum belong to the sieve plate
            mask = (eps[:, :, k] > 1.15)
            grid[mask, k] = 1
        elif zk > d / 2.0:
            # Top region: separate spires from backing slab
            if zk >= (d / 2.0 + H_spire):
                mask = (eps[:, :, k] > 1.15)
                grid[mask, k] = 3
            else:
                mask = (eps[:, :, k] > 1.05)
                grid[mask, k] = 2

    # Verification: ensure gap contains zero solid cells
    gap_mask = (z >= -d / 2.0) & (z <= d / 2.0)
    gap_solid = np.sum(grid[:, :, gap_mask] > 0)
    if gap_solid > 0:
        print(f"  WARNING: {gap_solid} non-vacuum cells found in Casimir gap! Clearing for strict standoff.")
        grid[:, :, gap_mask] = 0

    return grid, x, y, z


def mesh_voxels_culled(grid, x, y, z):
    """
    Extracts exterior surface quads for each object class, culling all internal faces.
    Returns dictionary of {class_id: (vertices, faces)}.
    """
    dx = x[1] - x[0] if len(x) > 1 else 1.0 / 40.0
    dy = y[1] - y[0] if len(y) > 1 else 1.0 / 40.0
    dz = z[1] - z[0] if len(z) > 1 else 1.0 / 40.0
    Nx, Ny, Nz = grid.shape

    objects_mesh = {}

    classes = [
        (1, "Bottom_Plate_Sieve"),
        (2, "Top_Plate_Spires"),
        (3, "Top_Plate_Backing_Slab"),
    ]

    for cat_id, cat_name in classes:
        solid = (grid == cat_id)
        if not np.any(solid):
            continue

        # Find exposed faces in all 6 orthogonal directions
        # +X
        diff_px = np.zeros_like(solid)
        diff_px[:-1, :, :] = solid[:-1, :, :] & (~solid[1:, :, :])
        diff_px[-1, :, :] = solid[-1, :, :]

        # -X
        diff_nx = np.zeros_like(solid)
        diff_nx[1:, :, :] = solid[1:, :, :] & (~solid[:-1, :, :])
        diff_nx[0, :, :] = solid[0, :, :]

        # +Y
        diff_py = np.zeros_like(solid)
        diff_py[:, :-1, :] = solid[:, :-1, :] & (~solid[:, 1:, :])
        diff_py[:, -1, :] = solid[:, -1, :]

        # -Y
        diff_ny = np.zeros_like(solid)
        diff_ny[:, 1:, :] = solid[:, 1:, :] & (~solid[:, :-1, :])
        diff_ny[:, 0, :] = solid[:, 0, :]

        # +Z
        diff_pz = np.zeros_like(solid)
        diff_pz[:, :, :-1] = solid[:, :, :-1] & (~solid[:, :, 1:])
        diff_pz[:, :, -1] = solid[:, :, -1]

        # -Z
        diff_nz = np.zeros_like(solid)
        diff_nz[:, :, 1:] = solid[:, :, 1:] & (~solid[:, :, :-1])
        diff_nz[:, :, 0] = solid[:, :, 0]

        vertex_map = {}
        vertices = []
        faces = []

        def get_v_idx(vx, vy, vz):
            key = (round(vx, 7), round(vy, 7), round(vz, 7))
            if key not in vertex_map:
                idx = len(vertices) + 1  # 1-indexed for OBJ
                vertex_map[key] = idx
                vertices.append(key)
                return idx
            return vertex_map[key]

        # Process +X faces (normal +X)
        for ix, iy, iz in zip(*np.where(diff_px)):
            xm, ym, zm = x[ix] + dx/2.0, y[iy] - dy/2.0, z[iz] - dz/2.0
            xp, yp, zp = xm, ym + dy, zm + dz
            v1 = get_v_idx(xm, ym, zm)
            v2 = get_v_idx(xm, yp, zm)
            v3 = get_v_idx(xm, yp, zp)
            v4 = get_v_idx(xm, ym, zp)
            faces.append((v1, v2, v3, v4))

        # Process -X faces (normal -X)
        for ix, iy, iz in zip(*np.where(diff_nx)):
            xm, ym, zm = x[ix] - dx/2.0, y[iy] - dy/2.0, z[iz] - dz/2.0
            xp, yp, zp = xm, ym + dy, zm + dz
            v1 = get_v_idx(xm, ym, zp)
            v2 = get_v_idx(xm, yp, zp)
            v3 = get_v_idx(xm, yp, zm)
            v4 = get_v_idx(xm, ym, zm)
            faces.append((v1, v2, v3, v4))

        # Process +Y faces (normal +Y)
        for ix, iy, iz in zip(*np.where(diff_py)):
            xm, ym, zm = x[ix] - dx/2.0, y[iy] + dy/2.0, z[iz] - dz/2.0
            xp, yp, zp = xm + dx, ym, zm + dz
            v1 = get_v_idx(xp, ym, zm)
            v2 = get_v_idx(xm, ym, zm)
            v3 = get_v_idx(xm, ym, zp)
            v4 = get_v_idx(xp, ym, zp)
            faces.append((v1, v2, v3, v4))

        # Process -Y faces (normal -Y)
        for ix, iy, iz in zip(*np.where(diff_ny)):
            xm, ym, zm = x[ix] - dx/2.0, y[iy] - dy/2.0, z[iz] - dz/2.0
            xp, yp, zp = xm + dx, ym, zm + dz
            v1 = get_v_idx(xm, ym, zm)
            v2 = get_v_idx(xp, ym, zm)
            v3 = get_v_idx(xp, ym, zp)
            v4 = get_v_idx(xm, ym, zp)
            faces.append((v1, v2, v3, v4))

        # Process +Z faces (normal +Z)
        for ix, iy, iz in zip(*np.where(diff_pz)):
            xm, ym, zm = x[ix] - dx/2.0, y[iy] - dy/2.0, z[iz] + dz/2.0
            xp, yp, zp = xm + dx, ym + dy, zm
            v1 = get_v_idx(xm, ym, zm)
            v2 = get_v_idx(xp, ym, zm)
            v3 = get_v_idx(xp, yp, zm)
            v4 = get_v_idx(xm, yp, zm)
            faces.append((v1, v2, v3, v4))

        # Process -Z faces (normal -Z)
        for ix, iy, iz in zip(*np.where(diff_nz)):
            xm, ym, zm = x[ix] - dx/2.0, y[iy] - dy/2.0, z[iz] - dz/2.0
            xp, yp, zp = xm + dx, ym + dy, zm
            v1 = get_v_idx(xp, ym, zm)
            v2 = get_v_idx(xm, ym, zm)
            v3 = get_v_idx(xm, yp, zm)
            v4 = get_v_idx(xp, yp, zm)
            faces.append((v1, v2, v3, v4))

        objects_mesh[cat_name] = {
            "name": cat_name,
            "cat_id": cat_id,
            "voxel_count": int(np.sum(solid)),
            "vertices": vertices,
            "faces": faces
        }

    return objects_mesh


def export_obj_and_mtl(objects_mesh, params, out_dir, base_name):
    """Writes the multi-part OBJ and MTL files."""
    os.makedirs(out_dir, exist_ok=True)
    obj_path = os.path.join(out_dir, f"{base_name}.obj")
    mtl_path = os.path.join(out_dir, f"{base_name}.mtl")

    # 1. Write MTL Material definitions
    with open(mtl_path, "w") as f_mtl:
        f_mtl.write("# Material definitions for MEEP Dual-Fractal Quantum Clutch\n")
        f_mtl.write("# Physically modeled Gold and Casimir gap indicators\n\n")

        # Top Plate Spires (Polished high-contrast gold)
        f_mtl.write("newmtl Material_TopPlate_Spires\n")
        f_mtl.write("Kd 1.000 0.766 0.336\n")  # Gold diffuse
        f_mtl.write("Ks 0.950 0.950 0.950\n")  # Specular
        f_mtl.write("Ns 150.0\n")             # High gloss
        f_mtl.write("d 1.0\n\n")

        # Top Plate Backing Slab (Substrate gold)
        f_mtl.write("newmtl Material_TopPlate_Backing_Slab\n")
        f_mtl.write("Kd 0.850 0.650 0.250\n")  # Slightly darker gold backing
        f_mtl.write("Ks 0.700 0.700 0.700\n")
        f_mtl.write("Ns 80.0\n")
        f_mtl.write("d 1.0\n\n")

        # Bottom Plate Sieve (Golden membrane)
        f_mtl.write("newmtl Material_Bottom_Plate_Sieve\n")
        f_mtl.write("Kd 0.980 0.820 0.400\n")  # Warm gold
        f_mtl.write("Ks 0.900 0.900 0.900\n")
        f_mtl.write("Ns 120.0\n")
        f_mtl.write("d 1.0\n\n")

        # Casimir Gap indicator (Emissive semi-transparent cyan wireframe)
        f_mtl.write("newmtl Material_Casimir_Vacuum_Gap\n")
        f_mtl.write("Kd 0.050 0.800 0.950\n")
        f_mtl.write("Ke 0.050 0.600 0.800\n")  # Emission
        f_mtl.write("d 0.35\n\n")

    # 2. Write OBJ file with all objects separated
    with open(obj_path, "w") as f_obj:
        f_obj.write(f"# MEEP 3D Voxel Model: {base_name}\n")
        f_obj.write(f"# Extracted from Yee grid cell-by-cell at resolution {params['resolution']} voxels/um\n")
        f_obj.write(f"# Plate width L = {params['L']} um, Gap d = {int(params['d']*1000)} nm\n")
        f_obj.write(f"mtllib {os.path.basename(mtl_path)}\n\n")

        global_v_offset = 0

        for obj_name, data in objects_mesh.items():
            f_obj.write(f"o {obj_name}\n")
            f_obj.write(f"g {obj_name}\n")
            f_obj.write(f"usemtl Material_{obj_name}\n")
            f_obj.write(f"s 1\n")

            # Write vertices
            for vx, vy, vz in data["vertices"]:
                f_obj.write(f"v {vx:.6f} {vy:.6f} {vz:.6f}\n")

            # Write faces (offset by global vertex counter)
            for v1, v2, v3, v4 in data["faces"]:
                f_obj.write(f"f {v1 + global_v_offset} {v2 + global_v_offset} {v3 + global_v_offset} {v4 + global_v_offset}\n")

            global_v_offset += len(data["vertices"])
            f_obj.write("\n")

        # Add Casimir Gap Volume Bounding Object
        d = params["d"]
        L = params["L"]
        gap_half_x = L / 2.0
        gap_half_y = L / 2.0
        z_gap_bot = -d / 2.0
        z_gap_top = d / 2.0

        f_obj.write("o Casimir_Vacuum_Gap\n")
        f_obj.write("g Casimir_Vacuum_Gap\n")
        f_obj.write("usemtl Material_Casimir_Vacuum_Gap\n")
        f_obj.write("s 1\n")

        gap_verts = [
            (-gap_half_x, -gap_half_y, z_gap_bot),
            ( gap_half_x, -gap_half_y, z_gap_bot),
            ( gap_half_x,  gap_half_y, z_gap_bot),
            (-gap_half_x,  gap_half_y, z_gap_bot),
            (-gap_half_x, -gap_half_y, z_gap_top),
            ( gap_half_x, -gap_half_y, z_gap_top),
            ( gap_half_x,  gap_half_y, z_gap_top),
            (-gap_half_x,  gap_half_y, z_gap_top),
        ]
        for vx, vy, vz in gap_verts:
            f_obj.write(f"v {vx:.6f} {vy:.6f} {vz:.6f}\n")

        # 6 quad faces of the gap volume
        gap_faces = [
            (1, 4, 3, 2),  # -Z face
            (5, 6, 7, 8),  # +Z face
            (1, 2, 6, 5),  # -Y face
            (2, 3, 7, 6),  # +X face
            (3, 4, 8, 7),  # +Y face
            (4, 1, 5, 8),  # -X face
        ]
        for v1, v2, v3, v4 in gap_faces:
            f_obj.write(f"f {v1 + global_v_offset} {v2 + global_v_offset} {v3 + global_v_offset} {v4 + global_v_offset}\n")

    return obj_path, mtl_path


def main():
    parser = argparse.ArgumentParser(description="Export MEEP physical simulation configuration to 3D voxels for Blender.")
    parser.add_argument("--config", type=str, default="sweep_configs_clutch/config_001.json", help="Path to config JSON.")
    parser.add_argument("--res", type=int, default=None, help="Override grid resolution in px/um (e.g. 40 or 60).")
    parser.add_argument("--out-dir", type=str, default="results_voxel_visualization", help="Output directory.")
    parser.add_argument("--name", type=str, default="meep_latest_clutch_voxels", help="Base name for outputs.")
    args = parser.parse_args()

    cfg_file = os.path.join(REPO_ROOT, args.config) if not os.path.isabs(args.config) else args.config
    if not os.path.exists(cfg_file):
        print(f"ERROR: Config file not found at {cfg_file}")
        sys.exit(1)

    with open(cfg_file, "r") as f:
        cfg = json.load(f)

    print("=" * 80)
    print("MEEP SIMULATOR: 3D PHYSICAL VOXEL EXTRACTOR")
    print("=" * 80)
    print(f"Configuration File: {cfg_file}")
    print(f"Label: {cfg.get('label', 'Quantum Clutch')}")
    print(f"Material: {cfg.get('material', 'Gold')}")
    print(f"Plate Width L: {cfg.get('L', 2.0)} um")
    print(f"Casimir Gap d: {int(cfg.get('d', 0.04)*1000)} nm")
    print(f"Twist Angle theta: {cfg.get('theta', 0.0)} deg")
    print(f"Pyramid Slope alpha: {cfg.get('corrugation_angle', 75.0)} deg")
    print(f"Tip Radius r_tip: {cfg.get('r_tip_nm', 5.0)} nm")
    print(f"Prefractal Levels: Top N={cfg.get('N_top', 3)}, Bottom N={cfg.get('N_bot', 3)}")
    print(f"Resolution: {args.res or cfg.get('resolution', 40)} voxels/um")
    print("=" * 80)

    # 1. Build simulation
    sim, params = build_meep_simulation(cfg, res=args.res)

    # 2. Extract cell grid
    grid, x, y, z = extract_cell_grid(sim, params)

    # 3. Mesh solid voxels with face culling
    print("  Meshing solid voxels with interior face culling...")
    objects_mesh = mesh_voxels_culled(grid, x, y, z)

    total_voxels = sum(o["voxel_count"] for o in objects_mesh.values())
    total_faces = sum(len(o["faces"]) for o in objects_mesh.values())
    total_verts = sum(len(o["vertices"]) for o in objects_mesh.values())

    print(f"  Extracted Components:")
    for obj_name, data in objects_mesh.items():
        print(f"    - {obj_name}: {data['voxel_count']:,} voxels, {len(data['faces']):,} quad faces, {len(data['vertices']):,} vertices")
    print(f"  Total Solid Voxels: {total_voxels:,} | Surface Quads: {total_faces:,} | Vertices: {total_verts:,}")

    # 4. Export OBJ & MTL
    out_dir = os.path.join(REPO_ROOT, args.out_dir) if not os.path.isabs(args.out_dir) else args.out_dir
    obj_path, mtl_path = export_obj_and_mtl(objects_mesh, params, out_dir, args.name)
    print(f"  OBJ exported: {obj_path} ({os.path.getsize(obj_path)/(1024*1024):.2f} MB)")
    print(f"  MTL exported: {mtl_path}")

    # 5. Export metadata JSON
    meta_path = os.path.join(out_dir, f"{args.name}_metadata.json")
    metadata = {
        "config_file": cfg_file,
        "label": cfg.get("label", "Quantum Clutch"),
        "material": cfg.get("material", "Gold"),
        "plate_width_um": params["L"],
        "gap_d_um": params["d"],
        "gap_d_nm": int(params["d"] * 1000),
        "theta_deg": params["theta"],
        "alpha_deg": params["alpha"],
        "r_tip_nm": params["r_tip_nm"],
        "resolution_px_per_um": params["resolution"],
        "cell_dx_nm": float((x[1] - x[0]) * 1000),
        "cell_dy_nm": float((y[1] - y[0]) * 1000),
        "cell_dz_nm": float((z[1] - z[0]) * 1000),
        "domain_shape": list(grid.shape),
        "total_domain_cells": int(grid.size),
        "total_solid_voxels": total_voxels,
        "total_surface_quads": total_faces,
        "components": {
            obj_name: {
                "voxel_count": data["voxel_count"],
                "quad_faces": len(data["faces"]),
                "vertices": len(data["vertices"])
            }
            for obj_name, data in objects_mesh.items()
        },
        "obj_file": obj_path,
        "mtl_file": mtl_path
    }
    with open(meta_path, "w") as f_meta:
        json.dump(metadata, f_meta, indent=4)
    print(f"  Metadata saved: {meta_path}")

    print("=" * 80)
    print("VOXEL EXTRACTION COMPLETE AND READY FOR BLENDER!")
    print("=" * 80)


if __name__ == "__main__":
    main()
