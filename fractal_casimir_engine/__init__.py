"""Fractal Casimir Engine package.

Implements chiral multi-scale Cantor NEMS geometries (Configurations B, C, and D
plus a symmetric Cantor control), exact 3D BEM (E_C, F_z, tau_theta) cycle mapping,
coupled axial-rotary dynamics, provenance logging, and Blender 3D animation export.
"""

from __future__ import annotations

__all__ = [
    "ENGINE_DESIGN_NAMES",
]

ENGINE_DESIGN_NAMES: tuple[str, ...] = (
    "Sym_Baseline_CantorN2",
    "Config_B_Manhattan_Vernier",
    "Config_C_Helical_Turbine",
    "Config_D_DualStator_PushPull",
)
