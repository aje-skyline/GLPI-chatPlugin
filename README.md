# GLPI AI Gateway

FastAPI + CrewAI chatbot gateway untuk mengakses data GLPI (IT Asset Management) menggunakan AI Agent.  
**Version:** 2.2.0 — with streaming, session management, and background async loop.

## Fitur

- **REST API** — endpoint `/v1/chat/completions` (OpenAI-compatible) dengan dukungan SSE streaming
- **CrewAI Agent** dengan tools untuk query GLPI:
  - Assets: semua komputer, detail komputer, cari komputer by name, aset milik user, total count
  - Contracts: daftar & detail kontrak, filter aktif
  - Knowledge Base articles
  - User tickets & profiles (realname > firstname > name)
  - ITIL Categories & Suppliers
  - Utilities: multi-item fetch, search options
- **SSE Streaming** — emulated word-by-word streaming dengan status/heartbeat events
- **Session Management** — multi-turn conversation via `session_id` (body, header, atau auto-fingerprint)
- **Background Async Loop** — persistent event loop thread untuk GLPI API calls (mencegah orphaned lock)
- **TTL Cache** — 5 menit cache untuk data statis GLPI (kategori, supplier, KB)
- **Authentication** via Bearer token + CORS

## Quick Start

### 1. Install Dependencies
```bash
pip install -e .
# atau
uv sync
```

### 2. Configure Environment
Copy `.env.example` ke `.env` dan isi dengan konfigurasi Anda:
```bash
cp .env.example .env
```

Key variables:
- `AI_GATEWAY_URL` / `AI_GATEWAY_BASE_URL` — URL AI Gateway (Nemotron)
- `AI_GATEWAY_API_KEY` — API key untuk AI Gateway
- `GATEWAY_API_KEY` — Secret untuk endpoint ini
- `GLPI_URL` / `GLPI_API_URL` — URL GLPI instance
- `GLPI_APP_TOKEN` & `GLPI_USER_TOKEN` — GLPI API tokens
- `NEMOTRON_MODEL` — model name (default: `qwen/qwen3-next-80b-a3b-instruct`)
- `ALLOWED_ORIGINS` — CORS allowed origins

### 3. Run Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Test
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Daftar semua komputer"}], "glpi_user_id": 0}'
```

Streaming:
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Daftar semua komputer"}], "stream": true}'
```

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check & service info |
| `/v1/chat/completions` | POST | Bearer token | Main chat endpoint (JSON or SSE) |

### Chat Request Format
```json
{
  "messages": [{"role": "user", "content": "Pertanyaan Anda"}],
  "glpi_user_id": 0,
  "session_id": "abc-123",
  "stream": false
}
```

- `session_id` — opsional, disarankan untuk multi-turn. Bisa via body, header `X-Session-ID`, atau auto-fingerprint.
- `stream` — jika `true`, response dalam format SSE dengan event: `status`, `heartbeat`, `meta`, `data` (OpenAI delta chunks), `data: [DONE]`.
- Response API juga mengembalikan `session_id` di body dan `X-Session-ID` di header.

### Health Check Response
```json
{
  "status": "ok",
  "service": "GLPI AI Gateway",
  "version": "2.2.0",
  "nemotron_gateway": "https://ai-gw.example.com/v1",
  "nemotron_model": "qwen/qwen3-next-80b-a3b-instruct",
  "architecture": "CrewAI Sequential (Agent + Tools)",
  "streaming": "emulated-sse",
  "active_sessions": 0
}
```

## CrewAI Tools

| Tool | Fungsi |
|------|--------|
| `search_knowledge_base` | Cari artikel panduan / FAQ di Knowledge Base |
| `get_user_assets` | Ambil daftar aset komputer milik user tertentu |
| `get_all_computers` | Ambil semua komputer di inventaris (dengan filter serial) |
| `get_computer_detail` | Detail lengkap 1 komputer termasuk infocom & kontrak |
| `count_all_computers` | Hitung total jumlah komputer |
| `search_computer_by_name` | Cari komputer spesifik by name via Search API |
| `list_all_contracts` | Daftar kontrak (filter by computer / active only) |
| `get_contract_detail` | Detail lengkap 1 kontrak |
| `get_user_tickets` | Daftar tiket IT milik user |
| `get_user_info` | Profil user (nama, email, grup) |
| `get_itil_categories` | Daftar kategori ITIL |
| `get_suppliers` | Daftar supplier/vendor |
| `get_multiple_items` | Ambil multi item GLPI sekaligus |
| `list_search_options` | Field options untuk GLPI Search API |

## Session & Context Management

- **Session ID resolution**: body > X-Session-ID header > fingerprint (hash pesan user pertama) > random UUID
- **History merge**: incoming messages di-merge dengan stored session history (append, mismatch fallback, dll.)
- **User ID persistence**: `glpi_user_id` disimpan per session setelah request pertama
- **Session TTL**: 60 menit (configurable via `session_ttl_minutes`)
- **Max session messages**: 20 pesan per sesi
- **Periodic cleanup**: stale sessions dibersihkan setiap ~100 request

## Project Structure

```
chatbot-fastapi/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entry point (v2.2.0)
│   ├── config.py                # Settings & environment variables
│   ├── crew_services.py         # CrewAI orchestration
│   ├── tools.py                 # CrewAI tools (GLPI wrappers) + bg event loop
│   ├── it_glpi_client.py        # GLPI REST API client + TTL cache
│   └── agents/
│       ├── __init__.py
│       └── it_support.py        # IT Support Agent definition
├── .env                         # Environment config (gitignored)
├── .env.example                 # Template for .env
├── .gitignore
├── .python-version              # Python 3.12
├── pyproject.toml               # Project metadata & dependencies (hatchling)
├── uv.lock                      # Lock file (uv)
├── test_session_fixes.py        # Unit tests for session & context fixes
└── deploy_and_test.sh           # Deployment checklist script
```

## Tech Stack

- **FastAPI** — Web framework
- **CrewAI** — Multi-agent AI framework
- **LiteLLM** — Unified LLM interface (Nemotron via AI Gateway)
- **httpx** — Async HTTP client untuk GLPI API (connection pooling)
- **Pydantic Settings** — Configuration management (.env)
- **python-dotenv** — Environment loader
- **hatchling** — Build system

## Notes for Developers

1. **Disable verbose mode** di production (`verbose=True` di `crew_services.py` dan `it_support.py`)
2. **Add rate limiting** ke endpoint `/v1/chat/completions`
3. **Add proper logging config** untuk production (saat ini via `logging` basic config)
4. **GLPI health check** di endpoint `/health` (saat ini hanya menampilkan config, belum ping ke GLPI)
5. **Add more agents** (HR, Finance, dll) di `app/agents/`
6. **Add CI/CD** workflow di `.github/workflows/`

## License

Internal use only.
