import os
import sys
import subprocess
import glob
import datetime

def main():
    L_vals = [3.0]
    summary_lines = []
    summary_lines.append("==================================================")
    summary_lines.append(f"TWIST SWEEP STATUS SUMMARY - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    summary_lines.append("==================================================\n")
    
    staged_any = False
    
    # Locate the python executable in the conda environment
    python_bin = os.path.join(os.environ.get("CONDA_PREFIX", sys.exec_prefix), "bin", "python")
    if not os.path.exists(python_bin):
        python_bin = sys.executable  # fallback
        
    print(f"Using python: {python_bin}")
    
    for L in L_vals:
        print(f"\nProcessing L = {L:.2f} um...")
        
        # Run run_twist_sweep.py with --plot-only
        cmd = [python_bin, "execution/run_twist_sweep.py", "--L", f"{L:.2f}", "--plot-only"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        if res.returncode == 0:
            summary_lines.append(f"L = {L:.2f} um: COMPLETED SUCCESSFULLY")
            # Find the most recently created results directory for this L
            dirs = glob.glob(f"results_twist_L_{L:.2f}_*")
            if dirs:
                latest_dir = max(dirs, key=os.path.getmtime)
                print(f" -> Found completed directory: {latest_dir}")
                # Stage files inside the results directory
                subprocess.run(["git", "add", latest_dir])
                staged_any = True
                summary_lines.append(f"   -> Results pushed: {latest_dir}\n")
            else:
                summary_lines.append("   -> WARNING: Completed exit code but no results directory found!\n")
        else:
            summary_lines.append(f"L = {L:.2f} um: INCOMPLETE (FDTD runs still missing)")
            # Parse missing files from the output
            missing_info = []
            for line in res.stdout.splitlines():
                if line.strip().startswith("- Material:"):
                    missing_info.append(line.strip())
            
            if missing_info:
                for mi in missing_info:
                    summary_lines.append(f"   {mi}")
            else:
                summary_lines.append("   -> Reason: Unknown error or missing cache files")
                print(f"Subprocess stderr:\n{res.stderr}")
            summary_lines.append("")
            
    summary_lines.append("==================================================")
    
    # Write the summary to file
    summary_file = "execution/sweep_status_summary.txt"
    with open(summary_file, "w") as f:
        f.write("\n".join(summary_lines) + "\n")
    print(f"\nWritten status summary to {summary_file}")
    
    # Stage the summary file
    subprocess.run(["git", "add", summary_file])
    
    # Check if there are staged changes to commit
    diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff_res.returncode != 0:
        print("Committing and pushing results/summary to GitHub...")
        subprocess.run(["git", "commit", "-m", "Auto-sync twist sweep results and status summary from BigRed200"])
        # Rebase from origin/main to prevent push rejection
        subprocess.run(["git", "pull", "--rebase", "origin", "main"])
        subprocess.run(["git", "push", "origin", "main"])
        print("Git sync complete!")
    else:
        print("No changes to push.")

if __name__ == "__main__":
    main()
