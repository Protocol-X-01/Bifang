def apply_edits(text, edits):
    ordered = sorted(edits, key=lambda edit: edit[0])
    previous_start = None
    previous_end = 0
    for start, end, replacement in ordered:
        if (type(start) is not int or type(end) is not int
                or not 0 <= start <= end <= len(text)
                or not isinstance(replacement, str)
                or start < previous_end or start == previous_start):
            raise ValueError("Invalid or overlapping edits")
        previous_start, previous_end = start, end
    for start, end, replacement in reversed(ordered):
        text = text[:start] + replacement + text[end:]
    return text
