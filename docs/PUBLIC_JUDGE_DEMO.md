# Public judge demo

Open the [public demo](https://bifang-judge-relay.vercel.app). On November 6,
the guarded production page, all seven anonymous metadata checks, Nano streaming
and a browser completion passed. The returned addition fixture passed five
independent input cases. The [guarded deployment receipt](evidence/vercel-public-demo-guard-20261106.json)
identifies the exact source, durable reservations and 475 reported tokens across
the two guarded requests. The [initial public demo receipt](evidence/vercel-public-demo-20261106.json)
retains the preceding deployment separately.

Public access is an explicit relay setting. With `BIFANG_JUDGE_PUBLIC_ACCESS=1`,
visitors can open the demo, choose Nano, Super or Ultra, and send a coding request
without an account or judge token. The provider key stays in Vercel's server-side
secret settings. These requests use the project's Token Factory credits.

The browser page demonstrates model inference. Download Bifang for the complete
workspace, tool approval, check and patch-review workflow. Existing release
identities and their native acceptance evidence remain in [readiness](HACKATHON_READINESS.md).

## Operator setup

Deploy the allowlisted relay bundle with these production settings:

```dotenv
BIFANG_JUDGE_PUBLIC_ACCESS=1
BIFANG_JUDGE_TOKEN_EXPIRES_AT=2026-12-23T20:00:00Z
```

Keep `NEBIUS_API_KEY` as a server-side secret. A judge token is optional in public
mode. Without the explicit public setting, the relay retains its existing
judge-token authentication. The expiry applies in both modes.

Public mode requires the [shared usage counter](../deploy/aws-judge-quota/README.md).
Set its `QuotaUrl` output as `BIFANG_PUBLIC_QUOTA_URL` and keep the matching
`BIFANG_PUBLIC_QUOTA_TOKEN` in a Vercel server-side secret. The counter uses a
single DynamoDB transaction for global, client lifetime, UTC-day and minute
allowances; it receives counts, sizes and a keyed client digest, not raw IPs,
prompts or provider keys. Missing configuration
stops public-mode initialization. A failed reservation never calls Token Factory.

The initial allowance is 1,000 reserved completions, 4,000,000 requested output
tokens and 16 MiB of input bodies, with 60 reservations per UTC minute across
the deployment. Individual requests accept 32 KiB and up to 8,192 output tokens.
The browser requests 2,048. Reservations remain counted if a provider call fails
or is cancelled; redeploying does not reset the allowance. Operators can review
the counts and increase the allowance in the quota stack. These are request
limits, not a currency-denominated spending guarantee.

Protocol 2 adds a 250-request lifetime allowance per client group (1,000,000
requested output tokens and 4 MiB input), a UTC-day allowance of 100 requests
(262,144 requested output tokens and 2 MiB input), and 10 requests per minute.
IPv4 addresses form individual groups; IPv6 addresses share their /64. The relay
uses an HMAC digest so the counter receives no raw visitor address. Visitors on
one network can share limits; these controls do not establish a person's identity.
Minute limits return 429 with a short `Retry-After`. Exhausted allowances return
403 without it, with a clear notice when the daily allowance resets at midnight UTC.

Use the stable production domain above for public access. Vercel Standard
Protection covers generated deployment and preview URLs, including old versions
that predate the usage guard. Anonymous checks verified their completion routes
are blocked while the production domain remains open. This uses Vercel's
[Standard Protection](https://vercel.com/docs/deployment-protection), available
on the existing plan.

The public routes are `/`, `/health`, `/v1/models` and `/v1/chat/completions`.
The relay provides model inference; it does not expose the local agent's session
or file routes. The demo page uses plain text for model output and a content
security policy that permits its exact static scripts and styles.

Check the public deployment without a credential or inference request:

```bash
uv run python scripts/check-judge-access.py \
  --relay-url https://bifang-judge-relay.vercel.app \
  --public --output /private/fresh-public-access-report.json
```

The seven checks cover the page, health, live model catalog and absent private
routes. Confirm a small real completion separately; metadata checks do not
establish balances or future availability.

## Other OpenAI-compatible clients

Use `https://bifang-judge-relay.vercel.app/v1` as the API base. If a client requires
a key field, use the non-secret placeholder `bifang-public-demo`.
For Bifang's local configuration, that means:

```dotenv
BIFANG_DEFAULT_PROVIDER=nebius
BIFANG_NEBIUS_BASE_URL=https://bifang-judge-relay.vercel.app/v1
NEBIUS_API_KEY=bifang-public-demo
BIFANG_NEBIUS_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
```

The placeholder is not a provider credential. Recheck the hosted source and
public-access setting after subsequent deployments; the receipt is a
point-in-time observation.
