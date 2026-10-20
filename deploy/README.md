# Deploying Northstar Ask (SAM)

This stack hosts only the end-product surface (the MCP server). Answers come
from the hosted 3Dogs Nexus service; nothing about how answers are produced
lives in this repository.

## Prerequisites

- AWS CLI and the AWS SAM CLI, configured for your account.
- Python 3.12 (matches the Lambda runtime).

## Run locally first

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Precomputed samples, no credentials:
SAMPLE_MODE=true uvicorn mcp_server.server:asgi_app --host 127.0.0.1 --port 8080
# MCP endpoint: http://127.0.0.1:8080/mcp

# Live service:
export NORTHSTAR_ENDPOINT="https://<hosted-service>" NORTHSTAR_TOKEN="<token>"
uvicorn mcp_server.server:asgi_app --host 127.0.0.1 --port 8080
```

Locally the server is stateful: the `Mcp-Session-Id` the client receives at
initialize is the conversation id.

## Deploy with SAM

From the `deploy/` folder:

```bash
sam build --template-file template.yaml
sam deploy --guided
```

Guided prompts:

- `SampleMode`: `true` (default) serves precomputed sample responses and needs no
  endpoint or token. Use `false` for live answers.
- `NorthstarEndpoint`: required when `SampleMode` is `false`.
- `NorthstarToken`: the bearer token (stored `NoEcho`).

The output `McpEndpointUrl` is the Streamable HTTP endpoint.

## Notes

- `CodeUri: ../` makes the repository root the package, so `sam build` reads
  `requirements.txt` there.
- The function runs with `MCP_STATELESS=true` and `MCP_ALLOW_ANY_HOST=true`.
  The Lambda handler mints an `Mcp-Session-Id` at `initialize` and echoes it on later calls, so
  follow-up turns work over plain MCP; `X-Northstar-Session` is an optional override. See `docs/AWS.md`.
- The Function URL uses `AuthType: NONE` so judges can reach it. Switch to
  `AWS_IAM` or put the URL behind your own gateway for anything beyond a demo.
- The Lambda timeout is 30 seconds; the client's own budget per service call
  is 7 seconds.
- Verified 19 Oct 2026 with SAM CLI 1.169.0: `sam validate --lint` passes, `sam build` succeeds,
  and the stack deploys (stack `northstar-dev`, us-east-1, `SampleMode=true`).
