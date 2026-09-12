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
