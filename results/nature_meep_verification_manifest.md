# Nature six-step Meep verification campaign

- Target: BigRed 200; 3D Meep FDTD.
- Configuration directory: `C:\Users\gorengor\Goren\IUB\Research\FractalCasimirEffect\Code\3Dsimulations\sweep_configs_nature_meep_verification`.
- Generated: 12 / 12 planned tasks.
- Complete campaign: yes.
- Sum of moments_per_config: 1080.
- Sum of total_moments: 4320.

All lengths are in micrometers unless otherwise indicated. Track elements are sorted by increasing r_inner.

| Task | Configuration | Steps | Tracks | θ (deg) | R (px/µm) | dx (nm) | d_eff (µm) | T_run | Sigma | Moments/config | Total moments |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `Step1_SingleTooth_Repulsive_z100_th3` | 1, 2 | 1 | 3 | 50 | 20 | 0.015 | 3 | 33.3333333 | 36 | 144 |
| 2 | `Step1_SingleTooth_AttractivePad_z100_th48` | 1, 2 | 1 | 48 | 50 | 20 | 0.015 | 3 | 33.3333333 | 36 | 144 |
| 3 | `Step1_SingleTooth_OverhangFlip_z055_th3` | 1 | 1 | 3 | 50 | 20 | 0.06 | 10.3616329 | 8.33333333 | 36 | 144 |
| 4 | `Step4_Ctrl_UniformPeriodic_th3_R50` | 4 | 3 | 3 | 50 | 20 | 0.015 | 3 | 33.3333333 | 108 | 432 |
| 5 | `Step4_Ctrl_UniformPeriodic_th48_R50` | 4 | 3 | 48 | 50 | 20 | 0.015 | 3 | 33.3333333 | 108 | 432 |
| 6 | `Step3_4_Cantor_N2_FlatZ_th3_R50` | 3, 4 | 3 | 3 | 50 | 20 | 0.015 | 3 | 33.3333333 | 108 | 432 |
| 7 | `Step3_4_Cantor_N2_FlatZ_th48_R50` | 3, 4 | 3 | 48 | 50 | 20 | 0.015 | 3 | 33.3333333 | 108 | 432 |
| 8 | `Step4_5_Cantor_N2_HybridRZ_th3_R50` | 4, 5 | 3 | 3 | 50 | 20 | 0.005 | 3 | 100 | 108 | 432 |
| 9 | `Step4_5_Cantor_N2_HybridRZ_th48_R50` | 4, 5 | 3 | 48 | 50 | 20 | 0.005 | 3 | 100 | 108 | 432 |
| 10 | `Step5_Rot_C8_Compact_N2_th3_R50` | 5 | 3 | 3 | 50 | 20 | 0.015 | 3 | 33.3333333 | 108 | 432 |
| 11 | `Step6_Conv_Cantor_N2_HybridRZ_th3_R40` | 6 | 3 | 3 | 40 | 25 | 0.005 | 3 | 100 | 108 | 432 |
| 12 | `Step6_Conv_Cantor_N2_HybridRZ_th3_R60` | 6 | 3 | 3 | 60 | 16.6667 | 0.005 | 3 | 100 | 108 | 432 |

## Verification comparisons

- Tasks 1–2: open-slot repulsion versus landing-pad attraction.
- Tasks 1 and 3: overhang-induced force-sign reversal.
- Tasks 4–7: equal-total-slot-width uniform control versus N=2 Cantor.
- Tasks 6–9: flat-z versus coupled (r,z) geometry.
- Task 10: compact-envelope peak-force design.
- Tasks 11, 8, and 12: identical disengaged hybrid geometry at R=40, 50, and 60.

No FDTD simulations are executed by this generator.
