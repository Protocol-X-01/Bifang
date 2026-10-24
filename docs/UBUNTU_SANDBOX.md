# Ubuntu command sandbox setup

Bifang's Linux command sandbox uses Bubblewrap. Installing `bwrap` alone
is not sufficient: Ubuntu 24.04 can restrict its unprivileged user namespaces.
In a fresh Ubuntu 24.04.5 VM, the initial probe failed with
`bwrap: setting up uid map: Permission denied`.

## Scoped administrator setup

Keep the system-wide namespace restriction enabled. Ubuntu provides an extra
AppArmor profile for `/usr/bin/bwrap` in the `apparmor-profiles` package.
An administrator can review and activate that distribution-supplied profile:

```bash
sudo apt install bubblewrap apparmor-profiles
sysctl kernel.apparmor_restrict_unprivileged_userns
less /usr/share/apparmor/extra-profiles/bwrap-userns-restrict
```

For a machine without an existing profile at the destination, run the following
as one shell block. The existence check prevents overwriting local policy:

```bash
if sudo test -e /etc/apparmor.d/bwrap-userns-restrict; then
  printf '%s\n' 'Existing profile found; ask your administrator to review it.'
else
  sudo install -m 0644 \
    /usr/share/apparmor/extra-profiles/bwrap-userns-restrict \
    /etc/apparmor.d/bwrap-userns-restrict &&
  sudo apparmor_parser -r /etc/apparmor.d/bwrap-userns-restrict
fi
```

Then, as your ordinary desktop user (not root), check:

```bash
sysctl kernel.apparmor_restrict_unprivileged_userns
bwrap --ro-bind / / --proc /proc --dev /dev --share-net /bin/true
```

On our restricted test VM, the sysctl remained `1` and the probe exited `0`.
This small probe checks namespace availability, not workspace isolation.
Do not set the global restriction to `0`, set Bubblewrap setuid, or disable
the command sandbox to resolve this prerequisite. Managed hosts may have
additional policy: ask the administrator if the scoped profile is unavailable
or the probe still fails. The app does not install profiles or change host
policy automatically. This permission is scoped to Bubblewrap, not exclusively
to Bifang; review it as a host administrator.

## Measured evidence

A fresh disposable Ubuntu VM passed an A/B/A test: the exact Bifang command
layout failed before the profile, succeeded with it, then failed after its
removal. While active, a harmless command wrote inside the workspace and could
not see an outside-home canary. The global restriction stayed `1` throughout.
No host security policy was changed and no model calls or credentials were used.
See [scoped profile evidence](evidence/ubuntu-bwrap-profile.json).

The installed native desktop also passes manual/auto/full approval, a real
sandboxed sentinel command, blocked-command denial, mid-turn pause, denied
post-pause write and new-chat/reload reset with this profile active. Eight
synthetic model replies and no real credentials were used. Global restrictions
remained enabled; the VM and temporary services were removed afterward.
See [installed native sandbox evidence](evidence/ubuntu-native-sandbox.json).

The live coding rehearsal and the profile checks are separate. The live
rehearsal used an explicit sandbox opt-out in a disposable trusted VM; it must
not be described as sandboxed. Exact package and test scope are also recorded
in [local validation](LOCAL_NATIVE_VALIDATION.md).
Network remains shared in the command sandbox; approval controls and namespace
checks are not a general guarantee for hostile code. For that use, isolate the
entire application in a disposable VM with externally controlled networking.

## Upstream guidance

Ubuntu documents the namespace restriction and prefers application-specific
AppArmor permission over disabling internal sandboxes in its
[24.04 release notes](https://documentation.ubuntu.com/release-notes/24.04/#unprivileged-user-namespace-restrictions).
See also [Ubuntu AppArmor documentation](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/).
