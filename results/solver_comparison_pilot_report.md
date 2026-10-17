# Scoped Pilot Concentric Casimir Clutch: Solver Comparison

Generated: 2026-10-14T20:14:25.749642+00:00

## Execution scope

The original pilot configurations are used without architectural replacement: task 1 at 0° (Disengaged), and task 2 at 45° (Engaged), both at z_tip=+15 nm. Primary results use the 3D vector electromagnetic dyadic BEM (vector_dyadic); scalar_yukawa is run separately at the same pilot heights. The BEM discretization is n_r=2, n_phi_tooth=3, n_phi_bridge=3, n_z=2.

**Micro-probe:** False. A positive max-steps produces diagnostic, potentially unconverged forces and must not be interpreted as a publication-ready physical result.

## Data-freshness guard

**No fresh post-bugfix 4-pass Meep data on disk yet; awaiting BigRed 200 Job completion**

Latest BUG_LOG fix: 2026-10-14T00:00:00+00:00. Accepted files require cache version >=5, co-located non-null F_stator/F_vac, mtime strictly after the fix, and finite F_net, f_net_pN, f_net_fN. Stale two-pass values are neither plotted nor used for speedup estimates.

Resolution and moment count are checked when reported; absent values remain unverified, never inferred from filenames. Cache version, subtraction fields, mtime, and all three net-force fields are mandatory.

| State | Vector BEM signed force (pN) | Local Lifshitz-PFA (pN) | Fresh Meep (pN) | BEM wall time (s) |
|---|---:|---:|---:|---:|
| 0° | -0.5340294 | 0 | Unavailable | 43.49864 |
| 45° | -1.939064 | -60.71343 | Unavailable | 45.884 |

## Vector Dyadic BEM vs Scalar Yukawa BEM & z_tip Repulsion Scan at 0°

The vector_dyadic formulation uses the upgraded 3D vector electromagnetic dyadic solver; scalar_yukawa is a scalar-kernel comparison, not an equivalent electromagnetic theory. All entries below are actual solver outputs, not inferred signs or reconstructed forces.

| State at z_tip=+15 nm | Vector Dyadic BEM (pN) | Scalar Yukawa BEM (pN) |
|---|---:|---:|
| 0° | -0.5340294 | -0.614915 |
| 45° | -1.939064 | -2.54507 |

The θ=0° height scan uses n_xi=12 and max_steps=0. Positive F_z denotes upward repulsion; negative F_z denotes attraction. Missing components remain unavailable. A lateral/edge component may be the explicitly labelled total-minus-bottom residual recorded with each task.

| z_tip_nm | Signed f_net (pN) | Signed f_net (fN) | Bottom face (fN) | Lateral/Edge (fN) | Regime |
|---:|---:|---:|---:|---:|---|
| -300 | 0.5196386 | 519.6386 | 13.17566 | 506.4629 | Repulsive |
| -250 | 0.5766639 | 576.6639 | 18.4544 | 558.2095 | Repulsive |
| -200 | 0.0990537 | 99.0537 | 19.51762 | 79.53608 | Repulsive |
| -175 | -0.405311 | -405.311 | 13.43389 | -418.7449 | Attractive |
| -150 | -0.1845383 | -184.5383 | 16.86531 | -201.4036 | Attractive |
| -125 | -0.05446541 | -54.46541 | 38.07216 | -92.53757 | Attractive |
| -100 | 0.1382533 | 138.2533 | 50.48279 | 87.77047 | Repulsive |
| -50 | -0.7603297 | -760.3297 | 46.39266 | -806.7224 | Attractive |
| 0 | -0.5719225 | -571.9225 | -95.91532 | -476.0072 | Attractive |
| 15 | -0.5339366 | -533.9366 | -129.7138 | -404.2228 | Attractive |
| 50 | -0.433232 | -433.232 | -167.3863 | -265.8458 | Attractive |

**Repulsion detected:** True. The largest sampled signed vector force is 0.5766639 pN (576.6639 fN) at z_tip=-250 nm. If every sample is attractive, this maximum is not a repulsive peak.

The first adjacent opposite-sign bracket in ascending height gives a linearly interpolated zero-force height z_tip_eq=-195.0902 nm. No sign change yields an unavailable equilibrium. This is a sampled zero-force estimate, not proof of stable levitation or a converged root.

A separate scalar solve at the same sampled maximum height gives 0.6628411 pN (662.8411 fN), using the same scan n_xi and max_steps as the vector scan. The figure uses the measured maximum rather than assuming that the peak occurs at −250 nm.

At z_tip=+15 nm (>0), the rotor tips are above the stator top, so a horizontal plane can separate the bodies. The Kenneth–Klich attraction theorem applies to reflection-related bodies across a separating plane under its material assumptions; a separating plane alone does not prove attraction for arbitrary, non-mirror-related rotor/stator shapes. It must therefore not be used as a universal sign constraint on this clutch.

When z_tip dips below roughly −160 nm inside the open 30° slot aperture, the intended geometry enters a deeply interdigitated regime. The stator z-bounds are [−175 nm, 0 nm]; overlapping vertical extents remove the simple horizontal separating-plane argument. Lateral and edge coupling can then support a positive vertical force F_z>0 without contradicting the Kenneth–Klich theorem. Repulsion is asserted only where the computed scan is positive, not merely because the tip is below −160 nm. Collision freedom and spatial/frequency convergence still require independent verification, especially for a max-steps micro-probe.

The dedicated figure fig_clutch_ztip_repulsion_scan shows signed total, bottom-face and lateral/edge forces, sign-regime shading, the +15 nm pilot marker, any interpolated equilibrium, and the stator z-bounds. Its second panel compares vector and scalar forces at both pilot states and at the sampled θ=0° maximum.

## Physical interpretation

At 45°, the intended 4×3=12 rotor teeth align with the gold landing pad; the nominal tip gap is 15 nm and pad thickness is 150 nm. At 0°, the teeth face the open 30° slot aperture. Exact polar overlap areas are computed from the original configuration's radial track bounds and periodic angular intervals, rather than triangulated facet areas or guessed tooth dimensions. The stator bridge spans 30°–90° in each sector, and the rotor tooth spans 15°+theta±7.5°, modulo 90°. The detailed patch audit is included in the JSON report.

The local reference integrates the exact vacuum/Gold Drude Lifshitz TM and TE reflection integrand over imaginary angular frequency and transverse wavevector. The q=sqrt(kappa²+k_perp²) change of variables retains the exact Jacobian. MaterialModel.from_parameters supplies the dielectric response; no independently fitted or ideal-metal dielectric is substituted.

This is a zero-temperature, semi-infinite-medium local reference. A finite 150 nm film, thermal Matsubara corrections, roughness, spatial dispersion, and multilayer support response are not silently folded into it. An open slot without an underlying surface contributes zero local PFA force, but can still have a nonzero 3D electromagnetic force through nearby edges. The PFA reference here is only for the original +15 nm pilot heights, not for the interdigitated height scan.

A BEM–PFA difference is a total three-dimensional/local-model correction, **not automatically an edge-diffraction measurement**. Edge fractions are reported only from solver components, or a clearly labelled total-minus-bottom residual. Signed component magnitudes do not generally add to the magnitude of the signed total.

Clutch on/off contrast |F_engaged/F_disengaged|: **3.631007**. A zero off-state denominator is represented as unavailable, not infinity.

## Numerical convergence and geometry

The production sweep uses vector_dyadic with n_xi=8,16,24 for both states at +15 nm with fixed spatial discretization. Frequency convergence is not spatial-panel convergence and does not establish a complete error bound. Relative changes use the finest sweep force as denominator and are unavailable for a zero denominator. The lower-node height scan and scalar comparisons are not independently convergence-certified by this sweep.

| State | n_xi | Signed force (pN) | Relative difference from n_xi=24 |
|---|---:|---:|---:|
| 0° | 8 | -0.5100367 | 0.04502896 |
| 0° | 16 | -0.5340294 | 0.0001059721 |
| 0° | 24 | -0.534086 | 0 |
| 45° | 8 | -1.836253 | 0.05333001 |
| 45° | 16 | -1.939064 | 0.0003262971 |
| 45° | 24 | -1.939697 | 0 |

Both in-memory and serialized Gmsh meshes are checked for exactly two incident faces per edge, consistent winding, nondegenerate and unique triangles, and connected circular vertex links. Successful exports have 100% manifold watertightness. The .scuffgeo file references both meshes. Watertightness alone does not certify collision freedom or mesh convergence.

## Computational comparison

The supplied Meep memory baseline is 481.27 decimal GB (448.218 GiB), not 481.27 GiB. Meep uses a 3D Yee volume grid at R=80; BEM discretizes 2D object surfaces. BEM may nevertheless require dense matrices with quadratic storage and higher-order solve cost. Solver-reported DoF are preferred; n_panels_total is used as a panel-count proxy when no explicit BEM DoF is reported. When no fresh Meep file is available, the reference proxy is 3.8×3.8×1.43×80³ = 1.057239e+07 Yee grid cells, not an independently measured unknown count.

| State | BEM memory (GiB) | Memory reduction | Runtime speedup | Edge fraction |
|---|---:|---:|---:|---:|
| 0° | 0.08358192 | 5362.614 | Unavailable | 0.7572831 |

Memory measurement for 0°: solver-estimated dense allocation bytes converted to GiB.
| 45° | 0.08358192 | 5362.614 | Unavailable | 0.4015414 |

Memory measurement for 45°: solver-estimated dense allocation bytes converted to GiB.

Runtime speedups use only fresh Meep runtimes divided by measured BEM wall time. Cluster/accelerator hardware differences, allocation scope, parallelism, cache reuse, and the four-pass workload prevent interpreting these as hardware-normalized algorithmic speedups.

## Figure and provenance

Panel (a) of the solver comparison uses solver per-xi BEM integrands converted with MEEP_FORCE_TO_SI=3.16152649e-14, or explicitly unit-labelled BEM spectra when available; otherwise it explicitly displays local Lifshitz-PFA reference spectra. Missing polarization-resolved BEM data are never reconstructed or falsely labelled. Zero-frequency nodes are omitted from the logarithmic axis. Panel (b) omits unreported BEM components and labels missing fresh Meep runs as Pending Cluster Run. Panel (c) distinguishes skipped micro-probe convergence. Panel (d) labels panel/Yee-cell proxies and documents the memory estimate or fallback.

Configuration, BUG_LOG, accepted Meep files, exported meshes, and figures carry SHA-256 provenance. Height overrides and formulation are recorded per solve without altering the original configuration files. Metrics, LaTeX macros, and plot sidecars for both publication figures are generated by metrics_logger using its native schemas, without custom wrappers or appended macro definitions.

## Audit details

```json
{
  "configuration_provenance": [
    {
      "path": "C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\sweep_configs_clutch_pilot\\config_001.json",
      "sha256": "75ea2e0949866d2773992ea1349740c5e105d317eecee12166d4a722e0492098",
      "config": {
        "H_teeth_um": 0.25,
        "L_domain_um": 3.0,
        "N_fractal": 2,
        "R_max_um": 1.35,
        "R_min_um": 0.3,
        "T_run": 3.0,
        "aperture_arc_deg": 30.0,
        "bridge_arc_deg": 60.0,
        "configurations": [
          "both",
          "rotor",
          "stator",
          "vac"
        ],
        "description": "Tooth centered in the 30 deg aperture.",
        "expected_regime": "REPULSIVE",
        "geometry": [
          {
            "W_slot": 0.35,
            "level": 1,
            "r_center": 0.825,
            "r_inner": 0.65,
            "r_outer": 1.0,
            "r_tooth_in": 0.78475,
            "r_tooth_out": 0.86525,
            "w_tooth": 0.0805
          },
          {
            "W_slot": 0.11666666666666664,
            "level": 2,
            "r_center": 0.475,
            "r_inner": 0.4166666666666667,
            "r_outer": 0.5333333333333333,
            "r_tooth_in": 0.4615833333333333,
            "r_tooth_out": 0.48841666666666667,
            "w_tooth": 0.026833333333333327
          },
          {
            "W_slot": 0.1166666666666667,
            "level": 2,
            "r_center": 1.175,
            "r_inner": 1.1166666666666667,
            "r_outer": 1.2333333333333334,
            "r_tooth_in": 1.1615833333333334,
            "r_tooth_out": 1.1884166666666667,
            "w_tooth": 0.02683333333333334
          }
        ],
        "inclusion_exclusion_passes": 4,
        "material": "Gold",
        "nmax": 1,
        "num_sectors": 4,
        "num_tracks": 3,
        "provenance": {
          "T_run_function": "execution.clutch_geometry_redesign.compute_dynamic_Trun",
          "T_run_inputs": {
            "z_tip_um": 0.015
          },
          "T_run_units": "Native units returned by compute_dynamic_Trun; no conversion applied.",
          "dynamic_Trun_diagnostics": {
            "Sigma": 33.333333333333336,
            "T_run": 3.0,
            "achieved_suppression": 1.3838965267367376e-87,
            "clipping": "min_floor",
            "d_eff_um": 0.015,
            "equation": "Sigma = 0.5/d_eff_um; T_ideal = -ln(target_suppression)/(2*Sigma); T_run = clip(safety_factor*T_ideal, min_floor, max_ceil)",
            "ideal_T_run": 1.7269388197455342,
            "log_achieved_suppression": -200.0,
            "log_target_suppression": -115.12925464970229,
            "max_ceil": 12.0,
            "min_floor": 3.0,
            "safety_factor": 1.5,
            "safety_scaled_T_run": 2.5904082296183013,
            "target_met": true,
            "target_suppression": 1e-50,
            "units": "d_eff_um: micrometres; T_run: normalized Wick-damping time"
          },
          "generated_at_utc": "2026-10-14T17:51:33.762912+00:00",
          "generator": "execution/generate_scoped_pilot_configs.py",
          "geometry_function": "execution.clutch_geometry_redesign.get_scoped_clutch_elements",
          "metrics_logger_available": true,
          "regime_note": "Expected regimes are pilot hypotheses, not simulation results."
        },
        "resolution": 80,
        "schema_version": 1,
        "suite_name": "Scoped Pilot Concentric Casimir Clutch",
        "t_landing_pad_um": 0.15,
        "t_membrane_um": 0.025,
        "task_id": 1,
        "task_name": "Disengaged",
        "theta_deg": 0.0,
        "tooth_arc_deg": 15.0,
        "z_tip_nm": 15.0,
        "z_tip_um": 0.015
      }
    },
    {
      "path": "C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\sweep_configs_clutch_pilot\\config_002.json",
      "sha256": "2401bbf8f97f2c8fb67a54ca322cdd92534a4e126d0864eff51dc5ed76e50410",
      "config": {
        "H_teeth_um": 0.25,
        "L_domain_um": 3.0,
        "N_fractal": 2,
        "R_max_um": 1.35,
        "R_min_um": 0.3,
        "T_run": 3.0,
        "aperture_arc_deg": 30.0,
        "bridge_arc_deg": 60.0,
        "configurations": [
          "both",
          "rotor",
          "stator",
          "vac"
        ],
        "description": "Tooth centered on the 60 deg reinforced 150 nm landing pad.",
        "expected_regime": "ATTRACTIVE",
        "geometry": [
          {
            "W_slot": 0.35,
            "level": 1,
            "r_center": 0.825,
            "r_inner": 0.65,
            "r_outer": 1.0,
            "r_tooth_in": 0.78475,
            "r_tooth_out": 0.86525,
            "w_tooth": 0.0805
          },
          {
            "W_slot": 0.11666666666666664,
            "level": 2,
            "r_center": 0.475,
            "r_inner": 0.4166666666666667,
            "r_outer": 0.5333333333333333,
            "r_tooth_in": 0.4615833333333333,
            "r_tooth_out": 0.48841666666666667,
            "w_tooth": 0.026833333333333327
          },
          {
            "W_slot": 0.1166666666666667,
            "level": 2,
            "r_center": 1.175,
            "r_inner": 1.1166666666666667,
            "r_outer": 1.2333333333333334,
            "r_tooth_in": 1.1615833333333334,
            "r_tooth_out": 1.1884166666666667,
            "w_tooth": 0.02683333333333334
          }
        ],
        "inclusion_exclusion_passes": 4,
        "material": "Gold",
        "nmax": 1,
        "num_sectors": 4,
        "num_tracks": 3,
        "provenance": {
          "T_run_function": "execution.clutch_geometry_redesign.compute_dynamic_Trun",
          "T_run_inputs": {
            "z_tip_um": 0.015
          },
          "T_run_units": "Native units returned by compute_dynamic_Trun; no conversion applied.",
          "dynamic_Trun_diagnostics": {
            "Sigma": 33.333333333333336,
            "T_run": 3.0,
            "achieved_suppression": 1.3838965267367376e-87,
            "clipping": "min_floor",
            "d_eff_um": 0.015,
            "equation": "Sigma = 0.5/d_eff_um; T_ideal = -ln(target_suppression)/(2*Sigma); T_run = clip(safety_factor*T_ideal, min_floor, max_ceil)",
            "ideal_T_run": 1.7269388197455342,
            "log_achieved_suppression": -200.0,
            "log_target_suppression": -115.12925464970229,
            "max_ceil": 12.0,
            "min_floor": 3.0,
            "safety_factor": 1.5,
            "safety_scaled_T_run": 2.5904082296183013,
            "target_met": true,
            "target_suppression": 1e-50,
            "units": "d_eff_um: micrometres; T_run: normalized Wick-damping time"
          },
          "generated_at_utc": "2026-10-14T17:51:33.762912+00:00",
          "generator": "execution/generate_scoped_pilot_configs.py",
          "geometry_function": "execution.clutch_geometry_redesign.get_scoped_clutch_elements",
          "metrics_logger_available": true,
          "regime_note": "Expected regimes are pilot hypotheses, not simulation results."
        },
        "resolution": 80,
        "schema_version": 1,
        "suite_name": "Scoped Pilot Concentric Casimir Clutch",
        "t_landing_pad_um": 0.15,
        "t_membrane_um": 0.025,
        "task_id": 2,
        "task_name": "Engaged",
        "theta_deg": 45.0,
        "tooth_arc_deg": 15.0,
        "z_tip_nm": 15.0,
        "z_tip_um": 0.015
      }
    }
  ],
  "freshness_candidates": {
    "1": [
      {
        "path": "results_clutch_pilot\\task_001_N2_th_0deg.json",
        "exists": false,
        "fresh": false,
        "reasons": [
          "file absent"
        ]
      },
      {
        "path": "results_clutch_pilot\\progress_task_001.json",
        "exists": false,
        "fresh": false,
        "reasons": [
          "file absent"
        ]
      }
    ],
    "2": [
      {
        "path": "results_clutch_pilot\\task_002_N2_th_45deg.json",
        "exists": false,
        "fresh": false,
        "reasons": [
          "file absent"
        ]
      },
      {
        "path": "results_clutch_pilot\\progress_task_002.json",
        "exists": false,
        "fresh": false,
        "reasons": [
          "file absent"
        ]
      }
    ]
  },
  "mesh_exports": {
    "1": {
      "stator": {
        "vertices": 1080,
        "triangles": 2208,
        "edges": 3312,
        "manifold_watertight_fraction": 1.0,
        "consistent_winding": true,
        "signed_volume_geometry_units_cubed": 0.40521379842314914,
        "path": "results\\scuff_clutch_th0\\stator.msh",
        "sha256": "56b169871e2d5173a8b8486eee85139c5cf00d74e4d6661645eb48c99c887d4e"
      },
      "rotor": {
        "vertices": 408,
        "triangles": 768,
        "edges": 1152,
        "manifold_watertight_fraction": 1.0,
        "consistent_winding": true,
        "signed_volume_geometry_units_cubed": 0.028941153826144272,
        "path": "results\\scuff_clutch_th0\\rotor.msh",
        "sha256": "bb02db0dfb7727a2a2941dcc629cea3313bb4679c17a4991638dbf0ded6850ce"
      },
      "scuffgeo": {
        "path": "results\\scuff_clutch_th0\\clutch.scuffgeo",
        "sha256": "9d171707955c65fbd32153ce02c721b5e35404feacaef6bad5966d3f6ced6132"
      }
    },
    "2": {
      "stator": {
        "vertices": 1080,
        "triangles": 2208,
        "edges": 3312,
        "manifold_watertight_fraction": 1.0,
        "consistent_winding": true,
        "signed_volume_geometry_units_cubed": 0.40521379842314914,
        "path": "results\\scuff_clutch_th45\\stator.msh",
        "sha256": "56b169871e2d5173a8b8486eee85139c5cf00d74e4d6661645eb48c99c887d4e"
      },
      "rotor": {
        "vertices": 408,
        "triangles": 768,
        "edges": 1152,
        "manifold_watertight_fraction": 1.0,
        "consistent_winding": true,
        "signed_volume_geometry_units_cubed": 0.028941153826144206,
        "path": "results\\scuff_clutch_th45\\rotor.msh",
        "sha256": "666bf479e09f0c91fb990349fb30c0a16fb2ad1d6777aafb99b5c95c745a1a3e"
      },
      "scuffgeo": {
        "path": "results\\scuff_clutch_th45\\clutch.scuffgeo",
        "sha256": "9d171707955c65fbd32153ce02c721b5e35404feacaef6bad5966d3f6ced6132"
      }
    }
  },
  "resources": {
    "meep_reference_memory_GB": 481.27,
    "meep_reference_memory_GiB": 448.21761548519135,
    "meep_reference_memory_source": "user-specified 481.27 GB baseline",
    "meep_resolution": 80,
    "meep_moments": 144,
    "degrees_of_freedom": [
      10572390.399999999,
      1488.0,
      1488.0
    ],
    "meep_dof_source": "reference Yee-cell proxy: 3.8 * 3.8 * 1.43 * 80**3",
    "surface_panel_counts": [
      2976,
      2976
    ],
    "dof_policy": "Prefer solver-reported DoF; n_panels_total is a BEM panel-count proxy. Use the reference Yee-cell proxy only when no fresh Meep file is present."
  },
  "ztip_repulsion_summary": {
    "has_repulsion": true,
    "max_repulsive_f_net_pN": 0.5766639334488132,
    "max_repulsive_f_net_fN": 576.6639334488132,
    "max_repulsive_z_tip_nm": -250.0,
    "z_tip_equilibrium_nm": -195.0901751914859
  }
}
```
