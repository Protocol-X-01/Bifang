import argparse
import asyncio
import json
import os
import tempfile
from contextlib import aclosing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.types import ProviderConfig
from bifang.workspace import Workspace


async def exercise(api_key, root):
    marker = "BIFANG-STREAM-FIXTURE-7329"
    (root / "fixture.txt").write_text(marker)
    config = Config(default_provider="nebius", providers={"nebius": ProviderConfig(
        name="nebius", api_key=api_key, base_url="https://api.tokenfactory.nebius.com/v1",
        default_model="nvidia/Nemotron-3-Ultra-550b-a55b")}, routing_mode="pinned",
        mode="observe", max_steps=3, enable_memory=False, enable_conversation_history=False,
        enable_tracing=False)
    agent = Agent(config, Workspace(root, root))
    original = agent.provider.complete_stream
    calls = 0
    tools_seen = []

    async def no_services():
        return

    async def bounded_stream(messages, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 3:
            raise RuntimeError("Request budget exceeded")
        kwargs["tools"] = [tool for tool in kwargs["tools"]
                           if tool["function"]["name"] == "read_file"]
        async with aclosing(original(messages, max_tokens=1024, **kwargs)) as stream:
            async for chunk in stream:
                yield chunk

    def allow_fixture_only(name, arguments):
        if name != "read_file" or arguments != {"path": "fixture.txt"}:
            raise RuntimeError("Unexpected tool action")
        tools_seen.append(name)

    async def collect():
        async with aclosing(agent.ask_stream(
            "Use read_file exactly once to inspect fixture.txt. Return ONLY its exact "
            "contents without explanation or formatting.")) as stream:
            return "".join([chunk async for chunk in stream])

    agent._ensure_services_started = no_services
    agent.provider.complete_stream = bounded_stream
    agent.on_tool = allow_fixture_only
    report = {"passed": False}
    try:
        answer = await asyncio.wait_for(collect(), timeout=180)
        report.update(passed=answer.strip() == marker and tools_seen == ["read_file"],
                      answer_chars=len(answer), contains_marker=marker in answer)
    except Exception as error:
        report["error_type"] = type(error).__name__
    finally:
        report.update(request_count=calls, tool_count=len(tools_seen),
                      routing=list(agent.provider.requests))
        await agent.close()
    return report


def main():
    parser = argparse.ArgumentParser(description="Bounded read-only live Token Factory streaming check")
    parser.add_argument("--live-env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    api_key = dotenv_values(options.live_env_file).get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("The selected private file has no Token Factory key")
    with open(options.output, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        with tempfile.TemporaryDirectory(prefix="bifang-stream-") as temporary:
            report = asyncio.run(exercise(api_key, Path(temporary)))
        report.update(timestamp=datetime.now(timezone.utc).isoformat(),
            limitations="Pinned Ultra; synthetic read-only fixture; source-only, not a native-package, quality, cost or scale benchmark.")
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
