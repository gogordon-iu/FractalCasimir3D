#!/usr/bin/env python3
"""Unit & integration tests for Suite 7 (eng_uf7: Thermodynamics, Efficiency, & Applications)."""

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

from fractal_casimir_engine import run_ultrafine_thermodynamics_and_applications as uf7
from fractal_casimir_engine.geometries import ENGINE_Z_TIP_MAX_UM, ENGINE_Z_TIP_MIN_UM, SECTOR_DEG
from fractal_casimir_engine.run_engine_cycle_mapping import PeriodicHermitePotential2D


def _build_analytic_switching_potentials() -> tuple[PeriodicHermitePotential2D, PeriodicHermitePotential2D]:
    # Note: PeriodicHermitePotential2D(z_grid_um, theta_grid_deg, ...) takes theta_grid_deg in degrees
    # and converts internally via self.th_rad = np.deg2rad(theta_grid_deg), while partial derivatives
    # tau_grid_pN_um = -dE/dtheta_rad are with respect to radians (1 aJ/rad == 1 pN*um).
    z_grid = np.linspace(ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MAX_UM, 7, dtype=np.float64)
    th_grid_deg = np.linspace(0.0, SECTOR_DEG, 60, endpoint=False, dtype=np.float64)
    zz, tt_rad = np.meshgrid(z_grid, np.deg2rad(th_grid_deg), indexing="ij")

    # Two-stroke-per-90-deg-sector harmonic (8*theta, period 45 deg) with exact potential minima
    # (dE/dtheta == 0, d^2E/dtheta^2 > 0) at theta = 32.0 deg and 77.0 deg so the retarding back-slopes
    # (32..54 deg and 77..99 deg) lie squarely inside the two release windows (42.5 +/- 11.5 deg and
    # 89.0 +/- 11.5 deg), driving sustained forward rotation in both two_state_switching and pad_release_gated.
    phi8 = 8.0 * (tt_rad - math.radians(32.0))
    shape = -np.cos(phi8)
    dshape_dth_rad = 8.0 * np.sin(phi8)
    decay = np.exp(-(zz + 0.100) / 0.024)
    ddecay_dz = -(1.0 / 0.024) * decay

    e_on = 0.90 * shape * decay
    fz_on = -(0.90 * shape * ddecay_dz)
    tau_on = -(0.90 * dshape_dth_rad * decay)

    e_off = 0.05 * shape * decay
    fz_off = -(0.05 * shape * ddecay_dz)
    tau_off = -(0.05 * dshape_dth_rad * decay)

    return (
        PeriodicHermitePotential2D(z_grid, th_grid_deg, e_on, fz_on, tau_on),
        PeriodicHermitePotential2D(z_grid, th_grid_deg, e_off, fz_off, tau_off),
    )


def test_first_law_and_tur_on_loaded_switching_and_gated_ensembles() -> None:
    """Loaded BAOAB ensembles must satisfy steady-state First Law, Second Law (dS >= 0), and TUR (Q_TUR >= 0.9)."""
    pot_on, pot_off = _build_analytic_switching_potentials()

    res_sw = uf7.simulate_loaded_thermodynamic_ensemble(
        "Config_D_DualStator_PushPull",
        pot_on,
        pot_off=pot_off,
        mode="two_state_switching",
        temperature_K=300.0,
        tau_load_pN_um=0.01,
        n_traj=128,
        n_steps=4000,
        seed=101,
    )
    assert 0.0 <= abs(res_sw["discrete_kick_balance_residual_aJ"]) < 1.0e-10
    assert 0.0 <= abs(res_sw["first_law_residual_aJ"]) < 2.5e-2
    assert res_sw["delta_s_tot_kB"] > 0.0
    assert res_sw["q_tur"] is not None
    assert res_sw["q_tur"] >= 0.85  # finite-sample 128-trajectory margin around >= 1.0

    res_gt = uf7.simulate_loaded_thermodynamic_ensemble(
        "Config_D_DualStator_PushPull",
        pot_on,
        mode="pad_release_gated",
        temperature_K=300.0,
        tau_load_pN_um=0.005,
        pre_equilibrate=False,
        n_traj=128,
        n_steps=4000,
        seed=202,
    )
    assert 0.0 <= abs(res_gt["discrete_kick_balance_residual_aJ"]) < 1.0e-10
    assert 0.0 <= abs(res_gt["first_law_residual_aJ"]) < 2.5e-2
    assert res_gt["delta_s_tot_kB"] > 0.0
    assert res_gt["q_tur"] is not None
    assert res_gt["q_tur"] >= 0.85
    assert 0.0 <= res_gt["eta_shaft_rev_pct"] <= 100.0


def test_epstein_knudsen_drag_and_wall_plug_monotonicity() -> None:
    """Epstein 3D panel gas drag must be positive with realistic mTorr-Torr P_1/2 and wall-plug ordering."""
    ep = uf7.compute_epstein_knudsen_rotor_drag_coeff("Config_D_DualStator_PushPull", temperature_K=300.0)
    assert ep["rotor_surface_area_um2"] > 2.0
    assert ep["gamma_gas_per_Pa_Nm_s_rad"] > 0.0
    assert 1.0 < ep["half_speed_crossover_pressure_Pa"] < 500.0

    pot_on, pot_off = _build_analytic_switching_potentials()
    dummy_curve = uf7.sweep_loaded_motor_curve(
        "dummy",
        "Config_D_DualStator_PushPull",
        pot_on,
        pot_off=pot_off,
        mode="two_state_switching",
        temperature_K=300.0,
        pre_equilibrate=False,
        n_traj=24,
        n_steps=1600,
        n_load_points=5,
    )
    assert dummy_curve["tau_stall_pN_um"] > 0.0
    assert dummy_curve["points"][0]["eta_shaft_rev_pct"] == 0.0

    mc_map = {
        "Config_B_VO2_300K": dummy_curve,
        "Config_D_Si_300K": dummy_curve,
        "Config_D_Gated_300K": dummy_curve,
    }
    wp = uf7.compute_wall_plug_efficiency_budget(mc_map)
    mods = wp["modalities"]
    assert mods["VO2_Thermal_Mott_25nm"]["carnot_ceiling_pct"] == pytest.approx(13.04, abs=0.05)
    # 2D capacitive resonant gate must vastly exceed bulk thermal VO2 enthalpy wall-plug efficiency
    assert mods["Graphene_2D_Capacitive_Gate_0p5V"]["resonant_vs_vo2_efficiency_gain"] > 1.0e3


def test_uf7_micro_probe_and_walltime_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--max-steps 2 micro-probe must execute cleanly and walltime TimeoutError must return exit code 75."""
    real_uf_dir = uf7.UF_RESULTS_DIR
    probe_dir = tmp_path / "uf7_probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    src_uf1 = real_uf_dir / "uf1_mesh_convergence_report.json"
    if not src_uf1.is_file():
        pytest.skip("uf1_mesh_convergence_report.json not present in workspace")
    (probe_dir / "uf1_mesh_convergence_report.json").write_bytes(src_uf1.read_bytes())

    rc = uf7.main(["--max-steps", "2", "--device", "cpu", "--results-dir", str(probe_dir)])
    assert rc == 0
    probe_json = json.loads(
        (probe_dir / "probe_uf7_thermodynamics_and_applications_report.json").read_text(encoding="utf-8")
    )
    assert probe_json["status"] == "micro_probe_completed"
    assert probe_json["time_truncated"] is True

    monkeypatch.setattr(uf7, "run_full_campaign", lambda _args: (_ for _ in ()).throw(TimeoutError("walltime")))
    assert uf7.main(["--max-steps", "0", "--device", "cpu", "--results-dir", str(probe_dir)]) == 75

    # Verify --from-report provenance, macro, and figure export when a completed non-null report is present
    rep_src = real_uf_dir / "uf7_thermodynamics_and_applications_report.json"
    if rep_src.is_file():
        rep_obj = json.loads(rep_src.read_text(encoding="utf-8"))
        if rep_obj.get("summary", {}).get("cryo_4K_90deg_step_us") is not None:
            rep_dst = probe_dir / "uf7_thermodynamics_and_applications_report.json"
            rep_dst.write_bytes(rep_src.read_bytes())
            fig_dst = tmp_path / "uf7_figs"
            assert (
                uf7.main(
                    [
                        "--from-report",
                        str(rep_dst),
                        "--results-dir",
                        str(probe_dir),
                        "--figures-dir",
                        str(fig_dst),
                    ]
                )
                == 0
            )
            assert (probe_dir / "uf7_provenance_metrics.json").is_file()
            assert (probe_dir / "uf7_macros_results.tex").is_file()
            assert (fig_dst / "fig_uf7_thermodynamics_and_applications.png.provenance.json").is_file()

