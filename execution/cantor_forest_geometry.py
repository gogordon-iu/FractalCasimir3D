#!/usr/bin/env python3
"""
Sierpinski-Cantor Forest Geometry Generator
--------------------------------------------
Generates the dual-fractal geometry for the Sierpinski-Cantor Forest Casimir simulation:
1. Bottom Stator Plate: Thin gold membrane with a space-filling Sierpinski Carpet Sieve
   perforated by 73 square apertures at N=3 (1 macro, 8 meso, 64 micro).
2. Top Rotor/Translator Plate: 3D Cantor Forest of elongated square metallic pillars
   extending downwards from a backing substrate, centered 1:1 inside the sieve apertures.

Guarantees:
- Pure first-principles Cartesian coordinate generation with zero hardcoded offsets.
- Exact self-similar analytical alignment between top pillars and bottom apertures.
- Rigorous tip clearance z_tip preserved in homogeneous vacuum between pillar tips
  (z = z_tip) and top surface of the stator membrane (z = 0).
- Support for cleanroom corner filleting (r_fillet) to model electron-beam blur and etching.
- Strict area fraction calculations for background extinction analysis.
"""

import math
import numpy as np

try:
    import meep as mp
except ImportError:
    mp = None


def get_sierpinski_cantor_elements(
    N: int,
    L: float = 1.0,
    W1: float = 0.250,
    w1: float = 0.035
) -> list:
    """
    Computes exact analytical coordinates and dimensions for each element
    in the Sierpinski-Cantor hierarchy up to prefractal level N in {1, 2, 3}.

    Parameters:
        N: Prefractal level (1, 2, or 3).
        L: Unit cell lateral span in microns (e.g. 1.0 um).
        W1: Primary aperture width in microns (e.g. 0.250 um = 250 nm).
        w1: Primary pillar base width in microns (e.g. 0.035 um = 35 nm).

    Returns:
        List of dicts, each containing:
          - 'level': Prefractal level k in {1, 2, 3}
          - 'cx': Center x coordinate (microns)
          - 'cy': Center y coordinate (microns)
          - 'W_aperture': Aperture width (microns)
          - 'w_pillar': Pillar width (microns)
    """
    assert N in [1, 2, 3], f"Prefractal level N must be 1, 2, or 3, got {N}"
    assert L > 0.0, f"Unit cell span L must be positive, got {L}"
    assert W1 > 0.0 and W1 < L, f"W1 must be in (0, L), got {W1}"
    assert w1 > 0.0 and w1 < W1, f"w1 must be in (0, W1), got {w1}"

    elements = []

    # Level 1: 1 central macro-aperture and pillar (centered at 0, 0)
    elements.append({
        "level": 1,
        "cx": 0.0,
        "cy": 0.0,
        "W_aperture": float(W1),
        "w_pillar": float(w1)
    })

    # Level 2 (if N >= 2): 8 meso-apertures and pillars
    if N >= 2:
        W2 = W1 / 3.0
        w2 = w1 / 3.0
        offsets_lvl2 = [-L / 3.0, 0.0, L / 3.0]
        for dx in offsets_lvl2:
            for dy in offsets_lvl2:
                if dx == 0.0 and dy == 0.0:
                    continue  # Central cell occupied by Level 1
                elements.append({
                    "level": 2,
                    "cx": float(dx),
                    "cy": float(dy),
                    "W_aperture": float(W2),
                    "w_pillar": float(w2)
                })

    # Level 3 (if N >= 3): 64 micro-apertures and pillars
    if N >= 3:
        W3 = W1 / 9.0
        w3 = w1 / 9.0
        offsets_lvl2 = [-L / 3.0, 0.0, L / 3.0]
        offsets_lvl3 = [-L / 9.0, 0.0, L / 9.0]
        for dx2 in offsets_lvl2:
            for dy2 in offsets_lvl2:
                if dx2 == 0.0 and dy2 == 0.0:
                    continue  # Level 1 central zone
                for dx3 in offsets_lvl3:
                    for dy3 in offsets_lvl3:
                        if dx3 == 0.0 and dy3 == 0.0:
                            continue  # Level 2 meso-cell center
                        elements.append({
                            "level": 3,
                            "cx": float(dx2 + dx3),
                            "cy": float(dy2 + dy3),
                            "W_aperture": float(W3),
                            "w_pillar": float(w3)
                        })

    # Exact element count assertions
    expected_counts = {1: 1, 2: 9, 3: 73}
    assert len(elements) == expected_counts[N], (
        f"Expected {expected_counts[N]} elements at N={N}, got {len(elements)}"
    )

    return elements


def compute_sieve_area_fractions(elements: list, L: float) -> dict:
    """
    Computes exact analytical geometric area fractions for the Sierpinski sieve:
      - total_aperture_area: sum of all W_k^2
      - aperture_area_fraction: f_holes = total_aperture_area / L^2
      - solid_metal_area_fraction: f_solid = 1.0 - f_holes
    """
    total_hole_area = sum(elem["W_aperture"] ** 2 for elem in elements)
    f_holes = float(total_hole_area / (L ** 2))
    f_solid = float(1.0 - f_holes)
    return {
        "total_aperture_area_um2": float(total_hole_area),
        "aperture_area_fraction": f_holes,
        "solid_metal_area_fraction": f_solid
    }


def generate_sierpinski_sieve_geometry(
    elements: list,
    L_plate: float,
    t_plate: float,
    plate_material,
    void_material,
    theta: float = 0.0,
    r_fillet: float = 0.0,
    num_fillet_segments: int = 4
) -> list:
    """
    Constructs the MEEP geometry blocks for the Sierpinski Carpet Sieve (stator membrane).
    Stator occupies: z in [-t_plate, 0].
    Outer solid slab spans [-L_plate/2, L_plate/2] in x and y.
    Each aperture is carved through the entire thickness (from -t_plate to 0).
    Apertures are rotated in-plane by angle theta around the z-axis.

    If r_fillet > 0:
    Models cleanroom corner rounding (filleting) due to e-beam blur and etching.
    Corners of the square aperture are rounded into circular arcs with radius r_fillet.
    """
    if mp is None:
        raise ImportError("MEEP library is required to instantiate physical geometry.")

    shapes = []

    # 1. Base solid metallic membrane
    shapes.append(mp.Block(
        center=mp.Vector3(0.0, 0.0, -t_plate / 2.0),
        size=mp.Vector3(L_plate, L_plate, t_plate),
        material=plate_material
    ))

    # Overhang to ensure clean numerical carving through Yee grid boundaries
    h_carve = t_plate + 0.002

    theta_rad = np.radians(theta)
    cos_th = np.cos(theta_rad)
    sin_th = np.sin(theta_rad)
    e1 = mp.Vector3(cos_th, sin_th, 0.0)
    e2 = mp.Vector3(-sin_th, cos_th, 0.0)
    e3 = mp.Vector3(0.0, 0.0, 1.0)

    # 2. Carve out apertures
    for elem in elements:
        cx_orig = elem["cx"]
        cy_orig = elem["cy"]
        cx = cx_orig * cos_th - cy_orig * sin_th
        cy = cx_orig * sin_th + cy_orig * cos_th
        W = elem["W_aperture"]

        if r_fillet <= 0.0 or r_fillet >= (W / 2.0):
            # Standard sharp 90-degree square aperture
            shapes.append(mp.Block(
                center=mp.Vector3(cx, cy, -t_plate / 2.0),
                size=mp.Vector3(W, W, h_carve),
                e1=e1,
                e2=e2,
                e3=e3,
                material=void_material
            ))
        else:
            # Filleted corner aperture (cross + 4 rounded corner cylinders)
            shapes.append(mp.Block(
                center=mp.Vector3(cx, cy, -t_plate / 2.0),
                size=mp.Vector3(W, W - 2.0 * r_fillet, h_carve),
                e1=e1,
                e2=e2,
                e3=e3,
                material=void_material
            ))
            shapes.append(mp.Block(
                center=mp.Vector3(cx, cy, -t_plate / 2.0),
                size=mp.Vector3(W - 2.0 * r_fillet, W, h_carve),
                e1=e1,
                e2=e2,
                e3=e3,
                material=void_material
            ))
            # 4 corner cylinders with radius r_fillet
            corner_offset = W / 2.0 - r_fillet
            for sx in [-1.0, 1.0]:
                for sy in [-1.0, 1.0]:
                    dx_local = sx * corner_offset
                    dy_local = sy * corner_offset
                    dx_rot = dx_local * cos_th - dy_local * sin_th
                    dy_rot = dx_local * sin_th + dy_local * cos_th
                    shapes.append(mp.Cylinder(
                        radius=r_fillet,
                        height=h_carve,
                        center=mp.Vector3(cx + dx_rot, cy + dy_rot, -t_plate / 2.0),
                        material=void_material
                    ))

    return shapes


def generate_cantor_forest_geometry(
    elements: list,
    z_tip: float,
    H_pillar: float,
    pillar_material,
    with_backing: bool = False,
    L_plate: float = 1.0,
    t_back: float = 0.050
) -> list:
    """
    Constructs the MEEP geometry blocks for the 3D Cantor Forest of pillars (top plate).
    Pillars occupy: z in [z_tip, z_tip + H_pillar].
    Pillar tips terminate at z = z_tip above the stator surface (z = 0).

    If with_backing is True:
    Adds a solid backing substrate of thickness t_back at z in [z_tip + H_pillar, z_tip + H_pillar + t_back],
    connecting all 73 pillars into a single monolithic top chip.
    """
    if mp is None:
        raise ImportError("MEEP library is required to instantiate physical geometry.")

    shapes = []
    z_center_pillar = z_tip + H_pillar / 2.0

    # 1. Array of Cantor square pillars
    for elem in elements:
        cx = elem["cx"]
        cy = elem["cy"]
        w = elem["w_pillar"]
        shapes.append(mp.Block(
            center=mp.Vector3(cx, cy, z_center_pillar),
            size=mp.Vector3(w, w, H_pillar),
            material=pillar_material
        ))

    # 2. Optional solid backing plate
    if with_backing:
        z_center_back = z_tip + H_pillar + t_back / 2.0
        shapes.append(mp.Block(
            center=mp.Vector3(0.0, 0.0, z_center_back),
            size=mp.Vector3(L_plate, L_plate, t_back),
            material=pillar_material
        ))

    return shapes
