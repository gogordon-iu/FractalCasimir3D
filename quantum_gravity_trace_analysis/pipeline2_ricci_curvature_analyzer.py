import os
import glob
import json
import argparse
import datetime
import logging

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from scipy.interpolate import griddata
from scipy.spatial import QhullError

try:
    from utils.metrics_logger import log_metrics
except ImportError:
    def log_metrics(metrics):
        logging.getLogger(__name__).info("Pipeline 2 metrics: %s", metrics)

try:
    from utils.plot_provenance import save_plot_provenance
except ImportError:
    def save_plot_provenance(plot_path, metadata):
        with open(os.fspath(plot_path) + ".provenance.json", "w") as f:
            json.dump(metadata, f, indent=4, allow_nan=False)


plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 8
plt.rcParams['axes.labelsize'] = 8
plt.rcParams['axes.titlesize'] = 9
plt.rcParams['legend.fontsize'] = 7
plt.rcParams['xtick.labelsize'] = 7
plt.rcParams['ytick.labelsize'] = 7
plt.rcParams['pdf.fonttype'] = 42

# Physical Constants (SI)
HBAR = 1.054571817e-34  # J*s
C_LIGHT = 299792458.0  # m/s
G_NEWTON = 6.67430e-11  # m^3 / (kg * s^2)
L_PLANCK = np.sqrt(HBAR * G_NEWTON / (C_LIGHT**3))
MEEP_TO_PA = 0.0316152649


def safe_norm(arr):
    values = np.asarray(arr, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    vmin, vmax = np.min(values), np.max(values)
    if vmin < 0 and vmax > 0:
        return TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
    return None


def analyze_ricci_curvature(
    summary_path=None,
    out_dir="quantum_gravity_trace_analysis/figures",
    json_out="quantum_gravity_trace_analysis/pipeline2_ricci_curvature_summary.json",
    max_steps=None,
):
    print('==================================================')
    print('PIPELINE 2: PARAMETER-SPACE RICCI CURVATURE & QUANTUM GRAVITY ANALYZER')
    print('==================================================')

    if max_steps is not None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, (int, np.integer)):
            raise TypeError("max_steps must be an integer or None.")
        if max_steps < 0:
            raise ValueError("max_steps must be nonnegative.")

    # 1. Locate summary files.
    if summary_path is not None:
        if not os.path.isfile(summary_path):
            raise RuntimeError(
                f"[ERROR: RUN_DATA_MISSING] Summary file not found: {summary_path}"
            )
        target_files = [os.fspath(summary_path)]
    else:
        target_files = sorted(
            glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json")
        )
        if not target_files:
            target_files = sorted(
                glob.glob("results_*/sweet_spot_sweep_summary.json")
            )

    if not target_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No sweet spot sweep summary JSON file found."
        )

    latest_file = target_files[-1]
    print(f"Loading empirical dataset from '{latest_file}'...")
    try:
        with open(latest_file, 'r') as f:
            payload = json.load(f)
    except OSError as exc:
        raise RuntimeError(
            f"[ERROR: RUN_DATA_MISSING] Cannot read summary file: {latest_file}"
        ) from exc

    source_metadata = {}
    if isinstance(payload, dict):
        source_metadata = payload.get('metadata', {})
        if not isinstance(source_metadata, dict):
            source_metadata = {}
        data = payload.get('results', payload.get('data'))
    else:
        data = payload

    if not isinstance(data, list):
        raise ValueError("Summary JSON must contain a list of parameter points.")

    print(f"Loaded {len(data)} total parameter points.")

    # Detect legacy, unscaled Meep pressure across the dataset, not separately
    # for each point: otherwise small pressures near zero get different units.
    legacy_pressures = []
    for r in data:
        if not isinstance(r, dict):
            continue
        if (
            'pressure_Pa_SI' in r
            or 'pressure_meep' in r
            or 'pressure_meep_raw' in r
        ):
            continue
        try:
            pressure = float(r.get('pressure_Pa', r.get('pressure', 0.0)))
        except (TypeError, ValueError, OverflowError):
            continue
        if np.isfinite(pressure):
            legacy_pressures.append(abs(pressure))

    pressure_units = str(
        source_metadata.get('pressure_units', '')
    ).strip().lower()
    if pressure_units in ('pa', 'si', 'pascal', 'pascals'):
        legacy_is_meep = False
    elif pressure_units in ('meep', 'meep_raw', 'unscaled'):
        legacy_is_meep = True
    else:
        legacy_is_meep = bool(
            legacy_pressures and max(legacy_pressures) > 0.5
        )

    if max_steps is not None:
        data = data[:max_steps]

    # 2. Group by (alpha, theta) to extract SI pressure curves P(d).
    curves = {}
    skipped_points = 0
    for r in data:
        if not isinstance(r, dict):
            skipped_points += 1
            continue
        try:
            alpha = float(r.get('alpha_deg', r.get('alpha', 75.0)))
            theta = float(r.get('theta_deg', r.get('theta', 90.0)))
            d_um = float(r.get('d_um', r.get('d', 0.1)))

            if 'pressure_Pa_SI' in r:
                p_pa = float(r['pressure_Pa_SI'])
                p_raw = float(
                    r.get('pressure_meep', r.get('pressure_meep_raw', p_pa / MEEP_TO_PA))
                )
            elif 'pressure_meep' in r:
                p_raw = float(r['pressure_meep'])
                # Post-fix summaries already store pressure_Pa in SI units.
                p_pa = float(r.get('pressure_Pa', p_raw * MEEP_TO_PA))
            elif 'pressure_meep_raw' in r:
                p_raw = float(r['pressure_meep_raw'])
                p_pa = p_raw * MEEP_TO_PA
            else:
                pressure = float(r.get('pressure_Pa', r.get('pressure', 0.0)))
                p_raw = pressure if legacy_is_meep else pressure / MEEP_TO_PA
                p_pa = pressure * MEEP_TO_PA if legacy_is_meep else pressure

            d_m = d_um * 1e-6
        except (TypeError, ValueError, OverflowError):
            skipped_points += 1
            continue

        if not all(np.isfinite(v) for v in (alpha, theta, d_um, d_m, p_pa, p_raw)):
            skipped_points += 1
            continue
        if d_m <= 0:
            skipped_points += 1
            continue

        key = (round(alpha, 1), round(theta, 1))
        curves.setdefault(key, []).append({
            'd_um': d_um,
            'd_m': d_m,
            'pressure_Pa': p_pa,
            'pressure_Pa_SI': p_pa,
            'pressure_meep_raw': p_raw,
            'is_repulsive': p_pa > 0,
        })

    # 3. Find stable equilibria and estimate the trace from the local gradient.
    equilibrium_results = []
    print("\n--- Identifying Levitation Equilibrium Points & Levitation-Locked Curvatures ---")

    for (alpha, theta), pts in sorted(curves.items()):
        pts.sort(key=lambda x: x['d_um'])
        if len(pts) < 2:
            continue

        p_max = max(p['pressure_Pa_SI'] for p in pts)
        for left, right in zip(pts, pts[1:]):
            p1, p2 = left['pressure_Pa_SI'], right['pressure_Pa_SI']
            d1, d2 = left['d_m'], right['d_m']
            if not (p1 > 0 and p2 < 0) or d2 <= d1:
                continue

            with np.errstate(over='ignore', divide='ignore', invalid='ignore',
                             under='ignore'):
                # Magnitude-scaled interpolation avoids overflowing p1 - p2.
                scale = max(abs(p1), abs(p2))
                fraction = (p1 / scale) / (p1 / scale - p2 / scale)
                d_eq_m = np.float64(d1 + fraction * (d2 - d1))
                dP_dd = (np.float64(p2) - p1) / (d2 - d1)
                stiffness_kappa = -dP_dd

                # Local pressure-gradient estimate of the effective anomaly.
                # This is an empirical closure, not an exact reconstruction of
                # C(d): pressure alone fixes 3*C - dC/dln(d), and its slope
                # does not independently determine C without a boundary
                # condition. Record the closure explicitly in the output.
                T_trace_Pa = -d_eq_m * dP_dd
                dC_dln_d = -(d_eq_m**4 / (HBAR * C_LIGHT)) * T_trace_Pa

                # At equilibrium, 3*C_eq = dC/dln(d). The corresponding
                # effective energy density is therefore -T_trace/3.
                C_eff_eq = dC_dln_d / 3.0
                rho_vac_J_m3 = -T_trace_Pa / 3.0
                Ricci_R_m2 = (
                    -(8.0 * np.pi * G_NEWTON / C_LIGHT**4) * T_trace_Pa
                )
                Ricci_Planck_dimless = Ricci_R_m2 * d_eq_m**2
                d_eq_um = d_eq_m * 1e6
                d_eq_nm = d_eq_m * 1e9

            values = (
                d_eq_m, d_eq_um, d_eq_nm, stiffness_kappa, dC_dln_d,
                C_eff_eq, rho_vac_J_m3, T_trace_Pa, Ricci_R_m2,
                Ricci_Planck_dimless,
            )
            if d_eq_m <= 0 or not all(np.isfinite(v) for v in values):
                continue

            rec = {
                'alpha_deg': alpha,
                'theta_deg': theta,
                'd_eq_nm': round(float(d_eq_nm), 2),
                'd_eq_um': round(float(d_eq_um), 4),
                'stiffness_kappa_Pa_per_m': float(stiffness_kappa),
                'p_max_repulsive_Pa': float(p_max),
                'dC_dln_d': float(dC_dln_d),
                'C_eff_eq': float(C_eff_eq),
                'rho_vac_J_m3': float(rho_vac_J_m3),
                'T_trace_Pa': float(T_trace_Pa),
                'T_trace_J_m3': float(T_trace_Pa),
                'Ricci_scalar_R_m2': float(Ricci_R_m2),
                'Ricci_Planck_scaled': float(Ricci_Planck_dimless),
            }
            equilibrium_results.append(rec)
            print(
                f"  Alpha={alpha:4.1f} deg, Theta={theta:4.1f} deg "
                f"=> d_eq={d_eq_nm:6.2f} nm | P_max={p_max:+.4f} Pa "
                f"| R={Ricci_R_m2:+.4e} m^-2"
            )

    # 4. Save analysis JSON, including corrected input pressures.
    executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    model = source_metadata.get('model', 'pipeline2_ricci_curvature_analyzer')
    dataset = source_metadata.get('dataset', latest_file)
    metadata = {
        'model': model,
        'dataset': dataset,
        'status': 'completed',
        'executed_at': executed_at,
        'dataset_source': latest_file,
        'timestamp': executed_at,
        'num_equilibrium_points': len(equilibrium_results),
        'num_processed_points': sum(len(pts) for pts in curves.values()),
        'num_skipped_points': skipped_points,
        'max_steps': max_steps,
        'MEEP_TO_PA': MEEP_TO_PA,
        'legacy_pressure_interpretation': 'meep_raw' if legacy_is_meep else 'SI',
        'trace_estimator': 'local_gradient_closure: T_trace_Pa = -d_eq * dP/dd',
        'note': (
            'T_trace = -(hbar*c/d_eq^4)*dC_dln_d; '
            'R = -8*pi*G*T_trace/c^4. dC_dln_d is estimated using a '
            'local-gradient closure, not a hardcoded vacuum coefficient.'
        ),
    }
    pressure_points = []
    for (alpha, theta), pts in sorted(curves.items()):
        pressure_points.extend(
            dict(p, alpha_deg=alpha, theta_deg=theta) for p in pts
        )

    summary_data = {
        'model': model,
        'dataset': dataset,
        'status': 'completed',
        'executed_at': executed_at,
        'metadata': metadata,
        'pressure_points': pressure_points,
        'equilibrium_curvature_points': equilibrium_results,
    }
    os.makedirs(os.path.dirname(os.fspath(json_out)) or '.', exist_ok=True)
    with open(json_out, 'w') as f:
        json.dump(summary_data, f, indent=4, allow_nan=False)
    print(f"\nSaved Pipeline 2 summary dataset to '{json_out}'.")

    # 5. Generate publication plots and record source provenance.
    plot_ricci_curvature_figures(curves, equilibrium_results, out_dir)
    for extension in ('png', 'pdf'):
        plot_path = os.path.join(
            out_dir, f'figure_qg_pipeline2_ricci_curvature.{extension}'
        )
        save_plot_provenance(plot_path, metadata)

    log_metrics({
        'model': model,
        'dataset': dataset,
        'status': 'completed',
        'executed_at': executed_at,
        'num_equilibrium_points': len(equilibrium_results),
        'num_processed_points': metadata['num_processed_points'],
        'num_skipped_points': skipped_points,
    })
    print("Pipeline 2 analysis completed successfully!")


def plot_ricci_curvature_figures(curves, eq_points, out_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.4))
    fig.subplots_adjust(wspace=0.35)

    rep_thetas = [80.0, 82.0, 90.0, 92.0, 94.0]
    colors = ['#1e3799', '#0984e3', '#00b894', '#e17055', '#d63031']

    for idx, th in enumerate(rep_thetas):
        key = (75.0, th)
        if key in curves and curves[key]:
            pts = sorted(curves[key], key=lambda x: x['d_um'])
            d_nm = [p['d_um'] * 1000.0 for p in pts]
            p_vals = [p['pressure_Pa'] for p in pts]
            ax1.plot(
                d_nm, p_vals, 'o-', color=colors[idx],
                label=f'$\\theta = {th:.0f}^\\circ$',
                linewidth=1.2, markersize=3.5,
            )

    ax1.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.7)
    for eq in eq_points:
        if eq['alpha_deg'] == 75.0 and eq['theta_deg'] in rep_thetas:
            ax1.scatter(
                [eq['d_eq_nm']], [0.0], color='gold', edgecolor='black',
                s=50, zorder=5, marker='*',
            )

    ax1.set_xlabel(r'Cavity Gap $d$ (nm)')
    ax1.set_ylabel(r'Casimir Normal Pressure $P_\perp$ (Pa)')
    ax1.set_title(
        r'(a) Casimir Pressure & Zero-Force Levitation ($\alpha = 75^\circ$)',
        fontweight='bold',
    )
    ax1.set_ylim(-0.04, 0.04)
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    if ax1.get_legend_handles_labels()[0]:
        ax1.legend(
            loc='lower right', frameon=True,
            facecolor='#f5f5f5', edgecolor='none',
        )

    if eq_points:
        alphas = np.array([p['alpha_deg'] for p in eq_points])
        thetas = np.array([p['theta_deg'] for p in eq_points])
        d_eqs = np.array([p['d_eq_nm'] for p in eq_points])
        grid_d = None

        if len(eq_points) >= 4:
            grid_a, grid_th = np.mgrid[70:75:50j, 80:94:50j]
            try:
                grid_d = griddata(
                    (alphas, thetas), d_eqs, (grid_a, grid_th), method='linear'
                )
            except (QhullError, ValueError):
                # Collinear or duplicate parameter points cannot form a
                # two-dimensional triangulation; display empirical data.
                grid_d = None

        if grid_d is not None and np.any(np.isfinite(grid_d)):
            im = ax2.imshow(
                grid_d, extent=[80, 94, 70, 75], origin='lower',
                aspect='auto', cmap='plasma',
            )
            ax2.scatter(
                thetas, alphas, c='white', edgecolor='black', s=25, zorder=4
            )
        else:
            im = ax2.scatter(
                thetas, alphas, c=d_eqs, cmap='plasma',
                edgecolor='black', s=25, zorder=4,
            )

        cbar = fig.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
        cbar.set_label(
            r'Stable Levitation Height $d_{\mathrm{eq}}$ (nm)', fontsize=7
        )
        for p in eq_points:
            ax2.annotate(
                f"{p['d_eq_nm']:.0f}nm", (p['theta_deg'], p['alpha_deg']),
                textcoords="offset points", xytext=(0, 4), ha='center',
                fontsize=6, color='black', weight='bold',
            )
    else:
        ax2.text(
            0.5, 0.5, 'No stable equilibrium points',
            transform=ax2.transAxes, ha='center', va='center',
        )

    ax2.set_xlabel(r'Optical Axis Twist Angle $\theta$ (deg)')
    ax2.set_ylabel(r'Corrugation Wall Slope $\alpha$ (deg)')
    ax2.set_title(
        r'(b) Levitation-Locked Metric State Space $d_{\mathrm{eq}}(\alpha, \theta)$',
        fontweight='bold',
    )

    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, 'figure_qg_pipeline2_ricci_curvature.png')
    out_pdf = os.path.join(out_dir, 'figure_qg_pipeline2_ricci_curvature.pdf')
    try:
        fig.savefig(out_png, dpi=300, bbox_inches='tight')
        fig.savefig(out_pdf, dpi=300, bbox_inches='tight')
    finally:
        plt.close(fig)
    print("Saved Pipeline 2 publication plots:")
    print(f"  - {out_png}")
    print(f"  - {out_pdf}")


def main():
    parser = argparse.ArgumentParser(
        description='Pipeline 2: Parameter-Space Ricci Curvature & Quantum Gravity Analyzer'
    )
    parser.add_argument(
        '--summary', type=str, default=None,
        help='Path to sweet_spot_sweep_summary.json',
    )
    parser.add_argument(
        '--out-dir', type=str, default='quantum_gravity_trace_analysis/figures',
        help='Output directory for plots',
    )
    parser.add_argument(
        '--json-out', type=str,
        default='quantum_gravity_trace_analysis/pipeline2_ricci_curvature_summary.json',
        help='Output JSON summary path',
    )
    parser.add_argument(
        '--max-steps', type=int, default=None,
        help='Maximum number of input parameter points to process',
    )
    args = parser.parse_args()
    if args.max_steps is not None and args.max_steps < 0:
        parser.error('--max-steps must be nonnegative')

    analyze_ricci_curvature(
        summary_path=args.summary,
        out_dir=args.out_dir,
        json_out=args.json_out,
        max_steps=args.max_steps,
    )


if __name__ == '__main__':
    main()
