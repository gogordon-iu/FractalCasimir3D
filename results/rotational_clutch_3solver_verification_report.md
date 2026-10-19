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

