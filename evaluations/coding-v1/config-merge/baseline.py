def merge_config(base, override):
    result = dict(base)
    result.update(override)
    return result
