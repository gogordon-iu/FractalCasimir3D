from pathlib import Path


NEW_ENTRY = r"""## [2026-10-18] Manuscript .63\times$ Meep-to-SI Unit Mismatch, Per-Task Freshness Collision, & BigRed 200 Detached-HEAD Rebase Lockup
- **Bug:** execution/export_provenance_pipeline.py exported \SweetSpotOnePressure in dimensionless Meep units (3.61084) while 
ature_fractal_casimir_em.tex appended \text{ Pa} and hardcoded 13 equilibria, 
"""


def main():
    path = Path("BUG_LOG.md")
    original = path.read_bytes()
    entry = NEW_ENTRY.encode("utf-8")
    header = entry.split(b"\n", 1)[0]

    if original.endswith(entry):
        return
    if header in original.splitlines():
        raise ValueError(
            "The new entry header already exists with different content; "
            "BUG_LOG.md was not modified."
        )

    if not original or original.endswith(b"\n\n"):
        separator = b""
    elif original.endswith(b"\n"):
        separator = b"\n"
    else:
        separator = b"\n\n"

    # Append only: every existing byte remains unchanged.
    with path.open("ab") as stream:
        stream.write(separator + entry)


if __name__ == "__main__":
    main()
