import argparse
import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.types import ProviderConfig
from bifang.routing import TaskType
from bifang.workspace import Workspace


async def exercise(api_key, root):
    marker = "BIFANG-ROUTING-FIXTURE-7329"
    (root / "fixture.txt").write_text(marker)
    rows = []
    for role, task in (("fast", TaskType.DOC_LOOKUP), ("balanced", TaskType.CODE_REVIEW),
                       ("reasoning", TaskType.ARCHITECTURE)):
        config = Config(default_provider="nebius", providers={"nebius": ProviderConfig(
            name="nebius", api_key=api_key, base_url="https://api.tokenfactory.nebius.com/v1",
            default_model="nvidia/Nemotron-3-Ultra-550b-a55b")}, routing_mode="auto",
            mode="observe", max_steps=3, enable_memory=False, enable_conversation_history=False,
            enable_tracing=False)
        agent = Agent(config, Workspace(root, root))
        original = agent.provider.complete
        calls = 0
        tools_seen = []

        async def no_services():
            return

        async def bounded_completion(messages, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 3:
                raise RuntimeError("Request budget exceeded")
            kwargs["tools"] = [tool for tool in kwargs["tools"]
                               if tool["function"]["name"] == "read_file"]
            return await original(messages, max_tokens=1024, **kwargs)

        def allow_fixture_only(name, arguments):
            if name != "read_file" or arguments != {"path": "fixture.txt"}:
                raise RuntimeError("Unexpected tool action")
            tools_seen.append(name)

        agent._ensure_services_started = no_services
        agent.provider.complete = bounded_completion
        agent.on_tool = allow_fixture_only
        row = {"role": role, "task_type": task.value, "passed": False}
        try:
            answer = await asyncio.wait_for(agent.ask(
                "Use read_file exactly once to inspect fixture.txt. Return ONLY its exact "
                "contents without explanation or formatting.", task_type=task,
                selection={"routing_mode": "auto"}), timeout=180)
            row["passed"] = answer.strip() == marker and tools_seen == ["read_file"]
        except Exception as error:
            row["error_type"] = type(error).__name__
        finally:
            row.update(request_count=calls, tool_count=len(tools_seen),
                       routing=list(agent.provider.requests))
            await agent.close()
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Bounded live Token Factory three-role read-only smoke test")
    parser.add_argument("--live-env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if options.output.exists():
        raise RuntimeError("Choose a fresh report path")
    api_key = dotenv_values(options.live_env_file).get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("The selected private file has no Token Factory key")
    with open(options.output, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        with tempfile.TemporaryDirectory(prefix="bifang-routing-") as temporary:
            rows = asyncio.run(exercise(api_key, Path(temporary)))
        report = {"timestamp": datetime.now(timezone.utc).isoformat(), "results": rows,
                  "passed": all(row["passed"] for row in rows),
                  "limitations": "Explicit task types; synthetic read-only fixture; not a routing quality, coding, cost or scale benchmark."}
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
