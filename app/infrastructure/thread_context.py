"""app/infrastructure/thread_context.py — ContextVar untuk propagate session ID.

Masalah yang dipecahkan:
    crew.kickoff_async() secara internal memanggil asyncio.to_thread(self.kickoff),
    yang menjalankan Crew di worker thread terpisah. Thread-local variable biasa
    (threading.local) TIDAK di-copy ke worker thread baru.

    ContextVar dari Python stdlib (PEP 567) di-copy otomatis ke child context
    saat asyncio.to_thread() dipanggil — inilah mekanisme yang benar untuk
    meneruskan nilai dari event loop ke worker thread.

Penggunaan:
    # Di event loop (crew_orchestrator.py) sebelum kickoff:
    set_session_id(session_id)

    # Di worker thread (computer_tools.py) saat tool dipanggil:
    session_id = get_session_id()
"""

from __future__ import annotations

from contextvars import ContextVar

_session_id_var: ContextVar[str] = ContextVar("session_id", default="")


def set_session_id(sid: str) -> None:
    """Set session ID ke ContextVar aktif.

    Dipanggil dari event loop FastAPI sebelum crew.kickoff_async(),
    sehingga nilai propagate ke worker thread via asyncio.to_thread().

    Args:
        sid: Session ID dengan prefix (mis. "conv:7ac87f83").
    """
    _session_id_var.set(sid)


def get_session_id() -> str:
    """Return session ID dari ContextVar aktif.

    Dipanggil dari worker thread CrewAI (dalam _run() tool).
    Return string kosong jika tidak di-set (default).

    Returns:
        Session ID string, atau "" jika tidak tersedia.
    """
    return _session_id_var.get()
