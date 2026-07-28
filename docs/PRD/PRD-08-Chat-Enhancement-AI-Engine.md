> **⛔ DOKUMEN INI TELAH DIPINDAHKAN**
>
> Dokumen PRD ini telah dipindahkan ke subdirektori `docs/planned/PRD/`.
>
> **Buka di:** `docs/planned/PRD/PRD-08-Chat-Enhancement-AI-Engine.md`

---

# PRD-08: Chat Enhancement — AI Engine

> **Modul:** AI Engine — SCCM-aware Chat Tools, Health-aware Chat, Multi-turn Improvement  
> **Sprint:** 11-12  
> **Prioritas:** Medium  
> **Dependensi:** PRD-04 (SCCM Connector), PRD-05 (Health AI Backend)  
> **PIC Pengembang:** Tim AI  
> **Repo:** `/home/ariel/projects/chatbot-fastapi/`

---

## 1. Deskripsi Modul

Modul ini menambahkan kemampuan SCCM dan Health-aware ke chat agent yang sudah ada, mencakup:

1. **SCCM Chat Tools** — 4 tools SCCM yang didaftarkan ke existing chat agent
2. **Health Chat Tools** — 2 tools untuk query health data via chat
3. **Multi-turn Context Improvement** — Peningkatan manajemen konteks percakapan
4. **Response Formatting Enhancement** — Format respons yang lebih kaya (tabel, badges)

## 2. Tujuan & Kriteria Sukses

### 2.1 Tujuan

1. Mendaftarkan SCCM tools ke chat agent agar pengguna bisa bertanya tentang data SCCM
2. Membuat health tools agar pengguna bisa bertanya tentang kesehatan aset via chat
3. Meningkatkan context management untuk percakapan yang lebih koheren
4. Memperbaiki format respons untuk data tabular dan rekomendasi

### 2.2 Kriteria Sukses (Acceptance Criteria)

| ID | Kriteria | Verifikasi |
|----|----------|------------|
| AC-01 | Chat agent bisa menjawab "Software apa di PC-001?" menggunakan SCCM data | Chat test |
| AC-02 | Chat agent bisa menjawab "Patch status PC-001?" menggunakan SCCM data | Chat test |
| AC-03 | Chat agent bisa menjawab "Komputer mana yang perlu diganti?" menggunakan health data | Chat test |
| AC-04 | Chat agent bisa menjawab "Kesehatan PC-001?" menggunakan health score | Chat test |
| AC-05 | Chat agent bisa membandingkan data GLPI vs SCCM | Chat test: "Bandingkan data PC-001 di GLPI dan SCCM" |
| AC-06 | Multi-turn conversation mempertahankan konteks dengan benar | Chat test: 5+ turn conversation |
| AC-07 | Respons tabular menggunakan format markdown table | Visual check |
| AC-08 | SCCM tools graceful degradation ketika SCCM tidak tersedia | Test dengan SCCM disabled |
| AC-09 | Health tools return meaningful data | Chat test |
| AC-10 | Agent tidak hallucinate data — selalu menggunakan tools | Chat test dengan pertanyaan spesifik |

## 3. Spesifikasi Teknis

### 3.1 SCCM Tools Registration

#### Modifikasi `app/tools/__init__.py`

```python
# Tambahkan import dan registration:
from app.tools.sccm_tools import (
    get_sccm_computer_detail,
    get_sccm_software_inventory,
    get_sccm_patch_status,
    compare_glpi_sccm,
)

# Tambahkan ke tool list yang dikembalikan ke agent factory
```

#### Modifikasi `app/agents/agent_factory.py`

```python
# Agent sekarang memiliki 26 tools (20 existing + 4 SCCM + 2 health)
# Update tool list dan agent backstory untuk menyebutkan kemampuan SCCM
```

### 3.2 Health Chat Tools

#### File Baru

| File | Fungsi |
|------|--------|
| `app/tools/health_tools.py` | 2 CrewAI tools untuk health data query via chat |

```python
# app/tools/health_tools.py
from crewai.tools import tool


@tool("get_asset_health_score")
def get_asset_health_score(computer_name: str) -> str:
    """Get the health score and risk category for a specific computer by name.
    Use this when user asks about the health, condition, or risk level of a computer."""
    from app.connectors.glpi_db_connector import get_glpi_db
    from app.scorers.health_scorer import HealthScorer

    glpi_db = get_glpi_db()
    rows = glpi_db.execute_query(
        "SELECT id, name FROM glpi_computers WHERE name = :name AND is_deleted = 0",
        {"name": computer_name},
    )
    if not rows:
        return f"Computer '{computer_name}' not found in GLPI database."

    computer_id = rows[0]["id"]
    computer = glpi_db.get_computer_details_for_health(computer_id)
    if not computer:
        return f"Details not available for '{computer_name}'."

    ticket_freq = glpi_db.get_ticket_frequency_by_computer(months=6)
    ticket_count = next(
        (t["ticket_count"] for t in ticket_freq if t["computer_id"] == computer_id), 0
    )

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
        sccm_system = sccm.find_by_hostname(computer_name)
        if sccm_system:
            sccm_compliance = sccm.get_patch_compliance(sccm_system["ResourceID"])
            sccm_correlation = "matched"
        else:
            sccm_correlation = "missing_in_sccm"
    except RuntimeError:
        sccm_correlation = "sccm_unavailable"

    scorer = HealthScorer()
    result = scorer.calculate_score(
        computer_data=computer,
        ticket_count=ticket_count,
        warranty_status=warranty_status,
        sccm_compliance=sccm_compliance,
        sccm_correlation=sccm_correlation,
    )

    parts = [
        f"Health Score for {computer_name}: **{result['score']}/100** ({result['risk_category']})",
        "",
        "Factors:",
    ]
    for factor_name, factor_data in result["factors"].items():
        penalty = factor_data.get("penalty", 0)
        weight = factor_data.get("weight", 0)
        parts.append(f"  - {factor_name}: penalty={penalty}, weight={weight:.0%}")

    parts.append("")
    parts.append("Recommendations:")
    for rec in result["recommendations"]:
        parts.append(f"  - {rec}")

    return "\n".join(parts)


@tool("get_at_risk_assets")
def get_at_risk_assets(risk_category: str = "Critical") -> str:
    """Get list of assets with a specific risk category.
    Use this when user asks which computers need attention or replacement.
    Risk categories: Critical, High, Medium, Low."""
    from app.connectors.glpi_db_connector import get_glpi_db
    from app.scorers.health_scorer import HealthScorer

    glpi_db = get_glpi_db()
    computers = glpi_db.get_all_computer_ids()

    scorer = HealthScorer()
    matching = []

    for comp in computers[:200]:
        computer = glpi_db.get_computer_details_for_health(comp["id"])
        if not computer:
            continue

        ticket_freq = glpi_db.get_ticket_frequency_by_computer(months=6)
        ticket_count = next(
            (t["ticket_count"] for t in ticket_freq if t["computer_id"] == comp["id"]), 0
        )

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
            matching.append({
                "name": comp["name"],
                "score": result["score"],
                "top_rec": result["recommendations"][0] if result["recommendations"] else "",
            })

    if not matching:
        return f"No assets found with risk category '{risk_category}'."

    parts = [f"Assets with **{risk_category}** risk ({len(matching)} found):", ""]
    parts.append("| Computer | Score | Top Recommendation |")
    parts.append("|----------|-------|-------------------|")
    for m in matching[:20]:
        parts.append(f"| {m['name']} | {m['score']}/100 | {m['top_rec']} |")

    if len(matching) > 20:
        parts.append(f"\n... and {len(matching) - 20} more")

    return "\n".join(parts)
```

### 3.3 Agent Backstory Update

```python
# Modifikasi app/agents/agent_factory.py — update agent backstory:

backstory = """
Anda adalah IT Support Specialist untuk sistem GLPI di AHM. Tugas Anda adalah membantu
pengguna dengan pertanyaan seputar aset IT, tiket, kontrak, supplier, dan hal teknis lainnya.

ATURAN KETAT:
1. WAJIB gunakan tools untuk mengambil data — JANGAN pernah membuat data sendiri
2. WAJIB basiskan jawaban 100% dari output tools
3. JANGAN tampilkan format internal (JSON, Thought, Action, Observation)
4. WAJIB gunakan Bahasa Indonesia
5. Jika data tidak ditemukan, katakan "Data tidak ditemukan" — JANGAN fabricate

KEMAMPUAN ANDA:
- Query data aset, tiket, kontrak, supplier dari GLPI
- Query data hardware, software, patch status dari SCCM
- Membandingkan data antara GLPI dan SCCM
- Menilai kesehatan aset (health score) dan memberikan rekomendasi
- Mencari aset yang berisiko tinggi

FORMAT RESPONS:
- Gunakan **tebal** untuk penekanan
- Gunakan markdown table untuk data tabular
- Gunakan emoji secukupnya (💻🎫📊❤️⚠️)
- Jawab singkat dan jelas
"""
```

### 3.4 Multi-turn Context Improvement

#### Modifikasi `app/agents/prompt_builder.py`

```python
# Tingkatkan context management:

# 1. Tingkatkan history window dari 4 ke 6 messages
# 2. Truncate assistant content dari 400 ke 600 chars (lebih konteks)
# 3. Tambahkan conversation summary untuk session panjang

HISTORY_WINDOW = 6
ASSISTANT_CONTENT_MAX = 600

def build_conversation_summary(history: list[dict]) -> str:
    """Buat ringkasan percakapan untuk context yang panjang."""
    if len(history) <= HISTORY_WINDOW:
        return ""

    older_messages = history[:-HISTORY_WINDOW]
    topics = set()
    for msg in older_messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").lower()
            if "komputer" in content or "computer" in content:
                topics.add("komputer/aset")
            if "tiket" in content or "ticket" in content:
                topics.add("tiket")
            if "supplier" in content:
                topics.add("supplier")
            if "kontrak" in content or "contract" in content:
                topics.add("kontrak")
            if "kesehatan" in content or "health" in content:
                topics.add("kesehatan aset")
            if "software" in content or "patch" in content:
                topics.add("software/patch")

    if topics:
        return f"Topik yang sudah dibahas sebelumnya: {', '.join(topics)}"
    return ""
```

### 3.5 Response Formatting Enhancement

#### Modifikasi `app/tools/formatters.py`

```python
# Tambahkan formatter untuk health data dan SCCM data:

def format_health_report(data: dict) -> str:
    """Format health report untuk LLM output."""
    parts = [
        f"**Health Score: {data['score']}/100** — {data['risk_category']}",
        "",
        "| Faktor | Penalty | Bobot |",
        "|--------|---------|-------|",
    ]
    for name, factor in data.get("factors", {}).items():
        parts.append(f"| {name} | {factor.get('penalty', 0)} | {factor.get('weight', 0):.0%} |")

    parts.append("")
    parts.append("**Rekomendasi:**")
    for rec in data.get("recommendations", []):
        parts.append(f"- {rec}")

    return "\n".join(parts)


def format_sccm_comparison(glpi_data: dict, sccm_data: dict, mismatches: list) -> str:
    """Format perbandingan GLPI vs SCCM."""
    if not mismatches:
        return "✅ Data GLPI dan SCCM konsisten — tidak ada perbedaan."

    parts = ["⚠️ Ditemukan perbedaan data:", "", "| Field | GLPI | SCCM |", "|-------|------|------|"]
    for m in mismatches:
        parts.append(f"| {m['field']} | {m['glpi']} | {m['sccm']} |")

    return "\n".join(parts)
```

## 4. Example Chat Interactions

### 4.1 SCCM Queries

| User Query | Tool Used | Expected Response |
|------------|-----------|-------------------|
| "Software apa di PC-001?" | `get_sccm_software_inventory` | Daftar software dari SCCM |
| "Patch status PC-001?" | `get_sccm_patch_status` | Compliance percentage |
| "Hardware detail PC-001 dari SCCM?" | `get_sccm_computer_detail` | Manufacturer, model, OS, dll |
| "Bandingkan data PC-001 di GLPI dan SCCM" | `compare_glpi_sccm` | Mismatch report atau "konsisten" |

### 4.2 Health Queries

| User Query | Tool Used | Expected Response |
|------------|-----------|-------------------|
| "Kesehatan PC-001?" | `get_asset_health_score` | Score, risk category, recommendations |
| "Komputer mana yang perlu diganti?" | `get_at_risk_assets("Critical")` | Tabel aset Critical |
| "Aset berisiko tinggi?" | `get_at_risk_assets("High")` | Tabel aset High |
| "PC mana yang patch-nya kurang?" | `get_at_risk_assets` + SCCM data | Aset dengan compliance rendah |

## 5. Testing

| ID | Test | Expected |
|----|------|----------|
| T-01 | "Software di PC-001?" | Agent menggunakan `get_sccm_software_inventory` |
| T-02 | "Patch status PC-001?" | Agent menggunakan `get_sccm_patch_status` |
| T-03 | "Kesehatan PC-001?" | Agent menggunakan `get_asset_health_score` |
| T-04 | "Komputer yang perlu diganti?" | Agent menggunakan `get_at_risk_assets` |
| T-05 | "Bandingkan PC-001 di GLPI dan SCCM" | Agent menggunakan `compare_glpi_sccm` |
| T-06 | SCCM disabled → SCCM query | Agent memberikan pesan "SCCM tidak tersedia" |
| T-07 | Multi-turn: tanya komputer → tanya detail | Context retained |
| T-08 | Multi-turn: 5+ messages | Conversation coherent |
| T-09 | Tabular response format | Markdown table rendered |
| T-10 | Agent tidak hallucinate | Semua data dari tools |

## 6. Dependensi Modul Lain

| Modul | Dependensi ke Modul Ini | Detail |
|-------|------------------------|--------|
| - | - | Modul ini adalah modul akhir untuk AI Engine |

## 7. Risiko & Mitigasi

| Risiko | Probabilitas | Impact | Mitigasi |
|--------|-------------|--------|----------|
| Agent memilih tool yang salah | Medium | Low | Tool descriptions yang jelas, prompt engineering |
| SCCM query lambat → chat timeout | Medium | Medium | Tool timeout, async execution |
| Health scoring untuk semua aset terlalu lambat | High | Medium | `get_at_risk_assets` limit ke 200 aset |
| Token limit terlampaui dengan banyak tools | Low | Medium | Tool descriptions ringkas, context truncation |

## 8. Deliverables

| Deliverable | Lokasi |
|-------------|--------|
| Health tools | `app/tools/health_tools.py` |
| Modified tools/__init__.py | `app/tools/__init__.py` |
| Modified agent_factory.py | `app/agents/agent_factory.py` |
| Modified prompt_builder.py | `app/agents/prompt_builder.py` |
| Modified formatters.py | `app/tools/formatters.py` |
