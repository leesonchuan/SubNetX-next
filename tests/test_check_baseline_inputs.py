from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_baseline_inputs.py"
SPEC = importlib.util.spec_from_file_location("check_baseline_inputs", SCRIPT_PATH)
check_baseline_inputs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_baseline_inputs
SPEC.loader.exec_module(check_baseline_inputs)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path, *, target_in_compounds: bool = True, pointer: bool = False) -> Path:
    root = tmp_path / "repo"
    write_text(root / "AGENTS.md", "# test\n")
    write_text(root / "1_subnetwork_extraction/code/Main.py", "# test\n")
    write_text(root / "1_subnetwork_extraction/defaults/compound_parameters.csv", "name,value\n")
    for name in check_baseline_inputs.DEFAULT_EXCLUDELISTS:
        write_text(root / "1_subnetwork_extraction/defaults/excludelists" / name, "\n")
    write_text(
        root / "1_subnetwork_extraction/tutorials/1_basic/ajmalicine/parameters.txt",
        "\n".join(
            [
                "model_organism|ecoli",
                "run_expansion|1",
                "lowest_atom_conservation_threshold|0.34",
                "distance_transformation|dist_exp",
                "boundaries_alternatives_num|1",
                "num_shortest_pathways|15",
                "num_pathways_to_model|1",
                "numSimPrecursorsLimit|1",
                "reaction_network|ARBRE",
                "main_target|1467941844",
                "main_precursor|all",
                "filter_precursor_structure|0",
            ]
        )
        + "\n",
    )
    write_text(
        root / "1_subnetwork_extraction/data/organisms_metabolites_annotated/ecoli.tsv",
        "metaboliteLCSBID\n1467941844\n",
    )

    arbre = root / "1_subnetwork_extraction/data/ARBRE"
    pointer_text = (
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        "size 100\n"
    )
    for name in check_baseline_inputs.REQUIRED_ARBRE_FILES:
        if pointer:
            write_text(arbre / name, pointer_text)
        elif name == "compounds.csv":
            cuid = "1467941844" if target_in_compounds else "not_the_target"
            write_text(arbre / name, f"cUID,SMILES\n{cuid},CCO\n")
        else:
            write_text(arbre / name, "header\nvalue\n")
    return root


def statuses(results):
    return {(result.item, result.status) for result in results}


def test_parameters_parse_success(tmp_path: Path) -> None:
    params = tmp_path / "parameters.txt"
    write_text(params, "# comment\nmain_target|1467941844\nreaction_network|ARBRE\n")

    parsed = check_baseline_inputs.parse_parameters(params)

    assert parsed["main_target"] == "1467941844"
    assert parsed["reaction_network"] == "ARBRE"


def test_missing_parameters_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    (root / "1_subnetwork_extraction/tutorials/1_basic/ajmalicine/parameters.txt").unlink()

    results, ok = check_baseline_inputs.run_checks(root)

    assert not ok
    assert ("parameters.txt", "FAIL") in statuses(results)


def test_lfs_pointer_file_is_detected(tmp_path: Path) -> None:
    root = make_repo(tmp_path, pointer=True)

    results, ok = check_baseline_inputs.run_checks(root)

    assert not ok
    assert ("ARBRE compounds.csv", "FAIL") in statuses(results)
    assert any("Git LFS pointer" in result.detail for result in results)


def test_empty_csv_file_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    (root / "1_subnetwork_extraction/data/ARBRE/network.csv").write_text("", encoding="utf-8")

    results, ok = check_baseline_inputs.run_checks(root)

    assert not ok
    assert ("ARBRE network.csv", "FAIL") in statuses(results)
    assert any("CSV is empty" in result.detail for result in results)


def test_main_target_missing_from_compounds_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path, target_in_compounds=False)

    results, ok = check_baseline_inputs.run_checks(root)

    assert not ok
    assert ("main_target in compounds.csv", "FAIL") in statuses(results)


def test_all_required_inputs_pass(tmp_path: Path) -> None:
    root = make_repo(tmp_path)

    results, ok = check_baseline_inputs.run_checks(root)

    assert ok
    assert not [result for result in results if result.status == "FAIL"]
