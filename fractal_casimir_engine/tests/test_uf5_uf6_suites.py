#!/usr/bin/env python3
"""Unit & integration tests for Suite 5 (eng_uf5) and Suite 6 (eng_uf6)."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pytest

from fractal_casimir_engine import ENGINE_DESIGN_NAMES
from fractal_casimir_engine.geometries import (
    ENGINE_Z_TIP_MAX_UM,
    ENGINE_Z_TIP_MIN_UM,
    HIERARCHY_NAMES,
    SECTOR_DEG,
    build_engine_surface_mesh,
    build_hierarchy_tracks,
    canonical_cantor_n2_tracks,
)
from fractal_casimir_engine.run_engine_cycle_mapping import PeriodicHermitePotential2D
from fractal_casimir_engine.run_ultrafine_langevin_and_tolerances import (
    eval_hermite_batch,
    simulate_baoab_langevin_ensemble,
)


def test_cantor_n2_bit_exact_backward_compatibility() -> None:
    """hierarchy='Cantor_N2' must produce bit-for-bit identical tracks and meshes across all designs."""
    for vernier in (False, True):
        assert build_hierarchy_tracks("Cantor_N2", vernier=vernier) == canonical_cantor_n2_tracks(
            vernier=vernier
        )

    for dname in ENGINE_DESIGN_NAMES:
        m_default = build_engine_surface_mesh(
            dname, z_tip_um=-0.092, theta_deg=22.0, n_r=1, n_phi_tooth=2, n_phi_bridge=2, n_z=1
        )
        m_explicit = build_engine_surface_mesh(
            dname,
            z_tip_um=-0.092,
            theta_deg=22.0,
            n_r=1,
            n_phi_tooth=2,
            n_phi_bridge=2,
            n_z=1,
            hierarchy="Cantor_N2",
        )
        assert len(m_default.rotor) == len(m_explicit.rotor)
        assert len(m_default.stator) == len(m_explicit.stator)
        for p1, p2 in zip(m_default.rotor + m_default.stator, m_explicit.rotor + m_explicit.stator):
            assert np.array_equal(p1.vertices, p2.vertices)
            assert np.array_equal(p1.normal, p2.normal)
            assert p1.area == p2.area


@pytest.mark.parametrize("hierarchy", HIERARCHY_NAMES)
def test_all_hierarchies_valid_disjoint_and_clearance(hierarchy: str) -> None:
    """Every hierarchy (N=0, N=1, N=2, Uniform_3Track, N=3) must pass intra-body & cross-body clearance."""
    min_clr = 0.008 if hierarchy != "Cantor_N3" else 0.006
    for dname in ("Sym_Baseline_CantorN2", "Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull"):
        for z_u, th_d in ((-0.092, 22.0), (-0.084, 64.0)):
            mesh = build_engine_surface_mesh(
                dname,
                z_tip_um=z_u,
                theta_deg=th_d,
                n_r=1,
                n_phi_tooth=2,
                n_phi_bridge=2,
                n_z=1,
                hierarchy=hierarchy,
                min_clearance_um=min_clr,
            )
            assert mesh.parameters["certified_min_clearance_um"] >= min_clr

    # Verify matched total slot width (500 nm) across N0_Macro_Ring, Cantor_N2, and Uniform_3Track
    if hierarchy in ("N0_Macro_Ring", "Cantor_N2", "Uniform_3Track"):
        trks = build_hierarchy_tracks(hierarchy, vernier=True)
        assert math.isclose(sum(t.w_slot for t in trks), 0.500, rel_tol=1.0e-5, abs_tol=1.0e-5)


def test_hermite_batch_matches_scalar_and_baoab_second_law() -> None:
    """eval_hermite_batch must match scalar eval_e_fz_tau and BAOAB must obey 300 K Second Law + equipartition."""
    z_grid = np.linspace(ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MAX_UM, 7)
    th_grid = np.linspace(0.0, SECTOR_DEG, 36, endpoint=False)
    zz, tt = np.meshgrid(z_grid, np.deg2rad(th_grid), indexing="ij")
    phi4 = 4.0 * tt
    # Strongly chiral asymmetric periodic potential (sawtooth harmonic)
    shape = -(np.cos(phi4 - 0.8) + 0.42 * np.sin(2.0 * (phi4 - 0.8)))
    dshape_dth = 4.0 * np.sin(phi4 - 0.8) - 3.36 * np.cos(2.0 * (phi4 - 0.8))
    decay = np.exp(-(zz + 0.100) / 0.025)
    ddecay_dz = -(1.0 / 0.025) * decay

    e_grid = 0.25 * shape * decay
    fz_grid = -(0.25 * shape * ddecay_dz)
    tau_grid = -(0.25 * dshape_dth * decay)
    pot = PeriodicHermitePotential2D(z_grid, th_grid, e_grid, fz_grid, tau_grid)

    rng = np.random.default_rng(42)
    z_samples = rng.uniform(ENGINE_Z_TIP_MIN_UM + 0.001, ENGINE_Z_TIP_MAX_UM - 0.001, size=25)
    th_samples_deg = rng.uniform(0.0, 360.0, size=25)
    eb, fzb, taub = eval_hermite_batch(pot, z_samples, np.deg2rad(th_samples_deg))
    for i in range(len(z_samples)):
        es, fzs, taus = pot.eval_e_fz_tau(float(z_samples[i]), float(th_samples_deg[i] % SECTOR_DEG))
        assert math.isclose(float(eb[i]), es, rel_tol=1.0e-12, abs_tol=1.0e-12)
        assert math.isclose(float(fzb[i]), fzs, rel_tol=1.0e-12, abs_tol=1.0e-12)
        assert math.isclose(float(taub[i]), taus, rel_tol=1.0e-12, abs_tol=1.0e-12)

    # Verify exact zeroing of fz outside [z_min, z_max] ([BUG-261112-08])
    _, fz_out, _ = eval_hermite_batch(
        pot, np.array([ENGINE_Z_TIP_MIN_UM - 0.005, ENGINE_Z_TIP_MAX_UM + 0.005]), np.array([0.2, 0.5])
    )
    assert np.all(fz_out == 0.0)

    # Equilibrium 300 K Second-Law & Maxwell-Boltzmann equipartition test on chiral sawtooth potential
    eq = simulate_baoab_langevin_ensemble(
        "Config_D_DualStator_PushPull",
        pot,
        mode="equilibrium_static",
        temperature_K=300.0,
        n_traj=256,
        n_steps=4000,
        dt_us=0.025,
        seed=12345,
        thermalize_init=True,
    )
    assert 0.88 <= eq["equipartition_th_ratio"] <= 1.12
    assert 0.88 <= eq["equipartition_z_ratio"] <= 1.12
    assert abs(eq["mean_advance_deg"]) <= 3.5 * max(eq["se_advance_deg"], 0.5)


def test_uf5_and_uf6_micro_probes_and_walltime_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify --max-steps 2 micro-probes and walltime exit code 75 for both UF5 and UF6."""
    from fractal_casimir_engine import run_ultrafine_cantor_ablation as uf5
    from fractal_casimir_engine import run_ultrafine_langevin_and_tolerances as uf6

    # Redirect probe output to tmp_path while allowing UF6 to read existing uf1/uf3 reports
    real_uf_dir = uf6.UF_RESULTS_DIR
    probe_dir = tmp_path / "ultrafine"
    probe_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("uf1_mesh_convergence_report.json", "uf3_active_switching_report.json"):
        src = real_uf_dir / fname
        if src.is_file():
            (probe_dir / fname).write_bytes(src.read_bytes())

    monkeypatch.setattr(uf5, "UF_RESULTS_DIR", probe_dir)
    monkeypatch.setattr(uf6, "UF_RESULTS_DIR", probe_dir)

    rc5 = uf5.main(["--max-steps", "2", "--device", "cpu"])
    assert rc5 == 0
    p5 = json.loads((probe_dir / "probe_uf5_cantor_ablation_report.json").read_text(encoding="utf-8"))
    assert p5["status"] == "micro_probe_completed"
    assert set(p5["samples"].keys()) == {"N0_Macro_Ring", "Cantor_N2", "Uniform_3Track", "Cantor_N3"}

    if (probe_dir / "uf1_mesh_convergence_report.json").is_file():
        rc6 = uf6.main(["--max-steps", "2", "--device", "cpu"])
        assert rc6 == 0
        p6 = json.loads((probe_dir / "probe_uf6_langevin_and_tolerances_report.json").read_text(encoding="utf-8"))
        assert p6["status"] == "micro_probe_completed"
        assert "sample_misalignment" in p6
        assert "sample_roughness" in p6 and len(p6["sample_roughness"]) == 2

    # Verify walltime timeout returns exit code 75 for Slurm auto-resubmit chaining
    monkeypatch.setattr(uf5, "run_full_campaign", lambda _args: (_ for _ in ()).throw(TimeoutError("walltime")))
    assert uf5.main(["--max-steps", "0", "--device", "cpu"]) == 75
    monkeypatch.setattr(uf6, "run_full_campaign", lambda _args: (_ for _ in ()).throw(TimeoutError("walltime")))
    assert uf6.main(["--max-steps", "0", "--device", "cpu"]) == 75


def test_extended_suites_aggregation_check(tmp_path: Path) -> None:
    """aggregate_campaigns(require_extended=True) must report missing UF5/UF6 until completed."""
    from fractal_casimir_engine.aggregate_ultrafine_campaigns import aggregate_campaigns

    res = aggregate_campaigns(
        uf_results_dir=tmp_path / "empty_uf",
        engine_figures_dir=tmp_path / "empty_fig",
        paper_dir=tmp_path / "empty_paper",
        check_only=True,
        require_extended=True,
    )
    assert res["ready"] is False
    missing_text = "\n".join(res["missing"])
    assert "eng_uf5" in missing_text and "eng_uf6" in missing_text


def test_uf5_export_provenance_and_figure_from_stub_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """export_uf5_provenance_and_figure must emit metrics, macros, and figure sidecars cleanly."""
    from fractal_casimir_engine import run_ultrafine_cantor_ablation as uf5

    uf_dir = tmp_path / "uf"
    fig_dir = tmp_path / "figs"
    uf_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(uf5, "UF_RESULTS_DIR", uf_dir)
    monkeypatch.setattr(uf5, "ENGINE_FIGURES_DIR", fig_dir)

    cell = {
        "benchmark_states": {
            "Stroke_I_Repulsive": {"tau_theta_pN_um": 0.8},
            "Stroke_III_Attractive": {"tau_theta_pN_um": 0.6},
            "mean_dual_stroke_tau_pN_um": 0.7,
        },
        "cycle_energetics": {"w_power_strokes_aJ": 0.32},
        "gated_dynamics": {"net_rotation_deg": 420.0},
        "stability_6dof": {"torque_to_pullin_fom_nm_um": 1.25},
    }
    matrix = {d: {h: cell for h in uf5.HIERARCHY_NAMES} for d in uf5.ABLATION_DESIGNS}
    rep = {
        "suite": "eng_uf5",
        "status": "completed",
        "time_truncated": False,
        "hierarchies": list(uf5.HIERARCHY_NAMES),
        "summary": {
            "config_d_n0_mean_tau_pN_um": 0.2,
            "config_d_n2_mean_tau_pN_um": 0.8,
            "config_d_uni_mean_tau_pN_um": 0.5,
            "config_d_n3_mean_tau_pN_um": 0.9,
            "config_d_n2_vs_n0_tau_gain": 4.0,
            "config_d_n2_vs_uniform_tau_gain": 1.6,
            "config_d_n3_spin_up_deg": 450.0,
        },
        "matrix": matrix,
    }
    rep_path = uf_dir / "uf5_cantor_ablation_report.json"
    rep_path.write_text(json.dumps(rep), encoding="utf-8")
    rc = uf5.main(["--from-report", str(rep_path)])
    assert rc == 0
    assert (uf_dir / "uf5_provenance_metrics.json").is_file()
    assert (uf_dir / "uf5_macros_results.tex").is_file()
    assert (fig_dir / "fig_uf5_cantor_scaling.png.provenance.json").is_file()


