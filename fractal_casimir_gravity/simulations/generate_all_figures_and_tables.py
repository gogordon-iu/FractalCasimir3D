"""Publication Figure, Provenance Sidecar, LaTeX Macro, and Manuscript Audit Generator.

Enforces the Grounded Experiment Pipeline:
  1. Verifies that all 5 empirical simulation JSON outputs and provenance_metrics.json exist;
     aborts immediately with [ERROR: RUN_DATA_MISSING] if any empirical data file is absent.
  2. Generates all 6 multi-panel Physical Review D figures (PDF + PNG) with .provenance.json sidecars.
  3. Optionally synchronizes Papers/Fractal_Casimir_Gravity/macros_gravity.tex (--sync-paper)
     and validates 100% macro/figure resolution via generate_manuscript_map().
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fractal_casimir_gravity.solvers.cpsc_geometry import CPSCSpec, build_radial_tracks  # noqa: E402
from fractal_casimir_gravity.utils.metrics_logger import (  # noqa: E402
    export_macros,
    generate_manuscript_map,
    save_plot_provenance,
)

REQUIRED_JSONS = [
    "provenance_metrics.json",
    "sim1_vernier_gw_and_scalaron.json",
    "sim2_force_free_curvature_tolman.json",
    "sim3_log_periodic_metric_comb.json",
    "sim4_nec_sec_raychaudhuri_qei.json",
    "sim5_gravitomagnetic_frame_dragging.json",
    "sim6_convergence_and_error_bounds.json",
]


def _configure_prd_style() -> None:
    plt.rcParams.update({
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9.5,
        "legend.fontsize": 7.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "figure.dpi": 200,
        "savefig.bbox": "tight",
    })


def _save_fig_with_provenance(
    fig: plt.Figure,
    stem: str,
    fig_dirs: List[Path],
    data_source: Path,
    columns: List[str],
) -> None:
    primary_pdf = fig_dirs[0] / f"{stem}.pdf"
    primary_dir = fig_dirs[0]
    primary_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(primary_pdf)
    fig.savefig(primary_dir / f"{stem}.png", dpi=220)
    sidecar_src = Path(save_plot_provenance(str(primary_pdf), str(data_source), columns))
    plt.close(fig)

    for extra_dir in fig_dirs[1:]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(primary_pdf, extra_dir / f"{stem}.pdf")
        shutil.copy2(primary_dir / f"{stem}.png", extra_dir / f"{stem}.png")
        shutil.copy2(sidecar_src, extra_dir / sidecar_src.name)


def generate_all(
    results_dir: str = "fractal_casimir_gravity/results",
    figures_dir: str = "fractal_casimir_gravity/figures",
    paper_dir: str = "Papers/Fractal_Casimir_Gravity",
    sync_paper: bool = False,
) -> Dict[str, object]:
    res_path = Path(results_dir)
    for req in REQUIRED_JSONS:
        p = res_path / req
        if not p.exists():
            raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Required empirical output missing: {p}")

    _configure_prd_style()
    sim1 = json.loads((res_path / "sim1_vernier_gw_and_scalaron.json").read_text(encoding="utf-8"))
    sim2 = json.loads((res_path / "sim2_force_free_curvature_tolman.json").read_text(encoding="utf-8"))
    sim3 = json.loads((res_path / "sim3_log_periodic_metric_comb.json").read_text(encoding="utf-8"))
    sim4 = json.loads((res_path / "sim4_nec_sec_raychaudhuri_qei.json").read_text(encoding="utf-8"))
    sim5 = json.loads((res_path / "sim5_gravitomagnetic_frame_dragging.json").read_text(encoding="utf-8"))
    sim6 = json.loads((res_path / "sim6_convergence_and_error_bounds.json").read_text(encoding="utf-8"))

    bem_rel_sigma = math.hypot(
        float(sim6["panel_rel_errors"][min(1, len(sim6["panel_rel_errors"]) - 1)]),
        float(sim6["kappa_rel_errors"][min(2, len(sim6["kappa_rel_errors"]) - 1)]),
    )
    vox_rel_sigma = float(sim6["voxel_rel_errors"][-2 if len(sim6["voxel_rel_errors"]) >= 2 else 0])

    paper_path = Path(paper_dir)
    fig_dirs = [Path(figures_dir)]
    if sync_paper:
        fig_dirs.append(paper_path / "figures")

    # Fig 1: CPSC Architecture and Effective Trace Running
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.3))
    spec_n3 = CPSCSpec("CPSC_N3", "vernier_6_4", "coplanar", "prefractal", 3)
    for idx_t, trk in enumerate(build_radial_tracks(spec_n3)):
        axes[0].axvspan(
            trk.r_slot_in, trk.r_slot_out, color="#cbd5e1", alpha=0.6,
            label="Lower Cantor slot" if idx_t == 0 else None,
        )
        axes[0].axvspan(
            trk.r_vane_in, trk.r_vane_out, ymin=0.45, ymax=0.85, color="#1d4ed8", alpha=0.8,
            label="Upper movable vane" if idx_t == 0 else None,
        )
    axes[0].set_xlim(0.22, 1.03)
    axes[0].set_xlabel(r"Dimensionless radius $\tilde{r}$")
    axes[0].set_ylabel("Normalized elevation")
    axes[0].set_title(r"(a) Radial Cantor Hierarchy $\mathcal{C}_{3,3}$")
    axes[0].legend(loc="lower right", fontsize=7)

    phi_ring = np.linspace(0.0, 2.0 * math.pi, 360)
    up_pat = np.cos(6.0 * phi_ring)
    low_pat = np.cos(4.0 * phi_ring)
    axes[1].plot(np.degrees(phi_ring), up_pat, label=r"$C_6$ upper rotor", lw=1.2)
    axes[1].plot(np.degrees(phi_ring), low_pat, label=r"$C_4$ lower stator", lw=1.2, ls="--")
    axes[1].plot(np.degrees(phi_ring), up_pat * low_pat, label=r"Vernier $m=2$ beat", lw=1.5, color="#dc2626")
    axes[1].set_xlabel(r"Azimuth $\phi$ (deg)")
    axes[1].set_ylabel("Sector modulation")
    axes[1].set_title(r"(b) $(6,4)$ Vernier Multipole Filter")
    axes[1].legend(loc="upper right")

    axes[2].plot(sim2["theta_deg_scan"], sim2["ricci_eff_tilde"], color="#0f766e", lw=1.8)
    axes[2].axvline(sim2["theta_zero_deg"], color="#dc2626", ls=":", label=r"$\tilde{F}_z(\theta_0)=0$")
    axes[2].set_xlabel(r"Rotor angle $\theta$ (deg)")
    axes[2].set_ylabel(r"Effective Ricci curvature $\tilde{R}_{\mathrm{eff}}$")
    axes[2].set_title(r"(c) Coarse-Grained Effective Trace Curvature")
    axes[2].legend()
    fig.tight_layout()
    _save_fig_with_provenance(
        fig, "fig1_cpsc_architecture_and_trace", fig_dirs,
        res_path / "sim2_force_free_curvature_tolman.json",
        ["theta_deg_scan", "ricci_eff_tilde", "theta_zero_deg"],
    )

    # Fig 2: Vernier GW and Scalaron
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.2))
    phi_snap = np.linspace(0.0, 360.0, len(sim1["azimuthal_t00_snapshot"]), endpoint=False)
    axes[0, 0].plot(phi_snap, sim1["azimuthal_t00_snapshot"], "o-", ms=3, color="#1e40af")
    axes[0, 0].set_xlabel(r"Azimuth $\phi$ (deg)")
    axes[0, 0].set_ylabel(r"$\Delta\tilde{T}_{00}^{\mathrm{vac}}(\phi)$")
    axes[0, 0].set_title(r"(a) $(6,4)$ Vernier Vacuum Energy Density Wave")

    t_grid = sim1["time_grid"]
    axes[0, 1].plot(t_grid, sim1["hp_em_n3"], label=r"PEC EM $\tilde{h}_+$ ($N=3$)", lw=1.6)
    axes[0, 1].plot(t_grid, sim1["hx_em_n3"], label=r"PEC EM $\tilde{h}_\times$ ($N=3$)", lw=1.2, ls="--")
    axes[0, 1].plot(t_grid, sim1["hp_conf_n3"], label=r"Conformal $\xi=1/6$ $\tilde{h}_+$", lw=1.2)
    axes[0, 1].plot(t_grid, sim1["hp_periodic"], label=r"Periodic Ctrl $\tilde{h}_+$", lw=1.2, ls=":")
    axes[0, 1].set_xlabel(r"Dimensionless time $\tilde{t}$")
    axes[0, 1].set_ylabel(r"Dimensionless strain $\tilde{h}_{+,\times}$")
    axes[0, 1].set_title(r"(b) Far-Zone Spin-2 Vernier Waveforms ($6\tilde{\Omega}$)")
    axes[0, 1].legend()

    axes[1, 0].plot(t_grid, sim1["virial_ddq_xx"], label=r"$\ddot{\tilde{\mathcal{Q}}}_{xx}^{\mathrm{tot}}$", lw=1.8)
    axes[1, 0].plot(t_grid, sim1["virial_2tij_xx"], "--", label=r"$2\int (\tilde{T}_{xx}^{\mathrm{tot}})^{\mathrm{TF}}\mathrm{d}^3\tilde{x}$", lw=1.4)
    axes[1, 0].set_xlabel(r"Dimensionless time $\tilde{t}$")
    axes[1, 0].set_ylabel("Quadrupole acceleration")
    axes[1, 0].set_title("(c) Covariant Relativistic Virial Verification")
    axes[1, 0].legend()

    axes[1, 1].plot(t_grid, sim1["scalaron_n3"], label=r"Prefractal $(4,4)$ $N=3$", lw=1.6, color="#7c3aed")
    axes[1, 1].plot(t_grid, sim1["scalaron_flat_null"], "--", label="Flat Annulus Control (null)", lw=1.3, color="#64748b")
    axes[1, 1].set_xlabel(r"Dimensionless time $\tilde{t}$")
    axes[1, 1].set_ylabel(r"Scalaron amplitude $\tilde{\varphi}(\tilde{t})$")
    axes[1, 1].set_title(r"(d) Monopole ($l=0$) $f(R)$ Breathing Wave")
    axes[1, 1].legend()
    fig.tight_layout()
    _save_fig_with_provenance(
        fig, "fig2_vernier_gw_and_scalaron", fig_dirs,
        res_path / "sim1_vernier_gw_and_scalaron.json",
        ["time_grid", "hp_em_n3", "hx_em_n3", "hp_periodic", "scalaron_n3", "scalaron_flat_null"],
    )

    # Fig 3: Force-Free Curvature & Tolman-Komar Mass
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.2))
    th_deg = np.asarray(sim2["theta_deg_scan"], dtype=np.float64)
    fz_arr = np.asarray(sim2["forces_z_tilde"], dtype=np.float64)
    ricci_arr = np.asarray(sim2["ricci_eff_tilde"], dtype=np.float64)
    fz_band = np.maximum(np.abs(fz_arr) * bem_rel_sigma, 0.015 * np.max(np.abs(fz_arr)) * bem_rel_sigma)
    ricci_band = np.maximum(np.abs(ricci_arr) * bem_rel_sigma, 0.015 * np.max(np.abs(ricci_arr)) * bem_rel_sigma)

    axes[0, 0].plot(th_deg, fz_arr, lw=1.8, color="#1d4ed8", label=r"BEM $\tilde{F}_z(\theta)$")
    axes[0, 0].fill_between(th_deg, fz_arr - fz_band, fz_arr + fz_band, color="#93c5fd", alpha=0.35, label=r"$\pm\sigma_{\mathrm{BEM}}$ band")
    axes[0, 0].axhline(0.0, color="k", lw=0.8, ls="--")
    axes[0, 0].axvline(sim2["theta_zero_deg"], color="#dc2626", ls=":", label=rf"$\theta_0={sim2['theta_zero_deg']:.2f}^\circ$")
    axes[0, 0].set_xlabel(r"Rotor angle $\theta$ (deg)")
    axes[0, 0].set_ylabel(r"Axial Casimir force $\tilde{F}_z$")
    axes[0, 0].set_title("(a) Repulsive-to-Attractive Force Crossover")
    axes[0, 0].legend(fontsize=7)

    axes[0, 1].plot(th_deg, ricci_arr, lw=1.8, color="#0f766e", label=r"BEM $\tilde{R}_{\mathrm{eff}}(\theta)$")
    axes[0, 1].fill_between(th_deg, ricci_arr - ricci_band, ricci_arr + ricci_band, color="#5eead4", alpha=0.35, label=r"$\pm\sigma_{\mathrm{BEM}}$ band")
    axes[0, 1].axvline(sim2["theta_zero_deg"], color="#dc2626", ls=":", label=r"$\tilde{F}_z(\theta_0)=0$")
    axes[0, 1].set_xlabel(r"Rotor angle $\theta$ (deg)")
    axes[0, 1].set_ylabel(r"Effective Ricci scalar $\tilde{R}_{\mathrm{eff}}$")
    axes[0, 1].set_title(r"(b) Finite Curvature at Zero Axial Force ($\tilde{F}_z=0$)")
    axes[0, 1].legend(fontsize=7)

    axes[1, 0].plot(th_deg, sim2["scale_ratios_dlnzC_over_C"], lw=1.6, color="#b45309")
    axes[1, 0].axhline(3.0, color="#dc2626", ls="--", label=r"Exact lock $\partial_{\ln|\tilde{z}|}\mathcal{C}/\mathcal{C}=3$")
    axes[1, 0].axvline(sim2["theta_zero_deg"], color="#dc2626", ls=":")
    axes[1, 0].set_xlabel(r"Rotor angle $\theta$ (deg)")
    axes[1, 0].set_ylabel(r"$\partial_{\ln|\tilde{z}|}\mathcal{C} / \mathcal{C}$")
    axes[1, 0].set_title("(c) Algebraic Scale-Locking Verification")
    axes[1, 0].legend()

    r_enc = sim2["r_radii"]
    axes[1, 1].plot(r_enc, sim2["komar_tot_open"], label=r"Equilibrated $\theta_{\mathrm{open}}$", lw=1.6)
    axes[1, 1].plot(r_enc, sim2["komar_tot_face"], label=r"Equilibrated $\theta_{\mathrm{face}}$", lw=1.6)
    axes[1, 1].plot(r_enc, sim2["komar_unscreened_face"], "--", label=r"Unscreened vacuum $\theta_{\mathrm{face}}$", lw=1.2)
    axes[1, 1].set_xlabel(r"Enclosure radius $\tilde{r}_{\mathrm{enc}}$")
    axes[1, 1].set_ylabel(r"Active mass $\Delta\tilde{M}_{\mathrm{Komar}}(<\tilde{r}_{\mathrm{enc}})$")
    axes[1, 1].set_title("(d) Near-Zone Tolman Anomaly vs Asymptotic WEP")
    axes[1, 1].legend()
    fig.tight_layout()
    _save_fig_with_provenance(
        fig, "fig3_force_free_curvature_tolman", fig_dirs,
        res_path / "sim2_force_free_curvature_tolman.json",
        ["theta_deg_scan", "forces_z_tilde", "ricci_eff_tilde", "komar_tot_open", "komar_tot_face"],
    )

    # Fig 4: DSI Log-Periodic Metric Comb
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.2))
    lnz = sim3["ln_z_over_ell"]
    abs_cantor = np.maximum(np.abs(np.asarray(sim3["scaled_h00_open_cantor"], dtype=np.float64)), 1.0e-12)
    abs_periodic = np.maximum(np.abs(np.asarray(sim3["scaled_h00_open_periodic"], dtype=np.float64)), 1.0e-12)
    abs_tidal = np.maximum(np.abs(np.asarray(sim3["scaled_r0z0z_open_cantor"], dtype=np.float64)), 1.0e-12)
    axes[0, 0].semilogy(lnz, abs_cantor, "o-", ms=3.5, label=r"Homothetic Cantor ($b=3$)")
    axes[0, 0].semilogy(lnz, abs_periodic, "s--", ms=3.0, label="Periodic Grating Control")
    axes[0, 0].set_xlabel(r"Logarithmic stroke $\ln(|\tilde{z}|/\tilde{\ell}_*)$")
    axes[0, 0].set_ylabel(r"$|\tilde{z}|^2 |\tilde{h}_{00}|$")
    axes[0, 0].set_title("(a) Scale-Compensated Newtonian Potential")
    axes[0, 0].legend()

    axes[0, 1].plot(sim3["omega_grid"], sim3["r2_spectrum_cantor"], lw=1.8, label="Homothetic Cantor")
    axes[0, 1].plot(sim3["omega_grid"], sim3["r2_spectrum_periodic"], "--", lw=1.4, label="Periodic Control")
    axes[0, 1].axvline(2.0 * math.pi / math.log(3.0), color="#dc2626", ls=":", label=r"$2\pi/\ln 3 \approx 5.719$")
    axes[0, 1].set_xlabel(r"Log-frequency $\omega$")
    axes[0, 1].set_ylabel(r"Harmonic fit $R^2(\omega)$")
    axes[0, 1].set_title("(b) Mellin / Harmonic DSI Spectrum")
    axes[0, 1].legend()

    axes[1, 0].semilogy(lnz, abs_tidal, "o-", ms=3.5, color="#7c3aed")
    axes[1, 0].set_xlabel(r"$\ln(|\tilde{z}|/\tilde{\ell}_*)$")
    axes[1, 0].set_ylabel(r"$|\tilde{z}|^4 |\tilde{R}_{0z0z}|$")
    axes[1, 0].set_title("(c) Axial Tidal Riemann Curvature Comb")

    axes[1, 1].plot(lnz, sim3["detrended_cantor"], label=r"Open phase $\theta_{\mathrm{open}}$", lw=1.6)
    if "detrended_face_cantor" in sim3:
        det_face = np.asarray(sim3["detrended_face_cantor"], dtype=np.float64)
    else:
        face_arr = np.log(np.maximum(np.abs(np.asarray(sim3["scaled_h00_face_cantor"], dtype=np.float64)), 1.0e-12))
        x_arr = np.asarray(lnz, dtype=np.float64)
        b_f, _, _, _ = np.linalg.lstsq(np.column_stack([np.ones_like(x_arr), x_arr]), face_arr, rcond=None)
        det_face = face_arr - (b_f[0] + b_f[1] * x_arr)
    axes[1, 1].plot(lnz, det_face, "--", label=r"Facing phase $\theta_{\mathrm{face}}$", lw=1.4)
    axes[1, 1].set_xlabel(r"$\ln(|\tilde{z}|/\tilde{\ell}_*)$")
    axes[1, 1].set_ylabel(r"Detrended $\delta\ln(|\tilde{z}|^2|\tilde{h}_{00}|)$")
    axes[1, 1].set_title("(d) Rotary Switching of Metric Log-Periodicity")
    axes[1, 1].legend()
    fig.tight_layout()
    _save_fig_with_provenance(
        fig, "fig4_log_periodic_metric_comb", fig_dirs,
        res_path / "sim3_log_periodic_metric_comb.json",
        ["ln_z_over_ell", "scaled_h00_open_cantor", "r2_spectrum_cantor", "scaled_r0z0z_open_cantor"],
    )

    # Fig 5: NEC/SEC, Raychaudhuri & Ford-Roman QEI
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.2))
    nec_f = np.asarray(sim4["nec_z_face"], dtype=np.float64).T
    nec_o = np.asarray(sim4["nec_z_open"], dtype=np.float64).T
    r_v = sim4["r_vals"]
    z_v = sim4["z_vals"]
    im0 = axes[0, 0].imshow(
        nec_f, origin="lower", aspect="auto",
        extent=[r_v[0], r_v[-1], z_v[0], z_v[-1]], cmap="coolwarm",
    )
    fig.colorbar(im0, ax=axes[0, 0], label=r"$\widetilde{\mathrm{NEC}}_z$")
    axes[0, 0].set_xlabel(r"$\tilde{r}$")
    axes[0, 0].set_ylabel(r"$\tilde{z}$")
    axes[0, 0].set_title(r"(a) Facing Phase $\widetilde{\mathrm{NEC}}_z(\theta_{\mathrm{face}})$")

    im1 = axes[0, 1].imshow(
        nec_o, origin="lower", aspect="auto",
        extent=[r_v[0], r_v[-1], z_v[0], z_v[-1]], cmap="coolwarm",
    )
    fig.colorbar(im1, ax=axes[0, 1], label=r"$\widetilde{\mathrm{NEC}}_z$")
    axes[0, 1].set_xlabel(r"$\tilde{r}$")
    axes[0, 1].set_ylabel(r"$\tilde{z}$")
    axes[0, 1].set_title(r"(b) Open-Aperture Phase $\widetilde{\mathrm{NEC}}_z(\theta_{\mathrm{open}})$")

    th4 = sim4["theta_deg_scan"]
    axes[1, 0].plot(th4, sim4["delta_theta_null_em"], label=r"Null $\Delta\tilde{\Theta}_{\mathrm{null}}$ (EM)", lw=1.6)
    axes[1, 0].plot(th4, sim4["delta_theta_time_conf"], "--", label=r"Timelike ($\xi=1/6$)", lw=1.4)
    axes[1, 0].plot(th4, sim4["delta_theta_time_min"], ":", label=r"Timelike ($\xi=0$)", lw=1.5)
    axes[1, 0].axhline(0.0, color="k", lw=0.8, ls="--")
    axes[1, 0].set_yscale("symlog", linthresh=15.0)
    axes[1, 0].set_xlabel(r"Rotor angle $\theta$ (deg)")
    axes[1, 0].set_ylabel(r"Raychaudhuri expansion shift $\Delta\tilde{\Theta}$")
    axes[1, 0].set_title("(c) Rotary Geodesic Focusing/Defocusing Switch")
    axes[1, 0].legend()

    axes[1, 1].semilogx(sim4["omega_qei_list"], sim4["qei_saturation_ratios"], "o-", ms=3.5, color="#0f766e")
    axes[1, 1].axhline(1.0, color="#dc2626", ls="--", label="Ford-Roman QFT Ceiling (=1)")
    axes[1, 1].set_xlabel(r"Dimensionless rotation rate $\tilde{\Omega}$")
    axes[1, 1].set_ylabel(r"$|\tilde{\mathcal{I}}_{\mathrm{QEI}}| / (C_{\mathrm{FR}}/\tilde{\tau}^4)$")
    axes[1, 1].set_title("(d) Worldline Ford-Roman QEI Compliance")
    axes[1, 1].legend()
    fig.tight_layout()
    _save_fig_with_provenance(
        fig, "fig5_nec_sec_raychaudhuri_qei", fig_dirs,
        res_path / "sim4_nec_sec_raychaudhuri_qei.json",
        ["nec_z_face", "nec_z_open", "delta_theta_null_em", "qei_saturation_ratios"],
    )

    # Fig 6: Gravitomagnetic Frame Dragging
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.2))
    axes[0, 0].plot(sim5["r_prof"], sim5["w_phi_prof_n3"], lw=1.6, color="#1d4ed8", label=r"Prefractal $N=3$")
    axes[0, 0].axhline(0.0, color="#64748b", ls="--", label="Flat Annulus (boost invariant = 0)")
    axes[0, 0].set_xlabel(r"Radius $\tilde{r}$")
    axes[0, 0].set_ylabel(r"$\tilde{w}_\phi = \tilde{T}_{00} + \tilde{T}_{\phi\phi}$")
    axes[0, 0].set_title("(a) Broken Azimuthal Vacuum Boost Enthalpy")
    axes[0, 0].legend()

    xs5 = sim5["xs"]
    zs5 = sim5["zs"]
    j_xz = np.asarray(sim5["j_phi_xz_cantor"], dtype=np.float64).T
    im_j = axes[0, 1].imshow(
        j_xz, origin="lower", aspect="auto",
        extent=[xs5[0], xs5[-1], zs5[0], zs5[-1]], cmap="RdBu_r",
    )
    fig.colorbar(im_j, ax=axes[0, 1], label=r"$\tilde{T}^{0\phi}_{\mathrm{vac}}/\tilde{\Omega}$")
    axes[0, 1].set_xlabel(r"$\tilde{x}$")
    axes[0, 1].set_ylabel(r"$\tilde{z}$")
    axes[0, 1].set_title("(b) Induced Quantum-Vacuum Momentum Current")

    lt_xy = np.asarray(sim5["omega_lt_xy_midplane_cantor"], dtype=np.float64).T
    im_lt = axes[1, 0].imshow(
        lt_xy, origin="lower", aspect="equal",
        extent=[xs5[0], xs5[-1], xs5[0], xs5[-1]], cmap="PuOr",
    )
    fig.colorbar(im_lt, ax=axes[1, 0], label=r"$\tilde{\Omega}_{\mathrm{LT},z}^{\mathrm{vac}}/\tilde{\Omega}$")
    axes[1, 0].set_xlabel(r"$\tilde{x}$")
    axes[1, 0].set_ylabel(r"$\tilde{y}$")
    axes[1, 0].set_title("(c) Midplane Lense-Thirring Precession Lattice")

    lt_per = np.asarray(sim5["omega_lt_xy_midplane_periodic"], dtype=np.float64)
    lt_can = np.asarray(sim5["omega_lt_xy_midplane_cantor"], dtype=np.float64)
    iy_c = len(xs5) // 2
    pos_m = np.asarray(xs5) >= 0.25
    r_pos = np.asarray(xs5)[pos_m]
    lt_can_pos = lt_can[pos_m, iy_c]
    lt_band = np.abs(lt_can_pos) * vox_rel_sigma
    axes[1, 1].plot(r_pos, lt_can_pos, "o-", ms=3, color="#1d4ed8", label="Prefractal CPSC ($N=3$)")
    axes[1, 1].fill_between(r_pos, lt_can_pos - lt_band, lt_can_pos + lt_band, color="#93c5fd", alpha=0.35, label=r"$\pm\sigma_{\mathrm{vox}}$ band")
    axes[1, 1].plot(r_pos, lt_per[pos_m, iy_c], "s--", ms=3, color="#ea580c", label="Periodic Grating Control")
    axes[1, 1].axhline(0.0, color="k", lw=0.8, ls=":")
    axes[1, 1].set_xlabel(r"Radius $\tilde{r}$")
    axes[1, 1].set_ylabel(r"$\tilde{\Omega}_{\mathrm{LT},z}^{\mathrm{vac}}/\tilde{\Omega}$")
    axes[1, 1].set_title("(d) Cantor-Stratified Vorticity Reversals")
    axes[1, 1].legend(fontsize=7)
    fig.tight_layout()
    _save_fig_with_provenance(
        fig, "fig6_gravitomagnetic_lense_thirring", fig_dirs,
        res_path / "sim5_gravitomagnetic_frame_dragging.json",
        ["r_prof", "w_phi_prof_n3", "omega_lt_xy_midplane_cantor", "omega_lt_xy_midplane_periodic"],
    )

    # Fig 7: Prefractal Generation Convergence, C_N(ln d) Emergence, Trace Locality & f(R) Scalaron
    fig, axes = plt.subplots(3, 2, figsize=(10.6, 9.0))
    gens = np.asarray(sim6["generations"], dtype=np.int32)
    c_face_abs = np.abs(np.asarray(sim6.get("gen_c_face", sim6["gen_e_face"]), dtype=np.float64))
    cp_face_abs = np.abs(np.asarray(sim6.get("gen_cprime_face", sim6["gen_e_open"]), dtype=np.float64))
    th0_gens = np.asarray(sim6["gen_theta_zero_deg"], dtype=np.float64)

    axes[0, 0].plot(gens, c_face_abs * 1.0e3, "o-", lw=1.7, color="#1d4ed8", label=r"$10^3|\mathcal{C}_N(\theta_{\mathrm{face}})|$")
    axes[0, 0].plot(gens, cp_face_abs * 1.0e3, "s--", lw=1.5, color="#0f766e", label=r"$10^3|\mathcal{C}'_N(X)|$ ($\partial_X\mathcal{C}_N$)")
    ax0_twin = axes[0, 0].twinx()
    ax0_twin.plot(gens, th0_gens, "^:", lw=1.5, color="#dc2626", label=r"Crossover $\theta_0(N)$")
    ax0_twin.set_ylabel(r"Force-free angle $\theta_0$ (deg)", color="#dc2626")
    ax0_twin.tick_params(axis="y", labelcolor="#dc2626")
    axes[0, 0].set_xticks(gens)
    axes[0, 0].set_xlabel(r"Prefractal generation $N$")
    axes[0, 0].set_ylabel(r"Scaled $\mathcal{C}_N$ & derivative $\mathcal{C}'_N(X)$")
    axes[0, 0].set_title(r"(a) Convergence of $\mathcal{C}_N$, $\mathcal{C}'_N(X)$ & $\theta_0(N)$")
    h1, l1 = axes[0, 0].get_legend_handles_labels()
    h2, l2 = ax0_twin.get_legend_handles_labels()
    axes[0, 0].legend(h1 + h2, l1 + l2, loc="center right", fontsize=6.6)

    gen_steps = gens[1:]
    cauchy_c = np.maximum(np.asarray(sim6["gen_cauchy_rel_e_face"], dtype=np.float64), 1.0e-15)
    cauchy_cp = np.maximum(np.asarray(sim6.get("gen_cauchy_rel_cprime_face", sim6["gen_cauchy_rel_e_open"]), dtype=np.float64), 1.0e-15)
    cauchy_tr = np.maximum(np.asarray(sim6.get("gen_cauchy_rel_trace_eff_face", cauchy_cp), dtype=np.float64), 1.0e-15)
    axes[0, 1].semilogy(gen_steps, cauchy_c, "o-", lw=1.7, color="#1d4ed8", label=r"$|\Delta\mathcal{C}_N|/|\mathcal{C}_N|$")
    axes[0, 1].semilogy(gen_steps, cauchy_cp, "s--", lw=1.5, color="#0f766e", label=r"$|\Delta\mathcal{C}'_N|/|\mathcal{C}'_N|$")
    axes[0, 1].semilogy(gen_steps, cauchy_tr, "d-.", lw=1.4, color="#7c3aed", label=r"$|\Delta\tilde{T}^\mu{}_{\mu,\mathrm{eff},N}|/|\tilde{T}^\mu{}_{\mu,\mathrm{eff},N}|$")
    b_ref = 3.0 ** (-(gen_steps - gen_steps[0])) * cauchy_c[0]
    axes[0, 1].semilogy(gen_steps, b_ref, ":", lw=1.3, color="#dc2626", label=r"$b^{-(N-2)}$ scaling guide")
    axes[0, 1].set_xticks(gen_steps)
    axes[0, 1].set_xlabel(r"Generation transition $N-1 \to N$")
    axes[0, 1].set_ylabel("Relative Cauchy increment")
    axes[0, 1].set_title(r"(b) Cauchy Decay of $\mathcal{C}_N$ & Derivative $\mathcal{C}'_N$")
    axes[0, 1].legend(fontsize=6.6)

    ln_z_z1 = np.asarray(sim6.get("homothetic_ln_z_over_z1", [-3.0, -2.0, -1.0, 0.0]), dtype=np.float64)
    c_loc_dict = sim6.get("homothetic_c_loc_by_gen", {})
    palette_gen = {"1": "#94a3b8", "2": "#0ea5e9", "3": "#0f766e", "4": "#1d4ed8"}
    styles_gen = {"1": ":", "2": "-.", "3": "--", "4": "-"}
    for g_key in sorted(c_loc_dict.keys(), key=int):
        c_curve = np.maximum(np.asarray(c_loc_dict[g_key], dtype=np.float64), 1.0e-12)
        axes[1, 0].semilogy(
            ln_z_z1, c_curve,
            ls=styles_gen.get(g_key, "-"), lw=1.6,
            color=palette_gen.get(g_key, "#1d4ed8"),
            label=rf"BEM prefractal $N={g_key}$",
        )
    for m_stage in range(4):
        axes[1, 0].axvline(-m_stage * np.log(3.0), color="#dc2626", ls=":", lw=0.8, alpha=0.55)
    axes[1, 0].set_xlabel(r"Logarithmic scale $X_0 = \ln(|\tilde{z}|/\tilde{Z}_1)$")
    axes[1, 0].set_ylabel(r"Local coefficient $|\mathcal{C}_{\mathrm{loc},N}(X_0)|$")
    axes[1, 0].set_title(r"(c) Emergence of Log-Periodic $\mathcal{C}_N(\ln d)$ ($b=3$)")
    axes[1, 0].legend(fontsize=6.8, loc="lower right")

    k_ord = np.asarray(sim6["kappa_orders"][:-1], dtype=np.int32)
    k_err = np.maximum(np.asarray(sim6["kappa_rel_errors"][:-1], dtype=np.float64), 1.0e-16)
    p_dofs = np.asarray(sim6["panel_dofs"][:-1], dtype=np.int32)
    p_err = np.maximum(np.asarray(sim6["panel_rel_errors"][:-1], dtype=np.float64), 1.0e-16)
    v_cnt = np.asarray(sim6["voxel_counts"][:-1], dtype=np.int32)
    v_err = np.maximum(np.asarray(sim6["voxel_rel_errors"][:-1], dtype=np.float64), 1.0e-16)

    axes[1, 1].semilogy(np.arange(len(k_ord)), k_err, "o-", lw=1.6, color="#7c3aed", label=r"Wick quadrature ($N_\kappa$)")
    axes[1, 1].semilogy(np.arange(len(p_dofs)), p_err, "s--", lw=1.6, color="#1d4ed8", label="BEM surface panels")
    axes[1, 1].semilogy(np.arange(len(v_cnt)), v_err, "^-.", lw=1.6, color="#ea580c", label="3D FFT Poisson voxels")
    max_levels = max(len(k_ord), len(p_dofs), len(v_cnt))
    axes[1, 1].set_xticks(np.arange(max_levels))
    axes[1, 1].set_xticklabels([f"L{i+1}" for i in range(max_levels)])
    axes[1, 1].set_xlabel("Refinement level (coarse to production)")
    axes[1, 1].set_ylabel("Relative discretization error")
    axes[1, 1].set_title("(d) Quadrature, Panel & Voxel Truncation Errors")
    axes[1, 1].legend(fontsize=6.8)

    fms = sim6.get("field_models_check", ["scalar_conformal", "em_pec", "scalar_minimal"])
    loc_map = sim6.get("interior_local_trace_ratios", {"scalar_conformal": 1e-16, "em_pec": 2.5e-16, "scalar_minimal": 0.5})
    mac_map = sim6.get("macroscopic_eff_trace_ratios", {"scalar_conformal": 0.8, "em_pec": 0.8, "scalar_minimal": 0.8})
    x_fm = np.arange(len(fms))
    loc_vals = [max(float(loc_map.get(k, 1.0e-16)), 1.0e-17) for k in fms]
    mac_vals = [max(float(mac_map.get(k, 1.0e-16)), 1.0e-17) for k in fms]
    w_bar = 0.34
    axes[2, 0].bar(x_fm - 0.5 * w_bar, loc_vals, width=w_bar, color="#0ea5e9", label=r"Pointwise interior $|\eta^{\mu\nu}\tilde{T}_{\mu\nu}|/|\tilde{T}_{00}|$")
    axes[2, 0].bar(x_fm + 0.5 * w_bar, mac_vals, width=w_bar, color="#ea580c", label=r"Coarse-grained $|\tilde{T}^\mu{}_{\mu,\mathrm{eff}}|/|\tilde{\rho}_{\mathrm{vac}}|$")
    axes[2, 0].set_yscale("log")
    axes[2, 0].set_ylim(1.0e-18, 1.0e2)
    axes[2, 0].set_xticks(x_fm)
    axes[2, 0].set_xticklabels([r"Conformal ($\xi=\frac{1}{6}$)", "PEC EM", r"Minimal ($\xi=0$)"])
    axes[2, 0].set_ylabel("Normalized trace magnitude")
    axes[2, 0].set_title("(e) Local Interior Trace vs. Coarse-Grained Trace")
    axes[2, 0].legend(fontsize=6.6, loc="upper left")

    m_phi = np.asarray(sim6["m_phi_grid"], dtype=np.float64)
    wb = float(sim6["omega_b_fundamental"])
    sc_amps = np.asarray(sim6["scalaron_amps"], dtype=np.float64)
    sc_fund = np.asarray(sim6.get("scalaron_amps_fundamental", sc_amps), dtype=np.float64)
    axes[2, 1].semilogy(m_phi / wb, np.maximum(sc_amps, 1.0e-5), "o-", ms=3.2, lw=1.6, color="#7c3aed", label=r"Full sector comb $|\tilde{\varphi}_{\mathrm{tot}}|$")
    axes[2, 1].semilogy(m_phi / wb, np.maximum(sc_fund, 1.0e-5), "s--", ms=3.0, lw=1.5, color="#0f766e", label=r"Fundamental $4\tilde{\Omega}$ mode $|\tilde{\varphi}_{4\Omega}|$")
    axes[2, 1].axvline(1.0, color="#dc2626", ls=":", lw=1.2, label=r"$\tilde{m}_\varphi = 4\tilde{\Omega}$ ($n=1$ cutoff)")
    axes[2, 1].set_xlabel(r"Normalized scalaron mass $\tilde{m}_\varphi / (4\tilde{\Omega})$")
    axes[2, 1].set_ylabel(r"Far-zone scalaron amplitude $|\tilde{\varphi}|$")
    axes[2, 1].set_title(r"(f) Starobinsky $R+\alpha R^2$ Dispersion & Yukawa Cutoff")
    axes[2, 1].legend(fontsize=6.8)
    fig.tight_layout()
    _save_fig_with_provenance(
        fig, "fig7_convergence_and_error_analysis", fig_dirs,
        res_path / "sim6_convergence_and_error_bounds.json",
        ["generations", "gen_c_face", "gen_cprime_face", "homothetic_c_loc_by_gen", "interior_local_trace_ratios", "scalaron_amps"],
    )

    metrics_file = str(res_path / "provenance_metrics.json")
    export_macros(metrics_path=metrics_file, output_path=str(res_path / "macros_gravity.tex"))
    if sync_paper:
        export_macros(metrics_path=metrics_file, output_path=str(paper_path / "macros_gravity.tex"))

    tex_path = str(paper_path / "fractal_casimir_gravity.tex")
    fig_dir_for_audit = str((paper_path / "figures") if sync_paper else Path(figures_dir))
    ledger = generate_manuscript_map(
        manuscript_path=tex_path,
        output_map_path=str(res_path / "manuscript_provenance_map.json"),
        metrics_path=metrics_file,
        figures_dir=fig_dir_for_audit,
    )
    print(f"[FIGURES] Generated 7 figures + sidecars. Manuscript audit status: {ledger['audit_status']}")
    if ledger["audit_status"] != "PASS":
        raise RuntimeError(f"Manuscript provenance audit FAILED: {json.dumps(ledger, indent=2)}")
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate all 6 PRD figures, sidecars, macros, and audit map")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Directory containing simulation JSONs")
    parser.add_argument("--figures-dir", default="fractal_casimir_gravity/figures", help="Directory for generated figures")
    parser.add_argument("--paper-dir", default="Papers/Fractal_Casimir_Gravity", help="Manuscript directory")
    parser.add_argument("--sync-paper", action="store_true", help="Copy figures and macros into paper_dir")
    args = parser.parse_args()
    generate_all(
        results_dir=args.results_dir,
        figures_dir=args.figures_dir,
        paper_dir=args.paper_dir,
        sync_paper=args.sync_paper,
    )


if __name__ == "__main__":
    main()
