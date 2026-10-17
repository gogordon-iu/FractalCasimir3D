import argparse
import glob
import json
import math
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from utils.metrics_logger import log_metrics


MEEP_TO_PA = 0.0316152649


def _pressure_is_scaled(metadata, default=False):
    """Use explicit metadata, not pressure magnitude, to detect SI pressures."""
    for key in ("pressure_scaled", "pressures_scaled", "pressure_is_scaled"):
        if key in metadata:
            value = metadata[key]
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean.")
            return value

    for key in ("pressure_units", "pressure_unit"):
        if key in metadata:
            unit = metadata[key]
            if not isinstance(unit, str):
                raise ValueError(f"{key} must be a string.")
            unit = unit.strip().lower()
            if unit in ("pa", "pascal", "pascals"):
                return True
            if unit in ("meep", "dimensionless", "unscaled", "meep_units"):
                return False
            raise ValueError(f"Unsupported pressure unit: {unit!r}.")

    return default


def _finite_number(record, key, index):
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Record {index}: {key} must be a finite number.")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError(f"Record {index}: {key} must be finite.") from exc
    if not math.isfinite(value):
        raise ValueError(f"Record {index}: {key} must be finite.")
    return value


def generate_latex_tables(max_steps=None):
    if max_steps is not None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps <= 0:
            raise ValueError("--max-steps must be a positive integer.")

    summaries = sorted(
        glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json"),
        key=os.path.getmtime,
    )
    if not summaries:
        raise FileNotFoundError("[ERROR: RUN_DATA_MISSING] No sweet spot sweep summary found.")

    summary_path = summaries[-1]
    print(f"Loading sweet spot sweep summary from: {summary_path}")
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"[ERROR: RUN_DATA_MISSING] Summary not found: {summary_path}"
        ) from exc

    scaled_by_default = False
    if isinstance(payload, dict):
        scaled_by_default = _pressure_is_scaled(payload)
        records = payload.get("results", payload.get("data"))
    else:
        records = payload

    if records is None or records == []:
        raise ValueError(f"[ERROR: RUN_DATA_MISSING] No records in {summary_path}.")
    if not isinstance(records, list):
        raise ValueError("The summary must contain a list of result records.")

    if max_steps is not None:
        records = records[:max_steps]

    # Normalize once so every downstream pressure calculation uses SI Pascals.
    # A pressure gradient computed against d_um must additionally be multiplied
    # by 1e6 to express stiffness in Pa/m.
    data = []
    converted_count = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Record {index} must be an object.")
        normalized = dict(record)
        for key in ("alpha_deg", "theta_deg", "d_um", "pressure_Pa"):
            normalized[key] = _finite_number(record, key, index)
        if not _pressure_is_scaled(record, scaled_by_default):
            normalized["pressure_Pa"] *= MEEP_TO_PA
            converted_count += 1
        normalized["pressure_scaled"] = True
        normalized["pressure_units"] = "Pa"
        data.append(normalized)

    # 1. High repulsive table
    repulsive = [d for d in data if d["pressure_Pa"] > 0]
    repulsive_sorted = sorted(repulsive, key=lambda x: x["pressure_Pa"], reverse=True)

    # 2. Levitation equilibrium points
    curves = {}
    for r in data:
        k = (r["alpha_deg"], r["theta_deg"])
        curves.setdefault(k, []).append(r)

    eq_points = []
    for (a, th), pts in curves.items():
        pts.sort(key=lambda x: x["d_um"])
        d_arr = [p["d_um"] for p in pts]
        p_arr = [p["pressure_Pa"] for p in pts]
        for i in range(len(p_arr) - 1):
            if p_arr[i] > 0 and p_arr[i + 1] < 0:
                d1, d2 = d_arr[i], d_arr[i + 1]
                p1, p2 = p_arr[i], p_arr[i + 1]
                if d2 <= d1:
                    continue
                # Weighted interpolation avoids overflow in p2 - p1.
                weight = 1.0 / (1.0 + abs(p2) / p1)
                d_eq = (1.0 - weight) * d1 + weight * d2
                eq_points.append({
                    "alpha_deg": a,
                    "theta_deg": th,
                    "d_eq_nm": d_eq * 1000.0,
                    "p_max_Pa": max(p_arr),
                    "d1_nm": d1 * 1000.0,
                    "d2_nm": d2 * 1000.0,
                    "p1_Pa": p1,
                    "p2_Pa": p2,
                })

    print(f"Found {len(repulsive)} repulsive points out of {len(data)} total FDTD points.")
    print(f"Found {len(eq_points)} stable nanomechanical levitation equilibrium points.")

    tables_dir = os.path.join("Papers", "Fractal_Casimir_Nature_EM", "tables")
    os.makedirs(tables_dir, exist_ok=True)

    # Write sweet spot table
    out_tex_path = os.path.join(tables_dir, "table_sweet_spot_repulsion.tex")
    with open(out_tex_path, "w", encoding="utf-8") as f:
        f.write(f"% Auto-generated from {summary_path}\n")
        f.write("% Pressures normalized to SI Pascals.\n")
        f.write("\\begin{table}[htbp]\n")
        f.write("\\centering\n")
        f.write("\\caption{Representative Verified 3D FDTD Repulsive Casimir Pressures ($P > 0$) in Vacuum across the $(\\alpha, \\theta, d)$ Parameter Space ($L=2.0\\ \\mu\\text{m}$, $N=3$).}\n")
        f.write("\\label{tab:sweet_spot_repulsion}\n")
        f.write("\\begin{tabular}{ccccc}\n")
        f.write("\\toprule\n")
        f.write("\\textbf{Corrugation $\\alpha$} & \\textbf{Twist $\\theta$} & \\textbf{Separation $d$ (nm)} & \\textbf{Pressure $P$ (Pa)} & \\textbf{Regime} \\\\\n")
        f.write("\\midrule\n")
        for r in repulsive_sorted[:20]:
            f.write(f"${r['alpha_deg']:.1f}^\\circ$ & ${r['theta_deg']:.1f}^\\circ$ & ${r['d_um'] * 1000.0:.1f}$ nm & $\\mathbf{{{r['pressure_Pa']:+.6f}}}$ & \\textbf{{REPULSIVE}} \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")

    # Write equilibrium table
    eq_tex_path = os.path.join(tables_dir, "table_levitation_equilibria.tex")
    with open(eq_tex_path, "w", encoding="utf-8") as f:
        f.write(f"% Auto-generated from {summary_path}\n")
        f.write("% Pressures normalized to SI Pascals.\n")
        f.write("\\begin{table}[htbp]\n")
        f.write("\\centering\n")
        f.write("\\caption{Stable Passive Nanomechanical Levitation Equilibrium Heights ($d_{\\rm eq}$ where $P=0$ and $\\partial P/\\partial d < 0$) in Vacuum.}\n")
        f.write("\\label{tab:levitation_equilibria}\n")
        f.write("\\begin{tabular}{ccccc}\n")
        f.write("\\toprule\n")
        f.write("\\textbf{Corrugation $\\alpha$} & \\textbf{Twist $\\theta$} & \\textbf{Peak Pressure $P_{\\max}$ (Pa)} & \\textbf{Equilibrium Gap $d_{\\rm eq}$ (nm)} & \\textbf{Stability} \\\\\n")
        f.write("\\midrule\n")
        for eq in eq_points:
            f.write(f"${eq['alpha_deg']:.1f}^\\circ$ & ${eq['theta_deg']:.1f}^\\circ$ & $+{eq['p_max_Pa']:.4f}$ Pa & $\\mathbf{{{eq['d_eq_nm']:.2f}\\text{{ nm}}}}$ & \\textbf{{Stable Levitation}} \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")

    log_metrics({
        "summary_path": summary_path,
        "max_steps": max_steps,
        "total_points": len(data),
        "converted_pressure_points": converted_count,
        "meep_to_pa": MEEP_TO_PA,
        "repulsive_points": len(repulsive),
        "equilibrium_points": len(eq_points),
        "repulsion_table": out_tex_path,
        "equilibrium_table": eq_tex_path,
    })
    print(f"Wrote {out_tex_path} and {eq_tex_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate SI-normalized sweet spot tables.")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Maximum number of summary records to process (default: all).",
    )
    args = parser.parse_args()
    if args.max_steps is not None and args.max_steps <= 0:
        parser.error("--max-steps must be a positive integer.")
    generate_latex_tables(max_steps=args.max_steps)
