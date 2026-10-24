# Releasing

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
CI explicitly targets Ubuntu 24.04 rather than the moving `ubuntu-latest`
label. This defines the intended Linux build baseline; it does not replace
installed-package validation on that distribution.

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

## Other targets

Windows and macOS Rust code is not equivalent to a validated desktop build.
Use native CI runners and build the Python sidecar for each target triple
before claiming those installers are available. Signed binaries, SBOMs, and
provenance are follow-up release hardening.
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
