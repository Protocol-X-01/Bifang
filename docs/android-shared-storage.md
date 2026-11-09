# Android shared storage

In Terminal, expand **Device storage**, choose **Connect shared storage**, then
**Check/refresh** after completing setup. No permission screen or storage setup
opens on startup, environment selection, or a status query.

- **Android system shell:** allow Bifang all-files access in its app-specific
  Settings screen on Android 11+. Android 7–10 uses runtime storage permissions
  (and Android 10's legacy storage mode). Refresh verifies the permission and
  creates only missing aliases inside the real terminal HOME, obtained from the
  same native `app_data_dir()/projects/terminal` path as the terminal engine.
- **Termux distributions:** Bifang permission does not grant Termux permission.
  Connect runs the real `termux-setup-storage` in a foreground Termux session
  when RUN_COMMAND is available and allowed. Otherwise use **Open Termux** and
  run `termux-setup-storage` yourself. Bifang never answers its existing-storage
  rebuild prompt. A dispatched setup command is not a successful connection.
  Connect the distribution runtime, check/refresh, then open a new guest shell.

Aliases are `~/storage/shared`, `downloads`, `documents`, `dcim`, `pictures`,
`music`, and `movies`, for public folders that exist and are accessible. Native
aliases never replace files or links, including dangling links. Conflicts are
reported. Revoked or denied permission is reported without deleting anything.
Refresh can fill missing native aliases only after the saved explicit opt-in;
the separate native status operation is read-only.

**Disconnect shared storage** saves only the selected host's opt-in as off.
For Bifang it stops creating missing links; existing `~/storage` links and files
remain, and those links can still work while Android access is allowed. For
Termux it stops extra shared-storage binds in **new** distribution logins;
existing sessions keep their mounts and need closing and reopening. Disconnect
does not remove links or data and does not revoke either app's OS permission.
Reconnect enables the same host again, and refresh still checks actual access.

Use the separate **Android storage permissions** button to open Bifang's
all-files Settings on Android 11+, or its app details on Android 7–10; in a
Termux environment it opens Termux's own app details. This action does not opt
in or create links. Only the owner can revoke access in Android Settings; return
and check/refresh afterwards. The disconnected native status still reports
whether Android storage access remains granted.

The installed distro backend remains **TermuxRuntime + bifang_runtime.py**;
NativeLinuxRuntime is a PRoot probe, not a native distro installer. A saved
native-held Termux opt-in controls new logins. The authenticated runtime queries
Termux's aliases as the Termux UID and revalidates them on every opted-in login.
`--isolated` stays enabled. Explicit binds expose each approved alias in the
guest HOME's `storage` directory, and approved `shared` at `/sdcard` (or
`/mnt/bifang-shared` if `/sdcard` already conflicts). The Termux distro image uses
its own `/data/data/com.termux/files/home`, not `/root`.

Sources must resolve exactly to known folders in the current Android user's
primary `/storage/emulated/<user>` volume and be readable/writable/searchable.
Redirected storage directories, private HOME/.ssh targets, unknown aliases,
and inaccessible sources are rejected. Linked or unavailable rootfs/runtime
paths skip **all** extra storage binds with a notice, without writing mount
placeholders; the existing isolated shell login can continue. Existing
guest files, nonempty directories, and symlinks are preserved; conflicting
mounts are skipped with terminal output. No full Termux HOME or host alias
directory is exported. Existing guest sessions need reopening to change binds.
Android still enforces app-private directory restrictions. SAF document URIs
are not POSIX paths and cannot be passed directly to PRoot.

All-files access applies to the app's Android UID and therefore the whole app,
including its tools; a shell opt-in does not narrow that OS grant. Bifang and
Termux have separate UIDs and permissions. The current APK is sideloaded. The
Play badge is a brand asset, not a Play release. A future Play variant needs a
permission review or must omit `MANAGE_EXTERNAL_STORAGE`; no Play flavor is
introduced by this change.

Local checks: `pytest -q tests/test_companion_distro_runtime.py
tests/test_companion_storage.py tests/test_companion_android_source.py`,
`npm test` and `npm run build` in `companion`, and `SharedStorageLinksTest` plus
`SharedStorageConsentTest` (JVM/JUnit; Gradle task
`:app:testArm64DebugUnitTest` in an initialized Android project). Tests use only
synthetic directories, links, preferences and PTYs. This follow-up passed 35
focused Python, 14 frontend and 5 JVM tests, the TypeScript/Vite build, and
Kotlin compilation against cached Android API 36/Tauri classes. Earlier layout previews
predate the disconnect controls. Full API 37 APK compilation and actual
Settings, Termux prompt, guest file read/write, permission revocation and phone
rotation checks for this follow-up still need separate verification.

References: [Android all-files access](https://developer.android.com/training/data-storage/manage-all-files),
[Android document access](https://developer.android.com/training/data-storage/shared/documents-files),
[Termux setup script](https://github.com/termux/termux-tools/blob/master/scripts/termux-setup-storage.in),
[pinned PRoot-Distro bind handling](https://github.com/termux/proot-distro/blob/v4.34.2/proot-distro.sh).
