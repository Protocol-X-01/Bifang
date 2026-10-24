# Long-context and KV-cache research

Bifang's product is the agentic coding IDE. Its research thread asks whether
lower-precision KV-cache storage can make long coding sessions faster or fit
more concurrent context without materially reducing recall.

## Current state

**Scope update:** Token Factory-first development takes priority. The creator
has deferred GPU rentals; quantization is conditional on a supported Token
Factory control. None is verified in the current API schema. See the
[current scope and evidence](TOKEN_FACTORY_STRATEGY.md). Preserve this research
separately rather than advertising it as a submission capability.

The local [controlled experiment](KV_CACHE_EXPERIMENT.md) now includes explicit
BF16/FP8 TensorRT-LLM serving-option files and a paired streaming recall/latency
harness (`python -m bifang.kv_benchmark`). Its synthetic-stream regression tests
are not GPU measurements. Controlled serving, effective dtype verification and
memory/task-quality measurements remain pending; no speedup is claimed.

`src/bifang/kv_quant.py` is a standalone prototype, not connected to Bifang's
OpenAI-compatible provider or a NIM/TensorRT-LLM serving process. It must not be
presented as an active optimization or as measured evidence. The live Token
Factory API does not expose Bifang's internal KV-cache controls; this experiment
requires a separately controlled serving deployment.

TensorRT-LLM documents active KV-cache dtype selection and a separate KV-cache
compression framework. NIM configuration also documents KV-cache reuse and
host offload. Those are related but distinct knobs: prefix reuse/offload is not
the same experiment as lower-precision active-cache quantization. Select only
features supported by the pinned NIM image, profile, TensorRT-LLM version, and
Nemotron architecture. In particular, preserve any non-attention state that
the model's hybrid layers require.

## Experiment protocol

1. Freeze the exact Nemotron Ultra checkpoint/model ID, NGC NIM image tag and
   digest, selected NIM profile, TensorRT-LLM version, GPU topology, and runtime
   settings. Record whether the run actually uses eight H200s.
2. Establish a BF16/FP16 KV-cache baseline and a fixed set of coding-agent
   tasks: repository questions, multi-file change requests, long-context
   retrieval/needle checks, and tool-call sequences.
3. Compare one supported lower-precision KV-cache mode at a time. Keep model
   weights, prompts, input/output lengths, concurrency, sampling settings, and
   cache reuse policy identical.
4. Measure time-to-first-token, inter-token latency, tokens/second, peak GPU
   memory, effective context/concurrency, task success, and long-context
   retrieval accuracy. Run repeated trials and report distributions, not a
   single best run.
5. Publish the configuration, raw aggregate measurements, and quality criteria.
   Treat “no recall loss” as a tested acceptance threshold, not a promise; if
   the quality threshold fails, reject the optimization.

Useful starting references are NVIDIA's [TensorRT-LLM KV-cache compression
guide](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/features/kv-cache-compression.md),
[KV-cache system guide](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/features/kvcache.md),
and [NIM KV-cache configuration](https://docs.nvidia.com/nim/large-language-models/1.15.0/configuration.html).
