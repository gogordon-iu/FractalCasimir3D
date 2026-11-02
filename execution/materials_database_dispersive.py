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

# ==============================================================================
# 0. Fundamental CODATA 2018 Physical & Mechanical Constants
# ==============================================================================
HBAR_SI_J_S = 1.054571817e-34
C_LIGHT_SI_M_S = 299_792_458.0
E_CHARGE_SI_C = 1.602176634e-19
BOLTZMANN_K_SI_J_PER_K = 1.380649e-23
BOLTZMANN_K_EV_PER_K = 8.617333262145e-5
EPSILON_0_F_PER_M = 8.8541878128e-12
ROOM_TEMPERATURE_K = 300.0

# Convert photon energy in eV to Meep real cyclic frequency (a = 1 micron):
# f = E / (h*c) = E [eV] / (1.23984193 eV * um).
HC_EV_UM = 1.23984193
EV_TO_MEEP_FREQ = 1.0 / HC_EV_UM

# Convert imaginary wavenumber xi/c in rad/um to photon energy in eV.
HBAR_C_EV_UM = 0.1973269804

# Energy/force/pressure conversions in Meep units (a = 1 um, hbar = c = 1):
HBAR_C_PN_UM2 = 0.031615267735
KB_T_300_PN_UM = 4.141947e-3
MEEP_FORCE_TO_SI = 3.16152649e-14
MEEP_FORCE_TO_NN = MEEP_FORCE_TO_SI * 1e9
MEEP_TO_PA = 0.0316152649
KB_MEEP_PER_K = BOLTZMANN_K_EV_PER_K / HBAR_C_EV_UM

# Single-crystal Silicon <110> Young's modulus for NEMS suspension tethers.
SILICON_YOUNGS_MODULUS_GPA = 169.0
SILICON_YOUNGS_MODULUS_PA = SILICON_YOUNGS_MODULUS_GPA * 1e9

# Planar Sierpinski carpet per-generation area retention fraction.
SIERPINSKI_AREA_RATIO = 8.0 / 9.0


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

# Out-of-plane (c/z-axis, interlayer van der Waals polarization):
RES2_OSCILLATORS_C = []
RES2_EPS_INF_C = 4.50
RES2_OSCILLATORS_Z = RES2_OSCILLATORS_C
RES2_EPS_INF_Z = RES2_EPS_INF_C


# ==============================================================================
# 3. Isotropic Metals & Semiconductors (Gold & Crystalline Silicon)
# ==============================================================================
GOLD_EPS_INF = 1.0
GOLD_WP_EV = 9.03
GOLD_GAMMA_EV = 0.053
GOLD_OSCILLATORS = []

SILICON_EPS_INF = 1.0
SILICON_EPS_STATIC = 11.87
SILICON_E0_EV = 3.64
SILICON_GAMMA_EV = 0.10
SILICON_OSCILLATORS = [
    {
        "E0_eV": SILICON_E0_EV,
        "f_eV2": (SILICON_EPS_STATIC - SILICON_EPS_INF) * (SILICON_E0_EV ** 2),
        "gamma_eV": SILICON_GAMMA_EV,
    }
]

# Structural NEMS dielectrics (Si3N4 UV Lorentz oscillator in rad/um and SiO2 static limit)
SILICON_NITRIDE_EPS_INF = 1.0
SILICON_NITRIDE_CHI_UV = 2.89
SILICON_NITRIDE_OMEGA_0_INV_UM = 5.85
SILICON_NITRIDE_GAMMA_INV_UM = 0.10
SILICON_NITRIDE_EPS_STATIC = SILICON_NITRIDE_EPS_INF + SILICON_NITRIDE_CHI_UV
SILICA_EPS_STATIC = 2.10


# ==============================================================================
# 4. Immersion Screening Dielectric Media
# ==============================================================================
DEFAULT_IMMERSION_GAMMA_EV = 0.10

IMMERSION_MEDIA = {
    "Vacuum": {"eps_static": 1.0, "eps_inf": 1.0, "uv_pole_eV": 10.0, "gamma_eV": DEFAULT_IMMERSION_GAMMA_EV},
    "Teflon_AF": {"eps_static": 1.89, "eps_inf": 1.84, "uv_pole_eV": 7.8, "gamma_eV": DEFAULT_IMMERSION_GAMMA_EV},
    "Ethanol": {"eps_static": 1.85, "eps_inf": 1.83, "uv_pole_eV": 9.2, "gamma_eV": DEFAULT_IMMERSION_GAMMA_EV},
    "Bromobenzene": {"eps_static": 2.40, "eps_inf": 2.38, "uv_pole_eV": 6.5, "gamma_eV": DEFAULT_IMMERSION_GAMMA_EV},
    "Glycerol": {"eps_static": 2.18, "eps_inf": 2.15, "uv_pole_eV": 8.4, "gamma_eV": DEFAULT_IMMERSION_GAMMA_EV},
    "Cyclohexane": {"eps_static": 2.02, "eps_inf": 2.01, "uv_pole_eV": 8.0, "gamma_eV": DEFAULT_IMMERSION_GAMMA_EV}
}


def _validate_xi_meep(xi_meep, *, strictly_positive=False):
    """Validate imaginary wavenumber input (scalar float or numpy ndarray)."""
    if isinstance(xi_meep, (bool, np.bool_, str, bytes)):
        raise TypeError("xi_meep must be a real scalar or numpy array.")
    is_scalar = np.isscalar(xi_meep)
    xi_arr = np.asarray(xi_meep, dtype=float)
    if not np.all(np.isfinite(xi_arr)):
        raise ValueError("xi_meep must be finite.")
    if strictly_positive:
        if np.any(xi_arr <= 0.0):
            raise ValueError("xi_meep must be strictly positive.")
    elif np.any(xi_arr < 0.0):
        raise ValueError("xi_meep must be nonnegative.")
    return (float(xi_arr) if is_scalar else xi_arr), is_scalar


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
    xi_val, is_scalar = _validate_xi_meep(xi_meep)
    eps_inf_val = float(eps_inf)
    if not np.isfinite(eps_inf_val) or eps_inf_val <= 0.0:
        raise ValueError("eps_inf must be finite and positive.")

    # Convert imaginary wavenumber to energy: hbar * xi = (xi/c) * hbar*c.
    xi_eV = xi_val * HBAR_C_EV_UM

    eps_val = float(eps_inf_val) if is_scalar else np.full_like(xi_eV, eps_inf_val, dtype=float)

    for osc in oscillators:
        w0 = float(osc["E0_eV"])
        f_k = float(osc["f_eV2"])
        gam = float(osc["gamma_eV"])
        if (
            not (np.isfinite(w0) and np.isfinite(f_k) and np.isfinite(gam))
            or w0 <= 0.0
            or f_k < 0.0
            or gam < 0.0
        ):
            raise ValueError("Oscillator parameters must be finite with E0_eV > 0, f_eV2 >= 0, gamma_eV >= 0.")
        denom = w0**2 + xi_eV**2 + gam * xi_eV
        eps_val = eps_val + f_k / denom

    return float(eps_val) if is_scalar else eps_val


def evaluate_drude_lorentz_eps_imag(xi_meep, eps_inf, wp_eV, gamma_eV, oscillators=()):
    """
    Evaluates epsilon(i*xi) for a Drude-Lorentz metal along the imaginary frequency axis:
    eps(i*xi) = eps_inf + wp^2 / (xi * (xi + gamma)) + sum_k [ f_k / (omega_0k^2 + xi^2 + gamma_k * xi) ]
    At xi = 0 (static Matsubara mode), a dissipative Drude metal diverges to +inf.
    """
    xi_val, is_scalar = _validate_xi_meep(xi_meep)
    wp = float(wp_eV)
    gam = float(gamma_eV)
    if not (np.isfinite(wp) and np.isfinite(gam)) or wp <= 0.0 or gam < 0.0:
        raise ValueError("Drude parameters require finite wp_eV > 0 and gamma_eV >= 0.")

    base = evaluate_lorentz_eps_imag(xi_val, eps_inf, oscillators)
    xi_eV = xi_val * HBAR_C_EV_UM
    if is_scalar:
        if xi_eV == 0.0:
            return float(np.inf)
        denom = xi_eV * (xi_eV + gam)
        if denom <= 0.0:
            return float(np.inf)
        return float(base + (wp ** 2) / denom)

    result = np.array(base, dtype=float, copy=True)
    pos = xi_eV > 0.0
    denom = xi_eV[pos] * (xi_eV[pos] + gam)
    result[pos] = result[pos] + (wp ** 2) / denom
    result[~pos] = np.inf
    return result


def get_dielectric_tensor_imag(
    material_name,
    xi_meep,
    theta_deg=0.0,
    *,
    res2_eps_inf_z=RES2_EPS_INF_Z,
    res2_oscillators_z=None,
):
    """
    Returns the full 3x3 dielectric tensor epsilon(i*xi) rotated by angle theta in the xy-plane.

    Returns:
    --------
    eps_xx, eps_yy, eps_zz, eps_xy : float or np.ndarray
    """
    xi_val, _ = _validate_xi_meep(xi_meep)
    theta_val = float(theta_deg)
    if not np.isfinite(theta_val):
        raise ValueError("theta_deg must be finite.")
    theta_rad = np.radians(theta_val)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)

    if material_name in ["BlackPhosphorus", "Phosphorene", "Phosphorene_tuned", "BP_realistic"]:
        eps_x = evaluate_lorentz_eps_imag(xi_val, BP_EPS_INF_X, BP_OSCILLATORS_X)
        eps_y = evaluate_lorentz_eps_imag(xi_val, BP_EPS_INF_Y, BP_OSCILLATORS_Y)
        eps_z = evaluate_lorentz_eps_imag(xi_val, BP_EPS_INF_Z, BP_OSCILLATORS_Z)
    elif material_name == "ReS2":
        osc_z = RES2_OSCILLATORS_Z if res2_oscillators_z is None else res2_oscillators_z
        eps_x = evaluate_lorentz_eps_imag(xi_val, RES2_EPS_INF_A, RES2_OSCILLATORS_A)
        eps_y = evaluate_lorentz_eps_imag(xi_val, RES2_EPS_INF_B, RES2_OSCILLATORS_B)
        eps_z = evaluate_lorentz_eps_imag(xi_val, res2_eps_inf_z, osc_z)
    elif material_name == "Gold":
        eps_iso = evaluate_drude_lorentz_eps_imag(
            xi_val, GOLD_EPS_INF, GOLD_WP_EV, GOLD_GAMMA_EV, GOLD_OSCILLATORS
        )
        eps_x = eps_y = eps_z = eps_iso
    elif material_name == "Silicon":
        eps_iso = evaluate_lorentz_eps_imag(xi_val, SILICON_EPS_INF, SILICON_OSCILLATORS)
        eps_x = eps_y = eps_z = eps_iso
    elif material_name in IMMERSION_MEDIA:
        med = IMMERSION_MEDIA[material_name]
        gamma_eV = med.get("gamma_eV", DEFAULT_IMMERSION_GAMMA_EV)
        f_uv = (med["eps_static"] - med["eps_inf"]) * med["uv_pole_eV"]**2
        osc_list = (
            [{"E0_eV": med["uv_pole_eV"], "f_eV2": f_uv, "gamma_eV": gamma_eV}]
            if f_uv > 0.0
            else []
        )
        eps_iso = evaluate_lorentz_eps_imag(xi_val, med["eps_inf"], osc_list)
        eps_x = eps_y = eps_z = eps_iso
    else:
        raise ValueError(f"Unknown material_name: {material_name!r}")

    # Rotate in xy-plane (avoiding inf - inf = nan for isotropic Drude static limit):
    if eps_x is eps_y:
        eps_xx = eps_x
        eps_yy = eps_y
        eps_zz = eps_z
        eps_xy = 0.0 if np.isscalar(eps_x) else np.zeros_like(eps_x, dtype=float)
    else:
        eps_xx = eps_x * C**2 + eps_y * S**2
        eps_yy = eps_x * S**2 + eps_y * C**2
        eps_zz = eps_z
        eps_xy = (eps_x - eps_y) * S * C

    return eps_xx, eps_yy, eps_zz, eps_xy


def get_meep_dispersive_medium(
    material_name,
    Sigma,
    ft,
    theta_deg=0.0,
    *,
    res2_eps_inf_z=RES2_EPS_INF_Z,
    res2_oscillators_z=None,
):
    """
    Constructs an authentic MEEP mp.Medium with physical multi-oscillator
    Lorentz susceptibilities and conductivity damping.
    """
    if mp is None:
        return None

    theta_val = float(theta_deg)
    if not np.isfinite(theta_val):
        raise ValueError("theta_deg must be finite.")
    theta_rad = np.radians(theta_val)
    C = np.cos(theta_rad)
    S = np.sin(theta_rad)

    cond_attr = {"D_conductivity" if ft == mp.E_stuff else "B_conductivity": Sigma}

    if material_name in ["BlackPhosphorus", "Phosphorene", "Phosphorene_tuned", "BP_realistic", "ReS2"]:
        if material_name == "ReS2":
            eps_inf_x = RES2_EPS_INF_A
            eps_inf_y = RES2_EPS_INF_B
            eps_inf_z = float(res2_eps_inf_z)
            oscillators_x = RES2_OSCILLATORS_A
            oscillators_y = RES2_OSCILLATORS_B
            oscillators_z = RES2_OSCILLATORS_Z if res2_oscillators_z is None else res2_oscillators_z
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
        # In Meep, offdiag Vector3(u_x, u_y, u_z) maps to (xy, xz, yz).
        for osc in oscillators_x:
            freq_meep = osc["E0_eV"] * EV_TO_MEEP_FREQ
            gamma_meep = osc["gamma_eV"] * EV_TO_MEEP_FREQ
            sig_x = (osc["f_eV2"] * EV_TO_MEEP_FREQ**2) / freq_meep**2

            susceptibilities.append(mp.LorentzianSusceptibility(
                frequency=freq_meep,
                gamma=gamma_meep,
                sigma_diag=mp.Vector3(sig_x * C**2, sig_x * S**2, 0.0),
                sigma_offdiag=mp.Vector3(sig_x * S * C, 0.0, 0.0)
            ))

        for osc_y in oscillators_y:
            freq_meep = osc_y["E0_eV"] * EV_TO_MEEP_FREQ
            gamma_meep = osc_y["gamma_eV"] * EV_TO_MEEP_FREQ
            sig_y = (osc_y["f_eV2"] * EV_TO_MEEP_FREQ**2) / freq_meep**2

            susceptibilities.append(mp.LorentzianSusceptibility(
                frequency=freq_meep,
                gamma=gamma_meep,
                sigma_diag=mp.Vector3(sig_y * S**2, sig_y * C**2, 0.0),
                sigma_offdiag=mp.Vector3(-sig_y * S * C, 0.0, 0.0)
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
        gamma_eV = med.get("gamma_eV", DEFAULT_IMMERSION_GAMMA_EV)
        susceptibilities = []
        sigma_uv = med["eps_static"] - med["eps_inf"]
        if sigma_uv != 0.0:
            susceptibilities.append(mp.LorentzianSusceptibility(
                frequency=med["uv_pole_eV"] * EV_TO_MEEP_FREQ,
                gamma=gamma_eV * EV_TO_MEEP_FREQ,
                sigma=sigma_uv
            ))
        return mp.Medium(
            epsilon=med["eps_inf"],
            E_susceptibilities=susceptibilities,
            **cond_attr
        )
    else:
        raise ValueError(f"Unknown material_name: {material_name!r}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Verify dispersive material dielectric tensors.")
    parser.add_argument("--max-steps", type=int, default=5, help="Number of imaginary frequency steps to verify.")
    args = parser.parse_args()

    steps = max(1, int(args.max_steps))
    xi_grid = np.linspace(0.1, 10.0, steps)
    for mat_name in ("BlackPhosphorus", "ReS2", "Gold", "Silicon", "Teflon_AF", "Bromobenzene", "Vacuum"):
        xx, yy, zz, xy = get_dielectric_tensor_imag(mat_name, xi_grid, theta_deg=30.0)
        assert xx.shape == (steps,) and yy.shape == (steps,) and zz.shape == (steps,) and xy.shape == (steps,)
        assert np.all(np.isfinite(xx)) and np.all(xx > 0.0)
        assert np.all(np.isfinite(yy)) and np.all(yy > 0.0)
        assert np.all(np.isfinite(zz)) and np.all(zz > 0.0)
        s_xx, s_yy, s_zz, s_xy = get_dielectric_tensor_imag(mat_name, float(xi_grid[0]), theta_deg=30.0)
        assert isinstance(s_xx, float) and isinstance(s_yy, float) and isinstance(s_zz, float) and isinstance(s_xy, float)
    print(f"Verified {steps} imaginary-frequency points across all materials successfully.")
