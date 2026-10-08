#!/usr/bin/env python3
"""
Concentric Cantor-Ring 3D FDTD Casimir Solver: "The One Ring to Rule Them All"
-------------------------------------------------------------------------------
Evaluates the full 3D Maxwell stress tensor for the Concentric Cantor-Ring
Rotary Casimir Clutch across prefractal generations N in {1, 2, 3},
non-fractal uniform periodic controls, and solid flat controls.

Physical & Computational Highlights:
1. Pure first-principles Maxwell stress tensor integration with imaginary-frequency
   Wick rotation (Sigma damping).
2. Complete free-space vacuum self-stress cancellation (F_net = F_both - F_self).
3. Exact invariant distance metric (<d> = 20.00 nm) applied dynamically.
4. Per-moment atomic checkpointing and multi-hour walltime guard with auto-resubmission flags.
5. Strict all_done guard before final result serialization.
"""

import os
import sys
import time
import math
import glob
import json
import argparse
import ctypes
import socket
import platform
import datetime
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import meep as mp

from execution.concentric_ring_geometry import (
    get_cantor_ring_elements,
    get_uniform_ring_elements,
    compute_concentric_aperture_area_fraction,
    compute_invariant_z_tip,
    generate_concentric_stator_geometry,
    generate_concentric_rotor_geometry
)

# Physical conversion constants (for length unit a = 1.0 um):
# hbar * c = 3.16152649e-26 J*m
# Force in N = F_meep * (hbar * c / a^2) = F_meep * 3.16152649e-14 N
# Force in fN = F_meep * 31.6152649 fN
MEEP_FORCE_TO_SI = 3.16152649e-14     # Newtons per MEEP force unit
MEEP_FORCE_TO_FN = 31.6152649         # FemtoNewtons per MEEP force unit
MEEP_TO_PA = 0.0316152649             # Pascals per (MEEP force / um^2)


def get_src_index(n):
    """Computes source spatial modal indices for DCT integration."""
    s = 0
    r = 0
    while s + r < n:
        r += 1
        s += r
    c = n - s
    return r - c, c


def get_casimir_material(mat_name, Sigma, ft, theta=0.0, eps_bg=1.0):
    """
    Constructs Wick-rotated dispersive material with conductivity Sigma.
    Applies Drude frequency rescaling to prevent numerical NaN/Inf divergence.
    """
    if mat_name == "PEC":
        return mp.metal

    cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}

    if mat_name in ["Gold", "Au"]:
        from meep.materials import Au
        base = Au
    elif mat_name in ["Silicon", "cSi"]:
        from meep.materials import cSi
        base = cSi
    else:
        return mp.Medium(epsilon=1.0, **cond_attr)

    new_sus = []
    for sus in base.E_susceptibilities:
        freq = sus.frequency
        gamma = sus.gamma
        gamma_val = gamma + Sigma if ft == mp.E_stuff else gamma
        if isinstance(sus, mp.DrudeSusceptibility):
            if freq < 1e-5:
                sigma_val = sus.sigma_diag.x * (freq ** 2)
                freq_val = 1.0
            else:
                sigma_val = sus.sigma_diag.x
                freq_val = freq
            new_sus.append(mp.DrudeSusceptibility(
                frequency=freq_val,
                gamma=gamma_val,
                sigma=sigma_val
            ))
        elif isinstance(sus, mp.LorentzianSusceptibility):
            new_sus.append(mp.LorentzianSusceptibility(
                frequency=freq,
                gamma=gamma_val,
                sigma=sus.sigma_diag.x
            ))

    return mp.Medium(epsilon=1.0, E_susceptibilities=new_sus, **cond_attr)


def run_concentric_ring_simulation(
    task_id: int,
    N_fractal: int,
    theta_deg: float,
    elements: list,
    L_domain: float,
    R_min: float,
    R_max: float,
    H_teeth: float,
    t_plate: float,
    z_tip: float,
    is_control: bool,
    is_flat_control: bool,
    material: str,
    resolution: int,
    n_max: int,
    config: str,
    T_run: float,
    chk_tag: str,
    max_walltime_hours: float,
    num_sectors: int,
    sector_duty_cycle: float,
    tooth_duty_cycle: float,
    no_cache: bool = False
):
    """
    Executes the 3D FDTD Casimir stress tensor calculation for the concentric ring architecture.
    """
    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)

    # 1. Domain and Boundary Dimensions
    dpml = 0.20
    buffer = 0.10
    delta_xy = 0.03  # 30 nm lateral margin around active tooth cluster
    delta_z_top = max(0.005, z_tip / 2.0)

    # 2. Integration Box S:
    # For flat reference control, enclose full R_max disk.
    # For structured concentric teeth, tightly enclose Sector 0 active teeth in Quadrant 1,
    # exploiting 4-fold rotational symmetry (F_total = num_sectors * F_sector0).
    # Use a fixed square lateral envelope to keep DCT normalization independent of theta.
    if is_flat_control:
        sx_box = 2.0 * (R_max + delta_xy)
        sy_box = sx_box
        z_bot = float(z_tip / 2.0)
        z_top = float(z_tip + H_teeth + delta_z_top)
        sz_box = z_top - z_bot
        cx_box = 0.0
        cy_box = 0.0
        cz_box = (z_top + z_bot) / 2.0
        num_sectors_scale = 1.0
    else:
        sector_pitch_rad = (2.0 * math.pi) / num_sectors
        tooth_arc_rad = sector_pitch_rad * tooth_duty_cycle
        arc_offset_rad = (sector_pitch_rad * 0.50 - tooth_arc_rad) / 2.0
        theta_rad = math.radians(theta_deg)

        phi_start = theta_rad + arc_offset_rad
        phi_end = phi_start + tooth_arc_rad

        r_mins = [e["r_tooth_in"] for e in elements]
        r_maxs = [e["r_tooth_out"] for e in elements]
        r_inner_all = min(r_mins)
        r_outer_all = max(r_maxs)

        phis = np.linspace(phi_start, phi_end, 30)
        xs = np.concatenate([r_inner_all * np.cos(phis), r_outer_all * np.cos(phis)])
        ys = np.concatenate([r_inner_all * np.sin(phis), r_outer_all * np.sin(phis)])

        max_span = 0.0
        for test_angle in np.linspace(0.0, sector_pitch_rad, 361):
            test_phis = np.linspace(
                test_angle + arc_offset_rad,
                test_angle + arc_offset_rad + tooth_arc_rad,
                30
            )
            th_xs = np.concatenate([
                r_inner_all * np.cos(test_phis),
                r_outer_all * np.cos(test_phis)
            ])
            th_ys = np.concatenate([
                r_inner_all * np.sin(test_phis),
                r_outer_all * np.sin(test_phis)
            ])
            max_span = max(
                max_span,
                float(np.max(th_xs) - np.min(th_xs)),
                float(np.max(th_ys) - np.min(th_ys))
            )

        s_box_lat = max_span + 2.0 * delta_xy
        sx_box = s_box_lat
        sy_box = s_box_lat
        cx_box = (float(np.min(xs)) + float(np.max(xs))) / 2.0
        cy_box = (float(np.min(ys)) + float(np.max(ys))) / 2.0
        z_bot = float(z_tip / 2.0)
        z_top = float(z_tip + H_teeth + delta_z_top)
        sz_box = z_top - z_bot
        cz_box = (z_bot + z_top) / 2.0
        num_sectors_scale = float(num_sectors)  # 4-fold rotational symmetry scaling

    # Total Simulation Cell Size
    sx = L_domain + 2.0 * (dpml + buffer)
    sy = sx
    z_max = max(z_top + delta_z_top, t_plate + delta_z_top) + buffer + dpml
    sz = 2.0 * z_max
    cell_size = mp.Vector3(sx, sy, sz)

    # Damping conductivity Sigma for Wick rotation along imaginary frequency
    d_eff = max(0.010, z_tip)
    Sigma = 0.5 / d_eff

    # 6 sides of bounding box S enclosing the active rotor teeth ensemble
    sides_info = [
        {"center": mp.Vector3(cx_box - sx_box / 2.0, cy_box, cz_box), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(cx_box + sx_box / 2.0, cy_box, cz_box), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(cx_box, cy_box - sy_box / 2.0, cz_box), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(cx_box, cy_box + sy_box / 2.0, cz_box), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(cx_box, cy_box, z_bot), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": -1.0},
        {"center": mp.Vector3(cx_box, cy_box, z_top), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": +1.0}
    ]

    pol_list = [mp.Ex, mp.Ey, mp.Ez, mp.Hx, mp.Hy, mp.Hz]
    component_direction = {
        mp.Ex: mp.X, mp.Ey: mp.Y, mp.Ez: mp.Z,
        mp.Dx: mp.X, mp.Dy: mp.Y, mp.Dz: mp.Z,
        mp.Hx: mp.X, mp.Hy: mp.Y, mp.Hz: mp.Z,
        mp.Bx: mp.X, mp.By: mp.Y, mp.Bz: mp.Z
    }

    num_tasks = 36 * n_max
    start_time = time.time()
    max_walltime_sec = (max_walltime_hours * 3600.0) if (max_walltime_hours is not None and max_walltime_hours > 0) else None
    all_moment_durations = []

    def run_one_config(cfg_name):
        chk_file = f".tmp/chk_{chk_tag}_{cfg_name}.json"
        moments_chk = f".tmp/chk_moments_{chk_tag}_{cfg_name}.json"

        # Check full cache
        if not no_cache and os.path.exists(chk_file):
            with open(chk_file, "r") as f_chk:
                data = json.load(f_chk)
            if is_g0:
                print(f"[{cfg_name.upper()}] Loaded cached force: {data['force']:.6e} from {chk_file}")
            return float(data["force"]), True

        completed_moments = {}
        if not no_cache and os.path.exists(moments_chk):
            with open(moments_chk, "r") as f_mom:
                chk_data = json.load(f_mom)
            completed_moments = {int(k): float(v) for k, v in chk_data["completed_moments"].items()}
            if is_g0:
                print(f"[{cfg_name.upper()}] Loaded {len(completed_moments)} cached moments from {moments_chk}")

        total_force = 0.0
        moment_durations = []

        for task_idx in range(num_tasks):
            if task_idx in completed_moments:
                f_cached = completed_moments[task_idx]
                total_force += f_cached
                if is_g0:
                    print(f"  [{cfg_name.upper()}][Rank 0] Skipped moment {task_idx+1}/{num_tasks} [CACHED]: force_integral={f_cached:+.6e}", flush=True)
                continue

            if max_walltime_sec is not None:
                elapsed_sec = time.time() - start_time
                est_dur = np.mean(all_moment_durations) * 1.15 if all_moment_durations else 900.0
                if elapsed_sec + est_dur >= max_walltime_sec:
                    if is_g0:
                        print(f"\n[WALLTIME GUARD] Elapsed {elapsed_sec/3600:.2f}h + estimated moment ({est_dur/60:.1f}m) >= limit ({max_walltime_hours:.2f}h). Pausing cleanly.", flush=True)
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

            # 1. Stator: Bottom Concentric Annular Membrane (present ONLY in 'both')
            if cfg_name == "both":
                stator_shapes = generate_concentric_stator_geometry(
                    elements=elements,
                    L_plate=L_domain,
                    t_plate=t_plate,
                    plate_material=mat_obj,
                    void_material=bg_material,
                    num_sectors=num_sectors,
                    sector_duty_cycle=sector_duty_cycle,
                    theta_deg=0.0,
                    is_flat_control=is_flat_control
                )
                geometry.extend(stator_shapes)

            # 2. Rotor: Concentric Annular Teeth (present in BOTH 'both' and 'self')
            rotor_shapes = generate_concentric_rotor_geometry(
                elements=elements,
                H_teeth=H_teeth,
                z_tip=z_tip,
                rotor_material=mat_obj,
                num_sectors=num_sectors,
                tooth_duty_cycle=tooth_duty_cycle,
                theta_rotor_deg=theta_deg,
                with_backing=False,
                L_plate=L_domain,
                is_flat_control=is_flat_control,
                R_max=R_max
            )
            geometry.extend(rotor_shapes)

            sim = mp.Simulation(
                cell_size=cell_size,
                boundary_layers=[mp.PML(dpml)],
                geometry=geometry,
                resolution=resolution,
                Courant=0.5,
                default_material=bg_material,
                eps_averaging=True
            )

            sim.init_sim()
            dt = sim.Courant / resolution
            T_steps = int(T_run / dt)

            # Casimir Green's function time kernel g(t)
            gt = mp.make_casimir_gfunc(T_run, dt, Sigma, curr_pol)
            addr = int(gt)
            double_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))
            data = np.ctypeslib.as_array(double_ptr, shape=(T_steps * 2,))
            gt_arr = data[0::2] + 1j * data[1::2]

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
                cx_v, cy_v, cz_v = center_vec.x, center_vec.y, center_vec.z
                Nx = (2.0 / sx_v if mx_val > 0 else 1.0 / sx_v) if sx_v > 1e-15 else 1.0
                Ny = (2.0 / sy_v if my_val > 0 else 1.0 / sy_v) if sy_v > 1e-15 else 1.0
                Nz = (2.0 / sz_v if mz_val > 0 else 1.0 / sz_v) if sz_v > 1e-15 else 1.0
                factor = np.sqrt(Nx * Ny * Nz)

                def amp_func(pt):
                    x = (pt.x - cx_v) + 0.5 * sx_v
                    y = (pt.y - cy_v) + 0.5 * sy_v
                    z = (pt.z - cz_v) + 0.5 * sz_v
                    kx = mx_val * np.pi / sx_v if sx_v > 1e-15 else 0.0
                    ky = my_val * np.pi / sy_v if sy_v > 1e-15 else 0.0
                    kz = mz_val * np.pi / sz_v if sz_v > 1e-15 else 0.0
                    return factor * np.cos(kx * x) * np.cos(ky * y) * np.cos(kz * z)
                return amp_func

            src_vol = mp.Volume(center=side_center, size=side_size, dims=3)
            amp_fn = make_amp_func(mx, my, mz, side_size, side_center)

            sim.change_sources([
                mp.Source(
                    src=mp.CustomSource(src_func=lambda t: 1.0 / dt, start_time=-0.25 * dt, end_time=0.75 * dt),
                    component=curr_pol,
                    center=side_center,
                    size=side_size,
                    amp_func=amp_fn
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
                    ft, src_vol.swigobj
                )
                force_integral += np.imag(gt_arr[step] * dt * side_orientation * f_temp)

            total_force += force_integral
            completed_moments[task_idx] = float(force_integral)
            dur = time.time() - moment_start_time
            moment_durations.append(dur)
            all_moment_durations.append(dur)

            if is_g0:
                tmp_path = f"{moments_chk}.tmp_{os.getpid()}"
                with open(tmp_path, "w") as f_chk:
                    json.dump({"completed_moments": {str(k): v for k, v in completed_moments.items()}}, f_chk, indent=4)
                os.replace(tmp_path, moments_chk)
                print(f"  [{cfg_name.upper()}][Rank 0] Done moment {task_idx+1}/{num_tasks}: force_integral={force_integral:+.6e} ({dur:.1f}s)", flush=True)

                progress_file = f"results_concentric_ring/progress_task_{task_id:03d}.json"
                prog_data = {
                    "task_id": task_id,
                    "architecture": "Concentric_Cantor_Ring",
                    "N_fractal": N_fractal,
                    "theta_deg": float(theta_deg),
                    "status": "RUNNING",
                    "current_config": cfg_name,
                    "moments_done_config": len(completed_moments),
                    "moments_total_config": num_tasks,
                    "elapsed_sec": round(time.time() - start_time, 1),
                    "last_moment_sec": round(dur, 1),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                tmp_prog = f"{progress_file}.tmp_{os.getpid()}"
                with open(tmp_prog, "w") as fp_prog:
                    json.dump(prog_data, fp_prog, indent=4)
                os.replace(tmp_prog, progress_file)

        is_done = (len(completed_moments) == num_tasks)
        total_force_scaled = total_force * num_sectors_scale
        if is_g0 and is_done:
            with open(chk_file, "w") as f_out:
                json.dump({
                    "force": float(total_force_scaled),
                    "force_sector0": float(total_force),
                    "num_sectors_scale": float(num_sectors_scale)
                }, f_out, indent=4)
            print(f"[{cfg_name.upper()}] Complete. Sector 0 force: {total_force:+.6e}, Total rotor force ({num_sectors_scale:.0f}x): {total_force_scaled:+.6e}")

        return total_force_scaled, is_done

    if config == "both":
        f_both, both_done = run_one_config("both")
        return f_both, 0.0, 0.0, both_done
    elif config == "self":
        f_self, self_done = run_one_config("self")
        return 0.0, f_self, 0.0, self_done
    else:  # 'all'
        f_both, both_done = run_one_config("both")
        if both_done:
            f_self, self_done = run_one_config("self")
        else:
            f_self = 0.0
            self_done = False
        all_done = bool(both_done and self_done)
        f_sub = (f_both - f_self) if all_done else 0.0
        return f_both, f_self, f_sub, all_done


def main():
    parser = argparse.ArgumentParser(description="Concentric Cantor-Ring 3D FDTD Casimir Solver")
    parser.add_argument("--config-file", type=str, default="", help="Path to task JSON config file.")
    parser.add_argument("--task-id", type=int, default=1, help="Task ID")
    parser.add_argument("--config", type=str, default="all", choices=["both", "self", "all"])
    parser.add_argument("--max-walltime-hours", type=float, default=7.2, help="Walltime limit buffer")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cached checkpoints")
    args = parser.parse_args()

    # Load from config file if provided
    if args.config_file and os.path.exists(args.config_file):
        with open(args.config_file, "r") as fc:
            cfg = json.load(fc)
    else:
        cfg_path = f"sweep_configs_concentric_ring/config_{args.task_id:03d}.json"
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as fc:
                cfg = json.load(fc)
        else:
            raise FileNotFoundError(f"Configuration file {cfg_path} not found!")

    task_id = int(cfg["task_id"])
    N_fractal = int(cfg["N_fractal"])
    theta_deg = float(cfg["theta_deg"])
    elements = cfg["elements"]
    L_domain = float(cfg["L_domain_um"])
    R_min = float(cfg["R_min_um"])
    R_max = float(cfg["R_max_um"])
    H_teeth = float(cfg["H_teeth_um"])
    t_plate = float(cfg["t_plate_um"])
    z_tip = float(cfg["z_tip_um"])
    is_control = bool(cfg["is_control"])
    is_flat_control = bool(cfg["is_flat_control"])
    material = str(cfg["material"])
    resolution = int(cfg["resolution"])
    nmax = int(cfg["nmax"])
    T_run = float(cfg["T_run"])
    num_sectors = int(cfg["num_sectors"])
    sector_duty_cycle = float(cfg["sector_duty_cycle"])
    tooth_duty_cycle = float(cfg["tooth_duty_cycle"])

    chk_tag = (
        f"v3_concentric_ring_task_{task_id:03d}_N_{N_fractal}_th_{theta_deg:.1f}_"
        f"ctrl_{int(is_control)}_flat_{int(is_flat_control)}_res_{resolution}"
    )

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)

    if is_g0:
        print("=" * 80)
        print(f"CONCENTRIC CANTOR-RING CASIMIR SOLVER: TASK {task_id}")
        print(f"Architecture: {'Cantor Ring N=' + str(N_fractal) if not is_control else 'Non-Fractal Control'}")
        print(f"Rotation Angle: theta = {theta_deg:.1f} deg | Standoff z_tip = {z_tip*1e3:.2f} nm (<d> = {cfg['d_average_nm']:.1f} nm)")
        print(f"Tracks: {len(elements)} annular tracks | Domain: {L_domain:.2f} um | Resolution: {resolution} px/um")
        print(f"Material: {material} | Courant: 0.5 | T_run: {T_run}")
        print("=" * 80, flush=True)

    f_both, f_self, f_net, all_done = run_concentric_ring_simulation(
        task_id=task_id,
        N_fractal=N_fractal,
        theta_deg=theta_deg,
        elements=elements,
        L_domain=L_domain,
        R_min=R_min,
        R_max=R_max,
        H_teeth=H_teeth,
        t_plate=t_plate,
        z_tip=z_tip,
        is_control=is_control,
        is_flat_control=is_flat_control,
        material=material,
        resolution=resolution,
        n_max=nmax,
        config=args.config,
        T_run=T_run,
        chk_tag=chk_tag,
        max_walltime_hours=args.max_walltime_hours,
        num_sectors=num_sectors,
        sector_duty_cycle=sector_duty_cycle,
        tooth_duty_cycle=tooth_duty_cycle,
        no_cache=args.no_cache
    )

    os.makedirs(".tmp", exist_ok=True)
    os.makedirs("results_concentric_ring", exist_ok=True)

    flag_pending = f".tmp/concentric_ring_task_{task_id:03d}_pending.flag"
    flag_complete = f".tmp/concentric_ring_task_{task_id:03d}_complete.flag"
    progress_file = f"results_concentric_ring/progress_task_{task_id:03d}.json"

    if not all_done:
        if is_g0:
            print("\n" + "=" * 80)
            print(f"[WALLTIME CHECKPOINT] Task {task_id} completed partial moments and cleanly checkpointed to .tmp/.")
            print("Status: PENDING remaining moments. Follow-up segment will resume seamlessly.")
            print("=" * 80 + "\n", flush=True)
            if os.path.exists(flag_complete):
                os.remove(flag_complete)
            with open(flag_pending, "w") as fp:
                fp.write(f"pending:{time.time()}\n")

            prog_data = {
                "task_id": task_id,
                "architecture": "Concentric_Cantor_Ring",
                "N_fractal": N_fractal,
                "theta_deg": float(theta_deg),
                "status": "PAUSED_WALLTIME",
                "all_done": False,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            tmp_prog = f"{progress_file}.tmp_{os.getpid()}"
            with open(tmp_prog, "w") as fp_prog:
                json.dump(prog_data, fp_prog, indent=4)
            os.replace(tmp_prog, progress_file)
        return

    if is_g0:
        with open(flag_complete, "w") as fp:
            fp.write(f"complete:{time.time()}\n")
        if os.path.exists(flag_pending):
            os.remove(flag_pending)

        prog_data = {
            "task_id": task_id,
            "architecture": "Concentric_Cantor_Ring",
            "N_fractal": N_fractal,
            "theta_deg": float(theta_deg),
            "status": "COMPLETE",
            "all_done": True,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        tmp_prog = f"{progress_file}.tmp_{os.getpid()}"
        with open(tmp_prog, "w") as fp_prog:
            json.dump(prog_data, fp_prog, indent=4)
        os.replace(tmp_prog, progress_file)

    if is_g0 and args.config == "all":
        # Force conversions
        f_net_N = f_net * MEEP_FORCE_TO_SI
        f_net_fN = f_net * MEEP_FORCE_TO_FN
        f_net_pN = f_net_N * 1e12

        # Active domain area (disk of R_max): pi * R_max^2
        area_active_um2 = math.pi * (R_max ** 2)
        area_cell_um2 = L_domain ** 2
        pressure_Pa = (f_net / area_cell_um2) * MEEP_TO_PA

        # Full chip scale on 100 um disk (radius 50 um)
        area_chip_100um = math.pi * (50.0 ** 2)
        n_disks_100um = area_chip_100um / area_active_um2
        f_chip_100um_nN = f_net_N * n_disks_100um * 1e9

        result_data = {
            "task_id": task_id,
            "architecture": "Concentric_Cantor_Ring",
            "N_fractal": N_fractal,
            "is_control": is_control,
            "is_flat_control": is_flat_control,
            "theta_deg": float(theta_deg),
            "num_tracks": len(elements),
            "L_domain_um": L_domain,
            "R_min_nm": R_min * 1e3,
            "R_max_nm": R_max * 1e3,
            "d_average_nm": cfg["d_average_nm"],
            "area_fraction": cfg["area_fraction"],
            "z_tip_nm": z_tip * 1e3,
            "material": material,
            "resolution": resolution,
            "force_both_meep": float(f_both),
            "force_self_meep": float(f_self),
            "force_net_meep": float(f_net),
            "force_net_fN": float(f_net_fN),
            "force_net_pN": float(f_net_pN),
            "pressure_Pa": float(pressure_Pa),
            "chip_scale_100um": {
                "force_net_nN": float(f_chip_100um_nN)
            },
            "provenance": {
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "slurm_job_id": os.environ.get("SLURM_JOB_ID", "local"),
                "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID", str(task_id)),
                "num_mpi_ranks": int(os.environ.get("SLURM_NTASKS", "1")),
                "config_file": args.config_file or f"sweep_configs_concentric_ring/config_{task_id:03d}.json",
                "algorithm": "FDTD Maxwell stress tensor with Wick-rotated Sigma damping (F_both - F_self)",
                "discrete_cosine_transform_basis": "Orthogonal DCT-I on standardized square Sector 0 box",
                "symmetry_scaling": f"{num_sectors}x rotational symmetry (C_4)",
                "date_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()
            },
            "regime": "REPULSIVE" if f_net > 0 else "ATTRACTIVE",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        out_dest = f"results_concentric_ring/task_{task_id:03d}_N{N_fractal}_th_{int(theta_deg)}deg.json"
        with open(out_dest, "w") as f:
            json.dump(result_data, f, indent=4)

        try:
            from utils.metrics_logger import log_metric, export_macros
            log_metric(
                f"concentric_ring_task_{task_id:03d}_force_fN",
                float(f_net_fN),
                step_id=f"task_{task_id:03d}"
            )
            log_metric(
                f"concentric_ring_task_{task_id:03d}_pressure_Pa",
                float(pressure_Pa),
                step_id=f"task_{task_id:03d}"
            )
            log_metric(
                f"concentric_ring_task_{task_id:03d}_chip_force_nN",
                float(f_chip_100um_nN),
                step_id=f"task_{task_id:03d}"
            )
            export_macros()
        except Exception:
            pass

        print("\n" + "=" * 80)
        print("SIMULATION COMPLETE: CONCENTRIC CANTOR-RING CASIMIR EVALUATION")
        print(f"Force Both (MEEP):          {f_both:+.6e}")
        print(f"Force Self (MEEP):          {f_self:+.6e}")
        print(f"Net Force (MEEP):           {f_net:+.6e}")
        print(f"Net Force (fN):             {f_net_fN:+.4f} fN  --> {'[+++ CASIMIR REPULSION +++]' if f_net > 0 else '[- ATTRACTIVE -]'}")
        print(f"Net Force (pN):             {f_net_pN:+.4f} pN")
        print(f"Casimir Pressure:           {pressure_Pa:+.4e} Pa")
        print(f"Chip Force (100 um disk):   {f_chip_100um_nN:+.4f} nN")
        print(f"Results saved to:           {out_dest}")
        print("=" * 80 + "\n", flush=True)


if __name__ == "__main__":
    main()
