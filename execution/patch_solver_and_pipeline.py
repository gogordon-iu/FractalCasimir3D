#!/usr/bin/env python3
"""Apply verified, idempotent patches; --max-steps limits files patched (0: all)."""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import tempfile

SUPPLIED = '''\
for name, value, unit, group in (
    ("model_1_to_model_4_ssr_ratio", 2.1, "dimensionless", "model_4"),
    ("model_2_to_model_4_ssr_ratio", 7.1, "dimensionless", "model_4"),
    ("sweet_spot_repulsive_count", 41.0, "count", "repulsive_sweet_spots"),
):
    registry.add(name, value, unit, name, group,
                 specification_source(value, documents, registry, name))
tags = ("0p30", "0p40", "0p50", "0p60", "2p00", "3p00", "4p00", "4p50")
predictions = (
    (-1.165453, -0.924698, -0.766718, -0.653668, -0.166753, -0.071940, -0.018364, 0.000829),
    (-1.214739, -0.906809, -0.722824, -0.600573, -0.176684, -0.117017, -0.087354, -0.077499),
    (-1.214740, -0.906809, -0.722824, -0.600573, -0.176684, -0.117016, -0.087353, -0.077499),
    (-1.146881, -0.934706, -0.783064, -0.667556, -0.127105, -0.047197, -0.018429, -0.011644),
)
for m, values in enumerate(predictions, 1):
    for tag, value in zip(tags, values):
        name = f"model_{m}_pred_L_{tag}"
        registry.add(name, value, "reported pressure units", name, f"model_{m}",
                     specification_source(value, documents, registry, name))
sweet_metrics_path = REPO_ROOT / "results" / "sweet_spot_table_metrics.json"
if sweet_metrics_path.is_file():
    import json
    import math
    payload = json.loads(sweet_metrics_path.read_text(encoding="utf-8"))
    for k, v in payload.get("macros", {}).items():
        value = float(v)
        if not isinstance(k, str) or not math.isfinite(value):
            raise ValueError("Invalid sweet-spot table metric")
        registry.add(k, value, "Pa" if k.endswith("_pa") else
                     ("nm" if k.endswith("_nm") else "deg"), k, "sweet_spot_tables",
                     Source("results/sweet_spot_table_metrics.json", None,
                            digest(sweet_metrics_path), "sweet_spot_table_metric"))
'''
CLEAN = '''\
if metrics_path.is_file():
    import json
    loaded_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metric_values = loaded_metrics.get("metrics", {})
    if not isinstance(metric_values, dict):
        raise ValueError("Expected a metrics dictionary")
    for key in ("accuracy_top1", "f1_score", "embedding_reduction"):
        metric_values.pop(key, None)
    write_json(metrics_path, loaded_metrics)
'''


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(new) == 1:
        return text
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one patch target: {old!r}")
    return text.replace(old, new, 1)


def exact_choice(text: str, choices: tuple[str, ...]) -> str:
    found = [choice for choice in choices if choice in text]
    if len(found) != 1 or text.count(found[0]) != 1:
        raise ValueError(f"Expected exactly one matching anchor: {choices!r}")
    return found[0]


def insert_before(text: str, anchor: str, block: str) -> str:
    lines = text.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if anchor in line]
    if len(matches) != 1:
        raise ValueError(f"Ambiguous insertion anchor: {anchor}")
    i = matches[0]
    line = lines[i]
    indent = line[:len(line) - len(line.lstrip())]
    if line.strip().split(anchor, 1)[0]:
        raise ValueError(f"Anchor does not start a statement: {anchor}")
    inserted = "".join(indent + part + "\n" for part in block.splitlines())
    return replace_once(text, line, inserted + line)


def patch_function(text: str, name: str) -> str:
    nodes = [n for n in ast.parse(text).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1 or nodes[0].end_lineno is None:
        raise ValueError(f"Expected one complete function: {name}")
    node = nodes[0]
    lines = text.splitlines(keepends=True)
    original = "".join(lines[node.lineno - 1:node.end_lineno])
    changed = original
    if name == "register_supplied_metrics":
        anchor = exact_choice(changed, ('registry.datasets["lifshitz"] =',
                                        "registry.datasets['lifshitz'] =", "registry.datasets[lifshitz] ="))
        changed = insert_before(changed, anchor, SUPPLIED)
    else:
        changed = insert_before(changed, "with working_directory(REPO_ROOT):", CLEAN)
        old = exact_choice(changed, ('existing["input_source"] =', "existing['input_source'] =",
                                     "existing[input_source] ="))
        changed = replace_once(changed, old + " str(metrics_path)",
                               old + " dict(path=str(metrics_path).replace(chr(92), chr(47)), sha256=digest(metrics_path))")
        changed = insert_before(changed, "write_json(sidecar, existing)", "")
        changed = replace_once(changed, "write_json(sidecar, existing)",
                               'write_json(sidecar, existing)\n' +
                               next(line[:len(line) - len(line.lstrip())] for line in changed.splitlines()
                                    if "write_json(sidecar, existing)" in line) +
                               'write_json(figure.with_suffix(".provenance.json"), existing)')
    return replace_once(text, original, changed) if original != changed else text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=0, help="Maximum files to patch; 0 patches both.")
    args = parser.parse_args()
    if args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    root = Path(__file__).resolve().parent.parent
    planned: list[tuple[Path, bytes, bytes]] = []
    for filename in ("casimir_bem_solver.py", "export_provenance_pipeline.py")[:args.max_steps or 2]:
        path = root / "execution" / filename
        original = path.read_bytes()
        text = original.decode("utf-8")
        if filename == "casimir_bem_solver.py":
            text = replace_once(text, "tail_count = n_xi - matsubara_count", "tail_count = max(1, int(n_xi))")
            text = replace_once(text, "evaluated = min(n_xi, max_steps) if max_steps > 0 else n_xi",
                                "evaluated = min(len(kappas), max_steps) if max_steps > 0 else len(kappas)")
        else:
            line = exact_choice(text, tuple(s for s in text.splitlines(keepends=True)
                                           if "frontier_2_F_net" in s and ("-0.021290" in s or "-0.021291" in s)))
            text = replace_once(text, line, line.replace("-0.021290", "-0.021291"))
            text = patch_function(patch_function(text, "register_supplied_metrics"), "export_pipeline")
        ast.parse(text, filename=str(path))
        planned.append((path, original, text.encode("utf-8")))
    for path, original, updated in planned:
        if original == updated:
            continue
        if path.read_bytes() != original:
            raise RuntimeError(f"File changed during patch preparation: {path}")
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, path.stat().st_mode)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
