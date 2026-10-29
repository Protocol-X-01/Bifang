from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from bifang.config import state_home

MAX_SOURCE_BYTES = 256_000
MAX_MANIFEST_BYTES = 16_000
HOST_ACCESS = "Trusted Python code: full host access, including files, network, processes and environment. Capability declarations are descriptive, not sandbox permissions."


def plugin_directories(project: Path) -> list[Path]:
    return [project / ".bifang" / "plugins", Path.home() / ".config" / "bifang" / "plugins"]


def read_regular(path: Path, limit: int) -> bytes:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Plugin paths must not contain symlinks")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Plugin file must be regular")
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Plugin file exceeds the size limit")
    return content


@dataclass(frozen=True)
class PluginCandidate:
    identity: str
    manifest_path: Path
    source_path: Path
    sha256: str
    metadata: dict
    source: bytes

    def summary(self) -> dict:
        return {"id": self.identity, "manifest_path": str(self.manifest_path),
                "source_path": str(self.source_path), "sha256": self.sha256,
                **self.metadata, "execution": HOST_ACCESS}


class PluginCatalog:
    def __init__(self, directories: list[Path], trust_path: Path | None = None):
        self.directories = directories
        self.trust_path = trust_path or state_home() / "plugins" / "trust.json"

    def inspect(self, manifest: Path) -> PluginCandidate:
        manifest_bytes = read_regular(manifest, MAX_MANIFEST_BYTES)
        metadata = json.loads(manifest_bytes)
        if not isinstance(metadata, dict) or set(metadata) != {"name", "version", "description", "capabilities"}:
            raise ValueError("Manifest requires name, version, description and capabilities only")
        if not isinstance(metadata["name"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", metadata["name"]):
            raise ValueError("Plugin name must be a lowercase identifier of at most 40 characters")
        for field, limit in (("version", 80), ("description", 1000)):
            if not isinstance(metadata[field], str) or not metadata[field].strip() or len(metadata[field]) > limit:
                raise ValueError(f"Manifest {field} must be a bounded nonempty string")
        capabilities = metadata["capabilities"]
        if (not isinstance(capabilities, list) or len(capabilities) > 4
                or any(not isinstance(value, str) or value not in {"filesystem", "network", "process", "environment"}
                       for value in capabilities) or len(set(capabilities)) != len(capabilities)):
            raise ValueError("Invalid capability declarations")
        if not manifest.name.endswith(".plugin.json"):
            raise ValueError("Select a .plugin.json manifest")
        manifest = manifest.absolute()
        source_path = manifest.with_name(manifest.name.removesuffix(".plugin.json") + ".py")
        source = read_regular(source_path, MAX_SOURCE_BYTES)
        canonical = str(manifest.resolve()).encode()
        identity = hashlib.sha256(canonical).hexdigest()[:24]
        digest = hashlib.sha256(b"bifang-plugin-v1\0" + canonical + b"\0" + manifest_bytes + b"\0" + source).hexdigest()
        return PluginCandidate(identity, manifest, source_path, digest, metadata, source)

    def discover(self) -> tuple[list[PluginCandidate], list[dict]]:
        candidates, errors = [], []
        seen = set()
        for directory in self.directories:
            if not directory.exists():
                continue
            if any(parent.is_symlink() for parent in (directory, *directory.parents)) or not directory.is_dir():
                errors.append({"path": str(directory), "error": "Plugin directory must be a real directory"})
                continue
            for manifest in sorted(directory.glob("*.plugin.json"))[:128]:
                try:
                    candidate = self.inspect(manifest)
                    if candidate.identity not in seen:
                        candidates.append(candidate)
                        seen.add(candidate.identity)
                except (OSError, ValueError, UnicodeError):
                    errors.append({"path": str(manifest), "error": "Invalid, missing, oversized or symlinked plugin files"})
        return candidates, errors

    def records(self) -> dict:
        if not self.trust_path.exists():
            if self.trust_path.is_symlink():
                raise ValueError("Plugin trust storage must not be a symlink")
            return {}
        data = json.loads(read_regular(self.trust_path, 1_000_000))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("plugins"), dict):
            raise ValueError("Invalid plugin trust storage")
        if any(not isinstance(record, dict) for record in data["plugins"].values()):
            raise ValueError("Invalid plugin trust record")
        return data["plugins"]

    def approved(self, candidate: PluginCandidate) -> bool:
        record = self.records().get(candidate.identity)
        return isinstance(record, dict) and record.get("enabled") is True and record.get("sha256") == candidate.sha256

    def list(self) -> dict:
        candidates, errors = self.discover()
        records = self.records()
        return {"plugins": [{**candidate.summary(), "trusted": self.approved(candidate),
                             "state": "enabled" if self.approved(candidate) else
                             "changed" if records.get(candidate.identity, {}).get("enabled") else "disabled"}
                            for candidate in candidates], "errors": errors, "execution": HOST_ACCESS,
                "entry_points": "Automatic installed entry-point loading is disabled"}

    def select(self, identity: str) -> PluginCandidate:
        if not re.fullmatch(r"[0-9a-f]{24}", identity):
            raise ValueError("Use a plugin ID from bifang plugins list")
        candidates, _ = self.discover()
        selected = [candidate for candidate in candidates if candidate.identity == identity]
        if len(selected) != 1:
            raise ValueError("Plugin is no longer available; list and review it again")
        return selected[0]

    def enable(self, identity: str, expected_sha256: str) -> dict:
        candidate = self.select(identity)
        if candidate.sha256 != expected_sha256:
            raise ValueError("Plugin changed; review its current content before trusting it")
        records = self.records()
        records[identity] = {"sha256": expected_sha256, "enabled": True}
        self._write(records)
        return candidate.summary()

    def disable(self, identity: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{24}", identity):
            raise ValueError("Use a plugin ID from bifang plugins list")
        records = self.records()
        records.pop(identity, None)
        self._write(records)

    def _write(self, records: dict) -> None:
        if any(parent.is_symlink() for parent in (self.trust_path, *self.trust_path.parents)):
            raise ValueError("Plugin trust storage must not contain symlinks")
        self.trust_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".trust-", dir=self.trust_path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"version": 1, "plugins": records}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.trust_path)
        finally:
            Path(temporary).unlink(missing_ok=True)
