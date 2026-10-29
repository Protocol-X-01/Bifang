# Releasing

## Current dev11 candidate (October 28)

Dev11 adds approved Tavily page extraction and complete relay source export.
The [dev11 receipt](evidence/dev11-local.json) identifies its exact packages,
build inputs and corrected source snapshot. That corrected snapshot passes
850 tests with real Bubblewrap checks enabled. Each Linux format passes the
GLIBC 2.35 audit, 33 embedded-library checks, 15 helper checks and two packaged
API tests. The normalized Debian installer passes a fresh Ubuntu 24.04 install.

The Debian packaging candidate uses `0.2.1~preview.7`, while the application
identifies itself as `0.2.1-dev.11`. Its checksum is
`39dfe18e4611bdb2165f30c82604e3b55bb384c57bcf80a5c12f9c456af46f63`.
Use this dev11 installer for the next candidate review; the older dev10
normalized installer has the same packaging version but different bytes.
Never substitute one for the other or overwrite a published asset.

Dev11 is installed locally. Owner restart and native-window acceptance remain
pending. Publication, Windows/macOS execution and final submission are separate
remaining steps. The sections below preserve earlier artifact evidence.

## Earlier dev10 Linux formats (October 28)

New release-profile Debian, AppImage and RPM candidates built in Ubuntu 22.04
now pass the **GLIBC 2.35** ceiling audit. Each extracted package passes 15
helper checks and two packaged backend tests, including fresh-folder reviewed
Apply and stale-approval rejection. Download transfer checksums match the build
VM. See [baseline artifact identities](evidence/dev10-linux-baseline.json).
Target installation, native interaction and publication remain delivery gates.

The dev10 Debian candidate is additionally repackaged as `0.2.1~preview.7` for
upgrade testing: it sorts after the published `0.2.1~preview.6` and before
stable `0.2.1`. `scripts/normalize-debian-preview.py` verifies the input checksum,
version ordering and unchanged installed payload, including file contents,
ownership, permissions and links. Preserve both package checksums and the
normalization report. The application itself retains its dev10 build identity;
this packaging candidate has not been published as Preview 7.
Its exact normalized installer now passes a fresh Ubuntu 24.04 APT installation,
library loading, eight management checks and API health/cleanup. The global
user-namespace restriction remains enabled. See [installation evidence](evidence/dev10-debian-install.json)
for its checksum and scope; native-window acceptance is still pending.

### Earlier host-built candidates

Dev10 has local Debian, AppImage and RPM packages. The AppImage's extracted
`AppRun` and RPM's extracted executable each pass two isolated nonvisual
startups; their exact sidecars each pass authentication and fresh-folder
reviewed-Apply tests. RPM payload digests pass. Neither additional format is
published, installed on its target distribution, or visually accepted.

The host-built AppImage bundles libraries requiring **GLIBC 2.43**; the RPM
declares the same host baseline. The newer Ubuntu 22.04 outputs above supersede
these host builds for broader Linux testing. The current
installed Debian artifact and its evidence remain unchanged. The paragraphs
below retain historical preview identities, not current publication status.

## Linux desktop test build

The vision preview uses desktop SemVer `0.2.1-preview.5` and Python
PEP 440 `0.2.1.dev5`; check GitHub Releases for publication status. A distinct package version
must sort after the previous preview's Debian version `0.2.0`; check the actual
generated package with `dpkg-deb -f` and `dpkg --compare-versions` before release.
The retained local candidate normalizes the generated Debian control version
to `0.2.1~preview.5`, verifies unchanged payload-file hashes, and checks that it
sorts above `0.2.0` but below future stable `0.2.1`. Preserve the original bundler
checksum separately from the normalized installer checksum. Its
[native receipt](evidence/ubuntu-vision-native.json) binds only that installer.
GitHub normalizes the tilde in uploaded filenames to a dot. The download is
`Bifang-vision_0.2.1.preview.5_amd64.deb`; its internal Debian version remains
`0.2.1~preview.5`. Checksums and installation instructions use the download name.
Keep npm, Cargo and Tauri versions aligned, and Python metadata and `uv.lock`
aligned. Never overwrite a retained installer or transfer its native evidence
to the newer build.

The desktop release bundles the React frontend and Python API sidecar into a
Tauri Debian package:

```bash
cd desktop
npm ci
npm run tauri:build -- --bundles deb
```

The build requires Python 3.11, Rust 1.90+, Node.js 20.19+, `uv`, and the Linux
Tauri development libraries listed in `desktop/README.md`. Python packages
come from the committed `uv.lock`; Rust dependencies use `desktop/src-tauri/Cargo.lock`;
frontend dependencies use `desktop/package-lock.json`. The CI workflow uploads
the Linux `.deb` package as an artifact after a successful native build.
The current local CI source explicitly targets Ubuntu 22.04 rather than the
moving `ubuntu-latest` label. Earlier host-built previews used Ubuntu 24.04;
retain their separate artifact identities. The older build baseline does not
replace installed-package validation on supported target distributions.

Before publishing a public GitHub Release:

1. Verify the installed package starts and completes the demo loop on a clean
   supported Linux machine.
2. Confirm provider configuration is outside the repository and scan all
   tracked files and Git history for secrets; rotate any exposed credentials.
3. Generate a SHA-256 checksum and include installation instructions and
   known platform limitations with the release.
4. Publish the public source repository under Apache-2.0 and link to the
   release build from the Devpost submission.

## Local test evidence (2026-10-23)

### Newer local approval-level candidate (2026-10-24)

The current unreleased candidate separately passes fresh Ubuntu 24.04.5
installation/live coding, and native approval/sandbox checks with Ubuntu's
scoped distribution AppArmor profile. See
[local native validation](LOCAL_NATIVE_VALIDATION.md) and
[Ubuntu prerequisites](UBUNTU_SANDBOX.md). The paragraphs below retain earlier
package identities; they are not substitutes for the current candidate's evidence.

For publication, retain the original frozen build-input archive and its
manifest. A new source archive can include later documentation without a
runtime rebuild only after checking that every runtime, build, dependency-lock,
asset, script and test input is unchanged. Keep the later source archive's
checksum separate, and include
[build-input provenance](evidence/publication-provenance.json). Distribute the
matching candidate package, checksums and notice archive together. Do not
replace immutable captures or describe cached native rebuilds as bit-identical.
Use [submission handoff](SUBMISSION_CHECKLIST.md) for the remaining approval,
public-link, video and judging-access gates.

### Historical retained build

A Linux release-profile Debian package was built with
`tauri build --bundles deb --ci`. Its extracted application completed a live
Token Factory Nemotron Ultra receipt-parser task through the native Tauri UI
on a virtual X display: submit prompt, approve actions, review diff, confirm
apply. All five original checks passed afterward. The rehearsal used
automated, exact-action approval clicks and a preselected synthetic workspace.
See [demo evidence](DEMO_EVIDENCE.md) for scope and screenshots.

The build used existing system runtime libraries plus development packages
extracted under `/tmp`; no privileged package installation was performed.
The native executable references GLIBC symbols through `GLIBC_2.39` on this
build host. Do not claim Debian 12 compatibility or broad Linux portability
from the `.deb` format alone. A fresh Ubuntu 24.04 VM now passes installation
and the live UI loop with a preselected workspace; see
[installation evidence](INSTALLATION_EVIDENCE.md). Successful native folder
selection and a public YouTube video remain unverified. Do not distribute this local
preview as a validated production release. The newer
[preview 2](https://github.com/Protocol-X-01/bifang/releases/tag/v0.2.0-preview.2)
adds validated workspace selection through its in-app path dialog and passes
the same installed live task in a second clean Ubuntu VM without preselection.

## Preview distribution and notices

Preview 2 is an unsigned prerelease, not a signed or production-certified
installer. Retain the accompanying third-party notice archive with the binary.
Its generated inventory conservatively includes build dependencies, available
Python/npm/Cargo license texts, the Python runtime license, and supplementary
distribution notices. It is not a complete binary SBOM or legal certification.
Upstream Cargo source links and retained supplementary notice provenance are
included in the archive; third-party code retains its own licensing.

To regenerate the inventory after building and installing locked dependencies:

```bash
cargo metadata --manifest-path desktop/src-tauri/Cargo.toml --locked \
  --filter-platform x86_64-unknown-linux-gnu --format-version 1 > /tmp/bifang-cargo.json
.build-server-venv/bin/python scripts/collect-release-notices.py \
  --cargo-metadata /tmp/bifang-cargo.json \
  --supplementary-notices /path/to/extracted/notices/supplementary \
  --output /tmp/bifang-notices
```

The supplementary files fill notices omitted from six published crate
archives. Their provenance uses the revisions recorded in `.cargo_vcs_info.json`
or the standard MPL 2.0 text; no third-party source modifications are claimed.
Review missing notices and actual binary contents for each new release rather
than treating a successful generator exit as proof of compliance.

The October 26 Ubuntu 22.04 release candidate has a separate
[exact-build notice inventory](evidence/linux-baseline-notices.json): 526
components, with a retained notice file for every inventoried component. It was
collected from the same stopped builder that produced all three hash-verified
packages, not regenerated from the newer host's dependencies. The archive includes
50 Python distributions, CPython, 107 production npm packages, 356 resolved Cargo
packages, ten supplementary distribution notices and two standard licence texts.
The collector covers both Ubuntu's `libssl3` and newer `libssl3t64` package names;
the final archive supersedes an earlier inventory missing the Ubuntu 22.04 notice.
This conservative source/build inventory does not prove correspondence for every
bundled native library, AppImage launcher or PyInstaller-embedded runtime file.
Review those redistributed contents and their source/notice obligations before
publishing; do not transfer older preview notice archives to this candidate.

## Other targets

The October 28 dev10 packages have their own
[notice evidence](evidence/dev10-linux-notices.json), collected from their retained
Ubuntu 22.04 builder with all three package hashes checked against the local
artifacts. All 526 dependency entries have notice files. Of 175 AppImage ELF
files, 171 match distribution providers by build ID and text/rodata fingerprints;
all matched providers have retained copyright notices. Two files are Bifang's
executables. Supplemental review explains the two strict-match exceptions:
`AppRun.wrapped` exactly matches Tauri's published `apprun-old` binary, and
WebKit's executable text is unchanged while all 156 changed read-only-data bytes
match the retained GTK plugin's `/usr` to `././` path rewrite. The matching Ubuntu
WebKit source version and copyright notice are retained. Embedded PyInstaller
contents have been listed; their full provenance, launcher notices and corresponding
source delivery remain release checks.

The dev10 sidecar also passes a separate [embedded-runtime audit](evidence/dev10-embedded-runtime.json):
33 ELF files extracted from its PyInstaller binary/data members require no GLIBC
version above 2.35. Linux CI now runs `scripts/check-sidecar-runtime.py` using the
build environment's Python for each package. This check complements the outer
payload audit; it does not verify runtime dependency resolution or licences.
The exact AppImage's `AppRun` and `AppRun.wrapped` both have mode 0755, allowing
execution by users other than their owner. No permissions patch was necessary.

A subsequent [embedded provenance check](evidence/dev10-embedded-provenance.json)
matched all 33 native members byte-for-byte to the retained PyInstaller build
inputs. Twenty-nine belong to five Python distributions; the other four are
CPython and Ubuntu's GCC, C++ and zlib runtimes. This establishes build-input
correspondence while component notice and corresponding-source review continues.

### Reproducible source export

Create a source candidate from actual working-tree bytes, including untracked
build-support modules, rather than relying on a potentially older Git index:

```bash
uv run --locked --no-dev python scripts/build-source-archive.py \
  --output /absolute/new-source.tar.gz
```

The exporter requires key desktop/companion build inputs, including Vite's
`desktop/dev/localWorkspaces.ts`. It omits private state, dependency installs and
generated binary directories, embeds a SHA-256 file manifest and normalizes
archive timestamps/ownership. Existing outputs are never replaced. Export twice
and compare to verify byte reproducibility for unchanged source. This does not
assert bit-reproducible native binaries. Review the selected source, media and
bounded secret-scan results before approving publication; an export is not
publication approval or proof that arbitrary source text contains no secrets.

### Linux package baseline

The native CI job now targets Ubuntu 22.04 and builds Debian, AppImage and RPM
packages. Build the desktop once with `--no-bundle`, then use
`uv run --locked --no-dev python scripts/bundle-linux.py` (add `--debug` for a
debug build). The wrapper gives each format a pristine compiled binary, restores
it afterwards even on failure, and refuses already-patched input. This avoids
reusing the wrong native bundle-type marker between formats.

For RPM only, the dev.9 package metadata maps `0.2.1-dev.9` to version `0.2.1`
and release `0.dev.9`. RPM verifies this sorts before `0.2.1-1`; the compiled
application keeps its original development version. This is a packaging override,
not a source-version change. Unsupported version shapes fail instead of being
silently rewritten.

RPM also declares the packaging host's glibc version as a conservative minimum.
Package on the selected baseline: a newer host can impose stricter requirements
than the two direct application ELFs alone reveal. This prevents an older RPM
system accepting a package whose broader native runtime has not been validated.

CI extracts each format and checks all included ELF files with
`scripts/check-linux-runtime.py --max-glibc 2.35`, then runs the extracted
helper's plugin, metrics and three setup-profile acceptance checks, plus
`scripts/check-sidecar-health.py` against each exact helper binary. The health
probe uses an empty temporary home, no private configuration and an ephemeral
loopback port, then checks owned-process/port cleanup. This is
configured source, not a completed remote CI run or distribution installation.

For an already extracted package or AppImage tree:

```bash
uv run --locked --no-dev python scripts/check-linux-runtime.py /absolute/payload \
  --max-glibc 2.35 --output /absolute/runtime-report.json
```

The report inventories each ELF's hash, direct dependencies and versioned runtime
requirements without executing the application. A passing ceiling does not
establish that all libraries resolve on a target distribution or that the GUI
works. Run installation/launch and relevant workflows on each supported target.

The October 25 host-built dev.9 Debian desktop directly requires glibc 2.39.
The AppImage staging audit additionally found bundled host WebKitGTK, JavaScriptCore,
GLib, libjxl and liborc requiring glibc 2.43. That host build must not be advertised
as an Ubuntu 22.04/24.04-compatible portable release. Rebuild in the selected older
baseline rather than bundling a newer libc or weakening the audit. See Tauri's
[AppImage baseline guidance](https://v2.tauri.app/distribute/appimage/#limitations)
and [RPM guidance](https://v2.tauri.app/distribute/rpm/#limitations).

A separate October 26 Ubuntu 22.04 **release-profile** build now produces all
three formats: 179 extracted ELF checks pass the 2.35 ceiling, all 45 helper
checks pass, and each exact-format service passes API health and cleanup.
[Package hashes and scope](evidence/linux-baseline-release.json) distinguish
this build from the earlier host debug candidates. AppImage changes its helper's
ELF fingerprint, so its API check is independent rather than inherited from
Debian. The exact Debian package also passes a [fresh Ubuntu 24.04.5
installation](evidence/linux-baseline-install.json): apt resolves its dependencies,
both installed ELF loaders resolve, eight plugin/workbench management checks pass,
and the installed service answers `/health` with owned-process/port cleanup.
The guest's global AppArmor user-namespace restriction remains enabled. This
install check does not rerun language installations or native-window workflows;
the builder's fifteen-per-format checks and older GUI evidence remain separate.
RPM target installation and AppImage target launch are still separate gates.

On Ubuntu 22.04, use `rpm2archive -n` for metadata-based extraction after default
`rpm --checksig` succeeds. Its older `rpm2cpio` can emit a valid payload but return
failure when the total archive-size header is absent; see the
[RPM 4.17 converter implementation](https://github.com/rpm-software-management/rpm/blob/rpm-4.17.0-release/rpm2cpio.c).
Do not discard that exit status or disable digest checks. CI uses the supported
extractor and retains its separate integrity result.

### Windows and macOS

Windows and macOS Rust code is not equivalent to a validated desktop build.
The manual `desktop-platforms` workflow now builds both the IDE and Companion
on Windows x64, macOS Intel, and macOS Apple Silicon runners. It uses locked
dependencies, native Python 3.11 sidecars, authenticated two-instance sidecar
checks, and a manifest requiring every requested installer from both apps.
Windows produces NSIS and MSI installers; macOS produces separate Intel/ARM
DMGs, not a relabelled universal binary. The workflow uploads CI artifacts;
it does not create a public release or use signing/provider credentials.

These workflow definitions and build-plan tests are not Windows/macOS execution
evidence. Run the workflow from the approved source snapshot, retain its artifacts
and checksums, then verify installation, startup, workspace selection, terminals,
remote pairing and model-driven work on each target. Local sandboxed setup remains
Linux-specific; never disable its checks to make another platform appear supported.
Signing, notarization, notices and installed workflow validation remain release gates.

`npm run build:server` uses the portable Python builder; native Python and Rust
architectures must match. [PyInstaller requires native platform builds](https://pyinstaller.org/en/stable/operating-mode.html),
and [Tauri requires target-suffixed sidecar names](https://v2.tauri.app/develop/sidecar/).
Runner labels are selected from [GitHub's runner image list](https://github.com/actions/runner-images).
## Preview 4 evidence and source roles

Preview 4's installer is `Bifang-engineering_0.2.0_amd64.deb`, SHA-256
`0282033adc7aa1fb55f1911a11ec60e31844e9f1ec6c840bc5b9ee10f82d87a9`.
It passes the installed-native engineering walkthrough on fresh Ubuntu 24.04;
see [the exact receipt](evidence/ubuntu-engineering-native.json).

Release assets distinguish the retained 363-file build-input snapshot from
the publication source, which adds post-build documentation, the native test
helper, and its evidence. Runtime/build-input file hashes are checked rather
than claiming a bit-identical rebuild. The source archive contains a manifest;
checksums, provenance and third-party notices accompany the unsigned package.
Earlier release evidence above retains its own artifact identities.
