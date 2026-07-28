> **⛔ DOKUMEN INI TELAH DIPINDAHKAN**
>
> Dokumen PRD ini telah dipindahkan ke subdirektori `docs/planned/PRD/`.
>
> **Buka di:** `docs/planned/PRD/PRD-01-Docker-Infrastructure.md`

---

# PRD-01: Docker & Infrastructure

> **Modul:** Docker & Infrastructure  
> **Sprint:** 1-2  
> **Prioritas:** High  
> **Dependensi:** Tidak ada (modul pertama)  
> **PIC Pengembang:** Tim AI  
> **PIC AHM:** IT Infrastructure (server provisioning)

---

## 1. Deskripsi Modul

Modul ini mencakup setup Docker environment untuk AI Engine, termasuk containerization FastAPI app, Celery worker, Celery beat scheduler, dan Redis. Saat ini AI Engine berjalan tanpa Docker di server `172.16.14.141`. Phase 2 membutuhkan Docker untuk menjalankan background workers (Celery) dan message broker (Redis) yang tidak bisa berjalan di setup saat ini.

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Containerize AI Engine (FastAPI) agar portable dan reproducible
2. Setup Celery worker container untuk background job processing
3. Setup Celery beat container untuk scheduled jobs
4. Setup Redis container sebagai message broker dan result backend
5. Menyediakan docker-compose untuk orchestrasi seluruh stack

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | `docker-compose up` berhasil menjalankan semua 4 service tanpa error | Manual test |
| AC-02 | FastAPI app accessible di `http://<host>:8000/health` dan return status ok | cURL test |
| AC-03 | Celery worker terhubung ke Redis dan siap menerima task | `celery inspect active` |
| AC-04 | Celery beat dapat menjadwalkan task periodik | Log check |
| AC-05 | Redis accessible di port 6379 dan persist data | `redis-cli ping` |
| AC-06 | Semua container auto-restart on failure | `docker-compose restart` test |
| AC-07 | Environment variables dari `.env` terbaca oleh semua container | Config check |
| AC-08 | Chat endpoint (`/v1/chat/completions`) berfungsi sama seperti sebelum Docker | cURL test |
| AC-09 | SSE streaming berfungsi di Docker environment | Browser test |
| AC-10 | Container logs terstruktur dan accessible via `docker-compose logs` | Log check |

## 3. Spesifikasi Teknis

### 3.1 Arsitektur Docker

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Host                           │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  ai-engine   │  │ celery-worker│  │  celery-beat │  │
│  │  (FastAPI)   │  │  (Worker)    │  │  (Scheduler) │  │
│  │  Port: 8000  │  │              │  │              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
│         └─────────────────┼──────────────────┘          │
│                           │                             │
│                    ┌──────┴───────┐                     │
│                    │    redis     │                     │
│                    │  Port: 6379  │                     │
│                    └──────────────┘                     │
│                                                         │
│  Network: ai-network (bridge)                           │
│  Volumes: redis-data (persistent)                       │
└─────────────────────────────────────────────────────────┘
```

### 3.2 File yang Dibuat

| File | Lokasi | Fungsi |
|------|--------|--------|
| `Dockerfile` | `docker/Dockerfile` | Image untuk FastAPI app |
| `Dockerfile.worker` | `docker/Dockerfile.worker` | Image untuk Celery worker/beat |
| `docker-compose.yml` | `docker/docker-compose.yml` | Orchestration semua service |
| `.dockerignore` | `docker/.dockerignore` | Exclude file dari build context |

### 3.3 Dockerfile — FastAPI App

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY app/ app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Catatan:**
- Base image `python:3.12-slim` untuk ukuran minimal
- `libmariadb-dev` diperlukan untuk pymysql (GLPI DB connector, Sprint 1-2)
- `uv sync --frozen --no-dev` untuk reproducible dependency install
- Healthcheck memastikan container di-restart jika app crash

### 3.4 Dockerfile.worker — Celery Worker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmariadb-dev \
    freetds-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY app/ app/

CMD ["uv", "run", "celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info"]
```

**Catatan:**
- `freetds-dev` diperlukan untuk pymssql (SCCM connector, Sprint 3-4)
- Worker image berbeda dari app image karena dependency tambahan
- Command bisa di-override di docker-compose untuk celery-beat

### 3.5 docker-compose.yml

```yaml
version: "3.8"

services:
  ai-engine:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: glpi-ai-engine
    ports:
      - "${AI_ENGINE_PORT:-8000}:8000"
    env_file:
      - ../.env
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - ai-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  celery-worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.worker
    container_name: glpi-ai-worker
    env_file:
      - ../.env
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - ai-network
    command: ["uv", "run", "celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"]

  celery-beat:
    build:
      context: ..
      dockerfile: docker/Dockerfile.worker
    container_name: glpi-ai-beat
    env_file:
      - ../.env
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - ai-network
    command: ["uv", "run", "celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info"]

  redis:
    image: redis:7-alpine
    container_name: glpi-ai-redis
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - ai-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru

networks:
  ai-network:
    driver: bridge
    name: glpi-ai-network

volumes:
  redis-data:
    name: glpi-ai-redis-data
```

**Catatan:**
- Redis menggunakan `appendonly yes` untuk persistence
- `maxmemory 256mb` dengan `allkeys-lru` untuk mencegah OOM
- Celery worker `--concurrency=2` untuk server dengan 4 vCPU
- Semua container menggunakan `restart: unless-stopped`
- Redis healthcheck memastikan worker/beat tidak start sebelum Redis ready

### 3.6 .dockerignore

```
.venv/
.git/
__pycache__/
*.pyc
*.pyo
.env
*.md
!README.md
test_*
docker/
*.log
.claude/
```

### 3.7 Environment Variables Baru

Tambahkan ke `.env`:

```bash
# Docker / Infrastructure
AI_ENGINE_PORT=8000
REDIS_HOST=redis
REDIS_PORT=6379
```

**Catatan:** `REDIS_HOST=redis` karena di Docker, Redis accessible via service name `redis` di network `ai-network`. Untuk development lokal tanpa Docker, gunakan `REDIS_HOST=localhost`.

### 3.8 Celery App Placeholder

Sebagai bagian dari modul ini, perlu dibuat placeholder untuk Celery app agar Docker build tidak gagal:

**`app/workers/__init__.py`** — Empty

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

**`app/config.py`** — Tambahkan:

```python
redis_host: str = "localhost"
redis_port: int = 6379
```

## 4. Data Flow

```
                    HTTP Request
                        │
                        ▼
                ┌──────────────┐
                │   ai-engine  │  Port 8000
                │   (FastAPI)  │
                └──────┬───────┘
                       │
            ┌──────────┼──────────┐
            │          │          │
            ▼          ▼          ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │  GLPI    │ │  AI      │ │  Redis   │
    │  REST API│ │  Gateway │ │  (cache) │
    └──────────┘ └──────────┘ └──────────┘
                       │
                       │ enqueue task
                       ▼
                ┌──────────────┐
                │ celery-worker│  Background
                │              │  Processing
                └──────┬───────┘
                       │
            ┌──────────┼──────────┐
            │          │          │
            ▼          ▼          ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │  GLPI DB │ │  SCCM DB │ │  Redis   │
    │ (future) │ │ (future) │ │ (result) │
    └──────────┘ └──────────┘ └──────────┘
```

## 5. Konfigurasi & Environment

### 5.1 Environment Variables Lengkap (Modul Ini)

| Variable | Default | Deskripsi | Dibutuhkan Di |
|----------|---------|-----------|---------------|
| `AI_ENGINE_PORT` | `8000` | Port mapping FastAPI ke host | docker-compose |
| `REDIS_HOST` | `localhost` | Redis hostname (Docker: `redis`) | celery_app, config |
| `REDIS_PORT` | `6379` | Redis port | celery_app, config |

### 5.2 Development vs Production

| Aspek | Development | Production |
|-------|-------------|------------|
| Redis host | `localhost` | `redis` (Docker service name) |
| Celery concurrency | 1 | 2-4 (sesuai CPU) |
| Redis maxmemory | default | 256mb |
| Log level | `info` | `warning` |
| Healthcheck interval | 30s | 60s |
| Container restart | `unless-stopped` | `always` |

## 6. Error Handling

| Error | Penyebab | Handling |
|-------|----------|----------|
| Redis connection refused | Redis belum ready saat worker start | `depends_on: condition: service_healthy` + retry logic di Celery |
| Container OOM | Memory limit terlampaui | Redis `maxmemory-policy`, worker `--concurrency` dibatasi |
| Build failure | Dependency install gagal | `uv sync --frozen` + cache layer di Dockerfile |
| Port conflict | Port 8000/6379 sudah dipakai | Configurable via `AI_ENGINE_PORT` dan `REDIS_PORT` env |
| Worker crash | Task exception tidak tertangani | `task_time_limit`, `worker_max_tasks_per_child`, auto-restart |

## 7. Testing

### 7.1 Test Cases

| ID | Test | Langkah | Expected Result |
|----|------|---------|-----------------|
| T-01 | Docker build | `docker-compose build` | Semua image berhasil dibuild tanpa error |
| T-02 | Docker up | `docker-compose up -d` | 4 container running: ai-engine, celery-worker, celery-beat, redis |
| T-03 | Health check | `curl http://localhost:8000/health` | Response `{"status": "ok", ...}` |
| T-04 | Redis ping | `docker exec glpi-ai-redis redis-cli ping` | Response `PONG` |
| T-05 | Celery inspect | `docker exec glpi-ai-worker uv run celery -A app.workers.celery_app inspect active` | Worker terdaftar dan aktif |
| T-06 | Chat endpoint | `curl -X POST http://localhost:8000/v1/chat/completions -H "Authorization: Bearer <key>" -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"halo"}]}'` | Response chat normal |
| T-07 | SSE streaming | Same as T-06 dengan `"stream": true` | SSE events diterima |
| T-08 | Auto restart | `docker restart glpi-ai-redis` | ai-engine, worker, beat reconnect setelah Redis up |
| T-09 | Log access | `docker-compose logs ai-engine` | Logs terstruktur dan readable |
| T-10 | Env loading | Check config di `/health` endpoint | Environment variables terbaca dengan benar |

### 7.2 Smoke Test Script

```bash
#!/bin/bash
# smoke-test.sh — Quick validation after docker-compose up

echo "=== Docker Infrastructure Smoke Test ==="

echo "[1/5] Checking containers..."
docker-compose ps | grep -E "ai-engine|celery-worker|celery-beat|redis" | grep "Up" && echo "PASS" || echo "FAIL"

echo "[2/5] Checking FastAPI health..."
curl -sf http://localhost:8000/health | python -m json.tool | grep "ok" && echo "PASS" || echo "FAIL"

echo "[3/5] Checking Redis..."
docker exec glpi-ai-redis redis-cli ping | grep "PONG" && echo "PASS" || echo "FAIL"

echo "[4/5] Checking Celery worker..."
docker exec glpi-ai-worker uv run celery -A app.workers.celery_app inspect ping --timeout 10 2>/dev/null | grep "pong" && echo "PASS" || echo "FAIL"

echo "[5/5] Checking chat endpoint..."
curl -sf -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"halo"}]}' | python -m json.tool | grep "choices" && echo "PASS" || echo "FAIL"

echo "=== Done ==="
```

## 8. Dependensi Modul Lain

| Modul | Dependensi ke Modul Ini | Detail |
|-------|------------------------|--------|
| PRD-03 (GLPI DB Connector) | Celery app placeholder | `app/workers/celery_app.py` harus ada |
| PRD-04 (SCCM Connector) | Dockerfile.worker | `freetds-dev` harus di-install |
| PRD-05 (Asset Health AI) | Celery + Redis | Worker dan broker harus running |
| PRD-06 (Health Plugin UI) | FastAPI accessible | API endpoints harus reachable dari GLPI |

## 9. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| Docker tidak tersedia di server target | Low | High | Konfirmasi Docker CE support dengan AHM sebelum mulai |
| Redis data loss pada restart | Medium | Medium | `appendonly yes` + volume persistent |
| Port conflict dengan service lain | Medium | Low | Port configurable via env vars |
| Image size terlalu besar | Low | Low | Multi-stage build jika perlu, slim base image |
| Celery worker memory leak | Medium | Medium | `worker_max_tasks_per_child=50` untuk recycle |

## 10. Deliverables

| Deliverable | Format | Lokasi |
|-------------|--------|--------|
| Dockerfile | File | `docker/Dockerfile` |
| Dockerfile.worker | File | `docker/Dockerfile.worker` |
| docker-compose.yml | File | `docker/docker-compose.yml` |
| .dockerignore | File | `docker/.dockerignore` |
| Celery app placeholder | File | `app/workers/celery_app.py` |
| Config update | File | `app/config.py` (extend) |
| Smoke test script | File | `docker/smoke-test.sh` |
