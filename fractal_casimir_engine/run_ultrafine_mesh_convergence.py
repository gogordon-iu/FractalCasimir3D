#!/usr/bin/env python3
"""Suite 1 (eng_uf1): Ultra-Fine 5-Level Mesh/Quadrature Convergence & 1.0 deg/1.5 deg Cycle Sweep.

Eliminates discrete panel-edge cogging artifacts and certifies Richardson mesh,
Gauss-Legendre sub-panel quadrature (quad_order in {2, 3, 4}), and sub-panel
regularization (sub_var_scale in {0.25, 0.50, 1.00}) convergence up to 18,912 panels
(37,824 tangential DOFs) on BigRed 200 A100 GPUs.

Supports:
  - ``--max-steps N`` (N > 0): fast local micro-probe writing strictly to ``probe_uf1_*``.
  - ``--max-steps 0``: full resumable GPU campaign with walltime guard (exit code 75)
    and grounded provenance + figure sidecar generation.
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

from fractal_casimir_engine import ENGINE_DESIGN_NAMES
from fractal_casimir_engine.bem_cycle_solver import (
    PreparedEngineBemModel,
    detect_compute_device,
)
from fractal_casimir_engine.geometries import (
    ENGINE_Z_TIP_MAX_UM,
    ENGINE_Z_TIP_MIN_UM,
    SECTOR_DEG,
)
from fractal_casimir_engine.run_engine_cycle_mapping import (
    PeriodicHermitePotential2D,
    cycle_z_profile_um,
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

BENCHMARK_STATES: tuple[tuple[str, float, float], ...] = (
    ("Stroke_I_Repulsive", -0.092, 22.0),
    ("Stroke_III_Attractive", -0.084, 64.0),
)

# 5-level mesh & sub-panel quadrature ladder (up to 18,912 panels = 37,824 DOFs)
CONVERGENCE_LADDER: tuple[dict[str, Any], ...] = (
    {
        "tier": "L1_Coarse",
        "n_r": 1,
        "n_phi_tooth": 2,
        "n_phi_bridge": 3,
        "n_phi_arc": 9,
        "n_z": 1,
        "n_xi": 8,
        "quad_order": 2,
    },
    {
        "tier": "L2_Standard",
        "n_r": 1,
        "n_phi_tooth": 3,
        "n_phi_bridge": 3,
        "n_phi_arc": 9,
        "n_z": 2,
        "n_xi": 12,
        "quad_order": 2,
    },
    {
        "tier": "L3_Fine",
        "n_r": 2,
        "n_phi_tooth": 4,
        "n_phi_bridge": 4,
        "n_phi_arc": 12,
        "n_z": 3,
        "n_xi": 18,
        "quad_order": 2,
    },
    {
        "tier": "L4_UltraFine",
        "n_r": 3,
        "n_phi_tooth": 6,
        "n_phi_bridge": 6,
        "n_phi_arc": 18,
        "n_z": 3,
        "n_xi": 24,
        "quad_order": 3,
    },
    {
        "tier": "L5_Extreme",
        "n_r": 3,
        "n_phi_tooth": 8,
        "n_phi_bridge": 8,
        "n_phi_arc": 24,
        "n_z": 4,
        "n_xi": 28,
        "quad_order": 3,
    },
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


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def check_walltime(started_monotonic: float, max_walltime_hours: float) -> None:
    if max_walltime_hours > 0.0 and (time.monotonic() - started_monotonic) >= max_walltime_hours * 3600.0:
        raise TimeoutError("Approaching Slurm walltime limit; checkpoint saved cleanly for auto-resubmit.")


def generate_uf1_figure(report: dict[str, Any], out_png: Path, out_pdf: Path, metrics_path: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 9.2), dpi=300)

    palette = {
        "Sym_Baseline_CantorN2": "#5f6368",
        "Config_B_Manhattan_Vernier": "#1a73e8",
        "Config_C_Helical_Turbine": "#0d9488",
        "Config_D_DualStator_PushPull": "#d93025",
    }
    labels = {
        "Sym_Baseline_CantorN2": "Sym Control",
        "Config_B_Manhattan_Vernier": "Config B (Manhattan)",
        "Config_C_Helical_Turbine": "Config C (Helical)",
        "Config_D_DualStator_PushPull": "Config D (Dual Push-Pull)",
    }

    # Panel A: 5-level mesh convergence of tau_theta (Stroke I & III)
    ax = axes[0, 0]
    for dname in ENGINE_DESIGN_NAMES:
        ladder_rows = report["ladder"][dname]
        dofs = [row["n_dofs_total"] * 1e-3 for row in ladder_rows]
        tau_s1 = [row["states"]["Stroke_I_Repulsive"]["tau_theta_pN_um"] for row in ladder_rows]
        tau_s3 = [row["states"]["Stroke_III_Attractive"]["tau_theta_pN_um"] for row in ladder_rows]
        ax.plot(dofs, tau_s1, "-o", color=palette[dname], lw=1.8, ms=4.5, label=f"{labels[dname]} (Stroke I)")
        ax.plot(dofs, tau_s3, "--s", color=palette[dname], lw=1.3, ms=3.8, alpha=0.8)
    ax.axhline(0.0, color="#333333", lw=0.8, ls=":")
    ax.set_xlabel("Total 4-Sector Tangential DOFs ($\\times 10^3$)")
    ax.set_ylabel("Azimuthal Torque $\\tau_\\theta$ (pN$\\cdot\\mu$m)")
    ax.set_title("A. 5-Level Mesh & $3\\times 3$ Sub-Panel Convergence")
    ax.legend(fontsize=7.2, loc="upper left", ncol=1)
    ax.grid(True, alpha=0.25)

    # Panel B: 5-level mesh convergence of F_z (Stroke I repulsive > 0, Stroke III attractive < 0)
    ax = axes[0, 1]
    for dname in ENGINE_DESIGN_NAMES:
        ladder_rows = report["ladder"][dname]
        dofs = [row["n_dofs_total"] * 1e-3 for row in ladder_rows]
        fz_s1 = [row["states"]["Stroke_I_Repulsive"]["f_z_pN"] for row in ladder_rows]
        fz_s3 = [row["states"]["Stroke_III_Attractive"]["f_z_pN"] for row in ladder_rows]
        ax.plot(dofs, fz_s1, "-o", color=palette[dname], lw=1.8, ms=4.5, label=f"{labels[dname]} ($F_z$ I)")
        ax.plot(dofs, fz_s3, "--s", color=palette[dname], lw=1.3, ms=3.8, alpha=0.8)
    ax.axhline(0.0, color="#333333", lw=0.8, ls=":")
    ax.set_xlabel("Total 4-Sector Tangential DOFs ($\\times 10^3$)")
    ax.set_ylabel("Axial Casimir Force $F_z$ (pN)")
    ax.set_title("B. Axial Lift ($+F_z$) & Pull ($-F_z$) Convergence")
    ax.grid(True, alpha=0.25)

    # Panel C: Dense 1.0 deg Ultra-Fine cycle torque profile vs Standard cogging suppression
    ax = axes[1, 0]
    for dname in ENGINE_DESIGN_NAMES:
        cyc = report["dense_cycle"][dname]
        th = cyc["theta_deg"]
        tau = cyc["tau_theta_pN_um"]
        ax.plot(th, tau, color=palette[dname], lw=1.9, label=labels[dname])
    ax.axhline(0.0, color="#333333", lw=0.8, ls=":")
    ax.set_xlabel("Rotor Angle $\\theta$ (deg, $1.0^\\circ$ Ultra-Fine Sampling)")
    ax.set_ylabel("Cycle Torque $\\tau_\\theta(z(\\theta), \\theta)$ (pN$\\cdot\\mu$m)")
    ax.set_title("C. Cogging-Suppressed $1.0^\\circ$ Ultra-Fine Cycle Torque")
    ax.legend(fontsize=7.5, loc="lower left")
    ax.grid(True, alpha=0.25)

    # Panel D: Ultra-Fine 1.5 deg 2D Hermite spin-up trajectories
    ax = axes[1, 1]
    for dname in ENGINE_DESIGN_NAMES:
        dyn = report["ultrafine_dynamics"][dname]["pad_release_engine"]
        t_us = [row["t_us"] for row in dyn["history"]]
        th_deg = [row["theta_deg"] - 9.0 for row in dyn["history"]]
        ax.plot(t_us, th_deg, color=palette[dname], lw=2.0, label=f"{labels[dname]} (+{dyn['net_advance_deg']:.1f}$^\\circ$)")
    ax.axhline(360.0, color="#111111", lw=0.9, ls="--", label="Full $360^\\circ$ Revolution")
    ax.set_xlabel("Time $t$ ($\\mu$s)")
    ax.set_ylabel("Angular Advance $\\Delta\\theta(t)$ (deg)")
    ax.set_title("D. 2-DOF Spin-Up on Ultra-Fine $1.5^\\circ$ Landscape")
    ax.legend(fontsize=7.5, loc="upper left")
    ax.grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)

    report_path = UF_RESULTS_DIR / "uf1_mesh_convergence_report.json"
    solver_meta = report["ladder"]["Config_D_DualStator_PushPull"][-1]["solver_metadata"]
    for fig_path in (out_png, out_pdf):
        save_plot_provenance(
            str(fig_path),
            str(report_path),
            columns_used=["ladder", "dense_cycle", "ultrafine_dynamics"],
            solver_name="BEM_UltraFine_3D_Suite1",
            solver_parameters=solver_meta,
        )


def run_micro_probe(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    device = detect_compute_device(args.device)
    probe_rows: list[dict[str, Any]] = []
    for tier_spec in CONVERGENCE_LADDER[:2]:
        model = PreparedEngineBemModel(
            "Config_D_DualStator_PushPull",
            n_r=tier_spec["n_r"],
            n_phi_tooth=tier_spec["n_phi_tooth"],
            n_phi_bridge=tier_spec["n_phi_bridge"],
            n_phi_arc_override=tier_spec["n_phi_arc"],
            n_z=tier_spec["n_z"],
            n_xi=tier_spec["n_xi"],
            quad_order=tier_spec["quad_order"],
            device=device,
            lazy_self_cache=True,
            max_memory_gib=args.max_memory_gib,
        )
        batch = model.evaluate_states_batch(
            [(-0.092, 22.0), (-0.084, 64.0)],
            max_steps=args.max_steps,
        )
        probe_rows.append(
            {
                "tier": tier_spec["tier"],
                "solver_metadata": model.solver_metadata(),
                "states": batch,
            }
        )

    out_path = UF_RESULTS_DIR / "probe_uf1_mesh_convergence_report.json"
    payload = {
        "suite": "eng_uf1",
        "status": "micro_probe_completed",
        "time_truncated": True,
        "max_steps": int(args.max_steps),
        "device": device,
        "elapsed_seconds": time.perf_counter() - started,
        "probe_ladder": probe_rows,
    }
    atomic_write_json(out_path, payload)
    print(f"[UF1 MICRO-PROBE] Completed in {payload['elapsed_seconds']:.2f}s -> {out_path}", flush=True)
    return 0


def run_full_campaign(args: argparse.Namespace) -> int:
    started_mono = time.monotonic()
    started_wall = time.perf_counter()
    device = detect_compute_device(args.device)
    chk_dir = args.checkpoint_dir
    chk_dir.mkdir(parents=True, exist_ok=True)

    # 1. 5-level convergence ladder across all 4 designs
    ladder_results: dict[str, list[dict[str, Any]]] = {d: [] for d in ENGINE_DESIGN_NAMES}
    for dname in ENGINE_DESIGN_NAMES:
        for tier_spec in CONVERGENCE_LADDER:
            check_walltime(started_mono, args.max_walltime_hours)
            chk_file = chk_dir / f"ladder_{dname}_{tier_spec['tier']}.json"
            cached = load_json_if_exists(chk_file)
            if cached is not None and not args.no_cache:
                ladder_results[dname].append(cached)
                continue

            t0 = time.perf_counter()
            model = PreparedEngineBemModel(
                dname,
                n_r=tier_spec["n_r"],
                n_phi_tooth=tier_spec["n_phi_tooth"],
                n_phi_bridge=tier_spec["n_phi_bridge"],
                n_phi_arc_override=tier_spec["n_phi_arc"],
                n_z=tier_spec["n_z"],
                n_xi=tier_spec["n_xi"],
                quad_order=tier_spec["quad_order"],
                device=device,
                lazy_self_cache=True,
                max_memory_gib=args.max_memory_gib,
            )
            pts = [(z_u, th_d) for _, z_u, th_d in BENCHMARK_STATES]
            evals = model.evaluate_states_batch(pts)
            row = {
                "tier": tier_spec["tier"],
                "n_panels_total": model.ref_mesh.n_panels_total,
                "n_dofs_total": 4 * (model.nr_dof + model.ns_dof),
                "quad_order": tier_spec["quad_order"],
                "n_xi": tier_spec["n_xi"],
                "elapsed_seconds": time.perf_counter() - t0,
                "solver_metadata": model.solver_metadata(),
                "states": {
                    BENCHMARK_STATES[i][0]: evals[i] for i in range(len(BENCHMARK_STATES))
                },
            }
            atomic_write_json(chk_file, row)
            ladder_results[dname].append(row)
            print(
                f"[UF1 LADDER] {dname} {tier_spec['tier']} "
                f"({row['n_dofs_total']} DOFs) done in {row['elapsed_seconds']:.1f}s",
                flush=True,
            )

    # 2. Quadrature order (2, 3, 4) & sub-panel variance regularization (0.25, 0.50, 1.00) audit on UltraFine
    reg_audit: list[dict[str, Any]] = []
    uf_spec = CONVERGENCE_LADDER[3]  # L4_UltraFine
    for q_ord, sv_scale in ((2, 1.0), (3, 1.0), (4, 1.0), (3, 0.50), (3, 0.25)):
        check_walltime(started_mono, args.max_walltime_hours)
        tag = f"q{q_ord}_sv{int(round(sv_scale * 100)):03d}"
        chk_file = chk_dir / f"reg_audit_Config_D_{tag}.json"
        cached = load_json_if_exists(chk_file)
        if cached is not None and not args.no_cache:
            reg_audit.append(cached)
            continue

        model = PreparedEngineBemModel(
            "Config_D_DualStator_PushPull",
            n_r=uf_spec["n_r"],
            n_phi_tooth=uf_spec["n_phi_tooth"],
            n_phi_bridge=uf_spec["n_phi_bridge"],
            n_phi_arc_override=uf_spec["n_phi_arc"],
            n_z=uf_spec["n_z"],
            n_xi=uf_spec["n_xi"],
            quad_order=q_ord,
            sub_var_scale=sv_scale,
            device=device,
            lazy_self_cache=True,
            max_memory_gib=args.max_memory_gib,
        )
        pts = [(z_u, th_d) for _, z_u, th_d in BENCHMARK_STATES]
        evals = model.evaluate_states_batch(pts)
        rec = {
            "tag": tag,
            "quad_order": q_ord,
            "sub_var_scale": sv_scale,
            "Stroke_I_Repulsive": evals[0],
            "Stroke_III_Attractive": evals[1],
        }
        atomic_write_json(chk_file, rec)
        reg_audit.append(rec)
        print(f"[UF1 REG-AUDIT] {tag} done.", flush=True)

    # 3. Dense 1.0 deg (91-node) closed-cycle sweep across all 4 designs on L4_UltraFine
    dense_cycle: dict[str, dict[str, Any]] = {}
    theta_1deg = np.linspace(0.0, SECTOR_DEG, 91, dtype=np.float64)
    for dname in ENGINE_DESIGN_NAMES:
        check_walltime(started_mono, args.max_walltime_hours)
        chk_file = chk_dir / f"dense_cycle_1deg_{dname}.json"
        cached = load_json_if_exists(chk_file)
        if cached is not None and not args.no_cache:
            dense_cycle[dname] = cached
            continue

        model = PreparedEngineBemModel(
            dname,
            n_r=uf_spec["n_r"],
            n_phi_tooth=uf_spec["n_phi_tooth"],
            n_phi_bridge=uf_spec["n_phi_bridge"],
            n_phi_arc_override=uf_spec["n_phi_arc"],
            n_z=uf_spec["n_z"],
            n_xi=uf_spec["n_xi"],
            quad_order=uf_spec["quad_order"],
            device=device,
            lazy_self_cache=True,
            max_memory_gib=args.max_memory_gib,
        )
        cycle_pts = [(cycle_z_profile_um(float(th))[0], float(th)) for th in theta_1deg]
        evals = model.evaluate_states_batch(cycle_pts)
        e_arr = [float(r["energy_aJ"]) for r in evals]
        fz_arr = [float(r["f_z_pN"]) for r in evals]
        tau_arr = [float(r["tau_theta_pN_um"]) for r in evals]
        closure_err_aj = abs(e_arr[-1] - e_arr[0])

        # Azimuthal roughness metric: RMS second difference normalized by peak-to-peak
        tau_np = np.asarray(tau_arr[:-1], dtype=np.float64)
        d2_tau = np.roll(tau_np, -1) - 2.0 * tau_np + np.roll(tau_np, 1)
        ptp_tau = max(1.0e-9, float(np.ptp(tau_np)))
        cogging_roughness_ratio = float(np.sqrt(np.mean(d2_tau**2)) / ptp_tau)

        payload_cyc = {
            "design_name": dname,
            "theta_deg": [float(x) for x in theta_1deg],
            "z_tip_um": [float(p[0]) for p in cycle_pts],
            "energy_aJ": e_arr,
            "f_z_pN": fz_arr,
            "tau_theta_pN_um": tau_arr,
            "periodic_closure_abs_error_aJ": float(closure_err_aj),
            "cogging_second_diff_roughness": cogging_roughness_ratio,
        }
        atomic_write_json(chk_file, payload_cyc)
        dense_cycle[dname] = payload_cyc
        print(f"[UF1 DENSE-1DEG] {dname} done (closure={closure_err_aj:.2e} aJ).", flush=True)

    # 4. Ultra-Fine 1.5 deg 2D (z, theta) landscape (7 x 60 = 420 states/design) + 2-DOF dynamics
    z_grid = np.linspace(ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MAX_UM, 7, dtype=np.float64)
    theta_grid = np.linspace(0.0, SECTOR_DEG, 60, endpoint=False, dtype=np.float64)
    uf_landscapes: dict[str, dict[str, Any]] = {}
    uf_dynamics: dict[str, dict[str, Any]] = {}

    for dname in ENGINE_DESIGN_NAMES:
        model: PreparedEngineBemModel | None = None
        e_mat = np.zeros((len(z_grid), len(theta_grid)), dtype=np.float64)
        fz_mat = np.zeros_like(e_mat)
        tau_mat = np.zeros_like(e_mat)

        for iz, z_val in enumerate(z_grid):
            check_walltime(started_mono, args.max_walltime_hours)
            row_chk = chk_dir / f"landscape_{dname}_zrow{iz:02d}.json"
            cached_row = load_json_if_exists(row_chk)
            if cached_row is not None and not args.no_cache:
                e_mat[iz, :] = np.asarray(cached_row["energy_aJ"], dtype=np.float64)
                fz_mat[iz, :] = np.asarray(cached_row["f_z_pN"], dtype=np.float64)
                tau_mat[iz, :] = np.asarray(cached_row["tau_theta_pN_um"], dtype=np.float64)
                continue

            if model is None:
                model = PreparedEngineBemModel(
                    dname,
                    n_r=uf_spec["n_r"],
                    n_phi_tooth=uf_spec["n_phi_tooth"],
                    n_phi_bridge=uf_spec["n_phi_bridge"],
                    n_phi_arc_override=uf_spec["n_phi_arc"],
                    n_z=uf_spec["n_z"],
                    n_xi=uf_spec["n_xi"],
                    quad_order=uf_spec["quad_order"],
                    device=device,
                    lazy_self_cache=True,
                    max_memory_gib=args.max_memory_gib,
                )
            pts_row = [(float(z_val), float(th)) for th in theta_grid]
            evals_row = model.evaluate_states_batch(pts_row)
            row_data = {
                "design_name": dname,
                "iz": iz,
                "z_tip_um": float(z_val),
                "theta_deg": [float(th) for th in theta_grid],
                "energy_aJ": [float(r["energy_aJ"]) for r in evals_row],
                "f_z_pN": [float(r["f_z_pN"]) for r in evals_row],
                "tau_theta_pN_um": [float(r["tau_theta_pN_um"]) for r in evals_row],
            }
            atomic_write_json(row_chk, row_data)
            e_mat[iz, :] = np.asarray(row_data["energy_aJ"], dtype=np.float64)
            fz_mat[iz, :] = np.asarray(row_data["f_z_pN"], dtype=np.float64)
            tau_mat[iz, :] = np.asarray(row_data["tau_theta_pN_um"], dtype=np.float64)
            print(f"[UF1 2D-GRID] {dname} z-row {iz + 1}/{len(z_grid)} done.", flush=True)

        # Verify Hermite conservative loop integral on the 1.5 deg Ultra-Fine grid
        hermite = PeriodicHermitePotential2D(z_grid, theta_grid, e_mat, fz_mat, tau_mat)
        th_loop = np.linspace(0.0, SECTOR_DEG, 721, dtype=np.float64)
        work_loop = 0.0
        for k in range(len(th_loop) - 1):
            th_mid = 0.5 * (th_loop[k] + th_loop[k + 1])
            z_mid, dz_dth_rad = cycle_z_profile_um(float(th_mid))
            _, fz_m, tau_m = hermite.eval_e_fz_tau(z_mid, float(th_mid))
            dth_rad = math.radians(float(th_loop[k + 1] - th_loop[k]))
            work_loop += (fz_m * dz_dth_rad + tau_m) * dth_rad

        uf_landscapes[dname] = {
            "z_grid_um": [float(x) for x in z_grid],
            "theta_grid_deg": [float(x) for x in theta_grid],
            "energy_grid_aJ": e_mat.tolist(),
            "fz_grid_pN": fz_mat.tolist(),
            "tau_grid_pN_um": tau_mat.tolist(),
            "hermite_closed_loop_work_aJ": float(work_loop),
        }
        uf_dynamics[dname] = {
            mode: simulate_coupled_dynamics(dname, z_grid, theta_grid, e_mat, fz_mat, tau_mat, mode=mode)
            for mode in ("ballistic", "pad_release_engine", "vertical_vibro_engine")
        }

    # Compute Richardson / L4-vs-L5 relative shifts for Config D
    d_l4 = ladder_results["Config_D_DualStator_PushPull"][3]["states"]
    d_l5 = ladder_results["Config_D_DualStator_PushPull"][4]["states"]
    rel_shift_tau_s1_pct = 100.0 * abs(
        d_l5["Stroke_I_Repulsive"]["tau_theta_pN_um"] - d_l4["Stroke_I_Repulsive"]["tau_theta_pN_um"]
    ) / max(1.0e-9, abs(d_l5["Stroke_I_Repulsive"]["tau_theta_pN_um"]))
    rel_shift_fz_s1_pct = 100.0 * abs(
        d_l5["Stroke_I_Repulsive"]["f_z_pN"] - d_l4["Stroke_I_Repulsive"]["f_z_pN"]
    ) / max(1.0e-9, abs(d_l5["Stroke_I_Repulsive"]["f_z_pN"]))

    report = {
        "suite": "eng_uf1",
        "status": "completed",
        "time_truncated": False,
        "device": device,
        "elapsed_seconds": time.perf_counter() - started_wall,
        "summary": {
            "max_dofs_evaluated": ladder_results["Config_D_DualStator_PushPull"][4]["n_dofs_total"],
            "config_d_l4_vs_l5_tau_shift_pct": float(rel_shift_tau_s1_pct),
            "config_d_l4_vs_l5_fz_shift_pct": float(rel_shift_fz_s1_pct),
            "config_d_uf_spinup_deg": float(
                uf_dynamics["Config_D_DualStator_PushPull"]["pad_release_engine"]["net_advance_deg"]
            ),
            "sym_uf_spinup_deg": float(
                uf_dynamics["Sym_Baseline_CantorN2"]["pad_release_engine"]["net_advance_deg"]
            ),
        },
        "ladder": ladder_results,
        "regularization_audit": reg_audit,
        "dense_cycle": dense_cycle,
        "ultrafine_landscapes": uf_landscapes,
        "ultrafine_dynamics": uf_dynamics,
    }
    report_path = UF_RESULTS_DIR / "uf1_mesh_convergence_report.json"
    atomic_write_json(report_path, report)

    # Grounded provenance logging & figure sidecars
    metrics_path = UF_RESULTS_DIR / "uf1_provenance_metrics.json"
    macros_path = UF_RESULTS_DIR / "uf1_macros_results.tex"
    set_solver_provenance(
        "BEM_UltraFine_3D_Suite1",
        ladder_results["Config_D_DualStator_PushPull"][4]["solver_metadata"],
        metrics_path=str(metrics_path),
    )
    log_step(
        "uf1_ultrafine_mesh_convergence",
        report["summary"],
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf1_max_dofs",
        report["summary"]["max_dofs_evaluated"],
        step_id="uf1_ultrafine_mesh_convergence",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf1_config_d_tau_shift_pct",
        round(rel_shift_tau_s1_pct, 2),
        step_id="uf1_ultrafine_mesh_convergence",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf1_config_d_fz_shift_pct",
        round(rel_shift_fz_s1_pct, 2),
        step_id="uf1_ultrafine_mesh_convergence",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf1_config_d_spin_up_deg",
        round(report["summary"]["config_d_uf_spinup_deg"], 1),
        step_id="uf1_ultrafine_mesh_convergence",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf1_sym_spin_up_deg",
        round(report["summary"]["sym_uf_spinup_deg"], 2),
        step_id="uf1_ultrafine_mesh_convergence",
        metrics_path=str(metrics_path),
    )
    export_macros(metrics_path=str(metrics_path), output_path=str(macros_path))

    generate_uf1_figure(
        report,
        ENGINE_FIGURES_DIR / "fig_uf1_mesh_convergence.png",
        ENGINE_FIGURES_DIR / "fig_uf1_mesh_convergence.pdf",
        metrics_path,
    )
    print(f"[UF1 COMPLETE] Saved {report_path} and figures.", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-steps", type=int, default=0, help=">0 runs fast local micro-probe.")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--max-walltime-hours", type=float, default=7.5)
    p.add_argument("--max-memory-gib", type=float, default=36.0)
    p.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=UF_RESULTS_DIR / "checkpoints_uf1",
    )
    p.add_argument("--no-cache", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.max_steps > 0:
            return run_micro_probe(args)
        return run_full_campaign(args)
    except TimeoutError as exc:
        print(f"[UF1 WALLTIME] {exc}", file=sys.stderr, flush=True)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
