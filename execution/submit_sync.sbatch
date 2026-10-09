#!/bin/bash
#SBATCH -J twist_sweep_sync
#SBATCH -A r01540
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:15:00
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=gogordon@iu.edu

# Exit trap for staging and pushing error logs on failure
#SBATCH --signal=B:SIGUSR1@120
#SBATCH -o cluster_diagnostics/raw_logs/%x_%j.out
#SBATCH -e cluster_diagnostics/raw_logs/%x_%j.err

# BIGRED200_TELEMETRY_HARNESS_V1
# SIGKILL/node loss cannot be trapped; publication is best-effort.
# Logs must exist BEFORE sbatch; the generator creates them locally.
export http_proxy="http://proxy.uits.iu.edu:3128"
export https_proxy="http://proxy.uits.iu.edu:3128"
export no_proxy="localhost,127.0.0.1,*.iu.edu,*.uits.iu.edu"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export WANDB_MODE=offline
export TORCH_HOME="${SLATE:-/N/slate/$USER}/.cache/torch"
export JOB_START_TIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TERMINATION_REASON="UNEXPECTED_EXIT"
CHILD_PID=""

resubmit_job() {
    echo "[BigRed200] Registering job continuation/resubmission..."
    touch -- "${SLURM_SUBMIT_DIR:-$PWD}/.resubmit_${SLURM_JOB_ID:-local}" || return $?
    export RESUBMITTED=1
    if [[ $# -gt 0 ]]; then
        sbatch "$@"
    fi
}
export -f resubmit_job 2>/dev/null || true

terminate_child_group() {
    if [[ -n "${CHILD_PID:-}" ]]; then
        kill -15 -- "-${CHILD_PID}" 2>/dev/null || true
    fi
}

handle_job_exit() {
    local EXIT_CODE=$?
    if [[ $# -gt 0 ]]; then EXIT_CODE="$1"; fi
    trap - EXIT ERR SIGTERM SIGINT SIGUSR1
    set +e
    terminate_child_group
    sync || true
    if [[ -f "${SLURM_SUBMIT_DIR:-$PWD}/.resubmit_${SLURM_JOB_ID:-local}"
          || -e "${SLURM_SUBMIT_DIR:-$PWD}/.slurm_resubmitted"
          || "${RESUBMITTED:-0}" == "1"
          || "${SLURM_JOB_RESUBMITTED:-0}" == "1"
          || "$EXIT_CODE" -eq 99
          || "$TERMINATION_REASON" == "RESUBMITTED"
          || "$TERMINATION_REASON" == "JOB_CHAINED"
          || "$TERMINATION_REASON" == "REQUEUED" ]]; then
        TERMINATION_REASON="RESUBMITTED"
        EXIT_CODE=0
    fi
    if [[ "$TERMINATION_REASON" != "RESUBMITTED" ]]; then
        (
            git config user.name >/dev/null 2>&1 || git config user.name "BigRed200-JobRunner"
            git config user.email >/dev/null 2>&1 || git config user.email "bigred200@iu.edu"
            CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
            export CURRENT_BRANCH
        )
    fi
    python3 - "$EXIT_CODE" "$TERMINATION_REASON" <<'BIGRED200_TELEMETRY_PYTHON'
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

CONFIG = json.loads('{"auto_resubmit": "0", "figures_dir": "Papers/Fractal_Casimir_Nature_EM/figures", "git_remote": "origin", "logs_dir": "cluster_diagnostics/raw_logs", "results_dir": "results"}')
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
BIGRED200_TELEMETRY_PYTHON
    local TELEMETRY_CODE=$?
    if [[ "$EXIT_CODE" -eq 0 && "$TELEMETRY_CODE" -ne 0 ]]; then
        EXIT_CODE="$TELEMETRY_CODE"
    fi
    exit "$EXIT_CODE"
}

handle_walltime() {
    TERMINATION_REASON="SLURM_WALLTIME_TIMEOUT"
    printf "%s\n" "[BigRed200] Walltime warning; terminating workload." >&2
    terminate_child_group
    exit 124
}

trap 'handle_job_exit' EXIT ERR
trap 'TERMINATION_REASON="SLURM_CANCELLED"; handle_job_exit 143' SIGTERM
trap 'TERMINATION_REASON="SIGINT"; handle_job_exit 130' SIGINT
trap 'handle_walltime' SIGUSR1
set -Eeuo pipefail
cd -- "${SLURM_SUBMIT_DIR:-$PWD}"
mkdir -p -- 'cluster_diagnostics/raw_logs'

run_user_job() (
    # Job control gives this subshell its own process group.
    # kill -15 0 is safe ONLY here, never in the supervisor's group.
    trap - EXIT ERR SIGUSR1
    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 143' SIGTERM
    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 130' SIGINT
    set -Eeuo pipefail
_curr_dir=$(dirname "$0")
_exit_handler=""
for i in {1..4}; do
    if [ -f "$_curr_dir/hpc_exit_handler.py" ]; then
        _exit_handler="$_curr_dir/hpc_exit_handler.py"
        break
    fi
    _curr_dir="$_curr_dir/.."
done
if [ -n "$_exit_handler" ]; then
    trap 'if [ $? -ne 0 ]; then python "$_exit_handler" $? "$0"; fi' EXIT
fi


# Activate Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate meep
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Force Slurm to run from the repository root directory
cd /N/project/gorengor_werewolf/FractalCasimir3D

echo "=================================================="
echo "Starting final sweep compilation and git sync..."
echo "=================================================="

# Run the git sync script to consolidate, plot, and push to GitHub
$CONDA_PREFIX/bin/python execution/sync_results_to_github.py

echo "Sync complete."
)
set -m
run_user_job &
CHILD_PID=$!
set +m
if wait "$CHILD_PID"; then
    WORKLOAD_EXIT=0
else
    WORKLOAD_EXIT=$?
fi
exit "$WORKLOAD_EXIT"
