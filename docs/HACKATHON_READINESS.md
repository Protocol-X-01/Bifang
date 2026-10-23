# Hackathon readiness — 2026-10-23

## Product and track

Bifang is a desktop IDE for the **Coding and Agentic Engineering** track. The
desktop coding loop is the submission; the longer-term product vision retains
both desktop and mobile clients, with mobile following as a companion for
session review and approvals rather than a second full IDE before the deadline.
KV-cache quantization remains an evidence-driven research thread, not the
product definition or a current serving optimization.

The GPU-acceleration interest was inspired by the prospect of running coding
agents on desk-side AI hardware. NVIDIA now uses **RTX Spark** for its new class
of Windows PCs and **DGX Spark** for its desktop AI supercomputer platform;
both are relevant examples, but neither is currently a tested Bifang local
inference target. The hackathon build gets model inference from Nebius Token
Factory (or a separately configured NIM endpoint), and no local-GPU speedup is
claimed. A local backend can remain a post-submission direction without
weakening the current cloud-backed Track 1 demo.

The official [Devpost rules](https://nebiusglobalaihackathon.devpost.com/rules)
require a working app using an NVIDIA open model on Token Factory or Nebius AI
Cloud, a public code repository with an open-source license and setup README, a
working demo URL, and a public YouTube demo of no more than three minutes. The
submission deadline is October 30, 2026 at 10:00 PDT.

## Verified implementation

- Public commit `1372625f51954c43b2377efd47aa9b0a51141ee9` was downloaded
  into a separate directory and passed `npm ci` followed by `npm run build`.
  Its tracked files match the local working copy byte for byte. This repairs
  a prior truncated upload of `ChatPanel.tsx`; use this commit or a newer
  verified revision rather than the earlier affected revision.
- Python is constrained to `>=3.11,<3.12`; all source files pass Python
  compilation and the current test suite passes (29 tests).
- An agent regression test exercises the model → read-file tool → model
  exchange through the HTTP provider adapter, including nested usage metadata.
  It covers task-schema argument binding and assistant message roles.
- Provider selection is authoritative for streamed and regular requests;
  an NVIDIA-prefixed model identifier no longer overrides the selected
  Nebius endpoint. Eight routing checks cover default/explicit selections
  and refusal to silently fall back from a missing provider.
- The agent's outer task router now preserves the configured deployment
  model and provider for every task type. Automatic task classification no
  longer substitutes a hard-coded NVIDIA endpoint or an unverified model ID.
- Session deletion refuses active agent requests with HTTP 409. A concurrent
  request regression test verifies that the worktree cleanup happens only
  after the chat finishes; desktop submission is also disabled during reset.
- The desktop frontend passes the production TypeScript/Vite build; the
  production dependency audit reports zero vulnerabilities.
- The Tauri bridge now registers file-tree and server-status commands, and
  file nodes serialize the `type` field expected by the frontend. A locked
  Windows GNU `cargo check --tests` passes with a temporary check-only config
  that omits the platform-specific sidecar. This type-check is not a native
  package build or runtime test.
- The desktop New Chat action now closes its server-side session and asks
  before discarding un-applied worktree changes. Unused dashboard, reasoning,
  and verification panels containing fabricated sample metrics were removed;
  no measured performance claims are shown as live data.
- The Linux Python server sidecar builds with PyInstaller and its packaged
  executable successfully serves `/health` on loopback.
- A local OTLP collector test verifies Phoenix span export, and a server test
  verifies non-loopback requests require the configured API key.
- The Rust/Tauri app now uses packaged frontend assets, least-privilege dialog
  capability, a scoped CSP, a private per-user `.env` path, and the bundled
  server sidecar. A native Linux **debug/test Debian package** now builds.
  Vite emits assets to `desktop/dist`, matching Tauri's packaged asset path.
  The extracted app launched under a virtual X display and started a healthy
  sidecar. This is not an installed-app click-through or release-build test.
- The Rust app passes a Windows GNU target `cargo check`; this is compile-time
  evidence only, not a Windows installer or runtime test.
- Prior same-day live checks confirmed both configured inference paths
  authenticated and accepted a tiny Nemotron Ultra request. Do not show API
  keys in logs, repository history, screenshots, or video.
- A live Token Factory Nemotron Ultra rehearsal through the packaged server
  fixed the receipt-parser demo, preserved the original checks, applied only
  `receipts.py`, and passed all five checks. Three approvals were resolved by
  an exact-action automated allowlist. The local report records 7.48 seconds
  for this one run, including server startup; this is not a general performance
  benchmark. The sidecar hash matches the final Debian test package.
- The configured NVIDIA endpoint authenticated and returned text from
  `nvidia/nemotron-3-ultra-550b-a55b`. That endpoint is NVIDIA's public hosted
  API; no self-hosted NIM deployment is established by this result.
- Workspace patch export excludes Bifang/Arca audit directories, preventing
  internal transcripts from being applied to the source checkout.
- Docker now binds on the container interface and refuses non-loopback startup
  without `BIFANG_SERVER_API_KEY`.
- The Docker build now uses the checked-in `uv.lock`, and `.dockerignore`
  excludes environment files and generated assets. The local Docker daemon is
  inaccessible in this environment, so the image itself remains unverified;
  CI builds it on pushes and pull requests.
- The project has an Apache-2.0 license and `.env` is ignored.
- The original supplied archive contains an `.env`; the working release copy
  does not. Never publish or reuse the original archive as the repository
  source. Because the archive was shared during project review and the
  repository is now public, rotate credentials from that file immediately.
  Keep real credentials out of commits, build contexts, screenshots, and
  recordings.

## Not yet demonstrated

- CI jobs previously stopped before execution under an account billing lock.
  Local native compilation was unblocked using development packages extracted
  under `/tmp`, with `PKG_CONFIG_PATH` and a native link search path pointing
  there. System package installation still requires administrator access.
  A release-profile build and clean-machine installation test remain pending.
- The public Apache-2.0 source repository is
  [Protocol-X-01/bifang](https://github.com/Protocol-X-01/bifang). The
  sanitized source tree is on `main`; the original archive was not published.
- No live 8×H200 deployment is evidenced. Token Factory inference does not
  prove that this project provisioned eight H200s.
- KV-cache quantization is a standalone prototype, not connected to the NIM or
  TensorRT-LLM serving path; no speed, memory, or recall claim is supported.
- Phoenix export has not been verified against a live collector. Lobster Trap
  remains an optional proxy and must not be presented as integrated metrics.
- The final public demo URL and ≤3-minute YouTube video are still required.

## Critical path

1. Resolve the GitHub Actions billing lock or use a working build host, build
   the release-profile package, and test the installed desktop app through the
   full approve → edit → diff → apply → test loop.
2. Repeat the successful packaged-server Token Factory rehearsal through the
   desktop UI and verify any separately deployed NIM endpoint. Record exact
   model/deployment details and distinguish hosted NVIDIA API access from NIM.
3. Keep the public Apache-2.0 repository limited to the sanitized working
   copy. Rotate credentials from the supplied archive promptly; confirm no
   actual credentials were used in the public source, build context, or demo.
4. Record and publish a concise demo (≤3 minutes) showing the user-visible IDE,
   Nebius Token Factory, NVIDIA Nemotron, approvals, real diff, and test result.
5. Keep NIM, Phoenix, Lobster Trap, KV-cache benchmarks, and mobile companion
   work on the roadmap unless they strengthen the demonstrated core loop.
