<p align="center">
  <img src="docs/assets/bifang-hero.svg" width="1280" alt="Bifang — Build. Run. Verify. A Nemotron coding workspace with disposable worktrees, approvals and diffs." />
</p>

<p align="center"><strong>Give the agent a failing test. Keep control of the change.</strong><br>A coding workspace for your desktop, terminal and Android device.</p>

<p align="center">
  <a href="https://github.com/Protocol-X-01/Bifang/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-E63946?style=flat-square" alt="Apache 2.0 license" /></a>
  <img src="https://img.shields.io/badge/Python-3.11-0F172A?style=flat-square" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/Track-01%20Agentic%20Engineering-FF8A3D?style=flat-square" alt="Track 1: Agentic Engineering" />
  <a href="https://github.com/Protocol-X-01/Bifang/actions/workflows/ci.yml"><img src="https://github.com/Protocol-X-01/Bifang/actions/workflows/ci.yml/badge.svg" alt="CI workflow status" /></a>
  <a href="https://github.com/Protocol-X-01/Bifang/actions/workflows/desktop-platforms.yml"><img src="https://github.com/Protocol-X-01/Bifang/actions/workflows/desktop-platforms.yml/badge.svg" alt="Desktop package workflow status" /></a>
</p>

<p align="center"><a href="#one-workspace-three-ways-in">Explore Bifang</a> · <a href="#see-the-coding-loop">Coding walkthrough</a> · <a href="#quickstart">Get started</a> · <a href="docs/ARCHITECTURE.md">Architecture</a> · <a href="docs/HACKATHON_READINESS.md">Build status</a></p>

## Watch Bifang in Action

https://github.com/Protocol-X-01/Bifang/assets/assets/v0.2.1-dev.11-refresh.20261029/Bifang-narrated-demo.mp4

**From failing checks to reviewed patch:** Watch Nemotron Ultra fix a broken receipt parser through Bifang's tools. The agent proposes edits, you approve actions, run independent checks, review the diff, and control when to apply. All five original tests pass after the fix.

<details>
<summary><strong>📹 Video details and evidence</strong></summary>

**Duration:** 2 minutes 50 seconds  
**Task:** Fix CSV quoted-comma handling in receipt parser  
**Model:** NVIDIA Nemotron Ultra on Nebius Token Factory  
**Tokens:** 12,252 across 5 live inference calls  
**Outcome:** All 5 original checks pass, parser fixed  

**Evidence:** [`evidence/native-vercel-relay.json`](evidence/native-vercel-relay.json) · [`docs/DEMO_EVIDENCE.md`](docs/DEMO_EVIDENCE.md)

</details>

## Impact: Why Bifang Exists

**Problem:** AI coding agents move fast, but their changes can break production. Engineers need visibility, control, and evidence—not just a finished solution.

**Solution:** Bifang makes every agent action reviewable:
- **Understand:** Map repositories, explore context, share screenshots
- **Approve:** Review every edit, command, and tool invocation
- **Verify:** Run checks in isolated worktrees, inspect diffs
- **Control:** Apply or discard with one click

**Built for:** Teams who need audit trails, engineers who review before merging, and projects where "just let the AI fix it" isn't enough.

## Downloads

**Latest Release (v0.2.1-dev.11):** [Debian, AppImage + Android APK](https://github.com/Protocol-X-01/Bifang/releases/tag/v0.2.1-dev.11-refresh.20261029)

| Platform | Format | Size | Status |
|----------|--------|------|--------|
| Linux | `.deb`, `.AppImage` | 34-108 MB | ✅ Tested on Ubuntu 22.04/24.04 |
| Android | `.apk` (ARM64) | 152 MB | ✅ Tested on Xiaomi 12T (Android 15) |
| Windows/macOS | Source | — | Build on demand (native required) |

Install CLI globally on any Python 3.11 system:

```bash
pipx install git+https://github.com/Protocol-X-01/Bifang.git@v0.2.1-dev.11-refresh.20261029
# or from source:
git clone https://github.com/Protocol-X-01/Bifang.git
cd Bifang && pipx install --python python3.11 .
```

**Quick start:**
```bash
export NEBIUS_API_KEY='your-key-here'
bifang doctor && bifang sandbox-check
cd your-project && bifang chat
```

## One workspace, three ways in

| Desktop IDE | Terminal | Android Companion |
| --- | --- | --- |
| Explore a project, discuss a change, inspect its diff and run checks from one workbench. | Work from the command line or the Rust TUI, with Bifang's ember-and-slate identity. | Pair with your desktop, use remote coding and open a terminal on your device. |
| [Desktop guide](desktop/README.md) | [CLI guide](docs/TERMINAL.md) · [Rust TUI](tui/) | [Companion guide](companion/README.md) · [Pairing](docs/MOBILE_PAIRING.md) |

**Context that helps you code.** Bring screenshots into a conversation with an
image-capable model, discover indexed tools through [The Toolbox](docs/THE_TOOLBOX.md),
and keep useful project knowledge in [local memory](docs/MEMORY_RETRIEVAL.md).

| Understand | Change | Verify |
| --- | --- | --- |
| Inspect files and repository context. | Approve edits in a disposable Git worktree. | Run checks, review the diff, then apply or discard. |

### Choose your pace

The desktop **Approvals** selector is separate from automatic model routing:

| Mode | Workflow |
| --- | --- |
| Off · manual review | Review edits, commands and external tool requests. |
| Auto · workspace edits | Ordinary source edits in disposable worktrees proceed automatically; commands, sensitive files and external tools ask. |
| Full tool approval | Explicit opt-in lets enabled tools proceed without repeated approval dialogs. |

The active level stays visible. New chats, workspace changes, restored conversations and page reloads return to manual review. Final **Apply** remains a separate confirmation. See [approval modes](docs/APPROVAL_MODES.md).

### From parallel review to a checked patch

Open **Read-only team review** for bounded investigator and reviewer workers, with file-backed observations. Use **Isolated engineering** when you want an implementer to prepare a change from explicitly selected files:

**Select files → approve writes → execute an independent check → review the patch → stage → Apply.**

The check receipt records the exact command, snapshot hash and exit status. Staging keeps the original checkout untouched until you choose Apply. [Follow the engineering walkthrough](docs/ENGINEERING_WORKFLOW.md).

Optional [Tavily web search and LangSmith tracing](docs/ENGINEERING_WORKFLOW.md#web-and-observability) complement the coding loop. The Ember terminal adapts to smaller windows with keyboard-accessible inspectors.

Built for **Track 1 · Coding and Agentic Engineering** at the Nebius × NVIDIA Global AI Hackathon.

## See the coding loop

The [receipt-parser demo](docs/DEMO.md) starts with two broken CSV cases. Nemotron Ultra fixes the parser through Bifang's tools, leaving the original checks intact. The release-profile desktop app completed the live task, approval dialogs, diff review, and patch application. All five original checks passed in the source checkout afterward.

<details>
<summary><strong>Earlier desktop screenshots · coding, approvals and visual review</strong></summary>

These captures document the earlier desktop interface. The current source uses
the refreshed ember-and-slate design across the apps.

![Earlier Bifang desktop after a real Nemotron coding task: repository files, reviewed diff and successful apply.](docs/assets/bifang-desktop.png)

![Earlier Bifang approval dialog with the proposed action, Deny and Allow once controls.](docs/assets/bifang-approval.png)

Approvals are scoped to one action. The demo harness clicked these actual controls using an exact-action allowlist.

![Preview 6 visual review using synthetic inference and explicit chat handoff.](docs/assets/bifang-vision-native.png)

[Visual context guide](docs/VISION.md) · [Recorded demo evidence](docs/DEMO_EVIDENCE.md)

</details>

The [coding walkthrough](docs/DEMO.md) shows the task and checks used for the
recorded loop. [Build status](docs/HACKATHON_READINESS.md) keeps package versions,
test results and delivery evidence together, including
[fresh Ubuntu installation](docs/INSTALLATION_EVIDENCE.md).

<p align="center"><img src="docs/assets/bifang-workflow.svg" alt="Bifang's coding loop: inspect, reason, review, verify and decide." /></p>

## Quickstart

- Python 3.11 (the supported range is `>=3.11,<3.12`)
- Git for isolated worktrees; Bubblewrap for the default Linux command sandbox
- A Nebius Token Factory API key, or an OpenAI-compatible NVIDIA NIM endpoint
- Building the desktop app additionally requires Rust 1.90+, Node.js 20.19+, `uv`, and the platform's Tauri system dependencies

On Ubuntu 24.04, check the [Bubblewrap/AppArmor prerequisite](docs/UBUNTU_SANDBOX.md) before agent commands. The scoped setup keeps global namespace restrictions enabled.

```bash
sudo apt update
sudo apt install -y pipx git ripgrep bubblewrap
pipx ensurepath
git clone https://github.com/Protocol-X-01/Bifang.git
cd Bifang
pipx install --python python3.11 .
```

Configure your provider, then open a project:

```bash
export NEBIUS_API_KEY='...'
bifang doctor
bifang sandbox-check
cd your-project
bifang chat
```

For development, from the cloned repository:

```bash
uv sync --locked --extra dev --extra observability
```

To run the desktop IDE in development (its build script provisions a separate locked Python environment for the bundled service):

```bash
cd desktop
npm ci
npm run tauri:dev
```

The desktop shell requires Python 3.11, Rust 1.90+, Node.js 20.19+, and the platform's Tauri build dependencies. Its build packages `bifang-server` as a sidecar; users do not need Python installed to run the packaged app. See [`desktop/README.md`](desktop/README.md) for configuration and Linux packaging.

## Why this build

The Bifang bird identity represents watchfulness and controlled fire: the agent moves the work forward while the engineer can inspect what changed. The engineering focus is a complete coding loop with visible evidence.

NVIDIA Nemotron models on Nebius Token Factory power the iterative edit/test loop. Visible model receipts, explicit action approvals and reviewable diffs help the engineer follow the work from the first failing check to the final patch. An OpenAI-compatible NIM endpoint is also available as a provider option.

The desktop brings together [visual review](docs/VISION.md), explicit image
sharing, model receipts and a handoff into coding chat. [Remote forge](docs/REMOTE_CODING.md)
adds selected-source tasks, isolated checks, reviewed patches and a separate Apply.
The [Android Companion](companion/README.md) has been built and installed on a
Xiaomi 12T running Android 15, with desktop-approved pairing and a device terminal.
The [Rust TUI](tui/) brings the refreshed design into the terminal. The published
Preview 6 installer and newer development clients have separate delivery records
in [product expansion](docs/PRODUCT_EXPANSION.md).

## Configure

Persistent [project memory](docs/MEMORY_RETRIEVAL.md) uses local ranked text retrieval by default in the development version. Provider embeddings are explicitly opt-in and use a separate embedding model, not the chat model. [Conversation history](docs/CONVERSATION_HISTORY.md) additionally supports durable API/terminal sessions and explicit resume; the desktop includes a history picker.

```bash
export NEBIUS_API_KEY='...'
export BIFANG_DEFAULT_PROVIDER='nebius'
export BIFANG_NEBIUS_BASE_URL='https://api.tokenfactory.nebius.com/v1'
export BIFANG_NEBIUS_MODEL='nvidia/Nemotron-3-Ultra-550b-a55b'
```

For an NVIDIA NIM deployment instead:

```bash
export NVIDIA_API_KEY='...'
export BIFANG_DEFAULT_PROVIDER='nvidia'
export BIFANG_NVIDIA_BASE_URL='http://localhost:8000/v1'
export BIFANG_NVIDIA_MODEL='<model-served-by-your-NIM>'
```

For NIM, point the NVIDIA-compatible provider at the OpenAI-compatible NIM endpoint and use the model name configured by that deployment. NGC credentials are needed to pull licensed NVIDIA containers; they are not inference API keys. The app does not deploy NIM or provision GPUs by itself.

Use `bifang models` to inspect the live model catalog rather than relying on a hard-coded model ID.

## Use

Try the [repeatable receipt-parser demo](docs/DEMO.md) to rehearse the inspect → approve → edit → test → apply loop on synthetic code.

```bash
cd your-project
bifang doctor
bifang chat
```

Inside chat:

```text
Find the failing parser test, determine the root cause, make the smallest reasonable fix, and verify it.
```

Commands:

```text
/help /status /diff /quit
```

Other CLI operations:

```bash
bifang toolchains
bifang plugins list
bifang boxes
bifang --box BOX_ID run -- pytest -q
bifang --box BOX_ID patch > bifang.patch
bifang --box BOX_ID discard
bifang --version
```

Replace `BOX_ID` with the eight-character ID from `bifang boxes`, run from the original project checkout. Patch export preserves the Git index. Discard asks for confirmation and removes only the selected isolated workspace. Toolchain discovery previews optional Python, JavaScript/TypeScript and Rust setup without installing packages. See [Developer workbench](docs/DEVELOPER_WORKBENCH.md) for the required plugin, package-manager, terminal and platform delivery work.

## Safety model

- disposable Git worktree by default;
- filesystem tools confined to the Bifang workspace;
- typed model tools, validated before use;
- read-only observation plus manual, workspace-edit auto and full tool-approval levels;
- approval required for mutation and execution in `assist` mode;
- destructive patterns blocked in every mode;
- environment allowlist, timeout, and output cap;
- JSONL audit transcript under `.bifang/sessions`.

Bifang is defense in depth, not a formally verified security boundary. Bubblewrap support is included for Linux command isolation, but kernel policy may disable unprivileged user namespaces. Use disposable VMs for hostile repositories.

## Development

```bash
uv run python -m compileall -q src
uv run ruff check src/bifang/workspace.py src/bifang/tracing/phoenix.py tests/test_workspace.py tests/test_config_env.py tests/test_ngc.py tests/test_phoenix_tracing.py tests/test_server_auth.py
uv run pytest -q
./scripts/build-linux.sh
```

Current local source supports [isolated folder workspaces](docs/FOLDER_WORKSPACES.md) for projects without Git or a first commit, with patch-bound review and Apply. These changes are not yet included in the published installer.

See `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/RELEASING.md`, and `docs/DEPLOYMENT.md`. Hackathon deliverables and remaining gates are tracked in `docs/HACKATHON_READINESS.md`.
