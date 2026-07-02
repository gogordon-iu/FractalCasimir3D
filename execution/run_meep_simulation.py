import meep as mp
mp.quiet(True)
mp.verbosity(0)
import numpy as np
import ctypes
import argparse
import os
import json

def get_src_index(n):
    """Cantor pairing function decoder."""
    s = 0
    r = 0
    while s + r < n:
        r += 1
        s += r
    c = n - s
    return r - c, c

def get_effective_area(N, L):
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def generate_carpet_holes(N, L, center_x, center_y, size_z, material, theta=0.0):
    """
    Generates a list of mp.Block objects representing the air holes
    in a Sierpinski carpet prefractal plate, rotated by theta degrees in the xy-plane.
    """
    holes = []
    theta_rad = np.radians(theta)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)
    e1 = mp.Vector3(C, S, 0.0)
    e2 = mp.Vector3(-S, C, 0.0)
    e3 = mp.Vector3(0.0, 0.0, 1.0)
    
    def recurse(x, y, w, level):
        if level > N:
            return
        # Add the center hole for this level
        hole_w = w / 3.0
        # Rotate the relative center (x, y) by theta
        rx = x * C - y * S
        ry = x * S + y * C
        
        holes.append(mp.Block(
            center=mp.Vector3(rx, ry, 0.0) + mp.Vector3(center_x, center_y, 0.0),
            size=mp.Vector3(hole_w, hole_w, size_z),
            e1=e1,
            e2=e2,
            e3=e3,
            material=mp.vacuum
        ))
        
        # Recurse for the 8 surrounding squares
        if level < N:
            offsets = [-w/3.0, 0.0, w/3.0]
            for dx in offsets:
                for dy in offsets:
                    if dx == 0.0 and dy == 0.0:
                        continue
                    recurse(x + dx, y + dy, hole_w, level + 1)
                    
    if N > 1:
        recurse(0.0, 0.0, L, 2)
        
    return holes


def get_casimir_material(material_name, Sigma, ft, theta=0.0, eps_bg=1.0):
    """
    Constructs the MEEP Medium for the bottom or top plate.
    If ft == mp.E_stuff: D_conductivity = Sigma, and gamma is shifted by Sigma.
    If ft == mp.H_stuff: B_conductivity = Sigma, and gamma is unshifted.
    """
    if material_name == "PEC":
        cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}
        return mp.Medium(epsilon=-1e20, **cond_attr)
        
    if material_name == "Gold":
        from meep.materials import Au
        base_medium = Au
    elif material_name == "Silicon":
        from meep.materials import cSi
        base_medium = cSi
    elif material_name in ["Phosphorene", "Phosphorene_tuned"]:
        eps_x, eps_y, eps_z = 2.0, 1.5, 1.2
        sig_x, sig_y, sig_z = 3.0, 1.0, 2.0
        if material_name == "Phosphorene_tuned":
            eps_z = eps_bg  # Tuned dynamically to match background eps_bg
            sig_z = 0.0  # Zero out out-of-plane dispersion to eliminate z-attraction
        f0 = 1.5
        gamma_p = 0.1
        
        # Rotate by theta
        theta_rad = np.radians(theta)
        C = np.cos(theta_rad)
        S = np.sin(theta_rad)
        
        # Rotated epsilon
        eps_xx = eps_x * C**2 + eps_y * S**2
        eps_yy = eps_x * S**2 + eps_y * C**2
        eps_zz = eps_z
        eps_xy = (eps_x - eps_y) * S * C
        
        # Rotated susceptibility sigma
        sig_xx = sig_x * C**2 + sig_y * S**2
        sig_yy = sig_x * S**2 + sig_y * C**2
        sig_zz = sig_z
        sig_xy = (sig_x - sig_y) * S * C
        
        gamma_val = gamma_p + Sigma if ft == mp.E_stuff else gamma_p
        cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}
        
        return mp.Medium(
            epsilon_diag=mp.Vector3(eps_xx, eps_yy, eps_zz),
            epsilon_offdiag=mp.Vector3(eps_xy, 0.0, 0.0),
            E_susceptibilities=[
                mp.LorentzianSusceptibility(
                    frequency=f0,
                    gamma=gamma_val,
                    sigma_diag=mp.Vector3(sig_xx, sig_yy, sig_zz),
                    sigma_offdiag=mp.Vector3(sig_xy, 0.0, 0.0)
                )
            ],
            **cond_attr
        )
    else:
        raise ValueError(f"Unknown material: {material_name}")

    # For Au and cSi:
    if material_name in ["Gold", "Silicon"]:
        new_sus = []
        for sus in base_medium.E_susceptibilities:
            freq = sus.frequency
            gamma = sus.gamma
            gamma_val = gamma + Sigma if ft == mp.E_stuff else gamma
            if isinstance(sus, mp.DrudeSusceptibility):
                # Rescale to avoid numerical overflow/underflow with 1e-10 frequency and 4e21 sigma
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
        cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}
        return mp.Medium(
            epsilon=base_medium.epsilon_diag.x,
            E_susceptibilities=new_sus,
            **cond_attr
        )

    # For general anisotropic materials (Phosphorene):
    theta_rad = np.radians(theta)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)
    
    eps_diag = base_medium.epsilon_diag
    
    eps_xx = eps_diag.x * C**2 + eps_diag.y * S**2
    eps_yy = eps_diag.x * S**2 + eps_diag.y * C**2
    eps_zz = eps_diag.z
    eps_xy = (eps_diag.x - eps_diag.y) * S * C
    
    new_sus = []
    for sus in base_medium.E_susceptibilities:
        freq = sus.frequency
        gamma = sus.gamma
        gamma_val = gamma + Sigma if ft == mp.E_stuff else gamma
        
        sig_diag = sus.sigma_diag
        sig_xx = sig_diag.x * C**2 + sig_diag.y * S**2
        sig_yy = sig_diag.x * S**2 + sig_diag.y * C**2
        sig_zz = sig_diag.z
        sig_xy = (sig_diag.x - sig_diag.y) * S * C
        
        if isinstance(sus, mp.DrudeSusceptibility):
            new_sus.append(mp.DrudeSusceptibility(
                frequency=freq,
                gamma=gamma_val,
                sigma_diag=mp.Vector3(sig_xx, sig_yy, sig_zz),
                sigma_offdiag=mp.Vector3(sig_xy, 0.0, 0.0)
            ))
        elif isinstance(sus, mp.LorentzianSusceptibility):
            new_sus.append(mp.LorentzianSusceptibility(
                frequency=freq,
                gamma=gamma_val,
                sigma_diag=mp.Vector3(sig_xx, sig_yy, sig_zz),
                sigma_offdiag=mp.Vector3(sig_xy, 0.0, 0.0)
            ))
            
    cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}
    return mp.Medium(
        epsilon_diag=mp.Vector3(eps_xx, eps_yy, eps_zz),
        epsilon_offdiag=mp.Vector3(eps_xy, 0.0, 0.0),
        E_susceptibilities=new_sus,
        **cond_attr
    )

def get_optimal_subgroups(M, num_tasks):
    """
    Finds the largest divisor of M that is less than or equal to num_tasks,
    while ensuring each subgroup has at least 8 processes (or M if M < 8)
    to prevent memory bandwidth starvation.
    """
    min_cores_per_subgroup = 8
    max_K = max(1, M // min_cores_per_subgroup)
    
    divisors = [i for i in range(1, M + 1) if M % i == 0]
    valid_divisors = [d for d in divisors if d <= num_tasks and d <= max_K]
    if not valid_divisors:
        return 1
    return max(valid_divisors)


def run_simulation(d, N, material, resolution, n_max=5, config="both", theta=0.0, eps_bg=1.0, subgroup_index=0, K=1, T_run=30.0, task_idx_override=-1, L=0.3):
    """
    Runs a 3D FDTD simulation for a single configuration, utilizing subgroups
    to run different polarizations and moments in parallel.
    """
    # 1. Computational Cell and Geometry parameters
    t_plate = 0.1  # plate thickness in microns
    dpml = 0.2  # PML thickness in microns
    buffer = 0.15  # buffer between plates and PML
    
    # Cell size
    sx = L + 2.0 * (dpml + buffer)
    sy = L + 2.0 * (dpml + buffer)
    sz = d + 2.0 * t_plate + 2.0 * (dpml + buffer)
    
    cell_size = mp.Vector3(sx, sy, sz)
    
    # Global conductivity scaling
    Sigma = 0.5 / d
    
    pol_list = [mp.Ex, mp.Ey, mp.Ez, mp.Hx, mp.Hy, mp.Hz]
    component_direction = {
        mp.Ex: mp.X, mp.Ey: mp.Y, mp.Ez: mp.Z,
        mp.Dx: mp.X, mp.Dy: mp.Y, mp.Dz: mp.Z,
        mp.Hx: mp.X, mp.Hy: mp.Y, mp.Hz: mp.Z,
        mp.Bx: mp.X, mp.By: mp.Y, mp.Bz: mp.Z
    }
    
    # Integration surface S enclosing the prefractal plate
    delta_s = 0.03
    sx_box = L + 2.0 * delta_s
    sy_box = L + 2.0 * delta_s
    sz_box = t_plate + 2.0 * delta_s
    center_z = d/2.0 + t_plate/2.0
    
    # 6 sides of S
    sides_info = [
        {"center": mp.Vector3(-sx_box/2.0, 0.0, center_z), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(sx_box/2.0, 0.0, center_z), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": 1.0},
        {"center": mp.Vector3(0.0, -sy_box/2.0, center_z), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(0.0, sy_box/2.0, center_z), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": 1.0},
        {"center": mp.Vector3(0.0, 0.0, center_z - sz_box/2.0), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": -1.0},
        {"center": mp.Vector3(0.0, 0.0, center_z + sz_box/2.0), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": 1.0}
    ]
    
    total_force = 0.0
    num_tasks = 36 * n_max
    
    
    # Each subgroup runs its assigned slice of tasks in parallel
    if task_idx_override >= 0:
        tasks_to_run = [task_idx_override]
    else:
        tasks_to_run = list(range(subgroup_index, num_tasks, K))
        
    for task_idx in tasks_to_run:
        p = task_idx // (n_max * 6)
        n = task_idx % (n_max * 6)
        
        curr_pol = pol_list[p]
        ft = mp.E_stuff if curr_pol in [mp.Ex, mp.Ey, mp.Ez] else mp.H_stuff
        
        # Setup materials with appropriate conductivity added
        bottom_plate_material = get_casimir_material(material, Sigma, ft, theta=0.0, eps_bg=eps_bg)
        top_plate_material = get_casimir_material(material, Sigma, ft, theta=theta, eps_bg=eps_bg)
        
        if ft == mp.E_stuff:
            bg_material = mp.Medium(epsilon=eps_bg, D_conductivity=Sigma)
        else:
            bg_material = mp.Medium(epsilon=eps_bg, B_conductivity=Sigma)
                
        # Geometry list
        geometry = []
        if config == "both":
            geometry.append(mp.Block(
                center=mp.Vector3(0.0, 0.0, -d/2.0 - t_plate/2.0),
                size=mp.Vector3(L, L, t_plate),
                material=bottom_plate_material
            ))
            
        if config != "vacuum":
            theta_rad = np.radians(theta)
            C = np.cos(theta_rad)
            S = np.sin(theta_rad)
            e1 = mp.Vector3(C, S, 0.0)
            e2 = mp.Vector3(-S, C, 0.0)
            e3 = mp.Vector3(0.0, 0.0, 1.0)
            
            geometry.append(mp.Block(
                center=mp.Vector3(0.0, 0.0, d/2.0 + t_plate/2.0),
                size=mp.Vector3(L, L, t_plate),
                e1=e1,
                e2=e2,
                e3=e3,
                material=top_plate_material
            ))
            # Subtract holes recursively
            holes = generate_carpet_holes(N, L, 0.0, 0.0, t_plate + 0.01, top_plate_material, theta=theta)
            for hole in holes:
                hole.center = mp.Vector3(hole.center.x, hole.center.y, d/2.0 + t_plate/2.0)
            geometry.extend(holes)
            
        # Setup Simulation on the subgroup communicator
        sim = mp.Simulation(
            cell_size=cell_size,
            geometry=geometry,
            resolution=resolution,
            boundary_layers=[mp.PML(dpml)],
            default_material=bg_material,
            Courant=0.1,
            eps_averaging=True
        )
        
        sim.init_sim()
        dt = sim.Courant / resolution
        T_steps = int(T_run / dt)
        
        # Calculate Green's function time-kernel g(t)
        gt = mp.make_casimir_gfunc(T_run, dt, Sigma, curr_pol)
        addr = int(gt)
        double_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))
        data = np.ctypeslib.as_array(double_ptr, shape=(T_steps * 2,))
        gt_arr = data[0::2] + 1j * data[1::2]
        
        # Process the specific moment and side
        s = n % 6
        nr = n // 6
        m1, m2 = get_src_index(nr)
        
        side = sides_info[s]
        side_center = side["center"]
        side_size = side["size"]
        side_orientation = side["orientation"]
        
        # Map DCT indices based on normal direction
        if s in [0, 1]:  # x-const
            mx, my, mz = 0, m1, m2
        elif s in [2, 3]:  # y-const
            mx, my, mz = m1, 0, m2
        else:  # z-const
            mx, my, mz = m1, m2, 0
            
        # Setup cosine modulation amplitude function
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
            
        # Create source modulation
        src_vol = mp.Volume(center=side_center, size=side_size, dims=3)
        
        sim.change_sources([
            mp.Source(
                src=mp.CustomSource(src_func=lambda t: 1.0/dt, start_time=-0.25*dt, end_time=0.75*dt),
                component=curr_pol,
                center=side_center,
                size=side_size,
                amp_func=make_amp_func(mx, my, mz, side_size)
            )
        ])
        
        sim.reset_meep()
        sim.init_sim()
        
        # Step and integrate
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
        
    # If K is 1 (non-MPI mode or single subgroup), return total_force immediately
    if K == 1:
        return total_force

    # Sum the force over all subgroups using MPI reduction or file-based aggregation fallback
    try:
        from mpi4py import MPI
        comm = MPI.COMM_WORLD
        global_force_sum = comm.allreduce(total_force, op=MPI.SUM)
        subgroup_size = comm.Get_size() / K
        final_force = global_force_sum / subgroup_size
    except ImportError:
        import time
        global_rank = int(os.environ.get("SLURM_PROCID", 0))
        
        # Subgroup master writes its total_force
        if mp.am_master():
            os.makedirs(".tmp", exist_ok=True)
            temp_file = f".tmp/temp_force_{config}_subgroup_{subgroup_index}.json"
            with open(temp_file, "w") as f:
                json.dump({"force": float(total_force)}, f)
                
        # Global rank 0 waits and sums
        if global_rank == 0:
            final_force = 0.0
            for i in range(K):
                temp_file = f".tmp/temp_force_{config}_subgroup_{i}.json"
                while not os.path.exists(temp_file):
                    time.sleep(0.5)
                success = False
                while not success:
                    try:
                        with open(temp_file, "r") as f:
                            data = json.load(f)
                            final_force += data["force"]
                        success = True
                    except (json.JSONDecodeError, PermissionError):
                        time.sleep(0.1)
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
        else:
            final_force = 0.0
            
    return final_force


def main():
    parser = argparse.ArgumentParser(description="Run 3D MEEP Casimir FDTD simulation.")
    parser.add_argument("--d", type=float, required=True, help="Plate separation in microns.")
    parser.add_argument("--N", type=int, required=True, help="Prefractal generation (1-4).")
    parser.add_argument("--material", type=str, required=True, choices=["PEC", "Gold", "Silicon", "Phosphorene", "Phosphorene_tuned"], help="Material configuration.")
    parser.add_argument("--res", type=int, default=10, help="Grid resolution.")
    parser.add_argument("--nmax", type=int, default=3, help="Max moments index limit.")
    parser.add_argument("--theta", type=float, default=0.0, help="Twist angle of top plate in degrees.")
    parser.add_argument("--eps-bg", type=float, default=1.0, help="Dielectric constant of the background medium.")
    parser.add_argument("--T-run", type=float, default=30.0, help="Total simulation runtime in dimensionless time units.")
    parser.add_argument("--config", type=str, default="all", choices=["both", "self", "all"], help="Simulation configuration (both plates, self plate only, or all).")
    parser.add_argument("--task-idx", type=int, default=-1, help="Specific task index to run (0-35). If -1, run all using subgroups.")
    parser.add_argument("--L", type=float, default=0.3, help="Plate width/length in microns.")
    args = parser.parse_args()
    
    # Calculate number of tasks and setup parallel subgroups
    # Use mp.count_processors() to check the actual number of MPI processes initialized by Meep
    M = mp.count_processors()
    num_tasks = 36 * args.nmax
    
    if args.task_idx >= 0:
        # If running a single task, we disable subgroup division (K=1, subgroup_index=0)
        K = 1
        subgroup_index = 0
    else:
        K = get_optimal_subgroups(M, num_tasks)
        subgroup_index = 0
        if K > 1:
            subgroup_index = mp.divide_parallel_processes(K)
        
    # We check if we are the global master (global rank 0) to print and write files
    global_rank = 0
    try:
        from mpi4py import MPI
        global_rank = MPI.COMM_WORLD.Get_rank()
    except ImportError:
        global_rank = int(os.environ.get("SLURM_PROCID", 0))
        
    if global_rank == 0:
        print(f"Starting simulation: d={args.d} um, N={args.N}, material={args.material}, resolution={args.res}, nmax={args.nmax}, theta={args.theta}, eps_bg={args.eps_bg}, config={args.config}")
        print(f"Parallel configuration: {M} processes divided into {K} subgroups of size {M//K} processes each.")
    
    # We run the cases for vacuum subtraction:
    f_both = 0.0
    f_self = 0.0
    
    if args.config in ["all", "both"]:
        f_both = run_simulation(args.d, args.N, args.material, args.res, args.nmax, config="both", theta=args.theta, eps_bg=args.eps_bg, subgroup_index=subgroup_index, K=K, T_run=args.T_run, task_idx_override=args.task_idx, L=args.L)
    if args.config in ["all", "self"]:
        f_self = run_simulation(args.d, args.N, args.material, args.res, args.nmax, config="self", theta=args.theta, eps_bg=args.eps_bg, subgroup_index=subgroup_index, K=K, T_run=args.T_run, task_idx_override=args.task_idx, L=args.L)
        
    # Save output to .tmp folder
    if global_rank == 0:
        os.makedirs(".tmp", exist_ok=True)
        if args.task_idx >= 0:
            if args.config == "all":
                out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}_task_{args.task_idx}.json"
                result = {
                    "d_um": args.d,
                    "N": args.N,
                    "material": args.material,
                    "resolution": args.res,
                    "theta_deg": args.theta,
                    "eps_bg": args.eps_bg,
                    "L": args.L,
                    "task_idx": args.task_idx,
                    "force_both": float(f_both),
                    "force_self": float(f_self)
                }
            else:
                out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}_config_{args.config}_task_{args.task_idx}.json"
                result = {
                    "d_um": args.d,
                    "N": args.N,
                    "material": args.material,
                    "resolution": args.res,
                    "theta_deg": args.theta,
                    "eps_bg": args.eps_bg,
                    "L": args.L,
                    "config": args.config,
                    "task_idx": args.task_idx,
                    "force": float(f_both if args.config == "both" else f_self)
                }
        else:
            if args.config == "all":
                out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}.json"
                result = {
                    "d_um": args.d,
                    "N": args.N,
                    "material": args.material,
                    "resolution": args.res,
                    "theta_deg": args.theta,
                    "eps_bg": args.eps_bg,
                    "L": args.L,
                    "force_both": float(f_both),
                    "force_self": float(f_self),
                    "force_subtracted": float(f_both - f_self)
                }
            else:
                out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}_config_{args.config}.json"
                result = {
                    "d_um": args.d,
                    "N": args.N,
                    "material": args.material,
                    "resolution": args.res,
                    "theta_deg": args.theta,
                    "eps_bg": args.eps_bg,
                    "L": args.L,
                    f"force_{args.config}": float(f_both if args.config == "both" else f_self)
                }
        
        with open(out_file, "w") as f:
            json.dump(result, f, indent=4)
            
        if args.config == "all":
            if args.task_idx >= 0:
                print(f"Simulation task complete. Saved to {out_file}")
            else:
                print(f"Simulation complete. Subtracted force: {f_both - f_self:.6e}. Saved to {out_file}")
        else:
            if args.task_idx >= 0:
                print(f"Simulation task complete. Saved to {out_file}")
            else:
                print(f"Simulation complete. {args.config} force: {f_both if args.config == 'both' else f_self:.6e}. Saved to {out_file}")

if __name__ == "__main__":
    main()
