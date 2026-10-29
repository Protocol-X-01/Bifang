# Developer workbench

Confirmed submission requirements, October 25, 2026. These extend the working
coding workflow rather than replacing it. The interface follows Ember Atelier:
one quiet working surface, keyboard access, readable receipts and progressive
disclosure of setup and system detail.

## Acceptance criteria

| Requirement | Delivery and verification |
|---|---|
| Plugins | Discover without importing repository code. Explicit user trust before loading; show origin, version and requested capabilities. Disable/remove and changed-content reapproval must work. Test that an untrusted repository cannot execute a plugin on open or chat. Native Python plugins are trusted host code, not sandboxed merely by their capability labels. |
| Languages and libraries | Distinguish editor highlighting, language-server support, runtime availability and dependency availability. Offer optional project profiles; no compulsory all-language bootstrap. Start with Python, JavaScript/TypeScript and Rust and make additional adapters explicit. |
| Native package-manager interface | Use established ecosystem managers behind Bifang's UI. Preview exact arguments, directory, network access and writes; preserve lockfile intent. Bind approval to reviewed manifest bytes, cancel execution, stream output and retain an exit receipt. Setup/build hooks require separate visible consent; never silently replace pnpm, yarn or bun with npm. |
| Embedded terminals | Real interactive PTY with resize, keyboard input, cancellation and lifecycle cleanup. Clearly distinguish the user's terminal from the agent's approved execution channel. Opening a project must not auto-run shell initialization from that repository. Verify the actual native window on each supported platform. |
| System information | Actual CPU, memory and disk measurements with sample time and unavailable states; optional GPU measurements where supported. Offer btop in an interactive terminal where installed. Keep hardware readings separate from model usage, latency and inference receipts. No automatic administrative elevation. |
| Desktop packages | Windows installer, macOS application/DMG, Linux AppImage and RPM alongside Debian. Build and verify on appropriate operating systems, retain checksums and install/launch evidence. Describe signing status accurately. A cross-compile or generated workflow alone is not a tested binary. |

Android and iOS companion builds remain separate requirements in
[Product expansion](PRODUCT_EXPANSION.md). A terminal on a phone must not imply
access to an unrestricted desktop host shell; remote execution stays bound to
the authenticated workspace and execution contract.

## Current implementation

The desktop sidebar offers **New workspace…** alongside opening existing folders.
Choose an existing parent directory and a new folder name; creation refuses
existing files or directories and opens the empty folder without running Git,
package managers or templates. The desktop uses its native filesystem bridge;
the local browser development server has a separate loopback-only workspace
bridge. See [Filespaces](FILESPACES.md) for access boundaries and storage.
Plain folders use direct
editing, not Git worktree isolation or Git patch export. Repository history and
an initial commit can be set up separately before using those Git features.

`bifang toolchains` performs read-only root manifest discovery and previews
bootstrap commands for uv, npm and Cargo. It skips symlinked manifest files,
does not parse or execute their contents and does not install packages. Other
JavaScript lock managers require selection rather than npm substitution.
Availability currently means the manager executable is on PATH, not a verified
runtime version or functioning dependency environment.

The newer [project setup workflow](PROJECT_SETUP.md) adds manifest-bound approval,
isolated locked npm, Python/uv and Rust/Cargo setup, streamed output, cancellation and saved exit
receipts in the CLI and F8 terminal workbench, with subsequent local desktop
review/install/cancel controls over a bounded native progress channel. Its private per-project cache
supports offline reinstallation after an approved network download. Dev.9 adds
Python wheel installation and Cargo fetching by default; dependency build code
requires separate approval. A fresh native-window acceptance walkthrough remains work.

`bifang boxes` lists existing isolated workspaces for the selected repository.
Use `--box ID` to resume, export a patch or explicitly discard one. Patch export
uses a temporary Git index so reviewing a patch does not stage the user's files.

Plugins now have [CLI trust and disable controls](PLUGINS.md), non-importing
manifest discovery, origin/content-bound trust and namespaced tool registration.
The local desktop Workbench now adds plugin review/enable/disable controls and
root-manifest language setup previews through a native stdio bridge. These
previews do not execute installation commands. Dev.8 also provides the
[F8 terminal workbench](TERMINAL.md#developer-workbench) for plugin controls,
language previews and explicit one-shot system measurements. The subsequent
Packages tab adds the three setup profiles above; further installer adapters
and extension distribution remain work.
The [desktop local terminal](EMBEDDED_TERMINAL.md) now has native PTY and bundled
renderer source, with actual Linux engine tests including installed btop.
Native-window, accessibility and packaged cross-platform walkthroughs remain
distinct acceptance gates. This is not an embedded Textual/mobile terminal yet.
[Forge pulse](SYSTEM_METRICS.md) in development version dev.8 adds actual local
CPU, memory and workspace filesystem readings; model receipts remain separate.
The Ubuntu Debian installer is
the verified desktop format; the additional platform packages remain required.
New local development changes are not included in Preview 6 or the previously
frozen terminal wheel unless a new artifact is built and verified.

## Platform choices

Use [Tauri's distribution formats](https://v2.tauri.app/distribute/) for the
existing desktop shell rather than creating a second packaging stack. Native
build, signing and fresh-install checks are independent acceptance steps.

Use [btop](https://github.com/aristocratos/btop) where supported and installed.
The separate [btop4win port](https://github.com/aristocratos/btop4win) provides
a non-administrative Windows option with fewer sensor capabilities; do not
promise its basic build provides GPU or CPU-temperature readings. A first-party
metrics panel should remain usable when btop is absent.

Respect [uv's lockfile synchronization behavior](https://docs.astral.sh/uv/concepts/projects/sync/)
and each package manager's lockfile rules. Fetching dependencies, executing
dependency build code and applying source changes are different operations and
must remain distinguishable in the interface and receipts.
