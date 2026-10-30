#!/bin/bash
# Build and package Bifang TUI for distribution
#
# This script builds the Rust TUI and packages it for inclusion
# in Python package distributions.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUI_DIR="$SCRIPT_DIR/tui"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"

echo "🔨 Building Bifang TUI..."
echo ""

# Clean previous builds
rm -rf "$BUILD_DIR/tui"
mkdir -p "$BUILD_DIR/tui"
mkdir -p "$DIST_DIR"

# Build release binary
echo "📦 Building release binary..."
cd "$TUI_DIR"
cargo build --release

# Copy binary
echo "📋 Copying binaries..."
TUI_BINARY="$TUI_DIR/target/release/bifang-tui"
if [ -f "$TUI_BINARY" ]; then
    cp "$TUI_BINARY" "$BUILD_DIR/tui/"
    chmod +x "$BUILD_DIR/tui/bifang-tui"
    echo "  ✅ bifang-tui ($(du -h "$BUILD_DIR/tui/bifang-tui" | cut -f1))"
else
    echo "  ❌ TUI binary not found at $TUI_BINARY"
    exit 1
fi

# Generate checksums
echo ""
echo "🔐 Generating SHA256 checksums..."
cd "$BUILD_DIR/tui"
sha256sum bifang-tui > bifang-tui.sha256
echo "  ✅ checksums generated"

# Copy to dist
echo ""
echo "📦 Copying to dist/..."
cp "$BUILD_DIR/tui/bifang-tui" "$DIST_DIR/"
cp "$BUILD_DIR/tui/bifang-tui.sha256" "$DIST_DIR/"
echo "  ✅ TUI packages ready in dist/"

# Summary
echo ""
echo "✅ TUI BUILD COMPLETE!"
echo ""
echo "Binary:     dist/bifang-tui ($(du -h "$DIST_DIR/bifang-tui" | cut -f1))"
echo "Checksum:   dist/bifang-tui.sha256"
echo ""
echo "Next steps:"
echo "  1. Include in Python package data_files"
echo "  2. Or distribute as standalone binary"
echo "  3. Add to GitHub releases"
