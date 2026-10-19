# Friction Log: Northstar Ask

Format per the hackathon rules: task attempted, steps taken, expected vs.
actual result, severity, workaround used, actionable suggestion. Every entry
below happened during this build and was reproduced by a test or a run.

## Entry 1: Session id inside an MCP tool

- **Task:** Make "And last quarter?", "explain that" and "correct me" refer
  to the previous answer in the same conversation.
- **Steps:** Built the server with `stateless_http=True`, read the session id
  from the tool's `Context`, and called `ask_northstar` twice and then
  `explain_last_answer` through the SDK's own client.
- **Expected:** One session id across the three calls.
- **Actual:** A new id every call. The service saw two unrelated sessions and
  `explain_last_answer` answered "no previous answer". Every earlier test
  passed, because they exercised the simulator bridge, not the MCP transport.
- **Severity:** High (multi-turn is the point of the entry).
- **Workaround:** Run stateful by default and read the `Mcp-Session-Id`
  request header inside the tool (an `X-Northstar-Session` header is the
  fallback for stateless hosting). `tests/test_mcp_session.py` now drives the
  real transport and fails if the ids differ.
- **Suggestion:** Expose the session id on the tool `Context` in both modes
  and document the pattern for per-conversation state.

## Entry 2: Streamable HTTP app on Lambda, first attempt

- **Task:** Serve the MCP app from a Lambda function URL handler.
- **Steps:** Wrote an adapter that turns a proxy event into an ASGI scope and
  calls the app once per invocation; sent `initialize` to it locally.
- **Expected:** An `initialize` result.
- **Actual:** `RuntimeError: Task group is not initialized. Make sure to use
  run().` The app's session manager only works after lifespan startup, which a
  per-request call never performs.
- **Severity:** High (the hosted endpoint could not have worked).
- **Workaround:** The handler keeps one event loop per warm container, sends
  the ASGI lifespan startup once, then runs every request on that loop.
  `tests/test_lambda.py` covers it.
- **Suggestion:** Ship a first-party Lambda adapter, or document the lifespan
  requirement next to the ASGI app helper.

## Entry 3: Function URL host name rejected

- **Task:** Call the Lambda handler with a Function-URL-style `Host` header.
- **Steps:** Sent `tools/list` with host `abc.lambda-url.us-east-1.on.aws`.
- **Expected:** The tool list.
- **Actual:** HTTP 421, `Invalid Host header`. The SDK's DNS-rebinding
  protection allows only localhost names by default.
- **Severity:** Medium (silent until the first real request).
- **Workaround:** `MCP_ALLOW_ANY_HOST=true` turns the check off for the
  Lambda deployment only; it stays on for local runs.
- **Suggestion:** Document the setting in the deployment section, with the
  Lambda case as the example.

## Entry 4: SAM package root versus handler path

- **Task:** Package the server for Lambda with the SAM template.
- **Steps:** Read the first draft: `CodeUri: ../mcp_server` with
  `Handler: mcp_server/server.lambda_handler`.
- **Expected:** A package where the handler and its imports resolve.
- **Actual:** The package root held only `mcp_server/`, so the handler path
  pointed one level too deep and `client/` and `samples/` were missing, which
  the server imports at start-up.
- **Severity:** High (would fail on first invoke).
- **Workaround:** `CodeUri: ../` and `Handler: mcp_server.server.lambda_handler`,
  so `requirements.txt` at the repo root is also what `sam build` installs.
  Not yet verified with `sam build`; the layout is covered by a local test.
- **Suggestion:** `sam validate` could warn when a handler module is not
  under `CodeUri`.

## Entry 5: A test server that failed to bind its own port

- **Task:** Start the MCP server under uvicorn inside a test.
- **Steps:** Probed for a free port with a socket, closed nothing, and gave the
  port number to uvicorn.
- **Expected:** The server starts on that port.
- **Actual:** Address-in-use errors and start-up timeouts: the probe socket
  was still bound.
- **Severity:** Low (test infrastructure only).
- **Workaround:** Pass the already-bound socket to `Server.run(sockets=[...])`.
- **Suggestion:** The uvicorn docs could show that pattern for tests.

## Entry 6: The client discarded every response body

- **Task:** Call a local stub service with the thin client.
- **Steps:** Ran the client against the stub and printed the parsed answer.
- **Expected:** The stub's JSON.
- **Actual:** "Answering service returned malformed JSON" on every 200. The
  size-capped read loop counted the bytes but never kept the chunks.
- **Severity:** High (live mode could never have worked).
- **Workaround:** Keep the chunks. A test that removes the line now fails.
- **Suggestion:** Test the transport against a real local server, not only
  injected openers.

## Entry 7: Browser voice input availability

- **Task:** Push-to-talk in the simulated experience.
- **Steps:** Feature-detect `SpeechRecognition` in the page script.
- **Expected:** Voice input in every browser.
- **Actual:** Support varies; where it is missing the mic button cannot work.
- **Severity:** Low.
- **Workaround:** The mic button is disabled with a visible hint, and typed
  input is a first-class path.
- **Suggestion:** Judge-facing instructions should name a browser for voice
  and rehearse the typed path.
