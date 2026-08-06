**SOFTWARE REQUIREMENTS SPECIFICATION**

**(SRS)**

**GLPI AI CHATBOT ECOSYSTEM**

*IT Operational AI Assistant*

PT Astra Honda Motor

Klien

**PT Astra Honda Motor (AHM)**

Pengembang

**PT Semesta Teknologi Informatika (STI)**

Versi Dokumen 3.0.0 | 03 Agustus 2026

Status: Revised Final Draft Untuk Review & Persetujuan

**RAHASIA**

# Informasi Dokumen
<table>
<colgroup>
<col style="width: 32%" />
<col style="width: 67%" />
</colgroup>
<thead>
<tr class="header">
<th><strong>Informasi Dokumen</strong></th>
<th><strong>Keterangan</strong></th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>Nama Proyek</td>
<td>GLPI AI Chatbot Ecosystem</td>
</tr>
<tr class="even">
<td>Klien</td>
<td>PT Astra Honda Motor (AHM)</td>
</tr>
<tr class="odd">
<td>Pengembang</td>
<td>PT Semesta Teknologi Informatika (STI)</td>
</tr>
<tr class="even">
<td>Versi Dokumen</td>
<td>3.0.0</td>
</tr>
<tr class="odd">
<td>Tanggal Pembuatan</td>
<td>03 Agustus 2026</td>
</tr>
<tr class="even">
<td>Status Dokumen</td>
<td><p>Revised Final Draft Untuk Review &amp; Persetujuan</p>
<p><strong>Ringkasan Revisi:</strong> Penegasan sistem sebagai ekosistem dual-komponen yang terdiri dari Plugin GLPI (Frontend PHP) dan Engine FastAPI (Python Backend) berdasarkan implementasi saat ini. Penyimpanan histori persisten pada DB MySQL GLPI, serta implementasi 20 Tools Read-Only untuk kueri Data Center dan tiket GLPI.</p></td>
</tr>
<tr class="odd">
<td>Bahasa Antarmuka Sistem</td>
<td>Bahasa Indonesia (satu bahasa konsisten)</td>
</tr>
<tr class="even">
<td>Standar Referensi</td>
<td>IEEE Std 830-1998 (SRS Guidelines)</td>
</tr>
</tbody>
</table>

> **Dokumen ini bersifat RAHASIA dan hanya untuk keperluan internal PT Astra Honda Motor dan PT Semesta Teknologi Informatika.**

# BAB 1 PENDAHULUAN
## 1.1 Tujuan Dokumen
Dokumen ini mendefinisikan spesifikasi kebutuhan perangkat lunak untuk GLPI AI Chatbot Ecosystem. Dokumen ini ditujukan bagi tim pengembang, arsitek sistem, dan pemangku kepentingan (*stakeholders*) sebagai acuan utama dalam siklus pengembangan, pemeliharaan, serta batasan fungsional operasional.

## 1.2 Ruang Lingkup Sistem
GLPI AI Chatbot dikembangkan sebagai sebuah asisten virtual cerdas yang terintegrasi secara *native* di dalam platform *IT Asset Management* (GLPI) milik korporasi. Sistem ini tidak dirancang untuk memodifikasi modul-modul utama GLPI, melainkan bertindak sebagai jembatan interaksi natural.

Ruang lingkup sistem difokuskan pada ekosistem dual-komponen:
1. **Komponen Plugin GLPI (Frontend & Storage):** Modul PHP yang diinstal secara lokal pada `/var/www/glpi/plugins/chatbot` untuk menyediakan antarmuka pengguna grafis, serta menangani penyimpanan riwayat percakapan secara permanen di database SQL GLPI.
2. **Komponen FastAPI (AI Engine):** Layanan backend microservice (Python) yang memproses permintaan chat, melakukan *Intent Routing*, menghubungi agen *CrewAI* untuk menarik data secara *read-only* dari GLPI, dan merangkum jawaban melalui LLM eksternal.

> **Catatan Scope: Eksekusi tools oleh Agen AI secara tegas bersifat *Read-Only*. Fitur pembuatan atau pembaruan tiket oleh AI TIDAK termasuk dalam scope pengembangan ini.**

## 1.3 Definisi, Akronim, dan Singkatan
| **Istilah / Akronim** | **Definisi**                                                                                                                     |
|-----------------------|----------------------------------------------------------------------------------------------------------------------------------|
| GLPI                  | *Gestionnaire Libre de Parc Informatique*, sistem IT Asset Management dan Helpdesk open-source.                                  |
| FastAPI               | Web framework Python yang digunakan untuk membangun engine backend AI dengan kinerja tinggi.                                     |
| LLM                   | *Large Language Model* (contoh: Nemotron, Qwen) yang digunakan untuk melakukan penalaran kalimat natural.                        |
| Intent Routing        | Mekanisme pemilahan awal oleh LLM untuk membedakan percakapan santai (*casual*) dan kueri teknis (*technical*).                  |
| Plugin                | Modul PHP terpisah yang ditambahkan ke arsitektur GLPI untuk memperluas kapabilitas sistem (Frontend Chatbot).                   |
| CSRF                  | *Cross-Site Request Forgery*, pengamanan validasi sesi web yang diterapkan oleh GLPI Plugin untuk melindungi akses API.          |
| SSE                   | *Server-Sent Events*, teknologi untuk mengirim *stream* data secara *real-time* ke antarmuka web (seperti efek *typing*).        |
| CrewAI                | Framework agen kecerdasan buatan multi-langkah yang digunakan di Engine FastAPI untuk mengeksekusi *tools* pencarian data.       |

## 1.4 Referensi Dokumen
| **No.** | **Judul Dokumen**                                                | **Penyusun**                     | **Tanggal**    |
|---------|------------------------------------------------------------------|----------------------------------|----------------|
| 1       | Arsitektur dan Codebase FastAPI GLPI Gateway                     | STI                              | Agustus 2026   |
| 2       | Arsitektur Plugin PHP `glpi/plugins/chatbot`                     | STI                              | Agustus 2026   |

## 1.5 Gambaran Umum Dokumen
Dokumen SRS ini terdiri dari 6 bab utama: Bab 1 berisi pendahuluan; Bab 2 deskripsi umum sistem dan arsitektur ekosistem; Bab 3 kebutuhan antarmuka pengguna dan teknis; Bab 4 kebutuhan fungsional (FR) berdasarkan modul; Bab 5 spesifikasi REST API; dan Bab 6 struktur database/Entitas (ERD sederhana).

# BAB 2 DESKRIPSI UMUM SISTEM
## 2.1 Perspektif Produk
Sistem diposisikan sebagai **Plugin Ekstensi Resmi** di dalam GLPI yang terhubung dengan **API Engine Eksternal**. Plugin ini akan menambahkan menu khusus di sidebar (di bawah grup menu "Tools") yang hanya dapat diakses oleh pengguna yang telah tervalidasi sesi login-nya di GLPI.

Secara arsitektur, Plugin bertindak sebagai antarmuka depan (*Client*) yang mengirim pesan pengguna, mengelola penyimpanan percakapan, dan mengidentifikasi `glpi_user_id` ke server FastAPI Engine. FastAPI Engine kemudian bertindak sebagai "pengguna otonom" yang melakukan *loopback* kueri ke *REST API GLPI* secara *read-only* dengan token aplikasi untuk merumuskan jawaban yang cerdas, lalu mengirimkannya kembali ke Plugin.

## 2.2 Fungsi Utama Sistem
| **Modul**             | **Fungsi Utama**                                                                                                                                                                            |
|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Chat Box UI (Plugin)  | Antarmuka percakapan natural language di dalam web GLPI yang mendukung format markdown dan SSE (*streaming* huruf).                                                                         |
| Session Management    | Menyimpan histori metadata sesi dan isi pesan pengguna secara persisten di MySQL GLPI, sehingga obrolan tidak hilang setelah *restart* atau penutupan peramban.                             |
| Intent Routing Engine | Klasifikasi awal di FastAPI untuk mem-bypass agen kompleks saat pengguna hanya melontarkan sapaan santai (*casual chat*).                                                                   |
| Read-Only Data Query  | Fasilitas agen (CrewAI) dengan 20 kumpulan *tools* untuk mengeksekusi pencarian data komputer, tiket, aset, dan kontrak GLPI secara aman.                                                   |
| LLM Integration       | Eksekusi pembuatan kalimat yang terstruktur, alami, dan selalu dibatasi dalam Bahasa Indonesia (Anti-Hallucination).                                                                        |

## 2.3 Karakteristik Pengguna
| **Role**             | **Deskripsi**                                                                          | **Akses Utama**                         |
|----------------------|----------------------------------------------------------------------------------------|-----------------------------------------|
| User GLPI (Teknisi/Umum)| Pengguna GLPI standar yang membutuhkan informasi status tiketnya, kontrak, atau *Knowledge Base*. | Akses Modul Chatbot, pencarian terbatas |
| Admin / Super-Admin  | Administrator sistem yang mengelola Plugin GLPI, setup konfigurasi koneksi FastAPI API, dan pemantauan sistem. | Konfigurasi Plugin, semua fitur chat |

## 2.4 Batasan Sistem
Berikut adalah batasan yang berlaku untuk GLPI AI Chatbot Ecosystem:
1.  **Lingkungan Teknis**: Instalasi sisi Frontend Plugin mengharuskan GLPI versi 11.0.0 - 12.0.0 dengan PHP versi 8.1+. Arsitektur Backend mensyaratkan Python 3.12+ (FastAPI).
2.  **Read-Only Strict Access**: Sistem dilarang merubah/melakukan operasi tulis ke database GLPI. Akses *tools agent* dibatasi hanya untuk narik data.
3.  **Kendala Bahasa**: Agen telah diinstruksikan (*system prompt*) untuk memberikan respon eksklusif dalam Bahasa Indonesia.
4.  **Timeout**: Pemrosesan *chaining tools* oleh AI Engine akan dibatalkan (*hard timeout*) jika melampaui batas eksekusi 80 detik.
5.  **Biaya Token API**: Sistem bergantung pada *rate-limit* eksternal dan API LLM pihak ketiga, biaya dan kapasitas sepenuhnya ditangani oleh klien (AHM).

## 2.5 Asumsi dan Ketergantungan
1.  **Jaringan**: Diasumsikan server Plugin GLPI memiliki jalur komunikasi terbuka menuju server FastAPI Engine, dan API Engine dapat berkomunikasi kembali ke GLPI API Server lokal.
2.  **Integritas Identitas**: Keamanan berbasis *Role* (seperti filter melihat tiket milik sendiri) sepenuhnya bertumpu pada suplai parameter `glpi_user_id` dari plugin ke engine AI.
3.  **Struktur Endpoint**: Engine mengasumsikan tidak ada perubahan ekstrem (*breaking changes*) pada respons endpoint bawaan REST API GLPI.

# BAB 3 KEBUTUHAN ANTARMUKA
## 3.1 Antarmuka Pengguna (User Interface)
> **KETENTUAN PENTING: Seluruh antarmuka obrolan dan output sistem dari Engine menggunakan SATU BAHASA yang konsisten, yaitu BAHASA INDONESIA.**

| **Aspek UI**       | **Ketentuan**                                                                                                                                                     |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Navigasi Sidebar   | Menu "AI Chatbot" ditambahkan pada grup menu "Tools" di GLPI, hanya dapat dilihat oleh user yang terautentikasi (menggunakan Hook Plugin `PluginChatbotChat`).    |
| Chat Window        | Antarmuka obrolan (*messenger-style*) yang mendukung *bubbles* teks, dilengkapi input pengetikan pesan, di folder `/front/` dan `/ajax/`.                         |
| Tampilan Respons   | Respons AI dirender dan di-*parse* mendukung *markdown*: teks tebal untuk info penting, *list* penomoran, serta blok kode (jika diperlukan).                      |
| Indikator Pengetikan| Terdapat indikator "Sedang mengetik..." atau efek *streaming* (SSE) huruf demi huruf selama AI Engine memproses *tools* di latar belakang.                        |

### 3.1.1 Deskripsi Fungsional Tampilan Antarmuka (Screenshots)

Berikut adalah penjelasan detail dan komprehensif mengenai antarmuka pengguna grafis (GUI) sistem GLPI AI Chatbot berdasarkan dokumentasi tangkapan layar sistem:

#### Gambar 1: Inisiasi Chatbot & Informasi Kemampuan Sistem (Screenshot 131055)
* **Integrasi Sidebar Menu (Navigasi Kiri):** Menu asisten AI diposisikan secara *native* sebagai sub-menu bertajuk **"Chatbot Assistant"** di bawah menu utama **"Tools"** pada sidebar GLPI. Navigasi ini dirancang menggunakan gaya visual GLPI standar untuk menjaga konsistensi UI/UX.
* **Header Chat & Identitas Bot:** Bagian atas panel chat menampilkan nama asisten (**"Al Chatbot"**) dengan sub-label **"GLPI Plugin"**. Di sebelah kanan terdapat indikator status koneksi (hijau aktif) dan tombol pintas riwayat chat.
* **Pesan Sambutan Dinamis (Welcome Message):** Saat memulai percakapan baru, asisten AI secara otomatis menyapa pengguna dengan memperkenalkan dirinya sebagai **IT Support Specialist GLPI**. Pesan ini menyajikan daftar kemampuan sistem yang terstruktur menggunakan format Markdown, yang terbagi ke dalam 5 domain utama:
  1. *Aset & Inventaris Komputer:* Pencarian komputer, detail hardware, status operasional, filter OS/lokasi, dan kepemilikan aset.
  2. *Tiket & Dukungan:* Monitoring daftar tiket dukungan IT milik pengguna serta informasi kategori ITIL.
  3. *Kontrak & Vendor:* Informasi supplier aktif dan detail kontrak lisensi/perangkat.
  4. *Panduan & Knowledge Base:* Pencarian artikel panduan pemecahan masalah (FAQ) internal GLPI.
  5. *Profil User:* Informasi akun pengguna yang terhubung.
* **Panduan Penggunaan (Cara Pakai):** Bagian bawah pesan pembuka memberikan contoh kueri teks berbasis bahasa alami (Natural Language) untuk memudahkan pengguna berinteraksi (misalnya: *"Berapa total komputer di GLPI?"*, *"Tampilkan komputer di Lantai 3"*).
* **Input Box & Aksi Pintas:** Panel input di bagian bawah halaman menyediakan area pengetikan pesan yang mendukung multiline (Shift+Enter untuk baris baru). Di sebelah kiri input box terdapat tombol ikon sampah (*Clear Chat*) untuk membersihkan sesi percakapan aktif dari layar secara instan, dan di sebelah kanan terdapat tombol kirim (pesawat kertas).

#### Gambar 2: Kueri Detail Aset & Tampilan Data Terstruktur (Screenshot 131630)
* **Visualisasi Output Kueri Kompleks:** Ketika pengguna meminta informasi detail dari aset tertentu (misalnya: *"Tolong berikan detail untuk informasi Asset dengan nama D02028L07"*), AI Engine memanggil fungsi *read-only tools* untuk menarik data terkait dari GLPI Server dan menyajikannya secara terstruktur.
* **Format Markdown Tabel Komprehensif:** Respons asisten disajikan menggunakan format tabel Markdown yang bersih dan terbagi menjadi beberapa kelompok klasifikasi informasi yang intuitif untuk teknisi IT:
  1. *Informasi Dasar:* Menampilkan ID entitas, Nama komputer (`D02028L07`), Entity/Divisi (`PT. Jaya Abadi`), Serial Number, Inventory Number, dan Lokasi fisik.
  2. *Spesifikasi Hardware:* Menampilkan Tipe perangkat (Laptop), Model (`HP EliteBook 840 G8`), dan Pabrikan/Manufacturer (`HP`).
  3. *Sistem Operasi:* Menampilkan OS (`Windows 11 Pro`), Versi (`22H2`), dan Arsitektur (`64-bit`).
  4. *Pengguna & Status:* Menampilkan nama pengguna yang menggunakan aset tersebut (`Budi Santoso`) beserta status operasionalnya (`Digunakan`).
* **Fitur Salin Cepat (Copy to Clipboard):** Pada setiap blok pesan tabel terstruktur, disediakan tombol salin cepat (*copy icon*) di pojok kanan atas kontainer pesan untuk mempermudah teknisi menyalin teks mentah tabel untuk kebutuhan dokumentasi eksternal atau tiket.

#### Gambar 3: Panel Riwayat Sesi & Quick Actions (Screenshot 132034)
* **Layar Awal Dashboard & Model AI:** Menampilkan sapaan personalisasi kepada pengguna (contoh: *"Halo, primary admin!"*). Di pojok kanan atas layar chat utama, sistem menampilkan nama model AI yang sedang melayani sesi aktif (contoh: `nvidia/nemotron-3-super-120b-a12b`).
* **Fitur Quick Actions (Aksi Cepat):** Di bawah pesan sambutan tengah halaman, sistem menyediakan tombol-tombol pilihan cepat (*pill buttons*) berdasarkan pertanyaan atau tindakan yang paling sering dicari oleh pengguna, seperti:
  * *"Apa yang bisa kamu lakukan?"*
  * *"Cara membuat tiket di GLPI"*
  * *"Cara reset password user"*
  * *"Fitur baru GLPI 11"*
* **Sidebar Riwayat Percakapan (Navigasi Kanan):** Di sebelah kanan antarmuka, terdapat panel vertikal **"RIWAYAT CHAT"** yang menyajikan daftar sesi obrolan sebelumnya:
  * Dilengkapi tombol **"+ Chat Baru"** untuk memulai sesi percakapan kosong dengan instan.
  * Sesi-sesi dikelompokkan secara kronologis (misalnya: *Hari Ini*, *Lebih Lama*).
  * Setiap riwayat sesi menampilkan judul ringkasan percakapan secara dinamis bersama waktu pembuatan relatif (contoh: *"5 menit lalu"*, *"2 jam lalu"*, *"17 Jun 2026"*).
  * Menyediakan kotak centang *"All"* untuk manajemen sesi atau penghapusan riwayat secara massal.

## 3.2 Antarmuka Perangkat Lunak
| **Sistem Eksternal**   | **Protokol/Metode Akses**          | **Tipe Akses** | **Keterangan**                                                                                                                                                               |
|------------------------|------------------------------------|----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| LLM Gateway API        | REST API (HTTPS)                   | Read (Query)   | *Language Model* eksternal (Nemotron/Qwen via LiteLLM) untuk orkestrasi pemrosesan *prompt*.                                                                                 |
| GLPI Database (MySQL)  | Native DB Protocol (PHP PDO)       | Read/Write     | Digunakan khusus oleh *Plugin PHP* untuk menyimpan histori teks percakapan dan profil sesi `glpi_plugin_chatbot_sessions`.                                                   |

## 3.3 Antarmuka Komunikasi
| **Komunikasi**                   | **Protokol**            | **Enkripsi**   | **Keterangan**                                          |
|----------------------------------|-------------------------|----------------|---------------------------------------------------------|
| Browser ↔ GLPI Plugin            | HTTPS / Web             | TLS            | Request UI Chat dari browser pengguna (mendukung validasi CSRF). |
| GLPI Plugin ↔ FastAPI Engine     | HTTPS / REST            | TLS            | Modul PHP mengirim JSON ke API Engine secara asinkron.  |
| FastAPI Engine ↔ GLPI Server     | HTTPS / REST            | TLS            | Engine menarik data GLPI (Aset, Kontrak, dll) melalui 20 *Tools*.|

# BAB 4 KEBUTUHAN FUNGSIONAL
## 4.1 Modul GLPI Plugin Chat UI (FR-UI)
Modul ini adalah ekstensi sisi Frontend di dalam GLPI (dikembangkan dengan PHP).

| **ID**  | **Nama Kebutuhan**               | **Deskripsi**                                                                                                                                                                                                                                                      | **Aktor**            | **Prioritas** |
|---------|----------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------|---------------|
| FRUI001 | Injeksi Sidebar Menu             | Sistem mendaftarkan "AI Chatbot" pada *hook* `menu_toadd` GLPI hanya jika status `Session::getLoginUserID()` bernilai benar.                                                                                                                                       | Semua Pengguna       | Tinggi        |
| FRUI002 | Manajemen Obrolan Sinkron        | Sistem menampilkan riwayat obrolan terdahulu pada peramban dengan menarik data dari tabel *messages* di MySQL GLPI.                                                                                                                                                | Semua Pengguna       | Tinggi        |
| FRUI003 | Pengecualian CSRF Streaming      | Sistem memastikan lalu lintas komunikasi ke endpoint `ajax/chat.php` yang digunakan untuk respon *stream* dari AI dikecualikan dari pemblokiran *strict* CSRF GLPI.                                                                                                | Sistem               | Tinggi        |
| FRUI004 | Komunikasi ke FastAPI Engine     | Sistem merangkum obrolan pengguna, melampirkan `glpi_user_id`, lalu meneruskannya via permintaan HTTP ke server FastAPI Engine untuk ditindaklanjuti.                                                                                                              | Sistem               | Tinggi        |

## 4.2 Modul AI Orchestration Engine (FR-AI)
Modul ini berjalan di Engine backend (Python/FastAPI) untuk mengatur pemrosesan bahasa dan memanggil GLPI.

| **ID**  | **Nama Kebutuhan**           | **Deskripsi**                                                                                                                                                  | **Aktor**      | **Prioritas** |
|---------|------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------|---------------|
| FRAI001 | Intent Classification Router | Sistem memisahkan obrolan ber-intent "Casual" (Sapaan santai) agar langsung dibalas cepat, dan meneruskan intent "Technical" ke CrewAI agent.                  | AI Engine      | Tinggi        |
| FRAI002 | Eksekusi Tools Agent         | Sistem menggunakan CrewAI untuk mengevaluasi prompt pengguna, memilih *tools* GLPI API yang sesuai (maksimal 20 *tools*), dan menarik datanya.                 | AI Engine      | Tinggi        |
| FRAI003 | Proteksi Anti-Hallucination  | Sistem memvalidasi kueri untuk mengunci bahasa ke Bahasa Indonesia dan mencegah kode observasional JSON (Thought/Action/Observation) bocor ke pengguna akhir.  | AI Engine      | Tinggi        |
| FRAI004 | Endpoint Compatibilitas      | Sistem menyediakan endpoint `/v1/chat/completions` yang strukturnya (*request/response/SSE*) secara ketat sejalan dengan standar Library OpenAI.               | Sistem         | Tinggi        |

## 4.3 Modul Integrasi Pencarian Data GLPI (FR-GLP)
Modul ini mendefinisikan koleksi *Tools* yang tersedia bagi Agen AI.

| **ID**  | **Nama Kebutuhan**              | **Deskripsi**                                                                                                                                                                                                                                                                                  | **Aktor**      | **Prioritas** |
|---------|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------|---------------|
| FRGLP01 | Domain Pencarian Aset/Komputer  | Tersedia 10 *Tools* untuk mencari daftar komputer, memfilter status aktif, lokasi, sistem operasi (OS), dan mencari detail *hardware* atau aset spesifik yang dimiliki oleh pengguna (*user assets*).                                                                                          | Agen AI        | Tinggi        |
| FRGLP02 | Domain Tiket ITIL               | Tersedia *Tool* untuk melihat riwayat tiket ITIL pengguna berdasarkan `glpi_user_id`, sehingga pengguna tidak dapat membaca tiket rahasia milik pengguna lainnya.                                                                                                                              | Agen AI        | Tinggi        |
| FRGLP03 | Domain Kontrak & Supplier       | Tersedia 5 *Tools* untuk mencari direktori kontak rekanan pemasok (Supplier), daftar kontrak lisensi aktif, serta detail periode kontrak.                                                                                                                                                      | Agen AI        | Sedang        |
| FRGLP04 | Automasi Sesi GLPI API          | *Tools* terhubung ke API GLPI dan berbagi sesi token tunggal yang dikelola menggunakan skema *Lazy Initialization* serta dapat diperbarui otomatis (*refresh*) saat menerima error 401.                                                                                                        | Sistem         | Tinggi        |

# BAB 5 SPESIFIKASI REST API
*Bab ini spesifik pada jembatan komunikasi antara Plugin PHP (Klien) dengan FastAPI Engine (Server)*.

## 5.1 Format API Standar

| **Aspek**          | **Konvensi** |
|--------------------|--------------|
| Base URL           | Di-deploy di server mandiri: `http://<ip-engine>:8000/v1` |
| Autentikasi        | `Authorization: Bearer <GATEWAY_API_KEY>` dari `.env` FastAPI. |
| Format Data        | `Content-Type: application/json` |

## 5.2 API Utama: Chat Completions

**Endpoint:** `POST /v1/chat/completions`

**Payload Request JSON dari Plugin PHP:**
```json
{
  "messages": [
    {"role": "user", "content": "Tampilkan jumlah komputer saya berdasarkan OS"}
  ],
  "glpi_user_id": 45, 
  "session_id": "sesi-kustom-45", 
  "stream": true
}
```

**Payload Response JSON (jika stream = false):**
```json
{
  "id": "glpi-crew-xxx",
  "object": "chat.completion",
  "model": "qwen/qwen3-next-80b-a3b-instruct",
  "session_id": "sesi-kustom-45",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Berdasarkan data sistem, Anda memiliki 3 PC..."
      },
      "finish_reason": "stop"
    }
  ]
}
```
*(Jika `stream = true`, balasan berupa text/event-stream OpenAI chunk)*.

# BAB 6 STRUKTUR DATABASE (PERSISTENCE)
## 6.1 Entity Deskripsi
Komponen Plugin PHP GLPI membuat tabel kustom secara otomatis di dalam database MySQL sistem GLPI (via `hook.php`). Tidak ada koneksi DB eksternal yang diatur oleh FastAPI Engine.

### 1. Tabel: `glpi_plugin_chatbot_sessions`
Menyimpan informasi sesi (topik obrolan) pengguna.
| **Atribut**  | **Tipe Data** | **Keterangan**                                    |
|--------------|---------------|---------------------------------------------------|
| `id`         | INT(11)       | Primary Key (Auto Increment)                      |
| `users_id`   | INT(11)       | Foreign Key: Pemilik sesi (ID pengguna GLPI)      |
| `title`      | VARCHAR(255)  | Judul percakapan (*auto generated* / kosong)      |
| `created_at` | DATETIME      | Waktu inisiasi sesi                               |
| `updated_at` | DATETIME      | Waktu pembaruan terakhir (saat *chat* baru masuk) |

### 2. Tabel: `glpi_plugin_chatbot_messages`
Menyimpan baris percakapan individual agar tidak hilang saat browser ditutup.
| **Atribut**  | **Tipe Data** | **Keterangan**                                    |
|--------------|---------------|---------------------------------------------------|
| `id`         | INT(11)       | Primary Key (Auto Increment)                      |
| `sessions_id`| INT(11)       | Foreign Key merujuk ke tabel Sessions             |
| `role`       | VARCHAR(20)   | `'user'` (pertanyaan) atau `'assistant'` (jawaban)|
| `content`    | TEXT          | Isi percakapan (*payload* atau teks AI)           |
| `created_at` | DATETIME      | Waktu pesan dicatat                               |

*(Catatan: Saat Plugin GLPI dilakukan proses Uninstall/Copot dari dasbor Administrator, kedua tabel ini akan secara otomatis di-Drop (hapus permanen).)*
