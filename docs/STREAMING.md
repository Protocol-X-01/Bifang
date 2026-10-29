# NVIDIA/Nebius streaming transport

The prior adapter parsed each streamed tool delta as a complete tool call.
Continuation chunks commonly omit the ID/type/name and contain only argument
fragments. Broad exception suppression dropped those chunks, leaving partial
JSON arguments, losing final usage events and hiding protocol errors.
Eight new transport tests reproduced these failures before the repair.

The local source now parses SSE event boundaries, including multiline data,
assembles arguments by tool index and emits complete tool calls only at a
completion boundary. Missing/conflicting IDs, non-object JSON arguments,
length/content-filter termination and malformed/error events are visible
failures rather than silently ignored actions. Error text does not quote raw
upstream payloads. Event/content/argument sizes and tool indices are bounded.
The adapter does not retry a failed stream or execute incomplete fragments.

Requested and server-reported model identifiers stay separate. Usage-only
events are propagated when the service supplies them, and counters/history
retain those real reports. Missing usage is not estimated as measured usage.
The code does not assume every endpoint supports requesting usage explicitly.

Nested provider/routing generators close deterministically on cancellation.
An additional end-to-end cancellation test reproduced an open HTTP response
after closing the agent stream; explicit nested closure fixed it.

Fourteen tests in `tests/test_streaming_transport.py` cover NVIDIA and Nebius
adapters with real HTTPX mock streaming, interleaved calls, malformed and
abrupt streams, multiline SSE, actual read-file execution, durable routing
receipts and direct/whole-agent cancellation. No paid model calls were needed.
The complete local backend suite passes 179 tests.

The bounded live source check on 2026-10-23 also passed against Token Factory
Ultra: two streamed requests, one actual fixture-file read and an exact final
answer. Requested and reported model IDs matched. Neither response supplied
usage counters, so usage remains unknown rather than reported as zero.
The metadata-only receipt is `docs/evidence/streaming-live.json`.
Reproduce explicitly with a private environment-file path and a fresh output:

```sh
PYTHONPATH=src .venv/bin/python scripts/smoke-live-streaming.py \
  --live-env-file /absolute/path/private.env --output /absolute/path/new-report.json
```

This makes at most three paid model calls, caps each at 1,024 output tokens,
uses a 180-second overall timeout and exposes only a read-only synthetic file.
Memory, durable history, tracing and background services are disabled.

This is not proof of every hosted provider's behavior or a performance
benchmark. OpenAI/Anthropic/OpenRouter
adapters are outside this repair. A new local Debian package includes the
repair and passes the synthetic native history/model-selection regression.
However, that test uses the non-streaming desktop HTTP route. Execution of
SSE inside the frozen binary still needs its own check before claiming that
delivery boundary is complete; see `LOCAL_NATIVE_VALIDATION.md`.
