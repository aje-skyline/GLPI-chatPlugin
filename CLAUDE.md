# GLPI AI Gateway - Project Guide

## Project Overview

**GLPI AI Gateway** is a FastAPI-based chatbot that provides an OpenAI-compatible API for querying GLPI (IT Asset Management) data using CrewAI agents. The system acts as a bridge between a front-end chat interface and a GLPI instance.

**Version:** 3.0.0
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
│   ├── main.py                  # FastAPI entry point (v3.0.0)
│   ├── config.py                # Pydantic Settings & environment variables
│   ├── cache.py                 # In-memory TTL cache
│   ├── utils.py                 # Agent output sanitizer
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── agent_factory.py     # LLM & Agent singleton factory
│   │   └── prompt_builder.py    # Task description builder
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── async_runner.py      # Background event loop
│   │   ├── glpi_gateway.py      # GLPI REST client with retry
│   │   ├── http_client.py       # Shared httpx client
│   │   └── session_manager.py   # GLPI session lifecycle
│   ├── repository/
│   │   ├── __init__.py
│   │   ├── _glpi_helpers.py     # Parsing helpers
│   │   ├── asset_repository.py  # Computer data (708 lines)
│   │   ├── contract_repository.py
│   │   ├── pagination.py        # Auto-pagination
│   │   ├── supplier_repository.py
│   │   ├── ticket_repository.py
│   │   └── utility_repository.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat_flow.py         # GLPIChatFlow (CrewAI Flow + persist)
│   │   ├── conversational_flow.py # ConversationalFlow (simpler async Flow)
│   │   └── crew_orchestrator.py # Crew execution + SSE + 429 retry
│   └── tools/
│       ├── __init__.py          # Tool registry (20 tools)
│       ├── computer_tools.py    # 9 computer tools
│       ├── contract_tools.py    # 3 contract tools
│       ├── formatters.py        # Output formatting
│       ├── supplier_tools.py    # 2 supplier tools
│       └── ticket_tools.py      # 6 ticket/KB/utility tools
├── .env                         # Environment config (gitignored)
├── .env.example                 # Template for .env
├── pyproject.toml               # Project metadata & dependencies
└── CLAUDE.md                    # This file
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
  "model": "qwen/qwen3-next-80b-a3b-instruct",
  "session_id": "abc-123",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Jawaban..."},
    "finish_reason": "stop"
  }]
}
```

## Session Management & Conversational Flow

The system supports two conversational flow implementations:

### GLPIChatFlow (CrewAI Flow + persist)
- **Class:** `GLPIChatFlow` in `app/services/chat_flow.py`
- Decorated with `@persist()` for automatic conversation turn management
- **GLPIChatState**: Stores `id` (session UUID), `glpi_user_id`, `current_message`, `conversation_history`, and `final_response`
- Uses a `@router` step to classify messages as **casual** or **technical** via LiteLLM
- **Casual Branch**: Greetings handled quickly without invoking Crew/Tools
- **Technical Branch**: GLPI queries routed to `run_crew` orchestrator

### ConversationalFlow (Simpler async Flow)
- **Class:** `ConversationalFlow` in `app/services/conversational_flow.py`
- Event-driven: `initialize_interaction()` → `trigger_crew_agent()`
- Uses `run_crew_async()` for non-blocking execution
- Used by the streaming path in `main.py`

### Session ID Resolution
- Priority: `body.session_id` > `X-Session-ID` header > MD5 fingerprint > random UUID
- Session ID returned in response header `X-Session-ID`

### History Merge
Incoming messages merged with stored session history via `_merge_conversation_history()`.

### Other Session Properties
- **User ID persistence**: `glpi_user_id` stored per session
- **Session TTL**: 60 minutes (configurable via `session_ttl_minutes`)
- **Max messages per session**: 20 (configurable `_MAX_SESSION_MESSAGES`)

## Streaming Support

The system implements emulated SSE streaming with OpenAI-compatible chunk format:
- **Thought events**: Agent reasoning steps streamed as SSE `thought` events
- **Status heartbeats**: Keep-alive every ~3 seconds with rotating status messages
- **Word-by-word streaming**: Final answer streamed as OpenAI `data: {...}` chunks (~30ms per word)
- **Server timeout**: 80 seconds hard cap, then cancels crew execution
- **Sentinel**: `data: [DONE]\n\n` marks completion

## CrewAI Tools

The system has **20 tools** registered in `app/tools/__init__.py`:

### Computer Domain (9 tools)
| Tool | Function |
|------|----------|
| `search_knowledge_base` | Search KB articles |
| `get_user_assets` | Get computers owned by user |
| `get_all_computers` | List all computers (smart pagination) |
| `get_computer_detail` | Get full computer details |
| `count_all_computers` | Count total computers |
| `search_computer_by_name` | Search by computer name |
| `search_computer` | Universal search (name, serial, inventory) |
| `get_computers_by_status` | Filter by status |
| `get_computers_by_location` | Filter by location |

### Computer OS (1 tool)
| Tool | Function |
|------|----------|
| `get_computers_by_os` | Filter by operating system |

### Supplier Domain (2 tools)
| Tool | Function |
|------|----------|
| `get_suppliers` | Search/list suppliers |
| `count_suppliers` | Count total suppliers |

### Contract Domain (3 tools)
| Tool | Function |
|------|----------|
| `get_contracts` | List contracts |
| `get_contract_detail` | Get contract details |
| `count_contracts` | Count total contracts |

### Ticket/User Domain (2 tools)
| Tool | Function |
|------|----------|
| `get_user_tickets` | Get user tickets |
| `get_user_info` | Get user profile |

### Utility Domain (3 tools)
| Tool | Function |
|------|----------|
| `get_itil_categories` | List ITIL categories |
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

### 429 Rate-Limit Retry
The orchestrator implements exponential backoff (5s → 10s → 20s, max 3 retries) for OpenAI `RateLimitError` on both blocking and async crew execution paths.

### Key Bugs Fixed
- **v2.1**: Fixed session history merge logic (exclude only last user message)
- **v2.1**: Fixed event loop/async lock issues (lazy initialization)
- **v2.2**: Emulated SSE streaming for PHP compatibility
- **v2.3**: Fixed model default to `qwen/qwen3-next-80b-a3b-instruct`, added 429 retry with backoff, renamed `NEMOTRON_MODEL` → `AI_MODEL`
- **v3.0**: Router-based intent classification, persistent bg event loop, 20 tools

## Environment Variables

```bash
# AI Gateway (Nemotron)
AI_GATEWAY_URL=https://ai-gw.example.com/v1/chat/completions
AI_GATEWAY_BASE_URL=https://ai-gw.example.com/v1
AI_GATEWAY_API_KEY=sk-xxx
AI_MODEL=qwen/qwen3-next-80b-a3b-instruct

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

1. **Verbose mode** is enabled in `crew_orchestrator.py` and `agent_factory.py` — disable in production
2. **MOCK_MODE** can be set in `.env` to test without GLPI
3. GLPI field IDs in Search API may vary by version — verify with `list_search_options('Computer')`
4. Session data is in-memory only — lost on restart

## Future Improvements

1. Add rate limiting to endpoint
2. Add proper logging config for production
3. Add GLPI health check to `/health` endpoint
4. Add more agents (SCCM, HR, Finance) — see `docs/planned/` for Phase 2 plans
5. Add CI/CD workflow
6. Add direct GLPI DB connector for health analysis
7. Add Celery + Redis for background workers
