#!/usr/bin/env python3
"""
Deep Casimir HPC Real-Time Monitor & Diagnostic Dashboard for BigRed 200
-------------------------------------------------------------------------
Displays active Slurm jobs, campaign physics, checkpoint moment progress,
live log snippets, and campaign completion/levitation status.

Usage:
  python execution/monitor_all_casimir_runs.py
  python execution/monitor_all_casimir_runs.py -w
  python execution/monitor_all_casimir_runs.py --tail 3
"""

import os
import re
import sys
import time
import glob
import json
import math
import argparse
import datetime
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ANSI terminal colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_BLUE = "\033[34m"
C_DIM = "\033[2m"

CAMPAIGNS = {
    "cantor_forest": {
        "title": "Sierpinski-Cantor Forest (8-Task Suite)",
        "config_dir": "sweep_configs_cantor_forest",
        "results_dir": "results_cantor_forest",
        "log_pattern": ".tmp/cantor_forest_*.out",
        "total_tasks": 8,
        "moments_per_task": 72
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
    },
    "concentric_ring": {
        "title": "Concentric Cantor-Ring Rotary Clutch ('The One Ring', 17 Tasks)",
        "config_dir": "sweep_configs_concentric_ring",
        "results_dir": "results_concentric_ring",
        "log_pattern": ".tmp/concentric_ring_*.out",
        "total_tasks": 17,
        "moments_per_task": 72
    },
    "clutch_pilot": {
        "title": "Clutch Pilot",
        "slurm_name": "fce_clt2",
        "config_dir": "sweep_configs_clutch_pilot",
        "results_dir": "results_clutch_pilot",
        "log_pattern": ".tmp/fce_clt2_*.out",
        "total_tasks": None,
        "moments_per_task": 144,
        "config_types": ["both", "top", "bottom", "empty"]
    },
    "rotational_z_eff_meep": {
        "title": "Rotational Effective-Separation MEEP",
        "slurm_name": "fce_mrot",
        "config_dir": "sweep_configs_rotational_z_eff_meep",
        "results_dir": "results_rotational_z_eff_meep",
        "log_pattern": ".tmp/fce_mrot_*.out",
        "total_tasks": None,
        "moments_per_task": 144,
        "config_types": ["both", "top", "bottom", "empty"]
    },
    "nature_meep_verification": {
        "title": "Nature MEEP Verification",
        "slurm_name": "fce_mver",
        "config_dir": "sweep_configs_nature_meep_verification",
        "results_dir": "results_nature_meep_verification",
        "log_pattern": ".tmp/fce_mver_*.out",
        "total_tasks": None,
        "moments_per_task": 144,
        "config_types": ["both", "top", "bottom", "empty"]
    }
}


def finite_number(value, default=0.0):
    """Converts numeric input without propagating NaNs or infinities."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def make_bar(pct, width=20):
    """Draws a clean, universally compatible progress bar."""
    pct = max(0.0, min(100.0, finite_number(pct)))
    filled = int(width * pct / 100.0)
    filled = max(0, min(width, filled))
    return "=" * filled + "-" * (width - filled)


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
            parts = [part.strip() for part in line.strip().split("|")]
            if len(parts) >= 8:
                raw_id, part, name, state, elapsed, time_lim, nodes, reason = parts[:8]

                # Array job index, e.g. "12345_1" or "12345_[3-8]".
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
    except (subprocess.SubprocessError, OSError):
        return []


def identify_campaign(job_name):
    """Identifies campaign metadata from job name."""
    if not isinstance(job_name, str) or not job_name.strip():
        return None, None
    clean_name = job_name.strip().lower()

    # Explicit names take precedence over broad legacy aliases.
    for key, meta in CAMPAIGNS.items():
        slurm_name = meta.get("slurm_name")
        if key in clean_name or (slurm_name and slurm_name in clean_name):
            return key, meta

    if "concentric" in clean_name or "ring" in clean_name:
        return "concentric_ring", CAMPAIGNS["concentric_ring"]
    if "cantor" in clean_name:
        return "cantor_forest", CAMPAIGNS["cantor_forest"]
    if "fractal_clutch" in clean_name:
        return "fractal_clutch", CAMPAIGNS["fractal_clutch"]
    if "clutch" in clean_name:
        return "clutch_campaign", CAMPAIGNS["clutch_campaign"]
    if "geom_repulse" in clean_name or "repulse" in clean_name or "repulsion" in clean_name:
        return "geom_repulse", CAMPAIGNS["geom_repulse"]
    if "control" in clean_name:
        return "fractal_control", CAMPAIGNS["fractal_control"]
    if "sweet" in clean_name:
        return "sweet_spot", CAMPAIGNS["sweet_spot"]
    for key, meta in CAMPAIGNS.items():
        if clean_name in key:
            return key, meta
    return None, None


def load_task_config(campaign_meta, task_id):
    """Loads JSON config for task if available."""
    if not campaign_meta or task_id is None:
        return None
    cfg_dir = os.path.join(REPO_ROOT, campaign_meta["config_dir"])
    try:
        cfg_file = os.path.join(cfg_dir, f"config_{task_id:03d}.json")
        with open(cfg_file, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def get_latest_log_line(job_info):
    """Extracts the last non-empty progress line of the job's Slurm log."""
    if not job_info:
        return "Running FDTD time-stepping..."
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
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        for line in reversed(lines):
                            if any(marker in line for marker in (
                                "Done moment", "force_integral", "Starting", "COMPLETE"
                            )):
                                return line
                        return lines[-1]
            except OSError:
                pass
    return "Running FDTD time-stepping..."


def checkpoint_patterns(campaign_key, task_id, cfg_data, cfg_type):
    """Returns full and moment checkpoint patterns for one simulation pass."""
    th = finite_number(cfg_data.get("theta_deg", cfg_data.get("theta", 0.0)))
    tmp_dir = os.path.join(REPO_ROOT, ".tmp")

    if campaign_key == "clutch_campaign":
        d_val = finite_number(cfg_data.get("d", 0.04), 0.04)
        prefix = f"v4_d_{d_val:.4f}_*th_{th:.1f}"
    elif campaign_key == "geom_repulse":
        d_val = finite_number(cfg_data.get("d", 0.05), 0.05)
        prefix = f"v3_d_{d_val:.4f}"
    elif task_id is None:
        return [], []
    else:
        task_prefix = "cantor" if campaign_key == "cantor_forest" else campaign_key
        try:
            prefix = f"{task_prefix}_task_{task_id:03d}"
        except (TypeError, ValueError):
            return [], []

    full_patterns = [os.path.join(tmp_dir, f"chk_{prefix}_*_{cfg_type}.json")]
    moment_patterns = [os.path.join(tmp_dir, f"chk_moments_{prefix}_*_{cfg_type}.json")]

    if campaign_key == "concentric_ring":
        moment_patterns.append(
            os.path.join(tmp_dir, f"chk_moments_v3_{prefix}_*_{cfg_type}.json")
        )
    return full_patterns, moment_patterns


def get_config_types(campaign_key, task_id, cfg_data, log_line=""):
    """Determines whether this task uses two or four simulation passes."""
    two_passes = ["both", "self"]
    four_passes = ["both", "top", "bottom", "empty"]
    meta = CAMPAIGNS.get(campaign_key, {})

    for source in (cfg_data, meta):
        for key in ("config_types", "configurations", "passes"):
            value = source.get(key)
            if isinstance(value, dict):
                value = list(value)
            if isinstance(value, (list, tuple)):
                if len(value) in (2, 4) and all(isinstance(v, str) and v for v in value):
                    return [v.lower() for v in value]
            if key == "passes" and finite_number(value) in (2, 4):
                return four_passes if finite_number(value) == 4 else two_passes
        for key in ("num_passes", "n_passes", "num_configs", "n_configs"):
            count = finite_number(source.get(key))
            if count in (2, 4):
                return four_passes if count == 4 else two_passes
        if source.get("inclusion_exclusion") is True:
            return four_passes
        # Explicit task settings override campaign defaults.
        if source is cfg_data:
            for cfg_type in four_passes[1:]:
                full_patterns, moment_patterns = checkpoint_patterns(
                    campaign_key, task_id, cfg_data, cfg_type
                )
                if any(glob.glob(pat) for pat in full_patterns + moment_patterns):
                    return four_passes
            if re.search(r"\(Config:\s*(top|bottom|empty)\)", log_line, re.IGNORECASE):
                return four_passes

    return two_passes


def get_moment_progress(campaign_key, task_id, cfg_data, job_info=None):
    """Computes completed moments from results, checkpoints, and Slurm logs."""
    camp_meta = CAMPAIGNS.get(campaign_key)
    if not isinstance(cfg_data, dict) or not cfg_data:
        return 0, (camp_meta or {}).get("moments_per_task", 72)

    th = finite_number(cfg_data.get("theta_deg", cfg_data.get("theta", 0.0)))
    nmax_value = finite_number(cfg_data.get("nmax", 1), 1.0)
    nmax = int(nmax_value) if nmax_value >= 0 and nmax_value.is_integer() else 1
    moments_per_cfg = 36 * nmax
    log_line = get_latest_log_line(job_info) if job_info else ""
    config_types = get_config_types(campaign_key, task_id, cfg_data, log_line)
    total_moments = moments_per_cfg * len(config_types)

    # Check 1: Task result file already written in campaign results directory.
    if camp_meta and task_id is not None:
        res_dir = os.path.join(REPO_ROOT, camp_meta["results_dir"])
        try:
            done_pats = [
                os.path.join(res_dir, f"task_{task_id:03d}_*.json"),
                os.path.join(res_dir, f"task_{task_id}_*.json"),
                os.path.join(res_dir, "results_json", f"*th_{th:.1f}*.json"),
            ]
        except (TypeError, ValueError):
            done_pats = []
        for pat in done_pats:
            if glob.glob(pat):
                return total_moments, total_moments

    # Check 2: Campaign-specific checkpoints, counted independently per pass.
    done_moments = 0
    for cfg_type in config_types:
        cfg_done = 0
        full_patterns, moment_patterns = checkpoint_patterns(
            campaign_key, task_id, cfg_data, cfg_type
        )
        matching_full = [
            path
            for pat in full_patterns
            for path in glob.glob(pat)
            if "chk_moments_" not in os.path.basename(path)
        ]
        if matching_full:
            cfg_done = moments_per_cfg
        else:
            for pat in moment_patterns:
                for mf in glob.glob(pat):
                    try:
                        with open(mf, "r") as f_mom:
                            mdata = json.load(f_mom)
                        if not isinstance(mdata, dict):
                            continue
                        completed = mdata.get("completed_moments", {})
                        if isinstance(completed, (dict, list, tuple)):
                            cfg_done = max(cfg_done, len(completed))
                    except (OSError, ValueError, TypeError):
                        pass
        done_moments += min(cfg_done, moments_per_cfg)

    # Check 3: Live stdout log progress, with offsets for all configured passes.
    if log_line:
        m = re.search(r"Done moment (\d+)/(\d+)\s*\(Config:\s*(\w+)\)", log_line)
        if m:
            cur_m = min(int(m.group(1)), moments_per_cfg)
            cfg_in_log = m.group(3).lower()
            if cfg_in_log in config_types:
                log_done = config_types.index(cfg_in_log) * moments_per_cfg + cur_m
                done_moments = max(done_moments, log_done)
        elif "SIMULATION COMPLETE" in log_line or "COMPLETE" in log_line:
            done_moments = total_moments

    return min(done_moments, total_moments), total_moments


def get_campaign_completed_data(ckey, cmeta):
    """Returns list of completed task dicts for a campaign."""
    res_dir = os.path.join(REPO_ROOT, cmeta["results_dir"])
    if not os.path.exists(res_dir):
        return []

    # 1. Check CAMPAIGN_PROGRESS.json if present.
    if ckey == "clutch_campaign":
        prog_json = os.path.join(res_dir, "CAMPAIGN_PROGRESS.json")
        if os.path.exists(prog_json):
            try:
                with open(prog_json, "r") as fp:
                    pdata = json.load(fp)
                tasks = pdata.get("tasks", []) if isinstance(pdata, dict) else []
                completed = []
                task_items = tasks.values() if isinstance(tasks, dict) else tasks
                if not isinstance(tasks, (dict, list, tuple)):
                    task_items = []
                for tinfo in task_items:
                    if not isinstance(tinfo, dict):
                        continue
                    pct = finite_number(tinfo.get("completion_pct", tinfo.get("pct_moments", 0)))
                    st = tinfo.get("status", "")
                    if st in ["COMPLETE", "COMPLETED"] or pct >= 100:
                        f_val = finite_number(tinfo.get("net_force", tinfo.get("force_sub_fN", 0.0)))
                        p_val = finite_number(tinfo.get("pressure_Pa", 0.0))
                        reg = "REPULSIVE" if (p_val > 0 or f_val > 0) else "ATTRACTIVE"
                        completed.append({
                            "force_net_fN": f_val,
                            "pressure_Pa": p_val,
                            "regime": reg
                        })
                if completed:
                    return completed
            except (OSError, ValueError, TypeError):
                pass

    # 2. Check task_*.json or meep_*.json in res_dir and res_dir/results_json.
    patterns = [
        os.path.join(res_dir, "task_*.json"),
        os.path.join(res_dir, "meep_*.json"),
        os.path.join(res_dir, "results_json", "meep_*.json"),
        os.path.join(res_dir, "results_json", "task_*.json")
    ]
    files = set()
    for pat in patterns:
        files.update(glob.glob(pat))

    completed = []
    for path in sorted(files):
        base = os.path.basename(path).lower()
        if "summary" in base or "progress" in base or "manifest" in base:
            continue
        try:
            with open(path, "r") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                completed.append(data)
        except (OSError, ValueError, TypeError):
            pass
    return completed


def render_dashboard():
    """Renders the comprehensive cluster status dashboard."""
    user = os.environ.get("USER", "gogordon")
    jobs = query_slurm_jobs(user)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 115)
    print(f" {C_BOLD}{C_CYAN}3D FRACTAL CASIMIR EFFECT: BIGRED 200 PRODUCTION MONITOR{C_RESET}")
    print(f" Cluster: {C_BOLD}BigRed 200 (Cray EX / Slurm){C_RESET} | User: {C_BOLD}{user}{C_RESET} | Time: {now_str}")
    print("=" * 115)

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
                th = finite_number(cfg_data.get("theta_deg", cfg_data.get("theta", 0.0)))
                ztip = finite_number(cfg_data.get("z_tip_um", 0.0)) * 1e3
                davg = finite_number(cfg_data.get("d_average_um", 0.0)) * 1e3
                mat = cfg_data.get("material", "Gold")
                res = cfg_data.get("resolution", 60)
                n_pillars = cfg_data.get("num_pillars", 1 if N == 1 else 73)
                regime = str(cfg_data.get("expected_regime", "REPULSIVE"))

                reg_color = C_GREEN if "REPULSIVE" in regime else C_RED if "ATTRACTIVE" in regime else C_YELLOW
                print(f"      Physics:  {C_CYAN}N={N}{C_RESET} ({n_pillars} pillars) | {C_CYAN}theta={th:.1f} deg{C_RESET} | {C_CYAN}z_tip={ztip:.2f} nm{C_RESET} | <d>={davg:.1f} nm | Mat: {mat} | R={res} px/um | Exp: {reg_color}{regime}{C_RESET}")

                if state == "RUNNING":
                    done_m, tot_m = get_moment_progress(camp_key, j["task_id"], cfg_data, job_info=j)
                    pct = (done_m / float(tot_m)) * 100.0 if tot_m > 0 else 0.0
                    bar = make_bar(pct, width=24)
                    log_line = get_latest_log_line(j)
                    print(f"      Progress: [{C_GREEN}{bar}{C_RESET}] {C_BOLD}{pct:5.1f}%{C_RESET} ({done_m}/{tot_m} moments)")
                    print(f"      Latest:   {C_DIM}{log_line[:85]}{C_RESET}")
            else:
                log_line = get_latest_log_line(j)
                print(f"      Latest:   {C_DIM}{log_line[:85]}{C_RESET}")
            print("  " + "-" * 110)

    print(f"\n{C_BOLD}[2] CAMPAIGN EXECUTION STATUS & LEVITATION YIELD{C_RESET}")
    print("-" * 115)
    print(f"{'Campaign':<42}{'Tasks':<12}{'Completed':<14}{'Repulsive':<14}{'Status':<16}")
    print("-" * 115)

    for ckey, cmeta in CAMPAIGNS.items():
        completed_items = get_campaign_completed_data(ckey, cmeta)
        num_done = len(completed_items)
        total = cmeta["total_tasks"]
        if total is None:
            # Derive new campaign sizes from configs rather than inventing totals.
            config_files = glob.glob(
                os.path.join(REPO_ROOT, cmeta["config_dir"], "config_*.json")
            )
            total = len(config_files) if config_files else None

        repulsive_count = 0
        for rdata in completed_items:
            f_net = finite_number(rdata.get(
                "force_net_fN_per_cell",
                rdata.get("force_net_fN", rdata.get("force_sub_fN", rdata.get("force_net_meep", 0.0)))
            ))
            regime = rdata.get("regime", "")
            if f_net > 0 or "REPULSIVE" in str(regime).upper():
                repulsive_count += 1

        active_in_queue = sum(
            1 for j in jobs if identify_campaign(j["name"])[0] == ckey
        )

        if active_in_queue > 0:
            status_str = f"{C_GREEN}RUNNING ({active_in_queue} in queue){C_RESET}"
        elif total is not None and total > 0 and num_done == total:
            status_str = f"{C_BOLD}{C_GREEN}100% COMPLETE{C_RESET}"
        elif num_done > 0:
            total_label = total if total is not None else "?"
            status_str = f"{C_YELLOW}PARTIAL ({num_done}/{total_label}){C_RESET}"
        else:
            status_str = f"{C_DIM}READY TO RUN{C_RESET}"

        pct = (num_done / float(total)) * 100.0 if total is not None and total > 0 else 0.0
        bar = make_bar(pct, width=12)
        total_label = total if total is not None else "?"
        print(f"{cmeta['title']:<42}{total_label:<12}{num_done:<6} [{bar}] {repulsive_count:<14}{status_str:<16}")

    print("=" * 115)
    print(f" {C_DIM}Tip: Run with '-w' for continuous 20s live-refresh: python execution/monitor_all_casimir_runs.py -w{C_RESET}")
    print(f" {C_DIM}     To view full log of a task: python execution/monitor_all_casimir_runs.py --tail <task_id>{C_RESET}")
    print("=" * 115 + "\n")


def tail_task_log(task_id):
    """Displays the last 40 lines of log file for a specific task."""
    patterns = [
        os.path.join(REPO_ROOT, ".tmp", f"*_{task_id:03d}*.out"),
        os.path.join(REPO_ROOT, ".tmp", f"*_{task_id}*.out"),
        os.path.join(REPO_ROOT, "logs", f"*_{task_id}*.out")
    ]
    matching = []
    for pattern in patterns:
        matching.extend(glob.glob(pattern))
    if not matching:
        print(f"No log files found matching Task {task_id}.")
        return
    log_file = matching[0]
    print(f"\nDisplaying last 40 lines of {log_file}:\n" + "-" * 80)
    try:
        with open(log_file, "r", errors="ignore") as f:
            lines = f.readlines()
            for line in lines[-40:]:
                print(line, end="")
    except OSError as e:
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
        if args.interval <= 0:
            parser.error("--interval must be a positive number of seconds")
        try:
            while True:
                os.system("cls" if os.name == "nt" else "clear")
                render_dashboard()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nExiting live monitor.")
    else:
        render_dashboard()


if __name__ == "__main__":
    main()
