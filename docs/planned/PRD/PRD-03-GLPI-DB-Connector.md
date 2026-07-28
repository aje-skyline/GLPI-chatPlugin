# PRD-03: GLPI DB Connector

> **Modul:** AI Engine — GLPI Direct Database Connector  
> **Sprint:** 1-2  
> **Prioritas:** High  
> **Dependensi:** PRD-01 (Docker Infrastructure)  
> **PIC Pengembang:** Tim AI  
> **PIC AHM:** DBA (read-only account provisioning)  
> **Repo:** `/home/ariel/projects/chatbot-fastapi/`

---

## 1. Deskripsi Modul

Modul ini menambahkan koneksi langsung (read-only) ke database GLPI (MariaDB) dari AI Engine. Saat ini AI Engine hanya mengakses data GLPI via REST API, yang tidak mendukung aggregate queries, JOIN antar tabel, dan analisis statistik yang dibutuhkan untuk Asset Health AI. Direct DB access memungkinkan query kompleks untuk health scoring, age distribution, ticket frequency analysis, dan warranty tracking.

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Membuat SQLAlchemy-based connector ke GLPI MariaDB dengan connection pooling
2. Menyediakan method-method query untuk data yang dibutuhkan health analysis
3. Memastikan semua operasi bersifat read-only (SELECT saja)
4. Mengintegrasikan connector dengan FastAPI lifecycle (startup/shutdown)
5. Menambahkan konfigurasi DB ke Settings dan `.env`

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | Connector berhasil koneksi ke GLPI DB dengan user read-only | Connection test |
| AC-02 | Semua query method return data yang benar | Unit test dengan test data |
| AC-03 | Connection pooling berfungsi (5 pool + 10 overflow) | Pool stats check |
| AC-04 | Pool pre_ping mendeteksi stale connections | Simulate connection drop |
| AC-05 | Connector di-init saat FastAPI startup dan dispose saat shutdown | Lifecycle test |
| AC-06 | Query parameterized — tidak ada SQL injection risk | Code review |
| AC-07 | Error handling: koneksi gagal → log error, tidak crash app | Simulate DB down |
| AC-08 | Config dari `.env` terbaca dengan benar | Config check |
| AC-09 | Connector bisa diakses dari Celery worker | Worker task test |
| AC-10 | Performance: query < 5 detik untuk tabel dengan 10.000 rows | Benchmark |

## 3. Spesifikasi Teknis

### 3.1 Arsitektur Koneksi

```
┌─────────────────────────────────────────────────────────┐
│                    AI Engine                             │
│                                                         │
│  ┌───────────────────┐    ┌───────────────────────────┐ │
│  │  FastAPI App       │    │  Celery Worker            │ │
│  │  (health endpoints)│    │  (health analysis tasks)  │ │
│  └─────────┬─────────┘    └─────────────┬─────────────┘ │
│            │                            │               │
│            └────────────┬───────────────┘               │
│                         │                               │
│              ┌──────────▼──────────┐                    │
│              │  GLPIDBConnector    │                    │
│              │  (Singleton)        │                    │
│              │  SQLAlchemy Engine  │                    │
│              │  Pool: 5 + 10       │                    │
│              └──────────┬──────────┘                    │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │ TCP 3306
                          ▼
               ┌────────────────────┐
               │  GLPI MariaDB      │
               │  User: glpi_ai_    │
               │  readonly          │
               │  Priv: SELECT ONLY │
               └────────────────────┘
```

### 3.2 File yang Dibuat/Dimodifikasi

#### File Baru

| File | Fungsi |
|------|--------|
| `app/connectors/__init__.py` | Module init, export `glpi_db`, `init_glpi_db`, `get_glpi_db` |
| `app/connectors/glpi_db_connector.py` | Class `GLPIDBConnector` dengan semua query methods |

#### File Dimodifikasi

| File | Perubahan |
|------|-----------|
| `app/config.py` | Tambah `glpi_db_*` settings |
| `app/main.py` | Tambah `init_glpi_db()` di startup, dispose di shutdown |
| `.env` / `.env.example` | Tambah `GLPI_DB_*` variables |

### 3.3 Config Settings

```python
# Ditambahkan ke app/config.py class Settings:
glpi_db_host: str = "127.0.0.1"
glpi_db_port: int = 3306
glpi_db_name: str = "glpi"
glpi_db_user: str = "glpi_readonly"
glpi_db_password: str = ""
```

### 3.4 Environment Variables

```bash
# Ditambahkan ke .env:
GLPI_DB_HOST=172.16.14.103
GLPI_DB_PORT=3306
GLPI_DB_NAME=glpi
GLPI_DB_USER=glpi_ai_readonly
GLPI_DB_PASSWORD=<disediakan_ahm>
```

### 3.5 Class: GLPIDBConnector

```python
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
from app.config import Settings
import logging

logger = logging.getLogger(__name__)


class GLPIDBConnector:
    def __init__(self, settings: Settings):
        self._engine: Engine | None = None
        self._settings = settings

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            url = (
                f"mysql+pymysql://{self._settings.glpi_db_user}"
                f":{self._settings.glpi_db_password}"
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

    # === Health Analysis Queries ===

    def get_computer_count_by_status(self) -> list[dict]:
        """Distribusi aset berdasarkan status."""
        return self.execute_query("""
            SELECT states.name AS status, COUNT(*) AS count
            FROM glpi_computers c
            LEFT JOIN glpi_states states ON states.id = c.states_id
            WHERE c.is_deleted = 0 AND c.is_template = 0
            GROUP BY c.states_id, states.name
            ORDER BY count DESC
        """)

    def get_computer_age_distribution(self) -> list[dict]:
        """Distribusi usia aset berdasarkan tanggal pembuatan."""
        return self.execute_query("""
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
        """)

    def get_ticket_frequency_by_computer(self, months: int = 6) -> list[dict]:
        """Frekuensi tiket per komputer dalam N bulan terakhir."""
        return self.execute_query("""
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
        """, {"months": months})

    def get_warranty_status(self) -> list[dict]:
        """Status garansi semua komputer."""
        return self.execute_query("""
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
        """)

    def get_computer_details_for_health(self, computer_id: int) -> dict | None:
        """Detail komputer untuk health analysis."""
        rows = self.execute_query("""
            SELECT
                c.id, c.name, c.date_creation, c.date_mod,
                c.states_id, states.name AS status_name,
                m.name AS manufacturer_name,
                ct.name AS computer_type,
                loc.name AS location_name,
                u.name AS user_name,
                os.name AS os_name
            FROM glpi_computers c
            LEFT JOIN glpi_states states ON states.id = c.states_id
            LEFT JOIN glpi_manufacturers m ON m.id = c.manufacturers_id
            LEFT JOIN glpi_computertypes ct ON ct.id = c.computertypes_id
            LEFT JOIN glpi_locations loc ON loc.id = c.locations_id
            LEFT JOIN glpi_users u ON u.id = c.users_id
            LEFT JOIN glpi_operatingsystems os ON os.id = c.operatingsystems_id
            WHERE c.id = :computer_id AND c.is_deleted = 0
        """, {"computer_id": computer_id})
        return rows[0] if rows else None

    def get_all_computer_ids(self) -> list[dict]:
        """Daftar semua ID dan nama komputer aktif."""
        return self.execute_query("""
            SELECT id, name FROM glpi_computers
            WHERE is_deleted = 0 AND is_template = 0
            ORDER BY name
        """)

    def get_computer_by_name(self, name: str) -> dict | None:
        """Cari komputer berdasarkan nama (untuk SCCM matching)."""
        rows = self.execute_query("""
            SELECT c.id, c.name, c.serial
            FROM glpi_computers c
            WHERE c.name = :name AND c.is_deleted = 0
        """, {"name": name})
        return rows[0] if rows else None

    def get_computer_serials(self) -> list[dict]:
        """Daftar hostname + serial untuk SCCM matching."""
        return self.execute_query("""
            SELECT id, name, serial
            FROM glpi_computers
            WHERE is_deleted = 0 AND is_template = 0 AND serial != ''
        """)

    # === Dashboard Queries ===

    def get_dashboard_summary(self) -> dict:
        """Ringkasan data untuk dashboard."""
        total = self.execute_query("""
            SELECT COUNT(*) AS count FROM glpi_computers
            WHERE is_deleted = 0 AND is_template = 0
        """)
        return {"total_computers": total[0]["count"] if total else 0}

    # === Utility ===

    def test_connection(self) -> dict:
        """Test koneksi dan return info."""
        try:
            result = self.execute_query("SELECT VERSION() AS version")
            return {"status": "ok", "version": result[0]["version"] if result else "unknown"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close(self):
        if self._engine:
            self._engine.dispose()
            self._engine = None
            logger.info("GLPI DB connector closed")
```

### 3.6 Module Init

```python
# app/connectors/__init__.py
from .glpi_db_connector import GLPIDBConnector, glpi_db, init_glpi_db, get_glpi_db
```

```python
# Ditambahkan ke glpi_db_connector.py bagian bawah:

glpi_db: GLPIDBConnector | None = None


def init_glpi_db(settings: Settings):
    global glpi_db
    glpi_db = GLPIDBConnector(settings)


def get_glpi_db() -> GLPIDBConnector:
    if glpi_db is None:
        raise RuntimeError("GLPI DB connector not initialized. Call init_glpi_db() first.")
    return glpi_db
```

### 3.7 FastAPI Lifecycle Integration

```python
# Modifikasi app/main.py:

from app.connectors import init_glpi_db, get_glpi_db
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # Startup
    init_glpi_db(settings)
    db_test = get_glpi_db().test_connection()
    if db_test["status"] == "ok":
        logger.info(f"GLPI DB connected: {db_test['version']}")
    else:
        logger.warning(f"GLPI DB connection failed: {db_test['message']}")
    yield
    # Shutdown
    get_glpi_db().close()

app = FastAPI(lifespan=lifespan, ...)
```

### 3.8 Health Endpoint Enhancement

```python
# Modifikasi /health endpoint untuk include DB status:

@app.get("/health")
async def health_check():
    db_status = "not_configured"
    db_version = None
    try:
        db = get_glpi_db()
        result = db.test_connection()
        db_status = result["status"]
        db_version = result.get("version")
    except RuntimeError:
        pass

    return {
        "status": "ok",
        "service": "GLPI AI Gateway",
        "version": "4.0.0",
        "ai_model": settings.ai_model,
        "glpi_db": {
            "status": db_status,
            "version": db_version,
        },
    }
```

## 4. Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│                      AI Engine                                │
│                                                              │
│  Request masuk                                                │
│       │                                                      │
│       ├── /api/health/dashboard                              │
│       │       │                                              │
│       │       ▼                                              │
│       │   get_glpi_db().get_dashboard_summary()              │
│       │   get_glpi_db().get_computer_count_by_status()       │
│       │   get_glpi_db().get_computer_age_distribution()      │
│       │       │                                              │
│       │       ▼                                              │
│       │   SQLAlchemy Engine → pymysql → GLPI MariaDB         │
│       │                                                      │
│       ├── /api/health/report/{asset_id}                      │
│       │       │                                              │
│       │       ▼                                              │
│       │   get_glpi_db().get_computer_details_for_health()    │
│       │   get_glpi_db().get_ticket_frequency_by_computer()   │
│       │   get_glpi_db().get_warranty_status()                │
│       │       │                                              │
│       │       ▼                                              │
│       │   HealthScorer.calculate_score()                     │
│       │       │                                              │
│       │       ▼                                              │
│       │   Return health report JSON                          │
│       │                                                      │
│       └── Celery Task: health.analyze_all                    │
│               │                                              │
│               ▼                                              │
│           get_glpi_db().get_all_computer_ids()               │
│           Loop: analyze_single_asset() per computer          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## 5. Query Reference

### 5.1 Daftar Query dan Tabel yang Diakses

| Query Method | Tabel GLPI | Operasi | Estimasi Rows |
|--------------|------------|---------|---------------|
| `get_computer_count_by_status` | `glpi_computers`, `glpi_states` | SELECT + GROUP BY | ~5-10 |
| `get_computer_age_distribution` | `glpi_computers` | SELECT + CASE + GROUP BY | ~4 |
| `get_ticket_frequency_by_computer` | `glpi_items_tickets`, `glpi_tickets`, `glpi_computers` | SELECT + JOIN + GROUP BY | ~100-1000 |
| `get_warranty_status` | `glpi_computers`, `glpi_contracts_items`, `glpi_contracts` | SELECT + LEFT JOIN + CASE | ~500-5000 |
| `get_computer_details_for_health` | `glpi_computers` + 6 lookup tables | SELECT + LEFT JOIN | 1 |
| `get_all_computer_ids` | `glpi_computers` | SELECT | ~500-5000 |
| `get_computer_by_name` | `glpi_computers` | SELECT WHERE | 1 |
| `get_computer_serials` | `glpi_computers` | SELECT | ~500-5000 |
| `get_dashboard_summary` | `glpi_computers` | SELECT COUNT | 1 |
| `test_connection` | (system) | SELECT VERSION | 1 |

### 5.2 Index yang Direkomendasikan

Jika query terlalu lambat, berikut index yang bisa ditambahkan ke GLPI DB:

```sql
-- Untuk get_ticket_frequency_by_computer
CREATE INDEX idx_items_tickets_itemtype_itemsid
    ON glpi_items_tickets (itemtype, items_id);

-- Untuk get_warranty_status
CREATE INDEX idx_contracts_items_itemtype_itemsid
    ON glpi_contracts_items (itemtype, items_id);
```

> **Catatan:** Index ini hanya rekomendasi. Sebelum menambahkan, koordinasi dengan DBA AHM karena bisa impact write performance.

## 6. Error Handling

| Error | Penyebab | Handling |
|-------|----------|----------|
| `OperationalError: Can't connect` | DB down, firewall, wrong credentials | Log error, return error response, don't crash |
| `OperationalError: Lost connection` | Connection timeout, DB restart | `pool_pre_ping=True` auto-detect stale connections |
| `ProgrammingError` | SQL syntax error, table not found | Log error, fix query, raise for developer attention |
| `AuthError: Access denied` | Wrong username/password | Log error, return config error message |
| `TimeoutError` | Query terlalu lambat | Set query timeout, log warning |
| `RuntimeError: Not initialized` | `get_glpi_db()` called before `init_glpi_db()` | Raise dengan clear message |

### Error Handling Pattern

```python
from sqlalchemy import exc

def safe_query(method_name: str, query: str, params: dict | None = None) -> list[dict]:
    try:
        return get_glpi_db().execute_query(query, params)
    except exc.OperationalError as e:
        logger.error(f"GLPI DB operational error in {method_name}: {e}")
        return []
    except exc.ProgrammingError as e:
        logger.error(f"GLPI DB programming error in {method_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"GLPI DB unexpected error in {method_name}: {e}")
        return []
```

## 7. Testing

### 7.1 Unit Tests

| ID | Test | Setup | Expected |
|----|------|-------|----------|
| T-01 | Connection test | Mock DB with test data | Returns version string |
| T-02 | get_computer_count_by_status | Insert test computers with states | Returns correct counts |
| T-03 | get_computer_age_distribution | Insert computers with various dates | Returns 4 age groups |
| T-04 | get_ticket_frequency_by_computer | Insert tickets linked to computers | Returns correct counts |
| T-05 | get_warranty_status | Insert contracts with various end dates | Returns correct status |
| T-06 | get_computer_details_for_health | Insert computer with all relations | Returns full detail dict |
| T-07 | get_computer_details_for_health (not found) | No computer with given ID | Returns None |
| T-08 | Connection failure | Mock DB down | Returns error dict, no crash |
| T-09 | Parameterized query | Query with params | No SQL injection possible |
| T-10 | Pool behavior | Multiple concurrent queries | Connections reused from pool |

### 7.2 Integration Test

```python
# tests/test_glpi_db_integration.py
# Hanya dijalankan jika GLPI DB accessible

import pytest
from app.connectors import init_glpi_db, get_glpi_db
from app.config import Settings

@pytest.fixture(scope="module")
def db_connector():
    settings = Settings(_env_file=".env")
    init_glpi_db(settings)
    return get_glpi_db()

def test_connection(db_connector):
    result = db_connector.test_connection()
    assert result["status"] == "ok"

def test_get_all_computer_ids(db_connector):
    result = db_connector.get_all_computer_ids()
    assert isinstance(result, list)
    if result:
        assert "id" in result[0]
        assert "name" in result[0]

def test_get_dashboard_summary(db_connector):
    result = db_connector.get_dashboard_summary()
    assert "total_computers" in result
    assert result["total_computers"] >= 0
```

## 8. Dependensi Modul Lain

| Modul | Dependensi ke Modul Ini | Detail |
|-------|------------------------|--------|
| PRD-04 (SCCM Connector) | `get_computer_by_name()`, `get_computer_serials()` | Untuk GLPI-SCCM matching |
| PRD-05 (Asset Health AI) | Semua health query methods | Data source untuk health scoring |
| PRD-06 (Health Plugin UI) | Dashboard query methods | Data untuk dashboard display |

## 9. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| DBA AHM tidak memberikan read-only access | Medium | High | Koordinasi sejak Sprint 1, sediakan SQL GRANT statement |
| Query terlalu lambat pada tabel besar | Medium | Medium | Pool pre_ping, query optimization, index rekomendasi |
| GLPI DB schema berubah saat upgrade | Low | High | Query menggunakan JOIN eksplisit, tidak SELECT * |
| pymysql tidak kompatibel dengan MariaDB version | Low | Medium | Test koneksi di awal sprint |
| Connection pool exhausted | Low | Medium | pool_size=5 + max_overflow=10, pool_recycle=3600 |

## 10. Deliverables

| Deliverable | Lokasi |
|-------------|--------|
| GLPI DB Connector class | `app/connectors/glpi_db_connector.py` |
| Module init | `app/connectors/__init__.py` |
| Config extension | `app/config.py` (extend) |
| Lifecycle integration | `app/main.py` (extend) |
| Health endpoint update | `app/main.py` (extend) |
| Unit tests | `tests/test_glpi_db_connector.py` |
| Integration tests | `tests/test_glpi_db_integration.py` |
