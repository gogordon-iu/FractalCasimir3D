# Unified 3D Conformal-Recursive Polar Cantor Fractal: $2^3$ Factorial & Matched Controls Study

- **Generated (UTC)**: `2026-11-07T01:40:15.073326+00:00`
- **Quadrature Order**: `n_xi = 24`
- **Invariant Stator Pad Top**: `z_pad_top = -0.115 um` (strictly fixed across all designs)

## 1. $2^3$ Factorial Ablation & Matched Control Table ($\theta = 3^\circ$, Target $A_{\text{tooth}} = 0.3104\ \mu\text{m}^2$)

| Code | Design Name | $(U_r, U_\theta, U_z)$ | $A_{\text{tooth}}$ [$\mu\text{m}^2$] | $F_z(3^\circ)$ [pN] | $F_z/A_{\text{tooth}}$ [pN/$\mu\text{m}^2$] | $\sum_k F_{z,k}/(2\pi R_k)$ [pN/$\mu\text{m}$] | Cantor Log-Mod Amp [%] | Per-Slot Forces $[F_1,\dots,F_K]$ [pN] |
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
| `C3_MonoGen` | `Ctrl_Monotonic_011_Matched` | `(0,1,1)` | 0.3104 | **+7.8420** | +25.27 | +2.4078 | 2.93% | `[+1.881, +1.782, +1.741, +1.737, +0.327, +0.368, +0.006]` |
| `C4_Shuf111` | `Ctrl_Shuffled_011_IsoArea` | `(0,1,1)` | 0.3104 | **+6.7585** | +21.77 | +1.3168 | 2.92% | `[+0.202, +1.815, +1.831, -0.018, +0.348, +1.068, +1.511]` |
| `C5_OutPhase` | `Ctrl_OutOfPhase_011_IsoArea` | `(0,1,1)` | 0.3104 | **+7.1966** | +23.19 | +1.3183 | 2.86% | `[+0.936, +0.240, +1.465, -0.022, +1.684, +0.366, +2.528]` |
| `C6_Uni12` | `Ctrl_Uniform12_111_IsoArea` | `(1,1,1)` | 0.3104 | **+13.9706** | +45.01 | +2.6495 | 3.18% | `[+0.997, +1.012, +1.049, +1.088, +1.125, +1.158, +1.188, +1.215, +1.239, +1.263, +1.286, +1.351]` |
| `C7_Lin12` | `Ctrl_Linear12_111_IsoArea` | `(1,1,1)` | 0.3104 | **+14.0404** | +45.23 | +3.5320 | 3.06% | `[+2.034, +1.734, +1.524, +1.362, +1.266, +1.193, +1.114, +1.043, +0.758, +0.712, +0.664, +0.635]` |
| `C8_Mono12` | `Ctrl_Monotonic7_12Sub_IsoArea` | `(1,1,1)` | 0.3104 | **+15.0679** | +48.55 | +3.5533 | 2.99% | `[+1.956, +1.866, +1.824, +1.787, +2.460, +2.480, +2.694]` |
| `C9_Shuf12` | `Ctrl_Shuffled7_12Sub_IsoArea` | `(1,1,1)` | 0.3104 | **+15.1719** | +48.88 | +3.0342 | 2.96% | `[+2.633, +1.723, +1.704, +3.086, +2.446, +1.471, +2.108]` |
| `C10_OutPhase12` | `Ctrl_OutOfPhase7_12Sub_IsoArea` | `(1,1,1)` | 0.3104 | **+14.2916** | +46.04 | +2.7414 | 3.02% | `[+0.954, +2.671, +1.467, +2.947, +1.613, +2.807, +1.832]` |

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

## 3. Pinpointing Physical Contributions: 7-Tooth vs. 12-Tooth Non-Fractal Controls

- **`F3_111` vs. `C6_Uni12` (12 Uniform Slots/Teeth, 24 Lobes)**: `+4.5803 pN` (`+32.8%`)
- **`F3_111` vs. `C7_Lin12` (12 Linearly Graded Slots/Teeth, 24 Lobes)**: `+4.5105 pN` (`+32.1%`)
- **`F3_111` vs. `C8_Mono12` (7 Monotonic Slots with 12 Equal Sub-Slots/Teeth, 24 Lobes)**: `+3.4829 pN` (`+23.1%`)
- **`F3_111` vs. `C9_Shuf12` (7 Shuffled Slots with 12 Equal Sub-Slots/Teeth, 24 Lobes)**: `+3.3789 pN` (`+22.3%`)
- **`F3_111` vs. `C10_OutPhase12` (7 Primary Cantor Slots with 12 Equal Sub-Slots & Out-of-Phase $(\theta, z)$)**: `+4.2593 pN` (`+29.8%`)
