<p align="center">
  <img src="https://raw.githubusercontent.com/Protocol-X-01/Bifang/main/docs/assets/bifang-hero.svg" width="1280" alt="Bifang — Build. Run. Verify. A Nemotron coding workspace with disposable worktrees, approvals and diffs." />
</p>

<p align="center">
  <strong>Give the agent a failing test. Keep control of the change.</strong><br>
  Open-source desktop and terminal tools for agentic engineering.
</p>

<p align="center">
  <a href="https://github.com/Protocol-X-01/Bifang/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-E63946?style=flat-square" alt="Apache 2.0 license" /></a>
  <img src="https://img.shields.io/badge/Python-3.11-0F172A?style=flat-square" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/Track-01%20Agentic%20Engineering-FF8A3D?style=flat-square" alt="Track 1: Agentic Engineering" />
  <img src="https://img.shields.io/badge/Status-Active%20Development-FF8A3D?style=flat-square" alt="Active Development" />
</p>

<p align="center">
  <a href="https://github.com/Protocol-X-01/Bifang/releases/latest"><img src="https://img.shields.io/github/v/release/Protocol-X-01/Bifang?label=Latest%20Release&color=E63946&style=flat-square" alt="Latest Release" /></a>
  <img src="https://img.shields.io/github/commit-activity/m/Protocol-X-01/Bifang?color=FF8A3D&style=flat-square" alt="Commit Activity" />
  <img src="https://img.shields.io/github/issues/Protocol-X-01/Bifang?color=E63946&style=flat-square" alt="Open Issues" />
</p>

---

## 🎯 What is Bifang?

**Bifang** is an evidence-driven coding workspace where every agent action is visible, reviewable, and yours to approve.

```text
Open a project → Ask for a fix → See the patch → Approve → Tests run → Apply
```

**No black boxes. No blind trust. Just evidence.**

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🌿 **Disposable Worktrees** | Original checkout untouched until you explicitly `Apply` |
| ⚡ **Three Approval Modes** | Manual · Auto source edits · Full tool approval |
| 📋 **Independent Check Receipts** | Every check bound to exact candidate SHA-256 |
| 🧠 **Model Routing Receipts** | Requested vs reported model · Token counts · Verified |
| 👁️ **Visual Debugging** | Explicit image sharing · Model receipts · Chat handoff |
| 🌐 **Remote Forge** | Selected source → proposal → check → hosted Apply |
| 📱 **Mobile Companion** | Terminal + remote coding from your phone |
| ✅ **Evidence-Driven** | Every claim bound to artifact. No black boxes. |

---

## 🎬 See It In Action

<p align="center">
  <a href="https://github.com/Protocol-X-01/Bifang/releases/latest">
    <img src="docs/assets/bifang-live-demo.mp4" width="800" alt="Bifang desktop demo" />
  </a>
</p>

> **The Demo:** A broken CSV parser. Nemotron Ultra reads the source, repairs it, runs the checks. You inspect the proposed actions, the diff, and model receipts. After Apply, all five original checks pass and only the parser has changed.

---

## 🚀 Quickstart

```bash
# Prerequisites: Python 3.11, Git, Bubblewrap (Linux)
sudo apt update && sudo apt install -y pipx git ripgrep bubblewrap
pipx ensurepath

git clone https://github.com/Protocol-X-01/Bifang.git
cd Bifang
pipx install --python python3.11 .

# Configure your provider
export NEBIUS_API_KEY='your-key-here'
bifang doctor
cd your-project
bifang chat
```

**Inside chat:**
```text
Find the failing parser test, determine the root cause, make the smallest reasonable fix, and verify it.
```

---

## 🏗️ For Developers

```bash
# From cloned repository
uv sync --locked --extra dev --extra observability

# Run tests
uv run pytest -q

# Run desktop in development
cd desktop
npm ci
npm run tauri:dev

# Build Linux packages
./scripts/build-linux.sh
```

**Stack:** Python 3.11 · Rust 1.90+ · Tauri 2 · React 18 · TypeScript · uv · uv.lock

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design and data flows |
| [Security](docs/SECURITY.md) | Safety model and threat analysis |
| [Releasing](docs/RELEASING.md) | Release process and gates |
| [Deployment](docs/DEPLOYMENT.md) | Production deployment guide |
| [Approval Modes](docs/APPROVAL_MODES.md) | Manual · Auto · Full tool approval |
| [Engineering Workflow](docs/ENGINEERING_WORKFLOW.md) | Isolated engineering walkthrough |
| [Visual Debugging](docs/VISION.md) | Image sharing and visual receipts |
| [Remote Coding](docs/REMOTE_CODING.md) | Remote forge workflow |
| [Mobile Companion](companion/README.md) | Android app and pairing |

---

## 🛡️ Safety Model

- **Disposable Git worktrees** by default — original checkout untouched
- **Filesystem tools confined** to the Bifang workspace
- **Typed model tools** validated before use
- **Three approval levels** — Manual · Auto · Full tool approval
- **Destructive patterns blocked** in every mode
- **Environment allowlist, timeout, and output cap**
- **JSONL audit transcript** under `.bifang/sessions`

> Bifang is defense in depth, not a formally verified security boundary. Use disposable VMs for hostile repositories.

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repo
2. Create a feature branch
3. Make your changes with tests
4. Run `uv run pytest -q` and `uv run ruff check`
5. Open a PR with a clear description

---

## 📄 License

**Apache 2.0** — See [LICENSE](LICENSE) for details.

> Independent open-source project for the Nebius x NVIDIA Global AI Hackathon. Not an official NVIDIA or Nebius product.

---

<p align="center">
  <img src="docs/assets/bifang-workflow.svg" width="800" alt="Bifang's coding loop: inspect, reason, review, verify and decide." />
</p>

<p align="center">
  <strong>Build. Run. Verify.</strong><br>
  <a href="https://github.com/Protocol-X-01/Bifang">github.com/Protocol-X-01/Bifang</a>
</p>