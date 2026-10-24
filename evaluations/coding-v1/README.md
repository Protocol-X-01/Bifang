# Coding evaluation v1 — reserved, not training data

Three newly authored engineering repair tasks: recursive configuration
overlay, deterministic dependency scheduling and simultaneous Unicode text
edits. These are outside the public algorithm-training export and the six
Bifang regression-training seed examples. Do not add these fixtures, reference
answers, checks or generated candidates to training or synthesis inputs.
The repository's Apache-2.0 license applies to these locally authored files.

Only `brief.md` and `baseline.py` are sent to the model. `reference.py` and
`checks.py` remain withheld from the generation prompt. Reference repairs are
oracles, not model outputs. This is a small synthetic module-repair benchmark,
not a full repository agent, classifier test or independent human audit.
Holding these files out does not prove absence of semantically related
material in pretrained models or other datasets.

## Reproduce

From the repository root:

```sh
PYTHONPATH=src .venv/bin/python scripts/verify-coding-eval.py --output /absolute/path/new-fixture-report.json
```

This executes only our authored baselines/reference repairs. Each baseline
must fail an actual assertion and each reference must pass all its checks.
There are 11 unittest methods total (with additional edge-case subtests).
All source, brief and check hashes are retained in reports.

For locally saved candidate modules named `config-merge.py`,
`dependency-order.py`, `text-edits.py`, add `--candidate-directory PATH`.
Candidate execution always requires working Linux bubblewrap user namespaces;
there is no unsandboxed candidate fallback. Network and host home directories
are unavailable, runtime/candidate mounts are read-only, and CPU, address-space,
file-output and wall-clock limits apply. The real sandbox test also probes
environment exclusion and blocked network/filesystem access. This is not a
claim that a shared-kernel sandbox defeats all hostile code or that tests in
the same Python process are tamper-proof. Do not expose real secrets to it.

The optional paid comparison command uses nine sequential model requests,
one per task and configured Nano/Super/Ultra model, up to 4,096 output tokens
each. It checks the live catalog and sandbox before inference, keeps reports
local and does not use LangSmith or start training:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark-coding-models.py \
  --live-env-file /absolute/path/private.env --output-directory /absolute/path/new-comparison
```

## First live baseline — October 23, 2026

| Model | Tasks passed | Observations |
| --- | --- | --- |
| Nano | 1/3 | Unknown prerequisite accepted; text-edit response hit the output limit and was not executed. |
| Super | 2/3 | Same-start insertion/replacement incorrectly accepted. |
| Ultra | 3/3 | All checks pass in this single small trial. |

Nine requests reported 16,962 total tokens. All requested/reported IDs matched.
These are actual test outcomes, not LLM-judge scores. No broad ranking,
statistical significance, savings or adapted-model superiority is established.
One trial is insufficient for stable model-routing decisions.

Review found an overstrict test assumption: the brief required ValueError for
invalid ranges but did not prescribe the exception class for invalid types.
Those type cases now accept TypeError or ValueError. Every saved completed
candidate was rerun under the corrected checks, without new inference.
Task pass counts are unchanged. The original and current check manifests and
original per-row outcomes are retained in `report-rescored.json` beside this
working repository at `../bifang-coding-model-comparison-20261023/`.
Do not hide this post-run test correction or treat later reuse of these
tasks for prompt tuning as fresh unseen evaluation.
