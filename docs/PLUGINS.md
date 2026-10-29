# Plugins

Plugins extend Bifang with tools or skills. Discovery reads a JSON manifest and
source bytes without importing code. New and changed plugins start disabled.

## Review and enable

Put a Python file and a matching `NAME.plugin.json` in either the original
project's `.bifang/plugins/` or `~/.config/bifang/plugins/`. For example, copy
both `github.py` and `github.plugin.json` from `examples/plugins/`.

```bash
bifang plugins list
bifang plugins trust PLUGIN_ID --sha256 REVIEWED_SHA256
bifang plugins disable PLUGIN_ID
```

Use the ID and fingerprint from the listing, inspect the indicated source and
manifest locally, then confirm trust. The fingerprint binds both files and the
manifest's absolute origin. Moving a plugin, changing its code, version,
description or capabilities requires fresh trust. A stale fingerprint is
rejected even if the change happens while the confirmation prompt is open.
Trust storage is outside the repository, atomically replaced with owner-only
file permissions. Do not copy trust records from an untrusted source.

Disabled, changed or removed plugins stop supplying tools/schemas on subsequent
lookups; the manager performs shutdown at its next service refresh. Restart
sessions to finish cleanup: arbitrary host code can create threads, processes
or side effects that unloading cannot reverse. Concurrent trust-file updates
are atomic but not a transactional multi-process administrative interface.

## Authoring

The manifest has exactly these fields:

```json
{
  "name": "my_tools",
  "version": "1.0.0",
  "description": "Developer tools for this project",
  "capabilities": ["filesystem", "network"]
}
```

Capabilities can declare `filesystem`, `network`, `process` and `environment`.
They describe intent; **a Python plugin is explicitly trusted host code with
full host access**, not a capability-confined sandbox. Its imports and external
dependencies also run with host privileges and are not covered by the two-file
fingerprint. Review and pin dependencies separately. Never embed credentials.

Expose `create_plugin()` returning `Plugin`, `ToolPlugin` or `SkillPlugin`, or a
`PLUGIN` instance. Runtime name/version must match the manifest. Tools and skills
are asynchronous; each tool needs one matching OpenAI-style function schema.
Exported names use `plugin_MANIFESTNAME_TOOLNAME`, are at most 64 ASCII
characters and cannot shadow built-in inspection tools.

Automatic imports from installed `bifang.plugins` entry points are disabled.
Package plugins must adopt the reviewable file/manifest path until a separately
reviewed distribution trust mechanism is provided. Discovery rejects symlinked,
non-regular and oversized plugin files. It never installs dependencies.

The local desktop source now includes **Workbench** controls for listing,
literal source review, exact-version enablement and disablement. Enablement
requires a separate full-host-trust checkbox; changes pause while the agent is
working. No Markdown or HTML is executed from plugin metadata or source. Refresh
after editing a plugin; changed fingerprints need fresh review. Disabling cannot
undo side effects from previously executed trusted code.

These controls use a main-window-origin-checked native command and a bounded
single-request sidecar stdio protocol, not an HTTP mutation route or agent tool.
The helper skips dotenv loading and the native caller supplies only OS/home,
locale, PATH and explicit state-root variables, not provider credentials. Both
native server and helper use the host's absolute `XDG_STATE_HOME`, defaulting to
the user's `.local/state`. Desktop configuration dotenv files no longer select
a different state root; existing data at a custom dotenv-only state root is not
automatically migrated. CLI users should use the same environment state root.

The internal `bifang-server --workbench` mode accepts one newline-terminated JSON
request on stdin with version 1, an absolute workspace path and one of
`plugins.list`, `plugins.review`, `plugins.trust`, `plugins.disable`, or
`toolchains.inspect`, or (from dev.8) `metrics.sample`. It never imports candidate
plugin code. Trust binds the
reviewed ID and SHA-256 and requires `confirmed: true`; the protocol is not a
sandbox or an authorization boundary against an already privileged local user.

Source tests cover untrusted import prevention, exact-content enablement,
changed-file reapproval, namespacing, origin binding, disable and malformed
storage. A separately built helper can be exercised with
`python scripts/check-workbench-helper.py /absolute/helper --output evidence.json`.
This is helper acceptance, not a native-window walkthrough. The dev.8
[terminal workbench](TERMINAL.md#developer-workbench) adds the same review,
explicit trust and disable workflow using F8. Broader extension distribution
remains delivery work. New local source is
not included in the published Preview 6 desktop package.
