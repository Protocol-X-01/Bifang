# Durable remote coding decisions

The coding service keeps proposed code, check results and approval decisions
together in a durable project. Desktop and mobile use the same workflow.
Hosted coding deployment evidence is linked below; individual release packages
and later working-copy changes retain their own verification scope.

## Start coding

Choose **Work on existing code** to select files, or **Build a new project** to
start with an empty project. A new project needs a brief, up to eight initial
file paths, and an explicit check command; no placeholder files are required.
The suggested initial paths are editable. Generated tests should be reviewed
alongside the implementation before approving a run.

The model selector loads the connected service's provider catalogue through
authenticated `GET /v1/models/{provider}`. Switching provider clears the previous
selection. A discovery failure offers a retry; it does not invent a model ID.
The service caches successful discovery for 30 seconds. The proposal worker
checks the chosen model against the provider catalogue again before generation.

## Exact candidate, explicit decisions

Each job holds a selected source snapshot, writable-path capability set,
explicit check arguments and check deadline. The first submission creates an
owner-scoped hosted project snapshot. Subsequent work against that project
must match its current source revision. The limits remain deliberately bounded:
eight selected/input-output paths, 128 KB of normalized source, 64 KB per
proposed replacement and a check deadline of at most 60 seconds.

The durable sequence is:

1. Queue and lease a tool-free model proposal using the exact selected provider
   and a model verified against its live catalog. Treat returned content as
   untrusted JSON, not execution evidence.
   Generation receipts retain requested/reported model IDs and allowlisted
   provider usage. Missing reported usage remains unknown, not zero.
2. Present proposed complete-file replacements. Only explicitly writable paths
   are accepted; other selected files remain unchanged. Source and credential
   paths, traversal and inconsistent file/directory paths are rejected.
3. Record a human write decision bound to the complete candidate's content hash.
   No hosted project source changes at this step.
4. Record a separate human check decision. The check command came from the
   request, not a model execution claim. Only an independent worker may record
   the executed receipt; no client-provided `passed` flag exists.
5. Require a passing receipt for the exact candidate and command, followed by
   separate patch review, staging and Apply decisions.
6. Apply updates only the owner's hosted project snapshot, transactionally,
   if its baseline revision is still current. It does not modify a desktop
   checkout. Desktop checkout Apply must still use its own reviewed patch and
   clean-baseline checks.

Every decision is owner-scoped and durable. Identical decision retries do not
advance another step. A denial cannot become an approval by replaying a request.
A late model or check completion cannot revive cancelled or expired work.
Ambiguous expired attempts become interrupted, never automatically requeued for
another provider call. The proposal worker cancels its pending provider
coroutine when ownership of the lease is lost or the user cancels.

## Backup and execution boundaries

The online backup now recognizes coding tables. In the exported snapshot only,
nonterminal coding work becomes interrupted, including pending approvals and
staged candidates. Restoring an older approval cannot automatically run checks
or Apply. The active store is unchanged. Hosted project source is retained as
project data; this is distinct from the read-only review worker's transient raw
source policy. Authenticated deletion of a terminal job clears its stored
request/proposal/receipt, preserving an idempotency tombstone. Deleting an owned
project requires all its jobs to be terminal and removes its source and those
jobs' retained payloads. This is logical removal, not forensic erasure from
SQLite pages or older backups. An operator backup-retention policy remains needed.

## Authenticated API contract

The new routes are absent by default. `create_remote_app` enables them only
when explicitly supplied the shared private coding store, a proposal runner
and an independent check runner. Incomplete configuration fails startup. The
deployed public entry point now runs the exact privately tested coding image,
with [public promotion and recovery evidence](evidence/aws-public-coding.json).
The image opts in through the fixed operator path
`BIFANG_REMOTE_CODING_SOCKET=/run/bifang-executor/check.sock`, with only that
private IPC directory mounted read-only. Root-peer verification is required
before sending source. Startup, health, submissions and check approvals probe
the broker; proposal generation checks again before requesting inference.
Unavailable execution fails closed rather than spending on uncheckable work.

All routes below use the existing bearer authentication and owner isolation.
Submission requires an `Idempotency-Key`; bodies are streamed and bounded.
Validation responses withhold source and parser details.

| Route | Meaning |
|---|---|
| `GET /v1/coding/schema` | Submission and strict decision JSON schemas |
| `POST /v1/coding/jobs` | Submit an explicitly shared selected snapshot |
| `GET /v1/coding/jobs` | Latest 20 owned jobs; no proposal bodies in list |
| `GET /v1/coding/jobs/{id}` | Durable state, proposal, model metadata and receipt |
| `GET /v1/coding/jobs/{id}/patch` | Untrusted unified diff and exact candidate hash |
| `POST /v1/coding/jobs/{id}/decisions` | Explicit action, hash and strict boolean approval |
| `POST /v1/coding/jobs/{id}/cancel` | Fence late completion and cancel the worker coroutine |
| `DELETE /v1/coding/jobs/{id}` | Clear a terminal job, retaining its retry tombstone |
| `GET /v1/coding/projects/{id}` | Owned hosted snapshot, not a host filesystem path |
| `DELETE /v1/coding/projects/{id}` | Remove owned source after finishing/cancelling jobs |

Decision actions are `writes`, `check`, `review`, `stage` and `apply`. The body
contains only `action`, `candidate_sha256` and `approved`; callers cannot inject
a subject, alternate command or passing receipt. API tests exercise the full
sequence using synthetic workers and confirm that exported patches pass an
actual `git apply --check`. That check validates patch syntax/applicability,
not the proposed program's correctness.

The HTTP/state tests use synthetic model responses and internal check receipts.
Actual sandbox execution and public promotion now have separate proofs below.
The remaining client integration gates are:

- Packaging and fresh-install verification of the newer Remote forge client.
- iOS and Android secure storage, builds and device walkthroughs.

The [AWS service](AWS_HOSTING.md) preserves the previous review receipt and
owner isolation while enabling coding. Each receipt identifies its own frozen
image; a newer client build does not change the hosted image's source identity.

## Actual isolated execution

The [AWS executor receipt](evidence/aws-executor.json) identifies the tested
module, Python execution image and gVisor runtime. The original synthetic
boundary-check program fails its unchanged tests; the corrected candidate
passes. Separate executed probes verify UID 10001, no provider/AWS environment,
no host state/socket mounts, read-only source, blocked outbound/metadata
networking, timeout and output bounds. A real Unix-socket disconnect cancels
the running execution and removes its container and private snapshot. These
are selected boundary checks, not an exhaustive escape analysis.

The host runtime is checksum-pinned `release-20261019.0`; its installation
preserved existing Docker settings and used reload rather than restart.
The named runtime is verified through operator-owned binary checks and Docker
control metadata, not an in-container `dmesg` string. Installation follows the
[official release-bundle guidance](https://gvisor.dev/docs/user_guide/install/).

`remote_executor.py` is a narrow, Python 3.9-compatible standard-library
operator component; the application remains Python 3.11. Its Unix-socket
contract accepts only selected files, exact argv and a bounded timeout. Image,
runtime, host mounts and environment are operator-controlled. It uses no shell
on the host and refuses unavailable sandbox support rather than using runc or
host execution. Check output is continuously bounded; the v1 receipt retains
its digest and exit status rather than raw logs.

The initial receipt above used a temporary broker. The newer
[peer-checked revision](evidence/aws-executor-peer.json) repeats those executed
checks, and the [persistent broker proof](evidence/aws-executor-broker.json)
verifies a UID-10001 client with no Docker socket. Forced broker termination
cleans the running check and snapshot; an already-mounted client reconnects
after restart. Preserving the socket directory inode avoids a stale read-only
bind mount. The directory is root-owned, group-readable/traversable only by
the API's dedicated group; the socket is mode 0600 and owned by UID 10001.

The first broker installer verification caught systemd resetting a manually
changed directory group. Assigning the service's dedicated group fixed the
cause; the failed attempt remains separate from the successful repair/proof.

## Private deployed coding workflow

The [coding-stage receipt](evidence/aws-coding-stage.json) identifies a frozen
97-input API build and its exact image. A single real Token Factory Nano job
reported 575 tokens and proposed the intended off-by-one fix. The operator
fixture checked its AST before making explicitly scoped automated decisions.
It then exercised write approval, an actual API-container restart preserving
the pending check approval, real gVisor execution, patch review, staging and
separate Apply. The tests and hosted project stayed unchanged until their
respective permitted steps; desktop source was never modified.

These are deployed private-loopback checks with temporary fixture identities,
not a human UI walkthrough or a claim that every generated patch is correct.
The fixture tokens were removed after the proof. The exact tested image was
then promoted to public HTTPS using the existing real client-token registry
and production store, after a consistent backup. External checks verified auth,
schema access, old-receipt preservation and rejection of a credential path
before inference. Restarting only the private broker preserved the same API
container and socket-directory inode, and coding health recovered. No additional
model request was needed for those promotion checks. The first inline restart
fixture failed shell parsing before restarting anything; a separate argv-only
fixture corrected that harness failure and passed.

## Desktop Remote forge

The [October 28 public-service fixture](evidence/public-coding-flow-20261028.json)
exercised the HTTPS coding path with judge credentials and one real Nemotron Nano
proposal (501 tokens). Before approving its synthetic writes, the fixture verified
the proposal's AST against the exact intended boundary fix. Owner isolation,
idempotency, premature Apply rejection and stale-candidate rejection passed.
The candidate-bound check completed successfully; review, staging and separate
hosted Apply followed while preserving the tests. The downloaded patch also passed
actual Git check/application in a temporary local folder, matched the hosted
revision byte-for-byte, and passed the same local tests. These are automated API
and patch-handoff checks; native desktop and paired-phone interaction remain
separate acceptance gates.

The newer local desktop source adds a Remote forge workspace. Enter the HTTPS
service origin and an owner/judge client token. Requests use the native transport,
not browser CORS exceptions. The client rejects non-HTTPS origins, credentials in
URLs, redirects and arbitrary routes; it bounds request/response sizes and request
time. Tokens remain session-only in native process memory after connection and
are not written to browser storage or a configuration file. Disconnect or app
exit drops the session; this is not a claim of forensic memory zeroization.
The transport uses the documented [reqwest client controls](https://docs.rs/reqwest/0.12/reqwest/struct.ClientBuilder.html)
without disabling certificate verification or adding a browser-origin exception.

Choose up to eight individual UTF-8 files with the source picker; imported files
start read-only. Preview their contents, edit relative paths, and explicitly
enable the writable subset. Snippets and an advanced JSON editor remain available.
Binary data, credential paths, duplicates and oversized files are rejected locally.
Imports preserve BOM and line-ending bytes. Reading files does not submit them;
source changes reset sharing consent, and submission waits for imports to finish.
Choose the exact check argv and confirm sharing before requesting a proposal.

Before enabling an approval, the client independently hashes the fetched baseline,
checks its revision against the job, reconstructs the complete candidate from
bounded writes to allowed paths, and recomputes its SHA-256. It implements the
server's Python JSON manifest encoding, including ASCII escaping and Unicode
codepoint ordering. Cross-language golden vectors verify this interoperability.
The displayed full-file replacement diff is generated locally from those verified
files, not trusted from a service-supplied patch string. Tests actually apply the
generated patches with Git and check byte-exact results, including CRLF, Unicode,
empty/new files and missing final newlines. These integrity checks are not remote
execution attestation or proof that a change is correct.

Each decision binds to the verified candidate, and review/stage/Apply also require
a matching passing check receipt. Each step has its own manual confirmation.
Already-applied jobs can verify their current hosted candidate, but only show a
clearly labelled historical service diff, with no approval control. A changed
baseline or digest disagreement prevents decisions. Refresh retrieves durable
state after reconnect. Apply changes the hosted snapshot only; the existing
local checkout Apply flow is independent.

Identical submission retries reuse one in-memory idempotency key. Disconnecting
does not cancel hosted work; reconnect and inspect recent jobs before starting
another task. Delete task payload and project source separately once terminal;
operator backups can retain older content. These client changes are not yet in
the published preview-5 binary. The [native client receipt](evidence/native-remote-coding.json)
records a real public-HTTPS task: 398 reported tokens, actual gVisor execution,
all five scoped UI decisions and reconnect before check approval. The first
walkthrough hit a job-list rendering race after write approval; a repaired
harness resumed that same pending job without requesting inference again.
The operator accepted only an AST-equivalent harmless boundary fix before
automating the UI decisions. This is not a human usability study or mobile proof.

The [newer candidate-verification receipt](evidence/native-candidate-verification.json)
adds actual native multi-file import and independent WebKit hashing against the
live API. One further Nano proposal used 569 tokens. Two harness observation races
were preserved separately; the same job continued through real checking and Apply,
then a read-only native reconnect verified the applied snapshot without another
model request. It is not a single uninterrupted walkthrough.
