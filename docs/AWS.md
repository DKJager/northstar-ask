# AWS Services Used: Northstar Ask (AWS Builder Mini Challenge)

This document lists the AWS services the project uses. It intentionally does
not name specific models or describe how answers are produced. Answers are
produced in live mode by 3Dogs Nexus, powered by our proprietary Discovery
model and proprietary Evolution module; sample mode makes no model calls.

## 1. AWS Lambda with a Function URL, defined in AWS SAM

The MCP server (`mcp_server/server.py`) deploys as one Lambda function behind
a Function URL, defined in `deploy/template.yaml`.

- `Handler: mcp_server.server.lambda_handler` adapts Function URL events onto
  the same ASGI app that uvicorn serves locally, so the deployed endpoint
  exposes the same four tools and the same prompt. `tests/test_lambda.py`
  feeds it Function-URL-shaped events and checks this.
- The package root (`CodeUri: ../`) holds `mcp_server/`, `client/`,
  `samples/` and `requirements.txt`.
- Configuration is by environment variables: `NORTHSTAR_ENDPOINT`,
  `NORTHSTAR_TOKEN` (a `NoEcho` parameter; the code never logs it),
  `SAMPLE_MODE`, and two switches for hosting, `MCP_STATELESS=true` and
  `MCP_ALLOW_ANY_HOST=true`.
- With `SAMPLE_MODE=true` (the template default) the endpoint serves
  precomputed responses bundled in `samples/responses.json`, each spoken reply
  prefixed "Sample answer:". A public demo URL then needs no private
  credentials.

Behavior to know about: Lambda mints an `Mcp-Session-Id` at initialize and
echoes it on later calls, so the deployed endpoint has an MCP session just as
the local run does (`tests/test_lambda.py` checks this). `X-Northstar-Session`
is an optional override: a client that sends it with a stable value uses that
value as the conversation id instead. A client that sends neither header makes
each call its own conversation, and the tools say honestly that there is no
previous answer. Session memory is held in the instance, so it does not
survive a cold start or a second container. Local `uvicorn` runs are stateful.

Status: the template and handler are tested locally. The stack has not been
deployed from our build environment.

## 2. Amazon managed model hosting (service side)

In live mode, the hosted 3Dogs Nexus service, outside this repository, makes its
language-model calls on Amazon's managed model hosting inside the 3Dogs AWS
account. This repository treats that service as an opaque HTTPS endpoint
(`NORTHSTAR_ENDPOINT`) and contains no model identifiers, request templates or
answering logic.

## 3. Amazon S3 (service side)

The hosted service uses Amazon S3 for data staging in the 3Dogs account. No code
in this repository calls S3; sample-mode responses ship inside the Lambda
package.

## Architecture summary

1. A Lambda function exposes the MCP endpoint at `<Function URL>/mcp`.
2. The thin client in `client/northstar_client.py` calls the hosted service
   (7 second budget, one budget-aware retry, 256 KB cap), or serves
   precomputed samples when `SAMPLE_MODE=true`.
3. Secrets arrive only as environment variables.
