# Implementation closeout — local development

Updated October 23, 2026. The creator has deferred the Devpost draft and
requested that updates remain local, except the subsequently authorized
curated dataset upload to Token Factory (not training). This describes working-copy
changes, not capabilities already shipped in the public preview.

## Fixed and regression-tested locally

The agent and context manager now share one message history from startup,
including the original system instructions. Previously, the separate context
buffer omitted those instructions; after compaction, aliasing the buffers
caused later messages to be appended twice.

Compaction now retains an assistant tool request with its tool results,
counts tool-call arguments when estimating retained context, uses the
configured threshold as its target, and records only actual reductions.
Generated summaries are historical user-level data rather than additional
system instructions. Summary timestamps are created per summary instance.

The tiered provider now accepts the explicit model/provider parameters used
by LLM summarization without passing duplicate keywords to the underlying
adapter. Its close operation delegates to the provider manager.

The context-fix milestone passed 42 backend tests. Its new coverage includes both streaming
and non-streaming message histories after compaction, heuristic and LLM
tool-pair retention, threshold/no-op accounting, large tool arguments, an
LLM-summary provider call, and an actual mocked-HTTP model → file tool →
model exchange with prior-history compaction. No live model request or
long-context recall benchmark was performed for these changes. Token counts
remain estimates, not model-tokenizer guarantees.

Persistent project memory is now implemented and tested locally. The default
is ranked SQLite FTS5 retrieval rather than test-only hash similarity. An
explicit embedding-model setting enables real provider requests, including
different document/query input modes. Async and sync embedders work, failures
do not store fake vectors, model spaces and dimensions are kept distinct,
and default databases are scoped to the original project. Custom database
paths are respected; legacy text is migrated and indexed without declaring
old vectors compatible with a new model.

The memory milestone passed 68 tests. A separate live Token
Factory check made six successful embedding requests to
`Qwen/Qwen3-Embedding-8B`, received 4096-dimensional vectors, ranked the
correct synthetic CSV fact first, passed the default similarity threshold,
and recalled it after closing/reopening the database. This is three facts
and one query, not a general semantic-recall benchmark. See
[memory behavior and privacy](MEMORY_RETRIEVAL.md) and the
[sanitized live report](evidence/memory-live.json). No publication, new desktop
package or TensorRT/KV-cache optimization is established by this work.

Conversation persistence now uses project-scoped transactional SQLite records,
with durable completed turns and explicit API/terminal resume. It keeps full
tool-call/result sequences together and distinguishes failed/cancelled turns
from completed history. The terminal displays restored text and actual new
responses; its streaming generator previously did not yield content. Each
provider manager now owns its clients, preventing cross-session closure.
New audit files are private and uniquely named rather than merged by second.
The local suite passes **202 backend tests** and **9 desktop API tests**,
including dataset curation, task-plan isolation and terminal activity/metrics.
The production frontend builds. The
local Linux release packages include multi-model controls and task plans.
The earlier extracted package passed model selection/history fixtures and a
live Token Factory coding regression. A newer package includes the subsequent
streaming repair and passed synthetic native selection/history checks plus
an independent fresh Ubuntu APT installation and actual live Ultra coding
loop. Its exact installed-sidecar hash matches the retained package.
See [history behavior and privacy](CONVERSATION_HISTORY.md). The extracted
native app also passed actual history selection, rendered restoration,
HTTP-503 recovery with candidate cleanup, and resume after stopping/restarting
the sidecar. This used preseeded synthetic SQLite turns and zero model calls,
not a new live coding demonstration or a fresh-machine package installation.

Native testing exposed a real process-lifecycle defect: killing the one-file
launcher left its server child alive while the UI reported stopped. The sidecar
now runs in an owned process group, so Stop/close cleans up the whole tree.
The successful rehearsal verified health actually disappears before restart,
in-memory sessions disappear, durable history remains and historical commands
are not replayed. Public binaries remain unchanged.

Phoenix now has a real authenticated collector rehearsal, including a bounded
live Ultra → file tool → Ultra exchange. Parent relationships, shutdown and
metadata-only export are covered, including cancellation. Thirteen tracing
test cases include concurrent parent isolation, content/exception exclusion,
missing-dependency visibility and explicit stream closure. See
[Phoenix evidence and remaining limits](PHOENIX.md).

## Remaining implementation gaps, not merely wording

The latest source additionally closes a reproduced command-runner sandbox
fallback: requesting Bubblewrap now fails before subprocess creation if the
executable is missing. Ten agent action-boundary cases and two sandbox cases
pass. This does not prove broad prompt-injection resistance. A new local
sandbox-repair package passes the actual frozen-API regression plus synthetic
native and authenticated Phoenix checks. This exact new package now also
passes fresh Ubuntu installation/live trusted-fixture recording. Namespace
creation was denied in the guest; explicit in-VM sandbox opt-out was used,
not a kernel security bypass or proof of default sandbox operation.
See `SECURITY.md` for exact coverage and other execution-path limits.

| Priority | Finding | Evidence and completion criterion |
| --- | --- | --- |
| Delivery | New desktop functionality is local, not released. | The streaming-repair package passes synthetic model-selection/history fixtures and fresh Ubuntu installation/live Ultra coding. The refreshed 476-component build-notice inventory has no missing notice texts. Final distribution review and publication approval remain required. See `LOCAL_NATIVE_VALIDATION.md`. |
| Local implementation closed | Terminal activity and request metrics now refresh from actual agent state. | Headless rendered UI tests cover task changes, literal markup, requested versus reported model identity, reported token counts and missing usage. Context tokens are labeled estimates; no GPU memory, cost or hidden reasoning is claimed. Native-package verification is still separate. |
| Local implementation closed | Task plans now retain validated per-agent-session state. | `todo_write` replaces the plan atomically; `todo_read`, a read-only session API and terminal Activity panel expose it. Invalid updates preserve the prior revision, cross-agent isolation is tested, and empty lists clear the plan. This state is not durable across new agents/restarts or restored automatically from history. |
| Optional observability | Phoenix production/evaluation operations remain incomplete. | Real collector and live source model/tool traces pass; the exact newer frozen sidecar also passes a synthetic HTTP model/file/error collector rehearsal. Rendered Phoenix UI, automated evaluations, retention and frozen SSE traces still need verification. |
| Conditional | Deployment optimizations are post-hackathon work. | Stability and observability are verified. Additional optimizations tracked for future releases. |
| Optional integration | Advanced metrics integration remains post-hackathon. | Current observability stack (LangSmith + Phoenix) verified. Additional features tracked in `SECURITY.md`. |
| Product validation | Explicit pinned/automatic selection and per-step routing receipts are implemented locally. | Native selection and failure recovery pass against a local synthetic provider; pinned Ultra also passes the live coding fixture. Earlier live Nano performed the read but failed its exact-answer criterion. Broad coding quality, classifier accuracy and savings remain unverified; see `TOKEN_FACTORY_STRATEGY.md`. |

Abstract interface methods and exception-handler `pass` statements are not
automatically missing features. Audit their actual callers before changing
them. Likewise, signing, cross-platform installers and rented GPU capacity
are distinct delivery/deployment tasks, not proof that the coding loop is
unfinished. Keep status language accurate until evidence closes each item.

## Packaging boundary

The public preview's runtime is still source revision
`f3f565601d76ee0191c81f3e903eb8826d9f50dc`. It does **not** contain these
new context fixes. A new local candidate is built and its extracted native
history UI, fresh Ubuntu installation and live coding loop are verified.
Distribution review, release recording and approval still precede release.
Do not commit, push, publish updates,
create a Devpost draft, or submit the entry without the creator's renewed
instruction. Existing public assets have not been removed.
