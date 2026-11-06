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
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse
import dataclasses
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
from pathlib import Path
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


def _compute_design_hash(des: Unified3DDesign) -> str:
    """Compute deterministic SHA-256 fingerprint of a Unified3DDesign geometry."""
    payload = json.dumps(dataclasses.asdict(des), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _compute_full_code_hash() -> str:
    """Compute combined SHA-256 hash across this script and the imported solver/geometry/architecture modules."""
    h = hashlib.sha256()
    for mod in (sys.modules[__name__], _arch_mod, _geom_mod, _bem_mod):
        h.update(inspect.getsource(mod).encode("utf-8"))
    return h.hexdigest()[:16]


def render_figure(
    records: Sequence[Mapping[str, Any]],
    factorial_effects: Mapping[str, float],
    out_png: Path,
    out_pdf: Path,
) -> None:
    """Render 4-panel diagnostic figure for the 2^3 Factorial & 3D Wavenumber Log-Periodic Study."""
    by_code = {r["code"]: r for r in records}
    fig, axes = plt.subplots(2, 2, figsize=(15.5, 10.8), dpi=220)
    ax_bar, ax_slot = axes[0]
    ax_spec, ax_res = axes[1]

    order = [
        ("F0_000", "F0 (000)\nBaseline", "#1f77b4"),
        ("F1z_001", "F1z (001)\nZ-Step Only", "#aec7e8"),
        ("F1t_010", "F1θ (010)\nθ-Cantor Only", "#ffbb78"),
        ("F2tz_011", "F2θz (011)\nθ + Z", "#ff7f0e"),
        ("F1r_Sub", "F1r-Sub\nRotor Sub-Teeth", "#98df8a"),
        ("F1r_100", "F1r (100)\nRotor+Stator", "#2ca02c"),
        ("F2rz_101", "F2rz (101)\nR + Z", "#17becf"),
        ("F2rt_110", "F2rθ (110)\n1-Mask Planar", "#e377c2"),
        ("F3_111", "F3 (111)\nUnified 3D", "#d62728"),
        ("C1_Uni000", "Ctrl C1 (7T)\nUniform Flat", "#7f7f7f"),
        ("C2_Uni111", "Ctrl C2 (7T)\nUniform 111", "#c7c7c7"),
        ("C3_MonoGen", "Ctrl C3 (7T)\nMonotonic 011", "#8c564b"),
        ("C4_Shuf111", "Ctrl C4 (7T)\nShuffled 011", "#9467bd"),
        ("C5_OutPhase", "Ctrl C5 (7T)\nOut-of-Phase", "#bcbd22"),
        ("C6_Uni12", "Ctrl C6 (12T)\nUniform 12-Slot", "#5254a3"),
        ("C7_Lin12", "Ctrl C7 (12T)\nLinear 12-Slot", "#6b6ecf"),
        ("C8_Mono12", "Ctrl C8 (12T)\nMonotonic 12-Sub", "#8ca252"),
        ("C9_Shuf12", "Ctrl C9 (12T)\nShuffled 12-Sub", "#bd9e39"),
        ("C10_OutPhase12", "Ctrl C10 (12T)\nOutPhase 12-Sub", "#ad494a"),
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
            label=f"Best 7-Tooth Ctrl C3 ({by_code['C3_MonoGen']['F_z_pN']:+.2f} pN)",
        )
    if "C8_Mono12" in by_code:
        ax_bar.axhline(
            float(by_code["C8_Mono12"]["F_z_pN"]),
            color="#8ca252",
            linestyle="-.",
            linewidth=1.2,
            label=f"Best 12-Tooth Ctrl C8 ({by_code['C8_Mono12']['F_z_pN']:+.2f} pN)",
        )
    for b, v in zip(bars, fvals):
        va = "bottom" if v >= 0 else "top"
        off = 0.12 if v >= 0 else -0.35
        ax_bar.text(b.get_x() + b.get_width() / 2.0, v + off, f"{v:+.2f}", ha="center", va=va, fontsize=6.8, fontweight="bold")
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels([lbl for _, lbl, _ in present], fontsize=6.5, rotation=28, ha="right")
    ax_bar.set_ylabel(r"Disengaged Repulsion $F_z(3^\circ)$ [pN] ($A = 0.3104\ \mu\mathrm{m}^2$)", fontsize=9.5)
    ax_bar.set_title(r"(a) $2^3$ Factorial Ablation & Matched 7-Tooth / 12-Tooth Controls ($z_{\mathrm{pad}} = -0.115\ \mu\mathrm{m}$ Fixed)", fontsize=10.0, fontweight="bold")
    ax_bar.set_ylim(min(-0.8, min(fvals) - 0.6), max(fvals) + 1.3)
    handles, labels = ax_bar.get_legend_handles_labels()
    if handles:
        ax_bar.legend(fontsize=8.0, loc="upper left")
    ax_bar.grid(axis="y", alpha=0.25)

    s_idx = np.arange(1, 8)
    bw = 0.15
    slot_series = [
        ("F0_000", "F0 (000) Baseline", "#1f77b4", -2.0 * bw),
        ("F1r_100", "F1r (100) Radial Cantor", "#2ca02c", -1.0 * bw),
        ("F3_111", "F3 (111) Unified 3D Fractal", "#d62728", 0.0 * bw),
        ("C3_MonoGen", "C3 (7T) Monotonic 011", "#8c564b", 1.0 * bw),
        ("C8_Mono12", "C8 (12T) Monotonic 12-Sub", "#8ca252", 2.0 * bw),
    ]
    for c, lbl, col, dx in slot_series:
        if c in by_code and len(by_code[c]["f_slots_pN"]) == len(s_idx):
            ax_slot.bar(s_idx + dx, by_code[c]["f_slots_pN"], width=bw, color=col, edgecolor="black", linewidth=0.6, label=lbl)
    ax_slot.axhline(0.0, color="black", linewidth=0.8)
    ax_slot.set_xticks(s_idx)
    ax_slot.set_xticklabels(["S1\n(Gen3)", "S2\n(Gen2)", "S3\n(Gen3)", "S4\n(Gen1)", "S5\n(Gen3)", "S6\n(Gen2)", "S7\n(Gen3)"], fontsize=8.5)
    ax_slot.set_ylabel(r"Per-Slot Axial Force $F_{z,k}$ [pN]", fontsize=9.5)
    ax_slot.set_title("(b) Per-Slot Force Breakdown Across the 7 Stator Radial Bands", fontsize=10.2, fontweight="bold")
    ax_slot.legend(fontsize=7.8, loc="upper right")
    ax_slot.grid(axis="y", alpha=0.25)

    spec_series = [
        ("F0_000", "F0 (000) Baseline", "#1f77b4", "--"),
        ("F1r_100", "F1r (100) Radial Fractal", "#2ca02c", "-."),
        ("F2rt_110", "F2rθ (110) 1-Mask Planar", "#e377c2", "-"),
        ("F3_111", "F3 (111) Unified 3D Fractal", "#d62728", "-"),
        ("C3_MonoGen", "Ctrl C3 (7T) Monotonic", "#8c564b", ":"),
        ("C8_Mono12", "Ctrl C8 (12T) Monotonic 12-Sub", "#8ca252", "-."),
        ("C9_Shuf12", "Ctrl C9 (12T) Shuffled 12-Sub", "#bd9e39", "--"),
    ]
    for c, lbl, col, ls in spec_series:
        if c in by_code:
            k_arr = np.asarray(by_code[c]["kappas_um_inv"])
            fk_arr = np.asarray(by_code[c]["f_kappa_pN_um"])
            lw = 2.4 if c in ("F3_111", "F2rt_110") else 1.6
            ax_spec.plot(k_arr, k_arr * fk_arr, linestyle=ls, color=col, linewidth=lw, marker="o", markersize=3.2, label=lbl)
    for kp, glbl in ((2.41, r"$\kappa_1$ (Gen 1)"), (4.92, r"$\kappa_2$ (Gen 2)"), (9.01, r"$\kappa_3$ (Gen 3)")):
        ax_spec.axvline(kp, color="black", linestyle=":", alpha=0.55, linewidth=1.0)
        ax_spec.text(kp * 1.03, 0.05, glbl, rotation=90, va="bottom", ha="left", fontsize=7.8)
    ax_spec.set_xscale("log")
    ax_spec.set_xlim(0.5, 40.0)
    ax_spec.set_xlabel(r"Imaginary Wavenumber $\kappa = \xi/c$ [$\mu\mathrm{m}^{-1}$]", fontsize=9.5)
    ax_spec.set_ylabel(r"Spectral Integrand $\kappa f_z(\kappa)$ [pN]", fontsize=9.5)
    ax_spec.set_title(r"(c) Wavenumber Spectrum $\kappa f_z(\kappa)$ Across $(r, \theta, z)$ Fractal Dimensions", fontsize=10.2, fontweight="bold")
    ax_spec.legend(fontsize=7.8, loc="upper left")
    ax_spec.grid(True, which="both", alpha=0.25)

    if "F3_111" in by_code and "F0_000" in by_code:
        r3 = by_code["F3_111"]
        r0 = by_code["F0_000"]
        k_arr = np.asarray(r3["kappas_um_inv"])
        ax_res.plot(k_arr, k_arr * np.asarray(r3["f_kappa_gen1_pN_um"]), "s-", color="#1f77b4", linewidth=2.0, markersize=3.5, label="F3 Gen-1 Slot (S4): 3 Cantor Sub-Teeth")
        ax_res.plot(k_arr, k_arr * np.asarray(r3["f_kappa_gen2_pN_um"]), "^-", color="#2ca02c", linewidth=2.0, markersize=3.5, label="F3 Gen-2 Slots (S2, S6): 2 Cantor Sub-Teeth")
        ax_res.plot(k_arr, k_arr * np.asarray(r3["f_kappa_gen3_pN_um"]), "o-", color="#d62728", linewidth=2.0, markersize=3.5, label="F3 Gen-3 Slots (S1, S3, S5, S7)")
        ax_res.plot(k_arr, k_arr * np.asarray(r0["f_kappa_gen1_pN_um"]), "s--", color="#1f77b4", alpha=0.45, linewidth=1.3, label="F0 Gen-1 Slot (Baseline)")
        ax_res.plot(k_arr, k_arr * np.asarray(r0["f_kappa_gen2_pN_um"]), "^--", color="#2ca02c", alpha=0.45, linewidth=1.3, label="F0 Gen-2 Slots (Baseline)")
        for kp in (2.41, 4.92, 9.01):
            ax_res.axvline(kp, color="black", linestyle=":", alpha=0.55, linewidth=1.0)
        ax_res.set_xscale("log")
        ax_res.set_xlim(0.5, 40.0)
        ax_res.set_xlabel(r"Imaginary Wavenumber $\kappa = \xi/c$ [$\mu\mathrm{m}^{-1}$]", fontsize=9.5)
        ax_res.set_ylabel(r"Generation-Resolved $\kappa f_{z,m}(\kappa)$ [pN]", fontsize=9.5)
        ax_res.set_title(r"(d) Scale-Locked Generation Spectra ($m=1,2,3$) in Unified 3D Fractal vs. Baseline", fontsize=10.2, fontweight="bold")
        ax_res.legend(fontsize=7.8, loc="upper left")
        ax_res.grid(True, which="both", alpha=0.25)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=220)
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
    if args.reuse_existing and out_json.exists():
        try:
            prev_payload = json.loads(out_json.read_text(encoding="utf-8"))
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
        records.append(rec)
        print(
            f"[{idx:2d}/{len(selected)} {tag}] {rec['code']:14s} | {rec['name']:36s} | "
            f"Fz={rec['F_z_pN']:+.4f} pN | A={rec['A_tooth_um2']:.4f} | F/A={rec['F_per_A_pN_per_um2']:+.2f} | "
            f"mod={rec['cantor_mod_amp_pct']:.2f}% | slots={[round(x, 3) for x in rec['f_slots_pN']]}",
            flush=True,
        )

    by_code = {r["code"]: r for r in records}
    factorial_effects = compute_factorial_effects(by_code) if not is_micro else {}

    payload = {
        "generated_at_utc": now_iso,
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

        metrics_to_log: dict[str, float] = {
            "n3_uni3d_f000_fz_pn": f0,
            "n3_uni3d_f1r_sub_fz_pn": f1r_sub,
            "n3_uni3d_f100_r_fz_pn": f1r,
            "n3_uni3d_f010_theta_fz_pn": f1t,
            "n3_uni3d_f001_z_fz_pn": f1z,
            "n3_uni3d_f110_rtheta_planar_fz_pn": f2rt,
            "n3_uni3d_f110_rtheta_planar_fa": float(by_code["F2rt_110"]["F_per_A_pN_per_um2"]),
            "n3_uni3d_f101_rz_fz_pn": f2rz,
            "n3_uni3d_f011_thetaz_fz_pn": f2tz,
            "n3_uni3d_f111_unified_fz_pn": f3,
            "n3_uni3d_f111_unified_fa": float(by_code["F3_111"]["F_per_A_pN_per_um2"]),
            "n3_uni3d_f111_unified_fcirc": float(by_code["F3_111"]["F_circ_sum_pN_per_um"]),
            "n3_uni3d_ctrl_uni000_fz_pn": c1,
            "n3_uni3d_ctrl_uni111_fz_pn": c2,
            "n3_uni3d_ctrl_monogen_fz_pn": c3,
            "n3_uni3d_ctrl_shuffled111_fz_pn": c4,
            "n3_uni3d_ctrl_outphase_fz_pn": c5,
            "n3_uni3d_ctrl_uni12_fz_pn": c6,
            "n3_uni3d_ctrl_lin12_fz_pn": c7,
            "n3_uni3d_ctrl_mono12_fz_pn": c8,
            "n3_uni3d_ctrl_shuf12_fz_pn": c9,
            "n3_uni3d_ctrl_outphase12_fz_pn": c10,
            "n3_uni3d_gain_f111_vs_f000_pct": 100.0 * _safe_div(f3 - f0, f0),
            "n3_uni3d_gain_f111_vs_monogen_pct": 100.0 * _safe_div(f3 - c3, c3),
            "n3_uni3d_gain_f111_vs_shuffled_pct": 100.0 * _safe_div(f3 - c4, c4),
            "n3_uni3d_gain_f111_vs_uni12_pct": 100.0 * _safe_div(f3 - c6, c6),
            "n3_uni3d_gain_f111_vs_lin12_pct": 100.0 * _safe_div(f3 - c7, c7),
            "n3_uni3d_gain_f111_vs_mono12_pct": 100.0 * _safe_div(f3 - c8, c8),
            "n3_uni3d_gain_f111_vs_shuf12_pct": 100.0 * _safe_div(f3 - c9, c9),
            "n3_uni3d_gain_f111_vs_outphase12_pct": 100.0 * _safe_div(f3 - c10, c10),
            "n3_uni3d_gain_f110_planar_vs_monogen_pct": 100.0 * _safe_div(f2rt - c3, c3),
            "n3_uni3d_ratio_f111_vs_uni111": _safe_div(f3, c2),
            "n3_uni3d_main_effect_r_pn": float(factorial_effects["main_effect_r_pN"]),
            "n3_uni3d_main_effect_theta_pn": float(factorial_effects["main_effect_theta_pN"]),
            "n3_uni3d_main_effect_z_pn": float(factorial_effects["main_effect_z_pN"]),
            "n3_uni3d_synergy_3way_pn": float(factorial_effects["synergy_3way_r_theta_z_pN"]),
            "n3_uni3d_mod_amp_f000_pct": float(by_code["F0_000"]["cantor_mod_amp_pct"]),
            "n3_uni3d_mod_amp_f111_pct": float(by_code["F3_111"]["cantor_mod_amp_pct"]),
        }
        for m_key, m_val in metrics_to_log.items():
            log_metric(m_key, m_val, step_id="n3_unified_3d_fractal_factorial_study", solver_name="bem", defer_save=True)
        first_k = next(iter(metrics_to_log))
        log_metric(first_k, metrics_to_log[first_k], step_id="n3_unified_3d_fractal_factorial_study", solver_name="bem", defer_save=False)
        export_macros(str(ROOT / "results" / "provenance_metrics.json"), str(ROOT / "results" / "macros_results.tex"))
        save_plot_provenance(str(out_png), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))
        save_plot_provenance(str(out_pdf), str(ROOT / "results" / "provenance_metrics.json"), list(metrics_to_log.keys()))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
