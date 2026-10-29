# Bifang Desktop

Bifang Desktop is the Tauri + React IDE for the Bifang coding-agent runtime.
Desktop builds bundle the Python `bifang-server` as a Tauri sidecar, so users
do not need to install Python or the CLI separately to run the desktop app.

## Local connection

Current source starts each native instance on its own OS-assigned loopback port,
with a fresh API token held only for that server lifetime. The sidecar announces
readiness to the native host; only the trusted main window can request its
connection details. Requests cannot follow redirects, and native startup failures
never fall back to a different service on port 8000. Restarting obtains a new
connection. No provider credential is used as the local API token.

The standalone CLI and browser-only development keep their explicit/default
port configuration (8000 by default). These source changes require rebuilding
both the native application and its sidecar; existing releases are unchanged.

## Prerequisites

- Python 3.11 (`>=3.11,<3.12`) and Git (build-time; Python is bundled)
- Node.js 20.19+, npm, and `uv`
- Rust stable 1.90+
- Tauri platform build prerequisites; on Ubuntu install
  `libwebkit2gtk-4.1-dev`, `build-essential`, `libssl-dev`, `libxdo-dev`,
  `libayatana-appindicator3-dev`, and `librsvg2-dev`

The portable sidecar builder runs through `uv` with Python 3.11. `PYTHON_BIN`
can explicitly select another Python 3.11 interpreter. It checks both Python
version and native OS/architecture against Rust before installing locked build
dependencies. Windows uses `Scripts/python.exe`; Unix uses `bin/python`.
A managed Python installation does not need to be added to PATH. The existing
shell entrypoint delegates to this same builder; npm no longer requires Bash.

## Install and run

An unsigned [Linux prerelease](https://github.com/Protocol-X-01/bifang/releases/tag/v0.2.1-preview.6)
is available for testing on Ubuntu 24.04. Download the `.deb`, checksums, and
third-party notice archive together. Verify the checksum and install with
`sudo apt install './Bifang-forge_0.2.1.preview.6_amd64.deb'`.
Configure your provider below, then launch Bifang from the application menu.
Choose a project with the native folder button or **Open by path…**. The path
dialog accepts existing absolute directories and validates them without
running a shell command. Native chooser automation is still unverified;
the path dialog and coding loop pass in a clean Ubuntu VM.

Preview 4 includes read-only team review and an isolated implementer with
independent checks and reviewed staging. Its exact installer passes the native
Ubuntu walkthrough through the separate original Apply confirmation. See the
[engineering guide](../docs/ENGINEERING_WORKFLOW.md) and
[exact-package evidence](../docs/evidence/ubuntu-engineering-native.json).

Preview 5 adds [visual review](../docs/VISION.md). Its new installer separately
passes both native image review and the coding/check/stage/Apply regression;
see the [Preview 5 coding receipt](../docs/evidence/ubuntu-preview5-engineering.json).

Preview 6 adds the native remote forge: selectively share files, independently
verify candidate hashes, reconnect to durable tasks, and review hosted checks
and Apply decisions. Its exact package passes fresh Ubuntu coding and vision
checks plus a separate real Token Factory remote workflow. See the
[Preview 6 evidence](../docs/evidence/preview6-candidate.json).

Before running agent commands on Ubuntu 24.04, follow the
[Bubblewrap prerequisite and scoped AppArmor setup](../docs/UBUNTU_SANDBOX.md).
An installed executable alone does not establish that namespaces are allowed.
The documented setup keeps Ubuntu's global namespace restriction enabled.

For a desktop-launched app, store provider settings in the per-user app config
directory as `.env` (on Linux, typically
`${XDG_CONFIG_HOME:-~/.config}/com.bifang.desktop/.env`). Copy the root
`.env.example` there, add your own provider key, and restrict the file to your
user (`chmod 600 ...` on Unix). The app points the server at this file; never
put live credentials in the project checkout or a public demo video.

Then build and launch the desktop app:

```bash
cd desktop
npm ci
npm run tauri:dev
```

For a Linux Debian package (Python 3.11, Rust, Node, and `uv` are required only
while building; the resulting app includes the Python service sidecar):

```bash
npm run tauri:build -- --bundles deb
```

The service binds to loopback for the desktop app. Do not expose it on a
network without configuring server API-key authentication. The standalone CLI
remains separately installable with `pipx install .`.

## Architecture

Local development adds **New workspace…**, the **Workbench** plugin review and
language setup panels, and a confirmed **Local terminal** with native PTY support.
The newer **Dependency setup** panel adds exact-plan approval, streamed progress,
cancellation and saved receipts for supported locked npm, Python/uv and Rust/Cargo
projects on Linux. Dependency build code requires separate approval; Python's
root project is not installed. See [Project setup](../docs/PROJECT_SETUP.md).
See [Developer workbench](../docs/DEVELOPER_WORKBENCH.md),
[Filespaces](../docs/FILESPACES.md), [Plugins](../docs/PLUGINS.md) and
[Embedded terminal](../docs/EMBEDDED_TERMINAL.md).
These changes are newer than the published Preview 6 installer. Local debug
package and helper checks are separate from a fresh native-window walkthrough.

- **Frontend**: React + TypeScript + Vite + Monaco Editor
- **Desktop shell**: Tauri 2, with packaged assets and a minimal dialog capability
- **Agent runtime**: local Python service communicating with the frontend over
  the loopback API
- **Model inference**: configured Nebius Token Factory or NVIDIA NIM endpoint
