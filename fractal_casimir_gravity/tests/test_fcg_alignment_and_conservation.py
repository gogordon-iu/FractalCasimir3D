"""Comprehensive Manuscript-Code Alignment, Disentanglement, Symmetry & Conservation Tests."""

from __future__ import annotations

import ast
import math
from pathlib import Path
import re

import numpy as np
import pytest

from fractal_casimir_gravity.analytics.units_and_identities import (
    brown_maclay_tensor_covariant,
    epsilon_planck_sq,
    minkowski_trace,
    verify_symbolic_identities,
)
from fractal_casimir_gravity.simulations.generate_all_figures_and_tables import generate_all
from fractal_casimir_gravity.solvers.bem_scattering import (
    compute_casimir_energy_bem,
    compute_cavity_thermodynamics,
    compute_four_pass_stress_tensor,
)
from fractal_casimir_gravity.solvers.cpsc_geometry import (
    CPSCSpec,
    verify_rigid_quadrupole_moment,
)
from fractal_casimir_gravity.solvers.linearized_gravity import (
    construct_covariant_virial_and_quadrupole,
    evaluate_ford_roman_worldline_qei,
    fit_log_periodic_metric_comb,
    solve_isolated_poisson_3d,
)
from fractal_casimir_gravity.utils.metrics_logger import (
    STANDARD_LATEX_COMMANDS,
    _format_macro_value,
    _sanitize_macro_name,
)

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
PAPER_DIR = WORKTREE_ROOT / "Papers" / "Fractal_Casimir_Gravity"
CODE_DIR = WORKTREE_ROOT / "fractal_casimir_gravity"


def test_symbolic_analytical_identities() -> None:
    checks = verify_symbolic_identities()
    assert all(checks.values()), f"Symbolic identity check failed: {checks}"
    eps2 = epsilon_planck_sq(1.0e-6)
    assert 2.6e-58 < eps2 < 2.7e-58


def test_manuscript_code_macro_and_figure_bijection() -> None:
    tex_text = (PAPER_DIR / "fractal_casimir_gravity.tex").read_text(encoding="utf-8")
    macros_text = (PAPER_DIR / "macros_gravity.tex").read_text(encoding="utf-8")

    # 1. Extract all custom uppercase macros referenced in fractal_casimir_gravity.tex
    used_upper = {
        m for m in re.findall(r"\\([A-Z][a-zA-Z]+)", tex_text)
        if m not in STANDARD_LATEX_COMMANDS
    }
    defined_macros = set(re.findall(r"\\newcommand\{\\([A-Z][a-zA-Z]+)\}", macros_text))
    assert len(defined_macros) == 30
    assert used_upper == defined_macros, (
        f"Mismatch between .tex usage and macros_gravity.tex:\n"
        f"  Only in .tex: {used_upper - defined_macros}\n"
        f"  Only in macros_gravity.tex: {defined_macros - used_upper}"
    )

    # 2. AST-scan sim1..sim5 for log_metric keys and check exact 1-to-1 bijection
    sim_files = sorted((CODE_DIR / "simulations").glob("sim*.py"))
    assert len(sim_files) == 5
    logged_keys = []
    for sf in sim_files:
        tree = ast.parse(sf.read_text(encoding="utf-8"), filename=str(sf))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "log_metric":
                assert isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                logged_keys.append(node.args[0].value)

    assert len(logged_keys) == 30, f"Expected 30 logged metrics, found {len(logged_keys)}"
    assert len(set(logged_keys)) == 30, "Duplicate metric keys detected across sim1..sim5"
    sanitized_from_code = {_sanitize_macro_name(k) for k in logged_keys}
    assert sanitized_from_code == defined_macros, (
        f"Macro bijection mismatch:\n"
        f"  Code - Paper: {sanitized_from_code - defined_macros}\n"
        f"  Paper - Code: {defined_macros - sanitized_from_code}"
    )

    # 3. Check all 6 figure stems match between manuscript and figure generator
    tex_figs = set(re.findall(r"figures/(fig[0-9]_[a-z0-9_]+)\.pdf", tex_text))
    gen_text = (CODE_DIR / "simulations" / "generate_all_figures_and_tables.py").read_text(encoding="utf-8")
    code_figs = set(re.findall(r'"(fig[0-9]_[a-z0-9_]+)"', gen_text))
    assert len(tex_figs) == 6
    assert tex_figs == code_figs

    # 4. Verify macros_gravity.tex holds all \pendingval pre-run, or zero \pendingval post-sync
    map_path = CODE_DIR / "results" / "manuscript_provenance_map.json"
    if map_path.exists():
        for line in macros_text.splitlines():
            if line.strip().startswith(r"\newcommand"):
                assert r"{\pendingval}" not in line, f"Unresolved placeholder in macros_gravity.tex: {line}"
    else:
        for line in macros_text.splitlines():
            if line.strip().startswith(r"\newcommand"):
                assert r"{\pendingval}" in line, f"Premature numerical result found in macros_gravity.tex: {line}"


def test_disentanglement_firewall() -> None:
    # Construct forbidden tokens dynamically so this test file itself stays clean too
    forbidden_patterns = [
        "quantum" + " clutch",
        r"\bnems\b",
        "stiction",
        "landing" + " pad",
        r"\bdrude\b",
        "matsubara",
        "patch" + " potential",
        "cantor_n2_hybridrz",
        "h3-cantor",
        r"\bfrom\s+execution\b",
        r"\bimport\s+execution\b",
    ]
    this_file = Path(__file__).resolve()
    targets = (
        list(PAPER_DIR.glob("*.tex"))
        + list(PAPER_DIR.glob("*.bib"))
        + [p for p in CODE_DIR.rglob("*.py") if p.resolve() != this_file]
    )
    assert len(targets) >= 12
    for path in targets:
        txt = path.read_text(encoding="utf-8").lower()
        for pat in forbidden_patterns:
            assert re.search(pat, txt) is None, f"Disentanglement violation '{pat}' in {path}"


def test_grounded_pipeline_missing_data_guard(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="RUN_DATA_MISSING"):
        generate_all(results_dir=str(tmp_path / "empty_results"))

    assert _format_macro_value(0.0) == "0"
    assert r"\times 10^{-16}" in _format_macro_value(1.23e-16)


def test_bem_bloch_equivalence_rigid_quadrupole_and_flat_null() -> None:
    spec_v = CPSCSpec("Vernier_Test", "vernier_6_4", "coplanar", "prefractal", 1)
    qu, ql = verify_rigid_quadrupole_moment(spec_v, theta_rad=0.31)
    assert qu < 1.0e-14
    assert ql < 1.0e-14

    # Bloch reduction M_g = 2 vs full dense 2*pi ring M_g = 1 must match to machine precision
    e_bloch_s = compute_casimir_energy_bem(
        spec_v, 0.19, field_model="scalar_conformal", n_kappa=6, n_rad=1, n_phi=2, n_z=1, use_bloch=True,
    )
    e_dense_s = compute_casimir_energy_bem(
        spec_v, 0.19, field_model="scalar_conformal", n_kappa=6, n_rad=1, n_phi=2, n_z=1, use_bloch=False,
    )
    assert e_bloch_s < 0.0
    assert abs(e_bloch_s - e_dense_s) / abs(e_dense_s) < 1.0e-11

    e_bloch_em = compute_casimir_energy_bem(
        spec_v, 0.19, field_model="em_pec", n_kappa=5, n_rad=1, n_phi=2, n_z=1, use_bloch=True,
    )
    e_dense_em = compute_casimir_energy_bem(
        spec_v, 0.19, field_model="em_pec", n_kappa=5, n_rad=1, n_phi=2, n_z=1, use_bloch=False,
    )
    assert e_bloch_em < 0.0
    assert abs(e_bloch_em - e_dense_em) / abs(e_dense_em) < 1.0e-11

    # Flat annulus exact Euler dilatation homogeneity => zero Effective Trace
    spec_flat = CPSCSpec("Flat_Test", "breathing_4_4", "coplanar", "flat_annulus", 0)
    thermo_flat = compute_cavity_thermodynamics(
        spec_flat, 0.0, field_model="em_pec", n_kappa=8, n_rad=2, n_phi=2, n_z=1, compute_torque=False,
    )
    v_cav_flat = math.pi * (spec_flat.r_out**2 - spec_flat.r_in**2) * spec_flat.d_0
    rho_flat_mag = abs(thermo_flat.energy_tilde) / v_cav_flat
    assert thermo_flat.force_z_tilde < 0.0
    assert abs(thermo_flat.trace_eff_tilde) / rho_flat_mag < 1.0e-12


def test_open_to_facing_force_sign_inversion_and_voxel_traces() -> None:
    spec_c = CPSCSpec("CPSC_SignTest", "breathing_4_4", "coplanar", "prefractal", 1)
    th_open = compute_cavity_thermodynamics(
        spec_c, 0.0, field_model="em_pec", n_kappa=8, n_rad=1, n_phi=2, n_z=1, compute_torque=False,
    )
    th_face = compute_cavity_thermodynamics(
        spec_c, math.pi / 4.0, field_model="em_pec", n_kappa=8, n_rad=1, n_phi=2, n_z=1, compute_torque=False,
    )
    # Open-aperture upward restoring/repulsive force > 0 vs facing-sector attraction < 0
    assert th_open.force_z_tilde > 0.0
    assert th_face.force_z_tilde < 0.0

    # Check interior vacuum voxel stress-tensor trace identities across all 3 QFT models
    pts = np.array([[0.625, 0.0, -0.110], [0.45, 0.45, -0.06]], dtype=np.float64)
    res_em = compute_four_pass_stress_tensor(
        spec_c, 0.1, pts, field_model="em_pec", n_kappa=6, n_rad=1, n_phi=2, n_z=1,
    )
    res_cf = compute_four_pass_stress_tensor(
        spec_c, 0.1, pts, field_model="scalar_conformal", n_kappa=6, n_rad=1, n_phi=2, n_z=1,
    )
    res_mn = compute_four_pass_stress_tensor(
        spec_c, 0.1, pts, field_model="scalar_minimal", n_kappa=6, n_rad=1, n_phi=2, n_z=1,
    )
    assert np.all(res_em["valid_mask"])
    norm_em = float(np.max(np.abs(res_em["t_total_ren"])))
    norm_cf = float(np.max(np.abs(res_cf["t_total_ren"])))
    norm_mn = float(np.max(np.abs(res_mn["t_total_ren"])))
    assert np.max(np.abs(minkowski_trace(res_em["t_total_ren"]))) / norm_em < 1.0e-12
    assert np.max(np.abs(minkowski_trace(res_cf["t_total_ren"]))) / norm_cf < 1.0e-12
    assert np.max(np.abs(minkowski_trace(res_mn["t_total_ren"]))) / norm_mn > 1.0e-3


def test_poisson_virial_qei_and_dsi_comb_recovery() -> None:
    # 1. 3D isolated-boundary Poisson test against analytical uniform ball nabla^2 psi = rho_0
    n = 28
    xs = np.linspace(-1.4, 1.4, n)
    dx = float(xs[1] - xs[0])
    gx, gy, gz = np.meshgrid(xs, xs, xs, indexing="ij")
    rr = np.sqrt(gx * gx + gy * gy + gz * gz)
    r_ball = 0.55
    src = np.where(rr <= r_ball, 1.0, 0.0)
    psi = solve_isolated_poisson_3d(src, (dx, dx, dx))
    # Analytical center potential of nabla^2 psi = 1 inside radius R: psi(0) = -R^2 / 2
    mid = n // 2
    psi_center_exact = -0.5 * (r_ball**2)
    assert abs(psi[mid, mid, mid] - psi_center_exact) / abs(psi_center_exact) < 0.03

    # 2. Covariant virial conservation test
    theta_g = np.linspace(0.0, math.pi, 16, endpoint=False)
    phi_v = np.linspace(0.0, 2.0 * math.pi, 24, endpoint=False)
    coords = np.column_stack([0.6 * np.cos(phi_v), 0.6 * np.sin(phi_v), np.zeros_like(phi_v)])
    vols = np.full(len(phi_v), 0.01)
    t00 = -1.0e-3 * np.cos(2.0 * phi_v[None, :] - 6.0 * theta_g[:, None])
    tij = np.zeros((16, len(phi_v), 3, 3), dtype=np.float64)
    vir = construct_covariant_virial_and_quadrupole(t00, tij, coords, vols, theta_g, omega_tilde=0.1)
    assert float(vir["virial_rel_err"]) < 1.0e-13
    assert float(vir["p_gw_tilde"]) > 0.0

    # 3. Ford-Roman QEI bound test on planar Brown-Maclay negative energy
    bm = brown_maclay_tensor_covariant(gap_tilde=0.5, field_model="em_pec")
    t00_ring = np.full(32, bm[0, 0])
    qei = evaluate_ford_roman_worldline_qei(t00_ring, np.linspace(0, 2 * math.pi, 32, endpoint=False), 0.1, 0.15)
    assert qei["compliant"] is True
    assert 0.0 < qei["saturation_ratio"] < 1.0

    # 4. DSI log-periodic comb frequency recovery for b = 3.0
    x_ln = np.linspace(0.0, 4.0, 60)
    w_true = 2.0 * math.pi / math.log(3.0)
    y_sig = 1.2 - 0.05 * x_ln + 0.18 * np.cos(w_true * x_ln - 0.4)
    fit = fit_log_periodic_metric_comb(x_ln, y_sig)
    assert abs(float(fit["omega_hat"]) - w_true) < 0.05
    assert abs(float(fit["b_hat"]) - 3.0) < 0.03
    assert float(fit["r_squared"]) > 0.98
