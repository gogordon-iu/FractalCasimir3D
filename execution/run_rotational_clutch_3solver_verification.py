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
from execution.clutch_geometry_redesign import (
    DEFAULT_ENGAGED_GAP_UM,
    DEFAULT_NUM_SECTORS,
    DEFAULT_SECTOR_DEG,
    DEFAULT_Z_PAD_TOP_UM,
    DEFAULT_Z_TIP_ROTATIONAL_UM,
    ROTATIONAL_3SOLVER_N2_ANGLES_DEG,
    ROTATIONAL_3STATE_ANGLES_DEG,
)
from execution.materials_database_dispersive import (
    C_LIGHT_SI_M_S,
    HBAR_SI_J_S,
)
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

HBAR = HBAR_SI_J_S
C_LIGHT = C_LIGHT_SI_M_S
GAP_UM = float(Z_TIP_FIXED_UM) - float(Z_PAD_TOP_UM)
CAMPAIGN = "rotational_clutch_3solver_verification"
DESIGN_NAMES = tuple(str(spec["name"]) for spec in DEFAULT_DESIGNS)
TIERS: tuple[dict[str, Any], ...] = tuple(
    dict(
        tier=tier.name,
        n_r=tier.n_r,
        n_phi_tooth=tier.n_phi_tooth,
        n_phi_bridge=tier.n_phi_bridge,
        n_z=tier.n_z,
        n_xi=tier.n_xi,
    )
    for tier in bem.BEM_RESOLUTION_LADDER
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
    import matplotlib.gridspec as gridspec
    from matplotlib.ticker import FixedLocator, FuncFormatter

    directory.mkdir(parents=True, exist_ok=True)
    provenance_path = REPOSITORY_ROOT / "results" / "provenance_metrics.json"
    if not provenance_path.is_file():
        raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Missing {provenance_path}")
    prov_payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    prov_metrics = prov_payload.get("metrics", {})
    if not isinstance(prov_metrics, Mapping) or not prov_metrics:
        raise RuntimeError("[ERROR: RUN_DATA_MISSING] Empty provenance_metrics.json")

    def pm_val(key: str) -> float:
        entry = prov_metrics.get(key)
        if not isinstance(entry, Mapping) or "value" not in entry:
            raise KeyError(f"[ERROR: RUN_DATA_MISSING] Missing metric {key!r} in provenance_metrics.json")
        return finite_float(entry["value"], key)

    row_lookup: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["design"]),
            str(row["tier"]),
            int(round(float(row["theta_deg"]))),
        )
        row_lookup[key] = row

    def row_force(design: str, tier: str, theta_deg: int, formulation: str) -> float:
        row = row_lookup.get((design, tier, theta_deg))
        if row is not None and formulation in row.get("forces_pN", {}):
            return finite_float(row["forces_pN"][formulation], f"{design}_{tier}_{theta_deg}_{formulation}")
        metric_key = f"{design}_{tier}_theta_{theta_deg:03d}p0_{formulation}_F_z_pN"
        return pm_val(metric_key)

    def row_panels(design: str, tier: str, theta_deg: int) -> int:
        row = row_lookup.get((design, tier, theta_deg))
        if row is not None and "panel_count" in row:
            return int(row["panel_count"])
        metric_key = f"{design}_{tier}_theta_{theta_deg:03d}p0_panel_count"
        return int(round(pm_val(metric_key)))

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 6.0,
            "axes.titlesize": 6.6,
            "axes.labelsize": 6.5,
            "xtick.labelsize": 5.6,
            "ytick.labelsize": 5.6,
            "legend.fontsize": 5.3,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    # 180 mm x 120 mm = 7.08 in x 4.72 in at 600 DPI
    figure = plt.figure(figsize=(7.08, 4.72), dpi=600, facecolor="#FFFFFF")
    outer_gs = gridspec.GridSpec(
        2,
        2,
        figure=figure,
        left=0.078,
        right=0.985,
        top=0.935,
        bottom=0.115,
        hspace=0.36,
        wspace=0.25,
    )

    def style_ax(ax: Any) -> None:
        ax.set_facecolor("#FFFFFF")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#334155")
            ax.spines[side].set_linewidth(0.65)
        ax.tick_params(colors="#1E293B", width=0.6, length=2.6, pad=1.8)
        ax.grid(True, color="#E2E8F0", linewidth=0.45, alpha=0.85)
        ax.set_axisbelow(True)

    # =========================================================================
    # Panel a (Top-Left): Repulsive-state BEM mesh refinement (\theta = 3°–6°)
    # =========================================================================
    gs_a = gridspec.GridSpecFromSubplotSpec(
        2, 1, subplot_spec=outer_gs[0, 0], height_ratios=[1.65, 1.0], hspace=0.40
    )
    ax_a = figure.add_subplot(gs_a[0])
    ax_a_ins = figure.add_subplot(gs_a[1])
    style_ax(ax_a)
    style_ax(ax_a_ins)

    n2_panels = [
        row_panels("Rot_C4_TightSlot_N2", "Standard", 6),
        row_panels("Rot_C4_TightSlot_N2", "High", 6),
        row_panels("Rot_C4_TightSlot_N2", "Ultra_High", 6),
    ]
    n3_panels = [
        row_panels("Rot_C10_Fractal_N3", "Standard", 3),
        row_panels("Rot_C10_Fractal_N3", "High", 3),
    ]
    cantor_n2_vec = [
        pm_val("cantor_n2_hybridrz_bem_std_f_z_pn"),
        pm_val("cantor_n2_hybridrz_bem_high_f_z_pn"),
        pm_val("cantor_n2_hybridrz_bem_ultra_f_z_pn"),
    ]
    cantor_n2_r5 = [
        pm_val("cantor_n2_hybridrz_bem_r5nm_std_f_z_pn"),
        pm_val("cantor_n2_hybridrz_bem_r5nm_high_f_z_pn"),
        pm_val("cantor_n2_hybridrz_bem_r5nm_ultra_f_z_pn"),
    ]
    amp_ratio_sharp = [
        pm_val("cantor_n2_vs_uniform_ratio_sharp_std"),
        pm_val("cantor_n2_vs_uniform_ratio_sharp_high"),
        pm_val("cantor_n2_vs_uniform_ratio_sharp_ultra"),
    ]
    amp_ratio_r5 = [
        pm_val("cantor_n2_vs_uniform_ratio_r5nm_std"),
        pm_val("cantor_n2_vs_uniform_ratio_r5nm_high"),
        pm_val("cantor_n2_vs_uniform_ratio_r5nm_ultra"),
    ]
    tight_n2_vec = [
        row_force("Rot_C4_TightSlot_N2", "Standard", 6, "vector_dyadic"),
        row_force("Rot_C4_TightSlot_N2", "High", 6, "vector_dyadic"),
        row_force("Rot_C4_TightSlot_N2", "Ultra_High", 6, "vector_dyadic"),
    ]
    compact_n2_vec = [
        row_force("Rot_C8_Compact_N2", "Standard", 6, "vector_dyadic"),
        row_force("Rot_C8_Compact_N2", "High", 6, "vector_dyadic"),
        row_force("Rot_C8_Compact_N2", "Ultra_High", 6, "vector_dyadic"),
    ]
    cantor_n3_vec = [
        row_force("Rot_C10_Fractal_N3", "Standard", 3, "vector_dyadic"),
        row_force("Rot_C10_Fractal_N3", "High", 3, "vector_dyadic"),
    ]
    cantor_n3_sca = [
        row_force("Rot_C10_Fractal_N3", "Standard", 3, "scalar_yukawa"),
        row_force("Rot_C10_Fractal_N3", "High", 3, "scalar_yukawa"),
    ]
    f3_111_panels = 6784
    f3_111_vec = pm_val("n3_uni3d_f111_unified_fz_pn")
    f2_110_vec = pm_val("n3_uni3d_f110_rtheta_planar_fz_pn")
    c6_uni12_vec = pm_val("n3_uni3d_ctrl_uni12_fz_pn")
    f3_vs_uni12_ratio = f3_111_vec / c6_uni12_vec
    f3_vs_uni111_ratio = pm_val("n3_uni3d_ratio_f111_vs_uni111")

    ax_a.plot(
        [f3_111_panels], [f3_111_vec], "*", color="#D62728", ms=5.8,
        markeredgecolor="#0F172A", markeredgewidth=0.45,
        label=r"3D Cantor $N=3$ ($F_{3\_111}$, $3^\circ$)", zorder=7,
    )
    ax_a.plot(
        [f3_111_panels], [f2_110_vec], "h", color="#E377C2", ms=4.5,
        markeredgecolor="#0F172A", markeredgewidth=0.4,
        label=r"2D Cantor $N=3$ ($F_{2r\theta}$, $3^\circ$)", zorder=6,
    )
    ax_a.plot(
        n2_panels, cantor_n2_vec, "-o", color="#6A3D9A", lw=1.2, ms=3.4,
        label=r"Cantor $N=2$ sharp ($r_{\mathrm{edge}}=0$)", zorder=5,
    )
    ax_a.plot(
        n2_panels, cantor_n2_r5, "-P", color="#009E73", lw=1.3, ms=3.8,
        label=r"Cantor $N=2$ rounded ($r_{\mathrm{edge}}=5$ nm)", zorder=6,
    )
    ax_a.plot(
        n2_panels, tight_n2_vec, "-^", color="#0072B2", lw=1.05, ms=3.2,
        label=r"Tight-slot $N=2$, $6^\circ$ (BEM)", zorder=4,
    )
    ax_a.plot(
        n2_panels, compact_n2_vec, "-s", color="#E69F00", lw=1.05, ms=3.2,
        label=r"Compact $N=2$, $6^\circ$ (BEM)", zorder=4,
    )
    ax_a.plot(
        n3_panels, cantor_n3_vec, "-D", color="#D55E00", lw=1.2, ms=3.4,
        label=r"1D Cantor $N=3$, $3^\circ$ (BEM)", zorder=5,
    )
    ax_a.plot(
        n3_panels, cantor_n3_sca, "--D", color="#D55E00", lw=0.95, ms=3.2,
        markerfacecolor="#FFFFFF", markeredgewidth=0.85,
        label=r"1D Cantor $N=3$, $3^\circ$ (Scalar)", zorder=4,
    )

    ax_a.annotate(
        f"+{f3_111_vec:.2f} pN ($F_{{3\\_111}}$)",
        xy=(f3_111_panels, f3_111_vec),
        xytext=(-5, 1.0), textcoords="offset points",
        fontsize=4.4, fontweight="bold", color="#D62728", ha="right", va="center",
    )
    ax_a.annotate(
        f"+{f2_110_vec:.2f} pN ($F_{{2r\\theta}}$)",
        xy=(f3_111_panels, f2_110_vec),
        xytext=(-5, 2.0), textcoords="offset points",
        fontsize=4.2, fontweight="bold", color="#BE185D", ha="right", va="bottom",
    )
    ax_a.annotate(
        f"+{cantor_n3_sca[-1]:.2f} pN",
        xy=(n3_panels[-1], cantor_n3_sca[-1]),
        xytext=(-14, 1.5), textcoords="offset points",
        fontsize=4.2, fontweight="bold", color="#D55E00", ha="right", va="bottom",
    )
    ax_a.annotate(
        f"+{cantor_n2_vec[-1]:.2f} pN",
        xy=(n2_panels[-1], cantor_n2_vec[-1]),
        xytext=(-4, 3.0), textcoords="offset points",
        fontsize=4.2, fontweight="bold", color="#6A3D9A", ha="right", va="bottom",
    )
    ax_a.annotate(
        f"+{cantor_n2_r5[-1]:.2f} pN ($r_{{\\mathrm{{edge}}}}=5$ nm)",
        xy=(n2_panels[-1], cantor_n2_r5[-1]),
        xytext=(3, 0), textcoords="offset points",
        fontsize=4.0, fontweight="bold", color="#047857", ha="left", va="center",
    )

    ax_a.set_title("Repulsive BEM refinement & corner rounding ($\\theta = 3^\\circ$–$6^\\circ$)", fontweight="bold", loc="left", pad=3)
    ax_a.set_ylabel("Force $F_z$ (pN)")
    ax_a.set_xlim(1100, 7450)
    ax_a.set_ylim(-0.6, 20.8)
    ax_a.set_xticks([1504, 3120, 4500, 6016, 6784])
    ax_a.set_xticklabels(["1,504", "3,120", "4,500", "6,016", "6,784"])
    ax_a.legend(loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94, fontsize=3.85, ncol=2, handlelength=1.2, columnspacing=0.45, labelspacing=0.12, borderpad=0.2)

    # Bottom sub-panel of Panel a: amplification ratio F_z^Cantor / F_z^Uniform convergence
    ax_a_ins.plot(n2_panels, amp_ratio_sharp, "--o", color="#6A3D9A", lw=1.1, ms=3.3, label=r"$N=2$ sharp ($r_{\mathrm{edge}}=0$: $1.39\times \to 1.60\times$)")
    ax_a_ins.plot(n2_panels, amp_ratio_r5, "-P", color="#009E73", lw=1.25, ms=3.8, label=r"$N=2$ rounded ($r_{\mathrm{edge}}=5$ nm: $1.37\times \to 1.42\times$)")
    ax_a_ins.plot([f3_111_panels], [f3_vs_uni12_ratio], "*", color="#D62728", ms=5.5, markeredgecolor="#0F172A", markeredgewidth=0.4, label=rf"3D $F_{{3\_111}}$ vs. 12T Unif. ($1.33\times$; vs. 7T $5.91\times$)")
    ax_a_ins.set_ylabel(r"Gain $F_z^{\mathrm{Cantor}}/F_z^{\mathrm{Unif}}$")
    ax_a_ins.set_xlabel("Four-sector panels $N_{\\mathrm{panels}}$ (near-gap size $h_{\\mathrm{gap}}$)", labelpad=1.2)
    ax_a_ins.set_xlim(1100, 7450)
    ax_a_ins.set_ylim(1.20, 1.74)
    ax_a_ins.set_xticks([1504, 3120, 4500, 6016, 6784])
    ax_a_ins.set_xticklabels(["1,504\n(27 nm)", "3,120\n(18 nm)", "4,500", "6,016\n(13.5 nm)", "6,784\n(3D N=3)"], fontsize=4.6)
    ax_a_ins.set_yticks([1.30, 1.45, 1.60])
    ax_a_ins.legend(loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94, fontsize=3.95, handlelength=1.2, labelspacing=0.12, borderpad=0.18)

    # =========================================================================
    # Panel b (Top-Right): Attractive-state continuum convergence (h = N_{panels}^{-1/2} -> 0)
    # =========================================================================
    ax_b = figure.add_subplot(outer_gs[0, 1])
    style_ax(ax_b)

    h_n2 = [1.0 / math.sqrt(float(p)) for p in n2_panels]
    c8_18_vec = [
        row_force("Rot_C8_Compact_N2", "Standard", 18, "vector_dyadic"),
        row_force("Rot_C8_Compact_N2", "High", 18, "vector_dyadic"),
        row_force("Rot_C8_Compact_N2", "Ultra_High", 18, "vector_dyadic"),
    ]
    c8_18_rich = pm_val("rot_c8_compact_n2_bem_theta18_richardson_f_z_pn")
    c8_18_fdtd = pm_val("rot_c8_compact_n2_meep_theta18_f_z_pn")
    c8_18_sca = row_force("Rot_C8_Compact_N2", "High", 18, "scalar_yukawa")

    c4_18_vec = [
        row_force("Rot_C4_TightSlot_N2", "Standard", 18, "vector_dyadic"),
        row_force("Rot_C4_TightSlot_N2", "High", 18, "vector_dyadic"),
        row_force("Rot_C4_TightSlot_N2", "Ultra_High", 18, "vector_dyadic"),
    ]
    c4_18_rich = pm_val("rot_c4_tightslot_n2_bem_theta18_richardson_f_z_pn")
    c4_18_fdtd = pm_val("rot_c4_tightslot_n2_meep_theta18_f_z_pn")
    c4_18_sca = row_force("Rot_C4_TightSlot_N2", "High", 18, "scalar_yukawa")

    c8_48_vec = [
        row_force("Rot_C8_Compact_N2", "Standard", 48, "vector_dyadic"),
        row_force("Rot_C8_Compact_N2", "High", 48, "vector_dyadic"),
        row_force("Rot_C8_Compact_N2", "Ultra_High", 48, "vector_dyadic"),
    ]
    c8_48_cont = pm_val("rot_c8_compact_n2_bem_theta48_continuum_f_z_pn")
    c8_48_fdtd = pm_val("rot_c8_compact_n2_meep_theta48_f_z_pn")
    c8_48_sca = row_force("Rot_C8_Compact_N2", "High", 48, "scalar_yukawa")

    c4_48_vec = [
        row_force("Rot_C4_TightSlot_N2", "Standard", 48, "vector_dyadic"),
        row_force("Rot_C4_TightSlot_N2", "High", 48, "vector_dyadic"),
        row_force("Rot_C4_TightSlot_N2", "Ultra_High", 48, "vector_dyadic"),
    ]
    c4_48_cont = pm_val("rot_c4_tightslot_n2_bem_theta48_continuum_f_z_pn")
    c4_48_rich = pm_val("rot_c4_tightslot_n2_bem_theta48_richardson_f_z_pn")
    c4_48_fdtd = pm_val("rot_c4_tightslot_n2_meep_theta48_f_z_pn")
    c4_48_sca = row_force("Rot_C4_TightSlot_N2", "High", 48, "scalar_yukawa")

    ax_b.axvline(0.0, color="#64748B", lw=0.75, ls=":", zorder=2)
    ax_b.axhline(0.0, color="#475569", lw=0.65, ls="--", zorder=2)

    # Plot BEM trajectories (h_n2) and extrapolation lines to h = 0
    series_b = [
        (r"Compact $N=2$ ($18^\circ$)", c8_18_vec, c8_18_rich, c8_18_fdtd, c8_18_sca, "#009E73", "o"),
        (r"Tight-slot $N=2$ ($18^\circ$)", c4_18_vec, c4_18_rich, c4_18_fdtd, c4_18_sca, "#56B4E9", "^"),
        (r"Compact $N=2$ ($48^\circ$)", c8_48_vec, c8_48_cont, c8_48_fdtd, c8_48_sca, "#E69F00", "s"),
        (r"Tight-slot $N=2$ ($48^\circ$)", c4_48_vec, c4_48_cont, c4_48_fdtd, c4_48_sca, "#0072B2", "D"),
    ]
    for label_b, vec_vals, extrap_val, fdtd_val, sca_val, col_b, mk_b in series_b:
        ax_b.plot(
            h_n2, vec_vals, linestyle="-", marker=mk_b, color=col_b, lw=1.2, ms=3.5,
            label=f"{label_b} BEM", zorder=4,
        )
        ax_b.plot(
            [h_n2[-1], 0.0], [vec_vals[-1], extrap_val],
            linestyle="--", color=col_b, lw=0.95, alpha=0.85, zorder=3,
        )
        ax_b.plot(
            [0.0], [extrap_val], marker=mk_b, color=col_b, ms=4.2,
            markerfacecolor="#FFFFFF", markeredgewidth=1.1, zorder=5,
        )
        ax_b.plot(
            [-0.00055], [fdtd_val], marker="*", color=col_b, ms=5.2,
            markeredgecolor="#0F172A", markeredgewidth=0.35, zorder=6,
        )
        ax_b.plot(
            [0.00055], [sca_val], marker="P", color=col_b, ms=4.0,
            markeredgecolor="#0F172A", markeredgewidth=0.35, zorder=6,
        )

    # Also plot Richardson intercept (-65.33 pN) for Tight-slot N=2 (48 deg)
    ax_b.plot(
        [h_n2[-1], 0.0], [c4_48_vec[-1], c4_48_rich],
        linestyle=":", color="#0072B2", lw=0.95, alpha=0.85, zorder=3,
    )
    ax_b.plot(
        [0.0], [c4_48_rich], marker="D", color="#0072B2", ms=4.2,
        markerfacecolor="#BFDBFE", markeredgewidth=1.0, zorder=5,
    )

    # Dummy legend entries for h=0 markers
    ax_b.plot([], [], marker="o", ls="--", color="#334155", markerfacecolor="#FFFFFF", ms=3.8, label="BEM continuum ($h\\to 0$)")
    ax_b.plot([], [], marker="*", ls="none", color="#334155", ms=5.0, label="4-pass 3D FDTD ($h=0$)")
    ax_b.plot([], [], marker="P", ls="none", color="#334155", ms=4.0, label="Scalar-Yukawa (sign bound)")

    ax_b.annotate(
        f"Tight-slot $48^\\circ$: Cont. {c4_48_cont:.1f}, FDTD {c4_48_fdtd:.1f}, Rich. {c4_48_rich:.1f} pN",
        xy=(0.0, c4_48_fdtd), xytext=(0.0022, -49.5),
        fontsize=4.55, color="#0072B2", fontweight="bold", ha="left", va="center",
        bbox=dict(boxstyle="round,pad=0.15", facecolor="#EFF6FF", edgecolor="#93C5FD", lw=0.5),
        arrowprops=dict(arrowstyle="->", color="#0072B2", lw=0.55, mutation_scale=5),
    )
    ax_b.annotate(
        f"Compact $48^\\circ$:\nCont. {c8_48_cont:.1f} | FDTD {c8_48_fdtd:.1f} pN",
        xy=(0.0, c8_48_cont), xytext=(0.0020, -25.5),
        fontsize=4.5, color="#B45309", fontweight="bold", ha="left", va="center",
        bbox=dict(boxstyle="round,pad=0.14", facecolor="#FFFBEB", edgecolor="#FCD34D", lw=0.5),
        arrowprops=dict(arrowstyle="->", color="#B45309", lw=0.55, mutation_scale=5),
    )

    ax_b.set_title("Attractive-state continuum convergence ($h = N_{\\mathrm{panels}}^{-1/2} \\to 0$)", fontweight="bold", loc="left", pad=4)
    ax_b.set_xlabel("Dimensionless panel size $h = N_{\\mathrm{panels}}^{-1/2}$")
    ax_b.set_ylabel("Attractive axial force $F_z$ (pN)")
    ax_b.set_xlim(-0.0022, 0.0275)
    ax_b.set_ylim(-70.0, 2.0)
    ax_b.set_xticks([0.0, round(h_n2[2], 4), round(h_n2[1], 4), round(h_n2[0], 4)])
    ax_b.set_xticklabels(["0\n(Cont.)", "0.0129\n(Ultra)", "0.0179\n(High)", "0.0258\n(Std)"])
    ax_b.legend(loc="lower right", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94, fontsize=4.55, ncol=2, handlelength=1.5, columnspacing=0.6, labelspacing=0.2, borderpad=0.28)

    # =========================================================================
    # Panel c (Bottom-Left): Cross-solver comparison vs. 1D Lifshitz–PFA (symlog scale)
    # =========================================================================
    ax_c = figure.add_subplot(outer_gs[1, 0])
    style_ax(ax_c)

    # 14 state points including 3D Cantor F3_111
    pfa_c4_6 = row_force("Rot_C4_TightSlot_N2", "High", 6, "lifshitz_pfa")
    pfa_c4_48 = row_force("Rot_C4_TightSlot_N2", "High", 48, "lifshitz_pfa")
    pfa_c8_6 = row_force("Rot_C8_Compact_N2", "High", 6, "lifshitz_pfa")
    pfa_c10_3 = row_force("Rot_C10_Fractal_N3", "High", 3, "lifshitz_pfa")
    pfa_c10_21 = row_force("Rot_C10_Fractal_N3", "High", 21, "lifshitz_pfa")
    pfa_c10_48 = row_force("Rot_C10_Fractal_N3", "High", 48, "lifshitz_pfa")
    f3_3_vec = pm_val("n3_uni3d_f111_unified_fz_pn")
    f3_21_vec = pm_val("n3_uni3d_f111_unified_theta21_fz_pn")
    f3_48_vec = pm_val("n3_uni3d_f111_unified_theta48_fz_pn")
    a_ratio_f3 = pm_val("n3_uni3d_f111_unified_area_um2") / 0.31038935417467184
    states_c = [
        ("Cantor $N=2$\n$(r,z),\\ 3^\\circ$", pm_val("cantor_n2_hybridrz_bem_high_f_z_pn"), pm_val("cantor_n2_hybridrz_bem_ultra_f_z_pn"), pm_val("cantor_n2_hybridrz_bem_scalar_std_theta3_f_z_pn"), pm_val("cantor_n2_hybridrz_meep_r50_f_z_pn"), pfa_c4_6),
        ("Cantor $N=2$\n$(r,z),\\ 48^\\circ$", pm_val("cantor_n2_hybridrz_bem_high_theta48_f_z_pn"), pm_val("cantor_n2_hybridrz_bem_ultra_theta48_f_z_pn"), pm_val("cantor_n2_hybridrz_bem_scalar_std_theta48_f_z_pn"), pm_val("cantor_n2_hybridrz_meep_theta48_f_z_pn"), pfa_c4_48),
        ("Tight-slot\n$N=2,\\ 6^\\circ$", row_force("Rot_C4_TightSlot_N2", "High", 6, "vector_dyadic"), row_force("Rot_C4_TightSlot_N2", "Ultra_High", 6, "vector_dyadic"), row_force("Rot_C4_TightSlot_N2", "High", 6, "scalar_yukawa"), pm_val("rot_c4_tightslot_n2_meep_theta6_f_z_pn"), pfa_c4_6),
        ("Tight-slot\n$N=2,\\ 18^\\circ$", c4_18_rich, row_force("Rot_C4_TightSlot_N2", "Ultra_High", 18, "vector_dyadic"), c4_18_sca, c4_18_fdtd, row_force("Rot_C4_TightSlot_N2", "High", 18, "lifshitz_pfa")),
        ("Tight-slot\n$N=2,\\ 48^\\circ$", c4_48_cont, row_force("Rot_C4_TightSlot_N2", "Ultra_High", 48, "vector_dyadic"), c4_48_sca, c4_48_fdtd, pfa_c4_48),
        ("Compact\n$N=2,\\ 6^\\circ$", row_force("Rot_C8_Compact_N2", "High", 6, "vector_dyadic"), row_force("Rot_C8_Compact_N2", "Ultra_High", 6, "vector_dyadic"), row_force("Rot_C8_Compact_N2", "High", 6, "scalar_yukawa"), pm_val("rot_c8_compact_n2_meep_theta6_f_z_pn"), pfa_c8_6),
        ("Compact\n$N=2,\\ 18^\\circ$", c8_18_rich, row_force("Rot_C8_Compact_N2", "Ultra_High", 18, "vector_dyadic"), c8_18_sca, c8_18_fdtd, row_force("Rot_C8_Compact_N2", "High", 18, "lifshitz_pfa")),
        ("Compact\n$N=2,\\ 48^\\circ$", c8_48_cont, row_force("Rot_C8_Compact_N2", "Ultra_High", 48, "vector_dyadic"), c8_48_sca, c8_48_fdtd, row_force("Rot_C8_Compact_N2", "High", 48, "lifshitz_pfa")),
        ("1D Cantor\n$N=3,\\ 3^\\circ$", row_force("Rot_C10_Fractal_N3", "High", 3, "vector_dyadic"), row_force("Rot_C10_Fractal_N3", "Standard", 3, "vector_dyadic"), row_force("Rot_C10_Fractal_N3", "High", 3, "scalar_yukawa"), pm_val("rot_c10_fractal_n3_meep_theta3_f_z_pn"), pfa_c10_3),
        ("1D Cantor\n$N=3,\\ 21^\\circ$", row_force("Rot_C10_Fractal_N3", "High", 21, "vector_dyadic"), row_force("Rot_C10_Fractal_N3", "Standard", 21, "vector_dyadic"), row_force("Rot_C10_Fractal_N3", "High", 21, "scalar_yukawa"), pm_val("rot_c10_fractal_n3_meep_theta21_f_z_pn"), pfa_c10_21),
        ("1D Cantor\n$N=3,\\ 48^\\circ$", row_force("Rot_C10_Fractal_N3", "High", 48, "vector_dyadic"), row_force("Rot_C10_Fractal_N3", "Standard", 48, "vector_dyadic"), row_force("Rot_C10_Fractal_N3", "High", 48, "scalar_yukawa"), pm_val("rot_c10_fractal_n3_meep_theta48_f_z_pn"), pfa_c10_48),
        ("3D Cantor\n$F_3,\\ 3^\\circ$", f3_3_vec, None, np.nan, np.nan, pfa_c10_3),
        ("3D Cantor\n$F_3,\\ 21^\\circ$", f3_21_vec, None, np.nan, np.nan, pfa_c10_21 * a_ratio_f3),
        ("3D Cantor\n$F_3,\\ 48^\\circ$", f3_48_vec, None, np.nan, np.nan, pfa_c10_48 * a_ratio_f3),
    ]

    x_c = np.arange(len(states_c), dtype=float)
    vec_c = [item[1] for item in states_c]
    ult_c = [item[2] for item in states_c]
    sca_c = [item[3] for item in states_c]
    fdtd_c = [item[4] for item in states_c]
    pfa_c = [item[5] for item in states_c]

    bem_yerr = [
        min(abs(u - v), 0.45 * abs(v)) if u is not None else 0.12 * abs(v)
        for v, u in zip(vec_c, ult_c, strict=True)
    ]
    fdtd_yerr = [max(0.04, 0.12 * abs(f)) if not math.isnan(f) else 0.0 for f in fdtd_c]
    sca_yerr = [0.18 * abs(s) if not math.isnan(s) else 0.0 for s in sca_c]

    ax_c.set_yscale("symlog", linthresh=1.0, linscale=0.8)
    ax_c.set_ylim(-1400.0, 95.0)
    ax_c.axhspan(0.0, 95.0, color="#FEF2F2", alpha=0.45, zorder=0)
    ax_c.axhline(0.0, color="#334155", lw=0.7, ls="--", zorder=2)

    ax_c.errorbar(
        x_c - 0.18, vec_c, yerr=bem_yerr,
        fmt="o", color="#0072B2", ms=3.4, elinewidth=0.65, capsize=1.5, capthick=0.55,
        label="3D Vector-Dyadic BEM (High / Cont.)", zorder=5,
    )
    ax_c.errorbar(
        x_c - 0.06, sca_c, yerr=sca_yerr,
        fmt="s", color="#E69F00", ms=3.2, elinewidth=0.55, capsize=1.3, capthick=0.5,
        label="Scalar-Yukawa (scalar sign bound)", zorder=4,
    )
    ax_c.errorbar(
        x_c + 0.06, fdtd_c, yerr=fdtd_yerr,
        fmt="*", color="#009E73", ms=4.3, elinewidth=0.65, capsize=1.5, capthick=0.55,
        label="4-pass 3D FDTD ($R = 50$)", zorder=5,
    )
    ax_c.plot(
        x_c + 0.18, pfa_c, marker="^", ls="none", color="#D55E00", ms=3.3,
        label="1D Lifshitz–PFA", zorder=5,
    )

    ax_c.set_title("Cross-solver comparison vs. 1D Lifshitz–PFA (symlog scale)", fontweight="bold", loc="left", pad=4)
    ax_c.set_ylabel("Axial Casimir force $F_z$ (pN)")
    ax_c.set_xticks(x_c)
    ax_c.set_xticklabels([item[0] for item in states_c], rotation=38, ha="right", fontsize=4.15)
    yticks_c = [20.0, 5.0, 1.0, 0.0, -1.0, -10.0, -50.0, -250.0, -1000.0]
    ax_c.yaxis.set_major_locator(FixedLocator(yticks_c))
    ax_c.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}" if v > 0 else f"{v:.0f}"))
    ax_c.legend(loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.95, fontsize=4.55, ncol=2, handlelength=1.1, columnspacing=0.55, labelspacing=0.18, borderpad=0.25)

    # =========================================================================
    # Panel d (Bottom-Right): Frequency quadrature & fixed-standoff FDTD convergence
    # =========================================================================
    gs_d = gridspec.GridSpecFromSubplotSpec(
        2, 1, subplot_spec=outer_gs[1, 1], height_ratios=[1.0, 1.15], hspace=0.42
    )
    ax_d_top = figure.add_subplot(gs_d[0])
    ax_d_bot = figure.add_subplot(gs_d[1])
    style_ax(ax_d_top)
    style_ax(ax_d_bot)

    n_xi_orders = [16, 24, 32, 40, 64]
    n_xi_forces = [
        pm_val("bem_conv_std_nxi16_pec_fz_pn"),
        pm_val("bem_conv_std_nxi24_pec_fz_pn"),
        pm_val("bem_conv_std_nxi32_pec_fz_pn"),
        pm_val("bem_conv_std_nxi40_pec_fz_pn"),
        pm_val("bem_conv_std_nxi64_pec_fz_pn"),
    ]
    n_xi_drift = pm_val("bem_conv_nxi_drift_pct")

    ax_d_top.plot(
        n_xi_orders, n_xi_forces, "-o", color="#0072B2", lw=1.2, ms=3.6,
        label="BEM Gauss–Legendre $n_\\xi$ (1,504-panel PEC)",
    )
    ax_d_top.axhline(n_xi_forces[-1], color="#64748B", lw=0.65, ls=":")
    ax_d_top.annotate(
        f"{n_xi_drift:.4f}% drift for $n_\\xi \\geq 24$\n(${n_xi_forces[1]:+.4f} \\to {n_xi_forces[-1]:+.4f}$ pN)",
        xy=(24, n_xi_forces[1]), xytext=(33, 6.2738),
        fontsize=4.75, fontweight="bold", color="#0072B2", ha="left", va="center",
        bbox=dict(boxstyle="round,pad=0.16", facecolor="#EFF6FF", edgecolor="#93C5FD", lw=0.5),
        arrowprops=dict(arrowstyle="->", color="#0072B2", lw=0.55, mutation_scale=5),
    )
    ax_d_top.set_title("Frequency quadrature & fixed-standoff FDTD convergence", fontweight="bold", loc="left", pad=4)
    ax_d_top.set_xlabel("BEM imaginary-frequency quadrature order $n_\\xi$", labelpad=1.2)
    ax_d_top.set_ylabel("$F_z$ (pN)")
    ax_d_top.set_xlim(12, 68)
    ax_d_top.set_ylim(6.2695, 6.2762)
    ax_d_top.set_xticks(n_xi_orders)

    fdtd_res = [40, 50, 60, 80]
    fdtd_fixed_fz = [
        pm_val("meep_fixedbox_r40_fz_pn"),
        pm_val("meep_fixedbox_r50_fz_pn"),
        pm_val("meep_fixedbox_r60_fz_pn"),
        pm_val("meep_fixedbox_r80_fz_pn"),
    ]
    fdtd_r60_nmax2 = pm_val("meep_fixedbox_r60_nmax2_fz_pn")
    fdtd_r60_gold = pm_val("meep_fixedbox_r60_gold_fz_pn")
    fdtd_gold_pct = pm_val("meep_fixedbox_r60_gold_vs_pec_pct")
    fdtd_drift = pm_val("meep_fixedbox_r60_to_r80_drift_pct")

    ax_d_bot.plot(
        fdtd_res, fdtd_fixed_fz, "-s", color="#009E73", lw=1.2, ms=3.6,
        label="PEC ($n_{\\max}=0$, $\\delta_{\\mathrm{box}}=10$ nm)",
    )
    ax_d_bot.plot(
        [60], [fdtd_r60_nmax2], marker="^", ls="none", color="#6A3D9A", ms=4.5,
        label=f"PEC $n_{{\\max}}=2$ DCT (+{fdtd_r60_nmax2:.4f} pN)",
    )
    ax_d_bot.plot(
        [60], [fdtd_r60_gold], marker="D", ls="none", color="#D55E00", ms=4.2,
        label=f"Drude gold (+{fdtd_r60_gold:.4f} pN, {fdtd_gold_pct:.1f}% PEC)",
    )
    ax_d_bot.annotate(
        f"{fdtd_drift:.2f}% drift ($R=60\\to 80$)",
        xy=(70, 0.5 * (fdtd_fixed_fz[2] + fdtd_fixed_fz[3])),
        xytext=(63, 0.62),
        fontsize=4.75, fontweight="bold", color="#047857", ha="center", va="bottom",
        bbox=dict(boxstyle="round,pad=0.15", facecolor="#ECFDF5", edgecolor="#6EE7B7", lw=0.5),
        arrowprops=dict(arrowstyle="->", color="#047857", lw=0.55, mutation_scale=5),
    )
    ax_d_bot.set_xlabel("FDTD grid resolution $R$ (px $\\mu\\mathrm{m}^{-1}$; $\\Delta x = 25 \\to 12.5$ nm)", labelpad=1.2)
    ax_d_bot.set_ylabel("$F_z$ (pN)")
    ax_d_bot.set_xlim(36, 84)
    ax_d_bot.set_ylim(0.14, 0.79)
    ax_d_bot.set_xticks(fdtd_res)
    ax_d_bot.set_xticklabels(["40\n(25 nm)", "50\n(20 nm)", "60\n(16.7 nm)", "80\n(12.5 nm)"])
    ax_d_bot.legend(loc="lower left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1", framealpha=0.94, fontsize=4.4, handlelength=1.2, labelspacing=0.18, borderpad=0.24)

    # Panel labels (8 pt bold lowercase outside top-left)
    panel_axes = [
        ("a", ax_a),
        ("b", ax_b),
        ("c", ax_c),
        ("d", ax_d_top),
    ]
    for label_char, ax_item in panel_axes:
        pos = ax_item.get_position()
        figure.text(
            pos.x0 - 0.042,
            pos.y1 + 0.014,
            label_char,
            fontsize=8.0,
            fontweight="bold",
            va="bottom",
            ha="left",
            color="#0F172A",
        )

    tracked_metrics = [
        "cantor_n2_hybridrz_bem_std_f_z_pn",
        "cantor_n2_hybridrz_bem_high_f_z_pn",
        "cantor_n2_hybridrz_bem_ultra_f_z_pn",
        "cantor_n2_hybridrz_bem_r5nm_std_f_z_pn",
        "cantor_n2_hybridrz_bem_r5nm_high_f_z_pn",
        "cantor_n2_hybridrz_bem_r5nm_ultra_f_z_pn",
        "cantor_n2_vs_uniform_ratio_sharp_std",
        "cantor_n2_vs_uniform_ratio_sharp_high",
        "cantor_n2_vs_uniform_ratio_sharp_ultra",
        "cantor_n2_vs_uniform_ratio_r5nm_std",
        "cantor_n2_vs_uniform_ratio_r5nm_high",
        "cantor_n2_vs_uniform_ratio_r5nm_ultra",
        "rot_c8_compact_n2_bem_theta18_richardson_f_z_pn",
        "rot_c8_compact_n2_bem_theta48_continuum_f_z_pn",
        "rot_c4_tightslot_n2_bem_theta18_richardson_f_z_pn",
        "rot_c4_tightslot_n2_bem_theta48_continuum_f_z_pn",
        "rot_c4_tightslot_n2_bem_theta48_richardson_f_z_pn",
        "bem_conv_std_nxi16_pec_fz_pn",
        "bem_conv_std_nxi24_pec_fz_pn",
        "bem_conv_std_nxi32_pec_fz_pn",
        "bem_conv_std_nxi40_pec_fz_pn",
        "bem_conv_std_nxi64_pec_fz_pn",
        "meep_fixedbox_r40_fz_pn",
        "meep_fixedbox_r50_fz_pn",
        "meep_fixedbox_r60_fz_pn",
        "meep_fixedbox_r80_fz_pn",
        "meep_fixedbox_r60_nmax2_fz_pn",
        "meep_fixedbox_r60_gold_fz_pn",
        "n3_uni3d_f111_unified_fz_pn",
        "n3_uni3d_f111_unified_theta21_fz_pn",
        "n3_uni3d_f111_unified_theta48_fz_pn",
        "n3_uni3d_f110_rtheta_planar_fz_pn",
        "n3_uni3d_ctrl_uni12_fz_pn",
        "n3_uni3d_ratio_f111_vs_uni111",
    ]
    try:
        for extension in ("png", "pdf"):
            path = directory / f"fig_{CAMPAIGN}.{extension}"
            figure.savefig(path, dpi=600, facecolor="#FFFFFF")
            metrics_logger.save_plot_provenance(
                str(path),
                str(provenance_path),
                tracked_metrics,
                solver_name=CAMPAIGN,
                solver_parameters=dict(provenance),
            )
            prov_sidecar = path.with_suffix(".provenance.json")
            for paper_dir in (
                REPOSITORY_ROOT / "Papers" / "Fractal_Casimir_Nature_EM" / "figures",
                REPOSITORY_ROOT / "Papers" / "FCE_Nature_ver01" / "figures",
            ):
                if paper_dir.is_dir():
                    for src_file in (path, prov_sidecar):
                        if not src_file.is_file():
                            continue
                        dst_fig = paper_dir / src_file.name
                        try:
                            shutil.copy2(src_file, dst_fig)
                        except OSError:
                            try:
                                tmp_fig = dst_fig.with_suffix(dst_fig.suffix + ".tmp")
                                shutil.copy2(src_file, tmp_fig)
                                os.replace(tmp_fig, dst_fig)
                            except OSError:
                                pass
    finally:
        plt.close(figure)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--figures-dir", type=Path, default=Path("figures"))
    parser.add_argument("--include-c10-ultra", action="store_true")
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="Regenerate Figure 3 directly from cached report and provenance_metrics.json.",
    )
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    return args


def main() -> int:
    args = parse_arguments()
    if args.plot_only:
        report_path = args.output_dir / f"{CAMPAIGN}_report.json"
        if not report_path.is_file():
            raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Missing {report_path}")
        existing_report = json.loads(report_path.read_text(encoding="utf-8"))
        rows_cached = existing_report.get("tasks", [])
        conv_cached = existing_report.get("convergence", [])
        prov_cached = existing_report.get("provenance", {})
        make_figure(rows_cached, conv_cached, args.figures_dir, prov_cached)
        print(f"Plot-only regeneration complete: {args.figures_dir / f'fig_{CAMPAIGN}.png'}", flush=True)
        return 0
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if args.device != "auto":
        device = args.device if args.device != "cuda" or torch.cuda.is_available() else "cpu"
    micro = 0 < args.max_steps <= 5
    if micro:
        torch.set_num_threads(1)

    if int(SYMMETRY_ORDER) != DEFAULT_NUM_SECTORS or not math.isclose(
        float(SECTOR_DEG), DEFAULT_SECTOR_DEG
    ):
        raise ValueError("This verification requires exact four-sector C4 geometry")
    if not math.isclose(
        float(Z_TIP_FIXED_UM), DEFAULT_Z_TIP_ROTATIONAL_UM, abs_tol=1e-12
    ):
        raise ValueError(
            f"Imported fixed tip elevation differs from {DEFAULT_Z_TIP_ROTATIONAL_UM} um"
        )
    if not math.isclose(float(Z_PAD_TOP_UM), DEFAULT_Z_PAD_TOP_UM, abs_tol=1e-12):
        raise ValueError(
            f"Imported landing-pad elevation differs from {DEFAULT_Z_PAD_TOP_UM} um"
        )
    if not math.isclose(GAP_UM, DEFAULT_ENGAGED_GAP_UM, abs_tol=1e-12):
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
            angles = (
                ROTATIONAL_3STATE_ANGLES_DEG
                if design == DESIGN_NAMES[2]
                else ROTATIONAL_3SOLVER_N2_ANGLES_DEG
            )
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
