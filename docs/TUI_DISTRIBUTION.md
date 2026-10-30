# Bifang TUI Distribution

**Binary Size:** 4.5MB (release build, stripped, LTO enabled)

## Quick Start

```bash
# Download binary
wget https://github.com/Protocol-X-01/Bifang/releases/download/v0.2.1-dev.11-refresh.20261029/bifang-tui

# Verify checksum
sha256sum -c bifang-tui.sha256

# Make executable
chmod +x bifang-tui

# Run
./bifang-tui
```

## Building from Source

```bash
# Prerequisites
# - Rust 1.70+ with Cargo
# - C toolchain (gcc or clang)

# Clone
git clone https://github.com/Protocol-X-01/Bifang.git
cd Bifang/tui

# Build release
cargo build --release

# Binary location
./target/release/bifang-tui
```

## Building with Script

```bash
# From repository root
./build-tui.sh

# Outputs:
#   dist/bifang-tui         (4.5MB binary)
#   dist/bifang-tui.sha256  (checksum)
```

## Distribution Methods

### 1. Standalone Binary (Recommended)

**Pros:**
- ✅ Single file, no dependencies
- ✅ Works on any Linux x86_64
- ✅ Fast download (4.5MB)

**Installation:**
```bash
curl -LO https://github.com/Protocol-X-01/Bifang/releases/download/v0.2.1-dev.11-refresh.20261029/bifang-tui
chmod +x bifang-tui
sudo mv bifang-tui /usr/local/bin/
```

### 2. Via Python Package

TUI binary bundled with Python wheel:

```python
# pyproject.toml
[tool.hatch.build.targets.wheel]
artifacts = ["dist/bifang-tui"]

# After pip install:
bifang-tui  # Launches TUI
```

### 3. Package Managers (Future)

```bash
# Homebrew (planned)
brew install bifang

# AUR (planned)
yay -S bifang-tui

# Cargo (available now)
cargo install --git https://github.com/Protocol-X-01/Bifang.git bifang-tui
```

## System Requirements

- **OS:** Linux x86_64 (Ubuntu 22.04+ recommended)
- **Architecture:** x86_64 (amd64)
- **Terminal:** True-color support recommended
- **Memory:** < 50MB RAM

## Checksum Verification

```bash
# Expected SHA256 (v0.2.1-dev.11-refresh.20261029)
sha256sum bifang-tui

# Should match checksum in release notes
```

## Build Optimizations

Current build enables:
- ✅ LTO (Link Time Optimization)
- ✅ Single codegen unit
- ✅ Strip symbols
- ✅ Panic = abort
- ✅ Release profile

Result: 4.5MB stripped binary (from ~50MB debug)

## Post-Hackathon Plans

- [ ] Build for multiple architectures (ARM64, x86)
- [ ] Add to package managers (Homebrew, AUR, deb, rpm)
- [ ] Auto-update mechanism
- [ ] Smaller binary size (< 3MB target)
- [ ] Static linking for maximum compatibility

## Developer Notes

To rebuild after TUI changes:

```bash
# Quick rebuild
./build-tui.sh

# Or manually:
cd tui && cargo build --release && cp target/release/bifang-tui ../dist/
```

For development:

```bash
cd tui
cargo run  # Debug build, faster compile
cargo run --release  # Release build, optimized
```

## Current Limitations

- Linux x86_64 only (no macOS/Windows yet)
- No auto-update (manual download new versions)
- Separate binary from Python CLI

## Integration with Python Package

The TUI can be launched from Python:

```python
import subprocess
import sys
from pathlib import Path

def launch_tui():
    tui_binary = Path(__file__).parent / "bifang-tui"
    if tui_binary.exists():
        sys.exit(subprocess.run([str(tui_binary)]).returncode)
    else:
        print("TUI not bundled. Install separately or build from source.")
```

For hackathon judges: Standalone binary recommended (4.5MB download).
