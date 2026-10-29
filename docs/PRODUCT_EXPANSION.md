# Bifang product expansion — October 24, 2026

These are additional requested requirements, not a claim of completion or a
replacement for the existing hackathon delivery gates. The working desktop,
Token Factory path and reproducible coding workflow remain the foundation.

| Workstream | Verified/current source | Remaining acceptance gate |
|---|---|---|
| Web access | Tavily search and current-source single-page extraction; live public-page checks and external-action approval tests | Package the extraction update; bounded multi-page research tools |
| Observability | Optional LangSmith adapter, synthetic parent/child trace read-back; Phoenix retained | Full agent/provider usage validation and intended production workspace setup |
| Hosted orchestration | AWS review and coding API, trusted HTTPS, durable candidate-bound approvals, real gVisor checks and hosted snapshot Apply; native Remote forge walkthrough | New desktop packaging, mobile clients and operating-period monitoring |
| Terminal | Ember Textual app; [installed development wheel and actual PTY](TERMINAL.md) check/review/stage/Apply proof | Screen-reader/human usability walkthrough and publication of newer source/wheel |
| Text models | Existing configurable providers/router; CLI no longer hides non-NVIDIA catalog IDs | Live catalog and measured task-based model comparisons |
| Embeddings | Existing embedding API, validation and retrieval path | Live selected model/dimension/space compatibility and measured retrieval quality |
| Vision | Attachments, capabilities/consent, cancellation and image-free handoff; live Nemotron card and three coding cases; fresh-Ubuntu native image/coding runs passed | Broader visual-debugging evaluations; see [Vision](VISION.md) |
| iOS | [Companion source](../companion/README.md) shares remote UI, integrity checks and native session-only transport; no iOS build | Mac/Xcode toolchain, optional keychain persistence, signed native build and device proof |
| Android | Actual ARM64 debug APK builds; packaged signature, manifest, backup policy and 16 KiB alignment pass; [exact APK](evidence/companion-android-build.json) installs and starts on a [physical Xiaomi 12T / Android 15](evidence/companion-android-device.json); owner confirms rendering, keyboard and orientation | [Pairing/Authenticator onboarding](MOBILE_PAIRING.md), background reconnect and full remote approval/check/review/Apply proof; production signing and optional keystore persistence |
| Developer workbench | Read-only CLI toolchain preview, explicit existing-workspace selection and CLI plugin trust/disable controls | Native/TUI plugin management, optional language bootstraps, package-manager UI, embedded terminals and system metrics; see [acceptance criteria](DEVELOPER_WORKBENCH.md) |
| Embedded desktop terminal | [Native PTY and renderer source](EMBEDDED_TERMINAL.md); actual Linux engine checks, installed btop and frontend transport tests | Native-window/accessibility walkthrough, packaged cleanup and Windows/macOS runs; Textual/mobile terminal work remains separate |
| Desktop distribution | Published Ubuntu Debian preview; newer local Ubuntu 22.04 release-profile Debian/AppImage/RPM builds pass ABI, extracted-helper and API checks; exact Debian candidate also passes fresh Ubuntu 24.04.5 apt install, loader, management and service-health checks | Exact-candidate native-window acceptance, AppImage target launch, RPM distribution install/launch, Windows/macOS binaries; see [packaging gates](RELEASING.md#linux-package-baseline) |

The developer workbench and additional desktop packages are explicit submission
requirements confirmed on October 25, not a post-submission roadmap. Language
bootstraps remain opt-in per project; opening a repository must not install every
runtime or execute its setup scripts. Existing Android/iOS requirements remain.

Image generation scaffolding is not image understanding. A model's name or
presence in `/models` does not establish vision, tool-use or embedding support.
Keep model capabilities explicit and verify the exact endpoint/model pair.

The [remote coding component](REMOTE_CODING.md) now provides durable
candidate-bound decisions, revision-checked hosted snapshot Apply, a
tool-free proposal worker and opt-in authenticated coding routes. Its synthetic
HTTP/state/worker tests are separate from its deployed model/execution proofs. The
[gVisor executor and persistent broker](REMOTE_CODING.md#actual-isolated-execution)
now pass actual AWS isolation, cancellation and forced-restart probes. A private
deployed coding workflow also passes a real Token Factory proposal, preserved
approval after restart, independent check and separate hosted Apply. The exact
image was promoted publicly with previous receipts preserved. A local native
desktop walkthrough now exercises real HTTPS and all five UI decisions, including
reconnect before check approval. New desktop packaging and mobile clients remain
delivery gates. The newer source picker imports individual UTF-8 files read-only
by default; independent candidate hashes and locally generated replacement diffs
now gate decisions. Cross-language vectors, actual Git application and a native
live task provide separate [evidence](evidence/native-candidate-verification.json).

An [October 28 live capability check](evidence/model-capabilities-20261028.json)
used the current Bifang modules with Token Factory: Qwen3-Embedding-8B returned
a finite, nonzero 4096-dimensional vector, and NVIDIA Nemotron-3.5-Super-VL
identified both expected colors in a synthetic image through discovery,
metadata removal and visual review. This confirms those request paths for the
selected models; retrieval quality and broader visual-debugging performance
remain evaluation work.

## Our visual direction: Ember Atelier

Use Bifang's own mythology and palette: deep slate `#0F1728`, elevated ink
`#1A2338`, vermilion `#E63946`, ember `#FF8A5D`, warm white `#F7F7F7`.
Luxury here means calm hierarchy, precise typography, deliberate spacing and
excellent interaction—not gold decoration, constant animation or copied UI.

- One dominant working surface; context and inspectors recede until requested.
- Keyboard-first command access, stable action locations and clear focus.
- Quiet borders; one strong action accent; status never encoded by color alone.
- Evidence as a first-class object: task, patch, check, source and model receipt.
- Match structure across desktop, terminal and mobile without forcing a desktop
  four-column layout into a small terminal or phone.
- Preserve reduced-motion preferences, text resizing, readable contrast and
  platform touch targets. Do not buy templates or copy protected product assets.

Research references, not templates to clone:
[Linear's calmer hierarchy](https://linear.app/now/behind-the-latest-design-refresh),
[Raycast theme system](https://manual.raycast.com/themes), and
[Apple adaptive layout guidance](https://developer.apple.com/design/human-interface-guidelines/layout).

The terminal now progressively hides tertiary columns as width shrinks, with
keyboard-accessible inspectors instead of a 220-column minimum. These changes
are included in Preview 4's retained source and packaged runtime.

## Shared architecture and sequence

1. Package and validate the isolated candidate → actual independent check →
   reviewed patch path. Backend, source-component browser, and exact-installer
   fresh-Ubuntu native walkthroughs now pass. Native denial, independent
   failing/passing checks, patch review, staging and separate Apply are
   recorded in `evidence/ubuntu-engineering-native.json`; mid-model cancellation
   was separately exercised through the source-component browser.
2. Validate Tavily and LangSmith live with bounded public/synthetic inputs.
   Keep provider credentials server-side and logs metadata-only by default.
3. Add a durable remote orchestrator on the selected [AWS host](AWS_HOSTING.md),
   keeping LangSmith tracing independent of managed deployment. Bind
   jobs, workspaces, tools, artifacts and approvals to authenticated users;
   retries must not repeat unapproved writes or Apply.
4. Add explicit model-capability discovery/configuration and a bounded vision
   input path. Compare real coding/visual-debugging tasks, not marketing labels.
5. Build iOS and Android clients against that authenticated contract. Share
   design tokens and request schemas; store only revocable user credentials in
   platform secure storage. Never embed Token Factory/Tavily/LangSmith keys.
6. Demonstrate reconnect, cancellation, review and approval on both platforms.
   An Android build is not evidence of an iOS build; signing and device testing
   remain separate gates. Do not submit store listings automatically.

No cloud migration, paid plan change, Engine terms acceptance, mobile store
submission or new public release follows merely from this design document.
