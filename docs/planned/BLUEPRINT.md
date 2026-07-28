# BLUEPRINT — PHASE 2: EKSTENSI AI GLPI

> Dokumen blueprint teknis untuk pengembangan Phase 2 GLPI AI Extension.
> Berdasarkan analisis kode existing dan keputusan arsitektur yang telah disetujui.

---

## 1. Status Kode Saat Ini

### 1.1 GLPI Plugin (`/var/www/glpi/plugins/chatbot/`)

| Komponen | Status | Detail |
|----------|--------|--------|
| Plugin Registration | ✅ Berfungsi | GLPI 11.0.0–12.0.0, PHP 8.1+, v1.0.0 |
| Chat UI | ✅ Berfungsi | Inline HTML/PHP di `front/chat.php`, SSE streaming |
| Session Management | ✅ Berfungsi | 2 tabel DB (sessions, messages), CRUD via `ajax/sessions.php` |
| AI Backend | ✅ Berfungsi | `ajax/chat.php` → cURL ke AI Gateway, SSE forwarding |
| CSS/JS | ✅ Berfungsi | `css/chat.css`, `js/chat.js`, inlined via `file_get_contents()` |
| Config | ⚠️ Hardcoded | `inc/config.php` menggunakan `define()`, tidak DB-driven |
| Twig Templates | ❌ Tidak ada | UI inline HTML/PHP |
| Config Page | ❌ Tidak ada | Tidak ada halaman konfigurasi di GLPI |
| Access Control | ⚠️ Minimal | Hanya cek `Session::getLoginUserID()`, tidak ada profile-based |
| Audit Logging | ❌ Tidak ada | Tidak ada audit trail |
| Health Dashboard | ❌ Tidak ada | Tidak ada UI untuk Asset Health |

**Struktur File Plugin Saat Ini:**

```
/var/www/glpi/plugins/chatbot/
├── .env                              # Tidak dipakai oleh kode
├── setup.php                         # Plugin registration (v1.0.0)
├── hook.php                          # Install/uninstall + 2 tabel DB
├── logo.png
├── README.md
├── inc/
│   ├── chat.class.php                # CommonGLPI subclass, menu registration
│   └── config.php                    # Hardcoded constants (API_KEY, URL, MODEL, PROMPT)
├── ajax/
│   ├── chat.php                      # AI backend: context, SSE streaming, cURL
│   ├── chat.php.bak                  # Backup dengan user context aktif
│   └── sessions.php                  # Session CRUD (list, messages, create, rename, delete)
├── front/
│   ├── chat.php                      # Main UI page (inline HTML + CSS + JS)
│   └── chat_backup.php               # Backup dengan sidebar
├── css/
│   └── chat.css                      # Chat styles (111 lines)
└── js/
    └── chat.js                       # Chat logic (358 lines, SSE consumer, markdown)
```

**Database Schema Plugin:**

```sql
-- Sudah ada (dibuat oleh hook.php)
CREATE TABLE glpi_plugin_chatbot_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    users_id INT NOT NULL,
    title VARCHAR(255) DEFAULT 'New Chat',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_users_id (users_id)
);

CREATE TABLE glpi_plugin_chatbot_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sessions_id INT NOT NULL,
    role VARCHAR(20) NOT NULL,  -- 'user' atau 'assistant'
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sessions_id (sessions_id),
    INDEX idx_created_at (created_at)
);
```

### 1.2 AI Engine (`/home/ariel/projects/chatbot-fastapi/`)

| Komponen | Status | Detail |
|----------|--------|--------|
| FastAPI App | ✅ Berfungsi | v3.0.0, entry point `app/main.py` (490 lines) |
| Chat Endpoint | ✅ Berfungsi | `/v1/chat/completions`, OpenAI-compatible, SSE streaming |
| Health Endpoint | ✅ Berfungsi | `/health`, service info |
| CrewAI Agent | ✅ Berfungsi | Single agent "IT Support Specialist GLPI", 20 tools |
| LLM Integration | ✅ Berfungsi | AI Gateway `ai-gw.stidev.biz.id`, model Qwen 3 80B |
| GLPI REST API | ✅ Berfungsi | `172.16.14.103/apirest.php`, session token management |
| Chat Flow | ✅ Berfungsi | CrewAI Flow + router (casual/technical) |
| Session Management | ✅ Berfungsi | In-memory dengan TTL, session ID resolution |
| Caching | ✅ Berfungsi | In-memory TTL cache (5 min) |
| Docker | ❌ Tidak ada | Tidak ada Dockerfile/docker-compose |
| Celery + Redis | ❌ Tidak ada | Tidak ada background worker |
| Direct DB Access | ❌ Tidak ada | Hanya via REST API |
| SCCM Connector | ❌ Tidak ada | Belum ada |
| Health Analysis | ❌ Tidak ada | Belum ada |
| Config API | ❌ Tidak ada | Belum ada |
| Tests | ❌ Tidak ada | Hanya `test_httpx.py` manual |

**Struktur File AI Engine Saat Ini:**

```
/home/ariel/projects/chatbot-fastapi/
├── .env                              # Konfigurasi aktif (gitignored)
├── .env.example                      # Template
├── .gitignore
├── .python-version                   # 3.12
├── CLAUDE.md                         # AI assistant guide
├── PROJECT_CONTEXT.md                # Fix history
├── README.md
├── pyproject.toml                    # Dependencies
├── uv.lock
├── test_httpx.py                     # Manual test
├── .venv/                            # Virtual environment
├── .git/
└── app/
    ├── __init__.py
    ├── main.py                       # FastAPI entry (490 lines)
    ├── config.py                     # Pydantic Settings (83 lines)
    ├── cache.py                      # In-memory TTL cache (130 lines)
    ├── utils.py                      # Agent output sanitizer (78 lines)
    ├── agents/
    │   ├── __init__.py               # Exports build_it_support
    │   ├── agent_factory.py          # LLM & Agent singleton (246 lines)
    │   └── prompt_builder.py         # Task description builder (318 lines)
    ├── infrastructure/
    │   ├── __init__.py               # Re-exports
    │   ├── async_runner.py           # Background event loop (169 lines)
    │   ├── glpi_gateway.py           # GLPI REST client (201 lines)
    │   ├── http_client.py            # Shared httpx client (159 lines)
    │   └── session_manager.py        # GLPI session lifecycle (225 lines)
    ├── repository/
    │   ├── __init__.py
    │   ├── _glpi_helpers.py          # Parsing helpers (108 lines)
    │   ├── asset_repository.py       # Computer data (708 lines)
    │   ├── contract_repository.py    # Contract data (146 lines)
    │   ├── pagination.py             # Auto-pagination (213 lines)
    │   ├── supplier_repository.py    # Supplier data (319 lines)
    │   ├── ticket_repository.py      # Ticket/user/KB (241 lines)
    │   └── utility_repository.py     # Multi-item & search (91 lines)
    ├── services/
    │   ├── __init__.py
    │   ├── chat_flow.py              # CrewAI Flow + router (118 lines)
    │   ├── conversational_flow.py    # Simpler async Flow (49 lines)
    │   └── crew_orchestrator.py      # Crew execution + SSE (382 lines)
    └── tools/
        ├── __init__.py               # Tool registry (155 lines)
        ├── computer_tools.py         # 9 computer tools (477 lines)
        ├── contract_tools.py         # 3 contract tools (223 lines)
        ├── formatters.py             # Output formatting (530 lines)
        ├── supplier_tools.py         # 2 supplier tools (198 lines)
        └── ticket_tools.py           # 6 ticket/KB/utility tools (334 lines)
```

**CrewAI Tools yang Sudah Ada (20 tools):**

| Tool | Domain | Fungsi |
|------|--------|--------|
| `search_knowledge_base` | KB | Cari artikel KB |
| `get_user_assets` | Computer | Komputer milik user |
| `get_all_computers` | Computer | Daftar semua komputer (smart pagination) |
| `get_computer_detail` | Computer | Detail komputer |
| `count_all_computers` | Computer | Hitung total komputer |
| `search_computer_by_name` | Computer | Cari by nama |
| `search_computer` | Computer | Universal search (name, serial, inventory) |
| `get_computers_by_status` | Computer | Filter by status |
| `get_computers_by_location` | Computer | Filter by lokasi |
| `get_computers_by_os` | Computer | Filter by OS |
| `get_suppliers` | Supplier | Daftar/cari supplier |
| `count_suppliers` | Supplier | Hitung total supplier |
| `count_contracts` | Contract | Hitung total kontrak |
| `list_all_contracts` | Contract | Daftar kontrak (smart pagination) |
| `get_contract_detail` | Contract | Detail kontrak |
| `get_user_tickets` | Ticket | Tiket user |
| `get_user_info` | Ticket | Profil user |
| `get_itil_categories` | Utility | Daftar kategori ITIL |
| `get_multiple_items` | Utility | Fetch multiple item types |
| `list_search_options` | Utility | Daftar GLPI search fields |

---

## 2. Keputusan Arsitektur

| Keputusan | Pilihan | Alasan |
|-----------|---------|--------|
| Repository | **Separate repos** | Plugin & AI Engine terpisah, koordinasi via API |
| GLPI Access | **REST API (existing) + Direct DB read-only (baru)** | REST API sudah ada, Direct DB perlu untuk query kompleks health analysis |
| SCCM Access | **Direct SQL Server** | Sesuai ketersediaan di AHM |
| Plugin UI | **Refactor ke Twig** | Sesuai konvensi GLPI 11, lebih maintainable |
| Agent Architecture | **Single agent + tools (Chat), Multi-agent crew (Health)** | Chat sudah berfungsi, Health butuh multi-step analysis |
| Prioritas | **SCCM + Health dulu** | Chat sudah basic berfungsi |
| SCCM Reachability | **Belum diketahui** | Perlu koordinasi dengan tim infrastruktur AHM |

---

## 3. Arsitektur Target

```
┌─────────────────────────────────────────────────────────────────────┐
│                          GLPI 11.0.6                                │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                GLPI AI Plugin (PHP/Twig)                       │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │ │
│  │  │ Chat UI  │ │Dashboard │ │ Config   │ │ Audit Log      │  │ │
│  │  │ (Twig)   │ │ (Twig)   │ │ (Twig)   │ │ (DB table)     │  │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬─────────┘  │ │
│  └───────┼─────────────┼────────────┼──────────────┼────────────┘ │
└──────────┼─────────────┼────────────┼──────────────┼──────────────┘
           │             │            │              │
           ▼             ▼            ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                AI Engine (Docker — Python/FastAPI)                  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  FastAPI (existing, enhanced)                                  │ │
│  │  ┌─────────────────────┐  ┌────────────────────────────────┐ │ │
│  │  │ /v1/chat/completions│  │ /api/health/*                  │ │ │
│  │  │ (existing)          │  │ /api/health/analyze  (NEW)     │ │ │
│  │  │                     │  │ /api/health/status   (NEW)     │ │ │
│  │  │                     │  │ /api/health/report   (NEW)     │ │ │
│  │  │                     │  │ /api/health/dashboard(NEW)     │ │ │
│  │  │                     │  │ /api/health/correlate(NEW)     │ │ │
│  │  │                     │  │ /api/config          (NEW)     │ │ │
│  │  └─────────────────────┘  └────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────┐  ┌────────────────────────────────────┐ │
│  │  Chat Crew           │  │  Health Analysis Crew (NEW)        │ │
│  │  (existing:          │  │  ┌──────────────────────────────┐ │ │
│  │   single agent       │  │  │ DataCollectorAgent           │ │ │
│  │   + 20 tools)        │  │  │ PatternAnalyzerAgent         │ │ │
│  │                      │  │  │ RiskAssessorAgent            │ │ │
│  │                      │  │  │ RecommendationAgent          │ │ │
│  │                      │  │  └──────────────────────────────┘ │ │
│  └──────────────────────┘  └────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Background Worker — Celery + Redis (NEW)                     │ │
│  │  - Asset Health Analysis (scheduled)                          │ │
│  │  - GLPI-SCCM Correlation (scheduled)                          │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└──────────┬──────────────────────────┬────────────────────────────────┘
           │                          │
     ┌─────┴──────┐          ┌───────┴────────┐
     │ GLPI DB    │          │ SCCM DB        │
     │ (MariaDB)  │          │ (SQL Server)   │
     │ read-only  │          │ read-only      │
     └────────────┘          └────────────────┘
```

---

## 4. Sprint Plan (14 Sprints)

### SPRINT 1-2: FOUNDATION & DOCKER

**Tujuan:** Setup Docker, config page, GLPI DB connector, FastAPI refactor

#### 4.1.1 Docker Setup (AI Engine Repo)

**File Baru:**

```
ai-engine/docker/
├── Dockerfile
├── Dockerfile.worker
├── docker-compose.yml
└── .dockerignore
```

**`docker/Dockerfile`** — FastAPI App Container:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libmariadb-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY app/ app/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`docker/Dockerfile.worker`** — Celery Worker Container:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libmariadb-dev freetds-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY app/ app/

CMD ["uv", "run", "celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info"]
```

**`docker/docker-compose.yml`:**

```yaml
version: "3.8"

services:
  ai-engine:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - ../.env
    depends_on:
      - redis
    restart: unless-stopped
    networks:
      - ai-network

  celery-worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.worker
    env_file:
      - ../.env
    depends_on:
      - redis
    restart: unless-stopped
    networks:
      - ai-network

  celery-beat:
    build:
      context: ..
      dockerfile: docker/Dockerfile.worker
    command: ["uv", "run", "celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info"]
    env_file:
      - ../.env
    depends_on:
      - redis
    restart: unless-stopped
    networks:
      - ai-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - ai-network

networks:
  ai-network:
    driver: bridge

volumes:
  redis-data:
```

**`docker/.dockerignore`:**

```
.venv/
.git/
__pycache__/
*.pyc
.env
*.md
test_*
```

#### 4.1.2 GLPI Plugin Config Page (Plugin Repo)

**Database Schema Baru:**

```sql
-- Ditambahkan di hook.php plugin_chatbot_install()
CREATE TABLE IF NOT EXISTS glpi_plugin_chatbot_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_config_key (config_key)
);

-- Default values (inserted on install)
INSERT INTO glpi_plugin_chatbot_config (config_key, config_value) VALUES
    ('api_url', 'http://127.0.0.1:8000/v1/chat/completions'),
    ('api_key', 'internal-glpi-secret-123'),
    ('api_model', 'aj/ai'),
    ('system_prompt', 'Kamu adalah AI Assistant resmi untuk sistem GLPI...'),
    ('max_tokens', '1024'),
    ('temperature', '0.3'),
    ('streaming_enabled', '1');
```

**File Baru/Modifikasi di Plugin:**

```
glpi-plugin/
├── inc/
│   ├── config.php              # DEPRECATE — ganti dengan ConfigService
│   └── config.class.php        # NEW — DB-driven config class
├── front/
│   ├── config.php              # NEW — Config page entry point
│   └── chat.php                # EXISTING — update untuk baca config dari DB
├── ajax/
│   ├── chat.php                # EXISTING — update untuk baca config dari DB
│   └── config.php              # NEW — Config AJAX handler (save/load)
├── views/                      # NEW DIRECTORY
│   └── config.twig             # NEW — Config form template
├── js/
│   └── config.js               # NEW — Config form logic
└── css/
    └── config.css              # NEW — Config form styles
```

**`inc/config.class.php`** — Config Class:

```php
<?php
class PluginChatbotConfig extends CommonDBTM {
    public static $rightname = 'config';

    public static function getTypeName($nb = 0) {
        return __('AI Chatbot Configuration', 'chatbot');
    }

    public static function getConfigValue(string $key, string $default = ''): string {
        global $DB;
        $result = $DB->request([
            'FROM'   => 'glpi_plugin_chatbot_config',
            'WHERE'  => ['config_key' => $key]
        ])->current();
        return $result ? $result['config_value'] : $default;
    }

    public static function setConfigValue(string $key, string $value): bool {
        global $DB;
        return $DB->updateOrInsert(
            'glpi_plugin_chatbot_config',
            ['config_value' => $value, 'updated_at' => date('Y-m-d H:i:s')],
            ['config_key' => $key]
        );
    }

    public static function getAllConfig(): array {
        global $DB;
        $config = [];
        foreach ($DB->request(['FROM' => 'glpi_plugin_chatbot_config']) as $row) {
            $config[$row['config_key']] = $row['config_value'];
        }
        return $config;
    }
}
```

**`views/config.twig`** — Config Form (Twig):

```twig
{# Config page for AI Chatbot plugin #}
<form method="post" action="{{ form_url }}" id="chatbot-config-form">
    <div class="card">
        <div class="card-header">
            <h3>{{ __('AI Chatbot Configuration', 'chatbot') }}</h3>
        </div>
        <div class="card-body">
            <div class="form-group">
                <label>{{ __('API URL', 'chatbot') }}</label>
                <input type="text" name="api_url" value="{{ config.api_url }}"
                       class="form-control" placeholder="http://127.0.0.1:8000/v1/chat/completions">
            </div>
            <div class="form-group">
                <label>{{ __('API Key', 'chatbot') }}</label>
                <input type="password" name="api_key" value="{{ config.api_key }}"
                       class="form-control">
            </div>
            <div class="form-group">
                <label>{{ __('Model', 'chatbot') }}</label>
                <input type="text" name="api_model" value="{{ config.api_model }}"
                       class="form-control">
            </div>
            <div class="form-group">
                <label>{{ __('System Prompt', 'chatbot') }}</label>
                <textarea name="system_prompt" class="form-control" rows="6">{{ config.system_prompt }}</textarea>
            </div>
            <div class="form-row">
                <div class="form-group col-md-4">
                    <label>{{ __('Max Tokens', 'chatbot') }}</label>
                    <input type="number" name="max_tokens" value="{{ config.max_tokens }}"
                           class="form-control" min="128" max="4096">
                </div>
                <div class="form-group col-md-4">
                    <label>{{ __('Temperature', 'chatbot') }}</label>
                    <input type="number" name="temperature" value="{{ config.temperature }}"
                           class="form-control" min="0" max="2" step="0.1">
                </div>
                <div class="form-group col-md-4">
                    <label>{{ __('Streaming', 'chatbot') }}</label>
                    <select name="streaming_enabled" class="form-control">
                        <option value="1" {{ config.streaming_enabled == '1' ? 'selected' : '' }}>
                            {{ __('Enabled', 'chatbot') }}
                        </option>
                        <option value="0" {{ config.streaming_enabled == '0' ? 'selected' : '' }}>
                            {{ __('Disabled', 'chatbot') }}
                        </option>
                    </select>
                </div>
            </div>
        </div>
        <div class="card-footer">
            <button type="submit" class="btn btn-primary">
                {{ __('Save', 'chatbot') }}
            </button>
            <input type="hidden" name="_glpi_csrf_token" value="{{ csrf_token }}">
        </div>
    </div>
</form>
```

**Modifikasi `setup.php`** — Tambah config ke menu:

```php
// Di plugin_init_chatbot(), tambahkan:
if (Session::haveRight('config', UPDATE)) {
    $PLUGIN_HOOKS['config_page']['chatbot'] = 'front/config.php';
}
```

**Modifikasi `hook.php`** — Tambah tabel config:

```php
// Di plugin_chatbot_install(), tambahkan setelah tabel messages:
$DB->query("CREATE TABLE IF NOT EXISTS `glpi_plugin_chatbot_config` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

// Insert default values
$defaults = [
    ['api_url', 'http://127.0.0.1:8000/v1/chat/completions'],
    ['api_key', 'internal-glpi-secret-123'],
    ['api_model', 'aj/ai'],
    ['system_prompt', 'Kamu adalah AI Assistant resmi untuk sistem GLPI (IT Service Management)...'],
    ['max_tokens', '1024'],
    ['temperature', '0.3'],
    ['streaming_enabled', '1'],
];
foreach ($defaults as [$key, $value]) {
    $DB->insert('glpi_plugin_chatbot_config', [
        'config_key'   => $key,
        'config_value' => $value,
    ]);
}

// Di plugin_chatbot_uninstall(), tambahkan:
$DB->query("DROP TABLE IF EXISTS `glpi_plugin_chatbot_config`");
```

#### 4.1.3 GLPI DB Connector (AI Engine Repo)

**File Baru:**

```
ai-engine/app/connectors/
├── __init__.py
└── glpi_db_connector.py
```

**`app/connectors/__init__.py`:**

```python
from .glpi_db_connector import glpi_db
```

**`app/connectors/glpi_db_connector.py`:**

```python
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
from app.config import Settings
import logging

logger = logging.getLogger(__name__)


class GLPIDBConnector:
    def __init__(self, settings: Settings):
        self._engine: Engine | None = None
        self._settings = settings
        self._metadata = MetaData()

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            url = (
                f"mysql+pymysql://{self._settings.glpi_db_user}:{self._settings.glpi_db_password}"
                f"@{self._settings.glpi_db_host}:{self._settings.glpi_db_port}"
                f"/{self._settings.glpi_db_name}"
            )
            self._engine = create_engine(
                url,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )
            logger.info(f"GLPI DB connector initialized: {self._settings.glpi_db_host}")
        return self._engine

    def execute_query(self, query: str, params: dict | None = None) -> list[dict]:
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    def get_computer_count_by_status(self) -> list[dict]:
        query = """
            SELECT states.name AS status, COUNT(*) AS count
            FROM glpi_computers c
            LEFT JOIN glpi_states states ON states.id = c.states_id
            WHERE c.is_deleted = 0 AND c.is_template = 0
            GROUP BY c.states_id, states.name
            ORDER BY count DESC
        """
        return self.execute_query(query)

    def get_computer_age_distribution(self) -> list[dict]:
        query = """
            SELECT
                CASE
                    WHEN c.date_creation >= DATE_SUB(NOW(), INTERVAL 2 YEAR) THEN '< 2 years'
                    WHEN c.date_creation >= DATE_SUB(NOW(), INTERVAL 4 YEAR) THEN '2-4 years'
                    WHEN c.date_creation >= DATE_SUB(NOW(), INTERVAL 6 YEAR) THEN '4-6 years'
                    ELSE '> 6 years'
                END AS age_group,
                COUNT(*) AS count
            FROM glpi_computers c
            WHERE c.is_deleted = 0 AND c.is_template = 0
            GROUP BY age_group
            ORDER BY FIELD(age_group, '< 2 years', '2-4 years', '4-6 years', '> 6 years')
        """
        return self.execute_query(query)

    def get_ticket_frequency_by_computer(self, months: int = 6) -> list[dict]:
        query = """
            SELECT
                items.items_id AS computer_id,
                c.name AS computer_name,
                COUNT(DISTINCT t.id) AS ticket_count
            FROM glpi_items_tickets items
            JOIN glpi_tickets t ON t.id = items.tickets_id
            JOIN glpi_computers c ON c.id = items.items_id
            WHERE items.itemtype = 'Computer'
              AND t.date >= DATE_SUB(NOW(), INTERVAL :months MONTH)
              AND c.is_deleted = 0
            GROUP BY items.items_id, c.name
            ORDER BY ticket_count DESC
        """
        return self.execute_query(query, {"months": months})

    def get_warranty_status(self) -> list[dict]:
        query = """
            SELECT
                c.id AS computer_id,
                c.name AS computer_name,
                con.end_date AS warranty_end,
                CASE
                    WHEN con.end_date IS NULL THEN 'no_warranty'
                    WHEN con.end_date < NOW() THEN 'expired'
                    WHEN con.end_date < DATE_ADD(NOW(), INTERVAL 6 MONTH) THEN 'expiring_soon'
                    ELSE 'active'
                END AS warranty_status
            FROM glpi_computers c
            LEFT JOIN glpi_contracts_items ci ON ci.items_id = c.id AND ci.itemtype = 'Computer'
            LEFT JOIN glpi_contracts con ON con.id = ci.contracts_id
            WHERE c.is_deleted = 0 AND c.is_template = 0
        """
        return self.execute_query(query)

    def get_computer_details_for_health(self, computer_id: int) -> dict | None:
        query = """
            SELECT
                c.id, c.name, c.date_creation, c.date_mod,
                c.states_id, states.name AS status_name,
                m.name AS manufacturer_name,
                ct.name AS computer_type,
                loc.name AS location_name,
                u.name AS user_name,
                os.name AS os_name,
                c.date_last_boot
            FROM glpi_computers c
            LEFT JOIN glpi_states states ON states.id = c.states_id
            LEFT JOIN glpi_manufacturers m ON m.id = c.manufacturers_id
            LEFT JOIN glpi_computertypes ct ON ct.id = c.computertypes_id
            LEFT JOIN glpi_locations loc ON loc.id = c.locations_id
            LEFT JOIN glpi_users u ON u.id = c.users_id
            LEFT JOIN glpi_operatingsystems os ON os.id = c.operatingsystems_id
            WHERE c.id = :computer_id AND c.is_deleted = 0
        """
        rows = self.execute_query(query, {"computer_id": computer_id})
        return rows[0] if rows else None

    def close(self):
        if self._engine:
            self._engine.dispose()
            self._engine = None


glpi_db: GLPIDBConnector | None = None


def init_glpi_db(settings: Settings):
    global glpi_db
    glpi_db = GLPIDBConnector(settings)


def get_glpi_db() -> GLPIDBConnector:
    if glpi_db is None:
        raise RuntimeError("GLPI DB connector not initialized")
    return glpi_db
```

**Modifikasi `app/config.py`** — Tambah GLPI DB settings:

```python
# Tambah ke class Settings:
glpi_db_host: str = "127.0.0.1"
glpi_db_port: int = 3306
glpi_db_name: str = "glpi"
glpi_db_user: str = "glpi_readonly"
glpi_db_password: str = ""
```

**Modifikasi `app/main.py`** — Init GLPI DB connector on startup:

```python
from app.connectors import init_glpi_db

# Di lifespan/startup event:
@app.on_event("startup")
async def startup():
    init_glpi_db(settings)
```

#### 4.1.4 FastAPI Route Refactor (AI Engine Repo)

**File Baru:**

```
ai-engine/app/api/
├── __init__.py
├── main.py                  # Slim entry point (router aggregation)
└── routes/
    ├── __init__.py
    ├── chat.py              # Extract dari main.py
    └── health.py            # Placeholder
```

**`app/api/main.py`** — Slim Entry Point:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import Settings
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router

settings = Settings()

app = FastAPI(
    title="GLPI AI Gateway",
    version="4.0.0",
    description="AI-powered GLPI IT Asset Management Gateway",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, tags=["Chat"])
app.include_router(health_router, prefix="/api/health", tags=["Health"])


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "GLPI AI Gateway",
        "version": "4.0.0",
        "ai_model": settings.ai_model,
    }
```

**`app/api/routes/chat.py`** — Extract Chat Logic:

```python
from fastapi import APIRouter, Header, Request
# ... (move chat endpoint logic from current main.py)

router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str = Header(None),
):
    # ... existing logic from main.py
    pass
```

**`app/api/routes/health.py`** — Placeholder:

```python
from fastapi import APIRouter

router = APIRouter()

@router.post("/analyze")
async def trigger_analysis():
    return {"status": "not_implemented", "message": "Health analysis coming in Sprint 5-6"}

@router.get("/status/{job_id}")
async def get_analysis_status(job_id: str):
    return {"status": "not_implemented"}

@router.get("/report/{asset_id}")
async def get_health_report(asset_id: int):
    return {"status": "not_implemented"}

@router.get("/dashboard")
async def get_dashboard():
    return {"status": "not_implemented"}

@router.post("/correlate")
async def trigger_correlation():
    return {"status": "not_implemented"}
```

---

### SPRINT 3-4: SCCM CONNECTOR + DATA LAYER

**Tujuan:** SCCM SQL Server connector, data normalization, GLPI-SCCM correlation

#### 4.2.1 SCCM Connector

**File Baru:**

```
ai-engine/app/connectors/
└── sccm_connector.py
```

**`app/connectors/sccm_connector.py`:**

```python
from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
from app.config import Settings
import logging

logger = logging.getLogger(__name__)


class SCCMConnector:
    def __init__(self, settings: Settings):
        self._engine: Engine | None = None
        self._settings = settings

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            url = (
                f"mssql+pymssql://{self._settings.sccm_db_user}:{self._settings.sccm_db_password}"
                f"@{self._settings.sccm_db_host}:{self._settings.sccm_db_port}"
                f"/{self._settings.sccm_db_name}"
            )
            self._engine = create_engine(
                url,
                poolclass=QueuePool,
                pool_size=3,
                max_overflow=5,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )
            logger.info(f"SCCM DB connector initialized: {self._settings.sccm_db_host}")
        return self._engine

    def execute_query(self, query: str, params: dict | None = None) -> list[dict]:
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    def get_all_systems(self) -> list[dict]:
        query = """
            SELECT
                sys.ResourceID,
                sys.Name0 AS hostname,
                sys.ResourceDomain_OR_Workgr0 AS domain,
                sys.Client0 AS client_installed,
                sys.Operating_System_Name_and0 AS os_name,
                sys.Active0 AS is_active
            FROM v_R_System sys
            WHERE sys.Obsolete0 = 0
            ORDER BY sys.Name0
        """
        return self.execute_query(query)

    def get_computer_hardware(self, resource_id: int) -> dict | None:
        query = """
            SELECT
                cs.Manufacturer0 AS manufacturer,
                cs.Model0 AS model,
                cs.SystemType0 AS system_type,
                os.Name0 AS os_name,
                os.Version0 AS os_version,
                os.InstallDate0 AS os_install_date,
                os.LastBootUpTime0 AS last_boot,
                proc.Name0 AS processor,
                proc.NumberOfCores0 AS cores,
                mem.TotalPhysicalMemory0 AS total_memory_mb
            FROM v_GS_COMPUTER_SYSTEM cs
            LEFT JOIN v_GS_OPERATING_SYSTEM os ON os.ResourceID = cs.ResourceID
            LEFT JOIN v_GS_PROCESSOR proc ON proc.ResourceID = cs.ResourceID
            LEFT JOIN v_GS_X86_COMPUTER_SYSTEM mem ON mem.ResourceID = cs.ResourceID
            WHERE cs.ResourceID = :resource_id
        """
        rows = self.execute_query(query, {"resource_id": resource_id})
        return rows[0] if rows else None

    def get_software_inventory(self, resource_id: int) -> list[dict]:
        query = """
            SELECT
                sw.DisplayName0 AS software_name,
                sw.Version0 AS version,
                sw.Publisher0 AS publisher,
                sw.InstallDate0 AS install_date
            FROM v_GS_INSTALLED_SOFTWARE_CATEGORIZED sw
            WHERE sw.ResourceID = :resource_id
            ORDER BY sw.DisplayName0
        """
        return self.execute_query(query, {"resource_id": resource_id})

    def get_patch_compliance(self, resource_id: int) -> dict:
        query = """
            SELECT
                COUNT(*) AS total_updates,
                SUM(CASE WHEN cs.Status = 3 THEN 1 ELSE 0 END) AS installed,
                SUM(CASE WHEN cs.Status = 2 THEN 1 ELSE 0 END) AS missing,
                SUM(CASE WHEN cs.Status = 0 THEN 1 ELSE 0 END) AS unknown
            FROM v_Update_ComplianceStatus cs
            WHERE cs.ResourceID = :resource_id
        """
        rows = self.execute_query(query, {"resource_id": resource_id})
        if rows and rows[0].get("total_updates"):
            r = rows[0]
            total = r["total_updates"]
            installed = r.get("installed", 0) or 0
            return {
                "total_updates": total,
                "installed": installed,
                "missing": r.get("missing", 0) or 0,
                "unknown": r.get("unknown", 0) or 0,
                "compliance_pct": round((installed / total) * 100, 1) if total > 0 else 0,
            }
        return {"total_updates": 0, "installed": 0, "missing": 0, "unknown": 0, "compliance_pct": 0}

    def get_network_adapters(self, resource_id: int) -> list[dict]:
        query = """
            SELECT
                na.Description0 AS adapter_name,
                na.MACAddress0 AS mac_address,
                na.IPAddress0 AS ip_address,
                na.DefaultIPGateway0 AS gateway,
                na.DHCPEnabled0 AS dhcp_enabled
            FROM v_GS_NETWORK_ADAPTER na
            WHERE na.ResourceID = :resource_id
              AND na.IPEnabled0 = 1
        """
        return self.execute_query(query, {"resource_id": resource_id})

    def get_last_heartbeat(self, resource_id: int) -> dict | None:
        query = """
            SELECT
                ws.LastHWScan AS last_hardware_scan,
                ws.LastSWScan AS last_software_scan
            FROM v_GS_WORKSTATION_STATUS ws
            WHERE ws.ResourceID = :resource_id
        """
        rows = self.execute_query(query, {"resource_id": resource_id})
        return rows[0] if rows else None

    def find_by_hostname(self, hostname: str) -> dict | None:
        query = """
            SELECT ResourceID, Name0 AS hostname, Operating_System_Name_and0 AS os_name
            FROM v_R_System
            WHERE Name0 = :hostname AND Obsolete0 = 0
        """
        rows = self.execute_query(query, {"hostname": hostname})
        return rows[0] if rows else None

    def find_by_mac(self, mac_address: str) -> dict | None:
        query = """
            SELECT sys.ResourceID, sys.Name0 AS hostname
            FROM v_R_System sys
            JOIN v_GS_NETWORK_ADAPTER na ON na.ResourceID = sys.ResourceID
            WHERE na.MACAddress0 = :mac_address AND sys.Obsolete0 = 0
        """
        rows = self.execute_query(query, {"mac_address": mac_address})
        return rows[0] if rows else None

    def close(self):
        if self._engine:
            self._engine.dispose()
            self._engine = None


sccm_db: SCCMConnector | None = None


def init_sccm_db(settings: Settings):
    global sccm_db
    sccm_db = SCCMConnector(settings)


def get_sccm_db() -> SCCMConnector:
    if sccm_db is None:
        raise RuntimeError("SCCM DB connector not initialized")
    return sccm_db
```

**Modifikasi `app/config.py`** — Tambah SCCM settings:

```python
# Tambah ke class Settings:
sccm_db_host: str = ""
sccm_db_port: int = 1433
sccm_db_name: str = ""
sccm_db_user: str = ""
sccm_db_password: str = ""
```

#### 4.2.2 Data Normalization Layer

**File Baru:**

```
ai-engine/app/normalizers/
├── __init__.py
├── glpi_normalizer.py
├── sccm_normalizer.py
└── asset_mapper.py
```

**`app/normalizers/asset_mapper.py`** — GLPI ↔ SCCM Field Mapping:

```python
from pydantic import BaseModel


class NormalizedAsset(BaseModel):
    source: str                          # "glpi" | "sccm" | "both"
    hostname: str = ""
    serial_number: str = ""
    mac_addresses: list[str] = []
    manufacturer: str = ""
    model: str = ""
    os_name: str = ""
    os_version: str = ""
    ip_address: str = ""
    location: str = ""
    user_name: str = ""
    status: str = ""
    last_seen: str = ""
    glpi_id: int | None = None
    sccm_resource_id: int | None = None


class AssetMappingResult(BaseModel):
    glpi_asset: NormalizedAsset | None = None
    sccm_asset: NormalizedAsset | None = None
    match_status: str = "unmatched"      # matched | mismatch | missing_in_sccm | missing_in_glpi
    mismatches: list[dict] = []          # [{"field": "os_name", "glpi": "Windows 11", "sccm": "Windows 10"}]
    match_method: str = ""               # hostname | serial | mac
    match_confidence: float = 0.0        # 0.0 - 1.0
```

**`app/normalizers/glpi_normalizer.py`:**

```python
from app.normalizers.asset_mapper import NormalizedAsset


def normalize_glpi_computer(glpi_data: dict) -> NormalizedAsset:
    return NormalizedAsset(
        source="glpi",
        hostname=glpi_data.get("name", ""),
        serial_number=glpi_data.get("serial", ""),
        manufacturer=glpi_data.get("manufacturer", {}).get("name", ""),
        model=glpi_data.get("computermodel", {}).get("name", ""),
        os_name=glpi_data.get("operatingsystem", {}).get("name", ""),
        os_version=glpi_data.get("operatingsystemversion", ""),
        location=glpi_data.get("location", {}).get("name", ""),
        user_name=glpi_data.get("user", {}).get("name", ""),
        status=glpi_data.get("state", {}).get("name", ""),
        glpi_id=glpi_data.get("id"),
    )
```

**`app/normalizers/sccm_normalizer.py`:**

```python
from app.normalizers.asset_mapper import NormalizedAsset


def normalize_sccm_system(sccm_data: dict, hardware: dict | None = None) -> NormalizedAsset:
    hw = hardware or {}
    return NormalizedAsset(
        source="sccm",
        hostname=sccm_data.get("hostname", ""),
        manufacturer=hw.get("manufacturer", ""),
        model=hw.get("model", ""),
        os_name=hw.get("os_name", ""),
        os_version=hw.get("os_version", ""),
        sccm_resource_id=sccm_data.get("ResourceID"),
    )
```

#### 4.2.3 GLPI-SCCM Correlator

**File Baru:**

```
ai-engine/app/correlators/
├── __init__.py
└── asset_correlator.py
```

**`app/correlators/asset_correlator.py`:**

```python
from app.normalizers.asset_mapper import AssetMappingResult, NormalizedAsset
from app.connectors.glpi_db_connector import get_glpi_db
from app.connectors.sccm_connector import get_sccm_db
import logging

logger = logging.getLogger(__name__)


class AssetCorrelator:
    MATCH_FIELDS = ["hostname", "manufacturer", "model", "os_name", "serial_number"]

    def correlate_by_hostname(self, glpi_assets: list[NormalizedAsset]) -> list[AssetMappingResult]:
        sccm = get_sccm_db()
        results = []

        all_sccm_systems = sccm.get_all_systems()
        sccm_by_hostname = {s["hostname"].lower(): s for s in all_sccm_systems}

        for glpi_asset in glpi_assets:
            hostname_lower = glpi_asset.hostname.lower()
            sccm_raw = sccm_by_hostname.get(hostname_lower)

            if sccm_raw:
                sccm_hardware = sccm.get_computer_hardware(sccm_raw["ResourceID"])
                from app.normalizers.sccm_normalizer import normalize_sccm_system
                sccm_asset = normalize_sccm_system(sccm_raw, sccm_hardware)

                mismatches = self._find_mismatches(glpi_asset, sccm_asset)
                status = "matched" if not mismatches else "mismatch"

                results.append(AssetMappingResult(
                    glpi_asset=glpi_asset,
                    sccm_asset=sccm_asset,
                    match_status=status,
                    mismatches=mismatches,
                    match_method="hostname",
                    match_confidence=0.9 if status == "matched" else 0.7,
                ))
            else:
                results.append(AssetMappingResult(
                    glpi_asset=glpi_asset,
                    match_status="missing_in_sccm",
                    match_method="hostname",
                    match_confidence=0.8,
                ))

        sccm_hostnames = {s["hostname"].lower() for s in all_sccm_systems}
        glpi_hostnames = {a.hostname.lower() for a in glpi_assets}
        missing_in_glpi = sccm_hostnames - glpi_hostnames

        for hostname in missing_in_glpi:
            sccm_raw = sccm_by_hostname[hostname]
            sccm_hardware = sccm.get_computer_hardware(sccm_raw["ResourceID"])
            from app.normalizers.sccm_normalizer import normalize_sccm_system
            sccm_asset = normalize_sccm_system(sccm_raw, sccm_hardware)

            results.append(AssetMappingResult(
                sccm_asset=sccm_asset,
                match_status="missing_in_glpi",
                match_method="hostname",
                match_confidence=0.8,
            ))

        return results

    def _find_mismatches(self, glpi: NormalizedAsset, sccm: NormalizedAsset) -> list[dict]:
        mismatches = []
        for field in self.MATCH_FIELDS:
            glpi_val = getattr(glpi, field, "").lower().strip()
            sccm_val = getattr(sccm, field, "").lower().strip()
            if glpi_val and sccm_val and glpi_val != sccm_val:
                mismatches.append({
                    "field": field,
                    "glpi": getattr(glpi, field),
                    "sccm": getattr(sccm, field),
                })
        return mismatches
```

#### 4.2.4 SCCM Tools untuk CrewAI

**File Baru:**

```
ai-engine/app/tools/
└── sccm_tools.py
```

**`app/tools/sccm_tools.py`:**

```python
from crewai.tools import tool
from app.connectors.sccm_connector import get_sccm_db


@tool("get_sccm_computer_detail")
def get_sccm_computer_detail(hostname: str) -> str:
    """Get detailed hardware and OS information from SCCM for a specific computer by hostname."""
    sccm = get_sccm_db()
    system = sccm.find_by_hostname(hostname)
    if not system:
        return f"Computer '{hostname}' not found in SCCM."
    hardware = sccm.get_computer_hardware(system["ResourceID"])
    if not hardware:
        return f"Hardware data not available for '{hostname}' in SCCM."
    parts = [f"SCCM Data for {hostname}:"]
    for k, v in hardware.items():
        if v is not None:
            parts.append(f"  {k}: {v}")
    return "\n".join(parts)


@tool("get_sccm_software_inventory")
def get_sccm_software_inventory(hostname: str) -> str:
    """Get software inventory from SCCM for a specific computer by hostname."""
    sccm = get_sccm_db()
    system = sccm.find_by_hostname(hostname)
    if not system:
        return f"Computer '{hostname}' not found in SCCM."
    software = sccm.get_software_inventory(system["ResourceID"])
    if not software:
        return f"No software inventory found for '{hostname}' in SCCM."
    parts = [f"Software on {hostname} ({len(software)} items):"]
    for sw in software[:50]:
        name = sw.get("software_name", "Unknown")
        ver = sw.get("version", "")
        pub = sw.get("publisher", "")
        parts.append(f"  - {name} {ver} ({pub})")
    if len(software) > 50:
        parts.append(f"  ... and {len(software) - 50} more")
    return "\n".join(parts)


@tool("get_sccm_patch_status")
def get_sccm_patch_status(hostname: str) -> str:
    """Get patch compliance status from SCCM for a specific computer by hostname."""
    sccm = get_sccm_db()
    system = sccm.find_by_hostname(hostname)
    if not system:
        return f"Computer '{hostname}' not found in SCCM."
    compliance = sccm.get_patch_compliance(system["ResourceID"])
    return (
        f"Patch Status for {hostname}:\n"
        f"  Total Updates: {compliance['total_updates']}\n"
        f"  Installed: {compliance['installed']}\n"
        f"  Missing: {compliance['missing']}\n"
        f"  Unknown: {compliance['unknown']}\n"
        f"  Compliance: {compliance['compliance_pct']}%"
    )


@tool("compare_glpi_sccm")
def compare_glpi_sccm(hostname: str) -> str:
    """Compare data between GLPI and SCCM for a specific computer. Shows discrepancies."""
    from app.correlators.asset_correlator import AssetCorrelator
    from app.normalizers.glpi_normalizer import normalize_glpi_computer
    from app.connectors.glpi_db_connector import get_glpi_db

    glpi_db = get_glpi_db()
    sccm = get_sccm_db()

    glpi_rows = glpi_db.execute_query(
        "SELECT c.id, c.name, c.serial FROM glpi_computers c WHERE c.name = :hostname AND c.is_deleted = 0",
        {"hostname": hostname},
    )
    if not glpi_rows:
        return f"Computer '{hostname}' not found in GLPI database."

    glpi_asset = normalize_glpi_computer(glpi_rows[0])
    correlator = AssetCorrelator()
    results = correlator.correlate_by_hostname([glpi_asset])

    if not results:
        return f"No correlation result for '{hostname}'."

    result = results[0]
    if result.match_status == "missing_in_sccm":
        return f"Computer '{hostname}' exists in GLPI but NOT found in SCCM."
    if result.match_status == "matched":
        return f"Computer '{hostname}' data is consistent between GLPI and SCCM."
    if result.match_status == "mismatch":
        parts = [f"Data discrepancies for '{hostname}':"]
        for m in result.mismatches:
            parts.append(f"  - {m['field']}: GLPI='{m['glpi']}' vs SCCM='{m['sccm']}'")
        return "\n".join(parts)
    return f"Correlation status: {result.match_status}"
```

---

### SPRINT 5-6: ASSET HEALTH AI — BACKEND

**Tujuan:** Celery + Redis, Health Analysis Crew, Risk Scoring, API endpoints

#### 4.3.1 Celery + Redis Setup

**File Baru:**

```
ai-engine/app/workers/
├── __init__.py
├── celery_app.py
└── health_worker.py
```

**`app/workers/celery_app.py`:**

```python
from celery import Celery
from app.config import Settings
import os

settings = Settings(_env_file=os.getenv("ENV_FILE", ".env"))

celery_app = Celery(
    "glpi_ai_worker",
    broker=f"redis://{settings.redis_host}:{settings.redis_port}/0",
    backend=f"redis://{settings.redis_host}:{settings.redis_port}/1",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jakarta",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

celery_app.autodiscover_tasks(["app.workers"])
```

**`app/workers/health_worker.py`:**

```python
from app.workers.celery_app import celery_app
from app.scorers.health_scorer import HealthScorer
from app.correlators.asset_correlator import AssetCorrelator
from app.normalizers.glpi_normalizer import normalize_glpi_computer
from app.connectors.glpi_db_connector import get_glpi_db
from app.connectors.sccm_connector import get_sccm_db
import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="health.analyze_single")
def analyze_single_asset(self, computer_id: int) -> dict:
    self.update_state(state="PROGRESS", meta={"step": "collecting_data", "computer_id": computer_id})

    glpi_db = get_glpi_db()
    scorer = HealthScorer()

    glpi_data = glpi_db.get_computer_details_for_health(computer_id)
    if not glpi_data:
        return {"status": "error", "message": f"Computer {computer_id} not found"}

    self.update_state(state="PROGRESS", meta={"step": "scoring", "computer_id": computer_id})

    ticket_freq = glpi_db.get_ticket_frequency_by_computer(months=6)
    ticket_count = next((t["ticket_count"] for t in ticket_freq if t["computer_id"] == computer_id), 0)

    warranty_data = glpi_db.get_warranty_status()
    warranty_status = next((w["warranty_status"] for w in warranty_data if w["computer_id"] == computer_id), "no_warranty")

    sccm_compliance = None
    sccm_correlation = "not_checked"
    try:
        sccm = get_sccm_db()
        sccm_system = sccm.find_by_hostname(glpi_data.get("name", ""))
        if sccm_system:
            sccm_compliance = sccm.get_patch_compliance(sccm_system["ResourceID"])
            sccm_correlation = "matched"
        else:
            sccm_correlation = "missing_in_sccm"
    except Exception:
        sccm_correlation = "sccm_unavailable"

    health_result = scorer.calculate_score(
        computer_data=glpi_data,
        ticket_count=ticket_count,
        warranty_status=warranty_status,
        sccm_compliance=sccm_compliance,
        sccm_correlation=sccm_correlation,
    )

    self.update_state(state="PROGRESS", meta={"step": "generating_recommendations", "computer_id": computer_id})

    return {
        "status": "completed",
        "computer_id": computer_id,
        "computer_name": glpi_data.get("name"),
        "health_score": health_result["score"],
        "risk_category": health_result["risk_category"],
        "factors": health_result["factors"],
        "recommendations": health_result["recommendations"],
        "sccm_correlation": sccm_correlation,
    }


@celery_app.task(bind=True, name="health.analyze_all")
def analyze_all_assets(self) -> dict:
    glpi_db = get_glpi_db()
    computers = glpi_db.execute_query(
        "SELECT id, name FROM glpi_computers WHERE is_deleted = 0 AND is_template = 0"
    )

    total = len(computers)
    results = []

    for i, comp in enumerate(computers):
        self.update_state(state="PROGRESS", meta={
            "step": "analyzing",
            "current": i + 1,
            "total": total,
            "current_computer": comp["name"],
        })
        try:
            result = analyze_single_asset(comp["id"])
            results.append(result)
        except Exception as e:
            logger.error(f"Error analyzing computer {comp['id']}: {e}")
            results.append({"computer_id": comp["id"], "status": "error", "message": str(e)})

    return {
        "status": "completed",
        "total_analyzed": len(results),
        "results": results,
    }


@celery_app.task(name="health.correlate_glpi_sccm")
def correlate_glpi_sccm() -> dict:
    glpi_db = get_glpi_db()
    computers = glpi_db.execute_query(
        "SELECT c.id, c.name, c.serial FROM glpi_computers c WHERE c.is_deleted = 0 AND c.is_template = 0"
    )

    glpi_assets = [normalize_glpi_computer(row) for row in computers]
    correlator = AssetCorrelator()
    results = correlator.correlate_by_hostname(glpi_assets)

    summary = {
        "matched": sum(1 for r in results if r.match_status == "matched"),
        "mismatch": sum(1 for r in results if r.match_status == "mismatch"),
        "missing_in_sccm": sum(1 for r in results if r.match_status == "missing_in_sccm"),
        "missing_in_glpi": sum(1 for r in results if r.match_status == "missing_in_glpi"),
    }

    return {
        "status": "completed",
        "total_assets": len(results),
        "summary": summary,
        "details": [r.model_dump() for r in results],
    }
```

**Modifikasi `app/config.py`** — Tambah Redis settings:

```python
redis_host: str = "localhost"
redis_port: int = 6379
```

#### 4.3.2 Health Scoring Algorithm

**File Baru:**

```
ai-engine/app/scorers/
├── __init__.py
├── health_scorer.py
└── risk_category.py
```

**`app/scorers/risk_category.py`:**

```python
from enum import Enum


class RiskCategory(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


def score_to_category(score: int) -> RiskCategory:
    if score <= 30:
        return RiskCategory.CRITICAL
    elif score <= 50:
        return RiskCategory.HIGH
    elif score <= 70:
        return RiskCategory.MEDIUM
    else:
        return RiskCategory.LOW
```

**`app/scorers/health_scorer.py`:**

```python
from app.scorers.risk_category import score_to_category
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class HealthScorer:
    WEIGHTS = {
        "hardware_age": 0.20,
        "ticket_frequency": 0.25,
        "patch_compliance": 0.25,
        "warranty_status": 0.15,
        "sccm_correlation": 0.15,
    }

    def calculate_score(
        self,
        computer_data: dict,
        ticket_count: int = 0,
        warranty_status: str = "no_warranty",
        sccm_compliance: dict | None = None,
        sccm_correlation: str = "not_checked",
    ) -> dict:
        factors = {}
        penalties = {}

        age_penalty = self._hardware_age_penalty(computer_data)
        factors["hardware_age"] = {"penalty": age_penalty, "weight": self.WEIGHTS["hardware_age"]}
        penalties["hardware_age"] = age_penalty * self.WEIGHTS["hardware_age"]

        ticket_penalty = self._ticket_frequency_penalty(ticket_count)
        factors["ticket_frequency"] = {"penalty": ticket_penalty, "weight": self.WEIGHTS["ticket_frequency"], "ticket_count": ticket_count}
        penalties["ticket_frequency"] = ticket_penalty * self.WEIGHTS["ticket_frequency"]

        patch_penalty = self._patch_compliance_penalty(sccm_compliance)
        factors["patch_compliance"] = {"penalty": patch_penalty, "weight": self.WEIGHTS["patch_compliance"], "compliance": sccm_compliance}
        penalties["patch_compliance"] = patch_penalty * self.WEIGHTS["patch_compliance"]

        warranty_penalty = self._warranty_penalty(warranty_status)
        factors["warranty_status"] = {"penalty": warranty_penalty, "weight": self.WEIGHTS["warranty_status"], "status": warranty_status}
        penalties["warranty_status"] = warranty_penalty * self.WEIGHTS["warranty_status"]

        correlation_penalty = self._sccm_correlation_penalty(sccm_correlation)
        factors["sccm_correlation"] = {"penalty": correlation_penalty, "weight": self.WEIGHTS["sccm_correlation"], "status": sccm_correlation}
        penalties["sccm_correlation"] = correlation_penalty * self.WEIGHTS["sccm_correlation"]

        total_penalty = sum(penalties.values())
        score = max(0, min(100, int(100 - total_penalty)))
        risk_category = score_to_category(score)
        recommendations = self._generate_recommendations(factors, score, risk_category)

        return {
            "score": score,
            "risk_category": risk_category.value,
            "factors": factors,
            "penalties": penalties,
            "recommendations": recommendations,
        }

    def _hardware_age_penalty(self, data: dict) -> int:
        creation_date = data.get("date_creation")
        if not creation_date:
            return 15
        if isinstance(creation_date, str):
            creation_date = datetime.fromisoformat(creation_date.replace(" ", "T"))
        age_years = (datetime.now() - creation_date).days / 365.25
        if age_years < 2:
            return 0
        elif age_years < 4:
            return 10
        elif age_years < 6:
            return 20
        else:
            return 30

    def _ticket_frequency_penalty(self, count: int) -> int:
        if count == 0:
            return 0
        elif count <= 3:
            return 10
        elif count <= 7:
            return 20
        else:
            return 30

    def _patch_compliance_penalty(self, compliance: dict | None) -> int:
        if not compliance:
            return 15
        pct = compliance.get("compliance_pct", 0)
        if pct > 95:
            return 0
        elif pct > 80:
            return 10
        elif pct > 60:
            return 20
        else:
            return 30

    def _warranty_penalty(self, status: str) -> int:
        if status == "active":
            return 0
        elif status == "expiring_soon":
            return 10
        elif status == "expired":
            return 20
        else:
            return 15

    def _sccm_correlation_penalty(self, status: str) -> int:
        if status == "matched":
            return 0
        elif status == "mismatch":
            return 10
        elif status == "missing_in_sccm":
            return 15
        elif status == "missing_in_glpi":
            return 15
        else:
            return 10

    def _generate_recommendations(self, factors: dict, score: int, risk_category) -> list[str]:
        recs = []
        if factors["hardware_age"]["penalty"] >= 20:
            recs.append("Pertimbangkan penggantian hardware — aset sudah berusia > 4 tahun")
        if factors["ticket_frequency"].get("ticket_count", 0) > 7:
            recs.append("Investigasi tingginya frekuensi tiket — kemungkinan ada masalah recurring")
        if factors["patch_compliance"].get("compliance", {}).get("compliance_pct", 100) < 80:
            recs.append("Patch compliance rendah — perlu update keamanan segera")
        if factors["warranty_status"]["status"] in ("expired", "no_warranty"):
            recs.append("Garansi tidak aktif — pertimbangkan perpanjangan atau penggantian")
        if factors["sccm_correlation"]["status"] == "missing_in_sccm":
            recs.append("Aset tidak terdaftar di SCCM — perlu verifikasi dan pendaftaran ulang")
        if factors["sccm_correlation"]["status"] == "mismatch":
            recs.append("Data GLPI dan SCCM tidak konsisten — perlu rekonsiliasi data")
        if score > 70 and not recs:
            recs.append("Aset dalam kondisi baik — tidak ada tindakan diperlukan saat ini")
        if not recs:
            recs.append("Lakukan penilaian lebih detail untuk aset ini")
        return recs
```

#### 4.3.3 Health Analysis Crew (Multi-Agent)

**File Baru:**

```
ai-engine/app/crews/
├── __init__.py
└── health_crew.py

ai-engine/app/agents/
├── data_collector_agent.py
├── pattern_analyzer_agent.py
├── risk_assessor_agent.py
└── recommendation_agent.py

ai-engine/app/tasks/
├── __init__.py
├── collect_data_task.py
├── analyze_patterns_task.py
├── assess_risk_task.py
└── generate_recommendations_task.py
```

**`app/agents/data_collector_agent.py`:**

```python
from crewai import Agent
from app.tools.sccm_tools import get_sccm_computer_detail, get_sccm_patch_status, get_sccm_software_inventory
from app.tools.computer_tools import get_computer_detail, get_computers_by_status


def create_data_collector_agent(llm) -> Agent:
    return Agent(
        role="Data Collector Specialist",
        goal="Mengumpulkan semua data relevan dari GLPI dan SCCM untuk analisis kesehatan aset",
        backstory=(
            "Anda adalah spesialis pengumpulan data IT. Tugas Anda adalah mengambil data "
            "dari GLPI dan SCCM secara akurat dan lengkap. Anda harus memastikan semua data "
            "yang diperlukan untuk analisis kesehatan tersedia. Gunakan tools yang tersedia "
            "untuk mengambil data dari kedua sistem. Jangan membuat data — hanya ambil dari tools."
        ),
        llm=llm,
        tools=[get_computer_detail, get_computers_by_status, get_sccm_computer_detail,
               get_sccm_software_inventory, get_sccm_patch_status],
        verbose=False,
        allow_delegation=False,
        max_iter=5,
    )
```

**`app/agents/pattern_analyzer_agent.py`:**

```python
from crewai import Agent


def create_pattern_analyzer_agent(llm) -> Agent:
    return Agent(
        role="Pattern Analyzer",
        goal="Menganalisis pola masalah dan anomali dari data aset IT",
        backstory=(
            "Anda adalah analis pola data IT. Anda menganalisis data dari GLPI dan SCCM "
            "untuk menemukan pola masalah, anomali, dan tren. Fokus pada: frekuensi tiket "
            "berulang, ketidakcocokan data antara GLPI dan SCCM, aset yang sering bermasalah, "
            "dan patch compliance yang rendah. Berikan analisis yang terstruktur dan faktual."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
    )
```

**`app/agents/risk_assessor_agent.py`:**

```python
from crewai import Agent


def create_risk_assessor_agent(llm) -> Agent:
    return Agent(
        role="Risk Assessor",
        goal="Menghitung skor risiko dan mengkategorikan tingkat risiko aset IT",
        backstory=(
            "Anda adalah penilai risiko IT. Berdasarkan data dan analisis pola yang diberikan, "
            "Anda menghitung skor risiko (0-100) dan mengkategorikan aset ke dalam: Critical (0-30), "
            "High (31-50), Medium (51-70), Low (71-100). Pertimbangkan faktor: usia hardware, "
            "frekuensi tiket, patch compliance, status garansi, dan korelasi GLPI-SCCM."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
    )
```

**`app/agents/recommendation_agent.py`:**

```python
from crewai import Agent


def create_recommendation_agent(llm) -> Agent:
    return Agent(
        role="Recommendation Specialist",
        goal="Menghasilkan rekomendasi tindakan berdasarkan analisis risiko aset IT",
        backstory=(
            "Anda adalah spesialis rekomendasi IT. Berdasarkan skor risiko dan analisis yang "
            "diberikan, Anda membuat rekomendasi tindakan yang konkret dan actionable. Prioritaskan "
            "rekomendasi berdasarkan urgensi. Gunakan bahasa Indonesia yang jelas dan profesional. "
            "Format rekomendasi dengan prioritas: [URGENT], [HIGH], [MEDIUM], [LOW]."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
    )
```

**`app/crews/health_crew.py`:**

```python
from crewai import Crew, Process
from app.agents.data_collector_agent import create_data_collector_agent
from app.agents.pattern_analyzer_agent import create_pattern_analyzer_agent
from app.agents.risk_assessor_agent import create_risk_assessor_agent
from app.agents.recommendation_agent import create_recommendation_agent
from app.agents.agent_factory import get_llm


def create_health_crew() -> Crew:
    llm = get_llm()

    data_collector = create_data_collector_agent(llm)
    pattern_analyzer = create_pattern_analyzer_agent(llm)
    risk_assessor = create_risk_assessor_agent(llm)
    recommendation = create_recommendation_agent(llm)

    return Crew(
        agents=[data_collector, pattern_analyzer, risk_assessor, recommendation],
        process=Process.sequential,
        verbose=False,
    )
```

#### 4.3.4 Health API Endpoints (Implementasi Penuh)

**`app/api/routes/health.py`** — Full Implementation:

```python
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from celery.result import AsyncResult
from app.workers.health_worker import analyze_single_asset, analyze_all_assets, correlate_glpi_sccm
from app.config import Settings

router = APIRouter()
settings = Settings()


def verify_api_key(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    token = authorization[7:]
    if token != settings.gateway_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class AnalyzeRequest(BaseModel):
    computer_id: int | None = None
    analyze_all: bool = False


@router.post("/analyze")
async def trigger_analysis(
    request: AnalyzeRequest,
    authorization: str | None = Header(None),
):
    verify_api_key(authorization)
    if request.analyze_all:
        task = analyze_all_assets.delay()
    elif request.computer_id:
        task = analyze_single_asset.delay(request.computer_id)
    else:
        raise HTTPException(status_code=400, detail="Specify computer_id or analyze_all=true")
    return {"job_id": task.id, "status": "started"}


@router.get("/status/{job_id}")
async def get_analysis_status(job_id: str):
    result = AsyncResult(job_id)
    response = {"job_id": job_id, "status": result.status}
    if result.status == "PROGRESS":
        response["progress"] = result.info
    elif result.status == "SUCCESS":
        response["result"] = result.result
    elif result.status == "FAILURE":
        response["error"] = str(result.result)
    return response


@router.get("/report/{asset_id}")
async def get_health_report(asset_id: int):
    from app.connectors.glpi_db_connector import get_glpi_db
    from app.scorers.health_scorer import HealthScorer

    glpi_db = get_glpi_db()
    computer = glpi_db.get_computer_details_for_health(asset_id)
    if not computer:
        raise HTTPException(status_code=404, detail="Computer not found")

    ticket_freq = glpi_db.get_ticket_frequency_by_computer(months=6)
    ticket_count = next((t["ticket_count"] for t in ticket_freq if t["computer_id"] == asset_id), 0)

    warranty_data = glpi_db.get_warranty_status()
    warranty_status = next(
        (w["warranty_status"] for w in warranty_data if w["computer_id"] == asset_id),
        "no_warranty",
    )

    scorer = HealthScorer()
    health_result = scorer.calculate_score(
        computer_data=computer,
        ticket_count=ticket_count,
        warranty_status=warranty_status,
    )

    return {
        "computer_id": asset_id,
        "computer_name": computer.get("name"),
        "health_score": health_result["score"],
        "risk_category": health_result["risk_category"],
        "factors": health_result["factors"],
        "recommendations": health_result["recommendations"],
    }


@router.get("/dashboard")
async def get_dashboard():
    from app.connectors.glpi_db_connector import get_glpi_db
    from app.scorers.risk_category import RiskCategory

    glpi_db = get_glpi_db()

    status_dist = glpi_db.get_computer_count_by_status()
    age_dist = glpi_db.get_computer_age_distribution()
    warranty_data = glpi_db.get_warranty_status()

    warranty_summary = {"active": 0, "expiring_soon": 0, "expired": 0, "no_warranty": 0}
    for w in warranty_data:
        status = w.get("warranty_status", "no_warranty")
        if status in warranty_summary:
            warranty_summary[status] += 1

    total_computers = sum(s["count"] for s in status_dist)

    return {
        "total_computers": total_computers,
        "status_distribution": status_dist,
        "age_distribution": age_dist,
        "warranty_summary": warranty_summary,
    }


@router.post("/correlate")
async def trigger_correlation(authorization: str | None = Header(None)):
    verify_api_key(authorization)
    task = correlate_glpi_sccm.delay()
    return {"job_id": task.id, "status": "started"}
```

---

### SPRINT 7-8: ASSET HEALTH AI — GLPI PLUGIN UI

**Tujuan:** Dashboard UI, health tab di Computer detail, scheduled jobs, notifications

#### 4.4.1 Database Schema Tambahan (Plugin)

```sql
-- Ditambahkan di hook.php
CREATE TABLE IF NOT EXISTS glpi_plugin_chatbot_health_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    asset_id INT NOT NULL,
    asset_type VARCHAR(50) DEFAULT 'Computer',
    health_score INT,
    risk_category VARCHAR(20),
    report_data JSON,
    sccm_correlation_status VARCHAR(50),
    recommendations JSON,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_asset_id (asset_id),
    INDEX idx_health_score (health_score),
    INDEX idx_risk_category (risk_category)
);

CREATE TABLE IF NOT EXISTS glpi_plugin_chatbot_audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    users_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    session_id VARCHAR(100),
    query_summary TEXT,
    ip_address VARCHAR(45),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_id (users_id),
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
);
```

#### 4.4.2 Dashboard UI (Twig)

**File Baru:**

```
glpi-plugin/
├── views/
│   ├── dashboard.twig
│   └── health_tab.twig
├── front/
│   └── dashboard.php
├── js/
│   └── dashboard.js
└── css/
    └── dashboard.css
```

**`views/dashboard.twig`** — Dashboard Template:

```twig
{# Asset Health Dashboard #}
<div id="health-dashboard" class="ai-dashboard">
    <div class="dashboard-header">
        <h2><i class="fas fa-heartbeat"></i> Asset Health Dashboard</h2>
        <button id="btn-analyze-all" class="btn btn-primary">
            <i class="fas fa-play"></i> Run Full Analysis
        </button>
    </div>

    <div class="dashboard-cards">
        <div class="card card-total">
            <div class="card-value" id="total-computers">-</div>
            <div class="card-label">Total Assets</div>
        </div>
        <div class="card card-critical">
            <div class="card-value" id="critical-count">-</div>
            <div class="card-label">Critical</div>
        </div>
        <div class="card card-high">
            <div class="card-value" id="high-count">-</div>
            <div class="card-label">High Risk</div>
        </div>
        <div class="card card-medium">
            <div class="card-value" id="medium-count">-</div>
            <div class="card-label">Medium Risk</div>
        </div>
        <div class="card card-low">
            <div class="card-value" id="low-count">-</div>
            <div class="card-label">Low Risk</div>
        </div>
    </div>

    <div class="dashboard-sections">
        <div class="section section-chart">
            <h3>Risk Distribution</h3>
            <canvas id="risk-chart"></canvas>
        </div>

        <div class="section section-correlation">
            <h3>GLPI ↔ SCCM Correlation</h3>
            <div id="correlation-summary">
                <button id="btn-correlate" class="btn btn-secondary">
                    <i class="fas fa-link"></i> Run Correlation
                </button>
            </div>
        </div>
    </div>

    <div class="dashboard-table">
        <h3>Top At-Risk Assets</h3>
        <table class="tab_cadre_fixehov">
            <thead>
                <tr>
                    <th>Asset Name</th>
                    <th>Health Score</th>
                    <th>Risk Category</th>
                    <th>Warranty</th>
                    <th>SCCM Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="risk-table-body">
                <tr><td colspan="6" class="center">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>
```

#### 4.4.3 Health Tab di Computer Detail

**Modifikasi `hook.php`:**

```php
// Tambah di plugin_init_chatbot():
$PLUGIN_HOOKS['item_purge']['chatbot'] = ['Computer' => 'plugin_chatbot_item_purge'];

// Tambah tab via display hook
function plugin_chatbot_display_hook($item) {
    if ($item instanceof Computer) {
        echo '<div id="health-tab-content" data-asset-id="' . $item->getID() . '"></div>';
    }
}
```

**`views/health_tab.twig`:**

```twig
<div class="health-tab" data-asset-id="{{ asset_id }}">
    <div class="health-score-ring">
        <svg viewBox="0 0 100 100">
            <circle class="ring-bg" cx="50" cy="50" r="45"/>
            <circle class="ring-fg" cx="50" cy="50" r="45"
                    stroke-dasharray="{{ score * 2.83 }} 283"
                    data-score="{{ score }}"/>
        </svg>
        <div class="score-text">{{ score }}</div>
    </div>
    <div class="health-factors">
        {% for factor_name, factor in factors %}
        <div class="factor-row">
            <span class="factor-name">{{ factor_name }}</span>
            <span class="factor-penalty">-{{ factor.penalty }}</span>
        </div>
        {% endfor %}
    </div>
    <div class="health-recommendations">
        <h4>Recommendations</h4>
        <ul>
            {% for rec in recommendations %}
            <li>{{ rec }}</li>
            {% endfor %}
        </ul>
    </div>
</div>
```

---

### SPRINT 9-10: CHAT ENHANCEMENT — PLUGIN REFACTOR

**Tujuan:** Refactor UI ke Twig, access control, audit logging, context management

#### 4.5.1 Refactor UI ke Twig

**File Modifikasi/Baru:**

```
glpi-plugin/
├── views/
│   ├── chat.twig              # Extract dari front/chat.php inline HTML
│   ├── config.twig            # Sudah dibuat di Sprint 1-2
│   └── dashboard.twig         # Sudah dibuat di Sprint 7-8
├── front/
│   ├── chat.php               # Slim down: hanya render Twig template
│   └── config.php             # Slim down: hanya render Twig template
├── inc/
│   ├── chat.class.php         # EXISTING
│   ├── config.class.php       # Sudah dibuat di Sprint 1-2
│   └── config.php             # DEPRECATED
└── ajax/
    ├── chat.php               # Update: baca config dari DB, kirim user context
    └── sessions.php           # EXISTING
```

**`front/chat.php`** — Refactored (Slim):

```php
<?php
include('../../../inc/includes.php');
Session::checkLoginUser();

$twig = Twig::load(GLPI_ROOT . '/plugins/chatbot/views', false);

$config = PluginChatbotConfig::getAllConfig();
$userName = Session::getLoginUserName();
$csrfToken = Session::getNewCSRFToken();
$ajaxUrl = Plugin::getWebDir('chatbot') . '/ajax';

echo $twig->render('chat.twig', [
    'config'        => $config,
    'user_name'     => $userName,
    'csrf_token'    => $csrfToken,
    'ajax_url'      => $ajaxUrl,
    'glpi_user_id'  => Session::getLoginUserID(),
]);
```

#### 4.5.2 Access Control Enhancement

**Modifikasi `setup.php`** — Register rights:

```php
// Di plugin_init_chatbot():
$PLUGIN_HOOKS['rights']['chatbot'] = [
    'chatbot:use'        => __('Use Chatbot', 'chatbot'),
    'chatbot:config'     => __('Configure Chatbot', 'chatbot'),
    'chatbot:dashboard'  => __('View Health Dashboard', 'chatbot'),
];
```

**Modifikasi `inc/chat.class.php`:**

```php
public static function canView(): bool {
    return Session::haveRight('chatbot:use', READ);
}

public static function canCreate(): bool {
    return false;
}
```

#### 4.5.3 Audit Logging

**`inc/audit.class.php`:**

```php
<?php
class PluginChatbotAudit {
    public static function log(string $action, ?string $sessionId = null, ?string $querySummary = null): void {
        global $DB;
        $DB->insert('glpi_plugin_chatbot_audit_log', [
            'users_id'       => Session::getLoginUserID(),
            'action'         => $action,
            'session_id'     => $sessionId,
            'query_summary'  => $querySummary ? substr($querySummary, 0, 500) : null,
            'ip_address'     => $_SERVER['REMOTE_ADDR'] ?? '',
            'created_at'     => date('Y-m-d H:i:s'),
        ]);
    }
}
```

**Modifikasi `ajax/chat.php`** — Tambah audit log:

```php
// Setelah menyimpan user message:
PluginChatbotAudit::log('chat_query', $sessionId, $userMessage);
```

#### 4.5.4 Context Management Enhancement

**Modifikasi `ajax/chat.php`** — Enable user context:

```php
// Ganti bagian yang di-comment out dengan versi aktif:
function plugin_chatbot_get_user_context($usersId) {
    global $DB;

    $context = [];

    // User name
    $user = $DB->request(['FROM' => 'glpi_users', 'WHERE' => ['id' => $usersId]])->current();
    if ($user) {
        $context['user_name'] = $user['name'] ?? $user['realname'] ?? 'User';
    }

    // User's computers
    $computers = $DB->request([
        'SELECT' => ['id', 'name', 'serial'],
        'FROM'   => 'glpi_computers',
        'WHERE'  => ['users_id' => $usersId, 'is_deleted' => 0],
        'LIMIT'  => 10,
    ]);
    $compList = [];
    foreach ($computers as $c) {
        $compList[] = $c['name'] . ' (S/N: ' . $c['serial'] . ')';
    }
    if ($compList) {
        $context['computers'] = implode(', ', $compList);
    }

    // Active tickets
    $tickets = $DB->request([
        'SELECT' => ['id', 'name', 'status'],
        'FROM'   => 'glpi_tickets',
        'WHERE'  => [
            'users_id_recipient' => $usersId,
            'status' => [CommonITILObject::INCOMING, CommonITILObject::ASSIGNED,
                         CommonITILObject::PLANNED, CommonITILObject::WAITING],
        ],
        'LIMIT'  => 5,
    ]);
    $ticketList = [];
    foreach ($tickets as $t) {
        $ticketList[] = '#' . $t['id'] . ' ' . $t['name'] . ' [' . $t['status'] . ']';
    }
    if ($ticketList) {
        $context['active_tickets'] = implode(', ', $ticketList);
    }

    return $context;
}

// Build context string for system prompt
$contextData = plugin_chatbot_get_user_context($usersId);
$contextStr = "Data pengguna saat ini:\n";
if (!empty($contextData['user_name'])) {
    $contextStr .= "- Nama: {$contextData['user_name']}\n";
}
if (!empty($contextData['computers'])) {
    $contextStr .= "- Komputer: {$contextData['computers']}\n";
}
if (!empty($contextData['active_tickets'])) {
    $contextStr .= "- Tiket aktif: {$contextData['active_tickets']}\n";
}
```

---

### SPRINT 11-12: CHAT ENHANCEMENT — AI ENGINE

**Tujuan:** SCCM-aware chat tools, health-aware chat, multi-turn improvement

#### 4.6.1 SCCM Tools untuk Chat Agent

**Modifikasi `app/tools/__init__.py`** — Register SCCM tools:

```python
# Tambah ke tool list yang sudah ada:
from app.tools.sccm_tools import (
    get_sccm_computer_detail,
    get_sccm_software_inventory,
    get_sccm_patch_status,
    compare_glpi_sccm,
)
```

**Modifikasi `app/agents/agent_factory.py`** — Tambah SCCM tools ke agent:

```python
# Tambah SCCM tools ke agent's tool list
# Agent sekarang punya 24 tools (20 existing + 4 SCCM)
```

#### 4.6.2 Health-Aware Chat Tools

**File Baru:**

```
ai-engine/app/tools/
└── health_tools.py
```

**`app/tools/health_tools.py`:**

```python
from crewai.tools import tool
from app.connectors.glpi_db_connector import get_glpi_db
from app.scorers.health_scorer import HealthScorer


@tool("get_asset_health_score")
def get_asset_health_score(computer_name: str) -> str:
    """Get the health score and risk category for a specific computer by name."""
    glpi_db = get_glpi_db()
    rows = glpi_db.execute_query(
        "SELECT id, name FROM glpi_computers WHERE name = :name AND is_deleted = 0",
        {"name": computer_name},
    )
    if not rows:
        return f"Computer '{computer_name}' not found."

    computer_id = rows[0]["id"]
    computer = glpi_db.get_computer_details_for_health(computer_id)
    if not computer:
        return f"Details not available for '{computer_name}'."

    ticket_freq = glpi_db.get_ticket_frequency_by_computer(months=6)
    ticket_count = next((t["ticket_count"] for t in ticket_freq if t["computer_id"] == computer_id), 0)

    warranty_data = glpi_db.get_warranty_status()
    warranty_status = next(
        (w["warranty_status"] for w in warranty_data if w["computer_id"] == computer_id),
        "no_warranty",
    )

    scorer = HealthScorer()
    result = scorer.calculate_score(
        computer_data=computer,
        ticket_count=ticket_count,
        warranty_status=warranty_status,
    )

    return (
        f"Health Score for {computer_name}: {result['score']}/100 ({result['risk_category']})\n"
        f"Recommendations: {'; '.join(result['recommendations'])}"
    )


@tool("get_at_risk_assets")
def get_at_risk_assets(risk_category: str = "Critical") -> str:
    """Get list of assets with a specific risk category (Critical, High, Medium, Low)."""
    glpi_db = get_glpi_db()
    computers = glpi_db.execute_query(
        "SELECT id, name FROM glpi_computers WHERE is_deleted = 0 AND is_template = 0 LIMIT 100"
    )

    scorer = HealthScorer()
    matching = []

    for comp in computers:
        computer = glpi_db.get_computer_details_for_health(comp["id"])
        if not computer:
            continue

        ticket_freq = glpi_db.get_ticket_frequency_by_computer(months=6)
        ticket_count = next((t["ticket_count"] for t in ticket_freq if t["computer_id"] == comp["id"]), 0)

        warranty_data = glpi_db.get_warranty_status()
        warranty_status = next(
            (w["warranty_status"] for w in warranty_data if w["computer_id"] == comp["id"]),
            "no_warranty",
        )

        result = scorer.calculate_score(
            computer_data=computer,
            ticket_count=ticket_count,
            warranty_status=warranty_status,
        )

        if result["risk_category"] == risk_category:
            matching.append(f"{comp['name']} (Score: {result['score']})")

    if not matching:
        return f"No assets found with risk category '{risk_category}'."
    return f"Assets with {risk_category} risk ({len(matching)}):\n" + "\n".join(f"  - {m}" for m in matching[:20])
```

---

### SPRINT 13-14: TESTING, SECURITY & DEPLOYMENT

**Tujuan:** Testing, security review, performance, documentation, UAT

#### 4.7.1 Testing Structure

```
ai-engine/tests/
├── __init__.py
├── conftest.py                    # Shared fixtures
├── test_sccm_connector.py         # SCCM connector unit tests
├── test_health_scorer.py          # Health scorer unit tests
├── test_asset_correlator.py       # Correlator unit tests
├── test_health_api.py             # API endpoint tests
├── test_sccm_tools.py             # SCCM tools tests
├── test_health_tools.py           # Health tools tests
└── test_integration.py            # End-to-end integration tests
```

**`tests/conftest.py`:**

```python
import pytest
from unittest.mock import MagicMock, AsyncMock
from app.config import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        ai_gateway_url="https://test.example.com/v1/chat/completions",
        ai_gateway_base_url="https://test.example.com/v1",
        ai_gateway_api_key="test-key",
        ai_model="test-model",
        gateway_api_key="test-gateway-key",
        glpi_db_host="localhost",
        glpi_db_name="test_glpi",
        glpi_db_user="test",
        glpi_db_password="test",
        sccm_db_host="localhost",
        sccm_db_name="test_sccm",
        sccm_db_user="test",
        sccm_db_password="test",
        redis_host="localhost",
        redis_port=6379,
    )


@pytest.fixture
def sample_computer_data():
    return {
        "id": 1,
        "name": "TEST-PC-001",
        "date_creation": "2022-01-15 10:00:00",
        "date_mod": "2024-06-01 08:30:00",
        "status_name": "Production",
        "manufacturer_name": "Dell",
        "computer_type": "Laptop",
        "location_name": "Jakarta Office",
        "user_name": "John Doe",
        "os_name": "Windows 11 Pro",
    }
```

**`tests/test_health_scorer.py`:**

```python
from app.scorers.health_scorer import HealthScorer
from app.scorers.risk_category import RiskCategory, score_to_category


class TestRiskCategory:
    def test_critical(self):
        assert score_to_category(25) == RiskCategory.CRITICAL

    def test_high(self):
        assert score_to_category(40) == RiskCategory.HIGH

    def test_medium(self):
        assert score_to_category(60) == RiskCategory.MEDIUM

    def test_low(self):
        assert score_to_category(85) == RiskCategory.LOW


class TestHealthScorer:
    def setup_method(self):
        self.scorer = HealthScorer()

    def test_healthy_asset(self, sample_computer_data):
        result = self.scorer.calculate_score(
            computer_data=sample_computer_data,
            ticket_count=0,
            warranty_status="active",
            sccm_compliance={"compliance_pct": 98, "total_updates": 100, "installed": 98, "missing": 2, "unknown": 0},
            sccm_correlation="matched",
        )
        assert result["score"] >= 70
        assert result["risk_category"] in ("Low", "Medium")

    def test_critical_asset(self, sample_computer_data):
        old_data = {**sample_computer_data, "date_creation": "2015-01-01 00:00:00"}
        result = self.scorer.calculate_score(
            computer_data=old_data,
            ticket_count=10,
            warranty_status="expired",
            sccm_compliance={"compliance_pct": 40, "total_updates": 100, "installed": 40, "missing": 60, "unknown": 0},
            sccm_correlation="missing_in_sccm",
        )
        assert result["score"] <= 50
        assert result["risk_category"] in ("Critical", "High")

    def test_no_sccm_data(self, sample_computer_data):
        result = self.scorer.calculate_score(
            computer_data=sample_computer_data,
            ticket_count=1,
            warranty_status="active",
        )
        assert 0 <= result["score"] <= 100
        assert len(result["recommendations"]) > 0

    def test_recommendations_generated(self, sample_computer_data):
        old_data = {**sample_computer_data, "date_creation": "2016-01-01 00:00:00"}
        result = self.scorer.calculate_score(
            computer_data=old_data,
            ticket_count=8,
            warranty_status="expired",
            sccm_correlation="missing_in_sccm",
        )
        assert len(result["recommendations"]) >= 2
```

#### 4.7.2 Security Checklist

| Item | Status | Detail |
|------|--------|--------|
| SQL Injection Prevention | ✅ | SQLAlchemy parameterized queries |
| API Key Rotation | 🔲 | Perlu mechanism untuk rotate GATEWAY_API_KEY |
| Rate Limiting | 🔲 | Perlu `slowapi` atau middleware |
| Input Sanitization | 🔲 | Perlu validasi input di API endpoints |
| SCCM Read-Only Guarantee | 🔲 | Verifikasi DB user hanya punya SELECT |
| CORS Configuration | ✅ | Sudah ada, perlu review origins |
| CSRF Protection | ✅ | Plugin sudah implement |
| IDOR Protection | ✅ | Session ownership validation |
| Audit Trail | 🔲 | Implementasi di Sprint 9-10 |
| Secrets Management | 🔲 | .env file, perlu vault untuk production |

---

## 5. Struktur Proyek Final (Delta dari Existing)

### 5.1 AI Engine (`/home/ariel/projects/chatbot-fastapi/`)

```
chatbot-fastapi/
├── .env                              # EXTEND: add SCCM, DB, Redis config
├── .env.example                      # EXTEND: add new env vars
├── pyproject.toml                    # EXTEND: add new dependencies
├── docker/                           # NEW
│   ├── Dockerfile                    # FastAPI app container
│   ├── Dockerfile.worker             # Celery worker container
│   ├── docker-compose.yml            # Full stack (app + worker + beat + redis)
│   └── .dockerignore
├── tests/                            # NEW
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_health_scorer.py
│   ├── test_asset_correlator.py
│   ├── test_health_api.py
│   ├── test_sccm_connector.py
│   ├── test_sccm_tools.py
│   ├── test_health_tools.py
│   └── test_integration.py
└── app/
    ├── main.py                       # REFACTOR: slim down, use routers
    ├── config.py                     # EXTEND: add SCCM, DB, Redis settings
    ├── cache.py                      # EXISTING (keep)
    ├── utils.py                      # EXISTING (keep)
    ├── api/                          # NEW
    │   ├── __init__.py
    │   ├── main.py                   # NEW: router aggregation entry point
    │   └── routes/
    │       ├── __init__.py
    │       ├── chat.py               # NEW: extract from main.py
    │       └── health.py             # NEW: health analysis endpoints
    ├── connectors/                   # NEW
    │   ├── __init__.py
    │   ├── glpi_db_connector.py      # NEW: direct DB read-only
    │   └── sccm_connector.py         # NEW: SQL Server read-only
    ├── normalizers/                  # NEW
    │   ├── __init__.py
    │   ├── glpi_normalizer.py
    │   ├── sccm_normalizer.py
    │   └── asset_mapper.py
    ├── correlators/                  # NEW
    │   ├── __init__.py
    │   └── asset_correlator.py
    ├── scorers/                      # NEW
    │   ├── __init__.py
    │   ├── health_scorer.py
    │   └── risk_category.py
    ├── crews/                        # NEW
    │   ├── __init__.py
    │   └── health_crew.py
    ├── agents/                       # EXTEND
    │   ├── __init__.py               # EXISTING
    │   ├── agent_factory.py          # EXTEND: add health agents
    │   ├── prompt_builder.py         # EXISTING (keep)
    │   ├── data_collector_agent.py   # NEW
    │   ├── pattern_analyzer_agent.py # NEW
    │   ├── risk_assessor_agent.py    # NEW
    │   └── recommendation_agent.py   # NEW
    ├── tasks/                        # NEW
    │   ├── __init__.py
    │   ├── collect_data_task.py
    │   ├── analyze_patterns_task.py
    │   ├── assess_risk_task.py
    │   └── generate_recommendations_task.py
    ├── tools/                        # EXTEND
    │   ├── __init__.py               # EXTEND: register SCCM + health tools
    │   ├── computer_tools.py         # EXISTING (keep)
    │   ├── contract_tools.py         # EXISTING (keep)
    │   ├── formatters.py             # EXISTING (keep)
    │   ├── supplier_tools.py         # EXISTING (keep)
    │   ├── ticket_tools.py           # EXISTING (keep)
    │   ├── sccm_tools.py             # NEW: 4 SCCM tools
    │   └── health_tools.py           # NEW: 2 health tools
    ├── workers/                      # NEW
    │   ├── __init__.py
    │   ├── celery_app.py
    │   └── health_worker.py
    ├── models/                       # NEW
    │   ├── __init__.py
    │   ├── health.py                 # Pydantic models for health API
    │   └── sccm.py                   # Pydantic models for SCCM data
    ├── repository/                   # EXISTING (keep)
    ├── infrastructure/               # EXISTING (keep)
    └── services/                     # EXISTING (keep, extend if needed)
```

### 5.2 GLPI Plugin (`/var/www/glpi/plugins/chatbot/`)

```
chatbot/
├── setup.php                         # EXTEND: add config table, rights
├── hook.php                          # EXTEND: add config/audit/health tables, health tab hook
├── inc/
│   ├── chat.class.php                # EXTEND: add canView with rights
│   ├── config.php                    # DEPRECATED (keep for backward compat)
│   ├── config.class.php              # NEW: DB-driven config
│   └── audit.class.php               # NEW: audit logging
├── ajax/
│   ├── chat.php                      # EXTEND: read config from DB, enable context, add audit
│   ├── chat.php.bak                  # EXISTING (keep)
│   ├── sessions.php                  # EXISTING (keep)
│   └── config.php                    # NEW: config AJAX handler
├── front/
│   ├── chat.php                      # REFACTOR: slim down, render Twig
│   ├── chat_backup.php               # EXISTING (keep)
│   ├── config.php                    # NEW: config page entry
│   └── dashboard.php                 # NEW: dashboard page entry
├── views/                            # NEW DIRECTORY
│   ├── chat.twig                     # NEW: extract from front/chat.php
│   ├── config.twig                   # NEW: config form
│   ├── dashboard.twig                # NEW: health dashboard
│   └── health_tab.twig               # NEW: computer detail health tab
├── js/
│   ├── chat.js                       # EXISTING (keep)
│   ├── config.js                     # NEW: config form logic
│   └── dashboard.js                  # NEW: dashboard logic
└── css/
    ├── chat.css                      # EXISTING (keep)
    ├── config.css                    # NEW: config form styles
    └── dashboard.css                 # NEW: dashboard styles
```

---

## 6. Dependencies

### 6.1 AI Engine — `pyproject.toml` (Extended)

```toml
[project]
name = "chatbot-fastapi"
version = "4.0.0"
description = "FastAPI + CrewAI Gateway for GLPI IT Asset Management with Health Analysis"
requires-python = ">=3.12"
dependencies = [
    # EXISTING
    "crewai>=1.6.1",
    "fastapi>=0.136.1",
    "httpx>=0.28.1",
    "litellm>=1.83.14",
    "pydantic-settings>=2.14.0",
    "python-dotenv>=1.2.2",
    "uvicorn[standard]>=0.46.0",
    # NEW — Database Connectors
    "pymysql>=1.1.1",              # MariaDB (GLPI direct DB)
    "pymssql>=2.2.8",              # SQL Server (SCCM)
    "sqlalchemy>=2.0.36",          # ORM layer
    # NEW — Background Worker
    "celery>=5.4.0",               # Task queue
    "redis>=5.2.0",                # Message broker + cache
    # NEW — Utilities
    "apscheduler>=3.10.4",         # Job scheduling
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.1",
]
```

### 6.2 Environment Variables (Extended)

```bash
# === EXISTING ===
AI_GATEWAY_URL=https://ai-gw.stidev.biz.id/v1/chat/completions
AI_GATEWAY_BASE_URL=https://ai-gw.stidev.biz.id/v1
AI_GATEWAY_API_KEY=sk-xxx
AI_MODEL=qwen/qwen3-next-80b-a3b-instruct
GATEWAY_API_KEY=internal-glpi-secret-123
ALLOWED_ORIGINS=http://172.16.14.141
GLPI_URL=https://172.16.14.103
GLPI_API_URL=https://172.16.14.103/asset/apirest.php
GLPI_APP_TOKEN=
GLPI_USER_TOKEN=xxx
GLPI_VERIFY_SSL=false

# === NEW — GLPI Direct DB ===
GLPI_DB_HOST=172.16.14.103
GLPI_DB_PORT=3306
GLPI_DB_NAME=glpi
GLPI_DB_USER=glpi_readonly
GLPI_DB_PASSWORD=xxx

# === NEW — SCCM SQL Server ===
SCCM_DB_HOST=                         # Perlu koordinasi AHM
SCCM_DB_PORT=1433
SCCM_DB_NAME=                         # e.g., CM_PS1
SCCM_DB_USER=                         # Read-only user
SCCM_DB_PASSWORD=                     # Perlu koordinasi AHM

# === NEW — Redis ===
REDIS_HOST=localhost
REDIS_PORT=6379
```

---

## 7. API Endpoints Final

| Method | Endpoint | Auth | Sprint | Description |
|--------|----------|------|--------|-------------|
| POST | `/v1/chat/completions` | Bearer | ✅ Existing | Chat (OpenAI-compatible) |
| GET | `/health` | None | ✅ Existing | Health check |
| POST | `/api/health/analyze` | Bearer | 5-6 | Trigger health analysis (async) |
| GET | `/api/health/status/{job_id}` | None | 5-6 | Check analysis job status |
| GET | `/api/health/report/{asset_id}` | None | 5-6 | Single asset health report |
| GET | `/api/health/dashboard` | None | 5-6 | Summary dashboard data |
| POST | `/api/health/correlate` | Bearer | 3-4 | Trigger GLPI-SCCM correlation |
| GET | `/api/config` | Bearer | 1-2 | Get AI Engine config |
| PUT | `/api/config` | Bearer | 1-2 | Update AI Engine config |

---

## 8. SCCM SQL Server — Key Views untuk Query

| SCCM View | Data | Digunakan Untuk |
|-----------|------|-----------------|
| `v_R_System` | Hostname, domain, OS name, active status | Asset matching by hostname |
| `v_GS_COMPUTER_SYSTEM` | Manufacturer, model, system type | Hardware comparison |
| `v_GS_OPERATING_SYSTEM` | OS name, version, install date, last boot | OS comparison, age calculation |
| `v_GS_NETWORK_ADAPTER` | MAC address, IP, gateway, DHCP | MAC-based matching, network info |
| `v_GS_INSTALLED_SOFTWARE_CATEGORIZED` | Software name, version, publisher | Software inventory |
| `v_Update_ComplianceStatus` | Patch installed/missing/unknown | Patch compliance scoring |
| `v_GS_WORKSTATION_STATUS` | Last hardware/software scan | Last seen timestamp |
| `v_GS_PROCESSOR` | CPU name, cores | Hardware specs |
| `v_GS_X86_COMPUTER_SYSTEM` | Total physical memory | Hardware specs |
| `v_GS_DISK` | Disk size, free space | Storage health |

---

## 9. Risk Scoring Algorithm

```
Health Score = 100 - Σ(weighted penalties)

┌─────────────────────────────────────────────────────────────────┐
│  Factor                    │ Weight │ Condition              │ P │
├─────────────────────────────────────────────────────────────────┤
│  Hardware Age              │  20%   │ < 2 years             │  0│
│                            │        │ 2-4 years             │ 10│
│                            │        │ 4-6 years             │ 20│
│                            │        │ > 6 years             │ 30│
├─────────────────────────────────────────────────────────────────┤
│  Ticket Frequency (6mo)    │  25%   │ 0 tickets             │  0│
│                            │        │ 1-3 tickets           │ 10│
│                            │        │ 4-7 tickets           │ 20│
│                            │        │ > 7 tickets           │ 30│
├─────────────────────────────────────────────────────────────────┤
│  Patch Compliance (SCCM)   │  25%   │ > 95%                 │  0│
│                            │        │ 80-95%                │ 10│
│                            │        │ 60-80%                │ 20│
│                            │        │ < 60%                 │ 30│
│                            │        │ No data               │ 15│
├─────────────────────────────────────────────────────────────────┤
│  Warranty Status           │  15%   │ Active                │  0│
│                            │        │ Expiring < 6mo        │ 10│
│                            │        │ Expired               │ 20│
│                            │        │ No warranty           │ 15│
├─────────────────────────────────────────────────────────────────┤
│  SCCM Correlation          │  15%   │ Matched               │  0│
│                            │        │ Data mismatch         │ 10│
│                            │        │ Missing in SCCM       │ 15│
│                            │        │ Missing in GLPI       │ 15│
│                            │        │ Not checked           │ 10│
└─────────────────────────────────────────────────────────────────┘

Risk Categories:
  Critical:  0-30   → Immediate action required
  High:     31-50   → Action within 1 month
  Medium:   51-70   → Monitor and plan
  Low:      71-100  → Healthy, no action needed
```

---

## 10. Blockers & Prerequisites

| Item | Sprint | Status | Action Required |
|------|--------|--------|-----------------|
| SCCM DB Reachability | 3-4 | ❌ Unknown | Koordinasi dengan tim infrastruktur AHM untuk konfirmasi network path dari Docker ke SQL Server SCCM |
| SCCM DB Credentials | 3-4 | ❌ Unknown | Request read-only SQL account untuk SCCM database |
| SCCM DB Name (Site Code) | 3-4 | ❌ Unknown | Konfirmasi nama database SCCM (format: `CM_<sitecode>`) |
| GLPI DB Read-Only Account | 1-2 | ❌ Unknown | Buat database user read-only di MariaDB GLPI |
| LLM API Documentation | 3-4 | 🔲 Partial | Dokumentasi rate limits, token limits, model capabilities |
| Production Server Access | 13-14 | ❌ Unknown | Akses server untuk deployment Docker |

---

## 11. Execution Order — Sprint 1-2 Detail

Sprint 1-2 dikerjakan dalam urutan berikut:

```
WEEK 1:
├── Day 1-2: Docker setup
│   ├── Buat docker/Dockerfile
│   ├── Buat docker/Dockerfile.worker
│   ├── Buat docker/docker-compose.yml
│   ├── Buat docker/.dockerignore
│   └── Test: docker-compose up
│
├── Day 3-4: GLPI DB Connector
│   ├── Buat app/connectors/__init__.py
│   ├── Buat app/connectors/glpi_db_connector.py
│   ├── Extend app/config.py (GLPI_DB_* settings)
│   ├── Request read-only DB account dari admin
│   └── Test: connector queries
│
└── Day 5: FastAPI Route Refactor
    ├── Buat app/api/__init__.py
    ├── Buat app/api/main.py (slim entry)
    ├── Buat app/api/routes/__init__.py
    ├── Buat app/api/routes/chat.py (extract dari main.py)
    ├── Buat app/api/routes/health.py (placeholder)
    └── Test: semua endpoint masih berfungsi

WEEK 2:
├── Day 1-3: GLPI Plugin Config Page
│   ├── Modifikasi hook.php (add config table)
│   ├── Buat inc/config.class.php
│   ├── Buat front/config.php
│   ├── Buat ajax/config.php
│   ├── Buat views/config.twig
│   ├── Buat js/config.js
│   ├── Buat css/config.css
│   ├── Modifikasi setup.php (add config_page hook)
│   └── Test: config page CRUD
│
└── Day 4-5: Integration & Testing
    ├── Test Docker deployment end-to-end
    ├── Test config page → AI Engine connection
    ├── Test GLPI DB connector queries
    └── Fix bugs, update documentation
```
