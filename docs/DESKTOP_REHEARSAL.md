# Reproduce the native desktop demo

This opt-in Linux test makes real, billable Token Factory requests. It runs
the packaged app against synthetic code, not your current project. It does
not need administrator access once the runtime and test tools are available.

## Requirements

- A built Linux Bifang app, with its matching `bifang-server` beside it.
- Python 3.11 and the locked project environment (`uv sync --locked --extra dev`).
- Git, Bubblewrap with functioning user namespaces, Xvfb, `xvfb-run`, and the
  platform's WebKitGTK runtime.
- `tauri-driver` and WebKitWebDriver; see the official
  [Tauri WebDriver setup](https://v2.tauri.app/develop/tests/webdriver/manual-setup/).
- Optional FFmpeg with X11 capture and libx264 for `--record`.
- A private Token Factory key, supplied through environment variables or a
  separate `--env-file`. Direct mode accepts only the Token Factory base URL.
  Alternatively, use `--relay-url https://approved-relay.example` together with
  `--judge-token-file /private/judge.json`. The JSON file must contain a strong
  `judge_token`; it must not contain the upstream provider key. Relay mode
  never loads `--env-file` or inherits the provider key from the environment.

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

The latest fresh-Ubuntu sandbox-repair rehearsal retained a 32.45-second raw
recording, rendered model receipts and a bright final success screenshot.
Its [evidence summary](evidence/ubuntu-sandbox-desktop.json) binds the exact
package and recording hashes. The guest denied Bubblewrap namespace setup;
no kernel controls were weakened, and the trusted fixture used explicit
opt-out. Do not turn that recording into a sandbox-safety claim. A finished
submission video still needs reviewed narration, disclosure of automated
approvals, and a separately approved public upload.

Use `--preselect-workspace` only when reproducing older builds; that bypasses
workspace-dialog validation and is labeled in the report. By default,
workspace selection and approvals use actual automated UI clicks.
Bubblewrap is now enabled by default, including independent final checks in a
read-only, network-isolated fixture environment. The app's own command sandbox
retains its existing network-sharing policy; do not claim network denial there.
`--no-command-sandbox` explicitly opts out for trusted synthetic fixtures in
an independently isolated disposable guest. Earlier recordings used that
configuration and are not retroactively sandbox proofs. This is not proof of the
native folder chooser, sandbox isolation, hostile-repository safety,
clean-machine installation, general model quality, or inference performance.
