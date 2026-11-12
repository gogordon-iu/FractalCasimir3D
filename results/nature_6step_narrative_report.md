# Fractal Casimir Rotary Clutch: six-step narrative

- Status: **complete**
- Solver: `execution.casimir_bem_solver.run_bem_casimir_solver`
- Formulation for steps 1–5: `vector_dyadic`
- Device: `cpu`
- Executed task records: 96
- Unique solver evaluations represented: 65
- New BEM evaluations this run: 65
- Elapsed time before report generation: 13087.221 s

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
| SingleTooth_Track0 | 3 | -0.11 | Active-Only | Standard | vector_dyadic | 1.0290637 | -2.8490155 |
| SingleTooth_Track0 | 48 | -0.11 | Active-Only | Standard | vector_dyadic | -0.98998978 | -2.9977493 |
| SingleTooth_Track0 | 3 | -0.105 | Active-Only | Standard | vector_dyadic | 0.84478354 | -2.9923127 |
| SingleTooth_Track0 | 48 | -0.105 | Active-Only | Standard | vector_dyadic | -1.4102709 | -2.8082001 |
| SingleTooth_Track0 | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.70670029 | -3.115062 |
| SingleTooth_Track0 | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.717278 | -2.5577364 |
| SingleTooth_Track0 | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 0.35631227 | -3.2818964 |
| SingleTooth_Track0 | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -1.5932242 | -2.0140514 |
| SingleTooth_Track0 | 3 | -0.075 | Active-Only | Standard | vector_dyadic | 0.14470068 | -3.3909629 |
| SingleTooth_Track0 | 48 | -0.075 | Active-Only | Standard | vector_dyadic | -1.0083847 | -1.4553879 |
| SingleTooth_Track0 | 3 | -0.055 | Active-Only | Standard | vector_dyadic | -0.35963487 | -3.3694349 |
| SingleTooth_Track0 | 48 | -0.055 | Active-Only | Standard | vector_dyadic | -0.58543942 | -1.0448121 |

At z_tip = −0.100 µm:
- Aperture repulsion verified: True
- Pad attraction verified: True
- |pad force| / |aperture force|: 2.4299947

## step2_n0_angular_sweep

Status: complete; records: 9.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 0 | -0.1 | Active-Only | Standard | vector_dyadic | 0.74389255 | -3.1660151 |
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.70670029 | -3.115062 |
| Fractal_N0_SingleTrack | 6 | -0.1 | Active-Only | Standard | vector_dyadic | 0.74389255 | -3.1660151 |
| Fractal_N0_SingleTrack | 12 | -0.1 | Active-Only | Standard | vector_dyadic | 0.39141729 | -3.3955827 |
| Fractal_N0_SingleTrack | 18 | -0.1 | Active-Only | Standard | vector_dyadic | -0.81455151 | -3.6712728 |
| Fractal_N0_SingleTrack | 24 | -0.1 | Active-Only | Standard | vector_dyadic | -1.2529503 | -3.3680707 |
| Fractal_N0_SingleTrack | 30 | -0.1 | Active-Only | Standard | vector_dyadic | -1.747623 | -3.0623459 |
| Fractal_N0_SingleTrack | 39 | -0.1 | Active-Only | Standard | vector_dyadic | -2.0186219 | -2.7565738 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.717278 | -2.5577364 |

computed

-hbar*c*d(energy_hbar_c_per_um)/d(theta_rad); nonuniform second-order finite differences.

| θ (deg) | τz (pN µm) |
|---:|---:|
| 0 | -0.061531701 |
| 3 | -9.7718395e-15 |
| 6 | 0.04361299 |
| 12 | 0.076269544 |
| 18 | -0.0041529794 |
| 24 | -0.0919186 |
| 30 | -0.079996636 |
| 39 | -0.050781131 |
| 48 | -0.029258482 |

## step3_fractal_hierarchy

Status: complete; records: 12.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Fractal_N0_SingleTrack | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.70670029 | -3.115062 |
| Fractal_N0_SingleTrack | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -1.0605959 | -3.4977346 |
| Fractal_N0_SingleTrack | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -1.717278 | -2.5577364 |
| Fractal_N1_FundRing | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 0.34736479 | -1.7521548 |
| Fractal_N1_FundRing | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -0.92908748 | -2.875723 |
| Fractal_N1_FundRing | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.98382635 | -2.7099421 |
| Fractal_N2_Cantor3Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.4931604 | -6.5839937 |
| Fractal_N2_Cantor3Track | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -2.6185753 | -8.4588554 |
| Fractal_N2_Cantor3Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -3.1044589 | -6.3352354 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 3.1774326 | -11.906482 |
| Fractal_N3_Cantor7Track | 21 | -0.1 | Active-Only | Standard | vector_dyadic | -4.4912158 | -15.749178 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -14.038832 | -10.946363 |

## step4_fractal_advantage

Status: complete; records: 20.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.4931604 | -6.5839937 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -3.1044589 | -6.3352354 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 1.6570364 | -6.6737421 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -3.0100066 | -5.5320948 |
| Cantor_N2_TrueRZ | 3 | -0.0333333 | Active-Only | Standard | vector_dyadic | 1.5501886 | -6.5967176 |
| Cantor_N2_TrueRZ | 48 | -0.0333333 | Active-Only | Standard | vector_dyadic | -1.1293055 | -3.1264964 |
| Ctrl_SingleWide | 3 | -0.1 | Active-Only | Standard | vector_dyadic | -0.01645345 | -0.8875214 |
| Ctrl_SingleWide | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.42960515 | -1.8153993 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.1952357 | -5.7544187 |
| Ctrl_UniformPeriodic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.5407937 | -6.5733357 |
| Ctrl_SizeMatched_Monotonic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.546318 | -6.8839006 |
| Ctrl_SizeMatched_Monotonic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -3.3679465 | -6.6784157 |
| Uniform_3Track_Control | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.1952357 | -5.7544187 |
| Uniform_3Track_Control | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.5407937 | -6.5733357 |
| Ctrl_N3_Uniform7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.0553136 | -8.9753489 |
| Ctrl_N3_Uniform7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -12.30829 | -12.394191 |
| Ctrl_N3_Monotonic7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 4.385393 | -14.265908 |
| Ctrl_N3_Monotonic7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -12.250339 | -10.603697 |
| Ctrl_N3_Shuffled7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.7670882 | -10.824395 |
| Ctrl_N3_Shuffled7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -14.62108 | -10.92363 |

## step5_best_active_configuration

Status: complete; records: 24.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Rot_C8_Compact_N2 | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.4782467 | -7.0147063 |
| Rot_C8_Compact_N2 | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -4.2918779 | -5.8599139 |
| Cantor_N2_FlatZ | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.4931604 | -6.5839937 |
| Cantor_N2_FlatZ | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -3.1044589 | -6.3352354 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 1.6570364 | -6.6737421 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -3.0100066 | -5.5320948 |
| Cantor_N2_TrueRZ | 3 | -0.0333333 | Active-Only | Standard | vector_dyadic | 1.5501886 | -6.5967176 |
| Cantor_N2_TrueRZ | 48 | -0.0333333 | Active-Only | Standard | vector_dyadic | -1.1293055 | -3.1264964 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 3.1774326 | -11.906482 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -14.038832 | -10.946363 |
| Ctrl_SingleWide | 3 | -0.1 | Active-Only | Standard | vector_dyadic | -0.01645345 | -0.8875214 |
| Ctrl_SingleWide | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -0.42960515 | -1.8153993 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.1952357 | -5.7544187 |
| Ctrl_UniformPeriodic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.5407937 | -6.5733357 |
| Ctrl_SizeMatched_Monotonic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.546318 | -6.8839006 |
| Ctrl_SizeMatched_Monotonic | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -3.3679465 | -6.6784157 |
| Uniform_3Track_Control | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.1952357 | -5.7544187 |
| Uniform_3Track_Control | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -2.5407937 | -6.5733357 |
| Ctrl_N3_Uniform7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.0553136 | -8.9753489 |
| Ctrl_N3_Uniform7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -12.30829 | -12.394191 |
| Ctrl_N3_Monotonic7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 4.385393 | -14.265908 |
| Ctrl_N3_Monotonic7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -12.250339 | -10.603697 |
| Ctrl_N3_Shuffled7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 2.7670882 | -10.824395 |
| Ctrl_N3_Shuffled7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -14.62108 | -10.92363 |

### Raw full-device force

| Candidate | Kind | Repulsion (pN) | Attraction (pN) | Swing (pN) |
|---|---|---:|---:|---:|
| Rot_C8_Compact_N2 | fractal | 1.4782467 | -4.2918779 | 5.7701246 |
| Cantor_N2_FlatZ | fractal | 1.4931604 | -3.1044589 | 4.5976193 |
| Cantor_N2_HybridRZ | fractal | 1.6570364 | -3.0100066 | 4.667043 |
| Cantor_N2_TrueRZ | fractal | 1.5501886 | -1.1293055 | 2.6794941 |
| Fractal_N3_Cantor7Track | fractal | 3.1774326 | -14.038832 | 17.216264 |
| Ctrl_SingleWide | control | -0.01645345 | -0.42960515 | 0.4131517 |
| Ctrl_UniformPeriodic | control | 1.1952357 | -2.5407937 | 3.7360294 |
| Ctrl_SizeMatched_Monotonic | control | 1.546318 | -3.3679465 | 4.9142644 |
| Uniform_3Track_Control | control | 1.1952357 | -2.5407937 | 3.7360294 |
| Ctrl_N3_Uniform7Track | control | 2.0553136 | -12.30829 | 14.363604 |
| Ctrl_N3_Monotonic7Track | control | 4.385393 | -12.250339 | 16.635732 |
| Ctrl_N3_Shuffled7Track | control | 2.7670882 | -14.62108 | 17.388168 |

### Normalized efficiency

| Candidate | Full tooth count | Repulsion (pN/tooth) | Swing (pN/tooth) | Repulsion / footprint (pN/µm²) | Swing / footprint (pN/µm²) | Repulsion / tooth area (pN/µm²) |
|---|---:|---:|---:|---:|---:|---:|
| Rot_C8_Compact_N2 | 12 | 0.12318723 | 0.48084372 | 0.61109163 | 2.3853087 | 14.666199 |
| Cantor_N2_FlatZ | 12 | 0.12443003 | 0.38313494 | 0.27433634 | 0.84471439 | 4.5582038 |
| Cantor_N2_HybridRZ | 12 | 0.13808637 | 0.38892025 | 0.30444506 | 0.85746951 | 5.0584718 |
| Cantor_N2_TrueRZ | 12 | 0.12918239 | 0.22329118 | 0.28481406 | 0.49229984 | 4.7322952 |
| Fractal_N3_Cantor7Track | 28 | 0.11347974 | 0.61486659 | 0.38420065 | 2.0817121 | 10.236925 |
| Ctrl_SingleWide | 4 | -0.0041133625 | 0.10328792 | -0.0030229701 | 0.075907803 | -0.050227811 |
| Ctrl_UniformPeriodic | 12 | 0.099602978 | 0.31133578 | 0.21959905 | 0.68641564 | 3.6487226 |
| Ctrl_SizeMatched_Monotonic | 12 | 0.12885983 | 0.40952204 | 0.28410291 | 0.90289117 | 4.4677575 |
| Uniform_3Track_Control | 12 | 0.099602978 | 0.31133578 | 0.21959905 | 0.68641564 | 3.6487226 |
| Ctrl_N3_Uniform7Track | 28 | 0.073404055 | 0.51298586 | 0.24851914 | 1.7367814 | 6.621727 |
| Ctrl_N3_Monotonic7Track | 28 | 0.15662118 | 0.59413329 | 0.53026171 | 2.0115168 | 13.070355 |
| Ctrl_N3_Shuffled7Track | 28 | 0.098824577 | 0.62100599 | 0.33458367 | 2.1024979 | 9.1621864 |

- Maximum raw-swing champion: **Ctrl_N3_Shuffled7Track**
- Maximum raw-repulsion champion: **Ctrl_N3_Monotonic7Track**
- Compact N=2 raw-swing champion: **Cantor_N2_HybridRZ**
- Maximum per-tooth-swing champion: **Ctrl_N3_Shuffled7Track**
- Maximum footprint-normalized-swing champion: **Rot_C8_Compact_N2**

These are the specified 3° and 48° operating states, not a proof of globally maximal force over all angles.

## step6_monolithic_ultrahigh_validation

Status: complete; records: 19.

| Design | θ (deg) | z tip (µm) | Boundary | Tier | Model | Fz (pN) | E (ℏc/µm) |
|---|---:|---:|---|---|---|---:|---:|
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 1.6570364 | -6.6737421 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Full-Monolithic | Standard | vector_dyadic | 1.6023852 | -6.9683067 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -3.0100066 | -5.5320948 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Full-Monolithic | Standard | vector_dyadic | -3.0572862 | -5.7865527 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 3.1774326 | -11.906482 |
| Fractal_N3_Cantor7Track | 3 | -0.1 | Full-Monolithic | Standard | vector_dyadic | 3.124676 | -12.219966 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Active-Only | Standard | vector_dyadic | -14.038832 | -10.946363 |
| Fractal_N3_Cantor7Track | 48 | -0.1 | Full-Monolithic | Standard | vector_dyadic | -14.085617 | -11.208606 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | vector_dyadic | 1.6570364 | -6.6737421 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | vector_dyadic | -3.0100066 | -5.5320948 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | High | vector_dyadic | 2.5917125 | -9.6131111 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | High | vector_dyadic | -6.8871974 | -8.8430508 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Ultra_High | vector_dyadic | 4.7386824 | -15.354618 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Ultra_High | vector_dyadic | -16.542594 | -15.747897 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Standard | vector_dyadic | 1.1952357 | -5.7544187 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | High | vector_dyadic | 1.7843916 | -8.2795918 |
| Ctrl_UniformPeriodic | 3 | -0.1 | Active-Only | Ultra_High | vector_dyadic | 2.956353 | -12.416958 |
| Cantor_N2_HybridRZ | 3 | -0.09 | Active-Only | Standard | scalar_yukawa | 3.9888701 | -15.418194 |
| Cantor_N2_HybridRZ | 48 | -0.09 | Active-Only | Standard | scalar_yukawa | -14.900166 | -16.77503 |

### Active-only versus full monolithic

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Active-only versus full monolithic | 0.054651196 | 0.032981289 | True |
| Cantor_N2_HybridRZ | 48 | Active-only versus full monolithic | 0.047279577 | 0.015707466 | True |
| Fractal_N3_Cantor7Track | 3 | Active-only versus full monolithic | 0.052756583 | 0.016603525 | True |
| Fractal_N3_Cantor7Track | 48 | Active-only versus full monolithic | 0.046784786 | 0.003332527 | True |

### Resolution convergence

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard -> High | 0.9346761 | 0.56406492 | False |
| Cantor_N2_HybridRZ | 48 | Standard -> High | 3.8771908 | 1.2881004 | False |
| Cantor_N2_HybridRZ | 3 | High -> Ultra_High | 2.1469699 | 0.82839817 | False |
| Cantor_N2_HybridRZ | 48 | High -> Ultra_High | 9.6553966 | 1.4019341 | False |
| Ctrl_UniformPeriodic | 3 | Standard -> High | 0.58915587 | 0.49292023 | False |
| Ctrl_UniformPeriodic | 3 | High -> Ultra_High | 1.1719614 | 0.65678488 | False |

### Vector-dyadic versus scalar-Yukawa

| Design | θ (deg) | Comparison | Absolute difference (pN) | Relative difference | Within tolerance |
|---|---:|---|---:|---:|---|
| Cantor_N2_HybridRZ | 3 | Standard | 2.3318337 | 0.58458502 | False |
| Cantor_N2_HybridRZ | 48 | Standard | 11.890159 | 0.79798838 | False |

Agreement is tested, not assumed. Scalar Yukawa and vector dyadic models can differ physically; a failed cross-check is retained.

## 3D FDTD Meep Cross-Solver Verification & Yee-Grid Convergence (BigRed 200)

Suite status: **complete**; validated tasks: 12/12.

Only complete tasks with 0 < dt ≤ 0.0075 are admitted. Recorded cache versions must equal 6; missing version metadata is identified below.
Two-pass and stator-only forces are converted using `F * MEEP_FORCE_TO_SI_N * 1e12`; the four-pass `f_net_pN` is already in pN.

| Task | Design | θ (deg) | R | dt | Cache version | Status | F₂pass (pN) | Fstator-only (pN) | F₄pass net (pN) |
|---:|---|---:|---:|---:|---|---|---:|---:|---:|
| 1 | SingleTooth_Track0 | 3 | 50 | 0.006 | 6 | complete | 0.3918759 | 0.47371419 | -0.081838289 |
| 2 | SingleTooth_Track0 | 48 | 50 | 0.006 | 6 | complete | 4.7657683 | 22.860887 | -18.095119 |
| 3 | SingleTooth_Track0 | 3 | 50 | 0.006 | 6 | complete | -0.15574774 | -0.03254325 | -0.12320449 |
| 4 | Ctrl_UniformPeriodic | 3 | 50 | 0.006 | 6 | complete | 1.6388295 | 1.5948457 | 0.043983753 |
| 5 | Ctrl_UniformPeriodic | 48 | 50 | 0.006 | 6 | complete | 5.6370602 | 62.398644 | -56.761583 |
| 6 | Cantor_N2_FlatZ | 3 | 50 | 0.006 | 6 | complete | 2.5225305 | 1.2690929 | 1.2534376 |
| 7 | Cantor_N2_FlatZ | 48 | 50 | 0.006 | 6 | complete | 5.0732259 | 60.555412 | -55.482186 |
| 8 | Cantor_N2_HybridRZ | 3 | 50 | 0.006 | 6 | complete | 2.8004046 | 1.3759218 | 1.4244828 |
| 9 | Cantor_N2_HybridRZ | 48 | 50 | 0.006 | 6 | complete | 60.445678 | 130.2905 | -69.84482 |
| 10 | Rot_C8_Compact_N2 | 3 | 50 | 0.006 | 6 | complete | 1.9931384 | 2.0814716 | -0.088333194 |
| 11 | Cantor_N2_HybridRZ | 3 | 40 | 0.0075 | 6 | complete | 4.0480617 | 0.62800176 | 3.42006 |
| 12 | Cantor_N2_HybridRZ | 3 | 60 | 0.005 | 6 | complete | 2.5779337 | 1.7378797 | 0.84005408 |


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

Not measured in this campaign.

Meep and BEM are independent solver results. Differences in discretization and physical formulation are retained rather than forced into agreement.

## Artifacts

- `results/nature_6step_narrative_report.json`
- `results/nature_6step_narrative_data.csv`
- `results/macros_results.tex`
- `figures/fig_nature_6step_narrative.pdf`
- `figures/fig_nature_6step_narrative.png`
