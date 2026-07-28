> **⛔ DOKUMEN INI TELAH DIPINDAHKAN**
>
> Dokumen PRD ini telah dipindahkan ke subdirektori `docs/planned/PRD/`.
>
> **Buka di:** `docs/planned/PRD/PRD-09-Testing-Security-Deployment.md`

---

# PRD-09: Testing, Security & Deployment

> **Modul:** Testing, Security Review, Performance Optimization, Documentation, Deployment  
> **Sprint:** 13-14  
> **Prioritas:** Medium  
> **Dependensi:** Semua modul PRD-01 s/d PRD-08  
> **PIC Pengembang:** Tim AI  
> **PIC AHM:** IT Security (review), IT Management (UAT, go-live approval)  
> **Repo:** Kedua repo (plugin + AI Engine)

---

## 1. Deskripsi Modul

Modul ini mencakup aktivitas-aktivitas akhir sebelum go-live:

1. **Testing** — Unit tests, integration tests, end-to-end tests, load tests
2. **Security Review** — SQL injection prevention, API key management, rate limiting, input validation
3. **Performance Optimization** — Caching, connection pooling, pagination
4. **Documentation** — API spec, deployment guide, SCCM integration guide
5. **Deployment** — Production deployment, UAT, go-live

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Mencapai minimal 80% code coverage untuk core modules (scorer, connector, correlator)
2. Lulus security review tanpa critical findings
3. Semua API endpoints merespons dalam 5 detik untuk normal load
4. Dokumentasi lengkap untuk deployment dan maintenance
5. UAT passed dengan minimal 3 pengguna AHM
6. Go-live approved oleh management AHM

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | Unit test coverage ≥ 80% untuk `scorers/`, `connectors/`, `correlators/` | pytest --cov |
| AC-02 | Integration test: chat flow end-to-end berfungsi | Test suite |
| AC-03 | Integration test: health analysis end-to-end berfungsi | Test suite |
| AC-04 | Security review: tidak ada SQL injection | Pen test / code review |
| AC-05 | Security review: API key tidak terekspos | Code review |
| AC-06 | Rate limiting aktif di semua endpoints | Load test |
| AC-07 | Dashboard load < 3 detik | Benchmark |
| AC-08 | Health report single asset < 2 detik | Benchmark |
| AC-09 | Full analysis (500 aset) < 10 menit | Benchmark |
| AC-10 | Chat response < 10 detik (non-streaming) | Benchmark |
| AC-11 | API documentation tersedia (OpenAPI/Swagger) | UI check |
| AC-12 | Deployment guide lengkap | Document review |
| AC-13 | UAT passed oleh 3+ pengguna AHM | Sign-off |
| AC-14 | Go-live approved | Management sign-off |

## 3. Spesifikasi Teknis

### 3.1 Testing

#### Test Structure

```
ai-engine/tests/
├── __init__.py
├── conftest.py                        # Shared fixtures
├── test_health_scorer.py              # Unit: HealthScorer
├── test_risk_category.py              # Unit: RiskCategory
├── test_glpi_db_connector.py          # Unit: GLPIDBConnector (mocked)
├── test_sccm_connector.py             # Unit: SCCMConnector (mocked)
├── test_asset_correlator.py           # Unit: AssetCorrelator (mocked)
├── test_glpi_normalizer.py            # Unit: GLPI normalizer
├── test_sccm_normalizer.py            # Unit: SCCM normalizer
├── test_sccm_tools.py                 # Unit: SCCM CrewAI tools
├── test_health_tools.py               # Unit: Health CrewAI tools
├── test_health_api.py                 # Integration: API endpoints
├── test_chat_api.py                   # Integration: Chat endpoint
├── test_celery_tasks.py               # Integration: Celery tasks
├── test_e2e_chat.py                   # E2E: Full chat flow
├── test_e2e_health.py                 # E2E: Full health analysis flow
└── test_load.py                       # Load: Concurrent requests
```

#### conftest.py

```python
import pytest
from unittest.mock import MagicMock, patch
from app.config import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        ai_gateway_url="https://test.example.com/v1/chat/completions",
        ai_gateway_base_url="https://test.example.com/v1",
        ai_gateway_api_key="test-ai-key",
        ai_model="test-model",
        gateway_api_key="test-gateway-key",
        allowed_origins="http://localhost",
        glpi_url="https://glpi.test",
        glpi_api_url="https://glpi.test/apirest.php",
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


@pytest.fixture
def sample_sccm_compliance():
    return {
        "total_updates": 100,
        "installed": 95,
        "missing": 3,
        "unknown": 2,
        "compliance_pct": 95.0,
    }


@pytest.fixture
def mock_glpi_db():
    with patch("app.connectors.glpi_db_connector.get_glpi_db") as mock:
        db = MagicMock()
        mock.return_value = db
        yield db


@pytest.fixture
def mock_sccm_db():
    with patch("app.connectors.sccm_connector.get_sccm_db") as mock:
        db = MagicMock()
        mock.return_value = db
        yield db
```

#### Key Test Cases

**test_health_scorer.py:**

| Test | Input | Expected |
|------|-------|----------|
| `test_healthy_asset` | New computer, 0 tickets, active warranty, 98% compliance, SCCM matched | Score ≥ 85, Low |
| `test_critical_asset` | Old computer, 10 tickets, expired warranty, 40% compliance, missing in SCCM | Score ≤ 30, Critical |
| `test_no_sccm_data` | Normal computer, sccm_compliance=None | Score calculated, sccm penalty=15 |
| `test_no_creation_date` | computer_data without date_creation | Age penalty=15 |
| `test_boundary_30` | Score exactly 30 | RiskCategory.CRITICAL |
| `test_boundary_31` | Score exactly 31 | RiskCategory.HIGH |
| `test_recommendations_urgent` | Low compliance | Contains "[URGENT]" |
| `test_recommendations_healthy` | All good | Contains "[INFO]" |

**test_asset_correlator.py:**

| Test | Input | Expected |
|------|-------|----------|
| `test_matched_assets` | Same hostname, same data | match_status="matched" |
| `test_os_mismatch` | Same hostname, different OS | match_status="mismatch", mismatches has os_name |
| `test_missing_in_sccm` | Hostname not in SCCM | match_status="missing_in_sccm" |
| `test_missing_in_glpi` | Hostname not in GLPI | match_status="missing_in_glpi" |
| `test_case_insensitive` | "PC-001" vs "pc-001" | Still matched |

### 3.2 Security Review

#### Checklist

| Item | Status | Detail |
|------|--------|--------|
| SQL Injection Prevention | 🔲 | Semua query menggunakan SQLAlchemy `text()` dengan parameterized inputs |
| API Key Exposure | 🔲 | API keys hanya di `.env`, tidak di log atau response |
| Rate Limiting | 🔲 | Implementasi `slowapi` middleware |
| Input Validation | 🔲 | Pydantic models untuk semua API inputs |
| CORS Configuration | 🔲 | Review `allowed_origins` — tidak menggunakan `*` |
| CSRF Protection | 🔲 | Plugin GLPI sudah implement (verify) |
| IDOR Protection | 🔲 | Session ownership validation (verify) |
| Audit Trail | 🔲 | Semua actions dicatat |
| Secrets Management | 🔲 | `.env` file, pertimbangkan vault untuk production |
| Read-Only DB Access | 🔲 | Verify DB users hanya punya SELECT |
| TLS/HTTPS | 🔲 | Verify komunikasi encrypted |
| Error Messages | 🔲 | Tidak expose internal details di error responses |

#### Rate Limiting Implementation

```python
# Ditambahkan ke app/main.py:
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )

# Apply ke endpoints:
@router.post("/v1/chat/completions")
@limiter.limit("20/minute")
async def chat_completions(request: Request, ...):
    ...
```

#### Input Validation Enhancement

```python
# Ditambahkan ke semua API input models:
from pydantic import BaseModel, Field, validator

class ChatRequest(BaseModel):
    messages: list[dict] = Field(..., max_length=50)
    glpi_user_id: int = Field(default=0, ge=0)
    session_id: str | None = Field(default=None, max_length=100)
    stream: bool = False

    @validator('messages')
    def validate_messages(cls, v):
        for msg in v:
            if 'role' not in msg or 'content' not in msg:
                raise ValueError('Each message must have role and content')
            if msg['role'] not in ('user', 'assistant', 'system'):
                raise ValueError('Invalid role')
            if len(msg['content']) > 10000:
                raise ValueError('Message content too long')
        return v
```

### 3.3 Performance Optimization

#### Caching Strategy

```python
# Ditambahkan ke app/cache.py — Redis-based caching:

import redis
import json
import logging
from app.config import Settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, settings: Settings):
        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=2,  # DB 2 untuk cache (0=broker, 1=result backend)
            decode_responses=True,
        )

    def get(self, key: str) -> dict | list | None:
        try:
            data = self._client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Cache get error for key '{key}': {e}")
        return None

    def set(self, key: str, value: dict | list, ttl: int = 300) -> bool:
        try:
            return self._client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning(f"Cache set error for key '{key}': {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for key '{key}": {e}')
            return False


_cache: RedisCache | None = None


def init_cache(settings: Settings):
    global _cache
    _cache = RedisCache(settings)


def get_cache() -> RedisCache:
    if _cache is None:
        raise RuntimeError("Cache not initialized")
    return _cache
```

#### Dashboard Caching

```python
# Modifikasi app/api/routes/health.py — dashboard endpoint:

@router.get("/dashboard")
async def get_dashboard():
    from app.cache import get_cache

    cache = get_cache()
    cached = cache.get("dashboard:summary")
    if cached:
        return cached

    # ... existing dashboard logic ...

    result = {
        "total_computers": total_computers,
        "status_distribution": status_dist,
        "age_distribution": age_dist,
        "warranty_summary": warranty_summary,
    }

    cache.set("dashboard:summary", result, ttl=300)  # 5 min cache
    return result
```

### 3.4 Documentation

#### File Baru

| File | Fungsi |
|------|--------|
| `docs/api-spec.md` | API specification (OpenAPI format) |
| `docs/deployment-guide.md` | Panduan deployment Docker |
| `docs/sccm-integration.md` | Panduan integrasi SCCM |
| `docs/health-algorithm.md` | Dokumentasi algoritma health scoring |
| `docs/operations-runbook.md` | Runbook untuk operasional |

#### API Spec Structure

```markdown
# API Specification — GLPI AI Gateway v4.0.0

## Base URL
`http://<ai-engine-host>:8000`

## Authentication
All protected endpoints require `Authorization: Bearer <GATEWAY_API_KEY>`

## Endpoints

### Chat
- POST /v1/chat/completions — OpenAI-compatible chat endpoint
  - Request: { messages, glpi_user_id, session_id, stream }
  - Response: { id, object, model, session_id, choices }

### Health Analysis
- POST /api/health/analyze — Trigger analysis
- GET /api/health/status/{job_id} — Check job status
- GET /api/health/report/{asset_id} — Single asset report
- GET /api/health/dashboard — Dashboard summary
- POST /api/health/correlate — Trigger GLPI-SCCM correlation

### System
- GET /health — Service health check
- GET /api/config — Get configuration
- PUT /api/config — Update configuration
```

#### Deployment Guide Structure

```markdown
# Deployment Guide

## Prerequisites
- Docker CE 24+
- Docker Compose v2
- Server: 4 vCPU, 8 GB RAM, 50 GB SSD
- Network access to GLPI DB (3306), SCCM DB (1433), AI Gateway (443)

## Steps
1. Clone repository
2. Configure .env
3. Build and start: `docker-compose -f docker/docker-compose.yml up -d`
4. Verify: `curl http://localhost:8000/health`
5. Configure GLPI Plugin
6. Test chat
7. Test health analysis

## Monitoring
- `docker-compose logs -f`
- `/health` endpoint
- Redis: `docker exec glpi-ai-redis redis-cli info`

## Troubleshooting
- Container won't start → check logs, check .env
- Can't connect to GLPI DB → check firewall, credentials
- SCCM features disabled → check sccm_db_host in .env
```

### 3.5 Deployment Procedure

#### Pre-deployment Checklist

| Item | Verifikasi |
|------|------------|
| Server siap dengan Docker | `docker --version`, `docker compose version` |
| `.env` dikonfigurasi dengan production values | Review semua variables |
| GLPI DB read-only account aktif | Test koneksi |
| SCCM DB read-only account aktif (jika tersedia) | Test koneksi |
| Firewall rules dibuka | Test dari AI Engine ke GLPI DB dan SCCM DB |
| SSL certificate terinstall (jika required) | HTTPS test |
| GLPI plugin diupdate ke versi terbaru | Install/upgrade plugin |
| Backup database GLPI | Verify backup exists |

#### Deployment Steps

```bash
# 1. Clone dan configure
cd /opt
git clone <repo-url> glpi-ai-engine
cd glpi-ai-engine
cp .env.example .env
# Edit .env dengan production values

# 2. Build dan start
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d

# 3. Verify
curl http://localhost:8000/health
docker compose -f docker/docker-compose.yml ps

# 4. Update GLPI Plugin
# Copy plugin files ke /var/www/glpi/plugins/chatbot/
# Login GLPI → Setup → Plugins → Install → Activate

# 5. Configure Plugin
# GLPI → Tools → Chatbot Configuration
# Set API URL ke AI Engine server

# 6. Smoke test
# GLPI → Tools → AI Chatbot → Send test message
# GLPI → Tools → Asset Health Dashboard → Check data
```

#### Rollback Plan

```bash
# Jika ada masalah:
docker compose -f docker/docker-compose.yml down
# Revert ke previous version:
git checkout <previous-tag>
docker compose -f docker/docker-compose.yml up -d
# Plugin: GLPI → Setup → Plugins → Rollback
```

### 3.6 UAT Plan

#### Test Scenarios untuk UAT

| No | Skenario | Langkah | Expected |
|----|----------|---------|----------|
| UAT-01 | Chat — tanya aset | Ketik "Komputer saya" | Daftar komputer user |
| UAT-02 | Chat — tanya tiket | Ketik "Tiket aktif saya" | Daftar tiket aktif |
| UAT-03 | Chat — tanya software | Ketik "Software di PC-001" | Daftar software dari SCCM |
| UAT-04 | Chat — tanya kesehatan | Ketik "Kesehatan PC-001" | Health score + rekomendasi |
| UAT-05 | Chat — multi-turn | Tanya komputer → tanya detail | Context retained |
| UAT-06 | Dashboard — overview | Buka dashboard | Cards dan tabel terisi |
| UAT-07 | Dashboard — run analysis | Click "Run Full Analysis" | Progress → completed |
| UAT-08 | Dashboard — correlation | Click "Run Correlation" | Correlation results |
| UAT-09 | Health tab | Buka Computer detail → AI Health tab | Score ring + recommendations |
| UAT-10 | Config page | Ubah model → save → test chat | Chat menggunakan model baru |

#### UAT Sign-off Template

```
UAT Sign-off — GLPI AI Extension Phase 2

Tester: _______________
Date: _______________
Department: _______________

Test Results:
□ All UAT scenarios passed
□ Minor issues found (list below)
□ Major issues found (list below)

Minor Issues:
1. _______________
2. _______________

Major Issues:
1. _______________

Verdict:
□ PASS — Ready for go-live
□ PASS WITH CONDITIONS — (specify conditions)
□ FAIL — Needs rework

Signature: _______________
```

## 4. Testing

| ID | Test | Expected |
|----|------|----------|
| T-01 | pytest —cov=app/scorers | Coverage ≥ 80% |
| T-02 | pytest —cov=app/connectors | Coverage ≥ 80% |
| T-03 | pytest —cov=app/correlators | Coverage ≥ 80% |
| T-04 | Integration test: full chat flow | Response received |
| T-05 | Integration test: health analysis flow | Report generated |
| T-06 | Load test: 10 concurrent chat requests | All respond < 15s |
| T-07 | Load test: dashboard with 5000 assets | Load < 5s |
| T-08 | Security: SQL injection attempt | No injection possible |
| T-09 | Security: API key in URL | Rejected |
| T-10 | Security: rate limit exceeded | 429 response |

## 5. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| UAT participants tidak tersedia | Medium | High | Koordinasi sejak Sprint 7, sediakan remote testing |
| Security review menemukan critical issue | Low | High | Address segera, re-test |
| Performance tidak memenuhi target | Medium | Medium | Caching, query optimization, pagination |
| Deployment gagal di production | Low | High | Rollback plan, staging environment test |
| Documentation tidak lengkap | Medium | Low | Template-based docs, review checklist |

## 6. Deliverables

| Deliverable | Lokasi |
|-------------|--------|
| Test suite | `tests/` (all test files) |
| Rate limiting middleware | `app/main.py` (extend) |
| Input validation | `app/models/` (extend) |
| Redis caching | `app/cache.py` (extend) |
| API specification | `docs/api-spec.md` |
| Deployment guide | `docs/deployment-guide.md` |
| SCCM integration guide | `docs/sccm-integration.md` |
| Health algorithm doc | `docs/health-algorithm.md` |
| Operations runbook | `docs/operations-runbook.md` |
| UAT plan & sign-off template | `docs/uat-plan.md` |

---

## 6. 🔄 Alignment Updates untuk PRD-04 SCCM Integration

### 6.1 Test File Baru untuk SCCM Integration

Tambahkan ke struktur `tests/`:

```
ai-engine/tests/
├── ...
├── test_correlation_api.py            # Integration: /v1/health/correlate endpoints (baru)
├── test_correlation_jobs.py           # Integration: Celery job idempotency + approval gate (baru)
├── test_audit_store.py                # Integration: SQLite WAL audit store (baru)
├── test_data_quality_filters.py       # Unit: Serial blacklist, MAC exclude, stale resolver (baru)
├── test_keyset_pagination.py          # Unit: Keyset pagination correctness (baru)
├── test_auth_dual_keys.py             # Security: GATEWAY_API_KEY vs GLPI_PLUGIN_API_KEY (baru)
├── test_e2e_correlation.py            # E2E: Full correlation + approve flow (baru)
└── test_load.py                       # Load: Concurrent requests (existing, update)
```

### 6.2 Tambahan Test Scenario per File

#### `test_correlation_api.py` — Approval Gate & Idempotency

| Test Case | Input | Expected |
|-----------|-------|----------|
| `test_trigger_correlation_fresh` | POST `/v1/health/correlate` (no running job) | `202 Accepted`, `job_id` returned |
| `test_trigger_correlation_duplicate` | POST `/v1/health/correlate` (job already running) | `409 Conflict`, `existing_job_id` |
| `test_approve_job_pending` | POST `/v1/health/correlate/{id}/approve` (status=pending_review) | `200 OK`, status changes to `approved` |
| `test_approve_job_already_approved` | POST approve pada job yg sudah `approved` | `409 Conflict` |
| `test_approve_job_already_rejected` | POST approve pada job yg sudah `rejected` | `409 Conflict` |
| `test_reject_job_pending` | POST `/v1/health/correlate/{id}/reject` (status=pending_review) | `200 OK`, status changes to `rejected` |
| `test_reject_twice` | POST reject dua kali berturut-turut | Kedua kalinya: `409 Conflict` |

#### `test_audit_store.py` — SQLite WAL Audit Persistence

| Test Case | Input | Expected |
|-----------|-------|----------|
| `test_audit_log_write` | Trigger correlation via API | SQLite file exists, entry written |
| `test_audit_log_approve` | Approve correlation result | Audit entry `action='approve'` with `requester_id` & `requester_name` |
| `test_audit_log_reject` | Reject correlation result | Audit entry `action='reject'` |
| `test_audit_log_wal_mode` | Check SQLite pragma | `journal_mode` = `wal` |
| `test_audit_log_requester_fields` | Verify identity fields in log | `requester_id`, `requester_name` populated from headers |
| `test_audit_log_persistence_restart` | Simulate container restart | Audit data tidak hilang |
| `test_audit_log_concurrent_write` | Simultan approve + reject | Tidak ada SQLite `database is locked` error |

#### `test_data_quality_filters.py` — Data Quality & Blacklist

| Test Case | Input | Expected |
|-----------|-------|----------|
| `test_serial_blacklist_to_be_filled` | Serial: `"To Be Filled By O.E.M."` | `skip Stage 2`, fallback ke MAC Stage 3 |
| `test_serial_blacklist_system_serial` | Serial: `"System Serial Number"` | `skip Stage 2` |
| `test_serial_blacklist_zeros` | Serial: `"00000000"` | `skip Stage 2` |
| `test_serial_blacklist_normal` | Serial: `"ABC123"` | `use untuk Stage 2` |
| `test_mac_virtual_exclude_hyperv` | MAC adapter: `vEthernet` | Exclude from matching |
| `test_mac_virtual_exclude_vpn` | MAC adapter: `VPN` | Exclude |
| `test_mac_virtual_exclude_tap` | MAC adapter: `TAP-Windows` | Exclude |
| `test_mac_virtual_exclude_bluetooth` | MAC adapter: `Bluetooth` | Exclude |
| `test_mac_non_virtual_included` | MAC adapter: `Realtek PCIe GbE` | Include in matching |
| `test_mac_ip_not_enabled` | `IPEnabled0 = 0` | Exclude |
| `test_stale_resolver_multiple` | 2 ResourceID untuk 1 hostname | Pilih yg `LastHWScan` terbaru |
| `test_stale_resolver_single` | 1 ResourceID | Tidak perlu resolver |

#### `test_keyset_pagination.py` — Keyset Pagination

| Test Case | Input | Expected |
|-----------|-------|----------|
| `test_keyset_pagination_first_page` | `last_seen_id=0`, `batch_size=100` | 100 records dari ResourceID 1-100 |
| `test_keyset_pagination_second_page` | `last_seen_id=100`, `batch_size=100` | 100 records dari ResourceID 101-200 |
| `test_keyset_pagination_no_more_data` | `last_seen_id=950`, `batch_size=100` | Empty list (0-49 records) |
| `test_keyset_pagination_order` | Pagination bertahap | IDs strictly ascending, no gaps |
| `test_keyset_pagination_active_only` | Default filter | Only `Obsolete0=0 AND Active0=1` returned |

#### `test_auth_dual_keys.py` — Dual Auth

| Test Case | Input | Expected |
|-----------|-------|----------|
| `test_chat_endpoint_gateway_key` | Chat with `GATEWAY_API_KEY` | `200 OK` |
| `test_chat_endpoint_wrong_key` | Chat with `GLPI_PLUGIN_API_KEY` | `401 Unauthorized` |
| `test_correlation_endpoint_plugin_key` | `/v1/health/correlate` with `GLPI_PLUGIN_API_KEY` | `202 Accepted` |
| `test_correlation_endpoint_wrong_key` | Correlation with `GATEWAY_API_KEY` | `401 Unauthorized` |
| `test_correlation_endpoint_no_key` | Correlation without auth header | `401 Unauthorized` |

### 6.3 Tambahan Security Checklist

| # | Item | Status |
|---|------|--------|
| 🔴 | `GLPI_PLUGIN_API_KEY` dipisah dari `GATEWAY_API_KEY` | ⬜ |
| 🟠 | `trustServerCertificate` diset `True` hanya untuk internal CA, `False` untuk public CA | ⬜ |
| 🟡 | Endpoint approval/reject hanya bisa diakses dari IP GLPI plugin (firewall) | ⬜ |
| 🟢 | Semua koneksi SCCM menggunakan `encrypt=true` | ⬜ |
| 🟢 | Audit log `audit_log.db` di volume mount persisten — tidak hilang saat container restart | ⬜ |

### 6.4 Tambahan Risk Register (Deployment)

| Risiko Baru | Prob. | Impact | Mitigasi |
|-------------|-------|--------|----------|
| FreeTDS build failure di Alpine (pymssql C extension) | Rendah | Tinggi | Gunakan `python:3.12-slim` untuk Docker + `freetds-dev` |
| SQLite audit lock di multi-worker | Sedang | Sedang | WAL mode + Celery audit task sentral + rekomendasi single-worker |
| Serial number generic menyebabkan false unmatch | Rendah | Rendah | Blacklist filtering + skip ke MAC; tidak ada false match, hanya beda metode |
| Keyset ResourceID gap (data dihapus di SCCM) | Rendah | Rendah | Keyset tetap aman — gap tidak mempengaruhi correctness |

### 6.5 Deployment Checklist Update

| # | Item | Sebelumnya | Sesudah |
|---|------|-----------|---------|
| 1 | **Volume Mounts** | Redis hanya `redis-data` | Redis `redis-data` + **SQLite `audit-data`** |
| 2 | **Environment Vars .env** | `GATEWAY_API_KEY` saja | `GATEWAY_API_KEY` + **`GLPI_PLUGIN_API_KEY`** |
| 3 | **Firewall Rules** | GLPI (3306), AI Gateway (443) | GLPI (3306), SCCM (1433), AI Gateway (443) |
| 4 | **Celery Services** | `celery-worker` + `celery-beat` | `celery-worker` + `celery-beat` + (internal: audit task route) |
| 5 | **Dockerfile Dependencies** | `libmariadb-dev` (pymysql) | `libmariadb-dev` + **`freetds-dev`** (pymssql) |
| 6 | **Health Check** | Status GLPI + Redis | Status GLPI + Redis + **SCCM** |
