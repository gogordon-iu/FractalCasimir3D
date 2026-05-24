# SOP: Casimir FDTD Sweep in 3D MEEP

This Standard Operating Procedure defines the protocol for performing high-resolution 3D Finite-Difference Time-Domain (FDTD) simulations using MEEP to evaluate the Casimir force between a self-similar prefractal plate and a flat plate.

## 1. Physical Configuration and Target Parameters

- **Fractal Geometry**: Sierpinski carpet prefractal plate of size $L_x \times L_y \times t_z$ facing a flat plate.
  - Generations: $N = 1, 2, 3, 4$.
  - Prefractal plate thickness: $0.1\ \mu\text{m}$.
- **Spatial Separations ($d$)**:
  - Range: $20\text{ nm}$ to $1000\text{ nm}$.
  - Logarithmic spacing: 30 points.
- **Material Configurations**:
  - **Perfect Electrical Conductor (PEC)**: Baseline reference.
  - **Dispersive Gold**: Drude-Lorentz model with $\omega_p = 9.0\text{ eV}$ and $\gamma = 0.035\text{ eV}$.
  - **Doped Silicon**: Lorentz model with $\epsilon_\infty = 1.035$, $\omega_0 = 2.18$, and $\Delta\epsilon = 10.835$.

## 2. Numerical Integration & FDTD Setup

- **Enclosing Surface ($S$)**: A 3D rectangular box surrounding the prefractal plate.
  - 6 sides: $x_{\min}, x_{\max}, y_{\min}, y_{\max}, z_{\min}, z_{\max}$.
- **Global Conductivity ($\sigma$)**:
  - To accelerate convergence, a global frequency-independent conductivity $\sigma$ is added to all materials.
  - Recommended scaling: $\sigma \approx 0.5 / d$ where $d$ is the plate separation.
- **Convergence Monitoring**:
  - The simulation run time $T$ must be dynamically set based on the energy decay.
  - Run until the fields decay to $< 10^{-6}$ of their peak value.
  - Typical max run time $T = 30$ to $40$ dimensionless time units.

## 3. Parallelization & Cluster Orchestration

- Run using MPI parallel execution (`mpirun -np [cores]`).
- Partition the parameter sweep (e.g., across $d$ or $N$) to distribute simulations across available nodes.
- Monitor memory limits to prevent out-of-memory (OOM) crashes at high resolution (resolution = 40).
