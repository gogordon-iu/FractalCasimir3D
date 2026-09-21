import sys
import os

# Guarantee repository root is in sys.path across all Slurm nodes/ranks
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import meep as mp
mp.verbosity(0)
import numpy as np
import ctypes
import argparse
import json
import time

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

def generate_carpet_holes(N, L, center_x, center_y, size_z, material=None, theta=0.0):
    """
    Generates a list of mp.Block objects representing the holes
    in a Sierpinski carpet prefractal plate, rotated by theta degrees in the xy-plane.
    Holes are filled with material (bg_material or mp.vacuum).
    """
    holes = []
    theta_rad = np.radians(theta)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)
    e1 = mp.Vector3(C, S, 0.0)
    e2 = mp.Vector3(-S, C, 0.0)
    e3 = mp.Vector3(0.0, 0.0, 1.0)
    hole_mat = mp.vacuum if material is None else material
    
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
            material=hole_mat
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


def generate_stepped_sieve_holes(N, L, center_x, center_y, depths, top_z, theta=0.0, material=None):
    """
    Generates 3D stepped cavity wells for the bottom plate (Frontier 1: Stepped Fractal Sieve).
    depths: list of depths for level 2 (macro), level 3 (medium), level 4 (micro), etc. in microns.
    top_z: the z-coordinate of the top surface of the bottom plate (-d/2).
    Cavities are filled with material (bg_material or mp.vacuum).
    """
    holes = []
    theta_rad = np.radians(theta)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)
    e1 = mp.Vector3(C, S, 0.0)
    e2 = mp.Vector3(-S, C, 0.0)
    e3 = mp.Vector3(0.0, 0.0, 1.0)
    hole_mat = mp.vacuum if material is None else material
    
    def recurse(x, y, w, level):
        if level > N:
            return
        hole_w = w / 3.0
        idx = level - 2
        h = depths[idx] if idx < len(depths) else depths[-1]
        
        rx = x * C - y * S
        ry = x * S + y * C
        
        # Etch a cavity box of depth h into the bottom plate starting from top_z
        holes.append(mp.Block(
            center=mp.Vector3(rx + center_x, ry + center_y, top_z - h / 2.0),
            size=mp.Vector3(hole_w, hole_w, h + 0.001),
            e1=e1,
            e2=e2,
            e3=e3,
            material=hole_mat
        ))
        
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


def generate_fractal_corrugations(N, L, center_x, center_y, base_z, is_top_plate=False, angle=45.0, theta=0.0, max_depth=None, material=None, r_tip=0.0):
    """
    Generates 3D Fractal Corrugations (Frontier 2) with sloped walls and optional tip rounding.
    For bottom plate (is_top_plate=False): carves V-groove pyramids downward into the substrate starting at base_z (-d/2).
    For top plate (is_top_plate=True): carves V-groove pyramids upward into the top plate starting at base_z (+d/2),
    rotated by angle theta in the xy-plane so corrugations rotate rigidly with the plate.
    When r_tip > 0, delegates to generate_rounded_pyramid_corrugations for spherical apex profiling.
    Both plates preserve a clear gap between -d/2 and +d/2, ensuring the stress tensor integration box never slices any material.
    """
    if r_tip > 0.0:
        from execution.edge_rounding_geometry import generate_rounded_pyramid_corrugations
        return generate_rounded_pyramid_corrugations(
            N, L, center_x, center_y, base_z, is_top_plate=is_top_plate,
            angle=angle, r_tip=r_tip, theta=theta, max_depth=max_depth, material=material
        )

    shapes = []
    tan_angle = np.tan(np.radians(angle))
    theta_rad = np.radians(theta)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)
    e1 = mp.Vector3(C, S, 0.0)
    e2 = mp.Vector3(-S, C, 0.0)
    e3 = mp.Vector3(0.0, 0.0, 1.0)
    carve_mat = mp.vacuum if material is None else material
    
    def recurse(x, y, w, level):
        if level > N:
            return
        w_hole = w / 3.0
        h_pyramid = (w_hole / 2.0) * tan_angle
        if max_depth is not None:
            h_pyramid = min(h_pyramid, max_depth)
        
        num_slices = 10
        dz = h_pyramid / num_slices
        
        for k in range(num_slices):
            frac = (k + 0.5) / num_slices
            if is_top_plate:
                # Top plate V-groove is carved UPWARD into the top plate starting at base_z (+d/2)
                # Slices taper from width w_hole at base_z to 0 at base_z + h_pyramid
                slice_w = w_hole * (1.0 - frac)
                slice_z = base_z + (frac * h_pyramid)
                rx = x * C - y * S
                ry = x * S + y * C
                shapes.append(mp.Block(
                    center=mp.Vector3(rx + center_x, ry + center_y, slice_z),
                    size=mp.Vector3(max(slice_w, 1e-4), max(slice_w, 1e-4), dz + 0.001),
                    e1=e1,
                    e2=e2,
                    e3=e3,
                    material=carve_mat
                ))
            else:
                # Bottom plate V-groove is carved DOWNWARD into the substrate starting at base_z (-d/2)
                slice_w = w_hole * frac
                slice_z = base_z - ((1.0 - frac) * h_pyramid)
                rx = x * C - y * S
                ry = x * S + y * C
                shapes.append(mp.Block(
                    center=mp.Vector3(rx + center_x, ry + center_y, slice_z),
                    size=mp.Vector3(max(slice_w, 1e-4), max(slice_w, 1e-4), dz + 0.001),
                    e1=e1,
                    e2=e2,
                    e3=e3,
                    material=carve_mat
                ))
                
        if level < N:
            offsets = [-w/3.0, 0.0, w/3.0]
            for dx in offsets:
                for dy in offsets:
                    if dx == 0.0 and dy == 0.0:
                        continue
                    recurse(x + dx, y + dy, w_hole, level + 1)
                    
    if N > 1:
        recurse(0.0, 0.0, L, 2)
        
    return shapes

def get_casimir_material(material_name, Sigma, ft, theta=0.0, eps_bg=1.0):
    """
    Constructs the MEEP Medium for the bottom or top plate.
    If ft == mp.E_stuff: D_conductivity = Sigma, and gamma is shifted by Sigma.
    If ft == mp.H_stuff: B_conductivity = Sigma, and gamma is unshifted.
    """
    if material_name == "PEC":
        cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}
        return mp.Medium(epsilon=-1e20, **cond_attr)

    if material_name in ["BlackPhosphorus", "ReS2", "BP_realistic"]:
        from execution.materials_database_dispersive import get_meep_dispersive_medium
        return get_meep_dispersive_medium(material_name, Sigma, ft, theta_deg=theta)
        
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
        
        # Rotated susceptibility oscillator strength
        sig_xx = sig_x * C**2 + sig_y * S**2
        sig_yy = sig_x * S**2 + sig_y * C**2
        sig_zz = sig_z
        sig_xy = (sig_x - sig_y) * S * C
        
        gamma_val = gamma_p + Sigma if ft == mp.E_stuff else gamma_p
        cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}
        
        # In MEEP, susceptibility tensor rotation is handled via sigma_offdiag and epsilon_offdiag
        sus = mp.LorentzianSusceptibility(
            frequency=f0,
            gamma=gamma_val,
            sigma_diag=mp.Vector3(sig_xx, sig_yy, sig_zz),
            sigma_offdiag=mp.Vector3(sig_xy, 0.0, 0.0)
        )

        return mp.Medium(
            epsilon_diag=mp.Vector3(eps_xx, eps_yy, eps_zz),
            epsilon_offdiag=mp.Vector3(eps_xy, 0.0, 0.0),
            E_susceptibilities=[sus],
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

def get_optimal_subgroups(M, num_tasks, max_safe_K=None):
    """
    Finds the largest divisor of M that is less than or equal to num_tasks,
    while ensuring each subgroup has at least 16 processes (or M if M < 16)
    and does not exceed memory constraints.
    """
    min_cores_per_subgroup = 16
    max_K = max(1, M // min_cores_per_subgroup)
    if max_safe_K is not None:
        max_K = min(max_K, max_safe_K)
        max_K = max(1, max_K)
    
    divisors = [i for i in range(1, M + 1) if M % i == 0]
    valid_divisors = [d for d in divisors if d <= num_tasks and d <= max_K]
    if not valid_divisors:
        return 1
    return max(valid_divisors)


def compute_plate_thicknesses(clutch=False, corrugated=False, corrugation_angle=45.0, stepped_sieve=False):
    """
    Computes physical plate thicknesses from geometry parameters:
    - Top plate: active fractal structure height + backing substrate slab.
    - Bottom plate: membrane or perforated substrate thickness.
    """
    if clutch:
        H_spire = 0.20  # Spire height (microns)
        t_top_slab = 0.10  # Backing substrate slab (microns)
        t_top = H_spire + t_top_slab
        t_bottom = 0.05  # Perforated sieve membrane (microns)
    elif corrugated:
        H_corr = 0.75 if corrugation_angle >= 60.0 else 0.50
        t_top = H_corr
        t_bottom = H_corr
        H_spire = 0.0
        t_top_slab = 0.0
    elif stepped_sieve:
        t_top = 0.10
        t_bottom = 0.40
        H_spire = 0.0
        t_top_slab = 0.0
    else:
        t_top = 0.10
        t_bottom = 0.10
        H_spire = 0.0
        t_top_slab = 0.0
    return t_top, t_bottom, H_spire, t_top_slab


def compute_domain_dimensions(L, theta, d, t_top, t_bottom, dpml=0.20, buffer=0.15, clutch=False):
    """
    Calculates 3D cell bounds (sx, sy, sz) and integration standoffs (delta_s_xy, delta_s_z).
    Integration box bottom face is placed at the exact mathematical midpoint of gap d (z = 0)
    via delta_s_z = d / 2.0, providing equal vacuum clearance to both plates.
    """
    theta_rad = np.radians(theta)
    L_rot = L * (abs(np.cos(theta_rad)) + abs(np.sin(theta_rad)))
    
    # Delta standoff: delta_s_z = d / 2.0 centers the bottom face of S exactly at z = 0
    delta_s_xy = 0.03
    delta_s_z = d / 2.0
    
    sx = L_rot + 2.0 * (dpml + buffer)
    sy = sx
    
    if clutch:
        z_top_max = d / 2.0 + t_top + delta_s_z
        sz = 2.0 * z_top_max + 2.0 * (dpml + buffer)
    else:
        sz = d + t_top + t_bottom + 2.0 * (dpml + buffer)
        
    return sx, sy, sz, delta_s_xy, delta_s_z, L_rot


def run_simulation(d, N, material, resolution, n_max=5, config="both", theta=0.0, eps_bg=1.0, subgroup_index=0, K=1, T_run=12.0, task_idx_override=-1, L=0.3, moment_start=0, moment_end=108, N_bottom=1, stepped_sieve=False, sieve_depths=[0.30, 0.15, 0.05], corrugated=False, corrugation_angle=45.0, r_tip=0.0, medium=None, clutch=False, task_chk_tag=None, max_walltime_hours=11.0, no_cache=False):
    """
    Runs a 3D FDTD simulation for a single configuration, utilizing subgroups
    to run different polarizations and moments in parallel.
    Features granular per-moment checkpointing and walltime budget limit guarding.
    """
    # 1. Computational Cell and Geometry parameters
    t_top, t_bottom, H_spire, t_top_slab = compute_plate_thicknesses(
        clutch=clutch, corrugated=corrugated, corrugation_angle=corrugation_angle, stepped_sieve=stepped_sieve
    )
    dpml = 0.2  # PML thickness in microns
    buffer = 0.15  # buffer between plates and PML
    
    sx, sy, sz, delta_s_xy, delta_s_z, L_rot = compute_domain_dimensions(
        L, theta, d, t_top, t_bottom, dpml=dpml, buffer=buffer, clutch=clutch
    )
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
    
    # Integration surface S enclosing the top prefractal plate
    sx_box = L_rot + 2.0 * delta_s_xy
    sy_box = L_rot + 2.0 * delta_s_xy
    sz_box = t_top + 2.0 * delta_s_z
    center_z = d/2.0 + t_top/2.0
    
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
    is_g0 = (int(os.environ.get("SLURM_PROCID", 0)) == 0)
    
    # Checkpoint & walltime tracking setup
    start_time = time.time()
    max_walltime_sec = (max_walltime_hours * 3600.0) if (max_walltime_hours is not None and max_walltime_hours > 0) else None
    moments_chk_file = None
    completed_moments = {}
    
    if task_chk_tag:
        moments_chk_file = f".tmp/chk_moments_{task_chk_tag}_{config}.json"
        if os.path.exists(moments_chk_file) and not no_cache:
            try:
                with open(moments_chk_file, "r") as f_chk:
                    chk_data = json.load(f_chk)
                completed_moments = {int(k): float(v) for k, v in chk_data.get("completed_moments", {}).items()}
                if is_g0:
                    print(f"[{config.upper()}] Loaded {len(completed_moments)} cached moments from {moments_chk_file}", flush=True)
            except Exception as chk_err:
                if is_g0:
                    print(f"Warning: Corrupted moments checkpoint {moments_chk_file} ({chk_err}). Starting fresh.", flush=True)
                completed_moments = {}
    
    # Each subgroup runs its assigned slice of tasks in parallel
    if task_idx_override >= 0:
        tasks_to_run = [task_idx_override]
    else:
        tasks_to_run = [t for t in list(range(subgroup_index, num_tasks, K)) if moment_start <= t < moment_end]
        
    all_completed = True
    for cur_idx, task_idx in enumerate(tasks_to_run):
        # 1. Skip if already completed in checkpoint
        if task_idx in completed_moments:
            force_val = completed_moments[task_idx]
            total_force += force_val
            if is_g0:
                print(f"  [{config.upper()}][Rank {subgroup_index}] Skipped moment {cur_idx+1}/{len(tasks_to_run)} (task {task_idx}) [CACHED]: force_integral={force_val:+.6e}", flush=True)
            continue
            
        # 2. Check walltime guard before starting next moment
        if max_walltime_sec is not None:
            elapsed_sec = time.time() - start_time
            if elapsed_sec >= max_walltime_sec:
                if is_g0:
                    print(f"\n[WALLTIME GUARD] Elapsed {elapsed_sec/3600:.2f}h >= budget limit ({max_walltime_hours:.2f}h).", flush=True)
                    print(f"[WALLTIME GUARD] Safely pausing simulation before moment {cur_idx+1}/{len(tasks_to_run)} (task {task_idx}).", flush=True)
                all_completed = False
                break
                
        p = task_idx // (n_max * 6)
        n = task_idx % (n_max * 6)
        
        curr_pol = pol_list[p]
        ft = mp.E_stuff if curr_pol in [mp.Ex, mp.Ey, mp.Ez] else mp.H_stuff
        
        # Setup materials with appropriate conductivity added
        bottom_plate_material = get_casimir_material(material, Sigma, ft, theta=0.0, eps_bg=eps_bg)
        top_plate_material = get_casimir_material(material, Sigma, ft, theta=theta, eps_bg=eps_bg)
        
        if medium is not None and medium not in ["Vacuum", "None"]:
            from execution.materials_database_dispersive import get_meep_dispersive_medium
            bg_material = get_meep_dispersive_medium(medium, Sigma, ft)
        else:
            if ft == mp.E_stuff:
                bg_material = mp.Medium(epsilon=eps_bg, D_conductivity=Sigma)
            else:
                bg_material = mp.Medium(epsilon=eps_bg, B_conductivity=Sigma)
                
        # Geometry list
        geometry = []
        if config == "both":
            geometry.append(mp.Block(
                center=mp.Vector3(0.0, 0.0, -d/2.0 - t_bottom/2.0),
                size=mp.Vector3(L, L, t_bottom),
                material=bottom_plate_material
            ))
            if clutch:
                from execution.fractal_clutch_geometry import generate_anisotropic_sieve_apertures
                slots_bottom = generate_anisotropic_sieve_apertures(
                    N_bottom, L, d, t_bottom=t_bottom, material=bg_material
                )
                geometry.extend(slots_bottom)
            elif corrugated:
                corrugations_bottom = generate_fractal_corrugations(
                    N_bottom, L, 0.0, 0.0, -d/2.0, is_top_plate=False,
                    angle=corrugation_angle, theta=0.0,
                    max_depth=0.85 * t_bottom, material=bg_material, r_tip=r_tip
                )
                geometry.extend(corrugations_bottom)
            elif stepped_sieve:
                holes_bottom = generate_stepped_sieve_holes(N_bottom, L, 0.0, 0.0, sieve_depths, -d/2.0, theta=0.0, material=bg_material)
                geometry.extend(holes_bottom)
            elif N_bottom > 1:
                holes_bottom = generate_carpet_holes(N_bottom, L, 0.0, 0.0, t_bottom + 0.01, material=bg_material, theta=0.0)
                for hole in holes_bottom:
                    hole.center = mp.Vector3(hole.center.x, hole.center.y, -d/2.0 - t_bottom/2.0)
                geometry.extend(holes_bottom)
            
        if config != "vacuum":
            theta_rad = np.radians(theta)
            C = np.cos(theta_rad)
            S = np.sin(theta_rad)
            e1 = mp.Vector3(C, S, 0.0)
            e2 = mp.Vector3(-S, C, 0.0)
            e3 = mp.Vector3(0.0, 0.0, 1.0)
            
            if clutch:
                from execution.fractal_clutch_geometry import generate_menger_spire_array
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, d/2.0 + H_spire + t_top_slab/2.0),
                    size=mp.Vector3(L, L, t_top_slab),
                    e1=e1,
                    e2=e2,
                    e3=e3,
                    material=top_plate_material
                ))
                spires_top = generate_menger_spire_array(
                    N, L, d, H_spire=H_spire, alpha=corrugation_angle,
                    r_tip=r_tip, theta=theta, material=top_plate_material
                )
                geometry.extend(spires_top)
            else:
                geometry.append(mp.Block(
                    center=mp.Vector3(0.0, 0.0, d/2.0 + t_top/2.0),
                    size=mp.Vector3(L, L, t_top),
                    e1=e1,
                    e2=e2,
                    e3=e3,
                    material=top_plate_material
                ))
                if corrugated:
                    corrugations_top = generate_fractal_corrugations(
                        N, L, 0.0, 0.0, d/2.0, is_top_plate=True,
                        angle=corrugation_angle, theta=theta,
                        max_depth=0.85 * t_top, material=bg_material, r_tip=r_tip
                    )
                    geometry.extend(corrugations_top)
                elif N > 1:
                    # Subtract holes recursively
                    holes = generate_carpet_holes(N, L, 0.0, 0.0, t_top + 0.01, material=bg_material, theta=theta)
                    for hole in holes:
                        hole.center = mp.Vector3(hole.center.x, hole.center.y, d/2.0 + t_top/2.0)
                    geometry.extend(holes)
            
        # Setup Simulation on the subgroup communicator
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
        completed_moments[task_idx] = float(force_integral)
        
        # Atomically save updated moments checkpoint on Rank 0
        if is_g0 and moments_chk_file:
            os.makedirs(os.path.dirname(moments_chk_file) or ".", exist_ok=True)
            tmp_chk_path = f"{moments_chk_file}.tmp_{os.getpid()}"
            try:
                with open(tmp_chk_path, "w") as f_chk:
                    json.dump({
                        "task_chk_tag": task_chk_tag,
                        "config": config,
                        "total_tasks": len(tasks_to_run),
                        "num_completed": len(completed_moments),
                        "completed_moments": {str(k): v for k, v in completed_moments.items()}
                    }, f_chk, indent=4)
                os.replace(tmp_chk_path, moments_chk_file)
            except Exception as save_err:
                print(f"Warning: Failed to save moments checkpoint: {save_err}", flush=True)

        if is_g0 or len(tasks_to_run) > 1:
            print(f"  [{config.upper()}][Rank {subgroup_index}] Done moment {cur_idx+1}/{len(tasks_to_run)} (task {task_idx}): force_integral={force_integral:+.6e}", flush=True)
        
    # If K is 1 (non-MPI mode or single subgroup), return total_force and completion status immediately
    if K == 1:
        return total_force, all_completed

    # Sum the force over all subgroups using direct MPI reduction
    try:
        from mpi4py import MPI
        comm = MPI.COMM_WORLD
        if comm.Get_size() > 1 and mp.count_processors() > 1:
            global_force_sum = comm.allreduce(total_force, op=MPI.SUM)
            global_all_comp = comm.allreduce(1 if all_completed else 0, op=MPI.MIN)
            subgroup_size = comm.Get_size() / K
            return global_force_sum / subgroup_size, bool(global_all_comp)
    except ImportError:
        pass

    return total_force, all_completed


def main():
    parser = argparse.ArgumentParser(description="Run 3D MEEP Casimir FDTD simulation.")
    parser.add_argument("--d", type=float, required=True, help="Plate separation in microns.")
    parser.add_argument("--N", type=int, required=True, help="Prefractal generation of top plate (1-4).")
    parser.add_argument("--N-bottom", type=int, default=1, help="Prefractal generation of bottom plate (1=solid, 2=single central hole).")
    parser.add_argument("--material", type=str, required=True, choices=["PEC", "Gold", "Silicon", "Phosphorene", "Phosphorene_tuned", "BlackPhosphorus", "ReS2", "BP_realistic"], help="Material configuration.")
    parser.add_argument("--res", type=int, default=10, help="Grid resolution.")
    parser.add_argument("--nmax", type=int, default=3, help="Max moments index limit.")
    parser.add_argument("--theta", type=float, default=0.0, help="Twist angle of top plate in degrees.")
    parser.add_argument("--eps-bg", type=float, default=1.0, help="Dielectric constant of the background medium.")
    parser.add_argument("--T-run", type=float, default=12.0, help="Total simulation runtime in dimensionless time units.")
    parser.add_argument("--config", type=str, default="all", choices=["both", "self", "all"], help="Simulation configuration (both plates, self plate only, or all).")
    parser.add_argument("--task-idx", type=int, default=-1, help="Specific task index to run (0-35). If -1, run all using subgroups.")
    parser.add_argument("--L", type=float, default=0.3, help="Plate width/length in microns.")
    parser.add_argument("--no-subgroups", action="store_true", help="Force sequential execution of moments without dividing processes into subgroups.")
    parser.add_argument("--moment-start", type=int, default=0, help="Start index of moments to run (0-107).")
    parser.add_argument("--moment-end", type=int, default=108, help="End index of moments to run (1-108).")
    parser.add_argument("--stepped-sieve", action="store_true", help="Enable 3D Stepped Fractal Sieve for bottom plate (Frontier 1).")
    parser.add_argument("--sieve-depths", type=float, nargs="+", default=[0.30, 0.15, 0.05], help="Cavity depths in um for 3D stepped sieve levels.")
    parser.add_argument("--corrugated", action="store_true", help="Enable 3D Interlocking Fractal Corrugations (Frontier 2).")
    parser.add_argument("--clutch", action="store_true", help="Enable Dual-Fractal Quantum Clutch mode (Menger-Weierstrass Spire top plate vs Anisotropic Sierpinski Sieve bottom plate).")
    parser.add_argument("--corrugation-angle", type=float, default=45.0, help="Wall slope angle in degrees for corrugation pyramids (default: 45.0).")
    parser.add_argument("--r-tip", type=float, default=0.0, help="Tip rounding radius in nm for corrugation pyramids (default: 0.0).")
    parser.add_argument("--medium", type=str, default=None, choices=[None, "Vacuum", "Teflon_AF", "Ethanol", "Bromobenzene", "Glycerol", "Cyclohexane"], help="Liquid immersion or background dielectric medium.")
    parser.add_argument("--subgroups", type=int, default=None, help="Explicitly specify number of parallel subgroups (e.g. 1, 2, 4).")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached checkpoint and result files, forcing complete recomputation.")
    parser.add_argument("--max-walltime-hours", type=float, default=11.0, help="Maximum execution time in hours before pausing cleanly for checkpointing (default: 11.0).")
    parser.add_argument("--campaign-task-id", type=int, default=-1, help="Campaign array task ID (1-10) for progress tracking flags.")
    args = parser.parse_args()
    
    # Setup global crash handler for automatic logging and git push
    try:
        from execution.crash_handler import setup_global_exception_handler
        setup_global_exception_handler(args.task_idx, vars(args))
    except (ImportError, RuntimeError, OSError) as exc_err:
        import sys
        print(f"Note: Global exception handler setup skipped: {exc_err}", file=sys.stderr)
    global_rank = int(os.environ.get("SLURM_PROCID", 0))
    total_ranks = int(os.environ.get("SLURM_NTASKS", 1))
    num_tasks = 36 * args.nmax
    
    if args.task_idx >= 0 or args.no_subgroups or total_ranks <= 1:
        K = 1
        subgroup_index = 0
    elif args.subgroups is not None:
        K = max(1, min(args.subgroups, total_ranks))
        subgroup_index = mp.divide_parallel_processes(K) if (K > 1 and mp.count_processors() > 1) else 0
    else:
        if mp.count_processors() > 1:
            M = mp.count_processors()
            # Dynamically query available physical node RAM from the OS kernel (/proc/meminfo)
            usable_ram_gb = 180.0
            try:
                with open("/proc/meminfo", "r") as f_mem:
                    for m_line in f_mem:
                        if m_line.startswith("MemTotal:"):
                            tot_mem_gb = float(m_line.split()[1]) / (1024.0 * 1024.0)
                            usable_ram_gb = tot_mem_gb * 0.75  # 75% for MEEP subgroups, 25% safety margin for OS/MPI
                            break
            except (OSError, ValueError, IndexError):
                usable_ram_gb = 180.0

            t_top_geom, t_bot_geom, _, _ = compute_plate_thicknesses(
                clutch=args.clutch, corrugated=args.corrugated, corrugation_angle=args.corrugation_angle, stepped_sieve=args.stepped_sieve
            )
            sx, sy, sz, _, _, _ = compute_domain_dimensions(
                args.L, args.theta, args.d, t_top_geom, t_bot_geom, dpml=0.20, buffer=0.15, clutch=args.clutch
            )
            est_cells = (sx * args.res) * (sy * args.res) * (sz * args.res)
            # 3D MEEP FDTD Yee cell state vectors (E, D, H, B, PML, susceptibilities) ~ 9.6 KB/cell
            est_mem_gb = (est_cells * 9600.0) / (1024.0**3)
            
            # Dynamically cap concurrent subgroups K so total RAM stays within the node's safe allocation
            max_safe_K = max(1, int(usable_ram_gb / max(1.0, est_mem_gb)))
            K = get_optimal_subgroups(M, num_tasks, max_safe_K=max_safe_K)
            subgroup_index = mp.divide_parallel_processes(K) if K > 1 else 0
        else:
            K = min(total_ranks, num_tasks)
            subgroup_index = global_rank
        
    try:
        from mpi4py import MPI
        if MPI.COMM_WORLD.Get_size() > 1 and mp.count_processors() > 1:
            global_rank = MPI.COMM_WORLD.Get_rank()
    except ImportError:
        pass
        
    if global_rank == 0:
        print(f"Starting simulation: d={args.d} um, N_top={args.N}, N_bottom={args.N_bottom}, material={args.material}, resolution={args.res}, nmax={args.nmax}, theta={args.theta}, eps_bg={args.eps_bg}, config={args.config}, clutch={args.clutch}, stepped_sieve={args.stepped_sieve}, corrugated={args.corrugated}")
        print(f"Parallel configuration: {total_ranks} processes running {K} parallel moment partitions.")
    
    # Setup immersion medium background permittivity if specified
    if args.medium and args.medium not in ["Vacuum", "None"]:
        from execution.materials_database_dispersive import IMMERSION_MEDIA
        if args.medium in IMMERSION_MEDIA and args.eps_bg == 1.0:
            args.eps_bg = IMMERSION_MEDIA[args.medium]["eps_static"]
    r_tip_um = args.r_tip / 1000.0

    # Checkpointing and cache tags (version 4 for verified clutch geometry, version 3 for others)
    rtip_str = f"_rtip_{args.r_tip:.1f}" if ((args.corrugated or args.clutch) and args.r_tip > 0.0) else ""
    med_str = f"_med_{args.medium}" if args.medium and args.medium not in ["Vacuum", "None"] else ""
    chk_version = "v4" if args.clutch else "v3"
    if args.clutch:
        geom_tag = f"_clutch_al_{args.corrugation_angle:.1f}{rtip_str}"
    elif args.corrugated:
        geom_tag = f"_corr_al_{args.corrugation_angle:.1f}{rtip_str}"
    elif args.stepped_sieve:
        geom_tag = "_sieve"
    else:
        geom_tag = "_planar"
    nmax_tag = f"_nmax_{args.nmax}" if args.nmax != 1 else ""
    task_chk_tag = f"{chk_version}_d_{args.d:.4f}_Ntop_{args.N}_Nbot_{args.N_bottom}_mat_{args.material}_res_{args.res}_th_{args.theta:.1f}{geom_tag}{med_str}_L_{args.L:.2f}{nmax_tag}"
    chk_both = f".tmp/chk_{task_chk_tag}_both.json"
    chk_self = f".tmp/chk_{task_chk_tag}_self.json"
    
    # Early exit if final output already exists
    if args.clutch:
        nbot_str = f"_clutch_al_{args.corrugation_angle:.1f}{rtip_str}_Nbot_{args.N_bottom}"
    elif args.corrugated:
        nbot_str = f"_corrugated_al_{args.corrugation_angle:.1f}{rtip_str}{med_str}_Nbot_{args.N_bottom}"
    elif args.stepped_sieve:
        nbot_str = f"_sieve_Nbot_{args.N_bottom}"
    elif args.N_bottom > 1:
        nbot_str = f"_Nbot_{args.N_bottom}"
    else:
        nbot_str = ""
    out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}{nbot_str}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}{nmax_tag}.json"
    
    check_file = None
    if not args.no_cache and os.path.exists(out_file):
        check_file = out_file

    if not args.no_cache and args.config == "all" and args.task_idx < 0 and check_file:
        try:
            with open(check_file, "r") as f:
                cached_res = json.load(f)
            if "force_subtracted" in cached_res:
                if global_rank == 0:
                    print(f"Task already complete! Found cached result in {check_file} (F_sub={cached_res['force_subtracted']:.6e}). Skipping.")
                return
        except (json.JSONDecodeError, OSError, KeyError) as err:
            if global_rank == 0:
                print(f"Warning: Corrupted cache file {check_file} ({err}). Recomputing.")

    # We run the cases for vacuum subtraction with checkpoint resume:
    f_both = 0.0
    f_self = 0.0
    both_done = True
    self_done = True
    
    if args.config in ["all", "both"]:
        if not args.no_cache and os.path.exists(chk_both):
            try:
                with open(chk_both, "r") as f:
                    f_both = float(json.load(f)["force"])
                if global_rank == 0:
                    print(f"Loaded cached 'both' force: {f_both:.6e} from {chk_both}")
            except (json.JSONDecodeError, OSError, KeyError, ValueError) as err:
                if global_rank == 0:
                    print(f"Warning: Corrupted checkpoint {chk_both} ({err}). Recomputing.")
                f_both, both_done = run_simulation(args.d, args.N, args.material, args.res, args.nmax, config="both", theta=args.theta, eps_bg=args.eps_bg, subgroup_index=subgroup_index, K=K, T_run=args.T_run, task_idx_override=args.task_idx, L=args.L, moment_start=args.moment_start, moment_end=args.moment_end, N_bottom=args.N_bottom, stepped_sieve=args.stepped_sieve, sieve_depths=args.sieve_depths, corrugated=args.corrugated, corrugation_angle=args.corrugation_angle, r_tip=r_tip_um, medium=args.medium, clutch=args.clutch, task_chk_tag=task_chk_tag, max_walltime_hours=args.max_walltime_hours, no_cache=args.no_cache)
                if both_done and global_rank == 0:
                    os.makedirs(".tmp", exist_ok=True)
                    with open(chk_both, "w") as f:
                        json.dump({"force": float(f_both)}, f)
        else:
            f_both, both_done = run_simulation(args.d, args.N, args.material, args.res, args.nmax, config="both", theta=args.theta, eps_bg=args.eps_bg, subgroup_index=subgroup_index, K=K, T_run=args.T_run, task_idx_override=args.task_idx, L=args.L, moment_start=args.moment_start, moment_end=args.moment_end, N_bottom=args.N_bottom, stepped_sieve=args.stepped_sieve, sieve_depths=args.sieve_depths, corrugated=args.corrugated, corrugation_angle=args.corrugation_angle, r_tip=r_tip_um, medium=args.medium, clutch=args.clutch, task_chk_tag=task_chk_tag, max_walltime_hours=args.max_walltime_hours, no_cache=args.no_cache)
            if both_done and global_rank == 0:
                os.makedirs(".tmp", exist_ok=True)
                with open(chk_both, "w") as f:
                    json.dump({"force": float(f_both)}, f)

    if both_done and args.config in ["all", "self"]:
        if not args.no_cache and os.path.exists(chk_self):
            try:
                with open(chk_self, "r") as f:
                    f_self = float(json.load(f)["force"])
                if global_rank == 0:
                    print(f"Loaded cached 'self' force: {f_self:.6e} from {chk_self}")
            except (json.JSONDecodeError, OSError, KeyError, ValueError) as err:
                if global_rank == 0:
                    print(f"Warning: Corrupted checkpoint {chk_self} ({err}). Recomputing.")
                f_self, self_done = run_simulation(args.d, args.N, args.material, args.res, args.nmax, config="self", theta=args.theta, eps_bg=args.eps_bg, subgroup_index=subgroup_index, K=K, T_run=args.T_run, task_idx_override=args.task_idx, L=args.L, moment_start=args.moment_start, moment_end=args.moment_end, N_bottom=args.N_bottom, stepped_sieve=args.stepped_sieve, sieve_depths=args.sieve_depths, corrugated=args.corrugated, corrugation_angle=args.corrugation_angle, r_tip=r_tip_um, medium=args.medium, clutch=args.clutch, task_chk_tag=task_chk_tag, max_walltime_hours=args.max_walltime_hours, no_cache=args.no_cache)
                if self_done and global_rank == 0:
                    os.makedirs(".tmp", exist_ok=True)
                    with open(chk_self, "w") as f:
                        json.dump({"force": float(f_self)}, f)
        else:
            f_self, self_done = run_simulation(args.d, args.N, args.material, args.res, args.nmax, config="self", theta=args.theta, eps_bg=args.eps_bg, subgroup_index=subgroup_index, K=K, T_run=args.T_run, task_idx_override=args.task_idx, L=args.L, moment_start=args.moment_start, moment_end=args.moment_end, N_bottom=args.N_bottom, stepped_sieve=args.stepped_sieve, sieve_depths=args.sieve_depths, corrugated=args.corrugated, corrugation_angle=args.corrugation_angle, r_tip=r_tip_um, medium=args.medium, clutch=args.clutch, task_chk_tag=task_chk_tag, max_walltime_hours=args.max_walltime_hours, no_cache=args.no_cache)
            if self_done and global_rank == 0:
                os.makedirs(".tmp", exist_ok=True)
                with open(chk_self, "w") as f:
                    json.dump({"force": float(f_self)}, f)
    elif not both_done:
        self_done = False
        
    task_fully_completed = (both_done if args.config in ["all", "both"] else True) and (self_done if args.config in ["all", "self"] else True)
    
    # Save output and update completion/pending flags
    if global_rank == 0:
        os.makedirs(".tmp", exist_ok=True)
        flag_complete = f".tmp/task_{args.campaign_task_id:03d}_complete.flag" if args.campaign_task_id > 0 else f".tmp/{task_chk_tag}_complete.flag"
        flag_pending = f".tmp/task_{args.campaign_task_id:03d}_pending.flag" if args.campaign_task_id > 0 else f".tmp/{task_chk_tag}_pending.flag"

        if task_fully_completed:
            A_eff = get_effective_area(args.N, args.L)
            is_partial = (args.moment_start > 0 or args.moment_end < num_tasks)
            if is_partial:
                # Write partial moment results
                if args.config == "all":
                    for cfg, force_val in [("both", f_both), ("self", f_self)]:
                        out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}{nbot_str}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}_config_{cfg}_moments_{args.moment_start}_{args.moment_end}.json"
                        result = {
                            "d_um": args.d,
                            "N": args.N,
                            "N_bottom": args.N_bottom,
                            "corrugation_angle": args.corrugation_angle if args.corrugated else 0.0,
                            "r_tip_nm": args.r_tip,
                            "medium": args.medium if args.medium else "Vacuum",
                            "material": args.material,
                            "resolution": args.res,
                            "theta_deg": args.theta,
                            "eps_bg": args.eps_bg,
                            "L": args.L,
                            "config": cfg,
                            "moment_start": args.moment_start,
                            "moment_end": args.moment_end,
                            "force": float(force_val)
                        }
                        with open(out_file, "w") as f:
                            json.dump(result, f, indent=4)
                        print(f"Partial simulation task complete. Saved to {out_file}")
                else:
                    out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}{nbot_str}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}_config_{args.config}_moments_{args.moment_start}_{args.moment_end}.json"
                    result = {
                        "d_um": args.d,
                        "N": args.N,
                        "N_bottom": args.N_bottom,
                        "corrugation_angle": args.corrugation_angle if args.corrugated else 0.0,
                        "r_tip_nm": args.r_tip,
                        "medium": args.medium if args.medium else "Vacuum",
                        "material": args.material,
                        "resolution": args.res,
                        "theta_deg": args.theta,
                        "eps_bg": args.eps_bg,
                        "L": args.L,
                        "config": args.config,
                        "moment_start": args.moment_start,
                        "moment_end": args.moment_end,
                        "force": float(f_both if args.config == "both" else f_self)
                    }
                    with open(out_file, "w") as f:
                        json.dump(result, f, indent=4)
                    print(f"Partial simulation task complete. Saved to {out_file}")
            else:
                if args.task_idx >= 0:
                    if args.config == "all":
                        out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}{nbot_str}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}_task_{args.task_idx}.json"
                        result = {
                            "d_um": args.d,
                            "N": args.N,
                            "N_bottom": args.N_bottom,
                            "corrugation_angle": args.corrugation_angle if args.corrugated else 0.0,
                            "r_tip_nm": args.r_tip,
                            "medium": args.medium if args.medium else "Vacuum",
                            "material": args.material,
                            "resolution": args.res,
                            "theta_deg": args.theta,
                            "eps_bg": args.eps_bg,
                            "L": args.L,
                            "task_idx": args.task_idx,
                            "force_both": float(f_both),
                            "force_self": float(f_self),
                            "force_subtracted": float(f_both - f_self),
                            "pressure_Pa": float((f_both - f_self) / A_eff)
                        }
                    else:
                        out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}{nbot_str}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}_config_{args.config}_task_{args.task_idx}.json"
                        result = {
                            "d_um": args.d,
                            "N": args.N,
                            "N_bottom": args.N_bottom,
                            "corrugation_angle": args.corrugation_angle if args.corrugated else 0.0,
                            "r_tip_nm": args.r_tip,
                            "medium": args.medium if args.medium else "Vacuum",
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
                        out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}{nbot_str}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}{nmax_tag}.json"
                        result = {
                            "d_um": args.d,
                            "N": args.N,
                            "N_bottom": args.N_bottom,
                            "clutch": args.clutch,
                            "corrugation_angle": args.corrugation_angle if (args.corrugated or args.clutch) else 0.0,
                            "r_tip_nm": args.r_tip,
                            "medium": args.medium if args.medium else "Vacuum",
                            "material": args.material,
                            "resolution": args.res,
                            "nmax": args.nmax,
                            "theta_deg": args.theta,
                            "eps_bg": args.eps_bg,
                            "L": args.L,
                            "force_both": float(f_both),
                            "force_self": float(f_self),
                            "force_subtracted": float(f_both - f_self),
                            "pressure_Pa": float((f_both - f_self) / A_eff)
                        }
                    else:
                        out_file = f".tmp/meep_d_{args.d:.4f}_N_{args.N}{nbot_str}_{args.material}_res_{args.res}_theta_{args.theta:.1f}_eps_{args.eps_bg:.1f}_L_{args.L:.2f}{nmax_tag}_config_{args.config}.json"
                        result = {
                            "d_um": args.d,
                            "N": args.N,
                            "N_bottom": args.N_bottom,
                            "clutch": args.clutch,
                            "corrugation_angle": args.corrugation_angle if (args.corrugated or args.clutch) else 0.0,
                            "r_tip_nm": args.r_tip,
                            "medium": args.medium if args.medium else "Vacuum",
                            "material": args.material,
                            "resolution": args.res,
                            "nmax": args.nmax,
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

            # Mark task as 100% complete and clear any pending flag
            with open(flag_complete, "w") as f:
                json.dump({"status": "complete", "timestamp": time.time(), "task_id": args.campaign_task_id, "out_file": out_file}, f, indent=4)
            if os.path.exists(flag_pending):
                try:
                    os.remove(flag_pending)
                except OSError:
                    pass
        else:
            # Task reached walltime budget with pending moments; write pending flag for continuation
            with open(flag_pending, "w") as f:
                json.dump({"status": "pending", "timestamp": time.time(), "task_id": args.campaign_task_id, "both_done": both_done, "self_done": self_done}, f, indent=4)
            print(f"\n[STATUS: PENDING] Task {args.campaign_task_id} reached walltime budget limit ({args.max_walltime_hours:.1f}h).")
            print(f"[STATUS: PENDING] Checkpointed progress safely recorded on disk. Ready for continuation job.")

if __name__ == "__main__":
    main()
