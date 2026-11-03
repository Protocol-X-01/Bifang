# TensorRT and NIM compatibility

## Bifang's Python boundary

Bifang's source package declares `requires-python = ">=3.11,<3.12"` in
`pyproject.toml`. That is the Python range for this project's current locked
dependencies and application environment. It should not be presented as a
general TensorRT requirement. TensorRT and TensorRT-LLM also have separate
release and Python support matrices; compatibility for one does not establish
compatibility for the other.

The normal Bifang model path is an HTTP client. The base dependencies do not
install TensorRT or TensorRT-LLM. Optional modules such as
`src/bifang/speculative.py` and `src/bifang/vram.py` import TensorRT-LLM only
when those local GPU features are used; they are not required to call Nebius
Token Factory or an NVIDIA NIM endpoint.

NVIDIA's TensorRT 11.4 tar-install guide lists matching Python wheels for
CPython 3.10 through 3.14. That rules out a blanket claim that TensorRT 11.4
itself requires Python `<3.12`. The Debian package path is different: its
Python bindings target the distribution's default Python, while a non-default
Python needs a matching wheel from the tar package. Bifang remains constrained
to Python 3.11 by its own package declaration. See NVIDIA's [11.4 tar
installation guide](https://docs.nvidia.com/deeplearning/tensorrt/11.4.1/installing-tensorrt/install-tar.html)
and [11.4 Debian package guide](https://docs.nvidia.com/deeplearning/tensorrt/11.4.0/installing-tensorrt/install-debian.html).

The installed TensorRT release alone does not establish TensorRT-LLM support
for a Python version, GPU, CUDA runtime or model. Check the exact
TensorRT-LLM/NIM release matrix separately before using the optional local-GPU
modules.

## Three distinct NVIDIA paths

1. **Nebius Token Factory:** hosted model API; configure `NEBIUS_API_KEY`.
2. **NVIDIA NIM API Catalog:** NVIDIA-hosted OpenAI-compatible API at
   `https://integrate.api.nvidia.com/v1`; configure `NVIDIA_API_KEY`.
3. **Self-hosted NIM container:** a separately installed container service;
   configure `BIFANG_NVIDIA_BASE_URL`, the served model ID, and an API key only
   if that endpoint requires one.

NVIDIA's API Catalog docs describe the hosted `/v1/chat/completions` endpoint.
They also distinguish models that are available as downloadable containers.
Therefore, an API Catalog completion is evidence of hosted API access, not a
local NIM deployment. Likewise, an NGC API key is for registry access when the
chosen image or artifact requires it; it does not authenticate inference calls
to the hosted API.

## Local NIM configuration

For an unauthenticated local NIM endpoint, set these values in the private
runtime environment:

```dotenv
BIFANG_DEFAULT_PROVIDER=nvidia
BIFANG_NVIDIA_BASE_URL=http://127.0.0.1:8000/v1
BIFANG_NVIDIA_MODEL=<model-served-by-nim>
```

For an authenticated endpoint, also set `NVIDIA_API_KEY`. For the hosted
NVIDIA API Catalog, leave the base URL unset (or set it to the official API
URL) and provide `NVIDIA_API_KEY`.

The Bifang config now registers the NVIDIA provider when either a key or an
explicit base URL is configured, and omits the Authorization header when a
keyless endpoint is selected. This makes local NIM configuration possible
without a placeholder credential.

## Self-hosted requirements and evidence boundary

NIM requirements vary by container version, model and profile. The current
NVIDIA prerequisites specify Docker, the NVIDIA Container Toolkit, a supported
driver/CUDA combination and model-specific GPU memory. For example, the current
page lists 24 GB for Llama 3.1 8B; this is an example, not a universal minimum
for all NIM models. Consult the selected release's [installation guide](https://docs.nvidia.com/nim/large-language-models/latest/get-started/installation.html)
and [prerequisites](https://docs.nvidia.com/nim/large-language-models/latest/get-started/prerequisites.html).

The local repository/bootstrap package name alone is not evidence that the
TensorRT shared libraries, Python bindings, `trtexec`, TensorRT-LLM, a compatible
container runtime, or a working NIM endpoint are installed. NVIDIA's Debian
guide separates installing the local repository from installing the `tensorrt`
runtime package. Verify the installed packages, Python import, command-line
tools and endpoint in the intended supported environment before claiming local
TensorRT or self-hosted NIM execution. Bifang's hosted-provider checks do not
establish that deployment.
