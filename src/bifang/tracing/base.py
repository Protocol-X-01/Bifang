from __future__ import annotations

import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpanContext:
    """Context for a span."""
    trace_id: str
    span_id: str
    parent_span_id: str | None = None


@dataclass
class Span:
    """A tracing span."""
    name: str
    context: SpanContext
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok, error

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def set_status(self, status: str, message: str | None = None) -> None:
        self.status = status
        if message:
            self.attributes["error.message"] = message

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def duration(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time


class Tracer(ABC):
    """Abstract base class for tracers."""

    def __init__(self, service_name: str = "bifang"):
        self.service_name = service_name
        self._current_span: Span | None = None

    @abstractmethod
    def start_span(
        self,
        name: str,
        parent: Span | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span."""
        ...

    @abstractmethod
    def end_span(self, span: Span) -> None:
        """End a span and export it."""
        ...

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None):
        """Context manager for creating a span."""
        span = self.start_span(name, attributes=attributes)
        try:
            yield span
        except Exception as e:
            span.set_status("error", str(e))
            raise
        finally:
            span.finish()
            self.end_span(span)

    def inject_context(self, carrier: dict[str, str]) -> None:
        """Inject trace context into a carrier (for HTTP headers, etc.)."""
        if self._current_span:
            carrier["traceparent"] = f"00-{self._current_span.context.trace_id}-{self._current_span.context.span_id}-01"

    def extract_context(self, carrier: dict[str, str]) -> SpanContext | None:
        """Extract trace context from a carrier."""
        traceparent = carrier.get("traceparent")
        if not traceparent:
            return None

        parts = traceparent.split("-")
        if len(parts) >= 3:
            return SpanContext(
                trace_id=parts[1],
                span_id=parts[2],
            )
        return None


class NoOpTracer(Tracer):
    """No-op tracer for when tracing is disabled."""

    def start_span(self, name: str, parent: Span | None = None, attributes: dict[str, Any] | None = None) -> Span:
        ctx = SpanContext(trace_id="", span_id="")
        return Span(name=name, context=ctx)

    def end_span(self, span: Span) -> None:
        pass
