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

NVIDIA's TensorRT 11.4 documentation lists Python wheels for CPython 3.10
through 3.14, so TensorRT 11.4 does not have a blanket Python `<3.12` limit.
The Debian binding package can have a narrower, package-specific range. For
example, the TensorRT 11.4.0 Debian 12 / CUDA 13.4 package
`python3-libnvinfer_11.4.0.106-1+cuda13.4_amd64.deb` declares dependencies
`python3 (>= 3.11)` and `python3 (< 3.12)` and installs into
`/usr/lib/python3.11/dist-packages`. That package therefore fits Bifang's
Python 3.11 pin, but cannot be imported by a Python 3.14 interpreter. A
matching TensorRT wheel or a supported Python 3.11 environment is needed when
using those bindings. NVIDIA's local-repository `.deb` only configures the apt
source; the `tensorrt` runtime is a separate package installation. TensorRT
11.4.0 Debian, tar and zip packages are built for CUDA 13.4 update 1; Python
ABI compatibility alone does not establish CUDA compatibility. NVIDIA's
[TensorRT 11.4.1 support matrix](https://docs.nvidia.com/deeplearning/tensorrt/11.4.1/getting-started/support-matrix.html)
and [tar installation guide](https://docs.nvidia.com/deeplearning/tensorrt/11.4.1/installing-tensorrt/install-tar.html)
document the Python wheel versions. The current
[Debian package guide](https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/install-debian.html)
explains that repository setup and runtime installation are separate steps.

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

NVIDIA's current LLM/VLM NIM guide says an NGC Personal API key is not needed
for most public NIM containers and models. It is required for Production Branch
artifacts, NIM releases older than 2.0.10, and private or gated images or model
artifacts. Container access also requires NVIDIA Developer Program membership
or an NVIDIA AI Enterprise license. Check the exact artifact before adding
registry credentials.

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

NIM requirements vary by container version, model and profile. As of
2026-11-06, NVIDIA's LLM/VLM prerequisites list Docker 24.0+, NVIDIA Container
Toolkit 1.14.0+, CUDA SDK 12.9+, and driver 580+; Ubuntu 22.04 LTS or later is
recommended, while other distributions are not officially validated. GPU
memory is model-specific: the prerequisites list 24 GB for Llama 3.1 8B, an
example rather than a universal NIM minimum. Check the selected release's
[installation guide](https://docs.nvidia.com/nim/large-language-models/latest/get-started/installation.html),
[prerequisites](https://docs.nvidia.com/nim/large-language-models/latest/get-started/prerequisites.html),
and [model/profile support matrix](https://docs.nvidia.com/nim/large-language-models/latest/reference/support-matrix.html).

The local repository/bootstrap package name alone is not evidence that the
TensorRT shared libraries, Python bindings, `trtexec`, TensorRT-LLM, a compatible
container runtime, or a working NIM endpoint are installed. NVIDIA's Debian
guide separates installing the local repository from installing the `tensorrt`
runtime package. Verify the installed packages, Python import, command-line
tools and endpoint in the intended supported environment before claiming local
TensorRT or self-hosted NIM execution. Bifang's hosted-provider checks do not
establish that deployment.
