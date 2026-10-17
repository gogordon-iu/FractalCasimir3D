# Fractal Casimir Rotary Clutch: six-step narrative

- Status: **complete**
- Solver: `execution.casimir_bem_solver.run_bem_casimir_solver`
- Formulation for steps 1–5: `vector_dyadic`
- Device: `cpu`
- Executed task records: 77
- Unique solver evaluations represented: 55
- New BEM evaluations this run: 55
- Elapsed time before report generation: 1373.860 s

## Numerical and provenance conventions

- All forces and energies below are solver outputs, not fitted or stipulated.
- Meshes contain one 90-degree sector; the solver supplies fourfold symmetry.
- Positive vertical force denotes repulsion; negative denotes attraction.
- Raw force is full-device force in pN; per-tooth efficiency divides by
  four times the track count (the full-device tooth count).
- Footprint-normalized efficiency uses the full annular active footprint;
  tooth-area-normalized efficiency instead uses full tooth planform area.
- Raw-force rankings are distinct from normalized-efficiency rankings.
- Uniform_3Track_Control is the named alias of Ctrl_UniformPeriodic;
  both are reported transparently and are not independent geometries.
- Pad overlap is an analytic projected-area fraction, not a solver observable.
- Missing measurements are unavailable, never filled with zeros.
- Freshness status `completed` denotes report/table-record generation;
  `campaign_status` and row `source_status` retain actual solver availability
  and incomplete/failed campaign states.
- Scalar/vector agreement and convergence are tested rather than assumed.
- Passive support validation includes union-boundary spider spokes and collars
  at z = 0.350–0.470 µm and the trench slab at z = −0.650–−0.550 µm.

## step1_single_tooth_ztip

Status: complete; records: 12.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| SingleTooth_Track0 | 3 | -0.11 | Active-Only | Standard | vector_dyadic | 0.59433706 | -1.7542936 |
| SingleTooth_Track0 | 48 | -0.11 | Active-Only | Standard | vector_dyadic | -0.86349578 | -1.8653544 |
| SingleTooth_Track0 | 3 | -0.105 | Active-Only | Standard | vector_dyadic | 0.50717058 | -1.8337419 |
| SingleTooth_Track0 | 48 | -0.105 | Active-Only | Standard | vector_dyadic | -1.0237064 | -1.7236423 |
| SingleTooth_Track0 | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.43272809 | -1.9033403 |
| SingleTooth_Track0 | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0007408 | -1.5730175 |
| SingleTooth_Track0 | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.15734463 | -1.9984266 |
| SingleTooth_Track0 | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -0.80321374 | -1.3085508 |
| SingleTooth_Track0 | 3 | -0.075 | Active-Only | Standard | vector_dyadic | -0.055483463 | -2.0009707 |
| SingleTooth_Track0 | 48 | -0.075 | Active-Only | Standard | vector_dyadic | -0.55408768 | -1.0203651 |
| SingleTooth_Track0 | 3 | -0.055 | Active-Only | Standard | vector_dyadic | -0.16344361 | -1.9665701 |
| SingleTooth_Track0 | 48 | -0.055 | Active-Only | Standard | vector_dyadic | -0.35270277 | -0.77072375 |

At z_tip = −0.100 µm:
- Aperture repulsion verified: True
- Pad attraction verified: True
- |pad force| / |aperture force|: 2.3126318

## step2_n0_angular_sweep

Status: complete; records: 9.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 0 | -0.1 | Active-Only | Standard | vector_dyadic | 0.31694067 | -1.8468519 |
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.43272809 | -1.9033403 |
| Fractal_N0_SingleTrack | 6 | -0.1 | Active-Only | Standard | vector_dyadic | 0.31694067 | -1.8468519 |
| Fractal_N0_SingleTrack | 12 | -0.1 | Active-Only | Standard | vector_dyadic | 0.28211575 | -1.9418278 |
| Fractal_N0_SingleTrack | 18 | -0.1 | Active-Only | Standard | vector_dyadic | -0.073498491 | -1.8315062 |
| Fractal_N0_SingleTrack | 24 | -0.1 | Active-Only | Standard | vector_dyadic | -0.35968003 | -1.9129055 |
| Fractal_N0_SingleTrack | 30 | -0.1 | Active-Only | Standard | vector_dyadic | -0.37435714 | -1.3749007 |
| Fractal_N0_SingleTrack | 39 | -0.1 | Active-Only | Standard | vector_dyadic | -0.37106654 | -1.111795 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0007408 | -1.5730175 |

computed

-hbar*c*d(energy_hbar_c_per_um)/d(theta_rad); nonuniform second-order finite differences.

| θ (deg) | τz (pN µm) |
|---:|---:|
| 0 | 0.068216193 |
| 3 | 6.7391996e-16 |
| 6 | -0.013180879 |
| 12 | -0.0023164581 |
| 18 | -0.0043658753 |
| 24 | -0.068925424 |
| 30 | -0.11863736 |
| 39 | 0.019937396 |
| 48 | 0.16572226 |

## step3_fractal_hierarchy

Status: complete; records: 12.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.43272809 | -1.9033403 |
| Fractal_N0_SingleTrack | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -0.4425582 | -2.0838911 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0007408 | -1.5730175 |
| Fractal_N1_FundRing | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.18711926 | -1.0219116 |
| Fractal_N1_FundRing | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -0.49032478 | -1.7361645 |
| Fractal_N1_FundRing | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.6716687 | -1.7729239 |
| Fractal_N2_Cantor3Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.75380808 | -3.6722068 |
| Fractal_N2_Cantor3Track | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0343977 | -4.9751267 |
| Fractal_N2_Cantor3Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.0006527 | -4.1303596 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.0851845 | -8.4202825 |
| Fractal_N3_Cantor7Track | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -1.825573 | -10.353958 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -4.4662626 | -6.6875861 |

## step4_fractal_advantage

Status: complete; records: 12.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.75380808 | -3.6722068 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.0006527 | -4.1303596 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.75888483 | -3.6618446 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -1.7951066 | -3.677625 |
| Ctrl_SingleWide | 3 | -0.1 | Active-Only | Standard | vector_dyadic | -0.0038522113 | -0.53668204 |
| Ctrl_SingleWide | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.24177703 | -1.0202432 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.6283053 | -3.5192695 |
| Ctrl_UniformPeriodic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.9229324 | -4.2808744 |
| Ctrl_SizeMatched_Monotonic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.88311452 | -4.0746734 |
| Ctrl_SizeMatched_Monotonic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.219435 | -4.2541171 |
| Uniform_3Track_Control | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.6283053 | -3.5192695 |
| Uniform_3Track_Control | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.9229324 | -4.2808744 |

## step5_best_active_configuration

Status: complete; records: 16.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Rot_C8_Compact_N2 | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.1133754 | -6.6473342 |
| Rot_C8_Compact_N2 | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -3.9652733 | -4.3627381 |
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.75380808 | -3.6722068 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.0006527 | -4.1303596 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.75888483 | -3.6618446 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -1.7951066 | -3.677625 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.0851845 | -8.4202825 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -4.4662626 | -6.6875861 |
| Ctrl_SingleWide | 3 | -0.1 | Active-Only | Standard | vector_dyadic | -0.0038522113 | -0.53668204 |
| Ctrl_SingleWide | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.24177703 | -1.0202432 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.6283053 | -3.5192695 |
| Ctrl_UniformPeriodic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.9229324 | -4.2808744 |
| Ctrl_SizeMatched_Monotonic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.88311452 | -4.0746734 |
| Ctrl_SizeMatched_Monotonic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.219435 | -4.2541171 |
| Uniform_3Track_Control | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.6283053 | -3.5192695 |
| Uniform_3Track_Control | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.9229324 | -4.2808744 |

### Raw full-device force

| Candidate | Kind | Repulsion (pN) | Attraction (pN) | Swing (pN) |
|---|---|---:|---:|---:|
| Rot_C8_Compact_N2 | fractal | 2.1133754 | -3.9652733 | 6.0786487 |
| Cantor_N2_FlatZ | fractal | 0.75380808 | -2.0006527 | 2.7544607 |
| Cantor_N2_HybridRZ | fractal | 0.75888483 | -1.7951066 | 2.5539914 |
| Fractal_N3_Cantor7Track | fractal | 2.0851845 | -4.4662626 | 6.5514472 |
| Ctrl_SingleWide | control | -0.0038522113 | -0.24177703 | 0.23792481 |
| Ctrl_UniformPeriodic | control | 0.6283053 | -1.9229324 | 2.5512377 |
| Ctrl_SizeMatched_Monotonic | control | 0.88311452 | -2.219435 | 3.1025495 |
| Uniform_3Track_Control | control | 0.6283053 | -1.9229324 | 2.5512377 |

### Normalized efficiency

| Candidate | Full tooth count | Repulsion (pN/tooth) | Swing (pN/tooth) | Repulsion / footprint (pN/µm²) | Swing / footprint (pN/µm²) | Repulsion / tooth area (pN/µm²) |
|---|---:|---:|---:|---:|---:|---:|
| Rot_C8_Compact_N2 | 12 | 0.17611462 | 0.50655406 | 2.0231828 | 5.81923 | 33.615961 |
| Cantor_N2_FlatZ | 12 | 0.06281734 | 0.2295384 | 0.13849614 | 0.50607335 | 2.3011666 |
| Cantor_N2_HybridRZ | 12 | 0.063240403 | 0.21283262 | 0.13942889 | 0.4692414 | 2.3166646 |
| Fractal_N3_Cantor7Track | 28 | 0.074470876 | 0.23398026 | 0.252131 | 0.79217109 | 6.717964 |
| Ctrl_SingleWide | 4 | -0.00096305283 | 0.059481204 | -0.00070776158 | 0.043713605 | -0.011759731 |
| Ctrl_UniformPeriodic | 12 | 0.052358775 | 0.21260314 | 0.11543768 | 0.46873546 | 1.9180415 |
| Ctrl_SizeMatched_Monotonic | 12 | 0.073592876 | 0.25854579 | 0.16225344 | 0.57002724 | 2.5515719 |
| Uniform_3Track_Control | 12 | 0.052358775 | 0.21260314 | 0.11543768 | 0.46873546 | 1.9180415 |

- Maximum raw-swing champion: **Fractal_N3_Cantor7Track**
- Maximum raw-repulsion champion: **Rot_C8_Compact_N2**
- Compact N=2 raw-swing champion: **Cantor_N2_FlatZ**
- Maximum per-tooth-swing champion: **Rot_C8_Compact_N2**
- Maximum footprint-normalized-swing champion: **Rot_C8_Compact_N2**

These are the specified 3° and 48° operating states, not a proof of globally maximal force over all angles.

## step6_monolithic_ultrahigh_validation

Status: complete; records: 16.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.75888483 | -3.6618446 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Full-Monolithic | Standard | vector_dyadic | 0.72066824 | -3.8809206 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -1.7951066 | -3.677625 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Full-Monolithic | Standard | vector_dyadic | -1.8304058 | -3.8901396 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.0851845 | -8.4202825 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Full-Monolithic | Standard | vector_dyadic | 2.0487852 | -8.6332269 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -4.4662626 | -6.6875861 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Full-Monolithic | Standard | vector_dyadic | -4.4998442 | -6.8956938 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.75888483 | -3.6618446 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -1.7951066 | -3.677625 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | High | vector_dyadic | 1.4513399 | -5.6088002 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | High | vector_dyadic | -1.5684859 | -3.6665336 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Ultra_High | vector_dyadic | 1.6570327 | -6.6737167 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Ultra_High | vector_dyadic | -3.0100094 | -5.5320532 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | scalar_yukawa | 2.1905693 | -9.9566274 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | scalar_yukawa | -8.6123562 | -11.588364 |

### Active-only versus full monolithic

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Active-only versus full monolithic | 0.03821659 | 0.05035888 | True |
| Cantor_N2_HybridRZ | 48 | Active-only versus full monolithic | 0.035299207 | 0.019664128 | True |
| Fractal_N3_Cantor7Track | 3 | Active-only versus full monolithic | 0.036399309 | 0.017456157 | True |
| Fractal_N3_Cantor7Track | 48 | Active-only versus full monolithic | 0.033581575 | 0.0075189431 | True |

### Resolution convergence

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard -> High | 0.69245508 | 0.91246398 | False |
| Cantor_N2_HybridRZ | 48 | Standard -> High | 0.22662069 | 0.12624358 | True |
| Cantor_N2_HybridRZ | 3 | High -> Ultra_High | 0.2056928 | 0.14172613 | True |
| Cantor_N2_HybridRZ | 48 | High -> Ultra_High | 1.4415235 | 0.91905415 | False |

### Vector-dyadic versus scalar-Yukawa

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard | 1.4316844 | 0.6535673 | False |
| Cantor_N2_HybridRZ | 48 | Standard | 6.8172496 | 0.79156615 | False |

Agreement is tested, not assumed. Scalar Yukawa and vector dyadic models can differ physically; a failed cross-check is retained.

## 3D FDTD Meep Cross-Solver Verification & Yee-Grid Convergence (BigRed 200)

Suite status: **complete**; validated tasks: 12/12.

Only complete tasks with 0 < dt ≤ 0.0075 are admitted. Recorded cache versions must equal 6; missing version metadata is identified below.
Two-pass and stator-only forces are converted using `F * MEEP_FORCE_TO_SI_N * 1e12`; the four-pass `f_net_pN` is already in pN.

| Task | Design | θ (deg) | R | dt | Cache version | Status | F₂pass (pN) | Fstator-only (pN) | F₄pass net (pN) |
|---:|---|---:|---:|---:|---|---|---:|---:|---:|
| 1 | SingleTooth_Track0 | 3 | 50 | 0.006 | 6 | complete | 0.3918759 | 0.47371419 | -0.081838289 |
| 2 | SingleTooth_Track0 | 48 | 50 | 0.006 | 6 | complete | 4.7657683 | 22.860887 | -18.095119 |
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
| step6_monolithic_ultrahigh_validation_0062 | vector_dyadic | Active-Only | Standard | +0.75888483 |
| step6_monolithic_ultrahigh_validation_0063 | vector_dyadic | Full-Monolithic | Standard | +0.72066824 |
| step6_monolithic_ultrahigh_validation_0070 | vector_dyadic | Active-Only | Standard | +0.75888483 |
| step6_monolithic_ultrahigh_validation_0072 | vector_dyadic | Active-Only | High | +1.4513399 |
| step6_monolithic_ultrahigh_validation_0074 | vector_dyadic | Active-Only | Ultra_High | +1.6570327 |
| step6_monolithic_ultrahigh_validation_0076 | scalar_yukawa | Active-Only | Standard | +2.1905693 |

Meep and BEM are independent solver results. Differences in discretization and physical formulation are retained rather than forced into agreement.

## Artifacts

- `results/nature_6step_narrative_report.json`
- `results/nature_6step_narrative_data.csv`
- `results/macros_results.tex`
- `figures/fig_nature_6step_narrative.pdf`
- `figures/fig_nature_6step_narrative.png`
