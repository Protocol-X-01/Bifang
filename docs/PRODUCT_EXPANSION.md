# Bifang product expansion — October 24, 2026

These are additional requested requirements, not a claim of completion or a
replacement for the existing hackathon delivery gates. The working desktop,
Token Factory path and reproducible coding workflow remain the foundation.

| Workstream | Verified/current source | Remaining acceptance gate |
|---|---|---|
| Web access | Tavily adapter, live public search and authenticated usage check | Bounded extraction/research tools |
| Observability | Optional LangSmith adapter, synthetic parent/child trace read-back; Phoenix retained | Full agent/provider usage validation and intended production workspace setup |
| Hosted orchestration | LangSmith deployment fit researched | Entitlement/cost check, durable jobs, auth, isolated execution, deployment and restart/cancel proof |
| Terminal | Existing Textual app; brand/responsive-layout improvements | Full keyboard/approval/edit/verification flow, small-terminal and screen-reader review |
| Text models | Existing configurable providers/router; CLI no longer hides non-NVIDIA catalog IDs | Live catalog and measured task-based model comparisons |
| Embeddings | Existing embedding API, validation and retrieval path | Live selected model/dimension/space compatibility and measured retrieval quality |
| Vision | No verified image-input coding workflow | Real image attachments, capability checks, consent/size/type controls and live image understanding |
| iOS | Requested; not implemented or built | Shared authenticated API client, keychain auth, consent, tests, signed native build and device proof |
| Android | Requested; not implemented or built | Same API contract, keystore auth, tests, signed native build and device proof |

Image generation scaffolding is not image understanding. A model's name or
presence in `/models` does not establish vision, tool-use or embedding support.
Keep model capabilities explicit and verify the exact endpoint/model pair.

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
3. Add a durable remote orchestrator suitable for LangSmith Deployment. Bind
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
