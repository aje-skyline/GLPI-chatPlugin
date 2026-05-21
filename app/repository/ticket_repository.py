"""Repository layer — Ticket, User, ITIL Category, dan Knowledge Base.

Menyediakan akses data ke endpoint GLPI berikut:
  GET /search/Ticket   → fetch_user_tickets()
  GET /User/{id}       → fetch_user_info()
  GET /ITILCategory    → fetch_itil_categories()   (dengan cache)
  GET /KnowbaseItem    → fetch_knowbase_items()     (dengan cache)

Cache diterapkan pada data statis (kategori ITIL dan Knowledge Base)
untuk mengurangi beban request ke GLPI.

Semua fungsi di sini MURNI mengembalikan struktur data Python (dict / list).
Tidak ada formatting teks untuk LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.cache import cache_get, cache_set
from app.infrastructure import glpi_get
from app.repository._glpi_helpers import first_of, strip_html
from app.repository.pagination import extract_data

logger = logging.getLogger(__name__)

# ── Status ticket label map ───────────────────────────────────────────────────

_STATUS_MAP: dict[int, str] = {
    1: "Baru",
    2: "Dalam Proses (Assigned)",
    3: "Dalam Proses (Planned)",
    4: "Menunggu",
    5: "Selesai",
    6: "Ditutup",
}


def _ticket_status_label(status: Any) -> str:
    """Konversi status tiket numerik GLPI ke label Bahasa Indonesia."""
    try:
        return _STATUS_MAP.get(int(status), f"Status {status}")
    except (TypeError, ValueError):
        return "Tidak diketahui"


# ── Public functions ──────────────────────────────────────────────────────────

async def fetch_user_tickets(
    glpi_user_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch tiket IT milik user dari GLPI.

    Mencoba tiga candidate field ID (4, 22, 64) secara berurutan untuk
    kompatibilitas antar versi GLPI. Berhenti pada candidate pertama yang
    mengembalikan hasil.

    Endpoint: GET /search/Ticket

    Args:
        glpi_user_id: GLPI User ID pemilik tiket.
        limit       : Jumlah maksimal tiket yang dikembalikan (default 20).

    Returns:
        List dict tiket dengan field: id, title, status, last_update, content.
        content dipotong maksimal 300 karakter dan sudah di-strip HTML.
    """

    def _parse_items(items: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "id":          first_of(item, "1", "id"),
                "title":       first_of(item, "2", "name"),
                "status":      _ticket_status_label(first_of(item, "12", "status")),
                "last_update": first_of(item, "15", "date_mod"),
                "content":     strip_html(first_of(item, "21", "content") or "")[:300],
            }
            for item in items if isinstance(item, dict)
        ]

    common_display: dict[str, Any] = {
        "range":           f"0-{limit - 1}",
        "sort":            15,
        "order":           "DESC",
        "forcedisplay[0]": 1,
        "forcedisplay[1]": 2,
        "forcedisplay[2]": 12,
        "forcedisplay[3]": 15,
        "forcedisplay[4]": 21,
    }

    for field_id in [4, 22, 64]:
        try:
            data = await glpi_get("/search/Ticket", params={
                "criteria[0][field]":      field_id,
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]":      glpi_user_id,
                **common_display,
            })
            items: list[Any] = extract_data(data)
            if items:
                logger.info(
                    "fetch_user_tickets: found %d tickets for user_id=%s (field=%s)",
                    len(items), glpi_user_id, field_id,
                )
                return _parse_items(items)
        except Exception as exc:
            logger.debug("fetch_user_tickets field=%s error: %s", field_id, exc)

    logger.warning("fetch_user_tickets: no tickets found for user_id=%s", glpi_user_id)
    return []


async def fetch_user_info(glpi_user_id: int) -> dict[str, Any] | None:
    """Fetch profil user dari GLPI.

    Endpoint: GET /User/{id}

    Args:
        glpi_user_id: GLPI User ID.

    Returns:
        Dict profil user dengan field: id, name, realname, firstname,
        login, email, groups.
        Mengembalikan None jika user tidak ditemukan atau terjadi error.
    """
    try:
        data = await glpi_get(f"/User/{glpi_user_id}")
        if not isinstance(data, dict):
            return None

        display_name = (
            data.get("realname", "").strip()
            or data.get("firstname", "").strip()
            or data.get("name", "")
        )
        return {
            "id":        data.get("id"),
            "name":      display_name,
            "realname":  data.get("realname", ""),
            "firstname": data.get("firstname", ""),
            "login":     data.get("name", ""),
            "email": (
                data.get("_useremails", [{}])[0].get("email", "")
                if data.get("_useremails") else ""
            ),
            "groups": [
                g.get("name", "") for g in data.get("_groups_id", [])
            ],
        }
    except Exception as exc:
        logger.warning("fetch_user_info failed: %s", exc)
        return None


async def fetch_itil_categories(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch kategori ITIL untuk pembuatan tiket.

    Hasil di-cache untuk menghindari request berulang ke GLPI karena
    data kategori ITIL bersifat relatif statis.

    Endpoint: GET /ITILCategory

    Args:
        limit: Jumlah maksimal kategori yang dikembalikan (default 20).

    Returns:
        List dict kategori dengan field: id, name, completename.
    """
    cache_key = f"itil_categories:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        data = await glpi_get("/ITILCategory", params={
            "expand_dropdowns": "true",
            "range":            f"0-{limit - 1}",
        })
        items: list[Any] = extract_data(data)
        result = [
            {
                "id":           item.get("1") or item.get("id"),
                "name":         item.get("2") or item.get("name", ""),
                "completename": item.get("16") or item.get("completename", ""),
            }
            for item in items if isinstance(item, dict)
        ]
        cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("fetch_itil_categories failed: %s", exc)
        return []


async def fetch_knowbase_items(
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Cari artikel Knowledge Base berdasarkan kata kunci.

    Hasil pencarian di-cache per kombinasi (query, limit) untuk menghindari
    request berulang dengan parameter yang sama.

    Endpoint: GET /KnowbaseItem

    Args:
        query: Kata kunci pencarian artikel.
        limit: Jumlah maksimal artikel yang dikembalikan (default 5).

    Returns:
        List dict artikel dengan field: id, title, answer.
        answer sudah di-strip dari tag HTML.
    """
    cache_key = f"kb:{query}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        data = await glpi_get("/KnowbaseItem", params={
            "search":           query,
            "range":            f"0-{limit - 1}",
            "expand_dropdowns": "true",
        })
        items: list[Any] = extract_data(data)
        result = [
            {
                "id":     item.get("id", ""),
                "title":  item.get("name", ""),
                "answer": strip_html(item.get("answer", "") or ""),
            }
            for item in items if isinstance(item, dict)
        ]
        cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("fetch_knowbase_items failed: %s", exc)
        return []