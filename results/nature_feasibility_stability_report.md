# Nature feasibility and stability: real 3D BEM

**Status:** `complete`
**Mode:** `full`
**Completed BEM evaluations:** 32

Positive vertical force denotes repulsion. Full-study forces and energies use Gold at 300 K unless a row explicitly states otherwise.

## Numerical settings

```json
{
  "device": "cpu",
  "formulation": "vector_dyadic",
  "max_steps": 0,
  "micro_resolution_override": false,
  "n_phi_bridge": 2,
  "n_phi_tooth": 2,
  "n_r": 1,
  "n_xi": 12,
  "n_z": 2,
  "requested_resolution": {
    "n_phi_bridge": 2,
    "n_phi_tooth": 2,
    "n_r": 1,
    "n_xi": 12,
    "n_z": 2
  },
  "resume_report_path": "C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\results\\nature_feasibility_stability_report.json"
}
```

## Cantor_N2_HybridRZ

Study status: `complete`

### 1. Material dispersion and temperature

| Regime | Angle (deg) | Fz (pN) | Wrep(30 nm)/kBT300 | Expected sign |
|---|---:|---:|---:|:---:|
| PEC_T0K | 3 | 1.70671 | 12.3617 | yes |
| PEC_T0K | 48 | -2.5215 | not available | yes |
| Gold_T0K | 3 | 0.200233 | 1.45028 | yes |
| Gold_T0K | 48 | -0.349367 | not available | yes |
| Gold_T300K | 3 | 0.204222 | 1.47917 | yes |
| Gold_T300K | 48 | -0.363874 | not available | yes |

### 2. Electrostatic residual-voltage bound

| Rotor shift (um) | Mutual capacitance (F) | Relative solve residual |
|---:|---:|---:|
| -0.002 | 1.681883842e-16 | 7.45244e-16 |
| 0 | 1.686215229e-16 | 6.02189e-16 |
| 0.002 | 1.690245213e-16 | 7.36918e-16 |

- dC/dz: 2.090342661e-10 F/m
- Absolute gradient coefficient: 0.0002090342661 pN/mV²
- Critical voltage: 44.20356257 mV (`finite`)
- Repulsion survives 50 mV: no

| Voltage (mV) | Net force (pN) |
|---:|---:|
| 0 | 0.204222 |
| 5 | 0.201609 |
| 10 | 0.19377 |
| 15 | 0.180705 |
| 20 | 0.162415 |
| 25 | 0.138899 |
| 30 | 0.110156 |
| 40 | 0.0369944 |
| 50 | -0.0570711 |

### 3. Lateral stiffness and four-spoke suspension

| Radial shift (um) | Energy (hbar*c/um) | Energy (pN um) |
|---:|---:|---:|
| 0 | -2.008099067 | -0.06348658965 |
| 0.004 | -1.999052345 | -0.0632005751 |
| 0.008 | -1.992293421 | -0.06298688991 |
- `k_r_Casimir_pN_per_um`: -4.520584322 pN/um
- `k_r_Casimir_pN_per_nm`: -0.004520584322 pN/nm
- `k_r_Casimir_N_per_m`: -4.520584322e-06 N/m
- `origin_even_energy_estimate_pN_per_um`: 35.75181757 pN/um
- `k_z_mech_pN_per_nm`: 0.1211392 pN/nm
- `k_r_mech_pN_per_nm`: 1.030524444 pN/nm
- `lateral_stability_safety_factor`: 227.9626639
- `combined_radial_stiffness_pN_per_nm`: 1.02600386 pN/nm
- `equilibrium_axial_repulsive_lift_nm`: 1.685843796 nm

### 4. Tooth critical-dimension tolerance

| CD error (nm) | Repulsive F (pN) | Engaged F (pN) | Swing (pN) | Repulsion + swing retained |
|---:|---:|---:|---:|:---:|
| -10 | 0.171815 | -0.332227 | 0.504042 | yes |
| -5 | 0.187692 | -0.347918 | 0.53561 | yes |
| 0 | 0.204222 | -0.363874 | 0.568096 | yes |
| 5 | 0.221357 | -0.379967 | 0.601324 | yes |
| 10 | 0.239078 | -0.396017 | 0.635094 | yes |

Requested ±10 nm robustness test passes: **yes**.
Engaged attraction retained at every CD: **yes**.

## Rot_C8_Compact_N2

Study status: `complete`

### 1. Material dispersion and temperature

| Regime | Angle (deg) | Fz (pN) | Wrep(30 nm)/kBT300 | Expected sign |
|---|---:|---:|---:|:---:|
| PEC_T0K | 3 | 2.19323 | 15.8855 | yes |
| PEC_T0K | 48 | -4.06104 | not available | yes |
| Gold_T0K | 3 | 0.238832 | 1.72986 | yes |
| Gold_T0K | 48 | -0.431566 | not available | yes |
| Gold_T300K | 3 | 0.243517 | 1.76378 | yes |
| Gold_T300K | 48 | -0.447448 | not available | yes |

### 2. Electrostatic residual-voltage bound

| Rotor shift (um) | Mutual capacitance (F) | Relative solve residual |
|---:|---:|---:|
| -0.002 | 1.175665382e-16 | 6.4472e-16 |
| 0 | 1.17993549e-16 | 6.62116e-16 |
| 0.002 | 1.183941074e-16 | 6.47453e-16 |

- dC/dz: 2.068922921e-10 F/m
- Absolute gradient coefficient: 0.0002068922921 pN/mV²
- Critical voltage: 48.51846904 mV (`finite`)
- Repulsion survives 50 mV: no

| Voltage (mV) | Net force (pN) |
|---:|---:|
| 0 | 0.243517 |
| 5 | 0.24093 |
| 10 | 0.233172 |
| 15 | 0.220241 |
| 20 | 0.202138 |
| 25 | 0.178863 |
| 30 | 0.150415 |
| 40 | 0.0780027 |
| 50 | -0.0150988 |

### 3. Lateral stiffness and four-spoke suspension

| Radial shift (um) | Energy (hbar*c/um) | Energy (pN um) |
|---:|---:|---:|
| 0 | -2.309397322 | -0.07301221463 |
| 0.004 | -2.30300768 | -0.07281020441 |
| 0.008 | -2.301212745 | -0.07275345704 |
- `k_r_Casimir_pN_per_um`: -9.078927371 pN/um
- `k_r_Casimir_pN_per_nm`: -0.009078927371 pN/nm
- `k_r_Casimir_N_per_m`: -9.078927371e-06 N/m
- `origin_even_energy_estimate_pN_per_um`: 25.25127681 pN/um
- `k_z_mech_pN_per_nm`: 0.1211392 pN/nm
- `k_r_mech_pN_per_nm`: 1.030524444 pN/nm
- `lateral_stability_safety_factor`: 113.5072903
- `combined_radial_stiffness_pN_per_nm`: 1.021445517 pN/nm
- `equilibrium_axial_repulsive_lift_nm`: 2.010220934 nm

### 4. Tooth critical-dimension tolerance

| CD error (nm) | Repulsive F (pN) | Engaged F (pN) | Swing (pN) | Repulsion + swing retained |
|---:|---:|---:|---:|:---:|
| -10 | 0.201818 | -0.383717 | 0.585536 | yes |
| -5 | 0.222654 | -0.415048 | 0.637702 | yes |
| 0 | 0.243517 | -0.447448 | 0.690965 | yes |
| 5 | 0.264459 | -0.481272 | 0.745732 | yes |
| 10 | 0.286004 | -0.516443 | 0.802447 | yes |

Requested ±10 nm robustness test passes: **yes**.
Engaged attraction retained at every CD: **yes**.

## Interpretation limits

- The active-sector 3D BEM backend is the only Casimir source.
- Material labels are passed to the backend without substituting a material model.
- Finite mesh/frequency settings require a separate convergence study.
- The voltage test is a mutual-capacitance residual/RMS-voltage bound; it does not integrate a spatial patch-potential spectrum.
- Three radial samples test one collective tooth-shift coordinate, not the complete lateral/rotational mechanical Hessian.
- The requested positive-offset origin-energy estimate assumes vanishing first derivative and is not a centered stiffness at zero displacement.
- Axial lift uses a linearized suspension, not a force-displacement equilibrium solve.
