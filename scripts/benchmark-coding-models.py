import argparse
import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from bifang.coding_eval import TASK_IDS, run_checks, save_report, task_manifest
from bifang.providers.base import ChatMessage
from bifang.providers.nebius import NebiusProvider
from bifang.providers.types import ProviderConfig


MODELS = {
    "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
}


async def benchmark(key, root, output):
    provider = NebiusProvider(ProviderConfig(name="nebius", api_key=key,
        base_url="https://api.tokenfactory.nebius.com/v1"))
    results = []
    try:
        available = await provider.verified_model_ids()
        if not set(MODELS.values()) <= available:
            raise RuntimeError("All requested models must be present in the live catalog")
        for role, model in MODELS.items():
            for identity in TASK_IDS:
                task = root / identity
                prompt = ((task / "brief.md").read_text() + "\n\nCurrent module:\n```python\n"
                          + (task / "baseline.py").read_text() + "\n```\n")
                row = {"task": identity, "role": role, "requested_model": model,
                       "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "passed": False}
                started = time.monotonic()
                try:
                    response = await asyncio.wait_for(provider.complete([
                        ChatMessage(role="user", content=prompt)], model=model,
                        temperature=0, max_tokens=4096), timeout=120)
                    row.update(reported_model=response.reported_model,
                        finish_reason=response.finish_reason,
                        usage={name: value for name, value in (response.usage or {}).items()
                               if name in {"prompt_tokens", "completion_tokens", "total_tokens"}
                               and type(value) is int and value >= 0})
                    if response.finish_reason != "stop":
                        row["status"] = "incomplete_completion"
                    else:
                        final = (response.content or "").rsplit("</think>", 1)[-1].strip()
                        fenced = re.fullmatch(r"```(?:python|py)?\s*\n(.*?)\n```", final, re.DOTALL)
                        source = fenced[1] if fenced else final
                        candidate = output / f"{role}-{identity}.py"
                        candidate.write_text(source)
                        candidate.chmod(0o600)
                        row.update(candidate_sha256=hashlib.sha256(source.encode()).hexdigest(),
                                   **run_checks(task, source, sandbox=True))
                except Exception as error:
                    row.update(status="error", error_type=type(error).__name__)
                row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                results.append(row)
                save_report(output / f"{role}-{identity}.json", row)
                print(json.dumps(row), flush=True)
    finally:
        await provider.close()
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "results": results,
        "summary": {role: {"passed": sum(row["passed"] for row in results if row["role"] == role),
                           "total": len(TASK_IDS)} for role in MODELS},
        "manifest": task_manifest(root), "model_requests": len(results),
        "limitations": ["One trial on three small authored module repairs, not full-agent or broad coding quality.",
            "Only briefs and buggy modules sent to hosted models; checks and reference repairs withheld.",
            "Candidates run in bubblewrap with no network or home mounts; evaluator is not adversarially tamper-proof.",
            "No training, LangSmith upload, classifier evaluation, pricing or capacity claims."]}


def main():
    parser = argparse.ArgumentParser(description="Nine-call local-report Token Factory module-repair comparison")
    parser.add_argument("--live-env-file", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "evaluations/coding-v1"
    task = root / TASK_IDS[0]
    if not run_checks(task, (task / "reference.py").read_text(), sandbox=True)["passed"]:
        raise RuntimeError("Sandbox preflight failed; no paid model requests made")
    key = dotenv_values(options.live_env_file).get("NEBIUS_API_KEY")
    if not key:
        raise RuntimeError("Private file has no Token Factory key")
    options.output_directory.mkdir(mode=0o700, exist_ok=False)
    report = asyncio.run(benchmark(key, root, options.output_directory))
    save_report(options.output_directory / "report.json", report)
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
