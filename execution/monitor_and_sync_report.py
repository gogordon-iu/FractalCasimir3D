"""
Live Cluster Progress Monitor & Automatic Git Sync Reporter
-------------------------------------------------------------
Scans BigRed 200 active Slurm jobs, reads logs, parses completed Nature validation
and Sweet Spot JSON results, generates a comprehensive markdown progress report,
and automatically commits and pushes selected results to GitHub.
"""

import os
import sys
import glob
import json
import datetime
import math
import subprocess


MAX_STAGE_BYTES = 50 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 180


def warn(message):
    print(f"[WARNING] {message}", file=sys.stderr)


def run_analysis(arguments):
    command = [sys.executable] + arguments
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        warn(f"Could not run {' '.join(command)}: {exc}")
        return

    if result.returncode != 0:
        warn(
            f"{' '.join(command)} failed with exit code {result.returncode}:\n"
            f"{result.stderr or result.stdout}"
        )


def load_results(paths):
    results = []
    for path in paths:
        try:
            with open(path, "r") as fp:
                data = json.load(fp)
        except (OSError, ValueError, UnicodeError) as exc:
            warn(f"Could not read JSON result '{path}': {exc}")
            continue
        if not isinstance(data, dict):
            warn(f"Skipping '{path}': expected a JSON object.")
            continue
        results.append(data)
    return results


def format_number(value, spec):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "N/A"
    try:
        return format(value, spec) if math.isfinite(value) else "N/A"
    except (ValueError, OverflowError):
        return "N/A"


def stage_result_paths(paths):
    files = set()

    def consider_file(path):
        # Do not follow symlinks into unrelated files or directories.
        if os.path.islink(path):
            warn(f"Skipping symlink '{path}'.")
            return
        try:
            if os.path.isfile(path):
                if os.path.getsize(path) > MAX_STAGE_BYTES:
                    warn(f"Skipping '{path}': exceeds the 50 MB staging limit.")
                else:
                    files.add(path)
        except OSError as exc:
            warn(f"Could not inspect '{path}': {exc}")

    def walk_error(exc):
        warn(f"Could not scan result directory: {exc}")

    for path in paths:
        if not os.path.lexists(path):
            continue
        if os.path.islink(path):
            warn(f"Skipping symlink '{path}'.")
            continue
        if os.path.isdir(path):
            for root, directories, filenames in os.walk(
                path, followlinks=False, onerror=walk_error
            ):
                directories[:] = [
                    name for name in directories
                    if name != ".git" and not os.path.islink(os.path.join(root, name))
                ]
                for filename in filenames:
                    consider_file(os.path.join(root, filename))
        else:
            consider_file(path)

    # Explicit file arguments prevent directory staging from including large files.
    for path in sorted(files):
        result = subprocess.run(
            ["git", "add", "--", path],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            warn(f"Could not stage '{path}':\n{result.stderr or result.stdout}")
            return False
    return True


def main():
    repo_dir = "/N/project/gorengor_werewolf/FractalCasimir3D"
    if os.path.exists(repo_dir):
        os.chdir(repo_dir)

    print("==================================================")
    print(f"BIGRED 200 PROGRESS SCAN & GIT SYNC - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    # Refresh analytical Tasks 2, 3, 4 and figures with latest audited code (<10s).
    analysis_commands = [
        ["execution/run_anisotropic_dispersive_lifshitz.py", "--d", "0.15", "--material-top", "BlackPhosphorus", "--medium", "Teflon_AF", "--theta", "90.0", "--outdir", "results_nature_validation"],
        ["execution/run_anisotropic_dispersive_lifshitz.py", "--d", "0.15", "--material-top", "ReS2", "--medium", "Teflon_AF", "--theta", "90.0", "--outdir", "results_nature_validation"],
        ["execution/run_6dof_stability_analyzer.py", "--d-eq", "0.15", "--alpha", "75.0", "--theta-z", "90.0", "--outdir", "results_nature_validation"],
        ["execution/run_thermal_matsubara_dsi.py", "--d", "0.15", "--T", "300.0", "--sweep-all", "--outdir", "results_nature_validation"],
        ["execution/run_sweet_spot_analyzer.py"],
        ["execution/generate_sweet_spot_tables.py"],
        ["execution/postprocess_nature_validation.py"],
    ]
    for command in analysis_commands:
        run_analysis(command)

    # 1. Check Active Slurm Jobs
    squeue_output = ""
    try:
        sq_res = subprocess.run(
            ["squeue", "-u", os.environ.get("USER", "gogordon")],
            capture_output=True,
            text=True,
        )
        if sq_res.returncode == 0:
            squeue_output = sq_res.stdout.strip()
        else:
            squeue_output = f"squeue failed: {sq_res.stderr.strip() or sq_res.stdout.strip()}"
            warn(squeue_output)
    except (OSError, subprocess.SubprocessError) as exc:
        squeue_output = f"squeue command unavailable: {exc}"
        warn(squeue_output)

    # 2. Scan Nature Validation Results
    nature_json_files = sorted(glob.glob("results_nature_validation/*.json"))
    t1_files = [f for f in nature_json_files if "conv_res_" in f]
    t2_files = [f for f in nature_json_files if "dispersive_" in f]
    t3_files = [f for f in nature_json_files if "stability_6dof_" in f]
    t4_files = [f for f in nature_json_files if "matsubara_" in f or "thermal_dsi_" in f]

    t1_data = load_results(t1_files)
    t2_data = load_results(t2_files)
    t3_data = load_results(t3_files)
    t4_data = load_results(t4_files)

    # 3. Scan Sweet Spot Sweep Results (.tmp)
    sweet_spot_files = sorted(set(
        glob.glob(".tmp/meep_d_*.json")
        + glob.glob(".tmp/**/meep_d_*.json", recursive=True)
    ))
    sweet_spot_data = [
        data for data in load_results(sweet_spot_files)
        if "force_subtracted" in data or "force_both" in data
    ]

    # 4. Check Latest Log Tail
    log_paths = (
        glob.glob("logs/nature_full_production_*.out")
        + glob.glob("logs/nature_refutation_*.out")
    )
    log_times = []
    for path in log_paths:
        try:
            log_times.append((os.path.getmtime(path), path))
        except OSError as exc:
            warn(f"Could not inspect log '{path}': {exc}")

    latest_logs = [
        path for _, path in sorted(log_times, reverse=True)
    ]
    log_tail_text = ""
    if latest_logs:
        latest_log = latest_logs[0]
        try:
            with open(latest_log, "r") as fp:
                lines = fp.readlines()
                log_tail_text = "".join(lines[-35:])
        except (OSError, UnicodeError) as exc:
            log_tail_text = f"Error reading log: {exc}"
            warn(f"Could not read '{latest_log}': {exc}")

    # 5. Re-render figures if results are present
    run_analysis(["execution/postprocess_nature_validation.py"])

    # 6. Build Comprehensive Markdown Report
    report_lines = []
    report_lines.append("# Live Cluster Progress Report — BigRed 200")
    report_lines.append(f"\n**Timestamp:** `{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`  ")
    report_lines.append("**Cluster:** Indiana University BigRed 200 Cray EX (128-core AMD EPYC 7742)  \n")

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
            pressure = format_number(item.get("pressure_Pa", 0.0), "+.4f")
            report_lines.append(f"| {item.get('resolution')} | {item.get('r_tip_nm')} | {item.get('delta_s_nm')} | {pressure} | {item.get('is_repulsive')} |")
        report_lines.append("")

    if t3_data:
        report_lines.append("### Task 3 6-DOF Stability Status:")
        latest_t3 = t3_data[-1]
        report_lines.append(f"- **Equilibrium Gap $d_{{eq}}$:** `{latest_t3.get('d_eq_um')} um`")
        report_lines.append(f"- **Corrugation Angle $\\alpha$:** `{latest_t3.get('alpha_deg')} deg`")
        report_lines.append(f"- **All 6 Eigenvalues $> 0$:** `{latest_t3.get('is_unconditionally_stable_6dof')}`")
        min_eigenvalue = format_number(latest_t3.get("min_eigenvalue"), "+.4e")
        report_lines.append(f"- **Min Eigenvalue $\\lambda_{{min}}$:** `{min_eigenvalue}`\n")

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

    # 7. Stage only approved results and reports, then commit, pull, and push.
    print("\nSyncing selected results and reports to GitHub...")
    stage_paths = [
        "results",
        "results_nature_meep_verification",
        "results_rotational_z_eff_meep",
        "results_clutch_pilot",
        "figures",
        "FORENSIC_INCIDENT_REPORT.md",
        report_path,
    ]
    try:
        if not stage_result_paths(stage_paths):
            warn("Git sync aborted because staging failed.")
            return

        commit_msg = f"Auto-sync live progress report and results ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        commit_res = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if commit_res.returncode != 0:
            # A clean index needs no commit; other commit failures must stop sync.
            diff_res = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT_SECONDS,
            )
            if diff_res.returncode != 0:
                warn(f"Git commit failed:\n{commit_res.stderr}\n{commit_res.stdout}")
                return
            print("No staged changes to commit.")

        pull_res = subprocess.run(
            ["git", "pull", "--rebase", "--autostash", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if pull_res.returncode != 0:
            warn(f"Git pull failed; push skipped:\n{pull_res.stderr}\n{pull_res.stdout}")
            return

        push_res = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if push_res.returncode == 0:
            print("[SUCCESS] Successfully pushed selected cluster results to GitHub!")
        else:
            warn(f"Git push output:\n{push_res.stderr}\n{push_res.stdout}")
    except (OSError, subprocess.SubprocessError) as exc:
        warn(f"Git sync failed: {exc}")
        return

    print("==================================================")
    print("PROGRESS MONITOR & SYNC COMPLETE")
    print("==================================================")


if __name__ == "__main__":
    main()
