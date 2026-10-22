# Northstar Ask: Devpost Submission Write-Up

**Primary track:** Alexa+
**Mini challenge:** AWS Builder

## Inspiration

3Dogs Nexus consults on advanced AI, and the question we hear most from
operators is simple: "Can I just ask my numbers out loud and trust the
answer?" Northstar Ask is our answer: a voice-first business analyst for the
fictional Northstar Outdoor Co. retail dataset, built as a self-hosted MCP
server with a simulated Alexa+ experience so judges can try it in a browser
with no device.

All demo data is fictional; no real customer data is used anywhere.

## What it does

- **Multi-turn voice Q&A.** Ask a question, then follow up with "And last
  quarter?" or "Break that down by sales channel." Follow-ups travel on the
  conversation's session id, which the MCP client gets at initialize, so
  context carries across turns.
- **Echo Show-style cards.** Every answer returns spoken text plus a
  structured card (title, columns, rows, chart hint, sources, confidence),
  drawn in the simulator the way a screen device would show it.
- **Weekly business brief.** One request returns a spoken summary with
  several cards. The MCP prompt `weekly-business-brief` drives it.
- **"Correct me" turn.** The `correct_last_answer` tool sends a correction
  about the previous answer to the service. A later answer may come back
  marked "Improved from your feedback".
- **Honest low-confidence answers.** When the dataset cannot support a
  question, the answer says so instead of bluffing.

In live mode, answers are produced by 3Dogs Nexus, powered by our proprietary
Discovery model and proprietary Evolution module. The sample mode available to
judges returns precomputed answers and makes no model calls.

## What you can run today, and what you can't

- Everything above runs offline in `SAMPLE_MODE`, which replays a small set
  of precomputed responses, each spoken reply prefixed "Sample answer:". The
  samples are illustrative: sample mode does not learn, and the
  "improved" reply is itself a precomputed sample.
- Live answers need the hosted service. The repository's tests exercise the
  live path against a hand-written local stub of that service, not against the
  service itself. `eval/` holds a five-question before/after-correction pack;
  its offline run proves the path works end to end, not answer quality.

## How we built it

- A self-hosted **MCP server** (`mcp_server/server.py`) on the official MCP
  Python SDK, negotiating MCP spec version 2025-11-25 over Streamable HTTP at
  `/mcp`. The SDK is imported and serves the tools at runtime; a test drives
  it with the SDK's own client.
- Four tools (`ask_northstar`, `weekly_brief`, `explain_last_answer`,
  `correct_last_answer`) and the `weekly-business-brief` prompt.
- A **thin HTTPS client** (`client/northstar_client.py`) with a 7 second total
  budget per call, at most one retry on a 5xx and only when 2 seconds remain,
  a 256 KB response cap, and a bearer token read only from the environment.
- A **simulated Alexa+ web experience** (`web_sim/`): push-to-talk through the
  Web Speech API with a typed fallback, spoken replies and card rendering. No
  external libraries or CDNs.
- A **SAM template** (`deploy/template.yaml`) for AWS Lambda behind a Function
  URL, with `SAMPLE_MODE=true` as the default so a judge endpoint needs no
  private credentials. `lambda_handler` is tested against Function-URL-shaped
  events, and the template is deployed as stack `northstar-dev` in us-east-1, in sample mode.
- A deterministic fictional data generator (`northstar/gen_data.py`) that
  gives the demo dataset and the ground truth for the evaluation pack.

## AWS services used (AWS Builder mini challenge)

See `docs/AWS.md`. In short: AWS Lambda with a Function URL, defined in AWS
SAM, hosts the MCP server; in live mode the hosted service makes its language-model calls
on Amazon's managed model hosting in the 3Dogs AWS account.

## Challenges

- **Session continuity over a stateless-looking protocol.** Our first version
  created the MCP app in stateless mode and so minted a new session id on every
  call; follow-ups, explain and correct all landed as new conversations. A test
  against the real MCP transport now guards it.
- **Lambda and Streamable HTTP.** The SDK's app needs its lifespan started
  before it can serve a request, which a bare per-request adapter skips, and its
  host-header check rejects Function URL host names unless told otherwise.
- **Voice latency.** A remote service doing the analysis forced a hard 7 second
  budget with a single budget-aware retry.

See `docs/FRICTION_LOG.md` for the detail.

## What's next

The template is deployed as stack `northstar-dev` in sample mode. Next:
point it at the hosted 3Dogs Nexus service, run the blind evaluation pack
against live answers, and re-record the sample responses from live runs.

---

## Product Feedback (required)

### MCP Python SDK (negotiated spec 2025-11-25, Streamable HTTP)

- **Used for:** the whole product surface: tools, the prompt and the
  Streamable HTTP transport at `/mcp`.
- **What worked well:** FastMCP made tool and prompt registration quick, and
  the Streamable HTTP app runs under uvicorn as is. The client side made a
  real end-to-end test easy.
- **What needs work:** per-conversation state is not obvious. A tool gets no
  session id in stateless mode, and in stateful mode you read it from the
  request headers. Running the ASGI app on Lambda needs a hand-written adapter
  that also starts the app's lifespan, and the DNS-rebinding host check
  returns "421 Invalid Host header" for Function URL host names until you turn
  it off. A first-party Lambda adapter would remove that work.
- **Onboarding:** a working local tool quickly; session handling and Lambda
  took far longer than the tools themselves.
- **Build again?** Yes. The tool and prompt model fits a voice analyst.

### AWS SAM and Lambda Function URLs

- **Used for:** the deployment template for a public judge endpoint.
- **What worked well:** a Function URL is a simple HTTPS front for one
  function, and `NoEcho` parameters keep the service token out of console
  output.
- **What needs work:** Streamable HTTP over a buffered Lambda response gives up
  server-initiated streaming, so the template runs the server in stateless
  JSON-response mode. `CodeUri` and `Handler` must agree on where the package
  root is; ours disagreed in the first draft.
- **Onboarding:** we wrote the SAM template and deployed it as the
  CloudFormation stack `northstar-dev` in us-east-1, in sample mode.
- **Build again?** Yes.

### Web Speech API (browser simulator)

- **Used for:** push-to-talk input and spoken replies in the simulator.
- **What worked well:** it needs no dependencies.
- **What needs work:** support is uneven across browsers, so a typed fallback
  is mandatory.
- **Onboarding:** minutes.
- **Build again?** Yes, with the typed path kept as a first-class option.
