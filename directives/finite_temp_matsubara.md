# SOP: Finite-Temperature Matsubara Corrections

This Standard Operating Procedure outlines the implementation of finite-temperature corrections (T = 77 K and T = 300 K) using the Matsubara imaginary frequency summation in combination with the MEEP FDTD solver.

## 1. Matsubara Frequency Summation

At finite temperature $T$, the imaginary frequency integral in the Casimir force formula is replaced by a discrete summation over Matsubara frequencies:

$$F_i(T) = k_B T \sum_{n=0}^{\infty} ' \int_S dS_j \, M_{ij}(i\xi_n, \mathbf{x})$$

where:
- $\xi_n = \frac{2\pi n k_B T}{\hbar}$ is the $n$-th Matsubara frequency.
- The prime on the sum indicates that the $n=0$ term is weighted by $1/2$.
- $k_B$ is the Boltzmann constant.

## 2. Imaginary-Frequency Green's Function in MEEP

In the MEEP FDTD solver, the imaginary frequency Green's function is evaluated by running simulations in a system with frequency-independent conductivity $\sigma$.
- The time-domain Green's function $g(t)$ is computed using the function `make_casimir_gfunc` (or `make_casimir_gfunc_kz` for $z$-invariant systems).
- The parameter `T` in `make_casimir_gfunc` corresponds to the simulation time, and `sigma` corresponds to the artificial global conductivity.
- For finite temperature $T_{phys}$, the summation over the Matsubara frequencies is handled by:
  1. Evaluating the imaginary-frequency reflection coefficients at $\xi_n$.
  2. Modifying the time-kernel $g(t)$ to incorporate the thermal occupation factors (temperature-dependent weights).

## 3. Practical Steps

1. For a given temperature ($T=77\text{ K}$ or $T=300\text{ K}$), calculate the Matsubara spacing $\Delta\xi = 2\pi k_B T / \hbar$.
2. Limit the sum to a cutoff $n_{\max}$ where terms become negligible (typically $n_{\max} \approx 20$ to $30$).
3. Run the FDTD simulations for each required separation $d$ and prefractal generation $N$.
4. Multiply each term by the thermal weighting factor and perform the sum to obtain the finite-temperature Casimir force.
