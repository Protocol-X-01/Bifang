from __future__ import annotations

import ast
import hashlib
import json
import re
import tempfile
from collections import Counter
from pathlib import Path

from .dataset_export import encoded_line, export_dataset


SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
    r"\bhf_[A-Za-z0-9]{30,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b"
)


def question_group(question: str) -> str:
    normalized = re.sub(r"\d+(?:\.\d+)?", "<number>", " ".join(question.casefold().split()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def solution_matches_output(solution: str, output: str) -> bool:
    target = ast.dump(ast.parse(solution))
    final = output.rsplit("</think>", 1)[-1]
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", final, re.DOTALL)
    if not blocks:
        blocks = [final]
    for block in blocks:
        try:
            if ast.dump(ast.parse(block.strip())) == target:
                return True
        except (SyntaxError, ValueError, RecursionError):
            continue
    return False


def curate_dataset(rows, destination: Path, *, source: str, revision: str,
                   max_bytes: int = 900_000_000, validation_percent: int = 5) -> dict:
    if not 1 <= validation_percent <= 30:
        raise ValueError("Use a validation percentage from 1 to 30")
    if not 0 < max_bytes < 1_000_000_000:
        raise ValueError("Byte cap must be strictly below 1 GB")
    destination.mkdir(mode=0o700, exist_ok=False)
    counts = Counter()
    sources = Counter()
    difficulties = Counter()
    seen_questions, seen_ids, seen_solutions = set(), set(), set()
    with tempfile.TemporaryDirectory(prefix="bifang-curation-") as temporary:
        paths = {name: Path(temporary) / f"{name}.jsonl" for name in ("train", "validation")}
        with paths["train"].open("wb") as training, paths["validation"].open("wb") as validation:
            for row in rows:
                counts["examined"] += 1
                if not isinstance(row, dict):
                    counts["invalid"] += 1
                    continue
                question, output, solution = (row.get(key) for key in ("input", "output", "solution"))
                if any(not isinstance(value, str) or not value.strip() for value in (question, output, solution)) or question.strip() == "-":
                    counts["missing_text"] += 1
                    continue
                if row.get("license") != "cc-by-4.0":
                    counts["license_excluded"] += 1
                    continue
                if row.get("split") != "train":
                    counts["upstream_nontraining"] += 1
                    continue
                if len(question) + len(output) + len(solution) > 300_000:
                    counts["oversize_text"] += 1
                    continue
                if SECRET_PATTERN.search(question + "\n" + output + "\n" + solution):
                    counts["credential_pattern"] += 1
                    continue
                try:
                    matching = solution_matches_output(solution, output)
                except (SyntaxError, ValueError, RecursionError):
                    counts["solution_syntax"] += 1
                    continue
                if not matching:
                    counts["final_code_mismatch"] += 1
                    continue
                question_hash = hashlib.sha256(" ".join(question.split()).encode()).hexdigest()
                identity = row.get("id")
                solution_hash = hashlib.sha256(ast.dump(ast.parse(solution)).encode()).hexdigest()
                if (question_hash in seen_questions or (identity and identity in seen_ids)
                        or solution_hash in seen_solutions):
                    counts["duplicate_question_id_or_solution"] += 1
                    continue
                seen_questions.add(question_hash)
                if identity:
                    seen_ids.add(identity)
                seen_solutions.add(solution_hash)
                group = question_group(question)
                subset = "validation" if int(group[:8], 16) % 100 < validation_percent else "train"
                (validation if subset == "validation" else training).write(encoded_line(row))
                counts[f"accepted_{subset}"] += 1
                sources[str(row.get("source", "unknown"))] += 1
                difficulties[str(row.get("difficulty", "unknown"))] += 1
        reports = {}
        for subset, path in paths.items():
            with path.open(encoding="utf-8") as source_rows:
                reports[subset] = export_dataset((json.loads(line) for line in source_rows),
                    destination / subset, source=source, revision=revision,
                    allowed_licenses={"cc-by-4.0"}, max_bytes=max_bytes, max_rows=1_000_000)
    groups, identities = {}, {}
    for subset in ("train", "validation"):
        groups[subset], identities[subset] = set(), set()
        with (destination / subset / "coding.jsonl").open(encoding="utf-8") as contents, (destination / subset / "provenance.jsonl").open(encoding="utf-8") as provenance:
            for line, origin in zip(contents, provenance, strict=True):
                groups[subset].add(question_group(json.loads(line)["messages"][0]["content"]))
                identity = json.loads(origin)["id"]
                if identity:
                    identities[subset].add(identity)
    if groups["train"] & groups["validation"] or identities["train"] & identities["validation"]:
        raise ValueError("Exported training and validation overlap")
    report = {"counts": dict(counts), "accepted_platforms": dict(sources),
              "accepted_difficulties": dict(difficulties), "exports": reports,
              "exported_split_audit": {"shared_question_groups": 0, "shared_ids": 0},
              "checks": ["Upstream train rows only; explicit cc-by-4.0 labels.",
                  "Python 3 AST syntax; solution matches a final response code block.",
                  "High-confidence credential-pattern exclusions, not a comprehensive secret audit.",
                  "Global exact question, ID and solution-AST deduplication before splitting.",
                  "Deterministic numeric-normalized question-group train/validation split."],
              "limitations": ["Syntax and response consistency are not functional correctness tests.",
                  "No downloaded code was executed; no model was trained or data uploaded.",
                  "Problem-family grouping is heuristic; final independent benchmark remains separate.",
                  "License labels do not replace review of underlying-source rights.",
                  "Accepted distributions precede byte-cap exclusions; export manifests are authoritative."]}
    (destination / "curation.json").write_bytes(encoded_line(report))
    return report
