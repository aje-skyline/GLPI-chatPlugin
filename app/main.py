"""FastAPI entry point for GLPI AI Gateway — Native OpenAI Function Calling.

UPDATES:
  - Removed sanitize_agent_output: Native SDK handles tool calling internally via JSON,
    so raw string outputs are guaranteed to be clean.
  - Replaced nemotron references with ai_model.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import settings
from app.crew_services import run_crew
from app import it_glpi_client

logger = logging.getLogger(__name__)

# ── Configure application logging ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

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

    def _key(m: dict[str, str]) -> tuple[str, str]:
        return (m.get("role", ""), m.get("content", ""))

    s_keys = [_key(m) for m in stored]
    i_keys = [_key(m) for m in incoming]
    s_len, i_len = len(s_keys), len(i_keys)

    if i_len >= s_len and i_keys[:s_len] == s_keys:
        return incoming

    if s_len >= i_len and s_keys[-i_len:] == i_keys:
        return stored

    if (stored[-1].get("role") == "assistant"
            and incoming
            and incoming[0].get("role") == "user"
            and all(m.get("role") == "user" for m in incoming)):
        return stored + incoming

    if i_len > s_len:
        return incoming

    return stored


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


_SESSION_ID_PREFIXES = ("body:", "hdr:", "conv:", "rand:")

def _strip_session_prefix(sid: str) -> str:
    for prefix in _SESSION_ID_PREFIXES:
        if sid.startswith(prefix):
            return sid[len(prefix):]
    return sid


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


def _save_to_session(session_id: str, messages: list[dict[str, str]], answer: str) -> None:
    """Simpan riwayat percakapan ke session."""
    assistant_msg = {"role": "assistant", "content": answer}
    _session_messages[session_id] = (messages + [assistant_msg])[-_MAX_SESSION_MESSAGES:]
    _session_last_seen[session_id] = time.time()


# ── SSE formatting ────────────────────────────────────────────────────────────

def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_openai_chunk(content: str, model: str, finish_reason: str | None = None) -> str:
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
    
    model_label = settings.ai_model

    loop = asyncio.get_event_loop()
    crew_future = loop.run_in_executor(
        None, run_crew, user_message, glpi_user_id, messages
    )

    status_cycle = [
        "Sedang memproses permintaan Anda…",
        "Mengambil data dari GLPI…",
        "Menganalisis informasi…",
        "Menyiapkan jawaban…",
        "Hampir selesai…",
    ]
    idx = 0
    tick = 0

    while not crew_future.done():
        await asyncio.sleep(0.5)
        tick += 1

        if tick % 4 == 0:
            yield _sse_event("status", {"message": status_cycle[idx % len(status_cycle)]})
            idx += 1

        if tick % 10 == 0:
            yield _sse_event("heartbeat", {"state": "waiting"})

    # ── Get result ────────────────────────────────────────────────────────────
    try:
        final_answer: str = await crew_future
    except Exception as exc:
        logger.exception("Crew error in streaming mode for session=%s", session_id[:20])
        yield _sse_event("error", {"error": f"Crew Error: {exc}"})
        return

    # Langsung gunakan final_answer karena sudah murni dari SDK
    _save_to_session(session_id, messages, final_answer)

    yield _sse_event("meta", {"model": model_label})

    # Stream final_answer word-by-word
    words = final_answer.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        yield _sse_openai_chunk(chunk, model_label)
        await asyncio.sleep(0.03) 

    yield _sse_openai_chunk("", model_label, finish_reason="stop")
    yield "data: [DONE]\n\n"


# ── FastAPI app ───────────────────────────────────────────────────────────────

async def _session_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        _clean_sessions()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    asyncio.create_task(_session_cleanup_loop())
    logger.info("GLPI AI Gateway started")
    yield
    await it_glpi_client.close_http_client()
    it_glpi_client.invalidate_static_cache()
    logger.info("GLPI AI Gateway shutdown complete")


app = FastAPI(title="GLPI AI Gateway", version="3.0.0", lifespan=_lifespan)

_allowed_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
    total_msgs = sum(len(v) for v in _session_messages.values())
    return {
        "status": "ok",
        "service": "GLPI AI Gateway",
        "version": "3.0.0",
        "ai_gateway": settings.ai_gateway_base_url,
        "ai_model": settings.ai_model,
        "architecture": "CrewAI Sequential (Native Integration)",
        "streaming": "emulated-sse",
        "active_sessions": len(_user_sessions),
        "total_session_messages": total_msgs,
    }


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request, response: Response):
    body: dict[str, Any] = await request.json()

    request_messages: list[dict[str, str]] = body.get("messages", [])
    if not request_messages:
        raise HTTPException(status_code=400, detail="'messages' tidak boleh kosong.")

    should_stream: bool = bool(body.get("stream", False))

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

    response.headers["X-Session-ID"] = _strip_session_prefix(session_id)

    stored = _session_messages.get(session_id, [])
    messages = _merge_conversation_history(stored, request_messages)

    logger.debug(
        "session=%s src=%s stored=%d incoming=%d merged=%d stream=%s",
        session_id[:30], session_source, len(stored),
        len(request_messages), len(messages), should_stream,
    )

    user_message: str = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    if not user_message:
        raise HTTPException(status_code=400, detail="Tidak ada pesan user ditemukan.")

    glpi_user_id = _resolve_user_id(body, user_message, session_id)

    logger.info(
        "Request | stream=%s | session=%s | user_id=%s | msg='%s...'",
        should_stream, session_id[:20], glpi_user_id, user_message[:80],
    )

    if should_stream:
        return StreamingResponse(
            _stream_crew_response(session_id, messages, user_message, glpi_user_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Content-Encoding": "none",
                "X-Session-ID": _strip_session_prefix(session_id), 
            },
        )

    try:
        loop = asyncio.get_event_loop()
        final_answer: str = await loop.run_in_executor(
            None, run_crew, user_message, glpi_user_id, messages
        )

        _save_to_session(session_id, messages, final_answer)

        return {
            "id": f"glpi-crew-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "model": settings.ai_model,
            "session_id": _strip_session_prefix(session_id),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": final_answer},
                "finish_reason": "stop",
            }],
        }

    except Exception as exc:
        logger.exception("Crew error for user_id=%s", glpi_user_id)
        raise HTTPException(status_code=500, detail=f"Crew Error: {exc}") from exc