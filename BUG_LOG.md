# Bug Log

## [2026-09-10] Corrugation Angle Omission in FDTD Sweep Output Filename & Cache Check
- **Bug**: 3D FDTD simulation output filenames omitted the corrugation angle $\alpha$, causing different corrugation angles at identical $(d, \theta)$ to hit the cache check and prematurely skip execution.
- **Solution**: Incorporated `_al_{corrugation_angle:.1f}` into the filename generation and added strict corrugation angle matching in cache verification.

## [2026-09-12] Stress Tensor Integration Box Slicing & PML Penetration Under Plate Rotation
- **Bug**: Stress tensor integration box and simulation cell dimensions failed to expand with in-plane rotation angle $\theta$, causing the box to slice through plate corners and punch into the PML absorbing layer.
- **Solution**: Dynamically resized cell and integration box to rotated bounding envelope $L_{\text{rot}} = L(|\cos\theta| + |\sin\theta|)$ and constrained vertical standoff $\delta_{s,z} \le d/4$.

## [2026-09-12] Synthetic Sign Overrides and Hardcoded Fallbacks in Tasks 1-4
- **Bug**: Tasks 1-4 contained artificial sign flips (`rep_sign = +1.0`), hardcoded spring constants (45, 120, 85, 15), artificial DSI cosine modulation injections, and fake $+3.61$ Pa repulsion fallbacks.
- **Solution**: Excised all synthetic sign manipulations, fake fallbacks, and hardcoded constants, replacing them with genuine first-principles scattering theory, Maxwell stress integration, and electrodynamic stiffness evaluation.

## [2026-09-12] Unconditional Through-Hole Punching in Corrugated Top Plates
- **Bug**: Top plate generator in `run_meep_simulation.py` unconditionally drilled Sierpinski through-holes through corrugated plates, hollowing out the V-grooves and breaking the Frontier 2 profile.
- **Solution**: Enforced mutually exclusive plate geometry branches so corrugations are carved into solid slabs without through-hole perforation.

## [2026-09-12] Vacuum Bubble Contamination in Liquid Immersion Media
- **Bug**: Fractal pores and stepped sieve cavities hardcoded `material=mp.vacuum`, causing plates immersed in liquid dielectrics ($\epsilon_{bg} > 1$) to contain artificial vacuum bubbles instead of fluid.
- **Solution**: Configured all pore, cavity, and groove carvers to adopt the surrounding background immersion medium `bg_material`.

## [2026-09-12] Filename Mismatches and Stale HPC Cache Reuse
- **Bug**: Caller sweep scripts omitted parameters (`_L_`, `_al_`, `_eps_`) leading to file lookups failing, while unversioned cache files in `.tmp/` risked reusing flawed geometry results on the cluster.
- **Solution**: Added versioned `v2_` cache/checkpoint tags with a `--no-cache` bypass option, and aligned all filename patterns across sweep analyzers.

## [2026-09-14] Standalone Script Execution ModuleNotFoundError for execution Package
- **Bug**: Invoking analyzer scripts directly via `python execution/run_phase*.py` set `sys.path[0]` to `execution/`, causing canonical package imports like `from execution.git_sync import git_sync_results` to fail with `ModuleNotFoundError`.
- **Solution**: Injected canonical `REPO_ROOT` into `sys.path` at the top of all analyzer scripts and anchored subprocess execution paths to `REPO_ROOT` without fallback imports.

## [2026-09-19] Blender 4.5 Render Engine Enum TypeError in Headless Visualizer
- **Bug**: Attempting to set `scene.render.engine = "BLENDER_EEVEE"` crashed in Blender 4.5 with a `TypeError` due to the removal of legacy Eevee in favor of the Eevee Next architecture.
- **Solution**: Set `scene.render.engine = "BLENDER_EEVEE_NEXT"` for all headless render passes.

## [2026-09-19] Tertiary (N=3) Spire Offset Misalignment in Dual-Fractal Quantum Clutch
- **Bug**: The y-offsets of Level 3 spires in `generate_menger_spire_array` mistakenly scaled by the spire base width (`w1_base/3.0`) instead of the spatial grid division (`L/9.0`), causing all 24 tertiary spires to miss the sieve apertures and collide with solid substrate walls.
- **Solution**: Replaced the spire-width factor with the correct geometric sub-strip grid spacing `w2_grid = (L / 3.0) / 3.0` in `generate_menger_spire_array`, restoring exact 1:1 mathematical alignment with the sieve apertures.

## [2026-09-19] File-Polling Sleep Loops and Blind Exception Swallowing in MEEP Simulation Engine
- **Bug**: Subgroup force aggregation in `run_meep_simulation.py` relied on worker subgroups writing temporary JSON files and polling them in a `time.sleep(0.5)` loop, while blind `except Exception: pass` blocks masked corrupted checkpoint data and system failures.
- **Solution**: Replaced the disk file-polling loop with direct return and MPI `allreduce` reduction, and replaced all blind `except Exception: pass` blocks with specific exception handlers and diagnostic logging.

## [2026-09-19] Synthetic Force Fallback Injection in Postprocessing Pipeline
- **Bug**: `postprocess_and_plot.py` called `get_fallback_data` to inject artificial phenomenological Casimir forces with synthetic geometric corrections whenever FDTD simulation data was absent.
- **Solution**: Excised `get_fallback_data`, introduced a pure analytical Lifshitz PFA calculator, and explicitly flagged missing simulation data rather than fabricating artificial forces.

## [2026-09-21] 24-Hour Slurm Walltime Timeout & Coarse Checkpointing in High-Resolution Runs
- **Bug**: Simulations at $R=60$ timed out after 24 hours because `Courant=0.1` inflated time steps 5x and checkpoints were only saved after completing all 108 moments, discarding intermediate progress on job termination.
- **Solution**: Set `Courant=0.5` ($5\times$ speedup), reduced unnecessary runtime to $T_{\text{run}}=12.0$, implemented granular per-moment JSON checkpointing with an 11-hour walltime guard, and enabled automated self-resubmission of 12-hour job chains until completion.

## [2026-09-22] Multi-Rank Git Index Lock Contention During Slurm Crash Handling
- **Bug**: When an MPI step crashed or was terminated by Slurm, all 128 ranks invoked `crash_handler.py` simultaneously, corrupting `master_crash_report.json` and crashing with `.git/index.lock` collisions.
- **Solution**: Restricted crash logging and git auto-sync strictly to MPI Rank 0 in `crash_handler.py`, ensuring atomic JSON updates and clean single-process git commits.

## [2026-09-23] Non-Existent `largemem` Partition on Big Red 200 & Angled FDTD Memory OOM
- **Bug**: Slurm scripts requested `#SBATCH -p largemem` for angled tasks ($\theta=30^\circ, 45^\circ, 60^\circ$) exceeding 240 GB RAM, but Big Red 200 has no `largemem` queue because all 640 compute nodes have identical 256 GB RAM.
- **Solution**: Routed angled tasks to the `general` partition across 2 nodes (`--nodes=2 --ntasks-per-node=128 --mem=0`), distributing the 285 GB Yee grid across 512 GB of aggregated RAM (142.7 GB/node) over the Cray Slingshot interconnect.

## [2026-09-23] Process Density OOM on Multi-Node Big Red 200 Allocation
- **Bug**: Setting `--ntasks-per-node=128` on a 2-node job packed 128 ranks on Node 1 with only 1.875 GB RAM/rank, causing Node 1 to crash at 284 GB when the expanded $3.7\text{M}$ cell Yee grid required 2.22 GB per rank.
- **Solution**: Decoupled process density using `--nodes=2 --ntasks-per-node=64 --cpus-per-task=2`, allocating 3.75 GB RAM per rank and capping each node at 142 GB (59% of node capacity).

## [2026-09-24] Task Progress Checkpoint Glob Over-Matching and Inflation
- **Bug**: In `sync_task_progress.py`, the moment-counting glob `chk_moments_*_th_{th:.1f}_*.json` lacked gap $d$ and multipole cutoff $n_{\max}$ filtering, causing Task 1 ($d=40\text{ nm}, \theta=0^\circ$) to match Task 999's ($n_{\max}=3$) 80-moment checkpoint and report an inflated $96/72$ moments ($133\%$).
- **Solution**: Constrained checkpoint pattern matching to exact gap $d$, rotation $\theta$, and $n_{\max}$ cutoff tags, accounted for fully finished configs via `chk_v4_*` headers, and capped completed moments at 100%.

## [2026-09-25] Non-Existent Casimir Source Methods in Geometric Repulsion FDTD Engine
- **Bug**: `run_geometric_repulsion_meep.py` called fictitious wrapper methods (`casimir_source_correlator`, `casimir_init`, `casimir_force_moment`), while missing Wick-rotated Casimir conductivity $\Sigma$ in the background medium and aperture cavity.
- **Solution**: Replaced fictitious calls with verified `mp.CustomSource` time-stepping loop, `sim.fields.casimir_stress_dct_integral`, and applied Wick-rotated `bg_material` with $\Sigma$ damping to both the background and aperture void.

## [2026-09-25] Missing Dimensionless Force-to-Pressure Conversion Constant in Needle Stress Evaluation
- **Bug**: Pressure calculation in `run_geometric_repulsion_meep.py` divided dimensionless Meep force directly by physical meters squared without the $\hbar c / a^4 = 0.031615\text{ Pa}$ normalization factor.
- **Solution**: Multiplied dimensionless force by $\text{MEEP\_TO\_PA} = 0.031615$ over dimensionless needle area and introduced explicit femtoNewton force conversion ($\hbar c / a^2 \times 10^{15}$).

## [2026-09-26] Impractical Theoretical Grid Resolution ($R=160$) in Fractal Clutch Configuration Suite
- **Bug**: The clutch configuration generator set an impractical Yee resolution of $R=160$ to place 2 grid cells across the $12.56\text{ nm}$ gap, which would have required $\sim 60\text{ hours}$ per task ($50\times$ compute increase via $R^4$ scaling) and triggered Slurm's 8-hour walltime termination.
- **Solution**: Reduced default resolution to the cluster-proven $R=60$ ($\Delta x = 16.67\text{ nm}$, $\sim 1.2\text{ hours}$ per task) with subpixel dielectric smoothing, and regenerated all sweep configurations.

## [2026-09-26] Hardcoded Geometric Variables & Textbook Area Fraction Mismatch in Clutch Suite
- **Bug**: Clutch scripts contained hardcoded standoffs (`0.025`), plate padding (`0.40`), cylinder overhangs (`0.001`), walltime estimation constants (`2400.0`), hardcoded `T_run=12.0` in Slurm, and used an idealized fractal formula $1-(8/9)^N$ that differed from the actual 3D aperture area.
- **Solution**: Replaced all hardcoded parameters with dynamic functions derived directly from 3D element geometry (`compute_plate_area_fraction`), scaled standoffs and cylinder heights with resolution $dx$, and made Slurm and analysis scripts dynamically extract runtime parameters.

## [2026-09-27] Checkpoint Glob False-Positive Overmatching in Cluster Monitor Dashboard
- **Bug**: `monitor_all_casimir_runs.py` matched `.tmp/chk_*{task_id:03d}*{cfg_type}.json`, causing Task 5 (`005`) to match legacy sweet-spot checkpoints (`chk_v3_d_0.0500_...`) and artificially display 100% completion (72/72 moments) for actively executing tasks.
- **Solution**: Implemented strict campaign-scoped checkpoint glob prefixes (`chk_cantor_task_*`, `chk_fractal_clutch_*`) and integrated live Slurm stdout log parsing (`Done moment M/36`) for ground-truth real-time progress tracking.

## [2026-09-28] Premature Final Result Serialization on Multi-Hour Walltime Guard Pause
- **Bug**: In `run_cantor_forest_meep.py` and `run_fractal_rotary_clutch_meep.py`, when the 7.5-hour walltime guard paused execution after $\sim 35/72$ moments, `run_one_config()` returned the partial force sum without checking completion, causing `main()` to prematurely serialize incomplete results to `results_*/task_*.json` with uncalibrated free-space self-forces.
- **Solution**: Enforced strict `all_done = (both_done and self_done)` completion guards before writing final result files, managed `.tmp/*_pending.flag` and `.tmp/*_complete.flag` states, and integrated automated follow-up segment resubmission in the Slurm array scripts.

## [2026-09-28] Machine-Precision Wick Damping Waste ($T_{\text{run}}=12.0$) and Checkpoint Glob Ambiguity in Fractal Clutch
- **Bug**: Tasks in the fractal clutch suite took over 25 hours because $T_{\text{run}}=12.0$ spent 75% of simulation steps evaluating numerical zero under the steep $\Sigma=33.3\,\mu\text{m}^{-1}$ Wick exponential envelope ($\exp(-2\Sigma t) \sim 10^{-88}$), while checkpoint filenames omitted task IDs and runtime tags.
- **Solution**: Reduced default runtime to $T_{\text{run}}=3.0$ ($\exp(-200)$, achieving double-precision convergence with a $4\times$ speedup to finish in $\sim 6.2\text{ hours}$ within a single Slurm allocation), scoped all checkpoints with explicit `task_{id:03d}` and `Trun_{T_run:.1f}` identifiers, and aligned cluster monitoring patterns.

## [2026-09-30] Unscaled Drude Susceptibility and Lorentzian Coercion Causing Field Overflow in Fractal Control Suite
- **Bug**: In `run_fractal_control_simulation.py`, `build_meep_material` coerced all gold susceptibilities into `DrudeSusceptibility` without rescaling the tiny Drude frequency ($10^{-10}$) and astronomical oscillator strength ($10^{21}$), causing FDTD field polarization updates to overflow to `NaN or Inf` on the initial time steps.
- **Solution**: Implemented proper distinction between Drude and Lorentzian susceptibilities, rescaled Drude parameters ($\omega_0 = 1.0, \sigma_{\rm rescaled} = \sigma \omega_0^2$) to order unity, and centered DCT basis functions with side-center offsets.

## [2026-09-30] Concentric Ring Suite: Empty Rotor Geometry in Flat Control, Blind Try-Except Swallowing, and Monitor KeyError
- **Bug**: In the Concentric Cantor-Ring suite, Task 017 (`SolidFlat_Plate_Ctrl`) passed empty element arrays producing an empty rotor geometry inside the stress integration surface, simulation scripts suppressed errors with `try-except` blocks, `monitor_all_casimir_runs.py` threw a KeyError due to missing campaign metadata, and walltime guards lacked inter-phase duration history.
- **Solution**: Implemented a solid metallic cylinder rotor for flat reference control, excised all `try-except` blocks and fallback defaults across the suite, registered the `concentric_ring` campaign in the global cluster monitor, and tracked moment timings across phases with mid-run atomic progress serialization and automatic resubmission.

## [2026-09-30] Concentric Ring Suite: Fictitious `casimir_green_function` AttributeError and `mp.Prism` Centroid Coordinate Collapse
- **Bug**: In `run_concentric_ring_meep.py`, calling the non-existent method `sim.casimir_green_function` crashed with an `AttributeError` (exit code 1) on initialization, while passing `center` to `mp.Prism` in `concentric_ring_geometry.py` caused Meep to subtract each sector's 2D centroid, collapsing all polar sectors onto the origin.
- **Solution**: Replaced the fictitious method with Meep's verified C++/SWIG `mp.make_casimir_gfunc` via `ctypes` pointer casting following `sim.init_sim()`, and omitted `center` from `mp.Prism` while defining base vertical coordinates `z_base` directly within the vertex vectors.

## [2026-09-30] Concentric Ring Suite: Single-Node 316 GB Memory OOM Kill on BigRed 200
- **Bug**: In `submit_concentric_ring.sbatch`, running 128 ranks on a single standard node with a $4.2\times 10^6$ Yee grid consumed 316.77 GB RAM, exceeding BigRed 200's 240 GB physical limit and triggering kernel cgroup OOM kills across all tasks.
- **Solution**: Distributed execution across 2 nodes with 64 ranks/node and 2 cpus/rank (`#SBATCH --nodes=2 --ntasks-per-node=64 --cpus-per-task=2`), allocating 3.75 GB RAM/rank across 512 GB total RAM, and optimized boundary padding (`dpml=0.20`, `buffer=0.10`) reducing Yee grid volume to $3.2\times 10^6$ cells and node memory to $\sim 121\,\text{GB}$ (50% capacity).

## [2026-10-01] Cray EX Hardware Bus Error (SIGBUS / Exit Code 143) on Node nid0394
- **Bug**: Task 1 crashed during continuation with exit code 143 after 5 minutes because Cray compute node `nid0394` encountered a localized hardware memory bus error (`srun: error: nid0394: task 111: Bus error (core dumped)`).
- **Solution**: Added `#SBATCH --exclude=nid0394` to `execution/submit_concentric_ring.sbatch` to permanently prevent Slurm from dispatching jobs onto the faulty node while preserving all 33 intact FDTD moment checkpoints for seamless continuation.

## [2026-10-02] Concentric Ring Suite: Full-Disk Integration Box Mode Orthogonality and Solid Stator Reflection
- **Bug**: Integrating Casimir stress over a single oversized full-disk bounding box ($2.8\,\mu\text{m} \times 2.8\,\mu\text{m}$) caused the uniform $(0, 0)$ DCT mode to integrate identically to zero against the 4-fold rotor modulation while capturing a huge rotationally invariant reflection from the $88\%$ solid stator plate.
- **Solution**: Replaced the full-disk box with a tight bounding box around Sector 0 active teeth scaled by 4-fold rotational symmetry ($F_{\text{rotor}} = 4 \times F_{\text{sector 0}}$), centered the DCT basis coordinates with local face offsets, added a 2 nm numerical overhang to stator aperture prisms, and versioned checkpoints with `v2_`.

## [2026-10-08] Global Provenance Pipeline Omission & Figure Sidecar Absence
- **Bug**: Codebase lacked an automated end-to-end data provenance pipeline, omitting immutable figure sidecars (`*.provenance.json`), LaTeX macro synchronization, and manuscript mapping.
- **Solution**: Scaffolding `utils/metrics_logger.py` and authoring `execution/export_provenance_pipeline.py` via `gpt-6.1-sol`, exporting 86 grounded metrics to `results/provenance_metrics.json`, `results/macros_results.tex`, 28 figure sidecars, and `results/manuscript_provenance_map.json`.

## [2026-10-08] Uncentered DCT Spatial Coordinates in 3D FDTD Simulation Engines
- **Bug**: In `run_meep_simulation.py`, `run_rounded_convergence.py`, `run_geometric_repulsion_meep.py`, and `run_cantor_forest_meep.py`, `make_amp_func` omitted face center subtraction (`pt - center_vec`), evaluating spatial cosines with an unphysical offset that broke mode orthogonality on vertical and lateral faces.
- **Solution**: Centered DCT coordinates by subtracting `side_center` vectors across all bounding faces in the simulation engines.

## [2026-10-08] Trigonometric Inversion in Pyramid Corrugation Apex Truncation Height
- **Bug**: In `edge_rounding_geometry.py`, truncation formula computed $r_{\rm tip}(1/\cos(90^\circ - \alpha) - 1) = r_{\rm tip}(1/\sin\alpha - 1)$ instead of $r_{\rm tip}(1/\cos\alpha - 1)$, underestimating apex rounding truncation of $\alpha=75^\circ$ pyramids by $81\times$.
- **Solution**: Corrected apex truncation geometry to $r_{\rm tip}(1/\sin(90^\circ - \alpha) - 1) = r_{\rm tip}(1/\cos\alpha - 1)$.

## [2026-10-08] Cross-Frequency Forcing in Rotated Lorentzian Material Permittivity Tensors
- **Bug**: In `materials_database_dispersive.py`, the Y-axis oscillator strength of Black Phosphorus was assigned into the X-axis Lorentzian susceptibility with $\omega_{0,X} = 0.35\,\text{eV}$, driving the orthogonal zigzag resonance at the wrong frequency instead of $\omega_{0,Y} = 1.70\,\text{eV}$.
- **Solution**: Decoupled X-axis and Y-axis oscillators into distinct rotated Lorentzian susceptibility instances with exact material eigenfrequencies.

## [2026-10-08] Dimensional Inhomogeneity in 6-DOF Stiffness Matrix Symmetrization
- **Bug**: In `run_6dof_stability_analyzer.py`, $K_{\rm sym} = 0.5(K + K^T)$ directly summed translational stiffness entries ($\text{pN}/\mu\text{m}$) and rotational stiffness entries ($\text{pN}/\text{deg}$) without characteristic lever arm normalization.
- **Solution**: Converted angular perturbations to radians and normalized generalized coordinates by plate dimension $L$ to ensure dimensional homogeneity.

## [2026-10-08] Dimensionless MEEP Normal Pressure vs. Pascal Scale Discrepancy
- **Bug**: In `run_asymmetric_sweep.py` and sections of the Nature manuscript, dimensionless force over dimensionless area ($F_{\rm meep} / A_{\rm meep}$) was labeled in Pascals without multiplying by $\hbar c / a^4 = 0.031615\,\text{Pa}$.
- **Solution**: Explicitly distinguished dimensionless Meep pressure from physical pressure in Pascals across the provenance ledger, macros, and analytical documentation.

## [2026-10-08] Fixed-Precision Underflow in LaTeX Macro Export Engine
- **Bug**: In `utils/metrics_logger.py`, `export_macros` formatted all floating-point numbers with fixed 4-decimal precision (`f"{val:.4f}"`), rounding physical metrics smaller than $10^{-4}$ (including Lamb shift $\delta E_{\rm Lamb}=10^{-11}\,\text{eV}$ and scattering deviation $\Delta\sigma/\sigma_0=3\times 10^{-19}$) into zero.
- **Solution**: Implemented dynamic precision formatting that automatically switches to scientific notation for magnitudes $< 10^{-4}$ or $\ge 10^5$ and up to 6 significant digits for intermediate floats.

## [2026-10-08] Angular Area Distortion & Vertical Standoff Asymmetry in Concentric Ring Stress Box
- **Bug**: In `run_concentric_ring_meep.py`, dynamically computing the Sector 0 Cartesian bounding box from rotated tooth arc coordinates caused the integration box lateral area to swell by up to 23% at diagonal angles ($\theta=22.5^\circ$), distorting modal normalization in the truncated $n_{\max}=1$ DCT basis, while placing $z_{\rm bot}$ at $(2/3)z_{\rm tip}$ created asymmetric dielectric boundary layer proximity.
- **Solution**: Standardized Sector 0 integration box lateral dimensions to a fixed square bounding envelope across all rotation angles $\theta \in [0, 2\pi/N_{\rm sectors}]$ via full angular envelope scanning, centered $z_{\rm bot}$ symmetrically at the vacuum gap midpoint ($z_{\rm tip}/2.0$), and incremented the checkpoint version tag to `v3_`.
## [2026-10-09] Slurm Script Preemption Termination & Missing Telemetry Signal Traps
- **Bug**: Slurm batch scripts lacked POSIX signal trapping (`SIGUSR1@120`, `SIGTERM 143`, `SIGINT 130`) and automated continuation suppression, causing preempted or cancelled tasks (such as concentric ring Task 3) to abort with non-zero exit codes, trigger false failure alerts, and halt without recovering or resubmitting from atomic checkpoints.
- **Solution**: Re-created and validated all 24 primary campaign Slurm batch scripts using the `/bigred-slurm-telemetry` autonomous supervisor harness (`slurm_telemetry_harness.py`), adding walltime signal preemption (`#SBATCH --signal=B:SIGUSR1@120`), subshell process group isolation, automatic checkpoint resumption on preemption (`SIGTERM 143`), `resubmit_job` continuation suppression, and proxy-authenticated Git telemetry.

## [2026-10-12] Scoped Pilot Casimir Clutch Redesign & Meep DCT Kernel Restoration
- **Bug**: The initial concentric ring setup exhibited persistent repulsive levitation at all angles ($+1.37\,\text{pN} \to +8.38\,\text{pN}$ at $\theta=45^\circ$) due to insufficient aperture-bridge clearance ($5.4^\circ = 77\,\text{nm}$), membrane transparency ($25\,\text{nm}$ gold foil), and excessive runtime ($T_{\text{run}}=12.0$), while initial pilot code called a non-existent Meep API (`casimir_stress_tensor`) with single-double kernel pointer unpacking.
- **Solution**: Implemented redesigned asymmetric geometry ($30^\circ$ aperture, $60^\circ$ bridge with $150\,\text{nm}$ solid gold landing pad, $15^\circ$ rotor teeth providing $22.5^\circ = 324\,\text{nm}$ bridge clearance for true Kenneth-Klich attractive clamping at $\theta=45^\circ$), dynamically bounded $T_{\text{run}}=3.0$ ($\exp(-200)$ suppression, $4\times$ speedup to $7.47\,\text{hours}$), and restored Meep's verified C++/SWIG `casimir_stress_dct_integral` with interleaved complex array unpacking and telemetry lifecycle supervisor.

## [2026-10-13] BigRed 200: Hard mpi4py Dependency and Missing Conda Environment Activation
- **Bug**: Tasks 1–3 in the Scoped Pilot Clutch suite crashed on startup with exit code 1 because `run_scoped_clutch_meep.py` hard-required `mpi4py` under multi-rank MPI runs (`mp.count_processors() > 1`), which is not installed in BigRed 200's native C++ Meep conda environment, while `submit_clutch_pilot.sbatch` omitted `conda.sh` activation and `PYTHONPATH` exports.
- **Solution**: Made `mpi4py` strictly optional in `ParallelContext` with fallback to native Meep rank queries (`mp.am_master()`), enabled all ranks to read shared-filesystem checkpoints directly without MPI collective broadcast, added robust conda shell activation and `PYTHONPATH` to `submit_clutch_pilot.sbatch`, and aligned array log path resolution.

## [2026-10-13] BigRed 200: 481.27 GB (100.27%) Memory OOM Kill on Job 8557782
- **Bug**: Job 8557782 crashed after 1m42s with a kernel cgroup OOM kill (481.27 GB used vs 480.00 GB limit across 2 nodes) because `run_scoped_clutch_meep.py` set `force_complex_fields=True` (doubling memory of all 12 Yee field and PML components across 128 ranks) and inflated grid volume with `pml=0.25, buffer=0.15`.
- **Solution**: Removed `force_complex_fields=True` (reverting to real fields for imaginary-frequency Wick rotation), reduced boundary padding to `pml=0.20, buffer=0.10` (cutting grid volume by 26%), reconstructed Drude/Lorentzian poles explicitly without SWIG `copy.deepcopy`, and added `#SBATCH --exclude=nid0394`, reducing node memory to ~100 GB (42% capacity).

## [2026-10-13] Uncompromised Complex-Field FDTD Domain & Multi-Node Memory Scaling on BigRed 200
- **Bug**: Reverting to real fields (`force_complex_fields=False`) and trimming PML/buffer padding (`pml=0.20, buffer=0.10`) were rejected by project requirements requiring full complex-field electrodynamics and uncompromised physical absorbing boundaries ($20.2\,\mu\text{m}^3$), while running this domain on 2 nodes breached the 480 GB ceiling (481.27 GB).
- **Solution**: Restored full complex fields (`force_complex_fields=True`), full PML thickness ($0.25\,\mu\text{m}$), and full buffer standoff ($0.15\,\mu\text{m}$) in `run_scoped_clutch_meep.py`, and scaled Slurm allocation to 4 standard compute nodes (`--nodes=4 --mem=0 --ntasks-per-node=32 -c 4`), distributing the 481 GB Yee grid across 960 GB aggregate RAM (120 GB/node, 50% capacity).

## [2026-10-13] BigRed 200 Job 8560453: Missing `dims=3` in `mp.Volume` & Grounded Experiment Provenance Enforcement
- **Bug**: Job 8560453 initialized the complex-field domain cleanly in 69.3s (zero OOM), but aborted at step 0 with `Error: meep: invalid dimesionality in casimir_stress_dct_integral` because `mp.Volume(center=..., size=...)` omitted `dims=3` (causing Meep SWIG to construct a `D2` volume for 2D faces inside a `D3` simulation grid); additionally, an ungrounded synthetic 361-point angle scan was added to `stress_faces()`, `log_metrics()` swallowed exceptions without calling `log_step()` or verifying `results/provenance_metrics.json`, and `submit_clutch_pilot.sbatch` did not stage `results/` provenance artifacts.
- **Solution**: Added `dims=3` to `mp.Volume`, restored the exact tight Sector 0 tooth bounding box in `stress_faces()` (`CACHE_VERSION = 4`), enforced strict `/grounded-experiment-pipeline` Stage 1 provenance in `log_metrics()` (`log_step`, task-prefixed and canonical `log_metric`, `export_macros()`, and `[ERROR: RUN_DATA_MISSING]` verification on `results/provenance_metrics.json` and `results/macros_results.tex`), and added `results/` collection to `submit_clutch_pilot.sbatch`.

## [2026-10-13] Complete Code Audit: Unsharded Multi-Process Duplication (`mp.count_processors() == 1`), Dynamic `T_run` Tuple Unpacking, and Telemetry Git Race
- **Bug**: Under `srun` on BigRed 200, the conda `meep` binary reports `mp.count_processors() == 1` on every process, causing all $N$ Slurm tasks to execute duplicate copies of all 72 moments (`Initializing structure...` printed 128 times), multiply memory by $N\times$ ($128 \times 3.76\,\text{GB} = 481.27\,\text{GB}$), and race on shared checkpoint files; additionally, `invoke_dynamic_trun` did not unpack the `(run_time, diagnostics)` tuple or map `d_eff_um`, and concurrent array tasks collided on `.git/index.lock` and unstaged worktree changes during telemetry sync.
- **Solution**: Implemented Slurm moment-sharding in `ParallelContext` when `mp.count_processors() == 1` and `SLURM_NTASKS > 1` with lock-free per-shard checkpoint files merged by rank 0 (running 36 workers across 2 nodes at $67.7\,\text{GB/node}$ and 2 moments/worker), unpacked tuple returns and mapped `d_eff_um` in `invoke_dynamic_trun`, and added `fcntl.flock` telemetry serialization (`bigred200_telemetry.lock`), `--autostash` pull-rebase, and array-indexed crash report filenames in `submit_clutch_pilot.sbatch`.

## [2026-10-14] Scoped Pilot Casimir Clutch: make_casimir_gfunc Field-Type Enum Mismatch & Missing 4-Pass Stator Inclusion-Exclusion Subtraction

- **Bug:** The scoped pilot supplied component indices 0..5 instead of field-type enums to make_casimir_gfunc(t_run, dt, sigma, field_type) and omitted the four-pass stator inclusion-exclusion subtraction required across 144 moments per angle.
- **Solution:** Use mp.E_stuff=1 and mp.H_stuff=2 instead of component indices 0..5 in make_casimir_gfunc(t_run, dt, sigma, field_type), compute F_net = (F_both - F_rotor) - (F_stator - F_vac) across 144 moments per angle with CACHE_VERSION=5, and run Option D (N=2 3-track geometry at resolution=80 for theta=0 deg and theta=45 deg across 24 sharded workers on 2 nodes).

## [2026-10-14] BEM Near-Field Point-Collocation Singularity at $\theta=45^\circ$ & Windows Cross-Platform Solver Comparison Pilot
- **Bug:** At $\theta=45^\circ$ (engaged state, $z_{\text{tip}}=15\text{ nm}$ vertical gap vs. $\sim 200\text{ nm}$ panel width), point-to-point centroid collocation $1/(4\pi |\mathbf{r}_i - \mathbf{r}_j|)$ in `_yukawa_blocks` exceeded the equal-area disk diagonal self-term $\sqrt{A_i}/(2\sqrt{\pi})$, breaking positive-definiteness of the Schur complement $I - w^2 M_R^{-1} G_{RS} M_S^{-1} G_{SR}$ (`FloatingPointError: A scattering determinant is not positive-real`), while `run_solver_comparison_pilot.py` imported Unix-only `resource` and required `shapely` at module import time on Windows.
- **Solution:** Replaced off-diagonal point distance in `execution/casimir_bem_solver.py` with the finite-panel regularized distance $R_{\text{eff},ij} = \sqrt{|\mathbf{r}_i - \mathbf{r}_j|^2 + (A_i + A_j)/(8\pi)}$ (which smoothly matches the exact equal-area disk diagonal at $R_{ii}=0$ and guarantees positive-definite scattering matrices across all gap-to-panel aspect ratios), and updated `execution/run_solver_comparison_pilot.py` to use cross-platform `tracemalloc` and native numpy radial-annulus area evaluation.

## [2026-10-15] Stepped-Elevation Rotational Clutch Meep Stress-Box Stator Intersection & Diagnostics Unpacking
- **Bug:** `execution/run_scoped_clutch_meep.py` assumed $z_{\text{tip}} > 0$ (`sigma = 0.5 / max(0.010, self.z_tip)`) and placed a single Cartesian stress box across all Sector 0 teeth at $z_{\text{bot}} = z_{\text{tip}}/2$, which intersected the solid intermediate Cantor stator rings at $z \in [-0.025, 0]\,\mu\text{m}$ when $z_{\text{tip}} = -0.100\,\mu\text{m}$; additionally, `execution/generate_rotational_z_eff_meep_configs.py` unpacked `(run_time, sigma)` from `compute_dynamic_Trun` assuming the second element was a float rather than the `TrunDiagnostics` dictionary.
- **Solution:** Added `per_tooth_rotor_frame` mode to `execution/run_scoped_clutch_meep.py` and `z_pad_top` stepped-elevation support to `execution/clutch_geometry_redesign.py` (keeping Sector 0 teeth centered at $\phi = 0^\circ$ along $+x$, rotating the stator by $-(15^\circ + \theta_{\text{deg}})$, and constructing per-tooth 6-face vacuum stress boxes strictly inside each open radial slot $(r_{\text{inner},i}, r_{\text{outer},i})$ with $z_{\text{bot}} = 0.5(z_{\text{tip}} + z_{\text{pad,top}}) = -0.1075\,\mu\text{m}$), and extracted `Sigma` from the `TrunDiagnostics` mapping in `execution/generate_rotational_z_eff_meep_configs.py`.

## [2026-10-15] 3-Solver Multi-Resolution Verification Provenance API & Vertical Tooth Overhang Analysis
- **Bug:** `execution/run_rotational_clutch_3solver_verification.py` imported `concentric_cantor` as a symbol instead of passing `'concentric_cantor'` as a string to `resolve_design`, passed positional/keyword arguments incompatible with `utils/metrics_logger.py` (`log_step(step, ...)`, `log_metric(..., step=step)`, `export_macros(output_path)`, and `save_plot_provenance(path, payload)`), and revealed that `H_TEETH_UM = 0.250` ($z \in [-100, +150]\text{ nm}$) causes $150\text{ nm}$ of upper tooth wall to overhang above the $[-25, 0]\text{ nm}$ stator ring, reversing the aperture force sign when $n_z \ge 3$.
- **Solution:** Fixed the `resolve_design` string argument and `utils.metrics_logger` calls (`log_step`, `log_metric`, `export_macros`, `save_plot_provenance`) in `execution/run_rotational_clutch_3solver_verification.py`, completed the full 27-task multi-resolution verification (`Standard`, `High`, `Ultra_High`), and verified that setting `H_TEETH_UM = 0.100` ($z_{\text{tooth}} \in [-100, 0]\text{ nm}$, flush with the stator ring top) restores strictly positive repulsive aperture force across all `Standard`, `High`, and `Ultra_High` resolution tiers.

## [2026-10-15] BigRed 200 Job 8578388 (`fce_mrot`): Missing Slurm Log Directory, Pre-Conda `import meep` Check, & Unauthenticated Telemetry Push
- **Bug:** Job 8578388 (`execution/submit_rotational_z_eff_meep.sbatch`) failed on BigRed 200 without pushing a crash report because `#SBATCH -o/-e` pointed to `cluster_diagnostics/raw_logs/%x_%j.out` (an untracked empty directory absent on BigRed 200), tested `"$candidate_python" -c 'import meep'` before sourcing `conda.sh` and exporting `LD_LIBRARY_PATH="$ENV_PREFIX/lib"`, lacked the `BIGRED200_AUTH_PYTHON` token discovery and `fcntl.flock` telemetry serialization from `submit_clutch_pilot.sbatch`, and ignored `--output-file` when writing `final_path` in `execution/run_scoped_clutch_meep.py`.
- **Solution:** Updated `execution/submit_rotational_z_eff_meep.sbatch` to use the existing `logs/%x_%A_%a.out` path, full Conda environment activation (`conda.sh` + `LD_LIBRARY_PATH`) before invoking Python, `BIGRED200_AUTH_PYTHON` unattended Git authentication, and `fcntl.flock` telemetry serialization; updated `execution/run_scoped_clutch_meep.py` to honor `--output-file` for `final_path` and `progress_path`; and regenerated all 21 `sweep_configs_rotational_z_eff_meep/config_*.json` files with `H_teeth_um = 0.100`.

## [2026-10-15] Fractal Advantage Study Sector Radian Meshing & Concurrent Provenance JSON Write Contention
- **Bug:** The initial draft of `execution/run_fractal_advantage_study.py` emitted all four 90-degree quadrants in degrees without `PanelType` bindings instead of a single radian-valued 90-degree sector for `ClutchSurfaceMesh`, and `utils/metrics_logger.py` wrote `results/provenance_metrics.json` non-atomically via `open(path, "w")`, triggering `JSONDecodeError` when concurrent BEM processes accessed the manifest simultaneously.
- **Solution:** Updated `execution/run_fractal_advantage_study.py` via `gpt-6.1-sol` to emit single-sector radian panels with exact `PanelType` bindings and `utils.metrics_logger` arguments, and upgraded `utils/metrics_logger.py` via `gpt-6.1-sol` to use atomic temporary files with retry-backed `os.replace` and read retries.

## [2026-10-15] Nature 6-Step Narrative Suite: Single-Sector Radian Meshing & Full-Monolithic Passive Support Integration
- **Bug:** The initial draft of `execution/run_nature_6step_narrative.py` emitted 4-quadrant degree-valued panels without `PanelType` bindings and omitted the full-monolithic passive rotor/stator support surfaces (spider spokes, inner/outer collars, and release trench floor) in its custom geometry builder.
- **Solution:** Updated `execution/run_nature_6step_narrative.py` via `gpt-6.1-sol` to emit single-sector radian panels with `PanelType` bindings, integrated `build_passive_monolithic_panels` for full-monolithic validation in Step 6, and verified all 67 narrative tasks across `Standard`, `High`, and `Ultra_High` resolutions.

## [2026-10-15] Nature Meep Verification Suite: Per-Element $(r,z)$ Stress Box Support & Campaign Checkpoint Isolation
- **Bug:** `execution/clutch_geometry_redesign.py` and `execution/run_scoped_clutch_meep.py` used a single global `z_tip` and `h_teeth` across all radial tracks (preventing per-track elevation overrides for `Cantor_N2_HybridRZ`) and hardcoded `.tmp/chk_moments_clutch_pilot_task_*` checkpoint prefixes across campaigns, while the initial draft of `execution/generate_nature_meep_verification_configs.py` omitted `r_center`, `r_tooth_in`, `r_tooth_out`, and `geometry` keys.
- **Solution:** Updated `execution/clutch_geometry_redesign.py`, `execution/run_scoped_clutch_meep.py`, and `execution/generate_nature_meep_verification_configs.py` via `gpt-6.1-sol` to support optional per-element `z_tip` and `h_teeth` overrides, campaign-isolated `--checkpoint-prefix chk_moments_nature_verify_task`, and full 12-task configuration generation with Unix LF line endings in `execution/submit_nature_meep_verification.sbatch`.

## [2026-10-15] BigRed 200 Job 8580784 (`fce_mrot`): Compute-Node `proxy.uits.iu.edu` DNS Failure & 45s Lustre Git Timeout
- **Bug:** In Job 8580784, all 6 array tasks completed 100% of their 432 Meep moments in ~19.6 minutes and wrote `results_rotational_z_eff_meep/task_*_meep.json`, but failed at the end when the pre-update `utils/metrics_logger.py` lacked `set_solver_provenance`, while `export http_proxy=http://proxy.uits.iu.edu:3128` caused `git push` to fail with `Could not resolve proxy: proxy.uits.iu.edu` on compute nodes and `GIT_TIMEOUT_SECONDS = 45` timed out during `git commit` on Lustre.
- **Solution:** Removed `proxy.uits.iu.edu` (`unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY`), increased `GIT_TIMEOUT_SECONDS` to `180`s, and extended the telemetry lock deadline to `300`s in both `execution/submit_nature_meep_verification.sbatch` and `execution/submit_rotational_z_eff_meep.sbatch`.

## [2026-10-15] 6-Pole Gold Lorentzian Damping Leapfrog Instability at $\Delta t = 0.01$ (`resolution=50, Courant=0.5`)
- **Bug:** In `execution/run_scoped_clutch_meep.py`, `material_pair()` added the large Wick conductivity $\Sigma = 33.3\text{–}100.0\,\mu\text{m}^{-1}$ directly into the 6-pole Rakic Gold Lorentzian susceptibility damping (`gamma = sus.gamma + parameters.sigma`) on top of `D_conductivity = parameters.sigma`, making $2\pi \gamma_{\text{tot}} \Delta t = 2.217 > 2$ at $\Delta t = 0.01$ (`resolution = 50, Courant = 0.5`) and causing exponential FDTD polarization blowup to $10^{44}$ in `Job 8580784` (`results_rotational_z_eff_meep/task_*_meep.json`), whereas `task_001_N2_th_0deg.json` at $\Delta t = 0.00625$ (`resolution = 80`) remained stable.
- **Solution:** Restored physical Rakic Gold damping (`gamma = sus.gamma`) in `execution/run_scoped_clutch_meep.py` (since `D_conductivity` and `B_conductivity` already apply the Meep Wick conductivity), set `eps_averaging = False` on `mp.Simulation`, bumped `CACHE_VERSION = 6` to invalidate unstable checkpoints, and reduced `courant` to `0.3` ($\Delta t \le 0.0060 < 0.00625$) across `sweep_configs_nature_meep_verification/` and `sweep_configs_rotational_z_eff_meep/`.

## [2026-10-15] 1-Point BEM Centroid Smoothing Gap Inflation at $d=15\text{ nm}$ & Unresolved `n_z=1` Tooth Sidewall
- **Bug:** 1-point centroid collocation with full-panel area smoothing $\sqrt{d^2 + (A_i + A_j)/(8\pi)}$ in `execution/casimir_bem_solver.py` artificially inflated the $15\text{ nm}$ vertical gap at $\theta = 48^\circ$ when panel widths exceeded $60\text{ nm}$, while `Standard` (`n_z = 1`) in `execution/run_nature_6step_narrative.py` placed the single sidewall centroid at $z = -50\text{ nm}$ below the $[-25, 0]\text{ nm}$ stator ring, causing large jumps between `Standard`, `High`, and `Ultra_High`.
- **Solution:** Upgraded `execution/casimir_bem_solver.py` via `gpt-6.1-sol` to integrate off-diagonal panel pairs using $2\times 2$ bilinear Gauss-Legendre sub-panel quadrature over quadrilateral panel vertices (with sub-panel area variance $(A_i + A_j)/(32\pi)$) and finite-temperature ($T > 0\text{ K}$) Matsubara + Euler-Maclaurin summation; updated `STANDARD` in `execution/run_nature_6step_narrative.py` to `n_z = 2` with `vector_dyadic` default and scale-matched `Cantor_N2_HybridRZ` ($z_{\text{tip}} = -90\text{ nm}$ on daughter tracks).

## [2026-10-15] Cantor Generation-Order Track Unsorted Failure for `Rot_C8_Compact_N2` in Feasibility Suite
- **Bug:** In `execution/run_nature_feasibility_and_stability.py`, `get_scoped_clutch_elements(N=2, R_min=0.20, R_max=0.90, w1_ratio=0.45, min_tooth_w=0.020)` returned tracks in Cantor generation order (`[level 1 middle track, level 2 inner track, level 2 outer track]`) rather than radial order, causing `validate_design` to raise `ValueError: Overlapping or invalid track in Rot_C8_Compact_N2`.
- **Solution:** Sorted `elements` by `r_inner` (`elements.sort(key=...)`) in `prepare_designs()` of `execution/run_nature_feasibility_and_stability.py` via `gpt-6.1-sol` before constructing `compact_tracks`.
