from __future__ import annotations

import json
import os
from typing import Any

from .base import Span, SpanContext, Tracer


class PhoenixTracer(Tracer):
    """Exports manual OpenTelemetry spans to an Arize Phoenix collector."""

    def __init__(
        self,
        service_name: str = "bifang",
        endpoint: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(service_name)
        self.endpoint = (
            endpoint
            or os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
            or os.getenv("PHOENIX_ENDPOINT")
            or "http://localhost:6006/v1/traces"
        )
        self.headers = headers or {}
        api_key = os.getenv("PHOENIX_API_KEY")
        if api_key:
            self.headers.setdefault("authorization", f"Bearer {api_key}")
        self._spans: list[Span] = []
        self._otel_spans: dict[str, Any] = {}
        self._provider = None
        self._otel_tracer = None
        self._init_otel()

    def _init_otel(self) -> None:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            return

        provider = TracerProvider(resource=Resource.create({"service.name": self.service_name}))
        exporter = OTLPSpanExporter(endpoint=self.endpoint, headers=self.headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        self._provider = provider
        self._otel_tracer = provider.get_tracer(self.service_name)

    def start_span(
        self,
        name: str,
        parent: Span | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        if self._otel_tracer:
            from opentelemetry import trace

            parent_otel = self._otel_spans.get(parent.context.span_id) if parent else None
            context = trace.set_span_in_context(parent_otel) if parent_otel else None
            otel_span = self._otel_tracer.start_span(name, context=context)
            otel_context = otel_span.get_span_context()
            span = Span(
                name=name,
                context=SpanContext(
                    trace_id=f"{otel_context.trace_id:032x}",
                    span_id=f"{otel_context.span_id:016x}",
                    parent_span_id=parent.context.span_id if parent else None,
                ),
                attributes=attributes or {},
            )
            self._otel_spans[span.context.span_id] = otel_span
            return span

        trace_id = parent.context.trace_id if parent else os.urandom(16).hex()
        span_id = os.urandom(8).hex()
        span = Span(
            name=name,
            context=SpanContext(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent.context.span_id if parent else None,
            ),
            attributes=attributes or {},
        )
        self._spans.append(span)
        return span

    def end_span(self, span: Span) -> None:
        span.finish()
        otel_span = self._otel_spans.pop(span.context.span_id, None)
        if otel_span:
            from opentelemetry.trace import Status, StatusCode

            for key, value in span.attributes.items():
                if not isinstance(value, (str, bool, int, float)):
                    value = json.dumps(value, ensure_ascii=False, default=str)
                otel_span.set_attribute(key, value)
            for event in span.events:
                otel_span.add_event(event["name"], attributes=event.get("attributes", {}))
            if span.status == "error":
                message = str(span.attributes.get("error.message", ""))
                otel_span.set_status(Status(StatusCode.ERROR, message))
            otel_span.end()

    def shutdown(self) -> None:
        if self._provider:
            self._provider.shutdown()

    def export_spans(self) -> list[dict[str, Any]]:
        return [
            {
                "name": span.name,
                "trace_id": span.context.trace_id,
                "span_id": span.context.span_id,
                "parent_span_id": span.context.parent_span_id,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "duration": span.duration,
                "attributes": span.attributes,
                "events": span.events,
                "status": span.status,
            }
            for span in self._spans
            if span.end_time is not None
        ]


def create_phoenix_tracer(
    service_name: str = "bifang",
    endpoint: str | None = None,
) -> PhoenixTracer:
    return PhoenixTracer(service_name=service_name, endpoint=endpoint)
