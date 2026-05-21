# GLPI AI Gateway

FastAPI + CrewAI chatbot gateway untuk mengakses data GLPI (IT Asset Management) menggunakan AI Agent dengan arsitektur **Clean Architecture**.
**Version:** 3.0.0 — Refined architecture, production-ready streaming, and optimized GLPI integration.

## Fitur Utama

- **Clean Architecture** — Pemisahan lapisan yang jelas antara Infrastructure, Repository, Service, dan Agent.
- **REST API** — OpenAI-compatible `/v1/chat/completions` endpoint dengan dukungan SSE streaming.
- **CrewAI Native Integration** — Agent cerdas dengan toolset lengkap untuk query data GLPI secara dinamis.
- **Optimasi Latensi** — Penggunaan `forcedisplay` pada GLPI Search API untuk menghindari N+1 query (terutama pada modul Supplier).
- **Session & Context Management** — Multi-turn conversation yang handal dengan auto-fingerprinting dan history merging.
- **Background Async Runner** — Menjalankan tugas asinkron di background thread untuk mencegah pemblokiran event loop utama.
- **Global HTTP Client** — Connection pooling menggunakan `httpx.AsyncClient` untuk efisiensi koneksi ke GLPI.
- **Auto-Cleanup** — Pembersihan sesi otomatis untuk menjaga efisiensi memori server.

## Struktur Proyek (Clean Architecture)

```
app/
├── agents/             # Brain: Definisi Agent, Prompt, dan Factory
│   ├── agent_factory.py    # Factory untuk membangun IT Support Agent
│   └── prompt_builder.py   # Logika pembangunan context & history
├── infrastructure/     # Plumbing: HTTP Client, Session, dan Async Runner
│   ├── glpi_gateway.py     # Pintu masuk utama HTTP ke GLPI API
│   ├── http_client.py      # Pengelolaan AsyncClient lifecycle
│   └── session_manager.py  # Logika cleanup & session storage
├── repository/         # Data: Abstraksi akses data ke GLPI (Domain Logic)
│   ├── asset_repository.py     # Komputer, Aset, Kontrak
│   ├── supplier_repository.py  # Optimized Supplier fetch (Single Call)
│   ├── ticket_repository.py    # Tiket, User Profile, ITIL Categories
│   └── pagination.py           # Helper untuk Search API GLPI
├── services/           # Orchestration: Menghubungkan API dengan CrewAI
│   └── crew_orchestrator.py    # Menjalankan CrewAI Task & SSE Streaming
├── tools/              # Action: CrewAI Tools per domain
│   ├── computer_tools.py
│   ├── supplier_tools.py
│   └── ticket_tools.py
├── main.py             # Entry Point: FastAPI application & routes
├── config.py           # Configuration: Pydantic Settings & Env
├── cache.py            # Utility: In-memory TTL Cache
└── utils.py            # Utility: Helper functions (parsing, dsb.)
```

## Quick Start

### 1. Persyaratan
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (disarankan) atau pip

### 2. Instalasi
```bash
uv sync
# atau
pip install -e .
```

### 3. Konfigurasi
Salin `.env.example` ke `.env` dan sesuaikan nilainya:
```bash
cp .env.example .env
```
Variabel Kunci:
- `AI_GATEWAY_URL`: Endpoint LLM API.
- `GLPI_API_URL`: URL API REST GLPI Anda.
- `GLPI_APP_TOKEN` & `GLPI_USER_TOKEN`: Kredensial API GLPI.

### 4. Menjalankan Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Usage

### Health Check
`GET /health`
Mengembalikan status layanan, versi, dan statistik sesi aktif.

### Chat Completions
`POST /v1/chat/completions`

**Request Body:**
```json
{
  "messages": [{"role": "user", "content": "Tampilkan 5 supplier terbaru"}],
  "glpi_user_id": 0,
  "stream": true
}
```

**Header:**
- `Authorization: Bearer <GATEWAY_API_KEY>`

## Domain & Tools

| Domain | Deskripsi |
|---|---|
| **Computer** | List, Search, Detail, Count, Status, Location, OS. |
| **Supplier** | List (Optimized 5-50 items), Count, Filter by Name/Address. |
| **Ticket** | List User Tickets, ITIL Categories. |
| **User** | Profil (Realname priority), User Assets. |
| **Contract** | List Contracts (by Computer/Active), Detail Contract. |
| **Utility** | KB Search, Multi-item fetch, Search Options Discovery. |

## License
Internal use only.
