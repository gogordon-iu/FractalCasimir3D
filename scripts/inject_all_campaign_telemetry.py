#!/usr/bin/env python3
"""Inject and validate BigRed 200 telemetry in primary campaign batch scripts.

Run from any directory:

    python scripts/inject_all_campaign_telemetry.py
    python scripts/inject_all_campaign_telemetry.py --max-steps 2

The harness must provide ``inject`` and ``validate`` subcommands. Its help output
is inspected to accommodate positional script paths and common path flags.
Each batch file is restored if injection or validation fails.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

MARKER = "# BIGRED200_TELEMETRY_HARNESS_V1"
LOGGER = logging.getLogger("campaign_telemetry")

TARGET_NAMES: tuple[str, ...] = (
    "submit_concentric_ring.sbatch",
    "submit_concentric_ring_plot.sbatch",
    "submit_unified_nature_array.sbatch",
    "submit_unified_nature_analyzer.sbatch",
    "submit_nature_master_pipeline.sbatch",
    "submit_nature_task1_convergence.sbatch",
    "submit_nature_task2_dispersion.sbatch",
    "submit_nature_task3_stability_6dof.sbatch",
    "submit_nature_task4_thermal_matsubara.sbatch",
    "submit_sweet_spot_array.sbatch",
    "submit_sweet_spot_analyzer.sbatch",
    "submit_geometric_repulsion.sbatch",
    "submit_repulsion_campaign.sbatch",
    "submit_rotary_casimir_clutch.sbatch",
    "submit_fractal_rotary_clutch.sbatch",
    "submit_cantor_forest.sbatch",
    "submit_cantor_forest_plot.sbatch",
    "submit_hybrid_sweep_array.sbatch",
    "submit_phase1_baselines.sbatch",
    "submit_phase2_corrugations.sbatch",
    "submit_phase3_sweet_spot.sbatch",
    "submit_postprocess.sbatch",
    "submit_sweep.sbatch",
    "submit_sync.sbatch",
)

# These two scripts do not launch simulations. Plot/analyzer names are handled
# separately below.
NON_SIMULATION_NAMES: frozenset[str] = frozenset(
    {"submit_postprocess.sbatch", "submit_sync.sbatch"}
)


class TelemetryError(RuntimeError):
    """An injection, validation, or safety check failed."""


@dataclass(frozen=True)
class Campaign:
    path: Path
    results_dir: str
    logs_dir: str
    figures_dir: str
    auto_resubmit: bool


@dataclass(frozen=True)
class CommandInterface:
    script_flag: str | None
    options: frozenset[str]
    help_text: str

    def path_arguments(self, path: Path) -> list[str]:
        if self.script_flag is None:
            return [str(path)]
        return [self.script_flag, str(path)]


@dataclass(frozen=True)
class Harness:
    path: Path
    repository: Path
    timeout: float
    inject_interface: CommandInterface
    validate_interface: CommandInterface

    def run(self, subcommand: str, arguments: Sequence[str]) -> str:
        return run_command(
            [sys.executable, str(self.path), subcommand, *arguments],
            cwd=self.repository,
            timeout=self.timeout,
        )

    def inject(self, campaign: Campaign) -> None:
        interface = self.inject_interface
        arguments = interface.path_arguments(campaign.path)
        for flag, value in (
            ("--results-dir", campaign.results_dir),
            ("--logs-dir", campaign.logs_dir),
            ("--figures-dir", campaign.figures_dir),
        ):
            arguments.extend((flag, value))

        arguments.extend(auto_resubmit_arguments(interface, campaign.auto_resubmit))

        # If an output option is advertised, explicitly request an in-place
        # result instead of allowing a separate generated file.
        for output_flag in ("--output", "--output-script", "--output-path"):
            if output_flag in interface.options:
                arguments.extend((output_flag, str(campaign.path)))
                break

        output = self.run("inject", arguments)
        if output.strip():
            LOGGER.info("%s", output.rstrip())

    def validate(self, path: Path) -> None:
        output = self.run("validate", self.validate_interface.path_arguments(path))
        if output.strip():
            LOGGER.info("%s", output.rstrip())


def run_command(
    command: Sequence[str], *, cwd: Path, timeout: float
) -> str:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TelemetryError(
            f"Command exceeded {timeout:g} seconds: {shlex.join(command)}"
        ) from exc
    except OSError as exc:
        raise TelemetryError(
            f"Cannot execute {shlex.join(command)}: {exc}"
        ) from exc

    if completed.returncode != 0:
        raise TelemetryError(
            f"Command failed with exit code {completed.returncode}:\n"
            f"{shlex.join(command)}\n{completed.stdout.rstrip()}"
        )
    return completed.stdout


def inspect_interface(help_text: str, subcommand: str) -> CommandInterface:
    options = frozenset(re.findall(r"--[a-zA-Z][a-zA-Z0-9-]*", help_text))
    script_flag: str | None = None
    for candidate in (
        "--script",
        "--sbatch",
        "--sbatch-path",
        "--script-path",
        "--slurm-script",
        "--batch-script",
        "--input",
    ):
        if candidate in options:
            script_flag = candidate
            break
    else:
        positional_section = re.search(
            r"(?im)^(?:positional arguments|arguments):\s*\n"
            r"(?P<body>(?:[ \t]+[^\n]*\n?)+)",
            help_text,
        )
        positional_names: list[str] = []
        if positional_section is not None:
            for line in positional_section.group("body").splitlines():
                match = re.match(r"^\s{2,}([A-Za-z_][\w-]*)\s*(?:$|\s{2,})", line)
                if match is not None:
                    positional_names.append(match.group(1))

        if len(positional_names) != 1:
            raise TelemetryError(
                f"Cannot safely determine the {subcommand!r} script-path "
                f"argument from harness help:\n{help_text}"
            )

    return CommandInterface(script_flag, options, help_text)


def option_takes_value(interface: CommandInterface, flag: str) -> bool:
    # Inspect only argparse syntax, never description text. In an option
    # listing, two or more spaces separate the declaration from its help.
    declarations: list[str] = []
    for line in interface.help_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("-"):
            declarations.append(re.split(r"[ \t]{2,}", stripped, maxsplit=1)[0])

    usage = re.search(
        r"(?im)^usage:[^\n]*(?:\n[ \t]+[^\n]+)*",
        interface.help_text,
    )
    if usage is not None:
        declarations.append(usage.group(0))

    # Valued options have a metavar or choices after the flag. A store_true
    # flag ends at the declaration or at its usage closing bracket.
    expression = (
        re.escape(flag)
        + r"(?![a-zA-Z0-9-])"
        + r"\s+(?:[A-Z][A-Z0-9_-]*|\{[^}\n]+\}|\[[A-Z][A-Z0-9_-]*\])"
    )
    return any(re.search(expression, declaration) for declaration in declarations)


def auto_resubmit_arguments(
    interface: CommandInterface, enabled: bool
) -> list[str]:
    flag = "--auto-resubmit"
    if flag not in interface.options:
        raise TelemetryError("Harness inject does not advertise --auto-resubmit.")

    # Supply a boolean string only when the option syntax includes a value.
    # Description words following a store_true flag are not metavars.
    if option_takes_value(interface, flag):
        choice_match = re.search(
            re.escape(flag) + r"\s+\{([^}\n]+)\}", interface.help_text
        )
        if choice_match is not None:
            choices = [choice.strip() for choice in choice_match.group(1).split(",")]
            accepted = (
                {"true", "yes", "1", "on"} if enabled
                else {"false", "no", "0", "off"}
            )
            for choice in choices:
                if choice.lower() in accepted:
                    return [flag, choice]
            raise TelemetryError(
                f"No appropriate boolean value in --auto-resubmit choices: {choices}"
            )
        return [flag, "true" if enabled else "false"]

    if enabled:
        return [flag]
    if "--no-auto-resubmit" in interface.options:
        return ["--no-auto-resubmit"]

    # Normal argparse store_true semantics: omission selects False. Refuse
    # an explicitly documented True default, since it cannot be overridden.
    if re.search(
        r"--auto-resubmit[^\n]*(?:default[:=]\s*True)",
        interface.help_text,
        flags=re.IGNORECASE,
    ):
        raise TelemetryError(
            "Harness documents auto-resubmit=True by default but exposes "
            "no way to disable it."
        )
    return []


def discover_harness(repository: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit if explicit.is_absolute() else repository / explicit
        candidate = candidate.resolve()
        if not candidate.is_file():
            raise TelemetryError(f"Harness does not exist: {candidate}")
        return candidate

    candidates = (
        repository / "scripts" / "slurm_telemetry_harness.py",
        repository / "slurm_telemetry_harness.py",
        repository / "execution" / "slurm_telemetry_harness.py",
    )
    matches = [candidate.resolve() for candidate in candidates if candidate.is_file()]
    if not matches:
        raise TelemetryError(
            "Cannot find slurm_telemetry_harness.py; supply --harness PATH."
        )
    if len(set(matches)) > 1:
        raise TelemetryError(
            "Multiple harness files found; select one with --harness PATH:\n"
            + "\n".join(str(path) for path in matches)
        )
    return matches[0]


def build_harness(repository: Path, path: Path, timeout: float) -> Harness:
    interfaces: dict[str, CommandInterface] = {}
    for subcommand in ("inject", "validate"):
        help_text = run_command(
            [sys.executable, str(path), subcommand, "--help"],
            cwd=repository,
            timeout=timeout,
        )
        interfaces[subcommand] = inspect_interface(help_text, subcommand)

    inject_interface = interfaces["inject"]
    required = {"--results-dir", "--logs-dir", "--figures-dir", "--auto-resubmit"}
    missing = required - inject_interface.options
    if missing:
        raise TelemetryError(
            "Harness inject is missing required options: " + ", ".join(sorted(missing))
        )
    for flag in ("--results-dir", "--logs-dir", "--figures-dir"):
        if not option_takes_value(inject_interface, flag):
            raise TelemetryError(f"Cannot determine the value syntax for {flag}.")

    # Verify both settings before modifying any file.
    auto_resubmit_arguments(inject_interface, True)
    auto_resubmit_arguments(inject_interface, False)
    return Harness(path, repository, timeout, inject_interface, interfaces["validate"])


def campaign_for(repository: Path, name: str) -> Campaign:
    lower_name = name.lower()
    if "concentric_ring" in lower_name:
        results_dir = figures_dir = "results_concentric_ring"
    elif "clutch" in lower_name:
        results_dir = figures_dir = "results_clutch"
    else:
        results_dir = "results"
        figures_dir = "Papers/Fractal_Casimir_Nature_EM/figures"

    analysis_only = (
        "plot" in lower_name
        or "analyzer" in lower_name
        or name in NON_SIMULATION_NAMES
    )
    return Campaign(
        path=repository / "execution" / name,
        results_dir=results_dir,
        logs_dir="cluster_diagnostics/raw_logs",
        figures_dir=figures_dir,
        auto_resubmit=not analysis_only,
    )


def read_script(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise TelemetryError(f"Expected a regular, non-symlink batch script: {path}")
    data = path.read_bytes()
    if not data or not data.strip():
        raise TelemetryError(f"Batch script is empty: {path}")
    if b"\x00" in data:
        raise TelemetryError(f"Batch script contains NUL bytes: {path}")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TelemetryError(f"Batch script is not UTF-8: {path}") from exc
    return data


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=str(path.parent), prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def normalize_lf(data: bytes) -> bytes:
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalized if normalized.endswith(b"\n") else normalized + b"\n"


def marker_count(data: bytes) -> int:
    return sum(
        line.strip() == MARKER
        for line in data.decode("utf-8").splitlines()
    )


def standalone_git_command(line: str) -> tuple[str, ...] | None:
    """Identify plain, single-line git commit/push commands only."""
    stripped = line.strip()
    if not stripped.startswith("git "):
        return None
    # Do not rewrite expansions, shell operators, continuations, or commands
    # whose execution is conditional.
    if any(character in stripped for character in ("$", "`", "\\", ";", "|", "&", "<", ">")):
        return None
    try:
        tokens = tuple(shlex.split(stripped, comments=True, posix=True))
    except ValueError:
        return None
    if len(tokens) >= 2 and tokens[0] == "git" and tokens[1] in {"commit", "push"}:
        return tokens
    return None


def clean_duplicate_git_commands(text: str) -> tuple[str, int]:
    """Remove only consecutive identical standalone git commit/push commands.

    No non-adjacent git commands or heredoc contents are rewritten: those may
    have intentional semantics. A shell no-op preserves otherwise-empty blocks.
    """
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    previous: tuple[str, ...] | None = None
    removed = 0

    # Heredocs require shell-aware parsing. Conservatively leave such scripts
    # untouched instead of modifying embedded Python or other literal content.
    if "<<" in text:
        return text, 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            output.append(line)
            continue

        command = standalone_git_command(line)
        if command is not None and command == previous:
            indentation = line[: len(line) - len(line.lstrip())]
            output.append(
                f"{indentation}: # duplicate git {command[1]} removed before telemetry injection\n"
            )
            removed += 1
        else:
            output.append(line)
        previous = command

    return "".join(output), removed


def verify_generated_script(path: Path) -> bytes:
    data = read_script(path)
    if b"\r" in data:
        raise TelemetryError(f"Non-LF line endings remain in {path}")
    if not data.endswith(b"\n"):
        raise TelemetryError(f"Missing final LF in {path}")
    count = marker_count(data)
    if count != 1:
        raise TelemetryError(
            f"Expected exactly one telemetry marker in {path}; found {count}."
        )
    return data


def process_campaign(harness: Harness, campaign: Campaign) -> bool:
    path = campaign.path
    original = read_script(path)
    original_mode = stat.S_IMODE(path.stat().st_mode)
    existing_markers = marker_count(original)
    if existing_markers > 1:
        raise TelemetryError(
            f"{path} already has multiple telemetry markers; repair it before rerunning."
        )

    try:
        if existing_markers == 1:
            LOGGER.info("Already injected; validating %s", path.name)
            # Validate before accepting an existing marker as a successful skip.
            harness.validate(path)
            normalized = normalize_lf(original)
            if normalized != original:
                atomic_write(path, normalized, original_mode)
                LOGGER.info("Normalized line endings: %s", path.name)
                harness.validate(path)
            verify_generated_script(path)
            return False

        normalized = normalize_lf(original)
        cleaned, removed = clean_duplicate_git_commands(normalized.decode("utf-8"))
        prepared = cleaned.encode("utf-8")
        if prepared != original:
            atomic_write(path, prepared, original_mode)
        if removed:
            LOGGER.info("Removed %d duplicate git command(s): %s", removed, path.name)

        LOGGER.info(
            "Injecting %s: results=%s, figures=%s, auto_resubmit=%s",
            path.name,
            campaign.results_dir,
            campaign.figures_dir,
            campaign.auto_resubmit,
        )
        harness.inject(campaign)

        generated = read_script(path)
        normalized_generated = normalize_lf(generated)
        # Preserve original executable/access permissions even if the harness
        # replaced the file.
        if (
            generated != normalized_generated
            or stat.S_IMODE(path.stat().st_mode) != original_mode
        ):
            atomic_write(path, normalized_generated, original_mode)

        verify_generated_script(path)
        harness.validate(path)
        # Validation must not invalidate the checked file.
        verify_generated_script(path)
        return True
    except BaseException:
        try:
            atomic_write(path, original, original_mode)
            LOGGER.error("Restored original file: %s", path.name)
        except OSError as rollback_error:
            LOGGER.critical("Could not restore %s: %s", path, rollback_error)
            raise TelemetryError(
                f"Rollback failed for {path}; original content could not be restored."
            ) from rollback_error
        raise


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return parsed


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (default: parent of this script's directory).",
    )
    parser.add_argument(
        "--harness",
        type=Path,
        help="Harness path, absolute or relative to --repo-root.",
    )
    parser.add_argument(
        "--max-steps",
        type=positive_int,
        default=len(TARGET_NAMES),
        help="Process only the first N target scripts for a micro-probe.",
    )
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=180.0,
        help="Per-harness-command timeout in seconds (default: 180).",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    logging.basicConfig(
        level=logging.DEBUG if arguments.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    try:
        repository = arguments.repo_root.expanduser().resolve()
        if not repository.is_dir():
            raise TelemetryError(f"Repository directory does not exist: {repository}")

        campaigns = [
            campaign_for(repository, name)
            for name in TARGET_NAMES[: arguments.max_steps]
        ]
        if not campaigns:
            raise TelemetryError("No campaign scripts selected.")

        # Preflight every selected target before modifying the first one.
        for campaign in campaigns:
            data = read_script(campaign.path)
            if marker_count(data) > 1:
                raise TelemetryError(
                    f"Multiple telemetry markers found in {campaign.path}."
                )

        explicit_harness = arguments.harness
        if explicit_harness is not None:
            explicit_harness = explicit_harness.expanduser()
        harness_path = discover_harness(repository, explicit_harness)
        harness = build_harness(repository, harness_path, arguments.timeout)

        injected = 0
        skipped = 0
        for campaign in campaigns:
            if process_campaign(harness, campaign):
                injected += 1
            else:
                skipped += 1

        # Final LF/marker verification covers every selected script, including
        # scripts that were already injected.
        for campaign in campaigns:
            verify_generated_script(campaign.path)

        LOGGER.info(
            "Completed: %d injected, %d already injected and validated; "
            "%d scripts verified with LF line endings.",
            injected,
            skipped,
            len(campaigns),
        )
        return 0
    except KeyboardInterrupt:
        LOGGER.error("Interrupted; the active script was restored.")
        return 130
    except (TelemetryError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
