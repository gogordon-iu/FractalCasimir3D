import os
import glob
import json
import subprocess
import datetime

def main():
    print("="*65)
    print("       3D CASIMIR HPC CLUSTER MONITOR & AUDIT DASHBOARD")
    print("="*65)
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 65)

    # 1. Check Active Slurm Jobs
    print("\n[1] ACTIVE SLURM QUEUE (squeue):")
    try:
        res = subprocess.run(['squeue', '-u', os.environ.get('USER', 'gogordon'), '-o', '%.18i %.9P %.25j %.8u %.2t %.10M %.6D %R'], capture_output=True, text=True)
        lines = res.stdout.strip().splitlines()
        if len(lines) <= 1:
            print("  No active running or pending jobs in queue.")
        else:
            for l in lines:
                print(f"  {l}")
    except Exception as e:
        print(f"  Could not query squeue: {e}")

    # 2. Check Recent Slurm History (sacct)
    print("\n[2] RECENT JOB COMPLETION HISTORY (sacct - last 7 days):")
    try:
        res = subprocess.run(['sacct', '-u', os.environ.get('USER', 'gogordon'), '--starttime', 'now-7days', '--format=JobID,JobName%22,State%12,Elapsed,ExitCode', '-X'], capture_output=True, text=True)
        lines = res.stdout.strip().splitlines()
        for l in lines[-15:]:
            print(f"  {l}")
    except Exception as e:
        print(f"  Could not query sacct: {e}")

    # 3. Audit Full 224 Task Sweep Progress
    print("\n[3] 224-TASK PARAMETER SWEEP PROGRESS:")
    config_files = sorted(glob.glob("sweep_configs_sweet_spot/config_*.json"))
    configs_map = {}
    for cf in config_files:
        try:
            task_num = int(os.path.basename(cf).replace("config_", "").replace(".json", ""))
            with open(cf, "r") as fp:
                cdata = json.load(fp)
                key = (round(float(cdata["d"]), 4), round(float(cdata["theta"]), 1), round(float(cdata["alpha"]), 1))
                configs_map[key] = task_num
        except Exception:
            pass

    completed_task_ids = set()
    repulsive_count = 0
    total_data_points = 0
    files = glob.glob(".tmp/**/*.json", recursive=True) + glob.glob(".tmp/*.json")
    for sf in glob.glob("results_sweet_spot_sweep_*/sweet_spot_sweep_summary.json"):
        try:
            with open(sf, "r") as fp:
                recs = json.load(fp)
                for r in recs:
                    if isinstance(r, dict) and "pressure_Pa" in r:
                        total_data_points += 1
                        if r.get("pressure_Pa", 0) > 0:
                            repulsive_count += 1
                        key = (round(float(r["d_um"]), 4), round(float(r["theta_deg"]), 1), round(float(r["alpha_deg"]), 1))
                        if key in configs_map:
                            completed_task_ids.add(configs_map[key])
        except Exception:
            pass
            
    for f in files:
        try:
            with open(f, "r") as fp:
                d = json.load(fp)
                if isinstance(d, dict) and "force_both" in d and "force_self" in d:
                    if "moment_start" not in d and "moment_end" not in d:
                        total_data_points += 1
                        if d.get("force_both", 0) > d.get("force_self", 0):
                            repulsive_count += 1
                        if "task_idx" in d and d["task_idx"] > 0:
                            completed_task_ids.add(d["task_idx"])
                        elif "d_um" in d and "theta_deg" in d and ("corrugation_angle" in d or "alpha_deg" in d):
                            al_v = d.get("corrugation_angle", d.get("alpha_deg", 0.0))
                            key = (round(float(d["d_um"]), 4), round(float(d["theta_deg"]), 1), round(float(al_v), 1))
                            if key in configs_map:
                                completed_task_ids.add(configs_map[key])
        except Exception:
            pass

    all_task_ids = set(range(1, 225))
    missing_task_ids = sorted(list(all_task_ids - completed_task_ids))

    pct_done = len(completed_task_ids) / 224 * 100
    bar_len = 30
    filled = int(bar_len * len(completed_task_ids) // 224)
    bar = "█" * filled + "░" * (bar_len - filled)

    print(f"  Progress: [{bar}] {pct_done:.1f}% ({len(completed_task_ids)} / 224 Tasks Completed)")
    print(f"  Missing / Remaining Tasks: {len(missing_task_ids)}")
    print(f"  Repulsive Levitation Yield: {repulsive_count} / {total_data_points} points ({repulsive_count/max(total_data_points,1)*100:.1f}%)")

    # 4. Latest Log Tails
    print("\n[4] LATEST ACTIVE / MODIFIED LOGS:")
    recent_outs = sorted(glob.glob(".tmp/sweet_spot_*.out"), key=os.path.getmtime, reverse=True)
    if recent_outs:
        for ro in recent_outs[:3]:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(ro)).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  Log: {ro} (Last modified: {mtime})")
            try:
                with open(ro, "r") as f:
                    last_lines = f.read().strip().splitlines()[-3:]
                    for ll in last_lines:
                        print(f"    | {ll}")
            except Exception:
                pass
    else:
        print("  No .out log files found in .tmp/")

    print("\n" + "="*65)

if __name__ == '__main__':
    main()
