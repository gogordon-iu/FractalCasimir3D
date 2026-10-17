#!/usr/bin/env python3
"""
Dual-Fractal Rotary Vacuum Casimir Clutch Simulation Engine.

Runs Meep stress-tensor integration for a fractal rotor and perforated stator.
With --max-steps, runs a deterministic synthetic micro-probe instead of Meep.
Micro-probe forces are diagnostic values, not physical Casimir predictions.
"""

import os
import sys
import json
import time
import ctypes
import argparse
import inspect
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

from execution.fractal_rotary_clutch_geometry import (
    get_fractal_clutch_elements,
    compute_plate_area_fraction,
)

try:
    from utils.metrics_logger import log_metrics
except ImportError:
    log_metrics = None


def get_src_index(n):
    r = int((np.sqrt(8 * n + 1) - 1) / 2)
    c = n - r * (r + 1) // 2
    return r - c, c


# Meep units: hbar = c = 1, length unit a = 1 um.
MEEP_TO_PA = 0.031615
MEEP_FORCE_TO_SI = 3.1615e-14


def _executed_at():
    return datetime.now(timezone.utc).isoformat()


def _result_metadata(micro_probe=False):
    return {
        "model": "dual_fractal_rotary_casimir_clutch",
        "dataset": "synthetic_micro_probe" if micro_probe else "fractal_rotary_clutch",
        "status": "completed",
        "executed_at": _executed_at(),
    }


def _log_result(result):
    """Support common dictionary and model/dataset/metrics logger interfaces."""
    if log_metrics is None:
        logging.getLogger(__name__).warning(
            "utils.metrics_logger is unavailable; metrics: %s",
            json.dumps(result, allow_nan=False),
        )
        return

    signature = inspect.signature(log_metrics)
    candidates = [
        ((), {
            "model": result["model"],
            "dataset": result["dataset"],
            "metrics": result,
        }),
        ((result,), {}),
        ((), {"metrics": result}),
        ((), {"model_name": result["model"],
              "dataset_name": result["dataset"],
              "metrics": result}),
    ]
    for positional, keyword in candidates:
        try:
            signature.bind(*positional, **keyword)
        except TypeError:
            continue
        log_metrics(*positional, **keyword)
        return
    raise TypeError("Unsupported utils.metrics_logger.log_metrics interface")


def _validate_parameters(
    N_fractal, theta_deg, L_fractal, W1_aperture, w1_needle,
    H_needle, t_plate, z_tip, resolution, n_max, config,
    T_run, dpml, buffer, max_walltime_hours, max_steps,
):
    for name, value in (
        ("N_fractal", N_fractal), ("resolution", resolution), ("n_max", n_max)
    ):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} must be an integer")
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if N_fractal not in (1, 2, 3):
        raise ValueError("N_fractal must be 1, 2, or 3")
    for name, value in (
        ("L_fractal", L_fractal), ("W1_aperture", W1_aperture),
        ("w1_needle", w1_needle), ("H_needle", H_needle),
        ("t_plate", t_plate), ("z_tip", z_tip), ("T_run", T_run),
        ("dpml", dpml),
    ):
        if not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError(f"{name} must be numeric")
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if not np.isfinite(theta_deg):
        raise ValueError("theta_deg must be finite")
    if not np.isfinite(buffer) or buffer < 0:
        raise ValueError("buffer must be finite and nonnegative")
    if W1_aperture <= w1_needle:
        raise ValueError("W1_aperture must exceed w1_needle")
    if config not in ("both", "self", "all"):
        raise ValueError("config must be 'both', 'self', or 'all'")
    if max_walltime_hours is not None and not np.isfinite(max_walltime_hours):
        raise ValueError("max_walltime_hours must be finite or None")
    if max_steps is not None:
        if (
            isinstance(max_steps, (bool, np.bool_))
            or not isinstance(max_steps, (int, np.integer))
            or max_steps < 0
        ):
            raise ValueError("max_steps must be a nonnegative integer")
    elif int(T_run * resolution / 0.5) < 1:
        raise ValueError("T_run must span at least one FDTD time step")


def _validate_elements(elements):
    if not elements:
        raise ValueError("Fractal geometry contains no elements")
    for elem in elements:
        for key in ("cx", "cy", "w_needle", "W_aperture"):
            if not np.isfinite(elem[key]):
                raise ValueError(f"Geometry field {key} must be finite")
        if elem["w_needle"] <= 0 or elem["W_aperture"] <= 0:
            raise ValueError("Needle widths and aperture diameters must be positive")


def _load_force(path):
    with open(path, "r") as stream:
        force = float(json.load(stream)["force"])
    if not np.isfinite(force):
        raise ValueError(f"Non-finite force in checkpoint {path}")
    return force


def _micro_probe(elements, theta_deg, max_steps, config):
    """Bounded synthetic arithmetic probe; does not estimate physical forces."""
    area = sum(elem["w_needle"] ** 2 for elem in elements)
    angular_factor = float(np.cos(4.0 * np.radians(theta_deg)))
    response = 0.0
    for step in range(max_steps):
        response += area * angular_factor / ((step + 1.0) ** 2)
    if config == "self":
        return 0.0, 0.0, 0.0, True
    return response, 0.0, response, True


def run_fractal_rotary_clutch_simulation(
    N_fractal=1,
    theta_deg=0.0,
    L_fractal=1.05,
    W1_aperture=0.25,
    w1_needle=0.035,
    H_needle=0.25,
    t_plate=0.025,
    z_tip=0.01555,
    material="Gold",
    resolution=60,
    n_max=1,
    config="all",
    T_run=3.0,
    dpml=0.20,
    buffer=0.15,
    chk_tag="fractal_clutch",
    max_walltime_hours=7.0,
    no_cache=False,
    max_steps=None,
):
    """
    Execute 3D FDTD stress-tensor integration.

    If max_steps is supplied, return synthetic micro-probe values without
    initializing Meep or reading/writing physical force checkpoints.
    """
    _validate_parameters(
        N_fractal, theta_deg, L_fractal, W1_aperture, w1_needle,
        H_needle, t_plate, z_tip, resolution, n_max, config,
        T_run, dpml, buffer, max_walltime_hours, max_steps,
    )
    elements = get_fractal_clutch_elements(
        N_fractal, L_fractal, W1=W1_aperture, w1=w1_needle
    )
    _validate_elements(elements)

    if max_steps is not None:
        return _micro_probe(elements, theta_deg, max_steps, config)

    if mp is None or get_casimir_material is None:
        raise RuntimeError("Meep module not found. Run in the BigRed 200 meep environment.")

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = global_rank == 0
    os.makedirs(".tmp", exist_ok=True)
    os.makedirs("results_fractal_rotary_clutch", exist_ok=True)

    z_needle_center = z_tip + H_needle / 2.0
    dx = 1.0 / resolution
    theta_rad = np.radians(theta_deg)
    cos_th, sin_th = np.cos(theta_rad), np.sin(theta_rad)

    chk_both = f".tmp/chk_{chk_tag}_both.json"
    chk_self = f".tmp/chk_{chk_tag}_self.json"
    if not no_cache:
        if config == "all" and os.path.exists(chk_both) and os.path.exists(chk_self):
            f1_both = _load_force(chk_both)
            f1_self = _load_force(chk_self)
            if is_g0:
                print(f"[BOTH] Loaded cached force: {f1_both:.6e} from {chk_both}")
                print(f"[SELF] Loaded cached force: {f1_self:.6e} from {chk_self}")
            return f1_both, f1_self, f1_both - f1_self, True
        elif config == "both" and os.path.exists(chk_both):
            f1_both = _load_force(chk_both)
            if is_g0:
                print(f"[BOTH] Loaded cached force: {f1_both:.6e} from {chk_both}")
            return f1_both, 0.0, f1_both, True
        elif config == "self" and os.path.exists(chk_self):
            f1_self = _load_force(chk_self)
            if is_g0:
                print(f"[SELF] Loaded cached force: {f1_self:.6e} from {chk_self}")
            return 0.0, f1_self, 0.0, True

    delta_xy = max(w1_needle / 2.0, 2.0 * dx)
    delta_z_top = max(w1_needle / 2.0, 2.0 * dx)
    z_bot = z_tip / 2.0
    z_top = z_tip + H_needle + delta_z_top

    max_needle_x = max(abs(elem["cx"]) + elem["w_needle"] / 2.0 for elem in elements)
    max_needle_y = max(abs(elem["cy"]) + elem["w_needle"] / 2.0 for elem in elements)
    sx_box = 2.0 * (max_needle_x + delta_xy)
    sy_box = 2.0 * (max_needle_y + delta_xy)
    sz_box = z_top - z_bot
    z_box_center = (z_top + z_bot) / 2.0

    max_aperture_extent = max(
        abs(elem["cx"]) + elem["W_aperture"] / 2.0 for elem in elements
    )
    L_plate = max(L_fractal, 2.0 * (max_aperture_extent + W1_aperture))
    sx = L_plate + 2.0 * (dpml + buffer)
    sy = sx
    z_max = max(z_top + delta_z_top, t_plate + delta_z_top) + buffer + dpml
    sz = 2.0 * z_max
    cell_size = mp.Vector3(sx, sy, sz)

    d_eff = min(z_tip, (W1_aperture - w1_needle) / 2.0)
    Sigma = 0.5 / d_eff

    sides_info = [
        {"center": mp.Vector3(-sx_box / 2.0, 0.0, z_box_center),
         "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(+sx_box / 2.0, 0.0, z_box_center),
         "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(0.0, -sy_box / 2.0, z_box_center),
         "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(0.0, +sy_box / 2.0, z_box_center),
         "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(0.0, 0.0, z_bot),
         "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": -1.0},
        {"center": mp.Vector3(0.0, 0.0, z_top),
         "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": +1.0},
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

    def run_one_config(cfg_name):
        chk_file = f".tmp/chk_{chk_tag}_{cfg_name}.json"
        moments_chk = f".tmp/chk_moments_{chk_tag}_{cfg_name}.json"

        if not no_cache and os.path.exists(chk_file):
            force = _load_force(chk_file)
            if is_g0:
                print(f"[{cfg_name.upper()}] Loaded cached force: {force:.6e} from {chk_file}")
            return force, True

        completed_moments = {}
        if not no_cache and os.path.exists(moments_chk):
            with open(moments_chk, "r") as f_mom:
                chk_data = json.load(f_mom)
            completed_moments = {
                int(k): float(v)
                for k, v in chk_data.get("completed_moments", {}).items()
            }
            if any(
                k < 0 or k >= num_tasks or not np.isfinite(v)
                for k, v in completed_moments.items()
            ):
                raise ValueError(f"Invalid cached moments in {moments_chk}")
            if is_g0:
                print(
                    f"[{cfg_name.upper()}] Loaded {len(completed_moments)} "
                    f"cached moments from {moments_chk}"
                )

        total_force = 0.0
        moment_durations = []

        for task_idx in range(num_tasks):
            if task_idx in completed_moments:
                f_cached = completed_moments[task_idx]
                total_force += f_cached
                if is_g0:
                    print(
                        f"  [{cfg_name.upper()}][Rank 0] Skipped moment "
                        f"{task_idx+1}/{num_tasks} [CACHED]: "
                        f"force_integral={f_cached:+.6e}", flush=True
                    )
                continue

            if moment_durations and max_walltime_sec is not None:
                elapsed_sec = time.time() - start_time
                avg_dur = np.mean(moment_durations)
                if elapsed_sec + avg_dur * 1.15 >= max_walltime_sec:
                    if is_g0:
                        print(
                            f"\n[WALLTIME GUARD] Elapsed {elapsed_sec/3600:.2f}h "
                            f"+ estimated moment ({avg_dur/60:.1f}m) >= limit "
                            f"({max_walltime_hours:.2f}h). Pausing cleanly.",
                            flush=True,
                        )
                    break

            moment_start_time = time.time()
            p = task_idx // (n_max * 6)
            n = task_idx % (n_max * 6)
            curr_pol = pol_list[p]
            ft = mp.E_stuff if curr_pol in [mp.Ex, mp.Ey, mp.Ez] else mp.H_stuff

            mat_obj = get_casimir_material(material, Sigma, ft, theta=0.0, eps_bg=1.0)
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
                for elem in elements:
                    cx_orig, cy_orig = elem["cx"], elem["cy"]
                    cx_rot = cx_orig * cos_th - cy_orig * sin_th
                    cy_rot = cx_orig * sin_th + cy_orig * cos_th
                    geometry.append(mp.Cylinder(
                        radius=elem["W_aperture"] / 2.0,
                        height=t_plate + 2.0 * dx,
                        center=mp.Vector3(cx_rot, cy_rot, -t_plate / 2.0),
                        material=bg_material,
                    ))

            for elem in elements:
                geometry.append(mp.Block(
                    center=mp.Vector3(elem["cx"], elem["cy"], z_needle_center),
                    size=mp.Vector3(elem["w_needle"], elem["w_needle"], H_needle),
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
            if T_steps < 1:
                raise ValueError("T_run must span at least one FDTD time step")

            # The kernel API expects a field-type enum, not a component enum.
            gt = mp.make_casimir_gfunc(T_run, dt, Sigma, ft)
            addr = int(gt)
            if not addr:
                raise RuntimeError("Meep returned a null Casimir kernel pointer")
            double_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))
            data = np.ctypeslib.as_array(double_ptr, shape=(T_steps * 2,))
            gt_arr = data[0::2] + 1j * data[1::2]
            if not np.all(np.isfinite(gt_arr)):
                raise RuntimeError("Meep returned a non-finite Casimir time kernel")

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
                Nx = (2.0 / sx_v if mx_val > 0 else 1.0 / sx_v) if sx_v > 1e-15 else 1.0
                Ny = (2.0 / sy_v if my_val > 0 else 1.0 / sy_v) if sy_v > 1e-15 else 1.0
                Nz = (2.0 / sz_v if mz_val > 0 else 1.0 / sz_v) if sz_v > 1e-15 else 1.0
                factor = np.sqrt(Nx * Ny * Nz)

                def amp_func(pt):
                    # Source coordinates are already relative to side_center.
                    x = pt.x + 0.5 * sx_v
                    y = pt.y + 0.5 * sy_v
                    z = pt.z + 0.5 * sz_v
                    kx = mx_val * np.pi / sx_v if sx_v > 1e-15 else 0.0
                    ky = my_val * np.pi / sy_v if sy_v > 1e-15 else 0.0
                    kz = mz_val * np.pi / sz_v if sz_v > 1e-15 else 0.0
                    return factor * np.cos(kx * x) * np.cos(ky * y) * np.cos(kz * z)

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
            for step in range(T_steps):
                sim.fields.step()
                f_temp = sim.fields.casimir_stress_dct_integral(
                    mp.Z, component_direction[curr_pol],
                    float(mx), float(my), float(mz),
                    ft, src_vol.swigobj,
                )
                force_integral += np.imag(gt_arr[step] * dt * side_orientation * f_temp)
            if not np.isfinite(force_integral):
                raise RuntimeError(f"Non-finite force for {cfg_name} moment {task_idx}")

            total_force += force_integral
            completed_moments[task_idx] = float(force_integral)
            moment_durations.append(time.time() - moment_start_time)

            if is_g0:
                tmp_path = f"{moments_chk}.tmp_{os.getpid()}"
                with open(tmp_path, "w") as f_chk:
                    json.dump({
                        "completed_moments": {
                            str(k): v for k, v in completed_moments.items()
                        },
                        "model": "dual_fractal_rotary_casimir_clutch",
                        "dataset": "fractal_rotary_clutch",
                        "status": (
                            "completed" if len(completed_moments) == num_tasks else "pending"
                        ),
                        "executed_at": _executed_at(),
                    }, f_chk, indent=4, allow_nan=False)
                os.replace(tmp_path, moments_chk)
                print(
                    f"  [{cfg_name.upper()}][Rank 0] Done moment "
                    f"{task_idx+1}/{num_tasks}: force_integral={force_integral:+.6e} "
                    f"({moment_durations[-1]:.1f}s)", flush=True
                )

        is_done = len(completed_moments) == num_tasks
        if not np.isfinite(total_force):
            raise RuntimeError(f"Non-finite total force for {cfg_name}")
        if is_g0 and is_done:
            checkpoint = {"force": float(total_force), **_result_metadata()}
            with open(chk_file, "w") as f_out:
                json.dump(checkpoint, f_out, indent=4, allow_nan=False)
            print(f"[{cfg_name.upper()}] Complete. Total rotor force: {total_force:+.6e}")

        return total_force, is_done

    if config == "both":
        f1_both, both_done = run_one_config("both")
        return f1_both, 0.0, f1_both, both_done
    elif config == "self":
        f1_self, self_done = run_one_config("self")
        return 0.0, f1_self, 0.0, self_done
    else:
        f1_both, both_done = run_one_config("both")
        if both_done:
            f1_self, self_done = run_one_config("self")
        else:
            f1_self, self_done = 0.0, False
        all_done = bool(both_done and self_done)
        f1_sub = f1_both - f1_self if all_done else 0.0
        return f1_both, f1_self, f1_sub, all_done


def main():
    parser = argparse.ArgumentParser(
        description="Dual-Fractal Rotary Vacuum Casimir Clutch"
    )
    parser.add_argument("--task-id", type=int, default=1, help="Task index (1-8)")
    parser.add_argument("--N-fractal", type=int, default=1, help="Prefractal generation N")
    parser.add_argument("--theta", type=float, default=0.0, help="Rotation angle (deg)")
    parser.add_argument("--L-fractal", type=float, default=1.05, help="Fractal span (um)")
    parser.add_argument("--W1-aperture", type=float, default=0.25, help="Aperture diameter (um)")
    parser.add_argument("--w1-needle", type=float, default=0.035, help="Needle width (um)")
    parser.add_argument("--H-needle", type=float, default=0.25, help="Needle height (um)")
    parser.add_argument("--t-plate", type=float, default=0.025, help="Plate thickness (um)")
    parser.add_argument("--z-tip", type=float, default=0.01722, help="Tip clearance (um)")
    parser.add_argument("--material", type=str, default="Gold")
    parser.add_argument("--res", type=int, default=60, help="Grid resolution (pixels/um)")
    parser.add_argument("--nmax", type=int, default=1, help="Multipole cutoff")
    parser.add_argument("--config", type=str, default="all", choices=["both", "self", "all"])
    parser.add_argument("--T-run", type=float, default=3.0, help="FDTD duration")
    parser.add_argument("--max-walltime-hours", type=float, default=7.0)
    parser.add_argument("--no-cache", action="store_true", help="Bypass checkpoints")
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Run a deterministic synthetic micro-probe for at most this many steps; no Meep",
    )
    args = parser.parse_args()

    try:
        _validate_parameters(
            args.N_fractal, args.theta, args.L_fractal, args.W1_aperture,
            args.w1_needle, args.H_needle, args.t_plate, args.z_tip,
            args.res, args.nmax, args.config, args.T_run, 0.20, 0.15,
            args.max_walltime_hours, args.max_steps,
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    micro_probe = args.max_steps is not None
    chk_tag = (
        f"fractal_clutch_task_{args.task_id:03d}_N_{args.N_fractal}_th_{args.theta:.1f}_"
        f"ztip_{args.z_tip:.4f}_res_{args.res}_Trun_{args.T_run:.1f}"
    )
    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = global_rank == 0

    if is_g0:
        elements_preview = get_fractal_clutch_elements(
            args.N_fractal, args.L_fractal, W1=args.W1_aperture, w1=args.w1_needle
        )
        _validate_elements(elements_preview)
        f_area = compute_plate_area_fraction(elements_preview, args.L_fractal)
        d_avg = (1.0 - f_area) * args.z_tip + f_area * (args.z_tip + args.t_plate)
        print("=" * 85)
        print(f"DUAL-FRACTAL ROTARY VACUUM CASIMIR CLUTCH (Generation N = {args.N_fractal})")
        print(f"Task ID: {args.task_id} | Rotation Angle theta: {args.theta:.1f} deg")
        print(f"Invariant Average Distance <d>: {d_avg*1e3:.2f} nm")
        print(f"Fractal Span L: {args.L_fractal*1e3:.1f} nm")
        print(f"Primary Aperture W1: {args.W1_aperture*1e3:.1f} nm")
        print(f"Primary Needle Width: {args.w1_needle*1e3:.1f} nm")
        print(f"Needle Height: {args.H_needle*1e3:.1f} nm")
        print(f"Tip Clearance: {args.z_tip*1e3:.1f} nm")
        print(f"Material: {args.material}, Resolution: {args.res} (dx = {1000/args.res:.2f} nm)")
        if micro_probe:
            print(f"SYNTHETIC MICRO-PROBE: {args.max_steps} steps; no physical force prediction")
        print("=" * 85, flush=True)

    f1_both, f1_self, f1_net, all_done = run_fractal_rotary_clutch_simulation(
        N_fractal=args.N_fractal,
        theta_deg=args.theta,
        L_fractal=args.L_fractal,
        W1_aperture=args.W1_aperture,
        w1_needle=args.w1_needle,
        H_needle=args.H_needle,
        t_plate=args.t_plate,
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

    if not all_done:
        if is_g0:
            print(
                f"\n[WALLTIME CHECKPOINT] Task {args.task_id}: "
                "PENDING remaining moments; checkpointed to .tmp/.",
                flush=True,
            )
            with open(f".tmp/clutch_task_{args.task_id:03d}_pending.flag", "w") as fp:
                fp.write(f"pending:{time.time()}\n")
        return

    # Synthetic probes must not mark physical simulation tasks complete.
    if is_g0 and not micro_probe:
        with open(f".tmp/clutch_task_{args.task_id:03d}_complete.flag", "w") as fp:
            fp.write(f"complete:{time.time()}\n")
        flag_pending = f".tmp/clutch_task_{args.task_id:03d}_pending.flag"
        if os.path.exists(flag_pending):
            os.remove(flag_pending)

    if is_g0 and (args.config == "all" or micro_probe):
        elements = get_fractal_clutch_elements(
            args.N_fractal, args.L_fractal, W1=args.W1_aperture, w1=args.w1_needle
        )
        _validate_elements(elements)
        A_rotor = sum(elem["w_needle"] ** 2 for elem in elements)
        if not np.isfinite(A_rotor) or A_rotor <= 0:
            raise ValueError("Total rotor cross-sectional area must be finite and positive")

        f_area = compute_plate_area_fraction(elements, args.L_fractal)
        d_avg_um = (1.0 - f_area) * args.z_tip + f_area * (args.z_tip + args.t_plate)
        result_data = {
            **_result_metadata(micro_probe),
            "task_id": args.task_id,
            "architecture": "dual_fractal_rotary_casimir_clutch",
            "mode": "micro_probe" if micro_probe else "meep",
            "config": args.config,
            "max_steps": args.max_steps,
            "N_fractal": args.N_fractal,
            "theta_deg": float(args.theta),
            "d_average_nm": float(d_avg_um * 1e3),
            "L_fractal_nm": float(args.L_fractal * 1e3),
            "W1_aperture_nm": float(args.W1_aperture * 1e3),
            "w1_needle_nm": float(args.w1_needle * 1e3),
            "H_needle_nm": float(args.H_needle * 1e3),
            "t_plate_nm": float(args.t_plate * 1e3),
            "z_tip_nm": float(args.z_tip * 1e3),
            "material": args.material,
            "resolution": args.res,
            "num_needles": len(elements),
            "A_rotor_um2": float(A_rotor),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if micro_probe:
            result_data.update({
                "probe_response": float(f1_net),
                "probe_both": float(f1_both),
                "probe_self": float(f1_self),
                "regime": "SYNTHETIC",
            })
        else:
            f_total_N = f1_net * MEEP_FORCE_TO_SI
            result_data.update({
                "force_total_meep": float(f1_net),
                "force_total_fN": float(f_total_N * 1e15),
                "pressure_Pa": float((f1_net / A_rotor) * MEEP_TO_PA),
                "regime": (
                    "REPULSIVE" if f1_net > 0 else "ATTRACTIVE" if f1_net < 0 else "ZERO"
                ),
            })

        os.makedirs("results_fractal_rotary_clutch", exist_ok=True)
        suffix = f"_micro_probe_steps_{args.max_steps}" if micro_probe else ""
        out_dest = (
            f"results_fractal_rotary_clutch/task_{args.task_id:03d}_"
            f"N_{args.N_fractal}_th_{int(args.theta)}deg{suffix}.json"
        )
        with open(out_dest, "w") as f:
            json.dump(result_data, f, indent=4, allow_nan=False)
        _log_result(result_data)

        print("\n" + "=" * 85)
        print("MICRO-PROBE COMPLETE" if micro_probe else "DUAL-FRACTAL CASIMIR CLUTCH SIMULATION COMPLETE")
        if micro_probe:
            print(f"Synthetic probe response: {f1_net:+.6e} (not a physical force)")
        else:
            print(f"Total Fractal Rotor Force (MEEP): {f1_net:+.6e}")
            print(f"Total Fractal Rotor Force (fN): {result_data['force_total_fN']:+.4f}")
            print(f"Rotor Normal Pressure: {result_data['pressure_Pa']:+.4e} Pa")
        print(f"Results saved to: {out_dest}")
        print("=" * 85 + "\n", flush=True)
    elif is_g0:
        _log_result({
            **_result_metadata(),
            "task_id": args.task_id,
            "config": args.config,
            "force_both": float(f1_both),
            "force_self": float(f1_self),
        })


if __name__ == "__main__":
    main()
