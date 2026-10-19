"""
Realistic Anisotropic Drude-Lorentz Material Dispersion Database
----------------------------------------------------------------
Provides full Kramers-Kronig compliant multi-oscillator dielectric tensors
for van der Waals 2D materials (Black Phosphorus, ReS2, MoS2), metals (Gold),
semiconductors (Silicon), and immersion screening liquids/dielectrics.

Addresses Nature Reviewer Issue 2:
Replaces idealized lossless tuning with realistic experimental optical constants,
interband transitions, and complex dissipation along the imaginary frequency axis xi.
"""

import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import numpy as np

try:
    import meep as mp
except ImportError:
    mp = None

# Convert photon energy in eV to Meep real cyclic frequency (a = 1 micron):
# f = E / (h*c) = E [eV] / (1.23984193 eV * um).
EV_TO_MEEP_FREQ = 1.0 / 1.23984193

# Convert imaginary wavenumber xi/c in rad/um to photon energy in eV.
HBAR_C_EV_UM = 0.1973269804


# ==============================================================================
# 1. Black Phosphorus (BP) Multi-Oscillator Drude-Lorentz Parameters
#    Fitted to Spectroscopic Ellipsometry & DFT (Prishchepa et al. / Ribeiro et al.)
# ==============================================================================
# Armchair (x-axis, high in-plane mobility / strong fundamental absorption):
BP_OSCILLATORS_X = [
    {"E0_eV": 0.35, "f_eV2": 1.45, "gamma_eV": 0.045},  # Fundamental excitonic interband peak
    {"E0_eV": 1.55, "f_eV2": 3.80, "gamma_eV": 0.180},  # Higher-order interband resonance
    {"E0_eV": 2.80, "f_eV2": 5.20, "gamma_eV": 0.350},  # Deep UV interband transition
    {"E0_eV": 4.25, "f_eV2": 8.10, "gamma_eV": 0.650}   # High-energy plasma shoulder
]
BP_EPS_INF_X = 9.80

# Zigzag (y-axis, optically forbidden fundamental gap, strong orthogonal resonance):
BP_OSCILLATORS_Y = [
    {"E0_eV": 1.70, "f_eV2": 3.20, "gamma_eV": 0.120},  # Orthogonal interband onset
    {"E0_eV": 2.45, "f_eV2": 4.10, "gamma_eV": 0.220},  # Secondary band transition
    {"E0_eV": 3.10, "f_eV2": 4.90, "gamma_eV": 0.380},  # UV resonance
    {"E0_eV": 4.60, "f_eV2": 7.50, "gamma_eV": 0.700}   # High-energy transition
]
BP_EPS_INF_Y = 7.10

# Out-of-plane (z-axis, interlayer polarization):
BP_OSCILLATORS_Z = [
    {"E0_eV": 2.20, "f_eV2": 1.80, "gamma_eV": 0.250},
    {"E0_eV": 4.10, "f_eV2": 3.50, "gamma_eV": 0.600}
]
BP_EPS_INF_Z = 5.50


# ==============================================================================
# 2. Rhenium Disulfide (ReS2) Anisotropic Optical Constants
# ==============================================================================
RES2_OSCILLATORS_A = [
    {"E0_eV": 1.52, "f_eV2": 2.10, "gamma_eV": 0.080},
    {"E0_eV": 1.85, "f_eV2": 3.40, "gamma_eV": 0.150},
    {"E0_eV": 2.90, "f_eV2": 4.80, "gamma_eV": 0.400}
]
RES2_EPS_INF_A = 6.20

RES2_OSCILLATORS_B = [
    {"E0_eV": 1.61, "f_eV2": 1.80, "gamma_eV": 0.090},
    {"E0_eV": 2.10, "f_eV2": 2.90, "gamma_eV": 0.180},
    {"E0_eV": 3.20, "f_eV2": 4.20, "gamma_eV": 0.450}
]
RES2_EPS_INF_B = 5.40


# ==============================================================================
# 3. Immersion Screening Dielectric Media
# ==============================================================================
IMMERSION_MEDIA = {
    "Vacuum": {"eps_static": 1.0, "eps_inf": 1.0, "uv_pole_eV": 10.0},
    "Teflon_AF": {"eps_static": 1.89, "eps_inf": 1.84, "uv_pole_eV": 7.8},
    "Ethanol": {"eps_static": 1.85, "eps_inf": 1.83, "uv_pole_eV": 9.2},
    "Bromobenzene": {"eps_static": 2.40, "eps_inf": 2.38, "uv_pole_eV": 6.5},
    "Glycerol": {"eps_static": 2.18, "eps_inf": 2.15, "uv_pole_eV": 8.4},
    "Cyclohexane": {"eps_static": 2.02, "eps_inf": 2.01, "uv_pole_eV": 8.0}
}


def evaluate_lorentz_eps_imag(xi_meep, eps_inf, oscillators):
    """
    Evaluates epsilon(i*xi) along the imaginary frequency axis for a multi-oscillator Lorentz model.
    eps(i*xi) = eps_inf + sum_k [ f_k / (omega_0k^2 + xi^2 + gamma_k * xi) ]

    Parameters:
    -----------
    xi_meep : float or np.ndarray
        Imaginary wavenumber xi/c in rad/um (a = 1 um).
    eps_inf : float
        High-frequency permittivity limit.
    oscillators : list of dict
        Oscillator parameters with 'E0_eV', 'f_eV2', 'gamma_eV'.

    Returns:
    --------
    float or np.ndarray
        Real, positive permittivity epsilon(i*xi).
    """
    # Convert imaginary wavenumber to energy: hbar * xi = (xi/c) * hbar*c.
    xi_eV = xi_meep * HBAR_C_EV_UM

    eps_val = np.full_like(xi_eV, float(eps_inf), dtype=float) if isinstance(xi_eV, np.ndarray) else float(eps_inf)

    for osc in oscillators:
        w0 = osc["E0_eV"]
        f_k = osc["f_eV2"]
        gam = osc["gamma_eV"]
        denom = w0**2 + xi_eV**2 + gam * xi_eV + 1e-30
        eps_val += f_k / denom

    return eps_val


def get_dielectric_tensor_imag(material_name, xi_meep, theta_deg=0.0):
    """
    Returns the full 3x3 dielectric tensor epsilon(i*xi) rotated by angle theta in the xy-plane.

    Returns:
    --------
    eps_xx, eps_yy, eps_zz, eps_xy : float or np.ndarray
    """
    theta_rad = np.radians(theta_deg)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)

    if material_name in ["BlackPhosphorus", "Phosphorene", "Phosphorene_tuned", "BP_realistic"]:
        eps_x = evaluate_lorentz_eps_imag(xi_meep, BP_EPS_INF_X, BP_OSCILLATORS_X)
        eps_y = evaluate_lorentz_eps_imag(xi_meep, BP_EPS_INF_Y, BP_OSCILLATORS_Y)
        eps_z = evaluate_lorentz_eps_imag(xi_meep, BP_EPS_INF_Z, BP_OSCILLATORS_Z)
    elif material_name == "ReS2":
        eps_x = evaluate_lorentz_eps_imag(xi_meep, RES2_EPS_INF_A, RES2_OSCILLATORS_A)
        eps_y = evaluate_lorentz_eps_imag(xi_meep, RES2_EPS_INF_B, RES2_OSCILLATORS_B)
        eps_z = np.full_like(eps_x, 4.5)
    elif material_name == "Gold":
        # Brendel-Bormann model for Au
        from execution.run_pfa_model import get_epsilon_imag
        eps_iso = np.array([get_epsilon_imag(x, "Gold") for x in np.atleast_1d(xi_meep)])
        eps_x = eps_y = eps_z = eps_iso[0] if np.isscalar(xi_meep) else eps_iso
    elif material_name == "Silicon":
        from execution.run_pfa_model import get_epsilon_imag
        eps_iso = np.array([get_epsilon_imag(x, "Silicon") for x in np.atleast_1d(xi_meep)])
        eps_x = eps_y = eps_z = eps_iso[0] if np.isscalar(xi_meep) else eps_iso
    elif material_name in IMMERSION_MEDIA:
        med = IMMERSION_MEDIA[material_name]
        eps_iso = evaluate_lorentz_eps_imag(
            xi_meep,
            med["eps_inf"],
            [{"E0_eV": med["uv_pole_eV"], "f_eV2": (med["eps_static"] - med["eps_inf"]) * med["uv_pole_eV"]**2, "gamma_eV": 0.1}]
        )
        eps_x = eps_y = eps_z = eps_iso
    else:
        # Default isotropic constant
        val = 2.1
        eps_x = eps_y = eps_z = np.full_like(xi_meep, val, dtype=float) if isinstance(xi_meep, np.ndarray) else val

    # Rotate in xy-plane:
    eps_xx = eps_x * C**2 + eps_y * S**2
    eps_yy = eps_x * S**2 + eps_y * C**2
    eps_zz = eps_z
    eps_xy = (eps_x - eps_y) * S * C

    return eps_xx, eps_yy, eps_zz, eps_xy


def get_meep_dispersive_medium(material_name, Sigma, ft, theta_deg=0.0):
    """
    Constructs an authentic MEEP mp.Medium with physical multi-oscillator
    Lorentz susceptibilities and conductivity damping.
    """
    if mp is None:
        return None

    theta_rad = np.radians(theta_deg)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)

    cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}

    if material_name in ["BlackPhosphorus", "Phosphorene", "Phosphorene_tuned", "BP_realistic", "ReS2"]:
        if material_name == "ReS2":
            eps_inf_x = RES2_EPS_INF_A
            eps_inf_y = RES2_EPS_INF_B
            eps_inf_z = 4.5
            oscillators_x = RES2_OSCILLATORS_A
            oscillators_y = RES2_OSCILLATORS_B
            oscillators_z = []
        else:
            eps_inf_x = BP_EPS_INF_X
            eps_inf_y = BP_EPS_INF_Y
            eps_inf_z = BP_EPS_INF_Z
            oscillators_x = BP_OSCILLATORS_X
            oscillators_y = BP_OSCILLATORS_Y
            oscillators_z = BP_OSCILLATORS_Z

        eps_xx_inf = eps_inf_x * C**2 + eps_inf_y * S**2
        eps_yy_inf = eps_inf_x * S**2 + eps_inf_y * C**2
        eps_zz_inf = eps_inf_z
        eps_xy_inf = (eps_inf_x - eps_inf_y) * S * C

        susceptibilities = []

        # Each principal-axis oscillator retains its own resonance and damping.
        # Sigma is applied only through the medium conductivity.
        for osc in oscillators_x:
            freq_meep = osc["E0_eV"] * EV_TO_MEEP_FREQ
            gamma_meep = osc["gamma_eV"] * EV_TO_MEEP_FREQ
            sig_x = (osc["f_eV2"] * EV_TO_MEEP_FREQ**2) / freq_meep**2

            susceptibilities.append(mp.LorentzianSusceptibility(
                frequency=freq_meep,
                gamma=gamma_meep,
                sigma_diag=mp.Vector3(sig_x * C**2, sig_x * S**2, 0.0),
                sigma_offdiag=mp.Vector3(0.0, 0.0, sig_x * S * C)
            ))

        for osc_y in oscillators_y:
            freq_meep = osc_y["E0_eV"] * EV_TO_MEEP_FREQ
            gamma_meep = osc_y["gamma_eV"] * EV_TO_MEEP_FREQ
            sig_y = (osc_y["f_eV2"] * EV_TO_MEEP_FREQ**2) / freq_meep**2

            susceptibilities.append(mp.LorentzianSusceptibility(
                frequency=freq_meep,
                gamma=gamma_meep,
                sigma_diag=mp.Vector3(sig_y * S**2, sig_y * C**2, 0.0),
                sigma_offdiag=mp.Vector3(0.0, 0.0, -sig_y * S * C)
            ))

        for osc_z in oscillators_z:
            freq_meep = osc_z["E0_eV"] * EV_TO_MEEP_FREQ
            gamma_meep = osc_z["gamma_eV"] * EV_TO_MEEP_FREQ
            sig_z = (osc_z["f_eV2"] * EV_TO_MEEP_FREQ**2) / freq_meep**2

            susceptibilities.append(mp.LorentzianSusceptibility(
                frequency=freq_meep,
                gamma=gamma_meep,
                sigma_diag=mp.Vector3(0.0, 0.0, sig_z)
            ))

        return mp.Medium(
            epsilon_diag=mp.Vector3(eps_xx_inf, eps_yy_inf, eps_zz_inf),
            epsilon_offdiag=mp.Vector3(eps_xy_inf, 0.0, 0.0),
            E_susceptibilities=susceptibilities,
            **cond_attr
        )
    elif material_name in ["Gold", "Silicon"]:
        from meep.materials import Au, cSi
        base_medium = Au if material_name == "Gold" else cSi
        new_sus = []
        for sus in base_medium.E_susceptibilities:
            freq = sus.frequency
            gamma = sus.gamma
            gamma_val = gamma
            if isinstance(sus, mp.DrudeSusceptibility):
                if freq < 1e-5:
                    sigma_val = sus.sigma_diag.x * (freq ** 2)
                    freq_val = 1.0
                else:
                    sigma_val = sus.sigma_diag.x
                    freq_val = freq
                new_sus.append(mp.DrudeSusceptibility(
                    frequency=freq_val,
                    gamma=gamma_val,
                    sigma=sigma_val
                ))
            elif isinstance(sus, mp.LorentzianSusceptibility):
                new_sus.append(mp.LorentzianSusceptibility(
                    frequency=freq,
                    gamma=gamma_val,
                    sigma=sus.sigma_diag.x
                ))
        return mp.Medium(
            epsilon=base_medium.epsilon_diag.x,
            E_susceptibilities=new_sus,
            **cond_attr
        )
    elif material_name in IMMERSION_MEDIA:
        med = IMMERSION_MEDIA[material_name]
        susceptibilities = []
        sigma_uv = med["eps_static"] - med["eps_inf"]
        if sigma_uv != 0.0:
            susceptibilities.append(mp.LorentzianSusceptibility(
                frequency=med["uv_pole_eV"] * EV_TO_MEEP_FREQ,
                gamma=0.1 * EV_TO_MEEP_FREQ,
                sigma=sigma_uv
            ))
        return mp.Medium(
            epsilon=med["eps_inf"],
            E_susceptibilities=susceptibilities,
            **cond_attr
        )
    else:
        return mp.Medium(epsilon=2.1, **cond_attr)
