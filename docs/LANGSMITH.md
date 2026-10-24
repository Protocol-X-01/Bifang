# LangSmith evaluation plan

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
