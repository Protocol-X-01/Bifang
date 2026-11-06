# Bifang inference-only relay bundle

Local preparation, not deployment authorization. This directory is a template;
use `scripts/build-vercel-judge-bundle.py` to assemble its reviewed Bifang
five modules and metadata into a fresh directory outside the main repository.
Do not deploy the full desktop repository or its Python 3.11-only metadata.

The generated bundle explicitly selects managed Python 3.12 with FastAPI in
`vercel.json`. This avoids a static-site deployment when automatic detection
does not recognize the imported application factory. The desktop's Python
3.11 requirement is unchanged. Credentials are supplied only at runtime.

The generated bundle also includes an optional `Dockerfile.vercel`, excluded
from uploads by `.vercelignore`. Vercel documents its OCI
container runtime as beta on all plans:
https://vercel.com/docs/functions/runtimes/container
It can preserve Python 3.11 independently of the managed Python runtime.
Set the project's non-secret `PORT` setting to `10000` before a container
deployment so Vercel's expected port matches the listener. The default
`app.py` entrypoint and `.python-version` also support separate local Python
3.12 ASGI tests. The desktop's interpreter requirement is unchanged.

The current relay's hosted HTTPS validation is recorded in the main project's
`docs/VERCEL_SETUP.md`; generated bundles are snapshots, not deployment proof.
Account/project selection, deployment, plan changes and upstream-key transfer
require explicit approval. A beta
feature's documentation is not proof it is enabled or reliable for this account.
No project ID or guessed team ID is supplied. Vercel can automatically assign
the first deployment to production even when preview/staging was requested;
inspect the returned target and remove unintended preliminary deployments.

After approval, configure separate `NEBIUS_API_KEY` and cryptographically random
`BIFANG_JUDGE_TOKEN` secrets server-side, never in source or public variables.
Also set `BIFANG_JUDGE_TOKEN_EXPIRES_AT` as an RFC 3339 UTC timestamp; for the
Nebius x NVIDIA hackathon judging window, use `2026-12-23T20:00:00Z`. The relay
fails closed if credentials or a valid future expiry are missing and rejects
judge authorization at or after the expiry. Keep the token valid throughout
the authorized evaluation window, then rotate or revoke it. No credentials are
included in this bundle; `.env` files must remain outside it. The relay exposes
no agent-execution, file-upload or training endpoints.

## Public demo access

Set the non-secret production variable `BIFANG_JUDGE_PUBLIC_ACCESS=1` to enable
the public demo page at `/` and anonymous access to the model catalog and chat
completion API. Provider credentials remain server-side. No judge token is
required in this mode; clients that require a key field can use the non-secret
placeholder `bifang-public-demo`. Public inference consumes the project's
Token Factory credits. The configured access expiry still applies.

Public mode also requires `BIFANG_PUBLIC_QUOTA_URL` and the server-side
`BIFANG_PUBLIC_QUOTA_TOKEN`. Every valid completion reserves its request,
requested output tokens and input-body bytes through the shared AWS counter
before contacting Token Factory. The protocol-2 counter atomically enforces
global, per-client lifetime/day and minute limits across deployments. The relay
sends a keyed digest of the platform client IP group, never the raw address.
Unavailable guard returns 503; minute limits return 429 with `Retry-After`;
exhausted allowances return 403 without an automatic-retry instruction. The
daily allowance resets at 00:00 UTC. Public requests accept at most 32 KiB and 8,192 output
tokens. Private mode retains its existing request limits and authentication.

Only the demo, model catalog and chat-completion routes are public. Other
routes return 404. JSON requests from the demo's own browser origin and normal
API clients are accepted. The default remains private access; values other
than `0` or `1` for the public-access setting stop initialization.

Validate dependencies from `uv.lock` in the chosen interpreter, then check
authentication, live model catalog, actual desktop coding, streaming and cleanup
at the hosted HTTPS URL. Confirm abuse controls and availability for judging.
Public completions require the configured shared counter. Embedding routes are
not part of this relay. Health alone does not prove upstream inference or
continued judge capacity.
