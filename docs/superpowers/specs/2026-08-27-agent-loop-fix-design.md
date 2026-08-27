# Design: Fix Agent Looping & Response Timeout

**Date:** 2026-08-27  
**Status:** Approved  
**Scope:** Agent loop prevention, execution time hard-stop, session-level count cache  

---

## Problem Statement

Request "Berapa total asset komputer GLPI?" memakan **>83 detik** dan timeout di frontend. Dari log:

```
14:44:06 → Request masuk
14:44:46 → LLM call #1 selesai (+40s) → count_all_computers berhasil return
14:45:28 → Server timeout cancel (+83s) ← Crew TETAP berjalan
14:45:34 → LLM call #2 terjadi (agent loop!)
14:45:44 → LLM call #3 terjadi (agent loop!)
14:45:51 → Crew selesai sendiri (+105s)
```

**Root causes:**
1. `count_all_computers` tidak emit `[INSTRUKSI SISTEM]` → agent tidak tahu harus stop → LLM call ke-2 dan ke-3 terjadi
2. `max_iter=8` tanpa `max_execution_time` → tidak ada hard-stop; worst case 8 × 40s = 320 detik
3. Cache dimatikan di count tools → call ke-2 tetap hit GLPI API meski hasil sama

---

## Approach

**Approach A — Minimal Patch** (dipilih):  
Tiga perubahan terisolasi, tidak menyentuh arsitektur utama, mudah di-rollback.

---

## Design

### Section 1 — `[INSTRUKSI SISTEM]` di Count Tools

**File:** `app/tools/computer_tools.py`  
**Target:** `CountAllComputersTool._run()` (L322–329) dan `CountAllAssetsTool._run()` (L300–307)

Tambah suffix `[INSTRUKSI SISTEM]` di return string kedua tool ini — konsisten dengan pola yang sudah ada di `GetAllComputersTool`, `GetComputersByStatusTool`, dll.

```python
# CountAllComputersTool._run() — SESUDAH
return (
    f"Total komputer yang terdaftar di sistem GLPI adalah **{total_fmt} unit**."
    f"\n\n[INSTRUKSI SISTEM]: Jawaban sudah lengkap. "
    f"TULIS Final Answer LANGSUNG dengan menyebut angka {total_fmt} unit. "
    f"DILARANG memanggil tool apapun lagi."
)

# CountAllAssetsTool._run() — SESUDAH
return (
    f"Total seluruh aset ... yang terdaftar di GLPI adalah **{total_fmt} item**."
    f"\n\n[INSTRUKSI SISTEM]: Jawaban sudah lengkap. "
    f"TULIS Final Answer LANGSUNG dengan menyebut angka {total_fmt} item. "
    f"DILARANG memanggil tool apapun lagi."
)
```

**Mengapa efektif:** `_BACKSTORY` agent (L89-92 `agent_factory.py`) sudah mengajarkan: *"Jika output tool berisi `[INSTRUKSI SISTEM]` → TULIS Final Answer LANGSUNG."* Tools lain sudah punya flag ini — ini menyeragamkan count tools yang terlewat.

---

### Section 2 — `max_iter` + `max_execution_time` di Agent

**File:** `app/agents/agent_factory.py`  
**Target:** `build_it_support()` return statement (L233–247)

```python
# SESUDAH
return Agent(
    ...
    max_iter=5,             # Turun dari 8 → 5
    max_retry_limit=2,
    max_execution_time=55,  # Hard-stop 55s < server timeout 80s
)
```

**Timeline baru:**
```
max_execution_time (Agent) : 55s  ← Crew stop sendiri
Server timeout (main.py)   : 80s  ← fallback jika CrewAI tidak raise
Buffer cleanup             : ~25s ← sentinel queue, SSE teardown
```

**File:** `app/services/crew_orchestrator.py`  
**Target:** `except Exception` block di `run_crew_async()` (L365–370)

Tambah deteksi timeout sebelum generic handler:

```python
except Exception as exc:
    err_str = str(exc).lower()
    if any(kw in err_str for kw in ("timeout", "timed out", "execution time", "max_execution")):
        logger.warning("Crew execution time limit reached: %s", exc)
        return (
            "Sistem membutuhkan waktu lebih lama dari biasanya untuk memproses "
            "permintaan ini. Silakan coba ulangi pertanyaan Anda."
        )
    logger.error("Crew async execution failed: %s", exc, exc_info=True)
    return (
        "Mohon maaf, sistem sedang mengalami kendala teknis. "
        "Silakan coba beberapa saat lagi."
    )
```

---

### Section 3 — Session-Level Count Cache

**Mekanisme:** Dict global `{session_id: {tool_name: (result, timestamp)}}` dengan TTL 5 menit. Session ID di-propagate ke worker thread via `contextvars.ContextVar` (propagate otomatis saat `asyncio.to_thread()`).

#### File baru: `app/cache_count.py`

```python
import time
from typing import Optional

_count_cache: dict[str, dict[str, tuple[str, float]]] = {}
COUNT_CACHE_TTL: float = 300.0  # 5 menit

def get_count_cache(session_id: str, tool_name: str) -> Optional[str]:
    """Return cached result jika ada dan belum expired. None jika miss/expired."""
    entry = _count_cache.get(session_id, {}).get(tool_name)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > COUNT_CACHE_TTL:
        _count_cache[session_id].pop(tool_name, None)
        return None
    return result

def set_count_cache(session_id: str, tool_name: str, result: str) -> None:
    """Simpan result ke cache dengan timestamp sekarang."""
    if session_id not in _count_cache:
        _count_cache[session_id] = {}
    _count_cache[session_id][tool_name] = (result, time.monotonic())

def clear_expired() -> None:
    """Bersihkan semua entry expired — dipanggil dari session_cleanup_loop."""
    now = time.monotonic()
    for sid in list(_count_cache.keys()):
        for tool in list(_count_cache[sid].keys()):
            _, ts = _count_cache[sid][tool]
            if now - ts > COUNT_CACHE_TTL:
                del _count_cache[sid][tool]
        if not _count_cache[sid]:
            del _count_cache[sid]
```

#### File baru: `app/infrastructure/thread_context.py`

```python
from contextvars import ContextVar

_session_id_var: ContextVar[str] = ContextVar("session_id", default="")

def set_session_id(sid: str) -> None:
    _session_id_var.set(sid)

def get_session_id() -> str:
    return _session_id_var.get()
```

`ContextVar` di-copy otomatis ke child context saat `asyncio.to_thread()` — session_id terbaca dengan benar di worker thread CrewAI.

#### Perubahan `app/services/crew_orchestrator.py`

Set session_id ke ContextVar sebelum `crew.kickoff_async()`:

```python
from app.infrastructure.thread_context import set_session_id

# Di run_crew_async(), sebelum crew kickoff:
set_session_id(session_id)  # propagate via ContextVar ke worker thread
result = await crew.kickoff_async()
```

`run_crew_async()` perlu terima parameter `session_id: str = ""` tambahan.

#### Perubahan `app/tools/computer_tools.py`

Lookup/set cache di `CountAllComputersTool._run()` dan `CountAllAssetsTool._run()`:

```python
from app.cache_count import get_count_cache, set_count_cache
from app.infrastructure.thread_context import get_session_id

def _run(self, **kwargs: Any) -> str:
    session_id = get_session_id()
    if session_id:
        cached = get_count_cache(session_id, "count_all_computers")
        if cached:
            return cached  # hit cache, tidak hit GLPI API

    total = run_async(asset_repository.get_total_computers_count())
    total_fmt = f"{total:,}".replace(",", ".")
    result = (
        f"Total komputer yang terdaftar di sistem GLPI adalah **{total_fmt} unit**."
        f"\n\n[INSTRUKSI SISTEM]: Jawaban sudah lengkap. ..."
    )
    if session_id:
        set_count_cache(session_id, "count_all_computers", result)
    return result
```

#### Perubahan `app/main.py`

Panggil `clear_expired()` dari cleanup loop:

```python
from app.cache_count import clear_expired as clear_count_cache

async def _session_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        _clean_sessions()
        clear_count_cache()  # bersihkan count cache expired
```

Juga pass `session_id` ke `run_crew_async()` di `_stream_crew_response()`.

---

## Files Touched

| File | Jenis | Perubahan |
|------|-------|-----------|
| `app/tools/computer_tools.py` | Existing | Tambah `[INSTRUKSI SISTEM]` + cache lookup/set di 2 tools |
| `app/agents/agent_factory.py` | Existing | `max_iter=5`, `max_execution_time=55` |
| `app/services/crew_orchestrator.py` | Existing | Timeout error handler + set ContextVar + terima `session_id` param |
| `app/main.py` | Existing | Pass `session_id` ke `run_crew_async()` + panggil `clear_count_cache()` |
| `app/cache_count.py` | **Baru** | Dict cache TTL 5 menit |
| `app/infrastructure/thread_context.py` | **Baru** | `ContextVar` untuk propagate session_id |

---

## Expected Impact

| Metric | Sebelum | Sesudah |
|--------|---------|---------|
| LLM call per query count | 2–3 call | 1 call (Section 1) |
| Worst-case execution time | 320s (8 × 40s) | 55s hard-stop (Section 2) |
| GLPI API call jika agent loop | N kali | 0 (Section 3 cache hit) |
| Server timeout rate | Tinggi | Jauh berkurang |

---

## Non-Goals

- Tidak fix LLM latency 40s/call (di luar scope, bergantung model/tier)
- Tidak tambah `[INSTRUKSI SISTEM]` ke tools selain `count_all_computers` dan `count_all_assets`
- Tidak ganti arsitektur CrewAI

---

## Rollback Plan

- Section 1: Hapus suffix `[INSTRUKSI SISTEM]` dari return string
- Section 2: Kembalikan `max_iter=8`, hapus `max_execution_time`
- Section 3: Hapus dua file baru, revert perubahan di 3 file existing
