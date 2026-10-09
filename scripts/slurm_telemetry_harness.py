#!/usr/bin/env python3
"""
slurm_telemetry_harness.py -- Standard-library-only Slurm/Git telemetry.

Generated scripts are self-contained and require bash, python3, and git on the
compute node. Git authentication must already support unattended pushes.

Important operational limits:
* SIGKILL, node loss, and an OOM kill of the batch shell cannot be trapped.
* A pre-walltime signal provides a best-effort opportunity, not a guarantee.
* Network/authentication failures cannot guarantee delivery to the remote.
* Slurm opens output files before starting bash. Create the configured log
  directory in the submission working directory BEFORE running sbatch.
* Injection executes the original body in a supervised bash subshell. Its
  traps cannot replace the supervisor's traps.
* Output verification means a real results directory containing at least one
  nonempty regular file. Application-specific correctness is not inferred.
* Continuation markers suppress publication; they do not guarantee that a
  replacement job was successfully submitted.

Python 3.9+.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple


MARKER = "# BIGRED200_TELEMETRY_HARNESS_V1"
BLOCKED_SUFFIXES = (".pt", ".ckpt", ".bin", ".h5", ".safetensors", ".tar")
PROXY = "http://proxy.uits.iu.edu:3128"


# Embedded verbatim into generated scripts; it does not import this module.
_TELEMETRY_PYTHON = r'''
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

CONFIG = json.loads(__HARNESS_CONFIG__)
BLOCKED_SUFFIXES = (".pt", ".ckpt", ".bin", ".h5", ".safetensors", ".tar")
GIT_TIMEOUT_SECONDS = 45

def diagnostic(message):
    print("[BigRed200 telemetry] " + str(message), file=sys.stderr, flush=True)

def run(command, check=True):
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_EDITOR"] = ":"
    environment["GIT_SEQUENCE_EDITOR"] = ":"
    result = subprocess.run(
        command, cwd=str(ROOT), env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace", timeout=GIT_TIMEOUT_SECONDS,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "{} failed ({}): {}".format(
                command[0:2], result.returncode,
                (result.stderr or result.stdout).strip()[-6000:],
            )
        )
    return result

def git(arguments, check=True):
    return run(["git"] + arguments, check=check)

def safe_path(relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("Unsafe repository-relative path: " + str(relative))
    current = ROOT
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Refusing symlink path: " + str(current))
    resolved = current.resolve()
    if resolved != ROOT and ROOT not in resolved.parents:
        raise ValueError("Path escapes repository: " + str(relative))
    if ".git" in path.parts:
        raise ValueError("Refusing Git metadata path")
    return current

def safe_file(path):
    if path.is_symlink() or not path.is_file():
        return False
    relative = path.relative_to(ROOT)
    safe_path(str(relative))
    # Exclude checkpoints even when compression/other suffixes are appended.
    if any(suffix.lower() in BLOCKED_SUFFIXES for suffix in path.suffixes):
        return False
    return True

def collect(directory):
    base = safe_path(directory)
    files = []
    if not base.exists():
        return files
    if not base.is_dir():
        raise ValueError("Expected directory: " + str(base))
    for current, directories, names in os.walk(str(base), followlinks=False):
        parent = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name != ".git" and not (parent / name).is_symlink()
        )
        for name in sorted(names):
            path = parent / name
            if safe_file(path):
                files.append(str(path.relative_to(ROOT)))
    return files

def outputs_verified(directory):
    base = safe_path(directory)
    if not base.is_dir():
        return False
    for current, directories, names in os.walk(str(base), followlinks=False):
        parent = Path(current)
        directories[:] = [
            name for name in directories
            if name != ".git" and not (parent / name).is_symlink()
        ]
        for name in names:
            path = parent / name
            if not path.is_symlink() and path.is_file() and path.stat().st_size > 0:
                return True
    return False

def write_report(report):
    destination = safe_path(CONFIG["logs_dir"]) / ("crash_report_" + JOB_ID + ".json")
    if destination.is_symlink():
        raise ValueError("Refusing symlink crash report")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp." + str(os.getpid()))
    descriptor = os.open(
        str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(destination))
    finally:
        if temporary.exists():
            temporary.unlink()
    return str(destination.relative_to(ROOT))

def publish(paths, message):
    selected = sorted(set(paths))
    for relative in selected:
        if not safe_file(safe_path(relative)):
            raise ValueError("Unsafe staging candidate: " + relative)

    git(["config", "user.name"], check=False)
    if git(["config", "--get", "user.name"], check=False).returncode != 0:
        git(["config", "user.name", "BigRed200-JobRunner"])
    if git(["config", "--get", "user.email"], check=False).returncode != 0:
        git(["config", "user.email", "bigred200@iu.edu"])

    branch = git(["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    if branch.returncode != 0 or not branch.stdout.strip():
        raise RuntimeError("Detached HEAD: refusing to guess a push branch")
    current_branch = branch.stdout.strip()
    git(["check-ref-format", "--branch", current_branch])
    git(["remote", "get-url", "--", CONFIG["git_remote"]])

    # Stage only enumerated files; never recursively `git add` a directory.
    # -f permits required diagnostics in repositories that ignore logs/results.
    for offset in range(0, len(selected), 100):
        git(["add", "-f", "--"] + selected[offset:offset + 100])

    # Refuse to commit pre-existing staged files unrelated to this job.
    staged = git(["diff", "--cached", "--name-only", "-z"]).stdout
    staged_paths = [name for name in staged.split("\0") if name]
    unrelated = sorted(set(staged_paths) - set(selected))
    if unrelated:
        raise RuntimeError(
            "Unrelated staged changes; refusing mixed commit: "
            + ", ".join(unrelated[:20])
        )
    for relative in staged_paths:
        if any(s.lower() in BLOCKED_SUFFIXES for s in Path(relative).suffixes):
            raise RuntimeError("Checkpoint staging safety violation: " + relative)

    if staged_paths:
        git(["commit", "-m", message])
    else:
        diagnostic("No new safe changes to commit; attempting synchronization.")

    # A dirty worktree can make pull fail even when a push remains possible.
    pulled = git(["pull", "--rebase", CONFIG["git_remote"], current_branch], check=False)
    if pulled.returncode != 0:
        diagnostic("git pull --rebase failed: " + pulled.stderr.strip()[-3000:])
        git_directory = Path(git(["rev-parse", "--absolute-git-dir"]).stdout.strip())
        if (git_directory / "rebase-merge").exists() or (git_directory / "rebase-apply").exists():
            raise RuntimeError("Rebase conflict; resolve manually before pushing")
    git(["push", CONFIG["git_remote"], current_branch])

def continuation_detected(code, reason):
    submit_directory = Path(os.environ.get("SLURM_SUBMIT_DIR") or str(ROOT)).resolve()
    sentinel_job_id = os.environ.get("SLURM_JOB_ID") or "local"
    sentinels = (
        submit_directory / (".resubmit_" + sentinel_job_id),
        submit_directory / ".slurm_resubmitted",
    )
    continuing = (
        reason in ("RESUBMITTED", "JOB_CHAINED", "REQUEUED")
        or code == 99
        or os.environ.get("RESUBMITTED") == "1"
        or os.environ.get("SLURM_JOB_RESUBMITTED") == "1"
        or any(path.exists() for path in sentinels)
    )
    if not continuing:
        return False
    diagnostic(
        "Job resubmitted/chained (task continuing). "
        "Skipping Git commit, push, and crash reporting."
    )
    for path in sentinels:
        try:
            # unlink never follows a symlink or recursively removes a directory.
            if path.is_symlink() or path.is_file():
                path.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            diagnostic("Could not remove continuation sentinel: " + str(error))
    return True

def main():
    global ROOT, JOB_ID
    ROOT = Path.cwd().resolve()
    JOB_ID = os.environ.get("SLURM_JOB_ID", "local_" + str(os.getppid()))
    if not JOB_ID or not all(c.isalnum() or c in "_.-" for c in JOB_ID):
        raise ValueError("Unsafe SLURM_JOB_ID")

    code = int(sys.argv[1])
    reason = sys.argv[2]
    if code < 0 or code > 255:
        raise ValueError("Exit code outside shell range")
    if continuation_detected(code, reason):
        return 0

    name = os.environ.get("SLURM_JOB_NAME", "bigred_job")
    if "/" in name or "\\" in name or "\0" in name:
        raise ValueError("Unsafe SLURM_JOB_NAME")

    logs = safe_path(CONFIG["logs_dir"])
    logs.mkdir(parents=True, exist_ok=True)
    stdout_log = logs / (name + "_" + JOB_ID + ".out")
    stderr_log = logs / (name + "_" + JOB_ID + ".err")
    verified = outputs_verified(CONFIG["results_dir"])
    if code == 0 and not verified:
        code = 66
        reason = "MISSING_OR_EMPTY_OUTPUTS"
    elif code == 0:
        reason = "SUCCESS"
    elif reason == "UNEXPECTED_EXIT":
        reason = "NONZERO_EXIT"

    report = {
        "schema_version": 1,
        "job_id": JOB_ID,
        "job_name": name,
        "exit_code": code,
        "termination_reason": reason,
        "started_at": os.environ.get("JOB_START_TIME", ""),
        "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": os.uname().nodename,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "results_dir": str(safe_path(CONFIG["results_dir"])),
        "outputs_verified": verified,
        "slurm": {
            key: os.environ.get(key, "")
            for key in (
                "SLURM_JOB_ID", "SLURM_JOB_NAME", "SLURM_JOB_NODELIST",
                "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID", "SLURM_SUBMIT_DIR",
            )
        },
        "telemetry_errors": [],
    }
    paths = []
    if code == 0:
        paths.extend(collect(CONFIG["results_dir"]))
        paths.extend(collect(CONFIG["figures_dir"]))
        paths.extend(collect(CONFIG["logs_dir"]))
        message = "[BigRed200] SUCCESS: Job {} ({}) on {}".format(
            JOB_ID, name, report["hostname"]
        )
    else:
        paths.append(write_report(report))
        message = "[BigRed200] FAILED: Job {} ({}) exit code {} [{}]".format(
            JOB_ID, name, code, reason
        )
    for log in (stdout_log, stderr_log):
        if safe_file(log):
            paths.append(str(log.relative_to(ROOT)))

    try:
        repository = Path(git(["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
        if repository != ROOT:
            raise RuntimeError("Submit from the repository root, not a subdirectory")
        publish(paths, message)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        diagnostic(error)
        report["telemetry_errors"].append(str(error))
        if code == 0:
            code = 74
            report["exit_code"] = code
            report["termination_reason"] = "TELEMETRY_FAILURE"
        report["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            write_report(report)
        except (OSError, ValueError) as report_error:
            diagnostic("Could not persist telemetry failure: " + str(report_error))
    return code

try:
    sys.exit(main())
except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
    diagnostic("Fatal telemetry error: " + str(error))
    sys.exit(74)
'''


def shell_quote(value: str) -> str:
    """Quote one literal argument for POSIX/bash shells."""
    if "\0" in value:
        raise ValueError("Shell arguments cannot contain NUL")
    return "'" + value.replace("'", "'\"'\"'") + "'"


def split_arguments(value: str) -> List[str]:
    """Parse literal shell-style words without expansion or command execution."""
    words: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None
    active = False
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\0":
            raise ValueError("--script-args contains NUL")
        if quote == "'":
            if character == "'":
                quote = None
            else:
                current.append(character)
        elif character == "\\":
            index += 1
            if index >= len(value):
                raise ValueError("Trailing backslash in --script-args")
            following = value[index]
            if quote == '"' and following not in '$`"\\\n':
                current.append("\\")
            if following != "\n":
                current.append(following)
            active = True
        elif quote == '"':
            if character == '"':
                quote = None
            else:
                current.append(character)
        elif character in ("'", '"'):
            quote = character
            active = True
        elif character.isspace():
            if active:
                words.append("".join(current))
                current = []
                active = False
        else:
            current.append(character)
            active = True
        index += 1
    if quote is not None:
        raise ValueError("Unterminated quote in --script-args")
    if active:
        words.append("".join(current))
    return words


def relative_directory(value: str) -> str:
    """Require unambiguous, repository-relative paths usable in SBATCH lines."""
    if not value or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError("Directory must contain only letters, digits, _, ., /, -")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise ValueError("Directories must be repository-relative and outside .git")
    if not path.parts or str(path) == ".":
        raise ValueError("Use a dedicated directory, not the repository root")
    return path.as_posix()


def configuration(namespace: argparse.Namespace) -> Dict[str, str]:
    remote = namespace.git_remote
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", remote):
        raise ValueError("--git-remote must be a remote name, not a URL or option")
    config = {
        "results_dir": relative_directory(namespace.results_dir),
        "figures_dir": relative_directory(namespace.figures_dir),
        "logs_dir": relative_directory(namespace.logs_dir),
        "git_remote": remote,
        "auto_resubmit": "1" if getattr(namespace, "auto_resubmit", False) else "0",
    }
    if config["logs_dir"] == config["results_dir"]:
        raise ValueError("Logs and results must use different directories")
    results = Path(config["results_dir"])
    logs = Path(config["logs_dir"])
    if results in logs.parents or logs in results.parents:
        raise ValueError("Logs and results directories must not contain each other")
    return config


def prepare_logs(value: str) -> None:
    root = Path.cwd().resolve()
    current = root
    for part in Path(value).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Refusing symlink log directory: " + str(current))
    current.mkdir(parents=True, exist_ok=True)


def harness_body(body: str, config: Dict[str, str]) -> str:
    payload = _TELEMETRY_PYTHON.replace(
        "__HARNESS_CONFIG__", repr(json.dumps(config, sort_keys=True))
    ).strip()
    logs = shell_quote(config["logs_dir"])
    auto_walltime = ""
    if config.get("auto_resubmit", "0") == "1":
        auto_walltime = (
            '    printf "%s\\n" "[BigRed200] Auto-resubmitting continuation job due to walltime..." >&2\n'
            '    if [[ -n "${SLURM_JOB_SCRIPT:-}" ]]; then\n'
            '        resubmit_job "$SLURM_JOB_SCRIPT" || true\n'
            "    else\n"
            "        resubmit_job || true\n"
            "    fi\n"
            '    TERMINATION_REASON="RESUBMITTED"\n'
            "    exit 0\n"
        )
    return (
        f"{MARKER}\n"
        "# SIGKILL/node loss cannot be trapped; publication is best-effort.\n"
        "# Logs must exist BEFORE sbatch; the generator creates them locally.\n"
        'export http_proxy="http://proxy.uits.iu.edu:3128"\n'
        'export https_proxy="http://proxy.uits.iu.edu:3128"\n'
        'export no_proxy="localhost,127.0.0.1,*.iu.edu,*.uits.iu.edu"\n'
        "export HF_HUB_OFFLINE=1\n"
        "export TRANSFORMERS_OFFLINE=1\n"
        "export WANDB_MODE=offline\n"
        'export TORCH_HOME="${SLATE:-/N/slate/$USER}/.cache/torch"\n'
        'export JOB_START_TIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"\n'
        'TERMINATION_REASON="UNEXPECTED_EXIT"\n'
        'CHILD_PID=""\n'
        "\n"
        "resubmit_job() {\n"
        '    echo "[BigRed200] Registering job continuation/resubmission..."\n'
        '    touch -- "${SLURM_SUBMIT_DIR:-$PWD}/.resubmit_${SLURM_JOB_ID:-local}" || return $?\n'
        "    export RESUBMITTED=1\n"
        "    if [[ $# -gt 0 ]]; then\n"
        '        sbatch "$@"\n'
        "    fi\n"
        "}\n"
        "export -f resubmit_job 2>/dev/null || true\n"
        "\n"
        "terminate_child_group() {\n"
        '    if [[ -n "${CHILD_PID:-}" ]]; then\n'
        '        kill -15 -- "-${CHILD_PID}" 2>/dev/null || true\n'
        "    fi\n"
        "}\n"
        "\n"
        "handle_job_exit() {\n"
        "    local EXIT_CODE=$?\n"
        '    if [[ $# -gt 0 ]]; then EXIT_CODE="$1"; fi\n'
        "    trap - EXIT ERR SIGTERM SIGINT SIGUSR1\n"
        "    set +e\n"
        "    terminate_child_group\n"
        "    sync || true\n"
        '    if [[ -f "${SLURM_SUBMIT_DIR:-$PWD}/.resubmit_${SLURM_JOB_ID:-local}"\n'
        '          || -e "${SLURM_SUBMIT_DIR:-$PWD}/.slurm_resubmitted"\n'
        '          || "${RESUBMITTED:-0}" == "1"\n'
        '          || "${SLURM_JOB_RESUBMITTED:-0}" == "1"\n'
        '          || "$EXIT_CODE" -eq 99\n'
        '          || "$TERMINATION_REASON" == "RESUBMITTED"\n'
        '          || "$TERMINATION_REASON" == "JOB_CHAINED"\n'
        '          || "$TERMINATION_REASON" == "REQUEUED" ]]; then\n'
        '        TERMINATION_REASON="RESUBMITTED"\n'
        "        EXIT_CODE=0\n"
        "    fi\n"
        '    if [[ "$TERMINATION_REASON" != "RESUBMITTED" ]]; then\n'
        "        (\n"
        "            git config user.name >/dev/null 2>&1 || "
        'git config user.name "BigRed200-JobRunner"\n'
        "            git config user.email >/dev/null 2>&1 || "
        'git config user.email "bigred200@iu.edu"\n'
        '            CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")\n'
        "            export CURRENT_BRANCH\n"
        "        )\n"
        "    fi\n"
        '    python3 - "$EXIT_CODE" "$TERMINATION_REASON" <<\'BIGRED200_TELEMETRY_PYTHON\'\n'
        + payload
        + "\nBIGRED200_TELEMETRY_PYTHON\n"
        "    local TELEMETRY_CODE=$?\n"
        '    if [[ "$EXIT_CODE" -eq 0 && "$TELEMETRY_CODE" -ne 0 ]]; then\n'
        '        EXIT_CODE="$TELEMETRY_CODE"\n'
        "    fi\n"
        '    exit "$EXIT_CODE"\n'
        "}\n"
        "\n"
        "handle_walltime() {\n"
        '    TERMINATION_REASON="SLURM_WALLTIME_TIMEOUT"\n'
        '    printf "%s\\n" "[BigRed200] Walltime warning; terminating workload." >&2\n'
        "    terminate_child_group\n"
        + auto_walltime
        + "    exit 124\n"
        "}\n"
        "\n"
        "trap 'handle_job_exit' EXIT ERR\n"
        "trap 'TERMINATION_REASON=\"SLURM_CANCELLED\"; handle_job_exit 143' SIGTERM\n"
        "trap 'TERMINATION_REASON=\"SIGINT\"; handle_job_exit 130' SIGINT\n"
        "trap 'handle_walltime' SIGUSR1\n"
        "set -Eeuo pipefail\n"
        'cd -- "${SLURM_SUBMIT_DIR:-$PWD}"\n'
        f"mkdir -p -- {logs}\n"
        "\n"
        "run_user_job() (\n"
        "    # Job control gives this subshell its own process group.\n"
        "    # kill -15 0 is safe ONLY here, never in the supervisor's group.\n"
        "    trap - EXIT ERR SIGUSR1\n"
        "    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 143' SIGTERM\n"
        "    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 130' SIGINT\n"
        "    set -Eeuo pipefail\n"
        + body.rstrip("\n")
        + "\n)\n"
        "set -m\n"
        "run_user_job &\n"
        "CHILD_PID=$!\n"
        "set +m\n"
        'if wait "$CHILD_PID"; then\n'
        "    WORKLOAD_EXIT=0\n"
        "else\n"
        "    WORKLOAD_EXIT=$?\n"
        "fi\n"
        'exit "$WORKLOAD_EXIT"\n'
    )


def telemetry_directives(config: Dict[str, str]) -> List[str]:
    logs = config["logs_dir"]
    return [
        "#SBATCH --signal=B:SIGUSR1@120",
        f"#SBATCH -o {logs}/%x_%j.out",
        f"#SBATCH -e {logs}/%x_%j.err",
    ]


def validate_generation_arguments(namespace: argparse.Namespace) -> None:
    for label, value in (
        ("job-name", namespace.job_name),
        ("account", namespace.account),
    ):
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value):
            raise ValueError(f"--{label} has unsafe characters")
    if namespace.gpus < 0 or namespace.cpus_per_task < 1:
        raise ValueError("--gpus must be >= 0; --cpus-per-task must be >= 1")
    if namespace.partition in ("general", "debug") and namespace.gpus != 0:
        raise ValueError("CPU partitions require --gpus 0")
    if not re.fullmatch(r"[1-9][0-9]*[KMGTP]?", namespace.mem, re.IGNORECASE):
        raise ValueError("--mem must be positive, optionally followed by K/M/G/T/P")
    match = re.fullmatch(r"(?:(\d+)-)?(\d+):([0-5]\d):([0-5]\d)", namespace.time)
    if match is None:
        raise ValueError("--time must use [days-]hours:minutes:seconds")
    days, hours, minutes, seconds = (int(item or "0") for item in match.groups())
    if days and hours >= 24:
        raise ValueError("With days specified, hours must be below 24")
    if days * 86400 + hours * 3600 + minutes * 60 + seconds <= 0:
        raise ValueError("--time must be positive")
    if not namespace.entry_script or "\0" in namespace.entry_script:
        raise ValueError("--entry-script must be nonempty and contain no NUL")


def generate_script(namespace: argparse.Namespace, config: Dict[str, str]) -> str:
    validate_generation_arguments(namespace)
    directives = [
        f"#SBATCH --job-name={namespace.job_name}",
        f"#SBATCH --account={namespace.account}",
        f"#SBATCH --partition={namespace.partition}",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        f"#SBATCH --cpus-per-task={namespace.cpus_per_task}",
        f"#SBATCH --mem={namespace.mem}",
        f"#SBATCH --time={namespace.time}",
    ]
    if namespace.gpus:
        directives.append(f"#SBATCH --gpus={namespace.gpus}")
    directives.extend(telemetry_directives(config))
    command = ["python3", "-u", "--", namespace.entry_script]
    command.extend(split_arguments(namespace.script_args))
    body = " ".join(shell_quote(argument) for argument in command) + "\n"
    return "#!/bin/bash\n" + "\n".join(directives) + "\n\n" + harness_body(body, config)


def inject_script(source: str, config: Dict[str, str]) -> str:
    if "\0" in source:
        raise ValueError("Source script contains NUL")
    if MARKER in source:
        raise ValueError("Script already contains this harness; refusing double injection")
    lines = source.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    header: List[str] = []
    body: List[str] = []
    in_header = True
    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and stripped.startswith("#!"):
            if not re.search(r"(?:^|[/\s])(?:bash|sh)(?:\s|$)", stripped):
                raise ValueError("Only bash/sh source scripts can be injected")
            continue
        if in_header and (not stripped or stripped.startswith("#")):
            if re.match(r"^\s*#SBATCH\s+", line):
                options = re.sub(r"^\s*#SBATCH\s+", "", line)
                if re.search(
                    r"(?:^|\s)(?:--signal(?:=|\s)|--output(?:=|\s)|"
                    r"--error(?:=|\s)|-[oe](?:\s|=|[^-\s]))",
                    options,
                ):
                    continue
            header.append(line)
        else:
            in_header = False
            if re.match(r"^\s*#SBATCH(?:\s|$)", line):
                raise ValueError("SBATCH directive occurs after executable code")
            body.append(line)
    return (
        "#!/bin/bash\n"
        + "\n".join(header + telemetry_directives(config))
        + "\n\n"
        + harness_body("\n".join(body) or "true", config)
    )


def atomic_write(path: Path, content: str, mode: int = 0o755) -> None:
    if path.is_symlink():
        raise ValueError("Refusing to overwrite a symlink: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Optional[Path] = None
    descriptor: Optional[int] = None
    for counter in range(100):
        candidate = path.with_name(f".{path.name}.tmp.{os.getpid()}.{counter}")
        try:
            descriptor = os.open(
                str(candidate), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            temporary = candidate
            break
        except FileExistsError:
            continue
    if temporary is None or descriptor is None:
        raise OSError("Could not allocate an atomic output file")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content.replace("\r\n", "\n").replace("\r", "\n"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(str(temporary), mode)
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def audit_script(source: str) -> List[Tuple[str, bool]]:
    """Conservative textual audit, not a proof of arbitrary shell semantics."""
    signal_directive = bool(
        re.search(
            r"(?m)^\s*#SBATCH\s+--signal(?:=|\s+)B:"
            r"(?:SIGUSR1|USR1|SIGTERM|TERM)@[1-9]\d*\s*$",
            source,
        )
    )
    trap_lines = [
        line for line in source.splitlines()
        if re.match(r"^\s*trap\s+", line) and not re.match(r"^\s*trap\s+-", line)
    ]

    def trapped(signal: str) -> bool:
        variants = [signal]
        if signal.startswith("SIG"):
            variants.append(signal[3:])
        return any(
            re.search(r"\s(?:" + "|".join(variants) + r")(?:\s|$)", line)
            is not None
            for line in trap_lines
        )

    proxy = bool(
        re.search(
            r'\bhttp_proxy\s*=\s*["\']?http://proxy\.uits\.iu\.edu:3128(?:["\']|\s|$)',
            source,
        )
    )
    commit = bool(
        re.search(r"\bgit\s+commit\b", source)
        or re.search(r'''git\(\[\s*["']commit["']''', source)
    )
    push = bool(
        re.search(r"\bgit\s+push\b", source)
        or re.search(r'''git\(\[\s*["']push["']''', source)
    )
    states = "[BigRed200] SUCCESS" in source and "[BigRed200] FAILED" in source
    exclusions = all(suffix in source for suffix in BLOCKED_SUFFIXES)
    guards = bool(
        re.search(r"suffix(?:\.lower\(\))?\s+in\s+BLOCKED_SUFFIXES", source)
        or re.search(r"(?:exclude|!|not|case|ignore)", source, re.IGNORECASE)
    )
    continuation = bool(
        re.search(r"(?m)^\s*resubmit_job\s*\(\)\s*\{", source)
        and re.search(r"export\s+-f\s+resubmit_job\b", source)
        and re.search(r'TERMINATION_REASON=["\']RESUBMITTED["\']', source)
        and re.search(r'EXIT_CODE=0\b', source)
        and re.search(
            r"if continuation_detected\(code, reason\):\s+return 0\b", source
        )
        and all(
            token in source
            for token in (
                "JOB_CHAINED", "REQUEUED", "code == 99",
                "SLURM_JOB_RESUBMITTED", ".resubmit_", ".slurm_resubmitted",
                "Skipping Git commit, push, and crash reporting.",
            )
        )
    )
    return [
        ("Walltime preemption signal directive", signal_directive),
        ("Bash EXIT trap", trapped("EXIT")),
        ("SIGUSR1 trap", trapped("SIGUSR1")),
        ("SIGTERM trap", trapped("SIGTERM")),
        ("BigRed 200 HTTP proxy", proxy),
        ("SUCCESS and FAILED commit/push paths", commit and push and states),
        ("Explicit checkpoint staging exclusions", exclusions and guards),
        ("Resubmission / job chaining suppression", continuation),
    ]


def read_text(path: Path, limit: int = 8 * 1024 * 1024) -> str:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"File exceeds {limit} bytes: {path}")
    return data.decode("utf-8")


def reject_json_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number: " + value)


def parse_crash(report_path: Path, err_path: Optional[Path]) -> int:
    loaded: object = json.loads(
        read_text(report_path),
        parse_constant=reject_json_constant,
    )
    if not isinstance(loaded, dict):
        raise ValueError("Crash report must be a JSON object")
    report: Dict[str, object] = loaded
    code = report.get("exit_code")
    if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code <= 255:
        raise ValueError("Crash report exit_code must be an integer from 0 to 255")
    reason = report.get("termination_reason")
    if not isinstance(reason, str) or not reason:
        raise ValueError("Crash report requires a nonempty termination_reason")

    print(f"Job: {report.get('job_id', '?')} ({report.get('job_name', '?')})")
    print(f"Exit: {code} | Reason: {reason}")
    print(f"Node: {report.get('hostname', '?')}")
    print(f"Started: {report.get('started_at', '?')}")
    print(f"Finished: {report.get('finished_at', '?')}")
    print(f"Outputs verified: {report.get('outputs_verified', 'unknown')}")
    errors = report.get("telemetry_errors", [])
    if isinstance(errors, list):
        for error in errors:
            print("Telemetry error: " + str(error))

    if err_path is None:
        stored = report.get("stderr_log")
        if isinstance(stored, str) and stored:
            candidate = Path(stored)
            if candidate.is_absolute():
                err_path = candidate
            else:
                candidates = [
                    report_path.parent / candidate.name,
                    Path.cwd() / candidate,
                    report_path.parent.parent / candidate,
                ]
                err_path = next((path for path in candidates if path.is_file()), candidates[0])
    if err_path is None:
        print("No error log path supplied or recorded.")
        return 0
    if not err_path.is_file():
        print(f"Error log unavailable: {err_path}")
        return 0

    with err_path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - 262144))
        tail = stream.read(262144).decode("utf-8", errors="replace")
    findings: List[str] = []
    patterns = [
        ("Out of memory / OOM", r"out[\s_-]*of[\s_-]*memory|oom[_ -]*(?:kill|killed)|OutOfMemoryError"),
        ("CUDA/GPU error", r"CUDA error|device-side assert|CUBLAS|CUDNN"),
        ("Python exception", r"Traceback \(most recent call last\)|\b\w+(?:Error|Exception):"),
        ("Walltime limit", r"time limit|walltime|SLURM_WALLTIME_TIMEOUT"),
        ("Cancellation / termination", r"CANCELLED|SIGTERM|terminated"),
        ("Missing file", r"No such file or directory|FileNotFoundError"),
        ("Permission / authentication", r"Permission denied|Authentication failed|could not read Username"),
        ("Network / proxy failure", r"Could not resolve|Connection timed out|Failed to connect|proxy.*(?:error|fail)"),
    ]
    for label, pattern in patterns:
        if re.search(pattern, tail, re.IGNORECASE):
            findings.append(label)
    print("Detected: " + (", ".join(findings) if findings else "No recognized signature"))
    print(f"Error log: {err_path}")
    print("--- Last 25 log lines ---")
    lines = tail.splitlines()
    print("\n".join(lines[-25:]) if lines else "(empty)")
    return 0


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--figures-dir", default="figures")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--git-remote", default="origin")
    parser.add_argument(
        "--auto-resubmit",
        action="store_true",
        default=False,
        help=(
            "Mark continuation on walltime warning and submit SLURM_JOB_SCRIPT "
            "when available; otherwise only create a continuation sentinel"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate, inject, audit, and diagnose BigRed 200 Slurm telemetry.",
        epilog=(
            "Best-effort only: SIGKILL/node loss cannot be trapped. "
            "Create log directories before sbatch; configure unattended Git authentication."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Generate a self-contained bash Slurm script")
    generate.add_argument("--job-name", default="bigred_job")
    generate.add_argument("--entry-script", default="main.py")
    generate.add_argument("--script-args", default="", help="Literal shell-quoted arguments; no expansion")
    generate.add_argument("--account", default="r01540")
    generate.add_argument("--partition", choices=("gpu", "gpu-debug", "general", "debug"), default="gpu")
    generate.add_argument("--gpus", type=int, default=1)
    generate.add_argument("--cpus-per-task", type=int, default=16)
    generate.add_argument("--mem", default="64G")
    generate.add_argument("--time", default="04:00:00")
    generate.add_argument("--output", required=True)
    add_common_arguments(generate)

    inject = commands.add_parser("inject", help="Supervise an existing Slurm script")
    inject.add_argument("--input", required=True)
    inject.add_argument("--output")
    add_common_arguments(inject)

    validate = commands.add_parser("validate", help="Perform a textual compliance audit")
    validate.add_argument("--script", required=True)

    crash = commands.add_parser("parse-crash", help="Summarize a crash report and stderr log")
    crash.add_argument("--report", required=True)
    crash.add_argument("--err-file")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    namespace = parser.parse_args(argv)
    try:
        if namespace.command == "validate":
            checks = audit_script(read_text(Path(namespace.script)))
            for label, passed in checks:
                print(f"[{'PASS' if passed else 'FAIL'}] {label}")
            compliant = all(passed for _, passed in checks)
            print("Textual audit only; runtime behavior and remote delivery are not guaranteed.")
            return 0 if compliant else 1

        if namespace.command == "parse-crash":
            return parse_crash(
                Path(namespace.report),
                Path(namespace.err_file) if namespace.err_file else None,
            )

        config = configuration(namespace)
        if namespace.command == "generate":
            content = generate_script(namespace, config)
            destination = Path(namespace.output)
            mode = 0o755
        else:
            source_path = Path(namespace.input)
            if source_path.is_symlink():
                raise ValueError("Refusing symlink input script")
            content = inject_script(read_text(source_path), config)
            destination = Path(namespace.output) if namespace.output else source_path
            mode = source_path.stat().st_mode & 0o777
        prepare_logs(config["logs_dir"])
        atomic_write(destination, content, mode)
        print(f"Wrote {destination}")
        print(
            f"Before sbatch, ensure {config['logs_dir']}/ exists in the remote "
            "submission directory and submit from the Git repository root."
        )
        return 0
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as error:
        print(f"{parser.prog}: error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"{parser.prog}: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
