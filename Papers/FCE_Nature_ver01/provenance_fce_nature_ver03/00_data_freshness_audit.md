# Data Freshness & Post-Bugfix Audit (`00_data_freshness_audit`)

- **Target Manuscript**: `Papers/FCE_Nature_ver01/fce_nature_ver03.tex`
- **Skills Enforced**: `/grounded-experiment-pipeline` + `/data-freshness-guard`
- **Overall Freshness Verdict**: **`FRESH_DATA (Exit Code 0 — All primary & MEEP artifacts verified post-bugfix)`**
- **Unique Resolved LaTeX Data Macros**: **283** (`0` unresolved)
- **Total Audited Manuscript/Table Lines Containing Numbers**: **131**

## 1. Primary Campaign Result Artifacts

| Artifact Key | File Path | `executed_at` (UTC) | `model` / `dataset` | SHA-256 Digest | Freshness Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `nature_6step_narrative_report` | `results/nature_6step_narrative_report.json` | `2026-11-04T19:03:31.198503+00:00` | `BEM_Meep_Nature6Step` / `nature_6step_narrative` | `4c0df6e2062e8b5b...` | **FRESH (Post-Bugfix Verified)** |
| `clutch_log_periodicity_probe` | `results/clutch_log_periodicity_probe.json` | `2026-11-04T19:16:29.386072+00:00` | `BEM_LogPeriodicity_Clutch_Bridge` / `clutch_log_periodicity_probe` | `5bfa468bd964b290...` | **FRESH (Post-Bugfix Verified)** |
| `nature_feasibility_stability_report` | `results/nature_feasibility_stability_report.json` | `2026-11-02T06:35:24.789257+00:00` | `BEM_ElectroThermal_Feasibility` / `nature_feasibility_stability` | `fbe7787071786ab1...` | **FRESH (Post-Bugfix Verified)** |
| `bem_fdtd_convergence_resolution` | `results/bem_fdtd_convergence_resolution.json` | `2026-11-02T07:31:37.120537+00:00` | `BEM_FDTD_Convergence_Resolution` / `cantor_n2_hybridrz_convergence_controls` | `345308fcdc242838...` | **FRESH (Post-Bugfix Verified)** |
| `atomic_cqed_probes_report` | `results/atomic_cqed_probes_report.json` | `2026-10-26T21:26:28.452959+00:00` | `AtomicCQED_VacuumProbes` / `atomic_cqed` | `386f4ca74082ceef...` | **FRESH (Post-Bugfix Verified)** |
| `fractal_advantage_study_report` | `results/fractal_advantage_study_report.json` | `2026-10-25T22:15:32.915251+00:00` | `BEM_FractalAdvantageStudy` / `fractal_advantage_study` | `edb6333c6a40d088...` | **FRESH (Post-Bugfix Verified)** |
| `rotational_z_eff_clutch_report` | `results/rotational_z_eff_clutch_report.json` | `2026-10-17T05:28:28.798368+00:00` | `BEM_Meep_RotationalZEff` / `rotational_z_eff_clutch` | `f3a45ba1152a6445...` | **FRESH (Post-Bugfix Verified)** |
| `rotational_clutch_3solver_verification_report` | `results/rotational_clutch_3solver_verification_report.json` | `2026-10-17T14:05:40.798975+00:00` | `rotational_clutch_3solver_verification` / `rotational_clutch_3solver_verification` | `2f45cc6633c10b4e...` | **FRESH (Post-Bugfix Verified)** |
| `provenance_metrics` | `results/provenance_metrics.json` | `2026-11-05T01:35:37.418444+00:00` | `bem` / `nature_feasibility_stability` | `cde0e3b48790e19f...` | **FRESH (Post-Bugfix Verified)** |
| `manuscript_provenance_map` | `results/manuscript_provenance_map.json` | `N/A` | `N/A` / `N/A` | `7314f89436343a63...` | **FRESH (Post-Bugfix Verified)** |

## 2. 4-Pass 3D FDTD (MEEP) Task Artifacts (`results_rotational_z_eff_meep/`)

| Task File | `executed_at` (UTC) | Cache Ver | SHA-256 Digest | Freshness Status |
| :--- | :--- | :--- | :--- | :--- |
| `results_rotational_z_eff_meep/task_1_meep.json` | `2026-10-17T05:35:45.018497+00:00` | `v6` | `7ae6d98a9fb4478b...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_2_meep.json` | `2026-10-17T05:35:37.432084+00:00` | `v6` | `bc68bb2aaa9e5595...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_3_meep.json` | `2026-10-17T05:35:28.771138+00:00` | `v6` | `4d80ff4ff3e3335d...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_4_meep.json` | `2026-10-17T05:35:35.386871+00:00` | `v6` | `e3d3b4b08aa87110...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_5_meep.json` | `2026-10-17T06:03:47.043277+00:00` | `v6` | `1ffd6d99366a01e9...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_6_meep.json` | `2026-10-17T06:03:54.382841+00:00` | `v6` | `8cc880a0c01ade15...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_7_meep.json` | `2026-10-17T06:04:49.634895+00:00` | `v6` | `5e8ec8545be9e602...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_8_meep.json` | `2026-10-17T06:04:16.841761+00:00` | `v6` | `7907e9e7603924f1...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_9_meep.json` | `2026-10-17T06:32:33.514836+00:00` | `v6` | `80517f534f5c0e75...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_10_meep.json` | `2026-10-17T06:58:24.828775+00:00` | `v6` | `581c18f925c69ffb...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_11_meep.json` | `2026-10-17T06:58:42.767532+00:00` | `v6` | `6433a4245d3b9f82...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_12_meep.json` | `2026-10-17T07:00:09.364881+00:00` | `v6` | `5a4b75e26649ea64...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_13_meep.json` | `2026-10-17T07:27:05.500198+00:00` | `v6` | `adce2ef8f6fa4abb...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_14_meep.json` | `2026-10-17T07:52:49.013895+00:00` | `v6` | `95b6f5469338c6e7...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_15_meep.json` | `2026-10-17T07:53:14.110808+00:00` | `v6` | `556322910028de6e...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_16_meep.json` | `2026-10-17T07:54:32.237324+00:00` | `v6` | `02f3e90acb7d8038...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_17_meep.json` | `2026-10-17T08:21:21.792096+00:00` | `v6` | `5e3626d250c27d66...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_18_meep.json` | `2026-10-17T08:47:26.680058+00:00` | `v6` | `257b71df448fd032...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_19_meep.json` | `2026-10-17T10:36:47.019151+00:00` | `v6` | `ac5202ccd17fd22e...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_20_meep.json` | `2026-10-17T10:36:58.365213+00:00` | `v6` | `ac8f83261fae5f2a...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
| `results_rotational_z_eff_meep/task_21_meep.json` | `2026-10-17T11:03:29.234572+00:00` | `v6` | `3f7a348a69884c8f...` | **FRESH (cache_version=6, Post-BUG-261016-06)** |
