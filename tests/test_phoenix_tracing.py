from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from bifang.tracing.phoenix import PhoenixTracer


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
