"""Asset repository — GLPI AI Gateway repository layer.

Mengelola semua akses data terkait aset komputer dari GLPI REST API.
Satu-satunya modul yang boleh memanggil endpoint ``/Computer`` dan
``/search/Computer``.

Endpoint yang digunakan:
  GET /search/Computer          → get_all_computers(), get_computers_by_*(),
                                   search_computer(), search_computer_by_name()
  GET /Computer/{id}            → get_computer_by_id()
  GET /Computer                 → _get_all_computers_fallback()

Setiap fungsi mengambil data mentah dari GLPI via ``glpi_get()``, mem-parse
field-field yang relevan ke format dict standar, lalu mengembalikannya ke
caller (biasanya Tools layer). Tidak ada logika formatting string di sini.

CATATAN PEMELIHARAAN:
  Fungsi get_multiple_items() dan list_search_options() telah DIPINDAHKAN
  ke app.repository.utility_repository (DRY Principle — menghindari duplikasi).
  Jangan tambahkan kembali di sini. Gunakan utility_repository untuk keperluan
  multi-itemtype fetch dan discovery field GLPI.
"""

import logging
from typing import Any

from app.infrastructure import glpi_get
from app.repository._glpi_helpers import clean_value, first_of, strip_html
from app.repository.pagination import PagedResult, extract_data, get_all_pages

logger = logging.getLogger(__name__)

# ── Konstanta Search API ──────────────────────────────────────────────────────
# forcedisplay mapping untuk GET /search/Computer.
# Key = nama parameter GLPI, value = field ID numerik.
# Field ID ini spesifik untuk itemtype Computer di GLPI 10.x.
_COMPUTER_SEARCH_FORCEDISPLAY: dict[str, int] = {
    "forcedisplay[0]":  1,    # Name
    "forcedisplay[1]":  2,    # ID
    "forcedisplay[2]":  3,    # Location
    "forcedisplay[3]":  4,    # Type
    "forcedisplay[4]":  5,    # Serial Number
    "forcedisplay[5]":  6,    # Inventory Number (otherserial)
    "forcedisplay[6]":  14,   # Operating System
    "forcedisplay[7]":  19,   # Last Update
    "forcedisplay[8]":  23,   # Manufacturer
    "forcedisplay[9]":  31,   # Status
    "forcedisplay[10]": 40,   # Model
    "forcedisplay[11]": 80,   # Entity
    "forcedisplay[12]": 24,   # User (users_id)
}

_INFOCOM_WARRANTY_FIELD: int = 162
"""Field ID untuk tanggal garansi di GLPI Search API (Infocom)."""


# ── Internal parsers ──────────────────────────────────────────────────────────

def _parse_computer_search_item(item: dict[str, Any]) -> dict[str, Any]:
    """Parse satu item dari GLPI Search API response ke format dict standar.

    Field ID numerik ("1", "2", dst.) adalah konvensi GLPI Search API —
    berbeda dari nama field di endpoint detail (/Computer/{id}).

    Args:
        item: Satu element dari list ``data`` di GLPI Search API response.

    Returns:
        Dict dengan key bernama: id, name, serial, otherserial, type, model,
        status, location, user, entity, manufacturer, os, date_mod.
    """
    return {
        "id":           first_of(item, "2", "id"),
        "name":         first_of(item, "1", "name"),
        "serial":       first_of(item, "5", "serial"),
        "otherserial":  first_of(item, "6", "otherserial"),
        "type":         clean_value(first_of(item, "4", "computertypes_id", "type")),
        "model":        clean_value(first_of(item, "40", "computermodels_id", "model")),
        "status":       clean_value(first_of(item, "31", "states_id", "status")),
        "location":     clean_value(first_of(item, "3", "locations_id", "location")),
        "user":         clean_value(first_of(item, "24", "users_id", "user")),
        "entity":       clean_value(first_of(item, "80", "entities_id", "entity")),
        "manufacturer": clean_value(first_of(item, "23", "manufacturers_id", "manufacturer")),
        "os":           clean_value(first_of(item, "14", "operatingsystems_id", "os")),
        "date_mod":     first_of(item, "19", "date_mod"),
    }


# ── Fallback fetcher ──────────────────────────────────────────────────────────

async def _get_all_computers_fallback(
    sample_size: int,
    has_serial: bool,
) -> PagedResult:
    """Fallback ke GET /Computer jika Search API tidak mengembalikan data.

    Search API kadang mengembalikan data kosong pada GLPI versi lama atau
    dengan konfigurasi permission yang ketat. Endpoint /Computer lebih
    universal tapi tidak mendukung forcedisplay, jadi field yang tersedia
    bergantung pada konfigurasi default GLPI.

    Args:
        sample_size: Jumlah record yang diminta.
        has_serial : Jika True, filter hanya komputer yang memiliki serial number.

    Returns:
        PagedResult dengan data dari endpoint /Computer, atau kosong jika gagal.
    """
    try:
        data = await glpi_get("/Computer", params={
            "expand_dropdowns": "true",
            "range": f"0-{sample_size - 1}",
        })
        items = extract_data(data)
        result = [
            {
                "id":           item.get("id", ""),
                "name":         item.get("name", ""),
                "serial":       item.get("serial", ""),
                "otherserial":  item.get("otherserial", ""),
                "type":         clean_value(item.get("computertypes_id")),
                "model":        clean_value(item.get("computermodels_id")) or clean_value(item.get("model")),
                "status":       clean_value(item.get("states_id")) or clean_value(item.get("status")),
                "location":     clean_value(item.get("locations_id")) or clean_value(item.get("location")),
                "user":         clean_value(item.get("users_id")) or clean_value(item.get("user")),
                "entity":       clean_value(item.get("entities_id")),
                "manufacturer": clean_value(item.get("manufacturers_id")),
                "os":           clean_value(item.get("operatingsystems_id")),
                "date_mod":     item.get("date_mod", ""),
            }
            for item in items if isinstance(item, dict)
        ]
        if has_serial:
            result = [c for c in result if c.get("serial", "").strip()]

        return PagedResult(
            items=result,
            totalcount=len(result),
            fetched=len(result),
            truncated=False,
        )
    except Exception as exc:
        logger.warning("_get_all_computers_fallback failed: %s", exc)
        return PagedResult(items=[], totalcount=0, fetched=0, truncated=False)


# ── Public API ────────────────────────────────────────────────────────────────

async def get_all_computers(
    sample_size: int = 50,
    has_serial: bool = False,
    paginate: bool = True,
) -> PagedResult:
    """Fetch semua komputer di GLPI dengan dukungan auto-pagination.

    Menggunakan GLPI Search API (``/search/Computer``) sebagai primary strategy
    karena mendukung ``forcedisplay`` dan ``totalcount``. Jika Search API gagal
    atau mengembalikan data kosong, fallback ke endpoint ``/Computer``.

    Args:
        sample_size: Jumlah komputer di halaman pertama / mode non-paginate.
                     Default 50.
        has_serial : Jika ``True``, filter hanya komputer yang memiliki
                     serial number tidak kosong. Default ``False``.
        paginate   : Jika ``True``, gunakan auto-pagination (ambil semua halaman
                     sampai ``GLPI_AUTO_PAGINATE_LIMIT``). Jika ``False``,
                     hanya ambil ``sample_size`` record dalam satu request.
                     Default ``True``.

    Returns:
        ``PagedResult`` dengan items (list komputer ter-parse), totalcount,
        fetched, dan truncated flag.
    """
    base_params: dict[str, Any] = {
        "is_recursive": "true",
        "expand_dropdowns": "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }

    if has_serial:
        base_params["criteria[0][field]"] = 5
        base_params["criteria[0][searchtype]"] = "isnotempty"

    try:
        if paginate:
            result = await get_all_pages(
                "/search/Computer",
                base_params=base_params,
                sample_size=sample_size,
            )
        else:
            probe_params = {**base_params, "range": f"0-{sample_size - 1}"}
            raw = await glpi_get("/search/Computer", params=probe_params)
            totalcount = int(raw.get("totalcount", 0)) if isinstance(raw, dict) else 0
            items = [item for item in extract_data(raw) if isinstance(item, dict)]
            result = PagedResult(
                items=items,
                totalcount=totalcount or len(items),
                fetched=len(items),
                truncated=(totalcount > len(items)),
            )

        parsed_items = [_parse_computer_search_item(item) for item in result["items"]]

        if not parsed_items:
            return await _get_all_computers_fallback(sample_size, has_serial)

        return PagedResult(
            items=parsed_items,
            totalcount=result["totalcount"],
            fetched=len(parsed_items),
            truncated=result["truncated"],
        )

    except Exception as exc:
        logger.warning("get_all_computers (Search API) failed: %s — falling back", exc)
        return await _get_all_computers_fallback(sample_size, has_serial)



async def get_total_all_assets_count() -> int:
    """Fetch jumlah total SELURUH aset di GLPI (AllAssets endpoint).

    Termasuk Computer, Monitor, Printer, Peripheral, NetworkEquipment, dsb.
    
    Returns:
        Integer jumlah total keseluruhan aset, atau 0 jika gagal.
    """
    try:
        data = await glpi_get("/search/AllAssets", params={
            "countonly": "true",
            "is_recursive": "true",
        })
        if isinstance(data, dict) and "totalcount" in data:
            return int(data["totalcount"])
        return 0
    except Exception as exc:
        logger.warning("get_total_all_assets_count failed: %s", exc)
        return 0

async def get_total_computers_count() -> int:
    """Fetch jumlah total komputer di GLPI (exact count, 1 API call).

    Dipertahankan untuk backward-compatibility dengan CountAllComputersTool.
    Untuk penggunaan baru, gunakan ``totalcount`` dari hasil ``get_all_computers()``.

    Returns:
        Integer jumlah total komputer, atau 0 jika gagal.
    """
    try:
        data = await glpi_get("/search/Computer", params={
            "countonly": "true",
            "is_recursive": "true",
        })
        if isinstance(data, dict) and "totalcount" in data:
            return int(data["totalcount"])
        return 0
    except Exception as exc:
        logger.warning("get_total_computers_count failed: %s", exc)
        return 0


async def get_computer_by_id(computer_id: int) -> dict[str, Any] | None:
    """Fetch satu komputer dengan data lengkap: finansial, kontrak, OS, dan dokumen.

    Menggunakan endpoint ``GET /Computer/{id}`` dengan semua parameter ekspansi:
    ``with_infocoms``, ``with_contracts``, ``with_operatingsystems``,
    ``with_documents``, dan ``expand_dropdowns``.

    OS: strategi cascade — coba ``operatingsystems_id`` (sudah di-expand),
    lalu ``_operatingsystems[0].name``, lalu ``_operatingsystems[0].operatingsystems_id``.

    Args:
        computer_id: GLPI Computer ID (integer).

    Returns:
        Dict komputer lengkap dengan semua field detail, atau ``None`` jika
        tidak ditemukan atau terjadi error.
    """
    try:
        data = await glpi_get(f"/Computer/{computer_id}", params={
            "expand_dropdowns":      "true",
            "with_infocoms":         "true",
            "with_contracts":        "true",
            "with_operatingsystems": "true",
            "with_documents":        "true",
        })
        if not isinstance(data, dict):
            return None

        infocoms: dict[str, Any] = data.get("_infocoms") or {}

        # ── OS: cascade dari beberapa sumber ──────────────────────────────────
        # expand_dropdowns=true menggantikan ID dengan nama string di field *_id.
        # Jika hasilnya masih angka (versi GLPI lama), fallback ke _operatingsystems.
        os_name: str = clean_value(data.get("operatingsystems_id"))
        os_version: str = ""
        os_arch: str = ""

        os_list: list[Any] = data.get("_operatingsystems") or []
        if os_list and isinstance(os_list[0], dict):
            os_item = os_list[0]
            if not os_name:
                os_name = clean_value(
                    os_item.get("operatingsystems_id")
                    or os_item.get("name", "")
                )
            os_version = clean_value(
                os_item.get("operatingsystemversions_id")
                or os_item.get("version", "")
            )
            os_arch = clean_value(
                os_item.get("operatingsystemarchitectures_id")
                or os_item.get("arch", "")
            )

        os_display = os_name
        if os_version:
            os_display = f"{os_name} {os_version}".strip()
        if os_arch:
            os_display = f"{os_display} ({os_arch})".strip()

        # ── Dokumen terlampir ─────────────────────────────────────────────────
        documents: list[Any] = data.get("_documents") or []
        doc_count: int = len(documents) if isinstance(documents, list) else 0

        return {
            "id":           data.get("id", ""),
            "name":         data.get("name", ""),
            "entity":       clean_value(data.get("entities_id")),
            "serial":       data.get("serial", ""),
            "otherserial":  data.get("otherserial", ""),
            "location":     clean_value(data.get("locations_id")),
            "type":         clean_value(data.get("computertypes_id")),
            "model":        clean_value(data.get("computermodels_id")),
            "manufacturer": clean_value(data.get("manufacturers_id")),
            "contact_num":  data.get("contact_num", ""),
            "contact":      data.get("contact", ""),
            "os":           os_display,
            "os_name":      os_name,
            "os_version":   os_version,
            "os_arch":      os_arch,
            "status":       clean_value(data.get("states_id")),
            "user":         clean_value(data.get("users_id")),
            "comment":      strip_html(data.get("comment", "") or ""),
            "doc_count":    doc_count,
            "date_mod":     data.get("date_mod", ""),
            # ── Infocom (Financial & Administrative) ─────────────────────────
            "buy_date":          infocoms.get("buy_date", ""),
            "use_date":          infocoms.get("use_date", ""),
            "warranty_duration": infocoms.get("warranty_duration", ""),
            "warranty_date":     infocoms.get("warranty_date", ""),
            "value":             infocoms.get("value", ""),
            "supplier":          clean_value(infocoms.get("suppliers_id", "")),
            # ── Kontrak terkait ───────────────────────────────────────────────
            "contracts": [
                {
                    "id":         c.get("id", ""),
                    "name":       c.get("name", ""),
                    "num":        c.get("num", ""),
                    "begin_date": c.get("begin_date", ""),
                    "duration":   c.get("duration", ""),
                    "end_date":   c.get("end_date", ""),
                }
                for c in (data.get("_contracts") or [])
                if isinstance(c, dict)
            ],
        }
    except Exception as exc:
        logger.warning("get_computer_by_id failed (id=%s): %s", computer_id, exc)
        return None


async def get_user_assets(user_id: int) -> list[dict[str, Any]]:
    """Fetch komputer yang dimiliki atau ditugaskan kepada user tertentu.

    Menggunakan tiga candidate field ID secara berurutan untuk kompatibilitas
    antar versi GLPI. Jika Search API dengan semua candidate field gagal,
    fallback ke GET /Computer dengan filter client-side.

    Args:
        user_id: GLPI User ID.

    Returns:
        List dict komputer yang terkait dengan user, atau list kosong.
    """
    def _normalise(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id":           item.get("id", ""),
            "name":         item.get("name", ""),
            "serial":       item.get("serial", ""),
            "otherserial":  item.get("otherserial", ""),
            "type":         clean_value(item.get("computertypes_id")),
            "model":        clean_value(item.get("computermodels_id")) or clean_value(item.get("model")),
            "status":       clean_value(item.get("states_id")) or clean_value(item.get("status")),
            "location":     clean_value(item.get("locations_id")) or clean_value(item.get("location")),
            "user":         clean_value(item.get("users_id")) or clean_value(item.get("user")),
            "entity":       clean_value(item.get("entities_id")),
            "manufacturer": clean_value(item.get("manufacturers_id")),
            "os":           clean_value(item.get("operatingsystems_id")),
            "date_mod":     item.get("date_mod", ""),
        }

    # Strategy 1: Search API dengan kandidat field user (multi-versi GLPI)
    candidate_fields = [
        (24, "User (GLPI 10.x/11 standard)"),
        (70, "users_id alternate"),
        (45, "User (some configs)"),
    ]

    for field_id, label in candidate_fields:
        try:
            params: dict[str, Any] = {
                "criteria[0][field]":      field_id,
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]":      user_id,
                "range":                   "0-199",
                "expand_dropdowns":        "true",
                "forcedisplay[0]":  1,
                "forcedisplay[1]":  2,
                "forcedisplay[2]":  3,
                "forcedisplay[3]":  4,
                "forcedisplay[4]":  5,
                "forcedisplay[5]":  6,
                "forcedisplay[6]":  23,
                "forcedisplay[7]":  31,
                "forcedisplay[8]":  40,
                "forcedisplay[9]":  80,
                "forcedisplay[10]": field_id,
            }
            data = await glpi_get("/search/Computer", params=params)
            items: list[Any] = extract_data(data)

            if items:
                logger.info(
                    "get_user_assets (Search API, field=%s '%s'): found %d results",
                    field_id, label, len(items),
                )
                return [
                    {
                        "id":           first_of(item, "2", "id"),
                        "name":         first_of(item, "1", "name"),
                        "serial":       first_of(item, "5", "serial"),
                        "otherserial":  first_of(item, "6", "otherserial"),
                        "type":         clean_value(first_of(item, "4", "computertypes_id", "type")),
                        "model":        clean_value(first_of(item, "40", "computermodels_id", "model")),
                        "status":       clean_value(first_of(item, "31", "states_id", "status")),
                        "location":     clean_value(first_of(item, "3", "locations_id", "location")),
                        "user":         clean_value(first_of(item, str(field_id), "users_id", "user")),
                        "entity":       clean_value(first_of(item, "80", "entities_id", "entity")),
                        "manufacturer": clean_value(first_of(item, "23", "manufacturers_id", "manufacturer")),
                        "os":           clean_value(first_of(item, "14", "operatingsystems_id", "os")),
                        "date_mod":     first_of(item, "19", "date_mod"),
                    }
                    for item in items if isinstance(item, dict)
                ]
        except Exception as exc:
            logger.debug(
                "get_user_assets (Search API, field=%s '%s') error: %s",
                field_id, label, exc,
            )

    # Strategy 2: GET /Computer bulk, filter client-side
    try:
        data = await glpi_get("/Computer", params={
            "expand_dropdowns": "true",
            "range":            "0-199",
            "is_deleted":       "0",
        })
        all_computers: list[Any] = extract_data(data)
        user_computers = [
            item for item in all_computers
            if isinstance(item, dict)
            and str(item.get("users_id", "")) == str(user_id)
            and str(item.get("is_deleted", "0")) == "0"
        ]
        if user_computers:
            logger.info(
                "get_user_assets (fallback bulk GET): found %d computers for user_id=%s",
                len(user_computers), user_id,
            )
            return [_normalise(c) for c in user_computers]
    except Exception as exc:
        logger.warning("get_user_assets strategy 2 failed (user_id=%s): %s", user_id, exc)

    logger.warning("get_user_assets: no assets found for user_id=%s", user_id)
    return []


async def search_computer_by_name(name: str, limit: int = 50) -> list[dict[str, Any]]:
    """Cari komputer berdasarkan nama menggunakan GLPI Search API.

    Pencarian bersifat partial match (``contains``) dan case-insensitive
    di sisi server GLPI.

    Args:
        name : Nama atau substring nama komputer yang dicari.
        limit: Jumlah maksimal hasil. Default 50.

    Returns:
        List dict komputer yang cocok, atau list kosong jika tidak ditemukan.
    """
    try:
        params: dict[str, Any] = {
            "is_recursive":            "true",
            "criteria[0][field]":      1,
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]":      name,
            "range":                   f"0-{limit - 1}",
            "expand_dropdowns":        "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
        data = await glpi_get("/search/Computer", params=params)
        items: list[Any] = extract_data(data)
        return [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("search_computer_by_name failed: %s", exc)
        return []


async def search_computer(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Cari komputer menggunakan satu kata kunci di Nama, Serial, ATAU Inventory Number.

    Menggunakan OR criteria sehingga satu query bisa mencocokkan field yang berbeda.
    Cocok untuk search box umum di mana user tidak tahu field mana yang relevan.

    Args:
        query: Kata kunci pencarian (partial match pada nama, serial, otherserial).
        limit: Jumlah maksimal hasil. Default 10.

    Returns:
        List dict komputer yang cocok, atau list kosong jika tidak ditemukan.
    """
    try:
        params: dict[str, Any] = {
            "is_recursive":            "true",
            "criteria[0][field]":      1,
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]":      query,
            "criteria[1][link]":       "OR",
            "criteria[1][field]":      5,
            "criteria[1][searchtype]": "contains",
            "criteria[1][value]":      query,
            "criteria[2][link]":       "OR",
            "criteria[2][field]":      6,
            "criteria[2][searchtype]": "contains",
            "criteria[2][value]":      query,
            "range":                   f"0-{limit - 1}",
            "expand_dropdowns":        "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
        data = await glpi_get("/search/Computer", params=params)
        items: list[Any] = extract_data(data)
        results = [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
        logger.info("search_computer: query='%s' -> %d result(s)", query, len(results))
        return results
    except Exception as exc:
        logger.warning("search_computer failed (query='%s'): %s", query, exc)
        return []


async def get_computers_by_status(
    status_filter: str,
    sample_size: int = 50,
) -> PagedResult:
    """Fetch komputer berdasarkan status (server-side filter, auto-paginated).

    Args:
        status_filter: Label status yang dicari (contains, case-insensitive di GLPI).
                       Contoh: ``"In use"``, ``"Available"``, ``"Retired"``.
        sample_size  : Jumlah item di halaman pertama. Default 50.

    Returns:
        ``PagedResult`` dengan komputer yang cocok, totalcount exact, dan
        truncated flag.
    """
    base_params: dict[str, Any] = {
        "is_recursive":            "true",
        "criteria[0][field]":      31,
        "criteria[0][searchtype]": "contains",
        "criteria[0][value]":      status_filter,
        "expand_dropdowns":        "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
    try:
        result = await get_all_pages(
            "/search/Computer",
            base_params=base_params,
            sample_size=sample_size,
        )
        parsed = [_parse_computer_search_item(item) for item in result["items"]]
        return PagedResult(
            items=parsed,
            totalcount=result["totalcount"],
            fetched=len(parsed),
            truncated=result["truncated"],
        )
    except Exception as exc:
        logger.warning("get_computers_by_status failed (filter=%s): %s", status_filter, exc)
        return PagedResult(items=[], totalcount=0, fetched=0, truncated=False)


async def get_computers_by_location(
    location_filter: str,
    sample_size: int = 50,
) -> PagedResult:
    """Fetch komputer berdasarkan lokasi (server-side filter, auto-paginated).

    Args:
        location_filter: Nama atau substring lokasi (contains, case-insensitive).
        sample_size    : Jumlah item di halaman pertama. Default 50.

    Returns:
        ``PagedResult`` dengan komputer yang cocok, totalcount exact, dan
        truncated flag.
    """
    base_params: dict[str, Any] = {
        "is_recursive":            "true",
        "criteria[0][field]":      3,
        "criteria[0][searchtype]": "contains",
        "criteria[0][value]":      location_filter,
        "expand_dropdowns":        "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
    try:
        result = await get_all_pages(
            "/search/Computer",
            base_params=base_params,
            sample_size=sample_size,
        )
        parsed = [_parse_computer_search_item(item) for item in result["items"]]
        return PagedResult(
            items=parsed,
            totalcount=result["totalcount"],
            fetched=len(parsed),
            truncated=result["truncated"],
        )
    except Exception as exc:
        logger.warning("get_computers_by_location failed (filter=%s): %s", location_filter, exc)
        return PagedResult(items=[], totalcount=0, fetched=0, truncated=False)


async def get_computers_by_os(
    os_filter: str,
    sample_size: int = 50,
) -> PagedResult:
    """Fetch komputer berdasarkan sistem operasi (server-side filter, auto-paginated).

    Args:
        os_filter  : Nama atau substring OS (contains, case-insensitive).
                     Contoh: ``"Windows 10"``, ``"Ubuntu"``, ``"macOS"``.
        sample_size: Jumlah item di halaman pertama. Default 50.

    Returns:
        ``PagedResult`` dengan komputer yang cocok, totalcount exact, dan
        truncated flag.
    """
    base_params: dict[str, Any] = {
        "is_recursive":            "true",
        "criteria[0][field]":      14,
        "criteria[0][searchtype]": "contains",
        "criteria[0][value]":      os_filter,
        "expand_dropdowns":        "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
    try:
        result = await get_all_pages(
            "/search/Computer",
            base_params=base_params,
            sample_size=sample_size,
        )
        parsed = [_parse_computer_search_item(item) for item in result["items"]]
        return PagedResult(
            items=parsed,
            totalcount=result["totalcount"],
            fetched=len(parsed),
            truncated=result["truncated"],
        )
    except Exception as exc:
        logger.warning("get_computers_by_os failed (filter=%s): %s", os_filter, exc)
        return PagedResult(items=[], totalcount=0, fetched=0, truncated=False)


async def get_computers_expiring_warranty(
    days: int = 90,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch komputer yang masa garansinya habis dalam N hari ke depan.

    Menggunakan GLPI Infocom field (field ID 162) untuk filter tanggal garansi.
    Hasil di-enrich dengan field ``warranty_expiry`` dari field warranty_date
    yang disertakan dalam forcedisplay.

    Args:
        days : Jumlah hari ke depan untuk batas pencarian garansi. Default 90.
        limit: Jumlah maksimal hasil. Default 50.

    Returns:
        List dict komputer dengan field tambahan ``warranty_expiry``.
    """
    import datetime
    today = datetime.date.today()
    today_str = today.isoformat()
    future_str = (today + datetime.timedelta(days=days)).isoformat()

    try:
        warranty_field_str = str(_INFOCOM_WARRANTY_FIELD)
        forcedisplay = dict(_COMPUTER_SEARCH_FORCEDISPLAY)
        next_idx = len(forcedisplay)
        forcedisplay[f"forcedisplay[{next_idx}]"] = _INFOCOM_WARRANTY_FIELD

        params: dict[str, Any] = {
            "criteria[0][field]":      _INFOCOM_WARRANTY_FIELD,
            "criteria[0][searchtype]": "morethan",
            "criteria[0][value]":      today_str,
            "criteria[1][link]":       "AND",
            "criteria[1][field]":      _INFOCOM_WARRANTY_FIELD,
            "criteria[1][searchtype]": "lessthan",
            "criteria[1][value]":      future_str,
            "range":                   f"0-{limit - 1}",
            "expand_dropdowns":        "true",
            **forcedisplay,
        }
        data = await glpi_get("/search/Computer", params=params)
        items: list[Any] = extract_data(data)
        return [
            {
                **_parse_computer_search_item(item),
                "warranty_expiry": first_of(item, warranty_field_str, "warranty_date"),
            }
            for item in items if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.warning("get_computers_expiring_warranty failed: %s", exc)
        return []