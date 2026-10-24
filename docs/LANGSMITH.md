# LangSmith evaluation plan

## Source implementation update — October 24, 2026

This section supersedes the older integration status below. Current source
adds an optional metadata-only LangSmith OTLP exporter. The older Phoenix
integration remains available; the agent framework has not been replaced.
Live authentication and a synthetic metadata-only trace read-back now pass.
No private source or transcript upload, balance verification or hosted
deployment has occurred.

Install the existing `observability` extra, set `BIFANG_ENABLE_TRACING=1` and
`BIFANG_TRACING_BACKEND=langsmith`, and provide `LANGSMITH_API_KEY` through a
private environment. Set `LANGSMITH_PROJECT` and the official regional
`LANGSMITH_ENDPOINT` as appropriate. Remove a previously configured Phoenix
`BIFANG_TRACING_ENDPOINT`, or explicitly set it to the LangSmith OTLP endpoint.

The exporter uses the full `/otel/v1/traces` path, `x-api-key` authentication
and the `Langsmith-Project` header. It maps safe model/tool and reported-usage
attributes to LangSmith semantics. Prompt/output text, arbitrary events,
environment variables and exception messages are not exported. Phoenix's
credential is deliberately not inherited by this exporter. Mocked tests
verify these boundaries. A dedicated integration project also received two
actual parent/child spans (`chain`, `tool`), with empty inputs, outputs and
error content; the parent link was verified by API read-back. This was a
synthetic integration check, not a hosted model request. The receipt is
`outputs/bifang-langsmith-live-trace-20261024.json` in the development workspace.
The initial read-back helper incorrectly compared LangSmith's trace identifier
to the OTLP trace ID. The received records used a padded root span ID; the
corrected helper matched the exact emitted root span and confirmed both runs.

Only official regional cloud endpoints are accepted by this first adapter.
Self-hosted/custom collectors require a separately reviewed destination policy.
Tracing is opt-in; merely finding an API key does not enable data transmission.

### Hosting and Engine

[LangSmith Deployment](https://docs.langchain.com/langsmith/deployment) can run
agents built with different frameworks. It is not a generic replacement for
the desktop sidecar or the existing Vercel relay. Its
[Cloud deployment guide](https://docs.langchain.com/langsmith/deploy-to-cloud)
currently requires Plus or above and an application working with `langgraph dev`.
Program tracing credit does not establish deployment entitlement or coverage.

Build a separate authenticated remote orchestrator around the existing tool
boundaries, with durable job state and isolated execution. Do not expose the
loopback desktop filesystem API unchanged. Validate locally before selecting
a plan, uploading code or configuring hosted secrets. Keep Vercel intact until
the replacement has an end-to-end authenticated regression pass.

[Engine](https://docs.langchain.com/langsmith/engine) diagnoses patterns in
production traces, tracks recurring issues and can produce evaluation examples
and proposed fixes. It does not execute or certify Bifang's regression suite.
Our current custom agent is not automatically a supported Engine code-fix
integration just because it emits traces. A durable runner and actual check
receipts remain required. Metadata-only traces also limit content diagnosis.

[Enabling Engine](https://docs.langchain.com/langsmith/engine-setup) requires
organization-admin setup, acceptance of AI terms, project configuration and
cost review. Those owner decisions have not been made on the user's behalf.

---

## Historical October 23 plan

Status: researched October 23, 2026; not installed, connected or credited by
this work. No dataset, source, credentials or traces have been uploaded to
LangSmith. The creator separately authorized the curated dataset upload to
Token Factory; this does not authorize LangSmith upload or publication.

## Fit for Bifang

LangSmith is a framework-agnostic evaluation/observability platform, distinct
from the LangChain framework, LangGraph runtime and Deep Agents harness.
Bifang already implements tool execution, approval, history, routing and
context management. Replacing those with another agent harness before the
deadline would introduce migration risk without proving better outcomes.

Use LangSmith first to compare the existing agent and model configurations
on the same independently held-out engineering tasks. Keep Phoenix as the
already-rehearsed metadata-only tracing backend. Optional OpenTelemetry
fan-out is supported by LangSmith, but Bifang's current Phoenix exporter is
not a verified LangSmith integration: endpoint, headers, semantic attributes,
privacy and duplicate-export behavior must be tested separately.

## First experiment, before any training

1. Freeze a small independent task set from permitted repository fixtures,
   separated by repository/problem family from all training and validation
   material. Keep answers and tests out of training examples.
2. Compare pinned Nano, Super and Ultra plus the existing automatic router
   on identical tasks, with repeated trials and bounded request/token limits.
   The previous Nano exact-answer failure remains a real regression signal.
3. Score original test success, patch applicability, unchanged regression
   checks, permitted-tool behavior, completion/cancellation, elapsed time and
   actually reported token usage. Preserve failures; missing usage/cost is
   unknown, not zero. Model-judge scores are supplementary, not test substitutes.
4. Record model IDs, source/dataset hashes and configuration with every trial.
   Compare the unchanged baseline against any later fine-tuned candidate.
   Claim superiority only for measured task distributions, not all coding.
5. Start with local Python evaluation using `upload_results=False` and local
   examples. This disables LangSmith result/trace upload for that evaluation;
   it does not make hosted model calls local or free. Avoid remote dataset
   cloning in an otherwise local-only rehearsal.
6. After explicit approval, use a dedicated LangSmith project and a private
   credential path. Verify workspace/region and actual credit/billing status;
   the program email alone does not establish the current balance.

Do not upload the 347 MB training corpus just to run a small held-out test.
Training/monitoring validation is not the independent evaluation benchmark.

## Privacy and verification gates

Disable prompt/output collection by default. LangSmith supports
`LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`, but metadata,
attachments, exceptions and other exporters also need separate screening.
Reuse Bifang's positive metadata allowlist rather than copying arbitrary
tool arguments, source files, environment variables or exception messages.
SDK masking settings do not automatically sanitize arbitrary manual OTLP
spans. Check actual received records before claiming privacy is verified.

This integration is optional and must not block the working Token Factory
demo. No LangSmith SDK dependency or agent-framework migration was added.

The first local-report live module-repair comparison is now complete:
Nano 1/3, Super 2/3, Ultra 3/3 on three small synthetic tasks. Real sandboxed
checks, held-out reference repairs, a documented test-contract correction
and source hashes are described in `evaluations/coding-v1/README.md`.
See `docs/evidence/coding-model-comparison.json`. These nine requests are a
baseline, not broad superiority or an evaluation of the full tool-using agent.

## Primary references

- [Product/framework distinction](https://www.langchain.com/resources/what-is-langsmith)
- [Local evaluation without upload](https://docs.langchain.com/langsmith/local)
- [OpenTelemetry and collector fan-out](https://docs.langchain.com/langsmith/trace-with-opentelemetry)
- [Sensitive-data controls](https://docs.langchain.com/langsmith/mask-inputs-outputs)
