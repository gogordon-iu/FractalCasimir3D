#!/usr/bin/env python3
"""
Geometric Vacuum Casimir Repulsion Solver (Levin-Johnson Architecture)
-------------------------------------------------------------------
Simulates a metallic needle above an aperture in a metallic membrane
in vacuum. The net force is F_both - F_self.

Physics Reference:
Levin, McCauley, Rodriguez, Reid, Johnson, Phys. Rev. Lett. 105, 090403 (2010).

--max-steps runs a deterministic, nonphysical micro-probe without Meep.
Micro-probe results are explicitly identified and never enter simulation caches.
"""

import os
import sys
import json
import time
import ctypes
import argparse
import inspect
import math
import numbers
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


MEEP_TO_PA = 0.031615
MEEP_FORCE_TO_SI = 3.1615e-14
MODEL_NAME = "Levin_Johnson_geometric_repulsion"
DATASET_NAME = "geometric_repulsion_vacuum"


class SimulationPaused(RuntimeError):
    """Raised after checkpointing when the walltime budget is exhausted."""


def get_src_index(n):
    if isinstance(n, bool) or not isinstance(n, numbers.Integral) or n < 0:
        raise ValueError("Source index must be a nonnegative integer.")
    r = math.isqrt(8 * int(n) + 1)
    r = (r - 1) // 2
    c = n - r * (r + 1) // 2
    return r - c, c


def _positive_finite(name, value, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a finite real number.")
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {qualifier}.")


def _validate_parameters(
    W_aperture, t_plate, H_needle, w_needle, z_tip, resolution,
    n_max, config, T_run, dpml, buffer, L_plate, max_walltime_hours,
    max_steps
):
    for name, value in (
        ("W_aperture", W_aperture),
        ("t_plate", t_plate),
        ("H_needle", H_needle),
        ("w_needle", w_needle),
        ("z_tip", z_tip),
        ("resolution", resolution),
        ("T_run", T_run),
        ("dpml", dpml),
        ("L_plate", L_plate),
    ):
        _positive_finite(name, value)
    _positive_finite("buffer", buffer, allow_zero=True)
    if isinstance(n_max, bool) or not isinstance(n_max, numbers.Integral) or n_max <= 0:
        raise ValueError("n_max must be a positive integer.")
    if config not in ("both", "self", "all"):
        raise ValueError("config must be 'both', 'self', or 'all'.")
    if w_needle >= W_aperture or W_aperture >= L_plate:
        raise ValueError("Geometry requires w_needle < W_aperture < L_plate.")
    if max_walltime_hours is not None:
        if (
            isinstance(max_walltime_hours, bool)
            or not isinstance(max_walltime_hours, numbers.Real)
            or not math.isfinite(max_walltime_hours)
        ):
            raise ValueError("max_walltime_hours must be finite or None.")
    if max_steps is not None and (
        isinstance(max_steps, bool)
        or not isinstance(max_steps, numbers.Integral)
        or max_steps < 0
    ):
        raise ValueError("max_steps must be a nonnegative integer or None.")


def _atomic_json(path, data):
    tmp_path = f"{path}.tmp_{os.getpid()}"
    try:
        with open(tmp_path, "w") as handle:
            json.dump(data, handle, indent=4, allow_nan=False)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _finite_force(value):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError("Force must be a finite real number.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Force is not finite.")
    return result


def _invoke_metrics_callable(function, context, fallback):
    """Accommodate common metrics_logger interfaces without positional guessing."""
    signature = inspect.signature(function)
    args = []
    kwargs = {}
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if parameter.name in context:
            value = context[parameter.name]
        elif parameter.default is not inspect.Parameter.empty:
            continue
        elif fallback is not None:
            value = fallback
            fallback = None
        else:
            raise TypeError(f"Unsupported metrics parameter: {parameter.name}")
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[parameter.name] = value
    return function(*args, **kwargs)


def _log_metrics(result_data):
    if metrics_logger is None:
        print("Warning: utils.metrics_logger is unavailable; metrics were not logged.", flush=True)
        return

    context = {
        "metrics": result_data,
        "data": result_data,
        "record": result_data,
        "result": result_data,
        "results": result_data,
        "model": result_data["model"],
        "model_name": result_data["model"],
        "dataset": result_data["dataset"],
        "dataset_name": result_data["dataset"],
        "task_id": result_data["task_id"],
        "run_name": result_data["model"],
        "experiment_name": result_data["model"],
        "script_name": "run_geometric_repulsion_meep",
        "output_dir": "results_geometric_repulsion",
        "log_dir": "results_geometric_repulsion",
        "step": result_data.get("steps_executed", 0),
        "status": result_data["status"],
        "executed_at": result_data["executed_at"],
    }
    try:
        log_function = getattr(metrics_logger, "log_metrics", None)
        if callable(log_function):
            _invoke_metrics_callable(log_function, context, result_data)
            return

        logger_class = getattr(metrics_logger, "MetricsLogger", None)
        if not callable(logger_class):
            raise TypeError("No supported metrics_logger entry point.")
        logger = _invoke_metrics_callable(logger_class, context, MODEL_NAME)
        for method_name in ("log_metrics", "log", "record"):
            method = getattr(logger, method_name, None)
            if callable(method):
                _invoke_metrics_callable(method, context, result_data)
                break
        else:
            raise TypeError("MetricsLogger has no supported logging method.")
        flush = getattr(logger, "flush", None)
        if callable(flush):
            flush()
    except Exception as error:
        print(f"Warning: Failed to log metrics: {error}", flush=True)


def _run_micro_probe(max_steps, config):
    """Exercise the source basis and subtraction deterministically, not physics."""
    # Keep the probe fast even if a large maximum is supplied.
    steps = min(int(max_steps), 256)
    both_terms = []
    self_terms = []
    for step in range(steps):
        m1, m2 = get_src_index(step % 16)
        basis = math.cos(m1 * math.pi / 4.0) * math.cos(m2 * math.pi / 4.0)
        weight = basis * basis / (step + 1.0)
        self_terms.append(weight)
        both_terms.append(weight * 1.01)
    f_both = math.fsum(both_terms)
    f_self = math.fsum(self_terms)
    if config == "both":
        return f_both, 0.0, 0.0
    if config == "self":
        return 0.0, f_self, 0.0
    return f_both, f_self, f_both - f_self


def run_geometric_repulsion_simulation(
    W_aperture=0.35,
    t_plate=0.025,
    H_needle=0.25,
    w_needle=0.04,
    z_tip=0.03,
    material="Gold",
    resolution=80,
    n_max=1,
    config="all",
    T_run=12.0,
    dpml=0.20,
    buffer=0.15,
    L_plate=1.0,
    chk_tag="repulsion",
    max_walltime_hours=3.5,
    no_cache=False,
    max_steps=None,
):
    """
    Return (F_both, F_self, F_net) only after the requested work completes.

    Walltime pauses raise SimulationPaused, preserving incremental checkpoints
    without returning partial sums as completed results. Passing max_steps runs
    a deterministic, nonphysical micro-probe instead of an FDTD simulation.
    """
    _validate_parameters(
        W_aperture, t_plate, H_needle, w_needle, z_tip, resolution,
        n_max, config, T_run, dpml, buffer, L_plate, max_walltime_hours,
        max_steps,
    )
    if max_steps is not None:
        return _run_micro_probe(max_steps, config)
    if mp is None or get_casimir_material is None:
        raise RuntimeError("Meep module not found. Run in the BigRed 200 meep environment.")

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = global_rank == 0
    os.makedirs(".tmp", exist_ok=True)
    os.makedirs("results_geometric_repulsion", exist_ok=True)

    z_needle_center = z_tip + H_needle / 2.0
    dx = 1.0 / resolution
    delta_xy = max(0.025, 2.0 * dx)
    delta_z = max(0.025, 2.0 * dx)

    sx_box = w_needle + 2.0 * delta_xy
    sy_box = sx_box
    z_bot = 0.5 * z_tip
    z_top = z_tip + H_needle + delta_z
    center_z_box = 0.5 * (z_bot + z_top)
    sz_box = z_top - z_bot

    sx = L_plate + 2.0 * (dpml + buffer)
    sy = sx
    z_max = max(z_top, t_plate + delta_z) + buffer + dpml
    sz = 2.0 * z_max
    if sx_box >= sx - 2.0 * dpml:
        raise ValueError("Stress box must fit inside the non-PML cell.")
    cell_size = mp.Vector3(sx, sy, sz)

    d_eff = max(0.04, min(z_tip, (W_aperture - w_needle) / 2.0))
    Sigma = 0.5 / d_eff

    sides_info = [
        {
            "center": mp.Vector3(-sx_box / 2.0, 0.0, center_z_box),
            "size": mp.Vector3(0.0, sy_box, sz_box),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(sx_box / 2.0, 0.0, center_z_box),
            "size": mp.Vector3(0.0, sy_box, sz_box),
            "orientation": 1.0,
        },
        {
            "center": mp.Vector3(0.0, -sy_box / 2.0, center_z_box),
            "size": mp.Vector3(sx_box, 0.0, sz_box),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(0.0, sy_box / 2.0, center_z_box),
            "size": mp.Vector3(sx_box, 0.0, sz_box),
            "orientation": 1.0,
        },
        {
            "center": mp.Vector3(0.0, 0.0, z_bot),
            "size": mp.Vector3(sx_box, sy_box, 0.0),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(0.0, 0.0, z_top),
            "size": mp.Vector3(sx_box, sy_box, 0.0),
            "orientation": 1.0,
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
    start_time = time.monotonic()
    max_walltime_sec = (
        max_walltime_hours * 3600.0
        if max_walltime_hours is not None and max_walltime_hours > 0
        else None
    )

    # Invalidate pre-fix caches and caches from different simulation parameters.
    cache_parameters = {
        "solver_version": 2,
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

    def run_one_config(cfg_name):
        chk_file = f".tmp/chk_{chk_tag}_{cfg_name}.json"
        moments_chk = f".tmp/chk_moments_{chk_tag}_{cfg_name}.json"

        if not no_cache and os.path.exists(chk_file):
            try:
                with open(chk_file, "r") as f_chk:
                    data = json.load(f_chk)
                if (
                    not isinstance(data, dict)
                    or data.get("parameters") != cache_parameters
                    or data.get("status") != "completed"
                ):
                    raise ValueError("Checkpoint is stale or incomplete.")
                force = _finite_force(data["force"])
                if is_g0:
                    print(f"[{cfg_name.upper()}] Loaded cached force: {force:.6e} from {chk_file}")
                return force
            except (OSError, TypeError, json.JSONDecodeError, KeyError, ValueError) as err:
                if is_g0:
                    print(f"[{cfg_name.upper()}] Notice: Stale/corrupt checkpoint {chk_file} ({err}). Recomputing.")

        completed_moments = {}
        if not no_cache and os.path.exists(moments_chk):
            try:
                with open(moments_chk, "r") as f_mom:
                    chk_data = json.load(f_mom)
                if not isinstance(chk_data, dict) or chk_data.get("parameters") != cache_parameters:
                    raise ValueError("Moment checkpoint parameters do not match.")
                raw_moments = chk_data["completed_moments"]
                if not isinstance(raw_moments, dict):
                    raise ValueError("Invalid moment checkpoint.")
                for key, value in raw_moments.items():
                    index = int(key)
                    if index < 0 or index >= num_tasks or index in completed_moments:
                        raise ValueError("Invalid or duplicate moment index.")
                    completed_moments[index] = _finite_force(value)
                if is_g0:
                    print(f"[{cfg_name.upper()}] Loaded {len(completed_moments)} cached moments from {moments_chk}")
            except (OSError, TypeError, json.JSONDecodeError, KeyError, ValueError) as err:
                if is_g0:
                    print(f"[{cfg_name.upper()}] Notice: Stale/corrupt moments file {moments_chk} ({err}). Starting fresh.")
                completed_moments = {}

        total_force = 0.0

        for task_idx in range(num_tasks):
            if task_idx in completed_moments:
                f_cached = completed_moments[task_idx]
                total_force += f_cached
                if is_g0:
                    print(
                        f"  [{cfg_name.upper()}][Rank 0] Skipped moment "
                        f"{task_idx + 1}/{num_tasks} [CACHED]: force_integral={f_cached:+.6e}",
                        flush=True,
                    )
                continue

            if max_walltime_sec is not None:
                elapsed_sec = time.monotonic() - start_time
                if elapsed_sec >= max_walltime_sec:
                    if is_g0:
                        print(
                            f"\n[WALLTIME GUARD] Elapsed {elapsed_sec / 3600:.2f}h "
                            f">= limit ({max_walltime_hours:.2f}h). Pausing cleanly.",
                            flush=True,
                        )
                    raise SimulationPaused(
                        f"{cfg_name}: completed {len(completed_moments)}/{num_tasks} moments."
                    )

            p = task_idx // (n_max * 6)
            n = task_idx % (n_max * 6)
            curr_pol = pol_list[p]
            ft_type = mp.E_stuff if curr_pol in [mp.Ex, mp.Ey, mp.Ez] else mp.H_stuff

            mat_obj = get_casimir_material(
                material, Sigma, ft_type, theta=0.0, eps_bg=1.0
            )
            if ft_type == mp.E_stuff:
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
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, -t_plate / 2.0),
                    size=mp.Vector3(W_aperture, W_aperture, t_plate + 0.001),
                    material=bg_material,
                ))

            geometry.append(mp.Block(
                center=mp.Vector3(0.0, 0.0, z_needle_center),
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
            if T_steps < 1:
                sim.reset_meep()
                raise ValueError("T_run must cover at least one FDTD time step.")

            gt = mp.make_casimir_gfunc(T_run, dt, Sigma, ft_type)
            addr = int(gt)
            if not addr:
                sim.reset_meep()
                raise RuntimeError("Meep returned a null Casimir kernel pointer.")
            double_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))
            data = np.ctypeslib.as_array(double_ptr, shape=(T_steps * 2,))
            gt_arr = data[0::2] + 1j * data[1::2]
            if not np.all(np.isfinite(gt_arr)):
                sim.reset_meep()
                raise FloatingPointError("Casimir time kernel contains nonfinite values.")

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

            def make_amp_func(mx_val, my_val, mz_val, size_vec):
                sx_v, sy_v, sz_v = size_vec.x, size_vec.y, size_vec.z
                Nx = (2.0 / sx_v if mx_val > 0 else 1.0 / sx_v) if sx_v > 1e-15 else 1.0
                Ny = (2.0 / sy_v if my_val > 0 else 1.0 / sy_v) if sy_v > 1e-15 else 1.0
                Nz = (2.0 / sz_v if mz_val > 0 else 1.0 / sz_v) if sz_v > 1e-15 else 1.0
                factor = np.sqrt(Nx * Ny * Nz)

                def amp_func(position):
                    x = position.x + 0.5 * sx_v
                    y = position.y + 0.5 * sy_v
                    z = position.z + 0.5 * sz_v
                    kx = mx_val * np.pi / sx_v if sx_v > 1e-15 else 0.0
                    ky = my_val * np.pi / sy_v if sy_v > 1e-15 else 0.0
                    kz = mz_val * np.pi / sz_v if sz_v > 1e-15 else 0.0
                    return factor * np.cos(kx * x) * np.cos(ky * y) * np.cos(kz * z)

                return amp_func

            src_vol = mp.Volume(center=side_center, size=side_size, dims=3)
            amp_fn = make_amp_func(mx, my, mz, side_size)

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
                        ft_type, src_vol.swigobj,
                    )
                    force_integral += np.imag(
                        gt_arr[step] * dt * side_orientation * f_temp
                    )
                force_integral = _finite_force(force_integral)
            finally:
                sim.reset_meep()

            total_force += force_integral
            completed_moments[task_idx] = force_integral

            if is_g0:
                try:
                    _atomic_json(moments_chk, {
                        "parameters": cache_parameters,
                        "completed_moments": {
                            str(k): v for k, v in completed_moments.items()
                        },
                    })
                except OSError as write_err:
                    print(f"Warning: Failed writing incremental checkpoint: {write_err}", flush=True)
                print(
                    f"  [{cfg_name.upper()}][Rank 0] Done moment "
                    f"{task_idx + 1}/{num_tasks}: force_integral={force_integral:+.6e}",
                    flush=True,
                )

        total_force = _finite_force(total_force)
        if len(completed_moments) != num_tasks:
            raise SimulationPaused(f"{cfg_name}: incomplete moment set.")

        if is_g0:
            try:
                _atomic_json(chk_file, {
                    "parameters": cache_parameters,
                    "force": total_force,
                    "model": MODEL_NAME,
                    "dataset": DATASET_NAME,
                    "status": "completed",
                    "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
                print(f"[{cfg_name.upper()}] Complete. Total force: {total_force:+.6e}")
            except OSError as save_err:
                print(f"Warning: Failed writing config checkpoint {chk_file}: {save_err}", flush=True)

        return total_force

    if config == "both":
        return run_one_config("both"), 0.0, 0.0
    if config == "self":
        return 0.0, run_one_config("self"), 0.0

    f_both = run_one_config("both")
    f_self = run_one_config("self")
    return f_both, f_self, _finite_force(f_both - f_self)


def main():
    parser = argparse.ArgumentParser(
        description="Geometric Vacuum Casimir Repulsion (Levin-Johnson Architecture)"
    )
    parser.add_argument("--task-id", type=int, default=1, help="Task ID")
    parser.add_argument("--W-aperture", type=float, default=0.35, help="Aperture diameter/width (um)")
    parser.add_argument("--t-plate", type=float, default=0.025, help="Membrane thickness (um)")
    parser.add_argument("--H-needle", type=float, default=0.25, help="Needle height (um)")
    parser.add_argument("--w-needle", type=float, default=0.04, help="Needle base width (um)")
    parser.add_argument("--z-tip", type=float, default=0.03, help="Tip clearance above aperture plane (um)")
    parser.add_argument("--material", type=str, default="Gold", help="Plate and needle material")
    parser.add_argument("--res", type=int, default=80, help="Grid resolution (pixels/um)")
    parser.add_argument("--nmax", type=int, default=1, help="Multipole cutoff")
    parser.add_argument("--config", type=str, default="all", choices=["both", "self", "all"])
    parser.add_argument("--T-run", type=float, default=12.0, help="FDTD run time")
    parser.add_argument("--max-walltime-hours", type=float, default=3.5, help="Slurm walltime limit buffer")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cached checkpoints")
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Run a deterministic, nonphysical micro-probe (at most 256 steps), without Meep.",
    )
    args = parser.parse_args()

    try:
        _validate_parameters(
            args.W_aperture, args.t_plate, args.H_needle, args.w_needle,
            args.z_tip, args.res, args.nmax, args.config, args.T_run,
            0.20, 0.15, 1.0, args.max_walltime_hours, args.max_steps,
        )
    except ValueError as error:
        parser.error(str(error))

    chk_tag = (
        f"geom_repulse_W_{args.W_aperture:.3f}_ztip_{args.z_tip:.4f}"
        f"_res_{args.res}_mat_{args.material}"
    )
    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = global_rank == 0
    is_probe = args.max_steps is not None

    if is_g0:
        print("=" * 80)
        print(
            "DETERMINISTIC MICRO-PROBE (NONPHYSICAL; NO MEEP)"
            if is_probe else
            "GEOMETRIC VACUUM CASIMIR REPULSION SOLVER (Levin-Johnson Mechanism)"
        )
        print(f"Task ID: {args.task_id}")
        print(f"Aperture Width W: {args.W_aperture * 1e3:.1f} nm, Plate Thickness t: {args.t_plate * 1e3:.1f} nm")
        print(f"Needle Height H: {args.H_needle * 1e3:.1f} nm, Width w: {args.w_needle * 1e3:.1f} nm")
        print(f"Tip Clearance z_tip: {args.z_tip * 1e3:.1f} nm (W/4 threshold = {args.W_aperture * 250:.1f} nm)")
        print(f"Material: {args.material}, Resolution: {args.res} (dx = {1000 / args.res:.2f} nm)")
        print("=" * 80, flush=True)

    try:
        f_both, f_self, f_net = run_geometric_repulsion_simulation(
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
    except SimulationPaused as error:
        if is_g0:
            print(
                f"SIMULATION PAUSED: {error} No final result was written. "
                "Rerun with the same parameters to resume.",
                flush=True,
            )
        return

    if not is_g0:
        return

    executed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result_data = {
        "task_id": args.task_id,
        "architecture": MODEL_NAME,
        "model": MODEL_NAME,
        "dataset": "geometric_repulsion_micro_probe" if is_probe else DATASET_NAME,
        "status": "completed",
        "executed_at": executed_at,
        "execution_mode": "micro_probe" if is_probe else "meep",
        "config": args.config,
        "W_aperture_nm": args.W_aperture * 1e3,
        "t_plate_nm": args.t_plate * 1e3,
        "H_needle_nm": args.H_needle * 1e3,
        "w_needle_nm": args.w_needle * 1e3,
        "z_tip_nm": args.z_tip * 1e3,
        "W_over_4_nm": (args.W_aperture / 4.0) * 1e3,
        "material": args.material,
        "resolution": args.res,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if is_probe:
        result_data.update({
            "max_steps": args.max_steps,
            "steps_executed": min(args.max_steps, 256),
            "probe_both": float(f_both),
            "probe_self": float(f_self),
            "probe_net": float(f_net),
            "regime": "NOT_PHYSICAL",
        })
    else:
        result_data.update({
            "force_both_meep": float(f_both),
            "force_self_meep": float(f_self),
        })
        if args.config == "all":
            f_net_N = f_net * MEEP_FORCE_TO_SI
            f_net_fN = f_net_N * 1e15
            f_net_nN = f_net_N * 1e9
            A_needle_meep = args.w_needle ** 2
            if not math.isfinite(A_needle_meep) or A_needle_meep <= 0:
                raise ValueError("Needle cross-sectional area is not finite and positive.")
            pressure_Pa = _finite_force((f_net / A_needle_meep) * MEEP_TO_PA)
            result_data.update({
                "force_net_meep": float(f_net),
                "force_net_fN": _finite_force(f_net_fN),
                "force_net_nN": _finite_force(f_net_nN),
                "pressure_Pa": pressure_Pa,
                "regime": (
                    "REPULSIVE" if f_net > 0 else
                    "ATTRACTIVE" if f_net < 0 else "ZERO"
                ),
            })

    os.makedirs("results_geometric_repulsion", exist_ok=True)
    suffix = "_micro_probe" if is_probe else (
        f"_{args.config}" if args.config != "all" else ""
    )
    out_dest = (
        f"results_geometric_repulsion/task_{args.task_id:03d}"
        f"_ztip_{int(args.z_tip * 1e3)}nm{suffix}.json"
    )
    _atomic_json(out_dest, result_data)
    _log_metrics(result_data)

    print("\n" + "=" * 80)
    if is_probe:
        print("MICRO-PROBE COMPLETE: NOT A CASIMIR FORCE EVALUATION")
        print(f"Steps executed: {result_data['steps_executed']}")
        print(f"Probe net: {f_net:+.6e}")
    else:
        print("SIMULATION COMPLETE")
        print(f"Force Both (MEEP):  {f_both:+.6e}")
        print(f"Force Self (MEEP):  {f_self:+.6e}")
        if args.config == "all":
            print(f"Net Force (MEEP):   {f_net:+.6e}")
            print(f"Net Force (fN):     {f_net_fN:+.4f} fN  -->  {result_data['regime']}")
            print(f"Pressure:           {pressure_Pa:+.4e} Pa")
    print(f"Results saved to:   {out_dest}")
    print("=" * 80 + "\n", flush=True)


if __name__ == "__main__":
    main()
