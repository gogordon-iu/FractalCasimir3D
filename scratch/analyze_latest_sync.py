import os
import glob
import json

def main():
    summary_file = 'results_sweet_spot_sweep_20260822_202515/sweet_spot_sweep_summary.json'
    if not os.path.exists(summary_file):
        print(f"Error: {summary_file} not found")
        return
        
    data = json.load(open(summary_file))
    print(f"=== SWEET SPOT SUMMARY ANALYSIS ({summary_file}) ===")
    print(f"Total Physical Parameter Records: {len(data)}")
    
    rep = [r for r in data if r.get('pressure_Pa', 0) > 0]
    print(f"Repulsive Levitation Points (P > 0): {len(rep)} / {len(data)} ({len(rep)/len(data)*100:.1f}%)")
    
    alphas = sorted(list(set(r['alpha_deg'] for r in data)))
    thetas = sorted(list(set(r['theta_deg'] for r in data)))
    ds = sorted(list(set(r['d_um'] for r in data)))
    print(f"Wall Slopes (alpha): {alphas}")
    print(f"Twist Angles (theta): {thetas}")
    print(f"Separations (d in um): {ds}")
    
    print("\n--- SAMPLE REPULSIVE LEVITATION POINTS ---")
    rep_sorted = sorted(rep, key=lambda x: -x['pressure_Pa'])
    for r in rep_sorted[:15]:
        print(f"  alpha={r['alpha_deg']:4.1f} deg | theta={r['theta_deg']:4.1f} deg | d={r['d_um']:6.4f} um ({r['d_um']*1000:5.1f} nm) => P = {r['pressure_Pa']:+10.6f} Pa")
        
    print("\n--- LOGS INSPECTION FOR JOB 8007998 ---")
    out_files = sorted(glob.glob('.tmp/sweet_spot_8007998_*.out'))
    err_files = sorted(glob.glob('.tmp/sweet_spot_8007998_*.err'))
    print(f"Found {len(out_files)} stdout files and {len(err_files)} stderr files for Job 8007998.")
    
    # Check completed vs running vs timed out tasks
    timed_out = []
    completed = []
    running = []
    
    for err_f in err_files:
        content = open(err_f, 'r', encoding='utf-8', errors='ignore').read()
        task_id = err_f.split('_')[-1].replace('.err', '')
        if "CANCELLED" in content and "TIME LIMIT" in content:
            timed_out.append(task_id)
        elif "Simulation complete" in content or "Subtracted force" in content:
            completed.append(task_id)
            
    print(f"Timed out tasks in Job 8007998: {len(timed_out)}")
    print(f"Explicitly completed tasks: {len(completed)}")
    
    # Look at recent logs
    print("\n--- RECENT OUT LOG SAMPLES ---")
    for out_f in out_files[-5:]:
        lines = open(out_f, 'r', encoding='utf-8', errors='ignore').readlines()
        print(f"File: {out_f}")
        for l in lines[:4]:
            print("  ", l.strip())
        if lines:
            print("   Last line:", lines[-1].strip())

if __name__ == '__main__':
    main()
