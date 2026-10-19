# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-7fa1de74
# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-tests-fakesvc
"""Hand-written local stub of the private Northstar answering service.

Used ONLY by tests. No mocking frameworks: this is a real stdlib HTTP
server with scripted behaviours, started on an ephemeral port by each
test that needs it.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _StubHandler(BaseHTTPRequestHandler):
    """Handler that reads all state from self.server (the ThreadingHTTPServer)."""
    server_version = "FakeNorthstar/1.0"

    def log_message(self, fmt, *args):
        pass

    def _reply(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client gave up (timeout test)

    def do_POST(self):
        server = self.server
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}

        with server._lock:
            server._recorded.append({
                "path": self.path.split("?", 1)[0],
                "body": payload,
                "had_auth": bool(self.headers.get("Authorization")),
            })
            server.request_count += 1

        mode = server.mode
        if mode in ("always_500", "error"):
            self._reply(500, {"error": "stubbed failure"})
            return
        if mode == "flaky" and server.request_count == 1:
            self._reply(500, {"error": "stubbed first-try failure"})
            return
        if mode in ("slow", "delay"):
            time.sleep(server.delay_seconds)
        if mode == "oversize":
            big_card = {
                "title": "Oversized",
                "columns": ["c"],
                "rows": [["x" * 1024]] * 300,
            }
            self._reply(200, {"spoken": "too big", "card": big_card,
                              "answer_id": "fake-big"})
            return

        path = self.path.split("?", 1)[0]
        if path == "/v1/ask":
            sid = str(payload.get("session_id", ""))
            with server._lock:
                server._asks += 1
                number = server._asks
                improved = sid in server._corrected
            lead = "Improved from your feedback: " if improved else ""
            self._reply(200, {
                "spoken": lead + "Stub answer to: " + str(payload.get("question", "")),
                "card": {
                    "title": "Stub Card", "columns": ["Metric", "Value"],
                    "rows": [["Revenue", "$100"]], "chart_hint": "bar",
                    "sources": ["stub"], "confidence": "high",
                },
                "answer_id": "fake-ans-%d" % number,
            })
        elif path == "/v1/brief":
            self._reply(200, {
                "spoken": "Stub weekly brief.",
                "cards": [{
                    "title": "Stub Brief", "columns": ["Metric", "Value"],
                    "rows": [["Trend", "Up"]], "chart_hint": "table",
                    "sources": ["stub"], "confidence": "medium",
                }],
                "answer_id": "fake-ans-brief",
            })
        elif path == "/v1/explain":
            self._reply(200, {
                "spoken": "Stub explanation for " + str(payload.get("answer_id", "")),
                "card": {
                    "title": "Stub Explanation", "columns": ["Signal", "Reading"],
                    "rows": [["Trend", "On target"]], "chart_hint": "table",
                    "sources": ["stub"], "confidence": "medium",
                },
            })
        elif path == "/v1/feedback":
            with server._lock:
                server._corrected.add(str(payload.get("session_id", "")))
            self._reply(200, {"spoken": "Stub: correction noted.", "status": "recorded"})
        else:
            self._reply(404, {"error": "unknown stub path"})


class FakeNorthstarService:
    """Context manager that runs the stub HTTP server in a background thread."""

    def __init__(self, mode="ok", delay_seconds=0.0, delay=None):
        if delay is not None:
            delay_seconds = float(delay)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        self._lock = threading.Lock()
        self._server._lock = self._lock
        self._server._recorded = []
        self._server.mode = mode
        self._server.delay_seconds = delay_seconds
        self._server.request_count = 0
        self._server._asks = 0
        self._server._corrected = set()
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)

    @property
    def mode(self):
        return self._server.mode

    @mode.setter
    def mode(self, value):
        self._server.mode = value

    @property
    def delay_seconds(self):
        return self._server.delay_seconds

    @delay_seconds.setter
    def delay_seconds(self, value):
        self._server.delay_seconds = value

    @property
    def url(self):
        host, port = self._server.server_address[:2]
        return "http://%s:%d" % (host, port)

    @property
    def recorded(self):
        with self._lock:
            return list(self._server._recorded)

    @property
    def request_count(self):
        with self._lock:
            return self._server.request_count

    @request_count.setter
    def request_count(self, value):
        with self._lock:
            self._server.request_count = value

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        return False
