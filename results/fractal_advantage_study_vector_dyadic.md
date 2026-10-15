# Optimal Fractal Advantage: grounded BEM study

- Status: **running**
- Formulation: `vector_dyadic`
- Device: `cpu`
- Completed tasks: 15/32
- Positive vertical force denotes repulsion.
- Window widths and work are restricted to the sampled displacement interval.
- Work integrates the positive piecewise-linear force, inserting zero crossings.
- These finite-resolution results do not establish mathematical optimality.
- Area means horizontal tooth footprint; perimeter means its plan-view boundary.

## Experiment A

| Design | Disengaged (pN) | Engaged (pN) | Swing (pN) | Ratio |
|---|---:|---:|---:|---:|
| Cantor_FlatZ | 0.392988 | -0.367582 | 0.76057 | 0.935354 |
| Cantor_RZ_ScaleMatched | 0.380431 | -0.355822 | 0.736253 | 0.935312 |
| Cantor_Z_Staircase | 0.34648 | -0.315406 | 0.661886 | 0.910317 |
| Ctrl_SingleWide | -0.0134214 | -0.0690018 | 0.0555803 | 6.90018e+07 |
| Ctrl_UniformPeriodic | 0.233538 | -0.390328 | 0.623867 | 1.67137 |
| Ctrl_SizeMatched_Monotonic | 0.420157 | -0.418279 | 0.838436 | 0.995529 |

## Experiment B

| Design | Peak (pN) | Window (um) | Work (fN um = aJ) | Censored |
|---|---:|---:|---:|---|

Not completed: no broadband-window claim can be made.
