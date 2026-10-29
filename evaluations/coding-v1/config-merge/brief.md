Repair merge_config(base, override). Merge nested dictionaries recursively;
other values, including None and lists, replace the base value. Return data
independent of both inputs, even for values not overridden. Do not mutate the
inputs. Inputs are ordinary dictionaries with JSON-compatible values. Keep
the public function name/signature. Return the complete Python module.
