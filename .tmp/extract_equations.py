import re

with open("C:/Users/gorengor/Goren/IUB/Research/FractalCasimirEffect/Science/Gordon_Fractal_Unified.tex", "r", encoding="utf-8") as f:
    text = f.read()

# Find all equation environments
equations = re.findall(r'\\begin\{equation\}.*?\\end\{equation\}', text, re.DOTALL)
equations_align = re.findall(r'\\begin\{align\}.*?\\end\{align\}', text, re.DOTALL)

all_eqs = equations + equations_align
for eq in all_eqs:
    if any(x in eq for x in ["C", "eta", "F_", "eta_", "per"]):
        print("-" * 40)
        print(eq.strip())
