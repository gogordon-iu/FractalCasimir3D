# Real-world monolithic NEMS clutch verification

**Status: MICRO-PROBE: NOT A COMPLETE VERIFICATION**

Forces are in SI newtons; positive force is upward on the rotor. Unavailable values are not zero forces.

Artifact status `completed` indicates output generation only; `measurement_status` retains failed or unavailable measurement states.

## Scope and limitations

- Part 2 specifies collars ending at R_min-0.03 and starting at R_max+0.03; part 3 explicitly occupies collars through R_min and from R_max. The mesh follows the explicit part-3 occupancy.
- Surviving Cantor ring ribs extend to z=0 in the landing-pad sector to provide pedestal clamps. Connectivity and rotor clearance are audited on the full geometry.
- An actuator ring is specified, but comb fingers, suspension, shaft bearings, drive electrodes, and electrical routing are not. Their mechanics and actuation are not verified by this script.
- Solver support macro-boxes use 2 nm clearances at adjoining boundaries to avoid overlapping or coincident interface panels. They approximate, rather than exactly reproduce, the connected full-geometry audit mesh.
- Selective metallization is a component-weighted homogeneous-BEM approximation, not an exact heterogeneous or finite-thickness coating solve.
- The silica comparison uses the specified static dielectric constant; a silica dispersion curve was not supplied.
- PFA is a zero-temperature planar projected-area comparison and cannot verify stepped-edge repulsion.
- The convergence check increases n_xi to max(12, 2 * baseline n_xi); panel subdivisions may also increase. Separate mesh and quadrature error contributions are not independently established.
- No load-bearing stress, buckling, release fabrication, stiction, electrical actuation, shaft bearing, or finite-temperature verification is claimed.
- Solves run in-process without a deadline by default. An explicitly requested deadline bounds the solver subprocess, not arbitrary third-party import, plotting, or filesystem latency.

## Mechanical and mesh audit

| Design | Angle (deg) | Rotor components | Stator components | Watertight | Collision-free |
|---|---:|---:|---:|:---:|:---:|
| Rot_C4_TightSlot_N2 | 0 | 1 | 1 | True | True |

## Solver execution

- Requested BEM measurements: 2
- Successful BEM measurements: 2
- BEM receives one 90-degree sector with face angles in radians; the repository solver applies four-fold cyclic symmetry.
- Repository `f_net_N` results are already SI newtons.
- Continuum PFA: 128-point Gauss-Legendre × 96-point Gauss-Laguerre, zero temperature.
- Hybrid weighting: mixed Au/dielectric planar pressure divided by Au/Au pressure at 350 nm for spider and 450 nm for foundation.
- Component ablations are nonadditive scattering differences. The residual is retained and disclosed.

## Convergence

| Angle | Kernel | Relative refined/baseline change | Sign |
|---:|---|---:|---|
| 0 | vector_dyadic | unavailable | unavailable |
| 0 | scalar_yukawa | unavailable | unavailable |
| 48 | vector_dyadic | unavailable | unavailable |
| 48 | scalar_yukawa | unavailable | unavailable |

## Provenance/output warnings

- save_plot_provenance: RepositoryAPIError: Unsupported required argument 'data_source' in save_plot_provenance(figure_path: str, data_source: str, columns_used: List[str], sidecar_suffix: str = '.provenance.json', solver_name: str | None = None, solver_parameters: Dict[str, Any] | None = None) -> str. Extend the explicit repository adapter for this API.
- save_plot_provenance: RepositoryAPIError: Unsupported required argument 'data_source' in save_plot_provenance(figure_path: str, data_source: str, columns_used: List[str], sidecar_suffix: str = '.provenance.json', solver_name: str | None = None, solver_parameters: Dict[str, Any] | None = None) -> str. Extend the explicit repository adapter for this API.

## Artifacts

- `results/real_world_nems_clutch_config.json`
- `results/real_world_nems_clutch_report.json`
- `results/real_world_nems_clutch/forces_comparison.csv`
- `figures/fig_real_world_nems_clutch_verification.png` and `.pdf` (unless plotting was disabled)

A mechanically disconnected geometry is not certified as a complete zero-floating-parts device, even if its field solve succeeds.
