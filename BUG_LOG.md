# Bug Log

## [2026-09-10] Corrugation Angle Omission in FDTD Sweep Output Filename & Cache Check
- **Bug**: 3D FDTD simulation output filenames omitted the corrugation angle $\alpha$, causing different corrugation angles at identical $(d, \theta)$ to hit the cache check and prematurely skip execution.
- **Solution**: Incorporated `_al_{corrugation_angle:.1f}` into the filename generation and added strict corrugation angle matching in cache verification.
