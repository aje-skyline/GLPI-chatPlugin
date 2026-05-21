"""Repository layer — Utility.

Menyediakan akses ke endpoint GLPI utilitas umum:
  GET /getMultipleItems         → get_multiple_items()
  GET /listSearchOptions/{type} → list_search_options()   (dengan cache)

Cache diterapkan pada list_search_options karena data search options
bersifat statis dan jarang berubah antar request.

Semua fungsi di sini MURNI mengembalikan struktur data Python (dict / list).
Tidak ada formatting teks untuk LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.cache import cache_get, cache_set
from app.infrastructure import glpi_get
from app.repository.pagination import extract_data

logger = logging.getLogger(__name__)


async def get_multiple_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch beberapa item GLPI sekaligus dalam satu request.

    Setiap elemen dalam `items` harus berisi:
      - ``itemtype``: Tipe item GLPI (e.g. "Computer", "Supplier").
      - ``items_id`` : ID item yang ingin di-fetch.

    Endpoint: GET /getMultipleItems

    Args:
        items: List dict dengan key ``itemtype`` dan ``items_id``.

    Returns:
        List dict item GLPI yang berhasil di-fetch.
        List kosong jika terjadi error atau tidak ada item yang valid.
    """
    try:
        params: dict[str, Any] = {}
        for idx, item in enumerate(items):
            params[f"items[{idx}][itemtype]"] = item["itemtype"]
            params[f"items[{idx}][items_id]"] = item["items_id"]

        data = await glpi_get("/getMultipleItems", params={
            **params,
            "expand_dropdowns": "true",
        })
        result: list[Any] = extract_data(data)
        return [item for item in result if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("get_multiple_items failed: %s", exc)
        return []


async def list_search_options(itemtype: str) -> dict[str, Any]:
    """List field (search options) yang tersedia untuk suatu item type.

    Hasil di-cache karena search options GLPI sangat jarang berubah
    (hanya berubah saat update GLPI atau instalasi plugin baru).

    Endpoint: GET /listSearchOptions/{itemtype}

    Berguna untuk mendebug field ID yang benar pada Search API,
    misalnya memverifikasi field ID Supplier sebelum digunakan pada criteria[].

    Args:
        itemtype: Nama tipe item GLPI (e.g. "Computer", "Supplier", "Ticket").

    Returns:
        Dict berisi mapping field ID → definisi field (name, table, field, dll).
        Dict kosong jika terjadi error.
    """
    cache_key = f"searchopts:{itemtype}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        data = await glpi_get(f"/listSearchOptions/{itemtype}")
        result: dict[str, Any] = data if isinstance(data, dict) else {}
        cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("list_search_options failed (itemtype=%s): %s", itemtype, exc)
        return {}