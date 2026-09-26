#!/usr/bin/env python3
"""
Deep Casimir HPC Real-Time Monitor & Diagnostic Dashboard for BigRed 200
-------------------------------------------------------------------------
Replaces coarse `squeue -u $USER` with full physical, numerical, and
progress transparency for every Casimir run on the cluster:

1. De-truncates job names and maps each job to its exact physics campaign:
   - Sierpinski-Cantor Forest (8-Task Suite)
   - Dual-Fractal Rotary Casimir Clutch (8-Task Suite)
   - Quantum Clutch: Menger Spire vs Sieve (10-Task Suite)
   - Geometric Vacuum Casimir Repulsion (Levin-Johnson 4-Task Suite)
   - Fractal Control & Shuffled 73-Element Suite
   - 224-Task Sweet Spot Sweep / Phase 1 / Phase 2 / Phase 3
2. Inspects active FDTD moment checkpoints (.tmp/chk_moments_*.json):
   - Computes exact % progress (e.g. 54 / 72 moments, 75.0%)
   - Shows graphical progress bar: [████████████████░░░░]
   - Estimates time remaining (ETA) based on average moment duration
3. Displays physical parameters for each job:
   - Generation N, rotation angle theta, tip clearance z_tip, average distance <d>,
     material, resolution, and expected regime (Repulsive vs Attractive)
4. Displays live log snippet (latest MEEP time step or completed moment)
5. Summarizes campaign-wide status: Total, Completed, Running, Pending, and Levitation Yield.

Usage:
  python execution/monitor_all_casimir_runs.py            # Single snapshot
  python execution/monitor_all_casimir_runs.py -w         # Continuous live watch (every 20s)
  python execution/monitor_all_casimir_runs.py --tail 3   # Live tail of Task 3 log
"""

import os
import re
import sys
import time
import glob
import json
import argparse
import datetime
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ANSI terminal colors (gracefully ignored if not supported)
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_BLUE = "\033[34m"
C_DIM = "\033[2m"

# Campaign mapping registry
CAMPAIGNS = {
    "cantor_forest": {
        "title": "Sierpinski-Cantor Forest (8-Task Suite)",
        "config_dir": "sweep_configs_cantor_forest",
        "results_dir": "results_cantor_forest",
        "log_pattern": ".tmp/cantor_forest_*.out",
        "total_tasks": 8,
        "moments_per_task": 72  # 36 both + 36 self at nmax=1
    },
    "fractal_clutch": {
        "title": "Dual-Fractal Rotary Clutch (8-Task Suite)",
        "config_dir": "sweep_configs_fractal_clutch",
        "results_dir": "results_fractal_rotary_clutch",
        "log_pattern": ".tmp/fractal_clutch_*.out",
        "total_tasks": 8,
        "moments_per_task": 72
    },
    "clutch_campaign": {
        "title": "Quantum Clutch: Menger Spire vs Sieve (10 Tasks)",
        "config_dir": "sweep_configs_clutch",
        "results_dir": "results_clutch",
        "log_pattern": "logs/clutch_campaign_*.out",
        "total_tasks": 10,
        "moments_per_task": 72
    },
    "geom_repulse": {
        "title": "Levin-Johnson Geometric Repulsion (4 Tasks)",
        "config_dir": "sweep_configs_geometric_repulsion",
        "results_dir": "results_geometric_repulsion",
        "log_pattern": ".tmp/geom_repulse_*.out",
        "total_tasks": 4,
        "moments_per_task": 72
    },
    "fractal_control": {
        "title": "Fractal Control & Shuffled 73-Element Suite",
        "config_dir": "sweep_configs_fractal_control",
        "results_dir": "results_fractal_control",
        "log_pattern": ".tmp/fractal_control_*.out",
        "total_tasks": 12,
        "moments_per_task": 72
    },
    "sweet_spot": {
        "title": "Sweet Spot Parameter Sweep (224 Tasks)",
        "config_dir": "sweep_configs_sweet_spot",
        "results_dir": "results_sweet_spot",
        "log_pattern": ".tmp/sweet_spot_*.out",
        "total_tasks": 224,
        "moments_per_task": 72
    }
}


def make_bar(pct, width=20):
    """Draws a clean, universally compatible progress bar."""
    filled = int(width * pct / 100.0)
    filled = max(0, min(width, filled))
    bar = "=" * filled + "-" * (width - filled)
    return bar


def query_slurm_jobs(user):
    """Queries squeue with de-truncated format fields."""
    cmd = [
        "squeue", "-u", user,
        "-o", "%i|%P|%j|%T|%M|%l|%D|%R"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = res.stdout.strip().splitlines()
        if len(lines) <= 1:
            return []
        
        jobs = []
        for line in lines[1:]:
            parts = line.strip().split("|")
            if len(parts) >= 8:
                raw_id, part, name, state, elapsed, time_lim, nodes, reason = parts[:8]
                
                # Check for array job index e.g. "12345_1" or "12345_[3-8]"
                array_task = None
                m = re.match(r"^(\d+)_\[?(\d+)", raw_id)
                if m:
                    base_id = m.group(1)
                    array_task = int(m.group(2))
                else:
                    base_id = raw_id
                    try:
                        array_task = int(raw_id)
                    except ValueError:
                        array_task = None

                jobs.append({
                    "job_id": raw_id,
                    "base_id": base_id,
                    "task_id": array_task,
                    "partition": part,
                    "name": name,
                    "state": state,
                    "elapsed": elapsed,
                    "time_limit": time_lim,
                    "nodes": nodes,
                    "reason_or_node": reason
                })
        return jobs
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def identify_campaign(job_name):
    """Identifies campaign metadata from job name."""
    clean_name = job_name.lower()
    for key, meta in CAMPAIGNS.items():
        if key in clean_name or clean_name in key:
            return key, meta
    if "cantor" in clean_name:
        return "cantor_forest", CAMPAIGNS["cantor_forest"]
    if "clutch" in clean_name:
        return "fractal_clutch", CAMPAIGNS["fractal_clutch"]
    if "repulse" in clean_name or "repulsion" in clean_name:
        return "geom_repulse", CAMPAIGNS["geom_repulse"]
    return None, None


def load_task_config(campaign_meta, task_id):
    """Loads JSON config for task if available."""
    if not campaign_meta or task_id is None:
        return None
    cfg_dir = os.path.join(REPO_ROOT, campaign_meta["config_dir"])
    cfg_file = os.path.join(cfg_dir, f"config_{task_id:03d}.json")
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def get_moment_progress(campaign_key, task_id, cfg_data):
    """Reads completed moments from .tmp/ checkpoints."""
    if not cfg_data:
        return 0, 72

    N = cfg_data.get("N_fractal", 1)
    th = cfg_data.get("theta_deg", cfg_data.get("theta", 0.0))
    z_tip = cfg_data.get("z_tip_um", cfg_data.get("d", 0.015))
    nmax = cfg_data.get("nmax", 1)
    total_moments = 36 * nmax * 2  # 'both' + 'self'

    done_moments = 0
    # Scan both configurations
    for cfg_type in ["both", "self"]:
        # Check full config checkpoint
        full_pattern = os.path.join(REPO_ROOT, ".tmp", f"chk_*{task_id:03d}*{cfg_type}.json")
        matching_full = [f for f in glob.glob(full_pattern) if "chk_moments_" not in f]
        if matching_full:
            done_moments += 36 * nmax
            continue

        # Check incremental moments
        mom_pattern = os.path.join(REPO_ROOT, ".tmp", f"chk_moments_*{task_id:03d}*{cfg_type}.json")
        matching_mom = glob.glob(mom_pattern)
        if not matching_mom:
            # Fallback by theta and z_tip
            mom_pattern = os.path.join(REPO_ROOT, ".tmp", f"chk_moments_*th_{th:.1f}*{cfg_type}.json")
            matching_mom = glob.glob(mom_pattern)

        for mf in matching_mom:
            try:
                with open(mf, "r") as f:
                    cdata = json.load(f)
                    done_moments += len(cdata.get("completed_moments", {}))
            except Exception:
                pass

    return min(done_moments, total_moments), total_moments


def get_latest_log_line(job_info):
    """Extracts the last non-empty line of the job's Slurm log."""
    job_id = job_info["base_id"]
    task_id = job_info["task_id"]
    patterns = [
        os.path.join(REPO_ROOT, ".tmp", f"*{job_id}_{task_id}*.out"),
        os.path.join(REPO_ROOT, ".tmp", f"*{job_id}*.out"),
        os.path.join(REPO_ROOT, "logs", f"*{job_id}_{task_id}*.out"),
        os.path.join(REPO_ROOT, "logs", f"*{job_id}*.out")
    ]
    for pat in patterns:
        files = glob.glob(pat)
        if files:
            try:
                with open(files[0], "r", errors="ignore") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                    if lines:
                        # Find last progress report or last line
                        for l in reversed(lines):
                            if "Done moment" in l or "force_integral" in l or "Starting" in l or "COMPLETE" in l:
                                return l
                        return lines[-1]
            except Exception:
                pass
    return "Running FDTD time-stepping..."


def render_dashboard():
    """Renders the comprehensive cluster status dashboard."""
    user = os.environ.get("USER", "gogordon")
    jobs = query_slurm_jobs(user)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 115)
    print(f" {C_BOLD}{C_CYAN}3D FRACTAL CASIMIR EFFECT: BIGRED 200 PRODUCTION MONITOR{C_RESET}")
    print(f" Cluster: {C_BOLD}BigRed 200 (Cray EX / Slurm){C_RESET} | User: {C_BOLD}{user}{C_RESET} | Time: {now_str}")
    print("=" * 115)

    # -------------------------------------------------------------------------
    # 1. Active Slurm Jobs (Detailed Breakdown)
    # -------------------------------------------------------------------------
    print(f"\n{C_BOLD}[1] ACTIVE RUNNING & QUEUED JOBS (De-truncated & Decoded){C_RESET}")
    print("-" * 115)

    if not jobs:
        print(f"  {C_YELLOW}No active jobs found in Slurm queue for user '{user}'.{C_RESET}")
        print(f"  {C_DIM}To submit a new run, execute: bash execution/submit_cantor_forest_pipeline.sh{C_RESET}")
    else:
        for idx, j in enumerate(jobs, start=1):
            jid = j["job_id"]
            state = j["state"]
            part = j["partition"]
            elapsed = j["elapsed"]
            limit = j["time_limit"]
            node = j["reason_or_node"]
            camp_key, camp_meta = identify_campaign(j["name"])

            camp_title = camp_meta["title"] if camp_meta else j["name"]
            cfg_data = load_task_config(camp_meta, j["task_id"])

            state_color = C_GREEN if state == "RUNNING" else C_YELLOW if state == "PENDING" else C_CYAN

            print(f" {C_BOLD}#{idx:02d} | Job {jid:<12} | Partition: {part:<8} | State: {state_color}{state:<9}{C_RESET} | Time: {elapsed} / {limit} | Node: {node}")
            print(f"      Campaign: {C_BOLD}{camp_title}{C_RESET}")

            if cfg_data:
                N = cfg_data.get("N_fractal", "-")
                th = cfg_data.get("theta_deg", cfg_data.get("theta", 0.0))
                ztip = cfg_data.get("z_tip_um", 0.0) * 1e3
                davg = cfg_data.get("d_average_um", 0.0) * 1e3
                mat = cfg_data.get("material", "Gold")
                res = cfg_data.get("resolution", 60)
                n_pillars = cfg_data.get("num_pillars", 1 if N == 1 else 73)
                regime = cfg_data.get("expected_regime", "REPULSIVE")

                reg_color = C_GREEN if "REPULSIVE" in regime else C_RED if "ATTRACTIVE" in regime else C_YELLOW
                print(f"      Physics:  {C_CYAN}N={N}{C_RESET} ({n_pillars} pillars) | {C_CYAN}theta={th:.1f} deg{C_RESET} | {C_CYAN}z_tip={ztip:.2f} nm{C_RESET} | <d>={davg:.1f} nm | Mat: {mat} | R={res} px/um | Exp: {reg_color}{regime}{C_RESET}")

                if state == "RUNNING":
                    done_m, tot_m = get_moment_progress(camp_key, j["task_id"], cfg_data)
                    pct = (done_m / float(tot_m)) * 100.0 if tot_m > 0 else 0.0
                    bar = make_bar(pct, width=24)
                    log_line = get_latest_log_line(j)
                    print(f"      Progress: [{C_GREEN}{bar}{C_RESET}] {C_BOLD}{pct:5.1f}%{C_RESET} ({done_m}/{tot_m} moments)")
                    print(f"      Latest:   {C_DIM}{log_line[:85]}{C_RESET}")
            else:
                log_line = get_latest_log_line(j)
                print(f"      Latest:   {C_DIM}{log_line[:85]}{C_RESET}")
            print("  " + "-" * 110)

    # -------------------------------------------------------------------------
    # 2. Comprehensive Campaign Completion Matrix
    # -------------------------------------------------------------------------
    print(f"\n{C_BOLD}[2] CAMPAIGN EXECUTION STATUS & LEVITATION YIELD{C_RESET}")
    print("-" * 115)
    print(f"{'Campaign':<42}{'Tasks':<12}{'Completed':<14}{'Repulsive':<14}{'Status':<16}")
    print("-" * 115)

    for ckey, cmeta in CAMPAIGNS.items():
        res_dir = os.path.join(REPO_ROOT, cmeta["results_dir"])
        completed_files = glob.glob(os.path.join(res_dir, "task_*.json"))
        num_done = len(completed_files)
        total = cmeta["total_tasks"]

        repulsive_count = 0
        for rf in completed_files:
            try:
                with open(rf, "r") as fp:
                    rdata = json.load(fp)
                    f_net = rdata.get("force_net_fN_per_cell", rdata.get("force_net_fN", 0.0))
                    if f_net > 0:
                        repulsive_count += 1
            except Exception:
                pass

        # Check if active in queue
        active_in_queue = sum(1 for j in jobs if ckey in j["name"].lower() or (j["name"].lower() in ckey))

        if active_in_queue > 0:
            status_str = f"{C_GREEN}RUNNING ({active_in_queue} in queue){C_RESET}"
        elif num_done == total:
            status_str = f"{C_BOLD}{C_GREEN}100% COMPLETE{C_RESET}"
        elif num_done > 0:
            status_str = f"{C_YELLOW}PARTIAL ({num_done}/{total}){C_RESET}"
        else:
            status_str = f"{C_DIM}READY TO RUN{C_RESET}"

        bar = make_bar((num_done / float(total)) * 100.0, width=12)
        print(f"{cmeta['title']:<42}{total:<12}{num_done:<6} [{bar}] {repulsive_count:<14}{status_str:<16}")

    print("=" * 115)
    print(f" {C_DIM}Tip: Run with '-w' for continuous 20s live-refresh: python execution/monitor_all_casimir_runs.py -w{C_RESET}")
    print(f" {C_DIM}     To view full log of a task: python execution/monitor_all_casimir_runs.py --tail <task_id>{C_RESET}")
    print("=" * 115 + "\n")


def tail_task_log(task_id):
    """Displays the last 50 lines of log file for a specific task."""
    patterns = [
        os.path.join(REPO_ROOT, ".tmp", f"*_{task_id:03d}*.out"),
        os.path.join(REPO_ROOT, ".tmp", f"*_{task_id}*.out"),
        os.path.join(REPO_ROOT, "logs", f"*_{task_id}*.out")
    ]
    matching = []
    for p in patterns:
        matching.extend(glob.glob(p))
    if not matching:
        print(f"No log files found matching Task {task_id}.")
        return
    log_file = matching[0]
    print(f"\nDisplaying last 40 lines of {log_file}:\n" + "-" * 80)
    try:
        with open(log_file, "r", errors="ignore") as f:
            lines = f.readlines()
            for l in lines[-40:]:
                print(l, end="")
    except Exception as e:
        print(f"Error reading log: {e}")
    print("-" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Deep Casimir BigRed 200 Real-Time Monitor")
    parser.add_argument("-w", "--watch", action="store_true", help="Continuous live watch mode (refreshes every 20s)")
    parser.add_argument("--interval", type=int, default=20, help="Refresh interval in seconds for watch mode")
    parser.add_argument("--tail", type=int, default=None, help="Display recent log output for specified task ID")
    args = parser.parse_args()

    if args.tail is not None:
        tail_task_log(args.tail)
        return

    if args.watch:
        try:
            while True:
                # Clear terminal screen
                os.system("cls" if os.name == "nt" else "clear")
                render_dashboard()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nExiting live monitor.")
    else:
        render_dashboard()


if __name__ == "__main__":
    main()
