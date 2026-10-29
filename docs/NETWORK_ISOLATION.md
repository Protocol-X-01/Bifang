# Offline command networking

The command sandbox now uses an offline policy, rather than sharing host
networking or relying on a DNS denylist. Model inference and explicitly trusted
host integrations remain outside this execution sandbox.

## Layers

1. Bubblewrap creates a new network namespace; the general command runner no
   longer supplies `--share-net`. Host routes, loopback listeners and abstract
   UNIX sockets are not shared. See the upstream
   [network namespace contract](https://man7.org/linux/man-pages/man7/network_namespaces.7.html).
2. A seccomp filter loaded by Bubblewrap denies new `socket` calls, `connect`,
   `sendmsg`, `sendmmsg`, `setns` and `io_uring_setup`. Explicit-destination
   `sendto` calls are also denied. This closes a separate pathname-UNIX-proxy
   route if an existing host socket is visible inside a mounted project.
3. New internal socket pairs and destination-free sends remain available for
   process-local communication, including asyncio's wakeup channel. Inherited
   host descriptors are not passed through; standard input is `/dev/null` and
   only the filter descriptor is explicitly passed to Bubblewrap at launch.
4. The filter checks the audit architecture, rejects alternate/x32 syscall
   numbering and follows descendants. It currently supports native Linux
   x86_64 and aarch64 syscall tables. Unsupported hosts fail closed rather than
   selecting an unfiltered execution path. Actual arm64 runtime testing remains
   a separate gate; x86_64 execution and both filter tables' branches are tested.

This blocks DNS transport, direct IPv4/IPv6 connections and DoH/DoT from command
code at the socket boundary, not by guessing which command or hostname is safe.
Local TCP/UDP server tests also need a different, separately reviewed execution
profile; this offline policy intentionally does not provide general networking.
Ordinary internal socketpair traffic remains functional, but descriptor-passing
APIs that depend on `sendmsg` are unavailable.

General commands, frozen-candidate checks and sandboxed coding evaluations use
the filter. Explicit `BIFANG_BWRAP=0` remains a trusted-workload host execution
opt-out, not a filtered mode. Full tool-approval mode does not itself disable
the sandbox. Python plugins and MCP servers are host integrations, not covered
by command network isolation; see [plugin trust](PLUGINS.md).

## Check this system

```bash
bifang sandbox-check
```

This reads limited host capability flags and runs an actual harmless probe
using the production command layout. Success requires a different network
namespace, seccomp and no-new-privileges, blocked IPv4/IPv6 TCP/UDP and UNIX
socket creation, and functioning internal socketpair communication. It performs
no external requests, installs nothing and changes no global host settings.
An executable on PATH alone is not treated as sufficient proof.

If the probe fails on Ubuntu, follow the scoped administrator setup in
[Ubuntu sandbox setup](UBUNTU_SANDBOX.md). Do not disable AppArmor or global
namespace restrictions. Kernel, LSM and installed Bubblewrap support matter;
missing/denied capabilities must remain visible rather than trigger fallback.

## Internet-enabled developer work

Keep package downloads separate from untrusted test execution. A future reviewed
fetch broker must resolve and connect outside the sandbox, validate all resolved
IPv4/IPv6 addresses and redirects, reject local/private/link-local/metadata
destinations, constrain methods and registries, and make its own host egress
policy enforceable. A DNS-only allowlist or arbitrary CONNECT tunnel is not that
broker. The current package-manager CLI only previews commands; it does not
silently grant network access or implement this broker.

The hosted gVisor check executor already pins Docker networking to `none` and
checks the configured runtime's `--network=none`. That is a different runtime
contract; local changes and tests do not prove a newer cloud image is deployed.

## Evidence and limits

`tests/test_sandbox_network.py` checks both native filter tables, wrong-ABI/x32
rejection and null/non-null destination handling. With
`BIFANG_TEST_REAL_BWRAP=1`, it additionally runs the actual host probe and a
mounted UNIX datagram canary: host control traffic and a namespace-only control
reach the canary, but the filtered sandbox does not; direct syscalls and a descendant process are denied while
internal IPC and asyncio work. Fixtures use no provider keys or public targets.

The implementation uses Bubblewrap's documented
[compiled-filter interface](https://github.com/containers/bubblewrap/blob/main/bwrap.xml).
As the kernel's [seccomp documentation](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)
explains, syscall filtering is one layer, not a complete sandbox. This policy
does not establish immunity to kernel/runtime escapes, hostile host control,
side channels or every possible data flow. Use an externally restricted
disposable VM for hostile repositories. New source verification is distinct
from the older published installers and retained VM receipts.
