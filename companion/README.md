# Bifang Companion

Mobile-oriented Tauri shell for the **same** Remote forge interface, candidate
verification and native HTTPS transport as the desktop app. It registers only
remote commands: no local agent sidecar, shell, workspace reader or provider key.
Access is session-only; no token persistence or keychain/keystore integration is
implemented. This source project is not an Android APK or an iOS release.

The [host-only evidence](../docs/evidence/companion-host.json) records the current
frontend build, shared Rust tests and actual Linux WebKit shell at 390 pixels:
trusted HTTPS connection, reconnect and inspection of an existing applied job,
without another proposal or approval. The phone-width viewport had no document
horizontal overflow, button targets were at least 44 pixels tall, and inputs used
16-pixel text. These checks do not simulate a mobile OS, keyboard or hardware.

From the repository root:

```sh
npm --prefix desktop ci
npm --prefix companion ci
npm --prefix companion run build
```

Shared components deliberately stay in `desktop/src` and shared Rust transport in
`desktop/src-tauri/src/remote.rs`; maintain their tests there rather than forking
approval behavior. Build from the complete repository, not this folder alone.
Development UI uses port 1435. `TAURI_DEV_HOST` is respected for device development.

After installing the official [Tauri mobile prerequisites](https://v2.tauri.app/start/prerequisites/),
run the following **inside `companion/`** for the desired target:

```sh
npm run tauri -- android init
npm run tauri -- android dev
```

On a Mac with Xcode, use `ios init` and `ios dev` instead. These are setup
instructions, not evidence that either target has built here. Android platform,
NDK, Rust target, Java/Gradle compatibility, SDK licence acceptance and real
device/emulator checks remain prerequisites. iOS additionally requires the Mac
toolchain and appropriate signing for device distribution. Do not silently accept
licences, buy developer accounts or enable paid infrastructure to satisfy a build.

Acceptance still requires actual Android/iOS builds, device file-picker and
keyboard/rotation/background-reconnect tests, appropriate signing, secure optional
token persistence, and a mobile walkthrough of approval/check/review/Apply.
Responsive browser or Linux-shell checks do not establish these mobile gates.
