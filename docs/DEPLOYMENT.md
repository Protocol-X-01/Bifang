# Deployment

Bifang supports both local development and cloud deployment options.

## Local Development

**Recommended platform:** Linux (Ubuntu 22.04/24.04)

**Build formats:**
- `.deb` package (Ubuntu, Debian)
- `.rpm` package (Fedora, RHEL)
- `.AppImage` (universal Linux)

**Android companion:** APK for mobile pairing and remote approvals.

**Prerequisites:**
- Python 3.11+
- Node.js 18+ (for desktop build)
- Rust toolchain (for Tauri desktop app)

## Token Factory Integration

Bifang uses Nebius Token Factory for NVIDIA Nemotron models:

**Configured models:**
- `nemotron-ultra-253b-v1` (Nemotron-3 Ultra 550B)
- `nemotron-nano-30b-v1` (Nemotron-4 Nano 30B)

**Setup:**
1. Obtain Nebius Token Factory API credentials
2. Set environment variable: `NEBIUS_TOKEN_FACTORY_API_KEY`
3. Select model in Bifang settings

See `TOKEN_FACTORY_STRATEGY.md` for API details.

## Desktop Distribution

**Build command:**
```bash
npm run build:linux
```

**Output:** Platform-specific packages in `dist/`

**Security:** Bubblewrap sandbox enabled by default on Linux.

## Mobile Companion

**Build:** See `companion/README.md` for Android build instructions

**Pairing:** Follow guide in `docs/MOBILE_PAIRING.md`

**Security:** PRoot-Distro for isolated terminal environments

## LangSmith Sandbox

**Status:** Provisioned and ready for integration

**Sandbox ID:** `01a18c11-e0c1-70dc-a82c-9b89c7171f7a`

**Purpose:** Cloud-based agent execution environment (post-hackathon)

Current execution uses local Bubblewrap sandbox. LangSmith Sandbox integration is documented for future deployment.

## Observability

**LangSmith:** Set `BIFANG_TRACING_BACKEND=langsmith` with API key

**Phoenix:** Active by default (OpenTelemetry)

See `LANGSMITH.md` and `PHOENIX.md` for configuration details.

## Security

**Sandboxing:** Bubblewrap isolation on Linux

**Guardrails:** PII filtering, command safety validation (48 tests)

**Network:** HTTPS-only communication

See `SECURITY.md` for security architecture.

---

For infrastructure requirements and scaling considerations, see `PRODUCT_EXPANSION.md`.
