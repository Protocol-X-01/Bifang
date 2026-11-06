<p align="center">
  <img src="docs/assets/bifang-hero.svg" width="1280" alt="Bifang — Build. Run. Verify. A Nemotron coding workspace with disposable worktrees, approvals and diffs." />
</p>

<p align="center"><strong>Give the agent a failing test. Keep control of the change.</strong><br>A coding workspace for your desktop, terminal and Android device.</p>

<p align="center">
  <a href="https://github.com/Protocol-X-01/Bifang/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-E63946?style=flat-square" alt="Apache 2.0 license" /></a>
  <img src="https://img.shields.io/badge/Python-3.11-0F172A?style=flat-square" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/Track-01%20Agentic%20Engineering-FF8A3D?style=flat-square" alt="Track 1: Agentic Engineering" />
  <a href="https://tavily.com"><img src="https://img.shields.io/badge/Built%20with-Tavily-blue?style=flat-square" alt="Built with Tavily" /></a>
  <a href="https://github.com/Protocol-X-01/Bifang/actions/workflows/ci.yml"><img src="https://github.com/Protocol-X-01/Bifang/actions/workflows/ci.yml/badge.svg" alt="CI workflow status" /></a>
  <a href="https://github.com/Protocol-X-01/Bifang/actions/workflows/desktop-platforms.yml"><img src="https://github.com/Protocol-X-01/Bifang/actions/workflows/desktop-platforms.yml/badge.svg" alt="Desktop package workflow status" /></a>
</p>

<p align="center"><a href="#one-workspace-three-ways-in">Explore Bifang</a> · <a href="#see-the-coding-loop">Coding walkthrough</a> · <a href="#quickstart">Get started</a> · <a href="docs/ARCHITECTURE.md">Architecture</a> · <a href="docs/HACKATHON_READINESS.md">Build status</a></p>

[Try the public coding-model demo](https://bifang-judge-relay.vercel.app) — choose Nano, Super or Ultra without an account or API key. Download the IDE for workspace tools, checks and patch review. [Live access check](docs/evidence/vercel-public-demo-fair-use-20261106.json).

## Watch Bifang in Action

[Watch the refreshed coding demo on YouTube · 2 min 45 sec](https://www.youtube.com/watch?v=Eg8Gcyj5ORM)

<p align="center"><a href="https://www.youtube.com/watch?v=Eg8Gcyj5ORM"><img src="docs/assets/bifang-desktop-ide.png" width="1100" alt="Bifang IDE v0.3.2 — open a workspace, choose a model and review a change. Watch the narrated coding demo." /></a></p>

**From failing checks to reviewed patch:** Watch Nemotron Ultra fix a broken receipt parser through Bifang's tools. The agent proposes edits, you approve actions, run independent checks, review the diff, and control when to apply. All five original tests pass after the fix.

<details>
<summary><strong>Short TUI clip and runtime evidence</strong></summary>

[Watch the 45-second terminal clip](https://github.com/Protocol-X-01/Bifang/releases/download/v0.3.1/bifang-live-demo.mp4)

**Duration:** 45 seconds  
**Task:** Fix CSV quoted-comma handling in receipt parser  
**Model:** NVIDIA Nemotron Ultra on Nebius Token Factory  
**Flow:** failing baseline → agent fix proposed in the TUI → write/command approvals → live diff → apply → all 5 checks pass  
**Outcome:** All 5 original checks pass, parser fixed  

**Runtime evidence:** [Native desktop task](docs/evidence/native-vercel-relay.json) · [Clip and build notes](docs/DEMO_EVIDENCE.md)

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

**Latest published release (v0.3.2):** [Linux desktop packages, Android companion APK, TUI and checksums](https://github.com/Protocol-X-01/Bifang/releases/tag/v0.3.2)

| Platform | Format | Size | Status |
|----------|--------|------|--------|
| Linux desktop | `.deb`, `.rpm`, `.AppImage` | 56-160 MB | v0.3.2; extracted payload audit ceiling: GLIBC 2.35 |
| Android companion | `.apk` (ARM64) | 51 MB | v0.3.1; tested on Xiaomi 12T (Android 15) |
| Terminal | `bifang-tui` (Linux x86_64) | 4.8 MB | v0.3.2 |
| Windows | `.exe`, `.msi` (x64) | 3-46 MB | Desktop v0.3.2 and Companion v0.3.1 installers in the release |
| macOS | `.dmg` (Intel x64, Apple Silicon arm64) | 4-40 MB | Desktop v0.3.2 and Companion v0.3.1 installers in the release |
| iOS companion | Unsigned `.xcarchive` (arm64) | — | [Build artifact](https://github.com/Protocol-X-01/Bifang/actions/runs/41562890458); Apple signing required for installation |

Install CLI globally on any Python 3.11 system:

```bash
pipx install git+https://github.com/Protocol-X-01/Bifang.git@v0.3.2
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

## Brand and press kit

[Download the Bifang brand pack](https://github.com/Protocol-X-01/Bifang/releases/tag/brand-pack-2026-11-06) for editable logos, transparent PNGs, video thumbnails, social artwork, and native iPhone/iPad and Android icon sets. Phone and tablet covers share the same ember-and-slate identity. [Preview the pack and choose an asset](docs/BRAND_ASSETS.md).

## 🔍 Web Intelligence with Tavily

**Real-time web search and extraction** powered by [Tavily](https://tavily.com)

| Capability | Tool | Limits | Verified |
|------------|------|-------|----------|
| **Web Search** | `web_search` | 400-char queries, 8 results max | ✅ Live |
| **Page Extraction** | `web_extract` | Public HTTPS only, 12K chars max | ✅ Live |

**Features:**
- ✅ Content hashing for verification
- ✅ Untrusted-data labeling  
- ✅ HTTPS-only URL filtering
- ✅ Timeout and size limits
- ✅ No credential exposure
- ✅ 83 test suite passing

**Evidence:** [Live Tavily extraction proof](docs/evidence/tavily-extract-20261028.json) — Python asyncio docs extracted (5,944 chars)

Tavily search and extraction are optional. See the [integration guide](docs/TAVILY.md) and its [live extraction evidence](docs/evidence/tavily-extract-20261028.json).

## Safety features

The coding loop combines visible approvals, reviewable changes and host-level isolation:

| Layer | Technology | Purpose | Verification |
|-------|------------|---------|--------------|
| **Action review** | Approval modes | Choose manual review or opt-in automation levels; inspect the patch before Apply | Desktop, CLI and TUI flows |
| **Linux command isolation** | Bubblewrap | Run eligible commands with scoped filesystem and network access | Depends on host namespace policy; see [Ubuntu setup](docs/UBUNTU_SANDBOX.md) |
| **Local checks** | Command, path and text validation | Flag selected risky commands and common sensitive-text patterns | [Guardrail tests](tests/test_guardrails.py) |
| **MCP tools** | Local stdio servers | Connect reviewed local tool servers such as [The Toolbox](docs/THE_TOOLBOX.md) | Explicit server configuration and tool approval |
| **Tracing** | Phoenix or LangSmith | Export allowlisted operational metadata when configured | [Configuration guide](docs/ENGINEERING_WORKFLOW.md#web-and-observability) |

The text checks are pattern-based. For untrusted repositories, use the supported
host sandbox and review each proposed change; the checks do not replace OS
isolation.

```python
from bifang.guardrails import validate_command_safety, filter_pii

# Validate before execution
safe, msg = validate_command_safety(["sudo", "rm", "-rf", "/"])
assert not safe  # Blocked!

# Filter outputs
filtered, warnings = filter_pii("Email: user@example.com")
assert "[EMAIL]" in filtered
```

The [Toolbox guide](docs/THE_TOOLBOX.md) records a real local MCP round trip with
Nemotron Nano and an indexed inventory. The recorded count is tied to that
October 29 scan and is not presented as a current machine inventory.

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
<summary><strong>More screenshots · terminal, checks and companion</strong></summary>

These captures show Bifang across the desktop, terminal and Android companion.
The desktop image is from v0.3.2; the other screenshots show their recorded
coding, approval and terminal workflows.

![Bifang TUI — chat turn with a live diff and connected status line.](docs/assets/bifang-tui-chat.png)

![Bifang TUI — permission dialog for writes and commands, one action at a time.](docs/assets/bifang-tui-approval.png)

![The demo's five checks passing in the original checkout after Apply.](docs/assets/bifang-tests-passing.png)

![Baseline before Bifang: two broken CSV cases and failing checks.](docs/assets/bifang-baseline-fail.png)

<p align="center"><img src="docs/assets/bifang-companion-mobile.png" width="360" alt="Bifang companion on Android — terminal, distributions and theme picker." /></p>

![Visual review preview using synthetic inference and explicit chat handoff.](docs/assets/bifang-vision-native.png)

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
The [Rust TUI](tui/) brings the refreshed design into the terminal. The TUI
expects a `bifang-server` on `BIFANG_TUI_SERVER` (default
`http://127.0.0.1:8000`); when nothing answers there, it starts the server
itself from `BIFANG_TUI_SERVER_BINARY`, a `bifang-server` next to the TUI
executable, or `bifang-server` on PATH, reusing it on later launches. The
desktop app spawns its private sidecar automatically; both keep working
without any manual server step. The published
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

For NVIDIA-hosted NIM API Catalog access:

```bash
export NVIDIA_API_KEY='...'
export BIFANG_DEFAULT_PROVIDER='nvidia'
export BIFANG_NVIDIA_MODEL='<model-id-from-NVIDIA-catalog>'
```

For a self-hosted NIM container, set `BIFANG_NVIDIA_BASE_URL` to its
OpenAI-compatible endpoint and `BIFANG_NVIDIA_MODEL` to the model it serves.
`NVIDIA_API_KEY` is optional if that endpoint has no authentication. NGC
credentials are required only where the selected image or model artifact
requires registry access; they are not inference API keys. Bifang does not
deploy NIM or provision GPUs. See [deployment boundaries](docs/DEPLOYMENT.md)
and [TensorRT compatibility](docs/TENSORRT_COMPATIBILITY.md).

Z.ai GLM and HuggingFace Inference Providers use OpenAI-compatible keys. OpenAI and Anthropic/OpenRouter account keys are also honored when present. `bifang models` reports every configured provider's live catalog; ids from non-default providers appear as `provider::model` and can be used anywhere a bare model id is accepted (composite ids are routed to the right provider on completion).

```bash
export ZAI_API_KEY='...'          # or ZHIPU_API_KEY / GLM_API_KEY; BIFANG_ZAI_MODEL defaults to glm-5.3
export HF_TOKEN='...'             # BIFANG_HUGGINGFACE_MODEL defaults to meta-llama/Llama-3.3-70B-Instruct
```

The app lists every model returned by the configured providers, not only the Nemotron family: the Nebius Token Factory account it is configured with is queried directly, and each provider's roles (fast/balanced/reasoning) preselect a model from its own catalog. `Auto` mode requires every role id to exist in the provider's live catalog.

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
