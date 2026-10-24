import json

import pytest

from bifang.dataset_curation import curate_dataset, question_group, solution_matches_output


def examples():
    return [{"id": str(index), "input": f"Compute task {chr(65 + index)} for 12 items.",
             "output": f"<think>Reasoning</think>\n```python\nprint({index})\n```",
             "solution": f"print({index})", "license": "cc-by-4.0", "split": "train"}
            for index in range(26)]


def test_final_code_consistency_does_not_accept_code_only_in_reasoning():
    assert solution_matches_output("print(1)", "```python\nprint(1)\n```")
    assert not solution_matches_output("print(1)", "<think>```python\nprint(1)\n```</think>Incorrect final answer")
    assert not solution_matches_output("print(1)", "```python\nprint(2)\n```")


def test_numeric_variants_share_a_group():
    assert question_group("Sum 12 items") == question_group("sum  24 ITEMS")


def test_curation_filters_before_grouped_split(tmp_path):
    rows = examples()
    rows += [dict(rows[0]), {**rows[1], "split": "test"},
             {**rows[2], "solution": "def broken("},
             {**rows[3], "output": "```python\nprint(999)\n```"},
             {**rows[4], "license": "unknown"},
             {**rows[5], "input": "-----BEGIN PRIVATE KEY-----"}]
    report = curate_dataset(rows, tmp_path / "data", source="synthetic tests", revision="v1", validation_percent=30)
    counts = report["counts"]
    assert counts["accepted_train"] + counts["accepted_validation"] == 26
    assert counts["duplicate_question_id_or_solution"] == 1
    for exclusion in ("upstream_nontraining", "solution_syntax", "final_code_mismatch", "license_excluded", "credential_pattern"):
        assert counts[exclusion] == 1
    subsets = {}
    for subset in ("train", "validation"):
        path = tmp_path / "data" / subset / "provenance.jsonl"
        subsets[subset] = {json.loads(line)["id"] for line in path.read_text().splitlines()}
    assert subsets["train"].isdisjoint(subsets["validation"])
    assert report["exported_split_audit"] == {"shared_question_groups": 0, "shared_ids": 0}


@pytest.mark.parametrize("percentage", [0, 31])
def test_invalid_split_is_rejected_before_creating_output(tmp_path, percentage):
    with pytest.raises(ValueError):
        curate_dataset([], tmp_path / "data", source="test", revision="v1", validation_percent=percentage)
    assert not (tmp_path / "data").exists()
