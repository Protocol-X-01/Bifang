Repair dependency_order(dependencies), where dependencies maps string job
names to lists of prerequisite names. Return every job once, after all its
prerequisites. At each step choose the lexicographically smallest currently
ready job. Reject unknown prerequisites and cycles (including self-cycles)
with ValueError. Duplicate prerequisites are harmless. Do not mutate inputs.
Return the complete Python module, keeping the public function signature.
