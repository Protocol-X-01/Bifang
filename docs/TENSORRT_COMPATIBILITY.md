# TensorRT compatibility: exact package versus Python runtime

Checked October 23, 2026. These findings distinguish local package evidence
from NVIDIA's published support information.

## Workstation evidence

The installed package is
`nv-tensorrt-local-repo-debian12-11.4.0-cuda-13.4` version `1.0-1`.
It registers a local package repository. `apt-cache policy` reports that
`tensorrt`, `libnvinfer11`, and `python3-libnvinfer` are not installed.
Their available local-repository version is `11.4.0.106-1+cuda13.4`.
The Bifang Python 3.11 environment cannot currently import `tensorrt`.

Inspecting the actual `python3-libnvinfer` Debian package with `dpkg-deb -f`
shows both Python constraints:

```text
python3 (>= 3.11)
python3 (<< 3.12)
```

Its module is installed under Python 3.11's distribution-packages directory.
The workstation's system `python3` is 3.14.8. Creating a Python 3.11 virtual
environment does not change the system package manager's Python dependency
resolution. This explains the Debian-package installation conflict.

## NVIDIA documentation

The [TensorRT 11.4 support matrix](https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html)
lists wheel support for Python 3.10 through 3.14; Debian/RPM bindings follow
the Python version of their target platform. Consequently, Python below 3.12
is a constraint of this specific Debian 12 binding package, not a universal
restriction on TensorRT 11.4.

NVIDIA's [Debian installation guide](https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/install-debian.html)
separates installing the repository package from installing the actual
runtime/bindings. It directs users needing a non-default Python version to
the wheel files supplied with its tar distribution.

## Bifang deployment decision

Keep Bifang's tested application runtime at Python 3.11. Hosted Token Factory
and NVIDIA-compatible API requests do not require TensorRT in the desktop
client. Keep local GPU inference experiments in a separate, reproducible
environment using an explicitly supported wheel/container combination.
Do not downgrade Kali's system Python to satisfy a Debian 12 package.

TensorRT and TensorRT-LLM have separate release/dependency requirements.
Installing TensorRT 11.4 alone does not establish a working TensorRT-LLM
Nemotron deployment. A chosen NIM image or TensorRT-LLM container must be
validated with its own model profile, CUDA/driver requirements, and exact
version. Eight H200s and quantized KV-cache serving remain unverified here.

Before claiming a local inference optimization, retain an import/runtime
check, GPU/driver information, an actual inference result, and matched
quality/memory/latency measurements. The existing KV-cache prototype has not
been wired into hosted model serving.
