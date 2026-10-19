# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-c56c1185
# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-97be2443
"""Northstar Ask — self-hosted MCP server (spec 2025-11-25, Streamable HTTP).

This is the end-product surface of the demo. It exposes a thin wrapper over
the private 3Dogs Nexus answering service reached at NORTHSTAR_ENDPOINT.
No answering logic lives here: answers are produced by 3Dogs Nexus.

Tools:
  * ask_northstar(question)      — ask over the fictional Northstar dataset
  * weekly_brief()               — autonomous multi-step weekly brief
  * explain_last_answer()        — business meaning of the previous answer
  * correct_last_answer(correction) — "correct me" feedback turn

Prompts:
  * weekly-business-brief        — guided text for the brief workflow

Service contract note (#134): /v1/brief returns a `cards` array (possibly
empty). Single-card answers from /v1/ask and /v1/explain use the singular
`card` field. weekly_brief reads `cards` first and only falls back to the
singular `card` (plus any `sub_cards` it carries) when `cards` is absent or
empty, so exactly one source is rendered and nothing double-renders.

Run locally:  uvicorn mcp_server.server:asgi_app --port 8080
Lambda:       Handler is mcp_server/server.lambda_handler (see deploy/).
"""
import json
import logging
import os
import sys
import uuid
import time
from collections import OrderedDict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP, Context  # noqa: E402

try:  # TransportSecuritySettings is absent from older `mcp` releases
    from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
except ImportError:  # pragma: no cover - depends on the installed mcp version
    TransportSecuritySettings = None

from client.northstar_client import NorthstarClient  # noqa: E402

_log = logging.getLogger("northstar.mcp")

# Fixed user-facing messages for failed service calls. Exception details are
# logged server-side only: they can contain file paths or configuration
# hints (for example the samples file path or the NORTHSTAR_TOKEN hint) that
# must never be spoken to users.
_ERR_ASK = "Sorry, I couldn't get an answer right now. Please try again."
_ERR_BRIEF = "Sorry, I couldn't generate the brief right now. Please try again."
_ERR_EXPLAIN = "Sorry, I couldn't explain the answer right now. Please try again."
_ERR_FEEDBACK = "Sorry, I couldn't send your feedback right now. Please try again."

# Local runs are stateful Streamable HTTP: the client keeps the Mcp-Session-Id
# header issued at initialize, and that id is the conversation session.
# The Lambda deployment sets MCP_STATELESS=true (the SDK keeps no server-side
# MCP session there; instead lambda_handler mints an Mcp-Session-Id at
# initialize and echoes it on later calls, so a standard MCP client keeps
# its follow-up turns together; an explicit X-Northstar-Session header is
# still accepted) and MCP_ALLOW_ANY_HOST=true (the Function URL host name
# is not localhost).
_STATELESS = os.environ.get("MCP_STATELESS", "").lower() == "true"
_ANY_HOST = os.environ.get("MCP_ALLOW_ANY_HOST", "").lower() == "true"
# Older `mcp` releases have neither TransportSecuritySettings nor the
# DNS-rebinding check it disables, so the kwarg is only passed when the
# class is available; otherwise there is no host check to relax.
_SECURITY = None
if _ANY_HOST and TransportSecuritySettings is not None:
    _SECURITY = TransportSecuritySettings(enable_dns_rebinding_protection=False)
_MCP_KWARGS = {}
if _SECURITY is not None:
    _MCP_KWARGS["transport_security"] = _SECURITY
mcp = FastMCP("northstar-ask", stateless_http=_STATELESS, json_response=True,
              **_MCP_KWARGS)

# In-memory per-session bookkeeping so follow-up turns ("and last quarter?",
# "explain that", "correct me") resolve through the same session_id.
# Limited to 1000 sessions to prevent unbounded memory growth in demo.
# On Lambda this dict lives in the warm container: it survives between
# invocations that land on the same container, but a cold start (or a
# second concurrent container) starts with an empty dict, so a follow-up
# may honestly report "no previous answer" after a long idle period.
_SESSIONS = OrderedDict()
_MAX_SESSIONS = 1000
_SESSION_TTL = 3600  # 1 hour TTL for sessions

# Header name used by the MCP Streamable HTTP transport for session ids.
_SESSION_HEADER = "Mcp-Session-Id"


def _client():
    return NorthstarClient()


def _session_id(ctx=None):
    """Conversation id for this call.

    Uses the Mcp-Session-Id header the client received at initialize (or an
    explicit X-Northstar-Session header, for stateless hosting). Without
    either, the call is its own one-off conversation.
    """
    try:
        request = ctx.request_context.request if ctx else None
        headers = getattr(request, "headers", None)
        if headers is not None:
            for name in ("mcp-session-id", "x-northstar-session"):
                value = headers.get(name)
                if value:
                    return str(value)[:128]
    except Exception:
        pass
    return "mcp-" + uuid.uuid4().hex[:12]


def _cleanup_expired_sessions():
    """Remove sessions that have expired."""
    current_time = time.time()
    expired_sessions = [
        sid for sid, data in _SESSIONS.items()
        if current_time - data.get("last_access", 0) > _SESSION_TTL
    ]
    for sid in expired_sessions:
        _SESSIONS.pop(sid, None)


def _state(session_id):
    # Clean up expired sessions first
    _cleanup_expired_sessions()

    # Evict oldest session if we've hit the limit
    if len(_SESSIONS) >= _MAX_SESSIONS and session_id not in _SESSIONS:
        _SESSIONS.popitem(last=False)

    current_time = time.time()
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = {
            "last_answer_id": None,
            "turns": 0,
            "last_access": current_time
        }
    else:
        # Update last access time
        _SESSIONS[session_id]["last_access"] = current_time

    # Move to end to mark as recently used
    _SESSIONS.move_to_end(session_id)
    return _SESSIONS[session_id]


def _card_text(card):
    """Render a service card as plain text for voice-first clients."""
    # Validate card structure
    if not card or not isinstance(card, dict):
        return ""

    lines = []

    # Safely get title
    title = card.get("title")
    if title is not None:
        lines.append(str(title))
    else:
        lines.append("Result")

    # Safely handle columns
    columns = card.get("columns")
    if isinstance(columns, list):
        formatted_columns = []
        for c in columns:
            try:
                formatted_columns.append(str(c) if c is not None else "")
            except Exception:
                formatted_columns.append("")
        if formatted_columns:
            lines.append(" | ".join(formatted_columns))

    # Safely handle rows with type checking
    rows = card.get("rows")
    if isinstance(rows, list):
        row_count = len(rows)
        displayed_rows = rows[:10]
        for row in displayed_rows:
            if isinstance(row, list):
                formatted_row = []
                for c in row:
                    try:
                        formatted_row.append(str(c) if c is not None else "")
                    except Exception:
                        formatted_row.append("")
                lines.append(" | ".join(formatted_row))

        # Add truncation indicator if needed
        if row_count > 10:
            lines.append(f"... {row_count - 10} more rows")

    # Safely handle confidence
    confidence = card.get("confidence")
    if confidence is not None:
        lines.append("Confidence: " + str(confidence))

    return "\n".join(lines)


@mcp.tool()
def ask_northstar(question: str, ctx: Context = None) -> dict[str, Any]:
    """Ask a natural-language question over the fictional Northstar
    Outdoor Co. dataset. Returns spoken text plus a structured card."""
    session_id = _session_id(ctx)
    state = _state(session_id)

    try:
        payload = _client().ask(session_id, question)
    except Exception:
        _log.exception("ask_northstar failed (session %s)", session_id)
        return {
            "session_id": session_id,
            "spoken": _ERR_ASK,
            "card": None,
            "answer_id": None,
            "text": "Error: " + _ERR_ASK,
            "status": "error"
        }

    state["last_answer_id"] = payload.get("answer_id")
    state["turns"] += 1
    return {
        "session_id": session_id,
        "spoken": payload.get("spoken", ""),
        "card": payload.get("card"),
        "answer_id": payload.get("answer_id"),
        "text": payload.get("spoken", "") + "\n\n"
                + _card_text(payload.get("card")),
        "status": "success"
    }


@mcp.tool()
def weekly_brief(ctx: Context = None) -> dict[str, Any]:
    """Autonomous weekly business brief: the service chains several
    analysis steps and returns a spoken summary with one or more cards.

    Contract (#134): /v1/brief returns a `cards` array (possibly empty).
    Only when `cards` is absent or empty does this tool fall back to the
    singular `card` field (plus any `sub_cards` it carries). Exactly one of
    the two sources is used, so a card can never be rendered twice."""
    session_id = _session_id(ctx)

    try:
        payload = _client().brief(session_id)
    except Exception:
        _log.exception("weekly_brief failed (session %s)", session_id)
        return {
            "session_id": session_id,
            "spoken": _ERR_BRIEF,
            "cards": [],
            "answer_id": None,
            "text": "Error: " + _ERR_BRIEF,
            "card": None,
            "status": "error"
        }

    # Brief contract: the `cards` array is authoritative when present and
    # non-empty. Otherwise fall back to the singular `card` (and its
    # `sub_cards`), never both, to avoid double-rendering (#134).
    cards = []
    if isinstance(payload.get("cards"), list):
        cards = [c for c in payload["cards"] if isinstance(c, dict)]
    if not cards and isinstance(payload.get("card"), dict):
        main_card = dict(payload["card"])
        sub_cards = main_card.pop("sub_cards", None)
        cards = [main_card]
        if isinstance(sub_cards, list):
            cards.extend(c for c in sub_cards if isinstance(c, dict))

    # Always update last_answer_id when present, regardless of cards
    if payload.get("answer_id"):
        state = _state(session_id)
        state["last_answer_id"] = payload["answer_id"]
        state["turns"] += 1

    card_texts = [_card_text(c) for c in cards]
    card_texts = [t for t in card_texts if t]
    text = payload.get("spoken", "")
    if card_texts:
        text = text + "\n\n" + "\n\n".join(card_texts)
    return {
        "session_id": session_id,
        "spoken": payload.get("spoken", ""),
        "cards": cards,
        "answer_id": payload.get("answer_id"),
        "text": text,
        "card": None,  # Briefs never expose a singular card (#134)
        "status": "success"
    }


@mcp.tool()
def explain_last_answer(ctx: Context = None) -> dict[str, Any]:
    """Explain, in business terms, what the previous answer means. Never
    explains how the answer was produced."""
    session_id = _session_id(ctx)
    state = _state(session_id)
    answer_id = state.get("last_answer_id")
    if not answer_id:
        return {
            "session_id": session_id,
            "spoken": "There is no previous answer in this session to explain.",
            "card": None,
            "text": "No previous answer in this session.",
            "status": "error"
        }

    try:
        payload = _client().explain(session_id, answer_id)
    except Exception:
        _log.exception("explain_last_answer failed (session %s)", session_id)
        return {
            "session_id": session_id,
            "spoken": _ERR_EXPLAIN,
            "card": None,
            "answer_id": answer_id,
            "text": "Error: " + _ERR_EXPLAIN,
            "status": "error"
        }

    return {
        "session_id": session_id,
        "spoken": payload.get("spoken", ""),
        "card": payload.get("card"),
        "answer_id": answer_id,
        "text": payload.get("spoken", "") + "\n\n"
                + _card_text(payload.get("card")),
        "status": "success"
    }


@mcp.tool()
def correct_last_answer(correction: str, ctx: Context = None) -> dict[str, Any]:
    """'Correct me' turn: send feedback about the previous answer to the
    service. Later answers may be marked 'Improved from your feedback'."""
    session_id = _session_id(ctx)
    state = _state(session_id)
    answer_id = state.get("last_answer_id")
    if not answer_id:
        return {
            "session_id": session_id,
            "spoken": "There is no previous answer in this session to correct.",
            "card": None,
            "text": "No previous answer in this session.",
            "status": "error"
        }

    try:
        payload = _client().feedback(session_id, answer_id, correction)
    except Exception:
        _log.exception("correct_last_answer failed (session %s)", session_id)
        return {
            "session_id": session_id,
            "spoken": _ERR_FEEDBACK,
            "status": "error",
            "text": "Error: " + _ERR_FEEDBACK,
            "card": None
        }

    # Update last_answer_id if provided in feedback response
    if payload.get("answer_id"):
        state["last_answer_id"] = payload["answer_id"]

    return {
        "session_id": session_id,
        "spoken": payload.get("spoken", ""),
        "status": payload.get("status", "sent"),
        "text": payload.get("spoken", ""),
        "card": None,  # Consistent with other tool responses
        "answer_id": payload.get("answer_id")
    }


@mcp.prompt("weekly-business-brief")
def weekly_business_brief_prompt() -> str:
    """Guided text a client can use to drive the weekly-brief workflow."""
    return (
        "Run the Northstar Ask weekly business brief: call the weekly_brief "
        "tool, summarise each returned card in one spoken sentence, and "
        "offer to explain any headline number in business terms."
    )


def build_asgi_app():
    """Streamable HTTP ASGI app serving the MCP endpoint at /mcp."""
    return mcp.streamable_http_app()


asgi_app = build_asgi_app()


_LAMBDA_RT = {"loop": None}


def _lambda_loop():
    """One event loop per warm container, with the ASGI lifespan started once.

    The MCP session manager only works between lifespan startup and
    shutdown, so each invocation reuses a loop where startup already ran.
    """
    import asyncio
    if _LAMBDA_RT["loop"] is not None:
        return _LAMBDA_RT["loop"]
    loop = asyncio.new_event_loop()

    async def boot():
        inbox = asyncio.Queue()
        up = asyncio.Event()
        outcome = {}

        async def receive():
            return await inbox.get()

        async def send(message):
            if message["type"].startswith("lifespan.startup"):
                outcome["type"] = message["type"]
                up.set()

        task = asyncio.ensure_future(
            asgi_app({"type": "lifespan", "asgi": {"version": "3.0"}},
                     receive, send))
        await inbox.put({"type": "lifespan.startup"})
        waiter = asyncio.ensure_future(up.wait())
        await asyncio.wait({task, waiter},
                           return_when=asyncio.FIRST_COMPLETED)
        if outcome.get("type") != "lifespan.startup.complete":
            raise RuntimeError("MCP application failed to start")
        return task

    loop.run_until_complete(boot())
    _LAMBDA_RT["loop"] = loop
    return loop


def _is_initialize(body):
    """True when the JSON-RPC body (single message or batch) is `initialize`."""
    if not body:
        return False
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError, UnicodeDecodeError):
        return False
    messages = parsed if isinstance(parsed, list) else [parsed]
    return any(isinstance(m, dict) and m.get("method") == "initialize"
               for m in messages)


# Demo-only: process memory in a warm Lambda container is not durable. See
# the "Warm-container limit" paragraph in the lambda_handler docstring.
def lambda_handler(event, context):
    """AWS Lambda entry point referenced by deploy/template.yaml.

    Adapts Function URL / API Gateway proxy events onto the same ASGI app
    that uvicorn serves locally, so Lambda exposes the same tools.

    Session handling on Lambda: the MCP app runs stateless there, so this
    adapter does what the stateful transport does locally for the client:
    it mints an `Mcp-Session-Id` on the `initialize` call, returns it in the
    response headers, and echoes whatever `Mcp-Session-Id` later calls carry.
    The tools read that same header (see _session_id), so "explain that" /
    "correct me" resolve the previous answer in _SESSIONS.

    Warm-container limit (demo-only): _SESSIONS is plain process memory in
    a warm Lambda container and is not durable. It persists only while the
    same Lambda container stays warm; a cold start or a second concurrent
    container has no memory of earlier turns, and the dict is capped at
    _MAX_SESSIONS entries with a 1 hour TTL. That is fine for a demo
    conversation; durable sessions would need an external store (or state
    keyed by a caller-supplied conversation id held outside the process).
    """
    import base64

    headers = {}
    if event.get("multiValueHeaders"):
        for key, values in event["multiValueHeaders"].items():
            if values:
                headers[key.lower()] = ", ".join(values)
    else:
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body)
    elif isinstance(body, str):
        body = body.encode("utf-8")

    path = event.get("rawPath", event.get("path", "/mcp"))
    method = event.get("requestContext", {}).get("http", {}).get(
        "method", event.get("httpMethod", "POST"))

    incoming_session = headers.get(_SESSION_HEADER.lower())
    if incoming_session:
        incoming_session = str(incoming_session)[:128]

    cors_expose = {"Access-Control-Expose-Headers": _SESSION_HEADER}

    # A standard client ends a session with DELETE + Mcp-Session-Id. The
    # stateless app cannot honour that, so the adapter drops the state.
    if method.upper() == "DELETE" and incoming_session:
        _SESSIONS.pop(incoming_session, None)
        return {"statusCode": 200, "headers": dict(cors_expose),
                "body": "", "isBase64Encoded": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": headers.get("x-forwarded-proto", "https"),
        "path": path,
        "raw_path": path.encode(),
        "query_string": (event.get("rawQueryString") or "").encode(),
        "headers": [(k.encode(), str(v).encode()) for k, v in headers.items()],
    }

    result = {"status": 200, "headers": [], "body": b""}
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
            result["headers"] = [(k.decode(), v.decode())
                                 for k, v in message.get("headers", [])]
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    _lambda_loop().run_until_complete(asgi_app(scope, receive, send))

    out_body = result["body"]
    try:
        final_body = out_body.decode("utf-8")
        encoded = False
    except UnicodeDecodeError:
        final_body = base64.b64encode(out_body).decode("ascii")
        encoded = True

    headers_dict = {}
    for key, value in result["headers"]:
        headers_dict[key] = (headers_dict[key] + ", " + value
                             if key in headers_dict else value)

    # Mint at initialize, echo afterwards. If the app itself issued a
    # session header (stateful local mode run through this adapter), it wins.
    lower_keys = {k.lower() for k in headers_dict}
    if _SESSION_HEADER.lower() not in lower_keys and result["status"] < 400:
        session_id = None
        if method.upper() == "POST" and _is_initialize(body) and not incoming_session:
            session_id = "lambda-" + uuid.uuid4().hex
            _state(session_id)  # register in the warm container
        elif incoming_session:
            session_id = incoming_session
        if session_id:
            headers_dict[_SESSION_HEADER] = session_id
    if "access-control-expose-headers" not in lower_keys:
        headers_dict.update(cors_expose)

    return {
        "statusCode": result["status"],
        "headers": headers_dict,
        "body": final_body,
        "isBase64Encoded": encoded,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(asgi_app, host="127.0.0.1",
                port=int(os.environ.get("PORT", "8080")))
