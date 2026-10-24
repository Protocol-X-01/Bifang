# Persistent project memory

The local development version supports two explicit retrieval modes. These
changes are not yet included in the public desktop preview.

## Local ranked recall, enabled by default

The memory tools store project facts in SQLite and rank literal query terms
with FTS5/BM25. Searches are case-insensitive, and words need not appear as
one exact substring. Query punctuation cannot become SQL or FTS operators.
This mode sends no embedding requests, needs no NumPy or sqlite-vec package,
and is **lexical retrieval**, not a claim of semantic understanding.

By default, each original project path gets its own database under
`~/.local/state/bifang/memory/`. Disposable worktrees from that same source
share its memory; a different source path does not. Newly created database
files use owner-only permissions on POSIX systems. The data is not encrypted at rest: use an encrypted
device and protect backups if storing sensitive project knowledge.

`BIFANG_MEMORY_DB_PATH` explicitly overrides this location. Pointing several
projects at one database intentionally shares their memories. The former
global `memory.db` is not imported automatically because its records do not
identify which project owns them. An explicitly selected legacy database is
migrated in place, preserving its text and indexing it for local retrieval.

## Opt-in provider embeddings

Configure an actual embedding model, not the chat/Nemotron model:

```bash
export BIFANG_MEMORY_EMBEDDING_PROVIDER=nebius
export BIFANG_MEMORY_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
```

This uses the selected provider's existing credential and configured base
URL. Verify the model ID against your account catalog before use. Memory
content and recall queries are transmitted to that provider and may incur
inference charges. Leave the embedding model unset to keep retrieval local.
Disabling remote embeddings does not remove vectors already stored on disk.

The implementation sends OpenAI-compatible `/embeddings` requests and
supports arbitrary valid vector dimensions rather than assuming 1536. It
distinguishes document and query inputs; NVIDIA embedding providers send
`input_type=passage` for indexing and `input_type=query` for retrieval by
default. Whether a model requires that parameter is model-specific; the
provider configuration's `extra.embedding_input_type` can override it.

Only finite, nonzero numeric vectors are accepted. Failures, including
authentication errors and rate limits, propagate without storing a fake
embedding or silently changing retrieval mode. Async embedders are awaited;
custom synchronous embedders run outside the event-loop thread. Custom
embedders must supply a stable `embedding_space` identifier.

Provider, configured endpoint and model define an embedding-space identity.
Search does not mix different spaces, legacy unlabelled vectors or changed
dimensions. Existing facts must be re-embedded with the desired model before
they can participate in that space's semantic search. Old text remains
available in local mode. Cosine similarity is computed in Python over the
selected space; this is not a GPU vector index or a large-scale search claim.

## Tools and verification

- `memory_store` persists content and metadata.
- `memory_recall` retrieves ranked facts and increments their access counts.
- `memory_context` formats matching facts within an approximate token budget.

Retrieval is tool-driven: the agent must request relevant memory. Facts are
not automatically perfect, authoritative, or complete, and recalled text
should be treated as historical data rather than new system instructions.

Local tests cover restart, project separation, updates/deletion, legacy
migration, literal query handling, numeric validation, model/dimension
separation, sync/async execution, and mocked HTTP embedding requests. Live
service checks are recorded separately; unit tests are not evidence of
provider availability or general long-context recall quality.

Protocol references:
[Nebius inference API](https://api.tokenfactory.nebius.com/docs),
[Nebius embedding cookbook](https://github.com/nebius/token-factory-cookbook/blob/main/integrations/pixeltable/README.md),
[NVIDIA embedding parameters](https://docs.api.nvidia.com/nim/reference/nvidia-embedding-2b-infer),
[SQLite FTS5](https://www.sqlite.org/fts5.html).
