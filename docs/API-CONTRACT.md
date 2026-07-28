# API Contract — Plugin ↔ AI Engine

> **Versi:** 1.0  
> **Scope:** Interface antara GLPI Plugin (PHP) dan AI Engine (FastAPI)  
> **Base URL:** `http://<ai-engine-host>:8000`  
> **Protokol:** HTTP/1.1, HTTPS (jika SSL tersedia)  
> **Auth:** Bearer Token (`GATEWAY_API_KEY`)

---

## Daftar Isi

1. [Autentikasi](#1-autentikasi)
2. [Chat Endpoint](#2-chat-endpoint)
3. [Health Analysis Endpoints](#3-health-analysis-endpoints)
4. [Configuration Endpoints](#4-configuration-endpoints)
5. [System Endpoints](#5-system-endpoints)
6. [Error Response Format](#6-error-response-format)
7. [SSE Streaming Protocol](#7-sse-streaming-protocol)
8. [Data Types Reference](#8-data-types-reference)

---

## 1. Autentikasi

### 1.1 Mechanism

Semua endpoint yang memerlukan autentikasi menggunakan **Bearer Token** di header `Authorization`.

```
Authorization: Bearer <GATEWAY_API_KEY>
```

### 1.2 Token

| Parameter | Nilai |
|-----------|-------|
| Token | `GATEWAY_API_KEY` dari `.env` AI Engine |
| Default | `internal-glpi-secret-123` |
| Disimpan di Plugin | `glpi_plugin_chatbot_config` table, key `api_key` |
| Rotasi | Manual — update di Plugin Config Page dan AI Engine `.env` |

### 1.3 Endpoint Auth Requirement

| Endpoint | Auth Required | Catatan |
|----------|--------------|---------|
| `GET /health` | ❌ No | Public health check |
| `POST /v1/chat/completions` | ✅ Yes | Chat |
| `POST /api/health/analyze` | ✅ Yes | ⏳ PLANNED — Phase 2 |
| `GET /api/health/status/{job_id}` | ❌ No | ⏳ PLANNED — Phase 2 |
| `GET /api/health/report/{asset_id}` | ❌ No | ⏳ PLANNED — Phase 2 |
| `GET /api/health/dashboard` | ❌ No | ⏳ PLANNED — Phase 2 |
| `POST /api/health/correlate` | ✅ Yes | ⏳ PLANNED — Phase 2 |
| `GET /api/config` | ✅ Yes | ⏳ PLANNED — Phase 2 |
| `PUT /api/config` | ✅ Yes | ⏳ PLANNED — Phase 2 |

---

## 2. Chat Endpoint

### 2.1 POST /v1/chat/completions

OpenAI-compatible chat endpoint. Mendukung streaming (SSE) dan non-streaming.

**Request:**

```http
POST /v1/chat/completions HTTP/1.1
Host: <ai-engine-host>:8000
Authorization: Bearer <GATEWAY_API_KEY>
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "Daftar komputer saya"}
  ],
  "glpi_user_id": 5,
  "session_id": "abc-123-def",
  "stream": false
}
```

**Request Schema:**

| Field | Type | Required | Default | Deskripsi |
|-------|------|----------|---------|-----------|
| `messages` | `array<Message>` | ✅ Yes | — | Daftar pesan percakapan |
| `glpi_user_id` | `integer` | ❌ No | `0` | ID user GLPI (untuk user context) |
| `session_id` | `string` | ❌ No | auto-generated | Session ID percakapan |
| `stream` | `boolean` | ❌ No | `false` | Aktifkan SSE streaming |

**Message Schema:**

| Field | Type | Required | Deskripsi |
|-------|------|----------|-----------|
| `role` | `string` | ✅ Yes | `"user"`, `"assistant"`, atau `"system"` |
| `content` | `string` | ✅ Yes | Isi pesan (max 10.000 karakter) |

**Non-Streaming Response (200 OK):**

```json
{
  "id": "glpi-crew-a1b2c3d4",
  "object": "chat.completion",
  "model": "qwen/qwen3-next-80b-a3b-instruct",
  "session_id": "abc-123-def",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Berikut daftar komputer Anda:\n1. PC-001 (Dell Latitude)\n2. PC-002 (HP EliteBook)"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

**Streaming Response:** Lihat [Bagian 7 — SSE Streaming Protocol](#7-sse-streaming-protocol)

**Error Responses:**

| Status | Code | Kondisi |
|--------|------|---------|
| 401 | `AUTH_INVALID` | API key salah atau tidak ada |
| 400 | `VALIDATION_ERROR` | Request body tidak valid |
| 429 | `RATE_LIMITED` | Terlalu banyak request |
| 500 | `INTERNAL_ERROR` | AI Engine error |
| 502 | `LLM_ERROR` | AI Gateway / LLM tidak bisa dijangkau |
| 504 | `LLM_TIMEOUT` | LLM response timeout |

---

## 3. Health Analysis Endpoints

> ⚠️ **PLANNED — Belum Diimplementasikan**  
> Endpoint di bagian ini adalah bagian dari **Phase 2** (SCCM Integration & Asset Health AI)  
> yang belum diimplementasikan. Kode aktual saat ini (v3.0.0) hanya memiliki:
> - `GET /health` — Health check
> - `POST /v1/chat/completions` — Chat endpoint
>
> Silakan lihat `docs/planned/` untuk detail roadmap Phase 2.

### 3.1 POST /api/health/analyze

Trigger health analysis sebagai background Celery task.

**Request:**

```http
POST /api/health/analyze HTTP/1.1
Host: <ai-engine-host>:8000
Authorization: Bearer <GATEWAY_API_KEY>
Content-Type: application/json

{
  "computer_id": 42,
  "analyze_all": false
}
```

**Request Schema:**

| Field | Type | Required | Default | Deskripsi |
|-------|------|----------|---------|-----------|
| `computer_id` | `integer` | ❌ No | — | ID komputer spesifik (GLPI DB id) |
| `analyze_all` | `boolean` | ❌ No | `false` | Analisis semua aset |

> **Catatan:** Harus specify salah satu: `computer_id` atau `analyze_all=true`. Jika keduanya tidak ada, return 400.

**Response (202 Accepted):**

```json
{
  "job_id": "c8d9e0f1-2345-6789-abcd-ef0123456789",
  "status": "started"
}
```

**Response Schema:**

| Field | Type | Deskripsi |
|-------|------|-----------|
| `job_id` | `string` | Celery task ID — gunakan untuk poll status |
| `status` | `string` | `"started"` |

---

### 3.2 GET /api/health/status/{job_id}

Check status background analysis job.

**Request:**

```http
GET /api/health/status/c8d9e0f1-2345-6789-abcd-ef0123456789 HTTP/1.1
Host: <ai-engine-host>:8000
```

**Response — In Progress (200 OK):**

```json
{
  "job_id": "c8d9e0f1-2345-6789-abcd-ef0123456789",
  "status": "PROGRESS",
  "progress": {
    "step": "analyzing",
    "current": 15,
    "total": 50,
    "current_computer": "PC-015",
    "progress_pct": 30.0
  }
}
```

**Response — Completed (200 OK):**

```json
{
  "job_id": "c8d9e0f1-2345-6789-abcd-ef0123456789",
  "status": "SUCCESS",
  "result": {
    "status": "completed",
    "total_analyzed": 50,
    "summary": {
      "critical": 3,
      "high": 8,
      "medium": 15,
      "low": 24,
      "error": 0
    },
    "results": [
      {
        "status": "completed",
        "computer_id": 1,
        "computer_name": "PC-001",
        "health_score": 85,
        "risk_category": "Low",
        "factors": { "...": "..." },
        "recommendations": ["[INFO] Aset dalam kondisi baik"],
        "sccm_correlation": "matched"
      }
    ]
  }
}
```

**Response — Failed (200 OK):**

```json
{
  "job_id": "c8d9e0f1-2345-6789-abcd-ef0123456789",
  "status": "FAILURE",
  "error": "GLPI DB connection refused"
}
```

**Status Values:**

| Status | Arti |
|--------|------|
| `PENDING` | Task queued, belum mulai |
| `PROGRESS` | Task sedang berjalan |
| `SUCCESS` | Task selesai, result tersedia |
| `FAILURE` | Task gagal, error tersedia |
| `REVOKED` | Task dibatalkan |
| `STARTED` | Task baru dimulai |

---

### 3.3 GET /api/health/report/{asset_id}

Get health report untuk satu aset secara synchronous (tanpa Celery).

**Request:**

```http
GET /api/health/report/42 HTTP/1.1
Host: <ai-engine-host>:8000
```

**Response (200 OK):**

```json
{
  "computer_id": 42,
  "computer_name": "PC-042",
  "health_score": 45,
  "risk_category": "High",
  "factors": {
    "hardware_age": {
      "penalty": 20,
      "weight": 0.2,
      "detail": "> 6 years"
    },
    "ticket_frequency": {
      "penalty": 20,
      "weight": 0.25,
      "ticket_count": 5
    },
    "patch_compliance": {
      "penalty": 10,
      "weight": 0.25,
      "compliance": {
        "total_updates": 100,
        "installed": 85,
        "missing": 10,
        "unknown": 5,
        "compliance_pct": 85.0
      }
    },
    "warranty_status": {
      "penalty": 20,
      "weight": 0.15,
      "status": "expired"
    },
    "sccm_correlation": {
      "penalty": 0,
      "weight": 0.15,
      "status": "matched"
    }
  },
  "recommendations": [
    "[HIGH] Pertimbangkan penggantian hardware — aset sudah berusia > 4 tahun",
    "[MEDIUM] Monitor frekuensi tiket — ada tren peningkatan masalah",
    "[HIGH] Garansi sudah expired — pertimbangkan perpanjangan atau penggantian"
  ],
  "sccm_correlation": "matched"
}
```

**Error Responses:**

| Status | Code | Kondisi |
|--------|------|---------|
| 404 | `NOT_FOUND` | Computer ID tidak ditemukan |
| 503 | `DB_UNAVAILABLE` | GLPI DB tidak bisa diakses |

---

### 3.4 GET /api/health/dashboard

Get dashboard summary data.

**Request:**

```http
GET /api/health/dashboard HTTP/1.1
Host: <ai-engine-host>:8000
```

**Response (200 OK):**

```json
{
  "total_computers": 500,
  "status_distribution": [
    {"status": "Production", "count": 350},
    {"status": "In repair", "count": 25},
    {"status": "Stock", "count": 125}
  ],
  "age_distribution": [
    {"age_group": "< 2 years", "count": 100},
    {"age_group": "2-4 years", "count": 200},
    {"age_group": "4-6 years", "count": 150},
    {"age_group": "> 6 years", "count": 50}
  ],
  "warranty_summary": {
    "active": 200,
    "expiring_soon": 50,
    "expired": 150,
    "no_warranty": 100
  }
}
```

**Response Schema:**

| Field | Type | Deskripsi |
|-------|------|-----------|
| `total_computers` | `integer` | Total aset aktif |
| `status_distribution` | `array<{status: string, count: int}>` | Distribusi per status |
| `age_distribution` | `array<{age_group: string, count: int}>` | Distribusi per usia |
| `warranty_summary` | `object` | Ringkasan garansi |

---

### 3.5 POST /api/health/correlate

Trigger GLPI-SCCM correlation sebagai background task.

**Request:**

```http
POST /api/health/correlate HTTP/1.1
Host: <ai-engine-host>:8000
Authorization: Bearer <GATEWAY_API_KEY>
```

**Response (202 Accepted):**

```json
{
  "job_id": "d9e0f1a2-3456-7890-bcde-f01234567890",
  "status": "started"
}
```

**Job Result (via GET /api/health/status/{job_id}):**

```json
{
  "status": "completed",
  "total_assets": 500,
  "summary": {
    "matched": 420,
    "mismatch": 30,
    "missing_in_sccm": 25,
    "missing_in_glpi": 25
  },
  "details": [
    {
      "glpi_asset": {
        "source": "glpi",
        "hostname": "PC-001",
        "manufacturer": "Dell",
        "os_name": "Windows 11 Pro",
        "glpi_id": 1
      },
      "sccm_asset": {
        "source": "sccm",
        "hostname": "PC-001",
        "manufacturer": "Dell Inc.",
        "os_name": "Microsoft Windows 11 Pro",
        "sccm_resource_id": 100
      },
      "match_status": "mismatch",
      "mismatches": [
        {"field": "manufacturer", "glpi": "Dell", "sccm": "Dell Inc."},
        {"field": "os_name", "glpi": "Windows 11 Pro", "sccm": "Microsoft Windows 11 Pro"}
      ],
      "match_method": "hostname",
      "match_confidence": 0.7
    }
  ]
}
```

---

## 4. Configuration Endpoints

> ⚠️ **PLANNED — Belum Diimplementasikan**  
> Endpoint konfigurasi ini adalah bagian dari **Phase 2** yang belum ada di kode.

### 4.1 GET /api/config

Get AI Engine configuration (non-sensitive values only).

**Request:**

```http
GET /api/config HTTP/1.1
Host: <ai-engine-host>:8000
Authorization: Bearer <GATEWAY_API_KEY>
```

**Response (200 OK):**

```json
{
  "ai_model": "qwen/qwen3-next-80b-a3b-instruct",
  "glpi_db_status": "ok",
  "sccm_db_status": "not_configured",
  "redis_status": "ok",
  "session_ttl_minutes": 60,
  "crew_verbose": false,
  "mock_mode": false
}
```

### 4.2 PUT /api/config

Update AI Engine configuration (runtime, tanpa restart).

**Request:**

```http
PUT /api/config HTTP/1.1
Host: <ai-engine-host>:8000
Authorization: Bearer <GATEWAY_API_KEY>
Content-Type: application/json

{
  "crew_verbose": true,
  "session_ttl_minutes": 120
}
```

**Response (200 OK):**

```json
{
  "status": "updated",
  "updated_keys": ["crew_verbose", "session_ttl_minutes"]
}
```

> **Catatan:** Hanya config yang bisa diubah runtime yang tersedia di endpoint ini. Perubahan `ai_gateway_url`, `glpi_db_*`, `sccm_db_*` memerlukan restart container.

---

## 5. System Endpoints

### 5.1 GET /health

Public health check — tidak memerlukan autentikasi.

**Request:**

```http
GET /health HTTP/1.1
Host: <ai-engine-host>:8000
```

**Response (200 OK):**

```json
{
  "status": "ok",
  "service": "GLPI AI Gateway",
  "version": "3.0.0",
  "ai_model": "qwen/qwen3-next-80b-a3b-instruct",
  "architecture": "CrewAI Sequential + Health Analysis",
  "streaming": "emulated-sse",
  "glpi_db": {
    "status": "ok",
    "version": "10.11.8-MariaDB"
  },
  "sccm_db": {
    "status": "not_configured"
  },
  "redis": {
    "status": "ok"
  },
  "active_sessions": 3,
  "total_session_messages": 45
}
```

---

## 6. Error Response Format

### 6.1 Standard Error Response

Semua error mengikuti format ini:

```json
{
  "error": {
    "code": "AUTH_INVALID",
    "message": "Missing or invalid authorization",
    "detail": null
  }
}
```

**Error Schema:**

| Field | Type | Deskripsi |
|-------|------|-----------|
| `error.code` | `string` | Error code (machine-readable) |
| `error.message` | `string` | Pesan error (human-readable) |
| `error.detail` | `string|null` | Detail tambahan (opsional) |

### 6.2 Error Codes

#### Authentication Errors (401)

| Code | HTTP Status | Kondisi |
|------|-------------|---------|
| `AUTH_MISSING` | 401 | Header Authorization tidak ada |
| `AUTH_INVALID` | 401 | Format Authorization salah (bukan Bearer) |
| `AUTH_TOKEN_INVALID` | 401 | API key tidak valid |

#### Validation Errors (400)

| Code | HTTP Status | Kondisi |
|------|-------------|---------|
| `VALIDATION_ERROR` | 400 | Request body tidak sesuai schema |
| `MISSING_PARAMETER` | 400 | Parameter required tidak ada |
| `INVALID_MESSAGE_FORMAT` | 400 | Format messages array salah |

#### Resource Errors (404, 409)

| Code | HTTP Status | Kondisi |
|------|-------------|---------|
| `NOT_FOUND` | 404 | Resource tidak ditemukan (computer_id, job_id) |
| `CONFLICT` | 409 | Conflict (sudah ada analysis running) |

#### Rate Limiting (429)

| Code | HTTP Status | Kondisi |
|------|-------------|---------|
| `RATE_LIMITED` | 429 | Terlalu banyak request dalam periode waktu |

#### Server Errors (500, 502, 503, 504)

| Code | HTTP Status | Kondisi |
|------|-------------|---------|
| `INTERNAL_ERROR` | 500 | Unexpected error di AI Engine |
| `LLM_ERROR` | 502 | AI Gateway / LLM tidak bisa dijangkau |
| `DB_UNAVAILABLE` | 503 | GLPI DB atau SCCM DB tidak bisa diakses |
| `SCCM_NOT_CONFIGURED` | 503 | SCCM DB belum dikonfigurasi |
| `LLM_TIMEOUT` | 504 | LLM response melebihi timeout |
| `CREW_ERROR` | 500 | CrewAI execution error |

### 6.3 Plugin Error Handling

Plugin PHP harus menangani error dari AI Engine:

```php
// Di ajax/chat.php — error handling pattern:

$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);

if ($httpCode === 401) {
    // API key salah — tampilkan pesan konfigurasi
    plugin_chatbot_stream_event('error', ['message' => 'API key tidak valid. Periksa konfigurasi plugin.']);
} elseif ($httpCode === 429) {
    // Rate limited — tampilkan pesan tunggu
    plugin_chatbot_stream_event('error', ['message' => 'Terlalu banyak request. Tunggu beberapa saat.']);
} elseif ($httpCode >= 500) {
    // Server error — tampilkan pesan generic
    plugin_chatbot_stream_event('error', ['message' => 'AI Engine sedang bermasalah. Coba lagi nanti.']);
}
```

---

## 7. SSE Streaming Protocol

### 7.1 Overview

Chat endpoint mendukung SSE (Server-Sent Events) streaming untuk respons real-time. Plugin PHP bertindak sebagai proxy: menerima SSE dari AI Engine, meneruskan ke browser.

### 7.2 Plugin → AI Engine Request (Streaming)

```http
POST /v1/chat/completions HTTP/1.1
Host: <ai-engine-host>:8000
Authorization: Bearer <GATEWAY_API_KEY>
Content-Type: application/json

{
  "messages": [{"role": "user", "content": "Halo"}],
  "stream": true
}
```

### 7.3 AI Engine → Plugin SSE Events

AI Engine mengirim SSE events dengan format:

```
event: <event_type>
data: <json_payload>

```

#### Event Types

| Event Type | Payload | Deskripsi |
|------------|---------|-----------|
| `thought` | `{"content": "..."}` | Agent thinking process (opsional, bisa di-skip di UI) |
| `status` | `{"message": "Processing..."}` | Status update saat CrewAI bekerja |
| `token` | `{"content": "word"}` | Token respons (word-by-word streaming) |
| `meta` | `{"session_id": "...", "model": "..."}` | Metadata respons |
| `error` | `{"code": "...", "message": "..."}` | Error terjadi |
| `done` | `{}` | Streaming selesai |

### 7.4 Plugin → Browser SSE Events

Plugin meneruskan events ke browser dengan format yang sama, ditambah:

| Event Type | Payload | Deskripsi |
|------------|---------|-----------|
| `heartbeat` | `{}` | Keep-alive setiap 2 detik |

### 7.5 Streaming Sequence

```
AI Engine                    Plugin (PHP)              Browser
    │                            │                        │
    │── event: status ──────────►│── event: status ──────►│
    │   {"message":"Processing"} │                        │
    │                            │                        │
    │── event: heartbeat ───────►│── event: heartbeat ───►│  (setiap 2 detik)
    │   {}                       │                        │
    │                            │                        │
    │── event: token ───────────►│── event: token ───────►│
    │   {"content":"Berikut"}    │                        │  (tampilkan "Berikut")
    │                            │                        │
    │── event: token ───────────►│── event: token ───────►│
    │   {"content":" daftar"}    │                        │  (tampilkan " daftar")
    │                            │                        │
    │── event: token ───────────►│── event: token ───────►│
    │   {"content":" komputer"}  │                        │  (tampilkan " komputer")
    │                            │                        │
    │── event: done ────────────►│── event: done ────────►│
    │   {}                       │                        │  (selesai)
    │                            │                        │
```

### 7.6 Browser JavaScript — SSE Consumer

```javascript
// Di js/chat.js — consumeStreamResponse()
async function consumeStreamResponse(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
            if (line.startsWith('event: ')) {
                currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
                const payload = JSON.parse(line.slice(6));
                handleSSEEvent(currentEvent, payload);
            }
        }
    }
}

function handleSSEEvent(eventType, payload) {
    switch (eventType) {
        case 'token':
            appendToken(payload.content);
            break;
        case 'status':
            showStatus(payload.message);
            break;
        case 'error':
            showError(payload.message);
            break;
        case 'done':
            finishResponse();
            break;
        case 'heartbeat':
            // keep-alive, ignore
            break;
    }
}
```

---

## 8. Data Types Reference

### 8.1 Health Score

| Range | Category | Color | Action |
|-------|----------|-------|--------|
| 71-100 | Low | 🟢 Green | No action needed |
| 51-70 | Medium | 🟡 Yellow | Monitor and plan |
| 31-50 | High | 🟠 Orange | Action within 1 month |
| 0-30 | Critical | 🔴 Red | Immediate action required |

### 8.2 Warranty Status

| Value | Arti |
|-------|------|
| `active` | Garansi masih berlaku |
| `expiring_soon` | Garansi berakhir < 6 bulan |
| `expired` | Garansi sudah berakhir |
| `no_warranty` | Tidak ada data garansi |

### 8.3 SCCM Correlation Status

| Value | Arti |
|-------|------|
| `matched` | Data GLPI dan SCCM konsisten |
| `mismatch` | Ada perbedaan data |
| `missing_in_sccm` | Ada di GLPI, tidak ada di SCCM |
| `missing_in_glpi` | Ada di SCCM, tidak ada di GLPI |
| `not_checked` | Belum dilakukan pengecekan |
| `sccm_unavailable` | SCCM DB tidak bisa diakses |

### 8.4 Celery Job Status

| Value | Arti |
|-------|------|
| `PENDING` | Task dalam antrian |
| `STARTED` | Task baru dimulai |
| `PROGRESS` | Task sedang berjalan (ada progress info) |
| `SUCCESS` | Task selesai berhasil |
| `FAILURE` | Task gagal |
| `REVOKED` | Task dibatalkan |

### 8.5 Recommendation Priority Tags

| Tag | Arti | Urgency |
|-----|------|---------|
| `[URGENT]` | Harus ditangani segera | < 24 jam |
| `[HIGH]` | Perlu tindakan dalam 1 bulan | < 30 hari |
| `[MEDIUM]` | Perlu perencanaan | < 90 hari |
| `[LOW]` | Monitor saja | Ongoing |
| `[INFO]` | Informasi saja | No action |

---

## Appendix: Postman Collection

Untuk testing, import collection berikut ke Postaman:

```json
{
  "info": {
    "name": "GLPI AI Engine API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    { "key": "base_url", "value": "http://172.16.14.141:8000" },
    { "key": "api_key", "value": "internal-glpi-secret-123" }
  ],
  "item": [
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/health"
      }
    },
    {
      "name": "Chat (Non-Streaming)",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/v1/chat/completions",
        "header": [
          { "key": "Authorization", "value": "Bearer {{api_key}}" },
          { "key": "Content-Type", "value": "application/json" }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\"messages\":[{\"role\":\"user\",\"content\":\"halo\"}],\"stream\":false}"
        }
      }
    },
    {
      "name": "Chat (Streaming)",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/v1/chat/completions",
        "header": [
          { "key": "Authorization", "value": "Bearer {{api_key}}" },
          { "key": "Content-Type", "value": "application/json" }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\"messages\":[{\"role\":\"user\",\"content\":\"halo\"}],\"stream\":true}"
        }
      }
    },
    {
      "name": "Dashboard",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/api/health/dashboard"
      }
    },
    {
      "name": "Health Report",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/api/health/report/1"
      }
    },
    {
      "name": "Trigger Analysis (Single)",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/api/health/analyze",
        "header": [
          { "key": "Authorization", "value": "Bearer {{api_key}}" },
          { "key": "Content-Type", "value": "application/json" }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\"computer_id\":1}"
        }
      }
    },
    {
      "name": "Trigger Analysis (All)",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/api/health/analyze",
        "header": [
          { "key": "Authorization", "value": "Bearer {{api_key}}" },
          { "key": "Content-Type", "value": "application/json" }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\"analyze_all\":true}"
        }
      }
    },
    {
      "name": "Job Status",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/api/health/status/{{job_id}}"
      }
    },
    {
      "name": "Trigger Correlation",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/api/health/correlate",
        "header": [
          { "key": "Authorization", "value": "Bearer {{api_key}}" }
        ]
      }
    }
  ]
}
```
