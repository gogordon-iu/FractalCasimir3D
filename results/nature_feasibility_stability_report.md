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

Legacy 30 nm work is the single-point force × 0.030 um extrapolation. Basin work is max(force, 0) × 0.5 × 0.016 um, using an approximately 16 nm triangular repulsive profile. Neither is a computed force integral.

| Regime | Angle (deg) | Fz (pN) | Legacy Wrep(30 nm)/kBT300 | Basin work (pN um) | Basin work/kBT300 | Expected sign |
|---|---:|---:|---:|---:|---:|:---:|
| PEC_T0K | 3 | 2.52898 | 18.3173 | 0.0202318 | 4.88461 | yes |
| PEC_T0K | 48 | -9.2572 | not available | not available | not available | yes |
| Gold_T0K | 3 | 0.758868 | 5.49646 | 0.00607094 | 1.46572 | yes |
| Gold_T0K | 48 | -1.79512 | not available | not available | not available | yes |
| Gold_T300K | 3 | 0.757441 | 5.48612 | 0.00605953 | 1.46297 | yes |
| Gold_T300K | 48 | -1.79121 | not available | not available | not available | yes |

### 2. Electrostatic residual-voltage bound

| Rotor shift (um) | Mutual capacitance (F) | Relative solve residual |
|---:|---:|---:|
| -0.002 | 1.681883873e-16 | 6.08108e-16 |
| 0 | 1.68621526e-16 | 6.99687e-16 |
| 0.002 | 1.690245244e-16 | 6.21476e-16 |

- dC/dz: 2.09034274e-10 F/m
- Absolute gradient coefficient: 0.000209034274 pN/mV²
- Critical voltage: 85.12961468 mV (`finite`)
- Repulsion survives 50 mV: yes

| Voltage (mV) | Net force (pN) |
|---:|---:|
| 0 | 0.757441 |
| 5 | 0.754828 |
| 10 | 0.746989 |
| 15 | 0.733925 |
| 20 | 0.715634 |
| 25 | 0.692118 |
| 30 | 0.663376 |
| 40 | 0.590214 |
| 50 | 0.496148 |

### 3. Lateral stiffness and four-spoke suspension

| Radial shift (um) | Energy (hbar*c/um) | Energy (pN um) |
|---:|---:|---:|
| 0 | -3.672031285 | -0.1160922522 |
| 0.004 | -3.681876948 | -0.1164035255 |
| 0.008 | -3.654060592 | -0.1155241039 |
- `k_r_Casimir_pN_per_um`: 74.41842804 pN/um
- `k_r_Casimir_pN_per_nm`: 0.07441842804 pN/nm
- `k_r_Casimir_N_per_m`: 7.441842804e-05 N/m
- `origin_even_energy_estimate_pN_per_um`: -38.90916145 pN/um
- `k_z_mech_pN_per_nm`: 0.1211392 pN/nm
- `k_r_mech_pN_per_nm`: 1.030524444 pN/nm
- `lateral_stability_safety_factor`: 13.84770509
- `combined_radial_stiffness_pN_per_nm`: 1.104942872 pN/nm
- `equilibrium_axial_repulsive_lift_nm`: 6.252650282 nm

### 4. Tooth critical-dimension tolerance

| CD error (nm) | Repulsive F (pN) | Engaged F (pN) | Swing (pN) | Repulsion + swing retained |
|---:|---:|---:|---:|:---:|
| -10 | 0.643253 | -1.61219 | 2.25544 | yes |
| -5 | 0.699346 | -1.70077 | 2.40012 | yes |
| 0 | 0.757441 | -1.79121 | 2.54865 | yes |
| 5 | 0.817385 | -1.8829 | 2.70028 | yes |
| 10 | 0.879328 | -1.97502 | 2.85435 | yes |

Requested ±10 nm robustness test passes: **yes**.
Engaged attraction retained at every CD: **yes**.

## Rot_C8_Compact_N2

Study status: `complete`

### 1. Material dispersion and temperature

Legacy 30 nm work is the single-point force × 0.030 um extrapolation. Basin work is max(force, 0) × 0.5 × 0.016 um, using an approximately 16 nm triangular repulsive profile. Neither is a computed force integral.

| Regime | Angle (deg) | Fz (pN) | Legacy Wrep(30 nm)/kBT300 | Basin work (pN um) | Basin work/kBT300 | Expected sign |
|---|---:|---:|---:|---:|---:|:---:|
| PEC_T0K | 3 | 3.12697 | 22.6485 | 0.0250157 | 6.03961 | yes |
| PEC_T0K | 48 | -14.4428 | not available | not available | not available | yes |
| Gold_T0K | 3 | 0.904683 | 6.55259 | 0.00723746 | 1.74736 | yes |
| Gold_T0K | 48 | -2.00068 | not available | not available | not available | yes |
| Gold_T300K | 3 | 0.90372 | 6.54562 | 0.00722976 | 1.7455 | yes |
| Gold_T300K | 48 | -1.99718 | not available | not available | not available | yes |

### 2. Electrostatic residual-voltage bound

| Rotor shift (um) | Mutual capacitance (F) | Relative solve residual |
|---:|---:|---:|
| -0.002 | 1.175665396e-16 | 6.37378e-16 |
| 0 | 1.179935504e-16 | 7.31843e-16 |
| 0.002 | 1.183941088e-16 | 6.17673e-16 |

- dC/dz: 2.068922979e-10 F/m
- Absolute gradient coefficient: 0.0002068922979 pN/mV²
- Critical voltage: 93.46731955 mV (`finite`)
- Repulsion survives 50 mV: yes

| Voltage (mV) | Net force (pN) |
|---:|---:|
| 0 | 0.90372 |
| 5 | 0.901134 |
| 10 | 0.893375 |
| 15 | 0.880445 |
| 20 | 0.862342 |
| 25 | 0.839066 |
| 30 | 0.810618 |
| 40 | 0.738206 |
| 50 | 0.645105 |

### 3. Lateral stiffness and four-spoke suspension

| Radial shift (um) | Energy (hbar*c/um) | Energy (pN um) |
|---:|---:|---:|
| 0 | -4.395577134 | -0.1389673479 |
| 0.004 | -4.364901403 | -0.1379975265 |
| 0.008 | -4.363516368 | -0.1379537382 |
- `k_r_Casimir_pN_per_um`: -57.8770752 pN/um
- `k_r_Casimir_pN_per_nm`: -0.0578770752 pN/nm
- `k_r_Casimir_N_per_m`: -5.78770752e-05 N/m
- `origin_even_energy_estimate_pN_per_um`: 121.2276808 pN/um
- `k_z_mech_pN_per_nm`: 0.1211392 pN/nm
- `k_r_mech_pN_per_nm`: 1.030524444 pN/nm
- `lateral_stability_safety_factor`: 17.80539947
- `combined_radial_stiffness_pN_per_nm`: 0.9726473692 pN/nm
- `equilibrium_axial_repulsive_lift_nm`: 7.460178219 nm

### 4. Tooth critical-dimension tolerance

| CD error (nm) | Repulsive F (pN) | Engaged F (pN) | Swing (pN) | Repulsion + swing retained |
|---:|---:|---:|---:|:---:|
| -10 | 0.752886 | -1.6611 | 2.41399 | yes |
| -5 | 0.827787 | -1.82577 | 2.65356 | yes |
| 0 | 0.90372 | -1.99718 | 2.9009 | yes |
| 5 | 0.979318 | -2.17683 | 3.15615 | yes |
| 10 | 1.05923 | -2.36419 | 3.42342 | yes |

Requested ±10 nm robustness test passes: **yes**.
Engaged attraction retained at every CD: **yes**.

## Interpretation limits

- The active-sector 3D BEM backend is the only Casimir source.
- Material labels are passed to the backend without substituting a material model.
- Finite mesh/frequency settings require a separate convergence study.
- W_rep_30nm_pN_um is retained as a legacy single-point force times 30 nm extrapolation, not work integrated over the repulsive basin.
- work_basin_pN_um uses max(force, 0) * 0.5 * 0.016 um for an approximately 16 nm triangular repulsive basin; it is a bounded profile-model estimate, not a computed force-displacement integral.
- The voltage test is a mutual-capacitance residual/RMS-voltage bound; it does not integrate a spatial patch-potential spectrum.
- Three radial samples test one collective tooth-shift coordinate, not the complete lateral/rotational mechanical Hessian.
- The requested positive-offset origin-energy estimate assumes vanishing first derivative and is not a centered stiffness at zero displacement.
- Axial lift uses a linearized suspension, not a force-displacement equilibrium solve.
- status='completed' marks output-record completion for freshness filtering; execution_status records scientific success, failure, timeout, or budget exhaustion.
