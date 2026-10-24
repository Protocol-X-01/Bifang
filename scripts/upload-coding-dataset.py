import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

from bifang.coding_eval import save_report
from bifang.dataset_upload import inspect_dataset, upload_file


def main():
    parser = argparse.ArgumentParser(description="Upload verified coding JSONL to Token Factory; never starts training")
    parser.add_argument("--dataset-directory", type=Path, required=True)
    parser.add_argument("--live-env-file", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    options = parser.parse_args()
    private = dotenv_values(options.live_env_file)
    key = private.get("NEBIUS_API_KEY")
    if not key:
        raise ValueError("Private file has no Token Factory API key")
    values = tuple(value for name, value in private.items() if value and len(value) >= 8
                   and any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")))
    prepared = {subset: inspect_dataset(options.dataset_directory / subset, values)
                for subset in ("train", "validation")}
    options.output_directory.mkdir(mode=0o700, exist_ok=False)
    save_report(options.output_directory / "preflight.json", prepared)
    sequence = 0

    def checkpoint(row):
        nonlocal sequence
        sequence += 1
        save_report(options.output_directory / f"checkpoint-{sequence:02d}.json", row)

    rows = {}
    with httpx.Client(base_url="https://api.tokenfactory.nebius.com", trust_env=False,
        headers={"Authorization": f"Bearer {key}"},
        timeout=httpx.Timeout(180, connect=15, write=300)) as client:
        for subset, expected in prepared.items():
            try:
                rows[subset] = upload_file(client, options.dataset_directory / subset, subset, expected, checkpoint)
                save_report(options.output_directory / f"{subset}-receipt.json", rows[subset])
                print(json.dumps({"subset": subset, **rows[subset]}), flush=True)
            except Exception as error:
                save_report(options.output_directory / "failure.json", {
                    "subset": subset, "error_type": type(error).__name__,
                    "status_code": error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None,
                    "instruction": "No automatic POST retry. Reconcile remote file listing/checkpoints before retrying."})
                raise SystemExit("Upload or verification failed; inspect the private metadata report before retrying.") from None
    save_report(options.output_directory / "report.json", {
        "timestamp": datetime.now(timezone.utc).isoformat(), "files": rows,
        "training_started": False, "destination": "Token Factory Files API, API key's default project",
        "scope": "Private training/validation file storage; not a Data Lab dataset or training job."})


if __name__ == "__main__":
    main()
