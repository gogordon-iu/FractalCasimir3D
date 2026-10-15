# Fractal Casimir Rotary Clutch: six-step narrative

- Status: **complete**
- Solver: `execution.casimir_bem_solver.run_bem_casimir_solver`
- Formulation for steps 1–5: `scalar_yukawa`
- Device: `cpu`
- Executed task records: 67
- Unique solver evaluations: 53
- Elapsed time before report generation: 479.409 s

## Numerical and provenance conventions

- All forces and energies below are solver outputs, not fitted or stipulated.
- Meshes contain one 90-degree sector; the solver supplies fourfold symmetry.
- Positive vertical force denotes repulsion; negative denotes attraction.
- Force density uses the full annular active footprint, not tooth area.
- Pad overlap is an analytic projected-area fraction, not a solver observable.
- Missing measurements are unavailable, never filled with zeros.
- Scalar/vector agreement and convergence are tested rather than assumed.
- Passive support validation includes union-boundary spider spokes and collars
  at z = 0.350–0.470 µm and the trench slab at z = −0.650–−0.550 µm.

## step1_single_tooth_ztip

Status: complete; records: 12.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| SingleTooth_Track0 | 3 | -0.11 | Active-Only | Standard | scalar_yukawa | 0.33467429 | -1.240776 |
| SingleTooth_Track0 | 48 | -0.11 | Active-Only | Standard | scalar_yukawa | -0.34846174 | -1.0301961 |
| SingleTooth_Track0 | 3 | -0.105 | Active-Only | Standard | scalar_yukawa | 0.36028596 | -1.2957226 |
| SingleTooth_Track0 | 48 | -0.105 | Active-Only | Standard | scalar_yukawa | -0.33071606 | -0.97649186 |
| SingleTooth_Track0 | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.38453789 | -1.3546548 |
| SingleTooth_Track0 | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.31366074 | -0.92554305 |
| SingleTooth_Track0 | 3 | -0.09 | Active-Only | Standard | scalar_yukawa | 0.40935301 | -1.4814785 |
| SingleTooth_Track0 | 48 | -0.09 | Active-Only | Standard | scalar_yukawa | -0.2820188 | -0.83140488 |
| SingleTooth_Track0 | 3 | -0.075 | Active-Only | Standard | scalar_yukawa | 0.27923303 | -1.6555478 |
| SingleTooth_Track0 | 48 | -0.075 | Active-Only | Standard | scalar_yukawa | -0.23911077 | -0.70791439 |
| SingleTooth_Track0 | 3 | -0.055 | Active-Only | Standard | scalar_yukawa | -0.22837976 | -1.6782794 |
| SingleTooth_Track0 | 48 | -0.055 | Active-Only | Standard | scalar_yukawa | -0.18766832 | -0.57320099 |

At z_tip = −0.100 µm:
- Aperture repulsion verified: True
- Pad attraction verified: True
- |pad force| / |aperture force|: 0.81568228

## step2_n0_angular_sweep

Status: complete; records: 9.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 0 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.53827441 | -1.4350158 |
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.38453789 | -1.3546548 |
| Fractal_N0_SingleTrack | 6 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.53827441 | -1.4350158 |
| Fractal_N0_SingleTrack | 12 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.39549472 | -1.4184336 |
| Fractal_N0_SingleTrack | 18 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.33193084 | -1.438069 |
| Fractal_N0_SingleTrack | 24 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.27157422 | -1.3076361 |
| Fractal_N0_SingleTrack | 30 | -0.1 | Active-Only | Standard | scalar_yukawa | -1.300577 | -2.0456658 |
| Fractal_N0_SingleTrack | 39 | -0.1 | Active-Only | Standard | scalar_yukawa | -1.3041548 | -1.9221899 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.31366074 | -0.92554305 |

computed

-hbar*c*d(energy_hbar_c_per_um)/d(theta_rad); nonuniform second-order finite differences.

| θ (deg) | τz (pN µm) |
|---:|---:|
| 0 | -0.097045176 |
| 3 | -1.0108799e-15 |
| 6 | 0.03067965 |
| 12 | 0.00046088395 |
| 18 | -0.016725083 |
| 24 | 0.091717818 |
| 30 | 0.12374753 |
| 39 | -0.11272302 |
| 48 | -0.28846532 |

## step3_fractal_hierarchy

Status: complete; records: 12.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.38453789 | -1.3546548 |
| Fractal_N0_SingleTrack | 21 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.020056278 | -1.2958745 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.31366074 | -0.92554305 |
| Fractal_N1_FundRing | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.11356664 | -0.98420352 |
| Fractal_N1_FundRing | 21 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.30361758 | -1.4655748 |
| Fractal_N1_FundRing | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.25645145 | -1.2296856 |
| Fractal_N2_Cantor3Track | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.7467202 | -3.2716685 |
| Fractal_N2_Cantor3Track | 21 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.29106842 | -3.6869669 |
| Fractal_N2_Cantor3Track | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.61656293 | -2.4221183 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 1.0351393 | -4.1394136 |
| Fractal_N3_Cantor7Track | 21 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.085177222 | -5.0860732 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.53501682 | -2.3897689 |

## step4_fractal_advantage

Status: complete; records: 10.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.7467202 | -3.2716685 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.61656293 | -2.4221183 |
| Cantor_N2_HybridRZ | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.75260477 | -3.2882411 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.62557787 | -2.5001795 |
| Ctrl_SingleWide | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.023552353 | -0.7017497 |
| Ctrl_SingleWide | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.25783956 | -1.386173 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.47567862 | -3.021837 |
| Ctrl_UniformPeriodic | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.64993542 | -2.4806158 |
| Ctrl_SizeMatched_Monotonic | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.76628264 | -3.2682116 |
| Ctrl_SizeMatched_Monotonic | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.6312607 | -2.4331351 |

## step5_best_active_configuration

Status: complete; records: 8.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Rot_C8_Compact_N2 | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 1.9871802 | -3.9099948 |
| Rot_C8_Compact_N2 | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.62766082 | -1.6305564 |
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.7467202 | -3.2716685 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.61656293 | -2.4221183 |
| Cantor_N2_HybridRZ | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.75260477 | -3.2882411 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.62557787 | -2.5001795 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 1.0351393 | -4.1394136 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.53501682 | -2.3897689 |

| Candidate | Repulsion (pN) | Attraction (pN) | Swing (pN) | Repulsion density (pN/µm²) |
|---|---:|---:|---:|---:|
| Rot_C8_Compact_N2 | 1.9871802 | -0.62766082 | 2.614841 | 1.9023733 |
| Cantor_N2_FlatZ | 0.7467202 | -0.61656293 | 1.3632831 | 0.13719389 |
| Cantor_N2_HybridRZ | 0.75260477 | -0.62557787 | 1.3781826 | 0.13827506 |
| Fractal_N3_Cantor7Track | 1.0351393 | -0.53501682 | 1.5701561 | 0.12516432 |

- Maximum-swing champion: **Rot_C8_Compact_N2**
- Maximum-repulsion champion: **Rot_C8_Compact_N2**
- Compact N=2 champion: **Cantor_N2_HybridRZ**

These are the specified 3° and 48° operating states, not a proof of globally maximal force over all angles.

## step6_monolithic_ultrahigh_validation

Status: complete; records: 16.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_HybridRZ | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.75260477 | -3.2882411 |
| Cantor_N2_HybridRZ | 3 | -0.1 | Full-Monolithic | Standard | scalar_yukawa | 0.70312838 | -3.4886425 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.62557787 | -2.5001795 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Full-Monolithic | Standard | scalar_yukawa | -0.66126894 | -2.6955276 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 1.0351393 | -4.1394136 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Full-Monolithic | Standard | scalar_yukawa | 0.98255219 | -4.3662102 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.53501682 | -2.3897689 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Full-Monolithic | Standard | scalar_yukawa | -0.57356371 | -2.6078316 |
| Cantor_N2_HybridRZ | 3 | -0.1 | Active-Only | Standard | scalar_yukawa | 0.75260477 | -3.2882411 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Active-Only | Standard | scalar_yukawa | -0.62557787 | -2.5001795 |
| Cantor_N2_HybridRZ | 3 | -0.1 | Active-Only | High | scalar_yukawa | 2.8285287 | -5.9970288 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Active-Only | High | scalar_yukawa | -3.5020381 | -7.0970187 |
| Cantor_N2_HybridRZ | 3 | -0.1 | Active-Only | Ultra_High | scalar_yukawa | 2.7359637 | -6.4530334 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Active-Only | Ultra_High | scalar_yukawa | -7.2830354 | -9.435125 |
| Cantor_N2_HybridRZ | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.39512799 | -2.4467794 |
| Cantor_N2_HybridRZ | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.36275918 | -1.9401834 |

### Active-only versus full monolithic

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Active-only versus full monolithic | 0.049476395 | 0.065740209 | False |
| Cantor_N2_HybridRZ | 48 | Active-only versus full monolithic | 0.035691064 | 0.057052952 | False |
| Fractal_N3_Cantor7Track | 3 | Active-only versus full monolithic | 0.052587115 | 0.050801969 | False |
| Fractal_N3_Cantor7Track | 48 | Active-only versus full monolithic | 0.038546891 | 0.072047999 | False |

### Resolution convergence

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard -> High | 2.075924 | 2.7583189 | False |
| Cantor_N2_HybridRZ | 48 | Standard -> High | 2.8764602 | 4.598085 | False |
| Cantor_N2_HybridRZ | 3 | High -> Ultra_High | 0.092565069 | 0.032725518 | True |
| Cantor_N2_HybridRZ | 48 | High -> Ultra_High | 3.7809973 | 1.0796563 | False |

### Vector-dyadic versus scalar-Yukawa

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard | 0.35747678 | 0.47498606 | False |
| Cantor_N2_HybridRZ | 48 | Standard | 0.26281869 | 0.42012146 | False |

Agreement is tested, not assumed. Scalar Yukawa and vector dyadic models can differ physically; a failed cross-check is retained.

## Artifacts

- `results/nature_6step_narrative_report.json`
- `results/nature_6step_narrative_data.csv`
- `results/macros_results.tex`
- `figures/fig_nature_6step_narrative.pdf`
- `figures/fig_nature_6step_narrative.png`
