#!/usr/bin/env python3
"""
Unified 3D Conformal-Recursive Polar Cantor Fractal: 2^3 Factorial Ablation,
Matched Controls (Uniform, Monotonic/Linear, Shuffled, Out-of-Phase) &
Multi-Dimensional (kappa_r, kappa_theta, kappa_z) Log-Periodic Study.

All geometry parameters, lab-minimum feature bounds, recursive (r, theta, z)
Cantor subdivision rules, matched control constructors, and 3D BEM evaluation
engines are imported from dedicated architecture modules:
  - execution/clutch_geometry_redesign.py
  - execution/multiscale_3d_fractal_architecture.py
"""

from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "8")
os.environ.setdefault("MKL_NUM_THREADS", "8")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "8")

import argparse
import dataclasses
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import execution.casimir_bem_solver as _bem_mod
import execution.clutch_geometry_redesign as _geom_mod
import execution.multiscale_3d_fractal_architecture as _arch_mod
from execution.clutch_geometry_redesign import (
    DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM as LINEAR_CANTOR_WIDTHS_NM,
    DEFAULT_N3_CONFORMAL_SLOT_WIDTHS_NM as CONFORMAL_CANTOR_WIDTHS_NM,
    DEFAULT_N3_ISO_AREA_TARGET_UM2 as ISO_AREA_TARGET_UM2,
    DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM as MONOTONIC_WIDTHS_NM,
    DEFAULT_N3_UNIFORM_SLOT_WIDTHS_NM as UNIFORM_WIDTHS_NM,
    DEFAULT_Z_PAD_TOP_UM,
)
from execution.multiscale_3d_fractal_architecture import (
    DEFAULT_BEM_QUADRATURE_ORDER,
    DEFAULT_DISENGAGED_THETA_DEG,
    SlotSpec3D,
    SubTooth3D,
    Unified3DDesign,
    active_area_unified,
    build_all_study_designs,
    build_matched_controls_for_most_fractal,
    build_unified_sector_mesh,
    compute_factorial_effects,
    compute_log_periodic_modulation,
    evaluate_unified_3d_bem,
    make_factorial_design,
)
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)


def _safe_div(num: float, den: float) -> float:
    """Divide `num` by `den` guarding against zero denominator while preserving sign."""
    return float(num) / math.copysign(max(abs(float(den)), 1e-12), float(den))


def _round_floats(obj: Any, ndigits: int = 12) -> Any:
    """Recursively round floats so cross-platform (Linux vs Windows) 1e-16 ULP differences produce identical hashes."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def _compute_design_hash(des: Unified3DDesign) -> str:
    """Compute deterministic cross-platform SHA-256 fingerprint of a Unified3DDesign geometry."""
    payload = json.dumps(_round_floats(dataclasses.asdict(des), 12), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _compute_full_code_hash() -> str:
    """Compute combined SHA-256 hash across the imported solver/geometry/architecture modules."""
    h = hashlib.sha256()
    for mod in (_arch_mod, _geom_mod, _bem_mod):
        h.update(inspect.getsource(mod).encode("utf-8"))
    return h.hexdigest()[:16]


def _perturb_unified_design_corner_rounding(des: Unified3DDesign, r_edge_nm: float) -> Unified3DDesign:
    """Apply physical EBL corner-fillet flat-face width reduction delta_w = -2*(1 - pi/4)*r_edge to all sub-teeth."""
    r_edge_um = float(r_edge_nm) * 1e-3
    if r_edge_um <= 0.0:
        return des
    delta_w_um = -2.0 * (1.0 - math.pi / 4.0) * r_edge_um
    new_slots: list[SlotSpec3D] = []
    for s in des.slots:
        new_subteeth: list[SubTooth3D] = []
        for st in s.sub_teeth:
            c_r = 0.5 * (st.r_tooth_in + st.r_tooth_out)
            w_r = max((st.r_tooth_out - st.r_tooth_in) + delta_w_um, 0.005)
            new_subteeth.append(
                dataclasses.replace(
                    st,
                    r_tooth_in=c_r - 0.5 * w_r,
                    r_tooth_out=c_r + 0.5 * w_r,
                )
            )
        new_slots.append(dataclasses.replace(s, sub_teeth=tuple(new_subteeth)))
    return dataclasses.replace(des, slots=tuple(new_slots))


def build_exact_b3_scaling_variants(f3_base: Unified3DDesign) -> list[Unified3DDesign]:
    """Construct four exact b=3 angular and axial scaling variants to test the 3D mechanism
    against the heuristic F3_111 geometry, phase permutations, and non-fractal controls."""
    def _make_variant(
        code: str,
        name: str,
        h_by_lvl_nm: Mapping[int, float],
        lobe_arc_by_lvl_deg: Mapping[int, float],
        gap_arc_by_lvl_deg: Mapping[int, float],
    ) -> Unified3DDesign:
        new_slots: list[SlotSpec3D] = []
        for s in f3_base.slots:
            lvl = int(s.level)
            ht = float(h_by_lvl_nm[lvl]) * 1e-3
            zt = -ht
            l_arc = float(lobe_arc_by_lvl_deg[lvl])
            g_arc = float(gap_arc_by_lvl_deg[lvl])
            off = 0.5 * (g_arc + l_arc)
            phis = ((-off, l_arc), (off, l_arc))
            new_sub = tuple(
                dataclasses.replace(st, z_tip=zt, h_teeth=ht, phi_offsets_deg=phis)
                for st in s.sub_teeth
            )
            new_slots.append(dataclasses.replace(s, sub_teeth=new_sub))
        return dataclasses.replace(
            f3_base,
            code=code,
            name=name,
            family_role="exact_b3_variant",
            slots=tuple(new_slots),
        )

    lobe_iso = {1: 28.0 / 3.0, 2: 28.0 / 3.0, 3: 28.0 / 3.0}
    gap_const = {1: 28.0 / 3.0, 2: 28.0 / 3.0, 3: 28.0 / 3.0}
    gap_b3 = {1: 28.0 / 3.0, 2: 28.0 / 9.0, 3: 28.0 / 27.0}
    h_heur = {1: 90.0, 2: 80.0, 3: 70.0}
    h_step_b3 = {1: 100.0 - 30.0 / 9.0, 2: 100.0 - 30.0 / 3.0, 3: 100.0 - 30.0}
    lobe_strict_b3 = {1: 28.0 / 3.0, 2: 28.0 / 9.0, 3: 28.0 / 27.0}
    h_padgap_b3 = {1: 105.0, 2: 85.0, 3: 25.0}

    return [
        _make_variant("F3_ExactZ_StepB3", "Cantor_111_ExactZ_StepB3", h_step_b3, lobe_iso, gap_const),
        _make_variant("F3_ExactTheta_GapB3", "Cantor_111_ExactTheta_GapB3", h_heur, lobe_iso, gap_b3),
        _make_variant("F3_Exact3D_IsoB3", "Cantor_111_Exact3D_IsoB3", h_step_b3, lobe_iso, gap_b3),
        _make_variant("F3_StrictB3_Uniso", "Cantor_111_StrictB3_Uniso", h_padgap_b3, lobe_strict_b3, gap_b3),
    ]


def compute_3d_geometric_descriptors(des: Unified3DDesign) -> dict[str, float]:
    """Compute exact 3D geometric descriptors across all 4 C4 sectors:
    active top-face area A_tooth, horizontal edge perimeter P_edge, radial-facing and
    azimuthal-facing vertical sidewall areas (A_sidewall_r, A_sidewall_theta, A_sidewall),
    active tooth metal volume V_tooth, minimum and harmonic-mean radial clearance (g_r_min_nm,
    g_r_harm_nm), axial landing-pad clearances (d_pad_min_nm, d_pad_mean_nm), and the
    near-field sidewall-to-gap coupling integral sum(A_wall_r / g_r)."""
    n_sec = float(_arch_mod.DEFAULT_NUM_SECTORS)
    a_tooth = 0.0
    p_edge = 0.0
    a_sw_r = 0.0
    a_sw_t = 0.0
    vol = 0.0
    g_inv_weighted = 0.0
    g_min_um = math.inf
    d_pad_min_um = math.inf
    d_pad_area_weighted = 0.0

    for s in des.slots:
        subslots = s.stator_subslots or ((s.r_inner, s.r_outer),)
        n_st = len(s.sub_teeth)
        for idx_st, st in enumerate(s.sub_teeth):
            rc = 0.5 * (st.r_tooth_in + st.r_tooth_out)
            w = st.r_tooth_out - st.r_tooth_in
            h = st.h_teeth
            d_pad = st.z_tip - des.z_pad_top
            if d_pad <= 0.0:
                raise ValueError(f"Nonpositive axial pad clearance d_pad={d_pad} in design {des.code}")
            d_pad_min_um = min(d_pad_min_um, d_pad)
            if len(subslots) == n_st:
                sub_in, sub_out = subslots[idx_st]
                g_in = st.r_tooth_in - sub_in
                g_out = sub_out - st.r_tooth_out
            else:
                g_in = (
                    (st.r_tooth_in - s.r_inner)
                    if idx_st == 0
                    else (st.r_tooth_in - s.sub_teeth[idx_st - 1].r_tooth_out)
                )
                g_out = (
                    (s.r_outer - st.r_tooth_out)
                    if idx_st == n_st - 1
                    else (s.sub_teeth[idx_st + 1].r_tooth_in - st.r_tooth_out)
                )
            if g_in <= 0.0 or g_out <= 0.0:
                raise ValueError(
                    f"Nonpositive radial clearance (g_in={g_in}, g_out={g_out}) in design {des.code}"
                )
            g_min_um = min(g_min_um, g_in, g_out)
            for _, arc_deg in st.phi_offsets_deg:
                rad = math.radians(arc_deg)
                lobe_a = n_sec * rad * rc * w
                a_tooth += lobe_a
                d_pad_area_weighted += lobe_a * d_pad
                p_edge += n_sec * (rad * (st.r_tooth_in + st.r_tooth_out) + 2.0 * w)
                sw_r_in = n_sec * rad * st.r_tooth_in * h
                sw_r_out = n_sec * rad * st.r_tooth_out * h
                a_sw_r += sw_r_in + sw_r_out
                a_sw_t += n_sec * 2.0 * w * h
                vol += lobe_a * h
                g_inv_weighted += (sw_r_in / g_in) + (sw_r_out / g_out)

    if a_tooth <= 0.0 or not (math.isfinite(g_min_um) and math.isfinite(d_pad_min_um)):
        raise ValueError(f"Design {des.code} has no active teeth or non-finite clearances")
    a_sw = a_sw_r + a_sw_t
    g_harm_nm = 1000.0 * _safe_div(a_sw_r, g_inv_weighted)
    return {
        "A_tooth_um2": float(a_tooth),
        "P_edge_um": float(p_edge),
        "A_sidewall_r_um2": float(a_sw_r),
        "A_sidewall_theta_um2": float(a_sw_t),
        "A_sidewall_um2": float(a_sw),
        "V_tooth_um3": float(vol),
        "g_r_min_nm": float(1000.0 * g_min_um),
        "g_r_harm_nm": float(g_harm_nm),
        "d_pad_min_nm": float(1000.0 * d_pad_min_um),
        "d_pad_mean_nm": float(1000.0 * _safe_div(d_pad_area_weighted, a_tooth)),
        "sidewall_over_gap_um": float(g_inv_weighted),
    }


def enrich_record_with_geometry(rec: dict[str, Any], des: Unified3DDesign) -> dict[str, Any]:
    """Attach exact 3D geometric descriptors and perimeter/sidewall/volume force densities to a BEM record."""
    geom = compute_3d_geometric_descriptors(des)
    fz = float(rec["F_z_pN"])
    rec.update(geom)
    rec["F_per_A_pN_per_um2"] = _safe_div(fz, geom["A_tooth_um2"])
    rec["F_per_P_pN_per_um"] = _safe_div(fz, geom["P_edge_um"])
    rec["F_per_Asw_pN_per_um2"] = _safe_div(fz, geom["A_sidewall_um2"])
    rec["F_per_Asw_r_pN_per_um2"] = _safe_div(fz, geom["A_sidewall_r_um2"])
    rec["F_per_V_pN_per_um3"] = _safe_div(fz, geom["V_tooth_um3"])
    return rec


def compute_extended_factorial_contrasts(by_code: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Compute both baseline-referenced Boolean-cube (Mobius) interaction contrasts and
    standard Yates/ANOVA scaled main and interaction effects across the 2^3 factorial cube."""
    base_eff = dict(compute_factorial_effects(by_code))
    if not base_eff:
        return {}
    f000 = float(by_code["F0_000"]["F_z_pN"])
    f111 = float(by_code["F3_111"]["F_z_pN"])
    sr = float(base_eff["single_effect_r_pN"])
    st = float(base_eff["single_effect_theta_pN"])
    sz = float(base_eff["single_effect_z_pN"])
    irt = float(base_eff["synergy_r_theta_pN"])
    irz = float(base_eff["synergy_r_z_pN"])
    itz = float(base_eff["synergy_theta_z_pN"])
    irtz = float(base_eff["synergy_3way_r_theta_z_pN"])
    lin_sum = f000 + sr + st + sz
    pair_sum = irt + irz + itz
    super_exc = f111 - lin_sum
    base_eff.update({
        "linear_additive_sum_pN": lin_sum,
        "pairwise_synergy_sum_pN": pair_sum,
        "superadditive_excess_pN": super_exc,
        "superadditive_excess_pct": 100.0 * _safe_div(super_exc, lin_sum),
        "anova_interaction_r_theta_pN": 0.5 * irt + 0.25 * irtz,
        "anova_interaction_r_z_pN": 0.5 * irz + 0.25 * irtz,
        "anova_interaction_theta_z_pN": 0.5 * itz + 0.25 * irtz,
        "anova_interaction_3way_pN": 0.25 * irtz,
    })
    return base_eff


def fit_multi_feature_geometric_model(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fit ordinary least-squares geometric scaling models predicting F_z(3 deg) from
    horizontal edge perimeter P_edge, vertical sidewall area A_sidewall, tooth volume V_tooth,
    and radial sidewall-to-gap coupling integral sum(A_wall_r / g_r)."""
    if len(records) <= 5:
        raise ValueError("fit_multi_feature_geometric_model requires at least 6 observations for 5 OLS parameters")
    y = np.asarray([float(r["F_z_pN"]) for r in records], dtype=np.float64)
    p_arr = np.asarray([float(r["P_edge_um"]) for r in records], dtype=np.float64)
    asw_arr = np.asarray([float(r["A_sidewall_um2"]) for r in records], dtype=np.float64)
    v_arr = np.asarray([float(r["V_tooth_um3"]) for r in records], dtype=np.float64)
    sg_arr = np.asarray([float(r["sidewall_over_gap_um"]) for r in records], dtype=np.float64)

    X_full = np.column_stack([np.ones_like(y), p_arr, asw_arr, v_arr, sg_arr])
    beta_full, _, _, _ = np.linalg.lstsq(X_full, y, rcond=None)
    y_pred_full = X_full @ beta_full
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    ss_res_full = float(np.sum((y - y_pred_full) ** 2))
    r2_full = 1.0 - _safe_div(ss_res_full, ss_tot)
    n_obs = len(y)
    r2_adj_full = 1.0 - (1.0 - r2_full) * float(n_obs - 1) / float(n_obs - 5)
    mae_full = float(np.mean(np.abs(y - y_pred_full)))
    rmse_full = float(math.sqrt(ss_res_full / float(n_obs)))

    X_psw = np.column_stack([np.ones_like(y), p_arr, asw_arr, v_arr])
    beta_psw, _, _, _ = np.linalg.lstsq(X_psw, y, rcond=None)
    y_pred_psw = X_psw @ beta_psw
    ss_res_psw = float(np.sum((y - y_pred_psw) ** 2))
    r2_psw = 1.0 - _safe_div(ss_res_psw, ss_tot)

    by_code_pred = {
        str(r["code"]): {
            "F_z_actual_pN": float(r["F_z_pN"]),
            "F_z_pred_full_pN": float(yp_f),
            "residual_full_pN": float(r["F_z_pN"] - yp_f),
            "F_z_pred_psw_pN": float(yp_p),
            "residual_psw_pN": float(r["F_z_pN"] - yp_p),
        }
        for r, yp_f, yp_p in zip(records, y_pred_full, y_pred_psw)
    }
    return {
        "n_designs": int(n_obs),
        "r2_full_p_asw_v_gap": float(r2_full),
        "r2_adj_full_p_asw_v_gap": float(r2_adj_full),
        "mae_full_pN": float(mae_full),
        "rmse_full_pN": float(rmse_full),
        "r2_perimeter_sidewall_volume": float(r2_psw),
        "beta_full": {
            "intercept_pN": float(beta_full[0]),
            "beta_P_edge_pN_per_um": float(beta_full[1]),
            "beta_A_sidewall_pN_per_um2": float(beta_full[2]),
            "beta_V_tooth_pN_per_um3": float(beta_full[3]),
            "beta_sidewall_over_gap_pN_per_um": float(beta_full[4]),
        },
        "predictions_by_code": by_code_pred,
    }


def build_phase_permutation_variants(f3_base: Unified3DDesign) -> list[Unified3DDesign]:
    """Construct all 5 non-identity (theta, z) generation permutations on the F3_111 radial Cantor
    12-sub-slot backbone (P_perm132..P_perm321) and all 6 generation permutations on the 12-equal-sub-slot
    control backbone (C10_perm123..C10_perm321)."""
    import itertools

    target_a = active_area_unified(f3_base)
    primary_sub_counts = tuple(max(1, len(s.stator_subslots)) for s in f3_base.slots)
    variants: list[Unified3DDesign] = []

    for perm in itertools.permutations([1, 2, 3]):
        p_map = {1: perm[0], 2: perm[1], 3: perm[2]}
        levels = tuple(p_map[g] for g in _arch_mod.DEFAULT_N3_CANTOR_GENERATIONS)
        p_str = f"{perm[0]}{perm[1]}{perm[2]}"
        if perm != (1, 2, 3):
            raw_p = _arch_mod.build_design_from_slot_sequence(
                name=f"Cantor_111_PhasePerm_{p_str}",
                code=f"P_perm{p_str}",
                family_role="cantor_phase_perm",
                slot_widths_nm=_arch_mod.DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM,
                slot_levels=levels,
                u_r=True,
                u_theta=True,
                u_z=True,
                enable_stator_subribs=True,
                iso_area=False,
            )
            variants.append(
                _arch_mod.scale_design_angles_to_iso_area(
                    raw_p, target_a, _arch_mod.DEFAULT_N3_MAX_TOOTH_ARC_DEG, area_tol_um2=0.05
                )
            )
        des_c10 = _arch_mod.build_equal_subdivided_design(
            name=f"Ctrl_EqualSub12_PhasePerm_{p_str}",
            code=f"C10_perm{p_str}",
            family_role="ctrl_c10_phase_perm",
            slot_widths_nm=_arch_mod.DEFAULT_N3_CANTOR_SLOT_WIDTHS_NM,
            slot_levels=levels,
            sub_counts=primary_sub_counts,
            u_theta=True,
            u_z=True,
            iso_area=True,
        )
        variants.append(des_c10)
    return variants


def build_matched_and_optimized_controls(f3_base: Unified3DDesign) -> list[Unified3DDesign]:
    """Construct fabrication-optimized and exact clearance/perimeter/sidewall/volume-matched
    12-tooth non-fractal controls under the same fabrication constraints:
      - M4_OptMaxHZ12: Monotonic 12-equal-sub-slot control with all sub-teeth optimized to maximum
        permitted height H=90 nm (d_pad=25 nm) and maximum envelope (28 deg) at A_tooth=0.3104 um^2.
      - M4_OptMaxHZ12_IsoF3: Same at exact F3_111 area A_tooth=0.3049 um^2.
      - M1_Uni12_g15: 12 uniform 50 nm slots (w_t=20 nm, g_r=15 nm) uniformly spaced across R in [0.30, 1.65] um,
        matching F3_111 in A_tooth=0.3049 um^2, P_edge=34.33 um, A_sidewall=2.7468 um^2, V_tooth=0.02440 um^3, g_r=15 nm.
      - M2_Mono12_g15: Monotonic 7-band / 12-trench control with 50 nm trenches (w_t=20 nm, g_r=15 nm).
      - M3_Shuf12_g15: Shuffled 7-band / 12-trench control with 50 nm trenches (w_t=20 nm, g_r=15 nm).
    """
    target_a = active_area_unified(f3_base)
    primary_sub_counts = tuple(max(1, len(s.stator_subslots)) for s in f3_base.slots)
    mono_sub_counts = tuple(sorted(primary_sub_counts))

    m4_nom = _arch_mod.build_equal_subdivided_design(
        name="Ctrl_Mono12_OptMaxHZ_NomArea",
        code="M4_OptMaxHZ12",
        family_role="ctrl_opt_max_hz",
        slot_widths_nm=_arch_mod.DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM,
        slot_levels=(1,) * len(_arch_mod.DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM),
        sub_counts=mono_sub_counts,
        u_theta=True,
        u_z=True,
        iso_area=True,
    )
    m4_iso = _arch_mod.scale_design_angles_to_iso_area(
        m4_nom, target_a, _arch_mod.DEFAULT_N3_MAX_TOOTH_ARC_DEG, area_tol_um2=0.05
    )
    m4_iso = dataclasses.replace(m4_iso, name="Ctrl_Mono12_OptMaxHZ_IsoF3", code="M4_OptMaxHZ12_IsoF3")

    m1_raw = _arch_mod.build_design_from_slot_sequence(
        name="Ctrl_Uni12_MatchedG15_IsoF3",
        code="M1_Uni12_g15",
        family_role="ctrl_matched_g15",
        slot_widths_nm=(50.0,) * 12,
        slot_levels=(2,) * 12,
        u_r=True,
        u_theta=True,
        u_z=True,
        enable_stator_subribs=True,
        iso_area=False,
    )
    m1 = _arch_mod.scale_design_angles_to_iso_area(
        m1_raw, target_a, _arch_mod.DEFAULT_N3_MAX_TOOTH_ARC_DEG, area_tol_um2=0.05
    )

    m2_raw = _arch_mod.build_design_from_slot_sequence(
        name="Ctrl_Mono12_MatchedG15_IsoF3",
        code="M2_Mono12_g15",
        family_role="ctrl_matched_g15",
        slot_widths_nm=_arch_mod.DEFAULT_N3_MONOTONIC_SLOT_WIDTHS_NM,
        slot_levels=_arch_mod.DEFAULT_N3_MONOTONIC_GENERATIONS,
        u_r=True,
        u_theta=True,
        u_z=True,
        enable_stator_subribs=True,
        iso_area=False,
    )
    m2 = _arch_mod.scale_design_angles_to_iso_area(
        m2_raw, target_a, _arch_mod.DEFAULT_N3_MAX_TOOTH_ARC_DEG, area_tol_um2=0.05
    )

    rng = np.random.default_rng(_arch_mod.DEFAULT_SHUFFLE_SEED)
    perm_w = list(rng.permutation(len(f3_base.slots)))
    perm_g = list(rng.permutation(len(f3_base.slots)))
    shuf_w = tuple((f3_base.slots[i].r_outer - f3_base.slots[i].r_inner) * 1000.0 for i in perm_w)
    shuf_l = tuple(f3_base.slots[i].level for i in perm_g)
    m3_raw = _arch_mod.build_design_from_slot_sequence(
        name="Ctrl_Shuf12_MatchedG15_IsoF3",
        code="M3_Shuf12_g15",
        family_role="ctrl_matched_g15",
        slot_widths_nm=shuf_w,
        slot_levels=shuf_l,
        u_r=True,
        u_theta=True,
        u_z=True,
        enable_stator_subribs=True,
        iso_area=False,
    )
    m3 = _arch_mod.scale_design_angles_to_iso_area(
        m3_raw, target_a, _arch_mod.DEFAULT_N3_MAX_TOOTH_ARC_DEG, area_tol_um2=0.05
    )

    return [m4_nom, m4_iso, m1, m2, m3]



_LAST_STATOR_CACHE: dict[str, Any] = {}


def evaluate_unified_r5nm_bem(
    des: Unified3DDesign,
    r_edge_nm: float = 5.0,
    theta_deg: float = DEFAULT_DISENGAGED_THETA_DEG,
    n_xi: int = DEFAULT_BEM_QUADRATURE_ORDER,
    num_threads: int = 8,
) -> dict[str, Any]:
    """Evaluate a Unified3DDesign under r_edge corner-rounding regularization (or sharp edges when r_edge_nm=0.0)
    with real-block C4 symmetry and automatic stator LU caching across shared stator geometries."""
    import time
    import torch

    torch.set_num_threads(max(1, int(num_threads)))
    t0 = time.perf_counter()
    r_edge_um = float(r_edge_nm) * 1e-3
    mod_des = _perturb_unified_design_corner_rounding(des, r_edge_nm)
    a_corner_um2 = math.pi * ((2.0 * r_edge_um) ** 2) if r_edge_um > 0.0 else 0.0

    mesh, panel_slot_ids = build_unified_sector_mesh(mod_des, theta_deg=theta_deg)
    rotor = mesh.sector_arrays("rotor")
    stator = mesh.sector_arrays("stator")
    material = _arch_mod.MaterialModel.from_parameters(mesh.parameters)
    dof_slot_ids = np.repeat(panel_slot_ids, 2)

    n_sectors = _arch_mod.DEFAULT_NUM_SECTORS
    char_gap_um = math.inf
    for sector in range(n_sectors):
        sp = stator.centroids @ _arch_mod._rotation(sector).T
        for c in rotor.centroids:
            char_gap_um = min(char_gap_um, float(np.min(np.linalg.norm(sp - c, axis=1))))
    k_eff = 1.0 / max(char_gap_um, _arch_mod.DEFAULT_MIN_TOOTH_W_UM)
    kappa_0 = 1.0 / _arch_mod.DEFAULT_H_TEETH_ROTATIONAL_UM
    kappas, weights, _ = _arch_mod._quadrature(n_xi, kappa_0)
    K = len(kappas)

    stator_key = (
        int(n_xi),
        round(float(r_edge_nm), 6),
        round(float(mod_des.R_min), 12),
        round(float(mod_des.R_max), 12),
        round(float(mod_des.aperture_arc_deg), 12),
        round(float(mod_des.t_membrane), 12),
        round(float(mod_des.t_landing_pad), 12),
        round(float(mod_des.z_pad_top), 12),
        tuple(
            (
                round(float(s.r_inner), 12),
                round(float(s.r_outer), 12),
                tuple((round(float(a), 12), round(float(b), 12)) for a, b in (s.stator_subslots or ())),
            )
            for s in mod_des.slots
        ),
    )

    def same_sec_blocks(body: Any) -> np.ndarray:
        N = body.count
        sub_var = torch.from_numpy((body.areas[:, None] + body.areas[None, :]) / (32.0 * math.pi))
        area_scale = torch.from_numpy(np.sqrt(body.areas[:, None]) * np.sqrt(body.areas[None, :]) / (4.0 * math.pi))
        kap_t = torch.from_numpy(kappas)
        sec_blocks = np.zeros((n_sectors, K, 2 * N, 2 * N), dtype=np.float64)
        for sec in range(n_sectors):
            rot = _arch_mod._rotation(sec)
            src_pts = body.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, body.tangents)
            t_dot_t = torch.from_numpy(np.einsum("ima,jna->ijmn", body.tangents, src_tan, optimize=True))
            ker_sum = torch.zeros((K, N, N), dtype=torch.float64)
            for qt in range(4):
                for qs in range(4):
                    w = float(body.quad_weights[qt] * body.quad_weights[qs])
                    delta = torch.from_numpy(body.quad_points[:, qt, None, :] - src_pts[None, :, qs, :])
                    eff_d = torch.sqrt(torch.sum(delta**2, dim=2) + sub_var)
                    scale = (area_scale * w) / eff_d
                    ker_sum += torch.exp(-kap_t[:, None, None] * eff_d[None, :, :]) * scale[None, :, :]
            single = ker_sum[:, :, :, None, None] * t_dot_t[None, :, :, :, :]
            if sec == 0:
                idx = np.arange(N)
                for q, kap in enumerate(kappas):
                    diag = torch.from_numpy(_arch_mod._disk_self_term(body.areas + a_corner_um2, float(kap)))
                    single[q, idx, idx] = diag[:, None, None] * torch.eye(2, dtype=torch.float64)
            sec_blocks[sec] = single.permute(0, 1, 3, 2, 4).reshape(K, 2 * N, 2 * N).numpy()
        return sec_blocks

    def cross_sec_blocks(target: Any, source: Any) -> tuple[np.ndarray, np.ndarray]:
        Nt, Ns = target.count, source.count
        M = Nt * Ns
        sub_var = torch.from_numpy((target.areas[:, None] + source.areas[None, :]) / (32.0 * math.pi))
        area_scale = torch.from_numpy(np.sqrt(target.areas[:, None]) * np.sqrt(source.areas[None, :]) / (4.0 * math.pi))
        qw = torch.from_numpy(target.quad_weights[:, None] * source.quad_weights[None, :]).reshape(16)
        rs_sec = np.zeros((n_sectors, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        dz_sec = np.zeros((n_sectors, K, 2 * Nt, 2 * Ns), dtype=np.float64)
        u_z = torch.from_numpy(target.tangents[:, :, 2][:, None, :, None])
        tgt_q = torch.from_numpy(target.quad_points.transpose(1, 0, 2)[:, :, None, :])
        for sec in range(n_sectors):
            rot = _arch_mod._rotation(sec)
            src_pts = source.quad_points @ rot.T
            src_tan = np.einsum("ab,jmb->jma", rot, source.tangents)
            t_dot_t = torch.from_numpy(np.einsum("ima,jna->ijmn", target.tangents, src_tan, optimize=True))
            v_z = torch.from_numpy(src_tan[:, :, 2][None, :, None, :])
            src_q = torch.from_numpy(src_pts.transpose(1, 0, 2)[None, :, :, :])
            delta = (tgt_q[:, None, :, :, :] - src_q[:, :, None, :, :]).reshape(16, Nt, Ns, 3)
            eff_d = torch.sqrt(torch.sum(delta**2, dim=3) + sub_var[None, :, :])
            inv_d = 1.0 / eff_d
            scale = (area_scale[None, :, :] * qw[:, None, None]) * inv_d
            dz_over_d = delta[:, :, :, 2] * inv_d
            u_R = torch.einsum("ima,qija->qijm", torch.from_numpy(target.tangents), delta)
            v_R = torch.einsum("jna,qija->qijn", torch.from_numpy(src_tan), delta)
            R_inv2 = (inv_d**2)[:, :, :, None, None]
            Z = delta[:, :, :, 2][:, :, :, None, None]
            D = u_R[:, :, :, :, None] * v_R[:, :, :, None, :] * R_inv2
            dD_dz = (
                (u_z[None] * v_R[:, :, :, None, :] + u_R[:, :, :, :, None] * v_z[None]) * R_inv2
                - 2.0 * Z * D * R_inv2
            )
            D_c = D.reshape(16, M, 4).permute(1, 2, 0).reshape(M, 4, 16)
            dD_c = dD_dz.reshape(16, M, 4).permute(1, 2, 0).reshape(M, 4, 16)
            eff_d_f = eff_d.reshape(16, M)
            inv_d_f = inv_d.reshape(16, M)
            scale_f = scale.reshape(16, M)
            dz_d_f = dz_over_d.reshape(16, M)
            for qk, kap_val in enumerate(kappas):
                kap = float(kap_val)
                x = kap * eff_d_f
                ker = torch.exp(-x) * scale_f
                rad_deriv = -ker * (kap + inv_d_f)
                sc_dz = rad_deriv * dz_d_f
                inv = 1.0 / (1.0 + x)
                denom = 1.0 - inv + inv**2
                c_dir = (1.0 + inv + inv**2) / denom
                dc_dir_dx = -2.0 * inv**2 * (1.0 - inv**2) / denom**2
                s_t = (0.5 * torch.sum(ker, dim=0)).reshape(Nt, Ns, 1, 1)
                dz_t = (0.5 * torch.sum(sc_dz, dim=0)).reshape(Nt, Ns, 1, 1)
                w_D = (-0.25 * ker * c_dir).T.reshape(M, 1, 16)
                w_dz_D = (-0.25 * sc_dz * c_dir - 0.25 * ker * dc_dir_dx * kap * dz_d_f).T.reshape(M, 1, 16)
                s_D = torch.sum(D_c * w_D, dim=2).reshape(Nt, Ns, 2, 2)
                dz_D = (torch.sum(D_c * w_dz_D, dim=2) + torch.sum(dD_c * w_D, dim=2)).reshape(Nt, Ns, 2, 2)
                single = s_t * t_dot_t + s_D
                dz = dz_t * t_dot_t + dz_D
                rs_sec[sec, qk] = single.permute(0, 2, 1, 3).reshape(2 * Nt, 2 * Ns).numpy()
                dz_sec[sec, qk] = dz.permute(0, 2, 1, 3).reshape(2 * Nt, 2 * Ns).numpy()
        return rs_sec, dz_sec

    rr_sec = same_sec_blocks(rotor)
    if _LAST_STATOR_CACHE.get("key") == stator_key:
        lu_s_cache: dict[tuple[int, int], tuple[Any, Any]] = _LAST_STATOR_CACHE["lu_s_cache"]
    else:
        ss_sec = same_sec_blocks(stator)
        lu_s_cache = {}
        for q in range(K):
            if float(kappas[q]) > 120.0:
                continue
            ms0 = torch.from_numpy(ss_sec[0, q] + ss_sec[1, q] + ss_sec[2, q] + ss_sec[3, q])
            ms2 = torch.from_numpy(ss_sec[0, q] - ss_sec[1, q] + ss_sec[2, q] - ss_sec[3, q])
            ms1 = torch.from_numpy((ss_sec[0, q] - ss_sec[2, q]) + 1j * (ss_sec[1, q] - ss_sec[3, q]))
            lu_s_cache[(q, 0)] = torch.linalg.lu_factor(ms0)
            lu_s_cache[(q, 2)] = torch.linalg.lu_factor(ms2)
            lu_s_cache[(q, 1)] = torch.linalg.lu_factor(ms1)
        _LAST_STATOR_CACHE.clear()
        _LAST_STATOR_CACHE["key"] = stator_key
        _LAST_STATOR_CACHE["lu_s_cache"] = lu_s_cache

    rs_sec, dz_sec = cross_sec_blocks(rotor, stator)

    dof_forces = np.zeros(2 * rotor.count, dtype=np.float64)
    for q in range(K):
        kap = float(kappas[q])
        if kap > 120.0:
            continue
        w_q = float(weights[q])
        tm, te, _ = material.channel_weights(kap, k_eff=k_eff)
        q_dof = np.zeros(2 * rotor.count, dtype=np.float64)
        for mode, mult in ((0, 1.0), (2, 1.0), (1, 2.0)):
            if mode == 0:
                mr = torch.from_numpy(rr_sec[0, q] + rr_sec[1, q] + rr_sec[2, q] + rr_sec[3, q])
                g = torch.from_numpy(rs_sec[0, q] + rs_sec[1, q] + rs_sec[2, q] + rs_sec[3, q])
                dg = torch.from_numpy(dz_sec[0, q] + dz_sec[1, q] + dz_sec[2, q] + dz_sec[3, q])
                sr, dsr = g.T.contiguous(), dg.T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.float64)
            elif mode == 2:
                mr = torch.from_numpy(rr_sec[0, q] - rr_sec[1, q] + rr_sec[2, q] - rr_sec[3, q])
                g = torch.from_numpy(rs_sec[0, q] - rs_sec[1, q] + rs_sec[2, q] - rs_sec[3, q])
                dg = torch.from_numpy(dz_sec[0, q] - dz_sec[1, q] + dz_sec[2, q] - dz_sec[3, q])
                sr, dsr = g.T.contiguous(), dg.T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.float64)
            else:
                mr = torch.from_numpy((rr_sec[0, q] - rr_sec[2, q]) + 1j * (rr_sec[1, q] - rr_sec[3, q]))
                g = torch.from_numpy((rs_sec[0, q] - rs_sec[2, q]) + 1j * (rs_sec[1, q] - rs_sec[3, q]))
                dg = torch.from_numpy((dz_sec[0, q] - dz_sec[2, q]) + 1j * (dz_sec[1, q] - dz_sec[3, q]))
                sr, dsr = g.conj().T.contiguous(), dg.conj().T.contiguous()
                eye = torch.eye(mr.shape[0], dtype=torch.complex128)
            lu_r, piv_r = torch.linalg.lu_factor(mr)
            lu_s, piv_s = lu_s_cache[(q, mode)]
            x = torch.linalg.lu_solve(lu_r, piv_r, g)
            ns_col = sr.shape[1]
            z_all = torch.linalg.lu_solve(lu_s, piv_s, torch.cat((sr, dsr), dim=1))
            z, dz = z_all[:, :ns_col], z_all[:, ns_col:]
            coupling = x @ z
            B, C = dg @ z, x @ dz
            for ch_w in (tm, te):
                pw = ch_w**2
                y = eye - pw * coupling
                lu_y, piv_y = torch.linalg.lu_factor(y)
                U = torch.linalg.lu_solve(lu_y, piv_y, C)
                V = torch.linalg.lu_solve(lu_r, piv_r, torch.linalg.lu_solve(lu_y, piv_y, B, left=False), left=False)
                per_dof = -pw * (torch.diagonal(V).real + torch.diagonal(U).real).numpy()
                q_dof += mult * (-per_dof / (2.0 * math.pi))
        dof_forces += w_q * q_dof

    f_total_pN = float(np.sum(dof_forces) * _arch_mod.MEEP_FORCE_TO_SI * 1e12)
    f_slots = [float(np.sum(dof_forces[dof_slot_ids == k]) * _arch_mod.MEEP_FORCE_TO_SI * 1e12) for k in range(len(mod_des.slots))]
    r_centers = [0.5 * (s.r_inner + s.r_outer) for s in mod_des.slots]
    f_circ_sum = float(sum(fk / (2.0 * math.pi * rk) for fk, rk in zip(f_slots, r_centers)))
    a_tot = active_area_unified(des)
    return {
        "code": des.code,
        "name": des.name,
        "r_edge_nm": float(r_edge_nm),
        "F_z_pN": f_total_pN,
        "F_circ_sum_pN_per_um": f_circ_sum,
        "F_per_A_pN_per_um2": f_total_pN / max(a_tot, 1e-12),
        "F_z_r5nm_pN": f_total_pN,
        "F_per_A_r5nm_pN_per_um2": f_total_pN / max(a_tot, 1e-12),
        "f_slots_pN": f_slots,
        "f_slots_r5nm_pN": f_slots,
        "elapsed_s": float(time.perf_counter() - t0),
    }


def render_figure(
    records: Sequence[Mapping[str, Any]],
    factorial_effects: Mapping[str, float],
    out_png: Path,
    out_pdf: Path,
) -> None:
    """Render 4-panel diagnostic figure for the 2^3 Factorial & 3D Wavenumber Log-Periodic Study."""
    by_code = {r["code"]: r for r in records}
    fig, axes = plt.subplots(2, 2, figsize=(16.5, 11.2), dpi=220)
    ax_bar, ax_slot = axes[0]
    ax_spec, ax_res = axes[1]

    order = [
        ("F0_000", "F0-000\nBaseline", "#1f77b4"),
        ("F1z_001", "F1z-001\nZ-Step Only", "#aec7e8"),
        ("F1t_010", "F1t-010\nθ-Cantor Only", "#ffbb78"),
        ("F2tz_011", "F2tz-011\nθ + Z", "#ff7f0e"),
        ("F1r_Sub", "F1r-Sub\nRotor Sub-Teeth", "#98df8a"),
        ("F1r_100", "F1r-100\nRotor+Stator", "#2ca02c"),
        ("F2rz_101", "F2rz-101\nR + Z", "#17becf"),
        ("F2rt_110", "F2rt-110\n1-Mask Planar", "#e377c2"),
        ("F3_111", "F3-111\nUnified 3D", "#d62728"),
        ("C1_Uni000", "C1-Uni000 (7T)\nUniform Flat", "#7f7f7f"),
        ("C2_Uni111", "C2-Uni111 (7T)\nUniform 111", "#c7c7c7"),
        ("C3_MonoGen", "C3-MonoGen (7T)\nMonotonic 011", "#8c564b"),
        ("C4_Shuf111", "C4-Shuf111 (7T)\nShuffled 011", "#9467bd"),
        ("C5_OutPhase", "C5-OutPhase (7T)\nOut-of-Phase", "#bcbd22"),
        ("C6_Uni12", "C6-Uni12 (12T)\nUniform 12-Slot", "#5254a3"),
        ("C7_Lin12", "C7-Lin12 (12T)\nLinear 12-Slot", "#6b6ecf"),
        ("C8_Mono12", "C8-Mono12 (12T)\nMonotonic 12-Sub", "#8ca252"),
        ("C9_Shuf12", "C9-Shuf12 (12T)\nShuffled 12-Sub", "#bd9e39"),
        ("C10_OutPhase12", "C10-OutPhase12\nOutPhase 12-Sub", "#ad494a"),
    ]
    present = [(c, lbl, col) for c, lbl, col in order if c in by_code]
    x = np.arange(len(present))
    fvals = [float(by_code[c]["F_z_pN"]) for c, _, _ in present]
    cols = [col for _, _, col in present]
    bars = ax_bar.bar(x, fvals, color=cols, edgecolor="black", linewidth=0.8)
    ax_bar.axhline(0.0, color="black", linewidth=0.8)
    if "C3_MonoGen" in by_code:
        ax_bar.axhline(
            float(by_code["C3_MonoGen"]["F_z_pN"]),
            color="#8c564b",
            linestyle="--",
            linewidth=1.2,
            label=f"Best 7-Tooth Ctrl C3-MonoGen ({by_code['C3_MonoGen']['F_z_pN']:+.2f} pN)",
        )
    ctrl12_codes = [c for c in ("C6_Uni12", "C7_Lin12", "C8_Mono12", "C9_Shuf12", "C10_OutPhase12") if c in by_code]
    if ctrl12_codes:
        best12_code = max(ctrl12_codes, key=lambda c: float(by_code[c]["F_z_pN"]))
        best12_val = float(by_code[best12_code]["F_z_pN"])
        best12_short = best12_code.replace("_", "-")
        ax_bar.axhline(
            best12_val,
            color="#8ca252",
            linestyle="-.",
            linewidth=1.2,
            label=f"Best 12-Tooth Ctrl {best12_short} ({best12_val:+.2f} pN)",
        )
    for b, v in zip(bars, fvals):
        va = "bottom" if v >= 0 else "top"
        off = 0.14 if v >= 0 else -0.35
        ax_bar.text(b.get_x() + b.get_width() / 2.0, v + off, f"{v:+.2f}", ha="center", va=va, fontsize=6.5, fontweight="bold")
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels([lbl for _, lbl, _ in present], fontsize=6.1, rotation=36, ha="right")
    ax_bar.set_ylabel(r"Disengaged Repulsion $F_z(3^\circ)$ [pN] ($A = 0.3104\ \mu\mathrm{m}^2$)", fontsize=9.5)
    ax_bar.set_title(r"$2^3$ Factorial Ablation & Matched 7-Tooth / 12-Tooth Controls ($z_{\mathrm{pad}} = -0.115\ \mu\mathrm{m}$ Fixed)", fontsize=10.0, fontweight="bold")
    ax_bar.set_ylim(min(-0.8, min(fvals) - 0.6), max(fvals) + 1.5)
    handles, labels = ax_bar.get_legend_handles_labels()
    if handles:
        ax_bar.legend(fontsize=8.0, loc="upper left")
    ax_bar.grid(axis="y", alpha=0.25)

    s_idx = np.arange(1, 8)
    bw = 0.15
    slot_series = [
        ("F0_000", "F0-000 Baseline", "#1f77b4", -2.0 * bw),
        ("F1r_100", "F1r-100 Radial Cantor", "#2ca02c", -1.0 * bw),
        ("F3_111", "F3-111 Unified 3D Fractal", "#d62728", 0.0 * bw),
        ("C3_MonoGen", "C3-MonoGen (7T) Monotonic", "#8c564b", 1.0 * bw),
        ("C8_Mono12", "C8-Mono12 (12T) Monotonic 12-Sub", "#8ca252", 2.0 * bw),
    ]
    for c, lbl, col, dx in slot_series:
        if c in by_code and len(by_code[c]["f_slots_pN"]) == len(s_idx):
            ax_slot.bar(s_idx + dx, by_code[c]["f_slots_pN"], width=bw, color=col, edgecolor="black", linewidth=0.6, label=lbl)
    ax_slot.axhline(0.0, color="black", linewidth=0.8)
    ax_slot.set_xticks(s_idx)
    ax_slot.set_xticklabels(["S1\n(Gen3)", "S2\n(Gen2)", "S3\n(Gen3)", "S4\n(Gen1)", "S5\n(Gen3)", "S6\n(Gen2)", "S7\n(Gen3)"], fontsize=8.5)
    ax_slot.set_ylabel(r"Per-Slot Axial Force $F_{z,k}$ [pN]", fontsize=9.5)
    ax_slot.set_title("Per-Slot Force Breakdown Across the 7 Stator Radial Bands", fontsize=10.2, fontweight="bold")
    ax_slot.legend(fontsize=7.8, loc="upper right")
    ax_slot.grid(axis="y", alpha=0.25)

    spec_series = [
        ("F0_000", "F0-000 Baseline", "#1f77b4", "--"),
        ("F1r_100", "F1r-100 Radial Fractal", "#2ca02c", "-."),
        ("F2rt_110", "F2rt-110 1-Mask Planar", "#e377c2", "-"),
        ("F3_111", "F3-111 Unified 3D Fractal", "#d62728", "-"),
        ("C3_MonoGen", "C3-MonoGen (7T) Monotonic", "#8c564b", ":"),
        ("C8_Mono12", "C8-Mono12 (12T) Monotonic 12-Sub", "#8ca252", "-."),
        ("C9_Shuf12", "C9-Shuf12 (12T) Shuffled 12-Sub", "#bd9e39", "--"),
    ]
    dense_spec_path = ROOT / "results" / "spectral_peak_refinement_and_models.json"
    dense_u: dict[str, Any] = {}
    if dense_spec_path.is_file():
        try:
            dense_u = json.loads(dense_spec_path.read_text(encoding="utf-8")).get("unified_3d", {})
        except Exception:
            dense_u = {}

    for c, lbl, col, ls in spec_series:
        if c in by_code:
            if c in dense_u and "kappas_um_inv" in dense_u[c]:
                k_arr = np.asarray(dense_u[c]["kappas_um_inv"], dtype=np.float64)
                fk_arr = np.asarray(dense_u[c]["f_kappa_pN_um"], dtype=np.float64)
                mev = max(1, len(k_arr) // 16)
            else:
                k_arr = np.asarray(by_code[c]["kappas_um_inv"], dtype=np.float64)
                fk_arr = np.asarray(by_code[c]["f_kappa_pN_um"], dtype=np.float64)
                mev = 1
            lw = 2.4 if c in ("F3_111", "F2rt_110") else 1.6
            ax_spec.plot(k_arr, k_arr * fk_arr, linestyle=ls, color=col, linewidth=lw, marker="o", markersize=3.0, markevery=mev, label=lbl)
    if "F3_111" in dense_u and "peaks" in dense_u["F3_111"]:
        pks_f3 = dense_u["F3_111"]["peaks"]
        k_lo = float(pks_f3[0]["kappa_peak_um_inv"] - pks_f3[0]["kappa_peak_sigma_um_inv"])
        k_hi = float(pks_f3[2]["kappa_peak_um_inv"] + pks_f3[2]["kappa_peak_sigma_um_inv"])
        ax_spec.axvspan(k_lo, k_hi, color="#d62728", alpha=0.10, lw=0.0, label=r"F3-111 Gen 1–3 Peak Window ($9.5\text{–}10.3\ \mu\mathrm{m}^{-1}$)")
        for idx_p, (pk_d, col_p) in enumerate(zip(pks_f3, ("#1f77b4", "#2ca02c", "#d62728")), 1):
            ax_spec.axvline(float(pk_d["kappa_peak_um_inv"]), color=col_p, linestyle=":", alpha=0.70, linewidth=1.1)
    ax_spec.set_xscale("log")
    ax_spec.set_xlim(0.5, 40.0)
    ax_spec.set_xlabel(r"Imaginary Wavenumber $\kappa = \xi/c$ [$\mu\mathrm{m}^{-1}$]", fontsize=9.5)
    ax_spec.set_ylabel(r"Spectral Integrand $\kappa f_z(\kappa)$ [pN]", fontsize=9.5)
    ax_spec.set_title(r"Wavenumber Spectrum $\kappa f_z(\kappa)$ Across $(r, \theta, z)$ Fractal Dimensions", fontsize=10.2, fontweight="bold")
    ax_spec.legend(fontsize=7.4, loc="upper left")
    ax_spec.grid(True, which="both", alpha=0.25)

    if "F3_111" in by_code and "F0_000" in by_code:
        r3 = by_code["F3_111"]
        r0 = by_code["F0_000"]
        if "F3_111" in dense_u and "F0_000" in dense_u:
            d3 = dense_u["F3_111"]
            d0 = dense_u["F0_000"]
            k_arr_f3 = np.asarray(d3["kappas_um_inv"], dtype=np.float64)
            k_arr_f0 = np.asarray(d0["kappas_um_inv"], dtype=np.float64)
            f3_k_g1 = np.asarray(d3["f_kappa_gen1_pN_um"], dtype=np.float64)
            f3_k_g2 = np.asarray(d3["f_kappa_gen2_pN_um"], dtype=np.float64)
            f3_k_g3 = np.asarray(d3["f_kappa_gen3_pN_um"], dtype=np.float64)
            f0_k_g1 = np.asarray(d0["f_kappa_gen1_pN_um"], dtype=np.float64)
            f0_k_g2 = np.asarray(d0["f_kappa_gen2_pN_um"], dtype=np.float64)
            f0_k_g3 = np.asarray(d0["f_kappa_gen3_pN_um"], dtype=np.float64)
            mev_d = max(1, len(k_arr_f3) // 16)
        else:
            k_arr_f3 = np.asarray(r3["kappas_um_inv"], dtype=np.float64)
            k_arr_f0 = np.asarray(r0["kappas_um_inv"], dtype=np.float64)
            f3_k_g1 = np.asarray(r3["f_kappa_gen1_pN_um"], dtype=np.float64)
            f3_k_g2 = np.asarray(r3["f_kappa_gen2_pN_um"], dtype=np.float64)
            f3_k_g3 = np.asarray(r3["f_kappa_gen3_pN_um"], dtype=np.float64)
            f0_k_g1 = np.asarray(r0["f_kappa_gen1_pN_um"], dtype=np.float64)
            f0_k_g2 = np.asarray(r0["f_kappa_gen2_pN_um"], dtype=np.float64)
            f0_k_g3 = np.asarray(r0["f_kappa_gen3_pN_um"], dtype=np.float64)
            mev_d = 1
        f3_slots = r3["f_slots_pN"]
        f0_slots = r0["f_slots_pN"]
        f3_g1, f3_g2, f3_g3 = f3_slots[3], f3_slots[1] + f3_slots[5], f3_slots[0] + f3_slots[2] + f3_slots[4] + f3_slots[6]
        f0_g1, f0_g2, f0_g3 = f0_slots[3], f0_slots[1] + f0_slots[5], f0_slots[0] + f0_slots[2] + f0_slots[4] + f0_slots[6]
        f0_g3_share_pct = 100.0 * _safe_div(f0_g3, float(r0["F_z_pN"]))
        gain_ratio_3d = _safe_div(float(r3["F_z_pN"]), float(r0["F_z_pN"]))

        ax_res.plot(
            k_arr_f3,
            k_arr_f3 * f3_k_g3,
            "o-",
            color="#d62728",
            linewidth=2.1,
            markersize=3.2,
            markevery=mev_d,
            label=f"3D F3-111 Gen-3 (S1,3,5,7): +{f3_g3:.2f} pN",
        )
        ax_res.plot(
            k_arr_f3,
            k_arr_f3 * f3_k_g2,
            "^-",
            color="#2ca02c",
            linewidth=2.1,
            markersize=3.2,
            markevery=mev_d,
            label=f"3D F3-111 Gen-2 (S2,S6 Up-Converted): +{f3_g2:.2f} pN",
        )
        ax_res.plot(
            k_arr_f3,
            k_arr_f3 * f3_k_g1,
            "s-",
            color="#1f77b4",
            linewidth=2.1,
            markersize=3.2,
            markevery=mev_d,
            label=f"3D F3-111 Gen-1 (S4 Up-Converted): +{f3_g1:.2f} pN",
        )
        ax_res.plot(
            k_arr_f0,
            k_arr_f0 * f0_k_g3,
            "o--",
            color="#d62728",
            alpha=0.55,
            linewidth=1.35,
            markersize=2.6,
            markevery=mev_d,
            label=f"1D Baseline F0-000 Gen-3: +{f0_g3:.2f} pN ({f0_g3_share_pct:.0f}% of F0)",
        )
        ax_res.plot(
            k_arr_f0,
            k_arr_f0 * f0_k_g2,
            "^--",
            color="#2ca02c",
            alpha=0.55,
            linewidth=1.35,
            markersize=2.6,
            markevery=mev_d,
            label=f"1D Baseline F0-000 Gen-2: +{f0_g2:.2f} pN (Starved)",
        )
        ax_res.plot(
            k_arr_f0,
            k_arr_f0 * f0_k_g1,
            "s--",
            color="#1f77b4",
            alpha=0.55,
            linewidth=1.35,
            markersize=2.6,
            markevery=mev_d,
            label=f"1D Baseline F0-000 Gen-1: {f0_g1:+.4f} pN (Dormant)",
        )
        if "F3_111" in dense_u and "peaks" in dense_u["F3_111"]:
            pks_f3 = dense_u["F3_111"]["peaks"]
            k_lo = float(pks_f3[0]["kappa_peak_um_inv"] - pks_f3[0]["kappa_peak_sigma_um_inv"])
            k_hi = float(pks_f3[2]["kappa_peak_um_inv"] + pks_f3[2]["kappa_peak_sigma_um_inv"])
            ax_res.axvspan(k_lo, k_hi, color="#64748B", alpha=0.13, lw=0.0)
            for idx_p, (pk_d, col_p, y_lbl) in enumerate(zip(pks_f3, ("#1f77b4", "#2ca02c", "#d62728"), (2.82, 3.04, 3.26)), 1):
                kp_v = float(pk_d["kappa_peak_um_inv"])
                ax_res.axvline(kp_v, color=col_p, linestyle=":", alpha=0.80, linewidth=1.15)
                ax_res.text(
                    kp_v * 1.04,
                    y_lbl,
                    rf"$\hat{{\kappa}}_{idx_p}={kp_v:.2f}\ \mu\mathrm{{m}}^{{-1}}$",
                    fontsize=6.9,
                    fontweight="bold",
                    color=col_p,
                    va="bottom",
                    ha="left",
                )
        ax_res.set_xscale("log")
        ax_res.set_xlim(0.5, 40.0)
        ax_res.set_ylim(-0.08, 3.55)
        ax_res.set_xlabel(r"Imaginary Wavenumber $\kappa = \xi/c$ [$\mu\mathrm{m}^{-1}$]", fontsize=9.5)
        ax_res.set_ylabel(r"Generation-Resolved $\kappa f_{z,m}(\kappa)$ [pN]", fontsize=9.5)
        ax_res.set_title(r"Generation-Resolved Wavenumber Bands: 3D Up-Conversion into Near-Field Window", fontsize=9.8, fontweight="bold")
        ax_res.legend(fontsize=6.4, loc="upper left", framealpha=0.92, borderpad=0.35, labelspacing=0.28)
        ax_res.grid(True, which="both", alpha=0.25)

        # Inset: 1D -> 3D Generation-Band Harvest Progression across (r, theta, z)
        prog_codes = [
            ("F0_000", "1D\nF0-000"),
            ("F1r_100", "1D+Rib\nF1r-100"),
            ("F2rt_110", "2D(r,θ)\nF2rt-110"),
            ("C10_OutPhase12", "OutPh\nC10"),
            ("F3_111", "3D\nF3-111"),
        ]
        prog_present = [(c, lbl) for c, lbl in prog_codes if c in by_code and len(by_code[c].get("f_slots_pN", ())) >= 7]
        if len(prog_present) >= 4:
            ax_ins = ax_res.inset_axes([0.046, 0.285, 0.224, 0.300])
            ax_ins.set_facecolor("#F8FAFC")
            ix = np.arange(len(prog_present))
            g1_vals = [float(by_code[c]["f_slots_pN"][3]) for c, _ in prog_present]
            g2_vals = [float(by_code[c]["f_slots_pN"][1] + by_code[c]["f_slots_pN"][5]) for c, _ in prog_present]
            g3_vals = [
                float(by_code[c]["f_slots_pN"][0] + by_code[c]["f_slots_pN"][2] + by_code[c]["f_slots_pN"][4] + by_code[c]["f_slots_pN"][6])
                for c, _ in prog_present
            ]
            ax_ins.bar(ix, g1_vals, width=0.56, color="#1f77b4", edgecolor="black", linewidth=0.5, label="Gen-1")
            ax_ins.bar(ix, g2_vals, width=0.56, bottom=g1_vals, color="#2ca02c", edgecolor="black", linewidth=0.5, label="Gen-2")
            b12 = [a + b for a, b in zip(g1_vals, g2_vals)]
            ax_ins.bar(ix, g3_vals, width=0.56, bottom=b12, color="#d62728", edgecolor="black", linewidth=0.5, label="Gen-3")
            totals = [a + b + c for a, b, c in zip(g1_vals, g2_vals, g3_vals)]
            for idx_i, tot_v in enumerate(totals):
                ax_ins.text(ix[idx_i], tot_v + 0.45, f"+{tot_v:.2f}", ha="center", va="bottom", fontsize=5.3, fontweight="bold")
            ax_ins.set_xticks(ix)
            ax_ins.set_xticklabels([lbl for _, lbl in prog_present], fontsize=5.4)
            ax_ins.set_ylim(0.0, 22.5)
            ax_ins.set_yticks([0, 6, 12, 18])
            ax_ins.tick_params(axis="y", labelsize=5.5, pad=1.0)
            ax_ins.tick_params(axis="x", pad=1.0)
            ax_ins.set_ylabel(r"$F_z$ [pN]", fontsize=6.0, labelpad=1.2)
            ax_ins.set_title(rf"1D $\to$ 3D Gen-Band Harvest ({gain_ratio_3d:.2f}$\times$)", fontsize=6.0, fontweight="bold", pad=2.2)
            ax_ins.grid(axis="y", alpha=0.25, linewidth=0.5)
            for sp in ax_ins.spines.values():
                sp.set_linewidth(0.6)
                sp.set_edgecolor("#64748B")

    for lbl_ch, ax_p in zip(("a", "b", "c", "d"), (ax_bar, ax_slot, ax_spec, ax_res)):
        ax_p.text(-0.075, 1.045, lbl_ch, transform=ax_p.transAxes, fontsize=13.0, fontweight="bold", va="bottom", ha="left", color="#0F172A")

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)


def write_markdown_summary(out_md: Path, payload: Mapping[str, Any]) -> None:
    """Write human-readable Markdown summary of the 2^3 Factorial & Wavenumber Study."""
    recs = payload["records"]
    by_code = {r["code"]: r for r in recs}
    eff = payload["factorial_effects"]
    lines = [
        "# Unified 3D Conformal-Recursive Polar Cantor Fractal: $2^3$ Factorial & Matched Controls Study",
        "",
        f"- **Generated (UTC)**: `{payload['generated_at_utc']}`",
        f"- **Quadrature Order**: `n_xi = {payload['solver_config']['n_xi']}`",
        f"- **Invariant Stator Pad Top**: `z_pad_top = {DEFAULT_Z_PAD_TOP_UM:.3f} um` (strictly fixed across all designs)",
        "",
        "## 1. $2^3$ Factorial Ablation & Matched Control Table ($\\theta = 3^\\circ$, Target $A_{\\text{tooth}} = 0.3104\\ \\mu\\text{m}^2$)",
        "",
        "| Code | Design Name | $(U_r, U_\\theta, U_z)$ | $A_{\\text{tooth}}$ [$\\mu\\text{m}^2$] | $F_z(3^\\circ)$ [pN] | $F_z/A_{\\text{tooth}}$ [pN/$\\mu\\text{m}^2$] | $\\sum_k F_{z,k}/(2\\pi R_k)$ [pN/$\\mu\\text{m}$] | Cantor Log-Mod Amp [%] | Per-Slot Forces $[F_1,\\dots,F_K]$ [pN] |",
        "|---|---|:---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in recs:
        s_str = ", ".join(f"{x:+.3f}" for x in r["f_slots_pN"])
        lines.append(
            f"| `{r['code']}` | `{r['name']}` | `({r['u_r']},{r['u_theta']},{r['u_z']})` | {r['A_tooth_um2']:.4f} | "
            f"**{r['F_z_pN']:+.4f}** | {r['F_per_A_pN_per_um2']:+.2f} | {r['F_circ_sum_pN_per_um']:+.4f} | "
            f"{r['cantor_mod_amp_pct']:.2f}% | `[{s_str}]` |"
        )
    if eff:
        lines.extend(
            [
                "",
                "## 2. Factorial Main Effects & Multi-Dimensional Synergies",
                "",
                f"- **Single Upgrade $U_r$ (`F1r_100 - F0_000`)**: `{eff['single_effect_r_pN']:+.4f} pN`",
                f"- **Single Upgrade $U_\\theta$ (`F1t_010 - F0_000`)**: `{eff['single_effect_theta_pN']:+.4f} pN`",
                f"- **Single Upgrade $U_z$ (`F1z_001 - F0_000`)**: `{eff['single_effect_z_pN']:+.4f} pN`",
                f"- **Factorial Main Effect $\\Delta F_r$**: `{eff['main_effect_r_pN']:+.4f} pN`",
                f"- **Factorial Main Effect $\\Delta F_\\theta$**: `{eff['main_effect_theta_pN']:+.4f} pN`",
                f"- **Factorial Main Effect $\\Delta F_z$**: `{eff['main_effect_z_pN']:+.4f} pN`",
                f"- **Two-Way Synergy $\\Delta F_{{r,\\theta}}$**: `{eff['synergy_r_theta_pN']:+.4f} pN`",
                f"- **Two-Way Synergy $\\Delta F_{{r,z}}$**: `{eff['synergy_r_z_pN']:+.4f} pN`",
                f"- **Two-Way Synergy $\\Delta F_{{\\theta,z}}$**: `{eff['synergy_theta_z_pN']:+.4f} pN`",
                f"- **Three-Way Synergy $\\Delta F_{{r,\\theta,z}}$**: `{eff['synergy_3way_r_theta_z_pN']:+.4f} pN`",
                f"- **Total Gain (`F3_111` vs. `F0_000`)**: `{eff['total_gain_111_over_000_pN']:+.4f} pN` (`{eff['total_gain_111_over_000_pct']:+.1f}%`)",
            ]
        )
    if "F3_111" in by_code and "C8_Mono12" in by_code:
        f3 = float(by_code["F3_111"]["F_z_pN"])
        c6 = float(by_code["C6_Uni12"]["F_z_pN"])
        c7 = float(by_code["C7_Lin12"]["F_z_pN"])
        c8 = float(by_code["C8_Mono12"]["F_z_pN"])
        c9 = float(by_code["C9_Shuf12"]["F_z_pN"])
        c10 = float(by_code["C10_OutPhase12"]["F_z_pN"])
        lines.extend(
            [
                "",
                "## 3. Pinpointing Physical Contributions: 7-Tooth vs. 12-Tooth Non-Fractal Controls",
                "",
                f"- **`F3_111` vs. `C6_Uni12` (12 Uniform Slots/Teeth, 24 Lobes)**: `{f3 - c6:+.4f} pN` (`{100.0 * _safe_div(f3 - c6, c6):+.1f}%`)",
                f"- **`F3_111` vs. `C7_Lin12` (12 Linearly Graded Slots/Teeth, 24 Lobes)**: `{f3 - c7:+.4f} pN` (`{100.0 * _safe_div(f3 - c7, c7):+.1f}%`)",
                f"- **`F3_111` vs. `C8_Mono12` (7 Monotonic Slots with 12 Equal Sub-Slots/Teeth, 24 Lobes)**: `{f3 - c8:+.4f} pN` (`{100.0 * _safe_div(f3 - c8, c8):+.1f}%`)",
                f"- **`F3_111` vs. `C9_Shuf12` (7 Shuffled Slots with 12 Equal Sub-Slots/Teeth, 24 Lobes)**: `{f3 - c9:+.4f} pN` (`{100.0 * _safe_div(f3 - c9, c9):+.1f}%`)",
                f"- **`F3_111` vs. `C10_OutPhase12` (7 Primary Cantor Slots with 12 Equal Sub-Slots & Out-of-Phase $(\\theta, z)$)**: `{f3 - c10:+.4f} pN` (`{100.0 * _safe_div(f3 - c10, c10):+.1f}%`)",
            ]
        )
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-xi", type=int, default=DEFAULT_BEM_QUADRATURE_ORDER, help="Imaginary-frequency quadrature order")
    parser.add_argument("--n-xi-r5nm", type=int, default=12, help="Imaginary-frequency quadrature order for r_edge=5nm rounded-edge evaluations")
    parser.add_argument("--num-threads", type=int, default=8, help="PyTorch CPU threads")
    parser.add_argument("--max-steps", type=int, default=0, help="Optional cap on evaluated designs (0 = all)")
    parser.add_argument(
        "--reuse-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse already-evaluated design records from existing output JSON when solver and design hashes match",
    )
    args = parser.parse_args(argv)

    designs = build_all_study_designs()
    if args.max_steps < 0:
        raise ValueError("--max-steps must be >= 0")
    is_micro = 0 < args.max_steps < len(designs)
    selected = designs[: args.max_steps] if is_micro else designs

    code_hash = _compute_full_code_hash()
    now_iso = datetime.now(timezone.utc).isoformat()

    suffix = "_micro" if is_micro else ""
    out_json = ROOT / "results" / f"n3_unified_3d_fractal_factorial_study{suffix}.json"
    out_md = ROOT / "results" / f"n3_unified_3d_fractal_factorial_study{suffix}.md"
    out_png = ROOT / "figures" / f"fig_n3_unified_3d_fractal_factorial{suffix}.png"
    out_pdf = ROOT / "figures" / f"fig_n3_unified_3d_fractal_factorial{suffix}.pdf"

    cached_by_code: dict[str, dict[str, Any]] = {}
    cached_angular_states: dict[str, Any] = {}
    cached_r5nm: dict[str, dict[str, Any]] = {}
    cached_exact_b3: dict[str, dict[str, Any]] = {}
    cached_iso_03049: dict[str, dict[str, Any]] = {}
    cached_phase_perms: dict[str, dict[str, Any]] = {}
    cached_matched_opt: dict[str, dict[str, Any]] = {}
    if args.reuse_existing and out_json.exists():
        try:
            prev_payload = json.loads(out_json.read_text(encoding="utf-8"))
            cached_angular_states = dict(prev_payload.get("f3_111_angular_states", {}))
            cached_r5nm = dict(prev_payload.get("f3_111_edge_rounding_r5nm", {}))
            cached_exact_b3 = dict(prev_payload.get("exact_b3_scaling_variants", {}))
            cached_iso_03049 = dict(prev_payload.get("iso_area_03049_suite", {}))
            cached_phase_perms = dict(prev_payload.get("phase_permutation_suite", {}))
            cached_matched_opt = dict(prev_payload.get("matched_and_optimized_controls", {}))
            prev_cfg = prev_payload.get("solver_config", {})
            if (
                int(prev_cfg.get("n_xi", -1)) == int(args.n_xi)
                and abs(float(prev_cfg.get("z_pad_top_um", 0.0)) - DEFAULT_Z_PAD_TOP_UM) <= 1e-9
                and str(prev_cfg.get("code_version_hash", "")) == code_hash
            ):
                for rec in prev_payload.get("records", []):
                    cached_by_code[str(rec["code"])] = rec
        except (OSError, ValueError, KeyError, TypeError):
            cached_by_code = {}
            cached_angular_states = {}
            cached_r5nm = {}
            cached_exact_b3 = {}
            cached_iso_03049 = {}
            cached_phase_perms = {}
            cached_matched_opt = {}

    records: list[dict[str, Any]] = []
    for idx, des in enumerate(selected, 1):
        d_hash = _compute_design_hash(des)
        if (
            des.code in cached_by_code
            and cached_by_code[des.code].get("name") == des.name
            and cached_by_code[des.code].get("design_hash") == d_hash
        ):
            rec = dict(cached_by_code[des.code])
            tag = "CACHED"
        else:
            rec = evaluate_unified_3d_bem(
                des,
                theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                n_xi=int(args.n_xi),
                num_threads=int(args.num_threads),
            )
            rec["design_hash"] = d_hash
            tag = "SOLVED"
        enrich_record_with_geometry(rec, des)
        records.append(rec)
        print(
            f"[{idx:2d}/{len(selected)} {tag}] {rec['code']:14s} | {rec['name']:36s} | "
            f"Fz={rec['F_z_pN']:+.4f} pN | A={rec['A_tooth_um2']:.4f} | P={rec['P_edge_um']:.2f} | "
            f"Asw={rec['A_sidewall_um2']:.4f} | V={rec['V_tooth_um3']:.5f} | gh={rec['g_r_harm_nm']:.2f}nm | "
            f"F/A={rec['F_per_A_pN_per_um2']:+.2f} | F/P={rec['F_per_P_pN_per_um']:+.3f} | F/Asw={rec['F_per_Asw_pN_per_um2']:+.2f}",
            flush=True,
        )

    by_code = {r["code"]: r for r in records}
    factorial_effects = compute_extended_factorial_contrasts(by_code) if not is_micro else {}
    geom_model = fit_multi_feature_geometric_model(records) if not is_micro else {}

    r5nm_results: dict[str, dict[str, Any]] = {}
    exact_b3_results: dict[str, dict[str, Any]] = {}
    iso_03049_results: dict[str, dict[str, Any]] = {}
    factorial_effects_iso_03049: dict[str, float] = {}
    phase_perm_results: dict[str, dict[str, Any]] = {}
    matched_opt_results: dict[str, dict[str, Any]] = {}
    if not is_micro:
        des_by_code = {d.code: d for d in designs}
        for r5_code in ("F3_111", "C6_Uni12", "C8_Mono12", "C9_Shuf12"):
            des_r5 = des_by_code[r5_code]
            d_hash_r5 = _compute_design_hash(des_r5)
            if (
                r5_code in cached_r5nm
                and cached_r5nm[r5_code].get("design_hash") == d_hash_r5
                and abs(float(cached_r5nm[r5_code].get("r_edge_nm", 0.0)) - 5.0) <= 1e-9
                and int(cached_r5nm[r5_code].get("n_xi_r5nm", 12)) == int(args.n_xi_r5nm)
            ):
                r5_rec = dict(cached_r5nm[r5_code])
                r5_tag = "CACHED-r5nm"
            else:
                r5_rec = evaluate_unified_r5nm_bem(
                    des_r5,
                    r_edge_nm=5.0,
                    theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                    n_xi=int(args.n_xi_r5nm),
                    num_threads=int(args.num_threads),
                )
                r5_rec["design_hash"] = d_hash_r5
                r5_rec["n_xi_r5nm"] = int(args.n_xi_r5nm)
                r5_tag = "SOLVED-r5nm"
            r5nm_results[r5_code] = r5_rec
            cached_r5nm[r5_code] = r5_rec
            print(
                f"[{r5_tag}] {r5_code:14s} | Fz(r=5nm)={r5_rec['F_z_r5nm_pN']:+.4f} pN "
                f"(sharp={by_code[r5_code]['F_z_pN']:+.4f} pN) | elapsed={r5_rec.get('elapsed_s', 0.0):.1f}s",
                flush=True,
            )

        for b3_des in build_exact_b3_scaling_variants(des_by_code["F3_111"]):
            b3_hash = _compute_design_hash(b3_des)
            if (
                b3_des.code in cached_exact_b3
                and cached_exact_b3[b3_des.code].get("design_hash") == b3_hash
                and int(cached_exact_b3[b3_des.code].get("n_xi", -1)) == int(args.n_xi)
                and int(cached_exact_b3[b3_des.code].get("n_xi_r5nm", 12)) == int(args.n_xi_r5nm)
            ):
                b3_rec = dict(cached_exact_b3[b3_des.code])
                b3_tag = "CACHED-b3"
            else:
                sharp_b3 = evaluate_unified_3d_bem(
                    b3_des,
                    theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                    n_xi=int(args.n_xi),
                    num_threads=int(args.num_threads),
                )
                r5_b3 = evaluate_unified_r5nm_bem(
                    b3_des,
                    r_edge_nm=5.0,
                    theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                    n_xi=int(args.n_xi_r5nm),
                    num_threads=int(args.num_threads),
                )
                b3_rec = {
                    "code": b3_des.code,
                    "name": b3_des.name,
                    "design_hash": b3_hash,
                    "n_xi": int(args.n_xi),
                    "n_xi_r5nm": int(args.n_xi_r5nm),
                    "A_tooth_um2": float(sharp_b3["A_tooth_um2"]),
                    "F_z_pN": float(sharp_b3["F_z_pN"]),
                    "F_per_A_pN_per_um2": float(sharp_b3["F_per_A_pN_per_um2"]),
                    "F_circ_sum_pN_per_um": float(sharp_b3["F_circ_sum_pN_per_um"]),
                    "f_slots_pN": list(sharp_b3["f_slots_pN"]),
                    "F_z_r5nm_pN": float(r5_b3["F_z_r5nm_pN"]),
                    "F_per_A_r5nm_pN_per_um2": float(r5_b3["F_per_A_r5nm_pN_per_um2"]),
                    "f_slots_r5nm_pN": list(r5_b3["f_slots_r5nm_pN"]),
                }
                b3_tag = "SOLVED-b3"
            enrich_record_with_geometry(b3_rec, b3_des)
            exact_b3_results[b3_des.code] = b3_rec
            print(
                f"[{b3_tag}] {b3_des.code:20s} | Fz={b3_rec['F_z_pN']:+.4f} pN (F/A={b3_rec['F_per_A_pN_per_um2']:+.2f}) | "
                f"Fz(r=5nm)={b3_rec['F_z_r5nm_pN']:+.4f} pN | A={b3_rec['A_tooth_um2']:.4f} um^2",
                flush=True,
            )

        # Exact A_tooth = 0.304944 um^2 matched factorial & 12-tooth control suite,
        # ordered by shared stator geometry so _LAST_STATOR_CACHE reuses stator LU factors:
        target_a_f3 = active_area_unified(des_by_code["F3_111"])
        n_xi_aux = int(args.n_xi_r5nm)
        iso_codes = (
            "F0_000", "F1r_Sub", "F1t_010", "F1z_001", "F2tz_011",
            "F2rt_110", "F3_111",
            "C6_Uni12", "C7_Lin12", "C8_Mono12", "C9_Shuf12",
            "C10_OutPhase12",
            "F1r_100", "F2rz_101",
        )
        for ic in iso_codes:
            base_d = des_by_code[ic]
            if abs(active_area_unified(base_d) - target_a_f3) <= 1e-6:
                iso_d = base_d
                iso_hash = _compute_design_hash(iso_d)
                iso_rec = {
                    "code": ic,
                    "name": base_d.name,
                    "design_hash": iso_hash,
                    "n_xi": int(args.n_xi),
                    "F_z_pN": float(by_code[ic]["F_z_pN"]),
                    "F_circ_sum_pN_per_um": float(by_code[ic]["F_circ_sum_pN_per_um"]),
                }
                enrich_record_with_geometry(iso_rec, iso_d)
                iso_tag = "REUSED-iso03049"
            else:
                iso_d = _arch_mod.scale_design_angles_to_iso_area(
                    base_d, target_a_f3, _arch_mod.DEFAULT_N3_MAX_TOOTH_ARC_DEG, area_tol_um2=1e-4
                )
                iso_hash = _compute_design_hash(iso_d)
                if (
                    ic in cached_iso_03049
                    and cached_iso_03049[ic].get("design_hash") == iso_hash
                    and int(cached_iso_03049[ic].get("n_xi", -1)) in (int(args.n_xi), n_xi_aux)
                ):
                    iso_rec = dict(cached_iso_03049[ic])
                    enrich_record_with_geometry(iso_rec, iso_d)
                    iso_tag = "CACHED-iso03049"
                else:
                    ev_iso = evaluate_unified_r5nm_bem(
                        iso_d,
                        r_edge_nm=0.0,
                        theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                        n_xi=n_xi_aux,
                        num_threads=int(args.num_threads),
                    )
                    iso_rec = {
                        "code": ic,
                        "name": iso_d.name,
                        "design_hash": iso_hash,
                        "n_xi": n_xi_aux,
                        "F_z_pN": float(ev_iso["F_z_pN"]),
                        "F_circ_sum_pN_per_um": float(ev_iso["F_circ_sum_pN_per_um"]),
                    }
                    enrich_record_with_geometry(iso_rec, iso_d)
                    iso_tag = "SOLVED-iso03049"
            iso_03049_results[ic] = iso_rec
            print(
                f"[{iso_tag}] {ic:14s} | A={iso_rec['A_tooth_um2']:.4f} | Fz={iso_rec['F_z_pN']:+.4f} pN | "
                f"F/A={iso_rec['F_per_A_pN_per_um2']:+.2f} | P={iso_rec['P_edge_um']:.2f} | Asw={iso_rec['A_sidewall_um2']:.4f}",
                flush=True,
            )
        factorial_effects_iso_03049 = compute_extended_factorial_contrasts(iso_03049_results)

        # Multiple (theta, z) phase permutations (P_perm* immediately reuse F2rz_101's cached 12-Cantor-sub-slot stator!):
        for pp_des in build_phase_permutation_variants(des_by_code["F3_111"]):
            pp_hash = _compute_design_hash(pp_des)
            if (
                pp_des.code in cached_phase_perms
                and cached_phase_perms[pp_des.code].get("design_hash") == pp_hash
                and int(cached_phase_perms[pp_des.code].get("n_xi", -1)) in (int(args.n_xi), n_xi_aux)
            ):
                pp_rec = dict(cached_phase_perms[pp_des.code])
                enrich_record_with_geometry(pp_rec, pp_des)
                pp_tag = "CACHED-perm"
            else:
                ev_pp = evaluate_unified_r5nm_bem(
                    pp_des,
                    r_edge_nm=0.0,
                    theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                    n_xi=n_xi_aux,
                    num_threads=int(args.num_threads),
                )
                pp_rec = {
                    "code": pp_des.code,
                    "name": pp_des.name,
                    "family_role": pp_des.family_role,
                    "design_hash": pp_hash,
                    "n_xi": n_xi_aux,
                    "slot_levels": [int(s.level) for s in pp_des.slots],
                    "F_z_pN": float(ev_pp["F_z_pN"]),
                    "F_circ_sum_pN_per_um": float(ev_pp["F_circ_sum_pN_per_um"]),
                }
                enrich_record_with_geometry(pp_rec, pp_des)
                pp_tag = "SOLVED-perm"
            phase_perm_results[pp_des.code] = pp_rec
            print(
                f"[{pp_tag}] {pp_des.code:16s} | levels={pp_rec['slot_levels']} | Fz={pp_rec['F_z_pN']:+.4f} pN | "
                f"A={pp_rec['A_tooth_um2']:.4f} | F/A={pp_rec['F_per_A_pN_per_um2']:+.2f}",
                flush=True,
            )

        # Matched-g15 (clearance/perimeter/sidewall/volume matched) & fabrication-optimized controls:
        mo_designs = build_matched_and_optimized_controls(des_by_code["F3_111"])
        mo_to_solve: list[tuple[Unified3DDesign, str]] = []
        for mo_des in mo_designs:
            mo_hash = _compute_design_hash(mo_des)
            if (
                mo_des.code in cached_matched_opt
                and cached_matched_opt[mo_des.code].get("design_hash") == mo_hash
                and int(cached_matched_opt[mo_des.code].get("n_xi", -1)) in (int(args.n_xi), n_xi_aux)
                and int(cached_matched_opt[mo_des.code].get("n_xi_r5nm", 12)) == int(args.n_xi_r5nm)
            ):
                mo_rec = dict(cached_matched_opt[mo_des.code])
                enrich_record_with_geometry(mo_rec, mo_des)
                matched_opt_results[mo_des.code] = mo_rec
                print(
                    f"[CACHED-opt] {mo_des.code:20s} | Fz={mo_rec['F_z_pN']:+.4f} pN (r5nm={mo_rec['F_z_r5nm_pN']:+.4f} pN) | "
                    f"A={mo_rec['A_tooth_um2']:.4f} | P={mo_rec['P_edge_um']:.2f} | Asw={mo_rec['A_sidewall_um2']:.4f} | gh={mo_rec['g_r_harm_nm']:.2f}nm",
                    flush=True,
                )
            else:
                mo_to_solve.append((mo_des, mo_hash))
        if mo_to_solve:
            sharp_by_code: dict[str, dict[str, Any]] = {}
            for mo_des, _ in mo_to_solve:
                sharp_by_code[mo_des.code] = evaluate_unified_r5nm_bem(
                    mo_des,
                    r_edge_nm=0.0,
                    theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                    n_xi=n_xi_aux,
                    num_threads=int(args.num_threads),
                )
            for mo_des, mo_hash in mo_to_solve:
                ev_mo = sharp_by_code[mo_des.code]
                r5_mo = evaluate_unified_r5nm_bem(
                    mo_des,
                    r_edge_nm=5.0,
                    theta_deg=DEFAULT_DISENGAGED_THETA_DEG,
                    n_xi=int(args.n_xi_r5nm),
                    num_threads=int(args.num_threads),
                )
                mo_rec = {
                    "code": mo_des.code,
                    "name": mo_des.name,
                    "family_role": mo_des.family_role,
                    "design_hash": mo_hash,
                    "n_xi": n_xi_aux,
                    "n_xi_r5nm": int(args.n_xi_r5nm),
                    "F_z_pN": float(ev_mo["F_z_pN"]),
                    "F_circ_sum_pN_per_um": float(ev_mo["F_circ_sum_pN_per_um"]),
                    "F_z_r5nm_pN": float(r5_mo["F_z_r5nm_pN"]),
                }
                enrich_record_with_geometry(mo_rec, mo_des)
                matched_opt_results[mo_des.code] = mo_rec
                print(
                    f"[SOLVED-opt] {mo_des.code:20s} | Fz={mo_rec['F_z_pN']:+.4f} pN (r5nm={mo_rec['F_z_r5nm_pN']:+.4f} pN) | "
                    f"A={mo_rec['A_tooth_um2']:.4f} | P={mo_rec['P_edge_um']:.2f} | Asw={mo_rec['A_sidewall_um2']:.4f} | gh={mo_rec['g_r_harm_nm']:.2f}nm",
                    flush=True,
                )

    payload = {
        "generated_at_utc": now_iso,
        "executed_at": now_iso,
        "model": "BEM_Unified3DFractal_Factorial",
        "dataset": "n3_unified_3d_fractal_factorial_study",
        "execution_status": "micro_probe_complete" if is_micro else "complete",
        "solver_config": {
            "n_r_slot": 2,
            "n_r_tooth": 2,
            "n_phi_tooth": 3,
            "n_phi_bridge": 3,
            "n_z": 2,
            "n_xi": int(args.n_xi),
            "z_pad_top_um": DEFAULT_Z_PAD_TOP_UM,
            "code_version_hash": code_hash,
        },
        "factorial_effects": factorial_effects,
        "records": records,
    }
    if geom_model:
        payload["geometric_scaling_model"] = geom_model
    if cached_angular_states:
        payload["f3_111_angular_states"] = cached_angular_states
    if r5nm_results:
        payload["f3_111_edge_rounding_r5nm"] = r5nm_results
    if exact_b3_results:
        payload["exact_b3_scaling_variants"] = exact_b3_results
    if iso_03049_results:
        payload["iso_area_03049_suite"] = iso_03049_results
        payload["factorial_effects_iso_03049"] = factorial_effects_iso_03049
    if phase_perm_results:
        payload["phase_permutation_suite"] = phase_perm_results
    if matched_opt_results:
        payload["matched_and_optimized_controls"] = matched_opt_results

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=out_json.parent, delete=False, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out_json)

    write_markdown_summary(out_md, payload)
    render_figure(records, factorial_effects, out_png, out_pdf)

    if not is_micro:
        set_solver_provenance(
            "bem",
            {
                "benchmark": "n3_unified_3d_fractal_factorial_study",
                "n_xi": int(args.n_xi),
                "n_designs": len(records),
                "z_pad_top_um": DEFAULT_Z_PAD_TOP_UM,
                "code_version_hash": code_hash,
                "executed_at": now_iso,
            },
        )
        log_step(
            "n3_unified_3d_fractal_factorial_study",
            {
                "status": "complete",
                "n_designs": len(records),
                "n_xi": int(args.n_xi),
            },
            solver_name="bem",
        )
        f0 = float(by_code["F0_000"]["F_z_pN"])
        f1r_sub = float(by_code["F1r_Sub"]["F_z_pN"])
        f1r = float(by_code["F1r_100"]["F_z_pN"])
        f1t = float(by_code["F1t_010"]["F_z_pN"])
        f1z = float(by_code["F1z_001"]["F_z_pN"])
        f2rt = float(by_code["F2rt_110"]["F_z_pN"])
        f2rz = float(by_code["F2rz_101"]["F_z_pN"])
        f2tz = float(by_code["F2tz_011"]["F_z_pN"])
        f3 = float(by_code["F3_111"]["F_z_pN"])
        c1 = float(by_code["C1_Uni000"]["F_z_pN"])
        c2 = float(by_code["C2_Uni111"]["F_z_pN"])
        c3 = float(by_code["C3_MonoGen"]["F_z_pN"])
        c4 = float(by_code["C4_Shuf111"]["F_z_pN"])
        c5 = float(by_code["C5_OutPhase"]["F_z_pN"])
        c6 = float(by_code["C6_Uni12"]["F_z_pN"])
        c7 = float(by_code["C7_Lin12"]["F_z_pN"])
        c8 = float(by_code["C8_Mono12"]["F_z_pN"])
        c9 = float(by_code["C9_Shuf12"]["F_z_pN"])
        c10 = float(by_code["C10_OutPhase12"]["F_z_pN"])

        single_r = float(factorial_effects["single_effect_r_pN"])
        single_t = float(factorial_effects["single_effect_theta_pN"])
        single_z = float(factorial_effects["single_effect_z_pN"])
        linear_sum = f0 + single_r + single_t + single_z
        superadd_excess = f3 - linear_sum
        subrib_gain = f1r - f1r_sub

        code_map = {
            "F0_000": "f000",
            "F1r_Sub": "f1r_sub",
            "F1r_100": "f100_r",
            "F1t_010": "f010_theta",
            "F1z_001": "f001_z",
            "F2rt_110": "f110_rtheta_planar",
            "F2rz_101": "f101_rz",
            "F2tz_011": "f011_thetaz",
            "F3_111": "f111_unified",
            "C1_Uni000": "ctrl_uni000",
            "C2_Uni111": "ctrl_uni111",
            "C3_MonoGen": "ctrl_monogen",
            "C4_Shuf111": "ctrl_shuffled111",
            "C5_OutPhase": "ctrl_outphase",
            "C6_Uni12": "ctrl_uni12",
            "C7_Lin12": "ctrl_lin12",
            "C8_Mono12": "ctrl_mono12",
            "C9_Shuf12": "ctrl_shuf12",
            "C10_OutPhase12": "ctrl_outphase12",
        }

        metrics_to_log: dict[str, float] = {}
        for code_str, slug in code_map.items():
            rec_item = by_code[code_str]
            metrics_to_log[f"n3_uni3d_{slug}_fz_pn"] = float(rec_item["F_z_pN"])
            metrics_to_log[f"n3_uni3d_{slug}_fa"] = float(rec_item["F_per_A_pN_per_um2"])
            metrics_to_log[f"n3_uni3d_{slug}_fcirc"] = float(rec_item["F_circ_sum_pN_per_um"])
            metrics_to_log[f"n3_uni3d_{slug}_area_um2"] = float(rec_item["A_tooth_um2"])
            metrics_to_log[f"n3_uni3d_{slug}_pedge_um"] = float(rec_item["P_edge_um"])
            metrics_to_log[f"n3_uni3d_{slug}_asw_um2"] = float(rec_item["A_sidewall_um2"])
            metrics_to_log[f"n3_uni3d_{slug}_aswr_um2"] = float(rec_item["A_sidewall_r_um2"])
            metrics_to_log[f"n3_uni3d_{slug}_vol_um3"] = float(rec_item["V_tooth_um3"])
            metrics_to_log[f"n3_uni3d_{slug}_gr_harm_nm"] = float(rec_item["g_r_harm_nm"])
            metrics_to_log[f"n3_uni3d_{slug}_fp"] = float(rec_item["F_per_P_pN_per_um"])
            metrics_to_log[f"n3_uni3d_{slug}_fasw"] = float(rec_item["F_per_Asw_pN_per_um2"])
            metrics_to_log[f"n3_uni3d_{slug}_fv"] = float(rec_item["F_per_V_pN_per_um3"])
            metrics_to_log[f"n3_uni3d_{slug}_mod_amp_pct"] = float(rec_item["cantor_mod_amp_pct"])

        metrics_to_log.update({
            "n3_uni3d_gain_f111_vs_f000_pn": f3 - f0,
            "n3_uni3d_gain_f111_vs_f000_pct": 100.0 * _safe_div(f3 - f0, f0),
            "n3_uni3d_ratio_f111_vs_f000": _safe_div(f3, f0),
            "n3_uni3d_ratio_f111_vs_uni000": _safe_div(f3, c1),
            "n3_uni3d_ratio_f111_vs_uni111": _safe_div(f3, c2),
            "n3_uni3d_ratio_f110_planar_vs_f000": _safe_div(f2rt, f0),
            "n3_uni3d_gain_f110_planar_vs_f000_pct": 100.0 * _safe_div(f2rt - f0, f0),
            "n3_uni3d_gain_f111_vs_monogen_pct": 100.0 * _safe_div(f3 - c3, c3),
            "n3_uni3d_gain_f111_vs_shuffled_pct": 100.0 * _safe_div(f3 - c4, c4),
            "n3_uni3d_gain_f011_vs_monogen_pct": 100.0 * _safe_div(f2tz - c3, c3),
            "n3_uni3d_gain_f111_vs_uni12_pn": f3 - c6,
            "n3_uni3d_gain_f111_vs_uni12_pct": 100.0 * _safe_div(f3 - c6, c6),
            "n3_uni3d_gain_f111_vs_uni12_fa_pct": 100.0 * _safe_div(
                float(by_code["F3_111"]["F_per_A_pN_per_um2"]) - float(by_code["C6_Uni12"]["F_per_A_pN_per_um2"]),
                float(by_code["C6_Uni12"]["F_per_A_pN_per_um2"]),
            ),
            "n3_uni3d_gain_f111_vs_lin12_pn": f3 - c7,
            "n3_uni3d_gain_f111_vs_lin12_pct": 100.0 * _safe_div(f3 - c7, c7),
            "n3_uni3d_gain_f111_vs_lin12_fa_pct": 100.0 * _safe_div(
                float(by_code["F3_111"]["F_per_A_pN_per_um2"]) - float(by_code["C7_Lin12"]["F_per_A_pN_per_um2"]),
                float(by_code["C7_Lin12"]["F_per_A_pN_per_um2"]),
            ),
            "n3_uni3d_gain_f111_vs_mono12_pn": f3 - c8,
            "n3_uni3d_gain_f111_vs_mono12_pct": 100.0 * _safe_div(f3 - c8, c8),
            "n3_uni3d_gain_f111_vs_mono12_fa_pct": 100.0 * _safe_div(
                float(by_code["F3_111"]["F_per_A_pN_per_um2"]) - float(by_code["C8_Mono12"]["F_per_A_pN_per_um2"]),
                float(by_code["C8_Mono12"]["F_per_A_pN_per_um2"]),
            ),
            "n3_uni3d_gain_f111_vs_shuf12_pn": f3 - c9,
            "n3_uni3d_gain_f111_vs_shuf12_pct": 100.0 * _safe_div(f3 - c9, c9),
            "n3_uni3d_gain_f111_vs_shuf12_fa_pct": 100.0 * _safe_div(
                float(by_code["F3_111"]["F_per_A_pN_per_um2"]) - float(by_code["C9_Shuf12"]["F_per_A_pN_per_um2"]),
                float(by_code["C9_Shuf12"]["F_per_A_pN_per_um2"]),
            ),
            "n3_uni3d_gain_f111_vs_outphase12_pn": f3 - c10,
            "n3_uni3d_gain_f111_vs_outphase12_pct": 100.0 * _safe_div(f3 - c10, c10),
            "n3_uni3d_gain_f111_vs_outphase12_fa_pct": 100.0 * _safe_div(
                float(by_code["F3_111"]["F_per_A_pN_per_um2"]) - float(by_code["C10_OutPhase12"]["F_per_A_pN_per_um2"]),
                float(by_code["C10_OutPhase12"]["F_per_A_pN_per_um2"]),
            ),
            "n3_uni3d_gain_f110_planar_vs_monogen_pct": 100.0 * _safe_div(f2rt - c3, c3),
            "n3_uni3d_single_effect_r_pn": single_r,
            "n3_uni3d_single_effect_r_pct": 100.0 * _safe_div(single_r, f0),
            "n3_uni3d_single_effect_r_sub_pct": 100.0 * _safe_div(f1r_sub - f0, f0),
            "n3_uni3d_stator_subrib_gain_pn": subrib_gain,
            "n3_uni3d_stator_subrib_gain_pct": 100.0 * _safe_div(subrib_gain, f1r_sub),
            "n3_uni3d_single_effect_theta_pn": single_t,
            "n3_uni3d_single_effect_theta_pct": 100.0 * _safe_div(single_t, f0),
            "n3_uni3d_single_effect_z_pn": single_z,
            "n3_uni3d_single_effect_z_pct": 100.0 * _safe_div(single_z, f0),
            "n3_uni3d_linear_additive_sum_pn": linear_sum,
            "n3_uni3d_superadditive_excess_pn": superadd_excess,
            "n3_uni3d_superadditive_excess_pct": 100.0 * _safe_div(superadd_excess, linear_sum),
            "n3_uni3d_main_effect_r_pn": float(factorial_effects["main_effect_r_pN"]),
            "n3_uni3d_main_effect_theta_pn": float(factorial_effects["main_effect_theta_pN"]),
            "n3_uni3d_main_effect_z_pn": float(factorial_effects["main_effect_z_pN"]),
            "n3_uni3d_synergy_r_theta_pn": float(factorial_effects["synergy_r_theta_pN"]),
            "n3_uni3d_synergy_r_z_pn": float(factorial_effects["synergy_r_z_pN"]),
            "n3_uni3d_synergy_theta_z_pn": float(factorial_effects["synergy_theta_z_pN"]),
            "n3_uni3d_synergy_3way_pn": float(factorial_effects["synergy_3way_r_theta_z_pN"]),
            "n3_uni3d_mod_amp_f000_pct": float(by_code["F0_000"]["cantor_mod_amp_pct"]),
            "n3_uni3d_mod_amp_f111_pct": float(by_code["F3_111"]["cantor_mod_amp_pct"]),
            "n3_uni3d_slot4_f000_pn": float(by_code["F0_000"]["f_slots_pN"][3]),
            "n3_uni3d_slot4_f100_pn": float(by_code["F1r_100"]["f_slots_pN"][3]),
            "n3_uni3d_slot4_f111_pn": float(by_code["F3_111"]["f_slots_pN"][3]),
            "n3_uni3d_slot2_f111_pn": float(by_code["F3_111"]["f_slots_pN"][1]),
            "n3_uni3d_slot6_f111_pn": float(by_code["F3_111"]["f_slots_pN"][5]),
            "n3_uni3d_gen2_f000_pn": float(by_code["F0_000"]["f_slots_pN"][1] + by_code["F0_000"]["f_slots_pN"][5]),
            "n3_uni3d_gen3_f000_pn": float(
                by_code["F0_000"]["f_slots_pN"][0]
                + by_code["F0_000"]["f_slots_pN"][2]
                + by_code["F0_000"]["f_slots_pN"][4]
                + by_code["F0_000"]["f_slots_pN"][6]
            ),
            "n3_uni3d_gen2_f111_pn": float(by_code["F3_111"]["f_slots_pN"][1] + by_code["F3_111"]["f_slots_pN"][5]),
            "n3_uni3d_gen3_f111_pn": float(
                by_code["F3_111"]["f_slots_pN"][0]
                + by_code["F3_111"]["f_slots_pN"][2]
                + by_code["F3_111"]["f_slots_pN"][4]
                + by_code["F3_111"]["f_slots_pN"][6]
            ),
        })
        if "straddling" in cached_angular_states and "landing_pad" in cached_angular_states:
            f3_21 = float(cached_angular_states["straddling"]["F_z_pN"])
            f3_48 = float(cached_angular_states["landing_pad"]["F_z_pN"])
            metrics_to_log["n3_uni3d_f111_unified_theta21_fz_pn"] = f3_21
            metrics_to_log["n3_uni3d_f111_unified_theta48_fz_pn"] = f3_48
            metrics_to_log["n3_uni3d_f111_unified_swing_pn"] = f3 - f3_48
        if all(k in r5nm_results for k in ("F3_111", "C6_Uni12", "C8_Mono12", "C9_Shuf12")):
            f3_r5 = float(r5nm_results["F3_111"]["F_z_r5nm_pN"])
            c6_r5 = float(r5nm_results["C6_Uni12"]["F_z_r5nm_pN"])
            c8_r5 = float(r5nm_results["C8_Mono12"]["F_z_r5nm_pN"])
            c9_r5 = float(r5nm_results["C9_Shuf12"]["F_z_r5nm_pN"])
            metrics_to_log["n3_uni3d_f111_r5nm_fz_pn"] = f3_r5
            metrics_to_log["n3_uni3d_ctrl_uni12_r5nm_fz_pn"] = c6_r5
            metrics_to_log["n3_uni3d_ctrl_mono12_r5nm_fz_pn"] = c8_r5
            metrics_to_log["n3_uni3d_ctrl_shuf12_r5nm_fz_pn"] = c9_r5
            metrics_to_log["n3_uni3d_gain_f111_vs_uni12_r5nm_pct"] = 100.0 * _safe_div(f3_r5 - c6_r5, c6_r5)
            metrics_to_log["n3_uni3d_gain_f111_vs_mono12_r5nm_pct"] = 100.0 * _safe_div(f3_r5 - c8_r5, c8_r5)
            metrics_to_log["n3_uni3d_gain_f111_vs_shuf12_r5nm_pct"] = 100.0 * _safe_div(f3_r5 - c9_r5, c9_r5)

        b3_slug_map = {
            "F3_ExactZ_StepB3": "exactz_stepb3",
            "F3_ExactTheta_GapB3": "exacttheta_gapb3",
            "F3_Exact3D_IsoB3": "exact3d_isob3",
            "F3_StrictB3_Uniso": "strictb3_uniso",
        }
        for b3_code, b3_slug in b3_slug_map.items():
            if b3_code in exact_b3_results:
                b3_rec = exact_b3_results[b3_code]
                b3_fz = float(b3_rec["F_z_pN"])
                b3_fa = float(b3_rec["F_per_A_pN_per_um2"])
                b3_r5 = float(b3_rec["F_z_r5nm_pN"])
                metrics_to_log[f"n3_uni3d_{b3_slug}_fz_pn"] = b3_fz
                metrics_to_log[f"n3_uni3d_{b3_slug}_fa"] = b3_fa
                metrics_to_log[f"n3_uni3d_{b3_slug}_area_um2"] = float(b3_rec["A_tooth_um2"])
                metrics_to_log[f"n3_uni3d_{b3_slug}_r5nm_fz_pn"] = b3_r5
                metrics_to_log[f"n3_uni3d_gain_{b3_slug}_vs_shuf12_pct"] = 100.0 * _safe_div(b3_fz - c9, c9)
                metrics_to_log[f"n3_uni3d_gain_{b3_slug}_vs_outphase12_pct"] = 100.0 * _safe_div(b3_fz - c10, c10)
                if "C9_Shuf12" in r5nm_results:
                    c9_r5_val = float(r5nm_results["C9_Shuf12"]["F_z_r5nm_pN"])
                    metrics_to_log[f"n3_uni3d_gain_{b3_slug}_vs_shuf12_r5nm_pct"] = 100.0 * _safe_div(b3_r5 - c9_r5_val, c9_r5_val)

        if factorial_effects:
            metrics_to_log["n3_uni3d_pairwise_synergy_sum_pn"] = float(factorial_effects["pairwise_synergy_sum_pN"])
            metrics_to_log["n3_uni3d_anova_int_r_theta_pn"] = float(factorial_effects["anova_interaction_r_theta_pN"])
            metrics_to_log["n3_uni3d_anova_int_r_z_pn"] = float(factorial_effects["anova_interaction_r_z_pN"])
            metrics_to_log["n3_uni3d_anova_int_theta_z_pn"] = float(factorial_effects["anova_interaction_theta_z_pN"])
            metrics_to_log["n3_uni3d_anova_int_3way_pn"] = float(factorial_effects["anova_interaction_3way_pN"])

        if geom_model:
            metrics_to_log["n3_uni3d_geom_model_r2_full"] = float(geom_model["r2_full_p_asw_v_gap"])
            metrics_to_log["n3_uni3d_geom_model_r2_adj_full"] = float(geom_model["r2_adj_full_p_asw_v_gap"])
            metrics_to_log["n3_uni3d_geom_model_mae_full_pn"] = float(geom_model["mae_full_pN"])
            metrics_to_log["n3_uni3d_geom_model_rmse_full_pn"] = float(geom_model["rmse_full_pN"])
            metrics_to_log["n3_uni3d_geom_model_r2_psw"] = float(geom_model["r2_perimeter_sidewall_volume"])
            metrics_to_log["n3_uni3d_geom_model_f111_pred_pn"] = float(geom_model["predictions_by_code"]["F3_111"]["F_z_pred_full_pN"])
            metrics_to_log["n3_uni3d_geom_model_f111_res_pn"] = float(geom_model["predictions_by_code"]["F3_111"]["residual_full_pN"])
            metrics_to_log["n3_uni3d_geom_model_f111_psw_pred_pn"] = float(geom_model["predictions_by_code"]["F3_111"]["F_z_pred_psw_pN"])
            metrics_to_log["n3_uni3d_geom_model_f111_psw_res_pn"] = float(geom_model["predictions_by_code"]["F3_111"]["residual_psw_pN"])

        if iso_03049_results and factorial_effects_iso_03049:
            for ic, i_rec in iso_03049_results.items():
                i_slug = code_map.get(ic, ic.lower())
                metrics_to_log[f"n3_iso3049_{i_slug}_fz_pn"] = float(i_rec["F_z_pN"])
                metrics_to_log[f"n3_iso3049_{i_slug}_fa"] = float(i_rec["F_per_A_pN_per_um2"])
                metrics_to_log[f"n3_iso3049_{i_slug}_fp"] = float(i_rec["F_per_P_pN_per_um"])
                metrics_to_log[f"n3_iso3049_{i_slug}_fasw"] = float(i_rec["F_per_Asw_pN_per_um2"])
                metrics_to_log[f"n3_iso3049_{i_slug}_fv"] = float(i_rec["F_per_V_pN_per_um3"])
            f0_iso = float(iso_03049_results["F0_000"]["F_z_pN"])
            c6_iso = float(iso_03049_results["C6_Uni12"]["F_z_pN"])
            c8_iso = float(iso_03049_results["C8_Mono12"]["F_z_pN"])
            c9_iso = float(iso_03049_results["C9_Shuf12"]["F_z_pN"])
            c10_iso = float(iso_03049_results["C10_OutPhase12"]["F_z_pN"])
            metrics_to_log["n3_iso3049_ratio_f111_vs_f000"] = _safe_div(f3, f0_iso)
            metrics_to_log["n3_iso3049_gain_f111_vs_uni12_pct"] = 100.0 * _safe_div(f3 - c6_iso, c6_iso)
            metrics_to_log["n3_iso3049_gain_f111_vs_mono12_pct"] = 100.0 * _safe_div(f3 - c8_iso, c8_iso)
            metrics_to_log["n3_iso3049_gain_f111_vs_shuf12_pct"] = 100.0 * _safe_div(f3 - c9_iso, c9_iso)
            metrics_to_log["n3_iso3049_gain_f111_vs_outphase12_pct"] = 100.0 * _safe_div(f3 - c10_iso, c10_iso)
            metrics_to_log["n3_iso3049_single_effect_r_pn"] = float(factorial_effects_iso_03049["single_effect_r_pN"])
            metrics_to_log["n3_iso3049_single_effect_theta_pn"] = float(factorial_effects_iso_03049["single_effect_theta_pN"])
            metrics_to_log["n3_iso3049_single_effect_z_pn"] = float(factorial_effects_iso_03049["single_effect_z_pN"])
            metrics_to_log["n3_iso3049_linear_additive_sum_pn"] = float(factorial_effects_iso_03049["linear_additive_sum_pN"])
            metrics_to_log["n3_iso3049_superadditive_excess_pn"] = float(factorial_effects_iso_03049["superadditive_excess_pN"])
            metrics_to_log["n3_iso3049_superadditive_excess_pct"] = float(factorial_effects_iso_03049["superadditive_excess_pct"])
            metrics_to_log["n3_iso3049_main_effect_r_pn"] = float(factorial_effects_iso_03049["main_effect_r_pN"])
            metrics_to_log["n3_iso3049_main_effect_theta_pn"] = float(factorial_effects_iso_03049["main_effect_theta_pN"])
            metrics_to_log["n3_iso3049_main_effect_z_pn"] = float(factorial_effects_iso_03049["main_effect_z_pN"])
            metrics_to_log["n3_iso3049_synergy_r_theta_pn"] = float(factorial_effects_iso_03049["synergy_r_theta_pN"])
            metrics_to_log["n3_iso3049_synergy_r_z_pn"] = float(factorial_effects_iso_03049["synergy_r_z_pN"])
            metrics_to_log["n3_iso3049_synergy_theta_z_pn"] = float(factorial_effects_iso_03049["synergy_theta_z_pN"])
            metrics_to_log["n3_iso3049_pairwise_synergy_sum_pn"] = float(factorial_effects_iso_03049["pairwise_synergy_sum_pN"])
            metrics_to_log["n3_iso3049_synergy_3way_pn"] = float(factorial_effects_iso_03049["synergy_3way_r_theta_z_pN"])
            metrics_to_log["n3_iso3049_anova_int_r_theta_pn"] = float(factorial_effects_iso_03049["anova_interaction_r_theta_pN"])
            metrics_to_log["n3_iso3049_anova_int_r_z_pn"] = float(factorial_effects_iso_03049["anova_interaction_r_z_pN"])
            metrics_to_log["n3_iso3049_anova_int_theta_z_pn"] = float(factorial_effects_iso_03049["anova_interaction_theta_z_pN"])
            metrics_to_log["n3_iso3049_anova_int_3way_pn"] = float(factorial_effects_iso_03049["anova_interaction_3way_pN"])

        if phase_perm_results:
            p_cantor_vals: list[float] = []
            p_c10_vals: list[float] = []
            for pp_code, pp_rec in phase_perm_results.items():
                pp_slug = pp_code.lower()
                pp_fz = float(pp_rec["F_z_pN"])
                metrics_to_log[f"n3_perm_{pp_slug}_fz_pn"] = pp_fz
                metrics_to_log[f"n3_perm_{pp_slug}_fa"] = float(pp_rec["F_per_A_pN_per_um2"])
                if pp_code.startswith("P_perm"):
                    p_cantor_vals.append(pp_fz)
                elif pp_code.startswith("C10_perm") and pp_code != "C10_perm123":
                    p_c10_vals.append(pp_fz)
            if p_cantor_vals:
                metrics_to_log["n3_perm_cantor_min_fz_pn"] = float(min(p_cantor_vals))
                metrics_to_log["n3_perm_cantor_max_fz_pn"] = float(max(p_cantor_vals))
                metrics_to_log["n3_perm_cantor_mean_fz_pn"] = float(np.mean(p_cantor_vals))
            if p_c10_vals:
                metrics_to_log["n3_perm_c10_min_fz_pn"] = float(min(p_c10_vals))
                metrics_to_log["n3_perm_c10_max_fz_pn"] = float(max(p_c10_vals))
                metrics_to_log["n3_perm_c10_mean_fz_pn"] = float(np.mean(p_c10_vals))

        if matched_opt_results:
            for mo_code, mo_rec in matched_opt_results.items():
                mo_slug = mo_code.lower()
                mo_fz = float(mo_rec["F_z_pN"])
                mo_r5 = float(mo_rec["F_z_r5nm_pN"])
                metrics_to_log[f"n3_opt_{mo_slug}_fz_pn"] = mo_fz
                metrics_to_log[f"n3_opt_{mo_slug}_r5nm_fz_pn"] = mo_r5
                metrics_to_log[f"n3_opt_{mo_slug}_area_um2"] = float(mo_rec["A_tooth_um2"])
                metrics_to_log[f"n3_opt_{mo_slug}_pedge_um"] = float(mo_rec["P_edge_um"])
                metrics_to_log[f"n3_opt_{mo_slug}_asw_um2"] = float(mo_rec["A_sidewall_um2"])
                metrics_to_log[f"n3_opt_{mo_slug}_vol_um3"] = float(mo_rec["V_tooth_um3"])
                metrics_to_log[f"n3_opt_{mo_slug}_gr_harm_nm"] = float(mo_rec["g_r_harm_nm"])
                metrics_to_log[f"n3_opt_{mo_slug}_fa"] = float(mo_rec["F_per_A_pN_per_um2"])
                metrics_to_log[f"n3_opt_{mo_slug}_fp"] = float(mo_rec["F_per_P_pN_per_um"])
                metrics_to_log[f"n3_opt_{mo_slug}_fasw"] = float(mo_rec["F_per_Asw_pN_per_um2"])
                metrics_to_log[f"n3_opt_{mo_slug}_fv"] = float(mo_rec["F_per_V_pN_per_um3"])
                metrics_to_log[f"n3_opt_{mo_slug}_fcirc"] = float(mo_rec["F_circ_sum_pN_per_um"])
                metrics_to_log[f"n3_opt_diff_{mo_slug}_vs_f111_pct"] = 100.0 * _safe_div(mo_fz - f3, f3)
                if "F3_111" in r5nm_results:
                    f3_r5_v = float(r5nm_results["F3_111"]["F_z_r5nm_pN"])
                    metrics_to_log[f"n3_opt_diff_{mo_slug}_vs_f111_r5nm_pct"] = 100.0 * _safe_div(mo_r5 - f3_r5_v, f3_r5_v)

        dense_spec_file = ROOT / "results" / "spectral_peak_refinement_and_models.json"
        if dense_spec_file.is_file():
            try:
                ds_u = json.loads(dense_spec_file.read_text(encoding="utf-8")).get("unified_3d", {})
                payload["dense_spectral_analysis"] = ds_u
                for code_ds, prefix_ds in (("F0_000", "f000"), ("F3_111", "f111")):
                    if code_ds in ds_u:
                        pks_ds = ds_u[code_ds]["peaks"]
                        mod_ds = ds_u[code_ds]["models"]
                        for g_idx in (1, 2, 3):
                            pk_g = pks_ds[g_idx - 1]
                            metrics_to_log[f"n3_uni3d_{prefix_ds}_gen{g_idx}_k_peak_um_inv"] = float(pk_g["kappa_peak_um_inv"])
                            metrics_to_log[f"n3_uni3d_{prefix_ds}_gen{g_idx}_k_peak_sigma_um_inv"] = float(pk_g["kappa_peak_sigma_um_inv"])
                            metrics_to_log[f"n3_uni3d_{prefix_ds}_gen{g_idx}_kf_peak_pn"] = float(pk_g["peak_value"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_dlnk_21"] = float(mod_ds["delta_ln_kappa_21"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_dlnk_21_sigma"] = float(mod_ds["delta_ln_kappa_21_sigma"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_dlnk_32"] = float(mod_ds["delta_ln_kappa_32"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_dlnk_32_sigma"] = float(mod_ds["delta_ln_kappa_32_sigma"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_ratio_k21"] = float(mod_ds["ratio_k2_over_k1"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_ratio_k32"] = float(mod_ds["ratio_k3_over_k2"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_model_ln3_r2"] = float(mod_ds["exact_ln3_model"]["r2"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_model_ln3_pk_chi2"] = float(mod_ds["exact_ln3_model"]["peak_location_chi2"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_model_comp_b_eff"] = float(mod_ds["compressed_periodic_model"]["effective_scale_b"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_model_comp_r2"] = float(mod_ds["compressed_periodic_model"]["r2"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_model_comp_daic"] = float(mod_ds["compressed_periodic_model"]["delta_aic_vs_exact_ln3"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_model_unres_r2"] = float(mod_ds["unrestricted_multiband_model"]["r2"])
                        metrics_to_log[f"n3_uni3d_{prefix_ds}_model_unres_daic"] = float(mod_ds["unrestricted_multiband_model"]["delta_aic_vs_exact_ln3"])
            except Exception:
                pass

        mt_file = ROOT / "results" / "multitier_physical_convergence.json"
        if mt_file.is_file():
            try:
                mt_entries = json.loads(mt_file.read_text(encoding="utf-8")).get("entries", {})
                payload["multitier_physical_convergence"] = mt_entries
                tier_short = {"tier1_std_phys": "t1", "tier2_high_phys": "t2", "tier3_ultra_phys": "t3"}
                for e_val in mt_entries.values():
                    c_e = str(e_val["code"])
                    r_int = int(round(float(e_val["r_edge_nm"])))
                    t_s = tier_short.get(str(e_val["tier"]), str(e_val["tier"]))
                    slug_e = code_map.get(c_e, c_e.lower())
                    metrics_to_log[f"n3_mt_{slug_e}_r{r_int}nm_{t_s}_fz_pn"] = float(e_val["F_z_pN"])
                    metrics_to_log[f"n3_mt_{slug_e}_r{r_int}nm_{t_s}_panels"] = float(e_val["n_total4"])
                for r_int, r_flt in ((5, 5.0), (10, 10.0)):
                    for t_slug, t_s in tier_short.items():
                        k_f3 = f"F3_111|{r_flt:.1f}|{t_slug}"
                        k_f0 = f"F0_000|{r_flt:.1f}|{t_slug}"
                        k_c1 = f"C1_Uni000|{r_flt:.1f}|{t_slug}"
                        k_c9 = f"C9_Shuf12|{r_flt:.1f}|{t_slug}"
                        if k_f3 in mt_entries and k_f0 in mt_entries:
                            v_f3 = float(mt_entries[k_f3]["F_z_pN"])
                            v_f0 = float(mt_entries[k_f0]["F_z_pN"])
                            metrics_to_log[f"n3_mt_ratio_f111_vs_f000_r{r_int}nm_{t_s}"] = _safe_div(v_f3, v_f0)
                        if k_f3 in mt_entries and k_c1 in mt_entries:
                            v_f3 = float(mt_entries[k_f3]["F_z_pN"])
                            v_c1 = float(mt_entries[k_c1]["F_z_pN"])
                            metrics_to_log[f"n3_mt_ratio_f111_vs_uni000_r{r_int}nm_{t_s}"] = _safe_div(v_f3, v_c1)
                        if k_f3 in mt_entries and k_c9 in mt_entries:
                            v_f3 = float(mt_entries[k_f3]["F_z_pN"])
                            v_c9 = float(mt_entries[k_c9]["F_z_pN"])
                            metrics_to_log[f"n3_mt_gain_f111_vs_shuf12_r{r_int}nm_{t_s}_pct"] = 100.0 * _safe_div(v_f3 - v_c9, v_c9)
                        k_fr = f"F1r_100|{r_flt:.1f}|{t_slug}"
                        k_ft = f"F1t_010|{r_flt:.1f}|{t_slug}"
                        k_fz = f"F1z_001|{r_flt:.1f}|{t_slug}"
                        if all(k in mt_entries for k in (k_f3, k_f0, k_fr, k_ft, k_fz)):
                            v_f3 = float(mt_entries[k_f3]["F_z_pN"])
                            v_f0 = float(mt_entries[k_f0]["F_z_pN"])
                            v_fr = float(mt_entries[k_fr]["F_z_pN"])
                            v_ft = float(mt_entries[k_ft]["F_z_pN"])
                            v_fz = float(mt_entries[k_fz]["F_z_pN"])
                            lin_s = v_f0 + (v_fr - v_f0) + (v_ft - v_f0) + (v_fz - v_f0)
                            metrics_to_log[f"n3_mt_linear_sum_r{r_int}nm_{t_s}_pn"] = lin_s
                            metrics_to_log[f"n3_mt_superadd_excess_r{r_int}nm_{t_s}_pn"] = v_f3 - lin_s
                            metrics_to_log[f"n3_mt_superadd_excess_r{r_int}nm_{t_s}_pct"] = 100.0 * _safe_div(v_f3 - lin_s, lin_s)
            except Exception:
                pass
        with tempfile.NamedTemporaryFile("w", dir=out_json.parent, delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.replace(out_json)
        for m_key, m_val in metrics_to_log.items():
            log_metric(m_key, m_val, step_id="n3_unified_3d_fractal_factorial_study", solver_name="bem", defer_save=True)
        first_k = next(iter(metrics_to_log))
        log_metric(first_k, metrics_to_log[first_k], step_id="n3_unified_3d_fractal_factorial_study", solver_name="bem", defer_save=False)
        export_macros(str(ROOT / "results" / "provenance_metrics.json"), str(ROOT / "results" / "macros_results.tex"))
        save_plot_provenance(str(out_png), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        save_plot_provenance(str(out_pdf), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        for paper_dir in (
            ROOT / "Papers" / "Fractal_Casimir_Nature_EM" / "figures",
            ROOT / "Papers" / "FCE_Nature_ver01" / "figures",
        ):
            if paper_dir.is_dir():
                for src_f in (out_png, out_pdf, out_png.with_suffix(".provenance.json"), out_pdf.with_suffix(".provenance.json")):
                    if src_f.is_file():
                        shutil.copy2(src_f, paper_dir / src_f.name)
        for paper_tex_dir in (
            ROOT / "Papers" / "Fractal_Casimir_Nature_EM",
            ROOT / "Papers" / "FCE_Nature_ver01",
        ):
            if paper_tex_dir.is_dir():
                shutil.copy2(ROOT / "results" / "macros_results.tex", paper_tex_dir / "macros_results.tex")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
