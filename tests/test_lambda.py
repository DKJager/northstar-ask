# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-tests-lambda
"""Lambda entry point test. Prints LAMBDA_OK.

Feeds Function-URL-shaped events to mcp_server.server.lambda_handler (the
handler named in deploy/template.yaml) and checks it serves the same tools
as the local run, keeps working across invocations, keeps a follow-up
conversation together when the client sends X-Northstar-Session, and —
for a standard MCP client — mints an Mcp-Session-Id at initialize that
later turns reuse.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def check(condition, label):
    if not condition:
        raise AssertionError("FAILED: " + label)
    print("  ok - " + label)


def invoke_raw(handler, payload, extra=None, method="POST"):
    """Invoke the handler with a Function-URL-shaped event; return the raw
    Lambda response dict (statusCode, headers, body)."""
    headers = {"content-type": "application/json",
               "accept": "application/json, text/event-stream",
               "host": "abc123.lambda-url.us-east-1.on.aws"}
    headers.update(extra or {})
    event = {"rawPath": "/mcp", "rawQueryString": "",
             "requestContext": {"http": {"method": method}},
             "headers": headers,
             "body": json.dumps(payload) if payload is not None else "",
             "isBase64Encoded": False}
    return handler(event, None)


def invoke(handler, payload, extra=None):
    resp = invoke_raw(handler, payload, extra)
    body = json.loads(resp["body"]) if resp["body"] else None
    return resp["statusCode"], body


def response_headers(resp):
    return {k.lower(): v for k, v in (resp.get("headers") or {}).items()}


def tool(handler, name, args, extra=None, rid=3):
    status, body = invoke(handler, {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                    "params": {"name": name, "arguments": args}}, extra)
    check(status == 200, "tools/call %s returns HTTP 200" % name)
    return body["result"]["structuredContent"]


INIT_PAYLOAD = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "1"}}}


def main():
    from tests.fake_service import FakeNorthstarService
    os.environ["MCP_STATELESS"] = "true"
    os.environ["MCP_ALLOW_ANY_HOST"] = "true"
    os.environ["SAMPLE_MODE"] = "true"
    from mcp_server.server import lambda_handler

    status, body = invoke(lambda_handler, INIT_PAYLOAD)
    check(status == 200 and "serverInfo" in body["result"], "initialize answers through the Lambda adapter")
    status, body = invoke(lambda_handler, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = sorted(t["name"] for t in body["result"]["tools"])
    check(names == ["ask_northstar", "correct_last_answer", "explain_last_answer", "weekly_brief"],
          "tools/list over Lambda shows the same four tools")
    sample = tool(lambda_handler, "ask_northstar",
                  {"question": "How much revenue did Northstar make last quarter?"})
    check(sample["spoken"].startswith("Recorded sample:") and sample["card"]["rows"],
          "a second invocation reuses the warm runtime and returns a recorded-sample card")

    # Live (stub) mode: continuity needs the explicit session header.
    with FakeNorthstarService(mode="ok") as stub:
        os.environ.update(SAMPLE_MODE="false", NORTHSTAR_ENDPOINT=stub.url, NORTHSTAR_TOKEN="test-token")
        h = {"x-northstar-session": "judge-1"}
        tool(lambda_handler, "ask_northstar", {"question": "q1"}, h)
        tool(lambda_handler, "ask_northstar", {"question": "q2"}, h)
        ex = tool(lambda_handler, "explain_last_answer", {}, h)
        check(ex["status"] == "success", "explain works across invocations with the session header")
        explains = [r for r in stub.recorded if r["path"] == "/v1/explain"]
        check(explains[0]["body"]["answer_id"] == "fake-ans-2" and explains[0]["body"]["session_id"] == "judge-1",
              "the header value is the session id and the latest answer id is sent")
        no_hdr = tool(lambda_handler, "explain_last_answer", {})
        check(no_hdr["status"] == "error", "without the header there is honestly no previous answer to explain")

        # Standard MCP client flow: initialize -> Mcp-Session-Id -> follow-up
        # turns that carry the id and reuse the same conversation state.
        init_resp = invoke_raw(lambda_handler, INIT_PAYLOAD)
        init_hdrs = response_headers(init_resp)
        sid = init_hdrs.get("mcp-session-id")
        check(init_resp["statusCode"] == 200 and bool(sid),
              "initialize on Lambda returns an Mcp-Session-Id header")
        check("mcp-session-id" in (init_hdrs.get("access-control-expose-headers") or "").lower(),
              "the session header is exposed to browser clients via CORS")
        other = response_headers(invoke_raw(lambda_handler, INIT_PAYLOAD)).get("mcp-session-id")
        check(other and other != sid, "each initialize mints a distinct session id")

        mh = {"mcp-session-id": sid}
        echo = invoke_raw(lambda_handler, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                           "params": {"name": "ask_northstar",
                                                      "arguments": {"question": "q3"}}}, mh)
        check(echo["statusCode"] == 200 and response_headers(echo).get("mcp-session-id") == sid,
              "a later call carrying Mcp-Session-Id gets the same id echoed back")
        first = json.loads(echo["body"])["result"]["structuredContent"]
        check(first["session_id"] == sid, "the tool resolves the conversation from Mcp-Session-Id")
        second = tool(lambda_handler, "ask_northstar", {"question": "q4"}, mh, rid=5)
        ex2 = tool(lambda_handler, "explain_last_answer", {}, mh, rid=6)
        check(ex2["status"] == "success" and ex2["session_id"] == sid,
              "the follow-up turn ('explain that') reuses the minted session")
        explains = [r for r in stub.recorded if r["path"] == "/v1/explain"]
        last = explains[-1]["body"]
        check(last["session_id"] == sid and last["answer_id"] == second["answer_id"],
              "the explain call sends the minted session id and the latest answer id")
        corr = tool(lambda_handler, "correct_last_answer", {"correction": "wrong quarter"}, mh, rid=7)
        check(corr["status"] != "error" and corr["session_id"] == sid,
              "the 'correct me' turn also reuses the minted session")

        bye = invoke_raw(lambda_handler, None, mh, method="DELETE")
        check(bye["statusCode"] == 200, "DELETE with the session id ends the session cleanly")
        gone = tool(lambda_handler, "explain_last_answer", {}, mh, rid=8)
        check(gone["status"] == "error", "after DELETE there is honestly no previous answer to explain")
    print("LAMBDA_OK")


if __name__ == "__main__":
    main()
