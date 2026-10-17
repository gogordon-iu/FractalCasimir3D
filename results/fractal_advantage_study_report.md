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
| Cantor_FlatZ | 0.753799 | -2.00038 | 2.75418 | 2.65373 |
| Cantor_RZ_ScaleMatched | 0.758875 | -1.79509 | 2.55397 | 2.36547 |
| Cantor_Z_Staircase | 0.856782 | -1.47431 | 2.3311 | 1.72076 |
| Ctrl_SingleWide | -0.00383356 | -0.241699 | 0.237865 | 2.41699e+08 |
| Ctrl_UniformPeriodic | 0.628297 | -1.9226 | 2.5509 | 3.06002 |
| Ctrl_SizeMatched_Monotonic | 0.883106 | -2.21904 | 3.10215 | 2.51277 |

## Experiment B

| Design | Peak (pN) | Window (um) | Work (fN um = aJ) | Censored |
|---|---:|---:|---:|---|
| Cantor_FlatZ | 0.753799 | 0.0793433 | 45.8415 | True |
| Cantor_RZ_ScaleMatched | 0.758875 | 0.0798693 | 47.3765 | True |
| Cantor_Z_Staircase | 0.856782 | 0.0924051 | 51.3539 | True |
| Ctrl_UniformPeriodic | 0.658097 | 0.0799499 | 40.2652 | True |
| Ctrl_SizeMatched_Monotonic | 0.883106 | 0.0782395 | 51.9568 | True |
