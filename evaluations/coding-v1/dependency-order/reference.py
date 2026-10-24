def dependency_order(dependencies):
    pending = {name: set(required) for name, required in dependencies.items()}
    if any(not required <= pending.keys() for required in pending.values()):
        raise ValueError("Unknown dependency")
    ordered = []
    while pending:
        ready = sorted(name for name, required in pending.items() if not required)
        if not ready:
            raise ValueError("Dependency cycle")
        selected = ready[0]
        ordered.append(selected)
        del pending[selected]
        for required in pending.values():
            required.discard(selected)
    return ordered
