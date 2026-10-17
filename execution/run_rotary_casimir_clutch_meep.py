#!/usr/bin/env python3
"""
Rotary Vacuum Casimir Clutch Simulation Engine.

Evaluates the normal Casimir force between a two-needle rotor and a thin
conducting stator membrane with dual circular apertures.

References:
1. Levin et al., Phys. Rev. Lett. 105, 090403 (2010).
2. Kenneth & Klich, Phys. Rev. Lett. 97, 160401 (2006).

--max-steps runs a deterministic numerical micro-probe, not a physical Meep
simulation. Probe results are explicitly identified in the output.
"""

import os
import sys
import json
import time
import ctypes
import argparse
import logging
from datetime import datetime, timezone

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import meep as mp
    from execution.run_meep_simulation import get_casimir_material
except ImportError:
    mp = None
    get_casimir_material = None

try:
    from utils import metrics_logger
except ImportError:
    metrics_logger = None


class WalltimeContinuationRequired(RuntimeError):
    """The incremental checkpoints are saved, but the task is incomplete."""


def get_src_index(n):
    r = int((np.sqrt(8 * n + 1) - 1) / 2)
    c = n - r * (r + 1) // 2
    return r - c, c


# Meep units: hbar = c = 1, length unit = 1 um.
MEEP_TO_PA = 0.031615
MEEP_FORCE_TO_SI = 3.1615e-14


def log_result_metrics(result_data):
    """Use the repository metrics logger when available."""
    log_metrics = getattr(metrics_logger, "log_metrics", None)
    if callable(log_metrics):
        try:
            log_metrics(result_data)
            return
        except Exception as err:
            logging.warning("Failed to log result via utils.metrics_logger: %s", err)
    logging.getLogger("utils.metrics_logger").info(
        "%s", json.dumps(result_data, allow_nan=False)
    )


def run_rotary_casimir_clutch_simulation(
    theta_deg=0.0,
    r_rotor=0.35,
    W_aperture=0.35,
    t_plate=0.025,
    H_needle=0.25,
    w_needle=0.04,
    z_tip=0.015,
    material="Gold",
    resolution=80,
    n_max=1,
    config="all",
    T_run=12.0,
    dpml=0.20,
    buffer=0.15,
    L_plate=1.8,
    chk_tag="rotary_clutch",
    max_walltime_hours=7.5,
    no_cache=False,
    max_steps=None,
):
    """
    Return (single_needle_both, single_needle_self, single_needle_net).

    Incomplete physical runs raise WalltimeContinuationRequired rather than
    returning partial forces as final results.
    """
    positive_parameters = {
        "W_aperture": W_aperture,
        "t_plate": t_plate,
        "H_needle": H_needle,
        "w_needle": w_needle,
        "z_tip": z_tip,
        "resolution": resolution,
        "T_run": T_run,
        "dpml": dpml,
        "L_plate": L_plate,
    }
    for name, value in positive_parameters.items():
        if (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not np.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a finite positive number")

    for name, value in {"r_rotor": r_rotor, "buffer": buffer}.items():
        if (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not np.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{name} must be a finite nonnegative number")

    if (
        isinstance(theta_deg, (bool, np.bool_))
        or not isinstance(theta_deg, (int, float, np.integer, np.floating))
        or not np.isfinite(theta_deg)
    ):
        raise ValueError("theta_deg must be finite")
    if (
        isinstance(n_max, (bool, np.bool_))
        or not isinstance(n_max, (int, np.integer))
        or n_max <= 0
    ):
        raise ValueError("n_max must be a positive integer")
    if config not in ("both", "self", "all"):
        raise ValueError("config must be 'both', 'self', or 'all'")
    if max_walltime_hours is not None:
        if (
            isinstance(max_walltime_hours, (bool, np.bool_))
            or not isinstance(
                max_walltime_hours, (int, float, np.integer, np.floating)
            )
            or not np.isfinite(max_walltime_hours)
        ):
            raise ValueError("max_walltime_hours must be finite or None")
    if max_steps is not None:
        if (
            isinstance(max_steps, (bool, np.bool_))
            or not isinstance(max_steps, (int, np.integer))
            or max_steps < 0
        ):
            raise ValueError("max_steps must be a nonnegative integer")

        # Deterministic, bounded-memory numerical smoke test. These values are
        # diagnostic only and must not be interpreted as physical forces.
        theta_rad = np.radians(theta_deg)
        samples = np.linspace(0.0, np.pi, 32, endpoint=False)
        probe_both = 0.0
        probe_self = 0.0
        for step in range(max_steps):
            weight = 1.0 / (step + 1.0) ** 2
            probe_both += float(
                np.mean(np.cos(samples + theta_rad) ** 2)
            ) * weight
            probe_self += float(np.mean(np.cos(samples) ** 2)) * weight
        if config == "both":
            return probe_both, 0.0, probe_both
        if config == "self":
            return 0.0, probe_self, 0.0
        return probe_both, probe_self, probe_both - probe_self

    if mp is None or get_casimir_material is None:
        raise RuntimeError(
            "Meep module not found. Run in the BigRed 200 meep environment."
        )

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = global_rank == 0
    os.makedirs(".tmp", exist_ok=True)
    os.makedirs("results_rotary_clutch", exist_ok=True)

    z_needle_center = z_tip + H_needle / 2.0
    dx = 1.0 / resolution
    delta_xy = max(0.025, 2.0 * dx)
    delta_z_top = max(0.025, 2.0 * dx)

    # Bottom face lies strictly inside the vacuum gap.
    z_bot = z_tip / 2.0
    z_top = z_tip + H_needle + delta_z_top
    sx_box = w_needle + 2.0 * delta_xy
    sy_box = w_needle + 2.0 * delta_xy
    sz_box = z_top - z_bot
    z_box_center = (z_top + z_bot) / 2.0

    sx = L_plate + 2.0 * (dpml + buffer)
    sy = sx
    z_max = max(z_top + delta_z_top, t_plate + delta_z_top) + buffer + dpml
    sz = 2.0 * z_max
    cell_size = mp.Vector3(sx, sy, sz)

    d_eff = max(0.04, min(z_tip, (W_aperture - w_needle) / 2.0))
    Sigma = 0.5 / d_eff

    sides_info = [
        {
            "center": mp.Vector3(r_rotor - sx_box / 2.0, 0.0, z_box_center),
            "size": mp.Vector3(0.0, sy_box, sz_box),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(r_rotor + sx_box / 2.0, 0.0, z_box_center),
            "size": mp.Vector3(0.0, sy_box, sz_box),
            "orientation": +1.0,
        },
        {
            "center": mp.Vector3(r_rotor, -sy_box / 2.0, z_box_center),
            "size": mp.Vector3(sx_box, 0.0, sz_box),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(r_rotor, +sy_box / 2.0, z_box_center),
            "size": mp.Vector3(sx_box, 0.0, sz_box),
            "orientation": +1.0,
        },
        {
            "center": mp.Vector3(r_rotor, 0.0, z_bot),
            "size": mp.Vector3(sx_box, sy_box, 0.0),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(r_rotor, 0.0, z_top),
            "size": mp.Vector3(sx_box, sy_box, 0.0),
            "orientation": +1.0,
        },
    ]

    pol_list = [mp.Ex, mp.Ey, mp.Ez, mp.Hx, mp.Hy, mp.Hz]
    component_direction = {
        mp.Ex: mp.X, mp.Ey: mp.Y, mp.Ez: mp.Z,
        mp.Dx: mp.X, mp.Dy: mp.Y, mp.Dz: mp.Z,
        mp.Hx: mp.X, mp.Hy: mp.Y, mp.Hz: mp.Z,
        mp.Bx: mp.X, mp.By: mp.Y, mp.Bz: mp.Z,
    }

    num_tasks = 36 * n_max
    start_time = time.time()
    max_walltime_sec = (
        max_walltime_hours * 3600.0
        if max_walltime_hours is not None and max_walltime_hours > 0
        else None
    )

    theta_rad = np.radians(theta_deg)
    xa1 = r_rotor * np.cos(theta_rad)
    ya1 = r_rotor * np.sin(theta_rad)
    xa2 = -xa1
    ya2 = -ya1

    # Invalidate checkpoints generated by the old kernel/source implementation,
    # and reject caches with different simulation parameters.
    cache_parameters = {
        "solver_version": 2,
        "theta_deg": float(theta_deg),
        "r_rotor": float(r_rotor),
        "W_aperture": float(W_aperture),
        "t_plate": float(t_plate),
        "H_needle": float(H_needle),
        "w_needle": float(w_needle),
        "z_tip": float(z_tip),
        "material": material,
        "resolution": float(resolution),
        "n_max": int(n_max),
        "T_run": float(T_run),
        "dpml": float(dpml),
        "buffer": float(buffer),
        "L_plate": float(L_plate),
    }

    def completion_tuple(cfg_name, force, is_complete):
        if cfg_name == "both":
            return force, 0.0, is_complete
        return 0.0, force, is_complete

    def run_one_config(cfg_name):
        chk_file = f".tmp/chk_{chk_tag}_{cfg_name}.json"
        moments_chk = f".tmp/chk_moments_{chk_tag}_{cfg_name}.json"

        if not no_cache and os.path.exists(chk_file):
            try:
                with open(chk_file, "r") as f_chk:
                    data = json.load(f_chk)
                if not isinstance(data, dict) or data.get("parameters") != cache_parameters:
                    raise ValueError("checkpoint parameters or solver version differ")
                force = float(data["force"])
                if not np.isfinite(force):
                    raise ValueError("nonfinite cached force")
                if is_g0:
                    print(
                        f"[{cfg_name.upper()}] Loaded cached force: "
                        f"{force:.6e} from {chk_file}"
                    )
                return completion_tuple(cfg_name, force, True)
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
                if is_g0:
                    print(
                        f"[{cfg_name.upper()}] Notice: Stale/corrupt checkpoint "
                        f"{chk_file} ({err}). Recomputing."
                    )

        completed_moments = {}
        if not no_cache and os.path.exists(moments_chk):
            try:
                with open(moments_chk, "r") as f_mom:
                    chk_data = json.load(f_mom)
                if (
                    not isinstance(chk_data, dict)
                    or chk_data.get("parameters") != cache_parameters
                ):
                    raise ValueError("checkpoint parameters or solver version differ")
                raw_moments = chk_data["completed_moments"]
                if not isinstance(raw_moments, dict):
                    raise ValueError("completed_moments must be a mapping")
                for key, value in raw_moments.items():
                    index = int(key)
                    force = float(value)
                    if (
                        str(index) != key
                        or not 0 <= index < num_tasks
                        or not np.isfinite(force)
                    ):
                        raise ValueError("invalid cached moment")
                    completed_moments[index] = force
                if is_g0:
                    print(
                        f"[{cfg_name.upper()}] Loaded {len(completed_moments)} "
                        f"cached moments from {moments_chk}"
                    )
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
                if is_g0:
                    print(
                        f"[{cfg_name.upper()}] Notice: Stale/corrupt moments file "
                        f"{moments_chk} ({err}). Starting fresh."
                    )
                completed_moments = {}

        total_force = 0.0
        moment_durations = []

        for task_idx in range(num_tasks):
            if task_idx in completed_moments:
                f_cached = completed_moments[task_idx]
                total_force += f_cached
                if is_g0:
                    print(
                        f"  [{cfg_name.upper()}][Rank 0] Skipped moment "
                        f"{task_idx + 1}/{num_tasks} [CACHED]: "
                        f"force_integral={f_cached:+.6e}",
                        flush=True,
                    )
                continue

            if max_walltime_sec is not None:
                elapsed_sec = time.time() - start_time
                avg_dur = (
                    float(np.mean(moment_durations)) if moment_durations else 2400.0
                )
                if elapsed_sec + avg_dur * 1.15 >= max_walltime_sec:
                    if is_g0:
                        print(
                            f"\n[WALLTIME GUARD] Elapsed {elapsed_sec / 3600:.2f}h "
                            f"+ estimated moment ({avg_dur / 60:.1f}m) >= limit "
                            f"({max_walltime_hours:.2f}h). Pausing cleanly.",
                            flush=True,
                        )
                    break

            moment_start_time = time.time()
            p = task_idx // (n_max * 6)
            n = task_idx % (n_max * 6)
            curr_pol = pol_list[p]
            ft = mp.E_stuff if curr_pol in [mp.Ex, mp.Ey, mp.Ez] else mp.H_stuff

            mat_obj = get_casimir_material(
                material, Sigma, ft, theta=0.0, eps_bg=1.0
            )
            if ft == mp.E_stuff:
                bg_material = mp.Medium(epsilon=1.0, D_conductivity=Sigma)
            else:
                bg_material = mp.Medium(epsilon=1.0, B_conductivity=Sigma)

            geometry = []
            if cfg_name == "both":
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, -t_plate / 2.0),
                    size=mp.Vector3(L_plate, L_plate, t_plate),
                    material=mat_obj,
                ))
                geometry.append(mp.Cylinder(
                    radius=W_aperture / 2.0,
                    height=t_plate + 0.001,
                    center=mp.Vector3(xa1, ya1, -t_plate / 2.0),
                    material=bg_material,
                ))
                geometry.append(mp.Cylinder(
                    radius=W_aperture / 2.0,
                    height=t_plate + 0.001,
                    center=mp.Vector3(xa2, ya2, -t_plate / 2.0),
                    material=bg_material,
                ))

            geometry.append(mp.Block(
                center=mp.Vector3(r_rotor, 0.0, z_needle_center),
                size=mp.Vector3(w_needle, w_needle, H_needle),
                material=mat_obj,
            ))
            geometry.append(mp.Block(
                center=mp.Vector3(-r_rotor, 0.0, z_needle_center),
                size=mp.Vector3(w_needle, w_needle, H_needle),
                material=mat_obj,
            ))

            sim = mp.Simulation(
                cell_size=cell_size,
                geometry=geometry,
                resolution=resolution,
                boundary_layers=[mp.PML(dpml)],
                default_material=bg_material,
                Courant=0.5,
                eps_averaging=False,
                force_complex_fields=True,
            )

            sim.init_sim()
            dt = sim.Courant / resolution
            T_steps = int(T_run / dt)
            if T_steps <= 0:
                sim.reset_meep()
                raise ValueError("T_run must span at least one simulation time step")

            # make_casimir_gfunc expects the field-type enum, not a component.
            gt = mp.make_casimir_gfunc(T_run, dt, Sigma, ft)
            addr = int(gt)
            if addr == 0:
                sim.reset_meep()
                raise RuntimeError("Meep returned a null Casimir kernel pointer")
            double_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))
            data = np.ctypeslib.as_array(double_ptr, shape=(T_steps * 2,))
            gt_arr = data[0::2] + 1j * data[1::2]
            if not np.all(np.isfinite(gt_arr)):
                sim.reset_meep()
                raise RuntimeError("Meep returned a nonfinite Casimir time kernel")

            s = n % 6
            nr = n // 6
            m1, m2 = get_src_index(nr)
            side = sides_info[s]
            side_center = side["center"]
            side_size = side["size"]
            side_orientation = side["orientation"]

            if s in [0, 1]:
                mx, my, mz = 0, m1, m2
            elif s in [2, 3]:
                mx, my, mz = m1, 0, m2
            else:
                mx, my, mz = m1, m2, 0

            def make_amp_func(mx_val, my_val, mz_val, size_vec, center_vec):
                sx_v, sy_v, sz_v = size_vec.x, size_vec.y, size_vec.z
                Nx = (
                    (2.0 if mx_val > 0 else 1.0) / sx_v
                    if sx_v > 1e-15 else 1.0
                )
                Ny = (
                    (2.0 if my_val > 0 else 1.0) / sy_v
                    if sy_v > 1e-15 else 1.0
                )
                Nz = (
                    (2.0 if mz_val > 0 else 1.0) / sz_v
                    if sz_v > 1e-15 else 1.0
                )
                factor = np.sqrt(Nx * Ny * Nz)

                def amp_func(pt):
                    # Meep supplies coordinates relative to the source center.
                    x = pt.x + 0.5 * sx_v
                    y = pt.y + 0.5 * sy_v
                    z = pt.z + 0.5 * sz_v
                    kx = mx_val * np.pi / sx_v if sx_v > 1e-15 else 0.0
                    ky = my_val * np.pi / sy_v if sy_v > 1e-15 else 0.0
                    kz = mz_val * np.pi / sz_v if sz_v > 1e-15 else 0.0
                    return (
                        factor * np.cos(kx * x) * np.cos(ky * y) * np.cos(kz * z)
                    )

                return amp_func

            src_vol = mp.Volume(center=side_center, size=side_size, dims=3)
            amp_fn = make_amp_func(mx, my, mz, side_size, side_center)
            sim.change_sources([
                mp.Source(
                    src=mp.CustomSource(
                        src_func=lambda t: 1.0 / dt,
                        start_time=-0.25 * dt,
                        end_time=0.75 * dt,
                    ),
                    component=curr_pol,
                    center=side_center,
                    size=side_size,
                    amp_func=amp_fn,
                )
            ])

            sim.reset_meep()
            sim.init_sim()
            force_integral = 0.0
            try:
                for step in range(T_steps):
                    sim.fields.step()
                    f_temp = sim.fields.casimir_stress_dct_integral(
                        mp.Z, component_direction[curr_pol],
                        float(mx), float(my), float(mz),
                        ft, src_vol.swigobj,
                    )
                    force_integral += float(
                        np.imag(gt_arr[step] * dt * side_orientation * f_temp)
                    )
                if not np.isfinite(force_integral):
                    raise RuntimeError(
                        f"Nonfinite force in {cfg_name} moment {task_idx}"
                    )
            finally:
                sim.reset_meep()

            total_force += force_integral
            if not np.isfinite(total_force):
                raise RuntimeError(f"Nonfinite accumulated force in {cfg_name}")
            completed_moments[task_idx] = force_integral
            moment_durations.append(time.time() - moment_start_time)

            if is_g0:
                tmp_path = f"{moments_chk}.tmp_{os.getpid()}"
                try:
                    with open(tmp_path, "w") as f_chk:
                        json.dump({
                            "parameters": cache_parameters,
                            "completed_moments": {
                                str(k): v for k, v in completed_moments.items()
                            },
                        }, f_chk, indent=4, allow_nan=False)
                    os.replace(tmp_path, moments_chk)
                except OSError as write_err:
                    print(
                        f"Warning: Failed writing incremental checkpoint: {write_err}",
                        flush=True,
                    )
                print(
                    f"  [{cfg_name.upper()}][Rank 0] Done moment "
                    f"{task_idx + 1}/{num_tasks}: "
                    f"force_integral={force_integral:+.6e} "
                    f"({moment_durations[-1]:.1f}s)",
                    flush=True,
                )

        is_complete = len(completed_moments) >= num_tasks
        if is_g0 and is_complete:
            tmp_path = f"{chk_file}.tmp_{os.getpid()}"
            try:
                with open(tmp_path, "w") as f_out:
                    json.dump({
                        "parameters": cache_parameters,
                        "force": float(total_force),
                        "model": "rotary_casimir_clutch",
                        "dataset": "rotary_casimir_clutch_meep",
                        "status": "completed",
                        "executed_at": datetime.now(timezone.utc).isoformat(),
                    }, f_out, indent=4, allow_nan=False)
                os.replace(tmp_path, chk_file)
                print(
                    f"[{cfg_name.upper()}] Complete. "
                    f"Single-needle force: {total_force:+.6e}"
                )
            except OSError as save_err:
                print(
                    f"Warning: Failed writing config checkpoint {chk_file}: {save_err}",
                    flush=True,
                )

        return completion_tuple(cfg_name, total_force, is_complete)

    if config == "both":
        f1_both, _, complete = run_one_config("both")
        if not complete:
            raise WalltimeContinuationRequired("The both configuration is incomplete")
        return f1_both, 0.0, f1_both

    if config == "self":
        _, f1_self, complete = run_one_config("self")
        if not complete:
            raise WalltimeContinuationRequired("The self configuration is incomplete")
        return 0.0, f1_self, 0.0

    f1_both, _, both_complete = run_one_config("both")
    if not both_complete:
        raise WalltimeContinuationRequired("The both configuration is incomplete")
    _, f1_self, self_complete = run_one_config("self")
    if not self_complete:
        raise WalltimeContinuationRequired("The self configuration is incomplete")
    return f1_both, f1_self, f1_both - f1_self


def main():
    parser = argparse.ArgumentParser(
        description="Rotary Vacuum Casimir Clutch Simulation Engine"
    )
    parser.add_argument("--task-id", type=int, default=1, help="Task index (1-6)")
    parser.add_argument("--theta", type=float, default=0.0, help="Rotation angle (deg)")
    parser.add_argument("--r-rotor", type=float, default=0.35)
    parser.add_argument("--W-aperture", type=float, default=0.35)
    parser.add_argument("--t-plate", type=float, default=0.025)
    parser.add_argument("--H-needle", type=float, default=0.25)
    parser.add_argument("--w-needle", type=float, default=0.04)
    parser.add_argument("--z-tip", type=float, default=0.015)
    parser.add_argument("--material", type=str, default="Gold")
    parser.add_argument("--res", type=int, default=80, help="Pixels per micron")
    parser.add_argument("--nmax", type=int, default=1, help="Multipole cutoff")
    parser.add_argument(
        "--config", default="all", choices=["both", "self", "all"]
    )
    parser.add_argument("--T-run", type=float, default=12.0)
    parser.add_argument("--max-walltime-hours", type=float, default=7.5)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Run a deterministic numerical micro-probe for this many steps (no Meep)",
    )
    args = parser.parse_args()

    if args.res <= 0:
        parser.error("--res must be positive")
    if args.max_steps is not None and args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")

    chk_tag = (
        f"rotary_clutch_th_{args.theta:.1f}_r_{args.r_rotor:.3f}"
        f"_W_{args.W_aperture:.3f}_ztip_{args.z_tip:.4f}_res_{args.res}"
    )
    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = global_rank == 0
    is_probe = args.max_steps is not None

    if is_g0:
        print("=" * 80)
        print("ROTARY VACUUM CASIMIR CLUTCH SOLVER")
        print(f"Task ID: {args.task_id} | Rotation angle: {args.theta:.1f} deg")
        print(f"Material: {args.material}, Resolution: {args.res}")
        print(f"Mode: {'DETERMINISTIC MICRO-PROBE (NONPHYSICAL)' if is_probe else 'MEEP'}")
        print("=" * 80, flush=True)

    try:
        f1_both, f1_self, f1_net = run_rotary_casimir_clutch_simulation(
            theta_deg=args.theta,
            r_rotor=args.r_rotor,
            W_aperture=args.W_aperture,
            t_plate=args.t_plate,
            H_needle=args.H_needle,
            w_needle=args.w_needle,
            z_tip=args.z_tip,
            material=args.material,
            resolution=args.res,
            n_max=args.nmax,
            config=args.config,
            T_run=args.T_run,
            chk_tag=chk_tag,
            max_walltime_hours=args.max_walltime_hours,
            no_cache=args.no_cache,
            max_steps=args.max_steps,
        )
    except WalltimeContinuationRequired as err:
        if is_g0:
            print(
                f"{err}. No final task output written; resume from checkpoints.",
                flush=True,
            )
        return 99
    except ValueError as err:
        parser.error(str(err))

    if is_g0 and (args.config == "all" or is_probe):
        f_total_meep = 2.0 * f1_net
        f_total_fN = f_total_meep * MEEP_FORCE_TO_SI * 1e15
        pressure_Pa = (f1_net / args.w_needle ** 2) * MEEP_TO_PA

        result_data = {
            "task_id": args.task_id,
            "architecture": "rotary_casimir_clutch",
            "model": "rotary_casimir_clutch",
            "dataset": (
                "rotary_casimir_clutch_micro_probe"
                if is_probe else "rotary_casimir_clutch_meep"
            ),
            "status": "completed",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "backend": "numpy_micro_probe" if is_probe else "meep",
            "is_physical_simulation": not is_probe,
            "max_steps": args.max_steps,
            "config": args.config,
            "theta_deg": float(args.theta),
            "r_rotor_nm": float(args.r_rotor * 1e3),
            "W_aperture_nm": float(args.W_aperture * 1e3),
            "t_plate_nm": float(args.t_plate * 1e3),
            "H_needle_nm": float(args.H_needle * 1e3),
            "w_needle_nm": float(args.w_needle * 1e3),
            "z_tip_nm": float(args.z_tip * 1e3),
            "material": args.material,
            "resolution": args.res,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if is_probe:
            result_data.update({
                "probe_both": float(f1_both),
                "probe_self": float(f1_self),
                "probe_net": float(f1_net),
                "regime": "MICRO_PROBE",
            })
        else:
            result_data.update({
                "force_single_meep": float(f1_net),
                "force_total_meep": float(f_total_meep),
                "force_total_fN": float(f_total_fN),
                "pressure_Pa": float(pressure_Pa),
                "regime": (
                    "REPULSIVE" if f_total_meep > 0
                    else "ATTRACTIVE" if f_total_meep < 0
                    else "ZERO"
                ),
            })

        suffix = f"_probe_{args.config}" if is_probe else ""
        out_dest = (
            f"results_rotary_clutch/task_{args.task_id:03d}"
            f"_th_{int(args.theta)}deg{suffix}.json"
        )
        os.makedirs("results_rotary_clutch", exist_ok=True)
        tmp_path = f"{out_dest}.tmp_{os.getpid()}"
        with open(tmp_path, "w") as f:
            json.dump(result_data, f, indent=4, allow_nan=False)
        os.replace(tmp_path, out_dest)
        log_result_metrics(result_data)

        print("\n" + "=" * 80)
        if is_probe:
            print("DETERMINISTIC MICRO-PROBE COMPLETE (NONPHYSICAL)")
            print(f"Probe net value: {f1_net:+.6e}")
        else:
            print("ROTARY CASIMIR CLUTCH SIMULATION COMPLETE")
            print(f"Single-needle net force (Meep): {f1_net:+.6e}")
            print(f"Total rotor force (fN): {f_total_fN:+.4f}")
            print(f"Needle pressure (Pa): {pressure_Pa:+.4e}")
        print(f"Results saved to: {out_dest}")
        print("=" * 80 + "\n", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
