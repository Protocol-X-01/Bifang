from __future__ import annotations

import difflib
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath


def selected_path(value: str) -> str:
    path = PurePosixPath(value)
    blocked = {".git", ".bifang", ".arca", ".venv", "node_modules", ".ssh", ".aws", ".vercel"}
    if (not value or len(value) > 512 or any(ord(character) < 32 or ord(character) == 127 for character in value)
            or path.is_absolute() or ".." in path.parts or "\\" in value
            or any(part in blocked for part in path.parts)
            or any(part.startswith(".env") for part in path.parts)
            or path.name in {"id_rsa", "id_ed25519", "credentials"}
            or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}):
        raise ValueError("Select a relative source path, not credential or internal state files")
    if path.as_posix() != value or value == ".":
        raise ValueError("Source paths must be normalized")
    return value


def read_selected(root: Path, value: str) -> tuple[bytes, int] | None:
    parts = PurePosixPath(selected_path(value)).parts
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(child, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1_000_000:
                raise ValueError("Select regular source files below 1 MB")
            data = stream.read(1_000_001)
            if len(data) > 1_000_000:
                raise ValueError("Source file grew beyond the size budget")
            data.decode("utf-8")
            return data, metadata.st_mode & 0o111
    except FileNotFoundError:
        return None
    finally:
        os.close(descriptor)


def manifest_digest(files: dict[str, tuple[bytes, int] | None]) -> str:
    manifest = {name: None if content is None else {
        "sha256": hashlib.sha256(content[0]).hexdigest(), "executable": content[1],
    } for name, content in files.items()}
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


class Candidate:
    def __init__(self, source: Path, files: list[str], writable: list[str]):
        if not (files or writable) or len(set(files) | set(writable)) > 128:
            raise ValueError("Select between one and 128 source/output paths")
        self.source = source.resolve()
        self.files = frozenset(selected_path(value) for value in files)
        self.writable = frozenset(selected_path(value) for value in writable)
        self.paths = self.files | self.writable
        self.baseline = {name: read_selected(self.source, name) for name in self.paths}
        if any(self.baseline[name] is None for name in self.files):
            raise ValueError("Selected source file does not exist")
        if sum(len(content[0]) for content in self.baseline.values() if content) > 8_000_000:
            raise ValueError("Selected source exceeds the 8 MB budget")
        self.storage = tempfile.TemporaryDirectory(prefix="bifang-candidate-")
        self.root = Path(self.storage.name)
        self.closed = False
        try:
            for name, content in self.baseline.items():
                if content is not None:
                    target = self.root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content[0])
                    target.chmod(0o600 | content[1])
        except BaseException:
            self.close()
            raise

    def snapshot(self) -> dict[str, tuple[bytes, int] | None]:
        if self.closed:
            raise RuntimeError("Candidate is closed")
        return {name: read_selected(self.root, name) for name in self.paths}

    def describe(self) -> dict:
        current = self.snapshot()
        return {"baseline_sha256": manifest_digest(self.baseline),
                "candidate_sha256": manifest_digest(current),
                "source_unchanged": all(read_selected(self.source, name) == content
                                        for name, content in self.baseline.items()),
                "changed_files": sorted(name for name in self.paths if current[name] != self.baseline[name])}

    def patch(self) -> str:
        current = self.snapshot()
        output = []
        for name in sorted(self.paths):
            before, after = self.baseline[name], current[name]
            if before == after:
                continue
            if before and after and before[1] != after[1]:
                raise ValueError("Executable-mode changes need separate review")
            original = before[0].decode() if before else ""
            proposed = after[0].decode() if after else ""
            output.append(f"diff --git a/{name} b/{name}\n")
            if before is None:
                output.append(f"new file mode {100755 if after and after[1] else 100644}\n")
            elif after is None:
                output.append("deleted file mode 100644\n")
            for line in difflib.unified_diff(original.splitlines(keepends=True), proposed.splitlines(keepends=True),
                                             fromfile=f"a/{name}" if before else "/dev/null",
                                             tofile=f"b/{name}" if after else "/dev/null"):
                output.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
        return "".join(output)

    def close(self):
        self.storage.cleanup()
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()
