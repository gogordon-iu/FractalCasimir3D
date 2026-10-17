#!/usr/bin/env python3
"""
Fractal Control Casimir FDTD Simulation Engine
----------------------------------------------
Executes 3D Maxwell stress tensor simulations for the Fractal Geometry Control
Campaign.

Passing --max-steps runs a bounded, deterministic geometry micro-probe instead
of FDTD. Micro-probe results are explicitly identified and contain no synthetic
force or pressure estimates.
"""

import os
import sys
import math
import json
import time
import argparse
import importlib.util
import inspect
import ctypes
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from execution.fractal_control_geometry import (
    calculate_area_fraction,
    calculate_standoff,
    get_geometry_elements,
    create_plate_blocks_meep,
)

MEEP_TO_PA = 0.0316152649
MEEP_TO_FN = 31.6152649
MODEL = "fractal_control_casimir_fdtd"
DATASET = "fractal_geometry_control"


def result_metadata(status="completed"):
    return {
        "model": MODEL,
        "dataset": DATASET,
        "status": status,
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def call_supported_parameters(function, values):
    """Bind repository helpers without guessing their positional argument order."""
    signature = inspect.signature(function)
    positional = []
    keywords = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if name not in values:
            assert parameter.default is not inspect.Parameter.empty, (
                f"Unsupported required parameter {name!r} in {function.__name__}"
            )
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                positional.append(parameter.default)
            continue
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            positional.append(values[name])
        else:
            keywords[name] = values[name]
    return function(*positional, **keywords)


def log_result_metrics(out_data, out_dir, output_path):
    """Record completed runs through the repository's metrics logger."""
    from utils.metrics_logger import log_metrics

    metrics = {
        key: value
        for key, value in out_data.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    values = dict(out_data)
    values.update({
        "metrics": metrics,
        "record": out_data,
        "data": out_data,
        "results": out_data,
        "model_name": MODEL,
        "dataset_name": DATASET,
        "run_id": out_data["label"],
        "out_dir": out_dir,
        "output_dir": out_dir,
        "log_dir": out_dir,
        "output_path": output_path,
        "file_path": output_path,
        "log_path": os.path.join(out_dir, "metrics.jsonl"),
    })
    call_supported_parameters(log_metrics, values)


def get_src_index(n: int) -> tuple:
    """Cantor pairing function decoder."""
    assert isinstance(n, (int, np.integer)) and not isinstance(n, bool)
    assert n >= 0, f"Moment index must be nonnegative, got {n}"
    s = 0
    r = 0
    while s + r < n:
        r += 1
        s += r
    c = n - s
    return r - c, c


def compute_domain_dimensions(
    L: float,
    theta_deg: float,
    d_min: float,
    t_top: float,
    t_bottom: float,
    dpml: float = 0.20,
    buffer: float = 0.15,
    delta_s_xy: float = 0.03,
) -> tuple:
    """
    Computes rotated bounding dimensions and integration box geometry.
    """
    for name, value in (
        ("L", L), ("theta_deg", theta_deg), ("d_min", d_min),
        ("t_top", t_top), ("t_bottom", t_bottom), ("dpml", dpml),
        ("buffer", buffer), ("delta_s_xy", delta_s_xy),
    ):
        assert isinstance(value, (int, float, np.number)), (
            f"{name} must be numeric, got {value!r}"
        )
        assert math.isfinite(value), f"{name} must be finite, got {value}"
    assert L > 0.0, f"Plate width L must be positive, got {L}"
    assert d_min > 0.0, f"d_min must be positive, got {d_min}"
    assert t_top > 0.0 and t_bottom > 0.0, "Plate thicknesses must be positive"
    assert dpml > 0.0 and buffer >= 0.0 and delta_s_xy >= 0.0

    theta_rad = math.radians(theta_deg)
    L_rot = L * (abs(math.cos(theta_rad)) + abs(math.sin(theta_rad)))
    delta_s_z = d_min / 2.0

    sx = L_rot + 2.0 * (dpml + buffer)
    sy = sx
    sz = d_min + t_top + t_bottom + 2.0 * (dpml + buffer)

    return sx, sy, sz, delta_s_xy, delta_s_z, L_rot


def build_meep_material(material_name: str, Sigma: float, ft, theta_deg: float, eps_bg: float, mp):
    """
    Constructs a dispersive MEEP Medium with Wick-rotated conductivity.

    The artificial conductivity is not added to susceptibility damping rates.
    """
    assert isinstance(material_name, str) and material_name.strip()
    assert math.isfinite(Sigma) and Sigma >= 0.0
    assert math.isfinite(theta_deg)
    assert math.isfinite(eps_bg) and eps_bg > 0.0
    assert ft in (mp.E_stuff, mp.H_stuff)

    cond_attr = {
        "D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma
    }

    if material_name == "PEC":
        return mp.Medium(epsilon=-1e20, **cond_attr)

    if material_name in ["Gold", "Silicon"]:
        from meep.materials import Au, cSi

        base_medium = Au if material_name == "Gold" else cSi
        new_sus = []
        for sus in base_medium.E_susceptibilities:
            freq = sus.frequency
            gamma_val = sus.gamma
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
                    sigma=sigma_val,
                ))
            elif isinstance(sus, mp.LorentzianSusceptibility):
                new_sus.append(mp.LorentzianSusceptibility(
                    frequency=freq,
                    gamma=gamma_val,
                    sigma=sus.sigma_diag.x,
                ))
        return mp.Medium(
            epsilon=base_medium.epsilon_diag.x,
            E_susceptibilities=new_sus,
            **cond_attr,
        )

    if material_name in ["Phosphorene", "Phosphorene_tuned"]:
        from execution.materials_database_dispersive import get_meep_dispersive_medium

        medium = call_supported_parameters(
            get_meep_dispersive_medium,
            {
                "material_name": material_name,
                "material": material_name,
                "name": material_name,
                "theta_deg": theta_deg,
                "theta": theta_deg,
                "angle_deg": theta_deg,
                "eps_bg": eps_bg,
                "epsilon_bg": eps_bg,
                "mp": mp,
                "mp_module": mp,
                "meep_module": mp,
                "Sigma": Sigma,
                "sigma": Sigma,
                "ft": ft,
                "ft_type": ft,
            },
        )
        assert medium is not None, "Dispersive material factory returned no medium"
        assert medium.E_susceptibilities, (
            f"{material_name} must include dispersive E_susceptibilities"
        )
        # Keep the factory's dielectric tensor and oscillator parameters intact.
        # Apply artificial conductivity only to the field type for this pass.
        medium.D_conductivity = Sigma if ft == mp.E_stuff else 0.0
        medium.B_conductivity = Sigma if ft == mp.H_stuff else 0.0
        return medium

    eps_val = float(material_name) if material_name.replace(".", "", 1).isdigit() else 2.0
    assert math.isfinite(eps_val) and eps_val > 0.0
    return mp.Medium(epsilon=eps_val, **cond_attr)


def run_single_pass(
    config: str,
    elements: list,
    d_min: float,
    t_top: float,
    t_bottom: float,
    feature_depth: float,
    theta_deg: float,
    L: float,
    material_name: str,
    eps_bg: float,
    resolution: int,
    nmax: int,
    T_run: float,
    mp,
    is_rank0: bool,
    chk_file: str,
) -> float:
    """Executes one pass over all 36 * nmax imaginary frequency moments."""
    assert config in ["both", "self"], (
        f"Pass config must be 'both' or 'self', got {config}"
    )
    assert isinstance(resolution, (int, np.integer)) and not isinstance(resolution, bool)
    assert resolution > 0
    assert isinstance(nmax, (int, np.integer)) and not isinstance(nmax, bool)
    assert nmax > 0
    assert isinstance(T_run, (int, float, np.number))
    assert math.isfinite(T_run) and T_run > 0.0

    dpml = 0.20
    buffer = 0.15
    sx, sy, sz, delta_s_xy, delta_s_z, L_rot = compute_domain_dimensions(
        L, theta_deg, d_min, t_top, t_bottom, dpml=dpml, buffer=buffer
    )
    cell_size = mp.Vector3(sx, sy, sz)
    Sigma = 0.5 / d_min

    sx_box = L_rot + 2.0 * delta_s_xy
    sy_box = L_rot + 2.0 * delta_s_xy
    sz_box = t_top + 2.0 * delta_s_z
    center_z = d_min / 2.0 + t_top / 2.0

    sides_info = [
        {"center": mp.Vector3(-sx_box / 2.0, 0.0, center_z), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(sx_box / 2.0, 0.0, center_z), "size": mp.Vector3(0.0, sy_box, sz_box), "orientation": 1.0},
        {"center": mp.Vector3(0.0, -sy_box / 2.0, center_z), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": -1.0},
        {"center": mp.Vector3(0.0, sy_box / 2.0, center_z), "size": mp.Vector3(sx_box, 0.0, sz_box), "orientation": 1.0},
        {"center": mp.Vector3(0.0, 0.0, center_z - sz_box / 2.0), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": -1.0},
        {"center": mp.Vector3(0.0, 0.0, center_z + sz_box / 2.0), "size": mp.Vector3(sx_box, sy_box, 0.0), "orientation": 1.0},
    ]

    pol_list = [mp.Ex, mp.Ey, mp.Ez, mp.Hx, mp.Hy, mp.Hz]
    comp_dir = {
        mp.Ex: mp.X, mp.Ey: mp.Y, mp.Ez: mp.Z,
        mp.Dx: mp.X, mp.Dy: mp.Y, mp.Dz: mp.Z,
        mp.Hx: mp.X, mp.Hy: mp.Y, mp.Hz: mp.Z,
        mp.Bx: mp.X, mp.By: mp.Y, mp.Bz: mp.Z,
    }

    total_tasks = 36 * nmax
    completed_moments = {}

    if chk_file and os.path.isfile(chk_file):
        with open(chk_file, "r", encoding="utf-8") as fc:
            cdata = json.load(fc)
        assert isinstance(cdata, dict), "Checkpoint must contain a JSON object"
        if "completed_moments" in cdata:
            assert cdata.get("config", config) == config
            assert cdata.get("total_tasks", total_tasks) == total_tasks
            assert isinstance(cdata["completed_moments"], dict)
            for key, value in cdata["completed_moments"].items():
                assert isinstance(key, str) and key.isdecimal()
                index = int(key)
                assert 0 <= index < total_tasks
                assert isinstance(value, (int, float)) and not isinstance(value, bool)
                assert math.isfinite(value), "Checkpoint contains a nonfinite force"
                completed_moments[index] = float(value)
            if is_rank0:
                print(
                    f"[{config.upper()}] Resuming from checkpoint: "
                    f"{len(completed_moments)}/{total_tasks} moments cached.",
                    flush=True,
                )

    total_force = 0.0

    for task_idx in range(total_tasks):
        if task_idx in completed_moments:
            f_val = completed_moments[task_idx]
            total_force += f_val
            if is_rank0:
                print(
                    f"  [{config.upper()}] Moment {task_idx + 1}/{total_tasks} "
                    f"[CACHED]: force={f_val:+.6e}",
                    flush=True,
                )
            continue

        p = task_idx // (nmax * 6)
        n = task_idx % (nmax * 6)
        curr_pol = pol_list[p]
        ft = mp.E_stuff if curr_pol in [mp.Ex, mp.Ey, mp.Ez] else mp.H_stuff

        bot_mat = build_meep_material(material_name, Sigma, ft, 0.0, eps_bg, mp)
        top_mat = build_meep_material(material_name, Sigma, ft, theta_deg, eps_bg, mp)
        carve_mat = (
            mp.Medium(epsilon=eps_bg, D_conductivity=Sigma)
            if ft == mp.E_stuff
            else mp.Medium(epsilon=eps_bg, B_conductivity=Sigma)
        )

        geometry = create_plate_blocks_meep(
            elements=elements,
            L=L,
            d_min=d_min,
            t_top=t_top,
            t_bottom=t_bottom,
            feature_depth=feature_depth,
            theta_deg=theta_deg,
            top_material=top_mat,
            bottom_material=bot_mat,
            carve_material=carve_mat,
            config=config,
            mp_module=mp,
        )

        sim = mp.Simulation(
            cell_size=cell_size,
            geometry=geometry,
            resolution=resolution,
            boundary_layers=[mp.PML(dpml)],
            default_material=carve_mat,
            Courant=0.5,
            eps_averaging=False,
            force_complex_fields=True,
        )

        sim.init_sim()
        dt = sim.Courant / resolution
        assert math.isfinite(dt) and dt > 0.0
        T_steps = int(T_run / dt)
        assert T_steps > 0, "T_run must span at least one FDTD timestep"

        # MEEP expects a field-type enum, not a polarization component.
        ft_type = mp.E_stuff if curr_pol in [mp.Ex, mp.Ey, mp.Ez] else mp.H_stuff
        gt = mp.make_casimir_gfunc(T_run, dt, Sigma, ft_type)
        addr = int(gt)
        assert addr != 0, "MEEP returned a null Casimir kernel"
        double_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_double))
        data = np.ctypeslib.as_array(double_ptr, shape=(T_steps * 2,))
        gt_arr = data[0::2] + 1j * data[1::2]
        assert np.all(np.isfinite(gt_arr)), "Casimir kernel contains NaN or Inf"

        s = n % 6
        nr = n // 6
        m1, m2 = get_src_index(nr)

        side = sides_info[s]
        side_center = side["center"]
        side_size = side["size"]
        side_orient = side["orientation"]

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
                # MEEP supplies source-local coordinates.
                x = pt.x + 0.5 * sx_v
                y = pt.y + 0.5 * sy_v
                z = pt.z + 0.5 * sz_v
                kx = mx_val * np.pi / sx_v if sx_v > 1e-15 else 0.0
                ky = my_val * np.pi / sy_v if sy_v > 1e-15 else 0.0
                kz = mz_val * np.pi / sz_v if sz_v > 1e-15 else 0.0
                return factor * np.cos(kx * x) * np.cos(ky * y) * np.cos(kz * z)

            return amp_func

        src_vol = mp.Volume(center=side_center, size=side_size, dims=3)

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
                amp_func=make_amp_func(mx, my, mz, side_size, side_center),
            )
        ])

        sim.reset_meep()
        sim.init_sim()

        force_integral = 0.0
        for step in range(T_steps):
            sim.fields.step()
            f_temp = sim.fields.casimir_stress_dct_integral(
                mp.Z, comp_dir[curr_pol],
                float(mx), float(my), float(mz),
                ft, src_vol.swigobj,
            )
            assert np.isfinite(f_temp), (
                f"Nonfinite stress at moment {task_idx}, step {step}"
            )
            force_integral += float(np.imag(gt_arr[step] * dt * side_orient * f_temp))
            assert math.isfinite(force_integral), "Nonfinite force integral"

        total_force += force_integral
        assert math.isfinite(total_force), "Nonfinite accumulated force"
        completed_moments[task_idx] = float(force_integral)

        if is_rank0 and chk_file:
            os.makedirs(os.path.dirname(chk_file) or ".", exist_ok=True)
            tmp_chk = f"{chk_file}.tmp_{os.getpid()}"
            checkpoint = {
                "config": config,
                "total_tasks": total_tasks,
                "num_completed": len(completed_moments),
                "completed_moments": {str(k): v for k, v in completed_moments.items()},
            }
            checkpoint.update(result_metadata(
                "completed" if len(completed_moments) == total_tasks else "in_progress"
            ))
            with open(tmp_chk, "w", encoding="utf-8") as fc:
                json.dump(checkpoint, fc, indent=4, allow_nan=False)
            os.replace(tmp_chk, chk_file)

        if is_rank0:
            print(
                f"  [{config.upper()}] Done moment {task_idx + 1}/{total_tasks}: "
                f"force_moment={force_integral:+.6e}",
                flush=True,
            )

    return total_force


def main():
    parser = argparse.ArgumentParser(
        description="Run 3D MEEP Casimir simulation for Fractal Geometry Control suite."
    )
    parser.add_argument("--config-file", type=str, default="", help="Path to task JSON config file.")
    parser.add_argument("--task-id", type=int, default=1, help="Task ID (1-15)")
    parser.add_argument("--geometry-type", type=str, default="fractal", choices=["fractal", "shuffled", "flat"])
    parser.add_argument("--N", type=int, default=3, help="Fractal iteration depth (0-3)")
    parser.add_argument("--theta", type=float, default=0.0, help="Twist angle in degrees")
    parser.add_argument("--d-avg", type=float, default=0.10, help="Target average distance in um")
    parser.add_argument("--feature-depth", type=float, default=0.05, help="Feature cavity depth in um")
    parser.add_argument("--L", type=float, default=2.0, help="Plate width in um")
    parser.add_argument("--material", type=str, default="Gold", help="Plate material")
    parser.add_argument("--resolution", type=int, default=40, help="Grid resolution")
    parser.add_argument("--nmax", type=int, default=1, help="Multipole moment multiplier")
    parser.add_argument("--T-run", type=float, default=12.0, help="FDTD run time")
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Run a deterministic geometry micro-probe with at most this many steps; no FDTD forces are estimated.",
    )
    parser.add_argument("--shuffle-seed", type=int, default=42, help="Seed for shuffled geometry")
    parser.add_argument("--out-dir", type=str, default="results_fractal_control", help="Output directory")

    args = parser.parse_args()
    if args.max_steps is not None:
        assert args.max_steps >= 0, "--max-steps must be nonnegative"

    if args.config_file:
        assert os.path.isfile(args.config_file), (
            f"Configuration file does not exist: {args.config_file}"
        )
        with open(args.config_file, "r", encoding="utf-8") as f_cfg:
            cfg = json.load(f_cfg)
        assert isinstance(cfg, dict), "Configuration must contain a JSON object"
        task_id = cfg.get("task_id", args.task_id)
        geom_type = cfg.get("geometry_type", args.geometry_type)
        N = cfg.get("N_top", args.N)
        theta = cfg.get("theta", args.theta)
        d_avg = cfg.get("d_average_um", args.d_avg)
        h = cfg.get("feature_depth_um", args.feature_depth)
        L = cfg.get("L", args.L)
        material = cfg.get("material", args.material)
        eps_bg = cfg.get("eps_bg", 1.0)
        res = cfg.get("resolution", args.resolution)
        nmax = cfg.get("nmax", args.nmax)
        T_run = cfg.get("T_run", args.T_run)
        shuffle_seed = cfg.get("shuffle_seed", args.shuffle_seed)
        label = cfg.get("label", f"Task_{task_id}")
    else:
        task_id = args.task_id
        geom_type = args.geometry_type
        N = args.N
        theta = args.theta
        d_avg = args.d_avg
        h = args.feature_depth
        L = args.L
        material = args.material
        eps_bg = 1.0
        res = args.resolution
        nmax = args.nmax
        T_run = args.T_run
        shuffle_seed = args.shuffle_seed
        label = f"Task_{task_id}_{geom_type}_N{N}_th{theta:.1f}"

    for name, value in (
        ("task_id", task_id), ("N", N), ("resolution", res),
        ("nmax", nmax), ("shuffle_seed", shuffle_seed),
    ):
        assert isinstance(value, int) and not isinstance(value, bool), (
            f"{name} must be an integer"
        )
    assert task_id > 0 and 0 <= N <= 3
    assert res > 0 and nmax > 0
    assert shuffle_seed >= 0
    assert geom_type in ("fractal", "shuffled", "flat")
    assert isinstance(material, str) and material.strip()
    assert isinstance(label, str) and label
    for name, value in (
        ("theta", theta), ("d_average_um", d_avg), ("feature_depth_um", h),
        ("L", L), ("eps_bg", eps_bg), ("T_run", T_run),
    ):
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"{name} must be numeric"
        )
        assert math.isfinite(value), f"{name} must be finite"
    assert d_avg > 0.0 and h >= 0.0 and L > 0.0
    assert eps_bg > 0.0 and T_run > 0.0
    assert T_run >= 0.5 / res, "T_run must span at least one FDTD timestep"

    f_area = calculate_area_fraction(N) if geom_type != "flat" else 0.0
    assert math.isfinite(f_area) and 0.0 <= f_area <= 1.0
    d_min = calculate_standoff(d_avg, h, f_area)
    assert math.isfinite(d_min) and d_min > 0.0
    assert math.isclose(d_min + f_area * h, d_avg, rel_tol=1e-12, abs_tol=1e-15)
    elements = get_geometry_elements(geom_type, N, L, shuffle_seed=shuffle_seed)

    slurm_proc = os.environ.get("SLURM_PROCID")
    is_rank0 = slurm_proc is None or int(slurm_proc) == 0
    # Also support launchers that do not populate SLURM_PROCID.
    for rank_variable in ("OMPI_COMM_WORLD_RANK", "PMI_RANK", "PMIX_RANK"):
        if slurm_proc is None and rank_variable in os.environ:
            is_rank0 = int(os.environ[rank_variable]) == 0
            break

    if is_rank0:
        print("=" * 80)
        print("FRACTAL GEOMETRY CONTROL FDTD SIMULATION")
        print("=" * 80)
        print(f"Task ID:          {task_id}")
        print(f"Label:            {label}")
        print(f"Geometry Type:    {geom_type}")
        print(f"Prefractal Level: N={N}")
        print(f"Twist Angle:      theta={theta:.1f} deg")
        print(f"Target Avg Gap:   <d> = {d_avg*1e3:.2f} nm")
        print(f"Surface Standoff: d_min = {d_min*1e3:.2f} nm")
        print(f"Feature Depth:    h = {h*1e3:.2f} nm")
        print(f"Feature Area:     f = {f_area*100:.2f}% ({f_area*729:.0f}/729 cells)")
        print(f"Num Elements:     {len(elements)}")
        print(f"Plate Width:      L = {L:.2f} um")
        print(f"Material:         {material}")
        print(f"Resolution:       R = {res} pixels/um")
        print("=" * 80)

    out_dir = os.path.join(REPO_ROOT, args.out_dir)
    res_json_dir = os.path.join(out_dir, "results_json")
    prog_dir = os.path.join(out_dir, "progress")
    chk_dir = os.path.join(REPO_ROOT, ".tmp")
    t_top = 0.10
    t_bottom = 0.10

    base_data = {
        "task_id": task_id,
        "label": label,
        "campaign": DATASET,
        "geometry_type": geom_type,
        "N_top": N,
        "theta_deg": theta,
        "d_average_um": d_avg,
        "d_min_um": d_min,
        "feature_depth_um": h,
        "area_fraction": f_area,
        "num_elements": len(elements),
        "material": material,
        "resolution": res,
    }

    if args.max_steps is not None:
        # Exercise the actual domain and moment-index calculations, not a
        # substitute physical force model. Empty probes remain valid.
        dimensions = compute_domain_dimensions(
            L, theta, d_min, t_top, t_bottom
        )
        steps = min(args.max_steps, 36 * nmax)
        checksum = 0
        for task_idx in range(steps):
            moment = (task_idx % (nmax * 6)) // 6
            m1, m2 = get_src_index(moment)
            checksum += (task_idx + 1) * (m1 + 1) * (m2 + 1)

        if is_rank0:
            os.makedirs(res_json_dir, exist_ok=True)
            os.makedirs(prog_dir, exist_ok=True)
            out_data = dict(base_data)
            out_data.update(result_metadata())
            out_data.update({
                "execution_mode": "geometry_micro_probe",
                "physics_simulated": False,
                "max_steps": args.max_steps,
                "steps_executed": steps,
                "moment_checksum": checksum,
                "average_distance_error_um": abs(d_min + f_area * h - d_avg),
                "domain_dimensions_um": list(dimensions[:3]),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            out_json_path = os.path.join(
                res_json_dir,
                f"micro_probe_task_{task_id:03d}_{geom_type}_N{N}_th_{theta:.1f}.json",
            )
            with open(out_json_path, "w", encoding="utf-8") as fo:
                json.dump(out_data, fo, indent=4, allow_nan=False)
            prog_path = os.path.join(
                prog_dir, f"task_{task_id:03d}_micro_probe_status.json"
            )
            with open(prog_path, "w", encoding="utf-8") as fp:
                json.dump(out_data, fp, indent=4, allow_nan=False)
            log_result_metrics(out_data, out_dir, out_json_path)
            print(f"Geometry micro-probe completed: {steps} steps; no FDTD force estimated.")
            print(f"Result written to: {out_json_path}")
        return

    meep_spec = importlib.util.find_spec("meep")
    if meep_spec is None:
        if is_rank0:
            print("Notice: MEEP library is not installed in the local Python environment.")
            print("Geometry assertions and distance calculations verified successfully.")
            print("Submit this job to BigRed 200 with conda environment 'meep' to run FDTD.")
        sys.exit(0)

    import meep as mp
    mp.verbosity(0)
    is_rank0 = bool(mp.am_master())

    mpi_spec = importlib.util.find_spec("mpi4py")
    comm = None
    if mpi_spec is not None:
        import mpi4py.MPI as MPI
        comm = MPI.COMM_WORLD

    if is_rank0:
        os.makedirs(res_json_dir, exist_ok=True)
        os.makedirs(prog_dir, exist_ok=True)
        os.makedirs(chk_dir, exist_ok=True)

    chk_both = os.path.join(chk_dir, f"chk_moments_fractal_ctrl_task_{task_id:03d}_both.json")
    chk_self = os.path.join(chk_dir, f"chk_moments_fractal_ctrl_task_{task_id:03d}_self.json")

    if is_rank0:
        print("\n--- Pass 1: BOTH PLATES (Interaction + Self) ---", flush=True)
    f_both = run_single_pass(
        config="both",
        elements=elements,
        d_min=d_min,
        t_top=t_top,
        t_bottom=t_bottom,
        feature_depth=h,
        theta_deg=theta,
        L=L,
        material_name=material,
        eps_bg=eps_bg,
        resolution=res,
        nmax=nmax,
        T_run=T_run,
        mp=mp,
        is_rank0=is_rank0,
        chk_file=chk_both,
    )

    if is_rank0:
        print("\n--- Pass 2: TOP PLATE ONLY (Self Force Isolation) ---", flush=True)
    f_self = run_single_pass(
        config="self",
        elements=elements,
        d_min=d_min,
        t_top=t_top,
        t_bottom=t_bottom,
        feature_depth=h,
        theta_deg=theta,
        L=L,
        material_name=material,
        eps_bg=eps_bg,
        resolution=res,
        nmax=nmax,
        T_run=T_run,
        mp=mp,
        is_rank0=is_rank0,
        chk_file=chk_self,
    )

    if comm is not None and comm.Get_size() > 1:
        f_both = comm.allreduce(f_both, op=MPI.SUM) / comm.Get_size()
        f_self = comm.allreduce(f_self, op=MPI.SUM) / comm.Get_size()

    f_net = f_both - f_self
    f_net_fN = f_net * MEEP_TO_FN
    plate_area_um2 = L * L
    assert math.isfinite(plate_area_um2) and plate_area_um2 > 0.0
    pressure_Pa = (f_net * MEEP_TO_PA) / plate_area_um2
    assert all(math.isfinite(value) for value in (
        f_both, f_self, f_net, f_net_fN, pressure_Pa
    )), "Simulation produced nonfinite results"
    regime = (
        "REPULSIVE" if pressure_Pa > 0.0
        else "ATTRACTIVE" if pressure_Pa < 0.0
        else "ZERO"
    )

    if is_rank0:
        print("\n" + "=" * 80)
        print("SIMULATION RESULTS SUMMARY")
        print("=" * 80)
        print(f"Force (Both):     F_both = {f_both:+.8e}")
        print(f"Force (Self):     F_self = {f_self:+.8e}")
        print(f"Net Force (meep): F_net  = {f_net:+.8e}")
        print(f"Net Force (fN):   F_net  = {f_net_fN:+.4f} fN")
        print(f"Pressure (Pa):    P      = {pressure_Pa:+.6e} Pa")
        print(f"Casimir Regime:   {regime}")
        print("=" * 80)

        out_data = dict(base_data)
        out_data.update(result_metadata())
        out_data.update({
            "execution_mode": "fdtd",
            "physics_simulated": True,
            "force_both": f_both,
            "force_self": f_self,
            "force_net_meep": f_net,
            "force_net_fN": f_net_fN,
            "pressure_Pa": pressure_Pa,
            "regime": regime,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

        out_json_path = os.path.join(
            res_json_dir,
            f"meep_task_{task_id:03d}_{geom_type}_N{N}_th_{theta:.1f}.json",
        )
        with open(out_json_path, "w", encoding="utf-8") as fo:
            json.dump(out_data, fo, indent=4, allow_nan=False)
        print(f"Result written to: {out_json_path}")

        progress = {
            "task_id": task_id,
            "label": label,
            "execution_mode": "fdtd",
            "moments_done": 36 * nmax,
            "total_moments": 36 * nmax,
            "completion_pct": 100.0,
            "net_force": f_net,
            "pressure_Pa": pressure_Pa,
            "exit_code": 0,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        progress.update(result_metadata())
        prog_path = os.path.join(prog_dir, f"task_{task_id:03d}_status.json")
        with open(prog_path, "w", encoding="utf-8") as fp:
            json.dump(progress, fp, indent=4, allow_nan=False)
        print(f"Status written to: {prog_path}")
        log_result_metrics(out_data, out_dir, out_json_path)


if __name__ == "__main__":
    main()
