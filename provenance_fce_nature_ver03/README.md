# Complete Data Provenance Archive for `fce_nature_ver03.tex`

This folder provides an end-to-end, machine- and human-readable data provenance trace for **every single number** appearing in `Papers/FCE_Nature_ver01/fce_nature_ver03.tex` and its three Extended Data tables (`table_fractal_geometry_control.tex`, `table_quantum_clutch.tex`, and `table_nems_feasibility.tex`), audited under `/grounded-experiment-pipeline` and `/data-freshness-guard`.

## Audit Summary

- **Data Freshness Status (`/data-freshness-guard`)**: **`FRESH_DATA (Exit Code 0 — All primary & MEEP artifacts verified post-bugfix)`**
- **Grounded Provenance Status (`/grounded-experiment-pipeline`)**: **`PASS (All 283 unique manuscript macros & all literal numbers resolved & fresh; 0 unresolved)`**
- **Line-by-Line Coverage**: **131** lines across the manuscript and tables containing empirical macro values or literal physical/geometric parameters are traced back to their exact result files, JSON pointers, SHA-256 digests, execution scripts, Python classes, functions (with line numbers), and simulation parameters.

## Directory Contents

1. **`00_data_freshness_audit.md` / `.json`**: Complete `/data-freshness-guard` report, SHA-256 checksums, execution timestamps (`executed_at`), and post-bugfix verification across all campaign JSON/CSV artifacts and all 21 4-pass MEEP task files.
2. **`01_macro_provenance_ledger.md` / `.json` / `.csv`**: Complete ledger of all **283 unique LaTeX macros** used in `fce_nature_ver03.tex` and Extended Data Tables 1–3, mapping each macro to its rendered value, raw floating-point value, metric key, result JSON file, exact JSON pointer/task ID, Python script, classes, functions (with line numbers), and full simulation parameters.
3. **`02_all_paper_numbers_line_by_line.md` / `.json` / `.csv`**: Complete line-by-line trace of **every number** (both LaTeX macro values and literal numbers in prose, equations, figure captions, Methods, and tables) ordered by file and line number.
4. **`03_by_section_and_table/`**: Dedicated provenance dossiers (`.md` and `.json`) broken down by manuscript section and Extended Data table:
   - `01_title_abstract_intro.md` & `.json`
   - `02_sec1_rotational_clutch_architecture.md` & `.json`
   - `03_sec2_multiscale_cantor_amplification.md` & `.json`
   - `04_sec3_log_periodic_wavenumber_locking.md` & `.json`
   - `05_sec4_room_temperature_stability.md` & `.json`
   - `06_sec5_atomic_cqed_optomech_readouts.md` & `.json`
   - `07_sec6_methods_and_declarations.md` & `.json`
   - `08_ed_table1_fractal_geometry_control.md` & `.json`
   - `09_ed_table2_quantum_clutch.md` & `.json`
   - `10_ed_table3_nems_feasibility.md` & `.json`
   - `11_figures_and_sidecars_provenance.md` & `.json`
