# Vercel relay preview

## Current verified deployment — 2026-10-24

The creator approved a relay-only preview and server-side Token Factory key
transfer. `protocol-x/bifang-judge-relay` is on the active Hobby plan; no paid
upgrade or integration was enabled. The working preview is
https://bifang-judge-relay-gn4sjo4ht-protocol-x.vercel.app . It requires a separate
judge bearer token, not the provider key or a Vercel login. Keep that token
private until distributing judge instructions through the approved channel.

The deployed v3 bundle uses the explicit `fastapi` framework, `app.py`, the
locked dependencies and managed Python 3.12. The desktop remains Python 3.11.
Vercel's successful build installed from `uv.lock`. Eleven files were uploaded;
environment files, verification artifacts and the optional Dockerfile were
excluded. HTTPS checks verified health 200, missing/wrong judge tokens 401,
disabled models 400, and absent agent/source/environment routes 404. The live
catalog returned the three configured NVIDIA models. Actual `NebiusProvider`
Ultra completion and Nano SSE completion passed, reporting 43 and 134 tokens.

Two preliminary deployments were assigned production automatically, even
when preview/staging was requested. Both were removed; the production alias
returns 404. The first had no inference runtime; the second had no production
credentials. Neither is the working preview. The container was not selected
by automatic detection, so OCI runtime support remains unverified here.

Evidence: `evidence/vercel-relay-hosted.json`. A subsequent retained-package
native desktop task through this endpoint passed with judge-only credentials,
command sandboxing enabled, approvals, apply and five unchanged checks; see
`evidence/native-vercel-relay.json`. Neither result is a shared-quota, load or
judging-period uptime result. Hobby limits
may pause service; provider inference consumes Token Factory credits. No
unconditional free judge-access guarantee follows. The public repository,
desktop release and video remain unchanged.

## Earlier onboarding and local evidence

The creator selected Vercel instead of the earlier Render proposal. Global
agent setup follows the official [onboarding guide](https://vercel.com/get-started.md).
CLI authentication, the existing enabled global plugin and the shared
`https://mcp.vercel.com` connection are verified, including documentation search
and an authenticated team-list request. At the earlier onboarding checkpoint,
no project had been created or linked and no provider credentials uploaded.

That was platform onboarding, not a deployment. Keep the current desktop app,
public repository and video unchanged until their publication gates are met.
Do not run a project-aware mutation before confirming the intended account,
team and project. Do not upgrade plans or install billable integrations
without explicit approval. Use private secret settings, never public frontend
environment variables, for any future relay's upstream credentials.

## Python boundary before deployment

Vercel currently supports Python 3.12, 3.13 and 3.14, with 3.12 as default;
see its [runtime-version documentation](https://vercel.com/docs/functions/runtimes/python/python-version).
Those versions describe the managed Python runtime, not all Vercel hosting.
Its [container runtime](https://vercel.com/docs/functions/runtimes/container)
is documented as beta on all plans and can use an image's own Python 3.11.
Account availability and actual hosting behavior still need verification.
The desktop/server source project deliberately requires Python 3.11, including
the TensorRT compatibility boundary. Do not relax that root requirement just
to make a Vercel deployment pass. Prepare the inference-only relay in a
separate supported runtime, with its own dependency and ASGI-entrypoint
validation, before creating a hosted project. It does not need TensorRT or
model weights; inference must continue to call Nebius Token Factory.

## Relay-only local bundle

Run `scripts/build-vercel-judge-bundle.py --output /absolute/fresh/path` from
the locked source environment. The exporter copies thirteen allowlisted relay,
metadata, license and verification files, not the desktop/agent code or `.env`.
Every payload has a SHA-256 manifest and byte-for-byte readback. The generated
package has an independent dependency lock and `.python-version`; the desktop's
`>=3.11,<3.12` requirement is unchanged.

The current v2 local bundle passes clean dependency installations and synthetic
ASGI entrypoint/auth/catalog/completion/SSE checks under Python 3.11.15 and
3.12.13. Its twelve files total about 72 KB before dependency installation.
Neither desktop agent nor GPU modules are imported. Source regression tests
also verify the allowlist, output non-overwrite, symlink rejection and shared
model-ID constants. This is not Vercel build, TLS, cold-start, live inference
or hosted desktop verification.

`Dockerfile.vercel` is an optional OCI entrypoint, excluded from the current
managed-Python upload. `vercel.json` explicitly selects FastAPI so the upload
cannot silently default to a static website. For an independently validated
container deployment, remove the Dockerfile exclusion and set the project's
non-secret `PORT` to `10000` to match the listener. The generated `app.py`
can also be checked separately with the supported managed Python interpreter.
Both paths require separately approved server-side provider and judge-token
secrets. `verify.py` uses only synthetic credentials and is excluded from
deployment, together with private environment files and validation artifacts.

The earlier full-source Docker-based relay image built successfully in a
disposable Ubuntu VM, but it was not run before the switch to Vercel. That
result does not cover the new minimal bundle's `Dockerfile.vercel`. Docker build
success is not proof of Vercel runtime compatibility, TLS, streaming behavior,
funded judge access or a deployed endpoint. The earlier Render blueprint is
historical preparation and must not be applied as the active hosting plan.

Next checks are appropriate abuse controls and funding/availability through judging.
The creator has since published a log-only WAF observation rule. Its coverage
of this preview is verified with empty unauthenticated probes and five matching
log events; no enforcing quota or challenge was enabled. See
`evidence/relay-firewall-observation.json` and `JUDGE_OPERATIONS.md`.
The overall hackathon submission is not complete because a relay is live.
