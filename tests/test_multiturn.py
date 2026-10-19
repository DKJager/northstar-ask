# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-82e6a54e
"""Multi-turn session-continuity tests. Prints MULTITURN_OK.

Verifies, per the spec:
  (i)   two asks in one MCP session carry the same session_id to the
        private answering service;
  (ii)  explain_last_answer sends the previous answer_id.

Runs against the hand-written local stub service (tests/fake_service.py)
through the same dispatch layer the bridge uses, so the assertions observe
the real JSON bodies that would reach the private service. Audit
compliance (#844): no mocking framework is imported or used anywhere in
this file — the stub is a real threaded HTTP server written by hand.
"""
import os
import sys
import json

# Make `tests.*` and `web_sim.*` importable when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(condition, label):
    if not condition:
        raise AssertionError("FAILED: " + label)
    print("  ok - " + label)


def setup_test_environment(stub_url):
    """Set up test environment variables and return original values for restoration."""
    original_env = {
        "NORTHSTAR_ENDPOINT": os.environ.get("NORTHSTAR_ENDPOINT"),
        "NORTHSTAR_TOKEN": os.environ.get("NORTHSTAR_TOKEN"),
        "SAMPLE_MODE": os.environ.get("SAMPLE_MODE")
    }
    
    os.environ["SAMPLE_MODE"] = "false"
    os.environ["NORTHSTAR_ENDPOINT"] = stub_url
    os.environ["NORTHSTAR_TOKEN"] = "test-token-placeholder-nonprod"
    
    return original_env


def restore_environment(original_env):
    """Restore original environment variables."""
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


def parse_response_body(response_body):
    """Parse response body if it's a JSON string, otherwise return as-is."""
    if isinstance(response_body, str):
        try:
            return json.loads(response_body)
        except json.JSONDecodeError:
            return response_body
    return response_body


def test_shared_session_and_answer_reuse():
    # Save original environment variables
    original_env = None
    
    try:
        # Set up environment before any imports
        from tests.fake_service import FakeNorthstarService
        with FakeNorthstarService(mode="ok") as stub:
            original_env = setup_test_environment(stub.url)

            # Import after env is set so the client picks up the stub endpoint.
            from web_sim.bridge import handle_api, _SESSIONS
            _SESSIONS.clear()

            session = "sess-multiturn-1"

            status1, first_raw = handle_api("/api/ask", {
                "session_id": session,
                "question": "How much revenue did Northstar make last quarter?",
            })
            first = parse_response_body(first_raw)
            
            check(status1 == 200, "first ask returns HTTP 200")
            check(isinstance(first, dict), "first response is a dictionary")
            check(first.get("answer_id") == "fake-ans-1",
                  "first ask returns the stub answer_id")

            status2, second_raw = handle_api("/api/ask", {
                "session_id": session,
                "question": "And last quarter?",
            })
            second = parse_response_body(second_raw)
            
            check(status2 == 200, "follow-up ask returns HTTP 200")
            check(isinstance(second, dict), "second response is a dictionary")
            check(second.get("answer_id") == "fake-ans-2",
                  "second ask returns a new answer_id")
            check(second.get("answer_id") != first.get("answer_id"),
                  "second answer_id differs from first")

            asks = [r for r in stub.recorded if r["path"] == "/v1/ask"]
            check(len(asks) == 2, "both asks reached the service")
            check(all(r["body"].get("session_id") == session for r in asks),
                  "both asks in one session carry the same session_id "
                  "to the service")

            status3, explained_raw = handle_api("/api/explain",
                                            {"session_id": session})
            explained = parse_response_body(explained_raw)
            
            check(status3 == 200, "explain returns HTTP 200")
            check(isinstance(explained, dict), "explain response is a dictionary")
            explains = [r for r in stub.recorded if r["path"] == "/v1/explain"]
            check(len(explains) == 1, "exactly one explain call reached "
                                      "the service")
            check(explains[0]["body"].get("session_id") == session,
                  "explain carries the same session_id")
            check(explains[0]["body"].get("answer_id") == "fake-ans-2",
                  "explain_last_answer sends the MOST RECENT answer_id")

            # A different session must not see the first session's answer.
            status4, other_raw = handle_api("/api/explain",
                                        {"session_id": "sess-multiturn-2"})
            other = parse_response_body(other_raw)
            
            check(status4 == 200 and other.get("card") is None,
                  "a fresh session has no previous answer to explain")
    finally:
        # Restore original environment variables
        if original_env is not None:
            restore_environment(original_env)


def test_error_handling():
    # Save original environment variables
    original_env = None
    
    try:
        # Set up environment before any imports
        from tests.fake_service import FakeNorthstarService
        with FakeNorthstarService(mode="error") as stub:
            original_env = setup_test_environment(stub.url)

            # Import after env is set so the client picks up the stub endpoint.
            from web_sim.bridge import handle_api, _SESSIONS
            _SESSIONS.clear()

            session = "sess-multiturn-error-1"

            status1, first_raw = handle_api("/api/ask", {
                "session_id": session,
                "question": "How much revenue did Northstar make last quarter?",
            })
            # Don't parse response in error case as it might not be JSON
            
            check(status1 != 200, "first ask returns non-200 HTTP status for error case")
            
            # Verify no session state pollution
            check(len(_SESSIONS) == 0, "no session state created on error")
    finally:
        # Restore original environment variables
        if original_env is not None:
            restore_environment(original_env)


if __name__ == "__main__":
    test_shared_session_and_answer_reuse()
    test_error_handling()
    print("MULTITURN_OK")
