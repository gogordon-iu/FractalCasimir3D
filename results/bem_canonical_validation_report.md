# 3D Vector-Dyadic BEM Canonical Validation Report (Referee Concerns 1 & 2)

- **Generated at**: `2026-11-05T23:58:05.255768+00:00`
- **Material**: Drude Gold ($\omega_p = 9.03\text{ eV}$, $\gamma = 0.053\text{ eV}$, $\varepsilon_{\text{bg}} = 1.0$)

## 1. Analytical Lifshitz Parallel-Plate Benchmark ($R = 1.0\ \mu\text{m}$ Disks)

| Gap $d$ (nm) | $d/R$ | $P_z^{\text{BEM}}$ Standard (Pa) | $P_z^{\text{BEM}}$ High (Pa) | $P_z^{\text{BEM}}$ Ultra-High (Pa) | $P_{z,\infty}^{\text{BEM}}$ Continuum (Pa) | Exact 1D Lifshitz $P_z^{\text{Lifshitz}}$ (Pa) | Continuum Rel. Error (%) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0.015 | -2745.8012 | -2805.2172 | -2832.1022 | -2872.4298 | -2880.4385 | 0.278% |
| 30 | 0.030 | -305.0409 | -308.3480 | -309.7989 | -311.9753 | -313.3216 | 0.430% |
| 50 | 0.050 | -57.4332 | -57.7642 | -57.8956 | -58.0927 | -58.6959 | 1.028% |
| 100 | 0.100 | -5.4526 | -5.4468 | -5.4389 | -5.4271 | -5.6557 | 4.042% |

- **Monotonic recovery of 1D Lifshitz limit as $d/R \to 0$**: `True` (4.042% at $d/R=0.100$ $\to$ 0.278% at $d/R=0.015$).

## 2. Energy-Derivative vs. Trace Force Consistency (`Cantor_N2_HybridRZ`)

| Angle $\theta$ (deg) | $E_C(z_0 - \Delta z)$ ($\text{pN}\cdot\mu\text{m}$) | $E_C(z_0)$ ($\text{pN}\cdot\mu\text{m}$) | $E_C(z_0 + \Delta z)$ ($\text{pN}\cdot\mu\text{m}$) | Direct Trace $F_z^{\text{trace}}$ (pN) | Central FD $-\partial E_C/\partial z_{\text{rotor}}$ (pN) | Relative Discrepancy (%) | Relative Agreement (%) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | -0.21015720 | -0.21099212 | -0.21181364 | +1.657036 | +1.656439 | 0.03604% | 99.96396% |
| 48 | -0.17640686 | -0.17489864 | -0.17339703 | -3.010007 | -3.009831 | 0.00584% | 99.99416% |

## 3. Matsubara Truncation Convergence ($T = 300\text{ K}$)

- **Fundamental Matsubara spacing at $T = 300\text{ K}$**: $\Delta\kappa = 2\pi k_B T / (\hbar c) = 0.82316622\ \mu\text{m}^{-1}$
- **Direct Matsubara summation cutoff**: $N_{\text{Matsubara}} = 64$ ($\kappa_{\max} = 52.68\ \mu\text{m}^{-1}$, $\hbar\omega_{\max} = 10.40\text{ eV}$) vs $2 N_{\text{Matsubara}} = 128$ ($N_{\text{poles}} = 129$)

| Configuration | $F_z(N)$ (pN) | $F_z(2N)$ (pN) | Relative Tail Residual $|F(2N)-F(N)|/|F(2N)|$ | Relative Tail Residual (%) |
|---|---:|---:|---:|---:|
| `Cantor_N2_HybridRZ` ($\theta = 3^\circ$) | +1.649163 | +1.656628 | 4.506e-03 | 0.45063% |
| `Cantor_N2_HybridRZ` ($\theta = 48^\circ$) | -2.986736 | -3.011645 | 8.271e-03 | 0.82708% |
