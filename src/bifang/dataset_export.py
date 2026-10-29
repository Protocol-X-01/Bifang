from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


def encoded_line(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def export_dataset(rows: Iterable[dict], destination: Path, *, source: str,
                   revision: str, allowed_licenses: set[str], max_bytes: int = 900_000_000,
                   max_rows: int = 5000) -> dict:
    if not 0 < max_bytes < 1_000_000_000 or max_rows < 1:
        raise ValueError("Use a positive byte cap strictly below 1 GB and a positive row limit")
    if not source or not revision or not allowed_licenses:
        raise ValueError("Source, revision and explicitly reviewed license identifiers are required")
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    seen = set()
    counts = Counter()
    digest = hashlib.sha256()
    size = 0
    with (destination / "coding.jsonl").open("xb") as output, (destination / "provenance.jsonl").open("xb") as provenance:
        for row in rows:
            counts["examined"] += 1
            if not isinstance(row, dict):
                counts["invalid"] += 1
                continue
            question, response = row.get("input"), row.get("output")
            if (not isinstance(question, str) or not question.strip() or question.strip() == "-"
                    or not isinstance(response, str) or not response.strip()):
                counts["invalid"] += 1
                continue
            if row.get("license") not in allowed_licenses:
                counts["license_excluded"] += 1
                continue
            question_hash = hashlib.sha256(" ".join(question.split()).encode("utf-8")).hexdigest()
            if question_hash in seen:
                counts["duplicate_question"] += 1
                continue
            record = {"messages": [{"role": "user", "content": question},
                                   {"role": "assistant", "content": response}]}
            line = encoded_line(record)
            if len(line) > max_bytes:
                counts["oversize_record"] += 1
                continue
            if size + len(line) > max_bytes:
                counts["byte_cap_reached"] += 1
                break
            output.write(line)
            digest.update(line)
            size += len(line)
            seen.add(question_hash)
            counts["exported"] += 1
            provenance.write(encoded_line({"line": counts["exported"], "source": source,
                "revision": revision, "id": row.get("id"), "question_sha256": question_hash,
                "license": row["license"], "upstream_dataset": row.get("dataset"),
                "upstream_split": row.get("split"), "platform": row.get("source"),
                "difficulty": row.get("difficulty"), "execution_verified_locally": False}))
            if counts["exported"] == max_rows:
                break
    if not counts["exported"]:
        raise ValueError("No eligible complete examples; output is not a usable dataset")
    actual_count = 0
    with (destination / "coding.jsonl").open("r", encoding="utf-8") as output:
        for line in output:
            record = json.loads(line)
            if [message["role"] for message in record["messages"]] != ["user", "assistant"]:
                raise ValueError("Export verification failed")
            actual_count += 1
    if actual_count != counts["exported"] or (destination / "coding.jsonl").stat().st_size != size:
        raise ValueError("Export size/count verification failed")
    report = {"source": source, "revision": revision, "counts": dict(counts),
              "bytes": size, "max_bytes": max_bytes, "sha256": digest.hexdigest(),
              "schema": "messages: user input, assistant output; original text preserved",
              "license_allowlist": sorted(allowed_licenses),
              "limitations": ["Not independently execution-verified or secret-scanned.",
                  "Not an independent evaluation set or repository-agent trajectory dataset.",
                  "Question-text deduplication does not establish problem-family separation.",
                  "No upload, training, benchmark superiority or target-model compatibility established."]}
    (destination / "manifest.json").write_bytes(encoded_line(report))
    return report
