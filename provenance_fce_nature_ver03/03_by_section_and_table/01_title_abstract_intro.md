# Provenance Dossier: `01_title_abstract_intro`

- **Audited Lines with Numbers**: **4**

## `fce_nature_ver03.tex` Line 48
`The quantum fluctuation-induced Casimir force between neutral surfaces in vacuum is ordinarily attractive, governed by face-to-face surface areas and symmetry constraints that preclude repulsion in true vacuum. Although `

- **Macro `\CantorNtwoFlatzVsUniformBemStdRatio{}`** -> Rendered: **`1.25`** | Raw: `1.25`
  - **Metric Key**: `cantor_n2_flatz_vs_uniform_bem_std_ratio`
  - **Data File**: `results/nature_6step_narrative_report.json` | **JSON Pointer**: `$.metrics.cantor_n2_flatz_vs_uniform_bem_std_ratio.value` | **SHA-256**: `4c0df6e2062e8b5b...`
  - **Execution Script**: `execution/run_nature_6step_narrative.py` | **Solver Scripts**: `execution/casimir_bem_solver.py, execution/clutch_geometry_redesign.py`
  - **Classes**: `execution/run_nature_6step_narrative.py::TrackSpec3D (L208), execution/run_nature_6step_narrative.py::StudyDesign (L247), execution/run_nature_6step_narrative.py::Resolution (L298), execution/run_nature_6step_narrative.py::Task (L345), execution/run_nature_6step_narrative.py::ReferenceMeshAdapter (L514), execution/run_nature_6step_narrative.py::Campaign (L1332), execution/casimir_bem_solver.py::BemResolutionTier (L134), execution/casimir_bem_solver.py::ClutchSurfaceMesh (L458), execution/casimir_bem_solver.py::MaterialModel (L1188), execution/casimir_bem_solver.py::DenseBackend (L1312)`
  - **Functions**: `execution/run_nature_6step_narrative.py::cantor_tracks (L971), execution/run_nature_6step_narrative.py::build_designs (L1005), execution/run_nature_6step_narrative.py::tooth_geometry_metrics (L1159), execution/run_nature_6step_narrative.py::build_active_sector_mesh (L699), execution/run_nature_6step_narrative.py::build_monolithic_sector_mesh (L862), execution/run_nature_6step_narrative.py::Campaign.run (L1442), execution/run_nature_6step_narrative.py::derive_analysis (L2029), execution/casimir_bem_solver.py::run_bem_casimir_solver (L1761), execution/casimir_bem_solver.py::_vector_dyadic_blocks (L1087), execution/casimir_bem_solver.py::_yukawa_blocks (L1038), execution/casimir_bem_solver.py::_frequency_integrand (L1444)`
  - **Parameters**: `{"campaign": "BEM_Meep_Nature6Step", "constellations_evaluated": 12, "bem_tasks_evaluated": 78, "meep_tasks_verified": 16, "formulation": "3D Vector-Dyadic BEM (Drude Gold, eps_bg = 1.0)", "metric_key": "cantor_n2_flatz_vs_uniform_bem_std_ratio", "value": 1.25}`
- **Macro `\FractalNthreeVsUniformBemStdRatio{}`** -> Rendered: **`2.66`** | Raw: `2.66`
  - **Metric Key**: `fractal_n3_vs_uniform_bem_std_ratio`
  - **Data File**: `results/nature_6step_narrative_report.json` | **JSON Pointer**: `$.metrics.fractal_n3_vs_uniform_bem_std_ratio.value` | **SHA-256**: `4c0df6e2062e8b5b...`
  - **Execution Script**: `execution/run_nature_6step_narrative.py` | **Solver Scripts**: `execution/casimir_bem_solver.py, execution/clutch_geometry_redesign.py`
  - **Classes**: `execution/run_nature_6step_narrative.py::TrackSpec3D (L208), execution/run_nature_6step_narrative.py::StudyDesign (L247), execution/run_nature_6step_narrative.py::Resolution (L298), execution/run_nature_6step_narrative.py::Task (L345), execution/run_nature_6step_narrative.py::ReferenceMeshAdapter (L514), execution/run_nature_6step_narrative.py::Campaign (L1332), execution/casimir_bem_solver.py::BemResolutionTier (L134), execution/casimir_bem_solver.py::ClutchSurfaceMesh (L458), execution/casimir_bem_solver.py::MaterialModel (L1188), execution/casimir_bem_solver.py::DenseBackend (L1312)`
  - **Functions**: `execution/run_nature_6step_narrative.py::cantor_tracks (L971), execution/run_nature_6step_narrative.py::build_designs (L1005), execution/run_nature_6step_narrative.py::tooth_geometry_metrics (L1159), execution/run_nature_6step_narrative.py::build_active_sector_mesh (L699), execution/run_nature_6step_narrative.py::build_monolithic_sector_mesh (L862), execution/run_nature_6step_narrative.py::Campaign.run (L1442), execution/run_nature_6step_narrative.py::derive_analysis (L2029), execution/casimir_bem_solver.py::run_bem_casimir_solver (L1761), execution/casimir_bem_solver.py::_vector_dyadic_blocks (L1087), execution/casimir_bem_solver.py::_yukawa_blocks (L1038), execution/casimir_bem_solver.py::_frequency_integrand (L1444)`
  - **Parameters**: `{"campaign": "BEM_Meep_Nature6Step", "constellations_evaluated": 12, "bem_tasks_evaluated": 78, "meep_tasks_verified": 16, "formulation": "3D Vector-Dyadic BEM (Drude Gold, eps_bg = 1.0)", "metric_key": "fractal_n3_vs_uniform_bem_std_ratio", "value": 2.66}`

## `fce_nature_ver03.tex` Line 53
`The Casimir effect---the macroscopic force arising from boundary-modified quantum electromagnetic fluctuations\cite{casimir1948,bordag2009}---provides a direct mechanical link between quantum field theory and the geometr`

- **Literal `100`** (verified: `100.0`, `$.probes.probe_distance_z_nm`) — Atomic cQED probe height / prefractal gap d = 100 nm
  - **Data File**: `results/atomic_cqed_probes_report.json` | **Script**: `execution/run_atomic_cqed_probes.py`
  - **Classes**: `execution/casimir_bem_solver.py::MaterialModel (L1188)` | **Functions**: `execution/run_atomic_cqed_probes.py::compute_casimir_polder_probe (L89), execution/run_atomic_cqed_probes.py::compute_purcell_probe (L122), execution/run_atomic_cqed_probes.py::compute_lamb_shift_probe (L159), execution/run_atomic_cqed_probes.py::compute_scattering_probe (L191)`
  - **Parameters**: `{"constant_type": "Atomic cQED probe height / prefractal gap d = 100 nm", "z_nm": 100.0}`
- **Literal `1.0`** (verified: `1.0`, `$.settings.epsilon_bg`) — True vacuum background permittivity eps_bg = 1.0
  - **Data File**: `results/nature_6step_narrative_report.json` | **Script**: `execution/run_nature_6step_narrative.py`
  - **Classes**: `execution/run_nature_6step_narrative.py::TrackSpec3D (L208), execution/run_nature_6step_narrative.py::StudyDesign (L247), execution/run_nature_6step_narrative.py::Resolution (L298), execution/run_nature_6step_narrative.py::Task (L345)` | **Functions**: `execution/run_nature_6step_narrative.py::cantor_tracks (L971), execution/run_nature_6step_narrative.py::build_designs (L1005), execution/run_nature_6step_narrative.py::tooth_geometry_metrics (L1159), execution/run_nature_6step_narrative.py::build_active_sector_mesh (L699)`
  - **Parameters**: `{"constant_type": "True vacuum background permittivity eps_bg = 1.0", "epsilon_bg": 1.0}`

## `fce_nature_ver03.tex` Line 57
`Second, Levin et al.\cite{levin2010} demonstrated that reflection symmetry can be broken geometrically in true vacuum ($\varepsilon_{\rm bg}=1.0$) without fractals: when a metallic ridge interdigitates with a slotted ape`

- **Literal `1.0`** (verified: `1.0`, `$.settings.epsilon_bg`) — True vacuum background permittivity eps_bg = 1.0
  - **Data File**: `results/nature_6step_narrative_report.json` | **Script**: `execution/run_nature_6step_narrative.py`
  - **Classes**: `execution/run_nature_6step_narrative.py::TrackSpec3D (L208), execution/run_nature_6step_narrative.py::StudyDesign (L247), execution/run_nature_6step_narrative.py::Resolution (L298), execution/run_nature_6step_narrative.py::Task (L345)` | **Functions**: `execution/run_nature_6step_narrative.py::cantor_tracks (L971), execution/run_nature_6step_narrative.py::build_designs (L1005), execution/run_nature_6step_narrative.py::tooth_geometry_metrics (L1159), execution/run_nature_6step_narrative.py::build_active_sector_mesh (L699)`
  - **Parameters**: `{"constant_type": "True vacuum background permittivity eps_bg = 1.0", "epsilon_bg": 1.0}`

## `fce_nature_ver03.tex` Line 59
`Here we unify these two phenomena by showing that 3D slot-tooth interdigitation and prefractal Cantor recursion are mutually essential counterparts of a macroscopic fractal Casimir effect (Figs.~\ref{fig:rotational_clutc`

- **Literal `0`** (verified: `0.0`, `$.evaluations[20].theta_deg`) — Zero-degree reference rotational angle theta = 0 deg
  - **Data File**: `results/rotational_clutch_3solver_verification_report.json` | **Script**: `execution/run_rotational_clutch_3solver_verification.py`
  - **Classes**: `execution/casimir_bem_solver.py::BemResolutionTier (L134), execution/casimir_bem_solver.py::ClutchSurfaceMesh (L458), execution/casimir_bem_solver.py::YukawaBlocks (L958), execution/casimir_bem_solver.py::MaterialModel (L1188)` | **Functions**: `execution/run_rotational_clutch_3solver_verification.py::get_design (L153), execution/run_rotational_clutch_3solver_verification.py::gold_material (L160), execution/run_rotational_clutch_3solver_verification.py::lifshitz_pressure (L164), execution/run_rotational_clutch_3solver_verification.py::polar_overlap_um2 (L217)`
  - **Parameters**: `{"constant_type": "Zero-degree reference rotational angle theta = 0 deg", "theta_deg": 0.0}`
- **Literal `6`** (verified: `6.0`, `$.settings.mst_box_faces`) — 6 bounding-box faces of the 3D Maxwell stress tensor surface
  - **Data File**: `results/rotational_z_eff_clutch_report.json` | **Script**: `execution/run_rotational_z_eff_clutch.py`
  - **Classes**: `execution/run_rotational_z_eff_clutch.py::ToothInterval (L276), execution/run_rotational_z_eff_clutch.py::ClutchSpec (L285), execution/casimir_bem_solver.py::ClutchSurfaceMesh (L458), execution/casimir_bem_solver.py::MaterialModel (L1188)` | **Functions**: `execution/run_rotational_z_eff_clutch.py::scan_meep_results (L198), execution/run_rotational_z_eff_clutch.py::build_rotational_stepped_clutch_mesh (L509), execution/run_rotational_z_eff_clutch.py::collision_certificate (L670), execution/run_rotational_z_eff_clutch.py::angular_state (L688)`
  - **Parameters**: `{"constant_type": "6 bounding-box faces of the 3D Maxwell stress tensor surface", "faces": 6}`
- **Literal `0`** (verified: `0.0`, `$.evaluations[20].theta_deg`) — Zero-degree reference rotational angle theta = 0 deg
  - **Data File**: `results/rotational_clutch_3solver_verification_report.json` | **Script**: `execution/run_rotational_clutch_3solver_verification.py`
  - **Classes**: `execution/casimir_bem_solver.py::BemResolutionTier (L134), execution/casimir_bem_solver.py::ClutchSurfaceMesh (L458), execution/casimir_bem_solver.py::YukawaBlocks (L958), execution/casimir_bem_solver.py::MaterialModel (L1188)` | **Functions**: `execution/run_rotational_clutch_3solver_verification.py::get_design (L153), execution/run_rotational_clutch_3solver_verification.py::gold_material (L160), execution/run_rotational_clutch_3solver_verification.py::lifshitz_pressure (L164), execution/run_rotational_clutch_3solver_verification.py::polar_overlap_um2 (L217)`
  - **Parameters**: `{"constant_type": "Zero-degree reference rotational angle theta = 0 deg", "theta_deg": 0.0}`
- **Literal `0`** (verified: `0.0`, `$.evaluations[20].theta_deg`) — Zero-degree reference rotational angle theta = 0 deg
  - **Data File**: `results/rotational_clutch_3solver_verification_report.json` | **Script**: `execution/run_rotational_clutch_3solver_verification.py`
  - **Classes**: `execution/casimir_bem_solver.py::BemResolutionTier (L134), execution/casimir_bem_solver.py::ClutchSurfaceMesh (L458), execution/casimir_bem_solver.py::YukawaBlocks (L958), execution/casimir_bem_solver.py::MaterialModel (L1188)` | **Functions**: `execution/run_rotational_clutch_3solver_verification.py::get_design (L153), execution/run_rotational_clutch_3solver_verification.py::gold_material (L160), execution/run_rotational_clutch_3solver_verification.py::lifshitz_pressure (L164), execution/run_rotational_clutch_3solver_verification.py::polar_overlap_um2 (L217)`
  - **Parameters**: `{"constant_type": "Zero-degree reference rotational angle theta = 0 deg", "theta_deg": 0.0}`
- **Literal `18`** (verified: `18.0`, `$.tasks[1].theta_deg`) — Intermediate rotational angle theta = 18 deg
  - **Data File**: `results/rotational_clutch_3solver_verification_report.json` | **Script**: `execution/run_rotational_clutch_3solver_verification.py`
  - **Classes**: `execution/casimir_bem_solver.py::BemResolutionTier (L134), execution/casimir_bem_solver.py::ClutchSurfaceMesh (L458), execution/casimir_bem_solver.py::YukawaBlocks (L958), execution/casimir_bem_solver.py::MaterialModel (L1188)` | **Functions**: `execution/run_rotational_clutch_3solver_verification.py::get_design (L153), execution/run_rotational_clutch_3solver_verification.py::gold_material (L160), execution/run_rotational_clutch_3solver_verification.py::lifshitz_pressure (L164), execution/run_rotational_clutch_3solver_verification.py::polar_overlap_um2 (L217)`
  - **Parameters**: `{"constant_type": "Intermediate rotational angle theta = 18 deg", "theta_deg": 18.0}`
- **Literal `48`** (verified: `48.0`, `$.tasks[?(@.task_id==step1_single_tooth_ztip_0006)].theta_deg`) — Engaged landing-pad rotational state theta = 48 deg
  - **Data File**: `results/nature_6step_narrative_report.json` | **Script**: `execution/run_nature_6step_narrative.py`
  - **Classes**: `execution/run_nature_6step_narrative.py::TrackSpec3D (L208), execution/run_nature_6step_narrative.py::StudyDesign (L247), execution/run_nature_6step_narrative.py::Resolution (L298), execution/run_nature_6step_narrative.py::Task (L345)` | **Functions**: `execution/run_nature_6step_narrative.py::cantor_tracks (L971), execution/run_nature_6step_narrative.py::build_designs (L1005), execution/run_nature_6step_narrative.py::tooth_geometry_metrics (L1159), execution/run_nature_6step_narrative.py::build_active_sector_mesh (L699)`
  - **Parameters**: `{"constant_type": "Engaged landing-pad rotational state theta = 48 deg", "theta_deg": 48.0}`

