#!/usr/bin/env python3
"""
Dedicated 3D Multi-Scale Cantor Fractal & Matched-Control Architecture Module.
==============================================================================
Single source of truth for:
  1. Lab-bound recursive Cantor generation in all three cylindrical dimensions
     (radial r, azimuthal theta, axial z) across both rotor teeth and stator slots.
  2. Strictly orthogonal 2^3 factorial operators (U_r, U_theta, U_z) with zero
     cross-conditional parameter switches and an invariant stator landing-pad
     elevation (DEFAULT_Z_PAD_TOP_UM).
  3. Matched non-fractal controls (Shuffled, Monotonic/Linear, Uniform, and
     Out-of-Phase) constructed from the exact multiset of features and active
     tooth area of the most-fractal configuration.
  4. Vectorized 3D Vector-Dyadic BEM evaluation and log-periodic wavenumber
     modulation extraction.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
import math
import time
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from execution.casimir_bem_solver import (
    ClutchSurfaceMesh,
    Geometry,
    MEEP_FORCE_TO_SI,
    MaterialModel,
    _disk_self_term,
    _quadrature,
    _rotation,
)
from execution.clutch_geometry_redesign import (
    DEFAULT_H_TEETH_ROTATIONAL_UM,
    DEFAULT_LAB_MIN_AXIAL_STEP_UM,
    DEFAULT_LAB_MIN_AZIMUTHAL_ARC_UM,
    DEFAULT_LAB_MIN_CLEARANCE_UM,
    DEFAULT_LAB_MIN_FEATURE_UM,
    DEFAULT_MAX_THETA_CANTOR_DEPTH,
    DEFAULT_MIN_TOOTH_W_UM,
    DEFAULT_N3_ANGLES_BY_GEN_DEG,
    DEFAULT_N3_APERTURE_MARGIN_DEG,
    DEFAULT_N3_CANTOR_GENERATIONS,
    DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM,
    DEFAULT_N3_CONFORMAL_SLOT_WIDTHS_NM,
    DEFAULT_N3_H_TEETH_BY_GEN_UM,
    DEFAULT_N3_ISO_AREA_TARGET_UM2,
    DEFAULT_N3_MAX_TOOTH_ARC_DEG,
    DEFAULT_N3_MONOTONIC_GENERATIONS,
    DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM,
    DEFAULT_N3_OUT_OF_PHASE_SLOT_ORDER,
    DEFAULT_N3_RAIL_CLEARANCE_UM,
    DEFAULT_N3_RAIL_WIDTH_UM,
    DEFAULT_N3_R_MAX_UM,
    DEFAULT_N3_SUBTOOTH_MIN_SLOT_NM,
    DEFAULT_N3_TOOTH_ARC_DEG,
    DEFAULT_N3_UNIFORM_GENERATIONS,
    DEFAULT_N3_UNIFORM_SLOT_WIDTHS_NM,
    DEFAULT_N3_W1_RATIO,
    DEFAULT_N3_Z_TIPS_BY_GEN_UM,
    DEFAULT_NUM_SECTORS,
    DEFAULT_ROTATIONAL_APERTURE_ARC_DEG,
    DEFAULT_R_MIN_UM,
    DEFAULT_T_LANDING_PAD_UM,
    DEFAULT_T_MEMBRANE_UM,
    DEFAULT_Z_PAD_TOP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
    compute_max_feasible_cantor_depth,
    disengaged_angle_deg,
    get_bounded_cantor_intervals,
    get_cantor_dust_intervals,
    get_cantor_radial_intervals,
    get_equal_subslots,
)
from execution.run_fractal_advantage_study import (
    TrackSpec3D,
    make_track_element,
    repository_face,
    subdivisions,
    tooth_segments,
)

# Canonical log-periodic fundamental frequency for base-3 Cantor scaling:
CANTOR_BASE_B: float = 3.0
CANTOR_OMEGA_FUNDAMENTAL: float = 2.0 * math.pi / math.log(CANTOR_BASE_B)
SPECTRAL_FIT_KAPPA_MIN_UM_INV: float = 1.2
SPECTRAL_FIT_KAPPA_MAX_UM_INV: float = 25.0
DEFAULT_BEM_QUADRATURE_ORDER: int = 24
DEFAULT_DISENGAGED_THETA_DEG: float = disengaged_angle_deg(DEFAULT_ROTATIONAL_APERTURE_ARC_DEG)

# Deterministic seed for reproducible shuffled controls:
DEFAULT_SHUFFLE_SEED: int = 20261106


@dataclass(frozen=True, slots=True)
class SubTooth3D:
    """Single 3D rotor sub-tooth prism within a stator sub-slot."""
    r_tooth_in: float
    r_tooth_out: float
    z_tip: float
    h_teeth: float
    phi_offsets_deg: tuple[tuple[float, float], ...]
    sub_level_r: int = 1
    sub_level_theta: int = 1
    sub_level_z: int = 1


@dataclass(frozen=True, slots=True)
class SlotSpec3D:
    """Single primary stator slot containing stator Cantor sub-slots and rotor Cantor sub-teeth."""
    r_inner: float
    r_outer: float
    level: int
    sub_teeth: tuple[SubTooth3D, ...]
    stator_subslots: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class Unified3DDesign:
    """Complete 3D (r, theta, z) clutch design with strictly invariant stator parameters."""
    name: str
    code: str
    u_r: int
    u_theta: int
    u_z: int
    family_role: str
    slots: tuple[SlotSpec3D, ...]
    R_min: float = DEFAULT_R_MIN_UM
    R_max: float = DEFAULT_N3_R_MAX_UM
    aperture_arc_deg: float = DEFAULT_ROTATIONAL_APERTURE_ARC_DEG
    t_membrane: float = DEFAULT_T_MEMBRANE_UM
    t_landing_pad: float = DEFAULT_T_LANDING_PAD_UM
    z_pad_top: float = DEFAULT_Z_PAD_TOP_UM


def active_area_unified(design: Unified3DDesign) -> float:
    """Compute exact C4 active rotor tooth footprint area in um^2."""
    total = 0.0
    for s in design.slots:
        for st in s.sub_teeth:
            rc = 0.5 * (st.r_tooth_in + st.r_tooth_out)
            w = st.r_tooth_out - st.r_tooth_in
            for _, arc_deg in st.phi_offsets_deg:
                total += float(DEFAULT_NUM_SECTORS) * math.radians(arc_deg) * rc * w
    return float(total)


def _scale_lobe_group_within_aperture(
    phis: tuple[tuple[float, float], ...],
    factor: float,
    max_arc_deg: float,
) -> tuple[tuple[float, float], ...]:
    """Scale a complete tooth lobe group uniformly by `eff_factor` so that the overall
    group span (max_edge - min_edge) never exceeds `max_arc_deg` and inter-lobe gaps
    remain strictly non-overlapping."""
    min_edge = min(off - 0.5 * arc for off, arc in phis)
    max_edge = max(off + 0.5 * arc for off, arc in phis)
    span_deg = max(max_edge - min_edge, 1e-12)
    eff_factor = min(factor, max_arc_deg / span_deg)
    return tuple((off * eff_factor, arc * eff_factor) for off, arc in phis)


def scale_design_angles_to_iso_area(
    design: Unified3DDesign,
    target_area_um2: float = DEFAULT_N3_ISO_AREA_TARGET_UM2,
    max_arc_deg: float = DEFAULT_N3_MAX_TOOTH_ARC_DEG,
    area_tol_um2: float = 1e-2,
) -> Unified3DDesign:
    """Scale azimuthal tooth arcs to match target_area_um2 while strictly enforcing
    total azimuthal span per slot <= max_arc_deg (preventing aperture overhang)."""
    cur_slots = list(design.slots)
    for _ in range(30):
        cur_design = dataclasses.replace(design, slots=tuple(cur_slots))
        cur_area = active_area_unified(cur_design)
        if abs(cur_area - target_area_um2) <= 1e-9:
            return cur_design
        factor = target_area_um2 / max(cur_area, 1e-12)
        new_slots: list[SlotSpec3D] = []
        for s in cur_slots:
            new_sub = tuple(
                dataclasses.replace(
                    st,
                    phi_offsets_deg=_scale_lobe_group_within_aperture(
                        st.phi_offsets_deg, factor, max_arc_deg
                    ),
                )
                for st in s.sub_teeth
            )
            new_slots.append(dataclasses.replace(s, sub_teeth=new_sub))
        cur_slots = new_slots
    final_design = dataclasses.replace(design, slots=tuple(cur_slots))
    final_area = active_area_unified(final_design)
    if abs(final_area - target_area_um2) > area_tol_um2:
        raise ValueError(
            f"Design {design.code} area {final_area:.6f} deviates from target {target_area_um2:.6f} "
            f"by more than area_tol_um2={area_tol_um2:.6f} under max_arc_deg={max_arc_deg:.2f}"
        )
    return final_design


def build_subteeth_for_radial_intervals(
    r_inner: float,
    r_outer: float,
    slot_level: int,
    r_subslots: Sequence[tuple[float, float]],
    sub_level_r: int,
    *,
    enable_theta_cantor: bool,
    enable_z_cantor: bool,
    min_tooth_w_um: float = DEFAULT_MIN_TOOTH_W_UM,
    min_clearance_um: float = DEFAULT_LAB_MIN_CLEARANCE_UM,
    min_arc_um: float = DEFAULT_LAB_MIN_AZIMUTHAL_ARC_UM,
    base_w_ratio: float = DEFAULT_N3_W1_RATIO,
    base_theta_deg: float = DEFAULT_N3_TOOTH_ARC_DEG,
    base_z_tip_um: float = DEFAULT_Z_TIP_ROTATIONAL_UM,
) -> tuple[SubTooth3D, ...]:
    """Construct 3D rotor sub-teeth inside a sequence of radial sub-slot intervals `r_subslots`
    using the exact (theta, z) operators with zero conditional branches."""
    # Azimuthal (theta) Cantor hierarchy (depth_theta = 0 when enable_theta_cantor is False):
    th_deg = base_theta_deg + int(enable_theta_cantor) * (
        DEFAULT_N3_ANGLES_BY_GEN_DEG[slot_level] - base_theta_deg
    )
    r_mid_slot = 0.5 * (r_inner + r_outer)
    arc_len_um = r_mid_slot * math.radians(th_deg)
    depth_theta = int(enable_theta_cantor) * compute_max_feasible_cantor_depth(
        arc_len_um,
        min_arc_um,
        max_depth_cap=DEFAULT_MAX_THETA_CANTOR_DEPTH,
    )
    theta_intervals = get_cantor_dust_intervals(depth_theta, -0.5 * th_deg, 0.5 * th_deg)
    phi_list: tuple[tuple[float, float], ...] = tuple(
        (0.5 * (a + b), b - a) for a, b in theta_intervals
    )

    # Axial (z) Cantor staircase hierarchy (strictly above DEFAULT_Z_PAD_TOP_UM = -0.115 um):
    zt = base_z_tip_um + int(enable_z_cantor) * (
        DEFAULT_N3_Z_TIPS_BY_GEN_UM[slot_level] - base_z_tip_um
    )
    ht = -zt

    min_subslot_um = min_tooth_w_um + 2.0 * min_clearance_um
    sub_teeth: list[SubTooth3D] = []
    for sub_in, sub_out in r_subslots:
        sub_w = sub_out - sub_in
        if sub_w + 1e-12 < min_subslot_um:
            raise ValueError(
                f"Sub-slot width {sub_w:.6f} um is narrower than required minimum {min_subslot_um:.6f} um"
            )
        max_tooth_w = sub_w - 2.0 * min_clearance_um
        w_t = min(max(base_w_ratio * sub_w, min_tooth_w_um), max_tooth_w)
        mid_r = 0.5 * (sub_in + sub_out)
        sub_teeth.append(
            SubTooth3D(
                r_tooth_in=mid_r - 0.5 * w_t,
                r_tooth_out=mid_r + 0.5 * w_t,
                z_tip=zt,
                h_teeth=ht,
                phi_offsets_deg=phi_list,
                sub_level_r=sub_level_r,
                sub_level_theta=depth_theta + 1,
                sub_level_z=slot_level,
            )
        )
    return tuple(sub_teeth)


def build_lab_bounded_subteeth_for_slot(
    r_inner: float,
    r_outer: float,
    slot_level: int,
    *,
    enable_r_cantor: bool,
    enable_theta_cantor: bool,
    enable_z_cantor: bool,
    min_tooth_w_um: float = DEFAULT_MIN_TOOTH_W_UM,
    min_clearance_um: float = DEFAULT_LAB_MIN_CLEARANCE_UM,
    min_arc_um: float = DEFAULT_LAB_MIN_AZIMUTHAL_ARC_UM,
    base_w_ratio: float = DEFAULT_N3_W1_RATIO,
    base_theta_deg: float = DEFAULT_N3_TOOTH_ARC_DEG,
    base_z_tip_um: float = DEFAULT_Z_TIP_ROTATIONAL_UM,
) -> tuple[SubTooth3D, ...]:
    """Apply recursive Cantor subdivision in (r, theta, z) to a single slot bounded by lab limits
    with zero conditional branches."""
    slot_w_um = r_outer - r_inner
    min_subslot_um = min_tooth_w_um + 2.0 * min_clearance_um
    depth_r = int(enable_r_cantor) * compute_max_feasible_cantor_depth(slot_w_um, min_subslot_um)
    r_subslots = get_cantor_dust_intervals(depth_r, r_inner, r_outer)
    return build_subteeth_for_radial_intervals(
        r_inner,
        r_outer,
        slot_level,
        r_subslots,
        depth_r + 1,
        enable_theta_cantor=enable_theta_cantor,
        enable_z_cantor=enable_z_cantor,
        min_tooth_w_um=min_tooth_w_um,
        min_clearance_um=min_clearance_um,
        min_arc_um=min_arc_um,
        base_w_ratio=base_w_ratio,
        base_theta_deg=base_theta_deg,
        base_z_tip_um=base_z_tip_um,
    )


def build_equal_subdivided_design(
    name: str,
    code: str,
    family_role: str,
    slot_widths_nm: Sequence[float],
    slot_levels: Sequence[int],
    sub_counts: Sequence[int],
    *,
    u_theta: bool,
    u_z: bool,
    sub_rib_um: float = DEFAULT_LAB_MIN_FEATURE_UM,
    iso_area: bool = True,
    R_min: float = DEFAULT_R_MIN_UM,
    R_max: float = DEFAULT_N3_R_MAX_UM,
) -> Unified3DDesign:
    """Construct a non-fractal equal-subdivision control where each primary slot k is subdivided
    into `sub_counts[k]` equal stator sub-slots separated by standard `sub_rib_um` stator ribs
    (instead of Cantor middle-third ribs) and houses `sub_counts[k]` rotor sub-teeth."""
    if len(slot_widths_nm) == 0 or len(slot_widths_nm) != len(slot_levels) or len(slot_widths_nm) != len(sub_counts):
        raise ValueError("slot_widths_nm, slot_levels, and sub_counts must be non-empty and have equal lengths")
    if any(float(w) <= 0.0 for w in slot_widths_nm):
        raise ValueError("All slot widths in slot_widths_nm must be strictly positive")
    if any(int(c) < 1 for c in sub_counts):
        raise ValueError("All entries in sub_counts must be >= 1")
    total_slot_um = sum(float(w) * 1e-3 for w in slot_widths_nm)
    if total_slot_um >= (R_max - R_min):
        raise ValueError("Total slot width must be strictly less than the radial span (R_max - R_min)")
    rib_um = ((R_max - R_min) - total_slot_um) / float(len(slot_widths_nm) + 1)
    cursor = R_min + rib_um
    slots: list[SlotSpec3D] = []
    for w_nm, lvl, c_sub in zip(slot_widths_nm, slot_levels, sub_counts, strict=True):
        s_um = float(w_nm) * 1e-3
        r_in, r_out = cursor, cursor + s_um
        cursor += s_um + rib_um
        stator_subslots = tuple(get_equal_subslots(int(c_sub), r_in, r_out, rib_um=sub_rib_um))
        sub_teeth = build_subteeth_for_radial_intervals(
            r_in,
            r_out,
            int(lvl),
            stator_subslots,
            int(c_sub),
            enable_theta_cantor=u_theta,
            enable_z_cantor=u_z,
        )
        slots.append(
            SlotSpec3D(
                r_inner=r_in,
                r_outer=r_out,
                level=int(lvl),
                sub_teeth=sub_teeth,
                stator_subslots=stator_subslots,
            )
        )

    raw_design = Unified3DDesign(
        name=name,
        code=code,
        u_r=1,
        u_theta=int(u_theta),
        u_z=int(u_z),
        family_role=family_role,
        slots=tuple(slots),
        R_min=R_min,
        R_max=R_max,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )
    if iso_area:
        return scale_design_angles_to_iso_area(raw_design, DEFAULT_N3_ISO_AREA_TARGET_UM2, DEFAULT_N3_MAX_TOOTH_ARC_DEG)
    return raw_design


def build_design_from_slot_sequence(
    name: str,
    code: str,
    family_role: str,
    slot_widths_nm: Sequence[float],
    slot_levels: Sequence[int],
    *,
    u_r: bool,
    u_theta: bool,
    u_z: bool,
    enable_stator_subribs: bool = True,
    iso_area: bool = True,
    R_min: float = DEFAULT_R_MIN_UM,
    R_max: float = DEFAULT_N3_R_MAX_UM,
) -> Unified3DDesign:
    """Construct a Unified3DDesign from any slot width sequence using the exact same
    orthogonal (U_r, U_theta, U_z) rules and invariant DEFAULT_Z_PAD_TOP_UM."""
    if len(slot_widths_nm) == 0 or len(slot_widths_nm) != len(slot_levels):
        raise ValueError("slot_widths_nm and slot_levels must be non-empty and have equal lengths")
    if any(float(w) <= 0.0 for w in slot_widths_nm):
        raise ValueError("All slot widths in slot_widths_nm must be strictly positive")
    total_slot_um = sum(float(w) * 1e-3 for w in slot_widths_nm)
    if total_slot_um >= (R_max - R_min):
        raise ValueError("Total slot width must be strictly less than the radial span (R_max - R_min)")
    rib_um = ((R_max - R_min) - total_slot_um) / float(len(slot_widths_nm) + 1)
    min_subslot_um = DEFAULT_MIN_TOOTH_W_UM + 2.0 * DEFAULT_LAB_MIN_CLEARANCE_UM
    cursor = R_min + rib_um
    slots: list[SlotSpec3D] = []
    for w_nm, lvl in zip(slot_widths_nm, slot_levels, strict=True):
        s_um = float(w_nm) * 1e-3
        r_in, r_out = cursor, cursor + s_um
        cursor += s_um + rib_um
        sub_teeth = build_lab_bounded_subteeth_for_slot(
            r_in,
            r_out,
            int(lvl),
            enable_r_cantor=u_r,
            enable_theta_cantor=u_theta,
            enable_z_cantor=u_z,
        )
        depth_s = int(u_r and enable_stator_subribs) * compute_max_feasible_cantor_depth(s_um, min_subslot_um)
        stator_subslots = tuple(get_cantor_dust_intervals(depth_s, r_in, r_out))
        slots.append(
            SlotSpec3D(
                r_inner=r_in,
                r_outer=r_out,
                level=int(lvl),
                sub_teeth=sub_teeth,
                stator_subslots=stator_subslots,
            )
        )

    raw_design = Unified3DDesign(
        name=name,
        code=code,
        u_r=int(u_r),
        u_theta=int(u_theta),
        u_z=int(u_z),
        family_role=family_role,
        slots=tuple(slots),
        R_min=R_min,
        R_max=R_max,
        z_pad_top=DEFAULT_Z_PAD_TOP_UM,
    )
    if iso_area:
        return scale_design_angles_to_iso_area(raw_design, DEFAULT_N3_ISO_AREA_TARGET_UM2, DEFAULT_N3_MAX_TOOTH_ARC_DEG)
    return raw_design


def make_factorial_design(
    name: str,
    code: str,
    family_role: str,
    enable_stator_subribs: bool,
    u_r_subteeth: bool,
    u_theta: bool,
    u_z: bool,
    iso_area: bool = True,
) -> Unified3DDesign:
    """Build one member of the strictly orthogonal 2^3 factorial fractal hierarchy."""
    return build_design_from_slot_sequence(
        name=name,
        code=code,
        family_role=family_role,
        slot_widths_nm=DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM,
        slot_levels=DEFAULT_N3_CANTOR_GENERATIONS,
        u_r=u_r_subteeth,
        u_theta=u_theta,
        u_z=u_z,
        enable_stator_subribs=enable_stator_subribs,
        iso_area=iso_area,
    )


def build_matched_controls_for_most_fractal(
    most_fractal: Unified3DDesign,
    shuffle_seed: int = DEFAULT_SHUFFLE_SEED,
) -> list[Unified3DDesign]:
    """Given the most-fractal configuration (F3_111), construct both the 7-slot primary controls
    (C1..C5) and the exact 12-slot / 12-tooth / 24-lobe non-fractal controls (C6..C10):
      1. C1_Uni000: Uniform 7-track flat baseline (0,0,0).
      2. C2_Uni111: Uniform 7-track passed through the exact same (U_r, U_theta, U_z) lab-bounded rules.
      3. C3_MonoGen: Monotonic/Linear 7-track [50,50,50,50,150,150,450] with monotonic (theta, z) rules
         and primary-slot radial profile (u_r=False, i.e., non-fractal radial trenches).
      4. C4_Shuf111: Shuffled control independently permuting the primary radial slot widths and (theta, z)
         generation rules of F3_111 without radial Cantor sub-slots (u_r=False) at matched active area.
      5. C5_OutPhase: Out-of-phase assignment of the (theta, z) generation parameters on the primary Cantor
         slots without radial Cantor sub-slots (u_r=False) at matched active area.
      6. C6_Uni12: Uniform 12-slot / 12-tooth / 24-lobe periodic grating sharing the exact primary slot width
         budget at uniform generation depth.
      7. C7_Lin12: Linearly graded 12-slot / 12-tooth / 24-lobe grating whose slot widths increase linearly
         from the minimum Cantor slot width while preserving the exact total slot width and sub-tooth generation multiset.
      8. C8_Mono12: Monotonic 7-slot control subdivided into the exact sorted sub-slot counts (1,1,1,1,2,2,4) = 12
         equal sub-slots separated by standard lab-minimum stator sub-ribs (instead of Cantor middle-third ribs),
         with 12 rotor sub-teeth and 24 azimuthal lobes.
      9. C9_Shuf12: Shuffled 7-slot control with 12 equal sub-slots (12 rotor sub-teeth, 24 lobes) that permutes
         the radial slot positions and independently permutes the (theta, z) generation levels.
      10. C10_OutPhase12: Out-of-phase 7-slot control with 12 equal sub-slots (12 rotor sub-teeth, 24 lobes) on
          the primary Cantor slot widths with out-of-phase (theta, z) generation levels.
    """
    # C1: Uniform 7-slot flat baseline (0,0,0)
    c1 = build_design_from_slot_sequence(
        name="Ctrl_Uniform_000_Flat",
        code="C1_Uni000",
        family_role="ctrl_uniform_flat",
        slot_widths_nm=DEFAULT_N3_UNIFORM_SLOT_WIDTHS_NM,
        slot_levels=DEFAULT_N3_UNIFORM_GENERATIONS,
        u_r=False,
        u_theta=False,
        u_z=False,
        iso_area=True,
    )

    # C2: Uniform 7-slot passed through the exact same lab-bounded (U_r, U_theta, U_z) operators
    c2 = build_design_from_slot_sequence(
        name="Ctrl_Uniform_111_Matched",
        code="C2_Uni111",
        family_role="ctrl_uniform_111",
        slot_widths_nm=DEFAULT_N3_UNIFORM_SLOT_WIDTHS_NM,
        slot_levels=DEFAULT_N3_UNIFORM_GENERATIONS,
        u_r=True,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # C3: Monotonic/Linear 7-slot non-fractal radial control (u_r=False) with matched (theta, z) grading
    c3 = build_design_from_slot_sequence(
        name="Ctrl_Monotonic_011_Matched",
        code="C3_MonoGen",
        family_role="ctrl_monotonic_011",
        slot_widths_nm=DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM,
        slot_levels=DEFAULT_N3_MONOTONIC_GENERATIONS,
        u_r=False,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # C4: Shuffled cross-dimensional control (permutes the primary slot widths and generation rules without radial Cantor sub-slots)
    rng = np.random.default_rng(shuffle_seed)
    perm_w = list(rng.permutation(len(most_fractal.slots)))
    perm_g = list(rng.permutation(len(most_fractal.slots)))
    shuf_widths_nm = tuple((most_fractal.slots[i].r_outer - most_fractal.slots[i].r_inner) * 1000.0 for i in perm_w)
    shuf_levels = tuple(most_fractal.slots[i].level for i in perm_g)
    c4 = build_design_from_slot_sequence(
        name="Ctrl_Shuffled_011_IsoArea",
        code="C4_Shuf111",
        family_role="ctrl_shuffled_011",
        slot_widths_nm=shuf_widths_nm,
        slot_levels=shuf_levels,
        u_r=False,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # C5: Out-of-Phase Control (permutes generation labels across the primary Cantor slots without radial Cantor sub-slots)
    anti_gens = tuple(DEFAULT_N3_CANTOR_GENERATIONS[i] for i in DEFAULT_N3_OUT_OF_PHASE_SLOT_ORDER)
    c5 = build_design_from_slot_sequence(
        name="Ctrl_OutOfPhase_011_IsoArea",
        code="C5_OutPhase",
        family_role="ctrl_outofphase_011",
        slot_widths_nm=DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM,
        slot_levels=anti_gens,
        u_r=False,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # Extract exact sub-slot counts and sub-tooth generation multiset from most_fractal (F3_111):
    primary_widths_nm = tuple((s.r_outer - s.r_inner) * 1000.0 for s in most_fractal.slots)
    primary_sub_counts = tuple(max(1, len(s.stator_subslots)) for s in most_fractal.slots)
    subtooth_levels = tuple(st.sub_level_z for s in most_fractal.slots for st in s.sub_teeth)
    n_total_sub = len(subtooth_levels)
    total_primary_width_nm = float(sum(primary_widths_nm))
    min_primary_width_nm = float(min(primary_widths_nm))
    mean_sub_width_nm = total_primary_width_nm / float(n_total_sub)

    # C6: Uniform 12-slot / 12-tooth / 24-lobe periodic grating sharing the exact primary slot budget
    uni12_widths_nm = tuple([mean_sub_width_nm] * n_total_sub)
    uni12_levels = tuple([DEFAULT_N3_UNIFORM_GENERATIONS[0]] * n_total_sub)
    c6 = build_design_from_slot_sequence(
        name="Ctrl_Uniform12_111_IsoArea",
        code="C6_Uni12",
        family_role="ctrl_uniform12_111",
        slot_widths_nm=uni12_widths_nm,
        slot_levels=uni12_levels,
        u_r=True,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # C7: Linearly graded 12-slot / 12-tooth / 24-lobe grating with monotonic generation multiset
    max_lin_width_nm = 2.0 * mean_sub_width_nm - min_primary_width_nm
    lin12_widths_nm = tuple(float(x) for x in np.linspace(min_primary_width_nm, max_lin_width_nm, n_total_sub))
    lin12_levels = tuple(sorted(subtooth_levels, reverse=True))
    c7 = build_design_from_slot_sequence(
        name="Ctrl_Linear12_111_IsoArea",
        code="C7_Lin12",
        family_role="ctrl_linear12_111",
        slot_widths_nm=lin12_widths_nm,
        slot_levels=lin12_levels,
        u_r=True,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # C8: Monotonic 7-slot control subdivided into (1,1,1,1,2,2,4)=12 equal sub-slots separated by standard 15 nm stator ribs
    mono_sub_counts = tuple(sorted(primary_sub_counts))
    c8 = build_equal_subdivided_design(
        name="Ctrl_Monotonic7_12Sub_IsoArea",
        code="C8_Mono12",
        family_role="ctrl_monotonic7_12sub",
        slot_widths_nm=DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM,
        slot_levels=DEFAULT_N3_MONOTONIC_GENERATIONS,
        sub_counts=mono_sub_counts,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # C9: Shuffled 7-slot control with 12 equal sub-slots (permutes slot positions & sub-counts together, and permutes levels)
    shuf_sub_counts = tuple(primary_sub_counts[i] for i in perm_w)
    c9 = build_equal_subdivided_design(
        name="Ctrl_Shuffled7_12Sub_IsoArea",
        code="C9_Shuf12",
        family_role="ctrl_shuffled7_12sub",
        slot_widths_nm=shuf_widths_nm,
        slot_levels=shuf_levels,
        sub_counts=shuf_sub_counts,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    # C10: Out-of-Phase 7-slot control with 12 equal sub-slots on the primary Cantor slots
    c10 = build_equal_subdivided_design(
        name="Ctrl_OutOfPhase7_12Sub_IsoArea",
        code="C10_OutPhase12",
        family_role="ctrl_outofphase7_12sub",
        slot_widths_nm=DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM,
        slot_levels=anti_gens,
        sub_counts=primary_sub_counts,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )

    return [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10]


def build_all_study_designs() -> list[Unified3DDesign]:
    """Build all 9 Factorial Fractal designs + 10 Matched Controls (5 seven-tooth + 5 twelve-tooth)."""
    f0 = make_factorial_design("Cantor_000_Baseline_Flat", "F0_000", "factorial_000", False, False, False, False, True)
    f1r_sub = make_factorial_design("Cantor_100a_SubTeethOnly", "F1r_Sub", "factorial_100_sub", False, True, False, False, True)
    f1r = make_factorial_design("Cantor_100_RadialOnly", "F1r_100", "factorial_100", True, True, False, False, True)
    f1t = make_factorial_design("Cantor_010_ThetaOnly", "F1t_010", "factorial_010", False, False, True, False, True)
    f1z = make_factorial_design("Cantor_001_ZStepOnly", "F1z_001", "factorial_001", False, False, False, True, True)
    f2rt = make_factorial_design("Cantor_110_RadialTheta_Planar1Mask", "F2rt_110", "factorial_110", True, True, True, False, True)
    f2rz = make_factorial_design("Cantor_101_RadialZ", "F2rz_101", "factorial_101", True, True, False, True, True)
    f2tz = make_factorial_design("Cantor_011_ThetaZ", "F2tz_011", "factorial_011", False, False, True, True, True)
    f3 = make_factorial_design("Cantor_111_Unified3DFractal", "F3_111", "factorial_111", True, True, True, True, True)
    controls = build_matched_controls_for_most_fractal(f3)
    return [f0, f1r_sub, f1r, f1t, f1z, f2rt, f2rz, f2tz, f3, *controls]


def build_unified_sector_mesh(
    design: Unified3DDesign,
    theta_deg: float = DEFAULT_DISENGAGED_THETA_DEG,
    n_r_slot: int = 2,
    n_r_tooth: int = 2,
    n_phi_tooth: int = 3,
    n_phi_bridge: int = 3,
    n_z: int = 2,
) -> tuple[ClutchSurfaceMesh, np.ndarray]:
    """Construct C4 sector BEM surface mesh and per-panel slot index array."""
    rotor: list[Any] = []
    stator: list[Any] = []
    panel_slot_ids: list[int] = []

    def emit_rotor(kind: str, r0: float, r1: float, p0: float, p1: float, z0: float, z1: float, sign: int, slot_idx: int) -> None:
        panel = repository_face(kind, r0, r1, math.degrees(p0), math.degrees(p1), z0, z1, sign, "rotor")
        rotor.append(panel)
        panel_slot_ids.append(slot_idx)

    def emit_stator(kind: str, r0: float, r1: float, p0: float, p1: float, z0: float, z1: float, sign: int) -> None:
        panel = repository_face(kind, r0, r1, math.degrees(p0), math.degrees(p1), z0, z1, sign, "stator")
        stator.append(panel)

    for slot_idx, slot in enumerate(design.slots):
        for st in slot.sub_teeth:
            re = subdivisions(st.r_tooth_in, st.r_tooth_out, n_r_tooth)
            ze = subdivisions(st.z_tip, st.z_tip + st.h_teeth, n_z)
            for d_phi_deg, arc_deg in st.phi_offsets_deg:
                for low_deg, high_deg, cap_low, cap_high in tooth_segments(theta_deg + d_phi_deg, arc_deg):
                    low_phi, high_phi = math.radians(low_deg), math.radians(high_deg)
                    pe = subdivisions(low_phi, high_phi, n_phi_tooth)
                    for i in range(n_r_tooth):
                        for j in range(n_phi_tooth):
                            emit_rotor("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[0], ze[0], -1, slot_idx)
                            emit_rotor("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[-1], ze[-1], 1, slot_idx)
                    for j in range(n_phi_tooth):
                        for k in range(n_z):
                            emit_rotor("radial", re[0], re[0], pe[j], pe[j + 1], ze[k], ze[k + 1], -1, slot_idx)
                            emit_rotor("radial", re[-1], re[-1], pe[j], pe[j + 1], ze[k], ze[k + 1], 1, slot_idx)
                    for i in range(n_r_tooth):
                        for k in range(n_z):
                            if cap_low:
                                emit_rotor("azimuthal", re[i], re[i + 1], pe[0], pe[0], ze[k], ze[k + 1], -1, slot_idx)
                            if cap_high:
                                emit_rotor("azimuthal", re[i], re[i + 1], pe[-1], pe[-1], ze[k], ze[k + 1], 1, slot_idx)

    # Construct explicit (low, high, is_solid_stator_rib) radial intervals:
    # Each sub-slot (sub_in, sub_out) in slot.stator_subslots is an OPEN stator trench (is_solid_stator_rib=False)
    # that houses a rotor sub-tooth, while the intervals between open sub-slots (both primary inter-slot ribs
    # and internal middle-third Cantor stator sub-ribs) are SOLID stator ribs (is_solid_stator_rib=True).
    radial_intervals: list[tuple[float, float, bool]] = []
    cursor_r = design.R_min
    for slot in design.slots:
        subslots = slot.stator_subslots or ((slot.r_inner, slot.r_outer),)
        for sub_in, sub_out in subslots:
            if sub_in > cursor_r + 1e-12:
                radial_intervals.append((cursor_r, sub_in, True))
            radial_intervals.append((sub_in, sub_out, False))
            cursor_r = sub_out
    if design.R_max > cursor_r + 1e-12:
        radial_intervals.append((cursor_r, design.R_max, True))

    radial_edges: list[float] = [design.R_min]
    cell_is_solid_rib: list[bool] = []
    for low, high, is_rib in radial_intervals:
        radial_edges.extend(subdivisions(low, high, n_r_slot)[1:].tolist())
        cell_is_solid_rib.extend([is_rib] * n_r_slot)

    angles = np.deg2rad(
        np.concatenate(
            (
                np.linspace(0.0, design.aperture_arc_deg, n_phi_tooth + 1),
                np.linspace(design.aperture_arc_deg, 90.0, n_phi_bridge + 1)[1:],
            )
        )
    )
    heights = np.unique(
        np.concatenate(
            (
                np.linspace(design.z_pad_top - design.t_landing_pad, design.z_pad_top, n_z + 1),
                np.linspace(-design.t_membrane, 0.0, n_z + 1),
            )
        )
    )
    ni, nj, nk = len(cell_is_solid_rib), len(angles) - 1, len(heights) - 1

    def filled(i: int, j: int, k: int) -> bool:
        if i < 0 or i >= ni or k < 0 or k >= nk:
            return False
        j %= nj
        midpoint = (heights[k] + heights[k + 1]) / 2.0
        # Open aperture (j < n_phi_tooth): only solid stator ribs (cell_is_solid_rib[i] is True) in [-t_membrane, 0] are solid.
        if j < n_phi_tooth:
            return cell_is_solid_rib[i] and -design.t_membrane < midpoint < 0.0
        # Engaged landing-pad sector (j >= n_phi_tooth): the continuous recessed landing pad spans all radial intervals
        # across [z_pad_top - t_landing_pad, z_pad_top] while keeping the slot space above z_pad_top open.
        return design.z_pad_top - design.t_landing_pad < midpoint < design.z_pad_top

    for i in range(ni):
        for j in range(nj):
            for k in range(nk):
                if not filled(i, j, k):
                    continue
                r0, r1 = radial_edges[i], radial_edges[i + 1]
                p0, p1 = angles[j], angles[j + 1]
                z0, z1 = heights[k], heights[k + 1]
                if not filled(i, j, k - 1):
                    emit_stator("horizontal", r0, r1, p0, p1, z0, z0, -1)
                if not filled(i, j, k + 1):
                    emit_stator("horizontal", r0, r1, p0, p1, z1, z1, 1)
                if not filled(i - 1, j, k):
                    emit_stator("radial", r0, r0, p0, p1, z0, z1, -1)
                if not filled(i + 1, j, k):
                    emit_stator("radial", r1, r1, p0, p1, z0, z1, 1)
                if not filled(i, j - 1, k):
                    emit_stator("azimuthal", r0, r1, p0, p0, z0, z1, -1)
                if not filled(i, j + 1, k):
                    emit_stator("azimuthal", r0, r1, p1, p1, z0, z1, 1)

    base_tracks = [
        TrackSpec3D(
            s.r_inner,
            s.r_outer,
            s.sub_teeth[0].r_tooth_in,
            s.sub_teeth[-1].r_tooth_out,
            s.sub_teeth[0].z_tip,
            s.sub_teeth[0].h_teeth,
            s.level,
        )
        for s in design.slots
    ]
    elements = tuple(make_track_element(t) for t in base_tracks)
    geometry = Geometry(
        R_min=design.R_min,
        R_max=design.R_max,
        t_membrane=design.t_membrane,
        t_landing_pad=design.t_landing_pad,
        z_tip=DEFAULT_Z_TIP_ROTATIONAL_UM,
        h_teeth=DEFAULT_H_TEETH_ROTATIONAL_UM,
        theta_deg=theta_deg,
        tooth_arc_deg=DEFAULT_N3_TOOTH_ARC_DEG,
        aperture_arc_deg=design.aperture_arc_deg,
        elements=elements,
    )
    parameters = {
        "material": "Gold",
        "R_min": design.R_min,
        "R_max": design.R_max,
        "z_tip": DEFAULT_Z_TIP_ROTATIONAL_UM,
        "h_teeth": DEFAULT_H_TEETH_ROTATIONAL_UM,
        "t_membrane": geometry.t_membrane,
        "t_landing_pad": geometry.t_landing_pad,
        "theta_deg": theta_deg,
        "tooth_arc_deg": DEFAULT_N3_TOOTH_ARC_DEG,
        "aperture_arc_deg": geometry.aperture_arc_deg,
        "elements": [dataclasses.asdict(e) for e in elements],
    }
    mesh = ClutchSurfaceMesh(
        rotor=tuple(rotor),
        stator=tuple(stator),
        geometry=geometry,
        parameters=parameters,
        config=dict(parameters),
        panel_resolution={"n_r": n_r_slot, "n_phi_tooth": n_phi_tooth, "n_phi_bridge": n_phi_bridge, "n_z": n_z},
    )
    return mesh, np.asarray(panel_slot_ids, dtype=int)


def compute_log_periodic_modulation(kappas: np.ndarray, f_kappa: np.ndarray) -> dict[str, Any]:
    """Extract log-periodic modulation amplitude and phase at Cantor frequency omega = 2*pi / ln(3)."""
    mask = (
        np.isfinite(kappas)
        & np.isfinite(f_kappa)
        & (kappas >= SPECTRAL_FIT_KAPPA_MIN_UM_INV)
        & (kappas <= SPECTRAL_FIT_KAPPA_MAX_UM_INV)
        & (np.abs(f_kappa) > 1e-9)
    )
    if int(np.sum(mask)) < 5:
        return {"cantor_mod_amp_pct": 0.0, "cantor_phase_rad": 0.0, "residual": [0.0] * len(kappas)}
    x = np.log(kappas[mask])
    y = np.log(np.maximum(np.abs(kappas[mask] * f_kappa[mask]), 1e-12))
    poly = np.polyfit(x, y, deg=2)
    res_band = y - np.polyval(poly, x)
    basis = np.column_stack([np.cos(CANTOR_OMEGA_FUNDAMENTAL * x), np.sin(CANTOR_OMEGA_FUNDAMENTAL * x), np.ones_like(x)])
    coeffs, _, _, _ = np.linalg.lstsq(basis, res_band, rcond=None)
    amp = float(math.hypot(coeffs[0], coeffs[1]))
    phase = float(math.atan2(coeffs[1], coeffs[0]))
    full_res = np.zeros_like(kappas)
    full_res[mask] = res_band
    return {
        "cantor_mod_amp_pct": 100.0 * amp,
        "cantor_phase_rad": phase,
        "residual": [round(float(v), 5) for v in full_res],
    }


def evaluate_unified_3d_bem(
    design: Unified3DDesign,
    theta_deg: float = DEFAULT_DISENGAGED_THETA_DEG,
    n_xi: int = DEFAULT_BEM_QUADRATURE_ORDER,
    num_threads: int = 8,
) -> dict[str, Any]:
    """Evaluate a Unified3DDesign in 3D Vector-Dyadic BEM with per-slot and per-kappa decomposition."""
    torch.set_num_threads(max(1, int(num_threads)))
    t0 = time.perf_counter()
    mesh, panel_slot_ids = build_unified_sector_mesh(design, theta_deg=theta_deg)
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    material = MaterialModel.from_parameters(mesh.parameters)
    dof_slot_ids = np.repeat(panel_slot_ids, 2)

    char_gap_um = math.inf
    for sector in range(DEFAULT_NUM_SECTORS):
        sp = stator.centroids @ _rotation(sector).T
        for c in rotor.centroids:
            char_gap_um = min(char_gap_um, float(np.min(np.linalg.norm(sp - c, axis=1))))
    k_eff = 1.0 / max(char_gap_um, DEFAULT_MIN_TOOTH_W_UM)
    kappa_0 = 1.0 / DEFAULT_H_TEETH_ROTATIONAL_UM
    kappas, weights, _ = _quadrature(n_xi, kappa_0)
    K = len(kappas)
    phases = np.exp(2j * math.pi * np.arange(DEFAULT_NUM_SECTORS)[:, None] * np.arange(DEFAULT_NUM_SECTORS)[None, :] / float(DEFAULT_NUM_SECTORS))

    def same_modes_torch(body: Any) -> np.ndarray:
        N = body.count
        sub_var = torch.from_numpy((body.areas[:, None] + body.areas[None, :]) / (32.0 * math.pi))
        area_scale = torch.from_numpy(np.sqrt(body.areas[:, None]) * np.sqrt(body.areas[None, :]) / (4.0 * math.pi))
        kap_t = torch.from_numpy(kappas)
        sec_blocks = np.zeros((DEFAULT_NUM_SECTORS, K, 2 * N, 2 * N), dtype=np.float64)
        for sec in range(DEFAULT_NUM_SECTORS):
            rot = _rotation(sec)
            src_pts = body.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, body.tangents)
            t_dot_t = torch.from_numpy(np.einsum("ima,jna->ijmn", body.tangents, src_tan))
            ker_sum = torch.zeros((K, N, N), dtype=torch.float64)
            for qt in range(4):
                for qs in range(4):
                    w = float(body.quad_weights[qt] * body.quad_weights[qs])
                    delta = torch.from_numpy(body.quad_points[:, qt, None, :] - src_pts[None, :, qs, :])
                    eff_d = torch.sqrt(torch.sum(delta**2, dim=2) + sub_var)
                    scale = (area_scale * w) / eff_d
                    ker_sum += torch.exp(-kap_t[:, None, None] * eff_d[None, :, :]) * scale[None, :, :]
            single = ker_sum[:, :, :, None, None] * t_dot_t[None, :, :, :, :]
            if sec == 0:
                idx = np.arange(N)
                for q, kap in enumerate(kappas):
                    diag = torch.from_numpy(_disk_self_term(body.areas, float(kap)))
                    single[q, idx, idx] = diag[:, None, None] * torch.eye(2, dtype=torch.float64)
            sec_blocks[sec] = single.permute(0, 1, 3, 2, 4).reshape(K, 2 * N, 2 * N).numpy()
        return np.einsum("ms,skij->kmij", phases, sec_blocks)

    def cross_modes_torch(target: Any, source: Any) -> tuple[np.ndarray, np.ndarray]:
        Nt, Ns = target.count, source.count
        M = Nt * Ns
        sub_var = torch.from_numpy((target.areas[:, None] + source.areas[None, :]) / (32.0 * math.pi))
        area_scale = torch.from_numpy(np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :]) / (4.0 * math.pi))
        qw = torch.from_numpy(target.quad_weights[:, None] * source.quad_weights[None, :]).reshape(16)
        rs_sec = np.zeros((DEFAULT_NUM_SECTORS, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        dz_sec = np.zeros((DEFAULT_NUM_SECTORS, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        u_z = torch.from_numpy(target.tangents[:, :, 2][:, None, :, None])
        tgt_q = torch.from_numpy(target.quad_points.transpose(1, 0, 2)[:, :, None, :])
        for sec in range(DEFAULT_NUM_SECTORS):
            rot = _rotation(sec)
            src_pts = source.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, source.tangents)
            t_dot_t = torch.from_numpy(np.einsum("ima,jna->ijmn", target.tangents, src_tan))
            v_z = torch.from_numpy(src_tan[:, :, 2][None, :, None, :])
            src_q = torch.from_numpy(src_pts.transpose(1, 0, 2)[None, :, :, :])
            delta = (tgt_q[:, None, :, :, :] - src_q[:, :, None, :, :]).reshape(16, Nt, Ns, 3)
            eff_d = torch.sqrt(torch.sum(delta**2, dim=3) + sub_var[None, :, :])
            inv_d = 1.0 / eff_d
            scale = (area_scale[None, :, :] * qw[:, None, None]) * inv_d
            dz_over_d = delta[:, :, :, 2] * inv_d
            u_R = torch.einsum("ima,qija->qijm", torch.from_numpy(target.tangents), delta)
            v_R = torch.einsum("jna,qija->qijn", torch.from_numpy(src_tan), delta)
            R_inv2 = (inv_d**2)[:, :, :, None, None]
            Z = delta[:, :, :, 2][:, :, :, None, None]
            D = u_R[:, :, :, :, None] * v_R[:, :, :, None, :] * R_inv2
            dD_dz = (
                (u_z[None] * v_R[:, :, :, None, :] + u_R[:, :, :, :, None] * v_z[None]) * R_inv2
                - 2.0 * Z * D * R_inv2
            )
            D_c = D.reshape(16, M, 4).permute(1, 2, 0).reshape(M, 4, 16)
            dD_c = dD_dz.reshape(16, M, 4).permute(1, 2, 0).reshape(M, 4, 16)
            eff_d_f = eff_d.reshape(16, M)
            inv_d_f = inv_d.reshape(16, M)
            scale_f = scale.reshape(16, M)
            dz_d_f = dz_over_d.reshape(16, M)
            for qk, kap_val in enumerate(kappas):
                kap = float(kap_val)
                x = kap * eff_d_f
                ker = torch.exp(-x) * scale_f
                rad_deriv = -ker * (kap + inv_d_f)
                sc_dz = rad_deriv * dz_d_f
                inv = 1.0 / (1.0 + x)
                denom = 1.0 - inv + inv**2
                c_dir = (1.0 + inv + inv**2) / denom
                dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denom**2
                s_t = (0.5 * torch.sum(ker, dim=0)).reshape(Nt, Ns, 1, 1)
                dz_t = (0.5 * torch.sum(sc_dz, dim=0)).reshape(Nt, Ns, 1, 1)
                w_D = (-0.25 * ker * c_dir).T.reshape(M, 1, 16)
                w_dz_D = (-0.25 * sc_dz * c_dir - 0.25 * ker * dc_dir_dx * kap * dz_d_f).T.reshape(M, 1, 16)
                s_D = torch.sum(D_c * w_D, dim=2).reshape(Nt, Ns, 2, 2)
                dz_D = (torch.sum(D_c * w_dz_D, dim=2) + torch.sum(dD_c * w_D, dim=2)).reshape(Nt, Ns, 2, 2)
                single = s_t * t_dot_t + s_D
                dz = dz_t * t_dot_t + dz_D
                rs_sec[sec, qk] = single.permute(0, 2, 1, 3).reshape(2 * Nt, 2 * Ns).numpy()
                dz_sec[sec, qk] = dz.permute(0, 2, 1, 3).reshape(2 * Nt, 2 * Ns).numpy()
        return np.einsum("ms,skij->kmij", phases, rs_sec), np.einsum("ms,skij->kmij", phases, dz_sec)

    rr_modes = same_modes_torch(rotor)
    ss_modes = same_modes_torch(stator)
    rs_modes, dz_modes = cross_modes_torch(rotor, stator)

    dof_forces = np.zeros(2 * rotor.count, dtype=np.float64)
    f_kappa = np.zeros(K, dtype=np.float64)
    f_kappa_by_gen = {1: np.zeros(K, dtype=np.float64), 2: np.zeros(K, dtype=np.float64), 3: np.zeros(K, dtype=np.float64)}
    slot_levels = [s.level for s in design.slots]

    for q in range(K):
        kap = float(kappas[q])
        w_q = float(weights[q])
        tm, te, _ = material.channel_weights(kap, k_eff=k_eff)
        q_dof = np.zeros(2 * rotor.count, dtype=np.float64)
        for mode, mult in ((0, 1.0), (2, 1.0), (1, 2.0)):
            if mode in (0, 2):
                mr = torch.from_numpy(rr_modes[q, mode].real.copy())
                ms = torch.from_numpy(ss_modes[q, mode].real.copy())
                g = torch.from_numpy(rs_modes[q, mode].real.copy())
                dg = torch.from_numpy(dz_modes[q, mode].real.copy())
                sr, dsr = g.T.contiguous(), dg.T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.float64)
            else:
                mr = torch.from_numpy(rr_modes[q, mode].copy())
                ms = torch.from_numpy(ss_modes[q, mode].copy())
                g = torch.from_numpy(rs_modes[q, mode].copy())
                dg = torch.from_numpy(dz_modes[q, mode].copy())
                sr, dsr = g.conj().T.contiguous(), dg.conj().T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.complex128)
            lu_r, piv_r = torch.linalg.lu_factor(mr)
            lu_s, piv_s = torch.linalg.lu_factor(ms)
            x = torch.linalg.lu_solve(lu_r, piv_r, g)
            ns_col = sr.shape[1]
            z_all = torch.linalg.lu_solve(lu_s, piv_s, torch.cat((sr, dsr), dim=1))
            z, dz = z_all[:, :ns_col], z_all[:, ns_col:]
            coupling = x @ z
            B, C = dg @ z, x @ dz
            for ch_w in (tm, te):
                pw = ch_w**2
                y = eye - pw * coupling
                lu_y, piv_y = torch.linalg.lu_factor(y)
                U = torch.linalg.lu_solve(lu_y, piv_y, C)
                V = torch.linalg.lu_solve(lu_r, piv_r, torch.linalg.lu_solve(lu_y, piv_y, B, left=False), left=False)
                per_dof = -pw * (torch.diagonal(V).real + torch.diagonal(U).real).numpy()
                q_dof += mult * (-per_dof / (2.0 * math.pi))
        f_kappa[q] = float(np.sum(q_dof) * MEEP_FORCE_TO_SI * 1e12)
        for s_idx, gen_lvl in enumerate(slot_levels):
            f_kappa_by_gen[gen_lvl][q] += float(np.sum(q_dof[dof_slot_ids == s_idx]) * MEEP_FORCE_TO_SI * 1e12)
        dof_forces += w_q * q_dof

    f_slots = [float(np.sum(dof_forces[dof_slot_ids == k]) * MEEP_FORCE_TO_SI * 1e12) for k in range(len(design.slots))]
    r_centers = [0.5 * (s.r_inner + s.r_outer) for s in design.slots]
    f_circ = [float(fk / (2.0 * math.pi * rk)) for fk, rk in zip(f_slots, r_centers)]
    f_total = float(sum(f_slots))
    a_tot = active_area_unified(design)
    spec_info = compute_log_periodic_modulation(kappas, f_kappa)

    return {
        "name": design.name,
        "code": design.code,
        "u_r": design.u_r,
        "u_theta": design.u_theta,
        "u_z": design.u_z,
        "family_role": design.family_role,
        "F_z_pN": f_total,
        "F_circ_sum_pN_per_um": float(sum(f_circ)),
        "A_tooth_um2": a_tot,
        "F_per_A_pN_per_um2": f_total / max(a_tot, 1e-12),
        "f_slots_pN": f_slots,
        "r_centers_um": r_centers,
        "n_rotor_panels_sector": int(rotor.count),
        "n_stator_panels_sector": int(stator.count),
        "kappas_um_inv": [round(float(k), 5) for k in kappas],
        "f_kappa_pN_um": [round(float(v), 5) for v in f_kappa],
        "f_kappa_gen1_pN_um": [round(float(v), 5) for v in f_kappa_by_gen[1]],
        "f_kappa_gen2_pN_um": [round(float(v), 5) for v in f_kappa_by_gen[2]],
        "f_kappa_gen3_pN_um": [round(float(v), 5) for v in f_kappa_by_gen[3]],
        "cantor_mod_amp_pct": spec_info["cantor_mod_amp_pct"],
        "cantor_phase_rad": spec_info["cantor_phase_rad"],
        "log_periodic_residual": spec_info["residual"],
        "elapsed_s": float(time.perf_counter() - t0),
    }


def compute_factorial_effects(by_code: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Compute exact 2^3 factorial main effects, 2-way interactions, and 3-way synergy."""
    required = ("F0_000", "F1r_100", "F1t_010", "F1z_001", "F2rt_110", "F2rz_101", "F2tz_011", "F3_111")
    if not all(k in by_code for k in required):
        return {}
    f000 = float(by_code["F0_000"]["F_z_pN"])
    f100 = float(by_code["F1r_100"]["F_z_pN"])
    f010 = float(by_code["F1t_010"]["F_z_pN"])
    f001 = float(by_code["F1z_001"]["F_z_pN"])
    f110 = float(by_code["F2rt_110"]["F_z_pN"])
    f101 = float(by_code["F2rz_101"]["F_z_pN"])
    f011 = float(by_code["F2tz_011"]["F_z_pN"])
    f111 = float(by_code["F3_111"]["F_z_pN"])

    return {
        "single_effect_r_pN": f100 - f000,
        "single_effect_theta_pN": f010 - f000,
        "single_effect_z_pN": f001 - f000,
        "main_effect_r_pN": 0.25 * ((f100 - f000) + (f110 - f010) + (f101 - f001) + (f111 - f011)),
        "main_effect_theta_pN": 0.25 * ((f010 - f000) + (f110 - f100) + (f011 - f001) + (f111 - f101)),
        "main_effect_z_pN": 0.25 * ((f001 - f000) + (f101 - f100) + (f011 - f010) + (f111 - f110)),
        "synergy_r_theta_pN": f110 - f100 - f010 + f000,
        "synergy_r_z_pN": f101 - f100 - f001 + f000,
        "synergy_theta_z_pN": f011 - f010 - f001 + f000,
        "synergy_3way_r_theta_z_pN": f111 - f110 - f101 - f011 + f100 + f010 + f001 - f000,
        "total_gain_111_over_000_pN": f111 - f000,
        "total_gain_111_over_000_pct": 100.0 * (f111 - f000) / math.copysign(max(abs(f000), 1e-12), f000),
    }
