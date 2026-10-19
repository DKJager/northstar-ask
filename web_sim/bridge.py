# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-29a5e038
"""Local HTTP bridge between the web simulator and the MCP server tools.

The browser talks plain JSON POSTs to this bridge; the bridge calls the
same client contract used by the MCP tools, so the simulator demonstrates
the real end-product surface. SAMPLE_MODE is honoured by the client, which
prefixes every recorded spoken reply with "Recorded sample:".

Endpoints:
  GET  /            -> web_sim/index.html
  GET  /app.js      -> simulator logic
  GET  /style.css   -> simulator styling
  POST /api/ask      {"session_id", "question"}   -> spoken + card JSON
  POST /api/brief    {"session_id"}               -> spoken + cards JSON
  POST /api/explain  {"session_id", "answer_id"?} -> spoken + card JSON
  POST /api/correct  {"session_id", "correction", "answer_id"?} -> spoken confirmation

Note: Callers should persist and resend the session_id from previous responses.
Alternatively, callers can explicitly provide answer_id in explain/correct requests.
If no session_id is provided, a new one is generated for each request.

Demo scope (local simulator only; not a production service):
  - The bridge binds to 127.0.0.1 by default and sends open CORS headers
    (``Access-Control-Allow-Origin: *``) so the simulator page can be
    opened from any local origin. This is demo-only; it performs no
    authentication and must not be exposed on a public interface.
  - Session state (the last answer id per session) lives in process memory
    with a TTL and size cap. It is lost when the bridge restarts; after a
    restart "explain that" and "correct me" report nothing to explain or
    correct until a new ask is made.
  - There is no DELETE endpoint: sessions cannot be ended explicitly; they
    expire by TTL eviction only. Only GET, POST and OPTIONS are handled.
  The hosted Lambda has its own demo-only limits (see deploy/template.yaml,
  which notes ``AWS_IAM`` for non-demo use, and the README).

Stdlib only. Run:  python web_sim/bridge.py  then open http://127.0.0.1:8765/
"""
import json
import os
import sys
import uuid
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.northstar_client import NorthstarClient, NorthstarClientError  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_HOST = os.environ.get("BRIDGE_HOST", "127.0.0.1")
_PORT = int(os.environ.get("BRIDGE_PORT", "8765"))

_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}

# Per-browser-session state: last answer id for explain / correct turns.
# Thread-safe with lock and TTL eviction.
# Demo-only: in-process memory, not persisted; lost on bridge restart.
_SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()
SESSION_TTL = 3600  # 1 hour
SESSION_MAX_COUNT = 1000


def _state(session_id):
    """Get or create session state with thread safety and eviction."""
    with _SESSIONS_LOCK:
        # Evict old sessions if we're at capacity
        if len(_SESSIONS) >= SESSION_MAX_COUNT:
            now = time.time()
            expired = [
                sid for sid, data in _SESSIONS.items() 
                if now - data.get("last_access", 0) > SESSION_TTL
            ]
            for sid in expired:
                del _SESSIONS[sid]
        
        # Create or update session
        now = time.time()
        if session_id not in _SESSIONS:
            _SESSIONS[session_id] = {
                "last_answer_id": None,
                "last_access": now
            }
        else:
            _SESSIONS[session_id]["last_access"] = now
            
        return _SESSIONS[session_id]


def _peek_state(session_id):
    """Return existing session state (touching it) without creating any."""
    with _SESSIONS_LOCK:
        state = _SESSIONS.get(session_id)
        if state is not None:
            state["last_access"] = time.time()
        return state


def handle_api(path, payload):
    """Dispatch an API call and return (status, dict). Pure for tests.

    Session state is only created after a successful ask, so a failed
    call never leaves a half-initialised session behind.
    """
    session_id = payload.get("session_id") or "sim-" + uuid.uuid4().hex[:12]
    state = _peek_state(session_id) or {}

    try:
        # Construct client inside try block to catch construction errors
        client = NorthstarClient()
        
        if path == "/api/ask":
            result = client.ask(session_id, payload.get("question", ""))
            _state(session_id)["last_answer_id"] = result.get("answer_id")
            return 200, {
                "session_id": session_id,
                "spoken": result.get("spoken", ""),
                "card": result.get("card"),
                "answer_id": result.get("answer_id"),
            }
        if path == "/api/brief":
            result = client.brief(session_id)
            # Fix: Use consistent .get() to avoid KeyError
            card = result.get("card")
            cards = result.get("cards") or ([card] if card else [])
            return 200, {
                "session_id": session_id,
                "spoken": result.get("spoken", ""),
                "cards": cards,
            }
        if path == "/api/explain":
            # Allow explicit answer_id in payload to override session state
            answer_id = payload.get("answer_id") or state.get("last_answer_id")
            if not answer_id:
                return 200, {"session_id": session_id,
                             "spoken": "Nothing to explain yet.",
                             "card": None}
            result = client.explain(session_id, answer_id)
            return 200, {
                "session_id": session_id,
                "spoken": result.get("spoken", ""),
                "card": result.get("card"),
            }
        if path == "/api/correct":
            # Allow explicit answer_id in payload to override session state
            answer_id = payload.get("answer_id") or state.get("last_answer_id")
            if not answer_id:
                return 200, {"session_id": session_id,
                             "spoken": "Nothing to correct yet."}
            result = client.feedback(session_id, answer_id,
                                     payload.get("correction", ""))
            return 200, {"session_id": session_id,
                         "spoken": result.get("spoken", "")}
        return 404, {"session_id": session_id, "error": "unknown endpoint"}
    except NorthstarClientError as exc:
        return 502, {"session_id": session_id, "error": str(exc)}
    except ValueError:
        # e.g. missing NORTHSTAR_TOKEN: a configuration problem, not a bug
        return 503, {"session_id": session_id,
                     "error": "The answering service is not configured."}


class BridgeHandler(BaseHTTPRequestHandler):
    """Minimal request handler; no external dependencies.

    Demo-only: open CORS headers are sent on every response so the local
    simulator page works from any local origin. No authentication is
    performed. Only GET, POST and OPTIONS are handled; there is no DELETE
    (sessions expire by TTL, see the module docstring).
    """

    server_version = "NorthstarBridge/1.0"

    def log_message(self, fmt, *args):  # keep the console quiet in tests
        pass

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Demo-only open CORS; the bridge is a local simulator, not a
        # public service.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected; suppress traceback

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/status":
            self._send_json(200, {
                "sample_mode": os.environ.get("SAMPLE_MODE", "").lower() == "true"})
            return
        entry = _STATIC.get(route)
        if not entry:
            self._send_json(404, {"error": "not found"})
            return
        filename, content_type = entry
        try:
            with open(os.path.join(_HERE, filename), "rb") as fh:
                body = fh.read()
        except OSError:
            self._send_json(500, {"error": "failed to read static file"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected; suppress traceback

    def do_POST(self):
        try:
            length_str = self.headers.get("Content-Length") or "0"
            length = int(length_str)
            if length > 64 * 1024:
                self._send_json(413, {"error": "request too large"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8")
                                     or "{}")
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid JSON"})
                return
            status, obj = handle_api(self.path.split("?", 1)[0], payload)
            self._send_json(status, obj)
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
        except Exception:
            self._send_json(500, {"error": "internal server error"})


def make_server(host=_HOST, port=_PORT):
    return ThreadingHTTPServer((host, port), BridgeHandler)


if __name__ == "__main__":
    server = make_server()
    print("Northstar Ask simulator bridge on http://%s:%d/"
          % (_HOST, _PORT))
    print("SAMPLE_MODE=%s" % os.environ.get("SAMPLE_MODE", "(unset)"))
    print("Demo-only local bridge: open CORS, no auth, session state "
          "in memory (lost on restart).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass  # exit cleanly without deadlock (issue #166)
