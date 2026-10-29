from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from .agent import Agent
from .config import Config
from .workspace import Workspace


async def _read_json(path: Path) -> dict:
    def _read():
        with open(path) as f:
            return json.load(f)
    return await asyncio.to_thread(_read)


async def _write_json(path: Path, data: dict):
    def _write():
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    await asyncio.to_thread(_write)


async def run_task(task_file: str):
    task = await _read_json(Path(task_file))

    cfg = Config.load()
    cfg.mode = task.get("mode", "trusted")
    cfg.max_steps = task.get("max_steps", 50)
    cfg.timeout = task.get("timeout", 600)

    ws = Workspace.create(Path(task.get("workspace", ".")), cfg.use_worktree)
    agent = Agent(cfg, ws)

    prompt = task["prompt"]
    result = await agent.ask(prompt)

    output = {
        "result": result,
        "workspace": str(ws.root),
        "diff": ws.diff() or "",
        "transcript": str(agent.audit.path),
    }

    output_file = Path(task.get("output_file", "/tmp/bifang-result.json"))
    await _write_json(output_file, output)

    print(f"Task completed. Output written to {output_file}")
    return output


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m bifang.batch_runner <task_file.json>")
        sys.exit(1)

    task_file = sys.argv[1]
    asyncio.run(run_task(task_file))


if __name__ == "__main__":
    main()