"""Shared HTTP client — GLPI AI Gateway infrastructure layer.

Mengelola satu instance ``httpx.AsyncClient`` yang di-share oleh semua
Repository. Pendekatan shared-client (bukan membuat client baru per-request)
dipilih karena:

  - Connection pooling: httpx mempertahankan koneksi TCP ke server GLPI
    sehingga request berikutnya tidak perlu 3-way handshake lagi.
  - Keepalive: koneksi idle dipertahankan selama ``keepalive_expiry`` detik,
    menghindari overhead reconnect pada query berurutan.
  - Konsistensi konfigurasi: timeout, SSL, dan limits dikonfigurasi di satu
    tempat — tidak mungkin ada request yang lupa set verify=False.

Konfigurasi bersumber dari ``app.config.settings`` (glpi_verify_ssl, dsb.).

Catatan asyncio.Lock
─────────────────────
Lock TIDAK dibuat di module-level. Ia dibuat secara lazy di dalam
``_get_http_client_lock()`` yang dipanggil saat pertama kali dibutuhkan.
Ini penting karena modul ini diimpor sebelum background event loop (di
``async_runner.py``) berjalan. Lock asyncio terikat ke event loop aktif
saat dibuat; jika dibuat terlalu awal, ia terikat ke loop yang salah dan
akan raise "Future attached to a different loop" saat digunakan.
"""

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ── Konfigurasi HTTP client ───────────────────────────────────────────────────

_HTTP_TIMEOUT: float = 30.0
"""Timeout per-request dalam detik. Mencakup connect + read + write."""

_MAX_CONNECTIONS: int = 20
"""Jumlah maksimum koneksi concurrent ke server GLPI."""

_MAX_KEEPALIVE_CONNECTIONS: int = 10
"""Jumlah koneksi idle yang dipertahankan di pool."""

_KEEPALIVE_EXPIRY: float = 30.0
"""Durasi maksimum koneksi idle dipertahankan sebelum ditutup (detik)."""

# ── Singleton state ───────────────────────────────────────────────────────────

_http_client: httpx.AsyncClient | None = None
_http_client_lock: asyncio.Lock | None = None


def _get_http_client_lock() -> asyncio.Lock:
    """Kembalikan Lock untuk inisialisasi client, membuat secara lazy jika belum ada.

    Lock ini TIDAK dibuat di module-level — lihat catatan di docstring modul.
    """
    global _http_client_lock
    if _http_client_lock is None:
        _http_client_lock = asyncio.Lock()
    return _http_client_lock


# ── Public API ────────────────────────────────────────────────────────────────

async def get_http_client() -> httpx.AsyncClient:
    """Kembalikan shared ``httpx.AsyncClient``, membuat satu kali jika belum ada.

    Menggunakan double-checked locking untuk thread/coroutine safety:
      1. Cek pertama (tanpa lock) untuk fast path setelah client tersedia.
      2. Cek kedua (di dalam lock) untuk memastikan hanya satu coroutine
         yang membuat client saat startup.

    Client dikonfigurasi dengan:
      - ``timeout``  : ``_HTTP_TIMEOUT`` detik (connect + read).
      - ``verify``   : Dari ``settings.glpi_verify_ssl``. Set ``False`` untuk
                       GLPI dengan self-signed certificate (umum di on-premise).
      - ``limits``   : Connection pool sesuai konstanta di atas.

    Returns:
        Instance ``httpx.AsyncClient`` yang siap dipakai untuk request.

    Raises:
        RuntimeError: Jika client gagal dibuat (sangat jarang, biasanya OOM).
    """
    global _http_client

    # Fast path: client sudah ada dan belum di-close.
    if _http_client is not None and not _http_client.is_closed:
        return _http_client

    async with _get_http_client_lock():
        # Double-check: coroutine lain mungkin sudah membuat client selama kita
        # menunggu lock.
        if _http_client is not None and not _http_client.is_closed:
            return _http_client

        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,   # Waktu tunggu koneksi TCP dibuka
                read=_HTTP_TIMEOUT,  # Waktu tunggu response body
                write=10.0,     # Waktu tunggu request dikirim
                pool=5.0,       # Waktu tunggu dapat koneksi dari pool
            ),
            verify=settings.glpi_verify_ssl,
            limits=httpx.Limits(
                max_connections=_MAX_CONNECTIONS,
                max_keepalive_connections=_MAX_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=_KEEPALIVE_EXPIRY,
            ),
            # Follow redirect — GLPI kadang redirect http → https
            follow_redirects=True,
        )
        logger.info(
            "GLPI shared AsyncClient created "
            "(verify_ssl=%s, timeout=%.1fs, max_conn=%d)",
            settings.glpi_verify_ssl,
            _HTTP_TIMEOUT,
            _MAX_CONNECTIONS,
        )

    return _http_client


async def close_http_client() -> None:
    """Tutup shared HTTP client dan bebaskan semua koneksi di pool.

    Harus dipanggil saat aplikasi shutdown (misal: di ``lifespan`` FastAPI)
    agar koneksi TCP ke server GLPI ditutup dengan bersih dan tidak menimbulkan
    "Connection reset by peer" di sisi server.

    Aman dipanggil berulang kali (idempotent): jika client sudah ditutup atau
    tidak pernah dibuat, fungsi ini tidak melakukan apa-apa.
    """
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        logger.info("GLPI shared AsyncClient closed")
    _http_client = None


def get_base_headers() -> dict[str, str]:
    """Kembalikan header dasar yang wajib disertakan di setiap request GLPI API.

    Header ini bersifat statis (tidak berubah antar request) dan tidak
    mengandung Session-Token (yang bersifat dinamis dan dikelola oleh
    ``session_manager.py``).

    Returns:
        Dict header dengan ``Content-Type`` dan ``App-Token``.
    """
    return {
        "Content-Type": "application/json",
        "App-Token": settings.glpi_app_token,
    }