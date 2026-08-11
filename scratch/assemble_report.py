import os
import sys
import subprocess

def close_pdf_viewers():
    """Close any processes on Windows locking PDF files."""
    viewers = ["Acrobat.exe", "AcroRd32.exe", "SumatraPDF.exe", "chrome.exe", "msedge.exe"]
    for v in viewers:
        try:
            subprocess.run(f"taskkill /f /im {v}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def main():
    print("==================================================")
    print("MASTER PDF REPORT ASSEMBLY ENGINE")
    print("(COMPILING DIRECTLY TO Papers/Fractal_Casimir_Version_02/fractal_casimir_report.pdf)")
    print("==================================================")

    close_pdf_viewers()

    repo_dir = "c:/Users/gorengor/Goren/IUB/Research/FractalCasimirEffect/Code/3Dsimulations"
    paper_dir = os.path.join(repo_dir, "Papers", "Fractal_Casimir_Version_02")
    source_tex = os.path.join(paper_dir, "report_body_source.tex")
    tables_tex_path = os.path.join(repo_dir, "scratch", "pairwise_tables.tex")
    dest_tex = os.path.join(paper_dir, "fractal_casimir_report.tex")
    dest_pdf = os.path.join(paper_dir, "fractal_casimir_report.pdf")

    if not os.path.exists(source_tex):
        print(f"Error: Source TeX template {source_tex} does not exist.")
        sys.exit(1)

    with open(source_tex, "r", encoding="utf-8") as f:
        tex_content = f.read()

    # Load fresh pairwise tables if available
    if os.path.exists(tables_tex_path):
        with open(tables_tex_path, "r", encoding="utf-8") as f:
            tables_content = f.read()
            
        start_marker = "\\begin{table}[h!]"
        end_marker = "\\section{Casimir Repulsion and Levitation Physics}"
        
        s_idx = tex_content.find("10.10.1 Pair 1")
        if s_idx != -1:
            t_start = tex_content.find(start_marker, s_idx)
            t_end = tex_content.find(end_marker, t_start)
            if t_start != -1 and t_end != -1:
                tex_content = tex_content[:t_start] + tables_content + "\n\n" + tex_content[t_end:]
                print("Successfully injected fresh scratch/pairwise_tables.tex into report_body_source.tex!")

    # Update report_body_source.tex directly
    with open(source_tex, "w", encoding="utf-8") as f:
        f.write(tex_content)

    # Write directly to destination fractal_casimir_report.tex
    with open(dest_tex, "w", encoding="utf-8") as f:
        f.write(tex_content)

    print(f"Wrote updated TeX source to {dest_tex} ({len(tex_content)} characters).")

    # Compile with pdflatex directly to fractal_casimir_report.pdf
    print("\nCompiling fractal_casimir_report.pdf with pdflatex...")
    cmd = ["pdflatex", "-interaction=nonstopmode", "fractal_casimir_report.tex"]
    result = subprocess.run(cmd, cwd=paper_dir, capture_output=True, text=True)

    if result.returncode != 0 and not os.path.exists(dest_pdf):
        print("pdflatex compilation error output:")
        print(result.stdout[-1000:])
        print(result.stderr[-1000:])
        sys.exit(1)

    # Run second pass for hyperref cross-references
    subprocess.run(cmd, cwd=paper_dir, capture_output=True, text=True)

    if os.path.exists(dest_pdf):
        print(f"\nSUCCESS! Compiled master report: {dest_pdf}")
    else:
        print("\nError: Failed to produce fractal_casimir_report.pdf")
        sys.exit(1)

if __name__ == "__main__":
    main()
