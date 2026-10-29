import hashlib
import json

import pytest

from bifang.dataset_export import encoded_line, export_dataset


def sample(**changes):
    return {"input": "Fix the function for café", "output": "print('café')", "license": "cc-by-4.0",
            "id": "one", **changes}


def export(rows, destination, **options):
    return export_dataset(rows, destination, source="first-party-test-fixture", revision="test-v1",
                          allowed_licenses={"cc-by-4.0"}, **options)


def test_export_preserves_text_and_measures_encoded_bytes(tmp_path):
    destination = tmp_path / "data"
    row = sample()
    report = export([row], destination)
    contents = (destination / "coding.jsonl").read_bytes()
    assert len(contents) == report["bytes"]
    assert hashlib.sha256(contents).hexdigest() == report["sha256"]
    assert json.loads(contents)["messages"][1]["content"] == row["output"]
    assert report["counts"]["exported"] == 1
    assert json.loads((destination / "provenance.jsonl").read_text())["execution_verified_locally"] is False


def test_size_cap_never_truncates_a_record(tmp_path):
    row = sample()
    record = {"messages": [{"role": "user", "content": row["input"]},
                           {"role": "assistant", "content": row["output"]}]}
    limit = len(encoded_line(record))
    report = export([row, sample(input="Different question")], tmp_path / "data", max_bytes=limit)
    assert report["bytes"] == limit
    assert report["counts"]["exported"] == 1
    assert report["counts"]["byte_cap_reached"] == 1


def test_filters_unknown_license_invalid_rows_and_duplicate_questions(tmp_path):
    report = export([None, sample(input="-"), sample(license="unknown"), sample(),
                     sample(input="Fix  the function\nfor café"), sample(input="A separate task")], tmp_path / "data")
    assert report["counts"] == {"examined": 6, "invalid": 2, "license_excluded": 1,
                                "exported": 2, "duplicate_question": 1}


@pytest.mark.parametrize("cap", [0, -1, 1_000_000_000, 1_073_741_824])
def test_rejects_invalid_or_one_gb_caps(tmp_path, cap):
    with pytest.raises(ValueError):
        export([sample()], tmp_path / "data", max_bytes=cap)
    assert not (tmp_path / "data").exists()


def test_never_overwrites_an_existing_export(tmp_path):
    destination = tmp_path / "data"
    export([sample()], destination)
    before = (destination / "coding.jsonl").read_bytes()
    with pytest.raises(FileExistsError):
        export([sample(input="replacement")], destination)
    assert (destination / "coding.jsonl").read_bytes() == before


def test_rejects_empty_and_oversize_exports(tmp_path):
    with pytest.raises(ValueError, match="No eligible"):
        export([sample()], tmp_path / "empty", max_bytes=1)
    assert not (tmp_path / "empty" / "manifest.json").exists()
