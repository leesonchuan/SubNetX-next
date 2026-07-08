#!/usr/bin/env python3
"""Preflight checks for the SubNetX ajmalicine baseline inputs.

This script only validates input availability and basic file shape. It does not
run the network extraction workflow.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


LFS_POINTER_PREFIX = "version https://git-lfs.github.com/spec/v1"
DEFAULT_TUTORIAL = Path("1_subnetwork_extraction/tutorials/1_basic/ajmalicine")
REQUIRED_ARBRE_FILES = (
    "compounds.csv",
    "network.csv",
    "reaction_balance.csv",
    "reactions.csv",
    "reactions_pairs.csv",
)
DEFAULT_EXCLUDELISTS = (
    "compounds.txt",
    "toxic_compounds.txt",
    "mammal_cofactors.txt",
    "reactions.txt",
)


@dataclass(frozen=True)
class CheckResult:
    status: str
    item: str
    detail: str


def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository root from this script or a supplied path."""
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (
            (candidate / "1_subnetwork_extraction").is_dir()
            and (candidate / "AGENTS.md").is_file()
        ):
            return candidate

    raise FileNotFoundError("Could not locate repository root from script path")


def parse_parameters(path: Path) -> dict[str, str]:
    """Parse SubNetX key|value parameter files."""
    params: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "|" not in stripped:
                raise ValueError(f"Line {line_number} is not key|value: {stripped}")
            key, value = stripped.split("|", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(f"Line {line_number} has an empty key")
            params[key] = value
    return params


def is_lfs_pointer(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.readline().strip() == LFS_POINTER_PREFIX


def csv_header_status(path: Path) -> tuple[bool, str]:
    """Validate that a CSV has real, non-empty header fields."""
    if not path.exists() or not path.is_file():
        return False, "missing"
    if path.stat().st_size == 0:
        return False, "CSV is empty"
    with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return False, "CSV has no header"
    normalized = [column.strip() for column in header]
    if not normalized or not any(normalized):
        return False, "CSV header is empty"
    return True, "CSV header: " + ", ".join(normalized[:8])


def csv_has_cuid(path: Path, target: str) -> tuple[bool, str]:
    """Return whether target is present in cUID and a short diagnostic."""
    header_ok, detail = csv_header_status(path)
    if not header_ok:
        return False, detail
    with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
        reader = csv.DictReader(handle)
        if "cUID" not in reader.fieldnames:
            return False, "CSV header does not contain cUID"
        target_text = str(target).strip()
        for row in reader:
            if str(row.get("cUID", "")).strip() == target_text:
                return True, f"main_target {target} found in cUID"
    return False, f"main_target {target} not found in cUID"


def add(results: list[CheckResult], status: str, item: str, detail: str) -> None:
    results.append(CheckResult(status=status, item=item, detail=detail))


def check_default_project_inputs(repo_root: Path, results: list[CheckResult]) -> None:
    defaults = repo_root / "1_subnetwork_extraction" / "defaults"
    compound_parameters = defaults / "compound_parameters.csv"
    if compound_parameters.is_file():
        add(results, "PASS", "default compound_parameters.csv", str(compound_parameters))
    else:
        add(results, "FAIL", "default compound_parameters.csv", "missing")

    excludelists = defaults / "excludelists"
    for name in DEFAULT_EXCLUDELISTS:
        path = excludelists / name
        if path.is_file():
            add(results, "PASS", f"default excludelist {name}", str(path))
        else:
            add(results, "FAIL", f"default excludelist {name}", "missing")


def run_checks(
    repo_root: Path | None = None,
    tutorial_rel: Path = DEFAULT_TUTORIAL,
) -> tuple[list[CheckResult], bool]:
    """Run all preflight checks and return results plus overall success."""
    results: list[CheckResult] = []
    root = (repo_root or find_repo_root()).resolve()

    expected_markers = [
        root / "1_subnetwork_extraction" / "code" / "Main.py",
        root / "1_subnetwork_extraction" / "data",
        root / "1_subnetwork_extraction" / "defaults",
    ]
    if all(path.exists() for path in expected_markers):
        add(results, "PASS", "repository root", str(root))
    else:
        missing = [str(path) for path in expected_markers if not path.exists()]
        add(results, "FAIL", "repository root", "missing markers: " + ", ".join(missing))
        return results, False

    tutorial_dir = root / tutorial_rel
    if tutorial_dir.is_dir():
        add(results, "PASS", "ajmalicine tutorial directory", str(tutorial_dir))
    else:
        add(results, "FAIL", "ajmalicine tutorial directory", str(tutorial_dir))

    params: dict[str, str] = {}
    parameters_path = tutorial_dir / "parameters.txt"
    if parameters_path.is_file():
        try:
            params = parse_parameters(parameters_path)
            add(results, "PASS", "parameters.txt parse", str(parameters_path))
        except Exception as exc:  # noqa: BLE001 - CLI diagnostic should surface parse issue
            add(results, "FAIL", "parameters.txt parse", str(exc))
    else:
        add(results, "FAIL", "parameters.txt", f"missing: {parameters_path}")

    main_target = params.get("main_target")
    if main_target:
        add(results, "PASS", "main_target", main_target)
    else:
        add(results, "FAIL", "main_target", "missing in parameters.txt")

    reaction_network = params.get("reaction_network")
    if reaction_network == "ARBRE":
        add(results, "PASS", "reaction_network", "ARBRE")
    else:
        add(results, "FAIL", "reaction_network", f"expected ARBRE, got {reaction_network!r}")

    check_default_project_inputs(root, results)

    organism = params.get("model_organism")
    if organism:
        metabolites = (
            root
            / "1_subnetwork_extraction"
            / "data"
            / "organisms_metabolites_annotated"
            / f"{organism}.tsv"
        )
        if metabolites.is_file():
            add(results, "PASS", "organism metabolites", str(metabolites))
        else:
            add(results, "FAIL", "organism metabolites", f"missing: {metabolites}")
    else:
        add(results, "FAIL", "model_organism", "missing in parameters.txt")

    arbre_dir = root / "1_subnetwork_extraction" / "data" / "ARBRE"
    if arbre_dir.is_dir():
        add(results, "PASS", "ARBRE directory", str(arbre_dir))
    else:
        add(results, "FAIL", "ARBRE directory", f"missing: {arbre_dir}")

    for name in REQUIRED_ARBRE_FILES:
        path = arbre_dir / name
        if not path.is_file():
            add(results, "FAIL", f"ARBRE {name}", "missing")
            continue
        if is_lfs_pointer(path):
            add(results, "FAIL", f"ARBRE {name}", "Git LFS pointer, real content missing")
            continue
        header_ok, detail = csv_header_status(path)
        if not header_ok:
            add(results, "FAIL", f"ARBRE {name}", detail)
            continue
        add(results, "PASS", f"ARBRE {name}", f"{path.stat().st_size} bytes; {detail}")

    compounds = arbre_dir / "compounds.csv"
    if main_target and compounds.is_file() and not is_lfs_pointer(compounds):
        found, detail = csv_has_cuid(compounds, main_target)
        add(results, "PASS" if found else "FAIL", "main_target in compounds.csv", detail)
    elif main_target:
        add(
            results,
            "FAIL",
            "main_target in compounds.csv",
            "cannot check because compounds.csv is missing or an LFS pointer",
        )

    ok = not any(result.status == "FAIL" for result in results)
    return results, ok


def print_results(results: Iterable[CheckResult]) -> None:
    for result in results:
        print(f"{result.status}: {result.item} - {result.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to auto-detection from script location.",
    )
    parser.add_argument(
        "--tutorial",
        type=Path,
        default=DEFAULT_TUTORIAL,
        help="Ajmalicine tutorial path relative to the repository root.",
    )
    args = parser.parse_args(argv)

    try:
        results, ok = run_checks(args.repo_root, args.tutorial)
    except Exception as exc:  # noqa: BLE001 - top-level CLI should produce clear failure
        print(f"FAIL: preflight - {exc}", file=sys.stderr)
        return 1

    print_results(results)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
