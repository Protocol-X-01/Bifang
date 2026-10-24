Repair apply_edits(text, edits). Each edit is (start, end, replacement), using
Python Unicode code-point indices and half-open ranges in the ORIGINAL text.
Apply edits simultaneously regardless of input order; support insertions and
deletions. Reject out-of-bounds, reversed, overlapping or same-start ranges
with ValueError; touching ranges are allowed. Start/end must be integers but
not booleans; replacement must be a string. Inputs have triples and
comparable numeric indices. Do not mutate the edits list. Return the complete
Python module, keeping the public signature.
