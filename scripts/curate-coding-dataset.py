import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from bifang.dataset_curation import curate_dataset
from bifang.dataset_export import encoded_line


def fetch_page(offset, directory):
    path = directory / f"rows-{offset:06d}.json"
    url = ("https://datasets-server.huggingface.co/rows?dataset=nvidia%2FOpenCodeReasoning"
           f"&config=split_0&split=split_0&offset={offset}&length=100")
    if not path.exists():
        partial = path.with_suffix(".part")
        subprocess.run(["curl", "-4", "--connect-timeout", "5", "--max-time", "40",
                        "--retry", "4", "--retry-delay", "20", "--retry-max-time", "180",
                        "--max-filesize", "20000000", "-fsS", url, "-o", str(partial)],
                       check=True, capture_output=True)
        partial.replace(path)
    raw = path.read_bytes()
    payload = json.loads(raw)
    rows = payload["rows"]
    if (len(rows) != 100 or [entry["row_idx"] for entry in rows] != list(range(offset, offset + 100))
            or any(entry.get("truncated_cells") for entry in rows)):
        raise ValueError(f"Incomplete or truncated source page at offset {offset}")
    return {"path": path.name, "url": url, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "num_rows_total": payload["num_rows_total"], "partial": payload.get("partial", False)}


def main():
    parser = argparse.ArgumentParser(description="Fetch and curate a bounded public NVIDIA candidate pool")
    parser.add_argument("--cache-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--pages", type=int, default=400)
    parser.add_argument("--max-bytes", type=int, default=900_000_000)
    options = parser.parse_args()
    if not 1 <= options.pages <= 500:
        raise ValueError("Use between 1 and 500 pages of 100 examples")
    if options.output_directory.exists():
        raise ValueError("Choose a fresh output directory")
    options.cache_directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    first = fetch_page(0, options.cache_directory)
    available = min(first["num_rows_total"] // 100 * 100, 500_000)
    if available < options.pages * 100:
        raise ValueError("The viewer has too few complete pages for this candidate-pool size")
    offsets = [int(index * available / options.pages) // 100 * 100 for index in range(options.pages)]
    manifests = []
    for index, offset in enumerate(offsets, 1):
        if not (options.cache_directory / f"rows-{offset:06d}.json").exists():
            time.sleep(3.2)
        manifests.append(fetch_page(offset, options.cache_directory))
        if index % 25 == 0:
            print(f"Validated {index}/{options.pages} source pages", flush=True)
    (options.cache_directory / "source-manifest.json").write_bytes(encoded_line({
        "snapshot": "Unversioned Hugging Face rows API; page hashes retained",
        "viewer_partial": first["partial"], "available_prefix_rows": available, "pages": manifests}))

    def rows():
        for manifest in manifests:
            raw = (options.cache_directory / manifest["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
                raise ValueError("Source changed after retrieval")
            for entry in json.loads(raw)["rows"]:
                yield entry["row"]

    report = curate_dataset(rows(), options.output_directory,
        source="https://huggingface.co/datasets/nvidia/OpenCodeReasoning",
        revision="Unversioned rows API snapshot; source-manifest.json preserves exact page hashes",
        max_bytes=options.max_bytes)
    (options.output_directory / "source-manifest.json").write_bytes(
        (options.cache_directory / "source-manifest.json").read_bytes())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
