import argparse
import asyncio
import json
from pathlib import Path

from bifang.judge_access import check_access, load_judge_token, save_access_report


def main():
    parser = argparse.ArgumentParser(description="Check relay access using metadata GETs only; no inference")
    parser.add_argument("--relay-url", required=True)
    access = parser.add_mutually_exclusive_group(required=True)
    access.add_argument("--judge-token-file", type=Path)
    access.add_argument("--public", action="store_true", help="Check public access without a credential")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    try:
        if options.output and options.output.exists():
            raise ValueError("Choose a fresh report path; existing reports are never overwritten")
        token = None if options.public else load_judge_token(options.judge_token_file)
        report = asyncio.run(check_access(options.relay_url, token, public_access=options.public))
        if options.output:
            save_access_report(options.output, report)
    except (OSError, ValueError):
        parser.error("Invalid input or report destination; private values deliberately withheld")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
