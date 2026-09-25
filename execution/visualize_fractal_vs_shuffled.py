#!/usr/bin/env python3
"""
Visualization Generator: Fractal vs. Shuffled Geometry
------------------------------------------------------
Generates a side-by-side visual comparison verifying:
1. Panel A: N=3 Fractal (Sierpinski carpet: 1 macro + 8 medium + 64 small elements).
2. Panel B: N=3 Shuffled (exact same 73 elements in a non-fractal, scrambled layout).
3. Both share identical total feature area (217/729 = 29.77%), identical volume,
   and identical average distance <d> = 100 nm.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from execution.fractal_control_geometry import (
    get_fractal_elements,
    get_shuffled_elements,
    calculate_area_fraction,
    calculate_standoff
)


def draw_plate_surface(ax, elements, L, title):
    """Draws plate boundary and color-coded cavity elements."""
    # Base plate outline
    plate_rect = patches.Rectangle(
        (-L / 2.0, -L / 2.0), L, L,
        facecolor="#e0e0e0", edgecolor="#333333", linewidth=1.5, label="Solid Land"
    )
    ax.add_patch(plate_rect)

    # Color mapping per level
    color_map = {
        1: "#1f77b4",  # Level 1 (Macro L/3): Blue
        2: "#ff7f0e",  # Level 2 (Medium L/9): Orange
        3: "#2ca02c"   # Level 3 (Micro L/27): Green
    }

    counts = {1: 0, 2: 0, 3: 0}
    for elem in elements:
        lvl = elem["level"]
        w = elem["w"]
        cx = elem["cx"]
        cy = elem["cy"]
        counts[lvl] = counts.get(lvl, 0) + 1

        rect = patches.Rectangle(
            (cx - w / 2.0, cy - w / 2.0), w, w,
            facecolor=color_map[lvl], edgecolor="#111111", linewidth=0.5
        )
        ax.add_patch(rect)

    ax.set_xlim(-L / 2.0 - 0.1, L / 2.0 + 0.1)
    ax.set_ylim(-L / 2.0 - 0.1, L / 2.0 + 0.1)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel("x (µm)", fontsize=10)
    ax.set_ylabel("y (µm)", fontsize=10)

    # Grid ticks
    ax.set_xticks([-1.0, -0.5, 0.0, 0.5, 1.0])
    ax.set_yticks([-1.0, -0.5, 0.0, 0.5, 1.0])
    ax.grid(True, linestyle="--", alpha=0.3)


def main():
    L = 2.0
    d_avg = 0.10
    h = 0.05
    f_area = calculate_area_fraction(3)
    d_min = calculate_standoff(d_avg, h, f_area)

    frac_elems = get_fractal_elements(3, L)
    shuf_elems = get_shuffled_elements(L, shuffle_seed=42)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))

    # Panel A: Fractal
    draw_plate_surface(
        axes[0], frac_elems, L,
        f"(a) N=3 Fractal (Sierpinski Carpet)\n73 elements: 1 macro + 8 med + 64 micro\nf = {f_area*100:.1f}%, <d> = 100 nm, d_min = {d_min*1e3:.2f} nm"
    )

    # Panel B: Shuffled
    draw_plate_surface(
        axes[1], shuf_elems, L,
        f"(b) N=3 Shuffled (Non-Fractal Control)\nExact same 73 elements, scrambled\nf = {f_area*100:.1f}%, <d> = 100 nm, d_min = {d_min*1e3:.2f} nm"
    )

    # Legend
    legend_elements = [
        patches.Patch(facecolor="#e0e0e0", edgecolor="#333333", label="Solid Land (d = d_min)"),
        patches.Patch(facecolor="#1f77b4", edgecolor="#111111", label="Level 1 Cavity: 1 × (L/3)"),
        patches.Patch(facecolor="#ff7f0e", edgecolor="#111111", label="Level 2 Cavity: 8 × (L/9)"),
        patches.Patch(facecolor="#2ca02c", edgecolor="#111111", label="Level 3 Cavity: 64 × (L/27)")
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=4, frameon=True, fontsize=10, bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.12)

    figs_dir = os.path.join(REPO_ROOT, "results_fractal_control", "figures")
    os.makedirs(figs_dir, exist_ok=True)

    out_svg = os.path.join(figs_dir, "figure_fractal_vs_shuffled.svg")
    out_png = os.path.join(figs_dir, "figure_fractal_vs_shuffled.png")

    plt.savefig(out_svg, format="svg", bbox_inches="tight")
    plt.savefig(out_png, format="png", dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Generated comparison figure:")
    print(f"  SVG: {out_svg}")
    print(f"  PNG: {out_png}")


if __name__ == "__main__":
    main()
