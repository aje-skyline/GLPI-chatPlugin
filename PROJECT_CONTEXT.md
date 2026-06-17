# GLPI AI Gateway - Konteks Proyek & Ringkasan Perbaikan

Proyek ini adalah **GLPI AI Gateway**, sebuah antarmuka chatbot berbasis FastAPI yang bertindak sebagai jembatan antara klien chat dan instansi GLPI IT Asset Management. Gateway ini menggunakan CrewAI dan model LLM (melalui LiteLLM) untuk memahami instruksi natural bahasa manusia dan mengambil data aset dari GLPI melalui REST API resmi.

---

## 1. Ringkasan Masalah & Perbaikan Terbaru

### Masalah Konektivitas GLPI
Sistem sebelumnya mengalami error `ERROR_WRONG_APP_TOKEN_PARAMETER` (HTTP 400) yang mengakibatkan chatbot tidak dapat menemukan data apa pun (termasuk data supplier, komputer, dll.).

### Solusi Perbaikan
Kami telah melakukan perbaikan konfigurasi pada berkas [.env](file:///home/ariel/projects/chatbot-fastapi/.env):
* **Koreksi URL API**: Mengubah `GLPI_API_URL` dari `https://172.16.14.103/apirest.php` menjadi `https://172.16.14.103/asset/apirest.php`. (Instance GLPI yang aktif berada di subpath `/asset`).
* **Pembersihan App Token**: Mengosongkan nilai `GLPI_APP_TOKEN` karena token sebelumnya (`X0zWW46YsKf...`) tidak valid untuk instance `/asset`. Karena GLPI pada subpath ini tidak mewajibkan penggunaan App-Token, pengosongan parameter ini berhasil meloloskan inisialisasi sesi.

---

## 2. Struktur Proyek

Berikut adalah tata letak berkas utama di dalam proyek ini:
* [app/main.py](file:///home/ariel/projects/chatbot-fastapi/app/main.py) — Titik masuk utama FastAPI, registrasi middleware, dan endpoint `/v1/chat/completions`.
* [app/config.py](file:///home/ariel/projects/chatbot-fastapi/app/config.py) — Pengelola pengaturan terpusat berbasis Pydantic Settings yang memuat konfigurasi dari [.env](file:///home/ariel/projects/chatbot-fastapi/.env).
* [app/repository/](file:///home/ariel/projects/chatbot-fastapi/app/repository/) — Lapisan akses data murni ke API GLPI (Computer, Supplier, Contract, Ticket, dll.).
* [app/tools/](file:///home/ariel/projects/chatbot-fastapi/app/tools/) — Implementasi CrewAI Tools yang membungkus fungsi repositori untuk digunakan oleh agen AI.
* [app/agents/](file:///home/ariel/projects/chatbot-fastapi/app/agents/) — Konfigurasi agen CrewAI (IT Support Specialist) beserta instruksi anti-halusinasi dan aturan khusus.
* [app/services/](file:///home/ariel/projects/chatbot-fastapi/app/services/) — Alur percakapan (`GLPIChatFlow`) dan orkestrasi eksekusi Crew.
* [app/infrastructure/](file:///home/ariel/projects/chatbot-fastapi/app/infrastructure/) — Pengelola koneksi HTTP client (`httpx`), penanganan token session GLPI, dan penanganan kegagalan.

---

## 3. Pemetaan Field ID GLPI 10.x untuk Supplier

Berdasarkan hasil pembacaan langsung dari endpoint `/listSearchOptions/Supplier`, berikut adalah pemetaan field ID resmi yang digunakan pada query `forcedisplay` di [app/repository/supplier_repository.py](file:///home/ariel/projects/chatbot-fastapi/app/repository/supplier_repository.py):

| Nama Field Python | Nama Field GLPI | ID Field GLPI | Deskripsi |
| :--- | :--- | :--- | :--- |
| `id` | `id` | `2` | ID Unik Supplier |
| `name` | `name` | `1` | Nama Perusahaan |
| `address` | `address` | `3` | Alamat Jalan Utama |
| `phone` | `phonenumber` | `5` | Nomor Telepon |
| `fax` | `fax` | `10` | Nomor Fax |
| `email` | `email` | `6` | Alamat Email |
| `town` | `town` | `11` | Kota |
| `state` | `state` | `12` | Provinsi / Negara Bagian |
| `country` | `country` | `13` | Negara |
| `postcode` | `postcode` | `14` | Kode Pos |
| `entity` | `completename` (glpi_entities) | `80` | Organisasi / Entity Terkait |

---

## 4. Cara Menjalankan & Menguji Aplikasi

### Menjalankan Server
Gunakan perintah berikut di terminal proyek:
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Menguji Melalui cURL
Untuk menguji pengambilan data supplier secara manual:
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer internal-glpi-secret-123" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Tampilkan data supplier"}], "glpi_user_id": 0}'
```
