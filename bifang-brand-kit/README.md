# Bifang

**Build. Run. Verify.**

Bifang is an open, terminal-native coding agent powered by NVIDIA models on Nebius. It understands repositories, writes and runs code inside isolated workspaces, and verifies changes with tests and execution evidence.

> Bifang is an independent open-source project created for the Nebius x NVIDIA Global AI Hackathon. It is not an official NVIDIA or Nebius product.

## Why Bifang?

Most coding assistants can produce code. Bifang is designed to produce evidence.

```text
Understand → Plan → Approve → Execute → Verify → Explain
```

The name comes from Bifang (毕方), the one-legged bird in early Chinese mythology associated with unusual fire and warning. The product adopts that warning aspect as a design principle: powerful execution should be visible, controlled, and verifiable.

## Features

- Repository mapping, search, and bounded file access
- NVIDIA Nemotron reasoning through Nebius Token Factory
- Typed model tools and bounded agent loops
- Explicit `observe`, `assist`, and `trusted` permission modes
- Disposable Git-worktree isolation
- Optional Bubblewrap command isolation on Linux
- Reviewable diffs and approval-gated writes
- Test execution and evidence-driven reporting
- JSONL audit transcripts
- Live model discovery

## Architecture

```text
Bifang Terminal
      │
      ▼
Agent Runtime ───── NVIDIA models on Nebius
      │
      ▼
Controlled workspace
Git worktree · Bubblewrap · audit log
```

## Kali Linux installation

```bash
sudo apt update
sudo apt install -y pipx git ripgrep bubblewrap
pipx ensurepath
pipx install .
```

Or run:

```bash
chmod +x scripts/install-kali.sh
./scripts/install-kali.sh
```

## Configure

Do not commit API keys.

```bash
export NEBIUS_API_KEY="your-token-factory-key"
export BIFANG_BASE_URL="https://api.tokenfactory.nebius.com/v1"
export BIFANG_MODEL="your-current-nvidia-model-id"
export BIFANG_MODE="assist"
```

Inspect the live NVIDIA model catalog and validate the host:

```bash
bifang models
bifang doctor
```

## Quick start

```bash
cd ~/code/your-project
bifang chat
```

Example:

```text
Find the failing parser test, determine the root cause,
make the smallest reasonable fix, and verify it.
```

## Terminal commands

```text
/help          Show commands
/status        Show workspace, provider, model, and policy
/map           Display the repository map
/diff          Show workspace changes
/tests         Start test-and-repair workflow
/transcript    Show the active audit log
/quit          Exit
```

## CLI

```bash
bifang chat
bifang doctor
bifang models
bifang run -- pytest -q
bifang patch > bifang.patch
bifang --version
```

## Approval modes

- `observe`: read-only analysis
- `assist`: ask before writes and commands, the default
- `trusted`: run permitted actions without per-action prompts

Trusted mode should only be used in disposable or controlled environments.

## Security

Bifang treats model output as untrusted. Current safeguards include workspace path containment, worktree isolation, typed tools, approvals, command deny rules, reduced child environments, timeouts, output caps, optional Bubblewrap namespaces, and append-only transcripts.

These are defense-in-depth controls, not a formally verified security boundary. For hostile repositories, use a disposable VM or dedicated cloud environment.

## Environment variables

```text
NEBIUS_API_KEY
BIFANG_BASE_URL
BIFANG_MODEL
BIFANG_MODE
BIFANG_MAX_STEPS
BIFANG_TIMEOUT
BIFANG_WORKTREE
BIFANG_BWRAP
```

Deprecated `ARCA_*` names may be accepted for one migration release, but all new installations should use `BIFANG_*`.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
ruff check .
```

## Linux binary

```bash
./scripts/build-linux.sh
./dist/bifang --version
sha256sum -c dist/bifang.sha256
```

## Roadmap

- Persistent sessions and reattachment
- Atomic patch transactions and undo
- Streaming model and tool output
- Network-denied execution by default
- CPU, memory, process, and GPU limits
- Scoped secret grants
- Test discovery and language-server integration
- CUDA profiling and benchmark evidence
- MCP and reusable skills
- Signed Linux, macOS, and Windows binaries with SBOMs and provenance

## Principles

1. Evidence over claims
2. Human control over consequential actions
3. Minimal, reviewable changes
4. Open infrastructure
5. Visible and configurable boundaries
6. Real engineering outcomes

## License

Apache License 2.0.

NVIDIA, Nemotron, CUDA, Nebius, and related marks belong to their respective owners. Compatibility references do not imply endorsement.
