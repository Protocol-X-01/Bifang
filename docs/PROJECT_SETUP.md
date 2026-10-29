# Project dependency setup

The local dev.9 source provides approval-bound **npm, Python/uv and Rust/Cargo**
setup in the desktop workbench, terminal workbench and CLI. Opening a project
does not install anything. Select the ecosystem before reviewing the plan.
These additions are newer than the published Preview 6; an older local package
does not acquire them without rebuilding.

## Desktop workbench

Open **Developer workbench → Dependency setup**, choose **Review offline setup**
or **Review network setup**, and inspect the exact arguments, writes, network
mode and manifest fingerprints. Cancel is initially focused. Check the explicit
approval box before **Install approved plan** becomes available; the agent's
full-permission mode does not bypass this decision.

The view streams literal output and retains its last 100,000 characters in
memory. **Cancel installation** requests cancellation, then waits for the actual
exit receipt rather than immediately declaring success. Other agent/plugin
actions pause while the local job runs. Changing the view requests cancellation;
it does not transfer a running setup to another workspace. A failed connection
does not automatically retry an installation or claim it was rolled back.

The native route accepts only a fixed setup request and the bundled helper's
`--setup` mode. It validates the main-window origin, uses an operation-specific
cancellation identifier and a structured progress channel, and rebuilds a small
environment without provider credentials. The helper transport bounds frames to
64 KiB, total encoded output to 8 MB, diagnostics to 16 KiB and elapsed time to
345 seconds. Normal cancellation gives the helper five seconds to retain its
receipt before forced cleanup. Abrupt process/window termination can prevent a
final receipt; inspect the project before retrying an uncertain result.

The browser preview does not expose this installer over HTTP. It displays the
native-build requirement instead. A compromised trusted native frontend is not
isolated by its own origin check; model output is not permission to invoke native
setup commands.

## Terminal workbench

Open **F8 → Packages**. Choose **Plan offline** or **Plan network**, review the
project, exact arguments, manifest hashes, cache path and access, then choose
**Install**. A separate confirmation starts with Deny focused, even when the
agent is in full-permission mode. Changed inputs reject the reviewed plan.

Output streams into the Packages view as literal text. **Ctrl+X** cancels the
running setup and terminates its process group. The final receipt records the
approved plan metadata, exit status, observed output hash/byte count, elapsed time, network mode and
whether the reviewed inputs remained unchanged. Metadata-only receipts are
saved under the user's Bifang state directory in `setup-receipts/`, with
owner-only directory/file permissions. Raw package output is not stored in
these receipts or sent to a model. If persistence fails, the UI reports it.

## CLI

For a first install that needs registry downloads:

```bash
bifang --workspace /absolute/project setup review --network
bifang --workspace /absolute/project setup run --network --sha256 REVIEWED_SHA256
```

Use the fingerprint printed by review. The default prompt denies; `--yes` is
explicit approval of that exact fingerprint for non-interactive use. Registry,
network mode, workspace, command, manifest bytes, system npm entry point and
execution limits participate in the fingerprint. Re-review if any change.

After the private per-project cache has been populated, an offline reinstall
can use it without enabling network access:

```bash
bifang --workspace /absolute/project setup review
bifang --workspace /absolute/project setup run --sha256 REVIEWED_OFFLINE_SHA256
```

Offline mode cannot fetch missing artifacts. The cache is separate from the
host user's normal npm cache, scoped by canonical project path, and shown in
the plan. Switching projects does not silently share their caches. Credentials
are not copied from the application environment, home-directory npm files or
cloud configuration. Only the selected project, its private cache and temporary
home are writable inside this execution environment.

The default registry is the public npm registry. For another registry, use the
same `--registry URL` in both review and run. URLs must be credential-free HTTPS,
or loopback HTTP for a local registry. Project `.npmrc` and authenticated
registries are not supported by this adapter. npm's own remote-package policy
is preserved; Bifang does not add `--allow-remote` to bypass it.

## Execution contract

### Python and Rust profiles

Use `--profile python-uv` or `--profile rust-cargo` with both CLI review and run.
The registry defaults to PyPI or crates.io respectively. Runtime discovery is
read-only and uses installed tools outside the project; setup does not download
a Python interpreter or Rust toolchain. Install prerequisites deliberately before
reviewing. Python projects need a static `pyproject.toml` and `uv.lock`; Rust
projects need `Cargo.toml` and `Cargo.lock`. Supported dependencies are locked,
checksum-pinned registry artifacts. Workspace, path/git dependencies and custom
manager configuration are rejected rather than silently reinterpreted.

- Python defaults to `uv sync --locked --no-install-project --no-build` with
  sources disabled. Each run creates a fresh private environment under
  `.bifang/environments/python-NNNN`; the plan shows its exact path. Existing
  `.venv` interpreters and installed dependency startup hooks are not probed.
  The root project itself is never installed. Failed runs can leave partial
  environments; cleanup is manual, not an implicit rollback.
- Rust defaults to `cargo fetch --locked`: it downloads dependencies but does
  not compile them or run build scripts. Its private registry cache is exposed
  through a fresh temporary Cargo home, not the user's credential/config files.
- `--allow-builds` explicitly permits Python dependency build backends, or
  changes Rust's command to `cargo check --locked`, including project/dependency
  build scripts and procedural macros. Both UIs require a separate build-code
  confirmation as well as approval of the exact install plan. CLI users must
  supply the flag and approve its matching fingerprint.
- Per-project caches support later offline runs after an approved download.
  Only the project, selected cache and sandbox temporary directories are
  writable. Installed manager/interpreter/toolchain locations are mounted
  read-only. Runtime hashes bind the selected executables, not every system
  library. Tools and allowed build code remain trusted software.

### Shared limits and npm

- Linux system npm under `/usr` and functional Bubblewrap namespaces are
  required. A missing or denied sandbox does not start a host shell instead.
- `npm ci --ignore-scripts --no-audit --no-fund` preserves lockfile intent and
  disables root/dependency lifecycle hooks. Script-dependent packages may need
  an additional setup step; this installer does not silently authorize it.
- Require `package.json`, lockfile version 2 or 3, and SHA-512 integrity-pinned
  dependency artifacts. Reject monorepos, linked packages, foreign-manager
  lockfiles, shrinkwrap and project npm configuration rather than replacing
  their intended manager or configuration.
- Offline execution uses the existing `offline-v1` namespace/seccomp policy.
  Network execution explicitly shares host networking and can reach local and
  remote services. It is not a registry-only egress allowlist.
- Bound execution to five minutes and 1 MB observed output. Setup operations
  hold an advisory project-directory lock, preventing concurrent Bifang setup
  jobs for that same directory. Escape/control characters are shown literally.
- Installation can replace `node_modules`. Failure, timeout or cancellation
  does not roll back partially installed packages. Inspect the receipt and
  project before retrying. A CLI failure to save its receipt returns nonzero
  even if the install itself succeeded.

Project files are visible inside the sandbox. This is not a disposable copy,
disk quota, malicious-package audit or a guarantee against an already-running
same-user process racing project/tool changes. Input hashes are checked before
execution and again afterwards; a changed-input result is not a verified success.
Installed system npm modules and Node runtime remain trusted host software;
the entry-point hash is not a fingerprint of their entire dependency tree.

## Verification scope

The regression suite uses real Linux npm and Bubblewrap to install an
integrity-pinned fixture dependency and prove root/dependency hooks stay off.
A disposable loopback registry proves that an offline cache miss makes no
request, an approved network plan downloads the artifact, and a subsequent
offline reinstall uses the populated cache. Separate synthetic sandbox
workloads exercise timeout, cancellation/descendant cleanup, output limits,
environment filtering and display failure. These tests do not establish
general package safety or a desktop/mobile installer walkthrough. The local
Debian candidate's extracted helper additionally passes real setup over the
native Rust event transport, and its actual plan/receipt validate through the
production frontend parsers. This is functional pipeline evidence, not a fresh
Ubuntu installation, native-window click-through or accessibility acceptance.

Dev.9 source tests also install a real checksum-pinned Python wheel and Cargo
crate from disposable loopback registries, then reuse their caches offline.
Python sdist and Cargo build-script fixtures exercise both default denial and
explicit build permission. Terminal tests separately deny each approval before
proving the approved Rust build runs. These are fixture-backed checks, not a
claim that arbitrary packages are safe. Older packaged npm evidence above does
not cover the new profiles.

Behavior references: [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/)
and [npm configuration](https://docs.npmjs.com/cli/using-npm/config),
[uv CLI](https://docs.astral.sh/uv/reference/cli/) and
[Cargo fetch](https://doc.rust-lang.org/cargo/commands/cargo-fetch.html).
