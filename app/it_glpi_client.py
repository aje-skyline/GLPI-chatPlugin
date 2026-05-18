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

CHANGELOG (bug-fix v2.1):
  asyncio.Lock() objects MUST NOT be created at module level.  A Lock is
  bound to the event loop that was running when it was constructed.  Since
  tools.py now uses a single persistent background loop (started *after*
  module import), any Lock created at import time would be bound to a
  *different* (or non-existent) loop and raise "got Future attached to a
  different loop" / "Event loop is closed" on first use.

  Fix: all Locks are created lazily inside async functions on first call,
  which guarantees they are bound to the correct running loop.
"""

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# GLPI API base URL — use glpi_api_url from config directly (e.g., http://glpi/apirest.php)
GLPI_API_BASE: str = settings.glpi_api_url.rstrip("/")

# Headers required for every GLPI API request
_BASE_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "App-Token": settings.glpi_app_token,
}

# ── Session state ─────────────────────────────────────────────────────────────
# Lock is created lazily on first use so it binds to the correct event loop.
_session_token: str | None = None
_session_lock: asyncio.Lock | None = None


def _get_session_lock() -> asyncio.Lock:
    """Return the session lock, creating it inside the running loop if needed."""
    global _session_lock
    if _session_lock is None:
        _session_lock = asyncio.Lock()
    return _session_lock


# ── Shared HTTP client (connection pooling) ──────────────────────────────────
# Lock is also lazy for the same reason.
_http_client: httpx.AsyncClient | None = None
_http_client_lock: asyncio.Lock | None = None


def _get_http_client_lock() -> asyncio.Lock:
    """Return the HTTP client lock, creating it inside the running loop if needed."""
    global _http_client_lock
    if _http_client_lock is None:
        _http_client_lock = asyncio.Lock()
    return _http_client_lock
 
async def _get_http_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, creating it once on first call."""
    global _http_client
    # Fast-path: client already exists and is open — no lock needed.
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    async with _get_http_client_lock():
        # Double-checked locking: another coroutine may have created it
        # while we waited for the lock.
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=20,
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

# ── Simple TTL cache for near-static GLPI data ───────────────────────────────
# Categories, suppliers, and KB articles rarely change between agent sessions.
# Caching them avoids redundant API round-trips and speeds up every conversation.

_CACHE_TTL_SECONDS: int = 300
_ttl_cache: dict[str, dict[str, Any]] = {}

def _cache_get(key : str) -> Any | None:
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

# ── Session Management ──────────────────────────────────────────────────────

async def _init_session() -> str:
    """Create a new GLPI session using the configured user_token (service account).
 
    Endpoint: GET /initSession
    Headers : Authorization: user_token {glpi_user_token}
 
    NOTE: Must only be called while holding ``_session_lock`` so that concurrent
    requests don't each open their own redundant GLPI sessions.
 
    Returns:
        A Session-Token string valid until killed or expired.
    """
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
    """Close a GLPI session (best-effort, errors are silently ignored).
 
    Endpoint: GET /killSession
    """
    try:
        client = await _get_http_client()
        await client.get(
            f"{GLPI_API_BASE}/killSession",
            headers={**_BASE_HEADERS, "Session-Token": token},
        )
    except Exception as exc:
        logger.warning("GLPI killSession failed (ignored): %s", exc)
 
 
async def _get_session_token() -> str:
    """Return the cached session token, creating one if absent.

    Protected by lazy ``_session_lock``: if two coroutines arrive simultaneously
    with ``_session_token = None``, only the first acquires the lock and calls
    ``_init_session()``. The second then finds the token already populated and
    returns it immediately — no duplicate sessions are created.
    """
    global _session_token
    # Fast-path: token already present, no lock needed.
    if _session_token:
        return _session_token
    async with _get_session_lock():
        # Re-check after acquiring the lock: another coroutine may have
        # already refreshed the token while we were waiting.
        if not _session_token:
            _session_token = await _init_session()
    return _session_token
 
 
async def _get(
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    """Authenticated GET request to the GLPI API.
 
    Uses the shared ``_http_client`` for connection pooling and automatically
    refreshes the session token (under ``_session_lock``) on HTTP 401, then
    retries once.
 
    Args:
        path  : URL path appended to GLPI_API_BASE (e.g., '/Computer').
        params: Optional query-string parameters.
 
    Returns:
        Parsed JSON response (dict or list).
    """
    global _session_token
 
    async def _do_request(token: str) -> httpx.Response:
        client = await _get_http_client()
        return await client.get(
            f"{GLPI_API_BASE}{path}",
            headers={**_BASE_HEADERS, "Session-Token": token},
            params=params,
        )
 
    token: str = await _get_session_token()
    resp: httpx.Response = await _do_request(token)
 
    # Refresh session on 401 (expired) and retry once.
    # The lock ensures only one coroutine performs the refresh even when
    # multiple requests expire concurrently.
    if resp.status_code == 401:
        logger.info("GLPI session expired — refreshing and retrying")
        async with _get_session_lock():
            # Another coroutine may have already refreshed the token.
            if _session_token == token:
                _session_token = None
                _session_token = await _init_session()
            token = _session_token  # type: ignore[assignment]
        resp = await _do_request(token)
 
    resp.raise_for_status()
    return resp.json()

# ── Assets ──────────────────────────────────────────────────────────────────

async def get_all_computers(limit: int = 50, has_serial: bool = False) -> list[dict[str, Any]]:
    """Fetch all computers registered in GLPI.

    Postman: GET /Computer?expand_dropdowns=true&range=0-49

    Args:
        limit     : Maximum number of records to return (maps to range=0-{limit-1}).
        has_serial: If True, use Search API with server-side filter to return only
                    computers that have a non-empty serial number (E.2 improvement).

    Returns:
        List of computer dicts with human-readable dropdown values including entity,
        manufacturer, operating system, and last-update fields (B enrichment).
    """
    # ── Server-side serial filter via Search API (E.2) ────────────────────────
    if has_serial:
        try:
            params: dict[str, Any] = {
                "criteria[0][field]": 5,              # Serial Number field
                "criteria[0][searchtype]": "isnotempty",
                "range": f"0-{limit - 1}",
                "expand_dropdowns": "true",
                **_COMPUTER_SEARCH_FORCEDISPLAY,
            }
            data = await _get("/search/Computer", params=params)
            items: list[Any] = _extract_data(data)
            return [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
        except Exception as exc:
            logger.warning("get_all_computers (has_serial, Search API) failed: %s — falling back", exc)
            # Fall through to the standard GET /Computer approach

    # ── Standard bulk fetch via GET /Computer ─────────────────────────────────
    try:
        data = await _get("/Computer", params={
            "expand_dropdowns": "true",
            "range": f"0-{limit - 1}",
        })
        items = _extract_data(data)
        result = [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "serial": item.get("serial", ""),
                "otherserial": item.get("otherserial", ""),
                # computertypes_id = hardware category (Notebook, Desktop, Server, …)
                "type": _clean_value(item.get("computertypes_id")),
                # computermodels_id = specific product name (e.g. ESPRIMO Mobile U9200)
                "model": _clean_value(item.get("computermodels_id")) or _clean_value(item.get("model")),
                "status": _clean_value(item.get("states_id")) or _clean_value(item.get("status")),
                "location": _clean_value(item.get("locations_id")) or _clean_value(item.get("location")),
                "user": _clean_value(item.get("users_id")) or _clean_value(item.get("user")),
                # ── B: GLPI 11 missing fields ──────────────────────────────────
                "entity": _clean_value(item.get("entities_id")),
                "manufacturer": _clean_value(item.get("manufacturers_id")),
                "os": _clean_value(item.get("operatingsystems_id")),
                "date_mod": item.get("date_mod", ""),
            }
            for item in items if isinstance(item, dict)
        ]
        # Client-side fallback if server-side isnotempty failed but has_serial=True
        if has_serial:
            result = [c for c in result if c.get("serial", "").strip()]
        return result
    except Exception as exc:
        logger.warning("get_all_computers failed: %s", exc)
        return []

async def get_total_computers_count() -> int:
    """Fetch the total number of computers registered in GLPI."""
    try:
        data = await _get("/search/Computer", params={
            "is_recursive": "1",
            "range": "0-1"
        })
        if isinstance(data, dict) and "totalcount" in data:
            return int(data["totalcount"])
        return 0
    except Exception as exc:
        logger.warning("get_total_computers_count failed: %s", exc)
        return 0
    

async def get_computer_by_id(computer_id: int) -> dict[str, Any] | None:
    """Fetch a single computer with its financial data and linked contracts.

    Postman: GET /Computer/{id}?expand_dropdowns=true
             &with_infocoms=true&with_contracts=true&with_operatingsystems=true

    Args:
        computer_id: GLPI Computer ID.

    Returns:
        Computer dict (with nested _infocoms / _contracts / _operatingsystems),
        or None if not found. Includes all GLPI 11 dashboard columns (B enrichment).
    """
    try:
        data = await _get(f"/Computer/{computer_id}", params={
            "expand_dropdowns": "true",
            "with_infocoms": "true",
            "with_contracts": "true",
            "with_operatingsystems": "true",   # B: Operating System
        })
        if not isinstance(data, dict):
            return None

        infocoms: dict[str, Any] = data.get("_infocoms") or {}

        # ── Operating System ─────────────────────────────────────────────────
        # Prefer the direct field (if GLPI caches it); fall back to the
        # _operatingsystems nested list returned by with_operatingsystems=true.
        os_name: str = _clean_value(data.get("operatingsystems_id"))
        if not os_name:
            os_list: list[Any] = data.get("_operatingsystems") or []
            if os_list and isinstance(os_list[0], dict):
                os_name = _clean_value(
                    os_list[0].get("operatingsystems_id")
                    or os_list[0].get("name", "")
                )

        return {
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "serial": data.get("serial", ""),
            "otherserial": data.get("otherserial", ""),
            # computertypes_id = hardware category (Notebook, Desktop, Server, …)
            "type": _clean_value(data.get("computertypes_id")),
            # computermodels_id = specific product name (e.g. ESPRIMO Mobile U9200)
            "model": _clean_value(data.get("computermodels_id")),
            "status": _clean_value(data.get("states_id")),
            "location": _clean_value(data.get("locations_id")),
            "user": _clean_value(data.get("users_id")),
            # ── B: GLPI 11 missing fields ────────────────────────────────────
            "entity": _clean_value(data.get("entities_id")),
            "manufacturer": _clean_value(data.get("manufacturers_id")),
            "os": os_name,
            "contact": data.get("contact", ""),          # Alternate Username
            "comment": _strip_html(data.get("comment", "") or ""),
            "date_mod": data.get("date_mod", ""),        # Last Update
            # Infocom (financial) fields
            "buy_date": infocoms.get("buy_date", ""),
            "use_date": infocoms.get("use_date", ""),    # Startup date
            "warranty_duration": infocoms.get("warranty_duration", ""),
            "warranty_date": infocoms.get("warranty_date", ""),   # Warranty expiry
            "value": infocoms.get("value", ""),
            "supplier": infocoms.get("suppliers_id", ""),
            # Linked contracts
            "contracts": [
                {
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "num": c.get("num", ""),
                    "begin_date": c.get("begin_date", ""),
                    "duration": c.get("duration", ""),
                    "end_date": c.get("end_date", ""),
                }
                for c in (data.get("_contracts") or [])
                if isinstance(c, dict)
            ],
        }
    except Exception as exc:
        logger.warning("get_computer_by_id failed (id=%s): %s", computer_id, exc)
        return None


async def get_user_assets(user_id: int) -> list[dict[str, Any]]:
    """Fetch computers owned by a specific user.
 
    Strategy 1 (primary): GLPI Search API — queries directly by ``users_id``
    server-side. More precise and efficient than bulk-fetching all computers.
    Multiple candidate field IDs are tried to handle GLPI version differences:
      - Field 24 : User (most common in GLPI 10.x / 11)
      - Field 4  : Type field (skip — causes false matches)
      - Field 70 : users_id alternate
      - Field 45 : user field in some GLPI setups
 
    Strategy 2 (fallback): GET /Computer with ``expand_dropdowns=true`` —
    fetches up to 200 records and filters ``users_id`` client-side. Mirrors
    what chat.php does with a direct DB query.
 
    Args:
        user_id: GLPI User ID.
 
    Returns:
        List of computer dicts owned by the user (includes all GLPI 11
        dashboard columns: entity, manufacturer, OS, otherserial, location).
    """

    def _normalise(item: dict[str, Any]) -> dict[str, Any]:
        """Map raw GET /Computer item to the enriched output dict (Strategy 2)."""
        return {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "serial": item.get("serial", ""),
            "otherserial": item.get("otherserial", ""),    # A.3: always include
            "type": _clean_value(item.get("computertypes_id")),
            "model": _clean_value(item.get("computermodels_id")) or _clean_value(item.get("model")),
            "status": _clean_value(item.get("states_id")) or _clean_value(item.get("status")),
            "location": _clean_value(item.get("locations_id")) or _clean_value(item.get("location")),
            "user": _clean_value(item.get("users_id")) or _clean_value(item.get("user")),
            # ── B: GLPI 11 enrichment ──────────────────────────────────────────
            "entity": _clean_value(item.get("entities_id")),
            "manufacturer": _clean_value(item.get("manufacturers_id")),
            "os": _clean_value(item.get("operatingsystems_id")),
            "date_mod": item.get("date_mod", ""),
        }

    # ── Strategy 1 (primary): Search API — server-side filter by users_id ────
    # GLPI field numbers for "users_id" on Computer differ by version/config.
    # We try all known candidates and return on first non-empty result.
    # IMPORTANT: forcedisplay uses CORRECT GLPI 11 field IDs:
    #   1=Name, 2=ID, 3=Location, 4=Type, 5=Serial, 6=Inventory No, 14=OS,
    #   23=Manufacturer, 31=Status, 40=Model, 80=Entity
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
                "range": "0-199",                         # E.1: was 0-99, raised to 199
                "expand_dropdowns": "true",
                # ── A.1 FIX: correct GLPI 11 field numbers ────────────────────
                "forcedisplay[0]": 1,    # Name
                "forcedisplay[1]": 2,    # ID
                "forcedisplay[2]": 3,    # Location
                "forcedisplay[3]": 4,    # Type
                "forcedisplay[4]": 5,    # Serial Number
                "forcedisplay[5]": 6,    # Inventory Number (otherserial)
                "forcedisplay[6]": 23,   # Manufacturer
                "forcedisplay[7]": 31,   # Status
                "forcedisplay[8]": 40,   # Model
                "forcedisplay[9]": 80,   # Entity
                "forcedisplay[10]": field_id,  # The user field we filtered by
            }
            data = await _get("/search/Computer", params=params)
            raw_count = data.get("totalcount", 0) if isinstance(data, dict) else 0
            items: list[Any] = _extract_data(data)

            if items:
                logger.info(
                    "get_user_assets (strategy 1 Search API, field=%s '%s'): found %d results",
                    field_id, label, len(items),
                )
                return [
                    {
                        # ── A.1 FIX: correct Search API field→key mapping ────
                        "id": _first(item, "2", "id"),
                        "name": _first(item, "1", "name"),
                        "serial": _first(item, "5", "serial"),
                        "otherserial": _first(item, "6", "otherserial"),  # A.3 fix
                        "type": _clean_value(_first(item, "4", "computertypes_id", "type")),
                        "model": _clean_value(_first(item, "40", "computermodels_id", "model")),
                        "status": _clean_value(_first(item, "31", "states_id", "status")),
                        "location": _clean_value(_first(item, "3", "locations_id", "location")),
                        "user": _clean_value(_first(item, str(field_id), "users_id", "user")),
                        # ── B: enrichment fields ──────────────────────────────
                        "entity": _clean_value(_first(item, "80", "entities_id", "entity")),
                        "manufacturer": _clean_value(_first(item, "23", "manufacturers_id", "manufacturer")),
                        "os": _clean_value(_first(item, "14", "operatingsystems_id", "os")),
                        "date_mod": _first(item, "19", "date_mod"),
                    }
                    for item in items if isinstance(item, dict)
                ]

            logger.debug(
                "get_user_assets (strategy 1 Search API, field=%s '%s'): 0 results (totalcount=%s)",
                field_id, label, raw_count,
            )
        except Exception as exc:
            logger.debug(
                "get_user_assets (strategy 1 Search API, field=%s '%s') error: %s",
                field_id, label, exc,
            )

    # ── Strategy 2 (fallback): GET /Computer, filter client-side ─────────────
    # Capped at 200 records — the Search API above handles the common case;
    # this fallback exists only for edge-case GLPI configs where none of the
    # Search API field IDs map correctly.
    try:
        data = await _get("/Computer", params={
            "expand_dropdowns": "true",
            "range": "0-199",
            "is_deleted": "0",
        })
        all_computers: list[Any] = _extract_data(data)

        # Filter client-side — users_id matches either as int or string
        user_computers = [
            item for item in all_computers
            if isinstance(item, dict)
            and str(item.get("users_id", "")) == str(user_id)
            and str(item.get("is_deleted", "0")) == "0"
        ]

        if user_computers:
            logger.info(
                "get_user_assets (strategy 2 bulk GET): found %d computers for user_id=%s",
                len(user_computers), user_id,
            )
            return [_normalise(c) for c in user_computers]

        logger.info(
            "get_user_assets (strategy 2 bulk GET): no match for user_id=%s in %d computers",
            user_id, len(all_computers),
        )
    except Exception as exc:
        logger.warning(
            "get_user_assets strategy 2 failed (user_id=%s): %s",
            user_id, exc,
        )

    logger.warning(
        "get_user_assets: all strategies exhausted, no assets found for user_id=%s",
        user_id,
    )
    return []


async def search_computer_by_name(name: str, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch computers by their name using the GLPI search API.

    A.2 FIX: Enriched output — now returns all GLPI 11 dashboard fields
    (entity, manufacturer, location, OS, date_mod) in addition to the
    previous minimalist id+name output.

    Args:
        name : Nama atau substring nama komputer yang dicari.
        limit: Jumlah maksimal hasil yang dikembalikan (default 50).

    Returns:
        List of computer dicts with full GLPI 11 column coverage.
    """
    try:
        params: dict[str, Any] = {
            "criteria[0][field]": 1,
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": name,
            "range": f"0-{limit - 1}",
            "expand_dropdowns": "true",
            # ── A.2 FIX: request all GLPI 11 relevant fields ─────────────────
            "forcedisplay[0]": 1,    # Name
            "forcedisplay[1]": 2,    # ID
            "forcedisplay[2]": 3,    # Location
            "forcedisplay[3]": 4,    # Type
            "forcedisplay[4]": 5,    # Serial Number
            "forcedisplay[5]": 6,    # Inventory Number (otherserial)
            "forcedisplay[6]": 14,   # Operating System
            "forcedisplay[7]": 19,   # Last Update (date_mod)
            "forcedisplay[8]": 23,   # Manufacturer
            "forcedisplay[9]": 31,   # Status
            "forcedisplay[10]": 40,  # Model
            "forcedisplay[11]": 80,  # Entity
        }

        data = await _get("/search/Computer", params=params)
        items: list[Any] = _extract_data(data)

        return [
            {
                # ── Core identity ─────────────────────────────────────────────
                "id":           _first(item, "2", "id"),
                "name":         _first(item, "1", "name"),
                "serial":       _first(item, "5", "serial"),
                "otherserial":  _first(item, "6", "otherserial"),
                # ── Type / model ──────────────────────────────────────────────
                "type":         _clean_value(_first(item, "4", "computertypes_id")),
                "model":        _clean_value(_first(item, "40", "computermodels_id", "model")),
                # ── Status / location ─────────────────────────────────────────
                "status":       _clean_value(_first(item, "31", "states_id", "status")),
                "location":     _clean_value(_first(item, "3", "locations_id", "location")),
                # ── B: GLPI 11 enrichment ─────────────────────────────────────
                "entity":       _clean_value(_first(item, "80", "entities_id")),
                "manufacturer": _clean_value(_first(item, "23", "manufacturers_id")),
                "os":           _clean_value(_first(item, "14", "operatingsystems_id")),
                "date_mod":     _first(item, "19", "date_mod"),
            }
            for item in items if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.warning("search_computer_by_name failed: %s", exc)
        return []


def _first(item: dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty value from ``item`` matching any of ``keys``."""
    for k in keys:
        v = item.get(k)
        if v is not None and v != "":
            return v
    return ""


# ── Shared Search API constants ───────────────────────────────────────────────
# Standard GLPI 11 Computer search field IDs used across all Search API calls.
# If your GLPI instance uses different field IDs, run list_search_options('Computer')
# to verify and update accordingly.

#: forcedisplay params common to ALL Computer search queries.
_COMPUTER_SEARCH_FORCEDISPLAY: dict[str, int] = {
    "forcedisplay[0]":  1,    # Name
    "forcedisplay[1]":  2,    # ID
    "forcedisplay[2]":  3,    # Location
    "forcedisplay[3]":  4,    # Type
    "forcedisplay[4]":  5,    # Serial Number
    "forcedisplay[5]":  6,    # Inventory Number (otherserial)
    "forcedisplay[6]":  14,   # Operating System
    "forcedisplay[7]":  19,   # Last Update (date_mod)
    "forcedisplay[8]":  23,   # Manufacturer
    "forcedisplay[9]":  31,   # Status
    "forcedisplay[10]": 40,   # Model
    "forcedisplay[11]": 80,   # Entity
}

#: Infocom warranty expiration field ID (linked to Computer via Search API).
#: This is typically field 162 in GLPI 10/11. Use list_search_options('Computer')
#: → look for "Warranty expiration date" or "Date d'expiration de garantie".
_INFOCOM_WARRANTY_FIELD: int = 162


def _parse_computer_search_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw GLPI Search API Computer item to the standard enriched dict.

    This shared parser is used by all Computer Search API functions so field
    mapping is defined exactly once.

    Args:
        item: Raw dict from GLPI Search API (keys are field ID strings, e.g. "2").

    Returns:
        Normalised computer dict with all GLPI 11 dashboard columns.
    """
    return {
        "id":           _first(item, "2", "id"),
        "name":         _first(item, "1", "name"),
        "serial":       _first(item, "5", "serial"),
        "otherserial":  _first(item, "6", "otherserial"),
        "type":         _clean_value(_first(item, "4", "computertypes_id", "type")),
        "model":        _clean_value(_first(item, "40", "computermodels_id", "model")),
        "status":       _clean_value(_first(item, "31", "states_id", "status")),
        "location":     _clean_value(_first(item, "3", "locations_id", "location")),
        "entity":       _clean_value(_first(item, "80", "entities_id", "entity")),
        "manufacturer": _clean_value(_first(item, "23", "manufacturers_id", "manufacturer")),
        "os":           _clean_value(_first(item, "14", "operatingsystems_id", "os")),
        "date_mod":     _first(item, "19", "date_mod"),
    }


# ── New Filter Functions (C: new tools) ───────────────────────────────────────

async def get_computers_by_status(
    status_filter: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch computers filtered by status name (server-side).

    Uses GLPI Search API with ``contains`` on field 31 (states_id).

    Args:
        status_filter: Status label to search for (e.g. 'aktif', 'rusak', 'disposed').
                       Case-insensitive contains search.
        limit        : Maximum number of results.

    Returns:
        List of computer dicts matching the given status.
    """
    try:
        params: dict[str, Any] = {
            "criteria[0][field]": 31,              # Status (states_id)
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": status_filter,
            "range": f"0-{limit - 1}",
            "expand_dropdowns": "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
        data = await _get("/search/Computer", params=params)
        items: list[Any] = _extract_data(data)
        return [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("get_computers_by_status failed (filter=%s): %s", status_filter, exc)
        return []


async def get_computers_by_location(
    location_filter: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch computers filtered by location name (server-side).

    Uses GLPI Search API with ``contains`` on field 3 (locations_id).

    Args:
        location_filter: Location label to search for (e.g. 'lantai 3', 'gedung A').
                         Case-insensitive contains search.
        limit          : Maximum number of results.

    Returns:
        List of computer dicts at the given location.
    """
    try:
        params: dict[str, Any] = {
            "criteria[0][field]": 3,               # Location (locations_id)
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": location_filter,
            "range": f"0-{limit - 1}",
            "expand_dropdowns": "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
        data = await _get("/search/Computer", params=params)
        items: list[Any] = _extract_data(data)
        return [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("get_computers_by_location failed (filter=%s): %s", location_filter, exc)
        return []


async def get_computers_by_os(
    os_filter: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch computers filtered by operating system name (server-side).

    Uses GLPI Search API with ``contains`` on field 14 (operatingsystems_id).

    Args:
        os_filter: OS label to search for (e.g. 'Windows 10', 'Ubuntu').
                   Case-insensitive contains search.
        limit    : Maximum number of results.

    Returns:
        List of computer dicts running the given OS.
    """
    try:
        params: dict[str, Any] = {
            "criteria[0][field]": 14,              # Operating System
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": os_filter,
            "range": f"0-{limit - 1}",
            "expand_dropdowns": "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
        data = await _get("/search/Computer", params=params)
        items: list[Any] = _extract_data(data)
        return [_parse_computer_search_item(item) for item in items if isinstance(item, dict)]
    except Exception as exc:
        logger.warning("get_computers_by_os failed (filter=%s): %s", os_filter, exc)
        return []


async def get_computers_expiring_warranty(
    days: int = 90,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch computers whose warranty expires within the next N days.

    Uses GLPI Search API with date range criteria on the Infocom warranty
    expiration field (default: field 162 — verify via list_search_options
    if your GLPI returns empty results).

    Args:
        days : Look-ahead window in days (default 90).
        limit: Maximum number of results.

    Returns:
        List of computer dicts with an additional ``warranty_expiry`` field.
    """
    import datetime
    today = datetime.date.today()
    today_str = today.isoformat()
    future_str = (today + datetime.timedelta(days=days)).isoformat()

    try:
        warranty_field_str = str(_INFOCOM_WARRANTY_FIELD)
        # Build forcedisplay including the warranty date field
        forcedisplay = dict(_COMPUTER_SEARCH_FORCEDISPLAY)
        next_idx = len(forcedisplay)
        forcedisplay[f"forcedisplay[{next_idx}]"] = _INFOCOM_WARRANTY_FIELD

        params: dict[str, Any] = {
            # Expiry > today (already past warranties excluded)
            "criteria[0][field]": _INFOCOM_WARRANTY_FIELD,
            "criteria[0][searchtype]": "morethan",
            "criteria[0][value]": today_str,
            # Expiry < today + days
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
        logger.warning(
            "get_computers_expiring_warranty failed (days=%s): %s — "
            "verify _INFOCOM_WARRANTY_FIELD via list_search_options('Computer')",
            days, exc,
        )
        return []




async def get_contracts(
    computer_id: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch contracts from GLPI.

    - computer_id=0  → all contracts via GET /Contract (Postman: List Contracts)
    - computer_id>0  → contracts linked to that computer (via get_computer_by_id)

    Postman: GET /Contract?expand_dropdowns=true&range=0-{limit-1}

    Args:
        computer_id: If > 0, return only contracts linked to this computer.
        limit       : Maximum records when fetching all contracts.

    Returns:
        List of contract dicts.
    """
    try:
        if computer_id > 0:
            computer = await get_computer_by_id(computer_id)
            if not computer:
                return []
            return computer.get("contracts", [])

        # All contracts
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
                # expand_dropdowns=true resolves IDs to text labels
                "supplier": item.get("suppliers_id", "") or item.get("supplier", ""),
                "type": item.get("contracttypes_id", "") or item.get("type", ""),
                "begin_date": item.get("begin_date", ""),
                "duration": item.get("duration", ""),
                "end_date": item.get("end_date", ""),
            }
            for item in items if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.warning("get_contracts failed: %s", exc)
        return []


async def get_contract_by_id(contract_id: int) -> dict[str, Any] | None:
    """Fetch a single contract by its ID.

    Postman: GET /Contract/{id}

    Args:
        contract_id: GLPI Contract ID.

    Returns:
        Contract dict, or None if not found.
    """
    try:
        data = await _get(f"/Contract/{contract_id}", params={
            "expand_dropdowns": "true",
        })
        if not isinstance(data, dict):
            return None
        return {
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "num": data.get("num", ""),
            "supplier": data.get("suppliers_id", ""),
            "type": data.get("contracttypes_id", ""),
            "begin_date": data.get("begin_date", ""),
            "duration": data.get("duration", ""),
            "end_date": data.get("end_date", ""),
            "comment": data.get("comment", ""),
        }
    except Exception as exc:
        logger.warning("get_contract_by_id failed (id=%s): %s", contract_id, exc)
        return None


# ── Utilities ────────────────────────────────────────────────────────────────

async def get_multiple_items(
    items: list[dict[str, Any]],
    with_infocoms: bool = True,
    with_contracts: bool = True,
) -> list[dict[str, Any]]:
    """Fetch multiple items across different itemtypes in a single API call.

    Postman: GET /getMultipleItems
             ?items[0][itemtype]=Computer&items[0][items_id]=1
             &items[1][itemtype]=Contract&items[1][items_id]=2
             &with_infocoms=true&with_contracts=true

    Args:
        items          : List of {"itemtype": "Computer", "items_id": 1} dicts.
        with_infocoms  : Include Infocom (financial) data in response.
        with_contracts : Include linked contracts in response.

    Returns:
        List of item dicts (may include _infocoms and _contracts sub-keys).
    """
    try:
        params: dict[str, Any] = {
            "expand_dropdowns": "true",
            "with_infocoms": "true" if with_infocoms else "false",
            "with_contracts": "true" if with_contracts else "false",
        }
        for idx, item in enumerate(items):
            params[f"items[{idx}][itemtype]"] = item["itemtype"]
            params[f"items[{idx}][items_id]"] = item["items_id"]

        data = await _get("/getMultipleItems", params=params)
        return _extract_data(data)
    except Exception as exc:
        logger.warning("get_multiple_items failed: %s", exc)
        return []


async def list_search_options(itemtype: str = "Computer") -> dict[str, Any]:
    """Get the available search fields for a given GLPI itemtype.

    Postman: GET /listSearchOptions/Computer (or any other itemtype)

    Useful for discovering field numbers to use in criteria[n][field]
    when building GLPI search queries.

    Args:
        itemtype: GLPI itemtype name (e.g., 'Computer', 'Contract', 'Ticket').

    Returns:
        Dict mapping field IDs to field metadata (name, table, field).
    """
    try:
        data = await _get(f"/listSearchOptions/{itemtype}")
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("list_search_options failed (itemtype=%s): %s", itemtype, exc)
        return {}


# ── Knowledge Base ────────────────────────────────────────────────────────────

async def fetch_knowbase_items(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Knowledge Base articles by keyword.

    Endpoint: GET /KnowbaseItem?searchText[name]={query}&range=0-{limit-1}

    Args:
        query: Search keyword.
        limit: Maximum number of articles to return.

    Returns:
        List of KB article dicts with id, title, and plain-text answer.
    """

    try:
        data = await _get("/KnowbaseItem", params={
            "searchText[name]": query,
            "range": f"0-{limit - 1}",
            "forcedisplay[0]": 1,   # ID
            "forcedisplay[1]": 2,   # Name/title
            "forcedisplay[2]": 5,   # Answer/content
        })
        items: list[Any] = _extract_data(data)
        return [
            {
                "id": item.get("1") or item.get("id"),
                "title": item.get("2") or item.get("name", ""),
                "answer": _strip_html(item.get("5") or item.get("answer", "")),
            }
            for item in items
        ]
    
    except Exception as exc:
        logger.warning("fetch_knowbase_items failed: %s", exc)
        return []


# ── Tickets ───────────────────────────────────────────────────────────────────

async def fetch_user_tickets(
    glpi_user_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Fetch tickets created by a specific user via GLPI Search API.

    Mirrors chat.php which queries glpi_tickets with
    users_id_recipient = usersId and active statuses (1,2,3,4).

    Candidate field IDs for requester user on Ticket:
      - Field 4  : users_id (requester) — most common in GLPI 10.x
      - Field 22 : Requester (alternative mapping)
      - Field 64 : users_id_recipient (older versions)

    Args:
        glpi_user_id: GLPI User ID.
        limit       : Maximum number of tickets to return.

    Returns:
        List of ticket dicts with id, title, status, last_update, content.
    """

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
            logger.debug(
                "fetch_user_tickets: 0 results for user_id=%s with field=%s",
                glpi_user_id, field_id,
            )
        except Exception as exc:
            logger.debug("fetch_user_tickets field=%s error: %s", field_id, exc)

    logger.warning("fetch_user_tickets: no tickets found for user_id=%s", glpi_user_id)
    return []


# ── User Info ─────────────────────────────────────────────────────────────────

async def fetch_user_info(glpi_user_id: int) -> dict[str, Any] | None:
    """Fetch a user's profile from GLPI.

    Endpoint: GET /User/{id}

    Args:
        glpi_user_id: GLPI User ID.

    Returns:
        User dict with name, email, and groups; or None if not found.
        Name priority: realname > firstname > name (to avoid "GLPI" service account names)
    """
    try:
        data = await _get(f"/User/{glpi_user_id}")
        if not isinstance(data, dict):
            return None
        
        # Determine display name with priority: realname > firstname > name
        # This avoids showing service account names like "GLPI"
        display_name = (
            data.get("realname", "").strip() or 
            data.get("firstname", "").strip() or 
            data.get("name", "")
        )
        
        return {
            "id": data.get("id"),
            "name": display_name,
            "realname": data.get("realname", ""),
            "firstname": data.get("firstname", ""),
            "login": data.get("name", ""),  # Actual login/username
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
    """Fetch ITIL categories for ticket creation.

    Endpoint: GET /ITILCategory?expand_dropdowns=true&range=0-{limit-1}
    """
    try:
        data = await _get("/ITILCategory", params={
            "expand_dropdowns": "true",
            "range": f"0-{limit - 1}",
        })
        items: list[Any] = _extract_data(data)
        return [
            {
                "id": item.get("1") or item.get("id"),
                "name": item.get("2") or item.get("name", ""),
                "completename": item.get("16") or item.get("completename", ""),
            }
            for item in items
        ]
    except Exception as exc:
        logger.warning("fetch_itil_categories failed: %s", exc)
        return []


# ── Suppliers ─────────────────────────────────────────────────────────────────

async def fetch_suppliers(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch suppliers / vendors from GLPI.

    Endpoint: GET /Supplier?expand_dropdowns=true&range=0-{limit-1}
    """
    try:
        data = await _get("/Supplier", params={
            "expand_dropdowns": "true",
            "range": f"0-{limit - 1}",
        })
        if isinstance(data, dict) and "data" in data:
            return data["data"]  # type: ignore[return-value]
        if isinstance(data, list):
            return data
        return []
    except Exception as exc:
        logger.warning("fetch_suppliers failed: %s", exc)
        return []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Remove HTML tags from GLPI rich-text content."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _extract_data(data: dict[str, Any] | list[Any]) -> list[Any]:
    """Unwrap GLPI search response envelope {'data': [...]} or pass through list."""
    if isinstance(data, dict) and "data" in data:
        return data["data"]  # type: ignore[return-value]
    if isinstance(data, list):
        return data
    return []


def _clean_value(value: Any) -> str:
    """Normalise a GLPI dropdown field value to a clean string.

    When expand_dropdowns=true is used, GLPI replaces foreign-key integer IDs
    with their human-readable label. However, unset fields come back as 0
    (integer) or "0" (string). Both are treated as empty so the UI shows "-"
    rather than a meaningless "0".

    Args:
        value: Raw value from a GLPI API response field.

    Returns:
        Clean string, or "" if the value is absent/zero/blank.
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
    """Convert a GLPI numeric ticket status to a human-readable Indonesian label."""
    try:
        return _STATUS_MAP.get(int(status), f"Status {status}")
    except (TypeError, ValueError):
        return "Tidak diketahui"