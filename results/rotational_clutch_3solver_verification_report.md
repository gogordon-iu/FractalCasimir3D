# Rotational clutch three-solver verification

Positive force denotes repulsion; negative force denotes attraction. PFA includes only the exact polar tooth–landing-pad overlap at 15 nm. It omits bridges, sidewalls, diffraction and nonlocal interactions; zero PFA in an aperture is therefore not a failed sign prediction.

Frequency and mesh resolution increase together. The ladder measures combined discretization change, not an independently isolated mesh error.

| Design | θ (deg) | State | Tier | ξ nodes | Panels | Vector DOFs | Scalar DOFs | Vector (pN) | Scalar (pN) | PFA (pN) | Vector / scalar / PFA runtime (s) | BEM signs agree | All signs agree |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| Rot_C4_TightSlot_N2 | 6 | Aperture | Standard | 24 | 1504 | 3008 | 3008 | 0.56260508 | 1.2380379 | -0 | 48.689 / 20.433 / 0.000 | True | False |
| Rot_C4_TightSlot_N2 | 18 | Straddling | Standard | 24 | 1504 | 3008 | 3008 | -0.55908411 | -0.38757977 | -51.474433 | 50.821 / 20.660 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 48 | Landing Pad | Standard | 24 | 1504 | 3008 | 3008 | -4.8571499 | -6.7850438 | -171.58144 | 46.278 / 21.874 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 6 | Aperture | High | 32 | 3120 | 6240 | 6240 | -0.68715365 | -0.81018538 | -0 | 159.433 / 66.752 / 0.000 | True | False |
| Rot_C4_TightSlot_N2 | 18 | Straddling | High | 32 | 3120 | 6240 | 6240 | -3.220485 | -3.526892 | -51.474433 | 180.974 / 101.668 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 48 | Landing Pad | High | 32 | 3120 | 6240 | 6240 | -10.412936 | -12.378494 | -171.58144 | 154.210 / 67.951 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 6 | Aperture | Ultra_High | 40 | 6016 | 12032 | 12032 | -1.5254101 | -1.2874678 | -0 | 550.718 / 169.193 / 0.000 | True | False |
| Rot_C4_TightSlot_N2 | 18 | Straddling | Ultra_High | 40 | 6016 | 12032 | 12032 | -8.8173022 | -8.7496133 | -51.474433 | 563.543 / 194.152 / 0.000 | True | True |
| Rot_C4_TightSlot_N2 | 48 | Landing Pad | Ultra_High | 40 | 6016 | 12032 | 12032 | -20.953268 | -19.215336 | -171.58144 | 575.690 / 194.484 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 6 | Aperture | Standard | 24 | 1504 | 3008 | 3008 | 0.86920372 | 1.6176493 | -0 | 51.563 / 22.945 / 0.000 | True | False |
| Rot_C8_Compact_N2 | 18 | Straddling | Standard | 24 | 1504 | 3008 | 3008 | -0.087553469 | 0.34629184 | -15.838287 | 53.718 / 23.323 / 0.000 | False | False |
| Rot_C8_Compact_N2 | 48 | Landing Pad | Standard | 24 | 1504 | 3008 | 3008 | -4.4406782 | -5.6209447 | -52.794291 | 52.879 / 23.304 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 6 | Aperture | High | 32 | 3120 | 6240 | 6240 | -0.68081762 | -0.77435129 | -0 | 156.602 / 67.897 / 0.000 | True | False |
| Rot_C8_Compact_N2 | 18 | Straddling | High | 32 | 3120 | 6240 | 6240 | -2.6523038 | -2.5888615 | -15.838287 | 155.413 / 66.990 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 48 | Landing Pad | High | 32 | 3120 | 6240 | 6240 | -8.8967962 | -9.926284 | -52.794291 | 157.437 / 67.953 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 6 | Aperture | Ultra_High | 40 | 6016 | 12032 | 12032 | -1.4528717 | -1.1593237 | -0 | 547.305 / 189.022 / 0.000 | True | False |
| Rot_C8_Compact_N2 | 18 | Straddling | Ultra_High | 40 | 6016 | 12032 | 12032 | -7.0481953 | -6.9896709 | -15.838287 | 544.016 / 189.303 / 0.000 | True | True |
| Rot_C8_Compact_N2 | 48 | Landing Pad | Ultra_High | 40 | 6016 | 12032 | 12032 | -17.257317 | -16.558532 | -52.794291 | 547.808 / 189.164 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 3 | Aperture | Standard | 24 | 3168 | 6336 | 6336 | 5.0089202 | 8.4773247 | -0 | 133.180 / 59.206 / 0.000 | True | False |
| Rot_C10_Fractal_N3 | 21 | Straddling | Standard | 24 | 3168 | 6336 | 6336 | 0.60941926 | 3.5633707 | -81.289495 | 134.657 / 57.580 / 0.000 | True | False |
| Rot_C10_Fractal_N3 | 48 | Landing Pad | Standard | 24 | 3168 | 6336 | 6336 | -10.357241 | -11.441743 | -162.57899 | 133.752 / 59.337 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 3 | Aperture | High | 32 | 6576 | 13152 | 13152 | -1.7010722 | -3.0467682 | -0 | 602.010 / 191.213 / 0.000 | True | False |
| Rot_C10_Fractal_N3 | 21 | Straddling | High | 32 | 6576 | 13152 | 13152 | -6.2630045 | -7.0540184 | -81.289495 | 590.136 / 190.242 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 48 | Landing Pad | High | 32 | 6576 | 13152 | 13152 | -6.6275242 | -6.5129257 | -162.57899 | 601.894 / 193.018 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 3 | Aperture | Ultra_High | 40 | 12672 | 25344 | 25344 | -4.3925053 | -3.3551003 | -0 | 3157.464 / 716.664 / 0.000 | True | False |
| Rot_C10_Fractal_N3 | 21 | Straddling | Ultra_High | 40 | 12672 | 25344 | 25344 | -20.803854 | -20.228257 | -81.289495 | 3170.316 / 726.822 / 0.000 | True | True |
| Rot_C10_Fractal_N3 | 48 | Landing Pad | Ultra_High | 40 | 12672 | 25344 | 25344 | -30.521071 | -29.956724 | -162.57899 | 3222.439 / 736.652 / 0.000 | True | True |

## Convergence and non-additive residual

Relative differences use the finer-tier force magnitude as denominator; a numerically zero denominator is reported as null. The signed residual (F_BEM − F_PFA)/|F_BEM| is a diagnostic, not an isolated measurement of edge diffraction: omitted surfaces and scalar/vector model differences also contribute.

```json
[
  {
    "design": "Rot_C4_TightSlot_N2",
    "theta_deg": 6.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 1.8187471384129605,
        "High_to_Ultra_High": 0.5495285913058949,
        "signed_nonadditive_edge_fraction": -1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      },
      "scalar_yukawa": {
        "Standard_to_High": 2.5280921943661774,
        "High_to_Ultra_High": 0.3707140502399704,
        "signed_nonadditive_edge_fraction": -1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      }
    }
  },
  {
    "design": "Rot_C4_TightSlot_N2",
    "theta_deg": 18.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.826397541874943,
        "High_to_Ultra_High": 0.6347539299121696,
        "signed_nonadditive_edge_fraction": 4.837889187154946,
        "absolute_nonadditive_edge_fraction": 4.837889187154946
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.8901072769779738,
        "High_to_Ultra_High": 0.5969088100414256,
        "signed_nonadditive_edge_fraction": 4.883052404399711,
        "absolute_nonadditive_edge_fraction": 4.883052404399711
      }
    }
  },
  {
    "design": "Rot_C4_TightSlot_N2",
    "theta_deg": 48.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.5335465430218616,
        "High_to_Ultra_High": 0.5030400096901171,
        "signed_nonadditive_edge_fraction": 7.18876775749247,
        "absolute_nonadditive_edge_fraction": 7.18876775749247
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.4518684112831597,
        "High_to_Ultra_High": 0.3558013030352448,
        "signed_nonadditive_edge_fraction": 7.929401171790482,
        "absolute_nonadditive_edge_fraction": 7.929401171790482
      }
    }
  },
  {
    "design": "Rot_C8_Compact_N2",
    "theta_deg": 6.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 2.2767056806742625,
        "High_to_Ultra_High": 0.5313986498653732,
        "signed_nonadditive_edge_fraction": -1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      },
      "scalar_yukawa": {
        "Standard_to_High": 3.089038001049848,
        "High_to_Ultra_High": 0.3320663852915273,
        "signed_nonadditive_edge_fraction": -1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      }
    }
  },
  {
    "design": "Rot_C8_Compact_N2",
    "theta_deg": 18.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.9669896525170111,
        "High_to_Ultra_High": 0.623690370850223,
        "signed_nonadditive_edge_fraction": 1.247140788365648,
        "absolute_nonadditive_edge_fraction": 1.247140788365648
      },
      "scalar_yukawa": {
        "Standard_to_High": 1.1337622105006224,
        "High_to_Ultra_High": 0.6296161074232406,
        "signed_nonadditive_edge_fraction": 1.265956051610628,
        "absolute_nonadditive_edge_fraction": 1.265956051610628
      }
    }
  },
  {
    "design": "Rot_C8_Compact_N2",
    "theta_deg": 48.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.5008677164139624,
        "High_to_Ultra_High": 0.4844623782061508,
        "signed_nonadditive_edge_fraction": 2.0592409288316724,
        "absolute_nonadditive_edge_fraction": 2.0592409288316724
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.433731225572749,
        "High_to_Ultra_High": 0.40053358617129625,
        "signed_nonadditive_edge_fraction": 2.188343603879277,
        "absolute_nonadditive_edge_fraction": 2.188343603879277
      }
    }
  },
  {
    "design": "Rot_C10_Fractal_N3",
    "theta_deg": 3.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 3.9445664905779756,
        "High_to_Ultra_High": 0.6127330327542947,
        "signed_nonadditive_edge_fraction": -1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      },
      "scalar_yukawa": {
        "Standard_to_High": 3.7823990005719255,
        "High_to_Ultra_High": 0.09189952278678545,
        "signed_nonadditive_edge_fraction": -1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      }
    }
  },
  {
    "design": "Rot_C10_Fractal_N3",
    "theta_deg": 21.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 1.0973046178084433,
        "High_to_Ultra_High": 0.6989497948924764,
        "signed_nonadditive_edge_fraction": 2.9074247665390667,
        "absolute_nonadditive_edge_fraction": 2.9074247665390667
      },
      "scalar_yukawa": {
        "Standard_to_High": 1.5051547248943402,
        "High_to_Ultra_High": 0.6512789705043512,
        "signed_nonadditive_edge_fraction": 3.018611020373797,
        "absolute_nonadditive_edge_fraction": 3.018611020373797
      }
    }
  },
  {
    "design": "Rot_C10_Fractal_N3",
    "theta_deg": 48.0,
    "highest_tier": "Ultra_High",
    "comparisons": {
      "vector_dyadic": {
        "Standard_to_High": 0.5627617673560453,
        "High_to_Ultra_High": 0.7828541422413022,
        "signed_nonadditive_edge_fraction": 4.326778583113995,
        "absolute_nonadditive_edge_fraction": 4.326778583113995
      },
      "scalar_yukawa": {
        "Standard_to_High": 0.7567746438501545,
        "High_to_Ultra_High": 0.7825888556310001,
        "signed_nonadditive_edge_fraction": 4.427128432735222,
        "absolute_nonadditive_edge_fraction": 4.427128432735222
      }
    }
  }
]
```

## Hybrid Multi-Scale Active-Zone vs Full-Monolithic

Imported comparison from the real-world NEMS clutch campaign; not an additional solver execution in this verification.

Source: `C:\Users\gorengor\Goren\IUB\Research\FractalCasimirEffect\Code\3Dsimulations\results\real_world_nems_clutch_report.json`
SHA256: `fdbe033630bc8eb55b15c13741fb8fb744d4812a0202604da7cf23a6f563556a`

```json
{
  "schema_version": 1,
  "verification_status": "NOT VERIFIED: SPECIFICATION OR MODEL LIMITATIONS",
  "complete_device_verified": false,
  "mechanical_connectivity_verified": true,
  "full_angle_sampling_completed": true,
  "numerical_checks_passed": true,
  "successful_bem_measurements": 108,
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
        0.0,
        18.0,
        36.0,
        48.0
      ],
      "full_monolithic_fz_N": [
        3.8066220764340566e-13,
        -9.496844964356408e-13,
        -4.332302261101349e-12,
        -6.77156974820437e-12
      ],
      "isolated_active_zone_fz_N": [
        5.625912904808796e-13,
        -5.587978064167808e-13,
        -3.611829866374616e-12,
        -4.853539518848715e-12
      ],
      "continuum_lifshitz_pfa_fz_N": [
        -1.431288400552545e-14,
        -5.148446398160115e-11,
        -1.7158148320932423e-10,
        -1.7158148320932423e-10
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
      "theta_deg": [
        0.0,
        18.0,
        36.0,
        48.0
      ],
      "full_monolithic_fz_N": [
        6.779978736669609e-13,
        -5.431087494888064e-13,
        -3.932082774619848e-12,
        -6.387259138340825e-12
      ],
      "isolated_active_zone_fz_N": [
        8.69151249400552e-13,
        -8.746257653481406e-14,
        -3.2376766887440006e-12,
        -4.4396633866961004e-12
      ],
      "continuum_lifshitz_pfa_fz_N": [
        -5.8540306750504225e-15,
        -1.5842388579256313e-11,
        -5.279430252594592e-11,
        -5.279430252594592e-11
      ]
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
      "theta_deg": [
        0.0,
        3.0,
        21.0,
        30.0,
        48.0
      ],
      "full_monolithic_fz_N": [
        2.903205374242642e-12,
        4.803160174542853e-12,
        -5.373504834431514e-13,
        -1.1025989867278876e-11,
        -1.2869670484299065e-11
      ],
      "isolated_active_zone_fz_N": [
        3.1150630312915713e-12,
        5.00793030572078e-12,
        6.094373984516655e-13,
        -1.0474387445792478e-11,
        -1.0352276821972144e-11
      ],
      "continuum_lifshitz_pfa_fz_N": [
        -1.2107712886844523e-14,
        -1.2107712886844523e-14,
        -8.129556694054926e-11,
        -1.625790261682117e-10,
        -1.625790261682117e-10
      ]
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
          "volume_um3": 0.40555408613865,
          "component_panel_counts": {
            "active": 108,
            "foundation": 120,
            "spider": 196
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
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 568,
          "vertices": 560,
          "triangles": 1136,
          "occupied_cells": 184,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.4055540861386504,
          "component_panel_counts": {
            "active": 168,
            "foundation": 112,
            "spider": 288
          }
        },
        "stator": {
          "panels": 1136,
          "vertices": 1120,
          "triangles": 2272,
          "occupied_cells": 672,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 2.8298288526297215,
          "component_panel_counts": {
            "active": 552,
            "foundation": 584
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "straddling",
          "aperture_fraction": 0.7,
          "landing_pad_fraction": 0.30000000000000004,
          "delta_z_eff_um": null,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.02041666666666664,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
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
          "volume_um3": 0.4055540861386498,
          "component_panel_counts": {
            "active": 108,
            "foundation": 120,
            "spider": 196
          }
        },
        "stator": {
          "panels": 1104,
          "vertices": 1088,
          "triangles": 2208,
          "occupied_cells": 792,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 2.8298288526297295,
          "component_panel_counts": {
            "active": 596,
            "foundation": 508
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "landing_pad",
          "aperture_fraction": 0.0,
          "landing_pad_fraction": 1.0,
          "delta_z_eff_um": 0.015,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.02041666666666664,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
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
          "volume_um3": 0.40555408613865,
          "component_panel_counts": {
            "active": 108,
            "foundation": 120,
            "spider": 196
          }
        },
        "stator": {
          "panels": 1104,
          "vertices": 1088,
          "triangles": 2208,
          "occupied_cells": 792,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 2.82982885262972,
          "component_panel_counts": {
            "active": 596,
            "foundation": 508
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "landing_pad",
          "aperture_fraction": 0.0,
          "landing_pad_fraction": 1.0,
          "delta_z_eff_um": 0.015,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.02041666666666664,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C8_Compact_N2",
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
          "volume_um3": 0.19326292606721,
          "component_panel_counts": {
            "active": 108,
            "foundation": 120,
            "spider": 196
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
          "volume_um3": 1.4074509621004447,
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
          "minimum_elevated_rib_radial_clearance_um": 0.021388888888888846,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 568,
          "vertices": 560,
          "triangles": 1136,
          "occupied_cells": 184,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.1932629260672101,
          "component_panel_counts": {
            "active": 168,
            "foundation": 112,
            "spider": 288
          }
        },
        "stator": {
          "panels": 1136,
          "vertices": 1120,
          "triangles": 2272,
          "occupied_cells": 672,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 1.407450962100443,
          "component_panel_counts": {
            "active": 552,
            "foundation": 584
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "straddling",
          "aperture_fraction": 0.7,
          "landing_pad_fraction": 0.30000000000000004,
          "delta_z_eff_um": null,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.021388888888888846,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
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
          "volume_um3": 0.19326292606721007,
          "component_panel_counts": {
            "active": 108,
            "foundation": 120,
            "spider": 196
          }
        },
        "stator": {
          "panels": 1104,
          "vertices": 1088,
          "triangles": 2208,
          "occupied_cells": 792,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 1.4074509621004447,
          "component_panel_counts": {
            "active": 596,
            "foundation": 508
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "landing_pad",
          "aperture_fraction": 0.0,
          "landing_pad_fraction": 1.0,
          "delta_z_eff_um": 0.015,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.021388888888888846,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
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
          "volume_um3": 0.19326292606721016,
          "component_panel_counts": {
            "active": 108,
            "foundation": 120,
            "spider": 196
          }
        },
        "stator": {
          "panels": 1104,
          "vertices": 1088,
          "triangles": 2208,
          "occupied_cells": 792,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 1.4074509621004465,
          "component_panel_counts": {
            "active": 596,
            "foundation": 508
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "landing_pad",
          "aperture_fraction": 0.0,
          "landing_pad_fraction": 1.0,
          "delta_z_eff_um": 0.015,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.021388888888888846,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 808,
          "vertices": 800,
          "triangles": 1616,
          "occupied_cells": 204,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.4484309353734073,
          "component_panel_counts": {
            "active": 252,
            "foundation": 120,
            "spider": 436
          }
        },
        "stator": {
          "panels": 2224,
          "vertices": 2176,
          "triangles": 4448,
          "occupied_cells": 1016,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 3.9755362774668312,
          "component_panel_counts": {
            "active": 1116,
            "foundation": 1108
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
          "minimum_elevated_rib_radial_clearance_um": 0.014999999999999902,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 808,
          "vertices": 800,
          "triangles": 1616,
          "occupied_cells": 204,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.4484309353734073,
          "component_panel_counts": {
            "active": 252,
            "foundation": 120,
            "spider": 436
          }
        },
        "stator": {
          "panels": 2224,
          "vertices": 2176,
          "triangles": 4448,
          "occupied_cells": 1016,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 3.9755362774668397,
          "component_panel_counts": {
            "active": 1116,
            "foundation": 1108
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
          "minimum_elevated_rib_radial_clearance_um": 0.014999999999999902,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 1144,
          "vertices": 1136,
          "triangles": 2288,
          "occupied_cells": 376,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.4484309353734079,
          "component_panel_counts": {
            "active": 392,
            "foundation": 112,
            "spider": 640
          }
        },
        "stator": {
          "panels": 2192,
          "vertices": 2144,
          "triangles": 4384,
          "occupied_cells": 1280,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 3.975536277466842,
          "component_panel_counts": {
            "active": 1224,
            "foundation": 968
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "straddling",
          "aperture_fraction": 0.5,
          "landing_pad_fraction": 0.5,
          "delta_z_eff_um": null,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.014999999999999902,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 808,
          "vertices": 800,
          "triangles": 1616,
          "occupied_cells": 204,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.4484309353734075,
          "component_panel_counts": {
            "active": 252,
            "foundation": 120,
            "spider": 436
          }
        },
        "stator": {
          "panels": 2160,
          "vertices": 2112,
          "triangles": 4320,
          "occupied_cells": 1544,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 3.975536277466831,
          "component_panel_counts": {
            "active": 1332,
            "foundation": 828
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "landing_pad",
          "aperture_fraction": 0.0,
          "landing_pad_fraction": 1.0,
          "delta_z_eff_um": 0.015,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.014999999999999902,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
          "z_pad_top_um": -0.115,
          "z_pad_bottom_um": -0.265,
          "qualification": "Analytical curved-geometry clearance, not mesh convergence."
        },
        "repository_certificate_scope": "Repository active-zone certificate is supplementary; the full occupancy intersection audit is authoritative for extended shanks and landing-sector rib clamps."
      },
      "zero_floating_parts": true
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "status": "ok",
      "mesh": {
        "rotor": {
          "panels": 808,
          "vertices": 800,
          "triangles": 1616,
          "occupied_cells": 204,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 0.4484309353734077,
          "component_panel_counts": {
            "active": 252,
            "foundation": 120,
            "spider": 436
          }
        },
        "stator": {
          "panels": 2160,
          "vertices": 2112,
          "triangles": 4320,
          "occupied_cells": 1544,
          "connected_components": 1,
          "watertight": true,
          "orientation_consistent": true,
          "volume_um3": 3.975536277466844,
          "component_panel_counts": {
            "active": 1332,
            "foundation": 828
          }
        }
      },
      "collision": {
        "full_geometry_collision_free": true,
        "intersections": [],
        "minimum_named_vertical_gap_um": 0.015,
        "repository_angular_state": {
          "state": "landing_pad",
          "aperture_fraction": 0.0,
          "landing_pad_fraction": 1.0,
          "delta_z_eff_um": 0.015,
          "z_tip_fixed_um": -0.1
        },
        "repository_collision_certificate": {
          "collision_free_for_all_angles": true,
          "minimum_elevated_rib_radial_clearance_um": 0.014999999999999902,
          "landing_pad_vertical_clearance_um": 0.015,
          "z_tip_fixed_um": -0.1,
          "z_rotor_top_um": 0.15,
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
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 3.8066220764340566e-13,
      "elapsed_s": 23.9390540999957,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.1775233642123173e-12,
      "elapsed_s": 11.328025800001342,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 5.625912904808796e-13,
      "elapsed_s": 17.439484800001082,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.2376535271138745e-12,
      "elapsed_s": 5.637410200004524,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 3.9131503421495974e-13,
      "elapsed_s": 23.588655200001085,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.1793433916322573e-12,
      "elapsed_s": 11.197746099998767,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.321919960012413e-13,
      "elapsed_s": 21.66051940000034,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.2043680115738016e-12,
      "elapsed_s": 10.38252420000208,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -9.496844964356408e-13,
      "elapsed_s": 25.117551799994544,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.961084003597056e-13,
      "elapsed_s": 10.35187649999716,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.587978064167808e-13,
      "elapsed_s": 17.967456399994262,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -3.87153657381211e-13,
      "elapsed_s": 5.744885899999645,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -9.408305427945331e-13,
      "elapsed_s": 22.83146029999625,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.94412896458725e-13,
      "elapsed_s": 10.739543499999854,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -8.544487709254952e-13,
      "elapsed_s": 22.010041600005934,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.888499555256089e-13,
      "elapsed_s": 10.112068800000998,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.332302261101349e-12,
      "elapsed_s": 25.03934339999978,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.412691482859154e-12,
      "elapsed_s": 10.525232100000721,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -3.611829866374616e-12,
      "elapsed_s": 10.136852299998282,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.287121872368014e-12,
      "elapsed_s": 3.1809763999990537,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.32228921115672e-12,
      "elapsed_s": 12.935984800002188,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.410945529895565e-12,
      "elapsed_s": 5.847242700001516,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.202435476869451e-12,
      "elapsed_s": 12.416931899999327,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.46008091643893e-12,
      "elapsed_s": 5.569681799999671,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.77156974820437e-12,
      "elapsed_s": 12.512117600002966,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.793755377465048e-12,
      "elapsed_s": 5.621837500002584,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.853539518848715e-12,
      "elapsed_s": 9.174831899996207,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.764514870992626e-12,
      "elapsed_s": 3.0646073000025353,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.757773620541076e-12,
      "elapsed_s": 11.346957399997336,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.792424568620954e-12,
      "elapsed_s": 5.386524200002896,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.69180002285337e-12,
      "elapsed_s": 10.874878700000409,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.77416293651252e-12,
      "elapsed_s": 4.068132399996102,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 6.779978736669609e-13,
      "elapsed_s": 11.977711700004875,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.5587605428432081e-12,
      "elapsed_s": 5.910496900003636,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 8.69151249400552e-13,
      "elapsed_s": 8.993963100001565,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.6171233981917287e-12,
      "elapsed_s": 3.2807514000014635,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 6.848606246328541e-13,
      "elapsed_s": 12.772853200003738,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.5597280551527695e-12,
      "elapsed_s": 3.3033781999984058,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 7.229864674174051e-13,
      "elapsed_s": 8.222892700003285,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.5750541206907842e-12,
      "elapsed_s": 3.1245515000046,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.431087494888064e-13,
      "elapsed_s": 8.601167100001476,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.6127645486203573e-13,
      "elapsed_s": 3.9620747000008123,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -8.746257653481406e-14,
      "elapsed_s": 7.02070349999849,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 3.4626770180900713e-13,
      "elapsed_s": 1.9943627000029664,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.375919094086243e-13,
      "elapsed_s": 8.86500089999754,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.622069648232028e-13,
      "elapsed_s": 2.8639480999991065,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.556642815498835e-13,
      "elapsed_s": 8.491191300003265,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.580771747628187e-13,
      "elapsed_s": 3.064135599997826,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -3.932082774619848e-12,
      "elapsed_s": 10.86746139999741,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.6707805541356574e-12,
      "elapsed_s": 3.98921440000413,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -3.2376766887440006e-12,
      "elapsed_s": 7.248153100001218,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.379914454948566e-12,
      "elapsed_s": 2.100357299997995,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -3.926285369052486e-12,
      "elapsed_s": 8.888366599996516,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.669863084340521e-12,
      "elapsed_s": 3.0635060999993584,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -3.79564093086902e-12,
      "elapsed_s": 9.2869314999989,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.712346698505329e-12,
      "elapsed_s": 3.8052741999999853,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.387259138340825e-12,
      "elapsed_s": 9.25248570000258,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.382254890142974e-12,
      "elapsed_s": 3.220041400003538,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.4396633866961004e-12,
      "elapsed_s": 6.654051500001515,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.616027211148983e-12,
      "elapsed_s": 2.094662799994694,
      "solver_sector_panels": {
        "rotor": 96,
        "stator": 280
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.379628116959781e-12,
      "elapsed_s": 8.48407440000301,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.381466523684748e-12,
      "elapsed_s": 2.9309095999997226,
      "solver_sector_panels": {
        "rotor": 126,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.306834090186043e-12,
      "elapsed_s": 8.741761199999019,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -6.3726775412581994e-12,
      "elapsed_s": 3.111526299995603,
      "solver_sector_panels": {
        "rotor": 120,
        "stator": 310
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 2.903205374242642e-12,
      "elapsed_s": 34.879424399994605,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.6775106956361694e-12,
      "elapsed_s": 11.582284500000242,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 3.1150630312915713e-12,
      "elapsed_s": 26.22867199999746,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.757038726255885e-12,
      "elapsed_s": 8.65518929999962,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 2.913272471642595e-12,
      "elapsed_s": 32.91881160000048,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.679215280745322e-12,
      "elapsed_s": 10.339161999996577,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 2.9552215968166363e-12,
      "elapsed_s": 30.625827300005767,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.708838721262193e-12,
      "elapsed_s": 10.835959299998649,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.803160174542853e-12,
      "elapsed_s": 32.89196720000473,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 8.38725212049833e-12,
      "elapsed_s": 10.633141600003,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 5.00793030572078e-12,
      "elapsed_s": 30.86998059999314,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 8.458942196154191e-12,
      "elapsed_s": 8.752584099995147,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.813159715436417e-12,
      "elapsed_s": 32.78224449999834,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 8.388951533539289e-12,
      "elapsed_s": 11.872023399999307,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 4.855163506851862e-12,
      "elapsed_s": 31.921449100002064,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 8.417558548799445e-12,
      "elapsed_s": 10.824150300002657,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.373504834431514e-13,
      "elapsed_s": 47.1431436999992,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.866991915006756e-12,
      "elapsed_s": 14.608643899999151,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 6.094373984516655e-13,
      "elapsed_s": 29.84853380000277,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 3.5624287590713593e-12,
      "elapsed_s": 11.514810099994065,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -5.281050298558421e-13,
      "elapsed_s": 37.12427639999805,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.8685003693675662e-12,
      "elapsed_s": 14.239138199998706,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -4.342620455625017e-13,
      "elapsed_s": 37.6410745999965,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": 1.8734263988298468e-12,
      "elapsed_s": 13.23292379999475,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1025989867278876e-11,
      "elapsed_s": 38.289200499995786,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1641419592141825e-11,
      "elapsed_s": 14.21673980000196,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.0474387445792478e-11,
      "elapsed_s": 28.718766300000425,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1437027142639803e-11,
      "elapsed_s": 10.987229600003047,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1017814916902056e-11,
      "elapsed_s": 37.211516300005314,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1639402483252338e-11,
      "elapsed_s": 14.261706099998264,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.0861868281257034e-11,
      "elapsed_s": 39.300935799998115,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1666013326332057e-11,
      "elapsed_s": 14.747192300004826,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.2869670484299065e-11,
      "elapsed_s": 37.232105799994315,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.15888228094091e-11,
      "elapsed_s": 14.680566700000782,
      "solver_sector_panels": {
        "rotor": 284,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "isolated",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.0352276821972144e-11,
      "elapsed_s": 28.95410450000054,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "isolated",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1430022652804102e-11,
      "elapsed_s": 11.993515199996182,
      "solver_sector_panels": {
        "rotor": 224,
        "stator": 568
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "without_spider",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.2850538763699596e-11,
      "elapsed_s": 37.3476967999959,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "without_spider",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1587311738941677e-11,
      "elapsed_s": 14.828992599999765,
      "solver_sector_panels": {
        "rotor": 278,
        "stator": 640
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "without_foundation",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.2793421086168607e-11,
      "elapsed_s": 35.07146310000098,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "variant": "without_foundation",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 6,
      "device": "cpu",
      "convergence": false,
      "status": "ok",
      "fz_N": -1.1563824081278936e-11,
      "elapsed_s": 14.363864799997828,
      "solver_sector_panels": {
        "rotor": 272,
        "stator": 622
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 12,
      "device": "cpu",
      "convergence": true,
      "status": "ok",
      "fz_N": 3.798602937100651e-13,
      "elapsed_s": 28.564898900003755,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 12,
      "device": "cpu",
      "convergence": true,
      "status": "ok",
      "fz_N": 1.1777657073526145e-12,
      "elapsed_s": 12.762129700000514,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "vector_dyadic",
      "subdivisions": 1,
      "n_xi": 12,
      "device": "cpu",
      "convergence": true,
      "status": "ok",
      "fz_N": -6.7995239769358635e-12,
      "elapsed_s": 30.34669120000035,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "variant": "full",
      "kernel": "scalar_yukawa",
      "subdivisions": 1,
      "n_xi": 12,
      "device": "cpu",
      "convergence": true,
      "status": "ok",
      "fz_N": -6.813382724918876e-12,
      "elapsed_s": 12.273172000001068,
      "solver_sector_panels": {
        "rotor": 132,
        "stator": 328
      },
      "solver_sector_deg": 90.0,
      "solver_symmetry_multiplier": 4,
      "force_conversion": "f_net_N already in SI Newtons; no conversion"
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
        "fz_N": -1.431288400552545e-14,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -1.0603610298873974e-14,
          "tooth_to_floor": -3.7092737066514745e-15
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -7.850136028978302e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -5.903303551327707e-15,
          "tooth_to_floor": -1.946832477650595e-15
        }
      },
      "hybrid_silica": {
        "fz_N": -4.8743166173437e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -3.684058585942897e-15,
          "tooth_to_floor": -1.1902580314008037e-15
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.0982729451951057,
        "spider_to_rib": 0.2822197400474831,
        "tooth_to_floor": 0.2293035387885799
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
        "fz_N": -5.148446398160115e-11,
        "components_N": {
          "landing_pad": -5.147444496279728e-11,
          "spider_to_rib": -7.422527209211784e-15,
          "tooth_to_floor": -2.5964915946560316e-15
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -5.1479940058017567e-11,
        "components_N": {
          "landing_pad": -5.147444496279728e-11,
          "spider_to_rib": -4.1323124859293955e-15,
          "tooth_to_floor": -1.3627827343554166e-15
        }
      },
      "hybrid_silica": {
        "fz_N": -5.147785698442942e-11,
        "components_N": {
          "landing_pad": -5.147444496279728e-11,
          "spider_to_rib": -2.5788410101600284e-15,
          "tooth_to_floor": -8.331806219805624e-16
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.3275764839836856,
        "spider_to_rib": 0.0,
        "tooth_to_floor": 0.0
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
        "fz_N": -1.7158148320932423e-10,
        "components_N": {
          "landing_pad": -1.7158148320932423e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -1.7158148320932423e-10,
        "components_N": {
          "landing_pad": -1.7158148320932423e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silica": {
        "fz_N": -1.7158148320932423e-10,
        "components_N": {
          "landing_pad": -1.7158148320932423e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.3275764839836856,
        "spider_to_rib": 0.0,
        "tooth_to_floor": 0.0
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
        "fz_N": -1.7158148320932423e-10,
        "components_N": {
          "landing_pad": -1.7158148320932423e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -1.7158148320932423e-10,
        "components_N": {
          "landing_pad": -1.7158148320932423e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silica": {
        "fz_N": -1.7158148320932423e-10,
        "components_N": {
          "landing_pad": -1.7158148320932423e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.0,
        "spider_to_rib": 0.1791871365380844,
        "tooth_to_floor": 0.10079276430267249
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
        "fz_N": -5.8540306750504225e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -4.71271568838843e-15,
          "tooth_to_floor": -1.141314986661992e-15
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -3.222715844995402e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -2.6236904672567577e-15,
          "tooth_to_floor": -5.990253777386447e-16
        }
      },
      "hybrid_silica": {
        "fz_N": -2.003592611961192e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -1.6373593715301755e-15,
          "tooth_to_floor": -3.662332404310165e-16
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.03023782929080175,
        "spider_to_rib": 0.1254309955766591,
        "tooth_to_floor": 0.07055493501187074
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
        "fz_N": -1.5842388579256313e-11,
        "components_N": {
          "landing_pad": -1.5838290757783777e-11,
          "spider_to_rib": -3.2989009818719017e-15,
          "tooth_to_floor": -7.989204906633942e-16
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -1.5840546658875274e-11,
        "components_N": {
          "landing_pad": -1.5838290757783777e-11,
          "spider_to_rib": -1.8365833270797306e-15,
          "tooth_to_floor": -4.1931776441705125e-16
        }
      },
      "hybrid_silica": {
        "fz_N": -1.583969327261215e-11,
        "components_N": {
          "landing_pad": -1.5838290757783777e-11,
          "spider_to_rib": -1.1461515600711231e-15,
          "tooth_to_floor": -2.5636326830171154e-16
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.10079276430267249,
        "spider_to_rib": 0.0,
        "tooth_to_floor": 0.0
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
        "fz_N": -5.279430252594592e-11,
        "components_N": {
          "landing_pad": -5.279430252594592e-11,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -5.279430252594592e-11,
        "components_N": {
          "landing_pad": -5.279430252594592e-11,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silica": {
        "fz_N": -5.279430252594592e-11,
        "components_N": {
          "landing_pad": -5.279430252594592e-11,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.10079276430267249,
        "spider_to_rib": 0.0,
        "tooth_to_floor": 0.0
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
        "fz_N": -5.279430252594592e-11,
        "components_N": {
          "landing_pad": -5.279430252594592e-11,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -5.279430252594592e-11,
        "components_N": {
          "landing_pad": -5.279430252594592e-11,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silica": {
        "fz_N": -5.279430252594592e-11,
        "components_N": {
          "landing_pad": -5.279430252594592e-11,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.0,
        "spider_to_rib": 0.32672563597333876,
        "tooth_to_floor": 0.31038935417467156
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
        "fz_N": -1.2107712886844523e-14,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -8.593055618827748e-15,
          "tooth_to_floor": -3.5146572680167744e-15
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -6.6286628463926844e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -4.783975864972068e-15,
          "tooth_to_floor": -1.8446869814206168e-15
        }
      },
      "hybrid_silica": {
        "fz_N": -4.113330931608307e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -2.9855228021147656e-15,
          "tooth_to_floor": -1.127808129493541e-15
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.0,
        "spider_to_rib": 0.32672563597333876,
        "tooth_to_floor": 0.31038935417467156
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
        "fz_N": -1.2107712886844523e-14,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -8.593055618827748e-15,
          "tooth_to_floor": -3.5146572680167744e-15
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -6.6286628463926844e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -4.783975864972068e-15,
          "tooth_to_floor": -1.8446869814206168e-15
        }
      },
      "hybrid_silica": {
        "fz_N": -4.113330931608307e-15,
        "components_N": {
          "landing_pad": -0.0,
          "spider_to_rib": -2.9855228021147656e-15,
          "tooth_to_floor": -1.127808129493541e-15
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.15519467708733578,
        "spider_to_rib": 0.16336281798666938,
        "tooth_to_floor": 0.15519467708733578
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
        "fz_N": -8.129556694054926e-11,
        "components_N": {
          "landing_pad": -8.128951308410585e-11,
          "spider_to_rib": -4.296527809413874e-15,
          "tooth_to_floor": -1.7573286340083872e-15
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -8.129282741552904e-11,
        "components_N": {
          "landing_pad": -8.128951308410585e-11,
          "spider_to_rib": -2.391987932486034e-15,
          "tooth_to_floor": -9.223434907103084e-16
        }
      },
      "hybrid_silica": {
        "fz_N": -8.129156974957165e-11,
        "components_N": {
          "landing_pad": -8.128951308410585e-11,
          "spider_to_rib": -1.4927614010573828e-15,
          "tooth_to_floor": -5.639040647467705e-16
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.31038935417467156,
        "spider_to_rib": 0.0,
        "tooth_to_floor": 0.0
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
        "fz_N": -1.625790261682117e-10,
        "components_N": {
          "landing_pad": -1.625790261682117e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -1.625790261682117e-10,
        "components_N": {
          "landing_pad": -1.625790261682117e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silica": {
        "fz_N": -1.625790261682117e-10,
        "components_N": {
          "landing_pad": -1.625790261682117e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
        }
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "quadrature": {
        "gauss_legendre": 128,
        "gauss_laguerre": 96
      },
      "areas_um2": {
        "landing_pad": 0.31038935417467156,
        "spider_to_rib": 0.0,
        "tooth_to_floor": 0.0
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
        "fz_N": -1.625790261682117e-10,
        "components_N": {
          "landing_pad": -1.625790261682117e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silicon_nitride": {
        "fz_N": -1.625790261682117e-10,
        "components_N": {
          "landing_pad": -1.625790261682117e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "hybrid_silica": {
        "fz_N": -1.625790261682117e-10,
        "components_N": {
          "landing_pad": -1.625790261682117e-10,
          "spider_to_rib": -0.0,
          "tooth_to_floor": -0.0
        }
      },
      "contrast_weights": {
        "silicon_nitride": {
          "spider": 0.5567258117694682,
          "foundation": 0.5248554384540384
        },
        "silica": {
          "spider": 0.34743436264666544,
          "foundation": 0.3208870861339867
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
      "fz_N": 3.8066220764340566e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 5.625912904808796e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 4.648852498598184e-13,
      "active_N": 5.625912904808796e-13,
      "spider_N": -5.930703520687806e-15,
      "foundation_N": -2.7045689661995624e-14,
      "nonadditive_residual_N": -6.472964743837772e-14,
      "gold_active_N": 5.625912904808796e-13,
      "gold_spider_N": -1.065282657155408e-14,
      "gold_foundation_N": -5.1529788357835633e-14,
      "gold_nonadditive_residual_N": -1.1974646790808422e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 5.023719035800776e-13,
      "active_N": 5.625912904808796e-13,
      "spider_N": -3.701158010273354e-15,
      "foundation_N": -1.6535243635246907e-14,
      "nonadditive_residual_N": -3.99829852552817e-14,
      "gold_active_N": 5.625912904808796e-13,
      "gold_spider_N": -1.065282657155408e-14,
      "gold_foundation_N": -5.1529788357835633e-14,
      "gold_nonadditive_residual_N": -1.1974646790808422e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 1.1775233642123173e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 1.2376535271138745e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 1.2055418596906246e-12,
      "active_N": 1.2376535271138745e-12,
      "spider_N": -1.0132562428087904e-15,
      "foundation_N": -1.4089559161055864e-14,
      "nonadditive_residual_N": -1.700885201938522e-14,
      "gold_active_N": 1.2376535271138745e-12,
      "gold_spider_N": -1.8200274199400057e-15,
      "gold_foundation_N": -2.6844647361484256e-14,
      "gold_nonadditive_residual_N": -3.146548812013291e-14,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 1.217900854589768e-12,
      "active_N": 1.2376535271138745e-12,
      "spider_N": -6.323400666463108e-16,
      "foundation_N": -8.614100670121097e-15,
      "nonadditive_residual_N": -1.0506231787339264e-14,
      "gold_active_N": 1.2376535271138745e-12,
      "gold_spider_N": -1.8200274199400057e-15,
      "gold_foundation_N": -2.6844647361484256e-14,
      "gold_nonadditive_residual_N": -3.146548812013291e-14,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.431288400552545e-14,
      "landing_pad": -0.0,
      "spider_to_rib": -1.0603610298873974e-14,
      "tooth_to_floor": -3.7092737066514745e-15
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -7.850136028978302e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -5.903303551327707e-15,
      "tooth_to_floor": -1.946832477650595e-15
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -4.8743166173437e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -3.684058585942897e-15,
      "tooth_to_floor": -1.1902580314008037e-15
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -9.496844964356408e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -5.587978064167808e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -7.687418062975999e-13,
      "active_N": -5.587978064167808e-13,
      "spider_N": -4.9292245282149e-15,
      "foundation_N": -4.998498846911593e-14,
      "nonadditive_residual_N": -1.5502978688348824e-13,
      "gold_active_N": -5.587978064167808e-13,
      "gold_spider_N": -8.853953641107658e-15,
      "gold_foundation_N": -9.523572551014563e-14,
      "gold_nonadditive_residual_N": -2.8679701086760666e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -6.881945474195318e-13,
      "active_N": -5.587978064167808e-13,
      "spider_N": -3.076167740201362e-15,
      "foundation_N": -3.055991445480681e-14,
      "nonadditive_residual_N": -9.576065880774286e-14,
      "gold_active_N": -5.587978064167808e-13,
      "gold_spider_N": -8.853953641107658e-15,
      "gold_foundation_N": -9.523572551014563e-14,
      "gold_nonadditive_residual_N": -2.8679701086760666e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -4.961084003597056e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -3.87153657381211e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -4.459632314793489e-13,
      "active_N": -3.87153657381211e-13,
      "spider_N": -9.439307856317518e-16,
      "foundation_N": -3.809634245894301e-15,
      "nonadditive_residual_N": -5.405600906661187e-14,
      "gold_active_N": -3.87153657381211e-13,
      "gold_spider_N": -1.6955039009806489e-15,
      "gold_foundation_N": -7.258444834096753e-15,
      "gold_nonadditive_residual_N": -1.000007942434172e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -4.2346183915471317e-13,
      "active_N": -3.87153657381211e-13,
      "spider_N": -5.890763172021467e-16,
      "foundation_N": -2.3291412126775955e-15,
      "nonadditive_residual_N": -3.33899642436224e-14,
      "gold_active_N": -3.87153657381211e-13,
      "gold_spider_N": -1.6955039009806489e-15,
      "gold_foundation_N": -7.258444834096753e-15,
      "gold_nonadditive_residual_N": -1.000007942434172e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -5.148446398160115e-11,
      "landing_pad": -5.147444496279728e-11,
      "spider_to_rib": -7.422527209211784e-15,
      "tooth_to_floor": -2.5964915946560316e-15
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -5.1479940058017567e-11,
      "landing_pad": -5.147444496279728e-11,
      "spider_to_rib": -4.1323124859293955e-15,
      "tooth_to_floor": -1.3627827343554166e-15
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 18.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -5.147785698442942e-11,
      "landing_pad": -5.147444496279728e-11,
      "spider_to_rib": -2.5788410101600284e-15,
      "tooth_to_floor": -8.331806219805624e-16
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -4.332302261101349e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -3.611829866374616e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -3.999408352208288e-12,
      "active_N": -3.611829866374616e-12,
      "spider_N": -5.574523358712034e-15,
      "foundation_N": -6.81612879786489e-14,
      "nonadditive_residual_N": -3.1384267449631055e-13,
      "gold_active_N": -3.611829866374616e-12,
      "gold_spider_N": -1.0013049944629405e-14,
      "gold_foundation_N": -1.2986678423189815e-13,
      "gold_nonadditive_residual_N": -5.805925605502056e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -3.850839426641621e-12,
      "active_N": -3.611829866374616e-12,
      "spider_N": -3.4788776256615457e-15,
      "foundation_N": -4.167257397776497e-14,
      "nonadditive_residual_N": -1.938581086635786e-13,
      "gold_active_N": -3.611829866374616e-12,
      "gold_spider_N": -1.0013049944629405e-14,
      "gold_foundation_N": -1.2986678423189815e-13,
      "gold_nonadditive_residual_N": -5.805925605502056e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -5.412691482859154e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -5.287121872368014e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -5.3557715164874794e-12,
      "active_N": -5.287121872368014e-12,
      "spider_N": -9.720170809650383e-16,
      "foundation_N": 2.4872601939601938e-14,
      "nonadditive_residual_N": -9.255022897810195e-14,
      "gold_active_N": -5.287121872368014e-12,
      "gold_spider_N": -1.7459529635883596e-15,
      "gold_foundation_N": 4.7389433579776145e-14,
      "gold_nonadditive_residual_N": -1.7121309110732718e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -5.329689355019922e-12,
      "active_N": -5.287121872368014e-12,
      "spider_N": -6.066040551153784e-16,
      "foundation_N": 1.520665725495447e-14,
      "nonadditive_residual_N": -5.716753585174691e-14,
      "gold_active_N": -5.287121872368014e-12,
      "gold_spider_N": -1.7459529635883596e-15,
      "gold_foundation_N": 4.7389433579776145e-14,
      "gold_nonadditive_residual_N": -1.7121309110732718e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.7158148320932423e-10,
      "landing_pad": -1.7158148320932423e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.7158148320932423e-10,
      "landing_pad": -1.7158148320932423e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 36.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.7158148320932423e-10,
      "landing_pad": -1.7158148320932423e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -6.77156974820437e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -4.853539518848715e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -5.889312549062466e-12,
      "active_N": -4.853539518848715e-12,
      "spider_N": -7.680660372622435e-15,
      "foundation_N": -4.186757417445735e-14,
      "nonadditive_residual_N": -9.862247956666711e-13,
      "gold_active_N": -4.853539518848715e-12,
      "gold_spider_N": -1.3796127663293761e-14,
      "gold_foundation_N": -7.976972535100005e-14,
      "gold_nonadditive_residual_N": -1.8244643763413608e-12,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -5.4931130069008204e-12,
      "active_N": -4.853539518848715e-12,
      "spider_N": -4.793248821688497e-15,
      "foundation_N": -2.5597074729590815e-14,
      "nonadditive_residual_N": -6.09183164500826e-13,
      "gold_active_N": -4.853539518848715e-12,
      "gold_spider_N": -1.3796127663293761e-14,
      "gold_foundation_N": -7.976972535100005e-14,
      "gold_nonadditive_residual_N": -1.8244643763413608e-12,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -6.793755377465048e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -6.764514870992626e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -6.780034907127235e-12,
      "active_N": -6.764514870992626e-12,
      "spider_N": -7.408956340381938e-16,
      "foundation_N": -1.0283199186523938e-14,
      "nonadditive_residual_N": -4.495941314045707e-15,
      "gold_active_N": -6.764514870992626e-12,
      "gold_spider_N": -1.3308088440939533e-15,
      "gold_foundation_N": -1.9592440952527995e-14,
      "gold_nonadditive_residual_N": -8.317256675799642e-15,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -6.774041307975798e-12,
      "active_N": -6.764514870992626e-12,
      "spider_N": -4.623687225523282e-16,
      "foundation_N": -6.286961287508899e-15,
      "nonadditive_residual_N": -2.7771069731104746e-15,
      "gold_active_N": -6.764514870992626e-12,
      "gold_spider_N": -1.3308088440939533e-15,
      "gold_foundation_N": -1.9592440952527995e-14,
      "gold_nonadditive_residual_N": -8.317256675799642e-15,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.7158148320932423e-10,
      "landing_pad": -1.7158148320932423e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.7158148320932423e-10,
      "landing_pad": -1.7158148320932423e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C4_TightSlot_N2",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.7158148320932423e-10,
      "landing_pad": -1.7158148320932423e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 6.779978736669609e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 8.69151249400552e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 7.664175502525391e-13,
      "active_N": 8.69151249400552e-13,
      "spider_N": -3.820670602458601e-15,
      "foundation_N": -2.3612508098319988e-14,
      "nonadditive_residual_N": -7.530052044723439e-14,
      "gold_active_N": 8.69151249400552e-13,
      "gold_spider_N": -6.8627509658932126e-15,
      "gold_foundation_N": -4.4988593750444175e-14,
      "gold_nonadditive_residual_N": -1.3930203101725375e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 8.058181062102668e-13,
      "active_N": 8.69151249400552e-13,
      "spider_N": -2.384355507837896e-15,
      "foundation_N": -1.4436258757845717e-14,
      "nonadditive_residual_N": -4.6512528924601654e-14,
      "gold_active_N": 8.69151249400552e-13,
      "gold_spider_N": -6.8627509658932126e-15,
      "gold_foundation_N": -4.4988593750444175e-14,
      "gold_nonadditive_residual_N": -1.3930203101725375e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 1.5587605428432081e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 1.6171233981917287e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 1.5858151887156187e-12,
      "active_N": 1.6171233981917287e-12,
      "spider_N": -5.386390759375106e-16,
      "foundation_N": -8.551772945174557e-15,
      "nonadditive_residual_N": -2.2217797454997825e-14,
      "gold_active_N": 1.6171233981917287e-12,
      "gold_spider_N": -9.67512309561377e-16,
      "gold_foundation_N": -1.6293577847576093e-14,
      "gold_nonadditive_residual_N": -4.1101765191383084e-14,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 1.5978350967500231e-12,
      "active_N": 1.6171233981917287e-12,
      "spider_N": -3.3614702262526026e-16,
      "foundation_N": -5.2283987182059676e-15,
      "nonadditive_residual_N": -1.3723755700874201e-14,
      "gold_active_N": 1.6171233981917287e-12,
      "gold_spider_N": -9.67512309561377e-16,
      "gold_foundation_N": -1.6293577847576093e-14,
      "gold_nonadditive_residual_N": -4.1101765191383084e-14,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -5.8540306750504225e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -4.71271568838843e-15,
      "tooth_to_floor": -1.141314986661992e-15
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -3.222715844995402e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -2.6236904672567577e-15,
      "tooth_to_floor": -5.990253777386447e-16
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -2.003592611961192e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -1.6373593715301755e-15,
      "tooth_to_floor": -3.662332404310165e-16
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -5.431087494888064e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -8.746257653481406e-14,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -3.3248105471436173e-13,
      "active_N": -8.746257653481406e-14,
      "spider_N": -3.0713672720417e-15,
      "foundation_N": -4.5895704560463474e-14,
      "nonadditive_residual_N": -1.960514063470425e-13,
      "gold_active_N": -8.746257653481406e-14,
      "gold_spider_N": -5.516840080182068e-15,
      "gold_foundation_N": -8.744446793892289e-14,
      "gold_nonadditive_residual_N": -3.626848649348874e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -2.385385017622498e-13,
      "active_N": -8.746257653481406e-14,
      "spider_N": -1.9167398170816356e-15,
      "foundation_N": -2.8059800515457787e-14,
      "nonadditive_residual_N": -1.210993848948963e-13,
      "gold_active_N": -8.746257653481406e-14,
      "gold_spider_N": -5.516840080182068e-15,
      "gold_foundation_N": -8.744446793892289e-14,
      "gold_nonadditive_residual_N": -3.626848649348874e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 1.6127645486203573e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 3.4626770180900713e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 2.462043346099419e-13,
      "active_N": 3.4626770180900713e-13,
      "spider_N": -5.180389134903105e-16,
      "foundation_N": 1.6791595592118297e-15,
      "nonadditive_residual_N": -1.0122448784478677e-13,
      "gold_active_N": 3.4626770180900713e-13,
      "gold_spider_N": -9.305099611670647e-16,
      "gold_foundation_N": 3.1992800992170226e-15,
      "gold_nonadditive_residual_N": -1.8726001708502135e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 2.844454622003008e-13,
      "active_N": 3.4626770180900713e-13,
      "spider_N": -3.2329113529445255e-16,
      "foundation_N": 1.0266076687642022e-15,
      "nonadditive_residual_N": -6.252555614217609e-14,
      "gold_active_N": 3.4626770180900713e-13,
      "gold_spider_N": -9.305099611670647e-16,
      "gold_foundation_N": 3.1992800992170226e-15,
      "gold_nonadditive_residual_N": -1.8726001708502135e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.5842388579256313e-11,
      "landing_pad": -1.5838290757783777e-11,
      "spider_to_rib": -3.2989009818719017e-15,
      "tooth_to_floor": -7.989204906633942e-16
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.5840546658875274e-11,
      "landing_pad": -1.5838290757783777e-11,
      "spider_to_rib": -1.8365833270797306e-15,
      "tooth_to_floor": -4.1931776441705125e-16
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 18.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.583969327261215e-11,
      "landing_pad": -1.5838290757783777e-11,
      "spider_to_rib": -1.1461515600711231e-15,
      "tooth_to_floor": -2.5636326830171154e-16
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -3.932082774619848e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -3.2376766887440006e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -3.6109934823885947e-12,
      "active_N": -3.2376766887440006e-12,
      "spider_N": -3.2275653206467154e-15,
      "foundation_N": -7.161224372531834e-14,
      "nonadditive_residual_N": -2.984769845986289e-13,
      "gold_active_N": -3.2376766887440006e-12,
      "gold_spider_N": -5.7974055673624874e-15,
      "gold_foundation_N": -1.3644184375082822e-13,
      "gold_nonadditive_residual_N": -5.52166836557657e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -3.467840177290466e-12,
      "active_N": -3.2376766887440006e-12,
      "spider_N": -2.0142179083008155e-15,
      "foundation_N": -4.378242566795197e-14,
      "nonadditive_residual_N": -1.843668449702129e-13,
      "gold_active_N": -3.2376766887440006e-12,
      "gold_spider_N": -5.7974055673624874e-15,
      "gold_foundation_N": -1.3644184375082822e-13,
      "gold_nonadditive_residual_N": -5.52166836557657e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -4.6707805541356574e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -4.379914454948566e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -4.537811249996854e-12,
      "active_N": -4.379914454948566e-12,
      "spider_N": -5.107791164711429e-16,
      "foundation_N": 2.1816216927987824e-14,
      "nonadditive_residual_N": -1.7920223285980473e-13,
      "gold_active_N": -4.379914454948566e-12,
      "gold_spider_N": -9.174697951361538e-16,
      "gold_foundation_N": 4.156614436967156e-14,
      "gold_nonadditive_residual_N": -3.315147737616266e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -4.477586961792594e-12,
      "active_N": -4.379914454948566e-12,
      "spider_N": -3.187605335206963e-16,
      "foundation_N": 1.3338038948608525e-14,
      "nonadditive_residual_N": -1.1069178525911501e-13,
      "gold_active_N": -4.379914454948566e-12,
      "gold_spider_N": -9.174697951361538e-16,
      "gold_foundation_N": 4.156614436967156e-14,
      "gold_nonadditive_residual_N": -3.315147737616266e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -5.279430252594592e-11,
      "landing_pad": -5.279430252594592e-11,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -5.279430252594592e-11,
      "landing_pad": -5.279430252594592e-11,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 36.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -5.279430252594592e-11,
      "landing_pad": -5.279430252594592e-11,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -6.387259138340825e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -4.4396633866961004e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -5.491308252723749e-12,
      "active_N": -4.4396633866961004e-12,
      "spider_N": -4.248386572991806e-15,
      "foundation_N": -4.2211523911965074e-14,
      "nonadditive_residual_N": -1.0051849555426917e-12,
      "gold_active_N": -4.4396633866961004e-12,
      "gold_spider_N": -7.63102138104385e-15,
      "gold_foundation_N": -8.042504815478165e-14,
      "gold_nonadditive_residual_N": -1.859539682108899e-12,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -5.089016728637361e-12,
      "active_N": -4.4396633866961004e-12,
      "spider_N": -2.6512790498660464e-15,
      "foundation_N": -2.580735935457345e-14,
      "nonadditive_residual_N": -6.208947035368204e-13,
      "gold_active_N": -4.4396633866961004e-12,
      "gold_spider_N": -7.63102138104385e-15,
      "gold_foundation_N": -8.042504815478165e-14,
      "gold_nonadditive_residual_N": -1.859539682108899e-12,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -6.382254890142974e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -5.616027211148983e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -6.030078405191841e-12,
      "active_N": -5.616027211148983e-12,
      "spider_N": -4.3890395642788357e-16,
      "foundation_N": -5.0267236481458115e-15,
      "nonadditive_residual_N": -4.0858556643828444e-13,
      "gold_active_N": -5.616027211148983e-12,
      "gold_spider_N": -7.883664582263469e-16,
      "gold_foundation_N": -9.577348884774874e-15,
      "gold_nonadditive_residual_N": -7.558619636509898e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -5.871754399205848e-12,
      "active_N": -5.616027211148983e-12,
      "spider_N": -2.739055979458798e-16,
      "foundation_N": -3.0732475765239965e-15,
      "nonadditive_residual_N": -2.523800348823942e-13,
      "gold_active_N": -5.616027211148983e-12,
      "gold_spider_N": -7.883664582263469e-16,
      "gold_foundation_N": -9.577348884774874e-15,
      "gold_nonadditive_residual_N": -7.558619636509898e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -5.279430252594592e-11,
      "landing_pad": -5.279430252594592e-11,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -5.279430252594592e-11,
      "landing_pad": -5.279430252594592e-11,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C8_Compact_N2",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -5.279430252594592e-11,
      "landing_pad": -5.279430252594592e-11,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 2.903205374242642e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 3.1150630312915713e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 3.0011960348153937e-12,
      "active_N": 3.1150630312915713e-12,
      "spider_N": -5.604612972151107e-15,
      "foundation_N": -2.730099730579659e-14,
      "nonadditive_residual_N": -8.096138619822973e-14,
      "gold_active_N": 3.1150630312915713e-12,
      "gold_spider_N": -1.0067097399952946e-14,
      "gold_foundation_N": -5.201622257399423e-14,
      "gold_nonadditive_residual_N": -1.49774337074982e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 3.044864841228574e-12,
      "active_N": 3.1150630312915713e-12,
      "spider_N": -3.4976555688545548e-15,
      "foundation_N": -1.6691334093465908e-14,
      "nonadditive_residual_N": -5.00092004006768e-14,
      "gold_active_N": 3.1150630312915713e-12,
      "gold_spider_N": -1.0067097399952946e-14,
      "gold_foundation_N": -5.201622257399423e-14,
      "gold_nonadditive_residual_N": -1.49774337074982e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 4.6775106956361694e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 4.757038726255885e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 4.714513686333197e-12,
      "active_N": 4.757038726255885e-12,
      "spider_N": -9.48986528623289e-16,
      "foundation_N": -1.6442684625845942e-14,
      "nonadditive_residual_N": -2.513336876821893e-14,
      "gold_active_N": 4.757038726255885e-12,
      "gold_spider_N": -1.7045851091528877e-15,
      "gold_foundation_N": -3.1328025626023555e-14,
      "gold_nonadditive_residual_N": -4.6495419884539436e-14,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 4.73086905518683e-12,
      "active_N": 4.757038726255885e-12,
      "spider_N": -5.922314409755301e-16,
      "foundation_N": -1.0052758857465563e-14,
      "nonadditive_residual_N": -1.5524680770614754e-14,
      "gold_active_N": 4.757038726255885e-12,
      "gold_spider_N": -1.7045851091528877e-15,
      "gold_foundation_N": -3.1328025626023555e-14,
      "gold_nonadditive_residual_N": -4.6495419884539436e-14,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.2107712886844523e-14,
      "landing_pad": -0.0,
      "spider_to_rib": -8.593055618827748e-15,
      "tooth_to_floor": -3.5146572680167744e-15
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -6.6286628463926844e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -4.783975864972068e-15,
      "tooth_to_floor": -1.8446869814206168e-15
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 0.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -4.113330931608307e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -2.9855228021147656e-15,
      "tooth_to_floor": -1.127808129493541e-15
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 4.803160174542853e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 5.00793030572078e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 4.897895402450848e-12,
      "active_N": 5.00793030572078e-12,
      "spider_N": -5.567002521291688e-15,
      "foundation_N": -2.729423178011628e-14,
      "nonadditive_residual_N": -7.717366896852458e-14,
      "gold_active_N": 5.00793030572078e-12,
      "gold_spider_N": -9.999540893564497e-15,
      "gold_foundation_N": -5.2003332309009576e-14,
      "gold_nonadditive_residual_N": -1.427672579753534e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 4.940099366052523e-12,
      "active_N": 5.00793030572078e-12,
      "spider_N": -3.4741841171148486e-15,
      "foundation_N": -1.668719777389549e-14,
      "nonadditive_residual_N": -4.7669557777245987e-14,
      "gold_active_N": 5.00793030572078e-12,
      "gold_spider_N": -9.999540893564497e-15,
      "gold_foundation_N": -5.2003332309009576e-14,
      "gold_nonadditive_residual_N": -1.427672579753534e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 8.38725212049833e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 8.458942196154191e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 8.420638052414264e-12,
      "active_N": 8.458942196154191e-12,
      "spider_N": -9.461071047591277e-16,
      "foundation_N": -1.590649371395765e-14,
      "nonadditive_residual_N": -2.145154292120878e-14,
      "gold_active_N": 8.458942196154191e-12,
      "gold_spider_N": -1.6994130409582956e-15,
      "gold_foundation_N": -3.030642830111511e-14,
      "gold_nonadditive_residual_N": -3.968423431378723e-14,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 8.435376373791828e-12,
      "active_N": 8.458942196154191e-12,
      "spider_N": -5.90434486758777e-16,
      "foundation_N": -9.724941468673417e-15,
      "nonadditive_residual_N": -1.3250446406930549e-14,
      "gold_active_N": 8.458942196154191e-12,
      "gold_spider_N": -1.6994130409582956e-15,
      "gold_foundation_N": -3.030642830111511e-14,
      "gold_nonadditive_residual_N": -3.968423431378723e-14,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.2107712886844523e-14,
      "landing_pad": -0.0,
      "spider_to_rib": -8.593055618827748e-15,
      "tooth_to_floor": -3.5146572680167744e-15
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -6.6286628463926844e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -4.783975864972068e-15,
      "tooth_to_floor": -1.8446869814206168e-15
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 3.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -4.113330931608307e-15,
      "landing_pad": -0.0,
      "spider_to_rib": -2.9855228021147656e-15,
      "tooth_to_floor": -1.127808129493541e-15
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -5.373504834431514e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 6.094373984516655e-13,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -8.996413069219624e-15,
      "active_N": 6.094373984516655e-13,
      "spider_N": -5.147182653571674e-15,
      "foundation_N": -5.4106527263390284e-14,
      "nonadditive_residual_N": -5.591801016039232e-13,
      "gold_active_N": 6.094373984516655e-13,
      "gold_spider_N": -9.245453587309231e-15,
      "gold_foundation_N": -1.0308843788064967e-13,
      "gold_nonadditive_residual_N": -1.0344539904268578e-12,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 2.27744387536595e-13,
      "active_N": 6.094373984516655e-13,
      "spider_N": -3.2121882744861093e-15,
      "foundation_N": -3.3079748445626166e-14,
      "nonadditive_residual_N": -3.4540107419495817e-13,
      "gold_active_N": 6.094373984516655e-13,
      "gold_spider_N": -9.245453587309231e-15,
      "gold_foundation_N": -1.0308843788064967e-13,
      "gold_nonadditive_residual_N": -1.0344539904268578e-12,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": 1.866991915006756e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": 3.5624287590713593e-12,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": 2.6460271759694793e-12,
      "active_N": 3.5624287590713593e-12,
      "spider_N": -8.39795478539216e-16,
      "foundation_N": -3.377173828193667e-15,
      "nonadditive_residual_N": -9.121846137951474e-13,
      "gold_active_N": 3.5624287590713593e-12,
      "gold_spider_N": -1.5084543608101336e-15,
      "gold_foundation_N": -6.434483823090664e-15,
      "gold_nonadditive_residual_N": -1.6874939058807024e-12,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": 2.9963907907979654e-12,
      "active_N": 3.5624287590713593e-12,
      "spider_N": -5.240888794296519e-16,
      "foundation_N": -2.064742764767838e-15,
      "nonadditive_residual_N": -5.634491366291966e-13,
      "gold_active_N": 3.5624287590713593e-12,
      "gold_spider_N": -1.5084543608101336e-15,
      "gold_foundation_N": -6.434483823090664e-15,
      "gold_nonadditive_residual_N": -1.6874939058807024e-12,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -8.129556694054926e-11,
      "landing_pad": -8.128951308410585e-11,
      "spider_to_rib": -4.296527809413874e-15,
      "tooth_to_floor": -1.7573286340083872e-15
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -8.129282741552904e-11,
      "landing_pad": -8.128951308410585e-11,
      "spider_to_rib": -2.391987932486034e-15,
      "tooth_to_floor": -9.223434907103084e-16
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 21.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -8.129156974957165e-11,
      "landing_pad": -8.128951308410585e-11,
      "spider_to_rib": -1.4927614010573828e-15,
      "tooth_to_floor": -5.639040647467705e-16
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -1.1025989867278876e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -1.0474387445792478e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.0770114753816778e-11,
      "active_N": -1.0474387445792478e-11,
      "spider_N": -4.551205884709971e-15,
      "foundation_N": -8.614010699126606e-14,
      "nonadditive_residual_N": -2.0503599514832465e-13,
      "gold_active_N": -1.0474387445792478e-11,
      "gold_spider_N": -8.174950376819527e-15,
      "gold_foundation_N": -1.64121586021842e-13,
      "gold_nonadditive_residual_N": -3.7930588508773613e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.0656541295479216e-11,
      "active_N": -1.0474387445792478e-11,
      "spider_N": -2.8402586738384098e-15,
      "foundation_N": -5.266449751023732e-14,
      "nonadditive_residual_N": -1.2664909350266247e-13,
      "gold_active_N": -1.0474387445792478e-11,
      "gold_spider_N": -8.174950376819527e-15,
      "gold_foundation_N": -1.64121586021842e-13,
      "gold_nonadditive_residual_N": -3.7930588508773613e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -1.1641419592141825e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -1.1437027142639803e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.1547931413283006e-11,
      "active_N": -1.1437027142639803e-11,
      "spider_N": -1.122976583926869e-15,
      "foundation_N": 1.290815514163629e-14,
      "nonadditive_residual_N": -1.22689449200915e-13,
      "gold_active_N": -1.1437027142639803e-11,
      "gold_spider_N": -2.0171088894866554e-15,
      "gold_foundation_N": 2.4593734190231998e-14,
      "gold_nonadditive_residual_N": -2.2696907480276717e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.1505620434888736e-11,
      "active_N": -1.1437027142639803e-11,
      "spider_N": -7.008129414077192e-16,
      "foundation_N": 7.891811701457348e-15,
      "nonadditive_residual_N": -7.578429100898192e-14,
      "gold_active_N": -1.1437027142639803e-11,
      "gold_spider_N": -2.0171088894866554e-15,
      "gold_foundation_N": 2.4593734190231998e-14,
      "gold_nonadditive_residual_N": -2.2696907480276717e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.625790261682117e-10,
      "landing_pad": -1.625790261682117e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.625790261682117e-10,
      "landing_pad": -1.625790261682117e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 30.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.625790261682117e-10,
      "landing_pad": -1.625790261682117e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -1.2869670484299065e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -1.0352276821972144e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.171218077760602e-11,
      "active_N": -1.0352276821972144e-11,
      "spider_N": -1.0651122681286229e-14,
      "foundation_N": -4.001991128761816e-14,
      "nonadditive_residual_N": -1.3092329216649713e-12,
      "gold_active_N": -1.0352276821972144e-11,
      "gold_spider_N": -1.9131720599469345e-14,
      "gold_foundation_N": -7.624939813045818e-14,
      "gold_nonadditive_residual_N": -2.4220125435969935e-12,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "vector_dyadic",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.119209398552564e-11,
      "active_N": -1.0352276821972144e-11,
      "spider_N": -6.647017152810712e-15,
      "foundation_N": -2.446744718555298e-14,
      "nonadditive_residual_N": -8.087026992151322e-13,
      "gold_active_N": -1.0352276821972144e-11,
      "gold_spider_N": -1.9131720599469345e-14,
      "gold_foundation_N": -7.624939813045818e-14,
      "gold_nonadditive_residual_N": -2.4220125435969935e-12,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_full",
      "fz_N": -1.15888228094091e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "homogeneous BEM",
      "stack": "all_gold_isolated",
      "fz_N": -1.1430022652804102e-11,
      "status": "ok"
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.1515494943103e-11,
      "active_N": -1.1430022652804102e-11,
      "spider_N": -8.412519326166667e-16,
      "foundation_N": -1.312071841355063e-14,
      "nonadditive_residual_N": -7.151031995273081e-14,
      "gold_active_N": -1.1430022652804102e-11,
      "gold_spider_N": -1.51107046742251e-15,
      "gold_foundation_N": -2.499872813016419e-14,
      "gold_nonadditive_residual_N": -1.322903580074115e-13,
      "weighting": {
        "spider": 0.5567258117694682,
        "foundation": 0.5248554384540384
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "scalar_yukawa",
      "model": "component-weighted BEM approximation",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.1482740772043986e-11,
      "active_N": -1.1430022652804102e-11,
      "spider_N": -5.249978047631386e-16,
      "foundation_N": -8.021769026744113e-15,
      "nonadditive_residual_N": -4.4171352408375966e-14,
      "gold_active_N": -1.1430022652804102e-11,
      "gold_spider_N": -1.51107046742251e-15,
      "gold_foundation_N": -2.499872813016419e-14,
      "gold_nonadditive_residual_N": -1.322903580074115e-13,
      "weighting": {
        "spider": 0.34743436264666544,
        "foundation": 0.3208870861339867
      }
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "all_gold",
      "status": "ok",
      "fz_N": -1.625790261682117e-10,
      "landing_pad": -1.625790261682117e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silicon_nitride",
      "status": "ok",
      "fz_N": -1.625790261682117e-10,
      "landing_pad": -1.625790261682117e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    },
    {
      "design_name": "Rot_C10_Fractal_N3",
      "theta_deg": 48.0,
      "solver": "continuum_lifshitz_pfa",
      "model": "zero-temperature projected-area Lifshitz-PFA",
      "stack": "hybrid_silica",
      "status": "ok",
      "fz_N": -1.625790261682117e-10,
      "landing_pad": -1.625790261682117e-10,
      "spider_to_rib": -0.0,
      "tooth_to_floor": -0.0
    }
  ],
  "convergence": [
    {
      "theta_deg": 0.0,
      "kernel": "vector_dyadic",
      "expected_sign": "repulsive",
      "relative_change": 0.0021066287045016737,
      "within_tolerance": true,
      "expected_sign_verified": true,
      "baseline_fz_N": 3.8066220764340566e-13,
      "refined_fz_N": 3.798602937100651e-13,
      "baseline_n_xi": 6,
      "refined_n_xi": 12,
      "observed_sign": "repulsive",
      "baseline_panels": 460,
      "refined_panels": 460
    },
    {
      "theta_deg": 0.0,
      "kernel": "scalar_yukawa",
      "expected_sign": "repulsive",
      "relative_change": 0.00020576515242738105,
      "within_tolerance": true,
      "expected_sign_verified": true,
      "baseline_fz_N": 1.1775233642123173e-12,
      "refined_fz_N": 1.1777657073526145e-12,
      "baseline_n_xi": 6,
      "refined_n_xi": 12,
      "observed_sign": "repulsive",
      "baseline_panels": 460,
      "refined_panels": 460
    },
    {
      "theta_deg": 48.0,
      "kernel": "vector_dyadic",
      "expected_sign": "attractive",
      "relative_change": 0.004111203788135054,
      "within_tolerance": true,
      "expected_sign_verified": true,
      "baseline_fz_N": -6.77156974820437e-12,
      "refined_fz_N": -6.7995239769358635e-12,
      "baseline_n_xi": 6,
      "refined_n_xi": 12,
      "observed_sign": "attractive",
      "baseline_panels": 460,
      "refined_panels": 460
    },
    {
      "theta_deg": 48.0,
      "kernel": "scalar_yukawa",
      "expected_sign": "attractive",
      "relative_change": 0.002880705259964973,
      "within_tolerance": true,
      "expected_sign_verified": true,
      "baseline_fz_N": -6.793755377465048e-12,
      "refined_fz_N": -6.813382724918876e-12,
      "baseline_n_xi": 6,
      "refined_n_xi": 12,
      "observed_sign": "attractive",
      "baseline_panels": 460,
      "refined_panels": 460
    }
  ],
  "convergence_relative_tolerance": 0.05,
  "limitations": [
    "Part 2 specifies collars ending at R_min-0.03 and starting at R_max+0.03; part 3 explicitly occupies collars through R_min and from R_max. The mesh follows the explicit part-3 occupancy.",
    "Surviving Cantor ring ribs extend to z=0 in the landing-pad sector to provide pedestal clamps. Connectivity and rotor clearance are audited on the full geometry.",
    "An actuator ring is specified, but comb fingers, suspension, shaft bearings, drive electrodes, and electrical routing are not. Their mechanics and actuation are not verified by this script.",
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
    "run_id": "real_world_nems_clutch_1792033661797315000",
    "script": "C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\execution\\run_real_world_nems_clutch.py",
    "device": "cpu",
    "python": "3.14.0 (tags/v3.14.0:ebf955d, Oct  7 2025, 10:15:03) [MSC v.1944 64 bit (AMD64)]",
    "numpy": "2.4.6",
    "arguments": {
      "max_steps": 0,
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
    "micro_probe": false,
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
      "omega_p_inv_um": 7.283186,
      "gamma_inv_um": 0.042747,
      "note": "The specified Drude-Lorentz stack has no Lorentz poles for Au."
    },
    "hybrid_model": "component-weighted BEM approximation",
    "no_fabricated_solver_results": true,
    "sampled_angles": {
      "Rot_C4_TightSlot_N2": [
        0.0,
        18.0,
        36.0,
        48.0
      ],
      "Rot_C8_Compact_N2": [
        0.0,
        18.0,
        36.0,
        48.0
      ],
      "Rot_C10_Fractal_N3": [
        0.0,
        3.0,
        21.0,
        30.0,
        48.0
      ]
    }
  },
  "elapsed_s": 1715.5543419999958,
  "micro_probe_under_15s": null
}
```

## External SCUFF provenance

Gmsh v2.2 and .scuffgeo exports are recorded in the JSON report with SHA256 digests and triangle counts. PATH availability does not imply SCUFF execution. SCUFF's Gold material must be explicitly matched to MaterialModel before interpreting an external calculation as verification.
