#!/usr/bin/env python3
"""Unit tests for the 4 Ultra-Fine verification & de-artifacting suites (UF1-UF4)."""

from __future__ import annotations

import math

from pathlib import Path

import numpy as np
import pytest

from fractal_casimir_engine.aggregate_ultrafine_campaigns import (
    REQUIRED_SUITES,
    aggregate_campaigns,
)
from fractal_casimir_engine.bem_cycle_solver import (
    EngineMaterialModel,
    Full4Sector6DofBemEvaluator,
    PreparedEngineBemModel,
    build_engine_body_panels,
)
from fractal_casimir_engine.geometries import (
    SECTOR_DEG,
    build_engine_surface_mesh,
)
from fractal_casimir_engine.run_ultrafine_active_switching import (
    simulate_two_state_thermodynamic_engine,
)
from fractal_casimir_engine.run_ultrafine_meep_verification import (
    MEEP_BENCHMARK_TASKS,
    build_and_certify_stress_faces,
)


def test_lazy_batch_and_multi_material_match_single_state_bem() -> None:
    """evaluate_states_batch(lazy_self_cache=True) must match single-state BEM to machine precision."""
    states = [(-0.092, 22.0), (-0.084, 64.0)]
    eager = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        material="Gold",
        stator_material="Gold",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=2,
        quad_order=2,
        device="cpu",
        lazy_self_cache=False,
    )
    lazy = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        material="Gold",
        stator_material="VO2_Metallic",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=2,
        quad_order=2,
        device="cpu",
        lazy_self_cache=True,
    )
    vo2_off_ref = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        material="Gold",
        stator_material="VO2_Insulating",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=2,
        quad_order=2,
        device="cpu",
        lazy_self_cache=False,
    )

    batch = lazy.evaluate_states_batch(
        states,
        material_pairs=(
            ("Au_Au", "Gold", "Gold"),
            ("Au_VO2_OFF", "Gold", "VO2_Insulating"),
        ),
    )
    for idx, (z_u, th_d) in enumerate(states):
        ref_au = eager.evaluate_state(z_u, th_d)
        ref_off = vo2_off_ref.evaluate_state(z_u, th_d)
        got_au = batch[idx]["material_pairs"]["Au_Au"]
        got_off = batch[idx]["material_pairs"]["Au_VO2_OFF"]
        assert abs(got_au["energy_aJ"] - ref_au["energy_aJ"]) < 1.0e-13
        assert abs(got_au["f_z_pN"] - ref_au["f_z_pN"]) < 1.0e-12
        assert abs(got_au["tau_theta_pN_um"] - ref_au["tau_theta_pN_um"]) < 1.0e-13
        assert abs(got_off["energy_aJ"] - ref_off["energy_aJ"]) < 1.0e-13
        assert abs(got_off["f_z_pN"] - ref_off["f_z_pN"]) < 1.0e-12
        assert abs(got_off["tau_theta_pN_um"] - ref_off["tau_theta_pN_um"]) < 1.0e-13


def test_higher_order_subpanel_quadrature_consistency() -> None:
    """3x3 Gauss-Legendre sub-panel quadrature must preserve co-directional signs and agree closely with 2x2."""
    m_q2 = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=2,
        quad_order=2,
        device="cpu",
    )
    m_q3 = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=2,
        quad_order=3,
        device="cpu",
    )
    assert m_q3.rotor_ref.quad_points.shape[1] == 9
    s_q2 = m_q2.evaluate_state(-0.092, 22.0)
    s_q3 = m_q3.evaluate_state(-0.092, 22.0)
    assert s_q3["f_z_pN"] > 0.0
    assert s_q3["tau_theta_pN_um"] > 0.0
    # Sub-panel refinement from 4 to 9 Gauss points on identical panels shifts smooth observables by only a few %
    assert abs(s_q3["f_z_pN"] - s_q2["f_z_pN"]) / abs(s_q2["f_z_pN"]) < 0.10


def test_full_4sector_6dof_matches_bloch_and_obeys_c4_symmetry() -> None:
    """Full 4-sector non-Bloch 6-DOF BEM must match cyclic Bloch at nominal pose and satisfy C4 isotropy."""
    base = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=2,
        n_z=1,
        n_xi=2,
        quad_order=2,
        device="cpu",
        lazy_self_cache=False,
    )
    ref_bloch = base.evaluate_state(-0.092, 22.0)
    ev6 = Full4Sector6DofBemEvaluator(base)
    hess = ev6.evaluate_6dof_hessian(-0.092, 22.0, step_xy_um=0.002, step_tilt_rad=0.002)

    assert abs(hess["energy_0_aJ"] - ref_bloch["energy_aJ"]) < 1.0e-12
    assert abs(hess["f_x_pN"]) < 1.0e-10
    assert abs(hess["f_y_pN"]) < 1.0e-10
    assert abs(hess["tau_x_pN_um"]) < 1.0e-10
    assert abs(hess["tau_y_pN_um"]) < 1.0e-10
    # Rank-2 symmetric Hessian under C4 symmetry must be isotropic: d2E/dx^2 == d2E/dy^2, d2E/drx^2 == d2E/dry^2
    assert math.isclose(hess["d2E_dx2_uN_m"], hess["d2E_dy2_uN_m"], rel_tol=1.0e-9, abs_tol=1.0e-9)
    assert math.isclose(hess["d2E_drx2_pN_um_rad"], hess["d2E_dry2_pN_um_rad"], rel_tol=1.0e-9, abs_tol=1.0e-9)


def test_ebl_corner_rounding_valid_geometry_and_clearance() -> None:
    """EBL corner filleting (r_edge_nm > 0) must yield valid orthonormal frames and non-decreasing clearance."""
    sharp = build_engine_surface_mesh(
        "Config_C_Helical_Turbine",
        z_tip_um=-0.092,
        theta_deg=22.0,
        n_r=2,
        n_phi_tooth=3,
        n_phi_bridge=3,
        n_z=2,
        r_edge_nm=0.0,
        min_clearance_um=0.008,
    )
    rounded = build_engine_surface_mesh(
        "Config_C_Helical_Turbine",
        z_tip_um=-0.092,
        theta_deg=22.0,
        n_r=2,
        n_phi_tooth=3,
        n_phi_bridge=3,
        n_z=2,
        r_edge_nm=12.0,
        min_clearance_um=0.008,
    )
    assert rounded.parameters["certified_min_clearance_um"] >= sharp.parameters["certified_min_clearance_um"] - 1.0e-4
    body = build_engine_body_panels(rounded.rotor, quad_order=3)
    for idx in range(min(25, body.count)):
        assert float(body.areas[idx]) > 0.0
        n_hat = body.normals[idx]
        u_hat, v_hat = body.tangents[idx, 0], body.tangents[idx, 1]
        assert math.isclose(float(np.linalg.norm(n_hat)), 1.0, rel_tol=1.0e-12)
        assert abs(float(np.dot(u_hat, n_hat))) < 1.0e-11
        assert abs(float(np.dot(v_hat, n_hat))) < 1.0e-11
        assert abs(float(np.dot(u_hat, v_hat))) < 1.0e-11


def test_dispersive_materials_and_first_law_switching_conservation() -> None:
    """Dispersive material pairs must obey Kramers-Kronig ordering and First-Law energy balance."""
    vo2_m = EngineMaterialModel.from_name("VO2_Metallic")
    vo2_i = EngineMaterialModel.from_name("VO2_Insulating")
    si_on = EngineMaterialModel.from_name("Silicon_PhotoDoped")
    si_off = EngineMaterialModel.from_name("Silicon_Intrinsic")

    for kappa in (0.2, 1.0, 5.0, 12.0):
        e_vm = vo2_m.epsilon(kappa)
        e_vi = vo2_i.epsilon(kappa)
        e_son = si_on.epsilon(kappa)
        e_soff = si_off.epsilon(kappa)
        assert e_vm is not None and e_vi is not None and e_vm > e_vi > 1.0
        assert e_son is not None and e_soff is not None and e_son > e_soff > 1.0

    # Construct analytic periodic two-state chiral test potential to verify First-Law integrator
    z_grid = np.linspace(-0.100, -0.068, 7)
    th_grid = np.linspace(0.0, SECTOR_DEG, 36, endpoint=False)
    zz, tt = np.meshgrid(z_grid, np.deg2rad(th_grid), indexing="ij")
    # Asymmetric sawtooth-like 4-fold periodic potential deeper in ON than OFF
    phi4 = 4.0 * tt
    shape = -(np.cos(phi4 - 1.1) + 0.35 * np.sin(2.0 * (phi4 - 1.1)))
    dshape_dth = -(-4.0 * np.sin(phi4 - 1.1) + 2.8 * np.cos(2.0 * (phi4 - 1.1)))
    decay = np.exp(-(zz + 0.100) / 0.025)
    ddecay_dz = -(1.0 / 0.025) * decay

    def make_surf(amp: float) -> dict[str, np.ndarray]:
        e = amp * shape * decay
        fz = -(amp * shape * ddecay_dz)
        tau = -(amp * dshape_dth * decay)
        return {"energy_grid_aJ": e, "fz_grid_pN": fz, "tau_grid_pN_um": tau}

    res = simulate_two_state_thermodynamic_engine(
        "Config_D_DualStator_PushPull",
        z_grid,
        th_grid,
        make_surf(0.18),
        make_surf(0.11),
        n_steps=4000,
        dt_us=0.02,
    )
    assert res["first_law_residual_aJ"] < 1.0e-3
    if res["net_em_work_into_rotor_aJ"] > 0.0:
        assert math.isclose(
            res["net_em_work_into_rotor_aJ"],
            res["w_mech_balance_check_aJ"],
            rel_tol=1.0e-2,
            abs_tol=1.0e-3,
        )


@pytest.mark.parametrize("task_spec", MEEP_BENCHMARK_TASKS)
def test_all_meep_benchmark_stress_boxes_certified_vacuum_isolated(
    task_spec: dict[str, object],
) -> None:
    """All 8 canonical Meep FDTD benchmark tasks must certify >= 4.5 nm stress-box vacuum clearance."""
    design_name = str(task_spec["design_name"])
    z_tip_um = float(task_spec["z_tip_um"])  # type: ignore[arg-type]
    theta_deg = float(task_spec["theta_deg"])  # type: ignore[arg-type]
    faces, meta = build_and_certify_stress_faces(design_name, z_tip_um, theta_deg)
    assert len(faces) == 18  # 3 Cantor teeth * 6 stress-box faces
    assert meta["min_certified_clearance_nm"] >= 4.5


def test_pec_te_sign_and_end_to_end_provenance_aggregation(tmp_path: Path) -> None:
    """Verify PEC TE channel sign (-1) and end-to-end save_plot_provenance + aggregate_campaigns."""
    import json
    from utils.metrics_logger import (
        export_macros,
        log_metric,
        log_step,
        save_plot_provenance,
        set_solver_provenance,
    )

    pec = EngineMaterialModel.from_name("PEC")
    vo2_i = EngineMaterialModel.from_name("VO2_Insulating")
    tm_p, te_p, _ = pec.channel_weights(2.0, k_eff=40.0)
    tm_v, te_v, _ = vo2_i.channel_weights(2.0, k_eff=40.0)
    assert tm_p == 1.0 and te_p == -1.0
    assert tm_p * tm_v > 0.0 and te_p * te_v > 0.0

    uf_dir = tmp_path / "results" / "ultrafine"
    fig_dir = tmp_path / "figures"
    paper_dir = tmp_path / "paper"
    (paper_dir / "figures").mkdir(parents=True, exist_ok=True)
    uf_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    base_metrics = tmp_path / "results" / "provenance_metrics.json"
    set_solver_provenance("BEM_Baseline", {"n_xi": 12}, metrics_path=str(base_metrics))
    log_metric("baseline_metric", 1.25, metrics_path=str(base_metrics))
    export_macros(metrics_path=str(base_metrics), output_path=str(paper_dir / "macros_results.tex"))

    for idx, (suite_id, rep_name, met_name, mac_name, fig_stem) in enumerate(REQUIRED_SUITES, start=1):
        rep_path = uf_dir / rep_name
        rep_path.write_text(
            json.dumps({"suite": suite_id, "status": "completed", "time_truncated": False}),
            encoding="utf-8",
        )
        met_path = uf_dir / met_name
        mac_path = uf_dir / mac_name
        set_solver_provenance(f"Solver_{suite_id}", {"suite_idx": idx}, metrics_path=str(met_path))
        log_step(f"step_{suite_id}", {"ok": 1}, metrics_path=str(met_path))
        log_metric(
            f"engine_uf_test_{idx}",
            float(idx) * 10.0,
            step_id=f"step_{suite_id}",
            metrics_path=str(met_path),
        )
        export_macros(metrics_path=str(met_path), output_path=str(mac_path))

        for ext in (".png", ".pdf"):
            fp = fig_dir / f"{fig_stem}{ext}"
            fp.write_bytes(b"test_figure_payload")
            save_plot_provenance(
                str(fp),
                str(rep_path),
                columns_used=["status"],
                solver_name=f"Solver_{suite_id}",
                solver_parameters={"suite_idx": idx},
            )

    (paper_dir / "fractal_casimir_engine.tex").write_text(
        r"\documentclass{article}" "\n"
        r"\input{macros_results.tex}" "\n"
        r"\begin{document}" "\n"
        r"Baseline \BaselineMetric, UF1 \EngineUfTestOne, UF4 \EngineUfTestFour." "\n"
        r"\includegraphics{figures/fig_uf1_mesh_convergence.pdf}" "\n"
        r"\end{document}" "\n",
        encoding="utf-8",
    )

    cs = aggregate_campaigns(
        uf_results_dir=uf_dir,
        engine_figures_dir=fig_dir,
        base_metrics_path=base_metrics,
        paper_dir=paper_dir,
        cluster_safe=True,
    )
    assert cs["ready"] is True and cs["cluster_safe"] is True
    assert not (paper_dir / "figures" / "fig_uf1_mesh_convergence.pdf").exists()

    full = aggregate_campaigns(
        uf_results_dir=uf_dir,
        engine_figures_dir=fig_dir,
        base_metrics_path=base_metrics,
        paper_dir=paper_dir,
        cluster_safe=False,
    )
    assert full["ready"] is True and full["ledger"]["audit_status"] == "PASS"
    assert (paper_dir / "figures" / "fig_uf1_mesh_convergence.pdf.provenance.json").is_file()

