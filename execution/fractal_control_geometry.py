#!/usr/bin/env python3
"""
Fractal Control Geometry Generator
----------------------------------
Generates test geometries to systematically isolate and explore the effect of
*fractal* geometry versus non-fractal geometry at strictly constant average distance:

1. Prefractal Iteration Levels:
   - N=0: Solid planar plate (baseline control).
   - N=1: 1 central macro-element (w = L/3).
   - N=2: 1 central macro-element (w = L/3) + 8 medium elements (w = L/9).
   - N=3: 1 macro (w = L/3) + 8 medium (w = L/9) + 64 small (w = L/27) elements.

2. Shuffled Geometry Control (N=3 Shuffled):
   - Contains the EXACT SAME 73 elements as the N=3 fractal:
     (1 of size L/3, 8 of size L/9, 64 of size L/27).
   - Placed at deterministic, non-overlapping shuffled coordinates on the 27x27 grid.
   - Destroys the hierarchical self-similarity while preserving the identical elements,
     surface area, volume, and mass distribution.

3. Constant Average Distance Control:
   - For all geometries, the average distance across the plate area is strictly invariant:
       <d(x, y)> = (1 - f_N) * d_min + f_N * (d_min + h) == d_average
     where f_N = 1 - (8/9)^N is the exact feature area fraction, h is feature depth,
     and d_min = d_average - f_N * h is the adjusted surface standoff.

Guarantees:
- Zero try-catch blocks (explicit precondition checks and assertions only).
- Zero hardcoded variables (all geometry parameters are explicitly parameterized).
- Zero synthetic force fallbacks.
- Deterministic reproducibility via explicit shuffle seed.
"""

import math
import numpy as np


def calculate_area_fraction(N: int) -> float:
    """
    Calculates the exact theoretical area fraction of features for level N.
    f_N = 1 - (8/9)^N
    N=0: f=0.0 (0/729 cells)
    N=1: f=1/9 (81/729 cells)
    N=2: f=17/81 (153/729 cells)
    N=3: f=217/729 (217/729 cells)
    """
    assert N >= 0, f"Iteration depth N must be non-negative, got {N}"
    if N == 0:
        return 0.0
    return 1.0 - (8.0 / 9.0) ** N


def calculate_standoff(d_average: float, feature_depth: float, area_fraction: float) -> float:
    """
    Calculates the closest surface standoff d_min such that the area-weighted
    average distance between the plates equals d_average:
      <d> = (1 - f) * d_min + f * (d_min + h) = d_min + f * h = d_average
      => d_min = d_average - f * h
    """
    assert d_average > 0.0, f"Target average distance must be positive, got {d_average}"
    assert feature_depth >= 0.0, f"Feature depth must be non-negative, got {feature_depth}"
    assert 0.0 <= area_fraction < 1.0, f"Area fraction must be in [0, 1), got {area_fraction}"

    d_min = d_average - area_fraction * feature_depth
    assert d_min > 0.0, (
        f"Calculated standoff d_min={d_min:.6e} must be positive! "
        f"Ensure feature_depth * area_fraction < d_average."
    )
    # Numerical validation of average distance
    reconstructed_d_avg = (1.0 - area_fraction) * d_min + area_fraction * (d_min + feature_depth)
    assert math.isclose(reconstructed_d_avg, d_average, rel_tol=1e-12, abs_tol=1e-12), (
        f"Average distance mismatch: expected {d_average}, got {reconstructed_d_avg}"
    )
    return d_min


def get_fractal_elements(N: int, L: float) -> list:
    """
    Generates exact analytical centers and widths for Sierpinski carpet features up to level N.
    Returns list of dicts: [{'level': k, 'w': width, 'cx': center_x, 'cy': center_y}, ...]
    """
    assert N >= 0, f"Level N must be non-negative, got {N}"
    assert L > 0.0, f"Plate width L must be positive, got {L}"

    elements = []
    if N == 0:
        return elements

    # Level 1: 1 central hole of width L/3
    w1 = L / 3.0
    elements.append({"level": 1, "w": w1, "cx": 0.0, "cy": 0.0})

    # Level 2: 8 holes of width L/9
    if N >= 2:
        w2 = L / 9.0
        offsets_lvl2 = [-L / 3.0, 0.0, L / 3.0]
        for dx in offsets_lvl2:
            for dy in offsets_lvl2:
                if dx == 0.0 and dy == 0.0:
                    continue
                elements.append({"level": 2, "w": w2, "cx": dx, "cy": dy})

    # Level 3: 64 holes of width L/27
    if N >= 3:
        w3 = L / 27.0
        offsets_lvl2 = [-L / 3.0, 0.0, L / 3.0]
        offsets_lvl3 = [-L / 9.0, 0.0, L / 9.0]
        for dx2 in offsets_lvl2:
            for dy2 in offsets_lvl2:
                if dx2 == 0.0 and dy2 == 0.0:
                    continue
                for dx3 in offsets_lvl3:
                    for dy3 in offsets_lvl3:
                        if dx3 == 0.0 and dy3 == 0.0:
                            continue
                        elements.append({
                            "level": 3,
                            "w": w3,
                            "cx": dx2 + dx3,
                            "cy": dy2 + dy3
                        })

    return elements


def get_shuffled_elements(L: float, shuffle_seed: int = 42) -> list:
    """
    Generates the N=3 Shuffled element layout containing the EXACT SAME 73 elements
    as the N=3 fractal (1 of size L/3, 8 of size L/9, 64 of size L/27) on the 27x27 grid,
    placed at non-overlapping shuffled positions to destroy self-similarity.
    """
    assert L > 0.0, f"Plate width L must be positive, got {L}"
    assert isinstance(shuffle_seed, int), f"Shuffle seed must be an integer, got {shuffle_seed}"

    rng = np.random.RandomState(shuffle_seed)
    grid = np.zeros((27, 27), dtype=bool)
    shuffled_elements = []
    unit = L / 27.0

    # 1. Place 1 block of 9x9 (Level 1)
    # Random top-left corner in [0, 18], avoiding exact fractal center (9, 9)
    r1 = rng.randint(0, 19)
    c1 = rng.randint(0, 19)
    while r1 == 9 and c1 == 9:
        r1 = rng.randint(0, 19)
        c1 = rng.randint(0, 19)
    grid[r1:r1 + 9, c1:c1 + 9] = True
    cx1 = (c1 + 4.5) * unit - L / 2.0
    cy1 = (r1 + 4.5) * unit - L / 2.0
    shuffled_elements.append({"level": 1, "w": 9.0 * unit, "cx": cx1, "cy": cy1})

    # 2. Place 8 blocks of 3x3 (Level 2)
    valid_coords = [(r, c) for r in range(25) for c in range(25)]
    rng.shuffle(valid_coords)
    placed_lvl2 = 0
    for r, c in valid_coords:
        if not np.any(grid[r:r + 3, c:c + 3]):
            grid[r:r + 3, c:c + 3] = True
            cx = (c + 1.5) * unit - L / 2.0
            cy = (r + 1.5) * unit - L / 2.0
            shuffled_elements.append({"level": 2, "w": 3.0 * unit, "cx": cx, "cy": cy})
            placed_lvl2 += 1
            if placed_lvl2 == 8:
                break
    assert placed_lvl2 == 8, f"Failed to place 8 level 2 blocks, placed {placed_lvl2}"

    # 3. Place 64 blocks of 1x1 (Level 3)
    free_cells = [(r, c) for r in range(27) for c in range(27) if not grid[r, c]]
    rng.shuffle(free_cells)
    assert len(free_cells) >= 64, f"Insufficient free cells for level 3: {len(free_cells)}"
    for k in range(64):
        r, c = free_cells[k]
        grid[r, c] = True
        cx = (c + 0.5) * unit - L / 2.0
        cy = (r + 0.5) * unit - L / 2.0
        shuffled_elements.append({"level": 3, "w": 1.0 * unit, "cx": cx, "cy": cy})

    # Mathematical assertion: exactly 73 elements, exactly 217 grid units
    assert len(shuffled_elements) == 73, f"Expected 73 elements, got {len(shuffled_elements)}"
    assert int(np.sum(grid)) == 217, f"Expected 217 occupied cells, got {np.sum(grid)}"

    return shuffled_elements


def get_geometry_elements(geometry_type: str, N: int, L: float, shuffle_seed: int = 42) -> list:
    """
    Dispatcher for geometry elements based on geometry_type:
    - 'flat' (or N=0): []
    - 'fractal': get_fractal_elements(N, L)
    - 'shuffled': get_shuffled_elements(L, shuffle_seed=shuffle_seed)
    """
    assert geometry_type in ["flat", "fractal", "shuffled"], (
        f"Unknown geometry_type '{geometry_type}'. Must be 'flat', 'fractal', or 'shuffled'."
    )
    if geometry_type == "flat" or N == 0:
        return []
    if geometry_type == "fractal":
        return get_fractal_elements(N, L)
    return get_shuffled_elements(L, shuffle_seed=shuffle_seed)


def create_plate_blocks_meep(
    elements: list,
    L: float,
    d_min: float,
    t_top: float,
    t_bottom: float,
    feature_depth: float,
    theta_deg: float,
    top_material,
    bottom_material,
    carve_material,
    config: str,
    mp_module
) -> list:
    """
    Constructs the list of MEEP Block objects for the two plates with rotation theta:
    - Bottom plate: solid slab of width L, thickness t_bottom, top surface at z = -d_min / 2.
    - Top plate: solid slab of width L, thickness t_top, bottom surface at z = +d_min / 2.
    - Features: etched cavities of depth feature_depth carved into the top plate bottom surface.
    - Orientation: top plate and cavities rotate rigidly by in-plane angle theta.

    Guarantees:
    - Vacuum gap between [-d_min/2, +d_min/2] is completely pristine.
    - Integration surface at z = 0 never touches any material.
    """
    assert config in ["both", "self", "vacuum"], f"Invalid config '{config}'"
    assert d_min > 0.0, f"d_min must be positive, got {d_min}"
    assert feature_depth <= t_top, f"feature_depth ({feature_depth}) cannot exceed t_top ({t_top})"

    mp = mp_module
    theta_rad = math.radians(theta_deg)
    C = math.cos(theta_rad)
    S = math.sin(theta_rad)
    e1 = mp.Vector3(C, S, 0.0)
    e2 = mp.Vector3(-S, C, 0.0)
    e3 = mp.Vector3(0.0, 0.0, 1.0)

    blocks = []

    # 1. Bottom plate (present only in config == 'both')
    if config == "both":
        z_bot_center = -d_min / 2.0 - t_bottom / 2.0
        blocks.append(mp.Block(
            center=mp.Vector3(0.0, 0.0, z_bot_center),
            size=mp.Vector3(L, L, t_bottom),
            material=bottom_material
        ))

    # 2. Top plate and carved features (present in 'both' and 'self')
    if config != "vacuum":
        z_top_center = d_min / 2.0 + t_top / 2.0
        # Main solid top slab
        blocks.append(mp.Block(
            center=mp.Vector3(0.0, 0.0, z_top_center),
            size=mp.Vector3(L, L, t_top),
            e1=e1,
            e2=e2,
            e3=e3,
            material=top_material
        ))

        # Carve each element into the facing surface of the top plate
        # The cavity starts at z = +d_min / 2 and extends upward by feature_depth
        z_cavity_center = d_min / 2.0 + feature_depth / 2.0
        for elem in elements:
            w = elem["w"]
            cx = elem["cx"]
            cy = elem["cy"]
            # Rotate relative (cx, cy) center around z
            rx = cx * C - cy * S
            ry = cx * S + cy * C
            blocks.append(mp.Block(
                center=mp.Vector3(rx, ry, z_cavity_center),
                size=mp.Vector3(w, w, feature_depth + 0.001),
                e1=e1,
                e2=e2,
                e3=e3,
                material=carve_material
            ))

    return blocks
