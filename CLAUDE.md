# GLPI AI Gateway - Project Guide

## Project Overview

**GLPI AI Gateway** is a FastAPI-based chatbot that provides an OpenAI-compatible API for querying GLPI (IT Asset Management) data using CrewAI agents. The system acts as a bridge between a front-end chat interface and a GLPI instance.

**Version:** 2.2.0
**Architecture:** FastAPI + CrewAI + LiteLLM (Nemotron)

## Technology Stack

- **FastAPI** — Web framework (v0.136.1+)
- **CrewAI** — Multi-agent AI orchestration (v1.6.1+)
- **LiteLLM** — Unified LLM interface for Nemotron model
- **httpx** — Async HTTP client for GLPI API
- **Pydantic Settings** — Configuration management
- **Python 3.12+**

## Directory Structure

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
├── pyproject.toml               # Project metadata & dependencies
└── CLAUDE.md                   # This file
```

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check & service info |
| `/v1/chat/completions` | POST | Bearer token | Main chat endpoint (JSON or SSE) |

### Request Format
```json
{
  "messages": [{"role": "user", "content": "Pertanyaan Anda"}],
  "glpi_user_id": 0,
  "session_id": "abc-123",
  "stream": false
}
```

### Response Format (Non-streaming)
```json
{
  "id": "glpi-crew-xxx",
  "object": "chat.completion",
  "model": "nemotron-crew/qwen/qwen3-next-80b-a3b-instruct",
  "session_id": "body:abc-123",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Jawaban..."},
    "finish_reason": "stop"
  }]
}
```

## Session Management

The system maintains in-memory sessions with:
- **Session ID resolution**: body > X-Session-ID header > MD5 fingerprint > random UUID
- **History merge**: Incoming messages merged with stored session history
- **User ID persistence**: `glpi_user_id` stored per session
- **Session TTL**: 60 minutes (configurable)
- **Max messages per session**: 20

## Streaming Support

The system implements emulated SSE streaming:
- **Phase 1**: Status/heartbeat events while CrewAI blocks (every 2-5 seconds)
- **Phase 2**: Word-by-word answer streaming (~30ms per word)
- **Phase 3**: `[DONE]` sentinel

## CrewAI Tools

| Tool | Function |
|------|----------|
| `search_knowledge_base` | Search KB articles |
| `get_user_assets` | Get computers owned by user |
| `get_all_computers` | List all computers |
| `get_computer_detail` | Get full computer details |
| `count_all_computers` | Count total computers |
| `search_computer_by_name` | Search by computer name |
| `search_computer` | Universal search (name, serial, inventory) |
| `list_all_contracts` | List contracts |
| `get_contract_detail` | Get contract details |
| `get_user_tickets` | Get user tickets |
| `get_user_info` | Get user profile |
| `get_itil_categories` | List ITIL categories |
| `get_suppliers` | List suppliers |
| `get_multiple_items` | Fetch multiple item types |
| `list_search_options` | List GLPI search fields |

## Important Implementation Details

### Event Loop Architecture
The system uses a **persistent background event loop** in a daemon thread to handle async GLPI calls. This prevents the "Event loop is closed" issue that occurs with repeated `asyncio.run()` calls.

### GLPI API Session Management
- Single GLPI session token is shared across requests
- Session is lazily initialized and auto-refreshed on 401 errors
- TTL cache (5 minutes) for static data (categories, suppliers, KB)

### Anti-Hallucination Rules
The IT Support Agent has strict rules:
1. **MUST** use tools for data queries
2. **MUST** base answers 100% on tool output
3. **MUST NOT** display internal format (JSON, Thought, Action)
4. **MUST** use Indonesian language

### Key Bugs Fixed
- **v2.1**: Fixed session history merge logic (exclude only last user message)
- **v2.1**: Fixed event loop/async lock issues (lazy initialization)
- **v2.2**: Emulated SSE streaming for PHP compatibility

## Environment Variables

```bash
# AI Gateway (Nemotron)
AI_GATEWAY_URL=https://ai-gw.example.com/v1/chat/completions
AI_GATEWAY_BASE_URL=https://ai-gw.example.com/v1
AI_GATEWAY_API_KEY=sk-xxx
NEMOTRON_MODEL=qwen/qwen3-next-80b-a3b-instruct

# FastAPI Security
GATEWAY_API_KEY=your-secret
ALLOWED_ORIGINS=http://localhost:3000

# GLPI API
GLPI_URL=http://glpi.example.com
GLPI_APP_TOKEN=xxx
GLPI_USER_TOKEN=xxx

# Optional
MOCK_MODE=false
```

## Running the Server

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or with uv
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Testing

```bash
# Non-streaming
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Daftar semua komputer"}], "glpi_user_id": 0}'

# Streaming
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Daftar semua komputer"}], "stream": true}'
```

## Development Notes

1. **Verbose mode** is enabled in `crew_services.py` and `it_support.py` — disable in production
2. **MOCK_MODE** can be set in `.env` to test without GLPI
3. GLPI field IDs in Search API may vary by version — verify with `list_search_options('Computer')`
4. Session data is in-memory only — lost on restart

## Future Improvements (from README)

1. Add rate limiting to endpoint
2. Add proper logging config for production
3. Add GLPI health check to `/health` endpoint
4. Add more agents (HR, Finance)
5. Add CI/CD workflow