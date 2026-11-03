# Deployment and runtime boundaries

Bifang separates the coding client from model serving. The desktop and CLI send
OpenAI-compatible HTTP requests to the selected provider; they do not load
Nemotron weights or start a GPU-serving container.

## Python and desktop runtime

The source package currently declares Python `>=3.11,<3.12` in
`pyproject.toml`. The desktop release bundles its Python service as a sidecar,
so end users do not need to install this development runtime. This project
constraint describes Bifang's tested dependency set; it is not a universal
TensorRT Python limit. See [TensorRT compatibility](TENSORRT_COMPATIBILITY.md).

Desktop development also requires Node.js, Rust and the platform-specific Tauri
build dependencies. See [`desktop/README.md`](../desktop/README.md).

## Model-serving choices

### Nebius Token Factory

Configure `NEBIUS_API_KEY`, optionally choose `BIFANG_NEBIUS_MODEL`, and use
the Token Factory base URL in `.env.example`. Inference runs through Nebius's
hosted API; Bifang does not provision GPUs for this route.

### NVIDIA-hosted NIM API Catalog

The default NVIDIA API endpoint is `https://integrate.api.nvidia.com/v1`.
It provides hosted model inference through an OpenAI-compatible API and needs
`NVIDIA_API_KEY`. NVIDIA documents this service as its hosted NIM API Catalog;
using it does not mean that Bifang has deployed a self-hosted NIM container.

### Self-hosted NVIDIA NIM

Set `BIFANG_NVIDIA_BASE_URL` to the reachable OpenAI-compatible endpoint and
`BIFANG_NVIDIA_MODEL` to the model ID served there. `NVIDIA_API_KEY` is optional
when the endpoint does not require authentication. NGC credentials are a
separate concern: the exact container or model artifact determines whether
registry authentication is needed. They are not inference API keys.

Self-hosting requires a compatible NVIDIA GPU, driver, container runtime and
NVIDIA Container Toolkit, plus enough GPU memory for the chosen model profile.
Check the version-specific [NIM installation guide](https://docs.nvidia.com/nim/large-language-models/latest/get-started/installation.html)
and [prerequisites](https://docs.nvidia.com/nim/large-language-models/latest/get-started/prerequisites.html)
before selecting hardware or a container image. Bifang does not deploy NIM or
allocate GPUs automatically.

A successful hosted API request does not identify the GPUs serving that request.
Do not claim an eight-H200 deployment from Token Factory or NVIDIA API Catalog
access; that would require provider-side deployment evidence.

## Desktop distribution

Native build workflows and the currently available platform artifacts are
tracked in [Hackathon readiness](HACKATHON_READINESS.md) and
[product expansion](PRODUCT_EXPANSION.md). Build output and CI status are
separate from evidence that an installed GUI works on a particular machine.

## Security and observability

Provider keys belong in local environment configuration or the operating
system's secure settings store. Do not put them in source, screenshots, logs,
or model prompts. Tracing is disabled by default; the optional Phoenix and
LangSmith integrations are configured separately. See [Phoenix](PHOENIX.md)
and [engineering workflow](ENGINEERING_WORKFLOW.md).
