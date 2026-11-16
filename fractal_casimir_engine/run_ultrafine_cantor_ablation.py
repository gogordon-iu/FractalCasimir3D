#!/usr/bin/env python3
"""Suite 5 (eng_uf5): Cantor Generation Scaling (N=0,1,2,3) & Non-Fractal Controls.

Answers the foundational referee question *"Why must the engine be fractal?"* across
fixed radial footprint R in [0.20, 1.10] um (span = 0.90 um) on Sym_Baseline_CantorN2,
Config_B_Manhattan_Vernier, and Config_D_DualStator_PushPull across five radial hierarchies:
  1. N0_Macro_Ring   (N=0, 1 wide channel W=500 nm matched to N=2 total slot width)
  2. Cantor_N1       (N=1, 1 middle-third lacuna W=300 nm)
  3. Cantor_N2       (N=2, 3 prefractal tracks: 1x300 nm + 2x100 nm, sum W = 500 nm)
  4. Uniform_3Track  (Periodic control: 3x166.67 nm equal rings, matched count=3 & sum W=500 nm)
  5. Cantor_N3       (N=3, 7 prefractal tracks: 1x300 nm + 2x100 nm + 4x33.33 nm)

For every (design, hierarchy) pair, checkpoints:
  - Stroke I & III 3x3 Gauss-Legendre BEM energies, forces, and torques
  - 2D (z_tip, theta) cycle landscape (6 x 30 = 180 states, 3-deg sampling), two-stroke work,
    cogging roughness, and 180 us gated 2-DOF spin-up with hierarchy-exact rotor inertia
  - Full non-Bloch 4-sector 6-DOF lateral/tilt pull-in stiffnesses & torque-to-pull-in FOM
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fractal_casimir_engine.bem_cycle_solver import (
    Full4Sector6DofBemEvaluator,
    PreparedEngineBemModel,
    detect_compute_device,
)
from fractal_casimir_engine.geometries import (
    ENGINE_Z_TIP_MAX_UM,
    ENGINE_Z_TIP_MIN_UM,
    HIERARCHY_NAMES,
    SECTOR_DEG,
    build_hierarchy_tracks,
)
from fractal_casimir_engine.run_engine_cycle_mapping import (
    PeriodicHermitePotential2D,
    cycle_z_profile_um,
    rotor_inertia_properties,
    simulate_coupled_dynamics,
)
from utils.metrics_logger import (
    export_macros,
    log_metric,
    log_step,
    save_plot_provenance,
    set_solver_provenance,
)

ENGINE_DIR = PROJECT_ROOT / "fractal_casimir_engine"
UF_RESULTS_DIR = ENGINE_DIR / "results" / "ultrafine"
ENGINE_FIGURES_DIR = ENGINE_DIR / "figures"

ABLATION_DESIGNS: tuple[str, ...] = (
    "Sym_Baseline_CantorN2",
    "Config_B_Manhattan_Vernier",
    "Config_D_DualStator_PushPull",
)

BENCHMARK_STATES: tuple[tuple[str, float, float], ...] = (
    ("Stroke_I_Repulsive", -0.092, 22.0),
    ("Stroke_III_Attractive", -0.084, 64.0),
)
HESSIAN_POSE_ANGLES_DEG: tuple[float, ...] = (22.0, 34.0, 64.0)


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


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        d = json.load(handle)
    return d if isinstance(d, dict) else None


def check_walltime(started_mono: float, max_walltime_hours: float) -> None:
    if max_walltime_hours > 0.0 and (time.monotonic() - started_mono) >= max_walltime_hours * 3600.0:
        raise TimeoutError("Approaching Slurm walltime limit; checkpoint saved cleanly for auto-resubmit.")


def _evaluate_cycle_work_on_hermite(pot: PeriodicHermitePotential2D) -> dict[str, float]:
    """Evaluate up-stroke [4, 42] deg, down-stroke [42, 80] deg, and closed-loop work on Hermite surface."""
    th_dense = np.linspace(4.0, 94.0, 361, dtype=np.float64)
    z_arr = np.empty_like(th_dense)
    fz_arr = np.empty_like(th_dense)
    tau_arr = np.empty_like(th_dense)
    for i, th_d in enumerate(th_dense):
        z_u, _ = cycle_z_profile_um(float(th_d % SECTOR_DEG))
        _, fz_v, tau_v = pot.eval_e_fz_tau(z_u, float(th_d % SECTOR_DEG))
        z_arr[i] = z_u
        fz_arr[i] = fz_v
        tau_arr[i] = tau_v

    th_rad = np.deg2rad(th_dense)
    dz = np.diff(z_arr)
    dth = np.diff(th_rad)
    dw = 0.5 * (fz_arr[:-1] + fz_arr[1:]) * dz + 0.5 * (tau_arr[:-1] + tau_arr[1:]) * dth
    th_mid = 0.5 * (th_dense[:-1] + th_dense[1:])

    mask_up = (th_mid >= 4.0) & (th_mid <= 42.0)
    mask_down = (th_mid > 42.0) & (th_mid <= 80.0)
    mask_exit = th_mid > 80.0

    w_up = float(np.sum(dw[mask_up]))
    w_down = float(np.sum(dw[mask_down]))
    w_exit = float(np.sum(dw[mask_exit]))
    w_loop = float(np.sum(dw))
    d2_tau = np.diff(tau_arr[:-1], n=2)
    cogging_roughness = float(np.sqrt(np.mean(d2_tau**2))) if d2_tau.size > 0 else 0.0
    return {
        "w_up_aJ": w_up,
        "w_down_aJ": w_down,
        "w_power_strokes_aJ": w_up + w_down,
        "w_exit_aJ": w_exit,
        "hermite_closed_loop_work_aJ": abs(w_loop),
        "cogging_second_diff_roughness": cogging_roughness,
    }


def generate_uf5_figure(
    report: dict[str, Any],
    fig_png: Path,
    fig_pdf: Path,
    rep_path: Path,
    solver_params: dict[str, Any],
) -> None:
    """Render 4-panel Cantor Generation & Non-Fractal Hierarchy Ablation figure."""
    fig_png.parent.mkdir(parents=True, exist_ok=True)
    short_h = {
        "N0_Macro_Ring": "N=0\n(Macro 1-Trk)",
        "Cantor_N1": "Cantor\nN=1 (1-Trk)",
        "Uniform_3Track": "Uniform\n3-Trk Ctrl",
        "Cantor_N2": "Cantor\nN=2 (3-Trk)",
        "Cantor_N3": "Cantor\nN=3 (7-Trk)",
    }
    order_h = ("N0_Macro_Ring", "Cantor_N1", "Uniform_3Track", "Cantor_N2", "Cantor_N3")
    colors = {
        "Sym_Baseline_CantorN2": "#555555",
        "Config_B_Manhattan_Vernier": "#1f77b4",
        "Config_D_DualStator_PushPull": "#d62728",
    }
    labels = {
        "Sym_Baseline_CantorN2": "Sym Control",
        "Config_B_Manhattan_Vernier": "Config B (Manhattan)",
        "Config_D_DualStator_PushPull": "Config D (Dual-Stator)",
    }

    x = np.arange(len(order_h), dtype=np.float64)
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9.6), dpi=220)

    # Panel A: Mean Dual-Stroke Forward Torque vs Hierarchy
    ax_a = axes[0, 0]
    w_bar = 0.25
    for idx_d, dname in enumerate(ABLATION_DESIGNS):
        vals = []
        for h in order_h:
            rec = report["matrix"][dname][h]
            t1 = float(rec["benchmark_states"]["Stroke_I_Repulsive"]["tau_theta_pN_um"])
            t3 = float(rec["benchmark_states"]["Stroke_III_Attractive"]["tau_theta_pN_um"])
            vals.append(0.5 * (t1 + t3))
        ax_a.bar(x + (idx_d - 1) * w_bar, vals, width=w_bar, color=colors[dname], label=labels[dname])
    ax_a.axhline(0.0, color="black", linewidth=0.8)
    ax_a.set_xticks(x)
    ax_a.set_xticklabels([short_h[h] for h in order_h], fontsize=8.5)
    ax_a.set_ylabel(r"Mean Dual-Stroke Torque $\overline{\tau}_\theta$ ($\mathrm{pN\cdot\mu m}$)")
    ax_a.set_title("A. Dual-Stroke Chiral Torque Across Hierarchies")
    ax_a.grid(True, axis="y", alpha=0.3)
    ax_a.legend(fontsize=8)

    # Panel B: Two-Stroke Harvested Cycle Work W_up + W_down (aJ)
    ax_b = axes[0, 1]
    for idx_d, dname in enumerate(ABLATION_DESIGNS):
        vals = [float(report["matrix"][dname][h]["cycle_energetics"]["w_power_strokes_aJ"]) for h in order_h]
        ax_b.bar(x + (idx_d - 1) * w_bar, vals, width=w_bar, color=colors[dname], label=labels[dname])
    ax_b.axhline(0.0, color="black", linewidth=0.8)
    ax_b.set_xticks(x)
    ax_b.set_xticklabels([short_h[h] for h in order_h], fontsize=8.5)
    ax_b.set_ylabel(r"Two-Stroke Harvested Work $W_{\mathrm{up}} + W_{\mathrm{down}}$ (aJ)")
    ax_b.set_title("B. Reciprocating Cycle Work Harvest")
    ax_b.grid(True, axis="y", alpha=0.3)
    ax_b.legend(fontsize=8)

    # Panel C: Gated 2-DOF Autonomous Spin-Up Delta theta (deg)
    ax_c = axes[1, 0]
    for dname in ABLATION_DESIGNS:
        vals = [float(report["matrix"][dname][h]["gated_dynamics"]["net_rotation_deg"]) for h in order_h]
        ax_c.plot(x, vals, marker="o", linewidth=2.0, color=colors[dname], label=labels[dname])
    ax_c.axhline(360.0, color="#333333", linestyle="--", linewidth=0.9, label=r"Full $360^\circ$ Revolution")
    ax_c.set_xticks(x)
    ax_c.set_xticklabels([short_h[h] for h in order_h], fontsize=8.5)
    ax_c.set_ylabel(r"Gated 2-DOF Net Advance $\Delta\theta$ ($^\circ$, $180\ \mu\mathrm{s}$)")
    ax_c.set_title("C. Inertia-Normalized Multi-Sector Spin-Up")
    ax_c.grid(True, alpha=0.3)
    ax_c.legend(fontsize=8)

    # Panel D: Torque-to-Pull-In Stability Figure of Merit
    ax_d = axes[1, 1]
    for dname in ("Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull"):
        vals = [float(report["matrix"][dname][h]["stability_6dof"]["torque_to_pullin_fom_nm_um"]) for h in order_h]
        ax_d.plot(x, vals, marker="s", linewidth=2.0, color=colors[dname], label=labels[dname])
    ax_d.set_xticks(x)
    ax_d.set_xticklabels([short_h[h] for h in order_h], fontsize=8.5)
    ax_d.set_ylabel(r"Stability FOM $\overline{\tau}_\theta / K_{\mathrm{lat}}^{\mathrm{destab}}$ ($\mathrm{pN\cdot\mu m / (mN/m)}$)")
    ax_d.set_title("D. Chiral Torque per Unit Lateral Pull-In Stiffness")
    ax_d.grid(True, alpha=0.3)
    ax_d.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(fig_png, dpi=240)
    fig.savefig(fig_pdf)
    plt.close(fig)

    for fp in (fig_png, fig_pdf):
        save_plot_provenance(
            str(fp),
            str(rep_path),
            columns_used=["matrix", "summary"],
            solver_name="BEM_UltraFine_3D_CantorHierarchyAblation",
            solver_parameters=solver_params,
        )


def run_micro_probe(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    device = detect_compute_device(args.device)
    samples: dict[str, Any] = {}
    for h in ("N0_Macro_Ring", "Cantor_N2", "Uniform_3Track", "Cantor_N3"):
        model = PreparedEngineBemModel(
            "Config_D_DualStator_PushPull",
            n_r=1,
            n_phi_tooth=2,
            n_phi_bridge=2,
            n_z=1,
            n_xi=min(max(1, int(args.max_steps)), 3),
            quad_order=2,
            hierarchy=h,
            device=device,
            lazy_self_cache=True,
        )
        st = model.evaluate_states_batch([(-0.092, 22.0)], max_steps=args.max_steps)[0]
        samples[h] = {
            "n_dofs_total": 4 * (model.nr_dof + model.ns_dof),
            "Stroke_I": st,
        }

    out_path = UF_RESULTS_DIR / "probe_uf5_cantor_ablation_report.json"
    payload = {
        "suite": "eng_uf5",
        "status": "micro_probe_completed",
        "time_truncated": True,
        "max_steps": int(args.max_steps),
        "device": device,
        "elapsed_seconds": time.perf_counter() - started,
        "samples": samples,
    }
    atomic_write_json(out_path, payload)
    print(f"[UF5 MICRO-PROBE] Completed in {payload['elapsed_seconds']:.2f}s -> {out_path}", flush=True)
    return 0


def run_full_campaign(args: argparse.Namespace) -> int:
    started_mono = time.monotonic()
    started_wall = time.perf_counter()
    device = detect_compute_device(args.device)
    chk_dir = args.checkpoint_dir
    chk_dir.mkdir(parents=True, exist_ok=True)

    z_grid = np.linspace(ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MAX_UM, 6, dtype=np.float64)
    th_grid = np.linspace(0.0, SECTOR_DEG, 30, endpoint=False, dtype=np.float64)

    matrix: dict[str, dict[str, Any]] = {d: {} for d in ABLATION_DESIGNS}

    for dname in ABLATION_DESIGNS:
        for h in HIERARCHY_NAMES:
            check_walltime(started_mono, args.max_walltime_hours)
            tracks = build_hierarchy_tracks(
                h, vernier=dname in ("Config_B_Manhattan_Vernier", "Config_D_DualStator_PushPull")
            )
            inertia = rotor_inertia_properties(dname, hierarchy=h)

            # Scale per-prism mesh density cleanly so Cantor_N3 (7 tracks) stays well within A100 RAM
            if h == "Cantor_N3":
                mesh_cfg = {"n_r": 2, "n_phi_tooth": 3, "n_phi_bridge": 3, "n_phi_arc_override": 12, "n_z": 2}
            else:
                mesh_cfg = {"n_r": 2, "n_phi_tooth": 4, "n_phi_bridge": 4, "n_phi_arc_override": 12, "n_z": 2}

            model: PreparedEngineBemModel | None = None

            def get_model() -> PreparedEngineBemModel:
                nonlocal model
                if model is None:
                    model = PreparedEngineBemModel(
                        dname,
                        n_xi=20,
                        quad_order=3,
                        hierarchy=h,
                        device=device,
                        lazy_self_cache=True,
                        max_memory_gib=args.max_memory_gib,
                        **mesh_cfg,
                    )
                return model

            # 1. Benchmark Stroke I & III
            bench_chk = chk_dir / f"bench_{dname}_{h}.json"
            bench_rec = None if args.no_cache else load_json_if_exists(bench_chk)
            if bench_rec is None:
                m = get_model()
                pts = [(z_u, th_d) for _, z_u, th_d in BENCHMARK_STATES]
                evals = m.evaluate_states_batch(pts)
                bench_rec = {
                    "n_panels_total": 4 * (m.rotor_ref.count + m.stator_ref.count),
                    "n_dofs_total": 4 * (m.nr_dof + m.ns_dof),
                    "Stroke_I_Repulsive": evals[0],
                    "Stroke_III_Attractive": evals[1],
                }
                atomic_write_json(bench_chk, bench_rec)

            # 2. 2D (z_tip, theta) cycle landscape (6 x 30)
            e_grid = np.zeros((len(z_grid), len(th_grid)), dtype=np.float64)
            fz_grid = np.zeros_like(e_grid)
            tau_grid = np.zeros_like(e_grid)
            for iz, z_val in enumerate(z_grid):
                check_walltime(started_mono, args.max_walltime_hours)
                row_chk = chk_dir / f"land_{dname}_{h}_zrow{iz:02d}.json"
                row_rec = None if args.no_cache else load_json_if_exists(row_chk)
                if row_rec is None:
                    m = get_model()
                    pts_row = [(float(z_val), float(th_d)) for th_d in th_grid]
                    res_row = m.evaluate_states_batch(pts_row)
                    row_rec = {
                        "iz": iz,
                        "z_tip_um": float(z_val),
                        "theta_deg": th_grid.tolist(),
                        "energy_aJ": [float(r["energy_aJ"]) for r in res_row],
                        "f_z_pN": [float(r["f_z_pN"]) for r in res_row],
                        "tau_theta_pN_um": [float(r["tau_theta_pN_um"]) for r in res_row],
                    }
                    atomic_write_json(row_chk, row_rec)
                    print(f"[UF5 LANDSCAPE] {dname} / {h} z-row {iz + 1}/{len(z_grid)} done.", flush=True)
                e_grid[iz, :] = np.asarray(row_rec["energy_aJ"], dtype=np.float64)
                fz_grid[iz, :] = np.asarray(row_rec["f_z_pN"], dtype=np.float64)
                tau_grid[iz, :] = np.asarray(row_rec["tau_theta_pN_um"], dtype=np.float64)

            pot = PeriodicHermitePotential2D(z_grid, th_grid, e_grid, fz_grid, tau_grid)
            cyc_work = _evaluate_cycle_work_on_hermite(pot)
            dyn_gated = simulate_coupled_dynamics(
                dname,
                z_grid,
                th_grid,
                e_grid,
                fz_grid,
                tau_grid,
                mode="pad_release_engine",
                n_steps=7200,
                dt_us=0.025,
                hierarchy=h,
            )

            # 3. Full 4-sector 6-DOF pull-in stiffness across benchmark & peak-pull-in poses
            hess_chk = chk_dir / f"hess6dof_{dname}_{h}.json"
            hess_rec = None if args.no_cache else load_json_if_exists(hess_chk)
            if hess_rec is None:
                check_walltime(started_mono, args.max_walltime_hours)
                # Use matched standard-tier 6-DOF mesh so 4-sector 7-track Cantor_N3 stays fast & memory-safe
                m6 = PreparedEngineBemModel(
                    dname,
                    n_r=1 if h == "Cantor_N3" else 2,
                    n_phi_tooth=3,
                    n_phi_bridge=3,
                    n_phi_arc_override=9,
                    n_z=2,
                    n_xi=16,
                    quad_order=2,
                    hierarchy=h,
                    device=device,
                    lazy_self_cache=True,
                    max_memory_gib=args.max_memory_gib,
                )
                ev6 = Full4Sector6DofBemEvaluator(m6)
                pose_rows = []
                for th_p in HESSIAN_POSE_ANGLES_DEG:
                    z_p, _ = cycle_z_profile_um(th_p)
                    # Use 1.2 nm lateral step so Cantor_N3 (8.5 nm min gap) maintains >= 6 nm clearance
                    pose_rows.append(
                        ev6.evaluate_6dof_hessian(z_p, th_p, step_xy_um=0.0012, step_tilt_rad=0.0015)
                    )
                max_k_lat = max(float(r["k_destab_lat_max_uN_m"]) for r in pose_rows)
                max_k_tilt = max(float(r["k_destab_tilt_max_pN_um_rad"]) for r in pose_rows)
                max_c4_res = max(max(abs(float(r["f_x_pN"])), abs(float(r["f_y_pN"]))) for r in pose_rows)
                hess_rec = {
                    "poses": pose_rows,
                    "max_k_lat_destab_uN_m": max_k_lat,
                    "max_k_tilt_destab_pN_um_rad": max_k_tilt,
                    "max_c4_lateral_force_residual_pN": max_c4_res,
                }
                atomic_write_json(hess_chk, hess_rec)
                print(f"[UF5 6DOF] {dname} / {h}: max K_lat={max_k_lat:.2f} uN/m done.", flush=True)

            t1 = float(bench_rec["Stroke_I_Repulsive"]["tau_theta_pN_um"])
            t3 = float(bench_rec["Stroke_III_Attractive"]["tau_theta_pN_um"])
            mean_tau = 0.5 * (t1 + t3)
            k_lat_mN_m = max(1.0e-3, float(hess_rec["max_k_lat_destab_uN_m"]) * 1.0e-3)
            fom_stability = mean_tau / k_lat_mN_m

            matrix[dname][h] = {
                "design_name": dname,
                "hierarchy": h,
                "n_tracks": len(tracks),
                "total_slot_width_nm": round(sum(t.w_slot for t in tracks) * 1.0e3, 3),
                "total_tooth_width_nm": round(sum(t.w_tooth for t in tracks) * 1.0e3, 3),
                "rotor_mass_pg": round(float(inertia["mass_pg"]), 4),
                "rotor_iz_kg_m2": float(inertia["iz_kg_m2"]),
                "n_panels_total": int(bench_rec["n_panels_total"]),
                "n_dofs_total": int(bench_rec["n_dofs_total"]),
                "benchmark_states": {
                    "Stroke_I_Repulsive": bench_rec["Stroke_I_Repulsive"],
                    "Stroke_III_Attractive": bench_rec["Stroke_III_Attractive"],
                    "mean_dual_stroke_tau_pN_um": mean_tau,
                },
                "cycle_energetics": cyc_work,
                "gated_dynamics": {
                    "net_rotation_deg": float(dyn_gated["net_rotation_deg"]),
                    "peak_omega_krad_s": float(dyn_gated["peak_omega_krad_s"]),
                    "z_stroke_span_nm": float(dyn_gated["z_stroke_span_nm"]),
                },
                "stability_6dof": {
                    "max_k_lat_destab_uN_m": float(hess_rec["max_k_lat_destab_uN_m"]),
                    "max_k_tilt_destab_pN_um_rad": float(hess_rec["max_k_tilt_destab_pN_um_rad"]),
                    "max_c4_lateral_force_residual_pN": float(hess_rec["max_c4_lateral_force_residual_pN"]),
                    "torque_to_pullin_fom_nm_um": float(fom_stability),
                },
            }

    d_mat = matrix["Config_D_DualStator_PushPull"]
    b_mat = matrix["Config_B_Manhattan_Vernier"]
    d_n0_tau = float(d_mat["N0_Macro_Ring"]["benchmark_states"]["mean_dual_stroke_tau_pN_um"])
    d_n2_tau = float(d_mat["Cantor_N2"]["benchmark_states"]["mean_dual_stroke_tau_pN_um"])
    d_uni_tau = float(d_mat["Uniform_3Track"]["benchmark_states"]["mean_dual_stroke_tau_pN_um"])
    d_n3_tau = float(d_mat["Cantor_N3"]["benchmark_states"]["mean_dual_stroke_tau_pN_um"])

    gain_n2_vs_n0 = d_n2_tau / d_n0_tau if abs(d_n0_tau) > 1.0e-9 else 0.0
    gain_n2_vs_uni = d_n2_tau / d_uni_tau if abs(d_uni_tau) > 1.0e-9 else 0.0

    summary = {
        "config_d_n0_mean_tau_pN_um": round(d_n0_tau, 4),
        "config_d_n1_mean_tau_pN_um": round(float(d_mat["Cantor_N1"]["benchmark_states"]["mean_dual_stroke_tau_pN_um"]), 4),
        "config_d_n2_mean_tau_pN_um": round(d_n2_tau, 4),
        "config_d_uni_mean_tau_pN_um": round(d_uni_tau, 4),
        "config_d_n3_mean_tau_pN_um": round(d_n3_tau, 4),
        "config_d_n2_vs_n0_tau_gain": round(gain_n2_vs_n0, 2),
        "config_d_n2_vs_uniform_tau_gain": round(gain_n2_vs_uni, 2),
        "config_b_n2_work_aJ": round(float(b_mat["Cantor_N2"]["cycle_energetics"]["w_power_strokes_aJ"]), 4),
        "config_b_uni_work_aJ": round(float(b_mat["Uniform_3Track"]["cycle_energetics"]["w_power_strokes_aJ"]), 4),
        "config_d_n2_spin_up_deg": round(float(d_mat["Cantor_N2"]["gated_dynamics"]["net_rotation_deg"]), 1),
        "config_d_n3_spin_up_deg": round(float(d_mat["Cantor_N3"]["gated_dynamics"]["net_rotation_deg"]), 1),
        "config_d_n0_spin_up_deg": round(float(d_mat["N0_Macro_Ring"]["gated_dynamics"]["net_rotation_deg"]), 1),
    }

    rep_path = UF_RESULTS_DIR / "uf5_cantor_ablation_report.json"
    report = {
        "suite": "eng_uf5",
        "status": "completed",
        "time_truncated": False,
        "device": device,
        "elapsed_seconds": time.perf_counter() - started_wall,
        "designs": list(ABLATION_DESIGNS),
        "hierarchies": list(HIERARCHY_NAMES),
        "summary": summary,
        "matrix": matrix,
    }
    atomic_write_json(rep_path, report)

    solver_params = {
        "n_xi": 20,
        "quad_order": 3,
        "z_nodes": len(z_grid),
        "theta_nodes": len(th_grid),
        "hierarchies": list(HIERARCHY_NAMES),
    }
    uf5_metrics = UF_RESULTS_DIR / "uf5_provenance_metrics.json"
    uf5_macros = UF_RESULTS_DIR / "uf5_macros_results.tex"
    set_solver_provenance(
        "BEM_UltraFine_3D_CantorHierarchyAblation",
        solver_params,
        dataset_name="fractal_casimir_engine_cycle",
        metrics_path=str(uf5_metrics),
    )
    log_step("uf5_cantor_hierarchy_ablation", summary, metrics_path=str(uf5_metrics))
    log_metric("engine_uf5_cfg_d_n0_tau", summary["config_d_n0_mean_tau_pN_um"], step_id="uf5_cantor_hierarchy_ablation", metrics_path=str(uf5_metrics))
    log_metric("engine_uf5_cfg_d_n2_tau", summary["config_d_n2_mean_tau_pN_um"], step_id="uf5_cantor_hierarchy_ablation", metrics_path=str(uf5_metrics))
    log_metric("engine_uf5_cfg_d_uni_tau", summary["config_d_uni_mean_tau_pN_um"], step_id="uf5_cantor_hierarchy_ablation", metrics_path=str(uf5_metrics))
    log_metric("engine_uf5_cfg_d_n3_tau", summary["config_d_n3_mean_tau_pN_um"], step_id="uf5_cantor_hierarchy_ablation", metrics_path=str(uf5_metrics))
    log_metric("engine_uf5_n2_vs_n0_gain", summary["config_d_n2_vs_n0_tau_gain"], step_id="uf5_cantor_hierarchy_ablation", metrics_path=str(uf5_metrics))
    log_metric("engine_uf5_n2_vs_uni_gain", summary["config_d_n2_vs_uniform_tau_gain"], step_id="uf5_cantor_hierarchy_ablation", metrics_path=str(uf5_metrics))
    log_metric("engine_uf5_cfg_d_n3_spin_deg", summary["config_d_n3_spin_up_deg"], step_id="uf5_cantor_hierarchy_ablation", metrics_path=str(uf5_metrics))
    export_macros(metrics_path=str(uf5_metrics), output_path=str(uf5_macros))

    fig_png = ENGINE_FIGURES_DIR / "fig_uf5_cantor_scaling.png"
    fig_pdf = ENGINE_FIGURES_DIR / "fig_uf5_cantor_scaling.pdf"
    generate_uf5_figure(report, fig_png, fig_pdf, rep_path, solver_params)
    print(f"[UF5 COMPLETE] Saved report -> {rep_path} and figure -> {fig_png}", flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-steps", type=int, default=0, help=">0 runs fast local micro-probe; 0 runs full campaign.")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=UF_RESULTS_DIR / "checkpoints_uf5",
        help="Directory for atomic per-row JSON checkpoints.",
    )
    p.add_argument("--max-walltime-hours", type=float, default=0.0, help="Graceful checkpoint exit threshold.")
    p.add_argument("--max-memory-gib", type=float, default=34.0)
    p.add_argument("--no-cache", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.max_steps > 0:
            return run_micro_probe(args)
        return run_full_campaign(args)
    except TimeoutError as exc:
        print(f"[UF5 WALLTIME] {exc}", file=sys.stderr, flush=True)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
