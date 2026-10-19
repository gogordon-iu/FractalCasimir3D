#!/usr/bin/env python3
"""Apply the manuscript audit patches atomically; line numbers are advisory."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Callable

Patch = Callable[[str], str]


def replace_exact(text: str, old: str, new: str) -> str:
    """Require exactly one original or already-patched occurrence."""
    patched = text.count(new)
    remaining = text.replace(new, "").count(old)
    if patched == 1 and remaining == 0:
        return text
    if patched != 0 or remaining != 1:
        raise ValueError(
            f"Expected one unambiguous occurrence of {old!r}; "
            f"found {remaining} original and {patched} patched occurrences."
        )
    return text.replace(old, new, 1)


def replacements(*pairs: tuple[str, str]) -> Patch:
    def apply(text: str) -> str:
        for old, new in pairs:
            text = replace_exact(text, old, new)
        return text

    return apply


def environment_span(text: str, label: str, environment: str) -> tuple[int, int]:
    marker = rf"\label{{{label}}}"
    if text.count(marker) != 1:
        raise ValueError(f"Expected exactly one {marker}.")
    position = text.index(marker)
    starts = list(
        re.finditer(r"\\begin\{" + re.escape(environment) + r"\*?\}", text[:position])
    )
    if not starts:
        raise ValueError(f"No enclosing {environment} for {label}.")
    opening = starts[-1]
    name = opening.group().removeprefix(r"\begin{").removesuffix("}")
    closing = rf"\end{{{name}}}"
    end = text.find(closing, opening.end())
    if end < position:
        raise ValueError(f"Label {label} is outside its {environment}.")
    return opening.start(), end + len(closing)


TABLE_ROWS = (
    r"0.30 & \ScalingLZeropthreezeroRFourzeroPressure & \ModelOnePredLZeropthreezero & \ModelTwoPredLZeropthreezero & \ModelThreePredLZeropthreezero & \ModelFourPredLZeropthreezero \\",
    r"0.40 & \ScalingLZeropfourzeroRFourzeroPressure & \ModelOnePredLZeropfourzero & \ModelTwoPredLZeropfourzero & \ModelThreePredLZeropfourzero & \ModelFourPredLZeropfourzero \\",
    r"0.50 & \ScalingLZeropfivezeroRFourzeroPressure & \ModelOnePredLZeropfivezero & \ModelTwoPredLZeropfivezero & \ModelThreePredLZeropfivezero & \ModelFourPredLZeropfivezero \\",
    r"0.60 & \ScalingLZeropsixzeroRFourzeroPressure & \ModelOnePredLZeropsixzero & \ModelTwoPredLZeropsixzero & \ModelThreePredLZeropsixzero & \ModelFourPredLZeropsixzero \\",
    r"2.00 & \ScalingLTwopzerozeroRFourzeroPressure & \ModelOnePredLTwopzerozero & \ModelTwoPredLTwopzerozero & \ModelThreePredLTwopzerozero & \ModelFourPredLTwopzerozero \\",
    r"3.00 & \ScalingLThreepzerozeroRFourzeroPressure & \ModelOnePredLThreepzerozero & \ModelTwoPredLThreepzerozero & \ModelThreePredLThreepzerozero & \ModelFourPredLThreepzerozero \\",
    r"4.00 & \ScalingLFourpzerozeroRFourzeroPressure & \ModelOnePredLFourpzerozero & \ModelTwoPredLFourpzerozero & \ModelThreePredLFourpzerozero & \ModelFourPredLFourpzerozero \\",
    r"4.50 & \ScalingLFourpfivezeroRFourzeroPressure & +\ModelOnePredLFourpfivezero & \ModelTwoPredLFourpfivezero & \ModelThreePredLFourpfivezero & \ModelFourPredLFourpfivezero \\",
)


def patch_table(text: str) -> str:
    start, end = environment_span(text, "tab:fit_comparison", "table")
    table = text[start:end]
    for row in TABLE_ROWS:
        value = row.split(" & ", 1)[0]
        pattern = re.compile(
            rf"^(?P<indent>[ \t]*){re.escape(value)}[ \t]*&[^\n]*$",
            re.MULTILINE,
        )
        matches = list(pattern.finditer(table))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one Table 2 row for {value}.")
        match = matches[0]
        if match.group().count("&") != 5 or r"\\" not in match.group():
            raise ValueError(f"Malformed six-column Table 2 row for {value}.")
        table = (
            table[:match.start()]
            + match.group("indent")
            + row
            + table[match.end():]
        )
    return text[:start] + table + text[end:]


ITEMS = r"""    \item $\alpha = \SweetSpotOneAlpha^\circ, \theta = \SweetSpotOneTheta^\circ, d = \SweetSpotOneD\text{ nm} \implies P = +\SweetSpotOnePressureMeep$ Meep units ($\mathbf{+\SweetSpotOnePressure\text{ Pa}}$) (\textbf{REPULSIVE})
    \item $\alpha = \SweetSpotThreeAlpha^\circ, \theta = \SweetSpotThreeTheta^\circ, d = \SweetSpotThreeD\text{ nm} \implies P = +\SweetSpotThreePressureMeep$ Meep units ($\mathbf{+\SweetSpotThreePressure\text{ Pa}}$) (\textbf{REPULSIVE})
    \item $\alpha = \SweetSpotFourAlpha^\circ, \theta = \SweetSpotFourTheta^\circ, d = \SweetSpotFourD\text{ nm} \implies P = +\SweetSpotFourPressureMeep$ Meep units ($\mathbf{+\SweetSpotFourPressure\text{ Pa}}$) (\textbf{REPULSIVE})
    \item $\alpha = \SweetSpotRepRowFourteenAlphaDeg{}^\circ, \theta = \SweetSpotRepRowFourteenThetaDeg{}^\circ, d = \SweetSpotRepRowFourteenDNm{}\text{ nm} \implies P = +\SweetSpotRepRowFourteenPPa{}\text{ Pa}$ (\textbf{REPULSIVE}; Table~\ref{tab:sweet_spot_repulsion})
    \item $\alpha = \SweetSpotRepRowFifteenAlphaDeg{}^\circ, \theta = \SweetSpotRepRowFifteenThetaDeg{}^\circ, d = \SweetSpotRepRowFifteenDNm{}\text{ nm} \implies P = +\SweetSpotRepRowFifteenPPa{}\text{ Pa}$ (\textbf{REPULSIVE}; Table~\ref{tab:sweet_spot_repulsion})"""


def patch_items(text: str) -> str:
    figure_start, _ = environment_span(text, "fig:pair2_plots", "figure")
    begin = text.rfind(r"\begin{itemize}", 0, figure_start)
    if begin < 0:
        raise ValueError("Cannot find the Pair 2 itemize environment.")
    start = begin + len(r"\begin{itemize}")
    end = text.find(r"\end{itemize}", start)
    if end < start or end > figure_start:
        raise ValueError("Pair 2 itemize environment is not closed before its figure.")
    body = text[start:end]
    lines = [line for line in body.splitlines() if line.strip()]
    if len(lines) != 5 or any(
        not line.lstrip().startswith(r"\item ") or "REPULSIVE" not in line
        for line in lines
    ):
        raise ValueError("Expected five single-line repulsive Pair 2 items.")
    return text[:start] + "\n" + ITEMS + "\n" + text[end:]


PAIR_THREE = r"""

\subsubsection{Pair 3: Corrugation Wall Slope $\alpha$ versus Separation Distance $d$}

Figure~\ref{fig:pair3_plots} shows the one-dimensional profiles and two-dimensional map for corrugation wall slope $\alpha$ versus separation distance $d$.

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.48\textwidth]{figures/pair3_alpha_d_1d.png}
    \hfill
    \includegraphics[width=0.48\textwidth]{figures/pair3_alpha_d_2d.png}
    \caption{Pair 3: corrugation wall slope $\alpha$ versus separation distance $d$. Left: one-dimensional profiles. Right: two-dimensional map.}
    \label{fig:pair3_plots}
\end{figure}"""


def insert_pair_three(text: str) -> str:
    _, end = environment_span(text, "fig:pair2_plots", "figure")
    if r"\label{fig:pair3_plots}" in text:
        if text[end:end + len(PAIR_THREE)] != PAIR_THREE:
            raise ValueError("An unexpected Pair 3 figure already exists.")
        if text.count(r"\label{fig:pair3_plots}") != 1:
            raise ValueError("Duplicate Pair 3 figure labels.")
        return text
    return text[:end] + PAIR_THREE + text[end:]


PATCHES: tuple[Patch, ...] = (
    replacements((
        r"\mathcal{N}(\omega) \approx \frac{V_s}{\Gamma(d_s/2)} \omega^{d_s - 1},",
        r"\mathcal{N}(\omega) \approx \frac{V_s}{\Gamma(d_s/2)\,c^{d_s}} \omega^{d_s - 1},",
    )),
    replacements((
        r"\left( \frac{k_B T}{\hbar} \right)^{d_s}.",
        r"\left( \frac{k_B T}{\hbar c} \right)^{d_s}.",
    )),
    replacements((
        r"\frac{(k_B T)^{d_s + 1}}{\hbar^{d_s}}.",
        r"\frac{(k_B T)^{d_s + 1}}{(\hbar c)^{d_s}}.",
    )),
    replacements((
        "recovers the exact Stefan-Boltzmann law:",
        r"recovers the exact single-polarization Stefan-Boltzmann law (doubling to $\pi^2/15$ when summed over the two electromagnetic polarizations):",
    )),
    replacements((
        r"+ g_{\mu\nu} \left[ 2\xi V(z) - \frac{1}{2} V(z) \right] \phi^2.",
        r"- \frac{1}{2} g_{\mu\nu} V(z) \phi^2.",
    )),
    replacements((
        "The finite-temperature vacuum trace evaluates to:",
        "The isothermal scale-dilation trace of the interaction free energy evaluates to:",
    )),
    replacements((
        r"U_{\rm CP}(z) = -\frac{\hbar c \,\alpha(0)}{8\pi z^4}",
        r"U_{\rm CP}(z) = -\frac{3\hbar c \,\alpha(0)}{32\pi^2 \varepsilon_0 z^4}",
    )),
    replacements((
        r"|\langle 2s | \mathbf{p} | 1s \rangle|^2",
        r"\sum_{n} \frac{|\langle 2s | \mathbf{p} | np \rangle|^2}{E_n - E_{2s} + \hbar c k}",
    )),
    replacements((
        r"The continuous integral is discretized into $108$ imaginary frequency moments $\xi_n$.",
        r"The boundary source expansion is discretized into $108$ spatial discrete-cosine-transform (DCT) modes integrated in time with the Meep Casimir kernel $g(t)$.",
    )),
    patch_table,
    replacements(
        (
            r"more than $2.1\times$ lower than Model 1",
            r"more than $\ModelOneToModelFourSsrRatio{}\times$ lower than Model 1",
        ),
        (
            r"and \textbf{$7.1\times$ lower than Model 2}",
            r"and \textbf{$\ModelTwoToModelFourSsrRatio{}\times$ lower than Model 2}",
        ),
    ),
    replacements((
        r"P(d) = \frac{\hbar}{2\pi^2 c^3} \int_0^\infty \xi^3 d\xi \int_1^\infty p^2 dp \, e^{-2 p \xi d / c} \sum_{\alpha = {\rm TE, TM}} \frac{r_1^\alpha(i\xi, p) \, r_2^\alpha(i\xi, p)}{1 - r_1^\alpha(i\xi, p) \, r_2^\alpha(i\xi, p) e^{-2 p \xi d / c}},",
        r"P(d) = -\frac{\hbar n_{\rm bg}^3}{2\pi^2 c^3} \int_0^\infty \xi^3 d\xi \int_1^\infty p^2 dp \, e^{-2 n_{\rm bg} p \xi d / c} \sum_{\alpha = {\rm TE, TM}} \frac{r_1^\alpha(i\xi, p) \, r_2^\alpha(i\xi, p)}{1 - r_1^\alpha(i\xi, p) \, r_2^\alpha(i\xi, p) e^{-2 n_{\rm bg} p \xi d / c}},",
    )),
    patch_items,
    insert_pair_three,
    replacements((
        r"($1,504$ panels) to \texttt{High} ($3,120$ panels) and \texttt{Ultra\_High} ($6,016$ panels)",
        r"($\RotCfourTightslotNtwoStandardThetaZerozerosixpzeroPanelCount{}$ panels) to \texttt{High} ($\RotCfourTightslotNtwoHighThetaZerozerosixpzeroPanelCount{}$ panels) and \texttt{Ultra\_High} ($\RotCfourTightslotNtwoUltraHighThetaZerozerosixpzeroPanelCount{}$ panels)",
    )),
    replacements((
        "across 32 FDTD configurations",
        r"across \SweetSpotRepulsiveCount{} FDTD configurations",
    )),
)


def atomic_write(path: Path, original: bytes, updated: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(updated)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        if path.read_bytes() != original:
            raise ValueError("Manuscript changed during patching; refusing to overwrite.")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-steps", type=int, default=len(PATCHES),
        help="Apply the first N audit patches (0–16; default: 16).",
    )
    parser.add_argument(
        "--path", type=Path,
        default=Path(__file__).resolve().parent.parent
        / "Papers/Fractal_Casimir_Nature_EM/nature_fractal_casimir_em.tex",
        help="Manuscript path; defaults to the repository manuscript.",
    )
    args = parser.parse_args()
    if not 0 <= args.max_steps <= len(PATCHES):
        parser.error("--max-steps must be between 0 and 16.")

    try:
        path = args.path.resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Not a regular file: {path}")
        original = path.read_bytes()
        if not original:
            raise ValueError("Manuscript is empty.")
        text = original.decode("utf-8")
        newline = "\r\n" if "\r\n" in text else "\n"
        if "\r" in text.replace("\r\n", ""):
            raise ValueError("Unsupported bare carriage returns.")
        if newline == "\r\n" and "\n" in text.replace("\r\n", ""):
            raise ValueError("Mixed newline styles; refusing to normalize.")
        text = text.replace("\r\n", "\n")
        for number, patch in enumerate(PATCHES[:args.max_steps], start=1):
            try:
                text = patch(text)
            except ValueError as exc:
                raise ValueError(f"Patch {number}: {exc}") from exc
        updated = text.replace("\n", newline).encode("utf-8")
        if updated != original:
            atomic_write(path, original, updated)
            print(f"Updated {path} using {args.max_steps} audit steps.")
        else:
            print(f"No changes needed ({args.max_steps} audit steps checked).")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Audit patch failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
