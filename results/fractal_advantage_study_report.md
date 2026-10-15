# Optimal Fractal Advantage: grounded BEM study

- Status: **running**
- Formulation: `vector_dyadic`
- Device: `cpu`
- Completed tasks: 4/32
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

## Experiment B

| Design | Peak (pN) | Window (um) | Work (fN um = aJ) | Censored |
|---|---:|---:|---:|---|

Not completed: no broadband-window claim can be made.
