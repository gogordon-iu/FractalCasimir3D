"""
Finite-Temperature Matsubara Summation & Thermal DSI Analyzer (Nature Challenge 4)
----------------------------------------------------------------------------------
Computes finite-temperature Casimir pressure using passive TM and TE reflections.
Models weak prefractal DSI modulation inside the spectral integral and measures its
thermal visibility relative to the corresponding zero-temperature integral.
"""

import os
import sys
import json
import argparse
import inspect
import operator
from datetime import datetime, timezone

import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from execution.materials_database_dispersive import get_dielectric_tensor_imag


KB_MEEP = 0.00043676
MEEP_TO_PA = 0.0316152649
PASSIVE_LIMIT = np.nextafter(1.0, 0.0)


def _finite_scalar(value, name):
    if isinstance(value, (str, bytes, bool, np.bool_)) or np.ndim(value) != 0:
        raise TypeError(f"{name} must be a real scalar.")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"{name} must be a real scalar.") from exc
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return value


def _integer(value, name, minimum):
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be an integer.")
    try:
        value = operator.index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _permittivity(material, xi, angle, allow_static_infinity=False):
    eps, _, _, _ = get_dielectric_tensor_imag(material, xi, angle)
    if np.ndim(eps) != 0 or np.iscomplexobj(eps):
        raise ValueError(f"{material} must provide a real scalar permittivity.")
    eps = float(eps)
    if np.isnan(eps) or eps <= 0.0:
        raise ValueError(f"{material} must have positive imaginary-axis permittivity.")
    if not np.isfinite(eps) and not (allow_static_infinity and xi == 0.0):
        raise ValueError(f"{material} has nonfinite permittivity at xi={xi}.")
    return eps


def _passive_reflections(eps_bg, eps_material, xi, kp, kz0):
    """Return strictly passive TM and TE amplitudes; static TE is zero."""
    if xi == 0.0:
        if np.isinf(eps_material):
            r_tm = np.full_like(kp, PASSIVE_LIMIT)
        else:
            scale = max(eps_material, eps_bg)
            em = eps_material / scale
            eb = eps_bg / scale
            r_tm = np.full_like(kp, (em - eb) / (em + eb))
        return np.clip(r_tm, -PASSIVE_LIMIT, PASSIVE_LIMIT), np.zeros_like(kp)

    kz_material = np.hypot(np.sqrt(eps_material) * xi, kp)
    if not np.all(np.isfinite(kz_material)):
        raise ValueError("Material wavevectors exceed the supported numeric range.")

    # Normalize before forming Fresnel ratios to avoid overflowing products.
    k_scale = np.maximum(kz0, kz_material)
    k0 = kz0 / k_scale
    km = kz_material / k_scale
    eps_scale = max(eps_material, eps_bg)
    em = eps_material / eps_scale
    eb = eps_bg / eps_scale

    r_tm = (em * k0 - eb * km) / (em * k0 + eb * km)
    r_te = (k0 - km) / (k0 + km)
    return (
        np.clip(r_tm, -PASSIVE_LIMIT, PASSIVE_LIMIT),
        np.clip(r_te, -PASSIVE_LIMIT, PASSIVE_LIMIT),
    )


def compute_matsubara_casimir_pressure(
    d_um,
    T_K,
    material_top="BlackPhosphorus",
    material_bot="BlackPhosphorus",
    medium_bg="Teflon_AF",
    theta_deg=90.0,
    alpha_deg=75.0,
    N_fractal=3,
    max_steps=400,
):
    """
    Compute pressure and DSI visibility with a shared finite-/zero-T model.

    max_steps caps both the Matsubara terms and the zero-temperature frequency
    quadrature nodes. The DSI amplitude is the coefficient of the log-periodic
    harmonic, not its instantaneous value at a particular phase.
    """
    d_um = _finite_scalar(d_um, "d_um")
    T_K = _finite_scalar(T_K, "T_K")
    theta_deg = _finite_scalar(theta_deg, "theta_deg")
    alpha_deg = _finite_scalar(alpha_deg, "alpha_deg")
    N_fractal = _integer(N_fractal, "N_fractal", 0)
    max_steps = _integer(max_steps, "max_steps", 1)
    if d_um <= 0.0:
        raise ValueError("d_um must be positive.")
    if T_K < 0.0:
        raise ValueError("T_K must be nonnegative.")

    delta_xi = 2.0 * np.pi * KB_MEEP * T_K
    chi_T = d_um * delta_xi
    kp_max = 6.0 / d_um
    xi_max = 12.0 / d_um
    if not np.all(np.isfinite([delta_xi, chi_T, kp_max, xi_max])):
        raise ValueError("Separation or temperature exceeds the supported numeric range.")
    if kp_max <= 0.0 or xi_max <= 0.0 or (T_K > 0.0 and delta_xi == 0.0):
        raise ValueError("Separation or temperature exceeds the supported numeric range.")

    lambda_T_um = None if T_K == 0.0 else 1.0 / delta_xi
    if lambda_T_um is not None and not np.isfinite(lambda_T_um):
        raise ValueError("Thermal wavelength exceeds the supported numeric range.")

    prefractal_scale = 0.30
    dsi_phase = 0.45
    dsi_period = np.log(3.0)
    phase = 2.0 * np.pi * (np.log(d_um) - np.log(prefractal_scale)) / dsi_period
    phase += dsi_phase
    # A bounded, weak geometric perturbation, not a Fresnel-amplitude boost.
    dsi_strength = 0.10 * np.sin(np.radians(alpha_deg)) ** 2

    kp_nodes, kp_weights = np.polynomial.legendre.leggauss(24)
    kp_arr = 0.5 * kp_max * (kp_nodes + 1.0)
    w_arr = 0.5 * kp_max * kp_weights

    def spectral_integral(xi):
        eps_bg = _permittivity(medium_bg, xi, 0.0)
        eps_top = _permittivity(material_top, xi, theta_deg, True)
        eps_bot = _permittivity(material_bot, xi, 0.0, True)

        kz0 = np.hypot(np.sqrt(eps_bg) * xi, kp_arr)
        if not np.all(np.isfinite(kz0)):
            raise ValueError("Background wavevectors exceed the supported numeric range.")

        rt_tm, rt_te = _passive_reflections(eps_bg, eps_top, xi, kp_arr, kz0)
        rb_tm, rb_te = _passive_reflections(eps_bg, eps_bot, xi, kp_arr, kz0)

        exponent = -2.0 * (kz0 * d_um)
        exp_factor = np.exp(exponent)
        polarization_sum = np.zeros_like(kp_arr)
        for rt, rb in ((rt_tm, rb_tm), (rt_te, rb_te)):
            product = rt * rb
            # Stable form of 1 - product * exp_factor, including small exponents.
            denominator = -np.expm1(exponent) + (1.0 - product) * exp_factor
            polarization_sum += product * exp_factor / denominator

        integrand = kp_arr * kz0 * polarization_sum

        # Each prefractal level couples to the spectrum at its own scale.
        # The normalized coupling is bounded in [0, 1], so the total spectral
        # weight 1 + dsi_strength * coupling * cos(phase) remains positive.
        coupling = np.zeros_like(kp_arr)
        if N_fractal:
            scale = prefractal_scale
            for _ in range(N_fractal):
                coupling += np.exp(-2.0 * (kz0 * scale))
                scale /= 3.0
                if scale == 0.0:
                    # Remaining levels have unit coupling at machine precision.
                    coupling += N_fractal - (_ + 1)
                    break
            coupling /= N_fractal

        base = np.sum(integrand * w_arr)
        harmonic = dsi_strength * np.sum(integrand * coupling * w_arr)
        result = np.array([base, harmonic], dtype=float)
        if not np.all(np.isfinite(result)):
            raise ValueError("Pressure integral produced nonfinite values.")
        return result

    # At T=0, k_B T sum_n' becomes (1 / 2*pi) integral dxi.
    # Use the same reflections, DSI coupling, and momentum cutoff as at finite T.
    xi_nodes, xi_weights = np.polynomial.legendre.leggauss(min(96, max_steps))
    xi_arr = 0.5 * xi_max * (xi_nodes + 1.0)
    xi_weights = 0.5 * xi_max * xi_weights
    zero_integral = np.zeros(2)
    for xi, weight in zip(xi_arr, xi_weights):
        zero_integral += weight * spectral_integral(float(xi))
    zero_pressure = -MEEP_TO_PA * zero_integral / (2.0 * np.pi**2)

    if T_K <= 1e-3:
        pressure_components = zero_pressure.copy()
        steps_used = 0
    else:
        # Avoid converting an arbitrarily large cutoff to an integer.
        if chi_T <= 12.0 / max_steps:
            n_max = max_steps
        else:
            n_max = min(max_steps, max(15, int(12.0 / chi_T) + 1))

        finite_sum = np.zeros(2)
        for n in range(n_max):
            weight = 0.5 if n == 0 else 1.0
            finite_sum += weight * spectral_integral(n * delta_xi)
        pressure_components = -(KB_MEEP * T_K / np.pi) * MEEP_TO_PA * finite_sum
        steps_used = n_max

    total_pressure_Pa = pressure_components[0] + pressure_components[1] * np.cos(phase)
    finite_amplitude = abs(float(pressure_components[1]))
    zero_amplitude = abs(float(zero_pressure[1]))
    # With no DSI harmonic, visibility is defined as zero rather than 0/0.
    thermal_visibility = finite_amplitude / zero_amplitude if zero_amplitude > 0.0 else 0.0
    if not np.all(np.isfinite([
        total_pressure_Pa, finite_amplitude, zero_amplitude, thermal_visibility
    ])):
        raise ValueError("Pressure or visibility exceeds the supported numeric range.")

    return {
        "d_um": d_um,
        "T_K": T_K,
        "lambda_T_um": lambda_T_um,
        "chi_T": chi_T,
        "total_pressure_Pa": float(total_pressure_Pa),
        "thermal_visibility": float(thermal_visibility),
        "dsi_amplitude_Pa": finite_amplitude,
        "dsi_amplitude_T0_Pa": zero_amplitude,
        "N_fractal": N_fractal,
        "max_steps": max_steps,
        "matsubara_steps": steps_used,
        "is_repulsive": bool(total_pressure_Pa > 0.0),
    }


def analyze_dsi_thermal_visibility(
    separations_um,
    temperatures_K,
    max_steps=400,
    material_top="BlackPhosphorus",
    material_bot="BlackPhosphorus",
    medium_bg="Teflon_AF",
):
    """Sweep separations and temperatures; empty inputs produce an empty sweep."""
    max_steps = _integer(max_steps, "max_steps", 1)
    separations_um = list(separations_um)
    temperatures_K = list(temperatures_K)
    matrix = {}
    for T in temperatures_K:
        matrix[f"T_{T}K"] = [
            compute_matsubara_casimir_pressure(
                d, T, material_top, material_bot, medium_bg, max_steps=max_steps
            )
            for d in separations_um
        ]
    return matrix


def _log_metrics(metadata, metrics, output_path):
    """Use the repository logger, accommodating its common argument names."""
    from utils.metrics_logger import log_metrics

    values = {
        "model": metadata["model"],
        "model_name": metadata["model"],
        "dataset": metadata["dataset"],
        "dataset_name": metadata["dataset"],
        "metrics": metrics,
        "status": metadata["status"],
        "executed_at": metadata["executed_at"],
        "output_path": output_path,
    }
    signature = inspect.signature(log_metrics)
    positional = []
    keywords = {}
    has_var_keywords = False
    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_keywords = True
            continue
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            continue
        if name in values:
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                positional.append(values[name])
            else:
                keywords[name] = values[name]
        elif parameter.default is inspect.Parameter.empty:
            raise TypeError(f"Unsupported required metrics logger argument: {name}")
        elif parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            positional.append(parameter.default)
    if has_var_keywords:
        for name in ("model", "dataset", "metrics", "status", "executed_at"):
            keywords.setdefault(name, values[name])
    log_metrics(*positional, **keywords)


def main():
    parser = argparse.ArgumentParser(
        description="Finite-Temperature Matsubara & DSI Solver (Challenge 4)."
    )
    parser.add_argument("--d", type=float, default=0.15, help="Separation in um.")
    parser.add_argument("--T", type=float, default=300.0, help="Temperature in Kelvin.")
    parser.add_argument("--material-top", type=str, default="BlackPhosphorus")
    parser.add_argument("--material-bot", type=str, default="BlackPhosphorus")
    parser.add_argument("--medium", type=str, default="Teflon_AF")
    parser.add_argument("--sweep-all", action="store_true", help="Perform full temperature-distance sweep.")
    parser.add_argument("--max-steps", type=int, default=400, help="Maximum Matsubara terms and zero-T quadrature nodes.")
    parser.add_argument("--outdir", type=str, default="results")
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1.")

    metadata = {
        "model": "finite_temperature_lifshitz_dsi",
        "dataset": "thermal_matsubara_dsi",
        "status": "completed",
    }

    if args.sweep_all:
        ds = np.logspace(np.log10(0.02), np.log10(1.0), 30)
        temps = [4.0, 77.0, 150.0, 300.0, 400.0]
        results = analyze_dsi_thermal_visibility(
            ds, temps, args.max_steps,
            args.material_top, args.material_bot, args.medium,
        )
        payload = {**metadata, "results": results, "max_steps": args.max_steps}
        records = [record for row in results.values() for record in row]
    else:
        res = compute_matsubara_casimir_pressure(
            args.d, args.T, args.material_top, args.material_bot, args.medium,
            max_steps=args.max_steps,
        )
        payload = {**metadata, **res}
        records = [res]

    metadata["executed_at"] = datetime.now(timezone.utc).isoformat()
    payload["executed_at"] = metadata["executed_at"]
    metrics = {
        "num_calculations": len(records),
        "mean_thermal_visibility": float(np.mean([
            record["thermal_visibility"] for record in records
        ])) if records else 0.0,
        "max_steps": args.max_steps,
    }
    if not args.sweep_all:
        metrics["total_pressure_Pa"] = res["total_pressure_Pa"]
        metrics["thermal_visibility"] = res["thermal_visibility"]

    os.makedirs(args.outdir, exist_ok=True)
    out_file = os.path.join(args.outdir, "thermal_matsubara_dsi.json")
    _log_metrics(metadata, metrics, out_file)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, allow_nan=False)

    if args.sweep_all:
        print(f"Full finite-temperature Matsubara sweep completed. Saved to {out_file}")
    else:
        print(
            f"Matsubara calculation complete: d={args.d} um, T={args.T} K, "
            f"chi_T={res['chi_T']:.3f}, "
            f"DSI Visibility={res['thermal_visibility'] * 100:.1f}% -> "
            f"P = {res['total_pressure_Pa']:+.4f} Pa (Saved to {out_file})"
        )


if __name__ == "__main__":
    main()
