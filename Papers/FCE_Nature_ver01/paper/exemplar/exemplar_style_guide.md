# Exemplar Style & Expressivity Guide (Three-Exemplar Flagship *Nature* Calibration)

- **Target Venue**: *Nature* (Flagship Physical Sciences Article, `sn-jnl` `[pdflatex,sn-nature]`)
- **Exemplar 1 (Quantum Nanomechanics & Phonon Control)**: E. Alex Wollack, Agnetta Y. Cleland, Rachel G. Gruenke, Zhaoyou Wang, Patricio Arrangoiz-Arriola, & Amir H. Safavi-Naeini, *"Quantum state preparation, tomography, and entanglement of mechanical oscillators"*, **Nature** 604, 463–469 (2022), DOI: `10.1038/s41586-022-04500-y` (`arXiv:2110.07561`; `Papers/FCE_Nature_ver01/paper/exemplar/exemplar_paper.md`)
- **Exemplar 2 (Silicon Optomechanics, Brownian Noise Calibration & Amplification)**: Jesse J. Slim, Clara C. Wanjura, Matteo Brunelli, Javier del Pino, Andreas Nunnenkamp, & Ewold Verhagen, *"Optomechanical realization of the bosonic Kitaev chain"*, **Nature** 627, 767–771 (2024), DOI: `10.1038/s41586-024-07174-w` (`arXiv:2309.05825`; `Papers/FCE_Nature_ver01/exemplar_2_nems_2024/paper/exemplar/exemplar_paper.md`)
- **Exemplar 3 (Discrete Self-Similarity & Fractal Quantum Physics)**: Kevin P. Nuckolls, Michael G. Scheer, Dillon Wong, Myungchul Oh, Ryan L. Lee, Jonah Herzog-Arbeitman, Kenji Watanabe, Takashi Taniguchi, Biao Lian, & Ali Yazdani, *"Spectroscopy of the fractal Hofstadter energy spectrum"*, **Nature** 639, 60–66 (2025), DOI: `10.1038/s41586-025-08632-x` (`arXiv:2501.04777`; `Papers/FCE_Nature_ver01/exemplar_3_fractal_2025/paper/exemplar/exemplar_paper.md`)
- **Casimir Domain Cross-Check**: Yichi Zhang et al., *"Magnetic-field tuning of the Casimir force"*, **Nature Physics** 20, 1282–1287 (2024), DOI: `10.1038/s41567-024-02521-0` (`Papers/FCE_Nature_ver01/exemplar_4_casimir_2024/paper/exemplar/exemplar_paper.md`)

---

## 1. Style (Voice, Cadence & Rhetorical Register)
- **Person & Voice**: Active first-person (`"Here we introduce..."`, `"We benchmark..."`, `"Sweeping rotor azimuth reveals..."`) for architectural, computational, and analytical steps; concise passive voice reserved for established physical theorems and fabrication priors.
- **Verb Tense Map**:
  - *Summary Paragraph (Abstract)*: Present tense for physical background and key quantitative results (`"delivers"`, `"switches"`, `"converge"`), bridged by `"Here we introduce..."`. Zero inline citations in the summary paragraph.
  - *Unheaded Opening (Introduction)*: Present tense for general physical principles (Casimir effect, Kenneth–Klich theorem, Weyl asymptotics); present-perfect (`"have been realized"`, `"has remained"`) for prior milestones and open bottlenecks; present tense (`"Here we resolve..."`) for the paper's central advance.
  - *Main Results Sections*: Present tense for architectural properties, figure walkthroughs, and physical relationships (`"Figure 2 shows..."`, `"activating radial Cantor subdivision boosts..."`).
  - *Methods*: Present timeless tense for mathematical formulations and solver definitions; past/passive or present procedural tense for simulation sweeps.
- **Sentence Length & Rhythm**: Topic sentences are crisp (~15–22 words) and state the physical takeaway upfront before unpacking numerical metrics. Avoid bulleted or `\begin{enumerate}` lists in main text—all three *Nature* exemplars use continuous, cohesive prose paragraphs.
- **Claim Calibration & Hedging**: Distinguish exact mathematical/numerical properties (`"eliminates horizontal face overlap"`, `"converges to within 5.5%"`) from finite-generation fractal behavior (`"three-generation prefractal hierarchy"`, `"smooth multi-stage envelope covering without unphysical log-periodic oscillations"`), mirroring Nuckolls et al. (*Nature* 2025) on discrete self-similarity over finite rational scales.

## 2. Format (Macro Organization, LaTeX & `.bib` Conventions)
- **Top-Level Section Sequence**:
  1. Title ($\le 75$ characters including spaces; concise running title)
  2. Bold Summary Paragraph (`\abstract{...}`, $\le 200$ words, unreferenced)
  3. Unheaded Opening (3 paragraphs, ~500–620 words; **never** titled `\section*{Introduction}`)
  4. 4–6 concise unnumbered `\section*{...}` headings ($\le 40$ characters including spaces), ending with `\section*{Discussion}`
  5. `\backmatter` $\to$ `\section*{Methods}` (with `\subsection*{...}` blocks), `\section*{Data availability}`, `\section*{Code availability}`, `\section*{Acknowledgements}`, `\section*{Author contributions}`, `\section*{Competing interests}`, `\bibliography{references}`
  6. Extended Data Figures and Extended Data Tables (`\renewcommand{\figurename}{Extended Data Fig.}`, `\renewcommand{\tablename}{Extended Data Table}`)
- **Display-Item Discipline (Critical *Nature* Rule)**:
  - All three flagship *Nature* exemplars place **4–6 display items total** in the main text and move detailed multi-column benchmark/convergence tables to Extended Data (`<= 10` Extended Data items).
  - Target allocation for `fce_nature_ver11.tex`: **5 Main Figures (`Figs. 1–5`) + 1 Flagship Main Table (`Table 1`: head-to-head 7-design robustness benchmark) = 6 Main Display Items**, plus **2 Extended Data Figures + 4 Extended Data Tables = 6 Extended Data Items**.
- **Equations & Environments**: Main text keeps display equations minimal (1–2 core governing equations, just as Slim et al. *Nature* 2024 has Eqs. 1–3 and Nuckolls et al. *Nature* 2025 uses inline Streda/scaling relations), placing detailed solver discretizations and quadrature formulas in `Methods`.
- **Citation & `.bib` Style**: Superscript/numeric Springer Nature `sn-nature` (`\cite{...}`), $\le 35$ main-text references, full verified author lists (no `and et al.` shortcuts), protection braces around `{Casimir}`, `{FDTD}`, `{Cantor}`, `{RWG}`, and complete DOIs.

## 3. Jargon & Notation Discipline
- **Canonical Domain Vocabulary**: *Casimir--Lifshitz interaction*, *Kenneth--Klich theorem*, *proximity-force approximation (PFA)*, *fluctuating surface currents*, *Rao--Wilton--Glisson (RWG) boundary elements*, *PMCHWT formulation*, *Yee lattice*, *Earnshaw instability*, *Matsubara frequencies*, *Brownian thermomechanical force noise*, *homothetic prefractal hierarchy*.
- **Mathematical Notation System**:
  - Axial force $F_z$ ($\mathrm{pN}$, $+F_z > 0$ repulsive, $-F_z < 0$ attractive), switching swing $\Delta F_z = F_z(\theta_{\mathrm{open}}) - F_z(\theta_{\mathrm{eng}})$, azimuthal torque $\tau_\theta = -\partial E/\partial\theta$ ($\mathrm{pN\cdot\mu m}$).
  - Imaginary wavenumber $\kappa = \xi/c$ ($\mu\mathrm{m}^{-1}$), scale ratio $b = 3$, generation index $m \in \{1,2,3\}$, homothetic factor $s_m = b^{N-m}$.
  - Dimensionless open-window torque-to-lift ratio $\mathcal{R}_\tau = \max_{\theta\in[1.5^\circ,4.5^\circ]}|\tau_\theta| / [R_{\mathrm{mean}}\max(|F_z(\theta_{\mathrm{open}})|, 0.10\ \mathrm{pN})]$.

## 4. Clarity & Pedagogical Flow
- **Intuition-Formalism Ordering**: Every section opens with a 1–2 sentence physical motivation explaining *why* a bottleneck arises (e.g., Weyl overlap attraction, Earnshaw transverse saddle instability, Yee staircase snapping) before presenting the quantitative benchmark or equation.
- **Figure & Caption Self-Containedness**: Each caption opens with a bold declarative title sentence (`\textbf{...}`), labels every panel in lower-case bold (`\textbf{a}, ...`), states physical conditions ($T=300\ \mathrm{K}$, $\varepsilon_{\mathrm{bg}}=1.0$, $A_{\mathrm{tooth}}$), and enables a reader scanning `Figs. 1–5` + `Table 1` alone to grasp the entire discovery.

## 5. Scientific Rigor
- **Strict Baseline & Ablation Controls**: Matched active tooth area $A_{\mathrm{tooth}} = 3.103\ \mu\mathrm{m}^2$ and minimum gap $g_{\min} = 27\ \mathrm{nm}$ across 5 non-fractal controls, full $2^3$ $(I_r, I_\theta, I_z)$ factorial hypercube, $N=1\to 3$ depth ladder, and micro-bridge isolation.
- **Dual-Solver First-Principles Cross-Verification**: Independent 5-tier 3D Maxwell RWG BEM (`EFIE`/`PMCHWT`) and 51-task 4-pass 3D Meep FDTD across single-cell and 3-track multiscale geometries, reporting explicit continuum uncertainties (`\pm`) and candidly explaining the non-subpixel $\mathcal{O}(\Delta x/2)$ Yee wall-snapping residual in ideal PEC vs. skin-depth-regularized Drude gold (`5.0%–5.5%`).
- **Exact Code-to-Prose Fidelity**: Every simulation parameter in `Methods` (Courant factor `0.5`, Matsubara poles $N_M = 80, 160$, tilt grid $\alpha_{\mathrm{tilt}} \in [0, 2.5]\ \mathrm{mrad}$, vacuum residual $|F_z^{\mathrm{vac}}| \le 1.7\times 10^{-8}\ \mathrm{pN}$) must match the executed solver code identically.

## 6. Expressivity (Section Word-Share Targets)

| Section | Exemplar Range (*Nature* 2022–2025) | Share (%) | Target Allocation for `fce_nature_ver11.tex` |
| :--- | ---: | ---: | :--- |
| Summary Paragraph (`\abstract`) | 175–196 words | ~5% | $\le 195$ words (1 paragraph, 0 citations) |
| Unheaded Opening | 480–620 words | ~16% | ~550–600 words (3 paragraphs) |
| 1. Homothetic 3D Cantor rotary switch | 420–550 words | ~14% | ~450–480 words + Eq. (1) + Fig. 1 |
| 2. Matched controls and lab robustness | 650–800 words | ~21% | ~680–740 words (4 prose paragraphs, no `enumerate`) + Fig. 2 + Table 1 |
| 3. Factorial and structural ablations | 380–480 words | ~12% | ~400–430 words + Fig. 3 (ref. ED Table 1) |
| 4. 6-DOF suspension and scale optimality | 520–650 words | ~17% | ~550–600 words + Fig. 4 (ref. ED Table 2) |
| 5. First-principles BEM and FDTD | 550–700 words | ~18% | ~580–640 words + Fig. 5 (ref. ED Fig. 2, ED Tables 3–4) |
| 6. Discussion | 180–260 words | ~6% | ~200–230 words (1–2 synthesis paragraphs) |
| **Total Main Text (excl. Methods/Captions)** | **~2,800–3,500 words** | **100%** | **~3,400–3,550 words** (`6` main display items) |
| Methods (5 subsections) | 1,200–2,200 words | — | ~1,350–1,450 words |
