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
