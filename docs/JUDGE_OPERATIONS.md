# Judge access: operator runbook

This checklist is not an uptime guarantee or permission to publish, purchase,
schedule jobs or change credentials. The retained native package completed a
real task through the relay (`evidence/native-vercel-relay.json`). Availability
through judging remains an open gate.

## Access checks without inference

From the locked Python 3.11 source environment:

```bash
uv run python scripts/check-judge-access.py \
  --relay-url https://approved-relay.example \
  --judge-token-file /private/judge.json \
  --output /private/fresh-access-report.json
```

Replace the example origin with the approved URL in `VERCEL_SETUP.md`. The
owner-only private JSON file contains `judge_token`, never the provider key.
Keep it outside the repository. Do not put tokens in arguments, URLs, public
documents or screenshots. The tool does not load `.env` or an inherited key.

Seven GETs check health, missing/wrong-token rejection, authenticated model
catalog, and absence of agent/source/environment routes. No completion request
is sent. HTTPS is required; redirects are never followed. Metadata is bounded
to 128 KiB. Reports exclude response bodies, unknown model IDs, exception
details and credentials. New report files are owner-only and never overwrite.

Exit 0 means these point-in-time checks passed; exit 1 means a check failed;
exit 2 means invalid input or report destination. These checks do not prove
inference, balances, native installation or long-term availability. Retain
the separate real native-task evidence with its exact package identity.

## Observation before enforcement

One rule is published for exact `POST /v1/chat/completions`: 120 requests per
60 seconds per IP, exceeded action **log**. It does not throttle, deny or
challenge. After the creator published it, the live firewall is enabled with
one active valid rule and no drafts. A bounded preview probe sent 125 empty,
unauthenticated requests: all returned 401, and the host/rule-filtered WAF
query reported exactly five log events. No model/messages/key was supplied,
so no valid inference request was sent. This verifies preview matching and
log-only behavior, not an enforcing quota; see `evidence/relay-firewall-observation.json`.
CLI 65.2.0 supports explicit project selection; the older 54.18.2 rejected it.

For subsequent changes, verify the actual configuration, enablement, URL
coverage and matching dashboard traffic after the operator publishes. Do not send
paid inference bursts merely to fill a counter. Consider enforcing changes
only after reviewing legitimate traffic and effects on judge access. Do not
enable browser challenges on an API. No enforcing rule, global concurrency
quota, shared token budget or paid storage has been deployed.

Vercel documents Hobby's one rate-limit rule, included usage and per-region
counters in its [WAF guide](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting).
Regional IP counters are not a global per-judge spend ledger. In-memory Python
counters reset across instances/cold starts; do not claim they are shared.
Hobby limits can pause service; verify actual remaining capacity before judging.

## Funding and availability gate

The [official rules](https://nebiusglobalaihackathon.devpost.com/rules) require
free testing access through December 15, 2026 at noon Pacific time and permit
private-site credentials. Do not assume an exception for arbitrary daily or
lifetime judge caps, offline-only replies or requiring a paid provider key.

Before distributing judge access, the owner must confirm:

- Billing is active and the applicable credits/payment arrangement remains
  usable through judging, not just trial credit expiring earlier. Keep balances
  and billing identifiers private.
- Hosting/provider capacity covers ordinary judging, with an incident contact
  and a way to restore access. One successful task is not an uptime guarantee.
- The approved endpoint, private judge credential and current downloadable
  build work from a clean judge machine. Do not expose the local agent API.
- Planned checks and usage review have a named owner. This document creates
  no recurring automation; scheduling requires separate authorization.

## Incident handling

Inspect check names/statuses, not raw responses. Working health with a failed
catalog can indicate authentication, provider availability, billing or catalog
changes; this check alone cannot identify which. Verify privately rather than
silently switching providers or substituting static answers.

Revoke compromised credentials through approved secret settings, replace them
through the private channel and retest. Never print raw project-protection
JSON: some APIs encode bypass secrets as object keys. Display only counts or
allowlisted fields. The obsolete automation bypass was revoked; direct HTTPS
checks do not generate another one.

Keep new reports separate from immutable captures. Revised source, binaries,
video and judge instructions still require renewed publication permission.
