# Northstar Ask

> **Demo scope.** The deployed Lambda keeps follow-up conversation state in process memory (a warm container), so it is demo-only: a cold start or a second container forgets earlier turns. Python dependency pin: `mcp>=1.23,<2`.


A voice business analyst you can talk to like a colleague, built for the
2026 Amazon Developer Hackathon (primary track: Alexa+; mini challenge:
AWS Builder).

Northstar Ask is a **self-hosted MCP server** (MCP spec version
2025-11-25 over Streamable HTTP) plus a **simulated Alexa+ web
experience**. It answers questions over the fictional Northstar Outdoor Co.
retail dataset. All demo data is fictional; no real customer data is used
anywhere.

In live mode, answers are produced by 3Dogs Nexus, powered by our proprietary
Discovery model and proprietary Evolution module. The sample mode
returns precomputed answers and makes no model calls. The answering service is hosted by
3Dogs Nexus and reached at `NORTHSTAR_ENDPOINT`; this repository contains
only the end-product surface: the MCP server, a thin HTTPS client, the
simulator, a fictional data generator, a deployment template, tests and docs.

## Judge Access

**Track:** primary track Alexa+; mini challenge AWS Builder.

**Hosted endpoint (nothing to install):** `https://rkko3li742dagcpa3f4os6zf640yuitu.lambda-url.us-east-1.on.aws/mcp` is the Streamable HTTP
MCP endpoint, deployed on AWS Lambda in sample mode (fictional data), available until
20 Nov 2026. Connect any MCP client (for example MCP Inspector), initialize, and call
`ask_northstar` with a question from "Try it" below.

No account or token is needed to run it yourself either: sample mode runs
entirely from this repository. After the install step in the Quickstart
below:

```bash
# Simulated Alexa+ experience in sample mode
SAMPLE_MODE=true python web_sim/bridge.py
#     then open http://127.0.0.1:8765/

# Or the MCP server itself (endpoint: http://127.0.0.1:8080/mcp)
SAMPLE_MODE=true uvicorn mcp_server.server:asgi_app --host 127.0.0.1 --port 8080
```

Type the questions listed under "Try it" exactly as written; every spoken
reply in sample mode is prefixed "Sample answer:".

## What it does

- **Multi-turn Q&A.** Follow-ups such as "And last quarter?" ride on the
  conversation's session id (the `Mcp-Session-Id` the client receives at
  initialize), so "explain that" and "correct me" refer to the right answer.
- **Echo Show-style cards.** Every answer is spoken text plus a structured
  card (title, columns, rows, chart hint, sources, confidence).
- **Weekly business brief.** One call asks the service for a spoken summary
  with several cards. The MCP prompt `weekly-business-brief` drives it.
- **"Correct me" turn.** `correct_last_answer` sends a correction about the
  previous answer to the service. A later answer may come back marked
  "Improved from your feedback".
- **Honest low-confidence answers.** When the data cannot support a
  question, the answer says so.

## Two ways to run it

| Mode | What you get | Needs |
|------|--------------|-------|
| `SAMPLE_MODE=true` | Answers precomputed from the fictional dataset by `samples/build_samples.py` and served from `samples/responses.json`; every spoken reply is prefixed "Sample answer:". Nothing is presented as live. | Nothing else |
| Live | Real answers from the hosted service | `NORTHSTAR_ENDPOINT` and `NORTHSTAR_TOKEN` from the 3Dogs team |

Sample mode replays a small fixed set of precomputed samples, matched to the question
by wording. Use the exact questions listed under "Try it" below. It does not
learn from corrections: the "improved" reply is itself a precomputed sample.

## Quickstart (about 5 minutes)

Requires Python 3.12 and git.

```bash
# 1. Create an environment and install
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 2. Run the tests (each prints its own OK token, takes under a minute in total
#    except test_client, which waits out a 7 second timeout on purpose)
for t in tests/test_*.py; do python "$t" || break; done

# 3a. Start the simulated Alexa+ experience in sample mode
SAMPLE_MODE=true python web_sim/bridge.py
#     then open http://127.0.0.1:8765/

# 3b. Or start the MCP server (endpoint: http://127.0.0.1:8080/mcp)
SAMPLE_MODE=true uvicorn mcp_server.server:asgi_app --host 127.0.0.1 --port 8080
```

For live answers drop `SAMPLE_MODE=true` and export `NORTHSTAR_ENDPOINT` and
`NORTHSTAR_TOKEN` first.

### Try it (sample mode, type these exactly)

1. "Which region sold the most tents this year?"
2. "And last quarter?"
3. "Break that down by sales channel."
4. Click **Weekly brief**.
5. Click **Correct me**, type a correction, then ask "Which region sold the
   most sleeping bags last quarter?" The precomputed sample reply is marked
   "Improved from your feedback".
6. "Are returns hurting our margins in the Central region?" shows the
   low-confidence case.

## Tools and prompt

| Name | Purpose |
|------|---------|
| `ask_northstar(question)` | Ask a question; returns spoken text plus a card |
| `weekly_brief()` | Multi-card weekly summary |
| `explain_last_answer()` | What the previous answer means in business terms |
| `correct_last_answer(correction)` | Tell the service the previous answer was wrong |
| prompt `weekly-business-brief` | Guided text that drives the brief |

## Configuration

| Variable | Meaning |
|----------|---------|
| `SAMPLE_MODE` | `true` serves precomputed samples and needs no token |
| `NORTHSTAR_ENDPOINT` | Base URL of the hosted answering service |
| `NORTHSTAR_TOKEN` | Bearer token for it; read from the environment only |
| `MCP_STATELESS` | `true` for Lambda: no server-side MCP session; clients send `X-Northstar-Session` to keep a conversation together |
| `MCP_ALLOW_ANY_HOST` | `true` for Lambda: accept the Function URL host name |
| `PORT`, `BRIDGE_PORT` | Listen ports for `python mcp_server/server.py` and the simulator bridge |

The client enforces a 7 second total budget per call, at most one retry on a
5xx and only if 2 seconds remain, and a 256 KB response cap.

## Deploying to AWS

`deploy/template.yaml` is an AWS SAM template (Lambda plus a Function URL).
See `deploy/README.md` for the full steps. It is deployed as the hosted endpoint above
(stack `northstar-dev`, us-east-1, `SampleMode=true`). To deploy your own copy, run it from the
`deploy/` directory, where the template lives, in your own account:

```bash
cd deploy
sam build && sam deploy --guided
```

## Repository layout

| Path | Purpose |
|------|---------|
| `mcp_server/server.py` | MCP server: 4 tools, 1 prompt, Streamable HTTP at `/mcp`, plus `lambda_handler` |
| `client/northstar_client.py` | Thin HTTPS client with the budget, retry, cap and token handling above |
| `web_sim/` | Simulated Alexa+ front end (push-to-talk with typed fallback, spoken replies, cards) and its local bridge |
| `northstar/gen_data.py`, `data/SCHEMA.md` | Deterministic fictional dataset and its schema |
| `samples/responses.json` | Precomputed samples for SAMPLE_MODE, built from the dataset by `samples/build_samples.py` |
| `eval/` | Five-question before/after-correction pack and runner; see `eval/README.md` |
| `deploy/` | SAM template and deployment guide |
| `docs/` | Write-up, AWS services, video script, friction log |
| `tests/` | Test scripts and a hand-written stub of the answering service |

## Tests

| Script | Prints | Covers |
|--------|--------|--------|
| `tests/test_client.py` | `CLIENT_OK` | sample prefix, 7 s budget, retry, 256 KB cap, token never in errors, input checks |
| `tests/test_mcp_live.py` | `MCP_OK` | real MCP client over Streamable HTTP: 4 tools, 1 prompt, a card |
| `tests/test_mcp_session.py` | `MCP_SESSION_OK` | one MCP session keeps one session id; explain and correct use the latest answer; sessions are isolated |
| `tests/test_lambda.py` | `LAMBDA_OK` | `lambda_handler` serves the same tools from Function-URL-shaped events |
| `tests/test_multiturn.py` | `MULTITURN_OK` | the simulator bridge keeps session state, and none on errors |
| `tests/test_sim.py` | `SIM_OK` | the simulator page and bridge API |
| `tests/test_eval.py` | `EVAL_TEST_OK` | the blind-pack runner, with a negative control |
| `tests/test_ip_scan.py` | `IPSCAN_OK` | scan of every shipped file for forbidden terms and secrets (needs the git checkout) |

## License

MIT. See `LICENSE`. This repository holds the Northstar Ask MCP server, the
simulator, the fictional demo data and the tests; the private answering service it
can call in live mode is not part of it.
