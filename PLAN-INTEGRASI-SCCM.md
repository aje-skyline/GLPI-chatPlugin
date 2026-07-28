---
> **⛔ DOKUMEN INI SUDAH DIGANTIKAN**
>
> Dokumen ini berisi **pendekatan lama** (PHP-based, langsung dari GLPI Plugin)
> yang sudah digantikan oleh pendekatan **Python/FastAPI** melalui AI Gateway.
>
> **Ganti dengan:**
> - `context.md` — Konteks & ADR integrasi SCCM
> - `spec.md` — Spesifikasi teknis SCCM connector
> - `plan.md` — Rencana implementasi
>
> Dokumen ini dipertahankan sebagai referensi historis saja.
---

# Plan Integrasi: SCCM Data Read ke GLPI Chatbot Plugin

> Dokumen ini berisi rencana pengembangan plugin AI Chatbot GLPI untuk membaca data dari
> server Microsoft SCCM (System Center Configuration Manager) 2012.

---

## 1. Arsitektur

### Lingkungan Saat Ini

```
┌─────────────────────────────────────┐
│  Server GLPI (Linux)                │
│  ├─ GLPI 11.x / 12.x                │
│  ├─ Chatbot Plugin                  │
│  └─ PHP + pdo_sqlsrv (perlu)        │
└──────────────┬──────────────────────┘
               │
               │ (jaringan berbeda — via SQL Server TCP/IP)
               │
┌──────────────▼──────────────────────┐
│  Server SCCM (Windows)              │
│  ├─ SCCM 2012                       │
│  ├─ SQL Server (SCCM Database)      │
│  └─ Port 1433 (perlu di-firewall)   │
└─────────────────────────────────────┘
```

### Opsi Arsitektur

| Opsi | Arsitektur | Pro | Kontra |
|------|-----------|-----|--------|
| **A** | GLPI → SQL Server langsung via `pdo_sqlsrv` | 1 hop saja, sederhana | Perlu firewall + SQL config |
| **B** | GLPI → Middleware (Windows) → SCCM SQL/PowerShell | Lebih aman, pakai cmdlet | Perlu deploy server tambahan |

**Rekomendasi:** Mulai dengan **Opsi A**. Jika client tidak mengizinkan SQL langsung, migrasi ke Opsi B.

---

## 2. Fase Implementasi

### Fase 1 — Foundation & Hardware Inventory (Prioritas)

Tujuan: Setup koneksi SCCM + baca data hardware inventory.

#### 1.1 — Konfigurasi SCCM (`inc/config.php`)

Tambah konstanta:

```php
// SCCM Database Connection
define('PLUGIN_CHATBOT_SCCM_ENABLED', false);
define('PLUGIN_CHATBOT_SCCM_HOST', '');
define('PLUGIN_CHATBOT_SCCM_PORT', '1433');
define('PLUGIN_CHATBOT_SCCM_DB', 'CM_S01');
define('PLUGIN_CHATBOT_SCCM_USER', '');
define('PLUGIN_CHATBOT_SCCM_PASS', '');
define('PLUGIN_CHATBOT_SCCM_CACHE_TTL', 300); // 5 menit
```

#### 1.2 — SCCM Connector Class (`inc/sccm.class.php`) — BARU

Class `PluginChatbotSccm` dengan method:

| Method | Deskripsi |
|--------|-----------|
| `isEnabled()` | Cek apakah SCCM dikonfigurasi |
| `connect()` | Buat koneksi PDO ke SQL Server SCCM |
| `testConnection()` | Test koneksi + return status |
| `getComputerInventory($filters, $limit)` | Query hardware: OS, CPU, RAM, Disk, Serial |
| `getComputerByUser($username)` | Cari device berdasarkan user SCCM |
| `getSoftwareInventory($computerName)` | Software terinstall per device |
| `getCollections()` | Daftar device collections |
| `getCollectionMembers($collectionId)` | Device dalam collection |
| `getPatchCompliance($computerName)` | Status patch update |

Design:
- Return `null` jika gagal (agar AI bisa handle gracefully)
- Query yang complex di-cache ke tabel `glpi_plugin_chatbot_sccm_cache`
- Logging error ke `Toolbox::logDebug()` / `Session::addMessageAfterRedirect()`

#### 1.3 — Cache Table (`hook.php`)

Tambah tabel saat install:

```sql
CREATE TABLE IF NOT EXISTS `glpi_plugin_chatbot_sccm_cache` (
    `id` INT(11) NOT NULL AUTO_INCREMENT,
    `query_hash` VARCHAR(64) NOT NULL,
    `data` LONGTEXT NOT NULL,
    `expires_at` DATETIME NOT NULL,
    `created_at` DATETIME NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `query_hash` (`query_hash`),
    KEY `expires_at` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 1.4 — SCCM AJAX Endpoint (`ajax/sccm.php`) — BARU

Endpoint REST untuk frontend:

| Method | Action | Deskripsi |
|--------|--------|-----------|
| `GET` | `check_connection` | Test koneksi SCCM |
| `GET` | `hardware` | Query hardware inventory |
| `GET` | `software` | Query software inventory (Fase 2) |
| `GET` | `collections` | Collections list (Fase 3) |
| `GET` | `compliance` | Patch compliance (Fase 4) |

#### 1.5 — Tool Calling untuk AI (`ajax/chat.php`)

Tambahkan ke API payload AI Gateway:

```php
// Tool definitions (OpenAI function calling format)
$tools = [
    [
        'type' => 'function',
        'function' => [
            'name' => 'sccm_hardware_inventory',
            'description' => 'Mencari data hardware inventory komputer dari SCCM.',
            'parameters' => [
                'type' => 'object',
                'properties' => [
                    'filter' => [
                        'type' => 'string',
                        'description' => 'Nama komputer atau keyword untuk filter',
                    ],
                ],
            ],
        ],
    ],
    // ... tools lain
];
```

Alur tool calling:
1. User bertanya: _"Siapa yang pakai komputer ABC?"_ atau _"Apa spek komputer saya?"_
2. AI merespons dengan `tool_calls` → `sccm_hardware_inventory({filter: "ABC"})`
3. Backend PHP:
   - Ekstrak `tool_call` dari response AI
   - Panggil `PluginChatbotSccm::getComputerInventory(...)`
   - Kirim hasil sebagai `tool_result` ke AI
   - AI generate jawaban final untuk user
4. Tampilkan hasil streaming ke frontend

#### 1.6 — Frontend Update (`js/chat.js` + `front/chat.php`)

- Handle event SSE baru: `tool_call` → tampilkan indikator _"Mengambil data SCCM..."_
- Handle event `tool_result` → sambung stream jawaban AI
- Tampilkan SCCM status indicator di header (connected/disconnected)

#### 1.7 — Prasyarat Teknis

- Install PHP extension `pdo_sqlsrv` di server GLPI
- Konfigurasi firewall: buka port 1433 antara GLPI dan SCCM
- SQL Server: enable TCP/IP, mixed auth, buat user read-only
- AI Gateway harus support function/tool calling format

---

### Fase 2 — Software Inventory

| Item | Detail |
|------|--------|
| Method baru | `getSoftwareInventory($computerName)`, `getSoftwareCount($softwareName)` |
| Tool baru | `sccm_software_inventory` |
| Endpoint baru | `ajax/sccm.php?action=software` |

---

### Fase 3 — Device Collections

| Item | Detail |
|------|--------|
| Method baru | `getCollections()`, `getCollectionMembers($collectionId)` |
| Tool baru | `sccm_collections`, `sccm_collection_members` |
| Endpoint baru | `ajax/sccm.php?action=collections` |

---

### Fase 4 — Patch / Update Compliance

| Item | Detail |
|------|--------|
| Method baru | `getPatchCompliance($computerName)`, `getUpdateDeployments()` |
| Tool baru | `sccm_patch_compliance` |
| Endpoint baru | `ajax/sccm.php?action=compliance` |

---

### Fase 5 (Opsional) — Middleware Alternatif

Jika client tidak mengizinkan akses SQL langsung ke SCCM:

```
GLPI ──HTTP──> Middleware (Windows) ──PowerShell──> SCCM Server
```

- Deploy **Flask/FastAPI** di Windows server dalam jaringan SCCM
- Middleware jalankan PowerShell SCCM cmdlet via `subprocess`
- Expose REST API: `/api/v1/hardware`, `/api/v1/software`, dll
- GLPI chatbot panggil middleware via HTTP (sama seperti pattern AI Gateway)

---

## 3. File yang Perlu Diubah/Dibuat

| File | Status | Fase | Keterangan |
|------|--------|------|------------|
| `inc/config.php` | **Edit** | 1 | Tambah konstanta SCCM |
| `inc/sccm.class.php` | **BARU** | 1 | Core SCCM connector |
| `inc/sccm_sql_queries.php` | **BARU** (opsional) | 1 | SQL queries dipisah |
| `hook.php` | **Edit** | 1 | Tambah cache table |
| `ajax/sccm.php` | **BARU** | 1 | REST endpoint SCCM |
| `ajax/chat.php` | **Edit** | 1 | Tool calling handler |
| `front/chat.php` | **Edit** | 1 | SCCM status badge |
| `js/chat.js` | **Edit** | 1 | Tool call events |
| `setup.php` | **Edit** | 1 | Cek extension PHP |
| `.env` | **Edit** | 1 | SCCM credentials |

---

## 4. Query SQL Referensi (SCCM 2012)

### Hardware Inventory

```sql
-- Data komputer + OS
SELECT
    CS.Name0 AS ComputerName,
    CS.Manufacturer0 AS Manufacturer,
    CS.Model0 AS Model,
    CS.SystemType0 AS SystemType,
    OS.Caption0 AS OSName,
    OS.Version0 AS OSVersion,
    OS.LastBootUpTime0 AS LastBoot,
    (SELECT SUM(Size0) FROM v_GS_LOGICAL_DISK WHERE MachineID = CS.MachineID AND DriveType0 = 3) / 1048576.0 AS TotalDiskGB,
    (SELECT COUNT(*) FROM v_GS_PC_BIOS WHERE MachineID = CS.MachineID) AS BiosCount
FROM v_GS_COMPUTER_SYSTEM CS
JOIN v_GS_OPERATING_SYSTEM OS ON CS.MachineID = OS.MachineID
WHERE CS.Name0 LIKE '%' + ? + '%'
```

### Software Inventory

```sql
SELECT
    CS.Name0 AS ComputerName,
    ARP.DisplayName0 AS SoftwareName,
    ARP.Publisher0 AS Publisher,
    ARP.Version0 AS Version,
    ARP.InstallDate0 AS InstallDate
FROM v_GS_ADD_REMOVE_PROGRAMS ARP
JOIN v_R_System CS ON ARP.MachineID = CS.ItemKey
WHERE CS.Name0 = ?
ORDER BY ARP.DisplayName0
```

### Device / User Relation

```sql
SELECT
    CS.Name0,
    CS.UserName0 AS LastLoggedOnUser,
    U.UniqueUserName AS UserName,
    U.FullUserName AS FullName
FROM v_GS_COMPUTER_SYSTEM CS
JOIN v_R_System SYS ON CS.MachineID = SYS.ItemKey
LEFT JOIN v_Users U ON SYS.UserName0 = U.UniqueUserName
WHERE CS.Name0 LIKE '%' + ? + '%'
```

### Collections

```sql
SELECT CollectionID, Name, Comment, MemberCount, LastMemberChangeTime
FROM v_Collection
WHERE IsHidden = 0
ORDER BY Name
```

---

## 5. Daftar Tool Functions untuk AI

| Tool Name | Deskripsi | Fase |
|-----------|-----------|------|
| `sccm_hardware_inventory` | Mencari data hardware komputer (OS, CPU, RAM, disk) | 1 |
| `sccm_software_inventory` | Mencari software terinstall di komputer | 2 |
| `sccm_collections` | Mendapatkan daftar device collections SCCM | 3 |
| `sccm_collection_members` | Mendapatkan daftar komputer dalam suatu collection | 3 |
| `sccm_patch_compliance` | Mengecek status patch compliance suatu komputer | 4 |

---

## 6. Alur Lengkap Tool Calling (di `ajax/chat.php`)

```
User: "Apa spesifikasi komputer saya?"
         │
         ▼
  1. Kirim prompt + tools[] ke AI Gateway
         │
         ▼
  2. AI response: tool_calls → sccm_hardware_inventory
         │
         ▼
  3. PHP panggil PluginChatbotSccm::getComputerInventory()
     └─ Cek cache dulu → jika expired, query SQL Server
         │
         ▼
  4. Kirim tool_result ke AI Gateway (lanjut stream)
         │
         ▼
  5. AI generate jawaban final + stream ke frontend
         │
         ▼
  6. User lihat: "Komputer ABC memiliki spesifikasi: ..."
```

---
