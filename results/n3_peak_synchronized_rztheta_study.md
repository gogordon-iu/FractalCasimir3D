# Peak-Synchronized 3D $(r, z, \theta)$ $N=3$ Cantor Clutch & Area-Angle-Height Control Study

- **Generated (UTC)**: `2026-11-06T18:29:01.356641+00:00`
- **Quadrature**: `n_xi = 24`, `n_r = 2`, `n_phi_tooth = 3`, `n_z = 2`

## 1. Comparative Summary Table ($\theta = 3^\circ$ Disengaged Open-Slot Repulsion)

| Design Name | Role | $A_{\text{tooth}}$ [$\mu\text{m}^2$] | $F_z(3^\circ)$ [pN] | $F_z / A_{\text{tooth}}$ [pN/$\mu\text{m}^2$] | $\sum_k F_{z,k}/(2\pi R_k)$ [pN/$\mu\text{m}$] | Track Forces $[F_1,\dots,F_7]$ [pN] |
|---|---|---:|---:|---:|---:|---|
| `Fractal_N3_Cantor7Track_FlatZ` | `baseline_cantor_flatz` | 0.3104 | **+3.1774** | +10.24 | +0.8183 | `[+0.953, +0.243, +0.939, -0.003, +0.479, +0.216, +0.351]` |
| `Ctrl_Uniform7Track_FlatZ` | `ctrl_uniform_flatz` | 0.3104 | **+2.0553** | +6.62 | +0.4076 | `[+0.288, +0.321, +0.321, +0.307, +0.289, +0.269, +0.261]` |
| `Ctrl_Monotonic7Track_FlatZ` | `ctrl_monotonic_flatz` | 0.3355 | **+4.3854** | +13.07 | +1.3203 | `[+0.955, +0.994, +0.982, +0.930, +0.259, +0.256, +0.009]` |
| `Cantor_N3_PeakSync_IsoArea` | `cantor_peaksync_isoarea` | 0.3104 | **+4.8777** | +15.71 | +1.1709 | `[+1.228, +0.494, +1.110, +0.123, +0.764, +0.523, +0.634]` |
| `Cantor_N3_PeakSync_HighForce` | `cantor_peaksync_highforce` | 0.3569 | **+4.7795** | +13.39 | +1.2125 | `[+1.357, +0.567, +1.089, +0.152, +0.605, +0.525, +0.484]` |
| `Ctrl_Uniform_IsoAreaAngleHeight` | `ctrl_uniform_iso_aah` | 0.3104 | **+1.7664** | +5.69 | +0.3535 | `[+0.264, +0.276, +0.273, +0.245, +0.244, +0.236, +0.229]` |
| `Ctrl_OutOfPhase_IsoAreaAngleHeight` | `ctrl_outofphase_iso_aah` | 0.3104 | **+3.6012** | +11.60 | +0.7398 | `[+0.310, +0.188, +1.603, -0.007, +0.850, +0.163, +0.493]` |
| `Ctrl_Monotonic_SameRadialProf_IsoArea` | `ctrl_monotonic_sameradial_iso` | 0.3104 | **+4.3290** | +13.95 | +1.4118 | `[+1.306, +1.527, +1.151, -0.409, +0.182, +0.569, +0.003]` |
| `Ctrl_Monotonic_SameGenRule_IsoArea` | `ctrl_monotonic_samegen_iso` | 0.3104 | **+5.2191** | +16.81 | +1.5222 | `[+1.105, +1.051, +1.050, +1.073, +0.416, +0.417, +0.106]` |
