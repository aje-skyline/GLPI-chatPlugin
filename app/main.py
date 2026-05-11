"""FastAPI entry point for GLPI AI Gateway.

Single endpoint (/v1/chat/completions) handles all chat requests.
Routing to appropriate tools is done by CrewAI Agent, not by FastAPI.

CHANGELOG (bug-fix):
  - _stable_fingerprint(): replaced Python built-in hash() (non-deterministic across
    processes due to PYTHONHASHSEED) with hashlib.md5 so the same first user message
    always maps to the same session bucket — even after server restarts.
  - _merge_conversation_history(): rewrote merge logic so the most-common case
    (client sends full history including new user turn) is handled correctly
    instead of silently dropping the latest user message.
  - run_crew() call now always receives the fully-merged messages list so the agent
    has complete multi-turn context.
"""

import asyncio
import hashlib
import logging
import re
import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.crew_services import run_crew

logger = logging.getLogger(__name__)

# In-memory session storage for glpi_user_id persistence across requests
# Key: session_id (from X-Session-ID header or auto-generated)
_user_sessions: dict[str, int] = {}
_session_last_seen: dict[str, float] = {}
_session_messages: dict[str, list[dict[str, str]]] = {}
_MAX_SESSION_MESSAGES: int = 20  # Increased from 16 to keep more context


# ── Stable fingerprint ────────────────────────────────────────────────────────

def _stable_fingerprint(text: str) -> str:
    """Return a deterministic 8-char hex digest of *text*.

    Uses hashlib.md5 instead of Python's built-in hash() because hash() is
    randomised per-process (PYTHONHASHSEED) and therefore produces different
    values across server restarts — causing the same conversation to land in
    different session buckets on every restart.
    """
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:8]


# ── Session merge logic ───────────────────────────────────────────────────────

def _merge_conversation_history(
    stored_messages: list[dict[str, str]],
    incoming_messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Merge stored session history with incoming request messages.

    Design goals
    ------------
    1. Never lose the latest user message (the one the client just sent).
    2. Prefer the longer / more-complete version of the history.
    3. Avoid duplicating messages when the client resends full history.

    Decision table
    --------------
    | stored | incoming | action                                      |
    |--------|----------|---------------------------------------------|
    | empty  | any      | use incoming                                |
    | any    | empty    | use stored                                  |
    | incoming is a superset of stored (client sent full history + new) | use incoming |
    | incoming is a strict subset of stored (client sent partial)       | use stored   |
    | else (new user turn appended to our stored history)               | stored + new |
    """
    if not stored_messages:
        logger.debug("Session history empty — using incoming messages.")
        return incoming_messages

    if not incoming_messages:
        logger.debug("Incoming empty — using stored session history.")
        return stored_messages

    stored_len = len(stored_messages)
    incoming_len = len(incoming_messages)

    # Case 1: Incoming contains the full stored history as a prefix (most common
    # in stateful clients that always resend the full conversation).
    # Accept incoming as-is because it may have new messages appended.
    if (incoming_len >= stored_len
            and incoming_messages[:stored_len] == stored_messages):
        logger.debug(
            "Incoming includes full stored history (%d msgs) — using incoming (%d msgs).",
            stored_len, incoming_len,
        )
        return incoming_messages

    # Case 2: Stored is a superset — incoming is a trailing slice of stored.
    # Client sent a window of recent messages; use the authoritative stored copy.
    if (stored_len >= incoming_len
            and stored_messages[-incoming_len:] == incoming_messages):
        logger.debug(
            "Incoming is a suffix of stored history — using stored (%d msgs).",
            stored_len,
        )
        return stored_messages

    # Case 3: Typical multi-turn where the client sends ONLY the new user turn
    # (i.e. incoming = [{role: "user", content: "<new question>"}]).
    # Append to stored so the agent gets full context.
    if (stored_messages
            and incoming_messages
            and stored_messages[-1].get("role") == "assistant"
            and all(m.get("role") == "user" for m in incoming_messages)):
        logger.debug(
            "New user turn detected — appending %d msg(s) to stored history.",
            incoming_len,
        )
        return stored_messages + incoming_messages

    # Case 4: Incoming is longer than stored but doesn't start with stored.
    # Client probably has more context; trust incoming.
    if incoming_len > stored_len:
        logger.debug(
            "Incoming (%d msgs) longer than stored (%d msgs) with no overlap — using incoming.",
            incoming_len, stored_len,
        )
        return incoming_messages

    # Fallback: prefer stored (authoritative server-side history).
    logger.debug(
        "History mismatch — falling back to stored history (%d msgs).",
        stored_len,
    )
    return stored_messages


# ── Session ID resolution ─────────────────────────────────────────────────────

def _resolve_session_id(request: Request, messages: list, body_sid: str = "") -> str:
    """Resolve a stable session ID for this request.

    Priority:
      1. body_sid field (from request body, passed explicitly).
      2. X-Session-ID header (client-supplied, most reliable).
      3. Fallback: deterministic hash of FIRST user message only.
         Uses hashlib.md5 (not Python's hash()) so it is stable across
         process restarts and different worker processes.

    Returns:
        A non-empty string that is stable across all requests belonging to
        the same conversation.
    """
    # Priority 1: explicit body field
    if body_sid:
        return f"body:{body_sid}"

    # Priority 2: explicit header
    header_sid = request.headers.get("X-Session-ID", "").strip()
    if header_sid:
        return f"hdr:{header_sid}"

    # Priority 3: deterministic fingerprint of first user message
    for msg in messages:
        if msg.get("role") == "user":
            first_user_message = msg.get("content", "").strip()
            if first_user_message:
                return f"conv:{_stable_fingerprint(first_user_message)}"
            break

    # Last resort: random (won't persist, but won't crash either)
    return f"rand:{uuid.uuid4().hex[:12]}"


# ── Session cleanup ───────────────────────────────────────────────────────────

def _clean_sessions() -> None:
    """Remove stale sessions older than TTL."""
    now = time.time()
    cutoff = now - (settings.session_ttl_minutes * 60)
    stale = [k for k, v in _session_last_seen.items() if v < cutoff]
    for k in stale:
        _user_sessions.pop(k, None)
        _session_last_seen.pop(k, None)
        _session_messages.pop(k, None)
    if stale:
        logger.debug("Cleaned %d stale sessions", len(stale))


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="GLPI AI Gateway", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origins],
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type", "X-Session-ID"],
    expose_headers=["X-Session-ID"],
)


def verify_api_key(request: Request) -> None:
    """Validate Bearer token in Authorization header."""
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or auth_header[7:] != settings.gateway_api_key:
        logger.warning("Unauthorized access from %s", request.client.host)
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint with service metadata."""
    return {
        "status": "ok",
        "service": "GLPI AI Gateway",
        "version": "2.1.0",
        "nemotron_gateway": settings.resolved_ai_gateway_base_url,
        "nemotron_model": settings.nemotron_model,
        "architecture": "CrewAI Sequential (Agent + Tools)",
        "active_sessions": len(_user_sessions),
    }


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, response: Response) -> dict[str, Any]:
    """Main chat endpoint (OpenAI-compatible).

    Session persistence
    ------------------
    The server keeps ``glpi_user_id`` AND full message history in memory so
    multi-turn conversations work without the client re-sending context.
    Use a stable ``X-Session-ID`` header (any opaque string, e.g. a UUID)
    for best results. The resolved ID is echoed in the ``X-Session-ID``
    response header so the client can pin it on the first request.
    """
    body: dict[str, Any] = await request.json()

    request_messages: list[dict[str, str]] = body.get("messages", [])
    if not request_messages:
        raise HTTPException(status_code=400, detail="'messages' tidak boleh kosong.")

    # ── Resolve a stable session ID ───────────────────────────────────────────
    body_sid = str(body.get("session_id", "")).strip()

    if body_sid:
        session_id = f"body:{body_sid}"
        session_source = "body"
    elif request.headers.get("X-Session-ID", "").strip():
        session_id = _resolve_session_id(request, request_messages, body_sid="")
        session_source = "header"
    else:
        session_id = _resolve_session_id(request, request_messages, body_sid="")
        session_source = "fingerprint"

    # Echo back so clients can pin it on subsequent requests
    response.headers["X-Session-ID"] = session_id

    # ── Merge conversation history ────────────────────────────────────────────
    stored = _session_messages.get(session_id, [])
    messages = _merge_conversation_history(stored, request_messages)

    logger.debug(
        "session=%s source=%s stored=%d incoming=%d merged=%d",
        session_id[:30], session_source, len(stored),
        len(request_messages), len(messages),
    )

    # ── Extract latest user message ───────────────────────────────────────────
    user_message: str = next(
        (msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"),
        "",
    )
    if not user_message:
        raise HTTPException(status_code=400, detail="Tidak ada pesan user ditemukan.")

    # Clean stale sessions occasionally (~1% of requests)
    if int(time.time()) % 100 == 0:
        _clean_sessions()

    # ── Resolve glpi_user_id with session persistence ─────────────────────────
    raw_user_id = body.get("glpi_user_id")
    glpi_user_id: int = 0

    # Priority 1: Explicit glpi_user_id in request body
    if raw_user_id is not None:
        try:
            glpi_user_id = int(raw_user_id)
        except (ValueError, TypeError):
            logger.warning("Invalid glpi_user_id in body: %s", raw_user_id)

    # Priority 2: Extract from message content (e.g., "user:123")
    if glpi_user_id == 0 and user_message:
        match = re.search(r"(?:user|pemilik|milik)[:\s=]?(\d+)", user_message.lower())
        if match:
            glpi_user_id = int(match.group(1))
            logger.info("Extracted user_id from message: %d", glpi_user_id)

    # Priority 3: Retrieve from session (persisted from a prior request)
    if glpi_user_id == 0:
        glpi_user_id = _user_sessions.get(session_id, 0)
        if glpi_user_id:
            logger.info(
                "Restored user_id=%d from session %s", glpi_user_id, session_id[:30]
            )

    # Persist user_id to session for future requests
    if glpi_user_id > 0:
        _user_sessions[session_id] = glpi_user_id
        _session_last_seen[session_id] = time.time()
        logger.info("Stored user_id=%d in session %s", glpi_user_id, session_id[:30])

    logger.info(
        "Request | session=%s | user_id=%s | msg='%s...'",
        session_id[:20], glpi_user_id, user_message[:60],
    )

    # ── Execute CrewAI agent ──────────────────────────────────────────────────
    try:
        loop = asyncio.get_event_loop()
        final_answer: str = await loop.run_in_executor(
            None, run_crew, user_message, glpi_user_id, messages
        )

        # Persist updated history (cap at _MAX_SESSION_MESSAGES)
        assistant_message = {"role": "assistant", "content": final_answer}
        updated_history = messages + [assistant_message]
        _session_messages[session_id] = updated_history[-_MAX_SESSION_MESSAGES:]
        _session_last_seen[session_id] = time.time()

        return {
            "id": f"glpi-crew-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "model": f"nemotron-crew/{settings.nemotron_model}",
            "session_id": session_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": final_answer},
                "finish_reason": "stop",
            }],
        }

    except Exception as exc:
        logger.exception("Crew error for user_id=%s", glpi_user_id)
        raise HTTPException(status_code=500, detail=f"Crew Error: {exc}") from exc