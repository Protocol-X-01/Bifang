from __future__ import annotations

from .base import NoOpTracer, Span, SpanContext, Tracer
from .langsmith import LangSmithTracer
from .phoenix import PhoenixTracer, create_phoenix_tracer


def create_tracer(backend: str, service_name: str = "bifang", endpoint: str | None = None) -> Tracer:
    if backend == "langsmith":
        return LangSmithTracer(service_name, endpoint)
    if backend == "phoenix":
        return create_phoenix_tracer(service_name, endpoint)
    raise ValueError("Tracing backend must be phoenix or langsmith")

__all__ = [
    "LangSmithTracer",
    "NoOpTracer",
    "PhoenixTracer",
    "Span",
    "SpanContext",
    "Tracer",
    "create_phoenix_tracer",
    "create_tracer",
]
