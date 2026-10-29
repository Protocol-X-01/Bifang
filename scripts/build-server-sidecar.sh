#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
exec uv run --no-project --python 3.11 python "$root/scripts/build-server-sidecar.py"
