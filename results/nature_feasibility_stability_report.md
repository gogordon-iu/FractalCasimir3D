# Nature feasibility and stability: real 3D BEM

**Status:** `complete`
**Mode:** `full`
**Completed BEM evaluations:** 48

Positive vertical force denotes repulsion. Full-study forces and energies use Gold at 300 K unless a row explicitly states otherwise.

## Numerical settings

```json
{
  "device": "cpu",
  "formulation": "vector_dyadic",
  "max_steps": 0,
  "micro_resolution_override": false,
  "n_phi_bridge": 3,
  "n_phi_tooth": 3,
  "n_r": 2,
  "n_xi": 24,
  "n_z": 2,
  "requested_resolution": {
    "n_phi_bridge": 3,
    "n_phi_tooth": 3,
    "n_r": 2,
    "n_xi": 24,
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
| PEC_T0K | 3 | 6.27131 | 45.4229 | 0.0501704 | 12.1128 | yes |
| PEC_T0K | 48 | -14.3629 | not available | not available | not available | yes |
| Gold_T0K | 3 | 1.65704 | 12.0019 | 0.0132563 | 3.2005 | yes |
| Gold_T0K | 48 | -3.01001 | not available | not available | not available | yes |
| Gold_T300K | 3 | 1.6571 | 12.0024 | 0.0132568 | 3.20063 | yes |
| Gold_T300K | 48 | -3.01241 | not available | not available | not available | yes |

### 2. Residual electrostatic bias threshold (V_crit)

| Rotor shift (um) | Mutual capacitance (F) | Relative solve residual |
|---:|---:|---:|
| -0.002 | 1.930647804e-16 | 1.06485e-15 |
| 0 | 1.939067162e-16 | 8.28375e-16 |
| 0.002 | 1.946927604e-16 | 8.65807e-16 |

- dC/dz: 4.069950004e-10 F/m
- Absolute gradient coefficient: 0.0004069950004 pN/mV²
- Critical voltage: 90.23921995 mV (`finite`)
- Repulsion survives 50 mV: yes

| Voltage (mV) | Net force (pN) |
|---:|---:|
| 0 | 1.6571 |
| 5 | 1.65202 |
| 10 | 1.63675 |
| 15 | 1.61132 |
| 20 | 1.5757 |
| 25 | 1.52992 |
| 30 | 1.47396 |
| 40 | 1.33151 |
| 50 | 1.14836 |

### 3. Lateral stiffness and four-spoke suspension

| Radial shift (um) | Energy (hbar*c/um) | Energy (pN um) |
|---:|---:|---:|
| 0 | -6.708913462 | -0.2121040953 |
| 0.004 | -6.833260736 | -0.2160353677 |
| 0.008 | -7.115697315 | -0.2249646757 |
- `k_r_Casimir_pN_per_um`: -312.3772329 pN/um
- `k_r_Casimir_pN_per_nm`: -0.3123772329 pN/nm
- `k_r_Casimir_N_per_m`: -0.0003123772329 N/m
- `origin_even_energy_estimate_pN_per_um`: -491.4090427 pN/um
- `k_z_mech_pN_per_nm`: 121.1392 pN/nm
- `k_r_mech_pN_per_nm`: 1030.524444 pN/nm
- `lateral_stability_safety_factor`: 3298.97424
- `combined_radial_stiffness_pN_per_nm`: 1030.212067 pN/nm
- `equilibrium_axial_repulsive_lift_nm`: 0.0136793368 nm
- `self_consistent_basin_repulsive_lift_nm`: 0.01366765152 nm
- `k_z_crit_pull_in_pN_per_nm`: 2.177916815 pN/nm
- `vertical_pull_in_safety_factor`: 55.62159177

| Suspension regime | L_spoke (um) | w_spoke (um) | t_spoke (um) | k_z (pN/nm) | k_r (pN/nm) | Radial SF | Pull-in SF | Linear lift (nm) | Basin eq. lift (nm) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `compact_high_aspect_clutch` | 60 | 0.35 | 0.05 | 0.136921 | 6.70914 | 21.4777 | 0.062868 | 12.1026 | 6.89052 |
| `high_stroke_clutch` | 150 | 0.35 | 0.12 | 0.121139 | 1.03052 | 3.29897 | 0.0556216 | 13.6793 | 7.37447 |
| `isometric_transducer` | 15 | 0.35 | 0.12 | 121.139 | 1030.52 | 3298.97 | 55.6216 | 0.0136793 | 0.0136677 |
| `noncontact_nm_actuator` | 65 | 0.4 | 0.075 | 0.415385 | 11.8154 | 37.8241 | 0.190726 | 3.98932 | 3.19316 |

### 4. Tooth critical-dimension tolerance

| CD error (nm) | Repulsive F (pN) | Engaged F (pN) | Swing (pN) | Repulsion + swing retained |
|---:|---:|---:|---:|:---:|
| -10 | 1.34311 | -2.76995 | 4.11306 | yes |
| -5 | 1.49321 | -2.88811 | 4.38132 | yes |
| 0 | 1.6571 | -3.01241 | 4.66952 | yes |
| 5 | 1.84677 | -3.14397 | 4.99074 | yes |
| 10 | 2.09395 | -3.28558 | 5.37953 | yes |

Requested ±10 nm robustness test passes: **yes**.
Engaged attraction retained at every CD: **yes**.

### 5. 3D BEM rotational energy barrier E_C(theta) & Casimir torque

- Switching work W_switch (|E_C(3°) - E_C(48°)|): 0.225905 eV (0.036194 aJ, 8.73839 k_B T_300)
- Barrier climb from straddling minimum: 0.323436 eV
- Peak-to-valley energy barrier: 0.549341 eV
- Peak Casimir torque |tau_theta|_max: 263.857 pN·nm (at theta = 12 deg)

| Angle (deg) | Fz (pN) | E_C (aJ) | Delta E_C (eV) | tau_theta (pN·nm) |
|---:|---:|---:|---:|---:|
| 0 | 1.59539 | -0.208662 | 0 | 131.466 |
| 3 | 1.6571 | -0.212104 | -0.0214819 | -9.88416e-12 |
| 6 | 1.59539 | -0.208662 | 6.43929e-15 | 24.3008 |
| 12 | 1.02915 | -0.230064 | -0.133577 | 263.857 |
| 18 | -1.48053 | -0.263924 | -0.344918 | 27.2627 |
| 24 | -2.07709 | -0.235774 | -0.169215 | -255.288 |
| 30 | -3.10428 | -0.210457 | -0.0112008 | -204.55 |
| 36 | -3.79874 | -0.192933 | 0.0981766 | -116.553 |
| 42 | -3.7724 | -0.186046 | 0.141159 | -81.2767 |
| 48 | -3.01241 | -0.17591 | 0.204423 | -112.306 |

### 6. Room-temperature (300 K) thermomechanical noise & lock-in SNR

- Unit engine: `pint 0.26.2`, modal mass factor `0.375`
- Rigid Gold rotor mass: 5.58913 pg (volume 0.289592 um³)
- Vertical standoff sensitivity dF_z/dz_0: -0.103569 pN/nm

| Suspension regime | m_eff (pg) | f_0 beam (kHz) | f_0 FEM (kHz) | delta z_th (nm) | S_F^{1/2} (fN/rtHz, Q=10^4) | S_F^{1/2} (fN/rtHz, Q=10^5) | SNR (1 s, Q=10^4) | SNR (1 s, Q=10^5) | tau(SNR=100, Q=10^4, us) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `compact_high_aspect_clutch` | 9.2573 | 19.3559 | 19.344 | 5.50005 | 0.0431888 | 0.0136575 | 38368.8 | 121333 | 6.7927 |
| `high_stroke_clutch` | 27.5982 | 10.5444 | 10.4768 | 5.84736 | 0.0550394 | 0.017405 | 30107.6 | 95208.6 | 11.0318 |
| `isometric_transducer` | 7.79003 | 627.614 | 627.665 | 0.18491 | 0.2256 | 0.0713408 | 7345.33 | 23228 | 185.343 |
| `noncontact_nm_actuator` | 12.4015 | 29.1279 | 29.0634 | 3.15775 | 0.0613215 | 0.0193916 | 27023.2 | 85454.9 | 13.6939 |

### 7. Discretization & corner-rounding bounds on pull-in threshold and Regime I-III safety factors

| Tier | F_rep (pN) | F_att (pN) | V_crit (mV) | k_{z,crit}^{pull-in} (pN/nm) | SF_z (Reg I) | SF_z (Reg II) | SF_z (Reg III) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Standard sharp-edge BEM | 1.6571 | -3.01241 | 90.2392 | 2.17792 | 55.6216 | 0.190726 | 0.062868 |
| r_edge = 5 nm rounded Ultra-High BEM | 1.72521 | --- | 92.075 | --- | --- | --- | --- |
| Sharp Ultra-High BEM | 4.73868 | -16.5426 | 152.598 | 11.96 | 10.1287 | 0.0347312 | 0.0114483 |
| Continuum-extrapolated BEM | 2.52074 | -37.2316 | 111.297 | 26.9177 | 4.50035 | 0.0154316 | 0.00508666 |

## Rot_C8_Compact_N2

Study status: `complete`

### 1. Material dispersion and temperature

Legacy 30 nm work is the single-point force × 0.030 um extrapolation. Basin work is max(force, 0) × 0.5 × 0.016 um, using an approximately 16 nm triangular repulsive profile. Neither is a computed force integral.

| Regime | Angle (deg) | Fz (pN) | Legacy Wrep(30 nm)/kBT300 | Basin work (pN um) | Basin work/kBT300 | Expected sign |
|---|---:|---:|---:|---:|---:|:---:|
| PEC_T0K | 3 | 5.04324 | 36.528 | 0.0403459 | 9.7408 | yes |
| PEC_T0K | 48 | -27.3345 | not available | not available | not available | yes |
| Gold_T0K | 3 | 1.47825 | 10.7069 | 0.011826 | 2.85517 | yes |
| Gold_T0K | 48 | -4.29188 | not available | not available | not available | yes |
| Gold_T300K | 3 | 1.47825 | 10.707 | 0.011826 | 2.85519 | yes |
| Gold_T300K | 48 | -4.29461 | not available | not available | not available | yes |

### 2. Residual electrostatic bias threshold (V_crit)

| Rotor shift (um) | Mutual capacitance (F) | Relative solve residual |
|---:|---:|---:|
| -0.002 | 1.300576465e-16 | 8.09121e-16 |
| 0 | 1.307461283e-16 | 8.06918e-16 |
| 0.002 | 1.31392833e-16 | 8.79918e-16 |

- dC/dz: 3.337966361e-10 F/m
- Absolute gradient coefficient: 0.0003337966361 pN/mV²
- Critical voltage: 94.1127704 mV (`finite`)
- Repulsion survives 50 mV: yes

| Voltage (mV) | Net force (pN) |
|---:|---:|
| 0 | 1.47825 |
| 5 | 1.47408 |
| 10 | 1.46156 |
| 15 | 1.4407 |
| 20 | 1.41149 |
| 25 | 1.37394 |
| 30 | 1.32805 |
| 40 | 1.21122 |
| 50 | 1.06101 |

### 3. Lateral stiffness and four-spoke suspension

| Radial shift (um) | Energy (hbar*c/um) | Energy (pN um) |
|---:|---:|---:|
| 0 | -7.041069341 | -0.2226052924 |
| 0.004 | -7.127714981 | -0.2253446175 |
| 0.008 | -7.372723008 | -0.2330906118 |
- `k_r_Casimir_pN_per_um`: -312.9168278 pN/um
- `k_r_Casimir_pN_per_nm`: -0.3129168278 pN/nm
- `k_r_Casimir_N_per_m`: -0.0003129168278 N/m
- `origin_even_energy_estimate_pN_per_um`: -342.4156382 pN/um
- `k_z_mech_pN_per_nm`: 121.1392 pN/nm
- `k_r_mech_pN_per_nm`: 1030.524444 pN/nm
- `lateral_stability_safety_factor`: 3293.285477
- `combined_radial_stiffness_pN_per_nm`: 1030.211528 pN/nm
- `equilibrium_axial_repulsive_lift_nm`: 0.01220293715 nm
- `self_consistent_basin_repulsive_lift_nm`: 0.01219363727 nm
- `k_z_crit_pull_in_pN_per_nm`: 3.104921642 pN/nm
- `vertical_pull_in_safety_factor`: 39.0152197

| Suspension regime | L_spoke (um) | w_spoke (um) | t_spoke (um) | k_z (pN/nm) | k_r (pN/nm) | Radial SF | Pull-in SF | Linear lift (nm) | Basin eq. lift (nm) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `compact_high_aspect_clutch` | 60 | 0.35 | 0.05 | 0.136921 | 6.70914 | 21.4407 | 0.0440981 | 10.7964 | 6.44647 |
| `high_stroke_clutch` | 150 | 0.35 | 0.12 | 0.121139 | 1.03052 | 3.29329 | 0.0390152 | 12.2029 | 6.92293 |
| `isometric_transducer` | 15 | 0.35 | 0.12 | 121.139 | 1030.52 | 3293.29 | 39.0152 | 0.0122029 | 0.0121936 |
| `noncontact_nm_actuator` | 65 | 0.4 | 0.075 | 0.415385 | 11.8154 | 37.7589 | 0.133783 | 3.55876 | 2.91124 |

### 4. Tooth critical-dimension tolerance

| CD error (nm) | Repulsive F (pN) | Engaged F (pN) | Swing (pN) | Repulsion + swing retained |
|---:|---:|---:|---:|:---:|
| -10 | 1.25329 | -3.80566 | 5.05895 | yes |
| -5 | 1.37041 | -4.06473 | 5.43514 | yes |
| 0 | 1.47825 | -4.29461 | 5.77286 | yes |
| 5 | 1.57402 | -4.51628 | 6.09031 | yes |
| 10 | 1.6694 | -4.75372 | 6.42313 | yes |

Requested ±10 nm robustness test passes: **yes**.
Engaged attraction retained at every CD: **yes**.

### 5. 3D BEM rotational energy barrier E_C(theta) & Casimir torque

- Switching work W_switch (|E_C(3°) - E_C(48°)|): 0.228382 eV (0.0365908 aJ, 8.83419 k_B T_300)
- Barrier climb from straddling minimum: 0.286004 eV
- Peak-to-valley energy barrier: 0.514385 eV
- Peak Casimir torque |tau_theta|_max: 222.159 pN·nm (at theta = 12 deg)

| Angle (deg) | Fz (pN) | E_C (aJ) | Delta E_C (eV) | tau_theta (pN·nm) |
|---:|---:|---:|---:|---:|
| 0 | 1.49108 | -0.221899 | 0 | 26.9711 |
| 3 | 1.47825 | -0.222605 | -0.00440714 | -2.33626e-11 |
| 6 | 1.49108 | -0.221899 | 1.5099e-14 | 45.9124 |
| 12 | 0.747631 | -0.239147 | -0.107655 | 222.159 |
| 18 | -2.33622 | -0.268428 | -0.290411 | 25.9801 |
| 24 | -3.03296 | -0.244589 | -0.141617 | -219.207 |
| 30 | -4.29953 | -0.222518 | -0.00385923 | -190.336 |
| 36 | -5.20327 | -0.204725 | 0.107194 | -126.258 |
| 42 | -5.18985 | -0.196074 | 0.161188 | -89.335 |
| 48 | -4.29461 | -0.186015 | 0.223974 | -102.788 |

### 6. Room-temperature (300 K) thermomechanical noise & lock-in SNR

- Unit engine: `pint 0.26.2`, modal mass factor `0.375`
- Rigid Gold rotor mass: 3.04912 pg (volume 0.157985 um³)
- Vertical standoff sensitivity dF_z/dz_0: -0.0923909 pN/nm

| Suspension regime | m_eff (pg) | f_0 beam (kHz) | f_0 FEM (kHz) | delta z_th (nm) | S_F^{1/2} (fN/rtHz, Q=10^4) | S_F^{1/2} (fN/rtHz, Q=10^5) | SNR (1 s, Q=10^4) | SNR (1 s, Q=10^5) | tau(SNR=100, Q=10^4, us) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `compact_high_aspect_clutch` | 6.71729 | 22.7226 | 22.6732 | 5.50005 | 0.039861 | 0.0126052 | 37085.2 | 117274 | 7.27108 |
| `high_stroke_clutch` | 25.0582 | 11.0659 | 10.9753 | 5.84736 | 0.0537268 | 0.0169899 | 27514.3 | 87007.8 | 13.2094 |
| `isometric_transducer` | 5.25002 | 764.508 | 763.892 | 0.18491 | 0.204406 | 0.0646389 | 7231.95 | 22869.4 | 191.201 |
| `noncontact_nm_actuator` | 9.86144 | 32.6644 | 32.5218 | 3.15775 | 0.0579069 | 0.0183118 | 25528.1 | 80727 | 15.3448 |

### 7. Discretization & corner-rounding bounds on pull-in threshold and Regime I-III safety factors

| Tier | F_rep (pN) | F_att (pN) | V_crit (mV) | k_{z,crit}^{pull-in} (pN/nm) | SF_z (Reg I) | SF_z (Reg II) | SF_z (Reg III) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Standard sharp-edge BEM | 1.47825 | -4.29461 | 94.1128 | 3.10492 | 39.0152 | 0.133783 | 0.0440981 |
| r_edge = 5 nm rounded Ultra-High BEM | 1.72521 | --- | 101.671 | --- | --- | --- | --- |
| Sharp Ultra-High BEM | 4.73868 | -22.3163 | 168.501 | 16.1343 | 7.50819 | 0.0257455 | 0.00848637 |
| Continuum-extrapolated BEM | 2.52074 | -37.2316 | 122.896 | 26.9177 | 4.50035 | 0.0154316 | 0.00508666 |

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
