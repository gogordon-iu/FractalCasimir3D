#!/usr/bin/env python3
"""Exact 3D cyclic BEM solver for (E_C, F_z, tau_theta) engine cycle mapping.

Computes Casimir interaction energy E_C(z, theta), axial force F_z = -dE_C/dz,
and azimuthal torque tau_theta = -dE_C/dtheta simultaneously in a single LU
factorization pass per cyclic Bloch mode, exploiting rigid-body invariance of
the rotor and stator self-interaction operators across (z, theta).
"""

from __future__ import annotations

import dataclasses
import math
import time
from typing import Any, Literal

import numpy as np
from scipy import linalg

from execution.casimir_bem_solver import (
    BEM_TIER_STANDARD,
    BodyPanels,
    DEFAULT_CONDITION_LIMIT,
    DEFAULT_MAX_MEMORY_GIB,
    DenseBackend,
    Formulation,
    MaterialModel,
    _assert_real,
    _formulation_qualification,
    _panel_pair_samples,
    _quadrature,
    _rotation,
    _vector_dyadic_blocks,
    _yukawa_blocks,
)
from execution.materials_database_dispersive import (
    BOLTZMANN_K_EV_PER_K,
    HBAR_C_EV_UM,
    MEEP_FORCE_TO_SI,
)
from fractal_casimir_engine.geometries import (
    ENGINE_KAPPA_0_REF_UM_INV,
    ENGINE_K_EFF_REF_UM_INV,
    ENGINE_Z_TIP_MIN_UM,
    build_engine_surface_mesh,
    certify_minimum_clearance_um,
)

# 1 dimensionless energy unit = hbar*c / (1 um) = (MEEP_FORCE_TO_SI * 1e12) aJ
# 1 dimensionless force unit  = hbar*c / (1 um)^2 = (MEEP_FORCE_TO_SI * 1e12) pN
# 1 dimensionless torque unit = hbar*c / (1 um * rad) = (MEEP_FORCE_TO_SI * 1e12) pN*um
DIMLESS_TO_PN_AJ: float = float(MEEP_FORCE_TO_SI) * 1.0e12
AJ_TO_MEV: float = 1.0 / 0.1602176634e-3  # 1 aJ = 6.241509074 eV = 6241.509 meV


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
    rotor_ref: BodyPanels,
    *,
    dz_um: float,
    theta_rad: float,
) -> BodyPanels:
    """Apply exact rigid rotation theta_rad about +z and translation dz_um along +z."""
    c = math.cos(theta_rad)
    s = math.sin(theta_rad)
    rmat = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    shift = np.array([0.0, 0.0, dz_um], dtype=np.float64)
    centroids = rotor_ref.centroids @ rmat.T + shift
    normals = rotor_ref.normals @ rmat.T
    tangents = np.einsum("ab,imb->ima", rmat, rotor_ref.tangents)
    quad_points = np.einsum("ab,iqb->iqa", rmat, rotor_ref.quad_points) + shift
    return BodyPanels(
        centroids=centroids,
        normals=normals,
        areas=rotor_ref.areas,
        panel_types=rotor_ref.panel_types,
        tangents=tangents,
        quad_points=quad_points,
        quad_weights=rotor_ref.quad_weights,
    )


def _cross_blocks_with_z_and_theta(
    target: BodyPanels,
    source: BodyPanels,
    source_sector: int,
    kappa: float,
    formulation: Formulation,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute cross-body single-layer block G_rs and exact dG_rs/dz, dG_rs/dtheta_rad."""
    rotation = _rotation(source_sector)
    dtheta_q_target = _z_cross(target.quad_points)

    if formulation == "scalar_yukawa":
        shape = (target.count, source.count)
        single = np.zeros(shape, dtype=np.float64)
        dz = np.zeros(shape, dtype=np.float64)
        dtheta = np.zeros(shape, dtype=np.float64)
        for qt in range(4):
            d_qt = dtheta_q_target[:, qt, None, :]
            for qs in range(4):
                weight = float(target.quad_weights[qt] * source.quad_weights[qs])
                if weight == 0.0:
                    continue
                source_pts = (source.quad_points @ rotation.T)[None, :, qs, :]
                delta = target.quad_points[:, qt, None, :] - source_pts
                sub_var = (target.areas[:, None] + source.areas[None, :]) / (32.0 * math.pi)
                area_scale = np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :])
                eff_dist = np.sqrt(np.sum(delta**2, axis=2) + sub_var)
                kernel = np.exp(-kappa * eff_dist) / (4.0 * math.pi * eff_dist) * area_scale * weight
                rad_deriv = -kernel * (kappa + 1.0 / eff_dist)
                single += kernel
                dz += rad_deriv * delta[:, :, 2] / eff_dist
                delta_dot_dtheta = np.sum(delta * d_qt, axis=2)
                dtheta += rad_deriv * delta_dot_dtheta / eff_dist
        if not (np.isfinite(single).all() and np.isfinite(dz).all() and np.isfinite(dtheta).all()):
            raise FloatingPointError("Non-finite scalar cross-block or derivative.")
        return single, dz, dtheta

    if formulation != "vector_dyadic":
        raise ValueError(f"Unsupported formulation {formulation!r}.")

    source_tangents = np.einsum("ab,jmb->jma", rotation, source.tangents)
    dtheta_t_target = _z_cross(target.tangents)
    t_dot_t = np.einsum("ima,jna->ijmn", target.tangents, source_tangents)
    dt_dot_t_dtheta = np.einsum("ima,jna->ijmn", dtheta_t_target, source_tangents)

    shape4 = (target.count, source.count, 2, 2)
    single4 = np.zeros(shape4, dtype=np.float64)
    dz4 = np.zeros(shape4, dtype=np.float64)
    dtheta4 = np.zeros(shape4, dtype=np.float64)

    sub_var = (target.areas[:, None] + source.areas[None, :]) / (32.0 * math.pi)
    area_scale = np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :])
    source_points_rot = source.quad_points @ rotation.T

    u_z = target.tangents[:, :, 2][:, None, :, None]
    v_z = source_tangents[:, :, 2][None, :, None, :]

    for qt in range(4):
        d_qt = dtheta_q_target[:, qt, None, :]
        for qs in range(4):
            weight = float(target.quad_weights[qt] * source.quad_weights[qs])
            if weight == 0.0:
                continue
            delta = target.quad_points[:, qt, None, :] - source_points_rot[None, :, qs, :]
            eff_dist = np.sqrt(np.sum(delta**2, axis=2) + sub_var)
            kernel = np.exp(-kappa * eff_dist) / (4.0 * math.pi * eff_dist) * area_scale * weight
            rad_deriv = -kernel * (kappa + 1.0 / eff_dist)

            scaled_kernel = kernel[:, :, None, None]
            dr_dz = delta[:, :, 2] / eff_dist
            scaled_dz = (rad_deriv * dr_dz)[:, :, None, None]

            delta_dot_dtheta = np.sum(delta * d_qt, axis=2)
            dr_dtheta = delta_dot_dtheta / eff_dist
            scaled_dtheta = (rad_deriv * dr_dtheta)[:, :, None, None]

            x = kappa * eff_dist
            inv = 1.0 / (1.0 + x)
            denom = 1.0 - inv + inv**2
            c_dir = (1.0 + inv + inv**2) / denom
            dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denom**2

            u_r = np.einsum("ima,ija->ijm", target.tangents, delta)
            v_r = np.einsum("jna,ija->ijn", source_tangents, delta)
            r_inv2 = (1.0 / eff_dist**2)[:, :, None, None]
            z_comp = delta[:, :, 2][:, :, None, None]
            d_mat = u_r[:, :, :, None] * v_r[:, :, None, :] * r_inv2

            # Axial z derivative of Aniso
            dd_dz = (
                (u_z * v_r[:, :, None, :] + u_r[:, :, :, None] * v_z) * r_inv2
                - 2.0 * z_comp * d_mat * r_inv2
            )
            aniso = 0.5 * (t_dot_t - 0.5 * c_dir[:, :, None, None] * d_mat)
            daniso_dz = (
                -0.25 * (dc_dir_dx * kappa * dr_dz)[:, :, None, None] * d_mat
                - 0.25 * c_dir[:, :, None, None] * dd_dz
            )

            # Azimuthal theta derivative of Aniso (co-rotating rotor tangent frame)
            du_r_dtheta = (
                np.einsum("ima,ija->ijm", dtheta_t_target, delta)
                + np.einsum("ima,ija->ijm", target.tangents, np.broadcast_to(d_qt, delta.shape))
            )
            dv_r_dtheta = np.einsum(
                "jna,ija->ijn", source_tangents, np.broadcast_to(d_qt, delta.shape)
            )
            dd_dtheta = (
                (du_r_dtheta[:, :, :, None] * v_r[:, :, None, :] + u_r[:, :, :, None] * dv_r_dtheta[:, :, None, :])
                * r_inv2
                - 2.0 * delta_dot_dtheta[:, :, None, None] * d_mat * r_inv2
            )
            daniso_dtheta = 0.5 * dt_dot_t_dtheta - (
                0.25 * (dc_dir_dx * kappa * dr_dtheta)[:, :, None, None] * d_mat
                + 0.25 * c_dir[:, :, None, None] * dd_dtheta
            )

            single4 += scaled_kernel * aniso
            dz4 += scaled_dz * aniso + scaled_kernel * daniso_dz
            dtheta4 += scaled_dtheta * aniso + scaled_kernel * daniso_dtheta

    nr_dof = 2 * target.count
    ns_dof = 2 * source.count
    single_out = single4.transpose(0, 2, 1, 3).reshape(nr_dof, ns_dof)
    dz_out = dz4.transpose(0, 2, 1, 3).reshape(nr_dof, ns_dof)
    dtheta_out = dtheta4.transpose(0, 2, 1, 3).reshape(nr_dof, ns_dof)
    if not (np.isfinite(single_out).all() and np.isfinite(dz_out).all() and np.isfinite(dtheta_out).all()):
        raise FloatingPointError("Non-finite vector dyadic cross-block or derivative.")
    return single_out, dz_out, dtheta_out


@dataclasses.dataclass(frozen=True)
class FrequencySelfFactorCache:
    """Cached cyclic self-operator LU factorizations at one imaginary wavenumber."""

    kappa: float
    weight: float
    tm_weight: float
    te_weight: float
    rr_lu: tuple[tuple[Any, Any], ...]
    ss_lu: tuple[tuple[Any, Any], ...]
    max_cond_rr: float
    max_cond_ss: float


class PreparedEngineBemModel:
    """Pre-factored rigid-body 3D cyclic BEM engine evaluator for fast (z, theta) sweeps."""

    def __init__(
        self,
        design_name: str,
        *,
        material: str = "Gold",
        temperature_K: float = 0.0,
        formulation: Formulation = "vector_dyadic",
        n_r: int = BEM_TIER_STANDARD.n_r,
        n_phi_tooth: int = BEM_TIER_STANDARD.n_phi_tooth,
        n_phi_bridge: int = BEM_TIER_STANDARD.n_phi_bridge,
        n_z: int = BEM_TIER_STANDARD.n_z,
        n_xi: int = BEM_TIER_STANDARD.n_xi,
        kappa_0_um_inv: float = ENGINE_KAPPA_0_REF_UM_INV,
        k_eff_um_inv: float = ENGINE_K_EFF_REF_UM_INV,
        device: Literal["auto", "cpu", "cuda"] = "auto",
        condition_limit: float = DEFAULT_CONDITION_LIMIT,
        max_memory_gib: float = DEFAULT_MAX_MEMORY_GIB,
    ) -> None:
        self.design_name = design_name
        self.material_name = material
        self.temperature_K = float(temperature_K)
        self.formulation: Formulation = formulation
        self.qualification = _formulation_qualification(formulation)
        self.n_r = int(n_r)
        self.n_phi_tooth = int(n_phi_tooth)
        self.n_phi_bridge = int(n_phi_bridge)
        self.n_z = int(n_z)
        self.n_xi = int(n_xi)
        self.kappa_0_um_inv = float(kappa_0_um_inv)
        self.k_eff_um_inv = float(k_eff_um_inv)
        self.condition_limit = float(condition_limit)
        self.compute_device = detect_compute_device(device)
        self.backend = DenseBackend(self.compute_device)

        self.z_ref_um = ENGINE_Z_TIP_MIN_UM
        self.ref_mesh = build_engine_surface_mesh(
            design_name,
            z_tip_um=self.z_ref_um,
            theta_deg=0.0,
            material=material,
            temperature_K=temperature_K,
            n_r=n_r,
            n_phi_tooth=n_phi_tooth,
            n_phi_bridge=n_phi_bridge,
            n_z=n_z,
            min_clearance_um=0.008,
        )
        self.rotor_ref = self.ref_mesh.sector_arrays("rotor")
        self.stator_ref = self.ref_mesh.sector_arrays("stator")
        self.material = MaterialModel.from_parameters(self.ref_mesh.parameters)

        dofs = 2 if formulation == "vector_dyadic" else 1
        self.nr_dof = dofs * self.rotor_ref.count
        self.ns_dof = dofs * self.stator_ref.count
        estimated_bytes = 16 * (
            12 * self.nr_dof**2 + 10 * self.ns_dof**2 + 24 * self.nr_dof * self.ns_dof
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
                    "Estimated BEM working memory exceeds currently available CUDA memory. "
                    "Request --device cpu or reduce mesh resolution."
                )

        self.kappas, self.weights = self._build_quadrature()
        self.phases = np.exp(2j * math.pi * np.arange(4)[:, None] * np.arange(4)[None, :] / 4.0)
        self.cache: tuple[FrequencySelfFactorCache, ...] = self._precompute_self_factors()

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

    def _precompute_self_factors(self) -> tuple[FrequencySelfFactorCache, ...]:
        block_fn = _vector_dyadic_blocks if self.formulation == "vector_dyadic" else _yukawa_blocks
        caches: list[FrequencySelfFactorCache] = []
        for kappa, weight in zip(self.kappas, self.weights):
            k_val = float(kappa)
            tm, te, _ = self.material.channel_weights(k_val, k_eff=self.k_eff_um_inv)
            rr_modes = [np.zeros((self.nr_dof, self.nr_dof), dtype=np.complex128) for _ in range(4)]
            ss_modes = [np.zeros((self.ns_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]
            for sector in range(4):
                b_rr = block_fn(self.rotor_ref, self.rotor_ref, sector, k_val, same_body=True)
                b_ss = block_fn(self.stator_ref, self.stator_ref, sector, k_val, same_body=True)
                for mode in range(4):
                    ph = self.phases[mode, sector]
                    rr_modes[mode] += ph * b_rr.single_layer
                    ss_modes[mode] += ph * b_ss.single_layer

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

            caches.append(
                FrequencySelfFactorCache(
                    kappa=k_val,
                    weight=float(weight),
                    tm_weight=float(tm),
                    te_weight=float(te),
                    rr_lu=tuple(rr_lu_list),
                    ss_lu=tuple(ss_lu_list),
                    max_cond_rr=max_c_r,
                    max_cond_ss=max_c_s,
                )
            )
        return tuple(caches)

    def solver_metadata(self) -> dict[str, Any]:
        return {
            "solver": "BEM_EngineCycle_3D",
            "design_name": self.design_name,
            "formulation": self.formulation,
            "physics_qualification": self.qualification,
            "material": self.material_name,
            "temperature_K": self.temperature_K,
            "device": self.backend.device,
            "n_r": self.n_r,
            "n_phi_tooth": self.n_phi_tooth,
            "n_phi_bridge": self.n_phi_bridge,
            "n_phi_arc": max(self.n_phi_bridge * 3, 9),
            "n_z": self.n_z,
            "n_xi": self.n_xi,
            "n_panels_rotor": self.ref_mesh.n_panels_rotor,
            "n_panels_stator": self.ref_mesh.n_panels_stator,
            "n_panels_total": self.ref_mesh.n_panels_total,
            "kappa_0_um_inv": self.kappa_0_um_inv,
            "k_eff_um_inv": self.k_eff_um_inv,
            "dataset": "fractal_casimir_engine_cycle",
        }

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

        # Certify positive cross-body clearance across centroids AND quadrature points in all 4 sectors
        rotor_pts = np.concatenate([rotor.centroids, rotor.quad_points.reshape(-1, 3)], axis=0)
        stator_base = np.concatenate(
            [self.stator_ref.centroids, self.stator_ref.quad_points.reshape(-1, 3)], axis=0
        )
        min_sep_um = math.inf
        for sector in range(4):
            stator_pts = stator_base @ _rotation(sector).T
            diff = rotor_pts[:, None, :] - stator_pts[None, :, :]
            min_sep_um = min(min_sep_um, float(np.min(np.linalg.norm(diff, axis=2))))
        if not math.isfinite(min_sep_um) or min_sep_um < min_clearance_um:
            raise ValueError(
                f"Clearance violation at (z={z_tip_um:.4f} um, theta={theta_deg:.2f} deg): "
                f"min quadrature/centroid gap {min_sep_um * 1e3:.2f} nm < {min_clearance_um * 1e3:.2f} nm."
            )

        total_nodes = len(self.cache)
        evaluated = min(total_nodes, int(max_steps)) if int(max_steps) > 0 else total_nodes

        energy_dimless = 0.0
        fz_dimless = 0.0
        tau_dimless = 0.0
        fz_tm_dimless = 0.0
        fz_te_dimless = 0.0
        tau_tm_dimless = 0.0
        tau_te_dimless = 0.0
        eye_nr = self.backend.eye(self.nr_dof)

        for q in range(evaluated):
            entry = self.cache[q]
            rs_modes = [np.zeros((self.nr_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]
            dz_modes = [np.zeros((self.nr_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]
            dth_modes = [np.zeros((self.nr_dof, self.ns_dof), dtype=np.complex128) for _ in range(4)]

            for sector in range(4):
                g_sec, dz_sec, dth_sec = _cross_blocks_with_z_and_theta(
                    rotor, self.stator_ref, sector, entry.kappa, self.formulation
                )
                for mode in range(4):
                    ph = self.phases[mode, sector]
                    rs_modes[mode] += ph * g_sec
                    dz_modes[mode] += ph * dz_sec
                    dth_modes[mode] += ph * dth_sec

            dlogdet_dz_sum = 0j
            dlogdet_dth_sum = 0j
            logdet_sum = 0j
            ch_dz = {"TM": 0j, "TE": 0j}
            ch_dth = {"TM": 0j, "TE": 0j}

            for mode in range(4):
                g = self.backend.array(rs_modes[mode])
                dg_z = self.backend.array(dz_modes[mode])
                dg_th = self.backend.array(dth_modes[mode])

                # Reciprocity: G_sr(m) = G_rs(m)^H for every (z, theta)
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

                tm_cached: tuple[complex, complex, complex] | None = None
                for ch_name, w_ch in (("TM", entry.tm_weight), ("TE", entry.te_weight)):
                    pw = w_ch * w_ch
                    if (
                        ch_name == "TE"
                        and tm_cached is not None
                        and math.isclose(entry.tm_weight**2, entry.te_weight**2, rel_tol=1.0e-14)
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

            w_q = entry.weight
            energy_dimless += w_q * _assert_real(logdet_sum, "logdet") / (2.0 * math.pi)
            fz_dimless += w_q * (-_assert_real(dlogdet_dz_sum, "dlogdet_dz") / (2.0 * math.pi))
            tau_dimless += w_q * (-_assert_real(dlogdet_dth_sum, "dlogdet_dth") / (2.0 * math.pi))
            fz_tm_dimless += w_q * (-_assert_real(ch_dz["TM"], "TM_dz") / (2.0 * math.pi))
            fz_te_dimless += w_q * (-_assert_real(ch_dz["TE"], "TE_dz") / (2.0 * math.pi))
            tau_tm_dimless += w_q * (-_assert_real(ch_dth["TM"], "TM_dth") / (2.0 * math.pi))
            tau_te_dimless += w_q * (-_assert_real(ch_dth["TE"], "TE_dth") / (2.0 * math.pi))

        energy_aJ = energy_dimless * DIMLESS_TO_PN_AJ
        f_z_pN = fz_dimless * DIMLESS_TO_PN_AJ
        tau_theta_pN_um = tau_dimless * DIMLESS_TO_PN_AJ

        return {
            "design_name": self.design_name,
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
    rotor_fresh = fresh_mesh.sector_arrays("rotor")
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
