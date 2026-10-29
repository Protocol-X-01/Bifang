# Try Bifang: a small repair from proposal to checked patch

**Local dev11 candidate walkthrough.** The operator supplies the matching
installer, source and private access details. The hosted API workflow has
[live evidence](evidence/public-coding-flow-20261028.json); this exact dev11
native-window walkthrough awaits acceptance.

## Install and connect

On Ubuntu 24.04 amd64, verify the supplied `SHA256SUMS`, then install
`Bifang_0.2.1.preview.7_amd64.deb` using your package installer. Its SHA-256 is
`39dfe18e4611bdb2165f30c82604e3b55bb384c57bcf80a5c12f9c456af46f63`.
The application version is `0.2.1-dev.11`.

Open **Bifang IDE → Remote forge**. Enter the supplied **HTTPS service origin**,
expand **Desktop owner or judge · sign in with a token**, enter your private
judge token and choose **Connect securely**. Use the origin without `/v1`.
The connection fields disappear when connected. Access lasts until disconnect
or app exit; the operator funds inference and hosted execution.

## Ask for the repair

1. Expand **Start coding** and select **Work on existing code**.
2. Choose **Nebius Token Factory**, then select
   `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` from the loaded model list.
3. Use **Choose source files** to import `bounds.py` and `test_bounds.py` from
   [`examples/judge-bounds`](../examples/judge-bounds). The operator should
   include this fixture alongside the candidate handoff.
4. Enable **Allow the agent to change this file** only for `bounds.py`.
   Confirm **Editable files** contains only that path.
5. Enter this brief:

> Fix only the upper off-by-one bound in bounds.py. Preserve the lower bound
> and function arguments. Do not change tests.

Set **Independent check · JSON argument array** to:

```json
["python", "-B", "-m", "unittest", "discover", "-v"]
```

Confirm sharing the selected code, then choose **Request proposal**. Only
these two public example files are needed; no personal project is required.

## Review and run

Review the proposed change: the upper comparison should become
`index < len(items)`, retaining the lower bound. For each decision, check the
candidate and check command, tick its confirmation box and choose:

1. **Approve proposed writes**.
2. **Run the independent check**. Wait for a passing execution receipt.
3. **Mark patch reviewed**.
4. **Stage verified patch**.
5. **Apply to hosted snapshot**.

Use **Inspect hosted snapshot** to see the resulting source. Expected:
`bounds.py` is repaired and `test_bounds.py` is unchanged. Hosted Apply updates
the service's project snapshot; the imported files on your computer stay as
they were. Use **Decline this step** if a proposal changes unexpected code.

For a second task, **Build a new project** accepts a brief, initial file paths
and a check command without importing existing files. Review generated tests
alongside implementation before approving execution.

## Getting help

If connection or model discovery fails, give the operator the build version,
step and error text. Keep the token private. If execution fails, inspect the
receipt before requesting another proposal. The local terminal and local
coding workflow have separate [Ubuntu sandbox prerequisites](UBUNTU_SANDBOX.md);
the Remote forge checks run on the hosted executor.
