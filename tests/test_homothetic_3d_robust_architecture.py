#!/usr/bin/env python3
"""Unit and physics invariant tests for `H3-Cantor-Robust` and matched controls."""

from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from execution.clutch_geometry_redesign import (
    H3_ROBUST_BASE_B,
    H3_ROBUST_G_MIN_NM,
    H3_ROBUST_NOMINAL_OP_Z_UM,
    H3_ROBUST_R_MAX_UM,
    H3_ROBUST_R_MIN_UM,
)
from execution.homothetic_3d_robust_architecture import (
    DISENGAGED_THETA_DEG,
    ENGAGED_THETA_DEG,
    active_tooth_area_um2,
    build_all_robustness_study_designs,
    build_h3_cantor_robust_design,
    build_h3_cantor_sym_2x2x2_design,
    build_homothetic_sector_bem_mesh,
    clear_bem_lu_caches,
    compute_design_geometric_summary,
    evaluate_homothetic_3d_bem,
    evaluate_laplace_capacitance_and_vcrit,
    solve_hermite_clamped_beam_fem,
    verify_design_3d_non_intersection,
)


def test_h3_cantor_exact_b3_3d_homothety() -> None:
    """Verify exact b=3.0 scaling across all 8 geometric dimensions of H3-Cantor-Robust."""
    h3 = build_h3_cantor_robust_design()
    assert len(h3.tracks) == 7
    by_gen = {m: [t for t in h3.tracks if t.generation == m] for m in (1, 2, 3)}
    assert len(by_gen[1]) == 1
    assert len(by_gen[2]) == 2
    assert len(by_gen[3]) == 4

    for m_coarse, m_fine in ((1, 2), (2, 3)):
        tc = by_gen[m_coarse][0]
        tf = by_gen[m_fine][0]
        chord_c = tc.radial_center_um * math.radians(tc.lobe_offsets_deg[0][1])
        chord_f = tf.radial_center_um * math.radians(tf.lobe_offsets_deg[0][1])
        bridge_h_c = tc.micro_bridges[0].z_top_um - tc.micro_bridges[0].z_bot_um
        bridge_h_f = tf.micro_bridges[0].z_top_um - tf.micro_bridges[0].z_bot_um

        for label, val_c, val_f in (
            ("slot_width", tc.slot_width_um, tf.slot_width_um),
            ("tooth_width", tc.tooth_width_um, tf.tooth_width_um),
            ("radial_gap", tc.radial_gap_um, tf.radial_gap_um),
            ("z_stage_center", abs(tc.z_stage_center_um), abs(tf.z_stage_center_um)),
            ("h_stage", tc.h_stage_um, tf.h_stage_um),
            ("lobe_chord", chord_c, chord_f),
            ("collar_width", tc.collar_width_um, tf.collar_width_um),
            ("bridge_thickness", bridge_h_c, bridge_h_f),
        ):
            ratio = val_c / val_f
            assert math.isclose(ratio, H3_ROBUST_BASE_B, rel_tol=1.0e-12), (
                f"{label} ratio between gen {m_coarse} and {m_fine} is {ratio}, expected {H3_ROBUST_BASE_B}"
            )


def test_iso_area_and_feature_floors_across_all_controls() -> None:
    """Verify exact active-area matching, envelope bounds, and g_min=27 nm floor."""
    designs = build_all_robustness_study_designs()
    assert len(designs) == 7
    h3 = designs[0]
    a_ref = active_tooth_area_um2(h3)
    assert math.isclose(a_ref, 3.102624, rel_tol=1.0e-12)

    h3_summary = compute_design_geometric_summary(h3)
    assert math.isclose(h3_summary["g_r_min_nm"], H3_ROBUST_G_MIN_NM, rel_tol=1.0e-12)

    for des in designs[1:]:
        a_ctrl = active_tooth_area_um2(des)
        assert abs(a_ctrl - a_ref) <= 1.0e-9, f"{des.code} area {a_ctrl} != {a_ref}"
        assert math.isclose(des.R_min_um, H3_ROBUST_R_MIN_UM, rel_tol=1.0e-12)
        assert math.isclose(des.R_max_um, H3_ROBUST_R_MAX_UM, rel_tol=1.0e-12)
        desc = compute_design_geometric_summary(des)
        assert desc["g_r_min_nm"] >= H3_ROBUST_G_MIN_NM - 1.0e-9

    knife_summary = compute_design_geometric_summary(designs[1])
    assert math.isclose(
        knife_summary["total_open_slot_width_um"],
        h3_summary["total_open_slot_width_um"],
        rel_tol=1.0e-12,
    )
    assert math.isclose(
        knife_summary["total_rib_metal_width_um"],
        h3_summary["total_rib_metal_width_um"],
        rel_tol=1.0e-12,
    )


def test_3d_non_intersection_and_mesh_collocation_validity() -> None:
    """Verify zero 3D solid collisions across stroke & rotation and distinct BEM centroids."""
    designs = build_all_robustness_study_designs()
    for des in designs:
        for z_um in (0.025, H3_ROBUST_NOMINAL_OP_Z_UM, 0.160, 0.520):
            chk = verify_design_3d_non_intersection(des, z_shift_um=z_um, theta_deg=DISENGAGED_THETA_DEG)
            assert chk["collision_free"], f"{des.code} stroke collision at z={z_um}: {chk['collisions']}"
        for th_deg in (0.0, DISENGAGED_THETA_DEG, 18.0, 30.0, ENGAGED_THETA_DEG):
            chk_r = verify_design_3d_non_intersection(
                des, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM, theta_deg=th_deg
            )
            assert chk_r["collision_free"], f"{des.code} rotation collision at theta={th_deg}: {chk_r['collisions']}"

        built = build_homothetic_sector_bem_mesh(des)
        assert built.mesh is not None
        assert not built.shorted
        for body_name in ("rotor", "stator"):
            arr = built.mesh.sector_arrays(body_name)
            assert arr.count > 0
            assert np.all(np.isfinite(arr.areas)) and np.all(arr.areas > 0.0)
            dmat = np.linalg.norm(arr.centroids[:, None, :] - arr.centroids[None, :, :], axis=2)
            off_diag = dmat[~np.eye(arr.count, dtype=bool)]
            assert np.min(off_diag) > 1.0e-7, f"Duplicate centroids in {des.code} {body_name}"


def test_etch_bias_dropout_and_shorting_guards() -> None:
    """Verify severe over-etch (-40 nm) drops 36 nm teeth cleanly while preserving coarse Cantor stages."""
    designs = {d.code: d for d in build_all_robustness_study_designs()}
    b_h3 = build_homothetic_sector_bem_mesh(designs["H3_Cantor_Robust"], delta_w_um=-0.040)
    assert not b_h3.all_teeth_etched_away
    assert b_h3.surviving_tracks == 3  # 1 coarse + 2 medium tracks survive

    b_ke = build_homothetic_sector_bem_mesh(designs["Ctrl_KnifeEdge_g27"], delta_w_um=-0.040)
    assert b_ke.all_teeth_etched_away
    assert b_ke.surviving_tracks == 0

    b_short = build_homothetic_sector_bem_mesh(designs["H3_Cantor_Robust"], delta_w_um=+0.026)
    assert b_short.shorted


def test_bem_lu_cache_and_analytic_force_energy_consistency() -> None:
    """Verify LU cache equivalence and F_z == +dE_Cas/dz_d thermodynamic consistency."""
    clear_bem_lu_caches()
    h3 = build_h3_cantor_robust_design()
    r_uncached = evaluate_homothetic_3d_bem(h3, n_xi=6, use_lu_cache=False)
    r_cached_1 = evaluate_homothetic_3d_bem(h3, n_xi=6, use_lu_cache=True)
    r_cached_2 = evaluate_homothetic_3d_bem(h3, z_shift_um=0.070, n_xi=6, use_lu_cache=True)
    r_uncached_2 = evaluate_homothetic_3d_bem(h3, z_shift_um=0.070, n_xi=6, use_lu_cache=False)

    assert math.isclose(r_uncached["F_z_pN"], r_cached_1["F_z_pN"], rel_tol=1.0e-12)
    assert math.isclose(r_uncached_2["F_z_pN"], r_cached_2["F_z_pN"], rel_tol=1.0e-12)

    dz_um = 0.0005
    z0 = H3_ROBUST_NOMINAL_OP_Z_UM
    rp = evaluate_homothetic_3d_bem(h3, z_shift_um=z0 + dz_um, n_xi=6)
    rm = evaluate_homothetic_3d_bem(h3, z_shift_um=z0 - dz_um, n_xi=6)
    f_fd_pN = ((rp["energy_J"] - rm["energy_J"]) / (2.0 * dz_um * 1.0e-6)) * 1.0e12
    assert math.isclose(r_cached_1["F_z_pN"], f_fd_pN, rel_tol=0.015), (
        f"Analytic F_z={r_cached_1['F_z_pN']} pN vs FD dE/dz_d={f_fd_pN} pN"
    )


def test_hermite_fem_exactness_and_27x_homothetic_span_stiffness() -> None:
    """Verify 32-element Hermite FEM accuracy against Euler-Bernoulli formula and 27x (3^3) stiffness law."""
    L_full = 3.0e-6
    EI = 79.0e9 * 80.0e-9 * ((100.0e-9) ** 3) / 12.0
    F_tot = 1.0e-9  # Same total transverse load F = q * L

    fem_1 = solve_hermite_clamped_beam_fem(
        span_length_m=L_full, flexural_rigidity_Nm2=EI, q_load_N_per_m=F_tot / L_full, k_neg_N_per_m2=0.0
    )
    assert math.isclose(
        fem_1["max_deflection_m"], fem_1["analytic_no_kneg_deflection_m"], rel_tol=1.0e-5
    )

    fem_third = solve_hermite_clamped_beam_fem(
        span_length_m=L_full / 3.0,
        flexural_rigidity_Nm2=EI,
        q_load_N_per_m=F_tot / (L_full / 3.0),
        k_neg_N_per_m2=0.0,
    )
    stiffness_ratio = fem_1["max_deflection_m"] / fem_third["max_deflection_m"]
    assert math.isclose(stiffness_ratio, 27.0, rel_tol=1.0e-5)


def test_cli_micro_probe_end_to_end(tmp_path: Path) -> None:
    """Run `--max-steps 2` CLI micro-probe and verify JSON & stdout schema."""
    out_probe = tmp_path / "probe_out.json"
    script = Path(__file__).resolve().parents[1] / "execution" / "run_unified_fractal_robustness_study.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--max-steps", "2", "--output-json", str(out_probe)],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [ln.strip() for ln in proc.stdout.strip().splitlines() if ln.strip()]
    assert len(lines) >= 1
    telemetry = json.loads(lines[-1])
    assert telemetry["event"] == "micro_probe_done"
    assert telemetry["steps"] == 2

    payload = json.loads(out_probe.read_text(encoding="utf-8"))
    for key in ("model", "dataset", "status", "executed_at", "sec_per_step", "records"):
        assert key in payload
    assert len(payload["records"]) == 2
    assert all(math.isfinite(r["F_z_pN"]) for r in payload["records"])


def test_input_validation_guards() -> None:
    """Verify adversarial-audit input validation guards on step sizes and CLI flags."""
    h3 = build_h3_cantor_robust_design()
    with pytest.raises(ValueError, match="dz_step_um"):
        evaluate_laplace_capacitance_and_vcrit(h3, f_z_nominal_pN=2.0, dz_step_um=0.0)
    with pytest.raises(ValueError, match="dz_step_um"):
        evaluate_laplace_capacitance_and_vcrit(h3, f_z_nominal_pN=2.0, dz_step_um=-0.001)

    from execution.run_unified_fractal_robustness_study import main as runner_main

    with pytest.raises(SystemExit):
        runner_main(["--n-mc", "0"])
    with pytest.raises(SystemExit):
        runner_main(["--n-xi", "0"])
    with pytest.raises(SystemExit):
        runner_main(["--max-steps", "-1"])


def test_blender_audit_and_visual_inspector(tmp_path: Path) -> None:
    """Verify Blender 3D patch serialization, design geometry audit, and PNG visual-quality inspector."""
    import matplotlib.image as mpimg
    from execution.build_unified_fractal_robustness_blender import (
        audit_robust_design_for_blender,
        inspect_rendered_png_quality,
        serialize_robust_design_blender_spec,
    )

    designs = build_all_robustness_study_designs()
    for idx, des in enumerate(designs, 1):
        aud = audit_robust_design_for_blender(des)
        assert aud["audit_status"] == "PASS", f"{des.code} failed Blender audit: {aud['issues']}"
        assert aud["collision_free_all_states"] is True
        spec = serialize_robust_design_blender_spec(
            idx, des, theta_deg=DISENGAGED_THETA_DEG, z_shift_um=H3_ROBUST_NOMINAL_OP_Z_UM
        )
        assert len(spec["stator_ribs"]) > 0
        assert len(spec["stator_pads"]) > 0
        # 1. Verify stator ribs exist ONLY in the 4 quarter-apertures [0, 36] mod 90, NEVER in (36, 90)
        for r_in, r_out, phi0, phi1, _, _ in spec["stator_ribs"]:
            assert r_out > r_in
            sec_phi0 = phi0 % 90.0
            sec_phi1 = phi1 - (phi0 - sec_phi0)
            assert sec_phi0 >= -1.0e-9 and sec_phi1 <= des.aperture_arc_deg + 1.0e-9, (
                f"{des.code} stator rib {phi0}..{phi1} intrudes into open attractive zone"
            )
        # 2. Verify hub_and_frame never enters active radial band (R_min, R_max) and shares identical [-0.64, 0.0] height datum
        frame_z_min = min(p[4] for p in spec["hub_and_frame"])
        frame_z_max = max(p[5] for p in spec["hub_and_frame"])
        assert math.isclose(frame_z_min, -0.640, abs_tol=1.0e-9)
        assert math.isclose(frame_z_max, 0.0, abs_tol=1.0e-9)
        for r_in, r_out, _, _, _, _ in spec["hub_and_frame"]:
            assert r_out <= des.R_min_um + 1.0e-9 or r_in >= des.R_max_um - 1.0e-9, (
                f"{des.code} frame patch [{r_in}, {r_out}] blocks active rotor slots"
            )
        if des.has_micro_bridges:
            assert len(spec["stator_bridges"]) == 4 * 35

    # Test programmatic PNG visual inspector on centered vs. clipped RGBA images
    img_ok = np.zeros((200, 300, 4), dtype=np.float32)
    yy, xx = np.meshgrid(np.linspace(0.2, 0.85, 120), np.linspace(0.25, 0.9, 180), indexing="ij")
    img_ok[40:160, 60:240, 0] = xx
    img_ok[40:160, 60:240, 1] = yy
    img_ok[40:160, 60:240, 2] = 0.5
    img_ok[40:160, 60:240, 3] = 1.0
    p_ok = tmp_path / "render_ok.png"
    mpimg.imsave(str(p_ok), img_ok)
    chk_ok = inspect_rendered_png_quality(p_ok, min_fg_fraction=0.15, max_fg_fraction=0.85, check_unclipped_margins=True)
    assert chk_ok["status"] == "PASS", chk_ok

    img_clipped = np.copy(img_ok)
    img_clipped[199, 120:150, :] = (0.8, 0.4, 0.2, 1.0)
    p_clip = tmp_path / "render_clipped.png"
    mpimg.imsave(str(p_clip), img_clipped)
    chk_clip = inspect_rendered_png_quality(
        p_clip, min_fg_fraction=0.15, max_fg_fraction=0.85, check_unclipped_margins=True
    )
    assert chk_clip["status"] == "FAIL"
    assert any("clipped" in msg for msg in chk_clip["issues"])


def test_postprocessing_provenance_figure_and_table_end_to_end(tmp_path: Path) -> None:
    """Verify _render_summary_figure, save_plot_provenance, _write_latex_summary_table, and Blender live-metric stamping."""
    from execution.build_unified_fractal_robustness_blender import (
        audit_robust_design_for_blender,
        compose_six_design_atlas_figure,
        inspect_rendered_png_quality,
    )
    from execution.run_unified_fractal_robustness_study import (
        _compute_combined_code_hash,
        _render_summary_figure,
        _write_latex_summary_table,
    )

    code_hash = _compute_combined_code_hash()
    assert len(code_hash) == 16

    designs = build_all_robustness_study_designs()
    designs_dict = {}
    for idx, d in enumerate(designs):
        designs_dict[d.code] = {
            "benchmark_1_axial_stroke": {
                "F_z_op_pN": 12.0 - idx,
                "log_stroke_basin_Bz": 2.15 - 0.1 * idx,
                "min_Fz_working_window_45_360nm_pN": 1.2 - 0.3 * idx,
                "sign_safe_span_nm": 410.0,
                "escape_work_kBT_300K": 25.0,
                "stroke_points": [{"z_d_nm": z, "F_z_pN": 5.0 - 0.01 * z} for z in (30.0, 56.0, 120.0, 360.0)],
            },
            "benchmark_2_angular_lateral": {
                "F_z_engaged_48deg_pN": -38.5,
                "torque_ripple_R_tau": 0.02 + 0.01 * idx,
            },
            "benchmark_3_rib_and_vcrit": {
                "rib_elastostatics": {"SF_rib": 5000.0 / (idx + 1)},
                "laplace_electrostatics": {"V_crit_mV": 85.0},
            },
            "benchmark_4_cleanroom_yield": {
                "cleanroom_yield_Y_lab_pct": 94.5 - 8.0 * idx,
                "etch_bias_curve": [{"delta_w_nm": dw, "F_z_zop_pN": 8.0 - 0.05 * abs(dw)} for dw in (-15.0, 0.0, 15.0)],
            },
        }

    kappas = [0.5, 2.0, 6.0, 18.0, 54.0]
    mock_subband = {
        "kappas_um_inv": kappas,
        "band_gen1_norm": [0.2, 1.0, 0.5, 0.2, 0.1],
        "band_gen2_norm": [0.1, 0.4, 1.0, 0.4, 0.1],
        "band_gen3_norm": [0.05, 0.2, 0.5, 1.0, 0.3],
        "peaks_by_generation": {
            "1": {"kappa_peak_um_inv": 2.0},
            "2": {"kappa_peak_um_inv": 6.0},
            "3": {"kappa_peak_um_inv": 18.0},
        },
        "spacing_comparison": {"delta_ln_kappa_21": 1.0986, "delta_ln_kappa_32": 1.0986},
    }
    mock_lomb = {
        "free_frequency_lomb_scargle": {
            "underdetermined": False,
            "omega_grid": [3.0, 5.72, 9.0],
            "r2_1h_spectrum": [0.15, 0.82, 0.21],
        }
    }
    mock_summary = {
        "executed_at": "2026-11-11T21:00:00Z",
        "designs": designs_dict,
        "benchmark_5_ln3_scale_covering": {
            "wavenumber_subbands": {
                "H3_Cantor_Robust_PEC": mock_subband,
                "H3_Cantor_Robust_Gold300K": mock_subband,
                "H3_Cantor_Sym_2x2x2_PEC": mock_subband,
                "H3_Cantor_Sym_2x2x2_Gold300K": mock_subband,
            },
            "stroke_log_periodicity": {
                "H3_Cantor_Robust_PEC": mock_lomb,
                "H3_Cantor_Robust_Gold300K": mock_lomb,
                "H3_Cantor_Sym_2x2x2_PEC": mock_lomb,
                "H3_Cantor_Sym_2x2x2_Gold300K": mock_lomb,
                "Ctrl_Lin_3Stage_Gold300K": mock_lomb,
                "Ctrl_KnifeEdge_g27_Gold300K": mock_lomb,
            },
        },
    }

    out_pdf = tmp_path / "fig_summary.pdf"
    out_png = tmp_path / "fig_summary.png"
    out_tex = tmp_path / "table_summary.tex"
    _render_summary_figure(mock_summary, out_pdf, out_png, code_hash)
    assert out_pdf.is_file() and out_png.is_file()
    assert Path(f"{out_pdf}.provenance.json").is_file()
    assert Path(f"{out_png}.provenance.json").is_file()

    fig_chk = inspect_rendered_png_quality(out_png, min_fg_fraction=0.04, max_fg_fraction=0.96)
    assert fig_chk["status"] == "PASS", fig_chk

    _write_latex_summary_table(mock_summary, out_tex)
    tex_txt = out_tex.read_text(encoding="utf-8")
    assert "H3-Cantor-Robust" in tex_txt
    assert "H3-Cantor-Sym-2x2x2" in tex_txt

    # Also verify Blender atlas live BEM metric annotation path
    audits = [audit_robust_design_for_blender(d) for d in designs]
    atlas_png = tmp_path / "atlas_stamped.png"
    atlas_pdf = tmp_path / "atlas_stamped.pdf"
    render_dir = Path(__file__).resolve().parents[1] / "results" / "unified_fractal_robustness_blender"
    compose_six_design_atlas_figure(designs, audits, designs_dict, render_dir, atlas_png, atlas_pdf)
    atlas_chk = inspect_rendered_png_quality(atlas_png, min_fg_fraction=0.10)
    assert atlas_chk["status"] == "PASS", atlas_chk


def test_h3_cantor_sym_2x2x2_symmetry_and_mesh_structure() -> None:
    """Verify H3-Cantor-Sym-2x2x2 zero-Vernier slot symmetry, 2x2x2+collar=9 mesh counts, and mirror-symmetric BEM energy."""
    h3_sym = build_h3_cantor_sym_2x2x2_design()
    assert h3_sym.code == "H3_Cantor_Sym_2x2x2"
    assert (h3_sym.bem_n_r_lobe, h3_sym.bem_n_phi_lobe, h3_sym.bem_n_z_lobe, h3_sym.bem_n_phi_collar) == (2, 2, 2, 9)
    assert math.isclose(active_tooth_area_um2(h3_sym), 3.102624, rel_tol=1.0e-12)

    for trk in h3_sym.tracks:
        assert trk.vernier_phase_deg == 0.0
        # Verify lobe center offsets d_phi are exact mirror images around 0 deg (slot center = 18 deg)
        centers = [d_phi for d_phi, _ in trk.lobe_offsets_deg]
        assert np.allclose(centers, [-c for c in reversed(centers)], atol=1.0e-12)
        # Verify stator micro-bridges are exact mirror images across the [0, 36] deg aperture
        b_centers = [b.phi_center_deg for b in trk.micro_bridges]
        assert np.allclose(b_centers, [36.0 - bc for bc in reversed(b_centers)], atol=1.0e-12)

    built_222 = build_homothetic_sector_bem_mesh(h3_sym)
    assert built_222.mesh is not None
    assert built_222.mesh.sector_arrays("rotor").count == 1008
    assert built_222.mesh.sector_arrays("stator").count == 1050

    # Fast 1x1x1 BEM check confirming exact mirror symmetry around theta = 3.0 deg (Delta_phi = 0)
    clear_bem_lu_caches()
    r_left = evaluate_homothetic_3d_bem(
        h3_sym, theta_deg=DISENGAGED_THETA_DEG - 0.5, n_xi=4, n_r_lobe=1, n_phi_lobe=1, n_z_lobe=1, n_phi_collar=3
    )
    r_right = evaluate_homothetic_3d_bem(
        h3_sym, theta_deg=DISENGAGED_THETA_DEG + 0.5, n_xi=4, n_r_lobe=1, n_phi_lobe=1, n_z_lobe=1, n_phi_collar=3
    )
    assert math.isclose(r_left["energy_J"], r_right["energy_J"], rel_tol=1.0e-11)
    assert math.isclose(r_left["F_z_pN"], r_right["F_z_pN"], rel_tol=1.0e-11)




