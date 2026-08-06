# Plan: Penyusunan Artefak SRS GLPI AI Chatbot Ecosystem (Plugin & API)

## Tujuan
Memperbarui dokumen *Software Requirements Specification* (SRS) agar mencakup seluruh ruang lingkup ekosistem GLPI AI Chatbot, yang kini divalidasi tidak hanya sebagai API *headless*, melainkan sebuah Plugin GLPI utuh (PHP/MySQL) yang berkolaborasi dengan FastAPI Middleware.

## Langkah-langkah
1. **Ruang Lingkup Sistem**: Mendefinisikan sistem sebagai gabungan dua komponen: Plugin GLPI (UI/DB) dan FastAPI Engine (AI Orchestrator).
2. **Perspektif Produk**: Menjelaskan posisi plugin di dalam dashboard GLPI (Tools Menu) yang menjembatani interaksi pengguna dengan API Model Bahasa (LLM).
3. **Fungsi Utama**: 
   - Antarmuka Chat di Sidebar GLPI.
   - Penyimpanan riwayat persisten di DB GLPI (`sessions` dan `messages`).
   - Eksekusi AI Tools (Read-Only query ke entitas GLPI) melalui FastAPI.
4. **Batasan Sistem**: Requirement PHP 8.1+ dan GLPI v11/v12. Backend FastAPI dengan CrewAI, komunikasi Bahasa Indonesia, dan sifat query yang hanya baca.
5. **Asumsi & Ketergantungan**: Asumsi bahwa koneksi jaringan antara Server GLPI dan FastAPI Engine terjamin, dan API Token terkonfigurasi dengan benar.
6. **Pembaruan SRS Final**: Memperbarui struktur `SRS_-_GLPI.md` untuk merepresentasikan antarmuka UI, struktur database tabel plugin, dan spesifikasi integrasi REST API backend.
