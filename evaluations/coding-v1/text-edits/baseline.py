def apply_edits(text, edits):
    for start, end, replacement in sorted(edits):
        text = text[:start] + replacement + text[end:]
    return text
