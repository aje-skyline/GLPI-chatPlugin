"""Async runner — GLPI AI Gateway.

Menyediakan satu persistent background event loop yang berjalan di thread
terpisah, sehingga tool CrewAI (yang dipanggil secara synchronous oleh
agent ReAct) dapat menjalankan coroutine async GLPI client tanpa bentrok
dengan event loop FastAPI/uvicorn.

Mengapa arsitektur ini diperlukan
──────────────────────────────────
CrewAI memanggil method ``_run()`` dari setiap ``BaseTool`` secara synchronous
di dalam thread pool miliknya. FastAPI/uvicorn sudah menguasai event loop
utama di main thread. Jika tool mencoba ``asyncio.run()`` baru, Python akan
menolak dengan "cannot run nested event loop". Jika tool mencoba
``asyncio.get_event_loop().run_until_complete()``, itu akan gagal karena
loop uvicorn sedang berjalan.

Solusi: satu background thread dengan event loop-nya sendiri, dimulai sekali
saat modul pertama kali diimpor. Tool kemudian menyerahkan coroutine ke loop
ini via ``asyncio.run_coroutine_threadsafe()`` dan menunggu hasilnya secara
blocking dengan timeout yang aman.

Thread ini bersifat daemon sehingga tidak menghalangi proses Python keluar.

Catatan penting tentang Lock asyncio
──────────────────────────────────────
Semua ``asyncio.Lock`` di modul repository / infra HARUS dibuat secara lazy
(pertama kali dipakai), bukan di module-level. Lock asyncio terikat ke event
loop yang sedang berjalan saat dibuat. Jika dibuat di module-level (saat
import), mereka terikat ke event loop yang berbeda dari background loop ini
dan akan memicu "got Future <Future pending> attached to a different loop".
"""

import asyncio
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Singleton state ───────────────────────────────────────────────────────────

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()

# Timeout default untuk setiap coroutine yang diserahkan ke background loop.
# 60 detik dipilih karena query dengan auto-pagination bisa memakan 20-40 detik
# pada GLPI dengan data besar. Nilai ini bisa di-override per-call.
DEFAULT_ASYNC_TIMEOUT: float = 60.0


# ── Private helpers ───────────────────────────────────────────────────────────

def _start_background_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Target fungsi thread: set event loop lalu jalankan selamanya (run_forever).

    ``asyncio.set_event_loop`` diperlukan agar semua coroutine yang
    dijadwalkan di loop ini mendapatkan referensi loop yang benar via
    ``asyncio.get_event_loop()`` di dalam thread tersebut.
    """
    asyncio.set_event_loop(loop)
    loop.run_forever()


# ── Public API ────────────────────────────────────────────────────────────────

def get_loop() -> asyncio.AbstractEventLoop:
    """Kembalikan background event loop, membuat dan memulainya sekali jika belum ada.

    Thread-safe via double-checked locking. Setelah loop berjalan, fungsi ini
    hanya membaca variabel global tanpa mengambil lock sehingga overhead-nya
    minimal di setiap call.

    Returns:
        Event loop yang sedang berjalan di background thread.

    Raises:
        RuntimeError: Jika background loop gagal start dalam 2 detik.
    """
    global _loop, _loop_thread

    # Fast path: loop sudah ada dan berjalan — langsung return tanpa lock.
    if _loop is not None and _loop.is_running():
        return _loop

    with _loop_lock:
        # Double-check setelah mendapat lock (thread lain mungkin sudah membuat).
        if _loop is not None and _loop.is_running():
            return _loop

        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=_start_background_loop,
            args=(loop,),
            daemon=True,
            name="glpi-async-loop",
        )
        thread.start()

        # Tunggu sampai loop benar-benar running (biasanya < 5ms).
        deadline = time.monotonic() + 2.0
        while not loop.is_running():
            time.sleep(0.005)
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "GLPI background async event loop gagal start dalam 2 detik. "
                    "Periksa apakah ada error di thread daemon."
                )

        _loop = loop
        _loop_thread = thread
        logger.info(
            "GLPI background async loop started (thread='%s', loop_id=%s)",
            thread.name,
            id(loop),
        )

    return _loop


def run_async(coro: Any, timeout: float = DEFAULT_ASYNC_TIMEOUT) -> Any:
    """Jalankan coroutine di background loop dan tunggu hasilnya secara blocking.

    Dipanggil dari dalam method ``_run()`` (synchronous) di setiap BaseTool.
    Thread yang memanggil fungsi ini akan diblokir sampai coroutine selesai
    atau timeout tercapai.

    Args:
        coro   : Coroutine object yang ingin dijalankan (hasil dari ``async_fn()``).
        timeout: Waktu tunggu maksimum dalam detik. Default ``DEFAULT_ASYNC_TIMEOUT``.

    Returns:
        Nilai yang dikembalikan oleh coroutine.

    Raises:
        TimeoutError: Jika coroutine tidak selesai dalam ``timeout`` detik.
                      Future akan di-cancel agar tidak menumpuk di loop.
        Exception   : Exception apapun yang di-raise oleh coroutine akan
                      di-propagate ke caller setelah di-unwrap dari Future.

    Example:
        >>> from app.infrastructure.async_runner import run_async
        >>> from app.repository.asset_repository import get_all_computers
        >>> result = run_async(get_all_computers(sample_size=20))
    """
    loop = get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        logger.error(
            "run_async: coroutine timed out setelah %.1fs — future di-cancel",
            timeout,
        )
        raise TimeoutError(
            f"GLPI async call tidak selesai dalam {timeout:.0f} detik. "
            "Periksa konektivitas ke GLPI atau kurangi jumlah data yang di-fetch."
        )


def is_loop_running() -> bool:
    """Periksa apakah background loop sedang berjalan (berguna untuk health check).

    Returns:
        ``True`` jika loop ada dan sedang running, ``False`` sebaliknya.
    """
    return _loop is not None and _loop.is_running()