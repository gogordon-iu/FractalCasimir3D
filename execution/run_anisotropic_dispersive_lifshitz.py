"""
Anisotropic Dispersive Casimir Solver with Optical Loss
-----------------------------------------------------
Computes vacuum pressures using imaginary-frequency dielectric tensors and
a passive, approximate tilted-facet reflection model. Positive pressure
denotes repulsion; repulsion is not assumed or imposed by the model.
"""

import os
import sys
import json
import argparse
import inspect
from datetime import datetime, timezone

import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from execution.materials_database_dispersive import (
    get_dielectric_tensor_imag,
    IMMERSION_MEDIA,
    EV_TO_MEEP_FREQ,
)


_REFLECTION_LIMIT = 1.0 - 1e-12
_MODEL = "anisotropic_dispersive_lifshitz"


def _finite_scalar(value, name):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite real scalar.")
    array = np.asarray(value)
    if array.ndim != 0 or not np.isrealobj(array):
        raise ValueError(f"{name} must be a finite real scalar.")
    try:
        value = float(array)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real scalar.") from exc
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return value


def _validate_max_steps(max_steps):
    if max_steps is None:
        return None
    if (
        isinstance(max_steps, (bool, np.bool_))
        or not isinstance(max_steps, (int, np.integer))
        or max_steps <= 0
    ):
        raise ValueError("max_steps must be a positive integer or None.")
    return int(max_steps)


def _dielectric_tensor(material, xi, theta):
    values = get_dielectric_tensor_imag(material, xi, theta)
    if len(values) != 4:
        raise ValueError(f"Invalid dielectric tensor for {material!r}.")
    xx, yy, zz, xy = (
        _finite_scalar(value, f"{material} dielectric component")
        for value in values
    )
    if xx <= 0.0 or yy <= 0.0 or zz <= 0.0:
        raise ValueError(f"{material!r} must have positive imaginary-axis permittivity.")
    # Check positive definiteness without forming a potentially overflowing product.
    if abs((xy / np.sqrt(xx)) / np.sqrt(yy)) >= 1.0:
        raise ValueError(f"{material!r} has a non-positive-definite dielectric tensor.")
    return xx, yy, zz, xy


def _passive_reflection(eps_xx, eps_yy, eps_zz, eps_xy, eps_bg, xi, kp, phi):
    """Approximate TE/TM reflection with a strictly contractive coupling."""
    c = np.cos(phi)
    s = np.sin(phi)
    eps_L = eps_xx * c**2 + eps_yy * s**2 + 2.0 * eps_xy * s * c
    eps_T = eps_xx * s**2 + eps_yy * c**2 - 2.0 * eps_xy * s * c
    eps_LT = (eps_yy - eps_xx) * s * c + eps_xy * (c**2 - s**2)

    if not np.all(np.isfinite([eps_L, eps_T, eps_LT])) or min(eps_L, eps_T) <= 0.0:
        raise ValueError("Invalid wavevector-frame dielectric tensor.")

    kz0 = np.hypot(np.sqrt(eps_bg) * xi, kp)
    kz_e = np.hypot(np.sqrt(eps_L) * xi, np.sqrt(eps_L / eps_zz) * kp)
    kz_o = np.hypot(np.sqrt(eps_T) * xi, kp)
    if not np.all(np.isfinite([kz0, kz_e, kz_o])):
        raise ValueError("Non-finite longitudinal wavevector.")

    # The single point xi = kp = 0 has zero integration weight.
    if kz0 == 0.0:
        return np.zeros((2, 2)), kz0

    # Scaled differences avoid overflow when computing Fresnel ratios.
    scale_s = max(kz0, kz_o)
    rss = ((kz0 / scale_s) - (kz_o / scale_s)) / (
        (kz0 / scale_s) + (kz_o / scale_s)
    )

    eps_scale = max(eps_L, eps_bg)
    kz_scale = max(kz0, kz_e)
    a = (eps_L / eps_scale) * (kz0 / kz_scale)
    b = (eps_bg / eps_scale) * (kz_e / kz_scale)
    if a + b == 0.0:
        raise ValueError("Degenerate TM Fresnel denominator.")
    rpp = (a - b) / (a + b)

    rss = float(np.clip(rss, -_REFLECTION_LIMIT, _REFLECTION_LIMIT))
    rpp = float(np.clip(rpp, -_REFLECTION_LIMIT, _REFLECTION_LIMIT))

    anisotropy = (eps_LT / np.sqrt(eps_L)) / np.sqrt(eps_T)
    if not np.isfinite(anisotropy):
        raise ValueError("Non-finite anisotropic coupling.")
    anisotropy = float(np.clip(anisotropy, -1.0, 1.0))
    coupling = 0.5 * anisotropy * (
        (kz0 / scale_s) / ((kz0 / scale_s) + (kz_o / scale_s))
    )

    # For a symmetric R, positivity of both I-R and I+R bounds every
    # eigenvalue strictly between -1 and 1. Limit the off-diagonal entry
    # using both corresponding determinant conditions.
    coupling_bound = np.sqrt(
        max(
            0.0,
            min(
                (1.0 - rss) * (1.0 - rpp),
                (1.0 + rss) * (1.0 + rpp),
            ),
        )
    )
    rsp = coupling * coupling_bound
    reflection = np.array([[rss, rsp], [rsp, rpp]], dtype=float)

    # Enforce a numerical margin as well as the analytic passivity bound.
    radius = float(np.max(np.abs(np.linalg.eigvalsh(reflection))))
    if radius > _REFLECTION_LIMIT:
        reflection *= _REFLECTION_LIMIT / radius
    return reflection, kz0


def compute_anisotropic_fresnel_reflection(
    xi_meep, kx, ky, material_top, material_bot, medium_bg, theta_deg=90.0
):
    """
    Compute passive approximate 2x2 reflection matrices in the TE/TM frame.

    The in-plane dielectric tensors are rotated into the wavevector's
    longitudinal/transverse frame, so reflection depends on its azimuth.
    """
    xi_meep = _finite_scalar(xi_meep, "xi_meep")
    kx = _finite_scalar(kx, "kx")
    ky = _finite_scalar(ky, "ky")
    theta_deg = _finite_scalar(theta_deg, "theta_deg")
    if xi_meep < 0.0:
        raise ValueError("xi_meep must be nonnegative.")

    kp = np.hypot(kx, ky)
    if not np.isfinite(kp):
        raise ValueError("Transverse wavevector magnitude must be finite.")
    phi = np.arctan2(ky, kx)

    eps_bg, _, _, _ = _dielectric_tensor(medium_bg, xi_meep, 0.0)
    top_tensor = _dielectric_tensor(material_top, xi_meep, theta_deg)
    bot_tensor = _dielectric_tensor(material_bot, xi_meep, 0.0)

    R_top, kz0 = _passive_reflection(
        *top_tensor, eps_bg, xi_meep, kp, phi
    )
    R_bot, _ = _passive_reflection(
        *bot_tensor, eps_bg, xi_meep, kp, phi
    )
    return R_top, R_bot, kz0


def lifshitz_anisotropic_integrand(
    kp, phi, xi, d, material_top, material_bot, medium_bg, theta_deg,
    corrugation_boost=1.0
):
    """
    Lifshitz integrand with a passive tilted-facet field projection.

    The legacy corrugation_boost parameter now represents cos(alpha)**2,
    in [0, 1], rather than an active reflection gain. The projection leaves
    the tangential TE component unchanged and projects the TM component.
    """
    kp = _finite_scalar(kp, "kp")
    phi = _finite_scalar(phi, "phi")
    xi = _finite_scalar(xi, "xi")
    d = _finite_scalar(d, "d")
    corrugation_boost = _finite_scalar(corrugation_boost, "corrugation_boost")
    if kp < 0.0 or xi < 0.0 or d <= 0.0:
        raise ValueError("kp and xi must be nonnegative, and d must be positive.")
    if not 0.0 <= corrugation_boost <= 1.0:
        raise ValueError("corrugation_boost must be a passive projection in [0, 1].")
    if kp == 0.0:
        return 0.0

    kx = kp * np.cos(phi)
    ky = kp * np.sin(phi)
    R_t, R_b, kz0 = compute_anisotropic_fresnel_reflection(
        xi, kx, ky, material_top, material_bot, medium_bg, theta_deg
    )

    # Congruence with a contraction cannot increase the reflection norm.
    projection = np.diag([1.0, np.sqrt(corrugation_boost)])
    R_t_eff = projection @ R_t @ projection
    R_b_eff = projection @ R_b @ projection

    M = R_t_eff @ R_b_eff
    with np.errstate(over="ignore"):
        exp_factor = np.exp(-2.0 * kz0 * d)
    if exp_factor == 0.0:
        return 0.0

    scattering = M * exp_factor
    # Strictly contractive reflections ensure that I-scattering is invertible.
    # Do not hide poles with an additive epsilon in the determinant.
    tr_val = np.trace(np.linalg.solve(np.eye(2) - scattering, scattering))
    value = float(kp * kz0 * np.real(tr_val))
    if not np.isfinite(value):
        raise FloatingPointError("Non-finite Lifshitz integrand.")
    return value


def _quadrature_orders(max_steps):
    orders = [16, 16, 8]
    if max_steps is not None:
        # Reduce complete quadrature rules instead of truncating a partial sum.
        while int(np.prod(orders)) > max_steps:
            index = max(range(3), key=lambda i: orders[i])
            orders[index] -= 1
    return orders


def get_dispersive_casimir_pressure(
    d_um,
    material_top="BlackPhosphorus",
    material_bot="BlackPhosphorus",
    medium_bg="Teflon_AF",
    theta_deg=90.0,
    alpha_deg=75.0,
    T_K=0.0,
    max_steps=None,
):
    """
    Compute Casimir pressure in Pascals (positive = repulsive).

    At zero temperature, max_steps optionally bounds the number of
    integrand evaluations by reducing the complete quadrature orders.
    The tilted-facet treatment is a passive projection approximation,
    not an exact corrugated-interface scattering solution.
    """
    d_um = _finite_scalar(d_um, "d_um")
    theta_deg = _finite_scalar(theta_deg, "theta_deg")
    alpha_deg = _finite_scalar(alpha_deg, "alpha_deg")
    T_K = _finite_scalar(T_K, "T_K")
    max_steps = _validate_max_steps(max_steps)
    if d_um <= 0.0:
        raise ValueError("d_um must be positive.")
    if T_K < 0.0:
        raise ValueError("T_K must be nonnegative.")

    geom_factor = float(np.cos(np.radians(alpha_deg)) ** 2)
    MEEP_TO_PA = 0.0316152649

    if T_K != 0.0:
        from execution.run_thermal_matsubara_dsi import compute_matsubara_casimir_pressure

        kwargs = {}
        if max_steps is not None:
            signature = inspect.signature(compute_matsubara_casimir_pressure)
            if "max_steps" not in signature.parameters:
                raise ValueError(
                    "The thermal solver does not support max_steps; "
                    "use T_K=0 or omit max_steps."
                )
            kwargs["max_steps"] = max_steps
        pressure = compute_matsubara_casimir_pressure(
            d_um, T_K, material_top, material_bot, medium_bg,
            theta_deg, alpha_deg, **kwargs
        )
        return _finite_scalar(pressure, "pressure_Pa")

    xi_order, kp_order, phi_order = _quadrature_orders(max_steps)
    xi_max = 6.0 / d_um
    kp_max = 5.0 / d_um
    if not np.all(np.isfinite([xi_max, kp_max])):
        raise ValueError("Separation is too small for finite quadrature bounds.")

    xi_nodes, xi_weights = np.polynomial.legendre.leggauss(xi_order)
    xi_arr = 0.5 * xi_max * (xi_nodes + 1.0)
    w_xi = 0.5 * xi_max * xi_weights

    kp_nodes, kp_weights = np.polynomial.legendre.leggauss(kp_order)
    kp_arr = 0.5 * kp_max * (kp_nodes + 1.0)
    w_kp = 0.5 * kp_max * kp_weights

    phi_nodes, phi_weights = np.polynomial.legendre.leggauss(phi_order)
    phi_arr = np.pi * (phi_nodes + 1.0)
    w_phi = np.pi * phi_weights

    integral_val = 0.0
    for i_xi, xi_val in enumerate(xi_arr):
        for i_phi, phi_val in enumerate(phi_arr):
            for i_kp, kp_val in enumerate(kp_arr):
                integrand = lifshitz_anisotropic_integrand(
                    kp_val, phi_val, xi_val, d_um,
                    material_top, material_bot, medium_bg,
                    theta_deg, geom_factor,
                )
                integral_val += (
                    integrand * w_xi[i_xi] * w_phi[i_phi] * w_kp[i_kp]
                )

    net_pressure = -(1.0 / (4.0 * np.pi**3)) * integral_val * MEEP_TO_PA
    return _finite_scalar(net_pressure, "pressure_Pa")


def _log_metrics(result, outdir):
    """Use the repository metrics logger without assuming optional arguments."""
    from utils import metrics_logger

    context = {
        "metrics": result,
        "data": result,
        "results": result,
        "model": result["model"],
        "model_name": result["model"],
        "name": result["model"],
        "experiment_name": result["model"],
        "run_name": result["model"],
        "dataset": result["dataset"],
        "status": result["status"],
        "step": 0,
        "output_dir": outdir,
        "log_dir": outdir,
        "results_dir": outdir,
    }

    def invoke(function):
        args = []
        kwargs = {}
        for name, parameter in inspect.signature(function).parameters.items():
            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if name in context:
                value = context[name]
            elif parameter.default is not inspect.Parameter.empty:
                if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                    args.append(parameter.default)
                continue
            else:
                raise TypeError(
                    f"Unsupported required metrics_logger parameter: {name}"
                )
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                args.append(value)
            else:
                kwargs[name] = value
        return function(*args, **kwargs)

    log_function = getattr(metrics_logger, "log_metrics", None)
    if callable(log_function):
        invoke(log_function)
        return

    logger_class = getattr(metrics_logger, "MetricsLogger", None)
    if logger_class is None:
        raise AttributeError("utils.metrics_logger must expose log_metrics or MetricsLogger.")
    logger = invoke(logger_class)
    log_function = getattr(logger, "log_metrics", None)
    if not callable(log_function):
        log_function = getattr(logger, "log", None)
    if not callable(log_function):
        raise AttributeError("MetricsLogger must expose log_metrics or log.")
    invoke(log_function)


def main():
    parser = argparse.ArgumentParser(
        description="Passive Anisotropic Dispersive Casimir Solver (Challenge 2)."
    )
    parser.add_argument("--d", type=float, default=0.15, help="Separation in um.")
    parser.add_argument("--material-top", type=str, default="BlackPhosphorus", help="Top material.")
    parser.add_argument("--material-bot", type=str, default="BlackPhosphorus", help="Bottom material.")
    parser.add_argument("--medium", type=str, default="Teflon_AF", help="Immersion medium.")
    parser.add_argument("--theta", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument("--alpha", type=float, default=75.0, help="Facet angle in degrees.")
    parser.add_argument("--T", type=float, default=0.0, help="Temperature in Kelvin.")
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="Maximum zero-temperature integrand evaluations (default: 2048).",
    )
    parser.add_argument("--outdir", type=str, default="results")
    args = parser.parse_args()

    try:
        pressure = get_dispersive_casimir_pressure(
            d_um=args.d,
            material_top=args.material_top,
            material_bot=args.material_bot,
            medium_bg=args.medium,
            theta_deg=args.theta,
            alpha_deg=args.alpha,
            T_K=args.T,
            max_steps=args.max_steps,
        )
    except (ValueError, FloatingPointError) as exc:
        parser.error(str(exc))

    result = {
        "model": _MODEL,
        "dataset": f"{args.material_top}/{args.material_bot}/{args.medium}",
        "status": "completed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "d_um": args.d,
        "material_top": args.material_top,
        "material_bot": args.material_bot,
        "medium": args.medium,
        "theta_deg": args.theta,
        "alpha_deg": args.alpha,
        "T_K": args.T,
        "max_steps": args.max_steps,
        "pressure_Pa": float(pressure),
        "is_repulsive": bool(pressure > 0.0),
    }
    if args.T == 0.0:
        orders = _quadrature_orders(args.max_steps)
        result["quadrature_orders"] = orders
        result["steps"] = int(np.prod(orders))

    os.makedirs(args.outdir, exist_ok=True)
    _log_metrics(result, args.outdir)
    out_file = os.path.join(args.outdir, "anisotropic_dispersive_lifshitz.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, allow_nan=False)

    print(
        f"Dispersive simulation complete: d={args.d} um, "
        f"Medium={args.medium}, Theta={args.theta} deg -> "
        f"Pressure = {pressure:+.4f} Pa "
        f"(Repulsive: {result['is_repulsive']})"
    )


if __name__ == "__main__":
    main()
