# Security

## Reporting a problem

Please arrange a private channel with the maintainer before sharing exploit
details, logs or credentials. GitHub private vulnerability reporting was not
enabled when checked on November 6, 2026. To arrange contact, open a minimal
[maintainer-contact request](https://github.com/Protocol-X-01/Bifang/issues/new)
with the affected component and your preferred contact method, without the
vulnerability details.

Include the exact Bifang version or source commit, platform, reproduction
steps and observed impact in the private report. Use synthetic credentials
and a disposable test project where possible. Maintainers will identify
affected versions during triage.

## Execution and approval

The agent uses a separate worktree or folder snapshot for reviewable changes.
Apply and check receipts bind decisions to the candidate patch. Manual mode
asks before actions; Auto permits constrained source edits; Full tool approval
grants broader tool authority after explicit confirmation. Workspace sharing,
restored history and query embedding have separate consent scopes.

Linux agent commands use Bubblewrap when enabled. Generated Python requires
the isolation path and stops when it is unavailable. Explicit command-isolation
opt-out and the native local terminal use host authority. Use a disposable VM
for hostile repositories or tools that need broader system access.

## Private data and external models

Model-facing file tools filter conventional credential paths and redact
recognized values from covered output. Redaction is heuristic: keep unrelated
secrets outside development workspaces. Source and memory content can be sent
to the configured model endpoints after the relevant approval. Local audit
transcripts and saved history are private application state.

Provider keys, desktop/API authentication, paired devices and judge access are
separate credentials. Never place a provider key in a client bundle or public
testing instructions. If a credential is exposed, coordinate replacement access
and revoke or rotate the exposed value.

## Review scope

Security reports distinguish source review, synthetic tests, packaged binaries
and deployed services. A passing source test does not by itself verify every
operating system or installed build. The repository's regression tests cover
the concrete control failures fixed by each patch.
