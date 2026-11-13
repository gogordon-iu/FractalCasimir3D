#!/usr/bin/env python3

"""Run a resumable, sector-scoped 3-D Meep Casimir clutch calculation.

Lengths are in micrometres, and time is in Meep units. The reported force is
the z-directed force. ``both`` includes stator and rotor; ``rotor`` (or its
alias ``self``) includes only the rotor; ``stator`` includes only the stator;
``vac`` includes neither. ``all`` runs all four configurations and computes
F_both - F_rotor - F_stator + F_vac.

Each face uses nmax cosine modes in each tangential direction, with six
polarizations per mode. --max-steps produces a deliberately time-truncated
diagnostic result, not a converged force. When Meep is unavailable,
--max-steps runs a NumPy 3-D Yee-grid micro-probe instead.

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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from execution.clutch_geometry_redesign import (
    DEFAULT_APERTURE_ARC_DEG,
    DEFAULT_BRIDGE_ARC_DEG,
    DEFAULT_H_TEETH_UM,
    DEFAULT_NUM_SECTORS,
    DEFAULT_T_LANDING_PAD_UM,
    DEFAULT_T_MEMBRANE_UM,
    DEFAULT_TOOTH_ARC_DEG,
    DEFAULT_TOOTH_CENTER_OFFSET_DEG,
    DEFAULT_Z_PAD_TOP_UM,
    DEFAULT_Z_TIP_UM,
)
from execution.materials_database_dispersive import (
    EV_TO_MEEP_FREQ as EV_TO_MEEP_CYCLICAL_UM,
    GOLD_EPS_INF as DEFAULT_GOLD_EPS_INF,
    GOLD_GAMMA_EV as DEFAULT_GOLD_GAMMA_EV,
    GOLD_WP_EV as DEFAULT_GOLD_WP_EV,
    MEEP_FORCE_TO_SI,
)

CACHE_VERSION = 6
ALL_CONFIGURATIONS = ("both", "rotor", "stator", "vac")
DEFAULT_RESOLUTION = 60
DEFAULT_L_DOMAIN_UM = 3.0
DEFAULT_PML_THICKNESS_UM = 0.25
DEFAULT_CELL_BUFFER_UM = 0.15
DEFAULT_COURANT = 0.5
MIN_D_EFF_UM = 0.010
STRESS_BOX_GRID_MARGIN_CELLS = 2.0
STRESS_BOX_MAX_CLEARANCE_FRACTION = 0.35
MICRO_PROBE_MAX_GRID_POINTS = 96
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
    z_pad_top: float | None = None
    d_eff: float = DEFAULT_Z_TIP_UM
    stress_box_mode: str = "legacy"
    tooth_center_offset_deg: float = DEFAULT_TOOTH_CENTER_OFFSET_DEG
    fixed_stress_box_margin_um: float | None = None
    eps_averaging: bool = False
    geometry_mode: str = "cylindrical"
    cell_buffer_um: float = DEFAULT_CELL_BUFFER_UM
    r_edge_nm: float = 0.0
    sector0_crop: bool = False
    explicit_rotor_boxes: tuple[tuple[float, float, float, float, float, float], ...] = ()
    explicit_stator_boxes: tuple[tuple[float, float, float, float, float, float], ...] = ()
    explicit_stress_boxes: tuple[tuple[float, float, float, float, float, float], ...] = ()
    explicit_cell_center: tuple[float, float, float] | None = None
    explicit_phys_bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None = None

    @property
    def sigma(self) -> float:
        return 0.5 / max(MIN_D_EFF_UM, self.d_eff)


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
    """Use MPI collectives or shard serial Meep processes launched by Slurm."""

    def __init__(self, mp: Any) -> None:
        self.master = bool(mp.am_master())
        self.comm: Any = None
        self.shard_count = 1
        self.shard_rank = 0
        processors = int(mp.count_processors())
        if processors == 1:
            slurm_ntasks = int(os.environ.get("SLURM_NTASKS", "1"))
            if slurm_ntasks > 1:
                slurm_procid = int(os.environ.get("SLURM_PROCID", "0"))
                if not 0 <= slurm_procid < slurm_ntasks:
                    raise ValueError("SLURM_PROCID must be within SLURM_NTASKS")
                self.shard_count = slurm_ntasks
                self.shard_rank = slurm_procid
                self.master = slurm_procid == 0
                if not self.master:
                    mp.verbosity(0)
        elif processors > 1:
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
    rotational_config = Path("sweep_configs_rotational_z_eff_meep/config_001.json")
    parser.add_argument(
        "--config-file",
        required=False,
        type=Path,
        default=(
            rotational_config
            if rotational_config.exists()
            else Path("sweep_configs_clutch_pilot/config_001.json")
        ),
    )
    parser.add_argument("--solver", choices=("meep", "bem", "scuff"), default="meep")
    parser.add_argument("--task-id", type=positive_integer, default=1)
    parser.add_argument(
        "--config",
        choices=("both", "rotor", "self", "stator", "vac", "all"),
        default="all",
    )
    parser.add_argument("--max-walltime-hours", type=positive_float, default=7.5)
    parser.add_argument("--max-steps", type=nonnegative_integer, default=0)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--checkpoint-prefix", type=str, default="chk_moments_clutch_pilot_task"
    )
    parser.add_argument("--resolution", type=positive_integer)
    parser.add_argument("--nmax", type=positive_integer, default=None)
    parser.add_argument(
        "--material", choices=("PEC", "Gold", "Gold_Drude", "pec", "gold", "gold_drude"), default=None
    )
    parser.add_argument(
        "--fixed-stress-box-margin-um", type=positive_float, default=None
    )
    parser.add_argument("--eps-averaging", action="store_true", default=None)
    parser.add_argument(
        "--geometry-mode",
        choices=("cylindrical", "rectilinear_xz", "explicit_boxes_3d"),
        default=None,
    )
    parser.add_argument("--r-edge-nm", type=float, default=None)
    parser.add_argument("--sector0-crop", action="store_true", default=None)
    parser.add_argument("--bem-n-xi", type=positive_integer, default=24)
    parser.add_argument("--bem-n-r", type=positive_integer, default=2)
    parser.add_argument("--bem-n-phi-tooth", type=positive_integer, default=3)
    parser.add_argument("--bem-n-phi-bridge", type=positive_integer, default=3)
    parser.add_argument("--bem-n-z", type=positive_integer, default=2)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output-file", type=Path, default=None)
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


def _extract_r_edge_nm(raw: Mapping[str, Any]) -> tuple[float, bool]:
    geometry = raw.get("geometry")
    geom_dict = geometry if isinstance(geometry, Mapping) else {}
    if "r_edge_nm" in raw and raw["r_edge_nm"] is not None:
        r_edge_raw = raw["r_edge_nm"]
    elif "r_edge_nm" in geom_dict and geom_dict["r_edge_nm"] is not None:
        r_edge_raw = geom_dict["r_edge_nm"]
    else:
        r_edge_raw = 0.0
    r_edge_nm = finite_number(r_edge_raw, "r_edge_nm")
    if r_edge_nm < 0.0:
        raise ValueError("r_edge_nm must be nonnegative")
    if "r_edge_preapplied" in raw and raw["r_edge_preapplied"] is not None:
        preapplied_raw = raw["r_edge_preapplied"]
    else:
        preapplied_raw = geom_dict.get("r_edge_preapplied", False)
    if not isinstance(preapplied_raw, bool):
        raise ValueError("r_edge_preapplied must be a JSON boolean")
    return r_edge_nm, preapplied_raw


def geometry_elements(raw: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    geometry = raw.get("geometry")
    entries = geometry.get("elements") if isinstance(geometry, dict) else geometry
    if not isinstance(entries, list) or not entries:
        raise ValueError("geometry must be a nonempty list or an object containing elements")
    r_edge_nm, r_edge_preapplied = _extract_r_edge_nm(raw)
    delta_w_um = (
        -2.0 * (1.0 - math.pi / 4.0) * (r_edge_nm * 1e-3)
        if (r_edge_nm > 0.0 and not r_edge_preapplied)
        else 0.0
    )
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
        if delta_w_um != 0.0:
            w_orig = item["r_tooth_out"] - item["r_tooth_in"]
            if 2.0 * (r_edge_nm * 1e-3) >= w_orig or w_orig + delta_w_um <= 0.005:
                raise ValueError(
                    f"r_edge_nm={r_edge_nm} exceeds the allowable corner radius for geometry element {index}"
                )
            c_r = 0.5 * (item["r_tooth_in"] + item["r_tooth_out"])
            w_r = w_orig + delta_w_um
            item["r_tooth_in"] = c_r - 0.5 * w_r
            item["r_tooth_out"] = c_r + 0.5 * w_r
            item["w_tooth"] = w_r
        for key in ("z_tip", "h_teeth"):
            if key in item:
                if item[key] is None:
                    # A null optional override uses the global value.
                    item.pop(key)
                else:
                    item[key] = finite_number(
                        item[key],
                        f"geometry[{index}].{key}",
                        positive=key == "h_teeth",
                    )
        if item["r_inner"] < 0 or item["r_inner"] >= item["r_outer"]:
            raise ValueError(f"Invalid inner/outer radii in geometry element {index}")
        if not (
            0.0 < item["r_tooth_in"] < item["r_tooth_out"]
            and item["r_inner"] < item["r_tooth_in"]
            and item["r_tooth_out"] < item["r_outer"]
        ):
            raise ValueError(f"Invalid tooth radii or slot bounds in geometry element {index}")
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
        "z_pad_top_um": "z_pad_top",
        "H_teeth_um": "H_teeth",
        "t_membrane_um": "t_membrane",
        "t_landing_pad_um": "t_landing_pad",
        "Sigma": "sigma",
        "d_eff": "d_eff",
        "d_eff_um": "d_eff",
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
    result = function(*args, **kwargs)
    if isinstance(result, (tuple, list)):
        if not result:
            raise ValueError("computed T_run result must not be empty")
        result = result[0]
    return finite_number(result, "computed T_run", positive=True)


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
        resolution_override if resolution_override is not None else get("resolution", DEFAULT_RESOLUTION),
        "resolution",
    )
    theta = finite_number(get("theta_deg", 0.0), "theta_deg")
    tooth_center_offset_deg = finite_number(
        get("tooth_center_offset_deg", DEFAULT_TOOTH_CENTER_OFFSET_DEG),
        "tooth_center_offset_deg",
    )
    values = {
        "aperture_arc_deg": finite_number(get("aperture_arc_deg", DEFAULT_APERTURE_ARC_DEG), "aperture_arc_deg", positive=True),
        "bridge_arc_deg": finite_number(get("bridge_arc_deg", DEFAULT_BRIDGE_ARC_DEG), "bridge_arc_deg", positive=True),
        "tooth_arc_deg": finite_number(get("tooth_arc_deg", DEFAULT_TOOTH_ARC_DEG), "tooth_arc_deg", positive=True),
        "t_membrane": finite_number(get("t_membrane_um", DEFAULT_T_MEMBRANE_UM), "t_membrane_um", positive=True),
        "t_landing_pad": finite_number(get("t_landing_pad_um", DEFAULT_T_LANDING_PAD_UM), "t_landing_pad_um", positive=True),
        "H_teeth": finite_number(get("H_teeth_um", DEFAULT_H_TEETH_UM), "H_teeth_um", positive=True),
        "z_tip": finite_number(get("z_tip_um", DEFAULT_Z_TIP_UM), "z_tip_um"),
        "L_domain": finite_number(get("L_domain_um", DEFAULT_L_DOMAIN_UM), "L_domain_um", positive=True),
    }
    if values["z_tip"] == 0:
        raise ValueError("z_tip_um must be nonzero")
    z_pad_value = get("z_pad_top_um", None)
    z_pad_top = (
        finite_number(z_pad_value, "z_pad_top_um")
        if z_pad_value is not None
        else (DEFAULT_Z_PAD_TOP_UM if values["z_tip"] < 0 else None)
    )
    if values["z_tip"] < 0:
        if z_pad_top is None or not (
            z_pad_top < values["z_tip"] and z_pad_top < -values["t_membrane"]
        ):
            raise ValueError(
                "For negative z_tip_um, z_pad_top_um must be below both "
                "z_tip_um and -t_membrane_um"
            )
        for index, element in enumerate(elements):
            if element.get("z_tip", values["z_tip"]) <= z_pad_top:
                raise ValueError(
                    f"geometry[{index}].z_tip must be strictly above z_pad_top_um"
                )
        d_eff = min(
            abs(values["z_tip"] - z_pad_top),
            min(
                abs(element.get("z_tip", values["z_tip"]) - z_pad_top)
                for element in elements
            ),
            min((element["W_slot"] - element["w_tooth"]) / 2.0 for element in elements),
        )
        d_eff = finite_number(d_eff, "d_eff", positive=True)
    else:
        d_eff = max(MIN_D_EFF_UM, values["z_tip"])
    stress_box_mode = get(
        "stress_box_mode",
        "per_tooth_rotor_frame" if values["z_tip"] < 0 else "legacy",
    )
    if not isinstance(stress_box_mode, str) or stress_box_mode not in (
        "legacy", "per_tooth_rotor_frame"
    ):
        raise ValueError("stress_box_mode must be 'legacy' or 'per_tooth_rotor_frame'")
    if any(values[name] > 360 for name in ("aperture_arc_deg", "bridge_arc_deg", "tooth_arc_deg")):
        raise ValueError("Angular spans must not exceed 360 degrees")
    num_sectors = integer_value(get("num_sectors", DEFAULT_NUM_SECTORS), "num_sectors")
    if num_sectors != DEFAULT_NUM_SECTORS:
        raise ValueError("The required F_total = 4 * F_sector0 scaling requires num_sectors=4")
    nmax = integer_value(get("nmax", 1), "nmax")
    pml = finite_number(get("pml_thickness_um", DEFAULT_PML_THICKNESS_UM), "pml_thickness_um", positive=True)
    courant = finite_number(get("courant", DEFAULT_COURANT), "courant", positive=True)
    if courant > DEFAULT_COURANT:
        raise ValueError("courant must not exceed 0.5 for this 3-D calculation")
    context: dict[str, Any] = dict(raw)
    context.update(values)
    context.update(
        elements=list(elements),
        raw_config=raw,
        resolution=resolution,
        theta_deg=theta,
        tooth_center_offset_deg=tooth_center_offset_deg,
        num_sectors=num_sectors,
        nmax=nmax,
        z_pad_top=z_pad_top,
        stress_box_mode=stress_box_mode,
        sigma=0.5 / max(MIN_D_EFF_UM, d_eff),
        d_eff=d_eff,
        dt=courant / resolution,
    )
    t_value = get("T_run", None)
    t_run = (
        invoke_dynamic_trun(dynamic_trun, context)
        if t_value is None
        else finite_number(t_value, "T_run", positive=True)
    )
    material = get("material", "Gold")
    if not isinstance(material, str) or material.lower() not in ("gold", "gold_drude", "pec"):
        raise ValueError("material must be 'Gold', 'Gold_Drude', or 'PEC'")
    cell_buffer_um = finite_number(
        get("cell_buffer_um", DEFAULT_CELL_BUFFER_UM), "cell_buffer_um", positive=True
    )
    gamma = finite_number(
        get("gamma", DEFAULT_GOLD_GAMMA_EV * EV_TO_MEEP_CYCLICAL_UM), "gamma"
    )
    if gamma < 0:
        raise ValueError("gamma must be nonnegative")
    force_complex_fields = get("force_complex_fields", True)
    if not isinstance(force_complex_fields, bool):
        raise ValueError("force_complex_fields must be a JSON boolean")
    fixed_margin_raw = get("fixed_stress_box_margin_um", None)
    fixed_stress_box_margin_um = (
        finite_number(fixed_margin_raw, "fixed_stress_box_margin_um", positive=True)
        if fixed_margin_raw is not None
        else None
    )
    eps_averaging = get("eps_averaging", False)
    if not isinstance(eps_averaging, bool):
        raise ValueError("eps_averaging must be a JSON boolean")
    geometry_mode = get("geometry_mode", "cylindrical")
    if not isinstance(geometry_mode, str) or geometry_mode not in (
        "cylindrical",
        "rectilinear_xz",
        "explicit_boxes_3d",
    ):
        raise ValueError("geometry_mode must be 'cylindrical', 'rectilinear_xz', or 'explicit_boxes_3d'")

    def _parse_box_list(key_name: str) -> tuple[tuple[float, float, float, float, float, float], ...]:
        raw_boxes = get(key_name, [])
        if not isinstance(raw_boxes, list) or not raw_boxes:
            raise ValueError(f"{key_name} must be a non-empty list of [x0, x1, y0, y1, z0, z1] boxes")
        parsed_boxes: list[tuple[float, float, float, float, float, float]] = []
        for b_idx, box in enumerate(raw_boxes):
            if not isinstance(box, (list, tuple)) or len(box) != 6:
                raise ValueError(f"{key_name}[{b_idx}] must have 6 coordinates [x0, x1, y0, y1, z0, z1]")
            coords = tuple(finite_number(c, f"{key_name}[{b_idx}][{c_idx}]") for c_idx, c in enumerate(box))
            if not (coords[0] < coords[1] and coords[2] < coords[3] and coords[4] < coords[5]):
                raise ValueError(f"{key_name}[{b_idx}] requires x0 < x1, y0 < y1, z0 < z1")
            parsed_boxes.append(coords)
        return tuple(parsed_boxes)

    explicit_rotor_boxes: tuple[tuple[float, float, float, float, float, float], ...] = ()
    explicit_stator_boxes: tuple[tuple[float, float, float, float, float, float], ...] = ()
    explicit_stress_boxes: tuple[tuple[float, float, float, float, float, float], ...] = ()
    explicit_cell_center: tuple[float, float, float] | None = None
    explicit_phys_bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None = None

    if geometry_mode == "explicit_boxes_3d":
        explicit_rotor_boxes = _parse_box_list("explicit_rotor_boxes")
        explicit_stator_boxes = _parse_box_list("explicit_stator_boxes")
        explicit_stress_boxes = _parse_box_list("explicit_stress_boxes")
        d_eff_override = get("d_eff_um", None)
        if d_eff_override is not None:
            d_eff = finite_number(d_eff_override, "d_eff_um", positive=True)

        # Enforce strict vacuum clearance between rotor, stress boxes, and stator!
        tol_um = 1.0e-3  # >= 1 nm strict separation
        for r_idx, rb in enumerate(explicit_rotor_boxes):
            inside_any = any(
                sb[0] + tol_um <= rb[0] and rb[1] <= sb[1] - tol_um
                and sb[2] + tol_um <= rb[2] and rb[3] <= sb[3] - tol_um
                and sb[4] + tol_um <= rb[4] and rb[5] <= sb[5] - tol_um
                for sb in explicit_stress_boxes
            )
            if not inside_any:
                raise ValueError(f"explicit_rotor_boxes[{r_idx}] must lie strictly inside an explicit_stress_box")
        for s_idx, stb in enumerate(explicit_stator_boxes):
            for sb_idx, sb in enumerate(explicit_stress_boxes):
                separated = (
                    stb[1] <= sb[0] - tol_um or stb[0] >= sb[1] + tol_um
                    or stb[3] <= sb[2] - tol_um or stb[2] >= sb[3] + tol_um
                    or stb[5] <= sb[4] - tol_um or stb[4] >= sb[5] + tol_um
                )
                if not separated:
                    raise ValueError(
                        f"explicit_stator_boxes[{s_idx}] intersects or touches explicit_stress_boxes[{sb_idx}]"
                    )

        raw_cc = get("explicit_cell_center", None)
        if raw_cc is not None:
            if not isinstance(raw_cc, (list, tuple)) or len(raw_cc) != 3:
                raise ValueError("explicit_cell_center must be [cx, cy, cz]")
            explicit_cell_center = (
                finite_number(raw_cc[0], "explicit_cell_center[0]"),
                finite_number(raw_cc[1], "explicit_cell_center[1]"),
                finite_number(raw_cc[2], "explicit_cell_center[2]"),
            )
        raw_pb = get("explicit_phys_bounds", None)
        if raw_pb is not None:
            if not isinstance(raw_pb, (list, tuple)) or len(raw_pb) != 3:
                raise ValueError("explicit_phys_bounds must be [[xmin, xmax], [ymin, ymax], [zmin, zmax]]")
            pb_parsed: list[tuple[float, float]] = []
            for a_idx, pair in enumerate(raw_pb):
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise ValueError(f"explicit_phys_bounds[{a_idx}] must be [min, max]")
                lo = finite_number(pair[0], f"explicit_phys_bounds[{a_idx}][0]")
                hi = finite_number(pair[1], f"explicit_phys_bounds[{a_idx}][1]")
                if lo >= hi:
                    raise ValueError(f"explicit_phys_bounds[{a_idx}] requires min < max")
                pb_parsed.append((lo, hi))
            explicit_phys_bounds = (pb_parsed[0], pb_parsed[1], pb_parsed[2])
        else:
            all_b = (*explicit_rotor_boxes, *explicit_stator_boxes, *explicit_stress_boxes)
            explicit_phys_bounds = (
                (min(b[0] for b in all_b), max(b[1] for b in all_b)),
                (min(b[2] for b in all_b), max(b[3] for b in all_b)),
                (min(b[4] for b in all_b), max(b[5] for b in all_b)),
            )

    r_edge_nm, _ = _extract_r_edge_nm(raw)
    sector0_crop = get("sector0_crop", False)
    if not isinstance(sector0_crop, bool):
        raise ValueError("sector0_crop must be a JSON boolean")
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
            get("plasma_frequency", DEFAULT_GOLD_WP_EV * EV_TO_MEEP_CYCLICAL_UM),
            "plasma_frequency",
            positive=True,
        ),
        epsilon_inf=finite_number(
            get("epsilon_inf", DEFAULT_GOLD_EPS_INF), "epsilon_inf", positive=True
        ),
        force_complex_fields=force_complex_fields,
        z_pad_top=z_pad_top,
        d_eff=d_eff,
        stress_box_mode=stress_box_mode,
        tooth_center_offset_deg=tooth_center_offset_deg,
        fixed_stress_box_margin_um=fixed_stress_box_margin_um,
        eps_averaging=eps_averaging,
        geometry_mode=geometry_mode,
        cell_buffer_um=cell_buffer_um,
        r_edge_nm=r_edge_nm,
        sector0_crop=sector0_crop,
        explicit_rotor_boxes=explicit_rotor_boxes,
        explicit_stator_boxes=explicit_stator_boxes,
        explicit_stress_boxes=explicit_stress_boxes,
        explicit_cell_center=explicit_cell_center,
        explicit_phys_bounds=explicit_phys_bounds,
    )


def meep_solver_parameters(
    parameters: Parameters,
    args: argparse.Namespace,
    latest_steps: int | None,
    latest_dt: float | None,
) -> dict[str, Any]:
    return {
        "solver": "meep",
        "method": "3D_FDTD_Wick_Rotated_Stress_Tensor_DCT",
        "resolution": parameters.resolution,
        "dx_um": 1.0 / parameters.resolution,
        "courant": parameters.courant,
        "t_run": parameters.t_run,
        "sigma": parameters.sigma,
        "nmax": parameters.nmax,
        "moments_per_config": 6 * len(stress_faces(parameters)) * parameters.nmax**2,
        "configurations": list(ALL_CONFIGURATIONS),
        "inclusion_exclusion_passes": 4,
        "pml_thickness": parameters.pml_thickness,
        "force_complex_fields": parameters.force_complex_fields,
        "fixed_stress_box_margin_um": parameters.fixed_stress_box_margin_um,
        "eps_averaging": parameters.eps_averaging,
        "geometry_mode": parameters.geometry_mode,
        "r_edge_nm": parameters.r_edge_nm,
        "sector0_crop": parameters.sector0_crop,
        "cell_dimensions_um": cell_dimensions(parameters),
        "cell_center_um": cell_center(parameters),
        "max_steps": args.max_steps,
        "timesteps_per_last_moment": latest_steps,
        "dt": latest_dt,
    }


def _sector0_phys_bounds(
    parameters: Parameters,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    if parameters.stress_box_mode != "per_tooth_rotor_frame":
        raise ValueError("sector0_crop requires stress_box_mode='per_tooth_rotor_frame'")
    max_arc_deg = max(parameters.aperture_arc_deg, parameters.tooth_arc_deg)
    if not 0.0 < max_arc_deg < 90.0:
        raise ValueError("sector0_crop requires aperture_arc_deg and tooth_arc_deg in (0, 90) degrees")
    margin = (
        parameters.fixed_stress_box_margin_um
        if parameters.fixed_stress_box_margin_um is not None
        else STRESS_BOX_GRID_MARGIN_CELLS / parameters.resolution
    )
    alpha_slot = math.radians(max_arc_deg / 2.0)
    r_in_min = min(float(el["r_inner"]) for el in parameters.elements)
    r_out_max = max(float(el["r_outer"]) for el in parameters.elements)
    r_in_bound = max(0.0, r_in_min - 0.12)
    r_out_bound = r_out_max + 0.05
    x_min = max(0.0, r_in_bound * math.cos(alpha_slot) - margin)
    x_max = r_out_bound + margin
    y_max = r_out_bound * math.sin(alpha_slot) + 0.05 + margin
    z_top = max(
        float(element.get("z_tip", parameters.z_tip))
        + float(element.get("h_teeth", parameters.h_teeth))
        for element in parameters.elements
    )
    stator_depth = (
        abs(parameters.z_pad_top) + parameters.t_landing_pad
        if parameters.z_pad_top is not None
        else parameters.t_membrane + parameters.t_landing_pad
    )
    z_min = -(stator_depth + margin)
    z_max = z_top + margin
    return (x_min, x_max), (-y_max, y_max), (z_min, z_max)


def cell_center(parameters: Parameters) -> tuple[float, float, float]:
    if parameters.geometry_mode == "explicit_boxes_3d":
        if parameters.explicit_cell_center is not None:
            return parameters.explicit_cell_center
        assert parameters.explicit_phys_bounds is not None
        (x_min, x_max), (y_min, y_max), (z_min, z_max) = parameters.explicit_phys_bounds
        return (0.5 * (x_min + x_max), 0.5 * (y_min + y_max), 0.5 * (z_min + z_max))
    if not parameters.sector0_crop:
        return (0.0, 0.0, 0.0)
    (x_min, x_max), (y_min, y_max), (z_min, z_max) = _sector0_phys_bounds(parameters)
    return (0.5 * (x_min + x_max), 0.5 * (y_min + y_max), 0.5 * (z_min + z_max))


def cell_dimensions(parameters: Parameters) -> tuple[float, float, float]:
    buffer = parameters.cell_buffer_um
    if parameters.geometry_mode == "explicit_boxes_3d":
        assert parameters.explicit_phys_bounds is not None
        centers = cell_center(parameters)
        dims_list: list[float] = []
        for (lo, hi), cc in zip(parameters.explicit_phys_bounds, centers):
            half_extent = max(cc - lo, hi - cc) + buffer + parameters.pml_thickness
            dims_list.append(round(2.0 * half_extent, 12))
        return (dims_list[0], dims_list[1], dims_list[2])
    if parameters.sector0_crop:
        (x_min, x_max), (y_min, y_max), (z_min, z_max) = _sector0_phys_bounds(parameters)
        pad = 2.0 * (buffer + parameters.pml_thickness)
        return (x_max - x_min + pad, y_max - y_min + pad, z_max - z_min + pad)
    margin = (
        parameters.fixed_stress_box_margin_um
        if parameters.fixed_stress_box_margin_um is not None
        else STRESS_BOX_GRID_MARGIN_CELLS / parameters.resolution
    )
    z_top = max(
        element.get("z_tip", parameters.z_tip)
        + element.get("h_teeth", parameters.h_teeth)
        for element in parameters.elements
    )
    stator_depth = (
        abs(parameters.z_pad_top) + parameters.t_landing_pad
        if parameters.z_pad_top is not None
        else parameters.t_membrane + parameters.t_landing_pad
    )
    lateral = parameters.l_domain + 2.0 * (parameters.pml_thickness + buffer)
    vertical = 2.0 * (
        max(z_top + margin, stator_depth + margin)
        + buffer
        + parameters.pml_thickness
    )
    return lateral, lateral, vertical


def stress_faces(parameters: Parameters) -> tuple[Face, ...]:
    dims = cell_dimensions(parameters)
    centers = cell_center(parameters)
    interiors = tuple(
        length / 2.0 - parameters.pml_thickness
        for length in dims
    )
    if parameters.geometry_mode != "explicit_boxes_3d":
        stator_depth = (
            abs(parameters.z_pad_top) + parameters.t_landing_pad
            if parameters.z_pad_top is not None
            else parameters.t_membrane + parameters.t_landing_pad
        )
        if -stator_depth <= centers[2] - interiors[2]:
            raise ValueError("The stator thickness reaches the lower PML")

    def box_faces(
        lower: list[float], upper: list[float], prefix: str = ""
    ) -> list[Face]:
        if any(
            not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi
            for lo, hi in zip(lower, upper)
        ):
            raise ValueError("The stress box must have finite, positive dimensions")
        if any(
            interior <= 0 or lo <= center_c - interior or hi >= center_c + interior
            for lo, hi, center_c, interior in zip(lower, upper, centers, interiors)
        ):
            raise ValueError("The stress box intersects the PML; increase L_domain_um")
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
                    Face(
                        f"{prefix}{label}{suffix}",
                        axis,
                        orientation,
                        tuple(face_center),
                        tuple(face_size),
                    )
                )
        return faces

    if parameters.geometry_mode == "explicit_boxes_3d":
        for box_group in (parameters.explicit_rotor_boxes, parameters.explicit_stator_boxes):
            for bx in box_group:
                for axis_i, (lo_c, hi_c) in enumerate(((bx[0], bx[1]), (bx[2], bx[3]), (bx[4], bx[5]))):
                    if lo_c <= centers[axis_i] - interiors[axis_i] or hi_c >= centers[axis_i] + interiors[axis_i]:
                        raise ValueError("An explicit solid box intersects the PML; increase cell_buffer_um")
        explicit_faces: list[Face] = []
        for idx, sb in enumerate(parameters.explicit_stress_boxes):
            explicit_faces.extend(
                box_faces([sb[0], sb[2], sb[4]], [sb[1], sb[3], sb[5]], prefix=f"b{idx}_")
            )
        return tuple(explicit_faces)

    if parameters.z_tip < 0 or parameters.stress_box_mode == "per_tooth_rotor_frame":
        alpha = math.radians(parameters.tooth_arc_deg / 2.0)
        if not 0 < alpha < math.pi / 2:
            raise ValueError("Per-tooth stress boxes require tooth_arc_deg < 180")
        pad_top = parameters.z_pad_top
        if pad_top is None:
            if parameters.z_tip < 0:
                raise ValueError("Negative z_tip requires z_pad_top")
            pad_top = 0.0
        if pad_top >= parameters.z_tip:
            raise ValueError("The landing pad must lie below the rotor tip")
        faces: list[Face] = []
        raw_grid_margin = (
            parameters.fixed_stress_box_margin_um
            if parameters.fixed_stress_box_margin_um is not None
            else STRESS_BOX_GRID_MARGIN_CELLS / parameters.resolution
        )
        for idx, element in enumerate(parameters.elements):
            el_z_tip = float(element.get("z_tip", parameters.z_tip))
            el_h_teeth = float(element.get("h_teeth", parameters.h_teeth))
            if pad_top >= el_z_tip:
                raise ValueError(f"The landing pad must lie below tooth {idx}'s rotor tip")
            clearance = (element["W_slot"] - element["w_tooth"]) / 2.0
            if clearance <= 0:
                raise ValueError(f"Tooth {idx} requires W_slot > w_tooth")
            margin = min(
                raw_grid_margin,
                STRESS_BOX_MAX_CLEARANCE_FRACTION * clearance,
            )
            if parameters.geometry_mode == "rectilinear_xz":
                x_tooth_min = element["r_tooth_in"]
                x_tooth_max = element["r_tooth_out"]
                y_tooth_max = element["r_tooth_out"] * math.sin(alpha)
                x_min = 0.5 * (element["r_inner"] + x_tooth_min)
                y_max = y_tooth_max + margin
                r_out_limit = element["r_outer"]
                x_max = 0.5 * (x_tooth_max + r_out_limit)
            else:
                x_tooth_min = element["r_tooth_in"] * math.cos(alpha)
                x_tooth_max = element["r_tooth_out"]
                y_tooth_max = element["r_tooth_out"] * math.sin(alpha)
                x_min = 0.5 * (element["r_inner"] + x_tooth_min)
                y_max = y_tooth_max + margin
                r_out_limit = math.sqrt(max(0.0, element["r_outer"]**2 - y_max**2))
                x_max = 0.5 * (x_tooth_max + r_out_limit)
            if not (
                element["r_inner"] < x_min < x_tooth_min
                and x_tooth_max < x_max < r_out_limit
            ):
                raise ValueError(
                    f"Tooth {idx} stress box cannot fit strictly inside its open radial slot"
                )
            faces.extend(
                box_faces(
                    [x_min, -y_max, 0.5 * (el_z_tip + pad_top)],
                    [
                        x_max,
                        y_max,
                        el_z_tip + el_h_teeth + raw_grid_margin,
                    ],
                    prefix=f"t{idx}_",
                )
            )
        return tuple(faces)

    if parameters.stress_box_mode != "legacy" or parameters.z_tip <= 0:
        raise ValueError("Invalid stress_box_mode or z_tip for a legacy stress box")

    center = math.radians(parameters.tooth_center_offset_deg + parameters.theta_deg)
    half_span = math.radians(parameters.tooth_arc_deg / 2.0)
    radii = (
        min(element["r_tooth_in"] for element in parameters.elements),
        max(element["r_tooth_out"] for element in parameters.elements),
    )

    def tooth_points(test_center: float) -> list[tuple[float, float]]:
        start, stop = test_center - half_span, test_center + half_span
        angles = [start + (stop - start) * index / 720 for index in range(721)]
        first = math.ceil(start / (math.pi / 2))
        last = math.floor(stop / (math.pi / 2))
        angles.extend(index * math.pi / 2 for index in range(first, last + 1))
        return [
            (radius * math.cos(angle), radius * math.sin(angle))
            for radius in radii
            for angle in angles
        ]

    # Size the box in the unrotated tooth frame. Its half-diagonal bounds
    # every rotation of that frame's rectangle, so a Cartesian square with
    # this fixed half-span encloses the tooth without angle-dependent sizing.
    points = tooth_points(0.0)
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    local_center_x = (min_x + max_x) / 2.0
    local_center_y = (min_y + max_y) / 2.0
    center_x = local_center_x * math.cos(center) - local_center_y * math.sin(center)
    center_y = local_center_x * math.sin(center) + local_center_y * math.cos(center)
    margin = STRESS_BOX_GRID_MARGIN_CELLS / parameters.resolution
    lateral_half_span = math.hypot(
        (max_x - min_x) / 2.0, (max_y - min_y) / 2.0
    ) + margin
    return tuple(
        box_faces(
            [
                center_x - lateral_half_span,
                center_y - lateral_half_span,
                parameters.z_tip / 2.0,
            ],
            [
                center_x + lateral_half_span,
                center_y + lateral_half_span,
                parameters.z_tip + parameters.h_teeth + margin,
            ],
        )
    )


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


def load_merged_checkpoints(
    checkpoint_directory: Path,
    task_id: int,
    configuration: str,
    fingerprint: str,
    expected_keys: set[str],
    no_cache: bool,
    checkpoint_prefix: str = "chk_moments_clutch_pilot_task",
) -> dict[str, float]:
    """Merge canonical and shard checkpoints when no shard is writing them."""
    if no_cache:
        return {}
    prefix = f"{checkpoint_prefix}_{task_id:03d}_{configuration}"
    paths = [checkpoint_directory / f"{prefix}.json"]
    paths.extend(sorted(checkpoint_directory.glob(f"{prefix}_shard_*.json")))
    moments: dict[str, float] = {}
    for path in paths:
        moments.update(
            {
                key: value
                for key, value in load_checkpoint(path, fingerprint, no_cache=False).items()
                if key in expected_keys
            }
        )
    return moments


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
    if parameters.material.lower() == "gold_drude":
        # In Meep, DrudeSusceptibility evaluates chi(f) = -sigma * frequency^2 / (f * (f + i*gamma)),
        # where `frequency` is a multiplicative scale factor (NOT a restoring pole; setting frequency=0 zeroes chi).
        # Setting frequency=1.0 and sigma=plasma_frequency^2 (in Meep cyclical 1/um units) gives exact Drude dispersion.
        drude_sus = mp.DrudeSusceptibility(
            frequency=1.0,
            gamma=parameters.gamma,
            sigma=parameters.plasma_frequency ** 2,
        )
        material = mp.Medium(
            epsilon=parameters.epsilon_inf,
            E_susceptibilities=[drude_sus],
            **conductivity,
        )
        return background, material

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
                gamma=sus.gamma,
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
    field_type: Any,
    count: int,
) -> tuple[Any, Any]:
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("The Casimir kernel sample count must be a positive integer")
    owner = mp.make_casimir_gfunc(t_run, dt, sigma, field_type)
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
    rotor_frame = (
        parameters.z_tip < 0 or parameters.stress_box_mode == "per_tooth_rotor_frame"
    )
    stator_options = (
        {
            "z_pad_top": parameters.z_pad_top,
            "theta_stator_deg": -(parameters.tooth_center_offset_deg + parameters.theta_deg),
        }
        if rotor_frame else {}
    )
    rotor_options = {
        "tooth_center_offset_deg": (
            0.0 if rotor_frame else parameters.tooth_center_offset_deg
        )
    }
    dims = cell_dimensions(parameters)
    centers = cell_center(parameters)
    geometry: list[Any] = []
    if parameters.geometry_mode == "explicit_boxes_3d":
        if configuration in ("both", "stator"):
            for bx in parameters.explicit_stator_boxes:
                geometry.append(
                    mp.Block(
                        size=mp.Vector3(bx[1] - bx[0], bx[3] - bx[2], bx[5] - bx[4]),
                        center=mp.Vector3(0.5 * (bx[0] + bx[1]), 0.5 * (bx[2] + bx[3]), 0.5 * (bx[4] + bx[5])),
                        material=material,
                    )
                )
        if configuration in ("both", "rotor", "self"):
            for bx in parameters.explicit_rotor_boxes:
                geometry.append(
                    mp.Block(
                        size=mp.Vector3(bx[1] - bx[0], bx[3] - bx[2], bx[5] - bx[4]),
                        center=mp.Vector3(0.5 * (bx[0] + bx[1]), 0.5 * (bx[2] + bx[3]), 0.5 * (bx[4] + bx[5])),
                        material=material,
                    )
                )
    else:
        if configuration in ("both", "stator"):
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
                    **stator_options,
                )
            )
        if configuration in ("both", "rotor", "self"):
            geometry.extend(
                rotor_generator(
                    elements=list(parameters.elements),
                    H_teeth=parameters.h_teeth,
                    z_tip=parameters.z_tip,
                    rotor_material=material,
                    num_sectors=parameters.num_sectors,
                    tooth_arc_deg=parameters.tooth_arc_deg,
                    theta_rotor_deg=0.0 if rotor_frame else parameters.theta_deg,
                    **rotor_options,
                )
            )
    if parameters.sector0_crop and parameters.geometry_mode != "explicit_boxes_3d" and geometry:
        (x_min, x_max), (y_min, y_max), _ = _sector0_phys_bounds(parameters)

        def _overlaps_sector0(obj: Any) -> bool:
            verts = getattr(obj, "vertices", None)
            if verts:
                xs = [float(v.x) for v in verts]
                ys = [float(v.y) for v in verts]
                return not (
                    max(xs) < x_min
                    or min(xs) > x_max
                    or max(ys) < y_min
                    or min(ys) > y_max
                )
            center_vec = getattr(obj, "center", None)
            size_vec = getattr(obj, "size", None)
            if center_vec is not None and size_vec is not None:
                cx, cy = float(center_vec.x), float(center_vec.y)
                hx, hy = 0.5 * abs(float(size_vec.x)), 0.5 * abs(float(size_vec.y))
                return not (
                    cx + hx < x_min
                    or cx - hx > x_max
                    or cy + hy < y_min
                    or cy - hy > y_max
                )
            return True

        geometry = [obj for obj in geometry if _overlaps_sector0(obj)]
        # Mask the exterior of _sector0_phys_bounds with `background` so that zero
        # metal/dielectric ever enters the cell_buffer_um vacuum padding or PML layers.
        cell_x_min = centers[0] - dims[0] / 2.0 - 0.05
        cell_x_max = centers[0] + dims[0] / 2.0 + 0.05
        cell_y_min = centers[1] - dims[1] / 2.0 - 0.05
        cell_y_max = centers[1] + dims[1] / 2.0 + 0.05
        mask_z_size = dims[2] + 0.10
        if x_min > cell_x_min:
            geometry.append(
                mp.Block(
                    size=mp.Vector3(x_min - cell_x_min, cell_y_max - cell_y_min, mask_z_size),
                    center=mp.Vector3(0.5 * (cell_x_min + x_min), centers[1], centers[2]),
                    material=background,
                )
            )
        if cell_x_max > x_max:
            geometry.append(
                mp.Block(
                    size=mp.Vector3(cell_x_max - x_max, cell_y_max - cell_y_min, mask_z_size),
                    center=mp.Vector3(0.5 * (x_max + cell_x_max), centers[1], centers[2]),
                    material=background,
                )
            )
        if y_min > cell_y_min:
            geometry.append(
                mp.Block(
                    size=mp.Vector3(cell_x_max - cell_x_min, y_min - cell_y_min, mask_z_size),
                    center=mp.Vector3(centers[0], 0.5 * (cell_y_min + y_min), centers[2]),
                    material=background,
                )
            )
        if cell_y_max > y_max:
            geometry.append(
                mp.Block(
                    size=mp.Vector3(cell_x_max - cell_x_min, cell_y_max - y_max, mask_z_size),
                    center=mp.Vector3(centers[0], 0.5 * (y_max + cell_y_max), centers[2]),
                    material=background,
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

    # In Meep, `geometry_center` positions the computational cell over
    # [centers - dims/2, centers + dims/2] in the shared global coordinate frame.
    # Both `geometry` and `face.center` (from `stress_faces`, which verifies
    # `abs(coord - centers[axis]) < interiors[axis]`) are expressed in this same
    # global frame, so no additional translation of `face.center` is needed or allowed.
    simulation = mp.Simulation(
        cell_size=mp.Vector3(*dims),
        geometry_center=mp.Vector3(*centers),
        dimensions=3,
        resolution=parameters.resolution,
        Courant=parameters.courant,
        boundary_layers=[mp.PML(parameters.pml_thickness)],
        default_material=background,
        geometry=geometry,
        eps_averaging=parameters.eps_averaging,
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
            mp, np, parameters.t_run, dt, parameters.sigma, field_type, steps
        )
        volume = mp.Volume(center=mp.Vector3(*face.center), size=mp.Vector3(*face.size), dims=3)
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

    from utils.metrics_logger import (
        log_step,
        log_metric,
        export_macros,
        set_solver_provenance,
    )

    solver_name = str(result.get("solver", "meep"))
    solver_parameters = result.get("solver_parameters", {})
    set_solver_provenance(solver_name, solver_parameters)
    task_prefix = f"clutch_pilot_task_{result['task_id']}"
    step_id = f"{task_prefix}_{result['status']}"
    out_dir = Path(result.get("output_file", "results/result.json")).parent
    default_dir = Path("results")
    in_array_job = os.environ.get("SLURM_ARRAY_TASK_ID") is not None
    output_is_default = out_dir.resolve() == default_dir.resolve()
    log_directories = []
    if not output_is_default or not in_array_job:
        log_directories.append(out_dir)
    if not output_is_default and not in_array_job:
        log_directories.append(default_dir)

    for directory in log_directories:
        directory.mkdir(parents=True, exist_ok=True)
        metrics_path = directory / "provenance_metrics.json"
        macros_path = directory / "macros_results.tex"
        log_step(
            step_id,
            {
                name: result.get(name)
                for name in (
                    "task_id",
                    "theta_deg",
                    "N_fractal",
                    "Sigma",
                    "completed_moments",
                    "completed_by_config",
                    "F_sector0_both",
                    "F_sector0_rotor",
                    "F_sector0_self",
                    "F_sector0_stator",
                    "F_sector0_vac",
                    "solver",
                    "solver_parameters",
                )
            },
            solver_name=solver_name,
            solver_parameters=solver_parameters,
            metrics_path=str(metrics_path),
        )
        for name in (
            "F_both",
            "F_rotor",
            "F_self",
            "F_stator",
            "F_vac",
            "F_2pass",
            "F_stator_only",
            "F_net",
            "f_net_fN",
            "f_net_pN",
            "elapsed_seconds",
            "completed_moments",
            "micro_probe_steps",
            "micro_probe_step_seconds",
            "micro_probe_dct_checksum",
        ):
            value = result.get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                log_metric(
                    f"{task_prefix}_{name}",
                    value,
                    step_id=step_id,
                    solver_name=solver_name,
                    solver_parameters=solver_parameters,
                    metrics_path=str(metrics_path),
                )
                log_metric(
                    name,
                    value,
                    step_id=step_id,
                    solver_name=solver_name,
                    solver_parameters=solver_parameters,
                    metrics_path=str(metrics_path),
                )
        export_macros(metrics_path=str(metrics_path), output_path=str(macros_path))
        for path in (metrics_path, macros_path):
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(
                    "[ERROR: RUN_DATA_MISSING] Provenance artifacts were not generated"
                )


def run_numpy_micro_probe(
    args: argparse.Namespace, parameters: Parameters, started: float
) -> int:
    """Measure real float64 3-D Yee updates and cosine stress-face projections.

    This vacuum timing probe is not a Casimir solver. E and H use staggered
    spatial locations and leapfrog times; forward/backward differences implement
    the Yee curls. Periodic boundaries are used only for this local diagnostic.
    """
    import numpy as np

    faces = stress_faces(parameters)
    dimensions = cell_dimensions(parameters)
    centers = cell_center(parameters)
    requested_shape = tuple(
        max(3, math.ceil(length * parameters.resolution)) for length in dimensions
    )
    shape = tuple(min(MICRO_PROBE_MAX_GRID_POINTS, count) for count in requested_shape)
    spacing = tuple(length / count for length, count in zip(dimensions, shape))
    dt = parameters.courant * min(spacing)
    coordinates = tuple(
        (np.arange(count, dtype=np.float64) + 0.5) * dx - length / 2.0 + center_c
        for count, dx, length, center_c in zip(shape, spacing, dimensions, centers)
    )
    electric = np.zeros((3, *shape), dtype=np.float64)
    magnetic = np.zeros_like(electric)

    # Separable cosine matrices avoid storing nmax**2 full face arrays.
    projections: list[tuple[Face, tuple[Any, ...], Any, Any, float]] = []
    for face in faces:
        selection: list[Any] = [slice(None)] * 3
        selection[face.axis] = int(
            np.argmin(np.abs(coordinates[face.axis] - face.center[face.axis]))
        )
        bases = []
        for axis in face.tangent_axes:
            relative = coordinates[axis] - face.center[axis]
            indices = np.flatnonzero(np.abs(relative) <= face.size[axis] / 2.0)
            if indices.size == 0:
                # The capped grid can underresolve a narrow face; sample its
                # center cell and document the cap in provenance.
                indices = np.array([int(np.argmin(np.abs(relative)))])
            selection[axis] = slice(int(indices[0]), int(indices[-1]) + 1)
            positions = np.clip(
                relative[indices] / face.size[axis] + 0.5, 0.0, 1.0
            )
            modes = np.arange(parameters.nmax, dtype=np.float64)
            basis = np.cos(math.pi * modes[:, None] * positions[None, :])
            basis *= np.sqrt(
                np.where(modes == 0, 1.0, 2.0) / face.size[axis]
            )[:, None]
            bases.append(basis)
        area = math.prod(spacing[axis] for axis in face.tangent_axes)
        projections.append((face, tuple(selection), bases[0], bases[1], area))

    # A nonzero, localized impulse excites propagation in all three dimensions.
    for face, selection, first, second, _ in projections:
        electric[(2, *selection)] += np.outer(first[0], second[0])

    def difference(field: Any, axis: int, forward: bool) -> Any:
        if forward:
            return (np.roll(field, -1, axis=axis) - field) / spacing[axis]
        return (field - np.roll(field, 1, axis=axis)) / spacing[axis]

    def update_curl(target: Any, source: Any, scale: float, forward: bool) -> None:
        target[0] += scale * (
            difference(source[2], 1, forward) - difference(source[1], 2, forward)
        )
        target[1] += scale * (
            difference(source[0], 2, forward) - difference(source[2], 0, forward)
        )
        target[2] += scale * (
            difference(source[1], 0, forward) - difference(source[0], 1, forward)
        )

    def centered_fields(fields: Any, is_electric: bool) -> Any:
        # Interpolate staggered components to common cell centers for stress.
        centered = np.empty_like(fields)
        for component in range(3):
            value = fields[component]
            axes = (
                (component,) if is_electric
                else tuple(axis for axis in range(3) if axis != component)
            )
            for axis in axes:
                value = 0.5 * (value + np.roll(value, 1, axis=axis))
            centered[component] = value
        return centered

    checksum = 0.0
    probe_started = time.perf_counter()
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for _ in range(args.max_steps):
            update_curl(magnetic, electric, -dt, True)
            update_curl(electric, magnetic, dt, False)
            e_center = centered_fields(electric, True)
            h_center = centered_fields(magnetic, False)
            step_checksum = 0.0
            for face, selection, first, second, area in projections:
                e = e_center[(slice(None), *selection)]
                h = h_center[(slice(None), *selection)]
                traction = e[2] * e[face.axis] + h[2] * h[face.axis]
                if face.axis == 2:
                    traction -= 0.5 * (np.sum(e * e, axis=0) + np.sum(h * h, axis=0))
                coefficients = first @ traction @ second.T
                step_checksum += face.orientation * area * float(np.sum(coefficients))
            checksum += dt * step_checksum
            if not math.isfinite(checksum):
                raise FloatingPointError("The NumPy micro-probe stress checksum is non-finite")
    probe_seconds = time.perf_counter() - probe_started
    if not bool(np.isfinite(electric).all() and np.isfinite(magnetic).all()):
        raise FloatingPointError("The NumPy micro-probe fields are non-finite")

    out_path = (
        args.output_file
        if args.output_file is not None
        else Path("results_clutch_pilot")
        / (
            f"task_{args.task_id:03d}_N{parameters.n_fractal}"
            f"_th_{int(parameters.theta_deg)}deg_numpy_micro_probe.json"
        )
    )
    result = {
        "status": "micro_probe_complete",
        "cache_version": CACHE_VERSION,
        "model": f"Meep_3D_FDTD_{parameters.material}_v{CACHE_VERSION}",
        "dataset": f"{out_path.parent.name}_task_{args.task_id}",
        "output_file": str(out_path),
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "solver": "numpy",
        "solver_parameters": {
            "solver": "numpy",
            "method": "3D_Yee_FDTD_Stress_Face_Cosine_DCT_Micro_Probe",
            "diagnostic_only": True,
            "casimir_force_computed": False,
            "device": "cpu",
            "requested_device": args.device,
            "dtype": "float64",
            "resolution": parameters.resolution,
            "cell_dimensions_um": dimensions,
            "requested_grid_shape": requested_shape,
            "grid_shape": shape,
            "grid_capped": shape != requested_shape,
            "grid_spacing_um": spacing,
            "boundary_conditions": "periodic",
            "material": "vacuum",
            "courant": parameters.courant,
            "dt": dt,
            "nmax": parameters.nmax,
            "stress_faces": len(faces),
            "max_steps": args.max_steps,
            "timesteps_per_last_moment": args.max_steps,
            "probe_seconds": probe_seconds,
            "seconds_per_step": probe_seconds / args.max_steps,
        },
        "task_id": args.task_id,
        "config_file": str(args.config_file.resolve()),
        "requested_config": args.config,
        "N_fractal": parameters.n_fractal,
        "theta_deg": parameters.theta_deg,
        "parameters": vars(parameters),
        "Sigma": parameters.sigma,
        "max_steps": args.max_steps,
        "time_truncated": True,
        "completed_moments": 0,
        "completed_by_config": {name: 0 for name in ALL_CONFIGURATIONS},
        "F_net": None,
        "f_net_N": None,
        "f_net_fN": None,
        "f_net_pN": None,
        "elapsed_seconds": time.monotonic() - started,
        "micro_probe_steps": args.max_steps,
        "micro_probe_step_seconds": probe_seconds / args.max_steps,
        "micro_probe_dct_checksum": checksum,
    }
    atomic_json(out_path, result)
    log_metrics(result, True)
    print(
        f"NumPy 3-D micro-probe: {args.max_steps} steps on {shape}, "
        f"{probe_seconds / args.max_steps:.6g} s/step. Saved {out_path}",
        flush=True,
    )
    return 0


def execute(args: argparse.Namespace, raw: dict[str, Any], started: float) -> int:
    if args.config == "self":
        args.config = "rotor"
    raw = dict(raw)
    if getattr(args, "nmax", None) is not None:
        raw["nmax"] = int(args.nmax)
    if getattr(args, "material", None) is not None:
        mat_low = str(args.material).lower()
        raw["material"] = "PEC" if mat_low == "pec" else ("Gold_Drude" if mat_low == "gold_drude" else "Gold")
    if getattr(args, "fixed_stress_box_margin_um", None) is not None:
        raw["fixed_stress_box_margin_um"] = float(args.fixed_stress_box_margin_um)
    if getattr(args, "eps_averaging", None) is not None:
        raw["eps_averaging"] = bool(args.eps_averaging)
    if getattr(args, "geometry_mode", None) is not None:
        raw["geometry_mode"] = str(args.geometry_mode)
    if getattr(args, "r_edge_nm", None) is not None:
        raw["r_edge_nm"] = float(args.r_edge_nm)
    if getattr(args, "sector0_crop", None) is not None:
        raw["sector0_crop"] = bool(args.sector0_crop)
    checkpoint_prefix = getattr(
        args, "checkpoint_prefix", "chk_moments_clutch_pilot_task"
    )
    # Delay scientific imports until after argparse and basic JSON parsing.
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))

    if args.solver in ("bem", "scuff"):
        from execution.clutch_geometry_redesign import compute_dynamic_Trun

        parameters = parse_parameters(raw, args.resolution, compute_dynamic_Trun)
        from execution.casimir_bem_solver import (
            run_bem_casimir_solver,
            export_scuff_files_and_run,
        )

        if args.solver == "bem":
            result = run_bem_casimir_solver(
                raw,
                n_r=args.bem_n_r,
                n_phi_tooth=args.bem_n_phi_tooth,
                n_phi_bridge=args.bem_n_phi_bridge,
                n_z=args.bem_n_z,
                n_xi=args.bem_n_xi,
                max_steps=args.max_steps,
                device=args.device,
                config_file=args.config_file.resolve(),
                task_id=str(args.task_id),
                record_metrics=True,
            )
        else:
            result = export_scuff_files_and_run(
                raw,
                n_r=args.bem_n_r,
                n_phi_tooth=args.bem_n_phi_tooth,
                n_phi_bridge=args.bem_n_phi_bridge,
                n_z=args.bem_n_z,
                config_file=args.config_file.resolve(),
                task_id=str(args.task_id),
                record_metrics=True,
            )
        out_path = (
            args.output_file
            if args.output_file is not None
            else Path("results_clutch_pilot")
            / (
                f"task_{args.task_id:03d}_N{parameters.n_fractal}"
                f"_th_{int(parameters.theta_deg)}deg_{args.solver}.json"
            )
        )
        atomic_json(out_path, result)
        print(f"Saved {out_path}", flush=True)
        return 0

    try:
        mp = importlib.import_module("meep")
    except ImportError as exc:
        if args.max_steps > 0:
            # Import only the runtime helper needed for parameter parsing.
            # Explicit T_run configurations do not need geometry-module imports.
            def dynamic_trun(**context: Any) -> Any:
                from execution.clutch_geometry_redesign import compute_dynamic_Trun

                return invoke_dynamic_trun(compute_dynamic_Trun, context)

            parameters = parse_parameters(raw, args.resolution, dynamic_trun)
            return run_numpy_micro_probe(args, parameters, started)
        raise RuntimeError(
            "Meep is required to run the simulation. Load the BigRed 200 "
            "Meep/MPI environment; --help does not require Meep."
        ) from exc
    if not hasattr(mp, "Simulation") or not hasattr(mp, "make_casimir_gfunc"):
        raise RuntimeError("The installed 'meep' module lacks the required Casimir API")
    import numpy as np
    from execution.clutch_geometry_redesign import (
        compute_dynamic_Trun,
        generate_rectilinear_rotor_geometry,
        generate_rectilinear_stator_geometry,
        generate_redesigned_rotor_geometry,
        generate_redesigned_stator_geometry,
    )

    parallel = ParallelContext(mp)
    parameters = parse_parameters(raw, args.resolution, compute_dynamic_Trun)
    faces = stress_faces(parameters)
    canonical_parameters = dict(vars(parameters))
    if (
        canonical_parameters.get("tooth_center_offset_deg")
        == DEFAULT_TOOTH_CENTER_OFFSET_DEG
    ):
        # Preserve CACHE_VERSION=6 SHA-256 fingerprint compatibility for the
        # standard 15.0 deg tooth center offset while hashing custom offsets.
        canonical_parameters.pop("tooth_center_offset_deg", None)
    if canonical_parameters.get("fixed_stress_box_margin_um") is None:
        canonical_parameters.pop("fixed_stress_box_margin_um", None)
    if canonical_parameters.get("eps_averaging") is False:
        canonical_parameters.pop("eps_averaging", None)
    if canonical_parameters.get("geometry_mode") == "cylindrical":
        canonical_parameters.pop("geometry_mode", None)
    if canonical_parameters.get("r_edge_nm") == 0.0:
        canonical_parameters.pop("r_edge_nm", None)
    if canonical_parameters.get("sector0_crop") is False:
        canonical_parameters.pop("sector0_crop", None)
    if canonical_parameters.get("geometry_mode") != "explicit_boxes_3d":
        for exp_k in (
            "explicit_rotor_boxes",
            "explicit_stator_boxes",
            "explicit_stress_boxes",
            "explicit_cell_center",
            "explicit_phys_bounds",
        ):
            canonical_parameters.pop(exp_k, None)
    canonical = {
        "version": CACHE_VERSION,
        "parameters": canonical_parameters,
        "stress_faces": [vars(face) for face in faces],
        "max_steps": args.max_steps,
        "force_direction": "z",
        "kernel_polarization": "field_type_E_stuff_H_stuff",
        "inclusion_exclusion": "4pass_both_rotor_stator_vac",
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    checkpoint_directory = Path(".tmp")
    result_directory = Path("results_clutch_pilot")
    checkpoint_directory.mkdir(parents=True, exist_ok=True)
    result_directory.mkdir(parents=True, exist_ok=True)
    if args.output_file is not None:
        final_path = args.output_file
        final_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path = final_path.parent / f"progress_task_{args.task_id:03d}.json"
    else:
        progress_path = result_directory / f"progress_task_{args.task_id:03d}.json"
        final_path = result_directory / (
            f"task_{args.task_id:03d}_N{parameters.n_fractal}"
            f"_th_{int(parameters.theta_deg)}deg.json"
        )
    configurations = (
        ALL_CONFIGURATIONS
        if args.config == "all"
        else ("rotor" if args.config == "self" else args.config,)
    )
    moments_per_config = 6 * len(faces) * parameters.nmax**2
    checkpoints = {
        name: checkpoint_directory
        / f"{checkpoint_prefix}_{args.task_id:03d}_{name}.json"
        for name in ALL_CONFIGURATIONS
    }
    sharded = parallel.shard_count > 1
    shard_checkpoints = {
        name: checkpoint_directory
        / (
            f"{checkpoint_prefix}_{args.task_id:03d}_{name}"
            f"_shard_{parallel.shard_rank:03d}.json"
        )
        for name in ALL_CONFIGURATIONS
    }
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

    def filter_moments(values: Mapping[str, float]) -> dict[str, float]:
        return {key: value for key, value in values.items() if key in expected_keys}

    def checkpoint_payload(
        configuration: str, values: Mapping[str, float]
    ) -> dict[str, Any]:
        return {
            "version": CACHE_VERSION,
            "fingerprint": fingerprint,
            "configuration": configuration,
            "moments": dict(values),
            "updated_unix_seconds": time.time(),
        }

    def initialize_moments(configuration: str) -> dict[str, float]:
        # Only the master writes canonical files or removes old shard files.
        # Shards cannot start writing until the initialization handshake ends.
        if parallel.master and args.no_cache:
            prefix = f"{checkpoint_prefix}_{args.task_id:03d}_{configuration}"
            for path in checkpoint_directory.glob(f"{prefix}_shard_*.json"):
                path.unlink()
        values = load_merged_checkpoints(
            checkpoint_directory,
            args.task_id,
            configuration,
            fingerprint,
            expected_keys,
            args.no_cache,
            checkpoint_prefix=checkpoint_prefix,
        )
        if parallel.master:
            atomic_json(
                checkpoints[configuration], checkpoint_payload(configuration, values)
            )
        return values

    moments: dict[str, dict[str, float]] = {}
    for name in ALL_CONFIGURATIONS:
        # Serial shards use only the master's immutable starting snapshot.
        # MPI ranks without mpi4py can read, but only the master writes.
        moments[name] = parallel.root_call(
            lambda name=name: initialize_moments(name),
            all_ranks_without_comm=not sharded,
        ) or {}

    # Each shard exclusively owns its checkpoint files. The canonical startup
    # snapshot already preserves earlier runs, so these contain only new work.
    local_moments: dict[str, dict[str, float]] = {
        name: {} for name in ALL_CONFIGURATIONS
    }
    active: dict[str, Any] = {}
    latest_steps: int | None = None
    latest_dt: float | None = None
    walltime_seconds = args.max_walltime_hours * 3600.0

    def elapsed() -> float:
        return time.monotonic() - started

    def guard() -> None:
        expired = parallel.broadcast(elapsed() >= walltime_seconds)
        if expired:
            raise WalltimeReached("Walltime limit reached; unfinished moment is not cached")

    shard_paths: list[Path] = []
    shard_run_id: str | None = None
    shard_master_payload: dict[str, Any] = {}

    def read_status(path: Path) -> dict[str, Any]:
        try:
            return read_config(path)
        except FileNotFoundError:
            return {}

    if sharded:
        # A run-id and per-process tokens prevent stale status files from a
        # previous invocation from being mistaken for participating shards.
        scope = hashlib.sha256(
            json.dumps(
                [
                    os.environ.get("SLURM_JOB_ID", ""),
                    os.environ.get("SLURM_STEP_ID", ""),
                    fingerprint,
                    args.config,
                    args.no_cache,
                    parallel.shard_count,
                    checkpoint_prefix,
                ]
            ).encode("utf-8")
        ).hexdigest()[:24]
        shard_paths = [
            checkpoint_directory
            / f"shard_task_{args.task_id:03d}_{scope}_{rank:05d}.json"
            for rank in range(parallel.shard_count)
        ]
        token = uuid.uuid4().hex
        if parallel.master:
            shard_run_id = uuid.uuid4().hex
            shard_master_payload = {
                "run_id": shard_run_id,
                "status": "initializing",
                "token": token,
            }
            atomic_json(shard_paths[0], shard_master_payload)
            tokens = {"0": token}
            while len(tokens) < parallel.shard_count:
                for rank in range(1, parallel.shard_count):
                    status = read_status(shard_paths[rank])
                    if (
                        status.get("run_id") == shard_run_id
                        and status.get("status") == "ready"
                        and isinstance(status.get("token"), str)
                    ):
                        tokens[str(rank)] = status["token"]
                if len(tokens) < parallel.shard_count:
                    if elapsed() >= args.max_walltime_hours * 3600.0:
                        shard_master_payload["status"] = "failed"
                        atomic_json(shard_paths[0], shard_master_payload)
                        raise RuntimeError("Timed out waiting for shard initialization")
                    time.sleep(0.1)
            shard_master_payload.update(
                status="running",
                tokens=tokens,
                snapshot={name: dict(values) for name, values in moments.items()},
            )
            atomic_json(shard_paths[0], shard_master_payload)
        else:
            while True:
                status = read_status(shard_paths[0])
                run_id = status.get("run_id")
                if isinstance(run_id, str):
                    if run_id != shard_run_id:
                        shard_run_id = run_id
                        atomic_json(
                            shard_paths[parallel.shard_rank],
                            {
                                "run_id": shard_run_id,
                                "status": "ready",
                                "token": token,
                            },
                        )
                    tokens = status.get("tokens", {})
                    if (
                        isinstance(tokens, dict)
                        and tokens.get(str(parallel.shard_rank)) == token
                        and "snapshot" in status
                    ):
                        snapshot = status["snapshot"]
                        moments = {
                            name: filter_moments(
                                {
                                    key: finite_number(value, f"snapshot moment {key}")
                                    for key, value in snapshot[name].items()
                                }
                            )
                            for name in ALL_CONFIGURATIONS
                        }
                        break
                    if status.get("status") == "failed":
                        raise RuntimeError("Master shard failed during initialization")
                if elapsed() >= args.max_walltime_hours * 3600.0:
                    raise RuntimeError("Timed out waiting for the shard snapshot")
                time.sleep(0.1)

    # This ordered list is built once from the shared starting snapshot.
    # Subsequent checkpoint writes must not change moment ownership.
    pending = [
        (configuration, label, component, electric, face, mode)
        for configuration in configurations
        for label, component, electric in polarizations
        for face in faces
        for mode in range(parameters.nmax**2)
        if f"{label}:{face.name}:{mode}" not in moments[configuration]
    ]

    def reload_moments() -> None:
        # Called by the master only after every shard has stopped writing.
        for name in ALL_CONFIGURATIONS:
            moments[name] = load_merged_checkpoints(
                checkpoint_directory,
                args.task_id,
                name,
                fingerprint,
                expected_keys,
                no_cache=False,
                checkpoint_prefix=checkpoint_prefix,
            )
            atomic_json(checkpoints[name], checkpoint_payload(name, moments[name]))

    def summary(status: str) -> dict[str, Any]:
        forces: dict[str, float | None] = {}
        for name in ALL_CONFIGURATIONS:
            forces[name] = (
                4.0 * math.fsum(moments[name].values())
                if len(moments[name]) == moments_per_config
                else None
            )
        f_2pass = (
            forces["both"] - forces["rotor"]
            if forces["both"] is not None and forces["rotor"] is not None
            else None
        )
        f_stator_only = (
            forces["stator"] - forces["vac"]
            if forces["stator"] is not None and forces["vac"] is not None
            else None
        )
        net = (
            f_2pass - f_stator_only
            if f_2pass is not None and f_stator_only is not None
            else None
        )
        return {
            "status": status,
            "cache_version": CACHE_VERSION,
            "model": f"Meep_3D_FDTD_{parameters.material}_v{CACHE_VERSION}",
            "dataset": (
                f"{final_path.parent.name}_task_{args.task_id}"
                if status == "complete"
                else f"{final_path.parent.name}_progress_task_{args.task_id}"
            ),
            "output_file": str(final_path),
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "solver": "meep",
            "solver_parameters": meep_solver_parameters(
                parameters, args, latest_steps, latest_dt
            ),
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
            "F_sector0_rotor": None if forces["rotor"] is None else forces["rotor"] / 4.0,
            "F_sector0_self": None if forces["rotor"] is None else forces["rotor"] / 4.0,
            "F_sector0_stator": None if forces["stator"] is None else forces["stator"] / 4.0,
            "F_sector0_vac": None if forces["vac"] is None else forces["vac"] / 4.0,
            "F_both": forces["both"],
            "F_rotor": forces["rotor"],
            "F_self": forces["rotor"],
            "F_stator": forces["stator"],
            "F_vac": forces["vac"],
            "F_2pass": f_2pass,
            "F_stator_only": f_stator_only,
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
        progress_result = dict(result)
        progress_result["dataset"] = (
            f"{final_path.parent.name}_progress_task_{args.task_id}"
        )
        parallel.root_call(lambda: atomic_json(progress_path, progress_result))
        return result

    def write_shard_status(status: str) -> None:
        payload = (
            dict(shard_master_payload)
            if parallel.master
            else {"run_id": shard_run_id}
        )
        payload["status"] = status
        atomic_json(shard_paths[parallel.shard_rank], payload)

    def finish_shards(status: str) -> int:
        write_shard_status(status)
        if not parallel.master:
            return 0

        statuses: dict[int, str] = {0: status}
        while len(statuses) < parallel.shard_count:
            for rank in range(1, parallel.shard_count):
                payload = read_status(shard_paths[rank])
                if (
                    payload.get("run_id") == shard_run_id
                    and payload.get("status") in ("done", "walltime", "failed")
                ):
                    statuses[rank] = payload["status"]
            if len(statuses) < parallel.shard_count:
                time.sleep(0.1)

        try:
            reload_moments()
            active.clear()
            if "failed" in statuses.values():
                save_progress("failed")
                raise RuntimeError("One or more moment shards failed")
            complete = all(
                len(moments[name]) == moments_per_config for name in configurations
            )
            result = save_progress("complete" if complete else "walltime_reached")
            if complete:
                atomic_json(final_path, result)
                log_metrics(result, True)
                print(f"Saved {final_path}", flush=True)
                return 0
            log_metrics(result, True)
            print(
                "Walltime limit reached. Resume with the same arguments; "
                "remaining moments will be restarted.",
                file=sys.stderr,
                flush=True,
            )
            return 75
        finally:
            for path in shard_paths:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    save_progress("running")
    try:
        for pending_index, (
            configuration, label, component, electric, face, mode
        ) in enumerate(pending):
            if pending_index % parallel.shard_count != parallel.shard_rank:
                continue
            key = f"{label}:{face.name}:{mode}"
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
                stator_generator=(
                    generate_rectilinear_stator_geometry
                    if parameters.geometry_mode == "rectilinear_xz"
                    else generate_redesigned_stator_geometry
                ),
                rotor_generator=(
                    generate_rectilinear_rotor_geometry
                    if parameters.geometry_mode == "rectilinear_xz"
                    else generate_redesigned_rotor_geometry
                ),
                guard=guard,
            )
            if sharded:
                force = finite_number(force, f"checkpoint moment {key}")
                local_moments[configuration][key] = force
                atomic_json(
                    shard_checkpoints[configuration],
                    checkpoint_payload(configuration, local_moments[configuration]),
                )
                moments[configuration][key] = force
            else:
                # Use the master's value when collectives are available.
                moments[configuration][key] = parallel.broadcast(force)
                payload = checkpoint_payload(configuration, moments[configuration])
                parallel.root_call(
                    lambda: atomic_json(checkpoints[configuration], payload)
                )
            active.clear()
            save_progress("running")
    except WalltimeReached:
        if sharded:
            return finish_shards("walltime")
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
        if sharded:
            write_shard_status("failed")
            if parallel.master:
                finish_shards("failed")
        save_progress("failed")
        raise

    if sharded:
        return finish_shards("done")
    parallel.root_call(reload_moments)
    result = save_progress("complete")
    parallel.root_call(lambda: atomic_json(final_path, result))
    log_metrics(result, parallel.master)
    if parallel.master:
        print(f"Saved {final_path}", flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    started = time.monotonic()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.config == "self":
        args.config = "rotor"
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
