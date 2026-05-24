# SOP: Proximity Force Approximation (PFA) Analytical Model

This Standard Operating Procedure defines the method to compute the corresponding Proximity Force Approximation (PFA) baseline for each prefractal geometry configuration.

## 1. PFA Formulation

The Proximity Force Approximation estimates the Casimir force between two non-planar surfaces by dividing the surfaces into infinitesimal parallel plate elements and integrating the parallel plate force over the area:

$$F_{\mathrm{PFA}}(d) = \int_{S_{\mathrm{eff}}} f_{\mathrm{pp}}(d(x,y)) \, dx \, dy$$

For flat parallel plates where one of the plates has a fractal structure:
- $d(x,y) = d$ is uniform over the contact area.
- The PFA force simplifies to:

$$F_{\mathrm{PFA}}(d) = A_{\mathrm{eff}} \cdot f_{\mathrm{pp}}(d)$$

where:
- $A_{\mathrm{eff}}$ is the effective contact area of the prefractal plate at generation $N$.
- $f_{\mathrm{pp}}(d)$ is the force density between two flat, infinite plates at separation $d$.

## 2. Area Scaling of the Prefractal Plate

For a Sierpinski carpet plate of side length $L$:
- **Generation $N=1$** (solid square):
  $$A_1 = L^2$$
- **Generation $N=2$** (middle square removed):
  $$A_2 = \frac{8}{9} L^2$$
- **Generation $N=3$**:
  $$A_3 = \left(\frac{8}{9}\right)^2 L^2$$
- **Generation $N=4$**:
  $$A_4 = \left(\frac{8}{9}\right)^3 L^2$$
- **General Generation $N$**:
  $$A_N = \left(\frac{8}{9}\right)^{N-1} L^2$$

## 3. Flat Plate Force Density $f_{\mathrm{pp}}(d)$

The parallel plate force density $f_{\mathrm{pp}}(d)$ is computed using the Lifshitz formula:
- For Perfect Electrical Conductors (PEC):
  $$f_{\mathrm{pp}}^{\mathrm{PEC}}(d) = -\frac{\pi^2 \hbar c}{240 d^4}$$
- For real materials (Gold, Silicon), the reflection coefficients are calculated using Fresnel formulas evaluated at imaginary frequencies $\omega = i\xi$, and integrated over imaginary frequency and transverse wavevector.

The fraction deviation between the exact FDTD force and the PFA baseline is then evaluated:

$$\eta = \frac{F_{\mathrm{exact}} - F_{\mathrm{PFA}}}{F_{\mathrm{PFA}}}$$
