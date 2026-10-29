from unittest.mock import Mock

import pytest

from bifang.config import Config
from bifang.tracing import create_tracer
from bifang.tracing.langsmith import LangSmithTracer, langsmith_endpoint
from bifang.tracing.phoenix import PhoenixTracer


@pytest.mark.parametrize("url", ["http://api.smith.langchain.com", "https://unknown.invalid/otel",
                                 "https://secret@api.smith.langchain.com", "https://api.smith.langchain.com/?key=secret"])
def test_langsmith_rejects_unapproved_key_destinations(url):
    with pytest.raises(ValueError):
        langsmith_endpoint(url)


def test_langsmith_headers_and_metadata_never_inherit_phoenix_credentials(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-langsmith-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "bifang-test")
    monkeypatch.setenv("PHOENIX_API_KEY", "synthetic-unrelated-key")
    monkeypatch.setattr(LangSmithTracer, "_init_otel", lambda self: None)
    tracer = create_tracer("langsmith", endpoint="https://eu.api.smith.langchain.com/otel")
    assert tracer.endpoint == "https://eu.api.smith.langchain.com/otel/v1/traces"
    assert tracer.headers == {"x-api-key": "synthetic-langsmith-key", "Langsmith-Project": "bifang-test"}
    assert "authorization" not in tracer.headers
    span = tracer.start_span("llm.complete", attributes={"provider": "nebius", "prompt": "private prompt"})
    span.set_attribute("usage.prompt_tokens", 7)
    span.set_attribute("error.message", "private error text")
    otel = Mock()
    tracer._otel_spans[span.context.span_id] = otel
    tracer.end_span(span)
    exported = {call.args[0]: call.args[1] for call in otel.set_attribute.call_args_list}
    assert exported["langsmith.span.kind"] == "llm"
    assert exported["gen_ai.usage.input_tokens"] == 7
    assert "private" not in str(exported)
    assert "synthetic" not in str(exported)


def test_langsmith_is_explicit_and_configuration_is_read(monkeypatch):
    monkeypatch.setenv("BIFANG_TRACING_BACKEND", "langsmith")
    assert Config.load().tracing_backend == "langsmith"
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    with pytest.raises(ValueError, match="requires LANGSMITH_API_KEY"):
        LangSmithTracer(endpoint="https://api.smith.langchain.com")
    with pytest.raises(ValueError, match="backend"):
        create_tracer("unknown")


def test_phoenix_remains_available_with_its_own_authentication(monkeypatch):
    monkeypatch.setenv("PHOENIX_API_KEY", "synthetic-phoenix")
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-unrelated")
    monkeypatch.setattr(PhoenixTracer, "_init_otel", lambda self: None)
    tracer = create_tracer("phoenix", endpoint="http://localhost:6006/v1/traces")
    assert tracer.headers == {"authorization": "Bearer synthetic-phoenix"}
    assert "x-api-key" not in tracer.headers
