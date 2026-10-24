# Phoenix tracing: verified local integration

Updated October 24, 2026. These changes are local and are not in the public
preview runtime. Phoenix provides observability, not an execution guardrail.

## What is wired

An agent request is the parent of its model and tool spans. Ordinary file
tools stay inside their span until execution finishes; previously only the
MCP/plugin branches were fully enclosed. Streaming calls now have model spans,
and explicit generator closure ends child spans before the request parent.
Context is task-local, so concurrent requests do not share a mutable parent.
Errors/cancellation record exception types, not exception messages. Explicitly
enabling tracing without its dependencies fails visibly rather than pretending
to export. Closing an agent flushes its tracer, including the terminal path.

Exported attributes are allowlisted: model/provider identifiers, task/tool and
argument names, usage counters, span kinds and error types. Prompt bodies,
argument values, file contents, arbitrary attributes and exception events are
not exported. This is a metadata-only design, not a general secret detector:
do not put sensitive text in model/tool/argument names or project labels.
Local conversation history and audit files have separate content/retention rules.

## Actual collector evidence

An isolated **Phoenix 20.25.0** service received Bifang OTLP HTTP spans using
**OpenTelemetry SDK 1.45.1**. The rehearsal queried spans back through Phoenix's
REST API rather than treating an HTTP collector stub as the real service.

- Synthetic rehearsal: two model responses around an actual file read, then
  a separate sanitized synthetic error. Six spans were retrieved: two AGENT,
  three LLM and one TOOL, with verified parent/trace identities.
- Live rehearsal: **two Token Factory Ultra model requests**, one actual
  synthetic file read and the separate injected error. The six expected spans
  were retrieved without the synthetic prompt/file/exception text or supplied
  credentials. This is an integration check, not an accuracy/performance benchmark.
- The authenticated HTTP API rejected missing/wrong credentials with 401. A
  separate run verified unauthenticated gRPC export returns UNAUTHENTICATED.
  The UI document returned 200; rendered UI navigation was not tested.

Sanitized reports are in [live evidence](evidence/phoenix-live.json) and
[collector/authentication evidence](evidence/phoenix-auth.json). Temporary
services, databases, credentials and synthetic project files were removed.
Automated evaluations, dashboards/cost attribution, retention operation and a
production deployment remain unverified. Source-level tracing does not by itself
prove the feature works in every frozen binary.

The newer local streaming-repair package now also passes an actual frozen-server
rehearsal against the authenticated collector. A local synthetic HTTP provider
caused a model → actual fixture-file read → model cycle, followed by an actual
provider HTTP 500. Six spans were queried back with the expected parent links,
error status, metadata-only content checks and HTTP/gRPC authentication.
The frozen server's port was confirmed closed after process-group cleanup.
No hosted model request or real provider key was used for this check.
See [the exact sidecar-bound report](evidence/phoenix-frozen.json).

The retained recovery-message sidecar has its own subsequent receipt, with
SHA-256 `000009d70dc63c00bad3dd9c27255b5c9a44cdcab6dcdd99bd757c0b60589d65`.
Its real authenticated collector result was rechecked against the saved report:
three synthetic model requests, six linked spans and the same authentication
and selected privacy checks. See [recovery-sidecar evidence](evidence/phoenix-recovery.json).
This is a different binary from the earlier streaming-repair report, not a new
collector run during this audit. Thirteen current tracing regression tests pass.

The first attempt failed during session deletion after the injected HTTP 500:
the server's error connection closed while the helper reused it. The helper
now opens a fresh cleanup connection. The repeated run passed; this was a
rehearsal transport correction, not a change to the shipped agent runtime.
This verifies ordinary completion tracing in that exact frozen sidecar, not
frozen SSE execution, a rendered Phoenix UI or production operations.

## Configuration

For a source installation, install the `observability` extra. New desktop
sidecar builds include it; the Phoenix **server itself** is deliberately separate.

```dotenv
BIFANG_ENABLE_TRACING=1
BIFANG_TRACING_ENDPOINT=http://127.0.0.1:6006/v1/traces
PHOENIX_PROJECT_NAME=bifang
```

Set `PHOENIX_API_KEY` privately when your collector requires authentication.
The collector base URL is also accepted and normalized to `/v1/traces`.
URLs containing credentials/query strings or an ambiguous collector path are
rejected. No automatic HTTP-client instrumentation captures source-code payloads.

For a reproducible, temporary collector check after installing Bifang's dev
and observability extras:

```sh
uv venv --python .venv/bin/python /tmp/bifang-phoenix
uv pip install --python /tmp/bifang-phoenix/bin/python arize-phoenix==20.25.0
PYTHONPATH=src .venv/bin/python scripts/smoke-phoenix.py \
  --phoenix-executable /tmp/bifang-phoenix/bin/phoenix --output /tmp/phoenix-check.json
```

Choose fresh environment/report paths if those already exist. Adding
`--live-env-file /absolute/path/to/private.env` enables the bounded live check:
only the Token Factory key is read, the destination is fixed to the official
Token Factory endpoint, and no more than three 256-output-token model calls
are allowed. The default run uses synthetic model responses and no hosted keys.

To test a built server instead of importing the source agent, add
`--server-executable /absolute/path/extracted/usr/bin/bifang-server`.
This mode uses a local synthetic HTTP provider and rejects combination with
`--live-env-file`; it never sends a real hosted key to the fixture service.

The helper isolates HOME/storage, disables Phoenix telemetry and enables
authentication with temporary generated secrets. HTTP binds to loopback.
Phoenix 20.25.0's gRPC listener defaults to a wildcard address independently of
the HTTP host; authentication is therefore essential, even for a local test.
For a permanent service, restrict network access, protect credentials, configure
retention and authentication, and pin the deployment. See the official
[self-hosting](https://arize.com/docs/phoenix/self-hosting) and
[authentication](https://arize.com/docs/phoenix/deployment/authentication) guides.
