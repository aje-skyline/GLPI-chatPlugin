# Agent Loop Fix & Response Timeout Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminasi agent looping di CrewAI sehingga query sederhana seperti "berapa total komputer" selesai dalam <60 detik, turun dari >83 detik saat ini.

**Architecture:** Tiga patch terisolasi — (1) tambah sinyal stop `[INSTRUKSI SISTEM]` di count tools, (2) kurangi `max_iter` + tambah `max_execution_time` di agent config, (3) session-level count cache via `ContextVar` + dict TTL global.

**Tech Stack:** Python 3.12, FastAPI, CrewAI 1.6.1+, `contextvars.ContextVar` (stdlib), `time.monotonic()` untuk TTL.

## Global Constraints

- Python 3.12+ — gunakan `str | None` bukan `Optional[str]`
- Tidak mengubah signature publik `run_crew()` (blocking path) — hanya `run_crew_async()`
- Tidak menyentuh `GetAllComputersTool`, `GetComputersByStatusTool`, dll — sudah punya `[INSTRUKSI SISTEM]`
- `max_execution_time=55` (detik integer) — harus < server timeout `_SERVER_TIMEOUT_S=80`
- `max_iter=5` — harus ≥ 3 (minimum untuk query 2-tool berurutan + Final Answer)
- Count cache TTL = 300 detik (5 menit) — gunakan `time.monotonic()`, bukan `time.time()`
- Semua file baru ditempatkan sesuai struktur direktori yang ada (`app/`, `app/infrastructure/`)
- Jalankan server dengan `uv run uvicorn app.main:app --reload` untuk verifikasi manual

---

## File Map

| File | Status | Tanggung Jawab |
|------|--------|----------------|
| `app/cache_count.py` | **Baru** | Dict cache `{session_id: {tool_name: (result, ts)}}` + TTL + get/set/clear |
| `app/infrastructure/thread_context.py` | **Baru** | `ContextVar[str]` untuk propagate session_id ke worker thread |
| `app/tools/computer_tools.py` | Modifikasi | Tambah `[INSTRUKSI SISTEM]` + cache lookup/set di `CountAllComputersTool` & `CountAllAssetsTool` |
| `app/agents/agent_factory.py` | Modifikasi | `max_iter=5`, `max_execution_time=55` |
| `app/services/crew_orchestrator.py` | Modifikasi | Terima `session_id` param, set ContextVar, timeout error handler |
| `app/main.py` | Modifikasi | Pass `session_id` ke `run_crew_async()`, panggil `clear_count_cache()` |

---

## Task 1: Buat `app/cache_count.py` — Session Count Cache

**Files:**
- Create: `app/cache_count.py`

**Interfaces:**
- Produces:
  - `get_count_cache(session_id: str, tool_name: str) -> str | None`
  - `set_count_cache(session_id: str, tool_name: str, result: str) -> None`
  - `clear_expired() -> None`

- [ ] **Step 1: Buat file `app/cache_count.py`**

```python
"""app/cache_count.py — Session-level in-memory cache untuk count tool results.

Menyimpan hasil count tools (count_all_computers, count_all_assets) per session
dengan TTL 5 menit. Mencegah agent memanggil GLPI API berkali-kali untuk
pertanyaan count yang sama dalam satu sesi.

Struktur data:
    _count_cache[session_id][tool_name] = (result_str, monotonic_timestamp)

Thread-safety:
    Dict Python bersifat thread-safe untuk operasi get/set sederhana di CPython
    (GIL). Tidak perlu lock eksplisit untuk use case ini.
"""

from __future__ import annotations

import time

_count_cache: dict[str, dict[str, tuple[str, float]]] = {}
COUNT_CACHE_TTL: float = 300.0  # 5 menit dalam detik


def get_count_cache(session_id: str, tool_name: str) -> str | None:
    """Return cached result jika ada dan belum expired. None jika miss/expired.

    Args:
        session_id: ID sesi user (format: "conv:xxxx", "body:xxxx", dll).
        tool_name:  Nama tool CrewAI, mis. "count_all_computers".

    Returns:
        String hasil tool jika cache hit dan belum expired. None jika miss.
    """
    if not session_id:
        return None
    entry = _count_cache.get(session_id, {}).get(tool_name)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > COUNT_CACHE_TTL:
        # Entry expired — hapus dan return None
        _count_cache[session_id].pop(tool_name, None)
        return None
    return result


def set_count_cache(session_id: str, tool_name: str, result: str) -> None:
    """Simpan result ke cache dengan timestamp monotonic sekarang.

    Args:
        session_id: ID sesi user.
        tool_name:  Nama tool CrewAI.
        result:     String output tool yang akan di-cache.
    """
    if not session_id:
        return
    if session_id not in _count_cache:
        _count_cache[session_id] = {}
    _count_cache[session_id][tool_name] = (result, time.monotonic())


def clear_expired() -> None:
    """Bersihkan semua entry expired dari cache.

    Dipanggil periodik dari _session_cleanup_loop() di main.py (setiap 60 detik).
    Mencegah memory leak dari session yang sudah tidak aktif.
    """
    now = time.monotonic()
    for sid in list(_count_cache.keys()):
        for tool in list(_count_cache[sid].keys()):
            _, ts = _count_cache[sid][tool]
            if now - ts > COUNT_CACHE_TTL:
                del _count_cache[sid][tool]
        if not _count_cache[sid]:
            del _count_cache[sid]
```

- [ ] **Step 2: Verifikasi import tidak error**

```bash
cd /home/ariel/projects/chatbot-fastapi
uv run python -c "from app.cache_count import get_count_cache, set_count_cache, clear_expired; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Test manual logika cache**

```bash
uv run python -c "
from app.cache_count import get_count_cache, set_count_cache, clear_expired

# Test set dan get
set_count_cache('conv:abc123', 'count_all_computers', 'Total: 20.291 unit.')
result = get_count_cache('conv:abc123', 'count_all_computers')
assert result == 'Total: 20.291 unit.', f'Expected result, got: {result}'

# Test miss untuk session lain
miss = get_count_cache('conv:xyz999', 'count_all_computers')
assert miss is None, f'Expected None, got: {miss}'

# Test clear_expired tidak error
clear_expired()

print('Semua assertion passed — cache_count.py OK')
"
```

Expected output: `Semua assertion passed — cache_count.py OK`

- [ ] **Step 4: Commit**

```bash
cd /home/ariel/projects/chatbot-fastapi
git add app/cache_count.py
git commit -m "feat: add session-level count cache (cache_count.py)"
```

---

## Task 2: Buat `app/infrastructure/thread_context.py` — ContextVar Session ID

**Files:**
- Create: `app/infrastructure/thread_context.py`

**Interfaces:**
- Produces:
  - `set_session_id(sid: str) -> None`
  - `get_session_id() -> str`

- [ ] **Step 1: Buat file `app/infrastructure/thread_context.py`**

```python
"""app/infrastructure/thread_context.py — ContextVar untuk propagate session ID.

Masalah yang dipecahkan:
    crew.kickoff_async() secara internal memanggil asyncio.to_thread(self.kickoff),
    yang menjalankan Crew di worker thread terpisah. Thread-local variable biasa
    (threading.local) TIDAK di-copy ke worker thread baru.

    ContextVar dari Python stdlib (PEP 567) di-copy otomatis ke child context
    saat asyncio.to_thread() dipanggil — inilah mekanisme yang benar untuk
    meneruskan nilai dari event loop ke worker thread.

Penggunaan:
    # Di event loop (crew_orchestrator.py) sebelum kickoff:
    set_session_id(session_id)

    # Di worker thread (computer_tools.py) saat tool dipanggil:
    session_id = get_session_id()
"""

from __future__ import annotations

from contextvars import ContextVar

_session_id_var: ContextVar[str] = ContextVar("session_id", default="")


def set_session_id(sid: str) -> None:
    """Set session ID ke ContextVar aktif.

    Dipanggil dari event loop FastAPI sebelum crew.kickoff_async(),
    sehingga nilai propagate ke worker thread via asyncio.to_thread().

    Args:
        sid: Session ID dengan prefix (mis. "conv:7ac87f83").
    """
    _session_id_var.set(sid)


def get_session_id() -> str:
    """Return session ID dari ContextVar aktif.

    Dipanggil dari worker thread CrewAI (dalam _run() tool).
    Return string kosong jika tidak di-set (default).

    Returns:
        Session ID string, atau "" jika tidak tersedia.
    """
    return _session_id_var.get()
```

- [ ] **Step 2: Verifikasi import tidak error**

```bash
cd /home/ariel/projects/chatbot-fastapi
uv run python -c "
from app.infrastructure.thread_context import set_session_id, get_session_id
print('Import OK')
"
```

Expected output: `Import OK`

- [ ] **Step 3: Test ContextVar propagate ke thread**

```bash
uv run python -c "
import asyncio
from app.infrastructure.thread_context import set_session_id, get_session_id

async def main():
    set_session_id('conv:test123')

    # Simulasi asyncio.to_thread seperti yang dilakukan kickoff_async()
    result = await asyncio.to_thread(get_session_id)
    assert result == 'conv:test123', f'Expected conv:test123, got: {result}'

    # Default jika tidak di-set
    from contextvars import copy_context
    ctx = copy_context()
    # Reset dengan set baru
    set_session_id('')
    result2 = await asyncio.to_thread(get_session_id)
    assert result2 == '', f'Expected empty, got: {result2}'

    print('ContextVar propagation test PASSED')

asyncio.run(main())
"
```

Expected output: `ContextVar propagation test PASSED`

- [ ] **Step 4: Commit**

```bash
cd /home/ariel/projects/chatbot-fastapi
git add app/infrastructure/thread_context.py
git commit -m "feat: add ContextVar session ID propagation (thread_context.py)"
```

---

## Task 3: Modifikasi `app/tools/computer_tools.py` — `[INSTRUKSI SISTEM]` + Cache

**Files:**
- Modify: `app/tools/computer_tools.py` — `CountAllComputersTool._run()` (L322–329) dan `CountAllAssetsTool._run()` (L300–307)

**Interfaces:**
- Consumes:
  - `get_count_cache(session_id: str, tool_name: str) -> str | None` dari `app.cache_count`
  - `set_count_cache(session_id: str, tool_name: str, result: str) -> None` dari `app.cache_count`
  - `get_session_id() -> str` dari `app.infrastructure.thread_context`

- [ ] **Step 1: Tambah imports di `app/tools/computer_tools.py`**

Di baris setelah `from app.tools.formatters import (...)` (sekitar L33–37), tambah:

```python
from app.cache_count import get_count_cache, set_count_cache
from app.infrastructure.thread_context import get_session_id
```

- [ ] **Step 2: Ganti `CountAllAssetsTool._run()` (L300–307)**

Ganti seluruh method `_run()` di class `CountAllAssetsTool`:

```python
    def _run(self, **kwargs: Any) -> str:
        session_id = get_session_id()
        cached = get_count_cache(session_id, "count_all_assets")
        if cached:
            logger.info("CountAllAssetsTool | cache HIT | session=%s", session_id[:20])
            return cached

        try:
            total: int = run_async(asset_repository.get_total_all_assets_count())
            total_fmt = f"{total:,}".replace(",", ".")
            result = (
                f"Total seluruh aset (termasuk Komputer, Monitor, Printer, "
                f"Network Equipment, dll) yang terdaftar di GLPI adalah "
                f"**{total_fmt} item**."
                f"\n\n[INSTRUKSI SISTEM]: Jawaban sudah lengkap. "
                f"TULIS Final Answer LANGSUNG dengan menyebut angka {total_fmt} item. "
                f"DILARANG memanggil tool apapun lagi."
            )
            set_count_cache(session_id, "count_all_assets", result)
            return result
        except Exception as exc:
            logger.error("CountAllAssetsTool failed: %s", exc)
            return f"Gagal menghitung jumlah seluruh aset: {exc}"
```

- [ ] **Step 3: Ganti `CountAllComputersTool._run()` (L322–329)**

Ganti seluruh method `_run()` di class `CountAllComputersTool`:

```python
    def _run(self, **kwargs: Any) -> str:
        session_id = get_session_id()
        cached = get_count_cache(session_id, "count_all_computers")
        if cached:
            logger.info("CountAllComputersTool | cache HIT | session=%s", session_id[:20])
            return cached

        try:
            total: int = run_async(asset_repository.get_total_computers_count())
            total_fmt = f"{total:,}".replace(",", ".")
            result = (
                f"Total komputer yang terdaftar di sistem GLPI adalah "
                f"**{total_fmt} unit**."
                f"\n\n[INSTRUKSI SISTEM]: Jawaban sudah lengkap. "
                f"TULIS Final Answer LANGSUNG dengan menyebut angka {total_fmt} unit. "
                f"DILARANG memanggil tool apapun lagi."
            )
            set_count_cache(session_id, "count_all_computers", result)
            return result
        except Exception as exc:
            logger.error("CountAllComputersTool failed: %s", exc)
            return f"Gagal menghitung jumlah komputer: {exc}"
```

- [ ] **Step 4: Verifikasi syntax tidak error**

```bash
cd /home/ariel/projects/chatbot-fastapi
uv run python -c "from app.tools.computer_tools import CountAllComputersTool, CountAllAssetsTool; print('Syntax OK')"
```

Expected output: `Syntax OK`

- [ ] **Step 5: Verifikasi `[INSTRUKSI SISTEM]` ada di output**

```bash
uv run python -c "
# Cek string [INSTRUKSI SISTEM] ada di output (tanpa hit GLPI)
# Simulasi dengan mock
from unittest.mock import patch

with patch('app.tools.computer_tools.run_async', return_value=20291):
    from app.tools.computer_tools import CountAllComputersTool
    tool = CountAllComputersTool()
    output = tool._run()
    assert '[INSTRUKSI SISTEM]' in output, 'Missing [INSTRUKSI SISTEM] in output!'
    assert '20.291' in output, 'Missing formatted total!'
    print('CountAllComputersTool output OK')
    print(output)
"
```

Expected output berisi `[INSTRUKSI SISTEM]` dan angka `20.291`.

- [ ] **Step 6: Commit**

```bash
cd /home/ariel/projects/chatbot-fastapi
git add app/tools/computer_tools.py
git commit -m "feat: add [INSTRUKSI SISTEM] + session cache to count tools"
```

---

## Task 4: Modifikasi `app/agents/agent_factory.py` — `max_iter` + `max_execution_time`

**Files:**
- Modify: `app/agents/agent_factory.py` — `build_it_support()` return statement (L233–247)

**Interfaces:**
- Tidak ada perubahan interface publik — `build_it_support()` signature tetap sama.

- [ ] **Step 1: Edit `build_it_support()` di `app/agents/agent_factory.py`**

Ganti bagian return statement (L233–247):

```python
    return Agent(
        role=_ROLE,
        goal=_GOAL,
        backstory=_BACKSTORY,
        tools=_TOOLS,
        llm=llm,
        verbose=settings.crew_verbose,
        allow_delegation=False,
        # max_iter=5: Turun dari 8 → 5.
        # Query sederhana (count/search) selesai 2 iter: tool call + Final Answer.
        # Query kompleks (search → detail → compare) butuh maks 3-4 iter.
        # 5 = safety net cukup tanpa risiko loop panjang.
        max_iter=5,
        max_retry_limit=2,
        # max_execution_time=55: Hard-stop 55s < server timeout 80s (main.py).
        # Memberi buffer 25s untuk cleanup SSE + sentinel queue.
        # CrewAI raise exception saat limit tercapai → ditangkap di crew_orchestrator.py.
        max_execution_time=55,
    )
```

- [ ] **Step 2: Verifikasi syntax tidak error**

```bash
cd /home/ariel/projects/chatbot-fastapi
uv run python -c "from app.agents.agent_factory import build_it_support; print('Syntax OK')"
```

Expected output: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
cd /home/ariel/projects/chatbot-fastapi
git add app/agents/agent_factory.py
git commit -m "feat: set max_iter=5 and max_execution_time=55 on agent"
```

---

## Task 5: Modifikasi `app/services/crew_orchestrator.py` — session_id param + ContextVar + timeout handler

**Files:**
- Modify: `app/services/crew_orchestrator.py` — `run_crew_async()` signature, body, dan `except Exception` block

**Interfaces:**
- Consumes:
  - `set_session_id(sid: str) -> None` dari `app.infrastructure.thread_context`
- Produces (perubahan signature):
  - `run_crew_async(user_message, glpi_user_id, messages, step_queue, session_id="") -> str`

- [ ] **Step 1: Tambah import di `app/services/crew_orchestrator.py`**

Di baris setelah `from app.utils import sanitize_agent_output` (L41), tambah:

```python
from app.infrastructure.thread_context import set_session_id
```

- [ ] **Step 2: Tambah parameter `session_id` ke `run_crew_async()`**

Ubah signature fungsi (L247–252):

```python
async def run_crew_async(
    user_message: str,
    glpi_user_id: int,
    messages: list[dict[str, str]] | None = None,
    step_queue: "asyncio.Queue[str | None] | None" = None,
    session_id: str = "",
) -> str:
```

- [ ] **Step 3: Tambah `set_session_id()` sebelum `crew.kickoff_async()`**

Di dalam `run_crew_async()`, tepat sebelum loop `for attempt in range(_MAX_RETRIES):` (sekitar L339), tambah satu baris:

```python
        # Propagate session_id ke worker thread via ContextVar.
        # ContextVar di-copy otomatis saat asyncio.to_thread() dipanggil
        # oleh kickoff_async() — thread-local biasa TIDAK akan berfungsi.
        set_session_id(session_id)
```

- [ ] **Step 4: Ganti `except Exception` block di `run_crew_async()` (L365–370)**

Ganti seluruh block `except Exception`:

```python
    except Exception as exc:
        err_str = str(exc).lower()
        # Deteksi timeout dari max_execution_time CrewAI sebelum generic handler.
        # CrewAI bisa raise berbagai exception type saat time limit tercapai.
        if any(kw in err_str for kw in (
            "timeout", "timed out", "execution time", "max_execution",
            "time limit", "took too long",
        )):
            logger.warning(
                "Crew execution time limit reached for session=%s: %s",
                session_id[:20], exc,
            )
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

- [ ] **Step 5: Verifikasi syntax tidak error**

```bash
cd /home/ariel/projects/chatbot-fastapi
uv run python -c "from app.services.crew_orchestrator import run_crew_async; print('Syntax OK')"
```

Expected output: `Syntax OK`

- [ ] **Step 6: Commit**

```bash
cd /home/ariel/projects/chatbot-fastapi
git add app/services/crew_orchestrator.py
git commit -m "feat: pass session_id to crew_orchestrator + timeout error handler"
```

---

## Task 6: Modifikasi `app/main.py` — Pass session_id + clear_count_cache

**Files:**
- Modify: `app/main.py` — `_stream_crew_response()` call ke `run_crew_async()` dan `_session_cleanup_loop()`

**Interfaces:**
- Consumes:
  - `run_crew_async(..., session_id="") -> str` — signature baru dari Task 5
  - `clear_expired() -> None` dari `app.cache_count`

- [ ] **Step 1: Tambah import `clear_expired` di `app/main.py`**

Di baris yang sudah ada (L21):
```python
from app.cache import cache_clear
```

Tambah di bawahnya:
```python
from app.cache_count import clear_expired as clear_count_cache
```

- [ ] **Step 2: Tambah `clear_count_cache()` di `_session_cleanup_loop()`**

Ganti fungsi `_session_cleanup_loop()` (L335–338):

```python
async def _session_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        _clean_sessions()
        clear_count_cache()  # bersihkan count cache expired setiap 60 detik
```

- [ ] **Step 3: Pass `session_id` ke `run_crew_async()` di `_stream_crew_response()`**

Di dalam `_stream_crew_response()`, ganti pemanggilan `asyncio.create_task(...)` (L225–227):

```python
    crew_task = asyncio.create_task(
        run_crew_async(user_message, glpi_user_id, messages, step_queue, session_id)
    )
```

- [ ] **Step 4: Verifikasi syntax tidak error**

```bash
cd /home/ariel/projects/chatbot-fastapi
uv run python -c "from app.main import app; print('Syntax OK')"
```

Expected output: `Syntax OK`

- [ ] **Step 5: Smoke test — server start tanpa error**

```bash
cd /home/ariel/projects/chatbot-fastapi
timeout 8 uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 2>&1 | head -20
```

Expected output: Mengandung `Application startup complete.` tanpa traceback.

- [ ] **Step 6: Commit**

```bash
cd /home/ariel/projects/chatbot-fastapi
git add app/main.py
git commit -m "feat: pass session_id to run_crew_async + clear count cache on cleanup"
```

---

## Task 7: Integrasi & Verifikasi End-to-End

**Files:**
- Tidak ada file baru — verifikasi semua perubahan bekerja bersama.

- [ ] **Step 1: Jalankan server**

```bash
cd /home/ariel/projects/chatbot-fastapi
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Kirim request streaming — query count komputer**

Di terminal lain:

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Berapa total asset komputer GLPI?"}],
    "glpi_user_id": 2,
    "stream": true
  }'
```

**Expected behavior:**
- Response selesai dalam **<60 detik** (idealnya <50 detik)
- Log tidak menampilkan `Crew async cancelled after` (tidak timeout)
- Log menampilkan hanya **1x** `Used count_all_computers`
- Final Answer mengandung angka total komputer

- [ ] **Step 3: Kirim request kedua — verifikasi cache hit**

Kirim request yang sama persis (session baru karena fingerprint sama):

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-session-cache-01" \
  -d '{
    "messages": [{"role": "user", "content": "Berapa total asset komputer GLPI?"}],
    "glpi_user_id": 2,
    "stream": true
  }'
```

Lalu kirim lagi dengan session ID yang sama:

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: test-session-cache-01" \
  -d '{
    "messages": [
      {"role": "user", "content": "Berapa total asset komputer GLPI?"},
      {"role": "assistant", "content": "Terdapat 20.291 komputer."},
      {"role": "user", "content": "Berapa total asset komputer GLPI?"}
    ],
    "glpi_user_id": 2,
    "stream": true
  }'
```

**Expected:** Log menampilkan `cache HIT` untuk request ke-2.

- [ ] **Step 4: Verifikasi log tidak ada agent loop**

Di log server, pastikan TIDAK ada:
- `Crew async cancelled after` (server timeout)
- `count_all_computers (2)` (tool dipanggil lebih dari sekali)
- `LiteLLM completion()` lebih dari **2 kali** per request (1 = think+tool, 1 = Final Answer)

- [ ] **Step 5: Commit final**

```bash
cd /home/ariel/projects/chatbot-fastapi
git add .
git commit -m "test: verify agent loop fix end-to-end OK"
```

---

## Rollback

Jika ada masalah setelah deploy:

```bash
# Rollback semua perubahan ke commit sebelum Task 1
git log --oneline -10  # cari commit hash sebelum "feat: add session-level count cache"
git revert HEAD~6..HEAD  # revert 6 commit terakhir (Task 1-6)
```

Atau revert per-task via `git revert <commit-hash>` untuk rollback selektif.
