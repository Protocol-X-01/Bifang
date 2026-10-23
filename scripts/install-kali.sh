#!/usr/bin/env bash
set -euo pipefail
sudo apt update
sudo apt install -y pipx git ripgrep bubblewrap
pipx ensurepath
pipx install --force "$(cd "$(dirname "$0")/.." && pwd)"
echo 'Installed. Export NVIDIA_API_KEY, then run: bifang doctor'