# Bifang Terminal

Target: a separately installable, open-source Android terminal IDE with Bifang's
visual identity, local development tools, AI assistance and desktop-approved pairing.
Companion's existing terminal is the starting implementation. A dedicated application
and an independently bootstrapped package environment are separate deliverables.

## Standalone Android preview

The native-shell preview has package identity `com.bifang.terminal` and application
label **Bifang Terminal**. It builds from the shared Companion sources and coexists
with both Companion and Termux. Its local Android PTY does not use the Termux bridge.
The independent package bootstrap and the remaining acceptance map below are still
required before claiming broad Termux capability parity.

With the documented Android SDK/NDK/Java environment, run inside `companion/`:

```sh
BIFANG_TERMINAL_EDITION=1 VITE_BIFANG_EDITION=terminal RUSTUP_TOOLCHAIN=stable npm run tauri -- android build --debug --apk --ci --target aarch64
```

The Gradle build selects the package identity and label; Vite selects the terminal
interface. Both edition variables are needed. Without them, the existing Companion
edition is built. Build output paths are shared: freeze and hash each APK before
building another edition.

## Capability acceptance map

Every area needs source coverage and an installed-device check. A library's feature
list, a successful APK build or a shell startup does not by itself close a row.

| Area | Acceptance cases | Current evidence / remaining work |
| --- | --- | --- |
| Terminal core | PTYs, ANSI/VT sequences, 256/true color, alternate screen, cursor modes, resize and reflow | Real PTY input/resize/exit tested on Linux; xterm renderer integrated; Android visual cases need device review |
| Input | IME composition, paste, bracketed paste, hardware keyboards, Ctrl/Alt/Esc/Tab/arrows/function keys, shortcuts | Basic device keyboard reported working; key strip exists; exhaustive IME and keyboard matrix remains |
| Text | Unicode graphemes, combining marks, CJK widths, emoji, RTL selection, ligatures/font sizing | Renderer integrated; physical rendering and selection matrix remains |
| Sessions | Create/name/switch/close sessions, independent scrollback, exit status, job control, child cleanup | Current distribution runtime permits one session; multiple sessions and session navigation remain |
| Output | Scrollback, selectable/copyable output, wrapped lines, search, links, clipboard policy | Selected-output handoff and wrapped-line tests pass; search and full clipboard/link review remain |
| Rootless runtime | Own writable prefix, bootstrap integrity, Android execution restrictions, package ABI, recovery | Android system shell exists; independent packaged toolchain/bootstrap remains |
| Packages | Package catalogue, install/update/remove, repository configuration, signature verification, interrupted install recovery | Existing distribution manager integration; independent app package environment remains |
| Development | Shells, Python/JS/Rust/C/C++ toolchains, Git, editors, build systems, debuggers and native libraries | Must verify representative install/build/run/debug workflows in the packaged environment |
| Files | Private home, working directories, shared storage via user grants, file picker, import/export, permissions, symlinks | Private project directory exists; broader storage UX and standalone home remain |
| Network | DNS, IPv4/IPv6, HTTPS, SSH/SFTP/SCP, port forwarding, loopback servers, reconnect | Must test in the local runtime; desktop network evidence does not establish phone behavior |
| Background work | Foreground service, notification controls, wake locks, screen-off jobs, Android process/battery limits | Dedicated terminal lifecycle remains; no unlimited-background guarantee |
| Distributions | Install/list/login/remove, distro package managers, download hashes, concurrent environments, recovery | Arch/Kali/BlackArch catalogue exists; physical rootfs login and maintenance cases remain |
| Graphics | X11/display connection, keyboard/pointer input, resize, native/GPU paths, software fallback | Device graphics correctness probe exists; graphical Linux application workflow remains |
| Android integration | Equivalent workflows for device APIs, notifications, intents, storage, clipboard, widgets, boot and automation | Needs explicit extension design and capability-by-capability review; not implied by a working terminal |
| Customization | Themes, contrast, fonts, key rows, touch gestures, accessibility, orientation, large text | Brand styling and responsive layout in source; accessibility and visual acceptance remain |
| AI | Selected context, model catalogue, local/remote distinction, reviewable edits, command approval, injection boundaries | Selected terminal-output handoff exists; complete terminal-first agent workflow remains |
| Pairing | Desktop approval plus Authenticator, revoke/reconnect, expiry, device isolation | Existing pairing foundation; dedicated Terminal APK acceptance remains |
| Data continuity | Backup/restore, app updates, migration, SSH key handling, uninstall warnings | Companion APK updates preserve data; standalone migration/backup flow remains |
| Delivery | Reproducible source/build inputs, notices, signed releases, upgrade path, current screenshots/demo | Source/build evidence tracked separately; dedicated Terminal release remains |

## Current Termux connection

The inspected Xiaomi APK `googleplay.2026.10.09` declares neither
`com.termux.permission.RUN_COMMAND` nor `RunCommandService`. Bifang detects this
capability rather than assuming that every app named Termux supports external commands.
The upstream command API requires both the permission and the Termux property:
[RUN_COMMAND documentation](https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent).

The manual connector copies a private Python startup command to the device clipboard.
The user starts it inside Termux, then connects from Bifang. It reuses the authenticated
loopback protocol, checks both peers' proofs, and clears Bifang's copied command after
connection. Runtime dependencies are installed inside Termux by the user. This path
preserves the existing Termux installation and its SSH files; it is an interim runtime
connection, not the independently packaged Bifang Terminal runtime.

The owner reported that this connection and setup still failed on the phone.
Development has moved to the standalone terminal at the owner's request; the manual
connector's host protocol tests must not be represented as phone workflow acceptance.

## Upstream reference scope

Audit the main [Termux app](https://github.com/termux/termux-app),
[Termux packages](https://github.com/termux/termux-packages),
[Termux:API](https://github.com/termux/termux-api) and
[Termux:X11](https://github.com/termux/termux-x11) separately. Related boot,
widget, automation, styling and floating-terminal extensions must be accounted for
explicitly. Reusing upstream components also requires retaining their applicable
licences, notices and corresponding-source obligations.

## Visual direction

Slate surfaces, warm ember accents, restrained typography and clear terminal chrome.
Terminal output gets the space; environment selection, sessions and contextual actions
stay within reach. Motion should explain state changes and respect reduced motion.
Verify portrait, landscape, keyboard-open, large-text and screen-reader flows before
refreshing the published screenshots and demo.
