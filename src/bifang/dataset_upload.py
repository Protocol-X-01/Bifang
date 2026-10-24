from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .dataset_curation import SECRET_PATTERN


def inspect_dataset(directory: Path, private_values: tuple[str, ...] = ()) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    path = directory / "coding.jsonl"
    digest = hashlib.sha256()
    size, count = 0, 0
    with path.open("rb") as contents:
        for line in contents:
            digest.update(line)
            size += len(line)
            row = json.loads(line)
            if set(row) != {"messages"} or not isinstance(row["messages"], list):
                raise ValueError("Unexpected dataset schema")
            if [message.get("role") for message in row["messages"]] != ["user", "assistant"]:
                raise ValueError("Expected user/assistant training examples")
            for message in row["messages"]:
                text = message.get("content")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Empty training content")
                if SECRET_PATTERN.search(text) or any(value in text for value in private_values if value):
                    raise ValueError("Credential screen failed; upload stopped")
            count += 1
    if (not count or not 0 < size < 1_000_000_000 or size != manifest["bytes"]
            or count != manifest["counts"]["exported"] or digest.hexdigest() != manifest["sha256"]
            or manifest["license_allowlist"] != ["cc-by-4.0"]):
        raise ValueError("Manifest, size, license or digest verification failed")
    return {"rows": count, "bytes": size, "sha256": digest.hexdigest(),
            "credential_screen": "Selected patterns and supplied private values; not comprehensive secret detection"}


def verify_remote(client, metadata: dict, expected: dict, filename: str) -> dict:
    identity = metadata.get("id")
    if (not isinstance(identity, str) or not identity or "/" in identity or "?" in identity
            or metadata.get("bytes") != expected["bytes"] or metadata.get("filename") != filename
            or metadata.get("purpose") != "fine-tune"):
        raise ValueError("Remote file metadata does not match the prepared dataset")
    digest = hashlib.sha256()
    size = 0
    response = client.send(client.build_request("GET", f"/v1/files/{identity}/content"), stream=True)
    if response.status_code in {302, 303, 307, 308}:
        target = response.headers.get("location", "")
        response.close()
        parsed = urlsplit(target)
        if (parsed.scheme != "https" or parsed.hostname != "storage.eu-west2.nebius.cloud"
                or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment):
            raise ValueError("Unsupported storage redirect; no credentials forwarded")
        response = client.send(httpx.Request("GET", target), stream=True, auth=None, follow_redirects=False)
    try:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > expected["bytes"]:
                raise ValueError("Remote file exceeds expected size")
            digest.update(chunk)
    finally:
        response.close()
    if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise ValueError("Remote file content digest mismatch")
    return {"file_id": identity, "bytes": size, "sha256": digest.hexdigest(),
            "remote_content_verified": True, "filename": filename, "purpose": "fine-tune"}


def upload_file(client, directory: Path, subset: str, expected: dict, checkpoint) -> dict:
    if subset not in {"train", "validation"}:
        raise ValueError("Unknown dataset subset")
    filename = f"bifang-ocr-{subset}-{expected['sha256'][:16]}.jsonl"
    response = client.get("/v1/files", params={"limit": 1000, "purpose": "fine-tune"})
    response.raise_for_status()
    listing = response.json()
    matches = [entry for entry in listing["data"] if entry.get("filename") == filename]
    if len(matches) > 1 or listing.get("has_more"):
        raise ValueError("File listing is ambiguous; reconcile before creating another upload")
    if matches:
        verified = verify_remote(client, matches[0], expected, filename)
        return {**verified, "reused": True}
    checkpoint({"subset": subset, "filename": filename, "state": "upload_starting", **expected})
    with (directory / "coding.jsonl").open("rb") as source:
        response = client.post("/v1/files", data={"purpose": "fine-tune"},
            files={"file": (filename, source, "application/jsonl")})
    response.raise_for_status()
    metadata = response.json()
    checkpoint({"subset": subset, "state": "uploaded_verification_pending",
                "file_id": metadata.get("id"), "filename": filename})
    return {**verify_remote(client, metadata, expected, filename), "reused": False}
