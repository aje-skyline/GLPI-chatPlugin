# GLPI AI Gateway

FastAPI + CrewAI chatbot gateway untuk mengakses data GLPI (IT Asset Management) menggunakan AI Agent.

## Fitur

- **REST API** dengan single endpoint `/v1/chat/completions` (OpenAI-compatible)
- **CrewAI Agent** dengan tools untuk query GLPI:
  - Assets (Computers, IT assets)
  - Contracts (Support, licensing, internet)
  - Knowledge Base articles
  - User tickets & profiles
  - ITIL Categories & Suppliers
  - Utilities (multi-item fetch, search options)
- **Mock Mode** untuk testing tanpa GLPI server
- **Authentication** via Bearer token

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
- `AI_GATEWAY_URL` - URL AI Gateway (Nemotron)
- `AI_GATEWAY_API_KEY` - API key untuk AI Gateway
- `GATEWAY_API_KEY` - Secret untuk endpoint ini
- `GLPI_URL` - URL GLPI instance
- `GLPI_APP_TOKEN` & `GLPI_USER_TOKEN` - GLPI API tokens
- `MOCK_MODE=true` - Aktifkan untuk testing tanpa GLPI

### 3. Run Server
```bash
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Test
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Daftar semua komputer"}], "glpi_user_id": 0}'
```

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check & service info |
| `/v1/chat/completions` | POST | Bearer token | Main chat endpoint |

### Chat Request Format
```json
{
  "messages": [{"role": "user", "content": "Pertanyaan Anda"}],
  "glpi_user_id": 0,
  "session_id": "abc-123"
}
```

`session_id` bersifat opsional, tetapi sangat disarankan untuk percakapan multi-turn.
Respons API juga mengembalikan `session_id` di body dan `X-Session-ID` di header.

## Project Structure

```
chatbot-fastapi/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings & environment variables
│   ├── crew_services.py    # CrewAI orchestration
│   ├── tools.py            # CrewAI tools (GLPI wrappers)
│   ├── it_glpi_client.py   # GLPI REST API client + mock data
│   └── agents/
│       ├── __init__.py
│       └── it_support.py   # IT Support Agent definition
├── .env                    # Environment config (gitignored)
├── .env.example            # Template for .env
├── pyproject.toml          # Project metadata & dependencies
└── README.md
```

## Mock Mode

Aktifkan `MOCK_MODE=true` di `.env` untuk testing tanpa GLPI server. Mock data tersedia untuk:
- 5 Computers (laptops, desktops, server)
- 4 Contracts (hardware support, software license, internet)
- 3 Users dengan groups
- 2 Tickets
- 3 Knowledge Base articles
- 9 ITIL Categories
- 5 Suppliers

## Next Steps for Developers

1. **Disable verbose mode** di production (`verbose=True` di `crew_services.py` dan `it_support.py`)
2. **Add rate limiting** ke endpoint `/v1/chat/completions`
3. **Add proper logging config** untuk production
4. **Implement health check** ke GLPI & AI Gateway
5. **Add more agents** (HR, Finance, dll) di `app/agents/`
6. **Add unit tests** untuk tools dan client
7. **Add CI/CD** workflow di `.github/workflows/`

## Tech Stack

- **FastAPI** - Web framework
- **CrewAI** - Multi-agent AI framework
- **LiteLLM** - Unified LLM interface (Nemotron via AI Gateway)
- **httpx** - Async HTTP client untuk GLPI API
- **Pydantic Settings** - Configuration management

## License

Internal use only.
