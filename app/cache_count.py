"""app/cache_count.py — Session-level in-memory cache untuk count tool results.

Menyimpan hasil count tools (count_all_computers, count_all_assets) per session
dengan TTL 5 menit. Mencegah agent memanggil GLPI API berkali-kali untuk
pertanyaan count yang sama dalam satu sesi.

Struktur data:
    _count_cache[session_id][tool_name] = (result_str, monotonic_timestamp)

Thread-safety:
    Dict Python bersifat thread-safe untuk operasi get/set sederhana di CPython
    (GIL). Tidak perlu lock eksplisit untuk use case ini.
"""

from __future__ import annotations

import time

_count_cache: dict[str, dict[str, tuple[str, float]]] = {}
COUNT_CACHE_TTL: float = 300.0  # 5 menit dalam detik


def get_count_cache(session_id: str, tool_name: str) -> str | None:
    """Return cached result jika ada dan belum expired. None jika miss/expired.

    Args:
        session_id: ID sesi user (format: "conv:xxxx", "body:xxxx", dll).
        tool_name:  Nama tool CrewAI, mis. "count_all_computers".

    Returns:
        String hasil tool jika cache hit dan belum expired. None jika miss.
    """
    if not session_id:
        return None
    entry = _count_cache.get(session_id, {}).get(tool_name)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > COUNT_CACHE_TTL:
        # Entry expired — hapus dan return None
        _count_cache[session_id].pop(tool_name, None)
        return None
    return result


def set_count_cache(session_id: str, tool_name: str, result: str) -> None:
    """Simpan result ke cache dengan timestamp monotonic sekarang.

    Args:
        session_id: ID sesi user.
        tool_name:  Nama tool CrewAI.
        result:     String output tool yang akan di-cache.
    """
    if not session_id:
        return
    if session_id not in _count_cache:
        _count_cache[session_id] = {}
    _count_cache[session_id][tool_name] = (result, time.monotonic())


def clear_expired() -> None:
    """Bersihkan semua entry expired dari cache.

    Dipanggil periodik dari _session_cleanup_loop() di main.py (setiap 60 detik).
    Mencegah memory leak dari session yang sudah tidak aktif.
    """
    now = time.monotonic()
    for sid in list(_count_cache.keys()):
        for tool in list(_count_cache[sid].keys()):
            _, ts = _count_cache[sid][tool]
            if now - ts > COUNT_CACHE_TTL:
                del _count_cache[sid][tool]
        if not _count_cache[sid]:
            del _count_cache[sid]
