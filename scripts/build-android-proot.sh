#!/usr/bin/env bash
set -euo pipefail

: "${NDK_HOME:?Set NDK_HOME to the Android NDK directory}"
: "${BIFANG_PROOT_SOURCE:?Set BIFANG_PROOT_SOURCE to the reviewed PRoot checkout}"
: "${BIFANG_TALLOC_BUILD:?Set BIFANG_TALLOC_BUILD to the ARM64 static talloc build directory}"
expected_commit=b27d81a68d765f3462e807f4a14e01a03f8e89ea
[[ "$(git -C "$BIFANG_PROOT_SOURCE" rev-parse HEAD)" == "$expected_commit" ]]
patch_file="$(cd "$(dirname "$0")" && pwd)/android-proot-string-header.patch"
if git -C "$BIFANG_PROOT_SOURCE" apply --check "$patch_file" 2>/dev/null; then
    git -C "$BIFANG_PROOT_SOURCE" apply "$patch_file"
else
    git -C "$BIFANG_PROOT_SOURCE" apply --reverse --check "$patch_file"
fi
compiler="$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android24-clang"
CPPFLAGS="-I$BIFANG_TALLOC_BUILD/talloc-2.5.0 -DARG_MAX=131072" \
LDFLAGS="-L$BIFANG_TALLOC_BUILD -Wl,-z,max-page-size=16384" \
make -B -C "$BIFANG_PROOT_SOURCE/src" -j2 proot CC="$compiler" PROOT_UNBUNDLE_LOADER=/nonexistent
"$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf" -d "$BIFANG_PROOT_SOURCE/src/proot"
sha256sum "$BIFANG_PROOT_SOURCE/src/proot"
