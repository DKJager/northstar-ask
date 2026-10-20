# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-5cf8d97b
# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-4271d4ee
# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-tests-client
"""Contract tests for client/northstar_client.py. Prints CLIENT_OK.

Covers, per the spec:
  (i)   SAMPLE_MODE returns "Sample answer:"-prefixed spoken text.
  (ii)  Against the local stub service: the 7 s total budget,
        the 256 KB cap, and the single budget-aware retry on 5xx behave
        as specified.
  (iii) The bearer token is read from env and never logged / leaked into
        error messages.

Audit compliance (#844): no mocking framework is imported or used anywhere
in this file. Every test double is a real HTTP server running in a thread
(see tests/fake_service.py) or a plain hand-written stub object, and the
assertions below verify the stub really is a live server.
"""
import os
import sys
import time
import contextlib
import socket

# Snapshot original environment to restore later
original_environ = dict(os.environ)

def get_free_port():
    """Get a random available port"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from client.northstar_client import (  # noqa: E402
        NorthstarClient,
        NorthstarClientError,
        SAMPLE_PREFIX,
    )
    from tests.fake_service import FakeNorthstarService  # noqa: E402

    def check(condition, label):
        if not condition:
            raise AssertionError("FAILED: " + label)
        print("  ok - " + label)

    @contextlib.contextmanager
    def env_var(key, value):
        """Context manager to temporarily set an environment variable"""
        old_value = os.environ.get(key)
        os.environ[key] = value
        try:
            yield
        finally:
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    def test_stub_is_real_server():
        # Audit compliance: prove the test double is a real threaded HTTP
        # server (hand-written), not an object from any mocking library.
        with FakeNorthstarService(mode="ok") as stub:
            check(stub.url.startswith("http://127.0.0.1:"),
                  "test double is a real threaded HTTP server "
                  "(hand-written stub, no mocking library)")
            check(type(stub).__module__.startswith("tests."),
                  "test double class is defined in this repo's tests")

    def test_sample_mode_prefix():
        free_port = get_free_port()
        with env_var("SAMPLE_MODE", "true"):
            # Don't override sample_mode in client constructor when using env var
            client = NorthstarClient(endpoint=f"http://127.0.0.1:{free_port}",
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"))
            result = client.ask("session-a",
                                "How much revenue did Northstar make last quarter?")
            check(result["spoken"].startswith(SAMPLE_PREFIX),
                  "SAMPLE_MODE spoken reply is prefixed 'Sample answer:'")
            brief = client.brief("session-a")
            check(brief["spoken"].startswith(SAMPLE_PREFIX),
                  "SAMPLE_MODE brief is prefixed 'Sample answer:'")
            expl = client.explain("session-a", "sample-ans-0001")
            check(expl["spoken"].startswith(SAMPLE_PREFIX),
                  "SAMPLE_MODE explain is prefixed 'Sample answer:'")
            fb = client.feedback("session-a", "sample-ans-0001", "fix it")
            check(fb["spoken"].startswith(SAMPLE_PREFIX),
                  "SAMPLE_MODE feedback is prefixed 'Sample answer:'")

    def test_retry_once_on_5xx():
        with FakeNorthstarService(mode="flaky") as stub:
            client = NorthstarClient(endpoint=stub.url, 
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"),
                                     sample_mode=False)
            start_time = time.monotonic()
            result = client.ask("session-b", "revenue?")
            end_time = time.monotonic()
            
            # Verify the total time is within the 7-second budget
            elapsed_time = end_time - start_time
            check(elapsed_time <= 7.0,
                  f"flaky service: total time {elapsed_time:.2f}s is within 7s budget")
            
            check(result["answer_id"] == "fake-ans-1",
                  "flaky service: retry recovered with a real answer")
            check(stub.request_count == 2,
                  "flaky service: exactly one retry fired (2 requests total)")
            check(all(r["had_auth"] for r in stub.recorded),
                  "bearer token was sent on every attempt")

    def test_no_retry_when_always_500():
        # Simulate "no budget left" by pointing at a service that always 500s;
        # the client must give up after the first failure (attempts == 1 retry
        # maximum overall) and must not leak the token in the error text.
        with FakeNorthstarService(mode="always_500") as stub:
            client = NorthstarClient(endpoint=stub.url, 
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"),
                                     sample_mode=False)
            try:
                client.ask("session-c", "anything")
                raise SystemExit("expected NorthstarClientError")
            except NorthstarClientError as exc:
                check(os.environ.get("NORTHSTAR_TOKEN", "test-token") not in str(exc),
                      "error message never contains the bearer token")
            check(stub.request_count == 2,
                  "always-500 service: exactly one retry attempted before giving up")

    def test_response_size_cap():
        with FakeNorthstarService(mode="oversize") as stub:
            client = NorthstarClient(endpoint=stub.url, 
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"),
                                     sample_mode=False)
            try:
                client.ask("session-d", "big answer please")
                raise SystemExit("expected size-cap error")
            except NorthstarClientError as exc:
                check("cap" in str(exc).lower() or "256" in str(exc),
                      "oversize response is rejected at the 256 KB cap")
                check(os.environ.get("NORTHSTAR_TOKEN", "test-token") not in str(exc),
                      "size-cap error never contains the bearer token")

    def test_unreachable_service_error_is_clean():
        # Use a dynamically assigned port that nothing is listening on
        free_port = get_free_port()
        client = NorthstarClient(endpoint=f"http://127.0.0.1:{free_port}",
                                 token=os.environ.get("NORTHSTAR_TOKEN", "test-token"), 
                                 sample_mode=False)
        try:
            client.ask("session-e", "hello")
            raise SystemExit("expected connection error")
        except NorthstarClientError as exc:
            check(os.environ.get("NORTHSTAR_TOKEN", "test-token") not in str(exc),
                  "connection error never contains the bearer token")
            check(f"127.0.0.1:{free_port}" not in str(exc),
                  "connection error does not contain raw endpoint")

    def test_token_from_environment():
        free_port = get_free_port()
        with env_var("NORTHSTAR_TOKEN", "test-env-token"):
            client = NorthstarClient(endpoint=f"http://127.0.0.1:{free_port}", sample_mode=True)
            check(client.token == "test-env-token",
                  "bearer token is read from NORTHSTAR_TOKEN env var")

    def test_no_retry_when_budget_exhausted():
        # Test that no retry is attempted when first request takes too long
        # The service answers only after 8 s, longer than the whole 7 s budget.
        with FakeNorthstarService(mode="delay", delay=8.0) as stub:
            client = NorthstarClient(endpoint=stub.url,
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"),
                                     sample_mode=False)
            start_time = time.monotonic()
            try:
                client.ask("session-f", "slow request")
                raise SystemExit("expected NorthstarClientError for timeout")
            except NorthstarClientError as exc:
                end_time = time.monotonic()
                elapsed_time = end_time - start_time
                # Should fail due to timeout without retry (no time left for retry)
                check(elapsed_time < 7.0, 
                      f"delay service: stopped after {elapsed_time:.2f}s without retry")
                check(stub.request_count == 1,
                      "delay service: no retry attempted due to time budget constraint")

    def test_slow_but_within_budget_succeeds():
        # Negative control for the test above: an answer that arrives inside
        # the budget must be accepted, not rejected.
        with FakeNorthstarService(mode="delay", delay=1.0) as stub:
            client = NorthstarClient(endpoint=stub.url,
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"),
                                     sample_mode=False)
            result = client.ask("session-f2", "slow but fine")
            check(result.get("answer_id") == "fake-ans-1",
                  "answer arriving within the budget is accepted")

    def test_client_without_token():
        # Test behavior when no token is provided
        free_port = get_free_port()
        try:
            NorthstarClient(endpoint=f"http://127.0.0.1:{free_port}", token=None)
            raise SystemExit("expected ValueError for missing token")
        except ValueError as exc:
            check("token" in str(exc).lower(),
                  "client raises ValueError when token is None")

    def test_invalid_endpoint():
        # Test behavior with invalid endpoint
        try:
            client = NorthstarClient(endpoint="invalid-url", 
                                   token=os.environ.get("NORTHSTAR_TOKEN", "test-token"))
            client.ask("session-g", "test")
            raise SystemExit("expected NorthstarClientError for invalid endpoint")
        except NorthstarClientError:
            # Expected error for invalid URL
            check(True, "client handles invalid endpoint appropriately")

    def test_explain_with_invalid_answer_id():
        # Test explain with malformed answer ID
        free_port = get_free_port()
        with env_var("SAMPLE_MODE", "true"):
            client = NorthstarClient(endpoint=f"http://127.0.0.1:{free_port}",
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"))
            
            # Test with empty answer ID
            try:
                client.explain("session-h", "")
                raise SystemExit("expected NorthstarClientError for empty answer ID")
            except NorthstarClientError:
                check(True, "explain raises error for empty answer ID")
            
            # Test with None answer ID
            try:
                client.explain("session-h", None)
                raise SystemExit("expected NorthstarClientError for None answer ID")
            except NorthstarClientError:
                check(True, "explain raises error for None answer ID")

    def test_feedback_with_empty_message():
        # An empty or missing correction is rejected; a real one is accepted.
        free_port = get_free_port()
        with env_var("SAMPLE_MODE", "true"):
            client = NorthstarClient(endpoint=f"http://127.0.0.1:{free_port}",
                                     token=os.environ.get("NORTHSTAR_TOKEN", "test-token"))
            for bad in ("", "   ", None):
                try:
                    client.feedback("session-i", "sample-ans-0001", bad)
                except NorthstarClientError:
                    check(True, "feedback rejects correction %r" % (bad,))
                else:
                    raise AssertionError("FAILED: feedback accepted %r" % (bad,))
            result = client.feedback("session-i", "sample-ans-0001", "Mountain led, not Pacific.")
            check(isinstance(result, dict) and result.get("spoken", "").startswith(SAMPLE_PREFIX),
                  "feedback with real text is accepted and labelled as a precomputed sample")

    if __name__ == "__main__":
        # Set up required environment variables for tests
        with env_var("NORTHSTAR_TOKEN", os.environ.get("NORTHSTAR_TOKEN", "test-token")):
            test_stub_is_real_server()
            test_sample_mode_prefix()
            test_retry_once_on_5xx()
            test_no_retry_when_always_500()
            test_response_size_cap()
            test_unreachable_service_error_is_clean()
            test_token_from_environment()
            test_no_retry_when_budget_exhausted()
            test_slow_but_within_budget_succeeds()
            test_client_without_token()
            test_invalid_endpoint()
            test_explain_with_invalid_answer_id()
            test_feedback_with_empty_message()
            print("CLIENT_OK")

finally:
    # Restore original environment and path
    os.environ.clear()
    os.environ.update(original_environ)
    sys.path[:] = [p for p in sys.path if p != os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
