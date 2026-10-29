# Ultra deployment decision

Checked October 23, 2026. No GPU capacity has been provisioned for this project.

**Superseding scope decision:** use Token Factory credits and a multi-model
coding workflow, not AI Cloud GPU rentals. Dedicated deployment notes below
are research references, not the current launch plan or spending authorization.
See [Token Factory strategy](TOKEN_FACTORY_STRATEGY.md) for the conditional
KV-control check and implementation requirements.

## Already verified

Bifang uses `nvidia/Nemotron-3-Ultra-550b-a55b` through Nebius Token Factory
in live desktop and packaged-server rehearsals. This is runtime model use on
Nebius, not only a blueprint made with NVIDIA's hosted API. Credentials remain
provider-specific; a model's vendor does not determine which API key is valid.

## Two distinct capacity choices

1. Keep the working public Token Factory Ultra endpoint. Nebius manages
   inference capacity; choosing the model does not allocate eight H200s to us.
2. Provision or reserve isolated capacity on Nebius AI Cloud or a confirmed
   dedicated offering. Model availability, region, quota, account credits,
   and price require confirmation before any resource is created.

Nebius distinguishes public, dedicated, and custom deployments on its
[Nemotron service page](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference).
Do not infer that every public model has a self-service dedicated endpoint.

### Live catalog distinction

The authenticated, read-only dedicated-template API was checked on October 23.
Its Ultra templates were `nvidia/Llama-3_1-Nemotron-Ultra-253B-v1` and the
`-kvoff` variant, with FP8 weights, a 128K context, and four or eight H200 GPUs
in `us-central1`. The public endpoint used by this project is **Nemotron-3
Ultra 550B**, not that older 253B checkpoint. No 550B dedicated template was
listed in that response. Availability can change; query the
[template catalog](https://docs.tokenfactory.nebius.com/api-reference/dedicated-endpoints/list-dedicated-endpoint-templates)
again before making a deployment decision. Do not silently substitute the
253B model, or interpret `kvoff` as proof of KV-cache quantization.

Dedicated Token Factory endpoints and AI Cloud GPU instances are separate
products. Confirm the applicable regional quote and promotional-credit
eligibility for the chosen product. A Token Factory balance is not evidence
of an AI Cloud GPU grant; neither is an advertised partner-credit offer
evidence that credits have actually been applied.

NVIDIA's [Dynamo 1.4.2 Ultra recipe](https://docs.dynamo.nvidia.com/dynamo/v1.4.2/recipes/nemotron-3-ultra)
documents an eight-H200 worker using vLLM. Its
[NIM 2.0.6 guide](https://docs.nvidia.com/nim/large-language-models/2.0.6/day-0/get-started-nemotron-3-ultra.html)
also documents version-specific H200 profiles and startup/context settings.
These are candidate deployment references, not evidence that our endpoint
runs those profiles. NIM is not synonymous with TensorRT-LLM: a vLLM-backed
profile does not demonstrate a TensorRT-LLM optimization.

## Required before provisioning

- User-confirmed spending cap and maximum runtime; no unbounded node rental.
- Hackathon credits, GPU quota, supported region, and live eight-H200 capacity.
- Exact model checkpoint, container image digest, license/NGC access, and driver compatibility.
- Backend/profile choice and supported context/concurrency settings.
- Private endpoint authentication, restricted ingress, and no keys baked into images.
- Teardown procedure and confirmation that metered resources actually stop.

Use the account's live quote rather than treating an old price in a README
as a purchase authorization. Start with a short staging session, not a
continuously running cluster through judging.

## Verification and experiment

First prove catalog access, one real completion, structured tool calling, and
the existing receipt-parser task. Record actual GPU inventory, software
versions, serving profile, and endpoint evidence separately from client tests.

Then compare the same prompts, generated-token limits, concurrency, and model
precision. Report time to first token, end-to-end latency, output throughput,
memory use, errors, and task/recall checks. Explicitly distinguish model-weight
quantization from KV-cache changes. Only claim improvements after a matched
baseline/candidate comparison; no zero-loss recall guarantee is established.

The existing KV-cache prototype is not connected to serving. Keep the tested
Token Factory path usable while evaluating infrastructure, and do not make a
hardware experiment a prerequisite for submitting the working coding agent.
