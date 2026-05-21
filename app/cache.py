"""Simple in-memory TTL cache — GLPI AI Gateway.

Diekstrak dari it_glpi_client.py agar dapat dipakai bersama oleh semua
modul Repository tanpa circular import.

Desain sengaja dibuat minimalis (dict biasa + time.monotonic()) karena:
  - Data GLPI bersifat semi-statis dalam satu sesi (kategori, search options, KB).
  - Thread-safety tidak diperlukan: semua akses terjadi di dalam background
    async event loop yang sama (single-threaded concurrency model asyncio).
  - Menghindari dependensi tambahan (redis, cachetools, dsb.).

Konstanta:
    CACHE_TTL_SECONDS: TTL default 5 menit. Cukup lama untuk menghindari
    redundant API call dalam satu sesi percakapan, cukup singkat agar
    perubahan data GLPI terefleksi tanpa restart server.
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Konfigurasi ───────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS: int = 300
"""TTL default entry cache dalam detik (5 menit)."""

# ── Storage ───────────────────────────────────────────────────────────────────

_ttl_cache: dict[str, dict[str, Any]] = {}
"""Dict global penyimpan cache. Key = cache key string, value = dict dengan
field ``value`` (data asli) dan ``expires_at`` (float monotonic timestamp)."""


# ── Public API ────────────────────────────────────────────────────────────────

def cache_get(key: str) -> Any | None:
    """Ambil nilai dari cache jika belum kedaluwarsa.

    Args:
        key: Cache key yang ingin diambil.

    Returns:
        Nilai yang tersimpan, atau ``None`` jika tidak ada / sudah expired.
    """
    entry = _ttl_cache.get(key)
    if entry is None:
        return None
    if time.monotonic() >= entry["expires_at"]:
        # Hapus entry expired secara lazy agar dict tidak terus membesar.
        _ttl_cache.pop(key, None)
        logger.debug("cache_get: expired key='%s'", key)
        return None
    logger.debug("cache_get: HIT key='%s'", key)
    return entry["value"]


def cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    """Simpan nilai ke cache dengan TTL tertentu.

    Args:
        key  : Cache key.
        value: Nilai yang ingin disimpan. Bisa berupa tipe apa pun.
        ttl  : Time-to-live dalam detik. Default ``CACHE_TTL_SECONDS``.
    """
    _ttl_cache[key] = {
        "value": value,
        "expires_at": time.monotonic() + ttl,
    }
    logger.debug("cache_set: key='%s' ttl=%ds", key, ttl)


def cache_invalidate(key: str) -> bool:
    """Hapus satu entry cache secara eksplisit.

    Args:
        key: Cache key yang ingin dihapus.

    Returns:
        ``True`` jika key ditemukan dan dihapus, ``False`` jika tidak ada.
    """
    removed = _ttl_cache.pop(key, None) is not None
    if removed:
        logger.info("cache_invalidate: key='%s' removed", key)
    return removed


def cache_clear() -> int:
    """Hapus seluruh isi cache.

    Dipanggil saat admin meminta refresh data atau saat startup/shutdown.

    Returns:
        Jumlah entry yang dihapus.
    """
    count = len(_ttl_cache)
    _ttl_cache.clear()
    logger.info("cache_clear: %d entries removed", count)
    return count


def cache_purge_expired() -> int:
    """Hapus semua entry yang sudah kedaluwarsa.

    Fungsi opsional untuk housekeeping. Tidak perlu dipanggil secara rutin
    karena ``cache_get`` sudah menghapus expired entry secara lazy, tapi
    berguna jika Anda ingin memastikan memori dibebaskan lebih awal.

    Returns:
        Jumlah entry expired yang dihapus.
    """
    now = time.monotonic()
    expired_keys = [k for k, v in _ttl_cache.items() if now >= v["expires_at"]]
    for k in expired_keys:
        _ttl_cache.pop(k, None)
    if expired_keys:
        logger.info("cache_purge_expired: %d expired entries removed", len(expired_keys))
    return len(expired_keys)


def cache_stats() -> dict[str, int]:
    """Kembalikan statistik cache saat ini (untuk debugging/monitoring).

    Returns:
        Dict dengan field ``total`` (semua entry) dan ``expired`` (yang sudah lewat TTL).
    """
    now = time.monotonic()
    expired = sum(1 for v in _ttl_cache.values() if now >= v["expires_at"])
    return {"total": len(_ttl_cache), "expired": expired, "active": len(_ttl_cache) - expired}