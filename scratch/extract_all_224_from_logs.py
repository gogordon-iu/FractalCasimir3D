import os
import glob
import re
import json

def main():
    print("==================================================")
    print("EXTRACTING ALL 224 TASKS FROM SLURM LOGS & OUTPUTS")
    print("==================================================")

    # 1. Load all 224 config definitions
    config_files = sorted(glob.glob("sweep_configs_sweet_spot/config_*.json"))
    print(f"Loaded {len(config_files)} configuration files.")

    task_results = {}

    for cf in config_files:
        task_num = int(os.path.basename(cf).replace("config_", "").replace(".json", ""))
        with open(cf, "r") as fp:
            cdata = json.load(fp)

        task_results[task_num] = {
            "task_id": task_num,
            "alpha_deg": float(cdata["alpha"]),
            "theta_deg": float(cdata["theta"]),
            "d_um": float(cdata["d"]),
            "L": float(cdata["L"]),
            "res": int(cdata["resolution"]),
            "status": "UNKNOWN",
            "force_both": None,
            "force_self": None,
            "force_sub": None,
            "pressure_Pa": None
        }

    # 2. Check all .out files for 8039918
    out_files = sorted(glob.glob(".tmp/sweet_spot_8039918_*.out"))
    print(f"Found {len(out_files)} SLURM stdout logs for job 8039918.")

    for of in out_files:
        try:
            # Extract task ID from filename: sweet_spot_8039918_<task_id>.out
            m = re.search(r"sweet_spot_8039918_(\d+)\.out", of)
            if not m:
                continue
            tid = int(m.group(1))
            if tid not in task_results:
                continue

            with open(of, "r", errors="ignore") as f:
                content = f.read()

            if "complete" in content.lower() or "simulation task complete" in content.lower():
                task_results[tid]["status"] = "COMPLETED"
            elif "executing 3d fdtd" in content.lower():
                task_results[tid]["status"] = "STARTED"
                
            # Look for printed force values
            m_both = re.search(r"force_both[:=]\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)", content)
            m_self = re.search(r"force_self[:=]\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)", content)
            if m_both:
                task_results[tid]["force_both"] = float(m_both.group(1))
            if m_self:
                task_results[tid]["force_self"] = float(m_self.group(1))
        except Exception:
            pass

    # 3. Check all .err files for completion or timeout
    err_files = sorted(glob.glob(".tmp/sweet_spot_8039918_*.err"))
    for ef in err_files:
        try:
            m = re.search(r"sweet_spot_8039918_(\d+)\.err", ef)
            if not m:
                continue
            tid = int(m.group(1))
            if tid not in task_results:
                continue

            with open(ef, "r", errors="ignore") as f:
                content = f.read()

            if "CANCELLED" in content or "TIMEOUT" in content or "due to time limit" in content:
                task_results[tid]["status"] = "TIMEOUT"
            elif "error" in content.lower() and "runtimeerror" in content.lower():
                task_results[tid]["status"] = "ERROR"
        except Exception:
            pass

    # 4. Check JSON files in .tmp
    json_files = glob.glob(".tmp/*.json") + glob.glob(".tmp/**/*.json", recursive=True)
    for jf in json_files:
        try:
            with open(jf, "r") as f:
                jd = json.load(f)
                if isinstance(jd, dict) and "force_both" in jd and "force_self" in jd:
                    d_val = float(jd.get("d_um", jd.get("d", -1)))
                    th_val = float(jd.get("theta_deg", jd.get("theta", -1)))
                    al_val = float(jd.get("corrugation_angle", jd.get("alpha_deg", -1)))
                    
                    for tid, tr in task_results.items():
                        if (abs(tr["d_um"] - d_val) < 1e-4 and 
                            abs(tr["theta_deg"] - th_val) < 1e-2 and 
                            abs(tr["alpha_deg"] - al_val) < 1e-2):
                            tr["status"] = "COMPLETED"
                            tr["force_both"] = jd["force_both"]
                            tr["force_self"] = jd["force_self"]
                            f_sub = jd["force_both"] - jd["force_self"]
                            tr["force_sub"] = f_sub
                            L_m = tr["L"] * 1e-6
                            area_m2 = L_m ** 2
                            hbar = 1.054571817e-34
                            c_const = 299792458.0
                            tr["pressure_Pa"] = (f_sub * hbar * c_const / L_m) / area_m2
        except Exception:
            pass

    # Status counts
    completed = [t for t in task_results.values() if t["status"] == "COMPLETED"]
    timeout = [t for t in task_results.values() if t["status"] == "TIMEOUT"]
    started = [t for t in task_results.values() if t["status"] == "STARTED"]
    unknown = [t for t in task_results.values() if t["status"] == "UNKNOWN"]
    errors = [t for t in task_results.values() if t["status"] == "ERROR"]

    print("\n" + "="*50)
    print("AUDIT SUMMARY ACROSS ALL 224 ARRAY TASKS:")
    print("="*50)
    print(f"COMPLETED (100% full outputs): {len(completed)} / 224 ({len(completed)/224*100:.1f}%)")
    print(f"TIMED OUT at 24:00:00:          {len(timeout)} / 224 ({len(timeout)/224*100:.1f}%)")
    print(f"STARTED / PARTIAL:             {len(started)} / 224 ({len(started)/224*100:.1f}%)")
    print(f"ERRORS (Crashes):              {len(errors)} / 224 ({len(errors)/224*100:.1f}%)")
    print(f"UNKNOWN:                       {len(unknown)} / 224 ({len(unknown)/224*100:.1f}%)")

    # Sample of completed tasks
    print("\nSample Completed Tasks:")
    for c in completed[:10]:
        print(f"  Task {c['task_id']:3d}: Alpha={c['alpha_deg']:4.1f}°, Theta={c['theta_deg']:4.1f}°, d={c['d_um']*1000:5.1f} nm => P = {c.get('pressure_Pa', 0):+.6f} Pa")

if __name__ == '__main__':
    main()
