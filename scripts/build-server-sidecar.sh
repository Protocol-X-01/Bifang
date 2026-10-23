#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3.11}"
build_venv="$root/.build-server-venv"
target_triple="$(rustc --print host-tuple)"
binary_name="bifang-server-${target_triple}"

"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Bifang desktop sidecar requires Python 3.11"'
export UV_PROJECT_ENVIRONMENT="$build_venv"
uv sync --locked --python "$python_bin" --extra dev
mkdir -p "$root/desktop/src-tauri/binaries"
"$build_venv/bin/pyinstaller" \
  --clean \
  --onefile \
  --name "$binary_name" \
  --distpath "$root/desktop/src-tauri/binaries" \
  --workpath "$build_venv/pyinstaller-work" \
  --specpath "$build_venv/spec" \
  --paths "$root/src" \
  --collect-all uvicorn \
  "$root/scripts/bifang-server-entry.py"
