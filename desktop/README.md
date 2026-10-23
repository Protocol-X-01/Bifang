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
