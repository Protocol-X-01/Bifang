# Durable remote review jobs

The working source after Preview 5 adds a separate authenticated review-job
service. This is the first remote workflow component for hosted orchestration
and mobile clients, not an exposure of the desktop filesystem API. It accepts
explicitly shared source snapshots, runs a selected model without tools and
retains a review receipt across reconnects.

The working source now runs as a private, authenticated AWS service. Preview 5
and the existing Vercel judge relay are unchanged. Trusted public-IP HTTPS and
one synthetic Token Factory Nano review now pass on AWS. Full remote editing,
independent execution/Apply and native mobile clients remain separate gates.

## Run locally

Use the locked Python 3.11 environment and an owner-only persistent state
directory. Configure a provider key privately, then set `BIFANG_REMOTE_CLIENTS`
to a JSON list of `subject` and `token_sha256` entries. Subjects are opaque
1–64 character identifiers; hashes are SHA-256 of independently provisioned
32–256 character bearer tokens. Never reuse or distribute provider credentials
as client tokens. The registry contains hashes, not plaintext bearer tokens.

Run `python -m bifang.remote_server`. The default bind is `127.0.0.1:8125`;
`BIFANG_REMOTE_STATE` selects the private state directory and
`BIFANG_REMOTE_HOST` selects the bind address. Do not expose this development
service publicly without HTTPS termination, operational monitoring and a
reviewed identity/deployment configuration. No service starts merely because
the desktop app or provider credentials are present.

## Client contract

All `/v1` requests require `Authorization: Bearer <client-token>`. Provider
credentials stay on the server. Requests and responses are non-cacheable.

| Route | Purpose |
|---|---|
| `GET /health` | Minimal health and worker availability; no owner/source data |
| `GET /v1/schema` | Self-contained JSON Schema for a review request |
| `POST /v1/reviews` | Submit a source snapshot; mandatory `Idempotency-Key` |
| `GET /v1/reviews` | Latest 20 jobs belonging to the authenticated subject |
| `GET /v1/reviews/{id}` | Reconnect to that subject's job and result |
| `POST /v1/reviews/{id}/cancel` | Cancel queued work or request running cancellation |
| `DELETE /v1/reviews/{id}` | Remove a terminal result, preserving an idempotency tombstone |

Submission includes explicit `provider`, exact `model`, `question`, `files`
(relative `path` and text `content`) and strict boolean `sharing_confirmed`.
The caller must affirm sharing with both this service and the selected provider.
An authenticated user cannot choose another subject through the body or URL.
Unknown and other-owner IDs return the same 404 response.

Use one idempotency key for retries of the same request. A duplicate returns
the same job without another model call; reusing a key for different input
returns 409. Changing the key deliberately requests new work and can incur
another provider charge. Keep the job ID to reconnect after an app restart.

## Durable execution

SQLite transactions serialize submission and worker claims. WAL is enabled only
on SQLite releases with the upstream WAL-reset fix (3.51.3+, or the 3.50.7 /
3.44.6 backport branches); other runtimes use rollback journaling. Vendor fixes
that are not identifiable from the SQLite version use the conservative fallback.
Stop all workers before changing runtime or journal mode on an existing store.
Leases fence stale
workers. Queued jobs survive a restart. Expired running jobs become
`interrupted`, not automatically queued for another inference request: the
previous provider attempt may already have been billed. An interrupted attempt
requires a new, explicit request to try again. Results remain labelled
`unverified_model_analysis`, with requested/reported model IDs, reported usage
and source-file hashes. Missing usage is unknown, not zero.

Cancellation wins over a late completion and drops that completion's result.
It cannot retract source already delivered to a provider or guarantee no charge.
Errors expose fixed categories, not provider exception text or source snippets.
The model receives no tools; returned tool calls are rejected. Source comments
are untrusted input, not permission to run commands or read the host filesystem.

Defaults allow four pending jobs and 20 submissions per subject per rolling
24 hours, with a 10,000-row service cap. Identical retries do not consume a new
submission. These limits bound this development service; they are not evidence
of large-scale capacity, fairness or production rate limiting.

## Data handling

At most eight files, 64,000 characters per file and 128,000 encoded request
bytes after normalization; the HTTP body also has a 400,000-byte cap. Paths are
logical source labels, never host file selectors. Traversal, `.git`, `.env*`,
key-file extensions, duplicate paths and selected credential patterns are
rejected. Pattern screening does not guarantee source is free of secrets;
review the selected contents before confirming sharing.

Queued source is stored in the private database. Raw source is logically cleared
on cancellation, completion or interrupted-lease recovery. Receipts retain file
paths/hashes and model analysis until deletion. SQLite journals, snapshots and
backups may retain earlier bytes: this is not forensic erasure or encryption.
A hosted operator still needs an encrypted persistent storage/retention policy.
This first remote worker does not export its source or answers to tracing.

The operator-only `python -m bifang.remote_backup` command creates a consistent,
private snapshot without overwriting existing backups. Pending/running jobs are
interrupted in the exported snapshot only, preventing automatic replay after
recovery. See [backup and recovery](AWS_HOSTING.md#consistent-backup-and-recovery)
for restore and retention requirements.

## Verification and remaining deployment work

Tests exercise owner isolation, durable reconnect, duplicate submission,
concurrent claims, lost leases, stale completions, cancellation, quotas,
strict validation and tool-free pinned-model selection. A separate actual HTTP
subprocess rehearsal kills a running worker and restarts the service with
accelerated two-second leases. It preserves completed results, marks the
ambiguous attempt interrupted and confirms no automatic second inference.
The temporary service and state are removed afterward.

One further check used the actual authenticated loopback API and a single live
Token Factory Nano request for an original synthetic authorization example.
The request completed with a receipt (657 reported tokens); resubmitting the
same idempotency key returned that result without another model call. The
answer suggested a suitable correction but imprecisely described the original
return value as boolean `True` instead of a truthy string. It remains unverified
model analysis, not executed correctness evidence. No private source was sent.

This SQLite rehearsal is not a LangSmith Agent Server deployment. Managed
hosting still needs the LangGraph adapter, its persistence/auth integration,
restart/cancel proof on that runtime and entitlement confirmation.
[LangSmith Cloud](https://docs.langchain.com/langsmith/deploy-to-cloud) requires
Plus or above and an application working with `langgraph dev`.
[Authentication and authorization](https://docs.langchain.com/langsmith/auth)
must isolate each client's threads/resources; a LangSmith administrator key
must never be shipped in a phone app. Engine suggestions do not replace actual
executed regression checks.

The owner subsequently selected an [AWS hosting path](AWS_HOSTING.md), avoiding
the need for LangSmith managed deployment. Keep this SQLite state on a private
local persistent volume, not ephemeral function storage or a shared network
filesystem. The isolated AWS host and private review worker are running;
see the hosting document for verified scope and remaining gates.

Next: integrate this bounded review operation into the selected runtime, then
extend remote workflows with isolated implementation, durable human approvals,
independent checks and separate Apply. Build iOS/Android clients against the
authenticated contract with credentials in platform secure storage.
