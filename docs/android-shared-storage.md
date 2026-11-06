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
linked rootfs/runtime paths, and inaccessible sources are rejected. Existing
guest files, nonempty directories, and symlinks are preserved; conflicting
mounts are skipped with terminal output. No full Termux HOME or host alias
directory is exported. Existing guest sessions need reopening to change binds.
Android still enforces app-private directory restrictions. SAF document URIs
are not POSIX paths and cannot be passed directly to PRoot.

Local checks: `pytest -q tests/test_companion_distro_runtime.py
tests/test_companion_storage.py`, `npm test` and `npm run build` in `companion`,
and `SharedStorageLinksTest` (JVM/JUnit; Gradle task
`:app:testArm64DebugUnitTest` in an initialized Android project). Tests use only
synthetic directories and links. This patch passed 29 Python, 11 frontend and
3 JVM tests, the frontend build, offline ARM64 Android `cargo check --lib`, and
Kotlin compilation against cached Android 36/Tauri classes. Browser layout
previews at 390×844 and 844×390 showed usable
storage controls. Full API 37 APK compilation needs that SDK. Actual Settings,
Termux prompt, guest file read/write, permission revocation and phone rotation
checks await an explicitly authorized device session.

References: [Android all-files access](https://developer.android.com/training/data-storage/manage-all-files),
[Android document access](https://developer.android.com/training/data-storage/shared/documents-files),
[Termux setup script](https://github.com/termux/termux-tools/blob/master/scripts/termux-setup-storage.in),
[pinned PRoot-Distro bind handling](https://github.com/termux/proot-distro/blob/v4.34.2/proot-distro.sh).
