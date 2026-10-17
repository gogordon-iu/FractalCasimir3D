"""
Publication-quality post-processing for the Nature Refutation Suite.

Figures are generated only from recorded simulation results. Missing, malformed,
or non-finite required data cause an explicit error; no placeholder plots or
synthetic visibility curves are generated.

--max-steps limits the number of figures rendered (default: all four).
"""

import argparse
import glob
import hashlib
import inspect
import json
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 7.5,
    "axes.labelsize": 8,
    "axes.titlesize": 8.5,
    "legend.fontsize": 6.5,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "lines.linewidth": 1.2,
    "axes.linewidth": 0.8,
})

RESULTS_DIR = "results"


def _data_error(message):
    return RuntimeError(f"[ERROR: RUN_DATA_MISSING] {message}")


def _load_json(path):
    if not os.path.isfile(path):
        raise _data_error(f"Required results file is missing: {path}")
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as exc:
        raise _data_error(f"Cannot read results file {path}: {exc}") from exc
    if not isinstance(data, (dict, list)) or not data:
        raise _data_error(f"Results file contains no usable records: {path}")
    return data


def _walk_dicts(data):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _walk_dicts(value)
    elif isinstance(data, list):
        for value in data:
            yield from _walk_dicts(value)


def _numeric(value):
    """Reject booleans, strings, complex values, NaNs, and infinities."""
    if isinstance(value, (bool, str, bytes)) or value is None:
        raise ValueError("Expected finite numerical data")
    array = np.asarray(value)
    if array.dtype.kind not in "iuf":
        raise ValueError("Expected real numerical data")
    array = array.astype(float)
    if not np.all(np.isfinite(array)):
        raise ValueError("Numerical data contain NaN or infinity")
    return array


def _first(record, names):
    for name in names:
        if name in record:
            return record[name]
    raise KeyError(names[0])


def _series(data, x_names, y_names, description):
    """Read paired arrays or scalar records, without synthesizing samples."""
    points = []
    for record in _walk_dicts(data):
        if not any(name in record for name in x_names):
            continue
        if not any(name in record for name in y_names):
            continue
        try:
            x = _numeric(_first(record, x_names))
            y = _numeric(_first(record, y_names))
            if x.ndim > 1 or y.ndim > 1 or x.shape != y.shape:
                raise ValueError("Coordinates and values must have matching shapes")
            points.extend(zip(x.reshape(-1), y.reshape(-1)))
        except (ValueError, TypeError, OverflowError) as exc:
            raise _data_error(f"Invalid {description}: {exc}") from exc
    if not points:
        raise _data_error(f"No recorded {description}")
    points = np.asarray(points, dtype=float)
    return points[np.argsort(points[:, 0], kind="stable")].T


def _matrix(record):
    try:
        matrix = _numeric(_first(
            record, ("stiffness_matrix", "stiffness_matrix_6x6", "K", "K_6x6")
        ))
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise _data_error(f"Invalid recorded stiffness matrix: {exc}") from exc
    if matrix.shape != (6, 6):
        raise _data_error("Recorded stiffness matrix must have shape (6, 6)")
    if not np.allclose(matrix, matrix.T, rtol=1e-7, atol=1e-12):
        raise _data_error("Recorded stiffness matrix is not symmetric")
    return matrix


def _style(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(True, linestyle=":", alpha=0.5)


def save_plot_provenance(out_base, source_files, details):
    """Save source hashes and transformations alongside every exported figure."""
    sources = []
    for path in sorted(set(source_files)):
        with open(path, "rb") as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        sources.append({
            "path": os.path.abspath(path),
            "sha256": digest,
        })
    provenance = {
        "figure": out_base,
        "outputs": [f"{out_base}.pdf", f"{out_base}.svg"],
        "sources": sources,
        "details": details,
    }
    with open(f"{out_base}.provenance.json", "w", encoding="utf-8") as stream:
        json.dump(provenance, stream, indent=2, allow_nan=False)


def _save_figure(fig, out_base, sources, details):
    try:
        fig.savefig(f"{out_base}.pdf", bbox_inches="tight")
        fig.savefig(f"{out_base}.svg", bbox_inches="tight")
        save_plot_provenance(out_base, sources, details)
    finally:
        plt.close(fig)
    print(f"Rendered: {out_base}.pdf / .svg")


def generate_figure1_convergence(data_dir="results_nature_validation"):
    """Grid convergence and standoff sweeps from recorded FDTD outputs."""
    files = sorted(set(
        glob.glob(os.path.join(data_dir, "*task1*.json"))
        + glob.glob(os.path.join(data_dir, "*conv*.json"))
        + glob.glob(os.path.join(RESULTS_DIR, "*task1*.json"))
        + glob.glob(os.path.join(RESULTS_DIR, "*conv*.json"))
    ))
    report_path = os.path.join(RESULTS_DIR, "nature_6step_narrative_report.json")
    if os.path.isfile(report_path):
        files.append(report_path)
    if not files:
        raise _data_error("No recorded FDTD convergence or standoff results")

    records = [
        record
        for path in files
        for record in _walk_dicts(_load_json(path))
    ]
    curves = []
    for radius in (0.0, 2.0, 5.0, 10.0, 20.0):
        selected = []
        for record in records:
            if "r_tip_nm" not in record or "resolution" not in record:
                continue
            try:
                tip = _numeric(record["r_tip_nm"])
                if tip.ndim != 0:
                    raise ValueError("Tip radius must be a scalar")
            except (ValueError, TypeError, OverflowError) as exc:
                raise _data_error(f"Invalid tip radius: {exc}") from exc
            if abs(float(tip) - radius) < 0.1:
                selected.append(record)
        if selected:
            resolution, pressure = _series(
                selected, ("resolution",), ("pressure_Pa",),
                f"FDTD convergence data for tip radius {radius:g} nm",
            )
            if np.any(resolution <= 0):
                raise _data_error("FDTD resolutions must be positive")
            curves.append((radius, 1000.0 / resolution, pressure))
    if not curves:
        raise _data_error("No recorded tip-radius convergence sweeps")
    offsets, pressures = _series(
        records, ("delta_s_nm",), ("pressure_Pa",), "FDTD standoff sweep"
    )

    fig = plt.figure(figsize=(7.2, 2.5), dpi=300)
    gs = gridspec.GridSpec(
        1, 3, wspace=0.35, left=0.08, right=0.96, bottom=0.18, top=0.88
    )
    ax1 = fig.add_subplot(gs[0, 0])
    for radius, cell_size, pressure in curves:
        order = np.argsort(cell_size)
        ax1.plot(
            cell_size[order], pressure[order], "o-", markersize=3.5,
            label=f"$r_{{tip}} = {radius:g}$ nm",
        )
    _style(
        ax1, r"Grid cell size $\Delta x$ (nm)", "Casimir Pressure $P$ (Pa)",
        "(a) Yee Grid & Tip Rounding",
    )
    ax1.legend(loc="upper right", frameon=False, ncol=2)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(offsets, pressures, "s-", color="#2ca02c", markersize=4)
    _style(
        ax2, r"Surface offset $\delta_s$ (nm)", "Casimir Pressure $P$ (Pa)",
        "(b) Standoff Invariance",
    )

    # Explicit analytical reference, not a simulated convergence result.
    ax3 = fig.add_subplot(gs[0, 2])
    angles = np.linspace(90, 330, 100)
    ax3.plot(angles, 180.0 / angles, color="#d62728",
             label=r"Analytical $\nu = \pi/\beta$")
    ax3.axhline(1, color="gray", linestyle="--", label="Smooth boundary")
    ax3.axvline(255, color="blue", linestyle=":", label="Pyramid wedge")
    _style(
        ax3, r"Exterior wedge angle $\beta$ (deg)", r"Field exponent $\nu$",
        "(c) Analytical Wedge Reference",
    )
    ax3.legend(loc="upper right", frameon=False)
    _save_figure(
        fig, "nature_fig1_corner_convergence", files,
        {"grid_cell_size_nm": "1000 / recorded resolution",
         "panel_c": "Analytical electrostatic wedge reference: nu = pi / beta"},
    )


def generate_figure2_dispersion():
    """Plot recorded permittivity and dispersive pressure results."""
    path = os.path.join(RESULTS_DIR, "anisotropic_dispersive_lifshitz.json")
    data = _load_json(path)
    permittivity = [
        _series(data, ("xi_eV", "imaginary_frequency_eV"), names, label)
        for names, label in (
            (("eps_x", "epsilon_xx"), "armchair permittivity"),
            (("eps_y", "epsilon_yy"), "zigzag permittivity"),
            (("eps_z", "epsilon_zz"), "out-of-plane permittivity"),
        )
    ]
    for frequency, epsilon in permittivity:
        if np.any(frequency <= 0) or np.any(epsilon <= 0):
            raise _data_error("Logarithmic permittivity axes require positive data")
    angles, twist_pressure = _series(
        data, ("theta_deg", "thetas_deg", "twist_angle_deg"),
        ("pressure_Pa", "pressures_Pa"), "dispersive twist sweep",
    )
    distances, distance_pressure = _series(
        data, ("d_nm", "ds_nm", "separation_nm"),
        ("pressure_Pa", "pressures_Pa"), "dispersive distance sweep",
    )
    if np.any(distances <= 0):
        raise _data_error("Plate separations must be positive")

    fig = plt.figure(figsize=(7.2, 2.5), dpi=300)
    gs = gridspec.GridSpec(
        1, 3, wspace=0.35, left=0.08, right=0.96, bottom=0.18, top=0.88
    )
    ax1 = fig.add_subplot(gs[0, 0])
    for (frequency, epsilon), label in zip(
        permittivity, ("Armchair", "Zigzag", "Out-of-plane")
    ):
        ax1.loglog(frequency, epsilon, label=label)
    _style(
        ax1, r"Imaginary frequency $\hbar\xi$ (eV)",
        r"Permittivity $\varepsilon(i\xi)$", "(a) Recorded Dispersion",
    )
    ax1.legend(frameon=False)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(angles, twist_pressure, "o-", markersize=3.5)
    ax2.axhline(0, color="k", linestyle=":", linewidth=0.8)
    _style(
        ax2, r"Twist angle $\theta$ (deg)", "Casimir Pressure $P$ (Pa)",
        "(b) Dispersive Force vs Twist Angle",
    )

    ax3 = fig.add_subplot(gs[0, 2])
    ax3.plot(distances, distance_pressure, "o-", markersize=3.5)
    ax3.axhline(0, color="k", linestyle=":", linewidth=0.8)
    _style(
        ax3, "Plate separation $d$ (nm)", "Casimir Pressure $P$ (Pa)",
        "(c) Dispersive Force vs Distance",
    )
    _save_figure(fig, "nature_fig2_material_dispersion", [path],
                 {"data": "Recorded permittivity and pressure sweeps"})


def generate_figure3_stability():
    """Plot recorded stiffness matrices and their signed local potential."""
    path = os.path.join(RESULTS_DIR, "stability_6dof_analysis.json")
    data = _load_json(path)
    matrices = []
    for record in _walk_dicts(data):
        if not any(key in record for key in (
            "stiffness_matrix", "stiffness_matrix_6x6", "K", "K_6x6"
        )):
            continue
        if not any(key in record for key in ("d_eq_nm", "d_eq_um")):
            continue
        try:
            if "d_eq_nm" in record:
                gap = _numeric(record["d_eq_nm"])
            else:
                gap = _numeric(record["d_eq_um"]) * 1000.0
            if gap.ndim != 0 or float(gap) <= 0:
                raise ValueError("Equilibrium gap must be a positive scalar")
        except (ValueError, TypeError, OverflowError) as exc:
            raise _data_error(f"Invalid equilibrium gap: {exc}") from exc
        matrices.append((float(gap), _matrix(record)))
    if not matrices:
        raise _data_error("No stiffness matrices with recorded equilibrium gaps")
    matrices.sort(key=lambda item: item[0])
    gaps = np.array([gap for gap, _ in matrices])
    eigs = np.array([np.linalg.eigvalsh(matrix) for _, matrix in matrices])
    gap, K = min(matrices, key=lambda item: abs(item[0] - 150.0))

    fig = plt.figure(figsize=(7.2, 2.5), dpi=300)
    gs = gridspec.GridSpec(
        1, 3, wspace=0.38, left=0.08, right=0.96, bottom=0.18, top=0.88
    )
    ax1 = fig.add_subplot(gs[0, 0])
    norm_K = np.log10(np.abs(K) + 1.0) * np.sign(K)
    limit = max(float(np.max(np.abs(norm_K))), 1e-12)
    image = ax1.imshow(norm_K, cmap="coolwarm", vmin=-limit, vmax=limit)
    labels = ["$x$", "$y$", "$z$", r"$\theta_x$", r"$\theta_y$", r"$\theta_z$"]
    ax1.set_xticks(range(6), labels)
    ax1.set_yticks(range(6), labels)
    ax1.set_title("(a) Recorded Stiffness Matrix", loc="left", fontweight="bold")
    fig.colorbar(image, ax=ax1, fraction=0.046, pad=0.04).set_label(
        r"$\mathrm{sgn}(K)\log_{10}(1+|K|)$", fontsize=6.5
    )

    ax2 = fig.add_subplot(gs[0, 1])
    for index in range(6):
        ax2.plot(gaps, eigs[:, index], "o-", markersize=3,
                 label=f"$\\lambda_{index + 1}$")
    ax2.axhline(0, color="k", linestyle=":", linewidth=0.8)
    _style(
        ax2, "Equilibrium gap $d_{eq}$ (nm)",
        "Eigenvalue (recorded generalized units)", "(b) 6-DOF Eigenspectrum",
    )
    ax2.legend(frameon=False, ncol=2)

    ax3 = fig.add_subplot(gs[0, 2])
    offsets = np.linspace(-0.2, 0.2, 50)
    X, Y = np.meshgrid(offsets, offsets)
    # Preserve signed stiffness and lateral coupling; pN * um = 0.001 fJ.
    U = 0.5 * (K[0, 0] * X**2 + 2 * K[0, 1] * X * Y + K[1, 1] * Y**2)
    U *= 1e-3
    if np.ptp(U) == 0:
        extent = max(abs(float(U.flat[0])), 1.0) * 1e-12
        levels = np.linspace(float(U.flat[0]) - extent,
                             float(U.flat[0]) + extent, 15)
    else:
        levels = 15
    contour = ax3.contourf(X * 1000, Y * 1000, U, levels=levels, cmap="viridis")
    _style(
        ax3, r"Lateral offset $\Delta x$ (nm)", r"Lateral offset $\Delta y$ (nm)",
        "(c) Local Quadratic Potential",
    )
    fig.colorbar(contour, ax=ax3, fraction=0.046, pad=0.04).set_label(
        "Energy $U$ (fJ)", fontsize=6.5
    )
    _save_figure(
        fig, "nature_fig3_6dof_stability_matrix", [path],
        {"selected_gap_nm": gap,
         "panel_c": "Signed lateral quadratic form of recorded K; not a global trap",
         "lateral_stiffness_units": "pN/um"},
    )


def generate_figure4_thermal_dsi():
    """Plot recorded thermal pressure, DSI modulation, and visibility."""
    path = os.path.join(RESULTS_DIR, "thermal_matsubara_dsi.json")
    data = _load_json(path)
    thermal = []
    modulation = []
    for temperature in (4.0, 77.0, 300.0):
        selected = []
        for record in _walk_dicts(data):
            if not any(key in record for key in ("T_K", "temperature_K", "T")):
                continue
            try:
                value = _numeric(_first(record, ("T_K", "temperature_K", "T")))
                if value.ndim != 0:
                    raise ValueError("Temperature must be a scalar")
            except (ValueError, TypeError, OverflowError) as exc:
                raise _data_error(f"Invalid recorded temperature: {exc}") from exc
            if np.isclose(float(value), temperature):
                selected.append(record)
        distances, pressure = _series(
            selected, ("d_nm", "ds_nm", "separation_nm"),
            ("total_pressure_Pa", "pressure_Pa", "pressures_Pa"),
            f"thermal pressure at {temperature:g} K",
        )
        if np.any(distances <= 0):
            raise _data_error("Thermal separations must be positive")
        thermal.append((temperature, distances, pressure))
        if temperature in (4.0, 300.0):
            log_distance, periodic_pressure = _series(
                selected, ("ln_d", "ln_d_over_lstar"),
                ("dsi_modulation_Pa", "periodic_pressure_Pa", "delta_pressure_Pa"),
                f"measured DSI modulation at {temperature:g} K",
            )
            modulation.append((temperature, log_distance, periodic_pressure))

    crossover, visibility = _series(
        data, ("chi_T", "thermal_crossover"),
        ("visibility_percent", "dsi_visibility_percent", "visibility_pct"),
        "DSI visibility percentages",
    )
    if np.any(crossover < 0) or np.any((visibility < 0) | (visibility > 100)):
        raise _data_error("Invalid thermal crossover or visibility percentage")

    fig = plt.figure(figsize=(7.2, 2.5), dpi=300)
    gs = gridspec.GridSpec(
        1, 3, wspace=0.35, left=0.08, right=0.96, bottom=0.18, top=0.88
    )
    ax1 = fig.add_subplot(gs[0, 0])
    for temperature, distances, pressure in thermal:
        ax1.plot(distances, pressure, label=f"$T = {temperature:g}$ K")
    ax1.set_xscale("log")
    ax1.axhline(0, color="k", linestyle=":", linewidth=0.8)
    _style(
        ax1, "Separation $d$ (nm)", "Casimir Pressure $P$ (Pa)",
        "(a) Finite-$T$ Matsubara Force",
    )
    ax1.legend(frameon=False)

    ax2 = fig.add_subplot(gs[0, 1])
    for temperature, log_distance, pressure in modulation:
        ax2.plot(log_distance, pressure, label=f"$T = {temperature:g}$ K")
    _style(
        ax2, r"$\ln(d / \ell_*)$", r"DSI Modulation $\Delta P_{\mathrm{per}}$ (Pa)",
        "(b) Recorded Log-Periodic Modulations",
    )
    ax2.legend(frameon=False)

    ax3 = fig.add_subplot(gs[0, 2])
    ax3.plot(crossover, visibility, "o-", color="#d62728", markersize=3)
    _style(
        ax3, r"Thermal crossover $\chi_T = d / \lambda_T$",
        "DSI Visibility (%)", "(c) Recorded DSI Visibility",
    )
    ax3.set_ylim(0, 105)
    _save_figure(
        fig, "nature_fig4_thermal_dsi_matsubara", [path],
        {"data": "Recorded thermal pressures, DSI modulation, and visibility",
         "synthetic_visibility": False},
    )


def _call_metrics_function(function, metrics, step):
    """Support dictionary-based logging without masking logger failures."""
    signature = inspect.signature(function)
    candidates = (
        ((), {"metrics": metrics, "step": step}),
        ((), {"metrics": metrics}),
        ((metrics,), {"step": step}),
        ((metrics,), {}),
    )
    for args, kwargs in candidates:
        try:
            signature.bind(*args, **kwargs)
        except TypeError:
            continue
        function(*args, **kwargs)
        return
    raise RuntimeError("utils.metrics_logger has no supported metrics interface")


def _log_metrics(metrics, step):
    from utils import metrics_logger

    function = getattr(metrics_logger, "log_metrics", None)
    if callable(function):
        _call_metrics_function(function, metrics, step)
        return

    logger_class = getattr(metrics_logger, "MetricsLogger", None)
    if logger_class is None:
        raise RuntimeError("utils.metrics_logger must expose log_metrics or MetricsLogger")
    signature = inspect.signature(logger_class)
    try:
        signature.bind()
    except TypeError as exc:
        raise RuntimeError(
            "MetricsLogger requires configuration; supply a module-level "
            "log_metrics(metrics, step) interface for this postprocessor"
        ) from exc
    logger = logger_class()
    for name in ("log_metrics", "log"):
        function = getattr(logger, name, None)
        if callable(function):
            _call_metrics_function(function, metrics, step)
            return
    raise RuntimeError("MetricsLogger has no supported dictionary logging method")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps", type=int, default=4,
        help="Maximum number of figures to render, from 0 to 4 (default: 4).",
    )
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be non-negative")

    generators = (
        generate_figure1_convergence,
        generate_figure2_dispersion,
        generate_figure3_stability,
        generate_figure4_thermal_dsi,
    )
    print("POST-PROCESSING & RENDERING NATURE PUBLICATION FIGURES")
    completed = 0
    _log_metrics({"figures_rendered": completed}, step=0)
    for step, generate in enumerate(generators[:args.max_steps], start=1):
        generate()
        completed = step
        _log_metrics({"figures_rendered": completed}, step=step)
    print(f"{completed} Nature publication figures rendered in PDF & SVG formats.")


if __name__ == "__main__":
    main()
