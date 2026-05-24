import numpy as np
import scipy.integrate as integrate
import sys
import json
import os

# Constants in Meep units (hbar = c = 1)
L = 0.3  # plate size in microns
T_77 = 77
T_300 = 300

def get_epsilon_gold(xi):
    # Drude model parameters for Gold in Meep units
    fp = 7.25
    gamma = 0.028
    return 1.0 + (fp**2) / (xi**2 + gamma * xi + 1e-15)

def get_epsilon_silicon(xi):
    # Lorentz model parameters for Silicon in Meep units
    eps_inf = 1.035
    f0 = 2.18
    delta_eps = 10.835
    return eps_inf + (delta_eps * f0**2) / (f0**2 + xi**2)

def lifshitz_integrand(k_parallel, xi, d, material):
    if material == "PEC":
        return 0.0  # handled analytically
    
    if material == "Gold":
        eps = get_epsilon_gold(xi)
    elif material == "Silicon":
        eps = get_epsilon_silicon(xi)
    else:
        eps = 1.0
        
    kz = np.sqrt(xi**2 + k_parallel**2)
    kzm = np.sqrt(eps * xi**2 + k_parallel**2)
    
    # Fresnel reflection coefficients
    rp = (eps * kz - kzm) / (eps * kz + kzm + 1e-15)
    rs = (kz - kzm) / (kz + kzm + 1e-15)
    
    exp_factor = np.exp(-2.0 * kz * d)
    
    term_p = (rp**2 * exp_factor) / (1.0 - rp**2 * exp_factor + 1e-15)
    term_s = (rs**2 * exp_factor) / (1.0 - rs**2 * exp_factor + 1e-15)
    
    return k_parallel * kz * (term_p + term_s)

def get_force_density_lifshitz(d, material, T=0):
    """
    Computes parallel plate force density in Meep units.
    If T > 0, performs Matsubara summation. If T == 0, performs imaginary-frequency integration.
    """
    if material == "PEC":
        # Analytical PEC force density: -pi^2 / (240 * d^4)
        return - (np.pi**2) / (240.0 * d**4)
        
    if T == 0:
        # T = 0 K integration
        def inner_int(xi, d, material):
            val, _ = integrate.quad(lambda kp: lifshitz_integrand(kp, xi, d, material), 0, 10.0 / d, limit=50)
            return val
            
        val, _ = integrate.quad(lambda xi: inner_int(xi, d, material), 0, 10.0 / d, limit=50)
        return - (1.0 / (2.0 * np.pi**2)) * val
    else:
        # Finite-temperature Matsubara sum
        # xi_n = 2 * pi * n * k_B * T / hbar
        # In Meep units: k_B = 8.6173e-5 eV/K. hbar * c = 0.1973 eV*um.
        # With c = 1, hbar = 0.1973 eV*um.
        # So k_B * T / hbar = (8.6173e-5 * T) / 0.1973 = 0.00043676 * T
        # Spacing Delta_xi = 2 * pi * 0.00043676 * T = 0.0027442 * T
        delta_xi = 0.0027442 * T
        n_max = int(10.0 / (delta_xi * d)) + 1
        n_max = max(n_max, 20)
        n_max = min(n_max, 500)
        
        sum_val = 0.0
        for n in range(n_max):
            xi = n * delta_xi
            weight = 0.5 if n == 0 else 1.0
            
            def inner_kp(kp):
                return lifshitz_integrand(kp, xi, d, material)
                
            val, _ = integrate.quad(inner_kp, 0, 10.0 / d, limit=50)
            sum_val += weight * val
            
        # Prefactor: - (k_B * T) / pi * sum_val
        # k_B * T in Meep units = 0.00043676 * T
        return - (0.00043676 * T / np.pi) * sum_val

def get_effective_area(N, L=L):
    # Sierpinski carpet area: (8/9)**(N-1) * L^2
    return ((8.0 / 9.0)**(N - 1)) * (L**2)

def main():
    # Sweep configurations
    separations = np.logspace(np.log10(0.02), np.log10(1.0), 30)  # 20 nm to 1000 nm in microns
    generations = [1, 2, 3, 4]
    materials = ["PEC", "Gold", "Silicon"]
    temperatures = [0, T_77, T_300]
    
    results = {}
    
    print("Running PFA analytical model baseline calculations...")
    for mat in materials:
        results[mat] = {}
        for T in temperatures:
            t_label = f"T_{T}" if T > 0 else "T_0"
            results[mat][t_label] = {}
            for N in generations:
                results[mat][t_label][f"N_{N}"] = []
                area = get_effective_area(N)
                for d in separations:
                    f_dens = get_force_density_lifshitz(d, mat, T)
                    force = f_dens * area
                    results[mat][t_label][f"N_{N}"].append({
                        "d_nm": float(d * 1000.0),
                        "force_val": float(force)
                    })
                    
    # Save results to .tmp directory
    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/pfa_results.json", "w") as f:
        json.dump(results, f, indent=4)
    print("PFA analytical model baseline calculations complete. Saved to .tmp/pfa_results.json")

if __name__ == "__main__":
    main()
