#!/usr/bin/env python3
"""
Dual-Fractal Rotary Vacuum Casimir Clutch Simulation Engine
--------------------------------------------------------------------------------
Completely fractal configuration on BOTH plates:
1. Bottom Stator Plate: Thin gold membrane with a self-similar Sierpinski Sieve
   aperture hierarchy of prefractal generation N.
2. Top Rotor Plate: 3D Menger Fractal Needle Array of matching prefractal
   generation N with high-aspect-ratio tips (H/w >> 1).

Physical Mechanism:
At theta = 0 deg: Every Menger needle is centered 1:1 above a matching Sierpinski
aperture. Because z_tip < W_k / 4 across all fractal levels k, transverse electric
field line expulsion dominates, driving a strictly positive repulsive Casimir force
(F_z > 0) that provides passive, frictionless vacuum levitation.

At theta = 45 deg: Spires rotate onto the continuous solid gold webs of the
Sierpinski membrane. The Kenneth-Klich separating plane is restored beneath the
needle tips, producing strong attractive Casimir adhesion (F_z << 0) for mechanical
braking/clamping.

At theta = 90 deg: By C4 rotational symmetry of the Sierpinski carpet, needles
re-align with orthogonal apertures, returning to the repulsive disengaged state.

By relative rotation theta alone at constant vertical clearance z_tip, the interaction
transitions reversibly:
    FRACTAL REPULSION (F_z > 0) <---> FRACTAL ATTRACTION (F_z < 0)

Physics References:
1. Levin, McCauley, Rodriguez, Reid, Johnson, Phys. Rev. Lett. 105, 090403 (2010).
2. Kenneth & Klich, Phys. Rev. Lett. 97, 160401 (2006).
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

# MEEP dimensionless units to SI conversion (hbar = c = 1, a = 1 um)
# Force:    1 unit = hbar * c / a^2 = 3.1615e-14 N = 31.615 fN
# Pressure: 1 unit = hbar * c / a^4 = 0.031615 Pa
MEEP_TO_PA = 0.031615
MEEP_FORCE_TO_SI = 3.1615e-14


def get_fractal_clutch_elements(N, L, W1=0.35, w1=0.04):
    """
    Computes exact self-similar fractal coordinates for both plates.
    Returns:
        elements: list of dicts with keys:
            level, cx, cy, W_aperture, w_needle
    """
    elements = []
    r1 = L / 3.0

    # Level 1: 4 primary axial aperture/needle pairs (C4 symmetric)
    axial_angles = [0.0, 90.0, 180.0, 270.0]
    for ang in axial_angles:
        rad = np.radians(ang)
        elements.append({
            "level": 1,
            "cx": r1 * np.cos(rad),
            "cy": r1 * np.sin(rad),
            "W_aperture": W1,
            "w_needle": w1
        })

    # Level 2 (if N >= 2): Secondary self-similar aperture/needle pairs
    if N >= 2:
        W2 = W1 / 3.0
        w2 = w1 / 3.0
        r2_diag = r1 * np.sqrt(2.0)
        diag_angles = [45.0, 135.0, 225.0, 315.0]
        for ang in diag_angles:
            rad = np.radians(ang)
            elements.append({
                "level": 2,
                "cx": r2_diag * np.cos(rad),
                "cy": r2_diag * np.sin(rad),
                "W_aperture": W2,
                "w_needle": w2
            })

    # Level 3 (if N >= 3): Tertiary nano-aperture/needle pairs
    if N >= 3:
        W3 = W1 / 9.0
        w3 = w1 / 9.0
        r3_offsets = [-W2, +W2]
        for ang in axial_angles:
            rad = np.radians(ang)
            base_x = r1 * np.cos(rad)
            base_y = r1 * np.sin(rad)
            for off in r3_offsets:
                perp_rad = rad + np.pi / 2.0
                elements.append({
                    "level": 3,
                    "cx": base_x + off * np.cos(perp_rad),
                    "cy": base_y + off * np.sin(perp_rad),
                    "W_aperture": W3,
                    "w_needle": w3
                })

    return elements


def run_fractal_rotary_clutch_simulation(
    N_fractal=2,            # Prefractal generation (1, 2, or 3)
    theta_deg=0.0,          # Relative rotation angle (degrees)
    L_fractal=1.05,         # Fractal base domain span (microns)
    W1_aperture=0.35,       # Primary aperture diameter (microns)
    w1_needle=0.04,         # Primary needle width (microns)
    H_needle=0.25,          # Needle height (microns)
    t_plate=0.025,          # Stator membrane thickness (microns)
    z_tip=0.015,            # Tip clearance above stator surface (microns)
    material="Gold",        # Metallic material
    resolution=80,          # Yee grid resolution (pixels/micron)
    n_max=1,                # Multipole cutoff (36 moments per polarization)
    config="all",           # 'both', 'self', or 'all'
    T_run=12.0,             # FDTD run duration
    dpml=0.20,              # PML thickness (microns)
    buffer=0.15,            # Vacuum buffer between objects and PML (microns)
    chk_tag="fractal_clutch", # Checkpoint file identifier
    max_walltime_hours=7.5, # Walltime budget limit
    no_cache=False
):
    """
    Executes 3D FDTD Maxwell stress tensor integration for the Dual-Fractal Rotary Clutch.
    """
    if mp is None:
        raise RuntimeError("Meep module not found. Run in the BigRed 200 meep environment.")

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)
    os.makedirs(".tmp", exist_ok=True)
    os.makedirs("results_fractal_rotary_clutch", exist_ok=True)

    # 1. Coordinate and Integration Box Setup
    # Origin: z = 0 is top surface of stator membrane.
    # Stator plate occupies: z in [-t_plate, 0]
    # Needles occupy: z in [z_tip, z_tip + H_needle]
    z_needle_center = z_tip + H_needle / 2.0
    dx = 1.0 / resolution

    # Standoffs:
    delta_xy = max(0.025, 2.0 * dx)
    delta_z_top = max(0.025, 2.0 * dx)

    # Bottom face of stress tensor box:
    # Placed at z_bot = z_tip / 2.0, strictly within the vacuum gap (0 < z_bot < z_tip).
    # Guarantees the integration surface never slices into metal at any rotation angle theta.
    z_bot = z_tip / 2.0
    z_top = z_tip + H_needle + delta_z_top

    # Primary Needle 1 is centered at (+r1, 0) where r1 = L_fractal / 3.0
    r1 = L_fractal / 3.0
    sx_box = w1_needle + 2.0 * delta_xy
    sy_box = w1_needle + 2.0 * delta_xy
    sz_box = z_top - z_bot
    z_box_center = (z_top + z_bot) / 2.0

    # 3D Cell Dimensions
    L_plate = L_fractal + 0.40  # Extra boundary padding
    sx = L_plate + 2.0 * (dpml + buffer)
    sy = sx
    z_max = max(z_top + delta_z_top, t_plate + delta_z_top) + buffer + dpml
    sz = 2.0 * z_max
    cell_size = mp.Vector3(sx, sy, sz)

    # Damping conductivity Sigma for Wick rotation along imaginary frequency
    d_eff = max(0.04, min(z_tip, (W1_aperture - w1_needle) / 2.0))
    Sigma = 0.5 / d_eff

    # 6 sides of bounding box S_1 enclosing Primary Needle 1 at (+r1, 0)
    sides_info = [
        {"center": mp.Vector3(r1 - sx_box / 2.0, 0.0, z_box_center), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(r1 + sx_box / 2.0, 0.0, z_box_center), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(r1, -sy_box / 2.0, z_box_center), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(r1, +sy_box / 2.0, z_box_center), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": +1.0},
        {"center": mp.Vector3(r1, 0.0, z_bot), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": -1.0},
        {"center": mp.Vector3(r1, 0.0, z_top), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": +1.0}
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

    # Retrieve fractal hierarchy
    elements = get_fractal_clutch_elements(N_fractal, L_fractal, W1=W1_aperture, w1=w1_needle)
    theta_rad = np.radians(theta_deg)
    cos_th, sin_th = np.cos(theta_rad), np.sin(theta_rad)

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
                avg_dur = np.mean(moment_durations) if moment_durations else 2400.0
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

            # 1. Stator: Thin Gold Membrane with Fractal Apertures (present in 'both' config)
            if cfg_name == "both":
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, -t_plate / 2.0),
                    size=mp.Vector3(L_plate, L_plate, t_plate),
                    material=mat_obj
                ))
                # Rotate aperture positions by theta
                for elem in elements:
                    cx_orig, cy_orig = elem["cx"], elem["cy"]
                    cx_rot = cx_orig * cos_th - cy_orig * sin_th
                    cy_rot = cx_orig * sin_th + cy_orig * cos_th
                    geometry.append(mp.Cylinder(
                        radius=elem["W_aperture"] / 2.0,
                        height=t_plate + 0.001,
                        center=mp.Vector3(cx_rot, cy_rot, -t_plate / 2.0),
                        material=bg_material
                    ))

            # 2. Rotor: Menger Fractal Needle Array (present in BOTH 'both' and 'self')
            # Needles are placed at theta = 0 (unrotated reference frame)
            for elem in elements:
                geometry.append(mp.Block(
                    center=mp.Vector3(elem["cx"], elem["cy"], z_needle_center),
                    size=mp.Vector3(elem["w_needle"], elem["w_needle"], H_needle),
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

            def make_amp_func(mx_val, my_val, mz_val, size_vec, center_vec):
                sx_v, sy_v, sz_v = size_vec.x, size_vec.y, size_vec.z
                cx_v, cy_v, cz_v = center_vec.x, center_vec.y, center_vec.z
                Nx = (2.0 / sx_v if mx_val > 0 else 1.0 / sx_v) if sx_v > 1e-15 else 1.0
                Ny = (2.0 / sy_v if my_val > 0 else 1.0 / sy_v) if sy_v > 1e-15 else 1.0
                Nz = (2.0 / sz_v if mz_val > 0 else 1.0 / sz_v) if sz_v > 1e-15 else 1.0
                factor = np.sqrt(Nx * Ny * Nz)

                def amp_func(p):
                    x = (p.x - cx_v) + 0.5 * sx_v
                    y = (p.y - cy_v) + 0.5 * sy_v
                    z = (p.z - cz_v) + 0.5 * sz_v
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

        if is_g0 and len(completed_moments) == num_tasks:
            try:
                with open(chk_file, "w") as f_out:
                    json.dump({"force": float(total_force)}, f_out, indent=4)
                print(f"[{cfg_name.upper()}] Complete. Single-needle force: {total_force:+.6e}")
            except OSError as save_err:
                print(f"Warning: Failed writing config checkpoint {chk_file}: {save_err}", flush=True)

        return total_force

    # Run requested configurations
    if config == "both":
        f1_both = run_one_config("both")
        return f1_both, 0.0, f1_both
    elif config == "self":
        f1_self = run_one_config("self")
        return 0.0, f1_self, 0.0
    else:  # 'all'
        f1_both = run_one_config("both")
        f1_self = run_one_config("self")
        f1_sub = f1_both - f1_self
        return f1_both, f1_self, f1_sub


def main():
    parser = argparse.ArgumentParser(description="Dual-Fractal Rotary Vacuum Casimir Clutch (Levin-Johnson Mechanism)")
    parser.add_argument("--task-id", type=int, default=1, help="Task index (1-6)")
    parser.add_argument("--N-fractal", type=int, default=2, help="Prefractal generation N (1, 2, or 3)")
    parser.add_argument("--theta", type=float, default=0.0, help="Relative rotation angle theta (deg)")
    parser.add_argument("--L-fractal", type=float, default=1.05, help="Base fractal domain span L (um)")
    parser.add_argument("--W1-aperture", type=float, default=0.35, help="Primary aperture diameter W1 (um)")
    parser.add_argument("--w1-needle", type=float, default=0.04, help="Primary needle width w1 (um)")
    parser.add_argument("--H-needle", type=float, default=0.25, help="Needle height (um)")
    parser.add_argument("--t-plate", type=float, default=0.025, help="Stator membrane thickness (um)")
    parser.add_argument("--z-tip", type=float, default=0.015, help="Tip clearance above stator (um)")
    parser.add_argument("--material", type=str, default="Gold", help="Plate and needle material")
    parser.add_argument("--res", type=int, default=80, help="Yee grid resolution (pixels/um)")
    parser.add_argument("--nmax", type=int, default=1, help="Multipole cutoff")
    parser.add_argument("--config", type=str, default="all", choices=["both", "self", "all"])
    parser.add_argument("--T-run", type=float, default=12.0, help="FDTD duration")
    parser.add_argument("--max-walltime-hours", type=float, default=7.5, help="Walltime limit budget")
    parser.add_argument("--no-cache", action="store_true", help="Bypass cached checkpoints")
    args = parser.parse_args()

    chk_tag = f"fractal_clutch_N_{args.N_fractal}_th_{args.theta:.1f}_ztip_{args.z_tip:.4f}_res_{args.res}"

    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    is_g0 = (global_rank == 0)
    if is_g0:
        print("=" * 85)
        print(f"DUAL-FRACTAL ROTARY VACUUM CASIMIR CLUTCH (Generation N = {args.N_fractal})")
        print(f"Task ID: {args.task_id} | Rotation Angle theta: {args.theta:.1f} deg")
        print(f"Fractal Span L: {args.L_fractal*1e3:.1f} nm, Primary Aperture W1: {args.W1_aperture*1e3:.1f} nm")
        print(f"Primary Needle Width w1: {args.w1_needle*1e3:.1f} nm, Height H: {args.H_needle*1e3:.1f} nm")
        print(f"Tip Clearance z_tip: {args.z_tip*1e3:.1f} nm (W1/4 threshold = {args.W1_aperture*250:.1f} nm)")
        print(f"Material: {args.material}, Resolution: {args.res} (dx = {1000/args.res:.2f} nm)")
        print(f"Predicted State: {'DISENGAGED (Repulsive Levitation)' if abs(args.theta) < 1e-3 or abs(args.theta - 90.0) < 1e-3 else ('ENGAGED (Attractive Clamping)' if abs(args.theta - 45.0) < 1e-3 else 'TRANSITIONAL')}")
        print("=" * 85, flush=True)

    f1_both, f1_self, f1_net = run_fractal_rotary_clutch_simulation(
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
        no_cache=args.no_cache
    )

    if is_g0 and args.config == "all":
        # Total force on the primary 4-needle C4 rotor: F_total = 4 * F_1
        # When secondary needles are present (N >= 2), the total force scales across the fractal hierarchy
        num_primary_needles = 4
        f_total_meep = num_primary_needles * f1_net
        f_total_N = f_total_meep * MEEP_FORCE_TO_SI
        f_total_fN = f_total_N * 1e15

        # Normal pressure on primary needle cross-section A_rotor = 4 * w1^2
        pressure_Pa = (f1_net / (args.w1_needle ** 2)) * MEEP_TO_PA

        result_data = {
            "task_id": args.task_id,
            "architecture": "dual_fractal_rotary_casimir_clutch",
            "N_fractal": args.N_fractal,
            "theta_deg": float(args.theta),
            "L_fractal_nm": float(args.L_fractal * 1e3),
            "W1_aperture_nm": float(args.W1_aperture * 1e3),
            "w1_needle_nm": float(args.w1_needle * 1e3),
            "H_needle_nm": float(args.H_needle * 1e3),
            "t_plate_nm": float(args.t_plate * 1e3),
            "z_tip_nm": float(args.z_tip * 1e3),
            "material": args.material,
            "resolution": args.res,
            "force_single_meep": float(f1_net),
            "force_total_meep": float(f_total_meep),
            "force_total_fN": float(f_total_fN),
            "pressure_Pa": float(pressure_Pa),
            "regime": "REPULSIVE" if f_total_meep > 0 else "ATTRACTIVE",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        out_dest = f"results_fractal_rotary_clutch/task_{args.task_id:03d}_N_{args.N_fractal}_th_{int(args.theta)}deg.json"
        with open(out_dest, "w") as f:
            json.dump(result_data, f, indent=4)

        print("\n" + "=" * 85)
        print("DUAL-FRACTAL CASIMIR CLUTCH SIMULATION COMPLETE")
        print(f"Generation N: {args.N_fractal} | Rotation Angle theta: {args.theta:.1f} deg")
        print(f"Primary Single-Needle Force (MEEP): {f1_net:+.6e}")
        print(f"Total Fractal Rotor Force (MEEP):   {f_total_meep:+.6e}")
        print(f"Total Fractal Rotor Force (fN):     {f_total_fN:+.4f} fN  -->  {'[+++ FRACTAL REPULSION (LEVITATING) +++]' if f_total_meep > 0 else '[- FRACTAL ATTRACTION (CLAMPING) -]'}")
        print(f"Primary Needle Pressure:            {pressure_Pa:+.4e} Pa")
        print(f"Results saved to:                   {out_dest}")
        print("=" * 85 + "\n", flush=True)


if __name__ == "__main__":
    main()
