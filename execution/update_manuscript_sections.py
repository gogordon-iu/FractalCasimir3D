#!/usr/bin/env python3
"""Idempotently update the fractal Casimir manuscript's requested sections."""

from __future__ import annotations

import argparse
import os
import stat
import tempfile
from pathlib import Path
from typing import Sequence


CLUTCH_ANCHOR = r"\input{tables/table_quantum_clutch.tex}"
CONVERGENCE_ANCHOR = "as the sub-panel regularization scale is reduced."
CONCLUSION_ANCHOR = r"\section{Conclusion}"
FEASIBILITY_INPUT = r"\input{tables/section_nems_feasibility.tex}"

ARCHITECTURE_LABEL = "fig:quantum_clutch_architecture_and_narrative"
VERIFICATION_LABEL = "fig:quantum_clutch_3solver_verification"
FEASIBILITY_LABEL = "fig:nature_feasibility_stability"

ARCHITECTURE_FIGURE = r"""\begin{figure*}[t]
\centering
\includegraphics[width=0.92\textwidth]{figures/fig_rotational_z_eff_clutch_blender.png}
\par\medskip
\includegraphics[width=0.95\textwidth]{figures/fig_nature_6step_narrative.png}
\caption{Rotational quantum-clutch architecture and operational narrative. The rendered architecture illustrates the effective separation and rotational configuration, while the narrative summarizes the proposed operating sequence.}
\label{fig:quantum_clutch_architecture_and_narrative}
\end{figure*}"""

VERIFICATION_FIGURE = r"""\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_rotational_clutch_3solver_verification.png}
\caption{Independent solver verification of the rotational quantum clutch. The comparison presents the force benchmarks and boundary-element continuum extrapolations used to assess quantitative convergence across rotational configurations.}
\label{fig:quantum_clutch_3solver_verification}
\end{figure*}"""

CONVERGENCE_ADDITION = r"""Extrapolating the 3D Vector-Dyadic BEM sequence to the continuum limit ($h = N_{\rm panels}^{-1/2} \to 0$) further confirms quantitative convergence: for \texttt{Rot\_C8\_Compact\_N2}, the three-tier linear continuum intercept at $\theta=48^\circ$ is $\RotCeightCompactNtwoBemThetafoureightContinuumFZPn{}\text{ pN}$ (matching the 4-pass 3D FDTD Meep force $\RotCeightCompactNtwoMeepThetafoureightFZPn{}\text{ pN}$) and the \texttt{High}-to-\texttt{Ultra\_High} Richardson extrapolation at $\theta=18^\circ$ is $\RotCeightCompactNtwoBemThetaoneeightRichardsonFZPn{}\text{ pN}$ (matching Meep $\RotCeightCompactNtwoMeepThetaoneeightFZPn{}\text{ pN}$); for \texttt{Rot\_C4\_TightSlot\_N2}, the \texttt{High}-to-\texttt{Ultra\_High} Richardson extrapolation at $\theta=18^\circ$ yields $\RotCfourTightslotNtwoBemThetaoneeightRichardsonFZPn{}\text{ pN}$ (matching Meep $\RotCfourTightslotNtwoMeepThetaoneeightFZPn{}\text{ pN}$) and the three-tier linear continuum intercept at $\theta=48^\circ$ yields $\RotCfourTightslotNtwoBemThetafoureightContinuumFZPn{}\text{ pN}$ (with Richardson extrapolation $\RotCfourTightslotNtwoBemThetafoureightRichardsonFZPn{}\text{ pN}$) alongside the Meep benchmark $\RotCfourTightslotNtwoMeepThetafoureightFZPn{}\text{ pN}$ (Fig.~\ref{fig:quantum_clutch_3solver_verification}, Fig.~\ref{fig:quantum_clutch_architecture_and_narrative})."""

FEASIBILITY_FIGURE = r"""\begin{figure*}[t]
\centering
\includegraphics[width=0.95\textwidth]{figures/fig_nature_feasibility_stability.png}
\caption{NEMS feasibility and stability assessment for the rotational quantum clutch at $T=\NatureRotCeightCompactNtwoCdToleranceTemperatureK{}\text{ K}$. The comparison summarizes the fabrication-tolerance and stability considerations relevant to operation.}
\label{fig:nature_feasibility_stability}
\end{figure*}"""


def has_figure(text: str, label: str) -> bool:
    """Check a label definition, not a cross-reference to that label."""
    return rf"\label{{{label}}}" in text


def require_unique_anchor(text: str, anchor: str) -> int:
    count = text.count(anchor)
    if count == 0:
        raise RuntimeError(f"Required insertion anchor not found: {anchor!r}")
    if count != 1:
        raise RuntimeError(
            f"Required insertion anchor is ambiguous ({count} matches): {anchor!r}"
        )
    return text.index(anchor)


def figure_bounds(text: str, label: str) -> tuple[int, int]:
    """Return bounds of the figure* containing an existing label."""
    marker = rf"\label{{{label}}}"
    label_position = require_unique_anchor(text, marker)
    opening = r"\begin{figure*}"
    closing = r"\end{figure*}"
    start = text.rfind(opening, 0, label_position)
    end = text.find(closing, label_position)
    if start < 0 or end < 0:
        raise RuntimeError(f"Label {label!r} is not inside a complete figure*.")
    if text.find(closing, start, label_position) != -1:
        raise RuntimeError(f"Label {label!r} is outside its figure* environment.")
    return start, end + len(closing)


def update_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("Manuscript content must be a string.")

    newline = "\r\n" if "\r\n" in text else "\n"

    def block(value: str) -> str:
        return value.replace("\n", newline)

    missing_architecture = not has_figure(text, ARCHITECTURE_LABEL)
    missing_verification = not has_figure(text, VERIFICATION_LABEL)
    missing_convergence = CONVERGENCE_ADDITION not in text
    missing_input = FEASIBILITY_INPUT not in text
    missing_feasibility = not has_figure(text, FEASIBILITY_LABEL)

    # Validate all required anchors before preparing any changes.
    if missing_architecture or missing_verification:
        require_unique_anchor(text, CLUTCH_ANCHOR)
    if missing_convergence:
        require_unique_anchor(text, CONVERGENCE_ANCHOR)
    if missing_input or missing_feasibility:
        require_unique_anchor(text, CONCLUSION_ANCHOR)

    if missing_architecture:
        position = text.index(CLUTCH_ANCHOR) + len(CLUTCH_ANCHOR)
        insertion = newline * 2 + block(ARCHITECTURE_FIGURE) + newline * 2
        text = text[:position] + insertion + text[position:]

    if missing_verification:
        _, position = figure_bounds(text, ARCHITECTURE_LABEL)
        insertion = newline * 2 + block(VERIFICATION_FIGURE) + newline * 2
        text = text[:position] + insertion + text[position:]

    if missing_convergence:
        position = text.index(CONVERGENCE_ANCHOR) + len(CONVERGENCE_ANCHOR)
        text = text[:position] + " " + CONVERGENCE_ADDITION + text[position:]

    if missing_input:
        if has_figure(text, FEASIBILITY_LABEL):
            position, _ = figure_bounds(text, FEASIBILITY_LABEL)
        else:
            position = text.index(CONCLUSION_ANCHOR)
        text = (
            text[:position]
            + FEASIBILITY_INPUT
            + newline * 2
            + text[position:]
        )

    if missing_feasibility:
        position = text.index(CONCLUSION_ANCHOR)
        text = (
            text[:position]
            + block(FEASIBILITY_FIGURE)
            + newline * 2
            + text[position:]
        )

    return text


def update_manuscript(path: Path) -> bool:
    """Atomically replace the UTF-8 manuscript only when changes are needed."""
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Manuscript path is not a regular file: {path}")

    original = path.read_bytes()
    updated = update_text(original.decode("utf-8")).encode("utf-8")
    if updated == original:
        return False

    permissions = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())

        temporary_path.chmod(permissions)
        if path.read_bytes() != original:
            raise RuntimeError(
                f"Manuscript changed during the update; refusing to overwrite: {path}"
            )
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return True


def main(argv: Sequence[str] | None = None) -> int:
    repository_root = Path(__file__).resolve().parent.parent
    default_path = (
        repository_root
        / "Papers"
        / "Fractal_Casimir_Nature_EM"
        / "nature_fractal_casimir_em.tex"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manuscript",
        type=Path,
        default=default_path,
        help="UTF-8 manuscript path (defaults to the repository manuscript).",
    )
    arguments = parser.parse_args(argv)
    changed = update_manuscript(arguments.manuscript)
    print("Manuscript updated." if changed else "Manuscript already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
