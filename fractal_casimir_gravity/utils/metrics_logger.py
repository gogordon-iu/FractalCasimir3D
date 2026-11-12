"""
Provenance Logger Utility for Grounded Experiment Pipelines.
Enforces empirical tracking across experiment execution, plot generation,
LaTeX macro synchronization, and manuscript mapping.
"""

import os
import sys
import json
import inspect
import hashlib
import datetime
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import platform

RESULTS_DIR = Path("results")
DEFAULT_METRICS_PATH = RESULTS_DIR / "provenance_metrics.json"
DEFAULT_MACROS_PATH = RESULTS_DIR / "macros_results.tex"
DEFAULT_MAP_PATH = Path("manuscript_provenance_map.json")

DIGIT_WORDS = {
    "0": "Zero",
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
}

# Built-in and commonly used package commands are not provenance metric macros.
# Names are case-sensitive, matching LaTeX command semantics.
STANDARD_LATEX_COMMANDS = set(
    """
    TeX LaTeX LaTeXe eTeX pdfTeX XeTeX XeLaTeX LuaTeX LuaLaTeX BibTeX
    MakeUppercase MakeLowercase MakeTextUppercase MakeTextLowercase
    NeedsTeXFormat ProvidesClass ProvidesPackage ProvidesFile
    LoadClass LoadClassWithOptions RequirePackage RequirePackageWithOptions
    DeclareOption ExecuteOptions ProcessOptions PassOptionsToPackage
    PassOptionsToClass AtBeginDocument AtEndDocument AtBeginDvi AtEndOfClass
    AtEndOfPackage InputIfFileExists IfFileExists
    ClassError ClassWarning ClassWarningNoLine ClassInfo
    PackageError PackageWarning PackageWarningNoLine PackageInfo
    DeclareRobustCommand DeclareMathOperator DeclareMathSymbol
    DeclareMathAlphabet DeclareSymbolFont DeclareSymbolFontAlphabet
    DeclareMathDelimiter DeclareMathAccent DeclareMathRadical
    DeclareFontFamily DeclareFontShape DeclareFontEncoding
    DeclareFontSubstitution DeclareTextCommand DeclareTextSymbol
    DeclareTextAccent DeclareTextComposite DeclareTextFontCommand
    NewDocumentCommand RenewDocumentCommand ProvideDocumentCommand
    DeclareDocumentCommand NewDocumentEnvironment RenewDocumentEnvironment
    ProvideDocumentEnvironment DeclareDocumentEnvironment
    NewCommandCopy RenewCommandCopy DeclareCommandCopy
    IfNoValueTF IfNoValueT IfNoValueF IfBooleanTF IfBooleanT IfBooleanF
    NewCounter NewLength NewEnvironment NewCommand
    Delta Gamma Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
    Alpha Beta Epsilon Zeta Eta Iota Kappa Mu Nu Omicron Rho Tau Chi
    Digamma Box
    Im Re Pr
    Big Bigg Bigl Bigr Bigm Biggl Biggr Biggm
    Arrowvert Vert Vvert
    Downarrow Uparrow Updownarrow Leftarrow Rightarrow Leftrightarrow
    Longleftarrow Longrightarrow Longleftrightarrow
    Lleftarrow Rrightarrow Lsh Rsh
    Leftrightarrows Rightleftarrows Leftrightharpoons Rightleftharpoons
    Uppercase Lowercase
    LARGE Large Huge Small Tiny Normalsize
    tiny scriptsize footnotesize small normalsize large huge
    Roman Alph
    S P
    AA AE DH DJ L NG O OE SS TH
    H C G
    IEEEPARstart IEEEtitleabstractindextext
    IEEEdisplaynontitleabstractindextext IEEEpeerreviewmaketitle
    IEEEauthorblockN IEEEauthorblockA IEEEauthorrefmark
    IEEEcompsocitemizethanks IEEEcompsocthanksitem
    IEEEcompsoctitleabstractindextext IEEEoverridecommandlockouts
    IEEEpubid IEEEpubidadjcol IEEEthanks IEEEkeywords
    IEEEbiography IEEEbiographynophoto
    IEEEeqnarray IEEEeqnarraybox IEEEeqnarrayboxm
    IEEEeqnarraynumspace IEEEeqnarraymulticol IEEEeqnarrayomit
    IEEEeqnarraydefcol IEEEeqnarraydefcolsep IEEEeqnarrayseprow
    IEEEeqnarrayseprowcut IEEEeqnarrayrulerow IEEEeqnarraydblrulerow
    IEEEeqnarraystrutsize IEEEeqnarraystrutmode
    IEEEyesnumber IEEEnonumber IEEEyessubnumber IEEEnosubnumber
    IEEEsettopmargin IEEEsettextwidth IEEEsettextheight
    IEEEtriggeratref IEEEtriggercmd IEEEoverridecommandlockouts
    IEEEraisesectionheading IEEEQED IEEEQEDhere
    IEEEnormaljot IEEEiedlistdecl IEEElabelindent
    IEEEilabelindent IEEEelabelindent IEEElabelindentfactor
    IEEEusemathlabelsep IEEEsetlabelwidth IEEEiedlabeljustifyc
    IEEEiedlabeljustifyl IEEEiedlabeljustifyr
    For EndFor ForAll ForEach EndForAll EndForEach
    If ElsIf ElseIf Else EndIf
    While EndWhile Repeat Until Loop EndLoop
    Require Ensure State Statex Return Break Continue
    Function EndFunction Procedure EndProcedure Call Comment
    Input Output Let Assert Print Do EndDo
    Switch Case Default EndSwitch EndCase
    Begin End True False And Or Not To Downto Step
    FOR ENDFOR FORALL FOREACH ENDFOREACH
    IF ELSIF ELSEIF ELSE ENDIF WHILE ENDWHILE
    REPEAT UNTIL LOOP ENDLOOP REQUIRE ENSURE
    STATE STATEX RETURN BREAK CONTINUE
    FUNCTION ENDFUNCTION PROCEDURE ENDPROCEDURE CALL COMMENT
    INPUT OUTPUT DO ENDDO TO TRUE FALSE AND OR NOT
    KwIn KwOut KwData KwResult KwTo KwBy KwRet
    KwAnd KwOr KwNot KwTrue KwFalse
    SetKw SetKwInput SetKwData SetKwFunction SetKwProg
    SetKwIF SetKwFor SetKwRepeat SetKwSwitch
    SetAlgoLined SetAlgoVlined SetAlgoNoLine
    SetAlgoCaptionSeparator SetAlgoCaptionLayout SetAlgoCaptionSkip
    SetAlgorithmName SetAlCapFnt SetAlCapNameFnt SetAlCapSty
    SetAlCapNameSty SetNlSty SetNlSkip SetNlRelativeSize
    DontPrintSemicolon PrintSemicolon LinesNumbered LinesNotNumbered
    IncMargin DecMargin RestyleAlgo
    Cref Crefrange Crefmultiformat Crefname
    Autoref Nameref Vref Vpageref Vrefrange
    Cite Citep Citet Citeauthor Citeyear Citealt Citealp
    Textcite Parencite Footcite Footcitetext Autocite
    """.split()
)


def _get_caller_info(skip_frames: int = 2) -> Dict[str, Any]:
    stack = inspect.stack()
    if not stack:
        return {"source_file": "UNKNOWN", "source_function": "UNKNOWN", "line_number": -1}
    frame = stack[skip_frames] if len(stack) > skip_frames else stack[-1]
    module_path = os.path.relpath(frame.filename, os.getcwd()) if os.path.isabs(frame.filename) else frame.filename
    return {
        "source_file": str(module_path).replace("\\", "/"),
        "source_function": frame.function,
        "line_number": frame.lineno,
    }


def _compute_sha256(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return "UNKNOWN_OR_MISSING"
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _load_or_init_manifest(path: Path) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                manifest = loaded
        except Exception:
            pass

    # Migrate legacy top-level metric entries when no metrics section exists.
    if "metrics" not in manifest:
        reserved_keys = {"run_metadata", "intermediate_steps", "metrics"}
        metric_keys = [key for key in manifest if key not in reserved_keys]
        manifest["metrics"] = {key: manifest.pop(key) for key in metric_keys}

    for key in ("intermediate_steps", "metrics", "run_metadata"):
        if not isinstance(manifest.get(key), dict):
            manifest[key] = {}

    metadata_defaults = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "environment": platform.system(),
        "entry_point": _get_caller_info(skip_frames=3)["source_file"],
    }
    for key, value in metadata_defaults.items():
        manifest["run_metadata"].setdefault(key, value)

    return manifest


def log_step(name: str, data: Any, metrics_path: str = str(DEFAULT_METRICS_PATH)) -> None:
    """Records intermediate pipeline state transitions, splits, or matrix reductions."""
    path = Path(metrics_path)
    manifest = _load_or_init_manifest(path)
    caller = _get_caller_info(skip_frames=1)

    manifest["intermediate_steps"][name] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_file": caller["source_file"],
        "source_function": caller["source_function"],
        "line_number": caller["line_number"],
        "data_summary": data,
    }
    manifest["run_metadata"]["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def log_metric(
    key: str,
    value: Any,
    step_id: Optional[str] = None,
    metrics_path: str = str(DEFAULT_METRICS_PATH),
) -> None:
    """Records final metric with rigorous caller lineage."""
    path = Path(metrics_path)
    manifest = _load_or_init_manifest(path)
    caller = _get_caller_info(skip_frames=1)

    manifest["metrics"][key] = {
        "value": value,
        "source_file": caller["source_file"],
        "source_function": caller["source_function"],
        "line_number": caller["line_number"],
        "step_id": step_id or "final_evaluation",
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    manifest["run_metadata"]["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _sanitize_macro_name(key: str) -> str:
    """
    Sanitizes arbitrary string into a standard LaTeX macro name.
    Standard LaTeX requires command names to consist solely of alphabet letters [a-zA-Z].
    Digits are converted into words (e.g. 1 -> One) to prevent LaTeX syntax errors.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", key)
    words = cleaned.split()
    sanitized_words = []
    for word in words:
        word_chars = []
        for char in word:
            if char.isdigit():
                word_chars.append(DIGIT_WORDS[char])
            else:
                word_chars.append(char)
        sanitized_words.append("".join(word_chars).capitalize())
    result = "".join(sanitized_words)
    # Strictly enforce pure alphabetic characters for valid LaTeX \\newcommand
    result = re.sub(r"[^a-zA-Z]", "", result)
    return result or "MacroValue"


def _format_macro_value(val: Any) -> str:
    """Format numeric or string metric safely for both LaTeX text and math modes."""
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val == 0.0:
            return "0"
        abs_v = abs(val)
        if abs_v < 1.0e-3 or abs_v >= 1.0e5:
            sci = f"{val:.2e}"
            mant_str, exp_str = sci.split("e")
            exp_int = int(exp_str)
            return f"\\ensuremath{{{mant_str}\\times 10^{{{exp_int}}}}}"
        s = f"{val:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("", "-") else s
    return str(val)


def export_macros(
    metrics_path: str = str(DEFAULT_METRICS_PATH),
    output_path: str = str(DEFAULT_MACROS_PATH),
) -> None:
    """Exports scalar values in provenance_metrics.json into LaTeX macros."""
    in_path = Path(metrics_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        raise FileNotFoundError(f"[ERROR: RUN_DATA_MISSING] Cannot find metrics manifest at {metrics_path}")

    with open(in_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    metrics = manifest.get("metrics", {})
    lines = [
        "% Auto-generated by utils.metrics_logger. DO NOT EDIT DIRECTLY.",
        f"% Generated at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        "",
    ]

    for key, data in sorted(metrics.items()):
        val = data.get("value")
        if isinstance(val, (int, float, str)):
            macro_name = _sanitize_macro_name(key)
            formatted_val = _format_macro_value(val)
            lines.append(f"\\newcommand{{\\{macro_name}}}{{{formatted_val}}}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def save_plot_provenance(
    figure_path: str,
    data_source: str,
    columns_used: List[str],
    sidecar_suffix: str = ".provenance.json",
) -> str:
    """Generates an immutable sidecar JSON for a generated figure."""
    fig = Path(figure_path)
    sidecar_path = fig.parent / f"{fig.stem}{sidecar_suffix}"
    caller = _get_caller_info(skip_frames=1)

    sidecar_data = {
        "figure_file": str(fig).replace("\\", "/"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_source": {
            "path": str(data_source).replace("\\", "/"),
            "sha256": _compute_sha256(data_source),
        },
        "data_slices_columns": columns_used,
        "generating_code": {
            "source_file": caller["source_file"],
            "source_function": caller["source_function"],
            "line_number": caller["line_number"],
        },
    }

    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, indent=2)

    return str(sidecar_path)


def generate_manuscript_map(
    manuscript_path: str,
    output_map_path: str = str(DEFAULT_MAP_PATH),
    metrics_path: str = str(DEFAULT_METRICS_PATH),
    figures_dir: str = "figures",
) -> Dict[str, Any]:
    """Scans manuscript for macro/figure citations and builds manuscript_provenance_map.json."""
    ms_path = Path(manuscript_path)
    if not ms_path.exists():
        raise FileNotFoundError(f"Manuscript not found at {manuscript_path}")

    with open(ms_path, "r", encoding="utf-8") as f:
        text = f.read()

    metrics_manifest_path = Path(metrics_path)
    metrics_data = {}
    if metrics_manifest_path.exists():
        with open(metrics_manifest_path, "r", encoding="utf-8") as f:
            metrics_data = json.load(f).get("metrics", {})

    ledger: Dict[str, Any] = {"macros": {}, "figures": {}, "audit_status": "PASS"}

    macro_matches = re.findall(r"\\([A-Z][a-zA-Z]+)", text)
    for m in sorted(set(macro_matches)):
        if m in STANDARD_LATEX_COMMANDS:
            continue

        macro_key_full = f"\\{m}"
        matched_key = None
        for k in metrics_data.keys():
            if _sanitize_macro_name(k) == m:
                matched_key = k
                break

        if matched_key:
            record = metrics_data[matched_key]
            ledger["macros"][macro_key_full] = {
                "value": record.get("value"),
                "source_metric_key": matched_key,
                "source_file": record.get("source_file"),
                "source_function": record.get("source_function"),
                "intermediate_step_id": record.get("step_id"),
                "provenance_artifact": str(metrics_manifest_path).replace("\\", "/"),
            }
        else:
            ledger["macros"][macro_key_full] = {
                "status": "UNRESOLVED_MACRO",
                "note": "Macro referenced in text but not found in provenance_metrics.json",
            }
            ledger["audit_status"] = "FAIL"

    fig_dir = Path(figures_dir)
    if fig_dir.exists():
        for sidecar in fig_dir.glob("*.provenance.json"):
            base_fig_name = sidecar.name.replace(".provenance.json", "")
            if base_fig_name in text:
                try:
                    with open(sidecar, "r", encoding="utf-8") as sf:
                        s_data = json.load(sf)
                    ledger["figures"][base_fig_name] = {
                        "figure_file": s_data.get("figure_file"),
                        "sidecar_artifact": str(sidecar).replace("\\", "/"),
                        "source_data": s_data.get("input_source", {}).get("path"),
                        "source_sha256": s_data.get("input_source", {}).get("sha256"),
                        "generating_function": s_data.get("generating_code", {}).get("source_function"),
                    }
                except Exception:
                    ledger["figures"][base_fig_name] = {"status": "INVALID_SIDECAR"}
                    ledger["audit_status"] = "FAIL"

    out_path = Path(output_map_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)

    return ledger


def init_workspace(target_dir: str = "utils") -> str:
    """Scaffolds metrics_logger.py into the specified target directory of the active project."""
    target_path = Path(target_dir) / "metrics_logger.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    this_file = Path(__file__).resolve()
    shutil.copy2(this_file, target_path)
    print(f"[METRICS-LOGGER] Installed local copy to {target_path}")
    return str(target_path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        target = sys.argv[2] if len(sys.argv) > 2 else "utils"
        init_workspace(target)
    else:
        print("Testing metrics_logger provenance harness...")
        log_step("test_reduction", {"dim": 128, "norm": 1.042})
        log_metric("accuracy_top1", 94.25, step_id="eval_test_split")
        log_metric("f1_score", 0.912, step_id="eval_test_split")
        export_macros()
        save_plot_provenance("figures/demo_loss.png", "results/provenance_metrics.json", ["accuracy_top1"])
        print("Verification complete. LaTeX macros and provenance sidecar generated successfully.")
