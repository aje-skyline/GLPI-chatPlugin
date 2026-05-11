"""FastAPI entry point for GLPI AI Gateway — v2.2.0 with streaming support.

CHANGELOG:
  v2.1 - hashlib.md5 fingerprint, fixed merge logic
  v2.2 - Streaming: when body contains "stream": true, returns SSE in
         OpenAI-compatible format so chat.php works unchanged.

WHY NOT TRUE TOKEN STREAMING
-----------------------------
CrewAI is a blocking orchestration framework: it calls the LLM to decide
which tool to use, waits for the tool (GLPI API), then calls the LLM again
to produce the final answer.  The token stream happens *inside* CrewAI and
cannot be piped out directly.

WHAT WE DO INSTEAD (Emulated Streaming)
-----------------------------------------
  Phase 1 — While CrewAI runs (blocking):
    • Every 2 s: `event: status` with rotating progress messages
    • Every 5 s: `event: heartbeat` to keep proxies/browsers alive

  Phase 2 — After CrewAI finishes:
    • Each word of the answer → `data: {...delta.content...}` (OpenAI format)
    • ~30 ms delay between words for a smooth typing effect
    • `data: [DONE]` sentinel — chat.php already handles this

chat.php parses `choices[0].delta.content` and the [DONE] sentinel, so
the PHP side requires ZERO changes.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import settings
from app.crew_services import run_crew

logger = logging.getLogger(__name__)

# ── In-memory session store ───────────────────────────────────────────────────
_user_sessions: dict[str, int] = {}
_session_last_seen: dict[str, float] = {}
_session_messages: dict[str, list[dict[str, str]]] = {}
_MAX_SESSION_MESSAGES: int = 20


# ── Utilities ─────────────────────────────────────────────────────────────────

def _stable_fingerprint(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:8]


def _merge_conversation_history(
    stored: list[dict[str, str]],
    incoming: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not stored:
        return incoming
    if not incoming:
        return stored

    s_len, i_len = len(stored), len(incoming)

    if i_len >= s_len and incoming[:s_len] == stored:
        return incoming  # incoming is superset
    if s_len >= i_len and stored[-i_len:] == incoming:
        return stored    # incoming is a trailing slice of stored
    if (stored[-1].get("role") == "assistant"
            and all(m.get("role") == "user" for m in incoming)):
        return stored + incoming  # new user turn(s) appended
    if i_len > s_len:
        return incoming  # incoming is longer but no overlap

    return stored  # fallback: stored is authoritative


def _resolve_session_id(request: Request | None, messages: list, body_sid: str = "") -> str:
    if body_sid:
        return f"body:{body_sid}"
    if request is not None:
        header_sid = request.headers.get("X-Session-ID", "").strip()
        if header_sid:
            return f"hdr:{header_sid}"
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("content", "").strip()
            if text:
                return f"conv:{_stable_fingerprint(text)}"
            break
    return f"rand:{uuid.uuid4().hex[:12]}"


def _clean_sessions() -> None:
    now = time.time()
    cutoff = now - (settings.session_ttl_minutes * 60)
    stale = [k for k, v in _session_last_seen.items() if v < cutoff]
    for k in stale:
        _user_sessions.pop(k, None)
        _session_last_seen.pop(k, None)
        _session_messages.pop(k, None)
    if stale:
        logger.debug("Cleaned %d stale sessions", len(stale))


def _resolve_user_id(body: dict, user_message: str, session_id: str) -> int:
    glpi_user_id: int = 0

    raw = body.get("glpi_user_id")
    if raw is not None:
        try:
            glpi_user_id = int(raw)
        except (ValueError, TypeError):
            pass

    if glpi_user_id == 0 and user_message:
        m = re.search(r"(?:user|pemilik|milik)[:\s=]?(\d+)", user_message.lower())
        if m:
            glpi_user_id = int(m.group(1))

    if glpi_user_id == 0:
        glpi_user_id = _user_sessions.get(session_id, 0)
        if glpi_user_id:
            logger.info("Restored user_id=%d from session %s", glpi_user_id, session_id[:30])

    if glpi_user_id > 0:
        _user_sessions[session_id] = glpi_user_id
        _session_last_seen[session_id] = time.time()

    return glpi_user_id


# ── SSE formatting ────────────────────────────────────────────────────────────

def _sse_event(event: str, data: Any) -> str:
    """Non-OpenAI event (status, heartbeat, error) — used by chat.php handlers."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_openai_chunk(content: str, model: str, finish_reason: str | None = None) -> str:
    """OpenAI-compatible streaming chunk — parsed by chat.php as delta.content."""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": content} if content else {},
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


# ── Streaming generator ───────────────────────────────────────────────────────

async def _stream_crew_response(
    session_id: str,
    messages: list[dict[str, str]],
    user_message: str,
    glpi_user_id: int,
) -> AsyncGenerator[str, None]:
    """Stream CrewAI response via SSE.

    Phase 1: status + heartbeat events while CrewAI blocks
    Phase 2: word-by-word token events after answer is ready
    Phase 3: [DONE] sentinel
    """
    model_label = f"nemotron-crew/{settings.nemotron_model}"

    # ── Phase 1: Status events while CrewAI runs ──────────────────────────────
    loop = asyncio.get_event_loop()
    crew_future = loop.run_in_executor(
        None, run_crew, user_message, glpi_user_id, messages
    )

    status_cycle = [
        "Sedang memproses permintaan Anda…",
        "Mengambil data dari GLPI…",
        "Menganalisis informasi…",
        "Menyiapkan jawaban…",
    ]
    idx = 0
    tick = 0

    while not crew_future.done():
        await asyncio.sleep(0.5)
        tick += 1

        if tick % 4 == 0:  # every 2 s
            yield _sse_event("status", {"message": status_cycle[idx % len(status_cycle)]})
            idx += 1

        if tick % 10 == 0:  # every 5 s — keep connection alive
            yield _sse_event("heartbeat", {"state": "waiting"})

    # ── Phase 2: Get result ───────────────────────────────────────────────────
    try:
        final_answer: str = await crew_future
    except Exception as exc:
        logger.exception("Crew error in streaming mode for session=%s", session_id[:20])
        yield _sse_event("error", {"error": f"Crew Error: {exc}"})
        return

    # Persist to session
    assistant_msg = {"role": "assistant", "content": final_answer}
    _session_messages[session_id] = (messages + [assistant_msg])[-_MAX_SESSION_MESSAGES:]
    _session_last_seen[session_id] = time.time()

    # Send model meta so chat.php can display it
    yield _sse_event("meta", {"model": model_label})

    # ── Phase 3: Stream answer word-by-word ───────────────────────────────────
    words = final_answer.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        yield _sse_openai_chunk(chunk, model_label)
        await asyncio.sleep(0.03)  # 30 ms per word ≈ natural typing speed

    # ── Phase 4: [DONE] sentinel ──────────────────────────────────────────────
    yield _sse_openai_chunk("", model_label, finish_reason="stop")
    yield "data: [DONE]\n\n"


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="GLPI AI Gateway", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origins],
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type", "X-Session-ID"],
    expose_headers=["X-Session-ID"],
)


def verify_api_key(request: Request) -> None:
    auth_header: str = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or auth_header[7:] != settings.gateway_api_key:
        logger.warning("Unauthorized access from %s", request.client.host)
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "GLPI AI Gateway",
        "version": "2.2.0",
        "nemotron_gateway": settings.resolved_ai_gateway_base_url,
        "nemotron_model": settings.nemotron_model,
        "architecture": "CrewAI Sequential (Agent + Tools)",
        "streaming": "emulated-sse",
        "active_sessions": len(_user_sessions),
    }


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, response: Response):
    """Main chat endpoint — OpenAI-compatible, supports streaming.

    When `"stream": true` in body → returns SSE (text/event-stream).
    Otherwise → returns standard JSON.
    """
    body: dict[str, Any] = await request.json()

    request_messages: list[dict[str, str]] = body.get("messages", [])
    if not request_messages:
        raise HTTPException(status_code=400, detail="'messages' tidak boleh kosong.")

    should_stream: bool = bool(body.get("stream", False))

    # ── Session resolution ────────────────────────────────────────────────────
    body_sid = str(body.get("session_id", "")).strip()
    header_sid = request.headers.get("X-Session-ID", "").strip()

    if body_sid:
        session_id = f"body:{body_sid}"
        session_source = "body"
    elif header_sid:
        session_id = f"hdr:{header_sid}"
        session_source = "header"
    else:
        session_id = _resolve_session_id(request, request_messages)
        session_source = "fingerprint"

    # Echo resolved session ID
    response.headers["X-Session-ID"] = session_id

    # ── History merge ─────────────────────────────────────────────────────────
    stored = _session_messages.get(session_id, [])
    messages = _merge_conversation_history(stored, request_messages)

    logger.debug(
        "session=%s src=%s stored=%d incoming=%d merged=%d stream=%s",
        session_id[:30], session_source, len(stored),
        len(request_messages), len(messages), should_stream,
    )

    # ── Extract latest user message ───────────────────────────────────────────
    user_message: str = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    if not user_message:
        raise HTTPException(status_code=400, detail="Tidak ada pesan user ditemukan.")

    # ── Resolve user ID ───────────────────────────────────────────────────────
    glpi_user_id = _resolve_user_id(body, user_message, session_id)

    if int(time.time()) % 100 == 0:
        _clean_sessions()

    logger.info(
        "Request | stream=%s | session=%s | user_id=%s | msg='%s...'",
        should_stream, session_id[:20], glpi_user_id, user_message[:60],
    )

    # ── STREAMING response ────────────────────────────────────────────────────
    if should_stream:
        return StreamingResponse(
            _stream_crew_response(session_id, messages, user_message, glpi_user_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",   # Nginx: disable proxy buffer
                "Content-Encoding": "none",
                "X-Session-ID": session_id,
            },
        )

    # ── NON-STREAMING response ────────────────────────────────────────────────
    try:
        loop = asyncio.get_event_loop()
        final_answer: str = await loop.run_in_executor(
            None, run_crew, user_message, glpi_user_id, messages
        )

        assistant_msg = {"role": "assistant", "content": final_answer}
        _session_messages[session_id] = (messages + [assistant_msg])[-_MAX_SESSION_MESSAGES:]
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