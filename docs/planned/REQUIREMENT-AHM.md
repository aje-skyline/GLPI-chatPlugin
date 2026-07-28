# REQUIREMENT KE AHM — PHASE 2: EKSTENSI AI GLPI

> **Dokumen:** Kebutuhan yang harus disediakan/dikoordinasikan oleh AHM untuk pengembangan Phase 2 GLPI AI Extension  
> **Tanggal:** Juli 2026  
> **Versi:** 1.0  
> **Status:** Draft — Menunggu Konfirmasi AHM  
> **Ditujukan Kepada:** IT Infrastructure Team, SCCM/Endpoint Team, IT Security, IT Management

---

## Daftar Isi

1. [Ringkasan Proyek](#1-ringkasan-proyek)
2. [Kebutuhan Server & Infrastruktur](#2-kebutuhan-server--infrastruktur)
3. [Kebutuhan Akses Database](#3-kebutuhan-akses-database)
4. [Kebutuhan Network & Connectivity](#4-kebutuhan-network--connectivity)
5. [Kebutuhan SCCM](#5-kebutuhan-sccm)
6. [Kebutuhan Keamanan](#6-kebutuhan-keamanan)
7. [Kebutuhan Koordinasi & Approval](#7-kebutuhan-koordinasi--approval)
8. [Checklist Ringkas](#8-checklist-ringkas)

---

## 1. Ringkasan Proyek

### 1.1 Konteks

Saat ini sistem GLPI AI Chatbot sudah berjalan di lingkungan AHM dengan arsitektur sebagai berikut:

```
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  GLPI 11.0.6     │  HTTP   │  AI Engine       │  HTTP   │  AI Gateway      │
│  (172.16.14.103) │◄───────►│  (FastAPI)       │◄───────►│  (LLM Internal)  │
│  + Chat Plugin   │         │  (172.16.14.141) │         │  AHM             │
└──────────────────┘         └──────────────────┘         └──────────────────┘
```

**Fitur yang sudah berjalan:**
- Chat AI di GLPI — pengguna bisa bertanya tentang aset, tiket, supplier, kontrak
- 20 tools CrewAI — query data GLPI via REST API
- SSE streaming — respons real-time di chat interface
- Session management — riwayat percakapan tersimpan

### 1.2 Rencana Phase 2

Phase 2 akan menambahkan dua fitur utama:

1. **Asset Health AI** — Analisis kesehatan aset IT secara otomatis dengan scoring dan rekomendasi
2. **SCCM Integration** — Korelasi data antara GLPI dan SCCM untuk deteksi gap dan anomali

Arsitektur target:

```
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  GLPI 11.0.6     │  HTTP   │  AI Engine       │  HTTP   │  AI Gateway      │
│  (172.16.14.103) │◄───────►│  (Docker)        │◄───────►│  (LLM Internal)  │
│  + Chat Plugin   │         │  (SERVER BARU)   │         │  AHM             │
│  + Dashboard UI  │         │                  │         └──────────────────┘
└──────────────────┘         │  + Celery Worker │
                             │  + Redis         │
                             └──────┬─────┬─────┘
                                    │     │
                          ┌─────────┘     └──────────┐
                          ▼                          ▼
                   ┌────────────┐           ┌────────────────┐
                   │  GLPI DB   │           │  SCCM DB       │
                   │  (MariaDB) │           │  (SQL Server)  │
                   │  READ-ONLY │           │  READ-ONLY     │
                   └────────────┘           └────────────────┘
```

### 1.3 Mengapa AHM Perlu Terlibat

Pengembangan Phase 2 membutuhkan akses dan resource yang **tidak tersedia saat ini** dan hanya bisa disediakan oleh tim AHM:

| Kebutuhan | Mengapa Perlu AHM | Tanpa Ini |
|-----------|-------------------|-----------|
| Server baru untuk Docker | AI Engine perlu pindah ke server dedicated | Tidak bisa deploy Celery + Redis |
| Akses read-only GLPI DB | Health analysis butuh query kompleks yang tidak bisa via REST API | Fitur Asset Health tidak bisa dibangun |
| Akses read-only SCCM DB | Korelasi data GLPI ↔ SCCM | Fitur SCCM Integration tidak bisa dibangun |
| Network connectivity | AI Engine harus reach GLPI DB + SCCM DB | Sistem tidak bisa berjalan |
| Approval keamanan | Akses database lintas sistem perlu approval | Deployment tertunda |

---

## 2. Kebutuhan Server & Infrastruktur

### 2.1 Server Baru untuk AI Engine (Docker)

AI Engine saat ini berjalan di `172.16.14.141` tanpa Docker. Phase 2 membutuhkan **server terpisah** untuk menjalankan Docker stack (FastAPI + Celery Worker + Celery Beat + Redis).

#### Spesifikasi Minimum

| Parameter | Minimum | Rekomendasi | Catatan |
|-----------|---------|-------------|---------|
| **OS** | Ubuntu 22.04 LTS / RHEL 8+ | Ubuntu 22.04 LTS | Docker CE support |
| **CPU** | 4 vCPU | 8 vCPU | Celery worker butuh CPU untuk health analysis |
| **RAM** | 8 GB | 16 GB | Redis + 2 Celery worker + FastAPI + LLM inference via API |
| **Storage** | 50 GB SSD | 100 GB SSD | Docker images, logs, Redis persistence |
| **Docker** | Docker CE 24+ | Docker CE 24+ | Docker Compose v2 |
| **Network** | 1 Gbps | 1 Gbps | Koneksi ke GLPI DB, SCCM DB, AI Gateway |

#### Docker Services yang Akan Berjalan

| Service | Port | Resource Estimasi | Keterangan |
|---------|------|-------------------|------------|
| **ai-engine** (FastAPI) | 8000 | 1-2 GB RAM, 1 CPU | API utama, chat + health endpoints |
| **celery-worker** | — | 2-4 GB RAM, 2 CPU | Background job: health analysis, SCCM correlation |
| **celery-beat** | — | 256 MB RAM, 0.5 CPU | Scheduler: menjalankan analisis periodik |
| **redis** | 6379 | 512 MB RAM, 0.5 CPU | Message broker + result backend + cache |

**Total estimasi resource:** 4-7 GB RAM, 3.5-5.5 CPU

#### Yang Perlu Disiapkan AHM

- [ ] **1 (satu) server** dengan spesifikasi di atas
- [ ] **Docker CE + Docker Compose v2** terinstall
- [ ] **User non-root** untuk menjalankan Docker (security best practice)
- [ ] **Akses SSH** untuk deployment dan maintenance
- [ ] **IP address static** (akan dikonfigurasi di GLPI plugin config)

### 2.2 Server GLPI yang Sudah Ada

Server GLPI (`172.16.14.103`) sudah berjalan. Tidak perlu perubahan hardware, tetapi perlu:

- [ ] **Database user read-only** baru (detail di Bagian 3)
- [ ] **Firewall rule** untuk mengizinkan koneksi dari server AI Engine baru ke port 3306 (MariaDB)

---

## 3. Kebutuhan Akses Database

### 3.1 GLPI Database (MariaDB) — Read-Only

AI Engine membutuhkan akses **langsung ke database GLPI** (bukan via REST API) untuk menjalankan query analisis kesehatan aset yang kompleks. REST API GLPI tidak mendukung aggregate queries, JOIN antar tabel, dan analisis statistik yang dibutuhkan.

#### Kredensial yang Dibutuhkan

| Parameter | Nilai yang Dibutuhkan | Contoh |
|-----------|----------------------|--------|
| **Host** | IP/hostname MariaDB | `172.16.14.103` |
| **Port** | Port MariaDB | `3306` |
| **Database** | Nama database GLPI | `glpi` |
| **Username** | User read-only baru | `glpi_ai_readonly` |
| **Password** | Password strong | *(disediakan AHM)* |

#### Permission yang Dibutuhkan

```sql
-- User hanya membutuhkan SELECT privilege, tidak ada INSERT/UPDATE/DELETE
GRANT SELECT ON glpi.* TO 'glpi_ai_readonly'@'<ai-engine-server-ip>';
FLUSH PRIVILEGES;
```

#### Tabel yang Di-Query

AI Engine hanya akan membaca data dari tabel-tabel berikut (semua operasi SELECT saja):

| Tabel GLPI | Data yang Diambil | Digunakan Untuk |
|------------|-------------------|-----------------|
| `glpi_computers` | Daftar aset, tanggal pembuatan, status | Health scoring, age analysis |
| `glpi_states` | Nama status aset | Status distribution |
| `glpi_manufacturers` | Nama manufacturer | Hardware info |
| `glpi_computertypes` | Tipe komputer | Hardware info |
| `glpi_locations` | Lokasi aset | Location-based analysis |
| `glpi_users` | Data pengguna | User context |
| `glpi_tickets` | Data tiket | Ticket frequency analysis |
| `glpi_items_tickets` | Relasi tiket-aset | Ticket per computer |
| `glpi_contracts` | Data kontrak | Warranty status |
| `glpi_contracts_items` | Relasi kontrak-aset | Warranty per computer |
| `glpi_operatingsystems` | Nama OS | OS distribution |
| `glpi_knowbaseitems` | Artikel KB | Knowledge search |
| `glpi_plugin_chatbot_sessions` | Session chat | Chat history |
| `glpi_plugin_chatbot_messages` | Pesan chat | Chat history |
| `glpi_plugin_chatbot_health_reports` | Laporan health | Health dashboard |
| `glpi_plugin_chatbot_audit_log` | Log audit | Audit trail |
| `glpi_plugin_chatbot_config` | Konfigurasi plugin | Config management |

**Pernyataan jaminan:**
- User `glpi_ai_readonly` **TIDAK** akan pernah melakukan INSERT, UPDATE, DELETE, atau DDL
- Semua operasi tulis ke GLPI tetap melalui REST API (seperti saat ini)
- Query yang dijalankan sudah ditentukan (parameterized) dan tidak ada raw user input di SQL

#### Yang Perlu Disiapkan AHM

- [ ] Buat database user `glpi_ai_readonly` dengan SELECT privilege saja
- [ ] Konfigurasi firewall: izinkan koneksi dari IP server AI Engine ke port 3306
- [ ] Berikan kredensial (host, port, database name, username, password) ke tim pengembang

### 3.2 SCCM Database (SQL Server) — Read-Only

AI Engine membutuhkan akses **read-only ke database SCCM** untuk korelasi data aset dan analisis patch compliance.

#### Kredensial yang Dibutuhkan

| Parameter | Nilai yang Dibutuhkan | Contoh |
|-----------|----------------------|--------|
| **Host** | IP/hostname SQL Server SCCM | *(disediakan AHM)* |
| **Port** | Port SQL Server | `1433` (default) |
| **Database** | Nama database SCCM | `CM_PS1` (format: `CM_<sitecode>`) |
| **Username** | User read-only baru | `sccm_ai_readonly` |
| **Password** | Password strong | *(disediakan AHM)* |

#### Permission yang Dibutuhkan

```sql
-- User hanya membutuhkan SELECT privilege pada views, tidak akses tabel langsung
GRANT SELECT ON SCHEMA::dbo TO sccm_ai_readonly;
-- Atau lebih spesifik, hanya pada views yang dibutuhkan:
GRANT SELECT ON OBJECT::dbo.v_R_System TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_COMPUTER_SYSTEM TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_OPERATING_SYSTEM TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_NETWORK_ADAPTER TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_INSTALLED_SOFTWARE_CATEGORIZED TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_Update_ComplianceStatus TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_WORKSTATION_STATUS TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_PROCESSOR TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_X86_COMPUTER_SYSTEM TO sccm_ai_readonly;
GRANT SELECT ON OBJECT::dbo.v_GS_DISK TO sccm_ai_readonly;
```

#### Views SCCM yang Di-Query

| SCCM View | Data | Digunakan Untuk |
|-----------|------|-----------------|
| `v_R_System` | Hostname, domain, OS, status aktif | Asset matching by hostname |
| `v_GS_COMPUTER_SYSTEM` | Manufacturer, model, tipe sistem | Hardware comparison GLPI vs SCCM |
| `v_GS_OPERATING_SYSTEM` | OS name, version, install date, last boot | OS comparison, age calculation |
| `v_GS_NETWORK_ADAPTER` | MAC address, IP, gateway | MAC-based matching, network info |
| `v_GS_INSTALLED_SOFTWARE_CATEGORIZED` | Software name, version, publisher | Software inventory query via chat |
| `v_Update_ComplianceStatus` | Patch installed/missing/unknown | Patch compliance scoring |
| `v_GS_WORKSTATION_STATUS` | Last hardware/software scan | Last seen timestamp |
| `v_GS_PROCESSOR` | CPU name, cores | Hardware specs |
| `v_GS_X86_COMPUTER_SYSTEM` | Total physical memory | Hardware specs |
| `v_GS_DISK` | Disk size, free space | Storage health analysis |

**Pernyataan jaminan:**
- User `sccm_ai_readonly` **TIDAK** akan pernah melakukan operasi tulis ke SCCM
- Hanya mengakses **views** (v_*), bukan tabel langsung
- Tidak akan mengakses SCCM console, collection management, atau deployment features
- Query bersifat read-only untuk analisis dan reporting

#### Yang Perlu Disiapkan AHM

- [ ] Konfirmasi: versi SCCM/MECM yang digunakan (untuk kompatibilitas views)
- [ ] Konfirmasi: nama database SCCM (format `CM_<sitecode>`)
- [ ] Buat SQL login `sccm_ai_readonly` dengan SELECT privilege pada views di atas
- [ ] Konfigurasi firewall: izinkan koneksi dari IP server AI Engine ke SQL Server port 1433
- [ ] Berikan kredensial (host, port, database name, username, password) ke tim pengembang
- [ ] Konfirmasi: apakah SQL Server menggunakan encryption (TLS)? Jika ya, berikan certificate detail

---

## 4. Kebutuhan Network & Connectivity

### 4.1 Diagram Network

```
                    ┌─────────────────────────────────────────┐
                    │           Jaringan Internal AHM         │
                    │                                         │
  ┌─────────────┐   │   ┌─────────────┐    ┌─────────────┐  │   ┌─────────────┐
  │  Browser    │   │   │  GLPI       │    │  AI Engine  │  │   │  AI Gateway │
  │  User       │───┼──►│  172.16.14  │◄──►│  SERVER     │──┼──►│  (LLM)      │
  │             │   │   │  .103       │    │  BARU       │  │   │  Internal   │
  └─────────────┘   │   └──────┬──────┘    └──────┬──────┘  │   └─────────────┘
                    │          │                   │          │
                    │          │ 3306              │ 1433     │
                    │          ▼                   ▼          │
                    │   ┌─────────────┐    ┌─────────────┐  │
                    │   │  GLPI DB    │    │  SCCM DB    │  │
                    │   │  (MariaDB)  │    │  (SQL Srv)  │  │
                    │   └─────────────┘    └─────────────┘  │
                    └─────────────────────────────────────────┘
```

### 4.2 Koneksi yang Dibutuhkan

| No | Dari | Ke | Port | Protokol | Tujuan | Status |
|----|------|----|------|----------|--------|--------|
| 1 | Browser User | GLPI Server | 443 | HTTPS | Akses GLPI + Chat UI | ✅ Sudah ada |
| 2 | GLPI Plugin | AI Engine (baru) | 8000 | HTTP(S) | Chat API, Health API | 🔲 Baru |
| 3 | AI Engine (baru) | AI Gateway | 443 | HTTPS | LLM inference | ✅ Sudah ada |
| 4 | AI Engine (baru) | GLPI DB (MariaDB) | 3306 | TCP | Query health analysis | 🔲 Baru |
| 5 | AI Engine (baru) | SCCM DB (SQL Server) | 1433 | TCP | Query SCCM data | 🔲 Baru |
| 6 | AI Engine (baru) | GLPI REST API | 443 | HTTPS | Chat tools (existing) | ✅ Sudah ada |

### 4.3 Firewall Rules yang Perlu Dibuka

| Rule | Source IP | Destination | Port | Protokol | Arah | Keterangan |
|------|-----------|-------------|------|----------|------|------------|
| **FR-01** | IP GLPI Server | IP AI Engine (baru) | 8000 | TCP | Inbound ke AI Engine | Chat + Health API |
| **FR-02** | IP AI Engine (baru) | IP GLPI Server | 3306 | TCP | Outbound dari AI Engine | GLPI DB read-only |
| **FR-03** | IP AI Engine (baru) | IP SCCM SQL Server | 1433 | TCP | Outbound dari AI Engine | SCCM DB read-only |
| **FR-04** | IP AI Engine (baru) | IP AI Gateway | 443 | TCP | Outbound dari AI Engine | LLM API (sudah ada) |
| **FR-05** | IP AI Engine (baru) | IP GLPI Server | 443 | TCP | Outbound dari AI Engine | GLPI REST API (sudah ada) |

> **Catatan:** IP AI Engine (baru) akan ditentukan setelah server disiapkan. Mohon informasikan range IP yang tersedia agar kami bisa mengajukan IP request.

### 4.4 DNS & SSL

| Kebutuhan | Detail | Status |
|-----------|--------|--------|
| **DNS Entry** | Hostname untuk AI Engine (misal: `ai-engine.ahm.internal`) | 🔲 Perlu dibuat |
| **SSL Certificate** | Untuk HTTPS di AI Engine (port 8000) | 🔲 Perlu disiapkan jika komunikasi Plugin ↔ AI Engine harus encrypted |
| **Internal CA** | Jika menggunakan internal Certificate Authority | 🔲 Perlu info |

> **Rekomendasi:** Komunikasi antara GLPI Plugin dan AI Engine sebaiknya menggunakan HTTPS, terutama karena data chat dan API key dilewatkan. Jika tidak memungkinkan, komunikasi HTTP internal di jaringan yang terisolasi juga dapat diterima dengan catatan keamanan.

### 4.5 Yang Perlu Disiapkan AHM

- [ ] Alokasi IP address untuk server AI Engine baru
- [ ] Buka firewall rules FR-01 sampai FR-05 (setelah IP AI Engine ditentukan)
- [ ] Buat DNS entry untuk AI Engine (opsional tapi direkomendasikan)
- [ ] Konfirmasi: apakah SSL certificate diperlukan untuk AI Engine?
- [ ] Konfirmasi: apakah ada proxy yang harus dikonfigurasi untuk outbound connections dari AI Engine?

---

## 5. Kebutuhan SCCM

### 5.1 Informasi yang Perlu Dikonfirmasi

Sebelum pengembangan SCCM Integration dimulai, berikut informasi yang **wajib** dikonfirmasi:

| No | Informasi | Contoh Jawaban | Pentingnya |
|----|-----------|----------------|------------|
| 1 | Versi SCCM/MECM yang digunakan | MECM 2203, SCCM 2016, dll | Menentukan views yang tersedia |
| 2 | Nama database SCCM | `CM_PS1`, `CM_PR1` | Koneksi database |
| 3 | SQL Server version | SQL Server 2019, 2022 | Driver compatibility |
| 4 | Apakah SQL Server menggunakan TLS encryption? | Ya/Tidak | Konfigurasi koneksi |
| 5 | Berapa jumlah total assets di SCCM? | ~500, ~5000 | Estimasi beban query |
| 6 | Seberapa sering SCCM data di-update? | Harian, per jam | Menentukan refresh interval |
| 7 | Apakah ada custom views yang sudah dibuat? | Ya/Tidak | Bisa dimanfaatkan |
| 8 | Apakah SCCM dan GLPI menggunakan hostname yang sama untuk aset yang sama? | Ya/Tidak | Menentukan matching strategy |

### 5.2 Data SCCM yang Akan Digunakan

Berikut adalah **data spesifik** yang akan diambil dari SCCM dan bagaimana data tersebut digunakan:

| Data SCCM | View Source | Digunakan Untuk | Frekuensi Akses |
|-----------|-------------|-----------------|-----------------|
| Daftar sistem/hostname | `v_R_System` | Matching aset GLPI ↔ SCCM | Per analisis (scheduled) |
| Hardware detail (manufacturer, model) | `v_GS_COMPUTER_SYSTEM` | Perbandingan data GLPI vs SCCM | Per aset |
| OS info (name, version, install date) | `v_GS_OPERATING_SYSTEM` | Perbandingan OS, age analysis | Per aset |
| MAC address | `v_GS_NETWORK_ADAPTER` | Matching alternatif jika hostname beda | Per aset |
| Software inventory | `v_GS_INSTALLED_SOFTWARE_CATEGORIZED` | Query chat: "Software apa di PC X?" | On-demand (chat) |
| Patch compliance | `v_Update_ComplianceStatus` | Health scoring: patch compliance factor | Per analisis (scheduled) |
| Last heartbeat/scan | `v_GS_WORKSTATION_STATUS` | Deteksi aset offline/inactive | Per analisis |
| Processor info | `v_GS_PROCESSOR` | Hardware specs comparison | Per aset |
| Memory info | `v_GS_X86_COMPUTER_SYSTEM` | Hardware specs comparison | Per aset |
| Disk info | `v_GS_DISK` | Storage health analysis | Per aset |

### 5.3 Estimasi Beban Query

| Skenario | Query Frequency | Estimasi Rows per Query | Impact ke SCCM DB |
|----------|-----------------|------------------------|-------------------|
| **Full correlation** (scheduled) | 1x per hari (malam) | ~500-5000 rows (v_R_System) | Low — diluar jam kerja |
| **Single asset lookup** (chat) | On-demand, ~10-50x per hari | 1-10 rows | Negligible |
| **Patch compliance** (scheduled) | 1x per hari | ~500-5000 rows | Low — diluar jam kerja |
| **Software inventory** (chat) | On-demand, ~5-20x per hari | 50-200 rows per aset | Negligible |

> **Jaminan:** Semua query bersifat SELECT read-only. Tidak ada operasi yang memodifikasi data SCCM. Scheduled jobs dijalankan di luar jam kerja (malam hari) untuk meminimalkan impact.

### 5.4 Yang Perlu Disiapkan AHM

- [ ] Jawab 8 pertanyaan di tabel 5.1
- [ ] Buat SQL login read-only (detail di Bagian 3.2)
- [ ] Konfirmasi: apakah ada maintenance window SCCM yang harus dihindari untuk scheduled queries?
- [ ] Konfirmasi: apakah ada data sensitif di SCCM yang tidak boleh diakses? (misal: user password, license keys)

---

## 6. Kebutuhan Keamanan

### 6.1 Prinsip Keamanan yang Diterapkan

| Prinsip | Implementasi |
|---------|--------------|
| **Least Privilege** | Database user hanya punya SELECT privilege, tidak INSERT/UPDATE/DELETE |
| **Defense in Depth** | API key authentication, CORS restriction, input validation |
| **No Secrets in Code** | Semua kredensial via environment variables, tidak hardcoded |
| **Audit Trail** | Semua query chat dan health analysis dicatat di audit log |
| **Encryption in Transit** | HTTPS untuk semua komunikasi API (jika SSL tersedia) |
| **Data Minimization** | Hanya mengambil data yang diperlukan, tidak seluruh tabel |

### 6.2 Kredensial yang Akan Digunakan

| Kredensial | Penyimpanan | Rotasi | Akses |
|------------|-------------|--------|-------|
| GLPI DB password | Environment variable (`.env`) | Perlu mekanisme rotasi | AI Engine container saja |
| SCCM DB password | Environment variable (`.env`) | Perlu mekanisme rotasi | AI Engine container saja |
| AI Gateway API Key | Environment variable (`.env`) | Sudah ada, perlu rotasi berkala | AI Engine container saja |
| GATEWAY_API_KEY (plugin auth) | GLPI DB (config table) | Perlu mekanisme rotasi | GLPI Plugin + AI Engine |
| GLPI User Token (REST API) | Environment variable (`.env`) | Sudah ada | AI Engine container saja |

### 6.3 Pertanyaan Keamanan untuk AHM

| No | Pertanyaan | Relevansi |
|----|-----------|-----------|
| 1 | Apakah ada kebijakan password rotation untuk database accounts? | Menentukan mekanisme update kredensial |
| 2 | Apakah ada requirement untuk encrypt data at rest di server AI Engine? | Konfigurasi Docker volume encryption |
| 3 | Apakah ada SIEM atau log aggregation system yang harus menerima audit logs? | Format dan destinasi audit log |
| 4 | Apakah ada vulnerability scanning policy untuk server baru? | Menentukan hardening requirements |
| 5 | Apakah ada kebijakan tentang penyimpanan chat history? Berapa lama data disimpan? | Data retention policy |
| 6 | Apakah penggunaan AI/LLM untuk data internal sudah mendapat approval? | Compliance dan legal |
| 7 | Apakah ada data classification yang berlaku? (Public, Internal, Confidential, Restricted) | Menentukan data mana yang boleh di-query oleh AI |

### 6.4 Yang Perlu Disiapkan AHM

- [ ] Jawab 7 pertanyaan keamanan di tabel 6.3
- [ ] Review dan approve prinsip keamanan di tabel 6.1
- [ ] Konfirmasi: apakah ada security assessment yang perlu dilakukan sebelum go-live?
- [ ] Konfirmasi: apakah perlu penetration testing sebelum production?

---

## 7. Kebutuhan Koordinasi & Approval

### 7.1 Timeline Pengembangan

Berikut adalah timeline pengembangan dan kapan setiap kebutuhan AHM diperlukan:

```
Minggu 1-4  (Sprint 1-2):  Foundation & Docker
  ├── BUTUH: Server AI Engine baru           ← SEKARANG
  ├── BUTUH: GLPI DB read-only account       ← SEKARANG
  ├── BUTUH: Firewall rules (FR-01, FR-02)   ← SEKARANG
  └── BUTUH: IP address alokasi              ← SEKARANG

Minggu 5-8  (Sprint 3-4):  SCCM Connector
  ├── BUTUH: SCCM DB read-only account       ← MINGGU 4
  ├── BUTUH: SCCM info (8 pertanyaan 5.1)    ← MINGGU 4
  ├── BUTUH: Firewall rules (FR-03)          ← MINGGU 4
  └── BUTUH: Jawaban keamanan (6.3)          ← MINGGU 4

Minggu 9-12 (Sprint 5-6):  Asset Health AI Backend
  └── Tidak ada kebutuhan baru dari AHM

Minggu 13-16 (Sprint 7-8):  Asset Health AI UI
  └── Tidak ada kebutuhan baru dari AHM

Minggu 17-20 (Sprint 9-10): Chat Enhancement
  └── Tidak ada kebutuhan baru dari AHM

Minggu 21-24 (Sprint 11-12): Chat Enhancement AI Engine
  └── Tidak ada kebutuhan baru dari AHM

Minggu 25-28 (Sprint 13-14): Testing & Deployment
  ├── BUTUH: Security review/approval        ← MINGGU 25
  ├── BUTUH: UAT participants dari AHM       ← MINGGU 27
  └── BUTUH: Go-live approval                ← MINGGU 28
```

### 7.2 PIC yang Dibutuhkan

| Peran | Tanggung Jawab | Dari Tim |
|-------|----------------|----------|
| **Database Administrator** | Buat GLPI DB + SCCM DB read-only accounts, konfigurasi firewall DB | IT Infrastructure |
| **Network Administrator** | Buka firewall rules, alokasi IP, konfigurasi DNS | IT Infrastructure |
| **SCCM Administrator** | Konfirmasi versi SCCM, views, data structure, maintenance window | SCCM/Endpoint Team |
| **Security Officer** | Review keamanan, approve akses, jawab pertanyaan keamanan | IT Security |
| **Server Administrator** | Siapkan server baru, install Docker, konfigurasi OS | IT Infrastructure |
| **Business Owner** | Approve penggunaan AI untuk data internal, UAT sign-off | IT Management |
| **Single Point of Contact** | Koordinasi antar tim, eskalasi blocker | AHM (ditunjuk) |

### 7.3 Prosedur Koordinasi

| Tahap | Aktivitas | Timeline | PIC |
|-------|-----------|----------|-----|
| **Kickoff** | Meeting kickoff untuk menjelaskan requirement ini | Minggu 0 | Semua PIC |
| **Provisioning** | Server + DB accounts + Firewall rules disiapkan | Minggu 1-2 | Infra + DBA |
| **Validation** | Tim pengembang test konektivitas ke semua resource | Minggu 2 | Pengembang + Infra |
| **SCCM Onboarding** | SCCM access disiapkan, data structure dikonfirmasi | Minggu 4 | SCCM Admin + DBA |
| **Security Review** | Review keamanan sebelum go-live | Minggu 25 | Security Officer |
| **UAT** | User acceptance testing dengan pengguna AHM | Minggu 27 | Business Owner + Users |
| **Go-Live** | Approval dan deployment ke production | Minggu 28 | Management |

### 7.4 Yang Perlu Disiapkan AHM

- [ ] Tunjuk **Single Point of Contact (SPOC)** dari AHM untuk koordinasi
- [ ] Jadwalkan **kickoff meeting** dengan semua PIC
- [ ] Tentukan **SLA respons** untuk setiap kebutuhan (misal: server provisioning 2 minggu, DB account 3 hari)
- [ ] Tentukan **maintenance window** yang diizinkan untuk deployment
- [ ] Identifikasi **UAT participants** (minimal 3-5 pengguna GLPI untuk testing)

---

## 8. Checklist Ringkas

### 8.1 Kebutuhan Mendesak (Dibutuhkan Minggu 1-2)

| No | Kebutuhan | PIC AHM | Status | Target |
|----|-----------|---------|--------|--------|
| 1 | Server baru (4 vCPU, 8 GB RAM, 50 GB SSD, Docker) | Server Admin | 🔲 | Minggu 1 |
| 2 | IP address untuk server baru | Network Admin | 🔲 | Minggu 1 |
| 3 | GLPI DB read-only account (`glpi_ai_readonly`) | DBA | 🔲 | Minggu 1 |
| 4 | Firewall: GLPI → AI Engine (port 8000) | Network Admin | 🔲 | Minggu 1 |
| 5 | Firewall: AI Engine → GLPI DB (port 3306) | Network Admin | 🔲 | Minggu 1 |
| 6 | SSH access ke server baru | Server Admin | 🔲 | Minggu 2 |
| 7 | DNS entry untuk AI Engine (opsional) | Network Admin | 🔲 | Minggu 2 |

### 8.2 Kebutuhan Sprint 3-4 (Dibutuhkan Minggu 4)

| No | Kebutuhan | PIC AHM | Status | Target |
|----|-----------|---------|--------|--------|
| 8 | SCCM DB read-only account (`sccm_ai_readonly`) | DBA + SCCM Admin | 🔲 | Minggu 4 |
| 9 | Firewall: AI Engine → SCCM DB (port 1433) | Network Admin | 🔲 | Minggu 4 |
| 10 | Jawaban 8 pertanyaan SCCM (tabel 5.1) | SCCM Admin | 🔲 | Minggu 4 |
| 11 | Jawaban 7 pertanyaan keamanan (tabel 6.2) | Security Officer | 🔲 | Minggu 4 |
| 12 | Konfirmasi SSL/TLS requirement | Security Officer | 🔲 | Minggu 4 |

### 8.3 Kebutuhan Go-Live (Dibutuhkan Minggu 25-28)

| No | Kebutuhan | PIC AHM | Status | Target |
|----|-----------|---------|--------|--------|
| 13 | Security review & approval | Security Officer | 🔲 | Minggu 25 |
| 14 | UAT participants (3-5 pengguna) | Business Owner | 🔲 | Minggu 25 |
| 15 | Go-live approval | Management | 🔲 | Minggu 28 |

### 8.4 Informasi yang Perlu Dikonfirmasi

| No | Informasi | Dibutuhkan Sebelum | PIC |
|----|-----------|-------------------|-----|
| 1 | Versi SCCM/MECM | Sprint 3 (Minggu 5) | SCCM Admin |
| 2 | Nama database SCCM | Sprint 3 (Minggu 5) | SCCM Admin |
| 3 | SQL Server version | Sprint 3 (Minggu 5) | DBA |
| 4 | TLS encryption di SQL Server? | Sprint 3 (Minggu 5) | DBA |
| 5 | Jumlah total assets di SCCM | Sprint 3 (Minggu 5) | SCCM Admin |
| 6 | SCCM data update frequency | Sprint 3 (Minggu 5) | SCCM Admin |
| 7 | Custom SCCM views yang ada? | Sprint 3 (Minggu 5) | SCCM Admin |
| 8 | Hostname consistency GLPI ↔ SCCM | Sprint 3 (Minggu 5) | SCCM Admin + GLPI Admin |
| 9 | Password rotation policy | Sprint 1 (Minggu 1) | Security Officer |
| 10 | Data at rest encryption requirement? | Sprint 1 (Minggu 1) | Security Officer |
| 11 | SIEM/log aggregation system? | Sprint 1 (Minggu 1) | Security Officer |
| 12 | Vulnerability scanning policy? | Sprint 1 (Minggu 1) | Security Officer |
| 13 | Chat history retention policy? | Sprint 1 (Minggu 1) | Security Officer |
| 14 | AI/LLM approval untuk data internal? | Sprint 1 (Minggu 1) | Management |
| 15 | Data classification yang berlaku? | Sprint 1 (Minggu 1) | Security Officer |
| 16 | Proxy configuration untuk outbound? | Sprint 1 (Minggu 1) | Network Admin |
| 17 | Maintenance window SCCM | Sprint 3 (Minggu 5) | SCCM Admin |
| 18 | Data sensitif di SCCM yang restricted? | Sprint 3 (Minggu 5) | SCCM Admin + Security |

---

## Lampiran

### A. Referensi Arsitektur Detail

Untuk detail teknis implementasi lengkap, silakan merujuk ke:
- `BLUEPRINT.md` — Blueprint teknis Phase 2 (tersedia di repository proyek)

### B. Query SQL Contoh (GLPI DB)

Berikut contoh query yang akan dijalankan oleh AI Engine ke GLPI DB:

```sql
-- Distribusi aset berdasarkan status
SELECT states.name AS status, COUNT(*) AS count
FROM glpi_computers c
LEFT JOIN glpi_states states ON states.id = c.states_id
WHERE c.is_deleted = 0 AND c.is_template = 0
GROUP BY c.states_id, states.name;

-- Distribusi usia aset
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
GROUP BY age_group;

-- Frekuensi tiket per komputer (6 bulan terakhir)
SELECT
    items.items_id AS computer_id,
    c.name AS computer_name,
    COUNT(DISTINCT t.id) AS ticket_count
FROM glpi_items_tickets items
JOIN glpi_tickets t ON t.id = items.tickets_id
JOIN glpi_computers c ON c.id = items.items_id
WHERE items.itemtype = 'Computer'
  AND t.date >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
  AND c.is_deleted = 0
GROUP BY items.items_id, c.name
ORDER BY ticket_count DESC;
```

### C. Query SQL Contoh (SCCM DB)

```sql
-- Daftar semua sistem aktif
SELECT ResourceID, Name0 AS hostname, Operating_System_Name_and0 AS os_name, Active0
FROM v_R_System
WHERE Obsolete0 = 0
ORDER BY Name0;

-- Patch compliance per aset
SELECT
    COUNT(*) AS total_updates,
    SUM(CASE WHEN cs.Status = 3 THEN 1 ELSE 0 END) AS installed,
    SUM(CASE WHEN cs.Status = 2 THEN 1 ELSE 0 END) AS missing
FROM v_Update_ComplianceStatus cs
WHERE cs.ResourceID = @ResourceID;

-- Hardware detail per aset
SELECT cs.Manufacturer0, cs.Model0, os.Name0 AS os_name, proc.Name0 AS processor
FROM v_GS_COMPUTER_SYSTEM cs
LEFT JOIN v_GS_OPERATING_SYSTEM os ON os.ResourceID = cs.ResourceID
LEFT JOIN v_GS_PROCESSOR proc ON proc.ResourceID = cs.ResourceID
WHERE cs.ResourceID = @ResourceID;
```

---

> **Dokumen ini bersifat living document dan akan di-update seiring progres koordinasi dengan AHM.**  
> **Terakhir diupdate:** Juli 2026
