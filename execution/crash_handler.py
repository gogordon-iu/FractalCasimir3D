import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import json
import time
import signal
import traceback
import subprocess
import datetime
import errno
import tempfile
from contextlib import contextmanager

CRASH_LOG_DIR = "cluster_diagnostics/crash_logs"
MASTER_CRASH_FILE = "cluster_diagnostics/master_crash_report.json"
TELEMETRY_LOCK_FILE = ".git/bigred200_telemetry.lock"


def ensure_dirs():
    os.makedirs(CRASH_LOG_DIR, exist_ok=True)
    os.makedirs("cluster_diagnostics", exist_ok=True)
    os.makedirs(".tmp", exist_ok=True)


@contextmanager
def telemetry_lock(timeout=180):
    if os.name == "nt":
        import msvcrt
    else:
        import fcntl

    with open(TELEMETRY_LOCK_FILE, "a+b") as lock_file:
        if os.name == "nt":
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()

        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(
                        lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                break
            except OSError as err:
                if err.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Timed out acquiring '{TELEMETRY_LOCK_FILE}' "
                        f"after {timeout}s."
                    ) from err
                time.sleep(min(0.1, remaining))

        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def log_crash_and_push(task_id, error_type, details, config_info=None):
    try:
        rank = int(os.environ.get(
            "SLURM_PROCID",
            os.environ.get("PMI_RANK", os.environ.get("OMPI_COMM_WORLD_RANK", 0))
        ))
        if rank != 0:
            return

        ensure_dirs()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        hostname = (
            os.uname().nodename
            if hasattr(os, "uname")
            else os.environ.get("COMPUTERNAME", "unknown_host")
        )

        crash_filename = f"crash_task_{task_id}_{timestamp}.log"
        crash_filepath = os.path.join(CRASH_LOG_DIR, crash_filename)

        crash_data = {
            "timestamp": timestamp,
            "task_id": task_id,
            "hostname": hostname,
            "error_type": str(error_type),
            "details": details,
            "config": config_info or {},
            "env_slurm_job_id": os.environ.get("SLURM_JOB_ID", "N/A"),
            "env_slurm_array_task_id": os.environ.get(
                "SLURM_ARRAY_TASK_ID", "N/A"
            )
        }

        # 1. Write human-readable crash log file.
        with open(crash_filepath, "w") as f:
            f.write("==================================================\n")
            f.write(f"CRASH REPORT - TASK {task_id} ON {hostname}\n")
            f.write("==================================================\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Error Type: {error_type}\n")
            f.write(f"Slurm Job ID: {os.environ.get('SLURM_JOB_ID', 'N/A')}\n")
            f.write(
                f"Slurm Array Task ID: "
                f"{os.environ.get('SLURM_ARRAY_TASK_ID', 'N/A')}\n"
            )
            f.write("--------------------------------------------------\n")
            f.write("DETAILS / TRACEBACK:\n")
            f.write(f"{details}\n")
            f.write("--------------------------------------------------\n")
            f.write("CONFIGURATION:\n")
            f.write(json.dumps(config_info or {}, indent=4))
            f.write("\n==================================================\n")

        print(f"\n[CRASH HANDLER] Logged crash details to '{crash_filepath}'.")

        # Serialize the master report update and all Git operations.
        with telemetry_lock(timeout=180):
            # 2. Append to the master report using atomic replacement.
            master_data = []
            if os.path.exists(MASTER_CRASH_FILE):
                try:
                    with open(MASTER_CRASH_FILE, "r") as f:
                        master_data = json.load(f)
                    if not isinstance(master_data, list):
                        raise ValueError("Master crash report must be a list.")
                except (ValueError, OSError) as err:
                    print(
                        f"[CRASH HANDLER WARNING] Corrupted master crash file "
                        f"({err}). Resetting."
                    )
                    master_data = []

            master_data.append(crash_data)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    dir=os.path.dirname(MASTER_CRASH_FILE) or ".",
                    prefix=".master_crash_report.",
                    suffix=".tmp",
                    delete=False
                ) as f:
                    temp_path = f.name
                    json.dump(master_data, f, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, MASTER_CRASH_FILE)
                temp_path = None
            finally:
                if temp_path is not None:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

            # 3. Auto-commit and push crash log to GitHub.
            print("[CRASH HANDLER] Auto-syncing crash report to GitHub...")
            try:
                if time.time() - os.stat(".git/index.lock").st_mtime > 120:
                    os.remove(".git/index.lock")
            except OSError:
                pass

            git_env = os.environ.copy()
            for key in list(git_env):
                if key.lower() in ("http_proxy", "https_proxy"):
                    del git_env[key]

            subprocess.run(
                ["git", "add", crash_filepath, MASTER_CRASH_FILE],
                check=True, env=git_env, timeout=180
            )
            msg = f"CRASH LOG: Task {task_id} failed on {hostname} ({error_type})"
            subprocess.run(
                ["git", "commit", "-m", msg],
                check=True, env=git_env, timeout=180
            )
            subprocess.run(
                ["git", "pull", "--rebase", "origin", "main"],
                check=True, env=git_env, timeout=180
            )
            subprocess.run(
                ["git", "push"],
                check=True, env=git_env, timeout=180
            )
            print("[CRASH HANDLER] Successfully pushed crash log to GitHub!")

    except (OSError, subprocess.SubprocessError, ValueError, TypeError) as e:
        print(f"[CRASH HANDLER ERROR] Failed to log/push crash: {e}")


def setup_global_exception_handler(task_id, config_info=None):
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        err_msg = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        print(f"\nCRITICAL UNCAUGHT EXCEPTION IN TASK {task_id}:\n{err_msg}")
        log_crash_and_push(task_id, exc_type.__name__, err_msg, config_info)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

    def handle_signal(sig, frame):
        sig_name = (
            signal.Signals(sig).name
            if hasattr(signal, "Signals")
            else f"Signal_{sig}"
        )
        details = f"Process terminated by signal {sig_name} ({sig})"
        print(f"\nCRITICAL SIGNAL RECEIVED IN TASK {task_id}: {sig_name}")
        log_crash_and_push(task_id, sig_name, details, config_info)
        sys.exit(128 + sig)

    # Register termination signals, including Unix preemption notifications.
    signals = [signal.SIGTERM, signal.SIGINT, signal.SIGABRT]
    if hasattr(signal, "SIGUSR1"):
        signals.append(signal.SIGUSR1)
    for sig in signals:
        try:
            signal.signal(sig, handle_signal)
        except (ValueError, OSError, RuntimeError):
            pass


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        t_id = sys.argv[1]
        e_type = sys.argv[2]
        det = (
            " ".join(sys.argv[3:])
            if len(sys.argv) > 3
            else "Execution failure reported by wrapper script."
        )
        log_crash_and_push(t_id, e_type, det)
