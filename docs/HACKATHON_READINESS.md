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

- Python is constrained to `>=3.11,<3.12`; all source files pass Python
  compilation and the current test suite passes (13 tests).
- The desktop frontend passes the production TypeScript/Vite build; the
  production dependency audit reports zero vulnerabilities.
- The Linux Python server sidecar builds with PyInstaller and its packaged
  executable successfully serves `/health` on loopback.
- A local OTLP collector test verifies Phoenix span export, and a server test
  verifies non-loopback requests require the configured API key.
- The Rust/Tauri app now uses packaged frontend assets, least-privilege dialog
  capability, a scoped CSP, a private per-user `.env` path, and the bundled
  server sidecar. A native Tauri package has **not** yet been built locally.
- The Rust app passes a Windows GNU target `cargo check`; this is compile-time
  evidence only, not a Windows installer or runtime test.
- Prior same-day live checks confirmed both configured inference paths
  authenticated and accepted a tiny Nemotron Ultra request. Do not show API
  keys in logs, repository history, screenshots, or video.
- Docker now binds on the container interface and refuses non-loopback startup
  without `BIFANG_SERVER_API_KEY`.
- The Docker build now uses the checked-in `uv.lock`, and `.dockerignore`
  excludes environment files and generated assets. The local Docker daemon is
  inaccessible in this environment, so the image itself remains unverified;
  CI builds it on pushes and pull requests.
- The project has an Apache-2.0 license and `.env` is ignored.
- The original supplied archive contains an `.env`; the working release copy
  does not. Never publish or reuse the original archive as the repository
  source. Rotate credentials from that file before public release, and keep
  real credentials out of commits, build contexts, screenshots, and recordings.

## Not yet demonstrated

- The Rust/Tauri native bundle has not compiled in this workstation because
  WebKitGTK/libsoup development libraries are missing. CI now installs these
  libraries and builds a Debian package; that CI result remains pending.
- The worktree copy has no Git remote or public GitHub repository yet, so the
  code is not publicly submitted.
- No live 8×H200 deployment is evidenced. Token Factory inference does not
  prove that this project provisioned eight H200s.
- KV-cache quantization is a standalone prototype, not connected to the NIM or
  TensorRT-LLM serving path; no speed, memory, or recall claim is supported.
- Phoenix export has not been verified against a live collector. Lobster Trap
  remains an optional proxy and must not be presented as integrated metrics.
- The final public demo URL and ≤3-minute YouTube video are still required.

## Critical path

1. Get the native Tauri/sidecar Linux package green in CI and smoke-test the
   installed app through the full approve → edit → diff → apply → test loop.
2. Verify the packaged app's Token Factory path and the separately configured
   NIM path without exposing credentials; record exact model and deployment
   details. Add measured response and task-quality evidence, not GPU claims.
3. Publish the Apache-2.0 repository and a reproducible desktop test build.
   Run secret scanning before publication and verify the public source comes
   only from the sanitized working copy. Rotate credentials from the supplied
   archive before publication.
4. Record and publish a concise demo (≤3 minutes) showing the user-visible IDE,
   Nebius Token Factory, NVIDIA Nemotron, approvals, real diff, and test result.
5. Keep NIM, Phoenix, Lobster Trap, KV-cache benchmarks, and mobile companion
   work on the roadmap unless they strengthen the demonstrated core loop.
