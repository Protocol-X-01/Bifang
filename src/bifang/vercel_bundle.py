from __future__ import annotations

import hashlib
import json
from pathlib import Path

TEMPLATES = ("pyproject.toml", "uv.lock", ".python-version", "app.py",
             "Dockerfile.vercel", ".vercelignore", "README.md", "verify.py", "vercel.json")
MODULES = ("__init__.py", "judge_relay.py", "model_ids.py")


def build_bundle(repository: Path, output: Path) -> dict:
    repository = repository.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(repository):
        raise ValueError("Choose a fresh bundle directory outside the repository")
    sources = {name: repository / "deploy/vercel-judge-relay" / name for name in TEMPLATES}
    sources.update({"bifang/" + name: repository / "src/bifang" / name for name in MODULES})
    sources["LICENSE"] = repository / "LICENSE"
    payloads = {}
    for name, source in sources.items():
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(repository):
            raise ValueError("Bundle source is missing, symlinked or outside the repository")
        payload = source.read_bytes()
        if len(payload) > 2_000_000:
            raise ValueError("Bundle source exceeds the bounded export size")
        payloads[name] = payload
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    records = []
    for name, payload in sorted(payloads.items()):
        destination = output / name
        destination.parent.mkdir(mode=0o700, exist_ok=True)
        destination.write_bytes(payload)
        destination.chmod(0o600)
        if destination.read_bytes() != payload:
            raise RuntimeError("Bundle readback differs from source")
        records.append({"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {"schema_version": 1, "files": records, "published": False,
                "scope": "Allowlisted relay-only files; no desktop, agent, dataset, environment file or credentials copied. Not a Vercel deployment or comprehensive secret audit."}
    (output / "BUNDLE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "BUNDLE_MANIFEST.json").chmod(0o600)
    return manifest
