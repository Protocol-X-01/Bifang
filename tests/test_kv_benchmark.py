import asyncio
import copy
import json
import os

import httpx
import pytest

from bifang.kv_benchmark import (
    Deployment,
    checked_url,
    compare,
    recall_cases,
    run,
    sample,
    write_report,
)


def deployment(dtype="bfloat16"):
    return Deployment(model="test/nemotron", checkpoint_revision="test-revision",
                      image_digest="sha256:" + "a" * 64, tensorrt_llm_version="test-version",
                      gpu_model="test-only-not-a-gpu-measurement", gpu_count=1,
                      driver_version="test-driver",
                      server_options={"backend": "pytorch", "dtype": "bfloat16",
                                      "max_seq_len": 32768,
                                      "kv_cache_config": {"dtype": dtype,
                                                          "enable_block_reuse": False,
                                                          "max_tokens": 32768}})


def stream_response(answer, finish="stop", usage=True, done=True):
    events = [{"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
              {"choices": [{"index": 0, "delta": {"content": answer[:8]}}]},
              {"choices": [{"index": 0, "delta": {"content": answer[8:]},
                            "finish_reason": finish}]}]
    if usage:
        events.append({"choices": [], "usage": {"prompt_tokens": 200, "completion_tokens": 8}})
    body = ": keepalive\n\n" + "".join("data: " + json.dumps(event) + "\n\n" for event in events)
    if done:
        body += "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)


def mock_server(request):
    assert request.url.path == "/v1/chat/completions"
    payload = json.loads(request.content)
    assert payload["temperature"] == 0
    assert "kv_cache_config" not in payload
    prompt = payload["messages"][0]["content"]
    answer = prompt.split("regression verification code = ", 1)[1].splitlines()[0]
    return stream_response(answer)


def make_report(dtype="bfloat16"):
    return asyncio.run(run("http://127.0.0.1:8000/v1", deployment(dtype), [8, 16], 3,
                           transport=httpx.MockTransport(mock_server)))


def test_paired_streaming_suite_and_report_privacy(tmp_path, monkeypatch):
    monkeypatch.setenv("BIFANG_BENCHMARK_API_KEY", "synthetic-test-secret")
    baseline, candidate = make_report(), make_report("fp8")
    assert len(baseline["samples"]) == 18
    assert baseline["summary"]["exact_recall_rate"] == 1
    assert baseline["gpu_memory_bytes"] is None
    assert baseline["serving_kv_dtype_verified"] is False
    result = compare(baseline, candidate)
    assert result["recall_smoke_gate"] == "pass"
    assert result["optimization_claim"] == "not-established"
    path = tmp_path / "report.json"
    write_report(path, baseline)
    output = path.read_text()
    assert "synthetic-test-secret" not in output
    assert "127.0.0.1" not in output
    assert "module_00000" not in output
    assert "regression verification code =" not in output
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_report(path, baseline)


@pytest.mark.parametrize("change", ["weights", "gpu_count", "suite", "missing", "duplicate",
                                    "tokens", "reuse", "dtype", "nan", "truncated"])
def test_confounded_or_incomplete_comparisons_are_rejected(change):
    baseline, candidate = make_report(), make_report("fp8")
    if change == "weights":
        candidate["deployment"]["checkpoint_revision"] = "different"
    elif change == "gpu_count":
        candidate["deployment"]["gpu_count"] = 8
    elif change == "suite":
        candidate["suite_sha256"] = "wrong"
    elif change == "missing":
        candidate["samples"].pop()
    elif change == "duplicate":
        candidate["samples"].append(copy.deepcopy(candidate["samples"][0]))
    elif change == "tokens":
        candidate["samples"][0]["prompt_tokens"] += 1
    elif change == "reuse":
        candidate["deployment"]["server_options"]["kv_cache_config"]["enable_block_reuse"] = True
    elif change == "dtype":
        baseline["deployment"]["server_options"]["kv_cache_config"]["dtype"] = "auto"
    elif change == "nan":
        candidate["samples"][0]["elapsed_s"] = float("nan")
    elif change == "truncated":
        candidate["samples"][0]["finish_reason"] = "length"
    with pytest.raises(ValueError):
        compare(baseline, candidate)


def test_recall_regression_rejects_candidate_even_if_summaries_are_forged():
    baseline, candidate = make_report(), make_report("fp8")
    candidate["samples"][0]["exact_recall"] = False
    candidate["summary"]["exact_recall_rate"] = 1
    assert compare(baseline, candidate)["recall_smoke_gate"] == "reject"


@pytest.mark.parametrize("url", ["https://host/v1?token=secret", "https://key@host/v1",
                                 "http://host/v1", "https://host/v1", "http://localhost/"])
def test_endpoint_credentials_and_remote_defaults_are_rejected(url):
    with pytest.raises(ValueError):
        checked_url(url, False)
    assert checked_url("https://controlled.example/v1", True).endswith("/v1")


@pytest.mark.parametrize("usage,done", [(False, True), (True, False)])
def test_incomplete_stream_is_not_reported_as_a_measurement(usage, done):
    case = recall_cases([8])[0]

    async def scenario():
        transport = httpx.MockTransport(lambda request: stream_response(case["answer"],
                                                                       usage=usage, done=done))
        async with httpx.AsyncClient(base_url="http://localhost/v1/", transport=transport) as client:
            with pytest.raises(ValueError):
                await sample(client, "test", case)

    asyncio.run(scenario())


def test_first_content_timing_excludes_role_chunk_and_does_not_fake_token_intervals():
    case = recall_cases([8])[0]

    async def scenario():
        clock = iter([10.0, 12.0, 13.5, 14.0])
        async with httpx.AsyncClient(base_url="http://localhost/v1/",
                                    transport=httpx.MockTransport(mock_server)) as client:
            result = await sample(client, "test", case, clock=lambda: next(clock))
        assert result["time_to_first_content_s"] == 2
        assert result["content_chunk_intervals_s"] == [1.5]
        assert result["elapsed_s"] == 4
        assert result["output_tokens_per_end_to_end_second"] == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("rows", [[], [8, 8], [1], [40000]])
def test_invalid_context_sweeps_rejected_before_network(rows):
    with pytest.raises(ValueError):
        recall_cases(rows)
