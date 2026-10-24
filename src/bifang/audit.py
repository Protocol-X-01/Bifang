import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path


class Audit:
    def __init__(self, root: Path):
        root = root.resolve()
        directory = (root / ".bifang/sessions").resolve()
        if root not in directory.parents:
            raise ValueError("Audit directory escapes the workspace")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        identity = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
        self.path = directory / f"{identity}.jsonl"
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)

    def add(self, event, **data):
        row = {"time": datetime.now(UTC).isoformat(), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
