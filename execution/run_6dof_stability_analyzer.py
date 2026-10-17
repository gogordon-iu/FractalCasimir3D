"""
6-DOF Mechanical Stability Matrix & Earnshaw's Theorem Analyzer (Nature Challenge 3)
-----------------------------------------------------------------------------------
Evaluates the 6x6 stiffness matrix for translational and rotational degrees of
freedom. Rotational coordinates are scaled by a characteristic plate length so
the generalized stiffness matrix has homogeneous units of pN/um.
"""

import os
import sys
import json
import argparse
import inspect
from datetime import datetime, timezone
from numbers import Integral, Real

import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _finite_scalar(name, value, positive=False):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real scalar.")
    value = float(value)
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    if positive and value <= 0.0:
        raise ValueError(f"{name} must be positive.")
    return value


def _validate_max_steps(max_steps):
    if isinstance(max_steps, bool) or not isinstance(max_steps, Integral):
        raise TypeError("max_steps must be a positive integer.")
    if max_steps <= 0:
        raise ValueError("max_steps must be a positive integer.")
    return int(max_steps)


def _casimir_energy(
    z_sep_um,
    material_top,
    material_bot,
    medium,
    theta_z_deg,
    alpha_deg,
    area_um2,
    max_steps
):
    """
    Interaction energy in pN*um, with E(infinity) = 0.

    Since Fz = Area * P = -dE/dz, E(z) = Area * integral_z^infinity P(s) ds.
    Gauss-Legendre quadrature uses s = z / (1 - t), 0 < t < 1.
    """
    from execution.run_anisotropic_dispersive_lifshitz import (
        get_dispersive_casimir_pressure,
    )

    nodes, weights = np.polynomial.legendre.leggauss(max_steps)
    t = 0.5 * (nodes + 1.0)
    weights = 0.5 * weights
    separations = z_sep_um / (1.0 - t)
    jacobian = z_sep_um / (1.0 - t) ** 2

    pressures = np.array([
        _finite_scalar(
            "Casimir pressure",
            get_dispersive_casimir_pressure(
                float(separation),
                material_top,
                material_bot,
                medium,
                theta_z_deg,
                alpha_deg,
                T_K=0.0
            )
        )
        for separation in separations
    ])
    return _finite_scalar(
        "Casimir energy",
        area_um2 * np.dot(weights, pressures * jacobian)
    )


def compute_6dof_forces_and_torques(
    x_offset_um=0.0,
    y_offset_um=0.0,
    z_sep_um=0.15,
    theta_x_deg=0.0,
    theta_y_deg=0.0,
    theta_z_deg=90.0,
    alpha_deg=75.0,
    L_um=2.0,
    d_eq_um=0.15,
    material_top="BlackPhosphorus",
    material_bot="BlackPhosphorus",
    medium="Teflon_AF",
    max_steps=32
):
    """
    Returns translational forces (Fx, Fy, Fz) in pN and physical angular
    torques (tau_x, tau_y, tau_z) in pN*um. Angular inputs remain in degrees.
    """
    from execution.run_anisotropic_dispersive_lifshitz import (
        get_dispersive_casimir_pressure,
    )

    x_offset_um = _finite_scalar("x_offset_um", x_offset_um)
    y_offset_um = _finite_scalar("y_offset_um", y_offset_um)
    z_sep_um = _finite_scalar("z_sep_um", z_sep_um, positive=True)
    theta_x_deg = _finite_scalar("theta_x_deg", theta_x_deg)
    theta_y_deg = _finite_scalar("theta_y_deg", theta_y_deg)
    theta_z_deg = _finite_scalar("theta_z_deg", theta_z_deg)
    alpha_deg = _finite_scalar("alpha_deg", alpha_deg)
    L_um = _finite_scalar("L_um", L_um, positive=True)
    _finite_scalar("d_eq_um", d_eq_um, positive=True)
    max_steps = _validate_max_steps(max_steps)
    if not 0.0 <= alpha_deg < 90.0:
        raise ValueError("alpha_deg must lie in [0, 90).")

    Area = ((8.0 / 9.0) ** 2) * (L_um ** 2)

    def pressure(separation, angle):
        return _finite_scalar(
            "Casimir pressure",
            get_dispersive_casimir_pressure(
                separation,
                material_top,
                material_bot,
                medium,
                angle,
                alpha_deg,
                T_K=0.0
            )
        )

    # 1. Normal force and local normal stiffness density.
    P_z = pressure(z_sep_um, theta_z_deg)
    Fz = P_z * Area

    # Keep the central-difference stencil at positive separations.
    dz_test = min(0.005, 0.5 * z_sep_um)
    if dz_test <= 0.0 or z_sep_um + dz_test == z_sep_um:
        raise ValueError("z_sep_um is too small for a finite-difference stencil.")
    P_plus = pressure(z_sep_um + dz_test, theta_z_deg)
    P_minus = pressure(z_sep_um - dz_test, theta_z_deg)
    dP_dz = (P_plus - P_minus) / (2.0 * dz_test)

    # 2. Lateral restoring forces from corrugation potential modulation.
    Lambda = L_um / 9.0
    h_pyr = min((Lambda / 2.0) * np.tan(np.radians(alpha_deg)), 0.3)
    Delta_E = abs(P_z) * h_pyr * Area * 0.1
    k_lat = ((2.0 * np.pi / Lambda) ** 2) * Delta_E
    Fx = -k_lat * x_offset_um
    Fy = -k_lat * y_offset_um

    # 3. Physical tilt torques; stiffness is per radian, not per degree.
    I_plate = Area * (L_um ** 2) / 12.0
    k_tilt_rad = -dP_dz * I_plate
    tau_x = -k_tilt_rad * np.radians(theta_x_deg)
    tau_y = -k_tilt_rad * np.radians(theta_y_deg)

    # 4. Physical torsional torque: tau_z = -dE/dtheta_rad.
    # Do not multiply this derivative by an angular displacement.
    dth_test_deg = 1.0
    E_plus = _casimir_energy(
        z_sep_um, material_top, material_bot, medium,
        theta_z_deg + dth_test_deg, alpha_deg, Area, max_steps
    )
    E_minus = _casimir_energy(
        z_sep_um, material_top, material_bot, medium,
        theta_z_deg - dth_test_deg, alpha_deg, Area, max_steps
    )
    tau_z = -(E_plus - E_minus) / (2.0 * np.radians(dth_test_deg))

    forces = np.array([Fx, Fy, Fz, tau_x, tau_y, tau_z], dtype=float)
    if not np.all(np.isfinite(forces)):
        raise ValueError("Computed forces and torques must be finite.")
    return forces


def compute_stiffness_matrix_6x6(
    d_eq_um=0.15,
    alpha_deg=75.0,
    L_um=2.0,
    theta_z_eq=90.0,
    dx_nm=2.0,
    dz_nm=2.0,
    dtheta_deg=0.5,
    max_steps=32
):
    """
    Computes K_ij = -dG_i/dQ_j via central finite differences.

    Q = (x, y, z, L_char*theta_x_rad, L_char*theta_y_rad,
         L_char*theta_z_rad), in um.
    G = (Fx, Fy, Fz, tau_x/L_char, tau_y/L_char, tau_z/L_char),
        in pN.

    Thus every entry of K has units of pN/um. Public angular inputs remain
    in degrees.
    """
    d_eq_um = _finite_scalar("d_eq_um", d_eq_um, positive=True)
    alpha_deg = _finite_scalar("alpha_deg", alpha_deg)
    L_um = _finite_scalar("L_um", L_um, positive=True)
    theta_z_eq = _finite_scalar("theta_z_eq", theta_z_eq)
    dx_nm = _finite_scalar("dx_nm", dx_nm, positive=True)
    dz_nm = _finite_scalar("dz_nm", dz_nm, positive=True)
    dtheta_deg = _finite_scalar("dtheta_deg", dtheta_deg, positive=True)
    max_steps = _validate_max_steps(max_steps)
    if not 0.0 <= alpha_deg < 90.0:
        raise ValueError("alpha_deg must lie in [0, 90).")

    dx_um = dx_nm * 1e-3
    dz_um = dz_nm * 1e-3
    if dz_um >= d_eq_um:
        raise ValueError("dz_nm must be smaller than the equilibrium separation.")

    Area_um2 = ((8.0 / 9.0) ** 2) * (L_um ** 2)
    L_char = _finite_scalar("L_char", np.sqrt(Area_um2), positive=True)

    # These perturbations are expressed in the public input units.
    dq_input = np.array(
        [dx_um, dx_um, dz_um, dtheta_deg, dtheta_deg, dtheta_deg],
        dtype=float
    )
    # Denominators use homogeneous generalized length coordinates.
    dq_generalized = dq_input.copy()
    dq_generalized[3:] = L_char * np.radians(dq_input[3:])
    if not np.all(np.isfinite(dq_generalized)) or np.any(dq_generalized <= 0.0):
        raise ValueError("Generalized finite-difference steps must be finite and positive.")

    q_eq = np.array(
        [0.0, 0.0, d_eq_um, 0.0, 0.0, theta_z_eq],
        dtype=float
    )
    K = np.zeros((6, 6), dtype=float)

    def generalized_forces(q):
        forces = compute_6dof_forces_and_torques(
            x_offset_um=q[0],
            y_offset_um=q[1],
            z_sep_um=q[2],
            theta_x_deg=q[3],
            theta_y_deg=q[4],
            theta_z_deg=q[5],
            alpha_deg=alpha_deg,
            L_um=L_um,
            d_eq_um=d_eq_um,
            max_steps=max_steps
        )
        forces = np.asarray(forces, dtype=float)
        if forces.shape != (6,) or not np.all(np.isfinite(forces)):
            raise ValueError("The force evaluator must return six finite components.")
        forces = forces.copy()
        forces[3:] /= L_char
        return forces

    for j in range(6):
        q_plus = q_eq.copy()
        q_minus = q_eq.copy()
        q_plus[j] += dq_input[j]
        q_minus[j] -= dq_input[j]
        if q_plus[j] == q_eq[j] or q_minus[j] == q_eq[j]:
            raise ValueError("Finite-difference step is too small for the coordinate.")

        F_plus = generalized_forces(q_plus)
        F_minus = generalized_forces(q_minus)
        K[:, j] = -(F_plus - F_minus) / (2.0 * dq_generalized[j])

    if not np.all(np.isfinite(K)):
        raise ValueError("Computed stiffness matrix must be finite.")
    return K


def evaluate_6dof_stability(
    d_eq_um=0.15,
    alpha_deg=75.0,
    L_um=2.0,
    theta_z_eq=90.0,
    max_steps=32
):
    """
    Computes eigenvalues of the dimensionally homogeneous symmetric stiffness
    matrix and checks positive definiteness within the specified force model.
    """
    d_eq_um = _finite_scalar("d_eq_um", d_eq_um, positive=True)
    alpha_deg = _finite_scalar("alpha_deg", alpha_deg)
    L_um = _finite_scalar("L_um", L_um, positive=True)
    theta_z_eq = _finite_scalar("theta_z_eq", theta_z_eq)
    max_steps = _validate_max_steps(max_steps)

    K = compute_stiffness_matrix_6x6(
        d_eq_um, alpha_deg, L_um, theta_z_eq, max_steps=max_steps
    )
    K = np.asarray(K, dtype=float)
    if K.shape != (6, 6) or not np.all(np.isfinite(K)):
        raise ValueError("The stiffness matrix must be a finite 6x6 array.")

    K_sym = 0.5 * K + 0.5 * K.T
    eigenvalues, eigenvectors = np.linalg.eigh(K_sym)
    idx = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    if not np.all(np.isfinite(eigenvalues)):
        raise ValueError("Stiffness eigenvalues must be finite.")

    is_stable = bool(np.all(eigenvalues > 0.0))
    min_eigenvalue = float(np.min(eigenvalues))
    L_char = np.sqrt(((8.0 / 9.0) ** 2) * (L_um ** 2))

    dof_names = [
        "x (lateral)", "y (lateral)", "z (normal)",
        "theta_x (pitch)", "theta_y (roll)", "theta_z (yaw)"
    ]

    return {
        "model": "6dof_stability_analyzer",
        "dataset": "dispersive_lifshitz",
        "status": "completed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "d_eq_um": d_eq_um,
        "alpha_deg": alpha_deg,
        "L_um": L_um,
        "theta_z_eq": theta_z_eq,
        "max_steps": max_steps,
        "L_char_um": float(L_char),
        "generalized_coordinate_units": "um",
        "generalized_force_units": "pN",
        "stiffness_units": "pN/um",
        "stiffness_matrix_K": K.tolist(),
        "stiffness_matrix_K_sym": K_sym.tolist(),
        "eigenvalues": eigenvalues.tolist(),
        "eigenvectors": eigenvectors.tolist(),
        "min_eigenvalue": min_eigenvalue,
        "is_unconditionally_stable_6dof": is_stable,
        "dof_labels": dof_names
    }


def _log_metrics(report, outdir):
    """Log through the project's function-based or class-based metrics API."""
    from utils import metrics_logger

    metrics = {
        "model": report["model"],
        "dataset": report["dataset"],
        "status": report["status"],
        "executed_at": report["executed_at"],
        "max_steps": report["max_steps"],
        "min_eigenvalue": report["min_eigenvalue"],
        "is_unconditionally_stable_6dof": report["is_unconditionally_stable_6dof"],
        "eigenvalues": report["eigenvalues"]
    }
    context = {
        "metrics": metrics,
        "record": metrics,
        "data": metrics,
        "model": report["model"],
        "model_name": report["model"],
        "dataset": report["dataset"],
        "dataset_name": report["dataset"],
        "status": report["status"],
        "executed_at": report["executed_at"],
        "run_name": report["model"],
        "name": report["model"],
        "output_dir": outdir,
        "log_dir": outdir,
        "log_file": os.path.join(outdir, "stability_6dof_metrics.jsonl"),
        "log_path": os.path.join(outdir, "stability_6dof_metrics.jsonl")
    }

    def invoke(function):
        signature = inspect.signature(function)
        positional = []
        keywords = {}
        for parameter in signature.parameters.values():
            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD
            ):
                continue
            if parameter.name in context:
                value = context[parameter.name]
            elif parameter.default is not inspect.Parameter.empty:
                continue
            else:
                raise TypeError(
                    f"Unsupported metrics_logger parameter: {parameter.name}"
                )
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
                positional.append(value)
            else:
                keywords[parameter.name] = value
        return function(*positional, **keywords)

    function = getattr(metrics_logger, "log_metrics", None)
    if callable(function):
        invoke(function)
        return

    logger = invoke(metrics_logger.MetricsLogger)
    for method_name in ("log_metrics", "log"):
        method = getattr(logger, method_name, None)
        if callable(method):
            invoke(method)
            return

    method = getattr(logger, "log_metric", None)
    if callable(method):
        for name in ("min_eigenvalue", "is_unconditionally_stable_6dof"):
            method(name, metrics[name])
        return
    raise TypeError("utils.metrics_logger does not expose a supported logging API.")


def main():
    parser = argparse.ArgumentParser(
        description="6-DOF Mechanical Stability Matrix Solver (Challenge 3)."
    )
    parser.add_argument("--d-eq", type=float, default=0.15, help="Equilibrium height in um.")
    parser.add_argument("--alpha", type=float, default=75.0, help="Corrugation angle in degrees.")
    parser.add_argument("--L", type=float, default=2.0, help="Plate length in um.")
    parser.add_argument("--theta-z", type=float, default=90.0, help="Twist angle in degrees.")
    parser.add_argument(
        "--max-steps", type=int, default=32,
        help="Number of quadrature steps for the angular interaction energy."
    )
    parser.add_argument("--outdir", type=str, default="results")
    args = parser.parse_args()

    try:
        report = evaluate_6dof_stability(
            d_eq_um=args.d_eq,
            alpha_deg=args.alpha,
            L_um=args.L,
            theta_z_eq=args.theta_z,
            max_steps=args.max_steps
        )
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    os.makedirs(args.outdir, exist_ok=True)
    out_file = os.path.join(args.outdir, "stability_6dof_analysis.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, allow_nan=False)

    _log_metrics(report, args.outdir)

    print("==================================================")
    print("6-DOF MECHANICAL STIFFNESS MATRIX & STABILITY REPORT")
    print("==================================================")
    print(
        f"Equilibrium Height d_eq: {args.d_eq * 1000.0:.1f} nm, "
        f"Corrugation Alpha: {args.alpha:.1f} deg"
    )
    print("6-DOF Eigenvalues (lambda_1 to lambda_6), in pN/um:")
    for i, val in enumerate(report["eigenvalues"]):
        print(f"  Mode {i + 1}: lambda_{i + 1} = {val:+.4e}")
    print(f"Minimum Eigenvalue lambda_min: {report['min_eigenvalue']:+.4e}")
    status = (
        "UNCONDITIONALLY STABLE (ALL 6 EIGENVALUES > 0)"
        if report["is_unconditionally_stable_6dof"]
        else "UNSTABLE OR MARGINAL"
    )
    print(f"Model Stability Status: {status}")
    print(f"Saved report to: {out_file}")


if __name__ == "__main__":
    main()
