#!/usr/bin/env python3
"""
Sierpinski-Cantor Forest 3D FDTD Casimir Repulsion Solver (BigRed 200)
----------------------------------------------------------------------
Simulates a space-filling 3D Cantor Forest of metallic pillars centered
inside a Sierpinski Carpet Sieve perforated membrane in pure vacuum (eps_bg = 1.0).

By breaking the Kenneth-Klich separating plane condition in a Cartesian space-filling
fractal, the Maxwell stress tensor develops a transverse field expulsion at pillar
edges when entering the near-field regime z_tip < W_k / 4, producing macroscopic
geometric Casimir repulsion across up to 730,000 pillars on a chip.

Physics Reference:
- Levin, McCauley, Rodriguez, Reid, Johnson, Phys. Rev. Lett. 105, 090403 (2010).
- Kenneth, Klich, Phys. Rev. Lett. 97, 160401 (2006).
"""

import os
import sys
import json
import time
import ctypes
import argparse
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

from execution.cantor_forest_geometry import (
    get_sierpinski_cantor_elements,
    compute_sieve_area_fractions,
    generate_sierpinski_sieve_geometry,
    generate_cantor_forest_geometry
)


def get_src_index(n):
    """Cantor pairing function decoder for DCT multipole indices."""
    r = int((np.sqrt(8 * n + 1) - 1) / 2)
    c = n - r * (r + 1) // 2
    return r - c, c


# Physical conversion constants for MEEP dimensionless units (hbar = c = 1, a = 1 um)
# Force:    1 unit = hbar * c / a^2 = 3.1615e-14 N = 31.615 fN
# Pressure: 1 unit = hbar * c / a^4 = 0.031615 Pa
MEEP_TO_PA = 0.031615
MEEP_FORCE_TO_SI = 3.1615e-14  # N per MEEP force unit
MEEP_FORCE_TO_FN = 31.615      # fN per MEEP force unit


def run_cantor_forest_simulation(
    task_id=1,
    N_fractal=3,
    theta_deg=0.0,
    L_cell=1.0,
    W1_aperture=0.250,
    w1_pillar=0.035,
    H_pillar=0.250,
    t_plate=0.025,
    z_tip=0.015,
    r_fillet=0.0,
    with_backing=False,
    t_backing=0.050,
    is_flat_control=False,
    material="Gold",
    resolution=60,
    n_max=1,
    config="all",
    T_run=12.0,
    dpml=0.20,
    buffer=0.15,
    chk_tag="cantor_forest",
    max_walltime_hours=7.5,
    no_cache=False
):
    """
    Executes 3D FDTD Maxwell stress tensor integration for the Sierpinski-Cantor Forest.
    Evaluates F_both (top pillars + bottom sieve) and F_self (top pillars alone in vacuum).
    Net Casimir force: F_net = F_both - F_self.
    F_net > 0 indicates genuine geometric Casimir REPULSION in vacuum.
    """
    if mp is None:
        raise RuntimeError("Meep module not found. Run in the BigRed 200 meep environment.")

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)
    os.makedirs(".tmp", exist_ok=True)
    os.makedirs("results_cantor_forest", exist_ok=True)

    # 1. Geometry Elements & Plate Boundaries
    # Stator plate occupies: z in [-t_plate, 0]
    # Pillars occupy: z in [z_tip, z_tip + H_pillar]
    if not is_flat_control and N_fractal > 0:
        elements = get_sierpinski_cantor_elements(N_fractal, L_cell, W1_aperture, w1_pillar)
    else:
        elements = []

    dx = 1.0 / resolution
    delta_xy = max(0.025, 2.0 * dx)
    delta_z = max(0.025, 2.0 * dx)

    # Integration box S coordinates:
    # Bottom face at z_bot = z_tip / 2.0, strictly within homogeneous vacuum gap.
    z_bot = z_tip / 2.0
    if with_backing:
        z_top = z_tip + H_pillar + t_backing + delta_z
    else:
        z_top = z_tip + H_pillar + delta_z

    if is_flat_control:
        sx_box = L_cell + 2.0 * delta_xy
        sy_box = sx_box
    else:
        # Enclose all pillars with margin delta_xy
        max_coord = max(abs(e["cx"]) + e["w_pillar"] / 2.0 for e in elements) if elements else L_cell / 2.0
        sx_box = 2.0 * (max_coord + delta_xy)
        sy_box = sx_box

    sz_box = z_top - z_bot
    z_box_center = (z_top + z_bot) / 2.0

    # 3D Computational Domain Dimensions
    L_plate = L_cell
    sx = L_plate + 2.0 * (dpml + buffer)
    sy = sx
    z_max = max(z_top + delta_z, t_plate + delta_z) + buffer + dpml
    sz = 2.0 * z_max
    cell_size = mp.Vector3(sx, sy, sz)

    # Damping conductivity Sigma for Wick rotation along imaginary frequency
    d_eff = max(0.010, min(z_tip, (W1_aperture - w1_pillar) / 2.0 if W1_aperture > w1_pillar else z_tip))
    Sigma = 0.5 / d_eff

    # 6 sides of bounding box S enclosing the top plate ensemble
    sides_info = [
        {"center": mp.Vector3(-sx_box / 2.0, 0.0, z_box_center), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(+sx_box / 2.0, 0.0, z_box_center), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(0.0, -sy_box / 2.0, z_box_center), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(0.0, +sy_box / 2.0, z_box_center), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(0.0, 0.0, z_bot), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": -1.0},
        {"center": mp.Vector3(0.0, 0.0, z_top), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": +1.0}
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

    def run_one_config(cfg_name):
        chk_file = f".tmp/chk_{chk_tag}_{cfg_name}.json"
        moments_chk = f".tmp/chk_moments_{chk_tag}_{cfg_name}.json"

        # Check full cache
        if not no_cache and os.path.exists(chk_file):
            try:
                with open(chk_file, "r") as f_chk:
                    data = json.load(f_chk)
                if is_g0:
                    print(f"[{cfg_name.upper()}] Loaded cached force: {data['force']:.6e} from {chk_file}")
                return float(data["force"]), True
            except (json.JSONDecodeError, KeyError, ValueError) as err:
                if is_g0:
                    print(f"[{cfg_name.upper()}] Notice: Stale/corrupt checkpoint {chk_file} ({err}). Recomputing.")

        completed_moments = {}
        if not no_cache and os.path.exists(moments_chk):
            try:
                with open(moments_chk, "r") as f_mom:
                    chk_data = json.load(f_mom)
                completed_moments = {int(k): float(v) for k, v in chk_data.get("completed_moments", {}).items()}
                if is_g0:
                    print(f"[{cfg_name.upper()}] Loaded {len(completed_moments)} cached moments from {moments_chk}")
            except (json.JSONDecodeError, KeyError, ValueError) as err:
                if is_g0:
                    print(f"[{cfg_name.upper()}] Notice: Stale/corrupt moments file {moments_chk} ({err}). Starting fresh.")
                completed_moments = {}

        total_force = 0.0
        moment_durations = []

        for task_idx in range(num_tasks):
            if task_idx in completed_moments:
                f_cached = completed_moments[task_idx]
                total_force += f_cached
                if is_g0:
                    print(f"  [{cfg_name.upper()}][Rank 0] Skipped moment {task_idx+1}/{num_tasks} [CACHED]: force_integral={f_cached:+.6e}", flush=True)
                continue

            if moment_durations and max_walltime_sec is not None:
                elapsed_sec = time.time() - start_time
                avg_dur = np.mean(moment_durations)
                if elapsed_sec + avg_dur * 1.15 >= max_walltime_sec:
                    if is_g0:
                        print(f"\n[WALLTIME GUARD] Elapsed {elapsed_sec/3600:.2f}h + estimated moment ({avg_dur/60:.1f}m) >= limit ({max_walltime_hours:.2f}h). Pausing cleanly.", flush=True)
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

            # 1. Stator: Bottom Sierpinski Sieve Membrane (present ONLY in 'both' config)
            if cfg_name == "both":
                if is_flat_control:
                    # Solid flat plate control
                    geometry.append(mp.Block(
                        center=mp.Vector3(0.0, 0.0, -t_plate / 2.0),
                        size=mp.Vector3(L_plate, L_plate, t_plate),
                        material=mat_obj
                    ))
                else:
                    # Space-filling Sierpinski Sieve
                    sieve_shapes = generate_sierpinski_sieve_geometry(
                        elements=elements,
                        L_plate=L_plate,
                        t_plate=t_plate,
                        plate_material=mat_obj,
                        void_material=bg_material,
                        theta=theta_deg,
                        r_fillet=r_fillet
                    )
                    geometry.extend(sieve_shapes)

            # 2. Rotor / Top Plate: Cantor Forest of Pillars (present in BOTH 'both' and 'self')
            if is_flat_control:
                # Solid flat top plate
                z_top_center = z_tip + H_pillar / 2.0
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, z_top_center),
                    size=mp.Vector3(L_plate, L_plate, H_pillar),
                    material=mat_obj
                ))
            else:
                cantor_shapes = generate_cantor_forest_geometry(
                    elements=elements,
                    z_tip=z_tip,
                    H_pillar=H_pillar,
                    pillar_material=mat_obj,
                    with_backing=with_backing,
                    L_plate=L_plate,
                    t_back=t_backing
                )
                geometry.extend(cantor_shapes)

            sim = mp.Simulation(
                cell_size=cell_size,
                geometry=geometry,
                resolution=resolution,
                boundary_layers=[mp.PML(dpml)],
                default_material=bg_material,
                Courant=0.5,
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

            def make_amp_func(mx_val, my_val, mz_val, size_vec):
                sx_v, sy_v, sz_v = size_vec.x, size_vec.y, size_vec.z
                Nx = (2.0 / sx_v if mx_val > 0 else 1.0 / sx_v) if sx_v > 1e-15 else 1.0
                Ny = (2.0 / sy_v if my_val > 0 else 1.0 / sy_v) if sy_v > 1e-15 else 1.0
                Nz = (2.0 / sz_v if mz_val > 0 else 1.0 / sz_v) if sz_v > 1e-15 else 1.0
                factor = np.sqrt(Nx * Ny * Nz)

                def amp_func(p):
                    x = p.x + 0.5 * sx_v
                    y = p.y + 0.5 * sy_v
                    z = p.z + 0.5 * sz_v
                    kx = mx_val * np.pi / sx_v if sx_v > 1e-15 else 0.0
                    ky = my_val * np.pi / sy_v if sy_v > 1e-15 else 0.0
                    kz = mz_val * np.pi / sz_v if sz_v > 1e-15 else 0.0
                    return factor * np.cos(kx * x) * np.cos(ky * y) * np.cos(kz * z)
                return amp_func

            src_vol = mp.Volume(center=side_center, size=side_size, dims=3)
            amp_fn = make_amp_func(mx, my, mz, side_size)

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
            moment_durations.append(time.time() - moment_start_time)

            if is_g0:
                tmp_path = f"{moments_chk}.tmp_{os.getpid()}"
                try:
                    with open(tmp_path, "w") as f_chk:
                        json.dump({"completed_moments": {str(k): v for k, v in completed_moments.items()}}, f_chk, indent=4)
                    os.replace(tmp_path, moments_chk)
                except OSError as write_err:
                    print(f"Warning: Failed writing incremental checkpoint: {write_err}", flush=True)
                print(f"  [{cfg_name.upper()}][Rank 0] Done moment {task_idx+1}/{num_tasks}: force_integral={force_integral:+.6e} ({moment_durations[-1]:.1f}s)", flush=True)

        is_done = (len(completed_moments) == num_tasks)
        if is_g0 and is_done:
            try:
                with open(chk_file, "w") as f_out:
                    json.dump({"force": float(total_force)}, f_out, indent=4)
                print(f"[{cfg_name.upper()}] Complete. Total force: {total_force:+.6e}")
            except OSError as save_err:
                print(f"Warning: Failed writing config checkpoint {chk_file}: {save_err}", flush=True)

        return total_force, is_done

    # Run requested configurations
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
    parser = argparse.ArgumentParser(description="Sierpinski-Cantor Forest 3D FDTD Casimir Repulsion Solver")
    parser.add_argument("--task-id", type=int, default=1, help="Task ID")
    parser.add_argument("--N-fractal", type=int, default=3, help="Prefractal generation (1, 2, or 3)")
    parser.add_argument("--theta", type=float, default=0.0, help="Rotation angle in degrees")
    parser.add_argument("--L-cell", type=float, default=1.05, help="Unit cell span (um)")
    parser.add_argument("--W1-aperture", type=float, default=0.250, help="Primary aperture width (um)")
    parser.add_argument("--w1-pillar", type=float, default=0.035, help="Primary pillar width (um)")
    parser.add_argument("--H-pillar", type=float, default=0.250, help="Pillar height (um)")
    parser.add_argument("--t-plate", type=float, default=0.025, help="Stator membrane thickness (um)")
    parser.add_argument("--z-tip", type=float, default=0.015, help="Tip clearance above membrane (um)")
    parser.add_argument("--r-fillet", type=float, default=0.0, help="Aperture corner fillet radius (um)")
    parser.add_argument("--with-backing", action="store_true", help="Include solid backing substrate on top plate")
    parser.add_argument("--t-backing", type=float, default=0.050, help="Backing plate thickness (um)")
    parser.add_argument("--is-flat-control", action="store_true", help="Run solid flat plate control")
    parser.add_argument("--material", type=str, default="Gold", help="Plate and pillar metallic material")
    parser.add_argument("--res", type=int, default=60, help="Grid resolution (pixels/um)")
    parser.add_argument("--nmax", type=int, default=1, help="Multipole cutoff")
    parser.add_argument("--config", type=str, default="all", choices=["both", "self", "all"])
    parser.add_argument("--T-run", type=float, default=12.0, help="FDTD run time")
    parser.add_argument("--max-walltime-hours", type=float, default=7.5, help="Walltime limit buffer")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cached checkpoints")
    args = parser.parse_args()

    chk_tag = (
        f"cantor_task_{args.task_id:03d}_N_{args.N_fractal}_th_{args.theta:.1f}_"
        f"ztip_{args.z_tip:.4f}_res_{args.res}_back_{int(args.with_backing)}"
    )

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)

    if is_g0:
        expected_n = {0: 0, 1: 1, 2: 9, 3: 73}.get(args.N_fractal, 73)
        if args.is_flat_control:
            expected_n = 0
        print("=" * 80)
        print("SIERPINSKI-CANTOR FOREST 3D FDTD CASIMIR REPULSION SOLVER")
        print(f"Task ID: {args.task_id} | Generation N: {args.N_fractal} | Active Pillars: {expected_n} | Rotation Theta: {args.theta:.1f} deg")
        print(f"Cell Span L: {args.L_cell*1e3:.1f} nm | Aperture W1: {args.W1_aperture*1e3:.1f} nm | Pillar w1: {args.w1_pillar*1e3:.1f} nm")
        print(f"Pillar Height H: {args.H_pillar*1e3:.1f} nm | Membrane Thickness t: {args.t_plate*1e3:.1f} nm")
        print(f"Tip Clearance z_tip: {args.z_tip*1e3:.2f} nm (W1/4 threshold = {args.W1_aperture*250:.1f} nm)")
        print(f"Corner Profile: {'Filleted (r = ' + str(int(args.r_fillet*1e3)) + ' nm)' if args.r_fillet > 0 else 'Sharp 90-degree'}")
        print(f"Backing Substrate: {'YES (Monolithic Cantor Chip)' if args.with_backing else 'NO (Pillars Only)'}")
        print(f"Flat Control: {'YES' if args.is_flat_control else 'NO'}")
        print(f"Material: {args.material} | Resolution: {args.res} (dx = {1000/args.res:.2f} nm)")
        print("=" * 80, flush=True)

    f_both, f_self, f_net, all_done = run_cantor_forest_simulation(
        task_id=args.task_id,
        N_fractal=args.N_fractal,
        theta_deg=args.theta,
        L_cell=args.L_cell,
        W1_aperture=args.W1_aperture,
        w1_pillar=args.w1_pillar,
        H_pillar=args.H_pillar,
        t_plate=args.t_plate,
        z_tip=args.z_tip,
        r_fillet=args.r_fillet,
        with_backing=args.with_backing,
        t_backing=args.t_backing,
        is_flat_control=args.is_flat_control,
        material=args.material,
        resolution=args.res,
        n_max=args.nmax,
        config=args.config,
        T_run=args.T_run,
        chk_tag=chk_tag,
        max_walltime_hours=args.max_walltime_hours,
        no_cache=args.no_cache
    )

    if not all_done:
        if is_g0:
            print("\n" + "=" * 80)
            print(f"[WALLTIME CHECKPOINT] Task {args.task_id} completed partial moments and cleanly checkpointed to .tmp/.")
            print(f"Status: PENDING remaining moments. Follow-up segment will resume seamlessly.")
            print("=" * 80 + "\n", flush=True)
            flag_pending = f".tmp/cantor_task_{args.task_id:03d}_pending.flag"
            try:
                with open(flag_pending, "w") as fp:
                    fp.write(f"pending:{time.time()}\n")
            except OSError:
                pass
        return

    if is_g0:
        flag_complete = f".tmp/cantor_task_{args.task_id:03d}_complete.flag"
        try:
            with open(flag_complete, "w") as fp:
                fp.write(f"complete:{time.time()}\n")
            flag_pending = f".tmp/cantor_task_{args.task_id:03d}_pending.flag"
            if os.path.exists(flag_pending):
                os.remove(flag_pending)
        except OSError:
            pass

    if is_g0 and args.config == "all":
        # Force in SI units per unit cell:
        f_net_N = f_net * MEEP_FORCE_TO_SI
        f_net_fN = f_net * MEEP_FORCE_TO_FN
        f_net_pN = f_net_N * 1e12

        # Pressure on unit cell (P = F / L_cell^2):
        pressure_Pa = (f_net / (args.L_cell ** 2)) * MEEP_TO_PA

        # Chip-scale force on 100 um x 100 um chip (10,000 unit cells):
        n_cells_100um = (100.0 / args.L_cell) ** 2
        f_chip_100um_nN = f_net_N * n_cells_100um * 1e9

        expected_n = {0: 0, 1: 1, 2: 9, 3: 73}.get(args.N_fractal, 73)
        if args.is_flat_control:
            expected_n = 0
        total_pillars_100um = int(expected_n * n_cells_100um)

        result_data = {
            "task_id": args.task_id,
            "architecture": "Sierpinski_Cantor_Forest",
            "N_fractal": args.N_fractal,
            "theta_deg": float(args.theta),
            "num_pillars_per_cell": expected_n,
            "L_cell_nm": args.L_cell * 1e3,
            "W1_aperture_nm": args.W1_aperture * 1e3,
            "w1_pillar_nm": args.w1_pillar * 1e3,
            "H_pillar_nm": args.H_pillar * 1e3,
            "t_plate_nm": args.t_plate * 1e3,
            "z_tip_nm": args.z_tip * 1e3,
            "W1_over_4_nm": (args.W1_aperture / 4.0) * 1e3,
            "r_fillet_nm": args.r_fillet * 1e3,
            "with_backing": bool(args.with_backing),
            "is_flat_control": bool(args.is_flat_control),
            "material": args.material,
            "resolution": args.res,
            "force_both_meep": float(f_both),
            "force_self_meep": float(f_self),
            "force_net_meep": float(f_net),
            "force_net_fN_per_cell": float(f_net_fN),
            "force_net_pN_per_cell": float(f_net_pN),
            "pressure_Pa": float(pressure_Pa),
            "chip_scale_100um": {
                "num_cells": int(n_cells_100um),
                "total_pillars": total_pillars_100um,
                "force_net_nN": float(f_chip_100um_nN)
            },
            "regime": "REPULSIVE" if f_net > 0 else "ATTRACTIVE",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        out_dest = f"results_cantor_forest/task_{args.task_id:03d}_N{args.N_fractal}_th_{int(args.theta)}deg.json"
        with open(out_dest, "w") as f:
            json.dump(result_data, f, indent=4)

        print("\n" + "=" * 80)
        print("SIMULATION COMPLETE: SIERPINSKI-CANTOR FOREST CASIMIR EVALUATION")
        print(f"Force Both (MEEP):          {f_both:+.6e}")
        print(f"Force Self (MEEP):          {f_self:+.6e}")
        print(f"Net Force (MEEP):           {f_net:+.6e}")
        print(f"Net Force per Cell (fN):    {f_net_fN:+.4f} fN  --> {'[+++ CASIMIR REPULSION +++]' if f_net > 0 else '[- ATTRACTIVE -]'}")
        print(f"Net Force per Cell (pN):    {f_net_pN:+.4f} pN")
        print(f"Casimir Pressure:           {pressure_Pa:+.4e} Pa")
        print(f"Chip Force (100x100 um):    {f_chip_100um_nN:+.4f} nN ({total_pillars_100um:,} active pillars)")
        print(f"Results saved to:           {out_dest}")
        print("=" * 80 + "\n", flush=True)


if __name__ == "__main__":
    main()
