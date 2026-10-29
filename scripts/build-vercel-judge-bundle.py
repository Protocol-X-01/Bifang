import argparse
from pathlib import Path

from bifang.vercel_bundle import build_bundle

parser = argparse.ArgumentParser(description="Prepare an allowlisted local Vercel judge-relay bundle")
parser.add_argument("--output", type=Path, required=True)
options = parser.parse_args()
manifest = build_bundle(Path(__file__).resolve().parents[1], options.output)
print(f"Prepared {len(manifest['files'])} relay-only files; no deployment performed")
