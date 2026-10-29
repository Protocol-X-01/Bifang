# Controlled active KV-cache experiment

## Status and boundary

Local implementation, not a measured GPU optimization. `bifang.kv_benchmark`
tests an actual OpenAI-compatible streaming endpoint when supplied. Unit tests
use synthetic streams and do not establish model quality, GPU memory savings,
or a functioning TensorRT-LLM installation. The legacy `kv_quant.py` prototype
is not used by this experiment or the desktop provider.

The experiment connects at the **serving engine**, not by adding an unsupported
`kv_cache_dtype` parameter to Token Factory requests. Once a controlled server
passes validation, the existing NVIDIA provider can connect to its `/v1` URL;
no tensor quantization library belongs in the desktop client.

## Choose hardware before spending

Start with a small, supported attention-based Nemotron checkpoint and one GPU
if possible. Keep a four-H200 ceiling for the initial larger-model trial; do
not silently substitute eight. Use one replica, no autoscaling, a fixed runtime
deadline and teardown on completion/failure. Include weight download/startup
time in the cost estimate. Confirm the live hourly price and effective credit
balance before launch. Token Factory credits do not establish Cloud VM credits.

The authenticated Token Factory template catalog checked on October 23, 2026
offered **Llama-3.1 Nemotron Ultra 253B FP8**, four/eight H200 SXM GPUs in
us-central1. This is not the hosted Nemotron-3 Ultra 550B model. Its `fp8` flavor
does not prove FP8 **KV**, and `kvoff` does not establish a cache-quantization
comparison. Template availability does not prove allocatable capacity, price,
or runtime configuration access. No deployment was created for that check.

NVIDIA's [NIM 2.0.6 Day-0 matrix](https://docs.nvidia.com/nim/large-language-models/2.0.6/day-0/support-matrix-day-0.html)
lists a four-H200 NVFP4-weight profile for Ultra 550B (2.0.5-variant).
The [current NIM matrix](https://docs.nvidia.com/nim/large-language-models/latest/supported-models.html)
identifies that profile as vLLM-backed. Neither establishes BF16-versus-FP8
KV override support. Do **not** apply the TensorRT-LLM YAML below to that profile
or relabel a vLLM run as TensorRT-LLM. Resolve the exact image/profile and
effective cache configuration before reserving GPUs for it.

## First controlled TensorRT-LLM lane

Use a separately pinned GPU container whose model/architecture supports both
cache types. NVIDIA documents
[active FP8 KV selection](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/features/quantization.md)
and [KV configuration](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/features/kvcache.md).
Validate against the source/version inside the actual container, not only main.
FP8 KV is the first candidate; do not assume Hopper supports active NVFP4 KV.
Preserve hybrid models' recurrent state; attention KV is not their whole state.

The two files under `examples/kv-cache/` deliberately differ only in active
KV dtype, with explicit BF16 compute, fixed token capacity and prefix reuse off.
They are starting configurations, not validated NIM profiles. In the selected
container, first check `trtllm-serve --help` and its supported model/dtype schema.
For a compatible small checkpoint, launch one mode at a time:

```sh
trtllm-serve "$MODEL_PATH" --host 127.0.0.1 --port 8000 \
  --extra_llm_api_options examples/kv-cache/baseline.yaml
```

Use `fp8.yaml` for the candidate after stopping the baseline. Freeze the same
checkpoint, weights, container, tokenizer, parser and topology. If using TP4,
record `tensor_parallel_size: 4` in BOTH configurations and manifests. Resolve
the corresponding single-node requirements before adding that option.

Retain startup logs that confirm **effective** cache dtype and any scales,
not just the requested option. Reject a silently ignored or unsupported dtype.
Do not enable remote code execution or change weights to make only one mode
work. A runtime rejection is useful evidence, not grounds to invent a result.

## Run the recall smoke comparison

Copy `deployment.example.json` into separate baseline/candidate manifests.
Replace every placeholder with actual non-secret values; its placeholder digest
intentionally fails validation. `server_options` must match all experiment
overrides, including CLI flags, and differ only in KV dtype. Keep manifests
free of credentials. The harness records them as operator-supplied, not verified.

```sh
python -m bifang.kv_benchmark run --base-url http://127.0.0.1:8000/v1 \
  --manifest baseline.json --rows 256 2048 --repetitions 3 --output baseline-run.json
# Restart the same server with fp8.yaml and the otherwise identical configuration.
python -m bifang.kv_benchmark run --base-url http://127.0.0.1:8000/v1 \
  --manifest candidate.json --rows 256 2048 --repetitions 3 --output candidate-run.json
python -m bifang.kv_benchmark compare baseline-run.json candidate-run.json \
  --output comparison.json
```

Each run excludes one warmup and measures 18 requests, six synthetic repository
recall cases over three repetitions, placing the target near the beginning,
middle and end. Row counts are **not token counts**; actual prompt/completion
tokens must be reported by the server. Short/long here are relative smoke cases,
not proof of 128K/1M-token context. Sweep larger sizes only after the smoke pass.

Use an SSH tunnel for remote experiments where possible. Remote URLs otherwise
require HTTPS and `--allow-remote`. Authentication, when needed, comes only from
`BIFANG_BENCHMARK_API_KEY`; do not reuse a hosted API key for an unrelated server.
Reports exclude request headers, endpoint URLs and raw prompts/responses. New
files are owner-only and existing reports are not overwritten. Manifests and
output artifacts still require review before publication.

## Interpretation and acceptance

- Record time to first **content** (not reasoning/role deltas), end-to-end latency,
  server-reported token counts and end-to-end output-token rate. SSE chunks can
  contain multiple tokens; their intervals are not inter-token latency.
- Reject any recall failure in either run. A smoke pass is not a statistical
  guarantee of no quality loss. The comparison checks paired prompts/token
  counts and fixed deployment settings, recomputing summaries from samples.
- Collect per-rank GPU/KV memory externally at matched live-token occupancy.
  A server can reserve the same fraction of VRAM while fitting more KV tokens;
  total reserved memory alone can conceal a capacity improvement. This harness
  leaves GPU memory null rather than inventing measurements.
- Then run held-out coding, multi-turn/tool tasks, larger context sweeps and
  concurrency tests. Repeat deployments in alternating A/B order to control
  thermal/load/time effects. Publish all failures and distributions.
- Until runtime dtype, memory/capacity and task quality evidence exist, reports
  retain `optimization_claim: not-established`, even when recall passes.

## The 200,000-user hypothesis

Registered users are not simultaneous decoding sequences. Capacity planning
needs peak request arrival rate, concurrent generations, prompt/output length
distributions, session persistence policy and a latency target. Average in-flight
requests approximately equal arrival rate times mean service time in a stable
system; burst/percentile headroom must be tested separately.

For ordinary attention, ideal KV payload scales with two tensors times attention
layers times live tokens times KV heads times head dimension times bytes per
element, before replication, scale metadata, allocation and fragmentation.
Moving 16-bit attention KV to 8-bit can approximately halve that payload, not
model weights, all GPU memory, recurrent state or total serving cost. A Nano
experiment validates the machinery cheaply; its gains do not transfer unchanged
to Ultra, especially hybrid architectures. Four H200s are an experiment topology,
not evidence of capacity for 200,000 users. Evaluate routing small coding tasks
to Nano and escalating hard tasks separately from the cache precision experiment.
