import os
import glob
import json
import argparse
import datetime
import logging
import numbers

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

try:
    from utils.metrics_logger import log_step, log_metric, export_macros
except ImportError:
    _logged_metrics = {}

    def log_step(step):
        logging.getLogger(__name__).info("Step: %s", step)

    def log_metric(name, value):
        _logged_metrics[name] = value
        logging.getLogger(__name__).info("%s: %s", name, value)

    def export_macros(path):
        with open(path, "w", encoding="utf-8") as handle:
            for name, value in sorted(_logged_metrics.items()):
                macro = "".join(character for character in name if character.isalpha())
                if macro:
                    handle.write(f"\\newcommand{{\\{macro}}}{{{value}}}\n")

try:
    from utils.plot_provenance import save_plot_provenance
except ImportError:
    def save_plot_provenance(path, metadata):
        with open(str(path) + ".provenance.json", "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=4, allow_nan=False)


plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 8
plt.rcParams['axes.labelsize'] = 8
plt.rcParams['axes.titlesize'] = 9
plt.rcParams['legend.fontsize'] = 7
plt.rcParams['xtick.labelsize'] = 7
plt.rcParams['ytick.labelsize'] = 7
plt.rcParams['pdf.fonttype'] = 42

MEEP_TO_PA = 0.0316152649
HBAR = 1.054571817e-34
LIGHT_SPEED = 299792458.0
SWEEP_PATH = 'results/sweet_spot_sweep_summary.json'
EMPIRICAL_PATHS = (
    SWEEP_PATH,
    '.tmp/sweet_spot_sweep_summary.json',
    'results/experiment_provenance_registry.json',
)


def _run_data_error(message):
    return RuntimeError(f'[ERROR: RUN_DATA_MISSING] {message}')


def _finite_number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f'{name} must be a finite real number.')
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f'{name} must be a finite real number.')
    return value


def _positive_integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise ValueError(f'{name} must be a positive integer.')
    value = int(value)
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer.')
    return value


def _first_present(record, keys):
    for key in keys:
        if key in record:
            return key, record[key]
    return None, None


def _load_empirical_trace(d_um, path=SWEEP_PATH, max_steps=None):
    """
    Read the dimensionless pressure coefficient C(d) and differentiate in ln(d).

    For pressure-only records, the coefficient convention is
        P(d) = -(hbar*c / d**4) * C(d).
    Explicit C records take precedence over pressure records. Bare `d` and
    `gap` values default to micrometres; bare pressures default to Meep units.
    `pressure_Pa_SI` is SI; `pressure_Pa` is SI only when accompanied by
    `pressure_meep`, otherwise it is a legacy unscaled Meep value.
    Search the default empirical locations and sweep directories in order and
    support registry datasets named repulsive_sweet_spots or lifshitz.
    Multidimensional sweeps use the (alpha, theta) slice with the most distinct
    gaps, preferring (0.1, 0.0), then the most repulsive gaps, on ties.
    No extrapolation or synthetic fallback is permitted.
    """
    if max_steps is not None:
        max_steps = _positive_integer(max_steps, 'max_steps')
        if max_steps < 2:
            raise ValueError('max_steps must be at least 2 to estimate logarithmic running.')

    if os.fspath(path) == SWEEP_PATH:
        candidates = (
            *EMPIRICAL_PATHS[:-1],
            *sorted(glob.glob(
                'results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json'
            )),
            EMPIRICAL_PATHS[-1],
        )
    else:
        candidates = (path,)
    path = next((candidate for candidate in candidates if os.path.isfile(candidate)), None)
    if path is None:
        raise _run_data_error(
            f'No empirical sweep file exists in: {", ".join(map(os.fspath, candidates))}.'
        )

    try:
        with open(path, 'r', encoding='utf-8') as handle:
            summary = json.load(handle)
    except (OSError, ValueError) as exc:
        raise _run_data_error(f'Cannot read empirical sweep {path!r}: {exc}') from exc

    gap_keys = (
        'd_m', 'gap_m', 'separation_m',
        'd_nm', 'gap_nm', 'separation_nm',
        'd_um', 'gap_um', 'separation_um',
        'd', 'gap', 'separation',
    )
    coefficient_keys = ('C', 'C_d', 'casimir_coefficient')
    pressure_keys = (
        'pressure_Pa_SI', 'pressure_Pa', 'pressure_pa', 'Pzz_pa', 'P_zz_pa',
        'casimir_pressure_pa', 'normal_pressure_pa',
        'pressure_meep', 'casimir_pressure_meep',
        'pressure', 'casimir_pressure', 'normal_pressure', 'Pzz', 'P_zz',
    )
    context_keys = (
        'd_units', 'gap_units', 'separation_units', 'pressure_units',
        'alpha', 'theta', 'alpha_deg', 'theta_deg',
    )
    samples = []

    def collect(node, inherited=None):
        inherited = {} if inherited is None else inherited
        if isinstance(node, list):
            for item in node:
                collect(item, inherited)
            return
        if not isinstance(node, dict):
            return

        context = dict(inherited)
        for key in context_keys:
            if key in node:
                context[key] = node[key]

        # Registry tables store positional rows alongside their column names.
        if 'columns' in node and 'rows' in node:
            columns = node['columns']
            rows = node['rows']
            if (not isinstance(columns, list)
                    or not all(isinstance(column, str) for column in columns)
                    or len(set(columns)) != len(columns)
                    or not isinstance(rows, list)):
                raise _run_data_error('Empirical table columns and rows must be valid lists.')
            for row in rows:
                if isinstance(row, dict):
                    collect(row, context)
                elif isinstance(row, list) and len(row) == len(columns):
                    collect(dict(zip(columns, row)), context)
                else:
                    raise _run_data_error('Empirical table rows must match their columns.')
            return

        gap_key, gap_value = _first_present(node, gap_keys)
        coefficient_key, coefficient_value = _first_present(node, coefficient_keys)
        pressure_key, pressure_value = _first_present(node, pressure_keys)
        value_key = coefficient_key or pressure_key
        value = coefficient_value if coefficient_key else pressure_value

        if gap_key is not None and value_key is not None:
            # Support both row-oriented and column-oriented sweep summaries.
            if isinstance(gap_value, list) or isinstance(value, list):
                if (not isinstance(gap_value, list) or not isinstance(value, list)
                        or len(gap_value) != len(value)):
                    raise _run_data_error('Empirical gap and coefficient/pressure arrays must match.')
                for key in ('alpha', 'theta', 'alpha_deg', 'theta_deg'):
                    if isinstance(context.get(key), list) and len(context[key]) != len(gap_value):
                        raise _run_data_error(
                            'Empirical geometry arrays must match the gap array.'
                        )
                paired_pressure = value_key == 'pressure_Pa' and 'pressure_meep' in node
                if (paired_pressure and isinstance(node['pressure_meep'], list)
                        and len(node['pressure_meep']) != len(gap_value)):
                    raise _run_data_error('Empirical pressure arrays must match the gap array.')
                for index, (gap_item, value_item) in enumerate(zip(gap_value, value)):
                    row_context = dict(context)
                    for key in ('alpha', 'theta', 'alpha_deg', 'theta_deg'):
                        if isinstance(row_context.get(key), list):
                            row_context[key] = row_context[key][index]
                    row = {gap_key: gap_item, value_key: value_item}
                    if paired_pressure:
                        companion = node['pressure_meep']
                        row['pressure_meep'] = (
                            companion[index] if isinstance(companion, list) else companion
                        )
                    collect(row, row_context)
                return

            try:
                gap = _finite_number(gap_value, gap_key)
                measured = _finite_number(value, value_key)
                if gap <= 0:
                    raise ValueError('Empirical gaps must be positive.')

                geometry = None
                if any(key in context for key in ('alpha', 'alpha_deg', 'theta', 'theta_deg')):
                    alpha_val = context.get('alpha', context.get('alpha_deg', 0.0))
                    theta_val = context.get('theta', context.get('theta_deg', 0.0))
                    angles = []
                    for key, angle in (('alpha', alpha_val), ('theta', theta_val)):
                        if isinstance(angle, str):
                            angle = float(angle)
                        angles.append(round(_finite_number(angle, key), 6))
                    geometry = tuple(angles)

                if gap_key.endswith('_nm'):
                    scale = 1e-9
                elif gap_key.endswith('_um'):
                    scale = 1e-6
                elif gap_key.endswith('_m'):
                    scale = 1.0
                else:
                    units = str(context.get(
                        'd_units', context.get(
                            'gap_units', context.get('separation_units', 'um')
                        )
                    )).lower().replace('µ', 'u').replace('μ', 'u')
                    scales = {
                        'm': 1.0, 'nm': 1e-9, 'um': 1e-6,
                        'micrometer': 1e-6, 'micrometers': 1e-6,
                    }
                    if units not in scales:
                        raise ValueError(f'Unsupported gap units: {units!r}.')
                    scale = scales[units]
                gap_m = gap * scale
                if not np.isfinite(gap_m) or gap_m <= 0:
                    raise ValueError('Empirical gap conversion is not finite and positive.')

                if coefficient_key:
                    coefficient = measured
                else:
                    units = str(context.get('pressure_units', 'meep')).strip().lower()
                    if 'pressure_Pa_SI' in node:
                        pressure_pa = measured
                    elif 'pressure_Pa' in node and 'pressure_meep' in node:
                        pressure_pa = measured
                    elif 'pressure_Pa' in node:
                        pressure_pa = measured * MEEP_TO_PA
                    elif pressure_key.lower().endswith('_pa'):
                        pressure_pa = measured
                    elif pressure_key.endswith('_meep'):
                        pressure_pa = measured * MEEP_TO_PA
                    elif units in ('pa', 'pascal', 'pascals', 'si'):
                        pressure_pa = measured
                    elif units in ('meep', 'unscaled', 'meep_units'):
                        pressure_pa = measured * MEEP_TO_PA
                    else:
                        raise ValueError(f'Unsupported pressure units: {units!r}.')
                    coefficient = -pressure_pa * gap_m**4 / (HBAR * LIGHT_SPEED)

                if not np.isfinite(coefficient):
                    raise ValueError('Empirical coefficient is not finite.')
                samples.append((gap_m, coefficient, geometry))
            except (ValueError, TypeError, OverflowError) as exc:
                raise _run_data_error(f'Invalid empirical sweep record: {exc}') from exc
            return

        for child in node.values():
            if isinstance(child, (dict, list)):
                collect(child, context)

    def find_dataset(node, name, inherited=None):
        context = {} if inherited is None else dict(inherited)
        if isinstance(node, dict):
            for key in context_keys:
                if key in node:
                    context[key] = node[key]
            if name in node:
                return node[name], context
            if any(node.get(key) == name for key in ('name', 'id', 'dataset', 'dataset_id')):
                return node, context
            for child in node.values():
                if isinstance(child, (dict, list)):
                    found = find_dataset(child, name, context)
                    if found is not None:
                        return found
        elif isinstance(node, list):
            for child in node:
                found = find_dataset(child, name, context)
                if found is not None:
                    return found
        return None

    def collect_dataset(node, context, source_path, visited):
        # Registries may embed measurements or point to a JSON data file.
        before = len(samples)
        collect(node, context)
        if len(samples) > before:
            return

        if isinstance(node, str) and node.lower().endswith('.json'):
            references = (node, os.path.join(os.path.dirname(source_path), node))
            reference = next((item for item in references if os.path.isfile(item)), None)
            if reference is None:
                return
            absolute = os.path.abspath(reference)
            if absolute in visited:
                return
            visited.add(absolute)
            try:
                with open(reference, 'r', encoding='utf-8') as handle:
                    referenced = json.load(handle)
            except (OSError, ValueError) as exc:
                raise _run_data_error(
                    f'Cannot read empirical dataset {reference!r}: {exc}'
                ) from exc
            collect_dataset(referenced, context, reference, visited)
        elif isinstance(node, dict):
            context = dict(context)
            for key in context_keys:
                if key in node:
                    context[key] = node[key]
            for child in node.values():
                collect_dataset(child, context, source_path, visited)
                if len(samples) > before:
                    return
        elif isinstance(node, list):
            for child in node:
                collect_dataset(child, context, source_path, visited)
                if len(samples) > before:
                    return

    registry_datasets = [
        found for name in ('repulsive_sweet_spots', 'lifshitz')
        if (found := find_dataset(summary, name)) is not None
    ]
    if registry_datasets:
        for dataset, context in registry_datasets:
            collect_dataset(dataset, context, path, {os.path.abspath(path)})
            if samples:
                break
    else:
        collect(summary)

    if not samples:
        raise _run_data_error(
            f'{path!r} contains no gap-resolved Casimir coefficients or pressures.'
        )

    # Select one fixed geometry before checking repeated gaps: pressures from
    # different (alpha, theta) slices must never be combined or differentiated.
    slices = {}
    for gap, coefficient, geometry in samples:
        if geometry is not None:
            slices.setdefault(geometry, []).append((gap, coefficient))

    if slices:
        def slice_rank(geometry):
            records = slices[geometry]
            distinct_gaps = {gap for gap, _ in records}
            repulsive_gaps = {gap for gap, coefficient in records if coefficient < 0}
            return (
                len(distinct_gaps),
                geometry == (0.1, 0.0),
                len(repulsive_gaps),
            )

        # Sorting gives deterministic selection when all preference scores tie.
        selected_geometry = max(sorted(slices), key=slice_rank)
        selected_samples = slices[selected_geometry]
    else:
        selected_samples = [(gap, coefficient) for gap, coefficient, _ in samples]

    # Identical duplicate records are harmless. Conflicting duplicates within
    # the selected geometry must not be silently averaged.
    unique = {}
    for gap, coefficient in selected_samples:
        if gap in unique and not np.isclose(
                coefficient, unique[gap], rtol=1e-10, atol=1e-14):
            raise _run_data_error(
                f'Conflicting coefficients at d={gap:g} m; select one empirical sweep.'
            )
        unique[gap] = coefficient

    gaps = np.array(sorted(unique), dtype=float)
    coefficients = np.array([unique[gap] for gap in gaps], dtype=float)
    if gaps.size < 2:
        raise _run_data_error('At least two distinct empirical gaps are required.')

    if max_steps is not None and gaps.size > max_steps:
        indices = np.linspace(0, gaps.size - 1, max_steps, dtype=int)
        gaps = gaps[indices]
        coefficients = coefficients[indices]

    target_gap = d_um * 1e-6
    if target_gap < gaps[0] or target_gap > gaps[-1]:
        if np.isclose(target_gap, gaps[0], rtol=1e-12, atol=0):
            target_gap = gaps[0]
        elif np.isclose(target_gap, gaps[-1], rtol=1e-12, atol=0):
            target_gap = gaps[-1]
        else:
            raise _run_data_error(
                f'Requested d={d_um:g} um lies outside the empirical sweep; '
                'trace extrapolation is not supported.'
            )

    log_gaps = np.log(gaps)
    running = np.gradient(
        coefficients, log_gaps, edge_order=2 if gaps.size >= 3 else 1
    )
    derivative = float(np.interp(np.log(target_gap), log_gaps, running))
    coefficient = float(np.interp(np.log(target_gap), log_gaps, coefficients))
    trace_pa = -(HBAR * LIGHT_SPEED / target_gap**4) * derivative
    if not np.isfinite(trace_pa):
        raise _run_data_error('The empirical trace anomaly is not finite.')

    return {
        'quantum_trace_pa': float(trace_pa),
        'casimir_coefficient': coefficient,
        'dC_dln_d': derivative,
        'empirical_samples_used': int(gaps.size),
        'dataset': os.path.abspath(path),
        'coefficient_convention': 'P = -(hbar*c/d^4)*C',
    }


def compute_3d_stress_tensor_fields(
        L=2.0, d=0.15, alpha=75.0, theta=82.0, N=3,
        nx=80, ny=80, nz=60, eps_bg=2.1, max_steps=None):
    """
    Compute illustrative classical Maxwell fields and an empirical quantum trace.

    The classical voxel fields are a geometric surrogate, not measured Casimir
    fields. The sweep supplies a gap-dependent scalar quantum trace in Pa, not
    spatially resolved quantum data; its uniform broadcast is explicitly labeled.
    """
    L = _finite_number(L, 'L')
    d = _finite_number(d, 'd')
    alpha = _finite_number(alpha, 'alpha')
    theta = _finite_number(theta, 'theta')
    eps_bg = _finite_number(eps_bg, 'eps_bg')
    if L <= 0 or d <= 0 or eps_bg <= 0:
        raise ValueError('L, d, and eps_bg must be positive.')
    N = _positive_integer(N, 'N')
    nx = _positive_integer(nx, 'nx')
    ny = _positive_integer(ny, 'ny')
    nz = _positive_integer(nz, 'nz')

    empirical = _load_empirical_trace(d, max_steps=max_steps)
    executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    print('==================================================')
    print('PIPELINE 1: CLASSICAL TENSOR MAPPER AND EMPIRICAL QUANTUM TRACE')
    print('==================================================')
    print('Geometry parameters:')
    print(f'  - Plate size L = {L} um')
    print(f'  - Cavity gap d = {d*1000.0:.1f} nm ({d} um)')
    print(f'  - Corrugation Wall Slope alpha = {alpha} deg')
    print(f'  - Optical Twist Angle theta = {theta} deg')
    print(f'  - Prefractal Generation N = {N}')
    print(f'  - Voxel Grid Resolution: {nx} x {ny} x {nz} ({nx*ny*nz} total voxels)')

    x = np.linspace(-L/2.0, L/2.0, nx)
    y = np.linspace(-L/2.0, L/2.0, ny)
    z = np.linspace(-d/2.0, d/2.0, nz)
    X, Y, Z = np.meshgrid(x, y, z, indexing='ij')

    w_macro = L / 3.0
    w_micro = L / 9.0
    theta_rad = np.radians(theta)
    cos_th = np.cos(theta_rad)
    sin_th = np.sin(theta_rad)

    # These fields retain the original illustrative geometry model. They are
    # not used to infer an empirical quantum trace anomaly.
    with np.errstate(over='raise', divide='raise', invalid='raise'):
        try:
            e_base = np.float64(d) ** -3
            pyramid_profile = np.maximum(
                0.0,
                1.0 - np.maximum(np.abs(X) / (w_macro/2.0),
                                 np.abs(Y) / (w_macro/2.0))
            )
            micro_profile = np.maximum(
                0.0,
                np.cos(2.0 * np.pi * X / w_micro)
                * np.cos(2.0 * np.pi * Y / w_micro)
            )
            slope_weight = pyramid_profile * 0.7 + micro_profile * 0.3
            field_tilt = (
                np.radians(alpha) * slope_weight
                * np.exp(-np.abs(Z) / (d * 0.8))
            )

            E0_sq = e_base * (1.0 + 0.15 * np.cos(2.0 * np.pi * Z / d))
            Ez_sq = E0_sq * np.cos(field_tilt)**2
            Eperp_sq = E0_sq * np.sin(field_tilt)**2

            eps_xx = eps_bg * (1.0 + 0.5 * cos_th**2)
            eps_yy = eps_bg * (1.0 + 0.5 * sin_th**2)
            eps_zz = eps_bg * 0.95

            Ex_sq = Eperp_sq * cos_th**2 * 1.2
            Ey_sq = Eperp_sq * sin_th**2 * 0.8

            Hz_sq = 0.8 * Ez_sq
            Hx_sq = 0.8 * Ey_sq
            Hy_sq = 0.8 * Ex_sq

            T00 = 0.5 * (
                eps_xx * Ex_sq + eps_yy * Ey_sq + eps_zz * Ez_sq
                + Hx_sq + Hy_sq + Hz_sq
            )

            # Maxwell tension sigma_ij has the opposite sign to the spatial
            # stress-energy components (principal pressures) P_ij.
            sigma_zz = eps_zz * Ez_sq + Hz_sq - T00
            sigma_xx = eps_xx * Ex_sq + Hx_sq - T00
            sigma_yy = eps_yy * Ey_sq + Hy_sq - T00
            sigma_xy = (
                0.5 * np.sqrt(eps_xx * eps_yy)
                * np.sqrt(Ex_sq) * np.sqrt(Ey_sq)
                * np.sin(2.0 * theta_rad)
            )

            Tzz = -sigma_zz
            Txx = -sigma_xx
            Tyy = -sigma_yy
            Txy = -sigma_xy
        except (FloatingPointError, OverflowError, ZeroDivisionError) as exc:
            raise ValueError('Geometry parameters produce non-finite classical fields.') from exc

    # Analytically -T00 + Pxx + Pyy + Pzz == 0. Store exact zeros rather
    # than floating-point cancellation noise. Do not confuse this with the
    # independently measured quantum trace.
    Trace_classical = np.zeros_like(T00)
    Trace = np.full_like(T00, empirical['quantum_trace_pa'])

    mean_T00 = float(np.mean(T00))
    mean_Tzz = float(np.mean(Tzz))
    mean_Txx = float(np.mean(Txx))
    mean_Tyy = float(np.mean(Tyy))
    mean_Trace = empirical['quantum_trace_pa']
    shear_quadrupole = float(np.mean(Txx - Tyy))

    print('\n--- Classical Surrogate Diagnostics (arb. units) ---')
    print(f'  Mean Energy Density <T_00>:   {mean_T00:+.6e}')
    regime_str = (
        'Repulsive' if mean_Tzz > 0 else
        'Attractive' if mean_Tzz < 0 else 'Neutral'
    )
    print(f'  Mean Normal Pressure <P_zz>: {mean_Tzz:+.6e} ({regime_str})')
    print(f'  Mean Transverse <P_xx>:      {mean_Txx:+.6e}')
    print(f'  Mean Transverse <P_yy>:      {mean_Tyy:+.6e}')
    print(f'  Shear Quadrupole <Pxx-Pyy>:  {shear_quadrupole:+.6e}')
    print('  Classical Maxwell Trace:    +0.000000e+00')
    print(f'  Empirical Quantum Trace:    {mean_Trace:+.6e} Pa')

    return {
        'x': x, 'y': y, 'z': z,
        'T00': T00, 'Tzz': Tzz, 'Txx': Txx, 'Tyy': Tyy, 'Txy': Txy,
        'sigma_xx': sigma_xx, 'sigma_yy': sigma_yy, 'sigma_zz': sigma_zz,
        'sigma_xy': sigma_xy,
        'Trace': Trace, 'Trace_classical': Trace_classical,
        'metrics': {
            'L_um': L, 'd_um': d, 'alpha_deg': alpha,
            'theta_deg': theta, 'N': N,
            'mean_T00': mean_T00, 'mean_Tzz': mean_Tzz,
            'mean_Txx': mean_Txx, 'mean_Tyy': mean_Tyy,
            'shear_quadrupole': shear_quadrupole,
            'mean_Trace': mean_Trace,
            'mean_classical_Trace': 0.0,
            'classical_field_units': 'arbitrary',
            'trace_units': 'Pa',
            'trace_spatial_model': 'uniform broadcast of gap-dependent empirical scalar',
            'model': 'classical_maxwell_surrogate_with_empirical_casimir_trace',
            'status': 'completed',
            'executed_at': executed_at,
            'max_steps': max_steps,
            **empirical,
        }
    }


def safe_norm(arr):
    values = np.asarray(arr, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    vmin, vmax = float(np.min(values)), float(np.max(values))
    if vmin < 0 < vmax:
        return TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
    return None


def plot_tensor_field_cross_sections(data, out_dir):
    """Plot classical surrogate slices and the gap-dependent empirical trace."""
    coordinates = {}
    for name in ('x', 'y', 'z'):
        values = np.asarray(data[name], dtype=float)
        if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
            raise ValueError(f'{name} must be a nonempty finite coordinate vector.')
        coordinates[name] = values
    x, y = coordinates['x'], coordinates['y']
    z = coordinates['z'] * 1000.0
    shape = (len(x), len(y), len(z))

    fields = {}
    for name in ('Tzz', 'T00', 'Trace', 'Txx', 'Tyy'):
        values = np.asarray(data[name], dtype=float)
        if values.shape != shape or not np.all(np.isfinite(values)):
            raise ValueError(f'{name} must be a finite field with shape {shape}.')
        fields[name] = values

    mid_y = int(np.argmin(np.abs(y)))
    mid_z = int(np.argmin(np.abs(z)))
    Tzz_xz = fields['Tzz'][:, mid_y, :].T
    T00_xz = fields['T00'][:, mid_y, :].T
    Trace_xz = fields['Trace'][:, mid_y, :].T
    Aniso_xy = (fields['Txx'][:, :, mid_z] - fields['Tyy'][:, :, mid_z]).T

    def extent_limits(values):
        if len(values) > 1:
            return values[0], values[-1]
        half_width = max(abs(float(values[0])) * 0.01, 0.5)
        return values[0] - half_width, values[0] + half_width

    x_limits = extent_limits(x)
    y_limits = extent_limits(y)
    z_limits = extent_limits(z)
    extent_xz = [*x_limits, *z_limits]
    extent_xy = [*x_limits, *y_limits]

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.6))
    fig.subplots_adjust(hspace=0.35, wspace=0.35)

    try:
        im1 = axes[0, 0].imshow(
            Tzz_xz, extent=extent_xz, aspect='auto', origin='lower',
            cmap='RdBu_r', norm=safe_norm(Tzz_xz)
        )
        axes[0, 0].set_title(
            r'(a) Classical Pressure $P_{zz}(x,z)$ [Surrogate]',
            fontweight='bold'
        )
        axes[0, 0].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
        axes[0, 0].set_ylabel(r'Cavity Gap $z$ (nm)')
        cbar1 = fig.colorbar(im1, ax=axes[0, 0], fraction=0.046, pad=0.04)
        cbar1.set_label(r'$P_{zz}$ (arb. units)', fontsize=7)

        im2 = axes[0, 1].imshow(
            T00_xz, extent=extent_xz, aspect='auto', origin='lower',
            cmap='viridis'
        )
        axes[0, 1].set_title(
            r'(b) Classical Energy $T_{00}(x,z)$ [Surrogate]',
            fontweight='bold'
        )
        axes[0, 1].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
        axes[0, 1].set_ylabel(r'Cavity Gap $z$ (nm)')
        cbar2 = fig.colorbar(im2, ax=axes[0, 1], fraction=0.046, pad=0.04)
        cbar2.set_label(r'$T_{00}$ (arb. units)', fontsize=7)

        im3 = axes[1, 0].imshow(
            Trace_xz, extent=extent_xz, aspect='auto', origin='lower',
            cmap='coolwarm', norm=safe_norm(Trace_xz)
        )
        axes[1, 0].set_title(
            r'(c) Empirical Quantum Trace [Uniform Gap Value]',
            fontweight='bold'
        )
        axes[1, 0].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
        axes[1, 0].set_ylabel(r'Cavity Gap $z$ (nm)')
        cbar3 = fig.colorbar(im3, ax=axes[1, 0], fraction=0.046, pad=0.04)
        cbar3.set_label(r'$T^\mu{}_\mu$ (Pa)', fontsize=7)

        im4 = axes[1, 1].imshow(
            Aniso_xy, extent=extent_xy, aspect='auto', origin='lower',
            cmap='PuOr', norm=safe_norm(Aniso_xy)
        )
        axes[1, 1].set_title(
            rf'(d) Classical $(P_{{xx}}-P_{{yy}})$ at $z={z[mid_z]:.3g}$ nm',
            fontweight='bold'
        )
        axes[1, 1].set_xlabel(r'Transverse Position $x$ ($\mu\mathrm{m}$)')
        axes[1, 1].set_ylabel(r'Transverse Position $y$ ($\mu\mathrm{m}$)')
        cbar4 = fig.colorbar(im4, ax=axes[1, 1], fraction=0.046, pad=0.04)
        cbar4.set_label(r'$\Delta P_\perp$ (arb. units)', fontsize=7)

        os.makedirs(out_dir, exist_ok=True)
        out_png = os.path.join(out_dir, 'figure_qg_pipeline1_tensor_fields.png')
        out_pdf = os.path.join(out_dir, 'figure_qg_pipeline1_tensor_fields.pdf')
        for path in (out_png, out_pdf):
            fig.savefig(path, dpi=300, bbox_inches='tight')
            save_plot_provenance(path, dict(data['metrics']))
    finally:
        plt.close(fig)

    print('\nSaved Pipeline 1 cross-section plots:')
    print(f'  - {out_png}')
    print(f'  - {out_pdf}')


def _max_steps_argument(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('--max-steps must be an integer.') from exc
    if result < 2:
        raise argparse.ArgumentTypeError('--max-steps must be at least 2.')
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Pipeline 1: Classical Tensor Mapper and Empirical Quantum Trace'
    )
    parser.add_argument('--L', type=float, default=2.0, help='Plate size L in um')
    parser.add_argument('--d', type=float, default=0.15, help='Separation d in um')
    parser.add_argument(
        '--alpha', type=float, default=75.0,
        help='Corrugation wall slope alpha in degrees'
    )
    parser.add_argument(
        '--theta', type=float, default=82.0,
        help='Optical axis twist angle theta in degrees'
    )
    parser.add_argument('--N', type=int, default=3, help='Prefractal generation N')
    parser.add_argument(
        '--max-steps', type=_max_steps_argument, default=None,
        help='Maximum empirical gap samples used for logarithmic differentiation '
             '(at least 2; evenly sampled over the sweep)'
    )
    parser.add_argument(
        '--out-dir', type=str,
        default='quantum_gravity_trace_analysis/figures',
        help='Output directory for plots'
    )
    parser.add_argument(
        '--json-out', type=str,
        default='quantum_gravity_trace_analysis/pipeline1_tensor_field_data.json',
        help='Output JSON file'
    )
    args = parser.parse_args()

    log_step(1)
    data = compute_3d_stress_tensor_fields(
        L=args.L, d=args.d, alpha=args.alpha, theta=args.theta,
        N=args.N, max_steps=args.max_steps
    )
    for name in (
        'mean_T00', 'mean_Tzz', 'mean_Txx', 'mean_Tyy',
        'shear_quadrupole', 'mean_classical_Trace', 'mean_Trace', 'dC_dln_d'
    ):
        log_metric(name, data['metrics'][name])

    log_step(2)
    plot_tensor_field_cross_sections(data, args.out_dir)

    log_step(3)
    export_macros(os.path.join(args.out_dir, 'pipeline1_metrics.tex'))
    os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
    with open(args.json_out, 'w', encoding='utf-8') as handle:
        json.dump(data['metrics'], handle, indent=4, allow_nan=False)

    print(f"Saved summary diagnostics to '{args.json_out}'.")
    print('Pipeline 1 execution finished successfully!')


if __name__ == '__main__':
    main()
