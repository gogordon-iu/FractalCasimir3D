"""Orchestrator for BigRed 200 Routed Simulations (Sim 1-3, plus optional Local Sim 4-5 & Sync)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fractal_casimir_gravity.simulations import (  # noqa: E402
    generate_all_figures_and_tables,
    sim1_vernier_gw_and_scalaron,
    sim2_force_free_curvature_tolman,
    sim3_log_periodic_metric_comb,
    sim4_nec_sec_raychaudhuri_qei,
    sim5_gravitomagnetic_frame_dragging,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BigRed 200 routed Fractal Casimir Gravity suite")
    parser.add_argument("--max-steps", type=int, default=None, help="Optional step cap for testing/profiling")
    parser.add_argument("--results-dir", default="fractal_casimir_gravity/results", help="Output directory for JSON and provenance")
    parser.add_argument("--figures-dir", default="fractal_casimir_gravity/figures", help="Output directory for generated figures")
    parser.add_argument("--include-local", action="store_true", help="Also execute local-routed Sim 4 and Sim 5")
    parser.add_argument("--generate-figures", action="store_true", help="Generate all 6 figures, sidecars, and macros into results/figures")
    parser.add_argument("--sync-paper", action="store_true", help="Generate figures and sync macros directly into Papers/Fractal_Casimir_Gravity")
    args = parser.parse_args()

    sim1_vernier_gw_and_scalaron.run_simulation(max_steps=args.max_steps, results_dir=args.results_dir)
    sim2_force_free_curvature_tolman.run_simulation(max_steps=args.max_steps, results_dir=args.results_dir)
    sim3_log_periodic_metric_comb.run_simulation(max_steps=args.max_steps, results_dir=args.results_dir)

    if args.include_local:
        sim4_nec_sec_raychaudhuri_qei.run_simulation(max_steps=args.max_steps, results_dir=args.results_dir)
        sim5_gravitomagnetic_frame_dragging.run_simulation(max_steps=args.max_steps, results_dir=args.results_dir)

    if args.generate_figures or args.sync_paper:
        generate_all_figures_and_tables.generate_all(
            results_dir=args.results_dir,
            figures_dir=args.figures_dir,
            sync_paper=args.sync_paper,
        )


if __name__ == "__main__":
    main()
