#!/usr/bin/env python3
"""Post-harvest aggregator for the 4 BigRed 200 Ultra-Fine Fractal Casimir Engine suites.

After ``git pull`` brings back the completed BigRed 200 telemetry commits for
``eng_uf1``, ``eng_uf2``, ``eng_uf3``, and ``eng_uf4``, run this script to:
  1. Verify non-truncated completion of all 4 ``uf*_report.json`` artifacts,
     their ``uf*_provenance_metrics.json`` ledgers, ``uf*_macros_results.tex``
     exports, and ``fig_uf*`` figures + ``.provenance.json`` sidecars.
  2. Merge ``uf1``..``uf4`` provenance steps and metrics with the baseline
     ``fractal_casimir_engine/results/provenance_metrics.json``.
  3. Sync ``fig_uf1_*``..``fig_uf4_*`` + ``.provenance.json`` sidecars into
     ``Papers/Fractal_Casimir_Engine/figures/`` (unless ``--cluster-safe`` is set,
     which writes strictly under ``fractal_casimir_engine/results/ultrafine/``).
  4. Append ``uf1``..``uf4`` LaTeX macros into ``Papers/Fractal_Casimir_Engine/macros_results.tex``
     and regenerate ``manuscript_provenance_map.json`` (verifying ``audit_status == 'PASS'``).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.metrics_logger import _sanitize_macro_name, generate_manuscript_map

ENGINE_DIR = PROJECT_ROOT / "fractal_casimir_engine"
UF_RESULTS_DIR = ENGINE_DIR / "results" / "ultrafine"
ENGINE_FIGURES_DIR = ENGINE_DIR / "figures"
PAPER_DIR = PROJECT_ROOT / "Papers" / "Fractal_Casimir_Engine"
PAPER_FIGURES_DIR = PAPER_DIR / "figures"

REQUIRED_SUITES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "eng_uf1",
        "uf1_mesh_convergence_report.json",
        "uf1_provenance_metrics.json",
        "uf1_macros_results.tex",
        "fig_uf1_mesh_convergence",
    ),
    (
        "eng_uf2",
        "uf2_meep_verification_report.json",
        "uf2_provenance_metrics.json",
        "uf2_macros_results.tex",
        "fig_uf2_meep_vs_bem",
    ),
    (
        "eng_uf3",
        "uf3_active_switching_report.json",
        "uf3_provenance_metrics.json",
        "uf3_macros_results.tex",
        "fig_uf3_active_switching",
    ),
    (
        "eng_uf4",
        "uf4_6dof_and_rounding_report.json",
        "uf4_provenance_metrics.json",
        "uf4_macros_results.tex",
        "fig_uf4_6dof_and_rounding",
    ),
)

EXTENDED_SUITES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "eng_uf5",
        "uf5_cantor_ablation_report.json",
        "uf5_provenance_metrics.json",
        "uf5_macros_results.tex",
        "fig_uf5_cantor_scaling",
    ),
    (
        "eng_uf6",
        "uf6_langevin_and_tolerances_report.json",
        "uf6_provenance_metrics.json",
        "uf6_macros_results.tex",
        "fig_uf6_langevin_and_tolerances",
    ),
    (
        "eng_uf7",
        "uf7_thermodynamics_and_applications_report.json",
        "uf7_provenance_metrics.json",
        "uf7_macros_results.tex",
        "fig_uf7_thermodynamics_and_applications",
    ),
)


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _format_macro_val(val: int | float | str) -> str:
    if isinstance(val, float) and not isinstance(val, bool):
        if val != 0 and (abs(val) < 1e-4 or abs(val) >= 1e5):
            mant, exp = f"{val:.2e}".split("e")
            return f"\\ensuremath{{{mant} \\times 10^{{{int(exp)}}}}}"
        formatted = f"{val:.6g}"
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted
    return str(val)


def _rel_diff_pct(val: float, ref: float) -> float | None:
    denom = abs(float(ref))
    if denom == 0.0:
        return None
    return 100.0 * abs(float(val) - float(ref)) / denom


def _extract_derived_suite_metrics(
    suite_reports: dict[str, dict[str, Any]],
) -> dict[str, tuple[int | float, str, str]]:
    """Derive additional manuscript-level summary metrics directly from UF1-UF4 reports."""
    derived: dict[str, tuple[int | float, str, str]] = {}

    r1 = suite_reports.get("eng_uf1", {})
    if "ladder" in r1 and "ultrafine_dynamics" in r1:
        lad = r1["ladder"]
        d_l5 = lad["Config_D_DualStator_PushPull"][-1]
        b_l5 = lad["Config_B_Manhattan_Vernier"][-1]
        c_l5 = lad["Config_C_Helical_Turbine"][-1]
        s_l5 = lad["Sym_Baseline_CantorN2"][-1]
        derived["engine_uf1_max_panels"] = (int(d_l5["n_panels_total"]), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_sym_l5_s1_fz"] = (round(float(s_l5["states"]["Stroke_I_Repulsive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_sym_l5_s1_tau"] = (round(float(s_l5["states"]["Stroke_I_Repulsive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_sym_l5_s3_fz"] = (round(float(s_l5["states"]["Stroke_III_Attractive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_sym_l5_s3_tau"] = (round(float(s_l5["states"]["Stroke_III_Attractive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_b_l5_s1_fz"] = (round(float(b_l5["states"]["Stroke_I_Repulsive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_b_l5_s1_tau"] = (round(float(b_l5["states"]["Stroke_I_Repulsive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_b_l5_s3_fz"] = (round(float(b_l5["states"]["Stroke_III_Attractive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_b_l5_s3_tau"] = (round(float(b_l5["states"]["Stroke_III_Attractive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_c_l5_s1_fz"] = (round(float(c_l5["states"]["Stroke_I_Repulsive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_c_l5_s1_tau"] = (round(float(c_l5["states"]["Stroke_I_Repulsive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_c_l5_s3_fz"] = (round(float(c_l5["states"]["Stroke_III_Attractive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_c_l5_s3_tau"] = (round(float(c_l5["states"]["Stroke_III_Attractive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_d_l5_s1_fz"] = (round(float(d_l5["states"]["Stroke_I_Repulsive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_d_l5_s1_tau"] = (round(float(d_l5["states"]["Stroke_I_Repulsive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_d_l5_s3_fz"] = (round(float(d_l5["states"]["Stroke_III_Attractive"]["f_z_pN"]), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_d_l5_s3_tau"] = (round(float(d_l5["states"]["Stroke_III_Attractive"]["tau_theta_pN_um"]), 3), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")

        reg = {row["tag"]: row for row in r1.get("regularization_audit", [])}
        if "q3_sv100" in reg and "q4_sv100" in reg and "q3_sv025" in reg:
            q3, q4, sv25 = reg["q3_sv100"], reg["q4_sv100"], reg["q3_sv025"]
            q_fz_terms = [
                _rel_diff_pct(q3["Stroke_I_Repulsive"]["f_z_pN"], q4["Stroke_I_Repulsive"]["f_z_pN"]),
                _rel_diff_pct(q3["Stroke_III_Attractive"]["f_z_pN"], q4["Stroke_III_Attractive"]["f_z_pN"]),
            ]
            q_tau_terms = [
                _rel_diff_pct(q3["Stroke_I_Repulsive"]["tau_theta_pN_um"], q4["Stroke_I_Repulsive"]["tau_theta_pN_um"]),
                _rel_diff_pct(q3["Stroke_III_Attractive"]["tau_theta_pN_um"], q4["Stroke_III_Attractive"]["tau_theta_pN_um"]),
            ]
            sv_terms = [
                _rel_diff_pct(sv25["Stroke_I_Repulsive"]["f_z_pN"], q3["Stroke_I_Repulsive"]["f_z_pN"]),
                _rel_diff_pct(sv25["Stroke_I_Repulsive"]["tau_theta_pN_um"], q3["Stroke_I_Repulsive"]["tau_theta_pN_um"]),
            ]
            if all(t is not None for t in q_fz_terms):
                derived["engine_uf1_quad_fz_shift_pct"] = (round(float(max(t for t in q_fz_terms if t is not None)), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
            if all(t is not None for t in q_tau_terms):
                derived["engine_uf1_quad_tau_shift_pct"] = (round(float(max(t for t in q_tau_terms if t is not None)), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
            if all(t is not None for t in sv_terms):
                derived["engine_uf1_reg_shift_pct"] = (round(float(max(t for t in sv_terms if t is not None)), 2), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")

        dyn = r1["ultrafine_dynamics"]
        derived["engine_uf1_cfg_b_spin_up_deg"] = (round(float(dyn["Config_B_Manhattan_Vernier"]["pad_release_engine"]["net_rotation_deg"]), 1), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        derived["engine_uf1_cfg_c_spin_up_deg"] = (round(float(dyn["Config_C_Helical_Turbine"]["pad_release_engine"]["net_rotation_deg"]), 1), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        if "dense_cycle" in r1:
            max_clos = max(abs(float(v["periodic_closure_abs_error_aJ"])) for v in r1["dense_cycle"].values())
            derived["engine_uf1_max_closure_aj"] = (float(max_clos), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")
        if "ultrafine_landscapes" in r1:
            max_herm = max(abs(float(v["hermite_closed_loop_work_aJ"])) for v in r1["ultrafine_landscapes"].values())
            derived["engine_uf1_max_hermite_loop_aj"] = (float(max_herm), "uf1_ultrafine_mesh_convergence", "BEM_UltraFine_3D_Suite1")

    r2 = suite_reports.get("eng_uf2", {})
    if "comparisons" in r2 and "summary" in r2:
        s2 = r2["summary"]
        derived["engine_uf2_dx_nm"] = (int(round(float(r2.get("dx_nm", 10.0)))), "uf2_meep_verification", "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM")
        derived["engine_uf2_total_states"] = (int(s2["total_states"]), "uf2_meep_verification", "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM")
        derived["engine_uf2_chiral_states"] = (int(s2["chiral_states"]), "uf2_meep_verification", "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM")
        by_key = {(c["design_name"], c["stroke"]): c for c in r2["comparisons"]}
        for d_short, d_full in (
            ("sym", "Sym_Baseline_CantorN2"),
            ("cfg_b", "Config_B_Manhattan_Vernier"),
            ("cfg_c", "Config_C_Helical_Turbine"),
            ("cfg_d", "Config_D_DualStator_PushPull"),
        ):
            c1 = by_key[(d_full, "Stroke_I_Repulsive")]
            c3 = by_key[(d_full, "Stroke_III_Attractive")]
            derived[f"engine_uf2_{d_short}_s1_fz"] = (round(float(c1["meep_f_z_pN"]), 2), "uf2_meep_verification", "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM")
            derived[f"engine_uf2_{d_short}_s3_fz"] = (round(float(c3["meep_f_z_pN"]), 2), "uf2_meep_verification", "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM")
            tau_digits = 4 if d_short == "sym" else 3
            derived[f"engine_uf2_{d_short}_s1_tau"] = (round(float(c1["meep_tau_theta_pN_um"]), tau_digits), "uf2_meep_verification", "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM")
            derived[f"engine_uf2_{d_short}_s3_tau"] = (round(float(c3["meep_tau_theta_pN_um"]), 3), "uf2_meep_verification", "Meep_3D_FDTD_Casimir_MST_vs_UltraFine_BEM")

    r3 = suite_reports.get("eng_uf3", {})
    if "designs" in r3:
        ds = r3["designs"]
        b_vo2 = ds["Config_B_Manhattan_Vernier"]["vo2_switching_engine"]
        d_si = ds["Config_D_DualStator_PushPull"]["silicon_photodoped_engine"]
        derived["engine_uf3_cfg_b_vo2_adv_deg"] = (round(float(b_vo2["net_advance_deg"]), 1), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_b_vo2_em_work_aj"] = (round(float(b_vo2["net_em_work_into_rotor_aJ"]), 3), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_b_vo2_pump_aj"] = (round(float(b_vo2["w_pump_irrev_aJ"]), 3), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_b_vo2_res_aj"] = (round(float(b_vo2["first_law_residual_aJ"]), 4), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_b_vo2_mod_pct"] = (round(float(ds["Config_B_Manhattan_Vernier"]["vo2_torque_modulation_depth_pct"]), 1), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_b_si_adv_deg"] = (round(float(ds["Config_B_Manhattan_Vernier"]["silicon_photodoped_engine"]["net_advance_deg"]), 1), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_c_vo2_adv_deg"] = (round(float(ds["Config_C_Helical_Turbine"]["vo2_switching_engine"]["net_advance_deg"]), 1), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_c_si_adv_deg"] = (round(float(ds["Config_C_Helical_Turbine"]["silicon_photodoped_engine"]["net_advance_deg"]), 1), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_d_si_peak_deg"] = (round(float(d_si["max_advance_deg"]), 1), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_d_si_em_work_aj"] = (round(float(d_si["net_em_work_into_rotor_aJ"]), 3), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_cfg_d_si_pump_aj"] = (round(float(d_si["w_pump_irrev_aJ"]), 3), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")
        derived["engine_uf3_sym_si_adv_deg"] = (round(float(ds["Sym_Baseline_CantorN2"]["silicon_photodoped_engine"]["net_advance_deg"]), 2), "uf3_active_permittivity_switching", "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si")

    r4 = suite_reports.get("eng_uf4", {})
    if "hessian_6dof" in r4 and "corner_rounding" in r4:
        s4 = r4["summary"]
        total_poses = sum(len(v) for v in r4["hessian_6dof"].values())
        derived["engine_uf4_total_poses"] = (int(total_poses), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")
        derived["engine_uf4_max_c4_lat_force_pn"] = (float(s4["max_c4_lateral_force_residual_pN"]), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")
        derived["engine_uf4_max_k_tilt_pn_um_rad"] = (round(float(s4["max_k_tilt_destab_pN_um_rad"]), 2), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")
        for d_short, d_full in (
            ("sym", "Sym_Baseline_CantorN2"),
            ("cfg_b", "Config_B_Manhattan_Vernier"),
            ("cfg_c", "Config_C_Helical_Turbine"),
            ("cfg_d", "Config_D_DualStator_PushPull"),
        ):
            max_klat = max(float(x["k_destab_lat_max_uN_m"]) for x in r4["hessian_6dof"][d_full])
            derived[f"engine_uf4_{d_short}_max_k_lat_un_m"] = (round(max_klat, 2), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")
            cr_rows = r4["corner_rounding"][d_full]
            r15 = cr_rows[-1]
            derived[f"engine_uf4_{d_short}_r15_s1_tau"] = (round(float(r15["Stroke_I_Repulsive"]["tau_theta_pN_um"]), 3), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")
            derived[f"engine_uf4_{d_short}_r15_s3_tau"] = (round(float(r15["Stroke_III_Attractive"]["tau_theta_pN_um"]), 3), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")

        cr_d = r4["corner_rounding"]["Config_D_DualStator_PushPull"]
        d_r0, d_r15 = cr_d[0], cr_d[-1]
        derived["engine_uf4_r_edge_max_nm"] = (int(round(float(d_r15["r_edge_nm"]))), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")
        derived["engine_uf4_cfg_d_round_dofs"] = (int(d_r15["n_dofs_total"]), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")
        ref_fz_r0 = float(d_r0["Stroke_I_Repulsive"]["f_z_pN"])
        if ref_fz_r0 != 0.0:
            fz_ret_pct = 100.0 * float(d_r15["Stroke_I_Repulsive"]["f_z_pN"]) / ref_fz_r0
            derived["engine_uf4_cfg_d_retain_fz_s1_pct"] = (round(fz_ret_pct, 1), "uf4_6dof_and_ebl_rounding", "BEM_UltraFine_3D_Full4Sector6DOF_and_EBLPlanformRounding")

    r5 = suite_reports.get("eng_uf5", {})
    if "matrix" in r5 and "summary" in r5:
        m5 = r5["matrix"]
        for d_short, d_full in (
            ("sym", "Sym_Baseline_CantorN2"),
            ("cfg_b", "Config_B_Manhattan_Vernier"),
            ("cfg_d", "Config_D_DualStator_PushPull"),
        ):
            if d_full not in m5:
                continue
            for h_short, h_full in (
                ("n0", "N0_Macro_Ring"),
                ("n1", "Cantor_N1"),
                ("n2", "Cantor_N2"),
                ("uni", "Uniform_3Track"),
                ("n3", "Cantor_N3"),
            ):
                if h_full not in m5[d_full]:
                    continue
                cell = m5[d_full][h_full]
                derived[f"engine_uf5_{d_short}_{h_short}_mean_tau"] = (
                    round(float(cell["benchmark_states"]["mean_dual_stroke_tau_pN_um"]), 3),
                    "uf5_cantor_hierarchy_ablation",
                    "BEM_UltraFine_3D_CantorHierarchyAblation",
                )
                derived[f"engine_uf5_{d_short}_{h_short}_work_aj"] = (
                    round(float(cell["cycle_energetics"]["w_power_strokes_aJ"]), 3),
                    "uf5_cantor_hierarchy_ablation",
                    "BEM_UltraFine_3D_CantorHierarchyAblation",
                )
                derived[f"engine_uf5_{d_short}_{h_short}_spin_deg"] = (
                    round(float(cell["gated_dynamics"]["net_rotation_deg"]), 1),
                    "uf5_cantor_hierarchy_ablation",
                    "BEM_UltraFine_3D_CantorHierarchyAblation",
                )
                derived[f"engine_uf5_{d_short}_{h_short}_fom"] = (
                    round(float(cell["stability_6dof"]["torque_to_pullin_fom_nm_um"]), 3),
                    "uf5_cantor_hierarchy_ablation",
                    "BEM_UltraFine_3D_CantorHierarchyAblation",
                )

    r6 = suite_reports.get("eng_uf6", {})
    if "summary" in r6:
        s6 = r6["summary"]
        if "eq_300K_se_deg" in s6:
            derived["engine_uf6_eq_se_deg"] = (
                round(float(s6["eq_300K_se_deg"]), 3),
                "uf6_langevin_and_tolerances",
                "BEM_Langevin_Patch_Roughness_Tolerance_Suite6",
            )
        if "eq_300K_equipartition_th" in s6:
            derived["engine_uf6_eq_equipartition_th"] = (
                round(float(s6["eq_300K_equipartition_th"]), 3),
                "uf6_langevin_and_tolerances",
                "BEM_Langevin_Patch_Roughness_Tolerance_Suite6",
            )
        if "config_b_vo2_300K_peclet" in s6:
            derived["engine_uf6_cfg_b_vo2_peclet"] = (
                round(float(s6["config_b_vo2_300K_peclet"]), 2),
                "uf6_langevin_and_tolerances",
                "BEM_Langevin_Patch_Roughness_Tolerance_Suite6",
            )
        if "config_d_si_77K_mean_deg" in s6:
            derived["engine_uf6_cfg_d_si_77k_deg"] = (
                round(float(s6["config_d_si_77K_mean_deg"]), 1),
                "uf6_langevin_and_tolerances",
                "BEM_Langevin_Patch_Roughness_Tolerance_Suite6",
            )

    return derived


def aggregate_campaigns(
    *,
    uf_results_dir: Path = UF_RESULTS_DIR,
    engine_figures_dir: Path = ENGINE_FIGURES_DIR,
    base_metrics_path: Path = ENGINE_DIR / "results" / "provenance_metrics.json",
    paper_dir: Path = PAPER_DIR,
    check_only: bool = False,
    cluster_safe: bool = False,
    require_extended: bool = False,
) -> dict[str, Any]:
    missing: list[str] = []
    macro_blocks: list[str] = []
    suite_manifests: list[dict[str, Any]] = []
    suite_reports: dict[str, dict[str, Any]] = {}
    included_fig_stems: list[str] = []

    suite_specs: list[tuple[tuple[str, str, str, str, str], bool]] = [
        (spec, True) for spec in REQUIRED_SUITES
    ] + [(spec, require_extended) for spec in EXTENDED_SUITES]

    for (suite_id, rep_name, met_name, mac_name, fig_stem), is_req in suite_specs:
        rep_path = uf_results_dir / rep_name
        met_path = uf_results_dir / met_name
        mac_path = uf_results_dir / mac_name
        if not rep_path.is_file():
            if is_req:
                missing.append(f"{suite_id}: missing {rep_path}")
            continue
        with rep_path.open("r", encoding="utf-8") as fh:
            rep = json.load(fh)
        if rep.get("time_truncated", False) or rep.get("status") != "completed":
            if is_req:
                missing.append(f"{suite_id}: incomplete or time-truncated ({rep.get('status')})")
            continue
        if not met_path.is_file() or not mac_path.is_file():
            if is_req:
                missing.append(f"{suite_id}: missing provenance/macros ({met_path.name} / {mac_path.name})")
            continue
        figs_ok = all(
            (engine_figures_dir / f"{fig_stem}{ext}").is_file()
            and (engine_figures_dir / f"{fig_stem}{ext}.provenance.json").is_file()
            for ext in (".png", ".pdf")
        )
        if not figs_ok:
            if is_req:
                missing.append(f"{suite_id}: missing figure/sidecar {fig_stem}")
            continue

        suite_reports[suite_id] = rep
        with met_path.open("r", encoding="utf-8") as fh:
            suite_manifests.append(json.load(fh))
        macro_blocks.append(
            f"% --- {suite_id} Ultra-Fine Campaign Macros ---\n"
            + mac_path.read_text(encoding="utf-8").strip()
        )
        included_fig_stems.append(fig_stem)

    if missing:
        return {"ready": False, "missing": missing}

    if check_only:
        return {"ready": True, "missing": []}

    # Merge baseline + UF1..UF4 provenance manifests
    if base_metrics_path.is_file():
        with base_metrics_path.open("r", encoding="utf-8") as fh:
            merged_manifest: dict[str, Any] = json.load(fh)
    else:
        merged_manifest = {"run_metadata": {}, "intermediate_steps": {}, "metrics": {}}
    merged_manifest.setdefault("run_metadata", {})
    merged_manifest.setdefault("intermediate_steps", {})
    merged_manifest.setdefault("metrics", {})

    existing_runs = merged_manifest["run_metadata"].setdefault("solver_runs", [])
    seen_runs = {json.dumps(r, sort_keys=True) for r in existing_runs if isinstance(r, dict)}
    for sm in suite_manifests:
        merged_manifest["intermediate_steps"].update(sm.get("intermediate_steps", {}))
        merged_manifest["metrics"].update(sm.get("metrics", {}))
        runs = sm.get("run_metadata", {}).get("solver_runs", [])
        if isinstance(runs, list):
            for r in runs:
                sig = json.dumps(r, sort_keys=True) if isinstance(r, dict) else str(r)
                if sig not in seen_runs:
                    seen_runs.add(sig)
                    existing_runs.append(r)

    paper_macros = paper_dir / "macros_results.tex"
    base_text = paper_macros.read_text(encoding="utf-8") if paper_macros.is_file() else ""
    marker = "% === BEGIN ULTRAFINE CAMPAIGN MACROS ==="
    if marker in base_text:
        base_text = base_text.split(marker)[0].rstrip() + "\n"

    emitted_macro_names = set(
        re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", base_text + "\n" + "\n".join(macro_blocks))
    )

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    derived = _extract_derived_suite_metrics(suite_reports)
    derived_lines: list[str] = []
    for m_key, (m_val, step_id, solver_name) in sorted(derived.items()):
        macro_name = _sanitize_macro_name(m_key)
        if macro_name in emitted_macro_names:
            continue
        emitted_macro_names.add(macro_name)
        merged_manifest["metrics"][m_key] = {
            "value": m_val,
            "source_file": "fractal_casimir_engine/aggregate_ultrafine_campaigns.py",
            "source_function": "_extract_derived_suite_metrics",
            "line_number": 99,
            "step_id": step_id,
            "recorded_at": now_iso,
            "solver": solver_name,
            "solver_parameters": {},
        }
        derived_lines.append(f"\\newcommand{{\\{macro_name}}}{{{_format_macro_val(m_val)}}}")
    if derived_lines:
        macro_blocks.append(
            "% --- Derived Multi-Suite Manuscript Macros ---\n" + "\n".join(derived_lines)
        )

    merged_manifest["run_metadata"]["updated_at"] = now_iso

    combined_uf_metrics = uf_results_dir / "uf_combined_provenance_metrics.json"
    atomic_write_json(combined_uf_metrics, merged_manifest)

    merged_macros = (
        base_text.rstrip()
        + "\n\n"
        + marker
        + "\n"
        + "\n\n".join(macro_blocks)
        + "\n% === END ULTRAFINE CAMPAIGN MACROS ===\n"
    )
    uf_macros_copy = uf_results_dir / "merged_macros_results.tex"
    uf_macros_copy.parent.mkdir(parents=True, exist_ok=True)
    uf_macros_copy.write_text(merged_macros, encoding="utf-8")

    paper_figures_dir = paper_dir / "figures"
    tex_path = paper_dir / "fractal_casimir_engine.tex"

    if cluster_safe:
        # On shared Lustre cluster nodes, write strictly under uf_results_dir without mutating Papers/
        map_out = uf_results_dir / "merged_manuscript_provenance_map.json"
        ledger = generate_manuscript_map(
            manuscript_path=str(tex_path),
            output_map_path=str(map_out),
            metrics_path=str(combined_uf_metrics),
            figures_dir=str(paper_figures_dir),
        )
        return {"ready": True, "cluster_safe": True, "ledger": ledger, "map_path": str(map_out)}

    if "designs" in suite_reports.get("eng_uf3", {}):
        from fractal_casimir_engine.run_ultrafine_active_switching import generate_uf3_figure

        uf3_rep_path = uf_results_dir / "uf3_active_switching_report.json"
        generate_uf3_figure(
            suite_reports["eng_uf3"],
            engine_figures_dir / "fig_uf3_active_switching.png",
            engine_figures_dir / "fig_uf3_active_switching.pdf",
            uf3_rep_path,
            {"n_r": 3, "n_phi_tooth": 6, "n_phi_arc": 18, "n_z": 3, "n_xi": 24, "quad_order": 3},
        )

    paper_figures_dir.mkdir(parents=True, exist_ok=True)
    for fig_stem in included_fig_stems:
        stem_sidecar = engine_figures_dir / f"{fig_stem}.provenance.json"
        if stem_sidecar.is_file():
            shutil.copy2(stem_sidecar, paper_figures_dir / stem_sidecar.name)
        for ext in (".png", ".pdf"):
            for suffix in ("", ".provenance.json"):
                src = engine_figures_dir / f"{fig_stem}{ext}{suffix}"
                dst = paper_figures_dir / f"{fig_stem}{ext}{suffix}"
                shutil.copy2(src, dst)

    atomic_write_json(base_metrics_path, merged_manifest)
    paper_macros.write_text(merged_macros, encoding="utf-8")

    map_out = paper_dir / "manuscript_provenance_map.json"
    ledger = generate_manuscript_map(
        manuscript_path=str(tex_path),
        output_map_path=str(map_out),
        metrics_path=str(base_metrics_path),
        figures_dir=str(paper_figures_dir),
    )
    if ledger.get("audit_status") != "PASS":
        raise RuntimeError(f"Manuscript provenance audit did not PASS: {ledger}")
    return {
        "ready": True,
        "cluster_safe": False,
        "included_suites": sorted(suite_reports.keys()),
        "ledger": ledger,
        "map_path": str(map_out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report completion status of suites without mutating manuscript files.",
    )
    parser.add_argument(
        "--cluster-safe",
        action="store_true",
        help="Write merged artifacts strictly into results/ultrafine without touching Papers/.",
    )
    parser.add_argument(
        "--require-extended",
        action="store_true",
        help="Require eng_uf5 and eng_uf6 in addition to eng_uf1..eng_uf4.",
    )
    args = parser.parse_args(argv)
    res = aggregate_campaigns(
        check_only=args.check_only,
        cluster_safe=args.cluster_safe,
        require_extended=args.require_extended,
    )
    if not res["ready"]:
        for item in res["missing"]:
            print(f"[PENDING] {item}", file=sys.stderr)
        return 1
    if args.check_only:
        print("[READY] All requested Ultra-Fine suites completed and verified.")
    else:
        print(f"[AGGREGATED] Provenance map ready -> {res['map_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
