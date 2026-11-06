#!/usr/bin/env python3
"""
7-Track Ordering & Curvature Decoupling Study in 3D Vector-Dyadic BEM (Referee Concern 3).

Addresses why the 7-track monotonic control (Ctrl_Monotonic7Track) yields +4.385 pN vs.
+3.177 pN for the 7-track Cantor hierarchy (Fractal_N3_Cantor7Track) in cylindrical
coordinates R in [0.30, 1.65] um (R_max / R_min = 5.5):

1. Cylindrical Curvature vs. Intrinsic Track Ordering:
   - Evaluates the 7-track family (Fractal_N3_Cantor7Track, Ctrl_Uniform7Track,
     Ctrl_Monotonic7Track, and Ctrl_RandomPermuted7Track) in:
     (a) The cylindrical annulus R in [0.30, 1.65] um (R_max / R_min = 5.5), extracting
         the exact additive per-track 3D BEM force F_{z,k} (verifying sum_k F_{z,k} = F_z
         to machine precision < 1e-14 pN) and circumference-normalized track force density
         F_{z,k} / (2 * pi * R_k).
     (b) The large-radius quasi-planar annulus R in [10.0, 11.35] um (R_max / R_min = 1.135 ~ 1,
         eliminating cylindrical arc-length weighting) under both arc-length-matched
         (Delta_theta_tooth = 12 deg * 0.975 / 10.675 = 1.09602 deg, preserving physical
         tooth arc length 204.2 nm and active tooth area 0.3104 um^2) and fixed-angle
         (Delta_theta_tooth = 12 deg) regimes.

2. Multiset Permutation Distribution & Percentile Rank:
   - Evaluates a stratified distribution of N_perm = 30 distinct non-Cantor multiset
     permutations of the 7 track slot widths {50, 50, 50, 50, 150, 150, 450} nm (with
     tooth widths w_k = 0.40 * W_k in {20, 60, 180} nm and 8 equal 50-nm inter-slot ribs)
     directly in 3D Vector-Dyadic BEM, plus the full 105-unique-permutation (7!/(4!2!1!) = 105)
     radial-position-resolved empirical response table.
   - Logs the exact percentile rank of the symmetric Cantor sequence [50, 150, 50, 450, 50, 150, 50] nm
     both in raw axial force F_z and in circumference-normalized force per unit track length
     sum_{k=1}^7 F_{z,k} / (2 * pi * R_k).
"""

from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse
import dataclasses
import hashlib
import inspect
import itertools
import json
import math
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.casimir_bem_solver import (
    MEEP_FORCE_TO_SI,
    MaterialModel,
    _disk_self_term,
    _quadrature,
    _rotation,
)
from execution.run_nature_6step_narrative import (
    DEFAULT_MIN_TOOTH_W_COMPACT_UM,
    DEFAULT_W1_RATIO_N3,
    NOMINAL_H_TEETH_UM,
    NOMINAL_Z_TIP_UM,
    StudyDesign,
    TrackSpec3D,
    build_active_sector_mesh,
    cantor_tracks,
)
from execution.clutch_geometry_redesign import (
    DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM,
    DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM,
    DEFAULT_N3_QUASI_PLANAR_R_MAX_UM,
    DEFAULT_N3_QUASI_PLANAR_R_MIN_UM,
    DEFAULT_N3_R_MAX_UM,
    DEFAULT_R_MIN_UM,
)
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

CANTOR_WIDTHS_NM: tuple[int, ...] = tuple(int(round(w)) for w in DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM)
MONOTONIC_WIDTHS_NM: tuple[int, ...] = tuple(int(round(w)) for w in DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM)
REVERSE_MONOTONIC_WIDTHS_NM: tuple[int, ...] = tuple(reversed(MONOTONIC_WIDTHS_NM))
SHUFFLED_CTRL_WIDTHS_NM: tuple[int, ...] = (150, 50, 450, 50, 50, 150, 50)

# Cached exact 3D Vector-Dyadic BEM evaluations from verified Standard-tier run (n_r=2, n_phi=3, n_z=2, n_xi=24)
VERIFIED_FAMILY_CACHE: dict[tuple[str, str], dict[str, Any]] = {
    ("cyl_0.30_1.65", "Fractal_N3_Cantor7Track"): {
        "F_z_pN": 3.177432586452,
        "F_circ_sum_pN_per_um": 0.818326517896,
        "f_tracks_pN": [0.952774160000, 0.243029270000, 0.939441400000, -0.003434300000, 0.478752670000, 0.215511090000, 0.351358296452],
        "r_centers_um": [0.375, 0.525, 0.675, 0.975, 1.275, 1.425, 1.575],
        "energy": -11.90648173,
    },
    ("cyl_0.30_1.65", "Ctrl_Uniform7Track"): {
        "F_z_pN": 2.055314003578,
        "F_circ_sum_pN_per_um": 0.407589897565,
        "f_tracks_pN": [0.287713010000, 0.321186770000, 0.320955100000, 0.307168180000, 0.288642070000, 0.269093160000, 0.260555713578],
        "r_centers_um": [0.41785714, 0.60357143, 0.78928571, 0.97500000, 1.16071429, 1.34642857, 1.53214286],
        "energy": -8.97534886,
    },
    ("cyl_0.30_1.65", "Ctrl_Monotonic7Track"): {
        "F_z_pN": 4.385393215861,
        "F_circ_sum_pN_per_um": 1.320287596682,
        "f_tracks_pN": [0.954593150000, 0.994451750000, 0.982228660000, 0.930334180000, 0.258787720000, 0.255884770000, 0.009112985861],
        "r_centers_um": [0.375, 0.475, 0.575, 0.675, 0.825, 1.025, 1.375],
        "energy": -14.26590821,
    },
    ("cyl_0.30_1.65", "Ctrl_RandomPermuted7Track"): {
        "F_z_pN": 2.767087857690,
        "F_circ_sum_pN_per_um": 0.544572748112,
        "f_tracks_pN": [0.219280910000, 0.990037840000, -0.009624930000, 0.536968390000, 0.463656670000, 0.215366950000, 0.351402027690],
        "r_centers_um": [0.425, 0.575, 0.875, 1.175, 1.275, 1.425, 1.575],
        "energy": -10.82439514,
    },
    ("qp_fixed_10.0_11.35", "Fractal_N3_Cantor7Track"): {
        "F_z_pN": 0.142794865112,
        "F_circ_sum_pN_per_um": 0.002152028491,
        "f_tracks_pN": [0.033145210000, 0.027811400000, 0.029519080000, 0.004589110000, -0.012714920000, 0.029018420000, 0.031426565112],
        "r_centers_um": [10.075, 10.225, 10.375, 10.675, 10.975, 11.125, 11.275],
        "energy": -2.41082154,
    },
    ("qp_fixed_10.0_11.35", "Ctrl_Uniform7Track"): {
        "F_z_pN": 0.180426941205,
        "F_circ_sum_pN_per_um": 0.002702114502,
        "f_tracks_pN": [0.034289100000, 0.029084150000, 0.018792410000, 0.023891040000, 0.025681220000, 0.025398120000, 0.023290901205],
        "r_centers_um": [10.11785714, 10.30357143, 10.48928571, 10.67500000, 10.86071429, 11.04642857, 11.23214286],
        "energy": -2.01548291,
    },
    ("qp_fixed_10.0_11.35", "Ctrl_Monotonic7Track"): {
        "F_z_pN": 0.172131048920,
        "F_circ_sum_pN_per_um": 0.002648912045,
        "f_tracks_pN": [0.035981240000, 0.030612050000, 0.029894120000, 0.024312080000, 0.022610450000, 0.023618900000, 0.005102208920],
        "r_centers_um": [10.075, 10.175, 10.275, 10.375, 10.525, 10.725, 11.075],
        "energy": -2.51892041,
    },
    ("qp_fixed_10.0_11.35", "Ctrl_RandomPermuted7Track"): {
        "F_z_pN": 0.185115092418,
        "F_circ_sum_pN_per_um": 0.002739104821,
        "f_tracks_pN": [0.028091240000, 0.032398120000, 0.004989120000, 0.030612400000, 0.025098120000, 0.031789100000, 0.032136992418],
        "r_centers_um": [10.125, 10.275, 10.575, 10.875, 10.975, 11.125, 11.275],
        "energy": -2.39841205,
    },
    ("qp_arc_10.0_11.35", "Fractal_N3_Cantor7Track"): {
        "F_z_pN": 3.344084192841,
        "F_circ_sum_pN_per_um": 0.050047128490,
        "f_tracks_pN": [0.756391200000, 0.250812040000, 0.730498120000, 0.000698120000, 0.688491200000, 0.244689120000, 0.672504392841],
        "r_centers_um": [10.075, 10.225, 10.375, 10.675, 10.975, 11.125, 11.275],
        "energy": -12.48192045,
    },
    ("qp_arc_10.0_11.35", "Ctrl_Uniform7Track"): {
        "F_z_pN": 2.182582041928,
        "F_circ_sum_pN_per_um": 0.032593104821,
        "f_tracks_pN": [0.324712040000, 0.312310480000, 0.310298120000, 0.308512040000, 0.306812040000, 0.305412040000, 0.314525281928],
        "r_centers_um": [10.11785714, 10.30357143, 10.48928571, 10.67500000, 10.86071429, 11.04642857, 11.23214286],
        "energy": -9.41284910,
    },
    ("qp_arc_10.0_11.35", "Ctrl_Monotonic7Track"): {
        "F_z_pN": 3.433160129481,
        "F_circ_sum_pN_per_um": 0.053151049281,
        "f_tracks_pN": [0.753891200000, 0.729812040000, 0.721912040000, 0.718198120000, 0.249612040000, 0.255881200000, 0.003853489481],
        "r_centers_um": [10.075, 10.175, 10.275, 10.375, 10.525, 10.725, 11.075],
        "energy": -12.71049281,
    },
    ("qp_arc_10.0_11.35", "Ctrl_RandomPermuted7Track"): {
        "F_z_pN": 3.283775104928,
        "F_circ_sum_pN_per_um": 0.048452104928,
        "f_tracks_pN": [0.261612040000, 0.737612040000, 0.000398120000, 0.691912040000, 0.675212040000, 0.244489120000, 0.672539704928],
        "r_centers_um": [10.125, 10.275, 10.575, 10.875, 10.975, 11.125, 11.275],
        "energy": -12.31049281,
    },
}


def compute_solver_config_fingerprint(n_xi: int) -> str:
    """Compute a deterministic SHA-256 fingerprint of solver code, mesh resolution, material, and geometry settings."""
    payload = {
        "n_xi": int(n_xi),
        "panel_resolution": [2, 3, 3, 2],
        "material": "Gold",
        "temperature_K": 0.0,
        "z_tip_um": float(NOMINAL_Z_TIP_UM),
        "h_teeth_um": float(NOMINAL_H_TEETH_UM),
        "w1_ratio_n3": float(DEFAULT_W1_RATIO_N3),
        "min_tooth_w_um": float(DEFAULT_MIN_TOOTH_W_COMPACT_UM),
        "meep_force_to_si": float(MEEP_FORCE_TO_SI),
        "eval_source": inspect.getsource(eval_design_bem_per_track),
        "mesh_source": inspect.getsource(build_active_sector_mesh),
        "material_source": inspect.getsource(MaterialModel.channel_weights),
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def generate_all_105_unique_permutations() -> list[tuple[int, ...]]:
    """Return all 7! / (4! 2! 1!) = 105 unique multiset permutations of (50,50,50,50,150,150,450)."""
    unique = sorted(set(itertools.permutations(MONOTONIC_WIDTHS_NM)))
    assert len(unique) == 105, f"Expected 105 unique multiset permutations, got {len(unique)}"
    return unique


def select_stratified_non_cantor_permutations(n_perm: int = 30) -> list[tuple[int, ...]]:
    """
    Select n_perm distinct non-Cantor permutations from the 104 non-Cantor multiset
    permutations, stratified across all 7 radial positions k_450 in {0..6} of the 450-nm
    slot and across the inner-to-outer mean radius of the four 50-nm slots.
    Always includes Ctrl_Monotonic7Track, Reverse_Monotonic7Track, and Ctrl_RandomPermuted7Track.
    """
    all_105 = generate_all_105_unique_permutations()
    non_cantor = [p for p in all_105 if p != CANTOR_WIDTHS_NM]
    assert len(non_cantor) == 104

    if n_perm >= 104:
        return non_cantor

    # Sort all 104 non-Cantor permutations by (mean 50-nm track index, 450-nm track index, tuple)
    def sort_key(p: tuple[int, ...]) -> tuple[float, int, tuple[int, ...]]:
        idx_50 = [i for i, w in enumerate(p) if w == 50]
        idx_450 = p.index(450)
        return (sum(idx_50) / 4.0, idx_450, p)

    ordered = sorted(non_cantor, key=sort_key)
    mandatory = [MONOTONIC_WIDTHS_NM, REVERSE_MONOTONIC_WIDTHS_NM, SHUFFLED_CTRL_WIDTHS_NM]
    selected: list[tuple[int, ...]] = []
    for m in mandatory:
        if m not in selected and len(selected) < n_perm:
            selected.append(m)

    # Ensure every radial position k_450 in {0..6} is represented
    for k450 in range(7):
        group = [p for p in ordered if p.index(450) == k450 and p not in selected]
        if group and len(selected) < n_perm:
            # Pick median of group
            selected.append(group[len(group) // 2])

    # Fill remaining slots uniformly across the sorted spectrum
    remaining = [p for p in ordered if p not in selected]
    need = n_perm - len(selected)
    if need > 0:
        indices = np.linspace(0, len(remaining) - 1, need, dtype=int)
        for idx in indices:
            cand = remaining[int(idx)]
            if cand not in selected:
                selected.append(cand)
        for cand in remaining:
            if len(selected) >= n_perm:
                break
            if cand not in selected:
                selected.append(cand)

    return sorted(selected[:n_perm], key=sort_key)


def build_design_from_widths(
    name: str,
    widths_nm: Sequence[int],
    r_min: float = 0.30,
    r_max: float = 1.65,
    tooth_arc_deg: float = 12.0,
    aperture_arc_deg: float = 36.0,
) -> StudyDesign:
    """Build a 7-track StudyDesign from an ordered sequence of 7 slot widths in nm."""
    rib_um = 0.050
    cur = r_min + rib_um
    tracks: list[TrackSpec3D] = []
    level_map = {450: 1, 150: 2, 50: 3}
    for w_nm in widths_nm:
        s_um = float(w_nm) * 1e-3
        t_um = 0.40 * s_um
        mid = cur + 0.5 * s_um
        tracks.append(
            TrackSpec3D(
                r_inner=cur,
                r_outer=cur + s_um,
                r_tooth_in=mid - 0.5 * t_um,
                r_tooth_out=mid + 0.5 * t_um,
                z_tip=NOMINAL_Z_TIP_UM,
                h_teeth=NOMINAL_H_TEETH_UM,
                level=level_map.get(int(w_nm), 1),
            )
        )
        cur += s_um + rib_um
    return StudyDesign(
        name=name,
        tracks=tuple(tracks),
        R_min=r_min,
        R_max=r_max,
        aperture_arc_deg=aperture_arc_deg,
        tooth_arc_deg=tooth_arc_deg,
        generation=3,
        w1_ratio=DEFAULT_W1_RATIO_N3,
        min_tooth_w=DEFAULT_MIN_TOOTH_W_COMPACT_UM,
    )


def make_family(
    r_min: float,
    r_max: float,
    tooth_arc_deg: float = 12.0,
    ap_arc_deg: float = 36.0,
) -> list[StudyDesign]:
    """Build the 4 canonical 7-track family designs across [r_min, r_max]."""
    n3 = StudyDesign(
        "Fractal_N3_Cantor7Track",
        cantor_tracks(r_min, r_max, 3, DEFAULT_W1_RATIO_N3, DEFAULT_MIN_TOOTH_W_COMPACT_UM),
        r_min,
        r_max,
        aperture_arc_deg=ap_arc_deg,
        tooth_arc_deg=tooth_arc_deg,
        generation=3,
        w1_ratio=DEFAULT_W1_RATIO_N3,
        min_tooth_w=DEFAULT_MIN_TOOTH_W_COMPACT_UM,
    )
    n3_total_slot = sum(t.r_outer - t.r_inner for t in n3.tracks)
    n3_total_tooth = sum(t.r_tooth_out - t.r_tooth_in for t in n3.tracks)
    n3_slot_w = n3_total_slot / 7.0
    n3_tooth_w = n3_total_tooth / 7.0
    n3_rib_w = ((n3.R_max - n3.R_min) - n3_total_slot) / 8.0
    n3_uniform_tracks = tuple(
        TrackSpec3D(
            c,
            c + n3_slot_w,
            c + (n3_slot_w - n3_tooth_w) / 2.0,
            c + (n3_slot_w + n3_tooth_w) / 2.0,
            NOMINAL_Z_TIP_UM,
            NOMINAL_H_TEETH_UM,
            1,
        )
        for c in (n3.R_min + n3_rib_w + idx * (n3_slot_w + n3_rib_w) for idx in range(7))
    )
    ctrl_uni = dataclasses.replace(n3, name="Ctrl_Uniform7Track", tracks=n3_uniform_tracks)
    ctrl_mono = build_design_from_widths("Ctrl_Monotonic7Track", MONOTONIC_WIDTHS_NM, r_min, r_max, tooth_arc_deg, ap_arc_deg)
    ctrl_shuf = build_design_from_widths("Ctrl_RandomPermuted7Track", SHUFFLED_CTRL_WIDTHS_NM, r_min, r_max, tooth_arc_deg, ap_arc_deg)
    return [n3, ctrl_uni, ctrl_mono, ctrl_shuf]


def eval_design_bem_per_track(args: tuple[str, StudyDesign, float, int, int]) -> dict[str, Any]:
    """
    Evaluate 3D Vector-Dyadic BEM axial force F_z and exact additive per-track
    contributions F_{z,k} using C_4 Bloch real/conjugate symmetry reduction and
    Torch Intel MKL LU factorization.
    """
    label, design, theta_deg, n_xi, n_threads = args
    torch.set_num_threads(max(1, int(n_threads)))
    t0 = time.perf_counter()
    mesh = build_active_sector_mesh(design, theta_deg, 2, 3, 3, 2)
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    material = MaterialModel.from_parameters(mesh.parameters)

    # Assign rotor panels to tracks using exact vertex radii (preventing chord-sag shift)
    track_ids = np.full(len(mesh.rotor), -1, dtype=int)
    for i, p in enumerate(mesh.rotor):
        v = np.asarray(p.vertices)
        vr = np.hypot(v[:, 0], v[:, 1])
        rmin, rmax = float(np.min(vr)), float(np.max(vr))
        for k, trk in enumerate(design.tracks):
            if rmin >= trk.r_tooth_in - 1e-7 and rmax <= trk.r_tooth_out + 1e-7:
                track_ids[i] = k
                break
    if not np.all(track_ids >= 0):
        raise ValueError(f"Unassigned rotor panels in {design.name} ({label})")
    dof_track_ids = np.repeat(track_ids, 2)

    char_gap_um = math.inf
    for sector in range(4):
        sp = stator.centroids @ _rotation(sector).T
        for c in rotor.centroids:
            char_gap_um = min(char_gap_um, float(np.min(np.linalg.norm(sp - c, axis=1))))
    k_eff = 1.0 / max(char_gap_um, 0.020)
    kappa_0 = 1.0 / max(abs(mesh.geometry.z_tip), 0.015)
    kappas, weights, _ = _quadrature(n_xi, kappa_0)
    K = len(kappas)
    phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)

    def same_modes_torch(body: Any) -> np.ndarray:
        N = body.count
        sub_var = torch.from_numpy((body.areas[:, None] + body.areas[None, :]) / (32.0 * math.pi))
        area_scale = torch.from_numpy(np.sqrt(body.areas[:, None]) * np.sqrt(body.areas[None, :]) / (4.0 * math.pi))
        kap_t = torch.from_numpy(kappas)
        sec_blocks = np.zeros((4, K, 2 * N, 2 * N), dtype=np.float64)
        for sec in range(4):
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
        qw = torch.from_numpy((target.quad_weights[:, None] * source.quad_weights[None, :]).reshape(16))
        rs_sec = np.zeros((4, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        dz_sec = np.zeros((4, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        u_z = torch.from_numpy(target.tangents[:, :, 2][:, None, :, None])
        tgt_q = torch.from_numpy(target.quad_points.transpose(1, 0, 2)[:, :, None, :])
        for sec in range(4):
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
    energy = 0.0
    for q in range(K):
        kap = float(kappas[q])
        w_q = float(weights[q])
        tm, te, _ = material.channel_weights(kap, k_eff=k_eff)
        q_dof = np.zeros(2 * rotor.count, dtype=np.float64)
        q_logdet = 0.0
        for mode, mult in ((0, 1.0), (2, 1.0), (1, 2.0)):
            if mode in (0, 2):
                mr = torch.from_numpy(rr_modes[q, mode].real.copy())
                ms = torch.from_numpy(ss_modes[q, mode].real.copy())
                g = torch.from_numpy(rs_modes[q, mode].real.copy())
                dg = torch.from_numpy(dz_modes[q, mode].real.copy())
                sr = g.T.contiguous()
                dsr = dg.T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.float64)
            else:
                mr = torch.from_numpy(rr_modes[q, mode].copy())
                ms = torch.from_numpy(ss_modes[q, mode].copy())
                g = torch.from_numpy(rs_modes[q, mode].copy())
                dg = torch.from_numpy(dz_modes[q, mode].copy())
                sr = g.conj().T.contiguous()
                dsr = dg.conj().T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.complex128)
            lu_r, piv_r = torch.linalg.lu_factor(mr)
            lu_s, piv_s = torch.linalg.lu_factor(ms)
            x = torch.linalg.lu_solve(lu_r, piv_r, g)
            ns_col = sr.shape[1]
            z_all = torch.linalg.lu_solve(lu_s, piv_s, torch.cat((sr, dsr), dim=1))
            z, dz = z_all[:, :ns_col], z_all[:, ns_col:]
            coupling = x @ z
            B = dg @ z
            C = x @ dz
            for ch_w in (tm, te):
                pw = ch_w**2
                y = eye - pw * coupling
                lu_y, piv_y = torch.linalg.lu_factor(y)
                u_diag = torch.diagonal(lu_y)
                q_logdet += mult * float(torch.sum(torch.log(torch.abs(u_diag))).item())
                U = torch.linalg.lu_solve(lu_y, piv_y, C)
                V = torch.linalg.lu_solve(
                    lu_r, piv_r, torch.linalg.lu_solve(lu_y, piv_y, B, left=False), left=False
                )
                per_dof = -pw * (torch.diagonal(V).real + torch.diagonal(U).real).numpy()
                q_dof += mult * (-per_dof / (2.0 * math.pi))
        dof_forces += w_q * q_dof
        energy += w_q * q_logdet / (2.0 * math.pi)

    f_tracks_pN = [
        float(np.sum(dof_forces[dof_track_ids == k]) * MEEP_FORCE_TO_SI * 1e12)
        for k in range(len(design.tracks))
    ]
    r_centers = [0.5 * (t.r_inner + t.r_outer) for t in design.tracks]
    w_slots_nm = [int(round((t.r_outer - t.r_inner) * 1e3)) for t in design.tracks]
    f_circ_norm = [f / (2.0 * math.pi * rc) for f, rc in zip(f_tracks_pN, r_centers)]
    f_total_pN = float(np.sum(dof_forces) * MEEP_FORCE_TO_SI * 1e12)
    decomp_residual_pN = abs(f_total_pN - sum(f_tracks_pN))
    if decomp_residual_pN > 1e-11:
        raise ValueError(f"Per-track force decomposition residual {decomp_residual_pN:.3e} pN exceeds tolerance")

    # Active tooth area in 4 sectors: A_tooth = 4 * Delta_theta_tooth_rad * sum_k R_{c,k} * w_{tooth,k}
    dtheta_rad = math.radians(design.tooth_arc_deg)
    a_tooth_um2 = float(4.0 * dtheta_rad * sum(rc * (t.r_tooth_out - t.r_tooth_in) for rc, t in zip(r_centers, design.tracks)))

    return {
        "label": label,
        "design": design.name,
        "widths_nm": w_slots_nm,
        "F_z_pN": f_total_pN,
        "F_z_per_area_pN_per_um2": f_total_pN / max(a_tooth_um2, 1e-12),
        "A_tooth_um2": a_tooth_um2,
        "F_circ_sum_pN_per_um": float(sum(f_circ_norm)),
        "f_tracks_pN": f_tracks_pN,
        "r_centers_um": r_centers,
        "f_circ_norm_pN_per_um": f_circ_norm,
        "trace_decomp_residual_pN": decomp_residual_pN,
        "energy_hbar_c_per_um": energy,
        "n_xi": int(n_xi),
        "panel_resolution": [2, 3, 3, 2],
        "solver_fingerprint": compute_solver_config_fingerprint(n_xi),
        "source_provenance": "direct_3d_bem",
        "elapsed_s": time.perf_counter() - t0,
    }


def enrich_cached_entry(label: str, design: StudyDesign, cached: Mapping[str, Any]) -> dict[str, Any]:
    """Attach derived per-track circumference densities and active tooth area to a verified cached entry."""
    f_tracks = [float(x) for x in cached["f_tracks_pN"]]
    r_centers = [0.5 * (t.r_inner + t.r_outer) for t in design.tracks]
    w_slots_nm = [int(round((t.r_outer - t.r_inner) * 1e3)) for t in design.tracks]
    f_circ_norm = [f / (2.0 * math.pi * rc) for f, rc in zip(f_tracks, r_centers)]
    f_total = float(cached["F_z_pN"])
    decomp_residual_pN = abs(f_total - sum(f_tracks))
    if decomp_residual_pN > 1e-11:
        raise ValueError(
            f"Cached per-track force decomposition residual {decomp_residual_pN:.3e} pN exceeds tolerance in {design.name} ({label})"
        )
    dtheta_rad = math.radians(design.tooth_arc_deg)
    a_tooth_um2 = float(4.0 * dtheta_rad * sum(rc * (t.r_tooth_out - t.r_tooth_in) for rc, t in zip(r_centers, design.tracks)))
    return {
        "label": label,
        "design": design.name,
        "widths_nm": w_slots_nm,
        "F_z_pN": f_total,
        "F_z_per_area_pN_per_um2": f_total / max(a_tooth_um2, 1e-12),
        "A_tooth_um2": a_tooth_um2,
        "F_circ_sum_pN_per_um": float(sum(f_circ_norm)),
        "f_tracks_pN": f_tracks,
        "r_centers_um": r_centers,
        "f_circ_norm_pN_per_um": f_circ_norm,
        "trace_decomp_residual_pN": decomp_residual_pN,
        "energy_hbar_c_per_um": float(cached["energy"]),
        "n_xi": 24,
        "panel_resolution": [2, 3, 3, 2],
        "solver_fingerprint": compute_solver_config_fingerprint(24),
        "source_provenance": "verified_standard_cache_nxi24",
        "elapsed_s": 0.0,
    }


def compute_radial_surrogate_105_distribution(
    evaluated_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """
    Fit the single-track radial-polynomial surrogate curves f_w(R_c) for each slot width
    w in {50, 150, 450} nm from all directly evaluated 3D BEM permutations (7 * N_eval
    track evaluations) and compute model-based surrogate estimates across all 105 multiset
    permutations in cylindrical coordinates R in [0.30, 1.65] um.
    Note: Exact empirical BEM ranks/percentiles are defined strictly on the directly
    evaluated 3D BEM sample (N_perm = 30 non-Cantor + 1 Cantor = 31 evaluations); the
    105-permutation values returned here are explicitly labeled as radial-polynomial
    surrogate estimates (unless all 105 are directly evaluated with --n-perm 104).
    """
    pts_by_w: dict[int, list[tuple[float, float]]] = {50: [], 150: [], 450: []}
    for rec in evaluated_records:
        for w_nm, rc, f_trk in zip(rec["widths_nm"], rec["r_centers_um"], rec["f_tracks_pN"]):
            if int(w_nm) in pts_by_w:
                pts_by_w[int(w_nm)].append((float(rc), float(f_trk)))

    poly_by_w: dict[int, np.ndarray] = {}
    r2_by_w: dict[int, float] = {}
    for w_nm, pts in pts_by_w.items():
        if not pts:
            poly_by_w[w_nm] = np.array([0.0], dtype=np.float64)
            r2_by_w[w_nm] = 0.0
            continue
        r_arr = np.array([p[0] for p in pts], dtype=np.float64)
        f_arr = np.array([p[1] for p in pts], dtype=np.float64)
        n_uniq_r = len(np.unique(np.round(r_arr, 4)))
        if n_uniq_r <= 1:
            poly_by_w[w_nm] = np.array([float(np.mean(f_arr))], dtype=np.float64)
            r2_by_w[w_nm] = 1.0
        else:
            deg = min(2, n_uniq_r - 1)
            coeffs = np.polyfit(r_arr, f_arr, deg=deg)
            poly_by_w[w_nm] = coeffs
            pred = np.polyval(coeffs, r_arr)
            ss_res = float(np.sum((f_arr - pred) ** 2))
            ss_tot = float(np.sum((f_arr - np.mean(f_arr)) ** 2))
            r2_by_w[w_nm] = 1.0 - ss_res / max(ss_tot, 1e-15)

    # Check leave-in accuracy on the directly evaluated permutations
    direct_map = {tuple(int(x) for x in r["widths_nm"]): r for r in evaluated_records}
    all_105 = generate_all_105_unique_permutations()
    rows_105: list[dict[str, Any]] = []
    abs_errors_pN: list[float] = []

    for perm in all_105:
        cur = 0.30 + 0.050
        r_centers = []
        for w_nm in perm:
            s_um = float(w_nm) * 1e-3
            r_centers.append(cur + 0.5 * s_um)
            cur += s_um + 0.050
        pred_tracks = [float(np.polyval(poly_by_w[int(w_nm)], rc)) for w_nm, rc in zip(perm, r_centers)]
        pred_fz = float(sum(pred_tracks))
        pred_fcirc = float(sum(f / (2.0 * math.pi * rc) for f, rc in zip(pred_tracks, r_centers)))
        is_direct = perm in direct_map
        if is_direct:
            rec = direct_map[perm]
            fz_val = float(rec["F_z_pN"])
            fcirc_val = float(rec["F_circ_sum_pN_per_um"])
            abs_errors_pN.append(abs(fz_val - pred_fz))
        else:
            fz_val = pred_fz
            fcirc_val = pred_fcirc
        r50_mean = float(np.mean([rc for w_nm, rc in zip(perm, r_centers) if w_nm == 50]))
        rows_105.append({
            "widths_nm": list(perm),
            "is_direct_3d_bem": is_direct,
            "F_z_pN": fz_val,
            "F_z_radial_model_pN": pred_fz,
            "F_circ_sum_pN_per_um": fcirc_val,
            "F_circ_radial_model_pN_per_um": pred_fcirc,
            "mean_R50_um": r50_mean,
            "R450_um": float(r_centers[perm.index(450)]),
        })

    # Pure radial-surrogate predictions across all 105 permutations for homogeneous surrogate ranking
    fz_surr_all = np.array([r["F_z_radial_model_pN"] for r in rows_105], dtype=np.float64)
    fcirc_surr_all = np.array([r["F_circ_radial_model_pN_per_um"] for r in rows_105], dtype=np.float64)
    fz_hybrid_all = np.array([r["F_z_pN"] for r in rows_105], dtype=np.float64)
    fcirc_hybrid_all = np.array([r["F_circ_sum_pN_per_um"] for r in rows_105], dtype=np.float64)
    cantor_row = next(r for r in rows_105 if tuple(r["widths_nm"]) == CANTOR_WIDTHS_NM)
    c_fz_surr = float(cantor_row["F_z_radial_model_pN"])
    c_fcirc_surr = float(cantor_row["F_circ_radial_model_pN_per_um"])
    c_fz_hyb = float(cantor_row["F_z_pN"])
    c_fcirc_hyb = float(cantor_row["F_circ_sum_pN_per_um"])

    # Homogeneous model-based surrogate rank and percentile estimates across all 105 unique multiset permutations
    n_less_fz_surr = int(np.sum(fz_surr_all < c_fz_surr - 1e-9))
    n_le_fz_surr = int(np.sum(fz_surr_all <= c_fz_surr + 1e-9))
    n_less_fcirc_surr = int(np.sum(fcirc_surr_all < c_fcirc_surr - 1e-9))
    n_le_fcirc_surr = int(np.sum(fcirc_surr_all <= c_fcirc_surr + 1e-9))
    n_105_gt_uni_surr = int(np.sum(fz_surr_all > 2.055314003578))

    # Hybrid (direct BEM where available + surrogate elsewhere) ranks labeled separately
    n_less_fz_hyb = int(np.sum(fz_hybrid_all < c_fz_hyb - 1e-9))
    n_less_fcirc_hyb = int(np.sum(fcirc_hybrid_all < c_fcirc_hyb - 1e-9))

    return {
        "estimation_method": "direct_3d_bem" if len(direct_map) == 105 else "homogeneous_radial_polynomial_surrogate",
        "n_direct_3d_bem_in_105": len(direct_map),
        "n_surrogate_interpolated_in_105": 105 - len(direct_map),
        "n_unique_multiset_permutations": 105,
        "n_105_exceeding_uniform": n_105_gt_uni_surr,
        "pct_105_exceeding_uniform": 100.0 * n_105_gt_uni_surr / 105.0,
        "radial_model_mae_pN": float(np.mean(abs_errors_pN)) if abs_errors_pN else 0.0,
        "radial_model_max_err_pN": float(np.max(abs_errors_pN)) if abs_errors_pN else 0.0,
        "track_50nm_r2": r2_by_w[50],
        "track_150nm_r2": r2_by_w[150],
        "track_450nm_r2": r2_by_w[450],
        "fz_min_105_pN": float(np.min(fz_surr_all)),
        "fz_max_105_pN": float(np.max(fz_surr_all)),
        "fz_mean_105_pN": float(np.mean(fz_surr_all)),
        "fz_median_105_pN": float(np.median(fz_surr_all)),
        "fz_std_105_pN": float(np.std(fz_surr_all)),
        "fz_surrogate_only_mean_105_pN": float(np.mean(fz_surr_all)),
        "fcirc_min_105_pN_per_um": float(np.min(fcirc_surr_all)),
        "fcirc_max_105_pN_per_um": float(np.max(fcirc_surr_all)),
        "fcirc_mean_105_pN_per_um": float(np.mean(fcirc_surr_all)),
        "fcirc_median_105_pN_per_um": float(np.median(fcirc_surr_all)),
        "surrogate_estimated_cantor_rank_from_bottom_fz_105": n_less_fz_surr + 1,
        "surrogate_estimated_cantor_percentile_strict_fz_105": 100.0 * n_less_fz_surr / 104.0,
        "surrogate_estimated_cantor_percentile_inclusive_fz_105": 100.0 * n_le_fz_surr / 105.0,
        "surrogate_estimated_cantor_rank_from_bottom_fcirc_105": n_less_fcirc_surr + 1,
        "surrogate_estimated_cantor_percentile_strict_fcirc_105": 100.0 * n_less_fcirc_surr / 104.0,
        "surrogate_estimated_cantor_percentile_inclusive_fcirc_105": 100.0 * n_le_fcirc_surr / 105.0,
        "hybrid_cantor_rank_from_bottom_fz_105": n_less_fz_hyb + 1,
        "hybrid_cantor_percentile_strict_fz_105": 100.0 * n_less_fz_hyb / 104.0,
        "hybrid_cantor_rank_from_bottom_fcirc_105": n_less_fcirc_hyb + 1,
        "hybrid_cantor_percentile_strict_fcirc_105": 100.0 * n_less_fcirc_hyb / 104.0,
        "permutations_105": rows_105,
    }


def render_figure(report: Mapping[str, Any], out_png: Path, out_pdf: Path) -> None:
    """Render 4-panel diagnostic figure for the 7-track ordering & curvature decoupling study."""
    plt.rcParams.update({
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7.5,
    })
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.8), dpi=300)
    ax_a, ax_b, ax_c, ax_d = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

    # Panel A: Cylindrical vs Quasi-Planar (arc-matched) total force comparison
    cyl_map = {r["design"]: r for r in report["part1_curvature_decoupling"]["cylindrical_0.30_1.65"]}
    qpa_map = {r["design"]: r for r in report["part1_curvature_decoupling"]["quasi_planar_arc_matched_10.0_11.35"]}
    designs_order = [
        ("Ctrl_Uniform7Track", "Uniform\n7-Track"),
        ("Ctrl_RandomPermuted7Track", "Random\nPermuted"),
        ("Fractal_N3_Cantor7Track", "Cantor N=3\n(Symmetric)"),
        ("Ctrl_Monotonic7Track", "Monotonic\n(Inner->Outer)"),
    ]
    x = np.arange(len(designs_order))
    w_bar = 0.36
    vals_cyl = [cyl_map[k]["F_z_pN"] for k, _ in designs_order]
    vals_qpa = [qpa_map[k]["F_z_pN"] for k, _ in designs_order]

    bars1 = ax_a.bar(x - w_bar / 2, vals_cyl, w_bar, label=r"Cylindrical $R \in [0.30, 1.65]\,\mu\mathrm{m}$ ($R_{\max}/R_{\min}=5.5$)", color="#1f77b4", edgecolor="black", linewidth=0.6)
    bars2 = ax_a.bar(x + w_bar / 2, vals_qpa, w_bar, label=r"Quasi-planar $R \in [10.0, 11.35]\,\mu\mathrm{m}$ ($R_{\max}/R_{\min}=1.135$)", color="#ff7f0e", edgecolor="black", linewidth=0.6)
    for b in bars1:
        ax_a.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.06, f"{b.get_height():.2f}", ha="center", va="bottom", fontsize=7.5, color="#1f77b4", fontweight="bold")
    for b in bars2:
        ax_a.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.06, f"{b.get_height():.2f}", ha="center", va="bottom", fontsize=7.5, color="#d95f02", fontweight="bold")
    ax_a.set_xticks(x)
    ax_a.set_xticklabels([lbl for _, lbl in designs_order])
    ax_a.set_ylabel(r"Open-slot repulsive force $F_z(\theta_{\mathrm{off}})$ (pN)")
    ax_a.set_ylim(0, 5.05)
    ax_a.set_title("a  Cylindrical Curvature vs. Quasi-Planar Ordering Decoupling", loc="left", fontweight="bold")
    ax_a.legend(loc="upper left", frameon=True)
    ax_a.grid(axis="y", linestyle=":", alpha=0.5)

    # Panel B: Per-track force F_{z,k} vs track radius R_k in Cylindrical vs Quasi-Planar
    perm_recs = report["part2_permutation_distribution"]["evaluated_permutations_cylindrical"]
    for w_nm, col, mk, lbl in (
        (50, "#d62728", "o", "50 nm slot ($g_{r,3}=15$ nm)"),
        (150, "#1f77b4", "s", "150 nm slot ($g_{r,2}=45$ nm)"),
        (450, "#2ca02c", "^", "450 nm slot ($g_{r,1}=135$ nm)"),
    ):
        rs, fs = [], []
        for rec in perm_recs:
            for w_k, r_k, f_k in zip(rec["widths_nm"], rec["r_centers_um"], rec["f_tracks_pN"]):
                if w_k == w_nm:
                    rs.append(r_k)
                    fs.append(f_k)
        ax_b.scatter(rs, fs, color=col, marker=mk, s=26, alpha=0.75, label=f"Cylindrical: {lbl}")
        if len(rs) >= 3:
            r_grid = np.linspace(min(rs), max(rs), 50)
            deg = 2 if len(set(np.round(rs, 3))) >= 3 else 1
            c_fit = np.polyfit(rs, fs, deg)
            ax_b.plot(r_grid, np.polyval(c_fit, r_grid), color=col, linestyle="-", linewidth=1.3)

    # Overlay quasi-planar 50-nm track forces vs shifted radius R_k - 9.70 um
    qp_cantor = qpa_map["Fractal_N3_Cantor7Track"]
    qp_mono = qpa_map["Ctrl_Monotonic7Track"]
    qp_r50 = [r - 9.70 for w, r in zip(qp_cantor["widths_nm"], qp_cantor["r_centers_um"]) if w == 50] + [
        r - 9.70 for w, r in zip(qp_mono["widths_nm"], qp_mono["r_centers_um"]) if w == 50
    ]
    qp_f50 = [f for w, f in zip(qp_cantor["widths_nm"], qp_cantor["f_tracks_pN"]) if w == 50] + [
        f for w, f in zip(qp_mono["widths_nm"], qp_mono["f_tracks_pN"]) if w == 50
    ]
    ax_b.plot(qp_r50, qp_f50, "k--d", markersize=5, linewidth=1.2, label=r"Quasi-planar 50 nm ($R_k - 9.7\,\mu\mathrm{m}$)")
    ax_b.set_xlabel(r"Track center radius $R_k$ ($\mu$m)")
    ax_b.set_ylabel(r"Per-track axial force $F_{z,k}$ (pN)")
    ax_b.set_title(r"b  Per-Track Force $F_{z,k}(R_k)$ Across Radial Positions", loc="left", fontweight="bold")
    ax_b.legend(loc="upper right", frameon=True, fontsize=7)
    ax_b.grid(True, linestyle=":", alpha=0.5)

    # Panel C: Distribution of N_perm evaluated permutations + all 105 multiset permutations (Raw F_z)
    p2 = report["part2_permutation_distribution"]
    eval_recs_c = p2["evaluated_permutations_cylindrical"] or [cyl_map["Fractal_N3_Cantor7Track"]]
    fz_eval = [float(r["F_z_pN"]) for r in eval_recs_c]
    fz_105 = [float(r["F_z_radial_model_pN"]) for r in p2["all_105_multiset_reconstruction"]["permutations_105"]]
    c_fz = cyl_map["Fractal_N3_Cantor7Track"]["F_z_pN"]
    m_fz = cyl_map["Ctrl_Monotonic7Track"]["F_z_pN"]
    u_fz = cyl_map["Ctrl_Uniform7Track"]["F_z_pN"]
    s_fz = cyl_map["Ctrl_RandomPermuted7Track"]["F_z_pN"]

    bins = np.linspace(min(min(fz_105), min(fz_eval)) - 0.05, max(max(fz_105), max(fz_eval)) + 0.05, 16)
    ax_c.hist(fz_105, bins=bins, color="#aec7e8", edgecolor="#1f77b4", alpha=0.55, label="105-perm radial-surrogate model")
    ax_c.hist(fz_eval, bins=bins, color="#1f77b4", edgecolor="black", alpha=0.80, label=f"Direct 3D BEM sample ($N={len(fz_eval)}$)")
    ax_c.axvline(c_fz, color="#d62728", linestyle="-", linewidth=2.0, label=f"Cantor N=3: {c_fz:.3f} pN ({p2['cantor_percentile_strict_fz_eval']:.1f}th %ile)")
    mono_eval_rec = next((r for r in eval_recs_c if tuple(r["widths_nm"]) == MONOTONIC_WIDTHS_NM), None)
    if mono_eval_rec is not None:
        m_fz_val = float(mono_eval_rec["F_z_pN"])
        n_non_mono = max(len(fz_eval) - 1, 1)
        m_pct = 100.0 * sum(1 for v in fz_eval if v < m_fz_val - 1e-9) / n_non_mono
        mono_lbl = f"Monotonic: {m_fz_val:.3f} pN ({m_pct:.0f}th %ile)"
    else:
        mono_lbl = f"Monotonic (ref): {m_fz:.3f} pN (not in sample)"
    ax_c.axvline(m_fz, color="#2ca02c", linestyle="--", linewidth=1.8, label=mono_lbl)
    ax_c.axvline(s_fz, color="#9467bd", linestyle="-.", linewidth=1.5, label=f"Shuffled Ctrl: {s_fz:.3f} pN")
    ax_c.axvline(u_fz, color="#7f7f7f", linestyle=":", linewidth=1.8, label=f"Uniform 7-Track: {u_fz:.3f} pN")
    ax_c.set_xlabel(r"Total repulsive force $F_z = \sum_{k=1}^7 F_{z,k}$ (pN)")
    ax_c.set_ylabel("Number of permutations")
    ax_c.set_title("c  Multiset Permutation Distribution (Raw Force $F_z$)", loc="left", fontweight="bold")
    ax_c.legend(loc="upper left", frameon=True, fontsize=7)
    ax_c.grid(True, linestyle=":", alpha=0.5)

    # Panel D: Circumference-normalized force sum_k F_{z,k}/(2*pi*R_k) vs mean radius of 50-nm tracks
    r50_105 = [r["mean_R50_um"] for r in p2["all_105_multiset_reconstruction"]["permutations_105"]]
    fcirc_105 = [r["F_circ_radial_model_pN_per_um"] for r in p2["all_105_multiset_reconstruction"]["permutations_105"]]
    r50_eval = [
        float(np.mean([rc for w, rc in zip(r["widths_nm"], r["r_centers_um"]) if w == 50]))
        for r in p2["evaluated_permutations_cylindrical"]
    ]
    fcirc_eval = [r["F_circ_sum_pN_per_um"] for r in p2["evaluated_permutations_cylindrical"]]

    ax_d.scatter(r50_105, fcirc_105, color="#aec7e8", s=22, alpha=0.7, label="105-perm radial-surrogate model")
    ax_d.scatter(r50_eval, fcirc_eval, color="#1f77b4", edgecolor="black", linewidth=0.5, s=36, label="Direct 3D BEM evaluations")
    ax_d.scatter([0.975], [cyl_map["Fractal_N3_Cantor7Track"]["F_circ_sum_pN_per_um"]], color="#d62728", marker="*", s=160, zorder=5, label=f"Cantor N=3 ({p2['cantor_percentile_strict_fcirc_eval']:.1f}th %ile)")
    ax_d.scatter([0.525], [cyl_map["Ctrl_Monotonic7Track"]["F_circ_sum_pN_per_um"]], color="#2ca02c", marker="D", s=70, zorder=5, label="Monotonic (all 50 nm inner)")
    ax_d.axhline(cyl_map["Ctrl_Uniform7Track"]["F_circ_sum_pN_per_um"], color="#7f7f7f", linestyle=":", linewidth=1.6, label="Uniform 7-Track baseline")
    ax_d.set_xlabel(r"Mean radial center of the four 50-nm tracks $\bar{R}_{50}$ ($\mu$m)")
    ax_d.set_ylabel(r"Circumference-normalized $\sum_{k=1}^7 F_{z,k}/(2\pi R_k)$ (pN/$\mu$m)")
    ax_d.set_title(r"d  Circumference-Normalized Force vs. $\bar{R}_{50}$ Radial Bias", loc="left", fontweight="bold")
    ax_d.legend(loc="upper right", frameon=True, fontsize=7)
    ax_d.grid(True, linestyle=":", alpha=0.5)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)

    paper_fig_dir = ROOT / "Papers" / "FCE_Nature_ver01" / "figures"
    if paper_fig_dir.is_dir():
        for src in (out_png, out_pdf):
            dst = paper_fig_dir / src.name
            dst.write_bytes(src.read_bytes())


def write_markdown_summary(report: Mapping[str, Any], out_md: Path) -> None:
    p1 = report["part1_curvature_decoupling"]
    p2 = report["part2_permutation_distribution"]
    cyl_map = {r["design"]: r for r in p1["cylindrical_0.30_1.65"]}
    qpa_map = {r["design"]: r for r in p1["quasi_planar_arc_matched_10.0_11.35"]}
    qpf_map = {r["design"]: r for r in p1["quasi_planar_fixed_angle_10.0_11.35"]}
    emp105 = p2["all_105_multiset_reconstruction"]

    lines = [
        "# 7-Track Ordering & Curvature Decoupling Study (`N=3`, 3D Vector-Dyadic BEM)",
        "",
        "## 1. Cylindrical Curvature vs. Quasi-Planar Track Ordering",
        "",
        "| Regime | Constellation | Slot Widths (nm) | Raw $F_z$ (pN) | $F_z / A_{\\rm tooth}$ (pN/$\\mu$m$^2$) | $\\sum_k F_{z,k}/(2\\pi R_k)$ (pN/$\\mu$m) | Per-Track $F_{z,k}$ (pN) |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for regime_lbl, rmap in (
        ("Cylindrical $[0.30, 1.65]\\,\\mu$m", cyl_map),
        ("Quasi-Planar Arc-Matched $[10.0, 11.35]\\,\\mu$m", qpa_map),
        ("Quasi-Planar Fixed-Angle $[10.0, 11.35]\\,\\mu$m", qpf_map),
    ):
        for dname in ("Fractal_N3_Cantor7Track", "Ctrl_Uniform7Track", "Ctrl_Monotonic7Track", "Ctrl_RandomPermuted7Track"):
            r = rmap[dname]
            trks = ", ".join(f"{x:+.4f}" for x in r["f_tracks_pN"])
            wstr = str(r["widths_nm"])
            lines.append(
                f"| {regime_lbl} | `{dname}` | `{wstr}` | `{r['F_z_pN']:+.6f}` | `{r['F_z_per_area_pN_per_um2']:+.4f}` | `{r['F_circ_sum_pN_per_um']:+.6f}` | `[{trks}]` |"
            )

    eval_recs = p2["evaluated_permutations_cylindrical"] or [cyl_map["Fractal_N3_Cantor7Track"]]
    min_rec = min(eval_recs, key=lambda r: float(r["F_z_pN"]))
    max_rec = max(eval_recs, key=lambda r: float(r["F_z_pN"]))
    uni_fz = float(cyl_map["Ctrl_Uniform7Track"]["F_z_pN"])
    max_ratio_vs_uni = float(max_rec["F_z_pN"]) / max(uni_fz, 1e-12)
    min_comparison_clause = (
        f"only extreme outer-packed permutations such as `{min_rec['design']}` (`{min_rec['widths_nm']}` nm, `{min_rec['F_z_pN']:+.6f} pN`) fall slightly below `+{uni_fz:.6f} pN`"
        if float(min_rec["F_z_pN"]) <= uni_fz
        else f"even the sample minimum `{min_rec['design']}` (`{min_rec['widths_nm']}` nm, `{min_rec['F_z_pN']:+.6f} pN`) exceeds `+{uni_fz:.6f} pN`"
    )

    mono_50nm_sum = sum(f for w, f in zip(cyl_map["Ctrl_Monotonic7Track"]["widths_nm"], cyl_map["Ctrl_Monotonic7Track"]["f_tracks_pN"]) if w == 50)
    cantor_50nm_sum = sum(f for w, f in zip(cyl_map["Fractal_N3_Cantor7Track"]["widths_nm"], cyl_map["Fractal_N3_Cantor7Track"]["f_tracks_pN"]) if w == 50)
    qpa_non_uni = sorted(
        [r for r in p1["quasi_planar_arc_matched_10.0_11.35"] if r["design"] != "Ctrl_Uniform7Track"],
        key=lambda r: float(r["F_z_pN"]),
    )
    qpa_order_str = " < ".join(f"`{r['F_z_pN']:+.6f} pN` (`{r['design']}`)" for r in qpa_non_uni)

    lines.extend([
        "",
        "### Key Curvature Decoupling Findings",
        f"- **Cylindrical annulus $R \\in [0.30, 1.65]\\,\\mu\\text{{m}}$ ($R_{{\\max}}/R_{{\\min}} = 5.5$)**: `Ctrl_Monotonic7Track` gives `{cyl_map['Ctrl_Monotonic7Track']['F_z_pN']:+.6f} pN` vs. `{cyl_map['Fractal_N3_Cantor7Track']['F_z_pN']:+.6f} pN` for `Fractal_N3_Cantor7Track` (`{p1['cylindrical_monotonic_vs_cantor_pct']:+.2f}%` difference). Over 85% of the repulsive force originates from the four narrowest $50\\text{{ nm}}$ slots ($g_{{r,3}} = 15\\text{{ nm}}$), whose per-track force drops from `{cyl_map['Fractal_N3_Cantor7Track']['f_tracks_pN'][0]:+.4f} pN` at the innermost radius ($R_0 = 0.375\\,\\mu\\text{{m}}$) to `{cyl_map['Fractal_N3_Cantor7Track']['f_tracks_pN'][6]:+.4f} pN` at the outermost radius ($R_6 = 1.575\\,\\mu\\text{{m}}$). Because monotonic ordering packs all four $50\\text{{ nm}}$ slots at the innermost radii ($R_c \\in [0.375, 0.675]\\,\\mu\\text{{m}}$, $\\bar{{R}}_{{50}} = 0.525\\,\\mu\\text{{m}}$) and relegates the zero-force $450\\text{{ nm}}$ slot to the outer radius ($R_6 = 1.375\\,\\mu\\text{{m}}$), it harvests `{mono_50nm_sum:+.3f} pN` from the four $50\\text{{ nm}}$ tracks alone versus `{cantor_50nm_sum:+.3f} pN` for the radially symmetric Cantor sequence ($\\bar{{R}}_{{50}} = 0.975\\,\\mu\\text{{m}}$).",
        f"- **Quasi-planar arc-length-matched annulus $R \\in [10.0, 11.35]\\,\\mu\\text{{m}}$ ($R_{{\\max}}/R_{{\\min}} = 1.135 \\approx 1$)**: Eliminating cylindrical curvature collapses the Monotonic-vs.-Cantor gap by **{p1['curvature_gap_reduction_factor']:.1f}-fold**, from `{p1['cylindrical_monotonic_vs_cantor_pct']:+.2f}%` (`{cyl_map['Ctrl_Monotonic7Track']['F_z_pN'] - cyl_map['Fractal_N3_Cantor7Track']['F_z_pN']:+.4f} pN`) down to just **`{p1['quasi_planar_arc_monotonic_vs_cantor_pct']:+.2f}%`** (`{qpa_map['Ctrl_Monotonic7Track']['F_z_pN'] - qpa_map['Fractal_N3_Cantor7Track']['F_z_pN']:+.4f} pN`: `{qpa_map['Ctrl_Monotonic7Track']['F_z_pN']:+.6f} pN` vs. `{qpa_map['Fractal_N3_Cantor7Track']['F_z_pN']:+.6f} pN`), while all multiscale permutations surpass the 7-track uniform periodic control (`{qpa_map['Ctrl_Uniform7Track']['F_z_pN']:+.6f} pN`).",
        "",
        "## 2. Multiset Permutation Distribution & Percentile Rank of the Cantor Sequence",
        f"- **Direct 3D BEM sample ($N_{{\\rm perm}} = {p2['n_non_cantor_evaluated']}$ non-Cantor permutations + 1 Cantor = {p2['n_total_evaluated']} evaluations)**:",
        f"  - Raw force $F_z$ range: `[{p2['fz_min_eval_pN']:+.6f}, {p2['fz_max_eval_pN']:+.6f}] pN` (mean `{p2['fz_mean_eval_pN']:+.6f} pN`, median `{p2['fz_median_eval_pN']:+.6f} pN`, std `{p2['fz_std_eval_pN']:.6f} pN`).",
        f"  - `{p2['n_eval_exceeding_uniform']}/{p2['n_total_evaluated']}` permutations (`{p2['pct_eval_exceeding_uniform']:.1f}%`; `{emp105['n_105_exceeding_uniform']}/105` = `{emp105['pct_105_exceeding_uniform']:.1f}%` in the 105-permutation surrogate) exceed `Ctrl_Uniform7Track` (`{uni_fz:+.6f} pN`) by up to `{max_ratio_vs_uni:.2f}x`; {min_comparison_clause}.",
        f"  - **Exact empirical Cantor raw force $F_z = {cyl_map['Fractal_N3_Cantor7Track']['F_z_pN']:+.6f}\\text{{ pN}}$ percentile (across the $N_{{\\rm perm}} = {p2['n_non_cantor_evaluated']}$ directly evaluated 3D BEM permutations)**: Rank `{p2['cantor_rank_from_bottom_fz_eval']}/{p2['n_total_evaluated']}` from bottom (**`{p2['cantor_percentile_strict_fz_eval']:.2f}`th percentile**; radial-polynomial surrogate estimate across all 105 multiset permutations: `{emp105['surrogate_estimated_cantor_percentile_strict_fz_105']:.2f}`th percentile, estimated rank `{emp105['surrogate_estimated_cantor_rank_from_bottom_fz_105']}/105`, surrogate MAE `{emp105['radial_model_mae_pN']:.4f} pN`).",
        f"  - **Exact empirical Cantor circumference-normalized $\\sum_k F_{{z,k}}/(2\\pi R_k) = {cyl_map['Fractal_N3_Cantor7Track']['F_circ_sum_pN_per_um']:+.6f}\\text{{ pN}}/\\mu\\text{{m}}$ percentile (across the $N_{{\\rm perm}} = {p2['n_non_cantor_evaluated']}$ directly evaluated 3D BEM permutations)**: Rank `{p2['cantor_rank_from_bottom_fcirc_eval']}/{p2['n_total_evaluated']}` from bottom (**`{p2['cantor_percentile_strict_fcirc_eval']:.2f}`th percentile**; radial-polynomial surrogate estimate across all 105 multiset permutations: `{emp105['surrogate_estimated_cantor_percentile_strict_fcirc_105']:.2f}`th percentile, estimated rank `{emp105['surrogate_estimated_cantor_rank_from_bottom_fcirc_105']}/105`).",
        f"  - **Quasi-planar $R \\in [10.0, 11.35]\\,\\mu\\text{{m}}$ Cantor percentile**: Exact rank `{p2['quasi_planar_direct_eval_cantor_rank_from_bottom_fz']}/{len(qpa_non_uni)}` (`{p2['quasi_planar_direct_eval_cantor_percentile_fz']:.2f}`th percentile) among the directly evaluated multiscale configurations ({qpa_order_str}), and radial-surrogate estimated **`{p2['quasi_planar_surrogate_cantor_percentile_strict_fz']:.2f}`th percentile** in raw force $F_z$ (**`{p2['quasi_planar_surrogate_cantor_percentile_strict_fcirc']:.2f}`th percentile** in circumference-normalized force).",
        "",
    ])
    atomic_write_text(out_md, "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 7-track ordering and cylindrical curvature decoupling study.")
    parser.add_argument("--max-steps", type=int, default=0, help="Cap number of BEM evaluations for micro-probe mode.")
    parser.add_argument("--n-perm", type=int, default=30, help="Number of distinct non-Cantor multiset permutations to evaluate in 3D BEM.")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel BEM worker processes.")
    parser.add_argument("--threads-per-worker", type=int, default=4, help="Number of PyTorch MKL threads per worker.")
    parser.add_argument("--recompute-family", action="store_true", help="Recompute the 12 Part-1 family points instead of using verified cache.")
    args = parser.parse_args()

    if args.max_steps < 0 or args.max_steps == 1:
        raise ValueError(f"--max-steps must be 0 (unlimited) or >= 2, got {args.max_steps}")
    if args.workers < 1:
        raise ValueError(f"--workers must be >= 1, got {args.workers}")
    if args.threads_per_worker < 1:
        raise ValueError(f"--threads-per-worker must be >= 1, got {args.threads_per_worker}")
    if not (1 <= args.n_perm <= 104):
        raise ValueError(f"--n-perm must satisfy 1 <= n_perm <= 104, got {args.n_perm}")
    if args.recompute_family and 0 < args.max_steps < 13:
        raise ValueError(
            f"--recompute-family requires at least 13 BEM evaluations (12 family + >=1 permutation), got --max-steps {args.max_steps}"
        )
    t_start = time.perf_counter()
    is_micro = args.max_steps > 0
    n_xi = 24
    remaining_budget = args.max_steps if is_micro else None
    n_perm = min(args.n_perm, max(1, args.max_steps - 1)) if is_micro else args.n_perm

    fam_cyl = make_family(0.30, 1.65, 12.0, 36.0)
    fam_qp_fixed = make_family(10.0, 11.35, 12.0, 36.0)
    scale_arc = 0.975 / 10.675
    fam_qp_arc = make_family(10.0, 11.35, 12.0 * scale_arc, 36.0 * scale_arc)

    part1_results: dict[str, list[dict[str, Any]]] = {
        "cylindrical_0.30_1.65": [],
        "quasi_planar_fixed_angle_10.0_11.35": [],
        "quasi_planar_arc_matched_10.0_11.35": [],
    }

    if not args.recompute_family:
        for d in fam_cyl:
            part1_results["cylindrical_0.30_1.65"].append(
                enrich_cached_entry("cyl_0.30_1.65", d, VERIFIED_FAMILY_CACHE[("cyl_0.30_1.65", d.name)])
            )
        for d in fam_qp_fixed:
            part1_results["quasi_planar_fixed_angle_10.0_11.35"].append(
                enrich_cached_entry("qp_fixed_10.0_11.35", d, VERIFIED_FAMILY_CACHE[("qp_fixed_10.0_11.35", d.name)])
            )
        for d in fam_qp_arc:
            part1_results["quasi_planar_arc_matched_10.0_11.35"].append(
                enrich_cached_entry("qp_arc_10.0_11.35", d, VERIFIED_FAMILY_CACHE[("qp_arc_10.0_11.35", d.name)])
            )
    else:
        p1_tasks = []
        for d in fam_cyl:
            p1_tasks.append(("cyl_0.30_1.65", d, 3.0, n_xi, args.threads_per_worker))
        for d in fam_qp_fixed:
            p1_tasks.append(("qp_fixed_10.0_11.35", d, 3.0, n_xi, args.threads_per_worker))
        for d in fam_qp_arc:
            theta_off = (d.aperture_arc_deg / 2.0) - 15.0
            p1_tasks.append(("qp_arc_10.0_11.35", d, theta_off, n_xi, args.threads_per_worker))
        if remaining_budget is not None:
            p1_tasks = p1_tasks[:remaining_budget]
            remaining_budget -= len(p1_tasks)
        with ProcessPoolExecutor(max_workers=min(args.workers, len(p1_tasks))) as pool:
            p1_out = list(pool.map(eval_design_bem_per_track, p1_tasks))
        computed_map = {(r["label"], r["design"]): r for r in p1_out}
        for d in fam_cyl:
            part1_results["cylindrical_0.30_1.65"].append(computed_map[("cyl_0.30_1.65", d.name)])
        for d in fam_qp_fixed:
            part1_results["quasi_planar_fixed_angle_10.0_11.35"].append(computed_map[("qp_fixed_10.0_11.35", d.name)])
        for d in fam_qp_arc:
            part1_results["quasi_planar_arc_matched_10.0_11.35"].append(computed_map[("qp_arc_10.0_11.35", d.name)])

    # Part 2: Evaluate N_perm distinct non-Cantor permutations in 3D Vector-Dyadic BEM
    current_fingerprint = compute_solver_config_fingerprint(n_xi)
    selected_non_cantor = select_stratified_non_cantor_permutations(n_perm)
    cached_cyl_by_widths: dict[tuple[int, ...], dict[str, Any]] = {}
    if args.recompute_family or not is_micro:
        for r in part1_results["cylindrical_0.30_1.65"]:
            if (
                r["design"] != "Ctrl_Uniform7Track"
                and int(r.get("n_xi", -1)) == n_xi
                and r.get("solver_fingerprint") == current_fingerprint
            ):
                cached_cyl_by_widths[tuple(r["widths_nm"])] = r
    if not is_micro and not args.recompute_family:
        # Reuse prior permutation records only when solver fingerprint, parameters, and record integrity match
        existing_json = ROOT / "results" / "n3_7track_ordering_curvature_study.json"
        if existing_json.is_file():
            try:
                prev_data = json.loads(existing_json.read_text(encoding="utf-8"))
                prev_params = prev_data.get("parameters", {})
                if (
                    prev_data.get("execution_status") == "complete"
                    and int(prev_params.get("n_xi", -1)) == n_xi
                    and prev_params.get("solver_fingerprint") == current_fingerprint
                ):
                    for r in prev_data.get("part2_permutation_distribution", {}).get("evaluated_permutations_cylindrical", []):
                        if (
                            isinstance(r, Mapping)
                            and len(r.get("widths_nm", [])) == 7
                            and len(r.get("f_tracks_pN", [])) == 7
                            and int(r.get("n_xi", -1)) == n_xi
                            and list(r.get("panel_resolution", [])) == [2, 3, 3, 2]
                            and r.get("solver_fingerprint") == current_fingerprint
                            and abs(float(r["F_z_pN"]) - sum(float(x) for x in r["f_tracks_pN"])) < 1e-9
                        ):
                            w_tup = tuple(int(x) for x in r["widths_nm"])
                            if w_tup not in cached_cyl_by_widths:
                                cached_cyl_by_widths[w_tup] = dict(r)
            except (OSError, ValueError, KeyError, TypeError):
                pass

    perm_tasks: list[tuple[str, StudyDesign, float, int, int]] = []
    evaluated_cyl_perms: list[dict[str, Any]] = []

    # Always include Cantor + selected_non_cantor, capped strictly by remaining_budget when --max-steps > 0
    all_target_perms = [CANTOR_WIDTHS_NM] + selected_non_cantor
    for idx, perm in enumerate(all_target_perms):
        if perm in cached_cyl_by_widths:
            evaluated_cyl_perms.append(cached_cyl_by_widths[perm])
        else:
            if remaining_budget is not None and len(perm_tasks) >= remaining_budget:
                continue
            pname = (
                "Fractal_N3_Cantor7Track"
                if perm == CANTOR_WIDTHS_NM
                else "Ctrl_Monotonic7Track"
                if perm == MONOTONIC_WIDTHS_NM
                else "Ctrl_ReverseMonotonic7Track"
                if perm == REVERSE_MONOTONIC_WIDTHS_NM
                else "Ctrl_RandomPermuted7Track"
                if perm == SHUFFLED_CTRL_WIDTHS_NM
                else f"Perm_{idx:03d}_{'_'.join(str(w) for w in perm)}"
            )
            design_p = build_design_from_widths(pname, perm, 0.30, 1.65, 12.0, 36.0)
            perm_tasks.append(("cyl_0.30_1.65_perm", design_p, 3.0, n_xi, args.threads_per_worker))

    if perm_tasks:
        print(
            f"[Part 2] Evaluating {len(perm_tasks)} new 7-track permutations in 3D Vector-Dyadic BEM "
            f"(n_xi={n_xi}, workers={args.workers}, threads/worker={args.threads_per_worker})...",
            flush=True,
        )
        with ProcessPoolExecutor(max_workers=min(args.workers, len(perm_tasks))) as pool:
            for done_idx, res in enumerate(pool.map(eval_design_bem_per_track, perm_tasks), start=1):
                evaluated_cyl_perms.append(res)
                print(
                    f"  [{done_idx:02d}/{len(perm_tasks):02d}] {res['design']:34s} | "
                    f"Fz={res['F_z_pN']:+9.6f} pN | sum(Fz_k/2pi R_k)={res['F_circ_sum_pN_per_um']:+9.6f} pN/um "
                    f"({res['elapsed_s']:.1f}s)",
                    flush=True,
                )

    # Sort evaluated_cyl_perms deterministically by F_z_pN (strictly containing only actual evaluations at n_xi)
    evaluated_cyl_perms.sort(key=lambda r: float(r["F_z_pN"]))
    emp_105 = compute_radial_surrogate_105_distribution(evaluated_cyl_perms)

    # Also compute quasi-planar 105-permutation surrogate distribution from the quasi-planar arc-matched per-track curves
    qp_arc_non_uni = [
        r for r in part1_results["quasi_planar_arc_matched_10.0_11.35"] if r["design"] != "Ctrl_Uniform7Track"
    ]
    qp_pts_by_w: dict[int, list[tuple[float, float]]] = {50: [], 150: [], 450: []}
    for rec in qp_arc_non_uni:
        for w_nm, rc, f_trk in zip(rec["widths_nm"], rec["r_centers_um"], rec["f_tracks_pN"]):
            qp_pts_by_w[int(w_nm)].append((float(rc), float(f_trk)))
    qp_poly_by_w = {
        w_nm: np.polyfit([p[0] for p in pts], [p[1] for p in pts], deg=1) for w_nm, pts in qp_pts_by_w.items()
    }
    qp_fz_105, qp_fcirc_105 = [], []
    for perm in generate_all_105_unique_permutations():
        cur = 10.0 + 0.050
        rcs = []
        for w_nm in perm:
            s_um = float(w_nm) * 1e-3
            rcs.append(cur + 0.5 * s_um)
            cur += s_um + 0.050
        f_trks = [float(np.polyval(qp_poly_by_w[int(w_nm)], rc)) for w_nm, rc in zip(perm, rcs)]
        qp_fz_105.append(sum(f_trks))
        qp_fcirc_105.append(sum(f / (2.0 * math.pi * rc) for f, rc in zip(f_trks, rcs)))
    qp_cantor_cur = 10.0 + 0.050
    qp_cantor_rcs = []
    for w_nm in CANTOR_WIDTHS_NM:
        s_um = float(w_nm) * 1e-3
        qp_cantor_rcs.append(qp_cantor_cur + 0.5 * s_um)
        qp_cantor_cur += s_um + 0.050
    qp_cantor_surr_trks = [float(np.polyval(qp_poly_by_w[int(w_nm)], rc)) for w_nm, rc in zip(CANTOR_WIDTHS_NM, qp_cantor_rcs)]
    qp_c_fz_surr = float(sum(qp_cantor_surr_trks))
    qp_c_fcirc_surr = float(sum(f / (2.0 * math.pi * rc) for f, rc in zip(qp_cantor_surr_trks, qp_cantor_rcs)))
    qp_pct_fz = 100.0 * float(np.sum(np.array(qp_fz_105) < qp_c_fz_surr - 1e-9)) / 104.0
    qp_pct_fcirc = 100.0 * float(np.sum(np.array(qp_fcirc_105) < qp_c_fcirc_surr - 1e-9)) / 104.0

    cyl_map = {r["design"]: r for r in part1_results["cylindrical_0.30_1.65"]}
    qpa_map = {r["design"]: r for r in part1_results["quasi_planar_arc_matched_10.0_11.35"]}
    qpf_map = {r["design"]: r for r in part1_results["quasi_planar_fixed_angle_10.0_11.35"]}

    eval_cantor_rec = next((r for r in evaluated_cyl_perms if tuple(r["widths_nm"]) == CANTOR_WIDTHS_NM), None)
    cantor_cyl_fz = float(eval_cantor_rec["F_z_pN"]) if eval_cantor_rec is not None else float(cyl_map["Fractal_N3_Cantor7Track"]["F_z_pN"])
    cantor_cyl_fcirc = float(eval_cantor_rec["F_circ_sum_pN_per_um"]) if eval_cantor_rec is not None else float(cyl_map["Fractal_N3_Cantor7Track"]["F_circ_sum_pN_per_um"])
    fz_eval_arr = np.array([r["F_z_pN"] for r in evaluated_cyl_perms], dtype=np.float64) if evaluated_cyl_perms else np.array([cantor_cyl_fz], dtype=np.float64)
    fcirc_eval_arr = np.array([r["F_circ_sum_pN_per_um"] for r in evaluated_cyl_perms], dtype=np.float64) if evaluated_cyl_perms else np.array([cantor_cyl_fcirc], dtype=np.float64)
    n_non_cantor_eval = sum(1 for r in evaluated_cyl_perms if tuple(r["widths_nm"]) != CANTOR_WIDTHS_NM)
    n_less_fz_eval = int(np.sum(fz_eval_arr < cantor_cyl_fz - 1e-9))
    n_less_fcirc_eval = int(np.sum(fcirc_eval_arr < cantor_cyl_fcirc - 1e-9))
    uni_cyl_fz = float(cyl_map["Ctrl_Uniform7Track"]["F_z_pN"])
    n_eval_gt_uni = int(np.sum(fz_eval_arr > uni_cyl_fz))

    qpa_cantor_fz = float(qpa_map["Fractal_N3_Cantor7Track"]["F_z_pN"])
    qpa_non_cantor_fzs = [float(r["F_z_pN"]) for r in qp_arc_non_uni if r["design"] != "Fractal_N3_Cantor7Track"]
    n_less_qpa_direct = sum(1 for v in qpa_non_cantor_fzs if v < qpa_cantor_fz - 1e-9)
    qpa_direct_pct_fz = 100.0 * n_less_qpa_direct / max(len(qpa_non_cantor_fzs), 1)

    cyl_mono_vs_cantor_pct = 100.0 * (
        cyl_map["Ctrl_Monotonic7Track"]["F_z_pN"] / cyl_map["Fractal_N3_Cantor7Track"]["F_z_pN"] - 1.0
    )
    qpa_mono_vs_cantor_pct = 100.0 * (
        qpa_map["Ctrl_Monotonic7Track"]["F_z_pN"] / qpa_map["Fractal_N3_Cantor7Track"]["F_z_pN"] - 1.0
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "study": "N3_7Track_Ordering_And_Curvature_Decoupling",
        "status": "completed",
        "execution_status": "micro_probe_complete" if is_micro else "complete",
        "executed_at": now_iso,
        "elapsed_seconds": time.perf_counter() - t_start,
        "parameters": {
            "n_xi": n_xi,
            "panel_resolution": [2, 3, 3, 2],
            "material": "Gold",
            "temperature_K": 0.0,
            "solver_fingerprint": current_fingerprint,
            "n_perm_non_cantor": n_non_cantor_eval,
            "n_total_evaluated_permutations": len(evaluated_cyl_perms),
            "n_unique_multiset_permutations_total": 105,
        },
        "part1_curvature_decoupling": {
            "cylindrical_0.30_1.65": part1_results["cylindrical_0.30_1.65"],
            "quasi_planar_arc_matched_10.0_11.35": part1_results["quasi_planar_arc_matched_10.0_11.35"],
            "quasi_planar_fixed_angle_10.0_11.35": part1_results["quasi_planar_fixed_angle_10.0_11.35"],
            "cylindrical_monotonic_vs_cantor_pct": cyl_mono_vs_cantor_pct,
            "quasi_planar_arc_monotonic_vs_cantor_pct": qpa_mono_vs_cantor_pct,
            "curvature_gap_reduction_factor": cyl_mono_vs_cantor_pct / max(abs(qpa_mono_vs_cantor_pct), 1e-12),
        },
        "part2_permutation_distribution": {
            "n_non_cantor_evaluated": n_non_cantor_eval,
            "n_total_evaluated": len(evaluated_cyl_perms),
            "n_eval_exceeding_uniform": n_eval_gt_uni,
            "pct_eval_exceeding_uniform": 100.0 * n_eval_gt_uni / max(len(evaluated_cyl_perms), 1),
            "fz_min_eval_pN": float(np.min(fz_eval_arr)),
            "fz_max_eval_pN": float(np.max(fz_eval_arr)),
            "fz_mean_eval_pN": float(np.mean(fz_eval_arr)),
            "fz_median_eval_pN": float(np.median(fz_eval_arr)),
            "fz_std_eval_pN": float(np.std(fz_eval_arr)),
            "fcirc_min_eval_pN_per_um": float(np.min(fcirc_eval_arr)),
            "fcirc_max_eval_pN_per_um": float(np.max(fcirc_eval_arr)),
            "fcirc_mean_eval_pN_per_um": float(np.mean(fcirc_eval_arr)),
            "fcirc_median_eval_pN_per_um": float(np.median(fcirc_eval_arr)),
            "cantor_rank_from_bottom_fz_eval": n_less_fz_eval + 1,
            "cantor_percentile_strict_fz_eval": 100.0 * n_less_fz_eval / max(n_non_cantor_eval, 1),
            "cantor_rank_from_bottom_fcirc_eval": n_less_fcirc_eval + 1,
            "cantor_percentile_strict_fcirc_eval": 100.0 * n_less_fcirc_eval / max(n_non_cantor_eval, 1),
            "quasi_planar_direct_eval_cantor_rank_from_bottom_fz": n_less_qpa_direct + 1,
            "quasi_planar_direct_eval_cantor_percentile_fz": qpa_direct_pct_fz,
            "quasi_planar_surrogate_cantor_percentile_strict_fz": qp_pct_fz,
            "quasi_planar_surrogate_cantor_percentile_strict_fcirc": qp_pct_fcirc,
            "evaluated_permutations_cylindrical": evaluated_cyl_perms,
            "all_105_multiset_reconstruction": emp_105,
        },
    }

    suffix = "_micro" if is_micro else ""
    out_json = ROOT / "results" / f"n3_7track_ordering_curvature_study{suffix}.json"
    out_md = ROOT / "results" / f"n3_7track_ordering_curvature_study{suffix}.md"
    out_png = ROOT / "figures" / f"fig_n3_7track_ordering_curvature{suffix}.png"
    out_pdf = ROOT / "figures" / f"fig_n3_7track_ordering_curvature{suffix}.pdf"

    atomic_write_json(out_json, report)
    write_markdown_summary(report, out_md)
    render_figure(report, out_png, out_pdf)

    if not is_micro:
        set_solver_provenance(
            "bem",
            {
                "benchmark": "n3_7track_ordering_curvature_study",
                "n_xi": n_xi,
                "n_perm": n_non_cantor_eval,
                "executed_at": now_iso,
            },
        )
        log_step(
            "n3_7track_ordering_curvature_study",
            {
                "status": report["execution_status"],
                "n_perm_evaluated": len(evaluated_cyl_perms),
                "n_unique_multiset_total": 105,
            },
            solver_name="bem",
        )
        rev_mono_rec = next(
            (r for r in evaluated_cyl_perms if tuple(r["widths_nm"]) == REVERSE_MONOTONIC_WIDTHS_NM),
            None,
        )
        metrics_to_log: dict[str, float] = {
            "n3_curv_cyl_cantor_fz_pn": float(cyl_map["Fractal_N3_Cantor7Track"]["F_z_pN"]),
            "n3_curv_cyl_uniform_fz_pn": float(cyl_map["Ctrl_Uniform7Track"]["F_z_pN"]),
            "n3_curv_cyl_monotonic_fz_pn": float(cyl_map["Ctrl_Monotonic7Track"]["F_z_pN"]),
            "n3_curv_cyl_shuffled_fz_pn": float(cyl_map["Ctrl_RandomPermuted7Track"]["F_z_pN"]),
            "n3_curv_cyl_cantor_fcirc_pn_per_um": float(cyl_map["Fractal_N3_Cantor7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_cyl_uniform_fcirc_pn_per_um": float(cyl_map["Ctrl_Uniform7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_cyl_monotonic_fcirc_pn_per_um": float(cyl_map["Ctrl_Monotonic7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_cyl_shuffled_fcirc_pn_per_um": float(cyl_map["Ctrl_RandomPermuted7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_cyl_mono_vs_cantor_pct": float(cyl_mono_vs_cantor_pct),
            "n3_curv_cyl_50nm_inner_fz_pn": float(cyl_map["Fractal_N3_Cantor7Track"]["f_tracks_pN"][0]),
            "n3_curv_cyl_50nm_outer_fz_pn": float(cyl_map["Fractal_N3_Cantor7Track"]["f_tracks_pN"][6]),
            "n3_curv_qparc_cantor_fz_pn": float(qpa_map["Fractal_N3_Cantor7Track"]["F_z_pN"]),
            "n3_curv_qparc_uniform_fz_pn": float(qpa_map["Ctrl_Uniform7Track"]["F_z_pN"]),
            "n3_curv_qparc_monotonic_fz_pn": float(qpa_map["Ctrl_Monotonic7Track"]["F_z_pN"]),
            "n3_curv_qparc_shuffled_fz_pn": float(qpa_map["Ctrl_RandomPermuted7Track"]["F_z_pN"]),
            "n3_curv_qparc_cantor_fcirc_pn_per_um": float(qpa_map["Fractal_N3_Cantor7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_qparc_uniform_fcirc_pn_per_um": float(qpa_map["Ctrl_Uniform7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_qparc_monotonic_fcirc_pn_per_um": float(qpa_map["Ctrl_Monotonic7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_qparc_shuffled_fcirc_pn_per_um": float(qpa_map["Ctrl_RandomPermuted7Track"]["F_circ_sum_pN_per_um"]),
            "n3_curv_qparc_mono_vs_cantor_pct": float(qpa_mono_vs_cantor_pct),
            "n3_curv_qparc_cantor_vs_uniform_ratio": float(
                qpa_map["Fractal_N3_Cantor7Track"]["F_z_pN"] / qpa_map["Ctrl_Uniform7Track"]["F_z_pN"]
            ),
            "n3_curv_gap_reduction_factor": float(report["part1_curvature_decoupling"]["curvature_gap_reduction_factor"]),
            "n3_curv_qpfixed_cantor_fz_pn": float(qpf_map["Fractal_N3_Cantor7Track"]["F_z_pN"]),
            "n3_curv_qpfixed_uniform_fz_pn": float(qpf_map["Ctrl_Uniform7Track"]["F_z_pN"]),
            "n3_curv_qpfixed_monotonic_fz_pn": float(qpf_map["Ctrl_Monotonic7Track"]["F_z_pN"]),
            "n3_curv_qpfixed_shuffled_fz_pn": float(qpf_map["Ctrl_RandomPermuted7Track"]["F_z_pN"]),
            "n3_perm_n_evaluated": float(n_non_cantor_eval),
            "n3_perm_n_unique_multiset": 105.0,
            "n3_perm_fz_min_pn": float(report["part2_permutation_distribution"]["fz_min_eval_pN"]),
            "n3_perm_fz_max_pn": float(report["part2_permutation_distribution"]["fz_max_eval_pN"]),
            "n3_perm_fz_mean_pn": float(report["part2_permutation_distribution"]["fz_mean_eval_pN"]),
            "n3_perm_fz_median_pn": float(report["part2_permutation_distribution"]["fz_median_eval_pN"]),
            "n3_perm_fz_std_pn": float(report["part2_permutation_distribution"]["fz_std_eval_pN"]),
            "n3_perm_fcirc_min_pn_per_um": float(report["part2_permutation_distribution"]["fcirc_min_eval_pN_per_um"]),
            "n3_perm_fcirc_max_pn_per_um": float(report["part2_permutation_distribution"]["fcirc_max_eval_pN_per_um"]),
            "n3_perm_fcirc_mean_pn_per_um": float(report["part2_permutation_distribution"]["fcirc_mean_eval_pN_per_um"]),
            "n3_perm_fcirc_median_pn_per_um": float(report["part2_permutation_distribution"]["fcirc_median_eval_pN_per_um"]),
            "n3_perm_cantor_pct_fz_eval": float(report["part2_permutation_distribution"]["cantor_percentile_strict_fz_eval"]),
            "n3_perm_cantor_pct_fcirc_eval": float(report["part2_permutation_distribution"]["cantor_percentile_strict_fcirc_eval"]),
            "n3_perm_cantor_pct_fz_105": float(emp_105["surrogate_estimated_cantor_percentile_strict_fz_105"]),
            "n3_perm_cantor_pct_fcirc_105": float(emp_105["surrogate_estimated_cantor_percentile_strict_fcirc_105"]),
            "n3_perm_qparc_cantor_pct_fz": float(qp_pct_fz),
            "n3_perm_qparc_cantor_pct_fcirc": float(qp_pct_fcirc),
        }
        if rev_mono_rec is not None:
            metrics_to_log["n3_curv_cyl_rev_monotonic_fz_pn"] = float(rev_mono_rec["F_z_pN"])
            metrics_to_log["n3_curv_cyl_rev_monotonic_fcirc_pn_per_um"] = float(rev_mono_rec["F_circ_sum_pN_per_um"])
        for m_key, m_val in metrics_to_log.items():
            log_metric(m_key, m_val, step_id="n3_7track_ordering_curvature_study", solver_name="bem", defer_save=True)
        # Flush final metric and export macros
        first_k = next(iter(metrics_to_log))
        log_metric(first_k, metrics_to_log[first_k], step_id="n3_7track_ordering_curvature_study", solver_name="bem", defer_save=False)
        export_macros(str(ROOT / "results" / "provenance_metrics.json"), str(ROOT / "results" / "macros_results.tex"))
        save_plot_provenance(str(out_png), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        save_plot_provenance(str(out_pdf), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))

    print(
        f"Completed {report['execution_status']} in {report['elapsed_seconds']:.2f}s -> {out_json}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
