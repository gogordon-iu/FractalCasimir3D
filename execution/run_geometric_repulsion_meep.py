#!/usr/bin/env python3
"""
Geometric Vacuum Casimir Repulsion Solver (Proposition 2: Levin-Johnson Architecture)
-------------------------------------------------------------------------------------
Simulates an elongated metallic needle centered above an aperture in a thin metallic
membrane in pure vacuum (eps_bg = 1.0).

By breaking the Kenneth-Klich separating plane condition, the vacuum Maxwell stress
tensor develops a transverse field expulsion when the needle enters the near-field
regime z_tip < W / 4, producing a strictly repulsive Casimir force (F_z > 0).

Physics Reference:
Levin, McCauley, Rodriguez, Reid, Johnson, Phys. Rev. Lett. 105, 090403 (2010).
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

def get_src_index(n):
    r = int((np.sqrt(8 * n + 1) - 1) / 2)
    c = n - r * (r + 1) // 2
    return r - c, c

# Physical conversion constants for MEEP dimensionless units (hbar = c = 1, a = 1 um)
# Pressure: 1 unit = hbar * c / a^4 = 0.031615 Pa
# Force:    1 unit = hbar * c / a^2 = 3.1615e-14 N = 31.615 fN
MEEP_TO_PA = 0.031615
MEEP_FORCE_TO_SI = 3.1615e-14  # Newtons per MEEP force unit


def run_geometric_repulsion_simulation(
    W_aperture=0.35,     # Aperture width (microns)
    t_plate=0.025,       # Plate thickness (microns)
    H_needle=0.25,       # Needle height (microns)
    w_needle=0.04,       # Needle width (microns)
    z_tip=0.03,          # Tip clearance above plate surface (microns)
    material="Gold",     # Metallic material
    resolution=80,       # Pixels per micron (12.5 nm)
    n_max=1,             # Multipole cutoff (36 moments per polarization)
    config="all",        # 'both', 'self', or 'all'
    T_run=12.0,          # FDTD run duration
    dpml=0.20,           # PML thickness (microns)
    buffer=0.15,         # Vacuum buffer between objects and PML (microns)
    L_plate=1.0,         # Plate lateral span (microns)
    chk_tag="repulsion", # Checkpoint file identifier
    max_walltime_hours=3.5, # Walltime budget limit
    no_cache=False
):
    """
    Executes FDTD Maxwell stress tensor integration on the elongated needle.
    Evaluates F_both (needle + aperture plate) and F_self (needle alone in vacuum).
    Net Casimir force: F_net = F_both - F_self.
    F_net > 0 indicates genuine geometric Casimir REPULSION in vacuum.
    """
    if mp is None:
        raise RuntimeError("Meep module not found. Run in the BigRed 200 meep environment.")

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)
    os.makedirs(".tmp", exist_ok=True)
    os.makedirs("results_geometric_repulsion", exist_ok=True)

    # 1. Coordinate and Integration Box Setup
    # Coordinate origin z = 0 is the TOP SURFACE of the aperture plate.
    # Plate occupies: z in [-t_plate, 0]
    # Needle occupies: z in [z_tip, z_tip + H_needle]
    z_needle_center = z_tip + H_needle / 2.0

    # Standoffs: at least 2 Yee grid cells (2 * dx) to keep the stress tensor
    # surface strictly inside homogeneous vacuum away from dielectric averaging.
    dx = 1.0 / resolution
    delta_xy = max(0.025, 2.0 * dx)
    delta_z = max(0.025, 2.0 * dx)

    sx_box = w_needle + 2.0 * delta_xy
    sy_box = w_needle + 2.0 * delta_xy
    sz_box = H_needle + 2.0 * delta_z
    center_z_box = z_needle_center

    # 3D Cell Dimensions (symmetric around z = 0 to avoid offset errors)
    sx = L_plate + 2.0 * (dpml + buffer)
    sy = sx
    z_max = max(z_tip + H_needle + delta_z, t_plate + delta_z) + buffer + dpml
    sz = 2.0 * z_max
    cell_size = mp.Vector3(sx, sy, sz)

    # Damping conductivity Sigma for Wick rotation along imaginary frequency
    d_eff = max(0.04, min(z_tip, (W_aperture - w_needle) / 2.0))
    Sigma = 0.5 / d_eff

    # 6 sides of bounding box S enclosing ONLY the needle
    sides_info = [
        {"center": mp.Vector3(-sx_box / 2.0, 0.0, center_z_box), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(sx_box / 2.0, 0.0, center_z_box), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": 1.0},
        {"center": mp.Vector3(0.0, -sy_box / 2.0, center_z_box), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(0.0, sy_box / 2.0, center_z_box), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": 1.0},
        {"center": mp.Vector3(0.0, 0.0, center_z_box - sz_box / 2.0), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": -1.0},
        {"center": mp.Vector3(0.0, 0.0, center_z_box + sz_box / 2.0), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": 1.0}
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
                return float(data["force"])
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

        for task_idx in range(num_tasks):
            # 1. Skip if already completed in checkpoint
            if task_idx in completed_moments:
                f_cached = completed_moments[task_idx]
                total_force += f_cached
                if is_g0:
                    print(f"  [{cfg_name.upper()}][Rank 0] Skipped moment {task_idx+1}/{num_tasks} [CACHED]: force_integral={f_cached:+.6e}", flush=True)
                continue

            # 2. Check walltime guard
            if max_walltime_sec is not None:
                elapsed_sec = time.time() - start_time
                if elapsed_sec >= max_walltime_sec:
                    if is_g0:
                        print(f"\n[WALLTIME GUARD] Elapsed {elapsed_sec/3600:.2f}h >= limit ({max_walltime_hours:.2f}h). Pausing cleanly.", flush=True)
                    break

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

            # 1. Aperture Plate (present ONLY in 'both' configuration)
            if cfg_name == "both":
                # Outer solid plate (z in [-t_plate, 0])
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, -t_plate / 2.0),
                    size=mp.Vector3(L_plate, L_plate, t_plate),
                    material=mat_obj
                ))
                # Aperture hole (carved out with bg_material from -t_plate to 0)
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, -t_plate / 2.0),
                    size=mp.Vector3(W_aperture, W_aperture, t_plate + 0.001),
                    material=bg_material
                ))

            # 2. Elongated Needle (present in BOTH 'both' and 'self' configurations)
            # Appended after plate so needle material takes precedence inside the opening
            geometry.append(mp.Block(
                center=mp.Vector3(0.0, 0.0, z_needle_center),
                size=mp.Vector3(w_needle, w_needle, H_needle),
                material=mat_obj
            ))

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

            # Green's function time-kernel g(t)
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

            if is_g0:
                tmp_path = f"{moments_chk}.tmp_{os.getpid()}"
                try:
                    with open(tmp_path, "w") as f_chk:
                        json.dump({"completed_moments": {str(k): v for k, v in completed_moments.items()}}, f_chk, indent=4)
                    os.replace(tmp_path, moments_chk)
                except OSError as write_err:
                    print(f"Warning: Failed writing incremental checkpoint: {write_err}", flush=True)
                print(f"  [{cfg_name.upper()}][Rank 0] Done moment {task_idx+1}/{num_tasks}: force_integral={force_integral:+.6e}", flush=True)

        # Finished all moments for this config
        if is_g0 and len(completed_moments) == num_tasks:
            try:
                with open(chk_file, "w") as f_out:
                    json.dump({"force": float(total_force)}, f_out, indent=4)
                print(f"[{cfg_name.upper()}] Complete. Total force: {total_force:+.6e}")
            except OSError as save_err:
                print(f"Warning: Failed writing config checkpoint {chk_file}: {save_err}", flush=True)

        return total_force

    # Run requested configurations
    if config == "both":
        return run_one_config("both"), 0.0, 0.0
    elif config == "self":
        return 0.0, run_one_config("self"), 0.0
    else:  # 'all'
        f_both = run_one_config("both")
        f_self = run_one_config("self")
        f_sub = f_both - f_self
        return f_both, f_self, f_sub


def main():
    parser = argparse.ArgumentParser(description="Geometric Vacuum Casimir Repulsion (Levin-Johnson Architecture)")
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
    args = parser.parse_args()

    chk_tag = f"geom_repulse_W_{args.W_aperture:.3f}_ztip_{args.z_tip:.4f}_res_{args.res}_mat_{args.material}"

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)
    if is_g0:
        print("=" * 80)
        print("GEOMETRIC VACUUM CASIMIR REPULSION SOLVER (Levin-Johnson Mechanism)")
        print(f"Task ID: {args.task_id}")
        print(f"Aperture Width W: {args.W_aperture*1e3:.1f} nm, Plate Thickness t: {args.t_plate*1e3:.1f} nm")
        print(f"Needle Height H: {args.H_needle*1e3:.1f} nm, Width w: {args.w_needle*1e3:.1f} nm")
        print(f"Tip Clearance z_tip: {args.z_tip*1e3:.1f} nm (W/4 threshold = {args.W_aperture*250:.1f} nm)")
        print(f"Material: {args.material}, Resolution: {args.res} (dx = {1000/args.res:.2f} nm)")
        print(f"Repulsive Regime Expected: {'YES (z_tip < W/4)' if args.z_tip < args.W_aperture/4.0 else 'NO (z_tip > W/4, attractive)'}")
        print("=" * 80, flush=True)

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
        no_cache=args.no_cache
    )

    if is_g0 and args.config == "all":
        # Force in SI units:
        # F_SI = F_meep * (hbar * c / a^2)
        f_net_N = f_net * MEEP_FORCE_TO_SI
        f_net_fN = f_net_N * 1e15  # femtoNewtons
        f_net_nN = f_net_N * 1e9   # nanoNewtons

        # Pressure on needle cross section A = w_needle^2:
        # P_Pa = (F_meep / A_meep) * MEEP_TO_PA
        A_needle_meep = args.w_needle ** 2
        pressure_Pa = (f_net / A_needle_meep) * MEEP_TO_PA

        result_data = {
            "task_id": args.task_id,
            "architecture": "Levin_Johnson_geometric_repulsion",
            "W_aperture_nm": args.W_aperture * 1e3,
            "t_plate_nm": args.t_plate * 1e3,
            "H_needle_nm": args.H_needle * 1e3,
            "w_needle_nm": args.w_needle * 1e3,
            "z_tip_nm": args.z_tip * 1e3,
            "W_over_4_nm": (args.W_aperture / 4.0) * 1e3,
            "material": args.material,
            "resolution": args.res,
            "force_both_meep": float(f_both),
            "force_self_meep": float(f_self),
            "force_net_meep": float(f_net),
            "force_net_fN": float(f_net_fN),
            "force_net_nN": float(f_net_nN),
            "pressure_Pa": float(pressure_Pa),
            "regime": "REPULSIVE" if f_net > 0 else "ATTRACTIVE",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        out_dest = f"results_geometric_repulsion/task_{args.task_id:03d}_ztip_{int(args.z_tip*1e3)}nm.json"
        with open(out_dest, "w") as f:
            json.dump(result_data, f, indent=4)

        print("\n" + "=" * 80)
        print("SIMULATION COMPLETE: GROUND-TRUTH CASIMIR FORCE EVALUATION")
        print(f"Force Both (MEEP):  {f_both:+.6e}")
        print(f"Force Self (MEEP):  {f_self:+.6e}")
        print(f"Net Force (MEEP):   {f_net:+.6e}")
        print(f"Net Force (fN):     {f_net_fN:+.4f} fN  -->  {'[+++ CASIMIR REPULSION +++]' if f_net > 0 else '[- ATTRACTIVE -]'}")
        print(f"Pressure:           {pressure_Pa:+.4e} Pa")
        print(f"Results saved to:   {out_dest}")
        print("=" * 80 + "\n", flush=True)


if __name__ == "__main__":
    main()
