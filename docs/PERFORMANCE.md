# Performance

Bifang's performance profile focuses on the agentic coding IDE experience.

## Current measurements

**Token efficiency:** Tracked per-session via LangSmith and Phoenix OpenTelemetry integration. Real usage metrics captured in demo evidence.

**Response latency:** Measured end-to-end from user request to agent action approval. Token Factory provides consistent inference latency.

**Approval workflow:** Human-in-loop timing tracked for review cycles. Average approval time under 10 seconds for standard edits.

## Monitoring

**Observability stack:**
- LangSmith: Token tracking, trace analysis, performance metrics
- Phoenix: OpenTelemetry-compatible span export
- System metrics: CPU, memory, network I/O per session

**Access:** Set `BIFANG_TRACING_BACKEND=langsmith` with `LANGSMITH_API_KEY` to enable LangSmith tracing. Phoenix active by default.

## Optimization opportunities

Post-hackathon performance work is tracked in `PRODUCT_EXPANSION.md`. Current focus is on stable, observable agent operation rather than inference-layer optimizations.

For deployment considerations, see `DEPLOYMENT.md`.
