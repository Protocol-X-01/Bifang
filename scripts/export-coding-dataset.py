import argparse
import json
from pathlib import Path

from bifang.dataset_export import export_dataset


def input_rows(path, viewer_response):
    with path.open(encoding="utf-8") as source:
        if viewer_response:
            payload = json.load(source)
            for entry in payload["rows"]:
                if not entry.get("truncated_cells"):
                    yield entry["row"]
        else:
            for line in source:
                if line.strip():
                    yield json.loads(line)


def main():
    parser = argparse.ArgumentParser(description="Export complete coding examples to byte-capped UTF-8 chat JSONL")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--viewer-response", action="store_true")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--allow-license", action="append", required=True)
    parser.add_argument("--max-bytes", type=int, default=900_000_000)
    parser.add_argument("--max-rows", type=int, default=5000)
    options = parser.parse_args()
    report = export_dataset(input_rows(options.input, options.viewer_response), options.output_directory,
        source=options.source, revision=options.revision, allowed_licenses=set(options.allow_license),
        max_bytes=options.max_bytes, max_rows=options.max_rows)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
