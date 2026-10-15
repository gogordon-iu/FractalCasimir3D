"""Concentric Cantor-ring rotary Casimir clutch geometry.

Distances are in micrometres; angles supplied to geometry functions are in
degrees unless explicitly named ``*_rad``.

Radial slots are the middle-thirds removed at successive Cantor construction
levels. For N=2, this produces one level-1 slot and two level-2 slots.
Teeth occupy the same radial centres, with width
max(w1_ratio * W_slot, min_tooth_w).

Meep is imported lazily. Numerical design and CLI verification work without
Meep; geometry construction requires its Python bindings.

Default materials are Meep's ideal metal and air. Supply an appropriate
dispersive metallic material for quantitative Casimir calculations.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Any, TypedDict


__all__ = [
    "compute_dynamic_Trun",
    "get_cantor_radial_intervals",
    "get_scoped_clutch_elements",
    "generate_annular_sector_prism_vertices",
    "generate_redesigned_stator_geometry",
    "generate_redesigned_rotor_geometry",
]


class RadialInterval(TypedDict):
    level: int
    r_inner: float
    r_outer: float


class _AxialOverrides(TypedDict, total=False):
    z_tip: float | None
    h_teeth: float | None


class ClutchElement(RadialInterval, _AxialOverrides):
    r_center: float
    W_slot: float
    w_tooth: float
    r_tooth_in: float
    r_tooth_out: float


class TrunDiagnostics(TypedDict):
    d_eff_um: float
    target_suppression: float
    safety_factor: float
    min_floor: float
    max_ceil: float
    Sigma: float
    log_target_suppression: float
    ideal_T_run: float
    safety_scaled_T_run: float
    T_run: float
    log_achieved_suppression: float
    achieved_suppression: float
    target_met: bool
    clipping: str
    equation: str
    units: str


def _finite(name: str, value: object) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}.")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"{name} must be a finite real number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _positive(name: str, value: object) -> float:
    result = _finite(name, value)
    if result <= 0.0:
        raise ValueError(f"{name} must be greater than zero.")
    return result


def _integer(name: str, value: object, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


@lru_cache(maxsize=1)
def _meep() -> Any:
    try:
        return importlib.import_module("meep")
    except ImportError as exc:
        raise ImportError(
            "Geometry construction requires the scientific Meep Python bindings. "
            "Numerical verification can run without Meep."
        ) from exc


def compute_dynamic_Trun(
    d_eff_um: float,
    target_suppression: float = 1e-50,
    safety_factor: float = 1.5,
    min_floor: float = 3.0,
    max_ceil: float = 12.0,
) -> tuple[float, TrunDiagnostics]:
    """Compute a bounded run time from exp(-2 * Sigma * T).

    Sigma = 0.5 / d_eff_um, so the ideal time is
    -d_eff_um * log(target_suppression). Time is in the corresponding
    normalized Wick-damping units, not implicitly seconds.

    Ceiling clipping can prevent the requested suppression from being met;
    this is explicitly recorded in the diagnostics.
    """
    d = _positive("d_eff_um", d_eff_um)
    target = _positive("target_suppression", target_suppression)
    if target >= 1.0:
        raise ValueError("target_suppression must lie strictly between 0 and 1.")
    safety = _positive("safety_factor", safety_factor)
    floor = _positive("min_floor", min_floor)
    ceiling = _positive("max_ceil", max_ceil)
    if floor > ceiling:
        raise ValueError("min_floor must not exceed max_ceil.")

    sigma = _positive("computed Sigma", 0.5 / d)
    log_target = math.log(target)
    ideal = _positive("computed ideal_T_run", -d * log_target)
    scaled = _positive("computed safety_scaled_T_run", ideal * safety)
    run_time = float(min(ceiling, max(floor, scaled)))
    log_achieved = _finite("computed log_achieved_suppression", -run_time / d)
    diagnostics: TrunDiagnostics = {
        "d_eff_um": d,
        "target_suppression": target,
        "safety_factor": safety,
        "min_floor": floor,
        "max_ceil": ceiling,
        "Sigma": sigma,
        "log_target_suppression": log_target,
        "ideal_T_run": ideal,
        "safety_scaled_T_run": scaled,
        "T_run": run_time,
        "log_achieved_suppression": log_achieved,
        "achieved_suppression": math.exp(log_achieved),
        "target_met": log_achieved <= log_target,
        "clipping": (
            "min_floor" if scaled < floor
            else "max_ceil" if scaled > ceiling
            else "none"
        ),
        "equation": (
            "Sigma = 0.5/d_eff_um; "
            "T_ideal = -ln(target_suppression)/(2*Sigma); "
            "T_run = clip(safety_factor*T_ideal, min_floor, max_ceil)"
        ),
        "units": "d_eff_um: micrometres; T_run: normalized Wick-damping time",
    }
    return run_time, diagnostics


def get_cantor_radial_intervals(
    N: int, R_min: float, R_max: float
) -> list[RadialInterval]:
    """Return removed middle-third intervals, ordered by level then radius."""
    depth = _integer("N", N)
    if depth not in (1, 2, 3):
        raise ValueError("N must be one of 1, 2, or 3.")
    inner = _finite("R_min", R_min)
    outer = _positive("R_max", R_max)
    if inner < 0.0 or inner >= outer:
        raise ValueError("Require 0 <= R_min < R_max.")

    survivors: list[tuple[float, float]] = [(inner, outer)]
    removed: list[RadialInterval] = []
    for level in range(1, depth + 1):
        next_survivors: list[tuple[float, float]] = []
        for left, right in survivors:
            third = (right - left) / 3.0
            a, b = left + third, right - third
            if not left < a < b < right:
                raise ValueError("Radial interval is too small to resolve numerically.")
            removed.append({"level": level, "r_inner": a, "r_outer": b})
            next_survivors.extend(((left, a), (b, right)))
        survivors = next_survivors
    return removed


def get_scoped_clutch_elements(
    N: int = 2,
    R_min: float = 0.30,
    R_max: float = 1.35,
    w1_ratio: float = 0.23,
    min_tooth_w: float = 0.020,
) -> list[ClutchElement]:
    """Build radially centred teeth with strictly positive slot clearances."""
    ratio = _positive("w1_ratio", w1_ratio)
    if ratio >= 1.0:
        raise ValueError("w1_ratio must be less than 1.")
    minimum = _positive("min_tooth_w", min_tooth_w)
    elements: list[ClutchElement] = []
    for interval in get_cantor_radial_intervals(N, R_min, R_max):
        inner, outer = interval["r_inner"], interval["r_outer"]
        width = outer - inner
        tooth_width = max(ratio * width, minimum)
        if tooth_width >= width:
            raise ValueError(
                f"Level {interval['level']} slot width {width:.9g} um cannot "
                f"accommodate tooth width {tooth_width:.9g} um with clearance."
            )
        centre = inner + width / 2.0
        tooth_inner = centre - tooth_width / 2.0
        tooth_outer = centre + tooth_width / 2.0
        if not inner < tooth_inner < tooth_outer < outer:
            raise ValueError("Tooth clearance cannot be represented numerically.")
        elements.append({
            **interval,
            "r_center": centre,
            "W_slot": width,
            "w_tooth": tooth_width,
            "r_tooth_in": tooth_inner,
            "r_tooth_out": tooth_outer,
        })
    return elements


def _validated_elements(elements: Iterable[ClutchElement]) -> list[ClutchElement]:
    if isinstance(elements, (str, bytes, dict)):
        raise TypeError("elements must be an iterable of clutch-element dictionaries.")
    result: list[ClutchElement] = []
    try:
        iterator = iter(elements)
    except TypeError as exc:
        raise TypeError("elements must be iterable.") from exc
    keys = (
        "r_inner", "r_outer", "r_center", "W_slot",
        "w_tooth", "r_tooth_in", "r_tooth_out",
    )
    for index, element in enumerate(iterator):
        if not isinstance(element, dict):
            raise TypeError(f"elements[{index}] must be a dictionary.")
        if "level" not in element or any(key not in element for key in keys):
            raise ValueError(f"elements[{index}] is missing required fields.")
        level = _integer(f"elements[{index}].level", element["level"])
        if level > 3:
            raise ValueError("Element levels must be in [1, 3].")
        values = {key: _finite(f"elements[{index}].{key}", element[key]) for key in keys}
        a, b = values["r_inner"], values["r_outer"]
        ti, to = values["r_tooth_in"], values["r_tooth_out"]
        if not 0.0 <= a < ti < to < b:
            raise ValueError(f"elements[{index}] has invalid radial bounds.")
        expected = {
            "r_center": a + (b - a) / 2.0,
            "W_slot": b - a,
            "w_tooth": to - ti,
        }
        for key, value in expected.items():
            if not math.isclose(values[key], value, rel_tol=1e-10, abs_tol=1e-12):
                raise ValueError(f"elements[{index}].{key} is inconsistent.")
        if not math.isclose(
            ti + (to - ti) / 2.0, values["r_center"],
            rel_tol=1e-10, abs_tol=1e-12,
        ):
            raise ValueError(f"elements[{index}] has an off-centre tooth.")
        if "z_tip" in element and element["z_tip"] is not None:
            values["z_tip"] = _finite(f"elements[{index}].z_tip", element["z_tip"])
        if "h_teeth" in element and element["h_teeth"] is not None:
            values["h_teeth"] = _positive(
                f"elements[{index}].h_teeth", element["h_teeth"]
            )
        result.append(ClutchElement(level=level, **values))  # type: ignore[typeddict-item]
    if not result:
        raise ValueError("elements must not be empty.")
    ordered = sorted(result, key=lambda item: item["r_inner"])
    for previous, current in zip(ordered, ordered[1:]):
        if current["r_inner"] < previous["r_outer"]:
            raise ValueError("Radial slot intervals must not overlap.")
    return result


def generate_annular_sector_prism_vertices(
    r_in: float,
    r_out: float,
    phi_start_rad: float,
    phi_end_rad: float,
    z_base: float = 0.0,
    num_pts_per_arc: int = 8,
) -> list[Any]:
    """Return counterclockwise Meep Vector3 vertices for a simple sector.

    Each arc includes both endpoints. Angles must be unwrapped and increasing,
    with span strictly below 2*pi. Curved boundaries are polygonal
    approximations. For a disk sector, use r_in=0.
    """
    inner = _finite("r_in", r_in)
    outer = _positive("r_out", r_out)
    if inner < 0.0 or inner >= outer:
        raise ValueError("Require 0 <= r_in < r_out.")
    start = _finite("phi_start_rad", phi_start_rad)
    end = _finite("phi_end_rad", phi_end_rad)
    base = _finite("z_base", z_base)
    count = _integer("num_pts_per_arc", num_pts_per_arc, minimum=2)
    span = end - start
    if not 0.0 < span < math.tau:
        raise ValueError("Angular span must lie strictly between 0 and 2*pi.")
    if span / (count - 1) >= math.pi:
        raise ValueError("Use more arc points so each angular step is below pi.")
    mp = _meep()
    # Reduce the phase before interpolation to avoid unnecessarily large angles.
    start = start % math.tau
    angles = [start + span * i / (count - 1) for i in range(count)]
    vertices = [
        mp.Vector3(outer * math.cos(phi), outer * math.sin(phi), base)
        for phi in angles
    ]
    if inner == 0.0:
        vertices.append(mp.Vector3(0.0, 0.0, base))
    else:
        vertices.extend(
            mp.Vector3(inner * math.cos(phi), inner * math.sin(phi), base)
            for phi in reversed(angles)
        )
    return vertices


def _square_sector_vertices(
    side: float, start_deg: float, end_deg: float, z_base: float
) -> list[Any]:
    """Exactly intersect an angular sector with an origin-centred square."""
    mp = _meep()
    half = side / 2.0
    start, end = math.radians(start_deg), math.radians(end_deg)
    angles = [start, end]
    for turn in range(-1, 3):
        for corner in (45.0, 135.0, 225.0, 315.0):
            angle = math.radians(corner + turn * 360.0)
            if start < angle < end:
                angles.append(angle)
    vertices = [mp.Vector3(0.0, 0.0, z_base)]
    for angle in sorted(angles):
        cosine, sine = math.cos(angle), math.sin(angle)
        radius = half / max(abs(cosine), abs(sine))
        vertices.append(mp.Vector3(radius * cosine, radius * sine, z_base))
    return vertices


def generate_redesigned_stator_geometry(
    elements: Iterable[ClutchElement],
    L_plate: float,
    t_membrane: float = 0.025,
    t_landing_pad: float = 0.150,
    plate_material: Any = None,
    void_material: Any = None,
    num_sectors: int = 4,
    aperture_arc_deg: float = 30.0,
    bridge_arc_deg: float = 60.0,
    z_pad_top: float | None = None,
    theta_stator_deg: float = 0.0,
) -> list[Any]:
    """Return Meep objects for a square membrane, bridge pads, and slots.

    The membrane occupies [-t_membrane, 0]. With z_pad_top=None, bridge
    pads occupy [-t_landing_pad, -t_membrane]; t_landing_pad is the total
    depth below z=0, not an additional thickness.

    With z_pad_top specified below the membrane, t_landing_pad is the pad
    thickness below z_pad_top. Bridge material extends from the pad bottom
    to the membrane; bridge slots are open above z_pad_top. Aperture slots
    overhang the membrane by 0.002 um at both faces in either mode.

    Positive theta_stator_deg rotates sectors counterclockwise around +z.
    Void objects are appended last so they override membrane material.
    """
    validated = _validated_elements(elements)
    side = _positive("L_plate", L_plate)
    membrane = _positive("t_membrane", t_membrane)
    pad = _positive("t_landing_pad", t_landing_pad)
    if z_pad_top is None:
        if pad <= membrane:
            raise ValueError("t_landing_pad must exceed t_membrane.")
        pad_bottom = -pad
        pad_top = None
    else:
        pad_top = _finite("z_pad_top", z_pad_top)
        if pad_top >= -membrane:
            raise ValueError("z_pad_top must lie below -t_membrane.")
        pad_bottom = _finite("z_pad_bot", pad_top - pad)
        if pad_bottom >= pad_top:
            raise ValueError("Landing pad thickness cannot be represented numerically.")
    bridge_height = _positive("bridge height", -membrane - pad_bottom)
    rotation = _finite("theta_stator_deg", theta_stator_deg) % 360.0
    sectors = _integer("num_sectors", num_sectors)
    aperture = _positive("aperture_arc_deg", aperture_arc_deg)
    bridge = _positive("bridge_arc_deg", bridge_arc_deg)
    pitch = 360.0 / sectors
    if not math.isclose(aperture + bridge, pitch, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("aperture_arc_deg + bridge_arc_deg must equal sector pitch.")
    if max(item["r_outer"] for item in validated) > side / 2.0:
        raise ValueError("L_plate must enclose every complete radial slot.")

    overhang = 0.002
    bridge_void_height = (
        _positive("bridge void height", -pad_top + overhang)
        if pad_top is not None else None
    )
    mp = _meep()
    metal = mp.metal if plate_material is None else plate_material
    void = mp.air if void_material is None else void_material
    geometry: list[Any] = [
        mp.Block(
            size=mp.Vector3(side, side, membrane),
            center=mp.Vector3(0.0, 0.0, -membrane / 2.0),
            material=metal,
        )
    ]
    for sector in range(sectors):
        start = sector * pitch + aperture + rotation
        end = (sector + 1) * pitch + rotation
        # Without an explicit centre, Meep extrudes from the vertex plane
        # along +z; specifying centre=(0,0,z) would move off-axis sectors.
        geometry.append(mp.Prism(
            vertices=_square_sector_vertices(side, start, end, pad_bottom),
            height=bridge_height,
            material=metal,
        ))

    for sector in range(sectors):
        start = math.radians(sector * pitch + rotation)
        end = math.radians(sector * pitch + aperture + rotation)
        for element in validated:
            geometry.append(mp.Prism(
                vertices=generate_annular_sector_prism_vertices(
                    element["r_inner"],
                    element["r_outer"],
                    start,
                    end,
                    z_base=-membrane - overhang,
                ),
                height=membrane + 2.0 * overhang,
                material=void,
            ))
            if pad_top is not None:
                geometry.append(mp.Prism(
                    vertices=generate_annular_sector_prism_vertices(
                        element["r_inner"],
                        element["r_outer"],
                        end,
                        math.radians((sector + 1) * pitch + rotation),
                        z_base=pad_top,
                    ),
                    height=bridge_void_height,
                    material=void,
                ))
    return geometry


def generate_redesigned_rotor_geometry(
    elements: Iterable[ClutchElement],
    H_teeth: float = 0.250,
    z_tip: float = 0.015,
    rotor_material: Any = None,
    num_sectors: int = 4,
    tooth_arc_deg: float = 15.0,
    theta_rotor_deg: float = 0.0,
    tooth_center_offset_deg: float = 15.0,
) -> list[Any]:
    """Return teeth only; no unspecified rotor backing plate is added.

    Each tooth is initially centred at tooth_center_offset_deg plus its
    sector offset. Positive theta rotates counterclockwise around +z.
    Default teeth therefore span [7.5, 22.5] at theta=0 and [52.5, 67.5]
    at theta=45.

    Non-None per-element z_tip and h_teeth override the axial defaults.
    """
    validated = _validated_elements(elements)
    height = _positive("H_teeth", H_teeth)
    tip = _finite("z_tip", z_tip)
    _finite("z_tip + H_teeth", tip + height)
    sectors = _integer("num_sectors", num_sectors)
    arc = _positive("tooth_arc_deg", tooth_arc_deg)
    rotation = _finite("theta_rotor_deg", theta_rotor_deg) % 360.0
    offset = _finite("tooth_center_offset_deg", tooth_center_offset_deg) % 360.0
    pitch = 360.0 / sectors
    if arc >= pitch:
        raise ValueError("tooth_arc_deg must be smaller than the sector pitch.")

    mp = _meep()
    material = mp.metal if rotor_material is None else rotor_material
    geometry: list[Any] = []
    for sector in range(sectors):
        centre = sector * pitch + offset + rotation
        start, end = math.radians(centre - arc / 2.0), math.radians(centre + arc / 2.0)
        for element in validated:
            elem_tip = _finite("element z_tip", element.get("z_tip", tip))
            elem_height = _positive("element h_teeth", element.get("h_teeth", height))
            _finite("element z_tip + h_teeth", elem_tip + elem_height)
            geometry.append(mp.Prism(
                vertices=generate_annular_sector_prism_vertices(
                    element["r_tooth_in"],
                    element["r_tooth_out"],
                    start,
                    end,
                    z_base=elem_tip,
                ),
                height=elem_height,
                material=material,
            ))
    return geometry


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--N", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--r-min", type=float, default=0.30)
    parser.add_argument("--r-max", type=float, default=1.35)
    parser.add_argument("--w1-ratio", type=float, default=0.23)
    parser.add_argument("--min-tooth-w", type=float, default=0.020)
    parser.add_argument("--z-tip", type=float, default=0.015)
    parser.add_argument(
        "--z-pad-top", type=float, default=None,
        help="Recessed pad top; defaults to -0.115 um for a negative z_tip.",
    )
    parser.add_argument("--h-teeth", type=float, default=0.250)
    parser.add_argument("--target-suppression", type=float, default=1e-50)
    parser.add_argument("--safety-factor", type=float, default=1.5)
    parser.add_argument("--min-floor", type=float, default=3.0)
    parser.add_argument("--max-ceil", type=float, default=12.0)
    parser.add_argument(
        "--d-eff-um", type=float, nargs="+", default=None,
        help="Explicit effective gaps; default verifies axial and radial tooth gaps.",
    )
    parser.add_argument(
        "--build-geometry", action="store_true",
        help="Also instantiate Meep stator and rotor objects.",
    )
    parser.add_argument("--plate-size", type=float, default=3.0)
    args = parser.parse_args(argv)

    try:
        elements = get_scoped_clutch_elements(
            args.N, args.r_min, args.r_max, args.w1_ratio, args.min_tooth_w
        )
        tip = _finite("z_tip for verification", args.z_tip)
        pad_top = args.z_pad_top
        if pad_top is None and tip < 0.0:
            pad_top = -0.115
        if pad_top is not None:
            pad_top = _finite("z_pad_top", pad_top)
            if pad_top >= -0.025:
                raise ValueError("z_pad_top must lie below -t_membrane (-0.025 um).")
        axial_gap = _positive(
            "effective axial gap",
            abs(tip - pad_top) if tip < 0.0 else tip,
        )
        height = _positive("h_teeth", args.h_teeth)
        _finite("tooth top", tip + height)
        print(f"Cantor clutch verification: N={args.N}; distances in um")
        if pad_top is None:
            print("Membrane z=[-0.025, 0]; bridge reinforcement z=[-0.150, -0.025]")
        else:
            print(
                f"Membrane z=[-0.025, 0]; bridge reinforcement "
                f"z=[{pad_top - 0.150:.9g}, -0.025]; "
                f"recessed landing pad top z={pad_top:.9g}"
            )
        print(f"Teeth z=[{tip:.9g}, {tip + height:.9g}]")
        print("Clearances below are arc lengths at the stated radii, not chords.")

        for index, element in enumerate(elements):
            gap = (element["W_slot"] - element["w_tooth"]) / 2.0
            print(
                f"Ring {index + 1}: level={element['level']}, "
                f"slot=[{element['r_inner']:.9f}, {element['r_outer']:.9f}], "
                f"centre={element['r_center']:.9f}, "
                f"W_slot={element['W_slot']:.9f}, "
                f"tooth=[{element['r_tooth_in']:.9f}, "
                f"{element['r_tooth_out']:.9f}], "
                f"w_tooth={element['w_tooth']:.9f}, "
                f"radial clearance={gap * 1000.0:.3f} nm per side"
            )

        for rotation, clearance_deg in ((0.0, 7.5), (45.0, 22.5)):
            print(f"\ntheta_rotor={rotation:g} deg")
            for sector in range(4):
                offset = sector * 90.0
                print(
                    f"  Sector {sector}: aperture=[{offset:g}, {offset + 30:g}] deg; "
                    f"bridge=[{offset + 30:g}, {offset + 90:g}] deg; "
                    f"tooth=[{offset + 7.5 + rotation:g}, "
                    f"{offset + 22.5 + rotation:g}] deg; "
                    f"angular clearance={clearance_deg:g} deg per side"
                )
            for index, element in enumerate(elements):
                arc = math.radians(clearance_deg)
                print(
                    f"  Ring {index + 1}: centre-radius arc clearance="
                    f"{element['r_center'] * arc * 1000.0:.3f} nm; "
                    f"inner-to-outer tooth-radius range="
                    f"[{element['r_tooth_in'] * arc * 1000.0:.3f}, "
                    f"{element['r_tooth_out'] * arc * 1000.0:.3f}] nm"
                )

        cases: list[tuple[str, float]]
        if args.d_eff_um is not None:
            cases = [
                (f"explicit gap {index + 1}", gap)
                for index, gap in enumerate(args.d_eff_um)
            ]
        else:
            cases = [("axial tip gap", axial_gap)]
            cases.extend(
                (
                    f"ring {index + 1} radial gap",
                    (element["W_slot"] - element["w_tooth"]) / 2.0,
                )
                for index, element in enumerate(elements)
            )
        print("\nDynamic T_run provenance:")
        print("Effective-gap choices are verification inputs, not a field-derived model.")
        for label, gap in cases:
            run_time, diagnostics = compute_dynamic_Trun(
                gap,
                args.target_suppression,
                args.safety_factor,
                args.min_floor,
                args.max_ceil,
            )
            print(f"{label}: T_run={run_time:.9g}")
            print(json.dumps(diagnostics, indent=2, sort_keys=True, allow_nan=False))

        if args.build_geometry:
            stator = generate_redesigned_stator_geometry(
                elements, args.plate_size, z_pad_top=pad_top
            )
            for rotation in (0.0, 45.0):
                rotor = generate_redesigned_rotor_geometry(
                    elements,
                    H_teeth=height,
                    z_tip=tip,
                    theta_rotor_deg=rotation,
                )
                print(
                    f"Meep objects at theta={rotation:g}: "
                    f"{len(stator)} stator, {len(rotor)} rotor"
                )
    except (TypeError, ValueError, ImportError, OverflowError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
