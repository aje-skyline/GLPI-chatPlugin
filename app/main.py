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
from app.crew_services import run_crew, run_crew_async
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

_MAX_STORED_ANSWER_LEN: int = 500

def _compress_for_history(answer: str) -> str:
    """Ringkas jawaban panjang sebelum disimpan ke session history."""
    if len(answer) <= _MAX_STORED_ANSWER_LEN:
        return answer
    return (
        answer[:_MAX_STORED_ANSWER_LEN]
        + "\n… [ringkasan: jawaban asli lebih panjang. "
        + "Agent dapat memanggil tool kembali jika user butuh detail lengkap.]"
    )

def _save_to_session(session_id: str, messages: list[dict[str, str]], answer: str) -> None:
    """Simpan riwayat percakapan ke session, dengan kompresi untuk jawaban panjang."""
    compressed = _compress_for_history(answer)
    assistant_msg = {"role": "assistant", "content": compressed}
    _session_messages[session_id] = (messages + [assistant_msg])[-_MAX_SESSION_MESSAGES:]
    _session_last_seen[session_id] = time.time()

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
    """SSE generator yang mengalirkan thought CrewAI secara real-time.

    Arsitektur aliran data:
    ┌─────────────────────────────────────────────────────────────┐
    │  kickoff_async()  →  asyncio.to_thread(kickoff)            │
    │       ↓                                                     │
    │  step_callback() [worker thread]                           │
    │       ↓  run_coroutine_threadsafe                          │
    │  asyncio.Queue  ←────────────────────────────────────────  │
    │       ↓  await queue.get(timeout=3s)                       │
    │  SSE generator  →  yield _sse_event("thought", ...)       │
    │       ↓                                                     │
    │  Client browser / Axios                                    │
    └─────────────────────────────────────────────────────────────┘

    Jika tidak ada thought dalam 3 detik, generator mengirim keep-alive ping
    dan status cycling agar koneksi HTTP tidak dianggap mati oleh client/proxy.
    Sentinel None dari queue menandakan crew selesai → lanjut stream Final Answer.
    """
    model_label = settings.ai_model

    # ── Queue sebagai jembatan thread ↔ async ────────────────────────────────
    # Unbounded queue; crew tidak akan diproduksi lebih cepat dari konsumsi SSE.
    step_queue: asyncio.Queue[str | None] = asyncio.Queue()

    # ── Jalankan crew sebagai coroutine (bukan thread pool manual) ────────────
    # run_crew_async() menggunakan kickoff_async() → asyncio.to_thread() secara
    # internal — event loop FastAPI TIDAK ter-block selama crew berjalan.
    crew_task = asyncio.create_task(
        run_crew_async(user_message, glpi_user_id, messages, step_queue)
    )

    status_cycle = [
        "Sedang memproses permintaan Anda…",
        "Mengambil data dari GLPI…",
        "Menganalisis informasi…",
        "Menyiapkan jawaban…",
        "Hampir selesai…",
    ]
    status_idx = 0
    start_time = asyncio.get_event_loop().time()
    # v8.0: Turun dari 110s → 80s.
    # Dengan SUPPLIER_MAX_ENRICH=8 dan enrich timeout 8s per-request,
    # query supplier bahkan yang paling lambat seharusnya selesai < 40s.
    # 80s memberi headroom 2× sekaligus abort lebih awal daripada 110s,
    # mengurangi waktu tunggu user saat ada edge-case loop/hang.
    _SERVER_TIMEOUT_S = 80  # Batalkan server-side sebelum client timeout 120s

    # ── Loop utama: konsumsi thought dari queue ───────────────────────────────
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time

        # Server-side timeout guard
        if elapsed >= _SERVER_TIMEOUT_S:
            crew_task.cancel()
            logger.error(
                "Crew async cancelled after %.0fs (server timeout) for session=%s",
                elapsed, session_id[:20],
            )
            yield _sse_event("error", {
                "error": "Waktu pemrosesan habis. Silakan coba lagi dengan pertanyaan yang lebih spesifik."
            })
            return

        try:
            # Tunggu step thought dengan timeout 3 detik.
            # Jika timeout → kirim keep-alive, lanjut loop.
            # Jika dapat None (sentinel) → crew selesai, keluar loop.
            # Jika dapat teks → stream sebagai thought event.
            step_text: str | None = await asyncio.wait_for(
                step_queue.get(), timeout=3.0
            )
        except asyncio.TimeoutError:
            # Tidak ada thought 3 detik → kirim keep-alive agar koneksi hidup.
            # ": ping" adalah SSE comment resmi yang RESET timer Nginx/proxy/Axios
            # tanpa menghasilkan event di client.
            yield ": ping\n\n"
            # Empty OpenAI delta chunk → reset timer SDK yang strict
            yield _sse_openai_chunk("", model_label)
            # Rotasi pesan status agar terlihat aktif di UI
            yield _sse_event("status", {
                "message": status_cycle[status_idx % len(status_cycle)]
            })
            status_idx += 1
            continue

        # Sentinel None = crew selesai (normal atau error)
        if step_text is None:
            break

        # Stream thought agent sebagai SSE event khusus.
        # Client dapat menampilkan ini sebagai "thinking indicator" atau log.
        # Thought sengaja dipotong (sudah dibatasi 400 char di _extract_step_text)
        # agar tidak membanjiri client dengan teks panjang.
        yield _sse_event("thought", {
            "content": step_text,
            "elapsed_s": round(asyncio.get_event_loop().time() - start_time, 1),
        })

    # ── Ambil hasil final dari crew_task ─────────────────────────────────────
    try:
        final_answer: str = await crew_task
    except asyncio.CancelledError:
        logger.error("Crew task cancelled for session=%s", session_id[:20])
        yield _sse_event("error", {
            "error": "Waktu pemrosesan habis. Silakan coba lagi dengan pertanyaan yang lebih spesifik."
        })
        return
    except Exception as exc:
        logger.exception("Crew error in streaming mode for session=%s", session_id[:20])
        err_msg = str(exc).lower()
        if "timed out" in err_msg or "timeout" in err_msg:
            yield _sse_event("error", {
                "error": "Waktu pemrosesan habis. Silakan coba lagi dengan pertanyaan yang lebih spesifik."
            })
        else:
            yield _sse_event("error", {"error": f"Crew Error: {exc}"})
        return

    _save_to_session(session_id, messages, final_answer)

    total_elapsed = round(asyncio.get_event_loop().time() - start_time, 1)
    yield _sse_event("meta", {"model": model_label, "elapsed_s": total_elapsed})

    # ── Stream Final Answer kata per kata ─────────────────────────────────────
    # Memberikan efek "mengetik" di UI; delay 30ms per kata terasa natural.
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
        # v8.0: Tambah asyncio.wait_for dengan timeout 80s agar non-streaming
        # path juga terlindungi (sebelumnya tidak ada timeout eksplisit di sini).
        final_answer: str = await asyncio.wait_for(
            loop.run_in_executor(
                None, run_crew, user_message, glpi_user_id, messages
            ),
            timeout=80.0,
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

    except asyncio.TimeoutError as te:
        logger.error("Crew execution timed out for user_id=%s", glpi_user_id)
        raise HTTPException(
            status_code=504,
            detail="Waktu pemrosesan habis. Silakan coba lagi dengan pertanyaan yang lebih spesifik."
        ) from te
    except Exception as exc:
        logger.exception("Crew error for user_id=%s", glpi_user_id)
        raise HTTPException(status_code=500, detail=f"Crew Error: {exc}") from exc