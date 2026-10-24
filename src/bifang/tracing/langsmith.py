from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from .base import Span
from .phoenix import PhoenixTracer, export_attributes


def langsmith_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    hosts = {"api.smith.langchain.com", "eu.api.smith.langchain.com",
             "apac.api.smith.langchain.com", "aws.api.smith.langchain.com"}
    if (parsed.scheme != "https" or parsed.hostname not in hosts or parsed.port not in {None, 443}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Choose an official HTTPS LangSmith regional API endpoint without embedded credentials")
    path = parsed.path.rstrip("/")
    if path not in {"", "/otel", "/otel/v1/traces"}:
        raise ValueError("LangSmith tracing requires its OTLP traces endpoint")
    return urlunsplit(("https", parsed.netloc, "/otel/v1/traces", "", ""))


class LangSmithTracer(PhoenixTracer):
    def __init__(self, service_name: str = "bifang", endpoint: str | None = None):
        selected = langsmith_endpoint(endpoint or os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"))
        key = os.getenv("LANGSMITH_API_KEY")
        if not key:
            raise ValueError("LangSmith tracing requires LANGSMITH_API_KEY")
        project = os.getenv("LANGSMITH_PROJECT", "bifang")
        if not project or len(project) > 128 or any(ord(character) < 32 for character in project):
            raise ValueError("Provide a bounded LangSmith project name without control characters")
        headers = {"x-api-key": key, "Langsmith-Project": project}
        workspace = os.getenv("LANGSMITH_WORKSPACE_ID")
        if workspace:
            headers["x-tenant-id"] = workspace
        super().__init__(service_name, selected, headers, phoenix_environment=False, resource_attributes={})

    def end_span(self, span: Span) -> None:
        otel = self._otel_spans.get(span.context.span_id)
        if otel:
            safe = export_attributes(span.attributes)
            kind = "llm" if span.name.startswith("llm.") else "tool" if span.name == "tool.execute" else "chain"
            otel.set_attribute("langsmith.span.kind", kind)
            for key, value in safe.items():
                otel.set_attribute(f"langsmith.metadata.{key}", value)
            for original, mapped in {"provider": "gen_ai.system", "requested_model": "gen_ai.request.model",
                                     "usage.prompt_tokens": "gen_ai.usage.input_tokens",
                                     "usage.completion_tokens": "gen_ai.usage.output_tokens"}.items():
                if original in safe:
                    otel.set_attribute(mapped, safe[original])
        super().end_span(span)
