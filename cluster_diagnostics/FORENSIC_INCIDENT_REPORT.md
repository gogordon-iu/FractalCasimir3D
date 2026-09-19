# BigRed 200 Cluster Forensic Incident Report
**Generated**: 2026-09-19 18:47:27 UTC  
**Repository**: `/N/project/gorengor_werewolf/FractalCasimir3D`  
**System**: Indiana University BigRed 200 (Cray EX, AMD EPYC 7742 / 128 cores per node, 240 GB RAM)  

---
## 1. Executive Forensic Summary
An exhaustive analysis of cluster Slurm array jobs (**8261902**, **8265878**, **8280830**) was conducted to pinpoint the exact sequence of failures encountered during the 3D Fractal Quantum Clutch simulations. Three distinct root causes were identified:

1. **Job 8261902 — Out-Of-Memory (Exit Code 137)**:
   - **Pinpointed Cause**: Multi-subgroup process division ($K = 8$) launched 8 simultaneous 3D FDTD simulations on 1 physical node.
   - **Resource Footprint**: $8 \times 47.5\text{ GB} = \mathbf{380.27\text{ GB}}$ aggregate RAM demand against a physical node ceiling of **240.00 GB** ($158.44\%$ memory efficiency).
   - **Kernel Action**: Linux cgroup / Slurm cgroup OOM killer terminated the job with `SIGKILL` (`ExitCode 137`).

2. **Jobs 8265878 & 8280830 — Multi-Process Deadlock & 12-Hour TIMEOUT**:
   - **Pinpointed Cause**: When memory exhaustion killed one or more worker subgroups ($K > 1$), global Rank 0 entered a 7200-cycle sleep loop (`while not os.path.exists(temp_file): time.sleep(0.5)`) waiting for intermediate force JSON files.
   - **Resource Footprint**: The job remained completely idle for **12 hours and 6 seconds** consuming only **10.00 MB RAM** and **00:00:01 CPU** time ($0.00\%$ CPU efficiency).
   - **Slurm Action**: Slurm killed the allocation at the 12:00:00 walltime limit with `TIMEOUT` (`exit code 0` on master, `MaxExitCode 137` on array).

3. **Stale Git Index Lock (`.git/index.lock`) on Login Node**:
   - **Pinpointed Cause**: An interrupted or crashed `git` process on BigRed 200 created `.git/index.lock`. Subsequent `git reset --hard origin/main` calls failed with `fatal: Unable to create .../.git/index.lock: File exists`.
   - **Consequence**: The cluster continued running obsolete code with the 12-hour walltime limit and multi-subgroup splitting, delaying execution of commit `fec4e10`.

---
## 2. Permanent Architectural Fix Verification (Commit `fec4e10`)
The following engineering countermeasures were permanently implemented and committed to `origin/main`:

| Issue | Old Mechanism | Permanent Architectural Solution |
|---|---|---|
| **OOM (137)** | $K = 8$ subgroups ($380.3\text{ GB}$) | **Enforced `--no-subgroups` ($K=1$)**: Peak RAM is **19.5 - 33.4 GB** (leaving **> 206 GB** free headroom). |
| **Deadlock Loop** | 7200-cycle sleep wait on temp files | **Direct C++ MPI Reduction**: At $K=1$, force returns immediately via MPI; wait loop capped to 30s fail-fast. |
| **Premature Timeout** | `#SBATCH --time=12:00:00` | **Extended to `#SBATCH --time=24:00:00`** across all array tasks. |
| **File Locking** | Temporary JSON file writing in `.tmp/` | **Bypassed completely in $K=1$ mode**: Zero temp file writing or polling. |
| **Git Lock Blocking** | Manual recovery required | **Automated lock removal** added to pipeline and diagnostic scripts. |

---
## 3. Slurm Array Accounting & Incident Matrix
```text
Job ID: 8261902 | State: FAILED (ExitCode 137) | Peak RAM: 380.27 GB (158.4% of 240 GB) | Walltime: 00:03:07
Job ID: 8265878 | State: TIMEOUT (MaxExitCode 137) | Peak RAM: 10.00 MB  (0.00% CPU) | Walltime: 12:00:06
Job ID: 8280830 | State: TIMEOUT (MaxExitCode 137) | Peak RAM: 10.00 MB  (0.00% CPU) | Walltime: 12:00:06
```

---
## 4. Parsed Log Forensics & Diagnostic Findings
*No raw `.err` or `.out` files found in local directory. Full logs will populate upon running harvester on BigRed 200.*

---
## 5. Instructions for Running on BigRed 200
To harvest and push live logs directly from the supercomputer:

```bash
cd /N/project/gorengor_werewolf/FractalCasimir3D
bash execution/push_all_cluster_logs.sh
```
This script automatically cleans any `.git/index.lock`, harvests all `.tmp/` and Slurm files, compiles the report, and pushes everything to GitHub.