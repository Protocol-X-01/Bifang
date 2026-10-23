# Inference and deployment

Bifang is the agent/control plane. It calls an OpenAI-compatible inference API;
it does not host Nemotron weights or provision GPUs.

## Hackathon demo path

Use Nebius Token Factory as the default hosted inference path. It avoids
pretending the application server itself is an eight-GPU model deployment and
keeps the demo runnable without NGC image-pull or cluster setup. Set
`NEBIUS_API_KEY`, `BIFANG_DEFAULT_PROVIDER=nebius`, and the model settings shown
in the root `.env.example`. Confirm the model is enabled for the account and
test a real request before recording the demo.

## NVIDIA NIM path

For a separately deployed NIM, set `NVIDIA_API_KEY`,
`BIFANG_DEFAULT_PROVIDER=nvidia`, `BIFANG_NVIDIA_BASE_URL` to the NIM
OpenAI-compatible `/v1` endpoint, and `BIFANG_NVIDIA_MODEL` to the served model
identifier. Pull NIM images from NGC using the deployment's documented image
tag and license requirements. Do not commit NGC credentials, API keys, or
deployment-specific endpoints.

The archive's former `nebius.yaml` was an unverified schema and did not describe
a validated Nebius Serverless deployment. It has been removed rather than
presented as deployable infrastructure. Use the official Nebius CLI/API for the
chosen endpoint product and validate its resource schema before deploying.

## Docker API service

The Docker image binds to `0.0.0.0` so a container port mapping can reach it.
Because that is a non-loopback bind, startup requires `BIFANG_SERVER_API_KEY`;
the server compares the `X-API-Key` header in constant time. Pass the key and
provider credential at runtime through the deployment's secret manager, not
as Docker build arguments or image-layer environment values. Configure
`BIFANG_CORS_ORIGINS` narrowly for the specific client origin; the local IDE
does not automatically attach a key for a remote API deployment.
The image installs dependencies from the checked-in `uv.lock`; `.dockerignore`
excludes local `.env` files, virtual environments, build output, and unrelated
project assets from the build context.

## Guardrails and tracing

Lobster Trap is an optional OpenAI-compatible reverse proxy. To inspect model
requests and responses, run it with a policy and a backend pointed at the
chosen Token Factory or NIM API, then set the matching
`BIFANG_NEBIUS_BASE_URL` or `BIFANG_NVIDIA_BASE_URL` to the proxy's `/v1`
endpoint. Its dashboard and JSONL audit log provide proxy-level security
visibility; it is not a substitute for tool approvals, workspace isolation, or
OpenTelemetry tracing. Keep the proxy on loopback for a local desktop setup.
Because the proxy inspects requests and responses, configure its audit-log
retention and policy for the sensitivity of source code and prompts.

Phoenix traces can be enabled with `BIFANG_ENABLE_TRACING=1` and the optional
`observability` extra. Set `BIFANG_TRACING_ENDPOINT` to the OTLP HTTP traces
endpoint and `PHOENIX_API_KEY` only for an authenticated Phoenix collector.
Traces record model/tool names and argument names, not prompt or file contents.

## GPU and KV-cache claims

Do not claim that eight H200 GPUs are running unless the selected model-serving
profile, endpoint configuration, and live deployment confirm it. A Token
Factory public endpoint is a managed API, not evidence that this project
provisioned eight GPUs.

The current `src/bifang/kv_quant.py` is a prototype, not an active inference
optimization: it observes generic module outputs, does not install a quantized
cache into a serving engine, and dequantizes tensors before use. Do not present
it as delivering KV-cache memory or latency savings. A credible performance
demo should compare the same model, prompt set, output length, concurrency,
and serving configuration, and report measured latency/throughput and quality.
