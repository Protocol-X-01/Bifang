# Reproduce the native desktop demo

This opt-in Linux test makes real, billable Token Factory requests. It runs
the packaged app against synthetic code, not your current project. It does
not need administrator access once the runtime and test tools are available.

## Requirements

- A built Linux Bifang app, with its matching `bifang-server` beside it.
- Python 3.11 and the locked project environment (`uv sync --locked --extra dev`).
- Git, Xvfb, `xvfb-run`, and the platform's WebKitGTK runtime.
- `tauri-driver` and WebKitWebDriver; see the official
  [Tauri WebDriver setup](https://v2.tauri.app/develop/tests/webdriver/manual-setup/).
- Optional FFmpeg with X11 capture and libx264 for `--record`.
- A private Token Factory key, supplied through environment variables or a
  separate `--env-file`. The tool accepts only the Token Factory base URL.

From the repository root, choose a new output directory outside the source:

```bash
xvfb-run -a -s '-screen 0 1600x1000x24' \
  uv run python scripts/rehearse-desktop.py \
  --application /absolute/path/to/bifang-desktop \
  --native-driver /absolute/path/to/WebKitWebDriver \
  --output /tmp/bifang-desktop-evidence \
  --record
```

Use `--tauri-driver /absolute/path/to/tauri-driver` if it is not on PATH.
Never paste a key into a command, screenshot, or issue. An environment file is
read privately; only the required provider settings reach the app. The test
uses an isolated temporary home and a dedicated display. Do not record your
normal desktop or publish raw diagnostic logs without reviewing them.

## What it verifies

The baseline fails. The actual app opens the workspace through **Open by
path…**, visibly rejects relative paths, files, and missing directories,
then accepts the existing fixture directory. It submits the task, presents approval
dialogs, shows the generated diff and confirms applying it. The harness
approves only `receipts.py` writes and the exact
`python3 -m unittest -v check_receipts` command. Unexpected actions are denied
and stop the rehearsal. After applying, all five checks must pass in the
original checkout, only `receipts.py` may differ, and the checks must remain
byte-identical.

Output includes before/after check results, a patch, actual screenshots, an
evidence JSON file, and optionally a continuous `desktop-demo.mp4`. Inspect
all artifacts before publishing. A video is saved during capture even if a
later check fails; only a successful exit plus passing evidence establishes
a successful rehearsal. The recording has no voiceover or time compression.

Use `--preselect-workspace` only when reproducing older builds; that bypasses
workspace-dialog validation and is labeled in the report. By default,
workspace selection and approvals use actual automated UI clicks, and
Bubblewrap is disabled for this synthetic fixture. This is not proof of the
native folder chooser, sandbox isolation, hostile-repository safety,
clean-machine installation, general model quality, or inference performance.
