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
| Cantor_FlatZ | 1.49316 | -3.10446 | 4.59762 | 2.07912 |
| Cantor_RZ_ScaleMatched | 1.65704 | -3.01001 | 4.66704 | 1.8165 |
| Cantor_Z_Staircase | 2.26483 | -2.19022 | 4.45505 | 0.967055 |
| Ctrl_SingleWide | -0.0164534 | -0.429605 | 0.413152 | 4.29605e+08 |
| Ctrl_UniformPeriodic | 1.19524 | -2.54079 | 3.73603 | 2.12577 |
| Ctrl_SizeMatched_Monotonic | 1.54632 | -3.36795 | 4.91426 | 2.17804 |

## Experiment B

| Design | Peak (pN) | Window (um) | Work (fN um = aJ) | Censored |
|---|---:|---:|---:|---|
| Cantor_FlatZ | 1.57903 | 0.0878285 | 104.105 | True |
| Cantor_RZ_ScaleMatched | 1.66762 | 0.085521 | 109.995 | True |
| Cantor_Z_Staircase | 2.26483 | 0.1 | 130.706 | True |
| Ctrl_UniformPeriodic | 1.24396 | 0.0897167 | 82.032 | True |
| Ctrl_SizeMatched_Monotonic | 1.64485 | 0.0891809 | 109.71 | True |
