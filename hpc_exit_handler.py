import sys
import os
import re
import shutil
import subprocess
import time
import random

def run_cmd(args, cwd=None):
    try:
        res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", str(e)

def run_git_cmd_with_retry(args, cwd=None, max_retries=5):
    ret, out, err = -1, "", ""
    for attempt in range(max_retries):
        ret, out, err = run_cmd(args, cwd=cwd)
        if "index.lock" not in err and "index.lock" not in out:
            return ret, out, err
        print(f"[HPC EXIT HANDLER] Git lock detected, retrying in {attempt + 1}s...")
        time.sleep(1.0 + random.random() * 2.0)
    return ret, out, err

def main():
    if len(sys.argv) < 3:
        print("[HPC EXIT HANDLER] Missing arguments. Usage: python hpc_exit_handler.py <exit_code> <script_path>")
        sys.exit(0)
        
    exit_code = int(sys.argv[1])
    script_path = sys.argv[2]
    
    if exit_code == 0:
        print(f"[HPC EXIT HANDLER] Clean exit (code 0) for {script_path}. No action required.")
        sys.exit(0)
        
    print(f"[HPC EXIT HANDLER] Script failed with code {exit_code}. Diagnosing logs...")
    
    if not os.path.exists(script_path):
        print(f"[HPC EXIT HANDLER] Script file not found: {script_path}")
        sys.exit(0)
        
    # Read script to find output and error file patterns
    with open(script_path, 'r', errors='ignore') as f:
        content = f.read()
        
    out_match = re.search(r'#SBATCH\s+(?:--output|-o)\s*=\s*(\S+)|#SBATCH\s+(?:--output|-o)\s+(\S+)', content)
    err_match = re.search(r'#SBATCH\s+(?:--error|-e)\s*=\s*(\S+)|#SBATCH\s+(?:--error|-e)\s+(\S+)', content)
    
    out_pat = (out_match.group(1) or out_match.group(2)) if out_match else None
    err_pat = (err_match.group(1) or err_match.group(2)) if err_match else None
    
    # If not found, check if it's default slurm-%j.out
    if not out_pat:
        out_pat = 'slurm-%j.out'
        
    # Resolve job ID variables
    job_id = os.environ.get('SLURM_JOB_ID', '')
    array_job_id = os.environ.get('SLURM_ARRAY_JOB_ID', '')
    array_task_id = os.environ.get('SLURM_ARRAY_TASK_ID', '')
    
    def resolve_pattern(pat):
        if not pat:
            return None
        # Replace %j, %A, %a
        res_pat = pat
        res_pat = res_pat.replace('%j', job_id if job_id else 'failed')
        res_pat = res_pat.replace('%A', array_job_id if array_job_id else 'failed')
        res_pat = res_pat.replace('%a', array_task_id if array_task_id else 'failed')
        return res_pat
        
    out_file = resolve_pattern(out_pat)
    err_file = resolve_pattern(err_pat)
    
    # Find files relative to script directory
    script_dir = os.path.dirname(os.path.abspath(script_path))
    
    def get_full_path(f_path):
        if not f_path:
            return None
        # If absolute
        if os.path.isabs(f_path):
            return f_path
        # Otherwise relative to script dir or current working dir
        cand1 = os.path.join(script_dir, f_path)
        if os.path.exists(cand1):
            return cand1
        cand2 = os.path.abspath(f_path)
        if os.path.exists(cand2):
            return cand2
        return cand1 # default
        
    files_to_push = []
    
    # Sync file buffers
    try:
        os.sync()
    except AttributeError:
        pass # Windows fallback
        
    for name, f_path in [('output', out_file), ('error', err_file)]:
        full_path = get_full_path(f_path)
        if full_path and os.path.exists(full_path):
            # To bypass write locking, copy to final name
            # e.g., name_final_JOBID.log
            base, ext = os.path.splitext(os.path.basename(full_path))
            dest_name = f"{base}_final_{job_id if job_id else 'failed'}{ext if ext in ['.log', '.err', '.txt'] else '.log'}"
            # If it is error file, use .err
            if name == 'error':
                dest_name = f"{base}_final_{job_id if job_id else 'failed'}.err"
                
            dest_path = os.path.join(script_dir, dest_name)
            try:
                shutil.copy2(full_path, dest_path)
                files_to_push.append(dest_path)
                print(f"[HPC EXIT HANDLER] Copied {name} log to: {dest_path}")
            except Exception as e:
                print(f"[HPC EXIT HANDLER] Error copying {name} log: {e}")
                
    if not files_to_push:
        print("[HPC EXIT HANDLER] No log files found to stage.")
        sys.exit(0)
        
    # Commit and push using git
    # Find repo root
    repo_dir = script_dir
    while repo_dir:
        if os.path.exists(os.path.join(repo_dir, '.git')):
            break
        parent = os.path.dirname(repo_dir)
        if parent == repo_dir:
            repo_dir = None
            break
        repo_dir = parent
        
    if not repo_dir:
        print("[HPC EXIT HANDLER] Could not find Git repository root.")
        sys.exit(0)
        
    # Stage files
    for fp in files_to_push:
        rel_path = os.path.relpath(fp, repo_dir)
        run_git_cmd_with_retry(['git', 'add', rel_path], cwd=repo_dir)
        
    commit_msg = f"HPC Run Failure: Logged output for job {job_id if job_id else 'failed'}"
    ret, out, err = run_git_cmd_with_retry(['git', 'commit', '-m', commit_msg], cwd=repo_dir)
    print(f"[HPC EXIT HANDLER] Git commit status: {ret}")
    
    # Pull before push to handle any concurrent commits
    run_git_cmd_with_retry(['git', 'pull', '--rebase', 'origin', 'main'], cwd=repo_dir)
    ret, out, err = run_git_cmd_with_retry(['git', 'push'], cwd=repo_dir)
    print(f"[HPC EXIT HANDLER] Git push status: {ret} stdout: {out} stderr: {err}")

if __name__ == '__main__':
    main()
