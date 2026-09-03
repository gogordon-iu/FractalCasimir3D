import os
import sys
import subprocess
import time

def run_all():
    print("================================================================================")
    print("      MASTER QUANTUM GRAVITY & STRESS TENSOR TRACE PIPELINE ORCHESTRATOR        ")
    print("================================================================================")
    start_time = time.time()

    base_dir = "quantum_gravity_trace_analysis"
    figures_dir = os.path.join(base_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    scripts = [
        ("Pipeline 1 (3D Voxel Stress Tensor Mapping)", os.path.join(base_dir, "pipeline1_3d_tensor_mapper.py")),
        ("Pipeline 2 (Ricci Curvature & Quantum Gravity)", os.path.join(base_dir, "pipeline2_ricci_curvature_analyzer.py")),
        ("Pipeline 3 (Null Energy Condition & Inversion)", os.path.join(base_dir, "pipeline3_nec_boundary_mapper.py"))
    ]

    for name, script_path in scripts:
        print(f"\n[EXEC] Running {name}...")
        cmd = [sys.executable, script_path]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"ERROR: {name} failed with exit code {res.returncode}")
            sys.exit(1)
        print(f"[SUCCESS] {name} completed successfully.")

    elapsed = time.time() - start_time
    print("\n================================================================================")
    print(f"ALL 3 QUANTUM GRAVITY PIPELINES COMPLETED SUCCESSFULLY IN {elapsed:.2f} SECONDS!")
    print("Generated Artifacts & Figures in 'quantum_gravity_trace_analysis/':")
    print("  - pipeline1_tensor_field_data.json")
    print("  - pipeline2_ricci_curvature_summary.json")
    print("  - pipeline3_nec_boundary_summary.json")
    print("  - figures/figure_qg_pipeline1_tensor_fields.png / .pdf")
    print("  - figures/figure_qg_pipeline2_ricci_curvature.png / .pdf")
    print("  - figures/figure_qg_pipeline3_nec_boundaries.png / .pdf")
    print("================================================================================")

if __name__ == '__main__':
    run_all()
