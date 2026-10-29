# Private judge inference relay

The creator selected and approved Vercel. A relay-only Hobby preview is now
deployed; see [Vercel verification](VERCEL_SETUP.md) for its exact URL and
evidence. The Render proposal below is historical, not authorization to create
a service. The public repository and desktop release remain unchanged.

Status: external HTTPS verifies judge-token rejection, three-model catalog,
an actual Ultra provider-client response and Nano SSE response. The two hosted
checks reported 177 tokens. A separate retained-package native desktop coding
loop through the relay now also passes with judge-only credentials, Bubblewrap
enabled, exact-action approvals, patch apply and five unchanged checks
(`evidence/native-vercel-relay.json`). This is not proof of shared quotas or
availability throughout judging. No paid plan
was enabled. Provider inference consumes the creator's Token Factory credits.

Use [the operator runbook](JUDGE_OPERATIONS.md) for the no-inference access
check, observation-rule rollout, funding and incident-response gates.
The [judge walkthrough](JUDGE_QUICKSTART.md) covers installation, private
configuration and the receipt-repair task for the newer local candidate.
`evidence/judge-access-metadata.json` records seven current metadata checks;
the published rule now has verified preview log events, but remains observation
only, not active throttling or a shared spend quota.

## Why a relay

Judges should not need to buy Token Factory credits or receive the creator's
provider key. The desktop can instead use a separate judge-only bearer token
and an HTTPS relay. Inference still runs on NVIDIA models in Token Factory;
the relay needs CPU hosting only, not GPU rentals or Nebius AI Cloud.

The relay exposes only health, live model catalog and chat-completion routes.
It does not create agent sessions, access projects, run commands, upload files
or start training. Coding tools execute in the judge's local desktop, with
the normal approval and sandbox boundaries. Never publicly expose the normal
Bifang agent API as a substitute for this inference-only service.

## Local preparation

Supply `NEBIUS_API_KEY` and a separate cryptographically random judge token
of at least 32 characters through a private environment or secret manager.
Do not put either in source, images, CLI arguments or testing screenshots.
Run from the locked Python 3.11 environment:

```bash
uv run python -m bifang.judge_relay
```

Default bind is loopback port 8010. A hosting container binds port 10000;
public use requires an HTTPS reverse proxy. Run one app worker for the
initial private test; this prototype has no shared quota backend.

On the judge's desktop, configure the Nebius provider's base URL to the
approved relay's `/v1` endpoint and its API key to the judge-only token,
not the upstream key. Keep the Nebius provider selected. Supply those private
testing instructions separately, not in the public README or video.

## Earlier Render proposal — superseded, do not deploy

[Render web services](https://render.com/docs/web-services) include a managed
HTTPS `onrender.com` address, so a purchased custom domain is unnecessary.
The smallest paid CPU service is currently listed at US$7/month, before
possible bandwidth/build charges and Token Factory usage; recheck
[pricing](https://render.com/pricing) at creation. An always-on paid service
is preferable for judging. The [free tier](https://render.com/docs/free)
idles after 15 minutes and may take about a minute to restart; outbound API
traffic can also trigger suspension. It is a trial, not reliable judge access.

`deploy/judge-relay/render.yaml` is a review-only
[Blueprint](https://render.com/docs/blueprint-spec). It deliberately uses
`plan: free` until paid hosting is approved and disables automatic deploys.
After explicit approval, review the current paid plan identifier (`0.5c-512mb`
in the current documentation), price, source revision, secret settings and
deployment region before creating the service. Initial creation still builds
and deploys even with automatic updates off. Never apply the blueprint as a
way to bypass the local-only publication gate.

The Dockerfile copies source and locked dependency metadata only; provider
credentials must be injected at runtime. It configures non-root execution,
with no workspace volume. The image subsequently built in a disposable Ubuntu
VM but was not run before the hosting choice changed. The blueprint has not
been validated by Render. Neither build nor local API tests prove deployment
or TLS.

## Verified locally and remaining gates

Synthetic tests cover the real Nebius client through the relay, separate
authentication, fixed upstream URLs, refusal to follow redirects, enabled
model filtering, body/output-token bounds, sanitized upstream failures and
normal SSE byte preservation/closure. An ASGI disconnect after the first SSE
chunk originally interrupted awaited upstream closure; a regression now passes
with cleanup shielded from that cancellation scope. This is a narrow simulated
disconnect check, not a load test. No hosted model calls are made by tests.
The relay does not log request bodies or forward client headers upstream.

A separate in-process rehearsal used the actual Nebius provider client through
the relay and made one live Ultra completion through Token Factory. It returned
nonempty text, matching requested/reported model IDs and 42 reported total
tokens. Live catalog access and unauthenticated rejection also passed. This
does not test a hosted relay URL, external TLS or the full desktop coding loop.

Hosting and server-side secret transfer were explicitly approved for the
isolated Vercel preview. Before distributing access, configure appropriate
edge request/concurrency/time limits and usage monitoring, and review upstream
terms. No distributed quota, SSE-disconnect load test or production abuse
assessment has been completed. Optional embeddings
are not relayed; this is the core chat/tool-model path, not all provider APIs.

Before marking judge access ready, independently verify HTTPS, an authenticated
desktop coding loop, wrong-token rejection, no upstream-key exposure, billing
and availability through the judging period. A 200 health response alone
does not prove model access. Ensure abuse controls do not obstruct legitimate
judging. The [event rules](https://nebiusglobalaihackathon.devpost.com/rules)
require free, unrestricted testing access through judging end and permit
private-site credentials in testing instructions. Hosting a relay alone does
not provide the required public test-build and video links.
