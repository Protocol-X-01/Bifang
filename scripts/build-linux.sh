#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_PROJECT_ENVIRONMENT="$(pwd)/.build-cli-venv"
uv sync --locked --extra dev
"$UV_PROJECT_ENVIRONMENT/bin/pyinstaller" --clean --onefile --name bifang --collect-all textual src/bifang/__main__.py
sha256sum dist/bifang > dist/bifang.sha256
