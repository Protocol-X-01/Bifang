# Coding dataset preparation

Dataset creation is local-only unless separately authorized. No import,
upload or training is implied by an export. The creator has now authorized
uploading the curated training/validation files to Token Factory. This does
not authorize LangSmith upload, public publication or a training job.
Fine-tuning is optional and must not displace a working coding demo.

## JSONL under 1 GB

`scripts/export-coding-dataset.py` converts local JSONL records with `input`,
`output` and `license` fields into UTF-8 chat-format JSONL. It preserves the
original question and response text, rejects missing questions (including the
OpenCodeReasoning split_1 `-` placeholder), requires an explicit license
allowlist and deduplicates whitespace-normalized question text. It never
executes downloaded code. A new output directory is required.

```sh
PYTHONPATH=src .venv/bin/python scripts/export-coding-dataset.py \
  --input /absolute/path/source.jsonl \
  --output-directory /absolute/path/new-export \
  --source https://huggingface.co/datasets/nvidia/OpenCodeReasoning \
  --revision SOURCE_REVISION_OR_EXPLICIT_SNAPSHOT_DESCRIPTION \
  --allow-license cc-by-4.0 --max-bytes 900000000 --max-rows 5000
```

The cap counts actual UTF-8 bytes, including JSON escaping and newlines, not
compressed download size. Files stop on a complete record before exceeding
the cap; individual oversize records are excluded. Caps at or above decimal
1 GB are rejected. The exporter rereads JSONL, checks count/size, records a
SHA-256 digest and emits per-line provenance separately from training content.
`--viewer-response` accepts a saved Hugging Face rows response and excludes
entries whose `truncated_cells` list is nonempty. Viewer snapshots are not
automatically immutable repository revisions; preserve raw input and its hash.

This is a preparation tool, not an assurance that every downstream training
service/model accepts the schema or context lengths. Review licenses and
attribution for the underlying sources as well as the top-level dataset card.
Do not interpret a license tag as blanket legal clearance. The exporter does
not independently scan for secrets, execute tests or establish training value.

## Larger candidate-pool curation

`scripts/curate-coding-dataset.py` samples up to 50,000 complete public NVIDIA
rows from 500 evenly spaced pages of the viewer's available split_0 prefix,
capped at 500,000 rows. The viewer currently exposes a partial prefix rather
than the whole underlying split. Sequential bounded public GETs with a
minimum pause between uncached pages are used, with exact page hashes in a retained
source manifest. Cached complete pages are reusable; incomplete/truncated
pages stop the run. This is an unversioned viewer snapshot, not a pinned
upstream revision or proof of statistical representativeness.

```sh
PYTHONPATH=src .venv/bin/python scripts/curate-coding-dataset.py \
  --cache-directory /absolute/path/public-source-cache \
  --output-directory /absolute/path/new-curated-export \
  --pages 500 --max-bytes 900000000
```

The curation pass keeps only rows labeled cc-by-4.0 and upstream train. It
requires nonempty questions, responses and Python solutions; parses solution
syntax without executing code; and matches the solution AST against a code
block in the final response, excluding code appearing only inside reasoning.
A bounded set of credential patterns is excluded. This is a useful screen,
**not functional correctness testing or comprehensive secret detection**.

Exact question text, question IDs and solution ASTs are deduplicated globally.
A deterministic numeric-normalized question-group hash reserves approximately
5% of groups for validation. Both exported files are separately capped below
1 GB, and the final exports are audited for shared question groups/IDs.
This validation split supports training monitoring; it is not an independent
benchmark, and heuristic grouping does not prove all semantic families are
separated. Independent repository tasks and human review remain necessary.
Filtering may produce a smaller file than the maximum; never pad it with
duplicates or low-quality material to hit a size target.

The October 23 local run completed all 500 pages / 50,000 candidates.
It retained 10,414 training records (346,725,366 bytes) and 558 validation
records (18,538,201 bytes), with no byte-cap exclusions. The main exclusions
were 39,010 repeated questions, IDs or solution ASTs. These are public-data
curation results, not new first-party examples or measured model improvement.
The export is beside the working repository in
`../bifang-opencodereasoning-curated-20261023/`. Upload progress and verified
receipts are kept separately; an upload-start checkpoint alone is not proof
that the remote file is complete.
Both remote Files API objects are now verified as of 2026-10-23 23:08 UTC
(October 24 locally). Full streamed read-back matched both local hashes and
byte counts. See `docs/evidence/dataset-upload.json`; account-specific IDs
remain in private sibling `bifang-tokenfactory-dataset-reconciled-20261024`
receipts. No Data Lab table, training job or deployment was created.
See [the LangSmith evaluation plan](LANGSMITH.md) for an independent baseline
comparison before claiming superior coding quality.

## Authorized Token Factory file upload

`scripts/upload-coding-dataset.py` uploads only the curated train and
validation `coding.jsonl` files. It never calls a training-job or deployment
endpoint. Before network mutation it rereads every record, validates the
chat schema and manifest/hash/size, checks explicit CC-BY-4.0 allowance and
screens selected credential patterns plus supplied private credential values.
This is not comprehensive secret detection or legal certification.

Remote filenames contain the split and content-hash prefix. An existing
matching file is reused only after downloading its content and verifying
the full SHA-256. New uploads use multipart `/v1/files` with
`purpose=fine-tune`, followed by the same read-back verification. Private
checkpoints/receipts distinguish upload-start, uploaded-but-unverified and
verified states. POST timeouts are not blindly retried; reconcile the remote
listing and saved checkpoints before another attempt. No unrelated remote
files are modified or deleted.

The first upload stored the training file successfully but its verification
encountered a 307 presigned storage redirect. Reconciliation reused that exact
object instead of posting a duplicate. The verifier now accepts a single
HTTPS redirect to the observed `storage.eu-west2.nebius.cloud` host and builds
a fresh request without API authorization or cookies. Unknown hosts, embedded
credentials and further redirects are rejected. The signed URL is not logged.
Seven mocked upload tests include cross-host authorization exclusion and
unexpected-host rejection. The live read-back then passed for both objects.

```sh
PYTHONPATH=src .venv/bin/python scripts/upload-coding-dataset.py \
  --dataset-directory /absolute/path/curated-export \
  --live-env-file /absolute/path/private.env \
  --output-directory /absolute/path/new-upload-receipts
```

The API key's default project is used. These are private post-training Files
API objects, not automatically Data Lab datasets. Do not imply a new Data Lab
table exists or that training has started. Do not print the private key file.
The upload service's current documented limit is larger than our own strict
below-1-GB policy, which remains enforced.

Training is a separate decision: select an actually supported fine-tuning base
model, validate its tokenizer/context lengths and reasoning format, estimate
training cost, and confirm the resulting deployment path. The current model
documentation does not list Nemotron, and says fine-tuned deployment is via
Dedicated endpoints; other overview pages describe serverless LoRA support.
Resolve that account/model-specific inconsistency before starting a job.
Hosted Nemotron inference access does not establish Nemotron fine-tuning or
serverless adapter deployment availability.

Primary sources checked October 23, 2026:
[dataset formats/limits](https://docs.tokenfactory.nebius.com/post-training/datasets),
[Files API upload workflow](https://docs.tokenfactory.nebius.com/post-training/how-to-fine-tune),
[supported training models](https://docs.tokenfactory.nebius.com/post-training/models).

## Our own dataset

`scripts/build-repair-dataset.py` now produces a six-example first-party
regression-repair seed from locally authored controlled mutations. Each
baseline must produce a real test assertion failure; the unified diff must
apply cleanly; and the exact repaired checks must pass. Code runs only from
our copied local source/tests with a sanitized environment, not from public
downloaded examples. Source/test hashes and actual test logs accompany the
chat JSONL. The successful seed is 46,568 bytes, across task-plan,
dataset-export and dataset-curation families. All six belong to training;
they are not an independent evaluation set or a full agent-trajectory corpus.
The small size is deliberate provenance/verification scaffolding, not a
claim that this alone meets the user's larger-data or coding-quality goals.

Prefer issue → inspection → patch → tests → outcome examples from permitted
repositories and purpose-built engineering tasks. Record real tool results;
do not fabricate successful checks or substitute model-judge approval for
execution. Keep failed attempts and corrections only with truthful labels.
Generated examples must identify generation source and undergo independent
review before being called verified. Do not call public-data repackaging a
first-party dataset or claim superiority without comparative measurements.

Hold out repositories/problem families before generation or adaptation, with
evaluation answers absent from training. Exact question-text deduplication is
only one filter, not a contamination audit. Measure patch/test success,
regressions, unsafe-action rejection, latency, tokens and cost against the
unchanged model. Do not train just because a file fits the upload limit.

Primary sources: [NVIDIA dataset card](https://huggingface.co/datasets/nvidia/OpenCodeReasoning),
[Nebius fine-tuning example and chat JSONL](https://nebius.com/blog/posts/fine-tuning-llms-with-nebius-ai-studio).
