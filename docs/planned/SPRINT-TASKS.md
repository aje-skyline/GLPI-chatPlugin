# Sprint Task Breakdown

> **Versi:** 1.0  
> **Format:** Structured Table — ID, Title, Description, Acceptance Criteria, Estimate, Dependencies  
> **Estimasi:** Dalam jam kerja (1 hari = 8 jam)

---

## SPRINT 1-2: Foundation & Docker

**Durasi:** 4 minggu (20 hari kerja)  
**Tujuan:** Docker environment, Config Page, GLPI DB Connector, FastAPI refactor

### PRD-01: Docker & Infrastructure

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| D-01 | Install Docker di server 141 | Install Docker CE + Compose v2 di 172.16.14.141, tambah user ke docker group | `docker --version` dan `docker compose version` return versi valid | 2h | — |
| D-02 | Stop uvicorn existing | Stop service uvicorn yang berjalan tanpa Docker di 141, verifikasi port 8000 free | `lsof -i :8000` return kosong | 0.5h | D-01 |
| D-03 | Buat Dockerfile | Buat `docker/Dockerfile` untuk FastAPI app (python:3.12-slim, uv, pymysql) | `docker build` berhasil tanpa error | 2h | — |
| D-04 | Buat Dockerfile.worker | Buat `docker/Dockerfile.worker` untuk Celery (tambah freetds-dev untuk pymssql) | `docker build` berhasil tanpa error | 1h | — |
| D-05 | Buat docker-compose.yml | Buat `docker/docker-compose.yml` dengan 4 service: ai-engine, celery-worker, celery-beat, redis | `docker compose up -d` → 4 container running | 3h | D-03, D-04 |
| D-06 | Buat .dockerignore | Buat `docker/.dockerignore` exclude .venv, .git, __pycache__, dll | Build context tidak include file tidak perlu | 0.5h | — |
| D-07 | Buat Celery app placeholder | Buat `app/workers/__init__.py` dan `app/workers/celery_app.py` dengan config dasar | Worker bisa connect ke Redis, `celery inspect ping` return pong | 2h | D-05 |
| D-08 | Tambah Redis config | Tambah `redis_host` dan `redis_port` ke `app/config.py` dan `.env` | Settings terbaca dari .env | 0.5h | — |
| D-09 | Update .env untuk Docker | Tambah `REDIS_HOST=redis`, `AI_ENGINE_PORT=8000` ke .env dan .env.example | Config values terbaca oleh containers | 0.5h | D-05 |
| D-10 | Buat smoke test script | Buat `docker/smoke-test.sh` untuk validasi cepat setelah docker-compose up | Script return PASS untuk semua 5 checks | 1h | D-05 |
| D-11 | Test Docker deployment end-to-end | Build, up, test semua service, test chat endpoint | Chat endpoint berfungsi sama seperti sebelum Docker | 3h | D-05, D-07 |
| D-12 | Buat docker-compose.dev.yml | Override untuk development: volume mount + hot-reload | Edit source → auto-restart tanpa rebuild | 1h | D-05 |

**Subtotal PRD-01: 17 jam**

### PRD-02: GLPI Plugin Config Page

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| C-01 | Tambah config table di hook.php | Tambah CREATE TABLE `glpi_plugin_chatbot_config` + INSERT default values di `plugin_chatbot_install()` | Install plugin → tabel terbuat dengan 10 default rows | 2h | — |
| C-02 | Tambah DROP TABLE di uninstall | Tambah DROP TABLE `glpi_plugin_chatbot_config` di `plugin_chatbot_uninstall()` | Uninstall → tabel terhapus | 0.5h | C-01 |
| C-03 | Buat PluginChatbotConfig class | Buat `inc/config.class.php` dengan methods: getConfigValue, setConfigValue, getAllConfig, setMultipleConfig | Semua methods return benar, UPSERT works | 3h | C-01 |
| C-04 | Buat config page entry | Buat `front/config.php` — check right, handle POST save, render Twig | Halaman accessible dari menu GLPI | 2h | C-03 |
| C-05 | Buat config.twig template | Buat `views/config.twig` — form dengan 3 section: API Connection, AI Behavior, Session Settings | Form menampilkan current values, semua fields ada | 3h | C-04 |
| C-06 | Buat config.js | Buat `js/config.js` — toggle API key visibility, test connection button | Toggle works, test connection return AI Engine status | 2h | C-04 |
| C-07 | Buat config.css | Buat `css/config.css` — styling untuk config form | Form tampil rapi sesuai GLPI style | 1h | C-04 |
| C-08 | Tambah config_page hook | Modifikasi `setup.php` — tambah `$PLUGIN_HOOKS['config_page']` | Config page muncul di menu untuk admin | 0.5h | C-04 |
| C-09 | Modifikasi ajax/chat.php | Ganti hardcoded constants → `PluginChatbotConfig::getConfigValue()` | Chat menggunakan config dari DB | 2h | C-03 |
| C-10 | Test config CRUD | Test: install → default values, edit → save → verify, chat → uses new config | Semua AC PRD-02 terpenuhi | 2h | C-09 |

**Subtotal PRD-02: 18 jam**

### PRD-03: GLPI DB Connector

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| G-01 | Tambah GLPI DB settings | Tambah `glpi_db_host/port/name/user/password` ke `app/config.py` dan `.env` | Settings terbaca dari .env | 1h | — |
| G-02 | Buat GLPIDBConnector class | Buat `app/connectors/__init__.py` dan `app/connectors/glpi_db_connector.py` | Class terinstansiasi, engine lazy-created | 4h | G-01 |
| G-03 | Implementasi query methods | Implement: get_computer_count_by_status, get_computer_age_distribution, get_ticket_frequency_by_computer, get_warranty_status, get_computer_details_for_health, get_all_computer_ids, get_computer_by_name, get_computer_serials, get_dashboard_summary, test_connection | Semua methods return data yang benar | 6h | G-02 |
| G-04 | Buat module init | Buat `app/connectors/__init__.py` dengan exports: glpi_db, init_glpi_db, get_glpi_db | Import works | 0.5h | G-02 |
| G-05 | Integrate dengan FastAPI lifecycle | Tambah init_glpi_db() di startup, close() di shutdown, update /health endpoint | DB status muncul di /health response | 2h | G-02, D-11 |
| G-06 | Test koneksi ke GLPI DB | Test dengan read-only account (jika sudah ada) atau dengan existing credentials | Connection test return "ok" | 1h | G-05 |
| G-07 | Buat unit tests | Buat `tests/test_glpi_db_connector.py` dengan mocked DB | Coverage ≥ 80% untuk connector | 3h | G-03 |

**Subtotal PRD-03: 17.5 jam**

### PRD-01 Extra: FastAPI Route Refactor

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| R-01 | Buat api directory structure | Buat `app/api/__init__.py`, `app/api/routes/__init__.py` | Directory structure ready | 0.5h | — |
| R-02 | Extract chat route | Pindahkan chat logic dari `app/main.py` ke `app/api/routes/chat.py` | Chat endpoint berfungsi sama | 3h | R-01 |
| R-03 | Buat health route placeholder | Buat `app/api/routes/health.py` dengan 5 placeholder endpoints | Endpoints return "not_implemented" | 1h | R-01 |
| R-04 | Slim down main.py | Refactor `app/main.py` jadi router aggregation + lifespan | App berfungsi sama, main.py < 100 lines | 2h | R-02, R-03 |
| R-05 | Test refactor | Verifikasi semua endpoint masih berfungsi setelah refactor | Chat + health + /health semua OK | 1h | R-04 |

**Subtotal Refactor: 7.5 jam**

### Sprint 1-2 Total: 60 jam (~7.5 hari kerja)

---

## SPRINT 3-4: SCCM Connector & Data Layer

**Durasi:** 4 minggu  
**Tujuan:** SCCM connector, normalizer, correlator, SCCM tools  
**Prasyarat AHM:** SCCM DB read-only account, SCCM info (8 pertanyaan), firewall rule FR-03

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| S-01 | Tambah SCCM DB settings | Tambah `sccm_db_host/port/name/user/password` ke config.py dan .env | Settings terbaca | 1h | — |
| S-02 | Buat SCCMConnector class | Buat `app/connectors/sccm_connector.py` dengan engine + execute_query | Connection ke SQL Server berhasil | 4h | S-01 |
| S-03 | Implementasi SCCM query methods | Implement: get_all_systems, get_computer_hardware, get_software_inventory, get_patch_compliance, get_network_adapters, get_last_heartbeat, find_by_hostname, find_by_mac, test_connection | Semua methods return data dari SCCM views | 6h | S-02 |
| S-04 | Buat asset_mapper models | Buat `app/normalizers/asset_mapper.py` — NormalizedAsset + AssetMappingResult | Pydantic models valid | 2h | — |
| S-05 | Buat glpi_normalizer | Buat `app/normalizers/glpi_normalizer.py` — normalize_glpi_computer() | Raw GLPI data → NormalizedAsset | 1h | S-04 |
| S-06 | Buat sccm_normalizer | Buat `app/normalizers/sccm_normalizer.py` — normalize_sccm_system() | Raw SCCM data → NormalizedAsset | 1h | S-04 |
| S-07 | Buat AssetCorrelator | Buat `app/correlators/asset_correlator.py` — correlate_by_hostname, correlate_single, _find_mismatches | Match, mismatch, missing_in_sccm, missing_in_glpi terdeteksi | 4h | S-05, S-06, S-03 |
| S-08 | Buat SCCM CrewAI tools | Buat `app/tools/sccm_tools.py` — 4 tools: get_sccm_computer_detail, get_sccm_software_inventory, get_sccm_patch_status, compare_glpi_sccm | Tools terdaftar di agent, return formatted string | 4h | S-03, S-07 |
| S-09 | Register SCCM tools ke agent | Modifikasi `app/tools/__init__.py` dan `app/agents/agent_factory.py` | Agent punya 24 tools (20 + 4 SCCM) | 1h | S-08 |
| S-10 | Buat correlate Celery task | Tambah `correlate_glpi_sccm` task ke `app/workers/health_worker.py` | Task return summary + details | 2h | S-07 |
| S-11 | Implementasi health.py correlate endpoint | Implementasi POST /api/health/correlate di `app/api/routes/health.py` | Endpoint return job_id | 1h | S-10 |
| S-12 | Integrate SCCM lifecycle | Tambah init_sccm_db() di main.py lifespan (graceful jika belum dikonfigurasi) | SCCM features disabled jika host kosong | 1h | S-02 |
| S-13 | Test SCCM connector | Test koneksi ke SCCM DB (jika sudah ada) atau mock test | Connection test OK atau graceful degradation | 2h | S-12 |
| S-14 | Buat unit tests | Buat test_sccm_connector.py, test_asset_correlator.py | Coverage ≥ 80% | 4h | S-07, S-08 |

**Sprint 3-4 Total: 34 jam (~4.5 hari kerja)**

---

## SPRINT 5-6: Asset Health AI — Backend

**Durasi:** 4 minggu  
**Tujuan:** Health scorer, risk category, health crew, Celery workers, API endpoints

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| H-01 | Buat RiskCategory enum | Buat `app/scorers/risk_category.py` — enum + score_to_category() | Boundary values (30/31/50/51/70/71) return correct category | 1h | — |
| H-02 | Buat HealthScorer class | Buat `app/scorers/health_scorer.py` — calculate_score + 5 penalty methods + generate_recommendations | Score 0-100, category correct, recommendations generated | 6h | H-01 |
| H-03 | Buat Pydantic health models | Buat `app/models/health.py` — AnalyzeRequest, HealthReportResponse, DashboardResponse, JobStatusResponse | Models valid | 1h | — |
| H-04 | Buat 4 health agents | Buat data_collector_agent, pattern_analyzer_agent, risk_assessor_agent, recommendation_agent | Agents terdefinisi dengan tools/backstory | 4h | H-02 |
| H-05 | Buat 4 health tasks | Buat collect_data_task, analyze_patterns_task, assess_risk_task, generate_recommendations_task | Tasks terdefinisi | 2h | H-04 |
| H-06 | Buat health crew | Buat `app/crews/health_crew.py` — create_health_crew() | Crew sequential dengan 4 agents | 1h | H-04, H-05 |
| H-07 | Buat analyze_single_asset task | Buat Celery task di `app/workers/health_worker.py` | Task selesai < 30 detik per aset | 4h | H-02, G-03 |
| H-08 | Buat analyze_all_assets task | Buat Celery task dengan progress tracking | Task memproses semua aset, progress terupdate | 3h | H-07 |
| H-09 | Implementasi health API endpoints | Implementasi 5 endpoints di `app/api/routes/health.py` | Semua endpoints return correct data | 4h | H-07, H-08, H-03 |
| H-10 | Test health scorer | Buat test_health_scorer.py — healthy, critical, boundary, no-data cases | Coverage ≥ 90% untuk scorer | 3h | H-02 |
| H-11 | Test health API | Buat test_health_api.py — endpoint integration tests | Semua endpoints return expected status codes | 3h | H-09 |
| H-12 | End-to-end test | Test: trigger analysis → poll status → get report → verify dashboard | Full flow works | 2h | H-09 |

**Sprint 5-6 Total: 34 jam (~4.5 hari kerja)**

---

## SPRINT 7-8: Asset Health AI — GLPI Plugin UI

**Durasi:** 4 minggu  
**Tujuan:** Dashboard UI, health tab, audit log, scheduled jobs

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| U-01 | Tambah health_reports + audit_log tables | Tambah 2 tabel di hook.php install/uninstall | Tabel terbuat saat install, terhapus saat uninstall | 2h | — |
| U-02 | Buat PluginChatbotHealth class | Buat `inc/health.class.php` — CRUD health reports + showTab method | Class berfungsi, tab muncul di Computer detail | 3h | U-01 |
| U-03 | Buat PluginChatbotAudit class | Buat `inc/audit.class.php` — static log() method | Audit entries tercatat | 1h | U-01 |
| U-04 | Buat dashboard page | Buat `front/dashboard.php` — check right, load config, render Twig | Dashboard accessible dari menu | 2h | U-02 |
| U-05 | Buat dashboard.twig | Buat `views/dashboard.twig` — cards, tables, buttons | Dashboard menampilkan semua sections | 4h | U-04 |
| U-06 | Buat dashboard.js | Buat `js/dashboard.js` — loadDashboard, triggerAnalysis, triggerCorrelation, pollJobStatus | Semua interactions berfungsi | 4h | U-04 |
| U-07 | Buat dashboard.css | Buat `css/dashboard.css` — cards, charts, responsive | Dashboard tampil rapi | 2h | U-04 |
| U-08 | Buat health_tab.twig | Buat `views/health_tab.twig` — score ring, factors table, recommendations | Tab menampilkan health data | 3h | U-02 |
| U-09 | Buat health_tab.js | Buat `js/health_tab.js` — load report, render score ring | Score ring animated, data populated | 2h | U-08 |
| U-10 | Buat health_tab.css | Buat `css/health_tab.css` — score ring SVG, factors layout | Tab tampil rapi | 1h | U-08 |
| U-11 | Buat ajax/health.php | Buat AJAX handler untuk health API calls dari plugin | AJAX calls ke AI Engine berhasil | 2h | U-04 |
| U-12 | Register health tab hook | Tambah hook di hook.php untuk Computer detail tab | Tab "AI Health" muncul di Computer detail | 1h | U-02 |
| U-13 | Tambah rights di setup.php | Tambah `chatbot:use`, `chatbot:config`, `chatbot:dashboard` rights | Permission checks berfungsi | 1h | — |
| U-14 | Test dashboard end-to-end | Test: load → run analysis → poll → refresh → verify data | Dashboard fully functional | 3h | U-06 |
| U-15 | Test health tab | Test: buka Computer detail → AI Health tab → verify data | Tab fully functional | 2h | U-09 |

**Sprint 7-8 Total: 33 jam (~4 hari kerja)**

---

## SPRINT 9-10: Chat Enhancement — Plugin Refactor

**Durasi:** 4 minggu  
**Tujuan:** Twig refactor, access control, audit logging, context management

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| P-01 | Buat chat.twig | Extract inline HTML dari `front/chat.php` ke `views/chat.twig` | Template render sama seperti inline | 4h | — |
| P-02 | Refactor front/chat.php | Slim down: hanya load config, render Twig, header/footer | File < 30 lines, chat berfungsi | 2h | P-01 |
| P-03 | Load CSS/JS sebagai assets | Ganti `file_get_contents()` → `<link>` dan `<script>` tags | Assets loaded via HTTP, bukan inline | 1h | P-01 |
| P-04 | Implementasi rights check | Tambah `Session::haveRight('chatbot:use', READ)` di chat/sessions/ajax | Non-authorized user → 403 | 2h | U-13 |
| P-05 | Tambah audit logging di chat | Tambah `PluginChatbotAudit::log()` di ajax/chat.php | Audit entries tercatat untuk setiap query | 1h | U-03 |
| P-06 | Tambah audit logging di sessions | Tambah audit log di ajax/sessions.php (create/rename/delete) | Audit entries tercatat | 1h | U-03 |
| P-07 | Tambah audit logging di config | Tambah audit log di front/config.php (config change) | Audit entries tercatat | 0.5h | U-03 |
| P-08 | Enable user context | Aktifkan `plugin_chatbot_get_user_context()` di ajax/chat.php | Context (computers, tickets) dikirim ke AI Engine | 2h | — |
| P-09 | Test refactor regression | Verifikasi chat berfungsi sama setelah refactor | Chat, SSE streaming, session CRUD semua OK | 3h | P-02 |
| P-10 | Test access control | Test dengan berbagai user roles | Rights enforcement berfungsi | 1h | P-04 |

**Sprint 9-10 Total: 17.5 jam (~2 hari kerja)**

---

## SPRINT 11-12: Chat Enhancement — AI Engine

**Durasi:** 4 minggu  
**Tujuan:** SCCM-aware chat, health-aware chat, multi-turn improvement

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| E-01 | Buat health_tools.py | Buat `app/tools/health_tools.py` — get_asset_health_score, get_at_risk_assets | Tools return formatted health data | 4h | H-02 |
| E-02 | Register health tools ke agent | Tambah health tools ke `app/tools/__init__.py` dan agent_factory | Agent punya 26 tools (20 + 4 SCCM + 2 health) | 1h | E-01, S-09 |
| E-03 | Update agent backstory | Update backstory di agent_factory.py — mention SCCM + health capabilities | Agent aware of new capabilities | 1h | E-02 |
| E-04 | Improve prompt_builder | Tingkatkan history window (4→6), assistant content max (400→600), tambah conversation summary | Multi-turn conversations lebih koheren | 2h | — |
| E-05 | Tambah formatters | Tambah format_health_report dan format_sccm_comparison ke formatters.py | Tabular responses formatted | 2h | — |
| E-06 | Test SCCM chat queries | Test: "Software di PC-001?", "Patch status?", "Bandingkan GLPI vs SCCM" | Agent menggunakan SCCM tools | 2h | E-02 |
| E-07 | Test health chat queries | Test: "Kesehatan PC-001?", "Komputer yang perlu diganti?" | Agent menggunakan health tools | 2h | E-02 |
| E-08 | Test multi-turn conversation | Test 5+ turn conversation dengan context | Context retained, coherent responses | 1h | E-04 |

**Sprint 11-12 Total: 15 jam (~2 hari kerja)**

---

## SPRINT 13-14: Testing, Security & Deployment

**Durasi:** 4 minggu  
**Tujuan:** Testing, security, performance, documentation, UAT, go-live

| ID | Title | Description | Acceptance Criteria | Est. | Deps |
|----|-------|-------------|---------------------|------|------|
| T-01 | Buat conftest.py | Buat shared fixtures: mock_settings, sample data, mock connectors | Fixtures reusable | 2h | — |
| T-02 | Buat test_health_scorer.py | Unit tests untuk HealthScorer — healthy, critical, boundary, no-data | Coverage ≥ 90% | 3h | T-01 |
| T-03 | Buat test_asset_correlator.py | Unit tests untuk AssetCorrelator — match, mismatch, missing | Coverage ≥ 80% | 2h | T-01 |
| T-04 | Buat test_sccm_connector.py | Unit tests untuk SCCMConnector (mocked) | Coverage ≥ 80% | 2h | T-01 |
| T-05 | Buat test_health_api.py | Integration tests untuk health API endpoints | Semua endpoints return correct status | 3h | T-01 |
| T-06 | Buat test_e2e_chat.py | E2E test: chat flow dari request → response | Full chat flow works | 2h | T-01 |
| T-07 | Buat test_e2e_health.py | E2E test: analysis flow dari trigger → report | Full health flow works | 2h | T-01 |
| T-08 | Implementasi rate limiting | Tambah slowapi middleware ke FastAPI | Rate limit aktif, 429 return untuk excess | 2h | — |
| T-09 | Tambah input validation | Tambah Pydantic validators ke request models | Invalid input → 400 | 2h | — |
| T-10 | Implementasi Redis caching | Extend cache.py → RedisCache, cache dashboard data | Dashboard load < 3 detik | 3h | — |
| T-11 | Security review | Review: SQL injection, API key exposure, CORS, error messages | Tidak ada critical findings | 4h | T-08, T-09 |
| T-12 | Buat api-spec.md | Dokumentasi API specification lengkap | Dokumen lengkap dan akurat | 3h | — |
| T-13 | Buat deployment-guide.md | Panduan deployment Docker step-by-step | Dokumen lengkap | 2h | — |
| T-14 | Buat sccm-integration.md | Panduan integrasi SCCM | Dokumen lengkap | 2h | — |
| T-15 | Buat health-algorithm.md | Dokumentasi algoritma health scoring | Dokumen lengkap | 1h | — |
| T-16 | Performance benchmark | Test: dashboard load, health report, full analysis, chat response | Semua target terpenuhi | 3h | T-10 |
| T-17 | UAT preparation | Siapkan UAT scenarios, sign-off template, koordinasi participants | UAT ready | 2h | — |
| T-18 | UAT execution | Fasilitasi UAT dengan 3+ pengguna AHM | UAT passed | 4h | T-17 |
| T-19 | Production deployment | Deploy ke production, verify, monitor | System running di production | 4h | T-18 |
| T-20 | Post-deployment monitoring | Monitor logs, performance, errors selama 1 minggu | Tidak ada critical issues | 2h | T-19 |

**Sprint 13-14 Total: 49 jam (~6 hari kerja)**

---

## Summary

| Sprint | Durasi | Total Jam | Hari Kerja | PRD References |
|--------|--------|-----------|------------|----------------|
| 1-2 | 4 minggu | 60h | ~7.5 | PRD-01, 02, 03 + Refactor |
| 3-4 | 4 minggu | 34h | ~4.5 | PRD-04 |
| 5-6 | 4 minggu | 34h | ~4.5 | PRD-05 |
| 7-8 | 4 minggu | 33h | ~4 | PRD-06 |
| 9-10 | 4 minggu | 17.5h | ~2 | PRD-07 |
| 11-12 | 4 minggu | 15h | ~2 | PRD-08 |
| 13-14 | 4 minggu | 49h | ~6 | PRD-09 |
| **TOTAL** | **28 minggu** | **242.5h** | **~30 hari** | |

> **Catatan:** Estimasi di atas adalah waktu coding murni. Waktu aktual perlu ditambah buffer untuk: koordinasi AHM, debugging, code review, context switching, dan unforeseen issues. Rekomendasi: kalikan 1.5x untuk estimasi realistis (~45 hari kerja, ~9 minggu efektif).
