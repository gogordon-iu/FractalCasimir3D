# Rotational clutch three-solver verification

Positive force denotes repulsion; negative force denotes attraction. PFA includes only the exact polar tooth–landing-pad overlap at 15 nm. It omits bridges, sidewalls, diffraction and nonlocal interactions; zero PFA in an aperture is therefore not a failed sign prediction.

Frequency and mesh resolution increase together. The ladder measures combined discretization change, not an independently isolated mesh error.

| Design | θ (deg) | State | Tier | ξ nodes | Panels | Vector DOFs | Scalar DOFs | Vector (pN) | Scalar (pN) | PFA (pN) | Vector / scalar / PFA runtime (s) | BEM signs agree | All signs agree |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| Rot_C4_TightSlot_N2 | 6 | Aperture | Standard | 24 | 1504 | 3008 | 1504 | 1.4688216 | 3.8038563 | -0 | 167.343 / 74.185 / 0.000 | True | False |
| Rot_C4_TightSlot_N2 | 18 | Straddling | Standard | 24 | 1504 | 3008 | 1504 | -2.3443663 | -11.513615 | -283.0692 | 164.670 / 74.409 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 48 | Landing Pad | Standard | 24 | 1504 | 3008 | 1504 | -3.1044589 | -20.188113 | -943.564 | 165.600 / 74.999 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 6 | Aperture | High | 32 | 3120 | 6240 | 3120 | 2.5671873 | 5.2100835 | -0 | 723.487 / 280.070 / 0.000 | True | False |
| Rot_C4_TightSlot_N2 | 18 | Straddling | High | 32 | 3120 | 6240 | 3120 | -3.4858616 | -19.335236 | -283.0692 | 722.157 / 278.466 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 48 | Landing Pad | High | 32 | 3120 | 6240 | 3120 | -9.6516618 | -39.727635 | -943.564 | 720.834 / 281.957 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 6 | Aperture | Ultra_High | 40 | 6016 | 12032 | 6016 | 4.3349882 | 7.5678924 | -0 | 2243.725 / 598.849 / 0.000 | True | False |
| Rot_C4_TightSlot_N2 | 18 | Straddling | Ultra_High | 40 | 6016 | 12032 | 6016 | -7.910191 | -30.213535 | -283.0692 | 1833.668 / 612.069 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 48 | Landing Pad | Ultra_High | 40 | 6016 | 12032 | 6016 | -25.234005 | -95.009394 | -943.564 | 1795.908 / 609.087 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 6 | Aperture | Standard | 24 | 1504 | 3008 | 1504 | 1.4913559 | 3.3228564 | -0 | 99.870 / 47.450 / 0.000 | True | False |
| Rot_C8_Compact_N2 | 18 | Straddling | Standard | 24 | 1504 | 3008 | 1504 | -2.3347091 | -9.5176914 | -87.098216 | 102.795 / 47.908 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 48 | Landing Pad | Standard | 24 | 1504 | 3008 | 1504 | -4.2918779 | -20.872078 | -290.32739 | 100.101 / 47.526 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 6 | Aperture | High | 32 | 3120 | 6240 | 3120 | 2.6233199 | 4.4556631 | -0 | 426.958 / 182.009 / 0.000 | True | False |
| Rot_C8_Compact_N2 | 18 | Straddling | High | 32 | 3120 | 6240 | 3120 | -3.7400609 | -15.440375 | -87.098216 | 441.500 / 177.769 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 48 | Landing Pad | High | 32 | 3120 | 6240 | 3120 | -9.6289434 | -34.058814 | -290.32739 | 427.258 / 165.300 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 6 | Aperture | Ultra_High | 40 | 6016 | 12032 | 6016 | 4.1227114 | 6.0888581 | -0 | 1777.278 / 599.276 / 0.000 | True | False |
| Rot_C8_Compact_N2 | 18 | Straddling | Ultra_High | 40 | 6016 | 12032 | 6016 | -7.1484027 | -22.306256 | -87.098216 | 1771.925 / 605.465 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 48 | Landing Pad | Ultra_High | 40 | 6016 | 12032 | 6016 | -22.316304 | -67.355207 | -290.32739 | 1802.154 / 622.282 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 3 | Aperture | Standard | 24 | 3168 | 6336 | 3168 | 3.1774326 | 7.3222348 | -0 | 348.396 / 140.050 / 0.000 | True | False |
| Rot_C10_Fractal_N3 | 21 | Straddling | Standard | 24 | 3168 | 6336 | 3168 | -4.4912158 | -18.541341 | -447.02876 | 352.053 / 136.909 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 48 | Landing Pad | Standard | 24 | 3168 | 6336 | 3168 | -14.038832 | -44.487924 | -894.05753 | 342.693 / 136.873 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 3 | Aperture | High | 32 | 6576 | 13152 | 6576 | 6.1589338 | 11.414593 | -0 | 1772.426 / 628.885 / 0.000 | True | False |
| Rot_C10_Fractal_N3 | 21 | Straddling | High | 32 | 6576 | 13152 | 6576 | -9.9397447 | -27.203883 | -447.02876 | 1821.787 / 587.655 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 48 | Landing Pad | High | 32 | 6576 | 13152 | 6576 | -19.179743 | -49.121846 | -894.05753 | 1784.889 / 577.144 / 0.000 | True | True |

## Convergence and non-additive residual

Relative differences use the finer-tier force magnitude as denominator; a numerically zero denominator is reported as null. The signed residual (F_BEM − F_PFA)/|F_BEM| is a diagnostic, not an isolated measurement of edge diffraction: omitted surfaces and scalar/vector model differences also contribute.

```json
[
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T07:36:53.930628+00:00",
    "design": "Rot_C4_TightSlot_N2",
    "theta_deg": 6.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.42784789992557065,
        "High_to_Ultra_High": 0.40779831637548614,
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.26990491898910657,
        "High_to_Ultra_High": 0.3115542368419128,
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T08:18:00.813923+00:00",
    "design": "Rot_C4_TightSlot_N2",
    "theta_deg": 18.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.32746433935061525,
        "High_to_Ultra_High": 0.5593201666658877,
        "signed_nonadditive_edge_fraction": 34.785381526585034,
        "absolute_nonadditive_edge_fraction": 34.785381526585034
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.4045268117396226,
        "High_to_Ultra_High": 0.3600471957627416,
        "signed_nonadditive_edge_fraction": 8.368953447570076,
        "absolute_nonadditive_edge_fraction": 8.368953447570076
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T08:58:27.340270+00:00",
    "design": "Rot_C4_TightSlot_N2",
    "theta_deg": 48.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.6783498004781161,
        "High_to_Ultra_High": 0.617513682804976,
        "signed_nonadditive_edge_fraction": 36.39255792322144,
        "absolute_nonadditive_edge_fraction": 36.39255792322144
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.49183703575610804,
        "High_to_Ultra_High": 0.5818557116098027,
        "signed_nonadditive_edge_fraction": 8.93127063106349,
        "absolute_nonadditive_edge_fraction": 8.93127063106349
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T10:18:28.941876+00:00",
    "design": "Rot_C8_Compact_N2",
    "theta_deg": 6.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.4315005688040723,
        "High_to_Ultra_High": 0.3636906104976705,
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.25423974935645394,
        "High_to_Ultra_High": 0.2682268166453589,
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T10:58:30.185333+00:00",
    "design": "Rot_C8_Compact_N2",
    "theta_deg": 18.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.375756409539585,
        "High_to_Ultra_High": 0.4767976733391403,
        "signed_nonadditive_edge_fraction": 11.184290575458736,
        "absolute_nonadditive_edge_fraction": 11.184290575458736
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.3835841872132718,
        "High_to_Ultra_High": 0.30780067718128695,
        "signed_nonadditive_edge_fraction": 2.9046542326491855,
        "absolute_nonadditive_edge_fraction": 2.9046542326491855
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T11:39:19.125311+00:00",
    "design": "Rot_C8_Compact_N2",
    "theta_deg": 48.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.5542732290182452,
        "High_to_Ultra_High": 0.5685242790822853,
        "signed_nonadditive_edge_fraction": 12.009653556504249,
        "absolute_nonadditive_edge_fraction": 12.009653556504249
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.3871754090524867,
        "High_to_Ultra_High": 0.49434030326424816,
        "signed_nonadditive_edge_fraction": 3.310392598264031,
        "absolute_nonadditive_edge_fraction": 3.310392598264031
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T12:45:16.444167+00:00",
    "design": "Rot_C10_Fractal_N3",
    "theta_deg": 3.0,
    "highest_tier": "High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.4840937271159321,
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.35851982995241805,
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T13:25:52.713786+00:00",
    "design": "Rot_C10_Fractal_N3",
    "theta_deg": 21.0,
    "highest_tier": "High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.5481558174158198,
        "signed_nonadditive_edge_fraction": 43.973867650430456,
        "absolute_nonadditive_edge_fraction": 43.973867650430456
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.3184303274314379,
        "signed_nonadditive_edge_fraction": 15.432535413698009,
        "absolute_nonadditive_edge_fraction": 15.432535413698009
      }
    }
  },
  {
    "model": "rotational_clutch_3solver_verification",
    "dataset": "rotational_clutch_3solver_verification",
    "status": "completed",
    "executed_at": "2026-10-17T14:05:40.798975+00:00",
    "design": "Rot_C10_Fractal_N3",
    "theta_deg": 48.0,
    "highest_tier": "High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.26803858295493854,
        "signed_nonadditive_edge_fraction": 45.614677405240776,
        "absolute_nonadditive_edge_fraction": 45.614677405240776
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.09433526513914726,
        "signed_nonadditive_edge_fraction": 17.200812885890294,
        "absolute_nonadditive_edge_fraction": 17.200812885890294
      }
    }
  }
]
```

## Hybrid Multi-Scale Active-Zone vs Full-Monolithic

Imported comparison from the real-world NEMS clutch campaign; not an additional solver execution in this verification.

Source: `C:\Users\gorengor\Goren\IUB\Research\FractalCasimirEffect\Code\3Dsimulations\results\real_world_nems_clutch_report.json`
SHA256: `d45a3ba941eab4757981253948fba9f5d67745d5d4621cf38e33991334c2fff8`

```json
{
  "schema_version": 1,
  "model": "BEM and continuum dispersive Lifshitz-PFA",
  "dataset": "real_world_nems_clutch",
  "status": "completed",
  "executed_at": "2026-10-17T03:14:53.577006+00:00",
  "verification_status": "MICRO-PROBE: NOT A COMPLETE VERIFICATION",
  "complete_device_verified": false,
  "mechanical_connectivity_verified": true,
  "full_angle_sampling_completed": false,
  "numerical_checks_passed": false,
  "successful_bem_measurements": 2,
  "designs": {
    "Rot_C4_TightSlot_N2": {
      "R_min_um": 0.3,
      "R_max_um": 1.35,
      "ring_intervals_um": [
        [
          0.3,
          0.4166666666666667
        ],
        [
          0.5333333333333333,
          0.65
        ],
        [
          1.0,
          1.1166666666666667
        ],
        [
          1.2333333333333334,
          1.35
        ]
      ],
      "tooth_intervals_um": [
        [
          0.4370833333333333,
          0.5129166666666667
        ],
        [
          0.7112499999999999,
          0.93875
        ],
        [
          1.1370833333333334,
          1.2129166666666666
        ]
      ],
      "aperture_arc_deg": 36.0,
      "tooth_arc_deg": 15.0,
      "theta_deg": [
        0.0
      ],
      "full_monolithic_fz_N": [
        1.198463495659994e-12
      ],
      "isolated_active_zone_fz_N": [
        1.4846215362842287e-12
      ],
      "continuum_lifshitz_pfa_fz_N": [
        -3.327385549259522e-14
      ]
    },
    "Rot_C8_Compact_N2": {
      "R_min_um": 0.2,
      "R_max_um": 0.9,
      "ring_intervals_um": [
        [
          0.2,
          0.2777777777777778
        ],
        [
          0.35555555555555557,
          0.43333333333333335
        ],
        [
          0.6666666666666667,
          0.7444444444444445
        ],
        [
          0.8222222222222223,
          0.9
        ]
      ],
      "tooth_intervals_um": [
        [
          0.29916666666666664,
          0.33416666666666667
        ],
        [
          0.49750000000000005,
          0.6025
        ],
        [
          0.7658333333333335,
          0.8008333333333334
        ]
      ],
      "aperture_arc_deg": 36.0,
      "tooth_arc_deg": 15.0,
      "theta_deg": [],
      "full_monolithic_fz_N": [],
      "isolated_active_zone_fz_N": [],
      "continuum_lifshitz_pfa_fz_N": []
    },
    "Rot_C10_Fractal_N3": {
      "R_min_um": 0.3,
      "R_max_um": 1.65,
      "ring_intervals_um": [
        [
          0.3,
          0.35
        ],
        [
          0.39999999999999997,
          0.44999999999999996
        ],
        [
          0.6,
          0.65
        ],
        [
          0.7,
          0.75
        ],
        [
          1.2,
          1.25
        ],
        [
          1.2999999999999998,
          1.3499999999999999
        ],
        [
          1.5,
          1.55
        ],
        [
          1.5999999999999999,
          1.65
        ]
      ],
      "tooth_intervals_um": [
        [
          0.365,
          0.385
        ],
        [
          0.4949999999999999,
          0.5549999999999999
        ],
        [
          0.665,
          0.685
        ],
        [
          0.885,
          1.065
        ],
        [
          1.265,
          1.285
        ],
        [
          1.3949999999999998,
          1.4549999999999998
        ],
        [
          1.565,
          1.585
        ]
      ],
      "aperture_arc_deg": 36.0,
      "tooth_arc_deg": 12.0,
      "theta_deg": [],
      "full_monolithic_fz_N": [],
      "isolated_active_zone_fz_N": [],
      "continuum_lifshitz_pfa_fz_N": []
    }
  },
  "geometry_audits": [
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 424,
          "vertices": 416,
          "triangles": 848,
          "occupied_cells": 108,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.40555408613865007,
          "component_panel_counts": {
            "active": 60,
            "foundation": 120,
            "spider": 244
          }
        },
        "stator": {
          "panels": 1168,
          "vertices": 1152,
          "triangles": 2336,
          "occupied_cells": 552,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 2.829828852629725,
          "component_panel_counts": {
            "active": 508,
            "foundation": 660
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "aperture",
          "aperture_fraction": 1.0,
          "landing_pad_fraction": 0.0,
          "delta_z_eff_um": -0.1,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.02041666666666664,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.0,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    }
  ],
  "solver_results": [
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 4,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.198463495659994e-12,
      "elapsed_s": 21.096621100004995,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion",
      "measurement_status": "ok",
      "model": "BEM and continuum dispersive Lifshitz-PFA",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 4,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.4846215362842287e-12,
      "elapsed_s": 13.381331700016744,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion",
      "measurement_status": "ok",
      "model": "BEM and continuum dispersive Lifshitz-PFA",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    }
  ],
  "lifshitz_pfa": [
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.0,
        "spider_to_rib": 0.4031710572106901,
        "tooth_to_floor": 0.3275764839836856
      },
      "gaps_um": {
        "landing_pad": 0.015,
        "spider_to_rib": 0.35,
        "tooth_to_floor": 0.45
      },
      "limitations": [
        "Pairwise projected planar areas; not an exact many-body solution.",
        "Only unshielded aperture tooth area is assigned to the trench floor.",
        "No positive-force stepped-edge contribution is invented.",
        "Hub sidewalls and corner diffraction are not planar PFA terms."
      ],
      "all_gold": {
        "fz_N": -3.327385549259522e-14,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -2.5288879143087007e-14,
          "tooth_to_floor": -7.984976349508213e-15
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -1.0914936535027023e-14,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -8.299340238803797e-15,
          "tooth_to_floor": -2.6155962962232263e-15
        }
      },
      "hybrid_silica": {
        "fz_N": -6.982463645074131e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -5.356542101991504e-15,
          "tooth_to_floor": -1.625921543082627e-15
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.32818141886974506,
          "foundation": 0.32756468920340864
        },
        "silica": {
          "spider": 0.21181413662834378,
          "foundation": 0.2036225872081344
        }
      }
    }
  ],
  "comparison": [
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 1.198463495659994e-12,
      "status": "completed",
      "measurement_status": "ok",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 1.4846215362842287e-12,
      "status": "completed",
      "measurement_status": "ok",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "completed",
      "fz_N": null,
      "measurement_status": "unavailable",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "completed",
      "fz_N": null,
      "measurement_status": "unavailable",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": null,
      "status": "completed",
      "measurement_status": "unavailable",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": null,
      "status": "completed",
      "measurement_status": "unavailable",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "completed",
      "fz_N": null,
      "measurement_status": "unavailable",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "completed",
      "fz_N": null,
      "measurement_status": "unavailable",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "completed",
      "fz_N": -3.327385549259522e-14,
      "landing_pad": -0.0,
      "spider_to_rib": -2.5288879143087007e-14,
      "tooth_to_floor": -7.984976349508213e-15,
      "measurement_status": "ok",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "completed",
      "fz_N": -1.0914936535027023e-14,
      "landing_pad": -0.0,
      "spider_to_rib": -8.299340238803797e-15,
      "tooth_to_floor": -2.6155962962232263e-15,
      "measurement_status": "ok",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "completed",
      "fz_N": -6.982463645074131e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -5.356542101991504e-15,
      "tooth_to_floor": -1.625921543082627e-15,
      "measurement_status": "ok",
      "dataset": "real_world_nems_clutch",
      "executed_at": "2026-10-17T03:14:53.577006+00:00"
    }
  ],
  "convergence": [
    {
      "theta_deg": 0.0,
      "kernel": "vector_dyadic",
      "expected_sign": "repulsive",
      "relative_change": null,
      "within_tolerance": false,
      "expected_sign_verified": false
    },
    {
      "theta_deg": 0.0,
      "kernel": "scalar_yukawa",
      "expected_sign": "repulsive",
      "relative_change": null,
      "within_tolerance": false,
      "expected_sign_verified": false
    },
    {
      "theta_deg": 48.0,
      "kernel": "vector_dyadic",
      "expected_sign": "attractive",
      "relative_change": null,
      "within_tolerance": false,
      "expected_sign_verified": false
    },
    {
      "theta_deg": 48.0,
      "kernel": "scalar_yukawa",
      "expected_sign": "attractive",
      "relative_change": null,
      "within_tolerance": false,
      "expected_sign_verified": false
    }
  ],
  "convergence_relative_tolerance": 0.05,
  "limitations": [
    "Part 2 specifies collars ending at R_min-0.03 and starting at R_max+0.03; part 3 explicitly occupies collars through R_min and from R_max. The mesh follows the explicit part-3 occupancy.",
    "Surviving Cantor ring ribs extend to z=0 in the landing-pad sector to provide pedestal clamps. Connectivity and rotor clearance are audited on the full geometry.",
    "An actuator ring is specified, but comb fingers, suspension, shaft bearings, drive electrodes, and electrical routing are not. Their mechanics and actuation are not verified by this script.",
    "Solver support macro-boxes use 2 nm clearances at adjoining boundaries to avoid overlapping or coincident interface panels. They approximate, rather than exactly reproduce, the connected full-geometry audit mesh.",
    "Selective metallization is a component-weighted homogeneous-BEM approximation, not an exact heterogeneous or finite-thickness coating solve.",
    "The silica comparison uses the specified static dielectric constant; a silica dispersion curve was not supplied.",
    "PFA is a zero-temperature planar projected-area comparison and cannot verify stepped-edge repulsion.",
    "The convergence check increases n_xi to max(12, 2 * baseline n_xi); panel subdivisions may also increase. Separate mesh and quadrature error contributions are not independently established.",
    "No load-bearing stress, buckling, release fabrication, stiction, electrical actuation, shaft bearing, or finite-temperature verification is claimed.",
    "Solves run in-process without a deadline by default. An explicitly requested deadline bounds the solver subprocess, not arbitrary third-party import, plotting, or filesystem latency."
  ],
  "warnings": [
    "save_plot_provenance: RepositoryAPIError: Unsupported required argument 'data_source' in save_plot_provenance(figure_path: str, data_source: str, columns_used: List[str], sidecar_suffix: str = '.provenance.json', solver_name: str | None = None, solver_parameters: Dict[str, Any] | None = None) -> str. Extend the explicit repository adapter for this API.",
    "save_plot_provenance: RepositoryAPIError: Unsupported required argument 'data_source' in save_plot_provenance(figure_path: str, data_source: str, columns_used: List[str], sidecar_suffix: str = '.provenance.json', solver_name: str | None = None, solver_parameters: Dict[str, Any] | None = None) -> str. Extend the explicit repository adapter for this API."
  ],
  "provenance": {
    "run_id": "real_world_nems_clutch_1792206895198703200",
    "script": "C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\execution\\run_real_world_nems_clutch.py",
    "device": "cpu",
    "python": "3.14.0 (tags/v3.14.0:ebf955d, Oct  7 2025, 10:15:03) [MSC v.1944 64 bit (AMD64)]",
    "numpy": "2.4.6",
    "arguments": {
      "max_steps": 5,
      "device": "auto",
      "plot": true,
      "n_xi": 6,
      "subdivisions": 1,
      "convergence_subdivisions": 1,
      "convergence_tolerance": 0.05,
      "solver_timeout": 0.0,
      "threads": 8,
      "strict": false
    },
    "micro_probe": true,
    "force_units": "N",
    "length_units": "um",
    "full_360_degree_mesh": true,
    "solver_sector_deg": 90.0,
    "solver_face_angular_unit": "rad",
    "solver_symmetry_multiplier": 4,
    "temperature_K": 0.0,
    "gold_model": {
      "model": "Drude",
      "eps_inf": 1.0,
      "omega_p_inv_um": 45.76160838064494,
      "gamma_inv_um": 0.268589728037008,
      "hbar_c_eV_um": 0.1973269804,
      "frequency_convention": "angular wavenumber, rad/um",
      "note": "The specified Drude-Lorentz stack has no Lorentz poles for Au."
    },
    "hybrid_model": "component-weighted BEM approximation",
    "no_fabricated_solver_results": true,
    "model": "BEM and continuum dispersive Lifshitz-PFA",
    "dataset": "real_world_nems_clutch",
    "executed_at": "2026-10-17T03:14:53.577006+00:00",
    "sampled_angles": {
      "Rot_C4_TightSlot_N2": [
        0.0
      ]
    }
  },
  "elapsed_s": 42.40805090000504,
  "micro_probe_under_15s": false
}
```

## External SCUFF provenance

Gmsh v2.2 and .scuffgeo exports are recorded in the JSON report with SHA256 digests and triangle counts. PATH availability does not imply SCUFF execution. SCUFF's Gold material must be explicitly matched to MaterialModel before interpreting an external calculation as verification.
