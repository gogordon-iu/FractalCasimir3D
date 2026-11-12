#!/usr/bin/env python3
"""
Unified 3D Homothetic Cantor Switch (`H3-Cantor-Robust`) & Matched Controls Engine.
===================================================================================
Implements:
  1. Exact 3D homothetic (b = 3.0, g_min = 27 nm) prefractal rotary-axial Casimir
     architecture (`H3-Cantor-Robust`) across R in [3.50, 6.20] um with C4 cyclic
     symmetry, Cantor-Vernier azimuthal lobe staggering, stepped landing-pad
     engagement sectors, and homothetic stator micro-bridges.
  2. Five strictly iso-area and g_min-matched non-fractal controls:
       - `Ctrl_KnifeEdge_g27` (19-track uniform g_r = 27 nm single-stage point optimizer)
       - `Ctrl_Uni_7Trk`      (7-track uniform single-stage grating at z_stage = -120 nm)
       - `Ctrl_Lin_3Stage`    (7-track arithmetic/linear 3-stage grating)
       - `Ctrl_Mono_3Stage`   (7-track monotonic radial ordering with synchronized phase)
       - `Ctrl_Shuf_OutPhase` (7-track cross-dimensionally decoupled / out-of-phase control)
  3. Watertight, collision-verified 3D C4-sector BEM mesh generation supporting axial
     stroke z_shift_um, azimuthal rotation theta_deg, cleanroom CD etch bias delta_w_um,
     radial displacement delta_r_um, EBL corner rounding r_edge_um, and dispersive
     300 K Gold vs. 0 K PEC materials.
  4. Fast PyTorch-vectorized 3D Vector-Dyadic BEM force, free-energy, wavenumber
     sub-band, and Laplace mutual-capacitance solver.
  5. `pint`-verified 32-element Hermite cubic Euler-Bernoulli clamped-clamped curved-arc
     beam FEM solver for suspended stator-rib elastostatic safety (`SF_rib`).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from scipy import linalg
from scipy.constants import Boltzmann as K_BOLTZMANN_SI_J_PER_K
from scipy.constants import epsilon_0 as EPSILON_0_F_PER_M
import torch

try:
    import pint as _pint_mod

    _UREG: Any = _pint_mod.UnitRegistry()
except ImportError:  # pragma: no cover - cluster offline fallback when pint is absent
    _UREG = None

from execution.casimir_bem_solver import (
    BOLTZMANN_K_EV_PER_K,
    ClutchSurfaceMesh,
    Geometry,
    HBAR_C_EV_UM,
    MEEP_FORCE_TO_SI,
    MaterialModel,
    _disk_self_term,
    _quadrature,
    _rotation,
    _yukawa_blocks,
)
from execution.clutch_geometry_redesign import (
    DEFAULT_NUM_SECTORS,
    DEFAULT_SECTOR_DEG,
    DEFAULT_T_MEMBRANE_UM,
    DEFAULT_TOOTH_CENTER_OFFSET_DEG,
    H3_ROBUST_APERTURE_ARC_DEG,
    H3_ROBUST_BASE_B,
    H3_ROBUST_BRIDGE_ARC_WIDTH_BY_GEN_DEG,
    H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM,
    H3_ROBUST_CANTOR_GENERATIONS,
    H3_ROBUST_CANTOR_RIB_WIDTHS_NM,
    H3_ROBUST_ENGAGED_PAD_GAP_UM,
    H3_ROBUST_G_MIN_UM,
    H3_ROBUST_GOLD_YOUNGS_MODULUS_PA,
    H3_ROBUST_HEIGHT_TO_STAGE_RATIO,
    H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG,
    H3_ROBUST_KNIFE_EDGE_TRACK_COUNT,
    H3_ROBUST_LOBE_CHORD_FINE_UM,
    H3_ROBUST_LOBES_BY_GEN,
    H3_ROBUST_MIN_SURVIVING_FEATURE_UM,
    H3_ROBUST_MIN_UNSHORTED_GAP_UM,
    H3_ROBUST_NOMINAL_OP_Z_UM,
    H3_ROBUST_PAD_THICKNESS_UM,
    H3_ROBUST_R_MAX_UM,
    H3_ROBUST_R_MIN_UM,
    H3_ROBUST_SLOT_FINE_UM,
    H3_ROBUST_VERNIER_PHASE_DEG,
    H3_ROBUST_W_RATIO,
    H3_ROBUST_Z_STAGE_FINE_UM,
    disengaged_angle_deg,
    engaged_angle_deg,
    tooth_center_angle_deg,
)
from execution.run_fractal_advantage_study import (
    TrackSpec3D,
    make_track_element,
    repository_face,
    subdivisions,
)

MEEP_ENERGY_TO_SI_J: float = MEEP_FORCE_TO_SI * 1.0e-6
KBT_300K_SI_J: float = K_BOLTZMANN_SI_J_PER_K * 300.0
CANTOR_LN_3: float = math.log(H3_ROBUST_BASE_B)
CANTOR_OMEGA_1: float = 2.0 * math.pi / CANTOR_LN_3
CANTOR_DF_1D: float = math.log(2.0) / CANTOR_LN_3
CANTOR_DF_2D: float = math.log(4.0) / CANTOR_LN_3

DISENGAGED_THETA_DEG: float = disengaged_angle_deg(H3_ROBUST_APERTURE_ARC_DEG)
ENGAGED_THETA_DEG: float = engaged_angle_deg(H3_ROBUST_APERTURE_ARC_DEG)


@dataclass(frozen=True)
class MicroBridge3D:
    """Azimuthal stator micro-bridge tying opposite slot walls across an open slot."""

    phi_center_deg: float
    phi_width_deg: float
    z_bot_um: float
    z_top_um: float


@dataclass(frozen=True)
class HomotheticTrack3D:
    """Single radial slot/tooth track in the 3D rotary-axial Casimir architecture."""

    track_index: int
    generation: int
    r_slot_in_um: float
    r_slot_out_um: float
    r_tooth_in_um: float
    r_tooth_out_um: float
    collar_width_um: float
    z_stage_center_um: float
    h_stage_um: float
    z_pad_top_um: float
    lobe_offsets_deg: tuple[tuple[float, float], ...]
    vernier_phase_deg: float
    micro_bridges: tuple[MicroBridge3D, ...] = ()

    @property
    def slot_width_um(self) -> float:
        return self.r_slot_out_um - self.r_slot_in_um

    @property
    def tooth_width_um(self) -> float:
        return self.r_tooth_out_um - self.r_tooth_in_um

    @property
    def radial_center_um(self) -> float:
        return 0.5 * (self.r_slot_in_um + self.r_slot_out_um)

    @property
    def radial_gap_um(self) -> float:
        return min(
            self.r_tooth_in_um - self.r_slot_in_um,
            self.r_slot_out_um - self.r_tooth_out_um,
        )


@dataclass(frozen=True)
class StatorRibSpan3D:
    """Inter-slot stator rib structural ring segment within one C4 sector."""

    rib_index: int
    r_in_um: float
    r_out_um: float
    z_bot_um: float
    z_top_um: float
    unsupported_arc_deg: float
    left_track_index: int | None
    right_track_index: int | None

    @property
    def width_um(self) -> float:
        return self.r_out_um - self.r_in_um

    @property
    def radial_center_um(self) -> float:
        return 0.5 * (self.r_in_um + self.r_out_um)

    @property
    def height_um(self) -> float:
        return self.z_top_um - self.z_bot_um


@dataclass(frozen=True)
class RobustClutchDesign3D:
    """Complete 3D rotary-axial clutch architecture specification."""

    name: str
    code: str
    family_role: str
    description: str
    R_min_um: float
    R_max_um: float
    aperture_arc_deg: float
    pad_thickness_um: float
    nominal_op_z_um: float
    is_fractal: bool
    has_micro_bridges: bool
    tracks: tuple[HomotheticTrack3D, ...]
    ribs: tuple[StatorRibSpan3D, ...]
    bem_n_r_lobe: int = 1
    bem_n_phi_lobe: int = 1
    bem_n_z_lobe: int = 1
    bem_n_phi_collar: int = 3


def active_tooth_area_um2(design: RobustClutchDesign3D) -> float:
    """Exact horizontal active rotor tooth top/bottom footprint area across all 4 C4 sectors."""
    total = 0.0
    for trk in design.tracks:
        r_diff2 = trk.r_tooth_out_um**2 - trk.r_tooth_in_um**2
        for _, arc_deg in trk.lobe_offsets_deg:
            total += float(DEFAULT_NUM_SECTORS) * 0.5 * r_diff2 * math.radians(arc_deg)
    return float(total)


def compute_design_geometric_summary(design: RobustClutchDesign3D) -> dict[str, float]:
    """Compute exact 3D Euclidean & clearance descriptors across all 4 C4 sectors."""
    n_sec = float(DEFAULT_NUM_SECTORS)
    a_tooth = 0.0
    p_edge = 0.0
    a_sw_r = 0.0
    a_sw_t = 0.0
    vol = 0.0
    sw_over_gap = 0.0
    g_min_um = math.inf
    total_lobes_sector = 0

    for trk in design.tracks:
        w_t = trk.tooth_width_um
        h_t = trk.h_stage_um
        g_in = trk.r_tooth_in_um - trk.r_slot_in_um
        g_out = trk.r_slot_out_um - trk.r_tooth_out_um
        g_min_um = min(g_min_um, g_in, g_out)
        total_lobes_sector += len(trk.lobe_offsets_deg)
        for _, arc_deg in trk.lobe_offsets_deg:
            rad = math.radians(arc_deg)
            a_lobe = n_sec * 0.5 * (trk.r_tooth_out_um**2 - trk.r_tooth_in_um**2) * rad
            a_tooth += a_lobe
            p_edge += n_sec * (rad * (trk.r_tooth_in_um + trk.r_tooth_out_um) + 2.0 * w_t)
            sw_in = n_sec * rad * trk.r_tooth_in_um * h_t
            sw_out = n_sec * rad * trk.r_tooth_out_um * h_t
            a_sw_r += sw_in + sw_out
            a_sw_t += n_sec * 2.0 * w_t * h_t
            vol += a_lobe * h_t
            sw_over_gap += (sw_in / max(g_in, 1e-9)) + (sw_out / max(g_out, 1e-9))

    return {
        "A_tooth_um2": float(a_tooth),
        "P_edge_um": float(p_edge),
        "A_sidewall_r_um2": float(a_sw_r),
        "A_sidewall_theta_um2": float(a_sw_t),
        "A_sidewall_um2": float(a_sw_r + a_sw_t),
        "V_tooth_um3": float(vol),
        "sidewall_over_gap_um": float(sw_over_gap),
        "g_r_min_nm": float(1000.0 * g_min_um),
        "n_tracks": float(len(design.tracks)),
        "n_lobes_per_sector": float(total_lobes_sector),
        "total_open_slot_width_um": float(sum(t.slot_width_um for t in design.tracks)),
        "total_rib_metal_width_um": float(sum(r.width_um for r in design.ribs)),
        "max_unsupported_rib_arc_deg": float(max(r.unsupported_arc_deg for r in design.ribs)),
    }


def _homothetic_scale_for_gen(gen: int) -> float:
    """Scale factor 3^(3 - gen) relative to the fine generation m=3 (1, 3, 9 for m=3, 2, 1)."""
    if gen not in (1, 2, 3):
        raise ValueError(f"Generation must be in {{1, 2, 3}}, got {gen}")
    return float(H3_ROBUST_BASE_B ** (3 - gen))


def _build_lobe_train_and_bridges(
    *,
    r_center_um: float,
    n_lobes: int,
    lobe_chord_um: float,
    inter_lobe_gap_deg: float,
    vernier_phase_deg: float,
    z_stage_center_um: float,
    h_stage_um: float,
    bridge_arc_width_deg: float,
    bridge_thickness_um: float,
    enable_bridges: bool,
    nominal_theta_deg: float = DISENGAGED_THETA_DEG,
) -> tuple[tuple[tuple[float, float], ...], tuple[MicroBridge3D, ...]]:
    """Construct azimuthal rotor lobe offsets and inter-lobe stator micro-bridges."""
    if n_lobes < 1:
        raise ValueError("n_lobes must be >= 1")
    lobe_arc_deg = math.degrees(lobe_chord_um / r_center_um)
    pitch_deg = lobe_arc_deg + inter_lobe_gap_deg
    total_span_deg = n_lobes * lobe_arc_deg + (n_lobes - 1) * inter_lobe_gap_deg
    start_offset_deg = vernier_phase_deg - 0.5 * total_span_deg + 0.5 * lobe_arc_deg

    lobes: list[tuple[float, float]] = []
    for idx in range(n_lobes):
        d_phi = start_offset_deg + idx * pitch_deg
        lobes.append((float(d_phi), float(lobe_arc_deg)))

    bridges: list[MicroBridge3D] = []
    if enable_bridges and n_lobes >= 2:
        ref_center_deg = tooth_center_angle_deg(nominal_theta_deg)
        z_stage_bot = z_stage_center_um - 0.5 * h_stage_um
        z_stage_top = z_stage_center_um + 0.5 * h_stage_um
        # Place bridge at upper stage rim for shallow stage (m=3) and lower stage rim
        # for deeper stages (m=1, 2) so bridges are disjoint in z from rotor teeth at
        # nominal_op_z_um across all rotation angles theta in [0, 90) deg.
        if abs(z_stage_center_um) <= H3_ROBUST_NOMINAL_OP_Z_UM:
            z_b_top = z_stage_top
            z_b_bot = z_stage_top - bridge_thickness_um
        else:
            z_b_bot = z_stage_bot
            z_b_top = z_stage_bot + bridge_thickness_um

        for idx in range(n_lobes - 1):
            gap_center_rel = start_offset_deg + (idx + 0.5) * pitch_deg
            phi_bridge_center = ref_center_deg + gap_center_rel
            bridges.append(
                MicroBridge3D(
                    phi_center_deg=float(phi_bridge_center),
                    phi_width_deg=float(bridge_arc_width_deg),
                    z_bot_um=float(z_b_bot),
                    z_top_um=float(z_b_top),
                )
            )
    return tuple(lobes), tuple(bridges)


def _compute_unsupported_rib_arc_deg(
    aperture_arc_deg: float,
    left_track: HomotheticTrack3D | None,
    right_track: HomotheticTrack3D | None,
) -> float:
    """Compute exact maximum unsupported angular span along a stator rib in [0, aperture_arc_deg]."""
    clamped_intervals: list[tuple[float, float]] = [(0.0, 0.0), (aperture_arc_deg, aperture_arc_deg)]
    for trk in (left_track, right_track):
        if trk is None:
            continue
        for br in trk.micro_bridges:
            lo = max(0.0, br.phi_center_deg - 0.5 * br.phi_width_deg)
            hi = min(aperture_arc_deg, br.phi_center_deg + 0.5 * br.phi_width_deg)
            if hi > lo:
                clamped_intervals.append((lo, hi))
    clamped_intervals.sort(key=lambda iv: (iv[0], iv[1]))
    merged: list[list[float]] = []
    for lo, hi in clamped_intervals:
        if not merged or lo > merged[-1][1] + 1e-9:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    max_span = 0.0
    for a, b in zip(merged, merged[1:]):
        max_span = max(max_span, b[0] - a[1])
    return float(max_span)


def _assemble_ribs_for_tracks(
    tracks: Sequence[HomotheticTrack3D],
    R_min_um: float,
    R_max_um: float,
    aperture_arc_deg: float,
) -> tuple[StatorRibSpan3D, ...]:
    """Build exact inter-slot stator rib structural spans from ordered radial tracks."""
    ribs: list[StatorRibSpan3D] = []
    n_trk = len(tracks)
    for rib_idx in range(n_trk + 1):
        r_in = R_min_um if rib_idx == 0 else tracks[rib_idx - 1].r_slot_out_um
        r_out = R_max_um if rib_idx == n_trk else tracks[rib_idx].r_slot_in_um
        if r_out - r_in <= 1e-9:
            raise ValueError(f"Nonpositive stator rib width at rib_idx={rib_idx}: [{r_in}, {r_out}]")
        left_trk = tracks[rib_idx - 1] if rib_idx > 0 else None
        right_trk = tracks[rib_idx] if rib_idx < n_trk else None
        adj = [t for t in (left_trk, right_trk) if t is not None]
        z_bot = min(t.z_stage_center_um - 0.5 * t.h_stage_um for t in adj)
        z_top = max(t.z_stage_center_um + 0.5 * t.h_stage_um for t in adj)
        span_deg = _compute_unsupported_rib_arc_deg(aperture_arc_deg, left_trk, right_trk)
        ribs.append(
            StatorRibSpan3D(
                rib_index=rib_idx,
                r_in_um=float(r_in),
                r_out_um=float(r_out),
                z_bot_um=float(z_bot),
                z_top_um=float(z_top),
                unsupported_arc_deg=float(span_deg),
                left_track_index=left_trk.track_index if left_trk is not None else None,
                right_track_index=right_trk.track_index if right_trk is not None else None,
            )
        )
    return tuple(ribs)


def build_h3_cantor_robust_design() -> RobustClutchDesign3D:
    """Construct the canonical unified 3D homothetic Cantor switch (`H3-Cantor-Robust`)."""
    gens = H3_ROBUST_CANTOR_GENERATIONS
    rib_widths_um = [w_nm * 1.0e-3 for w_nm in H3_ROBUST_CANTOR_RIB_WIDTHS_NM]
    cursor_r = H3_ROBUST_R_MIN_UM + rib_widths_um[0]
    tracks: list[HomotheticTrack3D] = []

    for idx, gen in enumerate(gens):
        scale = _homothetic_scale_for_gen(gen)
        w_slot = H3_ROBUST_SLOT_FINE_UM * scale
        w_tooth = H3_ROBUST_W_RATIO * w_slot
        r_s_in = cursor_r
        r_s_out = cursor_r + w_slot
        r_c = 0.5 * (r_s_in + r_s_out)
        r_t_in = r_c - 0.5 * w_tooth
        r_t_out = r_c + 0.5 * w_tooth

        z_stage = H3_ROBUST_Z_STAGE_FINE_UM * scale
        h_stage = H3_ROBUST_HEIGHT_TO_STAGE_RATIO * abs(z_stage)
        z_pad_top = -H3_ROBUST_NOMINAL_OP_Z_UM - 0.5 * h_stage - H3_ROBUST_ENGAGED_PAD_GAP_UM
        collar_w = H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM[gen]

        lobes, bridges = _build_lobe_train_and_bridges(
            r_center_um=r_c,
            n_lobes=int(H3_ROBUST_LOBES_BY_GEN[gen]),
            lobe_chord_um=H3_ROBUST_LOBE_CHORD_FINE_UM * scale,
            inter_lobe_gap_deg=float(H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG[gen]),
            vernier_phase_deg=float(H3_ROBUST_VERNIER_PHASE_DEG[gen]),
            z_stage_center_um=z_stage,
            h_stage_um=h_stage,
            bridge_arc_width_deg=float(H3_ROBUST_BRIDGE_ARC_WIDTH_BY_GEN_DEG[gen]),
            bridge_thickness_um=float(H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM[gen]),
            enable_bridges=True,
        )
        tracks.append(
            HomotheticTrack3D(
                track_index=idx,
                generation=gen,
                r_slot_in_um=float(r_s_in),
                r_slot_out_um=float(r_s_out),
                r_tooth_in_um=float(r_t_in),
                r_tooth_out_um=float(r_t_out),
                collar_width_um=float(collar_w),
                z_stage_center_um=float(z_stage),
                h_stage_um=float(h_stage),
                z_pad_top_um=float(z_pad_top),
                lobe_offsets_deg=lobes,
                vernier_phase_deg=float(H3_ROBUST_VERNIER_PHASE_DEG[gen]),
                micro_bridges=bridges,
            )
        )
        cursor_r = r_s_out + rib_widths_um[idx + 1]

    if not math.isclose(cursor_r, H3_ROBUST_R_MAX_UM, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError(f"Radial budget mismatch: cursor_r={cursor_r} vs R_max={H3_ROBUST_R_MAX_UM}")

    ribs = _assemble_ribs_for_tracks(
        tracks, H3_ROBUST_R_MIN_UM, H3_ROBUST_R_MAX_UM, H3_ROBUST_APERTURE_ARC_DEG
    )
    return RobustClutchDesign3D(
        name="H3-Cantor-Robust",
        code="H3_Cantor_Robust",
        family_role="fractal_homothetic_robust",
        description=(
            "Unified 3D homothetic b=3.0, g_min=27 nm Cantor rotary-axial switch with "
            "Vernier lobe staggering, homothetic micro-bridges, and stepped landing pads."
        ),
        R_min_um=H3_ROBUST_R_MIN_UM,
        R_max_um=H3_ROBUST_R_MAX_UM,
        aperture_arc_deg=H3_ROBUST_APERTURE_ARC_DEG,
        pad_thickness_um=H3_ROBUST_PAD_THICKNESS_UM,
        nominal_op_z_um=H3_ROBUST_NOMINAL_OP_Z_UM,
        is_fractal=True,
        has_micro_bridges=True,
        tracks=tuple(tracks),
        ribs=ribs,
    )


def build_h3_cantor_sym_2x2x2_design() -> RobustClutchDesign3D:
    """Construct the slot-symmetric (`Delta_phi = 0 deg`), 2x2x2 mesh-refined Cantor switch (`H3-Cantor-Sym-2x2x2`)."""
    gens = H3_ROBUST_CANTOR_GENERATIONS
    rib_widths_um = [w_nm * 1.0e-3 for w_nm in H3_ROBUST_CANTOR_RIB_WIDTHS_NM]
    cursor_r = H3_ROBUST_R_MIN_UM + rib_widths_um[0]
    tracks: list[HomotheticTrack3D] = []

    for idx, gen in enumerate(gens):
        scale = _homothetic_scale_for_gen(gen)
        w_slot = H3_ROBUST_SLOT_FINE_UM * scale
        w_tooth = H3_ROBUST_W_RATIO * w_slot
        r_s_in = cursor_r
        r_s_out = cursor_r + w_slot
        r_c = 0.5 * (r_s_in + r_s_out)
        r_t_in = r_c - 0.5 * w_tooth
        r_t_out = r_c + 0.5 * w_tooth

        z_stage = H3_ROBUST_Z_STAGE_FINE_UM * scale
        h_stage = H3_ROBUST_HEIGHT_TO_STAGE_RATIO * abs(z_stage)
        z_pad_top = -H3_ROBUST_NOMINAL_OP_Z_UM - 0.5 * h_stage - H3_ROBUST_ENGAGED_PAD_GAP_UM
        collar_w = H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM[gen]

        lobes, bridges = _build_lobe_train_and_bridges(
            r_center_um=r_c,
            n_lobes=int(H3_ROBUST_LOBES_BY_GEN[gen]),
            lobe_chord_um=H3_ROBUST_LOBE_CHORD_FINE_UM * scale,
            inter_lobe_gap_deg=float(H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG[gen]),
            vernier_phase_deg=0.0,
            z_stage_center_um=z_stage,
            h_stage_um=h_stage,
            bridge_arc_width_deg=float(H3_ROBUST_BRIDGE_ARC_WIDTH_BY_GEN_DEG[gen]),
            bridge_thickness_um=float(H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM[gen]),
            enable_bridges=True,
        )
        tracks.append(
            HomotheticTrack3D(
                track_index=idx,
                generation=gen,
                r_slot_in_um=float(r_s_in),
                r_slot_out_um=float(r_s_out),
                r_tooth_in_um=float(r_t_in),
                r_tooth_out_um=float(r_t_out),
                collar_width_um=float(collar_w),
                z_stage_center_um=float(z_stage),
                h_stage_um=float(h_stage),
                z_pad_top_um=float(z_pad_top),
                lobe_offsets_deg=lobes,
                vernier_phase_deg=0.0,
                micro_bridges=bridges,
            )
        )
        cursor_r = r_s_out + rib_widths_um[idx + 1]

    if not math.isclose(cursor_r, H3_ROBUST_R_MAX_UM, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError(f"Radial budget mismatch: cursor_r={cursor_r} vs R_max={H3_ROBUST_R_MAX_UM}")

    ribs = _assemble_ribs_for_tracks(
        tracks, H3_ROBUST_R_MIN_UM, H3_ROBUST_R_MAX_UM, H3_ROBUST_APERTURE_ARC_DEG
    )
    return RobustClutchDesign3D(
        name="H3-Cantor-Sym-2x2x2",
        code="H3_Cantor_Sym_2x2x2",
        family_role="fractal_homothetic_symmetric_refined",
        description=(
            "Unified 3D homothetic b=3.0, g_min=27 nm Cantor rotary-axial switch with centered "
            "slot-symmetric phase (Delta_phi = 0 deg), homothetic micro-bridges, stepped landing "
            "pads, and refined 2x2x2 lobe BEM discretization."
        ),
        R_min_um=H3_ROBUST_R_MIN_UM,
        R_max_um=H3_ROBUST_R_MAX_UM,
        aperture_arc_deg=H3_ROBUST_APERTURE_ARC_DEG,
        pad_thickness_um=H3_ROBUST_PAD_THICKNESS_UM,
        nominal_op_z_um=H3_ROBUST_NOMINAL_OP_Z_UM,
        is_fractal=True,
        has_micro_bridges=True,
        tracks=tuple(tracks),
        ribs=ribs,
        bem_n_r_lobe=2,
        bem_n_phi_lobe=2,
        bem_n_z_lobe=2,
        bem_n_phi_collar=9,
    )


def _scale_design_lobe_arcs_to_target_area(
    design: RobustClutchDesign3D, target_area_um2: float
) -> RobustClutchDesign3D:
    """Scale all lobe arc widths by a single constant factor to match target_area_um2 to machine precision."""
    cur_area = active_tooth_area_um2(design)
    if cur_area <= 0.0:
        raise ValueError(f"Cannot area-normalize design {design.code} with nonpositive area {cur_area}")
    factor = target_area_um2 / cur_area
    scaled_tracks: list[HomotheticTrack3D] = []
    for trk in design.tracks:
        n_l = len(trk.lobe_offsets_deg)
        old_arc = trk.lobe_offsets_deg[0][1]
        new_arc = old_arc * factor
        if n_l > 1:
            old_pitch = trk.lobe_offsets_deg[1][0] - trk.lobe_offsets_deg[0][0]
            old_gap = max(old_pitch - old_arc, 0.5)
        else:
            old_gap = 0.0
        # Keep total lobe-train span <= 26.0 deg so lobes stay strictly inside [0, 36] deg with >=5 deg margin
        max_gap = max(0.6, (25.0 - n_l * new_arc) / max(n_l - 1, 1)) if n_l > 1 else 0.0
        gap_deg = min(old_gap, max_gap)
        pitch = new_arc + gap_deg
        span = n_l * new_arc + (n_l - 1) * gap_deg
        if span > 28.0:
            raise ValueError(f"Scaled lobe train span {span:.3f} deg exceeds open-window safety bound in {design.code}")
        start = trk.vernier_phase_deg - 0.5 * span + 0.5 * new_arc
        new_lobes = tuple((float(start + i * pitch), float(new_arc)) for i in range(n_l))
        scaled_tracks.append(dataclasses.replace(trk, lobe_offsets_deg=new_lobes))
    out = dataclasses.replace(design, tracks=tuple(scaled_tracks))
    if abs(active_tooth_area_um2(out) - target_area_um2) > 1.0e-11:
        raise AssertionError(f"Iso-area normalization failed for {design.code}")
    return out


def _build_unbridged_control_from_specs(
    *,
    name: str,
    code: str,
    family_role: str,
    description: str,
    slot_widths_um: Sequence[float],
    tooth_widths_um: Sequence[float],
    z_stages_um: Sequence[float],
    h_stages_um: Sequence[float],
    generations: Sequence[int],
    lobe_counts: Sequence[int],
    lobe_chords_um: Sequence[float],
    inter_lobe_gaps_deg: Sequence[float],
    collar_widths_um: Sequence[float],
    target_area_um2: float,
) -> RobustClutchDesign3D:
    """Construct an unbridged non-fractal control inside [R_min, R_max] normalized to target_area_um2."""
    n_trk = len(slot_widths_um)
    total_slot_um = float(sum(slot_widths_um))
    span_um = H3_ROBUST_R_MAX_UM - H3_ROBUST_R_MIN_UM
    rem_metal_um = span_um - total_slot_um
    if rem_metal_um <= 0.05:
        raise ValueError(f"Insufficient stator metal budget ({rem_metal_um} um) in {code}")
    rib_w = rem_metal_um / float(n_trk + 1)

    cursor_r = H3_ROBUST_R_MIN_UM + rib_w
    tracks: list[HomotheticTrack3D] = []
    for idx in range(n_trk):
        w_s = float(slot_widths_um[idx])
        w_t = float(tooth_widths_um[idx])
        r_s_in = cursor_r
        r_s_out = cursor_r + w_s
        r_c = 0.5 * (r_s_in + r_s_out)
        r_t_in = r_c - 0.5 * w_t
        r_t_out = r_c + 0.5 * w_t
        z_st = float(z_stages_um[idx])
        h_st = float(h_stages_um[idx])
        z_pad_top = -H3_ROBUST_NOMINAL_OP_Z_UM - 0.5 * h_st - H3_ROBUST_ENGAGED_PAD_GAP_UM
        lobes, _ = _build_lobe_train_and_bridges(
            r_center_um=r_c,
            n_lobes=int(lobe_counts[idx]),
            lobe_chord_um=float(lobe_chords_um[idx]),
            inter_lobe_gap_deg=float(inter_lobe_gaps_deg[idx]),
            vernier_phase_deg=0.0,
            z_stage_center_um=z_st,
            h_stage_um=h_st,
            bridge_arc_width_deg=1.0,
            bridge_thickness_um=0.020,
            enable_bridges=False,
        )
        tracks.append(
            HomotheticTrack3D(
                track_index=idx,
                generation=int(generations[idx]),
                r_slot_in_um=float(r_s_in),
                r_slot_out_um=float(r_s_out),
                r_tooth_in_um=float(r_t_in),
                r_tooth_out_um=float(r_t_out),
                collar_width_um=min(float(collar_widths_um[idx]), 0.45 * rib_w),
                z_stage_center_um=z_st,
                h_stage_um=h_st,
                z_pad_top_um=float(z_pad_top),
                lobe_offsets_deg=lobes,
                vernier_phase_deg=0.0,
                micro_bridges=(),
            )
        )
        cursor_r = r_s_out + rib_w

    ribs = _assemble_ribs_for_tracks(
        tracks, H3_ROBUST_R_MIN_UM, H3_ROBUST_R_MAX_UM, H3_ROBUST_APERTURE_ARC_DEG
    )
    raw = RobustClutchDesign3D(
        name=name,
        code=code,
        family_role=family_role,
        description=description,
        R_min_um=H3_ROBUST_R_MIN_UM,
        R_max_um=H3_ROBUST_R_MAX_UM,
        aperture_arc_deg=H3_ROBUST_APERTURE_ARC_DEG,
        pad_thickness_um=H3_ROBUST_PAD_THICKNESS_UM,
        nominal_op_z_um=H3_ROBUST_NOMINAL_OP_Z_UM,
        is_fractal=False,
        has_micro_bridges=False,
        tracks=tuple(tracks),
        ribs=ribs,
    )
    return _scale_design_lobe_arcs_to_target_area(raw, target_area_um2)


def build_five_matched_robustness_controls(
    cantor_ref: RobustClutchDesign3D | None = None,
) -> list[RobustClutchDesign3D]:
    """Construct the 5 strictly area- and feature-matched non-fractal controls."""
    ref = cantor_ref if cantor_ref is not None else build_h3_cantor_robust_design()
    target_a = active_tooth_area_um2(ref)
    total_open_um = sum(t.slot_width_um for t in ref.tracks)

    # 1. Ctrl-KnifeEdge-g27: 19 uniform 90 nm slots (g_r = 27 nm, w = 36 nm), single fine stage (-40 nm)
    n_ke = H3_ROBUST_KNIFE_EDGE_TRACK_COUNT
    c_knife = _build_unbridged_control_from_specs(
        name="Ctrl-KnifeEdge-g27",
        code="Ctrl_KnifeEdge_g27",
        family_role="ctrl_knife_edge_point_opt",
        description=(
            "19-track uniform W=90 nm, w=36 nm, g_r=27 nm single-stage point optimizer "
            "matching H3-Cantor-Robust in A_tooth, open-slot budget, stator metal budget, and g_min."
        ),
        slot_widths_um=[H3_ROBUST_SLOT_FINE_UM] * n_ke,
        tooth_widths_um=[H3_ROBUST_W_RATIO * H3_ROBUST_SLOT_FINE_UM] * n_ke,
        z_stages_um=[H3_ROBUST_Z_STAGE_FINE_UM] * n_ke,
        h_stages_um=[H3_ROBUST_HEIGHT_TO_STAGE_RATIO * abs(H3_ROBUST_Z_STAGE_FINE_UM)] * n_ke,
        generations=[3] * n_ke,
        lobe_counts=[2] * n_ke,
        lobe_chords_um=[0.350] * n_ke,
        inter_lobe_gaps_deg=[5.0] * n_ke,
        collar_widths_um=[0.013] * n_ke,
        target_area_um2=target_a,
    )

    # 2. Ctrl-Uni-7Trk: 7 equal slots (W = 244.286 nm) at single coplanar stage z_stage = -120 nm
    w_uni = total_open_um / 7.0
    c_uni7 = _build_unbridged_control_from_specs(
        name="Ctrl-Uni-7Trk",
        code="Ctrl_Uni_7Trk",
        family_role="ctrl_uniform_7trk",
        description="Uniform 7-track single-stage periodic grating at z_stage = -120 nm, matched A_tooth.",
        slot_widths_um=[w_uni] * 7,
        tooth_widths_um=[H3_ROBUST_W_RATIO * w_uni] * 7,
        z_stages_um=[-0.120] * 7,
        h_stages_um=[0.084] * 7,
        generations=[2] * 7,
        lobe_counts=[4] * 7,
        lobe_chords_um=[0.243] * 7,
        inter_lobe_gaps_deg=[3.6] * 7,
        collar_widths_um=[0.039] * 7,
        target_area_um2=target_a,
    )

    # 3. Ctrl-Lin-3Stage: Arithmetic/linear 3-stage spacing W in {810, 450, 90} nm, z in -{360, 200, 40} nm
    lin_w_map = {1: 0.810, 2: 0.450, 3: 0.090}
    lin_z_map = {1: -0.360, 2: -0.200, 3: -0.040}
    lin_h_map = {1: 0.252, 2: 0.140, 3: 0.028}
    lin_c_map = {1: 0.729, 2: 0.405, 3: 0.081}
    lin_col_map = {1: 0.034, 2: 0.026, 3: 0.013}
    gens_cantor = H3_ROBUST_CANTOR_GENERATIONS
    c_lin3 = _build_unbridged_control_from_specs(
        name="Ctrl-Lin-3Stage",
        code="Ctrl_Lin_3Stage",
        family_role="ctrl_linear_3stage",
        description="Arithmetic 3-stage 7-track grating (W={810,450,90} nm, z_stage=-{360,200,40} nm).",
        slot_widths_um=[lin_w_map[g] for g in gens_cantor],
        tooth_widths_um=[H3_ROBUST_W_RATIO * lin_w_map[g] for g in gens_cantor],
        z_stages_um=[lin_z_map[g] for g in gens_cantor],
        h_stages_um=[lin_h_map[g] for g in gens_cantor],
        generations=gens_cantor,
        lobe_counts=[int(H3_ROBUST_LOBES_BY_GEN[g]) for g in gens_cantor],
        lobe_chords_um=[lin_c_map[g] for g in gens_cantor],
        inter_lobe_gaps_deg=[float(H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG[g]) for g in gens_cantor],
        collar_widths_um=[lin_col_map[g] for g in gens_cantor],
        target_area_um2=target_a,
    )

    # 4. Ctrl-Mono-3Stage: Exact multiset of 7 H3-Cantor-Robust tracks ordered monotonically (3,3,3,3,2,2,1)
    mono_gens = (3, 3, 3, 3, 2, 2, 1)
    c_mono3 = _build_unbridged_control_from_specs(
        name="Ctrl-Mono-3Stage",
        code="Ctrl_Mono_3Stage",
        family_role="ctrl_monotonic_3stage",
        description="Monotonic radial ordering (3,3,3,3,2,2,1) of exact Cantor track multiset, synchronized phase.",
        slot_widths_um=[H3_ROBUST_SLOT_FINE_UM * _homothetic_scale_for_gen(g) for g in mono_gens],
        tooth_widths_um=[H3_ROBUST_W_RATIO * H3_ROBUST_SLOT_FINE_UM * _homothetic_scale_for_gen(g) for g in mono_gens],
        z_stages_um=[H3_ROBUST_Z_STAGE_FINE_UM * _homothetic_scale_for_gen(g) for g in mono_gens],
        h_stages_um=[
            H3_ROBUST_HEIGHT_TO_STAGE_RATIO * abs(H3_ROBUST_Z_STAGE_FINE_UM) * _homothetic_scale_for_gen(g)
            for g in mono_gens
        ],
        generations=mono_gens,
        lobe_counts=[int(H3_ROBUST_LOBES_BY_GEN[g]) for g in mono_gens],
        lobe_chords_um=[H3_ROBUST_LOBE_CHORD_FINE_UM * _homothetic_scale_for_gen(g) for g in mono_gens],
        inter_lobe_gaps_deg=[float(H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG[g]) for g in mono_gens],
        collar_widths_um=[float(H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM[g]) for g in mono_gens],
        target_area_um2=target_a,
    )

    # 5. Ctrl-Shuf-OutPhase: Exact 7 Cantor radial slots, axial & theta tiers inverted (m_z = 4 - m_r)
    anti_gens = tuple(4 - g for g in gens_cantor)
    c_outphase = _build_unbridged_control_from_specs(
        name="Ctrl-Shuf-OutPhase",
        code="Ctrl_Shuf_OutPhase",
        family_role="ctrl_out_of_phase",
        description="Cross-dimensionally decoupled control: Cantor radial slots paired out-of-phase (m_z = 4 - m_r).",
        slot_widths_um=[H3_ROBUST_SLOT_FINE_UM * _homothetic_scale_for_gen(g) for g in gens_cantor],
        tooth_widths_um=[H3_ROBUST_W_RATIO * H3_ROBUST_SLOT_FINE_UM * _homothetic_scale_for_gen(g) for g in gens_cantor],
        z_stages_um=[H3_ROBUST_Z_STAGE_FINE_UM * _homothetic_scale_for_gen(ag) for ag in anti_gens],
        h_stages_um=[
            H3_ROBUST_HEIGHT_TO_STAGE_RATIO * abs(H3_ROBUST_Z_STAGE_FINE_UM) * _homothetic_scale_for_gen(ag)
            for ag in anti_gens
        ],
        generations=anti_gens,
        lobe_counts=[int(H3_ROBUST_LOBES_BY_GEN[ag]) for ag in anti_gens],
        lobe_chords_um=[0.180] * 7,
        inter_lobe_gaps_deg=[float(H3_ROBUST_INTER_LOBE_GAP_BY_GEN_DEG[ag]) for ag in anti_gens],
        collar_widths_um=[float(H3_ROBUST_BRIDGE_THICKNESS_BY_GEN_UM[g]) for g in gens_cantor],
        target_area_um2=target_a,
    )

    return [c_knife, c_uni7, c_lin3, c_mono3, c_outphase]


def build_all_robustness_study_designs() -> list[RobustClutchDesign3D]:
    """Return `[H3-Cantor-Robust, *5 matched controls, H3-Cantor-Sym-2x2x2]`."""
    h3 = build_h3_cantor_robust_design()
    h3_sym_ref = build_h3_cantor_sym_2x2x2_design()
    return [h3, *build_five_matched_robustness_controls(h3), h3_sym_ref]


def compute_design_fingerprint(design: RobustClutchDesign3D) -> str:
    """Compute cross-platform deterministic SHA-256 fingerprint of a RobustClutchDesign3D."""

    def _round_obj(obj: Any) -> Any:
        if isinstance(obj, float):
            return round(obj, 12)
        if isinstance(obj, dict):
            return {k: _round_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_round_obj(v) for v in obj]
        return obj

    payload = json.dumps(_round_obj(dataclasses.asdict(design)), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _lobe_sector_segments_deg(
    theta_deg: float, d_phi_deg: float, arc_deg: float
) -> list[tuple[float, float, bool, bool]]:
    """Map a single lobe interval onto Sector 0 [0, 90) deg, splitting cleanly across seam if needed."""
    center = tooth_center_angle_deg(theta_deg) + d_phi_deg
    low = center - 0.5 * arc_deg
    high = center + 0.5 * arc_deg
    if arc_deg <= 0.0 or arc_deg >= DEFAULT_SECTOR_DEG:
        raise ValueError(f"Invalid lobe arc_deg={arc_deg}")
    low_m = low % DEFAULT_SECTOR_DEG
    high_m = low_m + arc_deg
    if high_m <= DEFAULT_SECTOR_DEG + 1.0e-12:
        return [(float(low_m), float(min(high_m, DEFAULT_SECTOR_DEG)), True, True)]
    return [
        (float(low_m), float(DEFAULT_SECTOR_DEG), True, False),
        (0.0, float(high_m - DEFAULT_SECTOR_DEG), False, True),
    ]


def verify_design_3d_non_intersection(
    design: RobustClutchDesign3D,
    *,
    z_shift_um: float,
    theta_deg: float,
    delta_w_um: float = 0.0,
    delta_r_um: float = 0.0,
    tol_um: float = 1.0e-7,
) -> dict[str, Any]:
    """Verify strictly positive 3D clearance (zero solid overlap) between all rotor and stator prisms."""
    rotor_boxes: list[tuple[float, float, float, float, float, float, str]] = []
    stator_boxes: list[tuple[float, float, float, float, float, float, str]] = []

    for trk in design.tracks:
        w_t = trk.tooth_width_um + delta_w_um
        r_c_t = 0.5 * (trk.r_tooth_in_um + trk.r_tooth_out_um) + delta_r_um
        if w_t >= H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
            r_t0 = r_c_t - 0.5 * w_t
            r_t1 = r_c_t + 0.5 * w_t
            z_t0 = -z_shift_um - 0.5 * trk.h_stage_um
            z_t1 = -z_shift_um + 0.5 * trk.h_stage_um
            for l_idx, (d_phi, arc_deg) in enumerate(trk.lobe_offsets_deg):
                d_arc = math.degrees(delta_w_um / max(r_c_t, 0.5))
                eff_arc = arc_deg + d_arc
                if eff_arc < 0.05:
                    continue
                for p0, p1, _, _ in _lobe_sector_segments_deg(theta_deg, d_phi, eff_arc):
                    rotor_boxes.append((r_t0, r_t1, p0, p1, z_t0, z_t1, f"trk{trk.track_index}_lobe{l_idx}"))

        # Stator left/right aperture stage collars (metal ribs widen by delta_w_um -> slot narrows by delta_w_um)
        s_in = trk.r_slot_in_um + 0.5 * delta_w_um
        s_out = trk.r_slot_out_um - 0.5 * delta_w_um
        left_rib_w = design.ribs[trk.track_index].width_um
        right_rib_w = design.ribs[trk.track_index + 1].width_um
        col_w_L = trk.collar_width_um if delta_w_um >= 0.0 else min(
            trk.collar_width_um, 0.45 * max(0.0, left_rib_w + delta_w_um)
        )
        col_w_R = trk.collar_width_um if delta_w_um >= 0.0 else min(
            trk.collar_width_um, 0.45 * max(0.0, right_rib_w + delta_w_um)
        )
        col_L0 = s_in - col_w_L
        col_R1 = s_out + col_w_R
        z_s0 = trk.z_stage_center_um - 0.5 * trk.h_stage_um
        z_s1 = trk.z_stage_center_um + 0.5 * trk.h_stage_um
        if s_in - col_L0 >= H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
            stator_boxes.append((col_L0, s_in, 0.0, design.aperture_arc_deg, z_s0, z_s1, f"colL_{trk.track_index}"))
        if col_R1 - s_out >= H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
            stator_boxes.append((s_out, col_R1, 0.0, design.aperture_arc_deg, z_s0, z_s1, f"colR_{trk.track_index}"))

        # Stator micro-bridges
        for b_idx, br in enumerate(trk.micro_bridges):
            if s_out - s_in > 1.0e-6:
                stator_boxes.append(
                    (
                        s_in,
                        s_out,
                        br.phi_center_deg - 0.5 * br.phi_width_deg,
                        br.phi_center_deg + 0.5 * br.phi_width_deg,
                        br.z_bot_um,
                        br.z_top_um,
                        f"bridge_{trk.track_index}_{b_idx}",
                    )
                )

        # Stepped landing-pad terrace in [aperture + 1, 89] deg
        if s_out - s_in > 1.0e-6:
            stator_boxes.append(
                (
                    s_in,
                    s_out,
                    design.aperture_arc_deg + 1.0,
                    DEFAULT_SECTOR_DEG - 1.0,
                    trk.z_pad_top_um - design.pad_thickness_um,
                    trk.z_pad_top_um,
                    f"pad_{trk.track_index}",
                )
            )

    collisions: list[str] = []
    for rb in rotor_boxes:
        for sb in stator_boxes:
            r_ov = min(rb[1], sb[1]) - max(rb[0], sb[0])
            p_ov = min(rb[3], sb[3]) - max(rb[2], sb[2])
            z_ov = min(rb[5], sb[5]) - max(rb[4], sb[4])
            if r_ov > tol_um and p_ov > 1.0e-5 and z_ov > tol_um:
                collisions.append(f"{rb[6]} overlaps {sb[6]} (dr={r_ov:.5f}, dp={p_ov:.4f}, dz={z_ov:.5f})")

    return {
        "collision_free": len(collisions) == 0,
        "n_rotor_prisms": len(rotor_boxes),
        "n_stator_prisms": len(stator_boxes),
        "n_collisions": len(collisions),
        "collisions": collisions,
    }


@dataclass(frozen=True)
class PerturbedMeshBuildResult:
    """Built 3D BEM surface mesh together with cleanroom survival/shorting status flags."""

    mesh: ClutchSurfaceMesh | None
    panel_track_ids: np.ndarray
    panel_generations: np.ndarray
    shorted: bool
    all_teeth_etched_away: bool
    surviving_tracks: int
    surviving_lobes_per_sector: int
    min_radial_gap_um: float
    corner_self_area_um2: float


def build_homothetic_sector_bem_mesh(
    design: RobustClutchDesign3D,
    *,
    z_shift_um: float = H3_ROBUST_NOMINAL_OP_Z_UM,
    theta_deg: float = DISENGAGED_THETA_DEG,
    delta_w_um: float = 0.0,
    delta_r_um: float = 0.0,
    r_edge_um: float = 0.0,
    material: str = "Gold",
    temperature_K: float = 300.0,
    n_r_lobe: int | None = None,
    n_phi_lobe: int | None = None,
    n_z_lobe: int | None = None,
    n_phi_collar: int | None = None,
    n_phi_pad: int = 3,
) -> PerturbedMeshBuildResult:
    """Construct the exact C4-sector 3D BEM mesh for `design` under geometric/cleanroom perturbations."""
    n_r_lobe = int(design.bem_n_r_lobe if n_r_lobe is None else n_r_lobe)
    n_phi_lobe = int(design.bem_n_phi_lobe if n_phi_lobe is None else n_phi_lobe)
    n_z_lobe = int(design.bem_n_z_lobe if n_z_lobe is None else n_z_lobe)
    n_phi_collar = int(design.bem_n_phi_collar if n_phi_collar is None else n_phi_collar)
    r_edge_val = max(0.0, float(r_edge_um))
    # Physical EBL corner-fillet flat-face width reduction: delta_w_round = -2*(1 - pi/4)*r_edge
    dw_round_um = -2.0 * (1.0 - math.pi / 4.0) * r_edge_val
    a_corner_um2 = math.pi * ((2.0 * r_edge_val) ** 2) if r_edge_val > 0.0 else 0.0

    rotor_panels: list[Any] = []
    stator_panels: list[Any] = []
    panel_track_ids: list[int] = []
    panel_generations: list[int] = []

    min_gap_um = math.inf
    shorted = False
    surviving_tracks = 0
    surviving_lobes = 0

    def emit_rotor(
        kind: str, r0: float, r1: float, p0_rad: float, p1_rad: float, z0: float, z1: float, sign: int, trk: HomotheticTrack3D
    ) -> None:
        pan = repository_face(kind, r0, r1, math.degrees(p0_rad), math.degrees(p1_rad), z0, z1, sign, "rotor")
        rotor_panels.append(pan)
        panel_track_ids.append(trk.track_index)
        panel_generations.append(trk.generation)

    def emit_stator(kind: str, r0: float, r1: float, p0_rad: float, p1_rad: float, z0: float, z1: float, sign: int) -> None:
        pan = repository_face(kind, r0, r1, math.degrees(p0_rad), math.degrees(p1_rad), z0, z1, sign, "stator")
        stator_panels.append(pan)

    def emit_prism_stator(
        r0: float, r1: float, p0_deg: float, p1_deg: float, z0: float, z1: float, nr: int, np_sub: int, nz: int,
        *, include_radial_caps: bool = True
    ) -> None:
        re = subdivisions(r0, r1, nr)
        pe = subdivisions(math.radians(p0_deg), math.radians(p1_deg), np_sub)
        ze = subdivisions(z0, z1, nz)
        for i in range(nr):
            for j in range(np_sub):
                emit_stator("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[0], ze[0], -1)
                emit_stator("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[-1], ze[-1], 1)
        if include_radial_caps:
            for j in range(np_sub):
                for k in range(nz):
                    emit_stator("radial", re[0], re[0], pe[j], pe[j + 1], ze[k], ze[k + 1], -1)
                    emit_stator("radial", re[-1], re[-1], pe[j], pe[j + 1], ze[k], ze[k + 1], 1)
        for i in range(nr):
            for k in range(nz):
                emit_stator("azimuthal", re[i], re[i + 1], pe[0], pe[0], ze[k], ze[k + 1], -1)
                emit_stator("azimuthal", re[i], re[i + 1], pe[-1], pe[-1], ze[k], ze[k + 1], 1)

    for trk in design.tracks:
        # Stator slot boundaries shift inward into the slot by 0.5*delta_w_um when metal widens (delta_w_um > 0)
        s_in = trk.r_slot_in_um + 0.5 * delta_w_um
        s_out = trk.r_slot_out_um - 0.5 * delta_w_um
        left_rib_w = design.ribs[trk.track_index].width_um
        right_rib_w = design.ribs[trk.track_index + 1].width_um
        col_w_L = trk.collar_width_um if delta_w_um >= 0.0 else min(
            trk.collar_width_um, 0.45 * max(0.0, left_rib_w + delta_w_um)
        )
        col_w_R = trk.collar_width_um if delta_w_um >= 0.0 else min(
            trk.collar_width_um, 0.45 * max(0.0, right_rib_w + delta_w_um)
        )
        col_L0 = s_in - col_w_L
        col_R1 = s_out + col_w_R
        z_s0 = trk.z_stage_center_um - 0.5 * trk.h_stage_um
        z_s1 = trk.z_stage_center_um + 0.5 * trk.h_stage_um

        if s_in - col_L0 >= H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
            emit_prism_stator(col_L0, s_in, 0.0, design.aperture_arc_deg, z_s0, z_s1, 1, n_phi_collar, n_z_lobe)
        if col_R1 - s_out >= H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
            emit_prism_stator(s_out, col_R1, 0.0, design.aperture_arc_deg, z_s0, z_s1, 1, n_phi_collar, n_z_lobe)

        for br in trk.micro_bridges:
            b_phi_w = br.phi_width_deg + math.degrees(delta_w_um / max(trk.radial_center_um, 0.5))
            if s_out - s_in >= H3_ROBUST_MIN_SURVIVING_FEATURE_UM and b_phi_w >= 0.08:
                emit_prism_stator(
                    s_in,
                    s_out,
                    br.phi_center_deg - 0.5 * b_phi_w,
                    br.phi_center_deg + 0.5 * b_phi_w,
                    br.z_bot_um,
                    br.z_top_um,
                    1,
                    1,
                    1,
                    include_radial_caps=False,
                )

        if s_out - s_in >= H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
            emit_prism_stator(
                s_in,
                s_out,
                design.aperture_arc_deg + 1.0,
                DEFAULT_SECTOR_DEG - 1.0,
                trk.z_pad_top_um - design.pad_thickness_um,
                trk.z_pad_top_um,
                1,
                n_phi_pad,
                1,
            )

        # Rotor tooth lobes on this track
        w_t_eff = trk.tooth_width_um + delta_w_um + dw_round_um
        r_c_t = 0.5 * (trk.r_tooth_in_um + trk.r_tooth_out_um) + delta_r_um
        if w_t_eff < H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
            continue

        r_t0 = r_c_t - 0.5 * w_t_eff
        r_t1 = r_c_t + 0.5 * w_t_eff
        g_in = r_t0 - s_in
        g_out = s_out - r_t1
        min_gap_um = min(min_gap_um, g_in, g_out)
        if min(g_in, g_out) <= H3_ROBUST_MIN_UNSHORTED_GAP_UM:
            shorted = True
            continue

        z_t0 = -z_shift_um - 0.5 * trk.h_stage_um
        z_t1 = -z_shift_um + 0.5 * trk.h_stage_um
        re = subdivisions(r_t0, r_t1, n_r_lobe)
        ze = subdivisions(z_t0, z_t1, n_z_lobe)

        track_has_lobe = False
        for d_phi, arc_deg in trk.lobe_offsets_deg:
            d_arc = math.degrees((delta_w_um + dw_round_um) / max(r_c_t, 0.5))
            eff_arc = arc_deg + d_arc
            if eff_arc * math.pi / 180.0 * r_c_t < H3_ROBUST_MIN_SURVIVING_FEATURE_UM:
                continue
            track_has_lobe = True
            surviving_lobes += 1
            for low_deg, high_deg, cap_low, cap_high in _lobe_sector_segments_deg(theta_deg, d_phi, eff_arc):
                pe = subdivisions(math.radians(low_deg), math.radians(high_deg), n_phi_lobe)
                for i in range(n_r_lobe):
                    for j in range(n_phi_lobe):
                        emit_rotor("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[0], ze[0], -1, trk)
                        emit_rotor("horizontal", re[i], re[i + 1], pe[j], pe[j + 1], ze[-1], ze[-1], 1, trk)
                for j in range(n_phi_lobe):
                    for k in range(n_z_lobe):
                        emit_rotor("radial", re[0], re[0], pe[j], pe[j + 1], ze[k], ze[k + 1], -1, trk)
                        emit_rotor("radial", re[-1], re[-1], pe[j], pe[j + 1], ze[k], ze[k + 1], 1, trk)
                for i in range(n_r_lobe):
                    for k in range(n_z_lobe):
                        if cap_low:
                            emit_rotor("azimuthal", re[i], re[i + 1], pe[0], pe[0], ze[k], ze[k + 1], -1, trk)
                        if cap_high:
                            emit_rotor("azimuthal", re[i], re[i + 1], pe[-1], pe[-1], ze[k], ze[k + 1], 1, trk)
        if track_has_lobe:
            surviving_tracks += 1

    if shorted or len(rotor_panels) == 0 or len(stator_panels) == 0:
        return PerturbedMeshBuildResult(
            mesh=None,
            panel_track_ids=np.zeros(0, dtype=np.int64),
            panel_generations=np.zeros(0, dtype=np.int64),
            shorted=shorted,
            all_teeth_etched_away=(not shorted and len(rotor_panels) == 0),
            surviving_tracks=surviving_tracks,
            surviving_lobes_per_sector=surviving_lobes,
            min_radial_gap_um=float(min_gap_um if math.isfinite(min_gap_um) else 0.0),
            corner_self_area_um2=a_corner_um2,
        )

    base_tracks = [
        TrackSpec3D(
            t.r_slot_in_um,
            t.r_slot_out_um,
            t.r_tooth_in_um,
            t.r_tooth_out_um,
            -z_shift_um - 0.5 * t.h_stage_um,
            t.h_stage_um,
            t.generation,
        )
        for t in design.tracks
    ]
    elements = tuple(make_track_element(bt) for bt in base_tracks)
    geometry = Geometry(
        R_min=design.R_min_um,
        R_max=design.R_max_um,
        t_membrane=DEFAULT_T_MEMBRANE_UM,
        t_landing_pad=design.pad_thickness_um,
        z_tip=min(-z_shift_um - 0.5 * t.h_stage_um for t in design.tracks),
        h_teeth=max(t.h_stage_um for t in design.tracks),
        theta_deg=theta_deg,
        tooth_arc_deg=design.tracks[0].lobe_offsets_deg[0][1],
        aperture_arc_deg=design.aperture_arc_deg,
        elements=elements,
    )
    parameters = {
        "material": material,
        "temperature_K": float(temperature_K),
        "design_code": design.code,
        "R_min": design.R_min_um,
        "R_max": design.R_max_um,
        "z_shift_um": float(z_shift_um),
        "z_tip": geometry.z_tip,
        "h_teeth": geometry.h_teeth,
        "t_membrane": geometry.t_membrane,
        "t_landing_pad": geometry.t_landing_pad,
        "theta_deg": float(theta_deg),
        "delta_w_um": float(delta_w_um),
        "delta_r_um": float(delta_r_um),
        "r_edge_um": float(r_edge_val),
        "tooth_arc_deg": geometry.tooth_arc_deg,
        "aperture_arc_deg": geometry.aperture_arc_deg,
        "elements": [dataclasses.asdict(e) for e in elements],
    }
    mesh = ClutchSurfaceMesh(
        rotor=tuple(rotor_panels),
        stator=tuple(stator_panels),
        geometry=geometry,
        parameters=parameters,
        config=dict(parameters),
        panel_resolution={
            "n_r": n_r_lobe,
            "n_phi_tooth": n_phi_lobe,
            "n_phi_bridge": n_phi_pad,
            "n_z": n_z_lobe,
        },
    )
    return PerturbedMeshBuildResult(
        mesh=mesh,
        panel_track_ids=np.asarray(panel_track_ids, dtype=np.int64),
        panel_generations=np.asarray(panel_generations, dtype=np.int64),
        shorted=False,
        all_teeth_etched_away=False,
        surviving_tracks=surviving_tracks,
        surviving_lobes_per_sector=surviving_lobes,
        min_radial_gap_um=float(min_gap_um),
        corner_self_area_um2=a_corner_um2,
    )


def build_kappa_quadrature_rule(
    n_xi: int,
    kappa_0_um_inv: float,
    temperature_K: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Exact Matsubara + Euler-Maclaurin Gauss-Legendre tail rule matching `casimir_bem_solver.py`."""
    if temperature_K > 0.0:
        delta_kappa = 2.0 * math.pi * (BOLTZMANN_K_EV_PER_K * temperature_K) / HBAR_C_EV_UM
        matsubara_count = min(n_xi, min(8, max(2, n_xi // 3)))
        tail_count = max(1, int(n_xi))
        kappas = np.arange(matsubara_count, dtype=np.float64) * delta_kappa
        kappas[0] = 1.0e-4 * delta_kappa
        weights = np.full(matsubara_count, delta_kappa, dtype=np.float64)
        weights[0] *= 0.5
        kappa_cut = (matsubara_count - 0.5) * delta_kappa
        tail_k, tail_w, _ = _quadrature(tail_count, kappa_0_um_inv)
        return np.concatenate((kappas, kappa_cut + tail_k)), np.concatenate((weights, tail_w))
    kappas, weights, _ = _quadrature(n_xi, kappa_0_um_inv)
    return kappas, weights


_STATOR_LU_CACHE: dict[tuple[Any, ...], dict[tuple[int, int], tuple[torch.Tensor, torch.Tensor]]] = {}
_ROTOR_LU_CACHE: dict[tuple[Any, ...], dict[tuple[int, int], tuple[torch.Tensor, torch.Tensor]]] = {}
_ACTIVE_LARGE_STATOR_GEOM: tuple[Any, ...] | None = None
_ACTIVE_LARGE_ROTOR_GEOM: tuple[Any, ...] | None = None


def clear_bem_lu_caches() -> None:
    """Clear cached rotor and stator self-interaction LU factorizations."""
    global _ACTIVE_LARGE_STATOR_GEOM, _ACTIVE_LARGE_ROTOR_GEOM
    _STATOR_LU_CACHE.clear()
    _ROTOR_LU_CACHE.clear()
    _ACTIVE_LARGE_STATOR_GEOM = None
    _ACTIVE_LARGE_ROTOR_GEOM = None
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _same_body_lu_factors(
    body: Any,
    kappas: np.ndarray,
    corner_self_area_um2: float,
    dev: torch.device,
) -> dict[tuple[int, int], tuple[torch.Tensor, torch.Tensor]]:
    """Assemble C4 irreducible self-interaction blocks for `body` and return LU factors per (q, mode)."""
    N = body.count
    M = N * N
    K = len(kappas)
    sub_var = torch.as_tensor(
        (body.areas[:, None] + body.areas[None, :]) / (32.0 * math.pi), dtype=torch.float64, device=dev
    ).reshape(1, M)
    area_scale = torch.as_tensor(
        np.sqrt(body.areas[:, None]) * np.sqrt(body.areas[None, :]) / (4.0 * math.pi),
        dtype=torch.float64,
        device=dev,
    ).reshape(1, M)
    qw = torch.as_tensor(
        body.quad_weights[:, None] * body.quad_weights[None, :], dtype=torch.float64, device=dev
    ).reshape(16, 1)
    tgt_q = torch.as_tensor(body.quad_points.transpose(1, 0, 2)[:, :, None, :], dtype=torch.float64, device=dev)
    sec_blocks = torch.empty((K, 4, 2 * N, 2 * N), dtype=torch.float64, device=dev)

    for sec in (0, 1, 2):
        rot = _rotation(sec)
        src_pts = body.quad_points @ rot.T
        src_tan = np.einsum("ab,jmb->jma", rot, body.tangents)
        t_dot_t = torch.as_tensor(
            np.einsum("ima,jna->ijmn", body.tangents, src_tan, optimize=True), dtype=torch.float64, device=dev
        )
        src_q = torch.as_tensor(src_pts.transpose(1, 0, 2)[None, :, :, :], dtype=torch.float64, device=dev)
        delta = (tgt_q[:, None, :, :, :] - src_q[:, :, None, :, :]).reshape(16, M, 3)
        eff_d = torch.sqrt(torch.sum(delta**2, dim=2) + sub_var)
        del src_q, delta
        scale_q = (area_scale * qw) / eff_d
        ker_sum = torch.empty((K, N, N), dtype=torch.float64, device=dev)
        for qk in range(K):
            ker_sum[qk] = torch.sum(torch.exp(-float(kappas[qk]) * eff_d) * scale_q, dim=0).reshape(N, N)
        del eff_d, scale_q
        single = ker_sum[:, :, :, None, None] * t_dot_t[None, :, :, :, :]
        del ker_sum, t_dot_t
        if sec == 0:
            idx = np.arange(N)
            eye2 = torch.eye(2, dtype=torch.float64, device=dev)
            eff_areas = body.areas + corner_self_area_um2
            for qk, kap in enumerate(kappas):
                diag = torch.as_tensor(_disk_self_term(eff_areas, float(kap)), dtype=torch.float64, device=dev)
                single[qk, idx, idx] = diag[:, None, None] * eye2
        sec_blocks[:, sec] = single.permute(0, 1, 3, 2, 4).reshape(K, 2 * N, 2 * N)
        del single
    sec_blocks[:, 3] = sec_blocks[:, 1].transpose(1, 2)
    del sub_var, area_scale, qw, tgt_q

    lu_map: dict[tuple[int, int], tuple[torch.Tensor, torch.Tensor]] = {}
    for qk in range(K):
        b0, b1, b2, b3 = sec_blocks[qk, 0], sec_blocks[qk, 1], sec_blocks[qk, 2], sec_blocks[qk, 3]
        m0 = b0 + b1 + b2 + b3
        m2 = b0 - b1 + b2 - b3
        m1 = torch.complex(b0 - b2, b1 - b3)
        lu_map[(qk, 0)] = torch.linalg.lu_factor(m0)
        lu_map[(qk, 2)] = torch.linalg.lu_factor(m2)
        lu_map[(qk, 1)] = torch.linalg.lu_factor(m1)
        del m0, m2, m1
    del sec_blocks
    return lu_map


def evaluate_homothetic_3d_bem(
    design: RobustClutchDesign3D,
    *,
    z_shift_um: float = H3_ROBUST_NOMINAL_OP_Z_UM,
    theta_deg: float = DISENGAGED_THETA_DEG,
    delta_w_um: float = 0.0,
    delta_r_um: float = 0.0,
    r_edge_um: float = 0.0,
    material: str = "Gold",
    temperature_K: float = 300.0,
    n_xi: int = 20,
    max_steps: int = 0,
    kappas_override: Sequence[float] | None = None,
    device: Literal["auto", "cpu", "cuda"] = "auto",
    use_lu_cache: bool = True,
    n_r_lobe: int | None = None,
    n_phi_lobe: int | None = None,
    n_z_lobe: int | None = None,
    n_phi_collar: int | None = None,
) -> dict[str, Any]:
    """Evaluate 3D Vector-Dyadic Casimir force, free energy, per-track forces, and spectral trace."""
    t0 = time.perf_counter()
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA explicitly requested but unavailable.")
    dev = torch.device("cuda" if (device in {"auto", "cuda"} and torch.cuda.is_available()) else "cpu")

    eff_n_r = int(design.bem_n_r_lobe if n_r_lobe is None else n_r_lobe)
    eff_n_phi = int(design.bem_n_phi_lobe if n_phi_lobe is None else n_phi_lobe)
    eff_n_z = int(design.bem_n_z_lobe if n_z_lobe is None else n_z_lobe)
    eff_n_col = int(design.bem_n_phi_collar if n_phi_collar is None else n_phi_collar)

    built = build_homothetic_sector_bem_mesh(
        design,
        z_shift_um=z_shift_um,
        theta_deg=theta_deg,
        delta_w_um=delta_w_um,
        delta_r_um=delta_r_um,
        r_edge_um=r_edge_um,
        material=material,
        temperature_K=temperature_K,
        n_r_lobe=eff_n_r,
        n_phi_lobe=eff_n_phi,
        n_z_lobe=eff_n_z,
        n_phi_collar=eff_n_col,
    )
    if built.shorted or built.all_teeth_etched_away or built.mesh is None:
        return {
            "design_code": design.code,
            "design_name": design.name,
            "status": "shorted" if built.shorted else "etched_away",
            "shorted": built.shorted,
            "all_teeth_etched_away": built.all_teeth_etched_away,
            "surviving_tracks": built.surviving_tracks,
            "surviving_lobes_per_sector": built.surviving_lobes_per_sector,
            "min_radial_gap_um": built.min_radial_gap_um,
            "z_shift_um": float(z_shift_um),
            "theta_deg": float(theta_deg),
            "delta_w_um": float(delta_w_um),
            "delta_r_um": float(delta_r_um),
            "r_edge_um": float(r_edge_um),
            "material": material,
            "temperature_K": float(temperature_K),
            "F_z_pN": 0.0,
            "energy_hbar_c_per_um": 0.0,
            "energy_J": 0.0,
            "energy_kBT_300K": 0.0,
            "f_tracks_pN": [0.0 for _ in design.tracks],
            "e_tracks_approx_J": [0.0 for _ in design.tracks],
            "n_rotor_panels_sector": 0,
            "n_stator_panels_sector": 0,
            "kappas_um_inv": [],
            "f_kappa_pN_um": [],
            "e_kappa_hbar_c": [],
            "f_kappa_gen1_pN_um": [],
            "f_kappa_gen2_pN_um": [],
            "f_kappa_gen3_pN_um": [],
            "quadrature_incomplete": False,
            "elapsed_s": float(time.perf_counter() - t0),
        }

    mesh = built.mesh
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    mat_model = MaterialModel.from_parameters(mesh.parameters)
    dof_track_ids = np.repeat(built.panel_track_ids, 2)
    dof_gens = np.repeat(built.panel_generations, 2)

    char_gap_um = math.inf
    for sec in range(4):
        sp = stator.centroids @ _rotation(sec).T
        dists = np.linalg.norm(rotor.centroids[:, None, :] - sp[None, :, :], axis=2)
        char_gap_um = min(char_gap_um, float(np.min(dists)))
    k_eff = 1.0 / max(char_gap_um, 0.020)
    kappa_0 = 1.0 / 0.100

    if kappas_override is not None:
        full_kappas = np.asarray(kappas_override, dtype=np.float64)
        full_weights = np.ones_like(full_kappas)
    else:
        full_kappas, full_weights = build_kappa_quadrature_rule(n_xi, kappa_0, temperature_K)

    eval_count = min(len(full_kappas), int(max_steps)) if max_steps > 0 else len(full_kappas)
    kappas = full_kappas[:eval_count]
    weights = full_weights[:eval_count]
    K = len(kappas)

    # Cross-body geometry precomputation across 4 sectors (shared across wavenumber batches)
    Nt, Ns = rotor.count, stator.count
    M = Nt * Ns
    sub_var = torch.as_tensor(
        (rotor.areas[:, None] + stator.areas[None, :]) / (32.0 * math.pi), dtype=torch.float64, device=dev
    )
    area_scale = torch.as_tensor(
        np.sqrt(rotor.areas[:, None]) * np.sqrt(stator.areas[None, :]) / (4.0 * math.pi),
        dtype=torch.float64,
        device=dev,
    )
    qw = torch.as_tensor(
        rotor.quad_weights[:, None] * stator.quad_weights[None, :], dtype=torch.float64, device=dev
    ).reshape(16)
    u_z = torch.as_tensor(rotor.tangents[:, :, 2][:, None, :, None], dtype=torch.float64, device=dev)
    tgt_q = torch.as_tensor(rotor.quad_points.transpose(1, 0, 2)[:, :, None, :], dtype=torch.float64, device=dev)
    tgt_tan_t = torch.as_tensor(rotor.tangents, dtype=torch.float64, device=dev)

    nr_dof = 2 * Nt
    eye_r = torch.eye(nr_dof, dtype=torch.float64, device=dev)
    eye_c = torch.eye(nr_dof, dtype=torch.complex128, device=dev)

    dof_forces = np.zeros(nr_dof, dtype=np.float64)
    dof_energies = np.zeros(nr_dof, dtype=np.float64)
    f_kappa_pN_um = np.zeros(K, dtype=np.float64)
    e_kappa_hbar_c = np.zeros(K, dtype=np.float64)
    f_kappa_by_gen = {1: np.zeros(K, dtype=np.float64), 2: np.zeros(K, dtype=np.float64), 3: np.zeros(K, dtype=np.float64)}
    energy_total_hbar_c_per_um = 0.0

    global _ACTIVE_LARGE_STATOR_GEOM, _ACTIVE_LARGE_ROTOR_GEOM
    d_hash = compute_design_fingerprint(design)
    is_large_mesh = max(Nt, Ns) > 500
    max_k_batch = 6 if is_large_mesh else 28
    cache_ok = bool(use_lu_cache and K <= 32)
    max_cache_entries = max(6, math.ceil(K / max_k_batch)) if is_large_mesh else 16

    stator_geom_key = (
        d_hash,
        round(float(delta_w_um), 9),
        round(float(r_edge_um), 9),
        eff_n_phi,
        eff_n_z,
        eff_n_col,
        str(dev),
    )
    rotor_geom_key = (
        d_hash,
        round(float(theta_deg), 9),
        round(float(delta_w_um), 9),
        round(float(delta_r_um), 9),
        round(float(r_edge_um), 9),
        eff_n_r,
        eff_n_phi,
        eff_n_z,
        str(dev),
    )
    if is_large_mesh:
        if not cache_ok:
            clear_bem_lu_caches()
        else:
            evicted = False
            if _ACTIVE_LARGE_STATOR_GEOM != stator_geom_key:
                _STATOR_LU_CACHE.clear()
                _ACTIVE_LARGE_STATOR_GEOM = stator_geom_key
                evicted = True
            if _ACTIVE_LARGE_ROTOR_GEOM != rotor_geom_key:
                _ROTOR_LU_CACHE.clear()
                _ACTIVE_LARGE_ROTOR_GEOM = rotor_geom_key
                evicted = True
            if evicted and dev.type == "cuda":
                torch.cuda.empty_cache()
    elif _ACTIVE_LARGE_STATOR_GEOM is not None or _ACTIVE_LARGE_ROTOR_GEOM is not None:
        clear_bem_lu_caches()

    for q_start in range(0, K, max_k_batch):
        q_end = min(K, q_start + max_k_batch)
        k_batch = kappas[q_start:q_end]
        w_batch = weights[q_start:q_end]
        Kb = len(k_batch)
        kap_sig = tuple(round(float(k), 10) for k in k_batch)

        stator_key = (*stator_geom_key, kap_sig)
        # Rotor self-interaction is strictly invariant under rigid z_shift_um!
        rotor_key = (*rotor_geom_key, kap_sig)

        if cache_ok and stator_key in _STATOR_LU_CACHE:
            lu_s_map = _STATOR_LU_CACHE[stator_key]
        else:
            lu_s_map = _same_body_lu_factors(stator, k_batch, built.corner_self_area_um2, dev)
            if cache_ok:
                if not is_large_mesh and len(_STATOR_LU_CACHE) >= max_cache_entries:
                    _STATOR_LU_CACHE.clear()
                    if dev.type == "cuda":
                        torch.cuda.empty_cache()
                _STATOR_LU_CACHE[stator_key] = lu_s_map

        if cache_ok and rotor_key in _ROTOR_LU_CACHE:
            lu_r_map = _ROTOR_LU_CACHE[rotor_key]
        else:
            lu_r_map = _same_body_lu_factors(rotor, k_batch, built.corner_self_area_um2, dev)
            if cache_ok:
                if not is_large_mesh and len(_ROTOR_LU_CACHE) >= max_cache_entries:
                    _ROTOR_LU_CACHE.clear()
                    if dev.type == "cuda":
                        torch.cuda.empty_cache()
                _ROTOR_LU_CACHE[rotor_key] = lu_r_map

        rs_sec = torch.empty((Kb, 4, 2 * Nt, 2 * Ns), dtype=torch.float64, device=dev)
        dz_sec = torch.empty((Kb, 4, 2 * Nt, 2 * Ns), dtype=torch.float64, device=dev)

        for sec in range(4):
            rot = _rotation(sec)
            src_pts = stator.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, stator.tangents)
            src_tan_t = torch.as_tensor(src_tan, dtype=torch.float64, device=dev)
            t_dot_t = torch.as_tensor(
                np.einsum("ima,jna->ijmn", rotor.tangents, src_tan, optimize=True), dtype=torch.float64, device=dev
            )
            v_z = src_tan_t[:, :, 2][None, :, None, :]
            src_q = torch.as_tensor(src_pts.transpose(1, 0, 2)[None, :, :, :], dtype=torch.float64, device=dev)
            delta = (tgt_q[:, None, :, :, :] - src_q[:, :, None, :, :]).reshape(16, Nt, Ns, 3)
            eff_d = torch.sqrt(torch.sum(delta**2, dim=3) + sub_var[None, :, :])
            inv_d = 1.0 / eff_d
            scale = (area_scale[None, :, :] * qw[:, None, None]) * inv_d
            dz_over_d = delta[:, :, :, 2] * inv_d
            u_R = torch.einsum("ima,qija->qijm", tgt_tan_t, delta)
            v_R = torch.einsum("jna,qija->qijn", src_tan_t, delta)
            R_inv2 = (inv_d**2)[:, :, :, None, None]
            Z = delta[:, :, :, 2][:, :, :, None, None]
            D_raw = u_R[:, :, :, :, None] * v_R[:, :, :, None, :] * R_inv2
            D_m = D_raw.reshape(16, M, 4).permute(1, 2, 0).contiguous()
            dD_m = (
                (u_z[None] * v_R[:, :, :, None, :] + u_R[:, :, :, :, None] * v_z[None]) * R_inv2
                - 2.0 * Z * D_raw * R_inv2
            ).reshape(16, M, 4).permute(1, 2, 0).contiguous()
            del src_tan_t, v_z, src_q, delta, u_R, v_R, R_inv2, Z, D_raw

            eff_d_f = eff_d.reshape(16, M)
            inv_d_f = inv_d.reshape(16, M)
            scale_f = scale.reshape(16, M)
            dz_d_f = dz_over_d.reshape(16, M)

            W_D = torch.empty((Kb, 16, M), dtype=torch.float64, device=dev)
            W_dz_D = torch.empty((Kb, 16, M), dtype=torch.float64, device=dev)
            s_t_all = torch.empty((Kb, Nt, Ns, 1, 1), dtype=torch.float64, device=dev)
            dz_t_all = torch.empty((Kb, Nt, Ns, 1, 1), dtype=torch.float64, device=dev)

            for qk, kap_val in enumerate(k_batch):
                kap = float(kap_val)
                x = kap * eff_d_f
                ker = torch.exp(-x) * scale_f
                rad_deriv = -ker * (kap + inv_d_f)
                sc_dz = rad_deriv * dz_d_f
                inv = 1.0 / (1.0 + x)
                denom = 1.0 - inv + inv**2
                c_dir = (1.0 + inv + inv**2) / denom
                dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denom**2
                s_t_all[qk] = (0.5 * torch.sum(ker, dim=0)).reshape(Nt, Ns, 1, 1)
                dz_t_all[qk] = (0.5 * torch.sum(sc_dz, dim=0)).reshape(Nt, Ns, 1, 1)
                W_D[qk] = -0.25 * ker * c_dir
                W_dz_D[qk] = -0.25 * sc_dz * c_dir - 0.25 * ker * dc_dir_dx * kap * dz_d_f
                del x, ker, rad_deriv, sc_dz, inv, denom, c_dir, dc_dir_dx

            del eff_d, inv_d, scale, dz_over_d, eff_d_f, inv_d_f, scale_f, dz_d_f
            W_D_m = W_D.permute(2, 1, 0).contiguous()
            del W_D
            W_dz_m = W_dz_D.permute(2, 1, 0).contiguous()
            del W_dz_D
            s_D_all = torch.bmm(D_m, W_D_m).permute(2, 0, 1).reshape(Kb, Nt, Ns, 2, 2)
            dz_D_all = (torch.bmm(D_m, W_dz_m) + torch.bmm(dD_m, W_D_m)).permute(2, 0, 1).reshape(Kb, Nt, Ns, 2, 2)
            del D_m, dD_m, W_D_m, W_dz_m
            single_all = s_t_all * t_dot_t[None] + s_D_all
            dz_all = dz_t_all * t_dot_t[None] + dz_D_all
            del t_dot_t, s_t_all, dz_t_all, s_D_all, dz_D_all
            rs_sec[:, sec] = single_all.permute(0, 1, 3, 2, 4).reshape(Kb, 2 * Nt, 2 * Ns)
            dz_sec[:, sec] = dz_all.permute(0, 1, 3, 2, 4).reshape(Kb, 2 * Nt, 2 * Ns)
            del single_all, dz_all

        for qk in range(Kb):
            q_global = q_start + qk
            kap = float(k_batch[qk])
            w_q = float(w_batch[qk])
            tm, te, _ = mat_model.channel_weights(kap, k_eff=k_eff)
            q_dof = np.zeros(nr_dof, dtype=np.float64)
            e_dof = np.zeros(nr_dof, dtype=np.float64)
            q_logdet = 0.0
            rs_q = rs_sec[qk]
            dz_q = dz_sec[qk]

            for mode, mult in ((0, 1.0), (2, 1.0), (1, 2.0)):
                lu_r, piv_r = lu_r_map[(qk, mode)]
                lu_s, piv_s = lu_s_map[(qk, mode)]
                if mode == 0:
                    g = rs_q[0] + rs_q[1] + rs_q[2] + rs_q[3]
                    dg = dz_q[0] + dz_q[1] + dz_q[2] + dz_q[3]
                    sr, dsr = g.T.contiguous(), dg.T.contiguous()
                    eye = eye_r
                elif mode == 2:
                    g = rs_q[0] - rs_q[1] + rs_q[2] - rs_q[3]
                    dg = dz_q[0] - dz_q[1] + dz_q[2] - dz_q[3]
                    sr, dsr = g.T.contiguous(), dg.T.contiguous()
                    eye = eye_r
                else:
                    g = torch.complex(rs_q[0] - rs_q[2], rs_q[1] - rs_q[3])
                    dg = torch.complex(dz_q[0] - dz_q[2], dz_q[1] - dz_q[3])
                    sr, dsr = g.mH.contiguous(), dg.mH.contiguous()
                    eye = eye_c

                x = torch.linalg.lu_solve(lu_r, piv_r, g)
                ns_col = sr.shape[1]
                z_all = torch.linalg.lu_solve(lu_s, piv_s, torch.cat((sr, dsr), dim=1))
                z, dz = z_all[:, :ns_col], z_all[:, ns_col:]
                coupling = x @ z
                B, C = dg @ z, x @ dz

                tm_cached: tuple[np.ndarray, float, np.ndarray] | None = None
                for ch_idx, ch_w in enumerate((tm, te)):
                    if ch_idx == 1 and tm_cached is not None and math.isclose(tm**2, te**2, rel_tol=1.0e-14):
                        per_dof, ch_ld, coup_diag = tm_cached
                    else:
                        pw = ch_w**2
                        y = eye - pw * coupling
                        lu_y, piv_y = torch.linalg.lu_factor(y)
                        U = torch.linalg.lu_solve(lu_y, piv_y, C)
                        V = torch.linalg.lu_solve(
                            lu_r, piv_r, torch.linalg.lu_solve(lu_y, piv_y, B, left=False), left=False
                        )
                        per_dof = (-pw * (torch.diagonal(V).real + torch.diagonal(U).real)).detach().cpu().numpy()
                        sign_y, slog_y = torch.linalg.slogdet(y)
                        if abs(complex(sign_y.item())) == 0.0:
                            raise linalg.LinAlgError("Singular scattering determinant Y.")
                        ch_ld = float(slog_y.item())
                        coup_diag = (-pw * torch.diagonal(coupling).real).detach().cpu().numpy()
                        if ch_idx == 0:
                            tm_cached = (per_dof, ch_ld, coup_diag)

                    q_dof += mult * (-per_dof / (2.0 * math.pi))
                    q_logdet += mult * ch_ld
                    e_dof += mult * (coup_diag / (2.0 * math.pi))

            f_kappa_pN_um[q_global] = float(np.sum(q_dof) * MEEP_FORCE_TO_SI * 1.0e12)
            e_kappa_hbar_c[q_global] = float(q_logdet / (2.0 * math.pi))
            for gen_lvl in (1, 2, 3):
                f_kappa_by_gen[gen_lvl][q_global] = float(
                    np.sum(q_dof[dof_gens == gen_lvl]) * MEEP_FORCE_TO_SI * 1.0e12
                )
            if kappas_override is None:
                dof_forces += w_q * q_dof
                dof_energies += w_q * e_dof
                energy_total_hbar_c_per_um += w_q * float(q_logdet / (2.0 * math.pi))

        del rs_sec, dz_sec
        if not cache_ok:
            del lu_r_map, lu_s_map
            if dev.type == "cuda":
                torch.cuda.empty_cache()

    f_tracks_pN = [
        float(np.sum(dof_forces[dof_track_ids == trk.track_index]) * MEEP_FORCE_TO_SI * 1.0e12)
        for trk in design.tracks
    ]
    e_tracks_J = [
        float(np.sum(dof_energies[dof_track_ids == trk.track_index]) * MEEP_ENERGY_TO_SI_J)
        for trk in design.tracks
    ]
    f_total_pN = float(sum(f_tracks_pN))
    energy_J = float(energy_total_hbar_c_per_um * MEEP_ENERGY_TO_SI_J)

    return {
        "design_code": design.code,
        "design_name": design.name,
        "status": "completed",
        "shorted": False,
        "all_teeth_etched_away": False,
        "surviving_tracks": built.surviving_tracks,
        "surviving_lobes_per_sector": built.surviving_lobes_per_sector,
        "min_radial_gap_um": built.min_radial_gap_um,
        "z_shift_um": float(z_shift_um),
        "theta_deg": float(theta_deg),
        "delta_w_um": float(delta_w_um),
        "delta_r_um": float(delta_r_um),
        "r_edge_um": float(r_edge_um),
        "material": material,
        "temperature_K": float(temperature_K),
        "F_z_pN": f_total_pN,
        "energy_hbar_c_per_um": float(energy_total_hbar_c_per_um),
        "energy_J": energy_J,
        "energy_kBT_300K": float(energy_J / KBT_300K_SI_J),
        "f_tracks_pN": f_tracks_pN,
        "e_tracks_approx_J": e_tracks_J,
        "n_rotor_panels_sector": int(rotor.count),
        "n_stator_panels_sector": int(stator.count),
        "kappas_um_inv": [round(float(k), 6) for k in kappas],
        "f_kappa_pN_um": [round(float(v), 6) for v in f_kappa_pN_um],
        "e_kappa_hbar_c": [round(float(v), 6) for v in e_kappa_hbar_c],
        "f_kappa_gen1_pN_um": [round(float(v), 6) for v in f_kappa_by_gen[1]],
        "f_kappa_gen2_pN_um": [round(float(v), 6) for v in f_kappa_by_gen[2]],
        "f_kappa_gen3_pN_um": [round(float(v), 6) for v in f_kappa_by_gen[3]],
        "quadrature_incomplete": bool(eval_count < len(full_kappas)),
        "elapsed_s": float(time.perf_counter() - t0),
    }


def evaluate_laplace_capacitance_and_vcrit(
    design: RobustClutchDesign3D,
    *,
    f_z_nominal_pN: float,
    z_shift_um: float = H3_ROBUST_NOMINAL_OP_Z_UM,
    theta_deg: float = DISENGAGED_THETA_DEG,
    dz_step_um: float = 0.002,
) -> dict[str, float]:
    """Compute exact 3D Laplace BEM mutual capacitance C_mutual(z) and uniform-bias V_crit."""
    if dz_step_um <= 0.0:
        raise ValueError("dz_step_um must be strictly positive for finite-difference capacitance gradient.")

    def _cap_at(z_s: float) -> float:
        built = build_homothetic_sector_bem_mesh(design, z_shift_um=z_s, theta_deg=theta_deg)
        if built.mesh is None:
            raise ValueError(f"Cannot compute Laplace capacitance on degenerate mesh for {design.code}")
        rotor = built.mesh.sector_arrays("rotor")
        stator = built.mesh.sector_arrays("stator")
        nr, ns = rotor.count, stator.count
        rr = np.zeros((nr, nr), dtype=np.float64)
        ss = np.zeros((ns, ns), dtype=np.float64)
        rs = np.zeros((nr, ns), dtype=np.float64)
        for sec in range(DEFAULT_NUM_SECTORS):
            rr += _yukawa_blocks(rotor, rotor, sec, 0.0, same_body=True).single_layer
            ss += _yukawa_blocks(stator, stator, sec, 0.0, same_body=True).single_layer
            rs += _yukawa_blocks(rotor, stator, sec, 0.0, same_body=False).single_layer
        mat = np.block([[rr, rs], [rs.T, ss]])
        rhs = np.concatenate((np.sqrt(rotor.areas), -np.sqrt(stator.areas))) / 2.0
        charge = linalg.solve(mat, rhs, check_finite=True)
        return float(DEFAULT_NUM_SECTORS) * EPSILON_0_F_PER_M * 1.0e-6 * float(np.dot(np.sqrt(rotor.areas), charge[:nr]))

    c_mid = _cap_at(z_shift_um)
    c_plus = _cap_at(z_shift_um - dz_step_um)   # dz_rotor = +dz_step_um
    c_minus = _cap_at(z_shift_um + dz_step_um)  # dz_rotor = -dz_step_um
    dC_dz_F_per_m = (c_plus - c_minus) / (2.0 * dz_step_um * 1.0e-6)
    f_z_N = max(0.0, float(f_z_nominal_pN) * 1.0e-12)
    denom = max(abs(dC_dz_F_per_m), 1.0e-18)
    v_crit_V = math.sqrt(2.0 * f_z_N / denom)
    return {
        "C_mutual_fF": float(c_mid * 1.0e15),
        "dC_dz_nF_per_m": float(dC_dz_F_per_m * 1.0e9),
        "abs_dC_dz_nF_per_m": float(abs(dC_dz_F_per_m) * 1.0e9),
        "V_crit_V": float(v_crit_V),
        "V_crit_mV": float(v_crit_V * 1.0e3),
    }


def solve_hermite_clamped_beam_fem(
    *,
    span_length_m: float,
    flexural_rigidity_Nm2: float,
    q_load_N_per_m: float,
    k_neg_N_per_m2: float = 0.0,
    n_elements: int = 32,
) -> dict[str, float]:
    """32-element Hermite cubic Euler-Bernoulli clamped-clamped beam FEM solver with negative-stiffness coupling."""
    if span_length_m <= 0.0 or flexural_rigidity_Nm2 <= 0.0 or n_elements < 4:
        raise ValueError("Invalid beam parameters for Hermite FEM solver.")

    # pint dimensional verification on inputs when pint is installed (SI float fallback on offline cluster envs)
    if _UREG is not None:
        L_q = span_length_m * _UREG.meter
        EI_q = flexural_rigidity_Nm2 * (_UREG.newton * _UREG.meter**2)
        q_q = q_load_N_per_m * (_UREG.newton / _UREG.meter)
        w_analytic_q = (q_q * L_q**4) / (384.0 * EI_q)
        w_analytic_m = float(w_analytic_q.to(_UREG.meter).magnitude)
    else:
        w_analytic_m = float((q_load_N_per_m * span_length_m**4) / (384.0 * flexural_rigidity_Nm2))

    n_nodes = n_elements + 1
    n_dof = 2 * n_nodes
    le = span_length_m / float(n_elements)

    # Use scaled nodal DoFs [w_n, le * theta_n] so bending and geometric matrices are O(1) well-conditioned
    ke_bend = (flexural_rigidity_Nm2 / (le**3)) * np.array(
        [
            [12.0, 6.0, -12.0, 6.0],
            [6.0, 4.0, -6.0, 2.0],
            [-12.0, -6.0, 12.0, -6.0],
            [6.0, 2.0, -6.0, 4.0],
        ],
        dtype=np.float64,
    )
    me_consistent = (le / 420.0) * np.array(
        [
            [156.0, 22.0, 54.0, -13.0],
            [22.0, 4.0, 13.0, -3.0],
            [54.0, 13.0, 156.0, -22.0],
            [-13.0, -3.0, -22.0, 4.0],
        ],
        dtype=np.float64,
    )
    fe_load = q_load_N_per_m * le * np.array([0.5, 1.0 / 12.0, 0.5, -1.0 / 12.0], dtype=np.float64)

    K_bend = np.zeros((n_dof, n_dof), dtype=np.float64)
    M_geom = np.zeros((n_dof, n_dof), dtype=np.float64)
    F_vec = np.zeros(n_dof, dtype=np.float64)

    for e in range(n_elements):
        idx = slice(2 * e, 2 * e + 4)
        K_bend[idx, idx] += ke_bend
        M_geom[idx, idx] += me_consistent
        F_vec[idx] += fe_load

    # Clamped-clamped BCs: u_0 = theta_0 = u_N = theta_N = 0
    free = slice(2, n_dof - 2)
    K_b_ff = K_bend[free, free]
    M_g_ff = M_geom[free, free]
    F_f = F_vec[free]

    pull_in_margin = math.inf
    buckled = False
    if k_neg_N_per_m2 > 0.0:
        eigvals = linalg.eigvalsh(K_b_ff, k_neg_N_per_m2 * M_g_ff)
        pull_in_margin = float(np.min(eigvals))
        if pull_in_margin <= 1.001:
            buckled = True

    if buckled:
        return {
            "max_deflection_m": math.inf,
            "analytic_no_kneg_deflection_m": abs(w_analytic_m),
            "pull_in_eigenvalue_margin": pull_in_margin,
            "buckled": True,
        }

    K_eff = K_b_ff - max(0.0, k_neg_N_per_m2) * M_g_ff
    u_free = linalg.solve(K_eff, F_f, assume_a="pos", check_finite=True)
    u_all = np.zeros(n_dof, dtype=np.float64)
    u_all[free] = u_free
    nodal_w = np.abs(u_all[0::2])
    return {
        "max_deflection_m": float(np.max(nodal_w)),
        "analytic_no_kneg_deflection_m": abs(w_analytic_m),
        "pull_in_eigenvalue_margin": float(pull_in_margin),
        "buckled": False,
    }


def compute_stator_rib_elastostatic_safety(
    design: RobustClutchDesign3D,
    *,
    track_radial_stiffness_N_per_m: Sequence[float],
    v_patch_rms_mv: float = 20.0,
    overlay_eccentricity_nm: float = 5.0,
    delta_w_nm: float = 0.0,
    youngs_modulus_Pa: float = H3_ROBUST_GOLD_YOUNGS_MODULUS_PA,
) -> dict[str, Any]:
    """Evaluate 32-element Hermite FEM lateral deflection and safety factor SF_rib across all stator ribs."""
    v_patch_V = float(v_patch_rms_mv) * 1.0e-3
    dr_ovl_m = float(overlay_eccentricity_nm) * 1.0e-9
    dw_m = float(delta_w_nm) * 1.0e-9

    per_rib: list[dict[str, Any]] = []
    min_sf = math.inf
    max_defl_nm = 0.0
    any_buckled = False

    for rib in design.ribs:
        b_rib_m = rib.width_um * 1.0e-6 + dw_m
        h_rib_m = rib.height_um * 1.0e-6
        L_arc_m = (rib.radial_center_um * 1.0e-6) * math.radians(rib.unsupported_arc_deg)

        adj_indices = [idx for idx in (rib.left_track_index, rib.right_track_index) if idx is not None]
        local_min_gap_m = math.inf
        k_neg_per_m = 0.0
        q_net_per_m = 0.0

        for side_sign, t_idx in ((-1.0, rib.left_track_index), (1.0, rib.right_track_index)):
            if t_idx is None:
                continue
            trk = design.tracks[t_idx]
            g_m = trk.radial_gap_um * 1.0e-6 - dw_m
            local_min_gap_m = min(local_min_gap_m, g_m)
            if g_m <= H3_ROBUST_MIN_UNSHORTED_GAP_UM * 1.0e-6:
                any_buckled = True
                break
            h_eff_m = trk.h_stage_um * 1.0e-6
            total_trk_arc_m = float(DEFAULT_NUM_SECTORS) * (trk.radial_center_um * 1.0e-6) * math.radians(
                design.aperture_arc_deg
            )
            # Half of track's two-wall destabilizing Casimir stiffness acts on each bordering rib
            k_cas_side = 0.5 * max(0.0, float(track_radial_stiffness_N_per_m[t_idx])) / max(total_trk_arc_m, 1.0e-9)
            k_el_side = EPSILON_0_F_PER_M * h_eff_m * (v_patch_V**2) / (g_m**3)
            p_el_side = 0.5 * EPSILON_0_F_PER_M * h_eff_m * (v_patch_V**2) / (g_m**2)
            k_neg_per_m += k_cas_side + k_el_side
            # Static imbalance from unequal left/right gaps plus worst-case radial overlay eccentricity
            q_net_per_m += side_sign * p_el_side

        q_total_N_per_m = abs(q_net_per_m) + k_neg_per_m * dr_ovl_m

        if b_rib_m < H3_ROBUST_MIN_SURVIVING_FEATURE_UM * 1.0e-6 or any_buckled:
            any_buckled = True
            min_sf = 0.0
            max_defl_nm = math.inf
            per_rib.append(
                {
                    "rib_index": rib.rib_index,
                    "b_rib_nm": b_rib_m * 1.0e9,
                    "L_arc_um": L_arc_m * 1.0e6,
                    "deflection_nm": math.inf,
                    "safety_factor": 0.0,
                    "buckled": True,
                }
            )
            continue

        EI_Nm2 = youngs_modulus_Pa * h_rib_m * (b_rib_m**3) / 12.0
        fem = solve_hermite_clamped_beam_fem(
            span_length_m=L_arc_m,
            flexural_rigidity_Nm2=EI_Nm2,
            q_load_N_per_m=q_total_N_per_m,
            k_neg_N_per_m2=k_neg_per_m,
        )
        if fem["buckled"]:
            any_buckled = True
            sf_r = 0.0
            defl_nm = math.inf
        else:
            defl_m = max(fem["max_deflection_m"], 1.0e-18)
            defl_nm = defl_m * 1.0e9
            sf_r = local_min_gap_m / (3.0 * defl_m)
            max_defl_nm = max(max_defl_nm, defl_nm)
        min_sf = min(min_sf, sf_r)
        per_rib.append(
            {
                "rib_index": rib.rib_index,
                "b_rib_nm": float(b_rib_m * 1.0e9),
                "L_arc_um": float(L_arc_m * 1.0e6),
                "deflection_nm": float(defl_nm) if math.isfinite(defl_nm) else 1.0e9,
                "safety_factor": float(sf_r),
                "pull_in_margin": float(fem["pull_in_eigenvalue_margin"]),
                "buckled": bool(fem["buckled"]),
                "adjacent_tracks": adj_indices,
            }
        )

    return {
        "SF_rib": 0.0 if any_buckled else float(min_sf),
        "max_rib_deflection_nm": 1.0e9 if any_buckled else float(max_defl_nm),
        "any_rib_buckled": bool(any_buckled),
        "v_patch_rms_mv": float(v_patch_rms_mv),
        "overlay_eccentricity_nm": float(overlay_eccentricity_nm),
        "per_rib": per_rib,
    }
