# Contributing to Bifang

Thank you for your interest in contributing to Bifang! We welcome contributions from the community.

## 🎯 Ways to Contribute

- **Bug Reports** — Found a bug? Open an issue with reproduction steps
- **Feature Requests** — Have an idea? Open a discussion first
- **Code Contributions** — Fix bugs, add features, improve tests
- **Documentation** — Improve docs, add examples, fix typos
- **Testing** — Add test cases, improve coverage

## 🛠️ Development Setup

```bash
# Prerequisites
# - Python 3.11 (exactly)
# - Rust 1.90+
# - Node.js 20.19+
# - uv (for Python package management)
# - Tauri system dependencies (see https://tauri.app/v1/guides/getting-started/prerequisites)

# Clone and setup
git clone https://github.com/Protocol-X-01/bifang.git
cd bifang
uv sync --locked --extra dev --extra observability

# Run tests
uv run pytest -q

# Lint
uv run ruff check src/

# Type check
uv run python -m compileall -q src
```

## 🏗️ Project Structure

```
bifang/
├── src/                    # Python backend
│   └── bifang/            # Main package
├── desktop/               # Tauri + React desktop app
│   ├── src/               # React frontend
│   └── src-tauri/         # Rust backend
├── companion/             # Tauri + React Android app
├── companion/             # TUI (terminal UI)
├── tests/                 # Python tests
├── desktop/tests/         # Desktop tests
├── companion/tests/       # Companion tests
└── docs/                  # Documentation
```

## 🧪 Testing

```bash
# Run all tests
uv run pytest -q

# Run specific test file
uv run pytest tests/test_workspace.py -v

# Run desktop tests
cd desktop && npm test

# Run companion tests
cd companion && npm test
```

## 📝 Code Style

- **Python**: Ruff (line length 100, target Python 3.11)
- **TypeScript/React**: ESLint + Prettier
- **Rust**: rustfmt + clippy

Run linters before committing:
```bash
uv run ruff check src/
cd desktop && npm run lint
cd companion && npm run lint
```

## 📝 Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new approval mode for tool approval
fix: fix terminal resize on workspace switch
docs: update approval modes documentation
test: add test for candidate verification
refactor: extract approval logic into separate module
```

## 🔄 Pull Request Process

1. **Fork** the repository
2. **Create** a feature branch from `main`
3. **Make** your changes with tests
4. **Run** tests and linters locally
5. **Open** a Pull Request with:
   - Clear title and description
   - Link to related issue (if any)
   - Screenshots for UI changes
   - Test results

## 🔍 Code Review Guidelines

- **Be respectful** and constructive
- **Focus** on correctness, clarity, and maintainability
- **Check** that tests pass and coverage doesn't decrease
- **Verify** that the change aligns with Bifang's safety model

## 🏷️ Issue Labels

- `bug` — Something isn't working
- `enhancement` — New feature or improvement
- `documentation` — Documentation update needed
- `good first issue` — Good for newcomers
- `help wanted` — Extra attention needed
- `security` — Security-related
- `tui` — Terminal UI related
- `desktop` — Desktop app related
- `companion` — Mobile companion related

## 🤝 Community

- **Discussions** — Ask questions, share ideas
- **Issues** — Report bugs, request features
- **Discord** — [Join our Discord](https://discord.gg/bifang) (if available)

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).

---

**Thank you for contributing to Bifang!** 🎉

*Build. Run. Verify.*