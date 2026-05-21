"""GLPI API gateway — GLPI AI Gateway infrastructure layer.

Menyediakan fungsi ``glpi_get()`` sebagai satu-satunya pintu masuk untuk
semua HTTP GET request ke GLPI REST API. Semua modul Repository HARUS
menggunakan fungsi ini — tidak boleh membuat request httpx secara langsung.

Tanggung jawab lapisan ini:
  1. Menyuntikkan auth headers (App-Token + Session-Token) ke setiap request.
  2. Menangani HTTP 401 (session expired): invalidate + refresh token, retry
     request sekali lagi secara otomatis.
  3. Menangani retryable server errors (429, 500, 502, 503, 504): exponential
     backoff, maksimal 3 percobaan total.
  4. Memanggil ``raise_for_status()`` untuk non-retryable error sehingga
     Repository menerima exception yang bermakna (bukan response mentah).
  5. Me-log setiap retry dan refresh sehingga masalah konektivitas mudah
     di-trace dari log tanpa perlu debugger.

Hal yang TIDAK dilakukan lapisan ini:
  - Parsing/transformasi data response (tanggung jawab Repository).
  - Caching (tanggung jawab Repository atau shared cache.py).
  - Pagination (tanggung jawab Repository via pagination.py).

Desain retry
─────────────
  Attempt 1: request langsung.
  Attempt 2 (jika 429/5xx): tunggu 1 detik, coba lagi.
  Attempt 3 (jika masih 429/5xx): tunggu 2 detik, coba lagi.
  Setelah 3 attempt tetap gagal → raise_for_status() → exception ke Repository.

  HTTP 401 di-handle di luar loop retry dengan satu kali token refresh,
  karena 401 bukan "transient error" tapi "autentikasi perlu diperbarui".
  Setelah refresh, request di-retry sekali; jika masih 401 → exception.
"""

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings
from app.infrastructure.http_client import get_base_headers, get_http_client
from app.infrastructure.session_manager import get_session_token, refresh_session_token

logger = logging.getLogger(__name__)

# ── Konfigurasi retry ─────────────────────────────────────────────────────────

_MAX_ATTEMPTS: int = 3
"""Jumlah maksimum percobaan request (termasuk percobaan pertama)."""

_RETRY_WAIT_BASE: float = 1.0
"""Basis waktu tunggu exponential backoff dalam detik.

  Attempt 1 → langsung
  Attempt 2 → tunggu 1.0 detik
  Attempt 3 → tunggu 2.0 detik
"""

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
"""Status code yang layak dicoba ulang (transient errors dan rate limiting)."""

# ── Private helpers ───────────────────────────────────────────────────────────

def _build_auth_headers(session_token: str) -> dict[str, str]:
    """Bangun headers lengkap untuk satu request ke GLPI API.

    Menggabungkan header statis (Content-Type, App-Token) dari ``http_client``
    dengan Session-Token yang bersifat dinamis.

    Args:
        session_token: Token session aktif dari ``session_manager``.

    Returns:
        Dict header siap pakai.
    """
    return {
        **get_base_headers(),
        "Session-Token": session_token,
    }


async def _do_single_request(
    path: str,
    token: str,
    params: dict[str, Any] | None,
) -> httpx.Response:
    """Jalankan satu GET request ke GLPI dengan headers yang sudah di-inject.

    Args:
        path  : URL path relatif terhadap GLPI API base (misal: ``/Computer``).
        token : Session token aktif.
        params: Query parameters opsional.

    Returns:
        ``httpx.Response`` mentah — belum di-raise, belum di-parse.
    """
    api_base = settings.glpi_api_url.rstrip("/")
    client = await get_http_client()
    return await client.get(
        f"{api_base}{path}",
        headers=_build_auth_headers(token),
        params=params,
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def glpi_get(
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    """Kirim authenticated GET request ke GLPI API dan kembalikan response JSON.

    Fungsi ini adalah satu-satunya entry point untuk seluruh komunikasi HTTP
    ke GLPI. Semua Repository HARUS memanggil fungsi ini — tidak boleh membuat
    httpx request secara langsung.

    Args:
        path  : URL path relatif terhadap GLPI API base URL yang dikonfigurasi
                di ``settings.glpi_api_url``. Contoh: ``"/Computer"``,
                ``"/search/Computer"``, ``"/Contract/42"``.
        params: Dict query parameter opsional. GLPI menggunakan query string
                untuk filter, pagination, dan expand_dropdowns.

    Returns:
        Parsed JSON response: bisa berupa ``dict`` (single item / search
        envelope) atau ``list`` (beberapa item tanpa envelope).

    Raises:
        httpx.HTTPStatusError : Untuk non-retryable HTTP errors (4xx selain 401,
                                atau 5xx setelah semua retry habis).
        httpx.RequestError    : Untuk network errors (timeout, DNS, dsb.).
        RuntimeError          : Jika session tidak bisa diinisialisasi.

    Notes:
        - HTTP 401 di-handle secara internal dengan satu kali token refresh.
          Caller tidak perlu tahu tentang mekanisme session.
        - HTTP 429/5xx di-retry dengan exponential backoff secara internal.
          Caller tidak perlu tahu berapa kali request diulangi.
        - Logging retry dan refresh dilakukan di sini sehingga Repository
          tidak perlu mengulang logika ini.
    """
    token: str = await get_session_token()
    resp: httpx.Response | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        resp = await _do_single_request(path, token, params)

        # ── Handling HTTP 401: session expired ────────────────────────────────
        if resp.status_code == 401:
            logger.info(
                "glpi_get: HTTP 401 (session expired) pada path='%s' "
                "— refreshing session token",
                path,
            )
            token = await refresh_session_token(old_token=token)
            # Satu kali retry setelah refresh. Jika masih 401, raise.
            resp = await _do_single_request(path, token, params)
            if resp.status_code == 401:
                logger.error(
                    "glpi_get: HTTP 401 persisten setelah token refresh "
                    "(path='%s') — kemungkinan user_token tidak valid",
                    path,
                )
                resp.raise_for_status()
            # Jika setelah refresh berhasil (2xx), lanjut ke raise_for_status di bawah.

        # ── Handling retryable server errors ──────────────────────────────────
        if resp.status_code in _RETRYABLE_STATUS_CODES:
            if attempt < _MAX_ATTEMPTS:
                wait_seconds = _RETRY_WAIT_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "glpi_get: HTTP %d pada path='%s' "
                    "— retry ke-%d dalam %.1f detik",
                    resp.status_code,
                    path,
                    attempt,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue  # Ulangi loop dengan attempt berikutnya
            else:
                # Semua retry habis — raise agar Repository tahu.
                logger.error(
                    "glpi_get: HTTP %d pada path='%s' setelah %d attempt "
                    "— menyerah",
                    resp.status_code,
                    path,
                    _MAX_ATTEMPTS,
                )

        # ── Semua kasus lain: raise jika error, return jika sukses ───────────
        resp.raise_for_status()
        return resp.json()

    # Baris ini hanya tercapai jika loop selesai tanpa return (tidak mungkin
    # dengan logika di atas, tapi mypy membutuhkannya untuk type narrowing).
    assert resp is not None  # noqa: S101
    resp.raise_for_status()
    return resp.json()