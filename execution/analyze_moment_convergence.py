#!/usr/bin/env python3
"""
Quantum Clutch: Moment Multipole Convergence Analyzer
------------------------------------------------------
Analyzes the convergence of the spatial Discrete Cosine Transform (DCT)
multipole moment expansion for the Quantum Clutch at resolution R = 60.

Compares:
  - n_max = 1 (Fundamental uniform mode: m1=0, m2=0; 72 FDTD simulations)
  - n_max = 3 (Higher-order multipoles up to dipole modes; 216 FDTD simulations)

Quantifies truncation error:
  Delta_trunc = |F_net(nmax=3) - F_net(nmax=1)| / |F_net(nmax=1)| * 100%

Generates LaTeX summary for Nature manuscript and SI.
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

MEEP_TO_PA = 0.0316152649


def get_effective_area(N, L):
    return ((8.0 / 9.0) ** (N - 1)) * (L ** 2)


def _finite_float(value):
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid force or pressure data.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Force and pressure data must be finite.")
    return result


def load_result_or_checkpoint(tag, nmax):
    """
    Attempts to load completed force result or checkpoint for a given nmax.
    Returns (f_both, f_self, f_net, p_val, status).
    Raises RuntimeError if no usable moment data is found.
    """
    nmax_str = f"_nmax_{nmax}" if nmax != 1 else ""

    # 1. Check full output json
    out_file = (
        ".tmp/meep_d_0.0400_N_3_clutch_al_75.0_rtip_5.0_Nbot_3_Gold"
        f"_res_60_theta_0.0_eps_1.0_L_2.00{nmax_str}.json"
    )
    if os.path.exists(out_file):
        try:
            with open(out_file, "r") as f:
                d = json.load(f)
            values = tuple(
                _finite_float(d[key])
                for key in (
                    "force_both",
                    "force_self",
                    "force_subtracted",
                    "pressure_Pa",
                )
            )
            return (*values, "COMPLETE")
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, OverflowError):
            pass

    # 2. Check completed config checkpoints
    chk_tag = (
        "v4_d_0.0400_Ntop_3_Nbot_3_mat_Gold_res_60_th_0.0"
        f"_clutch_al_75.0_rtip_5.0_L_2.00{nmax_str}"
    )
    chk_both = f".tmp/chk_{chk_tag}_both.json"
    chk_self = f".tmp/chk_{chk_tag}_self.json"
    if os.path.exists(chk_both) and os.path.exists(chk_self):
        try:
            with open(chk_both, "r") as fb, open(chk_self, "r") as fs:
                f_both = _finite_float(json.load(fb)["force"])
                f_self = _finite_float(json.load(fs)["force"])
                f_net = _finite_float(f_both - f_self)
                A_eff = get_effective_area(3, 2.0)
                p_val = _finite_float((f_net / A_eff) * MEEP_TO_PA)
                return f_both, f_self, f_net, p_val, "CHECKPOINT_COMPLETE"
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, OverflowError):
            pass

    # 3. Check granular per-moment progress
    chk_moments_both = f".tmp/chk_moments_{chk_tag}_both.json"
    chk_moments_self = f".tmp/chk_moments_{chk_tag}_self.json"
    moments_done = 0
    total_moments = 36 * nmax * 2
    for m_file in [chk_moments_both, chk_moments_self]:
        if os.path.exists(m_file):
            try:
                with open(m_file, "r") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                completed = data.get("completed_moments", {})
                if isinstance(completed, (dict, list)):
                    moments_done += len(completed)
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
                pass

    if moments_done == 0:
        raise RuntimeError(
            f"[ERROR: RUN_DATA_MISSING] No usable moment data found for "
            f"{tag} (n_max={nmax}). Expected {out_file}, completed force "
            "checkpoints, or nonempty per-moment checkpoints."
        )

    pct = (moments_done / total_moments) * 100.0 if total_moments > 0 else 0.0
    return (
        None,
        None,
        None,
        None,
        f"IN_PROGRESS ({moments_done}/{total_moments} moments, {pct:.1f}%)",
    )


def _nonnegative_int(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if result < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps",
        type=_nonnegative_int,
        default=None,
        help=(
            "Run step-budget metadata for automation. This analyzer reads existing "
            "results and does not execute simulation steps."
        ),
    )
    args = parser.parse_args()

    print("=" * 80)
    print("QUANTUM CLUTCH: MOMENT MULTIPOLE CONVERGENCE ANALYZER (n_max=1 vs n_max=3)")
    print("=" * 80)
    print("Target Geometry: Dual-Fractal Quantum Clutch (Level 3 Menger vs Level 3 Sieve)")
    print("Parameters:      d = 40 nm, theta = 0.0 deg, R = 60 (dx = 16.7 nm), Gold, L = 2.0 um")
    print("-" * 80)

    f_both_1, f_self_1, f_net_1, p_1, status_1 = load_result_or_checkpoint("task_001", nmax=1)
    f_both_3, f_self_3, f_net_3, p_3, status_3 = load_result_or_checkpoint("task_conv_nmax3", nmax=3)

    print(f"Status n_max = 1 (Fundamental Mode, 72 sims):  {status_1}")
    if f_net_1 is not None:
        print(f"  -> F_both: {f_both_1:+.6e}, F_self: {f_self_1:+.6e}")
        print(f"  -> F_net:  {f_net_1:+.6e} [Casimir {'Repulsion' if f_net_1 > 0 else 'Attraction' if f_net_1 < 0 else 'Zero Force'}]")
        print(f"  -> Pressure: {p_1:+.4e} Pa")

    print(f"\nStatus n_max = 3 (Multipole Expansion, 216 sims): {status_3}")
    if f_net_3 is not None:
        print(f"  -> F_both: {f_both_3:+.6e}, F_self: {f_self_3:+.6e}")
        print(f"  -> F_net:  {f_net_3:+.6e} [Casimir {'Repulsion' if f_net_3 > 0 else 'Attraction' if f_net_3 < 0 else 'Zero Force'}]")
        print(f"  -> Pressure: {p_3:+.4e} Pa")

    os.makedirs("results_clutch", exist_ok=True)
    os.makedirs("Papers/Fractal_Casimir_Nature_EM/tables", exist_ok=True)

    if f_net_1 is not None and f_net_3 is not None:
        delta_f = abs(f_net_3 - f_net_1)
        if not math.isfinite(delta_f):
            raise RuntimeError("Force difference exceeds the finite numeric range.")

        delta_pct = None
        if f_net_1 != 0.0:
            relative_error = (delta_f / abs(f_net_1)) * 100.0
            if math.isfinite(relative_error):
                delta_pct = relative_error

        sign_preserved = (
            (f_net_1 > 0 and f_net_3 > 0)
            or (f_net_1 < 0 and f_net_3 < 0)
            or (f_net_1 == 0 and f_net_3 == 0)
        )
        delta_text = f"{delta_pct:.2f}%" if delta_pct is not None else "Undefined"
        delta_latex = (
            rf"{delta_pct:.2f}\%" if delta_pct is not None else r"\text{Undefined}"
        )
        if not sign_preserved:
            sign_text = "WARNING: SIGN CHANGED"
            sign_caption = "The force sign changes between the two cutoffs."
        elif f_net_1 > 0:
            sign_text = "VERIFIED (Repulsion Confirmed)"
            sign_caption = r"The repulsive sign ($P > 0$) is preserved."
        elif f_net_1 < 0:
            sign_text = "VERIFIED (Attraction Confirmed)"
            sign_caption = r"The attractive sign ($P < 0$) is preserved."
        else:
            sign_text = "VERIFIED (Both Forces Zero)"
            sign_caption = "Both net forces are zero."

        print("\n" + "=" * 80)
        print("CONVERGENCE ANALYSIS RESULTS")
        print("=" * 80)
        print(f"  Relative Truncation Error (Delta_trunc): {delta_text}")
        print(f"  Sign Preservation:                      {sign_text}")
        print(f"  Absolute Force Difference:              {delta_f:.6e}")
        print("=" * 80)

        summary_data = {
            "model": "Quantum Clutch",
            "dataset": "moment_convergence_nmax1_vs_nmax3",
            "status": "completed",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "max_steps": args.max_steps,
            "geometry": "Dual-Fractal Quantum Clutch (N=3)",
            "d_nm": 40.0,
            "theta_deg": 0.0,
            "resolution": 60,
            "nmax_1": {
                "modes": "(0, 0)",
                "force_both": f_both_1,
                "force_self": f_self_1,
                "force_net": f_net_1,
                "pressure_Pa": p_1,
            },
            "nmax_3": {
                "modes": "(0, 0), (1, 0), (0, 1)",
                "force_both": f_both_3,
                "force_self": f_self_3,
                "force_net": f_net_3,
                "pressure_Pa": p_3,
            },
            "delta_force_abs": delta_f,
            "truncation_error_percent": delta_pct,
            "sign_preserved": sign_preserved,
        }

        with open("results_clutch/moment_convergence_analysis.json", "w") as f:
            json.dump(summary_data, f, indent=4, allow_nan=False)
        print("Saved summary: results_clutch/moment_convergence_analysis.json")

        from utils.metrics_logger import log_metrics

        log_metrics(summary_data)

        latex_content = rf"""% Auto-generated by execution/analyze_moment_convergence.py
\begin{{table}}[htbp]
\centering
\caption{{\textbf{{Spatial Multipole Moment Convergence of the Dual-Fractal Quantum Clutch.}} Comparison of the Casimir force and pressure between the fundamental Discrete Cosine Transform (DCT) uniform mode ($n_{{\max}}=1$) and the higher-order multipole expansion including spatial dipole moments ($n_{{\max}}=3$) at $R=60$ ($\Delta x = 16.67\text{{ nm}}$), $d = 40\text{{ nm}}$, and $\theta = 0^\circ$. {sign_caption} The relative truncation discrepancy is $\Delta_{{\text{{trunc}}}} = {delta_latex}$.}}
\label{{tab:moment_convergence}}
\begin{{tabular}}{{lccccc}}
\toprule
\textbf{{Multipole Cutoff}} & \textbf{{Modes Evaluated}} & \textbf{{Total Sims}} & \textbf{{Net Force}} & \textbf{{Casimir Pressure}} & \textbf{{Relative Diff.}} \\
\midrule
$n_{{\max}} = 1$ (Fundamental) & $(0,0)$ & $72$ & ${f_net_1:+.4e}$ & ${p_1:+.2e}\text{{ Pa}}$ & Baseline \\
$n_{{\max}} = 3$ (Multipole) & $(0,0), (1,0), (0,1)$ & $216$ & ${f_net_3:+.4e}$ & ${p_3:+.2e}\text{{ Pa}}$ & $\mathbf{{{delta_latex}}}$ \\
\bottomrule
\end{{tabular}}
\end{{table}}
"""
        tex_path = "Papers/Fractal_Casimir_Nature_EM/tables/table_moment_convergence.tex"
        with open(tex_path, "w") as f:
            f.write(latex_content)
        print(f"Saved LaTeX table: {tex_path}")

        try:
            from execution.git_sync import git_sync_results

            git_sync_results("data(convergence): record nmax=1 vs nmax=3 multipole convergence")
        except Exception as e:
            print(f"Note: Git sync skipped: {e}")
    else:
        print("\n[Awaiting Data] One or both moment simulations are still calculating.")
        print("  - Run 'sbatch execution/submit_clutch_convergence_nmax3.sbatch' to begin or continue the nmax=3 test.")
        print("  - This analyzer will run automatically upon completion of the nmax=3 run.")


if __name__ == "__main__":
    main()
