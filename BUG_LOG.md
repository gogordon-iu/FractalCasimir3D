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



