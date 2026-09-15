"""
Git Auto-Sync Utility for Simulation Analyzers
---------------------------------------------
Automatically stages, commits, and pushes generated summary JSONs,
LaTeX tables, and publication figures from BigRed 200 compute/login nodes
to GitHub so results can be pulled and inspected locally.
"""

import os
import subprocess

def git_sync_results(phase_name, files_to_sync, completed_count, total_count):
    """
    Stages, commits, and pushes generated analysis artifacts to GitHub.
    """
    valid_files = [f for f in files_to_sync if os.path.exists(f)]
    if not valid_files:
        return
        
    try:
        subprocess.run(["git", "add"] + valid_files, check=False)
        msg = f"results({phase_name}): update summary, tables, and figures [{completed_count}/{total_count} completed]"
        subprocess.run(["git", "commit", "-m", msg], check=False)
        print(f"\n[Git Auto-Sync] Pushing {phase_name} results to GitHub...")
        res = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            print(f"[Git Auto-Sync] SUCCESS: {phase_name} results pushed to GitHub!")
        else:
            out_msg = res.stderr.strip() or res.stdout.strip()
            print(f"[Git Auto-Sync] Push status: {out_msg if out_msg else 'Complete'}")
    except Exception as e:
        print(f"[Git Auto-Sync] Note: Could not auto-sync to GitHub: {e}")