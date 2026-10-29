# Lobster Trap: compatibility tested, not enabled

Veea's [Lobster Trap](https://github.com/veeainc/lobstertrap) is an optional
prompt-inspection reverse proxy, not Bifang's executed tool policy or Phoenix
tracer. We evaluated upstream commit
`e49a402864104c19c9a560ad73e06d5493e5d876` without enabling it in the desktop,
Vercel relay or a hosted provider path. No real credential was supplied.

## Executed evidence

The pinned source's `go test ./...` passed. A local binary was built with
`go build -buildvcs=false -trimpath`; VCS stamping is disabled because this is
an extracted source archive, not a checkout. The compatibility helper used
the actual Bifang `NebiusProvider`, that external binary, a synthetic policy
and a loopback HTTP backend. Six backend completions were synthetic; no hosted
model request was made. The proxy's dashboard was disabled and its port closed
after cleanup. See `evidence/lobstertrap-synthetic.json`.

| Probe | Observed at this revision |
| --- | --- |
| Actual provider client, plain completion | Passes; requested/reported model IDs match. |
| Plain-text ingress matching the fixture rule | Denied before backend invocation. |
| Nonstreaming plain-text egress matching the rule | Denied. |
| Denial status | HTTP 200 with a proxy verdict, not an HTTP error. |
| SSE output matching the egress rule | Returned unchanged, without egress inspection. |
| Sensitive path in tool-call arguments | Returned with an ALLOW verdict; arguments not inspected. |
| Injection text inside structured content parts | Parse failure passes through without inspection metadata. |
| Benign test request quoting an injection phrase | Blocked: a demonstrated context false positive. |
| Authorization to synthetic backend | Forwarded correctly. |
| Audit privacy | Raw benign prompt canary absent, declared agent ID persisted. |
| Newly created audit-file mode | 0644 inside an owner-only temporary directory. |

These are specific compatibility/coverage observations, not a general attack
success rate or a claim about every policy/version. Streaming passthrough is
explicit in upstream's pinned
[`proxy.go`](https://github.com/veeainc/lobstertrap/blob/e49a402864104c19c9a560ad73e06d5493e5d876/internal/proxy/proxy.go).
The pinned [`openai.go`](https://github.com/veeainc/lobstertrap/blob/e49a402864104c19c9a560ad73e06d5493e5d876/internal/proxy/openai.go)
extracts message text, not tool-call arguments. Do not interpret its response
metadata as an authorization decision for Bifang tools.

## Reproduce without provider keys

Obtain and verify the selected upstream revision separately. With a binary
built from it and Bifang's locked source environment:

```bash
uv run python scripts/smoke-lobstertrap.py \
  --executable /private/lobstertrap \
  --upstream-revision e49a402864104c19c9a560ad73e06d5493e5d876 \
  --output /private/fresh-lobstertrap-report.json
```

The revision label is operator-supplied; verify its source archive independently.
The report records the executable and fixture-policy hashes. It deliberately
captures the above known gaps, so passing this compatibility probe does **not**
mean production guardrail readiness. Do not point it at a real provider: its
backend is created locally by the helper and it accepts no provider key.

## Decision and integration gates

Keep the normal Token Factory/judge-relay path unchanged. An optional proxy
must not silently break streamed coding, hide output inspection gaps, turn
policy denials into apparent ordinary model answers, or log private source
paths/declared identifiers without deliberate retention controls.

Before enabling, address streaming/tool/structured-content inspection,
fail-open parsing behavior, denial semantics in the client, legitimate coding
false positives, bounded buffering, local authentication/dashboard exposure,
and private audit-file permissions/retention. Re-run real transport and client
tests against the exact candidate. The upstream README states MIT; no separate
license file was present in the inspected archive. No upstream source or
binary has been vendored into Bifang's release; preserve applicable notices
and confirm distribution terms before doing so.

Bifang's existing approvals, workspace checks and command sandbox remain the
executed controls. Phoenix is metadata-only observability, not enforcement.
Neither component establishes immunity to prompt injection or hostile code.
