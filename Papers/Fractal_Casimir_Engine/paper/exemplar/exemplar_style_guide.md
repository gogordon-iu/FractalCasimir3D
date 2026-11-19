# Exemplar Style & Expressivity Guide

- **Exemplar Title**: Non-reciprocal energy transfer through the Casimir effect
- **Authors**: Zhujing Xu, Xingyu Gao, Jaehoon Bang, Zubin Jacob, and Tongcang Li
- **Published Venue & Year**: *Nature Nanotechnology* 17, 148–153 (2022)
- **Source / DOI / Open-Access Link**: https://doi.org/10.1038/s41565-021-01026-8 | https://arxiv.org/pdf/2102.12857.pdf
- **Processed Exemplar File**: `paper/exemplar/exemplar_paper.md`

---

## 1. Style (Voice, Cadence & Rhetorical Register)
- **Person & Voice**: Active first-person plural (`"Here we report..."`, `"We modulate..."`, `"We engineer..."`, `"We now discuss..."`, `"We demonstrate..."`) throughout main-text derivations, simulations, and design decisions; sparing passive voice reserved for objective physical laws (`"quantum electromagnetic fluctuations can induce a measurable force..."`) and standard fabrication/apparatus states.
- **Verb Tense Map**:
  - *Bold Summary Paragraph & Unheaded Opening*: Present tense for universal physical laws and device capabilities (`"quantum electromagnetic fluctuations can dominate..."`, `"Here we report..."`); present-perfect for the open frontier (`"has remained elusive"`, `"has not been realized with Casimir interactions before"`).
  - *Prior Literature Contrast*: Present-perfect (`"Several studies have demonstrated..."`) when summarizing cumulative capabilities, switching to simple past only for historical landmarks (`"In 1948, Casimir predicted..."`).
  - *Architecture, Cycle Physics & Results*: Present timeless tense when describing how the device operates and what figures show (`"Figure 3 shows..."`, `"When the control loop includes..."`, `"This coupling arises from..."`), paired with concise past-tense reporting of specific verification benchmarks.
  - *Methods*: Present tense for mathematical formulations and simulation protocols.
- **Sentence Length & Rhythm**: Short, declarative topic sentences (`12–18` words) open nearly every paragraph (`"We now realize a Casimir diode by engineering the system dynamically."`), followed by medium-length (`20–28` word) mechanistic sentences linking physical intuition directly to quantitative observables and figure panels. Avoid multi-line 70-word parenthetical run-on sentences.
- **Claim Calibration & Hedging**: Bold on verified physical mechanisms (`"realize non-reciprocal energy transfer with high contrast"`), scrupulously explicit about approximations, regime boundaries, and energy scales (`"Under weak-coupling approximation..."`, `"For the separation considered..., quantum fluctuations dominate"`, `"less than 0.1%, which is negligible"`).

## 2. Format (Macro Organization, LaTeX & `.bib` Conventions)
- **Top-Level Section Sequence (*Nature Nanotechnology* Article Format)**:
  1. Concise declarative title ($\le 15$ words, no colons or mathematical clutter).
  2. Author & affiliation block with superscript indices and corresponding-author email.
  3. **Boldface fully-referenced Summary Paragraph** (`160–200` words, zero equations, ending with a 1-sentence nanotechnology impact statement).
  4. **Unheaded Opening** (`3` paragraphs, no `\section{Introduction}` heading).
  5. **Thematic Unnumbered Main-Text Sections** (`\section*{...}`, concise `3–6` word lower-case Nature headings, e.g., `\section*{Chiral dual-stroke Cantor architectures}`, `\section*{Multiscale hierarchy and stability trade-off}`, `\section*{Dispersive switching and room-temperature dynamics}`, `\section*{Thermodynamic efficiency and practical actuation}`).
  6. **Unheaded Concluding Paragraph** (`1` crisp synthesis & outlook paragraph at the end of the main text, followed by Main References or Methods).
  7. **`\section*{Methods}`** divided into bold lead-in subsections (`\subsection*{...}`), followed by `\section*{Data availability}`, `\section*{Code availability}`, References (`\bibliographystyle{unsrt}` or Nature numeric superscripts), and **Extended Data Figures & Extended Data Tables**.
- **Equations & Environments**: Keep the main text mathematically lean (`3–4` essential numbered display equations maximum in the main text, unpacking every symbol immediately in plain prose); place full matrix/BEM/BAOAB/Epstein derivations in `Methods` (`Eqs. (4)–(11)` in exemplar). Zero formal `Theorem`/`Lemma` boxes.
- **Tables & Figures**:
  - **Main Display Items**: `6` Main Figures (`Figs. 1–6`) + `2` compact `booktabs` Main Tables (`Tables 1–2`), with supporting convergence, FDTD cross-check, 6-DOF/rounding, baseline stroke, and 3D keyframe panels organized cleanly as **Extended Data Figs. 1–5** and **Extended Data Table 1**.
  - **Captions**: Bold single-sentence title (`\textbf{Fig. 1 | ...}`), followed by panel-by-panel `(a)`, `(b)`, `(c)`, `(d)` self-contained descriptions stating conditions, temperatures, sample sizes, and error-bar definitions (`s.d.` or `s.e.m.`).
- **Citation & `.bib` Style**: Sequential numbered citations (`\cite{...}`) in order of appearance (`unsrt`), grouping foundational clusters cleanly (`\cite{casimir1948,munday2009,rodriguez2011,somers2018}`). Every `.bib` entry must contain verified peer-reviewed journal volume, page/article number, and year.

## 3. Jargon & Notation Discipline
- **Canonical Domain Vocabulary**: *quantum vacuum fluctuations*, *Casimir–Lifshitz interaction*, *Lifshitz theory*, *Wick-rotated imaginary frequency* $\xi$, *proximity-force approximation (PFA)*, *Maxwell stress tensor*, *boundary-element method (BEM)*, *Kramers–Kronig dispersion*, *Mott metal–insulator transition*, *photodoped carrier plasma*, *patch potentials*, *Kelvin-probe compensation*, *Brownian ratchet / detailed balance*, *Thermodynamic Uncertainty Relation (TUR)*, *efficiency at maximum power (EMP)*, *Knudsen number*.
- **Mathematical Notation System**:
  - Coordinates: cylindrical $(r, \theta, z)$, rotor tip height $z_{\mathrm{tip}}$, sector period $\Theta_{\mathrm{sec}} = 90^\circ$.
  - Observables: Casimir free energy $E_C(z,\theta)$ (in $\mathrm{aJ}$), axial force $F_z = -\partial E_C/\partial z$ (in $\mathrm{pN}$), azimuthal torque $\tau_\theta = -\partial E_C/\partial\theta$ (in $\mathrm{pN}\cdot\mu\mathrm{m}$ or $\mathrm{pN}\cdot\mathrm{nm}$), angular velocity $\omega$ (in $\mathrm{krad\,s^{-1}}$), external load torque $\tau_{\mathrm{load}}$, shaft power $P_{\mathrm{shaft}}$ (in $\mathrm{fW}$ or $\mathrm{aW}$).
  - Matrices/Vectors: bold Roman matrices ($\mathbf{Y}_{m,\mathrm{ch}}, \mathbf{M}_{rr,m}, \mathbf{G}_{rs,m}$) and vectors ($\mathbf{q}, \mathbf{F}$).
- **Acronym Onboarding**: Define NEMS, BEM, FDTD, EBL, SOI, EMP, TUR, and UHV on first appearance in main text; keep the bold Summary Paragraph largely free of niche acronyms.

## 4. Clarity & Pedagogical Flow
- **Intuition-Formalism Ordering**: Always state the physical mechanism and symmetry argument *first* in plain language (why mirror-symmetric teeth cancel torque, why opposing chiral tapers in upper repulsive collars and lower landing pads align torque across both strokes, why conservative loops require non-equilibrium switching), and only *then* introduce the compact governing equation.
- **Signposting & Transitions**: Open each `\section*{...}` with a crisp topic sentence connecting back to the engine's operating cycle (`"Having established co-directional dual-stroke torque on static surfaces, we next examine..."`).
- **Figure & Caption Self-Containedness**: A reader inspecting `Figs. 1–6`, `Tables 1–2`, and their captions must grasp the architecture, dual-stroke landscapes, Cantor $N=2$ Pareto optimum, physical $\mathrm{VO}_2$/$\mathrm{Si}$ switching, $300\text{ K}$ Langevin & defect tolerances, thermodynamic efficiency hierarchy, and practical $4\text{ K}$/Knudsen/metasurface applications without reading the body text.

## 5. Scientific Rigor
- **Thermodynamic & Physical Honesty**:
  - Explicitly enforce the equilibrium No-Go theorem ($\oint \mathbf{F}\cdot d\mathbf{q} = 0$ and zero drift at $300\text{ K}$ static equilibrium) so the engine is framed accurately as a **non-contact vacuum-mediated chemomechanical/optomechanical/electromechanical transducer**, never as zero-point energy extraction.
  - Explicitly separate **internal Casimir-to-shaft transduction efficiency** ($\eta_{\mathrm{EMP}} = 49.1\%$) from **device wall-plug efficiency** ($\sim 10^{-9}\text{--}10^{-8}$ for bulk thermal $\mathrm{VO}_2$ and optical $\mathrm{Si}$ vs.\ $0.63\%$ for $Q=50$ resonant 2D-graphene capacitive gating).
  - Report controlled non-fractal (`Uniform_3Track`) and generation ($N=0..3$) ablations candidly, noting both where uniform 3-track subdivision yields comparable/slightly higher stroke work (`0.513` vs.\ `0.457 aJ`) and where Cantor $N=2$/$N=3$ provides `3.19×–3.54×` gain over a single macro-channel, `55%` Vernier cogging cancellation at $N=3$, and optimal lateral pull-in stability at $N=2$.
- **Error Bars & Tolerances**: Report ensemble sizes ($M=96\text{--}256$), standard errors, mesh/quadrature discretization bounds, polycrystalline Au patch-potential SNR (`4.1×` at `30 mV`), `3 nm` RMS roughness, `12 nm` eccentricity, `2 mrad` tilt, and `15 nm` EBL corner rounding.

## 6. Expressivity (How Much to Write on What)

Calibrated directly from `exemplar_paper.md` (`3,924` total words across Summary + Main Text + Captions + Methods; `~2,150` words main narrative + captions, `~1,150` words Methods, `~620` words references):

| Section | Exemplar Words | Share (%) | Paragraphs | Equations | Citations | Target Allocation for Current Manuscript |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| Bold Summary Paragraph | ~195 | ~6% | 1 | 0 | 7 (`[1–17]`) | **185–200 words**, 1 bold paragraph, 6–8 key citations, 0 display eqs |
| Unheaded Opening (Intro) | ~430 | ~13% | 3 | 0 | ~18 | **450–550 words**, 3 paragraphs, clear gap + dual-stroke principle + preview |
| Main Results (`4–5` `\section*{}` blocks) | ~1,450 | ~44% | 10–12 | 3 | ~12 | **2,200–2,600 words** across 5 `\section*{}` blocks covering all 7 suites (`Figs. 1–6`, `Tables 1–2`) |
| Unheaded Concluding Outlook | ~140 | ~4% | 1 | 0 | 1 | **160–200 words**, 1 synthesis & experimental-roadmap paragraph |
| Methods (`\section*{Methods}`) | ~1,100 | ~33% | 6–8 | 8 | ~5 | **1,200–1,500 words**, 5 `\subsection*{}` blocks (`5–7` equations) + Data/Code Availability + Extended Data (`ED Figs. 1–5`, `ED Table 1`) |

- **Depth Allocation Rules**:
  - *Where to invest main-text detail*: Physical dual-stroke chirality mechanism (`Fig. 1–2`), Cantor multiscale scaling & $N=2$ stability trade-off (`Fig. 3`), physical $\mathrm{VO}_2$/photo-$\mathrm{Si}$ switching & $300\text{ K}$ Langevin + experimental defect budget (`Figs. 4–5`), and the loaded motor efficiency hierarchy + concrete $4\text{ K}$ optical latch / Knudsen gauge / metasurface applications (`Fig. 6`, `Table 2`).
  - *Where to stay terse in main text & defer to Methods / Extended Data*: Co-rotating $\mathbf{Y}_{m,\mathrm{ch}}$ matrix algebra, Gauss–Legendre sub-panel regularization sweeps (`ED Fig. 3`), Meep stress-box DCT details (`ED Fig. 4`), non-Bloch 6-DOF finite-difference stencils (`ED Fig. 5`), BAOAB splitting equations, and Voronoi patch capacitance matrices.
