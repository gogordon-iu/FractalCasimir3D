# Rotational clutch three-solver verification

Positive force denotes repulsion; negative force denotes attraction. PFA includes only the exact polar tooth–landing-pad overlap at 15 nm. It omits bridges, sidewalls, diffraction and nonlocal interactions; zero PFA in an aperture is therefore not a failed sign prediction.

Frequency and mesh resolution increase together. The ladder measures combined discretization change, not an independently isolated mesh error.

| Design | θ (deg) | State | Tier | ξ nodes | Panels | Vector DOFs | Scalar DOFs | Vector (pN) | Scalar (pN) | PFA (pN) | Vector / scalar / PFA runtime (s) | BEM signs agree | All signs agree |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| Rot_C4_TightSlot_N2 | 6 | Aperture | Standard | 2 | 1504 | 3008 | 3008 | 1.1185051 | 1.0388427 | -0 | 43.343 / 37.157 / 0.000 | True | False |

## Convergence and non-additive residual

Relative differences use the finer-tier force magnitude as denominator; a numerically zero denominator is reported as null. The signed residual (F_BEM − F_PFA)/|F_BEM| is a diagnostic, not an isolated measurement of edge diffraction: omitted surfaces and scalar/vector model differences also contribute.

```json
[
  {
    "design": "Rot_C4_TightSlot_N2",
    "theta_deg": 6.0,
    "highest_tier": "Standard",
    "comparisons": {
      "vector_dyadic": {
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      },
      "scalar_yukawa": {
        "signed_nonadditive_edge_fraction": 1.0,
        "absolute_nonadditive_edge_fraction": 1.0
      }
    }
  }
]
```

## Hybrid Multi-Scale Active-Zone vs Full-Monolithic

Imported comparison from the real-world NEMS clutch campaign; not an additional solver execution in this verification.

Source: `C:\Users\gorengor\Goren\IUB\Research\FractalCasimirEffect\Code\3Dsimulations\results\real_world_nems_clutch_report.json`
SHA256: `97e11f0ee0e8fc86dbfcd40f46891fb4bf4eb9780649c23c9e286324c84855a8`

```json
{
  "schema_version": 1,
  "verification_status": "PREPARATION FAILED",
  "complete_device_verified": false,
  "error": "RepositoryAPIError: Repository constant H_TEETH_UM=0.1; required 0.25.",
  "traceback": "Traceback (most recent call last):\n  File \"C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\execution\\run_real_world_nems_clutch.py\", line 2430, in <module>\n    raise SystemExit(main())\n                     ~~~~^^\n  File \"C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\execution\\run_real_world_nems_clutch.py\", line 2137, in main\n    designs = [get_design(name) for name in DESIGN_NAMES]\n               ~~~~~~~~~~^^^^^^\n  File \"C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\execution\\run_real_world_nems_clutch.py\", line 347, in get_design\n    repo = repository()\n  File \"C:\\Users\\gorengor\\Goren\\IUB\\Research\\FractalCasimirEffect\\Code\\3Dsimulations\\execution\\run_real_world_nems_clutch.py\", line 193, in repository\n    raise RepositoryAPIError(\n        f\"Repository constant {name}={actual!r}; required {value!r}.\"\n    )\nRepositoryAPIError: Repository constant H_TEETH_UM=0.1; required 0.25.\n",
  "elapsed_s": 2.0872878000081982
}
```

## External SCUFF provenance

Gmsh v2.2 and .scuffgeo exports are recorded in the JSON report with SHA256 digests and triangle counts. PATH availability does not imply SCUFF execution. SCUFF's Gold material must be explicitly matched to MaterialModel before interpreting an external calculation as verification.
