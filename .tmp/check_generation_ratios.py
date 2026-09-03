import os
import json

def main():
    materials = ["PEC", "Gold", "Silicon"]
    separations = ["0.1138", "0.1758", "0.2714"]
    
    for mat in materials:
        print(f"\n--- Material: {mat} ---")
        for d in separations:
            forces = {}
            for N in [1, 2, 3, 4]:
                fn = f"meep_d_{d}_N_{N}_{mat}_res_10.json"
                if os.path.exists(fn):
                    with open(fn, "r") as f:
                        data = json.load(f)
                        forces[N] = data["force_subtracted"]
            
            ratios = {N: forces[N] / forces[1] for N in [2, 3, 4] if N in forces and 1 in forces}
            print(f"d = {d:<8} F(1) = {forces[1]:.6f} | Ratios F(N)/F(1): N=2: {ratios.get(2,0):.5f}, N=3: {ratios.get(3,0):.5f}, N=4: {ratios.get(4,0):.5f}")

if __name__ == "__main__":
    main()
