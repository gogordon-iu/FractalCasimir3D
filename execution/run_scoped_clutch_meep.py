#!/usr/bin/env python3

"""Run a resumable, sector-scoped 3-D Meep Casimir clutch calculation.

Lengths are in micrometres, and time is in Meep units. The reported force is
the z-directed force. ``both`` includes stator and rotor; ``self`` includes
only the rotor. ``all`` runs both configurations and subtracts their forces.

Each face uses nmax cosine modes in each tangential direction, so there are
36 * nmax**2 moments per configuration. --max-steps produces a deliberately
time-truncated diagnostic result, not a converged force.

Run from the repository root, or invoke this file directly.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib
import inspect
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

MEEP_FORCE_TO_SI = 3.16152649e-14
CACHE_VERSION = 2
ELEMENT_KEYS = (
    "r_inner",
    "r_outer",
    "r_tooth_in",
    "r_tooth_out",
    "r_center",
    "W_slot",
    "w_tooth",
)


class WalltimeReached(RuntimeError):
    """The current moment must be restarted on the next invocation."""


@dataclass(frozen=True)
class Parameters:
    elements: tuple[dict[str, Any], ...]
    theta_deg: float
    t_run: float
    material: str
    resolution: int
    nmax: int
    num_sectors: int
    aperture_arc_deg: float
    bridge_arc_deg: float
    tooth_arc_deg: float
    t_membrane: float
    t_landing_pad: float
    h_teeth: float
    z_tip: float
    l_domain: float
    pml_thickness: float
    courant: float
    n_fractal: int
    gamma: float
    plasma_frequency: float
    epsilon_inf: float
    force_complex_fields: bool = True

    @property
    def sigma(self) -> float:
        return 0.5 / max(0.010, self.z_tip)


@dataclass(frozen=True)
class Face:
    name: str
    axis: int
    orientation: float
    center: tuple[float, float, float]
    size: tuple[float, float, float]

    @property
    def tangent_axes(self) -> tuple[int, int]:
        axes = tuple(axis for axis in range(3) if axis != self.axis)
        return axes[0], axes[1]


class ParallelContext:
    """Use MPI collectives when mpi4py is available, otherwise local decisions."""

    def __init__(self, mp: Any) -> None:
        self.master = bool(mp.am_master())
        self.comm: Any = None
        processors = int(mp.count_processors())
        if processors > 1:
            try:
                from mpi4py import MPI
            except ImportError:
                self.comm = None
                self.master = bool(mp.am_master())
            else:
                self.comm = MPI.COMM_WORLD
                if self.comm.Get_size() != processors:
                    raise RuntimeError(
                        "Meep and mpi4py communicator sizes differ; subgroup runs "
                        "are not supported by this script."
                    )
                self.master = self.comm.Get_rank() == 0

    def broadcast(self, value: Any) -> Any:
        if self.comm is None:
            return value
        return self.comm.bcast(value if self.master else None, root=0)

    def root_call(
        self, function: Callable[[], Any], *, all_ranks_without_comm: bool = False
    ) -> Any:
        result: Any = None
        error: str | None = None
        if self.master or (self.comm is None and all_ranks_without_comm):
            try:
                result = function()
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        error = self.broadcast(error)
        if error is not None:
            raise RuntimeError(error)
        return self.broadcast(result)


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-file", required=True, type=Path)
    parser.add_argument("--task-id", type=positive_integer, default=1)
    parser.add_argument("--config", choices=("both", "self", "all"), default="all")
    parser.add_argument("--max-walltime-hours", type=positive_float, default=7.5)
    parser.add_argument("--max-steps", type=nonnegative_integer, default=0)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--resolution", type=positive_integer)
    return parser


def finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a JSON number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return result


def integer_value(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def read_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("The configuration must be a JSON object")
    return value


def geometry_elements(raw: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    geometry = raw.get("geometry")
    entries = geometry.get("elements") if isinstance(geometry, dict) else geometry
    if not isinstance(entries, list) or not entries:
        raise ValueError("geometry must be a nonempty list or an object containing elements")
    output: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"geometry element {index} must be an object")
        item = dict(entry)
        for key in ELEMENT_KEYS:
            if key not in item:
                raise ValueError(f"geometry element {index} is missing {key}")
            item[key] = finite_number(
                item[key], f"geometry[{index}].{key}", positive=key != "r_inner"
            )
        if item["r_inner"] < 0 or item["r_inner"] >= item["r_outer"]:
            raise ValueError(f"Invalid inner/outer radii in geometry element {index}")
        if item["r_tooth_in"] >= item["r_tooth_out"]:
            raise ValueError(f"Invalid tooth radii in geometry element {index}")
        output.append(item)
    return tuple(output)


def invoke_dynamic_trun(
    function: Callable[..., Any],
    context: Mapping[str, Any],
) -> float:
    """Bind the helper's named arguments rather than guessing positional order."""
    aliases = {
        "config": "raw_config",
        "cfg": "raw_config",
        "config_data": "raw_config",
        "geometry": "elements",
        "geometry_elements": "elements",
        "L_domain_um": "L_domain",
        "L_plate": "L_domain",
        "z_tip_um": "z_tip",
        "H_teeth_um": "H_teeth",
        "t_membrane_um": "t_membrane",
        "t_landing_pad_um": "t_landing_pad",
        "Sigma": "sigma",
        "d_eff": "d_eff",
    }
    signature = inspect.signature(function)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        key = aliases.get(name, name)
        if key in context:
            value = context[key]
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            raise ValueError(
                f"compute_dynamic_Trun requires unknown parameter {name!r}; "
                "provide T_run explicitly or add that parameter to the configuration"
            )
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[name] = value
    return finite_number(function(*args, **kwargs), "computed T_run", positive=True)


def parse_parameters(
    raw: dict[str, Any],
    resolution_override: int | None,
    dynamic_trun: Callable[..., Any],
) -> Parameters:
    elements = geometry_elements(raw)
    geometry = raw["geometry"]

    def get(name: str, default: Any) -> Any:
        if name in raw:
            return raw[name]
        if isinstance(geometry, dict) and name in geometry:
            return geometry[name]
        return default

    resolution = integer_value(
        resolution_override if resolution_override is not None else get("resolution", 60),
        "resolution",
    )
    theta = finite_number(get("theta_deg", 0.0), "theta_deg")
    values = {
        "aperture_arc_deg": finite_number(get("aperture_arc_deg", 30.0), "aperture_arc_deg", positive=True),
        "bridge_arc_deg": finite_number(get("bridge_arc_deg", 60.0), "bridge_arc_deg", positive=True),
        "tooth_arc_deg": finite_number(get("tooth_arc_deg", 15.0), "tooth_arc_deg", positive=True),
        "t_membrane": finite_number(get("t_membrane_um", 0.025), "t_membrane_um", positive=True),
        "t_landing_pad": finite_number(get("t_landing_pad_um", 0.150), "t_landing_pad_um", positive=True),
        "H_teeth": finite_number(get("H_teeth_um", 0.250), "H_teeth_um", positive=True),
        "z_tip": finite_number(get("z_tip_um", 0.015), "z_tip_um", positive=True),
        "L_domain": finite_number(get("L_domain_um", 3.0), "L_domain_um", positive=True),
    }
    if any(values[name] > 360 for name in ("aperture_arc_deg", "bridge_arc_deg", "tooth_arc_deg")):
        raise ValueError("Angular spans must not exceed 360 degrees")
    num_sectors = integer_value(get("num_sectors", 4), "num_sectors")
    if num_sectors != 4:
        raise ValueError("The required F_total = 4 * F_sector0 scaling requires num_sectors=4")
    nmax = integer_value(get("nmax", 1), "nmax")
    pml = finite_number(get("pml_thickness_um", 0.20), "pml_thickness_um", positive=True)
    courant = finite_number(get("courant", 0.5), "courant", positive=True)
    if courant > 0.5:
        raise ValueError("courant must not exceed 0.5 for this 3-D calculation")
    context: dict[str, Any] = dict(raw)
    context.update(values)
    context.update(
        elements=list(elements),
        raw_config=raw,
        resolution=resolution,
        theta_deg=theta,
        num_sectors=num_sectors,
        nmax=nmax,
        sigma=0.5 / max(0.010, values["z_tip"]),
        d_eff=max(0.010, values["z_tip"]),
        dt=courant / resolution,
    )
    t_value = get("T_run", None)
    t_run = (
        invoke_dynamic_trun(dynamic_trun, context)
        if t_value is None
        else finite_number(t_value, "T_run", positive=True)
    )
    material = get("material", "Gold")
    if not isinstance(material, str) or material.lower() not in ("gold", "pec"):
        raise ValueError("material must be 'Gold' or 'PEC'")
    gamma = finite_number(get("gamma", 0.053 / 1.239841984), "gamma")
    if gamma < 0:
        raise ValueError("gamma must be nonnegative")
    force_complex_fields = get("force_complex_fields", True)
    if not isinstance(force_complex_fields, bool):
        raise ValueError("force_complex_fields must be a JSON boolean")
    return Parameters(
        elements=elements,
        theta_deg=theta,
        t_run=t_run,
        material=material,
        resolution=resolution,
        nmax=nmax,
        num_sectors=num_sectors,
        aperture_arc_deg=values["aperture_arc_deg"],
        bridge_arc_deg=values["bridge_arc_deg"],
        tooth_arc_deg=values["tooth_arc_deg"],
        t_membrane=values["t_membrane"],
        t_landing_pad=values["t_landing_pad"],
        h_teeth=values["H_teeth"],
        z_tip=values["z_tip"],
        l_domain=values["L_domain"],
        pml_thickness=pml,
        courant=courant,
        n_fractal=integer_value(get("N_fractal", len(elements)), "N_fractal"),
        gamma=gamma,
        plasma_frequency=finite_number(
            get("plasma_frequency", 9.03 / 1.239841984), "plasma_frequency", positive=True
        ),
        epsilon_inf=finite_number(get("epsilon_inf", 1.0), "epsilon_inf", positive=True),
        force_complex_fields=force_complex_fields,
    )


def cell_dimensions(parameters: Parameters) -> tuple[float, float, float]:
    buffer = 0.10
    margin = 2.0 / parameters.resolution
    z_top = parameters.z_tip + parameters.h_teeth
    # Include the full stator depth, not just the landing pad.
    stator_depth = parameters.t_membrane + parameters.t_landing_pad
    lateral = parameters.l_domain + 2.0 * (parameters.pml_thickness + buffer)
    vertical = 2.0 * (
        max(z_top + margin, stator_depth + margin)
        + buffer
        + parameters.pml_thickness
    )
    return lateral, lateral, vertical


def stress_faces(parameters: Parameters) -> tuple[Face, ...]:
    center = math.radians(15.0 + parameters.theta_deg)
    half_span = math.radians(parameters.tooth_arc_deg / 2.0)
    start, stop = center - half_span, center + half_span
    angles = [start + (stop - start) * index / 720 for index in range(721)]
    first = math.ceil(start / (math.pi / 2))
    last = math.floor(stop / (math.pi / 2))
    angles.extend(index * math.pi / 2 for index in range(first, last + 1))
    radii = (
        min(element["r_tooth_in"] for element in parameters.elements),
        max(element["r_tooth_out"] for element in parameters.elements),
    )
    points = [(radius * math.cos(angle), radius * math.sin(angle)) for radius in radii for angle in angles]
    margin = 2.0 / parameters.resolution
    lower = [
        min(point[0] for point in points) - margin,
        min(point[1] for point in points) - margin,
        parameters.z_tip / 2.0,
    ]
    upper = [
        max(point[0] for point in points) + margin,
        max(point[1] for point in points) + margin,
        parameters.z_tip + parameters.h_teeth + margin,
    ]
    interiors = tuple(
        length / 2.0 - parameters.pml_thickness
        for length in cell_dimensions(parameters)
    )
    if any(
        interior <= 0 or lo <= -interior or hi >= interior
        for lo, hi, interior in zip(lower, upper, interiors)
    ):
        raise ValueError("The stress box intersects the PML; increase L_domain_um")
    if parameters.t_membrane + parameters.t_landing_pad >= interiors[2]:
        raise ValueError("The stator thickness reaches the lower PML")
    midpoint = [(lo + hi) / 2 for lo, hi in zip(lower, upper)]
    extent = [hi - lo for lo, hi in zip(lower, upper)]
    faces: list[Face] = []
    for axis, label in enumerate(("x", "y", "z")):
        for endpoint, orientation, suffix in (
            (lower[axis], -1.0, "min"),
            (upper[axis], 1.0, "max"),
        ):
            face_center = midpoint.copy()
            face_size = extent.copy()
            face_center[axis] = endpoint
            face_size[axis] = 0.0
            faces.append(
                Face(f"{label}{suffix}", axis, orientation, tuple(face_center), tuple(face_size))
            )
    return tuple(faces)


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_checkpoint(path: Path, fingerprint: str, no_cache: bool) -> dict[str, float]:
    if no_cache or not path.exists():
        return {}
    payload = read_config(path)
    if payload.get("version") != CACHE_VERSION or payload.get("fingerprint") != fingerprint:
        return {}
    moments = payload.get("moments")
    if not isinstance(moments, dict):
        raise ValueError(f"Malformed checkpoint: {path}")
    return {
        key: finite_number(value, f"checkpoint moment {key}")
        for key, value in moments.items()
        if isinstance(key, str)
    }


def cosine_amplitude(
    face: Face, modes: tuple[int, int]
) -> Callable[[Any], float]:
    axes = face.tangent_axes
    lengths = (face.size[axes[0]], face.size[axes[1]])
    if min(lengths) <= 0:
        raise ValueError("A stress face must have positive tangential dimensions")
    normalization = math.sqrt(
        (1.0 if modes[0] == 0 else 2.0)
        * (1.0 if modes[1] == 0 else 2.0)
        / (lengths[0] * lengths[1])
    )

    def amplitude(relative_position: Any) -> float:
        coordinates = (
            float(relative_position.x),
            float(relative_position.y),
            float(relative_position.z),
        )
        result = normalization
        for axis, length, mode in zip(axes, lengths, modes):
            result *= math.cos(math.pi * mode * (coordinates[axis] / length + 0.5))
        return result

    return amplitude


def material_pair(mp: Any, parameters: Parameters, electric: bool) -> tuple[Any, Any]:
    conductivity = (
        {"D_conductivity": parameters.sigma}
        if electric
        else {"B_conductivity": parameters.sigma}
    )
    background = mp.Medium(epsilon=1.0, **conductivity)
    if parameters.material.lower() == "pec":
        return background, mp.metal

    from meep.materials import Au

    # Reconstruct poles explicitly without copying native/SWIG objects or
    # mutating the shared Au model. Preserve the Drude sigma * frequency**2.
    susceptibilities = []
    for sus in Au.E_susceptibilities:
        freq_val = sus.frequency
        scale = 1.0
        if isinstance(sus, mp.DrudeSusceptibility):
            susceptibility_type = mp.DrudeSusceptibility
            if freq_val < 1e-5:
                scale = freq_val ** 2
                freq_val = 1.0
        elif isinstance(sus, mp.LorentzianSusceptibility):
            susceptibility_type = mp.LorentzianSusceptibility
        else:
            raise ValueError(f"Unsupported gold susceptibility type: {type(sus).__name__}")
        susceptibilities.append(
            susceptibility_type(
                frequency=freq_val,
                gamma=sus.gamma + (parameters.sigma if electric else 0.0),
                sigma_diag=mp.Vector3(
                    sus.sigma_diag.x * scale,
                    sus.sigma_diag.y * scale,
                    sus.sigma_diag.z * scale,
                ),
                sigma_offdiag=mp.Vector3(
                    sus.sigma_offdiag.x * scale,
                    sus.sigma_offdiag.y * scale,
                    sus.sigma_offdiag.z * scale,
                ),
            )
        )
    material = mp.Medium(
        epsilon_diag=mp.Vector3(
            Au.epsilon_diag.x, Au.epsilon_diag.y, Au.epsilon_diag.z
        ),
        epsilon_offdiag=mp.Vector3(
            Au.epsilon_offdiag.x, Au.epsilon_offdiag.y, Au.epsilon_offdiag.z
        ),
        E_susceptibilities=susceptibilities,
        **conductivity,
    )
    return background, material


def kernel_array(
    mp: Any,
    np: Any,
    t_run: float,
    dt: float,
    sigma: float,
    polarization: Any,
    count: int,
) -> tuple[Any, Any]:
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("The Casimir kernel sample count must be a positive integer")
    owner = mp.make_casimir_gfunc(t_run, dt, sigma, polarization)
    if owner is None:
        raise RuntimeError("make_casimir_gfunc returned a null pointer")
    if isinstance(owner, np.ndarray):
        array = np.asarray(owner)
        if array.ndim != 1:
            raise RuntimeError("make_casimir_gfunc returned a non-vector array")
        if np.iscomplexobj(array):
            if len(array) < count:
                raise RuntimeError("make_casimir_gfunc returned an undersized array")
            array = array[:count]
        else:
            if len(array) < count * 2:
                raise RuntimeError("make_casimir_gfunc returned an undersized array")
            interleaved = array[:count * 2]
            array = interleaved[0::2] + 1j * interleaved[1::2]
    else:
        try:
            pointer = ctypes.cast(owner, ctypes.POINTER(ctypes.c_double))
        except (TypeError, ctypes.ArgumentError):
            pointer = ctypes.cast(int(owner), ctypes.POINTER(ctypes.c_double))
        if not bool(pointer):
            raise RuntimeError("make_casimir_gfunc returned a null pointer")
        interleaved = np.ctypeslib.as_array(pointer, shape=(count * 2,))
        array = interleaved[0::2] + 1j * interleaved[1::2]
    if not bool(np.isfinite(array).all()):
        raise FloatingPointError("The Casimir time kernel contains non-finite values")
    return owner, array


def run_moment(
    *,
    mp: Any,
    np: Any,
    parameters: Parameters,
    configuration: str,
    component: Any,
    electric: bool,
    face: Face,
    mode: int,
    max_steps: int,
    stator_generator: Callable[..., Any],
    rotor_generator: Callable[..., Any],
    guard: Callable[[], None],
) -> tuple[float, int, float]:
    guard()
    background, material = material_pair(mp, parameters, electric)
    geometry: list[Any] = []
    if configuration == "both":
        geometry.extend(
            stator_generator(
                elements=list(parameters.elements),
                L_plate=parameters.l_domain,
                t_membrane=parameters.t_membrane,
                t_landing_pad=parameters.t_landing_pad,
                plate_material=material,
                void_material=background,
                num_sectors=parameters.num_sectors,
                aperture_arc_deg=parameters.aperture_arc_deg,
                bridge_arc_deg=parameters.bridge_arc_deg,
            )
        )
    geometry.extend(
        rotor_generator(
            elements=list(parameters.elements),
            H_teeth=parameters.h_teeth,
            z_tip=parameters.z_tip,
            rotor_material=material,
            num_sectors=parameters.num_sectors,
            tooth_arc_deg=parameters.tooth_arc_deg,
            theta_rotor_deg=parameters.theta_deg,
        )
    )
    timestep = [parameters.courant / parameters.resolution]

    def impulse(t: float) -> float:
        dt = timestep[0]
        return 1.0 / dt if -0.25 * dt <= t < 0.75 * dt else 0.0

    m1, m2 = mode % parameters.nmax, mode // parameters.nmax
    if face.axis == 0:
        mx, my, mz = 0, m1, m2
    elif face.axis == 1:
        mx, my, mz = m1, 0, m2
    else:
        mx, my, mz = m1, m2, 0
    component_direction = {
        mp.Ex: mp.X,
        mp.Ey: mp.Y,
        mp.Ez: mp.Z,
        mp.Hx: mp.X,
        mp.Hy: mp.Y,
        mp.Hz: mp.Z,
    }

    simulation = mp.Simulation(
        cell_size=mp.Vector3(*cell_dimensions(parameters)),
        dimensions=3,
        resolution=parameters.resolution,
        Courant=parameters.courant,
        boundary_layers=[mp.PML(parameters.pml_thickness)],
        default_material=background,
        geometry=geometry,
        sources=[
            mp.Source(
                src=mp.CustomSource(
                    src_func=impulse,
                    start_time=-0.25 * timestep[0],
                    end_time=0.75 * timestep[0],
                ),
                component=component,
                center=mp.Vector3(*face.center),
                size=mp.Vector3(*face.size),
                amp_func=cosine_amplitude(face, (m1, m2)),
            )
        ],
        force_complex_fields=parameters.force_complex_fields,
    )
    try:
        simulation.init_sim()
        dt_value = simulation.fields.dt
        dt = finite_number(
            float(dt_value() if callable(dt_value) else dt_value), "Meep dt", positive=True
        )
        timestep[0] = dt
        full_steps = int(parameters.t_run / dt)
        if full_steps < 1:
            raise ValueError("T_run is shorter than one Meep timestep")
        steps = min(full_steps, max_steps) if max_steps > 0 else full_steps
        field_type = mp.E_stuff if electric else mp.H_stuff
        kernel_owner, gt_arr = kernel_array(
            mp, np, parameters.t_run, dt, parameters.sigma, component, steps
        )
        volume = mp.Volume(center=mp.Vector3(*face.center), size=mp.Vector3(*face.size))
        integral = 0.0
        compensation = 0.0
        for step in range(steps):
            guard()
            simulation.fields.step()
            f_temp = simulation.fields.casimir_stress_dct_integral(
                mp.Z,
                component_direction[component],
                float(mx),
                float(my),
                float(mz),
                field_type,
                volume.swigobj,
            )
            value = float(np.imag(gt_arr[step] * dt * face.orientation * f_temp))
            if not math.isfinite(value):
                raise FloatingPointError(f"Non-finite stress integral at step {step}")
            adjusted = value - compensation
            updated = integral + adjusted
            compensation = (updated - integral) - adjusted
            integral = updated
            if not math.isfinite(integral):
                raise FloatingPointError("The accumulated force overflowed")
        # Keep the native kernel owner alive until the integration is finished.
        del gt_arr, kernel_owner
        return integral, steps, dt
    finally:
        simulation.reset_meep()


def log_metrics(result: Mapping[str, Any], master: bool) -> None:
    if not master:
        return
    try:
        from utils.metrics_logger import export_macros, log_metric

        for name in (
            "F_both",
            "F_self",
            "F_net",
            "f_net_fN",
            "f_net_pN",
            "elapsed_seconds",
            "completed_moments",
        ):
            value = result.get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                log_metric(name, value)
        export_macros()
    except Exception as exc:
        print(f"Warning: metrics logging failed: {exc}", file=sys.stderr, flush=True)


def execute(args: argparse.Namespace, raw: dict[str, Any], started: float) -> int:
    # Delay scientific imports until after argparse and basic JSON parsing.
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    try:
        mp = importlib.import_module("meep")
    except ImportError as exc:
        raise RuntimeError(
            "Meep is required to run the simulation. Load the BigRed 200 "
            "Meep/MPI environment; --help does not require Meep."
        ) from exc
    if not hasattr(mp, "Simulation") or not hasattr(mp, "make_casimir_gfunc"):
        raise RuntimeError("The installed 'meep' module lacks the required Casimir API")
    import numpy as np
    from execution.clutch_geometry_redesign import (
        compute_dynamic_Trun,
        generate_redesigned_rotor_geometry,
        generate_redesigned_stator_geometry,
    )

    parallel = ParallelContext(mp)
    parameters = parse_parameters(raw, args.resolution, compute_dynamic_Trun)
    faces = stress_faces(parameters)
    canonical = {
        "version": CACHE_VERSION,
        "parameters": vars(parameters),
        "max_steps": args.max_steps,
        "force_direction": "z",
        "kernel_polarization": "source_component",
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    checkpoint_directory = Path(".tmp")
    result_directory = Path("results_clutch_pilot")
    progress_path = result_directory / f"progress_task_{args.task_id:03d}.json"
    final_path = result_directory / (
        f"task_{args.task_id:03d}_N{parameters.n_fractal}"
        f"_th_{int(parameters.theta_deg)}deg.json"
    )
    configurations = ("both", "self") if args.config == "all" else (args.config,)
    moments_per_config = 36 * parameters.nmax**2
    checkpoints = {
        name: checkpoint_directory
        / f"chk_moments_clutch_pilot_task_{args.task_id:03d}_{name}.json"
        for name in ("both", "self")
    }
    moments: dict[str, dict[str, float]] = {}
    for name in ("both", "self"):
        # Without mpi4py, every rank reads the same shared-filesystem checkpoint.
        moments[name] = parallel.root_call(
            lambda name=name: load_checkpoint(checkpoints[name], fingerprint, args.no_cache),
            all_ranks_without_comm=True,
        )
    polarizations = (
        ("Ex", mp.Ex, True),
        ("Ey", mp.Ey, True),
        ("Ez", mp.Ez, True),
        ("Hx", mp.Hx, False),
        ("Hy", mp.Hy, False),
        ("Hz", mp.Hz, False),
    )
    expected_keys = {
        f"{label}:{face.name}:{mode}"
        for label, _, _ in polarizations
        for face in faces
        for mode in range(parameters.nmax**2)
    }
    for name in moments:
        moments[name] = {
            key: value for key, value in moments[name].items() if key in expected_keys
        }
    active: dict[str, Any] = {}
    latest_steps: int | None = None
    latest_dt: float | None = None

    def elapsed() -> float:
        return time.monotonic() - started

    def guard() -> None:
        # broadcast is a passthrough without mpi4py, so each rank checks locally.
        expired = parallel.broadcast(elapsed() >= args.max_walltime_hours * 3600.0)
        if expired:
            raise WalltimeReached("Walltime limit reached; unfinished moment is not cached")

    def summary(status: str) -> dict[str, Any]:
        forces: dict[str, float | None] = {}
        for name in ("both", "self"):
            forces[name] = (
                4.0 * math.fsum(moments[name].values())
                if len(moments[name]) == moments_per_config
                else None
            )
        net = (
            forces["both"] - forces["self"]
            if forces["both"] is not None and forces["self"] is not None
            else None
        )
        return {
            "status": status,
            "task_id": args.task_id,
            "config_file": str(args.config_file.resolve()),
            "requested_config": args.config,
            "fingerprint": fingerprint,
            "N_fractal": parameters.n_fractal,
            "theta_deg": parameters.theta_deg,
            "parameters": vars(parameters),
            "Sigma": parameters.sigma,
            "max_steps": args.max_steps,
            "time_truncated": args.max_steps > 0,
            "timesteps_per_last_moment": latest_steps,
            "dt": latest_dt,
            "num_tasks_per_config": moments_per_config,
            "completed_moments": sum(len(moments[name]) for name in configurations),
            "completed_by_config": {name: len(value) for name, value in moments.items()},
            "active_moment": dict(active),
            "elapsed_seconds": elapsed(),
            "F_sector0_both": None if forces["both"] is None else forces["both"] / 4.0,
            "F_sector0_self": None if forces["self"] is None else forces["self"] / 4.0,
            "F_both": forces["both"],
            "F_self": forces["self"],
            "F_net": net,
            "MEEP_FORCE_TO_SI_N": MEEP_FORCE_TO_SI,
            "f_net_N": None if net is None else net * MEEP_FORCE_TO_SI,
            "f_net_fN": None if net is None else net * MEEP_FORCE_TO_SI * 1e15,
            "f_net_pN": None if net is None else net * MEEP_FORCE_TO_SI * 1e12,
            "force_component": "z",
            "symmetry_multiplier": 4.0,
        }

    def save_progress(status: str) -> dict[str, Any]:
        result = summary(status)
        parallel.root_call(lambda: atomic_json(progress_path, result))
        return result

    save_progress("running")
    try:
        for configuration in configurations:
            for label, component, electric in polarizations:
                for face in faces:
                    for mode in range(parameters.nmax**2):
                        key = f"{label}:{face.name}:{mode}"
                        if key in moments[configuration]:
                            continue
                        active.clear()
                        active.update(configuration=configuration, moment=key)
                        save_progress("running")
                        force, latest_steps, latest_dt = run_moment(
                            mp=mp,
                            np=np,
                            parameters=parameters,
                            configuration=configuration,
                            component=component,
                            electric=electric,
                            face=face,
                            mode=mode,
                            max_steps=args.max_steps,
                            stator_generator=generate_redesigned_stator_geometry,
                            rotor_generator=generate_redesigned_rotor_geometry,
                            guard=guard,
                        )
                        # Use the master's value when collectives are available.
                        moments[configuration][key] = parallel.broadcast(force)
                        payload = {
                            "version": CACHE_VERSION,
                            "fingerprint": fingerprint,
                            "configuration": configuration,
                            "moments": moments[configuration],
                            "updated_unix_seconds": time.time(),
                        }
                        parallel.root_call(
                            lambda: atomic_json(checkpoints[configuration], payload)
                        )
                        active.clear()
                        save_progress("running")
        result = save_progress("complete")
        parallel.root_call(lambda: atomic_json(final_path, result))
        log_metrics(result, parallel.master)
        if parallel.master:
            print(f"Saved {final_path}", flush=True)
        return 0
    except WalltimeReached:
        result = save_progress("walltime_reached")
        log_metrics(result, parallel.master)
        if parallel.master:
            print(
                "Walltime limit reached. Resume with the same arguments; "
                "the unfinished moment will be restarted.",
                file=sys.stderr,
                flush=True,
            )
        return 75
    except Exception:
        save_progress("failed")
        raise


def main(argv: Sequence[str] | None = None) -> int:
    started = time.monotonic()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raw = read_config(args.config_file)
        # Validate the geometry before loading Meep or repository geometry code.
        geometry_elements(raw)
        return execute(args, raw, started)
    except (OSError, ValueError, RuntimeError, ImportError, FloatingPointError) as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
