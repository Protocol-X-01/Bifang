#!/usr/bin/env bash
set -euo pipefail

: "${NDK_HOME:?Set NDK_HOME to the Android NDK directory}"
: "${BIFANG_PROOT_SOURCE:?Set BIFANG_PROOT_SOURCE to the reviewed PRoot checkout}"
expected_commit=b27d81a68d765f3462e807f4a14e01a03f8e89ea
actual_commit=$(git -C "$BIFANG_PROOT_SOURCE" rev-parse HEAD)
if [[ "$actual_commit" != "$expected_commit" ]]; then
    printf '%s\n' 'Unexpected PRoot source revision' >&2
    exit 1
fi
git -C "$BIFANG_PROOT_SOURCE" diff --exit-code HEAD -- src/loader src/arch.h src/GNUmakefile
compiler="$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android24-clang"
make -B -C "$BIFANG_PROOT_SOURCE/src" loader/loader CC="$compiler"
"$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf" -h "$BIFANG_PROOT_SOURCE/src/loader/loader"
sha256sum "$BIFANG_PROOT_SOURCE/src/loader/loader"
