# Independent installation evidence

Observed October 23, 2026. This is a fresh virtual-machine check, distinct
from launching an extracted package on the development workstation.

## Environment

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

The release-profile `0.2.0` Debian preview installed through APT. Its SHA-256:

```text
1117b08c02b0fc52639c93de477ae8c570b49bd8728416b267d284f99f23d927
```

The installed `/usr/bin/bifang-desktop` launched its bundled Python sidecar.
It completed the live Token Factory receipt-parser task through the actual
native UI: approvals, generated diff, apply confirmation, and successful
source-checkout verification. All five checks passed, only `receipts.py`
changed, and the original checks remained byte-identical.

The workspace was **preselected in test storage**. Attempts to drive the
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
- Public distribution/download instructions and a final submission video URL.
- CI execution once the account billing restriction is removed.
- Other Linux baselines, Windows, macOS, and physical-GPU behavior.

No Debian 12 compatibility or broad Linux portability claim follows from this
Ubuntu result. Credentials, private environment files, SSH keys, VM disks,
and raw diagnostic logs are not part of the public evidence.
