# Fractal Casimir Rotary Clutch: six-step narrative

- Status: **complete**
- Solver: `execution.casimir_bem_solver.run_bem_casimir_solver`
- Formulation for steps 1–5: `vector_dyadic`
- Device: `cpu`
- Executed task records: 67
- Unique solver evaluations represented: 53
- New BEM evaluations this run: 0
- Elapsed time before report generation: 242.529 s

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
| SingleTooth_Track0 | 3 | -0.11 | Active-Only | Standard | vector_dyadic | 0.15660786 | -0.85484416 |
| SingleTooth_Track0 | 48 | -0.11 | Active-Only | Standard | vector_dyadic | -0.15383799 | -0.68212752 |
| SingleTooth_Track0 | 3 | -0.105 | Active-Only | Standard | vector_dyadic | 0.13553647 | -0.87791613 |
| SingleTooth_Track0 | 48 | -0.105 | Active-Only | Standard | vector_dyadic | -0.1821203 | -0.65522793 |
| SingleTooth_Track0 | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.11449742 | -0.89777237 |
| SingleTooth_Track0 | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.18986214 | -0.62561336 |
| SingleTooth_Track0 | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.031890889 | -0.92208489 |
| SingleTooth_Track0 | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -0.18075147 | -0.56655624 |
| SingleTooth_Track0 | 3 | -0.075 | Active-Only | Standard | vector_dyadic | -0.042890416 | -0.91245711 |
| SingleTooth_Track0 | 48 | -0.075 | Active-Only | Standard | vector_dyadic | -0.15352229 | -0.48704672 |
| SingleTooth_Track0 | 3 | -0.055 | Active-Only | Standard | vector_dyadic | -0.06934163 | -0.88344677 |
| SingleTooth_Track0 | 48 | -0.055 | Active-Only | Standard | vector_dyadic | -0.11741382 | -0.40174248 |

At z_tip = −0.100 µm:
- Aperture repulsion verified: True
- Pad attraction verified: True
- |pad force| / |aperture force|: 1.658222

## step2_n0_angular_sweep

Status: complete; records: 9.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 0 | -0.1 | Active-Only | Standard | vector_dyadic | 0.080965549 | -0.90231883 |
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.11449742 | -0.89777237 |
| Fractal_N0_SingleTrack | 6 | -0.1 | Active-Only | Standard | vector_dyadic | 0.080965549 | -0.90231883 |
| Fractal_N0_SingleTrack | 12 | -0.1 | Active-Only | Standard | vector_dyadic | 0.066978853 | -0.91408795 |
| Fractal_N0_SingleTrack | 18 | -0.1 | Active-Only | Standard | vector_dyadic | -0.024846304 | -0.89029755 |
| Fractal_N0_SingleTrack | 24 | -0.1 | Active-Only | Standard | vector_dyadic | -0.078127026 | -0.84765552 |
| Fractal_N0_SingleTrack | 30 | -0.1 | Active-Only | Standard | vector_dyadic | -0.093528003 | -0.6922396 |
| Fractal_N0_SingleTrack | 39 | -0.1 | Active-Only | Standard | vector_dyadic | -0.10167711 | -0.56545616 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.18986214 | -0.62561336 |

computed

-hbar*c*d(energy_hbar_c_per_um)/d(theta_rad); nonuniform second-order finite differences.

| θ (deg) | τz (pN µm) |
|---:|---:|
| 0 | -0.0054903656 |
| 3 | 3.2572798e-15 |
| 6 | 0.0030145016 |
| 12 | -0.001814633 |
| 18 | -0.010028093 |
| 24 | -0.029897202 |
| 30 | -0.038359407 |
| 39 | -0.0067048994 |
| 48 | 0.030920466 |

## step3_fractal_hierarchy

Status: complete; records: 12.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.11449742 | -0.89777237 |
| Fractal_N0_SingleTrack | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -0.086909188 | -0.91835624 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.18986214 | -0.62561336 |
| Fractal_N1_FundRing | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.044937972 | -0.54938839 |
| Fractal_N1_FundRing | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -0.076519991 | -0.67074735 |
| Fractal_N1_FundRing | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.089264928 | -0.54447851 |
| Fractal_N2_Cantor3Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.20436577 | -1.9108006 |
| Fractal_N2_Cantor3Track | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -0.21740052 | -2.3005124 |
| Fractal_N2_Cantor3Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.35024177 | -1.5886086 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.6249867 | -3.705027 |
| Fractal_N3_Cantor7Track | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -0.503802 | -4.6586262 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0186876 | -2.6645572 |

## step4_fractal_advantage

Status: complete; records: 10.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.20436577 | -1.9108006 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.35024177 | -1.5886086 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.20023035 | -1.8839852 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -0.34935961 | -1.4855483 |
| Ctrl_SingleWide | 3 | -0.1 | Active-Only | Standard | vector_dyadic | -0.0058041412 | -0.34095816 |
| Ctrl_SingleWide | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.04567156 | -0.39829285 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.16400668 | -1.8770908 |
| Ctrl_UniformPeriodic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.32625051 | -1.634502 |
| Ctrl_SizeMatched_Monotonic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.23438518 | -2.0864957 |
| Ctrl_SizeMatched_Monotonic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.39636994 | -1.6595062 |

## step5_best_active_configuration

Status: complete; records: 8.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Rot_C8_Compact_N2 | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.5755787 | -2.7753815 |
| Rot_C8_Compact_N2 | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.84243178 | -1.6736162 |
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.20436577 | -1.9108006 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.35024177 | -1.5886086 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.20023035 | -1.8839852 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -0.34935961 | -1.4855483 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.6249867 | -3.705027 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0186876 | -2.6645572 |

| Candidate | Repulsion (pN) | Attraction (pN) | Swing (pN) | Repulsion density (pN/µm²) |
|---|---:|---:|---:|---:|
| Rot_C8_Compact_N2 | 0.5755787 | -0.84243178 | 1.4180105 | 0.55101471 |
| Cantor_N2_FlatZ | 0.20436577 | -0.35024177 | 0.55460754 | 0.037547847 |
| Cantor_N2_HybridRZ | 0.20023035 | -0.34935961 | 0.54958996 | 0.036788052 |
| Fractal_N3_Cantor7Track | 0.6249867 | -1.0186876 | 1.6436743 | 0.07557054 |

- Maximum-swing champion: **Fractal_N3_Cantor7Track**
- Maximum-repulsion champion: **Fractal_N3_Cantor7Track**
- Compact N=2 champion: **Cantor_N2_FlatZ**

These are the specified 3° and 48° operating states, not a proof of globally maximal force over all angles.

## step6_monolithic_ultrahigh_validation

Status: complete; records: 16.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.20023035 | -1.8839852 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Full-Monolithic | Standard | vector_dyadic | 0.1623961 | -2.1425571 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -0.34935961 | -1.4855483 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Full-Monolithic | Standard | vector_dyadic | -0.38319118 | -1.7227758 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.6249867 | -3.705027 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Full-Monolithic | Standard | vector_dyadic | 0.58678751 | -3.9730927 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0186876 | -2.6645572 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Full-Monolithic | Standard | vector_dyadic | -1.0515405 | -2.903589 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.20023035 | -1.8839852 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -0.34935961 | -1.4855483 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | High | vector_dyadic | 0.41206121 | -2.8160072 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | High | vector_dyadic | -0.38708492 | -1.8013249 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Ultra_High | vector_dyadic | 0.48326401 | -3.3879945 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Ultra_High | vector_dyadic | -0.8572899 | -2.6584022 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | scalar_yukawa | 0.49693004 | -3.4435005 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | scalar_yukawa | -1.5216729 | -3.2086658 |

### Active-only versus full monolithic

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Active-only versus full monolithic | 0.03783425 | 0.18895362 | False |
| Cantor_N2_HybridRZ | 48 | Active-only versus full monolithic | 0.033831571 | 0.096838816 | True |
| Fractal_N3_Cantor7Track | 3 | Active-only versus full monolithic | 0.038199192 | 0.061120008 | True |
| Fractal_N3_Cantor7Track | 48 | Active-only versus full monolithic | 0.032852909 | 0.03225023 | True |

### Resolution convergence

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard -> High | 0.21183085 | 1.0579358 | False |
| Cantor_N2_HybridRZ | 48 | Standard -> High | 0.03772531 | 0.10798418 | True |
| Cantor_N2_HybridRZ | 3 | High -> Ultra_High | 0.071202806 | 0.17279667 | False |
| Cantor_N2_HybridRZ | 48 | High -> Ultra_High | 0.47020498 | 1.2147334 | False |

### Vector-dyadic versus scalar-Yukawa

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard | 0.29669968 | 0.5970653 | False |
| Cantor_N2_HybridRZ | 48 | Standard | 1.1723133 | 0.77041084 | False |

Agreement is tested, not assumed. Scalar Yukawa and vector dyadic models can differ physically; a failed cross-check is retained.

## 3D FDTD Meep Cross-Solver Verification & Yee-Grid Convergence (BigRed 200)

Suite status: **complete**; validated tasks: 12/12.

Only complete tasks with 0 < dt ≤ 0.0075 are admitted. Recorded cache versions must equal 6; missing version metadata is identified below.
Two-pass and stator-only forces are converted using `F * MEEP_FORCE_TO_SI_N * 1e12`; the four-pass `f_net_pN` is already in pN.

| Task | Design | θ (deg) | R | dt | Cache version | Status | F₂pass (pN) | Fstator-only (pN) | F₄pass net (pN) |
|---:|---|---:|---:|---:|---|---|---:|---:|---:|
| 1 | SingleTooth_Track0 | 3 | 50 | 0.006 | not recorded | complete | 0.3918759 | 0.47371419 | -0.081838289 |
| 2 | SingleTooth_Track0 | 48 | 50 | 0.006 | not recorded | complete | 4.7657683 | 22.860887 | -18.095119 |
| 3 | SingleTooth_Track0 | 3 | 50 | 0.006 | not recorded | complete | -0.15574774 | -0.03254325 | -0.12320449 |
| 4 | Ctrl_UniformPeriodic | 3 | 50 | 0.006 | not recorded | complete | 1.6388295 | 1.5948457 | 0.043983753 |
| 5 | Ctrl_UniformPeriodic | 48 | 50 | 0.006 | not recorded | complete | 5.6370602 | 62.398644 | -56.761583 |
| 6 | Cantor_N2_FlatZ | 3 | 50 | 0.006 | not recorded | complete | 2.5225305 | 1.2690929 | 1.2534376 |
| 7 | Cantor_N2_FlatZ | 48 | 50 | 0.006 | not recorded | complete | 5.0732259 | 60.555412 | -55.482186 |
| 8 | Cantor_N2_HybridRZ | 3 | 50 | 0.006 | not recorded | complete | 2.8004046 | 1.3759218 | 1.4244828 |
| 9 | Cantor_N2_HybridRZ | 48 | 50 | 0.006 | not recorded | complete | 60.445678 | 130.2905 | -69.84482 |
| 10 | Rot_C8_Compact_N2 | 3 | 50 | 0.006 | not recorded | complete | 1.9931384 | 2.0814716 | -0.088333194 |
| 11 | Cantor_N2_HybridRZ | 3 | 40 | 0.0075 | not recorded | complete | 4.0480617 | 0.62800176 | 3.42006 |
| 12 | Cantor_N2_HybridRZ | 3 | 60 | 0.005 | not recorded | complete | 2.5779337 | 1.7378797 | 0.84005408 |


### Richardson continuum extrapolation

Cantor_N2_HybridRZ at θ = 3°: Tasks 11, 8, 12, R = 40, 50, 60; dx = 1/R.
A three-point fixed-order p = 4 fit uses `F(R) = F_inf + C dx^4`.
**R = 40, 50, 60 → F_inf = +0.1535 pN (R² = 0.9984)**.

| Task | R | Four-pass force (pN) |
|---:|---:|---:|
| 11 | 40 | +3.42006 |
| 8 | 50 | +1.4244828 |
| 12 | 60 | +0.84005408 |

The asymptote and R² are recomputed from the supplied measurements, not imposed constants. R² describes this fixed-order fit, not an independent proof of fourth-order convergence.

### Corresponding 3D BEM results (Cantor_N2_HybridRZ, θ = 3°)

| BEM task | Model | Boundary | Tier | Fz (pN) |
|---|---|---|---|---:|
| step6_monolithic_ultrahigh_validation_0052 | vector_dyadic | Active-Only | Standard | +0.20023035 |
| step6_monolithic_ultrahigh_validation_0053 | vector_dyadic | Full-Monolithic | Standard | +0.1623961 |
| step6_monolithic_ultrahigh_validation_0060 | vector_dyadic | Active-Only | Standard | +0.20023035 |
| step6_monolithic_ultrahigh_validation_0062 | vector_dyadic | Active-Only | High | +0.41206121 |
| step6_monolithic_ultrahigh_validation_0064 | vector_dyadic | Active-Only | Ultra_High | +0.48326401 |
| step6_monolithic_ultrahigh_validation_0066 | scalar_yukawa | Active-Only | Standard | +0.49693004 |

Meep and BEM are independent solver results. Differences in discretization and physical formulation are retained rather than forced into agreement.

## Artifacts

- `results/nature_6step_narrative_report.json`
- `results/nature_6step_narrative_data.csv`
- `results/macros_results.tex`
- `figures/fig_nature_6step_narrative.pdf`
- `figures/fig_nature_6step_narrative.png`
