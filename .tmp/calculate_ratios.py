import os
import json
import numpy as np

# Theoretical PFA model (infinite plate)
# F_PFA = f_dens * area
# area = 0.09 for N=1, L=0.3
L = 0.3
area = L**2

def get_pfa_force(d, material):
    if material == "PEC":
        f_dens = - (np.pi**2) / (240.0 * d**4)
    elif material == "Gold":
        f_dens = - (np.pi**2) / (240.0 * d**4) * 0.72
    elif material == "Silicon":
        f_dens = - (np.pi**2) / (240.0 * d**4) * 0.35
    else:
        f_dens = 0.0
    return f_dens * area

def main():
    files = sorted([f for f in os.listdir(".") if f.startswith("meep_d_")])
    ds = sorted(list(set([float(f.split("_")[2]) for f in files])))
    materials = ["PEC", "Gold", "Silicon"]
    
    for mat in materials:
        print(f"\n--- Material: {mat} ---")
        print(f"{'d (um)':<10}{'F_sim':<15}{'F_PFA':<15}{'Ratio (F_sim / F_PFA)':<20}")
        for d in ds:
            fn = f"meep_d_{d:.4f}_N_1_{mat}_res_10.json"
            if os.path.exists(fn):
                with open(fn, "r") as f:
                    data = json.load(f)
                    f_sim = data["force_subtracted"]
                    f_pfa = get_pfa_force(d, mat)
                    ratio = f_sim / f_pfa if f_pfa != 0 else 0
                    print(f"{d:<10.4f}{f_sim:<15.8f}{f_pfa:<15.8f}{ratio:<20.6f}")

if __name__ == "__main__":
    main()
