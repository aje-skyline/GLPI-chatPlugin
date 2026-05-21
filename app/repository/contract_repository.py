"""Repository layer — Contract.

Menyediakan akses data ke endpoint GLPI Contract:
  GET /Contract        → get_contracts()
  GET /Contract/{id}   → get_contract_by_id()

Semua fungsi di sini MURNI mengembalikan struktur data Python (dict / list).
Tidak ada formatting teks untuk LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.infrastructure import glpi_get
from app.repository._glpi_helpers import clean_value, strip_html
from app.repository.pagination import extract_data

logger = logging.getLogger(__name__)


async def get_contracts(
    computer_id: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch kontrak dari GLPI.

    Jika computer_id > 0, kembalikan kontrak yang terkait dengan komputer
    tersebut (diambil dari detail komputer via with_contracts=true).
    Jika computer_id == 0, fetch semua kontrak dari GET /Contract.

    Args:
        computer_id: ID komputer GLPI. Jika > 0, filter kontrak milik komputer ini.
        limit      : Jumlah maksimal kontrak yang dikembalikan (default 50).

    Returns:
        List dict kontrak dengan field: id, name, num, type, supplier,
        begin_date, duration, end_date, comment.
    """
    try:
        if computer_id > 0:
            # Import di sini untuk menghindari circular import antar repository
            from app.repository.asset_repository import get_computer_by_id
            computer = await get_computer_by_id(computer_id)
            if not computer:
                return []
            return computer.get("contracts", [])

        data = await glpi_get("/Contract", params={
            "expand_dropdowns": "true",
            "range": f"0-{limit - 1}",
        })
        items: list[Any] = extract_data(data)
        return [
            {
                "id":         item.get("id", ""),
                "name":       item.get("name", ""),
                "num":        item.get("num", ""),
                "type":       clean_value(item.get("contracttypes_id")),
                "supplier":   clean_value(item.get("suppliers_id")),
                "begin_date": item.get("begin_date", ""),
                "duration":   item.get("duration", ""),
                "end_date":   item.get("end_date", ""),
                "comment":    strip_html(item.get("comment", "") or ""),
            }
            for item in items if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.warning("get_contracts failed: %s", exc)
        return []


async def get_contract_by_id(contract_id: int) -> dict[str, Any] | None:
    """Fetch detail satu kontrak berdasarkan ID.

    Endpoint: GET /Contract/{id}?expand_dropdowns=true&with_items=true

    Args:
        contract_id: ID kontrak GLPI.

    Returns:
        Dict kontrak dengan field: id, name, num, type, supplier,
        begin_date, duration, end_date, comment.
        Mengembalikan None jika kontrak tidak ditemukan atau terjadi error.
    """
    try:
        data = await glpi_get(f"/Contract/{contract_id}", params={
            "expand_dropdowns": "true",
            "with_items":       "true",
        })
        if not isinstance(data, dict):
            return None
        return {
            "id":         data.get("id", ""),
            "name":       data.get("name", ""),
            "num":        data.get("num", ""),
            "type":       clean_value(data.get("contracttypes_id")),
            "supplier":   clean_value(data.get("suppliers_id")),
            "begin_date": data.get("begin_date", ""),
            "duration":   data.get("duration", ""),
            "end_date":   data.get("end_date", ""),
            "comment":    strip_html(data.get("comment", "") or ""),
        }
    except Exception as exc:
        logger.warning("get_contract_by_id failed (id=%s): %s", contract_id, exc)
        return None