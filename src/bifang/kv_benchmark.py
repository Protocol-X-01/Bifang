"""Controlled serving experiments, independent of the desktop Python/GPU runtime."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import statistics
import time
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt


class Deployment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model: str = Field(min_length=1)
    checkpoint_revision: str = Field(min_length=1)
    image_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    tensorrt_llm_version: str = Field(min_length=1)
    gpu_model: str = Field(min_length=1)
    gpu_count: StrictInt = Field(ge=1)
    driver_version: str = Field(min_length=1)
    server_options: dict

    def validate_options(self):
        options = self.server_options
        cache = options.get("kv_cache_config", {})
        if set(options) - {"backend", "dtype", "max_seq_len", "tensor_parallel_size",
                           "pipeline_parallel_size", "max_batch_size", "max_num_tokens",
                           "kv_cache_config"} or set(cache) - {"dtype", "max_tokens",
                                                              "enable_block_reuse"}:
            raise ValueError("Use only the controlled protocol's serving options")
        parallelism = [options.get("tensor_parallel_size", 1),
                       options.get("pipeline_parallel_size", 1)]
        if any(type(value) is not int or value <= 0 for value in parallelism):
            raise ValueError("Invalid parallelism")
        if math.prod(parallelism) != self.gpu_count:
            raise ValueError("GPU count must match TP times PP for this single-replica experiment")
        if cache.get("dtype") not in ("bfloat16", "float16", "fp8"):
            raise ValueError("An explicit BF16/FP16/FP8 active KV dtype is required")
        if cache.get("enable_block_reuse") is not False:
            raise ValueError("Disable prefix reuse for the first controlled experiment")
        if not isinstance(cache.get("max_tokens"), int) or cache["max_tokens"] <= 0:
            raise ValueError("Pin an identical positive KV token capacity")
        if options.get("backend") != "pytorch":
            raise ValueError("This protocol targets the TensorRT-LLM PyTorch backend")
        if options.get("dtype") not in ("bfloat16", "float16"):
            raise ValueError("Pin the model compute dtype independently of the KV dtype")
        if not isinstance(options.get("max_seq_len"), int) or options["max_seq_len"] <= 0:
            raise ValueError("Pin a positive maximum sequence length")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def recall_cases(rows=(256, 2048)) -> list[dict]:
    if not rows or len(set(rows)) != len(rows):
        raise ValueError("Use a nonempty set of distinct context sizes")
    cases = []
    for count in rows:
        if not 8 <= count <= 32768:
            raise ValueError("Rows must be between 8 and 32768; rows are not tokens")
        for position in (0.05, 0.5, 0.95):
            target = int(count * position)
            lines = [f"module_{index:05d}: receipt limit = {index % 97}" for index in range(count)]
            answer = hashlib.sha256(f"bifang:{count}:{target}".encode()).hexdigest()[:16]
            lines[target] = f"receipt_parser regression verification code = {answer}"
            prompt = ("Read this synthetic repository index. Return ONLY the receipt_parser "
                      "regression verification code, without explanation.\n\n"
                      + "\n".join(lines) + "\n\nWhat is that exact verification code?")
            cases.append({"id": f"rows-{count}-position-{position}", "prompt": prompt,
                          "answer": answer, "rows": count, "position": position})
    return cases


def checked_url(base_url: str, allow_remote: bool) -> str:
    parsed = urlsplit(base_url)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") != "/v1"):
        raise ValueError("Use an explicit /v1 endpoint without credentials or query parameters")
    if not local and (not allow_remote or parsed.scheme != "https"):
        raise ValueError("Remote endpoints require HTTPS and --allow-remote")
    return base_url.rstrip("/")


async def sample(client: httpx.AsyncClient, model: str, case: dict, clock=time.perf_counter):
    payload = {"model": model, "messages": [{"role": "user", "content": case["prompt"]}],
               "temperature": 0, "max_tokens": 128, "stream": True,
               "stream_options": {"include_usage": True}}
    started = clock()
    content_times, content = [], []
    usage, finish, done = None, None, False
    async with client.stream("POST", "chat/completions", json=payload) as response:
        if response.status_code != 200:
            raise ValueError(f"Serving request failed with HTTP {response.status_code}")
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise ValueError("Serving response is not an SSE stream")
        event_lines = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                event_lines.append(line[5:].lstrip())
            elif not line and event_lines:
                data = "\n".join(event_lines)
                event_lines.clear()
                if data == "[DONE]":
                    done = True
                    break
                event = json.loads(data)
                if "error" in event:
                    raise ValueError("Serving stream reported an error")
                if event.get("usage"):
                    usage = event["usage"]
                for choice in event.get("choices", []):
                    if choice.get("index", 0) != 0:
                        raise ValueError("Only single-choice streams are supported")
                    text = choice.get("delta", {}).get("content")
                    if text:
                        if not isinstance(text, str):
                            raise ValueError("Non-text stream content")
                        content.append(text)
                        content_times.append(clock())
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
    elapsed = clock() - started
    if not done or not content or not usage or elapsed <= 0:
        raise ValueError("Incomplete stream or missing server token accounting")
    for key in ("prompt_tokens", "completion_tokens"):
        if type(usage.get(key)) is not int or usage[key] <= 0:
            raise ValueError("Positive server-reported token counts are required")
    intervals = [later - earlier for earlier, later in pairwise(content_times)]
    return {"case_id": case["id"], "prompt_sha256": digest(case["prompt"]),
            "rows": case["rows"], "position": case["position"],
            "exact_recall": finish == "stop" and "".join(content).strip() == case["answer"],
            "finish_reason": finish, "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"], "elapsed_s": elapsed,
            "time_to_first_content_s": content_times[0] - started,
            "content_chunk_intervals_s": intervals,
            "output_tokens_per_end_to_end_second": usage["completion_tokens"] / elapsed}


def summary(samples: list[dict]) -> dict:
    def distribution(values):
        ordered = sorted(values)
        return {"median": statistics.median(ordered),
                "p95": ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]}

    return {"requests": len(samples),
            "exact_recall_rate": sum(item["exact_recall"] for item in samples) / len(samples),
            **{key: distribution([item[key] for item in samples]) for key in
               ("elapsed_s", "time_to_first_content_s", "output_tokens_per_end_to_end_second")}}


def validated_samples(report: dict) -> dict:
    settings = report["settings"]
    repetitions = settings["repetitions"]
    if type(repetitions) is not int or not 3 <= repetitions <= 100:
        raise ValueError("Invalid repetition count")
    if settings != {"temperature": 0, "max_tokens": 128, "concurrency": 1,
                    "repetitions": repetitions, "warmups": 1, "rows": settings["rows"]}:
        raise ValueError("Unrecognized sampling settings")
    cases = recall_cases(settings["rows"])
    if report.get("protocol") != "bifang-recall-v1" or report["suite_sha256"] != digest(cases):
        raise ValueError("Unknown or modified benchmark suite")
    expected = {(repeat, case["id"]): case for repeat in range(repetitions) for case in cases}
    samples = {}
    for item in report["samples"]:
        pair = (item["repeat"], item["case_id"])
        if pair not in expected or pair in samples:
            raise ValueError("Unexpected or duplicate sample")
        case = expected[pair]
        if (item["prompt_sha256"] != digest(case["prompt"]) or item["rows"] != case["rows"]
                or item["position"] != case["position"] or type(item["exact_recall"]) is not bool):
            raise ValueError("Invalid sample identity or score")
        for key in ("elapsed_s", "time_to_first_content_s",
                    "output_tokens_per_end_to_end_second"):
            value = item[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid timing measurement")
        for key in ("prompt_tokens", "completion_tokens"):
            if type(item[key]) is not int or item[key] <= 0:
                raise ValueError("Invalid token measurement")
        if item["exact_recall"] and item["finish_reason"] != "stop":
            raise ValueError("Truncated output cannot pass recall")
        samples[pair] = item
    if samples.keys() != expected.keys():
        raise ValueError("Incomplete benchmark suite")
    return samples


async def run(base_url, deployment, rows, repetitions, allow_remote=False, transport=None):
    deployment.validate_options()
    if not 3 <= repetitions <= 100:
        raise ValueError("Use 3–100 measured repetitions")
    base_url = checked_url(base_url, allow_remote)
    cases = recall_cases(rows)
    headers = {}
    key = os.environ.get("BIFANG_BENCHMARK_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    samples = []
    async with httpx.AsyncClient(base_url=base_url + "/", headers=headers, timeout=600,
                                 trust_env=False, follow_redirects=False,
                                 transport=transport) as client:
        await sample(client, deployment.model, cases[0])
        for repeat in range(repetitions):
            for case in cases[repeat % len(cases):] + cases[:repeat % len(cases)]:
                result = await sample(client, deployment.model, case)
                result["repeat"] = repeat
                if result["prompt_tokens"] + 128 > deployment.server_options["max_seq_len"]:
                    raise ValueError("Measured prompt exceeds declared context budget")
                samples.append(result)
    return {"schema_version": 1, "protocol": "bifang-recall-v1", "suite_sha256": digest(cases),
            "deployment": deployment.model_dump(), "deployment_evidence": "operator-supplied",
            "settings": {"temperature": 0, "max_tokens": 128, "concurrency": 1,
                         "repetitions": repetitions, "warmups": 1, "rows": list(rows)},
            "samples": samples, "summary": summary(samples),
            "gpu_memory_bytes": None, "serving_kv_dtype_verified": False,
            "optimization_claim": "not-established"}


def compare(baseline: dict, candidate: dict) -> dict:
    original = Deployment.model_validate(baseline["deployment"])
    proposed = Deployment.model_validate(candidate["deployment"])
    original.validate_options()
    proposed.validate_options()
    if original.server_options["kv_cache_config"]["dtype"] not in ("bfloat16", "float16"):
        raise ValueError("Baseline must explicitly use BF16/FP16 KV")
    if proposed.server_options["kv_cache_config"]["dtype"] != "fp8":
        raise ValueError("Candidate must explicitly use FP8 KV")
    left, right = original.model_dump(), proposed.model_dump()
    left["server_options"]["kv_cache_config"].pop("dtype")
    right["server_options"]["kv_cache_config"].pop("dtype")
    if left != right or any(baseline.get(key) != candidate.get(key) for key in
                            ("protocol", "suite_sha256", "settings")):
        raise ValueError("A/B runs differ in more than active KV dtype")
    before, after = validated_samples(baseline), validated_samples(candidate)
    for pair in before:
        if any(before[pair][key] != after[pair][key] for key in
               ("prompt_sha256", "prompt_tokens", "rows", "position")):
            raise ValueError("Paired prompts/tokenization differ")
    baseline_summary, candidate_summary = summary(list(before.values())), summary(list(after.values()))
    return {"baseline": baseline_summary, "candidate": candidate_summary,
            "recall_smoke_gate": "pass" if all(item["exact_recall"] for item in
                                               [*before.values(), *after.values()]) else "reject",
            "optimization_claim": "not-established",
            "remaining_evidence": ["Verify effective cache dtype in serving startup logs",
                                   "Measure per-rank GPU/KV memory at matched token occupancy",
                                   "Run held-out coding/tool tasks and longer context sweeps",
                                   "Repeat alternating A/B order and concurrent load tests"]}


def write_report(path: Path, report):
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--base-url", required=True)
    execute.add_argument("--manifest", type=Path, required=True)
    execute.add_argument("--rows", type=int, nargs="+", default=[256, 2048])
    execute.add_argument("--repetitions", type=int, default=3)
    execute.add_argument("--allow-remote", action="store_true")
    diff = commands.add_parser("compare")
    diff.add_argument("baseline", type=Path)
    diff.add_argument("candidate", type=Path)
    for command in (execute, diff):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output exists; choose a new report path")
        if args.command == "run":
            deployment = Deployment.model_validate_json(args.manifest.read_text())
            report = asyncio.run(run(args.base_url, deployment, args.rows, args.repetitions,
                                     args.allow_remote))
        else:
            report = compare(json.loads(args.baseline.read_text()),
                             json.loads(args.candidate.read_text()))
        write_report(args.output, report)
    except (ValueError, OSError, httpx.HTTPError, KeyError, TypeError):
        parser.exit(1, "Experiment failed validation, transport, or output checks; "
                       "no optimization claim produced. Check configuration privately.\n")


if __name__ == "__main__":
    main()
