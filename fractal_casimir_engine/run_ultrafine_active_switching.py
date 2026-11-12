#!/usr/bin/env python3
"""Suite 3 (eng_uf3): Ultra-Fine Physical VO2 & Photo-Doped Silicon Two-State Switching Engine.

Replaces phenomenological exit-seam gating with real Kramers-Kronig dispersive
3D BEM Casimir energy surfaces E_C^(ON)(z, theta) and E_C^(OFF)(z, theta) on the
Ultra-Fine mesh:
  1. Gold rotor + VO2 phase-change stator (Rutile VO2_Metallic <-> Monoclinic VO2_Insulating).
  2. Gold rotor + Optically modulated Silicon stator (Silicon_PhotoDoped <-> Silicon_Intrinsic).

Integrates coupled 2-DOF rigid-body dynamics across discrete ON <-> OFF state transitions,
verifies exact First-Law thermodynamic energy conservation, and quantifies mechanical output
work W_mech, irreversible switching work W_pump_irrev, and electromagnetic transduction
efficiency eta = W_mech / W_pump_irrev.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Mapping
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
    rotor_inertia_properties,
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

SWITCHING_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("Au_VO2_ON", "Gold", "VO2_Metallic"),
    ("Au_VO2_OFF", "Gold", "VO2_Insulating"),
    ("Au_Si_ON", "Gold", "Silicon_PhotoDoped"),
    ("Au_Si_OFF", "Gold", "Silicon_Intrinsic"),
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
        d = json.load(handle)
    return d if isinstance(d, dict) else None


def check_walltime(started_mono: float, max_walltime_hours: float) -> None:
    if max_walltime_hours > 0.0 and (time.monotonic() - started_mono) >= max_walltime_hours * 3600.0:
        raise TimeoutError("Approaching Slurm walltime limit; checkpoint saved cleanly for auto-resubmit.")


def is_in_release_window(theta_deg_unwrapped: float, *, half_width_deg: float = 11.5) -> bool:
    """Identical symmetric two-seam stator-termination window (42.5 deg & 89.0 deg) across all designs."""
    th_mod = float(theta_deg_unwrapped) % SECTOR_DEG
    for seam in (42.5, 89.0):
        delta = ((th_mod - seam + 0.5 * SECTOR_DEG) % SECTOR_DEG) - 0.5 * SECTOR_DEG
        if abs(delta) <= half_width_deg:
            return True
    return False


def simulate_two_state_thermodynamic_engine(
    design_name: str,
    z_grid_um: np.ndarray,
    theta_grid_deg: np.ndarray,
    surf_on: Mapping[str, Any],
    surf_off: Mapping[str, Any],
    *,
    n_steps: int = 9600,
    dt_us: float = 0.025,
) -> dict[str, Any]:
    """Integrate exact two-surface (ON <-> OFF) 2-DOF dynamics with First-Law energy accounting."""
    props = rotor_inertia_properties(design_name)
    mass_kg = props["mass_kg"]
    iz_kg_m2 = props["iz_kg_m2"]

    pot_on = PeriodicHermitePotential2D(
        z_grid_um,
        theta_grid_deg,
        np.asarray(surf_on["energy_grid_aJ"], dtype=np.float64),
        np.asarray(surf_on["fz_grid_pN"], dtype=np.float64),
        np.asarray(surf_on["tau_grid_pN_um"], dtype=np.float64),
    )
    pot_off = PeriodicHermitePotential2D(
        z_grid_um,
        theta_grid_deg,
        np.asarray(surf_off["energy_grid_aJ"], dtype=np.float64),
        np.asarray(surf_off["fz_grid_pN"], dtype=np.float64),
        np.asarray(surf_off["tau_grid_pN_um"], dtype=np.float64),
    )

    z_eq_um = -0.084
    k_flex_N_m = 4.0e-5
    gamma_z = 2.5e-12
    gamma_th = 6.0e-25

    def mech_aux_potential_and_force(z_um: float) -> tuple[float, float]:
        # Elastic spring U_spring in aJ (1 J = 1e18 aJ) + soft clearance stops
        dz_m = (z_um - z_eq_um) * 1.0e-6
        u_spring_aj = 0.5 * k_flex_N_m * (dz_m**2) * 1.0e18
        f_spring_pn = -k_flex_N_m * dz_m * 1.0e12

        u_stop_aj = 0.0
        f_stop_pn = 0.0
        k_stop_pn_per_um = 180.0 / 0.010  # 18,000 pN/um -> U = 0.5 * k_stop * dz_um^2 (since pN*um = aJ)
        if z_um < ENGINE_Z_TIP_MIN_UM:
            pen = ENGINE_Z_TIP_MIN_UM - z_um
            f_stop_pn += k_stop_pn_per_um * pen
            u_stop_aj += 0.5 * k_stop_pn_per_um * (pen**2)
        elif z_um > ENGINE_Z_TIP_MAX_UM:
            pen = z_um - ENGINE_Z_TIP_MAX_UM
            f_stop_pn -= k_stop_pn_per_um * pen
            u_stop_aj += 0.5 * k_stop_pn_per_um * (pen**2)
        return (u_spring_aj + u_stop_aj), (f_spring_pn + f_stop_pn)

    dt_s = dt_us * 1.0e-6
    z_um = -0.097
    vz_m_s = 0.0
    th_rad = math.radians(9.0)
    om_rad_s = 0.0

    is_off = is_in_release_window(math.degrees(th_rad))
    active_pot = pot_off if is_off else pot_on

    def total_hamiltonian_aj(z_u: float, vz: float, th_r: float, om: float, pot: PeriodicHermitePotential2D) -> float:
        ke_aj = (0.5 * mass_kg * vz * vz + 0.5 * iz_kg_m2 * om * om) * 1.0e18
        u_aux_aj, _ = mech_aux_potential_and_force(z_u)
        e_cas_aj, _, _ = pot.eval_e_fz_tau(z_u, math.degrees(th_r) % SECTOR_DEG)
        return ke_aj + u_aux_aj + e_cas_aj

    h_init_aj = total_hamiltonian_aj(z_um, vz_m_s, th_rad, om_rad_s, active_pot)
    sum_delta_e_switch_aj = 0.0
    w_pump_irrev_aj = 0.0
    q_diss_aj = 0.0
    n_switches = 0

    stride = max(1, n_steps // 320)
    history: list[dict[str, float]] = []

    def rhs(st: np.ndarray, pot: PeriodicHermitePotential2D) -> np.ndarray:
        zu, vz, thr, om = float(st[0]), float(st[1]), float(st[2]), float(st[3])
        _, fz_cas, tau_cas = pot.eval_e_fz_tau(zu, math.degrees(thr) % SECTOR_DEG)
        if zu <= ENGINE_Z_TIP_MIN_UM or zu >= ENGINE_Z_TIP_MAX_UM:
            fz_cas = 0.0
        _, f_aux = mech_aux_potential_and_force(zu)
        az = ((fz_cas + f_aux) * 1.0e-12 - gamma_z * vz) / mass_kg
        alpha = (tau_cas * 1.0e-18 - gamma_th * om) / iz_kg_m2
        return np.array([vz * 1.0e6, az, om, alpha], dtype=np.float64)

    state = np.array([z_um, vz_m_s, th_rad, om_rad_s], dtype=np.float64)
    for step in range(n_steps + 1):
        t_us = step * dt_us
        th_deg_now = math.degrees(float(state[2]))
        now_off = is_in_release_window(th_deg_now)
        if now_off != is_off:
            new_pot = pot_off if now_off else pot_on
            e_old, _, _ = active_pot.eval_e_fz_tau(float(state[0]), th_deg_now % SECTOR_DEG)
            e_new, _, _ = new_pot.eval_e_fz_tau(float(state[0]), th_deg_now % SECTOR_DEG)
            d_e = e_new - e_old
            sum_delta_e_switch_aj += d_e
            if d_e > 0.0:
                w_pump_irrev_aj += d_e
            active_pot = new_pot
            is_off = now_off
            n_switches += 1

        if step % stride == 0 or step == n_steps:
            history.append(
                {
                    "t_us": float(t_us),
                    "z_tip_um": float(state[0]),
                    "theta_deg": th_deg_now,
                    "omega_krad_s": float(state[3]) * 1.0e-3,
                    "state_off": 1.0 if is_off else 0.0,
                }
            )
        if step == n_steps:
            break

        # Simpson/midpoint bearing dissipation + RK4 state advance on fixed surface `active_pot`
        k1 = rhs(state, active_pot)
        k2 = rhs(state + 0.5 * dt_s * k1, active_pot)
        k3 = rhs(state + 0.5 * dt_s * k2, active_pot)
        k4 = rhs(state + dt_s * k3, active_pot)
        next_state = state + (dt_s / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        vz_mid = 0.5 * (float(state[1]) + float(next_state[1]))
        om_mid = 0.5 * (float(state[3]) + float(next_state[3]))
        q_diss_aj += (gamma_z * vz_mid * vz_mid + gamma_th * om_mid * om_mid) * dt_s * 1.0e18
        state = next_state

    h_final_aj = total_hamiltonian_aj(
        float(state[0]), float(state[1]), float(state[2]), float(state[3]), active_pot
    )
    # First Law: (H_final - H_init) + Q_diss == sum_switches Delta_E_switch
    first_law_residual_aj = abs((h_final_aj - h_init_aj) + q_diss_aj - sum_delta_e_switch_aj)

    ke_rot_final_aj = 0.5 * iz_kg_m2 * (float(state[3]) ** 2) * 1.0e18
    w_mech_output_aj = max(0.0, (h_final_aj - h_init_aj) + q_diss_aj)
    net_em_work_into_rotor_aj = sum_delta_e_switch_aj
    mech_harvested_aj = max(0.0, ke_rot_final_aj + q_diss_aj)
    eta_irrev = mech_harvested_aj / max(1.0e-12, w_pump_irrev_aj) if w_pump_irrev_aj > 0.0 else 0.0

    th_hist = [row["theta_deg"] for row in history]
    z_hist = [row["z_tip_um"] for row in history]
    return {
        "net_advance_deg": float(th_hist[-1] - th_hist[0]),
        "max_advance_deg": float(max(th_hist) - th_hist[0]),
        "z_stroke_pp_nm": float((max(z_hist) - min(z_hist)) * 1.0e3),
        "n_switches": n_switches,
        "net_em_work_into_rotor_aJ": float(net_em_work_into_rotor_aj),
        "w_pump_irrev_aJ": float(w_pump_irrev_aj),
        "rotational_ke_final_aJ": float(ke_rot_final_aj),
        "bearing_dissipation_aJ": float(q_diss_aj),
        "mech_harvested_aJ": float(mech_harvested_aj),
        "efficiency_irrev": float(eta_irrev),
        "first_law_residual_aJ": float(first_law_residual_aj),
        "w_mech_balance_check_aJ": float(w_mech_output_aj),
        "history": history,
    }


def run_micro_probe(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    device = detect_compute_device(args.device)
    model = PreparedEngineBemModel(
        "Config_D_DualStator_PushPull",
        n_r=1,
        n_phi_tooth=2,
        n_phi_bridge=3,
        n_z=1,
        n_xi=6,
        quad_order=2,
        device=device,
        lazy_self_cache=True,
    )
    batch = model.evaluate_states_batch(
        [(-0.092, 22.0), (-0.084, 64.0)],
        material_pairs=SWITCHING_PAIRS,
        max_steps=args.max_steps,
    )
    out_path = UF_RESULTS_DIR / "probe_uf3_active_switching_report.json"
    payload = {
        "suite": "eng_uf3",
        "status": "micro_probe_completed",
        "time_truncated": True,
        "max_steps": int(args.max_steps),
        "device": device,
        "elapsed_seconds": time.perf_counter() - started,
        "sample_states": batch,
    }
    atomic_write_json(out_path, payload)
    print(f"[UF3 MICRO-PROBE] Completed in {payload['elapsed_seconds']:.2f}s -> {out_path}", flush=True)
    return 0


def run_full_campaign(args: argparse.Namespace) -> int:
    started_mono = time.monotonic()
    started_wall = time.perf_counter()
    device = detect_compute_device(args.device)
    chk_dir = args.checkpoint_dir
    chk_dir.mkdir(parents=True, exist_ok=True)

    z_grid = np.linspace(ENGINE_Z_TIP_MIN_UM, ENGINE_Z_TIP_MAX_UM, 7, dtype=np.float64)
    theta_grid = np.linspace(0.0, SECTOR_DEG, 36, endpoint=False, dtype=np.float64)  # 2.5 deg step

    designs_out: dict[str, Any] = {}
    for dname in ENGINE_DESIGN_NAMES:
        model: PreparedEngineBemModel | None = None
        grids: dict[str, dict[str, np.ndarray]] = {
            label: {
                "energy_grid_aJ": np.zeros((len(z_grid), len(theta_grid)), dtype=np.float64),
                "fz_grid_pN": np.zeros((len(z_grid), len(theta_grid)), dtype=np.float64),
                "tau_grid_pN_um": np.zeros((len(z_grid), len(theta_grid)), dtype=np.float64),
            }
            for label, _, _ in SWITCHING_PAIRS
        }

        for iz, z_val in enumerate(z_grid):
            check_walltime(started_mono, args.max_walltime_hours)
            row_chk = chk_dir / f"uf3_{dname}_zrow{iz:02d}.json"
            cached = load_json_if_exists(row_chk)
            if cached is not None and not args.no_cache:
                for label, _, _ in SWITCHING_PAIRS:
                    grids[label]["energy_grid_aJ"][iz, :] = np.asarray(cached[label]["energy_aJ"], dtype=np.float64)
                    grids[label]["fz_grid_pN"][iz, :] = np.asarray(cached[label]["f_z_pN"], dtype=np.float64)
                    grids[label]["tau_grid_pN_um"][iz, :] = np.asarray(
                        cached[label]["tau_theta_pN_um"], dtype=np.float64
                    )
                continue

            if model is None:
                model = PreparedEngineBemModel(
                    dname,
                    n_r=3,
                    n_phi_tooth=6,
                    n_phi_bridge=6,
                    n_phi_arc_override=18,
                    n_z=3,
                    n_xi=24,
                    quad_order=3,
                    device=device,
                    lazy_self_cache=True,
                    max_memory_gib=args.max_memory_gib,
                )
            pts_row = [(float(z_val), float(th)) for th in theta_grid]
            evals_row = model.evaluate_states_batch(pts_row, material_pairs=SWITCHING_PAIRS)
            row_payload: dict[str, Any] = {"z_tip_um": float(z_val), "iz": iz}
            for label, _, _ in SWITCHING_PAIRS:
                e_list = [float(r["material_pairs"][label]["energy_aJ"]) for r in evals_row]
                fz_list = [float(r["material_pairs"][label]["f_z_pN"]) for r in evals_row]
                tau_list = [float(r["material_pairs"][label]["tau_theta_pN_um"]) for r in evals_row]
                row_payload[label] = {
                    "energy_aJ": e_list,
                    "f_z_pN": fz_list,
                    "tau_theta_pN_um": tau_list,
                }
                grids[label]["energy_grid_aJ"][iz, :] = np.asarray(e_list, dtype=np.float64)
                grids[label]["fz_grid_pN"][iz, :] = np.asarray(fz_list, dtype=np.float64)
                grids[label]["tau_grid_pN_um"][iz, :] = np.asarray(tau_list, dtype=np.float64)
            atomic_write_json(row_chk, row_payload)
            print(f"[UF3 SWITCH-GRID] {dname} z-row {iz + 1}/{len(z_grid)} done.", flush=True)

        surfaces_serializable = {
            label: {
                "energy_grid_aJ": grids[label]["energy_grid_aJ"].tolist(),
                "fz_grid_pN": grids[label]["fz_grid_pN"].tolist(),
                "tau_grid_pN_um": grids[label]["tau_grid_pN_um"].tolist(),
            }
            for label, _, _ in SWITCHING_PAIRS
        }
        vo2_dyn = simulate_two_state_thermodynamic_engine(
            dname, z_grid, theta_grid, surfaces_serializable["Au_VO2_ON"], surfaces_serializable["Au_VO2_OFF"]
        )
        si_dyn = simulate_two_state_thermodynamic_engine(
            dname, z_grid, theta_grid, surfaces_serializable["Au_Si_ON"], surfaces_serializable["Au_Si_OFF"]
        )
        # Contrast ratio at Stroke III attractive exit cliff
        tau_on_peak = float(np.max(np.abs(grids["Au_VO2_ON"]["tau_grid_pN_um"])))
        tau_off_peak = float(np.max(np.abs(grids["Au_VO2_OFF"]["tau_grid_pN_um"])))
        vo2_modulation_depth_pct = 100.0 * (1.0 - tau_off_peak / max(1.0e-12, tau_on_peak))

        designs_out[dname] = {
            "design_name": dname,
            "z_grid_um": [float(x) for x in z_grid],
            "theta_grid_deg": [float(x) for x in theta_grid],
            "vo2_torque_modulation_depth_pct": float(vo2_modulation_depth_pct),
            "vo2_switching_engine": vo2_dyn,
            "silicon_photodoped_engine": si_dyn,
            "surfaces": surfaces_serializable,
        }

    max_first_law_err = max(
        max(
            designs_out[d]["vo2_switching_engine"]["first_law_residual_aJ"],
            designs_out[d]["silicon_photodoped_engine"]["first_law_residual_aJ"],
        )
        for d in ENGINE_DESIGN_NAMES
    )

    report = {
        "suite": "eng_uf3",
        "status": "completed",
        "time_truncated": False,
        "device": device,
        "elapsed_seconds": time.perf_counter() - started_wall,
        "summary": {
            "config_d_vo2_advance_deg": designs_out["Config_D_DualStator_PushPull"]["vo2_switching_engine"][
                "net_advance_deg"
            ],
            "config_d_si_advance_deg": designs_out["Config_D_DualStator_PushPull"]["silicon_photodoped_engine"][
                "net_advance_deg"
            ],
            "sym_vo2_advance_deg": designs_out["Sym_Baseline_CantorN2"]["vo2_switching_engine"]["net_advance_deg"],
            "config_d_vo2_mod_depth_pct": designs_out["Config_D_DualStator_PushPull"][
                "vo2_torque_modulation_depth_pct"
            ],
            "config_d_vo2_efficiency_pct": 100.0
            * designs_out["Config_D_DualStator_PushPull"]["vo2_switching_engine"]["efficiency_irrev"],
            "max_first_law_residual_aJ": float(max_first_law_err),
        },
        "designs": designs_out,
    }
    report_path = UF_RESULTS_DIR / "uf3_active_switching_report.json"
    atomic_write_json(report_path, report)

    metrics_path = UF_RESULTS_DIR / "uf3_provenance_metrics.json"
    macros_path = UF_RESULTS_DIR / "uf3_macros_results.tex"
    solver_params = {"n_r": 3, "n_phi_tooth": 6, "n_phi_arc": 18, "n_z": 3, "n_xi": 24, "quad_order": 3}
    set_solver_provenance(
        "BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si",
        solver_params,
        metrics_path=str(metrics_path),
    )
    log_step("uf3_active_permittivity_switching", report["summary"], metrics_path=str(metrics_path))
    log_metric(
        "engine_uf3_config_d_vo2_adv_deg",
        round(report["summary"]["config_d_vo2_advance_deg"], 1),
        step_id="uf3_active_permittivity_switching",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf3_config_d_si_adv_deg",
        round(report["summary"]["config_d_si_advance_deg"], 1),
        step_id="uf3_active_permittivity_switching",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf3_sym_vo2_adv_deg",
        round(report["summary"]["sym_vo2_advance_deg"], 2),
        step_id="uf3_active_permittivity_switching",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf3_vo2_mod_depth_pct",
        round(report["summary"]["config_d_vo2_mod_depth_pct"], 1),
        step_id="uf3_active_permittivity_switching",
        metrics_path=str(metrics_path),
    )
    log_metric(
        "engine_uf3_first_law_max_res_aj",
        round(report["summary"]["max_first_law_residual_aJ"], 5),
        step_id="uf3_active_permittivity_switching",
        metrics_path=str(metrics_path),
    )
    export_macros(metrics_path=str(metrics_path), output_path=str(macros_path))

    # Plot Suite 3 figure
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=300)
    palette = {
        "Sym_Baseline_CantorN2": "#5f6368",
        "Config_B_Manhattan_Vernier": "#1a73e8",
        "Config_C_Helical_Turbine": "#0d9488",
        "Config_D_DualStator_PushPull": "#d93025",
    }
    for dname in ENGINE_DESIGN_NAMES:
        h_vo2 = designs_out[dname]["vo2_switching_engine"]["history"]
        h_si = designs_out[dname]["silicon_photodoped_engine"]["history"]
        short = dname.split("_")[1]
        axes[0].plot(
            [r["t_us"] for r in h_vo2],
            [r["theta_deg"] - 9.0 for r in h_vo2],
            lw=2.0,
            color=palette[dname],
            label=f"{short} (VO$_2$: +{designs_out[dname]['vo2_switching_engine']['net_advance_deg']:.1f}$^\\circ$)",
        )
        axes[1].plot(
            [r["t_us"] for r in h_si],
            [r["theta_deg"] - 9.0 for r in h_si],
            lw=2.0,
            color=palette[dname],
            label=f"{short} (Photo-Si: +{designs_out[dname]['silicon_photodoped_engine']['net_advance_deg']:.1f}$^\\circ$)",
        )
    for ax, title in (
        (axes[0], "A. Physical Au–VO$_2$ (Metal $\\leftrightarrow$ Insulator) Spin-Up"),
        (axes[1], "B. Physical Au–Si (Photo-Doped $\\leftrightarrow$ Intrinsic) Spin-Up"),
    ):
        ax.set_xlabel("Time $t$ ($\\mu$s)")
        ax.set_ylabel("Cumulative Rotation $\\Delta\\theta(t)$ (deg)")
        ax.set_title(title)
        ax.legend(fontsize=8.0, loc="upper left")
        ax.grid(True, alpha=0.25)

    fig.tight_layout()
    out_png = ENGINE_FIGURES_DIR / "fig_uf3_active_switching.png"
    out_pdf = ENGINE_FIGURES_DIR / "fig_uf3_active_switching.pdf"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)

    for fp in (out_png, out_pdf):
        save_plot_provenance(
            str(fp),
            str(report_path),
            columns_used=["designs", "summary"],
            solver_name="BEM_UltraFine_3D_KramersKronig_TwoState_VO2_Si",
            solver_parameters=solver_params,
        )
    print(f"[UF3 COMPLETE] Saved {report_path} and figures.", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-steps", type=int, default=0)
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--max-walltime-hours", type=float, default=5.5)
    p.add_argument("--max-memory-gib", type=float, default=36.0)
    p.add_argument("--checkpoint-dir", type=Path, default=UF_RESULTS_DIR / "checkpoints_uf3")
    p.add_argument("--no-cache", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.max_steps > 0:
            return run_micro_probe(args)
        return run_full_campaign(args)
    except TimeoutError as exc:
        print(f"[UF3 WALLTIME] {exc}", file=sys.stderr, flush=True)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
