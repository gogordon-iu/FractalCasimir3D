"""
Live Cluster Progress Monitor & Automatic Git Sync Reporter
-------------------------------------------------------------
Scans BigRed 200 active Slurm jobs, reads logs, parses completed Nature validation
and Sweet Spot JSON results, generates a comprehensive markdown progress report,
and automatically commits and pushes everything to GitHub.
"""

import os
import sys
import glob
import json
import datetime
import subprocess

def main():
    repo_dir = "/N/project/gorengor_werewolf/FractalCasimir3D"
    if os.path.exists(repo_dir):
        os.chdir(repo_dir)
        
    print("==================================================")
    print(f"BIGRED 200 PROGRESS SCAN & GIT SYNC - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    # 1. Check Active Slurm Jobs
    squeue_output = ""
    try:
        sq_res = subprocess.run(["squeue", "-u", os.environ.get("USER", "gogordon")], capture_output=True, text=True)
        squeue_output = sq_res.stdout.strip()
    except Exception:
        squeue_output = "squeue command unavailable."

    # 2. Scan Nature Validation Results
    nature_json_files = sorted(glob.glob("results_nature_validation/*.json"))
    t1_files = [f for f in nature_json_files if "conv_res_" in f]
    t2_files = [f for f in nature_json_files if "dispersive_" in f]
    t3_files = [f for f in nature_json_files if "stability_6dof_" in f]
    t4_files = [f for f in nature_json_files if "matsubara_" in f or "thermal_dsi_" in f]

    t1_data = []
    for f in t1_files:
        try:
            with open(f, "r") as fp:
                t1_data.append(json.load(fp))
        except Exception:
            pass

    t2_data = []
    for f in t2_files:
        try:
            with open(f, "r") as fp:
                t2_data.append(json.load(fp))
        except Exception:
            pass

    t3_data = []
    for f in t3_files:
        try:
            with open(f, "r") as fp:
                t3_data.append(json.load(fp))
        except Exception:
            pass

    t4_data = []
    for f in t4_files:
        try:
            with open(f, "r") as fp:
                t4_data.append(json.load(fp))
        except Exception:
            pass

    # 3. Scan Sweet Spot Sweep Results (.tmp)
    sweet_spot_files = sorted(glob.glob(".tmp/meep_d_*.json") + glob.glob(".tmp/**/meep_d_*.json", recursive=True))
    sweet_spot_data = []
    for f in sweet_spot_files:
        try:
            with open(f, "r") as fp:
                data = json.load(fp)
                if isinstance(data, dict) and "force_subtracted" in data:
                    sweet_spot_data.append(data)
        except Exception:
            pass

    # 4. Check Latest Log Tail
    latest_logs = sorted(glob.glob("logs/nature_full_production_*.out") + glob.glob("logs/nature_refutation_*.out"), key=os.path.getmtime, reverse=True)
    log_tail_text = ""
    if latest_logs:
        latest_log = latest_logs[0]
        try:
            with open(latest_log, "r") as fp:
                lines = fp.readlines()
                log_tail_text = "".join(lines[-35:])
        except Exception as e:
            log_tail_text = f"Error reading log: {e}"

    # 5. Re-render figures if results are present
    try:
        subprocess.run([sys.executable, "execution/postprocess_nature_validation.py"], capture_output=True)
    except Exception:
        pass

    # 6. Build Comprehensive Markdown Report
    report_lines = []
    report_lines.append("# Live Cluster Progress Report — BigRed 200")
    report_lines.append(f"\n**Timestamp:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`  ")
    report_lines.append(f"**Cluster:** Indiana University BigRed 200 Cray EX (128-core AMD EPYC 7742)  \n")

    report_lines.append("## 1. Slurm Active Queue Status")
    report_lines.append("```")
    report_lines.append(squeue_output if squeue_output else "No active jobs in queue.")
    report_lines.append("```\n")

    report_lines.append("## 2. Nature Refutation Suite Progress Summary")
    report_lines.append(f"- **Task 1 (FDTD Grid Convergence & Tip Rounding):** `{len(t1_files)} / 24` completed files")
    report_lines.append(f"- **Task 2 (Anisotropic Dispersive Loss):** `{len(t2_files)} / 216` completed files")
    report_lines.append(f"- **Task 3 (6-DOF Mechanical Stability Matrix):** `{len(t3_files)} / 20` completed files")
    report_lines.append(f"- **Task 4 (Finite-T Matsubara DSI):** `{len(t4_files)} / 60` completed files")
    report_lines.append(f"- **Total Nature Validation Files:** `{len(nature_json_files)} / 320` completed\n")

    if t1_data:
        report_lines.append("### Task 1 Sample Grid Convergence Points:")
        report_lines.append("| Resolution (px/um) | Tip Radius r_tip (nm) | Standoff delta_s (nm) | Pressure P (Pa) | Repulsive? |")
        report_lines.append("|---|---|---|---|---|")
        for item in t1_data[:8]:
            report_lines.append(f"| {item.get('resolution')} | {item.get('r_tip_nm')} | {item.get('delta_s_nm')} | {item.get('pressure_Pa', 0.0):+.4f} | {item.get('is_repulsive')} |")
        report_lines.append("")

    if t3_data:
        report_lines.append("### Task 3 6-DOF Stability Status:")
        latest_t3 = t3_data[-1]
        report_lines.append(f"- **Equilibrium Gap $d_{{eq}}$:** `{latest_t3.get('d_eq_um')} um`")
        report_lines.append(f"- **Corrugation Angle $\\alpha$:** `{latest_t3.get('alpha_deg')} deg`")
        report_lines.append(f"- **All 6 Eigenvalues $> 0$:** `{latest_t3.get('is_unconditionally_stable_6dof')}`")
        report_lines.append(f"- **Min Eigenvalue $\\lambda_{{min}}$:** `{latest_t3.get('min_eigenvalue'):+.4e}`\n")

    report_lines.append("## 3. Sweet Spot Parameter Sweep Progress (.tmp)")
    report_lines.append(f"- **Completed Subtracted Force Calculations:** `{len(sweet_spot_data)}` points recorded.\n")

    report_lines.append("## 4. Latest Compute Node Log Output")
    report_lines.append("```")
    report_lines.append(log_tail_text if log_tail_text else "No log tail available.")
    report_lines.append("```\n")

    report_text = "\n".join(report_lines)
    report_path = "execution/LIVE_CLUSTER_PROGRESS_REPORT.md"
    with open(report_path, "w") as fp:
        fp.write(report_text)
    print(f"Generated live report at '{report_path}'.")

    # 7. Git Add, Commit, and Push
    print("\nSyncing all results, logs, and report to GitHub...")
    subprocess.run(["git", "add", "-A"])
    commit_msg = f"Auto-sync live progress report and results ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    subprocess.run(["git", "commit", "-m", commit_msg])
    push_res = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    if push_res.returncode != 0:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"])
        push_res = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    
    if push_res.returncode == 0:
        print("[SUCCESS] Successfully pushed all latest cluster results to GitHub!")
    else:
        print(f"[WARNING] Git push output:\n{push_res.stderr}\n{push_res.stdout}")

    print("==================================================")
    print("PROGRESS MONITOR & SYNC COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    main()
