# SOP: Visualization Generator

This Standard Operating Procedure defines the guidelines for plotting publication-quality figures using matplotlib, formatted precisely to the style of Science/Nature.

## 1. Style Rules and Layout

- **Fonts**: Use `Google Sans` or `Helvetica` if available; otherwise fall back to `DejaVu Sans` but with clean styling.
  - Title Font Size: 10 pt bold.
  - Axis Labels: 8 pt.
  - Legend and Tick Labels: 7 pt.
- **Dimensions**: Single-column figures should be $8.9\text{ cm}$ ($3.5\text{ in}$) wide. Double-column figures should be $18.3\text{ cm}$ ($7.2\text{ in}$) wide.
- **Output Format**: Vector PDF/SVG only.
- **Color Palette**: High-contrast, neutral palettes (e.g., deep blues, muted reds, charcoal grey, teal). Avoid pure/neon primary colors.
- **Line Widths**: Plot lines $1.2\text{ pt}$, grid lines $0.5\text{ pt}$ (dashed, light grey).

## 2. Specific Figures to Generate

1. **Figure 1**: Force vs. Distance Curve.
   - X-axis: Separation $d$ (nm) on a log scale.
   - Y-axis: Casimir force $F(d)$ (nN) or force normalized by PFA.
   - Curves: $N=1, 2, 3, 4$ prefractal generations compared to the flat plate baseline.
2. **Figure 2**: Fractional PFA Deviation vs. Distance.
   - X-axis: Separation $d$ (nm) on a log scale.
   - Y-axis: Fractional deviation $\eta = (F - F_{\mathrm{PFA}}) / F_{\mathrm{PFA}}$.
   - Showcases the breakdown of pairwise additivity at sharp fractal edges, especially at short separations.
3. **Figure 3**: Finite-Temperature Matsubara Corrections.
   - X-axis: Separation $d$ (nm) on a log scale.
   - Y-axis: Normalized Casimir coefficient $C_T(d) = F(T)/F(0)$.
   - Curves for $T=77\text{ K}$ and $T=300\text{ K}$, proving that temperature washes out the short-distance cutoff log-periodic running of the effective Casimir coefficient.
