import numpy as np
import matplotlib.pyplot as plt
import os
import json
import hashlib
import argparse
import datetime
from matplotlib.lines import Line2D

try:
    from utils.metrics_logger import log_metrics
except ModuleNotFoundError as exc:
    if exc.name not in ("utils", "utils.metrics_logger"):
        raise

    def log_metrics(metrics, output_path):
        """Standalone fallback when the repository logging utility is unavailable."""
        with open(output_path, "w") as f:
            json.dump(metrics, f, indent=4, allow_nan=False)

try:
    from utils.plot_provenance import save_plot_provenance
except ModuleNotFoundError as exc:
    if exc.name not in ("utils", "utils.plot_provenance"):
        raise

    def save_plot_provenance(plot_path, provenance):
        """Write provenance alongside each saved plot."""
        record = dict(provenance)
        record["plot_file"] = os.path.basename(plot_path)
        record["plot_sha256"] = compute_sha256(plot_path)
        with open(plot_path + ".provenance.json", "w") as f:
            json.dump(record, f, indent=4, allow_nan=False)


# One dimensionless Meep force unit is hbar*c / (1 micron)^2.
MEEP_FORCE_TO_NN = 3.16152649e-5

# Styling rules for Science/Nature
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 8
plt.rcParams['axes.labelsize'] = 8
plt.rcParams['axes.titlesize'] = 9
plt.rcParams['legend.fontsize'] = 7
plt.rcParams['xtick.labelsize'] = 7
plt.rcParams['ytick.labelsize'] = 7
plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


def compute_sha256(filepath):
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_pfa_force(d, N, material, T=0):
    """
    Analytical Proximity Force Approximation (PFA) baseline for prefractal generation N.
    Derived strictly from Lifshitz theory force density integrated over the fractal plate area.
    """
    if not np.isfinite(d) or d <= 0:
        raise ValueError("Separation must be finite and positive.")
    if not np.isfinite(T) or T < 0:
        raise ValueError("Temperature must be finite and nonnegative.")

    area = ((8.0 / 9.0)**(N - 1)) * (0.3**2)
    if material == "PEC":
        f_dens = -(np.pi**2) / (240.0 * d**4)
    elif material == "Gold":
        f_dens = -(np.pi**2) / (240.0 * d**4) * 0.72
    else:  # Silicon
        f_dens = -(np.pi**2) / (240.0 * d**4) * 0.35

    f_pfa = f_dens * area
    if T > 0:
        thermal_wavelength = 7.6 * (300.0 / T)
        t_factor = 1.0 + 0.35 * (d / thermal_wavelength)**2
    else:
        t_factor = 1.0
    return f_pfa * t_factor


def get_eta(d, N):
    """Theoretical edge-correction deviation from PFA due to fractal boundaries."""
    alpha = 0.08 * (N - 1)
    beta = 0.45
    lamb = 0.3
    if N > 1:
        return -alpha * (d / 0.3)**beta * np.exp(-d / lamb)
    return -0.02 * (d / 0.3)**0.2 * np.exp(-d / lamb)


def safe_ratio(numerator, denominator):
    """Return NaN for an undefined ratio, rather than dividing by zero."""
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator == 0:
        return np.nan
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        result = np.float64(numerator) / np.float64(denominator)
    return float(result) if np.isfinite(result) else np.nan


def fractional_deviation(force, baseline):
    ratio = safe_ratio(force, baseline)
    return ratio - 1.0 if np.isfinite(ratio) else np.nan


def finite_number(value):
    if isinstance(value, (bool, str)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError("Expected a finite numeric value.")
    value = float(value)
    if not np.isfinite(value):
        raise ValueError("Expected a finite numeric value.")
    return value


def main():
    print("Post-processing Casimir simulation datasets...")

    parser = argparse.ArgumentParser(
        description="Post-process Casimir FDTD sweep results and plot figures."
    )
    parser.add_argument("--nsteps", type=int, default=30, help="Number of separations in sweep.")
    parser.add_argument("--res", type=int, default=10, help="Resolution of the simulations.")
    parser.add_argument("--nmax", type=int, default=3, help="Max moments used in the simulations.")
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Simulation step budget recorded in the run parameters."
    )
    args = parser.parse_args()
    if args.nsteps <= 0 or args.res <= 0 or args.nmax <= 0:
        parser.error("--nsteps, --res, and --nmax must be positive.")
    if args.max_steps is not None and args.max_steps <= 0:
        parser.error("--max-steps must be positive.")

    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = f"results_{now_str}"
    os.makedirs(outdir, exist_ok=True)

    with open(os.path.join(outdir, "parameters.txt"), "w") as f:
        f.write(f"--nsteps {args.nsteps}\n")
        f.write(f"--res {args.res}\n")
        f.write(f"--nmax {args.nmax}\n")
        if args.max_steps is not None:
            f.write(f"--max-steps {args.max_steps}\n")

    separations = np.logspace(np.log10(0.02), np.log10(1.0), args.nsteps)
    generations = [1, 2, 3, 4]
    materials = ["PEC", "Gold", "Silicon"]
    temperatures = [0, 77, 300]

    pfa_data = {}
    pfa_path = ".tmp/pfa_results.json"
    if os.path.isfile(pfa_path):
        try:
            with open(pfa_path, "r") as f:
                pfa_data = json.load(f)
            if not isinstance(pfa_data, dict):
                raise ValueError("PFA data must be a JSON object.")
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"Notice: Cannot load PFA baseline: {exc}. Using analytical baseline.")
            pfa_data = {}

    # Use only simulations at the explicitly requested resolution.
    meep_data = {}
    source_files = {}
    if os.path.isdir(".tmp"):
        for filename in sorted(os.listdir(".tmp")):
            if not filename.startswith("meep_d_") or not filename.endswith(".json"):
                continue
            if "check" in filename or "calculate" in filename:
                continue
            filepath = os.path.join(".tmp", filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Simulation data must be a JSON object.")
                resolution = finite_number(data.get("resolution", 10))
                if resolution != args.res:
                    continue
                d = finite_number(data["d_um"])
                n = finite_number(data["N"])
                material = data["material"]
                force = finite_number(data["force_subtracted"])
                if d <= 0 or not n.is_integer():
                    raise ValueError("Invalid separation or generation.")
                if not isinstance(material, str) or material not in materials:
                    raise ValueError("Unknown material.")
                if int(n) not in generations:
                    continue
                key = (d, int(n), material)
                meep_data[key] = force
                source_files[key] = filepath
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
                print(f"Error reading {filename}: {exc}")

    if not meep_data:
        raise RuntimeError(
            f"[ERROR: RUN_DATA_MISSING] No valid FDTD simulation outputs "
            f"at resolution {args.res} were found in .tmp."
        )

    sim_distances = sorted({key[0] for key in meep_data})
    sim_forces = {}
    missing = []
    for mat in materials:
        sim_forces[mat] = {}
        for N in generations:
            values = []
            for d in sim_distances:
                matches = [
                    (abs(key[0] - d), force)
                    for key, force in meep_data.items()
                    if abs(key[0] - d) < 1e-4 and key[1] == N and key[2] == mat
                ]
                val = min(matches, key=lambda item: item[0])[1] if matches else None
                if val is None:
                    missing.append(f"material={mat}, N={N}, d={d:.6g} um")
                values.append(val)
            sim_forces[mat][N] = values

    if missing:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] Incomplete FDTD simulation sweep: "
            + "; ".join(missing)
        )

    log_sim_d = np.log(np.asarray(sim_distances, dtype=float))
    baselines = {}
    ratios = {}
    for mat in materials:
        f1 = np.asarray(sim_forces[mat][1], dtype=float)
        if np.any(f1 == 0):
            raise RuntimeError(
                f"[ERROR: RUN_DATA_MISSING] Material {mat} has a zero N=1 force; "
                "the simulation baseline cannot normalize generation ratios."
            )

        log_abs_f1 = np.log(np.abs(f1))
        same_sign = np.all(np.sign(f1) == np.sign(f1[0]))

        def get_base(d_val, f1=f1, log_abs_f1=log_abs_f1, same_sign=same_sign):
            log_d = np.log(d_val)
            if same_sign:
                return np.sign(f1[0]) * np.exp(np.interp(log_d, log_sim_d, log_abs_f1))
            # A sign-changing baseline cannot be interpolated purely in log-force space.
            return np.interp(log_d, log_sim_d, f1)

        baselines[mat] = get_base
        ratios[mat] = {}
        for N in generations:
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                r_sim = np.asarray(sim_forces[mat][N], dtype=float) / f1
            if not np.all(np.isfinite(r_sim)):
                raise RuntimeError(
                    f"[ERROR: RUN_DATA_MISSING] Invalid simulation ratios for {mat}, N={N}."
                )

            def get_ratio(d_val, r_sim=r_sim):
                return np.interp(np.log(d_val), log_sim_d, r_sim)

            ratios[mat][N] = get_ratio

    def interpolate_pfa(d_val, mat, T, N):
        """Validate and interpolate each PFA series on its own distance grid."""
        try:
            pts = pfa_data[mat][f"T_{T}"][f"N_{N}"]
            if not isinstance(pts, list) or not pts:
                return None
            pairs = sorted(
                (finite_number(pt["d_nm"]), finite_number(pt["force_val"]))
                for pt in pts
            )
            distances = np.asarray([pair[0] for pair in pairs])
            forces = np.asarray([pair[1] for pair in pairs])
            if np.any(distances <= 0) or np.any(np.diff(distances) <= 0):
                return None
            value = float(np.interp(d_val * 1000.0, distances, forces))
            return value if np.isfinite(value) else None
        except (KeyError, TypeError, ValueError, OverflowError):
            return None

    def get_thermal_factor(d_val, mat, T):
        if T == 0:
            return 1.0
        f_T = interpolate_pfa(d_val, mat, T, 1)
        f_0 = interpolate_pfa(d_val, mat, 0, 1)
        if f_T is not None and f_0 is not None:
            factor = safe_ratio(f_T, f_0)
            if np.isfinite(factor):
                return factor
        thermal_wavelength = 7.6 * (300.0 / T)
        return 1.0 + 0.35 * (d_val / thermal_wavelength)**2

    compiled_dataset = {
        "metadata": {
            "title": "Effective Trace Framework for Self-Similar Casimir Systems 3D Simulation Sweep",
            "model": "Casimir FDTD",
            "dataset": "compiled_casimir_dataset.json",
            "unit_force": "dimensionless Meep units",
            "force_to_nN": MEEP_FORCE_TO_NN,
            "unit_distance": "microns",
            "notes": (
                "force_exact contains finite-resolution simulation interpolations; "
                "N=0 is the infinite flat-plate PFA baseline. No N=infinity data "
                "are inferred. Undefined fractional deviations are null."
            )
        },
        "data": []
    }

    for mat in materials:
        for T in temperatures:
            for d in separations:
                pfa_force_N1 = interpolate_pfa(d, mat, T, 1)
                if pfa_force_N1 is None:
                    pfa_force_N1 = compute_pfa_force(d, 1, mat, T)

                compiled_dataset["data"].append({
                    "material": mat,
                    "temperature_K": T,
                    "generation_N": 0,
                    "separation_um": float(d),
                    "force_exact": float(pfa_force_N1),
                    "force_pfa": float(pfa_force_N1),
                    "fractional_deviation": 0.0 if pfa_force_N1 != 0 else None
                })

                theta = get_thermal_factor(d, mat, T)
                for N in generations:
                    sim_force = baselines[mat](d) * ratios[mat][N](d) * theta
                    pfa_force = interpolate_pfa(d, mat, T, N)
                    if pfa_force is None:
                        pfa_force = compute_pfa_force(d, N, mat, T)
                    if not np.isfinite(sim_force) or not np.isfinite(pfa_force):
                        raise RuntimeError(
                            f"[ERROR: RUN_DATA_MISSING] Nonfinite compiled force "
                            f"for {mat}, N={N}, T={T}, d={d}."
                        )
                    deviation = fractional_deviation(sim_force, pfa_force)
                    compiled_dataset["data"].append({
                        "material": mat,
                        "temperature_K": T,
                        "generation_N": N,
                        "separation_um": float(d),
                        "force_exact": float(sim_force),
                        "force_pfa": float(pfa_force),
                        "fractional_deviation": float(deviation) if np.isfinite(deviation) else None
                    })

    dataset_file = os.path.join(outdir, "compiled_casimir_dataset.json")
    with open(dataset_file, "w") as f:
        json.dump(compiled_dataset, f, indent=4, allow_nan=False)

    dataset_hash = compute_sha256(dataset_file)
    log_file = os.path.join(outdir, "dataset_reproducibility.log")
    with open(log_file, "w") as f:
        f.write("Dataset File: compiled_casimir_dataset.json\n")
        f.write(f"SHA-256 Hash: {dataset_hash}\n")
        f.write(f"Date Logged: {datetime.date.today().strftime('%Y-%m-%d')}\n")
    print(f"Cryptographic reproducibility log created: {log_file} (Hash: {dataset_hash})")

    provenance = {
        "model": "Casimir FDTD",
        "dataset": os.path.basename(dataset_file),
        "dataset_sha256": dataset_hash,
        "executed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "parameters": vars(args),
        "force_unit": "nN",
        "force_conversion": MEEP_FORCE_TO_NN,
        "simulation_sources": [
            {"file": path, "sha256": compute_sha256(path)}
            for path in sorted(set(source_files.values()))
        ]
    }
    if os.path.isfile(pfa_path):
        provenance["pfa_source"] = {
            "file": pfa_path,
            "sha256": compute_sha256(pfa_path)
        }

    def save_figure(fig, basename, tight=True):
        for extension in ("pdf", "svg"):
            path = os.path.join(outdir, f"{basename}.{extension}")
            kwargs = {"bbox_inches": "tight"} if tight else {}
            fig.savefig(path, format=extension, dpi=300, **kwargs)
            save_plot_provenance(path, provenance)
        plt.close(fig)

    def select_points(mat, T, N):
        return sorted(
            [
                x for x in compiled_dataset["data"]
                if x["material"] == mat and x["temperature_K"] == T
                and x["generation_N"] == N
            ],
            key=lambda x: x["separation_um"]
        )

    print("Generating publication-quality figures...")
    colors = ['#2c3e50', '#2980b9', '#16a085', '#c0392b']

    for mat in materials:
        print(f"Generating figures for {mat}...")
        pts_0 = select_points(mat, 0, 0)
        d_nm_0 = [x["separation_um"] * 1000.0 for x in pts_0]
        force_nN_0 = [abs(x["force_exact"]) * MEEP_FORCE_TO_NN for x in pts_0]
        f_base_nN = [abs(baselines[mat](d)) * MEEP_FORCE_TO_NN for d in separations]

        fig1, ax1 = plt.subplots(figsize=(4.8, 3.2))
        ax1.plot(d_nm_0, force_nN_0, color='black', linewidth=1.5, zorder=1)
        ax1.plot(
            separations * 1000.0, f_base_nN,
            color='#7f8c8d', linewidth=1.5, zorder=1
        )

        for idx, N in enumerate(generations):
            pts = select_points(mat, 0, N)
            d_nm = [x["separation_um"] * 1000.0 for x in pts]
            force_nN = [abs(x["force_exact"]) * MEEP_FORCE_TO_NN for x in pts]
            ax1.plot(d_nm, force_nN, color=colors[idx], linewidth=1.2, zorder=2)

            f_ideal_pts = []
            for x in pts:
                d_val = x["separation_um"]
                f_id = (
                    baselines[mat](d_val) * ((8.0 / 9.0)**(N - 1))
                    * (1.0 + get_eta(d_val, N)) / (1.0 + get_eta(d_val, 1))
                )
                f_ideal_pts.append(abs(f_id) * MEEP_FORCE_TO_NN)
            ax1.plot(
                d_nm, f_ideal_pts, linestyle='--', color=colors[idx],
                linewidth=1.0, alpha=0.7, zorder=1
            )
            sim_force_nN = [abs(f) * MEEP_FORCE_TO_NN for f in sim_forces[mat][N]]
            ax1.scatter(
                np.asarray(sim_distances) * 1000.0, sim_force_nN,
                marker='o', s=15, facecolors='none', edgecolors=colors[idx], zorder=3
            )

        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel('Separation d (nm)')
        ax1.set_ylabel('Casimir Force |F| (nN)')
        ax1.set_title(f'Force vs. Distance ({mat}, T = 0 K)', fontsize=9, fontweight='bold')
        ax1.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)

        legend_elements_F1 = [
            Line2D([0], [0], color='black', linewidth=1.5, label='N = 0 (Infinite)'),
            Line2D([0], [0], color='#7f8c8d', linewidth=1.5, label='N = 0 (Finite)'),
            Line2D([0], [0], color='gray', linewidth=1.2, label='Finite-Res Theory'),
            Line2D([0], [0], color='gray', linestyle='--', linewidth=1.0, label='Ideal Theory'),
            Line2D(
                [0], [0], color='gray', marker='o', linestyle='None', markersize=4,
                markerfacecolor='none', markeredgecolor='gray', label='FDTD Simulation'
            ),
        ] + [
            Line2D([0], [0], color=colors[idx], label=f'N = {N}')
            for idx, N in enumerate(generations)
        ]
        ax1.legend(
            handles=legend_elements_F1, bbox_to_anchor=(1.05, 1), loc='upper left',
            frameon=True, edgecolor='none', facecolor='#f5f5f5'
        )
        save_figure(fig1, f'figure1_force_vs_distance_{mat}')

        fig2, (ax_main, ax_zoom) = plt.subplots(1, 2, figsize=(9.6, 3.2))
        fig2.subplots_adjust(wspace=0.7)
        ax_main.axhline(0, color='black', linewidth=1.5, zorder=1)
        dev_finite_0 = [
            fractional_deviation(force, baseline)
            for force, baseline in zip(f_base_nN, force_nN_0)
        ]
        ax_main.plot(
            separations * 1000.0, dev_finite_0,
            color='#7f8c8d', linewidth=1.5, zorder=1
        )
        pfa_d_pts = [p0["separation_um"] for p0 in pts_0]
        pfa_f_pts = [p0["force_pfa"] for p0 in pts_0]

        for idx, N in enumerate(generations):
            pts = select_points(mat, 0, N)
            d_nm = [x["separation_um"] * 1000.0 for x in pts]
            dev_finite = [
                fractional_deviation(x["force_exact"], pts_0[i]["force_pfa"])
                for i, x in enumerate(pts)
            ]
            ax_main.plot(d_nm, dev_finite, color=colors[idx], linewidth=1.2, zorder=2)
            dev_ideal = [
                (8.0 / 9.0)**(N - 1) * (1.0 + get_eta(x["separation_um"], N)) - 1.0
                for x in pts
            ]
            ax_main.plot(
                d_nm, dev_ideal, linestyle='--', color=colors[idx],
                linewidth=1.0, alpha=0.7, zorder=1
            )
            sim_dev = [
                fractional_deviation(
                    sim_forces[mat][N][i], np.interp(d_val, pfa_d_pts, pfa_f_pts)
                )
                for i, d_val in enumerate(sim_distances)
            ]
            ax_main.scatter(
                np.asarray(sim_distances) * 1000.0, sim_dev,
                marker='o', s=15, facecolors='none', edgecolors=colors[idx], zorder=3
            )

        ax_main.set_xscale('log')
        ax_main.set_xlabel('Separation d (nm)')
        ax_main.set_ylabel('Fractional PFA Deviation (F - F_{PFA}) / F_{PFA}')
        ax_main.set_title(f'A: Macroscopic PFA Suppression ({mat})', fontsize=8, fontweight='bold')
        ax_main.set_ylim(-1.1, 3.5)
        ax_main.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
        ax_main.legend(
            handles=legend_elements_F1, bbox_to_anchor=(1.02, 1), loc='upper left',
            frameon=True, edgecolor='none', facecolor='#f5f5f5'
        )

        ax_zoom.axhline(0, color='#7f8c8d', linewidth=1.5, zorder=1)
        pts_1 = select_points(mat, 0, 1)
        for idx, N in enumerate(generations):
            pts = select_points(mat, 0, N)
            d_nm = [x["separation_um"] * 1000.0 for x in pts]
            dev_finite_B = [
                fractional_deviation(x["force_exact"], pts_1[i]["force_exact"])
                for i, x in enumerate(pts)
            ]
            ax_zoom.plot(d_nm, dev_finite_B, color=colors[idx], linewidth=1.2, zorder=2)
            dev_ideal_B = [
                (8.0 / 9.0)**(N - 1) * (1.0 + get_eta(x["separation_um"], N))
                / (1.0 + get_eta(x["separation_um"], 1)) - 1.0
                for x in pts
            ]
            ax_zoom.plot(
                d_nm, dev_ideal_B, linestyle='--', color=colors[idx],
                linewidth=1.0, alpha=0.7, zorder=1
            )
            sim_dev_B = [
                fractional_deviation(force, baseline)
                for force, baseline in zip(sim_forces[mat][N], sim_forces[mat][1])
            ]
            ax_zoom.scatter(
                np.asarray(sim_distances) * 1000.0, sim_dev_B,
                marker='o', s=15, facecolors='none', edgecolors=colors[idx], zorder=3
            )

        ax_zoom.set_xscale('log')
        ax_zoom.set_xlabel('Separation d (nm)')
        ax_zoom.set_ylabel('Relative Deviation (F - F_1) / F_1')
        ax_zoom.set_title(f'B: Zoomed Corrections ({mat})', fontsize=8, fontweight='bold')
        ax_zoom.set_ylim(-0.65, 0.05)
        ax_zoom.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
        ax_zoom.legend(
            handles=legend_elements_F1[1:], bbox_to_anchor=(1.02, 1), loc='upper left',
            frameon=True, edgecolor='none', facecolor='#f5f5f5'
        )
        save_figure(fig2, f'figure2_pfa_deviation_{mat}')

        fig3, ax3 = plt.subplots(figsize=(3.5, 3.2))
        for T in [77, 300]:
            pts_T = select_points(mat, T, 3)
            pts_0_T = select_points(mat, 0, 3)
            d_nm = [x["separation_um"] * 1000.0 for x in pts_T]
            ratio = [
                safe_ratio(x["force_exact"], pts_0_T[i]["force_exact"])
                for i, x in enumerate(pts_T)
            ]
            ax3.plot(
                d_nm, ratio, label=f"T = {T} K", linewidth=1.2,
                color='#2980b9' if T == 77 else '#c0392b'
            )
        ax3.set_xscale('log')
        ax3.set_xlabel('Separation d (nm)')
        ax3.set_ylabel('Thermal Correction Factor F(T) / F(0)')
        ax3.set_title(
            f'Finite-Temperature Corrections ({mat}, N = 3)',
            fontsize=9, fontweight='bold'
        )
        ax3.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
        ax3.legend(loc='upper left', frameon=True, edgecolor='none', facecolor='#f5f5f5')
        fig3.tight_layout()
        save_figure(fig3, f'figure3_matsubara_corrections_{mat}', tight=False)

    fig4, (ax4_a, ax4_b) = plt.subplots(1, 2, figsize=(9.6, 3.2))
    fig4.subplots_adjust(wspace=0.7)
    mat_colors = {'PEC': '#1e3799', 'Gold': '#d35400', 'Silicon': '#27ae60'}

    for mat in materials:
        pts_T300 = select_points(mat, 300, 3)
        d_nm_A = [x["separation_um"] * 1000.0 for x in pts_T300]
        force_nN_A = [abs(x["force_exact"]) * MEEP_FORCE_TO_NN for x in pts_T300]
        ax4_a.plot(
            d_nm_A, force_nN_A, color=mat_colors[mat],
            linewidth=1.2, zorder=2, label=mat
        )
        sim_force_nN_A = [
            abs(sim_forces[mat][3][i] * get_thermal_factor(d_val, mat, 300))
            * MEEP_FORCE_TO_NN
            for i, d_val in enumerate(sim_distances)
        ]
        ax4_a.scatter(
            np.asarray(sim_distances) * 1000.0, sim_force_nN_A,
            marker='o', s=15, facecolors='none', edgecolors=mat_colors[mat], zorder=3
        )

    ax4_a.set_xscale('log')
    ax4_a.set_yscale('log')
    ax4_a.set_xlabel('Separation d (nm)')
    ax4_a.set_ylabel('Casimir Force |F| (nN)')
    ax4_a.set_title(
        'A: Absolute Force at Room Temp (T = 300 K, N = 3)',
        fontsize=8, fontweight='bold'
    )
    ax4_a.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    ax4_a.legend(loc='lower left', frameon=True, edgecolor='none', facecolor='#f5f5f5')

    for mat in materials:
        pts_3 = select_points(mat, 0, 3)
        pts_1 = select_points(mat, 0, 1)
        d_nm_B = [x["separation_um"] * 1000.0 for x in pts_3]
        dev_finite_B = [
            fractional_deviation(x["force_exact"], pts_1[i]["force_exact"])
            for i, x in enumerate(pts_3)
        ]
        ax4_b.plot(
            d_nm_B, dev_finite_B, color=mat_colors[mat],
            linewidth=1.2, zorder=2, label=mat
        )
        dev_ideal_B = [
            (8.0 / 9.0)**2 * (1.0 + get_eta(x["separation_um"], 3))
            / (1.0 + get_eta(x["separation_um"], 1)) - 1.0
            for x in pts_3
        ]
        ax4_b.plot(
            d_nm_B, dev_ideal_B, linestyle='--', color=mat_colors[mat],
            linewidth=1.0, alpha=0.7, zorder=1
        )
        sim_dev_B = [
            fractional_deviation(force, baseline)
            for force, baseline in zip(sim_forces[mat][3], sim_forces[mat][1])
        ]
        ax4_b.scatter(
            np.asarray(sim_distances) * 1000.0, sim_dev_B,
            marker='o', s=15, facecolors='none', edgecolors=mat_colors[mat], zorder=3
        )

    ax4_b.set_xscale('log')
    ax4_b.set_xlabel('Separation d (nm)')
    ax4_b.set_ylabel('Relative Deviation (F - F_1) / F_1')
    ax4_b.set_title(
        'B: Material Suppression of Fractal Scaling (T = 0 K, N = 3)',
        fontsize=8, fontweight='bold'
    )
    ax4_b.set_ylim(-0.4, 0.05)
    ax4_b.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    legend_elements_B = [
        Line2D([0], [0], color='gray', linewidth=1.2, label='Finite-Res Theory'),
        Line2D([0], [0], color='gray', linestyle='--', linewidth=1.0, label='Ideal Theory'),
        Line2D(
            [0], [0], color='gray', marker='o', linestyle='None', markersize=4,
            markerfacecolor='none', markeredgecolor='gray', label='FDTD Simulation'
        ),
    ] + [
        Line2D([0], [0], color=mat_colors[mat], label=mat) for mat in materials
    ]
    ax4_b.legend(
        handles=legend_elements_B, bbox_to_anchor=(1.02, 1), loc='upper left',
        frameon=True, edgecolor='none', facecolor='#f5f5f5'
    )
    save_figure(fig4, 'figure4_material_comparison')

    summary = {
        "model": "Casimir FDTD",
        "dataset": os.path.basename(dataset_file),
        "status": "completed",
        "executed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset_sha256": dataset_hash,
        "record_count": len(compiled_dataset["data"]),
        "parameters": vars(args)
    }
    with open(os.path.join(outdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=4, allow_nan=False)
    log_metrics(summary, os.path.join(outdir, "metrics.json"))

    print(f"Postprocessing complete. Output files generated in {outdir}:")
    print("  - compiled_casimir_dataset.json (dataset)")
    print("  - dataset_reproducibility.log (SHA-256 validation log)")
    for mat in materials:
        print(f"  - figure1_force_vs_distance_{mat}.pdf / .svg")
        print(f"  - figure2_pfa_deviation_{mat}.pdf / .svg")
        print(f"  - figure3_matsubara_corrections_{mat}.pdf / .svg")
    print("  - figure4_material_comparison.pdf / .svg")
    print("  - plot provenance sidecars")
    print("  - summary.json / metrics.json")
    print("  - parameters.txt (run parameters log)")


if __name__ == "__main__":
    main()
