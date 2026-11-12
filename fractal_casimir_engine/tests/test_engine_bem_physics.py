#!/usr/bin/env python3
"""Physics and numerical verification suite for the Fractal Casimir Engine BEM."""

from __future__ import annotations

import math

import numpy as np
import pytest

from fractal_casimir_engine import ENGINE_DESIGN_NAMES
from fractal_casimir_engine.bem_cycle_solver import (
    PreparedEngineBemModel,
    verify_fresh_mesh_equivalence,
)
from fractal_casimir_engine.geometries import (
    ENGINE_Z_TIP_MAX_UM,
    ENGINE_Z_TIP_MID_UM,
    ENGINE_Z_TIP_MIN_UM,
    build_engine_surface_mesh,
)


@pytest.mark.parametrize("design_name", ENGINE_DESIGN_NAMES)
def test_collision_free_across_full_360_rotation(design_name: str) -> None:
    """Every design must maintain >= 10 nm vacuum clearance across full rotation & stroke."""
    for z_tip in (ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MID_UM, ENGINE_Z_TIP_MAX_UM):
        for theta_deg in (0.0, 2.0, 8.0, 22.0, 36.0, 41.5, 44.0, 54.0, 64.0, 78.0, 86.5, 89.0):
            mesh = build_engine_surface_mesh(
                design_name,
                z_tip_um=z_tip,
                theta_deg=theta_deg,
                n_r=1,
                n_phi_tooth=2,
                n_phi_bridge=2,
                n_z=1,
                min_clearance_um=0.010,
            )
            assert mesh.parameters["certified_min_clearance_um"] >= 0.010


@pytest.mark.parametrize("formulation", ("vector_dyadic", "scalar_yukawa"))
def test_analytic_force_and_torque_match_energy_finite_differences(
    formulation: str,
) -> None:
    """Analytic trace F_z = -dE/dz and tau_theta = -dE/dtheta must match centered FD."""
    model = PreparedEngineBemModel(
        "Config_B_Manhattan_Vernier",
        formulation=formulation,  # type: ignore[arg-type]
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=6,
    )
    z0 = -0.086
    th0_deg = 24.0
    center = model.evaluate_state(z0, th0_deg)

    dz = 1.0e-5  # um
    ez_plus = model.evaluate_state(z0 + dz, th0_deg)["energy_aJ"]
    ez_minus = model.evaluate_state(z0 - dz, th0_deg)["energy_aJ"]
    fz_fd = -(ez_plus - ez_minus) / (2.0 * dz)

    dth_deg = 1.0e-3
    dth_rad = math.radians(dth_deg)
    eth_plus = model.evaluate_state(z0, th0_deg + dth_deg)["energy_aJ"]
    eth_minus = model.evaluate_state(z0, th0_deg - dth_deg)["energy_aJ"]
    tau_fd = -(eth_plus - eth_minus) / (2.0 * dth_rad)

    assert math.isclose(center["f_z_pN"], fz_fd, rel_tol=2.0e-5, abs_tol=1.0e-6)
    assert math.isclose(center["tau_theta_pN_um"], tau_fd, rel_tol=2.0e-5, abs_tol=1.0e-6)


def test_rigid_transform_matches_fresh_mesh_construction() -> None:
    """Cached rigid-body panel transform must match fresh mesh construction to machine eps."""
    for design in ("Config_B_Manhattan_Vernier", "Config_C_Helical_Turbine", "Config_D_DualStator_PushPull"):
        check = verify_fresh_mesh_equivalence(design, -0.082, 57.5, n_xi=4)
        assert check["max_centroid_diff_um"] < 1.0e-13
        assert check["max_normal_diff"] < 1.0e-13
        assert check["max_tangent_diff"] < 1.0e-13


def test_symmetric_baseline_vanishing_torque_at_symmetry_centers() -> None:
    """Symmetric baseline must have tau_theta = 0 at slot center (21 deg) and pad center (66 deg)."""
    model = PreparedEngineBemModel(
        "Sym_Baseline_CantorN2",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=6,
    )
    slot_center = model.evaluate_state(-0.095, 21.0)
    pad_center = model.evaluate_state(-0.095, 66.0)
    assert slot_center["f_z_pN"] > 0.0  # Repulsive slot lift
    assert pad_center["f_z_pN"] < 0.0   # Attractive pad pull
    assert abs(slot_center["tau_theta_pN_um"]) < 1.0e-10
    assert abs(pad_center["tau_theta_pN_um"]) < 1.0e-10


def test_chiral_configs_achieve_codirectional_torque_in_both_strokes() -> None:
    """Configs B, C, and D must produce (F_z > 0, tau > 0) in Stroke I and (F_z < 0, tau > 0) in Stroke III."""
    for design in ("Config_B_Manhattan_Vernier", "Config_C_Helical_Turbine", "Config_D_DualStator_PushPull"):
        model = PreparedEngineBemModel(
            design,
            n_r=1,
            n_phi_tooth=2,
            n_phi_bridge=2,
            n_z=1,
            n_xi=8,
        )
        rep_stroke = model.evaluate_state(-0.092, 22.0)
        attr_stroke = model.evaluate_state(-0.084, 64.0)
        assert rep_stroke["f_z_pN"] > 0.0, f"{design} failed repulsive F_z > 0 in Stroke I: {rep_stroke}"
        assert rep_stroke["tau_theta_pN_um"] > 0.0, f"{design} failed forward tau > 0 in Stroke I: {rep_stroke}"
        assert attr_stroke["f_z_pN"] < 0.0, f"{design} failed attractive F_z < 0 in Stroke III: {attr_stroke}"
        assert attr_stroke["tau_theta_pN_um"] > 0.0, f"{design} failed forward tau > 0 in Stroke III: {attr_stroke}"


def test_periodic_hermite_potential_exact_nodal_and_loop_closure() -> None:
    """PeriodicHermitePotential2D must match BEM grid nodes to 1e-14 and satisfy oint dW = 0."""
    import math
    import numpy as np
    from fractal_casimir_engine.run_engine_cycle_mapping import PeriodicHermitePotential2D

    z_grid = np.linspace(-0.100, -0.068, 6)
    th_grid = np.linspace(0.0, 90.0, 18, endpoint=False)
    zz, tt = np.meshgrid(z_grid, np.deg2rad(th_grid), indexing="ij")
    e_grid = -0.35 + 0.12 * np.cos(4.0 * tt) * np.exp(-(zz + 0.100) / 0.020)
    fz_grid = -(-0.12 * np.cos(4.0 * tt) * (-1.0 / 0.020) * np.exp(-(zz + 0.100) / 0.020))
    tau_grid = -(-0.48 * np.sin(4.0 * tt) * np.exp(-(zz + 0.100) / 0.020))

    pot = PeriodicHermitePotential2D(z_grid, th_grid, e_grid, fz_grid, tau_grid)
    for iz in range(len(z_grid) - 1):
        for ith in range(len(th_grid)):
            ev, fv, tv = pot.eval_e_fz_tau(float(z_grid[iz]), float(th_grid[ith]))
            assert abs(ev - e_grid[iz, ith]) < 1.0e-14
            assert abs(fv - fz_grid[iz, ith]) < 1.0e-12
            assert abs(tv - tau_grid[iz, ith]) < 1.0e-12

    ths = np.linspace(0.0, 90.0, 721)
    dth_r = math.radians(ths[1] - ths[0])
    loop_work = 0.0
    for k in range(len(ths) - 1):
        tm = 0.5 * (ths[k] + ths[k + 1])
        zm = -0.084 + 0.012 * math.sin(math.radians(4.0 * tm))
        dz = 0.012 * math.cos(math.radians(4.0 * tm)) * 4.0 * dth_r
        _, fz, tau = pot.eval_e_fz_tau(zm, tm)
        loop_work += fz * dz + tau * dth_r
    assert abs(loop_work) < 5.0e-5

