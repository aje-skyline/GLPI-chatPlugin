# Pre-Sprint Checklist

> **Versi:** 1.0  
> **Tujuan:** Daftar hal yang harus ready sebelum setiap sprint dimulai  
> **Penggunaan:** Review checklist ini sebelum Go/No-Go decision per sprint

---

## Cara Menggunakan

Setiap sprint memiliki 3 kategori checklist:

| Kategori | Arti | PIC |
|----------|------|-----|
| **Pengembang** | Hal yang harus disiapkan oleh tim pengembang | Tim AI |
| **AHM** | Hal yang harus disediakan/dikoordinasikan oleh AHM | AHM IT teams |
| **Infrastruktur** | Hal yang harus ready di level server/network | Infra + Pengembang |

**Go/No-Go Rule:**
- ✅ = Ready
- 🔲 = Belum ready
- ❌ = Tidak bisa disediakan (blocker)

Sprint boleh dimulai jika **semua item dengan prioritas HIGH** sudah ✅. Item MEDIUM boleh dikerjakan selama sprint berjalan.

---

## SPRINT 1-2: Foundation & Docker

### Pengembang

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Blueprint & PRD docs sudah dibaca dan dipahami | HIGH | ✅ | Sudah ada di docs/ |
| 2 | API Contract sudah dipahami | HIGH | ✅ | docs/API-CONTRACT.md |
| 3 | Dev environment guide sudah dibaca | HIGH | ✅ | docs/DEV-ENVIRONMENT.md |
| 4 | SSH access ke server 141 terverifikasi | HIGH | 🔲 | Test: `ssh <user>@172.16.14.141` |
| 5 | SSH access ke server 103 terverifikasi | HIGH | 🔲 | Test: `ssh <user>@172.16.14.103` |
| 6 | Git repo AI Engine sudah ada dan terupdate | HIGH | ✅ | /home/ariel/projects/chatbot-fastapi/ |
| 7 | Backup plugin chatbot di server 103 | HIGH | 🔲 | `cp -r chatbot chatbot.bak.$(date +%Y%m%d)` |
| 8 | Backup DB plugin di server 103 | MEDIUM | 🔲 | mysqldump glpi plugin tables |
| 9 | Code editor / IDE siap (VS Code Remote SSH) | MEDIUM | 🔲 | |
| 10 | cURL / Postman tersedia untuk API testing | LOW | 🔲 | |

### AHM

| # | Item | Prioritas | Status | PIC AHM | Deadline |
|---|------|-----------|--------|---------|----------|
| 1 | Server 141: Docker CE terinstall | HIGH | 🔲 | Server Admin | Sebelum sprint |
| 2 | Server 141: User punya akses Docker group | HIGH | 🔲 | Server Admin | Sebelum sprint |
| 3 | GLPI DB read-only account (`glpi_ai_readonly`) | HIGH | 🔲 | DBA | Minggu 1 |
| 4 | GLPI DB credentials diberikan ke pengembang | HIGH | 🔲 | DBA | Minggu 1 |
| 5 | Firewall: 141 → 103 port 3306 dibuka | HIGH | 🔲 | Network Admin | Minggu 1 |
| 6 | Firewall: 103 → 141 port 8000 dibuka | HIGH | 🔲 | Network Admin | Minggu 1 |
| 7 | IP address alokasi untuk server baru (production) | MEDIUM | 🔲 | Network Admin | Minggu 2 |
| 8 | DNS entry untuk AI Engine (opsional) | LOW | 🔲 | Network Admin | Minggu 2 |

### Infrastruktur

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Server 141: port 8000 free (uvicorn existing distop) | HIGH | 🔲 | `lsof -i :8000` |
| 2 | Server 141: Docker daemon running | HIGH | 🔲 | `docker info` |
| 3 | Server 141: disk space ≥ 10 GB untuk Docker images | MEDIUM | 🔲 | `df -h` |
| 4 | Konektivitas 141 → AI Gateway (443) | HIGH | ✅ | Sudah berjalan saat ini |
| 5 | Konektivitas 141 → GLPI REST API (443) | HIGH | ✅ | Sudah berjalan saat ini |

### Go/No-Go Decision

- [ ] **GO** — Semua HIGH items ✅ → Mulai Sprint 1-2
- [ ] **CONDITIONAL** — Beberapa HIGH items 🔲 tapi ada workaround → Mulai dengan catatan
- [ ] **NO-GO** — Critical HIGH items ❌ → Tunda sampai resolved

**Workaround jika AHM items belum ready:**
- GLPI DB account belum ada → Kerjakan Docker + Config Page dulu, DB connector nanti
- Firewall belum dibuka → Kerjakan local development dulu, integration test nanti

---

## SPRINT 3-4: SCCM Connector & Data Layer

### Pengembang

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Sprint 1-2 completed dan verified | HIGH | 🔲 | Semua AC PRD-01/02/03 terpenuhi |
| 2 | GLPI DB connector berfungsi (dari Sprint 1-2) | HIGH | 🔲 | `get_glpi_db().test_connection()` return ok |
| 3 | Celery + Redis berjalan di Docker | HIGH | 🔲 | `celery inspect ping` return pong |
| 4 | Health API placeholder endpoints ada | MEDIUM | 🔲 | Dari Sprint 1-2 refactor |
| 5 | pymssql terinstall di Docker worker image | HIGH | 🔲 | Dockerfile.worker punya freetds-dev |

### AHM

| # | Item | Prioritas | Status | PIC AHM | Deadline |
|---|------|-----------|--------|---------|----------|
| 1 | SCCM DB read-only account (`sccm_ai_readonly`) | HIGH | 🔲 | DBA + SCCM Admin | Sebelum sprint |
| 2 | SCCM DB credentials diberikan ke pengembang | HIGH | 🔲 | DBA | Sebelum sprint |
| 3 | SCCM info: 8 pertanyaan di REQUIREMENT-AHM.md dijawab | HIGH | 🔲 | SCCM Admin | Sebelum sprint |
| 4 | Firewall: 141 → SCCM DB port 1433 dibuka | HIGH | 🔲 | Network Admin | Sebelum sprint |
| 5 | Konfirmasi: SCCM SQL Server TLS encryption? | MEDIUM | 🔲 | DBA | Sebelum sprint |
| 6 | Konfirmasi: SCCM maintenance window | LOW | 🔲 | SCCM Admin | Minggu 1 |

### Infrastruktur

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Konektivitas 141 → SCCM SQL Server (1433) | HIGH | 🔲 | Test dari 141: `tsql -H <sccm> -p 1433` |
| 2 | SCCM views (v_R_System, dll) accessible oleh read-only user | HIGH | 🔲 | Test query manual |

### Go/No-Go Decision

- [ ] **GO** — Semua HIGH items ✅
- [ ] **CONDITIONAL** — SCCM belum ready → Kerjakan normalizer + correlator dengan mock data, SCCM connector nanti
- [ ] **NO-GO** — Sprint 1-2 belum selesai

**Workaround jika SCCM belum ready:**
- Kerjakan normalizer + correlator logic dengan mock SCCM data
- Kerjakan SCCM tools dengan mock responses
- Integrate SCCM connector ketika akses sudah tersedia

---

## SPRINT 5-6: Asset Health AI — Backend

### Pengembang

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Sprint 3-4 completed | HIGH | 🔲 | |
| 2 | GLPI DB connector berfungsi | HIGH | 🔲 | |
| 3 | SCCM connector berfungsi ATAU mock mode siap | HIGH | 🔲 | |
| 4 | Celery worker berjalan | HIGH | 🔲 | |
| 5 | Health API routes placeholder ada | MEDIUM | 🔲 | |

### AHM

| # | Item | Prioritas | Status | PIC AHM | Catatan |
|---|------|-----------|--------|---------|---------|
| 1 | Tidak ada kebutuhan baru dari AHM | — | — | — | Semua sudah disiapkan di Sprint 1-4 |

### Infrastruktur

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Celery worker container running | HIGH | 🔲 | |
| 2 | Redis accessible dari worker | HIGH | 🔲 | |
| 3 | GLPI DB accessible dari worker | HIGH | 🔲 | Worker butuh koneksi DB |

### Go/No-Go Decision

- [ ] **GO** — Sprint 3-4 completed + Celery running
- [ ] **NO-GO** — Celery/Redis belum berjalan

---

## SPRINT 7-8: Asset Health AI — GLPI Plugin UI

### Pengembang

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Sprint 5-6 completed | HIGH | 🔲 | |
| 2 | Health API endpoints berfungsi | HIGH | 🔲 | /api/health/* semua OK |
| 3 | Dashboard data return dari API | HIGH | 🔲 | GET /api/health/dashboard OK |
| 4 | Health report return dari API | HIGH | 🔲 | GET /api/health/report/{id} OK |
| 5 | Plugin Config Page berfungsi (dari Sprint 1-2) | HIGH | 🔲 | |

### AHM

| # | Item | Prioritas | Status | PIC AHM | Catatan |
|---|------|-----------|--------|---------|---------|
| 1 | Tidak ada kebutuhan baru | — | — | — | |

### Infrastruktur

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | GLPI server bisa reach AI Engine (port 8000) | HIGH | 🔲 | Test dari 103: curl 141:8000/health |

### Go/No-Go Decision

- [ ] **GO** — Sprint 5-6 completed + API endpoints verified
- [ ] **NO-GO** — API endpoints belum berfungsi

---

## SPRINT 9-10: Chat Enhancement — Plugin Refactor

### Pengembang

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Sprint 7-8 completed | HIGH | 🔲 | |
| 2 | Dashboard UI berfungsi | MEDIUM | 🔲 | |
| 3 | Audit class sudah ada (dari Sprint 7-8) | HIGH | 🔲 | |
| 4 | Rights sudah terdaftar (dari Sprint 7-8) | HIGH | 🔲 | |

### AHM

| # | Item | Prioritas | Status | PIC AHM | Catatan |
|---|------|-----------|--------|---------|---------|
| 1 | Tidak ada kebutuhan baru | — | — | — | |

### Go/No-Go Decision

- [ ] **GO** — Sprint 7-8 completed
- [ ] **NO-GO** — Sprint 7-8 belum selesai

---

## SPRINT 11-12: Chat Enhancement — AI Engine

### Pengembang

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Sprint 9-10 completed | HIGH | 🔲 | |
| 2 | SCCM tools terdaftar di agent (dari Sprint 3-4) | HIGH | 🔲 | |
| 3 | Health scorer berfungsi (dari Sprint 5-6) | HIGH | 🔲 | |

### AHM

| # | Item | Prioritas | Status | PIC AHM | Catatan |
|---|------|-----------|--------|---------|---------|
| 1 | Tidak ada kebutuhan baru | — | — | — | |

### Go/No-Go Decision

- [ ] **GO** — Sprint 9-10 completed + SCCM/Health tools available
- [ ] **NO-GO** — Core tools belum terdaftar

---

## SPRINT 13-14: Testing, Security & Deployment

### Pengembang

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Sprint 11-12 completed | HIGH | 🔲 | |
| 2 | Semua fitur berfungsi end-to-end | HIGH | 🔲 | |
| 3 | Test suite sudah ada (minimal basic) | HIGH | 🔲 | |
| 4 | Documentation drafts sudah ada | MEDIUM | 🔲 | |

### AHM

| # | Item | Prioritas | Status | PIC AHM | Deadline |
|---|------|-----------|--------|---------|----------|
| 1 | Security review / approval | HIGH | 🔲 | Security Officer | Minggu 25 |
| 2 | UAT participants ditunjuk (3+ orang) | HIGH | 🔲 | Business Owner | Minggu 25 |
| 3 | Production server siap (jika bukan 141) | HIGH | 🔲 | Server Admin | Minggu 27 |
| 4 | Go-live approval | HIGH | 🔲 | Management | Minggu 28 |
| 5 | Production firewall rules dibuka | HIGH | 🔲 | Network Admin | Minggu 27 |
| 6 | Production DB accounts aktif | HIGH | 🔲 | DBA | Minggu 27 |

### Infrastruktur

| # | Item | Prioritas | Status | Catatan |
|---|------|-----------|--------|---------|
| 1 | Production environment siap | HIGH | 🔲 | Server + Docker + Redis |
| 2 | Production .env dikonfigurasi | HIGH | 🔲 | |
| 3 | Production GLPI plugin terinstall | HIGH | 🔲 | |
| 4 | Backup database GLPI sebelum go-live | HIGH | 🔲 | |

### Go/No-Go Decision

- [ ] **GO** — Semua fitur tested + AHM approvals obtained
- [ ] **CONDITIONAL** — Minor issues found, go-live dengan known issues
- [ ] **NO-GO** — Critical issues found atau AHM belum approve

---

## AHM Dependency Timeline

Ringkasan kapan setiap kebutuhan AHM diperlukan:

```
Minggu 1  ──── Sprint 1-2 start
  ├── 🔴 HIGH: Docker di server 141
  ├── 🔴 HIGH: GLPI DB read-only account
  ├── 🔴 HIGH: Firewall rules (141↔103)
  └── 🟡 MEDIUM: IP address alokasi

Minggu 5  ──── Sprint 3-4 start
  ├── 🔴 HIGH: SCCM DB read-only account
  ├── 🔴 HIGH: SCCM info (8 pertanyaan)
  └── 🔴 HIGH: Firewall 141 → SCCM (1433)

Minggu 9-20 ── Sprint 5-12
  └── ⚪ Tidak ada kebutuhan baru dari AHM

Minggu 25 ──── Sprint 13-14 start
  ├── 🔴 HIGH: Security review
  ├── 🔴 HIGH: UAT participants
  └── 🟡 MEDIUM: Production server

Minggu 27 ──── Deployment
  ├── 🔴 HIGH: Production firewall rules
  ├── 🔴 HIGH: Production DB accounts
  └── 🔴 HIGH: Backup database

Minggu 28 ──── Go-Live
  └── 🔴 HIGH: Go-live approval
```

**Legenda:** 🔴 = Blocker jika tidak ready, 🟡 = Bisa dikerjakan selama sprint, ⚪ = Tidak diperlukan

---

## Action Items untuk Kickoff Meeting

Sebelum Sprint 1 dimulai, perlu diadakan kickoff meeting dengan AHM untuk:

| # | Agenda | Output yang Diharapkan |
|---|--------|----------------------|
| 1 | Presentasi REQUIREMENT-AHM.md | AHM memahami kebutuhan |
| 2 | Konfirmasi timeline | AHM setuju dengan timeline |
| 3 | Tunjuk PIC per kebutuhan | Nama PIC untuk setiap item |
| 4 | Tentukan SLA respons | Berapa lama setiap item bisa disediakan |
| 5 | Tentukan SPOC (Single Point of Contact) | 1 orang dari AHM untuk koordinasi |
| 6 | Agree on communication channel | Email / chat / ticketing system |
| 7 | Schedule check-in frequency | Weekly / bi-weekly sync |
| 8 | Discuss SCCM access options | Preliminary info tentang SCCM setup |
