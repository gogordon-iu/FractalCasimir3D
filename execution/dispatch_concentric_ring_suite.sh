#!/usr/bin/env bash
# Master dispatcher for the Concentric Cantor-Ring Casimir Clutch suite.
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "/N/project/gorengor_werewolf/FractalCasimir3D" ]]; then
    readonly REPO="/N/project/gorengor_werewolf/FractalCasimir3D"
else
    readonly REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
fi

usage() {
    cat <<'HELP'
Usage: execution/dispatch_concentric_ring_suite.sh SELECTION [OPTIONS]

Select exactly one task group:
  --all                 All 17 tasks
  --n1, --one-ring       Generation N=1: tasks 1-4
  --n2                  Generation N=2: tasks 5-8
  --n3                  Generation N=3: tasks 9-12
  --controls            Uniform and Flat Controls: tasks 13-17
  --tasks RANGE         Custom tasks, e.g. 1-4, 5-8, or 1,3,5

Options:
  --concurrency N       Maximum simultaneous array tasks (default: 2)
  --dry-run             Print commands without modifying files or submitting
  --help, -h            Show this help message

Examples:
  execution/dispatch_concentric_ring_suite.sh --all
  execution/dispatch_concentric_ring_suite.sh --one-ring --dry-run
  execution/dispatch_concentric_ring_suite.sh --tasks 1,3,5-8 --concurrency 3

If configurations are missing, the dispatcher locates a uniquely named
Python config generator containing "concentric", "ring", and "config".
Set CONCENTRIC_RING_CONFIG_GENERATOR to its repository-relative or absolute
path to override discovery. PYTHON may specify the Python executable.

Monitor submitted runs:
  python execution/monitor_all_casimir_runs.py
HELP
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

print_command() {
    printf '  '
    printf '%q ' "$@"
    printf '\n'
}

selection=""
task_spec=""
concurrency="2"
dry_run=0
python_bin="${PYTHON:-python}"

select_tasks() {
    [[ -z "$selection" ]] ||
        die "Select exactly one of --all, --n1, --n2, --n3, --controls, or --tasks."
    selection="$1"
    task_spec="$2"
}

while (($# > 0)); do
    case "$1" in
        --all)
            select_tasks "$1" "1-17"
            shift
            ;;
        --n1|--one-ring)
            select_tasks "$1" "1-4"
            shift
            ;;
        --n2)
            select_tasks "$1" "5-8"
            shift
            ;;
        --n3)
            select_tasks "$1" "9-12"
            shift
            ;;
        --controls)
            select_tasks "$1" "13-17"
            shift
            ;;
        --tasks)
            (($# >= 2)) || die "--tasks requires a range."
            select_tasks "$1" "$2"
            shift 2
            ;;
        --tasks=*)
            select_tasks "--tasks" "${1#*=}"
            shift
            ;;
        --concurrency)
            (($# >= 2)) || die "--concurrency requires a positive integer."
            concurrency="$2"
            shift 2
            ;;
        --concurrency=*)
            concurrency="${1#*=}"
            shift
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1. Use --help for usage."
            ;;
    esac
done

[[ -n "$selection" ]] || die "A task selection is required. Use --help."

# Limit digit counts before arithmetic expansion to prevent integer overflow.
[[ "$concurrency" =~ ^[0-9]{1,9}$ ]] ||
    die "--concurrency must be a positive integer of at most nine digits."
concurrency=$((10#$concurrency))
((concurrency > 0)) || die "--concurrency must be greater than zero."

[[ "$task_spec" =~ ^[0-9]{1,2}(-[0-9]{1,2})?(,[0-9]{1,2}(-[0-9]{1,2})?)*$ ]] ||
    die "Invalid task range '$task_spec'; use values such as 1-4 or 1,3,5."

declare -a selected=()
declare -a segments=()
IFS=',' read -r -a segments <<< "$task_spec"

for segment in "${segments[@]}"; do
    if [[ "$segment" == *-* ]]; then
        first="${segment%-*}"
        last="${segment#*-}"
    else
        first="$segment"
        last="$segment"
    fi

    first=$((10#$first))
    last=$((10#$last))
    ((first >= 1 && last <= 17 && first <= last)) ||
        die "Task ranges must be ascending and contained in 1-17: $segment"

    for ((task=first; task<=last; task++)); do
        selected[task]=1
    done
done

# Produce a sorted, deduplicated Slurm array specification.
tasks=""
task_count=0
for ((task=1; task<=17; task++)); do
    if [[ "${selected[task]:-0}" == "1" ]]; then
        tasks="${tasks:+$tasks,}$task"
        task_count=$((task_count + 1))
    fi
done
((task_count > 0)) || die "No tasks were selected."

[[ -d "$REPO" ]] || die "Repository directory does not exist: $REPO"
cd "$REPO"

for batch_file in \
    execution/submit_concentric_ring.sbatch \
    execution/submit_concentric_ring_plot.sbatch
do
    [[ -f "$batch_file" && -r "$batch_file" ]] ||
        die "Required submission file is missing or unreadable: $batch_file"
done

directories=(.tmp results_concentric_ring cluster_diagnostics/raw_logs)

if ((dry_run)); then
    printf 'Dry run; no files will be modified and no jobs submitted.\n'
    print_command cd "$REPO"
    print_command mkdir -p -- "${directories[@]}"
else
    command -v sbatch >/dev/null 2>&1 ||
        die "sbatch is unavailable. Run on a BigRed 200 Slurm login node."
    mkdir -p -- "${directories[@]}"
fi

if [[ ! -s sweep_configs_concentric_ring/config_017.json ]]; then
    command -v "$python_bin" >/dev/null 2>&1 ||
        die "Python executable is unavailable: $python_bin"

    if [[ -n "${CONCENTRIC_RING_CONFIG_GENERATOR:-}" ]]; then
        generator="$CONCENTRIC_RING_CONFIG_GENERATOR"
        [[ "$generator" == /* ]] || generator="$REPO/$generator"
        [[ -f "$generator" && -r "$generator" ]] ||
            die "Config generator is missing or unreadable: $generator"
    else
        # Discovery is read-only, including during --dry-run.
        if ! generator="$("$python_bin" - "$REPO" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
excluded = {
    ".git", ".tmp", ".venv", "venv", "__pycache__", "node_modules",
    "results_concentric_ring", "cluster_diagnostics",
    "sweep_configs_concentric_ring",
}
candidates = []
for directory, subdirectories, filenames in os.walk(root):
    subdirectories[:] = sorted(
        name for name in subdirectories
        if name not in excluded and not name.startswith(".")
    )
    for filename in sorted(filenames):
        name = filename.lower()
        if (
            name.endswith(".py")
            and "concentric" in name
            and "ring" in name
            and "config" in name
            and ("generat" in name or "make" in name or "build" in name)
        ):
            candidates.append(Path(directory) / filename)

if len(candidates) != 1:
    print(
        "Cannot uniquely identify the concentric-ring config generator. "
        "Set CONCENTRIC_RING_CONFIG_GENERATOR to the correct Python script.",
        file=sys.stderr,
    )
    for candidate in candidates:
        print(f"  Candidate: {candidate}", file=sys.stderr)
    sys.exit(1)

print(candidates[0])
PY
)"; then
            die "Config generator discovery failed."
        fi
    fi

    printf '%s\n' 'Generating missing sweep configurations:'
    print_command "$python_bin" "$generator"
    if ((!dry_run)); then
        "$python_bin" "$generator"
        [[ -s sweep_configs_concentric_ring/config_017.json ]] ||
            die "Generator did not create sweep_configs_concentric_ring/config_017.json."
    fi
fi

# Catch incomplete configuration sets before sending jobs to Slurm.
if ((!dry_run)); then
    for ((task=1; task<=17; task++)); do
        if [[ "${selected[task]:-0}" == "1" ]]; then
            printf -v config 'sweep_configs_concentric_ring/config_%03d.json' "$task"
            [[ -s "$config" && -r "$config" ]] ||
                die "Selected task $task has a missing, empty, or unreadable config: $config"
        fi
    done
fi

array_command=(
    sbatch
    --parsable
    "--array=${tasks}%${concurrency}"
    execution/submit_concentric_ring.sbatch
)

printf '\nSelected %s tasks: %s\n' "$task_count" "$tasks"
printf 'Maximum simultaneous array tasks: %s\n' "$concurrency"

if ((dry_run)); then
    print_command "${array_command[@]}"
    # This symbolic dependency is replaced with the actual ID during submission.
    printf '  sbatch --parsable --dependency=afterany:<ARRAY_JOB_ID> execution/submit_concentric_ring_plot.sbatch\n'
    printf '\n%s\n' 'Monitor after submission:'
    print_command "$python_bin" execution/monitor_all_casimir_runs.py
    exit 0
fi

printf '\n%s\n' 'Submitting array job:'
print_command "${array_command[@]}"
if ! array_response="$("${array_command[@]}")"; then
    die "Array submission failed; postprocessing was not submitted."
fi

# --parsable returns JOB_ID or JOB_ID;CLUSTER for federated submissions.
[[ "$array_response" =~ ^([0-9]+)(;([A-Za-z0-9_.-]+))?$ ]] ||
    die "Unexpected sbatch response '$array_response'; inspect squeue before retrying."
array_job_id="${BASH_REMATCH[1]}"
array_cluster="${BASH_REMATCH[3]:-}"

plot_command=(sbatch --parsable "--dependency=afterany:${array_job_id}")
if [[ -n "$array_cluster" ]]; then
    plot_command+=("--clusters=${array_cluster}")
fi
plot_command+=(execution/submit_concentric_ring_plot.sbatch)

printf '\n%s\n' 'Submitting postprocessing job:'
print_command "${plot_command[@]}"
if ! plot_response="$("${plot_command[@]}")"; then
    printf 'Array job %s remains submitted.\n' "$array_job_id" >&2
    printf '%s\n' 'Retry postprocessing with:' >&2
    print_command "${plot_command[@]}" >&2
    die "Postprocessing submission failed."
fi

[[ "$plot_response" =~ ^([0-9]+)(;([A-Za-z0-9_.-]+))?$ ]] ||
    die "Unexpected postprocessing response '$plot_response'; array job is $array_job_id."
plot_job_id="${BASH_REMATCH[1]}"

printf '\nSubmission confirmed.\n'
printf '  Array job ID:          %s\n' "$array_job_id"
printf '  Postprocessing job ID: %s\n' "$plot_job_id"
printf '  Dependency:            afterany:%s\n' "$array_job_id"
printf '\n%s\n' "Monitor suite status from $REPO:"
print_command "$python_bin" execution/monitor_all_casimir_runs.py
printf '\n%s\n' 'Inspect Slurm jobs:'
queue_command=(squeue)
if [[ -n "$array_cluster" ]]; then
    queue_command+=("--clusters=${array_cluster}")
fi
queue_command+=("--jobs=${array_job_id},${plot_job_id}")
print_command "${queue_command[@]}"
