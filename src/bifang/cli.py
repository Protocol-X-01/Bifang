from __future__ import annotations

import argparse
import asyncio
import json
import shlex
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
            print(m)
        return

    if a.cmd == "doctor":
        raise SystemExit(doctor(cfg))

    if a.cmd == "sandbox-check":
        from .sandbox_diagnostics import inspect_sandbox
        report = await inspect_sandbox()
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["ready"] else 1)

    if a.cmd == "toolchains":
        from .toolchains import inspect_toolchains
        print(json.dumps(inspect_toolchains(Path(a.workspace)), indent=2))
        return

    if a.cmd == "setup":
        from .package_setup import run_setup, setup_plan
        plan = setup_plan(Path(a.workspace), network=a.network, registry=a.registry, profile=a.profile, allow_builds=a.allow_builds)
        if a.setup_action == "review":
            print(json.dumps(plan, indent=2))
            return
        if a.sha256 != plan["sha256"]:
            raise ValueError("Setup inputs or options changed; review a fresh plan")
        print(json.dumps(plan, indent=2))
        if not a.yes and input("Install this exact reviewed plan? [y/N] ").strip().lower() != "y":
            print("Setup cancelled; no process started.")
            return
        report = await run_setup(Path(a.workspace), a.sha256, network=a.network, registry=a.registry, profile=a.profile, allow_builds=a.allow_builds, confirmed=True,
                                 on_output=lambda stream, value: C.print(value, end="", markup=False, highlight=False))
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["status"] == "succeeded" and report["receipt_saved"] else 1)

    if a.cmd == "plugins":
        from .plugins.catalog import HOST_ACCESS, PluginCatalog, plugin_directories
        catalog = PluginCatalog(plugin_directories(Path(a.workspace).resolve()))
        if a.plugin_action == "list":
            print(json.dumps(catalog.list(), indent=2))
        elif a.plugin_action == "trust":
            candidate = catalog.select(a.plugin_id)
            if candidate.sha256 != a.sha256:
                raise ValueError("Plugin changed; list and review it again")
            print(json.dumps(candidate.summary(), indent=2))
            print(HOST_ACCESS)
            if not a.yes and input("Trust and enable this exact plugin? [y/N] ").strip().lower() != "y":
                print("Plugin trust cancelled.")
                return
            catalog.enable(a.plugin_id, a.sha256)
            print("Plugin enabled. New or changed content requires fresh approval.")
        elif a.plugin_action == "disable":
            catalog.disable(a.plugin_id)
            print("Plugin disabled. Restart sessions to finish cleanup of previously loaded host code.")
        return

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

    if a.cmd == "boxes":
        print(json.dumps([{"id": workspace.root.name, "path": str(workspace.root), "branch": workspace.branch}
                          for workspace in Workspace.list_existing(Path(a.workspace))], indent=2))
        return

    identity = getattr(a, "box", None)
    if identity is not None or a.cmd in {"patch", "discard"} and cfg.use_worktree:
        ws = Workspace.open_existing(Path(a.workspace), identity)
    elif a.cmd in {"patch", "discard"}:
        source = Workspace.resolve_source(Path(a.workspace))
        ws = Workspace(source, source)
    else:
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
        if not ws.isolated:
            raise RuntimeError("There is no isolated workspace to discard; the original checkout will not be removed")
        if not getattr(a, "yes", False) and input(f"Discard isolated workspace {ws.root}? [y/N] ").strip().lower() != "y":
            C.print("Discard cancelled.")
            return
        ws = Workspace.open_existing(ws.source, ws.root.name)
        ws.discard()
        if ws.root.exists():
            raise RuntimeError("Workspace removal failed; its files were retained")
        C.print("Isolated workspace discarded; original checkout unchanged.")
    elif a.cmd == "run":
        p = Policy(ws.root, cfg.mode)
        arguments = a.command[1:] if a.command[:1] == ["--"] else a.command
        if not arguments:
            raise ValueError("Provide a command after run --")
        command = shlex.join(arguments)
        d = p.command(command)
        if not d.allowed:
            raise PermissionError(d.reason)
        if d.approval and input(f"Run in {ws.root}? [y/N] ").lower() != "y":
            return
        print(await run_command(p, command, cfg.timeout, cfg.use_bwrap))

def main():
    p = argparse.ArgumentParser(prog="bifang", description="Build. Run. Verify.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--workspace", default=".")
    p.add_argument("--box", help="Existing isolated workspace ID from bifang boxes")
    p.add_argument("--provider", help="Provider to use (nvidia, nebius, openai, anthropic, openrouter)")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True
    chat = sub.add_parser("chat")
    chat.add_argument("--session", help="Resume a saved conversation from this project")
    sub.add_parser("conversations")
    sub.add_parser("doctor")
    sub.add_parser("sandbox-check", help="Check actual offline sandbox capabilities without changing host policy")
    sub.add_parser("toolchains", help="Preview optional project toolchains without installing packages")
    setup = sub.add_parser("setup", help="Review and approve isolated locked project setup")
    setup_actions = setup.add_subparsers(dest="setup_action", required=True)
    setup_review = setup_actions.add_parser("review")
    setup_review.add_argument("--network", action="store_true", help="Review host-network access instead of offline setup")
    setup_review.add_argument("--registry", help="Credential-free registry/index URL included in approval")
    setup_review.add_argument("--profile", choices=["javascript-npm", "python-uv", "rust-cargo"], default="javascript-npm")
    setup_review.add_argument("--allow-builds", action="store_true", help="Explicitly review Python dependency builds or Rust check/build code")
    setup_run = setup_actions.add_parser("run")
    setup_run.add_argument("--sha256", required=True, help="Exact fingerprint from setup review")
    setup_run.add_argument("--network", action="store_true", help="Explicitly approve the reviewed host-network plan")
    setup_run.add_argument("--registry", help="Same registry/index URL as the reviewed plan")
    setup_run.add_argument("--profile", choices=["javascript-npm", "python-uv", "rust-cargo"], default="javascript-npm")
    setup_run.add_argument("--allow-builds", action="store_true", help="Explicit build-code permission; must match the reviewed fingerprint")
    setup_run.add_argument("--yes", action="store_true", help="Approve this exact fingerprint without the interactive prompt")
    plugins = sub.add_parser("plugins", help="Review, trust or disable local plugins")
    plugin_actions = plugins.add_subparsers(dest="plugin_action", required=True)
    plugin_actions.add_parser("list")
    trust = plugin_actions.add_parser("trust")
    trust.add_argument("plugin_id")
    trust.add_argument("--sha256", required=True, help="Exact reviewed fingerprint from plugins list")
    trust.add_argument("--yes", action="store_true", help="Confirm full host-code trust for the exact fingerprint")
    disable = plugin_actions.add_parser("disable")
    disable.add_argument("plugin_id")
    m = sub.add_parser("models")
    m.add_argument("--provider", help="Provider to list models from")
    sub.add_parser("patch")
    discard = sub.add_parser("discard")
    discard.add_argument("--yes", action="store_true", help="Confirm removal of the selected isolated workspace")
    sub.add_parser("boxes")
    r = sub.add_parser("run")
    r.add_argument("command", nargs=argparse.REMAINDER)
    asyncio.run(amain(p.parse_args()))
