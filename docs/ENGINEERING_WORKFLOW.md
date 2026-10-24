# A checked patch, not just a confident answer

Bifang's desktop separates investigation, implementation, verification and
the decision to keep a change. Start with an ordinary Git project and a
configured Nebius Token Factory or NVIDIA-compatible provider.

## Read-only team review

Open **Read-only team review** to run a bounded investigator and reviewer in
parallel. Their tools inspect files; they cannot write, run commands, delegate
or use external tools. File observations include paths, ranges and hashes.
Model analysis stays separate from those source-backed observations.

## Isolated engineering

1. Open the project with **Open by path…**, then start a chat to create its
   disposable session worktree.
2. Expand **Isolated engineering**. Enter source paths, one per line, and the
   paths the implementer may edit. Provide a focused engineering brief.
3. Choose **Prepare candidate** and review the inference confirmation. The
   implementer has up to six model steps and a 90-second inference deadline.
   Only selected source files enter its private candidate.
4. Review each proposed write. Denying a write does not silently approve it
   later. The worker's write approvals remain manual even if the parent chat
   uses an automatic approval mode.
5. Enter the exact check arguments as a JSON array, for example
   `["/usr/bin/python3", "-B", "-m", "unittest", "discover"]`.
   Choose **Run independent check** and confirm those arguments.
6. Inspect the executed check receipt and **Review candidate patch**.
   A current passing receipt and the reviewed candidate hash are required for
   **Stage reviewed candidate**.
7. Staging copies the checked patch only into the session worktree. Review
   **Workspace Diff**, then choose **Apply** and **Apply to repository** when
   you want it copied to the clean original checkout.

The independent check runs in Bubblewrap on a read-only snapshot, without
network or provider credentials. Missing sandbox support fails closed.
Use the [Ubuntu scoped profile instructions](UBUNTU_SANDBOX.md) where needed.
The receipt proves the selected command on that exact snapshot; an
implementer's statement that tests passed is not execution evidence.

## Web and observability

Set `TAVILY_API_KEY` to enable built-in `web_search`. It uses bounded basic
search, public result URLs, source hashes and untrusted-result labels. Search
is an external action governed by the parent agent's approval policy; the
read-only team and private implementer do not gain this capability.

Tracing is opt-in with `BIFANG_ENABLE_TRACING=1`. Choose
`BIFANG_TRACING_BACKEND=langsmith`, set `LANGSMITH_API_KEY` and
`LANGSMITH_PROJECT`, and use the official endpoint for your region through
`LANGSMITH_ENDPOINT`. The adapter exports allowlisted operational metadata,
not prompt/output bodies. Phoenix remains available through the `phoenix`
backend. LangSmith synthetic parent/child trace read-back has been verified;
this does not itself deploy a hosted agent or enable Engine.

Provider keys belong in private per-user configuration, never the repository.
Review [product expansion](PRODUCT_EXPANSION.md) for vision, hosted execution
and mobile requirements.

## Reproduce the native fixture

The exact Preview 4 installer passes this synthetic, local-only native test on
Ubuntu 24.04. Install its runtime dependencies, `git`, `xvfb`, `xauth`,
`python3-httpx`, `webkit2gtk-driver`, and Bubblewrap. Install `tauri-driver`
separately and follow the Ubuntu scoped profile prerequisite. From the source
root, with ports 8000 and 4444 unused:

```bash
PYTHONPATH=src xvfb-run -a python3 scripts/smoke-desktop-engineering.py \
  --application /usr/bin/bifang-desktop \
  --native-driver /usr/bin/WebKitWebDriver \
  --tauri-driver "$(command -v tauri-driver)" \
  --output /tmp/bifang-native-engineering-evidence
```

Use a fresh output path. The harness creates and removes a disposable Git
fixture and private app home; it uses synthetic loopback model replies rather
than your provider credentials. It verifies denial, actual failing/passing
checks, patch review, staging and separate Apply. The unsupported synthetic
success claim is intentional. Native tests use a virtual display and software
rendering, not a physical desktop usability or hostile-code isolation study.
See [exact installer receipt](evidence/ubuntu-engineering-native.json).
