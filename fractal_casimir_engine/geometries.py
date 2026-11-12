#!/usr/bin/env python3
"""Chiral multi-scale Cantor NEMS geometries for the Fractal Casimir Engine.

All coordinates are in micrometres (um) and angles in degrees unless suffixed
with ``_rad``. Four-fold cyclic symmetry (C_4, 90-degree sector period) is
enforced across all rotor and stator structures in true vacuum (eps_bg = 1.0).

Designs implemented:
1. ``Sym_Baseline_CantorN2``:
   Reflection-symmetric N=2 Cantor control (zero net chiral coupling).
2. ``Config_B_Manhattan_Vernier``:
   100% Manhattan vertical-wall EBL architecture combining radially tapering
   upper Cantor slot collars (repulsive up-stroke: F_z > 0, tau_theta > 0),
   expanding horn-shaped recessed Cantor landing pads + lower cheek rails
   (attractive down-stroke: F_z < 0, tau_theta > 0), and Cantor generation
   Vernier phase staggering.
3. ``Config_C_Helical_Turbine``:
   Helically pitched Cantor rotor blades paired with slanted repulsive slot
   louvers and terraced attractive stator louver pads.
4. ``Config_D_DualStator_PushPull``:
   Dual-plane upper/lower stator cage combining lower repulsive/attractive
   chiral Cantor stages with an upper attractive/overhang-push stator stage
   for amplified axial stroke and co-directional forward torque.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Literal, Sequence

import numpy as np

from execution.casimir_bem_solver import (
    BEM_TIER_STANDARD,
    ClutchSurfaceMesh,
    Geometry,
    PanelType,
    SurfacePanel,
    TrackElement,
    _panel,
)

NUM_SECTORS: int = 4
SECTOR_DEG: float = 360.0 / NUM_SECTORS  # 90.0 deg

# Exact rational N=2 middle-third Cantor radial domain [0.20, 1.10] um (span = 0.90 um):
#   Track 0 (Gen 2 inner): slot [0.30, 0.40] um (W=100 nm), tooth [0.332, 0.368] um (w=36 nm)
#   Track 1 (Gen 1 mid):   slot [0.50, 0.80] um (W=300 nm), tooth [0.596, 0.704] um (w=108 nm)
#   Track 2 (Gen 2 outer): slot [0.90, 1.00] um (W=100 nm), tooth [0.932, 0.968] um (w=36 nm)
ENGINE_R_MIN_UM: float = 0.20
ENGINE_R_MAX_UM: float = 1.10
ENGINE_W_RATIO: float = 0.36
ENGINE_TOOTH_ARC_DEG: float = 12.0
ENGINE_APERTURE_ARC_DEG: float = 42.0

# Operating axial stroke window: z_tip in [-0.100, -0.068] um (32 nm vertical stroke)
ENGINE_Z_TIP_MIN_UM: float = -0.100
ENGINE_Z_TIP_MAX_UM: float = -0.068
ENGINE_Z_TIP_MID_UM: float = -0.084
ENGINE_H_TEETH_STD_UM: float = 0.100
ENGINE_H_TEETH_DUAL_UM: float = 0.130
ENGINE_T_MEMBRANE_UM: float = 0.025
ENGINE_Z_PAD_TOP_UM: float = -0.115
ENGINE_T_PAD_UM: float = 0.110

# Fixed reference scales so E_C(z, theta) uses identical frequency nodes & channel weights
ENGINE_KAPPA_0_REF_UM_INV: float = 1.0 / 0.085
ENGINE_K_EFF_REF_UM_INV: float = 1.0 / 0.025


@dataclasses.dataclass(frozen=True)
class CantorTrackSpec:
    """Single concentric Cantor track specification in micrometres."""

    index: int
    generation: int
    r_slot_in: float
    r_slot_out: float
    r_tooth_in: float
    r_tooth_out: float
    vernier_deg: float = 0.0

    @property
    def w_slot(self) -> float:
        return self.r_slot_out - self.r_slot_in

    @property
    def w_tooth(self) -> float:
        return self.r_tooth_out - self.r_tooth_in

    @property
    def nominal_gap(self) -> float:
        return 0.5 * (self.w_slot - self.w_tooth)

    def to_track_element(self) -> TrackElement:
        return TrackElement(
            r_inner=self.r_slot_in,
            r_outer=self.r_slot_out,
            r_tooth_in=self.r_tooth_in,
            r_tooth_out=self.r_tooth_out,
        )


@dataclasses.dataclass(frozen=True)
class CurvilinearPrism:
    """Closed 6-face curvilinear cylindrical-sector hexahedron (for BEM & Blender).

    Parameterized over (u, v, w) in [0, 1]^3:
      - u: radial coordinate from r_in(v) to r_out(v)
      - v: azimuthal fraction across [phi0(w), phi1(w)]
      - w: axial fraction across [z0(v), z1(v)]
    """

    body: Literal["rotor", "stator"]
    role: str
    r0_v0: float
    r1_v0: float
    r0_v1: float
    r1_v1: float
    phi0_w0_deg: float
    phi1_w0_deg: float
    phi0_w1_deg: float
    phi1_w1_deg: float
    z0_v0: float
    z1_v0: float
    z0_v1: float
    z1_v1: float
    n_r: int = 2
    n_phi: int = 3
    n_z: int = 2
    r_edge_nm: float = 0.0

    def bounds_cyl(self) -> tuple[float, float, float, float, float, float]:
        r_min = min(self.r0_v0, self.r0_v1)
        r_max = max(self.r1_v0, self.r1_v1)
        p_min = min(self.phi0_w0_deg, self.phi0_w1_deg)
        p_max = max(self.phi1_w0_deg, self.phi1_w1_deg)
        z_min = min(self.z0_v0, self.z0_v1)
        z_max = max(self.z1_v0, self.z1_v1)
        return r_min, r_max, p_min, p_max, z_min, z_max

    def point(self, u: float, v: float, w: float) -> np.ndarray:
        """Map (u, v, w) in [0, 1]^3 with 2D EBL planform vertical-corner filleting (r_edge_nm > 0)."""
        u_eff = float(u)
        v_eff = float(v)
        if self.r_edge_nm > 0.0:
            r_edge_um = 1.0e-3 * float(self.r_edge_nm)
            dr_mid = 0.5 * ((self.r1_v0 - self.r0_v0) + (self.r1_v1 - self.r0_v1))
            r_ave = 0.25 * (self.r0_v0 + self.r1_v0 + self.r0_v1 + self.r1_v1)
            dphi_mid_rad = math.radians(
                0.5 * ((self.phi1_w0_deg - self.phi0_w0_deg) + (self.phi1_w1_deg - self.phi0_w1_deg))
            )
            ds_mid = r_ave * dphi_mid_rad
            half_a = 0.5 * dr_mid
            half_b = 0.5 * ds_mid
            rho = min(r_edge_um, 0.88 * half_a, 0.88 * half_b)
            if rho > 1.0e-9:
                xi0 = (2.0 * u_eff - 1.0) * half_a
                eta0 = (2.0 * v_eff - 1.0) * half_b
                c_xi = min(max(xi0, -(half_a - rho)), half_a - rho)
                c_eta = min(max(eta0, -(half_b - rho)), half_b - rho)
                d_xi = xi0 - c_xi
                d_eta = eta0 - c_eta
                if d_xi != 0.0 and d_eta != 0.0:
                    X = max(-1.0, min(1.0, d_xi / rho))
                    Y = max(-1.0, min(1.0, d_eta / rho))
                    xi_new = c_xi + rho * X * math.sqrt(max(0.0, 1.0 - 0.5 * Y * Y))
                    eta_new = c_eta + rho * Y * math.sqrt(max(0.0, 1.0 - 0.5 * X * X))
                    u_eff = 0.5 * (xi_new / half_a + 1.0)
                    v_eff = 0.5 * (eta_new / half_b + 1.0)

        r0 = (1.0 - v_eff) * self.r0_v0 + v_eff * self.r0_v1
        r1 = (1.0 - v_eff) * self.r1_v0 + v_eff * self.r1_v1
        if r1 <= r0 or r0 <= 0.0:
            raise ValueError(f"Invalid radial interval [{r0}, {r1}] in {self.role}.")
        r = (1.0 - u_eff) * r0 + u_eff * r1

        phi0 = (1.0 - w) * self.phi0_w0_deg + w * self.phi0_w1_deg
        phi1 = (1.0 - w) * self.phi1_w0_deg + w * self.phi1_w1_deg
        if phi1 <= phi0:
            raise ValueError(f"Invalid angular interval [{phi0}, {phi1}] in {self.role}.")
        phi_rad = math.radians((1.0 - v_eff) * phi0 + v_eff * phi1)

        z0 = (1.0 - v_eff) * self.z0_v0 + v_eff * self.z0_v1
        z1 = (1.0 - v_eff) * self.z1_v0 + v_eff * self.z1_v1
        if z1 <= z0:
            raise ValueError(f"Invalid axial interval [{z0}, {z1}] in {self.role}.")
        z = (1.0 - w) * z0 + w * z1

        return np.array([r * math.cos(phi_rad), r * math.sin(phi_rad), z], dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def canonical_cantor_n2_tracks(*, vernier: bool = False) -> tuple[CantorTrackSpec, ...]:
    """Return the exact N=2 middle-third Cantor tracks on [0.20, 1.10] um."""
    span = ENGINE_R_MAX_UM - ENGINE_R_MIN_UM  # 0.90 um
    raw_slots = (
        (0, 2, ENGINE_R_MIN_UM + span / 9.0, ENGINE_R_MIN_UM + 2.0 * span / 9.0, -2.5 if vernier else 0.0),
        (1, 1, ENGINE_R_MIN_UM + 3.0 * span / 9.0, ENGINE_R_MIN_UM + 6.0 * span / 9.0, 0.0),
        (2, 2, ENGINE_R_MIN_UM + 7.0 * span / 9.0, ENGINE_R_MIN_UM + 8.0 * span / 9.0, +2.5 if vernier else 0.0),
    )
    tracks: list[CantorTrackSpec] = []
    for idx, gen, r_in, r_out, v_deg in raw_slots:
        w_slot = r_out - r_in
        w_tooth = ENGINE_W_RATIO * w_slot
        mid = 0.5 * (r_in + r_out)
        tracks.append(
            CantorTrackSpec(
                index=idx,
                generation=gen,
                r_slot_in=round(r_in, 6),
                r_slot_out=round(r_out, 6),
                r_tooth_in=round(mid - 0.5 * w_tooth, 6),
                r_tooth_out=round(mid + 0.5 * w_tooth, 6),
                vernier_deg=v_deg,
            )
        )
    return tuple(tracks)


def _corner_graded_nodes(count: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, count + 1, dtype=np.float64)
    return 0.5 * t + 0.25 * (1.0 - np.cos(math.pi * t))


def _prism_to_panels(prism: CurvilinearPrism) -> list[SurfacePanel]:
    """Discretize all 6 boundary faces of a curvilinear prism with local outward normals."""
    panels: list[SurfacePanel] = []
    if prism.r_edge_nm > 0.0:
        nr_eff = max(int(prism.n_r), 4)
        nphi_eff = max(int(prism.n_phi), 6)
        us = _corner_graded_nodes(nr_eff)
        vs = _corner_graded_nodes(nphi_eff)
    else:
        nr_eff = int(prism.n_r)
        nphi_eff = int(prism.n_phi)
        us = np.linspace(0.0, 1.0, nr_eff + 1)
        vs = np.linspace(0.0, 1.0, nphi_eff + 1)
    nz_eff = int(prism.n_z)
    ws = np.linspace(0.0, 1.0, nz_eff + 1)

    def emit(pts: list[np.ndarray], interior_pt: np.ndarray, kind: PanelType) -> None:
        face_mid = 0.25 * (pts[0] + pts[1] + pts[2] + pts[3])
        outward_hint = face_mid - interior_pt
        norm = float(np.linalg.norm(outward_hint))
        if norm <= 1.0e-12:
            raise ValueError(f"Degenerate prism interior hint for {prism.role}.")
        panels.append(_panel(pts, outward_hint / norm, kind, prism.body))

    b_prefix = "rotor" if prism.body == "rotor" else "stator"
    t_bot: PanelType = "rotor_bottom" if b_prefix == "rotor" else "stator_bottom"
    t_top: PanelType = "rotor_top" if b_prefix == "rotor" else "stator_top"
    t_rad: PanelType = "rotor_radial_wall" if b_prefix == "rotor" else "stator_radial_wall"
    t_azi: PanelType = "rotor_azimuthal_wall" if b_prefix == "rotor" else "stator_azimuthal_wall"

    for i in range(nr_eff):
        for j in range(nphi_eff):
            u0, u1 = float(us[i]), float(us[i + 1])
            v0, v1 = float(vs[j]), float(vs[j + 1])
            um, vm = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
            mid_w = prism.point(um, vm, 0.5)
            emit(
                [prism.point(u0, v0, 0.0), prism.point(u1, v0, 0.0), prism.point(u1, v1, 0.0), prism.point(u0, v1, 0.0)],
                mid_w,
                t_bot,
            )
            emit(
                [prism.point(u0, v0, 1.0), prism.point(u1, v0, 1.0), prism.point(u1, v1, 1.0), prism.point(u0, v1, 1.0)],
                mid_w,
                t_top,
            )

    for j in range(nphi_eff):
        for k in range(nz_eff):
            v0, v1 = float(vs[j]), float(vs[j + 1])
            w0, w1 = float(ws[k]), float(ws[k + 1])
            vm, wm = 0.5 * (v0 + v1), 0.5 * (w0 + w1)
            mid_u = prism.point(0.5, vm, wm)
            emit(
                [prism.point(0.0, v0, w0), prism.point(0.0, v1, w0), prism.point(0.0, v1, w1), prism.point(0.0, v0, w1)],
                mid_u,
                t_rad,
            )
            emit(
                [prism.point(1.0, v0, w0), prism.point(1.0, v1, w0), prism.point(1.0, v1, w1), prism.point(1.0, v0, w1)],
                mid_u,
                t_rad,
            )

    for i in range(nr_eff):
        for k in range(nz_eff):
            u0, u1 = float(us[i]), float(us[i + 1])
            w0, w1 = float(ws[k]), float(ws[k + 1])
            um, wm = 0.5 * (u0 + u1), 0.5 * (w0 + w1)
            mid_v = prism.point(um, 0.5, wm)
            emit(
                [prism.point(u0, 0.0, w0), prism.point(u1, 0.0, w0), prism.point(u1, 0.0, w1), prism.point(u0, 0.0, w1)],
                mid_v,
                t_azi,
            )
            emit(
                [prism.point(u0, 1.0, w0), prism.point(u1, 1.0, w0), prism.point(u1, 1.0, w1), prism.point(u0, 1.0, w1)],
                mid_v,
                t_azi,
            )

    return panels


def certify_intra_body_disjointness(
    prisms: Sequence[CurvilinearPrism],
    *,
    min_gap_um: float = 0.006,
) -> None:
    """Verify that all prisms on the same physical body are strictly separated across C_4 sectors."""
    count = len(prisms)
    for a_idx in range(count):
        ra0, ra1, pa0, pa1, za0, za1 = prisms[a_idx].bounds_cyl()
        span_a = pa1 - pa0
        if span_a >= SECTOR_DEG or ra0 * math.radians(SECTOR_DEG - span_a) < min_gap_um:
            raise ValueError(
                f"Prism {prisms[a_idx].role!r} violates 90-degree cyclic self-clearance (span={span_a:.2f} deg)."
            )
        for b_idx in range(a_idx + 1, count):
            rb0, rb1, pb0, pb1, zb0, zb1 = prisms[b_idx].bounds_cyl()
            r_sep = max(rb0 - ra1, ra0 - rb1, 0.0)
            z_sep = max(zb0 - za1, za0 - zb1, 0.0)
            p_sep_deg = min(
                max((pb0 + SECTOR_DEG * k) - pa1, pa0 - (pb1 + SECTOR_DEG * k), 0.0)
                for k in (-1, 0, 1)
            )
            arc_sep = min(ra0, rb0) * math.radians(p_sep_deg)
            sep_3d = math.sqrt(r_sep**2 + z_sep**2 + arc_sep**2)
            if sep_3d < min_gap_um:
                raise ValueError(
                    f"Intra-body prism overlap/crowding between {prisms[a_idx].role!r} "
                    f"and {prisms[b_idx].role!r}: sep={sep_3d * 1e3:.2f} nm < {min_gap_um * 1e3:.2f} nm."
                )


def build_engine_prisms(
    design_name: str,
    *,
    z_tip_um: float = ENGINE_Z_TIP_MIN_UM,
    theta_deg: float = 18.0,
    n_r: int = BEM_TIER_STANDARD.n_r,
    n_phi_tooth: int = BEM_TIER_STANDARD.n_phi_tooth,
    n_phi_bridge: int = BEM_TIER_STANDARD.n_phi_bridge,
    n_z: int = BEM_TIER_STANDARD.n_z,
    n_phi_arc_override: int | None = None,
    r_edge_nm: float = 0.0,
) -> tuple[list[CurvilinearPrism], list[CurvilinearPrism], tuple[CantorTrackSpec, ...], float]:
    """Construct sector-0 rotor and stator curvilinear prisms for a given design."""
    if not math.isfinite(z_tip_um) or not math.isfinite(theta_deg):
        raise ValueError("z_tip_um and theta_deg must be finite.")
    if not math.isfinite(r_edge_nm) or r_edge_nm < 0.0:
        raise ValueError("r_edge_nm must be finite and nonnegative.")

    use_vernier = design_name in ("Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull")
    tracks = canonical_cantor_n2_tracks(vernier=use_vernier)
    h_teeth = ENGINE_H_TEETH_DUAL_UM if design_name == "Config_D_DualStator_PushPull" else ENGINE_H_TEETH_STD_UM
    n_phi_arc = (
        int(n_phi_arc_override)
        if n_phi_arc_override is not None
        else max(int(n_phi_bridge) * 3, 9)
    )

    rotor_prisms: list[CurvilinearPrism] = []
    stator_prisms: list[CurvilinearPrism] = []

    half_tooth = 0.5 * ENGINE_TOOTH_ARC_DEG
    helical_twist_deg = 4.5 if design_name == "Config_C_Helical_Turbine" else 0.0

    # --- 1. ROTOR TEETH (Sector 0; rotated by theta_deg + track Vernier phase) ---
    for tr in tracks:
        c_deg = theta_deg + tr.vernier_deg
        phi0_bot = c_deg - half_tooth - 0.5 * helical_twist_deg
        phi1_bot = c_deg + half_tooth - 0.5 * helical_twist_deg
        phi0_top = c_deg - half_tooth + 0.5 * helical_twist_deg
        phi1_top = c_deg + half_tooth + 0.5 * helical_twist_deg
        rotor_prisms.append(
            CurvilinearPrism(
                body="rotor",
                role=f"rotor_tooth_track{tr.index}",
                r0_v0=tr.r_tooth_in,
                r1_v0=tr.r_tooth_out,
                r0_v1=tr.r_tooth_in,
                r1_v1=tr.r_tooth_out,
                phi0_w0_deg=phi0_bot,
                phi1_w0_deg=phi1_bot,
                phi0_w1_deg=phi0_top,
                phi1_w1_deg=phi1_top,
                z0_v0=z_tip_um,
                z1_v0=z_tip_um + h_teeth,
                z0_v1=z_tip_um,
                z1_v1=z_tip_um + h_teeth,
                n_r=n_r,
                n_phi=n_phi_tooth,
                n_z=n_z,
            )
        )

    # --- 2. STATOR STRUCTURES (Sector 0: [0, 90) deg, strictly disjoint) ---
    if design_name == "Sym_Baseline_CantorN2":
        # Reflection-symmetric N=2 Cantor clutch control:
        #   - Repulsive slot aperture: phi in [2.0, 40.0] deg (center = 21.0 deg)
        #   - Attractive landing pad:  phi in [47.0, 85.0] deg (center = 66.0 deg)
        for tr in tracks:
            wall_w = 0.028 if tr.generation == 2 else 0.045
            stator_prisms.append(
                CurvilinearPrism(
                    body="stator",
                    role=f"sym_slot_inner_track{tr.index}",
                    r0_v0=tr.r_slot_in - wall_w,
                    r1_v0=tr.r_slot_in,
                    r0_v1=tr.r_slot_in - wall_w,
                    r1_v1=tr.r_slot_in,
                    phi0_w0_deg=2.0,
                    phi1_w0_deg=40.0,
                    phi0_w1_deg=2.0,
                    phi1_w1_deg=40.0,
                    z0_v0=-ENGINE_T_MEMBRANE_UM,
                    z1_v0=0.0,
                    z0_v1=-ENGINE_T_MEMBRANE_UM,
                    z1_v1=0.0,
                    n_r=n_r,
                    n_phi=n_phi_arc,
                    n_z=n_z,
                )
            )
            stator_prisms.append(
                CurvilinearPrism(
                    body="stator",
                    role=f"sym_slot_outer_track{tr.index}",
                    r0_v0=tr.r_slot_out,
                    r1_v0=tr.r_slot_out + wall_w,
                    r0_v1=tr.r_slot_out,
                    r1_v1=tr.r_slot_out + wall_w,
                    phi0_w0_deg=2.0,
                    phi1_w0_deg=40.0,
                    phi0_w1_deg=2.0,
                    phi1_w1_deg=40.0,
                    z0_v0=-ENGINE_T_MEMBRANE_UM,
                    z1_v0=0.0,
                    z0_v1=-ENGINE_T_MEMBRANE_UM,
                    z1_v1=0.0,
                    n_r=n_r,
                    n_phi=n_phi_arc,
                    n_z=n_z,
                )
            )
            stator_prisms.append(
                CurvilinearPrism(
                    body="stator",
                    role=f"sym_pad_track{tr.index}",
                    r0_v0=tr.r_slot_in,
                    r1_v0=tr.r_slot_out,
                    r0_v1=tr.r_slot_in,
                    r1_v1=tr.r_slot_out,
                    phi0_w0_deg=47.0,
                    phi1_w0_deg=85.0,
                    phi0_w1_deg=47.0,
                    phi1_w1_deg=85.0,
                    z0_v0=ENGINE_Z_PAD_TOP_UM - ENGINE_T_PAD_UM,
                    z1_v0=ENGINE_Z_PAD_TOP_UM,
                    z0_v1=ENGINE_Z_PAD_TOP_UM - ENGINE_T_PAD_UM,
                    z1_v1=ENGINE_Z_PAD_TOP_UM,
                    n_r=n_r,
                    n_phi=n_phi_arc,
                    n_z=n_z,
                )
            )

    elif design_name == "Config_B_Manhattan_Vernier":
        # 100% Manhattan vertical sidewalls (disjoint stator blocks):
        # Stroke I (phi in [2, 40] deg): Upper slot collars (z in [-0.025, +0.006] um)
        #   radially taper INWARD toward rotor tooth along +phi -> F_z > 0, tau_theta > 0.
        # Stroke III (phi in [44, 85] deg): Recessed horn-shaped Cantor landing pad
        #   (z in [-0.225, -0.115] um, expanding radially along +phi) PLUS disjoint lower
        #   cheek rails (z in [-0.106, -0.084] um, strictly above -0.115 um and strictly
        #   outside rotor tooth by >= 16 nm, below tooth midplane) -> F_z < 0, tau_theta > 0.
        for tr in tracks:
            g_entry = 0.038 if tr.generation == 2 else 0.068
            g_exit = 0.017 if tr.generation == 2 else 0.024
            wall_w = 0.028 if tr.generation == 2 else 0.045

            for suffix, r0_a, r1_a, r0_b, r1_b in (
                (
                    "in",
                    tr.r_tooth_in - g_entry - wall_w,
                    tr.r_tooth_in - g_entry,
                    tr.r_tooth_in - g_exit - wall_w,
                    tr.r_tooth_in - g_exit,
                ),
                (
                    "out",
                    tr.r_tooth_out + g_entry,
                    tr.r_tooth_out + g_entry + wall_w,
                    tr.r_tooth_out + g_exit,
                    tr.r_tooth_out + g_exit + wall_w,
                ),
            ):
                stator_prisms.append(
                    CurvilinearPrism(
                        body="stator",
                        role=f"b_rep_collar_{suffix}_track{tr.index}",
                        r0_v0=r0_a,
                        r1_v0=r1_a,
                        r0_v1=r0_b,
                        r1_v1=r1_b,
                        phi0_w0_deg=2.0,
                        phi1_w0_deg=41.5,
                        phi0_w1_deg=2.0,
                        phi1_w1_deg=41.5,
                        z0_v0=-0.018,
                        z1_v0=0.012,
                        z0_v1=-0.018,
                        z1_v1=0.012,
                        n_r=n_r,
                        n_phi=n_phi_arc,
                        n_z=n_z,
                    )
                )

            mid_r = 0.5 * (tr.r_tooth_in + tr.r_tooth_out)
            half_pad_entry = 0.16 * tr.w_tooth
            half_pad_exit = 0.62 * tr.w_tooth
            stator_prisms.append(
                CurvilinearPrism(
                    body="stator",
                    role=f"b_attr_horn_pad_track{tr.index}",
                    r0_v0=mid_r - half_pad_entry,
                    r1_v0=mid_r + half_pad_entry,
                    r0_v1=mid_r - half_pad_exit,
                    r1_v1=mid_r + half_pad_exit,
                    phi0_w0_deg=44.0,
                    phi1_w0_deg=86.5,
                    phi0_w1_deg=44.0,
                    phi1_w1_deg=86.5,
                    z0_v0=-0.225,
                    z1_v0=ENGINE_Z_PAD_TOP_UM,
                    z0_v1=-0.225,
                    z1_v1=ENGINE_Z_PAD_TOP_UM,
                    n_r=n_r,
                    n_phi=n_phi_arc,
                    n_z=n_z,
                )
            )

            g_cheek_in = 0.046 if tr.generation == 2 else 0.082
            g_cheek_out = 0.015 if tr.generation == 2 else 0.018
            for suffix, r0_a, r1_a, r0_b, r1_b in (
                (
                    "in",
                    tr.r_tooth_in - g_cheek_in - wall_w,
                    tr.r_tooth_in - g_cheek_in,
                    tr.r_tooth_in - g_cheek_out - wall_w,
                    tr.r_tooth_in - g_cheek_out,
                ),
                (
                    "out",
                    tr.r_tooth_out + g_cheek_in,
                    tr.r_tooth_out + g_cheek_in + wall_w,
                    tr.r_tooth_out + g_cheek_out,
                    tr.r_tooth_out + g_cheek_out + wall_w,
                ),
            ):
                stator_prisms.append(
                    CurvilinearPrism(
                        body="stator",
                        role=f"b_attr_cheek_{suffix}_track{tr.index}",
                        r0_v0=r0_a,
                        r1_v0=r1_a,
                        r0_v1=r0_b,
                        r1_v1=r1_b,
                        phi0_w0_deg=44.0,
                        phi1_w0_deg=86.5,
                        phi0_w1_deg=44.0,
                        phi1_w1_deg=86.5,
                        z0_v0=-0.107,
                        z1_v0=-0.072,
                        z0_v1=-0.107,
                        z1_v1=-0.072,
                        n_r=n_r,
                        n_phi=n_phi_arc,
                        n_z=n_z,
                    )
                )

    elif design_name == "Config_C_Helical_Turbine":
        # Helically twisted rotor teeth (+4.5 deg twist bottom-to-top) paired with
        # helically pitched stator louvers in both repulsive and attractive zones.
        for tr in tracks:
            g_entry = 0.038 if tr.generation == 2 else 0.068
            g_exit = 0.017 if tr.generation == 2 else 0.024
            wall_w = 0.028 if tr.generation == 2 else 0.045

            for suffix, r0_a, r1_a, r0_b, r1_b in (
                (
                    "in",
                    tr.r_tooth_in - g_entry - wall_w,
                    tr.r_tooth_in - g_entry,
                    tr.r_tooth_in - g_exit - wall_w,
                    tr.r_tooth_in - g_exit,
                ),
                (
                    "out",
                    tr.r_tooth_out + g_entry,
                    tr.r_tooth_out + g_entry + wall_w,
                    tr.r_tooth_out + g_exit,
                    tr.r_tooth_out + g_exit + wall_w,
                ),
            ):
                stator_prisms.append(
                    CurvilinearPrism(
                        body="stator",
                        role=f"c_helical_slot_{suffix}_track{tr.index}",
                        r0_v0=r0_a,
                        r1_v0=r1_a,
                        r0_v1=r0_b,
                        r1_v1=r1_b,
                        phi0_w0_deg=1.5,
                        phi1_w0_deg=37.5,
                        phi0_w1_deg=5.0,
                        phi1_w1_deg=41.0,
                        z0_v0=-0.022,
                        z1_v0=0.006,
                        z0_v1=-0.010,
                        z1_v1=0.018,
                        n_r=n_r,
                        n_phi=n_phi_arc,
                        n_z=n_z,
                    )
                )

            mid_r = 0.5 * (tr.r_tooth_in + tr.r_tooth_out)
            half_pad_entry = 0.18 * tr.w_tooth
            half_pad_exit = 0.62 * tr.w_tooth
            stator_prisms.append(
                CurvilinearPrism(
                    body="stator",
                    role=f"c_helical_pad_track{tr.index}",
                    r0_v0=mid_r - half_pad_entry,
                    r1_v0=mid_r + half_pad_entry,
                    r0_v1=mid_r - half_pad_exit,
                    r1_v1=mid_r + half_pad_exit,
                    phi0_w0_deg=44.0,
                    phi1_w0_deg=84.0,
                    phi0_w1_deg=46.5,
                    phi1_w1_deg=86.5,
                    z0_v0=-0.230,
                    z1_v0=-0.125,
                    z0_v1=-0.220,
                    z1_v1=-0.114,
                    n_r=n_r,
                    n_phi=n_phi_arc,
                    n_z=n_z,
                )
            )
            g_cheek_in = 0.044 if tr.generation == 2 else 0.076
            g_cheek_out = 0.016 if tr.generation == 2 else 0.019
            for suffix, r0_a, r1_a, r0_b, r1_b in (
                (
                    "in",
                    tr.r_tooth_in - g_cheek_in - wall_w,
                    tr.r_tooth_in - g_cheek_in,
                    tr.r_tooth_in - g_cheek_out - wall_w,
                    tr.r_tooth_in - g_cheek_out,
                ),
                (
                    "out",
                    tr.r_tooth_out + g_cheek_in,
                    tr.r_tooth_out + g_cheek_in + wall_w,
                    tr.r_tooth_out + g_cheek_out,
                    tr.r_tooth_out + g_cheek_out + wall_w,
                ),
            ):
                stator_prisms.append(
                    CurvilinearPrism(
                        body="stator",
                        role=f"c_helical_cheek_{suffix}_track{tr.index}",
                        r0_v0=r0_a,
                        r1_v0=r1_a,
                        r0_v1=r0_b,
                        r1_v1=r1_b,
                        phi0_w0_deg=44.0,
                        phi1_w0_deg=84.0,
                        phi0_w1_deg=46.5,
                        phi1_w1_deg=86.5,
                        z0_v0=-0.106,
                        z1_v0=-0.076,
                        z0_v1=-0.100,
                        z1_v1=-0.070,
                        n_r=n_r,
                        n_phi=n_phi_arc,
                        n_z=n_z,
                    )
                )

    elif design_name == "Config_D_DualStator_PushPull":
        # Dual-Stator Push-Pull Cage with 130 nm rotor teeth:
        #   Up-Stroke Zone [2, 41.5] deg: high lifting slot collar [0.012, 0.044] um +
        #     upper attractive ceiling horn pad [0.077, 0.165] um -> F_z > 0, tau_theta > 0.
        #   Down-Stroke Zone [44, 86.5] deg: low attractive cheek collar [-0.107, -0.062] um +
        #     lower attractive floor horn pad [-0.225, -0.115] um -> F_z < 0, tau_theta > 0.
        for tr in tracks:
            g_entry = 0.042 if tr.generation == 2 else 0.076
            g_exit = 0.016 if tr.generation == 2 else 0.020
            g_down_in = 0.048 if tr.generation == 2 else 0.084
            g_down_out = 0.015 if tr.generation == 2 else 0.018
            wall_w = 0.028 if tr.generation == 2 else 0.045
            mid_r = 0.5 * (tr.r_tooth_in + tr.r_tooth_out)
            half_pad_entry = 0.16 * tr.w_tooth
            half_pad_exit = 0.62 * tr.w_tooth

            for suffix, r0_a, r1_a, r0_b, r1_b, rd0_a, rd1_a, rd0_b, rd1_b in (
                (
                    "in",
                    tr.r_tooth_in - g_entry - wall_w,
                    tr.r_tooth_in - g_entry,
                    tr.r_tooth_in - g_exit - wall_w,
                    tr.r_tooth_in - g_exit,
                    tr.r_tooth_in - g_down_in - wall_w,
                    tr.r_tooth_in - g_down_in,
                    tr.r_tooth_in - g_down_out - wall_w,
                    tr.r_tooth_in - g_down_out,
                ),
                (
                    "out",
                    tr.r_tooth_out + g_entry,
                    tr.r_tooth_out + g_entry + wall_w,
                    tr.r_tooth_out + g_exit,
                    tr.r_tooth_out + g_exit + wall_w,
                    tr.r_tooth_out + g_down_in,
                    tr.r_tooth_out + g_down_in + wall_w,
                    tr.r_tooth_out + g_down_out,
                    tr.r_tooth_out + g_down_out + wall_w,
                ),
            ):
                stator_prisms.append(
                    CurvilinearPrism(
                        body="stator",
                        role=f"d_up_collar_{suffix}_track{tr.index}",
                        r0_v0=r0_a,
                        r1_v0=r1_a,
                        r0_v1=r0_b,
                        r1_v1=r1_b,
                        phi0_w0_deg=2.0,
                        phi1_w0_deg=41.5,
                        phi0_w1_deg=2.0,
                        phi1_w1_deg=41.5,
                        z0_v0=0.012,
                        z1_v0=0.044,
                        z0_v1=0.012,
                        z1_v1=0.044,
                        n_r=n_r,
                        n_phi=n_phi_arc,
                        n_z=n_z,
                    )
                )
                stator_prisms.append(
                    CurvilinearPrism(
                        body="stator",
                        role=f"d_down_collar_{suffix}_track{tr.index}",
                        r0_v0=rd0_a,
                        r1_v0=rd1_a,
                        r0_v1=rd0_b,
                        r1_v1=rd1_b,
                        phi0_w0_deg=44.0,
                        phi1_w0_deg=86.5,
                        phi0_w1_deg=44.0,
                        phi1_w1_deg=86.5,
                        z0_v0=-0.107,
                        z1_v0=-0.062,
                        z0_v1=-0.107,
                        z1_v1=-0.062,
                        n_r=n_r,
                        n_phi=n_phi_arc,
                        n_z=n_z,
                    )
                )

            stator_prisms.append(
                CurvilinearPrism(
                    body="stator",
                    role=f"d_up_ceiling_pad_track{tr.index}",
                    r0_v0=mid_r - half_pad_entry,
                    r1_v0=mid_r + half_pad_entry,
                    r0_v1=mid_r - half_pad_exit,
                    r1_v1=mid_r + half_pad_exit,
                    phi0_w0_deg=3.0,
                    phi1_w0_deg=41.5,
                    phi0_w1_deg=3.0,
                    phi1_w1_deg=41.5,
                    z0_v0=0.077,
                    z1_v0=0.165,
                    z0_v1=0.077,
                    z1_v1=0.165,
                    n_r=n_r,
                    n_phi=n_phi_arc,
                    n_z=n_z,
                )
            )
            stator_prisms.append(
                CurvilinearPrism(
                    body="stator",
                    role=f"d_down_floor_pad_track{tr.index}",
                    r0_v0=mid_r - half_pad_entry,
                    r1_v0=mid_r + half_pad_entry,
                    r0_v1=mid_r - half_pad_exit,
                    r1_v1=mid_r + half_pad_exit,
                    phi0_w0_deg=44.0,
                    phi1_w0_deg=86.5,
                    phi0_w1_deg=44.0,
                    phi1_w1_deg=86.5,
                    z0_v0=-0.225,
                    z1_v0=ENGINE_Z_PAD_TOP_UM,
                    z0_v1=-0.225,
                    z1_v1=ENGINE_Z_PAD_TOP_UM,
                    n_r=n_r,
                    n_phi=n_phi_arc,
                    n_z=n_z,
                )
            )
    else:
        raise ValueError(f"Unknown engine design {design_name!r}.")

    if r_edge_nm > 0.0:
        r_val = float(r_edge_nm)
        rotor_prisms = [dataclasses.replace(p, r_edge_nm=r_val) for p in rotor_prisms]
        stator_prisms = [dataclasses.replace(p, r_edge_nm=r_val) for p in stator_prisms]

    certify_intra_body_disjointness(rotor_prisms)
    certify_intra_body_disjointness(stator_prisms)
    return rotor_prisms, stator_prisms, tracks, h_teeth


def certify_minimum_clearance_um(
    mesh: ClutchSurfaceMesh,
    *,
    min_allowed_um: float = 0.010,
) -> float:
    """Compute minimum cross-body quadrature/vertex separation across all 4 sectors."""
    rotor_pts = np.concatenate(
        [np.asarray([p.vertices for p in mesh.rotor]).reshape(-1, 3), mesh.sector_arrays("rotor").centroids],
        axis=0,
    )
    stator_base = np.concatenate(
        [np.asarray([p.vertices for p in mesh.stator]).reshape(-1, 3), mesh.sector_arrays("stator").centroids],
        axis=0,
    )
    rot_mats = (
        np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
    )
    min_dist = math.inf
    for rmat in rot_mats:
        stator_pts = stator_base @ rmat.T
        diff = rotor_pts[:, None, :] - stator_pts[None, :, :]
        d = float(np.min(np.linalg.norm(diff, axis=2)))
        min_dist = min(min_dist, d)
    if not math.isfinite(min_dist) or min_dist < min_allowed_um:
        raise ValueError(
            f"Collision/clearance violation: min separation {min_dist * 1e3:.2f} nm "
            f"< {min_allowed_um * 1e3:.2f} nm."
        )
    return min_dist


def build_engine_surface_mesh(
    design_name: str,
    *,
    z_tip_um: float = ENGINE_Z_TIP_MIN_UM,
    theta_deg: float = 18.0,
    material: str = "Gold",
    temperature_K: float = 0.0,
    n_r: int = BEM_TIER_STANDARD.n_r,
    n_phi_tooth: int = BEM_TIER_STANDARD.n_phi_tooth,
    n_phi_bridge: int = BEM_TIER_STANDARD.n_phi_bridge,
    n_z: int = BEM_TIER_STANDARD.n_z,
    n_phi_arc_override: int | None = None,
    r_edge_nm: float = 0.0,
    min_clearance_um: float = 0.010,
) -> ClutchSurfaceMesh:
    """Build a validated ClutchSurfaceMesh for any Fractal Casimir Engine design."""
    rotor_prisms, stator_prisms, tracks, h_teeth = build_engine_prisms(
        design_name,
        z_tip_um=z_tip_um,
        theta_deg=theta_deg,
        n_r=n_r,
        n_phi_tooth=n_phi_tooth,
        n_phi_bridge=n_phi_bridge,
        n_z=n_z,
        n_phi_arc_override=n_phi_arc_override,
        r_edge_nm=r_edge_nm,
    )
    rotor_panels: list[SurfacePanel] = []
    for prism in rotor_prisms:
        rotor_panels.extend(_prism_to_panels(prism))
    stator_panels: list[SurfacePanel] = []
    for prism in stator_prisms:
        stator_panels.extend(_prism_to_panels(prism))

    geometry = Geometry(
        R_min=ENGINE_R_MIN_UM,
        R_max=ENGINE_R_MAX_UM,
        z_tip=z_tip_um,
        h_teeth=h_teeth,
        t_membrane=ENGINE_T_MEMBRANE_UM,
        t_landing_pad=ENGINE_T_PAD_UM,
        theta_deg=theta_deg,
        tooth_arc_deg=ENGINE_TOOTH_ARC_DEG,
        aperture_arc_deg=ENGINE_APERTURE_ARC_DEG,
        elements=tuple(t.to_track_element() for t in tracks),
        tooth_center_offset_deg=0.0,
    )
    parameters: dict[str, Any] = {
        "design_name": design_name,
        "dataset": "fractal_casimir_engine_cycle",
        "N_fractal": 2,
        "material": material,
        "temperature_K": temperature_K,
        "R_min": ENGINE_R_MIN_UM,
        "R_max": ENGINE_R_MAX_UM,
        "z_tip": z_tip_um,
        "h_teeth": h_teeth,
        "theta_deg": theta_deg,
        "tooth_arc_deg": ENGINE_TOOTH_ARC_DEG,
        "aperture_arc_deg": ENGINE_APERTURE_ARC_DEG,
        "r_edge_nm": float(r_edge_nm),
        "elements": [dataclasses.asdict(t.to_track_element()) for t in tracks],
    }
    resolution = {
        "n_r": int(n_r),
        "n_phi_tooth": int(n_phi_tooth),
        "n_phi_bridge": int(n_phi_bridge),
        "n_z": int(n_z),
    }
    mesh = ClutchSurfaceMesh(
        rotor=tuple(rotor_panels),
        stator=tuple(stator_panels),
        geometry=geometry,
        parameters=parameters,
        config=dict(parameters),
        panel_resolution=resolution,
    )
    min_gap = certify_minimum_clearance_um(mesh, min_allowed_um=min_clearance_um)
    mesh.parameters["certified_min_clearance_um"] = min_gap
    return mesh


def prism_to_meep_subwedges(
    prism: CurvilinearPrism,
    *,
    rot_deg: float = 0.0,
    n_v: int = 24,
    n_w_helical: int = 8,
) -> list[dict[str, Any]]:
    """Decompose a CurvilinearPrism into exact vertical right-quadrilateral sub-prisms for Meep C++.

    Each returned dict contains ``vertices_xy`` (4 CCW ``(x, y)`` tuples in um),
    ``z_min`` (um), ``z_max`` (um), ``body``, and ``role``.
    """
    has_twist_or_tilt = (
        abs(prism.phi0_w1_deg - prism.phi0_w0_deg) > 1.0e-9
        or abs(prism.phi1_w1_deg - prism.phi1_w0_deg) > 1.0e-9
        or abs(prism.z0_v1 - prism.z0_v0) > 1.0e-9
        or abs(prism.z1_v1 - prism.z1_v0) > 1.0e-9
    )
    nw = max(1, int(n_w_helical)) if has_twist_or_tilt else 1
    nv = max(2, int(n_v))
    vs = np.linspace(0.0, 1.0, nv + 1)
    ws = np.linspace(0.0, 1.0, nw + 1)

    rot_rad = math.radians(float(rot_deg))
    cr = math.cos(rot_rad)
    sr = math.sin(rot_rad)

    def rot_xy(pt3: np.ndarray) -> tuple[float, float]:
        x, y = float(pt3[0]), float(pt3[1])
        return (cr * x - sr * y, sr * x + cr * y)

    wedges: list[dict[str, Any]] = []
    for kw in range(nw):
        w0 = float(ws[kw])
        w1 = float(ws[kw + 1])
        wm = 0.5 * (w0 + w1)
        for jv in range(nv):
            v0 = float(vs[jv])
            v1 = float(vs[jv + 1])
            vm = 0.5 * (v0 + v1)
            p00 = prism.point(0.0, v0, wm)
            p10 = prism.point(1.0, v0, wm)
            p11 = prism.point(1.0, v1, wm)
            p01 = prism.point(0.0, v1, wm)
            zb = float(prism.point(0.5, vm, w0)[2])
            zt = float(prism.point(0.5, vm, w1)[2])
            if zt <= zb:
                raise ValueError(f"Degenerate axial sub-wedge [{zb}, {zt}] in {prism.role}.")
            verts_xy = [rot_xy(p00), rot_xy(p10), rot_xy(p11), rot_xy(p01)]
            # Ensure positive CCW 2D polygon area
            area2 = sum(
                verts_xy[m][0] * verts_xy[(m + 1) % 4][1] - verts_xy[(m + 1) % 4][0] * verts_xy[m][1]
                for m in range(4)
            )
            if area2 < 0.0:
                verts_xy.reverse()
            wedges.append(
                {
                    "body": prism.body,
                    "role": prism.role,
                    "vertices_xy": verts_xy,
                    "z_min": zb,
                    "z_max": zt,
                }
            )
    return wedges
