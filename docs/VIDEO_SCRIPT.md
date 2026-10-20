# Northstar Ask: Demo Video Script (target 2 min 50 s, under the 3-minute limit)

Record three browser-page captures:
- The local simulator (`SAMPLE_MODE=true python web_sim/bridge.py` → http://127.0.0.1:8765/), seen in scenes 1 and 4-6.
- Live MCP calls to the hosted endpoint (https://rkko3li742dagcpa3f4os6zf640yuitu.lambda-url.us-east-1.on.aws/mcp), seen in scene 2.
- The public GitHub repo (github.com/DKJager/northstar-ask), seen in scenes 3 and 7.
Every spoken reply in sample mode is prefixed "Sample answer:". All data is fictional.
No third-party logos, music or trademarks beyond the track's required Alexa+/AWS names. Narrator is a TTS voice.

## Scene 1 — 0:00‑0:35 Simulator hook and multi-turn (70 words)

*(Screen: simulator page at 127.0.0.1:8765 — title bar "Northstar Ask — Simulated Alexa+ Experience", mode pill "Simulated Alexa+ experience", text input, Ask button.)*

VOICEOVER: "This is Northstar Ask, by 3Dogs Nexus — a self-hosted MCP server for the Alexa+ track. The web simulator shows precomputed sample answers over fictional outdoor-gear data."

*(Type exactly: "Which region sold the most tents this year?" and press Ask. A user bubble appears with the question; an assistant bubble appears: "Sample answer: The Pacific region leads tent sales this year with about 235 thousand dollars. Mountain is second at about 224 thousand dollars." A card titled "Tent Sales by Region — 2026 YTD" shows.)*

VOICEOVER: "The spoken reply and card match the precomputed sample for that question."

*(Type exactly: "And last quarter?" and press Ask. An assistant bubble appears: "Sample answer: In Q2 2026, Mountain led tent sales at about 107 thousand dollars, ahead of Pacific. For the year so far, Pacific still leads." A card titled "Tent Sales by Region — Q2 2026" shows.)*

*(Type exactly: "Break that down by sales channel." and press Ask. An assistant bubble appears: "Sample answer: In the Mountain region, wholesale made up 63 percent of Q2 2026 tent revenue, online made up 19 percent and retail made up 17 percent." A card titled "Mountain Tent Revenue by Channel — Q2 2026" shows.)*

VOICEOVER: "Three questions, one session — the simulator sends them through the same client interface the MCP tools use."

## Scene 2 — 0:35‑1:10 MCP server working live (70 words)

*(Screen: a browser tab showing live JSON-RPC calls to the hosted Lambda endpoint. First request and response visible: POST /mcp with `{"jsonrpc":"2.0","method":"initialize","id":1}`; response shows `protocolVersion: "2025-11-25"` and an `Mcp-Session-Id` header in the Response Headers section.)*

VOICEOVER: "The MCP server is live on AWS Lambda. An initialize call over Streamable HTTP returns protocol version 2025-11-25 and an Mcp-Session-Id header."

*(Scroll slightly to show the next request and response: a tools/list call with the same Mcp-Session-Id header, response listing the four tools: `ask_northstar`, `weekly_brief`, `explain_last_answer`, `correct_last_answer`.)*

VOICEOVER: "Tools list shows the four tools the server exposes. Every call carries the session id."

*(Scroll to show a tools/call for `ask_northstar` with question "Which region sold the most tents this year?". The JSON-RPC response contains `Sample answer: The Pacific region leads...` and a card payload.)*

## Scene 3 — 1:10‑1:35 Simulation source on screen (50 words)

*(Screen: GitHub repo at github.com/DKJager/northstar-ask, file `web_sim/bridge.py` open. Scroll to show the docstring lines 2-7: "Local HTTP bridge … calls the same client contract used by the MCP tools … SAMPLE_MODE is honoured … prefixes … 'Sample answer:'". Then open `web_sim/app.js`, showing lines 208-215: the `ask` function from `addBubble(question, "user");` down through `speak(body.spoken || "");`.)*

VOICEOVER: "This is the simulation source. The bridge calls the same Northstar client that the MCP tools use, with sample mode on, so every spoken reply starts with 'Sample answer:'. App dot js shows how the simulator posts questions and displays the spoken replies."

## Scene 4 — 1:35‑1:55 Weekly brief (40 words)

*(Screen: back to the simulator. Click the "Weekly brief" button. A user bubble appears: "Give me the weekly business brief." An assistant bubble appears: "Sample answer: Here's your weekly brief. Revenue is down 11 percent quarter over quarter, the Pacific region leads overall, and online is the biggest channel (it grew from Q1 2026)." A card titled "Weekly Brief" shows.)*

VOICEOVER: "The weekly brief is a one-click request — the sample reply summarizes revenue, regions and channels."

## Scene 5 — 1:55‑2:20 Correct-me flow (50 words)

*(Screen: simulator. Click the "Correct me" button. A browser prompt appears; type exactly: "Sleeping bags: Central led, not Pacific." Press OK. A user bubble appears: "That answer is wrong: Sleeping bags: Central led, not Pacific." An assistant bubble appears: "Sample answer: Noted (precomputed sample). Sample mode does not apply corrections to later answers.")*

VOICEOVER: "If an answer is wrong, I can correct it. In sample mode the correction is acknowledged, not learned."

*(Type exactly: "Which region sold the most sleeping bags last quarter?" and press Ask. An assistant bubble appears: "Sample answer: Improved from your feedback: the Central region led sleeping-bag sales last quarter at about 68 thousand dollars, ahead of the Pacific region." A card titled "Sleeping Bag Sales by Region — Q2 2026" shows.)*

VOICEOVER: "The next reply is a precomputed sample that says 'Improved from your feedback' and reports Central as the leader. Sample mode does not learn — it returns a matching fictional answer."

## Scene 6 — 2:20‑2:35 Low-confidence question (30 words)

*(Screen: simulator. Type exactly: "Are returns hurting our margins in the Central region?" and press Ask. An assistant bubble appears: "Sample answer: I'm not confident in this one. Return counts in the Central region are low but the demo dataset doesn't carry margin detail, so this is directional only." A card titled "Central Region Returns — Directional" shows.)*

VOICEOVER: "When the fictional dataset cannot fully support an answer, the reply is flagged low-confidence and directional."

## Scene 7 — 2:35‑2:50 Close (30 words)

*(Screen: GitHub README, scroll to show the Judge Access section with the Lambda endpoint URL and the Quickstart commands `SAMPLE_MODE=true python web_sim/bridge.py` and `SAMPLE_MODE=true uvicorn mcp_server.server:asgi_app`.)*

VOICEOVER: "The repository has the full source, setup instructions, tests, and the Lambda template. Northstar Ask, by 3Dogs Nexus — ask your numbers out loud."

*(End card: "Northstar Ask — 3Dogs Nexus", "Track: Alexa+", "Mini challenge: AWS Builder".)*

## Evidence for each voice-over claim

| Claim | File:line |
|---|---|
| "self-hosted MCP server" | `mcp_server/server.py:3` |
| "protocol version 2025-11-25" | `mcp_server/server.py:3` |
| "Mcp-Session-Id header" | `mcp_server/server.py:92` |
| "four tools: ask_northstar, weekly_brief, explain_last_answer, correct_last_answer" | `mcp_server/server.py:208,242,302,342` |
| "precomputed sample answers over fictional data" | `web_sim/bridge.py:5-7` |
| "'Sample answer:' prefix" | `web_sim/bridge.py:7` |
| "same Northstar client that the MCP tools use" | `mcp_server/server.py:45` and `web_sim/bridge.py:4-5` |
| "app.js shows how the simulator posts questions and displays the spoken replies" | `web_sim/app.js:208-215` |
| "Central region led sleeping-bag sales" | `samples/responses.json` (sha256 051efd009149fd89d4cbd7c28afa93c7cc6d49af891f58d4da3551f4973eaad1), built by `samples/build_samples.py` from `northstar/gen_data.py` and checked by `tests/test_samples_match_data.py`; recompute gate: two independent sums, 0 mismatches |
| "Sample mode does not learn" | `client/northstar_client.py:190-197` |
| "live on AWS Lambda" | `deploy/template.yaml:70-73` |
| "Lambda endpoint URL" | `README.md:26-27` |
| "Quickstart commands for simulator and MCP server" | `README.md:36-41` |
