# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-a7907372
# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-tests-mcplive
"""Live MCP test: starts the real server and connects over Streamable HTTP.

Verifies, per the spec:
  (i)   the server starts and an `mcp` client connects over Streamable HTTP;
  (ii)  exactly the 4 tools and 1 prompt are listed;
  (iii) ask_northstar returns text plus a card with title/columns/rows.

Runs in SAMPLE_MODE so no private service is needed. SAMPLE_MODE is set
only inside ``main()`` when this file is executed as a script
(``python tests/test_mcp_live.py``), never at import time, and the previous
value is restored when ``main()`` returns, so collecting this module under
pytest (or importing it from anywhere else) does not leak environment
changes into other test modules. This file defines no pytest-style test
functions and uses no pytest skip; it is meant to be run one per process,
as the README test loop does. Audit compliance
(#844): no mocking framework is used anywhere in this file — the server
is the real ASGI app served by uvicorn on an ephemeral port, and the
client is the real `mcp` SDK client.
Prints MCP_OK.
"""
import asyncio
import os
import sys
import threading
import time
import urllib.request
import urllib.error
import socket
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _free_port(max_retries=5):
    """Get a free port with retry mechanism to avoid race conditions."""
    for attempt in range(max_retries):
        try:
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            return port, sock
        except OSError:
            sock.close()
            if attempt == max_retries - 1:
                raise
            time.sleep(0.01)  # Brief pause before retry
    raise RuntimeError("Could not allocate free port after retries")


class ServerThreadWrapper:
    """Wrapper to capture exceptions from the server thread."""
    def __init__(self):
        self.exception = None
        self.thread = None
        self.server = None
        self.shutdown_complete = False

    def run_server(self, port, sock):
        try:
            import uvicorn
            from mcp_server.server import asgi_app

            # Root cause of the old "address already in use": the test kept
            # its probe socket bound AND let uvicorn bind the same port again
            # (uvicorn.Config has no `socket` attribute, so it was ignored).
            # Hand the already-bound socket to the server instead; uvicorn
            # then listens on it rather than binding a second time.
            config = uvicorn.Config(asgi_app, host="127.0.0.1", port=port,
                                    log_level="error")
            self.server = uvicorn.Server(config)
            self.thread = threading.Thread(
                target=self.server.run, kwargs={"sockets": [sock]},
                daemon=True)
            self.thread.start()
        except Exception as e:
            self.exception = e
            raise

    def wait_for_startup(self, port):
        """Wait until the HTTP port answers with a successful status using exponential backoff."""
        if self.exception:
            raise self.exception
            
        deadline = time.monotonic() + 20
        delay = 0.1
        while time.monotonic() < deadline:
            if self.exception:
                raise self.exception
                
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:%d/mcp" % port, 
                    method='GET'
                )
                resp = urllib.request.urlopen(req, timeout=1)
                # Only treat 2xx responses as successful
                if 200 <= resp.status < 300:
                    resp.close()
                    return
                else:
                    # For non-2xx responses, close and continue waiting
                    resp.close()
            except urllib.error.HTTPError as e:
                # Any HTTP answer (the MCP endpoint returns 4xx to a bare GET)
                # proves the server is up and listening.
                e.close()
                return
            except Exception:
                pass
            
            # Exponential backoff with max delay of 1 second
            time.sleep(delay)
            delay = min(delay * 1.5, 1.0)
        else:
            if self.exception:
                raise self.exception
            raise SystemExit("server did not start within 20 seconds")

    def shutdown(self, timeout=5):
        """Ask uvicorn to exit its main loop and wait for the thread."""
        if not self.server:
            return
        self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                raise RuntimeError(
                    "Server shutdown timed out after {} seconds".format(timeout))
        self.shutdown_complete = True


def _start_server(port, sock):
    wrapper = ServerThreadWrapper()
    wrapper.run_server(port, sock)
    wrapper.wait_for_startup(port)
    return wrapper


async def _exercise(port):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = "http://127.0.0.1:%d/mcp" % port
    
    # Add timeout to prevent hanging
    async with asyncio.timeout(30):
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Add timeout for tool listing
                async with asyncio.timeout(10):
                    tools = await session.list_tools()
                    tool_names = sorted(t.name for t in tools.tools)
                    expected = ["ask_northstar", "correct_last_answer",
                                "explain_last_answer", "weekly_brief"]
                    assert tool_names == expected, (
                        "tool list mismatch: %r" % tool_names)
                    print("  ok - exactly the 4 tools are listed: "
                          + ", ".join(tool_names))

                # Add timeout for prompt listing
                async with asyncio.timeout(10):
                    prompts = await session.list_prompts()
                    prompt_names = [p.name for p in prompts.prompts]
                    assert prompt_names == ["weekly-business-brief"], (
                        "prompt list mismatch: %r" % prompt_names)
                    print("  ok - exactly 1 prompt is listed: "
                          "weekly-business-brief")

                # Add timeout for tool call
                async with asyncio.timeout(15):
                    result = await session.call_tool(
                        "ask_northstar",
                        {"question": "How much revenue did Northstar make "
                                     "last quarter?"})
                    
                    # Use getattr to handle older MCP client versions
                    structured_content = getattr(result, "structuredContent", None)
                    assert structured_content, "ask returned no structured content"
                    content = structured_content
                    spoken = content.get("spoken", "")
                    assert spoken.startswith("Sample answer:"), (
                        "SAMPLE_MODE prefix missing: %r" % spoken[:60])
                    card = content.get("card")
                    assert card, "ask returned no card"
                    assert card.get("title"), "card has no title"
                    assert isinstance(card.get("columns"), list) and card["columns"], \
                        "card has no columns"
                    assert isinstance(card.get("rows"), list) and card["rows"], \
                        "card has no rows"
                    assert content.get("text"), "ask returned no text channel"
                    print("  ok - ask_northstar returned text plus a card with "
                          "title/columns/rows: %r" % card["title"])


def main():
    # Set SAMPLE_MODE here, not at import time, so that importing this
    # module (e.g. pytest collection) never changes the environment seen
    # by other test modules such as test_client's no-token check. The
    # previous value is restored on exit so even an in-process call of
    # main() leaves the environment as it found it.
    prior_sample_mode = os.environ.get("SAMPLE_MODE")
    os.environ["SAMPLE_MODE"] = "true"
    try:
        port, sock = _free_port()
        server_wrapper = _start_server(port, sock)
        try:
            asyncio.run(_exercise(port))
        finally:
            server_wrapper.shutdown(timeout=5)
    finally:
        if prior_sample_mode is None:
            os.environ.pop("SAMPLE_MODE", None)
        else:
            os.environ["SAMPLE_MODE"] = prior_sample_mode
    print("MCP_OK")


if __name__ == "__main__":
    main()
