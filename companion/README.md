# Bifang Companion

Mobile-oriented Tauri shell for the **same** Remote forge interface, candidate
verification and native HTTPS transport as the desktop app. The Code tab connects
to the service; the Terminal tab opens a device shell in private app storage.
Access is session-only; no token persistence or keychain/keystore integration is
implemented. An ARM64 Android debug APK now builds and passes packaged signature,
manifest and 16 KiB alignment checks; see [exact artifact evidence](../docs/evidence/companion-android-build.json).
The exact APK also [installs and starts on an owner-offered Xiaomi 12T running
Android 15](../docs/evidence/companion-android-device.json); its installed bytes
match the verified candidate. The owner reports clean rendering, working keyboard
and orientation changes. The pairing-enabled APK has subsequently been installed
on that phone, and the AWS pairing routes have passed trusted HTTPS checks.
[Desktop-approved pairing with Authenticator](../docs/MOBILE_PAIRING.md) still
requires the owner's first successful phone connection and full hosted-workflow
verification. There is no iOS build or release yet.

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

## Device terminal

The app opens on **Terminal**, with an environment picker before shell launch.
Choose **Android system shell → Start device shell** to open an interactive terminal. Android
uses `/system/bin/sh` with its installed system tools; desktop companion builds
use the system shell. The native app chooses a persistent directory under its
own data storage. This directory is separate from projects on the remote service.
Switching back to Code keeps the remote workspace mounted and the shell available.

The terminal supports colour output, resizing, keyboard input, a command entry
field and touch buttons for Ctrl+C, Tab, Esc and arrow keys. Commands run with
the app's operating-system permissions. Shell startup profiles and provider-key
environment variables are skipped. Output is not sent to chat. Closing the shell
stops its process. **Select output** opens a text snapshot with Android selection
handles and the normal copy menu. Select a passage and use **Ask agent about
selection** to review it in Code before sending. Session labels and the prompt
use short folder names; expand **Full working path** when needed.

The distribution picker connects to a Termux runtime and installs Arch Linux ARM,
Kali NetHunter Minimal, or an Arch Linux ARM base with BlackArch's repository.
Interactive installation and login use the embedded Bifang terminal. The manager
is pinned to **PRoot-Distro v4.34.2** with reviewed SHA-256 hashes for its source,
licence, root filesystems and BlackArch bootstrap. The original manager source
and licence stay beside the locally configured copy in Termux storage.
Environments live under `~/.local/share/bifang-distros`, separate from existing
Termux distributions. Kali uses apt; Arch and BlackArch use pacman. Tool suites
are optional package installs. These catalogue entries currently target ARM64.

On Android, first install/open Termux and set `allow-external-apps=true` in
`~/.termux/termux.properties`, then run `termux-reload-settings`. In Bifang's
**Runtime setup**, use **Allow Termux connection**, **Install runtime tools**,
then **Connect runtime** after the package installation completes. Android owns
the permission prompt. Bifang uses Termux's documented RUN_COMMAND interface.

The local bridge authenticates both ends with fresh challenges and an ephemeral
native-held key. Only the native app can choose its loopback endpoint; the web
interface receives no key or port. It accepts catalogue and PTY actions, expires
after 90 seconds without an authenticated request, and closes its shell on exit.
PRoot environments share the Termux app's operating-system privileges and are
not a security boundary for hostile programs. Guest GPU libraries are a separate
capability from the companion's native GLES compute support.

Expand **Device compute → Check CPU and GPU** for an on-demand native check.
The offered Xiaomi 12T has passed an eight-worker CPU reference calculation and
a 256-value GLES compute/readback check on its Mali-G610 MC6; see the
[device evidence](../docs/evidence/companion-device-compute-20261026.json).
This measures correctness of the native helper, not model-inference speed or
GPU support inside a PRoot guest.

Host tests cover protocol authentication, replay rejection, real PTY I/O and
resizing, catalogue bounds and download checksum refusal. Android builds verify
the native bridge compiles. Distribution download/install/login on the phone
still require the owner's one-time Termux setup and device verification.
The terminal panel can scroll vertically in short landscape/keyboard viewports,
and its touch-key strip scrolls horizontally without widening the application.
Python, Node, compilers and a package manager are not bundled. An iOS local-shell
request reports that this feature requires Android or a desktop build. Shared
Linux PTY tests and Android compilation are separate from actual phone input,
keyboard, resizing and command-execution acceptance.

## Linux companion installation

The companion is a separate remote client, not the full desktop IDE. With the
Linux Tauri build prerequisites installed, build its Debian test package from
`companion/`:

```sh
npm run tauri -- build --debug --bundles deb --ci
sudo apt install './src-tauri/target/debug/bundle/deb/Bifang Companion_0.1.0_amd64.deb'
```

The package provides a Bifang Companion application-menu entry. Reinstalling a
new package updates the executable; uninstalling first is unnecessary. This is
a debug/test build, not a production release. Credentials remain session-only,
so reconnect after closing the application. A per-user extracted installation
is also possible but is not managed by the system package manager.

After installing the official [Tauri mobile prerequisites](https://v2.tauri.app/start/prerequisites/),
build the checked-in Android project **inside `companion/`**:

```sh
rustup target add --toolchain stable aarch64-linux-android
RUSTUP_TOOLCHAIN=stable npm run tauri -- android build --debug --apk --ci --target aarch64
```

Set `JAVA_HOME`, `ANDROID_HOME` and `NDK_HOME` for the selected installation in
your shell, not by changing an unrelated project's global Java settings. The
verified build uses Java 21, Rust 1.95.0, NDK 29.0.14206865, Android platform 37.0,
build-tools 37.0.0, Gradle 9.6.1 and Android Gradle Plugin 9.3.1. The wrapper's
distribution checksum is pinned; its bootstrap JAR was checked against Gradle's
published checksum. The source exporter preserves Android/Kotlin/Gradle inputs
and the wrapper while excluding local SDK paths, signing properties and build
outputs. It refuses an incomplete initialized Android project.

The APK targets API 37, requires API 24 or newer, and contains only ARM64 native
code. It uses Bifang's launcher artwork and disables application backup. It is
debuggable and signed with a local Android debug certificate, not a production
release. Its debug manifest permits cleartext traffic for development; the shared
native remote client independently accepts only HTTPS origins. The physical-device
installation/startup check does not establish keyboard, rotation, background
reconnect or full hosted-workflow behavior.

Use `android dev` for device development only after configuring the SDK and
authorizing the device. Avoid rerunning `android init` over this project without
reviewing changes: generated defaults can replace branding, backup settings and
the pinned wrapper configuration. On a Mac with Xcode, `ios init` and `ios dev`
remain setup instructions, not completed iOS evidence. iOS requires that toolchain
and appropriate signing for device distribution. SDK licence acceptance stays an
owner decision; do not silently accept licences, buy developer accounts or enable
paid infrastructure to satisfy a build.

Acceptance still requires actual Android/iOS builds, device file-picker and
keyboard/rotation/background-reconnect tests, appropriate signing, secure optional
token persistence, and a mobile walkthrough of approval/check/review/Apply.
Responsive browser or Linux-shell checks do not establish these mobile gates.
