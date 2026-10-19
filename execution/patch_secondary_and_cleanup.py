#!/usr/bin/env python3
"""Apply the six final publication-cleanup phases, in deterministic order."""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

MEEP_TO_PA_TEXT = "0.0316152649"
CITED_KEYS = frozenset(
    (
        "akkermans2010",
        "alexanderorbach1982",
        "bethe1947",
        "bordag2009",
        "brownmaclay1969",
        "casimir1948",
        "casimirpolder1948",
        "kajino2010",
        "kigami2001",
        "lapidus1991",
        "lodahl2015",
        "milton2004delta",
        "milton2016",
        "oskooi2010",
        "parthey2011",
        "purcell1946",
        "rodriguez2011",
        "safronova2018",
        "shajesh2016",
        "shajesh2017",
    )
)
BIB_ENTRY_RE = re.compile(r"@\w+\{\s*([^,\s]+)\s*,")
PAPER = Path("Papers/Fractal_Casimir_Nature_EM")
FIGURE_PATTERNS = (
    "figure1_architecture_schematic*",
    "figure2_1d_pressure_curves*",
    "figure3_2d_phase_diagram*",
    "fig1_tip_convergence*",
    "fig2_levitation_curves*",
    "fig3_phase_diagram*",
    "fig_repulsion_screening*",
    "fig_quantum_clutch_characteristic*",
)
TABLE_NAMES = (
    "table_scaling_models.tex",
    "table_sweet_spots.tex",
    "table_1d_theta_alpha.tex",
    "table_2d_theta_alpha.tex",
    "table_1d_theta_d.tex",
    "table_2d_theta_d.tex",
)


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes
    after: bytes | None
    mode: int


def read_regular(path: Path) -> tuple[bytes, int]:
    if path.is_symlink():
        raise ValueError(f"Refusing to modify a symbolic link: {path}")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"Expected a regular file: {path}")
    return path.read_bytes(), stat.S_IMODE(metadata.st_mode)


class Planner:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.changes: dict[Path, Change] = {}

    def path(self, relative: Path | str) -> Path:
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe repository-relative path: {relative}")
        path = self.root / relative
        for parent in (path.parent, *path.parent.parents):
            if parent == self.root:
                break
            if parent.is_symlink():
                raise ValueError(f"Refusing symbolic-link directory: {parent}")
        return path

    def text(self, relative: Path | str) -> str:
        path = self.path(relative)
        existing = self.changes.get(path)
        if existing is not None:
            if existing.after is None:
                raise ValueError(f"File is already scheduled for deletion: {path}")
            return existing.after.decode("utf-8")
        return read_regular(path)[0].decode("utf-8")

    def write(self, relative: Path | str, text: str) -> None:
        path = self.path(relative)
        existing = self.changes.get(path)
        if existing is None:
            before, mode = read_regular(path)
        else:
            before, mode = existing.before, existing.mode
        after = text.encode("utf-8")
        if after == before:
            self.changes.pop(path, None)
        else:
            self.changes[path] = Change(path, before, after, mode)

    def delete(self, relative: Path | str) -> None:
        path = self.path(relative)
        if not path.exists() and not path.is_symlink():
            return
        before, mode = read_regular(path)
        self.changes[path] = Change(path, before, None, mode)


def bib_entry_end(text: str, start: int) -> int:
    opening = text.find("{", start)
    if opening < 0:
        raise ValueError("BibTeX entry has no opening brace")
    depth = 0
    escaped = False
    comment = False
    for index in range(opening, len(text)):
        character = text[index]
        if comment:
            if character in "\r\n":
                comment = False
            continue
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == "%":
            comment = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError(f"Unterminated BibTeX entry at character {start}")


def clean_bibliography(planner: Planner, _: str) -> None:
    planner.text(PAPER / "nature_fractal_casimir_em.tex")
    relative = PAPER / "references.bib"
    text = planner.text(relative)
    retained: dict[str, str] = {}
    cursor = 0
    while (match := BIB_ENTRY_RE.search(text, cursor)) is not None:
        end = bib_entry_end(text, match.start())
        key = match.group(1)
        if key in CITED_KEYS and key not in retained:
            retained[key] = text[match.start():end].strip()
        cursor = end
    missing = CITED_KEYS - retained.keys()
    if missing:
        raise ValueError(f"Missing required bibliography entries: {', '.join(sorted(missing))}")
    cleaned = "\n\n".join(retained.values()) + "\n"
    keys = BIB_ENTRY_RE.findall(cleaned)
    if len(keys) != 20 or len(set(keys)) != 20 or set(keys) != CITED_KEYS:
        raise ValueError("Bibliography verification failed")
    planner.write(relative, cleaned)


def clean_report(planner: Planner, _: str) -> None:
    relative = Path("results/rotational_clutch_3solver_verification_report.md")
    lines = planner.text(relative).splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == "## Hybrid Multi-Scale Active-Zone vs Full-Monolithic":
            planner.write(relative, "".join(lines[:index]))
            return


def delete_orphans(planner: Planner, _: str) -> None:
    candidates: set[Path] = set()
    figure_dir = planner.path(PAPER / "figures")
    for pattern in FIGURE_PATTERNS:
        candidates.update(figure_dir.glob(pattern))
    candidates.update(planner.path("figures").glob("demo_loss*"))
    candidates.update(planner.path(PAPER / "tables" / name) for name in TABLE_NAMES)
    for path in sorted(candidates, key=lambda value: value.as_posix()):
        if path.is_dir() and not path.is_symlink():
            raise ValueError(f"Orphan file pattern unexpectedly matched a directory: {path}")
        planner.delete(path.relative_to(planner.root))


def parse_python(text: str, relative: Path) -> ast.Module:
    return ast.parse(text, filename=str(relative))


def offsets(text: str) -> list[int]:
    result = [0]
    for line in text.splitlines(keepends=True):
        result.append(result[-1] + len(line))
    return result


def node_span(text: str, node: ast.AST) -> tuple[int, int]:
    if (
        not hasattr(node, "lineno")
        or node.end_lineno is None
        or node.end_col_offset is None
    ):
        raise ValueError("AST node has no source location")
    lines = text.splitlines(keepends=True)
    starts = offsets(text)

    def position(line_number: int, byte_column: int) -> int:
        prefix = lines[line_number - 1].encode("utf-8")[:byte_column].decode("utf-8")
        return starts[line_number - 1] + len(prefix)

    return (
        position(node.lineno, node.col_offset),
        position(node.end_lineno, node.end_col_offset),
    )


def edit_source(text: str, edits: Sequence[tuple[int, int, str]]) -> str:
    ordered = sorted(edits, key=lambda edit: (edit[0], edit[1]))
    previous_end = -1
    for start, end, _ in ordered:
        if start < previous_end or start < 0 or end < start or end > len(text):
            raise ValueError("Invalid or overlapping source edits")
        previous_end = end
    for start, end, replacement in reversed(ordered):
        text = text[:start] + replacement + text[end:]
    return text


def patch_constant(text: str, relative: Path, *, add: bool = False) -> str:
    tree = parse_python(text, relative)
    assignments: list[ast.AST] = []
    for node in ast.walk(tree):
        targets: list[ast.expr]
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == "MEEP_TO_PA" for target in targets):
            if node.value is None:
                raise ValueError(f"Uninitialized MEEP_TO_PA in {relative}")
            assignments.append(node.value)

    if assignments:
        edits: list[tuple[int, int, str]] = []
        for value in assignments:
            if not isinstance(value, ast.Constant) or isinstance(value.value, bool):
                raise ValueError(f"Unexpected MEEP_TO_PA expression in {relative}")
            if not isinstance(value.value, (int, float)) or not math.isfinite(value.value):
                raise ValueError(f"Invalid MEEP_TO_PA value in {relative}")
            if value.value not in (0.03161, 0.031615, float(MEEP_TO_PA_TEXT)):
                raise ValueError(f"Unexpected MEEP_TO_PA value in {relative}: {value.value!r}")
            start, end = node_span(text, value)
            edits.append((start, end, MEEP_TO_PA_TEXT))
        return edit_source(text, edits)

    if not add:
        raise ValueError(f"MEEP_TO_PA assignment not found in {relative}")

    insertion = 0
    for index, node in enumerate(tree.body):
        is_docstring = (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
        is_import = isinstance(node, (ast.Import, ast.ImportFrom))
        if is_docstring or is_import:
            assert node.end_lineno is not None
            insertion = offsets(text)[node.end_lineno]
        else:
            break
    if insertion == 0 and tree.body:
        insertion = offsets(text)[tree.body[0].lineno - 1]
    return text[:insertion] + f"\nMEEP_TO_PA = {MEEP_TO_PA_TEXT}\n\n" + text[insertion:]


def patch_pfa(text: str, relative: Path) -> str:
    text = patch_constant(text, relative, add=True)
    tree = parse_python(text, relative)
    edits: list[tuple[int, int, str]] = []
    matched = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        if not any(
            isinstance(key, ast.Constant)
            and key.value == "force_val"
            and isinstance(value, ast.Name)
            and value.id == "force"
            for key, value in zip(node.keys, node.values, strict=True)
        ):
            continue
        matched += 1
        fields: dict[str, ast.expr] = {}
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in fields:
                    raise ValueError(f"Duplicate result key {key.value!r} in {relative}")
                fields[key.value] = value
        additions: list[str] = []
        for key, expression in (
            ("pressure_Pa", "float(f_dens * MEEP_TO_PA)"),
            ("force_pN", "float(force * MEEP_TO_PA)"),
        ):
            if key in fields:
                start, end = node_span(text, fields[key])
                edits.append((start, end, expression))
            else:
                additions.append(f"{key!r}: {expression}")
        if additions:
            _, end = node_span(text, node)
            insertion = end - 1
            prefix = text[node_span(text, node)[0]:insertion].rstrip()
            separator = "" if prefix.endswith(("{", ",")) else ","
            edits.append((insertion, insertion, separator + " " + ", ".join(additions) + ", "))
    if matched == 0:
        raise ValueError(
            f"No literal result dictionary with force_val: force found in {relative}; "
            "refusing to guess where pressure fields belong"
        )
    result = edit_source(text, edits)
    parse_python(result, relative)
    return result


def patch_units(planner: Planner, _: str) -> None:
    for name in (
        "run_anisotropic_dispersive_lifshitz.py",
        "run_thermal_matsubara_dsi.py",
        "serialize_clutch_results.py",
    ):
        relative = Path("execution") / name
        result = patch_constant(planner.text(relative), relative)
        parse_python(result, relative)
        planner.write(relative, result)
    relative = Path("execution/run_pfa_model.py")
    planner.write(relative, patch_pfa(planner.text(relative), relative))


def is_scaled_test(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Call)
        and isinstance(node.left.func, ast.Attribute)
        and isinstance(node.left.func.value, ast.Name)
        and node.left.func.value.id == "r"
        and node.left.func.attr == "get"
        and bool(node.left.args)
        and isinstance(node.left.args[0], ast.Constant)
        and node.left.args[0].value == "pressure_scaled"
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Is)
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is True
    )


def patch_pressure_branch(text: str, relative: Path) -> str:
    tree = parse_python(text, relative)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    edits: list[tuple[int, int, str]] = []
    recognized = 0
    raw_expression = "raw_pressure * MEEP_TO_PA"
    scaled_expression = (
        'raw_pressure if r.get("pressure_scaled") is True '
        'and "pressure_meep" not in r else raw_pressure * MEEP_TO_PA'
    )
    raw_ast = ast.dump(ast.parse(raw_expression, mode="eval").body)
    scaled_ast = ast.dump(ast.parse(scaled_expression, mode="eval").body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if (
                node.value is not None
                and any(
                    isinstance(target, ast.Name) and target.id == "p_pa"
                    for target in targets
                )
            ):
                expression_ast = ast.dump(node.value)
                if expression_ast == scaled_ast:
                    recognized += 1
                    continue
                if expression_ast == raw_ast:
                    recognized += 1
                    start, end = node_span(text, node.value)
                    edits.append((start, end, scaled_expression))
                    continue
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "p_meep"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.IsNot)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        ):
            continue
        if not (
            len(node.body) == 1
            and isinstance(node.body[0], ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "p_pa"
                for target in node.body[0].targets
            )
        ):
            continue
        recognized += 1
        parent = parents.get(node)
        if isinstance(parent, ast.If) and is_scaled_test(parent.test):
            continue
        if len(node.orelse) != 1 or not isinstance(node.orelse[0], ast.Assign):
            raise ValueError(f"Unexpected pressure fallback structure in {relative}")
        fallback = node.orelse[0]
        if not any(isinstance(target, ast.Name) and target.id == "p_pa" for target in fallback.targets):
            raise ValueError(f"Unexpected pressure fallback assignment in {relative}")
        start, end = node_span(text, node)
        line_start = text.rfind("\n", 0, start) + 1
        indent = text[line_start:start]
        if indent.strip():
            raise ValueError(f"Unsupported inline pressure branch in {relative}")
        replacement = (
            'if r.get("pressure_scaled") is True:\n'
            f'{indent}    p_pa = float(r.get("pressure_Pa", 0.0))\n'
            f"{indent}elif p_meep is not None:\n"
            f"{indent}    p_pa = float(p_meep) * MEEP_TO_PA\n"
            f"{indent}else:\n"
            f'{indent}    p_pa = float(r.get("pressure_Pa", 0.0)) * MEEP_TO_PA'
        )
        edits.append((start, end, replacement))
    if recognized == 0:
        raise ValueError(f"Pressure conversion branch not found in {relative}")
    result = edit_source(text, edits)
    parse_python(result, relative)
    return result


def patch_pipelines(planner: Planner, _: str) -> None:
    old_imports = (
        "from utils.provenance import save_plot_provenance",
        "from utils.plot_provenance import save_plot_provenance",
    )
    new = "from utils.metrics_logger import save_plot_provenance"
    for name in (
        "pipeline1_3d_tensor_mapper.py",
        "pipeline2_ricci_curvature_analyzer.py",
        "pipeline3_nec_boundary_mapper.py",
    ):
        relative = Path("quantum_gravity_trace_analysis") / name
        text = planner.text(relative)
        if not any(old in text for old in old_imports) and new not in text:
            raise ValueError(f"Expected provenance import not found in {relative}")
        for old in old_imports:
            text = text.replace(old, new)
        if name == "pipeline3_nec_boundary_mapper.py":
            text = patch_pressure_branch(text, relative)
        parse_python(text, relative)
        planner.write(relative, text)


def reject_constant(value: str) -> Any:
    raise ValueError(f"Non-finite JSON number: {value}")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def refresh_nested(value: Any, timestamp: str) -> None:
    if isinstance(value, dict):
        for key in ("executed_at", "timestamp"):
            if key in value:
                value[key] = timestamp
        for child in value.values():
            refresh_nested(child, timestamp)
    elif isinstance(value, list):
        for child in value:
            refresh_nested(child, timestamp)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numeric value in JSON")


def refresh_timestamps(planner: Planner, timestamp: str) -> None:
    paths = [planner.path("results/top_repulsive_verification_report.json")]
    scan_dir = planner.path("results/ztip_scan_th0")
    if not scan_dir.is_dir():
        raise ValueError(f"Missing scan directory: {scan_dir}")
    paths.extend(sorted(scan_dir.glob("*.json"), key=lambda path: path.name))
    for path in paths:
        relative = path.relative_to(planner.root)
        value = json.loads(
            planner.text(relative),
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
        if not isinstance(value, (dict, list)):
            raise ValueError(f"Expected a JSON object or record list in {relative}")
        refresh_nested(value, timestamp)
        records = [value] if isinstance(value, dict) else value
        if not records:
            raise ValueError(f"Empty record collection in {relative}")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"Non-object JSON record in {relative}")
            record["executed_at"] = timestamp
            record["timestamp"] = timestamp
        planner.write(
            relative,
            json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        )


def atomic_write(path: Path, content: bytes, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.cleanup-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def apply_changes(changes: Sequence[Change]) -> None:
    for change in changes:
        current, mode = read_regular(change.path)
        if current != change.before or mode != change.mode:
            raise ValueError(f"File changed while cleanup was being planned: {change.path}")
    applied: list[Change] = []
    try:
        for change in changes:
            if change.after is None:
                change.path.unlink()
            else:
                atomic_write(change.path, change.after, change.mode)
            applied.append(change)
    except BaseException as original:
        rollback_errors: list[str] = []
        for change in reversed(applied):
            try:
                atomic_write(change.path, change.before, change.mode)
            except Exception as error:
                rollback_errors.append(f"{change.path}: {error}")
        if rollback_errors:
            raise RuntimeError(
                "Cleanup failed and rollback was incomplete: " + "; ".join(rollback_errors)
            ) from original
        raise


def utc_timestamp(value: str | None) -> str:
    if value is None:
        instant = datetime.now(timezone.utc)
    else:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("--timestamp must include a UTC offset")
        instant = instant.astimezone(timezone.utc)
    return instant.isoformat(timespec="microseconds").replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root; defaults to the parent of execution/.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=6,
        help="Run the first N cleanup phases, from 0 through 6 (default: 6).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and display changes only.")
    parser.add_argument(
        "--timestamp",
        help="Optional timezone-aware ISO timestamp for reproducible runs; default: current UTC.",
    )
    args = parser.parse_args(argv)
    if not 0 <= args.max_steps <= 6:
        parser.error("--max-steps must be between 0 and 6")
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"Repository root is not a directory: {root}")
    try:
        timestamp = utc_timestamp(args.timestamp)
        planner = Planner(root)
        phases: tuple[Callable[[Planner, str], None], ...] = (
            clean_bibliography,
            clean_report,
            delete_orphans,
            patch_units,
            patch_pipelines,
            refresh_timestamps,
        )
        for phase in phases[:args.max_steps]:
            phase(planner, timestamp)
        changes = sorted(
            planner.changes.values(),
            key=lambda change: change.path.relative_to(root).as_posix(),
        )
        if not args.dry_run:
            apply_changes(changes)
        for change in changes:
            action = "DELETE" if change.after is None else "UPDATE"
            print(f"{'DRY-RUN ' if args.dry_run else ''}{action} {change.path.relative_to(root).as_posix()}")
        print(
            f"{'Validated' if args.dry_run else 'Completed'} "
            f"{args.max_steps}/6 phases; {len(changes)} file changes."
        )
        return 0
    except (OSError, ValueError, SyntaxError, RuntimeError) as error:
        print(f"Cleanup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
