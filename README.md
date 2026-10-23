# Bifang

**Build. Run. Verify.**

Bifang is an open-source, Nemotron-powered coding IDE for agentic engineering. Its desktop workspace is designed around a practical coding loop: understand a repository, propose and apply focused edits, run approved commands and tests, inspect the diff, then keep or discard the work. The terminal interface remains available for fast, scriptable use. Git repositories run in a disposable worktree by default, so the original checkout remains untouched until you explicitly export or apply the patch.

Our performance research explores KV-cache quantization as a way to reduce memory pressure while preserving long-context recall. The current quantizer is an experimental prototype, not yet wired into the serving path; measured quality and performance results are required before making optimization claims. See `docs/PERFORMANCE.md` for the experiment plan.

> Independent open-source project for the Nebius x NVIDIA Global AI Hackathon. Not an official NVIDIA or Nebius product.

## Requirements

- Python 3.11 (the supported range is `>=3.11,<3.12`)
- Git for isolated worktrees; Bubblewrap is optional on Linux
- A Nebius Token Factory API key, or an OpenAI-compatible NVIDIA NIM endpoint
- Building the desktop app additionally requires Rust 1.90+, Node.js 20.19+,
  `uv`, and the platform's Tauri system dependencies

## Install

```bash
sudo apt update
sudo apt install -y pipx git ripgrep bubblewrap
pipx ensurepath
pipx install .
```

For development:

```bash
cd bifang
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

## Product direction

The GPU-acceleration motivation is to make a coding agent feel responsive while
it understands a large codebase and runs an iterative edit/test loop. The
inspiration includes the new class of desk-side AI systems exemplified by
NVIDIA RTX Spark and DGX Spark. Bifang currently sends model inference to
Nebius Token Factory by default, with an OpenAI-compatible NIM endpoint as an
alternative; it does not yet run models locally on Spark hardware or claim
measured GPU speedups. Local inference is a potential future backend, not a
requirement for the current hackathon demo.

The long-term vision includes desktop and mobile clients. The hackathon build
focuses on making the desktop coding loop complete and demonstrable; a mobile
companion for session review and approvals can follow without turning the
deadline into two parallel IDE builds.

## Configure

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
/help /status /map /diff /tests /transcript /quit
```

Other CLI operations:

```bash
bifang run -- pytest -q
bifang patch > bifang.patch
bifang discard
bifang --version
```

## Safety model

- disposable Git worktree by default;
- filesystem tools confined to the Bifang workspace;
- typed model tools, validated before use;
- `observe`, `assist`, and `trusted` modes;
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

See `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/RELEASING.md`, and
`docs/DEPLOYMENT.md`. Hackathon deliverables and remaining gates are tracked in
`docs/HACKATHON_READINESS.md`.
