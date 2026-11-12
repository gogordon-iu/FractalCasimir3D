"""Canonical Prefractal Sector Cavity (CPSC) 3D geometry and surface-panel builder."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Literal, Sequence, Tuple

import numpy as np

ConstellationType = Literal["breathing_4_4", "vernier_6_4", "chiral_4_4"]
StagingType = Literal["coplanar", "homothetic"]
ControlType = Literal["prefractal", "periodic_grating", "flat_annulus"]


@dataclass(frozen=True)
class RadialSlotSpec:
    """Dimensionless radial slot and upper vane coordinates for one track."""

    track_index: int
    generation: int
    r_slot_in: float
    r_slot_out: float
    r_vane_in: float
    r_vane_out: float
    z_rim_bot: float
    z_rim_top: float
    z_face_top: float
    z_vane_bot: float
    z_vane_top: float

    @property
    def slot_width(self) -> float:
        return self.r_slot_out - self.r_slot_in

    @property
    def vane_width(self) -> float:
        return self.r_vane_out - self.r_vane_in

    @property
    def radial_clearance(self) -> float:
        return 0.5 * (self.slot_width - self.vane_width)

    @property
    def r_center(self) -> float:
        return 0.5 * (self.r_slot_in + self.r_slot_out)


@dataclass(frozen=True)
class CPSCSpec:
    """Complete dimensionless specification of a CPSC or matched control cavity."""

    name: str
    constellation: ConstellationType
    staging: StagingType
    geometry_kind: ControlType
    generation_n: int
    scale_b: float = 3.0
    r_in: float = 0.25
    r_out: float = 1.00
    fill_chi: float = 0.50
    tau_0: float = 0.03
    h_0: float = 0.12
    z_vane_0: float = -0.10
    d_0: float = 0.02
    z_stage_1: float = 0.27
    tau_stage_1: float = 0.054
    chiral_skew_rad: float = 0.0

    @property
    def m_up(self) -> int:
        return 6 if self.constellation == "vernier_6_4" else 4

    @property
    def m_low(self) -> int:
        return 4

    @property
    def m_gcd(self) -> int:
        return math.gcd(self.m_up, self.m_low)

    @property
    def ell_star(self) -> float:
        gen = max(self.generation_n, 1)
        return (self.r_out - self.r_in) * (self.scale_b ** (-gen))


@dataclass
class PanelBatch3D:
    """Discretized 3D surface panels for upper (body=0) or lower (body=1) assemblies."""

    centroids: np.ndarray      # (N_p, 3)
    normals: np.ndarray        # (N_p, 3)
    tangents_1: np.ndarray     # (N_p, 3)
    tangents_2: np.ndarray     # (N_p, 3)
    areas: np.ndarray          # (N_p,)
    sigma_reg: np.ndarray      # (N_p,)
    body_id: np.ndarray        # (N_p,) 0=upper, 1=lower
    generation_id: np.ndarray  # (N_p,)


def _recursive_cantor_slots(
    r_left: float,
    r_right: float,
    level: int,
    max_level: int,
    scale_b: float,
) -> List[Tuple[int, float, float]]:
    """Recursively subdivide [r_left, r_right] with retention 1/b and central slot (1 - 2/b)."""
    if level > max_level:
        return []
    span = r_right - r_left
    eta = 1.0 / scale_b
    gamma = 1.0 - 2.0 * eta
    s_in = r_left + eta * span
    s_out = s_in + gamma * span
    left_slots = _recursive_cantor_slots(r_left, s_in, level + 1, max_level, scale_b)
    right_slots = _recursive_cantor_slots(s_out, r_right, level + 1, max_level, scale_b)
    return left_slots + [(level, s_in, s_out)] + right_slots


def build_radial_tracks(
    spec: CPSCSpec,
    z_vane_override: float | None = None,
    r_scale: float = 1.0,
    freeze_slot_cutoff: bool = False,
) -> List[RadialSlotSpec]:
    """Construct dimensionless radial tracks matching Section II.B of the manuscript.

    When freeze_slot_cutoff=True (used for fixed-cutoff macroscopic dilatation D_cav at fixed ell_*),
    r_scale dilates the macroscopic annulus and track centers while holding internal slot/vane widths fixed.
    """
    if spec.scale_b <= 2.0:
        raise ValueError("Generalized symmetric Cantor requires scale_b > 2.0.")
    r_in = spec.r_in * r_scale
    r_out = spec.r_out * r_scale
    span = r_out - r_in
    z_vane_base = spec.z_vane_0 if z_vane_override is None else z_vane_override

    if spec.geometry_kind == "flat_annulus":
        return [
            RadialSlotSpec(
                track_index=0,
                generation=0,
                r_slot_in=r_in,
                r_slot_out=r_out,
                r_vane_in=r_in,
                r_vane_out=r_out,
                z_rim_bot=-spec.d_0 - spec.tau_0,
                z_rim_top=-spec.d_0,
                z_face_top=spec.z_vane_0 - spec.d_0,
                z_vane_bot=z_vane_base,
                z_vane_top=z_vane_base + spec.h_0,
            )
        ]

    base_in = spec.r_in if freeze_slot_cutoff else r_in
    base_out = spec.r_out if freeze_slot_cutoff else r_out
    base_span = base_out - base_in

    if spec.generation_n == 0:
        w_slot = base_span * (1.0 - 2.0 / spec.scale_b)
        rc = 0.5 * (base_in + base_out)
        raw_slots = [(1, rc - 0.5 * w_slot, rc + 0.5 * w_slot)]
    else:
        raw_slots = _recursive_cantor_slots(base_in, base_out, 1, spec.generation_n, spec.scale_b)

    if spec.geometry_kind == "periodic_grating":
        n_trk = len(raw_slots)
        total_slot_w = sum(so - si for _, si, so in raw_slots)
        w_unif = total_slot_w / n_trk
        pitch = base_span / n_trk
        raw_slots = [
            (
                1,
                base_in + (k + 0.5) * pitch - 0.5 * w_unif,
                base_in + (k + 0.5) * pitch + 0.5 * w_unif,
            )
            for k in range(n_trk)
        ]

    if freeze_slot_cutoff and r_scale != 1.0:
        scaled_slots = []
        for gen, s_in, s_out in raw_slots:
            rc_0 = 0.5 * (s_in + s_out)
            w_0 = s_out - s_in
            rc_new = rc_0 * r_scale
            scaled_slots.append((gen, rc_new - 0.5 * w_0, rc_new + 0.5 * w_0))
        raw_slots = scaled_slots

    tracks: List[RadialSlotSpec] = []
    for idx, (gen, s_in, s_out) in enumerate(raw_slots):
        w_s = s_out - s_in
        w_v = spec.fill_chi * w_s
        rc = 0.5 * (s_in + s_out)
        if spec.staging == "homothetic":
            scale_m = spec.scale_b ** (-(gen - 1))
            z_center = -spec.z_stage_1 * scale_m
            tau_m = spec.tau_stage_1 * scale_m
            z_rim_bot = z_center - 0.5 * tau_m
            z_rim_top = z_center + 0.5 * tau_m
            h_vane = spec.h_0 * scale_m
            z_vane_bot = z_vane_base
            z_vane_top = z_vane_base + h_vane
            z_face_top = z_rim_bot - spec.d_0 * scale_m
        else:
            z_rim_bot = -spec.tau_0
            z_rim_top = 0.0
            z_vane_bot = z_vane_base
            z_vane_top = z_vane_base + spec.h_0
            z_face_top = -(spec.h_0 - abs(spec.z_vane_0)) - abs(spec.z_vane_0) - spec.d_0
            # At baseline z_vane_0 = -0.10, d_0 = 0.02 -> z_face_top = -0.12
            z_face_top = spec.z_vane_0 - spec.d_0

        tracks.append(
            RadialSlotSpec(
                track_index=idx,
                generation=gen,
                r_slot_in=s_in,
                r_slot_out=s_out,
                r_vane_in=rc - 0.5 * w_v,
                r_vane_out=rc + 0.5 * w_v,
                z_rim_bot=z_rim_bot,
                z_rim_top=z_rim_top,
                z_face_top=z_face_top,
                z_vane_bot=z_vane_bot,
                z_vane_top=z_vane_top,
            )
        )
    return tracks


def _append_cyl_patch(
    panels: List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, int, int]],
    kind: str,
    r_val_or_bounds: Tuple[float, float] | float,
    phi_bounds: Tuple[float, float],
    z_val_or_bounds: Tuple[float, float] | float,
    normal_sign: float,
    n_1: int,
    n_2: int,
    body: int,
    gen: int,
) -> None:
    """Append discretized cylindrical-polar surface patches (horizontalz, radial-wall, or phi-wall)."""
    phi_a, phi_b = phi_bounds
    if kind == "horiz":
        r_a, r_b = r_val_or_bounds  # type: ignore[misc]
        z_0 = float(z_val_or_bounds)  # type: ignore[arg-type]
        r_edges = np.linspace(r_a, r_b, n_1 + 1)
        p_edges = np.linspace(phi_a, phi_b, n_2 + 1)
        for i in range(n_1):
            rm = 0.5 * (r_edges[i] + r_edges[i + 1])
            dr = r_edges[i + 1] - r_edges[i]
            for j in range(n_2):
                pm = 0.5 * (p_edges[j] + p_edges[j + 1])
                dp = p_edges[j + 1] - p_edges[j]
                area = rm * dr * dp
                c = np.array([rm * math.cos(pm), rm * math.sin(pm), z_0])
                n = np.array([0.0, 0.0, normal_sign])
                t1 = np.array([math.cos(pm), math.sin(pm), 0.0])
                t2 = np.cross(n, t1)
                panels.append((c, n, t1, t2, area, body, gen))
    elif kind == "radial":
        r_0 = float(r_val_or_bounds)  # type: ignore[arg-type]
        z_a, z_b = z_val_or_bounds  # type: ignore[misc]
        p_edges = np.linspace(phi_a, phi_b, n_1 + 1)
        z_edges = np.linspace(z_a, z_b, n_2 + 1)
        for i in range(n_1):
            pm = 0.5 * (p_edges[i] + p_edges[i + 1])
            dp = p_edges[i + 1] - p_edges[i]
            for j in range(n_2):
                zm = 0.5 * (z_edges[j] + z_edges[j + 1])
                dz = z_edges[j + 1] - z_edges[j]
                area = r_0 * dp * dz
                c = np.array([r_0 * math.cos(pm), r_0 * math.sin(pm), zm])
                n = normal_sign * np.array([math.cos(pm), math.sin(pm), 0.0])
                t1 = np.array([-math.sin(pm), math.cos(pm), 0.0])
                t2 = np.cross(n, t1)
                panels.append((c, n, t1, t2, area, body, gen))
    elif kind == "azimuthal":
        r_a, r_b = r_val_or_bounds  # type: ignore[misc]
        z_a, z_b = z_val_or_bounds  # type: ignore[misc]
        p_0 = phi_a
        r_edges = np.linspace(r_a, r_b, n_1 + 1)
        z_edges = np.linspace(z_a, z_b, n_2 + 1)
        for i in range(n_1):
            rm = 0.5 * (r_edges[i] + r_edges[i + 1])
            dr = r_edges[i + 1] - r_edges[i]
            for j in range(n_2):
                zm = 0.5 * (z_edges[j] + z_edges[j + 1])
                dz = z_edges[j + 1] - z_edges[j]
                area = dr * dz
                c = np.array([rm * math.cos(p_0), rm * math.sin(p_0), zm])
                n = normal_sign * np.array([-math.sin(p_0), math.cos(p_0), 0.0])
                t1 = np.array([math.cos(p_0), math.sin(p_0), 0.0])
                t2 = np.cross(n, t1)
                panels.append((c, n, t1, t2, area, body, gen))


def build_cpsc_mesh(
    spec: CPSCSpec,
    theta_rad: float,
    z_vane_override: float | None = None,
    r_scale: float = 1.0,
    freeze_slot_cutoff: bool = False,
    n_rad: int = 2,
    n_phi: int = 3,
    n_z: int = 2,
    fundamental_sector_only: bool = True,
) -> PanelBatch3D:
    """Build surface-panel discretization for CPSC (fundamental gcd sector or full 2*pi ring)."""
    tracks = build_radial_tracks(
        spec,
        z_vane_override=z_vane_override,
        r_scale=r_scale,
        freeze_slot_cutoff=freeze_slot_cutoff,
    )
    panels: List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, int, int]] = []

    m_gcd = spec.m_gcd if fundamental_sector_only else 1
    up_sectors_per_block = spec.m_up // m_gcd
    low_sectors_per_block = spec.m_low // m_gcd

    if spec.geometry_kind == "flat_annulus":
        trk = tracks[0]
        phi_span = 2.0 * math.pi / m_gcd
        _append_cyl_patch(
            panels, "horiz", (trk.r_vane_in, trk.r_vane_out), (0.0, phi_span),
            trk.z_vane_bot, -1.0, n_rad * 3, n_phi * 4, body=0, gen=0,
        )
        _append_cyl_patch(
            panels, "horiz", (trk.r_slot_in, trk.r_slot_out), (0.0, phi_span),
            trk.z_face_top, +1.0, n_rad * 3, n_phi * 4, body=1, gen=0,
        )
    else:
        dphi_up_period = 2.0 * math.pi / spec.m_up
        vane_arc = 0.28 * dphi_up_period
        dphi_low_period = 2.0 * math.pi / spec.m_low
        open_arc = 0.52 * dphi_low_period
        face_arc = dphi_low_period - open_arc

        # Upper movable vanes (centered at theta_rad + s * dphi_up_period)
        for trk in tracks:
            for s in range(up_sectors_per_block):
                p_center = theta_rad + s * dphi_up_period
                pa = p_center - 0.5 * vane_arc
                pb = p_center + 0.5 * vane_arc
                _append_cyl_patch(
                    panels, "horiz", (trk.r_vane_in, trk.r_vane_out), (pa, pb),
                    trk.z_vane_bot, -1.0, n_rad, n_phi, body=0, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "horiz", (trk.r_vane_in, trk.r_vane_out), (pa, pb),
                    trk.z_vane_top, +1.0, n_rad, n_phi, body=0, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "radial", trk.r_vane_in, (pa, pb),
                    (trk.z_vane_bot, trk.z_vane_top), -1.0, n_phi, n_z, body=0, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "radial", trk.r_vane_out, (pa, pb),
                    (trk.z_vane_bot, trk.z_vane_top), +1.0, n_phi, n_z, body=0, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "azimuthal", (trk.r_vane_in, trk.r_vane_out), (pa, pa),
                    (trk.z_vane_bot, trk.z_vane_top), -1.0, n_rad, n_z, body=0, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "azimuthal", (trk.r_vane_in, trk.r_vane_out), (pb, pb),
                    (trk.z_vane_bot, trk.z_vane_top), +1.0, n_rad, n_z, body=0, gen=trk.generation,
                )

        # Lower stationary aperture sidewalls + facing sectors
        for trk in tracks:
            skew = spec.chiral_skew_rad * ((-1.0) ** trk.generation)
            for s in range(low_sectors_per_block):
                p_open_c = s * dphi_low_period + skew
                p_oa = p_open_c - 0.5 * open_arc
                p_ob = p_open_c + 0.5 * open_arc
                # Aperture radial sidewalls facing inward toward the open slot
                _append_cyl_patch(
                    panels, "radial", trk.r_slot_in, (p_oa, p_ob),
                    (trk.z_rim_bot, trk.z_rim_top), +1.0, n_phi, max(1, n_z - 1), body=1, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "radial", trk.r_slot_out, (p_oa, p_ob),
                    (trk.z_rim_bot, trk.z_rim_top), -1.0, n_phi, max(1, n_z - 1), body=1, gen=trk.generation,
                )
                # Rim top/bottom collars flanking the open slot
                rim_w = 0.22 * trk.slot_width
                _append_cyl_patch(
                    panels, "horiz", (max(0.05, trk.r_slot_in - rim_w), trk.r_slot_in), (p_oa, p_ob),
                    trk.z_rim_top, +1.0, 1, n_phi, body=1, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "horiz", (trk.r_slot_out, trk.r_slot_out + rim_w), (p_oa, p_ob),
                    trk.z_rim_top, +1.0, 1, n_phi, body=1, gen=trk.generation,
                )
                # Azimuthal aperture end-walls (chiral bevel shifts asymmetry when chiral_skew_rad != 0)
                _append_cyl_patch(
                    panels, "azimuthal", (trk.r_slot_in, trk.r_slot_out), (p_oa, p_oa),
                    (trk.z_rim_bot, trk.z_rim_top), +1.0, n_rad, 1, body=1, gen=trk.generation,
                )
                _append_cyl_patch(
                    panels, "azimuthal", (trk.r_slot_in, trk.r_slot_out), (p_ob, p_ob),
                    (trk.z_rim_bot, trk.z_rim_top), -1.0, n_rad, 1, body=1, gen=trk.generation,
                )
                # Lower facing sector centered at (s + 0.5) * dphi_low_period
                p_face_c = (s + 0.5) * dphi_low_period
                p_fa = p_face_c - 0.5 * face_arc
                p_fb = p_face_c + 0.5 * face_arc
                _append_cyl_patch(
                    panels, "horiz", (trk.r_slot_in, trk.r_slot_out), (p_fa, p_fb),
                    trk.z_face_top, +1.0, n_rad, n_phi, body=1, gen=trk.generation,
                )

    centroids = np.array([p[0] for p in panels], dtype=np.float64)
    normals = np.array([p[1] for p in panels], dtype=np.float64)
    t1 = np.array([p[2] for p in panels], dtype=np.float64)
    t2 = np.array([p[3] for p in panels], dtype=np.float64)
    areas = np.array([p[4] for p in panels], dtype=np.float64)
    sigma_reg = np.sqrt(areas / (16.0 * math.pi))
    body_id = np.array([p[5] for p in panels], dtype=np.int64)
    gen_id = np.array([p[6] for p in panels], dtype=np.int64)
    return PanelBatch3D(
        centroids=centroids,
        normals=normals,
        tangents_1=t1,
        tangents_2=t2,
        areas=areas,
        sigma_reg=sigma_reg,
        body_id=body_id,
        generation_id=gen_id,
    )


def verify_rigid_quadrupole_moment(
    spec: CPSCSpec,
    theta_rad: float = 0.123,
) -> Tuple[float, float]:
    """Compute exact normalized l=2, m=2 mass quadrupole amplitude of rigid upper and lower bodies."""
    full_mesh = build_cpsc_mesh(spec, theta_rad=theta_rad, fundamental_sector_only=False)
    x, y = full_mesh.centroids[:, 0], full_mesh.centroids[:, 1]
    q_complex = full_mesh.areas * ((x**2 - y**2) + 2.0j * x * y)
    mask_u = full_mesh.body_id == 0
    mask_l = full_mesh.body_id == 1
    norm_u = max(float(np.sum(full_mesh.areas[mask_u] * (x[mask_u] ** 2 + y[mask_u] ** 2))), 1.0e-15)
    norm_l = max(float(np.sum(full_mesh.areas[mask_l] * (x[mask_l] ** 2 + y[mask_l] ** 2))), 1.0e-15)
    return float(np.abs(np.sum(q_complex[mask_u])) / norm_u), float(np.abs(np.sum(q_complex[mask_l])) / norm_l)


def _periodic_angular_distance(phi: np.ndarray, center: float, period: float) -> np.ndarray:
    """Minimal angular distance modulo azimuthal sector period."""
    half = 0.5 * period
    return np.abs(((phi - center + half) % period) - half)


def is_inside_cpsc_conductor(
    spec: CPSCSpec,
    theta_rad: float,
    points: np.ndarray,
    z_vane_override: float | None = None,
    margin: float = 0.0,
) -> np.ndarray:
    """Return boolean mask (N,) True where 3D points fall inside solid PEC conductor bulk."""
    pts = np.asarray(points, dtype=np.float64)
    r = np.hypot(pts[:, 0], pts[:, 1])
    phi = np.arctan2(pts[:, 1], pts[:, 0])
    z = pts[:, 2]
    inside = np.zeros(len(pts), dtype=bool)
    tracks = build_radial_tracks(spec, z_vane_override=z_vane_override)

    if spec.geometry_kind == "flat_annulus":
        trk = tracks[0]
        in_u = (
            (r >= trk.r_vane_in - margin)
            & (r <= trk.r_vane_out + margin)
            & (z >= trk.z_vane_bot - margin)
            & (z <= trk.z_vane_top + margin)
        )
        in_l = (
            (r >= trk.r_slot_in - margin)
            & (r <= trk.r_slot_out + margin)
            & (z >= trk.z_face_top - spec.tau_0 - margin)
            & (z <= trk.z_face_top + margin)
        )
        return in_u | in_l

    dphi_up = 2.0 * math.pi / spec.m_up
    half_vane = 0.5 * 0.28 * dphi_up
    dphi_low = 2.0 * math.pi / spec.m_low
    half_open = 0.5 * 0.52 * dphi_low
    half_face = 0.5 * (dphi_low - 0.52 * dphi_low)

    ang_u = _periodic_angular_distance(phi, theta_rad, dphi_up) <= (half_vane + margin / np.maximum(r, 0.05))
    ang_f = _periodic_angular_distance(phi, 0.5 * dphi_low, dphi_low) <= (half_face + margin / np.maximum(r, 0.05))

    for trk in tracks:
        in_vane = (
            ang_u
            & (r >= trk.r_vane_in - margin)
            & (r <= trk.r_vane_out + margin)
            & (z >= trk.z_vane_bot - margin)
            & (z <= trk.z_vane_top + margin)
        )
        in_face = (
            ang_f
            & (r >= trk.r_slot_in - margin)
            & (r <= trk.r_slot_out + margin)
            & (z >= trk.z_face_top - spec.tau_0 - margin)
            & (z <= trk.z_face_top + margin)
        )
        skew = spec.chiral_skew_rad * ((-1.0) ** trk.generation)
        ang_o = _periodic_angular_distance(phi, skew, dphi_low) <= (half_open + margin / np.maximum(r, 0.05))
        rim_w = 0.22 * trk.slot_width
        in_rim = (
            ang_o
            & (z >= trk.z_rim_bot - margin)
            & (z <= trk.z_rim_top + margin)
            & (
                ((r >= max(0.05, trk.r_slot_in - rim_w) - margin) & (r <= trk.r_slot_in + margin))
                | ((r >= trk.r_slot_out - margin) & (r <= trk.r_slot_out + rim_w + margin))
            )
        )
        inside |= in_vane | in_face | in_rim

    return inside
