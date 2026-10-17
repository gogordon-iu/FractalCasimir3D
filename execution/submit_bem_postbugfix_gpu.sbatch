#!/bin/bash
#SBATCH --job-name=fce_bemg
#SBATCH --account=r01540
#SBATCH --partition=general
#SBATCH --exclude=nid0394
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=128
#SBATCH --mem=0
#SBATCH --time=02:00:00
#SBATCH --signal=B:SIGUSR1@120
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

# BIGRED200_TELEMETRY_HARNESS_V1
# SIGKILL/node loss cannot be trapped; publication is best-effort.
# Logs must exist BEFORE sbatch; the generator creates them locally.
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
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
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

CONFIG = json.loads('{"auto_resubmit": "0", "figures_dir": "figures", "git_remote": "origin", "logs_dir": "logs", "proxy": "", "results_dir": "results"}')
BLOCKED_SUFFIXES = (".pt", ".ckpt", ".bin", ".h5", ".safetensors", ".tar")
GIT_TIMEOUT_SECONDS = 180

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
    # Keep the lock in Git metadata so it cannot be staged with job outputs.
    git_directory = Path(git(["rev-parse", "--absolute-git-dir"]).stdout.strip())
    lock_path = git_directory / "bigred200_telemetry.lock"
    descriptor = os.open(
        str(lock_path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            sync_git(paths, message)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

def sync_git(paths, message):
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

    # Preserve unstaged tracked changes while rebasing the shared worktree.
    pulled = git(
        ["pull", "--rebase", "--autostash", CONFIG["git_remote"], current_branch],
        check=False,
    )
    if pulled.returncode != 0:
        diagnostic("git pull --rebase --autostash failed: " + pulled.stderr.strip()[-3000:])
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
mkdir -p -- 'logs'

run_user_job() (
    # Job control gives this subshell its own process group.
    # kill -15 0 is safe ONLY here, never in the supervisor's group.
    trap - EXIT ERR SIGUSR1
    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 143' SIGTERM
    trap 'trap - SIGTERM SIGINT; kill -15 0 2>/dev/null || true; exit 130' SIGINT
    set -Eeuo pipefail

    export OMP_NUM_THREADS=128
    export MKL_NUM_THREADS=128
    export OPENBLAS_NUM_THREADS=128
    export PYTHONPATH="${SLURM_SUBMIT_DIR:-$PWD}${PYTHONPATH:+:$PYTHONPATH}"

    PYTHON_BIN=""
    for ENV_PREFIX in \
        "/N/u/gogordon/BigRed200/.conda/envs/meep" \
        "/N/u/gogordon/BigRed200/miniconda3" \
        "${HOME}/.conda/envs/meep" \
        "${HOME}/miniconda3/envs/meep" \
        "${HOME}/miniconda3"
    do
        [[ -x "$ENV_PREFIX/bin/python" ]] || continue
        if ! "$ENV_PREFIX/bin/python" -c 'import numpy; import torch' >/dev/null 2>&1; then
            continue
        fi

        # Conda may be installed separately from the environment prefix.
        CONDA_ACTIVATED=0
        for CONDA_SH in \
            "$ENV_PREFIX/etc/profile.d/conda.sh" \
            "$ENV_PREFIX/../../etc/profile.d/conda.sh" \
            "/N/u/gogordon/BigRed200/miniconda3/etc/profile.d/conda.sh" \
            "${HOME}/miniconda3/etc/profile.d/conda.sh"
        do
            [[ -f "$CONDA_SH" ]] || continue
            set +u
            if source "$CONDA_SH" && conda activate "$ENV_PREFIX"; then
                CONDA_ACTIVATED=1
            fi
            set -u
            if [[ "$CONDA_ACTIVATED" -eq 1 ]]; then
                break
            fi
        done
        # A standalone environment can still be used without a Conda hook.
        if [[ "$CONDA_ACTIVATED" -eq 0 ]]; then
            export PATH="$ENV_PREFIX/bin:$PATH"
        fi
        if "$ENV_PREFIX/bin/python" -c 'import numpy; import torch' >/dev/null 2>&1; then
            PYTHON_BIN="$ENV_PREFIX/bin/python"
            break
        fi
    done

    if [[ -z "$PYTHON_BIN" ]]; then
        if type module >/dev/null 2>&1; then
            module load python/gpu || module load python || true
        fi
        for PYTHON_COMMAND in python3 python; do
            if CANDIDATE=$(command -v "$PYTHON_COMMAND") \
                && "$CANDIDATE" -c 'import numpy; import torch' >/dev/null 2>&1; then
                PYTHON_BIN="$CANDIDATE"
                break
            fi
        done
    fi
    if [[ -z "$PYTHON_BIN" ]]; then
        printf "%s\n" "[BigRed200] No Python environment with numpy and torch found." >&2
        exit 1
    fi
    export PYTHON_BIN
    printf "[BigRed200] Using Python: %s\n" "$PYTHON_BIN"

    "$PYTHON_BIN" -u execution/run_nature_6step_narrative.py --device auto
    "$PYTHON_BIN" -u execution/run_real_world_nems_clutch.py --device auto
    "$PYTHON_BIN" -u execution/run_rotational_clutch_3solver_verification.py --device auto
    "$PYTHON_BIN" -u execution/run_rotational_z_eff_clutch.py --device auto
    "$PYTHON_BIN" -u execution/run_fractal_advantage_study.py --device auto
    "$PYTHON_BIN" -u execution/run_nature_feasibility_and_stability.py --device auto
    "$PYTHON_BIN" -u execution/run_repulsion_10configs_scan.py --device auto
    "$PYTHON_BIN" -u execution/run_top_repulsive_verification.py --device auto
    "$PYTHON_BIN" -u execution/export_provenance_pipeline.py
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
