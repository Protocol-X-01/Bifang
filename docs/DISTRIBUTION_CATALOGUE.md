# Distribution catalogue

Bifang pins the 18 provider definitions from proot-distro v4.34.2 in
`companion/src/distroCatalog.json`. Each record includes the resolved commit,
profile checksum, and available rootfs URLs and checksums. Earlier release URLs
are retained as published by that version. Architecture entries without an
upstream checksum are excluded.

The compatibility runtime downloads complete checksum-verified profiles,
preserving their setup hooks. The existing `arch` identifier remains stable for
saved installations. Kali NetHunter Minimal and BlackArch are additional Bifang
entries, not upstream v4.34.2 providers.

The standalone Terminal selector now includes this catalogue without launching
Termux permission or connection flows. Its bundled Linux installer remains
unfinished; listing a distribution does not establish installation or login
support. The installed phone APK has not yet been updated with this change.

Validation: catalogue/runtime consistency and profile preservation tests, host
PTY/protocol tests, and the Companion production frontend build pass. Physical
device distribution installation and package-manager checks remain required.
