import sys
import os
import re
import shutil
import subprocess
import time
import random
import fcntl


def run_cmd(args, cwd=None):
    env = os.environ.copy()
    for key in list(env):
        if key.lower() in ("http_proxy", "https_proxy"):
            env.pop(key)
    try:
        res = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
            timeout=180,
        )
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", str(e)


def run_git_cmd_with_retry(args, cwd=None, max_retries=5):
    ret, out, err = -1, "", ""
    for attempt in range(max_retries):
        ret, out, err = run_cmd(args, cwd=cwd)
        if "index.lock" not in err and "index.lock" not in out:
            return ret, out, err
        if attempt + 1 < max_retries:
            delay = 1.0 + random.random() * 2.0
            print(f"[HPC EXIT HANDLER] Git lock detected, retrying in {delay:.1f}s...")
            time.sleep(delay)
    return ret, out, err


def main():
    if len(sys.argv) < 3:
        print("[HPC EXIT HANDLER] Missing arguments. Usage: python hpc_exit_handler.py <exit_code> <script_path>")
        sys.exit(0)

    try:
        exit_code = int(sys.argv[1])
    except ValueError:
        print("[HPC EXIT HANDLER] Invalid exit code.")
        sys.exit(0)

    script_path = sys.argv[2]

    if exit_code == 0:
        print(f"[HPC EXIT HANDLER] Clean exit (code 0) for {script_path}. No action required.")
        sys.exit(0)

    print(f"[HPC EXIT HANDLER] Script failed with code {exit_code}. Diagnosing logs...")

    if not os.path.isfile(script_path):
        print(f"[HPC EXIT HANDLER] Script file not found: {script_path}")
        sys.exit(0)

    try:
        with open(script_path, "r", errors="ignore") as f:
            content = f.read()
    except OSError as e:
        print(f"[HPC EXIT HANDLER] Could not read script: {e}")
        sys.exit(0)

    script_dir = os.path.dirname(os.path.abspath(script_path))
    submit_dir = os.environ.get("SLURM_SUBMIT_DIR")
    current_dir = os.getcwd()

    # Discover the repository from the submission location before consulting
    # the script directory, which may be a Slurm spool directory.
    repo_dir = None
    checked_dirs = set()
    for candidate in (submit_dir, current_dir, script_dir):
        if not candidate:
            continue
        candidate = os.path.abspath(candidate)
        if candidate in checked_dirs or not os.path.isdir(candidate):
            continue
        checked_dirs.add(candidate)
        ret, out, err = run_cmd(
            ["git", "rev-parse", "--show-toplevel"], cwd=candidate
        )
        if ret == 0 and out.strip() and os.path.isdir(out.strip()):
            repo_dir = os.path.abspath(out.strip())
            break

        # Retain filesystem discovery as a fallback.
        parent_dir = candidate
        while True:
            if os.path.exists(os.path.join(parent_dir, ".git")):
                repo_dir = parent_dir
                break
            parent = os.path.dirname(parent_dir)
            if parent == parent_dir:
                break
            parent_dir = parent
        if repo_dir:
            break

    if not repo_dir:
        print("[HPC EXIT HANDLER] Could not find Git repository root.")
        sys.exit(0)

    out_match = re.search(r'#SBATCH\s+(?:--output|-o)\s*=\s*(\S+)|#SBATCH\s+(?:--output|-o)\s+(\S+)', content)
    err_match = re.search(r'#SBATCH\s+(?:--error|-e)\s*=\s*(\S+)|#SBATCH\s+(?:--error|-e)\s+(\S+)', content)

    out_pat = (out_match.group(1) or out_match.group(2)) if out_match else None
    err_pat = (err_match.group(1) or err_match.group(2)) if err_match else None

    if not out_pat:
        out_pat = "slurm-%j.out"

    job_id = os.environ.get("SLURM_JOB_ID", "")
    array_job_id = os.environ.get("SLURM_ARRAY_JOB_ID", "")
    array_task_id = os.environ.get("SLURM_ARRAY_TASK_ID", "")

    def resolve_pattern(pat):
        if not pat:
            return None
        res_pat = pat.replace("%j", job_id if job_id else "failed")
        res_pat = res_pat.replace("%A", array_job_id if array_job_id else "failed")
        res_pat = res_pat.replace("%a", array_task_id if array_task_id else "failed")
        return res_pat

    out_file = resolve_pattern(out_pat)
    err_file = resolve_pattern(err_pat)

    def get_full_path(f_path):
        if not f_path:
            return None
        if os.path.isabs(f_path):
            return f_path
        for directory in (submit_dir, current_dir, repo_dir, script_dir):
            if directory:
                candidate = os.path.abspath(os.path.join(directory, f_path))
                if os.path.isfile(candidate):
                    return candidate
        return os.path.join(repo_dir, f_path)

    try:
        os.sync()
    except (AttributeError, OSError):
        pass

    # Repository discovery necessarily precedes locking. Lock all subsequent
    # telemetry writes and Git operations, including in linked worktrees.
    ret, out, err = run_cmd(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=repo_dir
    )
    if ret != 0 or not out.strip():
        print(f"[HPC EXIT HANDLER] Could not resolve Git directory: {err}")
        sys.exit(0)
    git_dir = out.strip()
    lock_path = os.path.join(git_dir, "bigred200_telemetry.lock")

    try:
        lock_file = open(lock_path, "a")
    except OSError as e:
        print(f"[HPC EXIT HANDLER] Could not open telemetry lock: {e}")
        sys.exit(0)

    with lock_file:
        deadline = time.monotonic() + 180
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    print("[HPC EXIT HANDLER] Timed out waiting for telemetry lock.")
                    return
                time.sleep(1)
            except OSError as e:
                print(f"[HPC EXIT HANDLER] Could not acquire telemetry lock: {e}")
                return

        try:
            files_to_push = []
            for name, f_path in [("output", out_file), ("error", err_file)]:
                full_path = get_full_path(f_path)
                if full_path and os.path.isfile(full_path):
                    base, ext = os.path.splitext(os.path.basename(full_path))
                    dest_name = f"{base}_final_{job_id if job_id else 'failed'}{ext if ext in ['.log', '.err', '.txt'] else '.log'}"
                    if name == "error":
                        dest_name = f"{base}_final_{job_id if job_id else 'failed'}.err"

                    dest_path = os.path.join(repo_dir, dest_name)
                    try:
                        shutil.copy2(full_path, dest_path)
                        files_to_push.append(dest_path)
                        print(f"[HPC EXIT HANDLER] Copied {name} log to: {dest_path}")
                    except Exception as e:
                        print(f"[HPC EXIT HANDLER] Error copying {name} log: {e}")

            if not files_to_push:
                print("[HPC EXIT HANDLER] No log files found to stage.")
                return

            for fp in files_to_push:
                rel_path = os.path.relpath(fp, repo_dir)
                ret, out, err = run_git_cmd_with_retry(
                    ["git", "add", "--", rel_path], cwd=repo_dir
                )
                if ret != 0:
                    print(f"[HPC EXIT HANDLER] Git add failed: {err}")
                    return

            commit_msg = f"HPC Run Failure: Logged output for job {job_id if job_id else 'failed'}"
            ret, out, err = run_git_cmd_with_retry(
                ["git", "commit", "-m", commit_msg], cwd=repo_dir
            )
            print(f"[HPC EXIT HANDLER] Git commit status: {ret}")
            if ret != 0:
                print(f"[HPC EXIT HANDLER] Git commit failed: {out} {err}")
                return

            ret, out, err = run_git_cmd_with_retry(
                ["git", "pull", "--rebase", "--autostash", "origin", "main"],
                cwd=repo_dir,
            )
            if ret != 0:
                print(f"[HPC EXIT HANDLER] Git pull failed: {out} {err}")
                abort_ret, abort_out, abort_err = run_git_cmd_with_retry(
                    ["git", "rebase", "--abort"], cwd=repo_dir
                )
                print(
                    f"[HPC EXIT HANDLER] Git rebase abort status: {abort_ret} "
                    f"stdout: {abort_out} stderr: {abort_err}"
                )
                return

            ret, out, err = run_git_cmd_with_retry(["git", "push"], cwd=repo_dir)
            print(f"[HPC EXIT HANDLER] Git push status: {ret} stdout: {out} stderr: {err}")
        finally:
            # Keep the lock file in place to avoid races between waiters.
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
