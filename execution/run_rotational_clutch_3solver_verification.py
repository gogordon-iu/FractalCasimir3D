#!/usr/bin/env python3
"""Multi-resolution verification of the stepped concentric Cantor clutch.

Run from the repository root, for example::

    python execution/run_rotational_clutch_3solver_verification.py --max-steps 1
    python execution/run_rotational_clutch_3solver_verification.py --device auto

Solver errors are fatal; completed results are retained in the JSON report.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime
import hashlib
import inspect
import json
import math
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from execution import casimir_bem_solver as bem
from execution.run_rotational_z_eff_clutch import (
    DEFAULT_DESIGNS,
    SECTOR_DEG,
    SYMMETRY_ORDER,
    Z_PAD_TOP_UM,
    Z_ROTOR_TOP_UM,
    Z_TIP_FIXED_UM,
    angular_state,
    build_rotational_stepped_clutch_mesh,
    collision_certificate,
    resolve_design,
)
from utils import metrics_logger

HBAR = 1.054571817e-34
C_LIGHT = 299_792_458.0
GAP_UM = 0.015
CAMPAIGN = "rotational_clutch_3solver_verification"
DESIGN_NAMES = (
    "Rot_C4_TightSlot_N2",
    "Rot_C8_Compact_N2",
    "Rot_C10_Fractal_N3",
)
TIERS: tuple[dict[str, Any], ...] = (
    dict(tier="Standard", n_r=2, n_phi_tooth=3, n_phi_bridge=3, n_z=2, n_xi=24),
    dict(tier="High", n_r=3, n_phi_tooth=4, n_phi_bridge=4, n_z=3, n_xi=32),
    dict(tier="Ultra_High", n_r=4, n_phi_tooth=6, n_phi_bridge=6, n_z=4, n_xi=40),
)
FORMULATIONS = ("vector_dyadic", "scalar_yukawa")


def plain(value: Any) -> Any:
    """Convert scientific data to strict JSON-compatible objects."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return plain(dataclasses.asdict(value))
    if isinstance(value, torch.Tensor):
        return plain(value.detach().cpu().numpy())
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite value cannot enter a report: {value!r}")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "__dict__"):
        return plain(vars(value))
    return repr(value)


def finite_float(value: Any, label: str) -> float:
    if isinstance(value, torch.Tensor):
        if value.numel() != 1:
            raise ValueError(f"{label} must be a scalar")
        value = value.detach().cpu().item()
    array = np.asarray(value)
    if array.size != 1:
        raise ValueError(f"{label} must be scalar")
    scalar = array.item()
    if isinstance(scalar, bool) or not isinstance(scalar, (int, float)):
        raise TypeError(f"{label} must be a real number")
    result = float(scalar)
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(plain(data), stream, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_design(name: str) -> Any:
    matches = [item for item in DEFAULT_DESIGNS if item["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one default design named {name!r}")
    return resolve_design(matches[0], "concentric_cantor")


def gold_material() -> Any:
    return bem.MaterialModel.from_parameters({"material": "Gold"})


def lifshitz_pressure(material: Any) -> float:
    """Zero-temperature, identical-Gold half-space pressure, in Pa.

    xi = (c/g) t/(1-t), t in (0,1). The material API takes the scalar
    imaginary wave number xi/c in inverse micrometres, not SI frequency.

    The Laguerre coordinate is y = 2*g*kappa - 2*g*xi/c, so its
    exponential weight is exact.
    """
    gap = GAP_UM * 1e-6
    nodes, weights = np.polynomial.legendre.leggauss(128)
    t = (nodes + 1.0) * 0.5
    frequency_weights = weights * 0.5 * (C_LIGHT / gap) / (1.0 - t) ** 2
    xi = (C_LIGHT / gap) * t / (1.0 - t)
    epsilon = np.array(
        [
            float(material.epsilon(float(k)))
            for k in (xi / C_LIGHT * 1e-6)
        ],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(epsilon)) or np.any(epsilon < 1.0):
        raise ValueError("Invalid passive Gold imaginary-axis permittivity")

    laguerre_nodes, laguerre_weights = np.polynomial.laguerre.laggauss(96)
    lower = 2.0 * gap * xi / C_LIGHT
    x = lower[:, None] + laguerre_nodes[None, :]
    kappa = x / (2.0 * gap)
    medium_kappa = np.sqrt(
        kappa**2 + (epsilon[:, None] - 1.0) * (xi[:, None] / C_LIGHT) ** 2
    )
    r_te = (kappa - medium_kappa) / (kappa + medium_kappa)
    eps_kappa = epsilon[:, None] * kappa
    r_tm = (eps_kappa - medium_kappa) / (eps_kappa + medium_kappa)
    exponential = np.exp(-x)
    total = np.zeros_like(x)
    for reflection in (r_te, r_tm):
        squared = np.clip(reflection**2, 0.0, 1.0)
        denominator = 1.0 - squared * exponential
        if not np.all(np.isfinite(denominator)) or np.any(denominator <= 0.0):
            raise FloatingPointError("Invalid Lifshitz denominator")
        total += squared / denominator
    transverse_integral = (
        np.exp(-lower)
        * np.sum(laguerre_weights[None, :] * x**2 * total, axis=1)
        / (8.0 * gap**3)
    )
    pressure = -HBAR / (2.0 * math.pi**2) * np.dot(
        frequency_weights, transverse_integral
    )
    return finite_float(pressure, "Lifshitz pressure")


def polar_overlap_um2(spec: Any, mesh: Any, theta: float) -> float:
    """Exact four-sector horizontal tooth/landing-pad overlap in um²."""
    theta = finite_float(theta, "theta_deg")
    tooth_arc = finite_float(spec.tooth_arc_deg, "tooth_arc_deg")
    if not 0.0 < tooth_arc <= float(SECTOR_DEG):
        raise ValueError("Invalid tooth angular width")

    area = 0.0
    element_count = 0
    for element in spec.elements:
        inner = finite_float(element.r_tooth_in, "r_tooth_in")
        outer = finite_float(element.r_tooth_out, "r_tooth_out")
        if not 0.0 <= inner < outer:
            raise ValueError("Invalid tooth radial interval")
        area += 4.0 * 0.5 * (outer**2 - inner**2) * math.radians(tooth_arc)
        element_count += 1
    if element_count == 0:
        raise ValueError("Design contains no tooth elements")

    fraction = finite_float(
        angular_state(spec, theta)["landing_pad_fraction"],
        "landing_pad_fraction",
    )
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("Landing-pad fraction must be between zero and one")
    return finite_float(area * fraction, "polar overlap area")


def export_scuff(mesh: Any, directory: Path, task_id: str) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    rotor_tri = bem._triangular_mesh(mesh.rotor, mesh.geometry.R_max)
    stator_tri = bem._triangular_mesh(mesh.stator, mesh.geometry.R_max)
    records: list[dict[str, Any]] = []
    for label, tri_mesh in (("rotor", rotor_tri), ("stator", stator_tri)):
        path = directory / f"{task_id}_{label}.msh"
        bem._write_gmsh_v2(path, tri_mesh)
        if not path.is_file():
            raise FileNotFoundError(f"Gmsh writer did not create {path}")
        with path.open("r", encoding="utf-8") as stream:
            header = stream.read(256)
        if "$MeshFormat" not in header or "2.2" not in header:
            raise ValueError(f"SCUFF export is not Gmsh v2.2: {path}")

        # Count exported elements rather than assuming a native triangle container.
        triangle_count = 0
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip() == "$Elements":
                    count = int(next(stream).strip())
                    for _ in range(count):
                        element = next(stream).split()
                        if len(element) < 3:
                            raise ValueError(f"Malformed Gmsh element in {path}")
                        if int(element[1]) == 2:
                            triangle_count += 1
                    break
            else:
                raise ValueError(f"Missing Gmsh element section in {path}")
        if triangle_count == 0:
            raise ValueError(f"SCUFF export contains no triangles: {path}")

        records.append(
            dict(
                body=label,
                path=str(path),
                sha256=sha256(path),
                triangle_count=triangle_count,
                coordinate_unit="um",
            )
        )

    geo = directory / f"{task_id}.scuffgeo"
    geo.write_text(
        "// Geometry export only; SCUFF is not counted as a fourth solver.\n"
        "// Gold must resolve to SCUFF's dispersive Gold material database.\n"
        "// Its dielectric parameters must be matched before external comparison.\n"
        + "\n".join(
            f"OBJECT {record['body']}\n"
            f"    MESHFILE {Path(record['path']).name}\n"
            "    MATERIAL Gold\n"
            "ENDOBJECT\n"
            for record in records
        ),
        encoding="utf-8",
    )
    return dict(
        meshes=records,
        scuffgeo_path=str(geo),
        scuffgeo_sha256=sha256(geo),
        externally_executed=False,
        material_equivalence_verified=False,
    )


def load_hybrid_comparison() -> dict[str, Any] | None:
    path = REPOSITORY_ROOT / "results" / "real_world_nems_clutch_report.json"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as stream:
        source_report = json.load(stream)
    if not isinstance(source_report, Mapping):
        raise TypeError(f"Expected an object in {path}")
    return dict(
        title="Hybrid Multi-Scale Active-Zone vs Full-Monolithic",
        source_path=str(path),
        source_sha256=sha256(path),
        source_report=plain(source_report),
        scope=(
            "Imported comparison from the real-world NEMS clutch campaign; "
            "not an additional solver execution in this verification."
        ),
    )


def sign(value: float, tolerance: float = 1e-12) -> int:
    value = finite_float(value, "force")
    return 0 if abs(value) <= tolerance else (1 if value > 0.0 else -1)


def relative_difference(a: float, reference: float) -> float | None:
    a = finite_float(a, "force")
    reference = finite_float(reference, "reference force")
    if abs(reference) <= 1e-12:
        return None
    return finite_float(abs(a - reference) / abs(reference), "relative difference")


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for design in DESIGN_NAMES:
        angles = sorted({row["theta_deg"] for row in rows if row["design"] == design})
        for theta in angles:
            group = [
                row for row in rows
                if row["design"] == design and row["theta_deg"] == theta
            ]
            by_tier = {row["tier"]: row for row in group}
            highest = max(group, key=lambda row: row["tier_index"])
            record: dict[str, Any] = dict(
                model=CAMPAIGN,
                dataset=CAMPAIGN,
                status="completed",
                executed_at=highest["executed_at"],
                design=design,
                theta_deg=theta,
                highest_tier=highest["tier"],
                comparisons={},
            )
            for formulation in FORMULATIONS:
                values: dict[str, Any] = {}
                for low, high in (("Standard", "High"), ("High", "Ultra_High")):
                    if low in by_tier and high in by_tier:
                        values[f"{low}_to_{high}"] = relative_difference(
                            by_tier[low]["forces_pN"][formulation],
                            by_tier[high]["forces_pN"][formulation],
                        )
                bem_force = highest["forces_pN"][formulation]
                pfa_force = highest["forces_pN"]["lifshitz_pfa"]
                values["signed_nonadditive_edge_fraction"] = (
                    None
                    if abs(bem_force) <= 1e-12
                    else finite_float(
                        (bem_force - pfa_force) / abs(bem_force),
                        "signed non-additive fraction",
                    )
                )
                values["absolute_nonadditive_edge_fraction"] = relative_difference(
                    pfa_force, bem_force
                )
                record["comparisons"][formulation] = values
            output.append(record)
    return output


def write_tables(
    rows: list[dict[str, Any]],
    convergence: list[dict[str, Any]],
    output: Path,
    hybrid_comparison: dict[str, Any] | None = None,
) -> None:
    csv_path = output / CAMPAIGN / "convergence_results.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "model", "dataset", "status", "executed_at", "timestamp",
        "design", "theta_deg", "state", "tier", "n_r", "n_phi_tooth",
        "n_phi_bridge", "n_z", "n_xi", "panel_count", "vector_dofs",
        "scalar_dofs", "vector_dyadic_F_z_pN", "scalar_yukawa_F_z_pN",
        "lifshitz_pfa_F_z_pN", "vector_runtime_s", "scalar_runtime_s",
        "pfa_runtime_s", "bem_sign_agreement", "all_three_sign_agreement",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            flat = {name: row.get(name) for name in columns}
            flat["model"] = CAMPAIGN
            flat["dataset"] = CAMPAIGN
            flat["status"] = "completed"
            flat["executed_at"] = row["executed_at"]
            flat["timestamp"] = row["executed_at"]
            for name in ("n_r", "n_phi_tooth", "n_phi_bridge", "n_z", "n_xi"):
                flat[name] = row["resolution"][name]
            for formulation in (*FORMULATIONS, "lifshitz_pfa"):
                flat[f"{formulation}_F_z_pN"] = row["forces_pN"][formulation]
            flat["vector_runtime_s"] = row["runtime_s"]["vector_dyadic"]
            flat["scalar_runtime_s"] = row["runtime_s"]["scalar_yukawa"]
            flat["pfa_runtime_s"] = row["runtime_s"]["lifshitz_pfa"]
            writer.writerow(flat)

    lines = [
        "# Rotational clutch three-solver verification",
        "",
        "Positive force denotes repulsion; negative force denotes attraction. "
        "PFA includes only the exact polar tooth–landing-pad overlap at 15 nm. "
        "It omits bridges, sidewalls, diffraction and nonlocal interactions; "
        "zero PFA in an aperture is therefore not a failed sign prediction.",
        "",
        "Frequency and mesh resolution increase together. The ladder measures "
        "combined discretization change, not an independently isolated mesh error.",
        "",
        "| Design | θ (deg) | State | Tier | ξ nodes | Panels | Vector DOFs | "
        "Scalar DOFs | Vector (pN) | Scalar (pN) | PFA (pN) | "
        "Vector / scalar / PFA runtime (s) | BEM signs agree | All signs agree |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        forces = row["forces_pN"]
        runtimes = row["runtime_s"]
        lines.append(
            f"| {row['design']} | {row['theta_deg']:g} | {row['state']} | "
            f"{row['tier']} | {row['resolution']['n_xi']} | {row['panel_count']} | "
            f"{row['vector_dofs']} | {row['scalar_dofs']} | "
            f"{forces['vector_dyadic']:.8g} | {forces['scalar_yukawa']:.8g} | "
            f"{forces['lifshitz_pfa']:.8g} | "
            f"{runtimes['vector_dyadic']:.3f} / {runtimes['scalar_yukawa']:.3f} / "
            f"{runtimes['lifshitz_pfa']:.3f} | {row['bem_sign_agreement']} | "
            f"{row['all_three_sign_agreement']} |"
        )
    lines.extend(
        [
            "",
            "## Convergence and non-additive residual",
            "",
            "Relative differences use the finer-tier force magnitude as denominator; "
            "a numerically zero denominator is reported as null. The signed residual "
            "(F_BEM − F_PFA)/|F_BEM| is a diagnostic, not an isolated measurement of "
            "edge diffraction: omitted surfaces and scalar/vector model differences "
            "also contribute.",
            "",
            "```json",
            json.dumps(plain(convergence), indent=2, allow_nan=False),
            "```",
            "",
            "## Hybrid Multi-Scale Active-Zone vs Full-Monolithic",
            "",
        ]
    )
    if hybrid_comparison is None:
        lines.append(
            "No results/real_world_nems_clutch_report.json was present; "
            "no external comparison has been inferred."
        )
    else:
        lines.extend(
            [
                hybrid_comparison["scope"],
                "",
                f"Source: `{hybrid_comparison['source_path']}`",
                f"SHA256: `{hybrid_comparison['source_sha256']}`",
                "",
                "```json",
                json.dumps(
                    hybrid_comparison["source_report"], indent=2, allow_nan=False
                ),
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "## External SCUFF provenance",
            "",
            "Gmsh v2.2 and .scuffgeo exports are recorded in the JSON report with "
            "SHA256 digests and triangle counts. PATH availability does not imply "
            "SCUFF execution. SCUFF's Gold material must be explicitly matched to "
            "MaterialModel before interpreting an external calculation as verification.",
        ]
    )
    (output / f"{CAMPAIGN}_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def make_figure(
    rows: list[dict[str, Any]],
    convergence: list[dict[str, Any]],
    directory: Path,
    provenance: Mapping[str, Any],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "ps.fonttype": 42})
    figure, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    colors = dict(zip(DESIGN_NAMES, ("#0072B2", "#D55E00", "#009E73")))
    styles = {"vector_dyadic": ("o", "-"), "scalar_yukawa": ("s", "--")}
    for axis, state, title in (
        (axes[0, 0], "Aperture", "A  Repulsive-state mesh/frequency convergence"),
        (axes[0, 1], "Landing Pad", "B  Attractive-state mesh/frequency convergence"),
    ):
        for design in DESIGN_NAMES:
            group = sorted(
                [row for row in rows if row["design"] == design and row["state"] == state],
                key=lambda row: row["tier_index"],
            )
            if not group:
                continue
            for formulation, (marker, linestyle) in styles.items():
                axis.plot(
                    [row["panel_count"] for row in group],
                    [row["forces_pN"][formulation] for row in group],
                    marker=marker,
                    linestyle=linestyle,
                    color=colors[design],
                    label=f"{design}: {formulation}",
                )
            if state == "Landing Pad":
                axis.plot(
                    [row["panel_count"] for row in group],
                    [row["forces_pN"]["lifshitz_pfa"] for row in group],
                    color=colors[design],
                    linestyle=":",
                    label=f"{design}: PFA",
                )
        axis.set(title=title, xlabel="Full four-sector panel count", ylabel=r"$F_z$ (pN)")
        axis.axhline(0.0, color="0.6", linewidth=0.7)
        axis.grid(alpha=0.2)
        if axis.get_legend_handles_labels()[0]:
            axis.legend(fontsize=6)

    comparison = axes[1, 0]
    labels: list[str] = []
    positions: list[float] = []
    series: dict[str, list[float]] = {
        name: [] for name in (*FORMULATIONS, "lifshitz_pfa")
    }
    for design in DESIGN_NAMES:
        for state in ("Aperture", "Straddling", "Landing Pad"):
            group = [
                row for row in rows
                if row["design"] == design and row["state"] == state
            ]
            if not group:
                continue
            row = max(group, key=lambda item: item["tier_index"])
            positions.append(float(len(positions)))
            labels.append(f"{design}\n{state}, {row['theta_deg']:g}°")
            for formulation in series:
                series[formulation].append(row["forces_pN"][formulation])
    for index, (formulation, values) in enumerate(series.items()):
        comparison.plot(
            np.asarray(positions) + (index - 1) * 0.12,
            values,
            marker=("o", "s", "^")[index],
            linestyle="none",
            label=formulation,
        )
    comparison.set(
        title="C  Three solvers at highest completed resolution",
        ylabel=r"$F_z$ (pN)",
    )
    comparison.set_xticks(positions, labels, rotation=65, ha="right", fontsize=6)
    comparison.axhline(0.0, color="0.6", linewidth=0.7)
    comparison.grid(axis="y", alpha=0.2)
    comparison.legend(fontsize=7)

    error_axis = axes[1, 1]
    error_labels: list[str] = []
    for index, item in enumerate(convergence):
        error_labels.append(f"{item['design']}\n{item['theta_deg']:g}°")
        for offset, formulation in ((-0.12, "vector_dyadic"), (0.12, "scalar_yukawa")):
            values = item["comparisons"][formulation]
            refinement = values.get("High_to_Ultra_High", values.get("Standard_to_High"))
            residual = values["absolute_nonadditive_edge_fraction"]
            color = "#0072B2" if formulation == "vector_dyadic" else "#D55E00"
            if refinement is not None:
                error_axis.scatter(
                    index + offset,
                    refinement,
                    marker="o",
                    color=color,
                    label=f"{formulation}: refinement" if index == 0 else None,
                )
            if residual is not None:
                error_axis.scatter(
                    index + offset,
                    residual,
                    marker="x",
                    color=color,
                    label=f"{formulation}: |BEM−PFA|/|BEM|" if index == 0 else None,
                )
    error_axis.set(
        title="D  Refinement error and 3D/non-additive residual",
        ylabel="Dimensionless fraction",
    )
    error_axis.set_xticks(
        range(len(error_labels)), error_labels, rotation=65, ha="right", fontsize=6
    )
    error_axis.set_yscale("symlog", linthresh=1e-3)
    error_axis.grid(alpha=0.2)
    if error_axis.get_legend_handles_labels()[0]:
        error_axis.legend(fontsize=7)
    figure.suptitle("Stepped-elevation concentric Cantor clutch: three-solver verification")
    try:
        for extension in ("png", "pdf"):
            path = directory / f"fig_{CAMPAIGN}.{extension}"
            figure.savefig(path, dpi=220 if extension == "png" else 300)
            metrics_logger.save_plot_provenance(
                str(path),
                str(REPOSITORY_ROOT / "results" / "provenance_metrics.json"),
                [
                    "vector_dyadic_F_z_pN",
                    "scalar_yukawa_F_z_pN",
                    "lifshitz_pfa_F_z_pN",
                    "panel_count",
                ],
                solver_name=CAMPAIGN,
                solver_parameters=dict(provenance),
            )
    finally:
        plt.close(figure)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--figures-dir", type=Path, default=Path("figures"))
    parser.add_argument("--include-c10-ultra", action="store_true")
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    return args


def main() -> int:
    args = parse_arguments()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.device != "auto":
        device = args.device if args.device != "cuda" or torch.cuda.is_available() else "cpu"
    micro = 0 < args.max_steps <= 5
    if micro:
        torch.set_num_threads(1)

    if int(SYMMETRY_ORDER) != 4 or not math.isclose(float(SECTOR_DEG), 90.0):
        raise ValueError("This verification requires exact four-sector C4 geometry")
    if not math.isclose(float(Z_TIP_FIXED_UM), -0.100, abs_tol=1e-12):
        raise ValueError("Imported fixed tip elevation differs from -0.100 um")
    if not math.isclose(float(Z_PAD_TOP_UM), -0.115, abs_tol=1e-12):
        raise ValueError("Imported landing-pad elevation differs from -0.115 um")
    if not math.isclose(
        float(Z_TIP_FIXED_UM) - float(Z_PAD_TOP_UM), GAP_UM, abs_tol=1e-12
    ):
        raise ValueError("Imported geometry does not have the required 15 nm gap")

    output: Path = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / f"{CAMPAIGN}_report.json"
    material = gold_material()
    provenance: dict[str, Any] = dict(
        campaign=CAMPAIGN,
        solver_name=CAMPAIGN,
        device=device,
        micro_probe=micro,
        max_steps=args.max_steps,
        max_memory_gib=8.0,
        symmetry_order=int(SYMMETRY_ORDER),
        sector_deg=float(SECTOR_DEG),
        z_tip_um=float(Z_TIP_FIXED_UM),
        z_rotor_top_um=float(Z_ROTOR_TOP_UM),
        z_pad_top_um=float(Z_PAD_TOP_UM),
        gap_um=GAP_UM,
        material_class=f"{type(material).__module__}.{type(material).__qualname__}",
        material=plain(material),
        lifshitz_quadrature=dict(
            imaginary_frequency_nodes=128,
            transverse_wavevector_nodes=96,
            temperature_K=0.0,
            material_argument_unit="um^-1",
        ),
        scuff_executable=shutil.which("scuff-cas3d"),
        python=sys.version,
        numpy_version=np.__version__,
        torch_version=torch.__version__,
        geometry_source_sha256=sha256(
            Path(inspect.getfile(build_rotational_stepped_clutch_mesh))
        ),
        bem_source_sha256=sha256(Path(inspect.getfile(bem.run_bem_casimir_solver))),
    )
    rows: list[dict[str, Any]] = []
    report: dict[str, Any] = dict(
        model=CAMPAIGN,
        dataset=CAMPAIGN,
        status="running",
        executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        provenance=provenance,
        tasks=rows,
        convergence=[],
        hybrid_multiscale_comparison=None,
        force_convention="positive repulsive, negative attractive",
        pfa_scope="polar tooth/landing-pad overlap only; no aperture or bridge force",
        panel_count_scope="full four-sector geometry",
        scuff_scope="export only, not executed; external Gold equivalence unverified",
    )
    atomic_json(report_path, report)
    campaign_start = time.perf_counter()
    try:
        hybrid_comparison = load_hybrid_comparison()
        report["hybrid_multiscale_comparison"] = hybrid_comparison
        metrics_logger.set_solver_provenance(CAMPAIGN, provenance)

        pressure_start = time.perf_counter()
        pressure = lifshitz_pressure(material)
        provenance["lifshitz_pressure_Pa"] = pressure
        provenance["lifshitz_pressure_runtime_s"] = time.perf_counter() - pressure_start
        atomic_json(report_path, report)

        tasks: list[tuple[str, float, str, int, dict[str, Any]]] = []
        for design in DESIGN_NAMES:
            angles = (3.0, 21.0, 48.0) if design == DESIGN_NAMES[2] else (6.0, 18.0, 48.0)
            limit = 3 if design != DESIGN_NAMES[2] or args.include_c10_ultra else 2
            for tier_index, template in enumerate(TIERS[:limit]):
                for theta, state in zip(angles, ("Aperture", "Straddling", "Landing Pad")):
                    tier = dict(template)
                    if micro:
                        tier["n_xi"] = min(4, args.max_steps)
                    tasks.append((design, theta, state, tier_index, tier))
        if micro:
            tasks = tasks[:1]

        for step, (name, theta, state, tier_index, tier) in enumerate(tasks):
            task_id = f"{name}_{tier['tier']}_theta_{theta:05.1f}".replace(".", "p")
            print(f"[{step + 1}/{len(tasks)}] {task_id} device={device}", flush=True)
            metrics_logger.log_step(
                task_id,
                {
                    "design": name,
                    "theta_deg": theta,
                    "state": state,
                    "tier": tier["tier"],
                },
            )

            spec = get_design(name)
            certificate = collision_certificate(spec)
            if not certificate["collision_free_for_all_angles"]:
                raise ValueError(f"Geometry collision certificate failed: {task_id}")
            landing_fraction = finite_float(
                angular_state(spec, theta)["landing_pad_fraction"],
                "landing_pad_fraction",
            )
            if state == "Aperture" and landing_fraction != 0.0:
                raise ValueError(f"Aperture task overlaps a landing pad: {task_id}")

            mesh_start = time.perf_counter()
            mesh = build_rotational_stepped_clutch_mesh(
                spec,
                theta,
                tier["n_r"],
                tier["n_phi_tooth"],
                tier["n_phi_bridge"],
                tier["n_z"],
            )
            mesh_runtime = time.perf_counter() - mesh_start

            pfa_start = time.perf_counter()
            overlap = polar_overlap_um2(spec, mesh, theta)
            pfa_force = pressure * overlap  # Pa * um² = pN.
            pfa_runtime = time.perf_counter() - pfa_start
            forces = {"lifshitz_pfa": finite_float(pfa_force, "PFA force")}
            runtimes = {"lifshitz_pfa": pfa_runtime}
            panel_count: int | None = None
            for formulation in FORMULATIONS:
                start = time.perf_counter()
                result = bem.run_bem_casimir_solver(
                    mesh.parameters,
                    n_r=tier["n_r"],
                    n_phi_tooth=tier["n_phi_tooth"],
                    n_phi_bridge=tier["n_phi_bridge"],
                    n_z=tier["n_z"],
                    n_xi=tier["n_xi"],
                    max_steps=args.max_steps,
                    device=device,
                    max_memory_gib=8.0,
                    task_id=f"{task_id}_{formulation}",
                    mesh=mesh,
                    record_metrics=True,
                    formulation=formulation,
                )
                runtimes[formulation] = time.perf_counter() - start
                forces[formulation] = finite_float(result["f_net_pN"], "f_net_pN")
                count_value = finite_float(result["n_panels_total"], "n_panels_total")
                if count_value <= 0 or int(count_value) != count_value:
                    raise ValueError(f"Invalid native panel count: {count_value}")
                count = int(count_value)
                if panel_count is not None and panel_count != count:
                    raise ValueError("Vector and scalar native panel counts disagree")
                panel_count = count

            if panel_count is None:
                raise RuntimeError("No BEM formulation was executed")
            vector_dofs = 2 * panel_count
            scalar_dofs = panel_count
            scuff = export_scuff(mesh, output / CAMPAIGN / "scuff_meshes", task_id)
            signs = {key: sign(value) for key, value in forces.items()}
            row = dict(
                model=CAMPAIGN,
                dataset=CAMPAIGN,
                status="completed",
                executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                task_id=task_id,
                design=name,
                theta_deg=theta,
                state=state,
                tier=tier["tier"],
                tier_index=tier_index,
                resolution=tier,
                forces_pN=forces,
                panel_count=panel_count,
                vector_dofs=vector_dofs,
                scalar_dofs=scalar_dofs,
                runtime_s=runtimes,
                mesh_runtime_s=mesh_runtime,
                polar_overlap_um2=overlap,
                landing_pad_fraction=landing_fraction,
                collision_certificate=plain(certificate),
                bem_sign_agreement=signs["vector_dyadic"] == signs["scalar_yukawa"],
                all_three_sign_agreement=len(set(signs.values())) == 1,
                expected_bem_sign=(
                    1 if state == "Aperture" else -1 if state == "Landing Pad" else None
                ),
                scuff=scuff,
            )
            rows.append(row)
            report["convergence"] = summarize(rows)
            atomic_json(report_path, report)

            for formulation, value in forces.items():
                metrics_logger.log_metric(
                    f"{task_id}_{formulation}_F_z_pN", value, step_id=task_id
                )
                metrics_logger.log_metric(
                    f"{task_id}_{formulation}_runtime_s",
                    runtimes[formulation],
                    step_id=task_id,
                )
            for metric_name, metric_value in (
                ("panel_count", panel_count),
                ("vector_dofs", vector_dofs),
                ("scalar_dofs", scalar_dofs),
                ("polar_overlap_um2", overlap),
                ("bem_sign_agreement", int(row["bem_sign_agreement"])),
                ("all_three_sign_agreement", int(row["all_three_sign_agreement"])),
            ):
                metrics_logger.log_metric(
                    f"{task_id}_{metric_name}", metric_value, step_id=task_id
                )

        convergence = summarize(rows)
        report["convergence"] = convergence
        write_tables(rows, convergence, output, hybrid_comparison)
        make_figure(rows, convergence, args.figures_dir, provenance)
        metrics_logger.export_macros(
            output_path=str(output / f"{CAMPAIGN}_macros.tex")
        )
        metrics_logger.export_macros()
        report["status"] = "completed"
        report["runtime_s"] = time.perf_counter() - campaign_start
        atomic_json(report_path, report)
        print(f"Completed {len(rows)} tasks. Report: {report_path}", flush=True)
        return 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        report["runtime_s"] = time.perf_counter() - campaign_start
        atomic_json(report_path, report)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
