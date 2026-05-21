"""Infrastructure package — GLPI AI Gateway.

Re-export public API dari semua modul infrastruktur agar caller cukup
mengimpor dari ``app.infrastructure`` tanpa perlu tahu lokasi internal.

Usage:
    from app.infrastructure import glpi_get, get_session_token, close_http_client
    from app.infrastructure import run_async, get_loop
"""

from app.infrastructure.async_runner import get_loop, is_loop_running, run_async
from app.infrastructure.glpi_gateway import glpi_get
from app.infrastructure.http_client import close_http_client, get_base_headers, get_http_client
from app.infrastructure.session_manager import (
    get_session_token,
    invalidate_session_token,
    kill_session,
    refresh_session_token,
)

__all__ = [
    # async_runner
    "get_loop",
    "is_loop_running",
    "run_async",
    # glpi_gateway
    "glpi_get",
    # http_client
    "close_http_client",
    "get_base_headers",
    "get_http_client",
    # session_manager
    "get_session_token",
    "invalidate_session_token",
    "kill_session",
    "refresh_session_token",
]