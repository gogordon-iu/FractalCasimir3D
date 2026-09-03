import os
import json

def main():
    files = sorted([f for f in os.listdir(".") if f.startswith("meep_d_") and "Gold" in f])
    # Extract unique distances
    ds = sorted(list(set([f.split("_")[2] for f in files])))
    
    print(f"{'d (um)':<10}{'N=1':<15}{'N=2':<15}{'N=3':<15}{'N=4':<15}")
    for d in ds:
        row = [d]
        for N in [1, 2, 3, 4]:
            fn = f"meep_d_{d}_N_{N}_Gold_res_10.json"
            if os.path.exists(fn):
                with open(fn, "r") as f:
                    data = json.load(f)
                    row.append(f"{data['force_subtracted']:.8f}")
            else:
                row.append("N/A")
        print(f"{row[0]:<10}{row[1]:<15}{row[2]:<15}{row[3]:<15}{row[4]:<15}")

if __name__ == "__main__":
    main()
