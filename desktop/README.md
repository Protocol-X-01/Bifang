# Bifang Desktop

Bifang Desktop is the Tauri + React IDE for the Bifang coding-agent runtime.
Desktop builds bundle the Python `bifang-server` as a Tauri sidecar, so users
do not need to install Python or the CLI separately to run the desktop app.

## Prerequisites

- Python 3.11 (`>=3.11,<3.12`) and Git (build-time; Python is bundled)
- Node.js 20.19+, npm, and `uv`
- Rust stable 1.90+
- Tauri platform build prerequisites; on Ubuntu install
  `libwebkit2gtk-4.1-dev`, `build-essential`, `libssl-dev`, `libxdo-dev`,
  `libayatana-appindicator3-dev`, and `librsvg2-dev`

## Install and run

An unsigned [Linux prerelease](https://github.com/Protocol-X-01/bifang/releases/tag/v0.2.0-preview.4)
is available for testing on Ubuntu 24.04. Download the `.deb`, checksums, and
third-party notice archive together. Verify the checksum and install with
`sudo apt install ./Bifang-engineering_0.2.0_amd64.deb`.
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

- **Frontend**: React + TypeScript + Vite + Monaco Editor
- **Desktop shell**: Tauri 2, with packaged assets and a minimal dialog capability
- **Agent runtime**: local Python service communicating with the frontend over
  the loopback API
- **Model inference**: configured Nebius Token Factory or NVIDIA NIM endpoint
