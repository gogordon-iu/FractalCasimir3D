#!/usr/bin/env python3
"""
execution/casimir_bem_solver.py

Surface discretization, dense imaginary-frequency tangential-vector dyadic
and legacy scalar Yukawa BEM models, and a SCUFF-EM adapter for the concentric
clutch geometry.

IMPORTANT PHYSICS QUALIFICATION
------------------------------
The vector_dyadic formulation uses two tangential surface-current components
per panel and a regularized electromagnetic dyadic cross coupling. Its
single-layer self operator and scaled cross coupling are an approximate
model, not the complete Maxwell FSC/PMCHWT equations for dielectric bodies.
The legacy scalar_yukawa formulation is also an explicitly approximate model.
Neither formulation is advertised as an exact electromagnetic FSC solver.
Results requiring first-principles electromagnetic physics must use --solver
scuff.

The geometry is shared by both backends. It contains four physical sectors,
not artificial conducting symmetry-plane walls. The BEM evaluates all four
cyclic symmetry blocks, including interactions with the other sectors.
SCUFF receives the complete, closed, four-sector triangular surfaces.

Geometry inputs must supply the actual track elements, directly or through
execution.clutch_geometry_redesign. No guessed Cantor construction is used.
All lengths and imaginary wavenumbers are in micrometres and um^-1.

Dependencies:
    numpy, scipy
    torch                 optional CUDA backend
    utils.metrics_logger  project provenance integration
    scuff-cas3d            required for the scuff backend
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Callable, Literal, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray
from scipy import linalg

FloatArray: TypeAlias = NDArray[np.float64]
ComplexArray: TypeAlias = NDArray[np.complex128]
Formulation: TypeAlias = Literal["vector_dyadic", "scalar_yukawa"]
PanelType: TypeAlias = Literal[
    "rotor_bottom",
    "rotor_top",
    "rotor_radial_wall",
    "rotor_azimuthal_wall",
    "stator_top",
    "stator_bottom",
    "stator_radial_wall",
    "stator_azimuthal_wall",
]

MEEP_FORCE_TO_SI = 3.16152649e-14
SYMMETRY_MULTIPLIER = 4.0
SCALAR_MODEL = "dielectric_weighted_two_channel_scalar_yukawa"
VECTOR_MODEL = "dielectric_weighted_tangential_vector_dyadic"
PHYSICS_QUALIFICATION = (
    "Panel-collocation scalar Yukawa BEM with dielectric-weighted channels; "
    "not an exact vector electromagnetic FSC/PMCHWT calculation. "
    "Use SCUFF-EM for electromagnetic results."
)
VECTOR_PHYSICS_QUALIFICATION = (
    "Two-component tangential surface-current BEM with regularized dyadic "
    "cross coupling, scaled cross interactions, and single-layer self operators; "
    "an approximate model, not the complete electromagnetic FSC/PMCHWT equations. "
    "Use SCUFF-EM for first-principles electromagnetic results."
)


def _formulation_qualification(formulation: Formulation) -> str:
    if formulation == "vector_dyadic":
        return VECTOR_PHYSICS_QUALIFICATION
    if formulation == "scalar_yukawa":
        return PHYSICS_QUALIFICATION
    raise ValueError("formulation must be vector_dyadic or scalar_yukawa.")


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a real number, not bool.")
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError(f"{name} must be a real number; got {type(value).__name__}.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _positive_float(value: Any, name: str, *, allow_zero: bool = False) -> float:
    result = _finite_float(value, name)
    if result < 0.0 or (result == 0.0 and not allow_zero):
        raise ValueError(f"{name} must be {'nonnegative' if allow_zero else 'positive'}.")
    return result


def _integer(value: Any, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer.")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return result


def _plain(value: Any) -> Any:
    """Convert project objects to strictly JSON-serializable values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        return _finite_float(value, "serialized float")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "__dict__"):
        return {
            k: _plain(v)
            for k, v in vars(value).items()
            if not k.startswith("_") and not callable(v)
        }
    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    converted = _plain(value)
    if not isinstance(converted, dict):
        raise TypeError(f"{name} must be a mapping or a parameter object.")
    return cast(dict[str, Any], converted)


def _pick(
    data: Mapping[str, Any],
    names: Sequence[str],
    *,
    default: Any = None,
    required: bool = True,
) -> Any:
    matches = [(name, data[name]) for name in names if name in data]
    if not matches:
        if required:
            raise ValueError(f"Missing required parameter: {' / '.join(names)}.")
        return default
    first_name, first_value = matches[0]
    for other_name, other_value in matches[1:]:
        if _plain(first_value) != _plain(other_value):
            raise ValueError(f"Conflicting aliases {first_name!r} and {other_name!r}.")
    return first_value


def _configuration(parameters: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    config = _mapping(parameters, "parameters/config")
    nested = config.get("parameters", config.get("params"))
    values = _mapping(nested, "nested parameters") if nested is not None else dict(config)
    for key in (
        "elements",
        "theta_deg",
        "N_fractal",
        "material",
        "temperature_K",
        "R_min",
        "R_max",
        "r_min",
        "r_max",
        "R_min_um",
        "R_max_um",
        "r_min_um",
        "r_max_um",
        "z_tip",
        "z_tip_um",
        "h_teeth",
        "H_teeth_um",
        "H_teeth",
        "t_membrane",
        "t_membrane_um",
        "t_landing_pad",
        "t_landing_pad_um",
        "geometry",
    ):
        if key in config and key not in values:
            values[key] = config[key]
    geometry = values.get("geometry")
    if isinstance(geometry, Mapping):
        for key, value in geometry.items():
            values.setdefault(str(key), value)
    if values.get("elements") is None and isinstance(geometry, (list, tuple)):
        values["elements"] = geometry
    return config, values


@dataclasses.dataclass(frozen=True)
class TrackElement:
    r_inner: float
    r_outer: float
    r_tooth_in: float
    r_tooth_out: float


@dataclasses.dataclass(frozen=True)
class Geometry:
    R_min: float
    R_max: float
    z_tip: float
    h_teeth: float
    t_membrane: float
    t_landing_pad: float
    theta_deg: float
    tooth_arc_deg: float
    aperture_arc_deg: float
    elements: tuple[TrackElement, ...]


@dataclasses.dataclass(frozen=True)
class SurfacePanel:
    vertices: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    centroid: tuple[float, float, float]
    normal: tuple[float, float, float]
    area: float
    panel_type: PanelType
    body: Literal["rotor", "stator"]


@dataclasses.dataclass(frozen=True)
class BodyPanels:
    centroids: FloatArray
    normals: FloatArray
    areas: FloatArray
    panel_types: tuple[PanelType, ...]
    # The defaults preserve construction by legacy callers without vertices.
    tangents: FloatArray = dataclasses.field(
        default_factory=lambda: np.empty((0, 2, 3), dtype=np.float64)
    )
    quad_points: FloatArray = dataclasses.field(
        default_factory=lambda: np.empty((0, 4, 3), dtype=np.float64)
    )
    quad_weights: FloatArray = dataclasses.field(
        default_factory=lambda: np.full(4, 0.25, dtype=np.float64)
    )

    def __post_init__(self) -> None:
        if self.tangents.shape == (0, 2, 3) and self.count:
            normals = np.asarray(self.normals, dtype=np.float64)
            if normals.shape != (self.count, 3) or not np.isfinite(normals).all():
                raise ValueError("Panel normals must have shape (N, 3) and be finite.")
            lengths = np.linalg.norm(normals, axis=1)
            if not np.allclose(lengths, 1.0, rtol=1.0e-10, atol=1.0e-12):
                raise ValueError("Panel normals must be unit vectors.")
            axes = np.eye(3)[np.argmin(np.abs(normals), axis=1)]
            t1 = axes - np.sum(axes * normals, axis=1)[:, None] * normals
            t1 /= np.linalg.norm(t1, axis=1)[:, None]
            object.__setattr__(
                self, "tangents", np.stack((t1, np.cross(normals, t1)), axis=1)
            )
        if self.tangents.shape != (self.count, 2, 3):
            raise ValueError("Panel tangents must have shape (N, 2, 3).")
        if not np.isfinite(self.tangents).all():
            raise ValueError("Panel tangents must be finite.")
        gram = np.einsum("ima,ina->imn", self.tangents, self.tangents)
        if not np.allclose(gram, np.eye(2), rtol=1.0e-10, atol=1.0e-12):
            raise ValueError("Panel tangents must be orthonormal.")
        if not np.allclose(
            np.einsum("ima,ia->im", self.tangents, self.normals),
            0.0,
            atol=1.0e-12,
        ):
            raise ValueError("Panel tangents must be perpendicular to the normals.")
        if self.quad_points.shape == (0, 4, 3) and self.count:
            centroids = np.asarray(self.centroids, dtype=np.float64)
            if centroids.shape != (self.count, 3):
                raise ValueError("Panel centroids must have shape (N, 3).")
            object.__setattr__(
                self, "quad_points", np.repeat(centroids[:, None, :], 4, axis=1)
            )
        if self.quad_points.shape != (self.count, 4, 3):
            raise ValueError("Panel quadrature points must have shape (N, 4, 3).")
        if not np.isfinite(self.quad_points).all():
            raise ValueError("Panel quadrature points must be finite.")
        if self.quad_weights.shape != (4,):
            raise ValueError("Panel quadrature weights must have shape (4,).")
        if (
            not np.isfinite(self.quad_weights).all()
            or np.any(self.quad_weights < 0.0)
            or not math.isclose(
                float(np.sum(self.quad_weights)), 1.0,
                rel_tol=1.0e-12, abs_tol=1.0e-12,
            )
        ):
            raise ValueError(
                "Panel quadrature weights must be finite, nonnegative, and sum to one."
            )

    @property
    def count(self) -> int:
        return int(self.areas.size)


@dataclasses.dataclass(frozen=True)
class ClutchSurfaceMesh:
    rotor: tuple[SurfacePanel, ...]
    stator: tuple[SurfacePanel, ...]
    geometry: Geometry
    parameters: dict[str, Any]
    config: dict[str, Any]
    panel_resolution: dict[str, int]
    symmetry_multiplier: float = SYMMETRY_MULTIPLIER

    @property
    def n_panels_rotor(self) -> int:
        """Number of actual physical rotor panels over all four sectors."""
        return 4 * len(self.rotor)

    @property
    def n_panels_stator(self) -> int:
        return 4 * len(self.stator)

    @property
    def n_panels_total(self) -> int:
        return self.n_panels_rotor + self.n_panels_stator

    def sector_arrays(self, body: Literal["rotor", "stator"]) -> BodyPanels:
        panels = self.rotor if body == "rotor" else self.stator
        if not panels:
            raise ValueError(f"The {body} mesh is empty.")
        normals = np.asarray([p.normal for p in panels], dtype=np.float64)
        vertices = np.asarray([p.vertices for p in panels], dtype=np.float64)
        edges = vertices[:, 1] - vertices[:, 0]
        t1 = edges - np.sum(edges * normals, axis=1)[:, None] * normals
        lengths = np.linalg.norm(t1, axis=1)
        if not np.isfinite(lengths).all() or np.any(lengths <= 0.0):
            raise ValueError("Cannot construct panel tangent basis from its vertices.")
        t1 /= lengths[:, None]
        tangents = np.stack((t1, np.cross(normals, t1)), axis=1)
        s = (1.0 - 1.0 / math.sqrt(3.0)) / 2.0
        nodes = (s, 1.0 - s)
        quad_points = np.stack(
            [
                (1.0 - u) * (1.0 - v) * vertices[:, 0]
                + u * (1.0 - v) * vertices[:, 1]
                + u * v * vertices[:, 2]
                + (1.0 - u) * v * vertices[:, 3]
                for u in nodes
                for v in nodes
            ],
            axis=1,
        )
        return BodyPanels(
            np.asarray([p.centroid for p in panels], dtype=np.float64),
            normals,
            np.asarray([p.area for p in panels], dtype=np.float64),
            tuple(p.panel_type for p in panels),
            tangents,
            quad_points=quad_points,
            quad_weights=np.full(4, 0.25, dtype=np.float64),
        )


def _project_elements(values: dict[str, Any], original: Any) -> Any:
    """
    Resolve explicit project-generated elements without inventing geometry.

    Supported public geometry factories return either an object/dictionary
    containing 'elements', or the element sequence itself.
    """
    direct = values.get("elements")
    if direct is None and isinstance(values.get("geometry"), (list, tuple)):
        direct = values["geometry"]
        values["elements"] = direct
    if direct is not None:
        return direct

    module_name = "execution.clutch_geometry_redesign"
    if importlib.util.find_spec(module_name) is None:
        raise RuntimeError(
            "Track elements are absent and execution.clutch_geometry_redesign "
            "is unavailable. Supply exact 'elements' in the configuration."
        )
    module = importlib.import_module(module_name)
    parameter_object = original
    cls = getattr(module, "Parameters", None)
    if isinstance(original, Mapping) and callable(cls):
        signature = inspect.signature(cls)
        kwargs = {
            key: value
            for key, value in values.items()
            if key in signature.parameters
            and signature.parameters[key].kind
            in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        try:
            signature.bind(**kwargs)
        except TypeError as error:
            raise RuntimeError(
                "Cannot construct clutch_geometry_redesign.Parameters from this "
                "configuration. Supply explicit track elements."
            ) from error
        parameter_object = cls(**kwargs)

    embedded = getattr(parameter_object, "elements", None)
    if embedded is not None:
        return embedded() if callable(embedded) else embedded

    factory_names = (
        "get_track_elements",
        "build_track_elements",
        "generate_track_elements",
        "compute_track_elements",
        "build_elements",
        "generate_elements",
        "build_clutch_geometry",
        "build_geometry",
        "compute_geometry",
        "derive_geometry",
        "get_geometry",
    )
    for name in factory_names:
        factory = getattr(module, name, None)
        if not callable(factory):
            continue
        signature = inspect.signature(factory)
        candidates = (
            ((parameter_object,), {}),
            ((), {"parameters": parameter_object}),
            ((), {"params": parameter_object}),
        )
        for args, kwargs in candidates:
            try:
                signature.bind(*args, **kwargs)
            except TypeError:
                continue
            result = factory(*args, **kwargs)
            if isinstance(result, Mapping) and "elements" in result:
                return result["elements"]
            if hasattr(result, "elements"):
                return getattr(result, "elements")
            if isinstance(result, (list, tuple)) and result:
                first = result[0]
                if isinstance(first, Mapping) and "r_inner" in first:
                    return result
            raise RuntimeError(
                f"{module_name}.{name} did not return identifiable track elements. "
                "Supply the exact elements explicitly."
            )
    raise RuntimeError(
        "No supported project geometry factory exposes track elements. "
        "Supply 'elements' with r_inner, r_outer, r_tooth_in, and r_tooth_out."
    )


def _read_geometry(parameters: Any) -> tuple[Geometry, dict[str, Any], dict[str, Any]]:
    config, values = _configuration(parameters)
    raw_elements = _project_elements(values, parameters)
    if not isinstance(raw_elements, Sequence) or isinstance(raw_elements, (str, bytes)):
        raise TypeError("'elements' must be a nonempty sequence.")
    if not raw_elements:
        raise ValueError("'elements' cannot be empty.")

    elements: list[TrackElement] = []
    for index, raw in enumerate(raw_elements):
        data = _mapping(raw, f"elements[{index}]")
        element = TrackElement(
            _positive_float(_pick(data, ("r_inner",)), "r_inner"),
            _positive_float(_pick(data, ("r_outer",)), "r_outer"),
            _positive_float(_pick(data, ("r_tooth_in",)), "r_tooth_in"),
            _positive_float(_pick(data, ("r_tooth_out",)), "r_tooth_out"),
        )
        if not element.r_inner < element.r_outer:
            raise ValueError(f"Element {index} has an invalid radial slot.")
        if not element.r_tooth_in < element.r_tooth_out:
            raise ValueError(f"Element {index} has an invalid rotor tooth.")
        elements.append(element)
    elements.sort(key=lambda e: e.r_inner)
    for previous, current in zip(elements, elements[1:]):
        if previous.r_outer >= current.r_inner:
            raise ValueError("Radial slots must be disjoint with nonzero intervening rings.")

    geometry = Geometry(
        R_min=_positive_float(
            _pick(
                values, ("R_min", "r_min", "R_min_um", "r_min_um"),
                required=False, default=0.30,
            ),
            "R_min",
        ),
        R_max=_positive_float(
            _pick(
                values, ("R_max", "r_max", "R_max_um", "r_max_um"),
                required=False, default=1.35,
            ),
            "R_max",
        ),
        z_tip=_finite_float(_pick(values, ("z_tip", "z_tip_um")), "z_tip"),
        h_teeth=_positive_float(
            _pick(values, ("h_teeth", "H_teeth_um", "H_teeth")), "h_teeth"
        ),
        t_membrane=_positive_float(
            _pick(values, ("t_membrane", "t_membrane_um")), "t_membrane"
        ),
        t_landing_pad=_positive_float(
            _pick(values, ("t_landing_pad", "t_landing_pad_um")),
            "t_landing_pad", allow_zero=True,
        ),
        theta_deg=_finite_float(
            _pick(values, ("theta_deg",), required=False, default=0.0), "theta_deg"
        ),
        tooth_arc_deg=_positive_float(
            _pick(values, ("tooth_arc_deg",), required=False, default=15.0),
            "tooth_arc_deg",
        ),
        aperture_arc_deg=_positive_float(
            _pick(values, ("aperture_arc_deg",), required=False, default=30.0),
            "aperture_arc_deg",
        ),
        elements=tuple(elements),
    )
    if not geometry.R_min < geometry.R_max:
        raise ValueError("R_min must be smaller than R_max.")
    if not 0.0 < geometry.tooth_arc_deg < 90.0:
        raise ValueError("tooth_arc_deg must lie strictly between 0 and 90 degrees.")
    if not 0.0 < geometry.aperture_arc_deg < 90.0:
        raise ValueError("aperture_arc_deg must lie strictly between 0 and 90 degrees.")
    for element in geometry.elements:
        if not geometry.R_min <= element.r_inner < element.r_outer <= geometry.R_max:
            raise ValueError("Every stator slot must lie inside [R_min, R_max].")

    center_deg = (15.0 + geometry.theta_deg % 90.0) % 90.0
    phi_min = center_deg - geometry.tooth_arc_deg / 2.0
    phi_max = center_deg + geometry.tooth_arc_deg / 2.0
    inside_aperture = 0.0 < phi_min and phi_max < geometry.aperture_arc_deg
    inside_slots = all(
        e.r_inner <= e.r_tooth_in < e.r_tooth_out <= e.r_outer
        for e in geometry.elements
    )
    if not (inside_aperture and inside_slots) and geometry.z_tip <= 0.0:
        raise ValueError(
            "z_tip must be positive when rotor teeth are not entirely inside "
            "their radial slots and strictly inside the open angular aperture; "
            "nonpositive z_tip would permit metal-metal collision."
        )

    values["elements"] = [dataclasses.asdict(e) for e in geometry.elements]
    values.update(
        {
            key: value
            for key, value in dataclasses.asdict(geometry).items()
            if key != "elements"
        }
    )
    return geometry, values, config


def _xyz(r: float, phi: float, z: float) -> FloatArray:
    return np.array([r * math.cos(phi), r * math.sin(phi), z], dtype=np.float64)


def _panel(
    vertices: Sequence[FloatArray],
    outward: FloatArray,
    kind: PanelType,
    body: Literal["rotor", "stator"],
) -> SurfacePanel:
    points = np.asarray(vertices, dtype=np.float64)
    if points.shape != (4, 3) or not np.isfinite(points).all():
        raise ValueError("A panel must have four finite three-dimensional vertices.")
    cross = np.cross(points[1] - points[0], points[2] - points[0])
    if float(np.dot(cross, outward)) < 0.0:
        points = points[[0, 3, 2, 1]]
    cross_1 = np.cross(points[1] - points[0], points[2] - points[0])
    cross_2 = np.cross(points[2] - points[0], points[3] - points[0])
    a1 = 0.5 * float(np.linalg.norm(cross_1))
    a2 = 0.5 * float(np.linalg.norm(cross_2))
    area = a1 + a2
    if area <= 0.0 or not math.isfinite(area):
        raise ValueError("Degenerate surface panel.")
    normal_vector = cross_1 + cross_2
    norm = float(np.linalg.norm(normal_vector))
    if norm <= 0.0:
        raise ValueError("Invalid panel orientation.")
    normal = normal_vector / norm
    if float(np.dot(normal, outward)) <= 0.0:
        raise ValueError("Panel outward normal could not be established.")
    centroid = (
        a1 * (points[0] + points[1] + points[2]) / 3.0
        + a2 * (points[0] + points[2] + points[3]) / 3.0
    ) / area
    return SurfacePanel(
        vertices=cast(Any, tuple(tuple(float(x) for x in p) for p in points)),
        centroid=cast(Any, tuple(float(x) for x in centroid)),
        normal=cast(Any, tuple(float(x) for x in normal)),
        area=area,
        panel_type=kind,
        body=body,
    )


def _horizontal(
    r0: float, r1: float, p0: float, p1: float, z: float,
    sign: float, kind: PanelType, body: Literal["rotor", "stator"],
) -> SurfacePanel:
    return _panel(
        [_xyz(r0, p0, z), _xyz(r1, p0, z), _xyz(r1, p1, z), _xyz(r0, p1, z)],
        np.array([0.0, 0.0, sign]),
        kind,
        body,
    )


def _radial(
    r: float, p0: float, p1: float, z0: float, z1: float,
    sign: float, kind: PanelType, body: Literal["rotor", "stator"],
) -> SurfacePanel:
    midpoint = 0.5 * (p0 + p1)
    return _panel(
        [_xyz(r, p0, z0), _xyz(r, p1, z0), _xyz(r, p1, z1), _xyz(r, p0, z1)],
        sign * np.array([math.cos(midpoint), math.sin(midpoint), 0.0]),
        kind,
        body,
    )


def _azimuthal(
    r0: float, r1: float, p: float, z0: float, z1: float,
    sign: float, kind: PanelType, body: Literal["rotor", "stator"],
) -> SurfacePanel:
    return _panel(
        [_xyz(r0, p, z0), _xyz(r1, p, z0), _xyz(r1, p, z1), _xyz(r0, p, z1)],
        sign * np.array([-math.sin(p), math.cos(p), 0.0]),
        kind,
        body,
    )


def build_clutch_surface_mesh(
    parameters: Any,
    n_r: int = 2,
    n_phi_tooth: int = 3,
    n_phi_bridge: int = 3,
    n_z: int = 2,
) -> ClutchSurfaceMesh:
    """Construct oriented boundary panels for sector zero of both physical bodies."""
    resolution = {
        "n_r": _integer(n_r, "n_r"),
        "n_phi_tooth": _integer(n_phi_tooth, "n_phi_tooth"),
        "n_phi_bridge": _integer(n_phi_bridge, "n_phi_bridge"),
        "n_z": _integer(n_z, "n_z"),
    }
    geometry, values, config = _read_geometry(parameters)
    rotor: list[SurfacePanel] = []
    stator: list[SurfacePanel] = []

    center = math.radians((15.0 + geometry.theta_deg % 90.0) % 90.0)
    half_span = math.radians(geometry.tooth_arc_deg) / 2.0
    tooth_phis = np.linspace(center - half_span, center + half_span, n_phi_tooth + 1)
    rotor_z = np.linspace(geometry.z_tip, geometry.z_tip + geometry.h_teeth, n_z + 1)
    for element in geometry.elements:
        radii = np.linspace(element.r_tooth_in, element.r_tooth_out, n_r + 1)
        for r0, r1 in zip(radii, radii[1:]):
            for p0, p1 in zip(tooth_phis, tooth_phis[1:]):
                rotor.append(_horizontal(
                    float(r0), float(r1), float(p0), float(p1), geometry.z_tip,
                    -1.0, "rotor_bottom", "rotor",
                ))
                rotor.append(_horizontal(
                    float(r0), float(r1), float(p0), float(p1),
                    geometry.z_tip + geometry.h_teeth,
                    1.0, "rotor_top", "rotor",
                ))
            for z0, z1 in zip(rotor_z, rotor_z[1:]):
                rotor.append(_azimuthal(
                    float(r0), float(r1), float(tooth_phis[0]), float(z0), float(z1),
                    -1.0, "rotor_azimuthal_wall", "rotor",
                ))
                rotor.append(_azimuthal(
                    float(r0), float(r1), float(tooth_phis[-1]), float(z0), float(z1),
                    1.0, "rotor_azimuthal_wall", "rotor",
                ))
        for p0, p1 in zip(tooth_phis, tooth_phis[1:]):
            for z0, z1 in zip(rotor_z, rotor_z[1:]):
                for radius, sign in (
                    (element.r_tooth_in, -1.0), (element.r_tooth_out, 1.0)
                ):
                    rotor.append(_radial(
                        radius, float(p0), float(p1), float(z0), float(z1),
                        sign, "rotor_radial_wall", "rotor",
                    ))

    # A conforming r/phi/z cell complex is used only to discover external
    # surfaces. Internal metal-metal faces and artificial sector cuts vanish.
    radial_breaks = sorted({
        geometry.R_min,
        geometry.R_max,
        *(e.r_inner for e in geometry.elements),
        *(e.r_outer for e in geometry.elements),
    })
    radial_grid: list[float] = [radial_breaks[0]]
    slot_flags: list[bool] = []
    for r0, r1 in zip(radial_breaks, radial_breaks[1:]):
        midpoint = 0.5 * (r0 + r1)
        is_slot = any(e.r_inner < midpoint < e.r_outer for e in geometry.elements)
        subdivision = np.linspace(r0, r1, n_r + 1)
        radial_grid.extend(float(x) for x in subdivision[1:])
        slot_flags.extend([is_slot] * n_r)

    aperture = math.radians(geometry.aperture_arc_deg)
    phis = np.concatenate((
        np.linspace(0.0, aperture, n_phi_tooth + 1),
        np.linspace(aperture, math.pi / 2.0, n_phi_bridge + 1)[1:],
    ))
    membrane_z = np.linspace(-geometry.t_membrane, 0.0, n_z + 1)
    if geometry.t_landing_pad > 0.0:
        pad_z = np.linspace(
            -(geometry.t_membrane + geometry.t_landing_pad),
            -geometry.t_membrane,
            n_z + 1,
        )
        heights = np.concatenate((pad_z, membrane_z[1:]))
    else:
        heights = membrane_z

    nr = len(radial_grid) - 1
    np_ = len(phis) - 1
    nz = len(heights) - 1
    occupied = np.zeros((nr, np_, nz), dtype=np.bool_)
    for i in range(nr):
        for j in range(np_):
            in_bridge = j >= n_phi_tooth
            for k in range(nz):
                in_membrane = 0.5 * (heights[k] + heights[k + 1]) >= -geometry.t_membrane
                occupied[i, j, k] = (
                    in_bridge if slot_flags[i] else in_membrane
                )

    def is_occupied(i: int, j: int, k: int) -> bool:
        if i < 0 or i >= nr or k < 0 or k >= nz:
            return False
        # Adjacent physical sectors have the same occupancy pattern.
        return bool(occupied[i, j % np_, k])

    for i, j, k in np.argwhere(occupied):
        i, j, k = int(i), int(j), int(k)
        r0, r1 = radial_grid[i], radial_grid[i + 1]
        p0, p1 = float(phis[j]), float(phis[j + 1])
        z0, z1 = float(heights[k]), float(heights[k + 1])
        if not is_occupied(i, j, k - 1):
            stator.append(_horizontal(
                r0, r1, p0, p1, z0, -1.0, "stator_bottom", "stator"
            ))
        if not is_occupied(i, j, k + 1):
            stator.append(_horizontal(
                r0, r1, p0, p1, z1, 1.0, "stator_top", "stator"
            ))
        if not is_occupied(i - 1, j, k):
            stator.append(_radial(
                r0, p0, p1, z0, z1, -1.0, "stator_radial_wall", "stator"
            ))
        if not is_occupied(i + 1, j, k):
            stator.append(_radial(
                r1, p0, p1, z0, z1, 1.0, "stator_radial_wall", "stator"
            ))
        if not is_occupied(i, j - 1, k):
            stator.append(_azimuthal(
                r0, r1, p0, z0, z1, -1.0, "stator_azimuthal_wall", "stator"
            ))
        if not is_occupied(i, j + 1, k):
            stator.append(_azimuthal(
                r0, r1, p1, z0, z1, 1.0, "stator_azimuthal_wall", "stator"
            ))

    if not rotor or not stator:
        raise ValueError("Both bodies must have nonempty boundary meshes.")
    return ClutchSurfaceMesh(
        tuple(rotor), tuple(stator), geometry, values, config, resolution
    )


def _rotation(sector: int) -> FloatArray:
    # Exact right-angle matrices avoid trigonometric seam roundoff.
    matrices = (
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
        ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    )
    return np.asarray(matrices[sector % 4], dtype=np.float64)


@dataclasses.dataclass(frozen=True)
class YukawaBlocks:
    single_layer: FloatArray
    dz_target: FloatArray
    double_layer_source: FloatArray
    double_layer_target: FloatArray


def _panel_pair_samples(
    target: BodyPanels,
    source: BodyPanels,
    rotation: FloatArray,
    kappa: float,
    self_block: bool,
) -> Iterator[tuple[FloatArray, FloatArray, FloatArray, FloatArray]]:
    """Yield weighted kernels for 16 point pairs without a full QxQ tensor."""
    for body in (target, source):
        if body.centroids.shape != (body.count, 3):
            raise ValueError("Panel centroids must have shape (N, 3).")
        if not np.isfinite(body.centroids).all():
            raise ValueError("Panel centroids must be finite.")
        if body.areas.shape != (body.count,):
            raise ValueError("Panel areas must have shape (N,).")
        if not np.isfinite(body.areas).all() or np.any(body.areas <= 0.0):
            raise ValueError("Panel areas must be finite and positive.")

    if self_block and target.count != source.count:
        raise ValueError("Inconsistent self-block dimensions.")
    source_positions = source.centroids @ rotation.T
    distance = np.linalg.norm(
        target.centroids[:, None, :] - source_positions[None, :, :], axis=2
    )
    zero = distance <= 0.0
    if self_block:
        if np.any(zero & ~np.eye(target.count, dtype=np.bool_)):
            raise ValueError("A body has duplicate panel collocation points.")
    elif zero.any():
        raise ValueError("Distinct panels have coincident collocation points.")

    sub_panel_var = (
        target.areas[:, None] + source.areas[None, :]
    ) / (32.0 * math.pi)
    area_scale = (
        np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :])
    )
    source_points = source.quad_points @ rotation.T
    for qt in range(4):
        for qs in range(4):
            weight = float(target.quad_weights[qt] * source.quad_weights[qs])
            if weight == 0.0:
                continue
            delta = (
                target.quad_points[:, qt, None, :]
                - source_points[None, :, qs, :]
            )
            effective_distance = np.sqrt(
                np.sum(delta**2, axis=2) + sub_panel_var
            )
            kernel = (
                np.exp(-kappa * effective_distance)
                / (4.0 * math.pi * effective_distance)
                * area_scale * weight
            )
            radial_derivative = -kernel * (kappa + 1.0 / effective_distance)
            yield delta, effective_distance, kernel, radial_derivative


def _yukawa_blocks(
    target: BodyPanels,
    source: BodyPanels,
    source_sector: int,
    kappa: float,
    *,
    same_body: bool,
) -> YukawaBlocks:
    """
    Area-symmetrized finite-panel-regularized Yukawa kernels and analytic
    derivatives averaged over 2x2 bilinear quadrature on each panel.

    The self value remains the kappa-independent equal-area disk value.
    Off-diagonal point pairs use sub-panel-area distance regularization.
    """
    kappa = _positive_float(kappa, "kappa", allow_zero=True)
    rotation = _rotation(source_sector)
    source_normals = source.normals @ rotation.T
    self_block = same_body and source_sector == 0
    shape = (target.count, source.count)
    single = np.zeros(shape, dtype=np.float64)
    dz = np.zeros(shape, dtype=np.float64)
    d_target = np.zeros(shape, dtype=np.float64)
    d_source = np.zeros(shape, dtype=np.float64)

    for delta, effective_distance, kernel, radial_derivative in _panel_pair_samples(
        target, source, rotation, kappa, self_block
    ):
        gradient = (
            radial_derivative[:, :, None]
            * delta / effective_distance[:, :, None]
        )
        single += kernel
        dz += gradient[:, :, 2]
        d_target += np.einsum("ijk,ik->ij", gradient, target.normals)
        d_source -= np.einsum("ijk,jk->ij", gradient, source_normals)

    if self_block:
        # G_ii = 1 / (2 sqrt(pi A_i)); multiply by sqrt(A_i A_i).
        diagonal = np.sqrt(target.areas) / (2.0 * math.sqrt(math.pi))
        np.fill_diagonal(single, diagonal)
        np.fill_diagonal(dz, 0.0)
        np.fill_diagonal(d_target, 0.0)
        np.fill_diagonal(d_source, 0.0)
    for array in (single, dz, d_target, d_source):
        if not np.isfinite(array).all():
            raise FloatingPointError("Non-finite Yukawa matrix.")
    return YukawaBlocks(single, dz, d_source, d_target)


def _vector_dyadic_blocks(
    target: BodyPanels,
    source: BodyPanels,
    source_sector: int,
    kappa: float,
    *,
    same_body: bool,
) -> YukawaBlocks:
    """
    Regularized vector single-layer self blocks and tangential dyadic cross
    blocks, with analytic target-z derivatives and panel-major DoF ordering.

    Off-diagonal kernels and derivatives use 2x2 bilinear quadrature on each
    panel. Double-layer fields retain scalar-kernel normal-derivative
    diagnostics projected onto tangent bases; they are not PMCHWT operators.
    """
    kappa = _positive_float(kappa, "kappa", allow_zero=True)
    if target.count == 0 or source.count == 0:
        raise ValueError("Vector dyadic blocks require nonempty panel arrays.")

    rotation = _rotation(source_sector)
    source_normals = source.normals @ rotation.T
    source_tangents = np.einsum("ab,jmb->jma", rotation, source.tangents)
    self_block = same_body and source_sector == 0
    t_dot_t = np.einsum("ima,jna->ijmn", target.tangents, source_tangents)
    shape = (target.count, source.count, 2, 2)
    single = np.zeros(shape, dtype=np.float64)
    dz = np.zeros(shape, dtype=np.float64)
    d_target = np.zeros(shape, dtype=np.float64)
    d_source = np.zeros(shape, dtype=np.float64)

    for delta, effective_distance, kernel, radial_derivative in _panel_pair_samples(
        target, source, rotation, kappa, self_block
    ):
        scaled_kernel = kernel[:, :, None, None]
        scaled_dz = (
            radial_derivative * delta[:, :, 2] / effective_distance
        )[:, :, None, None]

        if same_body:
            single += scaled_kernel * t_dot_t
            dz += scaled_dz * t_dot_t
        else:
            x = kappa * effective_distance
            # Equivalent rational forms avoid overflow from x**2 at large kappa.
            inv = 1.0 / (1.0 + x)
            denominator = 1.0 - inv + inv**2
            c_dir = (1.0 + inv + inv**2) / denominator
            dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denominator**2
            u_R = np.einsum("ima,ija->ijm", target.tangents, delta)
            v_R = np.einsum("jna,ija->ijn", source_tangents, delta)
            u_z = target.tangents[:, :, 2][:, None, :, None]
            v_z = source_tangents[:, :, 2][None, :, None, :]
            R_inv2 = (1.0 / effective_distance**2)[:, :, None, None]
            Z = delta[:, :, 2][:, :, None, None]
            D = u_R[:, :, :, None] * v_R[:, :, None, :] * R_inv2
            dD_dz = (
                (u_z * v_R[:, :, None, :] + u_R[:, :, :, None] * v_z) * R_inv2
                - 2.0 * Z * D * R_inv2
            )
            Aniso = 0.5 * (t_dot_t - 0.5 * c_dir[:, :, None, None] * D)
            dAniso_dz = (
                -0.25
                * (dc_dir_dx * kappa * delta[:, :, 2] / effective_distance)[
                    :, :, None, None
                ]
                * D
                - 0.25 * c_dir[:, :, None, None] * dD_dz
            )
            single += scaled_kernel * Aniso
            dz += scaled_dz * Aniso + scaled_kernel * dAniso_dz

        gradient = (
            radial_derivative[:, :, None]
            * delta / effective_distance[:, :, None]
        )
        d_target += np.einsum(
            "ija,ia->ij", gradient, target.normals
        )[:, :, None, None] * t_dot_t
        d_source -= np.einsum(
            "ija,ja->ij", gradient, source_normals
        )[:, :, None, None] * t_dot_t

    if self_block:
        indices = np.arange(target.count)
        diagonal = np.sqrt(target.areas) / (2.0 * math.sqrt(math.pi))
        single[indices, indices] = diagonal[:, None, None] * np.eye(2)
        dz[indices, indices] = 0.0
        d_target[indices, indices] = 0.0
        d_source[indices, indices] = 0.0

    arrays = [
        array.transpose(0, 2, 1, 3).reshape(2 * target.count, 2 * source.count)
        for array in (single, dz, d_source, d_target)
    ]
    if not all(np.isfinite(array).all() for array in arrays):
        raise FloatingPointError("Non-finite vector dyadic matrix.")
    return YukawaBlocks(*arrays)


@dataclasses.dataclass(frozen=True)
class MaterialModel:
    material: str
    epsilon_inf: float | None
    plasma_frequency: float | None
    gamma: float | None
    oscillators: tuple[dict[str, float], ...]

    @classmethod
    def from_parameters(cls, parameters: Mapping[str, Any]) -> MaterialModel:
        material = str(_pick(parameters, ("material",), required=False, default="Gold"))
        if material.upper() == "PEC":
            return cls("PEC", None, None, None, ())
        if material.lower() not in {"gold", "au"}:
            raise ValueError("Supported materials are PEC and dispersive Gold/Au.")
        material_values = dict(parameters)
        dispersion = parameters.get("dispersion")
        if isinstance(dispersion, Mapping):
            material_values.update(dispersion)
        epsilon_inf = _positive_float(
            _pick(material_values, ("epsilon_inf",), required=False, default=1.0),
            "epsilon_inf",
        )
        wp = _positive_float(
            _pick(
                material_values, ("plasma_frequency",),
                required=False, default=9.03 / 1.239841984,
            ),
            "plasma_frequency",
        )
        gamma = _positive_float(
            _pick(
                material_values, ("gamma",),
                required=False, default=0.053 / 1.239841984,
            ),
            "gamma", allow_zero=True,
        )
        raw = _pick(
            material_values, ("lorentz_oscillators",), required=False, default=[]
        )
        if not isinstance(raw, (list, tuple)):
            raise TypeError("lorentz_oscillators must be a sequence.")
        oscillators: list[dict[str, float]] = []
        for index, entry in enumerate(raw):
            oscillator = _mapping(entry, f"lorentz_oscillators[{index}]")
            oscillators.append({
                "strength": _positive_float(
                    _pick(oscillator, ("strength",)), "oscillator strength",
                    allow_zero=True,
                ),
                "omega_0": _positive_float(
                    _pick(oscillator, ("omega_0",)), "oscillator omega_0"
                ),
                "gamma": _positive_float(
                    _pick(oscillator, ("gamma",)), "oscillator gamma", allow_zero=True
                ),
            })
        return cls("Gold", epsilon_inf, wp, gamma, tuple(oscillators))

    def epsilon(self, kappa: float) -> float | None:
        kappa = _positive_float(kappa, "kappa")
        if self.material == "PEC":
            return None
        if self.epsilon_inf is None or self.plasma_frequency is None or self.gamma is None:
            raise ValueError("Incomplete dispersion model.")
        denominator = kappa * (kappa + self.gamma)
        if denominator <= 0.0:
            raise FloatingPointError("Nonpositive Drude denominator.")
        epsilon = self.epsilon_inf + self.plasma_frequency**2 / denominator
        for oscillator in self.oscillators:
            omega = oscillator["omega_0"]
            denominator = omega**2 + kappa**2 + oscillator["gamma"] * kappa
            epsilon += oscillator["strength"] * omega**2 / denominator
        if not math.isfinite(epsilon) or epsilon <= 0.0:
            raise FloatingPointError("Invalid imaginary-frequency permittivity.")
        return epsilon

    def channel_weights(self, kappa: float) -> tuple[float, float, float | None]:
        epsilon = self.epsilon(kappa)
        if epsilon is None:
            return 1.0, 1.0, None
        # Normal-incidence Fresnel amplitudes, not an angle-resolved PMCHWT
        # material operator. Products for two identical bodies are positive.
        root = math.sqrt(epsilon)
        tm = (epsilon - root) / (epsilon + root)
        te = (1.0 - root) / (1.0 + root)
        if not all(math.isfinite(x) for x in (tm, te)):
            raise FloatingPointError("Invalid material channel weights.")
        return tm, te, epsilon

    def metadata(self) -> dict[str, Any]:
        return {
            "material": self.material,
            "model": "PEC" if self.material == "PEC" else "Drude-Lorentz",
            "frequency_units": "um^-1 (xi/c)",
            "epsilon_inf": self.epsilon_inf,
            "plasma_frequency": self.plasma_frequency,
            "gamma": self.gamma,
            "lorentz_oscillators": list(self.oscillators),
        }


class DenseBackend:
    def __init__(self, requested: Literal["auto", "cpu", "cuda"]) -> None:
        if requested not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda.")
        self.torch: Any = None
        self.device = "cpu"
        if requested != "cpu" and importlib.util.find_spec("torch") is not None:
            torch = importlib.import_module("torch")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cuda":
                self.torch = torch
                self.device = device
        if requested == "cuda" and self.device != "cuda":
            raise RuntimeError("CUDA was explicitly requested but is unavailable.")

    def array(self, value: NDArray[Any]) -> Any:
        if self.torch is None:
            return np.asarray(value, dtype=np.complex128)
        return self.torch.as_tensor(
            value, dtype=self.torch.complex128, device=self.device
        )

    def eye(self, count: int) -> Any:
        if self.torch is None:
            return np.eye(count, dtype=np.complex128)
        return self.torch.eye(count, dtype=self.torch.complex128, device=self.device)

    def concat_cols(self, arrays: Sequence[Any]) -> Any:
        if self.torch is None:
            return np.concatenate(arrays, axis=1)
        return self.torch.cat(arrays, dim=1)

    def solve(self, matrix: Any, rhs: Any) -> Any:
        if self.torch is None:
            result = linalg.solve(matrix, rhs, assume_a="gen", check_finite=True)
            if not np.isfinite(result).all():
                raise FloatingPointError("Non-finite linear solve.")
            return result
        result = self.torch.linalg.solve(matrix, rhs)
        if not bool(self.torch.isfinite(result).all().item()):
            raise FloatingPointError("Non-finite CUDA linear solve.")
        return result

    def factor_and_solve(
        self, matrix: Any, rhs: Any, need_logdet: bool = False
    ) -> tuple[Any, float, complex | None]:
        """Reuse CPU LU factors for solving, pivot conditioning, and logdet."""
        if self.torch is not None:
            condition = self.condition(matrix)
            solution = self.solve(matrix, rhs)
            logdet = self.logdet(matrix) if need_logdet else None
            return solution, condition, logdet

        lu, piv = linalg.lu_factor(matrix, check_finite=True)
        u_diag = np.diag(lu)
        diag = np.abs(u_diag)
        if np.any(diag == 0.0) or not np.isfinite(diag).all():
            raise linalg.LinAlgError("Singular BEM operator.")
        condition = float(np.max(diag) / np.min(diag)) if diag.size else 1.0
        if not math.isfinite(condition):
            raise linalg.LinAlgError("Singular or non-finite BEM operator.")
        solution = linalg.lu_solve((lu, piv), rhs, check_finite=True)
        if not np.isfinite(solution).all():
            raise FloatingPointError("Non-finite linear solve.")
        logdet = None
        if need_logdet:
            parity = (
                1.0
                if int(np.sum(piv != np.arange(len(piv)))) % 2 == 0
                else -1.0
            )
            sign = parity * np.prod(u_diag / diag)
            magnitude = float(np.sum(np.log(diag)))
            if abs(sign) == 0.0 or not math.isfinite(magnitude):
                raise linalg.LinAlgError("Singular scattering determinant.")
            logdet = complex(magnitude, float(np.angle(sign)))
        return solution, condition, logdet

    def adjoint(self, value: Any) -> Any:
        return value.conj().T if self.torch is None else value.mH

    def trace(self, value: Any) -> complex:
        if self.torch is None:
            return complex(np.trace(value))
        return complex(self.torch.trace(value).item())

    def condition(self, value: Any) -> float:
        result = (
            float(np.linalg.cond(value, p=1).real)
            if self.torch is None
            else float(self.torch.linalg.cond(value, p=1).real.item())
        )
        if not math.isfinite(result):
            raise linalg.LinAlgError("Singular or non-finite BEM operator.")
        return result

    def logdet(self, value: Any) -> complex:
        if self.torch is None:
            sign, magnitude = np.linalg.slogdet(value)
            if abs(sign) == 0.0 or not math.isfinite(float(magnitude)):
                raise linalg.LinAlgError("Singular scattering determinant.")
            return complex(float(magnitude), float(np.angle(sign)))
        sign, magnitude = self.torch.linalg.slogdet(value)
        sign_value = complex(sign.item())
        magnitude_value = float(magnitude.item())
        if abs(sign_value) == 0.0 or not math.isfinite(magnitude_value):
            raise linalg.LinAlgError("Singular CUDA scattering determinant.")
        return complex(magnitude_value, math.atan2(sign_value.imag, sign_value.real))


def _assert_real(value: complex, name: str, tolerance: float = 1.0e-7) -> float:
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        raise FloatingPointError(f"{name} is non-finite.")
    if abs(value.imag) > tolerance * max(1.0, abs(value.real)):
        raise FloatingPointError(f"{name} has an unexpected imaginary part: {value}.")
    return float(value.real)


def _quadrature(n_xi: int, kappa_0: float) -> tuple[FloatArray, FloatArray, FloatArray]:
    nodes, weights = np.polynomial.legendre.leggauss(n_xi)
    u = (nodes + 1.0) / 2.0
    w_u = weights / 2.0
    denominator = 1.0 - u
    if np.any(denominator <= 0.0):
        raise FloatingPointError("Invalid mapped imaginary-frequency quadrature.")
    kappas = kappa_0 * u / denominator
    weights_kappa = w_u * kappa_0 / denominator**2
    if not np.isfinite(kappas).all() or not np.isfinite(weights_kappa).all():
        raise FloatingPointError("Non-finite imaginary-frequency quadrature.")
    return kappas, weights_kappa, u


def _frequency_integrand(
    mesh: ClutchSurfaceMesh,
    kappa: float,
    material: MaterialModel,
    backend: DenseBackend,
    condition_limit: float,
    formulation: Formulation = "vector_dyadic",
) -> dict[str, Any]:
    _formulation_qualification(formulation)
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    tm, te, epsilon = material.channel_weights(kappa)
    dofs_per_panel = 2 if formulation == "vector_dyadic" else 1
    nr = dofs_per_panel * rotor.count
    ns = dofs_per_panel * stator.count
    block_function = (
        _vector_dyadic_blocks if formulation == "vector_dyadic" else _yukawa_blocks
    )
    bottom_mask = np.repeat(
        np.array(
            [kind == "rotor_bottom" for kind in rotor.panel_types], dtype=np.float64
        ),
        dofs_per_panel,
    )[:, None]
    phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)

    rr_modes = [np.zeros((nr, nr), dtype=np.complex128) for _ in range(4)]
    ss_modes = [np.zeros((ns, ns), dtype=np.complex128) for _ in range(4)]
    rs_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]
    dz_modes = [np.zeros((nr, ns), dtype=np.complex128) for _ in range(4)]
    normal_squared = {"rotor": 0.0, "stator": 0.0, "cross": 0.0}

    for sector in range(4):
        for target, source, modes, label, same in (
            (rotor, rotor, rr_modes, "rotor", True),
            (stator, stator, ss_modes, "stator", True),
            (rotor, stator, rs_modes, "cross", False),
        ):
            block = block_function(target, source, sector, kappa, same_body=same)
            normal_squared[label] += float(
                np.sum(block.double_layer_source**2)
                + np.sum(block.double_layer_target**2)
            )
            for mode in range(4):
                modes[mode] += phases[mode, sector] * block.single_layer
                if label == "cross":
                    dz_modes[mode] += phases[mode, sector] * block.dz_target

    derivative = 0j
    bottom_derivative = 0j
    logdet = 0j
    mode_diagnostics: list[dict[str, Any]] = []
    channel_derivatives = {"TM": 0j, "TE": 0j}

    for mode in range(4):
        mr = backend.array(rr_modes[mode])
        ms = backend.array(ss_modes[mode])
        g = backend.array(rs_modes[mode])
        dg = backend.array(dz_modes[mode])
        dg_bottom = backend.array(dz_modes[mode] * bottom_mask)

        # Reciprocity gives the reverse cyclic cross-block and its derivative.
        sr = backend.adjoint(g)
        dsr = backend.adjoint(dg)
        dsr_bottom = backend.adjoint(dg_bottom)
        n_col = g.shape[1]
        x_all, condition_r, _ = backend.factor_and_solve(
            mr, backend.concat_cols((g, dg, dg_bottom))
        )
        x, dx, dx_bottom = (
            x_all[:, :n_col],
            x_all[:, n_col:2 * n_col],
            x_all[:, 2 * n_col:],
        )
        n_col_s = sr.shape[1]
        z_all, condition_s, _ = backend.factor_and_solve(
            ms, backend.concat_cols((sr, dsr, dsr_bottom))
        )
        z, dz, dz_bottom = (
            z_all[:, :n_col_s],
            z_all[:, n_col_s:2 * n_col_s],
            z_all[:, 2 * n_col_s:],
        )
        if max(condition_r, condition_s) > condition_limit:
            raise linalg.LinAlgError(
                f"BEM block condition number exceeds {condition_limit:g} "
                f"at kappa={kappa:g}, symmetry mode={mode}. "
                "Refine/change the discretization; no regularization was applied."
            )
        coupling = x @ z
        dcoupling = dx @ z + x @ dz
        dcoupling_bottom = dx_bottom @ z + x @ dz_bottom

        channels: dict[str, Any] = {}
        tm_result: tuple[float, complex, complex, complex] | None = None
        for channel, weight in (("TM", tm), ("TE", te)):
            product_weight = weight**2
            if (
                channel == "TE"
                and tm_result is not None
                and math.isclose(tm**2, te**2, rel_tol=1.0e-14, abs_tol=0.0)
            ):
                (
                    condition_y,
                    channel_logdet,
                    channel_derivative,
                    channel_bottom,
                ) = tm_result
            else:
                y = backend.eye(nr) - product_weight * coupling
                n_col_y = dcoupling.shape[1]
                derivative_all, condition_y, channel_logdet = backend.factor_and_solve(
                    y,
                    backend.concat_cols((dcoupling, dcoupling_bottom)),
                    need_logdet=True,
                )
                if condition_y > condition_limit:
                    raise linalg.LinAlgError(
                        f"Scattering condition number exceeds {condition_limit:g}."
                    )
                assert channel_logdet is not None
                if abs(channel_logdet.imag) > 1.0e-7:
                    raise FloatingPointError(
                        "A scattering determinant is not positive-real. The specified "
                        f"{formulation} collocation model is invalid for this discretization."
                    )
                channel_derivative = -product_weight * backend.trace(
                    derivative_all[:, :n_col_y]
                )
                channel_bottom = -product_weight * backend.trace(
                    derivative_all[:, n_col_y:]
                )
                if channel == "TM":
                    tm_result = (
                        condition_y,
                        channel_logdet,
                        channel_derivative,
                        channel_bottom,
                    )
            derivative += channel_derivative
            bottom_derivative += channel_bottom
            channel_derivatives[channel] += channel_derivative
            logdet += channel_logdet
            channels[channel] = {
                "reflection_weight": weight,
                "condition_number_Y": condition_y,
                "d_logdet_d_z": _assert_real(channel_derivative, "channel derivative"),
                "logdet_Y": _assert_real(channel_logdet, "channel logdet"),
            }
        mode_diagnostics.append({
            "mode": mode,
            "condition_number_M_rotor": condition_r,
            "condition_number_M_stator": condition_s,
            "channels": channels,
        })

    d_total = _assert_real(derivative, "full cyclic derivative")
    d_bottom = _assert_real(bottom_derivative, "bottom derivative")
    # Summing the four irreducible cyclic blocks already performs the physical
    # four-sector trace. There must NOT be a second factor of four here.
    return {
        "kappa_um_inv": kappa,
        "epsilon_i_xi": epsilon,
        "d_logdet_d_z": d_total,
        "force_integrand": -d_total / (2.0 * math.pi),
        "bottom_force_integrand": -d_bottom / (2.0 * math.pi),
        "edge_top_force_integrand": -(d_total - d_bottom) / (2.0 * math.pi),
        "logdet_Y": _assert_real(logdet, "full cyclic logdet"),
        "TM_force_integrand": -_assert_real(
            channel_derivatives["TM"], "TM derivative"
        ) / (2.0 * math.pi),
        "TE_force_integrand": -_assert_real(
            channel_derivatives["TE"], "TE derivative"
        ) / (2.0 * math.pi),
        "normal_derivative_frobenius_norms": {
            key: math.sqrt(value) for key, value in normal_squared.items()
        },
        "symmetry_modes": mode_diagnostics,
    }


def _fingerprint(mesh: ClutchSurfaceMesh, settings: Mapping[str, Any]) -> str:
    payload = {
        "parameters": mesh.parameters,
        "solver_parameters": _plain(settings),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _base_result(
    mesh: ClutchSurfaceMesh,
    solver: str,
    settings: dict[str, Any],
    config_file: str | Path | None,
    task_id: str | None,
) -> dict[str, Any]:
    fingerprint = _fingerprint(mesh, settings)
    return {
        "status": "running",
        "task_id": task_id or str(mesh.config.get("task_id", fingerprint[:16])),
        "config_file": str(config_file) if config_file is not None else mesh.config.get("config_file"),
        "fingerprint": fingerprint,
        "N_fractal": mesh.parameters.get("N_fractal"),
        "theta_deg": mesh.geometry.theta_deg,
        "parameters": _plain(mesh.parameters),
        "solver": solver,
        "solver_parameters": settings,
        "symmetry_multiplier": mesh.symmetry_multiplier,
        "n_panels_rotor": mesh.n_panels_rotor,
        "n_panels_stator": mesh.n_panels_stator,
        "n_panels_total": mesh.n_panels_total,
        "force_units": "hbar*c/um^2",
        "force_direction": "z; negative means attraction toward stator",
        "MEEP_FORCE_TO_SI": MEEP_FORCE_TO_SI,
        "F_net": None,
        "f_net_N": None,
        "f_net_fN": None,
        "f_net_pN": None,
        "elapsed_seconds": None,
        "time_truncated": False,
        "converged": False,
    }


def _set_force(result: dict[str, Any], force: float) -> None:
    force = _finite_float(force, "F_net")
    newtons = force * MEEP_FORCE_TO_SI
    result.update({
        "F_net": force,
        "f_net_N": newtons,
        "f_net_fN": newtons * 1.0e15,
        "f_net_pN": newtons * 1.0e12,
    })


def _invoke_compatible(
    function: Callable[..., Any],
    candidates: Sequence[tuple[tuple[Any, ...], dict[str, Any]]],
    name: str,
) -> Any:
    signature = inspect.signature(function)
    for args, kwargs in candidates:
        try:
            signature.bind(*args, **kwargs)
        except TypeError:
            continue
        return function(*args, **kwargs)
    raise RuntimeError(f"Unsupported {name} signature: {signature}.")


def _record_provenance(result: dict[str, Any]) -> None:
    """Call the project's logger; logger failures are never silently ignored."""
    logger = importlib.import_module("utils.metrics_logger")
    names = ("set_solver_provenance", "log_step", "log_metric", "export_macros")
    for name in names:
        function = getattr(logger, name, None)
        if not callable(function):
            raise RuntimeError(f"utils.metrics_logger.{name} is missing or not callable.")

    solver = result["solver"]
    settings = result["solver_parameters"]
    task_id = result.get("task_id")
    step_id = f"clutch_pilot_{solver}_task_{task_id}_{result.get('status')}"
    summary_dict = _mapping(result, "provenance summary")

    logger.set_solver_provenance(solver, settings)
    logger.log_step(
        step_id,
        summary_dict,
        solver_name=solver,
        solver_parameters=settings,
    )
    for name in ("F_net", "f_net_N", "f_net_fN", "f_net_pN", "elapsed_seconds"):
        value = result.get(name)
        if value is None:
            continue
        for key in (
            f"clutch_pilot_{solver}_task_{task_id}_{name}",
            f"{solver}_{name}",
        ):
            logger.log_metric(
                key,
                value,
                step_id=step_id,
                solver_name=solver,
                solver_parameters=settings,
            )
    logger.export_macros()
    for path in (
        Path("results/provenance_metrics.json"),
        Path("results/macros_results.tex"),
    ):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(
                "[ERROR: RUN_DATA_MISSING] Provenance artifacts were not generated"
            )


def run_bem_casimir_solver(
    parameters: Any,
    *,
    n_r: int = 2,
    n_phi_tooth: int = 3,
    n_phi_bridge: int = 3,
    n_z: int = 2,
    n_xi: int = 24,
    max_steps: int = 0,
    device: Literal["auto", "cpu", "cuda"] = "auto",
    condition_limit: float = 1.0e14,
    max_memory_gib: float = 4.0,
    config_file: str | Path | None = None,
    task_id: str | None = None,
    mesh: ClutchSurfaceMesh | None = None,
    record_metrics: bool = True,
    require_exact_electromagnetics: bool = False,
    formulation: Formulation = "vector_dyadic",
    temperature_K: float | None = None,
) -> dict[str, Any]:
    """
    Evaluate the specified vector dyadic or legacy scalar T-operator model.

    At positive temperature, use low Matsubara modes and an Euler-Maclaurin
    midpoint tail integral. The static mode is evaluated at a small positive
    kappa to retain compatibility with the dispersive material model.

    max_steps evaluates a prefix of the *original* n_xi quadrature rule.
    A partial integral is never renormalized or reported as converged.
    """
    started = time.perf_counter()
    qualification = _formulation_qualification(formulation)
    n_xi = _integer(n_xi, "n_xi")
    max_steps = _integer(max_steps, "max_steps", minimum=0)
    condition_limit = _positive_float(condition_limit, "condition_limit")
    max_memory_gib = _positive_float(max_memory_gib, "max_memory_gib")
    if require_exact_electromagnetics:
        raise RuntimeError(
            qualification
            + " The approximate equations requested for 'bem' cannot meet an exact "
            "electromagnetic requirement; no substitute force was computed."
        )
    if mesh is None:
        mesh = build_clutch_surface_mesh(
            parameters, n_r, n_phi_tooth, n_phi_bridge, n_z
        )
    temperature_K = _positive_float(
        temperature_K if temperature_K is not None
        else mesh.parameters.get("temperature_K", 0.0),
        "temperature_K", allow_zero=True,
    )
    backend = DenseBackend(device)
    material = MaterialModel.from_parameters(mesh.parameters)
    nr, ns = len(mesh.rotor), len(mesh.stator)
    dofs_per_panel = 2 if formulation == "vector_dyadic" else 1
    nr_dof, ns_dof = dofs_per_panel * nr, dofs_per_panel * ns
    # Conservative peak allowance: cyclic blocks, kernel temporaries,
    # factorization workspace, and simultaneously live channel matrices.
    estimated_bytes = 16 * (
        12 * nr_dof**2 + 10 * ns_dof**2 + 20 * nr_dof * ns_dof
    )
    memory_limit = max_memory_gib * 1024**3
    if estimated_bytes > memory_limit:
        raise MemoryError(
            f"Estimated dense working memory is {estimated_bytes / 1024**3:.2f} GiB "
            f"for {nr} rotor and {ns} stator sector panels; limit is "
            f"{max_memory_gib:.2f} GiB. Reduce panel resolution for a micro-probe "
            "or explicitly increase --max-memory-gib."
        )
    if backend.torch is not None:
        free_bytes, _ = backend.torch.cuda.mem_get_info()
        if estimated_bytes > free_bytes:
            raise MemoryError(
                "Estimated dense working memory exceeds currently available CUDA "
                "memory. Request --device cpu or reduce resolution."
            )

    kappa_0 = 1.0 / max(abs(mesh.geometry.z_tip), 0.015)
    matsubara_count = 0
    tail_count = n_xi
    delta_kappa = 0.0
    kappa_cut = 0.0
    if temperature_K > 0.0:
        delta_kappa = (
            2.0 * math.pi * (8.617333262e-5 * temperature_K) / 0.1973269804
        )
        if not math.isfinite(delta_kappa) or delta_kappa <= 0.0:
            raise FloatingPointError("Invalid Matsubara frequency spacing.")
        # Cap M for n_xi=1, preserving the requested total node count.
        matsubara_count = min(n_xi, min(8, max(2, n_xi // 3)))
        tail_count = n_xi - matsubara_count
        kappas = np.arange(matsubara_count, dtype=np.float64) * delta_kappa
        kappas[0] = 1.0e-4 * delta_kappa
        weights = np.full(matsubara_count, delta_kappa, dtype=np.float64)
        weights[0] *= 0.5
        # Discrete modes have no mapped-tail coordinate; retain the numeric
        # "u" return key using zero for these entries.
        nodes = np.zeros(matsubara_count, dtype=np.float64)
        kappa_cut = (matsubara_count - 0.5) * delta_kappa
        if tail_count:
            tail_kappas, tail_weights, tail_nodes = _quadrature(tail_count, kappa_0)
            kappas = np.concatenate((kappas, kappa_cut + tail_kappas))
            weights = np.concatenate((weights, tail_weights))
            nodes = np.concatenate((nodes, tail_nodes))
        if (
            not np.isfinite(kappas).all()
            or np.any(kappas <= 0.0)
            or not np.isfinite(weights).all()
            or np.any(weights <= 0.0)
        ):
            raise FloatingPointError("Invalid finite-temperature quadrature.")
    else:
        kappas, weights, nodes = _quadrature(n_xi, kappa_0)

    evaluated = min(n_xi, max_steps) if max_steps > 0 else n_xi
    settings: dict[str, Any] = {
        "method": (
            "dense area-symmetrized tangential-vector dyadic T-operator"
            if formulation == "vector_dyadic"
            else "dense area-symmetrized centroid-collocation scalar T-operator"
        ),
        "formulation": formulation,
        "physical_model": VECTOR_MODEL if formulation == "vector_dyadic" else SCALAR_MODEL,
        "exact_electromagnetic_fsc": False,
        "physics_qualification": qualification,
        "n_xi": n_xi,
        "n_xi_evaluated": evaluated,
        "max_steps": max_steps,
        "panel_resolution": mesh.panel_resolution,
        "n_panels_rotor": mesh.n_panels_rotor,
        "n_panels_stator": mesh.n_panels_stator,
        "n_panels_total": mesh.n_panels_total,
        "n_panels_rotor_sector": nr,
        "n_panels_stator_sector": ns,
        "dofs_per_panel": dofs_per_panel,
        "n_dofs_rotor_sector": nr_dof,
        "n_dofs_stator_sector": ns_dof,
        "device": backend.device,
        "requested_device": device,
        "dtype": "complex128",
        "quadrature_rule": (
            "Matsubara modes plus Euler-Maclaurin midpoint Gauss-Legendre tail"
            if temperature_K > 0.0
            else "Gauss-Legendre on u in (0,1)"
        ),
        "kappa_mapping": (
            "kappa_cut + kappa_0*u/(1-u) for the tail"
            if temperature_K > 0.0 else "kappa_0*u/(1-u)"
        ),
        "kappa_0_um_inv": kappa_0,
        "dispersion_model": material.metadata(),
        "channel_weights": "normal-incidence TM and TE Fresnel amplitudes",
        "symmetry_multiplier": SYMMETRY_MULTIPLIER,
        "symmetry_method": "sum of four cyclic Fourier-block traces",
        "inter_sector_interactions": True,
        "diagonal_self_term": "equal-area disk: 1/(2*sqrt(pi*A))",
        "off_diagonal_quadrature": (
            "2x2 Gauss-Legendre bilinear points per panel; 16 weighted point pairs "
            "with sqrt(distance^2 + (A_target + A_source)/(32*pi))"
        ),
        "normal_derivatives": (
            "analytic finite-panel-regularized scalar kernel derivatives "
            "projected onto tangent bases; diagnostics only"
            if formulation == "vector_dyadic"
            else "analytic finite-panel-regularized kernel derivatives; diagnostics only"
        ),
        "condition_limit": condition_limit,
        "regularization": None,
        "estimated_dense_memory_bytes": estimated_bytes,
        "max_memory_gib": max_memory_gib,
        "temperature_K": temperature_K,
        "force_derivative": "analytic rigid rotor z translation",
        "diagnostic_decomposition": (
            "partition of translation derivative by rotor panel; "
            "not an independently observable Maxwell-stress face force"
        ),
    }
    if temperature_K > 0.0:
        settings.update({
            "matsubara_modes": matsubara_count,
            "tail_quadrature_points": tail_count,
            "delta_kappa_um_inv": delta_kappa,
            "kappa_cut_um_inv": kappa_cut,
            "static_mode_kappa_um_inv": float(kappas[0]),
        })
    result = _base_result(mesh, "bem", settings, config_file, task_id)
    rows: list[dict[str, Any]] = []
    net = bottom = edge = tm_total = te_total = energy = 0.0
    for q in range(evaluated):
        step_started = time.perf_counter()
        row = _frequency_integrand(
            mesh, float(kappas[q]), material, backend, condition_limit,
            formulation=formulation,
        )
        weight = float(weights[q])
        net += weight * float(row["force_integrand"])
        bottom += weight * float(row["bottom_force_integrand"])
        edge += weight * float(row["edge_top_force_integrand"])
        tm_total += weight * float(row["TM_force_integrand"])
        te_total += weight * float(row["TE_force_integrand"])
        energy += weight * float(row["logdet_Y"]) / (2.0 * math.pi)
        row.update({
            "quadrature_index": q,
            "u": float(nodes[q]),
            "quadrature_weight_um_inv": weight,
            "weighted_force_contribution": weight * float(row["force_integrand"]),
            "elapsed_seconds": time.perf_counter() - step_started,
        })
        if temperature_K > 0.0:
            row.update({
                "quadrature_kind": "matsubara" if q < matsubara_count else "tail",
                "matsubara_mode": q if q < matsubara_count else None,
            })
        rows.append(row)
    if not math.isclose(net, bottom + edge, rel_tol=1.0e-9, abs_tol=1.0e-12):
        raise FloatingPointError("Force diagnostic partition does not sum to total.")
    _set_force(result, net)
    result.update({
        "status": (
            "completed_vector_approximation"
            if formulation == "vector_dyadic"
            else "completed_scalar_approximation"
        ),
        "physics_qualification": qualification,
        "time_truncated": max_steps > 0,
        "quadrature_incomplete": evaluated < n_xi,
        "converged": False,
        "convergence_note": (
            "No resolution/frequency convergence study has been performed."
            if evaluated == n_xi
            else "Only a prefix of the frequency integral was evaluated."
        ),
        "elapsed_seconds": time.perf_counter() - started,
        "energy_hbar_c_per_um": energy,
        "diagnostics": {
            "F_bottom": bottom,
            "F_lateral_top_edge": edge,
            "f_bottom_N": bottom * MEEP_FORCE_TO_SI,
            "f_lateral_top_edge_N": edge * MEEP_FORCE_TO_SI,
            "F_TM": tm_total,
            "F_TE": te_total,
            "n_panels_rotor": mesh.n_panels_rotor,
            "n_panels_stator": mesh.n_panels_stator,
            "n_panels_total": mesh.n_panels_total,
            "panel_types_sector": dict(Counter(
                p.panel_type for p in (*mesh.rotor, *mesh.stator)
            )),
            "per_xi": rows,
        },
        "per_xi_integrands": rows,
    })
    if record_metrics:
        _record_provenance(result)
    return result


@dataclasses.dataclass(frozen=True)
class TriangleMesh:
    vertices: FloatArray
    triangles: NDArray[np.int64]


def _triangular_mesh(panels: Sequence[SurfacePanel], length_scale: float) -> TriangleMesh:
    if not panels:
        raise ValueError("Cannot export an empty surface.")
    tolerance = max(length_scale, 1.0) * 1.0e-11
    vertices: list[tuple[float, float, float]] = []
    vertex_ids: dict[tuple[int, int, int], int] = {}
    triangles: list[tuple[int, int, int]] = []

    def vertex_id(point: FloatArray) -> int:
        key = cast(tuple[int, int, int], tuple(int(round(x / tolerance)) for x in point))
        existing = vertex_ids.get(key)
        if existing is not None:
            if np.linalg.norm(point - np.asarray(vertices[existing])) > 2.0 * tolerance:
                raise ValueError("Ambiguous mesh vertex quantization.")
            return existing
        index = len(vertices)
        vertices.append(cast(Any, tuple(float(x) for x in point)))
        vertex_ids[key] = index
        return index

    for sector in range(4):
        rotation = _rotation(sector)
        for panel in panels:
            points = np.asarray(panel.vertices) @ rotation.T
            ids = [vertex_id(point) for point in points]
            triangles.extend(((ids[0], ids[1], ids[2]), (ids[0], ids[2], ids[3])))
    result = TriangleMesh(
        np.asarray(vertices, dtype=np.float64),
        np.asarray(triangles, dtype=np.int64),
    )
    _validate_watertight(result)
    return result


def _validate_watertight(mesh: TriangleMesh) -> None:
    if mesh.vertices.size == 0 or mesh.triangles.size == 0:
        raise ValueError("Empty triangular mesh.")
    directed: Counter[tuple[int, int]] = Counter()
    undirected: Counter[tuple[int, int]] = Counter()
    for triangle in mesh.triangles:
        a, b, c = (int(x) for x in triangle)
        if len({a, b, c}) != 3:
            raise ValueError("Triangle contains repeated vertices.")
        points = mesh.vertices[[a, b, c]]
        area = 0.5 * float(np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0])))
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError("Degenerate exported triangle.")
        for x, y in ((a, b), (b, c), (c, a)):
            directed[x, y] += 1
            undirected[min(x, y), max(x, y)] += 1
    bad_edges = [edge for edge, count in undirected.items() if count != 2]
    if bad_edges:
        raise ValueError(
            f"Surface is not watertight/manifold: {len(bad_edges)} invalid edges. "
            f"First invalid edge: {bad_edges[0]}."
        )
    for x, y in undirected:
        if directed[x, y] != 1 or directed[y, x] != 1:
            raise ValueError("Exported surface has inconsistent triangle orientation.")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def _write_gmsh_v2(path: Path, mesh: TriangleMesh) -> None:
    lines = [
        "$MeshFormat", "2.2 0 8", "$EndMeshFormat",
        "$Nodes", str(len(mesh.vertices)),
    ]
    for index, point in enumerate(mesh.vertices, start=1):
        lines.append(f"{index} {point[0]:.17g} {point[1]:.17g} {point[2]:.17g}")
    lines.extend(("$EndNodes", "$Elements", str(len(mesh.triangles))))
    for index, triangle in enumerate(mesh.triangles, start=1):
        a, b, c = (int(x) + 1 for x in triangle)
        lines.append(f"{index} 2 2 1 1 {a} {b} {c}")
    lines.extend(("$EndElements", ""))
    _atomic_text(path, "\n".join(lines))


def _scuff_material_text(material: MaterialModel) -> str:
    if material.material == "PEC":
        return ""
    if material.epsilon_inf is None or material.plasma_frequency is None or material.gamma is None:
        raise ValueError("Incomplete SCUFF material.")
    epsilon = (
        f"({material.epsilon_inf:.17g})"
        f"-({material.plasma_frequency:.17g})^2"
        f"/(w*(w+ii*({material.gamma:.17g})))"
    )
    for oscillator in material.oscillators:
        omega = oscillator["omega_0"]
        epsilon += (
            f"+({oscillator['strength']:.17g})*({omega:.17g})^2"
            f"/(({omega:.17g})^2-w^2-ii*({oscillator['gamma']:.17g})*w)"
        )
    return (
        "MATERIAL ClutchGold\n"
        f"  Eps(w) = {epsilon}\n"
        "  Mu(w) = 1.0\n"
        "ENDMATERIAL\n\n"
    )


def _scuff_geometry_text(material: MaterialModel) -> str:
    name = "PEC" if material.material == "PEC" else "ClutchGold"
    return (
        _scuff_material_text(material)
        + "OBJECT Stator\n"
        "  MESHFILE stator.msh\n"
        f"  MATERIAL {name}\n"
        "ENDOBJECT\n\n"
        "OBJECT Rotor\n"
        "  MESHFILE rotor.msh\n"
        f"  MATERIAL {name}\n"
        "ENDOBJECT\n"
    )


def _header_column(lines: Sequence[str]) -> int | None:
    accepted = {"fz", "zforce", "forcez", "z-force"}
    for line in lines:
        if not line.lstrip().startswith("#"):
            continue
        numbered = list(re.finditer(r"(\d+)\s*:\s*([^#]+?)(?=\s+\d+\s*:|$)", line))
        for match in numbered:
            label = re.sub(r"[^a-z-]", "", match.group(2).lower().split()[0])
            if label in accepted:
                return int(match.group(1)) - 1
        tokens = line.lstrip("# ").split()
        for index, token in enumerate(tokens):
            label = re.sub(r"[^a-z-]", "", token.lower())
            if label in accepted:
                return index
    return None


def _parse_scuff_force(path: Path, explicit_column: int | None) -> float:
    lines = path.read_text(encoding="utf-8").splitlines()
    column = explicit_column if explicit_column is not None else _header_column(lines)
    if column is None:
        raise RuntimeError(
            f"Cannot identify the integrated z-force column in {path}. "
            "Specify --scuff-force-column (zero-based) using the SCUFF output header; "
            "no column or force value will be guessed."
        )
    values: list[float] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if column >= len(fields):
            raise RuntimeError(f"Malformed SCUFF force row in {path}: {stripped}")
        token = fields[column].replace("D", "E").replace("d", "e")
        try:
            value = float(token)
        except ValueError as error:
            raise RuntimeError(f"Nonnumeric SCUFF force field in {path}: {token}") from error
        values.append(_finite_float(value, "SCUFF force"))
    if len(values) != 1:
        raise RuntimeError(
            f"Expected one integrated force row for one transformation in {path}; "
            f"found {len(values)}. Xi-resolved rows must not be summed as forces."
        )
    return values[0]


def export_scuff_files_and_run(
    parameters: Any,
    *,
    output_dir: str | Path = "results/scuff_clutch",
    n_r: int = 2,
    n_phi_tooth: int = 3,
    n_phi_bridge: int = 3,
    n_z: int = 2,
    mesh: ClutchSurfaceMesh | None = None,
    export_only: bool = False,
    timeout_seconds: float | None = None,
    config_file: str | Path | None = None,
    task_id: str | None = None,
    scuff_force_file: str | Path | None = None,
    scuff_force_column: int | None = None,
    scuff_extra_args: Sequence[str] = (),
    record_metrics: bool = True,
) -> dict[str, Any]:
    """Export closed Gmsh surfaces and run SCUFF's vector electromagnetic solver."""
    started = time.perf_counter()
    if timeout_seconds is not None:
        timeout_seconds = _positive_float(timeout_seconds, "timeout_seconds")
    if scuff_force_column is not None:
        scuff_force_column = _integer(
            scuff_force_column, "scuff_force_column", minimum=0
        )
    if not all(isinstance(arg, str) for arg in scuff_extra_args):
        raise TypeError("scuff_extra_args must contain strings.")
    reserved = {"--geometry", "--TransFile", "--FileBase", "--Xi", "--XiFile"}
    if any(arg.split("=", 1)[0] in reserved for arg in scuff_extra_args):
        raise ValueError(
            "SCUFF extra arguments cannot override geometry, transformations, "
            "output basename, or replace integration with individual Xi samples."
        )
    if mesh is None:
        mesh = build_clutch_surface_mesh(
            parameters, n_r, n_phi_tooth, n_phi_bridge, n_z
        )
    material = MaterialModel.from_parameters(mesh.parameters)
    rotor_triangles = _triangular_mesh(mesh.rotor, mesh.geometry.R_max)
    stator_triangles = _triangular_mesh(mesh.stator, mesh.geometry.R_max)
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    _write_gmsh_v2(directory / "rotor.msh", rotor_triangles)
    _write_gmsh_v2(directory / "stator.msh", stator_triangles)
    _atomic_text(directory / "clutch.scuffgeo", _scuff_geometry_text(material))
    _atomic_text(
        directory / "clutch.trans",
        "TRANSFORMATION Identity\n"
        "  OBJECT Rotor\n"
        "    DISPLACED 0 0 0\n"
        "  ENDOBJECT\n"
        "ENDTRANSFORMATION\n",
    )
    binary = shutil.which("scuff-cas3d")
    if binary is None:
        raise RuntimeError(
            "SCUFF meshes were exported to "
            f"{directory}, but scuff-cas3d is not on PATH. "
            "The scuff backend cannot compute a force without the external binary; "
            "no scalar or synthetic fallback was used."
        )
    settings: dict[str, Any] = {
        "method": "SCUFF-EM vector electromagnetic FSC",
        "physical_model": "Maxwell electromagnetic surface currents",
        "exact_electromagnetic_fsc": True,
        "panel_resolution": mesh.panel_resolution,
        "n_panels_rotor": mesh.n_panels_rotor,
        "n_panels_stator": mesh.n_panels_stator,
        "n_panels_total": mesh.n_panels_total,
        "n_triangles_rotor": len(rotor_triangles.triangles),
        "n_triangles_stator": len(stator_triangles.triangles),
        "device": "external scuff-cas3d",
        "quadrature_rule": "SCUFF adaptive imaginary-frequency integration",
        "dispersion_model": material.metadata(),
        "binary": str(Path(binary).resolve()),
        "mesh_units": "um",
        "temperature_K": 0.0,
        "symmetry_multiplier": SYMMETRY_MULTIPLIER,
        "symmetry_method": "full four-sector physical mesh; no extra force multiplier",
        "export_only": export_only,
        "timeout_seconds": timeout_seconds,
        "extra_args": list(scuff_extra_args),
    }
    result = _base_result(mesh, "scuff", settings, config_file, task_id)
    result["exported_files"] = {
        name: str(directory / name)
        for name in ("rotor.msh", "stator.msh", "clutch.scuffgeo", "clutch.trans")
    }
    if export_only:
        result.update({
            "status": "mesh_exported_no_force",
            "elapsed_seconds": time.perf_counter() - started,
            "convergence_note": "No solver run was requested.",
        })
        if record_metrics:
            _record_provenance(result)
        return result

    # Use a fresh basename, so stale output cannot be interpreted as a result.
    basename = f"casimir_{result['fingerprint'][:16]}_{time.time_ns()}"
    command = [
        binary,
        "--geometry", "clutch.scuffgeo",
        "--TransFile", "clutch.trans",
        "--FileBase", basename,
        "--ZForce",
        *scuff_extra_args,
    ]
    settings["command"] = command
    result["fingerprint"] = _fingerprint(mesh, settings)
    stdout_path = directory / f"{basename}.stdout.log"
    stderr_path = directory / f"{basename}.stderr.log"
    try:
        completed = subprocess.run(
            command,
            cwd=directory,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        _atomic_text(
            stdout_path,
            stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout,
        )
        _atomic_text(
            stderr_path,
            stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr,
        )
        raise RuntimeError(
            "SCUFF exceeded its timeout. An incomplete run is not a converged "
            f"force result. Logs: {stdout_path}, {stderr_path}."
        ) from error
    _atomic_text(stdout_path, completed.stdout)
    _atomic_text(stderr_path, completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(
            f"scuff-cas3d exited with code {completed.returncode}. "
            f"Inspect {stderr_path} and {stdout_path} for mesh, material, or "
            "installation errors. No fallback was used."
        )

    if scuff_force_file is not None:
        force_path = Path(scuff_force_file)
        if not force_path.is_absolute():
            force_path = directory / force_path
        if not force_path.is_file():
            raise RuntimeError(f"Requested SCUFF force output does not exist: {force_path}")
        if force_path.stat().st_mtime_ns < stdout_path.stat().st_mtime_ns - 1_000_000_000:
            raise RuntimeError(
                "Explicit SCUFF force output predates this run; refusing stale data."
            )
    else:
        candidates = [
            path for path in directory.glob(f"{basename}*")
            if path.is_file()
            and path not in (stdout_path, stderr_path)
            and path.suffix.lower() in {".out", ".force", ".forces"}
        ]
        identified = [
            path for path in candidates
            if _header_column(path.read_text(encoding="utf-8").splitlines()) is not None
        ]
        if len(identified) != 1:
            raise RuntimeError(
                "Could not uniquely identify SCUFF's integrated z-force output. "
                f"Candidate files: {[str(p) for p in candidates]}. "
                "Supply --scuff-force-file and, if necessary, --scuff-force-column."
            )
        force_path = identified[0]
    force = _parse_scuff_force(force_path, scuff_force_column)
    _set_force(result, force)
    result.update({
        "status": "completed",
        "elapsed_seconds": time.perf_counter() - started,
        "scuff_force_file": str(force_path),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "converged": False,
        "convergence_note": (
            "SCUFF completed its frequency integration; mesh-resolution convergence "
            "has not been independently established."
        ),
        "diagnostics": {
            "watertight_rotor": True,
            "watertight_stator": True,
            "bottom_edge_breakdown_available": False,
            "breakdown_note": (
                "Integrated SCUFF force does not provide the scalar panel-derivative "
                "partition. No face contributions were invented."
            ),
        },
    })
    if record_metrics:
        _record_provenance(result)
    return result


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise TypeError("Configuration JSON must contain an object.")
    return cast(dict[str, Any], config)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Concentric-clutch surface solver. 'bem' supports qualified tangential "
            "vector dyadic and legacy scalar Yukawa models; 'scuff' is electromagnetic FSC."
        )
    )
    parser.add_argument(
        "--config", "--config-file", dest="config", type=Path,
        required=False, default=Path("sweep_configs_clutch_pilot/config_001.json"),
    )
    parser.add_argument("--solver", choices=("bem", "scuff"), default="bem")
    parser.add_argument(
        "--formulation", choices=("vector_dyadic", "scalar_yukawa"),
        default="vector_dyadic",
    )
    parser.add_argument(
        "--z-tip-um", type=float,
        help="Override the rotor tooth bottom z coordinate in micrometres.",
    )
    parser.add_argument("--n-r", type=int, default=2)
    parser.add_argument("--n-phi-tooth", type=int, default=3)
    parser.add_argument("--n-phi-bridge", type=int, default=3)
    parser.add_argument("--n-z", type=int, default=2)
    parser.add_argument("--n-xi", type=int, default=24)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--condition-limit", type=float, default=1.0e14)
    parser.add_argument("--max-memory-gib", type=float, default=4.0)
    parser.add_argument("--task-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scuff-output-dir", type=Path, default=Path("results/scuff_clutch"))
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--scuff-force-file", type=Path)
    parser.add_argument("--scuff-force-column", type=int)
    parser.add_argument(
        "--scuff-extra-arg", action="append", default=[],
        help="Repeat for external SCUFF options; use --scuff-extra-arg=--Option.",
    )
    parser.add_argument(
        "--require-exact-electromagnetics", action="store_true",
        help="Reject approximate BEM models; SCUFF is required for Maxwell FSC.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Permit execution both as a package module and as execution/file.py.
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    args = _parser().parse_args(argv)
    config = _load_config(args.config)
    if args.z_tip_um is not None:
        z_tip = _finite_float(args.z_tip_um, "z_tip")
        config, values = _configuration(config)
        values["z_tip"] = z_tip
        # Update aliases rather than leaving an old alias conflicting with
        # the explicit CLI override, including flattened geometry parameters.
        if "z_tip_um" in values:
            values["z_tip_um"] = z_tip
        for key in ("z_tip", "z_tip_um"):
            if key in config:
                config[key] = z_tip
        config["parameters"] = values
    common: dict[str, Any] = {
        "n_r": args.n_r,
        "n_phi_tooth": args.n_phi_tooth,
        "n_phi_bridge": args.n_phi_bridge,
        "n_z": args.n_z,
        "config_file": args.config.resolve(),
        "task_id": args.task_id,
    }
    if args.solver == "bem":
        if args.export_only:
            raise ValueError("--export-only requires --solver scuff.")
        print(_formulation_qualification(args.formulation), file=sys.stderr)
        result = run_bem_casimir_solver(
            config,
            **common,
            n_xi=args.n_xi,
            max_steps=args.max_steps,
            device=args.device,
            condition_limit=args.condition_limit,
            max_memory_gib=args.max_memory_gib,
            require_exact_electromagnetics=args.require_exact_electromagnetics,
            formulation=args.formulation,
        )
    else:
        if args.max_steps != 0:
            raise ValueError(
                "--max-steps is a BEM quadrature-prefix control. For SCUFF, use "
                "--timeout-seconds; timed-out runs do not return forces."
            )
        result = export_scuff_files_and_run(
            config,
            **common,
            output_dir=args.scuff_output_dir,
            export_only=args.export_only,
            timeout_seconds=args.timeout_seconds,
            scuff_force_file=args.scuff_force_file,
            scuff_force_column=args.scuff_force_column,
            scuff_extra_args=args.scuff_extra_arg,
        )
    output = args.output or Path("results") / f"casimir_{result['task_id']}_{args.solver}.json"
    serialized = json.dumps(_plain(result), indent=2, sort_keys=True, allow_nan=False) + "\n"
    _atomic_text(output, serialized)
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
