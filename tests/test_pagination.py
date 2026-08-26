"""Test pagination cap behavior — Opsi A fix.

Memastikan get_all_pages() membatasi fetch Fase 2 ke STAT_FETCH_CAP
(500 record) meski totalcount jauh lebih besar, sambil menjaga
totalcount exact dari probe.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.repository.pagination import get_all_pages, STAT_FETCH_CAP


@pytest.mark.asyncio
async def test_cap_limits_fetch_to_500():
    """totalcount > cap → fetched <= cap, truncated=True, totalcount exact."""
    # Mock: probe returns totalcount=5000 + 10 items
    # Fase 2: return 100-item pages until cap
    probe_response = {
        "totalcount": 5000,
        "data": [{"id": i, "name": f"PC-{i}"} for i in range(10)],
    }

    # Fase 2 pages: 100 items each
    page_response = {
        "data": [{"id": i, "name": f"PC-{i}"} for i in range(100)],
    }

    mock_get = AsyncMock(side_effect=[probe_response] + [page_response] * 50)

    with patch("app.repository.pagination.glpi_get", mock_get):
        result = await get_all_pages(
            "/search/Computer",
            base_params={},
            sample_size=10,
        )

    assert result["totalcount"] == 5000, "totalcount harus exact dari probe"
    assert result["fetched"] <= STAT_FETCH_CAP, f"fetched harus <= {STAT_FETCH_CAP}"
    assert result["truncated"] is True, "truncated=True karena fetched < totalcount"
