with open("C:/Users/gorengor/Goren/IUB/Research/FractalCasimirEffect/Science/Gordon_Fractal_Unified.tex", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "eta" in line or "deviation" in line or "Figure 2" in line or "figure2" in line or "PFA" in line:
        print(f"L{i+1}: {line.strip()}")
