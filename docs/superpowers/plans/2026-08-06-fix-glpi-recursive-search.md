# Fix GLPI Recursive Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the issue where GLPI API searches only return root-entity assets (1,284 instead of ~20,000) by ensuring all computer-related API calls use `"is_recursive": "true"`.

**Architecture:** We will modify the repository layer (`app/repository/asset_repository.py`) to enforce recursive searching on all relevant GLPI API endpoints. We also change `countonly` query parameter where appropriate. The string "true" is used instead of "1" to ensure correct parsing by the strict GLPI API backend, aligning with the pattern successfully used in `supplier_repository.py`.

**Tech Stack:** FastAPI, Python, httpx, GLPI REST API

## Global Constraints
- Target file is `app/repository/asset_repository.py`.
- Must use string `"true"` for boolean query parameters expected by GLPI, not `"1"` or integer `1`.
- All computer fetching/searching functions must be updated to include `"is_recursive": "true"`.

---

### Task 1: Fix `get_total_computers_count`

**Files:**
- Modify: `app/repository/asset_repository.py`

**Interfaces:**
- Consumes: `glpi_get`
- Produces: `async def get_total_computers_count() -> int:`

- [ ] **Step 1: Write the failing test**

```python
# No automated test suite exists for this external API integration, but we can verify via curl or manual testing later.
# We will create a small script to test this directly.
import asyncio
import sys

# Script to verify count
with open("test_count.py", "w") as f:
    f.write("""
import asyncio
from app.repository.asset_repository import get_total_computers_count

async def main():
    count = await get_total_computers_count()
    print(f"Total computers: {count}")

if __name__ == "__main__":
    asyncio.run(main())
""")
```

- [ ] **Step 2: Run test to verify it fails (or returns old number)**

Run: `python test_count.py`
Expected: Output showing the old low number (e.g. 1284) or failure due to environment setup. (Note: this is an interactive system test).

- [ ] **Step 3: Write minimal implementation**

Modify `get_total_computers_count` in `app/repository/asset_repository.py`. Change:
```python
        data = await glpi_get("/search/Computer", params={
            "is_recursive": "1",
            "range": "0-1",
        })
```
to:
```python
        data = await glpi_get("/search/Computer", params={
            "countonly": "true",
            "is_recursive": "true",
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python test_count.py`
Expected: Output showing the correct high number (e.g. ~20,000).

- [ ] **Step 5: Commit**

```bash
git add app/repository/asset_repository.py
git commit -m "fix: use countonly=true and is_recursive=true for computer count"
```

### Task 2: Add `is_recursive` to global base parameters for Computer search

**Files:**
- Modify: `app/repository/asset_repository.py`

**Interfaces:**
- Consumes: `_COMPUTER_SEARCH_FORCEDISPLAY`
- Produces: Updated base parameters for `get_all_computers`, `search_computer_by_name`, `search_computer`, `get_computers_by_status`, etc.

- [ ] **Step 1: Write minimal implementation for `get_all_computers`**

In `app/repository/asset_repository.py`, update `base_params` inside `get_all_computers`:
```python
    base_params: dict[str, Any] = {
        "expand_dropdowns": "true",
        "is_recursive": "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
```

- [ ] **Step 2: Write minimal implementation for `search_computer_by_name`**

In `app/repository/asset_repository.py`, update `params` inside `search_computer_by_name`:
```python
        params: dict[str, Any] = {
            "criteria[0][field]":      1,
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]":      name,
            "range":                   f"0-{limit - 1}",
            "expand_dropdowns":        "true",
            "is_recursive":            "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
```

- [ ] **Step 3: Write minimal implementation for `search_computer`**

In `app/repository/asset_repository.py`, update `params` inside `search_computer`:
```python
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
            "range":                   f"0-{limit - 1}",
            "expand_dropdowns":        "true",
            "is_recursive":            "true",
            **_COMPUTER_SEARCH_FORCEDISPLAY,
        }
```

- [ ] **Step 4: Write minimal implementation for `get_computers_by_status`**

In `app/repository/asset_repository.py`, update `base_params` inside `get_computers_by_status`:
```python
    base_params: dict[str, Any] = {
        "criteria[0][field]":      31,
        "criteria[0][searchtype]": "equals",
        "criteria[0][value]":      status_id,
        "expand_dropdowns":        "true",
        "is_recursive":            "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
```

- [ ] **Step 5: Write minimal implementation for `get_computers_by_location`**

In `app/repository/asset_repository.py`, update `base_params` inside `get_computers_by_location`:
```python
    base_params: dict[str, Any] = {
        "criteria[0][field]":      3,
        "criteria[0][searchtype]": "equals",
        "criteria[0][value]":      location_id,
        "expand_dropdowns":        "true",
        "is_recursive":            "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
```

- [ ] **Step 6: Write minimal implementation for `get_computers_by_os`**

In `app/repository/asset_repository.py`, update `base_params` inside `get_computers_by_os`:
```python
    base_params: dict[str, Any] = {
        "criteria[0][field]":      14,
        "criteria[0][searchtype]": "equals",
        "criteria[0][value]":      os_id,
        "expand_dropdowns":        "true",
        "is_recursive":            "true",
        **_COMPUTER_SEARCH_FORCEDISPLAY,
    }
```

- [ ] **Step 7: Commit**

```bash
git add app/repository/asset_repository.py
git commit -m "fix: enforce is_recursive=true across all computer search endpoints"
```
