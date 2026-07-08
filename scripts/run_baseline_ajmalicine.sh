#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    "Usage: bash scripts/run_baseline_ajmalicine.sh [--help]" \
    "" \
    "Run the original SubNetX first-stage ajmalicine baseline from the basic tutorial." \
    "" \
    "Default tutorial:" \
    "  1_subnetwork_extraction/tutorials/1_basic/ajmalicine" \
    "" \
    "The expanded tutorial is not used by this script. This script copies the basic" \
    "tutorial into 1_subnetwork_extraction/projects/ajmalicine, refuses to overwrite" \
    "that project if it already exists, runs the original Main.py from" \
    "1_subnetwork_extraction/code, and writes logs plus environment metadata under:" \
    "  runs/baseline-ajmalicine/<timestamp>/" \
    "" \
    "--help prints this message and exits without creating projects, installing" \
    "packages, or running Main.py."
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "$#" -gt 0 ]]; then
  usage >&2
  die "Unknown argument: $1"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

timestamp="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$REPO_ROOT/runs/baseline-ajmalicine/$timestamp"
mkdir -p "$RUN_DIR"

echo "Run directory: $RUN_DIR"
python "$REPO_ROOT/scripts/check_baseline_inputs.py" --repo-root "$REPO_ROOT"

# The baseline run intentionally uses the smaller/basic ajmalicine tutorial.
# The expanded ajmalicine tutorial exists, but is not selected by default.
TUTORIAL_DIR="$REPO_ROOT/1_subnetwork_extraction/tutorials/1_basic/ajmalicine"
PROJECTS_DIR="$REPO_ROOT/1_subnetwork_extraction/projects"
PROJECT_DIR="$PROJECTS_DIR/ajmalicine"

[[ -d "$TUTORIAL_DIR" ]] || die "Ajmalicine tutorial directory not found: $TUTORIAL_DIR"
if [[ -e "$PROJECT_DIR" ]]; then
  die "Project directory already exists: $PROJECT_DIR. Back it up or choose a new run directory before rerunning."
fi

mkdir -p "$PROJECTS_DIR"
cp -R "$TUTORIAL_DIR" "$PROJECT_DIR"

{
  echo "timestamp=$timestamp"
  echo "repo_root=$REPO_ROOT"
  echo "git_commit=$(git rev-parse HEAD)"
  echo "git_branch=$(git branch --show-current)"
  echo "python=$(python --version 2>&1)"
  python - <<'PY'
import importlib

for module_name in ("pandas", "networkx", "rdkit"):
    try:
        module = importlib.import_module(module_name)
        if module_name == "rdkit":
            from rdkit import rdBase

            version = rdBase.rdkitVersion
        else:
            version = getattr(module, "__version__", "unknown")
        print(f"{module_name}={version}")
    except Exception as exc:  # noqa: BLE001 - environment metadata should not hide missing deps
        print(f"{module_name}=not available ({exc})")
PY
  if command -v conda >/dev/null 2>&1; then
    echo "conda=$(conda --version)"
    if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
      echo "conda_env=$CONDA_DEFAULT_ENV"
    else
      echo "conda_env=not active"
    fi
  else
    echo "conda=not found"
    echo "conda_env=not active"
  fi
  if command -v obabel >/dev/null 2>&1; then
    echo "openbabel=$(obabel -V 2>&1)"
  else
    echo "openbabel=not found"
  fi
} >"$RUN_DIR/environment.txt"

echo "Starting original SubNetX Main.py. Log: $RUN_DIR/run.log"
echo "Results and logs will be saved under: $RUN_DIR"
(
  cd "$REPO_ROOT/1_subnetwork_extraction/code"
  python Main.py ajmalicine
) >"$RUN_DIR/run.log" 2>&1

echo "Baseline ajmalicine run completed. Results and logs are in: $RUN_DIR"
