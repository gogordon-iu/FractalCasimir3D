#!/usr/bin/env python3
"""Export unsmoothed Meep material-grid meshes and clutch-pilot audit metrics."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import inspect
import json
import math
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import meep as mp
import numpy as np

from execution.run_scoped_clutch_meep import (
    cell_dimensions,
    parse_parameters,
    read_config,
    stress_faces,
)
from execution.clutch_geometry_redesign import (
    compute_dynamic_Trun,
    generate_redesigned_rotor_geometry,
    generate_redesigned_stator_geometry,
)
from utils.metrics_logger import export_macros, log_metric, log_step


CATEGORY_NAMES: dict[int, str] = {
    0: "Vacuum",
    1: "Stator_Membrane",
    2: "Stator_Landing_Pad",
    3: "Rotor_Teeth_Sector0",
    4: "Rotor_Teeth_Other",
}
MATERIALS: dict[str, tuple[tuple[float, float, float], float]] = {
    "Stator_Membrane": ((0.55, 0.62, 0.72), 1.0),
    "Stator_Landing_Pad": ((0.28, 0.35, 0.45), 1.0),
    "Rotor_Teeth_Sector0": ((0.95, 0.40, 0.12), 1.0),
    "Rotor_Teeth_Other": ((0.85, 0.72, 0.25), 1.0),
    "Stress_Box_Envelope": ((0.12, 0.65, 0.95), 0.15),
    "Zmin_Integration_Sheet": ((0.25, 0.95, 0.55), 0.35),
}


def fields(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise TypeError(f"{name} must be a real number, got {type(value).__name__}.")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise ValueError(f"Invalid {name}: {result!r}.")
    return result


def vector(value: Any, name: str) -> np.ndarray:
    if all(hasattr(value, axis) for axis in ("x", "y", "z")):
        items = [value.x, value.y, value.z]
    elif isinstance(value, Mapping) and all(axis in value for axis in ("x", "y", "z")):
        items = [value["x"], value["y"], value["z"]]
    else:
        items = value
    result = np.asarray(items, dtype=float)
    if result.shape != (3,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain three finite coordinates.")
    return result


def invoke(function: Callable[..., Any], context: Mapping[str, Any]) -> Any:
    """Bind repository helpers by their declared names; never guess argument order."""
    signature = inspect.signature(function)
    aliases = {
        "params": "parameters",
        "p": "parameters",
        "cfg": "config",
        "config_dict": "config",
        "meep": "mp",
        "meep_module": "mp",
        "theta": "theta_deg",
        "rotation_deg": "theta_deg",
        "rotation_angle_deg": "theta_deg",
        "sector": "sector_index",
        "sector_idx": "sector_index",
        "sector_id": "sector_index",
        "sectors": "sector_indices",
        "sector_ids": "sector_indices",
        "metal": "plate_material",
        "metal_material": "plate_material",
        "stator_material": "plate_material",
        "rotor_material": "tooth_material",
        "material": "plate_material",
        "air_material": "void_material",
        "vacuum_material": "void_material",
        "Trun": "T_run",
        "trun": "T_run",
        "dynamic_Trun": "T_run",
    }
    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        key = name if name in context else aliases.get(name, name)
        if key not in context:
            if parameter.default is not inspect.Parameter.empty:
                continue
            raise TypeError(
                f"Cannot bind required argument {name!r} of "
                f"{function.__module__}.{function.__name__}{signature}. "
                "Update the explicit helper adapter for this repository revision."
            )
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(context[key])
        else:
            keywords[name] = context[key]
    return function(*positional, **keywords)


def geometry_objects(value: Any) -> list[Any]:
    found: list[Any] = []

    def visit(item: Any) -> None:
        if isinstance(item, mp.GeometricObject):
            found.append(item)
        elif isinstance(item, Mapping):
            for key in ("geometry", "objects", "geometries"):
                if key in item:
                    visit(item[key])
                    return
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    if not found:
        raise ValueError("Geometry helper returned no Meep geometric objects.")
    if len({id(obj) for obj in found}) != len(found):
        raise ValueError("Geometry helper returned duplicate geometric objects.")
    return found


def build_geometry(
    parameters: Any, config: Any, theta_deg: float
) -> tuple[list[Any], list[dict[str, Any]], Any]:
    data = fields(parameters)
    elements = list(data["elements"])
    if not elements:
        raise ValueError("No rotor geometry or no sector-0 exact-area records.")
    num_sectors = finite_number(data["num_sectors"], "num_sectors", positive=True)
    if num_sectors != 4:
        raise ValueError("This exporter requires exactly four rotor sectors.")

    sector0_records = [fields(element) for element in elements]
    for index, record in enumerate(sector0_records):
        if "r_tooth_in" not in record or "r_tooth_out" not in record:
            raise ValueError(f"Element {index} lacks exact annular-tooth radii.")

    dynamic_trun = compute_dynamic_Trun(
        d_eff_um=max(0.010, finite_number(data["z_tip"], "z_tip", positive=True))
    )
    void = mp.Medium(epsilon=1.0)
    stator_material = mp.Medium(epsilon=3.0)
    other_material = mp.Medium(epsilon=4.0)
    sector0_material = mp.Medium(epsilon=5.0)

    stator = geometry_objects(
        generate_redesigned_stator_geometry(
            elements=elements,
            L_plate=data["l_domain"],
            t_membrane=data["t_membrane"],
            t_landing_pad=data["t_landing_pad"],
            plate_material=stator_material,
            void_material=void,
            num_sectors=data["num_sectors"],
            aperture_arc_deg=data["aperture_arc_deg"],
            bridge_arc_deg=data["bridge_arc_deg"],
        )
    )
    rotor = geometry_objects(
        generate_redesigned_rotor_geometry(
            elements=elements,
            H_teeth=data["h_teeth"],
            z_tip=data["z_tip"],
            rotor_material=other_material,
            num_sectors=data["num_sectors"],
            tooth_arc_deg=data["tooth_arc_deg"],
            theta_rotor_deg=theta_deg,
        )
    )
    if len(rotor) != 4 * len(elements):
        raise ValueError("Rotor geometry does not contain one tooth per element per sector.")

    # The helper emits sectors in order, with one prism per element in each sector.
    for index, obj in enumerate(rotor):
        obj.material = sector0_material if index < len(elements) else other_material

    return stator + rotor, sector0_records, dynamic_trun


def dimensions(value: Any) -> np.ndarray:
    data = fields(value)
    if data:
        if "cell_size" in data:
            return vector(data["cell_size"], "cell_size")
        for keys in (("Lx", "Ly", "Lz"), ("sx", "sy", "sz"), ("x", "y", "z")):
            if all(key in data for key in keys):
                return vector([data[key] for key in keys], "cell_dimensions")
    if isinstance(value, tuple) and value and hasattr(value[0], "x"):
        return vector(value[0], "cell_dimensions")
    return vector(value, "cell_dimensions")


def face_records(raw: Any) -> list[tuple[str, np.ndarray, np.ndarray]]:
    result: list[tuple[str, np.ndarray, np.ndarray]] = []

    def add(label: str, item: Any) -> None:
        data = fields(item)
        if data and "center" in data and "size" in data:
            name = str(data.get("name", data.get("label", data.get("face", label))))
            center = vector(data["center"], f"{name}.center")
            size = vector(data["size"], f"{name}.size")
        elif isinstance(item, (tuple, list)):
            parts = list(item)
            if parts and isinstance(parts[0], str):
                label = parts.pop(0)
            if len(parts) < 2:
                raise ValueError(f"Invalid stress face: {item!r}")
            name = label
            center = vector(parts[0], f"{name}.center")
            size = vector(parts[1], f"{name}.size")
        else:
            raise ValueError(f"Unsupported stress-face representation: {item!r}")
        if np.any(size < 0.0):
            raise ValueError("Stress face sizes cannot be negative.")
        result.append((name, center, size))

    if isinstance(raw, Mapping):
        if "faces" in raw:
            return face_records(raw["faces"])
        for label, item in raw.items():
            add(str(label), item)
    elif isinstance(raw, (list, tuple)):
        for index, item in enumerate(raw):
            add(str(index), item)
    else:
        raise TypeError("stress_faces must return a mapping or sequence of faces.")
    if len(result) != 6:
        raise ValueError(f"Expected six stress-box faces; received {len(result)}.")
    return result


def stress_bounds(
    raw: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    faces = face_records(raw)
    lower = np.min(np.asarray([c - s / 2.0 for _, c, s in faces]), axis=0)
    upper = np.max(np.asarray([c + s / 2.0 for _, c, s in faces]), axis=0)
    if np.any(upper <= lower):
        raise ValueError("Stress envelope must have positive extent on all axes.")
    zfaces = [
        (name, center, size)
        for name, center, size in faces
        if abs(float(size[2])) <= 1e-12 and size[0] > 0.0 and size[1] > 0.0
    ]
    if len(zfaces) != 2:
        raise ValueError("Expected exactly two lateral XY stress integration faces.")
    _, center, size = min(zfaces, key=lambda face: float(face[1][2]))
    xy_lower = center[:2] - size[:2] / 2.0
    xy_upper = center[:2] + size[:2] / 2.0
    area = finite_number(float(size[0] * size[1]), "zmin face area", positive=True)
    return lower, upper, xy_lower, xy_upper, area


def classify(
    epsilon: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    resolution: float,
    t_membrane: float,
) -> np.ndarray:
    categories = np.zeros(epsilon.shape, dtype=np.uint8)
    xx = x[:, None, None]
    yy = y[None, :, None]
    zz = z[None, None, :]
    boundary = -t_membrane - 0.5 / resolution
    solid = epsilon > 1.5
    # Spatial labels preserve sector-0 boundary voxels despite Yee-grid interpolation.
    rotor = solid & (zz > 0.0)
    quadrant1 = (xx > 0.0) & (yy > 0.0)
    categories[rotor & quadrant1] = 3
    categories[rotor & ~quadrant1] = 4
    categories[solid & (zz <= 0.0) & (zz >= boundary)] = 1
    categories[solid & (zz <= 0.0) & (zz < boundary)] = 2
    if np.any(solid & (categories == 0)):
        raise ValueError("Some non-vacuum voxels were not classified.")
    return categories


def write_mtl(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Classification colors; epsilon tags are not physical materials.\n")
        for name, (color, opacity) in MATERIALS.items():
            stream.write(
                f"\nnewmtl {name}\n"
                f"Ka {color[0]:.6g} {color[1]:.6g} {color[2]:.6g}\n"
                f"Kd {color[0]:.6g} {color[1]:.6g} {color[2]:.6g}\n"
                "Ks 0.05 0.05 0.05\n"
                f"d {opacity:.6g}\nillum 2\n"
            )


# Counterclockwise corner order, as viewed from outside each face.
FACE_CORNERS: tuple[tuple[int, int, tuple[tuple[int, int, int], ...]], ...] = (
    (0, 1, ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1))),
    (0, -1, ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1))),
    (1, 1, ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1))),
    (1, -1, ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1))),
    (2, 1, ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))),
    (2, -1, ((-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1))),
)


def write_quad(stream: TextIO, corners: np.ndarray, vertex_count: int) -> int:
    for point in corners:
        stream.write(f"v {point[0]:.17g} {point[1]:.17g} {point[2]:.17g}\n")
    stream.write(
        "f " + " ".join(str(vertex_count + offset) for offset in (1, 2, 3, 4)) + "\n"
    )
    return vertex_count + 4


def write_box(
    stream: TextIO,
    name: str,
    lower: np.ndarray,
    upper: np.ndarray,
    vertex_count: int,
) -> int:
    if not np.all(np.isfinite(lower)) or not np.all(np.isfinite(upper)):
        raise ValueError(f"Non-finite box coordinates for {name}.")
    if np.any(upper <= lower):
        raise ValueError(f"Degenerate box: {name}.")
    stream.write(f"\no {name}\nusemtl {name}\n")
    center = (lower + upper) / 2.0
    half = (upper - lower) / 2.0
    for _, _, signs in FACE_CORNERS:
        vertex_count = write_quad(
            stream, center + np.asarray(signs, dtype=float) * half, vertex_count
        )
    return vertex_count


def write_mesh(
    obj_path: Path,
    categories: np.ndarray,
    coordinates: tuple[np.ndarray, np.ndarray, np.ndarray],
    spacing: tuple[float, float, float],
    box_lower: np.ndarray,
    box_upper: np.ndarray,
    sheet_lower: np.ndarray,
    sheet_upper: np.ndarray,
) -> dict[str, int]:
    spacings = np.asarray(spacing, dtype=float)
    if (
        spacings.shape != (3,)
        or not np.all(np.isfinite(spacings))
        or np.any(spacings <= 0.0)
    ):
        raise ValueError("Voxel spacing must contain three positive finite values.")
    mtl_path = obj_path.with_suffix(".mtl")
    write_mtl(mtl_path)
    face_counts = {name: 0 for code, name in CATEGORY_NAMES.items() if code}
    vertex_count = 0

    with obj_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            "# Exact unsmoothed Meep epsilon samples represented by grid-cell cuboids.\n"
            "# Coordinates and lengths are in micrometers.\n"
            "# Only same-category internal faces are culled; material interfaces remain.\n"
            f"mtllib {mtl_path.name}\ns off\n"
        )
        for code in (1, 2, 3, 4):
            name = CATEGORY_NAMES[code]
            same_category = categories == code
            stream.write(f"\no {name}\nusemtl {name}\n")
            for axis, direction, signs in FACE_CORNERS:
                occupied_neighbor = np.zeros_like(same_category)
                destination = [slice(None)] * 3
                source = [slice(None)] * 3
                if direction > 0:
                    destination[axis] = slice(0, -1)
                    source[axis] = slice(1, None)
                else:
                    destination[axis] = slice(1, None)
                    source[axis] = slice(0, -1)
                occupied_neighbor[tuple(destination)] = same_category[tuple(source)]
                exposed = same_category & ~occupied_neighbor
                offsets = np.asarray(signs, dtype=float) * (spacings / 2.0)
                # Process one x-slab at a time to bound temporary index memory.
                for ix in range(categories.shape[0]):
                    indices = np.argwhere(exposed[ix])
                    face_counts[name] += int(len(indices))
                    for iy, iz in indices:
                        center = np.array(
                            [
                                coordinates[0][ix],
                                coordinates[1][iy],
                                coordinates[2][iz],
                            ]
                        )
                        vertex_count = write_quad(
                            stream, center + offsets, vertex_count
                        )
        vertex_count = write_box(
            stream, "Stress_Box_Envelope", box_lower, box_upper, vertex_count
        )
        vertex_count = write_box(
            stream,
            "Zmin_Integration_Sheet",
            sheet_lower,
            sheet_upper,
            vertex_count,
        )
    return {
        **{f"{name}_exterior_quads": count for name, count in face_counts.items()},
        "overlay_quads": 12,
        "obj_vertices": vertex_count,
        "obj_quads": sum(face_counts.values()) + 12,
    }


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_angle(parameters: Any, config: Any) -> float:
    for data in (fields(parameters), fields(config)):
        for key in ("theta_deg", "theta", "rotation_deg", "rotation_angle_deg"):
            if key in data:
                return finite_number(data[key], key)
        for key in ("parameters", "geometry", "rotor"):
            if key in data:
                nested = fields(data[key])
                for angle_key in ("theta_deg", "theta", "rotation_deg"):
                    if angle_key in nested:
                        return finite_number(nested[angle_key], angle_key)
    raise ValueError("Configuration does not expose its rotation angle in degrees.")


def export_config(config_path: Path, out_dir: Path) -> dict[str, Any]:
    config = read_config(config_path)
    parameters = parse_parameters(config, None, compute_dynamic_Trun)
    data = fields(parameters)
    config_data = fields(config)
    for required in ("t_membrane", "z_tip", "tooth_arc_deg"):
        if required not in data:
            raise ValueError(f"Parsed parameters lack required field {required!r}.")
    if "resolution" in data:
        resolution_value = data["resolution"]
    elif "resolution" in config_data:
        resolution_value = config_data["resolution"]
    else:
        raise ValueError("Configuration lacks required field 'resolution'.")
    resolution = finite_number(resolution_value, "resolution", positive=True)
    t_membrane = finite_number(data["t_membrane"], "t_membrane", positive=True)
    z_tip = finite_number(data["z_tip"], "z_tip", positive=True)
    tooth_arc = finite_number(data["tooth_arc_deg"], "tooth_arc_deg", positive=True)
    if tooth_arc > 360.0:
        raise ValueError("tooth_arc_deg cannot exceed 360 degrees.")
    theta = config_angle(parameters, config)
    cell = dimensions(cell_dimensions(parameters))
    if np.any(cell <= 0.0):
        raise ValueError("This exporter requires a positive three-dimensional cell.")
    box_lower, box_upper, xy_lower, xy_upper, box_area = stress_bounds(
        stress_faces(parameters)
    )
    zmin = z_tip / 2.0
    if not math.isclose(float(box_lower[2]), zmin, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("stress_faces zmin is inconsistent with parameters.z_tip / 2.")

    geometry, records, dynamic_trun = build_geometry(parameters, config, theta)
    exact_area = 0.0
    for index, record in enumerate(records):
        rin = finite_number(record["r_tooth_in"], f"tooth[{index}].r_tooth_in")
        rout = finite_number(record["r_tooth_out"], f"tooth[{index}].r_tooth_out")
        if rin < 0.0 or rout <= rin:
            raise ValueError(f"Invalid tooth radii in record {index}.")
        exact_area += 0.5 * (rout * rout - rin * rin) * math.radians(tooth_arc)
    exact_area = finite_number(exact_area, "sector0 exact area", positive=True)
    if exact_area > box_area * (1.0 + 1e-9):
        raise ValueError("Sector-0 exact tooth area exceeds its stress-box face area.")

    sim = mp.Simulation(
        cell_size=mp.Vector3(*cell.tolist()),
        dimensions=3,
        resolution=resolution,
        geometry=geometry,
        default_material=mp.Medium(epsilon=1.0),
        eps_averaging=False,
    )
    try:
        sim.init_sim()
        metadata = sim.get_array_metadata()
        if len(metadata) != 4:
            raise ValueError("Unexpected Meep array metadata format.")
        coordinates = tuple(np.asarray(axis, dtype=float) for axis in metadata[:3])
        spacing = 1.0 / resolution
        grid_spacings: list[float] = []
        for axis_name, axis in zip(("x", "y", "z"), coordinates):
            if axis.ndim != 1 or axis.size < 2 or not np.all(np.isfinite(axis)):
                raise ValueError(f"Invalid three-dimensional {axis_name} grid.")
            differences = np.diff(axis)
            axis_spacing = finite_number(
                float(np.mean(differences)), f"{axis_name} grid spacing", positive=True
            )
            if np.any(differences <= 0.0) or not np.allclose(
                differences, axis_spacing, rtol=1e-5, atol=1e-12
            ):
                raise ValueError(
                    f"{axis_name} metadata is not uniformly spaced; "
                    "refusing to fabricate voxel boundaries."
                )
            grid_spacings.append(axis_spacing)
        spacings = tuple(grid_spacings)
        epsilon = np.asarray(sim.get_epsilon(), dtype=float)
        shape = tuple(len(axis) for axis in coordinates)
        if epsilon.shape != shape:
            raise ValueError(
                f"Epsilon shape {epsilon.shape} does not match metadata {shape}."
            )
        if not np.all(np.isfinite(epsilon)):
            raise ValueError("Meep epsilon contains NaN or infinity.")
        # Centered samples interpolate Yee-grid tags even with eps_averaging=False.
        if not np.all((epsilon >= 0.999) & (epsilon <= 5.001)):
            raise ValueError("Meep returned epsilon values outside the tag range.")
        x, y, z = coordinates
        categories = classify(epsilon, x, y, z, resolution, t_membrane)
    finally:
        sim.reset_meep()

    inside_x = (x >= xy_lower[0]) & (x <= xy_upper[0])
    inside_y = (y >= xy_lower[1]) & (y <= xy_upper[1])
    column_count = int(np.count_nonzero(inside_x) * np.count_nonzero(inside_y))
    if column_count == 0:
        raise ValueError("The zmin lateral footprint contains no sampled XY columns.")
    stator_columns = np.any(
        ((categories == 1) | (categories == 2)) & (z[None, None, :] <= 0.0),
        axis=2,
    )
    metal_columns = int(np.count_nonzero(stator_columns[np.ix_(inside_x, inside_y)]))
    metal_fraction = metal_columns / column_count
    gap_mask = (z > 0.0) & (z < z_tip)
    pure_planes = np.all(categories == 0, axis=(0, 1))
    buffered_mask = (z > spacing) & (z < z_tip - spacing)

    metrics: dict[str, float | int] = {
        "theta_deg": theta,
        "resolution_pixels_per_um": resolution,
        "dx_nm": 1000.0 / resolution,
        "z_tip_nm": z_tip * 1000.0,
        "gap_in_voxels": z_tip * resolution,
        "zmin_in_voxels": zmin * resolution,
        "pure_vacuum_z_planes_in_gap": int(np.count_nonzero(gap_mask & pure_planes)),
        "z_grid_planes_strictly_in_gap": int(np.count_nonzero(gap_mask)),
        "z_planes_with_clear_1_voxel_buffer_from_both": int(
            np.count_nonzero(buffered_mask)
        ),
        "pure_vacuum_z_planes_with_clear_1_voxel_buffer_from_both": int(
            np.count_nonzero(buffered_mask & pure_planes)
        ),
        "stress_box_zmin_area_um2": box_area,
        "sector0_teeth_exact_area_um2": exact_area,
        "sector0_exact_area_element_count": len(records),
        "box_to_tooth_area_ratio": box_area / exact_area,
        "box_empty_area_fraction": 1.0 - exact_area / box_area,
        "stator_metal_fraction_under_box": metal_fraction,
        "stator_metal_area_under_box_um2": metal_fraction * box_area,
        "xy_columns_under_box": column_count,
        "stator_metal_columns_under_box": metal_columns,
        "total_voxels": int(categories.size),
        "grid_nx": len(x),
        "grid_ny": len(y),
        "grid_nz": len(z),
    }
    for code, name in CATEGORY_NAMES.items():
        metrics[f"{name}_voxel_count"] = int(np.count_nonzero(categories == code))

    label = f"{theta:g}".replace("-", "m").replace(".", "p")
    obj_path = out_dir / f"clutch_pilot_th{label}_voxels.obj"
    sheet_lower = np.array([xy_lower[0], xy_lower[1], zmin - 0.001])
    sheet_upper = np.array([xy_upper[0], xy_upper[1], zmin + 0.001])
    metrics.update(
        write_mesh(
            obj_path,
            categories,
            coordinates,
            spacings,
            box_lower,
            box_upper,
            sheet_lower,
            sheet_upper,
        )
    )
    for name, value in metrics.items():
        finite_number(value, name)

    return {
        "config_path": str(config_path),
        "config_sha256": file_hash(config_path),
        "theta_deg": theta,
        "metrics": metrics,
        "cell_size_um": cell.tolist(),
        "stress_box_lower_um": box_lower.tolist(),
        "stress_box_upper_um": box_upper.tolist(),
        "zmin_face_xy_lower_um": xy_lower.tolist(),
        "zmin_face_xy_upper_um": xy_upper.tolist(),
        "zmin_sheet_thickness_nm": 2.0,
        "gap_z_coordinates_um": z[gap_mask].tolist(),
        "pure_vacuum_gap_z_coordinates_um": z[gap_mask & pure_planes].tolist(),
        "one_voxel_buffer_gap_z_coordinates_um": z[buffered_mask].tolist(),
        "grid_metadata": {
            name: {
                "count": len(axis),
                "first_center_um": float(axis[0]),
                "last_center_um": float(axis[-1]),
                "spacing_um": axis_spacing,
            }
            for name, axis, axis_spacing in zip(
                ("x", "y", "z"), coordinates, spacings
            )
        },
        "epsilon_tag_histogram": {
            str(tag): int(np.count_nonzero(np.isclose(epsilon, tag, atol=1e-8, rtol=0)))
            for tag in (1.0, 3.0, 4.0, 5.0)
        },
        "dynamic_Trun": json_safe(dynamic_trun),
        "sector0_exact_area_records": [
            {
                key: json_safe(value)
                for key, value in record.items()
                if key not in ("geometry", "object", "tooth")
            }
            for record in records
        ],
        "outputs": {
            "obj": str(obj_path),
            "obj_sha256": file_hash(obj_path),
            "mtl": str(obj_path.with_suffix(".mtl")),
            "mtl_sha256": file_hash(obj_path.with_suffix(".mtl")),
        },
    }


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float, np.integer, np.floating)):
        finite_number(value, "JSON numeric value")
        return value.item() if isinstance(value, np.generic) else value
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if all(hasattr(value, key) for key in ("x", "y", "z")):
        return vector(value, "JSON vector").tolist()
    data = fields(value)
    if data:
        return json_safe(data)
    raise TypeError(f"Cannot serialize provenance value of type {type(value).__name__}.")


def log_audit(audit: Mapping[str, Any], provenance_path: Path) -> None:
    label = f"{audit['theta_deg']:g}".replace("-", "m").replace(".", "p")
    step = f"clutch_pilot_voxel_audit_th{label}"
    source = str(audit["config_path"])
    log_step(
        name=step,
        data={
            "message": f"Exported unsmoothed Meep Yee-grid audit at {audit['theta_deg']:g} deg",
            "description": f"Exact material-grid extraction from {source}",
            "details": {"config": source, "config_sha256": audit["config_sha256"]},
            "source": source,
        },
        metrics_path=str(provenance_path),
    )
    for name, value in audit["metrics"].items():
        log_metric(
            key=f"{step}_{name}",
            value=value,
            step_id=step,
            metrics_path=str(provenance_path),
        )


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configs",
        nargs="*",
        default=[
            "sweep_configs_clutch_pilot/config_001.json",
            "sweep_configs_clutch_pilot/config_003.json",
        ],
    )
    parser.add_argument("--out-dir", default="results_voxel_visualization")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Micro-probe compatibility flag; extraction initializes Meep but never time-steps.",
    )
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative.")
    if not args.configs:
        parser.error("--configs must contain at least one configuration.")
    if hasattr(mp, "count_processors") and mp.count_processors() != 1:
        raise RuntimeError("Run this exporter with one MPI process to avoid concurrent writes.")

    os.chdir(REPO_ROOT)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    results_dir = REPO_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    provenance_path = results_dir / "provenance_metrics.json"
    macros_path = results_dir / "macros_results.tex"

    audits: list[dict[str, Any]] = []
    seen_angles: set[float] = set()
    paths = [Path(path).expanduser().resolve() for path in args.configs]
    if len(set(paths)) != len(paths):
        parser.error("--configs contains duplicate paths.")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        audit = export_config(path, out_dir)
        angle = float(audit["theta_deg"])
        if angle in seen_angles:
            raise ValueError(f"Duplicate angle {angle:g} would overwrite an OBJ export.")
        seen_angles.add(angle)
        audits.append(audit)
        log_audit(audit, provenance_path)

    export_macros(
        metrics_path=str(provenance_path),
        output_path=str(macros_path),
    )
    for path in (provenance_path, macros_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"metrics_logger did not produce a non-empty file: {path}")
    with provenance_path.open(encoding="utf-8") as stream:
        logged_payload = json.load(stream)
    serialized_metrics = json.dumps(logged_payload, allow_nan=False)
    for audit in audits:
        label = f"{audit['theta_deg']:g}".replace("-", "m").replace(".", "p")
        for name in audit["metrics"]:
            metric_name = f"clutch_pilot_voxel_audit_th{label}_{name}"
            if metric_name not in serialized_metrics:
                raise RuntimeError(f"Provenance logger did not persist metric {metric_name}.")

    summary_path = out_dir / "clutch_pilot_voxel_audit.json"
    summary = {
        "schema_version": 1,
        "repository_root": str(REPO_ROOT),
        "meep_version": str(getattr(mp, "__version__", "not exposed by Meep")),
        "numpy_version": np.__version__,
        "coordinate_units": "um",
        "classification_epsilon_tags": {
            "vacuum": 1.0,
            "stator": 3.0,
            "rotor_sector0": 5.0,
            "rotor_sectors1_to3": 4.0,
        },
        "category_names": CATEGORY_NAMES,
        "eps_averaging": False,
        "time_steps_executed": 0,
        "requested_max_steps": args.max_steps,
        "mesh_convention": (
            "Axis-aligned cuboids centered on get_array_metadata coordinates with "
            "edge lengths equal to the actual per-axis metadata grid spacings. "
            "Faces adjoining a voxel of the same category are culled; interfaces "
            "between different solid categories are retained for closed category surfaces. "
            "No interpolated isosurface or epsilon smoothing is used."
        ),
        "audit_conventions": {
            "gap_planes": "Strict inequalities: 0 < z < z_tip.",
            "pure_vacuum_plane": "Every sampled XY voxel on the plane is category 0.",
            "one_voxel_buffer": "Strict inequalities: 1/resolution < z < z_tip-1/resolution.",
            "stator_under_box": (
                "Inclusive zmin-face lateral center bounds; a column is metal if "
                "any category-1 or category-2 sample at z <= 0 exists."
            ),
            "box_empty_area_fraction": (
                "Analytic area ratio, not a rasterized union or voxel occupancy fraction."
            ),
            "epsilon_tags": (
                "Artificial isotropic labels for classification only; not physical "
                "permittivities and not a Casimir-force simulation."
            ),
        },
        "provenance": {
            "metrics_json": str(provenance_path),
            "metrics_json_sha256": file_hash(provenance_path),
            "macros_tex": str(macros_path),
            "macros_tex_sha256": file_hash(macros_path),
        },
        "configs": audits,
    }
    atomic_json(summary_path, summary)
    print(f"Exported {len(audits)} configuration(s); audit: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
