<p align="center">
  <img src="docs/assets/bifang-hero.svg" width="1280" alt="Bifang — Build. Run. Verify. A Nemotron coding workspace with disposable worktrees, approvals and diffs." />
</p>

<p align="center"><strong>Give the agent a failing test. Keep control of the change.</strong><br />Open-source desktop and terminal tools for agentic engineering.</p>

<p align="center">
  <a href="https://github.com/Protocol-X-01/bifang/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-E63946?style=flat-square" alt="Apache 2.0 license" /></a>
  <img src="https://img.shields.io/badge/Python-3.11-0F172A?style=flat-square" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/Track-01%20Agentic%20Engineering-FF8A3D?style=flat-square" alt="Track 1: Agentic Engineering" />
  <img src="https://img.shields.io/badge/CI-passing-22C55E?style=flat-square&logo=githubactions" alt="CI Status" />
  <img src="https://img.shields.io/badge/desktop--platforms-passing-22C55E?style=flat-square&logo=githubactions" alt="Desktop Platforms" />
</p>

<p align="center"><a href="#see-the-coding-loop">See the demo</a> · <a href="#quickstart">Run Bifang</a> · <a href="docs/ARCHITECTURE.md">Architecture</a> · <a href="docs/HACKATHON_READINESS.md">Build status</a></p>

**Linux preview:** [Download the Ubuntu 24.04-tested Preview 6](https://github.com/Protocol-X-01/bifang/releases/tag/v0.2.1-preview.6).
Unsigned prerelease; bring your own provider key. Use **Open by path…** to
select a project without relying on a native file chooser.

Bifang is a desktop coding IDE and terminal agent built around a practical, reviewable engineering loop. It can map a repository, propose focused edits, run approved commands and tests, and show the resulting diff before you keep or discard the work. Git repositories use a disposable worktree by default, leaving the original checkout untouched until you explicitly export or apply a patch.

<details>
<summary><strong>Bring a screenshot into the coding conversation</strong></summary>

Choose an image-capable model, confirm image sharing, inspect the visual receipt
and decide which observations belong in your chat draft.

![Preview 5 native visual review with synthetic inference and explicit chat handoff.](docs/assets/bifang-vision-native.png)

[Visual context guide and evidence](docs/VISION.md)

</details>

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

The active level stays visible. New chats, workspace changes, restored
conversations and page reloads return to manual review. Final **Apply** remains
a separate confirmation. See [approval modes](docs/APPROVAL_MODES.md).

### From parallel review to a checked patch

Open **Read-only team review** for bounded investigator and reviewer workers,
with file-backed observations. Use **Isolated engineering** when you want an
implementer to prepare a change from explicitly selected files:

**Select files → approve writes → execute an independent check → review the
patch → stage → Apply.**

The check receipt records the exact command, snapshot hash and exit status.
Staging keeps the original checkout untouched until you choose Apply.
[Follow the engineering walkthrough](docs/ENGINEERING_WORKFLOW.md).

Optional [Tavily web search and LangSmith tracing](docs/ENGINEERING_WORKFLOW.md#web-and-observability)
complement the coding loop. The Ember terminal adapts to smaller windows with
keyboard-accessible inspectors.

> Independent open-source project for the Nebius x NVIDIA Global AI Hackathon. Not an official NVIDIA or Nebius product.

## See the coding loop

The [receipt-parser demo](docs/DEMO.md) starts with two broken CSV cases.
Nemotron Ultra fixes the parser through Bifang's tools, leaving the original
checks intact. The release-profile desktop app completed the live task,
approval dialogs, diff review, and patch application. All five original
checks passed in the source checkout afterward.

![Bifang desktop after a real Nemotron coding task: formatted chat, repository files, reviewed diff and successful apply.](docs/assets/bifang-desktop.png)

<details>
<summary><strong>Review an action before it runs</strong></summary>

![Bifang's in-app approval dialog with the exact proposed action, Deny and Allow once controls.](docs/assets/bifang-approval.png)

Approvals are scoped to one action. The demo harness clicked these actual
controls using an exact-action allowlist.

</details>

| Verified milestones on October 24 | Evidence and scope |
| --- | --- |
| Preview 5 visual context | Image attachments, explicit sharing, cancellation and labelled chat handoff; fresh-Ubuntu native package walkthrough. |
| Preview 5 coding regression | Same new installer: write denial, failing/passing independent checks, reviewed staging and separate Apply; seven synthetic calls. |
| Preview 5 frozen source | 374 backend tests; 373-file build-input archive. Three live Nemotron visual-debugging smoke cases used 3,010 reported tokens. |
| Preview 4 frozen-source suite | All 348 backend tests pass from the retained 363-file build-input archive. |
| Preview 4 native engineering | Exact installer on fresh Ubuntu: denied write → failed check; approved write → passing check → reviewed staging → separate Apply. Seven synthetic model calls, zero hosted calls. |
| Optional integrations | Live Tavily public search; LangSmith synthetic parent/child trace read-back. Phoenix remains available. |
| Live Token Factory coding task | Only `receipts.py` changed; all five checks passed after apply. |
| Earlier Preview 3 suite | 295 backend tests pass for that frozen release candidate. |
| Earlier frozen-source native rebuild | 336 build-input files verified; that package passes synthetic desktop, sandbox API and authenticated Phoenix checks. |
| Hosted judge relay | Judge-only HTTPS access, model catalog, Ultra completion and Nano streaming verified; no provider key distributed. |
| Native desktop through relay | Five Ultra calls, sandbox enabled, approved edit/test actions, patch apply and five unchanged checks. |
| Linux desktop loop | Release-profile Debian package; native UI approvals, diff and apply verified. |
| Independent installation | Fresh Ubuntu 24.04 VM: actual workspace dialog → live task → apply → five passing checks. |
| Container runtime | Built and tested in the VM: non-root, authenticated API, confined workspace paths. |
| NVIDIA-compatible endpoint | Configured hosted NVIDIA API returned a Nemotron Ultra completion. |

The original recorded rehearsal used synthetic code, a preselected test workspace,
and automated approvals restricted to the demo's edit and test actions.
See [demo evidence](docs/DEMO_EVIDENCE.md) and
[remaining release gates](docs/HACKATHON_READINESS.md). Clean-machine
installation is now verified on [Ubuntu 24.04](docs/INSTALLATION_EVIDENCE.md);
successful native folder selection remains unverified.
The newer preview also passes workspace selection through its in-app path
dialog, including rejection of relative, missing, and non-directory paths.

<p align="center"><img src="docs/assets/bifang-workflow.svg" alt="Bifang's coding loop: inspect, reason, review, verify and decide." /></p>

## Quickstart

- Python 3.11 (the supported range is `>=3.11,<3.12`)
- Git for isolated worktrees; Bubblewrap for the default Linux command sandbox
- A Nebius Token Factory API key, or an OpenAI-compatible NVIDIA NIM endpoint
- Building the desktop app additionally requires Rust 1.90+, Node.js 20.19+,
  `uv`, and the platform's Tauri system dependencies

On Ubuntu 24.04, check the [Bubblewrap/AppArmor prerequisite](docs/UBUNTU_SANDBOX.md)
before agent commands. The scoped setup keeps global namespace restrictions enabled.

```bash
sudo apt update
sudo apt install -y pipx git ripgrep bubblewrap
pipx ensurepath
git clone https://github.com/Protocol-X-01/bifang.git
cd bifang
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

To run the desktop IDE in development (its build script provisions a separate
locked Python environment for the bundled service):

```bash
cd desktop
npm ci
npm run tauri:dev
```

The desktop shell requires Python 3.11, Rust 1.90+, Node.js 20.19+, and the
platform's Tauri build dependencies. Its build packages `bifang-server` as a
sidecar; users do not need Python installed to run the packaged app. See
[`desktop/README.md`](desktop/README.md) for configuration and Linux packaging.

## Why this build

The Bifang bird identity represents watchfulness and controlled fire: the
agent moves the work forward while the engineer can inspect what changed.
The engineering focus is a complete coding loop with visible evidence.

NVIDIA Nemotron models on Nebius Token Factory power the iterative edit/test
loop. Visible model receipts, explicit action approvals and reviewable diffs
help the engineer follow the work from the first failing check to the final
patch. An OpenAI-compatible NIM endpoint is also available as a provider option.

The working desktop and terminal are the foundation. Preview 5 adds
[visual review](docs/VISION.md): explicit image sharing, a model receipt and
user-controlled handoff into coding chat.
Newer source adds [Remote forge](docs/REMOTE_CODING.md): selected-source tasks,
independently reconstructed candidate hashes, isolated checks and separate hosted
snapshot Apply. A [mobile-oriented companion](companion/README.md) shares this
workflow without a local agent sidecar. Its source and Linux shell are tested;
Android/iOS builds and device checks remain acceptance gates. These newer clients
are not in the Preview 5 installer; [product expansion](docs/PRODUCT_EXPANSION.md)
tracks delivery status.

## Configure

Persistent [project memory](docs/MEMORY_RETRIEVAL.md) uses local ranked text
retrieval by default in the development version. Provider embeddings are
explicitly opt-in and use a separate embedding model, not the chat model.
[Conversation history](docs/CONVERSATION_HISTORY.md) additionally supports
durable API/terminal sessions and explicit resume; the desktop includes a
history picker.

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

For NIM, point the NVIDIA-compatible provider at the OpenAI-compatible NIM
endpoint and use the model name configured by that deployment. NGC credentials
are needed to pull licensed NVIDIA containers; they are not inference API keys.
The app does not deploy NIM or provision GPUs by itself.

Use `bifang models` to inspect the live model catalog rather than relying on a hard-coded model ID.

## Use

Try the [repeatable receipt-parser demo](docs/DEMO.md) to rehearse the
inspect → approve → edit → test → apply loop on synthetic code.

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

Replace `BOX_ID` with the eight-character ID from `bifang boxes`, run from the
original project checkout. Patch export preserves the Git index. Discard asks
for confirmation and removes only the selected isolated workspace. Toolchain
discovery previews optional Python, JavaScript/TypeScript and Rust setup without
installing packages. See [Developer workbench](docs/DEVELOPER_WORKBENCH.md) for
the required plugin, package-manager, terminal and platform delivery work.

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

Current local source supports [isolated folder workspaces](docs/FOLDER_WORKSPACES.md)
for projects without Git or a first commit, with patch-bound review and Apply.
These changes are not yet included in the published installer.

See `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/RELEASING.md`, and
`docs/DEPLOYMENT.md`. Hackathon deliverables and remaining gates are tracked in
`docs/HACKATHON_READINESS.md`.
