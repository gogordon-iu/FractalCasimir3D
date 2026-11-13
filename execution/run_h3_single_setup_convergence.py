#!/usr/bin/env python3
"""
execution/run_h3_single_setup_convergence.py

First-principles single-setup 3D BEM + 4-pass 3D Meep FDTD quantitative
convergence suite for the H3-Cantor architecture (fce_nature_ver10).

Both solvers evaluate the exact same 3D Cartesian H3-Cantor unit-cell geometry
on an exact 20 nm Yee lattice (`geometry_mode="explicit_boxes_3d"` in Meep FDTD;
watertight Rao-Wilton-Glisson surface triangulation in Maxwell BEM) across:
  1. Two kinematic switching states (4x C_4 symmetry multiplier):
     - `open_repulsive`: rotor lobe between elevated flanking stator slot collars
       (+F_z > 0 normal repulsion).
     - `engaged_attractive`: rotor lobe above stepped stator landing pad
       (-F_z < 0 normal attraction).
  2. Two material models with algebraically identical imaginary-frequency
     permittivity eps(i*kappa):
     - `PEC`: exact RWG EFIE in BEM; `mp.metal` in Meep FDTD.
     - `Gold_Drude`: exact RWG PMCHWT in BEM; single-pole Drude medium
       (hbar*omega_p = 9.03 eV, hbar*gamma = 0.053 eV, eps_inf = 1.0) in Meep FDTD.

Modes:
  --max-steps N            Empirical micro-probe for hpc_gate.py profiling.
  --generate-fdtd-configs  Generate sweep_configs_h3_single_setup_fdtd/config_001..017.json.
  --run-bem                Run 4-tier RWG Maxwell BEM convergence + canonical checks.
  --aggregate              Merge BEM + FDTD results, log provenance macros, render
                           6-panel figure + sidecar, and write LaTeX convergence table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.casimir_bem_solver import (
    ClutchSurfaceMesh,
    DenseBackend,
    MaterialModel,
    _panel,
    _vector_dyadic_blocks,
)
from execution.materials_database_dispersive import (
    GOLD_EPS_INF,
    GOLD_GAMMA_EV,
    GOLD_WP_EV,
    HBAR_C_EV_UM,
    MEEP_FORCE_TO_SI,
)
from utils.metrics_logger import (
    _sanitize_macro_name,
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

MEEP_FORCE_TO_PN: float = float(MEEP_FORCE_TO_SI * 1e12)  # 3.16152649e-2 pN
SYMMETRY_MULTIPLIER: float = 4.0

GOLD_KAPPA_P_UM_INV: float = float(GOLD_WP_EV / HBAR_C_EV_UM)
GOLD_GAMMA_UM_INV: float = float(GOLD_GAMMA_EV / HBAR_C_EV_UM)

# =============================================================================
# Shared 20 nm-Lattice 3D H3-Cantor Single-Setup Geometry (um)
# Every coordinate is an integer multiple of 0.020 um -> exact Yee grid planes
# at ALL resolutions R in {100, 150, 200, 250} px/um (dx = 10, 6.67, 5, 4 nm)!
# =============================================================================
ROTOR_LOBE_BOX_UM: tuple[float, float, float, float, float, float] = (
    -0.020,
    0.020,
    -0.040,
    0.040,
    -0.080,
    -0.040,
)
STRESS_BOX_UM: tuple[float, float, float, float, float, float] = (
    -0.040,
    0.040,
    -0.080,
    0.080,
    -0.100,
    -0.020,
)
OPEN_STATOR_COLLAR_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.080, -0.060, -0.120, 0.120, -0.060, -0.020),
    (0.060, 0.080, -0.120, 0.120, -0.060, -0.020),
)
ENGAGED_STATOR_PAD_BOXES_UM: tuple[tuple[float, float, float, float, float, float], ...] = (
    (-0.060, 0.060, -0.100, 0.100, -0.160, -0.120),
)
EXPLICIT_CELL_CENTER_UM: tuple[float, float, float] = (0.0, 0.0, -0.060)
EXPLICIT_PHYS_BOUNDS_UM: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] = (
    (-0.080, 0.080),
    (-0.120, 0.120),
    (-0.180, 0.060),
)
D_EFF_SINGLE_SETUP_UM: float = 0.040
CELL_BUFFER_SINGLE_SETUP_UM: float = 0.080
PML_THICKNESS_SINGLE_SETUP_UM: float = 0.160
T_RUN_SINGLE_SETUP: float = 4.0

# 7-point symmetric degree-5 Dunavant triangle quadrature
DUNAVANT_7_BARY = np.array(
    [
        [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0],
        [0.059715871789770, 0.470142064105115, 0.470142064105115],
        [0.470142064105115, 0.059715871789770, 0.470142064105115],
        [0.470142064105115, 0.470142064105115, 0.059715871789770],
        [0.797426985353087, 0.101286507323456, 0.101286507323456],
        [0.101286507323456, 0.797426985353087, 0.101286507323456],
        [0.101286507323456, 0.101286507323456, 0.797426985353087],
    ],
    dtype=np.float64,
)
DUNAVANT_7_W = np.array(
    [
        0.225000000000000,
        0.132394152788506,
        0.132394152788506,
        0.132394152788506,
        0.125939180544827,
        0.125939180544827,
        0.125939180544827,
    ],
    dtype=np.float64,
)
DUNAVANT_7_W /= float(np.sum(DUNAVANT_7_W))

BEM_MESH_TIERS: tuple[dict[str, Any], ...] = (
    {
        "tier": 1,
        "label": "Tier 1 (coarse)",
        "rotor_sub": (2, 3, 2),
        "collar_sub": (1, 6, 2),
        "pad_sub": (3, 5, 2),
    },
    {
        "tier": 2,
        "label": "Tier 2 (medium)",
        "rotor_sub": (3, 4, 3),
        "collar_sub": (2, 8, 3),
        "pad_sub": (4, 6, 2),
    },
    {
        "tier": 3,
        "label": "Tier 3 (fine)",
        "rotor_sub": (4, 6, 3),
        "collar_sub": (2, 10, 3),
        "pad_sub": (5, 8, 3),
    },
    {
        "tier": 4,
        "label": "Tier 4 (ultra-fine)",
        "rotor_sub": (5, 8, 4),
        "collar_sub": (3, 12, 4),
        "pad_sub": (6, 10, 3),
    },
)


@dataclass(frozen=True)
class FDTDSweepSpec:
    task_id: int
    label: str
    state: str  # "open_repulsive" | "engaged_attractive"
    material: str  # "PEC" | "Gold_Drude"
    resolution: int
    nmax: int


FDTD_SWEEP_SPECS: tuple[FDTDSweepSpec, ...] = (
    # Open-slot repulsive PEC resolution ladder (R = 100, 150, 200, 250)
    FDTDSweepSpec(1, "h3_ss_open_pec_R100_nmax2", "open_repulsive", "PEC", 100, 2),
    FDTDSweepSpec(2, "h3_ss_open_pec_R150_nmax2", "open_repulsive", "PEC", 150, 2),
    FDTDSweepSpec(3, "h3_ss_open_pec_R200_nmax2", "open_repulsive", "PEC", 200, 2),
    FDTDSweepSpec(4, "h3_ss_open_pec_R250_nmax2", "open_repulsive", "PEC", 250, 2),
    # Source harmonic truncation controls (nmax = 1, 3 at R=150 and nmax = 3 at R=200)
    FDTDSweepSpec(5, "h3_ss_open_pec_R150_nmax1", "open_repulsive", "PEC", 150, 1),
    FDTDSweepSpec(6, "h3_ss_open_pec_R150_nmax3", "open_repulsive", "PEC", 150, 3),
    FDTDSweepSpec(7, "h3_ss_open_pec_R200_nmax3", "open_repulsive", "PEC", 200, 3),
    # Engaged landing-pad attractive PEC resolution ladder (R = 100, 150, 200, 250)
    FDTDSweepSpec(8, "h3_ss_eng_pec_R100_nmax2", "engaged_attractive", "PEC", 100, 2),
    FDTDSweepSpec(9, "h3_ss_eng_pec_R150_nmax2", "engaged_attractive", "PEC", 150, 2),
    FDTDSweepSpec(10, "h3_ss_eng_pec_R200_nmax2", "engaged_attractive", "PEC", 200, 2),
    FDTDSweepSpec(11, "h3_ss_eng_pec_R250_nmax2", "engaged_attractive", "PEC", 250, 2),
    # Open-slot repulsive Gold_Drude resolution ladder (R = 100, 150, 200)
    FDTDSweepSpec(12, "h3_ss_open_gold_R100_nmax2", "open_repulsive", "Gold_Drude", 100, 2),
    FDTDSweepSpec(13, "h3_ss_open_gold_R150_nmax2", "open_repulsive", "Gold_Drude", 150, 2),
    FDTDSweepSpec(14, "h3_ss_open_gold_R200_nmax2", "open_repulsive", "Gold_Drude", 200, 2),
    # Engaged landing-pad attractive Gold_Drude resolution ladder (R = 100, 150, 200)
    FDTDSweepSpec(15, "h3_ss_eng_gold_R100_nmax2", "engaged_attractive", "Gold_Drude", 100, 2),
    FDTDSweepSpec(16, "h3_ss_eng_gold_R150_nmax2", "engaged_attractive", "Gold_Drude", 150, 2),
    FDTDSweepSpec(17, "h3_ss_eng_gold_R200_nmax2", "engaged_attractive", "Gold_Drude", 200, 2),
)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_str, str(path))
    except Exception:
        try:
            os.unlink(tmp_str)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp_str, str(path))
    except Exception:
        try:
            os.unlink(tmp_str)
        except OSError:
            pass
        raise


def resolve_torch_device(device_arg: str = "auto") -> torch.device:
    if device_arg == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("Requested --device cuda, but CUDA is unavailable.")
        return torch.device("cuda")
    if device_arg == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def gold_drude_eps(kappa_um_inv: float) -> float:
    """Exact imaginary-wavenumber Gold_Drude permittivity matching Meep FDTD."""
    return float(
        GOLD_EPS_INF + (GOLD_KAPPA_P_UM_INV**2) / (kappa_um_inv * (kappa_um_inv + GOLD_GAMMA_UM_INV))
    )


def lifshitz_infinite_plate_ratio_gold_over_pec(d_um: float) -> float:
    """Zero-temperature Lifshitz force ratio F_Gold(d) / F_PEC(d) for semi-infinite plates."""
    nodes_k, w_k = np.polynomial.legendre.leggauss(64)
    nodes_s, w_s = np.polynomial.legendre.leggauss(64)
    uk, wuk = 0.5 * (nodes_k + 1.0), 0.5 * w_k
    us, wus = 0.5 * (nodes_s + 1.0), 0.5 * w_s
    k0 = 1.0 / d_um
    kappas = k0 * uk / (1.0 - uk)
    wkappas = wuk * k0 / ((1.0 - uk) ** 2)
    s_vals = k0 * us / (1.0 - us)
    ws_vals = wus * k0 / ((1.0 - us) ** 2)

    f_gold = 0.0
    f_pec = 0.0
    for kap, wk in zip(kappas, wkappas):
        eps = gold_drude_eps(float(kap))
        p = kap + s_vals
        s_in = np.sqrt(p**2 + (eps - 1.0) * (kap**2))
        r_te = (p - s_in) / (p + s_in)
        r_tm = (eps * p - s_in) / (eps * p + s_in)
        exp_fac = np.exp(-2.0 * p * d_um)
        term_gold = (r_te**2 * exp_fac) / (1.0 - r_te**2 * exp_fac) + (
            r_tm**2 * exp_fac
        ) / (1.0 - r_tm**2 * exp_fac)
        term_pec = 2.0 * exp_fac / (1.0 - exp_fac)
        f_gold += float(wk) * float(np.sum(ws_vals * (p**2) * term_gold))
        f_pec += float(wk) * float(np.sum(ws_vals * (p**2) * term_pec))
    return float(f_gold / f_pec)


# =============================================================================
# Analytical Wilton Potential + Polar Self-Triangle Helmholtz Integrals
# =============================================================================
def wilton_potential_batch(pts: np.ndarray, tri_verts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact analytic 1/(4*pi*R) scalar & vector moments over source triangles."""
    v0 = tri_verts[:, 0, :]
    v1 = tri_verts[:, 1, :]
    v2 = tri_verts[:, 2, :]
    normal_raw = np.cross(v1 - v0, v2 - v0)
    area2 = np.linalg.norm(normal_raw, axis=1)
    n_hat = normal_raw / area2[:, None]

    r_rel0 = pts[:, None, :] - v0[None, :, :]
    d = np.einsum("mtk,tk->mt", r_rel0, n_hat)
    abs_d = np.abs(d)
    r_proj = pts[:, None, :] - d[:, :, None] * n_hat[None, :, :]

    I_sub = np.zeros((pts.shape[0], tri_verts.shape[0]), dtype=np.float64)
    I_grad_tan = np.zeros((pts.shape[0], tri_verts.shape[0], 3), dtype=np.float64)

    for idx_m, idx_p in ((0, 1), (1, 2), (2, 0)):
        p_m = tri_verts[:, idx_m, :]
        p_p = tri_verts[:, idx_p, :]
        edge = p_p - p_m
        L_edge = np.linalg.norm(edge, axis=1)
        l_hat = edge / L_edge[:, None]
        u_hat = np.cross(l_hat, n_hat)

        rho_m = p_m[None, :, :] - r_proj
        rho_p = p_p[None, :, :] - r_proj
        P0 = np.einsum("mtk,tk->mt", rho_m, u_hat)
        l_m = np.einsum("mtk,tk->mt", rho_m, l_hat)
        l_p = np.einsum("mtk,tk->mt", rho_p, l_hat)

        R_m = np.sqrt(np.sum(rho_m**2, axis=2) + d**2)
        R_p = np.sqrt(np.sum(rho_p**2, axis=2) + d**2)
        R0_sq = P0**2 + d**2

        safe_num = np.where(l_p >= 0.0, R_p + l_p, R0_sq / np.maximum(R_p - l_p, 1e-300))
        safe_den = np.where(l_m >= 0.0, R_m + l_m, R0_sq / np.maximum(R_m - l_m, 1e-300))
        log_term = np.where(
            R0_sq > 1e-28,
            np.log(np.maximum(safe_num / np.maximum(safe_den, 1e-300), 1e-300)),
            0.0,
        )
        beta = np.arctan2(P0 * l_p, R0_sq + abs_d * R_p) - np.arctan2(
            P0 * l_m, R0_sq + abs_d * R_m
        )

        I_sub += P0 * log_term - abs_d * beta
        line_moment = 0.5 * (R0_sq * log_term + l_p * R_p - l_m * R_m)
        I_grad_tan += line_moment[:, :, None] * u_hat[None, :, :]

    I_scalar = I_sub / (4.0 * math.pi)
    I_vec = r_proj * I_scalar[:, :, None] + I_grad_tan / (4.0 * math.pi)
    return I_scalar, I_vec


class RWGMeshTorch:
    """Watertight RWG triangulated mesh with precomputed device tensors for fast batched solves."""

    def __init__(self, vertices: np.ndarray, triangles: np.ndarray, device: torch.device):
        self.device = device
        self.vertices = np.asarray(vertices, dtype=np.float64)
        self.triangles = np.asarray(triangles, dtype=np.int64)
        self.n_tri = int(self.triangles.shape[0])
        self.tri_verts = self.vertices[self.triangles]  # (T, 3, 3)

        e1 = self.tri_verts[:, 1] - self.tri_verts[:, 0]
        e2 = self.tri_verts[:, 2] - self.tri_verts[:, 0]
        normals_raw = np.cross(e1, e2)
        self.areas = 0.5 * np.linalg.norm(normals_raw, axis=1)
        self.normals = normals_raw / (2.0 * self.areas[:, None])

        edge_map: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
        for t_idx, (a, b, c) in enumerate(self.triangles):
            for loc_opp, (u, v) in ((0, (b, c)), (1, (c, a)), (2, (a, b))):
                key = (min(int(u), int(v)), max(int(u), int(v)))
                orient = +1 if int(u) < int(v) else -1
                edge_map.setdefault(key, []).append((t_idx, int(loc_opp), orient))

        tri_plus, tri_minus, opp_plus, opp_minus, edge_len = [], [], [], [], []
        for (u, v), entries in sorted(edge_map.items()):
            if len(entries) != 2:
                raise ValueError(f"Non-manifold edge {(u, v)} shared by {len(entries)} triangles.")
            (t0, o0, s0), (t1, o1, s1) = entries
            if s0 == s1:
                raise ValueError(f"Inconsistent orientation on edge {(u, v)}.")
            if s0 > 0:
                tp, op, tm, om = t0, o0, t1, o1
            else:
                tp, op, tm, om = t1, o1, t0, o0
            tri_plus.append(tp)
            opp_plus.append(op)
            tri_minus.append(tm)
            opp_minus.append(om)
            edge_len.append(float(np.linalg.norm(self.vertices[v] - self.vertices[u])))

        self.n_rwg = len(edge_len)
        self.tri_plus = np.array(tri_plus, dtype=np.int64)
        self.tri_minus = np.array(tri_minus, dtype=np.int64)
        self.opp_plus = np.array(opp_plus, dtype=np.int64)
        self.opp_minus = np.array(opp_minus, dtype=np.int64)
        self.edge_len = np.array(edge_len, dtype=np.float64)
        self.v_opp_plus = self.tri_verts[self.tri_plus, self.opp_plus]
        self.v_opp_minus = self.tri_verts[self.tri_minus, self.opp_minus]

        self.q_pts = np.einsum("qk,tkd->tqd", DUNAVANT_7_BARY, self.tri_verts)  # (T, 7, 3)
        self.q_wts = self.areas[:, None] * DUNAVANT_7_W[None, :]  # (T, 7)

        pts_flat = self.q_pts.reshape(-1, 3)
        I_s, I_v = wilton_potential_batch(pts_flat, self.tri_verts)
        I_s = I_s.reshape(self.n_tri, 7, self.n_tri)
        I_v = I_v.reshape(self.n_tri, 7, self.n_tri, 3)
        S0_scalar = np.einsum("tq,tqs->ts", self.q_wts, I_s)
        S0_rprime = np.einsum("tq,tqsd->tsd", self.q_wts, I_v)
        S0_r = np.einsum("tq,tqd,tqs->tsd", self.q_wts, self.q_pts, I_s)
        S0_rdotr = np.einsum("tq,tqd,tqsd->ts", self.q_wts, self.q_pts, I_v)

        # Precompute pairwise quadrature distances & coplanar masks ONCE on device
        diff_np = pts_flat[:, None, :] - pts_flat[None, :, :]
        R_np = np.linalg.norm(diff_np, axis=2)
        R_tri_min = R_np.reshape(self.n_tri, 7, self.n_tri, 7).min(axis=(1, 3))
        coplanar_tri = np.abs(np.abs(self.normals @ self.normals.T) - 1.0) < 1e-12
        non_coplanar_q = np.repeat(np.repeat(~coplanar_tri, 7, axis=0), 7, axis=1) & (R_np > 1e-12)

        # Precompute polar self-triangle geometry (T, 7, 3_edges, 16_gl)
        gl_nodes, gl_weights = np.polynomial.legendre.leggauss(16)
        u_gl = 0.5 * (gl_nodes + 1.0)
        w_gl = 0.5 * gl_weights

        pol_rho_max = np.zeros((self.n_tri, 7, 3, 16), dtype=np.float64)
        pol_wt_ang = np.zeros((self.n_tri, 7, 3, 16), dtype=np.float64)
        pol_dir_vec = np.zeros((self.n_tri, 7, 3, 16, 3), dtype=np.float64)
        for e_idx, (idx_m, idx_p) in enumerate(((0, 1), (1, 2), (2, 0))):
            p_m = self.tri_verts[:, idx_m, :]
            p_p = self.tri_verts[:, idx_p, :]
            edge = p_p - p_m
            l_hat = edge / np.linalg.norm(edge, axis=1)[:, None]
            u_hat = np.cross(l_hat, self.normals)
            rho_m = p_m[:, None, :] - self.q_pts
            rho_p = p_p[:, None, :] - self.q_pts
            P0 = np.einsum("tqd,td->tq", rho_m, u_hat)
            l_m = np.einsum("tqd,td->tq", rho_m, l_hat)
            l_p = np.einsum("tqd,td->tq", rho_p, l_hat)
            th_m = np.arctan2(l_m, P0)
            th_p = np.arctan2(l_p, P0)
            dth = th_p - th_m
            th = th_m[:, :, None] + dth[:, :, None] * u_gl[None, None, :]
            cos_th = np.cos(th)
            sin_th = np.sin(th)
            pol_rho_max[:, :, e_idx, :] = P0[:, :, None] / np.maximum(cos_th, 1e-15)
            pol_wt_ang[:, :, e_idx, :] = dth[:, :, None] * w_gl[None, None, :]
            pol_dir_vec[:, :, e_idx, :, :] = (
                cos_th[:, :, :, None] * u_hat[:, None, None, :]
                + sin_th[:, :, :, None] * l_hat[:, None, None, :]
            )

        # Store tensors on device
        self.q_pts_t = torch.as_tensor(self.q_pts, dtype=torch.float64, device=device)
        self.q_wts_t = torch.as_tensor(self.q_wts, dtype=torch.float64, device=device)
        self.wts_pair_t = torch.as_tensor(
            self.q_wts.reshape(-1)[:, None] * self.q_wts.reshape(-1)[None, :],
            dtype=torch.float64,
            device=device,
        )
        self.diff_t = torch.as_tensor(diff_np, dtype=torch.float64, device=device)
        self.R_t = torch.as_tensor(R_np, dtype=torch.float64, device=device)
        self.R_tri_min_t = torch.as_tensor(R_tri_min, dtype=torch.float64, device=device)
        self.non_coplanar_q_t = torch.as_tensor(non_coplanar_q, dtype=torch.bool, device=device)

        self.S0_scalar_t = torch.as_tensor(S0_scalar, dtype=torch.float64, device=device)
        self.S0_r_t = torch.as_tensor(S0_r, dtype=torch.float64, device=device)
        self.S0_rp_t = torch.as_tensor(S0_rprime, dtype=torch.float64, device=device)
        self.S0_rdotr_t = torch.as_tensor(S0_rdotr, dtype=torch.float64, device=device)

        self.pol_rho_max_t = torch.as_tensor(pol_rho_max, dtype=torch.float64, device=device)
        self.pol_wt_ang_t = torch.as_tensor(pol_wt_ang, dtype=torch.float64, device=device)
        self.pol_dir_vec_t = torch.as_tensor(pol_dir_vec, dtype=torch.float64, device=device)

        self.sides_t = [
            (
                torch.as_tensor(self.tri_plus, dtype=torch.long, device=device),
                torch.as_tensor(self.v_opp_plus, dtype=torch.float64, device=device),
                torch.as_tensor(self.edge_len / self.areas[self.tri_plus], dtype=torch.float64, device=device),
                torch.as_tensor(0.5 * self.edge_len / self.areas[self.tri_plus], dtype=torch.float64, device=device),
            ),
            (
                torch.as_tensor(self.tri_minus, dtype=torch.long, device=device),
                torch.as_tensor(self.v_opp_minus, dtype=torch.float64, device=device),
                torch.as_tensor(-self.edge_len / self.areas[self.tri_minus], dtype=torch.float64, device=device),
                torch.as_tensor(-0.5 * self.edge_len / self.areas[self.tri_minus], dtype=torch.float64, device=device),
            ),
        ]


def make_closed_box_rwg_mesh(
    box: tuple[float, float, float, float, float, float],
    sub: tuple[int, int, int],
    device: torch.device,
) -> RWGMeshTorch:
    x0, x1, y0, y1, z0, z1 = box
    nx, ny, nz = sub
    xs = np.linspace(x0, x1, nx + 1)
    ys = np.linspace(y0, y1, ny + 1)
    zs = np.linspace(z0, z1, nz + 1)
    verts: list[tuple[float, float, float]] = []
    vmap: dict[tuple[int, int, int], int] = {}

    def vid(x: float, y: float, z: float) -> int:
        key = (round(x * 1e9), round(y * 1e9), round(z * 1e9))
        if key not in vmap:
            vmap[key] = len(verts)
            verts.append((float(x), float(y), float(z)))
        return vmap[key]

    tris: list[tuple[int, int, int]] = []

    def add_quad(
        p0: tuple[float, float, float],
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
        p3: tuple[float, float, float],
    ) -> None:
        i0, i1, i2, i3 = vid(*p0), vid(*p1), vid(*p2), vid(*p3)
        tris.append((i0, i1, i2))
        tris.append((i0, i2, i3))

    for i in range(nx):
        for j in range(ny):
            add_quad((xs[i], ys[j], z0), (xs[i], ys[j + 1], z0), (xs[i + 1], ys[j + 1], z0), (xs[i + 1], ys[j], z0))
            add_quad((xs[i], ys[j], z1), (xs[i + 1], ys[j], z1), (xs[i + 1], ys[j + 1], z1), (xs[i], ys[j + 1], z1))
    for i in range(nx):
        for k in range(nz):
            add_quad((xs[i], y0, zs[k]), (xs[i + 1], y0, zs[k]), (xs[i + 1], y0, zs[k + 1]), (xs[i], y0, zs[k + 1]))
            add_quad((xs[i], y1, zs[k]), (xs[i], y1, zs[k + 1]), (xs[i + 1], y1, zs[k + 1]), (xs[i + 1], y1, zs[k]))
    for j in range(ny):
        for k in range(nz):
            add_quad((x0, ys[j], zs[k]), (x0, ys[j], zs[k + 1]), (x0, ys[j + 1], zs[k + 1]), (x0, ys[j + 1], zs[k]))
            add_quad((x1, ys[j], zs[k]), (x1, ys[j + 1], zs[k]), (x1, ys[j + 1], zs[k + 1]), (x1, ys[j], zs[k + 1]))

    return RWGMeshTorch(np.array(verts, dtype=np.float64), np.array(tris, dtype=np.int64), device=device)


def make_multi_box_rwg_mesh(
    boxes: Sequence[tuple[float, float, float, float, float, float]],
    sub: tuple[int, int, int],
    device: torch.device,
) -> RWGMeshTorch:
    v_list: list[np.ndarray] = []
    t_list: list[np.ndarray] = []
    v_offset = 0
    for box in boxes:
        m = make_closed_box_rwg_mesh(box, sub, device=torch.device("cpu"))
        v_list.append(m.vertices)
        t_list.append(m.triangles + v_offset)
        v_offset += len(m.vertices)
    return RWGMeshTorch(np.vstack(v_list), np.vstack(t_list), device=device)


def assemble_efie_same_body_torch(mesh: RWGMeshTorch, alpha: float) -> torch.Tensor:
    """Exact RWG EFIE matrix L(alpha) on a single closed body using Torch float64."""
    T = mesh.n_tri
    R = mesh.R_t
    R_safe = torch.clamp(R, min=1e-15)

    # Smooth Wilton subtraction for near/small-alpha pairs; direct exponential for well-separated high-alpha pairs!
    smooth_sub = torch.where(
        R > 1e-12,
        torch.expm1(-alpha * R_safe) / (4.0 * math.pi * R_safe),
        torch.full_like(R, -alpha / (4.0 * math.pi)),
    )
    direct_exp = torch.where(
        R > 1e-12,
        torch.exp(-alpha * R_safe) / (4.0 * math.pi * R_safe),
        torch.zeros_like(R),
    )

    use_direct_tri = (alpha * mesh.R_tri_min_t) > 1.25  # (T, T), strictly False on self/touching triangles
    use_direct_q = use_direct_tri.repeat_interleave(7, dim=0).repeat_interleave(7, dim=1)

    W_sub_4d = (mesh.wts_pair_t * torch.where(use_direct_q, torch.zeros_like(R), smooth_sub)).reshape(T, 7, T, 7)
    W_dir_4d = (mesh.wts_pair_t * torch.where(use_direct_q, direct_exp, torch.zeros_like(R))).reshape(T, 7, T, 7)
    W_tot_4d = W_sub_4d + W_dir_4d
    sub_mask_f = (~use_direct_tri).to(torch.float64)

    G_00 = W_tot_4d.sum(dim=(1, 3)) + sub_mask_f * mesh.S0_scalar_t
    G_r = torch.einsum("tqu,tqd->tud", W_tot_4d.sum(dim=3), mesh.q_pts_t) + sub_mask_f[:, :, None] * mesh.S0_r_t
    G_rp = torch.einsum("tuv,uvd->tud", W_tot_4d.sum(dim=1), mesh.q_pts_t) + sub_mask_f[:, :, None] * mesh.S0_rp_t
    G_rrp = sub_mask_f * mesh.S0_rdotr_t
    for d_idx in range(3):
        p_col = mesh.q_pts_t[:, :, d_idx]
        left = torch.einsum("tq,tquv->tuv", p_col, W_tot_4d)
        G_rrp = G_rrp + torch.einsum("tuv,uv->tu", left, p_col)

    # Exact polar radial antiderivative on self-triangle diagonal (t == u) for ALL alpha in (0, +inf)!
    ar = alpha * mesh.pol_rho_max_t
    rad_0 = torch.where(
        ar > 1e-8,
        -torch.expm1(-ar) / (4.0 * math.pi * alpha),
        mesh.pol_rho_max_t * (1.0 - 0.5 * ar) / (4.0 * math.pi),
    )
    rad_1 = torch.where(
        ar > 1e-5,
        (1.0 - (1.0 + ar) * torch.exp(-ar)) / (4.0 * math.pi * (alpha**2)),
        (mesh.pol_rho_max_t**2) * (0.5 - ar / 3.0 + (ar**2) / 8.0) / (4.0 * math.pi),
    )
    inner_0 = (mesh.pol_wt_ang_t * rad_0).sum(dim=(2, 3))  # (T, 7)
    inner_dr = ((mesh.pol_wt_ang_t * rad_1)[..., None] * mesh.pol_dir_vec_t).sum(dim=(2, 3))  # (T, 7, 3)
    inner_rp = mesh.q_pts_t * inner_0[:, :, None] + inner_dr

    diag_00 = (mesh.q_wts_t * inner_0).sum(dim=1)
    diag_r = torch.einsum("tq,tqd->td", mesh.q_wts_t, mesh.q_pts_t * inner_0[:, :, None])
    diag_rp = torch.einsum("tq,tqd->td", mesh.q_wts_t, inner_rp)
    sym_r = 0.5 * (diag_r + diag_rp)
    diag_rrp = torch.einsum("tq,tqd,tqd->t", mesh.q_wts_t, mesh.q_pts_t, inner_rp)

    idx = torch.arange(T, device=mesh.device)
    G_00[idx, idx] = diag_00
    G_r[idx, idx, :] = sym_r
    G_rp[idx, idx, :] = sym_r
    G_rrp[idx, idx] = diag_rrp

    L = torch.zeros((mesh.n_rwg, mesh.n_rwg), dtype=torch.float64, device=mesh.device)
    for tm, vm, div_m, sc_m in mesh.sides_t:
        for tn, vn, div_n, sc_n in mesh.sides_t:
            g00 = G_00[tm][:, tn]
            gr = G_r[tm][:, tn, :]
            grp = G_rp[tm][:, tn, :]
            grrp = G_rrp[tm][:, tn]
            dot_int = (
                grrp
                - torch.einsum("ijd,jd->ij", gr, vn)
                - torch.einsum("id,ijd->ij", vm, grp)
                + (vm @ vn.T) * g00
            )
            L = L + (
                alpha * (sc_m[:, None] * sc_n[None, :]) * dot_int
                + (1.0 / alpha) * (div_m[:, None] * div_n[None, :]) * g00
            )
    return L


def assemble_mfie_k_same_body_torch(mesh: RWGMeshTorch, alpha: float) -> torch.Tensor:
    """Fast vectorized RWG MFIE K(alpha) matrix using torch.cross (zero 3-operand einsum)."""
    T = mesh.n_tri
    R_safe = torch.where(mesh.non_coplanar_q_t, mesh.R_t, torch.ones_like(mesh.R_t))
    psi = torch.where(
        mesh.non_coplanar_q_t,
        (1.0 + alpha * R_safe) * torch.exp(-alpha * R_safe) / (4.0 * math.pi * (R_safe**3)),
        torch.zeros_like(R_safe),
    )
    W_vec = ((mesh.wts_pair_t * psi)[:, :, None] * mesh.diff_t).reshape(T, 7, T, 7, 3)
    M0 = W_vec.sum(dim=(1, 3))  # (T, T, 3)
    Vec_sum_q = W_vec.sum(dim=1)  # (T, T, 7, 3)
    M_rp_cross = torch.linalg.cross(mesh.q_pts_t[None, :, :, :], Vec_sum_q, dim=-1).sum(dim=2)  # (T, T, 3)

    K = torch.zeros((mesh.n_rwg, mesh.n_rwg), dtype=torch.float64, device=mesh.device)
    for tm, vm, _, sc_m in mesh.sides_t:
        for tn, vn, _, sc_n in mesh.sides_t:
            m0 = M0[tm][:, tn, :]
            mrp = M_rp_cross[tm][:, tn, :]
            vn_cross_m0 = torch.linalg.cross(vn[None, :, :], m0, dim=-1)
            bracket = mrp - vn_cross_m0
            dv = vn[None, :, :] - vm[:, None, :]
            K = K + (sc_m[:, None] * sc_n[None, :]) * (dv * bracket).sum(dim=-1)
    return K


class CrossBodyWorkspaceTorch:
    """Precomputed cross-body pairwise quadrature tensors between disjoint rotor and stator meshes."""

    def __init__(self, rotor: RWGMeshTorch, stator: RWGMeshTorch):
        self.rotor = rotor
        self.stator = stator
        self.device = rotor.device
        pts1 = rotor.q_pts_t.reshape(-1, 3)
        wts1 = rotor.q_wts_t.reshape(-1)
        pts2 = stator.q_pts_t.reshape(-1, 3)
        wts2 = stator.q_wts_t.reshape(-1)

        self.diff_t = pts1[:, None, :] - pts2[None, :, :]
        self.R_t = torch.linalg.norm(self.diff_t, dim=2)
        self.w12_t = wts1[:, None] * wts2[None, :]

    def assemble_efie_cross(self, kappa: float) -> tuple[torch.Tensor, torch.Tensor]:
        T1, T2 = self.rotor.n_tri, self.stator.n_tri
        R = self.R_t
        G = torch.exp(-kappa * R) / (4.0 * math.pi * R)
        dG_dz1 = -G * (kappa + 1.0 / R) * (self.diff_t[:, :, 2] / R)

        W_G = (self.w12_t * G).reshape(T1, 7, T2, 7)
        W_dG = (self.w12_t * dG_dz1).reshape(T1, 7, T2, 7)

        outs: list[torch.Tensor] = []
        for W_mat in (W_G, W_dG):
            G_00 = W_mat.sum(dim=(1, 3))
            G_r = torch.einsum("tqu,tqd->tud", W_mat.sum(dim=3), self.rotor.q_pts_t)
            G_rp = torch.einsum("tuv,uvd->tud", W_mat.sum(dim=1), self.stator.q_pts_t)
            G_rrp = torch.zeros((T1, T2), dtype=torch.float64, device=self.device)
            for d_idx in range(3):
                right_v = torch.einsum("tquv,uv->tqu", W_mat, self.stator.q_pts_t[:, :, d_idx])
                G_rrp = G_rrp + torch.einsum("tq,tqu->tu", self.rotor.q_pts_t[:, :, d_idx], right_v)

            M_out = torch.zeros((self.rotor.n_rwg, self.stator.n_rwg), dtype=torch.float64, device=self.device)
            for tm, vm, div_m, sc_m in self.rotor.sides_t:
                for tn, vn, div_n, sc_n in self.stator.sides_t:
                    g00 = G_00[tm][:, tn]
                    gr = G_r[tm][:, tn, :]
                    grp = G_rp[tm][:, tn, :]
                    grrp = G_rrp[tm][:, tn]
                    dot_int = (
                        grrp
                        - torch.einsum("ijd,jd->ij", gr, vn)
                        - torch.einsum("id,ijd->ij", vm, grp)
                        + (vm @ vn.T) * g00
                    )
                    M_out = M_out + (
                        kappa * (sc_m[:, None] * sc_n[None, :]) * dot_int
                        + (1.0 / kappa) * (div_m[:, None] * div_n[None, :]) * g00
                    )
            outs.append(M_out)
        return outs[0], outs[1]

    def assemble_mfie_k_cross(self, kappa: float) -> tuple[torch.Tensor, torch.Tensor]:
        T1, T2 = self.rotor.n_tri, self.stator.n_tri
        R = self.R_t
        exp_k = torch.exp(-kappa * R) / (4.0 * math.pi)
        psi = (1.0 + kappa * R) * exp_k / (R**3)
        dpsi_dR_over_R = -(3.0 + 3.0 * kappa * R + (kappa * R) ** 2) * exp_k / (R**5)

        vec_K = ((self.w12_t * psi)[:, :, None] * self.diff_t).reshape(T1, 7, T2, 7, 3)
        ez = torch.tensor([0.0, 0.0, 1.0], dtype=torch.float64, device=self.device)
        dvec_raw = psi[:, :, None] * ez[None, None, :] + (
            (dpsi_dR_over_R * self.diff_t[:, :, 2])[:, :, None] * self.diff_t
        )
        vec_dK = (self.w12_t[:, :, None] * dvec_raw).reshape(T1, 7, T2, 7, 3)

        outs: list[torch.Tensor] = []
        for V_4d in (vec_K, vec_dK):
            M0 = V_4d.sum(dim=(1, 3))
            Vec_sum_q = V_4d.sum(dim=1)
            M_rp_cross = torch.linalg.cross(self.stator.q_pts_t[None, :, :, :], Vec_sum_q, dim=-1).sum(dim=2)
            K_out = torch.zeros((self.rotor.n_rwg, self.stator.n_rwg), dtype=torch.float64, device=self.device)
            for tm, vm, _, sc_m in self.rotor.sides_t:
                for tn, vn, _, sc_n in self.stator.sides_t:
                    m0 = M0[tm][:, tn, :]
                    mrp = M_rp_cross[tm][:, tn, :]
                    vn_cross_m0 = torch.linalg.cross(vn[None, :, :], m0, dim=-1)
                    bracket = mrp - vn_cross_m0
                    dv = vn[None, :, :] - vm[:, None, :]
                    K_out = K_out + (sc_m[:, None] * sc_n[None, :]) * (dv * bracket).sum(dim=-1)
            outs.append(K_out)
        return outs[0], outs[1]


def solve_rwg_casimir_fz_pn(
    rotor: RWGMeshTorch,
    stator: RWGMeshTorch,
    d_char_um: float,
    material: str = "PEC",
    n_xi: int = 16,
    symmetry_multiplier: float = SYMMETRY_MULTIPLIER,
    eps_override_fn: Callable[[float], float] | None = None,
    max_steps: int = 0,
) -> dict[str, Any]:
    """Evaluate exact 3D Maxwell RWG Casimir force F_z (pN) for PEC (EFIE) or Gold_Drude (PMCHWT)."""
    t0 = time.perf_counter()
    nodes, weights = np.polynomial.legendre.leggauss(int(n_xi))
    u = 0.5 * (nodes + 1.0)
    wu = 0.5 * weights
    k0 = 1.0 / float(d_char_um)
    kappas_all = k0 * u / (1.0 - u)
    wkappas_all = wu * k0 / ((1.0 - u) ** 2)

    n_eval = min(len(kappas_all), int(max_steps)) if max_steps > 0 else len(kappas_all)
    kappas = kappas_all[:n_eval]
    wkappas = wkappas_all[:n_eval]

    cross_ws = CrossBodyWorkspaceTorch(rotor, stator)
    is_pec = material.upper() == "PEC" and eps_override_fn is None
    eps_fn = eps_override_fn if eps_override_fn is not None else gold_drude_eps

    fz_meep_1sec = 0.0
    f_spectrum_pn_um: list[float] = []
    eye_1 = torch.eye(rotor.n_rwg if is_pec else 2 * rotor.n_rwg, dtype=torch.float64, device=rotor.device)

    for kap, wkap in zip(kappas, wkappas):
        kap_f = float(kap)
        if is_pec:
            M11 = assemble_efie_same_body_torch(rotor, kap_f)
            M22 = assemble_efie_same_body_torch(stator, kap_f)
            M12, dM12 = cross_ws.assemble_efie_cross(kap_f)
            M21, dM21 = M12.T, dM12.T
        else:
            eps_val = float(eps_fn(kap_f))
            kap_in = kap_f * math.sqrt(eps_val)
            z_in = 1.0 / math.sqrt(eps_val)

            def _pmchwt_self(m: RWGMeshTorch) -> torch.Tensor:
                L_out = assemble_efie_same_body_torch(m, kap_f)
                L_in = assemble_efie_same_body_torch(m, kap_in)
                K_out = assemble_mfie_k_same_body_torch(m, kap_f)
                K_in = assemble_mfie_k_same_body_torch(m, kap_in)
                A = L_out + z_in * L_in
                D = L_out + (1.0 / z_in) * L_in
                B = K_out + K_in
                return torch.cat([torch.cat([A, B], dim=1), torch.cat([-B, D], dim=1)], dim=0)

            M11 = _pmchwt_self(rotor)
            M22 = _pmchwt_self(stator)
            L12, dL12 = cross_ws.assemble_efie_cross(kap_f)
            K12, dK12 = cross_ws.assemble_mfie_k_cross(kap_f)
            M12 = torch.cat([torch.cat([L12, K12], dim=1), torch.cat([-K12, L12], dim=1)], dim=0)
            dM12 = torch.cat([torch.cat([dL12, dK12], dim=1), torch.cat([-dK12, dL12], dim=1)], dim=0)
            M21 = torch.cat([torch.cat([L12.T, K12.T], dim=1), torch.cat([-K12.T, L12.T], dim=1)], dim=0)
            dM21 = torch.cat([torch.cat([dL12.T, dK12.T], dim=1), torch.cat([-dK12.T, dL12.T], dim=1)], dim=0)

        n2 = M12.shape[1]
        X_both = torch.linalg.solve(M11, torch.cat([M12, dM12], dim=1))
        X, dX = X_both[:, :n2], X_both[:, n2:]

        n1 = M21.shape[1]
        Z_both = torch.linalg.solve(M22, torch.cat([M21, dM21], dim=1))
        Z, dZ = Z_both[:, :n1], Z_both[:, n1:]

        C = X @ Z
        dC = dX @ Z + X @ dZ
        tr_val = float(torch.trace(torch.linalg.solve(eye_1 - C, dC)).item())
        integrand_meep = tr_val / (2.0 * math.pi)
        fz_meep_1sec += float(wkap) * integrand_meep
        f_spectrum_pn_um.append(float(symmetry_multiplier * integrand_meep * MEEP_FORCE_TO_PN))

    fz_1sec_pn = float(fz_meep_1sec * MEEP_FORCE_TO_PN)
    fz_total_pn = float(symmetry_multiplier * fz_1sec_pn)
    return {
        "material": material,
        "formulation": "RWG_EFIE" if is_pec else "RWG_PMCHWT",
        "n_xi": int(n_xi),
        "evaluated_steps": int(n_eval),
        "n_rotor_tri": int(rotor.n_tri),
        "n_stator_tri": int(stator.n_tri),
        "n_rotor_rwg": int(rotor.n_rwg),
        "n_stator_rwg": int(stator.n_rwg),
        "n_total_dof": int((rotor.n_rwg + stator.n_rwg) * (1 if is_pec else 2)),
        "symmetry_multiplier": float(symmetry_multiplier),
        "F_z_sector_pN": fz_1sec_pn,
        "F_z_total_pN": fz_total_pn,
        "kappas_um_inv": [float(k) for k in kappas],
        "f_spectrum_pN_um": f_spectrum_pn_um,
        "elapsed_s": float(time.perf_counter() - t0),
    }


def evaluate_fast_vector_dyadic_on_boxes(
    rotor_boxes: Sequence[tuple[float, float, float, float, float, float]],
    stator_boxes: Sequence[tuple[float, float, float, float, float, float]],
    rotor_sub: tuple[int, int, int],
    stator_sub: tuple[int, int, int],
    material: str,
    d_char_um: float,
    n_xi: int = 16,
    device_str: str = "auto",
) -> dict[str, Any]:
    """Cross-calibrate fast approximate `vector_dyadic` panel BEM on the exact same 3D box geometry."""
    t0 = time.perf_counter()

    def _boxes_to_panels(
        boxes: Sequence[tuple[float, float, float, float, float, float]],
        sub: tuple[int, int, int],
        body: str,
    ) -> list[Any]:
        panels: list[Any] = []
        nx, ny, nz = sub
        kind = "rotor_bottom" if body == "rotor" else "stator_top"
        for x0, x1, y0, y1, z0, z1 in boxes:
            xs = np.linspace(x0, x1, nx + 1)
            ys = np.linspace(y0, y1, ny + 1)
            zs = np.linspace(z0, z1, nz + 1)
            for i in range(nx):
                for j in range(ny):
                    panels.append(
                        _panel(
                            [
                                np.array([xs[i], ys[j], z0]),
                                np.array([xs[i], ys[j + 1], z0]),
                                np.array([xs[i + 1], ys[j + 1], z0]),
                                np.array([xs[i + 1], ys[j], z0]),
                            ],
                            np.array([0.0, 0.0, -1.0]),
                            kind,  # type: ignore[arg-type]
                            body,  # type: ignore[arg-type]
                        )
                    )
                    panels.append(
                        _panel(
                            [
                                np.array([xs[i], ys[j], z1]),
                                np.array([xs[i + 1], ys[j], z1]),
                                np.array([xs[i + 1], ys[j + 1], z1]),
                                np.array([xs[i], ys[j + 1], z1]),
                            ],
                            np.array([0.0, 0.0, 1.0]),
                            kind,  # type: ignore[arg-type]
                            body,  # type: ignore[arg-type]
                        )
                    )
            for i in range(nx):
                for k in range(nz):
                    panels.append(
                        _panel(
                            [
                                np.array([xs[i], y0, zs[k]]),
                                np.array([xs[i + 1], y0, zs[k]]),
                                np.array([xs[i + 1], y0, zs[k + 1]]),
                                np.array([xs[i], y0, zs[k + 1]]),
                            ],
                            np.array([0.0, -1.0, 0.0]),
                            kind,  # type: ignore[arg-type]
                            body,  # type: ignore[arg-type]
                        )
                    )
                    panels.append(
                        _panel(
                            [
                                np.array([xs[i], y1, zs[k]]),
                                np.array([xs[i], y1, zs[k + 1]]),
                                np.array([xs[i + 1], y1, zs[k + 1]]),
                                np.array([xs[i + 1], y1, zs[k]]),
                            ],
                            np.array([0.0, 1.0, 0.0]),
                            kind,  # type: ignore[arg-type]
                            body,  # type: ignore[arg-type]
                        )
                    )
            for j in range(ny):
                for k in range(nz):
                    panels.append(
                        _panel(
                            [
                                np.array([x0, ys[j], zs[k]]),
                                np.array([x0, ys[j], zs[k + 1]]),
                                np.array([x0, ys[j + 1], zs[k + 1]]),
                                np.array([x0, ys[j + 1], zs[k]]),
                            ],
                            np.array([-1.0, 0.0, 0.0]),
                            kind,  # type: ignore[arg-type]
                            body,  # type: ignore[arg-type]
                        )
                    )
                    panels.append(
                        _panel(
                            [
                                np.array([x1, ys[j], zs[k]]),
                                np.array([x1, ys[j + 1], zs[k]]),
                                np.array([x1, ys[j + 1], zs[k + 1]]),
                                np.array([x1, ys[j], zs[k + 1]]),
                            ],
                            np.array([1.0, 0.0, 0.0]),
                            kind,  # type: ignore[arg-type]
                            body,  # type: ignore[arg-type]
                        )
                    )
        return panels

    r_panels = _boxes_to_panels(rotor_boxes, rotor_sub, "rotor")
    s_panels = _boxes_to_panels(stator_boxes, stator_sub, "stator")
    mat_param = "PEC" if material.upper() == "PEC" else "Gold_Drude"
    mesh = ClutchSurfaceMesh(
        rotor=tuple(r_panels),
        stator=tuple(s_panels),
        geometry=None,  # type: ignore[arg-type]
        parameters={"material": mat_param},
        config={"mode": "single_setup_box"},
        panel_resolution={"rotor_sub": rotor_sub, "stator_sub": stator_sub},
        symmetry_multiplier=1.0,
    )
    rot_arr = mesh.sector_arrays("rotor")
    sta_arr = mesh.sector_arrays("stator")
    mat_model = MaterialModel.from_parameters({"material": mat_param})
    backend = DenseBackend(device_str if device_str in ("auto", "cpu", "cuda") else "auto")

    nodes, weights = np.polynomial.legendre.leggauss(int(n_xi))
    u = 0.5 * (nodes + 1.0)
    wu = 0.5 * weights
    k0 = 1.0 / float(d_char_um)
    kappas = k0 * u / (1.0 - u)
    wkappas = wu * k0 / ((1.0 - u) ** 2)
    k_eff = 1.0 / max(float(d_char_um), 0.020)

    fz_meep_1sec = 0.0
    for kap, wkap in zip(kappas, wkappas):
        kap_f = float(kap)
        m_rr = _vector_dyadic_blocks(rot_arr, rot_arr, kap_f, True, mat_model, k_eff)
        m_ss = _vector_dyadic_blocks(sta_arr, sta_arr, kap_f, True, mat_model, k_eff)
        m_rs, dm_rs = _vector_dyadic_blocks(
            rot_arr, sta_arr, kap_f, False, mat_model, k_eff, derivative_target_z=True
        )
        m_sr = m_rs.T
        dm_sr = dm_rs.T
        _, tr_deriv = backend.logdet_and_trace(m_rr, m_ss, m_rs, m_sr, dm_rs, dm_sr)
        # E = (hbar*c / 2*pi) int dkappa logdet(I - C); F_z = -dE/dz = -(hbar*c / 2*pi) int dkappa d(logdet)/dz
        fz_meep_1sec += -float(wkap) * float(tr_deriv) / (2.0 * math.pi)

    fz_total_pn = float(SYMMETRY_MULTIPLIER * fz_meep_1sec * MEEP_FORCE_TO_PN)
    return {
        "material": material,
        "formulation": "fast_vector_dyadic_quad",
        "n_rotor_panels": len(r_panels),
        "n_stator_panels": len(s_panels),
        "F_z_total_pN": fz_total_pn,
        "elapsed_s": float(time.perf_counter() - t0),
    }


def richardson_extrapolate_2pt(f1: float, f2: float, h1: float, h2: float, order_p: float = 1.0) -> float:
    """Two-point Richardson continuum extrapolation f(h) = f_inf + c * h^p."""
    r_p = (h1 / h2) ** order_p
    return float((r_p * f2 - f1) / (r_p - 1.0))


def richardson_fit_continuum(hs: Sequence[float], fs: Sequence[float], order_p: float = 1.0) -> dict[str, float]:
    """Weighted least-squares continuum fit f(h) = f_inf + c * h^p + 2-point finest check."""
    h_arr = np.asarray(hs, dtype=np.float64)
    f_arr = np.asarray(fs, dtype=np.float64)
    order = np.argsort(h_arr)[::-1]  # coarse -> fine
    h_arr = h_arr[order]
    f_arr = f_arr[order]
    if len(f_arr) < 2:
        return {"f_inf": float(f_arr[-1]), "se_fit": 0.0, "f_2pt_finest": float(f_arr[-1])}
    f_2pt = richardson_extrapolate_2pt(float(f_arr[-2]), float(f_arr[-1]), float(h_arr[-2]), float(h_arr[-1]), order_p)
    if len(f_arr) == 2:
        return {"f_inf": f_2pt, "se_fit": abs(f_2pt - float(f_arr[-1])), "f_2pt_finest": f_2pt}

    # Weight finer grids inversely with h^2
    w = 1.0 / np.maximum(h_arr, 1e-12)
    X = np.column_stack([np.ones_like(h_arr), h_arr**order_p])
    Xw = X * w[:, None]
    yw = f_arr * w
    beta, _, _, _ = np.linalg.lstsq(Xw, yw, rcond=None)
    resid = f_arr - (X @ beta)
    dof = max(len(f_arr) - 2, 1)
    cov = np.linalg.pinv(Xw.T @ Xw) * float(np.sum((w * resid) ** 2) / dof)
    se_inf = float(math.sqrt(max(float(cov[0, 0]), 0.0)))
    return {
        "f_inf": float(beta[0]),
        "slope": float(beta[1]),
        "se_fit": max(se_inf, 0.5 * abs(float(beta[0]) - f_2pt)),
        "f_2pt_finest": f_2pt,
    }


# =============================================================================
# 1. Generate 17 Yee-Aligned 3D Meep FDTD Configs
# =============================================================================
def generate_fdtd_configs(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest_rows: list[dict[str, Any]] = []

    for spec in FDTD_SWEEP_SPECS:
        stator_boxes = (
            OPEN_STATOR_COLLAR_BOXES_UM if spec.state == "open_repulsive" else ENGAGED_STATOR_PAD_BOXES_UM
        )
        theta_deg = 3.0 if spec.state == "open_repulsive" else 48.0
        payload = {
            "task_id": spec.task_id,
            "control_label": spec.label,
            "design_name": "H3_Cantor_SingleSetup_20nmLattice",
            "kinematic_state": spec.state,
            "geometry_mode": "explicit_boxes_3d",
            "explicit_rotor_boxes": [list(ROTOR_LOBE_BOX_UM)],
            "explicit_stator_boxes": [list(b) for b in stator_boxes],
            "explicit_stress_boxes": [list(STRESS_BOX_UM)],
            "explicit_cell_center": list(EXPLICIT_CELL_CENTER_UM),
            "explicit_phys_bounds": [list(ax) for ax in EXPLICIT_PHYS_BOUNDS_UM],
            "d_eff_um": D_EFF_SINGLE_SETUP_UM,
            "cell_buffer_um": CELL_BUFFER_SINGLE_SETUP_UM,
            "pml_thickness_um": PML_THICKNESS_SINGLE_SETUP_UM,
            "T_run": T_RUN_SINGLE_SETUP,
            "courant": 0.5,
            "resolution": spec.resolution,
            "nmax": spec.nmax,
            "material": spec.material,
            "eps_averaging": False,
            "force_complex_fields": True,
            "sector0_crop": False,
            "num_sectors": 4,
            "N_fractal": 3,
            "theta_deg": theta_deg,
            "aperture_arc_deg": 36.0,
            "bridge_arc_deg": 54.0,
            "tooth_arc_deg": 12.0,
            "tooth_center_offset_deg": 15.0,
            "H_teeth_um": 0.040,
            "z_tip_um": -0.080,
            "z_pad_top_um": -0.120,
            "t_membrane_um": 0.040,
            "t_landing_pad_um": 0.040,
            "L_domain_um": 0.640,
            "stress_box_mode": "per_tooth_rotor_frame",
            "fixed_stress_box_margin_um": 0.020,
            "geometry": {
                "elements": [
                    {
                        "track_index": 0,
                        "level": 3,
                        "r_inner": 3.50,
                        "r_outer": 3.60,
                        "r_center": 3.55,
                        "W_slot": 0.100,
                        "w_tooth": 0.040,
                        "r_tooth_in": 3.53,
                        "r_tooth_out": 3.57,
                        "h_teeth": 0.040,
                        "z_tip": -0.080,
                    }
                ]
            },
        }
        cfg_path = out_dir / f"config_{spec.task_id:03d}.json"
        _atomic_write_json(cfg_path, payload)
        written.append(cfg_path)
        manifest_rows.append(
            {
                "task_id": spec.task_id,
                "config_file": str(cfg_path.relative_to(ROOT)).replace("\\", "/"),
                "label": spec.label,
                "state": spec.state,
                "material": spec.material,
                "resolution": spec.resolution,
                "dx_nm": round(1000.0 / spec.resolution, 4),
                "nmax": spec.nmax,
            }
        )

    _atomic_write_json(
        out_dir / "manifest.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "num_tasks": len(manifest_rows),
            "tasks": manifest_rows,
        },
    )
    return written


# =============================================================================
# 2. Run Exact First-Principles 3D Maxwell RWG BEM Convergence Suite
# =============================================================================
def run_bem_convergence_suite(
    device_arg: str = "auto",
    n_xi_default: int = 16,
    checkpoint_dir: Path | None = None,
    output_path: Path | None = None,
    max_steps: int = 0,
) -> dict[str, Any]:
    t_suite = time.perf_counter()
    dev = resolve_torch_device(device_arg)
    ckpt_dir = checkpoint_dir or (ROOT / ".tmp" / "h3_single_setup_bem_ckpt")
    out_file = output_path or (ROOT / "results" / "h3_single_setup_bem_convergence.json")

    if max_steps > 0:
        # Empirical micro-probe for hpc_gate.py: run `max_steps` frequency evaluations on Tier 2 PMCHWT
        tier2 = BEM_MESH_TIERS[1]
        rot_m = make_closed_box_rwg_mesh(ROTOR_LOBE_BOX_UM, tier2["rotor_sub"], device=dev)
        sta_m = make_multi_box_rwg_mesh(OPEN_STATOR_COLLAR_BOXES_UM, tier2["collar_sub"], device=dev)
        probe_res = solve_rwg_casimir_fz_pn(
            rot_m,
            sta_m,
            d_char_um=D_EFF_SINGLE_SETUP_UM,
            material="Gold_Drude",
            n_xi=max(16, int(max_steps)),
            max_steps=int(max_steps),
        )
        print(
            f"[BEM Micro-Probe] device={dev} steps={max_steps} "
            f"RWG={rot_m.n_rwg}+{sta_m.n_rwg} F_z_partial={probe_res['F_z_total_pN']:+.5f} pN "
            f"elapsed={probe_res['elapsed_s']:.3f}s",
            flush=True,
        )
        return {"status": "micro_probe_complete", "device": str(dev), "probe": probe_res}

    ckpt_dir.mkdir(parents=True, exist_ok=True)
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]

    def _run_cached(key: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        cp = ckpt_dir / f"{key}.json"
        if cp.exists():
            try:
                cached = json.loads(cp.read_text(encoding="utf-8"))
                if cached.get("code_hash") == code_hash:
                    print(f"  [ckpt hit] {key}: F_z = {cached['result'].get('F_z_total_pN', 0.0):+.5f} pN", flush=True)
                    return cached["result"]
            except Exception:
                pass
        res = fn()
        _atomic_write_json(cp, {"code_hash": code_hash, "saved_at": datetime.now(timezone.utc).isoformat(), "result": res})
        return res

    print(f"=== Running Exact 3D Maxwell RWG BEM Convergence Suite on device={dev} ===", flush=True)

    # A. Canonical parallel-slab consistency check: PMCHWT(eps -> inf) == EFIE(PEC) & Gold_Drude Lifshitz
    print("--- [A] Canonical Parallel-Slab Consistency (d = 50 nm) ---", flush=True)
    slab_rot = make_closed_box_rwg_mesh((-0.15, 0.15, -0.15, 0.15, 0.050, 0.150), (4, 4, 1), device=dev)
    slab_sta = make_closed_box_rwg_mesh((-0.15, 0.15, -0.15, 0.15, -0.100, 0.000), (4, 4, 1), device=dev)
    slab_pec = _run_cached(
        "canonical_slab_pec_efie",
        lambda: solve_rwg_casimir_fz_pn(slab_rot, slab_sta, 0.050, "PEC", n_xi=16, symmetry_multiplier=1.0),
    )
    slab_high_eps = _run_cached(
        "canonical_slab_pmchwt_eps1e8",
        lambda: solve_rwg_casimir_fz_pn(
            slab_rot,
            slab_sta,
            0.050,
            "Gold_Drude",
            n_xi=16,
            symmetry_multiplier=1.0,
            eps_override_fn=lambda _k: 1.0e8,
        ),
    )
    slab_gold = _run_cached(
        "canonical_slab_pmchwt_gold",
        lambda: solve_rwg_casimir_fz_pn(slab_rot, slab_sta, 0.050, "Gold_Drude", n_xi=16, symmetry_multiplier=1.0),
    )
    eta_lif_50nm = lifshitz_infinite_plate_ratio_gold_over_pec(0.050)
    pmchwt_pec_rel_diff_pct = (
        abs(slab_high_eps["F_z_total_pN"] - slab_pec["F_z_total_pN"])
        / max(abs(slab_pec["F_z_total_pN"]), 1e-15)
        * 100.0
    )
    print(
        f"  Slab d=50nm: EFIE PEC={slab_pec['F_z_total_pN']:+.5f} pN | "
        f"PMCHWT(eps=1e8)={slab_high_eps['F_z_total_pN']:+.5f} pN (diff={pmchwt_pec_rel_diff_pct:.3f}%) | "
        f"PMCHWT Gold={slab_gold['F_z_total_pN']:+.5f} pN (Lifshitz inf-plate eta={eta_lif_50nm:.4f})",
        flush=True,
    )

    # B. 4-Tier RWG Mesh Refinement Ladder across all 4 (State x Material) channels
    print("--- [B] 4-Tier RWG Mesh Convergence Ladder on H3-Cantor Single Setup ---", flush=True)
    mesh_ladder: dict[str, list[dict[str, Any]]] = {
        "open_pec": [],
        "engaged_pec": [],
        "open_gold": [],
        "engaged_gold": [],
    }
    for t_cfg in BEM_MESH_TIERS:
        t_num = int(t_cfg["tier"])
        rot_mesh = make_closed_box_rwg_mesh(ROTOR_LOBE_BOX_UM, t_cfg["rotor_sub"], device=dev)
        open_sta_mesh = make_multi_box_rwg_mesh(OPEN_STATOR_COLLAR_BOXES_UM, t_cfg["collar_sub"], device=dev)
        eng_sta_mesh = make_multi_box_rwg_mesh(ENGAGED_STATOR_PAD_BOXES_UM, t_cfg["pad_sub"], device=dev)

        # Effective surface element size h_eff_nm = 1000 * sqrt(total_area / total_tri)
        h_open_nm = 1000.0 * math.sqrt(
            float(np.sum(rot_mesh.areas) + np.sum(open_sta_mesh.areas)) / (rot_mesh.n_tri + open_sta_mesh.n_tri)
        )
        h_eng_nm = 1000.0 * math.sqrt(
            float(np.sum(rot_mesh.areas) + np.sum(eng_sta_mesh.areas)) / (rot_mesh.n_tri + eng_sta_mesh.n_tri)
        )

        for chan_key, state_name, mat_name, sta_m, h_nm in (
            ("open_pec", "open_repulsive", "PEC", open_sta_mesh, h_open_nm),
            ("engaged_pec", "engaged_attractive", "PEC", eng_sta_mesh, h_eng_nm),
            ("open_gold", "open_repulsive", "Gold_Drude", open_sta_mesh, h_open_nm),
            ("engaged_gold", "engaged_attractive", "Gold_Drude", eng_sta_mesh, h_eng_nm),
        ):
            res = _run_cached(
                f"tier{t_num}_{chan_key}_nxi{n_xi_default}",
                lambda sta_m=sta_m, mat_name=mat_name: solve_rwg_casimir_fz_pn(
                    rot_mesh, sta_m, D_EFF_SINGLE_SETUP_UM, mat_name, n_xi=n_xi_default
                ),
            )
            entry = {
                "tier": t_num,
                "label": t_cfg["label"],
                "state": state_name,
                "material": mat_name,
                "h_eff_nm": round(h_nm, 4),
                **res,
            }
            mesh_ladder[chan_key].append(entry)
            print(
                f"  Tier {t_num} | {chan_key:12s} | RWG={res['n_rotor_rwg']:3d}+{res['n_stator_rwg']:4d} "
                f"(h={h_nm:5.2f} nm) | F_z = {res['F_z_total_pN']:+.5f} pN ({res['elapsed_s']:.2f}s)",
                flush=True,
            )

    bem_extrapolations: dict[str, dict[str, float]] = {}
    for chan_key, entries in mesh_ladder.items():
        hs = [float(e["h_eff_nm"]) for e in entries]
        fs = [float(e["F_z_total_pN"]) for e in entries]
        bem_extrapolations[chan_key] = richardson_fit_continuum(hs, fs, order_p=1.0)
        print(
            f"  [BEM Continuum] {chan_key:12s}: F_inf = {bem_extrapolations[chan_key]['f_inf']:+.5f} "
            f"+/- {bem_extrapolations[chan_key]['se_fit']:.5f} pN "
            f"(Tier 4 = {fs[-1]:+.5f} pN)",
            flush=True,
        )

    # C. Imaginary-frequency quadrature ladder on Tier 2 (n_xi = 8, 12, 16, 24, 32)
    print("--- [C] Imaginary-Frequency Gauss-Legendre Quadrature Ladder (Tier 2) ---", flush=True)
    t2 = BEM_MESH_TIERS[1]
    rot_t2 = make_closed_box_rwg_mesh(ROTOR_LOBE_BOX_UM, t2["rotor_sub"], device=dev)
    open_t2 = make_multi_box_rwg_mesh(OPEN_STATOR_COLLAR_BOXES_UM, t2["collar_sub"], device=dev)
    eng_t2 = make_multi_box_rwg_mesh(ENGAGED_STATOR_PAD_BOXES_UM, t2["pad_sub"], device=dev)
    quadrature_ladder: list[dict[str, Any]] = []
    for n_xi_val in (8, 12, 16, 24, 32):
        r_op_pec = _run_cached(
            f"quad_t2_open_pec_nxi{n_xi_val}",
            lambda n_xi_val=n_xi_val: solve_rwg_casimir_fz_pn(rot_t2, open_t2, D_EFF_SINGLE_SETUP_UM, "PEC", n_xi=n_xi_val),
        )
        r_op_au = _run_cached(
            f"quad_t2_open_gold_nxi{n_xi_val}",
            lambda n_xi_val=n_xi_val: solve_rwg_casimir_fz_pn(
                rot_t2, open_t2, D_EFF_SINGLE_SETUP_UM, "Gold_Drude", n_xi=n_xi_val
            ),
        )
        r_en_au = _run_cached(
            f"quad_t2_eng_gold_nxi{n_xi_val}",
            lambda n_xi_val=n_xi_val: solve_rwg_casimir_fz_pn(
                rot_t2, eng_t2, D_EFF_SINGLE_SETUP_UM, "Gold_Drude", n_xi=n_xi_val
            ),
        )
        quadrature_ladder.append(
            {
                "n_xi": n_xi_val,
                "open_pec_pN": r_op_pec["F_z_total_pN"],
                "open_gold_pN": r_op_au["F_z_total_pN"],
                "engaged_gold_pN": r_en_au["F_z_total_pN"],
            }
        )

    # D. Cross-calibration against fast `vector_dyadic` BEM used in parametric 17-design sweep
    print("--- [D] Cross-Calibration: Exact RWG BEM vs Fast Tangential Vector-Dyadic BEM ---", flush=True)
    t3 = BEM_MESH_TIERS[2]
    vd_open_pec = evaluate_fast_vector_dyadic_on_boxes(
        [ROTOR_LOBE_BOX_UM], OPEN_STATOR_COLLAR_BOXES_UM, t3["rotor_sub"], t3["collar_sub"], "PEC", D_EFF_SINGLE_SETUP_UM
    )
    vd_eng_pec = evaluate_fast_vector_dyadic_on_boxes(
        [ROTOR_LOBE_BOX_UM], ENGAGED_STATOR_PAD_BOXES_UM, t3["rotor_sub"], t3["pad_sub"], "PEC", D_EFF_SINGLE_SETUP_UM
    )
    vd_open_gold = evaluate_fast_vector_dyadic_on_boxes(
        [ROTOR_LOBE_BOX_UM],
        OPEN_STATOR_COLLAR_BOXES_UM,
        t3["rotor_sub"],
        t3["collar_sub"],
        "Gold_Drude",
        D_EFF_SINGLE_SETUP_UM,
    )
    vd_eng_gold = evaluate_fast_vector_dyadic_on_boxes(
        [ROTOR_LOBE_BOX_UM],
        ENGAGED_STATOR_PAD_BOXES_UM,
        t3["rotor_sub"],
        t3["pad_sub"],
        "Gold_Drude",
        D_EFF_SINGLE_SETUP_UM,
    )
    cross_calibration = {
        "open_pec": {
            "exact_rwg_tier3_pN": mesh_ladder["open_pec"][2]["F_z_total_pN"],
            "fast_vector_dyadic_pN": vd_open_pec["F_z_total_pN"],
            "transfer_factor_exact_over_fast": mesh_ladder["open_pec"][2]["F_z_total_pN"] / vd_open_pec["F_z_total_pN"],
        },
        "engaged_pec": {
            "exact_rwg_tier3_pN": mesh_ladder["engaged_pec"][2]["F_z_total_pN"],
            "fast_vector_dyadic_pN": vd_eng_pec["F_z_total_pN"],
            "transfer_factor_exact_over_fast": mesh_ladder["engaged_pec"][2]["F_z_total_pN"] / vd_eng_pec["F_z_total_pN"],
        },
        "open_gold": {
            "exact_rwg_tier3_pN": mesh_ladder["open_gold"][2]["F_z_total_pN"],
            "fast_vector_dyadic_pN": vd_open_gold["F_z_total_pN"],
            "transfer_factor_exact_over_fast": mesh_ladder["open_gold"][2]["F_z_total_pN"] / vd_open_gold["F_z_total_pN"],
        },
        "engaged_gold": {
            "exact_rwg_tier3_pN": mesh_ladder["engaged_gold"][2]["F_z_total_pN"],
            "fast_vector_dyadic_pN": vd_eng_gold["F_z_total_pN"],
            "transfer_factor_exact_over_fast": mesh_ladder["engaged_gold"][2]["F_z_total_pN"] / vd_eng_gold["F_z_total_pN"],
        },
    }

    payload = {
        "status": "complete",
        "model": "Maxwell_RWG_BEM_EFIE_PMCHWT",
        "dataset": "H3_Cantor_SingleSetup_20nmLattice",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "code_hash": code_hash,
        "device": str(dev),
        "geometry_um": {
            "rotor_lobe_box": list(ROTOR_LOBE_BOX_UM),
            "stress_box": list(STRESS_BOX_UM),
            "open_stator_collar_boxes": [list(b) for b in OPEN_STATOR_COLLAR_BOXES_UM],
            "engaged_stator_pad_boxes": [list(b) for b in ENGAGED_STATOR_PAD_BOXES_UM],
            "symmetry_multiplier": SYMMETRY_MULTIPLIER,
            "d_eff_um": D_EFF_SINGLE_SETUP_UM,
        },
        "canonical_parallel_slab": {
            "d_gap_um": 0.050,
            "slab_width_um": 0.300,
            "slab_thickness_um": 0.100,
            "efie_pec_pN": slab_pec["F_z_total_pN"],
            "pmchwt_eps1e8_pN": slab_high_eps["F_z_total_pN"],
            "pmchwt_vs_efie_rel_diff_pct": pmchwt_pec_rel_diff_pct,
            "pmchwt_gold_drude_pN": slab_gold["F_z_total_pN"],
            "finite_slab_gold_over_pec": slab_gold["F_z_total_pN"] / slab_pec["F_z_total_pN"],
            "lifshitz_infinite_plate_gold_over_pec": eta_lif_50nm,
        },
        "mesh_ladder": mesh_ladder,
        "continuum_extrapolation": bem_extrapolations,
        "quadrature_ladder_tier2": quadrature_ladder,
        "cross_calibration_vector_dyadic": cross_calibration,
        "elapsed_s": float(time.perf_counter() - t_suite),
    }
    _atomic_write_json(out_file, payload)
    print(f"Saved BEM convergence results -> {out_file} ({payload['elapsed_s']:.2f}s)", flush=True)
    return payload


# =============================================================================
# 3. Aggregate BEM + FDTD Convergence, Render Figure, Export Provenance Macros
# =============================================================================
def aggregate_convergence_results(
    bem_json_path: Path | None = None,
    fdtd_dirs: Sequence[Path] | None = None,
    summary_out_path: Path | None = None,
) -> dict[str, Any]:
    bem_path = bem_json_path or (ROOT / "results" / "h3_single_setup_bem_convergence.json")
    if not bem_path.exists():
        raise FileNotFoundError(f"BEM convergence JSON not found at {bem_path}; run --run-bem first.")
    bem_data = json.loads(bem_path.read_text(encoding="utf-8"))

    search_dirs = list(
        fdtd_dirs
        or (
            ROOT / "results_h3_single_setup_fdtd",
            ROOT / "results" / "h3_single_setup_fdtd",
        )
    )

    fdtd_tasks: dict[int, dict[str, Any]] = {}
    fdtd_sources: list[str] = []
    for spec in FDTD_SWEEP_SPECS:
        for d in search_dirs:
            cand = d / f"task_{spec.task_id}_meep.json"
            if cand.exists():
                raw = json.loads(cand.read_text(encoding="utf-8"))
                if raw.get("status") == "complete" and raw.get("f_net_pN") is not None:
                    fdtd_tasks[spec.task_id] = {
                        "task_id": spec.task_id,
                        "label": spec.label,
                        "state": spec.state,
                        "material": spec.material,
                        "resolution": spec.resolution,
                        "dx_nm": round(1000.0 / spec.resolution, 4),
                        "nmax": spec.nmax,
                        "f_net_pN": float(raw["f_net_pN"]),
                        "f_2pass_pN": float(raw["F_2pass"] * MEEP_FORCE_TO_PN),
                        "f_stator_only_pN": float(raw["F_stator_only"] * MEEP_FORCE_TO_PN),
                        "f_rotor_self_pN": float(raw["F_rotor"] * MEEP_FORCE_TO_PN),
                        "f_vac_pN": float(raw["F_vac"] * MEEP_FORCE_TO_PN),
                        "elapsed_s": float(raw.get("elapsed_seconds", 0.0)),
                        "source_file": str(cand.relative_to(ROOT)).replace("\\", "/"),
                    }
                    fdtd_sources.append(str(cand.relative_to(ROOT)).replace("\\", "/"))
                    break

    channel_specs = {
        "open_pec": ("open_repulsive", "PEC", [1, 2, 3, 4]),
        "engaged_pec": ("engaged_attractive", "PEC", [8, 9, 10, 11]),
        "open_gold": ("open_repulsive", "Gold_Drude", [12, 13, 14]),
        "engaged_gold": ("engaged_attractive", "Gold_Drude", [15, 16, 17]),
    }

    fdtd_ladders: dict[str, list[dict[str, Any]]] = {}
    fdtd_extrapolations: dict[str, dict[str, Any]] = {}
    comparison: dict[str, dict[str, Any]] = {}

    for chan_key, (_, _, tids) in channel_specs.items():
        pts = [fdtd_tasks[t] for t in tids if t in fdtd_tasks]
        pts.sort(key=lambda x: int(x["resolution"]))
        fdtd_ladders[chan_key] = pts
        bem_inf = float(bem_data["continuum_extrapolation"][chan_key]["f_inf"])
        bem_se = float(bem_data["continuum_extrapolation"][chan_key]["se_fit"])
        bem_t4 = float(bem_data["mesh_ladder"][chan_key][-1]["F_z_total_pN"])
        if len(pts) >= 2:
            # Yee FDTD without subpixel smoothing converges linearly O(dx^1)
            fit = richardson_fit_continuum(
                [float(p["dx_nm"]) for p in pts],
                [float(p["f_net_pN"]) for p in pts],
                order_p=1.0,
            )
            fdtd_extrapolations[chan_key] = fit
            fdtd_inf = float(fit["f_inf"])
            rel_diff_pct = abs(fdtd_inf - bem_inf) / max(abs(bem_inf), 1e-12) * 100.0
            finest_fdtd = float(pts[-1]["f_net_pN"])
            finest_rel_diff_pct = abs(finest_fdtd - bem_t4) / max(abs(bem_t4), 1e-12) * 100.0
            comparison[chan_key] = {
                "status": "complete",
                "bem_finest_pN": bem_t4,
                "bem_continuum_pN": bem_inf,
                "bem_continuum_se_pN": bem_se,
                "fdtd_finest_R": int(pts[-1]["resolution"]),
                "fdtd_finest_pN": finest_fdtd,
                "fdtd_continuum_pN": fdtd_inf,
                "fdtd_continuum_se_pN": float(fit["se_fit"]),
                "continuum_rel_diff_pct": rel_diff_pct,
                "finest_grid_rel_diff_pct": finest_rel_diff_pct,
            }
        else:
            comparison[chan_key] = {
                "status": "pending_fdtd",
                "bem_finest_pN": bem_t4,
                "bem_continuum_pN": bem_inf,
                "bem_continuum_se_pN": bem_se,
            }

    # Source-order nmax = 1, 2, 3 diagnostics
    nmax_diagnostics = {
        f"R{spec.resolution}_nmax{spec.nmax}": fdtd_tasks[spec.task_id]["f_net_pN"]
        for spec in FDTD_SWEEP_SPECS
        if spec.task_id in (2, 5, 6, 3, 7) and spec.task_id in fdtd_tasks
    }

    summary_payload = {
        "status": "complete" if len(fdtd_tasks) == len(FDTD_SWEEP_SPECS) else "partial",
        "model": "Consolidated_BEM_FDTD_SingleSetup_Convergence",
        "dataset": "H3_Cantor_SingleSetup_20nmLattice",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "completed_fdtd_tasks": len(fdtd_tasks),
        "expected_fdtd_tasks": len(FDTD_SWEEP_SPECS),
        "bem_source": str(bem_path.relative_to(ROOT)).replace("\\", "/"),
        "fdtd_sources": fdtd_sources,
        "bem_summary": {
            "canonical_parallel_slab": bem_data["canonical_parallel_slab"],
            "mesh_ladder": bem_data["mesh_ladder"],
            "continuum_extrapolation": bem_data["continuum_extrapolation"],
            "quadrature_ladder_tier2": bem_data["quadrature_ladder_tier2"],
            "cross_calibration_vector_dyadic": bem_data["cross_calibration_vector_dyadic"],
        },
        "fdtd_ladders": fdtd_ladders,
        "fdtd_continuum_extrapolation": fdtd_extrapolations,
        "nmax_source_convergence": nmax_diagnostics,
        "solver_agreement": comparison,
    }

    out_summary = summary_out_path or (ROOT / "results" / "h3_single_setup_convergence_summary.json")
    _atomic_write_json(out_summary, summary_payload)

    # Log provenance metrics & export LaTeX macros + table + figure
    _log_convergence_provenance_and_table(summary_payload, out_summary)
    _render_convergence_figure(summary_payload, bem_data, out_summary)
    print(
        f"Aggregated single-setup convergence ({len(fdtd_tasks)}/{len(FDTD_SWEEP_SPECS)} FDTD tasks) -> {out_summary}",
        flush=True,
    )
    return summary_payload


def _fmt_signed(val: float, decimals: int = 3) -> str:
    return f"{val:+.{decimals}f}"


def _log_convergence_provenance_and_table(summary: dict[str, Any], summary_path: Path) -> None:
    src = str(summary_path.relative_to(ROOT)).replace("\\", "/")
    solver_params = {
        "bem_formulation": "Maxwell_RWG_EFIE_PMCHWT",
        "fdtd_formulation": "Meep_3D_4Pass_ExplicitBoxes_20nmLattice",
        "completed_fdtd_tasks": summary["completed_fdtd_tasks"],
        "expected_fdtd_tasks": summary["expected_fdtd_tasks"],
    }
    set_solver_provenance("Maxwell_RWG_BEM_and_Meep_3D_FDTD", solver_params)
    step_id = "h3_single_setup_convergence_ver10"
    log_step(
        step_id,
        {
            "summary_json": src,
            "status": summary["status"],
            "completed_fdtd_tasks": summary["completed_fdtd_tasks"],
        },
        solver_name="Maxwell_RWG_BEM_and_Meep_3D_FDTD",
        solver_parameters=solver_params,
    )

    kv_pairs: list[tuple[str, Any]] = []
    bem_slab = summary["bem_summary"]["canonical_parallel_slab"]
    kv_pairs.append(("conv_slab_pec_pn", _fmt_signed(float(bem_slab["efie_pec_pN"]), 3)))
    kv_pairs.append(("conv_slab_pmchwt_inf_pn", _fmt_signed(float(bem_slab["pmchwt_eps1e8_pN"]), 3)))
    kv_pairs.append(("conv_slab_pmchwt_diff_pct", f"{float(bem_slab['pmchwt_vs_efie_rel_diff_pct']):.2f}"))
    kv_pairs.append(("conv_slab_gold_pn", _fmt_signed(float(bem_slab["pmchwt_gold_drude_pN"]), 3)))

    chan_macro_prefix = {
        "open_pec": "conv_open_pec",
        "engaged_pec": "conv_eng_pec",
        "open_gold": "conv_open_gold",
        "engaged_gold": "conv_eng_gold",
    }

    for chan_key, prefix in chan_macro_prefix.items():
        ladder = summary["bem_summary"]["mesh_ladder"][chan_key]
        for entry in ladder:
            t_idx = int(entry["tier"])
            kv_pairs.append((f"{prefix}_bem_t{t_idx}_pn", _fmt_signed(float(entry["F_z_total_pN"]), 3)))
            kv_pairs.append((f"{prefix}_bem_t{t_idx}_dof", str(int(entry["n_total_dof"]))))
        comp = summary["solver_agreement"][chan_key]
        kv_pairs.append((f"{prefix}_bem_inf_pn", _fmt_signed(float(comp["bem_continuum_pN"]), 3)))
        kv_pairs.append((f"{prefix}_bem_se_pn", f"{float(comp['bem_continuum_se_pN']):.3f}"))

        xcal = summary["bem_summary"]["cross_calibration_vector_dyadic"][chan_key]
        kv_pairs.append((f"{prefix}_fast_vd_pn", _fmt_signed(float(xcal["fast_vector_dyadic_pN"]), 3)))
        kv_pairs.append((f"{prefix}_transfer_ratio", f"{float(xcal['transfer_factor_exact_over_fast']):.2f}"))

        fdtd_pts = {int(p["resolution"]): p for p in summary["fdtd_ladders"].get(chan_key, [])}
        for res_val in (100, 150, 200, 250):
            if res_val in fdtd_pts:
                p = fdtd_pts[res_val]
                kv_pairs.append((f"{prefix}_fdtd_r{res_val}_pn", _fmt_signed(float(p["f_net_pN"]), 3)))
                kv_pairs.append((f"{prefix}_fdtd_r{res_val}_stator_pn", _fmt_signed(float(p["f_stator_only_pN"]), 4)))
                kv_pairs.append((f"{prefix}_fdtd_r{res_val}_self_pn", _fmt_signed(float(p["f_rotor_self_pN"]), 4)))

        if comp.get("status") == "complete":
            kv_pairs.append((f"{prefix}_fdtd_inf_pn", _fmt_signed(float(comp["fdtd_continuum_pN"]), 3)))
            kv_pairs.append((f"{prefix}_fdtd_se_pn", f"{float(comp['fdtd_continuum_se_pN']):.3f}"))
            kv_pairs.append((f"{prefix}_rel_diff_pct", f"{float(comp['continuum_rel_diff_pct']):.1f}"))
            kv_pairs.append((f"{prefix}_finest_diff_pct", f"{float(comp['finest_grid_rel_diff_pct']):.1f}"))

    nmax_map = summary.get("nmax_source_convergence", {})
    if "R150_nmax1" in nmax_map and "R150_nmax2" in nmax_map and "R150_nmax3" in nmax_map:
        f_n1 = float(nmax_map["R150_nmax1"])
        f_n2 = float(nmax_map["R150_nmax2"])
        f_n3 = float(nmax_map["R150_nmax3"])
        drift_23_pct = abs(f_n3 - f_n2) / max(abs(f_n3), 1e-12) * 100.0
        kv_pairs.append(("conv_nmax_r150_n1_pn", _fmt_signed(f_n1, 3)))
        kv_pairs.append(("conv_nmax_r150_n2_pn", _fmt_signed(f_n2, 3)))
        kv_pairs.append(("conv_nmax_r150_n3_pn", _fmt_signed(f_n3, 3)))
        kv_pairs.append(("conv_nmax_r150_drift23_pct", f"{drift_23_pct:.2f}"))
    if "R200_nmax3" in nmax_map:
        kv_pairs.append(("conv_nmax_r200_n3_pn", _fmt_signed(float(nmax_map["R200_nmax3"]), 3)))

    q_rows = {int(r["n_xi"]): r for r in summary["bem_summary"]["quadrature_ladder_tier2"]}
    if 16 in q_rows and 32 in q_rows:
        q_drift_pct = (
            abs(float(q_rows[32]["open_gold_pN"]) - float(q_rows[16]["open_gold_pN"]))
            / max(abs(float(q_rows[32]["open_gold_pN"])), 1e-12)
            * 100.0
        )
        kv_pairs.append(("conv_bem_quad_drift16_32_pct", f"{q_drift_pct:.3f}"))

    for idx_kv, (k_name, k_val) in enumerate(kv_pairs):
        log_metric(k_name, k_val, step_id=step_id, defer_save=(idx_kv < len(kv_pairs) - 1))

    macros_res = ROOT / "results" / "macros_results.tex"
    macros_paper = ROOT / "Papers" / "FCE_Nature_ver01" / "macros_results.tex"
    export_macros(output_path=str(macros_res))
    if macros_paper.parent.exists():
        export_macros(output_path=str(macros_paper))

    # Write 100% macro-backed LaTeX convergence table when all 4 channels have FDTD data
    all_complete = all(summary["solver_agreement"][ck].get("status") == "complete" for ck in chan_macro_prefix)
    if all_complete:
        def _m(key: str) -> str:
            return f"\\{_sanitize_macro_name(key)}"

        def _row(state_lbl: str, mat_lbl: str, pfx: str, r_fin: int) -> str:
            return (
                f"{state_lbl} & {mat_lbl} & "
                f"${_m(f'{pfx}_bem_t4_pn')}$ & "
                f"${_m(f'{pfx}_bem_inf_pn')} \\pm {_m(f'{pfx}_bem_se_pn')}$ & "
                f"${_m(f'{pfx}_fdtd_r{r_fin}_pn')}$ & "
                f"${_m(f'{pfx}_fdtd_inf_pn')} \\pm {_m(f'{pfx}_fdtd_se_pn')}$ & "
                f"${_m(f'{pfx}_rel_diff_pct')}\\%$ \\\\"
            )

        tex_lines = [
            "% Auto-generated by execution/run_h3_single_setup_convergence.py -- DO NOT EDIT BY HAND",
            "\\begin{table}[htbp]",
            "\\centering",
            "\\caption{Single-setup three-dimensional Maxwell RWG BEM and four-pass Meep FDTD quantitative convergence across kinematic states and material models on the shared $20\\,\\mathrm{nm}$-lattice \\texttt{H3-Cantor} unit cell ($4\\times$ $C_4$ clutch multiplicity; $\\pm$ denotes continuum extrapolation standard error).}",
            "\\label{tab:single-setup-convergence}",
            "\\small",
            "\\begin{tabular}{llccccc}",
            "\\toprule",
            "Kinematic state & Material & BEM finest & BEM continuum & FDTD finest & FDTD continuum & $|\\Delta F_{\\infty}|$ \\\\",
            " & & (Tier 4, pN) & ($h\\!\\to\\!0$, pN) & (pN) & ($\\Delta x\\!\\to\\!0$, pN) & (\\%) \\\\",
            "\\midrule",
            _row("Open slot ($+F_z$)", "PEC (EFIE)", "conv_open_pec", 250),
            _row("Open slot ($+F_z$)", "Drude Au (PMCHWT)", "conv_open_gold", 200),
            _row("Engaged pad ($-F_z$)", "PEC (EFIE)", "conv_eng_pec", 250),
            _row("Engaged pad ($-F_z$)", "Drude Au (PMCHWT)", "conv_eng_gold", 200),
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        ]
        table_text = "\n".join(tex_lines)
        table_paper = ROOT / "Papers" / "FCE_Nature_ver01" / "tables" / "table_h3_single_setup_convergence.tex"
        table_res = ROOT / "results" / "table_h3_single_setup_convergence.tex"
        _atomic_write_text(table_paper, table_text)
        _atomic_write_text(table_res, table_text)


def _render_convergence_figure(summary: dict[str, Any], bem_data: dict[str, Any], summary_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 8.5,
            "axes.titlesize": 9.5,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "legend.fontsize": 7.5,
        }
    )

    fig, axes = plt.subplots(2, 3, figsize=(12.2, 7.2), dpi=300)
    panel_configs = [
        (axes[0, 0], "open_pec", "a  Open-slot repulsion (PEC)", "#1b6ca8"),
        (axes[0, 1], "open_gold", "b  Open-slot repulsion (Drude Au)", "#d97706"),
        (axes[1, 0], "engaged_pec", "d  Engaged-pad attraction (PEC)", "#0f766e"),
        (axes[1, 1], "engaged_gold", "e  Engaged-pad attraction (Drude Au)", "#b91c1c"),
    ]

    for ax, chan_key, title, color in panel_configs:
        bem_pts = bem_data["mesh_ladder"][chan_key]
        # Normalized discretization scale s = h / h_coarse in [0, 1]
        h0_bem = float(bem_pts[0]["h_eff_nm"])
        x_bem = [float(p["h_eff_nm"]) / h0_bem for p in bem_pts]
        y_bem = [float(p["F_z_total_pN"]) for p in bem_pts]
        bem_inf = float(bem_data["continuum_extrapolation"][chan_key]["f_inf"])
        bem_se = float(bem_data["continuum_extrapolation"][chan_key]["se_fit"])

        ax.plot(x_bem, y_bem, "o-", color=color, lw=1.8, ms=5.5, label="3D Maxwell RWG BEM")
        ax.errorbar([0.0], [bem_inf], yerr=[bem_se], fmt="s", color=color, ms=6.0, capsize=3, label="BEM continuum ($h\\to 0$)")

        fdtd_pts = summary["fdtd_ladders"].get(chan_key, [])
        if fdtd_pts:
            dx0 = float(fdtd_pts[0]["dx_nm"])
            x_fdtd = [float(p["dx_nm"]) / dx0 for p in fdtd_pts]
            y_fdtd = [float(p["f_net_pN"]) for p in fdtd_pts]
            ax.plot(x_fdtd, y_fdtd, "^--", color="#111827", lw=1.6, ms=5.5, label="4-pass 3D Meep FDTD")
            comp = summary["solver_agreement"][chan_key]
            if comp.get("status") == "complete":
                ax.errorbar(
                    [0.02],
                    [float(comp["fdtd_continuum_pN"])],
                    yerr=[float(comp["fdtd_continuum_se_pN"])],
                    fmt="D",
                    color="#111827",
                    ms=5.5,
                    capsize=3,
                    label=f"FDTD continuum ($|\\Delta|={comp['continuum_rel_diff_pct']:.1f}\\%$)",
                )

        ax.axhline(bem_inf, color=color, ls=":", lw=1.0, alpha=0.65)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel("Normalized grid/mesh scale ($h / h_{\\mathrm{coarse}}$, $\\Delta x / \\Delta x_{\\mathrm{coarse}} \\to 0$)")
        ax.set_ylabel("4-sector normal force $F_z$ (pN)")
        ax.set_xlim(-0.06, 1.08)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", frameon=True)

    # Panel c: Imaginary-wavenumber spectral integrand dF_z / d(kappa)
    ax_c = axes[0, 2]
    for chan_key, lbl, col, ls in (
        ("open_pec", "Open PEC ($+F_z$)", "#1b6ca8", "-"),
        ("open_gold", "Open Drude Au ($+F_z$)", "#d97706", "--"),
        ("engaged_pec", "Engaged PEC ($-F_z$, $\\times 0.25$)", "#0f766e", "-."),
        ("engaged_gold", "Engaged Drude Au ($-F_z$, $\\times 0.25$)", "#b91c1c", ":"),
    ):
        finest = bem_data["mesh_ladder"][chan_key][-1]
        ks = np.array(finest["kappas_um_inv"], dtype=np.float64)
        fs = np.array(finest["f_spectrum_pN_um"], dtype=np.float64)
        scale = 0.25 if "engaged" in chan_key else 1.0
        ax_c.plot(ks, fs * scale, ls=ls, color=col, lw=1.7, label=lbl)
    ax_c.axhline(0.0, color="#6b7280", lw=0.9)
    ax_c.set_xscale("log")
    ax_c.set_title("c  Wick-rotated spectral force density", loc="left", fontweight="bold")
    ax_c.set_xlabel("Imaginary wavenumber $\\kappa = \\xi / c$ ($\\mu\\mathrm{m}^{-1}$)")
    ax_c.set_ylabel("$dF_z / d\\kappa$ ($\\mathrm{pN}\\cdot\\mu\\mathrm{m}$)")
    ax_c.grid(True, alpha=0.25)
    ax_c.legend(loc="best", frameon=True)

    # Panel f: Diagnostics — Quadrature stability + FDTD Gauss-law / source-order controls
    ax_f = axes[1, 2]
    q_lad = bem_data["quadrature_ladder_tier2"]
    n_xis = [int(r["n_xi"]) for r in q_lad]
    ref_op = float(q_lad[-1]["open_gold_pN"])
    ref_en = float(q_lad[-1]["engaged_gold_pN"])
    err_op = [max(abs(float(r["open_gold_pN"]) - ref_op) / abs(ref_op) * 100.0, 1e-5) for r in q_lad[:-1]]
    err_en = [max(abs(float(r["engaged_gold_pN"]) - ref_en) / abs(ref_en) * 100.0, 1e-5) for r in q_lad[:-1]]
    ax_f.semilogy(n_xis[:-1], err_op, "o-", color="#d97706", lw=1.7, label="BEM open Au $|\\Delta(n_\\xi)|$ (%)")
    ax_f.semilogy(n_xis[:-1], err_en, "s--", color="#b91c1c", lw=1.7, label="BEM engaged Au $|\\Delta(n_\\xi)|$ (%)")

    open_pec_fdtd = summary["fdtd_ladders"].get("open_pec", [])
    if open_pec_fdtd:
        res_x = [int(p["resolution"]) / 10.0 for p in open_pec_fdtd]  # map R=100..250 -> 10..25 on shared axis
        leak_pct = [
            max(abs(float(p["f_stator_only_pN"])) / max(abs(float(p["f_net_pN"])), 1e-12) * 100.0, 1e-4)
            for p in open_pec_fdtd
        ]
        ax_f.semilogy(res_x, leak_pct, "^:", color="#111827", lw=1.6, label="FDTD $|F_{\\mathrm{stator}}|/|F_{\\mathrm{net}}|$ (%, $R/10$)")

    ax_f.set_title("f  Quadrature & Gauss-law residual decay", loc="left", fontweight="bold")
    ax_f.set_xlabel("Quadrature order $n_\\xi$ (or FDTD $R/10$)")
    ax_f.set_ylabel("Relative residual (%)")
    ax_f.grid(True, which="both", alpha=0.25)
    ax_f.legend(loc="best", frameon=True)

    fig.tight_layout()
    fig_dir = ROOT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fig_dir / "fig_h3_single_setup_convergence.pdf"
    png_path = fig_dir / "fig_h3_single_setup_convergence.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    cols = [
        "bem_summary.mesh_ladder",
        "bem_summary.continuum_extrapolation",
        "bem_summary.quadrature_ladder_tier2",
        "fdtd_ladders",
        "solver_agreement",
    ]
    for p in (pdf_path, png_path):
        save_plot_provenance(
            str(p),
            str(summary_path),
            cols,
            solver_name="Maxwell_RWG_BEM_and_Meep_3D_FDTD",
            solver_parameters={"code_hash": bem_data.get("code_hash", "")},
        )

    paper_fig_dir = ROOT / "Papers" / "FCE_Nature_ver01" / "figures"
    if paper_fig_dir.exists():
        for p in (
            pdf_path,
            png_path,
            pdf_path.with_suffix(".pdf.provenance.json"),
            png_path.with_suffix(".png.provenance.json"),
        ):
            if p.exists():
                shutil.copyfile(p, paper_fig_dir / p.name)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--n-xi", type=int, default=16)
    parser.add_argument("--max-steps", type=int, default=0, help="Empirical micro-probe steps for hpc_gate.py.")
    parser.add_argument("--generate-fdtd-configs", action="store_true")
    parser.add_argument(
        "--fdtd-config-dir",
        type=Path,
        default=ROOT / "sweep_configs_h3_single_setup_fdtd",
    )
    parser.add_argument("--run-bem", action="store_true")
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=ROOT / ".tmp" / "h3_single_setup_bem_ckpt",
    )
    parser.add_argument(
        "--bem-output",
        type=Path,
        default=ROOT / "results" / "h3_single_setup_bem_convergence.json",
    )
    parser.add_argument("--aggregate", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_steps > 0:
        run_bem_convergence_suite(
            device_arg=args.device,
            n_xi_default=args.n_xi,
            checkpoint_dir=args.checkpoint_dir,
            output_path=args.bem_output,
            max_steps=args.max_steps,
        )
        return 0

    did_work = False
    if args.generate_fdtd_configs:
        written = generate_fdtd_configs(args.fdtd_config_dir)
        print(f"Generated {len(written)} Yee-aligned FDTD configs in {args.fdtd_config_dir}", flush=True)
        did_work = True

    if args.run_bem:
        run_bem_convergence_suite(
            device_arg=args.device,
            n_xi_default=args.n_xi,
            checkpoint_dir=args.checkpoint_dir,
            output_path=args.bem_output,
            max_steps=0,
        )
        did_work = True

    if args.aggregate:
        aggregate_convergence_results(bem_json_path=args.bem_output)
        did_work = True

    if not did_work:
        # Default CLI invocation without flags runs BEM suite
        run_bem_convergence_suite(
            device_arg=args.device,
            n_xi_default=args.n_xi,
            checkpoint_dir=args.checkpoint_dir,
            output_path=args.bem_output,
            max_steps=0,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
