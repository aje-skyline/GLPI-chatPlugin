"""Repository layer — Supplier.

Menyediakan akses data ke endpoint GLPI Supplier:
  GET /Supplier             → fetch_suppliers()
  GET /search/Supplier      → search_suppliers(), count_suppliers()

OPTIMASI (menggantikan strategi N+1 lama):
  Sebelumnya: 1 search call untuk ID + N individual calls via GET /Supplier/{id}
  Sekarang  : 1 search call dengan forcedisplay lengkap → semua field dalam
              satu response. Untuk 50 supplier: dari ~51 calls → 1 call.

Field ID GLPI 10.x untuk tabel Supplier (verifikasi via GET /listSearchOptions/Supplier):
  1  = name
  2  = id
  4  = phonenumber
  5  = fax
  6  = email
  8  = is_active
  16 = comment
  19 = address
  20 = postcode
  21 = town
  22 = state
  23 = country
  80 = entities_id  (dengan expand_dropdowns=true → nama entity)

Semua fungsi di sini MURNI mengembalikan struktur data Python (dict / list /
PagedResult). Tidak ada formatting teks untuk LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.cache import cache_get, cache_set
from app.infrastructure import glpi_get
from app.repository._glpi_helpers import clean_value
from app.repository.pagination import PagedResult, extract_data

logger = logging.getLogger(__name__)

# ── Konstanta ─────────────────────────────────────────────────────────────────

# Field ID untuk /search/Supplier yang digunakan pada forcedisplay[] DAN
# criteria[]. Sumber: GLPI 10.x standard field mapping (verified).
# Verifikasi via: GET /listSearchOptions/Supplier
_SUPPLIER_FIELD_IDS: dict[str, int] = {
    "id":       2,    # ID
    "name":     1,    # Name
    "entity":   80,   # Entity
    "phone":    5,    # Phone
    "fax":      10,   # Fax
    "email":    6,    # Email
    "address":  3,    # Address
    "postcode": 14,   # Postal code
    "town":     11,   # City
    "state":    12,   # State
    "country":  13,   # Country
}

# Field yang digunakan sebagai criteria filter (subset dari _SUPPLIER_FIELD_IDS)
_SUPPLIER_FILTER_FIELD_IDS: dict[str, int] = {
    "name":    _SUPPLIER_FIELD_IDS["name"],
    "entity":  _SUPPLIER_FIELD_IDS["entity"],
    "address": _SUPPLIER_FIELD_IDS["address"],
    "phone":   _SUPPLIER_FIELD_IDS["phone"],
    "fax":     _SUPPLIER_FIELD_IDS["fax"],
    "email":   _SUPPLIER_FIELD_IDS["email"],
}

# forcedisplay lengkap — semua field yang kita butuhkan dalam satu request.
# Ini adalah kunci optimasi: tidak perlu GET /Supplier/{id} lagi.
_SUPPLIER_FORCEDISPLAY: dict[str, int] = {
    f"forcedisplay[{i}]": field_id
    for i, field_id in enumerate([
        _SUPPLIER_FIELD_IDS["id"],       # forcedisplay[0] = 2  (id)
        _SUPPLIER_FIELD_IDS["name"],     # forcedisplay[1] = 1  (name)
        _SUPPLIER_FIELD_IDS["entity"],   # forcedisplay[2] = 80 (entities_id)
        _SUPPLIER_FIELD_IDS["phone"],    # forcedisplay[3] = 4  (phonenumber)
        _SUPPLIER_FIELD_IDS["fax"],      # forcedisplay[4] = 5  (fax)
        _SUPPLIER_FIELD_IDS["email"],    # forcedisplay[5] = 6  (email)
        _SUPPLIER_FIELD_IDS["address"],  # forcedisplay[6] = 19 (address)
        _SUPPLIER_FIELD_IDS["postcode"], # forcedisplay[7] = 20 (postcode)
        _SUPPLIER_FIELD_IDS["town"],     # forcedisplay[8] = 21 (town)
        _SUPPLIER_FIELD_IDS["state"],    # forcedisplay[9] = 22 (state)
        _SUPPLIER_FIELD_IDS["country"],  # forcedisplay[10]= 23 (country)
    ])
}


# ── Private helpers ───────────────────────────────────────────────────────────

def _parse_search_row(row: dict[str, Any]) -> dict[str, Any]:
    """Parse satu baris dari Search API response ke format standar supplier.

    Search API mengembalikan field dengan kunci numerik string (misal: "1",
    "4", "80") sesuai field ID yang di-request via forcedisplay[].

    Komponen alamat (address, postcode, town, state, country) digabungkan
    menjadi satu string `address` yang lengkap dan mudah dibaca.

    Args:
        row: Satu item dict dari data[] dalam Search API response.
             Kunci adalah string field ID ("1", "2", "4", dst).

    Returns:
        Dict standar: id, name, entity, address, phone, fax, email.
    """
    fid = _SUPPLIER_FIELD_IDS  # alias pendek

    def get(field_name: str) -> str:
        """Ambil nilai field dari row, return string kosong jika tidak ada."""
        raw = row.get(str(fid[field_name]), "")
        if raw is None:
            return ""
        cleaned = clean_value(raw)
        return str(cleaned) if cleaned not in ("", None) else ""

    # Gabungkan komponen alamat menjadi satu string
    addr_parts = [
        get("address"),
        get("postcode"),
        get("town"),
        get("state"),
        get("country"),
    ]
    address = ", ".join(p.strip() for p in addr_parts if p and p.strip())

    return {
        "id":      get("id")     or row.get("id", ""),
        "name":    get("name")   or "",
        "entity":  get("entity") or "",
        "address": address       or "",
        "phone":   get("phone")  or "",
        "fax":     get("fax")    or "",
        "email":   get("email")  or "",
    }


def _build_search_params(
    active_filters: list[tuple[str, str]],
    limit: int,
) -> dict[str, Any]:
    """Bangun parameter lengkap untuk GET /search/Supplier.

    Menggabungkan forcedisplay lengkap, sorting, expand_dropdowns,
    range pagination, dan criteria filter menjadi satu dict params.

    Args:
        active_filters: List tuple (field_name, value) dari filter aktif.
        limit         : Jumlah record yang diminta (untuk range parameter).

    Returns:
        Dict params siap pakai untuk glpi_get().
    """
    params: dict[str, Any] = {
        "expand_dropdowns": "true",   # Konversi ID → nama (entity, dll)
        "sort":             2,        # Sort by ID
        "order":            "DESC",   # Terbaru dulu
        "range":            f"0-{limit - 1}",
        **_SUPPLIER_FORCEDISPLAY,     # Semua field sekaligus
    }

    for idx, (field_name, value) in enumerate(active_filters):
        field_id = _SUPPLIER_FILTER_FIELD_IDS[field_name]
        params[f"criteria[{idx}][field]"]      = field_id
        params[f"criteria[{idx}][searchtype]"] = "contains"
        params[f"criteria[{idx}][value]"]      = value
        if idx > 0:
            params[f"criteria[{idx}][link]"] = "AND"

    return params


# ── Public functions ──────────────────────────────────────────────────────────

async def count_suppliers() -> int:
    """Hitung jumlah total supplier yang terdaftar di GLPI (exact count).

    Hanya 1 API call — sangat cepat. Digunakan untuk menjawab pertanyaan
    "ada berapa supplier?" tanpa fetch semua data.

    Returns:
        Integer jumlah total supplier, atau 0 jika gagal.
    """
    try:
        data = await glpi_get("/search/Supplier", params={"range": "0-1"})
        if isinstance(data, dict):
            return int(data.get("totalcount", 0))
        return 0
    except Exception as exc:
        logger.warning("count_suppliers failed: %s", exc)
        return 0


async def search_suppliers(
    name:    str | None = None,
    entity:  str | None = None,
    address: str | None = None,
    phone:   str | None = None,
    fax:     str | None = None,
    email:   str | None = None,
    limit:   int = 50,
) -> PagedResult:
    """Cari supplier di GLPI dengan filter dinamis — SATU API call.

    Menggunakan forcedisplay lengkap sehingga semua field detail (nama, entity,
    alamat, telepon, fax, email) tersedia langsung dari Search API response
    tanpa perlu GET /Supplier/{id} per item.

    Performa: O(1) API calls terlepas dari jumlah supplier (vs O(N) sebelumnya).
    Untuk 50 supplier: sebelumnya ~51 calls, sekarang 1 call.

    Args:
        name   : Filter nama supplier (partial match, contains).
        entity : Filter entity GLPI (partial match, contains).
        address: Filter alamat (partial match, contains).
        phone  : Filter nomor telepon (partial match, contains).
        fax    : Filter nomor fax (partial match, contains).
        email  : Filter email (partial match, contains).
        limit  : Jumlah maksimal hasil (default 50, max 100 per page GLPI).

    Returns:
        PagedResult dengan items (list supplier detail), totalcount exact,
        fetched, dan truncated flag.
    """
    # ── Bangun criteria dari filter aktif ─────────────────────────────────────
    filter_map: list[tuple[str, str | None]] = [
        ("name",    name),
        ("entity",  entity),
        ("address", address),
        ("phone",   phone),
        ("fax",     fax),
        ("email",   email),
    ]
    active_filters: list[tuple[str, str]] = [
        (field, str(val).strip())
        for field, val in filter_map
        if val and str(val).strip()
    ]

    logger.info(
        "search_suppliers: filters=%s limit=%d",
        [(n, v) for n, v in active_filters],
        limit,
    )

    # ── SATU API call dengan forcedisplay lengkap ─────────────────────────────
    params = _build_search_params(active_filters, limit)

    try:
        raw = await glpi_get("/search/Supplier", params=params)
    except Exception as exc:
        logger.error("search_suppliers: API call failed: %s", exc)
        return PagedResult(items=[], totalcount=0, fetched=0, truncated=False)

    # ── Parse response ────────────────────────────────────────────────────────
    totalcount: int = 0
    if isinstance(raw, dict):
        totalcount = int(raw.get("totalcount", 0))

    raw_items = extract_data(raw)
    parsed_items = [
        _parse_search_row(item)
        for item in raw_items
        if isinstance(item, dict)
    ]

    fetched   = len(parsed_items)
    truncated = totalcount > fetched

    logger.info(
        "search_suppliers: DONE totalcount=%d fetched=%d truncated=%s "
        "(1 API call, no N+1)",
        totalcount, fetched, truncated,
    )

    return PagedResult(
        items=parsed_items,
        totalcount=totalcount or fetched,
        fetched=fetched,
        truncated=truncated,
    )


async def fetch_suppliers(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch daftar supplier/vendor (backward-compatible wrapper).

    Memanggil search_suppliers() tanpa filter, dengan caching ringan
    agar panggilan berulang tidak mengakibatkan request redundan ke GLPI.

    Untuk pencarian dengan filter, panggil search_suppliers() langsung.

    Args:
        limit: Jumlah maksimal supplier yang dikembalikan.

    Returns:
        List dict supplier dengan field: id, name, entity, address, phone, fax, email.
    """
    cache_key = f"suppliers_all:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        result = await search_suppliers(limit=limit)
        items = result["items"]
        cache_set(cache_key, items)
        return items
    except Exception as exc:
        logger.warning("fetch_suppliers failed: %s", exc)
        return []