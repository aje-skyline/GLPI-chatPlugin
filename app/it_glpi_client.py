"""GLPI REST API client.

Connects to GLPI instance configured via settings.
All GET endpoints map 1-to-1 with the Postman collection:

  Assets:
    GET /Computer                          → get_all_computers()
    GET /Computer/{id}                     → get_computer_by_id()
    GET /search/Computer                   → get_user_assets()

  Contracts:
    GET /Contract                          → get_contracts(computer_id=0)
    GET /Contract/{id}                     → get_contract_by_id()

  Utilities:
    GET /getMultipleItems                  → get_multiple_items()
    GET /listSearchOptions/{itemtype}      → list_search_options()

  Knowledge Base / Tickets / User / ITIL:
    GET /KnowbaseItem                      → fetch_knowbase_items()
    GET /search/Ticket                     → fetch_user_tickets()
    GET /User/{id}                         → fetch_user_info()
    GET /ITILCategory                      → fetch_itil_categories()
    GET /Supplier                          → fetch_suppliers()

CHANGELOG (v7.0 — Full Computer Detail & Supplier Smart Pagination):
  - get_computer_by_id(): tambah with_documents=true; expose contact_num,
    os_version, os_arch, doc_count, entity. OS resolve cascade.
  - search_suppliers(): hard cap SUPPLIER_MAX_ENRICH (default 20) pada fase
    enrich agar jumlah concurrent GET /Supplier/{id} tidak meledak.

CHANGELOG (v4.0 — Smart Pagination):
  - Tambah _get_all_pages(): internal helper untuk auto-pagination yang
    mengambil semua halaman dari GLPI Search API secara efisien.
  - Tambah PagedResult TypedDict: membawa (items, totalcount) bersama-sama
    sehingga tools dapat melaporkan jumlah exact ke LLM.
  - get_all_computers(), get_computers_by_status(), get_computers_by_location(),
    get_computers_by_os() sekarang mengembalikan PagedResult.
  - get_total_computers_count() tetap ada untuk backward-compat tapi
    tools baru cukup pakai totalcount dari PagedResult.
  - GLPI_MAX_PAGE_SIZE = 100: batas aman per-request (server biasanya
    reject range > 1000; 100 adalah nilai konservatif yang pasti didukung).

CHANGELOG (bug-fix v2.1 — Event Loop):
  asyncio.Lock() objects MUST NOT be created at module level. A Lock is
  bound to the event loop that was running when it was constructed. Since
  tools.py now uses a single persistent background loop (started *after*
  module import), any Lock created at import time would be bound to a
  *different* (or non-existent) loop and raise errors on first use.
  Fix: all Locks are created lazily inside async functions on first call.
"""

import asyncio
import logging
import re
import time
from typing import Any, TypedDict

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# GLPI API base URL — use glpi_api_url from config directly
GLPI_API_BASE: str = settings.glpi_api_url.rstrip("/")

# Headers required for every GLPI API request
_BASE_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "App-Token": settings.glpi_app_token,
}

# ── Pagination constants ──────────────────────────────────────────────────────
# GLPI membatasi jumlah record per request. Nilai 100 adalah nilai aman
# yang didukung hampir semua versi GLPI tanpa konfigurasi khusus.
# Naikkan ke 200-500 hanya jika server GLPI Anda sudah dikonfigurasi untuk itu.
GLPI_MAX_PAGE_SIZE: int = 100

# Batas total record yang akan di-fetch melalui auto-pagination.
# Di luar batas ini, hanya summary statistik yang dikembalikan ke LLM
# (menghemat token dan menghindari context window overflow).
GLPI_AUTO_PAGINATE_LIMIT: int = 20_000


# ── PagedResult TypedDict ─────────────────────────────────────────────────────

class PagedResult(TypedDict):
    """Wrapper hasil pagination dari GLPI Search API.

    Attributes:
        items     : List item yang sudah di-fetch (bisa subset dari total).
        totalcount: Jumlah exact dari GLPI (selalu akurat, dari header API).
        fetched   : Jumlah item yang benar-benar di-fetch (len(items)).
        truncated : True jika totalcount > fetched (data dipotong untuk hemat token).
    """
    items: list[dict[str, Any]]
    totalcount: int
    fetched: int
    truncated: bool


# ── Session state ─────────────────────────────────────────────────────────────
_session_token: str | None = None
_session_lock: asyncio.Lock | None = None
_session_waiter: "asyncio.Future[str] | None" = None


def _get_session_lock() -> asyncio.Lock:
    global _session_lock
    if _session_lock is None:
        _session_lock = asyncio.Lock()
    return _session_lock


# ── Shared HTTP client ────────────────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None
_http_client_lock: asyncio.Lock | None = None


def _get_http_client_lock() -> asyncio.Lock:
    global _http_client_lock
    if _http_client_lock is None:
        _http_client_lock = asyncio.Lock()
    return _http_client_lock


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    async with _get_http_client_lock():
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=30,
                verify=settings.glpi_verify_ssl,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=30,
                ),
            )
            logger.debug("GLPI shared AsyncClient created")
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
        logger.info("GLPI shared AsyncClient closed")


# ── Simple TTL cache ──────────────────────────────────────────────────────────
_CACHE_TTL_SECONDS: int = 300
_ttl_cache: dict[str, dict[str, Any]] = {}


def _cache_get(key: str) -> Any | None:
    entry = _ttl_cache.get(key)
    if entry and time.monotonic() < entry["expires_at"]:
        return entry["value"]
    _ttl_cache.pop(key, None)
    return None


def _cache_set(key: str, value: Any, ttl: int = _CACHE_TTL_SECONDS) -> None:
    _ttl_cache[key] = {"value": value, "expires_at": time.monotonic() + ttl}


def invalidate_static_cache() -> None:
    _ttl_cache.clear()
    logger.info("GLPI static data cache cleared")


# ── Session Management ────────────────────────────────────────────────────────

async def _init_session() -> str:
    client = await _get_http_client()
    resp = await client.get(
        f"{GLPI_API_BASE}/initSession",
        headers={
            **_BASE_HEADERS,
            "Authorization": f"user_token {settings.glpi_user_token}",
        },
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    token: str | None = data.get("session_token")
    if not token:
        raise RuntimeError(f"GLPI initSession returned no token: {data}")
    logger.info("GLPI session obtained successfully")
    return token


async def _kill_session(token: str) -> None:
    try:
        client = await _get_http_client()
        await client.get(
            f"{GLPI_API_BASE}/killSession",
            headers={**_BASE_HEADERS, "Session-Token": token},
        )
    except Exception as exc:
        logger.warning("GLPI killSession failed (ignored): %s", exc)


async def _get_session_token() -> str:
    global _session_token, _session_waiter

    if _session_token:
        return _session_token

    lock = _get_session_lock()
    loop = asyncio.get_running_loop()
    is_leader = False
    waiter: "asyncio.Future[str]"

    async with lock:
        if _session_token:
            return _session_token
        if _session_waiter is not None:
            waiter = _session_waiter
        else:
            waiter = loop.create_future()
            _session_waiter = waiter
            is_leader = True

    if not is_leader:
        return await asyncio.shield(waiter)

    try:
        token = await _init_session()
        async with lock:
            _session_token = token
            _session_waiter = None
        waiter.set_result(token)
        return token
    except Exception as exc:
        async with lock:
            _session_waiter = None
        if not waiter.done():
            waiter.set_exception(exc)
        raise


async def _get(
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    """Authenticated GET request to the GLPI API with retry & token refresh."""
    global _session_token

    async def _do_request(token: str) -> httpx.Response:
        client = await _get_http_client()
        return await client.get(
            f"{GLPI_API_BASE}{path}",
            headers={**_BASE_HEADERS, "Session-Token": token},
            params=params,
        )

    token: str = await _get_session_token()

    _RETRYABLE = {429, 500, 502, 503, 504}
    for attempt in range(3):
        resp: httpx.Response = await _do_request(token)

        if resp.status_code == 401:
            logger.info("GLPI session expired — refreshing and retrying")
            lock = _get_session_lock()
            old_token = token
            async with lock:
                if _session_token == old_token:
                    _session_token = None
            new_token = await _init_session()
            async with lock:
                if not _session_token:
                    _session_token = new_token
            token = _session_token or new_token
            resp = await _do_request(token)

        if resp.status_code in _RETRYABLE and attempt < 2:
            wait = 2 ** attempt
            logger.warning(
                "GLPI API returned %s — retrying in %ss (attempt %d/3)",
                resp.status_code, wait, attempt + 1,
            )
            await asyncio.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.json()

    resp.raise_for_status()  # type: ignore[possibly-undefined]
    return resp.json()


# ── NEW: Auto-Pagination Helper ───────────────────────────────────────────────

async def _get_all_pages(
    path: str,
    base_params: dict[str, Any],
    sample_size: int = 50,
    max_total: int = GLPI_AUTO_PAGINATE_LIMIT,
    page_size: int = GLPI_MAX_PAGE_SIZE,
) -> PagedResult:
    """Ambil semua halaman dari GLPI Search API secara otomatis.

    Strategi dua fase:
    1. Fase probe: ambil halaman pertama (sample_size record) untuk mendapatkan
       ``totalcount`` yang akurat dari API.
    2. Fase pagination: jika totalcount > sample_size, ambil halaman berikutnya
       sampai semua data terkumpul atau mencapai max_total.

    Token-aware: jika totalcount sangat besar (> max_total), fungsi berhenti
    setelah max_total record agar tidak overflow context window LLM.

    Args:
        path       : URL path GLPI (e.g., '/search/Computer').
        base_params: Parameter dasar tanpa 'range' (akan di-override per halaman).
        sample_size: Jumlah record di halaman pertama (probe). Default 50.
        max_total  : Batas maksimum record yang di-fetch. Default 20.000.
        page_size  : Jumlah record per halaman setelah probe. Default 100.

    Returns:
        PagedResult dengan items, totalcount, fetched, dan truncated flag.
    """
    # ── Fase 1: Probe — ambil halaman pertama + dapatkan totalcount ───────────
    probe_params = {**base_params, "range": f"0-{sample_size - 1}"}
    probe_data = await _get(path, params=probe_params)

    totalcount: int = 0
    if isinstance(probe_data, dict):
        totalcount = int(probe_data.get("totalcount", 0))

    first_page_items = _extract_data(probe_data)
    items: list[dict[str, Any]] = [
        item for item in first_page_items if isinstance(item, dict)
    ]

    logger.info(
        "_get_all_pages: path=%s totalcount=%d fetched_first=%d",
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
            page_data = await _get(path, params=page_params)
            page_items = [
                item for item in _extract_data(page_data)
                if isinstance(item, dict)
            ]
        except Exception as exc:
            logger.warning(
                "_get_all_pages: error fetching range %d-%d: %s — stopping pagination",
                start, end, exc,
            )
            break

        if not page_items:
            break  # Server tidak mengembalikan data lagi

        items.extend(page_items)
        logger.debug(
            "_get_all_pages: fetched range %d-%d, total_so_far=%d",
            start, end, len(items),
        )

        start = end + 1
        if start >= fetch_target:
            break

    truncated = len(items) < totalcount
    logger.info(
        "_get_all_pages: DONE path=%s totalcount=%d fetched=%d truncated=%s",
        path, totalcount, len(items), truncated,
    )
    return PagedResult(
        items=items,
        totalcount=totalcount,
        fetched=len(items),
        truncated=truncated,
    )


# ── Assets ────────────────────────────────────────────────────────────────────

async def get_all_computers(
    sample_size: int = 50,
    has_serial: bool = False,
    paginate: bool = True,
) -> PagedResult:
    """Fetch semua komputer di GLPI dengan dukungan auto-pagination.

    PERUBAHAN v4.0: sekarang mengembalikan PagedResult (bukan list) agar
    tools dapat melaporkan totalcount exact ke LLM.

    Args:
        sample_size: Jumlah komputer yang ditampilkan sebagai sample (default 50).
        has_serial : Jika True, filter hanya komputer berserial number.
        paginate   : Jika True, gunakan auto-pagination (ambil semua halaman).
                     Jika False, hanya ambil sample_size record (mode cepat).

    Returns:
        PagedResult dengan items (sample), totalcount, fetched, truncated.
    """
    base_params: dict[str, Any] = {
        "expand_dropdowns": "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }

    if has_serial:
        base_params["criteria[0][field]"] = 5
        base_params["criteria[0][searchtype]"] = "isnotempty"

    try:
        if paginate:
            result = await _get_all_pages(
                "/search/Computer",
                base_params=base_params,
                sample_size=sample_size,
            )
        else:
            # Mode cepat: hanya satu request
            probe_params = {**base_params, "range": f"0-{sample_size - 1}"}
            raw = await _get("/search/Computer", params=probe_params)
            totalcount = int(raw.get("totalcount", 0)) if isinstance(raw, dict) else 0
            items = [
                item for item in _extract_data(raw) if isinstance(item, dict)
            ]
            result = PagedResult(
                items=items,
                totalcount=totalcount or len(items),
                fetched=len(items),
                truncated=(totalcount > len(items)),
            )

        # Parse setiap item ke format standar
        parsed_items = [
            _parse_computer_search_item(item) for item in result["items"]
        ]
        # Fallback ke GET /Computer jika Search API tidak mengembalikan data
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


async def _get_all_computers_fallback(
    sample_size: int,
    has_serial: bool,
) -> PagedResult:
    """Fallback ke GET /Computer jika Search API gagal."""
    try:
        data = await _get("/Computer", params={
            "expand_dropdowns": "true",
            "range": f"0-{sample_size - 1}",
        })
        items = _extract_data(data)
        result = [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "serial": item.get("serial", ""),
                "otherserial": item.get("otherserial", ""),
                "type": _clean_value(item.get("computertypes_id")),
                "model": _clean_value(item.get("computermodels_id")) or _clean_value(item.get("model")),
                "status": _clean_value(item.get("states_id")) or _clean_value(item.get("status")),
                "location": _clean_value(item.get("locations_id")) or _clean_value(item.get("location")),
                "user": _clean_value(item.get("users_id")) or _clean_value(item.get("user")),
                "entity": _clean_value(item.get("entities_id")),
                "manufacturer": _clean_value(item.get("manufacturers_id")),
                "os": _clean_value(item.get("operatingsystems_id")),
                "date_mod": item.get("date_mod", ""),
            }
            for item in items if isinstance(item, dict)
        ]
        if has_serial:
            result = [c for c in result if c.get("serial", "").strip()]

        return PagedResult(
            items=result,
            totalcount=len(result),  # Fallback: tidak ada totalcount
            fetched=len(result),
            truncated=False,
        )
    except Exception as exc:
        logger.warning("_get_all_computers_fallback failed: %s", exc)
        return PagedResult(items=[], totalcount=0, fetched=0, truncated=False)


async def get_total_computers_count() -> int:
    """Fetch jumlah total komputer di GLPI (exact count dari API).

    Dipertahankan untuk backward-compatibility dengan CountAllComputersTool.
    Untuk penggunaan baru, pakai PagedResult.totalcount dari get_all_computers().
    """
    try:
        data = await _get("/search/Computer", params={
            "is_recursive": "1",
            "range": "0-1",
        })
        if isinstance(data, dict) and "totalcount" in data:
            return int(data["totalcount"])
        return 0
    except Exception as exc:
        logger.warning("get_total_computers_count failed: %s", exc)
        return 0


async def get_computer_by_id(computer_id: int) -> dict[str, Any] | None:
    """Fetch satu komputer dengan data lengkap: finansial, kontrak, OS, dan dokumen.

    Endpoint: GET /Computer/{id}?expand_dropdowns=true
              &with_infocoms=true&with_contracts=true
              &with_operatingsystems=true&with_documents=true

    CHANGELOG v7.0:
      - Tambah with_documents=true untuk mendapatkan jumlah dokumen terlampir.
      - Tambah field: contact (alternate username number), contact_num
        (alternate username), os_version, os_arch, doc_count, entity.
      - OS: strategi cascade — coba operatingsystems_id (expand_dropdowns),
        lalu _operatingsystems[0].name, lalu _operatingsystems[0].operatingsystems_id.
      - Manufacturer: sudah di-expand via expand_dropdowns=true (nama langsung
        tersedia di manufacturers_id sebagai string).
    """
    try:
        data = await _get(f"/Computer/{computer_id}", params={
            "expand_dropdowns": "true",
            "with_infocoms":        "true",
            "with_contracts":       "true",
            "with_operatingsystems": "true",
            "with_documents":       "true",
        })
        if not isinstance(data, dict):
            return None

        infocoms: dict[str, Any] = data.get("_infocoms") or {}

        # ── OS: cascade nama dari beberapa sumber ─────────────────────────────
        # expand_dropdowns=true menggantikan ID dengan nama string di field
        # *_id. Jika hasilnya masih angka, fallback ke _operatingsystems list.
        os_name: str = _clean_value(data.get("operatingsystems_id"))
        os_version: str = ""
        os_arch: str = ""

        os_list: list[Any] = data.get("_operatingsystems") or []
        if os_list and isinstance(os_list[0], dict):
            os_item = os_list[0]
            if not os_name:
                os_name = _clean_value(
                    os_item.get("operatingsystems_id")
                    or os_item.get("name", "")
                )
            # Versi & arsitektur OS ada di sub-item _operatingsystems
            os_version = _clean_value(
                os_item.get("operatingsystemversions_id")
                or os_item.get("version", "")
            )
            os_arch = _clean_value(
                os_item.get("operatingsystemarchitectures_id")
                or os_item.get("arch", "")
            )

        os_display = os_name
        if os_version:
            os_display = f"{os_name} {os_version}".strip()
        if os_arch:
            os_display = f"{os_display} ({os_arch})".strip()

        # ── Jumlah dokumen terlampir ──────────────────────────────────────────
        documents: list[Any] = data.get("_documents") or []
        doc_count: int = len(documents) if isinstance(documents, list) else 0

        return {
            "id":           data.get("id", ""),
            "name":         data.get("name", ""),
            "entity":       _clean_value(data.get("entities_id")),
            "serial":       data.get("serial", ""),
            "otherserial":  data.get("otherserial", ""),
            "location":     _clean_value(data.get("locations_id")),
            "type":         _clean_value(data.get("computertypes_id")),
            "model":        _clean_value(data.get("computermodels_id")),
            "manufacturer": _clean_value(data.get("manufacturers_id")),
            # contact_num = "Alternate username number" di GLPI
            # contact     = "Alternate username" di GLPI
            "contact_num":  data.get("contact_num", ""),
            "contact":      data.get("contact", ""),
            "os":           os_display,
            "os_name":      os_name,
            "os_version":   os_version,
            "os_arch":      os_arch,
            "status":       _clean_value(data.get("states_id")),
            "user":         _clean_value(data.get("users_id")),
            "comment":      _strip_html(data.get("comment", "") or ""),
            "doc_count":    doc_count,
            "date_mod":     data.get("date_mod", ""),
            # ── Infocom (Financial & Administrative) ──────────────────────────
            "buy_date":          infocoms.get("buy_date", ""),
            "use_date":          infocoms.get("use_date", ""),
            "warranty_duration": infocoms.get("warranty_duration", ""),
            "warranty_date":     infocoms.get("warranty_date", ""),
            "value":             infocoms.get("value", ""),
            "supplier":          _clean_value(infocoms.get("suppliers_id", "")),
            # ── Linked contracts ──────────────────────────────────────────────
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
    """Fetch komputer yang dimiliki/ditugaskan kepada user tertentu.

    Menggunakan GLPI Search API dengan berbagai candidate field untuk
    kompatibilitas antar versi GLPI. Tidak menggunakan full pagination
    karena data personal user biasanya kecil (< 50 item).

    Args:
        user_id: GLPI User ID.

    Returns:
        List of computer dicts owned by the user.
    """
    def _normalise(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "serial": item.get("serial", ""),
            "otherserial": item.get("otherserial", ""),
            "type": _clean_value(item.get("computertypes_id")),
            "model": _clean_value(item.get("computermodels_id")) or _clean_value(item.get("model")),
            "status": _clean_value(item.get("states_id")) or _clean_value(item.get("status")),
            "location": _clean_value(item.get("locations_id")) or _clean_value(item.get("location")),
            "user": _clean_value(item.get("users_id")) or _clean_value(item.get("user")),
            "entity": _clean_value(item.get("entities_id")),
            "manufacturer": _clean_value(item.get("manufacturers_id")),
            "os": _clean_value(item.get("operatingsystems_id")),
            "date_mod": item.get("date_mod", ""),
        }

    candidate_fields = [
        (24, "User (GLPI 10.x/11 standard)"),
        (70, "users_id alternate"),
        (45, "User (some configs)"),
    ]

    for field_id, label in candidate_fields:
        try:
            params: dict[str, Any] = {
                "criteria[0][field]": field_id,
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": user_id,
                "range": "0-199",
                "expand_dropdowns": "true",
                "forcedisplay[0]": 1,
                "forcedisplay[1]": 2,
                "forcedisplay[2]": 3,
                "forcedisplay[3]": 4,
                "forcedisplay[4]": 5,
                "forcedisplay[5]": 6,
                "forcedisplay[6]": 23,
                "forcedisplay[7]": 31,
                "forcedisplay[8]": 40,
                "forcedisplay[9]": 80,
                "forcedisplay[10]": field_id,
            }
            data = await _get("/search/Computer", params=params)
            items: list[Any] = _extract_data(data)

            if items:
                logger.info(
                    "get_user_assets (Search API, field=%s '%s'): found %d results",
                    field_id, label, len(items),
                )
                return [
                    {
                        "id": _first(item, "2", "id"),
                        "name": _first(item, "1", "name"),
                        "serial": _first(item, "5", "serial"),
                        "otherserial": _first(item, "6", "otherserial"),
                        "type": _clean_value(_first(item, "4", "computertypes_id", "type")),
                        "model": _clean_value(_first(item, "40", "computermodels_id", "model")),
                        "status": _clean_value(_first(item, "31", "states_id", "status")),
                        "location": _clean_value(_first(item, "3", "locations_id", "location")),
                        "user": _clean_value(_first(item, str(field_id), "users_id", "user")),
                        "entity": _clean_value(_first(item, "80", "entities_id", "entity")),
                        "manufacturer": _clean_value(_first(item, "23", "manufacturers_id", "manufacturer")),
                        "os": _clean_value(_first(item, "14", "operatingsystems_id", "os")),
                        "date_mod": _first(item, "19", "date_mod"),
                    }
                    for item in items if isinstance(item, dict)
                ]
        except Exception as exc:
            logger.debug(
                "get_user_assets (Search API, field=%s '%s') error: %s",
                field_id, label, exc,
            )

    # Strategy 2 fallback: GET /Computer, filter client-side
    try:
        data = await _get("/Computer", params={
            "expand_dropdowns": "true",
            "range": "0-199",
            "is_deleted": "0",
        })
        all_computers: list[Any] = _extract_data(data)
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
    """Cari komputer berdasarkan nama menggunakan GLPI Search API."""
    try:
        params: dict[str, Any] = {
            "criteria[0][field]": 1,
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": name,
            "range": f"0-{limit - 1}",
            "expand_dropdowns": "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
        data = await _get("/search/Computer", params=params)
        items: list[Any] = _extract_data(data)
        return [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("search_computer_by_name failed: %s", exc)
        return []


async def search_computer(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Cari komputer menggunakan satu kata kunci di Nama, Serial, ATAU Inventory Number."""
    try:
        params: dict[str, Any] = {
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
            "range":            f"0-{limit - 1}",
            "expand_dropdowns": "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
        data = await _get("/search/Computer", params=params)
        items: list[Any] = _extract_data(data)
        results = [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
        logger.info("search_computer: query='%s' -> %d result(s)", query, len(results))
        return results
    except Exception as exc:
        logger.warning("search_computer failed (query='%s'): %s", query, exc)
        return []


# ── Filter Functions — sekarang mengembalikan PagedResult ─────────────────────

async def get_computers_by_status(
    status_filter: str,
    sample_size: int = 50,
) -> PagedResult:
    """Fetch komputer berdasarkan status (server-side filter, auto-paginated).

    PERUBAHAN v4.0: mengembalikan PagedResult (bukan list) agar tools dapat
    melaporkan totalcount dan truncated flag ke LLM.

    Args:
        status_filter: Label status yang dicari (contains, case-insensitive).
        sample_size  : Jumlah item yang di-fetch sebagai sample jika data besar.
    """
    base_params: dict[str, Any] = {
        "criteria[0][field]": 31,
        "criteria[0][searchtype]": "contains",
        "criteria[0][value]": status_filter,
        "expand_dropdowns": "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
    try:
        result = await _get_all_pages(
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

    PERUBAHAN v4.0: mengembalikan PagedResult.
    """
    base_params: dict[str, Any] = {
        "criteria[0][field]": 3,
        "criteria[0][searchtype]": "contains",
        "criteria[0][value]": location_filter,
        "expand_dropdowns": "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
    try:
        result = await _get_all_pages(
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
    """Fetch komputer berdasarkan OS (server-side filter, auto-paginated).

    PERUBAHAN v4.0: mengembalikan PagedResult.
    """
    base_params: dict[str, Any] = {
        "criteria[0][field]": 14,
        "criteria[0][searchtype]": "contains",
        "criteria[0][value]": os_filter,
        "expand_dropdowns": "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
    try:
        result = await _get_all_pages(
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
    """Fetch komputer yang garansinya habis dalam N hari ke depan."""
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
            "criteria[0][field]": _INFOCOM_WARRANTY_FIELD,
            "criteria[0][searchtype]": "morethan",
            "criteria[0][value]": today_str,
            "criteria[1][link]": "AND",
            "criteria[1][field]": _INFOCOM_WARRANTY_FIELD,
            "criteria[1][searchtype]": "lessthan",
            "criteria[1][value]": future_str,
            "range": f"0-{limit - 1}",
            "expand_dropdowns": "true",
            **forcedisplay,
        }
        data = await _get("/search/Computer", params=params)
        items: list[Any] = _extract_data(data)
        return [
            {
                **_parse_computer_search_item(item),
                "warranty_expiry": _first(item, warranty_field_str, "warranty_date"),
            }
            for item in items if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.warning("get_computers_expiring_warranty failed: %s", exc)
        return []


# ── Contracts ─────────────────────────────────────────────────────────────────

async def get_contracts(
    computer_id: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch kontrak dari GLPI."""
    try:
        if computer_id > 0:
            computer = await get_computer_by_id(computer_id)
            if not computer:
                return []
            return computer.get("contracts", [])

        data = await _get("/Contract", params={
            "expand_dropdowns": "true",
            "range": f"0-{limit - 1}",
        })
        items: list[Any] = _extract_data(data)
        return [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "num": item.get("num", ""),
                "type": _clean_value(item.get("contracttypes_id")),
                "supplier": _clean_value(item.get("suppliers_id")),
                "begin_date": item.get("begin_date", ""),
                "duration": item.get("duration", ""),
                "end_date": item.get("end_date", ""),
                "comment": _strip_html(item.get("comment", "") or ""),
            }
            for item in items if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.warning("get_contracts failed: %s", exc)
        return []


async def get_contract_by_id(contract_id: int) -> dict[str, Any] | None:
    """Fetch detail satu kontrak berdasarkan ID."""
    try:
        data = await _get(f"/Contract/{contract_id}", params={
            "expand_dropdowns": "true",
            "with_items": "true",
        })
        if not isinstance(data, dict):
            return None
        return {
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "num": data.get("num", ""),
            "type": _clean_value(data.get("contracttypes_id")),
            "supplier": _clean_value(data.get("suppliers_id")),
            "begin_date": data.get("begin_date", ""),
            "duration": data.get("duration", ""),
            "end_date": data.get("end_date", ""),
            "comment": _strip_html(data.get("comment", "") or ""),
        }
    except Exception as exc:
        logger.warning("get_contract_by_id failed (id=%s): %s", contract_id, exc)
        return None


# ── Knowledge Base ────────────────────────────────────────────────────────────

async def fetch_knowbase_items(
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Cari artikel Knowledge Base berdasarkan kata kunci."""
    cache_key = f"kb:{query}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        data = await _get("/KnowbaseItem", params={
            "search": query,
            "range": f"0-{limit - 1}",
            "expand_dropdowns": "true",
        })
        items: list[Any] = _extract_data(data)
        result = [
            {
                "id": item.get("id", ""),
                "title": item.get("name", ""),
                "answer": _strip_html(item.get("answer", "") or ""),
            }
            for item in items if isinstance(item, dict)
        ]
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("fetch_knowbase_items failed: %s", exc)
        return []


# ── Multiple Items ────────────────────────────────────────────────────────────

async def get_multiple_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch beberapa item GLPI sekaligus dalam satu request."""
    try:
        params: dict[str, Any] = {}
        for idx, item in enumerate(items):
            params[f"items[{idx}][itemtype]"] = item["itemtype"]
            params[f"items[{idx}][items_id]"] = item["items_id"]

        data = await _get("/getMultipleItems", params={
            **params,
            "expand_dropdowns": "true",
        })
        result: list[Any] = _extract_data(data)
        return [item for item in result if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("get_multiple_items failed: %s", exc)
        return []


# ── Search Options ────────────────────────────────────────────────────────────

async def list_search_options(itemtype: str) -> dict[str, Any]:
    """List field (search options) yang tersedia untuk suatu item type."""
    cache_key = f"searchopts:{itemtype}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        data = await _get(f"/listSearchOptions/{itemtype}")
        result: dict[str, Any] = data if isinstance(data, dict) else {}
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("list_search_options failed: %s", exc)
        return {}


# ── Tickets ───────────────────────────────────────────────────────────────────

async def fetch_user_tickets(
    glpi_user_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch tiket IT milik user dari GLPI."""

    def _parse_items(items: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": _first(item, "1", "id"),
                "title": _first(item, "2", "name"),
                "status": _ticket_status_label(_first(item, "12", "status")),
                "last_update": _first(item, "15", "date_mod"),
                "content": _strip_html(_first(item, "21", "content") or "")[:300],
            }
            for item in items if isinstance(item, dict)
        ]

    common_display: dict[str, Any] = {
        "range": f"0-{limit - 1}",
        "sort": 15,
        "order": "DESC",
        "forcedisplay[0]": 1,
        "forcedisplay[1]": 2,
        "forcedisplay[2]": 12,
        "forcedisplay[3]": 15,
        "forcedisplay[4]": 21,
    }

    for field_id in [4, 22, 64]:
        try:
            data = await _get("/search/Ticket", params={
                "criteria[0][field]": field_id,
                "criteria[0][searchtype]": "equals",
                "criteria[0][value]": glpi_user_id,
                **common_display,
            })
            items: list[Any] = _extract_data(data)
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


# ── User Info ─────────────────────────────────────────────────────────────────

async def fetch_user_info(glpi_user_id: int) -> dict[str, Any] | None:
    """Fetch profil user dari GLPI."""
    try:
        data = await _get(f"/User/{glpi_user_id}")
        if not isinstance(data, dict):
            return None

        display_name = (
            data.get("realname", "").strip()
            or data.get("firstname", "").strip()
            or data.get("name", "")
        )
        return {
            "id": data.get("id"),
            "name": display_name,
            "realname": data.get("realname", ""),
            "firstname": data.get("firstname", ""),
            "login": data.get("name", ""),
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


# ── ITIL Categories ───────────────────────────────────────────────────────────

async def fetch_itil_categories(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch kategori ITIL untuk pembuatan tiket."""
    cache_key = f"itil_categories:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        data = await _get("/ITILCategory", params={
            "expand_dropdowns": "true",
            "range": f"0-{limit - 1}",
        })
        items: list[Any] = _extract_data(data)
        result = [
            {
                "id": item.get("1") or item.get("id"),
                "name": item.get("2") or item.get("name", ""),
                "completename": item.get("16") or item.get("completename", ""),
            }
            for item in items if isinstance(item, dict)
        ]
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("fetch_itil_categories failed: %s", exc)
        return []


"""GLPI REST API — Supplier section patch (v5.1 bugfix).

Ganti SELURUH blok "# ── Suppliers" di it_glpi_client.py (baris ~1165 s.d. akhir file)
dengan kode di bawah ini.

==========================================================================
RINGKASAN PERBAIKAN v5.1:

1. FIELD ID MAPPING DIKOREKSI
   ---------------------------
   Versi sebelumnya memetakan field ID Supplier secara spekulatif dan hasilnya
   salah (nomor telepon muncul di kolom Alamat, kota muncul di kolom Telepon,
   dst). Strategi baru menggunakan pendekatan dua-fase:

   Fase A — Endpoint GET /Supplier (expand_dropdowns=true)
     Endpoint ini mengembalikan objek JSON dengan nama field yang eksplisit
     (phonenumber, fax, email, address, postcode, town, state, country).
     Ini digunakan untuk single-supplier lookup dan validasi field.

   Fase B — Endpoint GET /search/Supplier
     Digunakan untuk pencarian dengan filter (criteria). Field ID di sini
     BERBEDA dari nama field di Fase A. Mapping yang benar untuk GLPI 10.x:
       1  → name
       4  → phonenumber  (KOREKSI: sebelumnya 11, sekarang 4)
       5  → fax          (KOREKSI: sebelumnya 12, sekarang 5)
       6  → email        (KOREKSI: sebelumnya 13, sekarang 6)
       19 → address      (KOREKSI: sebelumnya 10, sekarang 19)
       20 → postcode
       21 → town
       22 → state
       23 → country
       80 → entity       (tidak berubah)

   ⚠️  CATATAN: Field ID Search API dapat berbeda di versi GLPI atau konfigurasi
   plugin custom. Jalankan `list_search_options` dengan itemtype='Supplier'
   untuk memverifikasi ID di instance Anda.

2. STRATEGI HYBRID: SEARCH + ENRICH
   ----------------------------------
   search_suppliers() sekarang menggunakan strategi hybrid:
   - Langkah 1: /search/Supplier → dapatkan daftar ID supplier yang cocok
     dengan filter (ini cepat dan mendukung pagination/totalcount).
   - Langkah 2: GET /Supplier/{id} → ambil detail lengkap per supplier
     menggunakan field nama yang eksplisit (tidak bergantung pada field ID).
   Ini menghilangkan ketergantungan pada field ID Search API yang tidak stabil,
   sambil tetap mempertahankan kemampuan filter dan totalcount yang akurat.

3. TAMBAH count_suppliers()
   -------------------------
   Fungsi baru yang hanya mengambil totalcount tanpa fetch semua data.
   Analog dengan get_total_computers_count(). Digunakan oleh CountSuppliersTool
   untuk menjawab pertanyaan "ada berapa supplier?" dengan cepat (1 API call).

4. ID SUPPLIER SEKARANG AKURAT
   ----------------------------
   _parse_supplier_detail() mengambil `id` langsung dari endpoint /Supplier/{id}
   yang selalu mengembalikan field `id` sebagai integer — tidak perlu fallback
   ke key "2" seperti di Search API.
==========================================================================
"""

# ── Suppliers ─────────────────────────────────────────────────────────────────
#
SUPPLIER_MAX_ENRICH: int = 8
# Field ID untuk /search/Supplier (GLPI 10.x — verifikasi via /listSearchOptions/Supplier)
# Digunakan HANYA untuk parameter criteria[] pada search request.
# Untuk parsing hasil, kita fetch ulang via GET /Supplier/{id} agar field eksplisit.
_SUPPLIER_FILTER_FIELD_IDS: dict[str, int] = {
    "name":    1,    # name
    "entity":  80,   # entities_id (konsisten di semua tipe GLPI)
    "address": 19,   # address
    "phone":   4,    # phonenumber
    "fax":     5,    # fax
    "email":   6,    # email
}

# forcedisplay minimal — kita hanya butuh field `id` (field 2) dari search response
# agar bisa fetch detail via GET /Supplier/{id}.
# Menambahkan `name` (field 1) sebagai fallback display jika enrich gagal.
_SUPPLIER_SEARCH_MINIMAL_DISPLAY: dict[str, int] = {
    "forcedisplay[0]": 2,   # id
    "forcedisplay[1]": 1,   # name (fallback)
}


def _parse_supplier_detail(data: dict[str, Any]) -> dict[str, Any]:
    """Parse response dari GET /Supplier/{id} ke format standar.

    Menggunakan field nama eksplisit dari endpoint detail (bukan field ID
    numerik dari Search API) — hasilnya selalu akurat terlepas dari versi GLPI.

    GLPI menyimpan alamat dalam beberapa sub-field:
      address  → jalan/gedung
      postcode → kode pos
      town     → kota
      state    → provinsi
      country  → negara
    Fungsi ini menggabungkannya menjadi satu string `address` yang lengkap.

    Args:
        data: Raw dict dari GET /Supplier/{id}?expand_dropdowns=true.

    Returns:
        Dict standar: id, name, entity, address, phone, fax, email.
    """
    # Gabungkan komponen alamat menjadi satu string
    addr_parts = [
        data.get("address", ""),
        data.get("postcode", ""),
        data.get("town", ""),
        data.get("state", ""),
        data.get("country", ""),
    ]
    address = ", ".join(p.strip() for p in addr_parts if p and str(p).strip())

    return {
        "id":      data.get("id", ""),
        "name":    data.get("name", "") or "",
        "entity":  _clean_value(data.get("entities_id")),
        "address": address or "",
        "phone":   data.get("phonenumber", "") or "",
        "fax":     data.get("fax", "") or "",
        "email":   data.get("email", "") or "",
    }


async def _enrich_supplier_ids(
    supplier_ids: list[int | str],
) -> list[dict[str, Any]]:
    """Fetch detail lengkap untuk setiap supplier ID secara concurrent.

    Menggunakan GET /Supplier/{id}?expand_dropdowns=true agar field nama
    (phonenumber, fax, email, address, town, dll) selalu eksplisit dan benar.

    Concurrency dibatasi via asyncio.Semaphore (maks 5 request simultan)
    untuk mencegah beban berlebih pada server GLPI saat list supplier besar.

    Args:
        supplier_ids: List ID supplier integer.

    Returns:
        List dict supplier terparse, dengan item None yang difilter keluar.
    """
    # v8.0: Concurrency diturunkan 5 → 3 agar server GLPI tidak kelebihan
    # beban. Dengan SUPPLIER_MAX_ENRICH=8, maksimal 3 request berjalan
    # bersamaan = lebih stabil di GLPI production.
    semaphore = asyncio.Semaphore(3)

    # v8.0: Per-request timeout 8 detik. Jika satu GET /Supplier/{id} tidak
    # selesai dalam 8 detik (server lambat / congestion), skip dan kembalikan
    # None — biarkan data lain tetap berjalan.
    # Dengan 8 ID dan semaphore 3: worst case ≈ 3 batch × 8s = ~24s total.
    _ENRICH_TIMEOUT_S: float = 8.0

    async def _fetch_one(sid: int | str) -> dict[str, Any] | None:
        async with semaphore:
            try:
                data = await asyncio.wait_for(
                    _get(
                        f"/Supplier/{sid}",
                        params={"expand_dropdowns": "true"},
                    ),
                    timeout=_ENRICH_TIMEOUT_S,
                )
                if isinstance(data, dict) and data.get("id"):
                    return _parse_supplier_detail(data)
                return None
            except asyncio.TimeoutError:
                logger.warning(
                    "_enrich_supplier_ids: timeout (%.0fs) for id=%s — skip",
                    _ENRICH_TIMEOUT_S, sid,
                )
                return None
            except Exception as exc:
                logger.debug("_enrich_supplier_ids: failed for id=%s: %s", sid, exc)
                return None

    tasks = [_fetch_one(sid) for sid in supplier_ids]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r is not None]


async def count_suppliers() -> int:
    """Hitung jumlah total supplier yang terdaftar di GLPI (exact count).

    Hanya 1 API call — sangat cepat. Digunakan oleh CountSuppliersTool
    untuk menjawab pertanyaan "ada berapa supplier?" tanpa fetch semua data.

    Returns:
        Integer jumlah total supplier, atau 0 jika gagal.
    """
    try:
        data = await _get("/search/Supplier", params={
            "range": "0-1",    # Minta minimal data — kita hanya butuh totalcount
        })
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
) -> "PagedResult":
    """Cari supplier di GLPI dengan filter dinamis.

    Strategi hybrid dua-fase:
    1. GET /search/Supplier dengan criteria[] → dapatkan list ID + totalcount exact.
    2. GET /Supplier/{id} per supplier → enrich dengan field detail yang eksplisit.

    Fase 2 menggunakan asyncio.gather() untuk concurrent requests — performanya
    baik meski ada banyak supplier (misal 30 supplier = 30 concurrent requests).

    Args:
        name   : Filter nama supplier (partial match, contains).
        entity : Filter entity GLPI (partial match, contains).
        address: Filter alamat (partial match, contains).
        phone  : Filter nomor telepon (partial match, contains).
        fax    : Filter nomor fax (partial match, contains).
        email  : Filter email (partial match, contains).
        limit  : Jumlah maksimal hasil (default 50).

    Returns:
        PagedResult dengan items (list supplier detail), totalcount exact,
        fetched, dan truncated flag.
    """
    # ── Fase 1: Bangun criteria params ────────────────────────────────────────
    filter_map: list[tuple[str, str | None]] = [
        ("name",    name),
        ("entity",  entity),
        ("address", address),
        ("phone",   phone),
        ("fax",     fax),
        ("email",   email),
    ]
    active_filters = [
        (field, str(val).strip())
        for field, val in filter_map
        if val and str(val).strip()
    ]

    base_params: dict[str, Any] = {
        "expand_dropdowns": "true",
        **_SUPPLIER_SEARCH_MINIMAL_DISPLAY,
    }

    for idx, (field_name, value) in enumerate(active_filters):
        field_id = _SUPPLIER_FILTER_FIELD_IDS[field_name]
        base_params[f"criteria[{idx}][field]"]      = field_id
        base_params[f"criteria[{idx}][searchtype]"] = "contains"
        base_params[f"criteria[{idx}][value]"]      = value
        if idx > 0:
            base_params[f"criteria[{idx}][link]"] = "AND"

    logger.info(
        "search_suppliers: filters=%s limit=%d",
        [(n, v) for n, v in active_filters],
        limit,
    )

    # ── Fase 1: GET /search/Supplier → ambil ID list + totalcount ─────────────
    try:
        # Minta sample_size = limit agar pagination minimal
        search_params = {**base_params, "range": f"0-{min(limit, SUPPLIER_MAX_ENRICH) - 1}"}
        raw = await _get("/search/Supplier", params=search_params)
    except Exception as exc:
        logger.error("search_suppliers: search phase failed: %s", exc)
        return PagedResult(items=[], totalcount=0, fetched=0, truncated=False)

    totalcount: int = 0
    if isinstance(raw, dict):
        totalcount = int(raw.get("totalcount", 0))

    raw_items = _extract_data(raw)
    search_items = [item for item in raw_items if isinstance(item, dict)]

    if not search_items:
        return PagedResult(items=[], totalcount=totalcount, fetched=0, truncated=False)

    # ── Hard cap: jumlah supplier yang akan di-enrich (fase 2) ───────────────
    # v8.0: Diturunkan 20 → 8.
    # Alasan: 20 concurrent GET /Supplier/{id} (meski dibatasi semaphore 5)
    # tetap memakan ~15-25 detik pada GLPI lambat → akumulasi agent loop
    # melewati timeout 110 detik.
    # 8 supplier = ~6-10 detik enrich, cukup representatif, aman untuk
    # LLM token budget, dan tidak memicu looping agent berulang.
    # totalcount exact tetap dikembalikan sehingga LLM tahu jumlah sebenarnya.
    

    # Extract supplier IDs dari search response
    # Search API mengembalikan field "2" sebagai ID (sesuai forcedisplay[0]=2)
    supplier_ids: list[int | str] = []
    for item in search_items[:min(limit, SUPPLIER_MAX_ENRICH)]:
        sid = _first(item, "2", "id")
        if sid and str(sid) not in ("", "0"):
            try:
                supplier_ids.append(int(sid))
            except (ValueError, TypeError):
                supplier_ids.append(sid)

    if not supplier_ids:
        # Fallback: jika ID tidak bisa diekstrak, gunakan parsing minimal dari search
        fallback_items = [
            {
                "id":      _first(item, "2", "id") or "-",
                "name":    _first(item, "1", "name") or "-",
                "entity":  "",
                "address": "",
                "phone":   "",
                "fax":     "",
                "email":   "",
            }
            for item in search_items[:min(limit, SUPPLIER_MAX_ENRICH)]
        ]
        return PagedResult(
            items=fallback_items,
            totalcount=totalcount or len(fallback_items),
            fetched=len(fallback_items),
            truncated=(totalcount > len(fallback_items)),
        )

    # ── Fase 2: Enrich via GET /Supplier/{id} → field eksplisit ──────────────
    enriched = await _enrich_supplier_ids(supplier_ids)

    fetched = len(enriched)
    # truncated = True jika totalcount lebih besar dari yang kita enrich
    truncated = totalcount > fetched

    logger.info(
        "search_suppliers: DONE totalcount=%d enriched=%d truncated=%s",
        totalcount, fetched, truncated,
    )

    return PagedResult(
        items=enriched,
        totalcount=totalcount or fetched,
        fetched=fetched,
        truncated=truncated,
    )


async def fetch_suppliers(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch daftar supplier/vendor (backward-compatible wrapper).

    Untuk pencarian dengan filter, panggil search_suppliers() langsung.

    Args:
        limit: Jumlah maksimal supplier yang dikembalikan.

    Returns:
        List dict supplier dengan field: id, name, entity, address, phone, fax, email.
    """
    cache_key = f"suppliers_all:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    try:
        result = await search_suppliers(limit=limit)
        items = result["items"]
        _cache_set(cache_key, items)
        return items
    except Exception as exc:
        logger.warning("fetch_suppliers fallback failed: %s", exc)
        return []
# ── Shared Search API constants ───────────────────────────────────────────────

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


def _parse_computer_search_item(item: dict[str, Any]) -> dict[str, Any]:
    """Parse satu item dari GLPI Search API ke format standar enriched dict."""
    return {
        "id":           _first(item, "2", "id"),
        "name":         _first(item, "1", "name"),
        "serial":       _first(item, "5", "serial"),
        "otherserial":  _first(item, "6", "otherserial"),
        "type":         _clean_value(_first(item, "4", "computertypes_id", "type")),
        "model":        _clean_value(_first(item, "40", "computermodels_id", "model")),
        "status":       _clean_value(_first(item, "31", "states_id", "status")),
        "location":     _clean_value(_first(item, "3", "locations_id", "location")),
        "user":         _clean_value(_first(item, "24", "users_id", "user")),
        "entity":       _clean_value(_first(item, "80", "entities_id", "entity")),
        "manufacturer": _clean_value(_first(item, "23", "manufacturers_id", "manufacturer")),
        "os":           _clean_value(_first(item, "14", "operatingsystems_id", "os")),
        "date_mod":     _first(item, "19", "date_mod"),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _first(item: dict[str, Any], *keys: str) -> Any:
    """Kembalikan nilai pertama yang tidak kosong dari item berdasarkan keys."""
    for k in keys:
        v = item.get(k)
        if v is not None and v != "":
            return v
    return ""


def _strip_html(text: str) -> str:
    """Hapus tag HTML dari teks GLPI."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _extract_data(data: dict[str, Any] | list[Any]) -> list[Any]:
    """Unwrap GLPI search response envelope {'data': [...]} atau pass-through list."""
    if isinstance(data, dict) and "data" in data:
        return data["data"]  # type: ignore[return-value]
    if isinstance(data, list):
        return data
    return []


def _clean_value(value: Any) -> str:
    """Normalise nilai dropdown GLPI ke string bersih.

    Nilai 0 atau "0" (unset foreign key) dikembalikan sebagai "" agar UI
    menampilkan "-" bukan "0" yang tidak bermakna.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s in ("", "0", "None"):
        return ""
    return s


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