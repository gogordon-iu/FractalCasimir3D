"""
Numerical Grid Convergence & Edge Rounding Verification Protocol (Nature Challenge 1)
-------------------------------------------------------------------------------------
Runs rounded-geometry Casimir simulations and supports a deterministic, non-physical
numerical micro-probe via --max-steps. Micro-probe results are not Casimir pressures.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
import sys

import numpy as np

# Ensure project execution path is available.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_MEEP_IMPORT_ERROR = None
try:
    import meep as mp
    from execution.edge_rounding_geometry import generate_rounded_pyramid_corrugations
    from execution.materials_database_dispersive import get_meep_dispersive_medium
    from execution.run_meep_simulation import get_src_index, get_effective_area
except ImportError as exc:
    mp = None
    _MEEP_IMPORT_ERROR = exc


def _finite_number(name, value, positive=False, nonnegative=False):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not np.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    if positive and number <= 0:
        raise ValueError(f"{name} must be positive.")
    if nonnegative and number < 0:
        raise ValueError(f"{name} must be nonnegative.")
    return number


def _positive_integer(name, value):
    number = _finite_number(name, value, positive=True)
    if not number.is_integer():
        raise ValueError(f"{name} must be a positive integer.")
    return int(number)


def _execution_metadata(model):
    return {
        "model": model,
        "dataset": "rounded_grid_convergence",
        "status": "completed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def _parallel_context():
    """Return the actual MPI communicator, not a file-based rank approximation."""
    try:
        from mpi4py import MPI
    except ImportError as exc:
        declared_size = int(os.environ.get("SLURM_NTASKS", "1"))
        meep_size = mp.count_processors() if mp is not None else 1
        if declared_size > 1 or meep_size > 1:
            raise RuntimeError(
                "mpi4py is required for deterministic multi-rank reduction."
            ) from exc
        return None, 0, 1

    comm = MPI.COMM_WORLD
    size = comm.Get_size()
    if size == 1 and int(os.environ.get("SLURM_NTASKS", "1")) > 1:
        raise RuntimeError(
            "Multiple SLURM tasks were requested, but MPI.COMM_WORLD has one rank. "
            "Launch with a working MPI configuration."
        )
    return comm, comm.Get_rank(), size


def _log_metrics(result):
    """Use the project logger, with an explicit fallback if it is unavailable."""
    try:
        from utils.metrics_logger import log_metrics
    except ImportError as exc:
        logging.warning("utils.metrics_logger unavailable: %s", exc)
        logging.info("metrics=%s", json.dumps(result, allow_nan=False))
        return
    log_metrics(result)


def _run_micro_probe(max_steps, parameters):
    """Bounded midpoint-quadrature check; never fabricate physical pressures."""
    max_steps = _positive_integer("max_steps", max_steps)
    # Chunking keeps memory bounded even for a large explicitly requested budget.
    integral = 0.0
    for start in range(0, max_steps, 65536):
        stop = min(start + 65536, max_steps)
        x = (np.arange(start, stop, dtype=float) + 0.5) / max_steps
        integral += float(np.sum(np.exp(-x))) / max_steps
    exact = float(-np.expm1(-1.0))
    return {
        **parameters,
        "max_steps": max_steps,
        "steps_executed": max_steps,
        "probe_integral": integral,
        "probe_absolute_error": abs(integral - exact),
        "is_physical_simulation": False,
        **_execution_metadata("rounded_convergence_micro_probe"),
    }


def run_rounded_convergence_simulation(
    d,
    alpha,
    theta,
    resolution,
    r_tip_nm=5.0,
    delta_s_nm=30.0,
    L=2.0,
    N_top=3,
    N_bot=3,
    eps_bg=2.1,
    material="Phosphorene_tuned",
    n_max=2,
    T_run=30.0,
    config="all",
    max_steps=None,
):
    """
    Execute rounded-geometry FDTD, or a deterministic numerical micro-probe when
    max_steps is supplied. T_run is retained for interface compatibility; physical
    runs use the conductivity-dependent stability window.
    """
    d = _finite_number("d", d, positive=True)
    alpha = _finite_number("alpha", alpha)
    theta = _finite_number("theta", theta)
    resolution = _positive_integer("resolution", resolution)
    r_tip_nm = _finite_number("r_tip_nm", r_tip_nm, nonnegative=True)
    delta_s_nm = _finite_number("delta_s_nm", delta_s_nm, nonnegative=True)
    L = _finite_number("L", L, positive=True)
    N_top = _positive_integer("N_top", N_top)
    N_bot = _positive_integer("N_bot", N_bot)
    eps_bg = _finite_number("eps_bg", eps_bg, positive=True)
    n_max = _positive_integer("n_max", n_max)
    _finite_number("T_run", T_run, positive=True)
    if config not in ("all", "both", "self"):
        raise ValueError("config must be 'all', 'both', or 'self'.")

    parameters = {
        "d_um": d,
        "alpha_deg": alpha,
        "theta_deg": theta,
        "resolution": resolution,
        "r_tip_nm": r_tip_nm,
        "delta_s_nm": delta_s_nm,
        "L_um": L,
        "N_top": N_top,
        "N_bot": N_bot,
        "eps_bg": eps_bg,
        "material": material,
        "n_max": n_max,
        "config": config,
    }
    if max_steps is not None:
        return _run_micro_probe(max_steps, parameters)

    if mp is None:
        raise RuntimeError(
            "MEEP and the geometry/material helpers are required for physical "
            "Casimir simulations. Use --max-steps for a numerical micro-probe."
        ) from _MEEP_IMPORT_ERROR

    comm, global_rank, total_ranks = _parallel_context()
    if total_ranks > 1:
        if mp.count_processors() != total_ranks:
            raise RuntimeError(
                "MEEP and mpi4py must use the same MPI world for task allocation."
            )
        # Each moment is an independent simulation. Split MEEP's internal
        # communicator while retaining the world communicator for reductions.
        mp.divide_parallel_processes(total_ranks)

    r_tip_um = r_tip_nm * 1e-3
    delta_s_um = delta_s_nm * 1e-3
    t_top = 0.75 if alpha >= 60.0 else 0.50
    t_bottom = 0.75 if alpha >= 60.0 else 0.50
    dpml = 0.25
    buffer = 0.20

    theta_rad = np.radians(theta)
    C_env = abs(np.cos(theta_rad))
    S_env = abs(np.sin(theta_rad))
    L_rot = L * (C_env + S_env)
    sx = L_rot + 2.0 * (dpml + buffer)
    sy = L_rot + 2.0 * (dpml + buffer)
    sz = d + t_top + t_bottom + 2.0 * (dpml + buffer)
    cell_size = mp.Vector3(sx, sy, sz)

    Sigma = _finite_number("Sigma", 0.5 / d, positive=True)
    T_run = max(3.0, min(12.0, 20.0 / (2.0 * Sigma)))

    delta_s_xy = delta_s_um
    delta_s_z = min(delta_s_um, d / 4.0)
    if delta_s_xy >= buffer or delta_s_z >= buffer:
        raise ValueError("The stress integration box must remain outside the PML.")
    sx_box = L_rot + 2.0 * delta_s_xy
    sy_box = L_rot + 2.0 * delta_s_xy
    sz_box = t_top + 2.0 * delta_s_z
    center_z = d / 2.0 + t_top / 2.0

    sides_info = [
        {
            "center": mp.Vector3(-sx_box / 2.0, 0.0, center_z),
            "size": mp.Vector3(0.0, sy_box, sz_box),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(sx_box / 2.0, 0.0, center_z),
            "size": mp.Vector3(0.0, sy_box, sz_box),
            "orientation": 1.0,
        },
        {
            "center": mp.Vector3(0.0, -sy_box / 2.0, center_z),
            "size": mp.Vector3(sx_box, 0.0, sz_box),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(0.0, sy_box / 2.0, center_z),
            "size": mp.Vector3(sx_box, 0.0, sz_box),
            "orientation": 1.0,
        },
        {
            "center": mp.Vector3(0.0, 0.0, center_z - sz_box / 2.0),
            "size": mp.Vector3(sx_box, sy_box, 0.0),
            "orientation": -1.0,
        },
        {
            "center": mp.Vector3(0.0, 0.0, center_z + sz_box / 2.0),
            "size": mp.Vector3(sx_box, sy_box, 0.0),
            "orientation": 1.0,
        },
    ]

    pol_list = [mp.Ex, mp.Ey, mp.Ez, mp.Hx, mp.Hy, mp.Hz]
    component_direction = {
        mp.Ex: mp.X, mp.Ey: mp.Y, mp.Ez: mp.Z,
        mp.Hx: mp.X, mp.Hy: mp.Y, mp.Hz: mp.Z,
    }

    # Memory-safe allocation for independent single-rank simulations.
    if resolution <= 40:
        max_active_ranks = 72
    elif resolution <= 60:
        max_active_ranks = 48
    elif resolution <= 80:
        max_active_ranks = 24
    else:
        max_active_ranks = 16
    active_ranks = min(total_ranks, max_active_ranks, 36 * n_max)

    def simulate_cfg(current_cfg):
        num_moments = 36 * n_max
        my_moments = (
            list(range(global_rank, num_moments, active_ranks))
            if global_rank < active_ranks else []
        )
        local_f = 0.0
        local_error = None
        sim = None
        try:
            for cur_i, task_idx in enumerate(my_moments):
                p = task_idx // (n_max * 6)
                n = task_idx % (n_max * 6)
                curr_pol = pol_list[p]
                ft_type = (
                    mp.E_stuff
                    if curr_pol in (mp.Ex, mp.Ey, mp.Ez)
                    else mp.H_stuff
                )

                mat_bot = get_meep_dispersive_medium(
                    material, Sigma, ft_type, theta_deg=0.0
                )
                mat_top = get_meep_dispersive_medium(
                    material, Sigma, ft_type, theta_deg=theta
                )
                if ft_type == mp.E_stuff:
                    bg_mat = mp.Medium(epsilon=eps_bg, D_conductivity=Sigma)
                else:
                    bg_mat = mp.Medium(epsilon=eps_bg, B_conductivity=Sigma)

                geometry = []
                if current_cfg == "both":
                    geometry.append(mp.Block(
                        center=mp.Vector3(0.0, 0.0, -d / 2.0 - t_bottom / 2.0),
                        size=mp.Vector3(L, L, t_bottom),
                        material=mat_bot,
                    ))
                    geometry.extend(generate_rounded_pyramid_corrugations(
                        N_bot, L, 0.0, 0.0, -d / 2.0,
                        is_top_plate=False, angle=alpha, r_tip=r_tip_um,
                        theta=0.0, max_depth=0.85 * t_bottom, material=bg_mat,
                    ))

                if current_cfg != "vacuum":
                    C, S = np.cos(theta_rad), np.sin(theta_rad)
                    geometry.append(mp.Block(
                        center=mp.Vector3(0.0, 0.0, d / 2.0 + t_top / 2.0),
                        size=mp.Vector3(L, L, t_top),
                        e1=mp.Vector3(C, S, 0.0),
                        e2=mp.Vector3(-S, C, 0.0),
                        e3=mp.Vector3(0.0, 0.0, 1.0),
                        material=mat_top,
                    ))
                    geometry.extend(generate_rounded_pyramid_corrugations(
                        N_top, L, 0.0, 0.0, d / 2.0,
                        is_top_plate=True, angle=alpha, r_tip=r_tip_um,
                        theta=theta, max_depth=0.85 * t_top, material=bg_mat,
                    ))

                sim = mp.Simulation(
                    cell_size=cell_size,
                    geometry=geometry,
                    resolution=resolution,
                    boundary_layers=[mp.PML(dpml)],
                    default_material=bg_mat,
                    Courant=0.3,
                    eps_averaging=False,
                    force_complex_fields=True,
                )
                sim.init_sim()
                dt = sim.Courant / resolution
                T_steps = int(T_run / dt)
                if T_steps < 1:
                    raise ValueError("The simulation must execute at least one step.")

                import ctypes

                gt = mp.make_casimir_gfunc(T_run, dt, Sigma, ft_type)
                addr = int(gt)
                if not addr:
                    raise RuntimeError("make_casimir_gfunc returned a null pointer.")
                double_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))
                data = np.ctypeslib.as_array(double_ptr, shape=(T_steps * 2,))
                gt_arr = data[0::2] + 1j * data[1::2]
                if not np.all(np.isfinite(gt_arr)):
                    raise FloatingPointError("The Casimir kernel contains nonfinite values.")

                s = n % 6
                nr = n // 6
                m1, m2 = get_src_index(nr)
                side = sides_info[s]
                if s in (0, 1):
                    mx, my, mz = 0, m1, m2
                elif s in (2, 3):
                    mx, my, mz = m1, 0, m2
                else:
                    mx, my, mz = m1, m2, 0

                def make_amp_func(mx_val, my_val, mz_val, size_vec):
                    sx_v, sy_v, sz_v = size_vec.x, size_vec.y, size_vec.z
                    Nx = ((2.0 if mx_val > 0 else 1.0) / sx_v
                          if sx_v > 1e-15 else 1.0)
                    Ny = ((2.0 if my_val > 0 else 1.0) / sy_v
                          if sy_v > 1e-15 else 1.0)
                    Nz = ((2.0 if mz_val > 0 else 1.0) / sz_v
                          if sz_v > 1e-15 else 1.0)
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

                src_vol = mp.Volume(center=side["center"], size=side["size"], dims=3)
                sim.change_sources([
                    mp.Source(
                        src=mp.CustomSource(
                            src_func=lambda t: 1.0 / dt,
                            start_time=-0.25 * dt,
                            end_time=0.75 * dt,
                        ),
                        component=curr_pol,
                        center=side["center"],
                        size=side["size"],
                        amp_func=make_amp_func(mx, my, mz, side["size"]),
                    )
                ])
                sim.reset_meep()
                sim.init_sim()

                f_integral = 0.0
                for step in range(T_steps):
                    sim.fields.step()
                    f_temp = sim.fields.casimir_stress_dct_integral(
                        mp.Z, component_direction[curr_pol],
                        float(mx), float(my), float(mz),
                        ft_type, src_vol.swigobj,
                    )
                    contribution = np.imag(
                        gt_arr[step] * dt * side["orientation"] * f_temp
                    )
                    if not np.isfinite(contribution):
                        raise FloatingPointError(
                            f"Nonfinite stress contribution at task {task_idx}, step {step}."
                        )
                    f_integral += float(contribution)

                local_f += f_integral
                if not np.isfinite(local_f):
                    raise FloatingPointError("Accumulated force is nonfinite.")
                if global_rank == 0 or len(my_moments) > 1:
                    print(
                        f"  [{current_cfg.upper()}][Rank {global_rank}] "
                        f"Done moment {cur_i + 1}/{len(my_moments)} "
                        f"(task {task_idx}): force_integral={f_integral:+.6e}",
                        flush=True,
                    )
                sim.reset_meep()
                sim = None
        except Exception as exc:
            # Propagate Python failures collectively so no rank waits for a file
            # or silently contributes an incomplete force.
            local_error = f"Rank {global_rank}: {type(exc).__name__}: {exc}"
        finally:
            if sim is not None:
                try:
                    sim.reset_meep()
                except Exception as exc:
                    cleanup_error = f"Rank {global_rank}: cleanup failed: {exc}"
                    local_error = (
                        f"{local_error}; {cleanup_error}" if local_error else cleanup_error
                    )

        if comm is not None and total_ranks > 1:
            errors = [error for error in comm.allgather(local_error) if error]
            if errors:
                raise RuntimeError("Simulation failed: " + "; ".join(errors))
            # Ordered summation is deterministic for a given task allocation.
            total_f = float(sum(comm.allgather(float(local_f))))
        else:
            if local_error:
                raise RuntimeError(local_error)
            total_f = float(local_f)
        if not np.isfinite(total_f):
            raise FloatingPointError("Reduced force is nonfinite.")
        return total_f

    f_both = simulate_cfg("both") if config in ("all", "both") else 0.0
    f_self = simulate_cfg("self") if config in ("all", "self") else 0.0

    A_eff = _finite_number(
        "effective area", get_effective_area(N_top, L), positive=True
    )
    f_net = f_both - f_self
    MEEP_TO_PA = 0.031615  # hbar*c / a^4 with a = 1 um.
    pressure_Pa = (f_net / A_eff) * MEEP_TO_PA
    if not np.isfinite(pressure_Pa):
        raise FloatingPointError("Computed pressure is nonfinite.")

    return {
        **parameters,
        "T_run": T_run,
        "force_both": float(f_both),
        "force_self": float(f_self),
        "force_net": float(f_net),
        "pressure_Pa": float(pressure_Pa),
        "is_repulsive": bool(pressure_Pa > 0),
        "is_physical_simulation": True,
        **_execution_metadata("rounded_casimir_fdtd"),
    }


def richardson_extrapolation(resolutions, pressures):
    """Fit P(1/R) = P_inf + c1*(1/R) + c2*(1/R)^2."""
    try:
        R_arr = np.asarray(resolutions, dtype=float)
        P_arr = np.asarray(pressures, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Resolutions and pressures must be numeric arrays.") from exc
    if R_arr.ndim != 1 or P_arr.ndim != 1 or R_arr.shape != P_arr.shape:
        raise ValueError("Resolutions and pressures must be equal-length 1D arrays.")
    if R_arr.size < 3 or np.unique(R_arr).size < 3:
        raise ValueError("Quadratic extrapolation requires three distinct resolutions.")
    if not np.all(np.isfinite(R_arr)) or np.any(R_arr <= 0):
        raise ValueError("Resolutions must be finite and positive.")
    if not np.all(np.isfinite(P_arr)):
        raise ValueError("Pressures must be finite.")
    inv_R = 1.0 / R_arr
    if not np.all(np.isfinite(inv_R)):
        raise ValueError("Inverse resolutions must be finite.")
    poly = np.polyfit(inv_R, P_arr, deg=2)
    if not np.all(np.isfinite(poly)):
        raise FloatingPointError("Extrapolation produced nonfinite coefficients.")
    return float(poly[2]), poly


def main():
    parser = argparse.ArgumentParser(
        description="Run Edge Rounding and Grid Convergence Study."
    )
    parser.add_argument("--d", type=float, default=0.15, help="Separation in um.")
    parser.add_argument("--alpha", type=float, default=75.0, help="Pyramid angle in degrees.")
    parser.add_argument("--theta", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument("--res", type=int, default=40, help="FDTD resolution in pixels/um.")
    parser.add_argument("--r-tip", type=float, default=5.0, help="Tip rounding radius in nm.")
    parser.add_argument("--delta-s", type=float, default=30.0, help="Stress standoff in nm.")
    parser.add_argument("--nmax", type=int, default=2, help="Number of moments.")
    parser.add_argument("--config", default="all", choices=["both", "self", "all"])
    parser.add_argument("--outdir", default=".tmp")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Run a deterministic numerical micro-probe with this positive step budget; "
             "does not compute a physical Casimir pressure.",
    )
    args = parser.parse_args()
    if args.max_steps is not None and args.max_steps <= 0:
        parser.error("--max-steps must be a positive integer.")

    _, global_rank, _ = _parallel_context()
    result = run_rounded_convergence_simulation(
        d=args.d,
        alpha=args.alpha,
        theta=args.theta,
        resolution=args.res,
        r_tip_nm=args.r_tip,
        delta_s_nm=args.delta_s,
        n_max=args.nmax,
        config=args.config,
        max_steps=args.max_steps,
    )

    if global_rank == 0:
        os.makedirs(args.outdir, exist_ok=True)
        probe_suffix = (
            f"_probe_{args.max_steps}" if args.max_steps is not None else ""
        )
        out_file = os.path.join(
            args.outdir,
            f"conv_res_{args.res}_rtip_{args.r_tip:.1f}_ds_{args.delta_s:.1f}"
            f"_al_{args.alpha:.1f}_th_{args.theta:.1f}"
            f"_d_{args.d:.17g}_nmax_{args.nmax}_{args.config}{probe_suffix}.json",
        )
        # Recompute rather than trusting legacy caches without freshness metadata.
        # Atomic publication prevents readers from observing a partial JSON file.
        temp_file = f"{out_file}.{os.getpid()}.tmp"
        try:
            with open(temp_file, "w") as handle:
                json.dump(result, handle, indent=4, allow_nan=False)
            os.replace(temp_file, out_file)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        _log_metrics(result)
        if result["is_physical_simulation"]:
            detail = f"P={result['pressure_Pa']:+.4f} Pa"
        else:
            detail = (
                f"numerical micro-probe, steps={result['steps_executed']}, "
                f"error={result['probe_absolute_error']:.6e} (not a Casimir pressure)"
            )
        print(
            f"Convergence task complete: Res={args.res}, r_tip={args.r_tip} nm, "
            f"{detail} -> Saved to {out_file}",
            flush=True,
        )


if __name__ == "__main__":
    main()
