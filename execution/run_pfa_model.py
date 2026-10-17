import argparse
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time

import numpy as np
import scipy.integrate as integrate

# Constants in Meep units (hbar = c = 1), with lengths in microns.
L = 0.3
T_77 = 77
T_300 = 300
HBAR_C_EV_UM = 0.1973269804
EV_TO_ANGULAR_UM = 1.0 / HBAR_C_EV_UM
MEEP_TO_ANGULAR = 2.0 * np.pi
KB_EV_K = 8.617333262e-5
KB_MEEP_K = KB_EV_K / HBAR_C_EV_UM
MATERIALS = ("PEC", "Gold", "Silicon")


def _finite_scalar(value, name, minimum=0.0, strictly_positive=False):
    if isinstance(value, (bool, str, bytes)) or not np.isscalar(value):
        raise ValueError(f"{name} must be a finite real scalar")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real scalar") from exc
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < minimum or (strictly_positive and value == minimum):
        relation = "greater than" if strictly_positive else "at least"
        raise ValueError(f"{name} must be {relation} {minimum}")
    return value


def _validate_material(material):
    if material not in MATERIALS:
        raise ValueError(f"Unknown material: {material}")


def get_epsilon_imag(xi, material_name):
    xi = _finite_scalar(xi, "xi")
    _validate_material(material_name)

    if material_name == "PEC":
        return -1e20

    try:
        import meep.materials as mat
    except ImportError:
        # Optical energies must be converted to angular wavenumbers (rad/um),
        # not Meep's cyclical frequencies (cycles/um).
        if material_name == "Gold":
            wp = 9.0 * EV_TO_ANGULAR_UM
            gam = 0.035 * EV_TO_ANGULAR_UM
            return 1.0 + wp**2 / (xi * (xi + gam) + 1e-30)

        w0 = 3.64 * EV_TO_ANGULAR_UM
        gam = 0.10 * EV_TO_ANGULAR_UM
        f0 = (11.87 - 1.0) * w0**2
        return 1.0 + f0 / (w0**2 + xi**2 + gam * xi + 1e-30)

    mat_obj = mat.Au if material_name == "Gold" else mat.cSi
    val = mat_obj.epsilon_diag.x
    for sus in mat_obj.E_susceptibilities:
        # Meep stores both resonance frequencies and damping in cycles/um.
        freq = MEEP_TO_ANGULAR * sus.frequency
        gamma = MEEP_TO_ANGULAR * sus.gamma
        sigma = sus.sigma_diag.x
        val += sigma * freq**2 / (
            freq**2 + xi**2 + gamma * xi + 1e-30
        )
    return val


def lifshitz_integrand(k_parallel, xi, d, material):
    k_parallel = _finite_scalar(k_parallel, "k_parallel")
    xi = _finite_scalar(xi, "xi")
    d = _finite_scalar(d, "d", strictly_positive=True)
    _validate_material(material)

    if material == "PEC":
        return 0.0  # Handled analytically.
    if k_parallel == 0.0:
        return 0.0

    eps = get_epsilon_imag(xi, material)

    kz = np.sqrt(xi**2 + k_parallel**2)
    kzm = np.sqrt(eps * xi**2 + k_parallel**2)

    # Fresnel reflection coefficients.
    rp = (eps * kz - kzm) / (eps * kz + kzm + 1e-15)
    rs = (kz - kzm) / (kz + kzm + 1e-15)

    exp_factor = np.exp(-2.0 * kz * d)
    term_p = rp**2 * exp_factor / (1.0 - rp**2 * exp_factor + 1e-15)
    term_s = rs**2 * exp_factor / (1.0 - rs**2 * exp_factor + 1e-15)

    return k_parallel * kz * (term_p + term_s)


def get_force_density_lifshitz(d, material, T=0):
    """
    Computes parallel plate force density in Meep units.
    If T > 0, performs Matsubara summation. If T == 0, performs
    imaginary-frequency integration.
    """
    d = _finite_scalar(d, "d", strictly_positive=True)
    T = _finite_scalar(T, "T")
    _validate_material(material)

    if material == "PEC":
        return -(np.pi**2) / (240.0 * d**4)

    if T == 0:
        def inner_int(xi, d, material):
            val, _ = integrate.quad(
                lambda kp: lifshitz_integrand(kp, xi, d, material),
                0,
                10.0 / d,
                limit=50,
            )
            return val

        val, _ = integrate.quad(
            lambda xi: inner_int(xi, d, material),
            0,
            10.0 / d,
            limit=50,
        )
        return -(1.0 / (2.0 * np.pi**2)) * val

    # xi_n = 2*pi*n*k_B*T/(hbar*c), in angular wavenumbers (rad/um).
    thermal_frequency = KB_MEEP_K * T
    delta_xi = 2.0 * np.pi * thermal_frequency
    if delta_xi == 0.0:
        return get_force_density_lifshitz(d, material, T=0)

    # Cap before converting to int to avoid overflow for very small T or d.
    cutoff = (10.0 / d) / delta_xi
    n_max = 500 if cutoff >= 499 else max(int(cutoff) + 1, 20)

    sum_val = 0.0
    for n in range(n_max):
        xi = n * delta_xi
        weight = 0.5 if n == 0 else 1.0

        val, _ = integrate.quad(
            lambda kp: lifshitz_integrand(kp, xi, d, material),
            0,
            10.0 / d,
            limit=50,
        )
        sum_val += weight * val

    return -(thermal_frequency / np.pi) * sum_val


def get_effective_area(N, L=L):
    if (
        isinstance(N, bool)
        or not isinstance(N, (int, np.integer))
        or N < 1
    ):
        raise ValueError("N must be a positive integer")
    L = _finite_scalar(L, "L", strictly_positive=True)
    return ((8.0 / 9.0)**(N - 1)) * L**2


def _nonnegative_int(value):
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "--max-steps must be a nonnegative integer"
        ) from exc
    if result < 0:
        raise argparse.ArgumentTypeError(
            "--max-steps must be a nonnegative integer"
        )
    return result


def _log_metrics(metrics):
    # Make the repository's utils package accessible when this file is run
    # directly as python execution/run_pfa_model.py.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from utils.metrics_logger import log_metrics
    except ModuleNotFoundError as exc:
        if exc.name not in ("utils", "utils.metrics_logger"):
            raise
        # Keep standalone execution usable when the repository utility is absent.
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            "utils.metrics_logger is unavailable; logging metrics locally."
        )
        logging.getLogger(__name__).info(
            "%s", json.dumps(metrics, allow_nan=False)
        )
    else:
        log_metrics(metrics)


def main():
    parser = argparse.ArgumentParser(description="Run the Lifshitz PFA baseline.")
    parser.add_argument(
        "--max-steps",
        type=_nonnegative_int,
        default=None,
        help="Maximum number of force evaluations across the sweep (default: all).",
    )
    args = parser.parse_args()

    separations = np.logspace(np.log10(0.02), np.log10(1.0), 30)
    generations = [1, 2, 3, 4]
    temperatures = [0, T_77, T_300]

    results = {
        "model": "Lifshitz_PFA_3D",
        "dataset": "pfa_baseline_verification",
    }
    steps = 0
    started_at = time.perf_counter()

    def limit_reached():
        return args.max_steps is not None and steps >= args.max_steps

    print("Running PFA analytical model baseline calculations...")
    for mat in MATERIALS:
        if limit_reached():
            break
        results[mat] = {}
        for T in temperatures:
            if limit_reached():
                break
            t_label = f"T_{T}" if T > 0 else "T_0"
            results[mat][t_label] = {}
            for N in generations:
                if limit_reached():
                    break
                records = []
                results[mat][t_label][f"N_{N}"] = records
                area = get_effective_area(N)
                for d in separations:
                    if limit_reached():
                        break
                    f_dens = get_force_density_lifshitz(d, mat, T)
                    force = float(f_dens * area)
                    if not np.isfinite(force):
                        raise ValueError(
                            f"Non-finite force for material={mat}, T={T}, N={N}, d={d}"
                        )
                    records.append({
                        "d_nm": float(d * 1000.0),
                        "force_val": force,
                    })
                    steps += 1

    results["status"] = "completed"
    results["executed_at"] = datetime.now(timezone.utc).isoformat()
    results["steps_completed"] = steps
    results["max_steps"] = args.max_steps

    os.makedirs(".tmp", exist_ok=True)
    output_path = ".tmp/pfa_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, allow_nan=False)

    _log_metrics({
        "model": results["model"],
        "dataset": results["dataset"],
        "status": results["status"],
        "executed_at": results["executed_at"],
        "steps_completed": steps,
        "max_steps": args.max_steps,
        "elapsed_seconds": time.perf_counter() - started_at,
        "output_path": output_path,
    })
    print(
        "PFA analytical model baseline calculations complete. "
        f"Saved to {output_path}"
    )


if __name__ == "__main__":
    main()
