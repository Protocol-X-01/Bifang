# Public judge demo

Open the [public demo](https://bifang-judge-relay.vercel.app). On November 6,
the production page, all seven anonymous metadata checks and a real Nano
completion passed. The returned addition fixture passed five independent input
cases. The [deployment receipt](evidence/vercel-public-demo-20261106.json)
identifies the exact source and 258 reported production-request tokens.

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
