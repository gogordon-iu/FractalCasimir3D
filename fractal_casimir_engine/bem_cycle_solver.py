#!/usr/bin/env python3
"""Exact 3D cyclic and 6-DOF BEM solvers for the Fractal Casimir Engine.

Computes Casimir interaction energy E_C(z, theta), axial force F_z = -dE_C/dz,
and azimuthal torque tau_theta = -dE_C/dtheta simultaneously, with support for:
  - Arbitrary Gauss-Legendre sub-panel quadrature order (quad_order in {1, 2, 3, 4},
    i.e., 1, 4, 9, or 16 quadrature nodes per panel) and sub-panel regularization
    scaling (sub_var_scale).
  - GPU-accelerated PyTorch float64/complex128 cross-block & self-block assembly.
  - Outer-loop-over-frequency batch evaluation (evaluate_states_batch) keeping peak
    VRAM O(1) in n_xi while evaluating multiple Kramers-Kronig dispersive material
    pairings (Gold, PEC, VO2_Metallic, VO2_Insulating, Silicon_Intrinsic,
    Silicon_PhotoDoped) in a single geometric pass.
  - Full 4-sector non-Bloch 6-DOF Euclidean rigid-body evaluation
    (Full4Sector6DofBemEvaluator) for lateral (x, y) and tilt (theta_x, theta_y)
    pull-in stability Hessians and EBL corner-rounded (r_edge_nm > 0) prisms.
"""

from __future__ import annotations

import dataclasses
import math
import time
from typing import Any, Literal, Sequence

import numpy as np
from scipy import linalg

from execution.casimir_bem_solver import (
    BEM_TIER_STANDARD,
    ClutchSurfaceMesh,
    DEFAULT_CONDITION_LIMIT,
    DEFAULT_MAX_MEMORY_GIB,
    DenseBackend,
    Formulation,
    PanelType,
    SurfacePanel,
    _assert_real,
    _disk_self_term,
    _formulation_qualification,
    _quadrature,
    _rotation,
)
from execution.materials_database_dispersive import (
    BOLTZMANN_K_EV_PER_K,
    GOLD_EPS_INF,
    GOLD_GAMMA_EV,
    GOLD_WP_EV,
    HBAR_C_EV_UM,
    MEEP_FORCE_TO_SI,
    SILICON_E0_EV,
    SILICON_EPS_INF,
    SILICON_EPS_STATIC,
    SILICON_GAMMA_EV,
)
from fractal_casimir_engine.geometries import (
    ENGINE_KAPPA_0_REF_UM_INV,
    ENGINE_K_EFF_REF_UM_INV,
    ENGINE_Z_TIP_MIN_UM,
    build_engine_surface_mesh,
    certify_minimum_clearance_um,
)

# MEEP_FORCE_TO_SI = 3.16152649e-14 N (hbar*c / (1 um)^2); * 1e12 = 0.0316152649 pN (and aJ, pN*um)
DIMLESS_TO_PN_AJ: float = float(MEEP_FORCE_TO_SI) * 1.0e12
AJ_TO_MEV: float = 1.0 / 0.1602176634e-3  # 1 aJ = 6.241509074 eV = 6241.509 meV


# Kramers-Kronig compliant dispersive optical models (energies in eV; converted to um^-1 via HBAR_C_EV_UM):
# - VO2_Metallic (rutile metallic phase T > 341 K / photo-switched; Verleur et al. PR 172, 788 (1968);
#   Qazilbash et al. Science 318, 1750 (2007); Pirozhenko & Lambrecht PRA 77, 013811 (2008)).
# - VO2_Insulating (monoclinic M1 insulating phase T < 340 K; Verleur et al. 1968; Pirozhenko & Lambrecht 2008).
# - Silicon_Intrinsic & Silicon_PhotoDoped (laser carrier-modulated Si; Chen et al. PRB 76, 035338 (2007)).
DISPERSIVE_ENGINE_MATERIALS: dict[str, dict[str, Any]] = {
    "pec": {
        "canonical": "PEC",
        "is_pec": True,
        "eps_inf": None,
        "wp_eV": 0.0,
        "gamma_eV": 0.0,
        "oscillators_eV": (),
    },
    "gold": {
        "canonical": "Gold",
        "is_pec": False,
        "eps_inf": GOLD_EPS_INF,
        "wp_eV": GOLD_WP_EV,
        "gamma_eV": GOLD_GAMMA_EV,
        "oscillators_eV": (),
    },
    "au": {
        "canonical": "Gold",
        "is_pec": False,
        "eps_inf": GOLD_EPS_INF,
        "wp_eV": GOLD_WP_EV,
        "gamma_eV": GOLD_GAMMA_EV,
        "oscillators_eV": (),
    },
    "vo2_metallic": {
        "canonical": "VO2_Metallic",
        "is_pec": False,
        "eps_inf": 3.95,
        "wp_eV": 3.33,
        "gamma_eV": 0.66,
        "oscillators_eV": (
            {"E0_eV": 2.80, "f_eV2": 7.80, "gamma_eV": 0.90},
            {"E0_eV": 6.50, "f_eV2": 28.00, "gamma_eV": 1.50},
        ),
    },
    "vo2_insulating": {
        "canonical": "VO2_Insulating",
        "is_pec": False,
        "eps_inf": 4.26,
        "wp_eV": 0.0,
        "gamma_eV": 0.0,
        "oscillators_eV": (
            {"E0_eV": 1.30, "f_eV2": 3.90, "gamma_eV": 0.55},
            {"E0_eV": 3.45, "f_eV2": 19.80, "gamma_eV": 1.10},
            {"E0_eV": 7.20, "f_eV2": 31.00, "gamma_eV": 1.80},
        ),
    },
    "silicon": {
        "canonical": "Silicon_Intrinsic",
        "is_pec": False,
        "eps_inf": SILICON_EPS_INF,
        "wp_eV": 0.0,
        "gamma_eV": 0.0,
        "oscillators_eV": (
            {
                "E0_eV": SILICON_E0_EV,
                "f_eV2": (SILICON_EPS_STATIC - SILICON_EPS_INF) * (SILICON_E0_EV**2),
                "gamma_eV": SILICON_GAMMA_EV,
            },
        ),
    },
    "silicon_intrinsic": {
        "canonical": "Silicon_Intrinsic",
        "is_pec": False,
        "eps_inf": SILICON_EPS_INF,
        "wp_eV": 0.0,
        "gamma_eV": 0.0,
        "oscillators_eV": (
            {
                "E0_eV": SILICON_E0_EV,
                "f_eV2": (SILICON_EPS_STATIC - SILICON_EPS_INF) * (SILICON_E0_EV**2),
                "gamma_eV": SILICON_GAMMA_EV,
            },
        ),
    },
    "silicon_photodoped": {
        "canonical": "Silicon_PhotoDoped",
        "is_pec": False,
        "eps_inf": SILICON_EPS_INF,
        "wp_eV": 2.15,
        "gamma_eV": 0.13,
        "oscillators_eV": (
            {
                "E0_eV": SILICON_E0_EV,
                "f_eV2": (SILICON_EPS_STATIC - SILICON_EPS_INF) * (SILICON_E0_EV**2),
                "gamma_eV": SILICON_GAMMA_EV,
            },
        ),
    },
}


@dataclasses.dataclass(frozen=True)
class EngineMaterialModel:
    """Kramers-Kronig compliant Drude-Lorentz / PEC reflection channel model."""

    name: str
    is_pec: bool
    eps_inf: float | None
    wp_um_inv: float
    gamma_um_inv: float
    oscillators_um_inv: tuple[tuple[float, float, float], ...]

    @classmethod
    def from_name(cls, material_name: str) -> EngineMaterialModel:
        key = material_name.strip().lower()
        if key not in DISPERSIVE_ENGINE_MATERIALS:
            raise ValueError(
                f"Unsupported engine material {material_name!r}; "
                f"expected one of {sorted(DISPERSIVE_ENGINE_MATERIALS)}."
            )
        spec = DISPERSIVE_ENGINE_MATERIALS[key]
        if spec["is_pec"]:
            return cls(spec["canonical"], True, None, 0.0, 0.0, ())
        osc_list: list[tuple[float, float, float]] = []
        for osc in spec["oscillators_eV"]:
            w0 = float(osc["E0_eV"]) / HBAR_C_EV_UM
            f_um2 = float(osc["f_eV2"]) / (HBAR_C_EV_UM**2)
            gam = float(osc["gamma_eV"]) / HBAR_C_EV_UM
            osc_list.append((w0, f_um2, gam))
        return cls(
            name=spec["canonical"],
            is_pec=False,
            eps_inf=float(spec["eps_inf"]),
            wp_um_inv=float(spec["wp_eV"]) / HBAR_C_EV_UM,
            gamma_um_inv=float(spec["gamma_eV"]) / HBAR_C_EV_UM,
            oscillators_um_inv=tuple(osc_list),
        )

    def epsilon(self, kappa: float) -> float | None:
        if kappa <= 0.0 or not math.isfinite(kappa):
            raise ValueError("kappa must be finite and positive.")
        if self.is_pec:
            return None
        assert self.eps_inf is not None
        eps = float(self.eps_inf)
        if self.wp_um_inv > 0.0:
            denom = kappa * (kappa + self.gamma_um_inv)
            eps += (self.wp_um_inv**2) / denom
        for w0, f_um2, gam in self.oscillators_um_inv:
            eps += f_um2 / (w0 * w0 + kappa * kappa + gam * kappa)
        if not math.isfinite(eps) or eps <= 0.0:
            raise FloatingPointError(f"Non-physical epsilon(i*kappa)={eps} for {self.name}.")
        return eps

    def channel_weights(self, kappa: float, *, k_eff: float) -> tuple[float, float, float | None]:
        eps = self.epsilon(kappa)
        if eps is None:
            return 1.0, -1.0, None
        k_par = max(float(k_eff), 1.0e-3)
        gamma_0 = math.hypot(kappa, k_par)
        gamma_m = math.hypot(kappa * math.sqrt(eps), k_par)
        gamma_m_over_eps = gamma_m / eps
        tm = (gamma_0 - gamma_m_over_eps) / (gamma_0 + gamma_m_over_eps)
        te = (gamma_0 - gamma_m) / (gamma_0 + gamma_m)
        if not (math.isfinite(tm) and math.isfinite(te)):
            raise FloatingPointError(f"Non-finite channel weights for {self.name} at kappa={kappa}.")
        return tm, te, eps


@dataclasses.dataclass(frozen=True)
class EngineBodyPanels:
    """Oriented surface panel array supporting arbitrary Gauss-Legendre sub-panel quadrature."""

    centroids: np.ndarray
    normals: np.ndarray
    areas: np.ndarray
    panel_types: tuple[PanelType, ...]
    tangents: np.ndarray
    quad_points: np.ndarray
    quad_weights: np.ndarray
    quad_order: int = 2

    def __post_init__(self) -> None:
        n = int(self.areas.size)
        q_expected = int(self.quad_order) ** 2
        if self.centroids.shape != (n, 3) or not np.isfinite(self.centroids).all():
            raise ValueError("centroids must have finite shape (N, 3).")
        if self.normals.shape != (n, 3) or not np.isfinite(self.normals).all():
            raise ValueError("normals must have finite shape (N, 3).")
        if self.tangents.shape != (n, 2, 3) or not np.isfinite(self.tangents).all():
            raise ValueError("tangents must have finite shape (N, 2, 3).")
        if self.quad_points.shape != (n, q_expected, 3) or not np.isfinite(self.quad_points).all():
            raise ValueError(f"quad_points must have finite shape (N, {q_expected}, 3).")
        if self.quad_weights.shape != (q_expected,) or not math.isclose(
            float(np.sum(self.quad_weights)), 1.0, rel_tol=1.0e-12, abs_tol=1.0e-12
        ):
            raise ValueError("quad_weights must sum to 1.0.")

    @property
    def count(self) -> int:
        return int(self.areas.size)


def build_engine_body_panels(
    panels: Sequence[SurfacePanel],
    *,
    quad_order: int = 2,
) -> EngineBodyPanels:
    """Build EngineBodyPanels with tensor-product Gauss-Legendre quadrature of order `quad_order`."""
    if quad_order not in (1, 2, 3, 4):
        raise ValueError(f"quad_order must be in {{1, 2, 3, 4}}; got {quad_order}.")
    if not panels:
        raise ValueError("Panel sequence cannot be empty.")

    normals = np.asarray([p.normal for p in panels], dtype=np.float64)
    vertices = np.asarray([p.vertices for p in panels], dtype=np.float64)
    edges = vertices[:, 1] - vertices[:, 0]
    t1 = edges - np.sum(edges * normals, axis=1)[:, None] * normals
    lengths = np.linalg.norm(t1, axis=1)
    if not np.isfinite(lengths).all() or np.any(lengths <= 0.0):
        raise ValueError("Cannot construct panel tangent basis from vertices.")
    t1 /= lengths[:, None]
    tangents = np.stack((t1, np.cross(normals, t1)), axis=1)

    nodes_1d, weights_1d = np.polynomial.legendre.leggauss(quad_order)
    uv_nodes = 0.5 * (nodes_1d + 1.0)
    uv_weights = 0.5 * weights_1d

    q_pts_list: list[np.ndarray] = []
    q_wts_list: list[float] = []
    for iu, u in enumerate(uv_nodes):
        for iv, v in enumerate(uv_nodes):
            uf, vf = float(u), float(v)
            pt = (
                (1.0 - uf) * (1.0 - vf) * vertices[:, 0]
                + uf * (1.0 - vf) * vertices[:, 1]
                + uf * vf * vertices[:, 2]
                + (1.0 - uf) * vf * vertices[:, 3]
            )
            q_pts_list.append(pt)
            q_wts_list.append(float(uv_weights[iu] * uv_weights[iv]))

    return EngineBodyPanels(
        centroids=np.asarray([p.centroid for p in panels], dtype=np.float64),
        normals=normals,
        areas=np.asarray([p.area for p in panels], dtype=np.float64),
        panel_types=tuple(p.panel_type for p in panels),
        tangents=tangents,
        quad_points=np.stack(q_pts_list, axis=1),
        quad_weights=np.asarray(q_wts_list, dtype=np.float64),
        quad_order=int(quad_order),
    )


def detect_compute_device(requested: Literal["auto", "cpu", "cuda"] = "auto") -> Literal["cpu", "cuda"]:
    """Dynamic PyTorch CUDA detection honoring project hardware contract."""
    if requested == "cpu":
        return "cpu"
    try:
        import torch

        has_cuda = bool(torch.cuda.is_available())
    except ImportError:
        has_cuda = False
    if requested == "cuda" and not has_cuda:
        raise RuntimeError("CUDA requested explicitly, but torch.cuda.is_available() is False.")
    return "cuda" if has_cuda else "cpu"


def _z_cross(vectors: np.ndarray) -> np.ndarray:
    """Compute z_hat x v = (-v_y, v_x, 0) along the last axis."""
    out = np.zeros_like(vectors)
    out[..., 0] = -vectors[..., 1]
    out[..., 1] = vectors[..., 0]
    return out


def transform_rotor_panels(
    rotor_ref: EngineBodyPanels,
    *,
    dz_um: float,
    theta_rad: float,
) -> EngineBodyPanels:
    """Apply exact rigid rotation theta_rad about +z and translation dz_um along +z."""
    c = math.cos(theta_rad)
    s = math.sin(theta_rad)
    rmat = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    shift = np.array([0.0, 0.0, dz_um], dtype=np.float64)
    centroids = rotor_ref.centroids @ rmat.T + shift
    normals = rotor_ref.normals @ rmat.T
    tangents = np.einsum("ab,imb->ima", rmat, rotor_ref.tangents)
    quad_points = np.einsum("ab,iqb->iqa", rmat, rotor_ref.quad_points) + shift
    return EngineBodyPanels(
        centroids=centroids,
        normals=normals,
        areas=rotor_ref.areas,
        panel_types=rotor_ref.panel_types,
        tangents=tangents,
        quad_points=quad_points,
        quad_weights=rotor_ref.quad_weights,
        quad_order=rotor_ref.quad_order,
    )


def transform_panels_rigid_3d(
    panels_ref: EngineBodyPanels,
    *,
    rmat: np.ndarray,
    shift_um: np.ndarray,
) -> EngineBodyPanels:
    """Apply arbitrary SO(3) rotation `rmat` and 3D translation `shift_um`."""
    centroids = panels_ref.centroids @ rmat.T + shift_um
    normals = panels_ref.normals @ rmat.T
    tangents = np.einsum("ab,imb->ima", rmat, panels_ref.tangents)
    quad_points = np.einsum("ab,iqb->iqa", rmat, panels_ref.quad_points) + shift_um
    return EngineBodyPanels(
        centroids=centroids,
        normals=normals,
        areas=panels_ref.areas,
        panel_types=panels_ref.panel_types,
        tangents=tangents,
        quad_points=quad_points,
        quad_weights=panels_ref.quad_weights,
        quad_order=panels_ref.quad_order,
    )


def _assemble_self_block(
    body: EngineBodyPanels,
    source_sector: int,
    kappa: float,
    formulation: Formulation,
    *,
    sub_var_scale: float = 1.0,
    torch_mod: Any = None,
) -> np.ndarray:
    """Assemble single-layer self-interaction operator block (GPU-accelerated if torch_mod given)."""
    rotation = _rotation(source_sector)
    self_block = source_sector == 0
    n = body.count
    q_count = int(body.quad_weights.size)

    if torch_mod is not None:
        dev = "cuda"
        dt = torch_mod.float64
        areas = torch_mod.as_tensor(body.areas, dtype=dt, device=dev)
        t_qpts = torch_mod.as_tensor(body.quad_points, dtype=dt, device=dev)
        s_qpts = torch_mod.as_tensor(body.quad_points @ rotation.T, dtype=dt, device=dev)
        qw = body.quad_weights
        sub_var = float(sub_var_scale) * (areas[:, None] + areas[None, :]) / (32.0 * math.pi)
        area_scale = torch_mod.sqrt(areas[:, None]) * torch_mod.sqrt(areas[None, :])

        kernel_sum = torch_mod.zeros((n, n), dtype=dt, device=dev)
        for qt in range(q_count):
            for qs in range(q_count):
                w = float(qw[qt] * qw[qs])
                if w == 0.0:
                    continue
                delta = t_qpts[:, qt, None, :] - s_qpts[None, :, qs, :]
                eff_dist = torch_mod.sqrt(torch_mod.sum(delta * delta, dim=2) + sub_var)
                kernel_sum += (
                    torch_mod.exp(-kappa * eff_dist) / (4.0 * math.pi * eff_dist) * (area_scale * w)
                )

        if formulation == "scalar_yukawa":
            out = kernel_sum.cpu().numpy()
            if self_block:
                np.fill_diagonal(out, _disk_self_term(body.areas, kappa))
            return out

        t_tan = torch_mod.as_tensor(body.tangents, dtype=dt, device=dev)
        s_tan = torch_mod.as_tensor(np.einsum("ab,jmb->jma", rotation, body.tangents), dtype=dt, device=dev)
        t_dot_t = torch_mod.einsum("ima,jna->ijmn", t_tan, s_tan)
        single4 = kernel_sum[:, :, None, None] * t_dot_t
        if self_block:
            diag = torch_mod.as_tensor(_disk_self_term(body.areas, kappa), dtype=dt, device=dev)
            idx = torch_mod.arange(n, device=dev)
            single4[idx, idx] = diag[:, None, None] * torch_mod.eye(2, dtype=dt, device=dev)
        out_vec = single4.permute(0, 2, 1, 3).reshape(2 * n, 2 * n).cpu().numpy()
        if not np.isfinite(out_vec).all():
            raise FloatingPointError("Non-finite CUDA self-block.")
        return out_vec

    # CPU NumPy path
    sub_var_np = float(sub_var_scale) * (body.areas[:, None] + body.areas[None, :]) / (32.0 * math.pi)
    area_scale_np = np.sqrt(body.areas[:, None]) * np.sqrt(body.areas[None, :])
    s_pts_np = body.quad_points @ rotation.T
    kernel_np = np.zeros((n, n), dtype=np.float64)
    for qt in range(q_count):
        for qs in range(q_count):
            w = float(body.quad_weights[qt] * body.quad_weights[qs])
            if w == 0.0:
                continue
            delta = body.quad_points[:, qt, None, :] - s_pts_np[None, :, qs, :]
            eff_dist = np.sqrt(np.sum(delta**2, axis=2) + sub_var_np)
            kernel_np += np.exp(-kappa * eff_dist) / (4.0 * math.pi * eff_dist) * (area_scale_np * w)

    if formulation == "scalar_yukawa":
        if self_block:
            np.fill_diagonal(kernel_np, _disk_self_term(body.areas, kappa))
        if not np.isfinite(kernel_np).all():
            raise FloatingPointError("Non-finite scalar self-block.")
        return kernel_np

    s_tan_np = np.einsum("ab,jmb->jma", rotation, body.tangents)
    t_dot_t_np = np.einsum("ima,jna->ijmn", body.tangents, s_tan_np)
    single4_np = kernel_np[:, :, None, None] * t_dot_t_np
    if self_block:
        idx_np = np.arange(n)
        single4_np[idx_np, idx_np] = _disk_self_term(body.areas, kappa)[:, None, None] * np.eye(2)
    out_np = single4_np.transpose(0, 2, 1, 3).reshape(2 * n, 2 * n)
    if not np.isfinite(out_np).all():
        raise FloatingPointError("Non-finite vector self-block.")
    return out_np


def _cross_blocks_with_z_and_theta(
    target: EngineBodyPanels,
    source: EngineBodyPanels,
    source_sector: int,
    kappa: float,
    formulation: Formulation,
    *,
    sub_var_scale: float = 1.0,
    torch_mod: Any = None,
    compute_derivatives: bool = True,
) -> tuple[Any, Any, Any]:
    """Compute cross-body single-layer block G_rs and exact dG_rs/dz, dG_rs/dtheta_rad.

    When ``torch_mod`` is provided, executes entirely in ``torch.float64`` on GPU and returns
    CUDA tensors directly so zero CPU<->GPU copies occur inside the inner loop.
    """
    rotation = _rotation(source_sector)
    q_t_count = int(target.quad_weights.size)
    q_s_count = int(source.quad_weights.size)

    if torch_mod is not None:
        dev = "cuda"
        dt = torch_mod.float64
        t_areas = torch_mod.as_tensor(target.areas, dtype=dt, device=dev)
        s_areas = torch_mod.as_tensor(source.areas, dtype=dt, device=dev)
        t_qpts = torch_mod.as_tensor(target.quad_points, dtype=dt, device=dev)
        s_qpts = torch_mod.as_tensor(source.quad_points @ rotation.T, dtype=dt, device=dev)
        dtheta_q_t = torch_mod.as_tensor(_z_cross(target.quad_points), dtype=dt, device=dev)

        sub_var = float(sub_var_scale) * (t_areas[:, None] + s_areas[None, :]) / (32.0 * math.pi)
        area_scale = torch_mod.sqrt(t_areas[:, None]) * torch_mod.sqrt(s_areas[None, :])

        if formulation == "scalar_yukawa":
            shape2 = (target.count, source.count)
            single = torch_mod.zeros(shape2, dtype=dt, device=dev)
            dz = torch_mod.zeros(shape2, dtype=dt, device=dev) if compute_derivatives else None
            dtheta = torch_mod.zeros(shape2, dtype=dt, device=dev) if compute_derivatives else None
            for qt in range(q_t_count):
                d_qt = dtheta_q_t[:, qt, None, :]
                for qs in range(q_s_count):
                    weight = float(target.quad_weights[qt] * source.quad_weights[qs])
                    if weight == 0.0:
                        continue
                    delta = t_qpts[:, qt, None, :] - s_qpts[None, :, qs, :]
                    eff_dist = torch_mod.sqrt(torch_mod.sum(delta * delta, dim=2) + sub_var)
                    kernel = (
                        torch_mod.exp(-kappa * eff_dist)
                        / (4.0 * math.pi * eff_dist)
                        * (area_scale * weight)
                    )
                    single += kernel
                    if compute_derivatives:
                        assert dz is not None and dtheta is not None
                        rad_deriv = -kernel * (kappa + 1.0 / eff_dist)
                        dz += rad_deriv * delta[:, :, 2] / eff_dist
                        delta_dot_dtheta = torch_mod.sum(delta * d_qt, dim=2)
                        dtheta += rad_deriv * delta_dot_dtheta / eff_dist
            return single, dz, dtheta

        if formulation != "vector_dyadic":
            raise ValueError(f"Unsupported formulation {formulation!r}.")

        t_tan = torch_mod.as_tensor(target.tangents, dtype=dt, device=dev)
        s_tan = torch_mod.as_tensor(
            np.einsum("ab,jmb->jma", rotation, source.tangents), dtype=dt, device=dev
        )
        dtheta_t_t = torch_mod.as_tensor(_z_cross(target.tangents), dtype=dt, device=dev)
        t_dot_t = torch_mod.einsum("ima,jna->ijmn", t_tan, s_tan)
        dt_dot_t_dtheta = (
            torch_mod.einsum("ima,jna->ijmn", dtheta_t_t, s_tan) if compute_derivatives else None
        )

        shape4 = (target.count, source.count, 2, 2)
        single4 = torch_mod.zeros(shape4, dtype=dt, device=dev)
        dz4 = torch_mod.zeros(shape4, dtype=dt, device=dev) if compute_derivatives else None
        dtheta4 = torch_mod.zeros(shape4, dtype=dt, device=dev) if compute_derivatives else None

        u_z = t_tan[:, :, 2][:, None, :, None]
        v_z = s_tan[:, :, 2][None, :, None, :]

        for qt in range(q_t_count):
            d_qt = dtheta_q_t[:, qt, None, :]
            for qs in range(q_s_count):
                weight = float(target.quad_weights[qt] * source.quad_weights[qs])
                if weight == 0.0:
                    continue
                delta = t_qpts[:, qt, None, :] - s_qpts[None, :, qs, :]
                eff_dist = torch_mod.sqrt(torch_mod.sum(delta * delta, dim=2) + sub_var)
                kernel = (
                    torch_mod.exp(-kappa * eff_dist)
                    / (4.0 * math.pi * eff_dist)
                    * (area_scale * weight)
                )
                scaled_kernel = kernel[:, :, None, None]

                x = kappa * eff_dist
                inv = 1.0 / (1.0 + x)
                denom = 1.0 - inv + inv * inv
                c_dir = (1.0 + inv + inv * inv) / denom

                u_r = torch_mod.einsum("ima,ija->ijm", t_tan, delta)
                v_r = torch_mod.einsum("jna,ija->ijn", s_tan, delta)
                r_inv2 = (1.0 / (eff_dist * eff_dist))[:, :, None, None]
                d_mat = u_r[:, :, :, None] * v_r[:, :, None, :] * r_inv2
                aniso = 0.5 * (t_dot_t - 0.5 * c_dir[:, :, None, None] * d_mat)
                single4 += scaled_kernel * aniso

                if compute_derivatives:
                    assert dz4 is not None and dtheta4 is not None and dt_dot_t_dtheta is not None
                    rad_deriv = -kernel * (kappa + 1.0 / eff_dist)
                    dr_dz = delta[:, :, 2] / eff_dist
                    scaled_dz = (rad_deriv * dr_dz)[:, :, None, None]

                    delta_dot_dtheta = torch_mod.sum(delta * d_qt, dim=2)
                    dr_dtheta = delta_dot_dtheta / eff_dist
                    scaled_dtheta = (rad_deriv * dr_dtheta)[:, :, None, None]

                    dc_dir_dx = -2.0 * (inv * inv) * (1.0 - inv * inv) / (denom * denom)
                    z_comp = delta[:, :, 2][:, :, None, None]
                    dd_dz = (
                        (u_z * v_r[:, :, None, :] + u_r[:, :, :, None] * v_z) * r_inv2
                        - 2.0 * z_comp * d_mat * r_inv2
                    )
                    daniso_dz = (
                        -0.25 * (dc_dir_dx * kappa * dr_dz)[:, :, None, None] * d_mat
                        - 0.25 * c_dir[:, :, None, None] * dd_dz
                    )

                    du_r_dtheta = (
                        torch_mod.einsum("ima,ija->ijm", dtheta_t_t, delta)
                        + torch_mod.einsum("ima,ia->im", t_tan, d_qt[:, 0, :])[:, None, :]
                    )
                    dv_r_dtheta = torch_mod.einsum("jna,ia->ijn", s_tan, d_qt[:, 0, :])
                    dd_dtheta = (
                        (
                            du_r_dtheta[:, :, :, None] * v_r[:, :, None, :]
                            + u_r[:, :, :, None] * dv_r_dtheta[:, :, None, :]
                        )
                        * r_inv2
                        - 2.0 * delta_dot_dtheta[:, :, None, None] * d_mat * r_inv2
                    )
                    daniso_dtheta = 0.5 * dt_dot_t_dtheta - (
                        0.25 * (dc_dir_dx * kappa * dr_dtheta)[:, :, None, None] * d_mat
                        + 0.25 * c_dir[:, :, None, None] * dd_dtheta
                    )

                    dz4 += scaled_dz * aniso + scaled_kernel * daniso_dz
                    dtheta4 += scaled_dtheta * aniso + scaled_kernel * daniso_dtheta

        nr_dof = 2 * target.count
        ns_dof = 2 * source.count
        single_out_g = single4.permute(0, 2, 1, 3).reshape(nr_dof, ns_dof)
        dz_out_g = dz4.permute(0, 2, 1, 3).reshape(nr_dof, ns_dof) if dz4 is not None else None
        dth_out_g = dtheta4.permute(0, 2, 1, 3).reshape(nr_dof, ns_dof) if dtheta4 is not None else None
        return single_out_g, dz_out_g, dth_out_g

    # CPU NumPy path
    dtheta_q_target = _z_cross(target.quad_points)

    if formulation == "scalar_yukawa":
        shape = (target.count, source.count)
        single_np = np.zeros(shape, dtype=np.float64)
        dz_np = np.zeros(shape, dtype=np.float64) if compute_derivatives else None
        dtheta_np = np.zeros(shape, dtype=np.float64) if compute_derivatives else None
        sub_var_s = float(sub_var_scale) * (target.areas[:, None] + source.areas[None, :]) / (32.0 * math.pi)
        area_scale_s = np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :])
        s_pts_rot = source.quad_points @ rotation.T
        for qt in range(q_t_count):
            d_qt = dtheta_q_target[:, qt, None, :]
            for qs in range(q_s_count):
                weight = float(target.quad_weights[qt] * source.quad_weights[qs])
                if weight == 0.0:
                    continue
                delta = target.quad_points[:, qt, None, :] - s_pts_rot[None, :, qs, :]
                eff_dist = np.sqrt(np.sum(delta**2, axis=2) + sub_var_s)
                kernel = np.exp(-kappa * eff_dist) / (4.0 * math.pi * eff_dist) * area_scale_s * weight
                single_np += kernel
                if compute_derivatives:
                    assert dz_np is not None and dtheta_np is not None
                    rad_deriv = -kernel * (kappa + 1.0 / eff_dist)
                    dz_np += rad_deriv * delta[:, :, 2] / eff_dist
                    delta_dot_dtheta = np.sum(delta * d_qt, axis=2)
                    dtheta_np += rad_deriv * delta_dot_dtheta / eff_dist
        if not np.isfinite(single_np).all():
            raise FloatingPointError("Non-finite scalar cross-block.")
        return single_np, dz_np, dtheta_np

    if formulation != "vector_dyadic":
        raise ValueError(f"Unsupported formulation {formulation!r}.")

    source_tangents = np.einsum("ab,jmb->jma", rotation, source.tangents)
    dtheta_t_target = _z_cross(target.tangents)
    t_dot_t_np = np.einsum("ima,jna->ijmn", target.tangents, source_tangents)
    dt_dot_t_dtheta_np = (
        np.einsum("ima,jna->ijmn", dtheta_t_target, source_tangents) if compute_derivatives else None
    )

    shape4_np = (target.count, source.count, 2, 2)
    single4_np = np.zeros(shape4_np, dtype=np.float64)
    dz4_np = np.zeros(shape4_np, dtype=np.float64) if compute_derivatives else None
    dtheta4_np = np.zeros(shape4_np, dtype=np.float64) if compute_derivatives else None

    sub_var_v = float(sub_var_scale) * (target.areas[:, None] + source.areas[None, :]) / (32.0 * math.pi)
    area_scale_v = np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :])
    source_points_rot = source.quad_points @ rotation.T

    u_z_np = target.tangents[:, :, 2][:, None, :, None]
    v_z_np = source_tangents[:, :, 2][None, :, None, :]

    for qt in range(q_t_count):
        d_qt = dtheta_q_target[:, qt, None, :]
        for qs in range(q_s_count):
            weight = float(target.quad_weights[qt] * source.quad_weights[qs])
            if weight == 0.0:
                continue
            delta = target.quad_points[:, qt, None, :] - source_points_rot[None, :, qs, :]
            eff_dist = np.sqrt(np.sum(delta**2, axis=2) + sub_var_v)
            kernel = np.exp(-kappa * eff_dist) / (4.0 * math.pi * eff_dist) * area_scale_v * weight
            scaled_kernel = kernel[:, :, None, None]

            x = kappa * eff_dist
            inv = 1.0 / (1.0 + x)
            denom = 1.0 - inv + inv**2
            c_dir = (1.0 + inv + inv**2) / denom

            u_r = np.einsum("ima,ija->ijm", target.tangents, delta)
            v_r = np.einsum("jna,ija->ijn", source_tangents, delta)
            r_inv2 = (1.0 / eff_dist**2)[:, :, None, None]
            d_mat = u_r[:, :, :, None] * v_r[:, :, None, :] * r_inv2
            aniso = 0.5 * (t_dot_t_np - 0.5 * c_dir[:, :, None, None] * d_mat)
            single4_np += scaled_kernel * aniso

            if compute_derivatives:
                assert dz4_np is not None and dtheta4_np is not None and dt_dot_t_dtheta_np is not None
                rad_deriv = -kernel * (kappa + 1.0 / eff_dist)
                dr_dz = delta[:, :, 2] / eff_dist
                scaled_dz = (rad_deriv * dr_dz)[:, :, None, None]
                delta_dot_dtheta = np.sum(delta * d_qt, axis=2)
                dr_dtheta = delta_dot_dtheta / eff_dist
                scaled_dtheta = (rad_deriv * dr_dtheta)[:, :, None, None]

                dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denom**2
                z_comp = delta[:, :, 2][:, :, None, None]
                dd_dz = (
                    (u_z_np * v_r[:, :, None, :] + u_r[:, :, :, None] * v_z_np) * r_inv2
                    - 2.0 * z_comp * d_mat * r_inv2
                )
                daniso_dz = (
                    -0.25 * (dc_dir_dx * kappa * dr_dz)[:, :, None, None] * d_mat
                    - 0.25 * c_dir[:, :, None, None] * dd_dz
                )

                du_r_dtheta = (
                    np.einsum("ima,ija->ijm", dtheta_t_target, delta)
                    + np.einsum("ima,ia->im", target.tangents, d_qt[:, 0, :])[:, None, :]
                )
                dv_r_dtheta = np.einsum("jna,ia->ijn", source_tangents, d_qt[:, 0, :])
                dd_dtheta = (
                    (du_r_dtheta[:, :, :, None] * v_r[:, :, None, :] + u_r[:, :, :, None] * dv_r_dtheta[:, :, None, :])
                    * r_inv2
                    - 2.0 * delta_dot_dtheta[:, :, None, None] * d_mat * r_inv2
                )
                daniso_dtheta = 0.5 * dt_dot_t_dtheta_np - (
                    0.25 * (dc_dir_dx * kappa * dr_dtheta)[:, :, None, None] * d_mat
                    + 0.25 * c_dir[:, :, None, None] * dd_dtheta
                )

                dz4_np += scaled_dz * aniso + scaled_kernel * daniso_dz
                dtheta4_np += scaled_dtheta * aniso + scaled_kernel * daniso_dtheta

    nr_dof = 2 * target.count
    ns_dof = 2 * source.count
    single_out = single4_np.transpose(0, 2, 1, 3).reshape(nr_dof, ns_dof)
    dz_out = dz4_np.transpose(0, 2, 1, 3).reshape(nr_dof, ns_dof) if dz4_np is not None else None
    dtheta_out = dtheta4_np.transpose(0, 2, 1, 3).reshape(nr_dof, ns_dof) if dtheta4_np is not None else None
    if not np.isfinite(single_out).all():
        raise FloatingPointError("Non-finite vector dyadic cross-block.")
    if compute_derivatives:
        assert dz_out is not None and dtheta_out is not None
        if not (np.isfinite(dz_out).all() and np.isfinite(dtheta_out).all()):
            raise FloatingPointError("Non-finite vector dyadic cross-block derivative.")
    return single_out, dz_out, dtheta_out


@dataclasses.dataclass(frozen=True)
class FrequencySelfFactorCache:
    """Cached cyclic self-operator LU factorizations at one imaginary wavenumber."""

    kappa: float
    weight: float
    tm_product: float
    te_product: float
    rr_lu: tuple[tuple[Any, Any], ...]
    ss_lu: tuple[tuple[Any, Any], ...]
    max_cond_rr: float
    max_cond_ss: float


class PreparedEngineBemModel:
    """Rigid-body 3D cyclic BEM engine evaluator for fast (z, theta) sweeps."""

    def __init__(
        self,
        design_name: str,
        *,
        material: str = "Gold",
        stator_material: str | None = None,
        temperature_K: float = 0.0,
        formulation: Formulation = "vector_dyadic",
        n_r: int = BEM_TIER_STANDARD.n_r,
        n_phi_tooth: int = BEM_TIER_STANDARD.n_phi_tooth,
        n_phi_bridge: int = BEM_TIER_STANDARD.n_phi_bridge,
        n_z: int = BEM_TIER_STANDARD.n_z,
        n_xi: int = BEM_TIER_STANDARD.n_xi,
        n_phi_arc_override: int | None = None,
        quad_order: int = 2,
        sub_var_scale: float = 1.0,
        r_edge_nm: float = 0.0,
        kappa_0_um_inv: float = ENGINE_KAPPA_0_REF_UM_INV,
        k_eff_um_inv: float = ENGINE_K_EFF_REF_UM_INV,
        device: Literal["auto", "cpu", "cuda"] = "auto",
        condition_limit: float = DEFAULT_CONDITION_LIMIT,
        max_memory_gib: float = DEFAULT_MAX_MEMORY_GIB,
        lazy_self_cache: bool = False,
    ) -> None:
        self.design_name = design_name
        self.rotor_material_model = EngineMaterialModel.from_name(material)
        self.stator_material_model = EngineMaterialModel.from_name(
            stator_material if stator_material is not None else material
        )
        self.material_name = self.rotor_material_model.name
        self.stator_material_name = self.stator_material_model.name
        self.temperature_K = float(temperature_K)
        self.formulation: Formulation = formulation
        self.qualification = _formulation_qualification(formulation)
        self.n_r = int(n_r)
        self.n_phi_tooth = int(n_phi_tooth)
        self.n_phi_bridge = int(n_phi_bridge)
        self.n_phi_arc_override = n_phi_arc_override
        self.n_z = int(n_z)
        self.n_xi = int(n_xi)
        self.quad_order = int(quad_order)
        self.sub_var_scale = float(sub_var_scale)
        self.r_edge_nm = float(r_edge_nm)
        self.kappa_0_um_inv = float(kappa_0_um_inv)
        self.k_eff_um_inv = float(k_eff_um_inv)
        self.condition_limit = float(condition_limit)
        self.compute_device = detect_compute_device(device)
        self.backend = DenseBackend(self.compute_device)

        self.z_ref_um = ENGINE_Z_TIP_MIN_UM
        # Use Gold placeholder in ClutchSurfaceMesh metadata when custom dispersive material is used
        mesh_mat = "PEC" if self.rotor_material_model.is_pec else "Gold"
        self.ref_mesh: ClutchSurfaceMesh = build_engine_surface_mesh(
            design_name,
            z_tip_um=self.z_ref_um,
            theta_deg=0.0,
            material=mesh_mat,
            temperature_K=temperature_K,
            n_r=n_r,
            n_phi_tooth=n_phi_tooth,
            n_phi_bridge=n_phi_bridge,
            n_z=n_z,
            n_phi_arc_override=n_phi_arc_override,
            r_edge_nm=r_edge_nm,
            min_clearance_um=0.008,
        )
        self.rotor_ref = build_engine_body_panels(self.ref_mesh.rotor, quad_order=self.quad_order)
        self.stator_ref = build_engine_body_panels(self.ref_mesh.stator, quad_order=self.quad_order)

        dofs = 2 if formulation == "vector_dyadic" else 1
        self.nr_dof = dofs * self.rotor_ref.count
        self.ns_dof = dofs * self.stator_ref.count

        # Per-frequency working memory (when lazy_self_cache=True) vs full cache memory
        per_freq_bytes = 16 * (6 * self.nr_dof**2 + 6 * self.ns_dof**2 + 16 * self.nr_dof * self.ns_dof)
        estimated_bytes = per_freq_bytes if lazy_self_cache else max(
            per_freq_bytes,
            16 * (4 * self.n_xi * (self.nr_dof**2 + self.ns_dof**2) + 12 * self.nr_dof * self.ns_dof),
        )
        if estimated_bytes > max_memory_gib * 1024**3:
            raise MemoryError(
                f"Estimated BEM working memory {estimated_bytes / 1024**3:.2f} GiB exceeds "
                f"budget {max_memory_gib:.2f} GiB."
            )
        if self.backend.torch is not None:
            free_bytes, _ = self.backend.torch.cuda.mem_get_info()
            if estimated_bytes > free_bytes:
                raise MemoryError(
                    f"Estimated BEM working memory ({estimated_bytes / 1024**3:.2f} GiB) exceeds "
                    f"available CUDA memory ({free_bytes / 1024**3:.2f} GiB). "
                    "Use lazy_self_cache=True / evaluate_states_batch or increase max_memory_gib."
                )

        self.kappas, self.weights = self._build_quadrature()
        self.phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)
        self.cache: tuple[FrequencySelfFactorCache, ...] = (
            () if lazy_self_cache else self._precompute_self_factors()
        )

    def _factor_self_operator(self, mat_np: np.ndarray, label: str) -> tuple[tuple[Any, Any], float]:
        if self.backend.torch is not None:
            mat_gpu = self.backend.array(mat_np)
            lu_g, piv_g = self.backend.torch.linalg.lu_factor(mat_gpu)
            dr = self.backend.torch.abs(self.backend.torch.diagonal(lu_g))
            if bool((dr == 0.0).any().item()) or not bool(self.backend.torch.isfinite(dr).all().item()):
                raise linalg.LinAlgError(f"Singular {label} CUDA BEM self-operator.")
            cond = float((self.backend.torch.max(dr) / self.backend.torch.min(dr)).item())
            return (lu_g, piv_g), cond

        lu_c, piv_c = linalg.lu_factor(mat_np, check_finite=True)
        dr_c = np.abs(np.diag(lu_c))
        if np.any(dr_c == 0.0) or not np.isfinite(dr_c).all():
            raise linalg.LinAlgError(f"Singular {label} BEM self-operator.")
        cond_c = float(np.max(dr_c) / np.min(dr_c))
        return (lu_c, piv_c), cond_c

    def _solve_self_operator(self, lu_pair: tuple[Any, Any], rhs: Any) -> Any:
        if self.backend.torch is not None:
            sol = self.backend.torch.linalg.lu_solve(lu_pair[0], lu_pair[1], rhs)
            if not bool(self.backend.torch.isfinite(sol).all().item()):
                raise FloatingPointError("Non-finite CUDA self-operator linear solve.")
            return sol
        sol_c = linalg.lu_solve(lu_pair, rhs, check_finite=True)
        if not np.isfinite(sol_c).all():
            raise FloatingPointError("Non-finite CPU self-operator linear solve.")
        return sol_c

    def _build_quadrature(self) -> tuple[np.ndarray, np.ndarray]:
        if self.temperature_K > 0.0:
            delta_kappa = 2.0 * math.pi * (BOLTZMANN_K_EV_PER_K * self.temperature_K) / HBAR_C_EV_UM
            matsubara_count = min(self.n_xi, min(8, max(2, self.n_xi // 3)))
            kappas = np.arange(matsubara_count, dtype=np.float64) * delta_kappa
            kappas[0] = 1.0e-4 * delta_kappa
            weights = np.full(matsubara_count, delta_kappa, dtype=np.float64)
            weights[0] *= 0.5
            kappa_cut = (matsubara_count - 0.5) * delta_kappa
            tail_k, tail_w, _ = _quadrature(max(1, self.n_xi), self.kappa_0_um_inv)
            return np.concatenate((kappas, kappa_cut + tail_k)), np.concatenate((weights, tail_w))
        kappas, weights, _ = _quadrature(self.n_xi, self.kappa_0_um_inv)
        return kappas, weights

    def build_single_frequency_factor(self, kappa: float, weight: float) -> FrequencySelfFactorCache:
        """Assemble and factorize cyclic Bloch self-operators for a single frequency kappa."""
        k_val = float(kappa)
        tm_r, te_r, _ = self.rotor_material_model.channel_weights(k_val, k_eff=self.k_eff_um_inv)
        tm_s, te_s, _ = self.stator_material_model.channel_weights(k_val, k_eff=self.k_eff_um_inv)
        rr_modes = [np.zeros((self.nr_dof, self.nr_dof), dtype=np.complex128) for _ in range(4)]
        ss_modes = [np.zeros((self.ns_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]
        for sector in range(4):
            b_rr = _assemble_self_block(
                self.rotor_ref,
                sector,
                k_val,
                self.formulation,
                sub_var_scale=self.sub_var_scale,
                torch_mod=self.backend.torch,
            )
            b_ss = _assemble_self_block(
                self.stator_ref,
                sector,
                k_val,
                self.formulation,
                sub_var_scale=self.sub_var_scale,
                torch_mod=self.backend.torch,
            )
            for mode in range(4):
                ph = self.phases[mode, sector]
                rr_modes[mode] += ph * b_rr
                ss_modes[mode] += ph * b_ss

        rr_lu_list: list[tuple[Any, Any]] = []
        ss_lu_list: list[tuple[Any, Any]] = []
        max_c_r = 1.0
        max_c_s = 1.0
        for mode in range(4):
            lu_r_pair, c_r = self._factor_self_operator(rr_modes[mode], "rotor")
            lu_s_pair, c_s = self._factor_self_operator(ss_modes[mode], "stator")
            if max(c_r, c_s) > self.condition_limit:
                raise linalg.LinAlgError(
                    f"Self-operator condition {max(c_r, c_s):g} exceeds {self.condition_limit:g}."
                )
            max_c_r = max(max_c_r, c_r)
            max_c_s = max(max_c_s, c_s)
            rr_lu_list.append(lu_r_pair)
            ss_lu_list.append(lu_s_pair)

        return FrequencySelfFactorCache(
            kappa=k_val,
            weight=float(weight),
            tm_product=float(tm_r * tm_s),
            te_product=float(te_r * te_s),
            rr_lu=tuple(rr_lu_list),
            ss_lu=tuple(ss_lu_list),
            max_cond_rr=max_c_r,
            max_cond_ss=max_c_s,
        )

    def _precompute_self_factors(self) -> tuple[FrequencySelfFactorCache, ...]:
        return tuple(
            self.build_single_frequency_factor(float(k), float(w))
            for k, w in zip(self.kappas, self.weights)
        )

    def solver_metadata(self) -> dict[str, Any]:
        n_phi_arc = (
            int(self.n_phi_arc_override)
            if self.n_phi_arc_override is not None
            else max(self.n_phi_bridge * 3, 9)
        )
        return {
            "solver": "BEM_EngineCycle_3D",
            "design_name": self.design_name,
            "formulation": self.formulation,
            "physics_qualification": self.qualification,
            "material": self.material_name,
            "stator_material": self.stator_material_name,
            "temperature_K": self.temperature_K,
            "device": self.backend.device,
            "n_r": self.n_r,
            "n_phi_tooth": self.n_phi_tooth,
            "n_phi_bridge": self.n_phi_bridge,
            "n_phi_arc": n_phi_arc,
            "n_z": self.n_z,
            "n_xi": self.n_xi,
            "quad_order": self.quad_order,
            "quad_points_per_panel": self.quad_order**2,
            "sub_var_scale": self.sub_var_scale,
            "r_edge_nm": self.r_edge_nm,
            "n_panels_rotor": self.ref_mesh.n_panels_rotor,
            "n_panels_stator": self.ref_mesh.n_panels_stator,
            "n_panels_total": self.ref_mesh.n_panels_total,
            "n_dofs_total": 4 * (self.nr_dof + self.ns_dof),
            "kappa_0_um_inv": self.kappa_0_um_inv,
            "k_eff_um_inv": self.k_eff_um_inv,
            "dataset": "fractal_casimir_engine_cycle",
        }

    def _certify_rotor_pose_clearance(
        self, rotor: EngineBodyPanels, *, min_clearance_um: float, z_tip_um: float, theta_deg: float
    ) -> float:
        rotor_pts = np.concatenate([rotor.centroids, rotor.quad_points.reshape(-1, 3)], axis=0)
        stator_base = np.concatenate(
            [self.stator_ref.centroids, self.stator_ref.quad_points.reshape(-1, 3)], axis=0
        )
        min_sep_um = math.inf
        if self.backend.torch is not None:
            t_mod = self.backend.torch
            r_g = t_mod.as_tensor(rotor_pts, dtype=t_mod.float64, device="cuda")
            for sector in range(4):
                s_g = t_mod.as_tensor(
                    stator_base @ _rotation(sector).T, dtype=t_mod.float64, device="cuda"
                )
                d_min = float(t_mod.min(t_mod.cdist(r_g, s_g)).item())
                min_sep_um = min(min_sep_um, d_min)
        else:
            for sector in range(4):
                stator_pts = stator_base @ _rotation(sector).T
                diff = rotor_pts[:, None, :] - stator_pts[None, :, :]
                min_sep_um = min(min_sep_um, float(np.min(np.linalg.norm(diff, axis=2))))
        if not math.isfinite(min_sep_um) or min_sep_um < min_clearance_um:
            raise ValueError(
                f"Clearance violation at (z={z_tip_um:.4f} um, theta={theta_deg:.2f} deg): "
                f"min quadrature/centroid gap {min_sep_um * 1e3:.2f} nm < {min_clearance_um * 1e3:.2f} nm."
            )
        return min_sep_um

    def _accumulate_single_state_at_frequency(
        self,
        rotor: EngineBodyPanels,
        entry: FrequencySelfFactorCache,
        eye_nr: Any,
        material_pairs_models: Sequence[tuple[str, EngineMaterialModel, EngineMaterialModel]],
    ) -> dict[str, tuple[float, float, float, float, float, float, float]]:
        """Evaluate frequency contribution (logdet, d/dz, d/dtheta) for one or more material pairs."""
        t_mod = self.backend.torch
        if t_mod is not None:
            c_dt = t_mod.complex128
            rs_modes = [t_mod.zeros((self.nr_dof, self.ns_dof), dtype=c_dt, device="cuda") for _ in range(4)]
            dz_modes = [t_mod.zeros((self.nr_dof, self.ns_dof), dtype=c_dt, device="cuda") for _ in range(4)]
            dth_modes = [t_mod.zeros((self.nr_dof, self.ns_dof), dtype=c_dt, device="cuda") for _ in range(4)]
            for sector in range(4):
                g_sec, dz_sec, dth_sec = _cross_blocks_with_z_and_theta(
                    rotor,
                    self.stator_ref,
                    sector,
                    entry.kappa,
                    self.formulation,
                    sub_var_scale=self.sub_var_scale,
                    torch_mod=t_mod,
                )
                g_c = g_sec.to(c_dt)
                dz_c = dz_sec.to(c_dt)
                dth_c = dth_sec.to(c_dt)
                for mode in range(4):
                    ph = complex(self.phases[mode, sector])
                    rs_modes[mode] = rs_modes[mode] + ph * g_c
                    dz_modes[mode] = dz_modes[mode] + ph * dz_c
                    dth_modes[mode] = dth_modes[mode] + ph * dth_c
        else:
            rs_modes = [np.zeros((self.nr_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]
            dz_modes = [np.zeros((self.nr_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]
            dth_modes = [np.zeros((self.nr_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]
            for sector in range(4):
                g_sec, dz_sec, dth_sec = _cross_blocks_with_z_and_theta(
                    rotor,
                    self.stator_ref,
                    sector,
                    entry.kappa,
                    self.formulation,
                    sub_var_scale=self.sub_var_scale,
                    torch_mod=None,
                )
                for mode in range(4):
                    ph = self.phases[mode, sector]
                    rs_modes[mode] += ph * g_sec
                    dz_modes[mode] += ph * dz_sec
                    dth_modes[mode] += ph * dth_sec

        # Solve geometric coupling matrices ONCE across all requested material pairs
        mode_couplings: list[tuple[Any, Any, Any]] = []
        for mode in range(4):
            g = rs_modes[mode] if t_mod is not None else self.backend.array(rs_modes[mode])
            dg_z = dz_modes[mode] if t_mod is not None else self.backend.array(dz_modes[mode])
            dg_th = dth_modes[mode] if t_mod is not None else self.backend.array(dth_modes[mode])

            sr = self.backend.adjoint(g)
            dsr_z = self.backend.adjoint(dg_z)
            dsr_th = self.backend.adjoint(dg_th)

            ncol = g.shape[1]
            x_all = self._solve_self_operator(
                entry.rr_lu[mode],
                self.backend.concat_cols((g, dg_z, dg_th)),
            )
            x = x_all[:, :ncol]
            dx_z = x_all[:, ncol : 2 * ncol]
            dx_th = x_all[:, 2 * ncol :]

            ncol_s = sr.shape[1]
            z_all = self._solve_self_operator(
                entry.ss_lu[mode],
                self.backend.concat_cols((sr, dsr_z, dsr_th)),
            )
            z_op = z_all[:, :ncol_s]
            dz_z = z_all[:, ncol_s : 2 * ncol_s]
            dz_th = z_all[:, 2 * ncol_s :]

            coupling = x @ z_op
            dcoupling_z = dx_z @ z_op + x @ dz_z
            dcoupling_th = dx_th @ z_op + x @ dz_th
            mode_couplings.append((coupling, dcoupling_z, dcoupling_th))

        w_q = entry.weight
        per_pair_out: dict[str, tuple[float, float, float, float, float, float, float]] = {}
        for pair_key, r_mat, s_mat in material_pairs_models:
            tm_r, te_r, _ = r_mat.channel_weights(entry.kappa, k_eff=self.k_eff_um_inv)
            tm_s, te_s, _ = s_mat.channel_weights(entry.kappa, k_eff=self.k_eff_um_inv)
            pw_tm = float(tm_r * tm_s)
            pw_te = float(te_r * te_s)

            logdet_sum = 0j
            dlogdet_dz_sum = 0j
            dlogdet_dth_sum = 0j
            ch_dz = {"TM": 0j, "TE": 0j}
            ch_dth = {"TM": 0j, "TE": 0j}

            for coupling, dcoupling_z, dcoupling_th in mode_couplings:
                tm_cached: tuple[complex, complex, complex] | None = None
                for ch_name, pw in (("TM", pw_tm), ("TE", pw_te)):
                    if (
                        ch_name == "TE"
                        and tm_cached is not None
                        and math.isclose(pw_tm, pw_te, rel_tol=1.0e-14)
                    ):
                        c_logdet, c_dz, c_dth = tm_cached
                    else:
                        y_mat = eye_nr - pw * coupling
                        ny = dcoupling_z.shape[1]
                        sol, cond_y, c_logdet_opt = self.backend.factor_and_solve(
                            y_mat,
                            self.backend.concat_cols((dcoupling_z, dcoupling_th)),
                            need_logdet=True,
                        )
                        if cond_y > self.condition_limit:
                            raise linalg.LinAlgError(f"Scattering Y condition {cond_y:g} exceeds limit.")
                        assert c_logdet_opt is not None
                        c_logdet = c_logdet_opt
                        if abs(c_logdet.imag) > 1.0e-7:
                            raise FloatingPointError(f"Scattering determinant has imaginary part {c_logdet}.")
                        c_dz = -pw * self.backend.trace(sol[:, :ny])
                        c_dth = -pw * self.backend.trace(sol[:, ny:])
                        if ch_name == "TM":
                            tm_cached = (c_logdet, c_dz, c_dth)

                    logdet_sum += c_logdet
                    dlogdet_dz_sum += c_dz
                    dlogdet_dth_sum += c_dth
                    ch_dz[ch_name] += c_dz
                    ch_dth[ch_name] += c_dth

            per_pair_out[pair_key] = (
                w_q * _assert_real(logdet_sum, "logdet") / (2.0 * math.pi),
                w_q * (-_assert_real(dlogdet_dz_sum, "dlogdet_dz") / (2.0 * math.pi)),
                w_q * (-_assert_real(dlogdet_dth_sum, "dlogdet_dth") / (2.0 * math.pi)),
                w_q * (-_assert_real(ch_dz["TM"], "TM_dz") / (2.0 * math.pi)),
                w_q * (-_assert_real(ch_dz["TE"], "TE_dz") / (2.0 * math.pi)),
                w_q * (-_assert_real(ch_dth["TM"], "TM_dth") / (2.0 * math.pi)),
                w_q * (-_assert_real(ch_dth["TE"], "TE_dth") / (2.0 * math.pi)),
            )

        return per_pair_out

    def evaluate_state(
        self,
        z_tip_um: float,
        theta_deg: float,
        *,
        max_steps: int = 0,
        min_clearance_um: float = 0.009,
    ) -> dict[str, Any]:
        """Evaluate (E_C, F_z, tau_theta) at rotor pose (z_tip_um, theta_deg)."""
        started = time.perf_counter()
        dz_um = float(z_tip_um) - self.z_ref_um
        theta_rad = math.radians(float(theta_deg))
        rotor = transform_rotor_panels(self.rotor_ref, dz_um=dz_um, theta_rad=theta_rad)
        min_sep_um = self._certify_rotor_pose_clearance(
            rotor, min_clearance_um=min_clearance_um, z_tip_um=float(z_tip_um), theta_deg=float(theta_deg)
        )

        total_nodes = int(self.kappas.size)
        evaluated = min(total_nodes, int(max_steps)) if int(max_steps) > 0 else total_nodes

        energy_dimless = 0.0
        fz_dimless = 0.0
        tau_dimless = 0.0
        fz_tm_dimless = 0.0
        fz_te_dimless = 0.0
        tau_tm_dimless = 0.0
        tau_te_dimless = 0.0
        eye_nr = self.backend.eye(self.nr_dof)
        pair_spec = [("primary", self.rotor_material_model, self.stator_material_model)]

        for q in range(evaluated):
            entry = (
                self.cache[q]
                if self.cache
                else self.build_single_frequency_factor(float(self.kappas[q]), float(self.weights[q]))
            )
            de, dfz, dtau, dfz_tm, dfz_te, dtau_tm, dtau_te = self._accumulate_single_state_at_frequency(
                rotor, entry, eye_nr, pair_spec
            )["primary"]
            energy_dimless += de
            fz_dimless += dfz
            tau_dimless += dtau
            fz_tm_dimless += dfz_tm
            fz_te_dimless += dfz_te
            tau_tm_dimless += dtau_tm
            tau_te_dimless += dtau_te

        energy_aJ = energy_dimless * DIMLESS_TO_PN_AJ
        f_z_pN = fz_dimless * DIMLESS_TO_PN_AJ
        tau_theta_pN_um = tau_dimless * DIMLESS_TO_PN_AJ

        return {
            "design_name": self.design_name,
            "material": self.material_name,
            "stator_material": self.stator_material_name,
            "z_tip_um": float(z_tip_um),
            "theta_deg": float(theta_deg),
            "theta_rad": theta_rad,
            "min_centroid_gap_um": min_sep_um,
            "energy_dimless": energy_dimless,
            "energy_aJ": energy_aJ,
            "energy_meV": energy_aJ * AJ_TO_MEV,
            "F_z_dimless": fz_dimless,
            "f_z_pN": f_z_pN,
            "f_z_TM_pN": fz_tm_dimless * DIMLESS_TO_PN_AJ,
            "f_z_TE_pN": fz_te_dimless * DIMLESS_TO_PN_AJ,
            "tau_theta_dimless": tau_dimless,
            "tau_theta_pN_um": tau_theta_pN_um,
            "tau_theta_TM_pN_um": tau_tm_dimless * DIMLESS_TO_PN_AJ,
            "tau_theta_TE_pN_um": tau_te_dimless * DIMLESS_TO_PN_AJ,
            "n_xi_evaluated": evaluated,
            "n_xi_total": total_nodes,
            "time_truncated": int(max_steps) > 0 and evaluated < total_nodes,
            "elapsed_seconds": time.perf_counter() - started,
        }

    def evaluate_states_batch(
        self,
        states: Sequence[tuple[float, float]],
        *,
        material_pairs: Sequence[tuple[str, str, str]] | None = None,
        max_steps: int = 0,
        min_clearance_um: float = 0.008,
    ) -> list[dict[str, Any]]:
        """Outer-loop-over-frequency batch evaluator with O(1)-in-n_xi VRAM footprint.

        ``material_pairs`` is an optional list of ``(pair_label, rotor_material, stator_material)``
        evaluated simultaneously from the same geometric BEM coupling operators.
        """
        if not states:
            return []
        started = time.perf_counter()
        if material_pairs is None:
            pair_models = [
                ("primary", self.rotor_material_model, self.stator_material_model)
            ]
        else:
            pair_models = [
                (label, EngineMaterialModel.from_name(rm), EngineMaterialModel.from_name(sm))
                for label, rm, sm in material_pairs
            ]

        rotors: list[EngineBodyPanels] = []
        clearances: list[float] = []
        for z_tip_um, theta_deg in states:
            dz_um = float(z_tip_um) - self.z_ref_um
            theta_rad = math.radians(float(theta_deg))
            r_pan = transform_rotor_panels(self.rotor_ref, dz_um=dz_um, theta_rad=theta_rad)
            sep = self._certify_rotor_pose_clearance(
                r_pan, min_clearance_um=min_clearance_um, z_tip_um=float(z_tip_um), theta_deg=float(theta_deg)
            )
            rotors.append(r_pan)
            clearances.append(sep)

        total_nodes = int(self.kappas.size)
        evaluated = min(total_nodes, int(max_steps)) if int(max_steps) > 0 else total_nodes
        eye_nr = self.backend.eye(self.nr_dof)

        accum: list[dict[str, np.ndarray]] = [
            {label: np.zeros(7, dtype=np.float64) for label, _, _ in pair_models}
            for _ in range(len(states))
        ]

        for q in range(evaluated):
            entry = (
                self.cache[q]
                if self.cache
                else self.build_single_frequency_factor(float(self.kappas[q]), float(self.weights[q]))
            )
            for idx, r_pan in enumerate(rotors):
                contrib = self._accumulate_single_state_at_frequency(r_pan, entry, eye_nr, pair_models)
                for label, vals in contrib.items():
                    accum[idx][label] += np.asarray(vals, dtype=np.float64)
            if not self.cache and self.backend.torch is not None:
                del entry
                self.backend.torch.cuda.empty_cache()

        elapsed_per_state = (time.perf_counter() - started) / max(1, len(states))
        results: list[dict[str, Any]] = []
        for idx, (z_tip_um, theta_deg) in enumerate(states):
            primary_label = pair_models[0][0]
            v = accum[idx][primary_label]
            rec: dict[str, Any] = {
                "design_name": self.design_name,
                "material": pair_models[0][1].name,
                "stator_material": pair_models[0][2].name,
                "z_tip_um": float(z_tip_um),
                "theta_deg": float(theta_deg),
                "theta_rad": math.radians(float(theta_deg)),
                "min_centroid_gap_um": clearances[idx],
                "energy_dimless": float(v[0]),
                "energy_aJ": float(v[0] * DIMLESS_TO_PN_AJ),
                "energy_meV": float(v[0] * DIMLESS_TO_PN_AJ * AJ_TO_MEV),
                "F_z_dimless": float(v[1]),
                "f_z_pN": float(v[1] * DIMLESS_TO_PN_AJ),
                "f_z_TM_pN": float(v[3] * DIMLESS_TO_PN_AJ),
                "f_z_TE_pN": float(v[4] * DIMLESS_TO_PN_AJ),
                "tau_theta_dimless": float(v[2]),
                "tau_theta_pN_um": float(v[2] * DIMLESS_TO_PN_AJ),
                "tau_theta_TM_pN_um": float(v[5] * DIMLESS_TO_PN_AJ),
                "tau_theta_TE_pN_um": float(v[6] * DIMLESS_TO_PN_AJ),
                "n_xi_evaluated": evaluated,
                "n_xi_total": total_nodes,
                "time_truncated": int(max_steps) > 0 and evaluated < total_nodes,
                "elapsed_seconds": elapsed_per_state,
            }
            if material_pairs is not None:
                rec["material_pairs"] = {
                    label: {
                        "rotor_material": rm.name,
                        "stator_material": sm.name,
                        "energy_aJ": float(accum[idx][label][0] * DIMLESS_TO_PN_AJ),
                        "f_z_pN": float(accum[idx][label][1] * DIMLESS_TO_PN_AJ),
                        "tau_theta_pN_um": float(accum[idx][label][2] * DIMLESS_TO_PN_AJ),
                        "f_z_TM_pN": float(accum[idx][label][3] * DIMLESS_TO_PN_AJ),
                        "f_z_TE_pN": float(accum[idx][label][4] * DIMLESS_TO_PN_AJ),
                        "tau_theta_TM_pN_um": float(accum[idx][label][5] * DIMLESS_TO_PN_AJ),
                        "tau_theta_TE_pN_um": float(accum[idx][label][6] * DIMLESS_TO_PN_AJ),
                    }
                    for label, rm, sm in pair_models
                }
            results.append(rec)
        return results


def _euler_xyz_rotation(rx_rad: float, ry_rad: float, rz_rad: float) -> np.ndarray:
    """Construct R_x(rx) @ R_y(ry) @ R_z(rz) in SO(3)."""
    cx, sx = math.cos(rx_rad), math.sin(rx_rad)
    cy, sy = math.cos(ry_rad), math.sin(ry_rad)
    cz, sz = math.cos(rz_rad), math.sin(rz_rad)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float64)
    ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float64)
    rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return rx @ ry @ rz


class Full4Sector6DofBemEvaluator:
    """Exact non-Bloch 4-sector 3D BEM evaluator for 6-DOF lateral/tilt pull-in stability.

    Lateral (dx, dy) and tilt (rx, ry) displacements break C_4 symmetry across the four
    sectors in the cross-body coupling G_rs^full, while the body-frame self-interaction
    operators M_rr^full and M_ss^full remain rigidly invariant and block-circulant.
    We invert M_rr^full and M_ss^full to machine precision via the unitary 4-point
    Bloch-DFT and evaluate the exact full-rotor scattering determinant log det(I_{4*nr} - p*X*Z).
    """

    def __init__(self, base_model: PreparedEngineBemModel) -> None:
        self.base = base_model
        self.stator_sectors: tuple[EngineBodyPanels, ...] = tuple(
            transform_panels_rigid_3d(
                self.base.stator_ref,
                rmat=_rotation(sec),
                shift_um=np.zeros(3, dtype=np.float64),
            )
            for sec in range(4)
        )
        # Pivot z_center of the rotor teeth in reference pose for pure tilt about rotor COM
        z_all = self.base.rotor_ref.centroids[:, 2]
        self.z_com_ref_um = 0.5 * float(np.min(z_all) + np.max(z_all))

    def _bloch_circulant_solve(
        self,
        lu_modes: tuple[tuple[Any, Any], ...],
        rhs_blocks: list[Any],
    ) -> list[Any]:
        """Solve M^full * X = Y for 4-block row-partitioned Y using unitary 4-point Bloch-DFT."""
        phases = self.base.phases  # phases[m, b] = exp(+2j * pi * m * b / 4)
        # 1. Y_hat[m] = 0.5 * sum_b conj(phases[m, b]) * Y[b]
        y_hat: list[Any] = []
        for m in range(4):
            acc = 0.5 * complex(np.conj(phases[m, 0])) * rhs_blocks[0]
            for b in range(1, 4):
                acc = acc + 0.5 * complex(np.conj(phases[m, b])) * rhs_blocks[b]
            y_hat.append(acc)

        # 2. X_hat[m] = M_hat[m]^{-1} Y_hat[m]
        x_hat = [self.base._solve_self_operator(lu_modes[m], y_hat[m]) for m in range(4)]

        # 3. X[a] = 0.5 * sum_m phases[m, a] * X_hat[m]
        x_blocks: list[Any] = []
        for a in range(4):
            acc_x = 0.5 * complex(phases[0, a]) * x_hat[0]
            for m in range(1, 4):
                acc_x = acc_x + 0.5 * complex(phases[m, a]) * x_hat[m]
            x_blocks.append(acc_x)
        return x_blocks

    def _rotor_sectors_at_6dof(
        self,
        *,
        dx_um: float,
        dy_um: float,
        z_tip_um: float,
        rx_rad: float,
        ry_rad: float,
        theta_deg: float,
        min_clearance_um: float = 0.005,
    ) -> tuple[tuple[EngineBodyPanels, ...], float]:
        rz_rad = math.radians(float(theta_deg))
        r_tilt_spin = _euler_xyz_rotation(rx_rad, ry_rad, rz_rad)
        dz_um = float(z_tip_um) - self.base.z_ref_um
        pivot = np.array([0.0, 0.0, self.z_com_ref_um], dtype=np.float64)
        shift_global = np.array([float(dx_um), float(dy_um), dz_um], dtype=np.float64)

        # x' = R_tilt_spin @ (R_sec @ x_ref - pivot) + pivot + shift_global
        #    = (R_tilt_spin @ R_sec) @ x_ref + (pivot - R_tilt_spin @ pivot + shift_global)
        eff_shift = pivot - (r_tilt_spin @ pivot) + shift_global
        rotor_secs: list[EngineBodyPanels] = []
        for sec in range(4):
            rmat_sec = r_tilt_spin @ _rotation(sec)
            rotor_secs.append(
                transform_panels_rigid_3d(self.base.rotor_ref, rmat=rmat_sec, shift_um=eff_shift)
            )

        # Certify full 4x4 sector clearance
        r_pts = np.concatenate(
            [np.concatenate([r.centroids, r.quad_points.reshape(-1, 3)], axis=0) for r in rotor_secs],
            axis=0,
        )
        s_pts = np.concatenate(
            [np.concatenate([s.centroids, s.quad_points.reshape(-1, 3)], axis=0) for s in self.stator_sectors],
            axis=0,
        )
        if self.base.backend.torch is not None:
            tm = self.base.backend.torch
            rg = tm.as_tensor(r_pts, dtype=tm.float64, device="cuda")
            sg = tm.as_tensor(s_pts, dtype=tm.float64, device="cuda")
            min_sep = float(tm.min(tm.cdist(rg, sg)).item())
        else:
            min_sep = float(np.min(np.linalg.norm(r_pts[:, None, :] - s_pts[None, :, :], axis=2)))
        if not math.isfinite(min_sep) or min_sep < min_clearance_um:
            raise ValueError(
                f"6-DOF clearance violation: {min_sep * 1e3:.2f} nm < {min_clearance_um * 1e3:.2f} nm."
            )
        return tuple(rotor_secs), min_sep

    def evaluate_energy_poses_batch(
        self,
        poses: Sequence[dict[str, float]],
        *,
        max_steps: int = 0,
        min_clearance_um: float = 0.005,
    ) -> list[dict[str, float]]:
        """Evaluate exact 4-sector Casimir energy E_C across a batch of 6-DOF poses."""
        if not poses:
            return []
        rotor_pose_list: list[tuple[EngineBodyPanels, ...]] = []
        clearances: list[float] = []
        for p in poses:
            r_secs, sep = self._rotor_sectors_at_6dof(
                dx_um=float(p.get("dx_um", 0.0)),
                dy_um=float(p.get("dy_um", 0.0)),
                z_tip_um=float(p["z_tip_um"]),
                rx_rad=float(p.get("rx_rad", 0.0)),
                ry_rad=float(p.get("ry_rad", 0.0)),
                theta_deg=float(p["theta_deg"]),
                min_clearance_um=min_clearance_um,
            )
            rotor_pose_list.append(r_secs)
            clearances.append(sep)

        total_nodes = int(self.base.kappas.size)
        evaluated = min(total_nodes, int(max_steps)) if int(max_steps) > 0 else total_nodes
        nr4 = 4 * self.base.nr_dof
        eye_4nr = self.base.backend.eye(nr4)
        t_mod = self.base.backend.torch

        energies_dimless = np.zeros(len(poses), dtype=np.float64)

        for q in range(evaluated):
            entry = (
                self.base.cache[q]
                if self.base.cache
                else self.base.build_single_frequency_factor(
                    float(self.base.kappas[q]), float(self.base.weights[q])
                )
            )
            pw_tm = entry.tm_product
            pw_te = entry.te_product

            for p_idx, r_secs in enumerate(rotor_pose_list):
                # Assemble 4x4 sector cross-blocks G_{a, b} (target rotor sector a, source stator sector b)
                g_rows: list[Any] = []
                for a in range(4):
                    row_blocks: list[Any] = []
                    for b in range(4):
                        g_ab, _, _ = _cross_blocks_with_z_and_theta(
                            r_secs[a],
                            self.stator_sectors[b],
                            0,
                            entry.kappa,
                            self.base.formulation,
                            sub_var_scale=self.base.sub_var_scale,
                            torch_mod=t_mod,
                            compute_derivatives=False,
                        )
                        if t_mod is not None:
                            row_blocks.append(g_ab.to(t_mod.complex128))
                        else:
                            row_blocks.append(self.base.backend.array(g_ab))
                    g_rows.append(self.base.backend.concat_cols(row_blocks))

                # Solve M_rr^full * X = G_rs^full (each block has nr_dof x 4*ns_dof)
                x_rows = self._bloch_circulant_solve(entry.rr_lu, g_rows)
                if t_mod is not None:
                    x_full = t_mod.cat(x_rows, dim=0)
                    g_full = t_mod.cat(g_rows, dim=0)
                    sr_full = g_full.mH
                    ns = self.base.ns_dof
                    sr_rows = [sr_full[b * ns : (b + 1) * ns, :] for b in range(4)]
                    z_rows = self._bloch_circulant_solve(entry.ss_lu, sr_rows)
                    z_full = t_mod.cat(z_rows, dim=0)
                else:
                    x_full = np.concatenate(x_rows, axis=0)
                    g_full = np.concatenate(g_rows, axis=0)
                    sr_full = g_full.conj().T
                    ns = self.base.ns_dof
                    sr_rows = [sr_full[b * ns : (b + 1) * ns, :] for b in range(4)]
                    z_rows = self._bloch_circulant_solve(entry.ss_lu, sr_rows)
                    z_full = np.concatenate(z_rows, axis=0)

                coupling_full = x_full @ z_full
                logdet_q = 0j
                tm_ld: complex | None = None
                for ch_name, pw in (("TM", pw_tm), ("TE", pw_te)):
                    if ch_name == "TE" and tm_ld is not None and math.isclose(pw_tm, pw_te, rel_tol=1.0e-14):
                        ld = tm_ld
                    else:
                        ld = self.base.backend.logdet(eye_4nr - pw * coupling_full)
                        if abs(ld.imag) > 1.0e-6:
                            raise FloatingPointError(f"6-DOF scattering logdet has imaginary part {ld}.")
                        if ch_name == "TM":
                            tm_ld = ld
                    logdet_q += ld

                energies_dimless[p_idx] += entry.weight * _assert_real(logdet_q, "logdet_6dof") / (2.0 * math.pi)

            if not self.base.cache and t_mod is not None:
                del entry
                t_mod.cuda.empty_cache()

        out: list[dict[str, float]] = []
        for idx, p in enumerate(poses):
            e_aj = float(energies_dimless[idx] * DIMLESS_TO_PN_AJ)
            out.append(
                {
                    **{k: float(v) for k, v in p.items()},
                    "energy_dimless": float(energies_dimless[idx]),
                    "energy_aJ": e_aj,
                    "min_clearance_um": clearances[idx],
                }
            )
        return out

    def evaluate_6dof_hessian(
        self,
        z_tip_um: float,
        theta_deg: float,
        *,
        step_xy_um: float = 0.002,
        step_tilt_rad: float = 0.002,
        max_steps: int = 0,
    ) -> dict[str, Any]:
        """Compute lateral (x, y) and tilt (rx, ry) forces/torques and destabilizing stiffnesses."""
        h_xy = float(step_xy_um)
        h_ang = float(step_tilt_rad)
        base_pose = {
            "dx_um": 0.0,
            "dy_um": 0.0,
            "z_tip_um": float(z_tip_um),
            "rx_rad": 0.0,
            "ry_rad": 0.0,
            "theta_deg": float(theta_deg),
        }
        stencil = [
            base_pose,
            {**base_pose, "dx_um": +h_xy},
            {**base_pose, "dx_um": -h_xy},
            {**base_pose, "dy_um": +h_xy},
            {**base_pose, "dy_um": -h_xy},
            {**base_pose, "rx_rad": +h_ang},
            {**base_pose, "rx_rad": -h_ang},
            {**base_pose, "ry_rad": +h_ang},
            {**base_pose, "ry_rad": -h_ang},
        ]
        vals = self.evaluate_energy_poses_batch(stencil, max_steps=max_steps)
        e0 = vals[0]["energy_aJ"]
        ex_p, ex_m = vals[1]["energy_aJ"], vals[2]["energy_aJ"]
        ey_p, ey_m = vals[3]["energy_aJ"], vals[4]["energy_aJ"]
        erx_p, erx_m = vals[5]["energy_aJ"], vals[6]["energy_aJ"]
        ery_p, ery_m = vals[7]["energy_aJ"], vals[8]["energy_aJ"]

        # E in aJ (1e-18 J), h_xy in um (1e-6 m):
        # F = -dE/dx in pN (1e-12 N = aJ/um)
        # d^2E/dx^2 in aJ / um^2 = 1e-18 / 1e-12 = 1e-6 N/m (uN/m)
        fx_pN = -(ex_p - ex_m) / (2.0 * h_xy)
        fy_pN = -(ey_p - ey_m) / (2.0 * h_xy)
        tau_x_pN_um = -(erx_p - erx_m) / (2.0 * h_ang)
        tau_y_pN_um = -(ery_p - ery_m) / (2.0 * h_ang)

        d2e_dx2_uN_m = (ex_p - 2.0 * e0 + ex_m) / (h_xy * h_xy)
        d2e_dy2_uN_m = (ey_p - 2.0 * e0 + ey_m) / (h_xy * h_xy)
        # d^2E/drx^2 in aJ / rad^2 = 1e-18 N*m/rad = pN*um/rad
        d2e_drx2_pN_um_rad = (erx_p - 2.0 * e0 + erx_m) / (h_ang * h_ang)
        d2e_dry2_pN_um_rad = (ery_p - 2.0 * e0 + ery_m) / (h_ang * h_ang)

        return {
            "design_name": self.base.design_name,
            "z_tip_um": float(z_tip_um),
            "theta_deg": float(theta_deg),
            "energy_0_aJ": e0,
            "min_clearance_0_um": vals[0]["min_clearance_um"],
            "f_x_pN": float(fx_pN),
            "f_y_pN": float(fy_pN),
            "tau_x_pN_um": float(tau_x_pN_um),
            "tau_y_pN_um": float(tau_y_pN_um),
            "d2E_dx2_uN_m": float(d2e_dx2_uN_m),
            "d2E_dy2_uN_m": float(d2e_dy2_uN_m),
            "k_destab_lat_max_uN_m": float(max(0.0, -d2e_dx2_uN_m, -d2e_dy2_uN_m)),
            "d2E_drx2_pN_um_rad": float(d2e_drx2_pN_um_rad),
            "d2E_dry2_pN_um_rad": float(d2e_dry2_pN_um_rad),
            "k_destab_tilt_max_pN_um_rad": float(max(0.0, -d2e_drx2_pN_um_rad, -d2e_dry2_pN_um_rad)),
        }


def verify_fresh_mesh_equivalence(
    design_name: str,
    z_tip_um: float,
    theta_deg: float,
    *,
    n_xi: int = 4,
) -> dict[str, float]:
    """Cross-check cached rigid-body model against rebuilding fresh ClutchSurfaceMesh."""
    model = PreparedEngineBemModel(
        design_name, n_r=1, n_phi_tooth=2, n_phi_bridge=3, n_z=1, n_xi=n_xi
    )
    fast = model.evaluate_state(z_tip_um, theta_deg)
    fresh_mesh = build_engine_surface_mesh(
        design_name,
        z_tip_um=z_tip_um,
        theta_deg=theta_deg,
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=3,
        n_z=1,
        min_clearance_um=0.008,
    )
    certify_minimum_clearance_um(fresh_mesh, min_allowed_um=0.008)
    rotor_fresh = build_engine_body_panels(fresh_mesh.rotor, quad_order=2)
    rotor_rigid = transform_rotor_panels(
        model.rotor_ref,
        dz_um=z_tip_um - model.z_ref_um,
        theta_rad=math.radians(theta_deg),
    )
    max_centroid_diff = float(np.max(np.abs(rotor_fresh.centroids - rotor_rigid.centroids)))
    max_normal_diff = float(np.max(np.abs(rotor_fresh.normals - rotor_rigid.normals)))
    max_tangent_diff = float(np.max(np.abs(rotor_fresh.tangents - rotor_rigid.tangents)))
    return {
        "max_centroid_diff_um": max_centroid_diff,
        "max_normal_diff": max_normal_diff,
        "max_tangent_diff": max_tangent_diff,
        "f_z_pN": float(fast["f_z_pN"]),
        "tau_theta_pN_um": float(fast["tau_theta_pN_um"]),
        "energy_aJ": float(fast["energy_aJ"]),
    }
