"""
Git Auto-Sync Utility for Simulation Analyzers
---------------------------------------------
Automatically stages, commits, and pushes generated summary JSONs,
LaTeX tables, and publication figures from BigRed 200 compute/login nodes
to GitHub so results can be pulled and inspected locally.
"""

import fcntl
import os
import subprocess
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git_sync_results(phase_name, files_to_sync, completed_count, total_count):
    """
    Stages, commits, and pushes generated analysis artifacts to GitHub.
    """
    valid_files = []
    for f in files_to_sync:
        full_p = f if os.path.isabs(f) else os.path.join(REPO_ROOT, f)
        if os.path.exists(full_p):
            rel_p = os.path.relpath(full_p, REPO_ROOT)
            valid_files.append(rel_p)

    if not valid_files:
        print(f"[Git Auto-Sync] Note: None of the target files exist yet to sync for {phase_name}.")
        return

    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(key, None)

    lock_path = os.path.join(REPO_ROOT, ".git", "bigred200_telemetry.lock")

    try:
        with open(lock_path, "a") as lock_file:
            deadline = time.monotonic() + 180
            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Timed out waiting for the Git auto-sync lock.")
                    time.sleep(min(0.1, remaining))

            try:
                add_res = subprocess.run(
                    ["git", "add", "--"] + valid_files,
                    cwd=REPO_ROOT,
                    env=env,
                    timeout=180,
                    check=False,
                )
                if add_res.returncode != 0:
                    print("[Git Auto-Sync] Note: Git staging failed; skipping auto-sync.")
                    return

                msg = (
                    f"results({phase_name}): update summary, tables, and figures "
                    f"[{completed_count}/{total_count} completed]"
                )
                subprocess.run(
                    ["git", "commit", "-m", msg],
                    cwd=REPO_ROOT,
                    env=env,
                    timeout=180,
                    check=False,
                )

                try:
                    pull_res = subprocess.run(
                        ["git", "pull", "--rebase", "--autostash", "origin", "main"],
                        cwd=REPO_ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    subprocess.run(
                        ["git", "rebase", "--abort"],
                        cwd=REPO_ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        check=False,
                    )
                    raise

                if pull_res.returncode != 0:
                    out_msg = pull_res.stderr.strip() or pull_res.stdout.strip()
                    print(
                        f"[Git Auto-Sync] Note: Git pull failed for {phase_name}: "
                        f"{out_msg or f'exit status {pull_res.returncode}'}"
                    )
                    abort_res = subprocess.run(
                        ["git", "rebase", "--abort"],
                        cwd=REPO_ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        check=False,
                    )
                    if abort_res.returncode != 0:
                        abort_msg = abort_res.stderr.strip() or abort_res.stdout.strip()
                        print(f"[Git Auto-Sync] Note: Rebase abort: {abort_msg}")
                    return

                print(f"\n[Git Auto-Sync] Pushing {phase_name} results to GitHub...")
                res = subprocess.run(
                    ["git", "push", "origin", "main"],
                    cwd=REPO_ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                if res.returncode == 0:
                    print(f"[Git Auto-Sync] SUCCESS: {phase_name} results pushed to GitHub!")
                else:
                    out_msg = res.stderr.strip() or res.stdout.strip()
                    print(
                        f"[Git Auto-Sync] Note: Git push failed for {phase_name}: "
                        f"{out_msg or f'exit status {res.returncode}'}"
                    )
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[Git Auto-Sync] Note: Could not auto-sync to GitHub: {e}")
