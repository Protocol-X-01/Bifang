# Bifang brand pack

Open [START-HERE.html](START-HERE.html) locally for a filterable visual catalogue. Start with the [brand board](guide/brand-board-1800.png) and [mobile + tablet board](guide/mobile-brand-board-1800.png) for a quick overview.

The pack preserves Bifang's established single-legged bird, code glyph, ember colours and **Build. Run. Verify.** line. Logo lettering is outlined so the SVGs work without installing a font.

| Need | Start here |
| --- | --- |
| Logo on a dark surface | logos/svg/bifang-horizontal-ember-dark.svg |
| Logo on a light surface | logos/svg/bifang-horizontal-ember-light.svg |
| Transparent symbols and lockups | logos/png/ |
| One-colour printing or overlays | logos/svg/ white and black variants |
| Profile image or app tile | icons/bifang-avatar-slate-1024.png |
| Video thumbnail | thumbnails/youtube-coding-demo-1920.png |
| Alternate thumbnails | thumbnails/youtube-reviewed-patch-1920.png; youtube-brand-1920.png |
| Social preview | social/social-preview-1200.png |
| Channel or profile banner | social/ |
| Story / reel cover | social/vertical-story-1080.png |
| Background for a new composition | backgrounds/ember-atmosphere.png |
| iPhone and iPad app icons | mobile/apple/; guide/APPLE_ASSETS.md |
| Android phone and tablet icons | mobile/android/; guide/ANDROID_ASSETS.md |
| Phone and tablet promotional covers | promos/mobile/ |
| Palette and sizing guidance | guide/USAGE.md; guide/palette.json |
| Repeat this for another project | guide/PROJECT-HANDOFF-CHECKLIST.md |

Each promotional layout has an editable SVG and a PNG export. The SVGs contain outlined lettering and embedded images; change copy and layout through the included source builder or a vector editor. A genuine desktop capture and a retained check-results capture are included under source/.

The logos and layout templates are vector-built. The abstract background was generated with the built-in image-generation tool; its exact prompt and mode are saved in source/image-generation.json. Original inputs, font licence and credits are included.

Rebuild with Python, FontTools, rsvg-convert and ImageMagick: `python3 source/build_brand_pack.py`. Rebuilding overwrites this pack's generated exports. To make a new edition, copy the whole folder first.

[ASSET-INDEX.json](ASSET-INDEX.json) lists all 139 artworks and their dimensions. [SHA256SUMS.txt](SHA256SUMS.txt) covers the delivered files, excluding itself. [VALIDATION.json](VALIDATION.json) records artwork checks; [NATIVE-ASSET-VALIDATION.json](NATIVE-ASSET-VALIDATION.json) records Android resource compilation, Apple catalog checks and repeat-build verification. Apple integration still needs an Xcode build and device review.
