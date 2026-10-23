# Releasing

## Linux desktop test build

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
preview as a validated production release.

## Other targets

Windows and macOS Rust code is not equivalent to a validated desktop build.
Use native CI runners and build the Python sidecar for each target triple
before claiming those installers are available. Signed binaries, SBOMs, and
provenance are follow-up release hardening.
