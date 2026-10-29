# Visual context for coding

Attach a screenshot or diagram, ask a visual reviewer about it, then choose
whether to place its observations in your coding-chat draft. Sending that draft
is a separate action. Visual observations remain untrusted evidence, not tool
instructions or proof that a patch works.

This feature is part of `0.2.1-preview.5`. Its installer passes image review and
the coding/check/stage/Apply workflow in separate fresh-Ubuntu native runs.
See [releases](https://github.com/Protocol-X-01/Bifang/releases) for availability.

## Use

1. Open Visual context and refresh the provider's capabilities.
2. Choose an exact image-capable model and one or two PNG, JPEG or WebP files.
3. Inspect the locally prepared thumbnail and enter your question.
4. Confirm sharing with the named provider/model, or keep the images local.
5. Review the response and receipt. Optionally copy labelled observations into
   the chat draft; inspect them before sending.

Cancel stops the owned review request and releases the session. Cancellation
cannot retract an image already delivered to a provider or guarantee no charge.
Other session actions remain unavailable while the review owns the session.

## Capabilities and providers

Nebius discovery intersects active image-to-text flavors from its
[public capability catalog](https://tokenfactory.nebius.com/api/public/models_info)
with the exact IDs returned by the configured authenticated `/models` endpoint.
Model names alone do not establish image support. There is no silent fallback.

For an OpenAI-compatible NIM deployment, declare its exact image-capable model
IDs with `BIFANG_VISION_MODELS`, for example
`{"nvidia":["your-image-capable-model-id"]}`. These declarations are labelled
operator-declared and checked against that deployment's live catalog. NIM
configuration and simulated adapter tests are not live NIM vision proof.

## Data flow and limits

- Up to two images, each at most 2,000,000 input bytes and 4,000,000 pixels.
- The local API decodes actual pixels, checks type, rejects animation, applies
  orientation and re-encodes a metadata-free PNG. Its output also has a 2 MB cap.
- Only inline uploads are accepted; remote URLs and file URLs are rejected.
- Preparation stays local. Explicit confirmation precedes external inference.
  The selected provider receives the question and canonical image pixels;
  its own retention and usage policies apply.
- The visual request contains no tools. Returned tool calls are rejected.
  This reduces authority, not a guarantee that image prompt injection is solved.
- The receipt identifies requested/reported model, canonical image SHA-256,
  dimensions and available usage. A missing reported model stays unknown.
- Raw images, questions and visual analysis are not written to conversation
  history or the audit log by the visual endpoint. The audit contains receipt
  metadata. Explicitly handing observations to chat, then sending them, places
  that labelled text into the normal coding-chat/history path, without images.
- The API request body and upstream response are bounded. Remote API access
  uses the existing authentication boundary. Image decoding is not a sandbox.

## Evidence — October 24, 2026

One live Token Factory request to `nvidia/Nemotron-3.5-Super-VL` correctly read
an original synthetic card containing EMBER 42, a red square on the left and
a blue circle on the right. Requested and reported model IDs matched; usage
was 445 tokens (345 input, 100 output). The prompt did not reveal the answer.
No private screenshot, model fallback or GPU provisioning was used.

A second bounded evaluation used three original synthetic coding screenshots:
an off-by-one loop, a truthy-string authorization bug and a correct function
beside an adversarial comment. Across three calls (3,010 reported tokens), the
selected model identified both bugs and proposed appropriate corrections. For
the adversarial comment it described the code statically, identified the
comment as an injection attempt and explicitly said no tests were executed.
Each full answer was reviewed by the assistant against predefined ground truth;
keyword checks alone were not treated as semantic proof. The suggested code was
not executed. See [evaluation answers and scope](evidence/visual-debugging.json).
These three controlled cases are useful smoke evidence, not a representative
quality benchmark or a guarantee against prompt injection.

The source-component browser walkthrough used synthetic inference and the real
file chooser/local image decoder. It exercised declining sharing, cancellation,
busy-state controls, response receipts and explicit image-free chat handoff.
Backend tests cover malformed images, size/type/pixel limits, catalog checks,
consent, authentication, audit privacy and request-scoped cancellation.

The exact local installer now passes a separate fresh-Ubuntu native walkthrough:
actual file input, packaged Pillow decoding, declining sharing, cancellation,
model receipts and explicit labelled image-free draft handoff. The native run
used two synthetic NIM-compatible image calls and zero hosted calls. The VM,
temporary SSH key and test ports were cleaned up. See the
[artifact-bound native receipt](evidence/ubuntu-vision-native.json).

Its Debian version `0.2.1~preview.5` upgrades the older `0.2.0` previews and sorts
before a future stable `0.2.1`. This package is separate from Preview 4.
Native WebDriver file-input testing does not establish GTK chooser coverage;
the synthetic NIM-compatible fixture is not a live NIM deployment.

Next is broader task-based visual-debugging evaluation. This read-only reviewer
does not add image history to the coding
agent, terminal or mobile clients.
