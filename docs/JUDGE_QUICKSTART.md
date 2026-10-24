# Judge walkthrough — local release candidate

**Track 1: Coding and Agentic Engineering.** Bifang turns a coding request
into reviewed edits, runnable checks and an explicit patch decision. Model
inference runs on NVIDIA Nemotron through Nebius Token Factory; the agent and
project stay in the Linux desktop application.

This walkthrough targets the locally verified approval-level candidate, not
the older public preview. Publication is still on hold. The operator must
supply the matching build, source, checksums, notices and private judge access
before distributing these instructions. No judge should need a paid API key.

## 1. Install

Use Ubuntu 24.04 amd64 with a graphical desktop, Git, Python 3 for the example
checks, and working Bubblewrap namespaces. The desktop bundles its own Python
3.11 agent; a separate Python 3.11 installation is not required to run it.

Verify the supplied checksum, then install:

```bash
sha256sum Bifang-approval-styled_0.2.0_amd64.deb
sudo apt install ./Bifang-approval-styled_0.2.0_amd64.deb
sudo apt install git python3 bubblewrap
```

Expected candidate SHA-256:
`160eb03fff45c5b5a562f2f05b7f0d90a6088c4f6533379b5c8cbcbb2152e024`.
Follow [Ubuntu sandbox setup](UBUNTU_SANDBOX.md) if AppArmor denies namespaces.
The profile change belongs to the machine administrator, not the agent.

## 2. Configure private judge access

The operator supplies an approved HTTPS relay origin and a judge-only token
through the private testing instructions. Do not use the creator's provider
key or paste any credential into chat, a project file or a screenshot.

Using a local editor, create
`${XDG_CONFIG_HOME:-~/.config}/com.bifang.desktop/.env` with these settings:

```dotenv
BIFANG_DEFAULT_PROVIDER=nebius
BIFANG_NEBIUS_BASE_URL=https://REPLACE_WITH_APPROVED_RELAY/v1
NEBIUS_API_KEY=REPLACE_WITH_PRIVATE_JUDGE_TOKEN
BIFANG_NEBIUS_MODEL=nvidia/Nemotron-3-Ultra-550b-a55b
BIFANG_ROUTING_MODE=pinned
BIFANG_APPROVAL_MODE=manual
BIFANG_BWRAP=1
```

Replace both placeholders privately; neither is a working credential. Restrict
the config file to your account (`chmod 600` on Linux), then launch Bifang.
Keep this config outside the example project. Restart the app after changing it.

## 3. Try the receipt repair

From the supplied matching source, copy `examples/demo` into a new disposable
directory. Initialize a Git repository there and commit the supplied fixture.
Do not use the whole Bifang source tree as the task workspace.

In that directory, run:

```bash
git init
git add .
git -c user.name='Bifang Demo' -c user.email='demo@example.invalid' commit -m 'Baseline fixture'
python3 -m unittest -v check_receipts
```

The baseline intentionally fails. In Bifang, use **Open by path…** with this
directory's absolute path. Leave approvals at **Off · manual review**. Ask:

> Fix parse_receipt in receipts.py so all five existing checks pass. Preserve
> check_receipts.py, use the standard library, run the checks before and after,
> and explain the resulting patch.

Read each proposed action before approving. The expected command is
`python3 -m unittest -v check_receipts`; the expected edited file is
`receipts.py`. Model output is not deterministic: reject unexpected actions
and report errors rather than assuming every run follows the recording.

Inspect the diff and expanded model receipts, then choose **Apply** only if
the change is appropriate. Verify in the original example directory:

```bash
git diff --name-only
git diff --exit-code -- check_receipts.py
python3 -m unittest -v check_receipts
```

Expected: only `receipts.py` changes, the checks file is unchanged, and all
five checks pass. Before Apply, edits remain in the isolated worktree.

## 4. Explore approval levels

- **Off:** review edits and commands individually.
- **Auto:** ordinary bounded source edits in the isolated worktree can proceed;
  commands and sensitive actions still request review.
- **Full:** explicitly opt in to automatic tool approval. Existing path,
  command and sandbox restrictions remain. Use only with a trusted project.

**Pause auto approvals** makes subsequent actions request review; it does not
cancel an already running process. Applying the patch remains a separate
decision. New chats and app reload reset the desktop to manual review.

## If something fails

Namespace/uid-map errors: use the scoped Ubuntu setup; do not disable the
sandbox. Authentication errors: ask the operator to check the judge token and
relay access. Provider errors: ask the operator to check availability/billing.
The judge should not need to purchase credits or supply a provider key.
For reporting, include the app/build identifier, action and sanitized error,
never your config file, token or private project contents. Operator procedures
are in [JUDGE_OPERATIONS.md](JUDGE_OPERATIONS.md).
