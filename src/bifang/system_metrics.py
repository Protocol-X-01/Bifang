from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil

MEASUREMENT_ERRORS = (OSError, psutil.Error, NotImplementedError, ValueError, TypeError, OverflowError)

def percentage(value: float) -> float:
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("Invalid system percentage")
    return round(value, 1)


def sample_system_metrics(workspace: Path) -> dict:
    started = time.monotonic()
    unavailable = {"available": False, "reason": "Operating-system measurement unavailable"}
    cpu, memory, disk = unavailable.copy(), unavailable.copy(), unavailable.copy()
    try:
        cpu = {"available": True, "percent": percentage(psutil.cpu_percent(interval=0.1)), "sample_ms": 100}
    except MEASUREMENT_ERRORS:
        pass
    try:
        measured = psutil.virtual_memory()
        total, available = int(measured.total), int(measured.available)
        if not 0 <= available <= total or total <= 0:
            raise ValueError("Invalid memory counters")
        memory = {"available": True, "total_bytes": total, "available_bytes": available,
                  "used_bytes": total - available, "percent": percentage(100 * (total - available) / total)}
    except MEASUREMENT_ERRORS:
        pass
    try:
        measured = psutil.disk_usage(workspace)
        total, used, free = int(measured.total), int(measured.used), int(measured.free)
        if total <= 0 or not 0 <= used <= total or not 0 <= free <= total:
            raise ValueError("Invalid disk counters")
        disk = {"available": True, "total_bytes": total, "used_bytes": used,
                "free_bytes": free, "percent": percentage(measured.percent)}
    except MEASUREMENT_ERRORS:
        pass
    return {"schema": 1, "sampled_at": datetime.now(UTC).isoformat(),
            "collection_ms": round((time.monotonic() - started) * 1000, 1),
            "cpu": cpu, "memory": memory, "disk": disk,
            "gpu": {"available": False, "reason": "GPU telemetry is not configured"},
            "scope": "Local host measurements; selected workspace filesystem. Not model usage or inference latency."}
