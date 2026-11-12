#!/bin/bash
# Master launcher for all 4 Ultra-Fine Fractal Casimir Engine verification campaigns on IUB BigRed 200.
# Run from the repository or worktree root on branch `fractal-casimir-engine`:
#   bash fractal_casimir_engine/slurm/dispatch_all_ultrafine_bigred200.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "fractal-casimir-engine" ]]; then
    echo "[ERROR] Current branch is '$CURRENT_BRANCH' (expected 'fractal-casimir-engine')." >&2
    echo "Switch branch or create an isolated worktree first:" >&2
    echo "  git fetch origin fractal-casimir-engine && git checkout fractal-casimir-engine" >&2
    exit 1
fi

mkdir -p -- .tmp logs fractal_casimir_engine/results/ultrafine fractal_casimir_engine/figures
UF2_CKPT_DIR="${SLATE:-/N/slate/$USER}/fce_uf_ckpt/uf2"
rm -f -- "${UF2_CKPT_DIR}/.uf2a_submitted.stamp" ".tmp/fce_uf_ckpt/uf2/.uf2a_submitted.stamp" 2>/dev/null || true

echo "=== Submitting All 4 Ultra-Fine Verification Suites on BigRed 200 ==="
UF1_ID="$(sbatch --parsable fractal_casimir_engine/slurm/submit_eng_uf1_mesh_gpu.slurm)"
echo "  [1/4] Suite 1 (eng_uf1 - 5-Level Mesh/Quadrature Convergence & 420-State Landscape): Job ${UF1_ID}"

UF2_ID="$(sbatch --parsable fractal_casimir_engine/slurm/submit_eng_uf2_meep_cpu.slurm)"
echo "  [2/4] Suite 2 (eng_uf2 - 3D Meep FDTD Stress Tensor Array 1-8%4, dx=10 nm):         Job ${UF2_ID}"
echo "        (eng_uf2a GPU aggregator auto-dispatches once all 8 uf2_task_01..08.json complete)"

UF3_ID="$(sbatch --parsable fractal_casimir_engine/slurm/submit_eng_uf3_switch_gpu.slurm)"
echo "  [3/4] Suite 3 (eng_uf3 - Physical VO2 & Photo-Si Switching Thermodynamics):         Job ${UF3_ID}"

UF4_ID="$(sbatch --parsable fractal_casimir_engine/slurm/submit_eng_uf4_6dof_gpu.slurm)"
echo "  [4/4] Suite 4 (eng_uf4 - Full 4-Sector 6-DOF Pull-In Hessian & EBL Rounding):       Job ${UF4_ID}"

echo ""
echo "=== Live Slurm Queue (8-char job names: eng_uf1, eng_uf2, eng_uf2a, eng_uf3, eng_uf4) ==="
squeue -u "$USER" -o "%.18i %.9P %.10j %.8u %.2t %.10M %.6D %R" || squeue -u "$USER"
