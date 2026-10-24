# Bounded engineering workflows

Current source development adds **Read-only team review** to the desktop chat
panel. This feature is not included in the retained Preview 3 installer.

After starting a workspace session, open the review panel, enter a brief and
confirm the inference budget. The coordinator runs an investigator and a
reviewer concurrently. Each has a separate conversation and provider client,
at most four model steps, a 60-second deadline and only list/read/search tools.
They cannot edit, run commands, access external tools, store memory or delegate
recursively. Credentials remain configured outside the project as usual;
selected repository content is sent to the configured inference service.

The panel shows each worker's state, analysis, model-receipt count and hashed
tool observations with actual inspected paths/ranges where applicable.
Analysis is explicitly unverified: a worker saying “tests passed” does not
create a verification record. Exhausting the step budget stops the worker;
it is not reported as successful completion.

## API and lifecycle

- `POST /sessions/{id}/review`: brief plus strict `inference_confirmed: true`.
- `GET /sessions/{id}/review`: current worker results and status.
- `POST /sessions/{id}/review/cancel`: cancel and await both workers.

The parent session is busy during a review, preventing overlapping chat,
Apply and session deletion. Server disposal also cancels its review before
closing the parent workspace. Cancellation before the first worker step has
a terminal status and releases the session. Starting another review requires
another explicit budget confirmation.

## Verification scope and remaining workflow

Synthetic tests exercise concurrent execution, real model–read–denied-write
cycles, unsupported success claims, bounded steps, early/mid-run cancellation
and API busy/confirmation controls. Search treats option-looking queries as
literal patterns and does not invoke a shell. Frontend compilation and helper
tests pass. A source-component browser rehearsal against the actual local API
with synthetic inference verified budget refusal, concurrent workers, mid-run
cancellation, restart and unverified-claim labels. The injected write attempt
did not create its sentinel file. Failed/cancelled workers retain available
model-request receipts; raw provider exception messages are not returned.
Packaged native interaction and live inference through this panel remain
separate checks; this rehearsal used no hosted model requests.

## Isolated implementer and independent verification

Current source also adds **Isolated engineering** beside the review panel.
Select source files and editable/output paths, then confirm the six-step model
budget. The implementer receives private copies of only those files; paths
escaping the selection and common credential/internal-state paths are denied.
Files must be regular UTF-8 text below 1 MB, with at most 128 selected paths
and an 8 MB initial snapshot. No shell, external tools or recursive workers
are available. Every write retains manual approval even if the parent uses
automatic approval. Selected source itself must still be screened for secrets.

After implementation, the engineer supplies an exact command argument array.
The verifier runs it on a separate read-only copy in Bubblewrap, without
network, host home or provider credentials. There is no unsandboxed fallback.
The result retains the exit status, exact selected-file snapshot hash, bounded
output plus complete stream hashes, timeout and candidate/source freshness.
Passing one declared check is not a claim that every regression or security
property passed. Dependencies must already exist in the mounted system
runtime; this path does not install packages or expose the host virtualenv.

Review the candidate patch, then stage it into the parent's isolated worktree.
Staging requires the reviewed candidate hash and a current passing check, and
refuses source drift, conflicts and a non-isolated parent. The original
checkout remains untouched until the existing separate **Apply** action.

### Candidate API

- `POST /sessions/{id}/candidate`: prompt, selected `files`, `writable` paths,
  and strict `inference_confirmed: true`.
- `GET /sessions/{id}/candidate`: state, analysis and check receipt.
- `POST /sessions/{id}/candidate/cancel`: cancel and await active work.
- `GET /sessions/{id}/candidate/patch`: review the exact candidate patch/hash.
- `POST /sessions/{id}/candidate/check`: `command` array, bounded `timeout`
  and strict `confirmed: true`.
- `POST /sessions/{id}/candidate/stage`: reviewed `candidate_sha256` and strict
  `confirmed: true`.

The session busy guard covers implementation and checking. Disposal cancels
active tasks and removes private candidate files. Typed API tests cover
confirmation, busy guards, selected paths, early cancellation, stale evidence
and the distinction between staging and Apply. Git patch tests cover text
with and without final newlines. A complete disposable-repository rehearsal
ran both real read-only agents, the real isolated implementer, a real
Bubblewrap/Python check, Git staging and a separate Apply, with scripted model
responses and zero hosted model requests. See development receipt
`outputs/bifang-engineering-pipeline-20261024.json`.

The actual source panel and local API also passed a browser walkthrough:
declining the budget made no model calls; denying a write produced a real
failed Bubblewrap check despite the model's unsupported success claim;
approving the write produced a passing check, reviewed patch and staged
worktree while the original stayed unchanged. Mid-inference cancellation
released the session. Staging now returns its full receipt immediately rather
than briefly hiding it until the next poll. Models were scripted; shell checks
and Git operations were real. Development receipts and screenshot are
`outputs/bifang-candidate-ui-20261024.json` and
`outputs/bifang-candidate-ui-staged-20261024.png`.

The installed native walkthrough remains a separate gate.
Dependency-aware scheduling, multiple-writer conflict handling,
durable hosted jobs, coordinator evidence synthesis and live model evaluation
remain unfinished. The bounded engineering path is not a claim of prompt-
injection immunity or a replacement for those remaining requirements.
