# Software Requirements Specification (SRS)
**Sistem:** GLPI AI Chatbot Ecosystem (Plugin & FastAPI Engine)  
**Versi:** 3.0.0

---

## 1. Ruang Lingkup Sistem
**GLPI AI Chatbot** adalah sebuah asisten virtual cerdas yang terintegrasi secara *native* di dalam platform *IT Asset Management* (GLPI). Sistem ini dirancang sebagai ekosistem dual-komponen: 
1. **Komponen Plugin GLPI (Frontend & Storage)**: Modul PHP yang diinstal di dalam GLPI untuk menyediakan antarmuka pengguna (UI) grafis dan menyimpan riwayat percakapan secara permanen di database SQL GLPI.
2. **Komponen FastAPI (AI Engine)**: Layanan terpisah berbasis Python yang mengeksekusi logika kecerdasan buatan, menerjemahkan bahasa alami pengguna menjadi *query* data (melalui 20 *tools* agen), dan berkomunikasi dengan penyedia *Large Language Model* (LLM).

Sistem ini ditujukan untuk mempermudah operasional pengguna GLPI dalam mencari data tiket, aset, dan kontrak menggunakan Bahasa Indonesia tanpa harus bernavigasi ke halaman pencarian yang rumit.

## 2. Perspektif Produk
Sistem ini diposisikan sebagai **Plugin Ekstensi Resmi** di dalam GLPI. Plugin ini akan menambahkan menu khusus di sidebar (di bawah menu "Tools") yang hanya dapat diakses oleh pengguna yang sudah *login* dan memiliki otorisasi (berdasarkan validasi sesesi GLPI). 

Secara arsitektur, Plugin bertindak sebagai *client* yang mengirim teks pengguna (beserta informasi identitas `glpi_user_id`) ke server FastAPI Engine. FastAPI Engine kemudian akan bertindak seolah-olah sebagai "pengguna otomatis" yang melakukan penarikan data ke REST API GLPI secara *read-only* untuk memberikan jawaban komprehensif.

## 3. Fungsi Utama Sistem
Ekosistem memiliki kapabilitas utama sebagai berikut:
*   **Antarmuka Obrolan Integratif**: Plugin menyediakan antarmuka *chat* di dalam dashboard GLPI yang mendukung interaksi bahasa alami, *streaming* jawaban, rendering format teks *markdown*, serta proteksi *Cross-Site Request Forgery* (CSRF).
*   **Persistent Chat History**: Berbeda dengan sesi AI sementara, plugin menyimpan setiap obrolan pengguna di dalam tabel kustom MySQL GLPI (`glpi_plugin_chatbot_sessions` & `glpi_plugin_chatbot_messages`), sehingga pengguna dapat melanjutkan obrolan dari riwayat sebelumnya.
*   **Smart Intent Routing**: FastAPI Engine secara otomatis mengklasifikasikan pertanyaan (apakah sapaan *casual* atau *technical query*) untuk menghemat waktu eksekusi dan biaya token API.
*   **Read-Only Data Retrieval (20 Tools)**: Mesin AI dapat secara otomatis mencari data dari modul Komputer (filter status/OS/user), Kontrak, Supplier, Tiket pengguna ITIL, dan *Knowledge Base*.
*   **Autentikasi Terintegrasi**: Akses UI dijamin sepenuhnya oleh sesi *login* standar GLPI (`Session::getLoginUserID()`). 

## 4. Batasan Sistem (Constraints)
Sistem tunduk pada batasan teknis berikut:
*   **Lingkungan GLPI**: Plugin membutuhkan setidaknya GLPI versi 11.0.0 (hingga maksimum v12.0.0) dan PHP versi minimal 8.1.
*   **Sistem AI**: Arsitektur *backend* wajib menggunakan FastAPI (Python 3.12+), CrewAI untuk *chaining tools*, dan LiteLLM untuk abstraksi komunikasi LLM. 
*   **Keamanan Data**: Eksekusi *tools* bersifat **Strictly Read-Only**. Agen AI tidak diberikan otorisasi, parameter, atau izin untuk melakukan operasi *Create, Update,* atau *Delete* ke database GLPI.
*   **Batasan Waktu Eksekusi**: Permintaan ke AI Engine memiliki batas toleransi *timeout* sebesar 80 detik untuk mencegah antrean (bottleneck) panjang di server.
*   **Batasan Bahasa**: Semua prompt dan output sistem dibatasi secara eksklusif menggunakan Bahasa Indonesia untuk meminimalisasi halusinasi (*Anti-Hallucination Rules*).

## 5. Asumsi dan Ketergantungan
Fungsionalitas dari GLPI AI Chatbot bergantung pada asumsi berikut:
*   **Jaringan dan Ketersediaan API**: Diasumsikan server GLPI memiliki jalur komunikasi jaringan yang terbuka (internal HTTPS/REST) menuju *FastAPI Engine*, dan sebaliknya *Engine* dapat menghubungi *GLPI REST API* serta eksternal *LLM API Gateway*.
*   **Kesesuaian Identitas**: Sistem AI bergantung pada integritas pengiriman `glpi_user_id` dari *Plugin* ke *Engine* untuk memastikan pengguna hanya dapat mengambil data (khususnya tiket ITIL) yang berhak mereka lihat.
*   **Konsistensi Skema**: *Engine* mengasumsikan tidak ada perubahan ekstrem (*breaking changes*) pada struktur REST API bawaan GLPI yang digunakan oleh *tools* agen pencarian.
