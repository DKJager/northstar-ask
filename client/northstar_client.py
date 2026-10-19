# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-0ff6ed60
"""Thin HTTPS client for the private 3Dogs Nexus Northstar service.

This module implements the documented private-service contract only:

  POST {NORTHSTAR_ENDPOINT}/v1/ask      {"session_id", "question"}
  POST {NORTHSTAR_ENDPOINT}/v1/brief    {"session_id"}
  POST {NORTHSTAR_ENDPOINT}/v1/explain  {"session_id", "answer_id"}
  POST {NORTHSTAR_ENDPOINT}/v1/feedback {"session_id", "answer_id", "correction"}

All answering happens in the private service. This repository never
implements, embeds, or names any answering logic; answers are produced by
3Dogs Nexus, powered by our proprietary Discovery model and proprietary
Evolution module.

Guarantees enforced here:
  * TOTAL time budget of 7 seconds per call, including at most one retry
    on HTTP 5xx, and the retry fires only if >= 2 seconds of budget remain.
  * Response body size capped at 256 KB.
  * Bearer token read from the NORTHSTAR_TOKEN environment variable and
    never logged or included in error messages.
  * SAMPLE_MODE=true returns recorded end-product responses from
    samples/responses.json with every spoken reply prefixed
    "Recorded sample:" so nothing recorded is presented as live.
"""
import json
import os
import time
import urllib.error
import urllib.request
import re
import socket
import zlib
from copy import deepcopy
from urllib.parse import urlparse

# Default values for budget constants
DEFAULT_TOTAL_BUDGET_SECONDS = 7.0
DEFAULT_RETRY_MIN_REMAINING_SECONDS = 2.0
TIMEOUT_MARGIN_SECONDS = 0.25
MAX_RESPONSE_BYTES = 256 * 1024
SAMPLE_PREFIX = "Recorded sample:"
MAX_SAMPLE_ITERATIONS = 100  # Limit iterations for performance

# Sample-mode explain: the recording used when no recording exists for the
# requested answer id. It explains the Q2 2026 revenue answer only.
_SAMPLE_EXPLAIN_FALLBACK_KEY = "explain_revenue_q2_2026"
_SAMPLE_EXPLAIN_FALLBACK_NOTE = (
    "Fixed explanation recording: sample mode has no explanation recorded "
    "for this answer id, so it replays the one recorded explanation "
    "(Q2 2026 revenue) regardless of which answer was asked about."
)

_DEFAULT_ENDPOINT = "https://localhost:8900"
_UNSET = object()  # distinguishes "token not passed" from an explicit None
_SAMPLES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples",
    "responses.json",
)


class NorthstarClientError(Exception):
    """Raised when the private service cannot be reached or answers badly."""
    
    def __init__(self, message, context=None):
        super().__init__(message)
        self.context = context or {}
    
    def __str__(self):
        """Return the error message for better readability in logs."""
        msg = self.args[0] if self.args else ""
        if self.context:
            # The raw endpoint URL is deliberately left out of the text.
            shown = {k: v for k, v in self.context.items() if k != "url"}
            if shown:
                context_str = ", ".join(f"{k}={v}" for k, v in shown.items())
                return f"{msg} ({context_str})"
        return msg


class NorthstarClient:
    """Stdlib-only HTTPS client for the private Northstar service."""

    def __init__(self, endpoint=None, token=_UNSET, sample_mode=None,
                 samples_path=None, opener=None, 
                 total_budget_seconds=DEFAULT_TOTAL_BUDGET_SECONDS,
                 retry_min_remaining_seconds=DEFAULT_RETRY_MIN_REMAINING_SECONDS):
        # Only strip trailing slash if it's redundant (not for root paths)
        endpoint_from_env = os.environ.get("NORTHSTAR_ENDPOINT")
        if endpoint is None and endpoint_from_env:
            self.endpoint = endpoint_from_env
        elif endpoint:
            self.endpoint = endpoint
        else:
            self.endpoint = _DEFAULT_ENDPOINT
            
        # Normalize endpoint - only strip trailing slash if not root path
        if self.endpoint.endswith("/") and len(self.endpoint) > 1:
            self.endpoint = self.endpoint.rstrip("/")
            
        self._validate_endpoint(self.endpoint)

        # Omitted token -> read NORTHSTAR_TOKEN; an explicit None means
        # "no token" and is never silently replaced from the environment.
        if token is _UNSET:
            token = os.environ.get("NORTHSTAR_TOKEN", "")
        self.token = token or ""
        if sample_mode is None:
            sample_mode = os.environ.get("SAMPLE_MODE", "").lower() == "true"
        self.sample_mode = sample_mode
        self.samples_path = samples_path or _SAMPLES_PATH
        # `opener` lets tests inject a transport without any mock framework.
        # Expected interface: callable that returns a context manager with
        # .read() method (like urllib.request.urlopen)
        self._opener = opener or urllib.request.urlopen
        self._validate_opener()
        self._samples_cache = None
        self._samples_cache_time = 0
        self._samples_cache_ttl = 60  # Cache for 1 minute
        
        # Budget configuration
        self.total_budget_seconds = total_budget_seconds
        self.retry_min_remaining_seconds = retry_min_remaining_seconds
        
        # A live client cannot work without a bearer token (SAMPLE_MODE
        # never calls the service, so it does not need one).
        if not self.sample_mode and not self.token:
            raise ValueError(
                "NORTHSTAR_TOKEN is required (set the environment variable "
                "or pass token=) unless SAMPLE_MODE=true")

    @staticmethod
    def _validate_endpoint(endpoint):
        """Require an absolute http(s) URL with a host."""
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise NorthstarClientError(
                "NORTHSTAR_ENDPOINT must be an absolute http(s) URL.")

    def _validate_opener(self):
        """Validate that the opener has the expected interface."""
        if not callable(self._opener):
            raise NorthstarClientError("Opener must be callable")
        # We can't fully validate the return type at runtime without calling it,
        # but we document the expected interface in comments

    # ------------------------------------------------------------------
    # Public contract methods
    # ------------------------------------------------------------------
    def ask(self, session_id, question):
        """Ask a natural-language question over the fictional dataset."""
        if self.sample_mode:
            return self._sample_lookup(question)
        return self._post("/v1/ask",
                          {"session_id": session_id, "question": question})

    def brief(self, session_id):
        """Run the autonomous weekly-brief workflow on the service side."""
        if self.sample_mode:
            return self._sample_by_key("weekly_brief")
        return self._post("/v1/brief", {"session_id": session_id})

    def explain(self, session_id, answer_id):
        """Explain what a previous answer means in business terms."""
        if not isinstance(answer_id, str) or not answer_id.strip():
            raise NorthstarClientError("An answer_id is required to explain an answer.")
        if self.sample_mode:
            # Prefer an explanation recorded for this specific answer id
            # (an item with kind "explain" and a matching "answer_id", or
            # keyed "explain_<answer_id>"). Only when none exists fall back
            # to the single fixed recording, and say so in the response.
            recorded = self._sample_explain_for_answer(answer_id.strip())
            if recorded is not None:
                return recorded
            fallback = self._sample_by_key(_SAMPLE_EXPLAIN_FALLBACK_KEY)
            fallback["note"] = _SAMPLE_EXPLAIN_FALLBACK_NOTE
            fallback["explains_answer_id"] = _SAMPLE_EXPLAIN_FALLBACK_KEY
            return fallback
        return self._post("/v1/explain",
                          {"session_id": session_id, "answer_id": answer_id})

    def feedback(self, session_id, answer_id, correction):
        """Send a 'correct me' correction for a previous answer."""
        if not isinstance(answer_id, str) or not answer_id.strip():
            raise NorthstarClientError("An answer_id is required to correct an answer.")
        if not isinstance(correction, str) or not correction.strip():
            raise NorthstarClientError("A correction text is required.")
        if self.sample_mode:
            # Sample mode does not learn from corrections, and these
            # templates must not suggest that it does.
            feedback_templates = [
                "Correction noted (recorded sample; no learning in sample mode).",
                "Noted. This is a recorded sample; sample mode does not learn from corrections.",
                "Your correction was noted (recorded sample; no learning in sample mode).",
                "Noted (recorded sample). Sample mode does not apply corrections to later answers."
            ]
            # Simple hash-based selection for deterministic but varied responses
            hash_val = zlib.crc32(
                f"{session_id}{answer_id}{correction}".encode("utf-8")
            ) % len(feedback_templates)
            return {
                "spoken": SAMPLE_PREFIX + " " + feedback_templates[hash_val],
                "status": "recorded",
                "learned": False,
            }
        return self._post("/v1/feedback", {
            "session_id": session_id,
            "answer_id": answer_id,
            "correction": correction,
        })

    # ------------------------------------------------------------------
    # Transport with budget, cap and single budget-aware retry
    # ------------------------------------------------------------------
    def _post(self, path, payload):
        url = self.endpoint + path
        body = json.dumps(payload).encode("utf-8")
        deadline = time.monotonic() + self.total_budget_seconds
        attempts = 0
        while True:
            attempts += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise NorthstarClientError(
                    "Time budget exhausted contacting the answering service.",
                    context={"url": url, "attempts": attempts})
            
            # Pre-flight check for retry budget
            if attempts > 1:
                if remaining < self.retry_min_remaining_seconds:
                    raise NorthstarClientError(
                        "Insufficient time remaining for retry.",
                        context={"url": url, "attempts": attempts, "remaining": remaining})
            
            request = urllib.request.Request(
                url, data=body, method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": "Bearer " + self.token,
                })
            try:
                start_time = time.monotonic()
                # Keep a small margin so the call returns inside the budget
                # even after local scheduling overhead.
                attempt_timeout = max(remaining - TIMEOUT_MARGIN_SECONDS, 0.05)
                with self._opener(request, timeout=attempt_timeout) as resp:
                    # Check content type before reading body
                    content_type = resp.headers.get('Content-Type', '')
                    if not content_type.startswith('application/json'):
                        raise NorthstarClientError(
                            f"Service returned non-JSON content: {content_type}",
                            context={"url": url, "content_type": content_type, "status": resp.status})
                    
                    # Stream response to prevent memory overallocation
                    raw_chunks = []
                    total_bytes = 0
                    while True:
                        chunk = resp.read(8192)  # Read in 8KB chunks
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > MAX_RESPONSE_BYTES:
                            raise NorthstarClientError(
                                "Service response exceeded the 256 KB size cap.",
                                context={"url": url, "bytes": total_bytes})
                        raw_chunks.append(chunk)
                    raw = b''.join(raw_chunks)
                
                # Check if we've exceeded our total budget after the call
                if time.monotonic() - start_time >= remaining:
                    raise NorthstarClientError(
                        "Time budget exceeded during response read.",
                        context={"url": url, "duration": time.monotonic() - start_time})
                
                # Parse and validate JSON response
                parsed = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise NorthstarClientError(
                        "Service returned invalid response format.",
                        context={"url": url, "type": type(parsed)})
                return parsed
            except urllib.error.HTTPError as exc:
                retryable = 500 <= exc.code < 600
                over_request_cap = exc.code == 413
                
                # Try to read response body for better error reporting
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8")
                except Exception:
                    pass  # If we can't read the body, continue with generic error
                
                if over_request_cap:
                    raise NorthstarClientError(
                        "Request body too large (HTTP 413).",
                        context={"url": url, "status": exc.code})
                
                # Restructured retry logic: check budget independently of attempts
                can_retry = (
                    retryable and 
                    attempts == 1 and 
                    (deadline - time.monotonic()) >= self.retry_min_remaining_seconds
                )
                
                if not can_retry:
                    error_msg = f"Answering service returned HTTP {exc.code}."
                    if error_body:
                        # Sanitize error body by truncating and avoiding auth header disclosure
                        sanitized_body = error_body[:500]  # Limit length
                        if self.token:
                            sanitized_body = sanitized_body.replace(
                                self.token, "[redacted]")
                        if sanitized_body:
                            error_msg += f" Response body: {sanitized_body}"
                    raise NorthstarClientError(error_msg, 
                                             context={"url": url, "status": exc.code, "attempts": attempts})
            except urllib.error.URLError as exc:
                # Never echo the endpoint or raw socket text to callers.
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    message = "The answering service did not respond in time."
                elif isinstance(exc.reason, ConnectionRefusedError):
                    message = ("Could not reach the answering service "
                               "(connection refused).")
                else:
                    message = "Could not reach the answering service."
                raise NorthstarClientError(message, context={"url": url}) from exc
            except (TimeoutError, socket.timeout) as exc:
                raise NorthstarClientError(
                    "The answering service did not respond in time.",
                    context={"url": url}) from exc
            except (ConnectionError, OSError) as exc:
                raise NorthstarClientError(
                    "Connection to the answering service was interrupted.",
                    context={"url": url}) from exc
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise NorthstarClientError(
                    "Answering service returned malformed JSON.",
                    context={"url": url, "error": str(exc)}) from exc

    # ------------------------------------------------------------------
    # SAMPLE_MODE helpers (recorded end-product responses)
    # ------------------------------------------------------------------
    def _load_samples(self):
        current_time = time.time()
        # Check if cache is still valid
        if (self._samples_cache is not None and 
            current_time - self._samples_cache_time < self._samples_cache_ttl):
            return self._samples_cache
            
        try:
            with open(self.samples_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            raise NorthstarClientError(
                f"Failed to load samples from {self.samples_path}: {e}",
                context={"path": self.samples_path, "error": str(e)})
        
        # Validate JSON structure
        if not isinstance(data, dict):
            raise NorthstarClientError(
                "Samples file must contain a JSON object",
                context={"path": self.samples_path, "type": type(data)})
        
        if "responses" not in data:
            raise NorthstarClientError(
                "Samples file missing 'responses' key",
                context={"path": self.samples_path})
        
        if not isinstance(data["responses"], list):
            raise NorthstarClientError(
                "'responses' in samples file must be a list",
                context={"path": self.samples_path, "type": type(data["responses"])})
        
        # Update cache
        self._samples_cache = data["responses"]
        self._samples_cache_time = current_time
        return self._samples_cache

    def _normalize_text(self, text):
        """Normalize text for better matching by removing punctuation and extra whitespace."""
        if not text:
            return ""
        # Remove punctuation and convert to lowercase
        normalized = re.sub(r'[^\w\s]', '', text.lower())
        # Replace multiple whitespace with single space and strip
        return re.sub(r'\s+', ' ', normalized).strip()

    def _prefix_spoken(self, payload):
        # Create a deep copy to avoid mutating the cached object
        result = deepcopy(payload)
        spoken = result.get("spoken", "")
        if spoken and not spoken.startswith(SAMPLE_PREFIX):
            # Normalize spacing to avoid double spaces
            result["spoken"] = SAMPLE_PREFIX + " " + spoken.lstrip()
        return result

    def _sample_explain_for_answer(self, answer_id):
        """Return the explanation recorded for `answer_id`, or None.

        A recording matches when it has kind "explain" and an "answer_id"
        equal to the requested one, or when its key is "explain_<answer_id>".
        """
        responses = self._load_samples()
        wanted_key = "explain_" + answer_id
        iteration_count = 0
        for item in responses:
            if iteration_count >= MAX_SAMPLE_ITERATIONS:
                break
            iteration_count += 1
            if not isinstance(item, dict):
                continue
            if item.get("kind") == "explain" and item.get("answer_id") == answer_id:
                result = self._prefix_spoken(item)
                result["explains_answer_id"] = answer_id
                return result
            if item.get("key") == wanted_key and wanted_key != _SAMPLE_EXPLAIN_FALLBACK_KEY:
                result = self._prefix_spoken(item)
                result["explains_answer_id"] = answer_id
                return result
        return None

    def _sample_lookup(self, question):
        """Pick a recorded response whose question best matches the input."""
        q = self._normalize_text(question)
        responses = self._load_samples()
        
        # First try exact match (with iteration limit)
        iteration_count = 0
        for item in responses:
            if iteration_count >= MAX_SAMPLE_ITERATIONS:
                break
            iteration_count += 1
            
            if item.get("kind") in ("ask", "follow-up", "breakdown",
                                    "low-confidence", "feedback-improved"):
                if self._normalize_text(item.get("question", "")) == q:
                    return self._prefix_spoken(item)
        
        # Keyword fallback with stable sorting (by position in file)
        matches = []
        iteration_count = 0
        for i, item in enumerate(responses):
            if iteration_count >= MAX_SAMPLE_ITERATIONS:
                break
            iteration_count += 1
            
            if item.get("kind") in ("ask", "follow-up", "breakdown",
                                    "low-confidence", "feedback-improved"):
                item_question = self._normalize_text(item.get("question", ""))
                # Only match on words with at least 5 characters to avoid matching on short/empty strings
                keywords = [word for word in item_question.split() if len(word) >= 5]
                if any(word in q for word in keywords):
                    matches.append((i, item))  # Store index for stable sort
        
        # Sort by position in file for deterministic results
        matches.sort(key=lambda x: x[0])
        if matches:
            return self._prefix_spoken(matches[0][1])
            
        # Return a clear "no match found" placeholder instead of default sample
        return {
            "spoken": SAMPLE_PREFIX + " I couldn't find a matching sample for your question.",
            "card": {
                "title": "No Sample Found",
                "columns": ["Status"],
                "rows": [["No matching sample found"]],
                "chart_hint": "table",
                "sources": [],
                "confidence": "low"
            }
        }

    def _sample_by_key(self, key):
        responses = self._load_samples()
        matches = []
        
        # Apply iteration limit
        iteration_count = 0
        for item in responses:
            if iteration_count >= MAX_SAMPLE_ITERATIONS:
                break
            iteration_count += 1
            
            if item.get("key") == key:
                matches.append(item)
        
        if len(matches) > 1:
            raise NorthstarClientError(
                "Multiple samples found with key %r. Keys must be unique." % key,
                context={"key": key, "count": len(matches)})
        elif len(matches) == 1:
            return self._prefix_spoken(matches[0])
        else:
            raise NorthstarClientError(
                "Recorded sample %r not found in samples file." % key,
                context={"key": key})
