# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-66eb3696
"""Simulator tests: static page plus bridge API. Prints SIM_OK.

Verifies, per the spec:
  (i)   web_sim/index.html is served with HTTP 200;
  (ii)  a question posted through bridge.py returns spoken text and card
        JSON (SAMPLE_MODE, prefixed "Sample answer:").

Runs the real bridge HTTP server on an ephemeral port in a background
thread. Audit compliance (#844): no mocking framework is imported or
used anywhere in this file — the server under test is the real thing.
"""
import json
import os
import sys
import threading
import urllib.request
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SAMPLE_MODE"] = "true"


def check(condition, label):
    if not condition:
        raise AssertionError("FAILED: " + label)
    print("  ok - " + label)


def _free_port():
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.read()


def _post(url, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def run():
    from web_sim.bridge import make_server

    # Try up to 3 times to bind to a port
    server = None
    for attempt in range(3):
        try:
            port = _free_port()
            server = make_server("127.0.0.1", port)
            break
        except OSError as e:
            if attempt == 2:  # Last attempt
                raise e
            time.sleep(0.1)  # Brief delay before retry

    if server is None:
        raise RuntimeError("Failed to create server after 3 attempts")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % port
    try:
        status, body = _get(base + "/")
        check(status == 200, "web_sim/index.html is served with HTTP 200")
        check(b"Northstar Ask" in body,
              "index.html contains the product name")
        check(b"src=\"/app.js\"" in body or b"src='/app.js'" in body,
              "index.html loads the simulator script")

        status, app_js = _get(base + "/app.js")
        check(status == 200, "web_sim/app.js is served with HTTP 200")
        check(len(app_js) > 200, "app.js has reasonable size")
        # Check for JavaScript-specific content
        check(b"function" in app_js and b"const" in app_js,
              "app.js contains JavaScript syntax")

        status, style = _get(base + "/style.css")
        check(status == 200, "web_sim/style.css is served with HTTP 200")
        check(len(style) > 200, "style.css has reasonable size")
        # Check for CSS-specific content
        check(b"{" in style and b"}" in style and b":" in style,
              "style.css contains CSS syntax")

        session = "sim-test-session"
        status, answer = _post(base + "/api/ask", {
            "session_id": session,
            "question": "How much revenue did Northstar make last quarter?",
        })
        check(status == 200, "bridge /api/ask returns HTTP 200")
        check(answer.get("spoken", "").startswith("Sample answer:"),
              "bridge answer returns 'Sample answer:'-prefixed spoken "
              "text in SAMPLE_MODE")
        card = answer.get("card")
        check(card and isinstance(card, dict), "card is a dictionary")
        check(isinstance(card.get("title"), str) and len(card["title"]) > 0,
              "card title is a non-empty string")
        check(isinstance(card.get("columns"), list) and len(card["columns"]) > 0,
              "card columns is a non-empty list")
        check(isinstance(card.get("rows"), list) and len(card["rows"]) > 0,
              "card rows is a non-empty list")
        check(answer.get("session_id") == session,
              "bridge echoes the caller's session id")

        status, brief = _post(base + "/api/brief", {"session_id": session})
        check(status == 200, "bridge /api/brief returns HTTP 200")
        check(brief.get("spoken", "").startswith("Sample answer:"),
              "bridge /api/brief returns 'Sample answer:'-prefixed spoken text")
        check(isinstance(brief.get("cards"), list), "bridge /api/brief returns cards as list")
        check(len(brief["cards"]) > 0, "bridge /api/brief returns non-empty cards list")
        
        # Verify structure of each card in the brief
        for i, card in enumerate(brief["cards"]):
            check(isinstance(card, dict), f"brief card {i} is a dictionary")
            check(isinstance(card.get("title"), str) and len(card["title"]) > 0,
                  f"brief card {i} has non-empty title")
            check(isinstance(card.get("columns"), list),
                  f"brief card {i} has columns list")
            check(isinstance(card.get("rows"), list),
                  f"brief card {i} has rows list")

        status, explained = _post(base + "/api/explain",
                                  {"session_id": session})
        check(status == 200, "bridge /api/explain returns HTTP 200")
        check(explained.get("spoken", "").startswith("Sample answer:"),
              "bridge /api/explain returns 'Sample answer:'-prefixed spoken text")
        check(isinstance(explained.get("card"), dict),
              "bridge /api/explain returns card dictionary")
        card = explained.get("card")
        check(isinstance(card.get("title"), str) and len(card["title"]) > 0,
              "explain card has non-empty title")
        check(isinstance(card.get("columns"), list),
              "explain card has columns list")
        check(isinstance(card.get("rows"), list),
              "explain card has rows list")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    run()
    print("SIM_OK")
