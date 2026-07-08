#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    "Usage: bash scripts/bootstrap_autodl.sh [--help]" \
    "" \
    "Prepare the SubNetX first-stage baseline environment on AutoDL/Linux." \
    "" \
    "This script:" \
    "  - locates the repository root from the script location," \
    "  - checks git, git-lfs, and conda or mamba," \
    "  - runs git lfs pull," \
    "  - verifies ARBRE CSV inputs are real files, not Git LFS pointers," \
    "  - creates or updates the conda environment from environment-baseline.yml," \
    "  - prints Python, pandas, RDKit, NetworkX, and Open Babel versions." \
    "" \
    "--help prints this message and exits without installing, downloading, or running" \
    "any baseline task."
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

is_lfs_pointer() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local first_line
  IFS= read -r first_line <"$file" || true
  [[ "$first_line" == "version https://git-lfs.github.com/spec/v1" ]]
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

echo "Repository root: $REPO_ROOT"

require_cmd git
git lfs version >/dev/null 2>&1 || die "git-lfs is not installed or git lfs is unavailable"

if command -v mamba >/dev/null 2>&1; then
  CONDA_TOOL="mamba"
elif command -v conda >/dev/null 2>&1; then
  CONDA_TOOL="conda"
else
  die "Neither mamba nor conda was found"
fi

echo "Using environment tool: $CONDA_TOOL"
echo "Running git lfs pull to retrieve large input data..."
git lfs pull || die "git lfs pull failed; ARBRE data may still be LFS pointers"

ARBRE_DIR="$REPO_ROOT/1_subnetwork_extraction/data/ARBRE"
required_arbre=(
  "compounds.csv"
  "network.csv"
  "reaction_balance.csv"
  "reactions.csv"
  "reactions_pairs.csv"
)

for name in "${required_arbre[@]}"; do
  path="$ARBRE_DIR/$name"
  [[ -f "$path" ]] || die "Missing ARBRE file: $path"
  if is_lfs_pointer "$path"; then
    die "ARBRE file is still a Git LFS pointer: $path"
  fi
  [[ -s "$path" ]] || die "ARBRE file is empty: $path"
done

echo "Creating or updating conda environment from environment-baseline.yml..."
"$CONDA_TOOL" env update -f "$REPO_ROOT/environment-baseline.yml" --prune

echo "Baseline environment versions:"
"$CONDA_TOOL" run -n subnetx-baseline python - <<'PY'
import shutil
import subprocess
import sys

import networkx
import pandas
from rdkit import rdBase

print(f"Python: {sys.version.split()[0]}")
print(f"pandas: {pandas.__version__}")
print(f"RDKit: {rdBase.rdkitVersion}")
print(f"NetworkX: {networkx.__version__}")

obabel = shutil.which("obabel")
if obabel:
    result = subprocess.run(["obabel", "-V"], text=True, capture_output=True, check=False)
    output = (result.stdout or result.stderr).strip()
    print(f"Open Babel: {output}")
else:
    print("Open Babel: not found on PATH")
PY

echo "AutoDL baseline bootstrap completed."
