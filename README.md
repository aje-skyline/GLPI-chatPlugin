![Logo of the project](https://raw.githubusercontent.com/jehna/readme-best-practices/master/sample-logo.png)

# GLPI AI Gateway
> FastAPI + CrewAI Gateway untuk GLPI IT Asset Management

GLPI AI Gateway adalah backend chatbot berbasis FastAPI yang menyediakan API kompatibel dengan OpenAI (`/v1/chat/completions`) untuk berinteraksi dengan data GLPI (IT Asset Management) menggunakan Agen CrewAI. Dengan mengadopsi prinsip **Clean Architecture**, aplikasi ini bertindak sebagai jembatan cerdas antara antarmuka pengguna percakapan (frontend) dan server GLPI Anda.

---

## Installing / Getting started

Ikuti langkah-langkah minimal berikut untuk memasang dan menjalankan aplikasi di lingkungan lokal:

```shell
# 1. Pasang dependensi menggunakan uv (disarankan)
uv sync

# Atau menggunakan pip konvensional
pip install -e .

# 2. Salin contoh berkas konfigurasi lingkungan
cp .env.example .env

# 3. Jalankan server FastAPI menggunakan uvicorn
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Setelah menjalankan perintah di atas, server akan aktif pada `http://localhost:8000`. Anda dapat memverifikasi status layanan dengan mengakses endpoint health check:
```shell
curl http://127.0.0.1:8000/health
```

### Initial Configuration

Sebelum menjalankan aplikasi, Anda harus mengonfigurasi beberapa variabel lingkungan di dalam file `.env`. Kredensial penting yang diperlukan meliputi:

- **AI_GATEWAY_API_KEY**: Kunci akses untuk API LLM/AI Gateway.
- **GATEWAY_API_KEY**: Kunci bearer token untuk mengamankan API FastAPI ini sendiri.
- **GLPI_APP_TOKEN** & **GLPI_USER_TOKEN**: Token otentikasi API yang digenerasikan oleh sistem GLPI Anda.

---

## Developing

Berikut langkah-langkah awal bagi pengembang untuk berkontribusi dan mengembangkan proyek ini lebih lanjut:

```shell
# Kloning repositori
git clone https://github.com/aje-skyline/GLPI-chatPlugin.git
cd chatbot-fastapi/

# Instalasi dependensi untuk mode pengembangan
uv sync
```

### Struktur Proyek (Clean Architecture)

Aplikasi ini dibagi menjadi beberapa lapisan demi pemisahan tanggung jawab (*separation of concerns*) yang jelas:

* [app/agents/](file:///home/ariel/projects/chatbot-fastapi/app/agents) — Definisi kepribadian agen, aturan pemikiran (backstory & goal), serta factory untuk memicu agen.
* [app/infrastructure/](file:///home/ariel/projects/chatbot-fastapi/app/infrastructure) — Pengelolaan koneksi tingkat rendah, termasuk HTTP Client (httpx pool), manajemen sesi GLPI, serta background async loop runner.
* [app/repository/](file:///home/ariel/projects/chatbot-fastapi/app/repository) — Penanganan logika kueri data GLPI (komputer, tiket, supplier, kontrak, dll.) dan pagination.
* [app/services/](file:///home/ariel/projects/chatbot-fastapi/app/services) — Crew Orchestrator untuk mengoordinasikan eksekusi tugas CrewAI secara asinkron.
* [app/tools/](file:///home/ariel/projects/chatbot-fastapi/app/tools) — Kumpulan alat bantu (CrewAI Tools) yang dapat dipanggil oleh agen untuk berinteraksi dengan repositori GLPI.

### Building

Proyek ini menggunakan Hatchling sebagai build backend yang dikonfigurasi pada [pyproject.toml](file:///home/ariel/projects/chatbot-fastapi/pyproject.toml). Untuk membuild paket wheel atau tarball distribusi:

```shell
uv build
```

Hasil build akan disimpan di folder `dist/` dan siap didistribusikan atau diinstal.

### Deploying / Publishing

Untuk menyebarkan proyek ini ke server produksi, jalankan server Uvicorn tanpa reload otomatis dan tentukan worker thread yang memadai:

```shell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Anda juga dapat membungkus aplikasi ini menggunakan container Docker atau mendaftarkannya sebagai systemd service pada server Linux.

---

## Features

Beberapa fitur utama yang ditawarkan oleh GLPI AI Gateway:

* **Clean Architecture**: Pemisahan modul yang jelas antara agen, alat, repositori, dan infrastruktur untuk mempermudah pemeliharaan jangka panjang.
* **REST API Kompatibel OpenAI**: Mendukung endpoint `/v1/chat/completions` dengan dukungan streaming berbasis SSE (*Server-Sent Events*).
* **CrewAI Native Integration**: Agen IT Support cerdas dengan akses ke 20 tools khusus untuk kueri data GLPI yang aman.
* **Smart Pagination**: Sistem paginasi cerdas otomatis untuk kueri inventaris besar untuk menghindari kelebihan memori pada agen dan menghindari *token explosion*.
* **CrewAI Flows Integrasi**: Menangani *multi-turn chat sessions* secara cerdas. Dilengkapi sistem *router* untuk memisahkan pertanyaan teknis dan sapaan biasa (casual) secara instan.
* **Manajemen Sesi In-Memory & Persisten**: Sistem state menggunakan Pydantic (`GLPIChatState`) serta dekorator `@persist()` dari CrewAI, digabung dengan *auto-fingerprinting* percakapan.
* **Persistent Background Async Loop**: Menjalankan call asinkron GLPI di dalam daemon thread terpisah sehingga tidak memblokir event loop FastAPI.

---

## Conversational Flow & Multi-turn Chat

Aplikasi ini menggunakan teknologi **CrewAI Flows** yang didekorasi dengan `@persist()` untuk mengatur laju dan state percakapan (`GLPIChatState`). Ketika endpoint menerima sebuah pesan, aliran pemrosesan (Flow) secara cerdas mem-parsing apakah pesan itu pertanyaan teknis atau sapaan biasa, dan meresponsnya tanpa kehilangan konteks riwayat obrolan sebelumnya.

### Cara Penggunaan (Input Payload)
Anda cukup mengirimkan parameter opsional `session_id` di dalam payload JSON untuk mempertahankan riwayat sesi:

```json
{
  "messages": [{"role": "user", "content": "Berapa banyak komputer yang kita miliki?"}],
  "glpi_user_id": 0,
  "session_id": "sesi-unik-anda-123"
}
```

### JSON Response
Gateway akan mengembalikan teks jawaban lengkap dengan `session_id` yang sedang aktif (yang mana bisa Anda gunakan lagi untuk request selanjutnya):

```json
{
  "id": "glpi-crew-xxx",
  "object": "chat.completion",
  "model": "qwen/qwen3-next-80b-a3b-instruct",
  "session_id": "body:sesi-unik-anda-123",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Kita memiliki 124 komputer yang tercatat di GLPI."},
    "finish_reason": "stop"
  }]
}
```

---

## Configuration

Aplikasi ini menggunakan konfigurasi berbasis environment variables yang dimuat via Pydantic Settings. Berikut adalah parameter yang dapat dikonfigurasi:

#### AI_GATEWAY_URL
Type: `String`  
Default: `None` (Wajib diisi)  
URL lengkap endpoint chat completions AI Gateway (misal: `https://ai-gw.example.com/v1/chat/completions`).

#### AI_GATEWAY_BASE_URL
Type: `String`  
Default: `""`  
Base URL opsional tanpa suffix endpoint. Jika tidak diisi, akan otomatis diekstrak dari `AI_GATEWAY_URL`.

#### AI_GATEWAY_API_KEY
Type: `String`  
Default: `None` (Wajib diisi)  
API key/token otentikasi untuk mengakses layanan AI Gateway.

#### AI_MODEL
Type: `String`  
Default: `"qwen/qwen3-next-80b-a3b-instruct"`  
Nama model AI yang akan digunakan oleh Agen CrewAI (misal: `qwen/qwen3-next-80b-a3b-instruct`).

#### GATEWAY_API_KEY
Type: `String`  
Default: `None` (Wajib diisi)  
Token keamanan (Bearer token) untuk memproteksi endpoint API `/v1/chat/completions` gateway ini.

#### ALLOWED_ORIGINS
Type: `String`  
Default: `"http://172.16.14.141"`  
Daftar asal (origins) yang diizinkan untuk CORS (dipisahkan oleh koma).

#### GLPI_URL
Type: `String`  
Default: `"https://172.16.14.141"`  
URL utama dari instansi GLPI.

#### GLPI_APP_TOKEN
Type: `String`  
Default: `""`  
Application token GLPI untuk otentikasi API.

#### GLPI_USER_TOKEN
Type: `String`  
Default: `""`  
User token GLPI untuk membuat session token dinamis.

#### GLPI_API_URL
Type: `String`  
Default: `"https://172.16.14.141/asset/apirest.php"`  
Endpoint URL REST API lengkap dari server GLPI.

#### GLPI_verify_ssl
Type: `Boolean`  
Default: `False`  
Jika bernilai `True`, verifikasi sertifikat SSL server GLPI diaktifkan. Set ke `False` untuk sertifikat self-signed.

#### MOCK_MODE
Type: `Boolean`  
Default: `False`  
Jika bernilai `True`, aplikasi berjalan dalam mode simulasi tanpa melakukan panggilan nyata ke GLPI atau LLM.

---

## Contributing

Kami sangat menyambut kontribusi dari pengembang lainnya. Jika Anda ingin berkontribusi:

"Silakan fork repositori ini, buat branch fitur baru Anda, dan buat pull request (PR). Untuk panduan gaya pengkodean, jalankan linter lokal sebelum mengajukan PR."

Silakan merujuk ke berkas [CLAUDE.md](file:///home/ariel/projects/chatbot-fastapi/CLAUDE.md) untuk detail panduan pengembangan, perintah testing, dan tips debugging yang lebih mendalam.

---

## Links

Berikut adalah ringkasan tautan penting terkait proyek ini:

* **Repository**: [GLPI Chat Plugin Repository](https://github.com/aje-skyline/GLPI-chatPlugin)
* **Related Project**: [GLPI Project Homepage](https://glpi-project.org/)

---

## Licensing

Kode sumber dan aset di dalam proyek ini dilisensikan di bawah aturan:

"Internal use only."

---

## 📚 Dokumentasi Fase

Dokumentasi proyek dibagi berdasarkan fase:

| Fase | Lokasi | Keterangan |
|------|--------|------------|
| **Saat Ini (v3.0.0)** | Root (`README.md`, `CLAUDE.md`, `PROJECT_CONTEXT.md`) | Dokumentasi kode yang sudah berjalan |
| **Phase 2 (Direncanakan)** | `docs/planned/` | Blueprint, PRD, spesifikasi SCCM/Health/Docker/Celery yang akan datang |
| **API Contract** | `docs/API-CONTRACT.md` | Kontrak API — endpoint yang sudah ada (v3.0.0) dan yang direncanakan (Phase 2) |

> Dokumen Phase 2 dipisahkan ke subdirektori `docs/planned/` untuk menghindari kebingungan dengan kode yang sudah berjalan saat ini.
