"""Pagination helpers — GLPI AI Gateway repository layer.

Menyediakan ``PagedResult`` TypedDict dan fungsi ``get_all_pages()`` yang
digunakan oleh semua repository untuk mengambil data berpaginasi dari
GLPI Search API secara otomatis.

Mengapa pagination perlu di-abstraksi
───────────────────────────────────────
GLPI Search API mengembalikan data dalam "halaman" (range parameter).
Jika total data lebih besar dari satu halaman, repository harus membuat
beberapa request untuk mengumpulkan semua data. Logika ini identik untuk
setiap endpoint (Computer, Supplier, Ticket, dll) sehingga layak
dijadikan shared utility.

Strategi dua-fase get_all_pages()
───────────────────────────────────
  Fase 1 — Probe: ambil halaman pertama (``sample_size`` record) untuk
  mendapatkan ``totalcount`` yang akurat dari GLPI (tersedia di response
  body). Ini adalah sumber kebenaran jumlah exact — lebih akurat daripada
  menghitung panjang list.

  Fase 2 — Pagination: jika ``totalcount > sample_size``, ambil halaman
  berikutnya sampai semua data terkumpul atau mencapai ``max_total``.

Token-aware: jika ``totalcount`` sangat besar (> ``max_total``), fungsi
berhenti setelah ``max_total`` record dan men-set ``truncated=True``.
Repository yang memanggil bertanggung jawab menyampaikan flag ini ke LLM.
"""

import logging
from typing import Any, TypedDict

from app.infrastructure import glpi_get

logger = logging.getLogger(__name__)

# ── Konstanta pagination ──────────────────────────────────────────────────────

GLPI_MAX_PAGE_SIZE: int = 100
"""Jumlah record maksimum per request ke GLPI Search API.

Nilai 100 adalah nilai konservatif yang didukung hampir semua versi dan
konfigurasi GLPI tanpa modifikasi server. Naikkan ke 200-500 hanya jika
server GLPI Anda sudah dikonfigurasi untuk mendukung range besar.
"""

GLPI_AUTO_PAGINATE_LIMIT: int = 20_000
"""Batas total record yang akan di-fetch melalui auto-pagination.

Di luar batas ini, hanya data yang sudah ter-fetch yang dikembalikan
(dengan ``truncated=True``). Ini melindungi context window LLM dari
overflow ketika GLPI menyimpan puluhan ribu record.
"""


# ── TypedDict ─────────────────────────────────────────────────────────────────

class PagedResult(TypedDict):
    """Hasil pagination dari GLPI Search API.

    Attributes:
        items     : List item yang sudah di-fetch. Bisa berupa subset dari
                    total jika ``truncated=True``.
        totalcount: Jumlah exact item di GLPI (dari header/body API).
                    Selalu akurat — bahkan saat data di-truncate, angka ini
                    mencerminkan jumlah sebenarnya di database.
        fetched   : Jumlah item yang benar-benar ada di ``items`` (len(items)).
                    Selalu ≤ totalcount.
        truncated : ``True`` jika ``totalcount > fetched`` — artinya tidak
                    semua data diambil karena batas ``max_total`` atau error
                    saat pagination.
    """

    items: list[dict[str, Any]]
    totalcount: int
    fetched: int
    truncated: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_data(data: dict[str, Any] | list[Any]) -> list[Any]:
    """Unwrap GLPI Search API response envelope atau pass-through list.

    GLPI Search API membungkus hasil dalam ``{"data": [...], "totalcount": N}``.
    Endpoint non-search (misal GET /Computer) mengembalikan list langsung.
    Fungsi ini menangani kedua format sekaligus.

    Args:
        data: Response JSON mentah dari ``glpi_get()``.

    Returns:
        List item tanpa envelope. List kosong jika data tidak dikenali.
    """
    if isinstance(data, dict) and "data" in data:
        return data["data"]  # type: ignore[return-value]
    if isinstance(data, list):
        return data
    return []


# ── Public API ────────────────────────────────────────────────────────────────

async def get_all_pages(
    path: str,
    base_params: dict[str, Any],
    sample_size: int = 50,
    max_total: int = GLPI_AUTO_PAGINATE_LIMIT,
    page_size: int = GLPI_MAX_PAGE_SIZE,
) -> PagedResult:
    """Ambil semua halaman dari GLPI Search API secara otomatis.

    Digunakan oleh repository yang membutuhkan data berjumlah besar
    tanpa harus mengimplementasikan loop pagination di setiap fungsi.

    Args:
        path       : URL path GLPI Search API, misal ``"/search/Computer"``.
        base_params: Parameter dasar tanpa ``range`` (akan di-override per halaman).
                     Biasanya berisi ``expand_dropdowns``, ``criteria[]``, dan
                     ``forcedisplay[]``.
        sample_size: Jumlah record yang diambil di halaman pertama (probe).
                     Default 50 — cukup untuk sample tapi tidak terlalu besar.
        max_total  : Batas maksimum record yang di-fetch via pagination.
                     Default ``GLPI_AUTO_PAGINATE_LIMIT`` (20.000).
        page_size  : Jumlah record per halaman setelah probe.
                     Default ``GLPI_MAX_PAGE_SIZE`` (100).

    Returns:
        ``PagedResult`` dengan:
          - ``items``: semua item yang berhasil di-fetch (sudah di-flatten).
          - ``totalcount``: jumlah exact dari GLPI (dari probe response).
          - ``fetched``: panjang ``items`` (mungkin < totalcount jika truncated).
          - ``truncated``: ``True`` jika data dipotong karena batas atau error.

    Raises:
        Tidak me-raise exception — error pagination di-log dan dihentikan
        secara graceful (``truncated=True``, data yang sudah ada dikembalikan).
        Exception dari probe (halaman pertama) di-propagate ke caller.
    """
    # ── Fase 1: Probe — ambil halaman pertama + dapatkan totalcount ───────────
    probe_params = {**base_params, "range": f"0-{sample_size - 1}"}
    probe_data = await glpi_get(path, params=probe_params)

    totalcount: int = 0
    if isinstance(probe_data, dict):
        totalcount = int(probe_data.get("totalcount", 0))

    first_page_items = extract_data(probe_data)
    items: list[dict[str, Any]] = [
        item for item in first_page_items if isinstance(item, dict)
    ]

    logger.info(
        "get_all_pages: path=%s totalcount=%d fetched_first=%d",
        path, totalcount, len(items),
    )

    # Jika totalcount <= sample_size, semua data sudah ada di halaman pertama.
    if totalcount <= sample_size or len(items) >= totalcount:
        return PagedResult(
            items=items,
            totalcount=totalcount or len(items),
            fetched=len(items),
            truncated=False,
        )

    # ── Fase 2: Pagination — ambil halaman berikutnya ─────────────────────────
    fetch_target = min(totalcount, max_total)
    start = sample_size  # Lanjut dari setelah probe

    while len(items) < fetch_target:
        end = min(start + page_size - 1, fetch_target - 1)
        page_params = {**base_params, "range": f"{start}-{end}"}

        try:
            page_data = await glpi_get(path, params=page_params)
            page_items = [
                item for item in extract_data(page_data)
                if isinstance(item, dict)
            ]
        except Exception as exc:
            logger.warning(
                "get_all_pages: error fetching range %d-%d pada path=%s: %s "
                "— pagination dihentikan, data yang ada dikembalikan",
                start, end, path, exc,
            )
            break

        if not page_items:
            # Server tidak mengembalikan data lagi — hentikan pagination.
            break

        items.extend(page_items)
        logger.debug(
            "get_all_pages: fetched range %d-%d, total_so_far=%d",
            start, end, len(items),
        )

        start = end + 1
        if start >= fetch_target:
            break

    truncated = len(items) < totalcount
    logger.info(
        "get_all_pages: DONE path=%s totalcount=%d fetched=%d truncated=%s",
        path, totalcount, len(items), truncated,
    )
    return PagedResult(
        items=items,
        totalcount=totalcount,
        fetched=len(items),
        truncated=truncated,
    )