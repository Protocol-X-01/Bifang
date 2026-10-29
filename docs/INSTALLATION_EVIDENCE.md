# Independent installation evidence

Updated October 24, 2026. These are fresh virtual-machine checks, distinct
from launching an extracted package on the development workstation.

## Environment

### Preview 4: installed native engineering

Package SHA-256
`0282033adc7aa1fb55f1911a11ec60e31844e9f1ec6c840bc5b9ee10f82d87a9`
was APT-installed in a fresh Ubuntu 24.04.5 guest. Desktop and bundled-sidecar
hashes matched the retained installer. The actual native UI passed inference
confirmation refusal, manual write denial, failed/passing independent checks,
patch review, staging and the separate original Apply action. Seven synthetic
loopback model calls were used, with zero hosted inference requests.

The deliberately unsupported model success claim did not override the failing
check. The successful check ran actual Python in Bubblewrap on a read-only
snapshot without network or provider credentials. This verifies that exact
command and selected files, rather than general correctness of model output.

Ubuntu initially blocked the namespace probe. Its packaged scoped AppArmor
profile enabled Bubblewrap while the global user-namespace restriction remained
enabled. There was no sandbox opt-out or host-policy change. Guest services
closed, the VM stopped, and its overlay/private SSH key were removed.
See [exact native evidence](evidence/ubuntu-engineering-native.json) and the
[reproducible engineering walkthrough](ENGINEERING_WORKFLOW.md).

The new sidecar's build used Python 3.11.15; the guest's Python 3.12.3 only
ran the test harness and fixture check. The earlier live-provider results
below retain their own package identities.

### Latest recovery-message package

The newer package SHA-256
`81944a2639bfa486e19a329964cb2f5371ff2b705be5b1af4b68ae6deae13a91`
was APT-installed in another fresh Ubuntu 24.04.5 guest. Installed hashes,
native path/approval/review/apply flow and all five unchanged checks pass.
Five live Ultra requests reported 13,722 total tokens. Its own continuous
31.55-second recording and model-receipt/final screenshots were retained;
screenshots were visually reviewed. It is raw local material, not a public
submission video. See [exact recovery-package evidence](evidence/ubuntu-recovery-desktop.json).

Bubblewrap's benign probes failed (uid-map permission denied with shared
network, loopback setup denied without it). No security controls were weakened;
the trusted fixture explicitly opted out inside the disposable VM. This does
not prove default sandbox compatibility. Provider credentials were removed,
the guest shut down, its overlay/private SSH key removed and ports closed.

### Latest local sandbox-repair package

The latest candidate was APT-installed in a fresh Ubuntu 24.04.5 guest on
October 24 locally. Package SHA-256:
`339a71b2824089e12fb218af600bdb8b6a5e9e511e264b9817430eb2a31d1c03`.
The installed sidecar was
`c482bdb0bd9a134a1c380321e9367ddd693caa60ce625684e252d490d7ace0d0`.
Actual path selection, approvals, diff review, apply and all five unchanged
checks passed using five real Ultra requests (13,464 reported total tokens).
The continuous local recording lasts 32.45 seconds; the final screenshot,
model receipts and a final video frame were visually inspected. This is raw
demo material, not a finished or published submission video.

The guest's benign Bubblewrap namespace probe failed with uid-map permission
denied. No kernel security controls were weakened. The trusted synthetic
fixture ran with explicit sandbox opt-out inside the disposable guest;
this does not establish default sandbox support or hostile-code isolation.
The precise namespace failure cause has not been isolated. See
[exact candidate evidence](evidence/ubuntu-sandbox-desktop.json).
The provider file was removed, guest and host test ports closed, guest shut
down, and disposable overlay and SSH private key removed.

### Earlier local streaming-repair package

The exact newer local package
`07fe7df0b8a1142cb55c6fb49f9c64689b0d222c25910bcda402f69efc725129`
was independently APT-installed in another fresh Ubuntu 24.04.5 guest on
October 24 locally. Its installed sidecar hash was
`6e42087c86a2a329d2bd654bee093b6c8a20835f89320c19af5eaedfab9dd609`.
The native UI completed the live Ultra task with actual path selection,
approvals, diff/apply and all five unchanged checks. Only `receipts.py` changed.
Four requests reported 10,066 total tokens. The system Python was 3.12.3;
the package used its bundled sidecar, not a system TensorRT/Python install.
The guest had no host mounts and used repository-supplied Ubuntu libraries.

The report binds the package, app, sidecar, environment and actual model
receipts in [newer package evidence](evidence/ubuntu-streaming-desktop.json).
The final captured image remained dimmed immediately after dialog closure;
do not use it as visual proof of the final success banner. The DOM success
check, applied source diff and independent unchanged checks passed. A polished
final video still needs a separately reviewed recording rather than recycling
that frame. Native GTK chooser selection remains unverified.

The private provider file was removed, test ports were confirmed closed,
the guest shut down and the disposable overlay/SSH private key removed.
The earlier preview and container evidence below retains its own identity.

### Earlier preview environment

A disposable KVM guest booted the official
[Ubuntu 24.04 cloud image](https://cloud-images.ubuntu.com/noble/current/)
dated October 17, 2026. The downloaded image matched the SHA-256 published
over HTTPS:

```text
04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94
```

No host directories were mounted. The guest used Ubuntu 24.04.5 LTS,
glibc `2.39-0ubuntu8.9`, WebKitGTK `2.52.6-0ubuntu0.24.04.1`, and system
Python 3.12.3. Runtime and test dependencies were installed inside the guest;
the host's development libraries were not copied into it.

## Installed desktop preview

The release-profile `0.2.0` preview 2 installed through APT in a second fresh
Ubuntu VM. Its SHA-256:

```text
7b30414e287434ec81415633451b1e53bdedc419b9d94e828955637c2522d3d4
```

The installed `/usr/bin/bifang-desktop` launched its bundled Python sidecar.
It completed the live Token Factory receipt-parser task through the actual
native UI: approvals, generated diff, apply confirmation, and successful
source-checkout verification. All five checks passed, only `receipts.py`
changed, and the original checks remained byte-identical.

The newer test selects the workspace through the actual **Open by path…**
dialog, not injected storage. Relative paths, files, and missing directories
are visibly rejected before a valid directory is accepted. Four native-shell
tests also pass, covering path validation and file-tree serialization.
The original preview used preselected storage; its earlier evidence remains
in repository history. Attempts to drive the
native GTK folder chooser with headless keyboard automation did not complete;
the dialog opens, but successful folder selection is still unverified.
This limitation is not evidence that human folder selection works or fails.
The test used a virtual X display, synthetic code, automated exact-action
approvals, and software rendering, not a physical GPU desktop or usability study.

## Docker API runtime

The Dockerfile built inside the same guest. The service runs as UID 10001,
not root. The writable workspace is separate from non-writable installed
application code. The checked-in smoke tool verifies authentication,
workspace-root confinement, and the session lifecycle without provider keys.
The retained [container report](evidence/container-runtime.json) and
[installed desktop report](evidence/ubuntu-desktop.json) describe the exact
scope. A container smoke check does not establish live container inference,
production deployment, or hostile-code isolation.

## Remaining gates

- Successful native folder selection on a normal supported desktop session.
- A final public submission video and working-app demo URL accepted by the event.
- CI execution once the account billing restriction is removed.
- Other Linux baselines, Windows, macOS, and physical-GPU behavior.

No Debian 12 compatibility or broad Linux portability claim follows from this
Ubuntu result. Credentials, private environment files, SSH keys, VM disks,
and raw diagnostic logs are not part of the public evidence.
