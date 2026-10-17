# Top repulsive Cantor-ring verification

- Started (UTC): 2026-10-17T03:02:54.569475+00:00
- Device: cpu; formulation: vector_dyadic
- Solver max steps: 2 (forwarded unchanged)
- Successful tasks: 1; failed tasks: 0
- Force convention: positive repulsive; negative attractive.

**Step-limited probe: these results are not evidence of solver convergence.**

## All tasks

Tasks not selected for this run are marked not run.

| Task | State | θ (deg) | z tip (µm) | Mesh (r/tooth/bridge/z) | n ξ | Status | Force (pN) | Class | Panels | Solver seconds | Wall seconds | Error |
|---|---|---:|---:|---|---:|---|---:|---|---:|---:|---:|---|
| C4_disengaged_base | disengaged | 0 | -0.1 | 2/3/3/2 | 24 | completed | -0.058015729 | attractive | 1488 | 6.4344326 | 20.241157 |  |
| C4_disengaged_highres | disengaged | 0 | -0.1 | 2/4/4/2 | 32 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C4_slot_offset_4deg | slot_offset | 4 | -0.1 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C4_engaged_pad_z15nm | engaged | 45 | 0.015 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C8_disengaged_base | disengaged | 3 | -0.1 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C8_disengaged_highres | disengaged | 3 | -0.1 | 2/4/4/2 | 32 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C8_slot_offset_4deg | slot_offset | 7 | -0.1 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C8_engaged_pad_z15nm | engaged | 48 | 0.015 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C10_disengaged_base | disengaged | 3 | -0.1 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C10_disengaged_highxi | disengaged | 3 | -0.1 | 2/3/3/2 | 32 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C10_slot_offset_4deg | slot_offset | 7 | -0.1 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |
| C10_engaged_pad_z15nm | engaged | 48 | 0.015 | 2/3/3/2 | 24 | not run | N/A | N/A | N/A | N/A | N/A |  |

## 24-point vs 32-point convergence

Relative difference = |F32 − F24| / max(|F24|, |F32|); defined as zero when both forces are zero.
C4/C8 also refine the azimuthal mesh; C10 keeps the mesh fixed.

| Winner | F24 (N) | F32 (N) | Relative difference | Tolerance | Within tolerance | Sign preserved | Note |
|---|---:|---:|---:|---:|---|---|---|
| C4 | N/A | N/A | N/A | N/A | N/A | N/A | Both baseline and high-resolution results are required. |
| C8 | N/A | N/A | N/A | N/A | N/A | N/A | Both baseline and high-resolution results are required. |
| C10 | N/A | N/A | N/A | N/A | N/A | N/A | Both baseline and high-resolution results are required. |

## Bipolar Disengaged-Repulsive vs Engaged-Attractive contrast

Contrast ratio = F_disengaged / |F_engaged|, using the 24-point disengaged baseline. It is reported only when the disengaged force is positive and the engaged force is negative. Missing, zero-divisor, non-bipolar, or nonfinite ratios are N/A.

| Winner | Disengaged force (N) | Engaged force (N) | Bipolar observed | Contrast ratio | Off-center force (N) |
|---|---:|---:|---|---:|---:|
| C4 | -5.8015729e-14 | N/A | N/A | N/A | N/A |
| C8 | N/A | N/A | N/A | N/A | N/A |
| C10 | N/A | N/A | N/A | N/A | N/A |

## Warnings

- Step-limited results are probes, not evidence of solver convergence.
