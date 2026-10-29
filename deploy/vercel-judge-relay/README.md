# Bifang inference-only relay bundle

Local preparation, not deployment authorization. This directory is a template;
use `scripts/build-vercel-judge-bundle.py` to assemble its three reviewed Bifang
modules and metadata into a fresh directory outside the main repository.
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
Unset/missing credentials make app initialization fail closed. No credentials
are included in this bundle; `.env` files must remain outside it. The relay
exposes no agent-execution, file-upload or training endpoints.

Validate dependencies from `uv.lock` in the chosen interpreter, then check
authentication, live model catalog, actual desktop coding, streaming and cleanup
at the hosted HTTPS URL. Confirm abuse controls and availability for judging.
The relay has no shared quota system, no optional embedding API and no uptime
proof. Health alone does not prove upstream inference or free judge access.
