import os
import glob
import json
import argparse
import datetime
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from scipy.interpolate import griddata
from scipy.spatial import QhullError

try:
    from utils.metrics_logger import log_metrics
except ImportError:
    def log_metrics(metrics):
        """Persist metrics when the shared logging utility is unavailable."""
        path = "quantum_gravity_trace_analysis/pipeline3_metrics.jsonl"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, allow_nan=False) + "\n")

try:
    from utils.plot_provenance import save_plot_provenance
except ImportError:
    def save_plot_provenance(plot_path, metadata):
        """Persist provenance when the shared plotting utility is unavailable."""
        with open(str(plot_path) + ".provenance.json", "w", encoding="utf-8") as f:
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

HBAR = 1.054571817e-34
C_LIGHT = 299792458.0
MEEP_TO_PA = 0.0316152649
C_EFF = 0.0108


def safe_norm(arr):
    values = np.asarray(arr, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    vmin, vmax = np.min(values), np.max(values)
    if vmin < 0 and vmax > 0:
        return TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
    return None


def vacuum_energy_density(d_m):
    """Return a finite, nonzero SI baseline, or None for invalid gaps."""
    if not np.isfinite(d_m) or d_m <= 0:
        return None
    with np.errstate(over='ignore', under='ignore', divide='ignore', invalid='ignore'):
        rho = -(HBAR * C_LIGHT * C_EFF) / np.float64(d_m) ** 4
    if not np.isfinite(rho) or rho == 0:
        return None
    return float(rho)


def analyze_nec_boundaries(
    summary_path=None,
    out_dir="quantum_gravity_trace_analysis/figures",
    json_out="quantum_gravity_trace_analysis/pipeline3_nec_boundary_summary.json",
    max_steps=None
):
    print('==================================================')
    print('PIPELINE 3: NULL ENERGY CONDITION (NEC) & ENERGY INVERSION MAPPER')
    print('==================================================')

    if max_steps is not None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0:
            raise ValueError("--max-steps must be a nonnegative integer.")

    if summary_path is not None:
        if not os.path.isfile(summary_path):
            raise RuntimeError(
                f"[ERROR: RUN_DATA_MISSING] Summary file not found: {summary_path}"
            )
        target_files = [summary_path]
    else:
        target_files = sorted(glob.glob(
            "results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json"
        ))
        if not target_files:
            target_files = sorted(glob.glob("results_*/sweet_spot_sweep_summary.json"))
        target_files = [path for path in target_files if os.path.isfile(path)]

    if not target_files:
        raise RuntimeError(
            "[ERROR: RUN_DATA_MISSING] No sweet spot sweep summary JSON file found."
        )

    latest_file = target_files[-1]
    print(f"Loading dataset from '{latest_file}'...")
    try:
        with open(latest_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"[ERROR: RUN_DATA_MISSING] Summary file not found: {latest_file}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError("Sweep summary must contain a JSON list of records.")

    records = data if max_steps is None else data[:max_steps]

    # Prefer the explicit raw Meep field in post-fix summaries; their
    # pressure_Pa field is already SI and must not be converted again.
    # Legacy summaries store raw Meep pressures under pressure_Pa or pressure.
    # Convert raw values exactly once; all downstream pressures are SI.
    curves = {}
    skipped_records = 0
    for r in records:
        if not isinstance(r, dict):
            skipped_records += 1
            continue
        try:
            alpha = float(r.get('alpha_deg', r.get('alpha', 75.0)))
            theta = float(r.get('theta_deg', r.get('theta', 90.0)))
            d_um = float(r.get('d_um', r.get('d', 0.1)))
            raw_pressure = float(r.get(
                'pressure_meep', r.get('pressure_Pa', r.get('pressure', 0.0))
            ))
        except (TypeError, ValueError, OverflowError):
            skipped_records += 1
            continue

        if not all(np.isfinite(v) for v in (alpha, theta, d_um, raw_pressure)):
            skipped_records += 1
            continue

        d_m = d_um * 1e-6
        rho_vac_pa = vacuum_energy_density(d_m)
        p_pa = raw_pressure * MEEP_TO_PA
        if rho_vac_pa is None or not np.isfinite(d_um * 1000.0):
            skipped_records += 1
            continue

        with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
            nec_val = np.float64(rho_vac_pa) + p_pa
            eta = np.float64(p_pa) / abs(rho_vac_pa)
        if not all(np.isfinite(v) for v in (p_pa, nec_val, eta)):
            skipped_records += 1
            continue

        key = (round(alpha, 1), round(theta, 1))
        curves.setdefault(key, []).append({
            'd_um': d_um,
            'd_m': d_m,
            'pressure_Pa': p_pa
        })

    nec_analysis = []
    print("\n--- Evaluating Null Energy Condition (NEC_z = rho_vac + P_z) ---")

    for (alpha, theta), pts in sorted(curves.items()):
        pts.sort(key=lambda x: x['d_um'])
        if len(pts) >= 2:
            d_nm_list = []
            p_list = []
            nec_list = []
            ratio_list = []

            for p in pts:
                d_nm = p['d_um'] * 1000.0
                p_z = p['pressure_Pa']
                rho_vac_pa = vacuum_energy_density(p['d_m'])

                nec_val = rho_vac_pa + p_z
                eta = p_z / abs(rho_vac_pa)

                d_nm_list.append(d_nm)
                p_list.append(p_z)
                nec_list.append(nec_val)
                ratio_list.append(eta)

            max_p = max(p_list)
            max_nec = max(nec_list)
            max_eta = max(ratio_list)
            is_nec_restored = bool(max_p > 0 and max_nec >= 0)

            rec = {
                'alpha_deg': alpha,
                'theta_deg': theta,
                'max_pressure_Pa': float(max_p),
                'max_nec_val_Pa': float(max_nec),
                'max_restoration_ratio_eta': float(max_eta),
                'is_repulsive': bool(max_p > 0),
                'is_nec_restored': is_nec_restored,
                'curve_points': [
                    {
                        'd_nm': round(d_nm_list[i], 2),
                        'pressure_Pa': p_list[i],
                        'nec_z_Pa': nec_list[i],
                        'eta': ratio_list[i]
                    }
                    for i in range(len(d_nm_list))
                ]
            }
            nec_analysis.append(rec)
            status = "RESTORED (NEC >= 0)" if is_nec_restored else "Violated (Standard QFT)"
            print(
                f"  Alpha={alpha:4.1f} deg, Theta={theta:4.1f} deg "
                f"=> P_max={max_p:+.4f} Pa | Status: {status}"
            )

    executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    provenance = {
        'model': 'pipeline3_nec_boundary_mapper',
        'dataset': str(latest_file),
        'status': 'completed',
        'executed_at': executed_at,
        'pressure_conversion_meep_to_pa': MEEP_TO_PA,
        'max_steps': max_steps
    }
    summary_data = {
        **provenance,
        'metadata': {
            **provenance,
            'dataset_source': str(latest_file),
            'timestamp': executed_at,
            'total_configurations': len(nec_analysis),
            'processed_records': len(records),
            'skipped_records': skipped_records,
            'note': (
                'NEC_z = rho_vac + P_z, with both terms in Pa. '
                'When P_z >= |rho_vac|, NEC is locally restored in vacuum.'
            )
        },
        'nec_configurations': nec_analysis
    }
    os.makedirs(os.path.dirname(os.fspath(json_out)) or ".", exist_ok=True)
    with open(json_out, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=4, allow_nan=False)
    print(f"\nSaved Pipeline 3 summary dataset to '{json_out}'.")

    plot_nec_figures(curves, nec_analysis, out_dir, provenance=provenance)
    log_metrics({
        **provenance,
        'total_configurations': len(nec_analysis),
        'nec_restored_configurations': sum(
            r['is_nec_restored'] for r in nec_analysis
        ),
        'repulsive_configurations': sum(r['is_repulsive'] for r in nec_analysis),
        'processed_records': len(records),
        'skipped_records': skipped_records
    })
    print("Pipeline 3 analysis completed successfully!")


def plot_nec_figures(curves, nec_results, out_dir, provenance=None):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.4))
    fig.subplots_adjust(wspace=0.35)

    rep_thetas = [80.0, 82.0, 90.0, 92.0, 94.0]
    colors = ['#1e3799', '#0984e3', '#00b894', '#e17055', '#d63031']
    plotted_pressures = []
    plotted_gaps = []

    for idx, th in enumerate(rep_thetas):
        key = (75.0, th)
        if key in curves:
            pts = sorted(curves[key], key=lambda x: x['d_um'])
            valid_pts = [
                p for p in pts
                if np.isfinite(p['d_um'] * 1000.0)
                and np.isfinite(p['pressure_Pa'])
            ]
            d_nm = [p['d_um'] * 1000.0 for p in valid_pts]
            p_vals = [p['pressure_Pa'] for p in valid_pts]
            if not p_vals:
                continue
            plotted_pressures.extend(p_vals)
            plotted_gaps.extend(d_nm)
            ax1.plot(
                d_nm, p_vals, 'o-', color=colors[idx],
                label=f'$\\theta = {th:.0f}^\\circ$',
                linewidth=1.2, markersize=3.5
            )

    if plotted_pressures:
        ymin, ymax = min(plotted_pressures), max(plotted_pressures)
        span = ymax - ymin
        margin = 0.15 * (span if span > 0 else max(abs(ymin), 1e-6))
        ax1.set_ylim(ymin - margin, ymax + margin)
    else:
        ax1.set_ylim(-0.03, 0.03)
        ax1.text(
            0.5, 0.5, 'No representative curves available',
            transform=ax1.transAxes, ha='center', va='center'
        )

    ax1.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.7)
    ax1.axhspan(0, max(ax1.get_ylim()[1], 0), color='green', alpha=0.08,
                label='Repulsive stress (P > 0)')
    ax1.axhspan(min(ax1.get_ylim()[0], 0), 0, color='red', alpha=0.05,
                label='Attractive stress (P < 0)')

    ax1.set_xlabel(r'Cavity Gap $d$ (nm)')
    ax1.set_ylabel(r'Normal Stress / NEC Driver $P_z$ (Pa)')
    ax1.set_title(
        r'(a) Null Energy Driver $P_z(d)$ ($\alpha = 75^\circ$)',
        fontweight='bold'
    )
    ax1.set_xlim(
        min([50.0] + plotted_gaps),
        max([350.0] + plotted_gaps)
    )
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.legend(
        loc='lower right', frameon=True, facecolor='#f5f5f5',
        edgecolor='none', fontsize=6.5
    )

    ax2.set_xlabel(r'Optical Axis Twist Angle $\theta$ (deg)')
    ax2.set_ylabel(r'Corrugation Wall Slope $\alpha$ (deg)')
    ax2.set_title(r'(b) Maximum Normal Stress $(\alpha, \theta)$', fontweight='bold')

    if len(nec_results) >= 4:
        alphas = np.array([p['alpha_deg'] for p in nec_results], dtype=float)
        thetas = np.array([p['theta_deg'] for p in nec_results], dtype=float)
        p_maxs = np.array([p['max_pressure_Pa'] for p in nec_results], dtype=float)
        valid = np.isfinite(alphas) & np.isfinite(thetas) & np.isfinite(p_maxs)
        alphas, thetas, p_maxs = alphas[valid], thetas[valid], p_maxs[valid]

        if p_maxs.size:
            grid_a, grid_th = np.mgrid[70:75:50j, 80:94:50j]
            try:
                grid_p = griddata(
                    (alphas, thetas), p_maxs, (grid_a, grid_th), method='linear'
                )
            except QhullError:
                grid_p = griddata(
                    (alphas, thetas), p_maxs, (grid_a, grid_th), method='nearest'
                )

            if np.any(np.isfinite(grid_p)):
                im = ax2.imshow(
                    np.ma.masked_invalid(grid_p), extent=[80, 94, 70, 75],
                    origin='lower', aspect='auto', cmap='RdYlGn',
                    norm=safe_norm(grid_p)
                )
            else:
                im = ax2.scatter(
                    thetas, alphas, c=p_maxs, cmap='RdYlGn',
                    norm=safe_norm(p_maxs), edgecolor='black', s=25
                )
            cbar = fig.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
            cbar.set_label(r'Maximum Pressure $P_{\mathrm{max}}$ (Pa)', fontsize=7)
            ax2.scatter(thetas, alphas, c='white', edgecolor='black', s=25, zorder=4)
        else:
            ax2.text(0.5, 0.5, 'No finite phase data', transform=ax2.transAxes,
                     ha='center', va='center')
    else:
        ax2.text(0.5, 0.5, 'Insufficient data for phase interpolation',
                 transform=ax2.transAxes, ha='center', va='center')

    os.makedirs(out_dir, exist_ok=True)
    out_png = os.path.join(out_dir, 'figure_qg_pipeline3_nec_boundaries.png')
    out_pdf = os.path.join(out_dir, 'figure_qg_pipeline3_nec_boundaries.pdf')
    plot_metadata = dict(provenance or {
        'model': 'pipeline3_nec_boundary_mapper',
        'dataset': 'in_memory',
        'status': 'completed',
        'executed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'pressure_conversion_meep_to_pa': MEEP_TO_PA
    })
    try:
        for path in (out_png, out_pdf):
            fig.savefig(path, dpi=300, bbox_inches='tight')
            save_plot_provenance(path, plot_metadata)
    finally:
        plt.close(fig)

    print("Saved Pipeline 3 publication plots:")
    print(f"  - {out_png}")
    print(f"  - {out_pdf}")


def nonnegative_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return parsed


def main():
    parser = argparse.ArgumentParser(
        description='Pipeline 3: Null Energy Condition (NEC) & Energy Inversion Mapper'
    )
    parser.add_argument('--summary', type=str, default=None,
                        help='Path to sweet_spot_sweep_summary.json')
    parser.add_argument('--out-dir', type=str,
                        default='quantum_gravity_trace_analysis/figures',
                        help='Output directory for plots')
    parser.add_argument(
        '--json-out', type=str,
        default='quantum_gravity_trace_analysis/pipeline3_nec_boundary_summary.json',
        help='Output JSON summary path'
    )
    parser.add_argument('--max-steps', type=nonnegative_int, default=None,
                        help='Maximum number of input records to process (default: all)')
    args = parser.parse_args()

    analyze_nec_boundaries(
        summary_path=args.summary, out_dir=args.out_dir,
        json_out=args.json_out, max_steps=args.max_steps
    )


if __name__ == '__main__':
    main()
