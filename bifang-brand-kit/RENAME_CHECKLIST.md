# Bifang Rename Checklist

## Inventory

- [ ] Create `rename/bifang` and tag the last Arca revision
- [ ] Run `rg -n -i 'nebterm|arca|arca-devbox|ARCA_' . --glob '!.git/**'`
- [ ] Run `find . -iname '*arca*' -print`

## Source and packaging

- [ ] Rename `src/arca/` to `src/bifang/`
- [ ] Change imports from `arca` to `bifang`
- [ ] Change distribution name to a cleared name such as `bifang-terminal`
- [ ] Set entry point to `bifang = "bifang.cli:main"`
- [ ] Update metadata, URLs, version, and generated package metadata

## Configuration

- [ ] Rename all `ARCA_*` variables to `BIFANG_*`
- [ ] Retain `NEBIUS_API_KEY`
- [ ] Update `.env.example`, docs, and diagnostics
- [ ] Optionally accept `ARCA_*` for one release with one deprecation warning
- [ ] Ensure warnings never reveal values

## State and filesystem

- [ ] `.arca/` → `.bifang/`
- [ ] `~/.config/arca/` → `~/.config/bifang/`
- [ ] `~/.local/state/arca/` → `~/.local/state/bifang/`
- [ ] `~/.cache/arca/` → `~/.cache/bifang/`
- [ ] Add safe, non-overwriting migration logic
- [ ] Update `.gitignore`

## Git

- [ ] `arca/<session>` → `bifang/<session>`
- [ ] Rename worktree labels, patch names, and templates
- [ ] Preserve old `arca/*` branches
- [ ] Test worktree creation, patch export, and cleanup

## UI and prompts

- [ ] Replace visible ARCA branding with BIFANG
- [ ] Use `Build. Run. Verify.`
- [ ] Change `arca://project` to `bifang://project`
- [ ] Update banners, help, status, confirmations, errors, and completion messages
- [ ] Update system identity to Bifang
- [ ] Remove obsolete box metaphors
- [ ] Re-test NVIDIA model tool calling

## CLI and scripts

- [ ] Rename all `arca` commands to `bifang`
- [ ] Update completions and man pages
- [ ] Update Kali installer and Linux build script
- [ ] Rename binary and checksum outputs
- [ ] Decide whether to include a time-bounded `arca` compatibility shim

## Tests

- [ ] Rename imports and fixtures
- [ ] Test deprecated environment fallbacks
- [ ] Test state migration
- [ ] Assert new state uses `.bifang/`
- [ ] Assert new branches use `bifang/`
- [ ] Assert the executable is `bifang`
- [ ] Add a CI check preventing legacy branding from returning

## CI, release, and registries

- [ ] Update workflows, artifacts, caches, images, SBOMs, provenance, and signing
- [ ] Update repository name, topics, description, badges, and templates
- [ ] Verify PyPI, npm, crates.io, domains, and handles before publishing
- [ ] Update release notes and security contact

## Documentation and media

- [ ] Replace README and update architecture, security, installation, roadmap, and release docs
- [ ] Update every command, path, variable, diagram, screenshot, and recording
- [ ] Add independent-project and trademark notices
- [ ] Describe Bifang accurately as a fire-associated warning bird, not a phoenix
- [ ] Update Devpost title to `Bifang: Build. Run. Verify.`

## Kali clean-install validation

- [ ] Install in a fresh Kali VM through pipx
- [ ] Run `bifang --version`, `bifang doctor`, and `bifang models`
- [ ] Exercise read, search, write approval, command approval, diff, and transcript
- [ ] Verify worktree and Bubblewrap isolation
- [ ] Verify the source checkout remains unchanged
- [ ] Export a patch and clean up the workspace

## Security regression

- [ ] Deny path traversal, privilege escalation, destructive commands, and credential access
- [ ] Ensure API keys never enter child environments or transcripts
- [ ] Verify timeouts and output caps
- [ ] Verify `observe`, `assist`, and `trusted` semantics
- [ ] Run dependency, secret, and release-artifact scans

## Final sweep

```bash
rg -n -i 'nebterm|arca|arca-devbox|ARCA_' .   --glob '!.git/**'   --glob '!CHANGELOG.md'   --glob '!RENAME_CHECKLIST.md'
```

- [ ] Run tests, lint, type checks, and binary build
- [ ] Verify checksums and package contents
- [ ] Verify all links and assets
- [ ] Tag and publish the first Bifang release

## Definition of done

The primary executable and package import are `bifang`; new state, configuration, and branches use Bifang names; clean Kali installation and NVIDIA/Nebius inference pass; security checks pass; and public materials contain no obsolete branding except documented migration history.
