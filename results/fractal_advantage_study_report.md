# Optimal Fractal Advantage: grounded BEM study

- Status: **complete**
- Formulation: `vector_dyadic`
- Device: `cpu`
- Completed tasks: 37/37
- Positive vertical force denotes repulsion.
- Window widths and work are restricted to the sampled displacement interval.
- Work integrates the positive piecewise-linear force, inserting zero crossings.
- These finite-resolution results do not establish mathematical optimality.
- Area means horizontal tooth footprint; perimeter means its plan-view boundary.

## Experiment A

| Design | Disengaged (pN) | Engaged (pN) | Swing (pN) | Ratio |
|---|---:|---:|---:|---:|
| Cantor_FlatZ | 0.204373 | -0.350259 | 0.554632 | 1.71383 |
| Cantor_RZ_ScaleMatched | 0.200237 | -0.349377 | 0.549615 | 1.74482 |
| Cantor_Z_Staircase | 0.231145 | -0.294478 | 0.525623 | 1.274 |
| Ctrl_SingleWide | -0.00580473 | -0.0456744 | 0.0398696 | 4.56744e+07 |
| Ctrl_UniformPeriodic | 0.164012 | -0.326268 | 0.49028 | 1.98929 |
| Ctrl_SizeMatched_Monotonic | 0.234393 | -0.39639 | 0.630784 | 1.69113 |

## Experiment B

| Design | Peak (pN) | Window (um) | Work (fN um = aJ) | Censored |
|---|---:|---:|---:|---|
| Cantor_FlatZ | 0.204373 | 0.0760685 | 12.593 | True |
| Cantor_RZ_ScaleMatched | 0.210702 | 0.0762877 | 12.8196 | True |
| Cantor_Z_Staircase | 0.231145 | 0.0869598 | 13.8108 | True |
| Ctrl_UniformPeriodic | 0.183815 | 0.0757815 | 10.865 | True |
| Ctrl_SizeMatched_Monotonic | 0.234393 | 0.0751278 | 13.993 | True |
