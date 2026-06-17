"""GLPI session manager — GLPI AI Gateway infrastructure layer.

Mengelola siklus hidup session GLPI: inisialisasi, pemakaian bersama antar
coroutine, dan refresh otomatis saat session expired.

Desain concurrency (Waiter Pattern)
────────────────────────────────────
Saat beberapa coroutine membutuhkan session token secara bersamaan (common
di awal startup saat banyak tool dipanggil hampir serentak), kita tidak ingin
N coroutine membuat N initSession request sekaligus — itu boros dan membuat
GLPI menyimpan N session aktif.

Solusinya adalah "waiter pattern":
  1. Coroutine pertama yang menemukan token kosong menjadi "leader" dan
     membuat sebuah ``asyncio.Future`` (disebut waiter) lalu menyimpannya
     di ``_session_waiter``.
  2. Coroutine berikutnya yang datang menemukan waiter sudah ada, lalu
     menunggu (``await asyncio.shield(waiter)``) tanpa memulai request baru.
  3. Setelah leader selesai, ia men-set result Future → semua waiter
     terbangun dan mendapat token yang sama.

``asyncio.shield`` dipakai agar pembatalan (cancel) dari luar tidak merusak
waiter yang sedang ditunggu banyak coroutine.

Catatan asyncio.Lock
─────────────────────
Lock dibuat secara lazy (pertama kali dibutuhkan), bukan di module-level.
Lihat penjelasan di ``async_runner.py`` tentang kenapa ini penting.
"""

import asyncio
import logging
from typing import Any

from app.config import settings
from app.infrastructure.http_client import get_base_headers, get_http_client

logger = logging.getLogger(__name__)

# ── Singleton state ───────────────────────────────────────────────────────────

_session_token: str | None = None
_session_lock: asyncio.Lock | None = None
_session_waiter: "asyncio.Future[str] | None" = None


def _get_session_lock() -> asyncio.Lock:
    """Kembalikan Lock session, membuat secara lazy jika belum ada."""
    global _session_lock
    if _session_lock is None:
        _session_lock = asyncio.Lock()
    return _session_lock


# ── Private helpers ───────────────────────────────────────────────────────────

async def _init_session() -> str:
    """Buat session GLPI baru via ``GET /initSession``.

    Menggunakan ``glpi_user_token`` dari settings untuk autentikasi awal.
    Setelah sukses, GLPI mengembalikan ``session_token`` yang dipakai untuk
    semua request berikutnya.

    Returns:
        Session token string yang valid.

    Raises:
        httpx.HTTPStatusError: Jika GLPI mengembalikan status error.
        RuntimeError: Jika response tidak mengandung ``session_token``.
    """
    api_base = settings.glpi_api_url.rstrip("/")
    client = await get_http_client()
    resp = await client.get(
        f"{api_base}/initSession",
        headers={
            **get_base_headers(),
            "Authorization": f"user_token {settings.glpi_user_token}",
        },
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    token: str | None = data.get("session_token")
    if not token:
        raise RuntimeError(
            f"GLPI initSession berhasil (HTTP 200) tapi tidak mengembalikan "
            f"'session_token'. Response: {data}"
        )
    logger.info("GLPI session initialized successfully")
    return token


async def kill_session(token: str) -> None:
    """Tutup session GLPI yang aktif via ``GET /killSession``.

    Kegagalan di-swallow dan hanya di-log sebagai warning karena:
      - Session GLPI akan expired sendiri sesuai konfigurasi server.
      - Kegagalan killSession tidak boleh mengganggu alur shutdown aplikasi.

    Args:
        token: Session token yang akan ditutup.
    """
    try:
        api_base = settings.glpi_api_url.rstrip("/")
        client = await get_http_client()
        await client.get(
            f"{api_base}/killSession",
            headers={**get_base_headers(), "Session-Token": token},
        )
        logger.info("GLPI session killed successfully")
    except Exception as exc:
        logger.warning("GLPI killSession failed (ignored): %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_session_token() -> str:
    """Kembalikan session token yang valid, membuat session baru jika diperlukan.

    Mengimplementasikan waiter pattern untuk menghindari multiple concurrent
    initSession requests. Aman dipanggil dari banyak coroutine secara bersamaan.

    Returns:
        Session token string yang siap dipakai sebagai ``Session-Token`` header.

    Raises:
        RuntimeError: Jika initSession gagal (propagated dari ``_init_session``).
        httpx.HTTPStatusError: Jika GLPI mengembalikan HTTP error saat init.
    """
    global _session_token, _session_waiter

    # Fast path: token sudah ada — return langsung tanpa lock.
    if _session_token:
        return _session_token

    lock = _get_session_lock()
    loop = asyncio.get_running_loop()
    is_leader = False
    waiter: "asyncio.Future[str]"

    async with lock:
        # Re-check setelah mendapat lock (coroutine lain mungkin sudah set token).
        if _session_token:
            return _session_token

        if _session_waiter is not None:
            # Ada coroutine lain yang sedang membuat session — ikut menunggu.
            waiter = _session_waiter
        else:
            # Kita yang pertama — jadi leader, buat waiter untuk coroutine lain.
            waiter = loop.create_future()
            _session_waiter = waiter
            is_leader = True

    if not is_leader:
        # Bukan leader — tunggu sampai leader selesai.
        # asyncio.shield melindungi waiter dari cancel yang datang dari luar.
        return await asyncio.shield(waiter)

    # Leader: jalankan initSession, broadcast hasilnya ke semua waiter.
    try:
        token = await _init_session()
        async with lock:
            _session_token = token
            _session_waiter = None
        waiter.set_result(token)
        return token
    except Exception as exc:
        # Gagal: bersihkan waiter dan propagate exception ke semua yang menunggu.
        async with lock:
            _session_waiter = None
        if not waiter.done():
            waiter.set_exception(exc)
            # Panggil exception() untuk menandai exception sebagai 'retrieved',
            # mencegah warning "Future exception was never retrieved" jika tidak ada
            # coroutine lain yang sedang menunggu (misal tidak ada concurrent request).
            try:
                waiter.exception()
            except asyncio.InvalidStateError:
                pass
        raise


async def invalidate_session_token(old_token: str) -> None:
    """Hapus session token yang kadaluarsa dari state global.

    Dipanggil oleh ``glpi_gateway.py`` saat menerima HTTP 401 dari GLPI.
    Hanya menghapus token jika nilai token yang tersimpan masih sama dengan
    ``old_token`` — ini mencegah race condition di mana coroutine lain sudah
    memperbarui token sementara coroutine ini masih menangani 401.

    Args:
        old_token: Token yang diterima respons 401 (yang sekarang tidak valid).
    """
    global _session_token
    lock = _get_session_lock()
    async with lock:
        if _session_token == old_token:
            _session_token = None
            logger.info("Session token invalidated (was: %s...)", old_token[:8])


async def refresh_session_token(old_token: str) -> str:
    """Invalidate token lama lalu buat session baru.

    Fungsi convenience yang menggabungkan ``invalidate_session_token`` dan
    ``get_session_token``. Dipanggil oleh gateway setelah menerima HTTP 401.

    Args:
        old_token: Token yang expired.

    Returns:
        Session token baru yang valid.
    """
    await invalidate_session_token(old_token)
    new_token = await _init_session()
    global _session_token
    lock = _get_session_lock()
    async with lock:
        # Hanya set jika belum ada yang lebih dulu mengisinya (race condition guard).
        if not _session_token:
            _session_token = new_token
        else:
            # Coroutine lain sudah refresh duluan — pakai token mereka.
            new_token = _session_token
    return new_token