# Top repulsive Cantor-ring verification

- Started (UTC): 2026-10-17T14:48:53.325920+00:00
- Device: cpu; formulation: vector_dyadic
- Solver max steps: 0 (forwarded unchanged)
- Successful tasks: 12; failed tasks: 0
- Force convention: positive repulsive; negative attractive.

## All tasks

Tasks not selected for this run are marked not run.

| Task | State | θ (deg) | z tip (µm) | Mesh (r/tooth/bridge/z) | n ξ | Status | Force (pN) | Class | Panels | Solver seconds | Wall seconds | Error |
|---|---|---:|---:|---|---:|---|---:|---|---:|---:|---:|---|
| C4_disengaged_base | disengaged | 0 | -0.1 | 2/3/3/2 | 24 | completed | -2.2227407 | attractive | 1488 | 84.45289 | 113.39136 |  |
| C4_disengaged_highres | disengaged | 0 | -0.1 | 2/4/4/2 | 32 | completed | -2.4735769 | attractive | 1888 | 165.08926 | 194.50418 |  |
| C4_slot_offset_4deg | slot_offset | 4 | -0.1 | 2/3/3/2 | 24 | completed | -2.3890354 | attractive | 1488 | 88.055779 | 117.99869 |  |
| C4_engaged_pad_z15nm | engaged | 45 | 0.015 | 2/3/3/2 | 24 | completed | -3.7329353 | attractive | 1488 | 91.033666 | 120.38298 |  |
| C8_disengaged_base | disengaged | 3 | -0.1 | 2/3/3/2 | 24 | completed | -1.9390014 | attractive | 1488 | 85.355663 | 115.47405 |  |
| C8_disengaged_highres | disengaged | 3 | -0.1 | 2/4/4/2 | 32 | completed | -2.2580396 | attractive | 1888 | 174.74792 | 204.08856 |  |
| C8_slot_offset_4deg | slot_offset | 7 | -0.1 | 2/3/3/2 | 24 | completed | -1.8512743 | attractive | 1488 | 82.292264 | 116.02849 |  |
| C8_engaged_pad_z15nm | engaged | 48 | 0.015 | 2/3/3/2 | 24 | completed | -4.1053592 | attractive | 1488 | 90.250971 | 121.08262 |  |
| C10_disengaged_base | disengaged | 3 | -0.1 | 2/3/3/2 | 24 | completed | -3.9010364 | attractive | 3216 | 354.8868 | 385.01307 |  |
| C10_disengaged_highxi | disengaged | 3 | -0.1 | 2/3/3/2 | 32 | completed | -3.9010366 | attractive | 3216 | 467.83577 | 497.79045 |  |
| C10_slot_offset_4deg | slot_offset | 7 | -0.1 | 2/3/3/2 | 24 | completed | -4.046325 | attractive | 3216 | 345.34808 | 375.25005 |  |
| C10_engaged_pad_z15nm | engaged | 48 | 0.015 | 2/3/3/2 | 24 | completed | -12.216634 | attractive | 3216 | 372.54801 | 402.42454 |  |

## 24-point vs 32-point convergence

Relative difference = |F32 − F24| / max(|F24|, |F32|); defined as zero when both forces are zero.
C4/C8 also refine the azimuthal mesh; C10 keeps the mesh fixed.

| Winner | F24 (N) | F32 (N) | Relative difference | Tolerance | Within tolerance | Sign preserved | Note |
|---|---:|---:|---:|---:|---|---|---|
| C4 | -2.2227407e-12 | -2.4735769e-12 | 0.10140627 | 0.05 | False | True | Joint azimuthal mesh/quadrature comparison; does not isolate their errors. |
| C8 | -1.9390014e-12 | -2.2580396e-12 | 0.14128991 | 0.05 | False | True | Joint azimuthal mesh/quadrature comparison; does not isolate their errors. |
| C10 | -3.9010364e-12 | -3.9010366e-12 | 5.1270449e-08 | 0.05 | True | True | Quadrature-only comparison at fixed mesh. |

## Bipolar Disengaged-Repulsive vs Engaged-Attractive contrast

Contrast ratio = F_disengaged / |F_engaged|, using the 24-point disengaged baseline. It is reported only when the disengaged force is positive and the engaged force is negative. Missing, zero-divisor, non-bipolar, or nonfinite ratios are N/A.

| Winner | Disengaged force (N) | Engaged force (N) | Bipolar observed | Contrast ratio | Off-center force (N) |
|---|---:|---:|---|---:|---:|
| C4 | -2.2227407e-12 | -3.7329353e-12 | False | N/A | -2.3890354e-12 |
| C8 | -1.9390014e-12 | -4.1053592e-12 | False | N/A | -1.8512743e-12 |
| C10 | -3.9010364e-12 | -1.2216634e-11 | False | N/A | -4.046325e-12 |
