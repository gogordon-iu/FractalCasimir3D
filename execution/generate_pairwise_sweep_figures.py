#!/usr/bin/env python3
"""Generate six empirical Casimir-pressure pairwise sweep figures.

The summary's ``pressure_Pa`` values are already SI pressures, converted during
the sweep using MEEP_TO_PA = 0.0316152649. They must NOT be converted again.

No fitted curves, interpolated pressures, or synthetic fallback data are used.
Two-dimensional diagrams display only observed points; unobserved regions remain
blank. Pair 3's diagram selects the maximum observed pressure over twist angle.

Run from the repository root:
    python execution/generate_pairwise_sweep_figures.py
    python execution/generate_pairwise_sweep_figures.py --max-steps 20

Dependencies:
    matplotlib
    the repository's utils.metrics_logger.save_plot_provenance
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import numbers
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.colors import TwoSlopeNorm
from matplotlib.figure import Figure


MEEP_TO_PA: float = 0.0316152649
EPSILON_BG: float = 2.1
PREFERRED_SWEEP: str = "results_sweet_spot_sweep_20261016_230736"
SUMMARY_FILENAME: str = "sweet_spot_sweep_summary.json"
PROVENANCE_FIELDS: tuple[str, ...] = (
    "pressure_Pa",
    "alpha_deg",
    "theta_deg",
    "d_um",
)
ALPHAS: tuple[float, ...] = (60.0, 70.0, 75.0)
PAIR2_ALPHAS: tuple[float, ...] = (70.0, 75.0)
PAIR2_THETAS: tuple[float, ...] = (80.0, 82.0, 84.0, 88.0, 90.0, 92.0, 94.0)
PAIR3_THETAS: tuple[float, ...] = (90.0, 82.0)
TOLERANCE: float = 1e-8


class ProvenanceSaver(Protocol):
    def __call__(
        self,
        fig_path: str,
        summary_path: str,
        fields: list[str],
        /,
    ) -> Any: ...


@dataclass(frozen=True)
class Observation:
    alpha_deg: float
    theta_deg: float
    d_um: float
    pressure_Pa: float

    @property
    def d_nm(self) -> float:
        return self.d_um * 1000.0


def positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a positive integer.") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer.")
    return parsed


def approximately(value: float, target: float) -> bool:
    return math.isclose(value, target, rel_tol=0.0, abs_tol=TOLERANCE)


def in_distance_window(point: Observation) -> bool:
    return 50.0 - TOLERANCE <= point.d_nm <= 350.0 + TOLERANCE


def numeric_value(value: Any, field: str, record_index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(
            f"Record {record_index}: {field!r} must be a JSON number, "
            f"not {type(value).__name__}."
        )
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(
            f"Record {record_index}: {field!r} cannot be represented as a float."
        ) from exc
    if not math.isfinite(result):
        raise ValueError(f"Record {record_index}: {field!r} is non-finite.")
    return result


def iter_record_dicts(node: Any) -> Iterator[dict[str, Any]]:
    """Accept flat lists, keyed records, or summaries with nested record lists."""
    if isinstance(node, dict):
        coordinates = ("alpha_deg", "theta_deg", "d_um")
        if all(field in node for field in coordinates):
            yield node
            return
        for child in node.values():
            if isinstance(child, (dict, list)):
                yield from iter_record_dicts(child)
    elif isinstance(node, list):
        for child in node:
            if isinstance(child, (dict, list)):
                yield from iter_record_dicts(child)


def load_observations(
    summary_path: Path, max_steps: int | None
) -> list[Observation]:
    with summary_path.open("r", encoding="utf-8") as handle:
        document: Any = json.load(handle)

    observations: list[Observation] = []
    for index, record in enumerate(iter_record_dicts(document), start=1):
        if max_steps is not None and index > max_steps:
            break
        missing = [field for field in PROVENANCE_FIELDS if field not in record]
        if missing:
            raise ValueError(f"Record {index} is missing required fields: {missing}")

        values = {
            field: numeric_value(record[field], field, index)
            for field in PROVENANCE_FIELDS
        }
        point = Observation(
            alpha_deg=values["alpha_deg"],
            theta_deg=values["theta_deg"],
            d_um=values["d_um"],
            pressure_Pa=values["pressure_Pa"],
        )
        if point.d_um <= 0.0 or not math.isfinite(point.d_nm):
            raise ValueError(
                f"Record {index}: separation must be positive and finite in nm."
            )
        observations.append(point)

    if not observations:
        raise ValueError(
            f"No empirical records with alpha_deg, theta_deg, d_um, and "
            f"pressure_Pa were found in {summary_path}."
        )

    return sorted(
        observations, key=lambda p: (p.alpha_deg, p.theta_deg, p.d_um)
    )


def find_summary(root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Summary does not exist: {path}")
        return path

    preferred = root / PREFERRED_SWEEP / SUMMARY_FILENAME
    if preferred.is_file():
        return preferred.resolve()

    # Never silently fall back to a sweep older than the known post-bugfix run.
    cutoff = PREFERRED_SWEEP.removeprefix("results_sweet_spot_sweep_")
    candidates: list[tuple[str, Path]] = []
    pattern = re.compile(r"results_sweet_spot_sweep_(\d{8}_\d{6})")
    for path in root.glob(f"results_sweet_spot_sweep_*/{SUMMARY_FILENAME}"):
        match = pattern.fullmatch(path.parent.name)
        if match is not None and match.group(1) >= cutoff and path.is_file():
            candidates.append((match.group(1), path))
    if not candidates:
        raise FileNotFoundError(
            f"No post-bugfix summary found under {root}. Expected {preferred}. "
            "Use --summary to supply its location explicitly."
        )
    return max(candidates, key=lambda item: item[0])[1].resolve()


def load_provenance_saver(root: Path) -> ProvenanceSaver:
    root_string = str(root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)
    module = importlib.import_module("utils.metrics_logger")
    function: Any = getattr(module, "save_plot_provenance", None)
    if not callable(function):
        raise TypeError("utils.metrics_logger.save_plot_provenance is not callable.")
    return cast(ProvenanceSaver, function)


def pressure_norm(points: Sequence[Observation]) -> TwoSlopeNorm:
    extent = max((abs(point.pressure_Pa) for point in points), default=0.0)
    # A non-degenerate color scale is needed even for empty/all-zero subsets.
    # This affects display limits only; it creates no pressure observations.
    if extent == 0.0:
        extent = 1.0
    return TwoSlopeNorm(vmin=-extent, vcenter=0.0, vmax=extent)


def configure_axes(ax: Axes, xlabel: str, ylabel: str) -> None:
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.22)
    ax.set_axisbelow(True)


def mark_empty(ax: Axes) -> None:
    ax.text(
        0.5,
        0.5,
        "No empirical points in this selection",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=10,
    )


def finish_line_axes(ax: Axes, series_count: int) -> None:
    ax.axhline(0.0, color="black", linewidth=0.8, alpha=0.6)
    ax.ticklabel_format(axis="y", style="sci", scilimits=(-3, 4))
    if series_count:
        ax.legend(fontsize=8, loc="best")
    else:
        mark_empty(ax)


def draw_line(
    ax: Axes,
    points: Sequence[Observation],
    x_field: str,
    label: str,
    color: Any,
    linestyle: str = "-",
) -> bool:
    if not points:
        return False
    ordered = sorted(
        points, key=lambda point: cast(float, getattr(point, x_field))
    )
    ax.plot(
        [getattr(point, x_field) for point in ordered],
        [point.pressure_Pa for point in ordered],
        marker="o",
        markersize=4,
        linewidth=1.3,
        linestyle=linestyle,
        color=color,
        label=label,
    )
    return True


def draw_empirical_map(
    fig: Figure,
    ax: Axes,
    points: Sequence[Observation],
    x_field: str,
    y_field: str,
    norm: TwoSlopeNorm,
) -> None:
    if not points:
        mark_empty(ax)
        return
    artist = ax.scatter(
        [getattr(point, x_field) for point in points],
        [getattr(point, y_field) for point in points],
        c=[point.pressure_Pa for point in points],
        cmap="RdBu_r",
        norm=norm,
        marker="s",
        s=75,
        edgecolors="black",
        linewidths=0.35,
    )
    colorbar = fig.colorbar(artist, ax=ax, pad=0.025)
    colorbar.set_label("Casimir Pressure P (Pa)")
    ax.margins(x=0.05, y=0.05)


def save_figure(
    fig: Figure,
    filename: str,
    output_dir: Path,
    summary_path: Path,
    provenance_saver: ProvenanceSaver,
    max_steps: int | None,
) -> None:
    path = output_dir / filename
    try:
        if max_steps is not None:
            fig.text(
                0.5,
                0.005,
                f"Micro-probe: first {max_steps} empirical records only",
                ha="center",
                fontsize=8,
            )
        fig.savefig(
            path,
            dpi=300,
            bbox_inches="tight",
            metadata={
                "Description": (
                    f"Empirical pressure_Pa data from {summary_path}; "
                    f"SI conversion already applied using MEEP_TO_PA={MEEP_TO_PA}. "
                    "No interpolation or synthetic pressures."
                )
            },
        )
        provenance_saver(str(path), str(summary_path), list(PROVENANCE_FIELDS))
        print(f"Saved {path}")
    finally:
        plt.close(fig)


def generate_figures(
    points: Sequence[Observation],
    output_dir: Path,
    summary_path: Path,
    provenance_saver: ProvenanceSaver,
    max_steps: int | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    colors = plt.get_cmap("tab10")
    epsilon_title = r"$\varepsilon_{\mathrm{bg}}=2.1$"

    def save(fig: Figure, name: str) -> None:
        save_figure(
            fig, name, output_dir, summary_path, provenance_saver, max_steps
        )

    pair1 = [point for point in points if approximately(point.d_um, 0.10)]
    fig, ax = plt.subplots(figsize=(8.5, 5.4), layout="constrained")
    count = 0
    for index, alpha in enumerate(ALPHAS):
        selected = [
            point for point in pair1 if approximately(point.alpha_deg, alpha)
        ]
        count += int(
            draw_line(
                ax, selected, "theta_deg", rf"$\alpha={alpha:g}^\circ$",
                colors(index),
            )
        )
    configure_axes(
        ax, r"Twist Angle $\theta$ (deg)", "Casimir Pressure P (Pa)"
    )
    ax.set_title(f"Empirical pressure at d = 100 nm; {epsilon_title}")
    finish_line_axes(ax, count)
    save(fig, "pair1_theta_alpha_1d.png")

    fig, ax = plt.subplots(figsize=(8.5, 5.4), layout="constrained")
    configure_axes(
        ax, r"Twist Angle $\theta$ (deg)", r"Wall Slope $\alpha$ (deg)"
    )
    ax.set_title(
        f"Empirical P(θ, α) at d = 100 nm; {epsilon_title}\n"
        "Observed points only (no interpolation)"
    )
    draw_empirical_map(fig, ax, pair1, "theta_deg", "alpha_deg", pressure_norm(pair1))
    save(fig, "pair1_theta_alpha_2d.png")

    distance_points = [point for point in points if in_distance_window(point)]
    pair2 = [
        point
        for point in distance_points
        if any(approximately(point.alpha_deg, alpha) for alpha in PAIR2_ALPHAS)
    ]
    fig, axes = plt.subplots(
        1, 2, figsize=(14, 5.4), layout="constrained", squeeze=False
    )
    for ax, alpha in zip(axes[0], PAIR2_ALPHAS, strict=True):
        count = 0
        for index, theta in enumerate(PAIR2_THETAS):
            selected = [
                point
                for point in pair2
                if approximately(point.alpha_deg, alpha)
                and approximately(point.theta_deg, theta)
            ]
            count += int(
                draw_line(
                    ax, selected, "d_nm", rf"$\theta={theta:g}^\circ$",
                    colors(index),
                )
            )
        configure_axes(ax, "Separation Distance d (nm)", "Casimir Pressure P (Pa)")
        ax.set_xlim(50.0, 350.0)
        ax.set_title(rf"$\alpha={alpha:g}^\circ$")
        finish_line_axes(ax, count)
    fig.suptitle(f"Empirical pressure versus separation; {epsilon_title}")
    save(fig, "pair2_theta_d_1d.png")

    fig, axes = plt.subplots(
        1, 2, figsize=(14, 5.4), layout="constrained", squeeze=False
    )
    norm = pressure_norm(pair2)
    for ax, alpha in zip(axes[0], PAIR2_ALPHAS, strict=True):
        selected = [
            point for point in pair2 if approximately(point.alpha_deg, alpha)
        ]
        configure_axes(ax, r"Twist Angle $\theta$ (deg)", "Separation d (nm)")
        ax.set_ylim(50.0, 350.0)
        ax.set_title(rf"$\alpha={alpha:g}^\circ$")
        draw_empirical_map(fig, ax, selected, "theta_deg", "d_nm", norm)
    fig.suptitle(
        f"Empirical P(θ, d); {epsilon_title}\n"
        "Observed points only (no interpolation)"
    )
    save(fig, "pair2_theta_d_2d.png")

    fig, axes = plt.subplots(
        1, 2, figsize=(14, 5.4), layout="constrained", squeeze=False
    )
    for ax, theta in zip(axes[0], PAIR3_THETAS, strict=True):
        count = 0
        for index, alpha in enumerate(ALPHAS):
            selected = [
                point
                for point in distance_points
                if approximately(point.alpha_deg, alpha)
                and approximately(point.theta_deg, theta)
            ]
            count += int(
                draw_line(
                    ax, selected, "d_nm", rf"$\alpha={alpha:g}^\circ$",
                    colors(index),
                )
            )
        configure_axes(ax, "Separation Distance d (nm)", "Casimir Pressure P (Pa)")
        ax.set_xlim(50.0, 350.0)
        ax.set_title(rf"$\theta={theta:g}^\circ$")
        finish_line_axes(ax, count)
    fig.suptitle(
        f"Cross-polarized sweet-spot empirical pressure; {epsilon_title}"
    )
    save(fig, "pair3_alpha_d_1d.png")

    maxima: dict[tuple[float, float], Observation] = {}
    for point in distance_points:
        if 80.0 - TOLERANCE <= point.theta_deg <= 94.0 + TOLERANCE:
            key = (point.alpha_deg, point.d_um)
            previous = maxima.get(key)
            if previous is None or point.pressure_Pa > previous.pressure_Pa:
                maxima[key] = point
    pair3_map = sorted(maxima.values(), key=lambda p: (p.alpha_deg, p.d_um))

    fig, ax = plt.subplots(figsize=(8.5, 5.4), layout="constrained")
    configure_axes(ax, r"Wall Slope $\alpha$ (deg)", "Separation d (nm)")
    ax.set_ylim(50.0, 350.0)
    ax.set_title(
        f"Empirical max P(α, d), θ ∈ [80°, 94°]; {epsilon_title}\n"
        "Maximum observed pressure; negative values retained"
    )
    draw_empirical_map(
        fig, ax, pair3_map, "alpha_deg", "d_nm", pressure_norm(pair3_map)
    )
    save(fig, "pair3_alpha_d_2d.png")


def main(argv: Sequence[str] | None = None) -> int:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Explicit summary JSON; defaults to the specified post-bugfix sweep.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "Papers" / "Fractal_Casimir_Nature_EM" / "figures",
        help="Figure output directory.",
    )
    parser.add_argument(
        "--max-steps",
        type=positive_integer,
        default=None,
        metavar="N",
        help=(
            "Process only the first N empirical records for micro-probing. "
            "All six figures are generated; unavailable selections stay empty."
        ),
    )
    args = parser.parse_args(argv)

    try:
        summary_path = find_summary(repository_root, args.summary)
        saver = load_provenance_saver(repository_root)
        points = load_observations(summary_path, args.max_steps)
        print(f"Source: {summary_path}")
        print(
            f"Loaded {len(points)} empirical records. Using pressure_Pa directly "
            f"in SI Pa (MEEP_TO_PA={MEEP_TO_PA}; no second conversion)."
        )
        if args.max_steps is not None:
            print("Micro-probe enabled: figures may contain incomplete selections.")
        generate_figures(
            points,
            args.output_dir.expanduser().resolve(),
            summary_path,
            saver,
            args.max_steps,
        )
    except Exception as exc:
        print(f"Figure generation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
