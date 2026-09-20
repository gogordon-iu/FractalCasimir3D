"""
Git Auto-Sync Utility for Simulation Analyzers
---------------------------------------------
Automatically stages, commits, and pushes generated summary JSONs,
LaTeX tables, and publication figures from BigRed 200 compute/login nodes
to GitHub so results can be pulled and inspected locally.
"""

import os
import subprocess

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
        
    try:
        subprocess.run(["git", "add"] + valid_files, cwd=REPO_ROOT, check=False)
        msg = f"results({phase_name}): update summary, tables, and figures [{completed_count}/{total_count} completed]"
        subprocess.run(["git", "commit", "-m", msg], cwd=REPO_ROOT, check=False)
        print(f"\n[Git Auto-Sync] Pushing {phase_name} results to GitHub...")
        res = subprocess.run(["git", "push", "origin", "main"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            print(f"[Git Auto-Sync] SUCCESS: {phase_name} results pushed to GitHub!")
        else:
            out_msg = res.stderr.strip() or res.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[Git Auto-Sync] Note: Could not auto-sync to GitHub: {e}")