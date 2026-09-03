import os
import json
import glob
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# Science/Nature style plot rules
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
plt.rcParams['font.size'] = 8
plt.rcParams['axes.labelsize'] = 9
plt.rcParams['axes.titlesize'] = 10
plt.rcParams['legend.fontsize'] = 7
plt.rcParams['xtick.labelsize'] = 8
plt.rcParams['ytick.labelsize'] = 8
plt.rcParams['pdf.fonttype'] = 42

def fit_linear(x, m, c):
    return m * x + c

def fit_inv_L(x, a, b):
    return a / x + b

def generate_report_plot():
    L_vals = np.array([0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2])
    std_p90 = []
    tuned_p90 = []
    
    for L in L_vals:
        dirs = glob.glob(f"results_twist_L_{L:.2f}_*")
        if not dirs:
            continue
        latest_dir = max(dirs, key=os.path.getmtime)
        filepath = os.path.join(latest_dir, "twist_sweep_results.json")
        with open(filepath, "r") as f:
            data = json.load(f)
            
        for entry in data['Phosphorene']:
            if entry['theta_deg'] == 90.0:
                std_p90.append(entry['pressure'])
        for entry in data['Phosphorene_tuned']:
            if entry['theta_deg'] == 90.0:
                tuned_p90.append(entry['pressure'])
                
    std_p90 = np.array(std_p90)
    tuned_p90 = np.array(tuned_p90)
    
    fig, ax = plt.subplots(figsize=(4.5, 3.5), dpi=300)
    
    # Plot raw data points
    ax.scatter(L_vals, std_p90, color='#d9534f', marker='o', s=30, label='Standard ($\epsilon_{bg} = 2.4$)', zorder=5)
    ax.scatter(L_vals, tuned_p90, color='#0275d8', marker='s', s=30, label='Tuned ($\epsilon_{bg} = 2.1$)', zorder=5)
    
    # 1. Linear fit to L <= 0.6 points only (Original fit)
    L_sub = L_vals[L_vals <= 0.6]
    std_sub = std_p90[L_vals <= 0.6]
    tuned_sub = tuned_p90[L_vals <= 0.6]
    
    popt_std_lin, _ = curve_fit(fit_linear, L_sub, std_sub)
    popt_tuned_lin, _ = curve_fit(fit_linear, L_sub, tuned_sub)
    
    x_fit_lin = np.linspace(0.25, 1.3, 100)
    ax.plot(x_fit_lin, fit_linear(x_fit_lin, *popt_std_lin), color='#d9534f', linestyle='--', linewidth=1.0, alpha=0.7, label='Linear Fit ($L \\leq 0.6$)')
    ax.plot(x_fit_lin, fit_linear(x_fit_lin, *popt_tuned_lin), color='#0275d8', linestyle='--', linewidth=1.0, alpha=0.7)
    
    # 2. Asymptotic 1/L fit to all points
    popt_std_inv, _ = curve_fit(fit_inv_L, L_vals, std_p90)
    popt_tuned_inv, _ = curve_fit(fit_inv_L, L_vals, tuned_p90)
    
    x_fit_inv = np.linspace(0.28, 1.3, 100)
    ax.plot(x_fit_inv, fit_inv_L(x_fit_inv, *popt_std_inv), color='#d9534f', linestyle='-', linewidth=1.2, label='Asymptotic Fit ($A/L + B$)')
    ax.plot(x_fit_inv, fit_inv_L(x_fit_inv, *popt_tuned_inv), color='#0275d8', linestyle='-', linewidth=1.2)
    
    # Add labels, grid, legend
    ax.axhline(0, color='black', linestyle=':', linewidth=0.8, alpha=0.8)
    ax.set_xlabel('Plate Size $L$ ($\mu$m)')
    ax.set_ylabel('Casimir Pressure $P$ (N/m$^2$)')
    ax.set_xlim(0.25, 1.3)
    ax.set_ylim(-1.8, 0.2)
    ax.grid(True, which='both', linestyle=':', linewidth=0.5, alpha=0.5)
    
    # Title and Legend
    ax.set_title('Casimir Pressure Scaling at $\theta = 90^\circ$', fontsize=10, fontweight='bold', pad=10)
    ax.legend(loc='lower right', frameon=True, facecolor='#f9f9f9', edgecolor='none')
    
    # Save output to artifacts directory
    output_dir = "C:/Users/gorengor/.gemini/antigravity/brain/a5ed6d7a-5753-4930-8bee-9f7a3482e4d1"
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(os.path.join(output_dir, "figure_scaling_trend_updated.png"), dpi=300, bbox_inches='tight')
    plt.close()
    
    print("Successfully generated updated scaling trend figure.")
    
    # Print the fit parameters
    print(f"Standard 1/L fit: P(L) = {popt_std_inv[0]:.4f}/L + {popt_std_inv[1]:.4f}")
    print(f"Tuned 1/L fit: P(L) = {popt_tuned_inv[0]:.4f}/L + {popt_tuned_inv[1]:.4f}")

if __name__ == "__main__":
    generate_report_plot()
