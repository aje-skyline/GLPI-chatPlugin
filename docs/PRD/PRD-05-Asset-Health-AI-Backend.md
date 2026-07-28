> **⛔ DOKUMEN INI TELAH DIPINDAHKAN**
>
> Dokumen PRD ini telah dipindahkan ke subdirektori `docs/planned/PRD/`.
>
> **Buka di:** `docs/planned/PRD/PRD-05-Asset-Health-AI-Backend.md`

---

# PRD-05: Asset Health AI — Backend

> **Modul:** AI Engine — Asset Health Analysis (Scoring, Crew, Workers, API)  
> **Sprint:** 5-6  
> **Prioritas:** High  
> **Dependensi:** PRD-01 (Docker), PRD-03 (GLPI DB Connector), PRD-04 (SCCM Connector)  
> **PIC Pengembang:** Tim AI  
> **Repo:** `/home/ariel/projects/chatbot-fastapi/`

---

## 1. Deskripsi Modul

Modul ini mengimplementasikan seluruh backend untuk Asset Health AI, mencakup:

1. **Health Scorer** — Algoritma scoring yang menghitung health score (0-100) berdasarkan 5 faktor
2. **Risk Category** — Kategorisasi aset ke Critical/High/Medium/Low
3. **Health Analysis Crew** — Multi-agent CrewAI crew untuk analisis mendalam
4. **Celery Workers** — Background tasks untuk analisis massal dan scheduled jobs
5. **API Endpoints** — REST API untuk trigger analysis, check status, get reports, dashboard data

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Mengimplementasikan health scoring algorithm dengan 5 faktor tertimbang
2. Membuat 4 CrewAI agents untuk health analysis (DataCollector, PatternAnalyzer, RiskAssessor, Recommendation)
3. Membuat Celery tasks untuk single-asset dan all-asset analysis
4. Menyediakan 5 API endpoints untuk health analysis operations
5. Menghasilkan rekomendasi actionable berdasarkan analisis

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | Health scorer menghitung score 0-100 dengan benar | Unit test dengan known inputs |
| AC-02 | Risk category sesuai score range (Critical 0-30, High 31-50, Medium 51-70, Low 71-100) | Unit test |
| AC-03 | Recommendations dihasilkan berdasarkan faktor yang bermasalah | Unit test |
| AC-04 | POST /api/health/analyze memulai Celery task dan return job_id | cURL test |
| AC-05 | GET /api/health/status/{job_id} return progress atau result | cURL test |
| AC-06 | GET /api/health/report/{asset_id} return health report synchronously | cURL test |
| AC-07 | GET /api/health/dashboard return summary data | cURL test |
| AC-08 | Celery task analyze_single_asset selesai dalam 30 detik per aset | Benchmark |
| AC-09 | Celery task analyze_all_assets memproses semua aset tanpa crash | Integration test |
| AC-10 | Health Analysis Crew menghasilkan analisis narrative | Manual test |
| AC-11 | SCCM data (patch compliance) terintegrasi dalam scoring | Test dengan SCCM data |
| AC-12 | API key authentication aktif di semua endpoints | Test tanpa API key → 401 |

## 3. Spesifikasi Teknis

### 3.1 Sub-Modul A: Health Scorer

#### File Baru

| File | Fungsi |
|------|--------|
| `app/scorers/__init__.py` | Module init |
| `app/scorers/risk_category.py` | Enum `RiskCategory` + `score_to_category()` |
| `app/scorers/health_scorer.py` | Class `HealthScorer` — scoring algorithm |

#### Risk Category

```python
# app/scorers/risk_category.py
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

#### Health Scorer Algorithm

```
Health Score = 100 - Σ(weighted penalties)

┌─────────────────────────────────────────────────────────────────┐
│  Factor                    │ Weight │ Condition              │ P │
├─────────────────────────────────────────────────────────────────┤
│  Hardware Age              │  20%   │ < 2 years             │  0│
│                            │        │ 2-4 years             │ 10│
│                            │        │ 4-6 years             │ 20│
│                            │        │ > 6 years             │ 30│
│                            │        │ No date               │ 15│
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
```

#### Class: HealthScorer

```python
# app/scorers/health_scorer.py
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
        factors["hardware_age"] = {
            "penalty": age_penalty,
            "weight": self.WEIGHTS["hardware_age"],
        }
        penalties["hardware_age"] = age_penalty * self.WEIGHTS["hardware_age"]

        ticket_penalty = self._ticket_frequency_penalty(ticket_count)
        factors["ticket_frequency"] = {
            "penalty": ticket_penalty,
            "weight": self.WEIGHTS["ticket_frequency"],
            "ticket_count": ticket_count,
        }
        penalties["ticket_frequency"] = ticket_penalty * self.WEIGHTS["ticket_frequency"]

        patch_penalty = self._patch_compliance_penalty(sccm_compliance)
        factors["patch_compliance"] = {
            "penalty": patch_penalty,
            "weight": self.WEIGHTS["patch_compliance"],
            "compliance": sccm_compliance,
        }
        penalties["patch_compliance"] = patch_penalty * self.WEIGHTS["patch_compliance"]

        warranty_penalty = self._warranty_penalty(warranty_status)
        factors["warranty_status"] = {
            "penalty": warranty_penalty,
            "weight": self.WEIGHTS["warranty_status"],
            "status": warranty_status,
        }
        penalties["warranty_status"] = warranty_penalty * self.WEIGHTS["warranty_status"]

        correlation_penalty = self._sccm_correlation_penalty(sccm_correlation)
        factors["sccm_correlation"] = {
            "penalty": correlation_penalty,
            "weight": self.WEIGHTS["sccm_correlation"],
            "status": sccm_correlation,
        }
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
            try:
                creation_date = datetime.fromisoformat(creation_date.replace(" ", "T"))
            except ValueError:
                return 15
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
        penalties = {
            "active": 0,
            "expiring_soon": 10,
            "expired": 20,
            "no_warranty": 15,
        }
        return penalties.get(status, 15)

    def _sccm_correlation_penalty(self, status: str) -> int:
        penalties = {
            "matched": 0,
            "mismatch": 10,
            "missing_in_sccm": 15,
            "missing_in_glpi": 15,
            "not_checked": 10,
            "sccm_unavailable": 10,
        }
        return penalties.get(status, 10)

    def _generate_recommendations(self, factors: dict, score: int, risk_category) -> list[str]:
        recs = []
        if factors["hardware_age"]["penalty"] >= 20:
            recs.append("[HIGH] Pertimbangkan penggantian hardware — aset sudah berusia > 4 tahun")
        if factors["ticket_frequency"].get("ticket_count", 0) > 7:
            recs.append("[HIGH] Investigasi tingginya frekuensi tiket — kemungkinan ada masalah recurring")
        elif factors["ticket_frequency"].get("ticket_count", 0) > 3:
            recs.append("[MEDIUM] Monitor frekuensi tiket — ada tren peningkatan masalah")
        if factors["patch_compliance"].get("compliance", {}).get("compliance_pct", 100) < 80:
            recs.append("[URGENT] Patch compliance rendah — perlu update keamanan segera")
        elif factors["patch_compliance"].get("compliance", {}).get("compliance_pct", 100) < 95:
            recs.append("[MEDIUM] Patch compliance perlu ditingkatkan")
        if factors["warranty_status"]["status"] == "expired":
            recs.append("[HIGH] Garansi sudah expired — pertimbangkan perpanjangan atau penggantian")
        elif factors["warranty_status"]["status"] == "no_warranty":
            recs.append("[MEDIUM] Tidak ada garansi — pertimbangkan asuransi atau kontrak maintenance")
        elif factors["warranty_status"]["status"] == "expiring_soon":
            recs.append("[LOW] Garansi segera berakhir — perlu keputusan perpanjangan")
        if factors["sccm_correlation"]["status"] == "missing_in_sccm":
            recs.append("[HIGH] Aset tidak terdaftar di SCCM — perlu verifikasi dan pendaftaran ulang")
        elif factors["sccm_correlation"]["status"] == "mismatch":
            recs.append("[MEDIUM] Data GLPI dan SCCM tidak konsisten — perlu rekonsiliasi data")
        if score > 70 and not recs:
            recs.append("[INFO] Aset dalam kondisi baik — tidak ada tindakan diperlukan saat ini")
        if not recs:
            recs.append("[LOW] Lakukan penilaian lebih detail untuk aset ini")
        return recs
```

### 3.2 Sub-Modul B: Health Analysis Crew

#### File Baru

| File | Fungsi |
|------|--------|
| `app/crews/__init__.py` | Module init |
| `app/crews/health_crew.py` | `create_health_crew()` — CrewAI Crew factory |
| `app/agents/data_collector_agent.py` | Agent: data collection dari GLPI + SCCM |
| `app/agents/pattern_analyzer_agent.py` | Agent: analisis pola dan anomali |
| `app/agents/risk_assessor_agent.py` | Agent: penilaian risiko |
| `app/agents/recommendation_agent.py` | Agent: rekomendasi tindakan |
| `app/tasks/__init__.py` | Module init |
| `app/tasks/collect_data_task.py` | Task: pengumpulan data |
| `app/tasks/analyze_patterns_task.py` | Task: analisis pola |
| `app/tasks/assess_risk_task.py` | Task: penilaian risiko |
| `app/tasks/generate_recommendations_task.py` | Task: rekomendasi |

#### Crew Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   HEALTH ANALYSIS CREW                          │
│                   Process: Sequential                           │
│                                                                 │
│  Step 1: DataCollectorAgent                                     │
│  ├── Tools: get_computer_detail, get_computers_by_status,       │
│  │          get_sccm_computer_detail, get_sccm_software_inventory│
│  │          get_sccm_patch_status                                │
│  └── Output: Collected data summary                             │
│           │                                                     │
│           ▼                                                     │
│  Step 2: PatternAnalyzerAgent                                   │
│  ├── Tools: (none — analyzes provided data)                     │
│  └── Output: Pattern analysis report                            │
│           │                                                     │
│           ▼                                                     │
│  Step 3: RiskAssessorAgent                                      │
│  ├── Tools: (none — calculates based on analysis)               │
│  └── Output: Risk assessment with scores                        │
│           │                                                     │
│           ▼                                                     │
│  Step 4: RecommendationAgent                                    │
│  ├── Tools: (none — generates recommendations)                  │
│  └── Output: Prioritized action recommendations                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Sub-Modul C: Celery Workers

#### File Baru/Dimodifikasi

| File | Fungsi |
|------|--------|
| `app/workers/health_worker.py` | Celery tasks: `analyze_single_asset`, `analyze_all_assets` |

#### Task: analyze_single_asset

```python
@celery_app.task(bind=True, name="health.analyze_single")
def analyze_single_asset(self, computer_id: int) -> dict:
    """Analisis kesehatan satu aset secara asynchronous."""
    from app.connectors.glpi_db_connector import get_glpi_db
    from app.scorers.health_scorer import HealthScorer

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
    warranty_status = next(
        (w["warranty_status"] for w in warranty_data if w["computer_id"] == computer_id),
        "no_warranty",
    )

    sccm_compliance = None
    sccm_correlation = "not_checked"
    try:
        from app.connectors.sccm_connector import get_sccm_db
        sccm = get_sccm_db()
        sccm_system = sccm.find_by_hostname(glpi_data.get("name", ""))
        if sccm_system:
            sccm_compliance = sccm.get_patch_compliance(sccm_system["ResourceID"])
            sccm_correlation = "matched"
        else:
            sccm_correlation = "missing_in_sccm"
    except RuntimeError:
        sccm_correlation = "sccm_unavailable"
    except Exception as e:
        logger.warning(f"SCCM lookup failed for computer {computer_id}: {e}")
        sccm_correlation = "sccm_unavailable"

    health_result = scorer.calculate_score(
        computer_data=glpi_data,
        ticket_count=ticket_count,
        warranty_status=warranty_status,
        sccm_compliance=sccm_compliance,
        sccm_correlation=sccm_correlation,
    )

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
```

#### Task: analyze_all_assets

```python
@celery_app.task(bind=True, name="health.analyze_all")
def analyze_all_assets(self) -> dict:
    """Analisis kesehatan semua aset secara asynchronous."""
    from app.connectors.glpi_db_connector import get_glpi_db

    glpi_db = get_glpi_db()
    computers = glpi_db.get_all_computer_ids()

    total = len(computers)
    results = []
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "error": 0}

    for i, comp in enumerate(computers):
        self.update_state(state="PROGRESS", meta={
            "step": "analyzing",
            "current": i + 1,
            "total": total,
            "current_computer": comp["name"],
            "progress_pct": round((i + 1) / total * 100, 1),
        })
        try:
            result = analyze_single_asset(comp["id"])
            results.append(result)
            category = result.get("risk_category", "error").lower()
            if category in summary:
                summary[category] += 1
        except Exception as e:
            logger.error(f"Error analyzing computer {comp['id']}: {e}")
            results.append({"computer_id": comp["id"], "computer_name": comp["name"], "status": "error", "message": str(e)})
            summary["error"] += 1

    return {
        "status": "completed",
        "total_analyzed": len(results),
        "summary": summary,
        "results": results,
    }
```

### 3.4 Sub-Modul D: API Endpoints

#### Endpoints

| Method | Path | Auth | Deskripsi |
|--------|------|------|-----------|
| POST | `/api/health/analyze` | Bearer | Trigger analysis (single atau all) |
| GET | `/api/health/status/{job_id}` | None | Check job status/progress |
| GET | `/api/health/report/{asset_id}` | None | Synchronous single report |
| GET | `/api/health/dashboard` | None | Dashboard summary data |
| POST | `/api/health/correlate` | Bearer | Trigger GLPI-SCCM correlation |

#### Request/Response Models

```python
# app/models/health.py
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    computer_id: int | None = None
    analyze_all: bool = False


class HealthReportResponse(BaseModel):
    computer_id: int
    computer_name: str
    health_score: int
    risk_category: str
    factors: dict
    recommendations: list[str]
    sccm_correlation: str | None = None


class DashboardResponse(BaseModel):
    total_computers: int
    status_distribution: list[dict]
    age_distribution: list[dict]
    warranty_summary: dict
    risk_summary: dict | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: dict | None = None
    result: dict | None = None
    error: str | None = None
```

#### Implementation

```python
# app/api/routes/health.py (full implementation)
from fastapi import APIRouter, HTTPException, Header
from celery.result import AsyncResult
from app.workers.health_worker import analyze_single_asset, analyze_all_assets, correlate_glpi_sccm
from app.models.health import AnalyzeRequest, JobStatusResponse
from app.config import Settings

router = APIRouter()
settings = Settings()


def verify_api_key(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    token = authorization[7:]
    if token != settings.gateway_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/analyze")
async def trigger_analysis(request: AnalyzeRequest, authorization: str | None = Header(None)):
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

    sccm_compliance = None
    sccm_correlation = "not_checked"
    try:
        from app.connectors.sccm_connector import get_sccm_db
        sccm = get_sccm_db()
        sccm_system = sccm.find_by_hostname(computer.get("name", ""))
        if sccm_system:
            sccm_compliance = sccm.get_patch_compliance(sccm_system["ResourceID"])
            sccm_correlation = "matched"
        else:
            sccm_correlation = "missing_in_sccm"
    except RuntimeError:
        sccm_correlation = "sccm_unavailable"

    scorer = HealthScorer()
    health_result = scorer.calculate_score(
        computer_data=computer,
        ticket_count=ticket_count,
        warranty_status=warranty_status,
        sccm_compliance=sccm_compliance,
        sccm_correlation=sccm_correlation,
    )

    return {
        "computer_id": asset_id,
        "computer_name": computer.get("name"),
        "health_score": health_result["score"],
        "risk_category": health_result["risk_category"],
        "factors": health_result["factors"],
        "recommendations": health_result["recommendations"],
        "sccm_correlation": sccm_correlation,
    }


@router.get("/dashboard")
async def get_dashboard():
    from app.connectors.glpi_db_connector import get_glpi_db

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

## 4. Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Health Analysis Flow                              │
│                                                                      │
│  A. Synchronous (GET /api/health/report/{asset_id})                  │
│                                                                      │
│     Request → GLPIDBConnector.get_computer_details_for_health()      │
│             → GLPIDBConnector.get_ticket_frequency_by_computer()     │
│             → GLPIDBConnector.get_warranty_status()                  │
│             → SCCMConnector.find_by_hostname() (if available)        │
│             → SCCMConnector.get_patch_compliance() (if matched)      │
│             → HealthScorer.calculate_score()                         │
│             → Response JSON                                          │
│                                                                      │
│  B. Asynchronous (POST /api/health/analyze)                          │
│                                                                      │
│     Request → Celery task queued in Redis                            │
│             → Worker picks up task                                    │
│             → Same data collection as A                               │
│             → HealthScorer.calculate_score()                         │
│             → Result stored in Redis                                  │
│             → Client polls GET /api/health/status/{job_id}           │
│                                                                      │
│  C. Dashboard (GET /api/health/dashboard)                            │
│                                                                      │
│     Request → GLPIDBConnector.get_computer_count_by_status()         │
│             → GLPIDBConnector.get_computer_age_distribution()        │
│             → GLPIDBConnector.get_warranty_status()                  │
│             → Aggregate and return                                    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

## 5. Testing

| ID | Test | Expected |
|----|------|----------|
| T-01 | HealthScorer: healthy asset (new, 0 tickets, warranty active, SCCM matched, 98% compliance) | Score ≥ 85, Low |
| T-02 | HealthScorer: critical asset (old, 10 tickets, warranty expired, missing in SCCM, 40% compliance) | Score ≤ 30, Critical |
| T-03 | HealthScorer: no SCCM data | Score calculated with sccm penalty=15 |
| T-04 | HealthScorer: no creation date | Age penalty=15 |
| T-05 | RiskCategory: boundary values (30, 31, 50, 51, 70, 71) | Correct categories |
| T-06 | POST /api/health/analyze with computer_id | Returns job_id |
| T-07 | GET /api/health/status/{job_id} while running | Returns PROGRESS with step info |
| T-08 | GET /api/health/status/{job_id} after completion | Returns SUCCESS with result |
| T-09 | GET /api/health/report/{valid_id} | Returns health report |
| T-10 | GET /api/health/report/{invalid_id} | Returns 404 |
| T-11 | GET /api/health/dashboard | Returns summary data |
| T-12 | POST /api/health/analyze without auth | Returns 401 |
| T-13 | POST /api/health/analyze without computer_id or analyze_all | Returns 400 |
| T-14 | Celery: analyze_all_assets with 10 computers | All 10 analyzed, summary correct |
| T-15 | HealthScorer: recommendations generated for each risk factor | Correct priority tags |

## 6. Dependensi Modul Lain

| Modul | Dependensi ke Modul Ini | Detail |
|-------|------------------------|--------|
| PRD-06 (Health Plugin UI) | API endpoints, dashboard data | UI memanggil endpoints ini |
| PRD-08 (Chat Enhancement) | Health tools, scorer | Chat agent bisa query health data |

## 7. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| Scoring algorithm tidak sesuai kebutuhan bisnis | Medium | Medium | Tunable weights via config, UAT feedback loop |
| Celery task timeout pada aset sangat banyak | Medium | Medium | `task_time_limit=600`, batch processing |
| SCCM data tidak tersedia | Medium | Low | Graceful degradation, penalty=15 untuk no data |
| Dashboard query lambat (tabel besar) | Low | Medium | Caching di Redis (TTL 5 min), query optimization |
| CrewAI crew terlalu lambat untuk real-time | High | Low | Crew hanya untuk deep analysis, scorer untuk quick report |

## 8. Deliverables

| Deliverable | Lokasi |
|-------------|--------|
| Risk Category module | `app/scorers/risk_category.py` |
| Health Scorer | `app/scorers/health_scorer.py` |
| Health Crew | `app/crews/health_crew.py` |
| 4 Agent definitions | `app/agents/data_collector_agent.py`, `pattern_analyzer_agent.py`, `risk_assessor_agent.py`, `recommendation_agent.py` |
| 4 Task definitions | `app/tasks/collect_data_task.py`, `analyze_patterns_task.py`, `assess_risk_task.py`, `generate_recommendations_task.py` |
| Celery worker tasks | `app/workers/health_worker.py` |
| Pydantic models | `app/models/health.py` |
| Health API routes | `app/api/routes/health.py` |
| Unit tests | `tests/test_health_scorer.py`, `tests/test_health_api.py` |

---

## 8. 🔄 Alignment Notes untuk PRD-04 SCCM Integration

### 8.1 Perubahan yang Perlu Diterapkan

| Area | Sebelumnya | Sesudah (Align with PRD-04) |
|------|------------|------------------------------|
| **Correlation Endpoint** | `POST /api/health/correlate` di PRD-05 §3.5 | **Pindah ke PRD-04** → `POST /v1/health/correlate` dengan `GLPI_PLUGIN_API_KEY`. PRD-05 harus *remove* endpoint ini dan referensi ke `health_worker.py` → `correlate_glpi_sccm` |
| **SCCM Data Collection** | DataCollectorAgent langsung panggil `SCCMConnector` | DataCollectorAgent harus _via_ 🖥️ **SCCM Infrastructure Specialist Agent** (ADR-05) atau melalui `SCCMConnector` yang sudah ada di PRD-04 |
| **Auth Key** | `verify_api_key(authorization)` di correlation endpoint | Pindah ke dual auth: chat → `GATEWAY_API_KEY`, korelasi → `GLPI_PLUGIN_API_KEY` |
| **Patch Compliance Data** | Langsung dari `SCCMConnector.get_patch_compliance()` | Tetap sama — PRD-04 connector reuse, tidak perlu duplikasi |
| **SCCM Correlation Status** | Field `sccm_correlation` di health result → status string | Update dengan `match_confidence` + `match_method` dari `AssetMappingResult` PRD-04 |

### 8.2 File Conflict Resolution

| File Konflik | PRD-04 (Baru) | PRD-05 (Eksisting) | Resolusi |
|-------------|---------------|---------------------|----------|
| `app/workers/health_worker.py` | Correlation task `health.correlate_glpi_sccm` | Health score analysis task `health.analyze_single` / `health.analyze_all` | ✅ **Coexist**: PRD-04 = korelasi; PRD-05 = health scoring. Beda task name |
| `app/api/routes/health.py` | `/v1/health/correlate/*` endpoints | `/api/health/*` endpoints | ✅ **Coexist** di file berbeda: `app/api/routes/health.py` (PRD-04) vs `app/api/routes/health_analysis.py` (PRD-05) |
| `app/config.py` | `sccm_db_*` fields (baru) | Tidak ada conflict — PRD-05 reuse dari settings | ✅ Natural reuse |
| `tests/*` | `test_sccm_*` (baru) | `test_health_*` (eksisting) | ✅ Natural separation |

### 8.3 Dependensi Update

```
PRD-05 → PRD-04
    └─ SCCMConnector (for patch compliance data)
    └─ AssetCorrelator (for sccm_correlation status in health scoring)
    └─ SCCM Infrastructure Specialist Agent (for data collection via CrewAI)

PRD-04 → PRD-05
    └─ Tidak ada (PRD-04 adalah fondasi, tidak tergantung PRD-05)
```
