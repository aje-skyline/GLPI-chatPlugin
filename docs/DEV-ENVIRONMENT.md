# Local Development Environment Guide

> **Versi:** 1.0  
> **Terakhir diupdate:** Juli 2026  
> **Tujuan:** Panduan setup environment development untuk Phase 2 GLPI AI Extension

---

## Daftar Isi

1. [Arsitektur Development](#1-arsitektur-development)
2. [Server AI Engine (172.16.14.141)](#2-server-ai-engine-1721614141)
3. [Server GLPI (172.16.14.103)](#3-server-glpi-1721614103)
4. [Local Machine Setup](#4-local-machine-setup)
5. [Development Workflow](#5-development-workflow)
6. [Mock Mode Development](#6-mock-mode-development)
7. [Testing Setup](#7-testing-setup)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Arsitektur Development

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Development Environment                         │
│                                                                     │
│  ┌─────────────────────┐        ┌─────────────────────────────┐    │
│  │  Local Machine       │        │  Server 172.16.14.141       │    │
│  │  (Laptop/PC Anda)    │        │  (AI Engine)                │    │
│  │                      │        │                             │    │
│  │  - Code editor       │  SSH   │  - Docker (NEW)             │    │
│  │  - Git client        ├───────►│  - FastAPI app              │    │
│  │  - Browser (test)    │  push  │  - Celery worker            │    │
│  │  - API test tools    │  pull  │  - Redis                    │    │
│  └─────────────────────┘        └──────────┬──────────────────┘    │
│                                            │                       │
│                                   ┌────────┴────────┐             │
│                                   │  AI Gateway      │             │
│                                   │  (LLM Internal)  │             │
│                                   └─────────────────┘             │
│                                                                     │
│  ┌─────────────────────────────┐                                   │
│  │  Server 172.16.14.103       │                                   │
│  │  (GLPI + Plugin)            │                                   │
│  │                             │                                   │
│  │  - GLPI 11.0.6              │                                   │
│  │  - MariaDB                  │                                   │
│  │  - Plugin chatbot/          │                                   │
│  └─────────────────────────────┘                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Prinsip Development

| Prinsip | Implementasi |
|---------|--------------|
| **Tidak ganggu production** | Docker di 141 berjalan di port berbeda saat dev, service existing tetap jalan |
| **Iterative deployment** | Kode di-push ke server, auto-reload/restart |
| **Mock first** | Fitur yang butuh resource AHM (SCCM, DB) di-mock dulu |
| **Test sebelum deploy** | Unit test di local, integration test di server |

---

## 2. Server AI Engine (172.16.14.141)

### 2.1 Kondisi Saat Ini

Service yang sudah berjalan di server ini:

| Service | Port | Status |
|---------|------|--------|
| FastAPI (uvicorn) | 8000 | ✅ Running (tanpa Docker) |
| AI Gateway connection | 443 (outbound) | ✅ Working |

### 2.2 Setup Docker Tanpa Ganggu Service Existing

**Langkah 1: Install Docker CE** (jika belum ada)

```bash
# SSH ke server
ssh <user>@172.16.14.141

# Cek apakah Docker sudah terinstall
docker --version
docker compose version

# Jika belum, install Docker CE:
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Tambahkan user ke docker group (agar tidak perlu sudo)
sudo usermod -aG docker $USER
# Logout dan login lagi agar group berlaku
```

**Langkah 2: Stop service uvicorn yang sudah jalan**

```bash
# Cek process uvicorn yang berjalan
ps aux | grep uvicorn

# Stop process (sesuaikan PID)
kill <PID>

# ATAU jika menggunakan systemd:
sudo systemctl stop chatbot-fastapi  # jika ada service file
```

**Langkah 3: Setup project directory**

```bash
# Project sudah ada di /home/ariel/projects/chatbot-fastapi
cd /home/ariel/projects/chatbot-fastapi

# Buat docker directory
mkdir -p docker
```

**Langkah 4: Konfigurasi .env untuk Docker**

```bash
# Backup .env yang ada
cp .env .env.backup

# Edit .env — ubah REDIS_HOST untuk Docker
# REDIS_HOST=redis  (bukan localhost)
```

**Langkah 5: Build dan start Docker**

```bash
# Build images
docker compose -f docker/docker-compose.yml build

# Start semua service
docker compose -f docker/docker-compose.yml up -d

# Cek status
docker compose -f docker/docker-compose.yml ps

# Cek logs
docker compose -f docker/docker-compose.yml logs -f ai-engine
```

### 2.3 Development Mode Setup

Untuk development dengan hot-reload (kode berubah → auto-restart):

**Opsi A: Docker dengan volume mount (Recommended)**

Modifikasi `docker/docker-compose.yml` untuk dev:

```yaml
# Override untuk development — buat file docker/docker-compose.dev.yml
services:
  ai-engine:
    volumes:
      - ../app:/app          # Mount source code
    command: ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    environment:
      - PYTHONPATH=/app
```

```bash
# Jalankan dengan dev override:
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d
```

**Opsi B: Tanpa Docker (seperti saat ini, untuk debugging)**

```bash
# Stop Docker containers
docker compose -f docker/docker-compose.yml down

# Jalankan Redis saja via Docker
docker run -d --name redis-dev -p 6379:6379 redis:7-alpine

# Jalankan FastAPI langsung (dengan hot-reload)
cd /home/ariel/projects/chatbot-fastapi
REDIS_HOST=localhost uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Di terminal lain, jalankan Celery worker
REDIS_HOST=localhost uv run celery -A app.workers.celery_app worker --loglevel=info
```

### 2.4 Port Management

| Service | Port | Keterangan |
|---------|------|------------|
| FastAPI (Docker) | 8000 | Sama seperti sebelumnya |
| Redis (Docker) | 6379 | Baru |
| FastAPI (non-Docker fallback) | 8000 | Jika Docker bermasalah |

> **Catatan:** Port 8000 tetap sama sehingga GLPI Plugin tidak perlu diubah konfigurasi API URL-nya.

---

## 3. Server GLPI (172.16.14.103)

### 3.1 Kondisi Saat Ini

| Komponen | Lokasi | Status |
|----------|--------|--------|
| GLPI 11.0.6 | `/var/www/glpi/` | ✅ Running |
| Plugin chatbot | `/var/www/glpi/plugins/chatbot/` | ✅ Active |
| MariaDB | Local (3306) | ✅ Running |

### 3.2 Development Workflow Plugin

**Akses via SSH:**

```bash
# SSH ke server GLPI
ssh <user>@172.16.14.103

# Navigasi ke plugin directory
cd /var/www/glpi/plugins/chatbot
```

**Edit file langsung di server:**

```bash
# Menggunakan nano/vim
nano inc/config.class.php

# ATAU menggunakan editor lokal + SSH (VS Code Remote SSH, etc)
# Di VS Code: Install "Remote - SSH" extension
# Cmd+Shift+P → "Remote-SSH: Connect to Host" → <user>@172.16.14.103
# Open folder: /var/www/glpi/plugins/chatbot
```

**Workflow edit → test:**

```
1. Edit file di server (SSH / VS Code Remote)
2. Save file
3. Refresh browser → GLPI → Tools → AI Chatbot
4. Jika ada PHP error, cek: tail -f /var/www/glpi/files/_log/php-errors.log
5. Jika ada perubahan hook.php/setup.php, perlu reinstall plugin:
   - GLPI → Setup → Plugins → Chatbot → Uninstall → Install → Activate
```

### 3.3 Backup Plugin Sebelum Modifikasi

```bash
# Sebelum mulai Sprint 1-2, backup plugin yang sudah berfungsi:
cd /var/www/glpi/plugins
cp -r chatbot chatbot.bak.$(date +%Y%m%d)

# Backup database plugin
mysqldump -u root glpi glpi_plugin_chatbot_sessions glpi_plugin_chatbot_messages > /tmp/chatbot_db_backup.sql
```

### 3.4 GLPI Log Monitoring

```bash
# Monitor error log saat development
tail -f /var/www/glpi/files/_log/php-errors.log

# Monitor SQL errors
tail -f /var/www/glpi/files/_log/sql-errors.log

# Monitor access log (jika perlu debug AJAX)
tail -f /var/log/apache2/access.log | grep chatbot
# ATAU
tail -f /var/log/nginx/access.log | grep chatbot
```

### 3.5 Twig Template Development

GLPI 11 menggunakan Twig. Untuk development template:

```bash
# Twig cache mungkin perlu di-clear setelah edit template
rm -rf /var/www/glpi/files/_cache/twig/*

# ATAU di GLPI UI:
# Setup → General → Maintenance → Clear cache
```

---

## 4. Local Machine Setup

### 4.1 Tools yang Dibutuhkan

| Tool | Versi | Fungsi | Install |
|------|-------|--------|---------|
| **Git** | 2.x+ | Version control | `sudo apt install git` |
| **SSH client** | - | Remote ke server | Built-in |
| **Code Editor** | - | Edit kode (VS Code recommended) | VS Code + Remote-SSH extension |
| **API Test Tool** | - | Test endpoints | cURL / Postman / httpie |
| **Python 3.12+** | 3.12 | Run local scripts/tests | `pyenv install 3.12` |
| **uv** | latest | Python package manager | `pip install uv` |

### 4.2 Git Clone (jika bekerja dari local)

```bash
# Clone AI Engine repo
cd ~/projects
git clone <repo-url> chatbot-fastapi
cd chatbot-fastapi

# Setup virtual environment
uv sync

# Copy .env
cp .env.example .env
# Edit .env dengan konfigurasi development
```

### 4.3 VS Code Remote SSH Setup

```json
// ~/.ssh/config — tambahkan:
Host glpi-server
    HostName 172.16.14.103
    User <username>
    IdentityFile ~/.ssh/id_rsa

Host ai-server
    HostName 172.16.14.141
    User <username>
    IdentityFile ~/.ssh/id_rsa
```

Di VS Code:
1. Install extension **Remote - SSH**
2. `Cmd+Shift+P` → `Remote-SSH: Connect to Host`
3. Pilih `ai-server` atau `glpi-server`
4. Open folder sesuai kebutuhan

---

## 5. Development Workflow

### 5.1 AI Engine Development Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                    AI Engine Dev Flow                             │
│                                                                  │
│  1. Edit kode (local atau SSH ke 141)                            │
│     ├── Jika local: git push → SSH ke 141 → git pull            │
│     └── Jika SSH langsung: edit di server                       │
│                                                                  │
│  2. Test perubahan                                               │
│     ├── Jika Docker + volume mount: auto-reload                  │
│     ├── Jika Docker tanpa mount: rebuild + restart               │
│     └── Jika non-Docker: uvicorn --reload auto-restart           │
│                                                                  │
│  3. Verify                                                       │
│     ├── curl http://172.16.14.141:8000/health                    │
│     ├── curl chat endpoint test                                  │
│     └── Browser: GLPI chat → test message                       │
│                                                                  │
│  4. Commit                                                       │
│     └── git add + commit + push                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 GLPI Plugin Development Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                    Plugin Dev Flow                                │
│                                                                  │
│  1. Edit file di server 103 (SSH / VS Code Remote)              │
│                                                                  │
│  2. Test perubahan                                               │
│     ├── PHP file: refresh browser (GLPI auto-reload PHP)        │
│     ├── JS/CSS file: hard refresh browser (Ctrl+Shift+R)        │
│     ├── Twig template: clear GLPI cache jika perlu              │
│     └── hook.php/setup.php: reinstall plugin di GLPI UI         │
│                                                                  │
│  3. Verify                                                       │
│     ├── Browser: GLPI → Tools → AI Chatbot                      │
│     ├── Browser: GLPI → Tools → Chatbot Configuration           │
│     └── Browser: GLPI → Asset Health Dashboard                  │
│                                                                  │
│  4. Backup & Commit                                              │
│     └── Jika plugin repo sudah git: git add + commit + push     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 Cross-Server Testing

Saat menguji integrasi Plugin ↔ AI Engine:

```
1. Pastikan AI Engine running di 172.16.14.141:8000
   → curl http://172.16.14.141:8000/health

2. Pastikan GLPI Plugin config mengarah ke AI Engine
   → GLPI → Tools → Chatbot Configuration
   → API URL: http://172.16.14.141:8000/v1/chat/completions

3. Test dari browser GLPI
   → GLPI → Tools → AI Chatbot → kirim pesan

4. Monitor AI Engine logs
   → SSH ke 141: docker compose logs -f ai-engine
   → ATAU: tail -f logs (jika non-Docker)
```

---

## 6. Mock Mode Development

### 6.1 Kapan Menggunakan Mock Mode

| Skenario | Mock Apa | Cara |
|----------|----------|------|
| SCCM DB belum tersedia | SCCM connector | `sccm_db_host` kosong → SCCM features auto-disabled |
| GLPI DB read-only belum tersedia | GLPI DB connector | Gunakan REST API saja (seperti saat ini) |
| AI Gateway down | LLM responses | `MOCK_MODE=true` di `.env` |
| Development tanpa server | Semua | Local Python + mock data |

### 6.2 SCCM Mock

SCCM connector sudah dirancang untuk graceful degradation:

```bash
# Di .env — biarkan SCCM config kosong:
SCCM_DB_HOST=
SCCM_DB_PORT=1433
SCCM_DB_NAME=
SCCM_DB_USER=
SCCM_DB_PASSWORD=
```

Ketika `sccm_db_host` kosong:
- `init_sccm_db()` tidak dipanggil
- SCCM tools return pesan "SCCM tidak tersedia"
- Health scoring menggunakan penalty default (15) untuk patch compliance
- Correlation endpoint return error "SCCM not configured"

### 6.3 GLPI DB Mock

Jika GLPI DB read-only account belum tersedia, gunakan REST API:

```bash
# Di .env — biarkan GLPI DB config kosong atau salah:
GLPI_DB_HOST=
# ATAU
GLPI_DB_HOST=not_configured
```

AI Engine akan:
- Log warning "GLPI DB not configured"
- Health endpoints return error "GLPI DB not available"
- Chat tetap berfungsi (menggunakan REST API seperti saat ini)

### 6.4 Full Mock Mode (Local Development Tanpa Server)

Untuk develop di local machine tanpa akses ke server manapun:

```bash
# .env untuk full mock
AI_GATEWAY_URL=https://ai-gw.stidev.biz.id/v1/chat/completions
AI_GATEWAY_BASE_URL=https://ai-gw.stidev.biz.id/v1
AI_GATEWAY_API_KEY=sk-xxx
AI_MODEL=qwen/qwen3-next-80b-a3b-instruct
GATEWAY_API_KEY=internal-glpi-secret-123
ALLOWED_ORIGINS=http://localhost:3000
MOCK_MODE=true

# GLPI REST API (jika bisa reach dari local)
GLPI_URL=https://172.16.14.103
GLPI_API_URL=https://172.16.14.103/asset/apirest.php
GLPI_APP_TOKEN=
GLPI_USER_TOKEN=xxx
GLPI_VERIFY_SSL=false

# DB connectors — kosongkan
GLPI_DB_HOST=
SCCM_DB_HOST=

# Redis — local
REDIS_HOST=localhost
REDIS_PORT=6379
```

```bash
# Jalankan Redis lokal
docker run -d --name redis-dev -p 6379:6379 redis:7-alpine

# Jalankan FastAPI
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Test
curl http://localhost:8000/health
```

---

## 7. Testing Setup

### 7.1 Unit Test (Local)

```bash
cd /home/ariel/projects/chatbot-fastapi

# Install dev dependencies
uv sync --dev

# Jalankan semua tests
uv run pytest tests/ -v

# Jalankan dengan coverage
uv run pytest tests/ -v --cov=app --cov-report=term-missing

# Jalankan test spesifik
uv run pytest tests/test_health_scorer.py -v

# Jalankan hanya unit tests (tanpa integration)
uv run pytest tests/ -v -m "not integration"
```

### 7.2 Integration Test (Server 141)

```bash
# SSH ke server
ssh <user>@172.16.14.141

# Pastikan Docker stack running
docker compose -f docker/docker-compose.yml ps

# Test health endpoint
curl http://localhost:8000/health

# Test chat endpoint
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"halo"}]}'

# Test health dashboard
curl http://localhost:8000/api/health/dashboard

# Test health report (jika GLPI DB connected)
curl http://localhost:8000/api/health/report/1
```

### 7.3 End-to-End Test (Browser)

```
1. Buka browser → https://172.16.14.103 (GLPI)
2. Login
3. Navigasi ke Tools → AI Chatbot
4. Kirim pesan: "Halo"
5. Verifikasi: respons diterima (streaming atau non-streaming)
6. Kirim pesan: "Daftar komputer saya"
7. Verifikasi: respons berisi data dari GLPI
```

---

## 8. Troubleshooting

### 8.1 AI Engine (Server 141)

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| Docker build gagal | Dependency install error | Cek `pyproject.toml`, run `uv sync` lokal dulu |
| Port 8000 sudah dipakai | uvicorn lama masih jalan | `lsof -i :8000` → `kill <PID>` |
| Redis connection refused | Redis container belum up | `docker compose -f docker/docker-compose.yml start redis` |
| Celery worker tidak connect | Redis host salah | Cek `REDIS_HOST` di `.env` (harus `redis` di Docker) |
| Hot-reload tidak bekerja | Volume mount tidak aktif | Gunakan `docker-compose.dev.yml` override |
| GLPI DB connection failed | Firewall / credentials | Cek dari server: `mysql -h 172.16.14.103 -u glpi_ai_readonly -p` |

### 8.2 GLPI Plugin (Server 103)

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| Plugin tidak muncul di menu | setup.php/hook.php error | Cek `php-errors.log`, reinstall plugin |
| Chat tidak merespons | AI Engine unreachable | Cek dari server: `curl http://172.16.14.141:8000/health` |
| Config page 404 | `config_page` hook belum terdaftar | Cek `setup.php` → `plugin_init_chatbot()` |
| Twig template tidak render | Cache belum clear | `rm -rf /var/www/glpi/files/_cache/twig/*` |
| AJAX 403 Forbidden | CSRF token salah | Cek `X-Glpi-Csrf-Token` header di request |
| Session table error | Tabel belum dibuat | Reinstall plugin (hook.php akan create tables) |

### 8.3 Connectivity Issues

```bash
# Dari server 141, test koneksi ke GLPI DB:
mysql -h 172.16.14.103 -P 3306 -u glpi_ai_readonly -p glpi

# Dari server 141, test koneksi ke SCCM DB (jika sudah ada):
# Install freetds first: sudo apt install freetds-bin
tsql -H <sccm-host> -p 1433 -U sccm_ai_readonly -P <password>

# Dari server 103, test koneksi ke AI Engine:
curl http://172.16.14.141:8000/health

# Dari local machine, test koneksi ke kedua server:
ssh <user>@172.16.14.141 "curl -s http://localhost:8000/health"
ssh <user>@172.16.14.103 "curl -s http://localhost/apirest.php/initSession"
```

---

## Appendix: Quick Reference Commands

### AI Engine (Server 141)

```bash
# Docker operations
docker compose -f docker/docker-compose.yml up -d        # Start
docker compose -f docker/docker-compose.yml down          # Stop
docker compose -f docker/docker-compose.yml restart       # Restart
docker compose -f docker/docker-compose.yml logs -f       # Logs
docker compose -f docker/docker-compose.yml ps            # Status

# Rebuild setelah code change (tanpa volume mount)
docker compose -f docker/docker-compose.yml build ai-engine
docker compose -f docker/docker-compose.yml up -d ai-engine

# Celery operations
docker exec glpi-ai-worker uv run celery -A app.workers.celery_app inspect active
docker exec glpi-ai-worker uv run celery -A app.workers.celery_app inspect ping

# Redis operations
docker exec glpi-ai-redis redis-cli ping
docker exec glpi-ai-redis redis-cli info memory
docker exec glpi-ai-redis redis-cli flushdb   # ⚠️ Hati-hati! Clear semua data
```

### GLPI Plugin (Server 103)

```bash
# File operations
ls -la /var/www/glpi/plugins/chatbot/
tail -f /var/www/glpi/files/_log/php-errors.log

# Database operations
mysql -u root glpi -e "SHOW TABLES LIKE 'glpi_plugin_chatbot%';"
mysql -u root glpi -e "SELECT * FROM glpi_plugin_chatbot_config;"

# Cache clear
rm -rf /var/www/glpi/files/_cache/twig/*

# Plugin reinstall (via CLI — jika memungkinkan)
php /var/www/glpi/bin/console plugin:install chatbot
php /var/www/glpi/bin/console plugin:activate chatbot
```
