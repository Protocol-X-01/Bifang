from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import BinaryIO

MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 2_000_000


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate request field")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError("Invalid JSON constant")


def dispatch(request: object) -> dict:
    if not isinstance(request, dict):
        raise TypeError("Expected an object")
    action = request.get("action")
    fields = {
        "plugins.list": set(),
        "plugins.review": {"id"},
        "plugins.trust": {"id", "sha256", "confirmed"},
        "plugins.disable": {"id"},
        "toolchains.inspect": set(),
        "metrics.sample": set(),
        "setup.plan": {"network"},
        "setup.profile_plan": {"network", "profile", "allow_builds"},
    }
    if not isinstance(action, str) or action not in fields:
        raise ValueError("Unknown action")
    if set(request) != {"version", "action", "workspace"} | fields[action]:
        raise ValueError("Unexpected fields")
    if type(request["version"]) is not int or request["version"] != 1:
        raise ValueError("Unsupported version")
    workspace = request["workspace"]
    if not isinstance(workspace, str) or not Path(workspace).is_absolute():
        raise ValueError("Choose an absolute project directory")
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Choose a project directory")
    if action in {"setup.plan", "setup.profile_plan"}:
        from bifang.package_setup import setup_plan

        return setup_plan(root, network=request["network"], profile=request.get("profile", "javascript-npm"), allow_builds=request.get("allow_builds", False))
    if action == "metrics.sample":
        from bifang.system_metrics import sample_system_metrics

        return sample_system_metrics(root)
    if action == "toolchains.inspect":
        from bifang.toolchains import inspect_toolchains

        return inspect_toolchains(root)

    from bifang.plugins.catalog import PluginCatalog, plugin_directories

    catalog = PluginCatalog(plugin_directories(root))
    if action == "plugins.list":
        return catalog.list()
    identity = request["id"]
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{24}", identity):
        raise ValueError("Invalid plugin identity")
    if action == "plugins.review":
        candidate = catalog.select(identity)
        return {**candidate.summary(), "source": candidate.source.decode("utf-8")}
    if action == "plugins.disable":
        catalog.disable(identity)
        return {"id": identity, "enabled": False}
    fingerprint = request["sha256"]
    if request["confirmed"] is not True:
        raise ValueError("Explicit confirmation required")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("Invalid fingerprint")
    return {**catalog.enable(identity, fingerprint), "enabled": True}


def serve_once(source: BinaryIO, destination: BinaryIO) -> int:
    try:
        raw = source.readline(MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            raise ValueError("Expected a bounded newline-delimited request")
        request = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
        response = {"ok": True, "result": dispatch(request)}
        encoded = json.dumps(response, ensure_ascii=True).encode("utf-8")
        if len(encoded) > MAX_RESPONSE_BYTES:
            raise ValueError("Response too large")
    except (OSError, ValueError, TypeError, RecursionError):
        encoded = b'{"ok":false,"error":"Workbench request failed. Refresh and review the current files and selection."}'
    destination.write(encoded + b"\n")
    destination.flush()
    return 0 if json.loads(encoded)["ok"] else 1


def main() -> None:
    os.environ["BIFANG_NO_DOTENV"] = "1"
    raise SystemExit(serve_once(sys.stdin.buffer, sys.stdout.buffer))


if __name__ == "__main__":
    main()
