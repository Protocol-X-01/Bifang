from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

from rich.console import Console

from . import __version__
from .agent import Agent
from .config import Config
from .context import ContextManager
from .policy import Policy
from .provider import ProviderManager
from .tools import run_command
from .workspace import Workspace

C = Console()


def doctor(cfg: Config):
    checks = {
        "python": sys.version.split()[0],
        "git": shutil.which("git") or "missing",
        "rg": shutil.which("rg") or "missing",
        "bwrap": shutil.which("bwrap") or "missing",
        "api_key": "set" if any(p.api_key for p in cfg.providers.values()) else "missing",
        "model": cfg.get_default_model(),
        "provider": cfg.default_provider,
    }
    for k, v in checks.items():
        C.print(f"{k:10} {v}")
    return 0 if checks["git"] != "missing" and checks["api_key"] == "set" else 1


async def amain(a):
    cfg = Config.load()
    if getattr(a, "provider", None):
        cfg.default_provider = a.provider

    if a.cmd == "models":
        provider_name = getattr(a, "provider", None) or cfg.default_provider
        pm = ProviderManager(cfg)
        try:
            models = await pm.list_models(provider_name)
        finally:
            await pm.close()
        for m in models:
            if "nvidia" in m.lower() or "nemotron" in m.lower() or "gpt" in m.lower() or "claude" in m.lower():
                print(m)
        return

    if a.cmd == "doctor":
        raise SystemExit(doctor(cfg))

    if a.cmd == "conversations":
        source = Path(a.workspace).resolve()
        if cfg.use_worktree:
            source = Workspace.resolve_source(source)
        context = ContextManager(cfg, project_path=source)
        try:
            if not context.conversation_cache:
                C.print("Conversation history is disabled.")
                return
            cache = context.conversation_cache.cache
            if not (cache.storage_path / "conversations.db").exists():
                C.print("No saved conversations.")
                return
            await context.initialize()
            for session in cache.list_sessions():
                C.print(f"{session.session_id}  {len(session.turns)} turns")
        finally:
            await context.close()
        return

    ws = Workspace.create(Path(a.workspace), cfg.use_worktree)

    if a.cmd == "chat":
        from .tui import BifangApp
        agent = Agent(cfg, ws)
        try:
            identity = getattr(a, "session", None)
            if identity:
                if not agent.context.conversation_cache:
                    raise RuntimeError("Conversation history is disabled")
                await agent.context.initialize()
                if agent.context.conversation_cache.cache.get_session(identity) is None:
                    raise RuntimeError("Conversation not found in this workspace")
                await agent.context.start_session(identity)
            await BifangApp(agent).run_async()
        finally:
            await agent.close()
    elif a.cmd == "patch":
        print(ws.diff(), end="")
    elif a.cmd == "discard":
        ws.discard()
        C.print("Bifang discarded")
    elif a.cmd == "run":
        p = Policy(ws.root, cfg.mode)
        command = " ".join(a.command)
        d = p.command(command)
        if d.approval and input(f"Run in {ws.root}? [y/N] ").lower() != "y":
            return
        print(await run_command(p, command, cfg.timeout, cfg.use_bwrap))

def main():
    p = argparse.ArgumentParser(prog="bifang", description="Build. Run. Verify.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--workspace", default=".")
    p.add_argument("--provider", help="Provider to use (nvidia, nebius, openai, anthropic, openrouter)")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True
    chat = sub.add_parser("chat")
    chat.add_argument("--session", help="Resume a saved conversation from this project")
    sub.add_parser("conversations")
    sub.add_parser("doctor")
    m = sub.add_parser("models")
    m.add_argument("--provider", help="Provider to list models from")
    sub.add_parser("patch")
    sub.add_parser("discard")
    r = sub.add_parser("run")
    r.add_argument("command", nargs=argparse.REMAINDER)
    asyncio.run(amain(p.parse_args()))
