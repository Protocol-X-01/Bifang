# Bundled Android Linux runtime

The standalone Terminal runtime is built for Android ARM64, API 24 and newer.
PRoot and its loader are packaged as native executables in the APK; they do not
use a Termux installation or its private storage. The distribution catalogue and
the Termux compatibility backend remain separate from this runtime.

## Rebuild the native dependencies

Use a Linux x86-64 host, Python 3.11.8 or newer, Git, Make and Android NDK
`29.0.14206865`. Run these commands from the repository root, choosing fresh build
directories. The talloc builder refuses to overwrite an existing directory.

```sh
export NDK_HOME=/path/to/android-ndk
mkdir -p build/android-runtime
curl --fail --location --proto '=https' \
  https://www.samba.org/ftp/talloc/talloc-2.5.0.tar.gz \
  -o build/android-runtime/talloc-2.5.0.tar.gz
python3 scripts/build-android-talloc.py \
  --archive build/android-runtime/talloc-2.5.0.tar.gz \
  --ndk "$NDK_HOME" --output build/android-runtime/talloc

git clone https://github.com/termux/proot.git build/android-runtime/proot
git -C build/android-runtime/proot checkout --detach \
  b27d81a68d765f3462e807f4a14e01a03f8e89ea
export BIFANG_PROOT_SOURCE="$PWD/build/android-runtime/proot"
export BIFANG_TALLOC_BUILD="$PWD/build/android-runtime/talloc"
bash scripts/build-android-proot.sh
bash scripts/build-android-proot-loader.sh
python3 scripts/stage-android-proot.py \
  --proot-source "$BIFANG_PROOT_SOURCE" \
  --talloc-source "$BIFANG_TALLOC_BUILD/talloc-2.5.0" \
  --output build/android-runtime/stage
```

The talloc archive is checked against SHA-256
`912afa237510ae542a7733998eb18a12bcda35ab6729c8e2ddb43e8d0ebab007` before extraction.
Its Android configuration and explicit-memory-fill implementation live in
`scripts/android-talloc/`; no configuration is fetched from a moving branch.
The build retains the original archive, extracted source, local configuration,
object files and `build-manifest.json`. Object paths are normalized and the static
archive uses deterministic mode.

The PRoot build applies only the retained missing-string-header patch. The staging
script checks ARM64 executable headers and includes the upstream PRoot and talloc
licence files with a binary-hash manifest.

## Package and test

To include the staged runtime in a standalone Terminal APK, set
`BIFANG_NATIVE_RUNTIME` to the absolute staging directory and set both
`BIFANG_TERMINAL_EDITION=1` and `VITE_BIFANG_EDITION=terminal` for the Companion
Android build. The Gradle configuration extracts the native executables into the
application's native-library directory.

`NativeLinuxRuntimeInstrumentedTest` runs the production runtime probe twice and
checks cleanup. Run that test explicitly against a build containing the runtime;
the normal Companion APK does not include these executables. It executes a fixed
Android shell command through bundled PRoot, without opening a window, using the
Termux bridge or accessing another application's files.

This check covers the native execution foundation. Distribution extraction,
first-boot setup, package-manager operation and interactive terminal behaviour
need their own checks as the standalone installer is completed.
