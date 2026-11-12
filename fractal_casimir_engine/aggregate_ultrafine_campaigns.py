#!/usr/bin/env python3
"""Post-harvest aggregator for the 4 BigRed 200 Ultra-Fine Fractal Casimir Engine suites.

After ``git pull`` brings back the completed BigRed 200 telemetry commits for
``eng_uf1``, ``eng_uf2``, ``eng_uf3``, and ``eng_uf4``, run this script to:
  1. Verify non-truncated completion of all 4 ``uf*_report.json`` artifacts,
     their ``uf*_provenance_metrics.json`` ledgers, ``uf*_macros_results.tex``
     exports, and ``fig_uf*`` figures + ``.provenance.json`` sidecars.
  2. Merge ``uf1``..``uf4`` provenance steps and metrics with the baseline
     ``fractal_casimir_engine/results/provenance_metrics.json``.
  3. Sync ``fig_uf1_*``..``fig_uf4_*`` + ``.provenance.json`` sidecars into
     ``Papers/Fractal_Casimir_Engine/figures/`` (unless ``--cluster-safe`` is set,
     which writes strictly under ``fractal_casimir_engine/results/ultrafine/``).
  4. Append ``uf1``..``uf4`` LaTeX macros into ``Papers/Fractal_Casimir_Engine/macros_results.tex``
     and regenerate ``manuscript_provenance_map.json`` (verifying ``audit_status == 'PASS'``).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.metrics_logger import generate_manuscript_map

ENGINE_DIR = PROJECT_ROOT / "fractal_casimir_engine"
UF_RESULTS_DIR = ENGINE_DIR / "results" / "ultrafine"
ENGINE_FIGURES_DIR = ENGINE_DIR / "figures"
PAPER_DIR = PROJECT_ROOT / "Papers" / "Fractal_Casimir_Engine"
PAPER_FIGURES_DIR = PAPER_DIR / "figures"

REQUIRED_SUITES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "eng_uf1",
        "uf1_mesh_convergence_report.json",
        "uf1_provenance_metrics.json",
        "uf1_macros_results.tex",
        "fig_uf1_mesh_convergence",
    ),
    (
        "eng_uf2",
        "uf2_meep_verification_report.json",
        "uf2_provenance_metrics.json",
        "uf2_macros_results.tex",
        "fig_uf2_meep_vs_bem",
    ),
    (
        "eng_uf3",
        "uf3_active_switching_report.json",
        "uf3_provenance_metrics.json",
        "uf3_macros_results.tex",
        "fig_uf3_active_switching",
    ),
    (
        "eng_uf4",
        "uf4_6dof_and_rounding_report.json",
        "uf4_provenance_metrics.json",
        "uf4_macros_results.tex",
        "fig_uf4_6dof_and_rounding",
    ),
)


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def aggregate_campaigns(
    *,
    uf_results_dir: Path = UF_RESULTS_DIR,
    engine_figures_dir: Path = ENGINE_FIGURES_DIR,
    base_metrics_path: Path = ENGINE_DIR / "results" / "provenance_metrics.json",
    paper_dir: Path = PAPER_DIR,
    check_only: bool = False,
    cluster_safe: bool = False,
) -> dict[str, Any]:
    missing: list[str] = []
    macro_blocks: list[str] = []
    suite_manifests: list[dict[str, Any]] = []

    for suite_id, rep_name, met_name, mac_name, fig_stem in REQUIRED_SUITES:
        rep_path = uf_results_dir / rep_name
        met_path = uf_results_dir / met_name
        mac_path = uf_results_dir / mac_name
        if not rep_path.is_file():
            missing.append(f"{suite_id}: missing {rep_path}")
            continue
        with rep_path.open("r", encoding="utf-8") as fh:
            rep = json.load(fh)
        if rep.get("time_truncated", False) or rep.get("status") != "completed":
            missing.append(f"{suite_id}: incomplete or time-truncated ({rep.get('status')})")
            continue
        if not met_path.is_file():
            missing.append(f"{suite_id}: missing {met_path}")
            continue
        with met_path.open("r", encoding="utf-8") as fh:
            suite_manifests.append(json.load(fh))
        if not mac_path.is_file():
            missing.append(f"{suite_id}: missing {mac_path}")
            continue
        macro_blocks.append(
            f"% --- {suite_id} Ultra-Fine Campaign Macros ---\n"
            + mac_path.read_text(encoding="utf-8").strip()
        )
        for ext in (".png", ".pdf"):
            fig_file = engine_figures_dir / f"{fig_stem}{ext}"
            sidecar = engine_figures_dir / f"{fig_stem}{ext}.provenance.json"
            if not fig_file.is_file() or not sidecar.is_file():
                missing.append(f"{suite_id}: missing figure/sidecar {fig_file.name}")

    if missing:
        return {"ready": False, "missing": missing}

    if check_only:
        return {"ready": True, "missing": []}

    # Merge baseline + UF1..UF4 provenance manifests
    if base_metrics_path.is_file():
        with base_metrics_path.open("r", encoding="utf-8") as fh:
            merged_manifest: dict[str, Any] = json.load(fh)
    else:
        merged_manifest = {"run_metadata": {}, "intermediate_steps": {}, "metrics": {}}
    merged_manifest.setdefault("run_metadata", {})
    merged_manifest.setdefault("intermediate_steps", {})
    merged_manifest.setdefault("metrics", {})

    for sm in suite_manifests:
        merged_manifest["intermediate_steps"].update(sm.get("intermediate_steps", {}))
        merged_manifest["metrics"].update(sm.get("metrics", {}))
        runs = sm.get("run_metadata", {}).get("solver_runs", [])
        if isinstance(runs, list):
            merged_manifest["run_metadata"].setdefault("solver_runs", []).extend(runs)
    merged_manifest["run_metadata"]["updated_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()

    combined_uf_metrics = uf_results_dir / "uf_combined_provenance_metrics.json"
    atomic_write_json(combined_uf_metrics, merged_manifest)

    paper_macros = paper_dir / "macros_results.tex"
    base_text = paper_macros.read_text(encoding="utf-8") if paper_macros.is_file() else ""
    marker = "% === BEGIN ULTRAFINE CAMPAIGN MACROS ==="
    if marker in base_text:
        base_text = base_text.split(marker)[0].rstrip() + "\n"
    merged_macros = (
        base_text.rstrip()
        + "\n\n"
        + marker
        + "\n"
        + "\n\n".join(macro_blocks)
        + "\n% === END ULTRAFINE CAMPAIGN MACROS ===\n"
    )
    uf_macros_copy = uf_results_dir / "merged_macros_results.tex"
    uf_macros_copy.parent.mkdir(parents=True, exist_ok=True)
    uf_macros_copy.write_text(merged_macros, encoding="utf-8")

    paper_figures_dir = paper_dir / "figures"
    tex_path = paper_dir / "fractal_casimir_engine.tex"

    if cluster_safe:
        # On shared Lustre cluster nodes, write strictly under uf_results_dir without mutating Papers/
        map_out = uf_results_dir / "merged_manuscript_provenance_map.json"
        ledger = generate_manuscript_map(
            manuscript_path=str(tex_path),
            output_map_path=str(map_out),
            metrics_path=str(combined_uf_metrics),
            figures_dir=str(paper_figures_dir),
        )
        return {"ready": True, "cluster_safe": True, "ledger": ledger, "map_path": str(map_out)}

    paper_figures_dir.mkdir(parents=True, exist_ok=True)
    for _, _, _, _, fig_stem in REQUIRED_SUITES:
        stem_sidecar = engine_figures_dir / f"{fig_stem}.provenance.json"
        if stem_sidecar.is_file():
            shutil.copy2(stem_sidecar, paper_figures_dir / stem_sidecar.name)
        for ext in (".png", ".pdf"):
            for suffix in ("", ".provenance.json"):
                src = engine_figures_dir / f"{fig_stem}{ext}{suffix}"
                dst = paper_figures_dir / f"{fig_stem}{ext}{suffix}"
                shutil.copy2(src, dst)

    atomic_write_json(base_metrics_path, merged_manifest)
    paper_macros.write_text(merged_macros, encoding="utf-8")

    map_out = paper_dir / "manuscript_provenance_map.json"
    ledger = generate_manuscript_map(
        manuscript_path=str(tex_path),
        output_map_path=str(map_out),
        metrics_path=str(base_metrics_path),
        figures_dir=str(paper_figures_dir),
    )
    if ledger.get("audit_status") != "PASS":
        raise RuntimeError(f"Manuscript provenance audit did not PASS: {ledger}")
    return {"ready": True, "cluster_safe": False, "ledger": ledger, "map_path": str(map_out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report completion status of all 4 suites without mutating manuscript files.",
    )
    parser.add_argument(
        "--cluster-safe",
        action="store_true",
        help="Write merged artifacts strictly into results/ultrafine without touching Papers/.",
    )
    args = parser.parse_args(argv)
    res = aggregate_campaigns(check_only=args.check_only, cluster_safe=args.cluster_safe)
    if not res["ready"]:
        for item in res["missing"]:
            print(f"[PENDING] {item}", file=sys.stderr)
        return 1
    if args.check_only:
        print("[READY] All 4 Ultra-Fine suites completed and verified.")
    else:
        print(f"[AGGREGATED] Provenance map ready -> {res['map_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
