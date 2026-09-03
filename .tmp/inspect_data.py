import json
import numpy as np

with open(".tmp/compiled_casimir_dataset.json") as f:
    data = json.load(f)

# Extract Gold, T=0 entries
gold_pts = [x for x in data["data"] if x["material"] == "Gold" and x["temperature_K"] == 0]

pts_0 = sorted([x for x in gold_pts if x["generation_N"] == 0], key=lambda x: x["separation_um"])
pts_1 = sorted([x for x in gold_pts if x["generation_N"] == 1], key=lambda x: x["separation_um"])

import os
meep_data = {}
meep_res = {}
for filename in os.listdir(".tmp"):
    if filename.startswith("meep_d_") and filename.endswith(".json"):
        if "check" in filename or "calculate" in filename or "inspect" in filename:
            continue
        with open(os.path.join(".tmp", filename), "r") as f:
            d = json.load(f)
            key = (d["d_um"], d["N"], d["material"])
            res = d.get("resolution", 10)
            if key not in meep_data or res >= meep_res[key]:
                meep_data[key] = d["force_subtracted"]
                meep_res[key] = res

sim_distances = sorted(list(set([k[0] for k in meep_data.keys() if k[2] == "Gold"])))
sim_forces = {}
for N in [1, 2, 3, 4]:
    sim_forces[N] = []
    for d in sim_distances:
        val = next(force for k, force in meep_data.items() if abs(k[0] - d) < 1e-4 and k[1] == N and k[2] == "Gold")
        sim_forces[N].append(val)

# Define the exact interpolators used in postprocess_and_plot.py
log_sim_d = np.log(sim_distances)
log_abs_F1 = np.log(np.abs(sim_forces[1]))
def get_base(d_val):
    log_d = np.log(d_val)
    return -np.exp(np.interp(log_d, log_sim_d, log_abs_F1))

ratios = {}
for N in [1, 2, 3, 4]:
    r_sim = np.array(sim_forces[N]) / np.array(sim_forces[1])
    def get_ratio(d_val, r_sim=r_sim):
        log_d = np.log(d_val)
        return np.interp(log_d, log_sim_d, r_sim)
    ratios[N] = get_ratio

pfa_d_pts = [p["separation_um"] for p in pts_0]
pfa_f_pts = [p["force_pfa"] for p in pts_0]

print("=== Direct Line Force vs Circle Force Difference ===")
for N in [1, 2, 3, 4]:
    diffs = []
    for i, d_val in enumerate(sim_distances):
        # Compute exact force from the curves' mathematical definition
        line_force = get_base(d_val) * ratios[N](d_val)
        sim_force = sim_forces[N][i]
        diffs.append(abs(line_force - sim_force))
    print(f"N={N} max force difference: {max(diffs):.2e}")

print("\n=== Direct Line Dev vs Circle Dev Difference (Panel A) ===")
for N in [1, 2, 3, 4]:
    diffs = []
    for i, d_val in enumerate(sim_distances):
        line_force = get_base(d_val) * ratios[N](d_val)
        pfa_val = np.interp(d_val, pfa_d_pts, pfa_f_pts)
        line_dev = (line_force - pfa_val) / pfa_val
        
        sim_force = sim_forces[N][i]
        sim_dev = (sim_force - pfa_val) / pfa_val
        diffs.append(abs(line_dev - sim_dev))
    print(f"N={N} max deviation difference: {max(diffs):.2e}")

print("\n=== Direct Line Dev vs Circle Dev Difference (Panel B) ===")
for N in [1, 2, 3, 4]:
    diffs = []
    for i, d_val in enumerate(sim_distances):
        line_force = get_base(d_val) * ratios[N](d_val)
        f1_val = get_base(d_val) # F_1
        line_dev = (line_force - f1_val) / f1_val
        
        sim_force = sim_forces[N][i]
        sim_force_1 = sim_forces[1][i]
        sim_dev = (sim_force - sim_force_1) / sim_force_1
        diffs.append(abs(line_dev - sim_dev))
    print(f"N={N} max deviation difference: {max(diffs):.2e}")
