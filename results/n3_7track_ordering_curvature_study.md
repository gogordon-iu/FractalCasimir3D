# 7-Track Ordering & Curvature Decoupling Study (`N=3`, 3D Vector-Dyadic BEM)

## 1. Cylindrical Curvature vs. Quasi-Planar Track Ordering

| Regime | Constellation | Slot Widths (nm) | Raw $F_z$ (pN) | $F_z / A_{\rm tooth}$ (pN/$\mu$m$^2$) | $\sum_k F_{z,k}/(2\pi R_k)$ (pN/$\mu$m) | Per-Track $F_{z,k}$ (pN) |
|---|---|---|---:|---:|---:|---|
| Cylindrical $[0.30, 1.65]\,\mu$m | `Fractal_N3_Cantor7Track` | `[50, 150, 50, 450, 50, 150, 50]` | `+3.177433` | `+10.2369` | `+0.818327` | `[+0.9528, +0.2430, +0.9394, -0.0034, +0.4788, +0.2155, +0.3514]` |
| Cylindrical $[0.30, 1.65]\,\mu$m | `Ctrl_Uniform7Track` | `[136, 136, 136, 136, 136, 136, 136]` | `+2.055314` | `+6.6217` | `+0.407590` | `[+0.2877, +0.3212, +0.3210, +0.3072, +0.2886, +0.2691, +0.2606]` |
| Cylindrical $[0.30, 1.65]\,\mu$m | `Ctrl_Monotonic7Track` | `[50, 50, 50, 50, 150, 150, 450]` | `+4.385393` | `+13.0704` | `+1.320288` | `[+0.9546, +0.9945, +0.9822, +0.9303, +0.2588, +0.2559, +0.0091]` |
| Cylindrical $[0.30, 1.65]\,\mu$m | `Ctrl_RandomPermuted7Track` | `[150, 50, 450, 50, 50, 150, 50]` | `+2.767088` | `+9.1622` | `+0.544573` | `[+0.2193, +0.9900, -0.0096, +0.5370, +0.4637, +0.2154, +0.3514]` |
| Quasi-Planar Arc-Matched $[10.0, 11.35]\,\mu$m | `Fractal_N3_Cantor7Track` | `[50, 150, 50, 450, 50, 150, 50]` | `+3.344084` | `+10.7738` | `+0.050047` | `[+0.7564, +0.2508, +0.7305, +0.0007, +0.6885, +0.2447, +0.6725]` |
| Quasi-Planar Arc-Matched $[10.0, 11.35]\,\mu$m | `Ctrl_Uniform7Track` | `[136, 136, 136, 136, 136, 136, 136]` | `+2.182582` | `+7.0318` | `+0.032593` | `[+0.3247, +0.3123, +0.3103, +0.3085, +0.3068, +0.3054, +0.3145]` |
| Quasi-Planar Arc-Matched $[10.0, 11.35]\,\mu$m | `Ctrl_Monotonic7Track` | `[50, 50, 50, 50, 150, 150, 450]` | `+3.433160` | `+10.9796` | `+0.053151` | `[+0.7539, +0.7298, +0.7219, +0.7182, +0.2496, +0.2559, +0.0039]` |
| Quasi-Planar Arc-Matched $[10.0, 11.35]\,\mu$m | `Ctrl_RandomPermuted7Track` | `[150, 50, 450, 50, 50, 150, 50]` | `+3.283775` | `+10.6057` | `+0.048452` | `[+0.2616, +0.7376, +0.0004, +0.6919, +0.6752, +0.2445, +0.6725]` |
| Quasi-Planar Fixed-Angle $[10.0, 11.35]\,\mu$m | `Fractal_N3_Cantor7Track` | `[50, 150, 50, 450, 50, 150, 50]` | `+0.142795` | `+0.0420` | `+0.002152` | `[+0.0331, +0.0278, +0.0295, +0.0046, -0.0127, +0.0290, +0.0314]` |
| Quasi-Planar Fixed-Angle $[10.0, 11.35]\,\mu$m | `Ctrl_Uniform7Track` | `[136, 136, 136, 136, 136, 136, 136]` | `+0.180427` | `+0.0531` | `+0.002702` | `[+0.0343, +0.0291, +0.0188, +0.0239, +0.0257, +0.0254, +0.0233]` |
| Quasi-Planar Fixed-Angle $[10.0, 11.35]\,\mu$m | `Ctrl_Monotonic7Track` | `[50, 50, 50, 50, 150, 150, 450]` | `+0.172131` | `+0.0503` | `+0.002649` | `[+0.0360, +0.0306, +0.0299, +0.0243, +0.0226, +0.0236, +0.0051]` |
| Quasi-Planar Fixed-Angle $[10.0, 11.35]\,\mu$m | `Ctrl_RandomPermuted7Track` | `[150, 50, 450, 50, 50, 150, 50]` | `+0.185115` | `+0.0546` | `+0.002739` | `[+0.0281, +0.0324, +0.0050, +0.0306, +0.0251, +0.0318, +0.0321]` |

### Key Curvature Decoupling Findings
- **Cylindrical annulus $R \in [0.30, 1.65]\,\mu\text{m}$ ($R_{\max}/R_{\min} = 5.5$)**: `Ctrl_Monotonic7Track` gives `+4.385393 pN` vs. `+3.177433 pN` for `Fractal_N3_Cantor7Track` (`+38.02%` difference). Over 85% of the repulsive force originates from the four narrowest $50\text{ nm}$ slots ($g_{r,3} = 15\text{ nm}$), whose per-track force drops from `+0.9528 pN` at the innermost radius ($R_0 = 0.375\,\mu\text{m}$) to `+0.3514 pN` at the outermost radius ($R_6 = 1.575\,\mu\text{m}$). Because monotonic ordering packs all four $50\text{ nm}$ slots at the innermost radii ($R_c \in [0.375, 0.675]\,\mu\text{m}$, $\bar{R}_{50} = 0.525\,\mu\text{m}$) and relegates the zero-force $450\text{ nm}$ slot to the outer radius ($R_6 = 1.375\,\mu\text{m}$), it harvests `+3.862 pN` from the four $50\text{ nm}$ tracks alone versus `+2.722 pN` for the radially symmetric Cantor sequence ($\bar{R}_{50} = 0.975\,\mu\text{m}$).
- **Quasi-planar arc-length-matched annulus $R \in [10.0, 11.35]\,\mu\text{m}$ ($R_{\max}/R_{\min} = 1.135 \approx 1$)**: Eliminating cylindrical curvature collapses the Monotonic-vs.-Cantor gap by **14.3-fold**, from `+38.02%` (`+1.2080 pN`) down to just **`+2.66%`** (`+0.0891 pN`: `+3.433160 pN` vs. `+3.344084 pN`), while all multiscale permutations surpass the 7-track uniform periodic control (`+2.182582 pN`).

## 2. Multiset Permutation Distribution & Percentile Rank of the Cantor Sequence
- **Direct 3D BEM sample ($N_{\rm perm} = 30$ non-Cantor permutations + 1 Cantor = 31 evaluations)**:
  - Raw force $F_z$ range: `[+2.029615, +4.385393] pN` (mean `+3.268004 pN`, median `+3.239531 pN`, std `0.639914 pN`).
  - `30/31` permutations (`96.8%`; `105/105` = `100.0%` in the 105-permutation surrogate) exceed `Ctrl_Uniform7Track` (`+2.055314 pN`) by up to `2.13x`; only extreme outer-packed permutations such as `Ctrl_ReverseMonotonic7Track` (`[450, 150, 150, 50, 50, 50, 50]` nm, `+2.029615 pN`) fall slightly below `+2.055314 pN`.
  - **Exact empirical Cantor raw force $F_z = +3.177433\text{ pN}$ percentile (across the $N_{\rm perm} = 30$ directly evaluated 3D BEM permutations)**: Rank `13/31` from bottom (**`40.00`th percentile**; radial-polynomial surrogate estimate across all 105 multiset permutations: `49.04`th percentile, estimated rank `52/105`, surrogate MAE `0.0663 pN`).
  - **Exact empirical Cantor circumference-normalized $\sum_k F_{z,k}/(2\pi R_k) = +0.818327\text{ pN}/\mu\text{m}$ percentile (across the $N_{\rm perm} = 30$ directly evaluated 3D BEM permutations)**: Rank `16/31` from bottom (**`50.00`th percentile**; radial-polynomial surrogate estimate across all 105 multiset permutations: `56.73`th percentile, estimated rank `60/105`).
  - **Quasi-planar $R \in [10.0, 11.35]\,\mu\text{m}$ Cantor percentile**: Exact rank `2/3` (`50.00`th percentile) among the directly evaluated multiscale configurations (`+3.283775 pN` (`Ctrl_RandomPermuted7Track`) < `+3.344084 pN` (`Fractal_N3_Cantor7Track`) < `+3.433160 pN` (`Ctrl_Monotonic7Track`)), and radial-surrogate estimated **`49.04`th percentile** in raw force $F_z$ (**`50.96`th percentile** in circumference-normalized force).

