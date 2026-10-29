# Boundary repair

This intentionally failing two-file task reproduces the fixture in the
[October 28 hosted coding receipt](../../docs/evidence/public-coding-flow-20261028.json).
It uses only Python's standard library. Keep `test_bounds.py` read-only and
allow changes only to `bounds.py`.

Run from this directory:

```sh
python -B -m unittest discover -v
```

Initially, `valid(1, [0])` incorrectly returns true. Repairing the upper bound
from `<= len(items)` to `< len(items)` makes the test pass. The four assertions
cover an index equal to length, a negative index, the first item and an empty
list. This is a small workflow demonstration, not a coding-quality benchmark.

Follow the [current judge walkthrough](../../docs/JUDGE_DEV11.md) to run the
proposal, independent check, review, stage and hosted Apply sequence.
