# Unified 3D Conformal-Recursive Polar Cantor Fractal: $2^3$ Factorial & Matched Controls Study

- **Generated (UTC)**: `2026-11-06T17:46:10.316247+00:00`
- **Quadrature Order**: `n_xi = 24`
- **Invariant Stator Pad Top**: `z_pad_top = -0.115 um` (strictly fixed across all designs)

## 1. $2^3$ Factorial Ablation & Matched Control Table ($\theta = 3^\circ$, Exact $A_{\text{tooth}} = 0.3104\ \mu\text{m}^2$)

| Code | Design Name | $(U_r, U_\theta, U_z)$ | $A_{\text{tooth}}$ [$\mu\text{m}^2$] | $F_z(3^\circ)$ [pN] | $F_z/A_{\text{tooth}}$ [pN/$\mu\text{m}^2$] | $\sum_k F_{z,k}/(2\pi R_k)$ [pN/$\mu\text{m}$] | Cantor Log-Mod Amp [%] | Per-Slot Forces $[F_1,\dots,F_7]$ [pN] |
|---|---|:---:|---:|---:|---:|---:|---:|---|
| `F0_000` | `Cantor_000_Baseline_Flat` | `(0,0,0)` | 0.3104 | **+3.1774** | +10.24 | +0.8183 | 3.04% | `[+0.953, +0.243, +0.939, -0.003, +0.479, +0.216, +0.351]` |
| `F1r_Sub` | `Cantor_100a_SubTeethOnly` | `(1,0,0)` | 0.3104 | **+5.4225** | +17.47 | +1.1933 | 2.65% | `[+0.906, +0.854, +0.790, +0.792, +0.696, +0.735, +0.650]` |
| `F1r_100` | `Cantor_100_RadialOnly` | `(1,0,0)` | 0.3104 | **+9.0910** | +29.29 | +1.8826 | 2.48% | `[+0.913, +1.713, +0.806, +2.939, +0.711, +1.352, +0.657]` |
| `F1t_010` | `Cantor_010_ThetaOnly` | `(0,1,0)` | 0.3104 | **+4.9753** | +16.03 | +1.0171 | 2.60% | `[+0.936, +0.273, +0.933, -0.010, +1.130, +0.424, +1.289]` |
| `F1z_001` | `Cantor_001_ZStepOnly` | `(0,0,1)` | 0.3104 | **+4.1070** | +13.23 | +1.0919 | 2.99% | `[+1.432, +0.216, +1.142, -0.005, +0.619, +0.185, +0.518]` |
| `F2rt_110` | `Cantor_110_RadialTheta_Planar1Mask` | `(1,1,0)` | 0.3049 | **+13.5440** | +44.41 | +2.5410 | 2.60% | `[+0.889, +1.957, +1.077, +4.633, +1.244, +2.488, +1.255]` |
| `F2rz_101` | `Cantor_101_RadialZ` | `(1,0,1)` | 0.3104 | **+13.9293** | +44.88 | +2.9609 | 2.75% | `[+1.678, +2.669, +1.433, +3.638, +1.265, +2.048, +1.198]` |
| `F2tz_011` | `Cantor_011_ThetaZ` | `(0,1,1)` | 0.3104 | **+8.2292** | +26.51 | +1.7920 | 2.86% | `[+1.906, +0.255, +1.808, -0.011, +1.916, +0.392, +1.964]` |
| `F3_111` | `Cantor_111_Unified3DFractal` | `(1,1,1)` | 0.3049 | **+18.5509** | +60.83 | +3.8129 | 2.80% | `[+1.976, +3.203, +1.817, +5.424, +1.621, +2.966, +1.544]` |
| `C1_Uni000` | `Ctrl_Uniform_000_Flat` | `(0,0,0)` | 0.3104 | **+2.0553** | +6.62 | +0.4076 | 3.96% | `[+0.288, +0.321, +0.321, +0.307, +0.289, +0.269, +0.261]` |
| `C2_Uni111` | `Ctrl_Uniform_111_Matched` | `(1,1,1)` | 0.3104 | **+3.1386** | +10.11 | +0.5705 | 3.83% | `[+0.325, +0.386, +0.428, +0.460, +0.487, +0.509, +0.543]` |
| `C3_MonoGen` | `Ctrl_Monotonic_111_Matched` | `(0,1,1)` | 0.3104 | **+7.8420** | +25.27 | +2.4078 | 2.93% | `[+1.881, +1.782, +1.741, +1.737, +0.327, +0.368, +0.006]` |
| `C4_Shuf111` | `Ctrl_Shuffled_111_IsoArea` | `(0,1,1)` | 0.3104 | **+6.7585** | +21.77 | +1.3168 | 2.92% | `[+0.202, +1.815, +1.831, -0.018, +0.348, +1.068, +1.511]` |
| `C5_OutPhase` | `Ctrl_OutOfPhase_111_IsoArea` | `(0,1,1)` | 0.3104 | **+7.1966** | +23.19 | +1.3183 | 2.86% | `[+0.936, +0.240, +1.465, -0.022, +1.684, +0.366, +2.528]` |

## 2. Factorial Main Effects & Multi-Dimensional Synergies

- **Single Upgrade $U_r$ (`F1r_100 - F0_000`)**: `+5.9135 pN`
- **Single Upgrade $U_\theta$ (`F1t_010 - F0_000`)**: `+1.7979 pN`
- **Single Upgrade $U_z$ (`F1z_001 - F0_000`)**: `+0.9296 pN`
- **Factorial Main Effect $\Delta F_r$**: `+8.6565 pN`
- **Factorial Main Effect $\Delta F_\theta$**: `+3.7487 pN`
- **Factorial Main Effect $\Delta F_z$**: `+3.5072 pN`
- **Two-Way Synergy $\Delta F_{r,\theta}$**: `+2.6551 pN`
- **Two-Way Synergy $\Delta F_{r,z}$**: `+3.9088 pN`
- **Two-Way Synergy $\Delta F_{\theta,z}$**: `+2.3243 pN`
- **Three-Way Synergy $\Delta F_{r,\theta,z}$**: `-2.1557 pN`
- **Total Gain (`F3_111` vs. `F0_000`)**: `+15.3734 pN` (`+483.8%`)
