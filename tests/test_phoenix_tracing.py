import asyncio
import builtins
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from bifang.agent import Agent
from bifang.config import Config
from bifang.tracing.phoenix import PhoenixTracer, collector_endpoint
from bifang.workspace import Workspace


@contextmanager
def collector():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length", "0")))
            received.append(body)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/traces", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def decoded_spans(received):
    spans = []
    for body in received:
        request = ExportTraceServiceRequest.FromString(body)
        for resource in request.resource_spans:
            for scope in resource.scope_spans:
                spans.extend(scope.spans)
    return spans


def test_phoenix_tracer_exports_otlp_without_prompt_content():
    received = []

    class CollectorHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("authorization"),
                    "content_type": self.headers.get("content-type"),
                    "body": self.rfile.read(int(self.headers.get("content-length", "0"))),
                }
            )
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            return

    collector = ThreadingHTTPServer(("127.0.0.1", 0), CollectorHandler)
    thread = Thread(target=collector.serve_forever, daemon=True)
    thread.start()
    tracer = PhoenixTracer(
        endpoint=f"http://127.0.0.1:{collector.server_port}/v1/traces",
        headers={"authorization": "Bearer test-key"},
    )

    try:
        span = tracer.start_span("agent.call", attributes={"provider": "test"})
        tracer.end_span(span)
        tracer.shutdown()
    finally:
        collector.shutdown()
        collector.server_close()
        thread.join(timeout=2)

    assert len(received) == 1
    assert received[0]["path"] == "/v1/traces"
    assert received[0]["authorization"] == "Bearer test-key"
    assert received[0]["content_type"].startswith("application/x-protobuf")
    assert received[0]["body"]
    assert b"prompt" not in received[0]["body"].lower()


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
def test_agent_trace_contains_actual_tool_execution_and_no_content(tmp_path, monkeypatch, failure, streaming):
    marker = "PRIVATE-SYNTHETIC-CONTENT-DO-NOT-EXPORT"
    (tmp_path / "private-name.txt").write_text(marker)

    async def no_services(self):
        return

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    with collector() as (endpoint, received):
        async def scenario():
            agent = Agent(Config(enable_memory=False, enable_conversation_history=False,
                                 enable_tracing=True, tracing_endpoint=endpoint),
                          Workspace(tmp_path, tmp_path))
            calls = []

            async def complete(messages, **kwargs):
                calls.append(True)
                if len(calls) == 1:
                    return {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "read-1", "type": "function", "function": {
                            "name": "read_file", "arguments": '{"path":"private-name.txt"}'}}]}
                if failure:
                    raise RuntimeError(marker)
                assert marker in messages[-1]["content"]
                return {"role": "assistant", "content": marker,
                        "provider": "test", "model": "test-model",
                        "usage": {"prompt_tokens": 5, "completion_tokens": 3}}

            agent.provider.complete = complete
            async def complete_stream(messages, **kwargs):
                yield await complete(messages, **kwargs)

            agent.provider.complete_stream = complete_stream

            async def ask():
                if streaming:
                    return "".join([chunk async for chunk in agent.ask_stream(marker)])
                return await agent.ask(marker)

            try:
                if failure:
                    with pytest.raises(RuntimeError, match=marker):
                        await ask()
                else:
                    assert await ask() == marker
            finally:
                await agent.close()
                agent.tracer.shutdown()

        asyncio.run(scenario())
    spans = decoded_spans(received)
    assert len(spans) == 4
    root = next(span for span in spans if span.name == "agent.request")
    children = [span for span in spans if span is not root]
    assert all(span.trace_id == root.trace_id and span.parent_span_id == root.span_id for span in children)
    assert all(root.start_time_unix_nano <= span.start_time_unix_nano <=
               span.end_time_unix_nano <= root.end_time_unix_nano for span in children)
    assert sum(span.name == "tool.execute" for span in children) == 1
    assert root.status.code == (2 if failure else 0)
    assert marker.encode() not in b"".join(received)
    assert b"private-name.txt" not in b"".join(received)


def test_stream_cancellation_ends_child_and_parent_spans(tmp_path, monkeypatch):
    async def no_services(self):
        return

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    with collector() as (endpoint, received):
        async def scenario():
            agent = Agent(Config(enable_memory=False, enable_conversation_history=False,
                                 enable_tracing=True, tracing_endpoint=endpoint),
                          Workspace(tmp_path, tmp_path))

            async def complete_stream(*args, **kwargs):
                yield {"content": "partial response"}
                await asyncio.Event().wait()

            agent.provider.complete_stream = complete_stream
            try:
                stream = agent.ask_stream("synthetic request")
                assert await anext(stream) == "partial response"
                await stream.aclose()
                assert agent.tracer._active_span.get() is None
                assert agent.tracer._otel_spans == {}
            finally:
                await agent.close()

        asyncio.run(scenario())
    spans = decoded_spans(received)
    assert len(spans) == 2
    assert all(span.status.code == 2 for span in spans)


def test_nested_context_is_task_local_and_cancellation_is_private():
    with collector() as (endpoint, received):
        tracer = PhoenixTracer(endpoint=endpoint)

        async def worker(fail):
            with tracer.span("agent.request") as root:
                await asyncio.sleep(0)
                with tracer.span("llm.stream") as child:
                    assert root.context.trace_id == child.context.trace_id
                    assert root.context.span_id == child.context.parent_span_id
                    carrier = {}
                    tracer.inject_context(carrier)
                    assert child.context.span_id in carrier["traceparent"]
                    if fail:
                        raise asyncio.CancelledError("PRIVATE-CANCELLATION")
            carrier = {}
            tracer.inject_context(carrier)
            assert carrier == {}

        async def scenario():
            result = await asyncio.gather(worker(False), worker(True), return_exceptions=True)
            assert isinstance(result[1], asyncio.CancelledError)
            assert tracer._active_span.get() is None

        asyncio.run(scenario())
        tracer.shutdown()
    spans = decoded_spans(received)
    assert len({span.trace_id for span in spans}) == 2
    assert sum(span.status.code == 2 for span in spans) == 2
    assert b"PRIVATE-CANCELLATION" not in b"".join(received)


def test_export_drops_content_exception_events_and_unknown_attributes():
    with collector() as (endpoint, received):
        tracer = PhoenixTracer(endpoint=endpoint)
        with tracer.span("agent.request", attributes={"prompt": "PRIVATE-PROMPT"}) as span:
            span.set_attribute("file.content", "PRIVATE-FILE")
            span.set_attribute("usage.prompt_tokens", 4)
            span.add_event("PRIVATE-EVENT", {"exception.message": "PRIVATE-EXCEPTION"})
            span.set_status("error", "PRIVATE-ERROR")
        tracer.shutdown()
    body = b"".join(received)
    assert b"PRIVATE-" not in body
    exported = decoded_spans(received)[0]
    assert not exported.events
    assert not exported.status.message
    assert next(attr for attr in exported.attributes if attr.key == "usage.prompt_tokens").value.int_value == 4


@pytest.mark.parametrize("value", ["https://key@host", "https://host?key=value", "file:///tmp/traces",
                                   "http://localhost:6006/other"])
def test_collector_rejects_ambiguous_or_credential_bearing_urls(value):
    with pytest.raises(ValueError):
        collector_endpoint(value)
    assert collector_endpoint("http://localhost:6006/") == "http://localhost:6006/v1/traces"


def test_explicit_tracing_without_dependencies_fails_visibly(monkeypatch):
    original = builtins.__import__

    def without_sdk(name, *args, **kwargs):
        if name.startswith("opentelemetry.exporter"):
            raise ImportError("synthetic missing extra")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_sdk)
    with pytest.raises(RuntimeError, match="observability extra"):
        PhoenixTracer()
