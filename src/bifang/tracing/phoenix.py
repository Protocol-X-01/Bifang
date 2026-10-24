from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .base import Span, SpanContext, Tracer


def collector_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Phoenix requires an HTTP(S) collector URL without embedded credentials")
    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1/traces"
    elif not path.endswith("/v1/traces"):
        raise ValueError("Phoenix HTTP collector path must end in /v1/traces")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def export_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    text_keys = {"provider", "model", "requested_model", "reported_model", "task_type", "tool", "argument_names",
                 "openinference.span.kind", "error.type"}
    count_keys = {"usage.prompt_tokens", "usage.completion_tokens", "usage.total_tokens"}
    result = {}
    for key, value in attributes.items():
        if key in text_keys and isinstance(value, str):
            result[key] = value[:256]
        elif key in count_keys and type(value) is int and value >= 0:
            result[key] = value
    return result


class PhoenixTracer(Tracer):
    """Exports manual OpenTelemetry spans to an Arize Phoenix collector."""

    def __init__(
        self,
        service_name: str = "bifang",
        endpoint: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(service_name)
        self.endpoint = collector_endpoint(
            endpoint
            or os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
            or os.getenv("PHOENIX_ENDPOINT")
            or "http://localhost:6006/v1/traces"
        )
        self.headers = dict(headers or {})
        api_key = os.getenv("PHOENIX_API_KEY")
        if api_key:
            self.headers.setdefault("authorization", f"Bearer {api_key}")
        self._spans: list[Span] = []
        self._otel_spans: dict[str, Any] = {}
        self._provider = None
        self._otel_tracer = None
        self._closed = False
        self._init_otel()

    def _init_otel(self) -> None:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as error:
            raise RuntimeError("Phoenix tracing requires Bifang's observability extra") from error

        provider = TracerProvider(resource=Resource({
            "service.name": self.service_name,
            "openinference.project.name": os.getenv("PHOENIX_PROJECT_NAME", "bifang"),
        }))
        exporter = OTLPSpanExporter(endpoint=self.endpoint, headers=self.headers, timeout=5)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        self._provider = provider
        self._otel_tracer = provider.get_tracer(self.service_name)

    def start_span(
        self,
        name: str,
        parent: Span | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        if self._closed:
            raise RuntimeError("Phoenix tracer is closed")
        attributes = export_attributes(attributes or {})
        if name not in {"agent.call", "agent.request", "llm.complete", "llm.stream", "tool.execute"}:
            name = "bifang.operation"
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
                attributes=attributes,
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
            attributes=attributes,
        )
        self._spans.append(span)
        return span

    def end_span(self, span: Span) -> None:
        span.finish()
        otel_span = self._otel_spans.pop(span.context.span_id, None)
        if otel_span:
            from opentelemetry.trace import Status, StatusCode

            for key, value in export_attributes(span.attributes).items():
                otel_span.set_attribute(key, value)
            if span.status == "error":
                otel_span.set_status(Status(StatusCode.ERROR))
            otel_span.end()

    def shutdown(self) -> None:
        if self._provider and not self._closed:
            self._closed = True
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
                "attributes": export_attributes(span.attributes),
                "events": [],
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
