# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-tests-mcpsession
"""Session continuity over the real MCP transport. Prints MCP_SESSION_OK.

Starts the server under uvicorn (stateful Streamable HTTP), points it at the
local stub service, and drives it with the official MCP client:
  (i)   two asks in one MCP session reach the service with the SAME session id;
  (ii)  explain_last_answer sends the MOST RECENT answer id;
  (iii) correct_last_answer posts a correction, and the next ask in that
        session comes back marked "Improved from your feedback";
  (iv)  a second, separate MCP session does not see the first one's answer.
"""
import asyncio
import os
import socket
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def check(condition, label):
    if not condition:
        raise AssertionError("FAILED: " + label)
    print("  ok - " + label)


def main():
    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from tests.fake_service import FakeNorthstarService

    with FakeNorthstarService(mode="ok") as stub:
        os.environ["NORTHSTAR_ENDPOINT"] = stub.url
        os.environ["NORTHSTAR_TOKEN"] = "test-token"
        os.environ["SAMPLE_MODE"] = "false"
        os.environ.pop("MCP_STATELESS", None)
        from mcp_server.server import asgi_app

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(asgi_app, log_level="critical"))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]),
                                  daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        check(server.started, "server is up")
        url = "http://127.0.0.1:%d/mcp" % port

        async def converse():
            out = {}
            async with streamablehttp_client(url) as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    out["a1"] = (await s.call_tool("ask_northstar", {"question": "How is revenue?"})).structuredContent
                    out["a2"] = (await s.call_tool("ask_northstar", {"question": "And last quarter?"})).structuredContent
                    out["ex"] = (await s.call_tool("explain_last_answer", {})).structuredContent
                    out["co"] = (await s.call_tool("correct_last_answer", {"correction": "Use Mountain, not Pacific."})).structuredContent
                    out["a3"] = (await s.call_tool("ask_northstar", {"question": "Which region led?"})).structuredContent
            async with streamablehttp_client(url) as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    out["other"] = (await s.call_tool("explain_last_answer", {})).structuredContent
            return out

        out = asyncio.run(converse())
        server.should_exit = True
        thread.join(timeout=10)

        asks = [x for x in stub.recorded if x["path"] == "/v1/ask"]
        sids = {x["body"]["session_id"] for x in asks}
        check(len(asks) == 3, "three asks reached the service")
        check(len(sids) == 1, "all asks in one MCP session carry one session id")
        check(out["a1"]["session_id"] == out["a2"]["session_id"], "tool replies report the same session id")
        check(out["a2"]["answer_id"] == "fake-ans-2", "second ask has its own answer id")
        explains = [x for x in stub.recorded if x["path"] == "/v1/explain"]
        check(len(explains) == 1 and explains[0]["body"]["answer_id"] == "fake-ans-2",
              "explain_last_answer sends the most recent answer id")
        check(out["ex"]["status"] == "success", "explain succeeds inside the session")
        feedback = [x for x in stub.recorded if x["path"] == "/v1/feedback"]
        check(len(feedback) == 1 and feedback[0]["body"]["answer_id"] == "fake-ans-2"
              and feedback[0]["body"]["session_id"] in sids,
              "correct_last_answer posts the correction for the latest answer in the same session")
        check(out["a3"]["spoken"].startswith("Improved from your feedback"),
              "the ask after a correction is marked as improved")
        check(not out["a1"]["spoken"].startswith("Improved"), "the ask before the correction is not marked")
        check(out["other"]["status"] == "error" and len(explains) == 1,
              "a separate MCP session cannot explain another session's answer")
    print("MCP_SESSION_OK")


if __name__ == "__main__":
    main()
