import argparse
import json
from pathlib import Path

from bifang.coding_eval import evaluate_candidates, save_report, verify_fixtures


def main():
    parser = argparse.ArgumentParser(description="Verify held-out fixtures or sandbox local candidate modules")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-directory", type=Path)
    options = parser.parse_args()
    if options.output.exists():
        raise ValueError("Choose a fresh report path")
    root = Path(__file__).resolve().parents[1] / "evaluations/coding-v1"
    report = (evaluate_candidates(root, options.candidate_directory) if options.candidate_directory
              else verify_fixtures(root))
    save_report(options.output, report)
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
