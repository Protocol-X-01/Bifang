# Reproducible coding demo

This is a deliberately broken, dependency-free CSV receipt parser. The example
is demo input, not a Bifang regression test. Its five checks initially produce
one failure and one error. A successful agent run must fix the parser without
changing the checks, then show all five checks passing.

## Prepare a clean demo repository

Run from the Bifang repository root. Choose a new directory outside Bifang;
the `mkdir` command should fail if that directory already exists.

```bash
mkdir /tmp/bifang-receipt-demo
cp examples/demo/receipts.py examples/demo/check_receipts.py /tmp/bifang-receipt-demo/
cd /tmp/bifang-receipt-demo
git init
git add receipts.py check_receipts.py
git -c user.name='Bifang Demo' -c user.email='demo@example.invalid' commit -m 'Demo baseline'
python3 -m unittest -v check_receipts
```

The last command should fail. Keep the clean baseline commit: Bifang creates
its disposable worktree from Git HEAD. Use synthetic demo files only.

Configure the selected Token Factory model using the setup instructions in
the root README. Check the actual account model catalog before recording.
Open this demo directory in the desktop app, or run `bifang chat` inside it.

## Prompt

> Run `python3 -m unittest -v check_receipts`. Find why valid quoted CSV
> receipt fields fail. Fix receipts.py using the Python standard library,
> preserve the return shape and reject incorrect field counts. Do not modify
> check_receipts.py. Rerun the same checks and summarize the diff and results.

Approve file changes and the test command only after reading the requests.
Inspect the actual diff. Check that only receipts.py changed. Apply the patch
to the original clean checkout and rerun the same test command there. Inspect
`git diff -- check_receipts.py` to verify the checks were not edited.

## Recording outline (under three minutes)

1. 0:00–0:25: introduce Bifang and show the failing baseline.
2. 0:25–1:45: show the real configured provider/model, task prompt, and approval.
3. 1:45–2:30: inspect the diff and the actual test result; apply the patch.
4. 2:30–2:55: rerun checks in the original checkout and show the public repo.

Rehearse before recording. If model latency exceeds the outline, label cuts
or time compression clearly. Do not substitute a scripted patch for the
model-generated change or describe this walkthrough as a completed demo.
No GPU performance or long-context recall result is measured by this task.

## Evidence to retain

Record the source revision, actual provider/model identifier, test output
before and after, final diff, and elapsed wall time for the full task. Keep
credentials and personal filesystem paths outside the recording. The public
demo URL and video link remain pending until published and independently
opened successfully.
